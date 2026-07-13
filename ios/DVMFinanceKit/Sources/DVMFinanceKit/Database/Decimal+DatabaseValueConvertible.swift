import Foundation
import GRDB

/// GRDB ships `DatabaseValueConvertible` conformances for `Int`, `Double`,
/// `String`, `Bool`, `Date`, `UUID`, ... but deliberately not for
/// Foundation's `Decimal`, because a naive conformance would round-trip it
/// through `Double` and silently lose precision on monetary values. This is
/// the standard workaround documented in GRDB's own FAQ ("How do I store
/// Decimal values?"): store the canonical base-10 string and parse it back
/// exactly, so every `transactions`/`budgets` amount and saldo column
/// (`core/models.py`: `Numeric(15, 2)` / `Numeric(10, 2)`) round-trips
/// byte-for-byte.
///
/// The corresponding columns are declared with GRDB's `.text` column type
/// (not `.numeric`) in `AppDatabase`'s migration — see the comment there for
/// why `.numeric`/`.date` SQLite type affinity would risk silently
/// reformatting these strings through SQLite's own numeric coercion.
///
/// Note: on toolchains that enable Swift 6's "retroactive conformance"
/// warning (SE-0364), this file may need an `@retroactive` annotation; it is
/// omitted here for Swift 5.9 compatibility (the deployment toolchain named
/// in `ios/docs/plan.md`).
extension Decimal: DatabaseValueConvertible {
    public var databaseValue: DatabaseValue {
        (self as NSDecimalNumber).stringValue.databaseValue
    }

    public static func fromDatabaseValue(_ dbValue: DatabaseValue) -> Decimal? {
        switch dbValue.storage {
        case .string(let string):
            return Decimal(string: string, locale: Locale(identifier: "en_US_POSIX"))
        case .int64(let int):
            return Decimal(int)
        case .double(let double):
            return Decimal(double)
        case .null, .blob:
            return nil
        }
    }
}
