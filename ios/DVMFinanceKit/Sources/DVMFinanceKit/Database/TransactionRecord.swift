import Foundation
import GRDB

/// Port of `src/abn_combined/core/models.py: Transaction`.
///
/// Column-name fidelity (`accountNumber`, `mutationcode`, `transactiondate`,
/// `valuedate`, `startsaldo`, `endsaldo`, ...) is required so the snapshot
/// codec (Phase C) is a plain field-for-field mapping — see
/// `ios/docs/spec.md` "Data model".
///
/// Storage notes:
/// - `id` is the deterministic id computed by
///   `core/dedup.py:generate_transaction_id` (ported in Phase B as
///   `TransactionID.swift`), not a GRDB-assigned rowid — this record type is
///   `PersistableRecord` (not `MutablePersistableRecord`): nothing needs to
///   be captured back from SQLite after insert.
/// - `amount`, `startsaldo`, `endsaldo` are `Decimal` (see
///   `Decimal+DatabaseValueConvertible.swift`) to avoid float precision loss
///   on monetary values.
/// - `transactiondate`/`valuedate` are `DATE` columns stored as `yyyy-MM-dd`
///   (see `DatabaseDateFormat.dateOnly`).
/// - `description_structured` is a JSON `TEXT` column (structured
///   description extraction, ported in Phase D); kept untyped `String?` here
///   since its shape is defined by the Phase D parser, not this layer.
public struct TransactionRecord: Codable, Equatable, FetchableRecord, PersistableRecord {
    public static let databaseTableName = "transactions"

    public var id: String
    public var accountNumber: String
    public var mutationcode: String?
    public var transactiondate: Date
    public var valuedate: Date?
    public var startsaldo: Decimal?
    public var endsaldo: Decimal?
    public var amount: Decimal
    public var description: String?
    public var descriptionStructured: String?
    public var category: String?
    public var manualCategory: String?
    public var tags: String?
    public var manualTags: String?
    public var categorizationSource: String?
    public var currency: String
    public var sourceFile: String?
    public var sourceLine: Int?
    public var transactionTypeCode: String?
    public var transactionReference: String?
    public var transactionHash: String?
    /// Stamped on every write that changes category/tags/manual fields/source
    /// (manual set/clear, bulk-tag, rule recategorization). Powers delta
    /// snapshots ("only transactions changed since <since>"). `nil` for rows
    /// never touched since this column was added (schema `v2`). Port of
    /// `core/models.py: Transaction.updated_at`.
    ///
    /// Stored as an ISO-8601 second-precision **string**
    /// (`yyyy-MM-dd'T'HH:mm:ss`, UTC — `DatabaseDateFormat.dateTime`), **not**
    /// a `Date`: GRDB's per-record `databaseDateDecodingStrategy` is a single
    /// record-wide setting, already pinned to date-only (`yyyy-MM-dd`) for
    /// `transactiondate`/`valuedate`. A `Date`-typed datetime column here
    /// would be silently truncated to day precision by that same strategy.
    /// ISO-8601 strings also sort lexicographically in the same order as
    /// chronologically, so the delta filter (`updated_at >= since`) is a
    /// plain string comparison in SQL. Use `updatedAtDate` for a parsed
    /// `Date`, and `TransactionMutations.timestampNow()` to produce the
    /// stamp string.
    public var updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case accountNumber
        case mutationcode
        case transactiondate
        case valuedate
        case startsaldo
        case endsaldo
        case amount
        case description
        case descriptionStructured = "description_structured"
        case category
        case manualCategory = "manual_category"
        case tags
        case manualTags = "manual_tags"
        case categorizationSource = "categorization_source"
        case currency
        case sourceFile = "source_file"
        case sourceLine = "source_line"
        case transactionTypeCode = "transaction_type_code"
        case transactionReference = "transaction_reference"
        case transactionHash = "transaction_hash"
        case updatedAt = "updated_at"
    }

    public init(
        id: String,
        accountNumber: String,
        mutationcode: String? = nil,
        transactiondate: Date,
        valuedate: Date? = nil,
        startsaldo: Decimal? = nil,
        endsaldo: Decimal? = nil,
        amount: Decimal,
        description: String? = nil,
        descriptionStructured: String? = nil,
        category: String? = nil,
        manualCategory: String? = nil,
        tags: String? = nil,
        manualTags: String? = nil,
        categorizationSource: String? = nil,
        currency: String = "EUR",
        sourceFile: String? = nil,
        sourceLine: Int? = nil,
        transactionTypeCode: String? = nil,
        transactionReference: String? = nil,
        transactionHash: String? = nil,
        updatedAt: String? = nil
    ) {
        self.id = id
        self.accountNumber = accountNumber
        self.mutationcode = mutationcode
        self.transactiondate = transactiondate
        self.valuedate = valuedate
        self.startsaldo = startsaldo
        self.endsaldo = endsaldo
        self.amount = amount
        self.description = description
        self.descriptionStructured = descriptionStructured
        self.category = category
        self.manualCategory = manualCategory
        self.tags = tags
        self.manualTags = manualTags
        self.categorizationSource = categorizationSource
        self.currency = currency
        self.sourceFile = sourceFile
        self.sourceLine = sourceLine
        self.transactionTypeCode = transactionTypeCode
        self.transactionReference = transactionReference
        self.transactionHash = transactionHash
        self.updatedAt = updatedAt
    }

    public static var databaseDateDecodingStrategy: DatabaseDateDecodingStrategy {
        .formatted(DatabaseDateFormat.dateOnly)
    }

    public static var databaseDateEncodingStrategy: DatabaseDateEncodingStrategy {
        .formatted(DatabaseDateFormat.dateOnly)
    }

    /// Effective category = `manual_category ?? category` — spec.md "Key
    /// invariants". Manual edits always win; never computed the other way.
    public var effectiveCategory: String? { manualCategory ?? category }

    /// Effective tags = `manual_tags ?? tags` — spec.md "Key invariants".
    public var effectiveTags: String? { manualTags ?? tags }

    /// `updatedAt` parsed to a `Date` (second precision, UTC), or `nil` if
    /// unset/unparseable. Also tolerates a microseconds-suffixed value the way
    /// `SnapshotCodec.parseDateTime` does, so a desktop-exported
    /// `updated_at` (SQLAlchemy `DateTime` can carry microseconds) round-trips.
    public var updatedAtDate: Date? {
        updatedAt.flatMap(SnapshotCodec.parseDateTime)
    }
}
