import Foundation
import GRDB

/// Port of `src/abn_combined/core/models.py: ExportState` plus the
/// `get_export_state`/`get_last_delta_export_at` accessors in
/// `core/snapshots.py`.
///
/// Single-row marker table (id=1) tracking the last successful delta export.
/// `lastDeltaExportAt` is the `since` boundary the delta-export UI defaults to,
/// so a delta covers "everything changed since the previous delta export"
/// without the user having to remember or re-run a full export first.
///
/// Stored as a `Date` mapped to the `.datetime` column via the record-wide
/// `databaseDateDecodingStrategy`/`EncodingStrategy` pinned to
/// `DatabaseDateFormat.dateTime` — the same convention every other `DateTime`
/// column follows (`SnapshotImportRecord`, `RuleChangeReportRecord`).
public struct ExportStateRecord: Codable, Equatable, FetchableRecord, MutablePersistableRecord {
    public static let databaseTableName = "export_state"

    public var id: Int64?
    public var lastDeltaExportAt: Date?

    enum CodingKeys: String, CodingKey {
        case id
        case lastDeltaExportAt = "last_delta_export_at"
    }

    public init(id: Int64? = nil, lastDeltaExportAt: Date? = nil) {
        self.id = id
        self.lastDeltaExportAt = lastDeltaExportAt
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

    // MARK: - Accessors (port of core/snapshots.py)

    /// Port of `core/snapshots.py:get_export_state`: return the single
    /// `export_state` row, creating it (id=1) if absent.
    static func getOrCreate(_ db: Database) throws -> ExportStateRecord {
        if let existing = try ExportStateRecord.order(Column("id").asc).fetchOne(db) {
            return existing
        }
        var state = ExportStateRecord()
        try state.insert(db)
        return state
    }

    /// Port of `core/snapshots.py:get_last_delta_export_at`: the `since`
    /// boundary the delta-export UI defaults to, or `nil` if no delta has
    /// been exported yet.
    public static func getLastDeltaExportAt(_ db: Database) throws -> Date? {
        try ExportStateRecord.order(Column("id").asc).fetchOne(db)?.lastDeltaExportAt
    }

    /// Advances the marker to `date`, mirroring `export_snapshot`'s
    /// `state.last_delta_export_at = export_started_at`. Creates the row if
    /// absent, then updates it in place.
    static func setLastDeltaExportAt(_ db: Database, _ date: Date) throws {
        var state = try getOrCreate(db)
        state.lastDeltaExportAt = date
        try state.update(db)
    }
}
