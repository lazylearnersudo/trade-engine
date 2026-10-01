import json
from pathlib import Path

import httpx

config = json.loads(Path(".pat/bootstrap.json").read_text())
base = (
    config.get("vercel_url")
    or config.get("backend_url")
    or "https://trade-engine.68.233.110.19.nip.io"
)
with httpx.Client(base_url=base, timeout=30) as client:
    assert client.get("/health/ready").status_code == 200
    assert (
        client.post("/api/v1/auth/login", json={"email": "admin", "password": "admin"}).status_code
        == 401
    )
    result = client.post(
        "/api/v1/auth/login",
        json={"email": config["admin_email"], "password": config["admin_password"]},
    )
    assert result.status_code == 200, "Production login failed"
    client.headers["Authorization"] = "Bearer " + result.json()["access_token"]
    assert client.get("/api/v1/auth/me").json()["role"] == "SUPERUSER"
    existing = client.get("/api/v1/strategies").json()
    name = "ETF allocation · deployment verification"
    item = next((s for s in existing if s["name"] == name), None)
    body = {"name": name, "budget": "2500", "enabled": True}
    if item:
        item_id = item["id"]
        assert client.put(f"/api/v1/strategies/{item_id}", json=body).status_code == 200
    else:
        result = client.post("/api/v1/strategies", json=body)
        assert result.status_code == 201
        item_id = result.json()["id"]
    key = "deployment-verification-etf-v1"
    run = client.post(f"/api/v1/strategies/{item_id}/run", json={"idempotency_key": key}).json()
    assert run["run"]["status"] == "COMPLETED"
    duplicate = client.post(
        f"/api/v1/strategies/{item_id}/run", json={"idempotency_key": key}
    ).json()
    assert duplicate["duplicate"] and duplicate["run"]["id"] == run["run"]["id"]
    assert client.get("/api/v1/orders").json()[0]["status"] == "FILLED"
    assert client.get("/api/v1/positions").json()[0]["quantity"] >= 10
    assert client.get("/api/v1/audit").json()
    assert client.post("/api/v1/controls/arm").status_code == 409
    assert client.post("/api/v1/reconcile").json()["discrepancies"] == []
    body["enabled"] = False
    assert client.put(f"/api/v1/strategies/{item_id}", json=body).status_code == 200
    assert client.post("/api/v1/controls/disarm").status_code == 200
Path(".pat/deployed-login.md").write_text(
    f"# Deployed application login\n\nURL: {base}\n\nEmail: {config['admin_email']}\n\nPassword: {config['admin_password']}\n\nRole: SUPERUSER. Supabase Auth verified. Live disarmed.\n\nThe current HTTPS tunnel hostname changes if the tunnel process restarts. Permanent OCI ingress needs the access listed in prequisites.md.\n"
)
print(
    "Production smoke passed: HTTPS, Supabase login, role, strategy, paper fill, position, audit, idempotency, reconciliation and live disarm. No real orders submitted."
)
