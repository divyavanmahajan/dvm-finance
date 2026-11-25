import SwiftUI
import DVMFinanceKit

/// Shared visual language for the app target — a small design system so the
/// screens read as one product rather than stock `Form`/`List` defaults.
/// View-layer only (colors, chips, badges); no business logic, per
/// `ios/docs/plan.md` "Phase E".
enum Theme {
    /// App accent — a calm teal that reads as neither "spend red" nor
    /// "income green", so it stays legible next to the amount colors.
    static let accent = Color(red: 0.10, green: 0.52, blue: 0.55)

    /// Money-in / money-out semantic colors. Expenses (negative amounts) use
    /// the primary label color by default so a list of spending isn't a wall
    /// of red; only income is tinted, plus a muted red reserved for detail/
    /// emphasis contexts.
    static let income = Color(red: 0.16, green: 0.55, blue: 0.36)
    static let expense = Color(red: 0.78, green: 0.24, blue: 0.24)

    /// Budget status colors (over / near / under), used by the badge and bar.
    static func statusColor(_ status: BudgetReport.Status) -> Color {
        switch status {
        case .over: return expense
        case .near: return Color(red: 0.85, green: 0.60, blue: 0.13)
        case .under: return income
        }
    }

    /// A stable, pleasant color for a category derived from its top-level
    /// (first hyphen segment), so the same category always looks the same and
    /// related sub-categories share a family — a cheap way to make dense
    /// lists scannable without a hand-maintained palette.
    static func categoryColor(_ category: String?) -> Color {
        guard let category, !category.isEmpty else { return Color.secondary }
        let top = category.split(separator: "-", maxSplits: 1).first.map(String.init) ?? category
        var hash: UInt64 = 5381
        for byte in top.lowercased().utf8 { hash = (hash &* 33) &+ UInt64(byte) }
        let hue = Double(hash % 360) / 360.0
        return Color(hue: hue, saturation: 0.55, brightness: 0.72)
    }
}

// MARK: - Reusable views

/// A compact, colored category pill used across the transactions list and
/// detail screen so a category is recognizable at a glance.
struct CategoryChip: View {
    let category: String?
    var uncategorizedLabel = "Uncategorized"
    /// `true` lets a long name wrap onto more lines. `false` keeps one line,
    /// for a picker or a budget row.
    var wraps = false

    var body: some View {
        let isUncategorized = (category?.isEmpty ?? true)
        let color = isUncategorized ? Color.secondary : Theme.categoryColor(category)
        Text(isUncategorized ? uncategorizedLabel : category!)
            .font(.caption.weight(.medium))
            .lineLimit(wraps ? nil : 1)
            .fixedSize(horizontal: false, vertical: wraps)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(
                // On one line this looks like a capsule. On two lines it
                // stays a tidy rounded rectangle.
                RoundedRectangle(cornerRadius: 10, style: .continuous).fill(color.opacity(0.15))
            )
            .foregroundStyle(color)
    }
}

/// A small tag pill (outlined, neutral) for the comma-joined effective tags.
struct TagChips: View {
    let tags: String
    /// `true` lets a long tag wrap onto more lines.
    var wraps = false

    private var parts: [String] {
        tags.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
    }

    var body: some View {
        ForEach(parts, id: \.self) { tag in
            Text(tag)
                .font(.caption2.weight(.medium))
                .lineLimit(wraps ? nil : 1)
                .fixedSize(horizontal: false, vertical: wraps)
                .padding(.horizontal, 7)
                .padding(.vertical, 2)
                .overlay(
                    RoundedRectangle(cornerRadius: 9, style: .continuous)
                        .stroke(Color.secondary.opacity(0.35), lineWidth: 1)
                )
                .foregroundStyle(.secondary)
        }
    }
}

/// Puts its subviews in rows from the leading edge, and starts a new row when
/// the next subview does not fit. A subview that is wider than the row gets
/// the full row width, so that a wrapping chip can wrap its text.
struct FlowLayout: Layout {
    var spacing: CGFloat = 6
    var lineSpacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        let rows = arrange(subviews, width: width)
        let height = rows.map(\.height).reduce(0, +) + lineSpacing * CGFloat(max(rows.count - 1, 0))
        let usedWidth = rows.map(\.width).max() ?? 0
        return CGSize(width: proposal.width ?? usedWidth, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for row in arrange(subviews, width: bounds.width) {
            var x = bounds.minX
            for item in row.items {
                subviews[item.index].place(
                    at: CGPoint(x: x, y: y),
                    proposal: ProposedViewSize(width: item.size.width, height: item.size.height)
                )
                x += item.size.width + spacing
            }
            y += row.height + lineSpacing
        }
    }

    private struct Row {
        var items: [(index: Int, size: CGSize)] = []
        var width: CGFloat = 0
        var height: CGFloat = 0
    }

    private func arrange(_ subviews: Subviews, width: CGFloat) -> [Row] {
        var rows: [Row] = []
        var row = Row()
        for index in subviews.indices {
            var size = subviews[index].sizeThatFits(.unspecified)
            if size.width > width {
                // Too wide for any row: give it the full width, so it wraps.
                size = subviews[index].sizeThatFits(ProposedViewSize(width: width, height: nil))
                size.width = min(size.width, width)
            }
            let needed = row.items.isEmpty ? size.width : row.width + spacing + size.width
            if !row.items.isEmpty && needed > width {
                rows.append(row)
                row = Row()
            }
            row.width = row.items.isEmpty ? size.width : row.width + spacing + size.width
            row.height = max(row.height, size.height)
            row.items.append((index, size))
        }
        if !row.items.isEmpty { rows.append(row) }
        return rows
    }
}
