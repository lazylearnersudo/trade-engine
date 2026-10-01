import concurrent.futures
import json
from pathlib import Path
from urllib.parse import quote

import psycopg

path = Path(".pat/bootstrap.json")
config = json.loads(path.read_text())


def probe(region):
    host = f"aws-0-{region}.pooler.supabase.com"
    try:
        with psycopg.connect(
            host=host,
            port=5432,
            user="postgres." + config["project_ref"],
            password=config["database_password"],
            dbname="postgres",
            sslmode="require",
            connect_timeout=8,
        ) as conn:
            conn.execute("SELECT 1")
        return host
    except psycopg.Error:
        return None


with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
    results = list(
        executor.map(
            probe,
            [
                "ap-south-1",
                "ap-south-2",
                "ap-southeast-1",
                "ap-southeast-2",
                "us-east-1",
                "eu-central-1",
            ],
        )
    )
hosts = [host for host in results if host]
if hosts:
    config["database_url"] = (
        f"postgresql://postgres.{config['project_ref']}:{quote(config['database_password'], safe='')}@{hosts[0]}:5432/postgres?sslmode=require"
    )
    path.write_text(json.dumps(config, indent=2))
    print("Supabase database connection verified; bootstrap updated.")
else:
    print("No verified session-pooler endpoint found.")
