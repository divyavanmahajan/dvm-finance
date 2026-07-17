import SwiftUI
import DVMFinanceKit

/// The Budgets tab: a budget-vs-actual report per category for the current
/// period window, with full add / edit / delete and a "seed from average"
/// bulk action — the iOS port of desktop's `api/budgets.py` page. Tapping a
/// row pushes the transactions that make up its actual, mirroring the Trends
/// cell tap-through.
///
/// All aggregation and writes live in `DVMFinanceKit` (`BudgetReport` /
/// `BudgetMutations`); this view only holds UI state.
struct BudgetsView: View {
    @Environment(\.appDatabase) private var appDatabase

    /// The active tab's period — the Budgets screen is split into a **Monthly**
    /// and a **Yearly** tab (default Monthly). `week` stays in the model but is
    /// not a primary tab, so this is always `.month` or `.year`.
    @State private var activePeriod: BudgetReport.Period = .month
    @State private var rows: [BudgetReport.Row] = []
    @State private var loadErrorMessage: String?
    @State private var showAddSheet = false
    @State private var editingRow: BudgetReport.Row?
    @State private var seedMessage: String?
    @State private var isLoaded = false

    var body: some View {
        NavigationStack {
            Group {
                if let loadErrorMessage {
                    ContentUnavailableView(
                        "Couldn't Load Budgets",
                        systemImage: "exclamationmark.triangle",
                        description: Text(loadErrorMessage)
                    )
                } else if rows.isEmpty && isLoaded {
                    emptyState
                } else {
                    budgetList
                }
            }
            .navigationTitle("Budgets")
            .safeAreaInset(edge: .top) { periodTabs }
            .toolbar { toolbarContent }
            .sheet(isPresented: $showAddSheet) {
                BudgetEditView(existing: nil, defaultPeriod: activePeriod) { await reload() }
            }
            .sheet(item: $editingRow) { row in
                BudgetEditView(existing: row, defaultPeriod: activePeriod) { await reload() }
            }
            .navigationDestination(for: BudgetTransactionsRoute.self) { route in
                TransactionsListView(initialFilter: route.filter)
            }
            .task(id: activePeriod) { await reload() }
        }
    }

    /// Monthly / Yearly tab selector pinned above the list. Changing it
    /// reloads the report filtered to the selected period and re-seeds the add
    /// sheet's default period.
    private var periodTabs: some View {
        Picker("Budget period", selection: $activePeriod.animation()) {
            Text("Monthly").tag(BudgetReport.Period.month)
            Text("Yearly").tag(BudgetReport.Period.year)
        }
        .pickerStyle(.segmented)
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(.bar)
    }

    // MARK: - List

    private var budgetList: some View {
        List {
            if let seedMessage {
                Section {
                    Label(seedMessage, systemImage: "checkmark.circle.fill")
                        .font(.subheadline)
                        .foregroundStyle(Theme.income)
                }
            }

            Section {
                ForEach(rows) { row in
                    NavigationLink(value: BudgetTransactionsRoute(row: row)) {
                        BudgetRowView(row: row)
                    }
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        Button(role: .destructive) {
                            Task { await delete(row) }
                        } label: { Label("Delete", systemImage: "trash") }
                        Button {
                            editingRow = row
                        } label: { Label("Edit", systemImage: "pencil") }
                        .tint(Theme.accent)
                    }
                }
            } footer: {
                Text("Actuals sum the absolute value of transactions in each budget’s current period window, using the effective category. Transfers are excluded.")
            }
        }
        .listStyle(.insetGrouped)
    }

    private var emptyState: some View {
        ContentUnavailableView {
            Label("No Budgets", systemImage: "chart.pie")
        } description: {
            Text("Add a budget to track spending against a target, or seed one per top-level category from your recent average.")
        } actions: {
            Button { showAddSheet = true } label: {
                Label("Add budget", systemImage: "plus")
            }
            .buttonStyle(.borderedProminent)
            Button { Task { await seed() } } label: {
                Label("Seed from average", systemImage: "wand.and.stars")
            }
        }
    }

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        ToolbarItem(placement: .navigationBarTrailing) {
            Button { showAddSheet = true } label: {
                Label("Add budget", systemImage: "plus")
            }
        }
        ToolbarItem(placement: .navigationBarTrailing) {
            Menu {
                Button {
                    Task { await seed() }
                } label: {
                    Label(
                        "Seed \(activePeriod == .year ? "yearly" : "monthly") from 3-month average",
                        systemImage: "wand.and.stars"
                    )
                }
            } label: {
                Label("More", systemImage: "ellipsis.circle")
            }
        }
    }

    // MARK: - Actions

    private func reload() async {
        guard let appDatabase else { return }
        seedMessage = nil
        do {
            rows = try await AppQueries.budgetReport(appDatabase: appDatabase, period: activePeriod)
            loadErrorMessage = nil
        } catch {
            loadErrorMessage = "Couldn't load budgets: \(error.localizedDescription)"
        }
        isLoaded = true
    }

    private func delete(_ row: BudgetReport.Row) async {
        guard let appDatabase else { return }
        do {
            try await AppQueries.deleteBudget(appDatabase: appDatabase, budgetId: row.budgetId)
            await reload()
        } catch {
            loadErrorMessage = "Couldn't delete budget: \(error.localizedDescription)"
        }
    }

    private func seed() async {
        guard let appDatabase else { return }
        do {
            let created = try await AppQueries.seedTopLevelBudgets(
                appDatabase: appDatabase, period: activePeriod)
            seedMessage = created.isEmpty
                ? "No new budgets to add — every top-level category with recent spend already has one."
                : "Added \(created.count) budget\(created.count == 1 ? "" : "s"): \(created.joined(separator: ", "))."
            await reload()
        } catch {
            loadErrorMessage = "Couldn't seed budgets: \(error.localizedDescription)"
        }
    }
}

// MARK: - Row

private struct BudgetRowView: View {
    let row: BudgetReport.Row

    private var fraction: Double {
        guard row.budget > 0 else { return row.actual > 0 ? 1 : 0 }
        return min(row.actual / row.budget, 1)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                CategoryChip(category: row.category)
                Spacer()
                StatusBadge(status: row.status, percentage: row.percentage)
            }

            ProgressBar(fraction: fraction, color: Theme.statusColor(row.status))

            HStack {
                Text("\(DisplayFormat.currency(row.actual)) of \(DisplayFormat.currency(row.budget))")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
                Spacer()
                Text(remainingLabel)
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(row.remaining < 0 ? Theme.expense : .secondary)
                    .monospacedDigit()
            }

            Text("\(row.period.label) · \(DisplayFormat.mediumDate.string(from: row.periodStart)) – \(DisplayFormat.mediumDate.string(from: row.periodEnd))")
                .font(.caption2)
                .foregroundStyle(.tertiary)
        }
        .padding(.vertical, 4)
    }

    private var remainingLabel: String {
        if row.remaining < 0 {
            return "\(DisplayFormat.currency(abs(row.remaining))) over"
        }
        return "\(DisplayFormat.currency(row.remaining)) left"
    }
}

private struct StatusBadge: View {
    let status: BudgetReport.Status
    let percentage: Double

    var body: some View {
        Text("\(Int(percentage.rounded()))%")
            .font(.caption.weight(.semibold))
            .monospacedDigit()
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(Capsule().fill(Theme.statusColor(status).opacity(0.15)))
            .foregroundStyle(Theme.statusColor(status))
    }
}

private struct ProgressBar: View {
    let fraction: Double
    let color: Color

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(Color.secondary.opacity(0.15))
                Capsule()
                    .fill(color)
                    .frame(width: max(6, geo.size.width * fraction))
            }
        }
        .frame(height: 8)
    }
}

/// Navigation route for a tapped budget row: the transactions in its current
/// period window under its (effective, subtree-matched) category.
private struct BudgetTransactionsRoute: Hashable {
    var filter: TransactionFilter

    init(row: BudgetReport.Row) {
        self.filter = TransactionFilter(
            dateFrom: row.periodStart,
            dateTo: row.periodEnd,
            categories: [row.category]
        )
    }
}

#Preview {
    BudgetsView()
}
