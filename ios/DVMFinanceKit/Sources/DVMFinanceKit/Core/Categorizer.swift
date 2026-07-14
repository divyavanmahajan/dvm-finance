import Foundation
import CoreFoundation
import GRDB

/// Port of `core/categorizer.py` (matching + `apply_rules` + `record_rule_change`;
/// `preview_rule` is intentionally **not** ported — see `ios/docs/plan.md`
/// "Phase B" and `CLAUDE.md`: "skip preview_rule — not in v1").
public enum Categorizer {

    /// Port of `core/categorizer.py: MANUAL_SOURCE`.
    public static let manualSource = "manual"

    // MARK: - Transaction <-> match-context

    /// Port of `core/categorizer.py:_txn_to_dict`. The minimal read-only view
    /// of a transaction the matcher needs; decouples matching from GRDB
    /// record types so `_apply_rule_to_transaction`'s logic reads exactly
    /// like its Python source.
    public struct MatchContext: Equatable {
        public var description: String
        public var descriptionStructured: String?
        public var accountNumber: String
        public var currency: String
        public var transactiondate: Date?

        public init(
            description: String,
            descriptionStructured: String?,
            accountNumber: String,
            currency: String,
            transactiondate: Date?
        ) {
            self.description = description
            self.descriptionStructured = descriptionStructured
            self.accountNumber = accountNumber
            self.currency = currency
            self.transactiondate = transactiondate
        }

        /// `txn.description or ""` — `nil` and `""` both collapse to `""`.
        public init(_ transaction: TransactionRecord) {
            self.description = transaction.description ?? ""
            self.descriptionStructured = transaction.descriptionStructured
            self.accountNumber = transaction.accountNumber
            self.currency = transaction.currency
            self.transactiondate = transaction.transactiondate
        }
    }

    // MARK: - Structured description JSON

    /// Port of `core/categorizer.py:_parse_structured_data`. `nil`/empty
    /// `description_structured`, invalid JSON, or JSON that doesn't decode to
    /// an object all yield `nil` (Python additionally tolerates a
    /// pre-parsed dict passed directly, which cannot occur here since our
    /// column is always `String?`).
    static func parseStructuredData(_ descriptionStructured: String?) -> [String: Any]? {
        guard let descriptionStructured, !descriptionStructured.isEmpty else { return nil }
        guard let data = descriptionStructured.data(using: .utf8) else { return nil }
        guard let object = try? JSONSerialization.jsonObject(with: data) else { return nil }
        return object as? [String: Any]
    }

    /// Python's `if not structured_data:` truthy check — `nil` **and** an
    /// empty dict `{}` (valid JSON `{}`) are both falsy, unlike a Swift
    /// `Optional` check alone.
    private static func isTruthy(_ structuredData: [String: Any]?) -> Bool {
        guard let structuredData else { return false }
        return !structuredData.isEmpty
    }

    /// Renders a JSON-decoded structured-field value exactly like the
    /// repeated Python pattern
    /// `"true"/"false" if raw is True/False else (str(raw) if raw is not None else "")`.
    /// `raw == nil` here stands in for "key absent" (Python's `.get(key, "")`
    /// default, already `""`) as well as "value is JSON null" (Python
    /// `None`, mapped to `""` by the `is not None` guard) — both collapse to
    /// the same observable result, so one function covers both call sites.
    ///
    /// NSNumber note: `JSONSerialization` represents JSON `true`/`false` as
    /// the CoreFoundation singletons `kCFBooleanTrue`/`kCFBooleanFalse`,
    /// distinguishable from a numeric `NSNumber` (e.g. the JSON integer `1`)
    /// via `CFGetTypeID` — a plain `as? Bool` cast is not reliable for this
    /// distinction on all Foundation implementations, so this checks the
    /// CFType explicitly rather than casting.
    private static func pythonJSONString(_ raw: Any?) -> String {
        guard let raw else { return "" }
        if raw is NSNull { return "" }
        if let number = raw as? NSNumber {
            if CFGetTypeID(number) == CFBooleanGetTypeID() {
                return number.boolValue ? "true" : "false"
            }
            if CFNumberIsFloatType(number) {
                // Matches Python `str(float)` for a JSON number with a
                // decimal point (shortest round-trip rendering).
                return "\(number.doubleValue)"
            }
            return String(number.int64Value)
        }
        if let string = raw as? String {
            return string
        }
        return "\(raw)"
    }

    /// `structured_data.get(field_target, "")`-then-stringify, folding the
    /// "no structured data at all" case (Python: `field_target and structured_data`
    /// being falsy) into the same `""` result the missing-key case produces.
    private static func structuredFieldString(_ structuredData: [String: Any]?, _ fieldTarget: String) -> String {
        pythonJSONString(structuredData?[fieldTarget])
    }

    // MARK: - Match patterns

    /// Port of `core/categorizer.py:_apply_match_pattern`.
    ///
    /// `contains`/`exact`/`starts_with`/`ends_with` compare **normalized**
    /// strings; `regex` searches the **raw** `matchValue` pattern
    /// (case-insensitive) against the **normalized** field value — Python
    /// computes but never uses the normalized pattern for the regex branch,
    /// see `ios/docs/spec.md` "Rule engine": "regex = case-insensitive search
    /// of the raw pattern against the normalized field value".
    ///
    /// `contains`/`ends_with`(iban)/`contains`(iban) all guard an empty
    /// normalized pattern explicitly: Python's `x in y` / `str.startswith`/
    /// `str.endswith` all treat an empty needle as always-matching, but
    /// Swift's `String.contains(_:)` does not reliably agree for an empty
    /// argument, so `contains` is special-cased here to preserve Python's
    /// substring semantics exactly. `hasPrefix("")`/`hasSuffix("")` already
    /// agree with Python's `startswith("")`/`endswith("")` (`true`) natively.
    static func applyMatchPattern(fieldValue: String, matchPattern: String, matchValue: String) -> Bool {
        let fv = CoreNormalize.normalizeStringForMatching(fieldValue)
        let mv = CoreNormalize.normalizeStringForMatching(matchValue)
        switch matchPattern {
        case "contains":
            return mv.isEmpty || fv.contains(mv)
        case "exact":
            return fv == mv
        case "starts_with":
            return fv.hasPrefix(mv)
        case "ends_with":
            return fv.hasSuffix(mv)
        case "regex":
            guard let regex = try? NSRegularExpression(pattern: matchValue, options: [.caseInsensitive]) else {
                return false
            }
            let range = NSRange(fv.startIndex..<fv.endIndex, in: fv)
            return regex.firstMatch(in: fv, options: [], range: range) != nil
        default:
            return false
        }
    }

    /// The IBAN-in-free-text fallback pattern used by `account_iban` rules
    /// when no structured `iban` field is present — Python:
    /// `r"IBAN[:\s]+([A-Z]{2}\d{2}[A-Z0-9]{4,30})"`, searched against the
    /// **uppercased** description.
    private static let ibanFallbackRegex = try! NSRegularExpression(
        pattern: "IBAN[:\\s]+([A-Z]{2}\\d{2}[A-Z0-9]{4,30})"
    )

    private static func extractIBAN(fromUppercasedDescription descUpper: String) -> String? {
        let range = NSRange(descUpper.startIndex..<descUpper.endIndex, in: descUpper)
        guard
            let match = ibanFallbackRegex.firstMatch(in: descUpper, options: [], range: range),
            match.numberOfRanges > 1,
            let groupRange = Range(match.range(at: 1), in: descUpper)
        else {
            return nil
        }
        return String(descUpper[groupRange])
    }

    /// Port of `core/categorizer.py:_evaluate_single_condition` (extra
    /// AND/OR conditions folded onto a rule's primary match).
    static func evaluateSingleCondition(
        fieldTarget: String,
        matchPattern: String,
        matchValue: String,
        context: MatchContext,
        structuredData: [String: Any]?
    ) -> Bool {
        let fieldValue: String
        if fieldTarget == "description" {
            fieldValue = context.description
        } else if !fieldTarget.isEmpty, isTruthy(structuredData) {
            fieldValue = structuredFieldString(structuredData, fieldTarget)
        } else {
            return false
        }
        return applyMatchPattern(fieldValue: fieldValue, matchPattern: matchPattern, matchValue: matchValue)
    }

    /// Port of `core/categorizer.py:_check_primary_condition`.
    ///
    /// Dispatch order: `structured_field` -> `account_iban` (with the
    /// description-regex IBAN fallback) -> `description`/`full_description`
    /// -> generic structured `field_target` -> no match.
    static func checkPrimaryCondition(
        rule: CategorizationRuleRecord,
        context: MatchContext,
        structuredData: [String: Any]?
    ) -> Bool {
        if rule.ruleType == "structured_field" {
            guard isTruthy(structuredData) else { return false }
            let fieldValue = structuredFieldString(structuredData, rule.fieldTarget ?? "")
            return applyMatchPattern(fieldValue: fieldValue, matchPattern: rule.matchPattern, matchValue: rule.matchValue)
        }

        if rule.ruleType == "account_iban" {
            if rule.fieldTarget == "iban" {
                var iban: String?
                if isTruthy(structuredData) {
                    let rendered = structuredFieldString(structuredData, "iban")
                    iban = rendered.isEmpty ? nil : rendered
                }
                if iban == nil {
                    iban = extractIBAN(fromUppercasedDescription: context.description.uppercased())
                }
                if let iban, !iban.isEmpty {
                    let ibanNorm = CoreNormalize.normalizeStringForMatching(iban)
                    let mvNorm = CoreNormalize.normalizeStringForMatching(rule.matchValue)
                    switch rule.matchPattern {
                    case "exact":
                        return ibanNorm == mvNorm
                    case "ends_with":
                        return ibanNorm.hasSuffix(mvNorm)
                    case "contains":
                        return mvNorm.isEmpty || ibanNorm.contains(mvNorm)
                    default:
                        return false
                    }
                }
                return false
            } else if rule.fieldTarget == "description" {
                let descNorm = CoreNormalize.normalizeStringForMatching(context.description)
                let mvNorm = CoreNormalize.normalizeStringForMatching(rule.matchValue)
                return mvNorm.isEmpty || descNorm.contains(mvNorm)
            }
            return false
        }

        if rule.fieldTarget == "description" || rule.ruleType == "full_description" {
            return applyMatchPattern(fieldValue: context.description, matchPattern: rule.matchPattern, matchValue: rule.matchValue)
        } else if let fieldTarget = rule.fieldTarget, !fieldTarget.isEmpty, isTruthy(structuredData) {
            let fieldValue = structuredFieldString(structuredData, fieldTarget)
            return applyMatchPattern(fieldValue: fieldValue, matchPattern: rule.matchPattern, matchValue: rule.matchValue)
        } else {
            return false
        }
    }

    /// Port of `core/categorizer.py:_apply_rule_to_transaction`.
    ///
    /// `conditions` must already be in ascending `sort_order` (as loaded by
    /// `loadActiveRules`) — the AND/OR fold is a left-fold over this
    /// sequence, order-sensitive by design (matches the Python `for cond in
    /// conditions:` loop over an ORM relationship ordered the same way).
    public static func applyRuleToTransaction(
        rule: CategorizationRuleRecord,
        conditions: [RuleConditionRecord],
        context: MatchContext
    ) -> Bool {
        let structuredData = parseStructuredData(context.descriptionStructured)

        guard checkPrimaryCondition(rule: rule, context: context, structuredData: structuredData) else {
            return false
        }

        if !conditions.isEmpty {
            var running = true
            for condition in conditions {
                let result = evaluateSingleCondition(
                    fieldTarget: condition.fieldTarget,
                    matchPattern: condition.matchPattern,
                    matchValue: condition.matchValue,
                    context: context,
                    structuredData: structuredData
                )
                if condition.operatorValue == "OR" {
                    running = running || result
                } else {
                    running = running && result
                }
            }
            if !running { return false }
        }

        if let filterAccount = rule.filterAccount, !filterAccount.isEmpty, context.accountNumber != filterAccount {
            return false
        }
        if let filterCurrency = rule.filterCurrency, !filterCurrency.isEmpty, context.currency != filterCurrency {
            return false
        }
        if rule.filterDateFrom != nil || rule.filterDateTo != nil {
            if let transDate = context.transactiondate {
                if let from = rule.filterDateFrom, transDate < from { return false }
                if let to = rule.filterDateTo, transDate > to { return false }
            }
        }

        return true
    }

    // MARK: - Rule loading / splitting

    /// A rule and its extra conditions, pre-loaded in the order
    /// `applyRuleToTransaction` requires (conditions ascending `sort_order`).
    public struct RuleWithConditions {
        public var rule: CategorizationRuleRecord
        public var conditions: [RuleConditionRecord]

        public init(rule: CategorizationRuleRecord, conditions: [RuleConditionRecord]) {
            self.rule = rule
            self.conditions = conditions
        }
    }

    /// Port of `core/categorizer.py:_load_active_rules` (+ eager-loading each
    /// rule's conditions, mirroring the ORM relationship Python reads
    /// lazily). Active rules only, ordered `priority asc, id asc`.
    public static func loadActiveRules(_ db: Database) throws -> [RuleWithConditions] {
        let rules = try CategorizationRuleRecord
            .filter(Column("is_active") == true)
            .order(Column("priority").asc, Column("id").asc)
            .fetchAll(db)
        return try rules.map { rule in
            let conditions = try RuleConditionRecord
                .filter(Column("rule_id") == rule.id)
                .order(Column("sort_order").asc)
                .fetchAll(db)
            return RuleWithConditions(rule: rule, conditions: conditions)
        }
    }

    // MARK: - apply_rules

    /// Port of `core/categorizer.py:TxnChange`.
    public struct TxnChange: Equatable {
        public var transactionId: String
        public var oldCategory: String?
        public var newCategory: String?
        public var oldTags: String?
        public var newTags: String?

        public init(
            transactionId: String,
            oldCategory: String?,
            newCategory: String?,
            oldTags: String?,
            newTags: String?
        ) {
            self.transactionId = transactionId
            self.oldCategory = oldCategory
            self.newCategory = newCategory
            self.oldTags = oldTags
            self.newTags = newTags
        }
    }

    /// Port of `core/categorizer.py:_merge_tags`.
    ///
    /// De-duplicates while preserving first-seen order, existing tags first.
    static func mergeTags(_ existingTags: String?, _ newTags: String?) -> String? {
        guard let newTags, !newTags.isEmpty else { return existingTags }
        let existingList = splitTags(existingTags)
        let newList = splitTags(newTags)
        var merged = existingList
        for tag in newList where !merged.contains(tag) {
            merged.append(tag)
        }
        return merged.isEmpty ? nil : merged.joined(separator: ",")
    }

    private static func splitTags(_ tags: String?) -> [String] {
        (tags ?? "")
            .split(separator: ",", omittingEmptySubsequences: false)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    private static func isManual(_ transaction: TransactionRecord) -> Bool {
        transaction.categorizationSource == manualSource
    }

    /// Port of `core/categorizer.py:_rule_result`.
    ///
    /// `category`: `nil` if the rule's category is `nil`/empty, else
    /// lowercased. `tags`: `nil` if the rule's tags are `nil`/empty, else
    /// kept verbatim (never lowercased).
    private static func ruleResult(_ rule: CategorizationRuleRecord) -> (category: String?, tags: String?) {
        let category = (rule.category?.isEmpty == false) ? rule.category!.lowercased() : nil
        let tags = (rule.tags?.isEmpty == false) ? rule.tags : nil
        return (category, tags)
    }

    /// Port of `core/categorizer.py:apply_rules`.
    ///
    /// Two-pass, exactly as documented in `docs/architecture.md` (§ Rules
    /// categorization) and `ios/docs/spec.md` "Rule engine":
    ///
    /// 1. Category rules (`is_tag_only == false`), priority order, first
    ///    match wins, non-manual transactions only. A transaction with no
    ///    matching rule gets `category = nil` (effective "Uncategorized").
    ///    `categorizationSource` is kept in sync with the winning rule's id
    ///    (as a `String`) **even when** the resulting category/tags are
    ///    unchanged from before.
    /// 2. Tag-only rules (`is_tag_only == true`), against **all**
    ///    transactions (including manually-categorized ones) — every
    ///    matching rule's tags are merged in, de-duplicated; `category` is
    ///    never touched in this pass.
    ///
    /// Writes every changed transaction in one GRDB write (caller is
    /// expected to already be inside a `db.write { }` transaction — this
    /// function takes a `Database`, not an `AppDatabase`, exactly like
    /// `Dedup.swift`). Returns the transactions whose rule-assigned category
    /// or tags changed (order-insensitive; compare by id).
    @discardableResult
    public static func applyRules(
        db: Database,
        transactionIds: [String]? = nil,
        rules: [RuleWithConditions]? = nil
    ) throws -> [TxnChange] {
        let allRules = try rules ?? loadActiveRules(db)
        let categoryRules = allRules.filter { !$0.rule.isTagOnly }
        let tagOnlyRules = allRules.filter { $0.rule.isTagOnly }

        let request: QueryInterfaceRequest<TransactionRecord> = {
            if let transactionIds {
                return TransactionRecord.filter(keys: transactionIds)
            }
            return TransactionRecord.all()
        }()
        var txns = try request.fetchAll(db)

        var changeOrder: [String] = []
        var changesByID: [String: TxnChange] = [:]
        var dirtyIDs: Set<String> = []

        // Pass 1: category rules, non-manual transactions only, first match wins.
        for index in txns.indices {
            let id = txns[index].id
            if isManual(txns[index]) { continue }

            let oldCategory = txns[index].category
            let oldTags = txns[index].tags
            let context = MatchContext(txns[index])

            var matchedRule: CategorizationRuleRecord?
            for entry in categoryRules
            where applyRuleToTransaction(rule: entry.rule, conditions: entry.conditions, context: context) {
                matchedRule = entry.rule
                break
            }

            let newCategory: String?
            let newTags: String?
            let newSource: String?
            if let matchedRule {
                let result = ruleResult(matchedRule)
                newCategory = result.category
                newTags = result.tags
                newSource = matchedRule.id.map { String($0) }
            } else {
                newCategory = nil
                newTags = nil
                newSource = nil
            }

            if newCategory != oldCategory || newTags != oldTags {
                txns[index].category = newCategory
                txns[index].tags = newTags
                txns[index].categorizationSource = newSource
                dirtyIDs.insert(id)
                changesByID[id] = TxnChange(
                    transactionId: id,
                    oldCategory: oldCategory,
                    newCategory: newCategory,
                    oldTags: oldTags,
                    newTags: newTags
                )
                changeOrder.append(id)
            } else if txns[index].categorizationSource != newSource {
                // Keep categorization_source in sync even when category/tags
                // are unchanged — see the Python comment of the same name.
                txns[index].categorizationSource = newSource
                dirtyIDs.insert(id)
            }
        }

        // Pass 2: tag-only rules, all transactions (including manual ones);
        // every match applies (not just the first); category untouched.
        for index in txns.indices {
            let id = txns[index].id
            let context = MatchContext(txns[index])
            let preTags = txns[index].tags
            var mergedTags = preTags

            for entry in tagOnlyRules
            where applyRuleToTransaction(rule: entry.rule, conditions: entry.conditions, context: context) {
                mergedTags = mergeTags(mergedTags, entry.rule.tags)
            }

            if mergedTags != preTags {
                txns[index].tags = mergedTags
                dirtyIDs.insert(id)
                if var existing = changesByID[id] {
                    existing.newTags = mergedTags
                    changesByID[id] = existing
                } else {
                    changesByID[id] = TxnChange(
                        transactionId: id,
                        oldCategory: txns[index].category,
                        newCategory: txns[index].category,
                        oldTags: preTags,
                        newTags: mergedTags
                    )
                    changeOrder.append(id)
                }
            }
        }

        for txn in txns where dirtyIDs.contains(txn.id) {
            try txn.update(db)
        }

        return changeOrder.compactMap { changesByID[$0] }
    }

    // MARK: - Rule snapshots + change reports

    /// Port of `core/categorizer.py: RuleCondition` inside `rule_snapshot()`.
    public struct RuleConditionSnapshot: Codable, Equatable {
        public var fieldTarget: String
        public var matchPattern: String
        public var matchValue: String
        public var operatorValue: String
        public var sortOrder: Int

        enum CodingKeys: String, CodingKey {
            case fieldTarget = "field_target"
            case matchPattern = "match_pattern"
            case matchValue = "match_value"
            case operatorValue = "operator"
            case sortOrder = "sort_order"
        }

        public init(fieldTarget: String, matchPattern: String, matchValue: String, operatorValue: String, sortOrder: Int) {
            self.fieldTarget = fieldTarget
            self.matchPattern = matchPattern
            self.matchValue = matchValue
            self.operatorValue = operatorValue
            self.sortOrder = sortOrder
        }
    }

    /// Port of `core/categorizer.py:rule_snapshot`'s dict shape.
    public struct RuleSnapshot: Codable, Equatable {
        public var id: Int64?
        public var uuid: String
        public var priority: Int
        public var ruleType: String
        public var matchPattern: String
        public var fieldTarget: String?
        public var matchValue: String
        public var category: String?
        public var tags: String?
        public var isActive: Bool
        public var isTagOnly: Bool
        public var notes: String?
        public var filterAccount: String?
        public var filterCurrency: String?
        public var filterDateFrom: String?
        public var filterDateTo: String?
        public var conditions: [RuleConditionSnapshot]

        enum CodingKeys: String, CodingKey {
            case id, uuid, priority
            case ruleType = "rule_type"
            case matchPattern = "match_pattern"
            case fieldTarget = "field_target"
            case matchValue = "match_value"
            case category, tags
            case isActive = "is_active"
            case isTagOnly = "is_tag_only"
            case notes
            case filterAccount = "filter_account"
            case filterCurrency = "filter_currency"
            case filterDateFrom = "filter_date_from"
            case filterDateTo = "filter_date_to"
            case conditions
        }
    }

    /// Builds the `RuleSnapshot` value for a rule + its conditions
    /// (conditions need not be pre-sorted; this sorts by `sort_order` to
    /// match the Python relationship's load order).
    public static func makeRuleSnapshot(
        rule: CategorizationRuleRecord,
        conditions: [RuleConditionRecord]
    ) -> RuleSnapshot {
        RuleSnapshot(
            id: rule.id,
            uuid: rule.uuid,
            priority: rule.priority,
            ruleType: rule.ruleType,
            matchPattern: rule.matchPattern,
            fieldTarget: rule.fieldTarget,
            matchValue: rule.matchValue,
            category: rule.category,
            tags: rule.tags,
            isActive: rule.isActive,
            isTagOnly: rule.isTagOnly,
            notes: rule.notes,
            filterAccount: rule.filterAccount,
            filterCurrency: rule.filterCurrency,
            filterDateFrom: rule.filterDateFrom.map { DatabaseDateFormat.dateOnly.string(from: $0) },
            filterDateTo: rule.filterDateTo.map { DatabaseDateFormat.dateOnly.string(from: $0) },
            conditions: conditions
                .sorted { $0.sortOrder < $1.sortOrder }
                .map {
                    RuleConditionSnapshot(
                        fieldTarget: $0.fieldTarget,
                        matchPattern: $0.matchPattern,
                        matchValue: $0.matchValue,
                        operatorValue: $0.operatorValue,
                        sortOrder: $0.sortOrder
                    )
                }
        )
    }

    /// Port of `core/categorizer.py:rule_snapshot` — JSON-string form (`nil`
    /// input -> `nil` output, matching `rule_snapshot(None) is None`).
    public static func ruleSnapshot(rule: CategorizationRuleRecord?, conditions: [RuleConditionRecord]) -> String? {
        guard let rule else { return nil }
        let snapshot = makeRuleSnapshot(rule: rule, conditions: conditions)
        guard let data = try? JSONEncoder().encode(snapshot) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private static func jsonObject(_ text: String) -> [String: Any]? {
        guard let data = text.data(using: .utf8) else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }

    /// Port of `core/categorizer.py:record_rule_change`.
    ///
    /// Reapplies all active rules (`applyRules`) and persists an audit
    /// report + per-transaction items. `before`/`after` are JSON strings in
    /// `ruleSnapshot`'s shape (or `nil`); `ruleId`/`ruleUuid` are derived
    /// from `after` (falling back to `before`) when not supplied explicitly,
    /// matching Python's `after.get("id")`/`(after or before or {}).get("uuid")`.
    ///
    /// v1 only ever calls this with `action == "import"` (file import and
    /// snapshot import both reapply the full rule set) — see
    /// `ios/docs/spec.md` "Rule engine".
    @discardableResult
    public static func recordRuleChange(
        db: Database,
        action: String,
        before: String? = nil,
        after: String? = nil,
        ruleId: Int64? = nil,
        ruleUuid: String? = nil
    ) throws -> RuleChangeReportRecord {
        let changes = try applyRules(db: db)

        var resolvedRuleId = ruleId
        if resolvedRuleId == nil, let after, let dict = jsonObject(after), let idNumber = dict["id"] as? NSNumber {
            resolvedRuleId = idNumber.int64Value
        }

        var resolvedRuleUuid = ruleUuid
        if resolvedRuleUuid == nil {
            let source = after.flatMap(jsonObject) ?? before.flatMap(jsonObject)
            resolvedRuleUuid = source?["uuid"] as? String
        }

        var report = RuleChangeReportRecord(
            ruleId: resolvedRuleId,
            ruleUuid: resolvedRuleUuid,
            action: action,
            ruleBefore: before,
            ruleAfter: after,
            summary: "{\"changed\":\(changes.count)}"
        )
        try report.insert(db)
        let reportId = report.id!

        for change in changes {
            var item = RuleChangeItemRecord(
                reportId: reportId,
                transactionId: change.transactionId,
                oldCategory: change.oldCategory,
                newCategory: change.newCategory,
                oldTags: change.oldTags,
                newTags: change.newTags
            )
            try item.insert(db)
        }

        return report
    }
}
