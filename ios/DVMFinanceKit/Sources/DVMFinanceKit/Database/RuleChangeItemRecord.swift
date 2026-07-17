import Foundation
import GRDB

/// Port of `src/abn_combined/core/models.py: RuleChangeItem`.
///
/// Per-transaction before/after diff belonging to a `RuleChangeReportRecord`.
/// `report_id` cascades on delete when the owning report is deleted
/// (`AppDatabase` migration `v1`).
public struct RuleChangeItemRecord: Codable, Equatable, FetchableRecord, MutablePersistableRecord {
    public static let databaseTableName = "rule_change_items"

    public var id: Int64?
    public var reportId: Int64
    public var transactionId: String
    public var oldCategory: String?
    public var newCategory: String?
    public var oldTags: String?
    public var newTags: String?

    enum CodingKeys: String, CodingKey {
        case id
        case reportId = "report_id"
        case transactionId = "transaction_id"
        case oldCategory = "old_category"
        case newCategory = "new_category"
        case oldTags = "old_tags"
        case newTags = "new_tags"
    }

    public init(
        id: Int64? = nil,
        reportId: Int64,
        transactionId: String,
        oldCategory: String? = nil,
        newCategory: String? = nil,
        oldTags: String? = nil,
        newTags: String? = nil
    ) {
        self.id = id
        self.reportId = reportId
        self.transactionId = transactionId
        self.oldCategory = oldCategory
        self.newCategory = newCategory
        self.oldTags = oldTags
        self.newTags = newTags
    }

    public mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }
}
