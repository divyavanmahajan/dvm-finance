import Foundation
import GRDB

/// Port of `core/merge.py`.
///
/// The bank writes one SEPA payment in two description forms. The two forms
/// hold a different raw text, so each form gives a different transaction id. A
/// database from before the end-to-end reference check can therefore hold one
/// payment twice. This module finds each such group and folds it to one row.
///
/// The merge keeps the row with the lowest id, writes `deleted_at` and
/// `merged_into` on each other row, and deletes no row. The purge keeps each
/// merged row.
///
/// The merge refuses a group whose rows hold two different manual categories.
/// Only the snapshot import may replace a manual categorization, so the merge
/// does not choose between the two values.
///
/// The merge stores a `MergeReportRecord`, like the Python port. The report
/// keeps each carried manual categorization, which the transaction table does
/// not record.
public enum Merge {

    /// One payment that the database holds more than one time. Port of
    /// `core/merge.py:MergeGroup`.
    public struct MergeGroup: Equatable {
        public var account: String
        public var reference: String
        public var amount: String
        /// How the system found the group: `reference` or `counterparty`.
        public var matchedBy: String
        public var survivorID: String
        public var mergedIDs: [String]
        public var carriedCategory: String?
        public var carriedTags: String?

        /// The shape of `core/merge.py:MergeGroup.as_dict`.
        var asDictionary: [String: Any] {
            [
                "account": account,
                "reference": reference,
                "amount": amount,
                "matched_by": matchedBy,
                "survivor_id": survivorID,
                "merged_ids": mergedIDs,
                "carried_category": carriedCategory ?? NSNull(),
                "carried_tags": carriedTags ?? NSNull(),
            ]
        }
    }

    /// One group that the merge refuses, with the reason. Port of
    /// `core/merge.py:RefusedGroup`.
    public struct RefusedGroup: Equatable {
        public var account: String
        public var reference: String
        public var amount: String
        /// How the system found the group: `reference` or `counterparty`.
        public var matchedBy: String
        public var reason: String
        public var rowIDs: [String]
        public var manualCategories: [String]

        /// The shape of `core/merge.py:RefusedGroup.as_dict`.
        var asDictionary: [String: Any] {
            [
                "account": account,
                "reference": reference,
                "amount": amount,
                "matched_by": matchedBy,
                "reason": reason,
                "row_ids": rowIDs,
                "manual_categories": manualCategories,
            ]
        }
    }

    /// What a merge would do. The preview changes no row. Port of
    /// `core/merge.py:MergePreview`.
    public struct MergePreview: Equatable {
        public var groups: [MergeGroup] = []
        public var refused: [RefusedGroup] = []

        /// The number of rows that the merge would flag.
        public var rowCount: Int { groups.reduce(0) { $0 + $1.mergedIDs.count } }
    }

    /// Port of `core/merge.py:_CONFLICTING_MANUAL_CATEGORY`.
    public static let conflictingManualCategory =
        "the rows hold two different manual categories"

    /// Port of `core/merge.py:_ONE_STATEMENT_FILE`.
    public static let oneStatementFile =
        "one statement file gives more than one row of the group, so the group "
        + "holds a repeated payment and not two forms of one payment"

    /// The usable reference of a stored row, or `nil` when it names no
    /// payment. Port of `core/merge.py:_usable_reference`.
    ///
    /// The function reads the column first, and otherwise the structured
    /// description. A row from before the backfill can hold the value in the
    /// structured description only.
    static func usableReference(_ row: TransactionRecord) -> String? {
        if let stored = row.endToEndReference {
            let trimmed = stored.trimmingCharacters(in: .whitespacesAndNewlines)
            return Dedup.isUnusableReference(trimmed) ? nil : trimmed
        }

        guard let raw = row.descriptionStructured,
              let data = raw.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data),
              let dict = object as? [String: Any],
              let value = dict["end_to_end_reference"] as? String
        else { return nil }

        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return Dedup.isUnusableReference(trimmed) ? nil : trimmed
    }

    /// The stored structured description of a row, as a dictionary.
    static func structuredOf(_ row: TransactionRecord) -> [String: Any] {
        guard let raw = row.descriptionStructured,
              let data = raw.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data),
              let dict = object as? [String: Any]
        else { return [:] }
        return dict
    }

    /// Port of `core/merge.py:preview_merge`. Changes no row.
    public static func previewMerge(db: Database) throws -> MergePreview {
        let rows = try TransactionRecord.fetchAll(
            db,
            sql: "SELECT * FROM transactions WHERE \(TransactionQuery.liveOnlySQL) "
                + "ORDER BY id ASC"
        )

        // The key is "account\0reference\0amount", so that two accounts with one
        // shared reference make no group, and so that a reversal does not join
        // the payment that it reverses. A reversal carries that payment's
        // reference with the opposite sign; the two description forms of one
        // payment always report the same amount.
        //
        // The key normalizes the reference, because the two forms can print one
        // reference with different separators.
        // A row belongs to one group only: the reference key wins, and the
        // counterparty key covers the rows that hold no usable reference.
        var groups: [String: (matchedBy: String, rows: [TransactionRecord])] = [:]
        for row in rows {
            let amount = Dedup.amountKey(Double(truncating: row.amount as NSNumber))
            if let reference = usableReference(row) {
                let key = Dedup.normalizeReference(reference)
                let id = "reference\u{0}\(row.accountNumber)\u{0}\(key)\u{0}\(amount)"
                groups[id, default: ("reference", [])].rows.append(row)
                continue
            }

            // A transfer between two accounts of the user carries no reference.
            let asParsed = ParsedTransaction(
                accountNumber: row.accountNumber,
                transactiondate: row.transactiondate,
                amount: Double(truncating: row.amount as NSNumber),
                description: row.description,
                descriptionStructured: row.descriptionStructured,
                sourceFile: row.sourceFile
            )
            // Caution: use the whole key. It holds the transaction date, and
            // without the date each monthly transfer of one amount to one
            // account joins one group.
            guard let other = Dedup.counterpartyKey(asParsed) else { continue }
            groups["counterparty\u{0}\(other)", default: ("counterparty", [])]
                .rows.append(row)
        }

        var preview = MergePreview()

        for key in groups.keys.sorted() {
            let entry = groups[key]!
            let members = entry.rows
            let matchedBy = entry.matchedBy
            guard members.count >= 2 else { continue }

            // Read the account and the amount from a row, so that the two
            // kinds of key need no shared position.
            let account = members[0].accountNumber
            let amount = Dedup.amountKey(
                Double(truncating: members[0].amount as NSNumber)
            )

            // Show the original text, so that the report names what the bank
            // wrote, and not the comparison form.
            let reference: String
            if matchedBy == "reference" {
                reference = usableReference(members[0]) ?? ""
            } else {
                let data = structuredOf(members[0])
                let iban = data["iban"] as? String ?? ""
                let remittance = data["remittance_info"] as? String ?? ""
                reference = remittance.isEmpty ? iban : "\(iban) / \(remittance)"
            }

            // Two rows of one statement file are two payments. The bank changed
            // the description form between two downloads, so two forms of one
            // payment always come from two files.
            if matchedBy == "counterparty" {
                var perFile: [String: Int] = [:]
                for row in members {
                    let name = row.sourceFile ?? ""
                    perFile[name, default: 0] += 1
                }
                if perFile.values.max() ?? 0 > 1 {
                    preview.refused.append(
                        RefusedGroup(
                            account: account,
                            reference: reference,
                            amount: amount,
                            matchedBy: matchedBy,
                            reason: oneStatementFile,
                            rowIDs: members.map(\.id),
                            manualCategories: Set(
                                members.compactMap { row -> String? in
                                    guard let v = row.manualCategory, !v.isEmpty
                                    else { return nil }
                                    return v
                                }
                            ).sorted()
                        )
                    )
                    continue
                }
            }

            let categories = Set(members.compactMap { row -> String? in
                guard let value = row.manualCategory, !value.isEmpty else { return nil }
                return value
            }).sorted()

            if categories.count > 1 {
                preview.refused.append(
                    RefusedGroup(
                        account: account,
                        reference: reference,
                        amount: amount,
                        matchedBy: matchedBy,
                        reason: conflictingManualCategory,
                        rowIDs: members.map(\.id),
                        manualCategories: categories
                    )
                )
                continue
            }

            // The survivor is the lowest id in the lexicographic order. The
            // choice is stable, so this app and the desktop app pick the same
            // row with no sync. A choice by the import order or by the source
            // file could differ between two machines, and the payment would
            // then disappear from the merged snapshot.
            let ordered = members.sorted { $0.id < $1.id }
            let survivor = ordered[0]
            let others = Array(ordered.dropFirst())

            var carriedCategory: String?
            var carriedTags: String?
            if survivor.manualCategory == nil || survivor.manualCategory?.isEmpty == true {
                carriedCategory = others.first { $0.manualCategory?.isEmpty == false }?
                    .manualCategory
            }
            if survivor.manualTags == nil || survivor.manualTags?.isEmpty == true {
                carriedTags = others.first { $0.manualTags?.isEmpty == false }?.manualTags
            }

            preview.groups.append(
                MergeGroup(
                    account: account,
                    reference: reference,
                    amount: amount,
                    matchedBy: matchedBy,
                    survivorID: survivor.id,
                    mergedIDs: others.map(\.id),
                    carriedCategory: carriedCategory,
                    carriedTags: carriedTags
                )
            )
        }

        return preview
    }

    /// Port of `core/merge.py:merge_duplicates`.
    ///
    /// Flags each row that is not the survivor, and names the survivor in
    /// `merged_into`. Carries the manual categorization to a survivor that
    /// holds none. Changes no row of a refused group.
    @discardableResult
    public static func mergeDuplicates(
        db: Database,
        now: Date = Date()
    ) throws -> MergePreview {
        let preview = try previewMerge(db: db)
        // Return early only when there is nothing at all to record. A refused
        // group still belongs in the report, exactly as in the Python port.
        guard !preview.groups.isEmpty || !preview.refused.isEmpty else {
            return preview
        }

        let stamp = DatabaseDateFormat.dateTime.string(from: now)

        for group in preview.groups {
            if let category = group.carriedCategory {
                try db.execute(
                    sql: "UPDATE transactions SET manual_category = ?, updated_at = ? "
                        + "WHERE id = ?",
                    arguments: [category, stamp, group.survivorID]
                )
            }
            if let tags = group.carriedTags {
                try db.execute(
                    sql: "UPDATE transactions SET manual_tags = ?, updated_at = ? "
                        + "WHERE id = ?",
                    arguments: [tags, stamp, group.survivorID]
                )
            }

            for rowID in group.mergedIDs {
                try db.execute(
                    sql: """
                        UPDATE transactions
                        SET deleted_at = ?, merged_into = ?, updated_at = ?
                        WHERE id = ?
                        """,
                    arguments: [stamp, group.survivorID, stamp, rowID]
                )
            }
        }

        var report = MergeReportRecord(
            createdAt: stamp,
            groups: jsonString(preview.groups.map(\.asDictionary)),
            refused: jsonString(preview.refused.map(\.asDictionary)),
            summary: jsonString([
                "groups": preview.groups.count,
                "rows": preview.rowCount,
                "refused": preview.refused.count,
            ])
        )
        try report.insert(db)

        return preview
    }

    /// Encode a JSON value for the report columns. Returns `nil` when the
    /// value cannot be encoded, so that a report still records the rest.
    static func jsonString(_ value: Any) -> String? {
        guard JSONSerialization.isValidJSONObject(value)
                || value is [Any],
              let data = try? JSONSerialization.data(
                  withJSONObject: value, options: [.sortedKeys]
              )
        else { return nil }
        return String(data: data, encoding: .utf8)
    }

    /// Port of `core/merge.py:undo_merge`. Returns the id of each row that
    /// comes back.
    ///
    /// Clears `deleted_at` and `merged_into` on each row that names the
    /// survivor. Keeps each manual categorization that the merge carried,
    /// because the user may have relied on it since.
    @discardableResult
    public static func undoMerge(
        db: Database,
        survivorID: String,
        now: Date = Date()
    ) throws -> [String] {
        let restored = try String.fetchAll(
            db,
            sql: "SELECT id FROM transactions WHERE merged_into = ? ORDER BY id ASC",
            arguments: [survivorID]
        )
        guard !restored.isEmpty else { return [] }

        let stamp = DatabaseDateFormat.dateTime.string(from: now)
        try db.execute(
            sql: """
                UPDATE transactions
                SET deleted_at = NULL, merged_into = NULL, updated_at = ?
                WHERE merged_into = ?
                """,
            arguments: [stamp, survivorID]
        )
        return restored
    }
}
