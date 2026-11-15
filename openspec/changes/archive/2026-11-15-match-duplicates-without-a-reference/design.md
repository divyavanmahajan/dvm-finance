# Design

## Context

See proposal.md for the motivation. See the spec deltas for the requirements.

The change `unify-sepa-description-and-reference-dedup` added
`end_to_end_reference` and the reference key. `core/dedup.py:_reference_key`
builds that key, and `core/merge.py:preview_merge` groups the stored rows by it.

The numbers below come from a real database of 7202 rows, after that change ran.

## Goals / Non-Goals

**Goals:**

- Join the two description forms of a transfer that carries no reference.
- Refuse a group that holds a genuine repeated payment.

**Non-Goals:**

- No change to the transaction id, and no schema change.
- No match across two accounts of the user. Each side of an internal transfer is
  its own transaction of its own account, and both sides must stay.
- No match of a point-of-sale row. Such a row holds no counterparty IBAN.

## Decisions

### The key holds the remittance text

Without the remittance text the key joins rows that are two payments. The real
database holds three payments of -149,00 euro of one day to one PayPal IBAN.
Only their remittance texts differ: `1881164974955/PAYPAL`,
`3404065959685/PAYPAL`, and `7624611028858/PAYPAL`. A key without the remittance
text folds two of them away, and 298 euro goes missing.

The same database holds three transfers of 120,00 euro of one day between two
accounts of the user, with the remittance texts `BIQTVW BIRTHDAY`, `BIQTVW`, and
none.

### The key allows an empty remittance text

189 of the 214 groups hold no remittance text on either row, because an internal
transfer often carries none. A key that needs a remittance text therefore finds
25 groups instead of 214, and it misses the whole purpose of the change.

The rule of the statement file below carries the safety instead.

### One row of each statement file

Two rows of one payment always come from two statement files. The bank answered
one download with the tagged form and a later download with the labelled form.
Two rows of one file are two payments.

This rule separates the two cases in the real database exactly:

- Each of the 214 groups holds one row of each of two files. The merge folds
  them.
- Each of the five clusters of a genuine repeated payment holds two rows or more
  of one file. The merge refuses them.

Alternative: trust the remittance text alone. Rejected. Two identical transfers
of one day with no remittance text would merge, and the user would lose one.

Alternative: allow a group of two rows only. Rejected. It refuses a payment that
three downloads report, and it does not refuse two equal payments that two
downloads each report.

### Refuse, and do not guess

A refused group appears in the report with its reason. The user decides. The
merge must not choose which row of a genuine pair to keep.

## Risks / Trade-offs

- [Two equal payments of one day that two downloads both report] → The group
  then holds two rows of each file, so the rule refuses it. The user sees the
  group in the report.
- [One payment that two downloads report, and the bank changed the remittance
  text between them] → The key misses the pair, and the user keeps two rows. The
  change finds fewer duplicates than exist; it creates none.
- [A creditor that reuses one remittance text for a daily payment of one amount]
  → Two such payments of one day from two downloads would merge. The report
  names each merged group, and the undo restores it.

## Migration Plan

No migration. The key reads the stored structured description, which already
holds the IBAN and the remittance text. The one-time pass of the earlier change
already rewrote each stored SEPA description.
