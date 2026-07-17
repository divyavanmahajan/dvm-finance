import XCTest
import GRDB
@testable import DVMFinanceKit

/// Covers `ios/docs/plan.md` "Phase B" dedup acceptance: in-batch duplicate
/// handling, existing-id duplicate detection against the DB, and upsert
/// idempotency — port of `core/dedup.py:check_duplicates`/`insert_transactions`.
final class DedupTests: XCTestCase {
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

    private func makeTransaction(
        account: String = "NL91ABNA0417164300",
        date: Date? = nil,
        amount: Double = -12.30,
        description: String = "Albert Heijn 1234"
    ) -> ParsedTransaction {
        ParsedTransaction(
            accountNumber: account,
            transactiondate: date ?? makeDate(2026, 1, 15),
            amount: amount,
            description: description,
            currency: "EUR"
        )
    }

    // MARK: - checkDuplicates: in-batch

    func testInBatchDuplicateFirstOccurrenceWins() throws {
        let first = makeTransaction(description: "Same description")
        let duplicate = makeTransaction(description: "Same description")
        let distinct = makeTransaction(description: "Different description")

        try appDatabase.dbWriter.read { db in
            let result = try Dedup.checkDuplicates(db: db, transactions: [first, duplicate, distinct])
            XCTAssertEqual(result.new.count, 2)
            XCTAssertEqual(result.duplicates.count, 1)
            XCTAssertEqual(result.duplicates.first?.description, "Same description")
        }
    }

    // MARK: - checkDuplicates: existing DB id

    func testExistingIDIsDetectedAsDuplicate() throws {
        let transaction = makeTransaction()

        try appDatabase.dbWriter.write { db in
            try Dedup.insertTransactions(db: db, transactions: [transaction])
        }

        try appDatabase.dbWriter.read { db in
            let result = try Dedup.checkDuplicates(db: db, transactions: [transaction])
            XCTAssertEqual(result.new.count, 0)
            XCTAssertEqual(result.duplicates.count, 1)
        }
    }

    func testNewTransactionIsNotADuplicate() throws {
        let existing = makeTransaction(description: "Existing")
        let incoming = makeTransaction(description: "Brand new")

        try appDatabase.dbWriter.write { db in
            try Dedup.insertTransactions(db: db, transactions: [existing])
        }

        try appDatabase.dbWriter.read { db in
            let result = try Dedup.checkDuplicates(db: db, transactions: [incoming])
            XCTAssertEqual(result.new.count, 1)
            XCTAssertEqual(result.duplicates.count, 0)
        }
    }

    // MARK: - insertTransactions: upsert idempotency

    func testReInsertingSameTransactionIsIdempotent() throws {
        let transaction = makeTransaction()

        try appDatabase.dbWriter.write { db in
            try Dedup.insertTransactions(db: db, transactions: [transaction, transaction])
        }

        let count = try appDatabase.dbWriter.read { db in
            try TransactionRecord.fetchCount(db)
        }
        XCTAssertEqual(count, 1, "exact duplicates must be absorbed by upsert (merge) semantics")
    }

    func testReInsertOverwritesFields() throws {
        var transaction = makeTransaction()
        transaction.category = "Groceries"
        transaction.tags = "food"

        try appDatabase.dbWriter.write { db in
            try Dedup.insertTransactions(db: db, transactions: [transaction])
        }

        transaction.category = "Updated-Category"
        transaction.tags = "updated"

        try appDatabase.dbWriter.write { db in
            try Dedup.insertTransactions(db: db, transactions: [transaction])
        }

        let id = TransactionID.generateTransactionID(transaction)
        let fetched = try appDatabase.dbWriter.read { db in
            try TransactionRecord.fetchOne(db, key: id)
        }
        XCTAssertEqual(fetched?.category, "updated-category")
        XCTAssertEqual(fetched?.tags, "updated")

        let count = try appDatabase.dbWriter.read { db in try TransactionRecord.fetchCount(db) }
        XCTAssertEqual(count, 1)
    }

    // MARK: - insertTransactions: normalization + defaults

    func testInsertNormalizesCategoryAndDefaultsCurrency() throws {
        var transaction = makeTransaction()
        transaction.category = "  Groceries, Food  "
        transaction.currency = nil

        try appDatabase.dbWriter.write { db in
            try Dedup.insertTransactions(db: db, transactions: [transaction])
        }

        let id = TransactionID.generateTransactionID(transaction)
        let fetched = try appDatabase.dbWriter.read { db in
            try TransactionRecord.fetchOne(db, key: id)
        }
        XCTAssertEqual(fetched?.category, "groceries, food")
        XCTAssertEqual(fetched?.currency, "EUR")
    }

    /// Port of Python's `normalize_category(x) or x`: a category that
    /// normalizes to `nil` (e.g. all-comma input) falls back to the *raw*
    /// value rather than being dropped.
    func testCategoryThatNormalizesToNilFallsBackToRawValue() throws {
        var transaction = makeTransaction()
        transaction.category = ", ,"

        try appDatabase.dbWriter.write { db in
            try Dedup.insertTransactions(db: db, transactions: [transaction])
        }

        let id = TransactionID.generateTransactionID(transaction)
        let fetched = try appDatabase.dbWriter.read { db in
            try TransactionRecord.fetchOne(db, key: id)
        }
        XCTAssertEqual(fetched?.category, ", ,", "normalize_category(x) or x must keep the raw value")
    }

    func testInsertReturnsWrittenIDsInOrder() throws {
        let first = makeTransaction(description: "First")
        let second = makeTransaction(description: "Second")

        let ids = try appDatabase.dbWriter.write { db in
            try Dedup.insertTransactions(db: db, transactions: [first, second])
        }

        XCTAssertEqual(ids, [
            TransactionID.generateTransactionID(first),
            TransactionID.generateTransactionID(second),
        ])
    }

    func testInsertThrowsOnMissingTransactionDate() throws {
        let transaction = ParsedTransaction(accountNumber: "acct", transactiondate: nil, amount: 1.0)
        XCTAssertThrowsError(
            try appDatabase.dbWriter.write { db in
                try Dedup.insertTransactions(db: db, transactions: [transaction])
            }
        ) { error in
            XCTAssertEqual(error as? Dedup.DedupError, .missingTransactionDate)
        }
    }
}
