# DVM Finance — iOS

A standalone native iOS/iPadOS companion to `abn-combined` (dvm-finance):
SwiftUI + local SQLite via GRDB, fully offline. See
[`docs/spec.md`](docs/spec.md) for the product spec and
[`docs/plan.md`](docs/plan.md) for the phased implementation plan.

The desktop Python app stays the primary tool; this app is a review-first
viewer with statement file import and snapshot sync. The two apps never
share a database file directly — they interoperate exclusively through the
gzipped-JSON snapshot format also used for desktop-to-desktop sharing.

## Prerequisites

- macOS with Xcode 15 or later (iOS 17 SDK).
- [XcodeGen](https://github.com/yonaskolb/XcodeGen): `brew install xcodegen`.
- A free or paid Apple Developer account for personal code signing (no App
  Store distribution in v1 — sideload/personal-team only).

## Generate and open the project

```bash
cd ios
xcodegen generate
open DVMFinance.xcodeproj
```

`DVMFinance.xcodeproj` is generated from `project.yml` and is **not**
committed to source control (see `.gitignore`) — re-run `xcodegen generate`
any time `project.yml` changes, or after pulling changes that touch it.

The project has one Xcode target, `DVMFinance` (iPhone + iPad, iOS 17.0
deployment target), which depends on the local Swift package
`DVMFinanceKit` (`DVMFinanceKit/Package.swift`). All business logic —
database access, normalization, dedup, the rule engine, the snapshot codec,
statement parsers, filters/trends — lives in `DVMFinanceKit` and is covered
by the package's own `DVMFinanceKitTests` target. The app target itself
holds only SwiftUI views and app wiring.

## Signing for your personal team

1. Open `DVMFinance.xcodeproj` in Xcode.
2. Select the `DVMFinance` target → **Signing & Capabilities**.
3. Set **Team** to your personal Apple ID team (Automatic signing is
   already configured in `project.yml`).
4. Xcode will assign a unique bundle identifier suffix automatically if
   `com.dvm.finance` collides with another provisioning profile on your
   account; adjust `PRODUCT_BUNDLE_IDENTIFIER` in `project.yml` and
   regenerate if you need a different one.

## Running on a device

1. Connect your iPhone/iPad and select it as the run destination in Xcode's
   scheme toolbar.
2. Build & run (`Cmd-R`). The first run on a new device requires trusting
   the developer certificate on-device: **Settings → General → VPN & Device
   Management**.
3. Data lives in the app's Application Support directory
   (`dvm_finance.sqlite`), private to the app sandbox. There is no iCloud
   sync in v1 — moving data between devices or to/from the desktop app is
   done by exporting a snapshot (`.json.gz`) from one and importing it into
   the other (Import tab, once Phase C/E land).

## Running tests

`DVMFinanceKit` is UI-free and covered by `XCTest`. Two equivalent ways to
run its test suite:

```bash
xcodebuild test -scheme DVMFinance \
  -destination 'platform=iOS Simulator,name=iPhone 15'
```

— or, in Xcode, open the scheme picker and select the `DVMFinanceKit`
package scheme (Xcode creates one automatically once the local package
dependency is resolved), then `Cmd-U`.

There is no separate unit-test Xcode target in `project.yml` for the Kit —
the package's own `DVMFinanceKitTests` target (declared in
`DVMFinanceKit/Package.swift`) is the single source of truth for its tests,
reached through Xcode's native Swift package test integration either way.

No Swift toolchain exists in the Linux container this project was
scaffolded in, so `xcodegen generate && xcodebuild test` on a Mac is the
actual build/test gate for every change under `ios/`.

## Backlog (post-v1 candidates)

Tracked here per `ios/docs/plan.md` "Phase F"; not in scope until a v1.1
decision:

- XLS statement import (needs a pure-Swift XLS reader, e.g. CoreXLSX).
- Budgets UI (schema is ported in v1; no screens).
- Cash-flow UI.
- Rule editing/creation/preview (v1 rules arrive read-only via snapshot
  import).
- Manual categorization from the iOS app.
- iCloud sync, widgets, charts, authentication, App Store distribution.
