import XCTest
import GRDB
@testable import DVMFinanceKit

/// Covers `SampleDataset`: the load adds rows and keeps the user's rows, the
/// removal deletes only the sample rows, and the exporter refuses an export
/// while the sample set is present.
final class SampleDatasetTests: XCTestCase {

    /// A fixed "today": the 20th of the month, so that the current month
    /// holds only the items on day 20 or earlier.
    private let today = DatabaseDateFormat.dateOnly.date(from: "2026-11-20")!

    private func makeDatabase() throws -> AppDatabase {
        try AppDatabase.inMemory()
    }

    private func insertUserRows(_ appDatabase: AppDatabase) throws {
        try appDatabase.dbWriter.write { db in
            try TransactionRecord(
                id: "NL91_2026-03-02_-9.99_abc",
                accountNumber: "NL91",
                transactiondate: DatabaseDateFormat.dateOnly.date(from: "2026-03-02")!,
                amount: Decimal(string: "-9.99")!,
                description: "User row",
                category: "groceries"
            ).insert(db)
            var budget = BudgetRecord(category: "groceries", amount: 300, period: "month", notes: "Mine")
            try budget.insert(db)
        }
    }

    private func count(_ appDatabase: AppDatabase) throws -> (transactions: Int, budgets: Int) {
        try appDatabase.dbWriter.read { db in
            (try TransactionRecord.fetchCount(db), try BudgetRecord.fetchCount(db))
        }
    }

    func testInsertAddsTheSetAndKeepsUserRows() throws {
        let appDatabase = try makeDatabase()
        try insertUserRows(appDatabase)

        let counts = try appDatabase.dbWriter.write { db in
            try SampleDataset.insert(db: db, today: today, localCalendar: DateMath.calendar)
        }

        // 16 items over 11 full months, plus the 13 items with a day of 20
        // or earlier in the current month. The user's monthly "groceries"
        // budget makes the load skip the sample one.
        XCTAssertEqual(counts, SampleDataset.Counts(transactions: 16 * 11 + 13, budgets: 4))
        let total = try count(appDatabase)
        XCTAssertEqual(total.transactions, 1 + counts.transactions)
        XCTAssertEqual(total.budgets, 1 + 4)
        let userBudget = try appDatabase.dbWriter.read { db in
            try BudgetRecord.filter(Column("category") == "groceries").fetchOne(db)
        }
        XCTAssertEqual(userBudget?.notes, "Mine")
        let userRow = try appDatabase.dbWriter.read { db in
            try TransactionRecord.fetchOne(db, key: "NL91_2026-03-02_-9.99_abc")
        }
        XCTAssertEqual(userRow?.description, "User row")
    }

    func testInsertSkipsDaysAfterToday() throws {
        let appDatabase = try makeDatabase()
        try appDatabase.dbWriter.write { db in _ = try SampleDataset.insert(db: db, today: today, localCalendar: DateMath.calendar) }

        let latest = try appDatabase.dbWriter.read { db in
            try TransactionRecord.order(Column("transactiondate").desc).fetchOne(db)
        }
        XCTAssertLessThanOrEqual(try XCTUnwrap(latest).transactiondate, today)
    }

    func testDatesKeepTheirCalendarDay() throws {
        let appDatabase = try makeDatabase()
        // A local calendar east of UTC: local midnight is the evening before
        // in UTC. The stored day must still be the local calendar day.
        var amsterdam = Calendar(identifier: .gregorian)
        amsterdam.timeZone = TimeZone(identifier: "Europe/Amsterdam")!
        let localToday = amsterdam.date(from: DateComponents(year: 2026, month: 11, day: 20))!
        try appDatabase.dbWriter.write { db in
            _ = try SampleDataset.insert(db: db, today: localToday, localCalendar: amsterdam)
        }

        let bloem = try appDatabase.dbWriter.read { db in
            try TransactionRecord
                .filter(Column("description") == "Restaurant Bloem")
                .order(Column("transactiondate").desc)
                .fetchOne(db)
        }
        XCTAssertEqual(DatabaseDateFormat.dateOnly.string(from: try XCTUnwrap(bloem).transactiondate), "2026-11-14")
    }

    func testSecondInsertAddsNothing() throws {
        let appDatabase = try makeDatabase()
        try appDatabase.dbWriter.write { db in _ = try SampleDataset.insert(db: db, today: today, localCalendar: DateMath.calendar) }
        let before = try count(appDatabase)

        let second = try appDatabase.dbWriter.write { db in
            try SampleDataset.insert(db: db, today: today, localCalendar: DateMath.calendar)
        }

        XCTAssertEqual(second, SampleDataset.Counts(transactions: 0, budgets: 0))
        let after = try count(appDatabase)
        XCTAssertEqual(after.transactions, before.transactions)
        XCTAssertEqual(after.budgets, before.budgets)
    }

    func testIsLoadedAndIsDatabaseEmpty() throws {
        let appDatabase = try makeDatabase()
        try appDatabase.dbWriter.read { db in
            XCTAssertFalse(try SampleDataset.isLoaded(db: db))
            XCTAssertTrue(try SampleDataset.isDatabaseEmpty(db: db))
        }

        try appDatabase.dbWriter.write { db in _ = try SampleDataset.insert(db: db, today: today, localCalendar: DateMath.calendar) }

        try appDatabase.dbWriter.read { db in
            XCTAssertTrue(try SampleDataset.isLoaded(db: db))
            XCTAssertFalse(try SampleDataset.isDatabaseEmpty(db: db))
        }
    }

    func testRemoveDeletesOnlySampleRows() throws {
        let appDatabase = try makeDatabase()
        try insertUserRows(appDatabase)
        let inserted = try appDatabase.dbWriter.write { db in
            try SampleDataset.insert(db: db, today: today, localCalendar: DateMath.calendar)
        }

        let removed = try appDatabase.dbWriter.write { db in try SampleDataset.remove(db: db) }

        XCTAssertEqual(removed, inserted)
        let total = try count(appDatabase)
        XCTAssertEqual(total.transactions, 1)
        XCTAssertEqual(total.budgets, 1)
        try appDatabase.dbWriter.read { db in
            XCTAssertFalse(try SampleDataset.isLoaded(db: db))
        }
    }

    func testExportRefusesWhileSampleDataIsPresent() throws {
        let appDatabase = try makeDatabase()
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("sample-export-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try appDatabase.dbWriter.write { db in _ = try SampleDataset.insert(db: db, today: today, localCalendar: DateMath.calendar) }

        XCTAssertThrowsError(
            try SnapshotExporter.exportSnapshot(appDatabase: appDatabase, dataDirectory: directory)
        ) { error in
            XCTAssertEqual(error as? SnapshotExporter.ExportError, .sampleDataPresent)
        }
        XCTAssertThrowsError(
            try SnapshotExporter.exportDeltaSnapshot(appDatabase: appDatabase, dataDirectory: directory, since: today)
        ) { error in
            XCTAssertEqual(error as? SnapshotExporter.ExportError, .sampleDataPresent)
        }

        try appDatabase.dbWriter.write { db in _ = try SampleDataset.remove(db: db) }
        XCTAssertNoThrow(try SnapshotExporter.exportSnapshot(appDatabase: appDatabase, dataDirectory: directory))
    }
}
