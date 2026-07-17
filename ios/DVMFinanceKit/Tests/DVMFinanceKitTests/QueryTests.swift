import XCTest
import GRDB
@testable import DVMFinanceKit

/// Covers `ios/docs/plan.md` "Phase E" acceptance for `TransactionQuery`
/// (port of `core/filters.py: build_query`/`apply_sort`/`paginate`): subtree
/// include/exclude semantics, transfer exclusion's contains-not-prefix
/// quirk, manual-category `NULLIF('')` precedence, free-text search against
/// `description_structured`, absolute-amount range, sort tiebreaking, and
/// pagination clamping.
final class QueryTests: XCTestCase {
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
        description: String = "desc",
        descriptionStructured: String? = nil,
        category: String? = nil,
        manualCategory: String? = nil,
        tags: String? = nil,
        manualTags: String? = nil
    ) throws -> TransactionRecord {
        let record = TransactionRecord(
            id: id,
            accountNumber: account,
            transactiondate: date,
            amount: Decimal(string: String(format: "%.2f", amount))!,
            description: description,
            descriptionStructured: descriptionStructured,
            category: category,
            manualCategory: manualCategory,
            tags: tags,
            manualTags: manualTags,
            currency: "EUR"
        )
        try record.insert(db)
        return record
    }

    // MARK: - Subtree include

    func testSubtreeIncludeMatchesChildNotUnrelatedPrefix() throws {
        try appDatabase.dbWriter.write { db in
            try self.insertTxn(db, id: "t1", date: self.makeDate(2026, 1, 5), amount: -10, category: "fixed-insurance-life")
            try self.insertTxn(db, id: "t2", date: self.makeDate(2026, 1, 6), amount: -20, category: "fixedother")
            try self.insertTxn(db, id: "t3", date: self.makeDate(2026, 1, 7), amount: -30, category: "fixed")
        }

        let filter = TransactionFilter(categories: ["fixed"], includeTransfers: true)
        let page = try appDatabase.dbWriter.read { db in
            try TransactionQuery.paginate(db: db, filter: filter)
        }

        XCTAssertEqual(Set(page.items.map(\.id)), ["t1", "t3"])
    }

    // MARK: - Exclude categories

    func testExcludeCategoryKeepsUncategorizedRows() throws {
        try appDatabase.dbWriter.write { db in
            try self.insertTxn(db, id: "cat", date: self.makeDate(2026, 1, 5), amount: -10, category: "groceries-ah")
            try self.insertTxn(db, id: "uncat", date: self.makeDate(2026, 1, 6), amount: -20, category: nil)
            try self.insertTxn(db, id: "other", date: self.makeDate(2026, 1, 7), amount: -30, category: "shopping")
        }

        let filter = TransactionFilter(excludeCategories: ["groceries"], includeTransfers: true)
        let page = try appDatabase.dbWriter.read { db in
            try TransactionQuery.paginate(db: db, filter: filter)
        }

        // "groceries" subtree is excluded, but the NULL/uncategorized row and
        // the unrelated category both survive (build_query lines 404-412).
        XCTAssertEqual(Set(page.items.map(\.id)), ["uncat", "other"])
    }

    func testExcludeUncategorizedIsPlainNegation() throws {
        try appDatabase.dbWriter.write { db in
            try self.insertTxn(db, id: "cat", date: self.makeDate(2026, 1, 5), amount: -10, category: "groceries-ah")
            try self.insertTxn(db, id: "uncat1", date: self.makeDate(2026, 1, 6), amount: -20, category: nil)
            try self.insertTxn(db, id: "uncat2", date: self.makeDate(2026, 1, 7), amount: -30, category: "")
        }

        let filter = TransactionFilter(excludeCategories: [TransactionFilter.uncategorized], includeTransfers: true)
        let page = try appDatabase.dbWriter.read { db in
            try TransactionQuery.paginate(db: db, filter: filter)
        }

        XCTAssertEqual(page.items.map(\.id), ["cat"])
    }

    // MARK: - Transfer exclusion (contains, not prefix)

    func testTransferExclusionUsesContainsSemantics() throws {
        try appDatabase.dbWriter.write { db in
            try self.insertTxn(db, id: "prefix", date: self.makeDate(2026, 1, 5), amount: -10, category: "transfer-wise")
            try self.insertTxn(db, id: "contains", date: self.makeDate(2026, 1, 6), amount: -20, category: "my-transfer-x")
            try self.insertTxn(db, id: "uncat", date: self.makeDate(2026, 1, 7), amount: -30, category: nil)
            try self.insertTxn(db, id: "normal", date: self.makeDate(2026, 1, 8), amount: -40, category: "groceries")
        }

        // Default: include_transfers == false excludes both the prefix and
        // the contains-only match; uncategorized rows are kept.
        let excluded = TransactionFilter()
        let excludedPage = try appDatabase.dbWriter.read { db in
            try TransactionQuery.paginate(db: db, filter: excluded)
        }
        XCTAssertEqual(Set(excludedPage.items.map(\.id)), ["uncat", "normal"])

        // include_transfers == true restores everything.
        let included = TransactionFilter(includeTransfers: true)
        let includedPage = try appDatabase.dbWriter.read { db in
            try TransactionQuery.paginate(db: db, filter: included)
        }
        XCTAssertEqual(Set(includedPage.items.map(\.id)), ["prefix", "contains", "uncat", "normal"])
    }

    // MARK: - manual_category precedence (NULLIF('') edge)

    func testManualCategoryEmptyStringFallsBackToCategory() throws {
        try appDatabase.dbWriter.write { db in
            try self.insertTxn(
                db, id: "t1", date: self.makeDate(2026, 1, 5), amount: -10,
                category: "groceries-ah", manualCategory: ""
            )
            try self.insertTxn(
                db, id: "t2", date: self.makeDate(2026, 1, 6), amount: -20,
                category: "groceries-ah", manualCategory: "shopping-special"
            )
        }

        // t1's manual_category is '' (falls back to "groceries-ah" via
        // NULLIF); t2's real manual override takes precedence.
        let groceries = TransactionFilter(categories: ["groceries"], includeTransfers: true)
        let groceriesPage = try appDatabase.dbWriter.read { db in
            try TransactionQuery.paginate(db: db, filter: groceries)
        }
        XCTAssertEqual(groceriesPage.items.map(\.id), ["t1"])

        let shopping = TransactionFilter(categories: ["shopping"], includeTransfers: true)
        let shoppingPage = try appDatabase.dbWriter.read { db in
            try TransactionQuery.paginate(db: db, filter: shopping)
        }
        XCTAssertEqual(shoppingPage.items.map(\.id), ["t2"])
    }

    // MARK: - Search against description_structured

    func testSearchMatchesDescriptionStructured() throws {
        try appDatabase.dbWriter.write { db in
            try self.insertTxn(
                db, id: "match", date: self.makeDate(2026, 1, 5), amount: -10,
                description: "Plain text", descriptionStructured: "{\"note\":\"findme123\"}"
            )
            try self.insertTxn(
                db, id: "nomatch", date: self.makeDate(2026, 1, 6), amount: -20,
                description: "Other", descriptionStructured: "{\"note\":\"nothing\"}"
            )
        }

        let filter = TransactionFilter(q: "findme123", includeTransfers: true)
        let page = try appDatabase.dbWriter.read { db in
            try TransactionQuery.paginate(db: db, filter: filter)
        }
        XCTAssertEqual(page.items.map(\.id), ["match"])
    }

    // MARK: - Absolute amount range

    func testAbsAmountRangeMatchesEitherSign() throws {
        try appDatabase.dbWriter.write { db in
            try self.insertTxn(db, id: "neg", date: self.makeDate(2026, 1, 5), amount: -15)
            try self.insertTxn(db, id: "pos", date: self.makeDate(2026, 1, 6), amount: 15)
            try self.insertTxn(db, id: "toosmall", date: self.makeDate(2026, 1, 7), amount: -1)
            try self.insertTxn(db, id: "toobig", date: self.makeDate(2026, 1, 8), amount: -100)
        }

        let filter = TransactionFilter(amountMin: 10, amountMax: 20, includeTransfers: true)
        let page = try appDatabase.dbWriter.read { db in
            try TransactionQuery.paginate(db: db, filter: filter)
        }
        XCTAssertEqual(Set(page.items.map(\.id)), ["neg", "pos"])
    }

    // MARK: - Sort stability / id tiebreak

    func testSortUsesIdAsTiebreakerInSameDirection() throws {
        let sameDate = makeDate(2026, 1, 10)
        try appDatabase.dbWriter.write { db in
            try self.insertTxn(db, id: "txn_a", date: sameDate, amount: -5)
            try self.insertTxn(db, id: "txn_b", date: sameDate, amount: -5)
            try self.insertTxn(db, id: "txn_c", date: sameDate, amount: -5)
        }

        let descFilter = TransactionFilter(includeTransfers: true, sort: .dateDesc)
        let descPage = try appDatabase.dbWriter.read { db in
            try TransactionQuery.paginate(db: db, filter: descFilter)
        }
        XCTAssertEqual(descPage.items.map(\.id), ["txn_c", "txn_b", "txn_a"])

        let ascFilter = TransactionFilter(includeTransfers: true, sort: .dateAsc)
        let ascPage = try appDatabase.dbWriter.read { db in
            try TransactionQuery.paginate(db: db, filter: ascFilter)
        }
        XCTAssertEqual(ascPage.items.map(\.id), ["txn_a", "txn_b", "txn_c"])
    }

    // MARK: - Pagination clamp

    func testPaginationClampsPageToMaxPage() throws {
        try appDatabase.dbWriter.write { db in
            for index in 1...5 {
                try self.insertTxn(
                    db, id: "t\(index)", date: self.makeDate(2026, 1, index), amount: -Double(index)
                )
            }
        }

        // 5 rows, page size 2 -> 3 pages; requesting page 99 clamps to 3.
        let filter = TransactionFilter(includeTransfers: true, page: 99)
        let page = try appDatabase.dbWriter.read { db in
            try TransactionQuery.paginate(db: db, filter: filter, pageSize: 2)
        }
        XCTAssertEqual(page.page, 3)
        XCTAssertEqual(page.total, 5)
        XCTAssertEqual(page.pages, 3)
        XCTAssertFalse(page.hasNext)
        XCTAssertTrue(page.hasPrev)
        // Last page holds the remainder (5 items / 2 per page -> 1 on page 3).
        XCTAssertEqual(page.items.count, 1)
    }

    // MARK: - Preset resolution sanity (TransactionFilter.resolvePresetRange)

    func testResolvePresetRangeThisMonthAndLastYear() {
        let today = makeDate(2026, 7, 14)

        let thisMonth = TransactionFilter.resolvePresetRange(.thisMonth, today: today)
        XCTAssertEqual(thisMonth.from, makeDate(2026, 7, 1))
        XCTAssertEqual(thisMonth.to, makeDate(2026, 7, 31))

        let lastYear = TransactionFilter.resolvePresetRange(.lastYear, today: today)
        XCTAssertEqual(lastYear.from, makeDate(2025, 1, 1))
        XCTAssertEqual(lastYear.to, makeDate(2025, 12, 31))

        // January edge: last-month wraps to December of the previous year.
        let january = makeDate(2026, 1, 15)
        let lastMonth = TransactionFilter.resolvePresetRange(.lastMonth, today: january)
        XCTAssertEqual(lastMonth.from, makeDate(2025, 12, 1))
        XCTAssertEqual(lastMonth.to, makeDate(2025, 12, 31))
    }
}
