import Foundation
import GRDB

/// Wraps the app's single GRDB database connection and owns schema
/// migrations. Mirrors `src/abn_combined/core/models.py` table-for-table
/// (see `ios/docs/spec.md` "Data model"), including its indexes, except
/// `download_state`, which is intentionally **not** ported — there are no
/// downloads on iOS (spec.md: "no downloads ... permanently out of scope").
///
/// This database is never opened by the Python app; sync between desktop and
/// iOS is snapshot-only (Phase C). The schema mirrors desktop 1:1 anyway, to
/// keep every port a plain field-for-field mapping.
public struct AppDatabase {
    public let dbWriter: any DatabaseWriter

    /// Wraps an already-configured `DatabaseWriter` and runs all pending
    /// migrations against it. Prefer `live(at:)` or `inMemory()` below.
    public init(_ dbWriter: any DatabaseWriter) throws {
        self.dbWriter = dbWriter
        try Self.makeMigrator().migrate(dbWriter)
    }

    /// Opens (creating if necessary) the on-disk database at `url`, applying
    /// any pending migrations. The app stores this file under
    /// `Application Support/DVMFinance/dvm_finance.sqlite`
    /// (see `DVMFinance/AppEnvironment.swift`).
    public static func live(at url: URL) throws -> AppDatabase {
        var configuration = Configuration()
        configuration.foreignKeysEnabled = true
        configuration.prepareDatabase { db in
            // WAL improves concurrent read/write behavior; the app is
            // single-process, but SwiftUI previews/background refresh can
            // still open a second connection briefly.
            try db.execute(sql: "PRAGMA journal_mode = WAL")
        }
        let dbPool = try DatabasePool(path: url.path, configuration: configuration)
        return try AppDatabase(dbPool)
    }

    /// In-memory database for tests and SwiftUI previews.
    public static func inMemory() throws -> AppDatabase {
        var configuration = Configuration()
        configuration.foreignKeysEnabled = true
        let dbQueue = try DatabaseQueue(configuration: configuration)
        return try AppDatabase(dbQueue)
    }

    static func makeMigrator() -> DatabaseMigrator {
        var migrator = DatabaseMigrator()

        migrator.registerMigration("v1") { db in
            // MARK: transactions
            //
            // `amount`/`startsaldo`/`endsaldo` use GRDB's `.text` column
            // type (not `.numeric`) even though `core/models.py` declares
            // them `Numeric(15, 2)`. SQLite's NUMERIC/DATE type affinities
            // both fall back to NUMERIC affinity (see sqlite.org/datatype3
            // rule 5), which would make SQLite *itself* try to coerce a
            // numeric-looking TEXT value like "12.30" into a REAL (12.3),
            // silently dropping the trailing zero and reintroducing the
            // float-precision loss `Decimal+DatabaseValueConvertible.swift`
            // exists to avoid. `.text` affinity stores exactly the string
            // GRDB hands SQLite, with no coercion. Date-only/date-time
            // columns keep GRDB's `.date`/`.datetime` types: our formatted
            // date strings (e.g. "2026-07-13") contain non-digit characters
            // that fail SQLite's losslessness check, so they are never
            // coerced away from TEXT storage in practice.
            try db.create(table: "transactions") { t in
                t.column("id", .text).primaryKey()
                t.column("accountNumber", .text).notNull().indexed()
                t.column("mutationcode", .text)
                t.column("transactiondate", .date).notNull().indexed()
                t.column("valuedate", .date)
                t.column("startsaldo", .text)
                t.column("endsaldo", .text)
                t.column("amount", .text).notNull().indexed()
                t.column("description", .text)
                t.column("description_structured", .text)
                t.column("category", .text).indexed()
                t.column("manual_category", .text).indexed()
                t.column("tags", .text)
                t.column("manual_tags", .text)
                t.column("categorization_source", .text)
                t.column("currency", .text).notNull().defaults(to: "EUR")
                t.column("source_file", .text)
                t.column("source_line", .integer)
                t.column("transaction_type_code", .text)
                t.column("transaction_reference", .text)
                t.column("transaction_hash", .text).indexed()
            }
            try db.create(
                index: "idx_account_date",
                on: "transactions",
                columns: ["accountNumber", "transactiondate"]
            )

            // MARK: categorization_rules
            try db.create(table: "categorization_rules") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("uuid", .text).notNull().unique()
                t.column("priority", .integer).notNull().defaults(to: 100)
                t.column("rule_type", .text).notNull()
                t.column("match_pattern", .text).notNull()
                t.column("field_target", .text)
                t.column("match_value", .text).notNull()
                t.column("category", .text)
                t.column("tags", .text)
                t.column("is_active", .boolean).notNull().defaults(to: true)
                t.column("is_tag_only", .boolean).notNull().defaults(to: false)
                t.column("notes", .text)
                t.column("filter_account", .text)
                t.column("filter_currency", .text)
                t.column("filter_date_from", .date)
                t.column("filter_date_to", .date)
            }
            try db.create(
                index: "idx_rules_priority_active",
                on: "categorization_rules",
                columns: ["priority", "is_active"]
            )
            try db.create(index: "idx_rules_type", on: "categorization_rules", columns: ["rule_type"])
            // `uuid`'s `.unique()` column modifier above already creates the
            // backing unique index; no separate `db.create(index:)` call
            // is needed.

            // MARK: rule_conditions
            try db.create(table: "rule_conditions") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("rule_id", .integer)
                    .notNull()
                    .indexed()
                    .references("categorization_rules", column: "id", onDelete: .cascade)
                t.column("field_target", .text).notNull()
                t.column("match_pattern", .text).notNull()
                t.column("match_value", .text).notNull()
                t.column("operator", .text).notNull().defaults(to: "AND")
                t.column("sort_order", .integer).notNull().defaults(to: 0)
            }

            // MARK: budgets
            try db.create(table: "budgets") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("category", .text).notNull()
                t.column("amount", .text).notNull()
                t.column("period", .text).notNull()
                t.column("start_date", .date)
                t.column("end_date", .date)
                t.column("notes", .text)
                t.column("created_at", .date)
                t.column("updated_at", .date)
            }
            try db.create(index: "idx_budgets_category", on: "budgets", columns: ["category"])
            try db.create(index: "idx_budgets_period", on: "budgets", columns: ["period"])
            try db.create(
                index: "idx_budgets_category_period",
                on: "budgets",
                columns: ["category", "period"],
                unique: true
            )

            // MARK: rule_change_reports
            try db.create(table: "rule_change_reports") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("created_at", .datetime).notNull().indexed()
                t.column("rule_id", .integer).indexed()
                t.column("rule_uuid", .text).indexed()
                t.column("action", .text).notNull()
                t.column("rule_before", .text)
                t.column("rule_after", .text)
                t.column("summary", .text)
            }

            // MARK: rule_change_items
            try db.create(table: "rule_change_items") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("report_id", .integer)
                    .notNull()
                    .indexed()
                    .references("rule_change_reports", column: "id", onDelete: .cascade)
                t.column("transaction_id", .text).notNull().indexed()
                t.column("old_category", .text)
                t.column("new_category", .text)
                t.column("old_tags", .text)
                t.column("new_tags", .text)
            }

            // MARK: snapshot_imports
            try db.create(table: "snapshot_imports") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("created_at", .datetime).notNull().indexed()
                t.column("source_machine_id", .text)
                t.column("schema_version", .integer)
                t.column("counts", .text)
                t.column("overwrites", .text)
            }

            // NOTE: `download_state` (core/models.py) is intentionally not
            // created here — see spec.md "Data model": no downloads on iOS.
        }

        // MARK: v2 — updated_at + delta-snapshot support
        //
        // Mirrors desktop Alembic revision
        // `7dd060546159_add_updated_at_export_state_snapshot_delta`.
        // Append-only (never edit v1): `updated_at` stamps every write that
        // changes category/tags/manual fields/source (manual set/clear,
        // bulk-tag, rule recategorization) so a delta snapshot can carry
        // "only transactions changed since <since>". `export_state` tracks the
        // last delta-export boundary; `snapshot_imports` gains delta
        // provenance columns.
        migrator.registerMigration("v2") { db in
            // `.text` affinity (a raw ISO-8601 string, like the amount/date
            // columns in v1) — `TransactionRecord.updatedAt` is a `String`,
            // and a lexicographic index over ISO-8601 strings orders the same
            // as chronological order, which is what the delta filter needs.
            try db.alter(table: "transactions") { t in
                t.add(column: "updated_at", .text).indexed()
            }

            try db.create(table: "export_state") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("last_delta_export_at", .datetime)
            }

            try db.alter(table: "snapshot_imports") { t in
                t.add(column: "is_delta", .boolean).notNull().defaults(to: false)
                t.add(column: "delta_since", .datetime)
            }
        }

        return migrator
    }
}
