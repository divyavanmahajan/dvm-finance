import SwiftUI
import VisionKit

/// Thin SwiftUI wrapper around VisionKit's `DataScannerViewController`,
/// restricted to QR codes. Camera-facing UI only — payload validation,
/// download and import all live elsewhere (`DVMFinanceKit`'s
/// `Sync/QRSnapshotSync.swift` and `SyncFromComputerView`), keeping this
/// wrapper as dumb as the other pickers in the app target.
///
/// `onScan` fires once with the first recognized QR payload; the parent is
/// expected to dismiss or replace the scanner, so scanning stops after the
/// first hit to avoid double-firing while the sheet animates away.
struct QRScannerView: UIViewControllerRepresentable {
    let onScan: (String) -> Void

    /// Whether the current device/context can scan at all (no camera on
    /// simulators; VisionKit unsupported on some hardware). Checked by the
    /// parent before presenting, so it can show a friendly message instead
    /// of a black rectangle.
    static var isSupported: Bool {
        DataScannerViewController.isSupported
    }

    func makeUIViewController(context: Context) -> DataScannerViewController {
        let scanner = DataScannerViewController(
            recognizedDataTypes: [.barcode(symbologies: [.qr])],
            qualityLevel: .balanced,
            recognizesMultipleItems: false,
            isHighlightingEnabled: true
        )
        scanner.delegate = context.coordinator
        return scanner
    }

    func updateUIViewController(_ scanner: DataScannerViewController, context: Context) {
        guard !context.coordinator.didScan else { return }
        // Idempotent; throws only when scanning is unavailable (no camera
        // permission / unsupported), which the parent view already gates on.
        try? scanner.startScanning()
    }

    static func dismantleUIViewController(_ scanner: DataScannerViewController, coordinator: Coordinator) {
        scanner.stopScanning()
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(onScan: onScan)
    }

    final class Coordinator: NSObject, DataScannerViewControllerDelegate {
        private let onScan: (String) -> Void
        private(set) var didScan = false

        init(onScan: @escaping (String) -> Void) {
            self.onScan = onScan
        }

        func dataScanner(
            _ dataScanner: DataScannerViewController,
            didAdd addedItems: [RecognizedItem],
            allItems: [RecognizedItem]
        ) {
            guard !didScan else { return }
            for item in addedItems {
                if case .barcode(let barcode) = item, let payload = barcode.payloadStringValue {
                    didScan = true
                    dataScanner.stopScanning()
                    onScan(payload)
                    return
                }
            }
        }
    }
}
