import Foundation
import GRDB

/// Shared `Date` <-> `String` formatting for every GRDB record in
/// `Database/`.
///
/// `src/abn_combined/core/models.py` has two kinds of date columns:
/// - SQLAlchemy `Date` columns (`transactions.transactiondate`/`valuedate`,
///   `categorization_rules.filter_date_from`/`filter_date_to`,
///   `budgets.start_date`/`end_date`/`created_at`/`updated_at`) — day
///   granularity, rendered as `yyyy-MM-dd` (matches the snapshot format's
///   ISO date strings, `ios/docs/spec.md` "Snapshot codec").
/// - SQLAlchemy `DateTime` columns (`rule_change_reports.created_at`,
///   `snapshot_imports.created_at`) — second granularity, rendered as
///   `yyyy-MM-dd'T'HH:mm:ss` (matches the `exported_at` example in
///   `docs/architecture.md` "Snapshot format").
///
/// Both formatters pin a POSIX locale and UTC time zone so the on-disk
/// representation never depends on device locale/time zone, and both are
/// wired into GRDB's per-record `databaseDateEncodingStrategy` /
/// `databaseDateDecodingStrategy` overrides rather than relying on GRDB's
/// `deferredToDate` default (which would store a bare Double, not a
/// human-readable/portable string).
enum DatabaseDateFormat {
    static let dateOnly: DateFormatter = makeFormatter(dateFormat: "yyyy-MM-dd")

    static let dateTime: DateFormatter = makeFormatter(dateFormat: "yyyy-MM-dd'T'HH:mm:ss")

    private static func makeFormatter(dateFormat: String) -> DateFormatter {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = dateFormat
        return formatter
    }
}
