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
                        labeledRow("Effective category", TransactionQuery.effectiveCategory(transaction) ?? "Uncategorized")
                        labeledRow("Effective tags", TransactionQuery.effectiveTags(transaction) ?? "—")
                        labeledRow("Raw category", transaction.category ?? "—")
                        labeledRow("Manual category", transaction.manualCategory ?? "—")
                        labeledRow("Raw tags", transaction.tags ?? "—")
                        labeledRow("Manual tags", transaction.manualTags ?? "—")
                        labeledRow("Categorized by", categorizationSourceLabel)
                        labeledRow("Manually categorized", TransactionQuery.isManual(transaction) ? "Yes" : "No")
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
        .task { await load() }
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
