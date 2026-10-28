import XCTest
import GRDB
@testable import DVMFinanceKit

/// Covers `ManualTransactions` — the port of the desktop `manual-transactions`
/// capability of the change `add-manual-transactions`
/// (`core/manual_txn.py`: the create, the edit, the flag, the
/// restore, and the purge), plus the shared exclusion predicate
/// `core/filters.py:live_only` in its three readers.
final class ManualTransactionsTests: XCTestCase {

    private func makeDatabase() throws -> AppDatabase {
        try AppDatabase.inMemory()
    }

    private func date(_ value: String) throws -> Date {
        try XCTUnwrap(DatabaseDateFormat.dateOnly.date(from: value))
    }

    /// An imported row, with the content-derived id the file import gives it.
    @discardableResult
    private func insertImported(
        _ appDatabase: AppDatabase,
        id: String = "NL91_2026-03-02_-9.99_abc",
        amount: String = "-9.99",
        category: String? = "groceries",
        day: String = "2026-03-02"
    ) throws -> TransactionRecord {
        let record = TransactionRecord(
            id: id,
            accountNumber: "NL91",
            transactiondate: try date(day),
            amount: Decimal(string: amount)!,
            description: "Imported row",
            category: category
        )
        try appDatabase.dbWriter.write { db in try record.insert(db) }
        return record
    }

    private func fetch(_ appDatabase: AppDatabase, _ id: String) throws -> TransactionRecord {
        try appDatabase.dbWriter.read { db in
            try XCTUnwrap(try TransactionRecord.fetchOne(db, key: id))
        }
    }

    private func makeTempDirectory() throws -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("manual-txn-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    // MARK: - 8.1 Migration

    /// A database that an earlier version of the app wrote holds schema `v2`
    /// and no `is_manual`/`deleted_at` column. The `v3` migration must run
    /// against it, and each existing row must read as imported and live.
    /// Mirrors the Alembic revision
    /// `b3c1f0a27d44_add_manual_transaction_columns`.
    func testMigrationV3RunsAgainstAnOlderDatabase() throws {
        var configuration = Configuration()
        configuration.foreignKeysEnabled = true
        let dbQueue = try DatabaseQueue(configuration: configuration)

        // Step 1: the schema an earlier version of the app wrote.
        try AppDatabase.makeMigrator().migrate(dbQueue, upTo: "v2")
        try dbQueue.read { db in
            XCTAssertFalse(try db.columns(in: "transactions").contains { $0.name == "is_manual" })
            XCTAssertFalse(try db.columns(in: "transactions").contains { $0.name == "deleted_at" })
        }
        try dbQueue.write { db in
            try db.execute(
                sql: """
                    INSERT INTO transactions (id, accountNumber, transactiondate, amount, currency)
                    VALUES ('old-row', 'NL91', '2026-01-05', '-5.00', 'EUR')
                    """
            )
        }

        // Step 2: the new version opens the same database.
        let appDatabase = try AppDatabase(dbQueue)
        let record = try fetch(appDatabase, "old-row")
        XCTAssertFalse(record.isManual, "a row of an older database reads as imported")
        XCTAssertNil(record.deletedAt, "a row of an older database reads as live")
        XCTAssertFalse(record.isFlagged)
    }

    // MARK: - 8.3 Create

    /// Port of the scenario "The user records a cash payment on the phone"
    /// (`core/manual_txn.py:create_manual_transaction`).
    func testCreateWritesUUIDIdAndCashAccount() throws {
        let appDatabase = try makeDatabase()
        let created = try appDatabase.dbWriter.write { db in
            try ManualTransactions.create(
                db: db,
                input: ManualTransactions.Input(
                    date: try self.date("2026-04-07"),
                    amount: Decimal(string: "-20.00"),
                    description: "Market",
                    category: " Groceries ",
                    tags: " Cash , ,Market "
                )
            )
        }

        XCTAssertEqual(created.accountNumber, "CASH")
        XCTAssertEqual(UUID(uuidString: created.id)?.uuidString, created.id, "the id is a UUID")
        XCTAssertTrue(created.isManual)
        XCTAssertNil(created.deletedAt)
        // The typed category is a manual category; the typed tags are manual
        // tags. The category pass therefore skips the row.
        XCTAssertEqual(created.manualCategory, "groceries")
        XCTAssertEqual(created.manualTags, "Cash, Market", "tags keep their case")
        XCTAssertNil(created.category)
        XCTAssertNil(created.tags)
        XCTAssertEqual(created.categorizationSource, Categorizer.manualSource)
        XCTAssertNotNil(created.updatedAt)
        XCTAssertEqual(
            created.transactionHash,
            CoreNormalize.calculateTransactionHash(
                date: try date("2026-04-07"),
                description: "Market",
                amount: CoreNormalize.HashAmountInput(Decimal(string: "-20.00")),
                account: "CASH"
            ),
            "the stored hash is the hash of the content"
        )

        let stored = try fetch(appDatabase, created.id)
        XCTAssertEqual(stored, created)
    }

    /// Port of the scenario "The form holds no amount": the app refuses the
    /// form, names the missing amount, and writes nothing.
    func testCreateRefusesAFormWithoutAnAmount() throws {
        let appDatabase = try makeDatabase()
        XCTAssertThrowsError(
            try appDatabase.dbWriter.write { db in
                try ManualTransactions.create(
                    db: db,
                    input: ManualTransactions.Input(
                        date: try self.date("2026-04-07"),
                        amount: nil,
                        description: "Market"
                    )
                )
            }
        ) { error in
            XCTAssertEqual(
                error as? ManualTransactions.ManualTransactionError,
                .missingAmount
            )
        }
        let count = try appDatabase.dbWriter.read { db in try TransactionRecord.fetchCount(db) }
        XCTAssertEqual(count, 0, "the app writes nothing")
    }

    func testCreateRefusesAFormWithoutADateAndAnAmountOfZero() throws {
        let appDatabase = try makeDatabase()
        XCTAssertThrowsError(
            try appDatabase.dbWriter.write { db in
                try ManualTransactions.create(
                    db: db,
                    input: ManualTransactions.Input(amount: Decimal(string: "-1.00"), description: "x")
                )
            }
        ) { error in
            XCTAssertEqual(error as? ManualTransactions.ManualTransactionError, .missingDate)
        }
        XCTAssertThrowsError(
            try appDatabase.dbWriter.write { db in
                try ManualTransactions.create(
                    db: db,
                    input: ManualTransactions.Input(
                        date: try self.date("2026-04-07"),
                        amount: Decimal(0),
                        description: "x"
                    )
                )
            }
        ) { error in
            XCTAssertEqual(error as? ManualTransactions.ManualTransactionError, .zeroAmount)
        }
        let count = try appDatabase.dbWriter.read { db in try TransactionRecord.fetchCount(db) }
        XCTAssertEqual(count, 0)
    }

    /// Port of the scenario "The user creates a row and then imports a file":
    /// the rules run after a later import, and the category of the
    /// hand-entered row does not change. The row carries
    /// `categorization_source = "manual"`, so the category pass of
    /// `core/categorizer.py:apply_rules` skips it.
    func testTheCategoryPassSkipsAHandEnteredRow() throws {
        let appDatabase = try makeDatabase()
        let created = try appDatabase.dbWriter.write { db -> TransactionRecord in
            var rule = CategorizationRuleRecord(
                ruleType: "full_description",
                matchPattern: "contains",
                fieldTarget: "description",
                matchValue: "market",
                category: "rule-wins"
            )
            try rule.insert(db)
            return try ManualTransactions.create(
                db: db,
                input: ManualTransactions.Input(
                    date: try self.date("2026-04-07"),
                    amount: Decimal(string: "-20.00"),
                    description: "Market",
                    category: "groceries"
                )
            )
        }

        try appDatabase.dbWriter.write { db in
            try Categorizer.applyRules(db: db, transactionIds: [created.id])
        }

        let after = try fetch(appDatabase, created.id)
        XCTAssertEqual(after.manualCategory, "groceries")
        XCTAssertNil(after.category, "the rule pass does not write a category over a manual one")
        XCTAssertEqual(TransactionQuery.effectiveCategory(after), "groceries")
    }

    /// Port of the scenario "Both devices create a cash row": each device
    /// mints its own UUID, so two rows with the same date, amount, and
    /// description both exist.
    func testTwoHandEnteredRowsWithEqualValuesBothExist() throws {
        let appDatabase = try makeDatabase()
        let input = ManualTransactions.Input(
            date: try date("2026-04-07"),
            amount: Decimal(string: "-20.00"),
            description: "Market"
        )
        let first = try appDatabase.dbWriter.write { db in
            try ManualTransactions.create(db: db, input: input)
        }
        let second = try appDatabase.dbWriter.write { db in
            try ManualTransactions.create(db: db, input: input)
        }
        XCTAssertNotEqual(first.id, second.id)
        let count = try appDatabase.dbWriter.read { db in try TransactionRecord.fetchCount(db) }
        XCTAssertEqual(count, 2)
    }

    // MARK: - 8.4 Edit

    /// Port of the scenario "The user corrects an amount on the phone": the
    /// row keeps its id, and a delta export carries the new amount.
    func testEditKeepsTheIdAndStampsTheRow() throws {
        let appDatabase = try makeDatabase()
        let created = try appDatabase.dbWriter.write { db in
            try ManualTransactions.create(
                db: db,
                input: ManualTransactions.Input(
                    date: try self.date("2026-04-07"),
                    amount: Decimal(string: "-20.00"),
                    description: "Market",
                    category: "groceries"
                )
            )
        }

        let edited = try appDatabase.dbWriter.write { db in
            try ManualTransactions.edit(
                db: db,
                transactionId: created.id,
                input: ManualTransactions.Input(
                    date: try self.date("2026-04-08"),
                    amount: Decimal(string: "-24.50"),
                    description: "Market stall",
                    category: "groceries-market",
                    tags: "cash"
                )
            )
        }

        XCTAssertEqual(edited.id, created.id, "the row keeps its id")
        XCTAssertEqual(edited.amount, Decimal(string: "-24.50"))
        XCTAssertEqual(edited.description, "Market stall")
        XCTAssertEqual(edited.manualCategory, "groceries-market")
        XCTAssertEqual(edited.manualTags, "cash")
        XCTAssertEqual(edited.categorizationSource, Categorizer.manualSource)
        XCTAssertNotNil(edited.updatedAt, "the edit stamps the row, so a delta export carries it")
        XCTAssertNotEqual(
            edited.transactionHash, created.transactionHash,
            "the edit recomputes the content hash"
        )

        let count = try appDatabase.dbWriter.read { db in try TransactionRecord.fetchCount(db) }
        XCTAssertEqual(count, 1, "the edit writes no second row")
    }

    /// Port of the scenario "The user opens an imported transaction": the app
    /// refuses the edit and offers the category and the tag functions only.
    func testEditRefusesAnImportedRow() throws {
        let appDatabase = try makeDatabase()
        let imported = try insertImported(appDatabase)
        XCTAssertThrowsError(
            try appDatabase.dbWriter.write { db in
                try ManualTransactions.edit(
                    db: db,
                    transactionId: imported.id,
                    input: ManualTransactions.Input(
                        date: try self.date("2026-04-08"),
                        amount: Decimal(string: "-1.00"),
                        description: "changed"
                    )
                )
            }
        ) { error in
            XCTAssertEqual(
                error as? ManualTransactions.ManualTransactionError,
                .notHandEntered(imported.id)
            )
        }
        let after = try fetch(appDatabase, imported.id)
        XCTAssertEqual(after.description, "Imported row", "the imported row does not change")
    }

    // MARK: - 8.5 Flag and restore

    /// Port of the scenario "The user flags a row on the phone": the row
    /// stays in the local database, and it holds the time of the flag.
    func testFlagKeepsTheRowAndRecordsTheTime() throws {
        let appDatabase = try makeDatabase()
        let created = try appDatabase.dbWriter.write { db in
            try ManualTransactions.create(
                db: db,
                input: ManualTransactions.Input(
                    date: try self.date("2026-04-07"),
                    amount: Decimal(string: "-20.00"),
                    description: "Market"
                )
            )
        }

        let flagged = try appDatabase.dbWriter.write { db in
            try ManualTransactions.flag(db: db, transactionId: created.id)
        }
        XCTAssertNotNil(flagged.deletedAt)
        XCTAssertTrue(flagged.isFlagged)
        XCTAssertNotNil(flagged.deletedAtDate, "the flag holds a readable time")
        XCTAssertEqual(
            flagged.updatedAt, flagged.deletedAt,
            "the flag stamps the row, so a delta export carries the flag to the computer"
        )

        let stored = try fetch(appDatabase, created.id)
        XCTAssertTrue(stored.isFlagged, "the row stays in the local database")

        // Port of the scenario "The user restores a row".
        let restored = try appDatabase.dbWriter.write { db in
            try ManualTransactions.restore(db: db, transactionId: created.id)
        }
        XCTAssertNil(restored.deletedAt)
        XCTAssertFalse(restored.isFlagged)
        XCTAssertNotNil(restored.updatedAt)
    }

    /// Port of the scenario "The user flags an imported transaction": the app
    /// refuses the flag, and it refuses the restore of the same row.
    func testFlagAndRestoreRefuseAnImportedRow() throws {
        let appDatabase = try makeDatabase()
        let imported = try insertImported(appDatabase)

        XCTAssertThrowsError(
            try appDatabase.dbWriter.write { db in
                try ManualTransactions.flag(db: db, transactionId: imported.id)
            }
        ) { error in
            XCTAssertEqual(
                error as? ManualTransactions.ManualTransactionError,
                .notHandEntered(imported.id)
            )
        }
        XCTAssertThrowsError(
            try appDatabase.dbWriter.write { db in
                try ManualTransactions.restore(db: db, transactionId: imported.id)
            }
        ) { error in
            XCTAssertEqual(
                error as? ManualTransactions.ManualTransactionError,
                .notHandEntered(imported.id)
            )
        }
        let after = try fetch(appDatabase, imported.id)
        XCTAssertNil(after.deletedAt, "the imported row stays live")
    }

    // MARK: - 8.6 The shared exclusion, in its three readers

    /// Seeds one live row and one flagged row of equal value in the account
    /// `CASH`, both in the category `groceries`.
    private func makeDatabaseWithOneFlaggedRow() throws -> AppDatabase {
        let appDatabase = try makeDatabase()
        try appDatabase.dbWriter.write { db in
            let input = ManualTransactions.Input(
                date: try self.date("2026-04-07"),
                amount: Decimal(string: "-20.00"),
                description: "Market",
                category: "groceries"
            )
            _ = try ManualTransactions.create(db: db, input: input)
            let flagged = try ManualTransactions.create(db: db, input: input)
            _ = try ManualTransactions.flag(db: db, transactionId: flagged.id)
        }
        return appDatabase
    }

    /// Reader one of `core/filters.py:live_only`: the transactions list, with
    /// its count and its sum.
    func testTheTransactionsListExcludesAFlaggedRow() throws {
        let appDatabase = try makeDatabaseWithOneFlaggedRow()
        let today = try date("2026-04-30")
        var filter = TransactionFilter()
        filter.dateFrom = try date("2026-01-01")
        filter.dateTo = try date("2026-12-31")

        try appDatabase.dbWriter.read { db in
            let page = try TransactionQuery.paginate(db: db, filter: filter, today: today)
            XCTAssertEqual(page.total, 1, "the rows hold no flagged transaction")
            XCTAssertEqual(page.items.count, 1)
            XCTAssertFalse(try XCTUnwrap(page.items.first).isFlagged)
            XCTAssertEqual(try TransactionQuery.count(db: db, filter: filter, today: today), 1)
            XCTAssertEqual(
                try TransactionQuery.sum(db: db, filter: filter, today: today), -20.0,
                accuracy: 0.001,
                "the summary total holds no flagged transaction"
            )
        }

        // The row is still in the table; only the readers hide it.
        let stored = try appDatabase.dbWriter.read { db in try TransactionRecord.fetchCount(db) }
        XCTAssertEqual(stored, 2)
    }

    /// Reader two: the category trends.
    func testTheCategoryTrendsExcludeAFlaggedRow() throws {
        let appDatabase = try makeDatabaseWithOneFlaggedRow()
        let params = TrendsBuilder.TrendsParams(
            granularity: .month,
            dateFrom: try date("2026-04-01"),
            dateTo: try date("2026-04-30")
        )
        let table = try appDatabase.dbWriter.read { db in
            try TrendsBuilder.aggregate(db: db, params: params, today: try self.date("2026-04-30"))
        }
        let total = table.rows.reduce(0.0) { $0 + $1.total }
        XCTAssertEqual(total, -20.0, accuracy: 0.001, "a flagged row contributes nothing to a cell")
    }

    /// Reader three: the budget actuals.
    func testTheBudgetActualsExcludeAFlaggedRow() throws {
        let appDatabase = try makeDatabaseWithOneFlaggedRow()
        let actual = try appDatabase.dbWriter.read { db in
            try BudgetReport.computeActual(
                db: db,
                category: "groceries",
                start: try self.date("2026-04-01"),
                end: try self.date("2026-04-30")
            )
        }
        XCTAssertEqual(actual, 20.0, accuracy: 0.001, "a flagged row contributes nothing to a total")
    }

    // MARK: - 8.7 Purge

    /// Port of the scenario "The user purges a flagged row on the phone": the
    /// app writes a backup, deletes exactly that row, and reports the number
    /// one.
    func testPurgeWritesABackupAndDeletesOnlyTheFlaggedRows() throws {
        let directory = try makeTempDirectory()
        let databaseURL = directory.appendingPathComponent("dvm_finance.sqlite")
        let appDatabase = try AppDatabase.live(at: databaseURL)

        let live = try appDatabase.dbWriter.write { db -> TransactionRecord in
            let input = ManualTransactions.Input(
                date: try self.date("2026-04-07"),
                amount: Decimal(string: "-20.00"),
                description: "Market"
            )
            let keep = try ManualTransactions.create(db: db, input: input)
            let flagged = try ManualTransactions.create(db: db, input: input)
            _ = try ManualTransactions.flag(db: db, transactionId: flagged.id)
            return keep
        }
        try insertImported(appDatabase)

        let result = try ManualTransactions.purgeFlagged(
            appDatabase: appDatabase, databaseURL: databaseURL)

        XCTAssertEqual(result.deleted, 1, "the purge reports the number of the deleted rows")
        let backupURL = try XCTUnwrap(result.backupURL, "the purge writes a backup first")
        XCTAssertTrue(FileManager.default.fileExists(atPath: backupURL.path))
        XCTAssertTrue(backupURL.lastPathComponent.hasPrefix("dvm_finance.backup-"))
        let backupSize = try FileManager.default.attributesOfItem(atPath: backupURL.path)[.size] as? Int
        XCTAssertGreaterThan(backupSize ?? 0, 0, "the backup is a real copy")

        let remaining = try appDatabase.dbWriter.read { db in
            try TransactionRecord.order(Column("id")).fetchAll(db)
        }
        XCTAssertEqual(remaining.count, 2, "the purge deletes no other row")
        XCTAssertTrue(remaining.contains { $0.id == live.id })
        XCTAssertTrue(remaining.contains { $0.id == "NL91_2026-03-02_-9.99_abc" })
    }

    /// Port of the scenario "The database holds no flagged row": the purge
    /// deletes nothing and reports the number zero.
    func testPurgeReportsZeroWhenNoRowIsFlagged() throws {
        let directory = try makeTempDirectory()
        let databaseURL = directory.appendingPathComponent("dvm_finance.sqlite")
        let appDatabase = try AppDatabase.live(at: databaseURL)
        try insertImported(appDatabase)

        let result = try ManualTransactions.purgeFlagged(
            appDatabase: appDatabase, databaseURL: databaseURL)
        XCTAssertEqual(result.deleted, 0)
        let count = try appDatabase.dbWriter.read { db in try TransactionRecord.fetchCount(db) }
        XCTAssertEqual(count, 1, "the purge deletes nothing")
    }

    /// The list the user reads before the purge holds the flagged rows only.
    func testFlaggedTransactionsListsOnlyTheFlaggedRows() throws {
        let appDatabase = try makeDatabaseWithOneFlaggedRow()
        let flagged = try appDatabase.dbWriter.read { db in
            try ManualTransactions.flaggedTransactions(db: db)
        }
        XCTAssertEqual(flagged.count, 1)
        XCTAssertTrue(try XCTUnwrap(flagged.first).isFlagged)
        let count = try appDatabase.dbWriter.read { db in
            try ManualTransactions.flaggedCount(db: db)
        }
        XCTAssertEqual(count, 1)
    }

    // MARK: - The duplicate check still reads a flagged row

    /// The duplicate check treats the id of a flagged transaction as taken,
    /// so that a second row cannot claim it. `Dedup.checkDuplicates` must
    /// therefore not compose the live-only predicate.
    func testTheDuplicateCheckTreatsTheIdOfAFlaggedRowAsTaken() throws {
        let appDatabase = try makeDatabase()
        let parsed = ParsedTransaction(
            accountNumber: "NL91",
            transactiondate: try date("2026-03-02"),
            amount: -9.99,
            description: "Imported row"
        )
        let id = TransactionID.generateTransactionID(parsed)
        try appDatabase.dbWriter.write { db in
            let record = TransactionRecord(
                id: id,
                accountNumber: "NL91",
                transactiondate: try self.date("2026-03-02"),
                amount: Decimal(string: "-9.99")!,
                description: "Imported row",
                deletedAt: "2026-04-01T10:00:00"
            )
            try record.insert(db)
        }

        let (new, duplicates) = try appDatabase.dbWriter.read { db in
            try Dedup.checkDuplicates(db: db, transactions: [parsed])
        }
        XCTAssertTrue(new.isEmpty)
        XCTAssertEqual(duplicates.count, 1, "the id of a flagged row stays taken")
    }
}
