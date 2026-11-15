import XCTest
import GRDB
@testable import DVMFinanceKit

/// Port of `tests/test_merge.py`.
///
/// The bank writes one SEPA payment in two description forms, and the two
/// forms give two different transaction ids. A database from before the
/// end-to-end reference check can therefore hold one payment twice. These
/// tests cover the discovery of such a group, the choice of the survivor, and
/// the refusal of a conflict.
final class MergeTests: XCTestCase {
    var appDatabase: AppDatabase!

    static let reference = "KFF5Q4D85TQK39G6"
    static let account = "720317081"

    override func setUpWithError() throws {
        appDatabase = try AppDatabase.inMemory()
    }

    override func tearDownWithError() throws {
        appDatabase = nil
    }

    private func makeDate() -> Date {
        var components = DateComponents()
        components.year = 2024
        components.month = 5
        components.day = 19
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        return calendar.date(from: components)!
    }

    /// Write one row. `structuredOnly` models a row from before the backfill:
    /// it holds the reference in the structured description only.
    @discardableResult
    private func insert(
        _ id: String,
        reference: String? = MergeTests.reference,
        account: String = MergeTests.account,
        manualCategory: String? = nil,
        manualTags: String? = nil,
        structuredOnly: Bool = false,
        sourceFile: String? = nil,
        amount: Double = -5.75
    ) throws -> TransactionRecord {
        var structured: String?
        if let reference {
            structured = "{\"format\": \"sepa\", \"end_to_end_reference\": \"\(reference)\"}"
        }
        let record = TransactionRecord(
            id: id,
            accountNumber: account,
            transactiondate: makeDate(),
            amount: Decimal(amount),
            description: "the description form \(id)",
            descriptionStructured: structured,
            manualCategory: manualCategory,
            manualTags: manualTags,
            currency: "EUR",
            sourceFile: sourceFile,
            endToEndReference: structuredOnly ? nil : reference
        )
        try appDatabase.dbWriter.write { db in try record.insert(db) }
        return record
    }

    private func preview() throws -> Merge.MergePreview {
        try appDatabase.dbWriter.read { db in try Merge.previewMerge(db: db) }
    }

    private func merge() throws -> Merge.MergePreview {
        try appDatabase.dbWriter.write { db in try Merge.mergeDuplicates(db: db) }
    }

    private func fetch(_ id: String) throws -> TransactionRecord? {
        try appDatabase.dbWriter.read { db in try TransactionRecord.fetchOne(db, key: id) }
    }

    // MARK: - The discovery of a group

    func testTwoRowsOfOneAccountMakeAGroup() throws {
        try insert("aaa")
        try insert("bbb")

        let result = try preview()

        XCTAssertEqual(result.groups.count, 1)
        XCTAssertEqual(result.groups[0].reference, Self.reference)
        XCTAssertEqual(result.groups[0].account, Self.account)
    }

    func testTwoAccountsMakeNoGroup() throws {
        try insert("aaa")
        try insert("bbb", account: "123456789")

        XCTAssertTrue(try preview().groups.isEmpty)
    }

    func testNonrefMakesNoGroup() throws {
        try insert("aaa", reference: "NONREF")
        try insert("bbb", reference: "NONREF")

        XCTAssertTrue(try preview().groups.isEmpty)
    }

    func testARowWithoutAReferenceMakesNoGroup() throws {
        try insert("aaa", reference: nil)
        try insert("bbb", reference: nil)

        XCTAssertTrue(try preview().groups.isEmpty)
    }

    func testASingleRowMakesNoGroup() throws {
        try insert("aaa")

        XCTAssertTrue(try preview().groups.isEmpty)
    }

    func testARowFromBeforeTheBackfillJoinsAGroup() throws {
        try insert("aaa", structuredOnly: true)
        try insert("bbb")

        XCTAssertEqual(try preview().groups.count, 1)
    }

    func testAnAlreadyMergedRowMakesNoGroup() throws {
        try insert("aaa")
        try insert("bbb")
        _ = try merge()

        XCTAssertTrue(try preview().groups.isEmpty)
    }

    // MARK: - The survivor is the lowest id

    func testTheSurvivorIsTheLowestID() throws {
        try insert("720317081_2024-05-19_-5.75_bbb")
        try insert("720317081_2024-05-19_-5.75_aaa")

        let group = try preview().groups[0]

        XCTAssertTrue(group.survivorID.hasSuffix("aaa"))
        XCTAssertEqual(group.mergedIDs, ["720317081_2024-05-19_-5.75_bbb"])
    }

    /// The choice must not depend on the source file. Two machines that pick
    /// different survivors would each flag the other's row, and a snapshot
    /// merge would then lose the payment.
    func testTheChoiceIgnoresTheSourceFile() throws {
        try insert("aaa", sourceFile: "zzz_last.mta")
        try insert("bbb", sourceFile: "aaa_first.sta")

        XCTAssertEqual(try preview().groups[0].survivorID, "aaa")
    }

    /// The desktop app picks the same survivor for the same group. The ids
    /// below are the ones `tests/test_merge.py` uses.
    func testTheChoiceMatchesThePythonPort() throws {
        try insert("zzz")
        try insert("aaa")

        XCTAssertEqual(try preview().groups[0].survivorID, "aaa")
    }

    // MARK: - The refusal of a conflict

    func testTwoDifferentManualCategoriesRefuseTheGroup() throws {
        try insert("aaa", manualCategory: "groceries")
        try insert("bbb", manualCategory: "restaurant")

        let result = try preview()

        XCTAssertTrue(result.groups.isEmpty)
        XCTAssertEqual(result.refused.count, 1)
        XCTAssertEqual(result.refused[0].manualCategories, ["groceries", "restaurant"])
    }

    func testARefusedGroupChangesNoRow() throws {
        try insert("aaa", manualCategory: "groceries")
        try insert("bbb", manualCategory: "restaurant")

        _ = try merge()

        for id in ["aaa", "bbb"] {
            let row = try fetch(id)
            XCTAssertNil(row?.deletedAt)
            XCTAssertNil(row?.mergedInto)
        }
    }

    func testTheSameManualCategoryMerges() throws {
        try insert("aaa", manualCategory: "groceries")
        try insert("bbb", manualCategory: "groceries")

        let result = try merge()

        XCTAssertEqual(result.groups.count, 1)
        XCTAssertTrue(result.refused.isEmpty)
        XCTAssertEqual(try fetch("bbb")?.mergedInto, "aaa")
    }

    // MARK: - The carried manual categorization

    func testTheMergeCarriesTheManualCategory() throws {
        try insert("aaa")
        try insert("bbb", manualCategory: "groceries")

        _ = try merge()

        XCTAssertEqual(try fetch("aaa")?.manualCategory, "groceries")
    }

    func testTheMergeKeepsTheManualCategoryOfTheSurvivor() throws {
        try insert("aaa", manualCategory: "groceries")
        try insert("bbb")

        _ = try merge()

        XCTAssertEqual(try fetch("aaa")?.manualCategory, "groceries")
    }

    func testTheMergeCarriesTheManualTags() throws {
        try insert("aaa")
        try insert("bbb", manualTags: "holiday")

        _ = try merge()

        XCTAssertEqual(try fetch("aaa")?.manualTags, "holiday")
    }

    // MARK: - The flag and the merged_into column

    func testTheMergeFlagsTheOtherRow() throws {
        try insert("aaa")
        try insert("bbb")

        _ = try merge()

        let other = try fetch("bbb")
        XCTAssertNotNil(other?.deletedAt)
        XCTAssertEqual(other?.mergedInto, "aaa")
        XCTAssertTrue(other?.isMerged == true)
        XCTAssertNil(try fetch("aaa")?.deletedAt)
    }

    func testTheMergeDeletesNoRow() throws {
        try insert("aaa")
        try insert("bbb")

        _ = try merge()

        let count = try appDatabase.dbWriter.read { db in
            try TransactionRecord.fetchCount(db)
        }
        XCTAssertEqual(count, 2)
    }

    // MARK: - The undo

    func testTheUndoBringsTheRowBack() throws {
        try insert("aaa")
        try insert("bbb")
        _ = try merge()

        let restored = try appDatabase.dbWriter.write { db in
            try Merge.undoMerge(db: db, survivorID: "aaa")
        }

        XCTAssertEqual(restored, ["bbb"])
        let other = try fetch("bbb")
        XCTAssertNil(other?.deletedAt)
        XCTAssertNil(other?.mergedInto)
    }

    func testTheUndoKeepsTheCarriedManualCategory() throws {
        try insert("aaa")
        try insert("bbb", manualCategory: "groceries")
        _ = try merge()

        _ = try appDatabase.dbWriter.write { db in
            try Merge.undoMerge(db: db, survivorID: "aaa")
        }

        XCTAssertEqual(try fetch("aaa")?.manualCategory, "groceries")
    }

    func testTheUndoReportsNothingWhenTheRowIsGone() throws {
        try insert("aaa")

        let restored = try appDatabase.dbWriter.write { db in
            try Merge.undoMerge(db: db, survivorID: "aaa")
        }

        XCTAssertTrue(restored.isEmpty)
    }

    // MARK: - The preview changes no row

    func testThePreviewChangesNoRow() throws {
        try insert("aaa")
        try insert("bbb")

        _ = try preview()

        XCTAssertNil(try fetch("bbb")?.deletedAt)
        XCTAssertNil(try fetch("bbb")?.mergedInto)
    }

    func testThePreviewCountsTheRows() throws {
        try insert("aaa")
        try insert("bbb")
        try insert("ccc")

        let result = try preview()

        XCTAssertEqual(result.rowCount, 2)
        XCTAssertEqual(result.groups[0].mergedIDs, ["bbb", "ccc"])
    }

    // MARK: - The values and the pairs that the real statement holds

    /// `tests/fixtures/mt940_sample.STA` holds `NOTPROVIDED` 136 times.
    /// Without this exclusion the merge would fold 136 unrelated payments.
    func testNotprovidedMakesNoGroup() throws {
        try insert("aaa", reference: "NOTPROVIDED")
        try insert("bbb", reference: "NOTPROVIDED")
        try insert("ccc", reference: "NOTPROVIDED")

        XCTAssertTrue(try preview().groups.isEmpty)
    }

    /// An MT940 description wraps, so the sentinel also appears split. The
    /// sample statement holds `NOTP ROVIDED` three times.
    func testASplitSentinelMakesNoGroup() throws {
        try insert("aaa", reference: "NOTP ROVIDED")
        try insert("bbb", reference: "NOTPROVIDED")

        XCTAssertTrue(try preview().groups.isEmpty)
    }

    /// A reversal carries the reference of the payment that it reverses, with
    /// the opposite sign. Those are two transactions, and the merge must keep
    /// both. The amount belongs to the match key for this reason.
    func testAReversalIsNotADuplicate() throws {
        try insert("aaa", amount: -149.88)
        try insert("bbb", amount: 149.88)

        XCTAssertTrue(try preview().groups.isEmpty)
    }

    /// The amount in the key does not break the case that the change targets.
    func testTheTwoFormsOfOnePaymentStillMerge() throws {
        try insert("aaa", amount: -5.75)
        try insert("bbb", amount: -5.75)

        XCTAssertEqual(try preview().groups.count, 1)
    }

    // MARK: - The purge keeps a merged row

    /// Port of `test_the_purge_keeps_a_merged_row` in `tests/test_manual_txn.py`.
    ///
    /// A purge of a merged row would free its id, and the next import would
    /// write the duplicate again.
    func testThePurgeKeepsAMergedRow() throws {
        try insert("aaa")
        try insert("bbb")
        _ = try merge()

        let flagged = try appDatabase.dbWriter.read { db in
            try ManualTransactions.flaggedTransactions(db: db)
        }
        XCTAssertTrue(flagged.isEmpty, "the list holds only a row that the user flagged")

        let count = try appDatabase.dbWriter.read { db in
            try ManualTransactions.flaggedCount(db: db)
        }
        XCTAssertEqual(count, 0)
    }
}

// MARK: - The one-time passes

/// Port of `tests/test_restructure.py`.
///
/// The rules read the stored structured description, so a rename of a key in
/// the parser changes nothing for a row that the app already stored. The pass
/// reparses such a row and renames the field target of each affected rule.
final class RestructureTests: XCTestCase {
    var appDatabase: AppDatabase!

    static let tagged =
        "/TRTP/SEPA INCASSO ALGEMEEN DOORLOPEND/CSID/VP20XNL847867841319 "
        + "/NAME/LEBARA/MARF/B0OXIVC5T2O3ZJ58/REMI/LEBARA NL-039442543-277 "
        + "/IBAN/NL65ADYB0257164544/BIC/ADYBNL2A/EREF/KFF5Q4D85TQK39G6"
    static let labelled =
        "SEPA INCASSO ALGEMEEN DOORLOPEND INCASSANT: VP20XNL847867841319 "
        + "NAAM: LEBARA MACHTIGING: B0OXIVC5T2O3ZJ58 "
        + "OMSCHRIJVING: LEBARA NL-03944254 3-277 IBAN: NL65ADYB0257164544 "
        + "KENMERK: KFF5Q4D85TQK39G6"

    /// The shape that the old tagged parser stored.
    static let oldTaggedStructured = """
    {"transaction_type": "SEPA INCASSO ALGEMEEN DOORLOPEND",
     "other_fields": {"CSID": "VP20XNL847867841319", "MARF": "B0OXIVC5T2O3ZJ58"},
     "name": "LEBARA", "remittance_info": "LEBARA NL-039442543-277",
     "iban": "NL65ADYB0257164544", "bic": "ADYBNL2A",
     "end_to_end_reference": "KFF5Q4D85TQK39G6", "format": "mt940"}
    """

    /// The shape that the old labelled parser stored.
    static let oldLabelledStructured = """
    {"sepa_type": "INCASSO", "transaction_type": "SEPA Direct Debit",
     "direct_debit_type": "General", "recurring": true,
     "iban": "NL65ADYB0257164544", "name": "LEBARA",
     "description": "LEBARA NL-03944254 3-277",
     "creditor_identifier": "VP20XNL847867841319",
     "mandate_reference": "B0OXIVC5T2O3ZJ58",
     "reference": "KFF5Q4D85TQK39G6", "format": "sepa"}
    """

    override func setUpWithError() throws {
        appDatabase = try AppDatabase.inMemory()
    }

    override func tearDownWithError() throws {
        appDatabase = nil
    }

    private func add(_ id: String, _ description: String, _ structured: String) throws {
        var components = DateComponents()
        components.year = 2024
        components.month = 5
        components.day = 19
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        let record = TransactionRecord(
            id: id,
            accountNumber: "720317081",
            transactiondate: calendar.date(from: components)!,
            amount: Decimal(-5.75),
            description: description,
            descriptionStructured: structured,
            currency: "EUR"
        )
        try appDatabase.dbWriter.write { db in try record.insert(db) }
    }

    private func structured(_ id: String) throws -> [String: Any] {
        let row = try appDatabase.dbWriter.read { db in
            try TransactionRecord.fetchOne(db, key: id)
        }
        let raw = try XCTUnwrap(row?.descriptionStructured)
        let data = try XCTUnwrap(raw.data(using: .utf8))
        return try XCTUnwrap(
            try JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
    }

    func testThePassRewritesAStoredTaggedRow() throws {
        try add("tagged", Self.tagged, Self.oldTaggedStructured)

        let count = try Restructure.runOnce(appDatabase: appDatabase).rows
        XCTAssertEqual(count, 1)

        let data = try structured("tagged")
        XCTAssertEqual(data["creditor_identifier"] as? String, "VP20XNL847867841319")
        XCTAssertEqual(data["mandate_reference"] as? String, "B0OXIVC5T2O3ZJ58")
        XCTAssertEqual(data["format"] as? String, "sepa")
        XCTAssertEqual(data["transaction_type"] as? String, "SEPA Direct Debit")
        XCTAssertNil(data["other_fields"])
    }

    func testThePassRewritesAStoredLabelledRow() throws {
        try add("labelled", Self.labelled, Self.oldLabelledStructured)

        _ = try Restructure.runOnce(appDatabase: appDatabase)

        let data = try structured("labelled")
        XCTAssertEqual(data["remittance_info"] as? String, "LEBARA NL-03944254 3-277")
        XCTAssertEqual(data["end_to_end_reference"] as? String, "KFF5Q4D85TQK39G6")
        XCTAssertNil(data["description"])
        XCTAssertNil(data["reference"])
    }

    func testThePassFillsTheReferenceColumn() throws {
        try add("tagged", Self.tagged, Self.oldTaggedStructured)

        _ = try Restructure.runOnce(appDatabase: appDatabase)

        let row = try appDatabase.dbWriter.read { db in
            try TransactionRecord.fetchOne(db, key: "tagged")
        }
        XCTAssertEqual(row?.endToEndReference, "KFF5Q4D85TQK39G6")
    }

    func testThePassIsIdempotent() throws {
        try add("tagged", Self.tagged, Self.oldTaggedStructured)
        try add("labelled", Self.labelled, Self.oldLabelledStructured)

        XCTAssertEqual(try Restructure.runOnce(appDatabase: appDatabase).rows, 2)
        XCTAssertEqual(try Restructure.runOnce(appDatabase: appDatabase).rows, 0)
    }

    // MARK: The field target of a rule

    private func addRule(
        fieldTarget: String,
        ruleType: String = "structured_field"
    ) throws -> String {
        let uuid = UUID().uuidString
        var rule = CategorizationRuleRecord(
            uuid: uuid,
            priority: 100,
            ruleType: ruleType,
            matchPattern: "contains",
            fieldTarget: fieldTarget,
            matchValue: "KFF5Q4D85TQK39G6",
            category: "utilities",
            isActive: true
        )
        try appDatabase.dbWriter.write { db in try rule.insert(db) }
        return uuid
    }

    private func ruleTarget(_ uuid: String) throws -> String? {
        try appDatabase.dbWriter.read { db in
            try CategorizationRuleRecord
                .filter(Column("uuid") == uuid)
                .fetchOne(db)?
                .fieldTarget
        }
    }

    func testTheMigrationRenamesTheReferenceTarget() throws {
        let uuid = try addRule(fieldTarget: "reference")

        _ = try Restructure.runOnce(appDatabase: appDatabase)

        XCTAssertEqual(try ruleTarget(uuid), "end_to_end_reference")
    }

    func testTheMigrationRenamesAStructuredDescriptionTarget() throws {
        let uuid = try addRule(fieldTarget: "description")

        _ = try Restructure.runOnce(appDatabase: appDatabase)

        XCTAssertEqual(try ruleTarget(uuid), "remittance_info")
    }

    /// That target names the raw text, and not a structured key.
    func testTheMigrationLeavesAFullDescriptionRule() throws {
        let uuid = try addRule(fieldTarget: "description", ruleType: "full_description")

        _ = try Restructure.runOnce(appDatabase: appDatabase)

        XCTAssertEqual(try ruleTarget(uuid), "description")
    }

    func testTheMigrationLeavesAKeywordRuleOnTheDescription() throws {
        let uuid = try addRule(fieldTarget: "description", ruleType: "keyword")

        _ = try Restructure.runOnce(appDatabase: appDatabase)

        XCTAssertEqual(try ruleTarget(uuid), "description")
    }

    func testTheMigrationIsIdempotent() throws {
        _ = try addRule(fieldTarget: "reference")

        XCTAssertEqual(try Restructure.runOnce(appDatabase: appDatabase).rules, 1)
        XCTAssertEqual(try Restructure.runOnce(appDatabase: appDatabase).rules, 0)
    }
}

// MARK: - The amount key agrees with the Python port

/// The match key decides which rows form a group. A divergence between the two
/// apps would mean they merge different sets, which is the cross-machine
/// disagreement that the lowest-id survivor rule exists to prevent.
final class AmountKeyParityTests: XCTestCase {

    /// Each pair is `(amount, the string that `core/dedup.py:_amount_key`
    /// returns for it)`.
    func testTheAmountKeyMatchesThePythonPort() {
        let cases: [(Double, String)] = [
            (-149.88, "-149.88"),
            (-5.75, "-5.75"),
            (0, "0.00"),
            (-0.0, "-0.00"),
            (104.99, "104.99"),
            (1458.32, "1458.32"),
            (-1, "-1.00"),
        ]
        for (amount, expected) in cases {
            XCTAssertEqual(Dedup.amountKey(amount), expected, "for \(amount)")
        }
    }

    func testAnAbsentAmountGivesTheEmptyKey() {
        XCTAssertEqual(Dedup.amountKey(nil), "")
    }
}

// MARK: - The stored report

/// The `transaction-merge` delta requires the merge to store a report. These
/// cover the Swift port of that requirement.
extension MergeTests {

    private func reports() throws -> [MergeReportRecord] {
        try appDatabase.dbWriter.read { db in try MergeReportRecord.fetchAll(db) }
    }

    private func object(_ raw: String?) throws -> Any {
        let data = try XCTUnwrap(try XCTUnwrap(raw).data(using: .utf8))
        return try JSONSerialization.jsonObject(with: data)
    }

    func testTheMergeStoresAReport() throws {
        try insert("aaa")
        try insert("bbb", manualCategory: "groceries")

        _ = try merge()

        let report = try XCTUnwrap(try reports().first)
        let summary = try XCTUnwrap(try object(report.summary) as? [String: Any])
        XCTAssertEqual(summary["groups"] as? Int, 1)
        XCTAssertEqual(summary["rows"] as? Int, 1)
        XCTAssertEqual(summary["refused"] as? Int, 0)

        let groups = try XCTUnwrap(try object(report.groups) as? [[String: Any]])
        XCTAssertEqual(groups[0]["survivor_id"] as? String, "aaa")
        XCTAssertEqual(groups[0]["merged_ids"] as? [String], ["bbb"])
        XCTAssertEqual(groups[0]["carried_category"] as? String, "groceries")
    }

    func testTheReportNamesARefusedGroup() throws {
        try insert("aaa", manualCategory: "groceries")
        try insert("bbb", manualCategory: "restaurant")

        _ = try merge()

        let report = try XCTUnwrap(try reports().first)
        let summary = try XCTUnwrap(try object(report.summary) as? [String: Any])
        XCTAssertEqual(summary["refused"] as? Int, 1)

        let refused = try XCTUnwrap(try object(report.refused) as? [[String: Any]])
        XCTAssertEqual(refused[0]["row_ids"] as? [String], ["aaa", "bbb"])
        XCTAssertEqual(
            refused[0]["manual_categories"] as? [String], ["groceries", "restaurant"]
        )
    }

    func testNoReportWithoutAGroup() throws {
        try insert("aaa")

        _ = try merge()

        XCTAssertTrue(try reports().isEmpty)
    }
}

// MARK: - The separators of one reference

/// Port of the separator group of `tests/test_dedup.py`.
///
/// The bank prints one reference with different separators in the two
/// description forms, and an MT940 description wraps at a fixed width so the
/// wrap can fall inside the reference. Each value below comes from a real
/// database of 7202 rows.
final class ReferenceNormalizationTests: XCTestCase {

    func testNormalizeReferenceRemovesEachSeparator() {
        XCTAssertEqual(
            Dedup.normalizeReference("04-06-2026 21:42 737082 4431202372"),
            "0406202621:427370824431202372"
        )
        XCTAssertEqual(
            Dedup.normalizeReference("8022.7644 .9692.6345"), "8022764496926345"
        )
        XCTAssertEqual(Dedup.normalizeReference("notprovided"), "NOTPROVIDED")
    }

    /// The two spellings of one reference give one comparison form.
    func testTheTwoSpellingsAgree() {
        let pairs = [
            ("30-05-2026 13:49 7180855028127978", "30-05-2026 13:49 718085 5028127978"),
            ("8022764496926345", "8022.7644 .9692.6345"),
            ("19-12- 2025 23:25 7051286296203069", "19-12 2025 23:25 7051286296203069"),
            ("DLT2026061909320000T010033153", "DLT-2026061909320000T010033153"),
        ]
        for (a, b) in pairs {
            XCTAssertEqual(
                Dedup.normalizeReference(a), Dedup.normalizeReference(b),
                "\(a) against \(b)"
            )
        }
    }

    /// The real database holds `NOTPROVIDE D` and `NOTPROV IDED`.
    func testASplitSentinelIsStillASentinel() {
        for value in ["NOTPROVIDE D", "NOTPROV IDED", "NOT-PROVIDED", "NONREF"] {
            XCTAssertTrue(Dedup.isUnusableReference(value), value)
        }
        XCTAssertFalse(Dedup.isUnusableReference("8022.7644 .9692.6345"))
    }
}

extension MergeTests {

    /// One reference, printed with different separators in the two forms.
    func testDifferentSeparatorsStillMerge() throws {
        try insert("aaa", reference: "8022764496926345")
        try insert("bbb", reference: "8022.7644 .9692.6345")

        let result = try preview()

        XCTAssertEqual(result.groups.count, 1)
        XCTAssertEqual(result.groups[0].survivorID, "aaa")
    }

    /// The report names what the bank wrote, and not the comparison form.
    func testTheGroupReportsTheOriginalReference() throws {
        try insert("aaa", reference: "8022.7644 .9692.6345")
        try insert("bbb", reference: "8022764496926345")

        XCTAssertEqual(try preview().groups[0].reference, "8022.7644 .9692.6345")
    }

    /// The amount still separates a payment from its reversal.
    func testTheNormalizationKeepsAReversalApart() throws {
        try insert("aaa", reference: "BAE3765 3137668063490036", amount: -65.13)
        try insert("bbb", reference: "BAE37653137668063490036", amount: 65.13)

        XCTAssertTrue(try preview().groups.isEmpty)
    }
}

// MARK: - The date belongs to the group key

/// The first implementation of the discovery dropped the date from the
/// counterparty group key. Each monthly transfer of one amount to one account
/// then joined one group. On a real database that produced a group of 21 rows
/// spanning two years.
extension MergeTests {

    private func insertTransfer(
        _ id: String,
        when: DateComponents,
        amount: Double = -200.00,
        sourceFile: String
    ) throws {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        let record = TransactionRecord(
            id: id,
            accountNumber: MergeTests.account,
            transactiondate: calendar.date(from: when)!,
            amount: Decimal(amount),
            description: "SEPA OVERBOEKING NL92ABNA8756430569 \(id)",
            descriptionStructured: """
            {"format": "sepa", "iban": "NL92ABNA8756430569",
             "end_to_end_reference": "NOTPROVIDED"}
            """,
            currency: "EUR",
            sourceFile: sourceFile
        )
        try appDatabase.dbWriter.write { db in try record.insert(db) }
    }

    func testTheGroupKeyHoldsTheDate() throws {
        try insertTransfer(
            "jan", when: DateComponents(year: 2026, month: 1, day: 20),
            sourceFile: "a.STA"
        )
        try insertTransfer(
            "feb", when: DateComponents(year: 2026, month: 2, day: 20),
            sourceFile: "b.STA"
        )

        let result = try preview()

        XCTAssertTrue(result.groups.isEmpty)
        XCTAssertTrue(result.refused.isEmpty)
    }

    func testAMonthlyTransferMakesNoGroup() throws {
        for month in 1...12 {
            try insertTransfer(
                "m\(month)",
                when: DateComponents(year: 2026, month: month, day: 20),
                sourceFile: "download\(month).STA"
            )
        }

        let result = try preview()

        XCTAssertTrue(
            result.groups.isEmpty,
            "a monthly transfer must not form a group: \(result.groups.count)"
        )
    }

    func testATransferPairOfOneDateMerges() throws {
        try insertTransfer(
            "aaa", when: DateComponents(year: 2026, month: 1, day: 20),
            sourceFile: "a.STA"
        )
        try insertTransfer(
            "bbb", when: DateComponents(year: 2026, month: 1, day: 20),
            sourceFile: "b.STA"
        )

        let result = try preview()

        XCTAssertEqual(result.groups.count, 1)
        XCTAssertEqual(result.groups[0].matchedBy, "counterparty")
        XCTAssertEqual(result.groups[0].survivorID, "aaa")
    }

    func testTwoTransfersOfOneFileRefuse() throws {
        try insertTransfer(
            "aaa", when: DateComponents(year: 2026, month: 1, day: 20),
            sourceFile: "a.STA"
        )
        try insertTransfer(
            "bbb", when: DateComponents(year: 2026, month: 1, day: 20),
            sourceFile: "a.STA"
        )

        let result = try preview()

        XCTAssertTrue(result.groups.isEmpty)
        XCTAssertEqual(result.refused.count, 1)
        XCTAssertEqual(result.refused[0].matchedBy, "counterparty")
    }
}
