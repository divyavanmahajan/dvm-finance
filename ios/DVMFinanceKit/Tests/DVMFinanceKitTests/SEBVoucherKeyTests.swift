import XCTest
import GRDB
@testable import DVMFinanceKit

/// The SEB voucher key on iOS: the shared id fixture, the parser refusal
/// without ECB rates, the GRDB migration `v7`, and the change of an old SEB
/// id in an incoming snapshot. See the OpenSpec change
/// `fix-seb-import-integrity`.
final class SEBVoucherKeyTests: XCTestCase {

    private struct SEBIDCase: Decodable {
        let voucherNumber: String
        let bookingDate: String
        let amount: String
        let balance: String?
        let expectedId: String

        enum CodingKeys: String, CodingKey {
            case voucherNumber = "voucher_number"
            case bookingDate = "booking_date"
            case amount, balance
            case expectedId = "expected_id"
        }
    }

    private struct SEBIDFixture: Decodable {
        let account: String
        let cases: [SEBIDCase]
    }

    private static let account = "seb:divyavanmahajan"
    private static let oldId = "seb:divyavanmahajan_5400000001"
    private static let newId = "seb:divyavanmahajan_5400000001_2026-10-02_-412.30_1234.56"
    private static let structured =
        #"{"format": "seb", "voucher_number": "5400000001", "native_amount": -412.3, "#
        + #""native_currency": "SEK", "native_balance": 1234.56, "eur_rate_used": 11.29}"#

    private static let sebCSV = """
        Booking date;Value date;Voucher number;Text;Amount;Balance
        2026-10-19;2026-10-19;5400000001;KIOSKEN AB  /26-10-18;-149.000;2200.750
        2026-10-19;2026-10-19;5400000001;KIOSKEN AB  /26-10-18;-149.000;2349.750
        2026-10-02;2026-10-02;5400000001;MARKET A    /26-10-01;-412.300;1234.560
        """

    private func dateOnly(_ string: String) throws -> Date {
        try XCTUnwrap(DatabaseDateFormat.dateOnly.date(from: string))
    }

    // MARK: - Shared fixture

    func testIdsMatchTheSharedFixture() throws {
        let data = try Data(contentsOf: try fixtureURL("seb_ids", "json"))
        let fixture = try JSONDecoder().decode(SEBIDFixture.self, from: data)
        XCTAssertFalse(fixture.cases.isEmpty)
        for testCase in fixture.cases {
            let transaction = ParsedTransaction(
                accountNumber: fixture.account,
                transactiondate: try dateOnly(testCase.bookingDate),
                sebVoucherId: testCase.voucherNumber,
                sebNativeAmount: testCase.amount,
                sebNativeBalance: testCase.balance
            )
            XCTAssertEqual(TransactionID.generateTransactionID(transaction), testCase.expectedId)
            // The migration reads the values as JSON numbers.
            let structured = try String(
                data: JSONSerialization.data(withJSONObject: [
                    "voucher_number": testCase.voucherNumber,
                    "native_amount": Double(testCase.amount)!,
                    "native_balance": testCase.balance.map { Double($0)! as Any } ?? NSNull(),
                ]),
                encoding: .utf8
            )
            XCTAssertEqual(
                TransactionID.upgradedSEBID(
                    id: "\(fixture.account)_\(testCase.voucherNumber)",
                    accountNumber: fixture.account,
                    bookingDate: testCase.bookingDate,
                    descriptionStructured: structured
                ),
                testCase.expectedId
            )
        }
    }

    // MARK: - Parser

    func testParserCarriesTheKronaValuesAndGivesEachPaymentItsOwnId() throws {
        let cache: [Date: Double] = [try dateOnly("2026-10-01"): 11.29]
        let transactions = try SEBParser.parse(content: Self.sebCSV, fileName: "seb.csv", rateCache: cache)
        XCTAssertEqual(transactions.count, 3)
        XCTAssertEqual(transactions[2].sebNativeAmount, "-412.300")
        XCTAssertEqual(transactions[2].sebNativeBalance, "1234.560")
        XCTAssertEqual(transactions[2].currency, "EUR")
        XCTAssertEqual(TransactionID.generateTransactionID(transactions[2]), Self.newId)
        XCTAssertEqual(Set(transactions.map(TransactionID.generateTransactionID)).count, 3)
    }

    func testParserWithoutRatesRefusesTheFile() {
        XCTAssertThrowsError(
            try SEBParser.parse(content: Self.sebCSV, fileName: "seb.csv", rateCache: [:])
        ) { error in
            XCTAssertEqual(error as? SEBParser.SEBParserError, .ratesUnavailable)
            XCTAssertEqual(
                error.localizedDescription,
                "The ECB exchange rates are not available. The import stored no transaction. Try again later."
            )
        }
    }

    func testImportWithoutRatesWritesNoRow() async throws {
        let appDatabase = try AppDatabase.inMemory()
        do {
            let parsed = try SEBParser.parse(content: Self.sebCSV, fileName: "seb.csv", rateCache: [:])
            _ = try await AppQueries.importStatementTransactions(appDatabase: appDatabase, transactions: parsed)
            XCTFail("the import must refuse the file")
        } catch SEBParser.SEBParserError.ratesUnavailable {
            // The import screen shows this error.
        }
        let count = try await appDatabase.dbWriter.read { db in try TransactionRecord.fetchCount(db) }
        XCTAssertEqual(count, 0)
    }

    // MARK: - GRDB migration v7

    func testMigrationV7ChangesTheIdsAndKeepsTheReferences() throws {
        let queue = try DatabaseQueue()
        let migrator = AppDatabase.makeMigrator()
        try migrator.migrate(queue, upTo: "v6")
        try queue.write { db in
            try db.execute(
                sql: """
                    INSERT INTO transactions (id, accountNumber, transactiondate, amount, currency,
                        description_structured, manual_category, manual_tags, is_manual)
                    VALUES (?, ?, '2026-10-02', '-36.52', 'EUR', ?, 'groceries', 'weekly', 0)
                    """,
                arguments: [Self.oldId, Self.account, Self.structured]
            )
            try db.execute(
                sql: """
                    INSERT INTO transactions (id, accountNumber, transactiondate, amount, currency,
                        description_structured, merged_into, is_manual)
                    VALUES ('other', ?, '2026-10-03', '-1.00', 'EUR', '{}', ?, 0)
                    """,
                arguments: [Self.account, Self.oldId]
            )
            try db.execute(
                sql: "INSERT INTO rule_change_reports (id, created_at, action) VALUES (1, '2026-11-01T00:00:00', 'import')"
            )
            try db.execute(
                sql: "INSERT INTO rule_change_items (report_id, transaction_id) VALUES (1, ?)",
                arguments: [Self.oldId]
            )
        }

        try migrator.migrate(queue)

        try queue.read { db in
            let ids = try String.fetchSet(db, sql: "SELECT id FROM transactions")
            XCTAssertEqual(ids, [Self.newId, "other"])
            let manual = try Row.fetchOne(
                db, sql: "SELECT manual_category, manual_tags FROM transactions WHERE id = ?",
                arguments: [Self.newId]
            )
            XCTAssertEqual(manual?["manual_category"], "groceries")
            XCTAssertEqual(manual?["manual_tags"], "weekly")
            XCTAssertEqual(
                try String.fetchOne(db, sql: "SELECT merged_into FROM transactions WHERE id = 'other'"),
                Self.newId
            )
            XCTAssertEqual(
                try String.fetchOne(db, sql: "SELECT transaction_id FROM rule_change_items"),
                Self.newId
            )
        }
    }

    // MARK: - Snapshot

    func testSnapshotWithAnOldSEBIdMatchesTheNewId() throws {
        let appDatabase = try AppDatabase.inMemory()
        let local = TransactionRecord(
            id: Self.newId,
            accountNumber: Self.account,
            transactiondate: try dateOnly("2026-10-02"),
            amount: Decimal(string: "-36.52")!,
            description: "MARKET A",
            descriptionStructured: Self.structured
        )
        try appDatabase.dbWriter.write { db in try local.insert(db) }

        var incoming = SnapshotCodec.makeSnapshotTransaction(local)
        incoming.id = Self.oldId
        incoming.manualCategory = "groceries"
        let report = SnapshotReport(
            createdAt: "2026-11-01T00:00:00", ruleId: nil, ruleUuid: nil, action: "recategorize",
            ruleBefore: nil, ruleAfter: nil, summary: nil,
            items: [SnapshotReportItem(transactionId: Self.oldId, oldCategory: nil,
                                       newCategory: "groceries", oldTags: nil, newTags: nil)]
        )
        let document = SnapshotDocument(
            header: SnapshotHeader(schemaVersion: 1, exportedAt: "2026-11-25T09:00:00", machineId: "desktop"),
            transactions: [incoming],
            rules: [],
            budgets: [],
            ruleChangeReports: [report]
        )

        _ = try SnapshotImporter.importSnapshot(
            appDatabase: appDatabase,
            document: document,
            databaseURL: FileManager.default.temporaryDirectory.appendingPathComponent("absent-\(UUID()).sqlite")
        )

        try appDatabase.dbWriter.read { db in
            XCTAssertEqual(try TransactionRecord.fetchCount(db), 1)
            XCTAssertEqual(try TransactionRecord.fetchOne(db, key: Self.newId)?.manualCategory, "groceries")
            let itemIds = try String.fetchSet(db, sql: "SELECT transaction_id FROM rule_change_items")
            XCTAssertFalse(itemIds.contains(Self.oldId))
            XCTAssertTrue(itemIds.contains(Self.newId))
        }
    }

    func testSnapshotWithTheNewIdsIsUnchanged() throws {
        let local = TransactionRecord(
            id: Self.newId, accountNumber: Self.account, transactiondate: try dateOnly("2026-10-02"),
            amount: Decimal(string: "-36.52")!, descriptionStructured: Self.structured
        )
        let document = SnapshotDocument(
            header: SnapshotHeader(schemaVersion: 1, exportedAt: "2026-11-25T09:00:00", machineId: "desktop"),
            transactions: [SnapshotCodec.makeSnapshotTransaction(local)],
            rules: [], budgets: [], ruleChangeReports: []
        )
        XCTAssertEqual(SnapshotImporter.upgradeSEBIDs(document), document)
    }
}
