import json
from pathlib import Path

import httpx
import psycopg

path = Path(".pat/bootstrap.json")
config = json.loads(path.read_text())
headers = {
    "apikey": config["supabase_service_key"],
    "Authorization": "Bearer " + config["supabase_service_key"],
}
with httpx.Client(base_url=config["supabase_url"], headers=headers, timeout=20) as client:
    response = client.get("/auth/v1/admin/users", params={"page": 1, "per_page": 1000})
    if response.status_code != 200:
        raise SystemExit("Supabase admin API unavailable; credentials suppressed.")
    users = response.json().get("users", [])
    account = next((user for user in users if user.get("email") == config["admin_email"]), None)
    if not account:
        result = client.post(
            "/auth/v1/admin/users",
            json={
                "email": config["admin_email"],
                "password": config["admin_password"],
                "email_confirm": True,
            },
        )
        if result.status_code not in (200, 201):
            raise SystemExit("Production account creation rejected; credentials suppressed.")
        account = result.json()
    with psycopg.connect(config["database_url"]) as conn:
        conn.execute(
            "INSERT INTO trade.users(id,email,role) VALUES (%s,%s,'SUPERUSER') ON CONFLICT(id) DO UPDATE SET role='SUPERUSER'",
            (account["id"], config["admin_email"]),
        )
        conn.execute("UPDATE trade.controls SET live_armed=false WHERE id=1")
    result = client.post(
        "/auth/v1/token?grant_type=password",
        json={"email": config["admin_email"], "password": config["admin_password"]},
    )
    if result.status_code != 200:
        raise SystemExit(
            "Production login verification failed; inspect the private bootstrap account."
        )
Path(".pat/deployed-login.md").write_text(
    f"# Production login\n\nURL: https://trade-engine.68.233.110.19.nip.io\n\nEmail: {config['admin_email']}\n\nPassword: {config['admin_password']}\n\nRole: SUPERUSER. Supabase Auth verifies this account. Live trading remains disarmed.\n\nKeep this file private.\n"
)
print(
    "Production Supabase login verified. Account details saved privately in .pat/deployed-login.md."
)
