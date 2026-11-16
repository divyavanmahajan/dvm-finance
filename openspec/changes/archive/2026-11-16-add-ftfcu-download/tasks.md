# Tasks

## 1. Rates

- [x] 1.1 Move the ECB rate code from `parsers/seb.py` to `parsers/fx.py` with
  the currency as a parameter. Keep the SEB helper names as wrappers. Verify
  that the SEB tests pass, and add offline tests for the currency selection and
  the lookup order.

## 2. Parser

- [x] 2.1 Add `parsers/ftfcu.py` with `ofxtools`. Verify with a synthetic
  fixture: a credit line in the bank message set, an account with no
  transactions, a FITID with spaces and commas, a memo line at column 0, and a
  date with and without a time zone.
- [x] 2.2 Assert the exact native amounts and the EUR amounts with fixed rates.
  Assert that no full account number is stored.
- [x] 2.3 Refuse a QFX file, an OFX file of another bank, and a file that is
  not OFX.
- [x] 2.4 Add the `ftfcu` format to the importer, the upload API, and the
  upload page. Add the `ftfcu_fitid` branch to the transaction identity.
- [x] 2.5 Parse the three real downloads locally. Do not commit them.

## 3. Download

- [x] 3.1 Add `downloaders/ftfcu.py`. Unit-test the date clamp, the multipart
  body, the record count, and the login wait without an attach.
- [x] 3.2 Add the start route, the status source, and the card on the download
  page. Test the 400 response for a malformed date and the 409 response.
- [x] 3.3 Run one live download into a scratch data folder.

## 4. Original amount

- [x] 4.1 Show the original amount before the euro amount in the table, and the
  original amount and the rate in the detail view. Test each parser spelling.
- [x] 4.2 Check the result with a real OFX file.

## 5. PayPal

- [x] 5.1 Convert a PayPal payment with no EUR funding row with the ECB rate.
  Move the exact rounding to `fx.to_eur`. Test a small and a large USD amount,
  the case without rates, and a funded payment that fetches no rate.

## 6. Docs

- [x] 6.1 Update `docs/product.md` and `docs/architecture.md`.
- [x] 6.2 Sync the deltas into `openspec/specs/` and archive the change after
  the merge.
