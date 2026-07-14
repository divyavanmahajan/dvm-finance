import Foundation

/// Port of `src/abn_combined/parsers/description.py` (708 lines) — structured
/// extraction of `description_structured`. Required for rule parity:
/// snapshot-imported `structured_field`/`account_iban` rules match on these
/// JSON fields (see `Categorizer.swift`), so any divergence here silently
/// breaks categorization on the phone.
///
/// Every public function returns a JSON **string** (matching Python's
/// `json.dumps(result, ensure_ascii=False)` stored into
/// `description_structured`), or `nil` when the Python function would return
/// `None`. Key *order* need not match Python (callers/tests compare parsed
/// JSON), but every *value*'s JSON type must match Python's exactly: strings
/// stay strings, booleans stay `true`/`false` literals (not `"true"`), and
/// numbers are encoded the way Python's `json.dumps(float)` renders a
/// `float` (shortest round-trip decimal, e.g. `2.0` not `2`).
public enum DescriptionParser {

    // MARK: - parse_transaction_description (description.py:673-707)

    /// Port of `description.py:parse_transaction_description`. Tries MT940
    /// format first, then account-balance, then SEPA, then POS — same
    /// dispatch order and short-circuit ("first non-nil wins") as Python.
    public static func parseTransactionDescription(_ description: String?) -> String? {
        guard let description, !description.isEmpty else { return nil }
        if let mt940 = parseMT940Description(description) { return mt940 }
        if let balance = parseAccountBalanceDescription(description) { return balance }
        if let sepa = parseSEPADescription(description) { return sepa }
        if let pos = parsePOSDescription(description) { return pos }
        return nil
    }

    // MARK: - parse_mt940_description (description.py:7-78)

    /// Port of `description.py:parse_mt940_description`.
    public static func parseMT940Description(_ description: String?) -> String? {
        mt940Fields(description)?.toJSONString()
    }

    /// Builds the `Fields` value (pre-JSON-encoding) so `MT940Parser.swift`
    /// and `parseTransactionDescription` share the parse without a redundant
    /// JSON round-trip.
    static func mt940Fields(_ description: String?) -> Fields? {
        guard let description, !description.isEmpty else { return nil }

        // Python: r"/([A-Z]+)/([^/]+?)(?=/(?:[A-Z]+)/|/$|$)" — matches
        // /FIELD/VALUE/, VALUE being everything up to (not including) the
        // next /FIELD/, a trailing "/" at end of string, or end of string.
        let pattern = "/([A-Z]+)/([^/]+?)(?=/(?:[A-Z]+)/|/$|$)"
        let allMatches = regexFindAll(pattern, description)
        if allMatches.isEmpty { return nil }

        let result = Fields()
        for match in allMatches {
            guard var field = group(match, 1, in: description) else { continue }
            guard var value = group(match, 2, in: description) else { continue }
            field = field.trimmingCharacters(in: .whitespacesAndNewlines)
            value = value.trimmingCharacters(in: .whitespacesAndNewlines)
            if value.isEmpty { continue }

            switch field {
            case "TRTP": result.setString("transaction_type", value)
            case "IBAN": result.setString("iban", value)
            case "BIC": result.setString("bic", value)
            case "NAME": result.setString("name", value)
            case "REMI": result.setString("remittance_info", value)
            case "EREF": result.setString("end_to_end_reference", value)
            case "MREF": result.setString("mandate_reference", value)
            case "PREF": result.setString("payment_reference", value)
            case "CRED": result.setString("creditor_reference", value)
            case "DEBT": result.setString("debtor_reference", value)
            case "COAM": result.setString("commission_amount", value)
            case "OAMT": result.setString("original_amount", value)
            default: result.setOtherField(field, value)
            }
        }

        guard !result.isEmpty else { return nil }
        result.setString("format", "mt940")
        parseTikkieFields(result)
        return result
    }

    // MARK: - parse_tikkie_fields (description.py:81-219)

    /// Port of `description.py:parse_tikkie_fields`. Mutates `result` in
    /// place exactly like the Python function mutates its `dict` argument.
    static func parseTikkieFields(_ result: Fields) {
        let name = (result.getString("name") ?? "").uppercased()
        let remi = result.getString("remittance_info") ?? ""
        let transactionType = result.getString("transaction_type") ?? ""

        var isTikkie = false
        if name.contains("TIKKIE") || remi.uppercased().contains("TIKKIE") {
            isTikkie = true
            result.setBool("is_tikkie", true)
            result.setString("payment_service", "Tikkie")
        }
        guard isTikkie else { return }

        if transactionType == "SEPA OVERBOEKING", remi.uppercased().contains("TIKKIE ID") {
            // REMI: "TIKKIE ID 001123453991, PICS, VAN G VAN AMSTERDAM, NL83ABNA0105946443"
            if let m = regexSearch("TIKKIE ID\\s+(\\d+)", remi, caseInsensitive: true),
               let id = group(m, 1, in: remi) {
                result.setString("tikkie_id", id)
            }

            let parts = remi
                .split(separator: ",", omittingEmptySubsequences: false)
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }

            var payerName: String?
            var payerIBAN: String?

            searchLoop: for (i, part) in parts.enumerated() {
                if let m = regexSearch("([A-Z]{2}\\d{2}[A-Z0-9]{4,30})", part), let iban = group(m, 1, in: part) {
                    payerIBAN = iban
                    if i > 0 {
                        var j = i - 1
                        while j >= 0 {
                            let prevPart = parts[j]
                            let looksLikeCode = regexSearch("^[A-Z]{2,4}$", prevPart) != nil
                            if !looksLikeCode, !prevPart.uppercased().contains("TIKKIE ID") {
                                payerName = prevPart
                                break
                            }
                            j -= 1
                        }
                    }
                    break searchLoop
                }
            }

            if let payerName { result.setString("payer_name", payerName) }
            if let payerIBAN { result.setString("payer_iban", payerIBAN) }
        } else if transactionType == "IDEAL", name.contains("VIA TIKKIE") {
            // REMI: "001112686692 0031855697994810 FOR THE COIN NL21A BNA0869690930"
            if let m = regexSearch("^(\\d{12})", remi), let id = group(m, 1, in: remi) {
                result.setString("tikkie_id", id)
            }
            if let m = regexSearch("^\\d{12}\\s+(\\d+)", remi), let ref = group(m, 1, in: remi) {
                result.setString("payment_reference", ref)
            }
            if let m = regexSearch("([A-Z]{2}\\d{2}[A-Z0-9\\s]{12,30})$", remi), let raw = group(m, 1, in: remi) {
                result.setString("payer_iban", raw.replacingOccurrences(of: " ", with: ""))
            }

            if let tikkieId = result.getString("tikkie_id"), let paymentRef = result.getString("payment_reference") {
                var descPart = remi
                descPart = reSubRemoveOnce("^" + NSRegularExpression.escapedPattern(for: tikkieId) + "\\s+", descPart)
                descPart = reSubRemoveOnce("^" + NSRegularExpression.escapedPattern(for: paymentRef) + "\\s+", descPart)

                if let payerIBAN = result.getString("payer_iban") {
                    let spaced = payerIBAN
                        .map { NSRegularExpression.escapedPattern(for: String($0)) }
                        .joined(separator: "\\s*")
                    descPart = reSubRemoveOnce("\\s*" + spaced + "\\s*$", descPart)
                }

                descPart = reSubRemoveOnce("\\s+\\d+\\s*$", descPart)
                descPart = descPart.trimmingCharacters(in: .whitespacesAndNewlines)
                if !descPart.isEmpty { result.setString("payment_description", descPart) }
            }

            let originalName = result.getString("name") ?? ""
            if let m = regexSearch("^(.+?)\\s+VIA\\s+TIKKIE", originalName, caseInsensitive: true),
               let payer = group(m, 1, in: originalName) {
                result.setString("payer_name", payer.trimmingCharacters(in: .whitespacesAndNewlines))
            }

            let eref = result.getString("end_to_end_reference") ?? ""
            if let m = regexSearch("(\\d{2}-\\d{2}-\\d{4}\\s+\\d{2}:\\d{2})", eref), let ts = group(m, 1, in: eref) {
                result.setString("tikkie_timestamp", ts)
            }

            if let kenmerk = result.getString("reference"),
               let m = regexSearch("(\\d{2}-\\d{2}-\\d{4}\\s+\\d{2}:\\d{2})", kenmerk),
               let ts = group(m, 1, in: kenmerk) {
                result.setString("tikkie_timestamp", ts)
            }
        }
    }

    // MARK: - parse_pos_description (description.py:222-377)

    /// Port of `description.py:parse_pos_description`.
    public static func parsePOSDescription(_ description: String?) -> String? {
        posFields(description)?.toJSONString()
    }

    static func posFields(_ description: String?) -> Fields? {
        guard let description, !description.isEmpty else { return nil }
        let upper = description.uppercased()

        let posIndicators = ["BEA", "ECOM", "BETAALPAS", "APPLE PAY", "PAS", "NR:", "/"]
        guard posIndicators.contains(where: { upper.contains($0) }) else { return nil }

        let result = Fields()

        if upper.contains("BEA") {
            result.setString("transaction_type", "POS")
            result.setString("payment_method", "Betaalautomaat")
        }
        if upper.contains("ECOM") {
            result.setString("transaction_type", "ECOM")
            result.setString("payment_method", "E-commerce")
        }
        if upper.contains("BETAALPAS") {
            result.setString("payment_method", "Betaalpas")
        }
        if upper.contains("APPLE PAY") {
            result.setString("payment_method", "Apple Pay")
        }

        // First try the format with merchant code: CODE*MERCHANT
        if let m = regexSearch("([A-Z0-9]+\\*[^,]+)", description), let merchantPart = group(m, 1, in: description) {
            if merchantPart.contains("*") {
                let parts = merchantPart
                    .split(separator: "*", maxSplits: 1, omittingEmptySubsequences: false)
                    .map(String.init)
                if parts.count == 2 {
                    result.setString("merchant_code", parts[0])
                    result.setString("merchant_name", parts[1].trimmingCharacters(in: .whitespacesAndNewlines))
                }
            }
        }

        // Apple Pay: merchant name comes directly after "APPLE PAY" without a code prefix.
        if upper.contains("APPLE PAY"), result.getString("merchant_name") == nil {
            if let m = regexSearch("APPLE PAY\\s+(.+?)(?=,PAS|,NR:|NR:)", description, caseInsensitive: true),
               var merchantName = group(m, 1, in: description) {
                merchantName = merchantName.trimmingCharacters(in: .whitespacesAndNewlines)
                merchantName = rstrip(merchantName, in: CharacterSet(charactersIn: " ,"))
                if !merchantName.isEmpty { result.setString("merchant_name", merchantName) }
            }
        }

        // BETAALPAS: merchant name may come directly after "BETAALPAS" without a code prefix.
        if upper.contains("BETAALPAS"), result.getString("merchant_name") == nil {
            if let m = regexSearch(
                "BETAALPAS\\s+(.+?)(?=,PAS|,NR:|NR:|\\d{1,2}\\.\\d{1,2}\\.\\d{2,4})",
                description,
                caseInsensitive: true
            ), var merchantName = group(m, 1, in: description) {
                merchantName = merchantName.trimmingCharacters(in: .whitespacesAndNewlines)
                merchantName = rstrip(merchantName, in: CharacterSet(charactersIn: " ,"))
                if !merchantName.isEmpty { result.setString("merchant_name", merchantName) }
            }
        }

        if let m = regexSearch("PAS\\s*(\\d+)", description, caseInsensitive: true), let v = group(m, 1, in: description) {
            result.setString("card_terminal_id", v)
        }
        if let m = regexSearch("NR:\\s*([A-Z0-9]+)", description, caseInsensitive: true), let v = group(m, 1, in: description) {
            result.setString("transaction_reference", v)
        }

        // Try HH:MM format first (standard), then HH.MM (alternative with dots).
        var datetimeMatch = regexSearch("(\\d{1,2})\\.(\\d{1,2})\\.(\\d{2,4})\\s*/\\s*(\\d{1,2}):(\\d{2})", description)
        if datetimeMatch == nil {
            datetimeMatch = regexSearch("(\\d{1,2})\\.(\\d{1,2})\\.(\\d{2,4})\\s*/\\s*(\\d{1,2})\\.(\\d{2})", description)
        }
        if let m = datetimeMatch,
           let dayS = group(m, 1, in: description),
           let monthS = group(m, 2, in: description),
           var yearS = group(m, 3, in: description),
           let hourS = group(m, 4, in: description),
           let minuteS = group(m, 5, in: description) {
            if yearS.count == 2 { yearS = "20" + yearS }
            result.setString("transaction_date", "\(yearS)-\(zfill(monthS, 2))-\(zfill(dayS, 2))")
            result.setString("transaction_time", "\(zfill(hourS, 2)):\(minuteS)")
        }

        let locationPattern =
            "(\\d{1,2}\\.\\d{1,2}\\.\\d{2,4}\\s*/\\s*\\d{1,2}[.:]\\d{2})\\s+([A-Z][A-Z\\s\\-]+?)(?=,\\s*LAND:|,\\s*[A-Z]{3}\\s+\\d|$)"
        if let m = regexSearch(locationPattern, description), var location = group(m, 2, in: description) {
            location = location.trimmingCharacters(in: .whitespacesAndNewlines)
            location = rstrip(location, in: CharacterSet(charactersIn: " ,-"))
            if location.count > 2, !isAllDigits(location),
               !location.contains("NR:"), !location.contains("PAS"), !location.contains("LAND:") {
                result.setString("location", location)
            }
        }

        if let m = regexSearch("LAND:\\s*([A-Z]{3})", description, caseInsensitive: true), let v = group(m, 1, in: description) {
            result.setString("country_code", v.uppercased())
        }

        if let m = regexSearch("([A-Z]{3})\\s+([\\d.,]+)", description),
           let currencyCode = group(m, 1, in: description),
           let amountRaw = group(m, 2, in: description) {
            let amountStr = amountRaw.replacingOccurrences(of: ".", with: "").replacingOccurrences(of: ",", with: ".")
            if let amount = Double(amountStr) {
                result.setString("foreign_currency", currencyCode)
                result.setNumber("foreign_amount", amount)
            }
        }

        if let m = regexSearch("1EUR=([\\d.,]+)", description, caseInsensitive: true), let rateRaw = group(m, 1, in: description) {
            let rateStr = rateRaw.replacingOccurrences(of: ",", with: ".")
            if let rate = Double(rateStr) {
                result.setNumber("exchange_rate", rate)
            }
        }

        guard !result.isEmpty else { return nil }
        result.setString("format", "pos")
        return result
    }

    // MARK: - parse_sepa_description (description.py:380-582)

    /// Port of `description.py:parse_sepa_description`.
    public static func parseSEPADescription(_ description: String?) -> String? {
        sepaFields(description)?.toJSONString()
    }

    static func sepaFields(_ description: String?) -> Fields? {
        guard let description, !description.isEmpty else { return nil }
        guard description.uppercased().hasPrefix("SEPA") else { return nil }

        let result = Fields()

        // Python: `re.match(r"SEPA\s+(\w+)", ...)` — anchored at start; the
        // leading "^" below reproduces `re.match`'s "only try position 0"
        // semantics (every other pattern in this file uses `re.search`,
        // which needs no such anchor).
        if let m = regexSearch("^SEPA\\s+(\\w+)", description, caseInsensitive: true), let typeRaw = group(m, 1, in: description) {
            let sepaType = typeRaw.uppercased()
            result.setString("sepa_type", sepaType)
            switch sepaType {
            case "OVERBOEKING":
                result.setString("transaction_type", "SEPA Transfer")
            case "IDEAL":
                result.setString("transaction_type", "SEPA iDEAL")
            case "INCASSO":
                result.setString("transaction_type", "SEPA Direct Debit")
                let upper = description.uppercased()
                if upper.contains("ALGEMEEN") { result.setString("direct_debit_type", "General") }
                if upper.contains("DOORLOPEND") { result.setBool("recurring", true) }
            default:
                break
            }
        }

        if let m = regexSearch("IBAN:\\s*([A-Z]{2}\\d{2}[A-Z0-9]{4,30})", description, caseInsensitive: true),
           let v = group(m, 1, in: description) {
            result.setString("iban", v.uppercased())
        }
        if let m = regexSearch("BIC:\\s*([A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?)", description, caseInsensitive: true),
           let v = group(m, 1, in: description) {
            result.setString("bic", v.uppercased())
        }
        if let m = regexSearch(
            "NAAM:\\s*([^:]+?)(?=\\s+(?:IBAN|BIC|OMSCHRIJVING|INCASSANT|MACHTIGING|KENMERK|BETALINGSKENM\\.?):|$)",
            description,
            caseInsensitive: true
        ), let v = group(m, 1, in: description) {
            result.setString("name", v.trimmingCharacters(in: .whitespacesAndNewlines))
        }
        if let m = regexSearch(
            "OMSCHRIJVING:\\s*(.+?)(?=\\s+(?:IBAN|BIC|NAAM|INCASSANT|MACHTIGING|KENMERK|BETALINGSKENM\\.?):|$)",
            description,
            caseInsensitive: true
        ), let v = group(m, 1, in: description) {
            result.setString("description", v.trimmingCharacters(in: .whitespacesAndNewlines))
        }
        if let m = regexSearch(
            "BETALINGSKENM\\.?:\\s*(.+?)(?=\\s+(?:IBAN|BIC|NAAM|OMSCHRIJVING|INCASSANT|MACHTIGING|KENMERK):|$)",
            description,
            caseInsensitive: true
        ), let v = group(m, 1, in: description) {
            result.setString("payment_reference", v.trimmingCharacters(in: .whitespacesAndNewlines))
        }
        if let m = regexSearch("INCASSANT:\\s*([A-Z0-9]+)", description, caseInsensitive: true), let v = group(m, 1, in: description) {
            result.setString("creditor_identifier", v.uppercased())
        }
        if let m = regexSearch("MACHTIGING:\\s*([A-Z0-9\\-]+)", description, caseInsensitive: true), let v = group(m, 1, in: description) {
            result.setString("mandate_reference", v)
        }
        if let m = regexSearch(
            "KENMERK:\\s*(.+?)(?=\\s+(?:IBAN|BIC|NAAM|OMSCHRIJVING|INCASSANT|MACHTIGING|BETALINGSKENM\\.?):|$)",
            description,
            caseInsensitive: true
        ), let v = group(m, 1, in: description) {
            result.setString("reference", v.trimmingCharacters(in: .whitespacesAndNewlines))
        }

        // Tikkie detection for SEPA IDEAL ("VIA TIKKIE"/"TIKKIE" in NAAM).
        if result.getString("sepa_type") == "IDEAL", let name = result.getString("name") {
            let nameUpper = name.uppercased()
            if nameUpper.contains("VIA TIKKIE") || nameUpper.contains("TIKKIE") {
                result.setBool("is_tikkie", true)
                result.setString("payment_service", "Tikkie")

                if let m = regexSearch("^(.+?)\\s+VIA\\s+TIKKIE", name, caseInsensitive: true), let payer = group(m, 1, in: name) {
                    result.setString("payer_name", payer.trimmingCharacters(in: .whitespacesAndNewlines))
                }

                // "001059714643 00315 14239726178 YEAH NL58INGB0631694 404"
                if let omschrijving = result.getString("description") {
                    if let m = regexSearch("^(\\d{12})", omschrijving), let id = group(m, 1, in: omschrijving) {
                        result.setString("tikkie_id", id)
                    }
                    if let m = regexSearch("^\\d{12}\\s+(\\d+)", omschrijving), let ref = group(m, 1, in: omschrijving) {
                        result.setString("payment_reference", ref)
                    }
                    if let m = regexSearch("(NL\\d{2}[A-Z]{4}\\d{6,10})(?:\\s+\\d+)?", omschrijving),
                       let raw = group(m, 1, in: omschrijving) {
                        let payerIban = raw.replacingOccurrences(of: " ", with: "")
                        if payerIban.hasPrefix("NL"), payerIban.count >= 14 {
                            result.setString("payer_iban", payerIban)
                        }
                    }

                    if let tikkieId = result.getString("tikkie_id"), let paymentRef = result.getString("payment_reference") {
                        var descPart = omschrijving
                        descPart = reSubRemoveOnce("^" + NSRegularExpression.escapedPattern(for: tikkieId) + "\\s+", descPart)
                        descPart = reSubRemoveOnce("^" + NSRegularExpression.escapedPattern(for: paymentRef) + "\\s+", descPart)

                        if let payerIban = result.getString("payer_iban") {
                            let spaced = payerIban
                                .map { NSRegularExpression.escapedPattern(for: String($0)) }
                                .joined(separator: "\\s*")
                            // SEPA variant allows a trailing bare number after the IBAN, unlike the MT940 variant.
                            descPart = reSubRemoveOnce("\\s*" + spaced + "\\s*\\d*\\s*$", descPart)
                        }

                        descPart = reSubRemoveOnce("\\s+\\d+\\s*$", descPart)
                        descPart = descPart.trimmingCharacters(in: .whitespacesAndNewlines)
                        if !descPart.isEmpty { result.setString("payment_description", descPart) }
                    }
                }

                if let kenmerk = result.getString("reference"),
                   let m = regexSearch("(\\d{2}-\\d{2}-\\d{4}\\s+\\d{2}:\\d{2})", kenmerk),
                   let ts = group(m, 1, in: kenmerk) {
                    result.setString("tikkie_timestamp", ts)
                }
            }
        }

        guard !result.isEmpty else { return nil }
        result.setString("format", "sepa")
        return result
    }

    // MARK: - parse_account_balance_description (description.py:585-670)

    /// Port of `description.py:parse_account_balance_description`.
    public static func parseAccountBalanceDescription(_ description: String?) -> String? {
        accountBalanceFields(description)?.toJSONString()
    }

    static func accountBalanceFields(_ description: String?) -> Fields? {
        guard let description, !description.isEmpty else { return nil }
        let upper = description.uppercased()
        guard upper.contains("ACCOUNT BALANCED") || upper.contains("CREDIT INTEREST") else { return nil }

        let result = Fields()
        result.setString("format", "account_balance")
        result.setString("transaction_type", "Account Balance")

        if let m = regexSearch("(CREDIT INTEREST|DEBIT INTEREST|INTEREST)", description, caseInsensitive: true),
           let matched = group(m, 1, in: description) {
            result.setString("interest_type", matched.uppercased())
            result.setString("transaction_type", pythonTitleCase(matched))
        }

        if let m = regexSearch("(\\d+[,.]\\d+)\\s*([CD])", description, caseInsensitive: true),
           let amountRaw = group(m, 1, in: description), let indicatorRaw = group(m, 2, in: description) {
            let amountStr = amountRaw.replacingOccurrences(of: ",", with: ".")
            if let amount = Double(amountStr) {
                let indicator = indicatorRaw.uppercased()
                result.setNumber("amount", amount)
                result.setString("amount_indicator", indicator)
                result.setBool("is_credit", indicator == "C")
            }
        }

        if let m = regexSearch(
            "FROM\\s+(\\d{2}\\.\\d{2}\\.\\d{4})\\s+TO\\s+(\\d{2}\\.\\d{2}\\.\\d{4})",
            description,
            caseInsensitive: true
        ), let fromStr = group(m, 1, in: description), let toStr = group(m, 2, in: description) {
            let fromParts = fromStr.split(separator: ".").map(String.init)
            let toParts = toStr.split(separator: ".").map(String.init)
            if fromParts.count == 3, toParts.count == 3 {
                result.setString("period_from", "\(fromParts[2])-\(fromParts[1])-\(fromParts[0])")
                result.setString("period_to", "\(toParts[2])-\(toParts[1])-\(toParts[0])")
            }
        }

        if let m = regexSearch("(?:TO\\s+\\d{2}\\.\\d{2}\\.\\d{4}|[CD]\\s+)(.+)$", description, caseInsensitive: true),
           let info = group(m, 1, in: description) {
            let trimmed = info.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty { result.setString("additional_info", trimmed) }
        }

        if let m = regexSearch("(https?://[^\\s]+|www\\.[^\\s]+)", description, caseInsensitive: true),
           let url = group(m, 1, in: description) {
            result.setString("url", url)
        }

        // "More than just format and transaction_type" — Python: `len(result) > 2`.
        guard result.count > 2 else { return nil }
        return result
    }
}

// MARK: - Ordered JSON-object builder

/// A minimal ordered string-keyed map preserving Python `dict`
/// insertion-order semantics (`result[key] = value` either appends a new key
/// or overwrites the existing slot without moving it) for the structured
/// description builders above. Values are restricted to the JSON shapes
/// `description.py` actually produces: `String`, `Bool`, `Double`, or a
/// nested string->string map (`other_fields` only — every value stored there
/// is itself always a raw regex-captured string, per `description.py:66-68`).
final class Fields {
    enum Value {
        case string(String)
        case bool(Bool)
        case number(Double)
        case null
        case stringMap([(String, String)])
    }

    private(set) var keys: [String] = []
    private var storage: [String: Value] = [:]

    var isEmpty: Bool { keys.isEmpty }
    var count: Int { keys.count }

    private subscript(key: String) -> Value? {
        get { storage[key] }
        set {
            guard let newValue else {
                storage.removeValue(forKey: key)
                keys.removeAll { $0 == key }
                return
            }
            if storage[key] == nil { keys.append(key) }
            storage[key] = newValue
        }
    }

    func setString(_ key: String, _ value: String) { self[key] = .string(value) }
    func setBool(_ key: String, _ value: Bool) { self[key] = .bool(value) }
    func setNumber(_ key: String, _ value: Double) { self[key] = .number(value) }
    func setNull(_ key: String) { self[key] = .null }

    /// Python's `value or None` pattern (used throughout `wise.py`'s
    /// `structured` dict literal): an empty string becomes JSON `null`,
    /// anything else is stored verbatim.
    func setStringOrNull(_ key: String, _ value: String) {
        if value.isEmpty {
            self[key] = .null
        } else {
            self[key] = .string(value)
        }
    }

    /// `value if value is not None else None` for an already-optional
    /// `Double` (`seb.py`'s `native_balance`/`stored_balance` fields, which
    /// can be genuinely absent when the CSV's `Balance` cell doesn't parse).
    func setNumberOrNull(_ key: String, _ value: Double?) {
        if let value {
            self[key] = .number(value)
        } else {
            self[key] = .null
        }
    }

    func getString(_ key: String) -> String? {
        if case .string(let s)? = storage[key] { return s }
        return nil
    }

    /// Port of Python's `result.setdefault("other_fields", {})[field] = value`
    /// pattern (`description.py:66-68`): creates the nested map (and the
    /// top-level `"other_fields"` key) on first use, updates in place on
    /// repeat keys.
    func setOtherField(_ field: String, _ value: String) {
        var existing: [(String, String)] = []
        if case .stringMap(let m)? = storage["other_fields"] { existing = m }
        if let idx = existing.firstIndex(where: { $0.0 == field }) {
            existing[idx] = (field, value)
        } else {
            existing.append((field, value))
        }
        self["other_fields"] = .stringMap(existing)
    }

    func toJSONString() -> String {
        var parts: [String] = []
        parts.reserveCapacity(keys.count)
        for key in keys {
            guard let value = storage[key] else { continue }
            parts.append("\(jsonEncodeString(key)):\(jsonEncode(value))")
        }
        return "{" + parts.joined(separator: ",") + "}"
    }
}

private func jsonEncode(_ value: Fields.Value) -> String {
    switch value {
    case .string(let s): return jsonEncodeString(s)
    case .bool(let b): return b ? "true" : "false"
    case .number(let d):
        // Matches Python `json.dumps(float)` — shortest round-trip decimal
        // rendering (e.g. `2.0`, not `2`). Swift's default `Double`
        // string-interpolation uses the same "shortest round-trip"
        // algorithm — see `TransactionID.swift`'s `pythonFloatString`.
        return "\(d)"
    case .stringMap(let m):
        let parts = m.map { "\(jsonEncodeString($0.0)):\(jsonEncodeString($0.1))" }
        return "{" + parts.joined(separator: ",") + "}"
    case .null:
        return "null"
    }
}

private func jsonEncodeString(_ s: String) -> String {
    var result = "\""
    for scalar in s.unicodeScalars {
        switch scalar {
        case "\"": result += "\\\""
        case "\\": result += "\\\\"
        case "\n": result += "\\n"
        case "\r": result += "\\r"
        case "\t": result += "\\t"
        default:
            if scalar.value < 0x20 {
                result += String(format: "\\u%04x", scalar.value)
            } else {
                // Matches `json.dumps(..., ensure_ascii=False)`: non-ASCII
                // characters are emitted as raw UTF-8, not `\uXXXX`-escaped.
                result.unicodeScalars.append(scalar)
            }
        }
    }
    result += "\""
    return result
}

// MARK: - Regex helpers

/// `re.search(pattern, text, re.IGNORECASE if caseInsensitive else 0)`.
func regexSearch(_ pattern: String, _ text: String, caseInsensitive: Bool = false) -> NSTextCheckingResult? {
    var options: NSRegularExpression.Options = []
    if caseInsensitive { options.insert(.caseInsensitive) }
    guard let regex = try? NSRegularExpression(pattern: pattern, options: options) else { return nil }
    let range = NSRange(text.startIndex..<text.endIndex, in: text)
    return regex.firstMatch(in: text, options: [], range: range)
}

/// `re.findall(pattern, text)` for a two-capture-group pattern (the only
/// shape `description.py` uses `findall` with) — returns every match, not
/// just the first.
private func regexFindAll(_ pattern: String, _ text: String, caseInsensitive: Bool = false) -> [NSTextCheckingResult] {
    var options: NSRegularExpression.Options = []
    if caseInsensitive { options.insert(.caseInsensitive) }
    guard let regex = try? NSRegularExpression(pattern: pattern, options: options) else { return [] }
    let range = NSRange(text.startIndex..<text.endIndex, in: text)
    return regex.matches(in: text, options: [], range: range)
}

/// `match.group(index)` — `nil` if the group didn't participate in the match
/// (mirrors Python returning `None` for an unmatched optional group).
func group(_ match: NSTextCheckingResult, _ index: Int, in text: String) -> String? {
    guard index < match.numberOfRanges else { return nil }
    let nsRange = match.range(at: index)
    guard nsRange.location != NSNotFound, let range = Range(nsRange, in: text) else { return nil }
    return String(text[range])
}

/// Mirrors `re.sub(pattern, "", text)` for the patterns `description.py`
/// actually uses it with — every call site anchors with `^` or `$`, so the
/// pattern matches **at most once**; this removes that single match (or
/// returns `text` unchanged if the pattern doesn't match at all).
private func reSubRemoveOnce(_ pattern: String, _ text: String, caseInsensitive: Bool = false) -> String {
    guard let m = regexSearch(pattern, text, caseInsensitive: caseInsensitive), let range = Range(m.range, in: text) else {
        return text
    }
    var result = text
    result.removeSubrange(range)
    return result
}

/// `text.rstrip(chars)` — strips trailing characters (by Unicode scalar) that
/// belong to `set`.
private func rstrip(_ text: String, in set: CharacterSet) -> String {
    var result = Substring(text)
    while let last = result.unicodeScalars.last, set.contains(last) {
        result = result.dropLast()
    }
    return String(result)
}

/// `str.zfill(width)` — left-pads with `"0"` to at least `width` characters;
/// never truncates a longer string.
private func zfill(_ s: String, _ width: Int) -> String {
    s.count >= width ? s : String(repeating: "0", count: width - s.count) + s
}

/// `str.isdigit()` for the plain-ASCII-digit inputs this file's callers can
/// produce.
private func isAllDigits(_ s: String) -> Bool {
    !s.isEmpty && s.allSatisfy { $0.isASCII && $0.isNumber }
}

/// `str.title()` — uppercases the first cased character of every maximal run
/// of letters, lowercases the rest; a non-letter resets the "start of word"
/// state. Exact for the plain-ASCII interest-type strings this file's
/// `parse_account_balance_description` feeds it
/// (`"CREDIT INTEREST"` -> `"Credit Interest"`, etc.).
private func pythonTitleCase(_ s: String) -> String {
    var result = ""
    var previousWasCased = false
    for char in s {
        if char.isLetter {
            result += previousWasCased ? char.lowercased() : char.uppercased()
            previousWasCased = true
        } else {
            result.append(char)
            previousWasCased = false
        }
    }
    return result
}
