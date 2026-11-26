# Proposal

## Why

The user wants an agent to analyze the household finances in dvm-finance. The
agent must answer questions about the transactions, the trends, the budgets,
and the cash flow. It must also give advice on the home finances.

The app has no JSON read interface. Each page gives HTML for htmx. An agent
therefore needs instructions to read the SQLite database. The numbers of the
agent must agree with the numbers on the screens of the app.

## What Changes

- The repository SHALL hold the agent skill `home-finance` in
  `plugins/home-finance/skills/home-finance/SKILL.md`.
- The skill SHALL tell the agent to open the database read-only, and to make
  each change through the app.
- The skill SHALL give the data model, the calculation rules of the app, and a
  tested query for each analysis.
- The repository SHALL be a plugin marketplace. The file
  `.claude-plugin/marketplace.json` lists the plugin `home-finance`. The file
  `plugins/home-finance/.claude-plugin/plugin.json` describes the plugin.
- The README SHALL tell the user how to install and use the skill.
- The app does not change. The app calls no language model.

## Capabilities

### New Capabilities

- `home-finance-skill`: The agent skill, its plugin manifests, and its install
  instructions.

## Impact

- New files: `SKILL.md`, `plugin.json`, and `marketplace.json`.
- `README.md` gets the section "Claude Code skill: home finance analysis".
- No change to the Python code, the database schema, or the iOS app.
