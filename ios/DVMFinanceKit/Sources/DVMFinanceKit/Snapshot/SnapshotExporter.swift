import Foundation
import GRDB

/// Port of `core/snapshots.py:export_snapshot` (+ `list_exports`, not needed
/// in v1 — the "Import" screen's export history list reads
/// `snapshot_imports` rows directly, not the filesystem; see `ios/docs/
/// spec.md` "UI").
public enum SnapshotExporter {
    private static let subdirectoryName = "snapshots"

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
        let document = try appDatabase.dbWriter.read { db in
            try SnapshotCodec.build(db: db, machineId: machineId)
        }

        let stamp = SnapshotCodec.localFilenameStampFormatter.string(from: Date())
        var path = snapshotsDirectory.appendingPathComponent("snapshot-\(stamp)\(SnapshotCodec.snapshotSuffix)")
        var suffixCounter = 1
        while FileManager.default.fileExists(atPath: path.path) {
            path = snapshotsDirectory.appendingPathComponent("snapshot-\(stamp)-\(suffixCounter)\(SnapshotCodec.snapshotSuffix)")
            suffixCounter += 1
        }

        let blob = try SnapshotCodec.write(document)
        try blob.write(to: path, options: .atomic)
        return path
    }
}
