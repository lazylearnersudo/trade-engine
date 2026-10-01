# Architecture

FastAPI composes domain modules, a browser-native UI and a persistent scheduler. PostgreSQL stores operational state in both environments; production uses the main Supabase database/Auth. No backtesting or historical market-data platform is included.

Strategy produces broker-neutral ETF BUY intent. Risk validates it. Execution owns persisted run/order/fill state and calls capability-based adapters. Dummy execution supports market, limit, partial, rejection, outage and ambiguous scenarios. External order capabilities are disabled pending adapter and account contract validation.

PostgreSQL advisory transaction locks serialize submissions, reservations and operational mutations. Unique idempotency keys prevent duplicate schedule/manual retries. Unknown submissions stay ambiguous. Startup reconciliation surfaces interrupted states. Dummy effects commit atomically with order and audit. Future live HTTP placement requires a durable submission record committed before contacting the broker; do not insert live calls into the current transaction.

Quotes are simulated and timestamped. The dummy scheduler refreshes them. Live execution must acquire broker quotes and cannot rely on manually entered prices. Risk validates quantity/value, daily capital, exposure, open orders, cash/reservations, instrument/account/broker permissions, session times and freshness. Exchange holidays remain an operator responsibility.

Local authentication uses Argon2 and hashed opaque sessions; admin/admin is local-only. Production verifies Supabase identities each request and reads roles from the application database. USER data is scoped by ownership. ADMIN operates global controls; SUPERUSER assigns roles. Tables use the private trade schema; migration tracking is explicitly public.trade_migrations to avoid search-path ambiguity.

OCI Docker hosts persistent execution and optionally the UI behind Caddy. Vercel may host the static UI with secure API rewrites. Secrets never enter images/client bundles. Default execution is DUMMY; local live execution and unsupported production arming fail closed. Schedules use Asia/Kolkata; timestamps are UTC.
