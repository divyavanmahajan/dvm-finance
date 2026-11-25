# Product

`dvm-finance` is one local web app that downloads, categorizes, and shows bank statements. It is distributed on PyPI as `dvm-finance` and runs via `uvx dvm-finance`.

## Goals

- Download (ABN AMRO, PayPal, Wise, SEB, First Tech Federal Credit Union) and upload (MT940/XLS/CSV/PayPal/Wise/SEB/First Tech OFX) statements from the web UI; auto-import with dedup and rule application.
- The First Tech download gets one OFX file for all accounts. Log in to First Tech in the debug Chrome when the job asks. The job attaches to Chrome only after the login, because the Cloudflare check on the login page fails while an automation client is attached. The bank gives at most two years of history.
- The SEB and First Tech parsers convert each amount to the euro with the ECB reference rates. If the app cannot get the ECB rates, the import refuses the SEB or First Tech file and stores no transaction. The upload and the download job then show the message "The ECB exchange rates are not available. The import stored no transaction. Try again later." The app never stores an SEB or a First Tech amount in krona or in US dollars. The PayPal parser uses the EUR funding row of a foreign-currency payment, and the ECB rate when no funding row exists. The transactions table shows the original amount and currency before the euro amount of each converted transaction (SEB, Wise, PayPal, First Tech). The detail view also shows the rate.
- Rule-based categorization with conditions, priorities, tags; fast "create rule from transaction"; preview before saving; stored change reports after every rule change.
- Two main tabs: **Transactions** (redesigned simple filter bar, URL-encoded filters; include and **exclude** category filters with subtree semantics; **transfer exclusion by default**) and **Category Trends** (table with cell/row click-through to filtered transactions). Plus Rules, Tags, Budgets, Cash Flow, Download/Upload, Snapshots.
- **Transfer exclusion**: Transfers (inter-account movements) excluded from all views by default to focus financial reporting on actual spending. Toggles on Transactions, Trends, and Cash Flow pages allow opting-in per-session.
- Budgets per category on **Monthly** and **Yearly** tabs, with budget-vs-actual. A budget repeats, and the **Create budgets** page proposes the recent average from a selected month or year (see [Budgets](#budgets)).
- Share data with one other person via export/import snapshots (incoming wins).
- One-time migration from the legacy `abn_analyst.db`.
- **Cash transactions** on the **Cash** tab (`/manual`): record a payment that no statement reports. The app holds each hand-entered transaction in the reserved pseudo account `CASH`.
- **The browser opens at the start.** The command `dvm-finance` waits for the
  app to answer, and then it opens the default browser at the address. Pass
  `--no-browser`, or set `DVM_FINANCE_NO_BROWSER`, to stop it.
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

## Rule editor

The rule editor has a **Match** card on the left and an **Assign** card on the
right.

### The field list

When you create a rule from a transaction, that transaction is the sample. The
Match card shows one row for each field of the sample. The merchant name, the
name, the counterparty, and the IBAN come first. The other structured fields
follow. The description is the last row. The list omits an empty field.

Each row has a checkbox, the field name, a pattern, and a value. The value
starts as the value of the sample. You can edit it, for example to make it
shorter.

- The first selected row is the main match of the rule.
- Each other selected row is an `AND` condition. The transaction must also
  match it.
- When the editor opens, it selects one row: the merchant name, the name, the
  counterparty, the IBAN, or the description, in that order. It also selects
  the account filter.

If you select no row, the editor shows "Select at least one field." The
editor does not save the rule until you select a row.

### Context filters

The account, the currency, the start date, and the end date are rows below the
fields. The rule uses a filter only when you select its row. The account and
the currency start with the values of the sample.

### Advanced conditions

Use the advanced conditions for `OR` logic, or for a field that the sample does
not hold. The main match must always match. The rule checks the other
conditions from top to bottom. An `OR` row passes when the conditions above it
pass, or when the `OR` row itself matches.

### Use as sample

"Edit rule" opens the rule as it is saved, with no field list. To see the
fields of a transaction, click **Preview matches**. Then click **Use as
sample** on a row of the preview. The Match card shows the fields of that
transaction, and the preview runs again. The editor keeps your other edits.
The main match and the leading `AND` conditions of the rule become selected
rows, with their own pattern and value.

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

## The duplicate transactions

The bank writes one SEPA payment in either of two description forms. One form
uses slash tags. The other form uses Dutch labels. The two forms hold a
different raw text, so each form gives a different transaction id. A database
from before the end-to-end reference check can therefore hold one payment twice.

The import now joins the two forms by the end-to-end reference of the payment.
The **Duplicates** page folds each pair that the database already holds. The
utility menu of the navigation bar holds the link, beside **Snapshots**.

### Merge the duplicate transactions

1. Open the utility menu, then select **Duplicates** (`GET /merge`). The page
   names each group, and it changes no row.
2. Check each group. The page names the row that stays and each row that the
   merge flags.
3. Select the confirmation, then select **Merge now**.

The merge keeps the row with the lowest id. The choice is the same on each
machine, so a snapshot merges without a heuristic. The merge carries the manual
category and the manual tags of a folded row to the row that stays, when that
row holds none. No manual categorization goes away.

The merge flags each folded row, and it names the row that stays. The merge
deletes no row. Each list and each total therefore holds the payment one time.

### A transfer between two of your own accounts

Such a transfer carries no reference. The bank writes `NOTPROVIDED`, which names
no single payment. The system therefore joins the two description forms of such
a transfer by the counterparty: the account, the date, the amount, the IBAN of
the other side, and the description text.

The page names which key found each group, so you can see why the system joined
two rows.

The system refuses a group when one statement file holds more than one of its
rows. Two rows of one file are two payments, and not two forms of one payment.
The page names each refused group with that reason.

### The two kinds of flag

A flag has two sources. The user flags a hand-entered row for removal. The merge
flags an imported row that it folded away. A merged row holds the id of the row
that absorbed it.

The list of the flagged transactions (`GET /manual/flagged`) holds only a row
that the user flagged. The purge deletes only such a row. The purge keeps each
merged row: a delete would free the id of that row, and the next import would
write the duplicate again.

### Undo a merge

The **Duplicates** page names the last merge. Select **Undo** beside a group.
Each folded row of that group appears again in each list and in each total. The
undo keeps each manual categorization that the merge carried.

### A group that the system refuses

The system refuses a group whose rows hold two different manual categories. Only
a snapshot import may replace a manual categorization, so the merge does not
choose between the two values. The page names each refused group. Set the same
category on each row of the group, then run the merge again.

## Budgets

A budget holds a category, an amount, a period (`month` or `year`), and a
validity range. A budget with no **Valid to** repeats in each later period, so
you set a monthly amount once.

The Monthly tab has a month selector, and the Yearly tab has a year selector.
The URL holds the selection (`?period=month&month=2026-11` or
`?period=year&year=2026`). The table sorts on each column, and the default
order is the largest budget first.

One category can have several budgets of one period, but their validity ranges
must not overlap. A validity start is the first day of a month or a year, and a
validity end is the last day.

### Create or override budgets

1. Select the month or the year on the tab.
2. Click **Create budgets**. The page asks for the start month or the start
   year, and it starts with the selection of the tab.
3. Check the proposed amounts. A proposal is the average spend of the last
   three complete months, or 12 times that average for a yearly budget. The
   page lists no proposal for `income` or `transfer`.
4. Select the categories. The page selects each category that has no budget at
   the start. To change an existing budget from the start on, select its row.
5. Click **Create budgets**. An override ends the old budget on the day before
   the start. The earlier periods keep the old amount.

An expired budget stays as history for its own period. It does not repeat.

Update the phone app before you export the first snapshot that holds two
budgets for one category. An older phone app cannot import such a snapshot.

## Amount correction on import

A PayPal or a Wise transaction keeps its id when its amount changes, because
the id holds the transaction number of the provider and not the amount. An SEB
transaction keeps its id when its euro amount changes. Its id holds the voucher
number, the booking date, the krona amount, and the krona balance, but not the
euro amount. If a parser stored a wrong amount, a new import of the same file
corrects it.

When an imported row has the id of a stored transaction and a different amount,
the import replaces the stored amount. The import keeps each other field, for
example a manual category and manual tags. The import does not change a flagged
transaction.

The import does not replace a stored amount when the incoming currency is not
the stored currency. The import counts that row as a duplicate. A file without
the ECB rates therefore cannot write a krona amount over a euro amount.

The upload summary shows the count of the corrected amounts. It also shows a
table with the id, the old amount, and the new amount of each corrected
transaction. The automatic import after a download corrects the amounts in the
same way.

The PayPal parser reads the amount in the European form (`-9,99`) and in the
English form (`-9.99`). The last period or comma is the decimal separator when
one or two digits follow it.

After an import corrects an amount, export a snapshot and import it on the
phone first. A snapshot from the phone that still holds the old amount puts the
old amount back, because the incoming values win.

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
