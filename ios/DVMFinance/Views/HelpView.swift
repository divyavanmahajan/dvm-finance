import SwiftUI

/// The Help tab: onboarding for the companion-app model. Explains that this
/// app pairs with the DVM Finance desktop (Python) app, links to where to get
/// it, and walks through the two sync directions — importing a snapshot to get
/// started, and exporting a delta snapshot to push mobile edits back.
///
/// View-only content; no business logic (see `ios/docs/plan.md` "Phase E").
struct HelpView: View {
    /// PyPI project for the desktop app. `uvx dvm-finance` runs it without a
    /// manual install.
    private let pypiURL = URL(string: "https://pypi.org/project/dvm-finance/")!

    var body: some View {
        NavigationStack {
            List {
                aboutSection
                desktopAppSection
                getStartedSection
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
                Text("You can also import raw bank statement files (MT940, ABN CSV, PayPal, Wise, SEB) directly from the Import tab.")
            } icon: {
                Image(systemName: "doc.badge.plus").foregroundStyle(Theme.accent)
            }
            Label {
                Text("Your data stays on your device and syncs only through snapshot files you move yourself. There's no account and no cloud service.")
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
