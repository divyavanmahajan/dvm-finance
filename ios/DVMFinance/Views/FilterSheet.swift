import SwiftUI
import DVMFinanceKit

/// Modal filter editor, generic over `DVMFinanceKit.FilterFields` so
/// Transactions (`TransactionFilter`) and Trends (`TrendsBuilder.TrendsParams`)
/// share one editing UI (`ios/docs/plan.md` iOS UI feedback: "Trends page -
/// there are no filters on this page - use the same filters as
/// transactions"). Edits a local draft and only writes back to the bound
/// `filter` when the user taps Apply, so backing out (Cancel/swipe-to-
/// dismiss) never mutates the live list.
struct FilterSheet<F: FilterFields>: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.appDatabase) private var appDatabase

    @Binding var filter: F

    @State private var draft: F
    @State private var availableCategories: [String] = []
    @State private var availableAccounts: [String] = []
    @State private var availableTags: [String] = []

    /// Only `TransactionFilter` paginates; `TrendsBuilder.TrendsParams` has
    /// no `page` field, so resetting to page 1 on Apply is expressed as a
    /// closure the Transactions call site supplies instead of a protocol
    /// requirement every conforming type would otherwise need.
    var onApply: (inout F) -> Void = { _ in }

    init(filter: Binding<F>, onApply: @escaping (inout F) -> Void = { _ in }) {
        self._filter = filter
        self._draft = State(initialValue: filter.wrappedValue)
        self.onApply = onApply
    }

    var body: some View {
        NavigationStack {
            Form {
                searchSection
                dateSection
                categoriesSection
                tagsSection
                accountSection
                amountSection
                transfersSection
                clearSection
            }
            .navigationTitle("Filters")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Apply") {
                        onApply(&draft)
                        filter = draft
                        dismiss()
                    }
                }
            }
            .task { await loadPickerData() }
        }
    }

    // MARK: - Sections

    private var searchSection: some View {
        Section("Search") {
            TextField(
                "Description contains…",
                text: Binding(get: { draft.q ?? "" }, set: { draft.q = $0.isEmpty ? nil : $0 })
            )
        }
    }

    private var dateSection: some View {
        Section("Date range") {
            Picker("Preset", selection: presetSelection) {
                Text("Custom").tag(TransactionFilter.Preset?.none)
                ForEach(TransactionFilter.Preset.allCases) { preset in
                    Text(preset.label).tag(TransactionFilter.Preset?.some(preset))
                }
            }
            .pickerStyle(.menu)

            if draft.preset == nil {
                DatePicker(
                    "From",
                    selection: Binding(get: { draft.dateFrom ?? Date() }, set: { draft.dateFrom = $0 }),
                    displayedComponents: .date
                )
                DatePicker(
                    "To",
                    selection: Binding(get: { draft.dateTo ?? Date() }, set: { draft.dateTo = $0 }),
                    displayedComponents: .date
                )
                if draft.dateFrom != nil || draft.dateTo != nil {
                    Button("Clear dates", role: .destructive) {
                        draft.dateFrom = nil
                        draft.dateTo = nil
                    }
                }
            }
        }
    }

    private var presetSelection: Binding<TransactionFilter.Preset?> {
        Binding(
            get: { draft.preset },
            set: { newValue in
                draft.preset = newValue
                if newValue != nil {
                    draft.dateFrom = nil
                    draft.dateTo = nil
                }
            }
        )
    }

    private var categoriesSection: some View {
        Section("Categories") {
            Toggle("Uncategorized only", isOn: uncategorizedToggle)
            NavigationLink {
                CategoryPickerView(
                    categories: $draft.categories,
                    excludeCategories: $draft.excludeCategories,
                    availableCategories: availableCategories
                )
            } label: {
                HStack {
                    Text("Categories")
                    Spacer()
                    Text(categoriesSummary)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
        }
    }

    private var categoriesSummary: String {
        var parts: [String] = []
        if !draft.categories.isEmpty { parts.append("\(draft.categories.count) included") }
        if !draft.excludeCategories.isEmpty { parts.append("\(draft.excludeCategories.count) excluded") }
        return parts.isEmpty ? "Any" : parts.joined(separator: ", ")
    }

    private var uncategorizedToggle: Binding<Bool> {
        Binding(
            get: { draft.categories.contains(TransactionFilter.uncategorized) },
            set: { isOn in
                if isOn {
                    if !draft.categories.contains(TransactionFilter.uncategorized) {
                        draft.categories.append(TransactionFilter.uncategorized)
                    }
                } else {
                    draft.categories.removeAll { $0 == TransactionFilter.uncategorized }
                }
            }
        )
    }

    private var accountSection: some View {
        Section("Accounts") {
            ForEach(availableAccounts, id: \.self) { account in
                pickerRow(account, selection: $draft.accounts)
            }
        }
    }

    private var amountSection: some View {
        Section("Amount (absolute value)") {
            HStack {
                Text("Min")
                TextField("0", value: $draft.amountMin, format: .number)
                    .keyboardType(.decimalPad)
                    .multilineTextAlignment(.trailing)
            }
            HStack {
                Text("Max")
                TextField("∞", value: $draft.amountMax, format: .number)
                    .keyboardType(.decimalPad)
                    .multilineTextAlignment(.trailing)
            }
        }
    }

    private var tagsSection: some View {
        Section("Tags") {
            NavigationLink {
                TagPickerView(selected: $draft.tags, availableTags: availableTags)
            } label: {
                HStack {
                    Text("Tags")
                    Spacer()
                    Text(draft.tags.isEmpty ? "Any" : draft.tags.joined(separator: ", "))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
        }
    }

    private var transfersSection: some View {
        Section {
            Toggle("Include transfers", isOn: $draft.includeTransfers)
        } footer: {
            Text("Transactions whose category starts with or contains \"transfer\" are hidden by default.")
        }
    }

    private var clearSection: some View {
        Section {
            Button("Clear all filters", role: .destructive) {
                draft = F.empty()
            }
        }
    }

    // MARK: - Multi-select row

    private func pickerRow(_ value: String, selection: Binding<[String]>) -> some View {
        Button {
            if selection.wrappedValue.contains(value) {
                selection.wrappedValue.removeAll { $0 == value }
            } else {
                selection.wrappedValue.append(value)
            }
        } label: {
            HStack {
                Text(value)
                    .foregroundStyle(.primary)
                Spacer()
                if selection.wrappedValue.contains(value) {
                    Image(systemName: "checkmark")
                        .foregroundStyle(.tint)
                }
            }
        }
    }

    // MARK: - Data loading

    private func loadPickerData() async {
        guard let appDatabase else { return }
        do {
            async let categoriesTask = AppQueries.distinctEffectiveCategories(appDatabase: appDatabase)
            async let accountsTask = AppQueries.distinctAccounts(appDatabase: appDatabase)
            async let tagsTask = AppQueries.distinctTags(appDatabase: appDatabase)
            let (categories, accounts, tags) = try await (categoriesTask, accountsTask, tagsTask)
            availableCategories = categories
            availableAccounts = accounts
            availableTags = tags
        } catch {
            // Best-effort: pickers just stay empty if this fails.
        }
    }
}

#Preview {
    FilterSheet(filter: .constant(TransactionFilter()))
}
