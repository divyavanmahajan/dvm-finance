import XCTest
import GRDB
@testable import DVMFinanceKit

/// Covers `TransactionMutations` — the port of `api/transactions.py`'s manual
/// category/tag set/clear endpoints. The subtle case (called out explicitly in
/// the plan) is that clearing one manual field resets
/// `categorization_source` to `nil` only when the *other* manual field is also
/// empty; these tests pin that both ways round.
final class TransactionMutationsTests: XCTestCase {

    private func makeDatabaseWithTransaction(
        category: String? = "rule-cat",
        tags: String? = "rule-tag",
        categorizationSource: String? = "5"
    ) throws -> AppDatabase {
        let appDatabase = try AppDatabase.inMemory()
        try appDatabase.dbWriter.write { db in
            var t = TransactionRecord(
                id: "t1",
                accountNumber: "NL91",
                transactiondate: DatabaseDateFormat.dateOnly.date(from: "2026-01-15")!,
                amount: Decimal(string: "-12.30")!,
                description: "BEA Albert Heijn",
                category: category,
                tags: tags,
                categorizationSource: categorizationSource,
                currency: "EUR"
            )
            try t.insert(db)
        }
        return appDatabase
    }

    private func fetch(_ appDatabase: AppDatabase) throws -> TransactionRecord {
        try appDatabase.dbWriter.read { db in
            try XCTUnwrap(try TransactionRecord.fetchOne(db, key: "t1"))
        }
    }

    // MARK: - set

    func testSetManualCategoryNormalizesAndPinsManualSource() throws {
        let appDatabase = try makeDatabaseWithTransaction()
        try appDatabase.dbWriter.write { db in
            _ = try TransactionMutations.setManualCategory(db: db, transactionId: "t1", manualCategory: "  Groceries , Food ")
        }
        let t = try fetch(appDatabase)
        // normalize_category: lowercased, trimmed, comma-rejoined.
        XCTAssertEqual(t.manualCategory, "groceries, food")
        XCTAssertEqual(t.categorizationSource, "manual")
        XCTAssertNotNil(t.updatedAt, "set stamps updated_at")
        XCTAssertEqual(t.effectiveCategory, "groceries, food")
    }

    func testSetManualTagsPreservesCaseAndPinsManualSource() throws {
        let appDatabase = try makeDatabaseWithTransaction()
        try appDatabase.dbWriter.write { db in
            _ = try TransactionMutations.setManualTags(db: db, transactionId: "t1", manualTags: " Travel , ,Work ")
        }
        let t = try fetch(appDatabase)
        // set_manual_tags does NOT lowercase (unlike categories); empties dropped.
        XCTAssertEqual(t.manualTags, "Travel, Work")
        XCTAssertEqual(t.categorizationSource, "manual")
        XCTAssertNotNil(t.updatedAt)
    }

    func testSetManualCategoryBlankClearsToNil() throws {
        let appDatabase = try makeDatabaseWithTransaction()
        try appDatabase.dbWriter.write { db in
            _ = try TransactionMutations.setManualCategory(db: db, transactionId: "t1", manualCategory: "   ")
        }
        let t = try fetch(appDatabase)
        XCTAssertNil(t.manualCategory, "blank input normalizes to nil")
        // Still pins manual source (matches desktop set_manual_category exactly).
        XCTAssertEqual(t.categorizationSource, "manual")
    }

    // MARK: - clear: source reset only when BOTH manual fields empty

    func testClearManualCategoryResetsSourceWhenNoManualTags() throws {
        let appDatabase = try makeDatabaseWithTransaction()
        try appDatabase.dbWriter.write { db in
            _ = try TransactionMutations.setManualCategory(db: db, transactionId: "t1", manualCategory: "groceries")
            _ = try TransactionMutations.clearManualCategory(db: db, transactionId: "t1")
        }
        let t = try fetch(appDatabase)
        XCTAssertNil(t.manualCategory)
        XCTAssertNil(t.categorizationSource, "source reset: no manual tags remain")
        XCTAssertEqual(t.effectiveCategory, "rule-cat", "rule value restored as effective")
    }

    func testClearManualCategoryKeepsManualSourceWhenManualTagsRemain() throws {
        let appDatabase = try makeDatabaseWithTransaction()
        try appDatabase.dbWriter.write { db in
            _ = try TransactionMutations.setManualCategory(db: db, transactionId: "t1", manualCategory: "groceries")
            _ = try TransactionMutations.setManualTags(db: db, transactionId: "t1", manualTags: "travel")
            _ = try TransactionMutations.clearManualCategory(db: db, transactionId: "t1")
        }
        let t = try fetch(appDatabase)
        XCTAssertNil(t.manualCategory)
        XCTAssertEqual(t.manualTags, "travel")
        XCTAssertEqual(t.categorizationSource, "manual", "manual tags keep the source manual")
    }

    func testClearManualTagsResetsSourceWhenNoManualCategory() throws {
        let appDatabase = try makeDatabaseWithTransaction()
        try appDatabase.dbWriter.write { db in
            _ = try TransactionMutations.setManualTags(db: db, transactionId: "t1", manualTags: "travel")
            _ = try TransactionMutations.clearManualTags(db: db, transactionId: "t1")
        }
        let t = try fetch(appDatabase)
        XCTAssertNil(t.manualTags)
        XCTAssertNil(t.categorizationSource, "source reset: no manual category remains")
    }

    func testClearManualTagsKeepsManualSourceWhenManualCategoryRemains() throws {
        let appDatabase = try makeDatabaseWithTransaction()
        try appDatabase.dbWriter.write { db in
            _ = try TransactionMutations.setManualTags(db: db, transactionId: "t1", manualTags: "travel")
            _ = try TransactionMutations.setManualCategory(db: db, transactionId: "t1", manualCategory: "groceries")
            _ = try TransactionMutations.clearManualTags(db: db, transactionId: "t1")
        }
        let t = try fetch(appDatabase)
        XCTAssertNil(t.manualTags)
        XCTAssertEqual(t.manualCategory, "groceries")
        XCTAssertEqual(t.categorizationSource, "manual", "manual category keeps the source manual")
    }

    // MARK: - clear when source was already a rule id (not "manual")

    func testClearManualCategoryLeavesRuleSourceUntouched() throws {
        // source is a rule id ("5"), no manual fields: clearing category must
        // not touch the rule source (desktop only nils it when it was "manual").
        let appDatabase = try makeDatabaseWithTransaction(categorizationSource: "5")
        try appDatabase.dbWriter.write { db in
            _ = try TransactionMutations.clearManualCategory(db: db, transactionId: "t1")
        }
        let t = try fetch(appDatabase)
        XCTAssertEqual(t.categorizationSource, "5", "rule source preserved when it was never manual")
    }
}
