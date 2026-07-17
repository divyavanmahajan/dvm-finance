import Foundation
import GRDB

/// Port of `core/filters.py: build_query` / `apply_sort` / `paginate` as raw
/// SQL (via GRDB `SQLRequest`/`fetchAll(_:sql:arguments:)`) against the
/// `transactions` table, plus the filter-UI helper queries
/// (`distinctEffectiveCategories`/`distinctAccounts`/`distinctSourceFiles`).
///
/// Raw SQL (rather than GRDB's query-interface `QueryInterfaceRequest`) is
/// used deliberately: the effective-category/tags expressions
/// (`COALESCE(NULLIF(...), ...)`) and the subtree/transfer-exclusion
/// predicates read far closer to their Python `sqlalchemy` originals as SQL
/// text than as a chain of `Column(...).collating(...)` calls, which keeps
/// the "port, don't rewrite" review easy — see `ios/docs/plan.md` "Working
/// agreements for subagents".
public enum TransactionQuery {

    /// Port of `core/filters.py: Page` (dataclass + its four computed
    /// properties).
    public struct Page: Equatable {
        public var items: [TransactionRecord]
        public var total: Int
        public var page: Int
        public var pageSize: Int

        public init(items: [TransactionRecord], total: Int, page: Int, pageSize: Int) {
            self.items = items
            self.total = total
            self.page = page
            self.pageSize = pageSize
        }

        public var pages: Int {
            total == 0 ? 1 : (total + pageSize - 1) / pageSize
        }

        public var hasPrev: Bool { page > 1 }
        public var hasNext: Bool { page < pages }

        public var startIndex: Int {
            total == 0 ? 0 : (page - 1) * pageSize + 1
        }

        public var endIndex: Int {
            min(page * pageSize, total)
        }
    }

    // MARK: - Effective-value SQL expressions

    /// Port of `core/filters.py:_effective_category_expr` — used by every
    /// filtering predicate (search excluded: `q` matches raw `description`/
    /// `description_structured`, not the effective category).
    static let effectiveCategorySQL = "COALESCE(NULLIF(manual_category, ''), category)"

    /// Port of `core/filters.py:_effective_tags_expr`.
    static let effectiveTagsSQL = "COALESCE(NULLIF(manual_tags, ''), tags)"

    /// The `_SORTS` category/tags expressions use a plain `coalesce` with
    /// **no** `nullif` — a documented desktop quirk (see `ios/docs/spec.md`
    /// "Filters & trends": "the sort coalesce does NOT use NULLIF") kept
    /// intentionally distinct from `effectiveCategorySQL`/`effectiveTagsSQL`
    /// above, which filtering uses.
    static let sortCategorySQL = "COALESCE(manual_category, category)"
    static let sortTagsSQL = "COALESCE(manual_tags, tags)"

    // MARK: - WHERE clause (port of build_query)

    /// Builds the `WHERE` predicate (no leading `WHERE` keyword) and its
    /// positional `?` arguments for `filter`. Port of
    /// `core/filters.py:build_query`.
    static func whereClause(
        _ filter: TransactionFilter,
        today: Date
    ) -> (sql: String, arguments: [(any DatabaseValueConvertible)?]) {
        var conditions: [String] = []
        var arguments: [(any DatabaseValueConvertible)?] = []

        if let q = filter.q, !q.isEmpty {
            let like = "%\(q)%"
            conditions.append("(description LIKE ? OR description_structured LIKE ?)")
            arguments.append(like)
            arguments.append(like)
        }

        let (lo, hi) = filter.effectiveDates(today: today)
        if let lo {
            conditions.append("transactiondate >= ?")
            arguments.append(DatabaseDateFormat.dateOnly.string(from: lo))
        }
        if let hi {
            conditions.append("transactiondate <= ?")
            arguments.append(DatabaseDateFormat.dateOnly.string(from: hi))
        }

        // Exclude transfers by default (build_query lines 384-389). A
        // CONTAINS match (not CoreNormalize.isTransferCategory's prefix
        // match) — see ios/docs/spec.md "TRANSFER EXCLUSION" and
        // CoreNormalize.isTransferCategory's doc comment on the two-variant
        // desktop quirk.
        if !filter.includeTransfers {
            conditions.append(
                "(\(effectiveCategorySQL) IS NULL OR \(effectiveCategorySQL) = '' "
                    + "OR \(effectiveCategorySQL) NOT LIKE '%transfer%')"
            )
        }

        if !filter.categories.isEmpty {
            let parts = filter.categories.map(categoryCondition)
            conditions.append("(" + parts.map(\.sql).joined(separator: " OR ") + ")")
            arguments.append(contentsOf: parts.flatMap(\.arguments))
        }

        // Port of build_query lines 404-412 exactly: excluding a real
        // category keeps uncategorized rows (NOT LIKE is NULL for them, so
        // they must be kept explicitly); excluding "uncategorized" itself is
        // a plain negation.
        for cat in filter.excludeCategories {
            let cond = categoryCondition(cat)
            if cat == TransactionFilter.uncategorized {
                conditions.append("NOT \(cond.sql)")
            } else {
                conditions.append(
                    "(\(effectiveCategorySQL) IS NULL OR \(effectiveCategorySQL) = '' OR NOT \(cond.sql))"
                )
            }
            arguments.append(contentsOf: cond.arguments)
        }

        if !filter.tags.isEmpty {
            let parts = filter.tags.map { _ in "(\(effectiveTagsSQL) LIKE ?)" }
            conditions.append("(" + parts.joined(separator: " OR ") + ")")
            for tag in filter.tags { arguments.append("%\(tag)%") }
        }

        if !filter.accounts.isEmpty {
            let placeholders = filter.accounts.map { _ in "?" }.joined(separator: ", ")
            conditions.append("accountNumber IN (\(placeholders))")
            arguments.append(contentsOf: filter.accounts.map { $0 as (any DatabaseValueConvertible)? })
        }

        // amount stored as decimal-string TEXT (Decimal+DatabaseValueConvertible.swift);
        // CAST to REAL before ABS()/comparison, matching the SUM convention
        // TrendsBuilder uses for the same column.
        if filter.amountMin != nil || filter.amountMax != nil {
            let absExpr = "ABS(CAST(amount AS REAL))"
            if let mn = filter.amountMin, let mx = filter.amountMax {
                conditions.append("(\(absExpr) >= ? AND \(absExpr) <= ?)")
                arguments.append(mn)
                arguments.append(mx)
            } else if let mn = filter.amountMin {
                conditions.append("\(absExpr) >= ?")
                arguments.append(mn)
            } else if let mx = filter.amountMax {
                conditions.append("\(absExpr) <= ?")
                arguments.append(mx)
            }
        }

        if let ruleId = filter.ruleId {
            conditions.append("categorization_source = ?")
            arguments.append(String(ruleId))
        }

        if let sourceFile = filter.sourceFile, !sourceFile.isEmpty {
            conditions.append("source_file = ?")
            arguments.append(sourceFile)
        }

        return (conditions.isEmpty ? "1" : conditions.joined(separator: " AND "), arguments)
    }

    /// Port of `core/filters.py:_category_cond` — matches a category exactly
    /// or any hierarchical child (hyphen-separated subtree). Internal (not
    /// `private`) so `TrendsBuilder`'s own WHERE-clause builder can share it
    /// — both need byte-identical subtree-match semantics.
    static func categoryCondition(_ cat: String) -> (sql: String, arguments: [(any DatabaseValueConvertible)?]) {
        if cat == TransactionFilter.uncategorized {
            return ("(\(effectiveCategorySQL) IS NULL OR \(effectiveCategorySQL) = '')", [])
        }
        let lowered = cat.lowercased()
        let sql = "(LOWER(\(effectiveCategorySQL)) = ? OR LOWER(\(effectiveCategorySQL)) LIKE ?)"
        return (sql, [lowered, "\(lowered)\(CoreNormalize.categorySeparator)%"])
    }

    // MARK: - ORDER BY (port of apply_sort)

    /// (SQL expression, descending) per sort key — port of
    /// `core/filters.py: _SORTS`. Amount is `CAST(... AS REAL)`, a necessary
    /// deviation from Python's native numeric column: this schema stores
    /// `amount` as decimal-string TEXT (see `Decimal+DatabaseValueConvertible.swift`),
    /// which sorts lexicographically (wrong for negative/width-varying
    /// values) without the cast.
    static func sortExpression(_ sort: TransactionFilter.Sort) -> (column: String, descending: Bool) {
        switch sort {
        case .dateDesc: return ("transactiondate", true)
        case .dateAsc: return ("transactiondate", false)
        case .descriptionDesc: return ("description", true)
        case .descriptionAsc: return ("description", false)
        case .amountDesc: return ("CAST(amount AS REAL)", true)
        case .amountAsc: return ("CAST(amount AS REAL)", false)
        case .categoryDesc: return (sortCategorySQL, true)
        case .categoryAsc: return (sortCategorySQL, false)
        case .tagsDesc: return (sortTagsSQL, true)
        case .tagsAsc: return (sortTagsSQL, false)
        }
    }

    /// Port of `core/filters.py:apply_sort` — always orders by `id` in the
    /// same direction as the primary sort, as a tiebreaker.
    static func orderBySQL(_ sort: TransactionFilter.Sort) -> String {
        let (column, descending) = sortExpression(sort)
        let direction = descending ? "DESC" : "ASC"
        return "\(column) \(direction), id \(direction)"
    }

    // MARK: - paginate

    /// Port of `core/filters.py:paginate`.
    public static func paginate(
        db: Database,
        filter: TransactionFilter,
        today: Date = Date(),
        pageSize: Int = TransactionFilter.pageSize
    ) throws -> Page {
        let (whereSQL, whereArguments) = whereClause(filter, today: today)

        let total = try Int.fetchOne(
            db,
            sql: "SELECT COUNT(*) FROM transactions WHERE \(whereSQL)",
            arguments: StatementArguments(whereArguments)
        ) ?? 0

        let maxPage = total > 0 ? max(1, (total + pageSize - 1) / pageSize) : 1
        let page = min(max(1, filter.page), maxPage)

        let orderSQL = orderBySQL(filter.sort)
        let offset = (page - 1) * pageSize

        var itemArguments = whereArguments
        itemArguments.append(pageSize)
        itemArguments.append(offset)

        let items = try TransactionRecord.fetchAll(
            db,
            sql: "SELECT * FROM transactions WHERE \(whereSQL) ORDER BY \(orderSQL) LIMIT ? OFFSET ?",
            arguments: StatementArguments(itemArguments)
        )

        return Page(items: items, total: total, page: page, pageSize: pageSize)
    }

    /// Convenience: the unpaginated, unsorted result count only — used by UI
    /// summary headers that don't need the row page. Not a direct Python
    /// port (no equivalent standalone helper in `filters.py`), but built
    /// from the same `whereClause`, so it always agrees with `paginate`'s
    /// `total`.
    public static func count(db: Database, filter: TransactionFilter, today: Date = Date()) throws -> Int {
        let (whereSQL, arguments) = whereClause(filter, today: today)
        return try Int.fetchOne(
            db,
            sql: "SELECT COUNT(*) FROM transactions WHERE \(whereSQL)",
            arguments: StatementArguments(arguments)
        ) ?? 0
    }

    /// Convenience: `SUM(amount)` over the filtered set, for a list header's
    /// "N transactions · sum" summary (`ios/docs/spec.md` "UI" §1). Sums via
    /// SQL (`CAST(amount AS REAL)`), not by decoding every row, per
    /// `ios/docs/plan.md` "Phase E" constraints. Not a direct Python port
    /// (desktop's transaction list doesn't show a sum), so no observable
    /// behavior is being reproduced here beyond "sum of the same filtered
    /// set `paginate` would return".
    public static func sum(db: Database, filter: TransactionFilter, today: Date = Date()) throws -> Double {
        let (whereSQL, arguments) = whereClause(filter, today: today)
        return try Double.fetchOne(
            db,
            sql: "SELECT COALESCE(SUM(CAST(amount AS REAL)), 0) FROM transactions WHERE \(whereSQL)",
            arguments: StatementArguments(arguments)
        ) ?? 0
    }

    // MARK: - Filter-UI helpers

    /// Distinct effective categories present in the data, for the filter
    /// sheet's category pickers. Sorted case-insensitively. Never includes
    /// `nil`/`""` (the "Uncategorized" entry is a UI-added sentinel, not a
    /// real stored value — see `TransactionFilter.uncategorized`).
    public static func distinctEffectiveCategories(db: Database) throws -> [String] {
        try String.fetchAll(
            db,
            sql: """
                SELECT DISTINCT \(effectiveCategorySQL) AS cat FROM transactions
                WHERE \(effectiveCategorySQL) IS NOT NULL AND \(effectiveCategorySQL) != ''
                ORDER BY cat COLLATE NOCASE
                """
        )
    }

    /// Distinct account numbers present in the data, for the filter sheet's
    /// account picker.
    public static func distinctAccounts(db: Database) throws -> [String] {
        try String.fetchAll(
            db,
            sql: "SELECT DISTINCT accountNumber FROM transactions ORDER BY accountNumber"
        )
    }

    /// Distinct non-empty `source_file` values present in the data.
    public static func distinctSourceFiles(db: Database) throws -> [String] {
        try String.fetchAll(
            db,
            sql: """
                SELECT DISTINCT source_file FROM transactions
                WHERE source_file IS NOT NULL AND source_file != ''
                ORDER BY source_file
                """
        )
    }

    /// Distinct individual tags present in the data, for the filter sheet's
    /// tag autocomplete. Tags are stored as a comma-separated string per row
    /// (effective = `COALESCE(NULLIF(manual_tags, ''), tags)`); this fetches
    /// every effective-tags string, splits on commas, trims, de-duplicates
    /// case-insensitively (keeping first-seen casing), and returns them sorted
    /// case-insensitively. Done in Swift rather than SQL because SQLite has no
    /// built-in string-split.
    public static func distinctEffectiveTags(db: Database) throws -> [String] {
        let rows = try String.fetchAll(
            db,
            sql: """
                SELECT DISTINCT \(effectiveTagsSQL) AS t FROM transactions
                WHERE \(effectiveTagsSQL) IS NOT NULL AND \(effectiveTagsSQL) != ''
                """
        )
        var seen: Set<String> = []
        var result: [String] = []
        for row in rows {
            for piece in row.split(separator: ",") {
                let tag = piece.trimmingCharacters(in: .whitespaces)
                guard !tag.isEmpty else { continue }
                let key = tag.lowercased()
                if seen.insert(key).inserted {
                    result.append(tag)
                }
            }
        }
        return result.sorted { $0.lowercased() < $1.lowercased() }
    }

    // MARK: - Display helpers (port of core/filters.py's free functions)

    /// Port of `core/filters.py:effective_category` — a **truthy** check
    /// (`manual_category or category`), so an empty-string `manual_category`
    /// also falls through to `category`. Deliberately distinct from
    /// `TransactionRecord.effectiveCategory`'s plain `manualCategory ??
    /// category` (Phase A, nil-only fallback) — kept that way rather than
    /// changing the already-established computed property, matching
    /// `SnapshotImporter.effectiveValue`'s same documented convention. Views
    /// displaying a row's category should call this, not the stored
    /// property, for exact parity with desktop.
    public static func effectiveCategory(_ record: TransactionRecord) -> String? {
        if let manual = record.manualCategory, !manual.isEmpty { return manual }
        return record.category
    }

    /// Port of `core/filters.py:effective_tags`.
    public static func effectiveTags(_ record: TransactionRecord) -> String? {
        if let manual = record.manualTags, !manual.isEmpty { return manual }
        return record.tags
    }

    /// Port of `core/filters.py:is_manual`.
    public static func isManual(_ record: TransactionRecord) -> Bool {
        record.categorizationSource == Categorizer.manualSource || !(record.manualCategory ?? "").isEmpty
    }

    /// Count of `ids` whose raw (not effective) `category` is non-`NULL` —
    /// used by the Import flow's post-import summary ("N categorized / M
    /// uncategorized"). Not a Python port; a small convenience that keeps
    /// this one raw-SQL call inside the Kit alongside every other query in
    /// this file.
    public static func categorizedCount(db: Database, ids: [String]) throws -> Int {
        guard !ids.isEmpty else { return 0 }
        let placeholders = ids.map { _ in "?" }.joined(separator: ", ")
        return try Int.fetchOne(
            db,
            sql: "SELECT COUNT(*) FROM transactions WHERE id IN (\(placeholders)) AND category IS NOT NULL",
            arguments: StatementArguments(ids.map { $0 as (any DatabaseValueConvertible)? })
        ) ?? 0
    }
}
