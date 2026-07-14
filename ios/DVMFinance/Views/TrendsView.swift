import SwiftUI
import DVMFinanceKit

/// The Trends tab (`ios/docs/spec.md` "UI" §2): a month/year × effective-category
/// matrix, hyphen-rollup parents expandable to their exact children, tapping
/// any cell or row total pushes `TransactionsListView` prefilled with the
/// equivalent `TransactionFilter` so the pushed list sums exactly to what was
/// tapped (`TrendsBuilder.transactionFilter(for:period:accounts:includeTransfers:)`).
///
/// All aggregation lives in `DVMFinanceKit.TrendsBuilder`; this view only
/// holds UI state (expanded rows, granularity/account/transfers pickers) and
/// renders the table it's handed.
struct TrendsView: View {
    @Environment(\.appDatabase) private var appDatabase

    @State private var params = TrendsBuilder.TrendsParams()
    @State private var table: TrendsBuilder.TrendsTable?
    @State private var expandedParents: Set<String> = []
    @State private var availableAccounts: [String] = []
    @State private var loadErrorMessage: String?
    @State private var showAccountPicker = false

    var body: some View {
        NavigationStack {
            Group {
                if let table {
                    matrix(table)
                } else if let loadErrorMessage {
                    ContentUnavailableView(
                        "Couldn't Load Trends",
                        systemImage: "exclamationmark.triangle",
                        description: Text(loadErrorMessage)
                    )
                } else {
                    ProgressView()
                }
            }
            .navigationTitle("Trends")
            .toolbar {
                ToolbarItem(placement: .principal) {
                    Picker("Granularity", selection: $params.granularity) {
                        Text("Month").tag(TrendsBuilder.TrendsParams.Granularity.month)
                        Text("Year").tag(TrendsBuilder.TrendsParams.Granularity.year)
                    }
                    .pickerStyle(.segmented)
                    .frame(width: 160)
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        showAccountPicker = true
                    } label: {
                        Label("Accounts", systemImage: "creditcard")
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        params.includeTransfers.toggle()
                    } label: {
                        Image(systemName: params.includeTransfers
                            ? "arrow.left.arrow.right.circle.fill"
                            : "arrow.left.arrow.right.circle")
                    }
                    .accessibilityLabel(params.includeTransfers ? "Transfers included" : "Transfers hidden")
                }
            }
            .sheet(isPresented: $showAccountPicker) {
                accountPickerSheet
            }
            .navigationDestination(for: TrendsCellRoute.self) { route in
                TransactionsListView(initialFilter: route.filter)
            }
            .task(id: params) {
                await reload()
            }
        }
    }

    // MARK: - Matrix

    private func matrix(_ table: TrendsBuilder.TrendsTable) -> some View {
        ScrollView([.horizontal, .vertical]) {
            Grid(alignment: .trailing, horizontalSpacing: 0, verticalSpacing: 0) {
                headerRow(table)
                ForEach(Array(table.rows.enumerated()), id: \.element.label) { _, row in
                    rowViews(row, table: table)
                }
                totalsRow(table)
            }
        }
        .safeAreaInset(edge: .bottom) {
            if table.rows.isEmpty {
                ContentUnavailableView(
                    "No Data",
                    systemImage: "chart.bar",
                    description: Text("No transactions fall inside this window.")
                )
                .padding()
            }
        }
    }

    private func headerRow(_ table: TrendsBuilder.TrendsTable) -> some View {
        GridRow {
            Text("Category")
                .font(.caption.bold())
                .frame(width: 160, alignment: .leading)
                .padding(8)
                .background(Color(.secondarySystemBackground))
            ForEach(table.periods, id: \.key) { period in
                Text(period.label)
                    .font(.caption.bold())
                    .frame(width: 88, alignment: .trailing)
                    .padding(8)
                    .background(Color(.secondarySystemBackground))
            }
            Text("Total")
                .font(.caption.bold())
                .frame(width: 88, alignment: .trailing)
                .padding(8)
                .background(Color(.secondarySystemBackground))
        }
    }

    @ViewBuilder
    private func rowViews(_ row: TrendsBuilder.TrendRow, table: TrendsBuilder.TrendsTable) -> some View {
        dataRow(row, table: table, isChild: false)
        if row.hasChildren, expandedParents.contains(row.label) {
            ForEach(row.children, id: \.label) { child in
                dataRow(child, table: table, isChild: true)
            }
        }
    }

    private func dataRow(_ row: TrendsBuilder.TrendRow, table: TrendsBuilder.TrendsTable, isChild: Bool) -> some View {
        GridRow {
            categoryCell(row, isChild: isChild)
            ForEach(table.periods, id: \.key) { period in
                cellButton(row: row, period: period, table: table)
            }
            Text(DisplayFormat.compactAmount(row.total))
                .font(.caption.monospacedDigit().bold())
                .frame(width: 88, alignment: .trailing)
                .padding(8)
        }
    }

    private func categoryCell(_ row: TrendsBuilder.TrendRow, isChild: Bool) -> some View {
        Button {
            guard row.hasChildren else { return }
            if expandedParents.contains(row.label) {
                expandedParents.remove(row.label)
            } else {
                expandedParents.insert(row.label)
            }
        } label: {
            HStack(spacing: 4) {
                if row.hasChildren {
                    Image(systemName: expandedParents.contains(row.label) ? "chevron.down" : "chevron.right")
                        .font(.caption2)
                }
                Text(row.label)
                    .font(isChild ? .caption : .caption.bold())
                    .lineLimit(1)
            }
        }
        .foregroundStyle(isChild ? .secondary : .primary)
        .frame(width: 160, alignment: .leading)
        .padding(.leading, isChild ? 20 : 8)
        .padding(.vertical, 8)
        .disabled(!row.hasChildren)
    }

    private func cellButton(
        row: TrendsBuilder.TrendRow,
        period: TrendsBuilder.Period,
        table: TrendsBuilder.TrendsTable
    ) -> some View {
        let value = row.cells[period.key] ?? 0
        return NavigationLink(value: TrendsCellRoute(row: row, period: period, accounts: params.accounts, includeTransfers: params.includeTransfers)) {
            Text(value == 0 ? "—" : DisplayFormat.compactAmount(value))
                .font(.caption.monospacedDigit())
                .frame(width: 88, alignment: .trailing)
                .padding(8)
        }
        .buttonStyle(.plain)
        .disabled(value == 0)
    }

    private func totalsRow(_ table: TrendsBuilder.TrendsTable) -> some View {
        GridRow {
            Text("Total")
                .font(.caption.bold())
                .frame(width: 160, alignment: .leading)
                .padding(8)
                .background(Color(.secondarySystemBackground))
            ForEach(table.periods, id: \.key) { period in
                Text(DisplayFormat.compactAmount(table.columnTotals[period.key] ?? 0))
                    .font(.caption.monospacedDigit().bold())
                    .frame(width: 88, alignment: .trailing)
                    .padding(8)
                    .background(Color(.secondarySystemBackground))
            }
            Text(DisplayFormat.compactAmount(table.grandTotal))
                .font(.caption.monospacedDigit().bold())
                .frame(width: 88, alignment: .trailing)
                .padding(8)
                .background(Color(.secondarySystemBackground))
        }
    }

    // MARK: - Accounts sheet

    private var accountPickerSheet: some View {
        NavigationStack {
            List(availableAccounts, id: \.self) { account in
                Button {
                    if params.accounts.contains(account) {
                        params.accounts.removeAll { $0 == account }
                    } else {
                        params.accounts.append(account)
                    }
                } label: {
                    HStack {
                        Text(account).foregroundStyle(.primary)
                        Spacer()
                        if params.accounts.contains(account) {
                            Image(systemName: "checkmark")
                        }
                    }
                }
            }
            .navigationTitle("Accounts")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { showAccountPicker = false }
                }
                ToolbarItem(placement: .cancellationAction) {
                    if !params.accounts.isEmpty {
                        Button("Clear") { params.accounts = [] }
                    }
                }
            }
        }
    }

    // MARK: - Data loading

    private func reload() async {
        guard let appDatabase else { return }
        do {
            async let tableTask = AppQueries.trendsTable(appDatabase: appDatabase, params: params)
            async let accountsTask = AppQueries.distinctAccounts(appDatabase: appDatabase)
            let (loadedTable, accounts) = try await (tableTask, accountsTask)
            table = loadedTable
            availableAccounts = accounts
            loadErrorMessage = nil
        } catch {
            loadErrorMessage = "Couldn't load trends: \(error.localizedDescription)"
        }
    }
}

/// Navigation-stack route for a tapped trends cell: the pushed
/// `TransactionsListView` is initialized directly from
/// `TrendsBuilder.transactionFilter(for:period:accounts:includeTransfers:)`,
/// so its filtered sum always matches the tapped cell exactly.
private struct TrendsCellRoute: Hashable {
    var filter: TransactionFilter

    init(row: TrendsBuilder.TrendRow, period: TrendsBuilder.Period, accounts: [String], includeTransfers: Bool) {
        self.filter = TrendsBuilder.transactionFilter(
            for: row,
            period: period,
            accounts: accounts,
            includeTransfers: includeTransfers
        )
    }
}

#Preview {
    TrendsView()
}
