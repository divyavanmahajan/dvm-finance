# DVM Finance iOS — Specification (v1)

A standalone native iOS/iPadOS companion app for `abn-combined` (dvm-finance).
SwiftUI, local SQLite via GRDB, no server dependency. The Python web app
remains the primary workstation tool; the iOS app is a **review-first viewer
with file import and snapshot sync**.

## Product decisions (locked with the user, 2026-07-13)

1. **Architecture**: standalone native app (SwiftUI + GRDB/SQLite). Fully
   offline. Interoperates with the desktop app exclusively through the
   existing gzipped-JSON snapshot format.
2. **Ingest**: statement **file import** (MT940 + the CSV family: ABN CSV,
   PayPal, Wise, SEB) via the Files app / share sheet, with the same
   deterministic-id dedup and automatic rule application as desktop
   auto-import. XLS import is deferred (needs CoreXLSX; note in backlog).
   Browser-automation downloads (Playwright/CDP) are impossible on iOS and
   permanently out of scope.
3. **v1 scope — read-only viewer**: browse Transactions and Category Trends.
   **No rule editing, no manual categorization, no budgets, no cash flow** in
   v1. Rules arrive via snapshot import and are applied automatically to
   file-imported transactions (identical semantics to desktop auto-import,
   audited as an `import` change report). Snapshot **export** is included so
   transactions imported on the phone can flow back to the desktop app —
   without it, file import would be a data dead-end.
4. **Location**: `ios/` folder in this repo. Project generated with XcodeGen
   (`project.yml`); built and signed on the user's Mac. Targets iPhone and
   iPad, iOS 17+.

## Inherited core beliefs (adapted)

The project's `docs/core-beliefs.md` applies with these translations:

- **Port, don't rewrite** — Swift code mirrors the Python semantics
  function-for-function. The Python files are the source of truth; every
  ported unit names its Python origin in its doc comment.
- **Manual edits are sacred** — the app never writes `manual_category` /
  `manual_tags` except via snapshot import (incoming wins, by explicit user
  action). The two-pass rule engine skips manual transactions in pass 1.
- **Every categorization run is auditable** — file import and snapshot import
  both persist `rule_change_reports` rows exactly like desktop.
- **No LLM, no auth, no charts** — trends are a table, not a chart.
- **Deterministic identity everywhere** — transaction ids and rule UUIDs are
  byte-identical to what the Python code produces for the same input, so
  snapshots merge across devices without heuristics.
- **Filter state lives in the navigation state** — the URL principle maps to
  a single `TransactionFilter` value type passed through navigation, so
  trends click-through and the transactions screen share one mechanism.
- **Schema changes via GRDB migrations only** — `DatabaseMigrator` with
  ordered, append-only migrations. The iOS SQLite file is *not* the desktop
  `abn_combined.db` and never will be opened by the Python app (sync is
  snapshot-only), but the schema mirrors it 1:1 to keep the port simple.

## Module layout

```
ios/
  project.yml                    # XcodeGen; app target DVMFinance + test targets
  README.md                      # build instructions (xcodegen, signing, sideload)
  DVMFinance/                    # app target: SwiftUI views + app wiring only
    DVMFinanceApp.swift
    Views/...
  DVMFinanceKit/                 # local SwiftPM package: ALL logic, no UI
    Package.swift                # depends on GRDB.swift (SPM)
    Sources/DVMFinanceKit/
      Database/                  # AppDatabase (GRDB), migrations, record types
      Core/                      # Normalize, TransactionID, Dedup, Categorizer
      Snapshot/                  # SnapshotCodec, SnapshotImporter/Exporter
      Parsers/                   # MT940, ABNCSV, PayPal, Wise, SEB, DescriptionParser
      Query/                     # TransactionFilter, TrendsBuilder
    Tests/DVMFinanceKitTests/    # XCTest; fixtures ported from Python tests
  docs/spec.md, docs/plan.md
```

Rule: the app target contains **no business logic** — everything testable
lives in `DVMFinanceKit` so XCTest covers it without UI tests.

## Data model

Mirror these tables byte-for-byte in column names and meaning (source:
`src/abn_combined/core/models.py`): `transactions`, `categorization_rules`
(incl. `uuid`, `is_tag_only`, the four `filter_*` context columns),
`rule_conditions`, `budgets` (schema only in v1 — imported/exported through
snapshots, no UI), `rule_change_reports`, `rule_change_items`,
`snapshot_imports`. `download_state` is **not** ported (no downloads on iOS).

Column-name fidelity (`accountNumber`, `transactiondate`, `valuedate`,
`startsaldo`, `endsaldo`, …) is required so the snapshot codec is a plain
field-for-field mapping.

Key invariants (identical to desktop):

- Effective category = `manual_category ?? category`; same for tags.
- Amounts and saldi are stored as `Decimal` (SQLite TEXT/NUMERIC via GRDB
  `Decimal` handling); snapshot serialization uses decimal **strings**.
- Dates are ISO-8601 `yyyy-MM-dd` strings in snapshots; `DATE` in SQLite.
- `rule_change_reports.rule_before/rule_after/summary` and
  `snapshot_imports.counts/overwrites` are JSON `TEXT` columns.

## Core logic contracts (ports)

Each Swift unit must reproduce the named Python function's observable
behavior, verified by tests that reuse the Python test fixtures.

### Normalization (`core/utils.py`)
- `normalizeCategory(_:)` — lowercase, comma-split/trim/rejoin, nil for blank.
- `normalizeStringForMatching(_:)` — nil→"", strip ALL whitespace, remove
  literal `WERO/`, lowercase. Order matters: whitespace removal happens
  before the `WERO/` replacement and lowercasing (so `WERO /x` → `WERO/x` →
  `x`).
- `calculateTransactionHash(date:description:amount:account:)` — SHA-256 of
  `"{account_norm}|{date_iso}|{desc_norm}|{amount:.2f}"`, amount formatted
  with exactly two decimals, non-numeric → `0.00`.
- `CATEGORY_SEPARATOR = "-"`; `isTransferCategory` = effective category
  matches `transfer*` prefix (see `core/utils.py` / `_is_transfer` — note
  desktop has two variants: filters use prefix `transfer*`, categorizer's
  preview uses substring `contains "transfer"`; iOS uses the **prefix**
  variant everywhere views/aggregations are concerned, matching
  `is_transfer_category()`).

### Transaction identity & dedup (`core/dedup.py`)
- `generateTransactionID`: `"\(account)_\(paypal|wise|seb id)"` when a
  source-specific id exists, else
  `"\(account)_\(date)_\(amount)_\(md5(description)[0..<16])"`.
  **MD5 hex, first 16 chars, of the UTF-8 description** — must match Python's
  `hashlib.md5(...).hexdigest()[:16]`. The `date` and `amount` components are
  Python `str()` renderings: date as `yyyy-MM-dd`, amount as the parser
  produced it (see plan: parsers must carry the string form so ids stay
  stable — Python renders `Decimal("12.30")` as `"12.30"`).
- `checkDuplicates`: in-batch dedup first (first occurrence wins), then
  against existing DB ids. `insertTransactions` = upsert (merge semantics),
  applies `normalizeCategory` to category fields, computes
  `transaction_hash`.

### Rule engine (`core/categorizer.py`)
- Match semantics: `_apply_rule_to_transaction` ported exactly — primary
  condition by `rule_type` (`structured_field`, `account_iban` with IBAN
  regex fallback `IBAN[:\s]+([A-Z]{2}\d{2}[A-Z0-9]{4,30})` on uppercased
  description, `full_description`, default field-target dispatch), then
  sequential left-fold of extra conditions (`AND`/`OR` in `sort_order`), then
  context filters (account exact, currency exact, date range inclusive).
- Match patterns: `contains`, `exact`, `starts_with`, `ends_with` on
  *normalized* strings; `regex` = case-insensitive search of the **raw
  pattern** against the *normalized* field value; invalid regex → no match.
  Use `NSRegularExpression`; document any ICU-vs-Python syntax divergence in
  code comments (both are fine for the patterns real rules use).
- `applyRules` two-pass exactly as documented in `docs/architecture.md`
  (§ Rules categorization): pass 1 category rules, priority asc / id asc,
  first match wins, non-manual only, no-match ⇒ category=nil,
  `categorization_source = String(rule.id)` kept in sync even when values
  don't change; pass 2 tag-only rules, ALL transactions, every match merges
  tags via order-preserving de-dup union on `,`.
- `recordRuleChange(action:...)` persists report + items. v1 uses only
  `action="import"` (both file import and snapshot import); the enum still
  carries all six actions for schema parity.
- `preview_rule` is **not** ported in v1 (no rule editing).

### Snapshot codec (`core/snapshots.py`)
- Format: gzipped JSON, `schema_version` 1, header with `exported_at` and
  `machine_id` (UUID persisted in the app's Application Support dir).
- Import contract (mirrors desktop steps 1–5): validate (corrupt gzip/JSON or
  wrong schema_version ⇒ typed error, nothing written); back up the SQLite
  file to `dvm_finance.backup-YYYYMMDD-HHMMSS.db`; merge in ONE transaction —
  insert-or-overwrite incoming wins including manual fields and rules, never
  delete local rows; remap incoming `categorization_source` rule ids to local
  rule ids via rule `uuid`; budgets identity `(category, period, start_date)`;
  reports matched on `(created_at, action, rule_uuid)`; persist
  `snapshot_imports` row + an `action="import"` change report of effective
  category/tag changes. Rules are NOT reapplied after import.
- Export: every transactions column; rules in `rule_snapshot()` shape with
  nested conditions; budgets without machine-local id; full
  `rule_change_reports` with items. Dates ISO strings, numerics decimal
  strings. Output shared via the iOS share sheet
  (`snapshot-YYYYMMDD-HHMMSS.json.gz`).
- Round-trip requirement: desktop→iOS→desktop must be lossless for all
  exported fields (tested against a fixture generated by the Python code).

### Parsers (`parsers/`)
Ported: `mt940.py`, `csv.py` (ABN), `paypal.py`, `wise.py`, `seb.py`, plus
`description.py` (structured-description extraction) and `parsers/utils.py`.
`description_structured` **must** be populated identically to desktop —
snapshot-imported rules of type `structured_field`/`account_iban` match on
those JSON fields, so skipping this parser would silently break
categorization parity. Deferred: `xls.py`.

File import flow: pick file(s) → detect format (same heuristics as
`parsers/__init__.py` / upload API) → parse → `checkDuplicates` →
`insertTransactions` → `applyRules` on the new ids → record `import` change
report → show summary (imported / duplicates / categorized counts).

### Filters & trends (`core/filters.py`, `core/trends.py`)
- `TransactionFilter` value type: free-text search, include-categories,
  **exclude-categories** (both with subtree semantics via the `-` separator:
  selecting `fixed` covers `fixed-insurance-life`), account, date range,
  uncategorized-only, `includeTransfers` (default **false**, excluding
  `transfer*` effective categories).
- Trends: month × top-level-category matrix (rollup on first `-` segment),
  expandable to exact child categories; every cell navigates to the
  Transactions screen with the equivalent `TransactionFilter` so the list
  sums exactly to the cell. Respects transfer exclusion with an on-screen
  toggle (session-scoped, like desktop).

## UI (SwiftUI, iPhone + iPad)

Tab bar: **Transactions · Trends · Import**.

1. **Transactions** — searchable list grouped by date; effective category and
   tags shown per row; filter sheet (categories include/exclude picker built
   from distinct effective categories, account, date range, uncategorized
   toggle, transfers toggle); row → detail view showing every field incl.
   structured description key/values, rule that categorized it
   (`categorization_source`), and source file/line. Read-only.
2. **Trends** — scrollable matrix (last 12 months default, period picker),
   income/expense sign conventions identical to desktop trends; tap-through
   as above.
3. **Import** — three actions: *Import statement file*, *Import snapshot*,
   *Export snapshot*; below them, history lists of `snapshot_imports` and
   `rule_change_reports` (read-only audit views with per-transaction items).

iPad: same screens; NavigationSplitView where it helps (transactions
master/detail). Dark mode supported (system colors only). No custom design
system in v1.

## Non-goals (v1)

Rule editing/creation/preview, manual categorization, budgets UI, cash-flow
UI, XLS parsing, downloads, iCloud sync, widgets, charts, auth, App Store
distribution (personal signing/sideload only).

## Verification

- `DVMFinanceKit` is UI-free; XCTest suites port the relevant Python test
  cases (normalization, ids, dedup, rule matching incl. tag-only pass,
  snapshot round-trip, each parser against fixture files).
- Golden fixtures: a small snapshot `.json.gz` and statement files are
  generated **by the Python code** and checked into
  `ios/DVMFinanceKit/Tests/Fixtures/` so parity is tested against desktop
  output, not against the port's own assumptions.
- No Swift toolchain exists in the Linux dev container; the build gate is
  `xcodegen generate && xcodebuild test` on the user's Mac (documented in
  `ios/README.md`).
