# Tasks

## 1. The skill

- [x] 1.1 Write `plugins/home-finance/skills/home-finance/SKILL.md` with the safety rules, the location of the database, the data model, the calculation rules, the queries, the links to the app, and the advice steps. Verify that the text uses ASD-STE100.
- [x] 1.2 Run each SQL query of the skill against a read-only connection to a real database. Verify that each query runs without an error.
- [x] 1.3 Compare the budget query with `budget_vs_actual_table` and the cash-flow query with `compute_cash_flow`. Verify that the values agree for each budget and each month.

## 2. The plugin and the marketplace

- [x] 2.1 Write `plugins/home-finance/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`. Verify with `claude plugin validate .` and `claude plugin validate plugins/home-finance`.

## 3. The README

- [x] 3.1 Add the install commands, the manual copy, and example questions to `README.md`. Verify that the text uses ASD-STE100.
