import SwiftUI
import UIKit
import AVFoundation
import DVMFinanceKit

/// "Sync from computer" (`ios/docs/spec.md` "QR sync from the computer"):
/// scan the QR code the desktop web app shows, download the one-shot
/// snapshot URL it encodes, and run the exact same snapshot import
/// (incoming-wins merge, pre-import DB backup, audit report) as the
/// file-picked "Import snapshot" path in `ImportView`.
///
/// Like every other screen, the view holds no business logic: payload
/// validation and the download live in `DVMFinanceKit`
/// (`Sync/QRSnapshotSync.swift`), the merge in `SnapshotImporter`. This view
/// is just the phase machine (permission → scan → download → import →
/// summary/error) plus the camera wrapper.
struct SyncFromComputerView: View {
    @Environment(\.appDatabase) private var appDatabase
    @Environment(\.appDatabaseURL) private var appDatabaseURL
    @Environment(\.dismiss) private var dismiss

    private enum Phase {
        case checkingPermission
        case cameraDenied
        case scannerUnavailable
        case scanning
        case downloading
        case importing
        case done(SnapshotImportRecord)
        /// `offerSettings` adds an "Open Settings" deep link — set only for
        /// the Local Network permission case, which the user fixes in the
        /// app's own Settings pane.
        case failed(message: String, offerSettings: Bool)
    }

    @State private var phase: Phase = .checkingPermission

    var body: some View {
        NavigationStack {
            content
                .navigationTitle("Sync from Computer")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button(doneButtonTitle) { dismiss() }
                    }
                }
        }
        .task { await requestCameraAndStart() }
        .interactiveDismissDisabled(isWorking)
    }

    @ViewBuilder
    private var content: some View {
        switch phase {
        case .checkingPermission:
            ProgressView("Preparing camera…")

        case .cameraDenied:
            unavailableMessage(
                systemImage: "camera.fill",
                title: "Camera Access Needed",
                message: "Allow camera access in Settings to scan the QR code shown by DVM Finance on your computer."
            )

        case .scannerUnavailable:
            unavailableMessage(
                systemImage: "qrcode.viewfinder",
                title: "Scanning Unavailable",
                message: "This device can't scan QR codes. On your computer, export a snapshot and open it here with \u{201C}Import snapshot\u{201D} instead."
            )

        case .scanning:
            VStack(spacing: 0) {
                QRScannerView { payload in
                    handleScannedPayload(payload)
                }
                Text("On your computer, open DVM Finance and choose \u{201C}Sync to phone\u{201D}, then point the camera at the QR code.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding()
            }

        case .downloading:
            progressMessage("Downloading from your computer…")

        case .importing:
            progressMessage("Importing snapshot…")

        case .done(let record):
            SnapshotImportSummaryContent(record: record)
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Done") { dismiss() }
                    }
                }

        case .failed(let message, let offerSettings):
            VStack(spacing: 16) {
                Image(systemName: "exclamationmark.triangle")
                    .font(.largeTitle)
                    .foregroundStyle(.orange)
                Text(message)
                    .multilineTextAlignment(.center)
                if offerSettings {
                    Button("Open Settings") { openAppSettings() }
                        .buttonStyle(.borderedProminent)
                    Button("Scan Again") { phase = .scanning }
                } else {
                    Button("Scan Again") { phase = .scanning }
                        .buttonStyle(.borderedProminent)
                }
            }
            .padding()
        }
    }

    private var isWorking: Bool {
        switch phase {
        case .downloading, .importing: return true
        default: return false
        }
    }

    private var doneButtonTitle: String {
        if case .done = phase { return "Close" }
        return "Cancel"
    }

    private func progressMessage(_ text: String) -> some View {
        VStack(spacing: 12) {
            ProgressView()
            Text(text).foregroundStyle(.secondary)
        }
    }

    private func unavailableMessage(systemImage: String, title: String, message: String) -> some View {
        ContentUnavailableView {
            Label(title, systemImage: systemImage)
        } description: {
            Text(message)
        }
    }

    // MARK: - Flow

    private func requestCameraAndStart() async {
        guard QRScannerView.isSupported else {
            phase = .scannerUnavailable
            return
        }
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            phase = .scanning
        case .notDetermined:
            let granted = await AVCaptureDevice.requestAccess(for: .video)
            phase = granted ? .scanning : .cameraDenied
        default:
            phase = .cameraDenied
        }
    }

    private func handleScannedPayload(_ payload: String) {
        do {
            let url = try QRSyncPayload.url(from: payload)
            Task { await downloadAndImport(from: url) }
        } catch {
            phase = fail(with: error)
        }
    }

    private func downloadAndImport(from url: URL) async {
        guard let appDatabase, let appDatabaseURL else { return }
        phase = .downloading
        do {
            let document = try await SnapshotURLDownloader.live().downloadSnapshot(from: url)
            phase = .importing
            let record = try SnapshotImporter.importSnapshot(
                appDatabase: appDatabase,
                document: document,
                databaseURL: appDatabaseURL
            )
            phase = .done(record)
        } catch {
            phase = fail(with: error)
        }
    }

    /// Maps any thrown error to a `.failed` phase, turning on the settings
    /// deep link only for the Local Network permission case.
    private func fail(with error: Error) -> Phase {
        let offerSettings = (error as? QRSyncError) == .localNetworkPermissionDenied
        return .failed(message: error.localizedDescription, offerSettings: offerSettings)
    }

    private func openAppSettings() {
        if let url = URL(string: UIApplication.openSettingsURLString) {
            UIApplication.shared.open(url)
        }
    }
}

#Preview {
    SyncFromComputerView()
}
