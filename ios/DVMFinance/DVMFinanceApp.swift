import SwiftUI
import DVMFinanceKit

@main
struct DVMFinanceApp: App {
    @StateObject private var appEnvironment = AppEnvironment()

    var body: some Scene {
        WindowGroup {
            RootTabView()
                .environment(\.appDatabase, appEnvironment.database)
        }
    }
}

/// Tab bar scaffolding per `ios/docs/spec.md` "UI": Transactions · Trends ·
/// Import. Phase E replaces the three placeholder screens with the real
/// implementations; this target otherwise carries no business logic — see
/// spec.md "Module layout": "the app target contains no business logic —
/// everything testable lives in DVMFinanceKit".
struct RootTabView: View {
    var body: some View {
        TabView {
            TransactionsView()
                .tabItem { Label("Transactions", systemImage: "list.bullet") }
            TrendsView()
                .tabItem { Label("Trends", systemImage: "chart.bar") }
            ImportView()
                .tabItem { Label("Import", systemImage: "square.and.arrow.down") }
        }
    }
}
