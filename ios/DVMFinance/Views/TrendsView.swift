import SwiftUI
import DVMFinanceKit

/// Placeholder for the Phase E trends matrix — month x top-level-category
/// rollup with tap-through to Transactions (`ios/docs/spec.md` "UI" §2).
/// Kept intentionally trivial in Phase A.
struct TrendsView: View {
    @Environment(\.appDatabase) private var appDatabase

    var body: some View {
        NavigationStack {
            ContentUnavailableView(
                "Trends",
                systemImage: "chart.bar",
                description: Text("The category trends matrix arrives in a later phase.")
            )
            .navigationTitle("Trends")
        }
    }
}

#Preview {
    TrendsView()
}
