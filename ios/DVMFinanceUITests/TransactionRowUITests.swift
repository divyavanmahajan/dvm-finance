import XCTest

/// Covers the full category and tag names in a transaction row
/// (`ios-transaction-review`, "Transaction list"). The app starts with
/// `-UITestSeed -UITestLongNames`, so the newest transaction has a long
/// category and two long tags (see `DVMFinance/SampleData.swift`).
final class TransactionRowUITests: XCTestCase {
    private let app = XCUIApplication()
    private let longCategory = "education-tuition-chelseaballet-weekly-lessons"

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
        app.launchArguments += ["-UITestSeed", "-UITestLongNames"]
        app.launch()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 10))
    }

    func testLongCategoryAndTagNamesShowInFull() {
        // A navigation row merges its texts into one button label, so the
        // test searches the labels.
        let row = app.descendants(matching: .any)
            .matching(NSPredicate(format: "label CONTAINS %@", longCategory)).firstMatch
        let found = row.waitForExistence(timeout: 10)

        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = "Transactions-long-names"
        attachment.lifetime = .keepAlways
        add(attachment)

        XCTAssertTrue(found, "the row does not hold the full category")
        XCTAssertTrue(row.label.contains("school-fees-autumn-term"))
        XCTAssertTrue(row.label.contains("after-school-activities"))
        XCTAssertFalse(row.label.contains("…"), "a name is truncated: \(row.label)")
        // The row stays inside the screen, so the chips wrapped.
        XCTAssertLessThanOrEqual(row.frame.maxX, app.windows.firstMatch.frame.maxX)
    }
}
