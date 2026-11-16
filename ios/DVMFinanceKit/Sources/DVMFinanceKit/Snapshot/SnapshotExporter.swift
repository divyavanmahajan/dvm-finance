import Foundation
import GRDB

/// Port of `core/snapshots.py:export_snapshot` (+ `list_exports`, not needed
/// in v1 — the "Import" screen's export history list reads
/// `snapshot_imports` rows directly, not the filesystem; see `ios/docs/
/// spec.md` "UI").
public enum SnapshotExporter {
    private static let subdirectoryName = "snapshots"

    /// The reasons the exporter refuses an export. Each case carries a
    /// message for the user.
    public enum ExportError: Error, LocalizedError, Equatable {
        /// The database holds the fictional rows of `SampleDataset`. The
        /// exporter refuses the export, so that these rows never reach the
        /// desktop database.
        case sampleDataPresent

        public var errorDescription: String? {
            switch self {
            case .sampleDataPresent:
                return "The app holds sample data. Remove the sample data in the Help tab, then export again."
            }
        }
    }

    /// Builds the full dataset snapshot and writes it, gzipped, to
    /// `<dataDirectory>/snapshots/snapshot-<stamp>.json.gz`, deduping with a
    /// `-1`, `-2`, ... suffix exactly like Python's `export_snapshot` (so two
    /// exports within the same second never clobber each other). Returns the
    /// written file's URL.
    @discardableResult
    public static func exportSnapshot(
        appDatabase: AppDatabase,
        dataDirectory: URL
    ) throws -> URL {
        let snapshotsDirectory = dataDirectory.appendingPathComponent(subdirectoryName, isDirectory: true)
        try FileManager.default.createDirectory(at: snapshotsDirectory, withIntermediateDirectories: true)

        let machineId = try MachineID.get(dataDirectory: dataDirectory)
        let document = try appDatabase.dbWriter.read { db -> SnapshotDocument in
            if try SampleDataset.isLoaded(db: db) { throw ExportError.sampleDataPresent }
            return try SnapshotCodec.build(db: db, machineId: machineId)
        }

        let path = uniquePath(in: snapshotsDirectory, prefix: "snapshot")
        let blob = try SnapshotCodec.write(document)
        try blob.write(to: path, options: .atomic)
        return path
    }

    /// Port of `core/snapshots.py:export_snapshot(since=...)`. Builds a
    /// **delta** snapshot (only transactions with `updated_at >= since`, plus
    /// full rules/budgets/reports), writes it gzipped to
    /// `<dataDirectory>/snapshots/delta-<stamp>.json.gz`, and advances the
    /// `export_state` marker to the export start time — so the next delta
    /// defaults to "changes since this one". Returns the written file's URL.
    @discardableResult
    public static func exportDeltaSnapshot(
        appDatabase: AppDatabase,
        dataDirectory: URL,
        since: Date
    ) throws -> URL {
        let snapshotsDirectory = dataDirectory.appendingPathComponent(subdirectoryName, isDirectory: true)
        try FileManager.default.createDirectory(at: snapshotsDirectory, withIntermediateDirectories: true)

        let machineId = try MachineID.get(dataDirectory: dataDirectory)
        // Captured before the build, matching desktop's `export_started_at =
        // datetime.now()` taken ahead of `build_snapshot`.
        let exportStartedAt = Date()
        let document = try appDatabase.dbWriter.write { db -> SnapshotDocument in
            if try SampleDataset.isLoaded(db: db) { throw ExportError.sampleDataPresent }
            let document = try SnapshotCodec.build(db: db, machineId: machineId, since: since)
            try ExportStateRecord.setLastDeltaExportAt(db, exportStartedAt)
            return document
        }

        let path = uniquePath(in: snapshotsDirectory, prefix: "delta")
        let blob = try SnapshotCodec.write(document)
        try blob.write(to: path, options: .atomic)
        return path
    }

    /// Builds `<directory>/<prefix>-<stamp>.json.gz`, deduping with a `-1`,
    /// `-2`, ... suffix exactly like Python's `export_snapshot` (so two
    /// exports within the same second never clobber each other).
    private static func uniquePath(in directory: URL, prefix: String) -> URL {
        let stamp = SnapshotCodec.localFilenameStampFormatter.string(from: Date())
        var path = directory.appendingPathComponent("\(prefix)-\(stamp)\(SnapshotCodec.snapshotSuffix)")
        var suffixCounter = 1
        while FileManager.default.fileExists(atPath: path.path) {
            path = directory.appendingPathComponent("\(prefix)-\(stamp)-\(suffixCounter)\(SnapshotCodec.snapshotSuffix)")
            suffixCounter += 1
        }
        return path
    }
}
