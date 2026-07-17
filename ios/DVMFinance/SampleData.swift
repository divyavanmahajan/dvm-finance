#if DEBUG
import Foundation
import DVMFinanceKit
import GRDB

/// Deterministic demo data used **only** for App Store / marketing screenshots
/// and UI tests — never compiled into a Release (App Store) build because the
/// whole file is behind `#if DEBUG`.
///
/// It is invoked from `AppEnvironment` when the app is launched with the
/// `-UITestSeed` argument (see `DVMFinanceUITests/ScreenshotTests.swift`). It
/// wipes the transactions/budgets tables and inserts a small, tidy month of
/// spending across a handful of categories plus a couple of monthly and yearly
/// budgets, so the Transactions, Trends and Budgets tabs all render with
/// realistic content.
enum SampleData {
    /// One recurring monthly line item: category, description, day-of-month it
    /// posts, and amount (negative = spend, positive = income). Replicated
    /// across the last 12 months so the Trends grid is populated in every
    /// column, with a little deterministic variation per month.
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

    /// Wipe and repopulate the database with 12 months of the recurring dataset
    /// above, plus a few budgets so the Budgets tab is populated on both the
    /// Monthly and Yearly tabs.
    static func populate(into appDatabase: AppDatabase) throws {
        let cal = Calendar(identifier: .gregorian)
        let today = cal.startOfDay(for: Date())

        try appDatabase.dbWriter.write { db in
            try TransactionRecord.deleteAll(db)
            try BudgetRecord.deleteAll(db)

            var seq = 0
            for monthsAgo in 0..<12 {
                guard let monthStart = cal.date(byAdding: .month, value: -monthsAgo,
                                                to: cal.date(from: cal.dateComponents([.year, .month], from: today))!)
                else { continue }
                // Small deterministic wobble so months aren't identical.
                let wobble = 1.0 + Double((monthsAgo * 7) % 11 - 5) / 100.0
                for item in monthly {
                    // Skip future-dated days in the current month.
                    guard let date = cal.date(byAdding: .day, value: item.day - 1, to: monthStart),
                          date <= today else { continue }
                    let amount = item.category == "income" ? item.amount : item.amount * wobble
                    var record = TransactionRecord(
                        id: "sample-\(seq)",
                        accountNumber: "NL91ABNA0417164300",
                        transactiondate: date,
                        amount: Decimal(string: String(format: "%.2f", amount)) ?? Decimal(amount),
                        description: item.description,
                        category: item.category,
                        currency: "EUR"
                    )
                    try record.insert(db)
                    seq += 1
                }
            }

            // Monthly budgets for the current month.
            let (mStart, mEnd) = BudgetReport.periodDates(.month, reference: today)
            for (category, amount) in [("groceries", 250), ("dining", 150), ("transport", 120)] {
                var b = BudgetRecord(
                    category: category, amount: Decimal(amount), period: "month",
                    startDate: mStart, endDate: mEnd, notes: "Sample budget",
                    createdAt: today, updatedAt: today
                )
                try b.insert(db)
            }

            // Yearly budgets for the current calendar year.
            let (yStart, yEnd) = BudgetReport.periodDates(.year, reference: today)
            for (category, amount) in [("shopping", 1500), ("subscriptions", 360)] {
                var b = BudgetRecord(
                    category: category, amount: Decimal(amount), period: "year",
                    startDate: yStart, endDate: yEnd, notes: "Sample budget",
                    createdAt: today, updatedAt: today
                )
                try b.insert(db)
            }
        }
    }
}
#endif
