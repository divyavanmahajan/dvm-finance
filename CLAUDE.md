# CLAUDE.md

Local single-user finance app: download/upload bank statements, categorize with auditable rules, review trends. FastAPI + SQLite + Jinja2/htmx/Alpine (no JS build step). Runs via `uvx abn-combined`.

## Environment

Always use the shared virtualenv:

```bash
source ~/venv/bin/activate
pip install -e ".[dev]"
```

## Commands

```bash
abn-combined --data-dir ./devdata   # run the app (http://127.0.0.1:8000)
pytest                              # unit + integration (e2e/slow deselected)
pytest -m e2e                       # Playwright e2e (5 user flows)
pytest --cov=abn_combined           # coverage, fail_under=80
ruff check .                        # lint gate
```

## Key docs

- `docs/core-beliefs.md` — project golden principles; read before any change
- `docs/architecture.md` — stack, module map, data-model invariants, snapshot format
- `docs/developer.md` — setup, commands, e2e harness
- `docs/product.md` — features and user flows

## Hard rules (from core-beliefs)

- Manual categorizations are never overwritten by rule reapplication; only snapshot import may (explicitly, audited).
- Every rule mutation goes through `record_rule_change` — no silent recategorization.
- Schema changes via Alembic only. Filter state lives in the URL. No JS build step. No LLM/MCP/auth/charts/Docker.

## Tag-only rules (v1.1.0+)

`CategorizationRule.is_tag_only` marks a rule as tags-only (no `category`).
`core/categorizer.py:apply_rules` runs two passes: category rules first
(priority order, first match wins, non-manual transactions only), then
tag-only rules (all matches apply, even to manually categorized
transactions, merged/de-duplicated into `tags`, category untouched). See
`docs/architecture.md` (Rules categorization) and `docs/product.md`
(Tag-only rules) for details.

## Phase: init
See full phase summary: [docs/phase/init/phase-summary.md](docs/phase/init/phase-summary.md)
