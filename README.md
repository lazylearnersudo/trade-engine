# Trade Engine

A modular ETF execution and risk workspace. FastAPI serves a responsive UI and persistent scheduler; PostgreSQL stores strategies, runs, orders, fills, positions, limits and audit. Production authentication uses Supabase Auth.

Run `docker compose up --build`, open `http://localhost:8000`, and sign in with `admin` / `admin`. These credentials exist only in local mode. All default prices and fills are simulated.

Features: configurable ETF strategies and run history, orders/cancellation, positions, broker status, risk limits, kill switch, reconciliation, activity, administration and system/light/dark themes. Authorization is enforced server-side.

Live order routing is disabled. Dhan, FYERS and Zerodha provide optional credential-backed profile checks; Shoonya awaits OAuth validation. Tokens alone cannot enable live orders. Local LIVE mode is rejected at startup and execution.

See [quickstart](docs/quickstart.md), [architecture](docs/architecture.md), and [module map](modules/CODE.md). OCI scripts live in `deploy/oracle`; a separate Vercel static-shell deployment is in `deploy/vercel`.

Validation: install `requirements-dev.txt`, run `ruff check .`, `ruff format --check .`, `python -m compileall -q app modules shared`, `pytest -q`, and `docker build .`. Tests require an isolated PostgreSQL database configured with DATABASE_URL; CI supplies it without broker/cloud credentials.
