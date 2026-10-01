# Quickstart

Run `docker compose up --build`. Open localhost:8000 and sign in with admin/admin. App/database ports bind only to loopback.

Create an ETF strategy with DUMMY / paper, enter a budget within risk limits, enable it, and run manually or set a weekday schedule between 09:15 and 15:29 IST. Triggers older than five minutes are skipped. Exchange holidays require disabling scheduled strategies. Inspect the resulting run, order, position and audit activity.

Outside Docker: start PostgreSQL, copy .env.example to .env, install requirements.lock, and run `uvicorn app.main:app`. Python 3.12+ is supported.

Tests: install requirements-dev.txt, create a separate trade_test database, set DATABASE_URL, and run `pytest -q`. Never point tests at production: they truncate order/run/position/audit tables. Also run `ruff check .` and `ruff format --check .`.

OCI: copy the repository to a dedicated directory. Supply mode-600 deploy/oracle/.env.production with deployed/DUMMY mode, Supabase Auth values and TLS PostgreSQL URL, plus deploy/oracle/.env with APP_HOST. Run `sh deploy/oracle/install.sh`. Backend binds loopback:8100; Caddy exposes HTTPS:443. Both host firewall and OCI security list/NSG must allow TCP 443. The ingress script preserves existing rules while adding HTTPS with authorized instance-principal access.

Docker starts at boot; containers restart automatically. Readiness: /health/ready. State lives in the external database. The optional preview Compose file creates an outbound HTTPS quick tunnel; its hostname changes on restart and it has no uptime guarantee. It does not replace permanent production ingress.

Vercel's static-shell deployment script creates a separate project with secure API rewrites. Supabase recovery needs a real admin email, SMTP and matching site URL/redirect allowlist.

Risk limits and kill switch require administrator role. Kill switch blocks new submissions; existing orders may fill. Cancellation is separate. Reconciliation flags discrepancies without rewriting history. Live arming remains unavailable until order adapters/account contracts pass validation.
