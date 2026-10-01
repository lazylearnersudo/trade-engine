import logging
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from psycopg import IntegrityError
from psycopg.types.json import Jsonb

from app.contracts import (
    BrokerInput,
    ControlsInput,
    Login,
    PasswordReset,
    QuoteInput,
    Recovery,
    RiskInput,
    RoleInput,
    RunInput,
    StrategyInput,
    UserInput,
)
from modules import auth, broker, execution, strategy
from modules.operations import audit
from modules.scheduler import Scheduler
from shared.config import settings
from shared.db import migrate, pool
from shared.errors import DomainError

logger = logging.getLogger("trade.api")
scheduler = Scheduler()
attempts = defaultdict(deque)


@asynccontextmanager
async def lifespan(app):
    if settings.environment == "local" and settings.execution_mode == "LIVE":
        raise RuntimeError("Local LIVE configuration is forbidden")
    if settings.environment == "deployed" and (
        not settings.supabase_url or not settings.supabase_anon_key
    ):
        raise RuntimeError("Deployed mode requires Supabase Auth")
    pool.open(wait=True)
    try:
        migrate()
        auth.seed_local()
        scheduler.start()
        yield
    finally:
        scheduler.stop()
        pool.close()


app = FastAPI(
    title="Trade Engine", version="1.0.0", lifespan=lifespan, docs_url=None, redoc_url=None
)


@app.exception_handler(DomainError)
async def domain_error(request, error):
    return JSONResponse({"error": error.code, "message": error.message}, status_code=error.status)


@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    return JSONResponse(
        {
            "error": "VALIDATION",
            "message": "Invalid request fields",
            "fields": [".".join(map(str, item["loc"])) for item in error.errors()],
        },
        status_code=422,
    )


@app.exception_handler(IntegrityError)
async def integrity_error(request, error):
    return JSONResponse(
        {"error": "CONFLICT", "message": "The resource conflicts with existing data"},
        status_code=409,
    )


@app.exception_handler(Exception)
async def unexpected_error(request, error):
    logger.error('{"event":"request_failed","path":"%s"}', request.url.path)
    return JSONResponse(
        {
            "error": "INTERNAL",
            "message": "Operation failed; inspect service health or contact the administrator",
        },
        status_code=500,
    )


@app.middleware("http")
async def security(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        allowed = settings.allowed_origins.split(",")
        if origin and origin not in allowed:
            return JSONResponse({"message": "Origin is not allowed"}, status_code=403)
    if request.url.path.startswith("/api/v1/auth"):
        peer = request.client.host if request.client else "unknown"
        key = (peer, request.url.path)
        now = time.monotonic()
        queue = attempts[key]
        while queue and now - queue[0] > 60:
            queue.popleft()
        if len(queue) >= 15:
            return JSONResponse({"message": "Too many requests; try in a minute"}, status_code=429)
        queue.append(now)
        if len(attempts) > 10000:
            attempts.clear()
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health/live")
def liveness():
    return {"status": "UP"}


@app.get("/health/ready")
def readiness():
    try:
        with pool.connection() as conn:
            conn.execute("SELECT 1")
        return {
            "status": "UP",
            "database": "UP",
            "scheduler": "UP" if scheduler.thread.is_alive() else "DOWN",
        }
    except Exception:
        return JSONResponse({"status": "DOWN", "database": "DOWN"}, status_code=503)


@app.get("/api/v1/config")
def config():
    return {
        "environment": settings.environment,
        "execution_mode": settings.execution_mode,
        "auth_provider": "supabase" if settings.environment == "deployed" else "local",
        "market_timezone": "Asia/Kolkata",
    }


@app.post("/api/v1/auth/login")
def login(body: Login):
    return auth.login(body.email, body.password)


@app.post("/api/v1/auth/refresh")
def refresh(body: dict):
    if settings.environment != "deployed" or not isinstance(body.get("refresh_token"), str):
        raise DomainError("Refresh is not available", "AUTH", 400)
    try:
        result = httpx.post(
            settings.supabase_url + "/auth/v1/token?grant_type=refresh_token",
            headers={"apikey": settings.supabase_anon_key},
            json={"refresh_token": body["refresh_token"]},
            timeout=15,
        )
        if result.status_code != 200:
            raise DomainError("Session expired", "AUTH", 401)
        data = result.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_in": data["expires_in"],
        }
    except httpx.HTTPError:
        raise DomainError("Authentication service unavailable", "AUTH", 503) from None


@app.get("/api/v1/auth/me")
def me(user=Depends(auth.current_user)):
    return user


@app.post("/api/v1/auth/logout")
def logout(request: Request, user=Depends(auth.current_user)):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if settings.environment == "local":
        with pool.connection() as conn:
            conn.execute("DELETE FROM trade.sessions WHERE token_hash=%s", (auth.digest(token),))
            audit(conn, user["id"], "LOGOUT")
    else:
        try:
            result = httpx.post(
                settings.supabase_url + "/auth/v1/logout",
                headers={"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {token}"},
                timeout=15,
            )
            if result.status_code not in (200, 204):
                raise DomainError("Logout service unavailable", "AUTH", 503)
        except httpx.HTTPError:
            raise DomainError("Logout service unavailable", "AUTH", 503) from None
    return {"status": "SIGNED_OUT"}


@app.post("/api/v1/auth/forgot")
def forgot(body: Recovery):
    return auth.forgot_password(body.email)


@app.post("/api/v1/auth/reset")
def reset(body: PasswordReset):
    if settings.environment == "local":
        auth.reset_local(body.token, body.password)
    else:
        try:
            result = httpx.put(
                settings.supabase_url + "/auth/v1/user",
                headers={
                    "apikey": settings.supabase_anon_key,
                    "Authorization": f"Bearer {body.token}",
                },
                json={"password": body.password},
                timeout=15,
            )
            if result.status_code != 200:
                raise DomainError("Invalid or expired password recovery session", "AUTH", 400)
        except httpx.HTTPError:
            raise DomainError("Authentication service unavailable", "AUTH", 503) from None
    return {"status": "PASSWORD_CHANGED"}


@app.get("/api/v1/dashboard")
def dashboard(user=Depends(auth.current_user)):
    with pool.connection() as conn:
        controls = conn.execute("SELECT * FROM trade.controls WHERE id=1").fetchone()
        where, args = ("WHERE owner_id=%s", (user["id"],)) if user["role"] == "USER" else ("", ())
        counts = conn.execute(
            f"SELECT count(*) AS total,count(*) FILTER(WHERE enabled) AS active FROM trade.strategies {where}",
            args,
        ).fetchone()
        recent = conn.execute(
            f"SELECT id,symbol,broker,price,quantity,filled_quantity,status,reason,created_at FROM trade.orders {where} ORDER BY created_at DESC LIMIT 8",
            args,
        ).fetchall()
        ambiguous = conn.execute(
            f"SELECT count(*) AS n FROM trade.orders {where + ' AND' if where else 'WHERE'} status='AMBIGUOUS'",
            args,
        ).fetchone()["n"]
        brokers = conn.execute(
            "SELECT id,enabled,scenario,cash FROM trade.brokers ORDER BY id"
        ).fetchall()
    return {
        **config(),
        "controls": controls,
        "strategies": counts,
        "recent_orders": recent,
        "ambiguous_orders": ambiguous,
        "brokers": brokers,
        "live_ready": False,
        "live_reason": "Live broker order adapters require account contract validation",
    }


@app.get("/api/v1/strategies")
def strategies(user=Depends(auth.current_user)):
    with pool.connection() as conn:
        items = conn.execute(
            "SELECT * FROM trade.strategies"
            + (" WHERE owner_id=%s" if user["role"] == "USER" else "")
            + " ORDER BY created_at DESC",
            (user["id"],) if user["role"] == "USER" else (),
        ).fetchall()
    return [{**item, "next_run_at": strategy.next_run(item)} for item in items]


@app.post("/api/v1/strategies", status_code=201)
def create_strategy(body: StrategyInput, user=Depends(auth.current_user)):
    item_id = str(uuid.uuid4())
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO trade.strategies(id,owner_id,name,broker,account_id,symbol,budget,limit_price,enabled,schedule_time) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                item_id,
                user["id"],
                body.name,
                body.broker,
                body.account_id,
                body.symbol,
                body.budget,
                body.limit_price,
                body.enabled,
                body.schedule_time,
            ),
        )
        audit(conn, user["id"], "STRATEGY_CREATED", item_id)
    return {"id": item_id}


@app.put("/api/v1/strategies/{item_id}")
def update_strategy(item_id: str, body: StrategyInput, user=Depends(auth.current_user)):
    with pool.connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(731821)")
        item = conn.execute(
            "SELECT * FROM trade.strategies WHERE id=%s FOR UPDATE", (item_id,)
        ).fetchone()
        if not item:
            raise DomainError("Strategy not found", "NOT_FOUND", 404)
        auth.authorize_owner(user, item["owner_id"])
        conn.execute(
            "UPDATE trade.strategies SET name=%s,broker=%s,account_id=%s,symbol=%s,budget=%s,limit_price=%s,enabled=%s,schedule_time=%s WHERE id=%s",
            (
                body.name,
                body.broker,
                body.account_id,
                body.symbol,
                body.budget,
                body.limit_price,
                body.enabled,
                body.schedule_time,
                item_id,
            ),
        )
        audit(conn, user["id"], "STRATEGY_UPDATED", item_id)
    return {"id": item_id}


@app.get("/api/v1/strategies/{item_id}/runs")
def runs(item_id: str, user=Depends(auth.current_user)):
    with pool.connection() as conn:
        item = conn.execute(
            "SELECT owner_id FROM trade.strategies WHERE id=%s", (item_id,)
        ).fetchone()
        if not item:
            raise DomainError("Strategy not found", "NOT_FOUND", 404)
        auth.authorize_owner(user, item["owner_id"])
        return conn.execute(
            "SELECT * FROM trade.runs WHERE strategy_id=%s ORDER BY started_at DESC LIMIT 100",
            (item_id,),
        ).fetchall()


@app.post("/api/v1/strategies/{item_id}/run")
def run(item_id: str, body: RunInput, user=Depends(auth.current_user)):
    return execution.execute(item_id, body.idempotency_key, user)


@app.get("/api/v1/orders")
def orders(user=Depends(auth.current_user)):
    with pool.connection() as conn:
        return conn.execute(
            "SELECT * FROM trade.orders"
            + (" WHERE owner_id=%s" if user["role"] == "USER" else "")
            + " ORDER BY created_at DESC LIMIT 200",
            (user["id"],) if user["role"] == "USER" else (),
        ).fetchall()


@app.post("/api/v1/orders/{order_id}/cancel")
def cancel(order_id: str, user=Depends(auth.current_user)):
    return execution.cancel(order_id, user)


@app.get("/api/v1/positions")
def positions(user=Depends(auth.current_user)):
    with pool.connection() as conn:
        if user["role"] == "USER":
            return conn.execute(
                "SELECT o.broker,o.account_id,o.symbol,sum(f.quantity) AS quantity,sum(f.quantity*f.price)/sum(f.quantity) AS average_price,q.price AS current_price,sum(f.quantity)*q.price AS market_value,sum(f.quantity*(q.price-f.price)) AS unrealized_pnl,'DUMMY' AS source,max(p.reconciliation_status) AS reconciliation_status,max(f.created_at) AS updated_at FROM trade.fills f JOIN trade.orders o ON f.order_id=o.id LEFT JOIN trade.quotes q ON q.symbol=o.symbol LEFT JOIN trade.positions p ON p.broker=o.broker AND p.account_id=o.account_id AND p.symbol=o.symbol WHERE o.owner_id=%s GROUP BY o.broker,o.account_id,o.symbol,q.price",
                (user["id"],),
            ).fetchall()
        return conn.execute(
            "SELECT p.*,q.price AS current_price,p.quantity*q.price AS market_value,p.quantity*(q.price-p.average_price) AS unrealized_pnl FROM trade.positions p LEFT JOIN trade.quotes q ON q.symbol=p.symbol ORDER BY p.symbol"
        ).fetchall()


@app.get("/api/v1/brokers")
def brokers(user=Depends(auth.current_user)):
    with pool.connection() as conn:
        items = conn.execute("SELECT * FROM trade.brokers ORDER BY id").fetchall()
    return [
        {
            **item,
            "status": "DEGRADED"
            if item["scenario"] == "OUTAGE"
            else "CONNECTED"
            if item["id"] == "DUMMY"
            else "DISABLED",
            "capabilities": broker.adapter(item["id"]).capabilities,
            "integration": "Validated simulator"
            if item["id"] == "DUMMY"
            else "Profile connectivity only; live orders disabled",
        }
        for item in items
    ]


@app.put("/api/v1/brokers/{broker_id}")
def update_broker(broker_id: str, body: BrokerInput, user=Depends(auth.current_user)):
    auth.require_admin(user)
    if broker_id != "DUMMY":
        raise DomainError(
            "Live broker configuration requires validated deployment credentials",
            "CONFIGURATION",
            409,
        )
    with pool.connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(731821)")
        conn.execute(
            "UPDATE trade.brokers SET enabled=%s,scenario=%s,cash=coalesce(%s,cash) WHERE id=%s",
            (body.enabled, body.scenario, body.cash, broker_id),
        )
        audit(conn, user["id"], "BROKER_UPDATED", broker_id, details=body.model_dump(mode="json"))
    return {"status": "UPDATED"}


@app.post("/api/v1/brokers/{broker_id}/check")
def check_broker(broker_id: str, user=Depends(auth.current_user)):
    auth.require_admin(user)
    if broker_id not in ("DUMMY", "DHAN", "FYERS", "SHOONYA", "ZERODHA"):
        raise DomainError("Unknown broker")
    result = (
        {"status": "CONNECTED"}
        if broker_id == "DUMMY"
        else broker.adapter(broker_id).check_connection()
    )
    with pool.connection() as conn:
        audit(conn, user["id"], "BROKER_CONNECTION_CHECK", broker_id, result["status"])
    return result


@app.get("/api/v1/quotes")
def quotes(user=Depends(auth.current_user)):
    with pool.connection() as conn:
        return conn.execute(
            "SELECT *, 'SIMULATED' AS source FROM trade.quotes ORDER BY symbol"
        ).fetchall()


@app.put("/api/v1/quotes/{symbol}")
def update_quote(symbol: str, body: QuoteInput, user=Depends(auth.current_user)):
    auth.require_admin(user)
    if settings.execution_mode != "DUMMY":
        raise DomainError("Manual quotes are only supported in dummy mode", "CONFIGURATION")
    with pool.connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(731821)")
        if not conn.execute(
            "UPDATE trade.quotes SET price=%s,updated_at=now() WHERE symbol=%s RETURNING symbol",
            (body.price, symbol),
        ).fetchone():
            raise DomainError("Instrument not mapped", "NOT_FOUND", 404)
        audit(conn, user["id"], "DUMMY_PRICE_UPDATED", symbol)
    return {"status": "UPDATED"}


@app.get("/api/v1/risk")
def get_risk(user=Depends(auth.current_user)):
    with pool.connection() as conn:
        return conn.execute("SELECT * FROM trade.controls WHERE id=1").fetchone()


@app.put("/api/v1/risk")
def set_risk(body: RiskInput, user=Depends(auth.current_user)):
    auth.require_admin(user)
    with pool.connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(731821)")
        conn.execute(
            "UPDATE trade.controls SET risk=%s,updated_at=now() WHERE id=1",
            (Jsonb(body.model_dump()),),
        )
        audit(conn, user["id"], "RISK_UPDATED", details=body.model_dump())
    return {"status": "UPDATED"}


@app.put("/api/v1/controls")
def controls(body: ControlsInput, user=Depends(auth.current_user)):
    auth.require_admin(user)
    with pool.connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(731821)")
        conn.execute(
            "UPDATE trade.controls SET kill_switch=%s,updated_at=now() WHERE id=1",
            (body.kill_switch,),
        )
        audit(conn, user["id"], "KILL_SWITCH", details={"enabled": body.kill_switch})
    return {
        "kill_switch": body.kill_switch,
        "behavior": "Blocks new submissions; existing orders may still fill. No liquidation.",
    }


@app.post("/api/v1/controls/arm")
def arm(user=Depends(auth.current_user)):
    auth.require_admin(user)
    raise DomainError(
        "Live adapters are not validated; arming is unavailable", "CONFIGURATION", 409
    )


@app.post("/api/v1/controls/disarm")
def disarm(user=Depends(auth.current_user)):
    auth.require_admin(user)
    with pool.connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(731821)")
        conn.execute("UPDATE trade.controls SET live_armed=false WHERE id=1")
        audit(conn, user["id"], "LIVE_DISARMED")
    return {"live_armed": False}


@app.post("/api/v1/reconcile")
def reconcile(user=Depends(auth.current_user)):
    auth.require_admin(user)
    return execution.reconcile(user["id"])


@app.get("/api/v1/audit")
def activity(user=Depends(auth.current_user)):
    with pool.connection() as conn:
        return conn.execute(
            "SELECT * FROM trade.audit"
            + (" WHERE actor=%s" if user["role"] == "USER" else "")
            + " ORDER BY id DESC LIMIT 200",
            (user["id"],) if user["role"] == "USER" else (),
        ).fetchall()


@app.get("/api/v1/users")
def users(user=Depends(auth.current_user)):
    auth.require_admin(user)
    with pool.connection() as conn:
        return conn.execute(
            "SELECT id,email,role,created_at FROM trade.users ORDER BY created_at"
        ).fetchall()


@app.post("/api/v1/users", status_code=201)
def create_user(body: UserInput, user=Depends(auth.current_user)):
    if user["role"] != "SUPERUSER":
        raise DomainError("Superuser role required", "FORBIDDEN", 403)
    with pool.connection() as conn:
        item_id = auth.create_local_user(conn, body.email, body.password, body.role)
        audit(conn, user["id"], "USER_CREATED", item_id)
    return {"id": item_id}


@app.put("/api/v1/users/{user_id}/role")
def set_role(user_id: str, body: RoleInput, user=Depends(auth.current_user)):
    if user["role"] != "SUPERUSER":
        raise DomainError("Superuser role required", "FORBIDDEN", 403)
    if user_id == user["id"]:
        raise DomainError("Cannot change your own superuser role")
    with pool.connection() as conn:
        if not conn.execute(
            "UPDATE trade.users SET role=%s WHERE id=%s RETURNING id", (body.role, user_id)
        ).fetchone():
            raise DomainError("User not found", "NOT_FOUND", 404)
        audit(conn, user["id"], "USER_ROLE_UPDATED", user_id, details={"role": body.role})
    return {"status": "UPDATED"}


app.mount("/assets", StaticFiles(directory=Path("app/web")), name="assets")


@app.get("/")
def index():
    return FileResponse("app/web/index.html", headers={"Cache-Control": "no-cache"})
