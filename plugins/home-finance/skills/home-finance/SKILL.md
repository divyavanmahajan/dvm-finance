---
name: home-finance
description: Analyze the household finances that the dvm-finance app holds. Use it to look at transactions, spend per category, trends over months or years, budgets against actual spend, income against expense (cash flow), uncategorized transactions, and recurring payments, and to give advice on how to manage the home finances. Use it when the user asks about their spending, savings, budgets, bills, subscriptions, or bank statements in dvm-finance (also called abn-combined).
---

# Home finance analysis with dvm-finance

dvm-finance is a local, single-user finance app. It imports bank statements,
categorizes the transactions with rules, and shows trends, budgets, and the
cash flow. All the data is in one SQLite database on the computer of the user.

Use this skill to answer questions about the finances of the user and to give
advice. Read the data from the database. Make each change through the app.

## Safety rules

- Open the database **read-only**. Use `sqlite3 -readonly` or the URI
  `file:<path>?mode=ro`. Do not write to the database.
- Do not change a rule, a category, a tag, or a budget with SQL. The app
  records each rule change in an audit trail, and a direct write breaks it.
  Make each change in the web UI, or with the HTTP form endpoints in
  [Changes through the app](#changes-through-the-app).
- The data is private financial data. Do not send it to a web service. Do not
  put it in a commit, an issue, a test, or a file outside the data folder,
  unless the user asks for it.
- Show amounts with two decimals and the currency. Most amounts are in EUR.

## Find the database

The database file is `abn_combined.db` in the data folder. Find the data folder
in this order:

1. The `--data-dir` value that the user gives.
2. The environment variable `DVM_FINANCE_DATA_DIR`.
3. The platform default:

| Platform | Data folder |
|---|---|
| macOS | `~/Library/Application Support/abn-combined` |
| Linux | `~/.local/share/abn-combined` |
| Windows | `%LOCALAPPDATA%\abn-combined` |

Make sure that the file exists before you continue:

```bash
DB="$HOME/Library/Application Support/abn-combined/abn_combined.db"   # macOS
sqlite3 -readonly "$DB" "select count(*), min(transactiondate), max(transactiondate) from transactions;"
```

If `sqlite3` is not available, use Python:

```bash
python3 -c "import sqlite3,sys; c=sqlite3.connect(f'file:{sys.argv[1]}?mode=ro', uri=True); print(c.execute(sys.argv[2]).fetchall())" "$DB" "select count(*) from transactions"
```

The app can run at the same time. A read-only query does not block it.

## The data model

### Table `transactions`

| Column | Meaning |
|---|---|
| `id` | The transaction id. The import derives it from the content. |
| `accountNumber` | The account. ABN AMRO accounts are numbers. Other sources use a prefix: `seb:`, `wise`, `pp:` (PayPal), `ftfcu`, and `CASH` for the transactions that the user typed by hand. |
| `transactiondate` | The booking date (`YYYY-MM-DD`). |
| `amount` | The signed amount. A negative value is money out. A positive value is money in. |
| `currency` | The stored currency, usually `EUR`. |
| `description` | The text from the bank statement. |
| `description_structured` | JSON. It holds the parsed fields, for example the counterparty name, the IBAN, and the native amount of a converted transaction (`native_amount`, `native_currency`, `eur_rate_used`). |
| `category` | The category from the rules. |
| `manual_category` | The category that the user set by hand. It has priority over `category`. |
| `tags`, `manual_tags` | The tags from the rules and from the user. Each value is a comma-separated list. |
| `categorization_source` | The id of the rule that set the category, or `manual`. |
| `is_manual` | 1 for a transaction that the user typed by hand. |
| `deleted_at` | Not NULL when the user flagged the transaction for removal. |
| `merged_into` | Not NULL when a merge folded this row into another row. |

### Other tables

| Table | Contents |
|---|---|
| `budgets` | `category`, `amount` (positive), `period` (`month`, `year`, or `week`), `start_date`, `end_date` (validity, NULL means open). |
| `categorization_rules` | The rules: `priority`, `rule_type`, `match_pattern`, `field_target`, `match_value`, `category`, `tags`, `is_active`, `is_tag_only`. |
| `rule_conditions` | The extra conditions of a rule, with `operator` `AND` or `OR`. |
| `rule_change_reports`, `rule_change_items` | The audit trail of each rule change and each transaction that it changed. |
| `download_state` | The date of the last successful download of each source. |

## The calculation rules of the app

Use the same rules as the app, so that your numbers agree with the screens.

1. **Live rows only.** Always add `deleted_at IS NULL`. A merged row also has
   `deleted_at`, so the same condition removes it.
2. **The effective category** is
   `COALESCE(NULLIF(manual_category, ''), category)`. A NULL or empty value
   means "uncategorized".
3. **The effective tags** are `COALESCE(NULLIF(manual_tags, ''), tags)`.
4. **The category hierarchy** uses a hyphen. The top-level segment is the
   parent: `groceries-ah` is a child of `groceries`. A filter on `food` also
   includes `food-restaurants`:
   `lower(cat) = 'food' OR lower(cat) LIKE 'food-%'`.
5. **Transfers.** A category that contains `transfer` is a transfer between
   accounts of the user. The cash flow and the budgets exclude these
   transactions by default. The trends also exclude them by default.
6. **Sample data.** The id of a sample transaction starts with `sample-`.
   Exclude these rows unless the user asks about the sample data.

Put this common filter in each query:

```sql
WITH t AS (
  SELECT *,
         COALESCE(NULLIF(manual_category, ''), category) AS cat,
         COALESCE(NULLIF(manual_tags, ''), tags)         AS tagset
  FROM transactions
  WHERE deleted_at IS NULL
    AND id NOT LIKE 'sample-%'
)
```

## Queries

Each query below starts with the `WITH t AS (...)` block above. Change the dates
to fit the question.

### Data coverage per account

Run this query first. It shows the period that each account covers. A gap
means a missing statement, and a total for that period is then too low.

```sql
SELECT accountNumber, count(*) AS n,
       min(transactiondate) AS first, max(transactiondate) AS last
FROM t GROUP BY accountNumber ORDER BY last DESC;
```

### Spend per top-level category in a period

```sql
SELECT CASE WHEN cat IS NULL THEN '(uncategorized)'
            WHEN instr(cat, '-') > 0 THEN substr(cat, 1, instr(cat, '-') - 1)
            ELSE cat END AS parent,
       round(sum(-amount), 2) AS spend, count(*) AS n
FROM t
WHERE transactiondate BETWEEN '2026-01-01' AND '2026-12-31'
  AND amount < 0
  AND (cat IS NULL OR cat NOT LIKE '%transfer%')
GROUP BY parent ORDER BY spend DESC;
```

### Monthly trend of one category

```sql
SELECT substr(transactiondate, 1, 7) AS month, round(sum(amount), 2) AS net, count(*) AS n
FROM t
WHERE (lower(cat) = 'groceries' OR lower(cat) LIKE 'groceries-%')
  AND transactiondate >= date('now', 'start of month', '-12 months')
GROUP BY month ORDER BY month;
```

### Cash flow per month (income, expense, net)

This query gives the same numbers as the Cash flow page.

```sql
SELECT substr(transactiondate, 1, 7) AS month,
       round(sum(CASE WHEN amount > 0 THEN amount ELSE 0 END), 2)  AS income,
       round(sum(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 2) AS expense,
       round(sum(amount), 2) AS net
FROM t
WHERE (cat IS NULL OR cat NOT LIKE '%transfer%')
  AND transactiondate >= date('now', 'start of month', '-12 months')
GROUP BY month ORDER BY month;
```

The savings rate of a period is `net / income`.

### Budget against actual spend in the current period

The actual spend is the sum of `abs(amount)` for the budget category and its
children, without transfers, in the current month, year, or week. Only a budget
whose validity covers today counts.

```sql
WITH t AS (
  SELECT *, COALESCE(NULLIF(manual_category, ''), category) AS cat
  FROM transactions WHERE deleted_at IS NULL AND id NOT LIKE 'sample-%'
),
b AS (
  SELECT id, category, amount, period,
         CASE period WHEN 'month' THEN date('now', 'start of month')
                     WHEN 'year'  THEN date('now', 'start of year')
                     ELSE date('now', 'weekday 0', '-6 days') END AS p_start,
         CASE period WHEN 'month' THEN date('now', 'start of month', '+1 month', '-1 day')
                     WHEN 'year'  THEN date('now', 'start of year', '+1 year', '-1 day')
                     ELSE date('now', 'weekday 0') END AS p_end
  FROM budgets
  WHERE (start_date IS NULL OR start_date <= date('now'))
    AND (end_date IS NULL OR end_date >= date('now'))
)
SELECT b.category, b.period, b.amount AS budget,
       round(coalesce(sum(abs(t.amount)), 0), 2) AS actual,
       round(b.amount - coalesce(sum(abs(t.amount)), 0), 2) AS remaining
FROM b LEFT JOIN t
  ON (lower(t.cat) = lower(b.category) OR lower(t.cat) LIKE lower(b.category) || '-%')
 AND t.cat NOT LIKE '%transfer%'
 AND t.transactiondate BETWEEN b.p_start AND b.p_end
GROUP BY b.id ORDER BY remaining;
```

For a month budget, compare the actual spend with the part of the month that is
over. On day 15 of a 30-day month, a spend of 50% is on plan.

### Average monthly spend of a category

The app proposes a budget from the average of the last complete months. Use the
last 6 complete months, and do not include the current month.

```sql
SELECT round(sum(abs(amount)) / 6.0, 2) AS avg_month
FROM t
WHERE (lower(cat) = 'groceries' OR lower(cat) LIKE 'groceries-%')
  AND cat NOT LIKE '%transfer%'
  AND transactiondate >= date('now', 'start of month', '-6 months')
  AND transactiondate <  date('now', 'start of month');
```

### Uncategorized transactions

```sql
SELECT description, count(*) AS n, round(sum(amount), 2) AS total
FROM t WHERE cat IS NULL
GROUP BY description ORDER BY abs(total) DESC LIMIT 30;
```

A group with many rows is a good candidate for a new rule.

### Recurring payments and subscriptions

```sql
SELECT description, round(amount, 2) AS amount, count(*) AS n,
       min(transactiondate) AS first, max(transactiondate) AS last,
       count(DISTINCT substr(transactiondate, 1, 7)) AS months
FROM t
WHERE amount < 0 AND transactiondate >= date('now', '-12 months')
GROUP BY description, round(amount, 2)
HAVING months >= 3
ORDER BY months DESC, amount;
```

A payment that stopped (`last` is more than two months ago) is probably
cancelled. A payment with a new, higher amount shows a price increase.

### The largest transactions

```sql
SELECT transactiondate, accountNumber, amount, cat, substr(description, 1, 60)
FROM t WHERE transactiondate >= date('now', '-3 months')
ORDER BY abs(amount) DESC LIMIT 20;
```

### Spend per tag

```sql
SELECT tagset, round(sum(amount), 2) AS net, count(*) AS n
FROM t WHERE tagset IS NOT NULL AND tagset <> ''
GROUP BY tagset ORDER BY net;
```

A row can have more than one tag. For one tag, use
`',' || replace(tagset, ' ', '') || ',' LIKE '%,2025prague,%'`.

### Spend per counterparty

```sql
SELECT json_extract(description_structured, '$.name') AS counterparty,
       round(sum(amount), 2) AS total, count(*) AS n
FROM t
WHERE json_valid(description_structured)
  AND json_extract(description_structured, '$.name') IS NOT NULL
  AND transactiondate >= date('now', '-12 months')
GROUP BY counterparty ORDER BY total LIMIT 25;
```

## Links to the app

The filter state of each page is in the URL. Give the user a link to the rows
behind each number, so that the user can check it. The app runs at
`http://127.0.0.1:8000` by default.

| Page | URL and parameters |
|---|---|
| Transactions | `/transactions?date_from=2026-01-01&date_to=2026-12-31&category=groceries&exclude_category=...&tag=...&account=...&q=<text>&amount_min=&amount_max=&include_transfers=1&sort=amount_asc` |
| Uncategorized | `/transactions?category=uncategorized` |
| Trends | `/trends` |
| Budgets | `/budgets` |
| Cash flow | `/cash-flow` |
| Rules | `/rules` |

`category`, `exclude_category`, `tag`, and `account` can occur more than once.
The values of one parameter combine with OR. `preset` accepts `this-month`,
`last-month`, `this-year`, and `last-year`.

## Changes through the app

Ask the user before each change. Prefer the web UI, because it shows a preview
and records the audit trail. These endpoints accept an HTTP form post while the
app runs:

| Change | Request |
|---|---|
| Set the category of one transaction by hand | `POST /transactions/{id}/category` with the form field `manual_category` |
| Set the tags of one transaction by hand | `POST /transactions/{id}/tags` with the form field `manual_tags` |
| Add tags to many transactions | `POST /transactions/bulk-tags` with `transaction_ids` (comma-separated) and `tags` |

```bash
curl -s -X POST "http://127.0.0.1:8000/transactions/<id>/category" \
     --data-urlencode "manual_category=groceries-ah" -o /dev/null -w "%{http_code}\n"
```

Do not make a rule or a budget with `curl`. Write the rule or the budget
proposal for the user, and tell the user to make it on the Rules page or the
Budgets page. The Rules page shows the transactions that a rule will change
before it saves the rule.

## How to give advice

1. Make sure that the data covers the period. Look at the coverage query and
   at `download_state`. Tell the user about each gap.
2. Answer the question with numbers first. Give the period, the currency, and
   the number of transactions.
3. Compare with an earlier period or with the average, so that a number has a
   context.
4. Look for these items, and tell the user about each one that you find:
   - A category that is over budget, or will be over budget at the end of the
     period at the current rate.
   - A month with a negative net cash flow, or a savings rate that goes down.
   - A recurring payment that the user possibly does not use.
   - A large or unusual transaction.
   - Many uncategorized transactions. These make each category total too low.
   - A category without a budget that has a high, regular spend.
5. Propose a concrete action for each item: a budget amount, a rule, or a
   payment to cancel. Show the link to the rows in the app.
6. Do not give investment, tax, or legal advice as a fact. Tell the user to ask
   a qualified advisor for these subjects.
