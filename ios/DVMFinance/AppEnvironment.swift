import Foundation
import SwiftUI
import DVMFinanceKit

/// Owns the single live `AppDatabase` connection for the app process and
/// exposes it to SwiftUI via `.environment(\.appDatabase)`.
///
/// The database file lives at
/// `Application Support/DVMFinance/dvm_finance.sqlite`. This is intentional:
/// per `ios/docs/spec.md`, the iOS database is never opened by the desktop
/// Python app — the two are kept in sync exclusively through the gzipped
/// JSON snapshot format (Phase C).
@MainActor
final class AppEnvironment: ObservableObject {
    let database: AppDatabase
    /// `Application Support/DVMFinance` — also `SnapshotExporter`'s
    /// `dataDirectory` (its `snapshots/` subdirectory holds exports) and
    /// `MachineID`'s marker-file directory. Exposed so the Import screen
    /// doesn't have to re-derive this path itself.
    let dataDirectory: URL
    /// The live SQLite file backing `database` — `SnapshotImporter.importSnapshot`
    /// needs this to back up the file before merging.
    let databaseURL: URL

    init() {
        do {
            let directory = try AppEnvironment.makeDataDirectory()
            let url = directory.appendingPathComponent("dvm_finance.sqlite")
            self.dataDirectory = directory
            self.databaseURL = url
            self.database = try AppDatabase.live(at: url)
            #if DEBUG
            // Screenshot / UI-test hook: repopulate with deterministic demo
            // data when launched with `-UITestSeed`. Never runs in Release.
            if ProcessInfo.processInfo.arguments.contains("-UITestSeed") {
                try? SampleData.populate(into: self.database)
            }
            #endif
        } catch {
            // Phase A has no UI to surface a database-open failure, and a
            // broken database connection means the app has nothing useful
            // to show. Later phases may replace this with a recovery screen
            // (e.g. offer to restore from a snapshot backup).
            fatalError("Failed to open the app database: \(error)")
        }
    }

    private static func makeDataDirectory() throws -> URL {
        let fileManager = FileManager.default
        let supportDirectory = try fileManager.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        let appDirectory = supportDirectory.appendingPathComponent("DVMFinance", isDirectory: true)
        if !fileManager.fileExists(atPath: appDirectory.path) {
            try fileManager.createDirectory(at: appDirectory, withIntermediateDirectories: true)
        }
        return appDirectory
    }
}

private struct AppDatabaseKey: EnvironmentKey {
    static let defaultValue: AppDatabase? = nil
}

private struct AppDataDirectoryKey: EnvironmentKey {
    static let defaultValue: URL? = nil
}

private struct AppDatabaseURLKey: EnvironmentKey {
    static let defaultValue: URL? = nil
}

extension EnvironmentValues {
    var appDatabase: AppDatabase? {
        get { self[AppDatabaseKey.self] }
        set { self[AppDatabaseKey.self] = newValue }
    }

    var appDataDirectory: URL? {
        get { self[AppDataDirectoryKey.self] }
        set { self[AppDataDirectoryKey.self] = newValue }
    }

    var appDatabaseURL: URL? {
        get { self[AppDatabaseURLKey.self] }
        set { self[AppDatabaseURLKey.self] = newValue }
    }
}
