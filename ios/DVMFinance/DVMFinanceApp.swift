import SwiftUI
import DVMFinanceKit

@main
struct DVMFinanceApp: App {
    @StateObject private var appEnvironment = AppEnvironment()

    var body: some Scene {
        WindowGroup {
            RootTabView()
                .environment(\.appDatabase, appEnvironment.database)
                .environment(\.appDataDirectory, appEnvironment.dataDirectory)
                .environment(\.appDatabaseURL, appEnvironment.databaseURL)
                .tint(Theme.accent)
        }
    }
}

/// Root tab bar: Transactions · Trends · Budgets · Import · Help. The app
/// target carries no business logic — see `ios/docs/spec.md` "Module layout":
/// "the app target contains no business logic — everything testable lives in
/// DVMFinanceKit".
struct RootTabView: View {
    var body: some View {
        TabView {
            TransactionsView()
                .tabItem { Label("Transactions", systemImage: "list.bullet") }
            TrendsView()
                .tabItem { Label("Trends", systemImage: "chart.bar") }
            BudgetsView()
                .tabItem { Label("Budgets", systemImage: "chart.pie") }
            ImportView()
                .tabItem { Label("Import", systemImage: "square.and.arrow.down") }
            HelpView()
                .tabItem { Label("Help", systemImage: "questionmark.circle") }
        }
    }
}
