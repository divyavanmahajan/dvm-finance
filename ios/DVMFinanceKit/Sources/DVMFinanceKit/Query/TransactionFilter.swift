import Foundation

/// Port of `core/filters.py: TransactionFilter` — the typed filter model.
///
/// The Python type is URL-round-trippable (Golden Principle 8: "filter state
/// lives in the URL query string"); iOS has no URL, so this port drops
/// `from_query_string`/`to_query_string`/`to_pairs`/`active_chips` and every
/// other serialization helper — see `ios/docs/spec.md` "Filters & trends":
/// "iOS state is the struct itself, passed through navigation". Every field
/// that shapes the SQL query (`TransactionQuery.swift`) or resolves a preset
/// date range is kept, byte-for-byte in meaning.
public struct TransactionFilter: Equatable, Hashable {
    /// Port of `core/filters.py: PRESETS`.
    public enum Preset: String, CaseIterable, Identifiable, Sendable, Codable, Hashable {
        case thisMonth = "this-month"
        case lastMonth = "last-month"
        case thisYear = "this-year"
        case lastYear = "last-year"

        public var id: String { rawValue }

        /// Display label — Python's `preset.replace("-", " ").title()`
        /// (`active_chips`), kept here since it's the obvious UI label and
        /// has no other home in a UI-free Kit.
        public var label: String {
            rawValue.split(separator: "-").map { $0.capitalized }.joined(separator: " ")
        }
    }

    /// Port of `core/filters.py: _SORTS` keys (the 10 sort keys + their
    /// (column, descending) mapping is ported in `TransactionQuery.swift`,
    /// which owns SQL concerns; this enum is just the typed key).
    public enum Sort: String, CaseIterable, Identifiable, Sendable, Codable, Hashable {
        case dateDesc = "date_desc"
        case dateAsc = "date_asc"
        case descriptionDesc = "description_desc"
        case descriptionAsc = "description_asc"
        case amountDesc = "amount_desc"
        case amountAsc = "amount_asc"
        case categoryDesc = "category_desc"
        case categoryAsc = "category_asc"
        case tagsDesc = "tags_desc"
        case tagsAsc = "tags_asc"

        public var id: String { rawValue }
    }

    /// Port of `core/filters.py: UNCATEGORIZED` — the special `categories`/
    /// `exclude_categories` sentinel value meaning "no effective category".
    public static let uncategorized = "uncategorized"

    /// Port of `core/filters.py: PAGE_SIZE`.
    public static let pageSize = 50

    /// Port of `core/filters.py: DEFAULT_SORT`.
    public static let defaultSort: Sort = .dateDesc

    public var q: String?
    public var dateFrom: Date?
    public var dateTo: Date?
    public var preset: Preset?
    public var categories: [String]
    public var excludeCategories: [String]
    public var tags: [String]
    public var accounts: [String]
    public var amountMin: Double?
    public var amountMax: Double?
    public var ruleId: Int64?
    public var sourceFile: String?
    public var includeTransfers: Bool
    public var sort: Sort
    public var page: Int

    public init(
        q: String? = nil,
        dateFrom: Date? = nil,
        dateTo: Date? = nil,
        preset: Preset? = nil,
        categories: [String] = [],
        excludeCategories: [String] = [],
        tags: [String] = [],
        accounts: [String] = [],
        amountMin: Double? = nil,
        amountMax: Double? = nil,
        ruleId: Int64? = nil,
        sourceFile: String? = nil,
        includeTransfers: Bool = false,
        sort: Sort = TransactionFilter.defaultSort,
        page: Int = 1
    ) {
        self.q = q
        self.dateFrom = dateFrom
        self.dateTo = dateTo
        self.preset = preset
        self.categories = categories
        self.excludeCategories = excludeCategories
        self.tags = tags
        self.accounts = accounts
        self.amountMin = amountMin
        self.amountMax = amountMax
        self.ruleId = ruleId
        self.sourceFile = sourceFile
        self.includeTransfers = includeTransfers
        self.sort = sort
        self.page = max(1, page)
    }

    // MARK: - Preset resolution

    /// Port of `core/filters.py:resolve_preset_range`. Inclusive `(from,
    /// to)`.
    public static func resolvePresetRange(_ preset: Preset, today: Date) -> (from: Date, to: Date) {
        let (year, month, _) = DateMath.components(today)
        switch preset {
        case .thisMonth:
            return (DateMath.date(year, month, 1), DateMath.monthEnd(year: year, month: month))
        case .lastMonth:
            let (y, m) = month > 1 ? (year, month - 1) : (year - 1, 12)
            return (DateMath.date(y, m, 1), DateMath.monthEnd(year: y, month: m))
        case .thisYear:
            return (DateMath.date(year, 1, 1), DateMath.date(year, 12, 31))
        case .lastYear:
            return (DateMath.date(year - 1, 1, 1), DateMath.date(year - 1, 12, 31))
        }
    }

    /// Port of `core/filters.py: TransactionFilter.effective_dates` — the
    /// `(from, to)` range, resolving a preset if one is set.
    public func effectiveDates(today: Date = Date()) -> (from: Date?, to: Date?) {
        if let preset {
            let range = TransactionFilter.resolvePresetRange(preset, today: today)
            return (range.from, range.to)
        }
        return (dateFrom, dateTo)
    }
}
