import XCTest
import GRDB
@testable import DVMFinanceKit

/// Delta-snapshot tests — the XCTest port of desktop
/// `tests/test_snapshots_delta.py`. A delta snapshot carries only the
/// transactions changed since a `since` boundary (`updated_at >= since`, NULLs
/// excluded), plus a self-describing header (`delta: true`, `since: <iso>`).
/// The import path is the same incoming-wins merge as a full snapshot; these
/// tests verify the delta filter, the `export_state` marker, header provenance
/// on the import report, and that a delta with fewer transactions merges
/// without touching absent local rows.
final class SnapshotDeltaTests: XCTestCase {
    private var tempDirectories: [URL] = []

    override func tearDownWithError() throws {
        for url in tempDirectories {
            try? FileManager.default.removeItem(at: url)
        }
        tempDirectories = []
    }

    // MARK: - Helpers

    private func makeTempDirectory() throws -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("SnapshotDeltaTests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        tempDirectories.append(url)
        return url
    }

    /// A `Date` at second precision in the codec's UTC/POSIX frame, so the
    /// stored `updated_at` string and the `since` boundary compare exactly.
    private func dateTime(_ string: String) throws -> Date {
        try XCTUnwrap(SnapshotCodec.parseDateTime(string))
    }

    /// Builds a `TransactionRecord` mirroring `_txn` in the Python test:
    /// `updatedAt` is the stored ISO-8601 string (or `nil` for never-touched).
    private func txn(_ id: String, updatedAt: Date?, category: String? = nil) -> TransactionRecord {
        TransactionRecord(
            id: id,
            accountNumber: "NL01TEST0123456789",
            transactiondate: DatabaseDateFormat.dateOnly.date(from: "2026-01-15")!,
            amount: Decimal(string: "-10.00")!,
            description: "payment \(id)",
            category: category,
            currency: "EUR",
            updatedAt: updatedAt.map(SnapshotCodec.renderDateTime)
        )
    }

    private func insert(_ appDatabase: AppDatabase, _ records: [TransactionRecord]) throws {
        try appDatabase.dbWriter.write { db in
            for var record in records {
                try record.insert(db)
            }
        }
    }

    private func build(_ appDatabase: AppDatabase, machineId: String = "m", since: Date? = nil) throws -> SnapshotDocument {
        try appDatabase.dbWriter.read { db in
            try SnapshotCodec.build(db: db, machineId: machineId, since: since)
        }
    }

    // MARK: - build_snapshot delta filter

    func testBuildSnapshotDeltaFiltersByUpdatedAt() throws {
        let appDatabase = try AppDatabase.inMemory()
        let since = try dateTime("2026-06-01T12:00:00")
        // Before, on the boundary, after, and never-touched (NULL).
        try insert(appDatabase, [
            txn("before", updatedAt: since.addingTimeInterval(-3600)),
            txn("boundary", updatedAt: since),
            txn("after", updatedAt: since.addingTimeInterval(3600)),
            txn("never", updatedAt: nil),
        ])

        let payload = try build(appDatabase, since: since)

        let ids = Set(payload.transactions.map(\.id))
        XCTAssertEqual(ids, ["boundary", "after"], "edits at/after `since` included; before & NULL excluded")
        XCTAssertEqual(payload.header.delta, true)
        XCTAssertEqual(payload.header.since, SnapshotCodec.renderDateTime(since))
    }

    func testBuildSnapshotFullHasNoDeltaHeader() throws {
        let appDatabase = try AppDatabase.inMemory()
        try insert(appDatabase, [txn("t1", updatedAt: try dateTime("2026-06-01T00:00:00"))])

        let payload = try build(appDatabase)

        XCTAssertNil(payload.header.delta)
        XCTAssertNil(payload.header.since)
        XCTAssertEqual(Set(payload.transactions.map(\.id)), ["t1"])
    }

    // MARK: - export_state marker

    func testExportDeltaAdvancesExportStateMarker() throws {
        let appDatabase = try AppDatabase.inMemory()
        let dataDir = try makeTempDirectory()
        try insert(appDatabase, [txn("t1", updatedAt: try dateTime("2026-06-01T00:00:00"))])

        let markerBefore = try appDatabase.dbWriter.read { db in
            try ExportStateRecord.getLastDeltaExportAt(db)
        }
        XCTAssertNil(markerBefore)

        let before = Date()
        let url = try SnapshotExporter.exportDeltaSnapshot(
            appDatabase: appDatabase,
            dataDirectory: dataDir,
            since: try dateTime("2026-01-01T00:00:00")
        )
        XCTAssertTrue(url.lastPathComponent.hasPrefix("delta-"), "delta files use the delta- prefix")

        let marker = try appDatabase.dbWriter.read { db in
            try ExportStateRecord.getLastDeltaExportAt(db)
        }
        let unwrapped = try XCTUnwrap(marker)
        // Second-precision storage can round down below `before`; allow a 1s slack.
        XCTAssertGreaterThanOrEqual(unwrapped.timeIntervalSince1970, before.timeIntervalSince1970 - 1)

        let stateRowCount = try appDatabase.dbWriter.read { db in
            try ExportStateRecord.fetchCount(db)
        }
        XCTAssertEqual(stateRowCount, 1, "exactly one export_state row is ever created")
    }

    // MARK: - Roundtrip: only recent edits reach the target

    func testDeltaRoundtripOnlyRecentEditsReachTarget() throws {
        let source = try AppDatabase.inMemory()
        let since = try dateTime("2026-06-01T12:00:00")
        try insert(source, [
            txn("old", updatedAt: since.addingTimeInterval(-86_400), category: "groceries"),
            txn("recent", updatedAt: since.addingTimeInterval(86_400), category: "dining"),
        ])

        let payload = try build(source, machineId: "src", since: since)
        XCTAssertEqual(Set(payload.transactions.map(\.id)), ["recent"])

        // Target already has `old` (a different category) plus a local-only row.
        let target = try AppDatabase.inMemory()
        try insert(target, [
            txn("old", updatedAt: since.addingTimeInterval(-86_400), category: "OLD-LOCAL"),
            txn("t_local", updatedAt: since, category: "keep-me"),
        ])

        let dbURL = try makeTempDirectory().appendingPathComponent("nonexistent.sqlite")
        _ = try SnapshotImporter.importSnapshot(appDatabase: target, document: payload, databaseURL: dbURL)

        let (recent, old, local) = try target.dbWriter.read { db in
            (
                try TransactionRecord.fetchOne(db, key: "recent"),
                try TransactionRecord.fetchOne(db, key: "old"),
                try TransactionRecord.fetchOne(db, key: "t_local")
            )
        }
        XCTAssertEqual(recent?.category, "dining", "recent inserted from delta")
        XCTAssertEqual(old?.category, "OLD-LOCAL", "old untouched — not in delta")
        XCTAssertEqual(local?.category, "keep-me", "local-only row preserved")
    }

    // MARK: - Import provenance

    func testImportRecordsDeltaProvenance() throws {
        let source = try AppDatabase.inMemory()
        let since = try dateTime("2026-06-01T12:00:00")
        try insert(source, [txn("recent", updatedAt: since.addingTimeInterval(86_400))])
        let payload = try build(source, machineId: "src", since: since)

        let target = try AppDatabase.inMemory()
        let dbURL = try makeTempDirectory().appendingPathComponent("nonexistent.sqlite")
        let record = try SnapshotImporter.importSnapshot(appDatabase: target, document: payload, databaseURL: dbURL)

        XCTAssertEqual(record.isDelta, true)
        XCTAssertEqual(record.deltaSince, since)
    }

    func testImportFullSnapshotIsNotDelta() throws {
        let source = try AppDatabase.inMemory()
        try insert(source, [txn("t1", updatedAt: try dateTime("2026-06-01T00:00:00"))])
        let payload = try build(source, machineId: "src")

        let target = try AppDatabase.inMemory()
        let dbURL = try makeTempDirectory().appendingPathComponent("nonexistent.sqlite")
        let record = try SnapshotImporter.importSnapshot(appDatabase: target, document: payload, databaseURL: dbURL)

        XCTAssertEqual(record.isDelta, false)
        XCTAssertNil(record.deltaSince)
    }

    // MARK: - Exported delta file reads back as a valid snapshot

    func testDeltaFileReadsBackAsValidSnapshot() throws {
        let appDatabase = try AppDatabase.inMemory()
        let dataDir = try makeTempDirectory()
        try insert(appDatabase, [txn("t1", updatedAt: try dateTime("2026-06-02T00:00:00"))])

        let url = try SnapshotExporter.exportDeltaSnapshot(
            appDatabase: appDatabase,
            dataDirectory: dataDir,
            since: try dateTime("2026-01-01T00:00:00")
        )
        let payload = try SnapshotCodec.read(Data(contentsOf: url))
        XCTAssertEqual(payload.header.delta, true)
        XCTAssertEqual(Set(payload.transactions.map(\.id)), ["t1"])
    }
}
