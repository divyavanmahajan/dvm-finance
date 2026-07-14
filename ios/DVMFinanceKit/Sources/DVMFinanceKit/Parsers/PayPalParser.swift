import Foundation

/// Port of `src/abn_combined/parsers/paypal.py` — the PayPal "Activity report
/// for balance affecting transactions" (TAB-delimited, `csv.DictReader` with
/// `QUOTE_MINIMAL`, read as `utf-8-sig`).
public enum PayPalParser {

    public static func parse(fileURL: URL) throws -> [ParsedTransaction] {
        let content = try ParserUtils.readFileStrippingBOM(fileURL)
        return parse(content: content, fileName: fileURL.lastPathComponent)
    }

    /// The pure-function core, separated from file I/O for testability.
    static func parse(content: String, fileName: String) -> [ParsedTransaction] {
        let rawRows = CSVTokenizer.parse(content, delimiter: "\t")
        guard let rawHeaderRow = rawRows.first else { return [] }

        // paypal.py:99-108: `k.strip().strip('"')` for header keys, skipping
        // any that clean to empty (`if k`); `v.strip().strip('"') if v else
        // ""` for values.
        let headers = rawHeaderRow.map(cleanQuoted)

        var rows: [[String: String]] = []
        for fields in rawRows.dropFirst() {
            var cleaned: [String: String] = [:]
            for (i, header) in headers.enumerated() where !header.isEmpty {
                let raw = i < fields.count ? fields[i] : ""
                cleaned[header] = raw.isEmpty ? "" : cleanQuoted(raw)
            }
            rows.append(cleaned)
        }
        if rows.isEmpty { return [] }

        // paypal.py:113-124: group child rows by `Reference Txn ID`.
        // `parent_txn_ids` (paypal.py:124) is built in Python but never read
        // again anywhere in the module — dead value, not ported.
        var refToRows: [String: [[String: String]]] = [:]
        var refOrder: [String] = []
        for row in rows {
            let refId = (row["Reference Txn ID"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            guard !refId.isEmpty else { continue }
            if refToRows[refId] == nil {
                refToRows[refId] = []
                refOrder.append(refId)
            }
            refToRows[refId]!.append(row)
        }

        // paypal.py:126-137: EUR funding row for each non-EUR parent —
        // first Bank-Deposit/User-Initiated-Withdrawal EUR child (in
        // first-seen row order) whose `Net` parses.
        var eurFundingForParent: [String: Double] = [:]
        for refId in refOrder {
            guard let children = refToRows[refId] else { continue }
            for child in children {
                let name = (child["Name"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                let ttype = (child["Type"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                let curr = (child["Currency"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
                guard name.isEmpty, curr == "EUR" else { continue }
                guard ttype.contains("Bank Deposit to PP Account") || ttype.contains("User Initiated Withdrawal") else {
                    continue
                }
                let netField = child["Net"] ?? ""
                let netInput = netField.isEmpty ? "0" : netField
                if let net = parseEuropeanNumber(netInput) {
                    eurFundingForParent[refId] = net
                    break
                }
            }
        }

        // paypal.py:141-142. `ttype` is always already fully trimmed by the
        // row-cleaning step above, so the trailing space in Python's literal
        // `"Bank Deposit to PP Account "` (only meaningful against an
        // *un*trimmed value) never matters in practice; compared here in its
        // already-trimmed form.
        let bankDepositType = "Bank Deposit to PP Account"
        let userWithdrawalType = "User Initiated Withdrawal"

        var transactions: [ParsedTransaction] = []

        for (offset, row) in rows.enumerated() {
            let lineNum = offset + 2 // paypal.py:144 — line 1 is the header.

            let name = (row["Name"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let ttype = (row["Type"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let txnId = (row["Transaction ID"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let refId = (row["Reference Txn ID"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let currency = (row["Currency"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
            let netField = row["Net"] ?? ""
            let net = parseEuropeanNumber(netField.isEmpty ? "0" : netField) ?? 0.0

            let account = accountFromRow(row)
            guard let transDate = parsePayPalDate(row["Date"] ?? "") else { continue }

            let raw = rowToSnakeCase(row)
            raw.setString("paypal_transaction_id", txnId)
            raw.setString("paypal_type", ttype)
            raw.setString("paypal_balance_impact", (row["Balance Impact"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines))

            // Rule 1: rows with a Name.
            if !name.isEmpty {
                let itemTitle = (row["Item Title"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                let description = itemTitle.isEmpty ? "\(name):\(txnId)" : "\(name):\(txnId):\(itemTitle)"

                var amount = net
                var currStored = currency

                if currency != "EUR", let eurNet = eurFundingForParent[txnId] {
                    amount = net < 0 ? -abs(eurNet) : abs(eurNet)
                    currStored = "EUR"
                    raw.setString("original_currency", currency)
                    raw.setNumber("original_amount", net)
                    raw.setNumber("eur_amount", amount)
                    raw.setString("eur_currency", "EUR")
                }

                var transaction = ParsedTransaction(
                    accountNumber: account,
                    transactiondate: transDate,
                    amount: amount,
                    description: description,
                    currency: currStored,
                    sourceFile: fileName,
                    sourceLine: lineNum,
                    category: nil,
                    paypalTransactionId: txnId
                )
                transaction.descriptionStructured = raw.toJSONString()
                transactions.append(transaction)
                continue
            }

            // Rule 2: Bank Deposit / User Initiated Withdrawal rows (no Name).
            if ttype == bankDepositType || ttype == userWithdrawalType {
                var isEURFundingForForeign = false
                if !refId.isEmpty, currency == "EUR" {
                    for parent in rows {
                        let parentTxnId = (parent["Transaction ID"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                        if parentTxnId == refId {
                            let parentCurr = (parent["Currency"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
                            if parentCurr != "EUR" { isEURFundingForForeign = true }
                            break
                        }
                    }
                }
                if isEURFundingForForeign { continue }

                let description = refId.isEmpty ? ttype : "\(ttype):\(refId)"

                var transaction = ParsedTransaction(
                    accountNumber: account,
                    transactiondate: transDate,
                    amount: net,
                    description: description,
                    currency: "EUR",
                    sourceFile: fileName,
                    sourceLine: lineNum,
                    category: "transfer-paypal",
                    paypalTransactionId: txnId
                )
                transaction.descriptionStructured = raw.toJSONString()
                transactions.append(transaction)
            }

            // Rule 3 (paypal.py:236): other rows without a Name — skipped.
        }

        return transactions
    }

    // MARK: - paypal.py:17-32 `_parse_european_number`

    /// Comma=decimal, period=thousands: `-89,71` -> `-89.71`, `1.458,32` ->
    /// `1458.32`. Amounts flow through Python's `Decimal(s)`, then `float(...)`
    /// at the dict-building point — parsing the same normalized decimal
    /// string directly as a `Double` here reproduces that conversion exactly
    /// for realistic monetary magnitudes (see `ios/docs/spec.md` "Parsers").
    static func parseEuropeanNumber(_ value: String) -> Double? {
        let s = value
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: "\""))
        guard !s.isEmpty else { return nil }
        let normalized = s.replacingOccurrences(of: ".", with: "").replacingOccurrences(of: ",", with: ".")
        return Double(normalized)
    }

    // MARK: - paypal.py:35-49 `_parse_date`

    /// `DD/MM/YYYY`.
    static func parsePayPalDate(_ value: String) -> Date? {
        let s = value
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: "\""))
        guard !s.isEmpty else { return nil }
        let parts = s.components(separatedBy: "/")
        guard parts.count == 3, let day = Int(parts[0]), let month = Int(parts[1]), let year = Int(parts[2]) else {
            return nil
        }
        return ParserUtils.makeUTCDate(year: year, month: month, day: day)
    }

    // MARK: - paypal.py:52-70 `_email_to_account` / `_get_account_from_row`

    private static func emailToAccount(_ email: String) -> String {
        let e = email
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: "\""))
        guard !e.isEmpty, e.contains("@") else { return "pp:unknown" }
        let local = e
            .split(separator: "@", maxSplits: 1, omittingEmptySubsequences: false)[0]
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return local.isEmpty ? "pp:unknown" : "pp:\(local)"
    }

    /// `From Email Address` when `Balance Impact == "Debit"`, else `To Email Address`.
    private static func accountFromRow(_ row: [String: String]) -> String {
        let balanceImpact = (row["Balance Impact"] ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: "\""))
        let email = balanceImpact == "Debit" ? (row["From Email Address"] ?? "") : (row["To Email Address"] ?? "")
        return emailToAccount(email)
    }

    // MARK: - paypal.py:73-83 `_row_to_snake_case`

    /// Every original header, snake-cased (`" "`/`"/"`/`"-"` -> `"_"`,
    /// lowercased, non-alnum/underscore characters dropped), mapped to its
    /// already-cleaned string value — the base of `description_structured`
    /// before the `paypal_*`/`original_*`/`eur_*` keys are layered on.
    private static func rowToSnakeCase(_ row: [String: String]) -> Fields {
        let result = Fields()
        for (key, value) in row {
            var snake = key
                .replacingOccurrences(of: " ", with: "_")
                .replacingOccurrences(of: "/", with: "_")
                .replacingOccurrences(of: "-", with: "_")
                .lowercased()
            snake = String(snake.unicodeScalars.filter { CharacterSet.alphanumerics.contains($0) || $0 == "_" })
            result.setString(snake, value)
        }
        return result
    }

    /// `k.strip().strip('"')` / `v.strip().strip('"')`.
    private static func cleanQuoted(_ s: String) -> String {
        s.trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: "\""))
    }
}
