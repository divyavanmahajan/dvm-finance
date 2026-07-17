import XCTest
import GRDB
@testable import DVMFinanceKit

/// Covers Phase A's acceptance criteria (`ios/docs/plan.md` "Phase A"):
/// record types round-trip through an in-memory GRDB database, and column
/// names/constraints match `core/models.py` exactly.
final class DatabaseTests: XCTestCase {
    var appDatabase: AppDatabase!

    override func setUpWithError() throws {
        appDatabase = try AppDatabase.inMemory()
    }

    override func tearDownWithError() throws {
        appDatabase = nil
    }

    // MARK: - Migration

    func testMigratorCreatesAllTables() throws {
        try appDatabase.dbWriter.read { db in
            let expectedTables = [
                "transactions",
                "categorization_rules",
                "rule_conditions",
                "budgets",
                "rule_change_reports",
                "rule_change_items",
                "snapshot_imports",
            ]
            for table in expectedTables {
                XCTAssertTrue(try db.tableExists(table), "missing table \(table)")
            }
            XCTAssertFalse(
                try db.tableExists("download_state"),
                "download_state must not be ported (spec.md: no downloads on iOS)"
            )
        }
    }

    // MARK: - Transaction round-trip

    func testTransactionRoundTrip() throws {
        let record = TransactionRecord(
            id: "NL00ABNA0000000000_2026-07-13_12.30_abcdef0123456789",
            accountNumber: "NL00ABNA0000000000",
            mutationcode: "BA",
            transactiondate: makeDate(2026, 7, 13),
            valuedate: makeDate(2026, 7, 14),
            startsaldo: Decimal(string: "100.00"),
            endsaldo: Decimal(string: "112.30"),
            amount: Decimal(string: "12.30")!,
            description: "Test payment",
            descriptionStructured: "{\"IBAN\":\"NL00ABNA0000000000\"}",
            category: "groceries-ah",
            manualCategory: nil,
            tags: "food",
            manualTags: nil,
            categorizationSource: "1",
            currency: "EUR",
            sourceFile: "statement.csv",
            sourceLine: 3,
            transactionTypeCode: "BEA",
            transactionReference: "REF123",
            transactionHash: "deadbeef"
        )

        try appDatabase.dbWriter.write { db in
            try record.insert(db)
        }

        let fetched = try appDatabase.dbWriter.read { db in
            try TransactionRecord.fetchOne(db, key: record.id)
        }

        XCTAssertEqual(fetched, record)
        XCTAssertEqual(fetched?.transactiondate, makeDate(2026, 7, 13))
        XCTAssertEqual(fetched?.startsaldo, Decimal(string: "100.00"))
        XCTAssertEqual(fetched?.amount, Decimal(string: "12.30"))
        XCTAssertEqual(fetched?.effectiveCategory, "groceries-ah")
    }

    func testTransactionRoundTripWithNilOptionals() throws {
        let record = TransactionRecord(
            id: "acct_2026-01-01_0.00_0000000000000000",
            accountNumber: "acct",
            transactiondate: makeDate(2026, 1, 1),
            amount: Decimal(string: "0.00")!
        )

        try appDatabase.dbWriter.write { db in try record.insert(db) }
        let fetched = try appDatabase.dbWriter.read { db in
            try TransactionRecord.fetchOne(db, key: record.id)
        }

        XCTAssertEqual(fetched, record)
        XCTAssertNil(fetched?.valuedate)
        XCTAssertNil(fetched?.startsaldo)
        XCTAssertNil(fetched?.endsaldo)
        XCTAssertNil(fetched?.category)
        XCTAssertNil(fetched?.manualCategory)
        XCTAssertEqual(fetched?.currency, "EUR", "currency default must survive round-trip")
    }

    /// Manual category takes precedence over rule-assigned category — the
    /// invariant this record's `effectiveCategory` exists to enforce
    /// (spec.md "Key invariants"; `CLAUDE.md` "Manual edits are sacred").
    func testEffectiveCategoryPrefersManual() {
        let record = TransactionRecord(
            id: "x",
            accountNumber: "acct",
            transactiondate: makeDate(2026, 1, 1),
            amount: Decimal(string: "1.00")!,
            category: "groceries-ah",
            manualCategory: "fixed-insurance-life"
        )
        XCTAssertEqual(record.effectiveCategory, "fixed-insurance-life")
    }

    // MARK: - CategorizationRule + RuleCondition round-trip / cascade

    func testCategorizationRuleRoundTrip() throws {
        var rule = CategorizationRuleRecord(
            ruleType: "structured_field",
            matchPattern: "contains",
            fieldTarget: "IBAN",
            matchValue: "NL00ABNA0000000000",
            category: "groceries-ah",
            tags: "food,recurring",
            filterAccount: "NL00ABNA0000000000",
            filterCurrency: "EUR",
            filterDateFrom: makeDate(2026, 1, 1),
            filterDateTo: makeDate(2026, 12, 31)
        )

        try appDatabase.dbWriter.write { db in
            try rule.insert(db)
        }

        let ruleId = try XCTUnwrap(rule.id, "didInsert(_:) must capture the autoincrement rowid")

        let fetched = try appDatabase.dbWriter.read { db in
            try CategorizationRuleRecord.fetchOne(db, key: ruleId)
        }
        XCTAssertEqual(fetched, rule)
        XCTAssertEqual(fetched?.filterDateFrom, makeDate(2026, 1, 1))
        XCTAssertEqual(fetched?.isActive, true)
        XCTAssertEqual(fetched?.isTagOnly, false)
    }

    func testRuleUuidUniqueConstraint() throws {
        let sharedUUID = UUID().uuidString
        var first = CategorizationRuleRecord(
            uuid: sharedUUID,
            ruleType: "full_description",
            matchPattern: "contains",
            matchValue: "foo"
        )
        var second = CategorizationRuleRecord(
            uuid: sharedUUID,
            ruleType: "full_description",
            matchPattern: "contains",
            matchValue: "bar"
        )

        try appDatabase.dbWriter.write { db in try first.insert(db) }

        XCTAssertThrowsError(try appDatabase.dbWriter.write { db in try second.insert(db) }) { error in
            guard let dbError = error as? DatabaseError else {
                XCTFail("expected DatabaseError, got \(error)")
                return
            }
            XCTAssertEqual(dbError.resultCode, .SQLITE_CONSTRAINT)
        }
    }

    func testRuleConditionCascadeDelete() throws {
        var rule = CategorizationRuleRecord(
            ruleType: "full_description",
            matchPattern: "contains",
            matchValue: "foo"
        )
        try appDatabase.dbWriter.write { db in try rule.insert(db) }
        let ruleId = try XCTUnwrap(rule.id)

        var condition = RuleConditionRecord(
            ruleId: ruleId,
            fieldTarget: "description",
            matchPattern: "contains",
            matchValue: "bar",
            operatorValue: "OR",
            sortOrder: 1
        )
        try appDatabase.dbWriter.write { db in try condition.insert(db) }
        let conditionId = try XCTUnwrap(condition.id)

        let fetchedCondition = try appDatabase.dbWriter.read { db in
            try RuleConditionRecord.fetchOne(db, key: conditionId)
        }
        XCTAssertEqual(fetchedCondition, condition)

        try appDatabase.dbWriter.write { db in
            _ = try CategorizationRuleRecord.deleteOne(db, key: ruleId)
        }

        let remaining = try appDatabase.dbWriter.read { db in
            try RuleConditionRecord.fetchCount(db)
        }
        XCTAssertEqual(remaining, 0, "rule_conditions must cascade-delete with their rule")
    }

    // MARK: - Budget round-trip / unique constraint

    func testBudgetRoundTrip() throws {
        var budget = BudgetRecord(
            category: "groceries",
            amount: Decimal(string: "400.00")!,
            period: "monthly",
            startDate: makeDate(2026, 1, 1),
            endDate: nil,
            notes: "household groceries",
            createdAt: makeDate(2026, 1, 1),
            updatedAt: makeDate(2026, 1, 1)
        )
        try appDatabase.dbWriter.write { db in try budget.insert(db) }
        let budgetId = try XCTUnwrap(budget.id)

        let fetched = try appDatabase.dbWriter.read { db in
            try BudgetRecord.fetchOne(db, key: budgetId)
        }
        XCTAssertEqual(fetched, budget)
        XCTAssertNil(fetched?.endDate)
    }

    func testBudgetCategoryPeriodUniqueConstraint() throws {
        var first = BudgetRecord(category: "groceries", amount: Decimal(string: "100.00")!, period: "monthly")
        var second = BudgetRecord(category: "groceries", amount: Decimal(string: "200.00")!, period: "monthly")

        try appDatabase.dbWriter.write { db in try first.insert(db) }

        XCTAssertThrowsError(try appDatabase.dbWriter.write { db in try second.insert(db) }) { error in
            guard let dbError = error as? DatabaseError else {
                XCTFail("expected DatabaseError, got \(error)")
                return
            }
            XCTAssertEqual(dbError.resultCode, .SQLITE_CONSTRAINT)
        }
    }

    func testBudgetSameCategoryDifferentPeriodAllowed() throws {
        var monthly = BudgetRecord(category: "groceries", amount: Decimal(string: "100.00")!, period: "monthly")
        var yearly = BudgetRecord(category: "groceries", amount: Decimal(string: "1200.00")!, period: "yearly")

        try appDatabase.dbWriter.write { db in
            try monthly.insert(db)
            try yearly.insert(db)
        }

        let count = try appDatabase.dbWriter.read { db in try BudgetRecord.fetchCount(db) }
        XCTAssertEqual(count, 2)
    }

    // MARK: - RuleChangeReport + RuleChangeItem round-trip / cascade

    func testRuleChangeReportRoundTripAndCascadeDelete() throws {
        var report = RuleChangeReportRecord(
            createdAt: makeDateTime(2026, 7, 13, 10, 30, 0),
            ruleId: 1,
            ruleUuid: UUID().uuidString,
            action: "import",
            ruleBefore: nil,
            ruleAfter: nil,
            summary: "{\"imported\":3}"
        )
        try appDatabase.dbWriter.write { db in try report.insert(db) }
        let reportId = try XCTUnwrap(report.id)

        let fetched = try appDatabase.dbWriter.read { db in
            try RuleChangeReportRecord.fetchOne(db, key: reportId)
        }
        XCTAssertEqual(fetched, report)
        XCTAssertEqual(fetched?.createdAt, makeDateTime(2026, 7, 13, 10, 30, 0))
        XCTAssertEqual(fetched?.summaryDictionary?["imported"] as? Int, 3)

        var item = RuleChangeItemRecord(
            reportId: reportId,
            transactionId: "txn-1",
            oldCategory: nil,
            newCategory: "groceries-ah",
            oldTags: nil,
            newTags: "food"
        )
        try appDatabase.dbWriter.write { db in try item.insert(db) }
        XCTAssertNotNil(item.id)

        try appDatabase.dbWriter.write { db in
            _ = try RuleChangeReportRecord.deleteOne(db, key: reportId)
        }

        let remaining = try appDatabase.dbWriter.read { db in
            try RuleChangeItemRecord.fetchCount(db)
        }
        XCTAssertEqual(remaining, 0, "rule_change_items must cascade-delete with their report")
    }

    // MARK: - SnapshotImport round-trip

    func testSnapshotImportRoundTrip() throws {
        var snapshotImport = SnapshotImportRecord(
            createdAt: makeDateTime(2026, 7, 13, 9, 0, 0),
            sourceMachineId: UUID().uuidString,
            schemaVersion: 1,
            counts: "{\"transactions\":10}",
            overwrites: nil
        )
        try appDatabase.dbWriter.write { db in try snapshotImport.insert(db) }
        let importId = try XCTUnwrap(snapshotImport.id)

        let fetched = try appDatabase.dbWriter.read { db in
            try SnapshotImportRecord.fetchOne(db, key: importId)
        }
        XCTAssertEqual(fetched, snapshotImport)
        XCTAssertNil(fetched?.overwrites)
        XCTAssertEqual(fetched?.countsDictionary?["transactions"] as? Int, 10)
    }

    // MARK: - Helpers

    private func makeDate(_ year: Int, _ month: Int, _ day: Int) -> Date {
        var components = DateComponents()
        components.year = year
        components.month = month
        components.day = day
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        return calendar.date(from: components)!
    }

    private func makeDateTime(
        _ year: Int, _ month: Int, _ day: Int,
        _ hour: Int, _ minute: Int, _ second: Int
    ) -> Date {
        var components = DateComponents()
        components.year = year
        components.month = month
        components.day = day
        components.hour = hour
        components.minute = minute
        components.second = second
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        return calendar.date(from: components)!
    }
}
