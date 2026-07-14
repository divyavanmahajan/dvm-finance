import Foundation
import CoreFoundation
import GRDB

/// Port of `core/snapshots.py`'s errors, raised by `SnapshotCodec.read(_:)`.
///
/// Mirrors `read_snapshot`'s validation order and user-readable messages
/// exactly (`SnapshotError(ValueError)` in Python, with an f-string message
/// per case); the associated data differs slightly where Python interpolates
/// the *original exception* (`exc`) into the message — this port has no
/// underlying exception to quote (gzip/JSON failures surface as Swift enum
/// cases, not caught `Error` values with a message), so those two messages
/// are a fixed, still user-readable string instead.
public enum SnapshotError: Error, LocalizedError, Equatable {
    case corruptGzip
    case corruptJSON
    case missingHeader
    case schemaVersionMismatch(found: Int?)
    case missingSection(String)

    public var errorDescription: String? {
        switch self {
        case .corruptGzip:
            return "Not a valid snapshot file (corrupt gzip)."
        case .corruptJSON:
            return "Not a valid snapshot file (corrupt JSON)."
        case .missingHeader:
            return "Not a valid snapshot file (missing header)."
        case .schemaVersionMismatch(let found):
            let foundDescription = found.map(String.init) ?? "None"
            return "Schema version mismatch: snapshot has version \(foundDescription), "
                + "this app supports version \(SnapshotCodec.schemaVersion)."
        case .missingSection(let key):
            return "Not a valid snapshot file (missing '\(key)')."
        }
    }
}

// MARK: - Snapshot document model

/// Port of `core/snapshots.py:build_snapshot`'s `header` dict.
public struct SnapshotHeader: Codable, Equatable {
    public var schemaVersion: Int
    public var exportedAt: String
    public var machineId: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case exportedAt = "exported_at"
        case machineId = "machine_id"
    }

    public init(schemaVersion: Int, exportedAt: String, machineId: String) {
        self.schemaVersion = schemaVersion
        self.exportedAt = exportedAt
        self.machineId = machineId
    }
}

/// Port of `core/snapshots.py:_txn_dict`'s shape — every `transactions`
/// column, JSON-safe (dates as `yyyy-MM-dd` strings, `startsaldo`/
/// `endsaldo`/`amount` as decimal strings, everything else passed through).
/// Field order/names match `TransactionRecord.CodingKeys` (`Database/
/// TransactionRecord.swift`) so the two stay a plain 1:1 mapping.
public struct SnapshotTransaction: Codable, Equatable {
    public var id: String
    public var accountNumber: String
    public var mutationcode: String?
    public var transactiondate: String?
    public var valuedate: String?
    public var startsaldo: String?
    public var endsaldo: String?
    public var amount: String?
    public var description: String?
    public var descriptionStructured: String?
    public var category: String?
    public var manualCategory: String?
    public var tags: String?
    public var manualTags: String?
    public var categorizationSource: String?
    public var currency: String
    public var sourceFile: String?
    public var sourceLine: Int?
    public var transactionTypeCode: String?
    public var transactionReference: String?
    public var transactionHash: String?

    enum CodingKeys: String, CodingKey {
        case id
        case accountNumber
        case mutationcode
        case transactiondate
        case valuedate
        case startsaldo
        case endsaldo
        case amount
        case description
        case descriptionStructured = "description_structured"
        case category
        case manualCategory = "manual_category"
        case tags
        case manualTags = "manual_tags"
        case categorizationSource = "categorization_source"
        case currency
        case sourceFile = "source_file"
        case sourceLine = "source_line"
        case transactionTypeCode = "transaction_type_code"
        case transactionReference = "transaction_reference"
        case transactionHash = "transaction_hash"
    }
}

/// Port of `core/snapshots.py:_budget_dict`'s shape (no machine-local `id`).
public struct SnapshotBudget: Codable, Equatable {
    public var category: String
    /// Required (not tolerant-decoded like the rest of this struct):
    /// `core/snapshots.py`'s `_merge_budgets` always dereferences
    /// `data["amount"]` with no fallback, so a budget entry missing it is a
    /// malformed snapshot either way — Python raises `KeyError` deep in the
    /// merge; here, decoding the whole document fails up front instead (see
    /// `SnapshotCodec.read(_:)`'s doc comment on that trade-off).
    public var amount: String
    public var period: String
    public var startDate: String?
    public var endDate: String?
    public var notes: String?

    enum CodingKeys: String, CodingKey {
        case category
        case amount
        case period
        case startDate = "start_date"
        case endDate = "end_date"
        case notes
    }
}

/// Port of `core/snapshots.py:_report_dict`'s `items` entry shape.
public struct SnapshotReportItem: Codable, Equatable {
    public var transactionId: String
    public var oldCategory: String?
    public var newCategory: String?
    public var oldTags: String?
    public var newTags: String?

    enum CodingKeys: String, CodingKey {
        case transactionId = "transaction_id"
        case oldCategory = "old_category"
        case newCategory = "new_category"
        case oldTags = "old_tags"
        case newTags = "new_tags"
    }
}

/// Port of `core/snapshots.py:_report_dict`'s shape. `ruleBefore`/
/// `ruleAfter`/`summary` are arbitrary JSON (or absent/`null`) on the Python
/// side — see `JSONValue`'s doc comment. Every top-level field is optional
/// (tolerant decoding): a hand-edited or future-format snapshot missing one
/// of these keys should not make the whole file unreadable, only degrade
/// that one field to its Python-side `dict.get(...)` fallback in
/// `SnapshotImporter`.
public struct SnapshotReport: Codable, Equatable {
    public var createdAt: String?
    public var ruleId: Int64?
    public var ruleUuid: String?
    public var action: String?
    public var ruleBefore: JSONValue?
    public var ruleAfter: JSONValue?
    public var summary: JSONValue?
    public var items: [SnapshotReportItem]

    enum CodingKeys: String, CodingKey {
        case createdAt = "created_at"
        case ruleId = "rule_id"
        case ruleUuid = "rule_uuid"
        case action
        case ruleBefore = "rule_before"
        case ruleAfter = "rule_after"
        case summary
        case items
    }

    public init(
        createdAt: String?,
        ruleId: Int64?,
        ruleUuid: String?,
        action: String?,
        ruleBefore: JSONValue?,
        ruleAfter: JSONValue?,
        summary: JSONValue?,
        items: [SnapshotReportItem]
    ) {
        self.createdAt = createdAt
        self.ruleId = ruleId
        self.ruleUuid = ruleUuid
        self.action = action
        self.ruleBefore = ruleBefore
        self.ruleAfter = ruleAfter
        self.summary = summary
        self.items = items
    }
}

/// Port of `core/snapshots.py:build_snapshot`'s full payload shape —
/// `{header, transactions, rules, budgets, rule_change_reports}`. `rules`
/// reuses `Categorizer.RuleSnapshot`/`RuleConditionSnapshot` (Phase B,
/// `Core/Categorizer.swift`) rather than redefining an equivalent type, per
/// `ios/docs/plan.md` "Phase C": "REUSE them for the rules section".
public struct SnapshotDocument: Codable, Equatable {
    public var header: SnapshotHeader
    public var transactions: [SnapshotTransaction]
    public var rules: [Categorizer.RuleSnapshot]
    public var budgets: [SnapshotBudget]
    public var ruleChangeReports: [SnapshotReport]

    enum CodingKeys: String, CodingKey {
        case header
        case transactions
        case rules
        case budgets
        case ruleChangeReports = "rule_change_reports"
    }

    public init(
        header: SnapshotHeader,
        transactions: [SnapshotTransaction],
        rules: [Categorizer.RuleSnapshot],
        budgets: [SnapshotBudget],
        ruleChangeReports: [SnapshotReport]
    ) {
        self.header = header
        self.transactions = transactions
        self.rules = rules
        self.budgets = budgets
        self.ruleChangeReports = ruleChangeReports
    }
}

// MARK: - Codec

/// Port of `core/snapshots.py`'s module-level constants + `read_snapshot`/
/// `build_snapshot` + the serialization helpers (`_json_safe`/`_txn_dict`/
/// `_budget_dict`/`_report_dict`).
public enum SnapshotCodec {
    public static let schemaVersion = 1
    public static let snapshotSuffix = ".json.gz"

    /// `_ENTITY_KEYS` from `core/snapshots.py` — the four sections
    /// `read_snapshot` requires to be present and list-typed.
    static let entityKeys = ["transactions", "rules", "budgets", "rule_change_reports"]

    // MARK: Date/decimal rendering shared by build() and SnapshotImporter

    /// Renders `exported_at`/`rule_change_reports.created_at` the way
    /// Python's naive (timezone-less) `datetime.isoformat()` does at second
    /// precision: `"yyyy-MM-dd'T'HH:mm:ss"`. Reuses `DatabaseDateFormat`'s
    /// POSIX-locale, fixed-timezone construction (the same convention every
    /// other `DateTime` column in this codebase already follows —
    /// `Database/DatabaseDateFormat.swift`) rather than the device's current
    /// time zone, so a snapshot's timestamps — and the identity comparisons
    /// `SnapshotImporter` builds from them — never depend on the running
    /// device's locale/time zone.
    static let dateTimeFormatter = DatabaseDateFormat.dateTime

    /// Fallback parser for a `created_at` value that carries microseconds
    /// (real desktop rows can: SQLAlchemy's SQLite `DateTime` type preserves
    /// them) — `dateTimeFormatter` alone cannot parse a fractional-seconds
    /// suffix.
    static let dateTimeMicrosecondsFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
        return formatter
    }()

    /// Parses a snapshot `created_at`/`exported_at` string, trying the
    /// plain-seconds format first and falling back to the
    /// microseconds-suffixed one.
    static func parseDateTime(_ value: String) -> Date? {
        dateTimeFormatter.date(from: value) ?? dateTimeMicrosecondsFormatter.date(from: value)
    }

    /// Renders a `Date` back to the plain-seconds snapshot string form —
    /// used both to build `exported_at` and, in `SnapshotImporter`, to
    /// render a local `rule_change_reports.created_at` (or a parsed
    /// incoming one) into the identity-comparison string. Both sides always
    /// go through this one formatter, so a microsecond-carrying incoming
    /// value and its second-precision locally-stored counterpart compare
    /// equal — see `SnapshotImporter.swift`'s `mergeReports`.
    static func renderDateTime(_ date: Date) -> String {
        dateTimeFormatter.string(from: date)
    }

    /// Human-facing timestamp (device local time) used for snapshot export
    /// filenames (`SnapshotExporter`) and SQLite backup filenames
    /// (`SnapshotImporter`). Deliberately distinct from `dateTimeFormatter`
    /// above: a filename is never compared for merge identity, so there is
    /// no correctness reason to pin it away from the device's actual clock
    /// the way `created_at`/`exported_at` are — matches Python's
    /// `datetime.now().strftime(...)` (device local time) used for both
    /// `export_snapshot`'s and `_backup_db`'s filename stamps.
    static let localFilenameStampFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone.current
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        return formatter
    }()

    /// Port of `_json_safe`'s `Decimal` branch (`str(value)`), rendered to
    /// **exactly two decimal places** — desktop's columns are
    /// `Numeric(15, 2)`/`Numeric(10, 2)`, so every amount/saldo/budget value
    /// round-trips through 2-decimal precision; `NSDecimalNumber` is
    /// formatted explicitly (its own `.stringValue` does *not* pad/round to
    /// a fixed scale — `Decimal(12)` renders as `"12"`, not `"12.00"`).
    static func decimalString(_ value: Decimal) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.usesGroupingSeparator = false
        formatter.minimumFractionDigits = 2
        formatter.maximumFractionDigits = 2
        formatter.minimumIntegerDigits = 1
        return formatter.string(from: NSDecimalNumber(decimal: value)) ?? NSDecimalNumber(decimal: value).stringValue
    }

    enum DecimalParseError: Error {
        case invalid(String)
    }

    /// Port of `Decimal(str(value))` (`_txn_from_data`/`_merge_budgets`).
    static func parseDecimal(_ value: String) throws -> Decimal {
        guard let decimal = Decimal(string: value, locale: Locale(identifier: "en_US_POSIX")) else {
            throw DecimalParseError.invalid(value)
        }
        return decimal
    }

    // MARK: Transaction <-> SnapshotTransaction

    /// Port of `core/snapshots.py:_txn_dict`.
    public static func makeSnapshotTransaction(_ record: TransactionRecord) -> SnapshotTransaction {
        SnapshotTransaction(
            id: record.id,
            accountNumber: record.accountNumber,
            mutationcode: record.mutationcode,
            transactiondate: DatabaseDateFormat.dateOnly.string(from: record.transactiondate),
            valuedate: record.valuedate.map { DatabaseDateFormat.dateOnly.string(from: $0) },
            startsaldo: record.startsaldo.map(decimalString),
            endsaldo: record.endsaldo.map(decimalString),
            amount: decimalString(record.amount),
            description: record.description,
            descriptionStructured: record.descriptionStructured,
            category: record.category,
            manualCategory: record.manualCategory,
            tags: record.tags,
            manualTags: record.manualTags,
            categorizationSource: record.categorizationSource,
            currency: record.currency,
            sourceFile: record.sourceFile,
            sourceLine: record.sourceLine,
            transactionTypeCode: record.transactionTypeCode,
            transactionReference: record.transactionReference,
            transactionHash: record.transactionHash
        )
    }

    enum TransactionDecodeError: Error {
        case missingTransactionDate
        case missingAmount
    }

    /// Port of `core/snapshots.py:_txn_from_data`.
    public static func makeTransactionRecord(_ snapshot: SnapshotTransaction) throws -> TransactionRecord {
        guard let transactiondateString = snapshot.transactiondate,
              let transactiondate = DatabaseDateFormat.dateOnly.date(from: transactiondateString)
        else {
            throw TransactionDecodeError.missingTransactionDate
        }
        guard let amountString = snapshot.amount else {
            throw TransactionDecodeError.missingAmount
        }
        return TransactionRecord(
            id: snapshot.id,
            accountNumber: snapshot.accountNumber,
            mutationcode: snapshot.mutationcode,
            transactiondate: transactiondate,
            valuedate: snapshot.valuedate.flatMap { DatabaseDateFormat.dateOnly.date(from: $0) },
            startsaldo: try snapshot.startsaldo.map(parseDecimal),
            endsaldo: try snapshot.endsaldo.map(parseDecimal),
            amount: try parseDecimal(amountString),
            description: snapshot.description,
            descriptionStructured: snapshot.descriptionStructured,
            category: snapshot.category,
            manualCategory: snapshot.manualCategory,
            tags: snapshot.tags,
            manualTags: snapshot.manualTags,
            categorizationSource: snapshot.categorizationSource,
            currency: snapshot.currency,
            sourceFile: snapshot.sourceFile,
            sourceLine: snapshot.sourceLine,
            transactionTypeCode: snapshot.transactionTypeCode,
            transactionReference: snapshot.transactionReference,
            transactionHash: snapshot.transactionHash
        )
    }

    // MARK: Budget <-> SnapshotBudget

    /// Port of `core/snapshots.py:_budget_dict`.
    public static func makeSnapshotBudget(_ record: BudgetRecord) -> SnapshotBudget {
        SnapshotBudget(
            category: record.category,
            amount: decimalString(record.amount),
            period: record.period,
            startDate: record.startDate.map { DatabaseDateFormat.dateOnly.string(from: $0) },
            endDate: record.endDate.map { DatabaseDateFormat.dateOnly.string(from: $0) },
            notes: record.notes
        )
    }

    // MARK: RuleChangeReport <-> SnapshotReport

    /// Port of `core/snapshots.py:_report_dict`. `rule_before`/`rule_after`/
    /// `summary` are stored locally as JSON `TEXT`; exporting re-parses them
    /// into `JSONValue` objects rather than embedding the already-serialized
    /// string, matching the "IMPORTANT JSON fidelity" note in `ios/docs/
    /// plan.md` "Phase C" (no double-encoding).
    public static func makeSnapshotReport(
        _ report: RuleChangeReportRecord,
        items: [RuleChangeItemRecord]
    ) -> SnapshotReport {
        SnapshotReport(
            createdAt: renderDateTime(report.createdAt),
            ruleId: report.ruleId,
            ruleUuid: report.ruleUuid,
            action: report.action,
            ruleBefore: parseStoredJSON(report.ruleBefore),
            ruleAfter: parseStoredJSON(report.ruleAfter),
            summary: parseStoredJSON(report.summary),
            items: items.map {
                SnapshotReportItem(
                    transactionId: $0.transactionId,
                    oldCategory: $0.oldCategory,
                    newCategory: $0.newCategory,
                    oldTags: $0.oldTags,
                    newTags: $0.newTags
                )
            }
        )
    }

    /// Parses a JSON `TEXT` column (`rule_before`/`rule_after`/`summary`/
    /// `counts`/`overwrites`) into a `JSONValue`, or `nil` for a `NULL`
    /// column / unparseable text.
    static func parseStoredJSON(_ text: String?) -> JSONValue? {
        guard let text, let data = text.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode(JSONValue.self, from: data)
    }

    /// Serializes a `JSONValue` back to the compact JSON text a `TEXT`
    /// column stores.
    static func jsonColumnString(_ value: JSONValue?) -> String? {
        guard let value else { return nil }
        guard let data = try? JSONEncoder().encode(value) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    // MARK: Comparable objects (for SnapshotImporter's diff)
    //
    // These build a `[String: JSONValue]` "comparable object" per entity —
    // the Swift analog of the plain `dict`s Python hands to `_diff`
    // (`_txn_dict`/`rule_snapshot`/`_budget_dict`). They are hand-written
    // field-by-field, **not** a generic `JSONEncoder`-round-trip over the
    // `Encodable` struct: Swift's synthesized `encode(to:)` for an
    // `Optional` stored property calls `encodeIfPresent`, which *omits* the
    // key entirely for `nil` rather than writing `null` — unlike Python,
    // whose dicts always carry every key (with `None` as the sentinel for
    // "no value"). `SnapshotImporter.diff(local:incoming:)` iterates only
    // over `incoming`'s keys (matching Python's `for key in incoming`), so
    // a key silently missing from `incoming` because its value happened to
    // be `nil` would make a real "local had a value, incoming cleared it"
    // change invisible in the reported `fields` diff. Explicit `.from(_:)`
    // calls below guarantee every field key is always present.

    /// Port of `core/categorizer.py:rule_snapshot`'s dict shape, **minus**
    /// `id` — `_merge_rules` always compares/diffs rules with `id` excluded
    /// (`{k: v for k, v in data.items() if k != "id"}`), since rule ids are
    /// machine-local and never meaningfully equal/comparable across devices.
    static func comparableObject(_ snapshot: Categorizer.RuleSnapshot) -> [String: JSONValue] {
        [
            "uuid": .string(snapshot.uuid),
            "priority": .int(Int64(snapshot.priority)),
            "rule_type": .string(snapshot.ruleType),
            "match_pattern": .string(snapshot.matchPattern),
            "field_target": .from(snapshot.fieldTarget),
            "match_value": .string(snapshot.matchValue),
            "category": .from(snapshot.category),
            "tags": .from(snapshot.tags),
            "is_active": .bool(snapshot.isActive),
            "is_tag_only": .bool(snapshot.isTagOnly),
            "notes": .from(snapshot.notes),
            "filter_account": .from(snapshot.filterAccount),
            "filter_currency": .from(snapshot.filterCurrency),
            "filter_date_from": .from(snapshot.filterDateFrom),
            "filter_date_to": .from(snapshot.filterDateTo),
            "conditions": .array(snapshot.conditions.map(comparableObject)),
        ]
    }

    private static func comparableObject(_ condition: Categorizer.RuleConditionSnapshot) -> JSONValue {
        .object([
            "field_target": .string(condition.fieldTarget),
            "match_pattern": .string(condition.matchPattern),
            "match_value": .string(condition.matchValue),
            "operator": .string(condition.operatorValue),
            "sort_order": .int(Int64(condition.sortOrder)),
        ])
    }

    /// Port of `core/snapshots.py:_txn_dict`'s shape as a comparable object
    /// (includes `id` — always equal since both sides are looked up by the
    /// same id, so it never actually appears in a diff, but kept for
    /// fidelity with Python's full-column dict).
    static func comparableObject(_ snapshot: SnapshotTransaction) -> [String: JSONValue] {
        [
            "id": .string(snapshot.id),
            "accountNumber": .string(snapshot.accountNumber),
            "mutationcode": .from(snapshot.mutationcode),
            "transactiondate": .from(snapshot.transactiondate),
            "valuedate": .from(snapshot.valuedate),
            "startsaldo": .from(snapshot.startsaldo),
            "endsaldo": .from(snapshot.endsaldo),
            "amount": .from(snapshot.amount),
            "description": .from(snapshot.description),
            "description_structured": .from(snapshot.descriptionStructured),
            "category": .from(snapshot.category),
            "manual_category": .from(snapshot.manualCategory),
            "tags": .from(snapshot.tags),
            "manual_tags": .from(snapshot.manualTags),
            "categorization_source": .from(snapshot.categorizationSource),
            "currency": .string(snapshot.currency),
            "source_file": .from(snapshot.sourceFile),
            "source_line": .from(snapshot.sourceLine),
            "transaction_type_code": .from(snapshot.transactionTypeCode),
            "transaction_reference": .from(snapshot.transactionReference),
            "transaction_hash": .from(snapshot.transactionHash),
        ]
    }

    /// Port of `core/snapshots.py:_budget_dict`'s shape as a comparable object.
    static func comparableObject(_ snapshot: SnapshotBudget) -> [String: JSONValue] {
        [
            "category": .string(snapshot.category),
            "amount": .string(snapshot.amount),
            "period": .string(snapshot.period),
            "start_date": .from(snapshot.startDate),
            "end_date": .from(snapshot.endDate),
            "notes": .from(snapshot.notes),
        ]
    }

    // MARK: - build_snapshot

    /// Port of `core/snapshots.py:build_snapshot`. Transactions ordered by
    /// `id asc`, rules by `uuid asc`, budgets by `id asc`, reports by
    /// `created_at asc, id asc` — the same orderings the Python query uses.
    public static func build(db: Database, machineId: String) throws -> SnapshotDocument {
        let header = SnapshotHeader(
            schemaVersion: schemaVersion,
            exportedAt: renderDateTime(Date()),
            machineId: machineId
        )

        let transactions = try TransactionRecord
            .order(Column("id").asc)
            .fetchAll(db)
            .map(makeSnapshotTransaction)

        let ruleRecords = try CategorizationRuleRecord
            .order(Column("uuid").asc)
            .fetchAll(db)
        let rules = try ruleRecords.map { rule -> Categorizer.RuleSnapshot in
            let conditions = try RuleConditionRecord
                .filter(Column("rule_id") == rule.id)
                .order(Column("sort_order").asc)
                .fetchAll(db)
            return Categorizer.makeRuleSnapshot(rule: rule, conditions: conditions)
        }

        let budgets = try BudgetRecord
            .order(Column("id").asc)
            .fetchAll(db)
            .map(makeSnapshotBudget)

        let reportRecords = try RuleChangeReportRecord
            .order(Column("created_at").asc, Column("id").asc)
            .fetchAll(db)
        let reports = try reportRecords.map { report -> SnapshotReport in
            let items = try RuleChangeItemRecord
                .filter(Column("report_id") == report.id)
                .fetchAll(db)
            return makeSnapshotReport(report, items: items)
        }

        return SnapshotDocument(
            header: header,
            transactions: transactions,
            rules: rules,
            budgets: budgets,
            ruleChangeReports: reports
        )
    }

    /// Encodes a `SnapshotDocument` to JSON, then gzips it — the write half
    /// of `core/snapshots.py:export_snapshot`.
    public static func write(_ document: SnapshotDocument) throws -> Data {
        let json = try JSONEncoder().encode(document)
        return try Gzip.compress(json)
    }

    // MARK: - read_snapshot

    /// Port of `core/snapshots.py:read_snapshot`. Validation order matches
    /// the Python function exactly: corrupt gzip, then corrupt JSON, then
    /// missing/non-dict header, then schema-version mismatch, then each of
    /// the four entity keys missing or non-array — every check short-circuits
    /// on the first failure, same as Python's sequential `if`/`raise`s.
    public static func read(_ blob: Data) throws -> SnapshotDocument {
        let raw: Data
        do {
            raw = try Gzip.decompress(blob)
        } catch {
            throw SnapshotError.corruptGzip
        }

        let topLevel: Any
        do {
            topLevel = try JSONSerialization.jsonObject(with: raw, options: [.fragmentsAllowed])
        } catch {
            throw SnapshotError.corruptJSON
        }

        guard let payload = topLevel as? [String: Any] else {
            throw SnapshotError.missingHeader
        }
        guard let header = payload["header"] as? [String: Any] else {
            throw SnapshotError.missingHeader
        }

        let foundVersion = integerSchemaVersion(header["schema_version"])
        guard foundVersion == schemaVersion else {
            throw SnapshotError.schemaVersionMismatch(found: foundVersion)
        }

        for key in entityKeys {
            guard payload[key] is [Any] else {
                throw SnapshotError.missingSection(key)
            }
        }

        // The coarse checks above passed; decode the full typed document
        // from the same bytes. A well-formed export always succeeds here —
        // unlike Python (which has no static shape to fail against and
        // would instead raise a raw `KeyError`/`TypeError` deep inside the
        // merge functions for a structurally-malformed-but-list-shaped
        // section), a Swift `DecodingError` surfaces immediately and
        // precisely instead. This is intentionally *not* wrapped into a
        // `SnapshotError` case: it indicates a snapshot that passed the
        // coarse shape check but violates the fixed per-entity schema
        // (e.g. a rule missing `match_value`), which is a different failure
        // mode than "not a snapshot file at all".
        return try JSONDecoder().decode(SnapshotDocument.self, from: raw)
    }

    /// `header["schema_version"]` as an `Int`, or `nil` if absent, not a
    /// number, or a JSON boolean (`NSNumber` bridges `true`/`false` to a
    /// numeric type that would otherwise satisfy `as? NSNumber`).
    private static func integerSchemaVersion(_ raw: Any?) -> Int? {
        guard let number = raw as? NSNumber else { return nil }
        if CFGetTypeID(number) == CFBooleanGetTypeID() { return nil }
        return number.intValue
    }
}
