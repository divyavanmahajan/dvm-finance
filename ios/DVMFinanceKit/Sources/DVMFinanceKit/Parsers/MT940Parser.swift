import Foundation

/// Port of `src/abn_combined/parsers/mt940.py:_parse_mt940_basic` **only**
/// (per `ios/docs/plan.md` "Phase D" / the task brief: the optional
/// `abnamroparser`-library code path in `parse_mt940_file` was never used to
/// generate the golden fixture and is explicitly out of scope). `_parse_mt940_basic`
/// is a hand-rolled line scanner over `:25:`/`:60F:`/`:61:`/`:86:`/`:62F:`/`-`
/// tags — every quirk below (including ones that look like bugs) is ported
/// deliberately; see the inline notes citing `mt940.py` line ranges.
public enum MT940Parser {

    /// Reads `fileURL` as UTF-8 (matching Python's `open(file_path,
    /// encoding="utf-8")`) and parses it. Throws on decode failure exactly
    /// as Python's `open(...)` would raise `UnicodeDecodeError`.
    public static func parse(fileURL: URL) throws -> [ParsedTransaction] {
        let content = try String(contentsOf: fileURL, encoding: .utf8)
        return parse(content: content)
    }

    /// The pure-function core (`mt940.py:43-280`), separated from file I/O
    /// for testability.
    static func parse(content: String) -> [ParsedTransaction] {
        var transactions: [ParsedTransaction] = []
        var current: MT940Transaction?
        var accountNumber = ""
        var startBalance: Double?
        var endBalance: Double?

        let lines = readLines(content)

        /// Appends `current` to `transactions` after stamping the
        /// finalize-time fields (`startsaldo`/`endsaldo`/`valuedate`/
        /// `mutationcode`) — mirrors the four (nearly) identical inline
        /// blocks in `mt940.py` (`:61:`, `:62F:`, `"-"`, and the trailing
        /// leftover after the loop).
        func finalize(_ txn: inout MT940Transaction) {
            txn.startsaldo = startBalance
            txn.endsaldo = endBalance
            txn.valuedate = txn.transactiondate
            txn.mutationcode = ""
        }

        var i = 0
        while i < lines.count {
            let rawLine = lines[i]
            let line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)

            if line.hasPrefix(":25:") {
                // mt940.py:59-60
                accountNumber = String(line.dropFirst(4)).trimmingCharacters(in: .whitespacesAndNewlines)

            } else if line.hasPrefix(":60F:") {
                // mt940.py:63-78 (the date-part extraction there is computed
                // but never used — dead code, not ported).
                let balanceStr = String(line.dropFirst(5)).trimmingCharacters(in: .whitespacesAndNewlines)
                if !balanceStr.isEmpty, let parsed = parseEURBalance(balanceStr) {
                    startBalance = parsed
                }

            } else if line.hasPrefix(":61:") {
                // mt940.py:80-191.
                //
                // Save the previous transaction if it has a non-empty
                // description. NOTE: unlike the `:62F:`/`"-"` branches below,
                // Python does **not** explicitly reset `current_transaction`
                // to `{}` here after appending — it relies on the
                // `current_transaction = {...}` literal a few lines below to
                // overwrite it, which only runs `if trans_line:`. If
                // `trans_line` is empty (never happens for a well-formed
                // statement), the just-appended dict would survive and could
                // be appended a second time at the next boundary. Ported
                // as-is: `current` is left untouched unless `transLine` is
                // non-empty.
                if var txn = current, txn.hasNonEmptyDescription {
                    finalize(&txn)
                    transactions.append(txn.toParsedTransaction())
                }

                let transLine = String(line.dropFirst(4)).trimmingCharacters(in: .whitespacesAndNewlines)
                if !transLine.isEmpty {
                    current = parseTransactionLine(transLine, accountNumber: accountNumber, sourceLine: i + 1)
                }

            } else if line.hasPrefix(":86:") {
                // mt940.py:193-218. Continuation lines (not starting with
                // ":") are appended, space-joined, until the next tag.
                var description = String(line.dropFirst(4)).trimmingCharacters(in: .whitespacesAndNewlines)
                i += 1
                while i < lines.count, !lines[i].trimmingCharacters(in: .whitespacesAndNewlines).hasPrefix(":") {
                    description += " " + lines[i].trimmingCharacters(in: .whitespacesAndNewlines)
                    i += 1
                }
                i -= 1 // compensate for the loop's `i += 1` at the bottom

                if current != nil {
                    current!.description = description
                    current!.descriptionStructured = DescriptionParser.parseTransactionDescription(description)
                }

            } else if line.hasPrefix(":62F:") {
                // mt940.py:220-244.
                let balanceStr = String(line.dropFirst(5)).trimmingCharacters(in: .whitespacesAndNewlines)
                if !balanceStr.isEmpty, let parsed = parseEURBalance(balanceStr) {
                    endBalance = parsed
                }
                if var txn = current, txn.hasNonEmptyDescription {
                    finalize(&txn)
                    transactions.append(txn.toParsedTransaction())
                    current = nil
                }

            } else if line == "-" {
                // mt940.py:246-263 (end-of-statement marker).
                if var txn = current, txn.hasNonEmptyDescription {
                    finalize(&txn)
                    transactions.append(txn.toParsedTransaction())
                    current = nil
                }
            }

            i += 1
        }

        // mt940.py:267-278: trailing transaction, kept even without a
        // description (empty description substituted) as long as it has a
        // `transactiondate` — which, per the state machine above, `current`
        // always has whenever it is non-nil.
        if current != nil {
            if current!.description == nil {
                current!.description = ""
            }
            finalize(&current!)
            transactions.append(current!.toParsedTransaction())
        }

        return transactions
    }

    // MARK: - `:61:` transaction-line parsing (mt940.py:98-191)

    /// Parses one `:61:` line's body (already stripped of the `:61:`
    /// prefix), e.g. `"2405190519D5,N426NONREF"`. Returns `nil` exactly
    /// where Python's `except Exception:` would fire (invalid date
    /// components, or an amount segment that fails `float(...)`), matching
    /// `current_transaction = {}` on the exception path. A `nil` amount
    /// (when no `D`/`C` marker is found at all) is **not** a failure — that
    /// mirrors Python leaving `amount = None` and still constructing the
    /// dict successfully.
    private static func parseTransactionLine(_ transLine: String, accountNumber: String, sourceLine: Int) -> MT940Transaction? {
        let chars = Array(transLine)
        guard chars.count >= 6 else { return nil }

        let dateStr = String(chars[0..<6])
        guard let yearSuffix = Int(dateStr.prefix(2)),
              let month = Int(dateStr.dropFirst(2).prefix(2)),
              let day = Int(dateStr.dropFirst(4).prefix(2)),
              let transactionDate = ParserUtils.makeUTCDate(year: 2000 + yearSuffix, month: month, day: day)
        else {
            return nil
        }

        var amount: Double?
        var transactionTypeCode: String?
        var reference: String?

        var j = 6
        scan: while j < chars.count {
            let c = chars[j]
            if c == "D" || c == "C" {
                let remainingChars = Array(chars[(j + 1)...])
                let remaining = String(remainingChars)
                let nIndex = remainingChars.firstIndex(of: "N")

                if let nIndex, nIndex > 0 {
                    let amountPart = String(remainingChars[0..<nIndex])
                    guard let parsedAmount = Double(amountPart.replacingOccurrences(of: ",", with: ".")) else {
                        return nil
                    }
                    amount = (c == "D") ? -parsedAmount : parsedAmount

                    let typeCodeStart = j + 1 + nIndex
                    let typeCodeRemainingChars = (typeCodeStart + 1) < chars.count
                        ? Array(chars[(typeCodeStart + 1)...])
                        : []
                    let typeCodeRemaining = String(typeCodeRemainingChars)

                    if let m = regexSearch("^(\\d+)", typeCodeRemaining), let digits = group(m, 1, in: typeCodeRemaining) {
                        transactionTypeCode = "N" + digits
                        let referenceStart = typeCodeStart + 1 + digits.count
                        if referenceStart < chars.count {
                            reference = String(chars[referenceStart...]).trimmingCharacters(in: .whitespacesAndNewlines)
                        }
                    } else if !typeCodeRemaining.isEmpty {
                        reference = typeCodeRemaining.trimmingCharacters(in: .whitespacesAndNewlines)
                    }
                } else {
                    // No "N" found (or it's at position 0 of `remaining`,
                    // which Python's strict `n_index > 0` check also treats
                    // as "not found" — mt940.py:123 vs 157): amount runs to
                    // the end of the line.
                    guard let parsedAmount = Double(remaining.replacingOccurrences(of: ",", with: ".")) else {
                        return nil
                    }
                    amount = (c == "D") ? -parsedAmount : parsedAmount
                }
                break scan
            }
            j += 1
        }

        var txn = MT940Transaction()
        txn.transactiondate = transactionDate
        txn.amount = amount
        txn.accountNumber = accountNumber
        txn.currency = "EUR"
        txn.sourceLine = sourceLine
        txn.transactionTypeCode = transactionTypeCode
        txn.transactionReference = reference
        return txn
    }

    // MARK: - Balance parsing (`:60F:`/`:62F:`, mt940.py:76/225)

    /// `float(balance_str.split("EUR")[1].replace(",", "."))` — `nil`
    /// (leaving the prior start/end balance untouched, matching Python's
    /// `except Exception: pass`) if `"EUR"` doesn't occur in `balanceStr` or
    /// the remainder isn't numeric.
    private static func parseEURBalance(_ balanceStr: String) -> Double? {
        let parts = balanceStr.components(separatedBy: "EUR")
        guard parts.count > 1 else { return nil }
        return Double(parts[1].replacingOccurrences(of: ",", with: "."))
    }

    // MARK: - Line splitting

    /// `f.readlines()` under Python's universal-newline text mode: splits on
    /// `\r\n`/`\r`/`\n` uniformly, with no trailing empty element for a file
    /// that ends in a newline.
    private static func readLines(_ content: String) -> [String] {
        let normalized = content
            .replacingOccurrences(of: "\r\n", with: "\n")
            .replacingOccurrences(of: "\r", with: "\n")
        var lines = normalized.components(separatedBy: "\n")
        if lines.last == "" {
            lines.removeLast()
        }
        return lines
    }
}

/// The mutable, partially-built transaction the `:61:`/`:86:`/`:60F:`/`:62F:`
/// state machine accumulates — the Swift analog of Python's
/// `current_transaction` dict. `nil` (absent, not this type) represents
/// Python's `current_transaction = {}` falsy state.
private struct MT940Transaction {
    var transactiondate: Date?
    var amount: Double?
    var accountNumber: String = ""
    var currency: String = "EUR"
    var sourceLine: Int?
    var transactionTypeCode: String?
    var transactionReference: String?
    var description: String?
    var descriptionStructured: String?
    var startsaldo: Double?
    var endsaldo: Double?
    var valuedate: Date?
    var mutationcode: String = ""

    /// `"description" in current_transaction and current_transaction.get("description")`
    /// — key present *and* the value is a non-empty string.
    var hasNonEmptyDescription: Bool {
        guard let description else { return false }
        return !description.isEmpty
    }

    func toParsedTransaction() -> ParsedTransaction {
        ParsedTransaction(
            accountNumber: accountNumber,
            transactiondate: transactiondate,
            valuedate: valuedate,
            startsaldo: startsaldo,
            endsaldo: endsaldo,
            amount: amount,
            description: description,
            descriptionStructured: descriptionStructured,
            mutationcode: mutationcode,
            currency: currency,
            sourceFile: nil, // stamped by StatementFileParser.swift, matching parsers/__init__.py
            sourceLine: sourceLine,
            transactionTypeCode: transactionTypeCode,
            transactionReference: transactionReference
        )
    }
}
