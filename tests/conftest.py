import os
from unittest.mock import patch

os.environ.setdefault("ENVIRONMENT", "local")
os.environ.setdefault("EXECUTION_MODE", "DUMMY")
os.environ.setdefault("DATABASE_URL", "postgresql://trade:trade@localhost:5432/trade_test")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from shared.db import pool


@pytest.fixture(scope="session")
def client():
    from app.main import scheduler

    with patch.object(scheduler, "start"), patch.object(scheduler, "stop"):
        with TestClient(app) as session:
            yield session


@pytest.fixture(autouse=True)
def clean_database(request):
    if "client" not in request.fixturenames:
        return
    request.getfixturevalue("client")
    from app.main import attempts

    attempts.clear()
    with pool.connection() as conn:
        conn.execute(
            "TRUNCATE trade.fills,trade.orders,trade.runs,trade.strategies,trade.positions,trade.audit RESTART IDENTITY CASCADE"
        )
        conn.execute(
            "UPDATE trade.controls SET kill_switch=false,live_armed=false,risk=%s::jsonb WHERE id=1",
            (
                '{"max_order_value":10000,"max_quantity":100,"max_position_value":50000,"max_daily_capital":25000,"max_open_orders":5,"max_quote_age_seconds":30,"allowed_instruments":["NIFTYBEES","GOLDBEES"],"allowed_brokers":["DUMMY"],"allowed_accounts":["paper"],"market_hours_only":true}',
            ),
        )
        conn.execute("UPDATE trade.brokers SET cash=100000,enabled=(id='DUMMY'),scenario='NORMAL'")
        conn.execute(
            "UPDATE trade.quotes SET price=CASE WHEN symbol='NIFTYBEES' THEN 250 ELSE 75 END,updated_at=now()"
        )


@pytest.fixture
def headers(client):
    response = client.post("/api/v1/auth/login", json={"email": "admin", "password": "admin"})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["access_token"]}


@pytest.fixture
def strategy_id(client, headers):
    result = client.post(
        "/api/v1/strategies",
        headers=headers,
        json={"name": "ETF allocation", "budget": "2500", "enabled": True},
    )
    assert result.status_code == 201
    return result.json()["id"]
