import Foundation
import GRDB

/// Port of `src/abn_combined/core/budget_report.py`: budget-vs-actual
/// aggregation for the iOS Budgets tab.
///
/// Actual spend uses the *effective* category (manual precedence:
/// `COALESCE(NULLIF(manual_category, ''), category)`) with hierarchical
/// prefix matching (`food` also matches `food-restaurants`), summing
/// `ABS(amount)` inside the period window. Transfers are excluded by the same
/// `%transfer%` CONTAINS convention `TransactionQuery.whereClause` uses.
public enum BudgetReport {

    /// Port of `budget_report.py:PERIODS`. Raw values match the stored
    /// `budgets.period` column and desktop's `?period=` query state.
    public enum Period: String, CaseIterable, Identifiable, Hashable {
        case year
        case month
        case week
        public var id: String { rawValue }
        public var label: String { rawValue.capitalized }
    }

    /// Port of `budget_report.py:budget_status` — 'over' / 'near' (>= 80%) /
    /// 'under'.
    public enum Status: String {
        case over
        case near
        case under
    }

    public static let defaultAverageMonths = 3

    /// One report row: the budget plus its computed actuals for the current
    /// period window. Port of the dict `budget_vs_actual_table` yields.
    public struct Row: Identifiable, Equatable {
        public var id: Int64 { budgetId }
        public var budgetId: Int64
        public var category: String
        public var budget: Double
        public var actual: Double
        public var remaining: Double
        public var percentage: Double
        public var status: Status
        public var period: Period
        public var periodStart: Date
        public var periodEnd: Date
        public var startDate: Date?
        public var endDate: Date?
        public var notes: String?

        public init(
            budgetId: Int64, category: String, budget: Double, actual: Double,
            remaining: Double, percentage: Double, status: Status, period: Period,
            periodStart: Date, periodEnd: Date, startDate: Date?, endDate: Date?, notes: String?
        ) {
            self.budgetId = budgetId
            self.category = category
            self.budget = budget
            self.actual = actual
            self.remaining = remaining
            self.percentage = percentage
            self.status = status
            self.period = period
            self.periodStart = periodStart
            self.periodEnd = periodEnd
            self.startDate = startDate
            self.endDate = endDate
            self.notes = notes
        }
    }

    // MARK: - Period math (port of get_period_dates)

    /// Inclusive `(start, end)` window for the period containing
    /// `reference`. Port of `budget_report.py:get_period_dates`; uses
    /// `DateMath`'s UTC-pinned calendar for parity with the rest of the Kit.
    public static func periodDates(_ period: Period, reference: Date) -> (start: Date, end: Date) {
        let (year, month, _) = DateMath.components(reference)
        switch period {
        case .year:
            return (DateMath.date(year, 1, 1), DateMath.date(year, 12, 31))
        case .month:
            return (DateMath.date(year, month, 1), DateMath.monthEnd(year: year, month: month))
        case .week:
            // Python `ref.weekday()` is Monday=0..Sunday=6; SQLite/Foundation
            // gregorian weekday is Sunday=1..Saturday=7. Map to a Monday-based
            // offset so the week starts on Monday like desktop.
            let weekday = DateMath.calendar.component(.weekday, from: reference)
            let daysFromMonday = (weekday + 5) % 7
            let start = DateMath.calendar.date(byAdding: .day, value: -daysFromMonday, to: DateMath.calendar.startOfDay(for: reference))!
            let end = DateMath.calendar.date(byAdding: .day, value: 6, to: start)!
            return (start, end)
        }
    }

    // MARK: - Actual spend (port of compute_actual)

    /// Total `ABS(amount)` for the effective category (incl. hyphen-children)
    /// inside `[start, end]`. Port of `budget_report.py:compute_actual`.
    public static func computeActual(
        db: Database,
        category: String,
        start: Date,
        end: Date,
        excludeTransfers: Bool = true
    ) throws -> Double {
        let eff = TransactionQuery.effectiveCategorySQL
        let c = category.trimmingCharacters(in: .whitespaces).lowercased()
        var sql = """
            SELECT COALESCE(SUM(ABS(CAST(amount AS REAL))), 0) FROM transactions
            WHERE transactiondate >= ? AND transactiondate <= ?
            AND (LOWER(\(eff)) = ? OR LOWER(\(eff)) LIKE ?)
            """
        let arguments: [any DatabaseValueConvertible] = [
            DatabaseDateFormat.dateOnly.string(from: start),
            DatabaseDateFormat.dateOnly.string(from: end),
            c,
            "\(c)\(CoreNormalize.categorySeparator)%",
        ]
        if excludeTransfers {
            sql += " AND (\(eff) IS NULL OR \(eff) = '' OR \(eff) NOT LIKE '%transfer%')"
        }
        return try Double.fetchOne(db, sql: sql, arguments: StatementArguments(arguments)) ?? 0
    }

    /// Average monthly actual spend for `category` (incl. subtree) over the
    /// last `months` **full** calendar months before the month containing
    /// `reference` — the current in-progress month is excluded so a partial
    /// month never drags the average down. Port of
    /// `budget_report.py:average_monthly_spend`.
    public static func averageMonthlySpend(
        db: Database,
        category: String,
        months: Int = defaultAverageMonths,
        reference: Date = Date(),
        excludeTransfers: Bool = true
    ) throws -> Double {
        guard months > 0 else { return 0 }
        var (year, month, _) = DateMath.components(reference)
        var total = 0.0
        for _ in 0..<months {
            if month > 1 { month -= 1 } else { year -= 1; month = 12 }
            let (start, end) = periodDates(.month, reference: DateMath.date(year, month, 1))
            total += try computeActual(db: db, category: category, start: start, end: end, excludeTransfers: excludeTransfers)
        }
        return total / Double(months)
    }

    /// Distinct top-level (first-hyphen-segment) effective categories observed
    /// across transactions, sorted alphabetically. Port of
    /// `budget_report.py:distinct_top_level_categories`.
    public static func distinctTopLevelCategories(db: Database) throws -> [String] {
        let eff = TransactionQuery.effectiveCategorySQL
        let values = try String.fetchAll(
            db,
            sql: "SELECT DISTINCT LOWER(\(eff)) AS c FROM transactions WHERE \(eff) IS NOT NULL AND \(eff) != ''"
        )
        var tops: Set<String> = []
        for value in values {
            let top = value.split(separator: Character(CoreNormalize.categorySeparator), maxSplits: 1).first.map(String.init) ?? value
            tops.insert(top)
        }
        return tops.sorted { $0 < $1 }
    }

    /// Port of `budget_report.py:budget_status`.
    public static func status(actual: Double, budget: Double) -> Status {
        if actual > budget { return .over }
        if budget > 0 && actual >= budget * 0.8 { return .near }
        return .under
    }

    // MARK: - Report table (port of budget_vs_actual_table)

    /// One row per valid budget with actuals for its current period window.
    /// `period` restricts to budgets of one period type; validity dates
    /// exclude budgets whose window does not overlap `[start_date, end_date]`.
    /// Port of `budget_report.py:budget_vs_actual_table`.
    public static func budgetVsActual(
        db: Database,
        reference: Date = Date(),
        period: Period? = nil,
        excludeTransfers: Bool = true
    ) throws -> [Row] {
        var request = BudgetRecord.order(Column("category"))
        if let period {
            request = request.filter(Column("period") == period.rawValue)
        }
        let budgets = try request.fetchAll(db)
        var rows: [Row] = []
        for budget in budgets {
            guard let budgetId = budget.id, let period = Period(rawValue: budget.period) else { continue }
            let (periodStart, periodEnd) = periodDates(period, reference: reference)
            if let startDate = budget.startDate, periodEnd < startDate { continue } // not yet active
            if let endDate = budget.endDate, periodStart > endDate { continue } // expired
            let actual = try computeActual(
                db: db, category: budget.category, start: periodStart, end: periodEnd,
                excludeTransfers: excludeTransfers)
            let amount = NSDecimalNumber(decimal: budget.amount).doubleValue
            let percentage = amount > 0 ? ((actual / amount * 100) * 10).rounded() / 10 : 0
            rows.append(Row(
                budgetId: budgetId,
                category: budget.category,
                budget: amount,
                actual: actual,
                remaining: amount - actual,
                percentage: percentage,
                status: status(actual: actual, budget: amount),
                period: period,
                periodStart: periodStart,
                periodEnd: periodEnd,
                startDate: budget.startDate,
                endDate: budget.endDate,
                notes: budget.notes
            ))
        }
        return rows
    }
}
