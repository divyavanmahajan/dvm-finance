import SwiftUI
import DVMFinanceKit

/// Placeholder for the Phase E import screen — statement file import,
/// snapshot import/export, and audit history lists
/// (`ios/docs/spec.md` "UI" §3). Kept intentionally trivial in Phase A.
struct ImportView: View {
    @Environment(\.appDatabase) private var appDatabase

    var body: some View {
        NavigationStack {
            ContentUnavailableView(
                "Import",
                systemImage: "square.and.arrow.down",
                description: Text("Statement and snapshot import arrive in a later phase.")
            )
            .navigationTitle("Import")
        }
    }
}

#Preview {
    ImportView()
}
