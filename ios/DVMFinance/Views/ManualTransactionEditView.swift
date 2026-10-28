import SwiftUI
import DVMFinanceKit

/// The create form and the edit form of a hand-entered transaction, as one
/// sheet. The screen mirrors the desktop forms of the capability
/// `manual-transactions`.
///
/// The form requires a date, an amount, and a description. It accepts an
/// optional category and optional tags. It refuses a form without a date,
/// without an amount, or with an amount of zero, and it writes nothing. The
/// view holds the typed values only; each rule lives in
/// `DVMFinanceKit.ManualTransactions`, per `ios/docs/plan.md` "Phase E":
/// keep the views thin.
struct ManualTransactionEditView: View {
    @Environment(\.appDatabase) private var appDatabase
    @Environment(\.dismiss) private var dismiss

    /// The row to change, or `nil` for a new row.
    let existing: TransactionRecord?
    /// Runs after a write, so that the list reads the database again.
    let onSaved: () async -> Void

    @State private var date = Date()
    @State private var amountText = ""
    @State private var descriptionText = ""
    @State private var category = ""
    @State private var tagList: [String] = []
    @State private var availableTags: [String] = []
    @State private var availableCategories: [String] = []
    @State private var errorMessage: String?
    @State private var isSaving = false
    @State private var didSeed = false

    private var isEditing: Bool { existing != nil }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    DatePicker("Date", selection: $date, displayedComponents: .date)
                    HStack {
                        Text("Amount")
                        Spacer()
                        TextField("-20.00", text: $amountText)
                            .keyboardType(.numbersAndPunctuation)
                            .multilineTextAlignment(.trailing)
                            .autocorrectionDisabled()
                    }
                    TextField("Description", text: $descriptionText)
                } header: {
                    Text("Payment")
                } footer: {
                    Text("Type a negative amount for a payment. "
                        + "Type a positive amount for money that you receive.")
                }

                Section("Category") {
                    TextField("e.g. groceries", text: $category)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    if !categorySuggestions.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 6) {
                                ForEach(categorySuggestions, id: \.self) { suggestion in
                                    Button { category = suggestion } label: {
                                        CategoryChip(category: suggestion)
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                            .padding(.vertical, 2)
                        }
                    }
                }

                Section("Tags") {
                    NavigationLink {
                        TagPickerView(selected: $tagList, availableTags: availableTags)
                    } label: {
                        if tagList.isEmpty {
                            Text("Add tags…").foregroundStyle(.secondary)
                        } else {
                            HStack(spacing: 6) { TagChips(tags: tagList.joined(separator: ", ")) }
                        }
                    }
                }

                Section {
                    Label(
                        "Give the withdrawal that funds your cash a transfer category. "
                            + "The withdrawal otherwise counts as spending, "
                            + "and these rows count the same money a second time.",
                        systemImage: "info.circle"
                    )
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                }

                if let errorMessage {
                    Section {
                        Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                            .foregroundStyle(Theme.expense)
                            .font(.subheadline)
                    }
                }
            }
            .navigationTitle(isEditing ? "Edit Cash Payment" : "New Cash Payment")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { Task { await save() } }
                        .disabled(isSaving)
                }
            }
            .task { await onFirstAppear() }
        }
    }

    private var categorySuggestions: [String] {
        let trimmed = category.trimmingCharacters(in: .whitespaces).lowercased()
        let base = trimmed.isEmpty
            ? availableCategories
            : availableCategories.filter { $0.lowercased().contains(trimmed) && $0.lowercased() != trimmed }
        return Array(base.prefix(10))
    }

    private func onFirstAppear() async {
        guard !didSeed else { return }
        didSeed = true
        if let existing {
            date = existing.transactiondate
            amountText = DisplayFormat.plainAmount(NSDecimalNumber(decimal: existing.amount).doubleValue)
            descriptionText = existing.description ?? ""
            category = existing.manualCategory ?? ""
            tagList = Self.splitTags(existing.manualTags)
        }
        guard let appDatabase else { return }
        availableTags = (try? await AppQueries.distinctTags(appDatabase: appDatabase)) ?? []
        availableCategories = (try? await AppQueries.distinctEffectiveCategories(appDatabase: appDatabase)) ?? []
    }

    private static func splitTags(_ value: String?) -> [String] {
        (value ?? "")
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
    }

    /// Reads the typed amount. A text that does not parse reads as no
    /// amount, so the Kit refuses the form and names the missing amount.
    private var typedAmount: Decimal? {
        let trimmed = amountText
            .trimmingCharacters(in: .whitespaces)
            .replacingOccurrences(of: ",", with: ".")
        guard !trimmed.isEmpty else { return nil }
        return Decimal(string: trimmed, locale: Locale(identifier: "en_US_POSIX"))
    }

    private func save() async {
        guard let appDatabase else { return }
        isSaving = true
        defer { isSaving = false }
        let input = ManualTransactions.Input(
            date: date,
            amount: typedAmount,
            description: descriptionText,
            category: category,
            tags: tagList.joined(separator: ", ")
        )
        do {
            if let existing {
                _ = try await AppQueries.editManualTransaction(
                    appDatabase: appDatabase, transactionId: existing.id, input: input)
            } else {
                _ = try await AppQueries.createManualTransaction(appDatabase: appDatabase, input: input)
            }
            await onSaved()
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
