import SwiftUI
import DVMFinanceKit

/// Add / edit form for a single budget, presented as a sheet from
/// `BudgetsView`. Ports the desktop "Add budget" / "Edit budget" forms
/// (`api/budgets.py`), including the live "recent average" hint below the
/// amount field and category suggestions drawn from observed spending.
struct BudgetEditView: View {
    @Environment(\.appDatabase) private var appDatabase
    @Environment(\.dismiss) private var dismiss

    /// The row being edited, or `nil` when adding a new budget.
    let existing: BudgetReport.Row?
    /// The period a *new* budget defaults to — the active Budgets tab
    /// (Monthly/Yearly). Ignored when editing (the row's own period wins).
    var defaultPeriod: BudgetReport.Period = .month
    /// Called after a successful save so the list can refresh.
    let onSaved: () async -> Void

    @State private var category = ""
    @State private var amount = ""
    @State private var period: BudgetReport.Period = .month
    @State private var didInitPeriod = false
    @State private var useStartDate = false
    @State private var startDate = Date()
    @State private var useEndDate = false
    @State private var endDate = Date()
    @State private var notes = ""

    @State private var suggestions: [String] = []
    @State private var averageHint: Double?
    @State private var errorMessage: String?
    @State private var isSaving = false

    private var isEditing: Bool { existing != nil }

    private var matchingSuggestions: [String] {
        let trimmed = category.trimmingCharacters(in: .whitespaces).lowercased()
        let base = trimmed.isEmpty ? suggestions : suggestions.filter { $0.contains(trimmed) }
        return Array(base.filter { $0 != trimmed }.prefix(8))
    }

    var body: some View {
        NavigationStack {
            Form {
                categorySection
                amountSection
                periodSection
                validitySection
                notesSection
                if let errorMessage {
                    Section {
                        Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                            .foregroundStyle(Theme.expense)
                            .font(.subheadline)
                    }
                }
            }
            .navigationTitle(isEditing ? "Edit Budget" : "New Budget")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { Task { await save() } }
                        .disabled(isSaving || category.trimmingCharacters(in: .whitespaces).isEmpty || amount.isEmpty)
                }
            }
            .task { await onFirstAppear() }
            .task(id: category) { await refreshHint() }
        }
    }

    // MARK: - Sections

    private var categorySection: some View {
        Section("Category") {
            TextField("e.g. groceries", text: $category)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
            if !matchingSuggestions.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(matchingSuggestions, id: \.self) { suggestion in
                            Button {
                                category = suggestion
                            } label: {
                                Text(suggestion)
                                    .font(.caption.weight(.medium))
                                    .padding(.horizontal, 10)
                                    .padding(.vertical, 5)
                                    .background(Capsule().fill(Theme.accent.opacity(0.12)))
                                    .foregroundStyle(Theme.accent)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.vertical, 2)
                }
                .listRowInsets(EdgeInsets(top: 4, leading: 16, bottom: 8, trailing: 8))
            }
        }
    }

    private var amountSection: some View {
        Section {
            HStack {
                Text("Amount")
                Spacer()
                TextField("0.00", text: $amount)
                    .keyboardType(.decimalPad)
                    .multilineTextAlignment(.trailing)
                    .monospacedDigit()
            }
        } footer: {
            if let averageHint, averageHint > 0 {
                HStack(spacing: 6) {
                    Image(systemName: "chart.bar.xaxis")
                    Text("Recent average \(DisplayFormat.currency(averageHint)) (last \(BudgetReport.defaultAverageMonths) months).")
                    Button("Use") { amount = String(format: "%.2f", averageHint) }
                        .font(.caption.weight(.semibold))
                }
                .font(.caption)
            }
        }
    }

    private var periodSection: some View {
        Section("Period") {
            Picker("Period", selection: $period) {
                ForEach(BudgetReport.Period.allCases) { p in
                    Text(p.label).tag(p)
                }
            }
            .pickerStyle(.segmented)
        }
    }

    private var validitySection: some View {
        Section {
            Toggle("Active from", isOn: $useStartDate.animation())
            if useStartDate {
                DatePicker("From", selection: $startDate, displayedComponents: .date)
            }
            Toggle("Active until", isOn: $useEndDate.animation())
            if useEndDate {
                DatePicker("Until", selection: $endDate, displayedComponents: .date)
            }
        } header: {
            Text("Validity (optional)")
        } footer: {
            Text("Limit which period windows this budget applies to. Leave off to always apply.")
        }
    }

    private var notesSection: some View {
        Section("Notes (optional)") {
            TextField("Notes", text: $notes, axis: .vertical)
                .lineLimit(1...4)
        }
    }

    // MARK: - Data

    private func onFirstAppear() async {
        if let existing {
            category = existing.category
            amount = String(format: "%.2f", existing.budget)
            period = existing.period
            if let start = existing.startDate { useStartDate = true; startDate = start }
            if let end = existing.endDate { useEndDate = true; endDate = end }
            notes = existing.notes ?? ""
        } else if !didInitPeriod {
            // New budget: default to the active tab's period (once, so the
            // user's later picker choice isn't clobbered by a re-run task).
            period = defaultPeriod
            didInitPeriod = true
        }
        guard let appDatabase else { return }
        suggestions = (try? await AppQueries.budgetCategorySuggestions(appDatabase: appDatabase)) ?? []
    }

    private func refreshHint() async {
        guard let appDatabase else { return }
        // Debounce keystrokes; SwiftUI cancels the prior task on each change.
        try? await Task.sleep(nanoseconds: 250_000_000)
        if Task.isCancelled { return }
        averageHint = try? await AppQueries.budgetAverageHint(appDatabase: appDatabase, category: category)
    }

    private func save() async {
        guard let appDatabase else { return }
        errorMessage = nil
        guard let decimalAmount = Decimal(string: amount.replacingOccurrences(of: ",", with: ".")) else {
            errorMessage = "Enter a valid amount."
            return
        }
        isSaving = true
        defer { isSaving = false }
        do {
            let input = try BudgetMutations.makeInput(
                category: category,
                amount: decimalAmount,
                period: period,
                startDate: useStartDate ? startDate : nil,
                endDate: useEndDate ? endDate : nil,
                notes: notes
            )
            if let existing {
                try await AppQueries.updateBudget(appDatabase: appDatabase, budgetId: existing.budgetId, input: input)
            } else {
                try await AppQueries.createBudget(appDatabase: appDatabase, input: input)
            }
            await onSaved()
            dismiss()
        } catch let error as BudgetMutations.BudgetError {
            errorMessage = message(for: error)
        } catch {
            errorMessage = "Couldn't save budget: \(error.localizedDescription)"
        }
    }

    private func message(for error: BudgetMutations.BudgetError) -> String {
        switch error {
        case .emptyCategory: return "Category is required."
        case .invalidAmount: return "Enter a valid amount."
        case let .duplicate(category, period): return "A \(period) budget for “\(category)” already exists."
        case .notFound: return "This budget no longer exists."
        }
    }
}

#Preview {
    BudgetEditView(existing: nil) {}
}
