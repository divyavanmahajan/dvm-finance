import XCTest

/// Covers "Delete all data" in the import tab (`ios-data-reset`), and saves
/// screenshots of the screens that this change touches: the trends matrix at
/// rest and after a horizontal scroll, the end of the import tab, the empty
/// transactions tab, and the QR code help.
///
/// Each test starts the app with `-UITestSeed`, so the database holds the
/// sample data (see `DVMFinance/SampleData.swift`).
final class DataResetUITests: XCTestCase {
    private let app = XCUIApplication()

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
        app.launchArguments += ["-UITestSeed"]
        app.launch()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 10))
    }

    func testDeleteAllDataCancelThenConfirm() {
        tapTab("Import")
        let deleteButton = app.buttons["deleteAllDataButton"]
        scrollUntilHittable(deleteButton)
        capture("Import-bottom")

        // Cancel: the app deletes nothing.
        deleteButton.tap()
        let cancel = app.buttons["Cancel"]
        XCTAssertTrue(cancel.waitForExistence(timeout: 5))
        capture("Import-delete-confirmation")
        cancel.tap()
        XCTAssertFalse(app.staticTexts["deleteAllDataMessage"].waitForExistence(timeout: 2))
        tapTab("Transactions")
        XCTAssertFalse(app.buttons["loadSampleDataButton"].waitForExistence(timeout: 3))

        // Confirm: the app deletes all data and shows the count.
        tapTab("Import")
        scrollUntilHittable(deleteButton)
        deleteButton.tap()
        let confirm = app.buttons
            .matching(NSPredicate(format: "label == %@ AND identifier != %@", "Delete all data", "deleteAllDataButton"))
            .firstMatch
        XCTAssertTrue(confirm.waitForExistence(timeout: 5))
        confirm.tap()
        let message = app.staticTexts["deleteAllDataMessage"]
        XCTAssertTrue(message.waitForExistence(timeout: 10))
        XCTAssertTrue(message.label.hasPrefix("Deleted "), message.label)
        XCTAssertFalse(message.label.hasPrefix("Deleted 0 "), message.label)
        // The sample data section shows the load control again.
        XCTAssertTrue(app.buttons["Load sample data"].waitForExistence(timeout: 5))
        capture("Import-after-delete")

        tapTab("Transactions")
        let offer = app.buttons["loadSampleDataButton"]
        XCTAssertTrue(offer.waitForExistence(timeout: 5))
        XCTAssertTrue(offer.isHittable)
        // The button shows its label at the normal height of a button.
        XCTAssertGreaterThanOrEqual(offer.frame.height, 30)
        XCTAssertLessThan(offer.frame.height, 80)
        capture("Transactions-empty")

        // Each other tab shows its empty state.
        tapTab("Trends")
        XCTAssertTrue(app.staticTexts["No Data"].waitForExistence(timeout: 5))
        tapTab("Budgets")
        XCTAssertTrue(app.staticTexts["No Budgets"].waitForExistence(timeout: 5))

        // A load in the transactions tab shows the remove control in the
        // import tab.
        tapTab("Transactions")
        XCTAssertTrue(offer.waitForExistence(timeout: 5))
        offer.tap()
        XCTAssertTrue(offer.waitForNonExistence(timeout: 10))
        tapTab("Import")
        scrollUntilHittable(app.buttons["Remove sample data"])
    }

    /// The category column must not wobble at the start position. The test
    /// scrolls to the right, so the column becomes narrow. Then it drags past
    /// the start, so the scroll view bounces. After that, the width of the
    /// column must settle at the wide value and stay there.
    func testTrendsCategoryColumnSettlesAtTheStart() {
        tapTab("Trends")
        let header = app.descendants(matching: .any)["trendsCategoryHeader"]
        XCTAssertTrue(header.waitForExistence(timeout: 10))
        usleep(700_000)
        let wideWidth = header.frame.width

        let window = app.windows.firstMatch
        let right = window.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5))
        let left = window.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
        right.press(forDuration: 0.05, thenDragTo: left)
        usleep(700_000)
        XCTAssertLessThanOrEqual(header.frame.width, wideWidth)

        // Drag back past the start, twice, so that the scroll view bounces.
        let farRight = window.coordinate(withNormalizedOffset: CGVector(dx: 0.98, dy: 0.5))
        left.press(forDuration: 0.05, thenDragTo: farRight)
        left.press(forDuration: 0.05, thenDragTo: farRight)
        usleep(800_000)

        var samples: [CGFloat] = []
        for _ in 0..<10 {
            samples.append(header.frame.width)
            usleep(150_000)
        }
        XCTAssertEqual(Set(samples).count, 1, "the column width changed at rest: \(samples)")
        XCTAssertEqual(samples.first ?? 0, wideWidth, accuracy: 0.5)
    }

    func testCaptureTrendsAndHelp() {
        tapTab("Trends")
        XCTAssertTrue(app.descendants(matching: .any)["trendsCategoryHeader"].waitForExistence(timeout: 10))
        capture("Trends-at-rest")

        // Scroll the value columns to the right.
        let window = app.windows.firstMatch
        let start = window.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5))
        let end = window.coordinate(withNormalizedOffset: CGVector(dx: 0.78, dy: 0.5))
        start.press(forDuration: 0.05, thenDragTo: end)
        capture("Trends-scrolled")

        // Scroll back to the start.
        let back = window.coordinate(withNormalizedOffset: CGVector(dx: 0.4, dy: 0.5))
        let farRight = window.coordinate(withNormalizedOffset: CGVector(dx: 0.98, dy: 0.5))
        back.press(forDuration: 0.05, thenDragTo: farRight)
        back.press(forDuration: 0.05, thenDragTo: farRight)
        capture("Trends-back-at-start")

        tapTab("Help")
        let troubleshooting = app.staticTexts
            .matching(NSPredicate(format: "label CONTAINS %@", "Turn off a VPN"))
            .firstMatch
        scrollUntilHittable(troubleshooting)
        capture("Help-QR-troubleshooting")
    }

    // MARK: - Helpers

    private func tapTab(_ label: String) {
        let element = app.buttons.matching(NSPredicate(format: "label == %@", label)).firstMatch
        XCTAssertTrue(element.waitForExistence(timeout: 5), "could not find tab '\(label)'")
        element.tap()
    }

    private func scrollUntilHittable(_ element: XCUIElement, attempts: Int = 25) {
        for _ in 0..<attempts {
            if element.exists && element.isHittable { return }
            app.swipeUp()
        }
        XCTAssertTrue(element.exists && element.isHittable, "element not reachable: \(element)")
    }

    private func capture(_ name: String) {
        usleep(700_000)
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
