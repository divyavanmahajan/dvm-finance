import Foundation
import GRDB

/// Port of `src/abn_combined/core/models.py: Budget`.
///
/// Schema-only in v1 — spec.md "Data model": "budgets (schema only in v1 —
/// imported/exported through snapshots, no UI)". `created_at`/`updated_at`
/// are `Date` (date-only) columns in the Python model
/// (`mapped_column(Date, ...)`, not `DateTime`), matched here for fidelity
/// even though it limits the audit timestamp to day granularity.
public struct BudgetRecord: Codable, Equatable, FetchableRecord, MutablePersistableRecord {
    public static let databaseTableName = "budgets"

    public var id: Int64?
    public var category: String
    public var amount: Decimal
    public var period: String
    public var startDate: Date?
    public var endDate: Date?
    public var notes: String?
    public var createdAt: Date?
    public var updatedAt: Date?

    enum CodingKeys: String, CodingKey {
        case id
        case category
        case amount
        case period
        case startDate = "start_date"
        case endDate = "end_date"
        case notes
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    public init(
        id: Int64? = nil,
        category: String,
        amount: Decimal,
        period: String,
        startDate: Date? = nil,
        endDate: Date? = nil,
        notes: String? = nil,
        createdAt: Date? = nil,
        updatedAt: Date? = nil
    ) {
        self.id = id
        self.category = category
        self.amount = amount
        self.period = period
        self.startDate = startDate
        self.endDate = endDate
        self.notes = notes
        self.createdAt = createdAt
        self.updatedAt = updatedAt
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
