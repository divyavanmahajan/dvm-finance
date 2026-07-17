import Foundation

/// Groups a flat, distinct category list into a one-level parent/children
/// tree by first-hyphen-segment, for the mobile category picker (`ios/docs/
/// plan.md` iOS UI feedback: "long list of categories... more mobile
/// friendly way"). Mirrors `TrendsBuilder.aggregate`'s own rollup
/// (`firstSegment`) exactly, so a category's place in this tree always
/// matches its place in the Trends matrix — kept here as a small public Kit
/// utility (rather than app-target code) since it's still pure data
/// shaping, not UI.
public enum CategoryTree {
    public struct Node: Identifiable, Equatable {
        /// The full category value this node selects — for a parent, this
        /// is the parent label itself, which `TransactionQuery.categoryCondition`
        /// matches as "this exact value OR any hyphen-child of it", so
        /// selecting a parent node already means "this category and everything
        /// under it".
        public var id: String { value }
        public var label: String
        public var value: String
        public var children: [Node]

        public init(label: String, value: String, children: [Node] = []) {
            self.label = label
            self.value = value
            self.children = children
        }

        public var hasChildren: Bool { !children.isEmpty }
    }

    /// `categories` must already be distinct (as returned by
    /// `AppQueries.distinctEffectiveCategories`/`distinctAccounts`-style
    /// queries); this does not itself deduplicate.
    public static func build(from categories: [String]) -> [Node] {
        var groups: [String: [String]] = [:]
        var order: [String] = []
        for cat in categories {
            let parent = firstSegment(cat)
            if groups[parent] == nil { order.append(parent) }
            groups[parent, default: []].append(cat)
        }
        return order.sorted { $0.lowercased() < $1.lowercased() }.map { parent in
            let members = (groups[parent] ?? []).sorted { $0.lowercased() < $1.lowercased() }
            if members == [parent] {
                return Node(label: parent, value: parent, children: [])
            }
            let children = members.map { Node(label: $0, value: $0, children: []) }
            return Node(label: parent, value: parent, children: children)
        }
    }

    private static func firstSegment(_ cat: String) -> String {
        guard let range = cat.range(of: CoreNormalize.categorySeparator) else { return cat }
        return String(cat[cat.startIndex..<range.lowerBound])
    }
}
