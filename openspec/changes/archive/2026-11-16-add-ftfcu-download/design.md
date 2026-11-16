# Design

## Context

A capture of the First Tech web site (2026-11-16) gave these facts:

- The export is one multipart `POST /MyAccountsV2/Export`. The form
  `#export_form` on the account overview holds the anti-forgery token and one
  GUID for each account. The page script adds the form after the load.
- `format=56` gives OFX for all the accounts in one file. `format=54` (CSV)
  accepts one account only, and its rows hold no account number.
  `format=58` (QFX) gives other transaction identifiers than OFX.
- The bank refuses transactions older than two years.
- The login page has a Cloudflare Turnstile check. The check did not complete
  while Playwright was attached with init scripts. It completed with no client
  attached. An attach after the login caused no problem.

## Decisions

### OFX, not CSV

One OFX request covers all the accounts, and the file names each account. A CSV
download needs one request for each account, and the job must supply the
account. The user chose OFX only.

### `ofxtools` for the parse

`ofxtools` and `ofxparse` both read the real files correctly. `ofxtools` is
maintained, and it has no runtime dependency. Its licence is GPL-3.0-only. The
user chose `ofxtools`.

### Exact decimals

`ofxtools` gives each amount as a `Decimal`. The OFX decimal separator is always
a period. The parser does not use the number parser of SEB, which changes a
comma to a period. The conversion divides the `Decimal` by the rate and rounds
one time, to 2 places, half up.

### Dates in UTC

`ofxtools` gives each date as a UTC datetime. A date without a time becomes UTC
midnight. The parser takes the UTC date. A conversion to the Pacific time zone
would move a date without a time back by one day.

### Account and identity

The account is `ftfcu:<last 4 digits>`. The `ACCTID` of the card is the card
number, so the parser never stores the full value. The FITID holds spaces and
commas (`20261113 100002 1,049 7,693`), and the transaction id goes into URL
paths. The id therefore uses the FITID without commas, with `-` between the
parts. The amount part is always grouped cents, so the change cannot make two
FITIDs equal. The raw FITID stays in the structured description and in
`transaction_reference`.

### Login first, then attach

The job reads `/json/list` over plain HTTP. If no First Tech tab exists, it
opens one with `PUT /json/new`, which does not attach a client. The job polls
`/json/list` until a tab shows `/MyAccountsV2`. Only then does it attach with
`connect_over_cdp`. It sends the export with `context.request`, which carries
the session cookies. It detaches at the end, and it keeps the tab of the user.

### PayPal: funding row first, then the ECB rate

A PayPal payment in another currency can have a linked EUR funding row. That
row holds the EUR amount that PayPal took from the bank, and the bank statement
shows the same amount. The parser keeps that amount. A payment with no funding
row, for example a subscription paid from a USD balance, gets the ECB rate, as
for SEB. The parser fetches rates only when such a payment exists. The field
`eur_conversion` records `paypal_funding` or `ecb_reference_rate`.

Before this change, the parser stored each bank deposit as EUR, also when the
report gave another currency. A deposit from a USD bank account of 9.99 USD
therefore read 9.99 EUR. A deposit in another currency now gets the ECB rate.

An import skips a transaction whose id the database already holds. A PayPal
row that an earlier import stored in USD therefore stays in USD after a new
import of the same report.

### Original amount in the table

The parsers keep the original amount in the structured description, with two
spellings: `native_amount`/`native_currency` (SEB, Wise, First Tech) and
`original_amount`/`original_currency` (PayPal). One helper reads both. Wise
keeps the amount without a sign, so the sign comes from the stored amount. The
table shows the value only when the original currency differs from the stored
currency.

## Risks

- First Tech can change the form or the export. The protocol notes hold the
  selectors of the UI steps as a fallback.
- Another download job can attach to Chrome during the First Tech login. The
  card on the download page tells the user to complete the First Tech login
  first. This case is not tested.
- The token and the account GUIDs come from the page on each run. The capture
  did not show whether the GUIDs change between sessions.
