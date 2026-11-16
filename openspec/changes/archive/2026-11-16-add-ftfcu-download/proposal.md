# Proposal

## Why

The user has accounts at First Tech Federal Credit Union (First Tech) in the
United States. The app cannot read the statements of that bank, and it cannot
download them. The amounts are in US dollars, and the reports of the app use the
euro. The user must download the First Tech transactions and see them in euro,
with the dollar amount beside each euro amount.

## What Changes

- A new parser reads the OFX file that First Tech exports. One file holds all
  the accounts of the user, including the credit card. The parser uses the
  `ofxtools` package from PyPI.
- The parser converts each dollar amount to the euro with the reference rates
  of the European Central Bank (ECB), as the SEB parser does for the krona. The
  rate code of the SEB parser moves to a shared module. The SEB behavior does
  not change.
- The PayPal parser converts a payment in another currency with no EUR funding
  row to the euro with the same ECB rates. Before this change, such a payment
  stayed in its own currency. A payment with a funding row keeps the EUR amount
  that PayPal took from the bank.
- The parser refuses a QFX file from First Tech. The QFX file gives the same
  transactions other identifiers, so a QFX import would add duplicates.
- The account of a First Tech transaction is `ftfcu:` and the last 4 digits of
  the account number. The full card number is never stored.
- A new download job gets the OFX file for a date range. The job does not
  attach to Chrome before the user logs in, because the Cloudflare check on the
  login page fails while an automation client is attached.
- The transactions table shows the original amount and currency before the euro
  amount of each converted transaction. The detail view shows the original
  amount and the rate. This applies to SEB, Wise, PayPal, and First Tech rows.
- The upload page offers the First Tech format.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `statement-parsers`: the First Tech OFX format, its explicit selection, its
  identifier, and its conversion to the euro. The ECB conversion of a PayPal
  payment with no funding row.
- `statement-download`: the First Tech download job, its login order, and its
  date limit.
- `transaction-dedup`: the First Tech identifier in the transaction identity.
- `transaction-browsing`: the original amount before the euro amount.

## Impact

- New dependency: `ofxtools` (licence GPL-3.0-only). The app has the MIT
  licence. The user accepted this dependency.
- New modules: `parsers/fx.py`, `parsers/ftfcu.py`, `downloaders/ftfcu.py`.
- The iOS app has its own port of each parser. It cannot import a First Tech
  file until it gets a matching parser. That work is a separate change.
- Protocol notes: `protocol/firsttechfed.com-protocol.md` (local file, not in
  the repository).
