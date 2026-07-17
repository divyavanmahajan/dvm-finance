import Foundation
import GRDB

/// Port of `core/snapshots.py`'s import half: `import_snapshot` +
/// `_merge_rules`/`_merge_transactions`/`_merge_budgets`/`_merge_reports` +
/// `_backup_db`/`_diff`/`_effective`.
///
/// Semantics (see `ios/docs/spec.md` "Snapshot codec" and `CLAUDE.md`):
/// incoming-wins on identity collision (including manual categorizations and
/// rule definitions — the *only* code path allowed to overwrite manual
/// edits), local-only rows are never deleted, the whole merge is one
/// database transaction after a file-system backup, and rules are
/// deliberately **not** reapplied afterwards — the snapshot's categorization
/// state (including `categorization_source`) is authoritative.
public enum SnapshotImporter {

    // MARK: - Per-entity counters (Python's `_Counter`)

    struct MergeCounter {
        var inserted = 0
        var updated = 0
        var unchanged = 0

        var jsonValue: JSONValue {
            .object([
                "inserted": .int(Int64(inserted)),
                "updated": .int(Int64(updated)),
                "unchanged": .int(Int64(unchanged)),
            ])
        }
    }

    // MARK: - Diff helper (Python's `_diff`)

    /// Port of `core/snapshots.py:_diff`: `{key: {"local": x, "incoming": y}}`
    /// for every key in `incoming` whose value differs from `local`'s (a
    /// missing key on either side reads as `JSONValue.null`, mirroring
    /// Python's `dict.get(key)`). Iterates `incoming`'s keys only — a key
    /// present only in `local` never appears in the diff, matching Python's
    /// `for key in incoming`.
    static func diff(local: [String: JSONValue], incoming: [String: JSONValue]) -> [String: JSONValue] {
        var result: [String: JSONValue] = [:]
        for (key, incomingValue) in incoming {
            let localValue = local[key] ?? .null
            if localValue != incomingValue {
                result[key] = .object(["local": localValue, "incoming": incomingValue])
            }
        }
        return result
    }

    /// Port of `core/snapshots.py:_effective`: `manual or category` — a
    /// **truthy** check, so an empty-string `manual` also falls through to
    /// `category` (unlike `TransactionRecord.effectiveCategory`'s plain
    /// `manualCategory ?? category`, which only falls through on `nil`).
    /// Kept local to the importer, matching the narrow scope of Python's
    /// module-private `_effective`, rather than changing the shared
    /// `TransactionRecord` computed property's (already-established, Phase A)
    /// nil-coalescing semantics.
    static func effectiveValue(_ category: String?, _ manual: String?) -> String? {
        if let manual, !manual.isEmpty { return manual }
        return category
    }

    // MARK: - Rules (Python's `_merge_rules` / `_apply_rule_data`)

    struct RuleMergeResult {
        var counter = MergeCounter()
        var overwrites: [JSONValue] = []
        /// Incoming machine-local rule id (as `String`) -> local rule id —
        /// used to remap `categorization_source` (transactions) and
        /// `rule_id` (reports).
        var idMap: [String: Int64] = [:]
    }

    private static func applyRuleFields(_ rule: inout CategorizationRuleRecord, data: Categorizer.RuleSnapshot) {
        rule.priority = data.priority
        rule.ruleType = data.ruleType
        rule.matchPattern = data.matchPattern
        rule.fieldTarget = data.fieldTarget
        rule.matchValue = data.matchValue
        rule.category = data.category
        rule.tags = data.tags
        rule.isActive = data.isActive
        rule.isTagOnly = data.isTagOnly
        rule.notes = data.notes
        rule.filterAccount = data.filterAccount
        rule.filterCurrency = data.filterCurrency
        rule.filterDateFrom = data.filterDateFrom.flatMap { DatabaseDateFormat.dateOnly.date(from: $0) }
        rule.filterDateTo = data.filterDateTo.flatMap { DatabaseDateFormat.dateOnly.date(from: $0) }
    }

    /// Incoming wins: conditions are replaced wholesale (delete-all, then
    /// insert every incoming condition), matching Python's
    /// `rule.conditions.clear()` + re-append inside `_apply_rule_data`.
    private static func replaceConditions(
        db: Database,
        ruleId: Int64,
        with conditions: [Categorizer.RuleConditionSnapshot]
    ) throws {
        try RuleConditionRecord.filter(Column("rule_id") == ruleId).deleteAll(db)
        for condition in conditions {
            var record = RuleConditionRecord(
                ruleId: ruleId,
                fieldTarget: condition.fieldTarget,
                matchPattern: condition.matchPattern,
                matchValue: condition.matchValue,
                operatorValue: condition.operatorValue,
                sortOrder: condition.sortOrder
            )
            try record.insert(db)
        }
    }

    /// Port of `core/snapshots.py:_merge_rules`.
    static func mergeRules(db: Database, incomingRules: [Categorizer.RuleSnapshot]) throws -> RuleMergeResult {
        var result = RuleMergeResult()

        for data in incomingRules {
            let incomingCmp = SnapshotCodec.comparableObject(data)

            if var existing = try CategorizationRuleRecord.filter(Column("uuid") == data.uuid).fetchOne(db) {
                let existingId = existing.id! // fetched row always has an id
                let existingConditions = try RuleConditionRecord
                    .filter(Column("rule_id") == existingId)
                    .order(Column("sort_order").asc)
                    .fetchAll(db)
                let localSnapshot = Categorizer.makeRuleSnapshot(rule: existing, conditions: existingConditions)
                let localCmp = SnapshotCodec.comparableObject(localSnapshot)

                if localCmp == incomingCmp {
                    result.counter.unchanged += 1
                } else {
                    result.overwrites.append(.object([
                        "uuid": .string(data.uuid),
                        "fields": .object(diff(local: localCmp, incoming: incomingCmp)),
                    ]))
                    applyRuleFields(&existing, data: data)
                    try existing.update(db)
                    try replaceConditions(db: db, ruleId: existingId, with: data.conditions)
                    result.counter.updated += 1
                }
                if let incomingId = data.id {
                    result.idMap[String(incomingId)] = existingId
                }
            } else {
                var newRule = CategorizationRuleRecord(
                    uuid: data.uuid,
                    ruleType: data.ruleType,
                    matchPattern: data.matchPattern,
                    matchValue: data.matchValue
                )
                applyRuleFields(&newRule, data: data)
                try newRule.insert(db)
                let newId = newRule.id!
                try replaceConditions(db: db, ruleId: newId, with: data.conditions)
                result.counter.inserted += 1
                if let incomingId = data.id {
                    result.idMap[String(incomingId)] = newId
                }
            }
        }

        return result
    }

    // MARK: - Transactions (Python's `_merge_transactions`)

    struct TransactionMergeResult {
        var counter = MergeCounter()
        var overwrites: [JSONValue] = []
        var changeItems: [Categorizer.TxnChange] = []
    }

    /// Port of `core/snapshots.py:_merge_transactions`.
    static func mergeTransactions(
        db: Database,
        incomingTransactions: [SnapshotTransaction],
        ruleIdMap: [String: Int64]
    ) throws -> TransactionMergeResult {
        var result = TransactionMergeResult()

        for original in incomingTransactions {
            var data = original
            // `categorization_source` stores `str(rule.id)`, which is
            // machine-local; remap to the local id of the same rule
            // (matched by uuid in `mergeRules`) before comparing/storing.
            if let source = data.categorizationSource, let mappedId = ruleIdMap[source] {
                data.categorizationSource = String(mappedId)
            }

            guard let local = try TransactionRecord.fetchOne(db, key: data.id) else {
                let newRecord = try SnapshotCodec.makeTransactionRecord(data)
                try newRecord.insert(db)
                result.counter.inserted += 1
                continue
            }

            let localSnapshot = SnapshotCodec.makeSnapshotTransaction(local)
            if localSnapshot == data {
                result.counter.unchanged += 1
                continue
            }

            // Incoming wins — including manual_category/manual_tags. This is
            // the only path allowed to overwrite manual edits (Golden
            // Principle 2), and it always records what it overwrote.
            let localCmp = SnapshotCodec.comparableObject(localSnapshot)
            let incomingCmp = SnapshotCodec.comparableObject(data)
            result.overwrites.append(.object([
                "id": .string(data.id),
                "fields": .object(diff(local: localCmp, incoming: incomingCmp)),
            ]))

            let oldEffectiveCategory = effectiveValue(local.category, local.manualCategory)
            let oldEffectiveTags = effectiveValue(local.tags, local.manualTags)
            let newEffectiveCategory = effectiveValue(data.category, data.manualCategory)
            let newEffectiveTags = effectiveValue(data.tags, data.manualTags)
            if oldEffectiveCategory != newEffectiveCategory || oldEffectiveTags != newEffectiveTags {
                result.changeItems.append(Categorizer.TxnChange(
                    transactionId: data.id,
                    oldCategory: oldEffectiveCategory,
                    newCategory: newEffectiveCategory,
                    oldTags: oldEffectiveTags,
                    newTags: newEffectiveTags
                ))
            }

            let updatedRecord = try SnapshotCodec.makeTransactionRecord(data)
            try updatedRecord.update(db)
            result.counter.updated += 1
        }

        return result
    }

    // MARK: - Budgets (Python's `_merge_budgets`)

    struct BudgetMergeResult {
        var counter = MergeCounter()
        var overwrites: [JSONValue] = []
    }

    /// Port of `core/snapshots.py:_merge_budgets`. Identity is
    /// `(category, period, start_date)`; if no exact match, falls back to
    /// `(category, period)` alone (the DB-unique pair) — a local row with
    /// the same `(category, period)` but a different `start_date` still
    /// collides, and incoming wins on that row.
    static func mergeBudgets(db: Database, incomingBudgets: [SnapshotBudget]) throws -> BudgetMergeResult {
        var result = BudgetMergeResult()

        for data in incomingBudgets {
            let startDate = data.startDate.flatMap { DatabaseDateFormat.dateOnly.date(from: $0) }
            let endDate = data.endDate.flatMap { DatabaseDateFormat.dateOnly.date(from: $0) }

            var local = try BudgetRecord
                .filter(Column("category") == data.category)
                .filter(Column("period") == data.period)
                .filter(Column("start_date") == startDate)
                .fetchOne(db)
            if local == nil {
                local = try BudgetRecord
                    .filter(Column("category") == data.category)
                    .filter(Column("period") == data.period)
                    .fetchOne(db)
            }

            guard var existing = local else {
                var newBudget = BudgetRecord(
                    category: data.category,
                    amount: try SnapshotCodec.parseDecimal(data.amount),
                    period: data.period,
                    startDate: startDate,
                    endDate: endDate,
                    notes: data.notes
                )
                try newBudget.insert(db)
                result.counter.inserted += 1
                continue
            }

            let localSnapshot = SnapshotCodec.makeSnapshotBudget(existing)
            if localSnapshot == data {
                result.counter.unchanged += 1
                continue
            }

            let localCmp = SnapshotCodec.comparableObject(localSnapshot)
            let incomingCmp = SnapshotCodec.comparableObject(data)
            result.overwrites.append(.object([
                "key": .object([
                    "category": .string(data.category),
                    "period": .string(data.period),
                    "start_date": .from(data.startDate),
                ]),
                "fields": .object(diff(local: localCmp, incoming: incomingCmp)),
            ]))

            existing.amount = try SnapshotCodec.parseDecimal(data.amount)
            existing.startDate = startDate
            existing.endDate = endDate
            existing.notes = data.notes
            try existing.update(db)
            result.counter.updated += 1
        }

        return result
    }

    // MARK: - Reports (Python's `_merge_reports`)

    /// `(created_at, action, rule_uuid)` — Python's stable-enough identity
    /// for reports (they have no cross-machine uuid of their own).
    struct ReportKey: Hashable {
        var createdAt: String
        var action: String?
        var ruleUuid: String?
    }

    /// Port of `core/snapshots.py:_merge_reports`. Existing local reports
    /// are never modified or deleted; a `(created_at, action, rule_uuid)`
    /// match is treated as "already imported" (unchanged), so re-importing
    /// the same snapshot does not duplicate the audit trail.
    ///
    /// `created_at` identity strings are always rendered through
    /// `SnapshotCodec.renderDateTime` (plain-seconds precision) on **both**
    /// sides — a locally-stored report's `createdAt: Date` already lost any
    /// sub-second precision going through `RuleChangeReportRecord`'s own
    /// `DatabaseDateFormat.dateTime` column encoding (Phase A), so comparing
    /// at that same precision (rather than Python's raw microsecond-exact
    /// string) is what makes re-import idempotency hold in practice.
    static func mergeReports(
        db: Database,
        incomingReports: [SnapshotReport],
        ruleIdMap: [String: Int64]
    ) throws -> MergeCounter {
        var counter = MergeCounter()

        let existingReports = try RuleChangeReportRecord.fetchAll(db)
        var existingKeys = Set(existingReports.map {
            ReportKey(
                createdAt: SnapshotCodec.renderDateTime($0.createdAt),
                action: $0.action,
                ruleUuid: $0.ruleUuid
            )
        })

        for data in incomingReports {
            let storedDate = data.createdAt.flatMap(SnapshotCodec.parseDateTime) ?? Date()
            let key = ReportKey(
                createdAt: SnapshotCodec.renderDateTime(storedDate),
                action: data.action,
                ruleUuid: data.ruleUuid
            )

            if existingKeys.contains(key) {
                counter.unchanged += 1
                continue
            }

            let mappedRuleId = data.ruleId.flatMap { ruleIdMap[String($0)] }
            var report = RuleChangeReportRecord(
                createdAt: storedDate,
                ruleId: mappedRuleId,
                ruleUuid: data.ruleUuid,
                action: (data.action?.isEmpty == false) ? data.action! : "update",
                ruleBefore: SnapshotCodec.jsonColumnString(data.ruleBefore),
                ruleAfter: SnapshotCodec.jsonColumnString(data.ruleAfter),
                summary: SnapshotCodec.jsonColumnString(data.summary)
            )
            try report.insert(db)
            let reportId = report.id!

            for item in data.items {
                var itemRecord = RuleChangeItemRecord(
                    reportId: reportId,
                    transactionId: item.transactionId,
                    oldCategory: item.oldCategory,
                    newCategory: item.newCategory,
                    oldTags: item.oldTags,
                    newTags: item.newTags
                )
                try itemRecord.insert(db)
            }

            existingKeys.insert(key)
            counter.inserted += 1
        }

        return counter
    }

    // MARK: - Backup (Python's `_backup_db`)

    /// Port of `core/snapshots.py:_backup_db`: `<stem>.backup-YYYYMMDD-HHMMSS<suffix>`,
    /// deduped with `-1`, `-2`, ... if a backup from the same second already
    /// exists.
    ///
    /// Extra step vs. Python (`shutil.copy2`, a plain file copy): if the
    /// writer has a WAL journal (`AppDatabase.live(at:)` enables
    /// `PRAGMA journal_mode = WAL`), recent commits can still be sitting in
    /// the `-wal` file rather than the main database file, so a raw
    /// file-system copy of just the `.sqlite` file could silently miss them.
    /// A passive checkpoint flushes the WAL into the main file first, so the
    /// backup this function makes is always complete. `core/models.py`'s
    /// SQLite usage on desktop is not WAL-mode, so Python's importer never
    /// needed this step.
    static func backupDatabaseFile(appDatabase: AppDatabase, databaseURL: URL) throws -> URL {
        // Best-effort: `writeWithoutTransaction`'s closure genuinely
        // `throws` here (it calls `db.checkpoint`, not `try?`-wrapped), so
        // `rethrows` makes this call throwing; `try?` swallows a checkpoint
        // failure (e.g. a concurrent reader) rather than aborting the
        // import over what is a best-effort completeness improvement, not a
        // hard requirement — see the doc comment above.
        _ = try? appDatabase.dbWriter.writeWithoutTransaction { db in
            try db.checkpoint(.passive)
        }

        let directory = databaseURL.deletingLastPathComponent()
        let stem = databaseURL.deletingPathExtension().lastPathComponent
        let ext = databaseURL.pathExtension
        let suffix = ext.isEmpty ? "" : ".\(ext)"
        let stamp = SnapshotCodec.localFilenameStampFormatter.string(from: Date())

        var backupURL = directory.appendingPathComponent("\(stem).backup-\(stamp)\(suffix)")
        var n = 1
        while FileManager.default.fileExists(atPath: backupURL.path) {
            backupURL = directory.appendingPathComponent("\(stem).backup-\(stamp)-\(n)\(suffix)")
            n += 1
        }
        try FileManager.default.copyItem(at: databaseURL, to: backupURL)
        return backupURL
    }

    // MARK: - import_snapshot

    /// Port of `core/snapshots.py:import_snapshot`.
    ///
    /// 1. If `databaseURL` exists on disk, back it up first (outside the
    ///    merge transaction, matching Python's ordering).
    /// 2. Run the whole incoming-wins merge — rules, then transactions
    ///    (using the rule id map), then budgets, then reports (using the
    ///    same id map) — plus the `snapshot_imports` row and an
    ///    `action = "import"` `RuleChangeReportRecord` (built directly, not
    ///    via `Categorizer.recordRuleChange`, which would reapply rules —
    ///    the snapshot's categorization state is authoritative) in **one**
    ///    `dbWriter.write` transaction, so any failure rolls everything back.
    @discardableResult
    public static func importSnapshot(
        appDatabase: AppDatabase,
        document: SnapshotDocument,
        databaseURL: URL
    ) throws -> SnapshotImportRecord {
        if FileManager.default.fileExists(atPath: databaseURL.path) {
            _ = try backupDatabaseFile(appDatabase: appDatabase, databaseURL: databaseURL)
        }

        return try appDatabase.dbWriter.write { db -> SnapshotImportRecord in
            let ruleResult = try mergeRules(db: db, incomingRules: document.rules)
            let transactionResult = try mergeTransactions(
                db: db,
                incomingTransactions: document.transactions,
                ruleIdMap: ruleResult.idMap
            )
            let budgetResult = try mergeBudgets(db: db, incomingBudgets: document.budgets)
            let reportCounter = try mergeReports(
                db: db,
                incomingReports: document.ruleChangeReports,
                ruleIdMap: ruleResult.idMap
            )

            let entityCounters: [(name: String, counter: MergeCounter)] = [
                ("transactions", transactionResult.counter),
                ("rules", ruleResult.counter),
                ("budgets", budgetResult.counter),
                ("rule_change_reports", reportCounter),
            ]

            // Audit trail: an action="import" RuleChangeReport (renders in
            // the rules History list) carrying the per-transaction effective
            // category/tag diff. Built directly here, matching Python's
            // comment: NOT via `record_rule_change`, which would reapply
            // rules.
            var summaryFields: [String: JSONValue] = [
                "changed": .int(Int64(transactionResult.changeItems.count)),
            ]
            for (entity, counter) in entityCounters {
                if counter.inserted != 0 { summaryFields["\(entity)_inserted"] = .int(Int64(counter.inserted)) }
                if counter.updated != 0 { summaryFields["\(entity)_updated"] = .int(Int64(counter.updated)) }
                if counter.unchanged != 0 { summaryFields["\(entity)_unchanged"] = .int(Int64(counter.unchanged)) }
            }

            var changeReport = RuleChangeReportRecord(
                action: "import",
                summary: SnapshotCodec.jsonColumnString(.object(summaryFields))
            )
            try changeReport.insert(db)
            let changeReportId = changeReport.id!
            for change in transactionResult.changeItems {
                var item = RuleChangeItemRecord(
                    reportId: changeReportId,
                    transactionId: change.transactionId,
                    oldCategory: change.oldCategory,
                    newCategory: change.newCategory,
                    oldTags: change.oldTags,
                    newTags: change.newTags
                )
                try item.insert(db)
            }

            let countsJSON = JSONValue.object(Dictionary(uniqueKeysWithValues: entityCounters.map { ($0.name, $0.counter.jsonValue) }))
            let overwritesJSON = JSONValue.object([
                "transactions": .array(transactionResult.overwrites),
                "rules": .array(ruleResult.overwrites),
                "budgets": .array(budgetResult.overwrites),
            ])

            var importRecord = SnapshotImportRecord(
                sourceMachineId: document.header.machineId,
                schemaVersion: document.header.schemaVersion,
                counts: SnapshotCodec.jsonColumnString(countsJSON),
                overwrites: SnapshotCodec.jsonColumnString(overwritesJSON),
                // Delta provenance from the imported file's header — mirrors
                // desktop `import_snapshot`'s `is_delta=bool(header.get("delta"))`
                // / `delta_since=_parse_datetime(header.get("since"))`.
                isDelta: document.header.delta ?? false,
                deltaSince: document.header.since.flatMap(SnapshotCodec.parseDateTime)
            )
            try importRecord.insert(db)
            return importRecord
        }
    }
}
