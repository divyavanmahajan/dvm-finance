import Foundation
import Network

/// "Sync from computer" — the phone-side half of the desktop's QR snapshot
/// hand-off (see `ios/docs/spec.md` "QR sync from the computer").
///
/// The desktop web app shows a QR code containing a plain URL like
/// `http://192.168.1.23:54321/<token>` — an ephemeral one-shot HTTP server on
/// the user's machine serving a single gzipped-JSON snapshot (the same
/// `.json.gz` format `SnapshotCodec` already reads). The server allows
/// exactly one download and expires after ~10 minutes, so every failure mode
/// here maps to a "generate a fresh QR code" style message.
///
/// This file holds everything camera-free and therefore unit-testable:
/// QR payload validation (`QRSyncPayload`) and the download step with an
/// injectable transport (`SnapshotURLDownloader`). The camera view and the
/// import call itself live in the app target (`Views/SyncFromComputerView.swift`),
/// which feeds the downloaded bytes through the existing
/// `SnapshotCodec.read` → `SnapshotImporter.importSnapshot` pipeline.
public enum QRSyncError: Error, LocalizedError, Equatable {
    /// The scanned QR code does not contain a web URL at all.
    case notAWebURL
    /// The QR code holds a URL, but with a scheme other than http/https
    /// (e.g. `mailto:` or an arbitrary deep link) — refused outright.
    case unsupportedScheme(String)
    /// A failure to reach a public host (connection refused, host
    /// unreachable, timeout). The one-shot server probably stopped.
    case serverUnreachable
    /// iOS reports that the Local Network permission of the app is off. The
    /// download classifies a failure as this case only when the
    /// `PermissionProbe` or the path text of the error says so. The address
    /// class alone never gives this case. The message points the user to
    /// Settings.
    case localNetworkPermissionDenied
    /// The computer on the local network refused the connection
    /// (`ECONNREFUSED`). The one-shot server stopped after a download or
    /// after 10 minutes, so the user must make a new QR code.
    case shareStopped
    /// Another failure to reach a host on the local network: a timeout, an
    /// unreachable host, or a lost connection. The usual cause is a
    /// different Wi-Fi network, a VPN, a guest network, or a firewall.
    case computerUnreachable
    /// HTTP 404/410 from the server: the token was already used or expired.
    case linkAlreadyUsed
    /// Any other non-success HTTP status.
    case serverError(statusCode: Int)
    /// A 200 response with an empty body — not a snapshot.
    case emptyDownload

    public var errorDescription: String? {
        switch self {
        case .notAWebURL:
            return "That QR code doesn't contain a web link. Scan the QR code shown by DVM Finance on your computer."
        case .unsupportedScheme(let scheme):
            return "That QR code links to '\(scheme)', which this app can't open. Scan the QR code shown by DVM Finance on your computer."
        case .serverUnreachable:
            return "Couldn't reach your computer. The link may have expired — generate a fresh QR code on your computer and make sure both devices are on the same Wi-Fi network."
        case .localNetworkPermissionDenied:
            return "DVM Finance needs Local Network access to reach your computer. Enable it in Settings \u{203A} DVM Finance \u{203A} Local Network, then tap Scan Again."
        case .shareStopped:
            return "The QR code expired or was already used. Your computer does not share the snapshot now. On your computer, click the QR icon to make a new QR code. Then tap Scan Again."
        case .computerUnreachable:
            return "Couldn't reach your computer. Make sure that this device and your computer use the same Wi-Fi network. A VPN on this device, a guest network, or the firewall of your computer can also stop the connection. Then make a new QR code and tap Scan Again."
        case .linkAlreadyUsed:
            return "This QR code was already used or has expired. Generate a fresh QR code on your computer and scan it again."
        case .serverError(let statusCode):
            return "Your computer responded with an error (HTTP \(statusCode)). Generate a fresh QR code and try again."
        case .emptyDownload:
            return "The download from your computer was empty. Generate a fresh QR code and try again."
        }
    }
}

/// Validation of the raw string a QR code decodes to.
public enum QRSyncPayload {
    /// Accepts only an absolute `http://` or `https://` URL with a host;
    /// anything else throws a `QRSyncError` with a user-friendly message.
    ///
    /// Leading/trailing whitespace is tolerated (some QR generators pad the
    /// payload); everything else must parse strictly.
    public static func url(from rawPayload: String) throws -> URL {
        let trimmed = rawPayload.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty,
              let components = URLComponents(string: trimmed),
              let url = components.url
        else {
            throw QRSyncError.notAWebURL
        }
        guard let scheme = components.scheme?.lowercased() else {
            throw QRSyncError.notAWebURL
        }
        guard scheme == "http" || scheme == "https" else {
            throw QRSyncError.unsupportedScheme(scheme)
        }
        guard let host = components.host, !host.isEmpty else {
            throw QRSyncError.notAWebURL
        }
        return url
    }

    /// Whether `url`'s host is a private / link-local / loopback address (or
    /// an `.local` mDNS name) — i.e. a machine on the local network rather
    /// than the public internet. When a download fails, the downloader uses
    /// it to select the local-network messages (`.shareStopped`,
    /// `.computerUnreachable`, or the permission message) or the public-host
    /// message (`.serverUnreachable`). It does not decide the permission case
    /// alone.
    ///
    /// Covers RFC 1918 IPv4 ranges (10/8, 172.16/12, 192.168/16), link-local
    /// 169.254/16, IPv4 loopback 127/8, IPv6 loopback `::1`, IPv6 link-local
    /// `fe80::/10`, IPv6 unique-local `fc00::/7`, and hostnames ending in
    /// `.local` or equal to `localhost`. Anything else (a public IP or a
    /// normal DNS name) reads as non-local.
    public static func isLocalNetworkHost(_ url: URL) -> Bool {
        guard let host = url.host?.lowercased(), !host.isEmpty else { return false }
        return isLocalNetworkHost(host)
    }

    /// Host-string overload (also the testable core).
    static func isLocalNetworkHost(_ rawHost: String) -> Bool {
        var host = rawHost.lowercased()
        // A bracketed IPv6 literal ("[fe80::1]") can arrive with brackets.
        host = host.trimmingCharacters(in: CharacterSet(charactersIn: "[]"))

        if host == "localhost" || host.hasSuffix(".local") {
            return true
        }

        // IPv4 dotted quad?
        let octetStrings = host.split(separator: ".", omittingEmptySubsequences: false)
        if octetStrings.count == 4 {
            let octets = octetStrings.compactMap { Int($0) }.filter { (0...255).contains($0) }
            if octets.count == 4 {
                switch (octets[0], octets[1]) {
                case (10, _): return true                     // 10.0.0.0/8
                case (127, _): return true                    // loopback 127.0.0.0/8
                case (169, 254): return true                  // link-local 169.254.0.0/16
                case (192, 168): return true                  // 192.168.0.0/16
                case (172, let b) where (16...31).contains(b): return true // 172.16.0.0/12
                default: return false
                }
            }
        }

        // IPv6 literal?
        if host.contains(":") {
            if host == "::1" { return true }              // loopback
            if host.hasPrefix("fe8") || host.hasPrefix("fe9")
                || host.hasPrefix("fea") || host.hasPrefix("feb") {
                return true                               // fe80::/10 link-local
            }
            if host.hasPrefix("fc") || host.hasPrefix("fd") {
                return true                               // fc00::/7 unique-local
            }
            return false
        }

        return false
    }
}

/// Downloads the snapshot bytes behind a validated QR URL and maps transport
/// failures to the `QRSyncError` cases above. The transport and the
/// permission probe are injectable, so the mapping is unit-testable without a
/// network (mirrors how the parsers take raw bytes rather than doing their
/// own I/O).
public struct SnapshotURLDownloader {
    /// `(data, response)` for a request — `URLSession.data(for:)`-shaped.
    public typealias Transport = @Sendable (URLRequest) async throws -> (Data, URLResponse)

    /// Returns `true` when iOS refuses the path to the host of the URL
    /// because the Local Network permission is off. The downloader calls it
    /// only after a failed connection to a host on the local network, never
    /// on the success path.
    public typealias PermissionProbe = @Sendable (URL) async -> Bool

    private let transport: Transport
    private let permissionProbe: PermissionProbe

    /// The default probe always returns `false` ("the permission is on").
    /// The tests use this default, or inject a fixed answer.
    public init(
        transport: @escaping Transport,
        permissionProbe: @escaping PermissionProbe = { _ in false }
    ) {
        self.transport = transport
        self.permissionProbe = permissionProbe
    }

    /// The production transport: an ephemeral `URLSession` (no cache, no
    /// cookies, nothing persisted — the URL is a one-shot secret token) with
    /// a short timeout, appropriate for a LAN transfer. The probe is
    /// `localNetworkDenied(for:)`.
    public static func live() -> SnapshotURLDownloader {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 15
        configuration.timeoutIntervalForResource = 120
        configuration.waitsForConnectivity = false
        let session = URLSession(configuration: configuration)
        return SnapshotURLDownloader(
            transport: { request in try await session.data(for: request) },
            permissionProbe: { url in await localNetworkDenied(for: url) }
        )
    }

    /// Fetches the snapshot bytes. Throws `QRSyncError` for every anticipated
    /// failure (server gone, token used/expired, HTTP error, empty body);
    /// unexpected errors propagate as-is.
    public func download(from url: URL) async throws -> Data {
        var request = URLRequest(url: url)
        request.httpMethod = "GET"

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await transport(request)
        } catch let error as URLError {
            switch error.code {
            case .cannotConnectToHost, .cannotFindHost, .networkConnectionLost,
                 .timedOut, .notConnectedToInternet, .dnsLookupFailed:
                throw await classifyConnectionFailure(error, url: url)
            default:
                throw error
            }
        }

        if let http = response as? HTTPURLResponse {
            switch http.statusCode {
            case 200...299:
                break
            case 404, 410:
                throw QRSyncError.linkAlreadyUsed
            default:
                throw QRSyncError.serverError(statusCode: http.statusCode)
            }
        }

        guard !data.isEmpty else {
            throw QRSyncError.emptyDownload
        }
        return data
    }

    /// Convenience orchestration: download, then decode through the existing
    /// snapshot codec — so a malformed payload surfaces as the codec's own
    /// user-readable `SnapshotError` ("Not a valid snapshot file (…)").
    /// The caller then runs `SnapshotImporter.importSnapshot` exactly like a
    /// file-picked snapshot import.
    public func downloadSnapshot(from url: URL) async throws -> SnapshotDocument {
        let data = try await download(from: url)
        return try SnapshotCodec.read(data)
    }

    // MARK: - Failure classification (design D1)

    /// The POSIX code for "connection refused".
    static let connectionRefusedCode = 61

    /// Classifies a connection failure in three steps:
    ///
    /// 1. A public host gives `.serverUnreachable`.
    /// 2. The probe, or the "Local network prohibited" path text in the
    ///    error, gives `.localNetworkPermissionDenied`.
    /// 3. `ECONNREFUSED` gives `.shareStopped`. Each other failure gives
    ///    `.computerUnreachable`.
    ///
    /// The permission check comes first. With the permission off, iOS can
    /// also report the failure as "connection refused".
    func classifyConnectionFailure(_ error: URLError, url: URL) async -> QRSyncError {
        guard QRSyncPayload.isLocalNetworkHost(url) else {
            return .serverUnreachable
        }
        if Self.reportsLocalNetworkProhibited(error) {
            return .localNetworkPermissionDenied
        }
        if await permissionProbe(url) {
            return .localNetworkPermissionDenied
        }
        if error.code == .cannotConnectToHost, Self.isConnectionRefused(error) {
            return .shareStopped
        }
        return .computerUnreachable
    }

    /// `true` when the description of the network path in the user info
    /// holds "Local network prohibited". This key is private, and its text
    /// can change in a new iOS version, so it is only the fallback of the
    /// probe.
    static func reportsLocalNetworkProhibited(_ error: Error) -> Bool {
        var current: NSError? = error as NSError
        while let nsError = current {
            if let path = nsError.userInfo["_NSURLErrorNWPathKey"],
               String(describing: path).localizedCaseInsensitiveContains("Local network prohibited") {
                return true
            }
            current = nsError.userInfo[NSUnderlyingErrorKey] as? NSError
        }
        return false
    }

    /// `true` when the error, or an error in its `NSUnderlyingError` chain,
    /// holds the POSIX code `ECONNREFUSED`. The code can be in
    /// `_kCFStreamErrorCodeKey`, or it can be the code of an underlying
    /// error in `NSPOSIXErrorDomain`.
    static func isConnectionRefused(_ error: Error) -> Bool {
        var current: NSError? = error as NSError
        while let nsError = current {
            if nsError.domain == NSPOSIXErrorDomain, nsError.code == connectionRefusedCode {
                return true
            }
            if let streamCode = nsError.userInfo["_kCFStreamErrorCodeKey"] as? Int,
               streamCode == connectionRefusedCode {
                return true
            }
            current = nsError.userInfo[NSUnderlyingErrorKey] as? NSError
        }
        return false
    }

    // MARK: - Live permission probe

    /// Opens an `NWConnection` to the host and the port of `url`, and returns
    /// `true` when the path is unsatisfied because of `.localNetworkDenied`.
    /// The probe stops after `timeout` seconds and then returns `false`. The
    /// unit tests cannot run it, because the simulator does not apply the
    /// permission.
    static func localNetworkDenied(for url: URL, timeout: TimeInterval = 2) async -> Bool {
        guard let host = url.host, !host.isEmpty else { return false }
        let defaultPort = url.scheme?.lowercased() == "https" ? 443 : 80
        guard let port = NWEndpoint.Port(rawValue: UInt16(clamping: url.port ?? defaultPort)) else {
            return false
        }
        let connection = NWConnection(host: NWEndpoint.Host(host), port: port, using: .tcp)
        let queue = DispatchQueue(label: "DVMFinanceKit.LocalNetworkProbe")
        let once = ProbeResult()

        return await withCheckedContinuation { continuation in
            @Sendable func finish(_ denied: Bool) {
                guard once.claim() else { return }
                connection.stateUpdateHandler = nil
                connection.cancel()
                continuation.resume(returning: denied)
            }
            connection.stateUpdateHandler = { state in
                switch state {
                case .waiting, .failed:
                    let denied = connection.currentPath?.unsatisfiedReason == .localNetworkDenied
                    finish(denied)
                case .ready, .cancelled:
                    finish(false)
                default:
                    break
                }
            }
            connection.start(queue: queue)
            queue.asyncAfter(deadline: .now() + timeout) {
                finish(false)
            }
        }
    }
}

/// A flag that lets exactly one caller resume the continuation of the probe.
/// The state handler of `NWConnection` can fire more than once, and the
/// timeout fires too.
private final class ProbeResult: @unchecked Sendable {
    private let lock = NSLock()
    private var claimed = false

    func claim() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        if claimed { return false }
        claimed = true
        return true
    }
}
