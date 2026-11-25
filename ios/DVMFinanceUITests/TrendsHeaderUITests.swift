import XCTest

/// Covers the pinned header row of the trends matrix (`ios-category-trends`,
/// "The header row stays visible"). The app starts with `-UITestSeed
/// -UITestManyCategories`, so the matrix has more rows than one screen.
final class TrendsHeaderUITests: XCTestCase {
    private let app = XCUIApplication()

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
        app.launchArguments += ["-UITestSeed", "-UITestManyCategories"]
        app.launch()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 10))
        let trends = app.buttons.matching(NSPredicate(format: "label == %@", "Trends")).firstMatch
        XCTAssertTrue(trends.waitForExistence(timeout: 5))
        trends.tap()
        XCTAssertTrue(header.waitForExistence(timeout: 10))
        usleep(700_000)
    }

    private var header: XCUIElement { app.descendants(matching: .any)["trendsCategoryHeader"] }
    private var firstCell: XCUIElement { app.descendants(matching: .any)["trendsCategoryCell"].firstMatch }

    func testHeaderStaysVisibleWhileTheRowsScroll() {
        // The extra categories fall in the current month. The default window
        // holds only full months, so the test selects the 3-month window.
        let threeMonths = app.buttons["3mo"]
        XCTAssertTrue(threeMonths.waitForExistence(timeout: 5))
        threeMonths.tap()
        XCTAssertTrue(app.descendants(matching: .any)
            .matching(NSPredicate(format: "label == %@", "testcategory01")).firstMatch
            .waitForExistence(timeout: 5), "the extra categories are missing")
        usleep(800_000)
        let headerY = header.frame.minY
        let firstRowY = firstCell.frame.minY

        app.windows.firstMatch.coordinate(withNormalizedOffset: CGVector(dx: 0.6, dy: 0.75))
            .press(forDuration: 0.05, thenDragTo: app.windows.firstMatch
                .coordinate(withNormalizedOffset: CGVector(dx: 0.6, dy: 0.35)))
        usleep(800_000)

        XCTAssertLessThan(firstCell.frame.minY, firstRowY - 50, "the rows did not scroll")
        XCTAssertEqual(header.frame.minY, headerY, accuracy: 0.5, "the header moved with the rows")
        XCTAssertTrue(header.isHittable)
        capture("Trends-header-pinned")

        // The pinned header keeps its tap action.
        header.tap()
        XCTAssertEqual(header.value as? String, "Shows all names")
    }

    func testMonthHeadersStayAboveTheirColumns() {
        checkMonthHeadersAfterAScroll(minimumColumns: 2)
    }

    /// Scrolls the months to the right, and checks that each fully visible
    /// month header ends at the same x position as its value column.
    private func checkMonthHeadersAfterAScroll(minimumColumns: Int) {
        let window = app.windows.firstMatch
        window.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5))
            .press(forDuration: 0.05, thenDragTo: window.coordinate(withNormalizedOffset: CGVector(dx: 0.55, dy: 0.5)))
        usleep(800_000)

        // The category column and its header stay at the leading edge.
        XCTAssertEqual(header.frame.minX, window.frame.minX, accuracy: 1, "the category header moved")
        XCTAssertTrue(header.isHittable)

        let headers = app.descendants(matching: .any)
            .matching(NSPredicate(format: "identifier BEGINSWITH %@", "trendsPeriodHeader-"))
        var compared = 0
        for index in 0..<headers.count {
            let periodHeader = headers.element(boundBy: index)
            let key = String(periodHeader.identifier.dropFirst("trendsPeriodHeader-".count))
            let cell = app.descendants(matching: .any)["trendsCell-\(key)"].firstMatch
            guard cell.exists, periodHeader.frame.minX > header.frame.maxX, periodHeader.frame.maxX < window.frame.maxX else {
                continue
            }
            XCTAssertEqual(periodHeader.frame.maxX, cell.frame.maxX, accuracy: 1, "header \(key) is not above its column")
            compared += 1
        }
        XCTAssertGreaterThanOrEqual(compared, minimumColumns, "the test compared too few columns")
        capture("Trends-header-scrolled")
    }

    /// At the largest accessibility text size, the header row and the body
    /// rows must still line up.
    func testHeaderStaysAlignedAtTheLargestTextSize() {
        app.terminate()
        app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        let trends = app.buttons.matching(NSPredicate(format: "label == %@", "Trends")).firstMatch
        XCTAssertTrue(trends.waitForExistence(timeout: 10))
        trends.tap()
        XCTAssertTrue(header.waitForExistence(timeout: 10))
        usleep(800_000)

        XCTAssertEqual(header.frame.maxY, firstCell.frame.minY, accuracy: 1, "the first row is not right below the header")
        // Only one month column fits on the screen at this text size.
        checkMonthHeadersAfterAScroll(minimumColumns: 1)
        capture("Trends-header-largest-text")
    }

    private func capture(_ name: String) {
        usleep(400_000)
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
