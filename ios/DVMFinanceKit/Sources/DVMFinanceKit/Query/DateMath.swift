import Foundation

/// Shared UTC-pinned calendar arithmetic backing `TransactionFilter`'s preset
/// resolution (port of `core/filters.py:resolve_preset_range`/`_month_end`)
/// and `TrendsBuilder`'s window/period math (port of
/// `core/trends.py:default_window`/`build_periods`/`_month_end`/
/// `_shift_month`).
///
/// Pinned to UTC (not `Calendar.current`) to match `DatabaseDateFormat`'s
/// convention: every day-only `Date` this codebase stores/compares is
/// midnight UTC on the given calendar day (see
/// `Database/DatabaseDateFormat.swift`). Using the device's local calendar
/// here would risk off-by-one-day drift for users outside UTC.
enum DateMath {
    static let calendar: Calendar = {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        return cal
    }()

    /// Builds a UTC midnight `Date` for the given calendar day.
    static func date(_ year: Int, _ month: Int, _ day: Int) -> Date {
        calendar.date(from: DateComponents(year: year, month: month, day: day))!
    }

    static func components(_ date: Date) -> (year: Int, month: Int, day: Int) {
        let c = calendar.dateComponents([.year, .month, .day], from: date)
        return (c.year!, c.month!, c.day!)
    }

    static func daysInMonth(year: Int, month: Int) -> Int {
        let anchor = calendar.date(from: DateComponents(year: year, month: month, day: 1))!
        return calendar.range(of: .day, in: .month, for: anchor)!.count
    }

    /// Port of `core/filters.py:_month_end` / `core/trends.py:_month_end`.
    static func monthEnd(year: Int, month: Int) -> Date {
        date(year, month, daysInMonth(year: year, month: month))
    }

    /// Floor division (Python `//`), needed because Swift's `/` truncates
    /// toward zero while Python's floors toward negative infinity — matters
    /// for `shiftMonth` when the shifted index goes negative.
    private static func floorDiv(_ a: Int, _ b: Int) -> Int {
        let q = a / b
        let r = a % b
        return (r != 0 && (r < 0) != (b < 0)) ? q - 1 : q
    }

    /// Floor modulo (Python `%`), always non-negative for a positive `b`.
    private static func floorMod(_ a: Int, _ b: Int) -> Int {
        a - floorDiv(a, b) * b
    }

    /// Port of `core/trends.py:_shift_month`: `index = year*12 + (month-1) +
    /// delta; return index // 12, index % 12 + 1`.
    static func shiftMonth(year: Int, month: Int, by delta: Int) -> (year: Int, month: Int) {
        let index = year * 12 + (month - 1) + delta
        return (floorDiv(index, 12), floorMod(index, 12) + 1)
    }

    /// `(y1, m1) <= (y2, m2)` — Swift's stdlib only synthesizes `<` for
    /// homogeneous tuples, not `<=`/`>`/`>=`, so `build_periods`' `while
    /// (year, month) <= (window_to.year, window_to.month):` loop condition
    /// is spelled out explicitly here.
    static func monthKeyLessOrEqual(_ y1: Int, _ m1: Int, _ y2: Int, _ m2: Int) -> Bool {
        y1 < y2 || (y1 == y2 && m1 <= m2)
    }

    /// Port of `core/trends.py:default_window`: the last 12 full months,
    /// current month excluded.
    static func defaultWindow(today: Date) -> (from: Date, to: Date) {
        let (ty, tm, _) = components(today)
        let (endYear, endMonth) = shiftMonth(year: ty, month: tm, by: -1)
        let (startYear, startMonth) = shiftMonth(year: endYear, month: endMonth, by: -11)
        return (date(startYear, startMonth, 1), monthEnd(year: endYear, month: endMonth))
    }
}
