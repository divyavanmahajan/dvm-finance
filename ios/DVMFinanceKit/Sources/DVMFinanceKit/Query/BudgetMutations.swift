import Foundation
import GRDB

/// Port of the budget CRUD endpoints in `src/abn_combined/api/budgets.py`
/// (`budget_create`, `budget_update`, `budget_delete`,
/// `budgets_create_top_level`).
///
/// Categories are normalized via `CoreNormalize.normalizeCategory`; a
/// (category, period) pair is unique — creating/updating into an existing
/// pair raises `BudgetError.duplicate`. `created_at`/`updated_at` are stamped
/// day-granular to match the `Date` columns in `models.py: Budget`.
public enum BudgetMutations {

    public enum BudgetError: Error, Equatable {
        case emptyCategory
        case invalidAmount
        /// A budget for this (category, period) pair already exists.
        case duplicate(category: String, period: String)
        case notFound(Int64)
    }

    /// Validated form input shared by create and update.
    public struct Input {
        public var category: String
        public var amount: Decimal
        public var period: BudgetReport.Period
        public var startDate: Date?
        public var endDate: Date?
        public var notes: String?

        public init(
            category: String,
            amount: Decimal,
            period: BudgetReport.Period,
            startDate: Date? = nil,
            endDate: Date? = nil,
            notes: String? = nil
        ) {
            self.category = category
            self.amount = amount
            self.period = period
            self.startDate = startDate
            self.endDate = endDate
            self.notes = notes
        }
    }

    /// Normalizes and validates raw form fields into an `Input`. Port of
    /// `api/budgets.py:_parse_budget_form` (period/amount are already typed
    /// here, so only category normalization and emptiness remain to check).
    public static func makeInput(
        category: String,
        amount: Decimal,
        period: BudgetReport.Period,
        startDate: Date? = nil,
        endDate: Date? = nil,
        notes: String? = nil
    ) throws -> Input {
        guard let cat = CoreNormalize.normalizeCategory(category), !cat.isEmpty else {
            throw BudgetError.emptyCategory
        }
        let trimmedNotes = notes?.trimmingCharacters(in: .whitespacesAndNewlines)
        return Input(
            category: cat,
            amount: amount,
            period: period,
            startDate: startDate,
            endDate: endDate,
            notes: (trimmedNotes?.isEmpty ?? true) ? nil : trimmedNotes
        )
    }

    /// Port of `api/budgets.py:budget_create`. Rejects a duplicate
    /// (category, period).
    @discardableResult
    public static func create(db: Database, input: Input) throws -> BudgetRecord {
        if try existsDuplicate(db, category: input.category, period: input.period, excluding: nil) {
            throw BudgetError.duplicate(category: input.category, period: input.period.rawValue)
        }
        let today = Date()
        var record = BudgetRecord(
            category: input.category,
            amount: input.amount,
            period: input.period.rawValue,
            startDate: input.startDate,
            endDate: input.endDate,
            notes: input.notes,
            createdAt: today,
            updatedAt: today
        )
        try record.insert(db)
        return record
    }

    /// Port of `api/budgets.py:budget_update`. Rejects a duplicate
    /// (category, period) on another budget; stamps `updated_at`.
    @discardableResult
    public static func update(db: Database, budgetId: Int64, input: Input) throws -> BudgetRecord {
        guard var record = try BudgetRecord.fetchOne(db, key: budgetId) else {
            throw BudgetError.notFound(budgetId)
        }
        if try existsDuplicate(db, category: input.category, period: input.period, excluding: budgetId) {
            throw BudgetError.duplicate(category: input.category, period: input.period.rawValue)
        }
        record.category = input.category
        record.amount = input.amount
        record.period = input.period.rawValue
        record.startDate = input.startDate
        record.endDate = input.endDate
        record.notes = input.notes
        record.updatedAt = Date()
        try record.update(db)
        return record
    }

    /// Port of `api/budgets.py:budget_delete`.
    public static func delete(db: Database, budgetId: Int64) throws {
        guard try BudgetRecord.deleteOne(db, key: budgetId) else {
            throw BudgetError.notFound(budgetId)
        }
    }

    /// Period-aware generalization of `api/budgets.py:budgets_create_top_level`.
    /// Creates a budget of `period` for every top-level category without one of
    /// that period, proposing an amount derived from the last-N-months average
    /// monthly spend:
    ///
    /// - `.month`: the raw monthly average, validity = the current month
    ///   window, notes "Auto-created from N-month average".
    /// - `.year`: the annualized amount (`12 ×` monthly average), validity =
    ///   the current calendar year (Jan 1 – Dec 31), notes
    ///   "Auto-created from N-month average (annualized)".
    /// - `.week`: the raw monthly average against the current week window
    ///   (supported for completeness; not surfaced as a primary tab).
    ///
    /// Categories with no recent spend (average <= 0) are skipped and existing
    /// budgets of `period` are never touched. Amounts are rounded to 2dp.
    /// Returns the categories actually created.
    @discardableResult
    public static func seedTopLevelBudgets(
        db: Database,
        period: BudgetReport.Period = .month,
        reference: Date = Date(),
        averageMonths: Int = BudgetReport.defaultAverageMonths
    ) throws -> [String] {
        let (start, end) = BudgetReport.periodDates(period, reference: reference)
        let today = Date()
        let annualized = period == .year
        var created: [String] = []
        for cat in try BudgetReport.distinctTopLevelCategories(db: db) {
            let existing = try BudgetRecord
                .filter(Column("category") == cat && Column("period") == period.rawValue)
                .fetchCount(db)
            if existing > 0 { continue }
            let avg = try BudgetReport.averageMonthlySpend(
                db: db, category: cat, months: averageMonths, reference: reference)
            if avg <= 0 { continue }
            let amount = annualized ? avg * 12 : avg
            let rounded = Decimal(string: String(format: "%.2f", amount)) ?? Decimal(amount)
            let notes = annualized
                ? "Auto-created from \(averageMonths)-month average (annualized)"
                : "Auto-created from \(averageMonths)-month average"
            var record = BudgetRecord(
                category: cat,
                amount: rounded,
                period: period.rawValue,
                startDate: start,
                endDate: end,
                notes: notes,
                createdAt: today,
                updatedAt: today
            )
            try record.insert(db)
            created.append(cat)
        }
        return created
    }

    /// Back-compat entry point: month-only seeding. Prefer the period-aware
    /// `seedTopLevelBudgets(db:period:reference:averageMonths:)`.
    @discardableResult
    public static func seedTopLevelMonthBudgets(
        db: Database,
        reference: Date = Date(),
        averageMonths: Int = BudgetReport.defaultAverageMonths
    ) throws -> [String] {
        try seedTopLevelBudgets(
            db: db, period: .month, reference: reference, averageMonths: averageMonths)
    }

    private static func existsDuplicate(
        _ db: Database,
        category: String,
        period: BudgetReport.Period,
        excluding budgetId: Int64?
    ) throws -> Bool {
        var request = BudgetRecord
            .filter(Column("category") == category && Column("period") == period.rawValue)
        if let budgetId {
            request = request.filter(Column("id") != budgetId)
        }
        return try request.fetchCount(db) > 0
    }
}
