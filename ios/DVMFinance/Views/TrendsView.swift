import SwiftUI
import DVMFinanceKit

/// The Trends tab (`ios/docs/spec.md` "UI" §2): a month/year × effective-category
/// matrix, hyphen-rollup parents expandable to their exact children, tapping
/// any cell or row total pushes `TransactionsListView` prefilled with the
/// equivalent `TransactionFilter` so the pushed list sums exactly to what was
/// tapped (`TrendsBuilder.transactionFilter(for:period:params:)`).
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
    @State private var showFilterSheet = false

    /// Row height shared by the frozen category column and the scrollable
    /// value columns — both are built from the same `visibleRows` list, so
    /// keeping this one constant in sync between them is what keeps the two
    /// halves' rows aligned (see `matrix(_:)`).
    private let rowHeight: CGFloat = 34

    var body: some View {
        NavigationStack {
            Group {
                if let table {
                    VStack(spacing: 0) {
                        quickRangeChips
                        matrix(table)
                    }
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
                        showFilterSheet = true
                    } label: {
                        Label("Filter", systemImage: "line.3.horizontal.decrease.circle")
                    }
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
            .sheet(isPresented: $showFilterSheet) {
                FilterSheet(filter: $params)
            }
            .navigationDestination(for: TrendsCellRoute.self) { route in
                TransactionsListView(initialFilter: route.filter)
            }
            .task(id: params) {
                await reload()
            }
        }
    }

    // MARK: - Quick range chips

    /// Always-visible rolling-window shortcuts (`ios/docs/plan.md` iOS UI
    /// feedback: "no way to quick select the last few months... should be
    /// easily accessible" — not buried inside the filter sheet). The 3/6/12
    /// month chips end today, so the in-progress current month (excluded
    /// from the last-12-*full*-months default) is included; "12mo (full)"
    /// keeps that default reachable by name once a chip has been tapped.
    private var quickRangeChips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(TrendsBuilder.TrendsParams.QuickRange.allCases) { range in
                    quickRangeChip(range)
                }
                if params.quickRange != nil || params.preset != nil || params.dateFrom != nil || params.dateTo != nil {
                    Button {
                        params.quickRange = nil
                        params.preset = nil
                        params.dateFrom = nil
                        params.dateTo = nil
                    } label: {
                        Text("Default")
                            .font(.caption)
                    }
                    .buttonStyle(.bordered)
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
        }
    }

    private func quickRangeChip(_ range: TrendsBuilder.TrendsParams.QuickRange) -> some View {
        let isActive = params.quickRange == range
        return Button {
            params.quickRange = range
            params.preset = nil
            params.dateFrom = nil
            params.dateTo = nil
        } label: {
            Text(range.label)
                .font(.caption.weight(isActive ? .semibold : .regular))
        }
        .buttonStyle(.bordered)
        .tint(isActive ? .accentColor : .secondary)
    }

    // MARK: - Matrix (frozen category column + horizontally-scrolling value columns)

    /// Two synced halves inside one shared vertical `ScrollView`: a
    /// fixed-width category column that only scrolls vertically (with the
    /// outer view), and a horizontally-scrolling `Grid` of period/total
    /// columns (`ios/docs/plan.md` iOS UI feedback: "first column with the
    /// categories disappears as you scroll to the right"). Both halves are
    /// built from the same `visibleRows` list at the same `rowHeight`, which
    /// is what keeps their rows aligned.
    private func matrix(_ table: TrendsBuilder.TrendsTable) -> some View {
        let rows = visibleRows(table)
        return ScrollView(.vertical) {
            HStack(spacing: 0) {
                frozenCategoryColumn(table, rows: rows)
                ScrollView(.horizontal) {
                    valueColumns(table, rows: rows)
                }
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

    /// Flattened top-level rows plus any expanded parent's children, in
    /// display order — the single source of truth both matrix halves
    /// render from, so a parent's expand/collapse toggle can never desync
    /// row counts between them.
    private func visibleRows(_ table: TrendsBuilder.TrendsTable) -> [(row: TrendsBuilder.TrendRow, isChild: Bool)] {
        var result: [(TrendsBuilder.TrendRow, Bool)] = []
        for row in table.rows {
            result.append((row, false))
            if row.hasChildren, expandedParents.contains(row.label) {
                for child in row.children {
                    result.append((child, true))
                }
            }
        }
        return result
    }

    private func frozenCategoryColumn(
        _ table: TrendsBuilder.TrendsTable,
        rows: [(row: TrendsBuilder.TrendRow, isChild: Bool)]
    ) -> some View {
        VStack(spacing: 0) {
            Text("Category")
                .font(.caption.bold())
                .frame(width: 160, height: rowHeight, alignment: .leading)
                .padding(.horizontal, 8)
                .background(Color(.secondarySystemBackground))
            ForEach(Array(rows.enumerated()), id: \.offset) { _, entry in
                categoryCell(entry.row, isChild: entry.isChild)
            }
            Text("Total")
                .font(.caption.bold())
                .frame(width: 160, height: rowHeight, alignment: .leading)
                .padding(.horizontal, 8)
                .background(Color(.secondarySystemBackground))
        }
        .background(Color(.systemBackground))
        .zIndex(1)
        .shadow(color: .black.opacity(0.08), radius: 3, x: 2, y: 0)
    }

    private func valueColumns(
        _ table: TrendsBuilder.TrendsTable,
        rows: [(row: TrendsBuilder.TrendRow, isChild: Bool)]
    ) -> some View {
        Grid(alignment: .trailing, horizontalSpacing: 0, verticalSpacing: 0) {
            GridRow {
                ForEach(table.periods, id: \.key) { period in
                    Text(period.label)
                        .font(.caption.bold())
                        .frame(width: 88, height: rowHeight, alignment: .trailing)
                        .padding(.horizontal, 8)
                        .background(Color(.secondarySystemBackground))
                }
                Text("Total")
                    .font(.caption.bold())
                    .frame(width: 88, height: rowHeight, alignment: .trailing)
                    .padding(.horizontal, 8)
                    .background(Color(.secondarySystemBackground))
            }
            ForEach(Array(rows.enumerated()), id: \.offset) { _, entry in
                GridRow {
                    ForEach(table.periods, id: \.key) { period in
                        cellButton(row: entry.row, period: period, table: table)
                    }
                    Text(DisplayFormat.compactAmount(entry.row.total))
                        .font(.caption.monospacedDigit().bold())
                        .frame(width: 88, height: rowHeight, alignment: .trailing)
                        .padding(.horizontal, 8)
                }
            }
            GridRow {
                ForEach(table.periods, id: \.key) { period in
                    Text(DisplayFormat.compactAmount(table.columnTotals[period.key] ?? 0))
                        .font(.caption.monospacedDigit().bold())
                        .frame(width: 88, height: rowHeight, alignment: .trailing)
                        .padding(.horizontal, 8)
                        .background(Color(.secondarySystemBackground))
                }
                Text(DisplayFormat.compactAmount(table.grandTotal))
                    .font(.caption.monospacedDigit().bold())
                    .frame(width: 88, height: rowHeight, alignment: .trailing)
                    .padding(.horizontal, 8)
                    .background(Color(.secondarySystemBackground))
            }
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
        .frame(width: 160, height: rowHeight, alignment: .leading)
        .padding(.leading, isChild ? 20 : 8)
        .disabled(!row.hasChildren)
    }

    private func cellButton(
        row: TrendsBuilder.TrendRow,
        period: TrendsBuilder.Period,
        table: TrendsBuilder.TrendsTable
    ) -> some View {
        let value = row.cells[period.key] ?? 0
        return NavigationLink(value: TrendsCellRoute(row: row, period: period, params: params)) {
            Text(value == 0 ? "—" : DisplayFormat.compactAmount(value))
                .font(.caption.monospacedDigit())
                .frame(width: 88, height: rowHeight, alignment: .trailing)
                .padding(.horizontal, 8)
        }
        .buttonStyle(.plain)
        .disabled(value == 0)
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
/// `TrendsBuilder.transactionFilter(for:period:params:)`, so its filtered
/// sum always matches the tapped cell exactly.
private struct TrendsCellRoute: Hashable {
    var filter: TransactionFilter

    init(row: TrendsBuilder.TrendRow, period: TrendsBuilder.Period, params: TrendsBuilder.TrendsParams) {
        self.filter = TrendsBuilder.transactionFilter(for: row, period: period, params: params)
    }
}

#Preview {
    TrendsView()
}
