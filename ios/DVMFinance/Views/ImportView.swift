import SwiftUI
import UniformTypeIdentifiers
import DVMFinanceKit

/// The Import tab (`ios/docs/spec.md` "UI" §3): statement file import,
/// snapshot import, snapshot export, and read-only audit history
/// (`snapshot_imports` / `rule_change_reports`).
///
/// Business logic (parsing, dedup, rule application, snapshot merge) is
/// entirely `DVMFinanceKit` calls; this view only picks files, dispatches to
/// the Kit, and renders the resulting summaries — `ios/docs/plan.md`
/// "Phase E": "Keep views thin; NO business logic in the app target".
struct ImportView: View {
    @Environment(\.appDatabase) private var appDatabase
    @Environment(\.appDataDirectory) private var appDataDirectory
    @Environment(\.appDatabaseURL) private var appDatabaseURL

    @State private var showStatementImporter = false
    @State private var showSnapshotImporter = false
    @State private var pendingStatementURL: URL?
    @State private var showFormatDialog = false

    @State private var isBusy = false
    @State private var errorMessage: String?
    @State private var statementSummary: StatementImportSummary?
    @State private var snapshotImportSummary: SnapshotImportSummaryDisplay?
    @State private var exportedFileURL: URL?

    var body: some View {
        NavigationStack {
            List {
                Section("Import") {
                    Button {
                        showStatementImporter = true
                    } label: {
                        Label("Import statement file", systemImage: "doc.badge.plus")
                    }
                    Button {
                        showSnapshotImporter = true
                    } label: {
                        Label("Import snapshot", systemImage: "square.and.arrow.down.on.square")
                    }
                    Button {
                        Task { await exportSnapshot() }
                    } label: {
                        Label("Export snapshot", systemImage: "square.and.arrow.up")
                    }
                    if let exportedFileURL {
                        ShareLink(item: exportedFileURL) {
                            Label("Share \(exportedFileURL.lastPathComponent)", systemImage: "square.and.arrow.up.circle")
                        }
                    }
                }

                if isBusy {
                    Section {
                        HStack {
                            ProgressView()
                            Text("Working…")
                        }
                    }
                }

                if let errorMessage {
                    Section {
                        Text(errorMessage).foregroundStyle(.red)
                    }
                }

                Section("History") {
                    NavigationLink {
                        SnapshotImportHistoryView()
                    } label: {
                        Label("Snapshot imports", systemImage: "clock.arrow.circlepath")
                    }
                    NavigationLink {
                        RuleChangeHistoryView()
                    } label: {
                        Label("Categorization runs", systemImage: "list.bullet.clipboard")
                    }
                }
            }
            .navigationTitle("Import")
            .fileImporter(
                isPresented: $showStatementImporter,
                allowedContentTypes: Self.statementContentTypes,
                allowsMultipleSelection: false
            ) { result in
                handleStatementPicked(result)
            }
            .fileImporter(
                isPresented: $showSnapshotImporter,
                allowedContentTypes: Self.snapshotContentTypes,
                allowsMultipleSelection: false
            ) { result in
                handleSnapshotPicked(result)
            }
            .confirmationDialog(
                "Which format is this file?",
                isPresented: $showFormatDialog,
                titleVisibility: .visible
            ) {
                ForEach(StatementFormat.allCases) { format in
                    Button(format.displayName) {
                        if let url = pendingStatementURL {
                            Task { await importStatement(url: url, format: format) }
                        }
                        pendingStatementURL = nil
                    }
                }
                Button("Cancel", role: .cancel) { pendingStatementURL = nil }
            }
            .sheet(item: $statementSummary) { summary in
                StatementImportSummaryView(summary: summary)
            }
            .sheet(item: $snapshotImportSummary) { summary in
                NavigationStack {
                    SnapshotImportSummaryContent(record: summary.record)
                        .toolbar {
                            ToolbarItem(placement: .confirmationAction) {
                                Button("Done") { snapshotImportSummary = nil }
                            }
                        }
                }
            }
        }
    }

    // MARK: - UTType lists (built defensively — a filename-extension UTType
    // lookup can return nil on some OS/extension combinations).

    private static var statementContentTypes: [UTType] {
        var types: [UTType] = [.commaSeparatedText, .plainText]
        for ext in ["sta", "940", "mt940", "mta"] {
            if let type = UTType(filenameExtension: ext) {
                types.append(type)
            }
        }
        return types
    }

    private static var snapshotContentTypes: [UTType] {
        // ".json.gz" is a compound extension; UTType resolution by extension
        // uses the final component ("gz"), so `.gzip` covers it. `.item` is
        // kept as a catch-all fallback ("Import snapshot ... .gz/any" per
        // `ios/docs/plan.md` "Phase E") in case a share-sheet-delivered file
        // arrives with no extension or an unrecognized one.
        [UTType.gzip, UTType.item]
    }

    // MARK: - Statement import

    private func handleStatementPicked(_ result: Result<[URL], Error>) {
        switch result {
        case .failure(let error):
            errorMessage = "Couldn't open file: \(error.localizedDescription)"
        case .success(let urls):
            guard let url = urls.first else { return }
            let ext = url.pathExtension.lowercased()
            if ext == "csv" || ext == "txt" {
                // Ambiguous: ABN CSV / PayPal / Wise / SEB all export .csv,
                // and Wise/PayPal/SEB exports can also be .txt — mirrors the
                // desktop upload page's explicit format picker rather than
                // guessing.
                pendingStatementURL = url
                showFormatDialog = true
            } else {
                Task { await importStatement(url: url, format: nil) }
            }
        }
    }

    /// `format == nil` uses `StatementFileParser`'s extension auto-detection
    /// (`.sta`/`.mt940`/`.mta` -> MT940; anything else unsupported/error);
    /// a non-nil `format` uses the user's explicit `StatementFormat` choice.
    private func importStatement(url: URL, format: StatementFormat?) async {
        guard let appDatabase else { return }
        isBusy = true
        errorMessage = nil
        defer { isBusy = false }

        let accessing = url.startAccessingSecurityScopedResource()
        defer { if accessing { url.stopAccessingSecurityScopedResource() } }

        do {
            let parsed: [ParsedTransaction]
            if let format {
                parsed = try StatementFormat.parse(url: url, as: format)
            } else {
                parsed = try StatementFileParser.parse(fileURL: url)
            }

            // Dedup -> insert -> apply rules -> audit report, all in one
            // write transaction — see `AppQueries.importStatementTransactions`'s
            // doc comment for why this audits file imports (a deliberate
            // iOS addition over desktop's unaudited `import_file`).
            let result = try await AppQueries.importStatementTransactions(appDatabase: appDatabase, transactions: parsed)
            statementSummary = StatementImportSummary(
                sourceFile: url.lastPathComponent,
                imported: result.imported,
                duplicates: result.duplicates,
                categorized: result.categorized,
                uncategorized: result.uncategorized
            )
        } catch {
            errorMessage = "Couldn't import '\(url.lastPathComponent)': \(error.localizedDescription)"
        }
    }

    // MARK: - Snapshot import

    private func handleSnapshotPicked(_ result: Result<[URL], Error>) {
        switch result {
        case .failure(let error):
            errorMessage = "Couldn't open file: \(error.localizedDescription)"
        case .success(let urls):
            guard let url = urls.first else { return }
            Task { await importSnapshotFile(url: url) }
        }
    }

    private func importSnapshotFile(url: URL) async {
        guard let appDatabase, let appDatabaseURL else { return }
        isBusy = true
        errorMessage = nil
        defer { isBusy = false }

        let accessing = url.startAccessingSecurityScopedResource()
        defer { if accessing { url.stopAccessingSecurityScopedResource() } }

        do {
            let data = try Data(contentsOf: url)
            let document = try SnapshotCodec.read(data)
            let record = try SnapshotImporter.importSnapshot(
                appDatabase: appDatabase,
                document: document,
                databaseURL: appDatabaseURL
            )
            snapshotImportSummary = SnapshotImportSummaryDisplay(record: record)
        } catch {
            errorMessage = "Couldn't import snapshot: \(error.localizedDescription)"
        }
    }

    // MARK: - Snapshot export

    private func exportSnapshot() async {
        guard let appDatabase, let appDataDirectory else { return }
        isBusy = true
        errorMessage = nil
        defer { isBusy = false }
        do {
            let url = try SnapshotExporter.exportSnapshot(appDatabase: appDatabase, dataDirectory: appDataDirectory)
            exportedFileURL = url
        } catch {
            errorMessage = "Couldn't export snapshot: \(error.localizedDescription)"
        }
    }
}

// MARK: - Statement format display

extension StatementFormat {
    var displayName: String {
        switch self {
        case .mt940: return "MT940 (.txt)"
        case .abnCSV: return "ABN CSV"
        case .paypal: return "PayPal"
        case .wise: return "Wise"
        case .seb: return "SEB"
        }
    }
}

// MARK: - Summary models (view-layer only; not ports of a Python type)

struct StatementImportSummary: Identifiable {
    let id = UUID()
    let sourceFile: String
    let imported: Int
    let duplicates: Int
    let categorized: Int
    let uncategorized: Int
}

struct SnapshotImportSummaryDisplay: Identifiable {
    let id = UUID()
    let record: SnapshotImportRecord
}

// MARK: - Summary sheets

private struct StatementImportSummaryView: View {
    @Environment(\.dismiss) private var dismiss
    let summary: StatementImportSummary

    var body: some View {
        NavigationStack {
            List {
                Section(summary.sourceFile) {
                    LabeledContent("Imported", value: "\(summary.imported)")
                    LabeledContent("Duplicates skipped", value: "\(summary.duplicates)")
                    LabeledContent("Categorized", value: "\(summary.categorized)")
                    LabeledContent("Uncategorized", value: "\(summary.uncategorized)")
                }
            }
            .navigationTitle("Import Complete")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

/// Plain content (no `NavigationStack` of its own) so it can be reused both
/// as a `.sheet` (right after a snapshot import — `ImportView` wraps it in a
/// `NavigationStack` + "Done" button) and as a `NavigationLink` push from
/// `SnapshotImportHistoryView` (which already has an ambient
/// `NavigationStack` via `ImportView`'s own).
struct SnapshotImportSummaryContent: View {
    let record: SnapshotImportRecord

    var body: some View {
        List {
            if let counts = record.countsDictionary {
                ForEach(Array(counts.keys.sorted()), id: \.self) { entity in
                    if let entityCounts = counts[entity] as? [String: Any] {
                        Section(entity) {
                            ForEach(Array(entityCounts.keys.sorted()), id: \.self) { key in
                                LabeledContent(key, value: "\(entityCounts[key] ?? 0)")
                            }
                        }
                    }
                }
            }
            Section {
                LabeledContent("Source machine", value: record.sourceMachineId ?? "—")
                LabeledContent("Schema version", value: record.schemaVersion.map(String.init) ?? "—")
            }
        }
        .navigationTitle("Snapshot Imported")
        .navigationBarTitleDisplayMode(.inline)
    }
}

#Preview {
    ImportView()
}
