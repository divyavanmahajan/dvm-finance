import Foundation
import GRDB

/// Port of `src/abn_combined/core/models.py: RuleChangeReport`.
///
/// Audit record for a rule mutation or a recategorization/import run;
/// `core/categorizer.py:record_rule_change` (ported in Phase B) is the only
/// writer. v1 only ever persists `action == "import"` (file import and
/// snapshot import both go through the two-pass rule engine); the six-case
/// `RULE_CHANGE_ACTIONS` enum is carried here for schema parity with
/// desktop, matching `CLAUDE.md`'s "every rule mutation goes through
/// `record_rule_change`" rule.
///
/// `rule_before`/`rule_after`/`summary` are JSON columns on the Python side
/// (SQLAlchemy `JSON`, itself stored as SQLite `TEXT`); stored here as raw
/// JSON `String?` with `Dictionary`-typed computed accessors below.
public struct RuleChangeReportRecord: Codable, Equatable, FetchableRecord, MutablePersistableRecord {
    public static let databaseTableName = "rule_change_reports"

    public var id: Int64?
    public var createdAt: Date
    public var ruleId: Int64?
    public var ruleUuid: String?
    public var action: String
    public var ruleBefore: String?
    public var ruleAfter: String?
    public var summary: String?

    enum CodingKeys: String, CodingKey {
        case id
        case createdAt = "created_at"
        case ruleId = "rule_id"
        case ruleUuid = "rule_uuid"
        case action
        case ruleBefore = "rule_before"
        case ruleAfter = "rule_after"
        case summary
    }

    public init(
        id: Int64? = nil,
        createdAt: Date = Date(),
        ruleId: Int64? = nil,
        ruleUuid: String? = nil,
        action: String,
        ruleBefore: String? = nil,
        ruleAfter: String? = nil,
        summary: String? = nil
    ) {
        self.id = id
        self.createdAt = createdAt
        self.ruleId = ruleId
        self.ruleUuid = ruleUuid
        self.action = action
        self.ruleBefore = ruleBefore
        self.ruleAfter = ruleAfter
        self.summary = summary
    }

    public static var databaseDateDecodingStrategy: DatabaseDateDecodingStrategy {
        .formatted(DatabaseDateFormat.dateTime)
    }

    public static var databaseDateEncodingStrategy: DatabaseDateEncodingStrategy {
        .formatted(DatabaseDateFormat.dateTime)
    }

    public mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }

    /// `RULE_CHANGE_ACTIONS` from `core/models.py`. v1 only ever writes
    /// `.import`; the rest exist for schema parity with desktop.
    public enum Action: String, CaseIterable {
        case create, update, delete, toggle, recategorize
        case `import`
    }

    private static func decodeJSONDictionary(_ text: String?) -> [String: Any]? {
        guard let text, let data = text.data(using: .utf8) else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }

    private static func encodeJSONDictionary(_ dictionary: [String: Any]?) -> String? {
        guard let dictionary,
              JSONSerialization.isValidJSONObject(dictionary),
              let data = try? JSONSerialization.data(withJSONObject: dictionary)
        else { return nil }
        return String(data: data, encoding: .utf8)
    }

    public var ruleBeforeDictionary: [String: Any]? {
        get { Self.decodeJSONDictionary(ruleBefore) }
        set { ruleBefore = Self.encodeJSONDictionary(newValue) }
    }

    public var ruleAfterDictionary: [String: Any]? {
        get { Self.decodeJSONDictionary(ruleAfter) }
        set { ruleAfter = Self.encodeJSONDictionary(newValue) }
    }

    public var summaryDictionary: [String: Any]? {
        get { Self.decodeJSONDictionary(summary) }
        set { summary = Self.encodeJSONDictionary(newValue) }
    }
}
