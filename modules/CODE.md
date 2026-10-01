# Module map

- auth.py: Argon2 sessions/reset tokens, Supabase verification, role/ownership checks. Never trust client-selected roles; admin/admin is local-only.
- broker.py: capability boundary, deterministic dummy outcomes, optional Dhan/FYERS/Zerodha profile checks. External order capabilities are disabled. Secrets come from a server file.
- strategy.py: ETF BUY calculation and IST schedule slots/next run. No broker calls.
- risk.py: pure intent validation and deployed/live prerequisites. Every order passes through it.
- execution.py: locks, idempotency, reservations, orders, fills, positions, cancellation and reconciliation. Never retry ambiguous submissions. Live placement needs a durable pre-submission commit and contract tests first.
- scheduler.py: ten-second ticks; schedules persist as data. Five-minute grace, weekdays, no older catch-up.
- operations.py: audit writes containing safe domain context.

Composition/DTO validation: app/main.py and app/contracts.py. Shared database/config: shared. Schema changes: versioned migrations. Behavioral coverage: tests/test_domain.py and tests/test_api.py.

Run focused tests against an isolated PostgreSQL database, e.g. `pytest tests/test_api.py::test_duplicate_and_recovery`. Keep routes thin and change rules in their owning module. Reconciliation flags discrepancies without rewriting history. Dummy cash/fills survive restart; ordinary users' positions derive from their own fills.
