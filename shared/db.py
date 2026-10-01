from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from shared.config import settings

pool = ConnectionPool(
    settings.database_url,
    min_size=1,
    max_size=4,
    open=False,
    kwargs={"row_factory": dict_row},
    timeout=15,
)


def migrate():
    with pool.connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(731820)")
        conn.execute("CREATE TABLE IF NOT EXISTS public.trade_migrations (name text PRIMARY KEY)")
        for path in sorted(Path("migrations").glob("*.sql")):
            if not conn.execute(
                "SELECT 1 FROM public.trade_migrations WHERE name=%s", (path.name,)
            ).fetchone():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute("INSERT INTO public.trade_migrations VALUES (%s)", (path.name,))
