import Foundation
import GRDB

/// Port of the manual category/tag write endpoints in
/// `src/abn_combined/api/transactions.py`: `set_manual_category`,
/// `set_manual_tags`, `clear_manual_category`, `clear_manual_tags`.
///
/// Manual edits are the *only* categorization writes the iOS app makes
/// directly (rules arrive via snapshot import and are applied automatically to
/// file-imported transactions). Setting a manual field always pins
/// `categorization_source = "manual"` and stamps `updated_at`; clearing one
/// resets `categorization_source` back to `nil` only when the *other* manual
/// field is also empty — matching desktop's `clear_manual_category` /
/// `clear_manual_tags` exactly (see the doc comment on each function).
///
/// Every write stamps `updated_at` via `timestampNow()` so the change lands in
/// the next delta snapshot ("only transactions changed since <since>").
public enum TransactionMutations {

    /// The ISO-8601 second-precision, UTC stamp `TransactionRecord.updatedAt`
    /// expects (see that field's doc comment). Mirrors desktop's
    /// `txn.updated_at = datetime.now()`; the exact wall-clock offset is not
    /// load-bearing (the value is only ever compared lexicographically for the
    /// delta filter), but the format must match the `updated_at` column's
    /// (`DatabaseDateFormat.dateTime`).
    public static func timestampNow() -> String {
        DatabaseDateFormat.dateTime.string(from: Date())
    }

    enum MutationError: Error {
        case transactionNotFound(String)
    }

    private static func fetch(_ db: Database, _ transactionId: String) throws -> TransactionRecord {
        guard let txn = try TransactionRecord.fetchOne(db, key: transactionId) else {
            throw MutationError.transactionNotFound(transactionId)
        }
        return txn
    }

    /// Port of `api/transactions.py:set_manual_category`. Sets the manual
    /// category (normalized via `CoreNormalize.normalizeCategory`, so a blank
    /// input clears it to `nil`), pins `categorization_source = "manual"`, and
    /// stamps `updated_at`.
    @discardableResult
    public static func setManualCategory(
        db: Database,
        transactionId: String,
        manualCategory: String
    ) throws -> TransactionRecord {
        var txn = try fetch(db, transactionId)
        txn.manualCategory = CoreNormalize.normalizeCategory(manualCategory)
        txn.categorizationSource = "manual"
        txn.updatedAt = timestampNow()
        try txn.update(db)
        return txn
    }

    /// Port of `api/transactions.py:set_manual_tags`. Sets manual tags from a
    /// comma-separated string, trimming each segment and dropping empties
    /// (`", ".join(p.strip() for p in manual_tags.split(",") if p.strip())`),
    /// with an empty result stored as `nil`. Note this deliberately does NOT
    /// go through `CoreNormalize.normalizeCategory` — desktop preserves tag
    /// case, unlike categories.
    @discardableResult
    public static func setManualTags(
        db: Database,
        transactionId: String,
        manualTags: String
    ) throws -> TransactionRecord {
        var txn = try fetch(db, transactionId)
        let cleaned = manualTags
            .split(separator: ",", omittingEmptySubsequences: false)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
            .joined(separator: ", ")
        txn.manualTags = cleaned.isEmpty ? nil : cleaned
        txn.categorizationSource = "manual"
        txn.updatedAt = timestampNow()
        try txn.update(db)
        return txn
    }

    /// Port of `api/transactions.py:clear_manual_category`. Clears the manual
    /// category (restoring the rule-assigned value as effective). Resets
    /// `categorization_source` to `nil` only when it was `"manual"` and no
    /// manual tags remain — otherwise the remaining manual tags keep the
    /// source `"manual"`.
    @discardableResult
    public static func clearManualCategory(
        db: Database,
        transactionId: String
    ) throws -> TransactionRecord {
        var txn = try fetch(db, transactionId)
        txn.manualCategory = nil
        if txn.categorizationSource == "manual" && (txn.manualTags?.isEmpty ?? true) {
            txn.categorizationSource = nil
        }
        txn.updatedAt = timestampNow()
        try txn.update(db)
        return txn
    }

    /// Port of `api/transactions.py:clear_manual_tags`. Clears manual tags
    /// (restoring the rule-assigned value as effective). Resets
    /// `categorization_source` to `nil` only when it was `"manual"` and no
    /// manual category remains.
    @discardableResult
    public static func clearManualTags(
        db: Database,
        transactionId: String
    ) throws -> TransactionRecord {
        var txn = try fetch(db, transactionId)
        txn.manualTags = nil
        if txn.categorizationSource == "manual" && (txn.manualCategory?.isEmpty ?? true) {
            txn.categorizationSource = nil
        }
        txn.updatedAt = timestampNow()
        try txn.update(db)
        return txn
    }
}
