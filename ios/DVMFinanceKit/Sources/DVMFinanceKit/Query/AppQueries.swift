import Foundation
import GRDB

/// Async, `AppDatabase`-level entry points for the app target (`ios/DVMFinance/`).
///
/// Every function here takes/returns plain Kit value types (`AppDatabase`,
/// `TransactionFilter`, `TransactionRecord`, ...) and never spells `Database`,
/// `DatabaseWriter`, or any other GRDB type in its signature. This is
/// deliberate: `ios/project.yml` wires the `DVMFinance` app target to depend
/// on the `DVMFinanceKit` **product** only, not on GRDB directly, and
/// Xcode's per-target SPM product visibility does not expose a product's own
/// transitive dependencies to its consumers — a target that never declares
/// `GRDB` as a dependency may not be able to `import GRDB` at all. Routing
/// every `Database`-touching call through this file means the app target
/// never needs to, avoiding that (unverifiable in this sandbox, since no
/// Swift toolchain is available — see `ios/docs/plan.md` "Phase E"
/// constraints) risk entirely.
///
/// All of these just wrap `TransactionQuery`/`TrendsBuilder`/`Dedup`/
/// `Categorizer` calls in an `appDatabase.dbWriter.read`/`.write`; no new
/// query semantics are introduced here.
public enum AppQueries {

    // MARK: - Transactions list

    public static func transactionsPage(
        appDatabase: AppDatabase,
        filter: TransactionFilter,
        today: Date = Date(),
        pageSize: Int = TransactionFilter.pageSize
    ) async throws -> TransactionQuery.Page {
        try await appDatabase.dbWriter.read { db in
            try TransactionQuery.paginate(db: db, filter: filter, today: today, pageSize: pageSize)
        }
    }

    public static func transactionsSum(
        appDatabase: AppDatabase,
        filter: TransactionFilter,
        today: Date = Date()
    ) async throws -> Double {
        try await appDatabase.dbWriter.read { db in
            try TransactionQuery.sum(db: db, filter: filter, today: today)
        }
    }

    public static func distinctEffectiveCategories(appDatabase: AppDatabase) async throws -> [String] {
        try await appDatabase.dbWriter.read { db in
            try TransactionQuery.distinctEffectiveCategories(db: db)
        }
    }

    public static func distinctAccounts(appDatabase: AppDatabase) async throws -> [String] {
        try await appDatabase.dbWriter.read { db in
            try TransactionQuery.distinctAccounts(db: db)
        }
    }

    // MARK: - Transaction detail

    public struct TransactionDetail {
        public var transaction: TransactionRecord
        /// The rule named by `transaction.categorizationSource`, when that
        /// source is a rule id (as opposed to `nil` or `"manual"`).
        public var matchedRule: CategorizationRuleRecord?

        public init(transaction: TransactionRecord, matchedRule: CategorizationRuleRecord?) {
            self.transaction = transaction
            self.matchedRule = matchedRule
        }
    }

    public static func transactionDetail(
        appDatabase: AppDatabase,
        transactionId: String
    ) async throws -> TransactionDetail? {
        try await appDatabase.dbWriter.read { db -> TransactionDetail? in
            guard let transaction = try TransactionRecord.fetchOne(db, key: transactionId) else {
                return nil
            }
            var matchedRule: CategorizationRuleRecord?
            if let source = transaction.categorizationSource, let ruleId = Int64(source) {
                matchedRule = try CategorizationRuleRecord.fetchOne(db, key: ruleId)
            }
            return TransactionDetail(transaction: transaction, matchedRule: matchedRule)
        }
    }

    // MARK: - Trends

    public static func trendsTable(
        appDatabase: AppDatabase,
        params: TrendsBuilder.TrendsParams,
        today: Date = Date()
    ) async throws -> TrendsBuilder.TrendsTable {
        try await appDatabase.dbWriter.read { db in
            try TrendsBuilder.aggregate(db: db, params: params, today: today)
        }
    }

    // MARK: - Statement import orchestration

    public struct StatementImportResult {
        public var imported: Int
        public var duplicates: Int
        public var categorized: Int
        public var uncategorized: Int

        public init(imported: Int, duplicates: Int, categorized: Int, uncategorized: Int) {
            self.imported = imported
            self.duplicates = duplicates
            self.categorized = categorized
            self.uncategorized = uncategorized
        }
    }

    /// Runs the full file-import pipeline in one write transaction: dedup ->
    /// insert -> apply rules to the newly-inserted ids -> an `action =
    /// "import"` audit report.
    ///
    /// Deliberately more than desktop's `core/importer.py:import_file` (which
    /// calls `apply_rules` but never `record_rule_change` — file imports are
    /// unaudited on desktop): `ios/docs/spec.md` "v1 scope" specifically
    /// calls for iOS file imports to be "audited as an import change
    /// report", since iOS has no rule editor and file import is the only
    /// place categorization state changes on this platform.
    public static func importStatementTransactions(
        appDatabase: AppDatabase,
        transactions: [ParsedTransaction]
    ) async throws -> StatementImportResult {
        try await appDatabase.dbWriter.write { db in
            let (newTransactions, duplicates) = try Dedup.checkDuplicates(db: db, transactions: transactions)
            let newIds = try Dedup.insertTransactions(db: db, transactions: newTransactions)
            try Categorizer.applyRules(db: db, transactionIds: newIds)
            try Categorizer.recordRuleChange(db: db, action: "import")
            let categorizedCount = try TransactionQuery.categorizedCount(db: db, ids: newIds)
            return StatementImportResult(
                imported: newIds.count,
                duplicates: duplicates.count,
                categorized: categorizedCount,
                uncategorized: newIds.count - categorizedCount
            )
        }
    }

    // MARK: - Audit history (Import screen)

    public static func snapshotImports(appDatabase: AppDatabase) async throws -> [SnapshotImportRecord] {
        try await appDatabase.dbWriter.read { db in
            try SnapshotImportRecord.order(Column("created_at").desc).fetchAll(db)
        }
    }

    public static func ruleChangeReports(appDatabase: AppDatabase) async throws -> [RuleChangeReportRecord] {
        try await appDatabase.dbWriter.read { db in
            try RuleChangeReportRecord.order(Column("created_at").desc).fetchAll(db)
        }
    }

    public static func ruleChangeItems(
        appDatabase: AppDatabase,
        reportId: Int64
    ) async throws -> [RuleChangeItemRecord] {
        try await appDatabase.dbWriter.read { db in
            try RuleChangeItemRecord
                .filter(Column("report_id") == reportId)
                .order(Column("id").asc)
                .fetchAll(db)
        }
    }
}
