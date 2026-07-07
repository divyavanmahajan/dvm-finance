> **Initial draft** — scaffolded from spec interview. Updated by spec-execute as each phase completes.

# Core Beliefs

1. **Port, don't rewrite.** The rule engine, parsers, dedup logic, and downloader internals in abn-analyst/abn-download are proven. Copy them (with their tests) and adapt; never reimplement matching or parsing semantics from scratch.
2. **Manual edits are sacred.** `manual_category`/`manual_tags` always take precedence and are never overwritten by rule reapplication. Only snapshot import (incoming-wins, by explicit user action) may replace them.
3. **No LLM, no MCP, no auth, no charts, no Docker.** These were deliberately removed. Do not add API keys, login screens, chart libraries, or Dockerfiles.
4. **Local-only by default.** Bind to 127.0.0.1. There is no auth layer, so never widen the bind address silently.
5. **Every rule change is auditable.** Any create/edit/delete/toggle of a rule must produce a stored change report of affected transactions. No silent recategorization.
6. **Schema changes go through Alembic only.** No `ensure_*`-style runtime schema mutation (a known legacy wart in abn-analyst).
7. **TDD, red/green.** Write the failing test first — unit for logic, TestClient for routes, Playwright for flows. A step is not done until `pytest` and `ruff check` pass and UI features are verified in a real browser.
8. **Filter state lives in the URL.** All transaction filtering is expressed in the query string so trends click-through, bookmarks, and htmx partial swaps all use one mechanism.
9. **No JS build step.** htmx + Alpine.js as vendored static files; if a feature seems to need a bundler, simplify the feature.
10. **Deterministic identity everywhere.** Transactions keep their deterministic ids; rules carry a UUID from creation so snapshots merge across machines without heuristics.
