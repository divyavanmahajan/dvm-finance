# Product

`abn-combined` merges abn-download (statement downloaders) and abn-analyst (categorizer/viewer) into one local web app run via `uvx abn-combined`.

## Goals

- Download (ABN AMRO, PayPal) and upload (MT940/XLS/CSV/PayPal/Wise/SEB) statements from the web UI; auto-import with dedup and rule application.
- Rule-based categorization with conditions, priorities, tags; fast "create rule from transaction"; preview before saving; stored change reports after every rule change.
- Two main tabs: **Transactions** (redesigned simple filter bar, URL-encoded filters; include and **exclude** category filters with subtree semantics; **transfer exclusion by default**) and **Category Trends** (table with cell/row click-through to filtered transactions). Plus Rules, Tags, Budgets, Cash Flow, Download/Upload, Snapshots.
- **Transfer exclusion**: Transfers (inter-account movements) excluded from all views by default to focus financial reporting on actual spending. Toggles on Transactions, Trends, and Cash Flow pages allow opting-in per-session.
- Share data with one other person via export/import snapshots (incoming wins).
- One-time migration from the legacy `abn_analyst.db`.

Removed on purpose: graphs, LLM categorization, MCP servers, login.

## Key flows

1. Download tab → authenticate in opened browser → statements imported → summary.
2. Filter Uncategorized → create rule from a transaction → preview matches → save → change report.
3. Trends cell click → filtered transaction list for that category/period.
4. Edit rule → preview impact → save → audit history per rule.
5. Export snapshot → partner imports → incoming-wins merge report.

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
