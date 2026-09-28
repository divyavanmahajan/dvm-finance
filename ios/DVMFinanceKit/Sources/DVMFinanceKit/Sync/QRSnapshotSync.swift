import Foundation

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
    /// TCP-level failure (connection refused, host unreachable, timeout):
    /// the one-shot server has almost certainly exited or expired.
    case serverUnreachable
    /// A connection failure to a private/link-local address (see
    /// `QRSyncPayload.isLocalNetworkHost`). iOS gives no public API to read
    /// the Local Network privacy permission, so a failure to reach a LAN
    /// host is treated as "the permission is off" — by far the most common
    /// cause, and Safari (which is not sandboxed by that permission) reaching
    /// the same URL is exactly the reported symptom. The message points the
    /// user at Settings rather than blaming the (still-running) server.
    case localNetworkPermissionDenied
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
    /// than the public internet. Used to decide, when a download connection
    /// fails, whether to blame the missing Local Network privacy permission
    /// (LAN host) or a genuinely gone/expired server (public host).
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
/// failures to the `QRSyncError` cases above. The transport is injectable so
/// the mapping is unit-testable without a network (mirrors how the parsers
/// take raw bytes rather than doing their own I/O).
public struct SnapshotURLDownloader {
    /// `(data, response)` for a request — `URLSession.data(for:)`-shaped.
    public typealias Transport = @Sendable (URLRequest) async throws -> (Data, URLResponse)

    private let transport: Transport

    public init(transport: @escaping Transport) {
        self.transport = transport
    }

    /// The production transport: an ephemeral `URLSession` (no cache, no
    /// cookies, nothing persisted — the URL is a one-shot secret token) with
    /// a short timeout, appropriate for a LAN transfer.
    public static func live() -> SnapshotURLDownloader {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 15
        configuration.timeoutIntervalForResource = 120
        configuration.waitsForConnectivity = false
        let session = URLSession(configuration: configuration)
        return SnapshotURLDownloader { request in
            try await session.data(for: request)
        }
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
                // A connection failure to a LAN host is, in practice, the
                // Local Network privacy permission being off (Safari, exempt
                // from it, reaches the same URL). A public host failing the
                // same way is a genuinely gone/expired server. iOS exposes no
                // API to read the permission, so the host class is the tell.
                if QRSyncPayload.isLocalNetworkHost(url) {
                    throw QRSyncError.localNetworkPermissionDenied
                }
                throw QRSyncError.serverUnreachable
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
}
