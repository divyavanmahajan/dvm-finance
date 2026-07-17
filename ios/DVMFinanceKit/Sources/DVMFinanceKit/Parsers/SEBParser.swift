import Foundation

/// Port of `src/abn_combined/parsers/seb.py` — the SEB kontoutdrag CSV export
/// (semicolon-delimited, header row, `utf-8-sig` with a `latin-1` fallback).
///
/// SEK->EUR conversion depends on live ECB reference rates
/// (`_parse_ecb_xml`/`_build_rate_cache`, `seb.py:69-124`), fetched from
/// `eurofxref-hist-90d.xml`/`eurofxref-hist.xml` over HTTPS — ported
/// faithfully below (`fetchECBRateCache`/`parseECBXML`) for production use.
/// Because a live network fetch is inherently non-deterministic in an
/// offline unit test, the internal `parse(content:fileName:rateCache:)`
/// overload accepts an **injectable** rate cache: `nil` (used by the public
/// `parse(fileURL:)` entry point) fetches live from ECB exactly like Python;
/// a non-nil cache — as `ParserTests.swift`'s golden-fixture test supplies,
/// reconstructed from `parser_expected.json`'s own `eur_rate_used`
/// values — skips the network call and exercises the identical conversion
/// arithmetic and JSON shape deterministically.
public enum SEBParser {

    private static let account = "seb:divyavanmahajan"
    private static let nativeCurrency = "SEK"
    private static let ecb90DayURL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
    private static let ecbHistURL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.xml"

    public enum SEBParserError: Error, Equatable {
        case decodingFailed
        case missingColumns
    }

    public static func parse(fileURL: URL) throws -> [ParsedTransaction] {
        let content = try readSEBContent(fileURL)
        return try parse(content: content, fileName: fileURL.lastPathComponent, rateCache: nil)
    }

    static func parse(content: String, fileName: String, rateCache providedRateCache: [Date: Double]?) throws -> [ParsedTransaction] {
        let rows = CSVTokenizer.parse(content, delimiter: ";")
        guard let headerRow = rows.first else { return [] }

        // seb.py:161-168.
        let expectedHeaders: Set<String> = ["Booking date", "Value date", "Voucher number", "Text", "Amount", "Balance"]
        guard expectedHeaders.isSubset(of: Set(headerRow)) else {
            throw SEBParserError.missingColumns
        }

        var records: [[String: String]] = []
        for fields in rows.dropFirst() {
            var record: [String: String] = [:]
            for (i, header) in headerRow.enumerated() where i < fields.count {
                record[header] = fields[i]
            }
            records.append(record)
        }
        if records.isEmpty { return [] }

        // seb.py:170-177: pre-fetch the rate cache covering every booking date.
        let bookingDates = records.compactMap { parseSEBDate($0["Booking date"] ?? "") }
        let rateCache = providedRateCache ?? buildRateCache(dates: bookingDates)

        var transactions: [ParsedTransaction] = []

        for (offset, row) in records.enumerated() {
            let lineNum = offset + 2

            let bookingDate = parseSEBDate(row["Booking date"] ?? "")
            let valueDate = parseSEBDate(row["Value date"] ?? "")
            let voucher = (row["Voucher number"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let text = (row["Text"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let amountSEK = parseSEBDecimal(row["Amount"] ?? "")
            let balanceSEK = parseSEBDecimal(row["Balance"] ?? "")

            guard let bookingDate, let amountSEK else { continue }

            let structured = Fields()
            structured.setString("format", "seb")
            structured.setStringOrNull("voucher_number", voucher)
            structured.setNumber("native_amount", amountSEK)
            structured.setString("native_currency", nativeCurrency)
            structured.setNumberOrNull("native_balance", balanceSEK)

            let storedAmount: Double
            let storedBalance: Double?
            let storedCurrency: String

            if let eurRate = bestRate(rateCache, target: bookingDate), eurRate > 0 {
                // `round(x, 2)` — Python's round-half-to-even.
                storedAmount = (amountSEK / eurRate * 100).rounded(.toNearestOrEven) / 100
                storedBalance = balanceSEK.map { ($0 / eurRate * 100).rounded(.toNearestOrEven) / 100 }
                storedCurrency = "EUR"
                structured.setNumber("eur_rate_used", eurRate)
            } else {
                storedAmount = amountSEK
                storedBalance = balanceSEK
                storedCurrency = nativeCurrency
            }

            let transaction = ParsedTransaction(
                accountNumber: account,
                transactiondate: bookingDate,
                valuedate: valueDate ?? bookingDate,
                endsaldo: storedBalance,
                amount: storedAmount,
                description: text,
                descriptionStructured: structured.toJSONString(),
                currency: storedCurrency,
                sourceFile: fileName,
                sourceLine: lineNum,
                sebVoucherId: voucher.isEmpty ? nil : voucher
            )
            transactions.append(transaction)
        }

        return transactions
    }

    // MARK: - seb.py:142-152 encoding fallback

    /// `utf-8-sig`, falling back to `latin-1` (which never fails to decode —
    /// every byte 0-255 maps to a character) on invalid UTF-8.
    private static func readSEBContent(_ url: URL) throws -> String {
        let data = try Data(contentsOf: url)
        var stripped = data
        let bom: [UInt8] = [0xEF, 0xBB, 0xBF]
        if stripped.count >= 3, Array(stripped.prefix(3)) == bom {
            stripped.removeFirst(3)
        }
        if let content = String(data: stripped, encoding: .utf8) {
            return content
        }
        guard let content = String(data: data, encoding: .isoLatin1) else {
            throw SEBParserError.decodingFailed
        }
        return content
    }

    // MARK: - seb.py:47-56 `_parse_decimal`

    static func parseSEBDecimal(_ value: String) -> Double? {
        let s = value.trimmingCharacters(in: .whitespacesAndNewlines).replacingOccurrences(of: ",", with: ".")
        guard !s.isEmpty else { return nil }
        return Double(s)
    }

    // MARK: - seb.py:59-66 `_parse_date`

    static func parseSEBDate(_ value: String) -> Date? {
        let s = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !s.isEmpty else { return nil }
        return sebDateFormatter.date(from: s)
    }

    private static let sebDateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()

    // MARK: - seb.py:114-124 `_best_rate`

    static func bestRate(_ cache: [Date: Double], target: Date) -> Double? {
        if let exact = cache[target] { return exact }
        let earlier = cache.keys.filter { $0 <= target }
        if let latestEarlier = earlier.max() { return cache[latestEarlier] }
        if let oldest = cache.keys.min() { return cache[oldest] }
        return nil
    }

    // MARK: - seb.py:96-111 `_build_rate_cache`

    private static func buildRateCache(dates: [Date]) -> [Date: Double] {
        var cache = fetchECBXML(ecb90DayURL)
        if let oldestNeeded = dates.min(), let oldestCached = cache.keys.min(), oldestNeeded < oldestCached {
            let hist = fetchECBXML(ecbHistURL)
            for (key, value) in hist { cache[key] = value }
        }
        return cache
    }

    // MARK: - seb.py:69-93 `_parse_ecb_xml`

    /// Best-effort live fetch: any failure (network, malformed XML) yields
    /// an empty cache, matching Python's `except Exception: pass`.
    /// `URLSession`/`Data(contentsOf:)` has no direct `timeout=15` parameter
    /// equivalent at this call site; the platform default request timeout
    /// applies instead.
    private static func fetchECBXML(_ urlString: String) -> [Date: Double] {
        guard let url = URL(string: urlString), let data = try? Data(contentsOf: url) else { return [:] }
        return parseECBXML(data)
    }

    /// SAX parse of the ECB `eurofxref` feed: `<Cube><Cube time="...">
    /// <Cube currency="SEK" rate="..."/>...</Cube></Cube>`. Matches
    /// Python's `ElementTree` namespace-qualified `.//{ns}Cube[@time]`
    /// search structurally (day cubes have a `time` attribute, currency
    /// cubes are their direct children) — `XMLParser`'s default
    /// (non-namespace-aware) mode already reports the plain tag name
    /// `"Cube"` regardless of the feed's default `xmlns`, so no namespace
    /// handling is needed here.
    static func parseECBXML(_ data: Data) -> [Date: Double] {
        let delegate = ECBXMLDelegate()
        let parser = XMLParser(data: data)
        parser.delegate = delegate
        _ = parser.parse()
        return delegate.cache
    }

    private static let ecbDayFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()

    private final class ECBXMLDelegate: NSObject, XMLParserDelegate {
        var cache: [Date: Double] = [:]
        private var currentDay: Date?

        func parser(
            _ parser: XMLParser,
            didStartElement elementName: String,
            namespaceURI: String?,
            qualifiedName qName: String?,
            attributes attributeDict: [String: String] = [:]
        ) {
            guard elementName == "Cube" else { return }
            if let timeStr = attributeDict["time"] {
                currentDay = SEBParser.ecbDayFormatter.date(from: timeStr)
                return
            }
            if attributeDict["currency"] == "SEK",
               let currentDay,
               let rateStr = attributeDict["rate"],
               let rate = Double(rateStr) {
                cache[currentDay] = rate
            }
        }
    }
}
