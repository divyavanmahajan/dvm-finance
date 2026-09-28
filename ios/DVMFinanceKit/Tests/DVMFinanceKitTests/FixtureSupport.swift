import Foundation
import XCTest

/// Shared golden-fixture locator for the `DVMFinanceKitTests` target.
///
/// `Package.swift` declares the fixtures with `.copy("Fixtures")`, which
/// preserves the directory in the built test bundle — so every fixture lives
/// under the bundle's `Fixtures/` subdirectory, not at its root. A bare
/// `Bundle.module.url(forResource:withExtension:)` therefore returns `nil`.
///
/// This helper tries the bundle root first (tolerating a future flattened
/// layout) and falls back to the `Fixtures` subdirectory, giving every
/// fixture-based test one lookup path that finds resources regardless of the
/// copied layout. It handles two-extension names (e.g. `fixture-snapshot.json.gz`)
/// just as `Bundle.url` does.
func fixtureURL(
    _ name: String,
    _ ext: String,
    file: StaticString = #filePath,
    line: UInt = #line
) throws -> URL {
    let url = Bundle.module.url(forResource: name, withExtension: ext)
        ?? Bundle.module.url(forResource: name, withExtension: ext, subdirectory: "Fixtures")
    return try XCTUnwrap(url, "missing fixture \(name).\(ext)", file: file, line: line)
}
