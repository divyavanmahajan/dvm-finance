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
            "BEA, BETAALPAS                   KERMISEXPLOITATIE,PAS603 NR:23G0D8, 19.05.24/14:33        WEERT"
        let expected = try expectedObject(#"""
        {"transaction_type": "POS", "payment_method": "Betaalpas", "merchant_name": "KERMISEXPLOITATIE",
         "card_terminal_id": "603", "transaction_reference": "23G0D8", "transaction_date": "2024-05-19",
         "transaction_time": "14:33", "location": "WEERT", "format": "pos"}
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
            "BEA, BETAALPAS                   PINAP 2,PAS603 NR:90306456, 19.05.24/15:12      APELDOORN"
        // Ground truth: no "*" in "PINAP 2" so no merchant_code; foreign
        // currency comes from parser_expected.json's first-5 fixture row 4
        // (`"foreign_currency": "NAP", "foreign_amount": 2.0`) — the
        // `([A-Z]{3})\s+([\d.,]+)` regex incidentally matches "NAP 2" from
        // the merchant name itself.
        let expected = try expectedObject(#"""
        {"transaction_type": "POS", "payment_method": "Betaalpas", "merchant_name": "PINAP 2",
         "card_terminal_id": "603", "transaction_reference": "90306456", "transaction_date": "2024-05-19",
         "transaction_time": "15:12", "location": "APELDOORN", "foreign_currency": "NAP",
         "foreign_amount": 2.0, "format": "pos"}
        """#)
        let actual = try actualObject(DescriptionParser.parsePOSDescription(description))
        XCTAssertEqual(actual, expected)
    }

    // MARK: - MT940 SEPA OVERBOEKING + Tikkie (mt940_sample.STA:2328-2330)

    func testMT940TikkieSEPAOverboeking() throws {
        let description =
            "/TRTP/SEPA OVERBOEKING/IBAN/NL13ABNA0506417344/BIC/ABNANL2A/NAME/ AAB INZ TIKKIE/REMI/TIKKIE ID 001105143313, BRUH, VAN A VAN MAHAJ AN, NL21ABNA0869690930/EREF/1105143313"
        let expected = try expectedObject(#"""
        {"transaction_type": "SEPA OVERBOEKING", "iban": "NL13ABNA0506417344", "bic": "ABNANL2A",
         "name": "AAB INZ TIKKIE",
         "remittance_info": "TIKKIE ID 001105143313, BRUH, VAN A VAN MAHAJ AN, NL21ABNA0869690930",
         "end_to_end_reference": "1105143313", "format": "mt940", "is_tikkie": true,
         "payment_service": "Tikkie", "tikkie_id": "001105143313",
         "payer_name": "VAN A VAN MAHAJ AN", "payer_iban": "NL21ABNA0869690930"}
        """#)
        let actual = try actualObject(DescriptionParser.parseMT940Description(description))
        XCTAssertEqual(actual, expected)
    }

    // MARK: - MT940 IDEAL + Tikkie, full field extraction (mt940_sample.STA:2429-2431)

    func testMT940TikkieIDEAL() throws {
        let description =
            "/TRTP/IDEAL/IBAN/NL13ABNA0506417344/BIC/ABNANL2A/NAME/VAN MAHAJAN VIA TIKKIE/REMI/001112686692 0031855697994810 FOR THE COIN NL21A BNA0869690930/EREF/23-10-2025 23:57 0031855697994810"
        let expected = try expectedObject(#"""
        {"transaction_type": "IDEAL", "iban": "NL13ABNA0506417344", "bic": "ABNANL2A",
         "name": "VAN MAHAJAN VIA TIKKIE",
         "remittance_info": "001112686692 0031855697994810 FOR THE COIN NL21A BNA0869690930",
         "end_to_end_reference": "23-10-2025 23:57 0031855697994810", "format": "mt940",
         "is_tikkie": true, "payment_service": "Tikkie", "tikkie_id": "001112686692",
         "payment_reference": "0031855697994810", "payer_iban": "NL21ABNA0869690930",
         "payment_description": "FOR THE COIN", "payer_name": "VAN MAHAJAN",
         "tikkie_timestamp": "23-10-2025 23:57"}
        """#)
        let actual = try actualObject(DescriptionParser.parseMT940Description(description))
        XCTAssertEqual(actual, expected)
    }

    // MARK: - SEPA INCASSO (direct debit) (mt940_sample.STA:2653-2655)

    func testSEPAIncassoGeneralRecurring() throws {
        let description =
            "SEPA INCASSO ALGEMEEN DOORLOPEND INCASSANT: NL37ZZZ801111060000 NAAM: XPLOR-ANYTIME FITNESS      MACHTIGING: ANYTIME-NL-4597629 IBAN: NL77RABO0362406480         KENMERK: 39857858-65913"
        let expected = try expectedObject(#"""
        {"sepa_type": "INCASSO", "transaction_type": "SEPA Direct Debit", "direct_debit_type": "General",
         "recurring": true, "iban": "NL77RABO0362406480", "name": "XPLOR-ANYTIME FITNESS",
         "creditor_identifier": "NL37ZZZ801111060000", "mandate_reference": "ANYTIME-NL-4597629",
         "reference": "39857858-65913", "format": "sepa"}
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
        let description = "/TRTP/BETALING/CSID/XYZ123/"
        let expected = try expectedObject(#"""
        {"transaction_type": "BETALING", "other_fields": {"CSID": "XYZ123"}, "format": "mt940"}
        """#)
        let actual = try actualObject(DescriptionParser.parseMT940Description(description))
        XCTAssertEqual(actual, expected)
    }
}
