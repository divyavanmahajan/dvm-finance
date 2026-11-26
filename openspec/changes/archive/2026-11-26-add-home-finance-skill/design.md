# Design

## Context

The rule "No LLM" in `docs/core-beliefs.md` applies to the app. The app must
not call a language model or need an API key. This change adds no code to the
app. The skill is a text file that an agent outside the app reads.

## Decisions

### D1: The skill reads the database and not the HTTP interface

Each read route of the app gives HTML for htmx. An agent cannot read numbers
from these pages in a reliable manner. The skill therefore reads the SQLite
database with `sqlite3 -readonly` or the URI `mode=ro`. A read-only connection
does not block the running app.

### D2: Each change goes through the app

Each rule change must make a stored change report. A direct SQL write skips the
report and breaks the audit trail. The skill therefore does not allow a write
to the database. For one transaction, the agent can post to the form endpoints
of the manual category and the manual tags. For a rule or a budget, the agent
writes a proposal, and the user makes it in the web UI.

### D3: The queries use the calculation rules of the app

The skill gives these rules: the live rows only, the effective category with
the manual priority, the hyphen hierarchy, and the transfer exclusion. The
budget query and the cash-flow query give the same values as
`core/budget_report.py` and `core/cash_flow.py`.

### D4: The plugin lives in the repository

The repository root holds the marketplace manifest. The user installs the
plugin with one command, and each release of the repository updates the skill.
The user can also copy the skill folder into `~/.claude/skills`.

## Risks

- A schema change can make a query in the skill wrong. Update the skill in the
  same change as the Alembic migration.
- The sample-data filter in the skill removes the rows with the id prefix
  `sample-`. The screens of the app keep these rows. The numbers differ only
  when the user loads the sample data.
