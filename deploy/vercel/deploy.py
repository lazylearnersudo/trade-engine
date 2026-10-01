import json
from pathlib import Path

import httpx

root = Path(__file__).resolve().parents[2]
path = root / ".pat/bootstrap.json"
bootstrap = json.loads(path.read_text())
name = "trade-engine-companion"
backend = bootstrap.get("backend_url", "https://trade-engine.68.233.110.19.nip.io")
with httpx.Client(
    base_url="https://api.vercel.com",
    headers={"Authorization": "Bearer " + bootstrap["vercel_token"]},
    timeout=30,
) as client:
    projects = client.get("/v9/projects")
    teams = {
        p.get("accountId")
        for p in projects.json().get("projects", [])
        if p.get("accountId", "").startswith("team_")
    }
    if len(teams) == 1:
        client.params = {"teamId": next(iter(teams))}
    project = client.get("/v9/projects/" + name)
    if project.status_code == 404:
        project = client.post("/v10/projects", json={"name": name, "framework": None})
    if project.status_code not in (200, 201):
        print(
            "Vercel project access failed:",
            project.status_code,
            project.json().get("error", {}).get("code"),
        )
        raise SystemExit(1)
    project_id = project.json()["id"]
    config = {
        "rewrites": [
            {"source": "/api/:path*", "destination": backend + "/api/:path*"},
            {"source": "/health/:path*", "destination": backend + "/health/:path*"},
        ],
        "headers": [
            {
                "source": "/(.*)",
                "headers": [
                    {"key": "X-Content-Type-Options", "value": "nosniff"},
                    {"key": "X-Frame-Options", "value": "DENY"},
                    {
                        "key": "Content-Security-Policy",
                        "value": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
                    },
                ],
            }
        ],
    }
    files = [{"file": "vercel.json", "data": json.dumps(config), "encoding": "utf-8"}]
    for source in (root / "app/web").iterdir():
        files.append(
            {
                "file": source.name if source.name == "index.html" else "assets/" + source.name,
                "data": source.read_text(encoding="utf-8"),
                "encoding": "utf-8",
            }
        )
    result = client.post(
        "/v13/deployments",
        json={
            "name": name,
            "project": project_id,
            "target": "production",
            "files": files,
            "projectSettings": {"framework": None, "buildCommand": None, "outputDirectory": None},
        },
    )
    if result.status_code not in (200, 201):
        print(
            "Vercel deployment failed:",
            result.status_code,
            result.json().get("error", {}).get("code"),
        )
        raise SystemExit(1)
    data = result.json()
    bootstrap["vercel_project_id"] = project_id
    bootstrap["vercel_deployment_id"] = data["id"]
    bootstrap["vercel_url"] = "https://" + data["url"]
    path.write_text(json.dumps(bootstrap, indent=2))
    print("Vercel deployment submitted:", bootstrap["vercel_url"])
