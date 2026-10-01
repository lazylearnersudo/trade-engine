from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4

from modules.execution import reconcile
from shared.db import pool
from shared.db import migrate


def run(client, headers, strategy_id, key="run-1"):
    response = client.post(
        f"/api/v1/strategies/{strategy_id}/run", headers=headers, json={"idempotency_key": key}
    )
    assert response.status_code == 200
    return response.json()


def test_login_logout_and_auth(client, headers):
    assert client.get("/api/v1/orders").status_code == 401
    assert client.get("/api/v1/auth/me", headers=headers).json()["role"] == "SUPERUSER"
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/v1/orders", headers=headers).status_code == 401


def test_dummy_vertical_slice(client, headers, strategy_id):
    result = run(client, headers, strategy_id)
    assert result["run"]["status"] == "COMPLETED"
    orders = client.get("/api/v1/orders", headers=headers).json()
    assert orders[0]["status"] == "FILLED"
    assert orders[0]["filled_quantity"] == 10
    positions = client.get("/api/v1/positions", headers=headers).json()
    assert positions[0]["quantity"] == 10
    assert Decimal(str(positions[0]["market_value"])) == 2500
    assert client.get("/api/v1/audit", headers=headers).json()


def test_duplicate_and_recovery(client, headers, strategy_id):
    first = run(client, headers, strategy_id)
    reconcile()
    second = run(client, headers, strategy_id)
    assert second["duplicate"]
    assert first["run"]["id"] == second["run"]["id"]
    assert len(client.get("/api/v1/orders", headers=headers).json()) == 1


def test_migrations_repeat_safely(client):
    migrate()
    migrate()
    assert client.get("/health/ready").status_code == 200


def test_concurrent_retry(client, headers, strategy_id):
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: run(client, headers, strategy_id), range(4)))
    assert len({r["run"]["id"] for r in results}) == 1
    assert len(client.get("/api/v1/orders", headers=headers).json()) == 1


def test_kill_switch(client, headers, strategy_id):
    client.put("/api/v1/controls", headers=headers, json={"kill_switch": True})
    result = run(client, headers, strategy_id)
    assert result["run"]["status"] == "REJECTED"
    assert "Kill switch" in result["run"]["reason"]
    assert not client.get("/api/v1/orders", headers=headers).json()


def test_broker_reject_and_outage(client, headers, strategy_id):
    for scenario in ("REJECT", "OUTAGE"):
        client.put(
            "/api/v1/brokers/DUMMY", headers=headers, json={"enabled": True, "scenario": scenario}
        )
        assert run(client, headers, strategy_id, scenario)["run"]["status"] == "REJECTED"
    brokers = client.get("/api/v1/brokers", headers=headers).json()
    assert next(b for b in brokers if b["id"] == "DUMMY")["status"] == "DEGRADED"


def test_ambiguous_no_retry(client, headers, strategy_id):
    client.put(
        "/api/v1/brokers/DUMMY", headers=headers, json={"enabled": True, "scenario": "AMBIGUOUS"}
    )
    assert run(client, headers, strategy_id)["run"]["status"] == "AMBIGUOUS"
    reconcile()
    assert run(client, headers, strategy_id)["duplicate"]
    assert client.get("/api/v1/orders", headers=headers).json()[0]["status"] == "AMBIGUOUS"


def test_partial_then_reconcile(client, headers, strategy_id):
    client.put(
        "/api/v1/brokers/DUMMY", headers=headers, json={"enabled": True, "scenario": "PARTIAL"}
    )
    run(client, headers, strategy_id)
    assert client.get("/api/v1/orders", headers=headers).json()[0]["filled_quantity"] == 5
    client.put(
        "/api/v1/brokers/DUMMY", headers=headers, json={"enabled": True, "scenario": "NORMAL"}
    )
    reconcile()
    reconcile()
    assert client.get("/api/v1/positions", headers=headers).json()[0]["quantity"] == 10


def test_limit_cancel_and_reservation(client, headers, strategy_id):
    client.put(
        f"/api/v1/strategies/{strategy_id}",
        headers=headers,
        json={"name": "limit", "budget": "2500", "limit_price": "240", "enabled": True},
    )
    run(client, headers, strategy_id)
    order = client.get("/api/v1/orders", headers=headers).json()[0]
    assert order["status"] == "OPEN"
    assert (
        client.post(f"/api/v1/orders/{order['id']}/cancel", headers=headers).json()["status"]
        == "CANCELLED"
    )
    assert client.post(f"/api/v1/orders/{order['id']}/cancel", headers=headers).status_code == 409


def test_stale_price_and_risk_rejection(client, headers, strategy_id):
    with pool.connection() as conn:
        conn.execute("UPDATE trade.quotes SET updated_at=now()-interval '1 hour'")
    result = run(client, headers, strategy_id)
    assert "stale" in result["run"]["reason"]


def test_position_discrepancy_visible(client, headers, strategy_id):
    run(client, headers, strategy_id)
    with pool.connection() as conn:
        conn.execute("UPDATE trade.positions SET quantity=11")
    result = client.post("/api/v1/reconcile", headers=headers).json()
    assert len(result["discrepancies"]) == 1
    assert (
        client.get("/api/v1/positions", headers=headers).json()[0]["reconciliation_status"]
        == "DISCREPANCY"
    )


def test_role_and_ownership(client, headers, strategy_id):
    email = "user-" + str(uuid4())
    result = client.post(
        "/api/v1/users",
        headers=headers,
        json={"email": email, "password": "test-password-123", "role": "USER"},
    )
    assert result.status_code == 201
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "test-password-123"}
    ).json()["access_token"]
    user_headers = {"Authorization": "Bearer " + token}
    assert (
        client.put("/api/v1/controls", headers=user_headers, json={"kill_switch": True}).status_code
        == 403
    )
    assert (
        client.get(f"/api/v1/strategies/{strategy_id}/runs", headers=user_headers).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/strategies/{strategy_id}/run",
            headers=user_headers,
            json={"idempotency_key": "other"},
        ).status_code
        == 403
    )
    assert client.get("/api/v1/strategies", headers=user_headers).json() == []


def test_forgot_reset_single_use(client, headers):
    email = "reset-" + str(uuid4())
    client.post(
        "/api/v1/users",
        headers=headers,
        json={"email": email, "password": "original-password", "role": "USER"},
    )
    token = client.post("/api/v1/auth/forgot", json={"email": email}).json()["local_reset_token"]
    body = {"token": token, "password": "changed-password"}
    assert client.post("/api/v1/auth/reset", json=body).status_code == 200
    assert client.post("/api/v1/auth/reset", json=body).status_code == 400
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": email, "password": "changed-password"}
        ).status_code
        == 200
    )


def test_live_configuration_controls(client, headers):
    assert client.post("/api/v1/controls/arm", headers=headers).status_code == 409
    assert (
        client.put("/api/v1/brokers/DHAN", headers=headers, json={"enabled": True}).status_code
        == 409
    )


def test_security_and_health(client, headers):
    assert client.get("/health/ready").status_code == 200
    assert client.get("/").headers["Content-Security-Policy"]
    assert (
        client.post(
            "/api/v1/auth/login",
            headers={"Origin": "https://evil.example"},
            json={"email": "admin", "password": "admin"},
        ).status_code
        == 403
    )

    assert (
        client.post(
            "/api/v1/strategies", headers=headers, json={"name": "bad", "budget": "-1"}
        ).status_code
        == 422
    )


def test_dummy_cash_rejects_insufficient_funds(client, headers, strategy_id):
    response = client.put(
        "/api/v1/brokers/DUMMY", headers=headers, json={"enabled": True, "cash": "100"}
    )
    assert response.status_code == 200
    result = run(client, headers, strategy_id)
    assert result["run"]["status"] == "REJECTED"
    assert "cash" in result["run"]["reason"]
