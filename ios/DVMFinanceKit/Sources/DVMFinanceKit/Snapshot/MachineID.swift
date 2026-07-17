import Foundation

/// Port of `core/snapshots.py:get_machine_id`.
///
/// A UUID persisted as a plain-text "machine_id" marker file in the app's
/// data directory, so a snapshot's header can identify which device
/// exported it (`SnapshotHeader.machineId`). Read-through-or-create: an
/// existing, non-blank marker wins; otherwise a fresh UUID is generated,
/// the directory is created if needed, and the value is persisted before
/// being returned.
public enum MachineID {
    private static let markerFileName = "machine_id"

    /// Mirrors Python's `marker.exists()` -> `read_text().strip()` -> (if
    /// non-empty) return; else generate + `mkdir(parents=True,
    /// exist_ok=True)` + `write_text(...)` + return.
    ///
    /// Deviation: Python's `Path.read_text()` raises if the marker exists
    /// but is unreadable (e.g. permissions); this implementation instead
    /// falls through to "generate a fresh id" in that case (`try?`), since
    /// the app sandbox makes an unreadable-but-existing marker file an
    /// unrealistic scenario worth failing softly on rather than propagating
    /// a file-system error from what is otherwise a best-effort identifier.
    public static func get(dataDirectory: URL) throws -> String {
        let marker = dataDirectory.appendingPathComponent(markerFileName)
        if let data = try? Data(contentsOf: marker),
           let text = String(data: data, encoding: .utf8) {
            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty {
                return trimmed
            }
        }

        let value = UUID().uuidString
        try FileManager.default.createDirectory(
            at: dataDirectory,
            withIntermediateDirectories: true
        )
        try value.write(to: marker, atomically: true, encoding: .utf8)
        return value
    }
}
