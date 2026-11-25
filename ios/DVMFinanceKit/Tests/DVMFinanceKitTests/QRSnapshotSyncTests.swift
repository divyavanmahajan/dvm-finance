import XCTest
@testable import DVMFinanceKit

/// Camera-free coverage for "Sync from computer" (`Sync/QRSnapshotSync.swift`):
/// QR payload validation and the download step's error mapping via a stubbed
/// transport, plus the download→decode→import orchestration against the
/// Python-generated `Fixtures/fixture-snapshot.json.gz`. The scanner view
/// itself (VisionKit) lives in the app target and is not unit-tested.
final class QRSnapshotSyncTests: XCTestCase {

    // MARK: - QRSyncPayload validation

    func testAcceptsPlainHTTPURL() throws {
        let url = try QRSyncPayload.url(from: "http://192.168.1.23:54321/abc123token")
        XCTAssertEqual(url.absoluteString, "http://192.168.1.23:54321/abc123token")
    }

    func testAcceptsHTTPSURLAndTrimsWhitespace() throws {
        let url = try QRSyncPayload.url(from: "  https://mac.local:8443/tok\n")
        XCTAssertEqual(url.absoluteString, "https://mac.local:8443/tok")
    }

    func testUppercaseSchemeIsAccepted() throws {
        let url = try QRSyncPayload.url(from: "HTTP://192.168.0.5:1234/t")
        XCTAssertEqual(url.host, "192.168.0.5")
    }

    func testRejectsEmptyPayload() {
        XCTAssertThrowsError(try QRSyncPayload.url(from: "   ")) { error in
            XCTAssertEqual(error as? QRSyncError, .notAWebURL)
        }
    }

    func testRejectsNonURLText() {
        XCTAssertThrowsError(try QRSyncPayload.url(from: "hello world, not a link")) { error in
            XCTAssertEqual(error as? QRSyncError, .notAWebURL)
        }
    }

    func testRejectsRelativeURLWithoutSchemeOrHost() {
        XCTAssertThrowsError(try QRSyncPayload.url(from: "/just/a/path")) { error in
            XCTAssertEqual(error as? QRSyncError, .notAWebURL)
        }
    }

    func testRejectsSchemeWithoutHost() {
        XCTAssertThrowsError(try QRSyncPayload.url(from: "http://")) { error in
            XCTAssertEqual(error as? QRSyncError, .notAWebURL)
        }
    }

    func testRejectsNonWebSchemes() {
        for payload in ["ftp://192.168.1.2/file", "file:///etc/passwd", "mailto:someone@example.com", "javascript:alert(1)"] {
            XCTAssertThrowsError(try QRSyncPayload.url(from: payload), payload) { error in
                guard case .unsupportedScheme = error as? QRSyncError else {
                    return XCTFail("expected unsupportedScheme for \(payload), got \(error)")
                }
            }
        }
    }

    // MARK: - isLocalNetworkHost classification

    func testLocalNetworkHostsAreDetected() {
        let local = [
            "10.0.0.1", "10.255.255.254",
            "172.16.0.1", "172.20.1.1", "172.31.255.254",
            "192.168.1.23", "192.168.0.1",
            "169.254.1.1",           // link-local
            "127.0.0.1",             // loopback
            "localhost",
            "mac.local", "My-MacBook.local",
            "::1",                   // IPv6 loopback
            "fe80::1", "fd00::1234", // IPv6 link-local / unique-local
        ]
        for host in local {
            XCTAssertTrue(QRSyncPayload.isLocalNetworkHost(host), "expected \(host) to be local")
        }
    }

    func testPublicHostsAreNotLocal() {
        let public_ = [
            "8.8.8.8", "1.1.1.1",
            "172.15.0.1", "172.32.0.1",   // just outside 172.16/12
            "192.169.0.1", "11.0.0.1",
            "example.com", "api.example.org",
            "2001:4860:4860::8888",       // public IPv6 (Google DNS)
        ]
        for host in public_ {
            XCTAssertFalse(QRSyncPayload.isLocalNetworkHost(host), "expected \(host) to be public")
        }
    }

    func testIsLocalNetworkHostURLOverload() {
        XCTAssertTrue(QRSyncPayload.isLocalNetworkHost(URL(string: "http://192.168.1.23:54321/tok")!))
        XCTAssertTrue(QRSyncPayload.isLocalNetworkHost(URL(string: "http://[fe80::1]:8080/tok")!))
        XCTAssertFalse(QRSyncPayload.isLocalNetworkHost(URL(string: "https://example.com/tok")!))
    }

    // MARK: - SnapshotURLDownloader error mapping (stubbed transport)

    private static let testURL = URL(string: "http://192.168.1.23:54321/token")!

    private func downloader(status: Int, body: Data) -> SnapshotURLDownloader {
        SnapshotURLDownloader { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: status,
                httpVersion: "HTTP/1.1",
                headerFields: nil
            )!
            return (body, response)
        }
    }

    func testSuccessfulDownloadReturnsBody() async throws {
        let body = Data("snapshot-bytes".utf8)
        let data = try await downloader(status: 200, body: body).download(from: Self.testURL)
        XCTAssertEqual(data, body)
    }

    func testGoneAndNotFoundMapToLinkAlreadyUsed() async {
        for status in [404, 410] {
            do {
                _ = try await downloader(status: status, body: Data()).download(from: Self.testURL)
                XCTFail("expected linkAlreadyUsed for HTTP \(status)")
            } catch {
                XCTAssertEqual(error as? QRSyncError, .linkAlreadyUsed, "HTTP \(status)")
            }
        }
    }

    func testOtherHTTPErrorMapsToServerError() async {
        do {
            _ = try await downloader(status: 500, body: Data()).download(from: Self.testURL)
            XCTFail("expected serverError")
        } catch {
            XCTAssertEqual(error as? QRSyncError, .serverError(statusCode: 500))
        }
    }

    func testConnectionRefusedToPublicHostMapsToServerUnreachable() async {
        let downloader = SnapshotURLDownloader { _ in
            throw URLError(.cannotConnectToHost)
        }
        do {
            _ = try await downloader.download(from: URL(string: "https://example.com/tok")!)
            XCTFail("expected serverUnreachable")
        } catch {
            XCTAssertEqual(error as? QRSyncError, .serverUnreachable)
        }
    }

    func testTimeoutMapsToServerUnreachable() async {
        // A public host is used here so the local-network branch doesn't fire.
        let downloader = SnapshotURLDownloader { _ in
            throw URLError(.timedOut)
        }
        do {
            _ = try await downloader.download(from: URL(string: "https://example.com/tok")!)
            XCTFail("expected serverUnreachable")
        } catch {
            XCTAssertEqual(error as? QRSyncError, .serverUnreachable)
        }
    }

    func testSameConnectionFailureToPublicHostMapsToServerUnreachable() async {
        let downloader = SnapshotURLDownloader { _ in
            throw URLError(URLError.Code(rawValue: -1004))
        }
        do {
            _ = try await downloader.download(from: URL(string: "https://example.com/tok")!)
            XCTFail("expected serverUnreachable")
        } catch {
            XCTAssertEqual(error as? QRSyncError, .serverUnreachable)
        }
    }

    // MARK: - Local-network failure classification (design D1)

    private static let lanURL = URL(string: "http://192.168.1.23:54321/tok")!

    /// A downloader whose transport throws `error`, with a fixed probe.
    private func failingDownloader(
        _ error: URLError,
        permissionDenied: Bool = false
    ) -> SnapshotURLDownloader {
        SnapshotURLDownloader(
            transport: { _ in throw error },
            permissionProbe: { _ in permissionDenied }
        )
    }

    private func classify(
        _ error: URLError,
        url: URL = lanURL,
        permissionDenied: Bool = false,
        file: StaticString = #filePath,
        line: UInt = #line
    ) async -> QRSyncError? {
        do {
            _ = try await failingDownloader(error, permissionDenied: permissionDenied).download(from: url)
            XCTFail("expected a QRSyncError", file: file, line: line)
            return nil
        } catch {
            return error as? QRSyncError
        }
    }

    /// The shape that iOS gives for a refused TCP connection: the POSIX
    /// code in `_kCFStreamErrorCodeKey`, and an underlying error.
    private static func refusedWithStreamCode() -> URLError {
        URLError(.cannotConnectToHost, userInfo: [
            "_kCFStreamErrorCodeKey": 61,
            "_kCFStreamErrorDomainKey": 1,
        ])
    }

    /// The other known shape: an underlying POSIX error with code 61, one
    /// level down in the chain.
    private static func refusedWithUnderlyingPOSIXError() -> URLError {
        let posix = NSError(domain: NSPOSIXErrorDomain, code: 61)
        let cfNetwork = NSError(domain: "kCFErrorDomainCFNetwork", code: -1004, userInfo: [NSUnderlyingErrorKey: posix])
        return URLError(.cannotConnectToHost, userInfo: [NSUnderlyingErrorKey: cfNetwork])
    }

    func testRefusedConnectionWithStreamCodeMapsToShareStopped() async {
        let result = await classify(Self.refusedWithStreamCode())
        XCTAssertEqual(result, .shareStopped)
    }

    func testRefusedConnectionWithUnderlyingPOSIXErrorMapsToShareStopped() async {
        let result = await classify(Self.refusedWithUnderlyingPOSIXError())
        XCTAssertEqual(result, .shareStopped)
    }

    func testRefusedConnectionWithPermissionAllowedIsNotThePermissionMessage() async {
        // The field report: the permission is on and the share expired.
        let result = await classify(Self.refusedWithStreamCode(), permissionDenied: false)
        XCTAssertEqual(result, .shareStopped)
        XCTAssertNotEqual(result, .localNetworkPermissionDenied)
    }

    func testProbeThatReportsDeniedWinsOverRefused() async {
        let result = await classify(Self.refusedWithStreamCode(), permissionDenied: true)
        XCTAssertEqual(result, .localNetworkPermissionDenied)
    }

    func testProbeThatReportsDeniedMapsTimeoutToPermission() async {
        let result = await classify(URLError(.timedOut), permissionDenied: true)
        XCTAssertEqual(result, .localNetworkPermissionDenied)
    }

    func testLocalNetworkProhibitedPathTextMapsToPermission() async {
        let error = URLError(.notConnectedToInternet, userInfo: [
            "_NSURLErrorNWPathKey": "unsatisfied (Local network prohibited), interface: en0[802.11], ipv4, ipv6",
        ])
        let result = await classify(error, permissionDenied: false)
        XCTAssertEqual(result, .localNetworkPermissionDenied)
    }

    func testCannotConnectWithoutRefusedCodeMapsToComputerUnreachable() async {
        // -1004 with no POSIX code: the cause is not known, so the app
        // gives the network text, not the permission text.
        let result = await classify(URLError(URLError.Code(rawValue: -1004)))
        XCTAssertEqual(result, .computerUnreachable)
    }

    func testOtherPOSIXCodeMapsToComputerUnreachable() async {
        // 65 is EHOSTUNREACH ("no route to host").
        let error = URLError(.cannotConnectToHost, userInfo: ["_kCFStreamErrorCodeKey": 65])
        let result = await classify(error)
        XCTAssertEqual(result, .computerUnreachable)
    }

    func testTimeoutToLocalHostMapsToComputerUnreachable() async {
        let result = await classify(URLError(.timedOut), url: URL(string: "http://mac.local:8080/tok")!)
        XCTAssertEqual(result, .computerUnreachable)
    }

    func testLostConnectionToLocalHostMapsToComputerUnreachable() async {
        let result = await classify(URLError(.networkConnectionLost))
        XCTAssertEqual(result, .computerUnreachable)
    }

    func testRefusedConnectionToPublicHostMapsToServerUnreachable() async {
        // The probe does not run for a public host, so a "denied" answer has
        // no effect.
        let result = await classify(
            Self.refusedWithStreamCode(),
            url: URL(string: "https://example.com/tok")!,
            permissionDenied: true
        )
        XCTAssertEqual(result, .serverUnreachable)
    }

    func testProbeIsNotCalledForPublicHost() async {
        let called = ProbeCallFlag()
        let downloader = SnapshotURLDownloader(
            transport: { _ in throw URLError(.timedOut) },
            permissionProbe: { _ in called.set(); return true }
        )
        _ = try? await downloader.download(from: URL(string: "https://example.com/tok")!)
        XCTAssertFalse(called.value)
    }

    func testProbeIsNotCalledOnSuccess() async throws {
        let called = ProbeCallFlag()
        let downloader = SnapshotURLDownloader(
            transport: { request in
                (Data("bytes".utf8), HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!)
            },
            permissionProbe: { _ in called.set(); return true }
        )
        _ = try await downloader.download(from: Self.lanURL)
        XCTAssertFalse(called.value)
    }

    func testEachFailureCaseHasItsOwnText() {
        let stopped = QRSyncError.shareStopped.errorDescription ?? ""
        XCTAssertTrue(stopped.contains("expired or was already used"), stopped)
        XCTAssertTrue(stopped.contains("new QR code"), stopped)
        XCTAssertFalse(stopped.contains("Settings"), stopped)

        let unreachable = QRSyncError.computerUnreachable.errorDescription ?? ""
        for word in ["same Wi-Fi network", "VPN", "guest network", "firewall"] {
            XCTAssertTrue(unreachable.contains(word), "missing '\(word)' in: \(unreachable)")
        }
        XCTAssertFalse(unreachable.contains("Settings"), unreachable)

        let permission = QRSyncError.localNetworkPermissionDenied.errorDescription ?? ""
        XCTAssertTrue(permission.contains("Local Network"), permission)
        XCTAssertTrue(permission.contains("Settings"), permission)
    }

    func testUnrelatedURLErrorPropagatesUnmapped() async {
        let downloader = SnapshotURLDownloader { _ in
            throw URLError(.cancelled)
        }
        do {
            _ = try await downloader.download(from: Self.testURL)
            XCTFail("expected an error")
        } catch let error as URLError {
            XCTAssertEqual(error.code, .cancelled)
        } catch {
            XCTFail("expected URLError.cancelled, got \(error)")
        }
    }

    func testEmptyBodyIsRejected() async {
        do {
            _ = try await downloader(status: 200, body: Data()).download(from: Self.testURL)
            XCTFail("expected emptyDownload")
        } catch {
            XCTAssertEqual(error as? QRSyncError, .emptyDownload)
        }
    }

    // MARK: - Download → decode → import orchestration

    func testDownloadSnapshotDecodesFixtureAndImports() async throws {
        // Shared `fixtureURL(_:_:)` (FixtureSupport.swift) resolves the
        // resource under the copied "Fixtures" subdirectory of the bundle.
        let url = try fixtureURL("fixture-snapshot", "json.gz")
        let blob = try Data(contentsOf: url)

        let document = try await downloader(status: 200, body: blob)
            .downloadSnapshot(from: Self.testURL)
        XCTAssertEqual(document.header.schemaVersion, SnapshotCodec.schemaVersion)

        // The downloaded document runs through the exact same importer the
        // file-picked path uses — a fresh database ends up with every
        // fixture transaction inserted.
        let appDatabase = try AppDatabase.inMemory()
        let nonexistentDBURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("QRSnapshotSyncTests-\(UUID().uuidString).sqlite")
        let record = try SnapshotImporter.importSnapshot(
            appDatabase: appDatabase,
            document: document,
            databaseURL: nonexistentDBURL
        )
        XCTAssertEqual(record.schemaVersion, SnapshotCodec.schemaVersion)
        let transactionCount = try await appDatabase.dbWriter.read { db in
            try TransactionRecord.fetchCount(db)
        }
        XCTAssertEqual(transactionCount, document.transactions.count)
    }

    func testDownloadSnapshotRejectsMalformedBody() async {
        let downloader = downloader(status: 200, body: Data("this is not gzip".utf8))
        do {
            _ = try await downloader.downloadSnapshot(from: Self.testURL)
            XCTFail("expected SnapshotError.corruptGzip")
        } catch {
            XCTAssertEqual(error as? SnapshotError, .corruptGzip)
        }
    }
}

/// Records whether a test probe ran. The probe is `@Sendable`, so the flag
/// uses a lock.
private final class ProbeCallFlag: @unchecked Sendable {
    private let lock = NSLock()
    private var called = false

    var value: Bool {
        lock.lock(); defer { lock.unlock() }
        return called
    }

    func set() {
        lock.lock(); defer { lock.unlock() }
        called = true
    }
}
