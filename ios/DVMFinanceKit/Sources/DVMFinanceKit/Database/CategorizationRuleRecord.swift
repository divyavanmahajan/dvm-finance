import Foundation
import GRDB

/// Port of `src/abn_combined/core/models.py: CategorizationRule`.
///
/// `uuid` is the cross-machine identity used by the snapshot codec (Phase C)
/// to remap `transactions.categorization_source`; `id` is a machine-local
/// autoincrement rowid captured via `didInsert(_:)`, hence
/// `MutablePersistableRecord` rather than plain `PersistableRecord`.
///
/// `is_tag_only` (v1.1.0+ on desktop) marks a rule as tags-only (no
/// `category`) — see `CLAUDE.md` "Tag-only rules" and
/// `core/categorizer.py:apply_rules`'s two-pass engine (ported in Phase B).
///
/// The four `filter_*` columns are context filters: all optional, `NULL`
/// meaning "no restriction" (account exact match, currency exact match,
/// date range inclusive).
public struct CategorizationRuleRecord: Codable, Equatable, FetchableRecord, MutablePersistableRecord {
    public static let databaseTableName = "categorization_rules"

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
    public var filterDateFrom: Date?
    public var filterDateTo: Date?

    enum CodingKeys: String, CodingKey {
        case id
        case uuid
        case priority
        case ruleType = "rule_type"
        case matchPattern = "match_pattern"
        case fieldTarget = "field_target"
        case matchValue = "match_value"
        case category
        case tags
        case isActive = "is_active"
        case isTagOnly = "is_tag_only"
        case notes
        case filterAccount = "filter_account"
        case filterCurrency = "filter_currency"
        case filterDateFrom = "filter_date_from"
        case filterDateTo = "filter_date_to"
    }

    public init(
        id: Int64? = nil,
        uuid: String = UUID().uuidString,
        priority: Int = 100,
        ruleType: String,
        matchPattern: String,
        fieldTarget: String? = nil,
        matchValue: String,
        category: String? = nil,
        tags: String? = nil,
        isActive: Bool = true,
        isTagOnly: Bool = false,
        notes: String? = nil,
        filterAccount: String? = nil,
        filterCurrency: String? = nil,
        filterDateFrom: Date? = nil,
        filterDateTo: Date? = nil
    ) {
        self.id = id
        self.uuid = uuid
        self.priority = priority
        self.ruleType = ruleType
        self.matchPattern = matchPattern
        self.fieldTarget = fieldTarget
        self.matchValue = matchValue
        self.category = category
        self.tags = tags
        self.isActive = isActive
        self.isTagOnly = isTagOnly
        self.notes = notes
        self.filterAccount = filterAccount
        self.filterCurrency = filterCurrency
        self.filterDateFrom = filterDateFrom
        self.filterDateTo = filterDateTo
    }

    public static var databaseDateDecodingStrategy: DatabaseDateDecodingStrategy {
        .formatted(DatabaseDateFormat.dateOnly)
    }

    public static var databaseDateEncodingStrategy: DatabaseDateEncodingStrategy {
        .formatted(DatabaseDateFormat.dateOnly)
    }

    public mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }
}
