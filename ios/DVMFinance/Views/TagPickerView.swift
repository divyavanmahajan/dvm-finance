import SwiftUI
import DVMFinanceKit

/// Reusable tag selector with type-ahead partial matching, used both by the
/// filter sheet (filter on tags) and the transaction detail screen (edit
/// manual tags). As the user types, `availableTags` are filtered to those
/// *containing* the query (case-insensitive) and shown as tappable
/// suggestions; the user can also commit a brand-new tag that doesn't exist
/// yet (manual tagging is free-form). Selected tags render as removable pills.
struct TagPickerView: View {
    /// The chosen tags, bound to the caller (filter `.tags` or a manual-tags draft).
    @Binding var selected: [String]
    /// Every distinct tag already present in the data, for suggestions.
    let availableTags: [String]
    /// When true, the field commits a typed value on return even if it's not
    /// an existing tag (manual tagging). The filter uses this too — you can
    /// filter on a tag substring that isn't a full stored tag.
    var allowsCustom = true

    @State private var query = ""
    @FocusState private var fieldFocused: Bool

    /// Suggestions: available tags that contain the query (or all, when the
    /// query is empty), excluding already-selected ones, capped for a tidy list.
    private var suggestions: [String] {
        let trimmed = query.trimmingCharacters(in: .whitespaces).lowercased()
        let notSelected = availableTags.filter { tag in
            !selected.contains { $0.caseInsensitiveCompare(tag) == .orderedSame }
        }
        let matches = trimmed.isEmpty
            ? notSelected
            : notSelected.filter { $0.lowercased().contains(trimmed) }
        return Array(matches.prefix(12))
    }

    private var canCommitCustom: Bool {
        let trimmed = query.trimmingCharacters(in: .whitespaces)
        guard allowsCustom, !trimmed.isEmpty else { return false }
        let alreadySelected = selected.contains { $0.caseInsensitiveCompare(trimmed) == .orderedSame }
        let isExistingSuggestion = suggestions.contains { $0.caseInsensitiveCompare(trimmed) == .orderedSame }
        return !alreadySelected && !isExistingSuggestion
    }

    var body: some View {
        List {
            if !selected.isEmpty {
                Section("Selected") {
                    ForEach(selected, id: \.self) { tag in
                        Button(role: .destructive) {
                            selected.removeAll { $0 == tag }
                        } label: {
                            HStack {
                                Text(tag).foregroundStyle(.primary)
                                Spacer()
                                Image(systemName: "xmark.circle.fill")
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }

            Section {
                HStack {
                    Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                    TextField("Type to search or add a tag", text: $query)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .focused($fieldFocused)
                        .onSubmit(commitQuery)
                }
                if canCommitCustom {
                    Button {
                        commitQuery()
                    } label: {
                        Label("Add “\(query.trimmingCharacters(in: .whitespaces))”", systemImage: "plus.circle.fill")
                    }
                }
            } header: {
                Text("Add tag")
            } footer: {
                if availableTags.isEmpty {
                    Text("No tags exist yet — type one to create it.")
                }
            }

            if !suggestions.isEmpty {
                Section(query.isEmpty ? "All tags" : "Matches") {
                    ForEach(suggestions, id: \.self) { tag in
                        Button {
                            select(tag)
                        } label: {
                            HStack {
                                Text(highlightedName(tag))
                                Spacer()
                                Image(systemName: "plus")
                                    .font(.caption)
                                    .foregroundStyle(Theme.accent)
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle("Tags")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if !selected.isEmpty {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Clear") { selected = [] }
                }
            }
        }
        .onAppear { fieldFocused = true }
    }

    private func select(_ tag: String) {
        if !selected.contains(where: { $0.caseInsensitiveCompare(tag) == .orderedSame }) {
            selected.append(tag)
        }
        query = ""
    }

    private func commitQuery() {
        let trimmed = query.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        // Prefer an exact existing-tag match (keeps stored casing); otherwise
        // add the typed value verbatim when custom tags are allowed.
        if let existing = availableTags.first(where: { $0.caseInsensitiveCompare(trimmed) == .orderedSame }) {
            select(existing)
        } else if allowsCustom {
            select(trimmed)
        }
    }

    /// Bolds the matched substring within a suggestion for quick scanning.
    private func highlightedName(_ tag: String) -> AttributedString {
        var attributed = AttributedString(tag)
        let trimmed = query.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty,
              let range = tag.range(of: trimmed, options: .caseInsensitive),
              let attributedRange = Range(range, in: attributed) else {
            return attributed
        }
        attributed[attributedRange].font = .body.weight(.semibold)
        attributed[attributedRange].foregroundColor = Theme.accent
        return attributed
    }
}

#Preview {
    NavigationStack {
        TagPickerView(
            selected: .constant(["Travel"]),
            availableTags: ["Travel", "Groceries", "Subscription", "Reimbursable", "Tax-deductible"]
        )
    }
}
