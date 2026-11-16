import Foundation
import GRDB

/// "Delete all data" of the import tab (`ios-data-reset`). Deletes each row
/// of each data table, and keeps the schema.
///
/// The caller runs `deleteAll(db:)` in one write transaction (see
/// `AppQueries.deleteAllData`), so an error rolls back each deletion. The
/// machine identity of the app is a file, not a row, so the reset does not
/// touch it.
public enum DataReset {

    /// The data tables, in the order of the foreign keys: a child table comes
    /// before its parent table.
    public static let resetTables: [String] = [
        "rule_change_items",
        "rule_change_reports",
        "rule_conditions",
        "categorization_rules",
        "transactions",
        "budgets",
        "snapshot_imports",
        "merge_reports",
        "export_state",
    ]

    /// The tables that the reset keeps on purpose. `grdb_migrations` holds
    /// the applied migrations, so the schema stays at its version. The test
    /// `DataResetTests` fails when a table is in neither list.
    public static let keptTables: Set<String> = [
        "grdb_migrations",
    ]

    /// Deletes each row of each table in `resetTables`. Returns the count of
    /// the deleted transactions.
    @discardableResult
    public static func deleteAll(db: Database) throws -> Int {
        let transactions = try TransactionRecord.fetchCount(db)
        for table in resetTables {
            try db.execute(sql: "DELETE FROM \(table)")
        }
        return transactions
    }

    /// The user tables of the schema that are neither in `resetTables` nor in
    /// `keptTables`. SQLite's own tables (`sqlite_%`) are not user tables.
    static func uncoveredTables(db: Database) throws -> [String] {
        let names = try String.fetchAll(
            db,
            sql: "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        let covered = Set(resetTables).union(keptTables)
        return names.filter { !covered.contains($0) }
    }

    /// Deletes each file in `<dataDirectory>/snapshots`, the folder of the
    /// exported snapshots. The `machine_id` marker file is in
    /// `dataDirectory`, not in this folder, so it stays. Returns the count of
    /// the deleted files.
    @discardableResult
    static func deleteSnapshotFiles(dataDirectory: URL) throws -> Int {
        let folder = dataDirectory.appendingPathComponent(SnapshotExporter.subdirectoryName, isDirectory: true)
        let fileManager = FileManager.default
        guard fileManager.fileExists(atPath: folder.path) else { return 0 }
        let files = try fileManager.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)
        for file in files {
            try fileManager.removeItem(at: file)
        }
        return files.count
    }

    /// Deletes each database backup in `dataDirectory`. A snapshot import
    /// writes a backup with the name `<stem>.backup-<stamp>.<ext>` next to
    /// the database (see `SnapshotImporter.backupDatabaseFile`). Each backup
    /// is a full copy of the data, so the reset must delete it too. The
    /// function does not touch the live database or another file. Returns the
    /// count of the deleted files.
    @discardableResult
    static func deleteDatabaseBackups(dataDirectory: URL) throws -> Int {
        let fileManager = FileManager.default
        guard fileManager.fileExists(atPath: dataDirectory.path) else { return 0 }
        let backups = try fileManager.contentsOfDirectory(at: dataDirectory, includingPropertiesForKeys: nil)
            .filter { $0.lastPathComponent.contains(".backup-") }
        for file in backups {
            try fileManager.removeItem(at: file)
        }
        return backups.count
    }
}
