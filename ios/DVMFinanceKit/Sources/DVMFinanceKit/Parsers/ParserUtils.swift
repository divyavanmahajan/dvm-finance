import Foundation

/// Port of `src/abn_combined/parsers/utils.py`.
///
/// Only `parse_date`/`parse_decimal` are ported (`save_to_csv`/`save_to_json`
/// are desktop export helpers with no iOS caller — the app never writes CSV
/// exports).
public enum ParserUtils {

    /// Port of `parsers/utils.py:parse_date`.
    ///
    /// Python's version calls `pandas.to_datetime(date_value)`, which is
    /// extremely tolerant (it accepts dozens of formats, locale-dependent
    /// day/month ordering heuristics, `Timestamp`/`date` passthrough, etc.).
    /// This port only recognizes the formats that can actually occur in the
    /// **inputs this app supports**: the generic ABN-style CSV path
    /// (`CSVParser.swift`, `parsers/csv.py`) is the only caller of this
    /// function — MT940 dates are parsed directly from fixed-width `YYMMDD`
    /// (`MT940Parser.swift`), and PayPal/Wise/SEB each have their own local
    /// `_parse_date` (ported separately in `PayPalParser.swift`/
    /// `WiseParser.swift`/`SEBParser.swift`, matching the Python files
    /// exactly). There is no golden ABN-CSV fixture in this repo (only
    /// mt940/paypal/seb/wise fixtures exist), so the formats below are a
    /// deliberately conservative superset covering every format
    /// `pandas.to_datetime` would resolve unambiguously for a plain date
    /// string, in the order pandas would try them:
    ///   - `yyyy-MM-dd` (ISO, unambiguous — pandas' preferred format)
    ///   - `yyyy-MM-dd HH:mm:ss` / `yyyy-MM-dd'T'HH:mm:ss` (ISO datetime;
    ///     pandas parses these and `.date()`-truncates, matching
    ///     `parse_date`'s `date_value.date()` branch for a `Timestamp`)
    ///   - `dd-MM-yyyy` and `dd/MM/yyyy` (day-first, the convention every
    ///     other parser in this codebase — MT940/PayPal/SEB — uses for
    ///     non-ISO dates, so it is the most plausible ambiguous-format
    ///     fallback for a hand-exported ABN CSV)
    /// Any other input, or an unparsable one, returns `nil` (Python: the
    /// `except Exception: return None` branch). Empty string / whitespace
    /// input also returns `nil` (Python: `date_value == ""`).
    public static func parseDate(_ value: String?) -> Date? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return nil }

        for formatter in dateFormatters {
            if let date = formatter.date(from: trimmed) {
                return date
            }
        }
        return nil
    }

    private static let dateFormatters: [DateFormatter] = [
        "yyyy-MM-dd",
        "yyyy-MM-dd'T'HH:mm:ss",
        "yyyy-MM-dd HH:mm:ss",
        "dd-MM-yyyy",
        "dd/MM/yyyy",
    ].map { pattern in
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = pattern
        return formatter
    }

    /// Port of `parsers/utils.py:parse_decimal`.
    ///
    /// Strips `€` and whitespace, replaces `,` with `.`, then parses as a
    /// `Double`. This is the **generic** utils version used only by
    /// `CSVParser.swift` (`csv.py`'s `parse_decimal(row.get("amount"))`
    /// calls) — PayPal/Wise/SEB each have their own local number-parsing
    /// function, ported separately (see `PayPalParser.swift`'s
    /// `_parse_european_number`, `WiseParser.swift`/`SEBParser.swift`'s
    /// `_parse_decimal`), matching the Python source file-by-file rather than
    /// sharing this one.
    ///
    /// `nil`/empty input -> `nil` (Python: `pd.isna(value) or value is None or
    /// value == ""`). Unparsable non-numeric string -> `nil` (Python's
    /// `except Exception: return None`).
    public static func parseDecimal(_ value: String?) -> Double? {
        guard let value else { return nil }
        let cleaned = value
            .replacingOccurrences(of: "\u{20AC}", with: "")
            .replacingOccurrences(of: ",", with: ".")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if cleaned.isEmpty { return nil }
        return Double(cleaned)
    }

    /// Constructs a UTC calendar date from `(year, month, day)`, returning
    /// `nil` for out-of-range components exactly like Python's `date(year,
    /// month, day)` constructor raising `ValueError` (e.g. `month=13`,
    /// `day=32`, or `day=29` in a non-leap February) — unlike
    /// `Calendar.date(from:)`, which silently normalizes overflowing
    /// components instead of failing, this validates the day against the
    /// actual number of days in the target month first. Shared by every
    /// parser that builds dates from individually-parsed y/m/d integers
    /// (`MT940Parser.swift`'s `:61:`/`:60F:`/`:62F:` dates).
    static func makeUTCDate(year: Int, month: Int, day: Int) -> Date? {
        guard month >= 1, month <= 12, day >= 1 else { return nil }
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        guard let firstOfMonth = calendar.date(from: DateComponents(year: year, month: month, day: 1)) else {
            return nil
        }
        guard let dayRange = calendar.range(of: .day, in: .month, for: firstOfMonth), dayRange.contains(day) else {
            return nil
        }
        return calendar.date(from: DateComponents(year: year, month: month, day: day))
    }

    /// Reads a file as UTF-8, stripping a leading byte-order mark if present
    /// — matches Python's `encoding="utf-8-sig"` (used by
    /// `parsers/paypal.py`, `parsers/wise.py`, and the first `parsers/seb.py`
    /// decode attempt): a BOM is discarded if present, and plain UTF-8
    /// (no BOM) decodes unchanged.
    static func readFileStrippingBOM(_ url: URL) throws -> String {
        var data = try Data(contentsOf: url)
        let bom: [UInt8] = [0xEF, 0xBB, 0xBF]
        if data.count >= 3, Array(data.prefix(3)) == bom {
            data.removeFirst(3)
        }
        guard let content = String(data: data, encoding: .utf8) else {
            throw ParserError.decodingFailed
        }
        return content
    }
}
