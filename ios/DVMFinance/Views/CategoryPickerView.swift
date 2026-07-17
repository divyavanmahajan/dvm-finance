import SwiftUI
import DVMFinanceKit

/// Full-screen hierarchical category picker, pushed from `FilterSheet`
/// (`ios/docs/plan.md` iOS UI feedback: "long list of categories... could
/// be a separate screen" + "option to select all matching categories
/// prefixed with that"). One shared screen edits both `categories` (include)
/// and `excludeCategories` via a segmented mode toggle, rather than two
/// separate push destinations — selecting a parent row adds the parent
/// label itself, which `TransactionQuery.categoryCondition` already matches
/// as "this value or any hyphen-child of it" server-side, so a parent
/// selection is a subtree selection with no extra query-layer work.
struct CategoryPickerView: View {
    enum Mode: String, CaseIterable, Identifiable {
        case include = "Include"
        case exclude = "Exclude"
        var id: String { rawValue }
    }

    @Binding var categories: [String]
    @Binding var excludeCategories: [String]
    let availableCategories: [String]

    @State private var mode: Mode = .include
    @State private var searchText = ""
    @State private var expandedParents: Set<String> = []

    private var tree: [CategoryTree.Node] {
        CategoryTree.build(from: availableCategories)
    }

    private var filteredTree: [CategoryTree.Node] {
        guard !searchText.isEmpty else { return tree }
        let needle = searchText.lowercased()
        return tree.compactMap { parent -> CategoryTree.Node? in
            if parent.label.lowercased().contains(needle) { return parent }
            let matchingChildren = parent.children.filter { $0.label.lowercased().contains(needle) }
            guard !matchingChildren.isEmpty else { return nil }
            return CategoryTree.Node(label: parent.label, value: parent.value, children: matchingChildren)
        }
    }

    private var activeSelection: Binding<[String]> {
        mode == .include ? $categories : $excludeCategories
    }

    var body: some View {
        List {
            Section {
                Picker("Mode", selection: $mode) {
                    ForEach(Mode.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
                .listRowInsets(EdgeInsets())
                .padding(.vertical, 4)
            }

            Section {
                ForEach(filteredTree) { parent in
                    parentRow(parent)
                    if parent.hasChildren, expandedParents.contains(parent.value) || !searchText.isEmpty {
                        ForEach(parent.children) { child in
                            childRow(child)
                        }
                    }
                }
            } footer: {
                Text("Selecting a category also matches every category beneath it.")
            }
        }
        .searchable(text: $searchText, prompt: "Search categories")
        .navigationTitle("Categories")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                if !activeSelection.wrappedValue.isEmpty {
                    Button("Clear \(mode.rawValue)") { activeSelection.wrappedValue = [] }
                }
            }
        }
    }

    private func parentRow(_ node: CategoryTree.Node) -> some View {
        HStack(spacing: 8) {
            if node.hasChildren {
                Button {
                    if expandedParents.contains(node.value) {
                        expandedParents.remove(node.value)
                    } else {
                        expandedParents.insert(node.value)
                    }
                } label: {
                    Image(systemName: expandedParents.contains(node.value) || !searchText.isEmpty
                        ? "chevron.down" : "chevron.right")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
            } else {
                Color.clear.frame(width: 12)
            }
            selectableRow(label: node.label, value: node.value, bold: true)
        }
    }

    private func childRow(_ node: CategoryTree.Node) -> some View {
        HStack(spacing: 8) {
            Color.clear.frame(width: 12)
            selectableRow(label: node.label, value: node.value, bold: false)
                .padding(.leading, 20)
        }
    }

    private func selectableRow(label: String, value: String, bold: Bool) -> some View {
        Button {
            toggle(value)
        } label: {
            HStack {
                Text(label)
                    .font(bold ? .body.weight(.semibold) : .body)
                    .foregroundStyle(.primary)
                Spacer()
                if activeSelection.wrappedValue.contains(value) {
                    Image(systemName: "checkmark")
                        .foregroundStyle(.tint)
                }
            }
        }
    }

    private func toggle(_ value: String) {
        if activeSelection.wrappedValue.contains(value) {
            activeSelection.wrappedValue.removeAll { $0 == value }
        } else {
            activeSelection.wrappedValue.append(value)
        }
    }
}

#Preview {
    NavigationStack {
        CategoryPickerView(
            categories: .constant(["food-groceries"]),
            excludeCategories: .constant([]),
            availableCategories: ["food-groceries", "food-restaurants", "education-books", "salary"]
        )
    }
}
