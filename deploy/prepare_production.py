import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
config = json.loads((root / ".pat/bootstrap.json").read_text())
host = "trade-engine.68.233.110.19.nip.io"
app_url = config.get("vercel_url") or config.get("backend_url") or "https://" + host
values = {
    "ENVIRONMENT": "deployed",
    "EXECUTION_MODE": "DUMMY",
    "DATABASE_URL": config["database_url"],
    "SUPABASE_URL": config["supabase_url"],
    "SUPABASE_ANON_KEY": config["supabase_anon_key"],
    "APP_URL": app_url,
    "ALLOWED_ORIGINS": ",".join(
        dict.fromkeys([app_url, "https://" + host, config.get("backend_url", app_url)])
    ),
    "APPROVED_OUTBOUND_IP": "",
    "VERIFIED_OUTBOUND_IP": "",
    "DEPLOYMENT_ACK": "",
}
target = root / "deploy/oracle/.env.production"
target.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
(root / "deploy/oracle/.env").write_text(f"APP_HOST={host}\n")
print("Production environment written; DUMMY mode and disarmed live execution.")
