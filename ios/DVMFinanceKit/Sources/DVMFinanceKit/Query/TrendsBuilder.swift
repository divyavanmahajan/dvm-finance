import Foundation
import GRDB

/// Port of `core/trends.py` — the category-trends matrix: effective category
/// × period (month or year), one SQL `GROUP BY` query, arranged into a
/// hierarchical (parent/children, hyphen-rollup) table in Swift, exactly
/// like the Python module's own split (SQL aggregates, Python arranges).
public enum TrendsBuilder {

    // MARK: - Params (port of core/trends.py: TrendsParams)

    public struct TrendsParams: Equatable {
        /// Port of `core/trends.py: GRANULARITIES`.
        public enum Granularity: String, CaseIterable, Identifiable, Sendable, Hashable {
            case month
            case year

            public var id: String { rawValue }
        }

        /// Port of `core/trends.py: TRENDS_SORTS`.
        public enum Sort: String, CaseIterable, Identifiable, Sendable, Hashable {
            case categoryAsc = "category_asc"
            case categoryDesc = "category_desc"
            case totalAsc = "total_asc"
            case totalDesc = "total_desc"

            public var id: String { rawValue }
        }

        public var granularity: Granularity
        public var dateFrom: Date?
        public var dateTo: Date?
        public var accounts: [String]
        public var includeTransfers: Bool
        public var sort: Sort

        public init(
            granularity: Granularity = .month,
            dateFrom: Date? = nil,
            dateTo: Date? = nil,
            accounts: [String] = [],
            includeTransfers: Bool = false,
            sort: Sort = .categoryAsc
        ) {
            self.granularity = granularity
            self.dateFrom = dateFrom
            self.dateTo = dateTo
            self.accounts = accounts
            self.includeTransfers = includeTransfers
            self.sort = sort
        }

        /// Port of `core/trends.py: TrendsParams.effective_window` — each
        /// missing side defaults independently to the last-12-full-months
        /// window.
        public func effectiveWindow(today: Date = Date()) -> (from: Date, to: Date) {
            let (lo, hi) = DateMath.defaultWindow(today: today)
            return (dateFrom ?? lo, dateTo ?? hi)
        }
    }

    // MARK: - Table structure (port of core/trends.py: Period/TrendRow/TrendsTable)

    public struct Period: Equatable {
        public var key: String
        public var label: String
        public var start: Date
        public var end: Date

        public init(key: String, label: String, start: Date, end: Date) {
            self.key = key
            self.label = label
            self.start = start
            self.end = end
        }
    }

    public struct TrendRow: Equatable {
        public var label: String
        /// The exact list of full category values this row covers — a
        /// single-element list for a leaf/uncategorized row, or every child
        /// category for a rolled-up parent row. See
        /// `TrendsBuilder.transactionFilter(for:period:accounts:includeTransfers:)`:
        /// this is what makes a cell tap "sum exactly to the cell" (spec.md
        /// "Filters & trends").
        public var categories: [String]
        public var cells: [String: Double]
        public var total: Double
        public var children: [TrendRow]

        public init(label: String, categories: [String], cells: [String: Double], total: Double, children: [TrendRow] = []) {
            self.label = label
            self.categories = categories
            self.cells = cells
            self.total = total
            self.children = children
        }

        public var hasChildren: Bool { !children.isEmpty }
    }

    public struct TrendsTable: Equatable {
        public var periods: [Period]
        public var rows: [TrendRow]
        public var columnTotals: [String: Double]
        public var grandTotal: Double
    }

    /// Port of `core/trends.py: UNCATEGORIZED_LABEL`.
    public static let uncategorizedLabel = "Uncategorized"

    static let monthLabels = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]

    // MARK: - Window / periods

    /// Port of `core/trends.py:default_window`.
    public static func defaultWindow(today: Date = Date()) -> (from: Date, to: Date) {
        DateMath.defaultWindow(today: today)
    }

    /// Port of `core/trends.py:build_periods`. Edge periods are clamped to
    /// the window so a period's `(start, end)` never selects transactions
    /// outside it (click-through correctness).
    public static func buildPeriods(
        windowFrom: Date,
        windowTo: Date,
        granularity: TrendsParams.Granularity
    ) -> [Period] {
        var periods: [Period] = []
        guard windowFrom <= windowTo else { return periods }

        let (fromYear, fromMonth, _) = DateMath.components(windowFrom)
        let (toYear, toMonth, _) = DateMath.components(windowTo)

        if granularity == .year {
            for year in fromYear...toYear {
                let start = max(DateMath.date(year, 1, 1), windowFrom)
                let end = min(DateMath.date(year, 12, 31), windowTo)
                periods.append(Period(key: String(year), label: String(year), start: start, end: end))
            }
            return periods
        }

        var year = fromYear
        var month = fromMonth
        while DateMath.monthKeyLessOrEqual(year, month, toYear, toMonth) {
            let start = max(DateMath.date(year, month, 1), windowFrom)
            let end = min(DateMath.monthEnd(year: year, month: month), windowTo)
            let key = String(format: "%04d-%02d", year, month)
            let label = "\(monthLabels[month - 1]) \(year)"
            periods.append(Period(key: key, label: label, start: start, end: end))
            (year, month) = DateMath.shiftMonth(year: year, month: month, by: 1)
        }
        return periods
    }

    // MARK: - Aggregation (port of core/trends.py:aggregate)

    /// Port of `core/trends.py:aggregate`.
    ///
    /// One `GROUP BY period_expr, eff_cat` SQL query
    /// (`strftime('%Y'|'%Y-%m', transactiondate)` × `LOWER(COALESCE(NULLIF(
    /// manual_category, ''), category))`), summing `CAST(amount AS REAL)` —
    /// desktop sums the same `Numeric(15,2)` column through SQLAlchemy,
    /// which resolves to SQLite floats in practice; this port makes that
    /// explicit rather than relying on SQLite's NUMERIC-affinity TEXT
    /// coercion (`amount` is stored `.text`, see
    /// `Decimal+DatabaseValueConvertible.swift`).
    public static func aggregate(
        db: Database,
        params: TrendsParams,
        today: Date = Date()
    ) throws -> TrendsTable {
        let (windowFrom, windowTo) = params.effectiveWindow(today: today)
        let periods = buildPeriods(windowFrom: windowFrom, windowTo: windowTo, granularity: params.granularity)

        let periodExpr = params.granularity == .year
            ? "strftime('%Y', transactiondate)"
            : "strftime('%Y-%m', transactiondate)"
        let effCatExpr = "LOWER(COALESCE(NULLIF(manual_category, ''), category))"

        var conditions = ["transactiondate >= ?", "transactiondate <= ?"]
        var arguments: [(any DatabaseValueConvertible)?] = [
            DatabaseDateFormat.dateOnly.string(from: windowFrom),
            DatabaseDateFormat.dateOnly.string(from: windowTo),
        ]
        if !params.accounts.isEmpty {
            let placeholders = params.accounts.map { _ in "?" }.joined(separator: ", ")
            conditions.append("accountNumber IN (\(placeholders))")
            arguments.append(contentsOf: params.accounts.map { $0 as (any DatabaseValueConvertible)? })
        }
        if !params.includeTransfers {
            conditions.append(
                "(\(effCatExpr) IS NULL OR \(effCatExpr) = '' OR \(effCatExpr) NOT LIKE '%transfer%')"
            )
        }

        let sql = """
            SELECT \(periodExpr) AS period_key, \(effCatExpr) AS cat, SUM(CAST(amount AS REAL)) AS total
            FROM transactions
            WHERE \(conditions.joined(separator: " AND "))
            GROUP BY \(periodExpr), \(effCatExpr)
            """
        let rows = try Row.fetchAll(db, sql: sql, arguments: StatementArguments(arguments))

        // cat -> {period_key: amount}. NULL and '' both fold into the `nil`
        // ("Uncategorized") bucket — Python: `by_cat.setdefault(cat or
        // None, {})` — even though SQL groups NULL and '' as two separate
        // rows, so this dictionary build is where the accumulation happens
        // (port of core/trends.py:279-282).
        var byCat: [String?: [String: Double]] = [:]
        for row in rows {
            let periodKey: String = row["period_key"]
            let rawCat: String? = row["cat"]
            let amount: Double = row["total"]
            let key: String? = (rawCat?.isEmpty ?? true) ? nil : rawCat
            byCat[key, default: [:]][periodKey, default: 0.0] += amount
        }

        let uncategorizedCells = byCat.removeValue(forKey: nil)

        // Group full category values by their top-level (first hyphen
        // segment) parent (core/trends.py:287-289).
        var groups: [String: [String]] = [:]
        for case let cat? in byCat.keys {
            groups[firstSegment(cat), default: []].append(cat)
        }

        var rows2: [TrendRow] = []
        for parentLabel in groups.keys.sorted() {
            let cats = groups[parentLabel]!.sorted()
            if cats == [parentLabel] {
                rows2.append(leafRow(parentLabel, byCat[parentLabel] ?? [:]))
                continue
            }
            let children = cats.map { leafRow($0, byCat[$0] ?? [:]) }
            var parentCells: [String: Double] = [:]
            for child in children {
                for (key, amount) in child.cells {
                    parentCells[key, default: 0] += amount
                }
            }
            rows2.append(
                TrendRow(
                    label: parentLabel,
                    categories: cats,
                    cells: parentCells,
                    total: parentCells.values.reduce(0, +),
                    children: children
                )
            )
        }

        if let uncategorizedCells {
            rows2.append(
                TrendRow(
                    label: uncategorizedLabel,
                    categories: [TransactionFilter.uncategorized],
                    cells: uncategorizedCells,
                    total: uncategorizedCells.values.reduce(0, +)
                )
            )
        }

        var columnTotals: [String: Double] = [:]
        for row in rows2 {
            for (key, amount) in row.cells {
                columnTotals[key, default: 0] += amount
            }
        }

        let sortedRows = sortRows(rows2, sort: params.sort)

        return TrendsTable(
            periods: periods,
            rows: sortedRows,
            columnTotals: columnTotals,
            grandTotal: columnTotals.values.reduce(0, +)
        )
    }

    /// Port of `core/trends.py:_sort_rows`. Children within a parent row are
    /// never touched — only the top-level row order changes.
    static func sortRows(_ rows: [TrendRow], sort: TrendsParams.Sort) -> [TrendRow] {
        switch sort {
        case .totalAsc:
            return rows.sorted { $0.total < $1.total }
        case .totalDesc:
            return rows.sorted { $0.total > $1.total }
        case .categoryDesc:
            return rows.sorted { $0.label.lowercased() > $1.label.lowercased() }
        case .categoryAsc:
            return rows.sorted { $0.label.lowercased() < $1.label.lowercased() }
        }
    }

    /// Port of `core/trends.py:_leaf_row`.
    private static func leafRow(_ cat: String, _ cells: [String: Double]) -> TrendRow {
        TrendRow(label: cat, categories: [cat], cells: cells, total: cells.values.reduce(0, +))
    }

    /// `cat.split(SEPARATOR, 1)[0]` — the top-level (first-hyphen-segment)
    /// parent of a full category value.
    private static func firstSegment(_ cat: String) -> String {
        guard let range = cat.range(of: CoreNormalize.categorySeparator) else { return cat }
        return String(cat[cat.startIndex..<range.lowerBound])
    }

    // MARK: - Click-through (port of core/trends.py:transactions_link, minus the URL)

    /// Builds the `TransactionFilter` selecting exactly the transactions
    /// behind a cell/row — port of `core/trends.py:transactions_link`,
    /// minus URL serialization (there is no `/transactions?...` route on
    /// iOS; the filter value itself is pushed onto the navigation stack).
    ///
    /// Deviation: unlike `transactions_link` (which never sets
    /// `include_transfers` on the built filter, always leaving it at its
    /// `False` default), this passes the trends view's current
    /// `includeTransfers` through explicitly. Without that, a cell reached
    /// while "include transfers" is toggled on in Trends — a transfer-
    /// prefixed category row, for instance — would land on a Transactions
    /// screen that excludes transfers again, silently filtering out some of
    /// the very rows the cell just summed. Passing it through keeps the
    /// spec's round-trip guarantee ("its linked transactions sum exactly to
    /// the cell value") true in every toggle state, not just the default.
    public static func transactionFilter(
        for row: TrendRow,
        period: Period,
        accounts: [String],
        includeTransfers: Bool = false
    ) -> TransactionFilter {
        TransactionFilter(
            dateFrom: period.start,
            dateTo: period.end,
            categories: row.categories,
            accounts: accounts,
            includeTransfers: includeTransfers
        )
    }
}
