import Foundation
import GRDB

/// A small set of fictional transactions and budgets. A new user loads it to
/// try the app before importing real data, and an App Store reviewer loads it
/// to see each screen with content.
///
/// The set holds one recurring month of spending and income, repeated over
/// the last 12 months, plus three monthly and two yearly budgets.
///
/// Rules of the set:
/// - The load adds rows and never deletes a row. The user's own data stays.
/// - Each sample transaction id starts with `idPrefix`. An imported row has a
///   content-derived hash id, and a hand-entered row has a UUID, so no real
///   row can start with this prefix.
/// - Each sample budget carries `budgetNote` in `notes`. The load skips a
///   sample budget when the user has a budget with the same category and
///   period, because the table holds one budget for each such pair.
/// - The removal deletes only the rows that these two marks identify.
/// - `SnapshotExporter` refuses an export while the set is present, so the
///   fictional rows never reach the desktop database.
public enum SampleDataset {

    /// The prefix of each sample transaction id.
    public static let idPrefix = "sample-"

    /// The `notes` value of each sample budget.
    public static let budgetNote = "Sample budget"

    /// The fictional account of each sample transaction.
    public static let accountNumber = "NL91ABNA0417164300"

    /// The numbers of rows that a load added or a removal deleted.
    public struct Counts: Equatable {
        public let transactions: Int
        public let budgets: Int
    }

    /// One recurring monthly line item: the day of the month, the category,
    /// the description, and the amount (negative = spend, positive = income).
    private struct Item {
        let day: Int
        let category: String
        let description: String
        let amount: Double
    }

    private static let monthly: [Item] = [
        Item(day: 25, category: "income", description: "Salary — Acme BV", amount: 3250.00),
        Item(day: 2, category: "groceries", description: "Albert Heijn", amount: -42.18),
        Item(day: 9, category: "groceries", description: "Jumbo Supermarkt", amount: -56.73),
        Item(day: 17, category: "groceries", description: "Marqt", amount: -47.32),
        Item(day: 4, category: "dining", description: "Cafe De Jaren", amount: -28.50),
        Item(day: 14, category: "dining", description: "Restaurant Bloem", amount: -68.00),
        Item(day: 21, category: "dining", description: "Thuisbezorgd", amount: -31.20),
        Item(day: 6, category: "transport", description: "NS Reizigers", amount: -19.40),
        Item(day: 19, category: "transport", description: "Shell Fuel", amount: -72.10),
        Item(day: 8, category: "utilities", description: "Vattenfall Energy", amount: -87.65),
        Item(day: 22, category: "utilities", description: "Ziggo Internet", amount: -49.00),
        Item(day: 12, category: "subscriptions", description: "Netflix", amount: -13.99),
        Item(day: 12, category: "subscriptions", description: "Spotify Premium", amount: -10.99),
        Item(day: 5, category: "entertainment", description: "Pathe Cinema", amount: -24.00),
        Item(day: 16, category: "shopping", description: "Bol.com Order", amount: -64.99),
        Item(day: 18, category: "health", description: "Apotheek", amount: -22.45),
    ]

    private static let monthlyBudgets: [(String, Int)] = [("groceries", 250), ("dining", 150), ("transport", 120)]
    private static let yearlyBudgets: [(String, Int)] = [("shopping", 1500), ("subscriptions", 360)]

    /// `true` when the database holds at least one sample transaction or one
    /// sample budget.
    public static func isLoaded(db: Database) throws -> Bool {
        try sampleTransactions().fetchCount(db) > 0 || sampleBudgets().fetchCount(db) > 0
    }

    /// `true` when the database holds no live transaction. A flagged
    /// hand-entered row does not count, because no list shows it.
    public static func isDatabaseEmpty(db: Database) throws -> Bool {
        try TransactionRecord.filter(Column("deleted_at") == nil).fetchCount(db) == 0
    }

    /// Adds the sample set. Each date falls in the 12 months up to `today`,
    /// and the load skips a day after `today`. When the set is already
    /// present, the load adds nothing and returns zero counts.
    ///
    /// `localCalendar` gives the calendar day of `today` for the user. The
    /// arithmetic then uses `DateMath.calendar` (UTC), because the database
    /// stores each date as midnight UTC. Arithmetic in the local time zone
    /// moves each date one day back east of UTC.
    @discardableResult
    public static func insert(
        db: Database,
        today: Date = Date(),
        localCalendar: Calendar = .current
    ) throws -> Counts {
        if try isLoaded(db: db) {
            return Counts(transactions: 0, budgets: 0)
        }
        let calendar = DateMath.calendar
        let parts = localCalendar.dateComponents([.year, .month, .day], from: today)
        let day = DateMath.date(parts.year!, parts.month!, parts.day!)
        let currentMonth = DateMath.date(parts.year!, parts.month!, 1)

        var sequence = 0
        for monthsAgo in 0..<12 {
            guard let monthStart = calendar.date(byAdding: .month, value: -monthsAgo, to: currentMonth) else {
                continue
            }
            // A small fixed variation, so that the months are not identical.
            let wobble = 1.0 + Double((monthsAgo * 7) % 11 - 5) / 100.0
            for item in monthly {
                guard let date = calendar.date(byAdding: .day, value: item.day - 1, to: monthStart),
                      date <= day else { continue }
                let amount = item.category == "income" ? item.amount : item.amount * wobble
                let record = TransactionRecord(
                    id: "\(idPrefix)\(sequence)",
                    accountNumber: accountNumber,
                    transactiondate: date,
                    amount: Decimal(string: String(format: "%.2f", amount)) ?? Decimal(amount),
                    description: item.description,
                    category: item.category,
                    currency: "EUR"
                )
                try record.insert(db)
                sequence += 1
            }
        }

        var budgets = 0
        let (monthStart, monthEnd) = BudgetReport.periodDates(.month, reference: day)
        for (category, amount) in monthlyBudgets where try !budgetExists(db, category, "month") {
            var budget = BudgetRecord(
                category: category, amount: Decimal(amount), period: "month",
                startDate: monthStart, endDate: monthEnd, notes: budgetNote,
                createdAt: day, updatedAt: day
            )
            try budget.insert(db)
            budgets += 1
        }
        let (yearStart, yearEnd) = BudgetReport.periodDates(.year, reference: day)
        for (category, amount) in yearlyBudgets where try !budgetExists(db, category, "year") {
            var budget = BudgetRecord(
                category: category, amount: Decimal(amount), period: "year",
                startDate: yearStart, endDate: yearEnd, notes: budgetNote,
                createdAt: day, updatedAt: day
            )
            try budget.insert(db)
            budgets += 1
        }
        return Counts(transactions: sequence, budgets: budgets)
    }

    /// Deletes each sample transaction and each sample budget. The removal
    /// does not touch another row.
    @discardableResult
    public static func remove(db: Database) throws -> Counts {
        let transactions = try sampleTransactions().deleteAll(db)
        let budgets = try sampleBudgets().deleteAll(db)
        return Counts(transactions: transactions, budgets: budgets)
    }

    private static func budgetExists(_ db: Database, _ category: String, _ period: String) throws -> Bool {
        try BudgetRecord
            .filter(Column("category") == category && Column("period") == period)
            .fetchCount(db) > 0
    }

    private static func sampleTransactions() -> QueryInterfaceRequest<TransactionRecord> {
        TransactionRecord.filter(Column("id").like("\(idPrefix)%"))
    }

    private static func sampleBudgets() -> QueryInterfaceRequest<BudgetRecord> {
        BudgetRecord.filter(Column("notes") == budgetNote)
    }
}
