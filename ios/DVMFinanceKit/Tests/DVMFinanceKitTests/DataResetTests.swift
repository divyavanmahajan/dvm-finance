import XCTest
import GRDB
@testable import DVMFinanceKit

/// Covers `DataReset` and `AppQueries.deleteAllData`: the reset empties each
/// data table in one transaction, keeps the schema and the machine identity,
/// and deletes the exported snapshot files.
final class DataResetTests: XCTestCase {

    private var directory: URL!

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("data-reset-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
    }

    /// Puts one row into each table of `DataReset.resetTables`.
    private func insertRowInEachTable(_ appDatabase: AppDatabase) throws {
        try appDatabase.dbWriter.write { db in
            try TransactionRecord(
                id: "tx-1",
                accountNumber: "NL91",
                transactiondate: DatabaseDateFormat.dateOnly.date(from: "2026-03-02")!,
                amount: Decimal(string: "-9.99")!,
                description: "User row",
                category: "groceries"
            ).insert(db)
            try db.execute(sql: """
                INSERT INTO categorization_rules (id, uuid, rule_type, match_pattern, match_value, category)
                VALUES (1, 'rule-uuid', 'simple', 'contains', 'Albert', 'groceries')
                """)
            try db.execute(sql: """
                INSERT INTO rule_conditions (rule_id, field_target, match_pattern, match_value)
                VALUES (1, 'description', 'contains', 'Albert')
                """)
            try db.execute(sql: """
                INSERT INTO rule_change_reports (id, created_at, action) VALUES (1, '2026-03-02T10:00:00', 'apply')
                """)
            try db.execute(sql: """
                INSERT INTO rule_change_items (report_id, transaction_id) VALUES (1, 'tx-1')
                """)
            var budget = BudgetRecord(category: "groceries", amount: 300, period: "month", notes: "Mine")
            try budget.insert(db)
            try db.execute(sql: "INSERT INTO snapshot_imports (created_at) VALUES ('2026-03-02T10:00:00')")
            try db.execute(sql: "INSERT INTO merge_reports (created_at) VALUES ('2026-03-02T10:00:00')")
            try db.execute(sql: "INSERT INTO export_state (last_delta_export_at) VALUES ('2026-03-02T10:00:00')")
        }
    }

    private func rowCounts(_ appDatabase: AppDatabase) throws -> [String: Int] {
        try appDatabase.dbWriter.read { db in
            var counts: [String: Int] = [:]
            for table in DataReset.resetTables {
                counts[table] = try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM \(table)") ?? 0
            }
            return counts
        }
    }

    private func schema(_ appDatabase: AppDatabase) throws -> [String] {
        try appDatabase.dbWriter.read { db in
            try String.fetchAll(db, sql: "SELECT type || ':' || name FROM sqlite_master ORDER BY type, name")
        }
    }

    func testDeleteAllEmptiesEachTableAndKeepsTheSchema() throws {
        let appDatabase = try AppDatabase.inMemory()
        try insertRowInEachTable(appDatabase)
        XCTAssertTrue(try rowCounts(appDatabase).values.allSatisfy { $0 == 1 })
        let schemaBefore = try schema(appDatabase)

        let deleted = try appDatabase.dbWriter.write { db in try DataReset.deleteAll(db: db) }

        XCTAssertEqual(deleted, 1)
        for (table, count) in try rowCounts(appDatabase) {
            XCTAssertEqual(count, 0, "table \(table) is not empty")
        }
        XCTAssertEqual(try schema(appDatabase), schemaBefore)
        let migrations = try appDatabase.dbWriter.read { db in
            try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM grdb_migrations") ?? 0
        }
        XCTAssertGreaterThan(migrations, 0)
    }

    func testEachTableIsResetOrExplicitlyKept() throws {
        let appDatabase = try AppDatabase.inMemory()
        try appDatabase.dbWriter.read { db in
            XCTAssertEqual(
                try DataReset.uncoveredTables(db: db), [],
                "Add each new data table to DataReset.resetTables, or to DataReset.keptTables."
            )
        }
    }

    func testCompletenessCheckFindsANewTable() throws {
        let appDatabase = try AppDatabase.inMemory()
        try appDatabase.dbWriter.write { db in
            try db.execute(sql: "CREATE TABLE extra_table (id INTEGER PRIMARY KEY)")
        }
        try appDatabase.dbWriter.read { db in
            XCTAssertEqual(try DataReset.uncoveredTables(db: db), ["extra_table"])
        }
    }

    func testDeleteAllDataDeletesSnapshotFilesAndKeepsTheMachineID() async throws {
        let appDatabase = try AppDatabase.inMemory()
        try insertRowInEachTable(appDatabase)
        let machineBefore = try MachineID.get(dataDirectory: directory)
        let exported = try SnapshotExporter.exportSnapshot(appDatabase: appDatabase, dataDirectory: directory)
        XCTAssertTrue(FileManager.default.fileExists(atPath: exported.path))

        let deleted = try await AppQueries.deleteAllData(appDatabase: appDatabase, dataDirectory: directory)

        XCTAssertEqual(deleted, 1)
        XCTAssertFalse(FileManager.default.fileExists(atPath: exported.path))
        XCTAssertEqual(try MachineID.get(dataDirectory: directory), machineBefore)
        for (table, count) in try rowCounts(appDatabase) {
            XCTAssertEqual(count, 0, "table \(table) is not empty")
        }
        let isEmpty = try await AppQueries.databaseIsEmpty(appDatabase: appDatabase)
        XCTAssertTrue(isEmpty)
    }

    func testDeleteAllDataDeletesTheDatabaseBackups() async throws {
        let appDatabase = try AppDatabase.inMemory()
        try insertRowInEachTable(appDatabase)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let backup = directory.appendingPathComponent("dvm_finance.backup-20261116-210000.sqlite")
        let second = directory.appendingPathComponent("dvm_finance.backup-20261116-210000-1.sqlite")
        let live = directory.appendingPathComponent("dvm_finance.sqlite")
        for file in [backup, second, live] {
            XCTAssertTrue(FileManager.default.createFile(atPath: file.path, contents: Data("x".utf8)))
        }

        try await AppQueries.deleteAllData(appDatabase: appDatabase, dataDirectory: directory)

        XCTAssertFalse(FileManager.default.fileExists(atPath: backup.path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: second.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: live.path))
    }

    func testAnErrorRollsBackEachRowAndKeepsTheFiles() async throws {
        struct InjectedError: Error {}
        let appDatabase = try AppDatabase.inMemory()
        try insertRowInEachTable(appDatabase)
        let exported = try SnapshotExporter.exportSnapshot(appDatabase: appDatabase, dataDirectory: directory)
        let before = try rowCounts(appDatabase)

        do {
            _ = try await AppQueries.deleteAllData(
                appDatabase: appDatabase,
                dataDirectory: directory,
                beforeCommit: { _ in throw InjectedError() }
            )
            XCTFail("expected the injected error")
        } catch is InjectedError {
            // Expected.
        }

        XCTAssertEqual(try rowCounts(appDatabase), before)
        XCTAssertTrue(FileManager.default.fileExists(atPath: exported.path))
    }

    func testImportAfterTheResetWorksAsOnANewInstallation() async throws {
        let appDatabase = try AppDatabase.inMemory()
        try insertRowInEachTable(appDatabase)
        try await AppQueries.deleteAllData(appDatabase: appDatabase, dataDirectory: directory)

        let blob = try Data(contentsOf: try fixtureURL("fixture-snapshot", "json.gz"))
        let document = try SnapshotCodec.read(blob)
        let fresh = try AppDatabase.inMemory()
        let nowhere = directory.appendingPathComponent("none.sqlite")
        _ = try SnapshotImporter.importSnapshot(appDatabase: appDatabase, document: document, databaseURL: nowhere)
        _ = try SnapshotImporter.importSnapshot(appDatabase: fresh, document: document, databaseURL: nowhere)

        let counts = try rowCounts(appDatabase)
        let freshCounts = try rowCounts(fresh)
        XCTAssertEqual(counts["transactions"], freshCounts["transactions"])
        XCTAssertEqual(counts["categorization_rules"], freshCounts["categorization_rules"])
        XCTAssertEqual(counts["budgets"], freshCounts["budgets"])
    }
}
