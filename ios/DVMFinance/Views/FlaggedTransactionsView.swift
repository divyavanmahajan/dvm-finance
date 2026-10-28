import SwiftUI
import DVMFinanceKit

/// The flagged transactions, and the purge control.
///
/// This is the one screen of the app that shows a flagged row. The user reads
/// the rows here before the purge, and the user restores a row that the user
/// flagged by mistake. The purge copies the local database to a backup first,
/// then it deletes each flagged row. The app cannot undo the purge, so the
/// screen asks the user to confirm.
struct FlaggedTransactionsView: View {
    @Environment(\.appDatabase) private var appDatabase
    @Environment(\.appDatabaseURL) private var appDatabaseURL

    /// Runs after a restore or a purge, so that the transactions list reads
    /// the database again.
    let onChanged: () async -> Void

    @State private var rows: [TransactionRecord] = []
    @State private var message: String?
    @State private var errorMessage: String?
    @State private var showPurgeConfirmation = false
    @State private var isPurging = false

    var body: some View {
        List {
            if let message {
                Section { Text(message).font(.subheadline).foregroundStyle(.secondary) }
            }
            if let errorMessage {
                Section {
                    Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(Theme.expense)
                        .font(.subheadline)
                }
            }

            if rows.isEmpty {
                Section {
                    Text("No transaction waits for removal.")
                        .foregroundStyle(.secondary)
                        .font(.subheadline)
                }
            } else {
                Section("Waiting for removal") {
                    ForEach(rows, id: \.id) { row in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text(row.description?.isEmpty == false ? row.description! : "(no description)")
                                Spacer(minLength: 8)
                                Text(DisplayFormat.currency(row.amount, code: row.currency))
                                    .monospacedDigit()
                            }
                            Text(DisplayFormat.mediumDate.string(from: row.transactiondate))
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .swipeActions {
                            Button("Restore") { Task { await restore(row) } }
                                .tint(Theme.accent)
                        }
                    }
                }

                Section {
                    Button(role: .destructive) {
                        showPurgeConfirmation = true
                    } label: {
                        Label("Purge \(rows.count) transaction\(rows.count == 1 ? "" : "s")", systemImage: "trash")
                    }
                    .disabled(isPurging)
                } footer: {
                    Text("The purge copies the database to a backup first. "
                        + "The app cannot undo the purge.")
                }
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle("Flagged")
        .navigationBarTitleDisplayMode(.inline)
        .confirmationDialog(
            "Delete each flagged transaction?",
            isPresented: $showPurgeConfirmation,
            titleVisibility: .visible
        ) {
            Button("Purge", role: .destructive) { Task { await purge() } }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("The app writes a backup of the database first. "
                + "The app cannot undo the purge.")
        }
        .task { await reload() }
    }

    private func reload() async {
        guard let appDatabase else { return }
        do {
            rows = try await AppQueries.flaggedTransactions(appDatabase: appDatabase)
            errorMessage = nil
        } catch {
            errorMessage = "Couldn't read the flagged transactions: \(error.localizedDescription)"
        }
    }

    private func restore(_ row: TransactionRecord) async {
        guard let appDatabase else { return }
        do {
            _ = try await AppQueries.restoreTransaction(appDatabase: appDatabase, transactionId: row.id)
            message = "The transaction is back in your list."
            await reload()
            await onChanged()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func purge() async {
        guard let appDatabase, let appDatabaseURL else { return }
        isPurging = true
        defer { isPurging = false }
        do {
            let result = try await AppQueries.purgeFlaggedTransactions(
                appDatabase: appDatabase, databaseURL: appDatabaseURL)
            message = "The purge deleted \(result.deleted) transaction"
                + (result.deleted == 1 ? "." : "s.")
            errorMessage = nil
            await reload()
            await onChanged()
        } catch {
            errorMessage = "The purge failed: \(error.localizedDescription)"
        }
    }
}
