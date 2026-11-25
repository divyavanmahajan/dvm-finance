import XCTest

/// Covers the full category name on request and the header that keeps the
/// category column wide (`ios-category-trends`, design D2a). The app starts
/// with `-UITestSeed`, so the database holds the sample data.
final class TrendsCategoryUITests: XCTestCase {
    private let app = XCUIApplication()

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
        app.launchArguments += ["-UITestSeed"]
        app.launch()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 10))
        let trends = app.buttons.matching(NSPredicate(format: "label == %@", "Trends")).firstMatch
        XCTAssertTrue(trends.waitForExistence(timeout: 5))
        trends.tap()
        XCTAssertTrue(header.waitForExistence(timeout: 10))
    }

    private var header: XCUIElement { app.descendants(matching: .any)["trendsCategoryHeader"] }
    private var firstCell: XCUIElement { app.descendants(matching: .any)["trendsCategoryCell"].firstMatch }
    private var fullName: XCUIElement { app.descendants(matching: .any)["trendsFullName"] }
    private var hint: XCUIElement { app.descendants(matching: .any)["trendsFullNameHint"] }

    func testLongPressShowsTheFullNameAndTheHint() {
        let name = firstCell.label
        firstCell.press(forDuration: 0.8)
        XCTAssertTrue(fullName.waitForExistence(timeout: 5), "no popover after a long press")
        XCTAssertEqual(fullName.label, name)
        XCTAssertTrue(hint.exists, "the popover has no hint")
        capture("Trends-full-name-popover")

        // A tap outside closes the popover.
        app.windows.firstMatch.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.15)).tap()
        XCTAssertFalse(fullName.waitForExistence(timeout: 2))
    }

    func testHeaderKeepsTheColumnWideAndHidesTheHint() {
        usleep(700_000)
        let wideWidth = header.frame.width
        header.tap()
        XCTAssertEqual(header.value as? String, "Shows all names")

        // A scroll to the right does not make the column narrow.
        let window = app.windows.firstMatch
        let right = window.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5))
        let left = window.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
        right.press(forDuration: 0.05, thenDragTo: left)
        usleep(700_000)
        XCTAssertEqual(header.frame.width, wideWidth, accuracy: 0.5)
        capture("Trends-kept-wide-scrolled")

        // While the column stays wide, the popover shows no hint.
        firstCell.press(forDuration: 0.8)
        XCTAssertTrue(fullName.waitForExistence(timeout: 5))
        XCTAssertFalse(hint.exists)
        app.windows.firstMatch.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.15)).tap()

        // A second tap returns the column to the automatic width.
        header.tap()
        XCTAssertEqual(header.value as? String, "Automatic width")
    }

    private func capture(_ name: String) {
        usleep(500_000)
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
