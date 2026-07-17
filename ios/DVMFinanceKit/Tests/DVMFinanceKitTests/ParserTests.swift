import XCTest
import GRDB
@testable import DVMFinanceKit

/// Golden-fixture parity tests for Phase D (`Parsers/`): every parser is run
/// against its real statement-file fixture (`Fixtures/mt940_sample.STA`,
/// `paypal_sample.TXT`, `seb_sample.csv`, `wise_sample.csv`) and compared
/// field-for-field against `Fixtures/parser_expected.json` — the **real**
/// Python parsers' output for the same files (`Fixtures/generators/
/// gen_parser_fixtures.py`), not the port's own assumptions.
final class ParserTests: XCTestCase {

    // MARK: - Fixture loading

    private func fixtureURL(_ name: String, _ ext: String, file: StaticString = #filePath, line: UInt = #line) throws -> URL {
        try XCTUnwrap(Bundle.module.url(forResource: name, withExtension: ext), "missing fixture \(name).\(ext)", file: file, line: line)
    }

    private func loadExpected() throws -> [String: Any] {
        let url = try fixtureURL("parser_expected", "json")
        let data = try Data(contentsOf: url)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    // MARK: - Generic per-row field assertion
    //
    // One comparator covers every format: a key **absent** from `expected`
    // (Python's dict never set it) or present as JSON `null` (Python set it
    // to `None` explicitly) both assert the corresponding `ParsedTransaction`
    // field is `nil` — per the task brief, a Python parser's "omitted key"
    // vs. "key set to None" both collapse to the same Swift `nil`, and that
    // is fine.

    private func assertString(
        _ actual: String?, _ key: String, _ expected: [String: Any],
        file: StaticString = #filePath, line: UInt = #line
    ) {
        let raw = expected[key]
        if raw == nil || raw is NSNull {
            XCTAssertNil(actual, "\(key) should be nil", file: file, line: line)
        } else if let s = raw as? String {
            XCTAssertEqual(actual, s, key, file: file, line: line)
        } else {
            XCTFail("\(key): unexpected expected type \(String(describing: raw))", file: file, line: line)
        }
    }

    private func assertInt(
        _ actual: Int?, _ key: String, _ expected: [String: Any],
        file: StaticString = #filePath, line: UInt = #line
    ) {
        let raw = expected[key]
        if raw == nil || raw is NSNull {
            XCTAssertNil(actual, "\(key) should be nil", file: file, line: line)
        } else if let n = raw as? NSNumber {
            XCTAssertEqual(actual, n.intValue, key, file: file, line: line)
        } else {
            XCTFail("\(key): unexpected expected type \(String(describing: raw))", file: file, line: line)
        }
    }

    private func assertDouble(
        _ actual: Double?, _ key: String, _ expected: [String: Any],
        file: StaticString = #filePath, line: UInt = #line
    ) {
        let raw = expected[key]
        if raw == nil || raw is NSNull {
            XCTAssertNil(actual, "\(key) should be nil", file: file, line: line)
        } else if let n = raw as? NSNumber {
            XCTAssertEqual(actual, n.doubleValue, key, file: file, line: line)
        } else {
            XCTFail("\(key): unexpected expected type \(String(describing: raw))", file: file, line: line)
        }
    }

    private func assertDate(
        _ actual: Date?, _ key: String, _ expected: [String: Any],
        file: StaticString = #filePath, line: UInt = #line
    ) {
        let raw = expected[key]
        if raw == nil || raw is NSNull {
            XCTAssertNil(actual, "\(key) should be nil", file: file, line: line)
        } else if let s = raw as? String {
            guard let actual else {
                XCTFail("\(key) should be non-nil (expected \(s))", file: file, line: line)
                return
            }
            XCTAssertEqual(DatabaseDateFormat.dateOnly.string(from: actual), s, key, file: file, line: line)
        } else {
            XCTFail("\(key): unexpected expected type \(String(describing: raw))", file: file, line: line)
        }
    }

    private func assertDescriptionStructured(
        _ actual: String?, _ expected: [String: Any],
        file: StaticString = #filePath, line: UInt = #line
    ) {
        let raw = expected["description_structured"]
        if raw == nil || raw is NSNull {
            XCTAssertNil(actual, "description_structured should be nil", file: file, line: line)
            return
        }
        guard let expectedJSONString = raw as? String else {
            XCTFail("description_structured: unexpected expected type", file: file, line: line)
            return
        }
        guard let actual else {
            XCTFail("description_structured should be non-nil", file: file, line: line)
            return
        }
        guard let actualObj = try? JSONSerialization.jsonObject(with: Data(actual.utf8)) as? NSDictionary else {
            XCTFail("actual description_structured is not a valid JSON object: \(actual)", file: file, line: line)
            return
        }
        guard let expectedObj = try? JSONSerialization.jsonObject(with: Data(expectedJSONString.utf8)) as? NSDictionary else {
            XCTFail("expected description_structured fixture is not valid JSON", file: file, line: line)
            return
        }
        XCTAssertEqual(actualObj, expectedObj, "description_structured mismatch (parsed JSON)", file: file, line: line)
    }

    /// Every field a Phase D parser can produce, checked against `expected`'s
    /// keys generically (see the comment above).
    private func assertTransaction(
        _ actual: ParsedTransaction, _ expected: [String: Any],
        file: StaticString = #filePath, line: UInt = #line
    ) {
        assertString(actual.accountNumber, "accountNumber", expected, file: file, line: line)
        assertDate(actual.transactiondate, "transactiondate", expected, file: file, line: line)
        assertDate(actual.valuedate, "valuedate", expected, file: file, line: line)
        assertDouble(actual.startsaldo, "startsaldo", expected, file: file, line: line)
        assertDouble(actual.endsaldo, "endsaldo", expected, file: file, line: line)
        assertDouble(actual.amount, "amount", expected, file: file, line: line)
        assertString(actual.description, "description", expected, file: file, line: line)
        assertDescriptionStructured(actual.descriptionStructured, expected, file: file, line: line)
        assertString(actual.mutationcode, "mutationcode", expected, file: file, line: line)
        assertString(actual.currency, "currency", expected, file: file, line: line)
        assertString(actual.sourceFile, "source_file", expected, file: file, line: line)
        assertInt(actual.sourceLine, "source_line", expected, file: file, line: line)
        assertString(actual.transactionTypeCode, "transaction_type_code", expected, file: file, line: line)
        assertString(actual.transactionReference, "transaction_reference", expected, file: file, line: line)
        assertString(actual.category, "category", expected, file: file, line: line)
        assertString(actual.paypalTransactionId, "paypal_transaction_id", expected, file: file, line: line)
        assertString(actual.wiseTransactionId, "wise_transaction_id", expected, file: file, line: line)
        assertString(actual.sebVoucherId, "seb_voucher_id", expected, file: file, line: line)
    }

    // MARK: - MT940 (2291 transactions; only first/last 5 are golden)

    func testMT940FixtureParity() throws {
        let expected = try loadExpected()
        let mt940Expected = try XCTUnwrap(expected["mt940_sample.STA"] as? [String: Any])
        let expectedCount = try XCTUnwrap(mt940Expected["count"] as? Int)
        let expectedFirst = try XCTUnwrap(mt940Expected["first"] as? [[String: Any]])
        let expectedLast = try XCTUnwrap(mt940Expected["last"] as? [[String: Any]])

        let url = try fixtureURL("mt940_sample", "STA")
        let transactions = try MT940Parser.parse(fileURL: url)

        XCTAssertEqual(transactions.count, expectedCount)

        for (actual, expectedRow) in zip(transactions.prefix(5), expectedFirst) {
            assertTransaction(actual, expectedRow)
        }
        for (actual, expectedRow) in zip(transactions.suffix(5), expectedLast) {
            assertTransaction(actual, expectedRow)
        }
    }

    // MARK: - PayPal (89 transactions, every row is golden)

    func testPayPalFixtureParity() throws {
        let expected = try loadExpected()
        let paypalExpected = try XCTUnwrap(expected["paypal_sample.TXT"] as? [String: Any])
        let expectedCount = try XCTUnwrap(paypalExpected["count"] as? Int)
        let expectedRows = try XCTUnwrap(paypalExpected["rows"] as? [[String: Any]])

        let url = try fixtureURL("paypal_sample", "TXT")
        let transactions = try PayPalParser.parse(fileURL: url)

        XCTAssertEqual(transactions.count, expectedCount)
        XCTAssertEqual(transactions.count, expectedRows.count)

        for (actual, expectedRow) in zip(transactions, expectedRows) {
            assertTransaction(actual, expectedRow)
        }
    }

    // MARK: - Wise (3 transactions, every row is golden)

    func testWiseFixtureParity() throws {
        let expected = try loadExpected()
        let wiseExpected = try XCTUnwrap(expected["wise_sample.csv"] as? [String: Any])
        let expectedCount = try XCTUnwrap(wiseExpected["count"] as? Int)
        let expectedRows = try XCTUnwrap(wiseExpected["rows"] as? [[String: Any]])

        let url = try fixtureURL("wise_sample", "csv")
        let transactions = try WiseParser.parse(fileURL: url)

        XCTAssertEqual(transactions.count, expectedCount)
        XCTAssertEqual(transactions.count, expectedRows.count)

        for (actual, expectedRow) in zip(transactions, expectedRows) {
            assertTransaction(actual, expectedRow)
        }
    }

    // MARK: - SEB (21 transactions, every row is golden)
    //
    // SEK->EUR conversion depends on live ECB rates (`SEBParser.swift`'s
    // `fetchECBRateCache`), which would make a network-dependent test
    // flaky/non-deterministic. Instead this injects the exact per-date rate
    // cache the fixture's own `eur_rate_used` values imply (extracted
    // directly from `parser_expected.json` below) via the internal
    // `parse(content:fileName:rateCache:)` seam, exercising the identical
    // conversion arithmetic and JSON shape deterministically.

    func testSEBFixtureParity() throws {
        let expected = try loadExpected()
        let sebExpected = try XCTUnwrap(expected["seb_sample.csv"] as? [String: Any])
        let expectedCount = try XCTUnwrap(sebExpected["count"] as? Int)
        let expectedRows = try XCTUnwrap(sebExpected["rows"] as? [[String: Any]])

        func day(_ year: Int, _ month: Int, _ dayOfMonth: Int) -> Date {
            ParserUtils.makeUTCDate(year: year, month: month, day: dayOfMonth)!
        }

        // Every unique "Booking date" in seb_sample.csv paired with the
        // `eur_rate_used` parser_expected.json records for that date.
        let rateCache: [Date: Double] = [
            day(2026, 6, 25): 11.069,
            day(2026, 6, 23): 11.0585,
            day(2026, 6, 22): 10.998,
            day(2026, 6, 18): 10.9845,
            day(2026, 6, 8): 10.876,
            day(2026, 6, 5): 10.8675,
            day(2026, 6, 4): 10.8803,
            day(2026, 6, 2): 10.825,
            day(2026, 6, 1): 10.789,
            day(2026, 5, 27): 10.7895,
            day(2026, 5, 26): 10.8245,
            day(2026, 5, 25): 10.7965,
        ]

        let url = try fixtureURL("seb_sample", "csv")
        let content = try ParserUtils.readFileStrippingBOM(url)
        let transactions = try SEBParser.parse(content: content, fileName: "seb_sample.csv", rateCache: rateCache)

        XCTAssertEqual(transactions.count, expectedCount)
        XCTAssertEqual(transactions.count, expectedRows.count)

        for (actual, expectedRow) in zip(transactions, expectedRows) {
            assertTransaction(actual, expectedRow)
        }
    }

    // MARK: - StatementFileParser dispatch

    func testStatementFileParserDispatchesMT940ByExtension() throws {
        let url = try fixtureURL("mt940_sample", "STA")
        let transactions = try StatementFileParser.parse(fileURL: url)
        XCTAssertEqual(transactions.count, 2291)
        XCTAssertEqual(transactions.first?.sourceFile, "mt940_sample.STA")
    }

    func testStatementFileParserDispatchesGenericCSVByExtension() throws {
        // No golden ABN-CSV fixture exists; exercise the dispatch + minimal
        // shape with an inline well-formed CSV.
        let tempURL = FileManager.default.temporaryDirectory.appendingPathComponent("abn-\(UUID().uuidString).csv")
        let csv = "accountNumber,transactiondate,amount,description\nNL91ABNA0417164300,2026-01-15,-12.30,Albert Heijn\n"
        try csv.write(to: tempURL, atomically: true, encoding: .utf8)
        defer { try? FileManager.default.removeItem(at: tempURL) }

        let transactions = try StatementFileParser.parse(fileURL: tempURL)
        XCTAssertEqual(transactions.count, 1)
        XCTAssertEqual(transactions.first?.accountNumber, "NL91ABNA0417164300")
        XCTAssertEqual(transactions.first?.amount, -12.30)
        XCTAssertEqual(transactions.first?.sourceFile, tempURL.lastPathComponent)
    }

    func testStatementFileParserRejectsXLS() throws {
        let tempURL = FileManager.default.temporaryDirectory.appendingPathComponent("statement-\(UUID().uuidString).xlsx")
        try Data().write(to: tempURL)
        defer { try? FileManager.default.removeItem(at: tempURL) }

        XCTAssertThrowsError(try StatementFileParser.parse(fileURL: tempURL)) { error in
            guard case ParserError.unsupportedFormat = error else {
                XCTFail("expected .unsupportedFormat, got \(error)")
                return
            }
        }
    }

    func testStatementFormatExplicitDispatchMatchesAutoDetection() throws {
        let url = try fixtureURL("wise_sample", "csv")
        let viaFormat = try StatementFormat.parse(url: url, as: .wise)
        let viaParser = try WiseParser.parse(fileURL: url)
        XCTAssertEqual(viaFormat.count, viaParser.count)
        XCTAssertEqual(viaFormat.count, 3)
    }

    // MARK: - End-to-end: parse -> dedup -> insert -> applyRules -> report
    //
    // Mirrors `ios/docs/plan.md` "Phase D" acceptance: "import flow (parse
    // -> dedup -> insert -> applyRules -> report) covered by an end-to-end
    // Kit test using an in-memory DB and a bundled rules snapshot."

    func testWiseImportEndToEnd() throws {
        let url = try fixtureURL("wise_sample", "csv")
        let transactions = try WiseParser.parse(fileURL: url)
        XCTAssertEqual(transactions.count, 3)

        let appDatabase = try AppDatabase.inMemory()

        try appDatabase.dbWriter.write { db in
            var rule = CategorizationRuleRecord(
                ruleType: "full_description",
                matchPattern: "contains",
                fieldTarget: "description",
                matchValue: "spotify",
                category: "entertainment-music"
            )
            try rule.insert(db)
        }

        var newIDs: [String] = []
        try appDatabase.dbWriter.write { db in
            let (new, duplicates) = try Dedup.checkDuplicates(db: db, transactions: transactions)
            XCTAssertEqual(new.count, 3)
            XCTAssertEqual(duplicates.count, 0)

            newIDs = try Dedup.insertTransactions(db: db, transactions: new)
            XCTAssertEqual(newIDs.count, 3)

            try Categorizer.applyRules(db: db, transactionIds: newIDs)
            try Categorizer.recordRuleChange(db: db, action: "import")
        }

        let finalTransactions = try appDatabase.dbWriter.read { db in
            try TransactionRecord.fetchAll(db)
        }
        XCTAssertEqual(finalTransactions.count, 3)
        XCTAssertEqual(Set(finalTransactions.map(\.id)), Set(newIDs))

        let spotifyTransaction = try XCTUnwrap(
            finalTransactions.first { $0.description?.localizedCaseInsensitiveContains("spotify") == true }
        )
        XCTAssertEqual(spotifyTransaction.category, "entertainment-music")
        XCTAssertNotNil(spotifyTransaction.categorizationSource)

        // The other two transactions (no rule matches "spotify") land
        // uncategorized — apply_rules' pass 1 clears category when no rule
        // matches, even though the Wise parser itself pre-set `category:
        // "transfer"` on the incoming (IN-direction) transaction.
        let otherTransactions = finalTransactions.filter { $0.id != spotifyTransaction.id }
        XCTAssertEqual(otherTransactions.count, 2)
        for txn in otherTransactions {
            XCTAssertNil(txn.category, "expected no rule to match \(txn.description ?? "")")
        }

        let reportCount = try appDatabase.dbWriter.read { db in try RuleChangeReportRecord.fetchCount(db) }
        XCTAssertGreaterThanOrEqual(reportCount, 1)

        let items = try appDatabase.dbWriter.read { db in try RuleChangeItemRecord.fetchAll(db) }
        XCTAssertTrue(items.contains { $0.transactionId == spotifyTransaction.id && $0.newCategory == "entertainment-music" })
    }
}
