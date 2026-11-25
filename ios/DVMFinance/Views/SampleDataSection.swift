import SwiftUI
import DVMFinanceKit

/// The list section that loads and removes the sample data. The help tab and
/// the import tab both show it (`ios-help` "Sample data controls").
///
/// The section shows "Load sample data" while the sample set is absent, and
/// "Remove sample data" while it is present. It reads the state again in
/// `.task` and in `.onAppear`, so a load in another tab shows when the user
/// comes back. A change of `refreshID` also makes it read the state again,
/// for example after "Delete all data" on the same screen.
///
/// No business logic: the section calls `AppQueries` only.
struct SampleDataSection: View {
    @Environment(\.appDatabase) private var appDatabase

    /// The footer text. Each tab gives its own text.
    let footer: String
    /// A value that the parent changes to make the section read its state
    /// again.
    var refreshID: Int = 0

    @State private var isSampleLoaded = false
    @State private var isWorking = false
    @State private var message: String?

    var body: some View {
        Section {
            Group {
                if isSampleLoaded {
                    Button(role: .destructive) {
                        Task { await removeSampleData() }
                    } label: {
                        Label("Remove sample data", systemImage: "trash")
                    }
                    .disabled(isWorking)
                } else {
                    Button {
                        Task { await loadSampleData() }
                    } label: {
                        Label("Load sample data", systemImage: "wand.and.stars")
                    }
                    .disabled(isWorking)
                }
                if let message {
                    Text(message)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .task(id: refreshID) { await refreshState() }
            .onChange(of: refreshID) { message = nil }
            .onAppear { Task { await refreshState() } }
        } header: {
            Label("Try the app with sample data", systemImage: "wand.and.stars")
        } footer: {
            Text(footer)
        }
    }

    private func refreshState() async {
        guard let appDatabase else { return }
        isSampleLoaded = (try? await AppQueries.sampleDataLoaded(appDatabase: appDatabase)) ?? false
    }

    private func loadSampleData() async {
        guard let appDatabase else { return }
        isWorking = true
        defer { isWorking = false }
        do {
            let counts = try await AppQueries.loadSampleData(appDatabase: appDatabase)
            message = "Loaded \(counts.transactions) transactions and \(counts.budgets) budgets."
        } catch {
            message = "Couldn't load the sample data: \(error.localizedDescription)"
        }
        await refreshState()
    }

    private func removeSampleData() async {
        guard let appDatabase else { return }
        isWorking = true
        defer { isWorking = false }
        do {
            let counts = try await AppQueries.removeSampleData(appDatabase: appDatabase)
            message = "Removed \(counts.transactions) transactions and \(counts.budgets) budgets."
        } catch {
            message = "Couldn't remove the sample data: \(error.localizedDescription)"
        }
        await refreshState()
    }
}

#Preview {
    List {
        SampleDataSection(footer: "Remove the sample data before you export a snapshot.")
    }
}
