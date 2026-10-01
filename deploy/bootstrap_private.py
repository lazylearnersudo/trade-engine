"""Consume the private bootstrap file without writing credentials to stdout."""

import json
import re
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
raw = (root / ".pat/init.txt").read_text()
main = raw.split("supabase", 1)[1].split("backtest", 1)[0]
lines = [line.strip() for line in main.splitlines() if line.strip()]
url = re.search(r"https://[a-z]+\.supabase\.co", main).group()
anon = lines[lines.index("Anon") + 1]
service = lines[lines.index("Servicerole") + 1]
password = lines[2]
config = {
    "supabase_url": url,
    "supabase_anon_key": anon,
    "supabase_service_key": service,
    "database_password": password,
    "project_ref": url.split("//")[1].split(".")[0],
    "vercel_token": re.search(r"vcp_[A-Za-z0-9]+", raw).group(),
    "github_token": re.search(r"github_pat_[A-Za-z0-9_]+", raw).group(),
    "admin_email": "admin@trade-engine.local",
    "admin_password": secrets.token_urlsafe(24),
}
path = root / ".pat/bootstrap.json"
if path.exists():
    existing = json.loads(path.read_text())
    for key in ("admin_email", "admin_password", "database_url"):
        if key in existing:
            config[key] = existing[key]
path.write_text(json.dumps(config, indent=2))
print("Private bootstrap parsed; credential values suppressed.")
