import Foundation

/// Port of `src/abn_combined/parsers/csv.py` — the generic ABN-style CSV
/// import path (delimited file with a header row using column names like
/// `accountNumber`/`transactiondate`/`amount`/`description`). PayPal, Wise,
/// and SEB have their own dedicated parsers (`PayPalParser.swift`,
/// `WiseParser.swift`, `SEBParser.swift`) and are never routed through this
/// one — same split as the Python package (`csv.py`'s module doc: "PayPal,
/// Wise and SEB have their own dedicated parsers and are dispatched
/// explicitly, not through this generic path").
///
/// No golden fixture exists for this parser (the four checked-in fixtures
/// under `Tests/Fixtures/` are mt940/paypal/seb/wise only — there is no ABN
/// generic-CSV sample in the repo). Implemented directly from `csv.py`'s
/// source with one documented, deliberate divergence: Python builds this on
/// `pandas.read_csv`, whose `Series.get(key, default)` only substitutes
/// `default` when a *column* is entirely absent — a present column with an
/// empty cell yields pandas' `NaN`, and `str(nan)` renders the literal
/// string `"nan"` for `accountNumber`/`mutationcode`/`description`. This
/// port has no pandas-equivalent NaN sentinel; an empty cell in a present
/// column decodes to `""`, not `"nan"`. Reproducing the `"nan"`-string
/// quirk would actively misrepresent real transaction data with no fixture
/// to justify it, so it is not ported.
public enum CSVParser {

    public enum CSVParserError: Error, Equatable {
        case missingRequiredColumns
    }

    /// `_COLUMN_MAPPING` (csv.py:18-36) — lowercased, whitespace-trimmed
    /// header name -> canonical field name. A header not present in this
    /// table keeps its lowercased/trimmed form untouched, matching
    /// `pandas.DataFrame.rename(columns=...)`, which only renames columns
    /// present in the mapping dict.
    private static let columnMapping: [String: String] = [
        "accountnumber": "accountNumber",
        "account_number": "accountNumber",
        "mutationcode": "mutationcode",
        "mutation_code": "mutationcode",
        "transactiondate": "transactiondate",
        "transaction_date": "transactiondate",
        "date": "transactiondate",
        "valuedate": "valuedate",
        "value_date": "valuedate",
        "startsaldo": "startsaldo",
        "start_saldo": "startsaldo",
        "startbalance": "startsaldo",
        "endsaldo": "endsaldo",
        "end_saldo": "endsaldo",
        "endbalance": "endsaldo",
        "amount": "amount",
        "description": "description",
    ]

    public static func parse(fileURL: URL) throws -> [ParsedTransaction] {
        let content = try ParserUtils.readFileStrippingBOM(fileURL)
        return try parse(content: content, fileName: fileURL.lastPathComponent)
    }

    /// The pure-function core, separated from file I/O for testability.
    static func parse(content: String, fileName: String) throws -> [ParsedTransaction] {
        // `pd.read_csv(file_path, sep=None, engine="python")` (csv.py:43)
        // auto-detects the delimiter via `csv.Sniffer`. Approximated here by
        // picking whichever of comma/semicolon/tab is more frequent in the
        // header line — the same answer `Sniffer` gives for any
        // single-delimiter well-formed file, which is the only case this
        // port needs to support (no golden fixture exercises a pathological
        // one).
        let delimiter = sniffDelimiter(content)
        let rows = CSVTokenizer.parse(content, delimiter: delimiter)
        guard let headerRow = rows.first else { return [] }

        // `df.columns = df.columns.str.lower().str.strip()` then `.rename(columns=_COLUMN_MAPPING)`.
        let headers = headerRow.map { header -> String in
            let lowered = header.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
            return columnMapping[lowered] ?? lowered
        }

        guard headers.contains("amount"), headers.contains("transactiondate") else {
            throw CSVParserError.missingRequiredColumns
        }

        var transactions: [ParsedTransaction] = []
        for (offset, fields) in rows.dropFirst().enumerated() {
            var row: [String: String] = [:]
            for (i, header) in headers.enumerated() where i < fields.count {
                row[header] = fields[i]
            }

            let description = row["description"] ?? ""
            let currency: String
            if let raw = row["currency"], !raw.isEmpty {
                currency = raw.uppercased()
            } else {
                currency = "EUR"
            }

            var transaction = ParsedTransaction(
                accountNumber: row["accountNumber"] ?? "",
                transactiondate: ParserUtils.parseDate(row["transactiondate"]),
                valuedate: ParserUtils.parseDate(row["valuedate"]),
                startsaldo: ParserUtils.parseDecimal(row["startsaldo"]),
                endsaldo: ParserUtils.parseDecimal(row["endsaldo"]),
                // `parse_decimal(row.get("amount", 0))` — the `0` default is
                // effectively dead code in Python (the "amount" column is
                // already known present, per the guard above, so `.get`
                // always finds the key); an unparsable/empty cell yields
                // `nil` here exactly as `parse_decimal(NaN)` yields `None`
                // there, not a `0` fallback.
                amount: ParserUtils.parseDecimal(row["amount"]),
                description: description,
                mutationcode: row["mutationcode"] ?? "",
                currency: currency,
                sourceFile: fileName,
                sourceLine: offset + 2
            )
            transaction.descriptionStructured = DescriptionParser.parseTransactionDescription(description)
            transactions.append(transaction)
        }

        return transactions
    }

    private static func sniffDelimiter(_ content: String) -> Character {
        guard let firstLine = content.split(separator: "\n", maxSplits: 1, omittingEmptySubsequences: false).first else {
            return ","
        }
        let candidates: [Character] = [",", ";", "\t"]
        var best: Character = ","
        var bestCount = -1
        for candidate in candidates {
            let count = firstLine.filter { $0 == candidate }.count
            if count > bestCount {
                bestCount = count
                best = candidate
            }
        }
        return best
    }
}

// MARK: - Shared delimited-text tokenizer

/// A small RFC 4180-style tokenizer shared by every delimited-text parser in
/// this module (`CSVParser` itself, `WiseParser`, `SEBParser`, and
/// `PayPalParser`'s TAB-delimited variant) — each Python source uses the
/// standard library `csv` module or `pandas.read_csv`, both of which handle
/// quoted fields (embedded delimiters/newlines) and `""`-escaped literal
/// quotes; this is the from-scratch Swift equivalent, since Foundation has
/// no built-in CSV parser.
enum CSVTokenizer {
    /// Splits `content` into rows of fields. Recognizes `delimiter`-separated
    /// fields, double-quote-enclosed fields (which may contain embedded
    /// delimiters and newlines), `""` as an escaped literal quote inside a
    /// quoted field, and `\r\n`/`\r`/`\n` as row terminators.
    static func parse(_ content: String, delimiter: Character) -> [[String]] {
        var rows: [[String]] = []
        var currentRow: [String] = []
        var currentField = ""
        var inQuotes = false
        var rowHasContent = false

        let chars = Array(content)
        var i = 0

        while i < chars.count {
            let c = chars[i]

            if inQuotes {
                if c == "\"" {
                    if i + 1 < chars.count, chars[i + 1] == "\"" {
                        currentField.append("\"")
                        i += 2
                    } else {
                        inQuotes = false
                        i += 1
                    }
                } else {
                    currentField.append(c)
                    i += 1
                }
                continue
            }

            switch c {
            case "\"" where currentField.isEmpty:
                inQuotes = true
                rowHasContent = true
                i += 1
            case delimiter:
                currentRow.append(currentField)
                currentField = ""
                rowHasContent = true
                i += 1
            case "\r", "\n":
                if c == "\r", i + 1 < chars.count, chars[i + 1] == "\n" {
                    i += 1
                }
                currentRow.append(currentField)
                rows.append(currentRow)
                currentRow = []
                currentField = ""
                rowHasContent = false
                i += 1
            default:
                currentField.append(c)
                rowHasContent = true
                i += 1
            }
        }

        // Trailing row with no terminating newline at EOF.
        if rowHasContent || !currentField.isEmpty || !currentRow.isEmpty {
            currentRow.append(currentField)
            rows.append(currentRow)
        }

        return rows
    }
}
