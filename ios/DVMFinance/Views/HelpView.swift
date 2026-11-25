import SwiftUI
import DVMFinanceKit

/// The Help tab: onboarding for the companion-app model. Explains that this
/// app pairs with the DVM Finance desktop (Python) app, links to where to get
/// it, and walks through the two sync directions — importing a snapshot to get
/// started, and exporting a delta snapshot to push mobile edits back. It also
/// tells the user how to sync with the QR code, and holds the controls that
/// load and remove the sample data.
///
/// No business logic (see `ios/docs/plan.md` "Phase E"): the sample-data
/// controls call `AppQueries`.
struct HelpView: View {
    @Environment(\.appDatabase) private var appDatabase

    @State private var isSampleLoaded = false
    @State private var isWorking = false
    @State private var sampleMessage: String?

    /// PyPI project for the desktop app. `uvx dvm-finance` runs it without a
    /// manual install.
    private let pypiURL = URL(string: "https://pypi.org/project/dvm-finance/")!

    var body: some View {
        NavigationStack {
            List {
                aboutSection
                desktopAppSection
                sampleDataSection
                getStartedSection
                qrSyncSection
                pushBackSection
                notesSection
            }
            .navigationTitle("Help")
            .task { await refreshSampleState() }
        }
    }

    // MARK: - Sample data

    private var sampleDataSection: some View {
        Section {
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
            if let sampleMessage {
                Text(sampleMessage)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        } header: {
            Label("Try the app with sample data", systemImage: "wand.and.stars")
        } footer: {
            Text("The sample data is one year of fictional transactions and five budgets. The app adds it next to your own data and does not change your data. Remove the sample data before you export a snapshot. The removal deletes only the sample data.")
        }
    }

    private func refreshSampleState() async {
        guard let appDatabase else { return }
        isSampleLoaded = (try? await AppQueries.sampleDataLoaded(appDatabase: appDatabase)) ?? false
    }

    private func loadSampleData() async {
        guard let appDatabase else { return }
        isWorking = true
        defer { isWorking = false }
        do {
            let counts = try await AppQueries.loadSampleData(appDatabase: appDatabase)
            sampleMessage = "Loaded \(counts.transactions) transactions and \(counts.budgets) budgets."
        } catch {
            sampleMessage = "Couldn't load the sample data: \(error.localizedDescription)"
        }
        await refreshSampleState()
    }

    private func removeSampleData() async {
        guard let appDatabase else { return }
        isWorking = true
        defer { isWorking = false }
        do {
            let counts = try await AppQueries.removeSampleData(appDatabase: appDatabase)
            sampleMessage = "Removed \(counts.transactions) transactions and \(counts.budgets) budgets."
        } catch {
            sampleMessage = "Couldn't remove the sample data: \(error.localizedDescription)"
        }
        await refreshSampleState()
    }

    // MARK: - About

    private var aboutSection: some View {
        Section {
            VStack(alignment: .leading, spacing: 10) {
                Label("A companion app", systemImage: "iphone.and.arrow.forward")
                    .font(.headline)
                    .foregroundStyle(Theme.accent)
                Text("DVM Finance for iPhone and iPad is a companion to the DVM Finance desktop app.")
                Text("The desktop app is the home base: import bank statements in bulk, manage your categorization rules, and keep the main database. This app lets you review transactions, trends and budgets on the go, make quick edits, and sync those changes back.")
                    .foregroundStyle(.secondary)
            }
            .padding(.vertical, 4)
        }
    }

    // MARK: - Get the desktop app

    private var desktopAppSection: some View {
        Section("Get the desktop app") {
            Text("The desktop app is free and open source, published on PyPI as **dvm-finance**.")
            VStack(alignment: .leading, spacing: 6) {
                Text("Run it without installing:")
                    .foregroundStyle(.secondary)
                Text("uvx dvm-finance")
                    .font(.system(.callout, design: .monospaced))
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 8).fill(Color.secondary.opacity(0.12)))
                Text("…or install it with pip:")
                    .foregroundStyle(.secondary)
                Text("pip install dvm-finance")
                    .font(.system(.callout, design: .monospaced))
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 8).fill(Color.secondary.opacity(0.12)))
            }
            .padding(.vertical, 2)
            Link(destination: pypiURL) {
                Label("View on PyPI", systemImage: "arrow.up.right.square")
            }
        }
    }

    // MARK: - Getting started (import)

    private var getStartedSection: some View {
        Section {
            StepRow(1, "In the desktop app, open the **Snapshots** page.")
            StepRow(2, "Click **Export snapshot**. This downloads a compressed snapshot file (ending in `.json.gz`).")
            StepRow(3, "Get the file onto your device — AirDrop, iCloud Drive, Files, or email all work.")
            StepRow(4, "Here, open the **Import** tab and tap **Import snapshot**, then choose the file.")
            StepRow(5, "Review the import summary. Your transactions, categories, rules and budgets are now on your device.")
        } header: {
            Label("Get started: import a snapshot", systemImage: "square.and.arrow.down")
        } footer: {
            Text("A snapshot is a full copy of your desktop data. Importing merges it in — incoming values win, and every import is recorded in Import ▸ History.")
        }
    }

    // MARK: - Sync with the QR code

    private var qrSyncSection: some View {
        Section {
            StepRow(1, "Connect your computer and this device to the same Wi-Fi network.")
            StepRow(2, "On your computer, start the desktop app and open the **Snapshots** page.")
            StepRow(3, "Click **Share to phone**. A QR code appears on the page.")
            StepRow(4, "Here, open the **Import** tab and tap **Sync from computer**.")
            StepRow(5, "Point the camera at the QR code. The app downloads the snapshot and imports it.")
            StepRow(6, "Review the import summary.")
        } header: {
            Label("Sync with a QR code", systemImage: "qrcode.viewfinder")
        } footer: {
            Text("The first time, allow access to the camera and to the local network. The QR code works for one download only and expires after 10 minutes. If the app tells you that the link expired, click **Share to phone** again to get a new QR code.")
        }
    }

    // MARK: - Push changes back (delta export)

    private var pushBackSection: some View {
        Section {
            StepRow(1, "Open the **Import** tab.")
            StepRow(2, "Under **Export changes since…**, pick the date you last synced. It defaults to your previous delta export.")
            StepRow(3, "Tap **Export delta snapshot**. This builds a small file with only the transactions you changed since that date.")
            StepRow(4, "Share the file back to your computer (AirDrop, Files, iCloud Drive, email).")
            StepRow(5, "In the desktop app's **Snapshots** page, import that file to apply your mobile edits.")
        } header: {
            Label("Push mobile changes back", systemImage: "square.and.arrow.up.badge.clock")
        } footer: {
            Text("A delta snapshot carries only what changed, so it stays small and won't overwrite unrelated desktop data. Use a full Export snapshot instead if you want to hand off everything.")
        }
    }

    // MARK: - Notes

    private var notesSection: some View {
        Section("Good to know") {
            Label {
                Text("You can also import raw bank statement files (MT940, ABN CSV, PayPal, Wise, SEB) directly from the Import tab. An SEB file needs the ECB exchange rates, so the device must have network access. Without the rates, the import stores no transaction.")
            } icon: {
                Image(systemName: "doc.badge.plus").foregroundStyle(Theme.accent)
            }
            Label {
                Text("Your data stays on your device. It syncs only through snapshots: a file that you move yourself, or a QR code download over your own Wi-Fi network. There's no account and no cloud service.")
            } icon: {
                Image(systemName: "lock.shield").foregroundStyle(Theme.accent)
            }
        }
    }
}

/// A numbered step with a teal circle badge, used by the two walkthroughs.
/// The text supports Markdown so key UI labels can be bolded inline.
private struct StepRow: View {
    let number: Int
    let text: LocalizedStringKey

    init(_ number: Int, _ text: LocalizedStringKey) {
        self.number = number
        self.text = text
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Text("\(number)")
                .font(.footnote.weight(.bold))
                .foregroundStyle(.white)
                .frame(width: 24, height: 24)
                .background(Circle().fill(Theme.accent))
            Text(text)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.vertical, 2)
    }
}

#Preview {
    HelpView()
}
