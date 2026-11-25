import Foundation
import CryptoKit

/// The Swift analog of the Python parsers' transaction `dict` — every field
/// a Phase D parser (`Parsers/`) produces before dedup/insert. Deliberately
/// mirrors `TransactionRecord`'s column set (minus `id`/`transactionHash`,
/// which are *computed*, not parsed) so `TransactionID.swift`/`Dedup.swift`
/// have a single, clean input shape to work from.
///
/// `amount`/`startsaldo`/`endsaldo` are `Double?` here (not `Decimal?` like
/// `TransactionRecord`) because the Python parsers this type mirrors produce
/// plain Python `float`s — see `ios/docs/spec.md` "Transaction identity &
/// dedup": "the Python parsers produce float amounts, so `-12.30` renders as
/// `"-12.3"`". Conversion to `Decimal` happens in `Dedup.swift` when building
/// the `TransactionRecord` to insert, *after* the id has already been
/// computed from the `Double`.
public struct ParsedTransaction: Equatable {
    public var accountNumber: String
    public var transactiondate: Date?
    public var valuedate: Date?
    public var startsaldo: Double?
    public var endsaldo: Double?
    public var amount: Double?
    public var description: String?
    public var descriptionStructured: String?
    public var mutationcode: String?
    public var currency: String?
    public var sourceFile: String?
    public var sourceLine: Int?
    public var transactionTypeCode: String?
    public var transactionReference: String?
    public var category: String?
    public var manualCategory: String?
    public var tags: String?
    public var manualTags: String?
    public var categorizationSource: String?

    /// Source-specific ids that short-circuit `generate_transaction_id`
    /// (priority order: PayPal, Wise, SEB) — see `core/dedup.py`.
    public var paypalTransactionId: String?
    public var wiseTransactionId: String?
    public var sebVoucherId: String?
    /// The exact krona amount and krona balance of an SEB row, as text with a
    /// period (for example `-412.300`). The SEB voucher key holds them,
    /// because SEB gives one voucher number to many card payments.
    public var sebNativeAmount: String?
    public var sebNativeBalance: String?

    public init(
        accountNumber: String,
        transactiondate: Date? = nil,
        valuedate: Date? = nil,
        startsaldo: Double? = nil,
        endsaldo: Double? = nil,
        amount: Double? = nil,
        description: String? = nil,
        descriptionStructured: String? = nil,
        mutationcode: String? = nil,
        currency: String? = nil,
        sourceFile: String? = nil,
        sourceLine: Int? = nil,
        transactionTypeCode: String? = nil,
        transactionReference: String? = nil,
        category: String? = nil,
        manualCategory: String? = nil,
        tags: String? = nil,
        manualTags: String? = nil,
        categorizationSource: String? = nil,
        paypalTransactionId: String? = nil,
        wiseTransactionId: String? = nil,
        sebVoucherId: String? = nil,
        sebNativeAmount: String? = nil,
        sebNativeBalance: String? = nil
    ) {
        self.accountNumber = accountNumber
        self.transactiondate = transactiondate
        self.valuedate = valuedate
        self.startsaldo = startsaldo
        self.endsaldo = endsaldo
        self.amount = amount
        self.description = description
        self.descriptionStructured = descriptionStructured
        self.mutationcode = mutationcode
        self.currency = currency
        self.sourceFile = sourceFile
        self.sourceLine = sourceLine
        self.transactionTypeCode = transactionTypeCode
        self.transactionReference = transactionReference
        self.category = category
        self.manualCategory = manualCategory
        self.tags = tags
        self.manualTags = manualTags
        self.categorizationSource = categorizationSource
        self.paypalTransactionId = paypalTransactionId
        self.wiseTransactionId = wiseTransactionId
        self.sebVoucherId = sebVoucherId
        self.sebNativeAmount = sebNativeAmount
        self.sebNativeBalance = sebNativeBalance
    }
}

/// Port of `core/dedup.py:generate_transaction_id`.
public enum TransactionID {

    /// Python's `str(trans.get("transactiondate", ""))`/`str(trans.get("amount", ""))`/
    /// `str(trans.get("description", ""))` is a subtle trap: `dict.get(key, default)`
    /// only substitutes `default` when the *key is absent*. Every field this
    /// type models is a key the real parsers always set (even if the value is
    /// `None`), so a `nil` field renders as the **literal string `"None"`**,
    /// not `""` — see `ios/docs/spec.md`'s "LOOK AT parity.json transaction_id
    /// last case" note and the fixture case
    /// `{"accountNumber": "", "transactiondate": null, "amount": null, "description": null}`
    /// -> `"_None_None_6adf97f83acf6453"`.
    private static func pythonNoneAware(_ value: String?) -> String {
        value ?? "None"
    }

    /// Renders a `Date` the way Python's `str(date(...))` does: ISO
    /// `yyyy-MM-dd`.
    private static func pythonDateString(_ date: Date?) -> String {
        guard let date else { return "None" }
        return DatabaseDateFormat.dateOnly.string(from: date)
    }

    /// Renders a `Double` the way Python's `str(float)` does: the shortest
    /// decimal string that round-trips back to the same value (Swift's
    /// default `Double` `description`/string-interpolation uses the same
    /// "shortest round-trip" algorithm as Python's `repr(float)`/`str(float)`
    /// for realistic monetary magnitudes — see `ios/docs/spec.md` and the
    /// `transaction_id_float_amounts` fixture, which is exactly this guard).
    private static func pythonFloatString(_ amount: Double?) -> String {
        guard let amount else { return "None" }
        return "\(amount)"
    }

    /// The core id-assembly logic, taking already-`str()`-rendered
    /// components. Exists separately from the `ParsedTransaction` overload
    /// below so tests can feed it the *exact* string components some parity
    /// fixture cases were generated with (Python `Decimal` renderings like
    /// `"100.00"`/`"100"`, which preserve trailing/absent decimal digits in a
    /// way a `Double`-typed amount cannot — see `parity.json`'s
    /// `transaction_id` cases 0-3, generated by feeding `Decimal` values
    /// directly into the Python function, vs `transaction_id_float_amounts`,
    /// generated with real `float`s). Production callers should use
    /// `generateTransactionID(_:)` below; this exists for exact fixture
    /// parity testing of the string-rendering edge cases.
    public static func generateTransactionID(
        account: String,
        paypalTransactionId: String?,
        wiseTransactionId: String?,
        sebVoucherId: String?,
        dateComponent: String,
        amountComponent: String,
        descriptionComponent: String,
        sebAmount: String? = nil,
        sebBalance: String? = nil
    ) -> String {
        if let paypal = paypalTransactionId, !paypal.isEmpty {
            return "\(account)_\(paypal)"
        }
        if let wise = wiseTransactionId, !wise.isEmpty {
            return "\(account)_\(wise)"
        }
        if let seb = sebVoucherId, !seb.isEmpty {
            return sebVoucherKey(
                account: account, voucher: seb, bookingDate: dateComponent,
                amount: sebAmount, balance: sebBalance
            )
        }
        let descHash = md5Hex16(descriptionComponent)
        return "\(account)_\(dateComponent)_\(amountComponent)_\(descHash)"
    }

    /// Production entry point: builds the id from a `ParsedTransaction`
    /// (`Double` amount, `Date` transaction date — the shapes Phase D
    /// parsers produce).
    public static func generateTransactionID(_ transaction: ParsedTransaction) -> String {
        generateTransactionID(
            account: transaction.accountNumber,
            paypalTransactionId: transaction.paypalTransactionId,
            wiseTransactionId: transaction.wiseTransactionId,
            sebVoucherId: transaction.sebVoucherId,
            dateComponent: pythonDateString(transaction.transactiondate),
            amountComponent: pythonFloatString(transaction.amount),
            descriptionComponent: pythonNoneAware(transaction.description),
            sebAmount: transaction.sebNativeAmount,
            sebBalance: transaction.sebNativeBalance
        )
    }

    // MARK: - SEB voucher key (`core/dedup.py:seb_voucher_key`)

    /// Returns the id of an SEB transaction:
    /// `<account>_<voucher>_<YYYY-MM-DD>_<krona amount>_<krona balance>`.
    /// SEB gives one voucher number to many card payments, so the id also
    /// holds the booking date, the krona amount, and the krona balance. The
    /// shared fixture `Fixtures/seb_ids.json` holds the cases that the
    /// desktop app and this app must agree on.
    public static func sebVoucherKey(
        account: String, voucher: String, bookingDate: String, amount: String?, balance: String?
    ) -> String {
        [account, voucher, String(bookingDate.prefix(10)), formatKrona(amount), formatKrona(balance)]
            .joined(separator: "_")
    }

    /// Writes a krona value with exactly 2 decimal places, a period, and a
    /// leading `-` for a negative value. The value is rounded half up (away
    /// from zero), as Python's `ROUND_HALF_UP`. A missing value gives an
    /// empty text.
    public static func formatKrona(_ text: String?) -> String {
        guard let text, !text.isEmpty,
              let value = Decimal(string: text, locale: Locale(identifier: "en_US_POSIX"))
        else { return "" }
        var cents = value * 100
        var rounded = Decimal()
        NSDecimalRound(&rounded, &cents, 0, .plain)
        let negative = rounded < 0
        var digits = (negative ? -rounded : rounded).description
        while digits.count < 3 { digits = "0" + digits }
        let split = digits.index(digits.endIndex, offsetBy: -2)
        return (negative ? "-" : "") + digits[..<split] + "." + digits[split...]
    }

    /// Returns the SEB voucher key for a stored SEB row that has an id in the
    /// old form `<account>_<voucher>`, or nil when the row needs no change.
    /// The values come from the structured description of the row. The
    /// GRDB migration `v7` and the snapshot import use this function.
    public static func upgradedSEBID(
        id: String, accountNumber: String, bookingDate: String?, descriptionStructured: String?
    ) -> String? {
        guard accountNumber.hasPrefix("seb:"),
              let bookingDate, !bookingDate.isEmpty,
              let structured = descriptionStructured,
              let object = try? JSONSerialization.jsonObject(with: Data(structured.utf8)),
              let values = object as? [String: Any],
              let voucher = values["voucher_number"] as? String, !voucher.isEmpty,
              id == "\(accountNumber)_\(voucher)",
              let amount = kronaText(values["native_amount"])
        else { return nil }
        return sebVoucherKey(
            account: accountNumber, voucher: voucher, bookingDate: bookingDate,
            amount: amount, balance: kronaText(values["native_balance"])
        )
    }

    /// Renders a JSON number the way Python's `str(float)` does, so that a
    /// value such as `-412.3` keeps its exact decimal text.
    private static func kronaText(_ value: Any?) -> String? {
        switch value {
        case let text as String: return text
        case let number as NSNumber: return "\(number.doubleValue)"
        default: return nil
        }
    }

    /// MD5 hex digest of the UTF-8 description, first 16 hex characters —
    /// `hashlib.md5(description.encode("utf-8")).hexdigest()[:16]`.
    static func md5Hex16(_ description: String) -> String {
        let digest = Insecure.MD5.hash(data: Data(description.utf8))
        let hex = digest.map { String(format: "%02x", $0) }.joined()
        return String(hex.prefix(16))
    }
}
