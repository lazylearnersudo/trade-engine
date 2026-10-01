from psycopg.types.json import Jsonb


def audit(conn, actor, action, entity_id=None, outcome="OK", details=None):
    conn.execute(
        "INSERT INTO trade.audit(actor,action,entity_id,outcome,details) VALUES (%s,%s,%s,%s,%s)",
        (actor, action, entity_id, outcome, Jsonb(details or {})),
    )
