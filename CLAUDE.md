# CLAUDE.md

Local single-user finance app: download/upload bank statements, categorize with auditable rules, review trends. FastAPI + SQLite + Jinja2/htmx/Alpine (no JS build step). Distributed on PyPI as `dvm-finance`; runs via `uvx dvm-finance` (the repo/source dir is `abn-combined`).

## Environment

Always use the shared virtualenv:

```bash
source ~/venv/bin/activate
pip install -e ".[dev]"
```

## Commands

```bash
dvm-finance --data-dir ./devdata    # run the app (http://127.0.0.1:8000)
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
- **Never mention Claude, Anthropic, or model names in commit messages, PR titles, or PR descriptions.**
- **Write all prose in ASD-STE100 Simplified Technical English** — docs, specs,
  code comments, docstrings, commit messages, PR descriptions, and UI text. See
  [Writing style](#writing-style-asd-ste100).

## Writing style (ASD-STE100)

Use ASD-STE100 Simplified Technical English for every piece of prose in this
repository. The rules that apply most often:

- Write one instruction per sentence. Keep procedural sentences to 20 words or
  fewer and descriptive sentences to 25 words or fewer.
- Use the active voice and name the actor: "The importer skips the duplicate",
  not "The duplicate is skipped".
- Use the simple present tense where possible. Do not use the present participle
  or the gerund as a noun: "after you import the file", not "after importing the
  file".
- Give each word one meaning and each meaning one word. Do not use a noun as a
  verb. Keep noun clusters to three words or fewer.
- Keep the article: "the transaction", not "transaction".
- Do not use a figure of speech, an idiom, slang, or an undefined abbreviation.
- Write a warning or a caution as a command, and put it before the step it
  applies to.

Technical names stay as they are: identifiers, column names, route paths, CLI
flags, and the SHALL/MUST keywords that the OpenSpec specs need.

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
