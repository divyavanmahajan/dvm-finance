import Foundation

/// Errors a Phase D parser can raise that the Python source doesn't model as
/// a typed exception (Python raises a bare `ValueError` for both cases this
/// covers — `parsers/__init__.py:33` for an unrecognized extension,
/// `parsers/xls.py`'s absence for `.xls`/`.xlsx`).
public enum ParserError: Error, Equatable {
    /// `.xls`/`.xlsx`, or any other unrecognized extension. `message` is a
    /// user-facing explanation (XLS specifically notes the CoreXLSX
    /// dependency gap — see `ios/docs/spec.md` "Ingest": "XLS import is
    /// deferred (needs CoreXLSX; note in backlog)").
    case unsupportedFormat(String)
    /// A file's bytes could not be decoded under the encoding(s) its parser
    /// expects (mirrors Python's `UnicodeDecodeError`/`ValueError` for a
    /// malformed statement file).
    case decodingFailed
}

/// Port of `src/abn_combined/parsers/__init__.py:parse_statement_file` — the
/// extension-based auto-detection dispatcher. Per the Python module's own
/// doc comment ("PayPal, Wise and SEB exports (all `.txt`/`.csv`) are
/// dispatched explicitly by the importer, not auto-detected here"), this
/// type only ever resolves to MT940 or the generic ABN CSV path; the
/// explicit picker for PayPal/Wise/SEB (mirroring `core/importer.py`'s
/// `fmt` parameter / `VALID_FORMATS`) is `StatementFormat` below, for the
/// Phase E Import UI to drive directly.
public enum StatementFileParser {

    /// Dispatches by lowercased file extension:
    ///   - `.mt940`/`.mta`/`.sta`/`.txt` -> `MT940Parser` (`_parse_mt940_basic`
    ///     only — see `MT940Parser.swift`'s doc comment for why the optional
    ///     `abnamroparser`-library path is out of scope)
    ///   - `.csv` -> `CSVParser` (generic ABN-style CSV)
    ///   - `.xls`/`.xlsx` -> `ParserError.unsupportedFormat` (desktop's
    ///     `parse_xls_file` is explicitly out of scope on iOS)
    ///   - anything else -> `ParserError.unsupportedFormat`
    ///
    /// `source_file` is stamped on every returned transaction with `fileURL`'s
    /// last path component, exactly as `parsers/__init__.py:35-36` does it
    /// uniformly for every dispatched format (and as `core/importer.py:98-99`
    /// re-does it again at the unified-import-pipeline level, keeping the
    /// user-facing name stable regardless of any on-disk storage renaming —
    /// the iOS import flow has no such renaming step, but the re-stamp is
    /// harmless and keeps this function's contract self-sufficient).
    public static func parse(fileURL: URL) throws -> [ParsedTransaction] {
        let suffix = fileURL.pathExtension.lowercased()
        let sourceFileName = fileURL.lastPathComponent

        var transactions: [ParsedTransaction]
        switch suffix {
        case "mt940", "mta", "sta", "txt":
            transactions = try MT940Parser.parse(fileURL: fileURL)
        case "csv":
            transactions = try CSVParser.parse(fileURL: fileURL)
        case "xls", "xlsx":
            throw ParserError.unsupportedFormat(
                "XLS/XLSX statement files are not supported on iOS (no CoreXLSX dependency in v1). "
                    + "Export a CSV or MT940 statement instead."
            )
        default:
            throw ParserError.unsupportedFormat("Unsupported file format: .\(suffix)")
        }

        for index in transactions.indices {
            transactions[index].sourceFile = sourceFileName
        }
        return transactions
    }
}

/// Explicit statement-format selector, mirroring `core/importer.py`'s `fmt`
/// parameter / `VALID_FORMATS` (`"auto"`/`"paypal"`/`"wise"`/`"seb"`/`"csv"`)
/// — the Phase E Import UI uses this so the user can pick PayPal/Wise/SEB
/// explicitly instead of relying on (impossible, for these formats)
/// extension auto-detection. `.mt940`/`.abnCSV` cover the `"auto"`/`"csv"`
/// desktop options for symmetry; both also work via `StatementFileParser`
/// directly.
public enum StatementFormat: String, CaseIterable, Identifiable, Sendable {
    case mt940
    case abnCSV
    case paypal
    case wise
    case seb

    public var id: String { rawValue }

    /// Parses `url` as the explicitly-selected `format`. Every individual
    /// parser already stamps `source_file` internally
    /// (`PayPalParser`/`WiseParser`/`SEBParser`/`CSVParser`/`MT940Parser`
    /// all set it from the same `url.lastPathComponent`), but this
    /// re-stamps unconditionally too, matching `core/importer.py:98-99`'s
    /// belt-and-suspenders re-stamp in the unified import pipeline.
    public static func parse(url: URL, as format: StatementFormat) throws -> [ParsedTransaction] {
        var transactions: [ParsedTransaction]
        switch format {
        case .mt940:
            transactions = try MT940Parser.parse(fileURL: url)
        case .abnCSV:
            transactions = try CSVParser.parse(fileURL: url)
        case .paypal:
            transactions = try PayPalParser.parse(fileURL: url)
        case .wise:
            transactions = try WiseParser.parse(fileURL: url)
        case .seb:
            transactions = try SEBParser.parse(fileURL: url)
        }

        let sourceFileName = url.lastPathComponent
        for index in transactions.indices {
            transactions[index].sourceFile = sourceFileName
        }
        return transactions
    }
}
