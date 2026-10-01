import json
import os
import sys
from pathlib import Path

config = json.loads(Path(".pat/bootstrap.json").read_text())
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DATABASE_URL"] = config["database_url"]

from shared.db import migrate, pool  # noqa: E402

pool.open(wait=True)
migrate()
pool.close()
print("Production migrations applied successfully.")
