import Foundation
import CryptoKit

/// Port of `src/abn_combined/core/utils.py`.
///
/// Shared normalization and hashing helpers used by the rule engine
/// (`Categorizer.swift`), transaction identity (`TransactionID.swift`), and
/// dedup (`Dedup.swift`). Every function mirrors its Python counterpart's
/// *observable* behavior (including surprising edge cases), not just its
/// intent — see `ios/docs/plan.md` "Working agreements for subagents":
/// "Never invent semantics".
public enum CoreNormalize {

    /// Port of `core/utils.py: CATEGORY_SEPARATOR`.
    ///
    /// Hierarchical category separator, e.g. `"fixed-insurance-life"`.
    public static let categorySeparator = "-"

    /// Port of `core/utils.py:normalize_category`.
    ///
    /// Lowercases, comma-splits/trims/rejoins; `nil` for empty/whitespace-only
    /// input (including a purely-comma/whitespace input like `", ,"` — every
    /// segment trims to empty, so the parts list is empty and the whole
    /// result is `nil`, matching the Python `parts` list falling empty).
    public static func normalizeCategory(_ value: String?) -> String? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return nil }
        let parts = trimmed
            .split(separator: ",", omittingEmptySubsequences: false)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .map { $0.lowercased() }
        return parts.isEmpty ? nil : parts.joined(separator: ", ")
    }

    /// Port of `core/utils.py:normalize_string_for_matching`.
    ///
    /// Steps, in this exact order (the order is load-bearing — see
    /// `ios/docs/spec.md` "Normalization"): `nil` -> `""`; remove ALL
    /// whitespace (`\s+` in Python, mirrored here with a `\s+` regex, which
    /// in NSRegularExpression/ICU matches the same Unicode whitespace class
    /// Python's `re` module does for the ASCII+common-Unicode inputs this
    /// app's descriptions use); remove the exact literal `"WERO/"` substring
    /// (case-sensitive, *before* lowercasing — so `"WERO /Payment"` becomes
    /// `"WERO/Payment"` after whitespace removal, then `"Payment"` after the
    /// `WERO/` removal, then `"payment"` after lowercasing); lowercase last.
    public static func normalizeStringForMatching(_ value: String?) -> String {
        guard let value else { return "" }
        let noWhitespace = value.replacingOccurrences(
            of: "\\s+",
            with: "",
            options: .regularExpression
        )
        let withoutWero = noWhitespace.replacingOccurrences(of: "WERO/", with: "")
        return withoutWero.lowercased()
    }

    /// Mirrors Python's duck-typed `amount` argument to
    /// `calculate_transaction_hash_components`: callers there might pass a
    /// `Decimal`, a `float`, a numeric-looking `str`, a garbage `str`, or
    /// `None`. Swift needs a concrete type, so this small enum stands in for
    /// Python's `Any`; each case renders exactly like `float(amount)` would
    /// in Python (raising -> caught -> `"0.00"` fallback happens in
    /// `calculateTransactionHash`, not here).
    public enum HashAmountInput {
        case none
        case double(Double)
        case decimal(Decimal)
        /// A raw string, numeric or not (e.g. `"12"`, `"abc"`) — mirrors
        /// Python's `float(amount)` being handed a `str`.
        case string(String)

        public init(_ value: Double?) {
            self = value.map(HashAmountInput.double) ?? .none
        }

        public init(_ value: Decimal?) {
            self = value.map(HashAmountInput.decimal) ?? .none
        }

        public init(_ value: String?) {
            self = value.map(HashAmountInput.string) ?? .none
        }

        /// `float(amount)` in Python, or `nil` if that call would raise
        /// `ValueError`/`TypeError` (caught in `calculate_transaction_hash_components`
        /// and mapped to the `"0.00"` fallback).
        fileprivate var asDouble: Double? {
            switch self {
            case .none:
                return nil
            case .double(let d):
                return d
            case .decimal(let d):
                return NSDecimalNumber(decimal: d).doubleValue
            case .string(let s):
                return Double(s)
            }
        }
    }

    /// Port of `core/utils.py:calculate_transaction_hash_components`.
    ///
    /// SHA-256 hex digest of
    /// `"{account_norm}|{date_str}|{description_norm}|{amount_str}"`.
    ///
    /// - `date`: `nil` -> `""` (Python: `if date_value: ... else: date_str = ""` —
    ///   a *truthiness* check, not an `is not None` check, but the only falsy
    ///   non-`None` `date`/`str` values Python would ever see here don't occur
    ///   in this app's data, so `nil` -> `""` is the entire observable
    ///   behavior). Non-`nil` renders as `yyyy-MM-dd` (`date.isoformat()`).
    /// - `amount`: parsed as `Double` per Python's `float(amount)`; unparsable
    ///   or `nil` -> `0.00`. Formatted to exactly two decimals
    ///   (`f"{amount_float:.2f}"`).
    /// - `description`/`account`: run through `normalizeStringForMatching`.
    public static func calculateTransactionHash(
        date: Date?,
        description: String?,
        amount: HashAmountInput,
        account: String?
    ) -> String {
        let dateStr = date.map { DatabaseDateFormat.dateOnly.string(from: $0) } ?? ""
        let descriptionNorm = normalizeStringForMatching(description)
        let accountNorm = normalizeStringForMatching(account)
        let amountStr = String(
            format: "%.2f",
            locale: Locale(identifier: "en_US_POSIX"),
            amount.asDouble ?? 0.0
        )

        let hashInput = "\(accountNorm)|\(dateStr)|\(descriptionNorm)|\(amountStr)"
        let digest = SHA256.hash(data: Data(hashInput.utf8))
        return digest.map { String(format: "%02x", $0) }.joined()
    }

    /// Port of `core/categorizer.py:_is_transfer` (prefix variant — see
    /// `ios/docs/spec.md` "Normalization": desktop's filters use a
    /// `transfer*` prefix match while the categorizer's (unported)
    /// `preview_rule` uses a substring match; iOS standardizes on the prefix
    /// variant everywhere).
    ///
    /// `effectiveCategory` is the caller-computed `manual_category ?? category`
    /// (see `TransactionRecord.effectiveCategory`).
    public static func isTransferCategory(_ effectiveCategory: String?) -> Bool {
        guard let effectiveCategory, !effectiveCategory.isEmpty else { return false }
        return effectiveCategory.lowercased().hasPrefix("transfer")
    }
}
