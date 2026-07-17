import XCTest
import GRDB
@testable import DVMFinanceKit

/// Covers `ios/docs/plan.md` "Phase E" acceptance for `TrendsBuilder` (port
/// of `core/trends.py`): the default 12-full-month window, month bucketing,
/// hyphen-rollup parent sums, `NULL`/`''` accumulation into the
/// "Uncategorized" row, transfer exclusion, and the cell-to-filter
/// round-trip that makes a tapped cell's linked transactions sum exactly to
/// the cell.
final class TrendsTests: XCTestCase {
    var appDatabase: AppDatabase!

    override func setUpWithError() throws {
        appDatabase = try AppDatabase.inMemory()
    }

    override func tearDownWithError() throws {
        appDatabase = nil
    }

    private func makeDate(_ year: Int, _ month: Int, _ day: Int) -> Date {
        var components = DateComponents()
        components.year = year
        components.month = month
        components.day = day
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        return calendar.date(from: components)!
    }

    @discardableResult
    private func insertTxn(
        _ db: Database,
        id: String,
        account: String = "ACC1",
        date: Date,
        amount: Double,
        category: String? = nil,
        manualCategory: String? = nil
    ) throws -> TransactionRecord {
        let record = TransactionRecord(
            id: id,
            accountNumber: account,
            transactiondate: date,
            amount: Decimal(string: String(format: "%.2f", amount))!,
            description: "desc",
            category: category,
            manualCategory: manualCategory,
            currency: "EUR"
        )
        try record.insert(db)
        return record
    }

    // MARK: - Default window

    func testDefaultWindowIsLast12FullMonthsExcludingCurrent() {
        let today = makeDate(2026, 7, 14)
        let window = TrendsBuilder.defaultWindow(today: today)
        XCTAssertEqual(window.from, makeDate(2025, 7, 1))
        XCTAssertEqual(window.to, makeDate(2026, 6, 30))
    }

    // MARK: - Month bucketing

    func testMonthBucketingGroupsByStrftimeYearMonth() throws {
        try appDatabase.dbWriter.write { db in
            try self.insertTxn(db, id: "t1", date: self.makeDate(2026, 1, 5), amount: -10, category: "groceries")
            try self.insertTxn(db, id: "t2", date: self.makeDate(2026, 1, 20), amount: -5, category: "groceries")
            try self.insertTxn(db, id: "t3", date: self.makeDate(2026, 2, 3), amount: -7, category: "groceries")
        }

        let params = TrendsBuilder.TrendsParams(
            dateFrom: makeDate(2026, 1, 1),
            dateTo: makeDate(2026, 2, 28),
            includeTransfers: true
        )
        let table = try appDatabase.dbWriter.read { db in
            try TrendsBuilder.aggregate(db: db, params: params)
        }

        XCTAssertEqual(table.periods.map(\.key), ["2026-01", "2026-02"])
        let groceries = try XCTUnwrap(table.rows.first { $0.label == "groceries" })
        XCTAssertEqual(groceries.cells["2026-01"] ?? 0, -15, accuracy: 0.001)
        XCTAssertEqual(groceries.cells["2026-02"] ?? 0, -7, accuracy: 0.001)
    }

    // MARK: - Hyphen rollup

    func testHyphenRollupParentSumsChildren() throws {
        try appDatabase.dbWriter.write { db in
            try self.insertTxn(db, id: "t1", date: self.makeDate(2026, 1, 5), amount: -10, category: "education-tuition-violin")
            try self.insertTxn(db, id: "t2", date: self.makeDate(2026, 1, 6), amount: -20, category: "education-books")
        }

        let params = TrendsBuilder.TrendsParams(
            dateFrom: makeDate(2026, 1, 1),
            dateTo: makeDate(2026, 1, 31),
            includeTransfers: true
        )
        let table = try appDatabase.dbWriter.read { db in
            try TrendsBuilder.aggregate(db: db, params: params)
        }

        let education = try XCTUnwrap(table.rows.first { $0.label == "education" })
        XCTAssertEqual(Set(education.categories), ["education-books", "education-tuition-violin"])
        XCTAssertTrue(education.hasChildren)
        XCTAssertEqual(education.children.map(\.label), ["education-books", "education-tuition-violin"])
        XCTAssertEqual(education.cells["2026-01"] ?? 0, -30, accuracy: 0.001)
        XCTAssertEqual(education.total, -30, accuracy: 0.001)
    }

    // MARK: - Uncategorized accumulation

    func testUncategorizedAccumulatesNullAndEmptyString() throws {
        try appDatabase.dbWriter.write { db in
            try self.insertTxn(db, id: "t1", date: self.makeDate(2026, 1, 5), amount: -10, category: nil)
            try self.insertTxn(db, id: "t2", date: self.makeDate(2026, 1, 6), amount: -20, category: "")
        }

        let params = TrendsBuilder.TrendsParams(
            dateFrom: makeDate(2026, 1, 1),
            dateTo: makeDate(2026, 1, 31),
            includeTransfers: true
        )
        let table = try appDatabase.dbWriter.read { db in
            try TrendsBuilder.aggregate(db: db, params: params)
        }

        let uncategorized = try XCTUnwrap(table.rows.first { $0.label == TrendsBuilder.uncategorizedLabel })
        XCTAssertEqual(uncategorized.categories, [TransactionFilter.uncategorized])
        // Both the NULL-category and the ''-category row accumulate into one
        // bucket, even though SQL GROUP BY treats them as two groups.
        XCTAssertEqual(uncategorized.cells["2026-01"] ?? 0, -30, accuracy: 0.001)
        XCTAssertEqual(uncategorized.total, -30, accuracy: 0.001)
        // Appended last in pre-sort order, but category_asc (default) then
        // re-sorts everything alphabetically.
        XCTAssertEqual(table.rows.last?.label, TrendsBuilder.uncategorizedLabel)
    }

    // MARK: - Transfer exclusion

    func testTransferExclusionContainsSemantics() throws {
        try appDatabase.dbWriter.write { db in
            try self.insertTxn(db, id: "t1", date: self.makeDate(2026, 1, 5), amount: -10, category: "transfer-wise")
            try self.insertTxn(db, id: "t2", date: self.makeDate(2026, 1, 6), amount: -20, category: "my-transfer-x")
            try self.insertTxn(db, id: "t3", date: self.makeDate(2026, 1, 7), amount: -30, category: "groceries")
        }

        let excluded = TrendsBuilder.TrendsParams(
            dateFrom: makeDate(2026, 1, 1),
            dateTo: makeDate(2026, 1, 31),
            includeTransfers: false
        )
        let excludedTable = try appDatabase.dbWriter.read { db in
            try TrendsBuilder.aggregate(db: db, params: excluded)
        }
        XCTAssertEqual(excludedTable.rows.map(\.label), ["groceries"])

        let included = TrendsBuilder.TrendsParams(
            dateFrom: makeDate(2026, 1, 1),
            dateTo: makeDate(2026, 1, 31),
            includeTransfers: true
        )
        let includedTable = try appDatabase.dbWriter.read { db in
            try TrendsBuilder.aggregate(db: db, params: included)
        }
        XCTAssertEqual(Set(includedTable.rows.map(\.label)), ["groceries", "my-transfer-x", "transfer-wise"])
    }

    // MARK: - Cell -> TransactionFilter round-trip

    func testCellFilterRoundTripSumsExactlyToCell() throws {
        try appDatabase.dbWriter.write { db in
            try self.insertTxn(db, id: "t1", date: self.makeDate(2026, 1, 5), amount: -10, category: "education-tuition-violin")
            try self.insertTxn(db, id: "t2", date: self.makeDate(2026, 1, 20), amount: -20, category: "education-books")
            // Different period / different category: must not leak into the cell.
            try self.insertTxn(db, id: "t3", date: self.makeDate(2026, 2, 1), amount: -99, category: "education-books")
            try self.insertTxn(db, id: "t4", date: self.makeDate(2026, 1, 10), amount: -50, category: "groceries")
        }

        let params = TrendsBuilder.TrendsParams(
            dateFrom: makeDate(2026, 1, 1),
            dateTo: makeDate(2026, 2, 28),
            includeTransfers: true
        )
        let table = try appDatabase.dbWriter.read { db in
            try TrendsBuilder.aggregate(db: db, params: params)
        }

        let educationRow = try XCTUnwrap(table.rows.first { $0.label == "education" })
        let januaryPeriod = try XCTUnwrap(table.periods.first { $0.key == "2026-01" })
        let cellValue = try XCTUnwrap(educationRow.cells[januaryPeriod.key])
        XCTAssertEqual(cellValue, -30, accuracy: 0.001)

        let cellFilter = TrendsBuilder.transactionFilter(
            for: educationRow,
            period: januaryPeriod,
            params: params
        )
        let sum = try appDatabase.dbWriter.read { db in
            try TransactionQuery.sum(db: db, filter: cellFilter)
        }
        XCTAssertEqual(sum, cellValue, accuracy: 0.001)

        let matchingIds = try appDatabase.dbWriter.read { db in
            try TransactionQuery.paginate(db: db, filter: cellFilter).items.map(\.id)
        }
        XCTAssertEqual(Set(matchingIds), ["t1", "t2"])
    }
}
