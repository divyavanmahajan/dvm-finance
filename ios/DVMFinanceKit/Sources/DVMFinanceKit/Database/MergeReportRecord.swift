import Foundation
import GRDB

/// Port of the Python model `core/models.py:MergeReport`.
///
/// The row holds each group that a merge folded and each group that it refused.
/// The carried manual categorization is not recoverable from the transaction
/// table, so the report keeps it.
public struct MergeReportRecord: Codable, FetchableRecord, MutablePersistableRecord {
    public static let databaseTableName = "merge_reports"

    public var id: Int64?
    /// An ISO-8601 second-precision string, like `updatedAt` on
    /// `TransactionRecord` and for the same reason: the record-wide
    /// `databaseDateDecodingStrategy` is pinned to date-only.
    public var createdAt: String
    /// The merged groups, as a JSON array string. The shape matches
    /// `core/merge.py:MergeGroup.as_dict`.
    public var groups: String?
    /// The refused groups, as a JSON array string. The shape matches
    /// `core/merge.py:RefusedGroup.as_dict`.
    public var refused: String?
    /// The counts, as a JSON object string.
    public var summary: String?

    enum CodingKeys: String, CodingKey {
        case id
        case createdAt = "created_at"
        case groups
        case refused
        case summary
    }

    public init(
        id: Int64? = nil,
        createdAt: String,
        groups: String? = nil,
        refused: String? = nil,
        summary: String? = nil
    ) {
        self.id = id
        self.createdAt = createdAt
        self.groups = groups
        self.refused = refused
        self.summary = summary
    }

    public mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }
}
