import Foundation
import GRDB

/// Port of `src/abn_combined/core/models.py: SnapshotImport`.
///
/// Report for a snapshot import (incoming-wins merge), written once per
/// import by the Phase C `SnapshotImporter`. `counts`/`overwrites` are JSON
/// columns on the Python side, stored here as raw JSON `String?` with
/// `Dictionary`-typed computed accessors, matching
/// `RuleChangeReportRecord`'s convention.
public struct SnapshotImportRecord: Codable, Equatable, FetchableRecord, MutablePersistableRecord {
    public static let databaseTableName = "snapshot_imports"

    public var id: Int64?
    public var createdAt: Date
    public var sourceMachineId: String?
    public var schemaVersion: Int?
    public var counts: String?
    public var overwrites: String?
    /// Delta-snapshot provenance, read from the imported file's header
    /// (`SnapshotHeader.delta`/`since`): `isDelta` is `true` and `deltaSince`
    /// carries the `since` boundary when the imported file was a delta/partial
    /// snapshot. Port of `core/models.py: SnapshotImport.is_delta`/
    /// `delta_since` (columns added by the `v2` migration).
    public var isDelta: Bool
    public var deltaSince: Date?

    enum CodingKeys: String, CodingKey {
        case id
        case createdAt = "created_at"
        case sourceMachineId = "source_machine_id"
        case schemaVersion = "schema_version"
        case counts
        case overwrites
        case isDelta = "is_delta"
        case deltaSince = "delta_since"
    }

    public init(
        id: Int64? = nil,
        createdAt: Date = Date(),
        sourceMachineId: String? = nil,
        schemaVersion: Int? = nil,
        counts: String? = nil,
        overwrites: String? = nil,
        isDelta: Bool = false,
        deltaSince: Date? = nil
    ) {
        self.id = id
        self.createdAt = createdAt
        self.sourceMachineId = sourceMachineId
        self.schemaVersion = schemaVersion
        self.counts = counts
        self.overwrites = overwrites
        self.isDelta = isDelta
        self.deltaSince = deltaSince
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

    public var countsDictionary: [String: Any]? {
        get { Self.decodeJSONDictionary(counts) }
        set { counts = Self.encodeJSONDictionary(newValue) }
    }

    public var overwritesDictionary: [String: Any]? {
        get { Self.decodeJSONDictionary(overwrites) }
        set { overwrites = Self.encodeJSONDictionary(newValue) }
    }
}
