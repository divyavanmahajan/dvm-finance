import SwiftUI
import DVMFinanceKit

/// The Transactions tab (`ios/docs/spec.md` "UI" §1): a thin `NavigationStack`
/// wrapper around `TransactionsListView` for the tab-bar entry point. Trends
/// cell tap-through (`TrendsView`) instead pushes `TransactionsListView`
/// directly into its own ambient `NavigationStack`, so a cell's prefilled
/// screen still gets a normal push/back transition instead of nesting a
/// second `NavigationStack` inside a navigation destination.
struct TransactionsView: View {
    var initialFilter = TransactionFilter()

    var body: some View {
        NavigationStack {
            TransactionsListView(initialFilter: initialFilter)
        }
    }
}

/// The actual transactions list content: searchable, date-grouped, filter
/// sheet, incremental "Load more" pagination, row -> detail. Read-only — no
/// manual categorization in v1 (spec.md "Non-goals").
///
/// All querying/aggregation lives in `DVMFinanceKit.TransactionQuery`; this
/// view only holds UI state and orchestrates `dbWriter` calls, per
/// `ios/docs/plan.md` "Phase E": "Keep views thin; NO business logic in the
/// app target".
struct TransactionsListView: View {
    @Environment(\.appDatabase) private var appDatabase

    @State private var filter: TransactionFilter
    @State private var items: [TransactionRecord] = []
    @State private var total = 0
    @State private var totalSum = 0.0
    @State private var hasNext = false
    /// Decoupled from `filter.page` deliberately: `filter` also drives
    /// `.task(id: filter)`'s reload-from-page-1 debounce, so writing
    /// `loadMore`'s advanced page number back into it would retrigger that
    /// task and discard the just-appended items — see `loadMore()`.
    @State private var currentPage = 1
    @State private var isLoadingMore = false
    @State private var loadErrorMessage: String?
    @State private var showFilterSheet = false

    init(initialFilter: TransactionFilter = TransactionFilter()) {
        self._filter = State(initialValue: initialFilter)
    }

    var body: some View {
        List {
            Section {
                summaryRow
            }

            ForEach(sections, id: \.date) { section in
                Section(header: Text(DisplayFormat.sectionDate.string(from: section.date))) {
                    ForEach(section.items, id: \.id) { transaction in
                        NavigationLink(value: transaction.id) {
                            TransactionRow(transaction: transaction)
                        }
                    }
                }
            }

            if hasNext {
                Section {
                    loadMoreRow
                }
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle("Transactions")
        .searchable(text: searchText, prompt: "Search description")
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button {
                    filter.includeTransfers.toggle()
                } label: {
                    Image(systemName: filter.includeTransfers
                        ? "arrow.left.arrow.right.circle.fill"
                        : "arrow.left.arrow.right.circle")
                }
                .accessibilityLabel(filter.includeTransfers ? "Transfers included" : "Transfers hidden")
            }
            ToolbarItem(placement: .navigationBarTrailing) {
                Button {
                    showFilterSheet = true
                } label: {
                    Label("Filter", systemImage: "line.3.horizontal.decrease.circle")
                }
            }
        }
        .sheet(isPresented: $showFilterSheet) {
            FilterSheet(filter: $filter)
        }
        .navigationDestination(for: String.self) { transactionId in
            TransactionDetailView(transactionId: transactionId)
        }
        .task(id: filter) {
            // Debounce: any filter change (including a keystroke in the
            // search field) restarts this task; SwiftUI cancels the
            // previous one automatically, so only the last edit in a
            // burst actually reloads.
            try? await Task.sleep(nanoseconds: 300_000_000)
            if Task.isCancelled { return }
            await reload()
        }
    }

    // MARK: - Search binding

    private var searchText: Binding<String> {
        Binding(
            get: { filter.q ?? "" },
            set: { filter.q = $0.isEmpty ? nil : $0 }
        )
    }

    // MARK: - Summary / load more

    private var summaryRow: some View {
        HStack {
            if let loadErrorMessage {
                Text(loadErrorMessage).foregroundStyle(.red)
            } else {
                Text("\(total) transaction\(total == 1 ? "" : "s")")
                Spacer()
                Text(DisplayFormat.plainAmount(totalSum))
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
            }
        }
        .font(.footnote)
    }

    private var loadMoreRow: some View {
        Button {
            Task { await loadMore() }
        } label: {
            HStack {
                Spacer()
                if isLoadingMore {
                    ProgressView()
                } else {
                    Text("Load more")
                }
                Spacer()
            }
        }
        .disabled(isLoadingMore)
    }

    // MARK: - Date grouping

    /// Groups the currently-loaded items by `transactiondate`, preserving
    /// each date's first-appearance order (correct regardless of the active
    /// sort — under the default date sort this also happens to produce
    /// contiguous sections).
    private var sections: [(date: Date, items: [TransactionRecord])] {
        var order: [Date] = []
        var byDate: [Date: [TransactionRecord]] = [:]
        for item in items {
            if byDate[item.transactiondate] == nil {
                order.append(item.transactiondate)
                byDate[item.transactiondate] = []
            }
            byDate[item.transactiondate]!.append(item)
        }
        return order.map { (date: $0, items: byDate[$0] ?? []) }
    }

    // MARK: - Data loading

    private func reload() async {
        guard let appDatabase else { return }
        var reloadFilter = filter
        reloadFilter.page = 1
        do {
            async let pageTask = AppQueries.transactionsPage(appDatabase: appDatabase, filter: reloadFilter)
            async let sumTask = AppQueries.transactionsSum(appDatabase: appDatabase, filter: reloadFilter)
            let (page, sum) = try await (pageTask, sumTask)
            items = page.items
            total = page.total
            totalSum = sum
            hasNext = page.hasNext
            currentPage = page.page
            loadErrorMessage = nil
        } catch {
            loadErrorMessage = "Couldn't load transactions: \(error.localizedDescription)"
        }
    }

    private func loadMore() async {
        guard let appDatabase, hasNext, !isLoadingMore else { return }
        isLoadingMore = true
        defer { isLoadingMore = false }
        var nextFilter = filter
        nextFilter.page = currentPage + 1
        do {
            let page = try await AppQueries.transactionsPage(appDatabase: appDatabase, filter: nextFilter)
            items.append(contentsOf: page.items)
            hasNext = page.hasNext
            currentPage = page.page
        } catch {
            loadErrorMessage = "Couldn't load more transactions: \(error.localizedDescription)"
        }
    }
}

// MARK: - Row

private struct TransactionRow: View {
    let transaction: TransactionRecord

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(transaction.description?.isEmpty == false ? transaction.description! : "(no description)")
                    .font(.body)
                    .lineLimit(2)
                HStack(spacing: 6) {
                    categoryChip
                    if let tags = TransactionQuery.effectiveTags(transaction), !tags.isEmpty {
                        Text(tags)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
            }
            Spacer(minLength: 8)
            Text(DisplayFormat.currency(transaction.amount, code: transaction.currency))
                .font(.body.monospacedDigit())
                .foregroundStyle(transaction.amount < 0 ? Color.red : Color.primary)
        }
        .padding(.vertical, 2)
    }

    private var categoryChip: some View {
        let category = TransactionQuery.effectiveCategory(transaction)
        return Text(category?.isEmpty == false ? category! : "Uncategorized")
            .font(.caption)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(Capsule().fill(Color.secondary.opacity(0.15)))
            .foregroundStyle(.secondary)
    }
}

#Preview {
    TransactionsView()
}
