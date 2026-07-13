import SwiftUI
import DVMFinanceKit

/// Placeholder for the Phase E transactions list — searchable, grouped by
/// date, with a filter sheet and row detail (`ios/docs/spec.md` "UI" §1).
/// Kept intentionally trivial in Phase A.
struct TransactionsView: View {
    @Environment(\.appDatabase) private var appDatabase

    var body: some View {
        NavigationStack {
            ContentUnavailableView(
                "Transactions",
                systemImage: "list.bullet.rectangle",
                description: Text("The transactions list arrives in a later phase.")
            )
            .navigationTitle("Transactions")
        }
    }
}

#Preview {
    TransactionsView()
}
