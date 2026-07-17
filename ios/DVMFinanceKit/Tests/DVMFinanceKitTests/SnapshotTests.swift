import XCTest
import GRDB
@testable import DVMFinanceKit

/// Covers Phase C's acceptance criteria (`ios/docs/plan.md` "Phase C"):
/// gzip round-trip/corruption handling, `SnapshotCodec.read(_:)` validation
/// order, the key parity test against `Fixtures/fixture-snapshot.json.gz` +
/// `Fixtures/fixture-snapshot-expected.json` (produced by the real Python
/// exporter/importer — see `Fixtures/generators/gen_snapshot_fixture.py`),
/// re-import idempotency, export->read round-trip, and the on-disk DB
/// backup step.
final class SnapshotTests: XCTestCase {
    private var tempDirectories: [URL] = []

    override func tearDownWithError() throws {
        for url in tempDirectories {
            try? FileManager.default.removeItem(at: url)
        }
        tempDirectories = []
    }

    // MARK: - Test helpers

    private func makeTempDirectory() throws -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("SnapshotTests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        tempDirectories.append(url)
        return url
    }

    private func dateOnly(_ string: String) throws -> Date {
        try XCTUnwrap(DatabaseDateFormat.dateOnly.date(from: string))
    }

    private func loadFixtureSnapshotBlob() throws -> Data {
        let url = try XCTUnwrap(Bundle.module.url(forResource: "fixture-snapshot", withExtension: "json.gz"))
        return try Data(contentsOf: url)
    }

    // MARK: - `fixture-snapshot-expected.json` decoding

    private struct ExpectedCounter: Decodable, Equatable {
        let inserted: Int
        let updated: Int
        let unchanged: Int
    }

    private struct ExpectedCounts: Decodable {
        let transactions: ExpectedCounter
        let rules: ExpectedCounter
        let budgets: ExpectedCounter
        let ruleChangeReports: ExpectedCounter

        enum CodingKeys: String, CodingKey {
            case transactions, rules, budgets
            case ruleChangeReports = "rule_change_reports"
        }
    }

    private struct ExpectedFinalTransaction: Decodable {
        let id: String
        let category: String?
        let manualCategory: String?
        let tags: String?
        let manualTags: String?
        let categorizationSource: String?

        enum CodingKeys: String, CodingKey {
            case id, category
            case manualCategory = "manual_category"
            case tags
            case manualTags = "manual_tags"
            case categorizationSource = "categorization_source"
        }
    }

    private struct ExpectedFinalRule: Decodable {
        let id: Int64
        let uuid: String
        let priority: Int
        let matchValue: String
        let category: String?
        let isActive: Bool
        let nConditions: Int

        enum CodingKeys: String, CodingKey {
            case id, uuid, priority
            case matchValue = "match_value"
            case category
            case isActive = "is_active"
            case nConditions = "n_conditions"
        }
    }

    private struct ExpectedFinalState: Decodable {
        let transactions: [ExpectedFinalTransaction]
        let rules: [ExpectedFinalRule]
    }

    private struct ExpectedFixture: Decodable {
        let importCounts: ExpectedCounts
        let finalState: ExpectedFinalState

        enum CodingKeys: String, CodingKey {
            case importCounts = "import_counts"
            case finalState = "final_state"
        }
    }

    private func loadExpectedFixture() throws -> ExpectedFixture {
        let url = try XCTUnwrap(Bundle.module.url(forResource: "fixture-snapshot-expected", withExtension: "json"))
        let data = try Data(contentsOf: url)
        return try JSONDecoder().decode(ExpectedFixture.self, from: data)
    }

    /// Seeds an in-memory `AppDatabase` exactly like
    /// `Fixtures/generators/gen_snapshot_fixture.py`'s destination ("phone")
    /// database: `t1` present locally with a *different* manual category
    /// (incoming must overwrite it), `t-local` present only locally (must
    /// survive untouched), and a local rule sharing the fixture's uuid but a
    /// different machine-local id (7) and different field values (incoming
    /// must update it in place, keeping local id 7).
    private func seedDestinationDatabase(_ appDatabase: AppDatabase) throws {
        try appDatabase.dbWriter.write { db in
            var t1 = TransactionRecord(
                id: "t1",
                accountNumber: "NL91",
                transactiondate: try self.dateOnly("2026-01-15"),
                amount: Decimal(string: "-12.30")!,
                description: "BEA Albert Heijn",
                manualCategory: "local-manual",
                categorizationSource: "manual",
                currency: "EUR"
            )
            try t1.insert(db)

            var tLocal = TransactionRecord(
                id: "t-local",
                accountNumber: "NL91",
                transactiondate: try self.dateOnly("2026-03-01"),
                amount: Decimal(string: "-1")!,
                description: "local only",
                currency: "EUR"
            )
            try tLocal.insert(db)

            var localRule = CategorizationRuleRecord(
                id: 7,
                uuid: "11111111-1111-1111-1111-111111111111",
                priority: 99,
                ruleType: "full_description",
                matchPattern: "contains",
                fieldTarget: "description",
                matchValue: "old value",
                category: "old-cat",
                isActive: false,
                isTagOnly: false
            )
            try localRule.insert(db)
        }
    }

    // MARK: - Gzip round-trip / corruption (RawDeflate + CRC32 + framing)

    func testGzipRoundTripArbitraryData() throws {
        let original = Data("hello, gzip world! Special chars: \u{00e9}\u{00fc}\u{1F600}".utf8)
        let compressed = try Gzip.compress(original)
        XCTAssertEqual(compressed.prefix(2), Data([0x1f, 0x8b]), "gzip magic bytes")
        let decompressed = try Gzip.decompress(compressed)
        XCTAssertEqual(decompressed, original)
    }

    func testGzipRoundTripLargePayload() throws {
        // Exercise the streaming loop across multiple 64 KiB chunks.
        let original = Data(repeating: 0x5A, count: 5 * 64 * 1024 + 137)
        let compressed = try Gzip.compress(original)
        let decompressed = try Gzip.decompress(compressed)
        XCTAssertEqual(decompressed, original)
    }

    func testGzipRoundTripEmptyData() throws {
        let compressed = try Gzip.compress(Data())
        let decompressed = try Gzip.decompress(compressed)
        XCTAssertEqual(decompressed, Data())
    }

    func testGzipDecodesRealPythonFixture() throws {
        let blob = try loadFixtureSnapshotBlob()
        let decompressed = try Gzip.decompress(blob)
        let json = try XCTUnwrap(String(data: decompressed, encoding: .utf8))
        XCTAssertTrue(json.contains("\"schema_version\": 1") || json.contains("\"schema_version\":1"))
        XCTAssertTrue(json.contains("machine_id"))
    }

    func testGzipRejectsTruncatedData() {
        let truncated = Data([0x1f, 0x8b, 0x08, 0x00])
        XCTAssertThrowsError(try Gzip.decompress(truncated))
    }

    func testGzipRejectsWrongMagicBytes() {
        let notGzip = Data("this is not a gzip file at all, just plain text".utf8)
        XCTAssertThrowsError(try Gzip.decompress(notGzip))
    }

    func testGzipRejectsCorruptedTrailer() throws {
        var compressed = [UInt8](try Gzip.compress(Data("hello".utf8)))
        // Flip a byte in the CRC32 trailer (last 8 bytes are CRC32 + ISIZE).
        compressed[compressed.count - 1] ^= 0xFF
        XCTAssertThrowsError(try Gzip.decompress(Data(compressed))) { error in
            XCTAssertTrue(error is GzipError)
        }
    }

    // MARK: - SnapshotCodec.read(_:) validation order

    func testReadRejectsCorruptGzip() {
        let blob = Data([0x00, 0x01, 0x02, 0x03, 0x04, 0x05])
        XCTAssertThrowsError(try SnapshotCodec.read(blob)) { error in
            XCTAssertEqual(error as? SnapshotError, .corruptGzip)
        }
    }

    func testReadRejectsCorruptJSON() throws {
        let blob = try Gzip.compress(Data("{ this is not valid json ][".utf8))
        XCTAssertThrowsError(try SnapshotCodec.read(blob)) { error in
            XCTAssertEqual(error as? SnapshotError, .corruptJSON)
        }
    }

    func testReadRejectsMissingHeader() throws {
        let payload = try JSONSerialization.data(withJSONObject: [
            "transactions": [], "rules": [], "budgets": [], "rule_change_reports": [],
        ])
        let blob = try Gzip.compress(payload)
        XCTAssertThrowsError(try SnapshotCodec.read(blob)) { error in
            XCTAssertEqual(error as? SnapshotError, .missingHeader)
        }
    }

    func testReadRejectsWrongSchemaVersion() throws {
        let payload = try JSONSerialization.data(withJSONObject: [
            "header": ["schema_version": 2, "exported_at": "2026-01-01T00:00:00", "machine_id": "abc"],
            "transactions": [], "rules": [], "budgets": [], "rule_change_reports": [],
        ])
        let blob = try Gzip.compress(payload)
        XCTAssertThrowsError(try SnapshotCodec.read(blob)) { error in
            XCTAssertEqual(error as? SnapshotError, .schemaVersionMismatch(found: 2))
        }
    }

    func testReadRejectsMissingSchemaVersion() throws {
        let payload = try JSONSerialization.data(withJSONObject: [
            "header": ["exported_at": "2026-01-01T00:00:00", "machine_id": "abc"],
            "transactions": [], "rules": [], "budgets": [], "rule_change_reports": [],
        ])
        let blob = try Gzip.compress(payload)
        XCTAssertThrowsError(try SnapshotCodec.read(blob)) { error in
            XCTAssertEqual(error as? SnapshotError, .schemaVersionMismatch(found: nil))
        }
    }

    func testReadRejectsMissingSection() throws {
        let payload = try JSONSerialization.data(withJSONObject: [
            "header": ["schema_version": 1, "exported_at": "2026-01-01T00:00:00", "machine_id": "abc"],
            "transactions": [], "rules": [], "budgets": [],
            // rule_change_reports intentionally omitted
        ])
        let blob = try Gzip.compress(payload)
        XCTAssertThrowsError(try SnapshotCodec.read(blob)) { error in
            XCTAssertEqual(error as? SnapshotError, .missingSection("rule_change_reports"))
        }
    }

    func testReadRejectsNonArraySection() throws {
        let payload = try JSONSerialization.data(withJSONObject: [
            "header": ["schema_version": 1, "exported_at": "2026-01-01T00:00:00", "machine_id": "abc"],
            "transactions": "not-an-array", "rules": [], "budgets": [], "rule_change_reports": [],
        ])
        let blob = try Gzip.compress(payload)
        XCTAssertThrowsError(try SnapshotCodec.read(blob)) { error in
            XCTAssertEqual(error as? SnapshotError, .missingSection("transactions"))
        }
    }

    func testReadParsesRealFixtureIntoTypedDocument() throws {
        let blob = try loadFixtureSnapshotBlob()
        let document = try SnapshotCodec.read(blob)

        XCTAssertEqual(document.header.schemaVersion, 1)
        XCTAssertFalse(document.header.machineId.isEmpty)
        XCTAssertEqual(document.transactions.count, 3)
        XCTAssertEqual(document.rules.count, 2)
        XCTAssertEqual(document.budgets.count, 1)
        XCTAssertEqual(document.ruleChangeReports.count, 1)

        let t1 = try XCTUnwrap(document.transactions.first { $0.id == "t1" })
        XCTAssertEqual(t1.amount, "-12.30")
        XCTAssertEqual(t1.category, "groceries-ah")
        XCTAssertEqual(t1.categorizationSource, "1")

        let rule1 = try XCTUnwrap(document.rules.first { $0.uuid == "11111111-1111-1111-1111-111111111111" })
        XCTAssertEqual(rule1.conditions.count, 1)
        XCTAssertEqual(rule1.conditions.first?.matchValue, "albert")
    }

    // MARK: - Key parity test: real fixture, real expected Python import counts

    func testImportMatchesPythonFixtureCountsAndFinalState() throws {
        let blob = try loadFixtureSnapshotBlob()
        let document = try SnapshotCodec.read(blob)
        let expected = try loadExpectedFixture()

        let appDatabase = try AppDatabase.inMemory()
        try seedDestinationDatabase(appDatabase)

        let nonexistentDBURL = try makeTempDirectory().appendingPathComponent("does-not-exist.sqlite")
        let importRecord = try SnapshotImporter.importSnapshot(
            appDatabase: appDatabase,
            document: document,
            databaseURL: nonexistentDBURL
        )

        // --- import counts ---
        let countsData = try XCTUnwrap(importRecord.counts?.data(using: .utf8))
        let counts = try JSONDecoder().decode(ExpectedCounts.self, from: countsData)
        XCTAssertEqual(counts.transactions, expected.importCounts.transactions)
        XCTAssertEqual(counts.rules, expected.importCounts.rules)
        XCTAssertEqual(counts.budgets, expected.importCounts.budgets)
        XCTAssertEqual(counts.ruleChangeReports, expected.importCounts.ruleChangeReports)

        XCTAssertEqual(importRecord.sourceMachineId, document.header.machineId)
        XCTAssertEqual(importRecord.schemaVersion, 1)

        // --- final transaction state ---
        let finalTransactions = try appDatabase.dbWriter.read { db in
            try TransactionRecord.order(Column("id").asc).fetchAll(db)
        }
        XCTAssertEqual(finalTransactions.map(\.id), expected.finalState.transactions.map(\.id))
        for (actual, expectedTxn) in zip(finalTransactions, expected.finalState.transactions) {
            XCTAssertEqual(actual.id, expectedTxn.id)
            XCTAssertEqual(actual.category, expectedTxn.category, "category for \(actual.id)")
            XCTAssertEqual(actual.manualCategory, expectedTxn.manualCategory, "manual_category for \(actual.id)")
            XCTAssertEqual(actual.tags, expectedTxn.tags, "tags for \(actual.id)")
            XCTAssertEqual(actual.manualTags, expectedTxn.manualTags, "manual_tags for \(actual.id)")
            XCTAssertEqual(
                actual.categorizationSource,
                expectedTxn.categorizationSource,
                "categorization_source for \(actual.id)"
            )
        }

        // t1's manual category must have been overwritten away (incoming wins).
        let t1 = try XCTUnwrap(finalTransactions.first { $0.id == "t1" })
        XCTAssertNil(t1.manualCategory)
        XCTAssertEqual(t1.category, "groceries-ah")
        XCTAssertEqual(t1.categorizationSource, "7", "remapped to the LOCAL rule id, not the incoming id 1")

        // t-local must have survived completely untouched.
        let tLocal = try XCTUnwrap(finalTransactions.first { $0.id == "t-local" })
        XCTAssertNil(tLocal.category)
        XCTAssertNil(tLocal.manualCategory)

        // --- final rule state ---
        let finalRules = try appDatabase.dbWriter.read { db in
            try CategorizationRuleRecord.order(Column("uuid").asc).fetchAll(db)
        }
        XCTAssertEqual(finalRules.map(\.uuid), expected.finalState.rules.map(\.uuid))

        let rule1 = try XCTUnwrap(finalRules.first { $0.uuid == "11111111-1111-1111-1111-111111111111" })
        let expectedRule1 = try XCTUnwrap(expected.finalState.rules.first { $0.uuid == rule1.uuid })
        XCTAssertEqual(rule1.id, 7, "the uuid-111... rule must keep its LOCAL id")
        XCTAssertEqual(rule1.id, expectedRule1.id)
        XCTAssertEqual(rule1.priority, expectedRule1.priority)
        XCTAssertEqual(rule1.matchValue, expectedRule1.matchValue)
        XCTAssertEqual(rule1.category, expectedRule1.category)
        XCTAssertEqual(rule1.isActive, expectedRule1.isActive)
        let rule1Conditions = try appDatabase.dbWriter.read { db in
            try RuleConditionRecord.filter(Column("rule_id") == rule1.id).fetchCount(db)
        }
        XCTAssertEqual(rule1Conditions, expectedRule1.nConditions)

        let rule2 = try XCTUnwrap(finalRules.first { $0.uuid == "22222222-2222-2222-2222-222222222222" })
        let expectedRule2 = try XCTUnwrap(expected.finalState.rules.first { $0.uuid == rule2.uuid })
        XCTAssertNotEqual(rule2.id, 7, "the new rule must NOT reuse the uuid-111... rule's id")
        XCTAssertNotNil(rule2.id) // autoincrement-assigned; not hard-coded, per the phase brief
        XCTAssertEqual(rule2.priority, expectedRule2.priority)
        XCTAssertEqual(rule2.matchValue, expectedRule2.matchValue)
        XCTAssertNil(rule2.category)
        XCTAssertEqual(rule2.isActive, expectedRule2.isActive)
        let rule2Conditions = try appDatabase.dbWriter.read { db in
            try RuleConditionRecord.filter(Column("rule_id") == rule2.id).fetchCount(db)
        }
        XCTAssertEqual(rule2Conditions, expectedRule2.nConditions)

        // --- overwrites: spot-check the two overwrite records the fixture predicts ---
        let overwritesData = try XCTUnwrap(importRecord.overwrites?.data(using: .utf8))
        let overwrites = try XCTUnwrap(
            JSONSerialization.jsonObject(with: overwritesData) as? [String: Any]
        )
        let txnOverwrites = try XCTUnwrap(overwrites["transactions"] as? [[String: Any]])
        XCTAssertEqual(txnOverwrites.count, 1)
        XCTAssertEqual(txnOverwrites.first?["id"] as? String, "t1")
        let ruleOverwrites = try XCTUnwrap(overwrites["rules"] as? [[String: Any]])
        XCTAssertEqual(ruleOverwrites.count, 1)
        XCTAssertEqual(ruleOverwrites.first?["uuid"] as? String, "11111111-1111-1111-1111-111111111111")
        let budgetOverwrites = try XCTUnwrap(overwrites["budgets"] as? [[String: Any]])
        XCTAssertTrue(budgetOverwrites.isEmpty)
    }

    // MARK: - Re-import idempotency

    func testReimportIsIdempotent() throws {
        let blob = try loadFixtureSnapshotBlob()
        let document = try SnapshotCodec.read(blob)

        let appDatabase = try AppDatabase.inMemory()
        try seedDestinationDatabase(appDatabase)

        let dbURL = try makeTempDirectory().appendingPathComponent("does-not-exist.sqlite")
        _ = try SnapshotImporter.importSnapshot(appDatabase: appDatabase, document: document, databaseURL: dbURL)

        let reportCountAfterFirstImport = try appDatabase.dbWriter.read { db in
            try RuleChangeReportRecord.fetchCount(db)
        }

        let secondImport = try SnapshotImporter.importSnapshot(
            appDatabase: appDatabase,
            document: document,
            databaseURL: dbURL
        )

        let countsData = try XCTUnwrap(secondImport.counts?.data(using: .utf8))
        let counts = try JSONDecoder().decode(ExpectedCounts.self, from: countsData)

        XCTAssertEqual(counts.transactions, ExpectedCounter(inserted: 0, updated: 0, unchanged: 3))
        XCTAssertEqual(counts.rules, ExpectedCounter(inserted: 0, updated: 0, unchanged: 2))
        XCTAssertEqual(counts.budgets, ExpectedCounter(inserted: 0, updated: 0, unchanged: 1))
        XCTAssertEqual(counts.ruleChangeReports, ExpectedCounter(inserted: 0, updated: 0, unchanged: 1))

        // Every import always appends its own fresh "import" audit report
        // (matching Python — this is *not* deduped), so the total grows by
        // exactly one on the second run: the snapshot's own "create" report
        // must NOT have been duplicated.
        let reportCountAfterSecondImport = try appDatabase.dbWriter.read { db in
            try RuleChangeReportRecord.fetchCount(db)
        }
        XCTAssertEqual(reportCountAfterSecondImport, reportCountAfterFirstImport + 1)
    }

    // MARK: - Export -> read round-trip

    func testExportReadImportRoundTrip() throws {
        let sourceDatabase = try AppDatabase.inMemory()
        var seededRule = CategorizationRuleRecord(
            ruleType: "full_description",
            matchPattern: "contains",
            fieldTarget: "description",
            matchValue: "coffee",
            category: "dining-coffee"
        )
        try sourceDatabase.dbWriter.write { db in
            try seededRule.insert(db)
            var condition = RuleConditionRecord(
                ruleId: seededRule.id!,
                fieldTarget: "description",
                matchPattern: "contains",
                matchValue: "bar",
                operatorValue: "AND",
                sortOrder: 0
            )
            try condition.insert(db)

            // Deliberately not a clean 2-decimal literal, to exercise
            // 2-decimal-place padding on export.
            var txn = TransactionRecord(
                id: "acct_2026-01-01_12.3_abc",
                accountNumber: "NL91",
                transactiondate: try self.dateOnly("2026-01-01"),
                amount: Decimal(string: "12.3")!,
                description: "Coffee shop"
            )
            try txn.insert(db)

            var budget = BudgetRecord(category: "dining", amount: Decimal(string: "150")!, period: "monthly")
            try budget.insert(db)

            var report = RuleChangeReportRecord(
                ruleId: seededRule.id,
                ruleUuid: seededRule.uuid,
                action: "create",
                summary: "{\"changed\":0}"
            )
            try report.insert(db)
        }

        let dataDirectory = try makeTempDirectory()
        let exportedURL = try SnapshotExporter.exportSnapshot(appDatabase: sourceDatabase, dataDirectory: dataDirectory)
        XCTAssertTrue(FileManager.default.fileExists(atPath: exportedURL.path))
        XCTAssertTrue(exportedURL.lastPathComponent.hasSuffix(".json.gz"))

        let blob = try Data(contentsOf: exportedURL)
        let document = try SnapshotCodec.read(blob)

        XCTAssertEqual(document.header.schemaVersion, 1)
        XCTAssertFalse(document.header.machineId.isEmpty)
        // "yyyy-MM-dd'T'HH:mm:ss" — no timezone suffix, no fractional seconds.
        XCTAssertTrue(document.header.exportedAt.range(of: #"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$"#, options: .regularExpression) != nil)

        XCTAssertEqual(document.transactions.count, 1)
        XCTAssertEqual(document.transactions.first?.amount, "12.30", "2-decimal-place padding on export")
        XCTAssertEqual(document.rules.count, 1)
        XCTAssertEqual(document.rules.first?.conditions.count, 1)
        XCTAssertEqual(document.budgets.count, 1)
        XCTAssertEqual(document.budgets.first?.amount, "150.00")
        XCTAssertEqual(document.ruleChangeReports.count, 1)

        // Import into a fresh, empty database: everything should insert.
        let destinationDatabase = try AppDatabase.inMemory()
        let importedDBURL = try makeTempDirectory().appendingPathComponent("does-not-exist.sqlite")
        let importRecord = try SnapshotImporter.importSnapshot(
            appDatabase: destinationDatabase,
            document: document,
            databaseURL: importedDBURL
        )
        let countsData = try XCTUnwrap(importRecord.counts?.data(using: .utf8))
        let counts = try JSONDecoder().decode(ExpectedCounts.self, from: countsData)
        XCTAssertEqual(counts.transactions, ExpectedCounter(inserted: 1, updated: 0, unchanged: 0))
        XCTAssertEqual(counts.rules, ExpectedCounter(inserted: 1, updated: 0, unchanged: 0))
        XCTAssertEqual(counts.budgets, ExpectedCounter(inserted: 1, updated: 0, unchanged: 0))
        XCTAssertEqual(counts.ruleChangeReports, ExpectedCounter(inserted: 1, updated: 0, unchanged: 0))
    }

    func testMachineIdPersistsAcrossExports() throws {
        let dataDirectory = try makeTempDirectory()
        let firstID = try MachineID.get(dataDirectory: dataDirectory)
        let secondID = try MachineID.get(dataDirectory: dataDirectory)
        XCTAssertEqual(firstID, secondID)

        let markerURL = dataDirectory.appendingPathComponent("machine_id")
        XCTAssertTrue(FileManager.default.fileExists(atPath: markerURL.path))
        let storedValue = try String(contentsOf: markerURL, encoding: .utf8)
        XCTAssertEqual(storedValue.trimmingCharacters(in: .whitespacesAndNewlines), firstID)

        // Two full exports must also agree on the header's machine_id.
        let appDatabase = try AppDatabase.inMemory()
        let firstExport = try SnapshotExporter.exportSnapshot(appDatabase: appDatabase, dataDirectory: dataDirectory)
        let secondExport = try SnapshotExporter.exportSnapshot(appDatabase: appDatabase, dataDirectory: dataDirectory)
        XCTAssertNotEqual(firstExport, secondExport, "must dedupe filenames rather than clobber")

        let firstDocument = try SnapshotCodec.read(Data(contentsOf: firstExport))
        let secondDocument = try SnapshotCodec.read(Data(contentsOf: secondExport))
        XCTAssertEqual(firstDocument.header.machineId, firstID)
        XCTAssertEqual(secondDocument.header.machineId, firstID)
    }

    // MARK: - Backup on import

    func testImportBacksUpExistingDatabaseFileBeforeMerging() throws {
        let tempDirectory = try makeTempDirectory()
        let dbURL = tempDirectory.appendingPathComponent("dvm_finance.sqlite")

        let liveDatabase = try AppDatabase.live(at: dbURL)
        try liveDatabase.dbWriter.write { db in
            var rule = CategorizationRuleRecord(ruleType: "full_description", matchPattern: "contains", matchValue: "x")
            try rule.insert(db)
        }
        XCTAssertTrue(FileManager.default.fileExists(atPath: dbURL.path))

        let emptyDocument = SnapshotDocument(
            header: SnapshotHeader(schemaVersion: 1, exportedAt: "2026-01-01T00:00:00", machineId: "test-machine"),
            transactions: [],
            rules: [],
            budgets: [],
            ruleChangeReports: []
        )
        _ = try SnapshotImporter.importSnapshot(appDatabase: liveDatabase, document: emptyDocument, databaseURL: dbURL)

        let siblingNames = try FileManager.default.contentsOfDirectory(atPath: tempDirectory.path)
        let backupNames = siblingNames.filter { $0.hasPrefix("dvm_finance.backup-") }
        XCTAssertFalse(backupNames.isEmpty, "expected a backup file in \(siblingNames)")

        // The backup must be a real, non-empty copy of the pre-import database.
        let backupURL = tempDirectory.appendingPathComponent(try XCTUnwrap(backupNames.first))
        let backupSize = try FileManager.default.attributesOfItem(atPath: backupURL.path)[.size] as? Int
        XCTAssertNotNil(backupSize)
        XCTAssertGreaterThan(backupSize ?? 0, 0)
    }

    func testImportDoesNotBackUpWhenNoDatabaseFileExists() throws {
        let tempDirectory = try makeTempDirectory()
        let dbURL = tempDirectory.appendingPathComponent("does-not-exist.sqlite")
        XCTAssertFalse(FileManager.default.fileExists(atPath: dbURL.path))

        let appDatabase = try AppDatabase.inMemory()
        let emptyDocument = SnapshotDocument(
            header: SnapshotHeader(schemaVersion: 1, exportedAt: "2026-01-01T00:00:00", machineId: "test-machine"),
            transactions: [],
            rules: [],
            budgets: [],
            ruleChangeReports: []
        )
        _ = try SnapshotImporter.importSnapshot(appDatabase: appDatabase, document: emptyDocument, databaseURL: dbURL)

        let siblingNames = try FileManager.default.contentsOfDirectory(atPath: tempDirectory.path)
        XCTAssertTrue(siblingNames.isEmpty, "no database file existed, so nothing should have been backed up")
    }
}
