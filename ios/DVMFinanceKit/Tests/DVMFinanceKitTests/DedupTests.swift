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

// MARK: - Duplicate detection by the end-to-end reference

/// Port of the reference-dedup group of `tests/test_dedup.py`.
///
/// The bank writes one SEPA payment in two description forms. The two forms
/// hold a different raw text, so the id of the two forms differs. Only the
/// reference joins them.
final class DedupReferenceTests: XCTestCase {
    var appDatabase: AppDatabase!

    static let taggedDescription =
        "/TRTP/SEPA INCASSO ALGEMEEN DOORLOPEND/CSID/VP20XNL847867841319 "
        + "/NAME/LEBARA/MARF/B0OXIVC5T2O3ZJ58/REMI/LEBARA NL-039442543-277 "
        + "/IBAN/NL65ADYB0257164544/BIC/ADYBNL2A/EREF/KFF5Q4D85TQK39G6"
    static let labelledDescription =
        "SEPA INCASSO ALGEMEEN DOORLOPEND INCASSANT: VP20XNL847867841319 "
        + "NAAM: LEBARA MACHTIGING: B0OXIVC5T2O3ZJ58 "
        + "OMSCHRIJVING: LEBARA NL-03944254 3-277 IBAN: NL65ADYB0257164544 "
        + "KENMERK: KFF5Q4D85TQK39G6"
    static let posDescription =
        "BEA, BETAALPAS                   JUMBO 123375,PAS603 "
        + "NR:97EX02, 30.05.24/17:07        DDUWAS EN KEE"

    override func setUpWithError() throws {
        appDatabase = try AppDatabase.inMemory()
    }

    override func tearDownWithError() throws {
        appDatabase = nil
    }

    private func makeDate() -> Date {
        var components = DateComponents()
        components.year = 2024
        components.month = 1
        components.day = 1
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        return calendar.date(from: components)!
    }

    /// Build a parsed transaction the way a parser hands one to the importer.
    private func parsed(_ description: String, amount: Double = -5.75) -> ParsedTransaction {
        ParsedTransaction(
            accountNumber: "720317081",
            transactiondate: makeDate(),
            amount: amount,
            description: description,
            descriptionStructured: DescriptionParser.parseTransactionDescription(description),
            currency: "EUR"
        )
    }

    // MARK: The stored column

    func testInsertStoresTheReference() throws {
        try appDatabase.dbWriter.write { db in
            try Dedup.insertTransactions(db: db, transactions: [parsed(Self.taggedDescription)])
        }

        let row = try appDatabase.dbWriter.read { db in
            try TransactionRecord.fetchOne(db)
        }
        XCTAssertEqual(row?.endToEndReference, "KFF5Q4D85TQK39G6")
    }

    func testInsertLeavesAPOSRowWithoutAReference() throws {
        try appDatabase.dbWriter.write { db in
            try Dedup.insertTransactions(db: db, transactions: [parsed(Self.posDescription)])
        }

        let row = try appDatabase.dbWriter.read { db in
            try TransactionRecord.fetchOne(db)
        }
        XCTAssertNil(row?.endToEndReference)
    }

    // MARK: The match

    /// The premise of the whole change: the id cannot join the two forms.
    func testTheTwoFormsHaveDifferentIDs() {
        let tagged = TransactionID.generateTransactionID(parsed(Self.taggedDescription))
        let labelled = TransactionID.generateTransactionID(parsed(Self.labelledDescription))
        XCTAssertNotEqual(tagged, labelled)
    }

    func testTheLabelledFormMatchesAStoredTaggedRow() throws {
        try appDatabase.dbWriter.write { db in
            try Dedup.insertTransactions(db: db, transactions: [parsed(Self.taggedDescription)])
        }

        let result = try appDatabase.dbWriter.read { db in
            try Dedup.checkDuplicates(db: db, transactions: [parsed(Self.labelledDescription)])
        }

        XCTAssertTrue(result.new.isEmpty)
        XCTAssertEqual(result.duplicates.count, 1)
    }

    func testTheTwoFormsInOneBatch() throws {
        let result = try appDatabase.dbWriter.read { db in
            try Dedup.checkDuplicates(
                db: db,
                transactions: [parsed(Self.taggedDescription), parsed(Self.labelledDescription)]
            )
        }

        XCTAssertEqual(result.new.count, 1)
        XCTAssertEqual(result.duplicates.count, 1)
    }

    /// The key holds the account, so two accounts do not collide.
    func testTwoAccountsKeepTheSameReference() throws {
        try appDatabase.dbWriter.write { db in
            try Dedup.insertTransactions(db: db, transactions: [parsed(Self.taggedDescription)])
        }

        var other = parsed(Self.labelledDescription)
        other.accountNumber = "123456789"
        let result = try appDatabase.dbWriter.read { db in
            try Dedup.checkDuplicates(db: db, transactions: [other])
        }

        XCTAssertEqual(result.new.count, 1)
        XCTAssertTrue(result.duplicates.isEmpty)
    }

    // MARK: The references that the check ignores

    func testNonrefDoesNotJoinTwoPayments() throws {
        let first = parsed(
            "/TRTP/SEPA OVERBOEKING/IBAN/NL65ADYB0257164544/NAME/A/REMI/one/EREF/NONREF"
        )
        let second = parsed(
            "/TRTP/SEPA OVERBOEKING/IBAN/NL65ADYB0257164544/NAME/B/REMI/two/EREF/NONREF",
            amount: -9.99
        )

        let result = try appDatabase.dbWriter.read { db in
            try Dedup.checkDuplicates(db: db, transactions: [first, second])
        }

        XCTAssertEqual(result.new.count, 2)
        XCTAssertTrue(result.duplicates.isEmpty)
    }

    func testTheHelperIgnoresAnEmptyReference() {
        let blank = ParsedTransaction(
            accountNumber: "720317081",
            descriptionStructured: "{\"end_to_end_reference\": \"   \"}"
        )
        XCTAssertNil(Dedup.extractEndToEndReference(blank))

        let none = ParsedTransaction(accountNumber: "720317081")
        XCTAssertNil(Dedup.extractEndToEndReference(none))
    }

    // MARK: The id does not change

    /// The reference is a match key, and not part of the id. A new id would
    /// make the next import write a second row, and the manual categorization
    /// of the first row would lose its transaction.
    func testTheIDIgnoresTheReference() {
        let without = ParsedTransaction(
            accountNumber: "720317081",
            transactiondate: makeDate(),
            amount: -5.75,
            description: Self.taggedDescription
        )
        let with = parsed(Self.taggedDescription)

        XCTAssertEqual(
            TransactionID.generateTransactionID(without),
            TransactionID.generateTransactionID(with)
        )
    }
}
