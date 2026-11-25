# Help & User Guide

DVM Finance is a local, single-user personal-finance app: download or upload
your bank statements, categorize them with auditable rules, and review your
spending in trends and budgets. Everything runs on your own machine — there is
no account, no cloud, and no tracking.

> **Tip:** Your filters live in the page URL, so you can bookmark or share a
> particular view (for example "uncategorized dining in Q1").

---

## Transactions

The **Transactions** tab is your main ledger. Each row shows the date,
description, amount, effective category, and tags.

- **Filter bar** — filter by text, date range, account, amount, and category.
  Category filters understand the hierarchy, so filtering by `food` also
  includes `food:restaurants` and `food:groceries`.
- **Include _and_ exclude categories** — narrow to some categories, or push
  others out of view, with the same subtree semantics.
- **Transfers are hidden by default** — inter-account movements don't count as
  spending, so they're excluded from the list until you toggle them on.
- **Original currency** — a transaction that the app converted to the euro
  (SEB, Wise, PayPal, First Tech) shows the original amount and currency before
  the euro amount. The detail view also shows the exchange rate.
- **Edit a transaction** — open any row to set a manual category, add or remove
  tags, and see how it was categorized. A manual category is never overwritten
  by a later rule run.

---

## Category Trends

The **Trends** tab is a category-by-period table (by month or year). Every
number is a link:

- Click a **cell** to jump to the transactions for that category in that period.
- Click a **row** or **column** total to see the wider slice.

Transfers are excluded by default here too, with a per-session toggle.

---

## Rules

**Rules** categorize transactions automatically and _auditably_ — every change
is previewed before saving and recorded afterward, so nothing is silently
recategorized.

- **Create a rule from a transaction** — the fastest path: open a transaction,
  turn its description or fields into a rule, preview the matches, then save.
- **Conditions & priorities** — combine match conditions (AND/OR) and order
  rules by priority; the first matching category rule wins.
- **Preview before saving** — see exactly which transactions a new or edited
  rule will affect before you commit.
- **Change reports** — every rule create/update/delete/toggle is stored, so you
  have a full audit history per rule.

Manual categorizations always take precedence over rules.

### Tag-only rules

A normal rule sets a transaction's **category**. A **tag-only rule** instead
only adds tags and never touches the category. They:

- run _after_ all category rules,
- apply even to manually categorized transactions (adding tags, never changing
  the category),
- are **not** first-match-wins — every matching tag-only rule contributes its
  tags (merged and de-duplicated).

Use them for cross-cutting labels like `recurring`, `large-expense`, or
`joint-account` that span multiple categories. Create one under **Rules ▸
Tag-only rules**: fill in the match conditions and check **"Tag-only rule"**;
the Category field is hidden and at least one tag becomes required.

---

## Tags

The **Tags** tab lists every tag in use and lets you review and manage the
transactions carrying each one — handy alongside tag-only rules.

---

## Budgets

The **Budgets** tab compares the spend of each category with a target. It has a
**Monthly** tab and a **Yearly** tab.

- **Month or year** — the Monthly tab has a month selector, and the Yearly tab
  has a year selector. The table shows the budgets and the actual spend of the
  selected month or year.
- **A budget repeats** — set a monthly amount once. The budget applies to each
  later month until you end it. To end a budget, edit it and set **Valid to**
  to the last day of a month.
- **Add a budget** — enter a category, an amount, and a start. Leave **Valid
  to** empty, so that the budget repeats. A hint shows the recent average spend
  of the category.
- **Create budgets** — this button is in each tab. It opens a page that asks
  for the start month (Monthly tab) or the start year (Yearly tab). The page
  lists each top-level category with recent spend and proposes the average of
  the last three complete months. On the Yearly tab the proposal is 12 times
  that average. You can change each amount. The page selects each category
  that has no budget at that start.
- **Override from a month** — to change an amount from a given month on,
  select the category on the **Create budgets** page. The old budget ends on
  the day before, and the new amount applies from the selected month. The
  earlier months keep the old amount.
- **Categories without a budget** — the page never proposes a budget for
  `income` or `transfer`.
- **Sort** — click a column header to sort on it. A second click reverses the
  order. The default order is the largest budget first.
- **Status** — each row shows an over / near (80% or more) / under badge.
  Click the category to see the transactions behind the actual spend.

Budget actuals exclude transfers.

---

## Cash Flow

The **Cash Flow** tab summarizes money in versus money out over time, again with
a transfer-exclusion toggle so you're looking at real income and spending.

---

## Cash

The **Cash** tab records a payment that no bank statement reports, for example
a payment in cash. The app keeps each hand-entered transaction in the account
`CASH`.

1. Open the **Cash** tab.
2. Type the date, the amount, and the description. Write a payment as a
   negative amount.
3. Type a category and tags if you want them.
4. Select **Add the transaction**.

Give the bank withdrawal that funds your cash a transfer category. If you do
not, the app counts the same money two times.

To remove a cash transaction, open it and flag it. A flagged transaction leaves
every list and every total. Restore it on the **The flagged transactions** page.

Caution: check each row before you purge the flagged transactions. The app
cannot undo a purge.

---

## Duplicates

Your bank can write one payment in two description forms. A database from an
older version can therefore hold one payment two times. The **Duplicates** page
finds these pairs. Open it from the menu at the right end of the navigation
bar.

1. Open **Duplicates**. The page shows each group and changes nothing.
2. Check each group. The page names the row that stays.
3. Select the confirmation, then select **Merge now**.

The merge keeps your manual categories and tags. It flags each extra row and
deletes nothing. Select **Undo** beside a group to bring its rows back. The
page refuses a group whose rows have two different manual categories. Give the
rows the same category, then merge again.

---

## Getting statements in

### Download

The **Download** tab gets statements directly from **ABN AMRO**, **PayPal**,
**Wise**, **SEB**, and **First Tech**. ABN AMRO opens its own browser. For the
other banks, start Chrome with remote debugging, as the page shows. Log in to
the bank in the browser when the job asks. The app then imports the statements
with dedup and rule application, and shows a summary.

### Upload

The **Upload** tab imports statement files you already have. Supported formats:
**MT940**, **XLS/XLSX**, **CSV**, **PayPal**, **Wise**, **SEB**, and **First
Tech OFX**. Files are de-duplicated on import, so re-uploading an overlapping
export won't create double entries.

### Amounts in another currency

The app converts SEB and First Tech amounts to the euro with the ECB reference
rates. If the app cannot get the rates, it refuses the file and stores no
transaction. The message says "The ECB exchange rates are not available."
Try the import again later.

SEB can give one voucher number to many card payments. The app stores each of
these payments as its own transaction.

---

## Snapshots — sharing & backup

A **snapshot** is a compressed (`.json.gz`) copy of your data. Snapshots let you
back up, move between machines, or share with one other person.

- **Export snapshot** — writes a full snapshot and downloads it.
- **Export delta snapshot** — writes a smaller snapshot containing only the
  transactions changed since a date you choose. Ideal for pushing a small set of
  edits without moving everything.
- **Share to phone** — shows a QR code. Scan it in the iOS app to get a
  snapshot over your own Wi-Fi network. The QR code works for one download
  only and expires after 10 minutes.
- **Import snapshot** — merges a snapshot in. The merge is **incoming-wins**:
  values from the imported file overwrite the local ones, your database is
  backed up first, and you get a merge report. Every import is recorded.

Snapshots are also how the **iOS companion app** syncs — see the next section.
