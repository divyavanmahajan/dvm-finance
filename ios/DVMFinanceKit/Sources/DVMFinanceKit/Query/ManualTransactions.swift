import Foundation
import GRDB

/// Hand-entered transactions: the create, the edit, the flag, the restore,
/// and the purge.
///
/// Port of `src/abn_combined/core/manual_txn.py`:
/// `create_manual_transaction`, `edit_manual_transaction`,
/// `flag_manual_transaction`, `restore_manual_transaction`, and
/// `purge_flagged_transactions`, with the helpers `_validate`,
/// `_clean_tags`, `_content_hash`, and `_get_manual_row`. The two
/// applications hold the same observable behavior:
///
/// - A hand-entered row belongs to the fixed pseudo account `CASH`.
/// - A hand-entered row carries a UUID id, not the content-derived id of
///   `TransactionID.generateTransactionID`. The identity therefore survives
///   an edit, and the two devices never mint the same id for two different
///   payments. A merge of the two snapshots is a union.
/// - The typed category is a *manual* category, and the typed tags are
///   *manual* tags. The category pass of `Categorizer.applyRules` skips the
///   row, exactly as it skips a manually categorized transaction. A tag-only
///   rule still adds a tag.
/// - A removal is a flag in `deleted_at`, not a delete. Only the purge
///   deletes a row.
///
/// Each function that writes stamps `updated_at`, so that the change reaches
/// the computer in the next delta snapshot.
public enum ManualTransactions {

    /// The reserved identifier of the fixed pseudo account. It is identical
    /// on both devices. The app creates no other pseudo account, and it never
    /// writes a hand-entered transaction to a bank account.
    public static let cashAccount = "CASH"

    /// The reasons the app refuses a create, an edit, a flag, or a restore.
    /// Each case carries a message for the user.
    public enum ManualTransactionError: Error, LocalizedError, Equatable {
        case missingDate
        case missingAmount
        case zeroAmount
        case missingDescription
        case transactionNotFound(String)
        /// The row exists, but the user did not type it. Only a hand-entered
        /// row accepts an edit, a flag, and a restore.
        case notHandEntered(String)

        public var errorDescription: String? {
            switch self {
            case .missingDate:
                return "Give the transaction a date."
            case .missingAmount:
                return "Give the transaction an amount."
            case .zeroAmount:
                return "The amount must not be zero."
            case .missingDescription:
                return "Give the transaction a description."
            case .transactionNotFound(let id):
                return "This transaction no longer exists (\(id))."
            case .notHandEntered:
                return "This transaction comes from a statement. "
                    + "You can change its category and its tags only."
            }
        }
    }

    // MARK: - The typed form

    /// The values of the create form and of the edit form.
    ///
    /// The date, the amount, and the description are required. The category
    /// and the tags are optional. `amount` is a `Decimal?` and not a string,
    /// because the view parses the typed text; a text that does not parse
    /// reaches this type as `nil` and the create refuses the form with
    /// `missingAmount`.
    public struct Input: Equatable {
        public var date: Date?
        public var amount: Decimal?
        public var description: String
        public var category: String
        public var tags: String

        public init(
            date: Date? = nil,
            amount: Decimal? = nil,
            description: String = "",
            category: String = "",
            tags: String = ""
        ) {
            self.date = date
            self.amount = amount
            self.description = description
            self.category = category
            self.tags = tags
        }
    }

    /// Port of `core/manual_txn.py:_validate`.
    ///
    /// Checks the form and returns its clean values. The app refuses a form
    /// without a date, without an amount, with an amount of zero, or without
    /// a description, and it writes nothing. This is identical to the
    /// desktop application.
    static func validate(
        _ input: Input
    ) throws -> (date: Date, amount: Decimal, description: String) {
        guard let date = input.date else { throw ManualTransactionError.missingDate }
        guard let amount = input.amount else { throw ManualTransactionError.missingAmount }
        guard amount != 0 else { throw ManualTransactionError.zeroAmount }
        let description = input.description.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !description.isEmpty else { throw ManualTransactionError.missingDescription }
        return (date, amount, description)
    }

    /// Port of `core/manual_txn.py:_clean_tags`.
    ///
    /// Cleans a typed tag list, with the rule of
    /// `api/transactions.py:set_manual_tags`: trim each part, drop each empty
    /// part, and join the rest with a comma and a space. The case of a tag
    /// stays as the user typed it. An empty result reads as `nil`.
    static func cleanTags(_ tags: String) -> String? {
        let cleaned = tags
            .split(separator: ",", omittingEmptySubsequences: false)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
            .joined(separator: ", ")
        return cleaned.isEmpty ? nil : cleaned
    }

    // MARK: - Create

    /// Port of `core/manual_txn.py:create_manual_transaction`. Creates one
    /// hand-entered transaction in the account `CASH`.
    ///
    /// The row holds a UUID id, `is_manual` true, the typed category in
    /// `manual_category`, the typed tags in `manual_tags`, and a content hash
    /// in `transaction_hash`. `categorization_source` reads `"manual"`, so
    /// the category pass of `Categorizer.applyRules` skips the row.
    @discardableResult
    public static func create(db: Database, input: Input) throws -> TransactionRecord {
        let (date, amount, description) = try validate(input)
        let record = TransactionRecord(
            id: UUID().uuidString,
            accountNumber: cashAccount,
            transactiondate: date,
            amount: amount,
            description: description,
            category: nil,
            manualCategory: CoreNormalize.normalizeCategory(input.category),
            tags: nil,
            manualTags: cleanTags(input.tags),
            categorizationSource: Categorizer.manualSource,
            currency: "EUR",
            transactionHash: hash(date: date, description: description, amount: amount),
            updatedAt: TransactionMutations.timestampNow(),
            isManual: true,
            deletedAt: nil
        )
        try record.insert(db)
        return record
    }

    /// Port of `core/manual_txn.py:_content_hash`. The content hash of a
    /// hand-entered row, through the same helper the
    /// file import uses (`core/utils.py:calculate_transaction_hash`).
    static func hash(date: Date, description: String, amount: Decimal) -> String {
        CoreNormalize.calculateTransactionHash(
            date: date,
            description: description,
            amount: CoreNormalize.HashAmountInput(amount),
            account: cashAccount
        )
    }

    // MARK: - Edit

    /// Port of `core/manual_txn.py:edit_manual_transaction`. Changes the
    /// date, the amount, the description, the category, and the tags of a
    /// hand-entered transaction.
    ///
    /// The row keeps its id, the function recomputes the content hash, and it
    /// stamps `updated_at`, so that a delta export carries the new values.
    /// The function refuses an imported transaction.
    @discardableResult
    public static func edit(
        db: Database,
        transactionId: String,
        input: Input
    ) throws -> TransactionRecord {
        var record = try fetchHandEntered(db, transactionId)
        let (date, amount, description) = try validate(input)
        record.transactiondate = date
        record.amount = amount
        record.description = description
        record.manualCategory = CoreNormalize.normalizeCategory(input.category)
        record.manualTags = cleanTags(input.tags)
        // Pinned, and never cleared the way `clearManualCategory` clears it:
        // a hand-entered row must stay out of the category pass even when the
        // user removes the category again.
        record.categorizationSource = Categorizer.manualSource
        record.transactionHash = hash(date: date, description: description, amount: amount)
        record.updatedAt = TransactionMutations.timestampNow()
        try record.update(db)
        return record
    }

    // MARK: - Flag and restore

    /// Port of `core/manual_txn.py:flag_manual_transaction`. Flags a
    /// hand-entered transaction for removal.
    ///
    /// The function writes the time of the flag in `deleted_at`. It deletes
    /// no row. It stamps `updated_at`, so that the flag reaches the computer
    /// in a delta snapshot as well as in a full snapshot. It refuses an
    /// imported transaction.
    @discardableResult
    public static func flag(db: Database, transactionId: String) throws -> TransactionRecord {
        var record = try fetchHandEntered(db, transactionId)
        let now = TransactionMutations.timestampNow()
        record.deletedAt = now
        record.updatedAt = now
        try record.update(db)
        return record
    }

    /// Port of `core/manual_txn.py:restore_manual_transaction`. Removes the
    /// flag from a hand-entered transaction. The row appears
    /// again in each list and in each total. The function refuses an imported
    /// transaction.
    @discardableResult
    public static func restore(db: Database, transactionId: String) throws -> TransactionRecord {
        var record = try fetchHandEntered(db, transactionId)
        record.deletedAt = nil
        record.updatedAt = TransactionMutations.timestampNow()
        try record.update(db)
        return record
    }

    /// Port of `core/manual_txn.py:_get_manual_row`. Reads one row and
    /// refuses it when the user did not type it. This is
    /// the one gate of the edit, of the flag, and of the restore.
    static func fetchHandEntered(_ db: Database, _ transactionId: String) throws -> TransactionRecord {
        guard let record = try TransactionRecord.fetchOne(db, key: transactionId) else {
            throw ManualTransactionError.transactionNotFound(transactionId)
        }
        guard record.isManual else {
            throw ManualTransactionError.notHandEntered(transactionId)
        }
        return record
    }

    // MARK: - The flagged rows

    /// Each flagged transaction, newest flag first. The user reads this list
    /// before the purge. It is the one list of the app that shows a flagged
    /// row.
    public static func flaggedTransactions(db: Database) throws -> [TransactionRecord] {
        try TransactionRecord.fetchAll(
            db,
            sql: "SELECT * FROM transactions WHERE deleted_at IS NOT NULL "
                + "ORDER BY deleted_at DESC, id ASC"
        )
    }

    /// The number of the flagged transactions. The purge control shows it.
    public static func flaggedCount(db: Database) throws -> Int {
        try Int.fetchOne(
            db,
            sql: "SELECT COUNT(*) FROM transactions WHERE deleted_at IS NOT NULL"
        ) ?? 0
    }

    // MARK: - Purge

    /// The result of a purge: the number of the deleted rows, and the backup
    /// that the purge wrote first. `backupURL` is `nil` when the database
    /// file does not exist, which happens for an in-memory database in a
    /// test.
    public struct PurgeResult: Equatable {
        public var deleted: Int
        public var backupURL: URL?

        public init(deleted: Int, backupURL: URL?) {
            self.deleted = deleted
            self.backupURL = backupURL
        }
    }

    /// Port of `core/manual_txn.py:purge_flagged_transactions`. Deletes each
    /// flagged transaction from the local database.
    ///
    /// The purge copies the database to a timestamped backup first, through
    /// the same helper the snapshot import uses
    /// (`SnapshotImporter.backupDatabaseFile`, the port of
    /// `core/snapshots.py:_backup_db`). It then deletes each flagged row and
    /// no other row, and it reports the number of the deleted rows. The app
    /// cannot undo the purge, so the caller asks the user to confirm first.
    ///
    /// A purged row can return. A later snapshot of the computer that still
    /// holds the row brings it back with its flag, and it stays out of each
    /// list and each total. This is harmless, and it needs no tombstone.
    @discardableResult
    public static func purgeFlagged(
        appDatabase: AppDatabase,
        databaseURL: URL
    ) throws -> PurgeResult {
        var backupURL: URL?
        if FileManager.default.fileExists(atPath: databaseURL.path) {
            backupURL = try SnapshotImporter.backupDatabaseFile(
                appDatabase: appDatabase,
                databaseURL: databaseURL
            )
        }
        let deleted = try appDatabase.dbWriter.write { db -> Int in
            try db.execute(sql: "DELETE FROM transactions WHERE deleted_at IS NOT NULL")
            return db.changesCount
        }
        return PurgeResult(deleted: deleted, backupURL: backupURL)
    }
}
