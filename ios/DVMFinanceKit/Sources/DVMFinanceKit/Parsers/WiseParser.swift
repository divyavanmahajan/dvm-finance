import Foundation

/// Port of `src/abn_combined/parsers/wise.py` — the Wise transaction-history
/// CSV export (comma-delimited, header row, read as `utf-8-sig`).
///
/// The `db`-backed historical-rate lookup (`wise.py:79-106`,
/// `_lookup_eur_rate_from_db`) is **not** ported: it is only consulted when
/// `parse_wise_file(file_path, db=...)` is called with a live SQLAlchemy
/// session (the desktop upload path threading in prior uploads' rates), and
/// the iOS file-import flow has no such cross-file rate history to offer —
/// every call here is the Python equivalent of `db=None`, which always skips
/// straight past that branch. The in-CSV rate lookup (`_best_csv_rate`,
/// two-pass over the same file) is fully ported, since it's file-local.
public enum WiseParser {

    public static func parse(fileURL: URL) throws -> [ParsedTransaction] {
        let content = try ParserUtils.readFileStrippingBOM(fileURL)
        return parse(content: content, fileName: fileURL.lastPathComponent)
    }

    /// The pure-function core, separated from file I/O for testability.
    static func parse(content: String, fileName: String) -> [ParsedTransaction] {
        let rows = CSVTokenizer.parse(content, delimiter: ",")
        guard let headerRow = rows.first else { return [] }

        var records: [[String: String]] = []
        for fields in rows.dropFirst() {
            var record: [String: String] = [:]
            for (i, header) in headerRow.enumerated() where i < fields.count {
                record[header] = fields[i]
            }
            records.append(record)
        }

        // Pass 1 (wise.py:129-145): collect EUR->currency rates from
        // Transfer IN rows in this CSV, keyed by target currency.
        var csvEURRates: [String: [(Date, Double)]] = [:]
        for row in records {
            let status = (row["Status"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if status == "CANCELLED" || status == "REFUNDED" { continue }
            let direction = (row["Direction"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            guard direction == "IN" else { continue }
            let srcCcy = (row["Source currency"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let tgtCcy = (row["Target currency"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            guard srcCcy == "EUR", !tgtCcy.isEmpty, tgtCcy != "EUR" else { continue }
            let rate = parseWiseDecimal((row["Exchange rate"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines))
            let d = parseWiseDate((row["Created on"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines))
            if let rate, rate > 0, let d {
                csvEURRates[tgtCcy, default: []].append((d, rate))
            }
        }

        func bestCSVRate(_ currency: String, onOrBefore: Date) -> Double? {
            let entries = (csvEURRates[currency] ?? []).filter { $0.0 <= onOrBefore }
            guard !entries.isEmpty else { return nil }
            return entries.max(by: { $0.0 < $1.0 })!.1
        }

        var transactions: [ParsedTransaction] = []

        for (offset, row) in records.enumerated() {
            let lineNum = offset + 2

            let status = (row["Status"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if status == "CANCELLED" || status == "REFUNDED" { continue }

            let wiseId = (row["ID"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let direction = (row["Direction"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let createdOn = (row["Created on"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let finishedOn = (row["Finished on"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let sourceFeeAmt = (row["Source fee amount"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let sourceFeeCcy = (row["Source fee currency"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let sourceName = (row["Source name"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let sourceAmtStr = (row["Source amount (after fees)"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let sourceCurrency = (row["Source currency"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let targetName = (row["Target name"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let targetAmtStr = (row["Target amount (after fees)"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let targetCurrency = (row["Target currency"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let exchangeRate = (row["Exchange rate"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let reference = (row["Reference"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let wiseCategory = (row["Category"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let note = (row["Note"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)

            guard let transDate = parseWiseDate(createdOn) else { continue }

            let sourceAmount = parseWiseDecimal(sourceAmtStr) ?? 0.0
            let amount = direction == "OUT" ? -sourceAmount : sourceAmount

            let description: String
            if !targetName.isEmpty {
                description = "\(targetName):\(wiseId)"
            } else if !reference.isEmpty {
                description = "Wise Transfer:\(wiseId):\(reference)"
            } else {
                description = "Wise:\(wiseId)"
            }

            let structured = Fields()
            structured.setString("wise_id", wiseId)
            structured.setString("status", status)
            structured.setString("direction", direction)
            structured.setString("created_on", createdOn)
            structured.setString("finished_on", finishedOn)
            structured.setStringOrNull("source_fee_amount", sourceFeeAmt)
            structured.setStringOrNull("source_fee_currency", sourceFeeCcy)
            structured.setString("source_name", sourceName)
            structured.setString("source_amount", sourceAmtStr)
            structured.setString("source_currency", sourceCurrency)
            structured.setStringOrNull("target_name", targetName)
            structured.setStringOrNull("target_amount", targetAmtStr)
            structured.setStringOrNull("target_currency", targetCurrency)
            structured.setStringOrNull("exchange_rate", exchangeRate)
            structured.setStringOrNull("reference", reference)
            structured.setStringOrNull("wise_category", wiseCategory)
            structured.setStringOrNull("note", note)
            structured.setString("format", "wise")

            let accountNumber = wiseAccount(direction: direction, sourceName: sourceName, targetName: targetName)
            let category: String? = direction == "IN" ? "transfer" : nil

            var storedAmount = amount
            var storedCurrency = sourceCurrency.isEmpty ? "EUR" : sourceCurrency

            if direction == "OUT", !sourceCurrency.isEmpty, sourceCurrency != "EUR" {
                // `db` lookup intentionally not ported — see the type doc
                // comment; this always behaves as Python's `db=None` path.
                if let eurRate = bestCSVRate(sourceCurrency, onOrBefore: transDate), eurRate > 0 {
                    storedAmount = -(sourceAmount / eurRate)
                    storedCurrency = "EUR"
                    structured.setString("native_amount", sourceAmtStr)
                    structured.setString("native_currency", sourceCurrency)
                    structured.setNumber("eur_rate_used", eurRate)
                }
            }

            var transaction = ParsedTransaction(
                accountNumber: accountNumber,
                transactiondate: transDate,
                valuedate: parseWiseDate(finishedOn) ?? transDate,
                // `round(stored_amount, 2)` — Python's `round()` uses
                // round-half-to-even; `.toNearestOrEven` matches for the
                // clean 2-decimal monetary values these files contain.
                amount: (storedAmount * 100).rounded(.toNearestOrEven) / 100,
                description: description,
                currency: storedCurrency,
                sourceFile: fileName,
                sourceLine: lineNum,
                category: category,
                wiseTransactionId: wiseId
            )
            transaction.descriptionStructured = structured.toJSONString()
            transactions.append(transaction)
        }

        return transactions
    }

    // MARK: - wise.py:34-48

    private static func normalizeName(_ name: String) -> String {
        name.lowercased().replacingOccurrences(of: " ", with: "").replacingOccurrences(of: "-", with: "")
    }

    private static func wiseAccount(direction: String, sourceName: String, targetName: String) -> String {
        if direction == "OUT" {
            return sourceName.isEmpty ? "wise" : "wise-\(normalizeName(sourceName))"
        } else {
            return targetName.isEmpty ? "wise" : "wise-\(normalizeName(targetName))"
        }
    }

    // MARK: - wise.py:51-60

    /// `float(Decimal(s))`.
    static func parseWiseDecimal(_ value: String) -> Double? {
        let s = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !s.isEmpty else { return nil }
        return Double(s)
    }

    // MARK: - wise.py:63-76

    /// `"YYYY-MM-DD HH:MM:SS"`, falling back to the first 10 characters as
    /// `"YYYY-MM-DD"`.
    static func parseWiseDate(_ value: String) -> Date? {
        let s = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !s.isEmpty else { return nil }
        if let date = wiseDateTimeFormatter.date(from: s) {
            return date
        }
        let prefix = String(s.prefix(10))
        return wiseDateOnlyFormatter.date(from: prefix)
    }

    private static let wiseDateTimeFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss"
        return formatter
    }()

    private static let wiseDateOnlyFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()
}
