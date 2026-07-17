import XCTest
import GRDB
@testable import DVMFinanceKit

/// Covers the period-aware "seed from average" bulk action
/// (`BudgetMutations.seedTopLevelBudgets`) that backs the split
/// Monthly / Yearly Budgets tabs.
///
/// Monthly seeding is the original `budgets_create_top_level` behavior
/// (last-3-month monthly average, current-month validity). Yearly seeding
/// proposes the annualized amount (`12 ×` the monthly average, rounded to
/// 2dp) with full-calendar-year validity. Both skip categories that already
/// have a budget of that period, skip a non-positive average, and never touch
/// existing budgets.
final class BudgetSeedTests: XCTestCase {
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
        date: Date,
        amount: Double,
        category: String? = nil
    ) throws -> TransactionRecord {
        let record = TransactionRecord(
            id: id,
            accountNumber: "ACC1",
            transactiondate: date,
            amount: Decimal(string: String(format: "%.2f", amount))!,
            description: "desc",
            category: category,
            currency: "EUR"
        )
        try record.insert(db)
        return record
    }

    /// Seeds three full months (Apr/May/Jun 2026) of `groceries` spend so the
    /// 3-month average, referenced from Jul 2026, is a clean 120.00/month.
    private func seedThreeMonthsOfGroceries(_ db: Database) throws {
        try insertTxn(db, id: "a", date: makeDate(2026, 4, 10), amount: -100, category: "groceries")
        try insertTxn(db, id: "b", date: makeDate(2026, 5, 10), amount: -120, category: "groceries")
        try insertTxn(db, id: "c", date: makeDate(2026, 6, 10), amount: -140, category: "groceries")
        // (100 + 120 + 140) / 3 = 120.00
    }

    // MARK: - Monthly seeding (unchanged behavior)

    func testMonthlySeedingCreatesMonthBudget() throws {
        let reference = makeDate(2026, 7, 15)
        try appDatabase.dbWriter.write { db in
            try seedThreeMonthsOfGroceries(db)
            let created = try BudgetMutations.seedTopLevelBudgets(
                db: db, period: .month, reference: reference)
            XCTAssertEqual(created, ["groceries"])

            let budget = try BudgetRecord
                .filter(Column("category") == "groceries" && Column("period") == "month")
                .fetchOne(db)
            let record = try XCTUnwrap(budget)
            XCTAssertEqual(record.amount, Decimal(string: "120.00"))
            XCTAssertEqual(record.startDate, self.makeDate(2026, 7, 1))
            XCTAssertEqual(record.endDate, self.makeDate(2026, 7, 31))
            XCTAssertEqual(record.notes, "Auto-created from 3-month average")
        }
    }

    /// The legacy `seedTopLevelMonthBudgets` entry point still delegates to the
    /// month path.
    func testLegacyMonthEntryPointStillWorks() throws {
        let reference = makeDate(2026, 7, 15)
        try appDatabase.dbWriter.write { db in
            try seedThreeMonthsOfGroceries(db)
            let created = try BudgetMutations.seedTopLevelMonthBudgets(db: db, reference: reference)
            XCTAssertEqual(created, ["groceries"])
            let count = try BudgetRecord
                .filter(Column("period") == "month").fetchCount(db)
            XCTAssertEqual(count, 1)
        }
    }

    // MARK: - Yearly seeding (annualized)

    func testYearlySeedingCreatesAnnualizedYearBudget() throws {
        let reference = makeDate(2026, 7, 15)
        try appDatabase.dbWriter.write { db in
            try seedThreeMonthsOfGroceries(db)
            let created = try BudgetMutations.seedTopLevelBudgets(
                db: db, period: .year, reference: reference)
            XCTAssertEqual(created, ["groceries"])

            let budget = try BudgetRecord
                .filter(Column("category") == "groceries" && Column("period") == "year")
                .fetchOne(db)
            let record = try XCTUnwrap(budget)
            // 12 × 120.00 monthly average = 1440.00
            XCTAssertEqual(record.amount, Decimal(string: "1440.00"))
            XCTAssertEqual(record.startDate, self.makeDate(2026, 1, 1))
            XCTAssertEqual(record.endDate, self.makeDate(2026, 12, 31))
            XCTAssertEqual(record.notes, "Auto-created from 3-month average (annualized)")
        }
    }

    // MARK: - Independence of period tabs

    func testMonthlyAndYearlyBudgetsCoexist() throws {
        let reference = makeDate(2026, 7, 15)
        try appDatabase.dbWriter.write { db in
            try seedThreeMonthsOfGroceries(db)
            _ = try BudgetMutations.seedTopLevelBudgets(db: db, period: .month, reference: reference)
            // A month budget must NOT block a year budget for the same category.
            let created = try BudgetMutations.seedTopLevelBudgets(
                db: db, period: .year, reference: reference)
            XCTAssertEqual(created, ["groceries"])
            XCTAssertEqual(try BudgetRecord.fetchCount(db), 2)
        }
    }

    // MARK: - Skips

    func testSeedingSkipsExistingBudgetOfSamePeriod() throws {
        let reference = makeDate(2026, 7, 15)
        try appDatabase.dbWriter.write { db in
            try seedThreeMonthsOfGroceries(db)
            _ = try BudgetMutations.seedTopLevelBudgets(db: db, period: .year, reference: reference)
            // Second run adds nothing and leaves the existing budget untouched.
            let created = try BudgetMutations.seedTopLevelBudgets(
                db: db, period: .year, reference: reference)
            XCTAssertTrue(created.isEmpty)
            XCTAssertEqual(
                try BudgetRecord.filter(Column("period") == "year").fetchCount(db), 1)
        }
    }

    func testSeedingSkipsNonPositiveAverage() throws {
        let reference = makeDate(2026, 7, 15)
        try appDatabase.dbWriter.write { db in
            // Spend only in the current (partial) month, which the average
            // excludes → average is 0 → category is skipped for both periods.
            try self.insertTxn(db, id: "x", date: self.makeDate(2026, 7, 5), amount: -50, category: "groceries")
            let month = try BudgetMutations.seedTopLevelBudgets(
                db: db, period: .month, reference: reference)
            let year = try BudgetMutations.seedTopLevelBudgets(
                db: db, period: .year, reference: reference)
            XCTAssertTrue(month.isEmpty)
            XCTAssertTrue(year.isEmpty)
            XCTAssertEqual(try BudgetRecord.fetchCount(db), 0)
        }
    }
}
