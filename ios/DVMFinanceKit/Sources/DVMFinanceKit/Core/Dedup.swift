import Foundation
import GRDB

/// Port of `core/dedup.py`.
///
/// `check_duplicates`/`insert_transactions` operate on lists of transaction
/// dicts in Python; here they operate on `[ParsedTransaction]`. `db` is a
/// GRDB `Database` (a connection inside a read/write closure), not the
/// `AppDatabase` wrapper — callers open the transaction via
/// `appDatabase.dbWriter.write { db in ... }`, matching how `Categorizer.swift`
/// takes `db: Database` too.
public enum Dedup {

    /// Errors that only arise from insert-time data that violates the
    /// desktop schema's `NOT NULL` constraints (`core/models.py`:
    /// `transactiondate`/`amount` are `nullable=False`). Real Phase D parsers
    /// always populate both fields for a parsed statement line; this only
    /// guards against malformed input reaching `insertTransactions`,
    /// mirroring the `IntegrityError` SQLAlchemy would raise for the same
    /// condition in the Python pipeline, just surfaced before we attempt the
    /// write rather than as a SQLite constraint failure.
    public enum DedupError: Error, Equatable {
        case missingTransactionDate
        case missingAmount
    }

    /// Port of `core/dedup.py:check_duplicates`.
    ///
    /// Splits incoming transactions into `(new, duplicates)` using
    /// deterministic ids (`TransactionID.generateTransactionID`). A
    /// duplicate is either a repeat id *within* `transactions` (first
    /// occurrence wins, matching Python's dict-insertion-order semantics) or
    /// an id that already exists in `db`.
    public static func checkDuplicates(
        db: Database,
        transactions: [ParsedTransaction]
    ) throws -> (new: [ParsedTransaction], duplicates: [ParsedTransaction]) {
        var incomingByID: [String: ParsedTransaction] = [:]
        var incomingOrder: [String] = []
        var duplicates: [ParsedTransaction] = []

        for transaction in transactions {
            let id = TransactionID.generateTransactionID(transaction)
            if incomingByID[id] != nil {
                // In-batch duplicate.
                duplicates.append(transaction)
            } else {
                incomingByID[id] = transaction
                incomingOrder.append(id)
            }
        }

        var existingIDs: Set<String> = []
        if !incomingByID.isEmpty {
            let idsRequest = TransactionRecord.select(Column("id"), as: String.self)
            existingIDs = try Set(idsRequest.fetchAll(db))
        }

        var newTransactions: [ParsedTransaction] = []
        newTransactions.reserveCapacity(incomingOrder.count)
        for id in incomingOrder {
            let transaction = incomingByID[id]!
            if existingIDs.contains(id) {
                duplicates.append(transaction)
            } else {
                newTransactions.append(transaction)
            }
        }

        return (newTransactions, duplicates)
    }

    /// Port of `core/dedup.py:insert_transactions`.
    ///
    /// Upserts (GRDB `save(_:)`, the analog of SQLAlchemy `Session.merge`)
    /// each transaction, computing its id and `transaction_hash`, applying
    /// `normalize_category` to `category`/`manual_category`, and defaulting
    /// `currency` to `"EUR"`. Returns the ids written, in input order.
    ///
    /// Idempotent: re-inserting an id already present overwrites that row
    /// (exact re-imports are silently absorbed) — callers that need
    /// duplicate *counts* must call `checkDuplicates` first, exactly as the
    /// Python docstring notes.
    @discardableResult
    public static func insertTransactions(
        db: Database,
        transactions: [ParsedTransaction]
    ) throws -> [String] {
        var written: [String] = []
        written.reserveCapacity(transactions.count)

        for transaction in transactions {
            guard let transactiondate = transaction.transactiondate else {
                throw DedupError.missingTransactionDate
            }
            guard let amount = transaction.amount else {
                throw DedupError.missingAmount
            }

            let id = TransactionID.generateTransactionID(transaction)
            let transactionHash = CoreNormalize.calculateTransactionHash(
                date: transaction.transactiondate,
                description: transaction.description,
                amount: CoreNormalize.HashAmountInput(transaction.amount),
                account: transaction.accountNumber
            )

            // Port of Python's `normalize_category(x) or x`: if normalization
            // yields `nil` (blank/whitespace-only input, or `x` was already
            // `nil`), fall back to the raw value rather than dropping it —
            // this only differs from `normalizeCategory(x)` when `x` itself
            // is a non-nil string that normalizes to `nil` (e.g. all-comma
            // input), in which case Python keeps the *original* unnormalized
            // string.
            let category = CoreNormalize.normalizeCategory(transaction.category) ?? transaction.category
            let manualCategory = CoreNormalize.normalizeCategory(transaction.manualCategory)
                ?? transaction.manualCategory

            let record = TransactionRecord(
                id: id,
                accountNumber: transaction.accountNumber,
                mutationcode: transaction.mutationcode,
                transactiondate: transactiondate,
                valuedate: transaction.valuedate,
                startsaldo: transaction.startsaldo.map { Decimal($0) },
                endsaldo: transaction.endsaldo.map { Decimal($0) },
                amount: Decimal(amount),
                description: transaction.description,
                descriptionStructured: transaction.descriptionStructured,
                category: category,
                manualCategory: manualCategory,
                tags: transaction.tags,
                manualTags: transaction.manualTags,
                categorizationSource: transaction.categorizationSource,
                currency: transaction.currency ?? "EUR",
                sourceFile: transaction.sourceFile,
                sourceLine: transaction.sourceLine,
                transactionTypeCode: transaction.transactionTypeCode,
                transactionReference: transaction.transactionReference,
                transactionHash: transactionHash
            )

            try record.save(db)
            written.append(id)
        }

        return written
    }
}
