import SwiftUI
import CoreFoundation
import DVMFinanceKit

/// Read-only detail screen for a single transaction (`ios/docs/spec.md`
/// "UI" §1): every stored column, plus the parsed `description_structured`
/// key/values and a human label for `categorization_source` (the matching
/// rule, or "Manual").
struct TransactionDetailView: View {
    @Environment(\.appDatabase) private var appDatabase
    let transactionId: String

    @State private var transaction: TransactionRecord?
    @State private var rule: CategorizationRuleRecord?
    @State private var structuredFields: [(key: String, value: String)] = []
    @State private var loadErrorMessage: String?

    // Manual edit state. `isEditing` swaps the Categorization section from the
    // read-only rows to editable fields; the draft strings are seeded from the
    // current manual values when editing begins. Writes go through
    // `AppQueries.setManual*`/`clearManual*` (ports of
    // `api/transactions.py`), which pin `categorization_source = "manual"` and
    // stamp `updated_at` so the change reaches the next delta snapshot.
    @State private var isEditing = false
    @State private var draftManualCategory = ""
    @State private var draftManualTagList: [String] = []
    @State private var availableTags: [String] = []
    @State private var availableCategories: [String] = []
    @State private var saveErrorMessage: String?

    var body: some View {
        Group {
            if let transaction {
                List {
                    Section("Transaction") {
                        labeledRow("Description", transaction.description?.isEmpty == false ? transaction.description! : "—")
                        labeledRow("Amount", DisplayFormat.currency(transaction.amount, code: transaction.currency))
                        labeledRow("Date", DisplayFormat.mediumDate.string(from: transaction.transactiondate))
                        if let valuedate = transaction.valuedate {
                            labeledRow("Value date", DisplayFormat.mediumDate.string(from: valuedate))
                        }
                        labeledRow("Account", transaction.accountNumber)
                        labeledRow("Currency", transaction.currency)
                    }

                    Section("Categorization") {
                        HStack {
                            Text("Effective category").foregroundStyle(.secondary)
                            Spacer(minLength: 12)
                            CategoryChip(category: TransactionQuery.effectiveCategory(transaction))
                        }
                        .font(.subheadline)
                        if let tags = TransactionQuery.effectiveTags(transaction), !tags.isEmpty {
                            HStack(alignment: .top) {
                                Text("Effective tags").foregroundStyle(.secondary)
                                Spacer(minLength: 12)
                                HStack(spacing: 6) { TagChips(tags: tags) }
                            }
                            .font(.subheadline)
                        }
                        labeledRow("Raw category", transaction.category ?? "—")
                        labeledRow("Raw tags", transaction.tags ?? "—")

                        if isEditing {
                            editableManualFields(transaction)
                        } else {
                            labeledRow("Manual category", transaction.manualCategory ?? "—")
                            labeledRow("Manual tags", transaction.manualTags ?? "—")
                        }

                        labeledRow("Categorized by", categorizationSourceLabel)
                        labeledRow("Manually categorized", TransactionQuery.isManual(transaction) ? "Yes" : "No")

                        if let saveErrorMessage {
                            Text(saveErrorMessage).foregroundStyle(.red).font(.subheadline)
                        }
                    }

                    Section("Source") {
                        labeledRow("Source file", transaction.sourceFile ?? "—")
                        if let sourceLine = transaction.sourceLine {
                            labeledRow("Source line", String(sourceLine))
                        }
                        labeledRow("Mutation code", transaction.mutationcode ?? "—")
                        labeledRow("Type code", transaction.transactionTypeCode ?? "—")
                        labeledRow("Reference", transaction.transactionReference ?? "—")
                        labeledRow(
                            "Start saldo",
                            transaction.startsaldo.map { DisplayFormat.currency($0, code: transaction.currency) } ?? "—"
                        )
                        labeledRow(
                            "End saldo",
                            transaction.endsaldo.map { DisplayFormat.currency($0, code: transaction.currency) } ?? "—"
                        )
                        labeledRow("Hash", transaction.transactionHash ?? "—")
                        labeledRow("Id", transaction.id)
                    }

                    if !structuredFields.isEmpty {
                        Section("Structured description") {
                            ForEach(structuredFields, id: \.key) { field in
                                labeledRow(field.key, field.value)
                            }
                        }
                    }
                }
                .listStyle(.insetGrouped)
            } else if let loadErrorMessage {
                ContentUnavailableView("Not Found", systemImage: "questionmark.circle", description: Text(loadErrorMessage))
            } else {
                ProgressView()
            }
        }
        .navigationTitle("Transaction")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if transaction != nil {
                ToolbarItem(placement: .primaryAction) {
                    Button(isEditing ? "Done" : "Edit") {
                        if isEditing {
                            isEditing = false
                        } else {
                            beginEditing()
                        }
                    }
                }
            }
        }
        .task { await load() }
    }

    /// Editable manual category/tags plus a per-field "clear (restore rule)"
    /// action. Category is normalized on save (`CoreNormalize.normalizeCategory`
    /// via the Kit); tags keep their case (`set_manual_tags` semantics).
    @ViewBuilder
    private func editableManualFields(_ transaction: TransactionRecord) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Manual category").foregroundStyle(.secondary).font(.subheadline)
            TextField("Category (e.g. fixed-insurance)", text: $draftManualCategory)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .onSubmit { Task { await saveManualCategory() } }
            if !categorySuggestions.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(categorySuggestions, id: \.self) { suggestion in
                            Button { draftManualCategory = suggestion } label: {
                                CategoryChip(category: suggestion)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.vertical, 2)
                }
            }
            HStack {
                Button("Save category") { Task { await saveManualCategory() } }
                    .buttonStyle(.borderless)
                Spacer()
                if transaction.manualCategory != nil {
                    Button("Clear", role: .destructive) { Task { await clearCategory() } }
                        .buttonStyle(.borderless)
                }
            }
            .font(.subheadline)
        }

        VStack(alignment: .leading, spacing: 6) {
            Text("Manual tags").foregroundStyle(.secondary).font(.subheadline)
            NavigationLink {
                TagPickerView(selected: $draftManualTagList, availableTags: availableTags)
            } label: {
                HStack(spacing: 6) {
                    if draftManualTagList.isEmpty {
                        Text("Add tags…").foregroundStyle(.secondary)
                    } else {
                        HStack(spacing: 6) { TagChips(tags: draftManualTagList.joined(separator: ", ")) }
                    }
                    Spacer()
                }
            }
            HStack {
                Button("Save tags") { Task { await saveManualTags() } }
                    .buttonStyle(.borderless)
                Spacer()
                if transaction.manualTags != nil {
                    Button("Clear", role: .destructive) { Task { await clearTags() } }
                        .buttonStyle(.borderless)
                }
            }
            .font(.subheadline)
        }
    }

    private func beginEditing() {
        draftManualCategory = transaction?.manualCategory ?? ""
        draftManualTagList = Self.splitTags(transaction?.manualTags)
        saveErrorMessage = nil
        isEditing = true
    }

    /// Effective-category values matching what's currently typed, for quick
    /// one-tap manual categorization (partial, case-insensitive contains).
    private var categorySuggestions: [String] {
        let trimmed = draftManualCategory.trimmingCharacters(in: .whitespaces).lowercased()
        let base = trimmed.isEmpty
            ? availableCategories
            : availableCategories.filter { $0.lowercased().contains(trimmed) && $0.lowercased() != trimmed }
        return Array(base.prefix(10))
    }

    private static func splitTags(_ value: String?) -> [String] {
        (value ?? "")
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
    }

    private func saveManualCategory() async {
        guard let appDatabase else { return }
        do {
            let updated = try await AppQueries.setManualCategory(
                appDatabase: appDatabase, transactionId: transactionId, manualCategory: draftManualCategory)
            applyUpdated(updated)
        } catch {
            saveErrorMessage = "Couldn't save category: \(error.localizedDescription)"
        }
    }

    private func saveManualTags() async {
        guard let appDatabase else { return }
        do {
            let updated = try await AppQueries.setManualTags(
                appDatabase: appDatabase, transactionId: transactionId,
                manualTags: draftManualTagList.joined(separator: ", "))
            applyUpdated(updated)
        } catch {
            saveErrorMessage = "Couldn't save tags: \(error.localizedDescription)"
        }
    }

    private func clearCategory() async {
        guard let appDatabase else { return }
        do {
            let updated = try await AppQueries.clearManualCategory(
                appDatabase: appDatabase, transactionId: transactionId)
            applyUpdated(updated)
        } catch {
            saveErrorMessage = "Couldn't clear category: \(error.localizedDescription)"
        }
    }

    private func clearTags() async {
        guard let appDatabase else { return }
        do {
            let updated = try await AppQueries.clearManualTags(
                appDatabase: appDatabase, transactionId: transactionId)
            applyUpdated(updated)
        } catch {
            saveErrorMessage = "Couldn't clear tags: \(error.localizedDescription)"
        }
    }

    /// Reflects a mutation's returned record back into the view and re-seeds
    /// the draft fields, so the read-only rows and the edit fields stay in
    /// sync without a full reload.
    private func applyUpdated(_ updated: TransactionRecord) {
        transaction = updated
        draftManualCategory = updated.manualCategory ?? ""
        draftManualTagList = Self.splitTags(updated.manualTags)
        saveErrorMessage = nil
    }

    private var categorizationSourceLabel: String {
        guard let source = transaction?.categorizationSource, !source.isEmpty else { return "Uncategorized" }
        if source == Categorizer.manualSource { return "Manual" }
        if let ruleId = Int64(source) {
            if let rule {
                return "Rule #\(ruleId) — \(rule.matchPattern) \"\(rule.matchValue)\""
            }
            return "Rule #\(ruleId)"
        }
        return source
    }

    private func labeledRow(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top) {
            Text(label)
                .foregroundStyle(.secondary)
            Spacer(minLength: 12)
            Text(value)
                .multilineTextAlignment(.trailing)
        }
        .font(.subheadline)
    }

    private func load() async {
        guard let appDatabase else { return }
        do {
            guard let detail = try await AppQueries.transactionDetail(appDatabase: appDatabase, transactionId: transactionId) else {
                loadErrorMessage = "This transaction no longer exists."
                return
            }
            transaction = detail.transaction
            rule = detail.matchedRule
            structuredFields = Self.parseStructuredFields(detail.transaction.descriptionStructured)
            availableTags = (try? await AppQueries.distinctTags(appDatabase: appDatabase)) ?? []
            availableCategories = (try? await AppQueries.distinctEffectiveCategories(appDatabase: appDatabase)) ?? []
        } catch {
            loadErrorMessage = "Couldn't load this transaction: \(error.localizedDescription)"
        }
    }

    private static func parseStructuredFields(_ json: String?) -> [(key: String, value: String)] {
        guard let json, let data = json.data(using: .utf8) else { return [] }
        guard let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { return [] }
        return object.keys.sorted().map { key in (key: key, value: render(object[key])) }
    }

    private static func render(_ value: Any?) -> String {
        guard let value, !(value is NSNull) else { return "—" }
        if let string = value as? String { return string }
        if let number = value as? NSNumber {
            if CFGetTypeID(number) == CFBooleanGetTypeID() {
                return number.boolValue ? "true" : "false"
            }
            return number.stringValue
        }
        return "\(value)"
    }
}

#Preview {
    NavigationStack {
        TransactionDetailView(transactionId: "preview")
    }
}
