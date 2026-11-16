#if DEBUG
import Foundation
import DVMFinanceKit
import GRDB

/// The screenshot and UI-test hook for the demo data. It is compiled only
/// into a Debug build, because the whole file is behind `#if DEBUG`.
///
/// `AppEnvironment` calls it when the app starts with the `-UITestSeed`
/// argument (see `DVMFinanceUITests/ScreenshotTests.swift`). Unlike the
/// user-facing "Load sample data" control, this hook first deletes every
/// transaction and every budget, so that each screenshot run starts from the
/// same state. The data itself is `DVMFinanceKit.SampleDataset`.
enum SampleData {
    static func populate(into appDatabase: AppDatabase) throws {
        try appDatabase.dbWriter.write { db in
            try TransactionRecord.deleteAll(db)
            try BudgetRecord.deleteAll(db)
            try SampleDataset.insert(db: db)
        }
    }

    /// With `-UITestLongNames`, the newest sample transaction gets a long
    /// category and two long tags, so a UI test can check that a row shows
    /// each name in full.
    static let longCategory = "education-tuition-chelseaballet-weekly-lessons"
    static let longTags = "school-fees-autumn-term, after-school-activities"

    static func applyLongNames(to appDatabase: AppDatabase) throws {
        try appDatabase.dbWriter.write { db in
            try db.execute(
                sql: """
                    UPDATE transactions SET category = ?, tags = ?
                    WHERE id = (SELECT id FROM transactions ORDER BY transactiondate DESC LIMIT 1)
                    """,
                arguments: [longCategory, longTags]
            )
        }
    }
}
#endif
