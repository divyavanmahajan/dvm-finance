import SwiftUI
import UIKit
import DVMFinanceKit

/// The Trends tab (`ios/docs/spec.md` "UI" §2): a month/year × effective-category
/// matrix, hyphen-rollup parents expandable to their exact children, tapping
/// any cell or row total pushes `TransactionsListView` prefilled with the
/// equivalent `TransactionFilter` so the pushed list sums exactly to what was
/// tapped (`TrendsBuilder.transactionFilter(for:period:params:)`).
///
/// All aggregation lives in `DVMFinanceKit.TrendsBuilder`; this view only
/// holds UI state (expanded rows, granularity/account/transfers pickers) and
/// renders the table it's handed.
struct TrendsView: View {
    @Environment(\.appDatabase) private var appDatabase

    @State private var params = TrendsBuilder.TrendsParams()
    @State private var table: TrendsBuilder.TrendsTable?
    @State private var expandedParents: Set<String> = []
    /// `true` after the user taps the "Category" header. The category column
    /// then stays wide during a horizontal scroll (design D2a).
    @State private var keepCategoryWide = false
    /// The key of the category cell whose full name the popover shows (see
    /// `cellKey`), or `nil` when no popover shows.
    @State private var fullNameCellKey: String?
    /// The horizontal offset of the value columns. The pinned header strip
    /// moves by this amount, so each month header stays above its column.
    @State private var horizontalOffset: CGFloat = 0
    @State private var availableAccounts: [String] = []
    @State private var loadErrorMessage: String?
    @State private var showAccountPicker = false
    @State private var showFilterSheet = false
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    /// `true` after the user scrolls the value columns more than
    /// `narrowAfterOffset` points to the right. The category column is then
    /// narrow (design D2).
    @State private var isCategoryColumnNarrow = false
    /// The width of the matrix. The wide category column is at most half of
    /// it.
    @State private var matrixWidth: CGFloat = 0

    var body: some View {
        NavigationStack {
            Group {
                if let table {
                    VStack(spacing: 0) {
                        quickRangeChips
                        matrix(table)
                    }
                } else if let loadErrorMessage {
                    ContentUnavailableView(
                        "Couldn't Load Trends",
                        systemImage: "exclamationmark.triangle",
                        description: Text(loadErrorMessage)
                    )
                } else {
                    ProgressView()
                }
            }
            .navigationTitle("Trends")
            .toolbar {
                ToolbarItem(placement: .principal) {
                    Picker("Granularity", selection: $params.granularity) {
                        Text("Month").tag(TrendsBuilder.TrendsParams.Granularity.month)
                        Text("Year").tag(TrendsBuilder.TrendsParams.Granularity.year)
                    }
                    .pickerStyle(.segmented)
                    .frame(width: 160)
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        showFilterSheet = true
                    } label: {
                        Label("Filter", systemImage: "line.3.horizontal.decrease.circle")
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        showAccountPicker = true
                    } label: {
                        Label("Accounts", systemImage: "creditcard")
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        params.includeTransfers.toggle()
                    } label: {
                        Image(systemName: params.includeTransfers
                            ? "arrow.left.arrow.right.circle.fill"
                            : "arrow.left.arrow.right.circle")
                    }
                    .accessibilityLabel(params.includeTransfers ? "Transfers included" : "Transfers hidden")
                }
            }
            .sheet(isPresented: $showAccountPicker) {
                accountPickerSheet
            }
            .sheet(isPresented: $showFilterSheet) {
                FilterSheet(filter: $params)
            }
            .navigationDestination(for: TrendsCellRoute.self) { route in
                TransactionsListView(initialFilter: route.filter)
            }
            .task(id: params) {
                await reload()
            }
        }
    }

    // MARK: - Quick range chips

    /// Always-visible rolling-window shortcuts (`ios/docs/plan.md` iOS UI
    /// feedback: "no way to quick select the last few months... should be
    /// easily accessible" — not buried inside the filter sheet). The 3/6/12
    /// month chips end today, so the in-progress current month (excluded
    /// from the last-12-*full*-months default) is included; "12mo (full)"
    /// keeps that default reachable by name once a chip has been tapped.
    private var quickRangeChips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(TrendsBuilder.TrendsParams.QuickRange.allCases) { range in
                    quickRangeChip(range)
                }
                if params.quickRange != nil || params.preset != nil || params.dateFrom != nil || params.dateTo != nil {
                    Button {
                        params.quickRange = nil
                        params.preset = nil
                        params.dateFrom = nil
                        params.dateTo = nil
                    } label: {
                        Text("Default")
                            .font(.caption)
                    }
                    .buttonStyle(.bordered)
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
        }
    }

    private func quickRangeChip(_ range: TrendsBuilder.TrendsParams.QuickRange) -> some View {
        let isActive = params.quickRange == range
        return Button {
            params.quickRange = range
            params.preset = nil
            params.dateFrom = nil
            params.dateTo = nil
        } label: {
            Text(range.label)
                .font(.caption.weight(isActive ? .semibold : .regular))
        }
        .buttonStyle(.bordered)
        .tint(isActive ? .accentColor : .secondary)
    }

    // MARK: - Matrix (frozen category column + horizontally-scrolling value columns)

    /// The category column becomes narrow when the horizontal offset is more
    /// than `narrowAfterOffset`. It becomes wide again only when the offset is
    /// less than `wideBeforeOffset`. The gap between the two values stops a
    /// wobble at the start position, where the scroll view bounces.
    private static let narrowAfterOffset: CGFloat = 24
    private static let wideBeforeOffset: CGFloat = 4
    /// The name of the coordinate space of the horizontal `ScrollView`.
    private static let valueScrollSpace = "trendsValueScroll"
    /// The width of the label area of the narrow category column. The
    /// padding comes on top of it.
    private static let narrowLabelWidth: CGFloat = 96
    /// The gap on each side of a value.
    private static let valueGap: CGFloat = 6
    /// The leading padding of a top-level row and of a child row, and the
    /// trailing padding of each row of the category column.
    private static let parentIndent: CGFloat = 8
    private static let childIndent: CGFloat = 20
    private static let categoryTrailingPadding: CGFloat = 8
    /// The space between the chevron and the label.
    private static let chevronSpacing: CGFloat = 4

    /// The sizes of one matrix, measured from its text (design D2). The app
    /// measures with `UIFont` at the size of the caption text style, so
    /// Dynamic Type changes each size.
    private struct MatrixMetrics {
        /// The width of each value column, gaps included.
        var valueWidth: CGFloat
        /// The width of the category column at rest, padding included.
        var wideCategoryWidth: CGFloat
        /// The width of the category column after a scroll, padding included.
        var narrowCategoryWidth: CGFloat
        /// The height of each body row and of the totals row.
        var rowHeight: CGFloat
        /// The height of the header row: two lines of text.
        var headerHeight: CGFloat
    }

    /// The month and the year of a month period ("Oct 2026"), on two lines.
    /// A year period ("2026") has one line.
    private static func headerLines(_ period: TrendsBuilder.Period) -> [String] {
        period.label.split(separator: " ").map(String.init)
    }

    private func metrics(
        _ table: TrendsBuilder.TrendsTable,
        rows: [(row: TrendsBuilder.TrendRow, isChild: Bool)]
    ) -> MatrixMetrics {
        let traits = UITraitCollection(preferredContentSizeCategory: UIContentSizeCategory(dynamicTypeSize))
        let caption = UIFont.preferredFont(forTextStyle: .caption1, compatibleWith: traits)
        let caption2 = UIFont.preferredFont(forTextStyle: .caption2, compatibleWith: traits)
        let size = caption.pointSize
        // The bold monospaced-digit font is the widest variant that a value
        // cell uses, so it is a safe upper bound for each value.
        let valueFont = UIFont.monospacedDigitSystemFont(ofSize: size, weight: .bold)
        let labelBold = UIFont.systemFont(ofSize: size, weight: .bold)
        let labelRegular = UIFont.systemFont(ofSize: size, weight: .regular)

        func width(_ text: String, _ font: UIFont) -> CGFloat {
            ceil((text as NSString).size(withAttributes: [.font: font]).width)
        }

        // Value columns: each cell, each total, and each header line.
        var values: [String] = ["—", "Total"]
        for period in table.periods {
            values.append(contentsOf: Self.headerLines(period))
            values.append(DisplayFormat.compactAmount(table.columnTotals[period.key] ?? 0))
        }
        values.append(DisplayFormat.compactAmount(table.grandTotal))
        for entry in rows {
            values.append(DisplayFormat.compactAmount(entry.row.total))
            for value in entry.row.cells.values where value != 0 {
                values.append(DisplayFormat.compactAmount(value))
            }
        }
        let widestValue = values.map { width($0, valueFont) }.max() ?? 0
        let valueWidth = widestValue + 2 * Self.valueGap

        // Category column: the longest visible label, with the chevron, the
        // indent, and the padding.
        let symbolConfiguration = UIImage.SymbolConfiguration(font: caption2)
        let chevronWidth = ["chevron.right", "chevron.down"]
            .compactMap { UIImage(systemName: $0, withConfiguration: symbolConfiguration)?.size.width }
            .max().map { ceil($0) + Self.chevronSpacing } ?? caption2.pointSize + Self.chevronSpacing
        var widestCategory = max(width("Category", labelBold), width("Total", labelBold)) + Self.parentIndent
        for entry in rows {
            let font = entry.isChild ? labelRegular : labelBold
            var rowWidth = width(entry.row.label, font)
            rowWidth += entry.isChild ? Self.childIndent : Self.parentIndent
            if entry.row.hasChildren { rowWidth += chevronWidth }
            widestCategory = max(widestCategory, rowWidth)
        }
        widestCategory += Self.categoryTrailingPadding
        let narrowCategoryWidth = Self.narrowLabelWidth + Self.parentIndent
        let maximum = matrixWidth > 0 ? floor(matrixWidth / 2) : 200
        let wideCategoryWidth = max(narrowCategoryWidth, min(ceil(widestCategory), maximum))

        let lineHeight = ceil(max(caption.lineHeight, labelBold.lineHeight))
        return MatrixMetrics(
            valueWidth: ceil(valueWidth),
            wideCategoryWidth: wideCategoryWidth,
            narrowCategoryWidth: narrowCategoryWidth,
            rowHeight: max(34, lineHeight + 14),
            headerHeight: max(40, 2 * lineHeight + 8)
        )
    }

    /// Two synced halves inside one shared vertical `ScrollView`: a
    /// category column that only scrolls vertically (with the outer view),
    /// and a horizontally-scrolling `Grid` of period/total columns
    /// (`ios/docs/plan.md` iOS UI feedback: "first column with the
    /// categories disappears as you scroll to the right"). Both halves are
    /// built from the same `visibleRows` list with the same row heights,
    /// which is what keeps their rows aligned.
    ///
    /// A `GeometryReader` in the background of the value grid reads its x
    /// position in the coordinate space of the horizontal scroll view, with
    /// `onChange`. The negative of that value is the horizontal offset (see
    /// `updateCategoryWidth`). A change of the category width moves the scroll
    /// view and the grid together, so it does not change this value. This
    /// works on iOS 17; `onScrollGeometryChange` needs iOS 18.
    ///
    /// The header row is outside the vertical `ScrollView`, so it stays
    /// visible while the rows scroll (see `headerRow`). Its month headers
    /// move by `horizontalOffset`, the same offset that sets the category
    /// width.
    ///
    /// The app does not use a `PreferenceKey` here. In this nested scroll
    /// view, `onPreferenceChange` did not fire during a scroll on the iOS 26
    /// simulator.
    private func matrix(_ table: TrendsBuilder.TrendsTable) -> some View {
        let rows = visibleRows(table)
        let sizes = metrics(table, rows: rows)
        let categoryWidth = isCategoryColumnNarrow && !keepCategoryWide
            ? sizes.narrowCategoryWidth
            : sizes.wideCategoryWidth
        return VStack(spacing: 0) {
            headerRow(table, sizes: sizes, categoryWidth: categoryWidth)
            ScrollView(.vertical) {
                HStack(spacing: 0) {
                    frozenCategoryColumn(table, rows: rows, sizes: sizes, width: categoryWidth)
                    ScrollView(.horizontal) {
                        valueColumns(table, rows: rows, sizes: sizes)
                            .background(
                                GeometryReader { proxy in
                                    let minX = proxy.frame(in: .named(Self.valueScrollSpace)).minX
                                    Color.clear
                                        .onAppear { updateCategoryWidth(offset: -minX) }
                                        .onChange(of: minX) { _, newValue in
                                            updateCategoryWidth(offset: -newValue)
                                        }
                                }
                            )
                    }
                    .coordinateSpace(name: Self.valueScrollSpace)
                }
            }
        }
        .background(
            GeometryReader { proxy in
                Color.clear
                    .onAppear { matrixWidth = proxy.size.width }
                    .onChange(of: proxy.size.width) { _, newWidth in matrixWidth = newWidth }
            }
        )
        .safeAreaInset(edge: .bottom) {
            if table.rows.isEmpty {
                ContentUnavailableView(
                    "No Data",
                    systemImage: "chart.bar",
                    description: Text("No transactions fall inside this window.")
                )
                .padding()
            }
        }
    }

    /// Makes the category column narrow when the horizontal offset is more
    /// than `narrowAfterOffset`, and wide again when it is less than
    /// `wideBeforeOffset`. Between the two values, the width does not change.
    private func updateCategoryWidth(offset: CGFloat) {
        // The header strip follows the offset exactly, also during a bounce,
        // so that each month header stays above its column.
        horizontalOffset = offset
        let narrow: Bool
        if offset > Self.narrowAfterOffset {
            narrow = true
        } else if offset < Self.wideBeforeOffset {
            narrow = false
        } else {
            return
        }
        if narrow != isCategoryColumnNarrow {
            withAnimation(.easeInOut(duration: 0.2)) {
                isCategoryColumnNarrow = narrow
            }
        }
    }

    /// Flattened top-level rows plus any expanded parent's children, in
    /// display order — the single source of truth both matrix halves
    /// render from, so a parent's expand/collapse toggle can never desync
    /// row counts between them.
    private func visibleRows(_ table: TrendsBuilder.TrendsTable) -> [(row: TrendsBuilder.TrendRow, isChild: Bool)] {
        var result: [(TrendsBuilder.TrendRow, Bool)] = []
        for row in table.rows {
            result.append((row, false))
            if row.hasChildren, expandedParents.contains(row.label) {
                for child in row.children {
                    result.append((child, true))
                }
            }
        }
        return result
    }

    /// The header row of the matrix, above the vertical `ScrollView`, so it
    /// stays visible while the rows scroll. The "Category" header has the
    /// width of the category column. The strip of month headers and the
    /// "Total" header moves by `horizontalOffset` and clips at its edges, so
    /// each header stays above its value column. A drag on the strip does not
    /// scroll the months.
    private func headerRow(
        _ table: TrendsBuilder.TrendsTable,
        sizes: MatrixMetrics,
        categoryWidth width: CGFloat
    ) -> some View {
        HStack(spacing: 0) {
            // A tap keeps the column wide, and a second tap returns it to the
            // automatic width (design D2a).
            Button {
                withAnimation(.easeInOut(duration: 0.2)) { keepCategoryWide.toggle() }
            } label: {
                HStack(spacing: Self.chevronSpacing) {
                    Text("Category")
                        .lineLimit(1)
                    if keepCategoryWide {
                        Image(systemName: "arrow.left.and.right")
                            .font(.caption2)
                            .accessibilityHidden(true)
                    }
                }
                .font(.caption.bold())
                .padding(.leading, Self.parentIndent)
                .padding(.trailing, Self.categoryTrailingPadding)
                .frame(width: width, height: sizes.headerHeight, alignment: .leading)
                .background(Color(.secondarySystemBackground))
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Category")
            .accessibilityValue(keepCategoryWide ? "Shows all names" : "Automatic width")
            .accessibilityHint("Shows all category names in full, or returns to the automatic width.")
            .accessibilityIdentifier("trendsCategoryHeader")
            .background(Color(.systemBackground))
            .zIndex(1)
            .shadow(color: .black.opacity(0.08), radius: 3, x: 2, y: 0)

            // The strip is wider than the screen. A clear view takes the
            // space that the row gives it, and the strip lies on top of it
            // and clips, so the strip cannot make the row wider.
            Color.clear
                .overlay(alignment: .leading) {
                    HStack(spacing: 0) {
                        ForEach(table.periods, id: \.key) { period in
                            valueCell(
                                Text(Self.headerLines(period).joined(separator: "\n")),
                                sizes: sizes,
                                height: sizes.headerHeight,
                                lines: 2
                            )
                            .font(.caption.bold())
                            .accessibilityLabel(period.label)
                            .accessibilityIdentifier("trendsPeriodHeader-\(period.key)")
                        }
                        valueCell(Text("Total"), sizes: sizes, height: sizes.headerHeight)
                            .font(.caption.bold())
                    }
                    .fixedSize()
                    .offset(x: -horizontalOffset)
                }
                .clipped()
                .background(Color(.secondarySystemBackground))
        }
        .frame(height: sizes.headerHeight)
    }

    private func frozenCategoryColumn(
        _ table: TrendsBuilder.TrendsTable,
        rows: [(row: TrendsBuilder.TrendRow, isChild: Bool)],
        sizes: MatrixMetrics,
        width: CGFloat
    ) -> some View {
        VStack(spacing: 0) {
            ForEach(Array(rows.enumerated()), id: \.offset) { _, entry in
                categoryCell(entry.row, isChild: entry.isChild, width: width, height: sizes.rowHeight)
            }
            Text("Total")
                .font(.caption.bold())
                .lineLimit(1)
                .padding(.leading, Self.parentIndent)
                .padding(.trailing, Self.categoryTrailingPadding)
                .frame(width: width, height: sizes.rowHeight, alignment: .leading)
                .background(Color(.secondarySystemBackground))
        }
        .background(Color(.systemBackground))
        .zIndex(1)
        .shadow(color: .black.opacity(0.08), radius: 3, x: 2, y: 0)
    }

    /// A value in its column: one line, never truncated, with `valueGap` on
    /// each side.
    private func valueCell(_ text: Text, sizes: MatrixMetrics, height: CGFloat? = nil, lines: Int = 1) -> some View {
        text
            .lineLimit(lines)
            .multilineTextAlignment(.trailing)
            .fixedSize()
            .padding(.horizontal, Self.valueGap)
            .frame(width: sizes.valueWidth, height: height ?? sizes.rowHeight, alignment: .trailing)
    }

    private func valueColumns(
        _ table: TrendsBuilder.TrendsTable,
        rows: [(row: TrendsBuilder.TrendRow, isChild: Bool)],
        sizes: MatrixMetrics
    ) -> some View {
        Grid(alignment: .trailing, horizontalSpacing: 0, verticalSpacing: 0) {
            ForEach(Array(rows.enumerated()), id: \.offset) { _, entry in
                GridRow {
                    ForEach(table.periods, id: \.key) { period in
                        cellButton(row: entry.row, period: period, table: table, sizes: sizes)
                    }
                    valueCell(Text(DisplayFormat.compactAmount(entry.row.total)), sizes: sizes)
                        .font(.caption.monospacedDigit().bold())
                }
            }
            GridRow {
                ForEach(table.periods, id: \.key) { period in
                    valueCell(Text(DisplayFormat.compactAmount(table.columnTotals[period.key] ?? 0)), sizes: sizes)
                        .font(.caption.monospacedDigit().bold())
                        .background(Color(.secondarySystemBackground))
                }
                valueCell(Text(DisplayFormat.compactAmount(table.grandTotal)), sizes: sizes)
                    .font(.caption.monospacedDigit().bold())
                    .background(Color(.secondarySystemBackground))
            }
        }
    }

    /// The key of a category cell. A parent and a child can have the same
    /// label, so the key also holds the level.
    private static func cellKey(_ row: TrendsBuilder.TrendRow, isChild: Bool) -> String {
        "\(isChild ? "child" : "top"):\(row.label)"
    }

    private func toggleExpanded(_ row: TrendsBuilder.TrendRow) {
        guard row.hasChildren else { return }
        if expandedParents.contains(row.label) {
            expandedParents.remove(row.label)
        } else {
            expandedParents.insert(row.label)
        }
    }

    /// A tap expands or collapses a group. A long press shows the full name
    /// in a popover (design D2a). The cell is not a `Button`, because a
    /// disabled button for a leaf row would also stop the long press.
    private func categoryCell(_ row: TrendsBuilder.TrendRow, isChild: Bool, width: CGFloat, height: CGFloat) -> some View {
        let key = Self.cellKey(row, isChild: isChild)
        return HStack(spacing: Self.chevronSpacing) {
            if row.hasChildren {
                Image(systemName: expandedParents.contains(row.label) ? "chevron.down" : "chevron.right")
                    .font(.caption2)
            }
            Text(row.label)
                .font(isChild ? .caption : .caption.bold())
                .lineLimit(1)
                .truncationMode(.middle)
        }
        .padding(.leading, isChild ? Self.childIndent : Self.parentIndent)
        .padding(.trailing, Self.categoryTrailingPadding)
        .frame(width: width, height: height, alignment: .leading)
        .foregroundStyle(isChild ? .secondary : .primary)
        .contentShape(Rectangle())
        .onTapGesture { toggleExpanded(row) }
        .onLongPressGesture(minimumDuration: 0.4) { fullNameCellKey = key }
        .popover(isPresented: Binding(
            get: { fullNameCellKey == key },
            set: { if !$0 { fullNameCellKey = nil } }
        )) {
            fullNamePopover(row.label)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(row.label)
        .accessibilityAddTraits(row.hasChildren ? .isButton : [])
        .accessibilityAction {
            toggleExpanded(row)
        }
        .accessibilityIdentifier("trendsCategoryCell")
    }

    /// The full name of a category. While the column does not stay wide, a
    /// second line tells the user how to see all names at once.
    private func fullNamePopover(_ name: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(name)
                .font(.subheadline.bold())
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("trendsFullName")
            if !keepCategoryWide {
                Label("Tap Category to show all names", systemImage: "arrow.left.and.right")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .accessibilityIdentifier("trendsFullNameHint")
            }
        }
        .padding()
        .presentationCompactAdaptation(.popover)
    }

    private func cellButton(
        row: TrendsBuilder.TrendRow,
        period: TrendsBuilder.Period,
        table: TrendsBuilder.TrendsTable,
        sizes: MatrixMetrics
    ) -> some View {
        let value = row.cells[period.key] ?? 0
        return NavigationLink(value: TrendsCellRoute(row: row, period: period, params: params)) {
            valueCell(Text(value == 0 ? "—" : DisplayFormat.compactAmount(value)), sizes: sizes)
                .font(.caption.monospacedDigit())
        }
        .buttonStyle(.plain)
        .disabled(value == 0)
        .accessibilityIdentifier("trendsCell-\(period.key)")
    }

    // MARK: - Accounts sheet

    private var accountPickerSheet: some View {
        NavigationStack {
            List(availableAccounts, id: \.self) { account in
                Button {
                    if params.accounts.contains(account) {
                        params.accounts.removeAll { $0 == account }
                    } else {
                        params.accounts.append(account)
                    }
                } label: {
                    HStack {
                        Text(account).foregroundStyle(.primary)
                        Spacer()
                        if params.accounts.contains(account) {
                            Image(systemName: "checkmark")
                        }
                    }
                }
            }
            .navigationTitle("Accounts")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { showAccountPicker = false }
                }
                ToolbarItem(placement: .cancellationAction) {
                    if !params.accounts.isEmpty {
                        Button("Clear") { params.accounts = [] }
                    }
                }
            }
        }
    }

    // MARK: - Data loading

    private func reload() async {
        guard let appDatabase else { return }
        do {
            async let tableTask = AppQueries.trendsTable(appDatabase: appDatabase, params: params)
            async let accountsTask = AppQueries.distinctAccounts(appDatabase: appDatabase)
            let (loadedTable, accounts) = try await (tableTask, accountsTask)
            table = loadedTable
            availableAccounts = accounts
            loadErrorMessage = nil
        } catch {
            loadErrorMessage = "Couldn't load trends: \(error.localizedDescription)"
        }
    }
}

/// Navigation-stack route for a tapped trends cell: the pushed
/// `TransactionsListView` is initialized directly from
/// `TrendsBuilder.transactionFilter(for:period:params:)`, so its filtered
/// sum always matches the tapped cell exactly.
private struct TrendsCellRoute: Hashable {
    var filter: TransactionFilter

    init(row: TrendsBuilder.TrendRow, period: TrendsBuilder.Period, params: TrendsBuilder.TrendsParams) {
        self.filter = TrendsBuilder.transactionFilter(for: row, period: period, params: params)
    }
}

#Preview {
    TrendsView()
}
