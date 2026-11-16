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
/// controls are `SampleDataSection`, which calls `AppQueries`.
struct HelpView: View {
    /// PyPI project for the desktop app. `uvx dvm-finance` runs it without a
    /// manual install.
    private let pypiURL = URL(string: "https://pypi.org/project/dvm-finance/")!

    var body: some View {
        NavigationStack {
            List {
                aboutSection
                desktopAppSection
                SampleDataSection(footer: "The sample data is one year of fictional transactions and five budgets. The app adds it next to your own data and does not change your data. Remove the sample data before you export a snapshot. The removal deletes only the sample data. The Import tab holds the same controls.")
                getStartedSection
                qrSyncSection
                qrTroubleshootingSection
                pushBackSection
                notesSection
            }
            .navigationTitle("Help")
        }
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
            StepRow(1, "In the desktop app, open the **Export** page. The **⋮** menu in the top bar holds it.")
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
            StepRow(2, "On your computer, start the desktop app.")
            StepRow(3, "Click the **QR icon** in the top bar of the desktop app. The **Export** page opens and shows a QR code.")
            StepRow(4, "Here, open the **Import** tab and tap **Sync from computer**.")
            StepRow(5, "Point the camera at the QR code. The app downloads the snapshot and imports it.")
            StepRow(6, "Review the import summary.")
        } header: {
            Label("Sync with a QR code", systemImage: "qrcode.viewfinder")
        } footer: {
            Text("The first time, allow access to the camera and to the local network. The QR code works for one download only and expires after 10 minutes.")
        }
    }

    // MARK: - QR code troubleshooting

    private var qrTroubleshootingSection: some View {
        Section {
            TroubleshootingRow("Make a new QR code. Click the **QR icon** on your computer again. Each QR code works for one download only and expires after 10 minutes.")
            TroubleshootingRow("Make sure that this device and your computer use the same Wi-Fi network. A guest network can stop the connection between devices.")
            TroubleshootingRow("Turn off a VPN on this device. A VPN can send the download away from your local network.")
            TroubleshootingRow("Make sure that the firewall of your computer lets DVM Finance accept connections.")
            TroubleshootingRow("Open the link of the QR code in Safari on this device. If Safari cannot open it either, the problem is the network, not the app.")
            TroubleshootingRow("If the app asks for Local Network access, open **Settings ▸ DVM Finance** and turn on **Local Network**.")
        } header: {
            Label("If the QR code sync fails", systemImage: "wrench.and.screwdriver")
        }
    }

    // MARK: - Push changes back (delta export)

    private var pushBackSection: some View {
        Section {
            StepRow(1, "Open the **Import** tab.")
            StepRow(2, "Under **Export changes since…**, pick the date you last synced. It defaults to your previous delta export.")
            StepRow(3, "Tap **Export delta snapshot**. This builds a small file with only the transactions you changed since that date.")
            StepRow(4, "Share the file back to your computer (AirDrop, Files, iCloud Drive, email).")
            StepRow(5, "In the desktop app, open the **Export** page and import that file to apply your mobile edits.")
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
                Text("You can also import raw bank statement files (MT940, ABN CSV, PayPal, Wise, SEB) directly from the Import tab.")
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

/// One troubleshooting step with a check-mark icon. The text supports
/// Markdown, as in `StepRow`.
private struct TroubleshootingRow: View {
    let text: LocalizedStringKey

    init(_ text: LocalizedStringKey) {
        self.text = text
    }

    var body: some View {
        Label {
            Text(text)
                .fixedSize(horizontal: false, vertical: true)
        } icon: {
            Image(systemName: "checkmark.circle").foregroundStyle(Theme.accent)
        }
    }
}

#Preview {
    HelpView()
}
