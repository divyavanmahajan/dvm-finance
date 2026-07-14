import Foundation

/// A generic JSON value, used for two things in `Snapshot/`:
///
/// 1. Fields that carry genuinely arbitrary JSON in `core/snapshots.py` —
///    `rule_change_reports.rule_before`/`rule_after`/`summary` are Python
///    `dict | None` columns (SQLAlchemy `JSON`) whose shape is "whatever
///    `rule_snapshot()`/a hand-built summary dict happened to contain", not a
///    fixed schema.
/// 2. A uniform intermediate representation for the incoming-wins **diff**
///    machinery in `SnapshotImporter.swift`: `SnapshotCodec.comparableObject(_:)`
///    builds a `[String: JSONValue]` "comparable object" per entity
///    (`Categorizer.RuleSnapshot`, `SnapshotTransaction`, `SnapshotBudget`),
///    giving `SnapshotImporter.diff(local:incoming:)` a `Python dict`-shaped
///    value to compare field-by-field — mirrors `core/snapshots.py:_diff`'s
///    `dict`-of-`dict` shape exactly, including nested values (e.g. a rule's
///    `conditions` array inside a diffed field). These comparable objects are
///    built explicitly field-by-field rather than via a generic
///    `Encodable`-to-`JSONValue` round trip, precisely so every field key is
///    always present (see the long comment above `SnapshotCodec`'s
///    `comparableObject` overloads for why that matters).
public enum JSONValue: Equatable {
    case string(String)
    case int(Int64)
    case double(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    /// Python's `None`/JSON `null` coerced away for `_diff`'s "missing key"
    /// fallback (`local.get(key)` defaults to `None`); missing entries in a
    /// `[String: JSONValue]` comparable-object dict use this via
    /// `dict[key] ?? .null`.
    public static func lookup(_ dictionary: [String: JSONValue], _ key: String) -> JSONValue {
        dictionary[key] ?? .null
    }
}

extension JSONValue: Codable {
    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            // Must precede Int64/Double: some JSON decoders will happily
            // coerce a boolean into a numeric type otherwise.
            self = .bool(value)
        } else if let value = try? container.decode(Int64.self) {
            self = .int(value)
        } else if let value = try? container.decode(Double.self) {
            self = .double(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else {
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Unsupported JSON value"
            )
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value): try container.encode(value)
        case .int(let value): try container.encode(value)
        case .double(let value): try container.encode(value)
        case .bool(let value): try container.encode(value)
        case .object(let value): try container.encode(value)
        case .array(let value): try container.encode(value)
        case .null: try container.encodeNil()
        }
    }
}

extension JSONValue {
    /// `JSONValue.string`/`.int` builders for literal construction in
    /// `SnapshotImporter`'s hand-built overwrite/report records (avoids
    /// `ExpressibleByLiteral` boilerplate for the handful of call sites that
    /// build a `JSONValue` from a known-concrete Swift value rather than by
    /// decoding).
    static func from(_ value: String?) -> JSONValue {
        value.map(JSONValue.string) ?? .null
    }

    static func from(_ value: Int?) -> JSONValue {
        value.map { JSONValue.int(Int64($0)) } ?? .null
    }

    static func from(_ value: Int64?) -> JSONValue {
        value.map(JSONValue.int) ?? .null
    }

    static func from(_ value: Bool?) -> JSONValue {
        value.map(JSONValue.bool) ?? .null
    }
}
