import Foundation
import GRDB

/// Port of `core/restructure.py`.
///
/// The rules read the stored structured description, and not the raw text. A
/// rename of a key in the parser therefore changes nothing for a row that the
/// app already stored. This module reparses each stored SEPA description with
/// the present parser, and it renames the field target of each rule that names
/// a renamed key.
///
/// Both passes are self-limiting and idempotent. After the first run no row and
/// no rule holds an old shape, so a later launch reads them and writes nothing.
///
/// The app runs both passes after `AppDatabase` finishes its migrations. The
/// desktop app runs the same two passes at startup. Either app may run first.
public enum Restructure {

    // MARK: - The stored structured description

    /// The two key names that the labelled parser used before the change.
    static let oldKeys = ["description", "reference"]

    /// Port of `core/restructure.py:needs_rewrite`.
    ///
    /// A row needs the rewrite when one of three tests holds:
    ///
    /// - It holds the format `sepa` with one of the two old key names.
    /// - It holds the format `mt940` with a transaction type that starts with
    ///   `SEPA`. A tagged SEPA row carried that format before the change.
    /// - It hides `CSID` or `MARF` inside `other_fields`.
    static func needsRewrite(_ data: [String: Any]) -> Bool {
        let format = data["format"] as? String

        if format == "sepa", oldKeys.contains(where: { data[$0] != nil }) {
            return true
        }

        if format == "mt940",
           let type = data["transaction_type"] as? String,
           type.uppercased().hasPrefix("SEPA") {
            return true
        }

        if let other = data["other_fields"] as? [String: Any],
           other["CSID"] != nil || other["MARF"] != nil {
            return true
        }

        return false
    }

    /// Port of `core/restructure.py:rewrite_sepa_structured_descriptions`.
    /// Returns the number of rewritten rows.
    ///
    /// The function writes the new value only when the parser returns one, so
    /// that a row with an unparseable description keeps what it holds. It does
    /// not touch the category, the tags, or any manual field, so it changes no
    /// categorization.
    @discardableResult
    public static func rewriteSEPAStructuredDescriptions(db: Database) throws -> Int {
        let rows = try Row.fetchAll(
            db,
            sql: """
                SELECT id, description, description_structured FROM transactions
                WHERE description_structured IS NOT NULL
                """
        )

        var rewritten = 0
        for row in rows {
            guard let id: String = row["id"],
                  let raw: String = row["description_structured"],
                  let data = raw.data(using: .utf8),
                  let object = try? JSONSerialization.jsonObject(with: data),
                  let dict = object as? [String: Any],
                  needsRewrite(dict)
            else { continue }

            let description: String = row["description"] ?? ""
            guard let parsed = DescriptionParser.parseTransactionDescription(description)
            else { continue }

            var reference: String?
            if let parsedData = parsed.data(using: .utf8),
               let parsedObject = try? JSONSerialization.jsonObject(with: parsedData),
               let parsedDict = parsedObject as? [String: Any],
               let value = parsedDict["end_to_end_reference"] as? String {
                let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
                if !Dedup.isUnusableReference(trimmed) { reference = trimmed }
            }

            if let reference {
                try db.execute(
                    sql: """
                        UPDATE transactions
                        SET description_structured = ?, end_to_end_reference = ?
                        WHERE id = ?
                        """,
                    arguments: [parsed, reference, id]
                )
            } else {
                try db.execute(
                    sql: "UPDATE transactions SET description_structured = ? WHERE id = ?",
                    arguments: [parsed, id]
                )
            }
            rewritten += 1
        }

        return rewritten
    }

    // MARK: - The field target of a rule

    /// Port of `core/restructure.py:_RENAMES`.
    static let renames = ["reference": "end_to_end_reference"]

    /// Port of `core/restructure.py:_STRUCTURED_RENAMES`.
    ///
    /// The raw description keeps the field target `description`. Both match
    /// functions short-circuit that target to the raw text, whatever the rule
    /// type. Only a rule of the type `structured_field` reads the structured
    /// key of that name, so only such a rule takes this rename. An extra
    /// condition never takes it.
    static let structuredRenames = ["description": "remittance_info"]

    static let structuredRuleType = "structured_field"

    /// Port of `core/restructure.py:_new_target`. Returns the new field target,
    /// or `nil` when the old one stays.
    static func newTarget(fieldTarget: String?, ruleType: String?) -> String? {
        guard let fieldTarget, !fieldTarget.isEmpty else { return nil }
        if let renamed = renames[fieldTarget] { return renamed }
        if ruleType == structuredRuleType, let renamed = structuredRenames[fieldTarget] {
            return renamed
        }
        return nil
    }

    /// One renamed field target, for the report of the pass.
    public struct RenamedTarget: Equatable {
        public var kind: String
        public var identifier: String
        public var from: String
        public var to: String
    }

    /// Port of `core/restructure.py:migrate_rule_field_targets`.
    ///
    /// Renames the field target of each rule that names a renamed key, and
    /// returns what it changed. The caller reapplies the rules afterwards, so
    /// that no categorization changes without a record. A manual
    /// categorization does not change, because `Categorizer` skips a manually
    /// categorized row.
    @discardableResult
    public static func migrateRuleFieldTargets(db: Database) throws -> [RenamedTarget] {
        var changed: [RenamedTarget] = []

        for rule in try CategorizationRuleRecord.fetchAll(db) {
            guard let target = newTarget(
                fieldTarget: rule.fieldTarget,
                ruleType: rule.ruleType
            ) else { continue }
            changed.append(
                RenamedTarget(
                    kind: "rule",
                    identifier: rule.uuid,
                    from: rule.fieldTarget ?? "",
                    to: target
                )
            )
            try db.execute(
                sql: "UPDATE categorization_rules SET field_target = ? WHERE uuid = ?",
                arguments: [target, rule.uuid]
            )
        }

        // An extra condition takes the reference rename only.
        for condition in try RuleConditionRecord.fetchAll(db) {
            guard let target = renames[condition.fieldTarget] else { continue }
            guard let id = condition.id else { continue }
            changed.append(
                RenamedTarget(
                    kind: "condition",
                    identifier: String(id),
                    from: condition.fieldTarget,
                    to: target
                )
            )
            try db.execute(
                sql: "UPDATE rule_conditions SET field_target = ? WHERE id = ?",
                arguments: [target, id]
            )
        }

        return changed
    }

    /// Run both one-time passes. The app calls this after the migrations.
    @discardableResult
    public static func runOnce(appDatabase: AppDatabase) throws -> (rows: Int, rules: Int) {
        try appDatabase.dbWriter.write { db in
            let rows = try rewriteSEPAStructuredDescriptions(db: db)
            let rules = try migrateRuleFieldTargets(db: db)
            return (rows, rules.count)
        }
    }
}
