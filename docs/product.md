# Product

`dvm-finance` merges abn-download (statement downloaders) and abn-analyst (categorizer/viewer) into one local web app, distributed on PyPI as `dvm-finance` and run via `uvx dvm-finance`.

## Goals

- Download (ABN AMRO, PayPal) and upload (MT940/XLS/CSV/PayPal/Wise/SEB) statements from the web UI; auto-import with dedup and rule application.
- Rule-based categorization with conditions, priorities, tags; fast "create rule from transaction"; preview before saving; stored change reports after every rule change.
- Two main tabs: **Transactions** (redesigned simple filter bar, URL-encoded filters; include and **exclude** category filters with subtree semantics; **transfer exclusion by default**) and **Category Trends** (table with cell/row click-through to filtered transactions). Plus Rules, Tags, Budgets, Cash Flow, Download/Upload, Snapshots.
- **Transfer exclusion**: Transfers (inter-account movements) excluded from all views by default to focus financial reporting on actual spending. Toggles on Transactions, Trends, and Cash Flow pages allow opting-in per-session.
- Budgets per category on **Monthly** and **Yearly** tabs, with budget-vs-actual and one-click "seed from average" (annualized on the Yearly tab).
- Share data with one other person via export/import snapshots (incoming wins).
- One-time migration from the legacy `abn_analyst.db`.
- **Cash transactions** on the **Cash** tab (`/manual`): record a payment that no statement reports. The app holds each hand-entered transaction in the reserved pseudo account `CASH`.
- **The browser opens at the start.** The command `dvm-finance` waits for the
  app to answer, and then it opens the default browser at the address. Pass
  `--no-browser`, or set `ABN_COMBINED_NO_BROWSER`, to stop it.
- In-app **Help** page (`/help`) rendering the Markdown user guide plus an iOS companion-app section.
- **iOS/iPadOS companion app** (`ios/`): review transactions, trends and budgets on the go and sync via snapshots. See [`ios/README.md`](../ios/README.md).

Removed on purpose: graphs, LLM categorization, MCP servers, login.

## Key flows

1. Download tab → launch/connect to your Chrome (CDP) → authenticate → statements imported → summary.
2. Filter Uncategorized → create rule from a transaction → preview matches → save → change report.
3. Trends cell click → filtered transaction list for that category/period.
4. Edit rule → preview impact → save → audit history per rule.
5. Export snapshot → partner imports → incoming-wins merge report.
6. Cash tab → add a cash transaction → the row appears in the transactions list and in the cash flow.
7. Cash tab → **The flagged transactions** → restore a row, or confirm the purge.

## Tag-only rules (v1.1.0+)

Normally a rule sets a transaction's **category** (and optionally tags) when it
matches. A **tag-only rule** instead skips the category entirely and only adds
tags — it never changes what category a transaction ends up in.

Tag-only rules are useful for cross-cutting labels that don't map to a single
category, e.g.:

- Tagging every transaction matching `"subscription"` with `recurring`,
  regardless of whether it lands in `entertainment`, `software`, or
  `utilities`.
- Tagging transactions above a certain amount with `large-expense` for later
  filtering, on top of whatever category applies.
- Tagging counterparty-based labels (e.g. `joint-account`) that should follow
  a merchant across multiple spending categories.

### How it works

- Tag-only rules run **after** all category rules have been applied (see
  [architecture.md](architecture.md#rules-categorization-two-pass-v110) for the two-pass
  matching logic).
- They apply **even to manually categorized transactions** — a manual
  category assignment is never touched, but manual transactions can still
  pick up tags from a matching tag-only rule.
- **Every** matching tag-only rule contributes its tags — this is not
  "first match wins" like category rules. If three tag-only rules match a
  transaction, all three rules' tags are added (merged, de-duplicated).
- Tag-only rules never set or clear a transaction's category.

### Creating a tag-only rule in the UI

1. Go to the **Rules** tab; it now has two sub-tabs: **Rules** (category
   rules) and **Tag-only rules**.
2. Click **New rule**, fill in the match conditions as usual, then check
   **"Tag-only rule"**.
3. When checked, the **Category** field is hidden/disabled and the **Tags**
   field becomes required — a tag-only rule must specify at least one tag.
4. Save. The rule now shows up under the **Tag-only rules** sub-tab, with a
   preview and audit history like any other rule.

Tag-only rules go through the same preview-before-save and
`record_rule_change` audit trail as category rules — no silent
recategorization, per the project's hard rules.

## Cash transactions

A statement reports no cash payment. The **Cash** tab (`GET /manual`) gives the
user a form that records such a payment. The app writes each hand-entered
transaction to one reserved pseudo account with the identifier `CASH`. The
account shows beside the bank accounts in the account filter of the transactions
list (`api/transactions.py:_known_accounts`), after the first hand-entered row
exists. That query reads each distinct account and no flag, so the account stays
in the list while a flagged cash row stays in the table.

No parser and no downloader writes a transaction to the account `CASH`. The
import pipeline refuses a batch that holds a transaction for this account, and it
reports the reserved account (`core/dedup.py:reject_reserved_account`). A
snapshot import writes to the account, because this is how the two devices share
the cash rows. The merge applies no reserved-account check of its own.

### Fund the pseudo account with a transfer category

Give the bank withdrawal that funds the cash account a transfer category. The
withdrawal counts as spending in the bank account if you do not. The app then
counts the same money a second time: once in the bank account and once in the
cash rows. The create form repeats this instruction, because nothing reports the
error later.

### Add a cash transaction

1. Open the **Cash** tab.
2. Type the date, the amount, and the description. All three are required.
3. Write a payment as a negative amount.
4. Type an optional category and optional tags.
5. Select **Add the transaction**. The form posts to `POST /manual/create`.

The app refuses a form without a date, without a description, without an amount,
or with an amount of zero. The app names the reason and writes nothing.

The app stores the typed category in `manual_category` and the typed tags in
`manual_tags`. A rule reapplication therefore never replaces them, per the
project rule on manual edits. A tag-only rule still adds a tag to a cash
transaction, exactly as it does to an imported transaction.

### Change a cash transaction

Open `GET /manual/{txn_id}/edit` to change the date, the amount, the
description, the category, or the tags. The form posts to
`POST /manual/{txn_id}/update`. The transaction keeps its id after each edit, so
the next delta snapshot carries the new values to the other device.

The app refuses the edit form and the update for an imported transaction. Only a
hand-entered transaction accepts an edit.

### Flag a cash transaction, and restore it

A removal is a flag. `POST /manual/{txn_id}/flag` records the time of the flag
and keeps the row in the database. `POST /manual/{txn_id}/restore` removes the
flag again. The app refuses both routes for an imported transaction.

A flagged transaction leaves the transactions list, the category trends, the
cash flow, the budget actuals, the tag counts, the rule match counts, and the
rule preview. A restored transaction returns to each of them.

A snapshot export keeps a flagged transaction and the time of its flag, so the
flag reaches the other device. The other device therefore hides the same row.

### Purge the flagged transactions

`GET /manual/flagged` lists each flagged transaction. The user opens the page
from the **The flagged transactions** button on the Cash tab. The page shows the
restore control of each row and the control of the purge.

Caution: check each flagged row on this page before you start the purge. The
purge deletes the rows, and the app cannot undo it.

1. Read each row in the list.
2. Select the confirmation checkbox. The purge deletes nothing without it.
3. Select **Purge now**. The form posts to `POST /manual/purge`.

The purge copies the database to a timestamped backup beside it before it deletes
a row. It deletes each flagged transaction, it deletes no other row, and it
reports the number of the deleted rows.

A purged row can come back from the other device. The row comes back with its
flag, so it stays out of each list and out of each total. The user purges it
again on the device that still holds it.
