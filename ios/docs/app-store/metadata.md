# App Store listing — DVM Finance

Draft copy for the App Store Connect listing. Adjust wording/URLs to taste
before submitting.

## Identity

| Field | Value |
|---|---|
| App name (30 char max) | `DVM Finance` |
| Subtitle (30 char max) | `Private budgets & spending` |
| Bundle ID | `com.dvm.finance` |
| SKU | `dvm-finance-001` |
| Primary category | Finance |
| Secondary category | (optional) Productivity |
| Age rating | 4+ |
| Price | Free (or as desired) |

## Promotional text (170 char max, editable without review)

> Track spending and stay on budget — completely offline. Import your bank
> statements, auto-categorize with your own rules, and watch monthly and
> yearly budgets.

## Description

> DVM Finance is a private, offline personal-finance tracker. Everything stays
> on your device — no account, no cloud, no tracking.
>
> IMPORT YOUR STATEMENTS
> Bring in bank statement exports and let DVM Finance organize them into a
> clean, searchable transaction history.
>
> CATEGORIZE WITH RULES YOU CONTROL
> Build auditable categorization rules and tag-only rules. Manual choices are
> never silently overwritten — you stay in charge of every category.
>
> MONTHLY AND YEARLY BUDGETS
> Set budgets per category on separate Monthly and Yearly tabs, or seed one per
> top-level category from your recent average. See budget-vs-actual at a glance
> and tap through to the exact transactions behind each number.
>
> SEE YOUR TRENDS
> Break down spending over time by category, filter the way you think, and
> follow any figure back to its source transactions.
>
> YOURS, AND PRIVATE
> No sign-in. No analytics. No ads. Your financial data is stored only in a
> local database on your iPhone or iPad, and never leaves the device.

## Keywords (100 char max, comma-separated, no spaces)

```
budget,expenses,spending,finance,money,bank,statement,categorize,offline,private,tracker,savings
```

## URLs

| Field | Value |
|---|---|
| Support URL | (required) e.g. a GitHub repo/issues page or a contact page |
| Marketing URL | (optional) |
| Privacy Policy URL | (required) host `privacy-policy.md` publicly — e.g. GitHub Pages |

## App Privacy questionnaire

- **Data collection:** *Data Not Collected.* The app stores all data locally in
  an on-device SQLite database and transmits nothing. Answer "No" to collection
  for every data-type category.
- **Tracking:** No.

## Screenshots (required)

Generated sets are already checked in (Transactions, Trends, Budgets Monthly,
Budgets Yearly, Import):

- `screenshots/iphone-6.9/` — **1320 × 2868** (iPhone 16 Pro Max) — required
- `screenshots/ipad-13/` — **2064 × 2752** (13" iPad Pro M4) — required (universal app)

Both sets are produced by the `DVMFinanceUITests/ScreenshotTests` UI test, which
launches the app with `-UITestSeed` (loads the demo dataset in
`DVMFinance/SampleData.swift`), walks every tab, and attaches a screenshot at
each stop. To regenerate:

```bash
cd ios
SIM="iPhone 16 Pro Max"   # or: "iPad Pro 13-inch (M4)"
RES=/tmp/shots.xcresult; rm -rf "$RES"
# boot the sim once first (avoids a cold-launch flake), then:
xcodebuild test -project DVMFinance.xcodeproj -scheme DVMFinance \
  -destination "platform=iOS Simulator,name=$SIM" \
  -only-testing:DVMFinanceUITests/ScreenshotTests -resultBundlePath "$RES"
xcrun xcresulttool export attachments --path "$RES" --output-path /tmp/shots_out
# PNGs land in /tmp/shots_out (see manifest.json for the human-readable names)
```

Optional extra sizes you may also upload: iPhone 6.5"/6.7" (1284 × 2778 /
1290 × 2796) — capture by pointing the same test at that simulator.

## What's New (release notes for 1.0.0)

> First release: local transaction tracking, rule-based categorization,
> monthly and yearly budgets, and spending trends — all offline.
