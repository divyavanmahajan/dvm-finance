# Proposal

## Why

The change `unify-sepa-description-and-reference-dedup` joins the two SEPA
description forms of one payment by the end-to-end reference. A transfer between
two accounts of the user carries no reference: the bank writes `NOTPROVIDED`.
The reference check therefore cannot join the two forms of such a transfer.

A real database of 7202 rows shows the size of the gap. It holds 278 pairs of
rows that share an account, a date, and an amount across two statement files.
The reference check joins 46 of them. The other 232 hold no usable reference,
and they represent about 13,000 euro of double counting.

## What Changes

- The duplicate check SHALL add a second key for a transaction that holds no
  usable end-to-end reference. The key is the account, the transaction date, the
  amount, the counterparty IBAN, and the remittance text.
- The system SHALL normalize the IBAN and the remittance text with the same
  rule as the reference.
- The system SHALL refuse a group when one statement file gives more than one
  row of it. Such a group holds a genuine repeated payment, and not two forms of
  one payment.
- The merge SHALL find a group by this key as well, and SHALL report the key
  that matched each group.

## Capabilities

### New Capabilities

None. Each change belongs to a capability that exists.

### Modified Capabilities

- `transaction-dedup`: the duplicate check adds a second key for a transaction
  with no usable reference.
- `transaction-merge`: the discovery finds a group by that key as well, and the
  report names the key that matched.

## Impact

- `src/abn_combined/core/dedup.py`: a second match key beside the reference key.
- `src/abn_combined/core/merge.py`: the discovery, the refusal, and the report.
- `src/abn_combined/web/templates/merge.html`: the page names the key of a
  group.
- The iOS companion mirrors the dedup logic and the merge logic. The change
  needs the same port in `ios/DVMFinanceKit`.
- No schema change. The key reads the stored structured description, which
  already holds the IBAN and the remittance text.
- The transaction ids do not change.
