# Tech Debt Tracker

Accepted warnings and known shortcuts, tracked so they are not forgotten or inadvertently replicated.

| Phase | Area | Warning | Date Accepted | Owner |
|-------|------|---------|---------------|-------|
| init | Schema Validation | No centralized schema layer; FastAPI per-endpoint Form/Query validation, Pydantic models only on the upload API | 2026-07-08 | unassigned |
| init | Demo Document | demo.md skipped — showboat unavailable; per-step screenshots + e2e suite serve as evidence | 2026-07-08 | unassigned |
| init | Downloads (open action, not accepted debt) | Real ABN AMRO / PayPal download flows verified via mocked tests only; live-credential session still pending | 2026-07-08 | Divya |
