import Foundation

/// The subset of `TransactionFilter`'s fields that `TrendsBuilder.TrendsParams`
/// also carries (added so Trends can share the exact same filter-editing UI
/// as Transactions — see `ios/docs/plan.md` iOS UI feedback: "Trends page -
/// there are no filters on this page - use the same filters as
/// transactions"). Both types conform directly (their stored properties
/// already have these exact names/types), so no adapter/bridging type is
/// needed — the app-target `FilterSheet` is generic over this protocol.
public protocol FilterFields {
    var q: String? { get set }
    var dateFrom: Date? { get set }
    var dateTo: Date? { get set }
    var preset: TransactionFilter.Preset? { get set }
    var categories: [String] { get set }
    var excludeCategories: [String] { get set }
    var accounts: [String] { get set }
    var amountMin: Double? { get set }
    var amountMax: Double? { get set }
    var tags: [String] { get set }
    var includeTransfers: Bool { get set }

    /// A value with every field at its default — backs `FilterSheet`'s
    /// "Clear all filters" button generically, without the app target
    /// needing to know which concrete type it's editing.
    static func empty() -> Self
}

extension TransactionFilter: FilterFields {
    public static func empty() -> Self { Self() }
}
extension TrendsBuilder.TrendsParams: FilterFields {
    public static func empty() -> Self { Self() }
}
