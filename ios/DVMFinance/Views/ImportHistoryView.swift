import SwiftUI
import DVMFinanceKit

/// Read-only audit history lists for the Import screen (`ios/docs/spec.md`
/// "UI" §3): `snapshot_imports` and `rule_change_reports`, each with a
/// per-transaction-change detail view. All data access goes through
/// `DVMFinanceKit.AppQueries`.
struct SnapshotImportHistoryView: View {
    @Environment(\.appDatabase) private var appDatabase

    @State private var records: [SnapshotImportRecord] = []
    @State private var errorMessage: String?

    var body: some View {
        List {
            if records.isEmpty {
                ContentUnavailableView(
                    "No Snapshot Imports",
                    systemImage: "square.and.arrow.down.on.square",
                    description: Text(errorMessage ?? "Imported snapshots will appear here.")
                )
            }
            ForEach(records, id: \.id) { record in
                NavigationLink {
                    SnapshotImportSummaryContent(record: record)
                } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(DisplayFormat.mediumDateTime.string(from: record.createdAt))
                            .font(.subheadline)
                        Text(record.sourceMachineId ?? "Unknown machine")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .navigationTitle("Snapshot Imports")
        .task { await load() }
    }

    private func load() async {
        guard let appDatabase else { return }
        do {
            records = try await AppQueries.snapshotImports(appDatabase: appDatabase)
        } catch {
            errorMessage = "Couldn't load history: \(error.localizedDescription)"
        }
    }
}

struct RuleChangeHistoryView: View {
    @Environment(\.appDatabase) private var appDatabase

    @State private var reports: [RuleChangeReportRecord] = []
    @State private var errorMessage: String?

    var body: some View {
        List {
            if reports.isEmpty {
                ContentUnavailableView(
                    "No Categorization Runs",
                    systemImage: "list.bullet.clipboard",
                    description: Text(errorMessage ?? "File imports and snapshot imports both record a run here.")
                )
            }
            ForEach(reports, id: \.id) { report in
                NavigationLink {
                    RuleChangeReportDetailView(report: report)
                } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(report.action.capitalized)
                                .font(.subheadline.bold())
                            Spacer()
                            Text(DisplayFormat.mediumDateTime.string(from: report.createdAt))
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Text(changedCountLabel(report))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .navigationTitle("Categorization Runs")
        .task { await load() }
    }

    private func changedCountLabel(_ report: RuleChangeReportRecord) -> String {
        guard let summary = report.summaryDictionary, let changedNumber = summary["changed"] as? NSNumber else {
            return "—"
        }
        let changed = changedNumber.intValue
        return "\(changed) transaction\(changed == 1 ? "" : "s") changed"
    }

    private func load() async {
        guard let appDatabase else { return }
        do {
            reports = try await AppQueries.ruleChangeReports(appDatabase: appDatabase)
        } catch {
            errorMessage = "Couldn't load history: \(error.localizedDescription)"
        }
    }
}

struct RuleChangeReportDetailView: View {
    @Environment(\.appDatabase) private var appDatabase
    let report: RuleChangeReportRecord

    @State private var items: [RuleChangeItemRecord] = []
    @State private var errorMessage: String?

    var body: some View {
        List {
            Section("Run") {
                LabeledContent("Action", value: report.action.capitalized)
                LabeledContent("Date", value: DisplayFormat.mediumDateTime.string(from: report.createdAt))
                if let ruleId = report.ruleId {
                    LabeledContent("Rule", value: "#\(ruleId)")
                }
                if let ruleUuid = report.ruleUuid {
                    LabeledContent("Rule UUID", value: ruleUuid)
                }
            }

            if items.isEmpty {
                Text(errorMessage ?? "No per-transaction changes recorded for this run.")
                    .foregroundStyle(.secondary)
            } else {
                Section("Changed transactions (\(items.count))") {
                    ForEach(items, id: \.id) { item in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(item.transactionId)
                                .font(.caption.monospaced())
                                .foregroundStyle(.secondary)
                            Text("\(item.oldCategory ?? "Uncategorized") → \(item.newCategory ?? "Uncategorized")")
                                .font(.subheadline)
                            if item.oldTags != item.newTags {
                                Text("tags: \(item.oldTags ?? "—") → \(item.newTags ?? "—")")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle("Run Detail")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func load() async {
        guard let appDatabase, let reportId = report.id else { return }
        do {
            items = try await AppQueries.ruleChangeItems(appDatabase: appDatabase, reportId: reportId)
        } catch {
            errorMessage = "Couldn't load changes: \(error.localizedDescription)"
        }
    }
}

#Preview {
    NavigationStack {
        SnapshotImportHistoryView()
    }
}
