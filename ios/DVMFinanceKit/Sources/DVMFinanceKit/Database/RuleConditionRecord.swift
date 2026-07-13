import Foundation
import GRDB

/// Port of `src/abn_combined/core/models.py: RuleCondition`.
///
/// An additional AND/OR condition folded onto a rule's primary match — see
/// `core/categorizer.py:_apply_rule_to_transaction`'s sequential left-fold,
/// ported in Phase B. `rule_id` cascades on delete when the owning
/// `CategorizationRuleRecord` is deleted (`AppDatabase` migration `v1`).
public struct RuleConditionRecord: Codable, Equatable, FetchableRecord, MutablePersistableRecord {
    public static let databaseTableName = "rule_conditions"

    public var id: Int64?
    public var ruleId: Int64
    public var fieldTarget: String
    public var matchPattern: String
    public var matchValue: String
    /// "AND" or "OR" — kept as a plain string to mirror the Python column
    /// exactly (`String(3)`, default `"AND"`); named `operatorValue` because
    /// `operator` is a Swift keyword.
    public var operatorValue: String
    public var sortOrder: Int

    enum CodingKeys: String, CodingKey {
        case id
        case ruleId = "rule_id"
        case fieldTarget = "field_target"
        case matchPattern = "match_pattern"
        case matchValue = "match_value"
        case operatorValue = "operator"
        case sortOrder = "sort_order"
    }

    public init(
        id: Int64? = nil,
        ruleId: Int64,
        fieldTarget: String,
        matchPattern: String,
        matchValue: String,
        operatorValue: String = "AND",
        sortOrder: Int = 0
    ) {
        self.id = id
        self.ruleId = ruleId
        self.fieldTarget = fieldTarget
        self.matchPattern = matchPattern
        self.matchValue = matchValue
        self.operatorValue = operatorValue
        self.sortOrder = sortOrder
    }

    public mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }
}
