# Product

`abn-combined` merges abn-download (statement downloaders) and abn-analyst (categorizer/viewer) into one local web app run via `uvx abn-combined`.

## Goals

- Download (ABN AMRO, PayPal) and upload (MT940/XLS/CSV/PayPal/Wise/SEB) statements from the web UI; auto-import with dedup and rule application.
- Rule-based categorization with conditions, priorities, tags; fast "create rule from transaction"; preview before saving; stored change reports after every rule change.
- Two main tabs: **Transactions** (redesigned simple filter bar, URL-encoded filters) and **Category Trends** (table with cell/row click-through to filtered transactions). Plus Rules, Tags, Budgets, Cash Flow, Download/Upload, Snapshots.
- Share data with one other person via export/import snapshots (incoming wins).
- One-time migration from the legacy `abn_analyst.db`.

Removed on purpose: graphs, LLM categorization, MCP servers, login.

## Key flows

1. Download tab → authenticate in opened browser → statements imported → summary.
2. Filter Uncategorized → create rule from a transaction → preview matches → save → change report.
3. Trends cell click → filtered transaction list for that category/period.
4. Edit rule → preview impact → save → audit history per rule.
5. Export snapshot → partner imports → incoming-wins merge report.
