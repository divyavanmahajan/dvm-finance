import Foundation

/// View-layer presentation formatting shared by the app target's screens.
/// Deliberately not part of `DVMFinanceKit`: this is display-only rendering
/// (date/currency/compact-number strings), not business logic — the
/// underlying values (`TransactionRecord.transactiondate`/`.amount`, `Query`
/// aggregates) come entirely from the Kit; see `ios/docs/plan.md` "Phase E":
/// "Keep views thin; NO business logic in the app target".
enum DisplayFormat {
    /// UTC-pinned, matching `DatabaseDateFormat`'s storage convention
    /// (`DVMFinanceKit/Database/DatabaseDateFormat.swift`): every
    /// day-granularity `Date` this app stores/compares is midnight UTC on
    /// the given calendar day. Formatting with the device's local time zone
    /// instead could roll a date back or forward a day for users outside
    /// UTC (e.g. midnight UTC is still "yesterday evening" west of
    /// Greenwich).
    private static let utcTimeZone = TimeZone(identifier: "UTC")!

    static let sectionDate: DateFormatter = {
        let formatter = DateFormatter()
        formatter.timeZone = utcTimeZone
        formatter.dateStyle = .full
        formatter.timeStyle = .none
        return formatter
    }()

    static let mediumDate: DateFormatter = {
        let formatter = DateFormatter()
        formatter.timeZone = utcTimeZone
        formatter.dateStyle = .medium
        formatter.timeStyle = .none
        return formatter
    }()

    /// For `DateTime` columns (`rule_change_reports.created_at`/
    /// `snapshot_imports.created_at`) — these carry a real time-of-day, not
    /// just a calendar day, so the audit history lists show both.
    static let mediumDateTime: DateFormatter = {
        let formatter = DateFormatter()
        formatter.timeZone = utcTimeZone
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter
    }()

    /// Currency-formatted `Decimal`, using the transaction's own currency
    /// code (not the device locale's currency) — every amount/saldo in this
    /// app is already tagged with its `currency` column.
    static func currency(_ amount: Decimal, code: String) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.currencyCode = code
        formatter.locale = Locale(identifier: "en_US_POSIX")
        return formatter.string(from: NSDecimalNumber(decimal: amount)) ?? "\(amount) \(code)"
    }

    /// Currency-formatted `Double`, for budget/actual figures which come off
    /// the report builder as `Double` sums rather than a single record's
    /// `Decimal`. Defaults to EUR (the app's home currency).
    static func currency(_ value: Double, code: String = "EUR") -> String {
        currency(Decimal(value), code: code)
    }

    /// Compact form for narrow trends-table cells, e.g. `-1.2K`, `3.4M`. Full
    /// precision is always available on tap (row/cell detail), so lossy
    /// rounding here is a deliberate legibility trade-off, not a data
    /// concern.
    static func compactAmount(_ value: Double) -> String {
        let magnitude = abs(value)
        let sign = value < 0 ? "-" : ""
        if magnitude >= 1_000_000 {
            return String(format: "%@%.1fM", sign, magnitude / 1_000_000)
        }
        if magnitude >= 1_000 {
            return String(format: "%@%.1fK", sign, magnitude / 1_000)
        }
        return String(format: "%@%.0f", sign, magnitude)
    }

    /// Plain fixed-point amount (no currency symbol), for trends totals rows
    /// and detail popovers where the column header already establishes the
    /// unit.
    static func plainAmount(_ value: Double) -> String {
        String(format: "%.2f", value)
    }
}
