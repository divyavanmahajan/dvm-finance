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

    /// A reference that names no single payment. Port of
    /// `core/dedup.py:_UNUSABLE_REFERENCES`.
    ///
    /// The bank writes one of these when the payment carries no reference, so
    /// many rows share the value. The sample statement of 2291 rows holds
    /// `NOTPROVIDED` 136 times. The duplicate check must not join two payments
    /// on such a value.
    ///
    /// The comparison removes each whitespace character first. An MT940
    /// description wraps at a fixed width, so the same value also appears
    /// split, as in `NOTP ROVIDED`.
    static let unusableReferences: Set<String> = ["NONREF", "NOTPROVIDED"]

    /// The separators that `normalizeReference` removes.
    ///
    /// An MT940 description wraps at a fixed width, and the wrap can fall
    /// inside the reference. The bank also prints the same reference with
    /// different separators in the two description forms. One payment
    /// therefore reads `8022764496926345` in one form and
    /// `8022.7644 .9692.6345` in the other.
    static let referenceSeparators: CharacterSet = {
        var set = CharacterSet.whitespacesAndNewlines
        set.insert(charactersIn: ".-")
        return set
    }()

    /// Port of `core/dedup.py:normalize_reference`.
    ///
    /// Removes each whitespace character, each period, and each hyphen, then
    /// changes the text to upper case. Two forms of one reference therefore
    /// give one key. The system stores the original text and compares this
    /// form.
    public static func normalizeReference(_ value: String) -> String {
        value.components(separatedBy: referenceSeparators)
            .joined()
            .uppercased()
    }

    /// True for a reference that names no single payment.
    static func isUnusableReference(_ value: String) -> Bool {
        let normalized = normalizeReference(value)
        return normalized.isEmpty || unusableReferences.contains(normalized)
    }

    /// The amount as a stable string with two decimal places. Port of
    /// `core/dedup.py:_amount_key`.
    static func amountKey(_ amount: Double?) -> String {
        guard let amount else { return "" }
        return String(format: "%.2f", amount)
    }

    /// The amount of a raw database row, as the same stable string.
    ///
    /// GRDB stores a `Decimal` as TEXT, so the column holds `"-5.75"` and not
    /// a numeric value. Reading it as `Double?` raises. The function therefore
    /// reads the text first and falls back to a numeric column.
    static func amountKey(fromRow row: Row, column: String) -> String {
        if let text: String = row[column] {
            if let value = Double(text) { return amountKey(value) }
            return text
        }
        if let value: Double = row[column] { return amountKey(value) }
        return ""
    }

    /// Port of `core/dedup.py:extract_end_to_end_reference`.
    ///
    /// Returns the usable end-to-end reference of a parsed transaction, from
    /// its structured description. Returns `nil` for an empty value and for a
    /// value that names no single payment.
    public static func extractEndToEndReference(
        _ transaction: ParsedTransaction
    ) -> String? {
        guard let raw = transaction.descriptionStructured,
              let data = raw.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data),
              let dict = object as? [String: Any],
              let value = dict["end_to_end_reference"] as? String
        else { return nil }

        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if isUnusableReference(trimmed) { return nil }
        return trimmed
    }

    /// The `(account, reference, amount)` match key, or `nil` when there is
    /// none. Port of `core/dedup.py:_reference_key`.
    ///
    /// The key holds the account, because a reference is unique for one
    /// creditor and not for the world.
    ///
    /// The key also holds the amount. A reversal carries the reference of the
    /// payment that it reverses, with the opposite sign. The sample statement
    /// holds three such pairs, for example a direct debit of -149,88 and its
    /// `SEPA INCASSO TERUGBOEKING` of +149,88. Those are two transactions, and
    /// the check must not join them. The two description forms of one payment
    /// always report the same amount, because they describe one statement line.
    static func referenceKey(_ transaction: ParsedTransaction) -> String? {
        guard let reference = extractEndToEndReference(transaction) else { return nil }
        return "\(transaction.accountNumber)\u{0}\(normalizeReference(reference))\u{0}"
            + amountKey(transaction.amount)
    }

    /// Port of `core/dedup.py:counterparty_key`.
    ///
    /// The second match key: the account, the transaction date, the amount, the
    /// normalized counterparty IBAN, and the normalized remittance text. A
    /// transfer between two accounts of the user carries no end-to-end
    /// reference, so only this key joins its two description forms.
    ///
    /// The key holds the remittance text, because two payments of one day can
    /// share an account, an amount, and a counterparty. A real database holds
    /// three payments of -149,00 euro of one day to one PayPal IBAN, and only
    /// their remittance texts differ.
    ///
    /// Returns `nil` when the transaction holds a usable reference, because the
    /// reference key already covers it, and `nil` when it holds no IBAN.
    public static func counterpartyKey(_ transaction: ParsedTransaction) -> String? {
        if extractEndToEndReference(transaction) != nil { return nil }

        guard let raw = transaction.descriptionStructured,
              let data = raw.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data),
              let dict = object as? [String: Any],
              let iban = dict["iban"] as? String,
              !iban.trimmingCharacters(in: .whitespaces).isEmpty
        else { return nil }

        let remittance = dict["remittance_info"] as? String ?? ""
        // Python renders a `date` as `yyyy-MM-dd`, so the key must match.
        let date = transaction.transactiondate
            .map(DatabaseDateFormat.dateOnly.string(from:)) ?? ""
        return [
            transaction.accountNumber,
            date,
            amountKey(transaction.amount),
            normalizeReference(iban),
            normalizeReference(remittance),
        ].joined(separator: "\u{0}")
    }

    /// The source file of a parsed transaction. Port of
    /// `core/dedup.py:_source_file`.
    static func sourceFile(_ transaction: ParsedTransaction) -> String {
        transaction.sourceFile ?? ""
    }

    /// Port of `core/dedup.py:check_duplicates`.
    ///
    /// Splits incoming transactions into `(new, duplicates)` using
    /// deterministic ids (`TransactionID.generateTransactionID`). A
    /// duplicate is either a repeat id *within* `transactions` (first
    /// occurrence wins, matching Python's dict-insertion-order semantics) or
    /// an id that already exists in `db`.
    ///
    /// The check also matches the account with the end-to-end reference. The
    /// bank writes one SEPA payment in two description forms, and the two forms
    /// hold a different raw text. The id of the two forms therefore differs,
    /// and only the reference joins them.
    public static func checkDuplicates(
        db: Database,
        transactions: [ParsedTransaction]
    ) throws -> (new: [ParsedTransaction], duplicates: [ParsedTransaction]) {
        var incomingByID: [String: ParsedTransaction] = [:]
        var incomingOrder: [String] = []
        var incomingReferences: Set<String> = []
        // The counterparty key maps to the source file of the row that claimed
        // it. Two rows of one file are two payments, never two forms of one.
        var incomingCounterparties: [String: String] = [:]
        var duplicates: [ParsedTransaction] = []

        for transaction in transactions {
            let id = TransactionID.generateTransactionID(transaction)
            if incomingByID[id] != nil {
                // In-batch duplicate by the id.
                duplicates.append(transaction)
                continue
            }

            if let key = referenceKey(transaction), incomingReferences.contains(key) {
                // In-batch duplicate by the reference: the second description
                // form of a payment that an earlier row of this batch holds.
                duplicates.append(transaction)
                continue
            }

            let otherKey = counterpartyKey(transaction)
            if let otherKey,
               let claimedFrom = incomingCounterparties[otherKey],
               claimedFrom != sourceFile(transaction) {
                // The second description form of a transfer that carries no
                // reference. The two rows come from two statement files.
                duplicates.append(transaction)
                continue
            }

            incomingByID[id] = transaction
            incomingOrder.append(id)
            if let key = referenceKey(transaction) {
                incomingReferences.insert(key)
            }
            if let otherKey, incomingCounterparties[otherKey] == nil {
                incomingCounterparties[otherKey] = sourceFile(transaction)
            }
        }

        var existingIDs: Set<String> = []
        var existingReferences: Set<String> = []
        var existingCounterparties: [String: String] = [:]
        if !incomingCounterparties.isEmpty {
            // Build the stored side with the same function, so that it agrees
            // with the incoming side.
            let stored = try TransactionRecord.fetchAll(
                db,
                sql: "SELECT * FROM transactions WHERE description_structured IS NOT NULL"
            )
            for row in stored {
                let asParsed = ParsedTransaction(
                    accountNumber: row.accountNumber,
                    transactiondate: row.transactiondate,
                    amount: Double(truncating: row.amount as NSNumber),
                    description: row.description,
                    descriptionStructured: row.descriptionStructured,
                    sourceFile: row.sourceFile
                )
                if let key = counterpartyKey(asParsed), existingCounterparties[key] == nil {
                    existingCounterparties[key] = row.sourceFile ?? ""
                }
            }
        }
        if !incomingByID.isEmpty {
            let idsRequest = TransactionRecord.select(Column("id"), as: String.self)
            existingIDs = try Set(idsRequest.fetchAll(db))

            let rows = try Row.fetchAll(
                db,
                sql: """
                    SELECT accountNumber, end_to_end_reference, amount
                    FROM transactions WHERE end_to_end_reference IS NOT NULL
                    """
            )
            for row in rows {
                guard let account: String = row["accountNumber"],
                      let reference: String = row["end_to_end_reference"],
                      !reference.isEmpty
                else { continue }
                // The column holds the original text, so the comparison
                // normalizes each stored value as well.
                existingReferences.insert(
                    "\(account)\u{0}\(normalizeReference(reference))\u{0}"
                        + amountKey(fromRow: row, column: "amount")
                )
            }
        }

        var newTransactions: [ParsedTransaction] = []
        newTransactions.reserveCapacity(incomingOrder.count)
        for id in incomingOrder {
            let transaction = incomingByID[id]!
            if existingIDs.contains(id) {
                duplicates.append(transaction)
                continue
            }
            if let key = referenceKey(transaction), existingReferences.contains(key) {
                duplicates.append(transaction)
                continue
            }
            if let key = counterpartyKey(transaction),
               let storedFrom = existingCounterparties[key],
               storedFrom != sourceFile(transaction) {
                duplicates.append(transaction)
                continue
            }
            newTransactions.append(transaction)
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
                transactionHash: transactionHash,
                endToEndReference: extractEndToEndReference(transaction)
            )

            try record.save(db)
            written.append(id)
        }

        return written
    }
}
