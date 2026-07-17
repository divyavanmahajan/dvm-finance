import XCTest

/// Drives the app through its four tabs (and both Budgets sub-tabs) and saves a
/// full-screen screenshot at each stop as a test attachment. Run it to produce
/// App Store screenshots; extract the PNGs from the result bundle with:
///
///     xcrun xcresulttool export attachments \
///       --path <result.xcresult> --output-path <dir>
///
/// The app is launched with `-UITestSeed`, which makes `AppEnvironment` load
/// the deterministic demo dataset (see `DVMFinance/SampleData.swift`) so every
/// screen renders with realistic content.
final class ScreenshotTests: XCTestCase {
    private let app = XCUIApplication()

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    func testCaptureAppStoreScreenshots() {
        app.launchArguments += ["-UITestSeed"]
        app.launch()

        // Wait for first content — the "Transactions" title/tab. On iPhone the
        // tabs are a bottom bar; on iPad (iOS 18) they render differently, so
        // we locate tab controls by label rather than assuming a `tabBars`
        // container.
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 10))
        _ = app.staticTexts["Transactions"].waitForExistence(timeout: 10)
        capture("01-Transactions")

        tapTab("Trends")
        capture("02-Trends")

        tapTab("Budgets")
        capture("03-Budgets-Monthly")

        // The Monthly/Yearly segmented control at the top of the Budgets screen.
        let yearly = button(label: "Yearly")
        if yearly.waitForExistence(timeout: 5) {
            yearly.tap()
            capture("04-Budgets-Yearly")
        }

        tapTab("Import")
        capture("05-Import")

        tapTab("Help")
        capture("06-Help")
    }

    /// A button matched by its visible *label*. Tab buttons expose the SF Symbol
    /// name as their identifier (e.g. `chart.bar`) — different on iPhone vs
    /// iPad — so matching on the accessibility label is the portable approach.
    private func button(label: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "label == %@", label)).firstMatch
    }

    /// Tap a tab by its visible label (works for the iPhone bottom bar and the
    /// iPad top tab bar).
    private func tapTab(_ label: String) {
        let element = button(label: label)
        if element.waitForExistence(timeout: 5) && element.isHittable {
            element.tap()
            return
        }
        XCTFail("could not find tab '\(label)'")
    }

    /// Attach a full-screen screenshot that survives into the result bundle.
    private func capture(_ name: String) {
        usleep(700_000) // let SwiftUI settle animations before grabbing the frame
        let screenshot = XCUIScreen.main.screenshot()
        let attachment = XCTAttachment(screenshot: screenshot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
