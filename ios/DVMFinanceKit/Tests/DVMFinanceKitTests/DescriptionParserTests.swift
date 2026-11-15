import XCTest
@testable import DVMFinanceKit

/// Unit tests for `DescriptionParser.swift` (port of
/// `src/abn_combined/parsers/description.py`), covering one representative
/// description string per family. Every expected JSON blob below was
/// produced by running the **real** `parse_transaction_description` against
/// description text pulled verbatim (continuation lines joined with a single
/// space, matching `mt940.py:86`'s `:86:` accumulation) from
/// `Fixtures/mt940_sample.STA` — see the comment above each case for the
/// exact source lines. This is independent, finer-grained coverage beyond
/// `ParserTests.swift`'s whole-file fixture parity (which only checks the
/// first/last 5 of 2291 MT940 rows and happens not to hit the Tikkie/SEPA
/// INCASSO/account-balance branches).
final class DescriptionParserTests: XCTestCase {

    /// Parses `json` (a JSON object literal) into `[String: Any]` for
    /// comparison against `DescriptionParser`'s output.
    private func expectedObject(_ json: String) throws -> NSDictionary {
        let data = Data(json.utf8)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? NSDictionary)
    }

    private func actualObject(_ jsonString: String?, file: StaticString = #filePath, line: UInt = #line) throws -> NSDictionary {
        let jsonString = try XCTUnwrap(jsonString, "expected a non-nil JSON string", file: file, line: line)
        let data = Data(jsonString.utf8)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? NSDictionary, file: file, line: line)
    }

    // MARK: - POS (mt940_sample.STA:9-10, also parser_expected.json's first MT940 row)

    func testPOSBetaalpasWithMerchantName() throws {
        let description =
            "BEA, BETAALPAS                   PWKEDZSPWTHROJTQL,PAS603 NR:23G0D8, 19.05.24/14:33        XYGPF"
        let expected = try expectedObject(#"""
        {"transaction_type": "POS", "payment_method": "Betaalpas", "merchant_name": "PWKEDZSPWTHROJTQL",
         "card_terminal_id": "603", "transaction_reference": "23G0D8", "transaction_date": "2024-05-19",
         "transaction_time": "14:33", "location": "XYGPF", "format": "pos"}
        """#)
        let actual = try actualObject(DescriptionParser.parsePOSDescription(description))
        XCTAssertEqual(actual, expected)
        // Dispatcher must reach the same result via POS (MT940/account-balance/SEPA all decline first).
        let dispatched = try actualObject(DescriptionParser.parseTransactionDescription(description))
        XCTAssertEqual(dispatched, expected)
    }

    // MARK: - POS with a merchant code (CODE*MERCHANT) and foreign currency (mt940_sample.STA:17-19)

    func testPOSMerchantCodeAndForeignCurrency() throws {
        let description =
            "BEA, BETAALPAS                   DHYTO 2,PAS603 NR:89518832, 19.05.24/15:12      APELDOORN"
        // Ground truth: no "*" in "DHYTO 2" so no merchant_code; foreign
        // currency comes from parser_expected.json's first-5 fixture row 4
        // (`"foreign_currency": "YTO", "foreign_amount": 2.0`) — the
        // `([A-Z]{3})\s+([\d.,]+)` regex incidentally matches "YTO 2" from
        // the merchant name itself.
        let expected = try expectedObject(#"""
        {"transaction_type": "POS", "payment_method": "Betaalpas", "merchant_name": "DHYTO 2",
         "card_terminal_id": "603", "transaction_reference": "89518832", "transaction_date": "2024-05-19",
         "transaction_time": "15:12", "location": "APELDOORN", "foreign_currency": "YTO",
         "foreign_amount": 2.0, "format": "pos"}
        """#)
        let actual = try actualObject(DescriptionParser.parsePOSDescription(description))
        XCTAssertEqual(actual, expected)
    }

    // MARK: - MT940 SEPA OVERBOEKING + Tikkie (mt940_sample.STA:2328-2330)

    func testMT940TikkieSEPAOverboeking() throws {
        let description =
            "/TRTP/SEPA OVERBOEKING/IBAN/NL13ABNA8992624444/BIC/ABNANL2A/NAME/ AAB INZ TIKKIE/REMI/TIKKIE ID 584357511540, BRUH, VAN A VAN LCJFO ST, NL21ABNA9847172551/EREF/4364003958"
        let expected = try expectedObject(#"""
        {"transaction_type": "SEPA Transfer", "sepa_type": "OVERBOEKING",
         "iban": "NL13ABNA8992624444", "bic": "ABNANL2A",
         "name": "AAB INZ TIKKIE",
         "remittance_info": "TIKKIE ID 584357511540, BRUH, VAN A VAN LCJFO ST, NL21ABNA9847172551",
         "end_to_end_reference": "4364003958", "format": "sepa", "is_tikkie": true,
         "payment_service": "Tikkie", "tikkie_id": "584357511540",
         "payer_name": "VAN A VAN LCJFO ST", "payer_iban": "NL21ABNA9847172551"}
        """#)
        let actual = try actualObject(DescriptionParser.parseMT940Description(description))
        XCTAssertEqual(actual, expected)
    }

    // MARK: - MT940 IDEAL + Tikkie, full field extraction (mt940_sample.STA:2429-2431)

    func testMT940TikkieIDEAL() throws {
        let description =
            "/TRTP/IDEAL/IBAN/NL13ABNA8992624444/BIC/ABNANL2A/NAME/VAN LCJFOST VIA TIKKIE/REMI/133916989819 6199124765088459 FOR THE COIN NL21A BNA9847172551/EREF/23-10-2025 23:57 6199124765088459"
        let expected = try expectedObject(#"""
        {"transaction_type": "IDEAL", "iban": "NL13ABNA8992624444", "bic": "ABNANL2A",
         "name": "VAN LCJFOST VIA TIKKIE",
         "remittance_info": "133916989819 6199124765088459 FOR THE COIN NL21A BNA9847172551",
         "end_to_end_reference": "23-10-2025 23:57 6199124765088459", "format": "mt940",
         "is_tikkie": true, "payment_service": "Tikkie", "tikkie_id": "133916989819",
         "payment_reference": "6199124765088459", "payer_iban": "NL21ABNA9847172551",
         "payment_description": "FOR THE COIN", "payer_name": "VAN LCJFOST",
         "tikkie_timestamp": "23-10-2025 23:57"}
        """#)
        let actual = try actualObject(DescriptionParser.parseMT940Description(description))
        XCTAssertEqual(actual, expected)
    }

    // MARK: - SEPA INCASSO (direct debit) (mt940_sample.STA:2653-2655)

    func testSEPAIncassoGeneralRecurring() throws {
        let description =
            "SEPA INCASSO ALGEMEEN DOORLOPEND INCASSANT: TF45FAQ873822907467 NAAM: VRAWD-KFQONIZ FITNESS      MACHTIGING: ANYTIME-NL-5363362 IBAN: NL77RABO8509119907         KENMERK: 39857858-65913"
        let expected = try expectedObject(#"""
        {"sepa_type": "INCASSO", "transaction_type": "SEPA Direct Debit", "direct_debit_type": "General",
         "recurring": true, "iban": "NL77RABO8509119907", "name": "VRAWD-KFQONIZ FITNESS",
         "creditor_identifier": "TF45FAQ873822907467", "mandate_reference": "ANYTIME-NL-5363362",
         "end_to_end_reference": "39857858-65913", "format": "sepa"}
        """#)
        let actual = try actualObject(DescriptionParser.parseSEPADescription(description))
        XCTAssertEqual(actual, expected)
        // MT940 declines (no /FIELD/ tokens), account-balance declines, so the
        // dispatcher must reach SEPA.
        let dispatched = try actualObject(DescriptionParser.parseTransactionDescription(description))
        XCTAssertEqual(dispatched, expected)
    }

    // MARK: - Account balance / credit interest (mt940_sample.STA:12582-12584)
    //
    // A deliberately tricky case: the `[CD]\s+` alternative in the
    // `additional_info` regex matches the "D" at the end of "BALANCED"
    // (followed by run of spaces) *before* it would reach "TO 30.06.2024" or
    // the amount's own trailing "C" — `re.search`'s leftmost-match plus a
    // greedy `.+` then swallows everything from "CREDIT INTEREST..." to the
    // end of the string. Confirms `regexSearch`'s leftmost/greedy semantics
    // agree with Python's `re` module for this pattern.

    func testAccountBalanceCreditInterest() throws {
        let description =
            "ACCOUNT BALANCED                 CREDIT INTEREST            0,44C FROM 31.03.2024 TO 30.06.2024    DIRECT SPAREN FOR INTEREST RATES PLEASE VISIT  WWW.ABNAMRO.NL/RENTE"
        let expected = try expectedObject(#"""
        {"format": "account_balance", "transaction_type": "Credit Interest", "interest_type": "CREDIT INTEREST",
         "amount": 0.44, "amount_indicator": "C", "is_credit": true, "period_from": "2024-03-31",
         "period_to": "2024-06-30",
         "additional_info": "CREDIT INTEREST            0,44C FROM 31.03.2024 TO 30.06.2024    DIRECT SPAREN FOR INTEREST RATES PLEASE VISIT  WWW.ABNAMRO.NL/RENTE",
         "url": "WWW.ABNAMRO.NL/RENTE"}
        """#)
        let actual = try actualObject(DescriptionParser.parseAccountBalanceDescription(description))
        XCTAssertEqual(actual, expected)
        let dispatched = try actualObject(DescriptionParser.parseTransactionDescription(description))
        XCTAssertEqual(dispatched, expected)
    }

    // MARK: - Dispatcher short-circuit / no-match

    func testDispatcherReturnsNilForPlainText() {
        XCTAssertNil(DescriptionParser.parseTransactionDescription("just a plain description with no markers"))
    }

    func testDispatcherReturnsNilForEmptyOrNilInput() {
        XCTAssertNil(DescriptionParser.parseTransactionDescription(""))
        XCTAssertNil(DescriptionParser.parseTransactionDescription(nil))
    }

    // MARK: - MT940 with an unrecognized field tag (other_fields nesting)

    func testMT940UnknownFieldGoesToOtherFields() throws {
        // `ZZZZ` is a tag that the parser does not know. `CSID` used to serve
        // as the example here, but it is now a known tag that maps to
        // `creditor_identifier`, so it no longer reaches `other_fields`.
        let description = "/TRTP/BETALING/ZZZZ/XYZ123/"
        let expected = try expectedObject(#"""
        {"transaction_type": "BETALING", "other_fields": {"ZZZZ": "XYZ123"}, "format": "mt940"}
        """#)
        let actual = try actualObject(DescriptionParser.parseMT940Description(description))
        XCTAssertEqual(actual, expected)
    }

    // MARK: - CSID and MARF are known tags

    /// Port of `test_tagged_form_promotes_csid_and_marf` in
    /// `tests/test_parsers.py`. A non-SEPA transaction type keeps the format
    /// `mt940`, and the two tags still take their canonical keys.
    func testMT940PromotesCSIDOutOfOtherFields() throws {
        let description = "/TRTP/BETALING/CSID/XYZ123/"
        let expected = try expectedObject(#"""
        {"transaction_type": "BETALING", "creditor_identifier": "XYZ123", "format": "mt940"}
        """#)
        let actual = try actualObject(DescriptionParser.parseMT940Description(description))
        XCTAssertEqual(actual, expected)
    }
}
