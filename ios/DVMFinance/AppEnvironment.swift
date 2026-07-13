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

    init() {
        do {
            self.database = try AppEnvironment.makeLiveDatabase()
        } catch {
            // Phase A has no UI to surface a database-open failure, and a
            // broken database connection means the app has nothing useful
            // to show. Later phases may replace this with a recovery screen
            // (e.g. offer to restore from a snapshot backup).
            fatalError("Failed to open the app database: \(error)")
        }
    }

    private static func makeLiveDatabase() throws -> AppDatabase {
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
        let databaseURL = appDirectory.appendingPathComponent("dvm_finance.sqlite")
        return try AppDatabase.live(at: databaseURL)
    }
}

private struct AppDatabaseKey: EnvironmentKey {
    static let defaultValue: AppDatabase? = nil
}

extension EnvironmentValues {
    var appDatabase: AppDatabase? {
        get { self[AppDatabaseKey.self] }
        set { self[AppDatabaseKey.self] = newValue }
    }
}
