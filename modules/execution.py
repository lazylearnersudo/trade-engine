import uuid
from datetime import datetime, timezone

from modules import broker, risk, strategy
from modules.auth import authorize_owner
from modules.operations import audit
from shared.config import settings
from shared.db import pool
from shared.errors import DomainError

ACTIVE = ("CREATED", "SUBMITTING", "OPEN", "PARTIAL", "AMBIGUOUS")


def apply_fill(conn, order, quantity):
    if quantity <= 0:
        return
    conn.execute(
        "INSERT INTO trade.fills VALUES (%s,%s,%s,%s,now())",
        (str(uuid.uuid4()), order["id"], quantity, order["price"]),
    )
    conn.execute(
        "INSERT INTO trade.positions(broker,account_id,symbol,owner_id,quantity,average_price) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(broker,account_id,symbol) DO UPDATE SET average_price=(trade.positions.average_price*trade.positions.quantity + excluded.average_price*excluded.quantity)/(trade.positions.quantity+excluded.quantity), quantity=trade.positions.quantity+excluded.quantity, updated_at=now()",
        (
            order["broker"],
            order["account_id"],
            order["symbol"],
            order["owner_id"],
            quantity,
            order["price"],
        ),
    )
    conn.execute(
        "UPDATE trade.brokers SET cash=cash-%s WHERE id=%s",
        (quantity * order["price"], order["broker"]),
    )


def execute(strategy_id, key, user):
    if not key or len(key) > 150:
        raise DomainError("An idempotency key of at most 150 characters is required")
    with pool.connection() as conn:
        # One deployment-wide lock covers risk reservations, fills, controls and schedule retries.
        conn.execute("SELECT pg_advisory_xact_lock(731821)")
        item = conn.execute(
            "SELECT * FROM trade.strategies WHERE id=%s FOR UPDATE", (strategy_id,)
        ).fetchone()
        if not item:
            raise DomainError("Strategy not found", "NOT_FOUND", 404)
        authorize_owner(user, item["owner_id"])
        previous = conn.execute(
            "SELECT * FROM trade.runs WHERE idempotency_key=%s", (key,)
        ).fetchone()
        if previous:
            if previous["strategy_id"] != strategy_id:
                raise DomainError("Idempotency key belongs to another strategy", "CONFLICT", 409)
            return {"run": previous, "duplicate": True}
        run_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO trade.runs(id,strategy_id,idempotency_key,status) VALUES (%s,%s,%s,'STARTED')",
            (run_id, strategy_id, key),
        )
        audit(conn, user["id"], "STRATEGY_RUN", run_id, details={"strategy_id": strategy_id})
        try:
            if not item["enabled"]:
                raise DomainError("Strategy is disabled", "RISK_REJECTION", 409)
            quote = conn.execute(
                "SELECT * FROM trade.quotes WHERE symbol=%s", (item["symbol"],)
            ).fetchone()
            intent = strategy.order_intent(item, quote)
            controls = conn.execute("SELECT * FROM trade.controls WHERE id=1").fetchone()
            account = conn.execute(
                "SELECT * FROM trade.brokers WHERE id=%s", (item["broker"],)
            ).fetchone()
            held = conn.execute(
                "SELECT coalesce(sum(p.quantity*q.price),0) AS value FROM trade.positions p JOIN trade.quotes q ON q.symbol=p.symbol WHERE p.broker=%s AND p.account_id=%s AND p.symbol=%s",
                (item["broker"], item["account_id"], item["symbol"]),
            ).fetchone()["value"]
            reserved = conn.execute(
                "SELECT coalesce(sum((quantity-filled_quantity)*greatest(price,coalesce(limit_price,price))),0) AS value FROM trade.orders WHERE broker=%s AND account_id=%s AND status=ANY(%s)",
                (item["broker"], item["account_id"], list(ACTIVE)),
            ).fetchone()["value"]
            today = (
                datetime.now(timezone.utc)
                .astimezone(risk.IST)
                .replace(hour=0, minute=0, second=0, microsecond=0)
            )
            deployed = conn.execute(
                "SELECT coalesce(sum(CASE WHEN status IN ('OPEN','PARTIAL','AMBIGUOUS','SUBMITTING') THEN quantity*greatest(price,coalesce(limit_price,price)) ELSE filled_quantity*price END),0) AS value FROM trade.orders WHERE created_at>=%s AND broker=%s AND account_id=%s",
                (today, item["broker"], item["account_id"]),
            ).fetchone()["value"]
            open_count = conn.execute(
                "SELECT count(*) AS n FROM trade.orders WHERE status=ANY(%s)", (list(ACTIVE),)
            ).fetchone()["n"]
            account["cash"] -= reserved
            risk.validate(
                intent, controls, account, quote, held + reserved, deployed, open_count, settings
            )
            audit(conn, user["id"], "RISK_DECISION", run_id, "APPROVED")
            order = {
                **intent,
                "id": str(uuid.uuid4()),
                "price": quote["price"],
                "owner_id": item["owner_id"],
            }
            conn.execute(
                "INSERT INTO trade.orders(id,run_id,strategy_id,owner_id,broker,account_id,symbol,side,quantity,price,order_type,limit_price,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'SUBMITTING')",
                (
                    order["id"],
                    run_id,
                    strategy_id,
                    item["owner_id"],
                    order["broker"],
                    order["account_id"],
                    order["symbol"],
                    order["side"],
                    order["quantity"],
                    order["price"],
                    order["order_type"],
                    order["limit_price"],
                ),
            )
            result = broker.adapter(item["broker"]).place(order, account["scenario"])
            conn.execute(
                "UPDATE trade.orders SET status=%s,filled_quantity=%s,broker_order_id=%s,reason=%s,updated_at=now() WHERE id=%s",
                (
                    result.status,
                    result.filled_quantity,
                    result.broker_order_id,
                    result.reason,
                    order["id"],
                ),
            )
            apply_fill(conn, order, result.filled_quantity)
            status = (
                "AMBIGUOUS"
                if result.status == "AMBIGUOUS"
                else "REJECTED"
                if result.status == "REJECTED"
                else "COMPLETED"
            )
            reason = result.reason
            audit(
                conn, user["id"], "BROKER_RESPONSE", order["id"], result.status, {"run_id": run_id}
            )
        except DomainError as error:
            status, reason = "REJECTED", error.message
            conn.execute(
                "UPDATE trade.orders SET status='REJECTED',reason=%s WHERE run_id=%s AND status='SUBMITTING'",
                (reason, run_id),
            )
            audit(
                conn, user["id"], "RISK_OR_BROKER_REJECTION", run_id, error.code, {"reason": reason}
            )
        conn.execute(
            "UPDATE trade.runs SET status=%s,reason=%s,finished_at=now() WHERE id=%s",
            (status, reason, run_id),
        )
        conn.execute("UPDATE trade.strategies SET last_run_at=now() WHERE id=%s", (strategy_id,))
        return {
            "run": conn.execute("SELECT * FROM trade.runs WHERE id=%s", (run_id,)).fetchone(),
            "duplicate": False,
        }


def cancel(order_id, user):
    with pool.connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(731821)")
        order = conn.execute(
            "SELECT * FROM trade.orders WHERE id=%s FOR UPDATE", (order_id,)
        ).fetchone()
        if not order:
            raise DomainError("Order not found", "NOT_FOUND", 404)
        authorize_owner(user, order["owner_id"])
        if order["broker"] != "DUMMY" or order["status"] not in ("OPEN", "PARTIAL"):
            raise DomainError("Order cannot be cancelled in its current state", "CONFLICT", 409)
        conn.execute(
            "UPDATE trade.orders SET status='CANCELLED',updated_at=now() WHERE id=%s", (order_id,)
        )
        audit(conn, user["id"], "ORDER_CANCELLED", order_id)
    return {"status": "CANCELLED"}


def reconcile(actor="system"):
    with pool.connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(731821)")
        # Interrupted external submissions remain unknown until broker reconciliation proves an outcome.
        conn.execute(
            "UPDATE trade.orders SET status='AMBIGUOUS',reason='Interrupted submission requires broker reconciliation' WHERE status='SUBMITTING'"
        )
        conn.execute(
            "UPDATE trade.runs SET status='AMBIGUOUS',reason='Interrupted execution requires reconciliation',finished_at=now() WHERE status='STARTED'"
        )
        orders = conn.execute(
            "SELECT * FROM trade.orders WHERE broker='DUMMY' AND status IN ('OPEN','PARTIAL') ORDER BY created_at"
        ).fetchall()
        controls = conn.execute("SELECT kill_switch FROM trade.controls WHERE id=1").fetchone()
        for order in orders:
            # Existing orders may fill with the kill switch on: it only blocks new submissions.
            quote = conn.execute(
                "SELECT * FROM trade.quotes WHERE symbol=%s", (order["symbol"],)
            ).fetchone()
            account = conn.execute("SELECT * FROM trade.brokers WHERE id='DUMMY'").fetchone()
            if not quote or account["scenario"] != "NORMAL":
                continue
            if order["limit_price"] is not None and order["limit_price"] < quote["price"]:
                continue
            remaining = order["quantity"] - order["filled_quantity"]
            if remaining * quote["price"] > account["cash"]:
                continue
            order["price"] = quote["price"]
            apply_fill(conn, order, remaining)
            conn.execute(
                "UPDATE trade.orders SET status='FILLED',filled_quantity=quantity,updated_at=now() WHERE id=%s",
                (order["id"],),
            )
            audit(
                conn,
                actor,
                "ORDER_RECONCILED",
                order["id"],
                "FILLED",
                {"kill_switch": controls["kill_switch"]},
            )
        discrepancies = conn.execute(
            "SELECT p.broker,p.account_id,p.symbol,p.quantity,coalesce(sum(f.quantity),0) AS actual FROM trade.positions p LEFT JOIN trade.orders o ON o.broker=p.broker AND o.account_id=p.account_id AND o.symbol=p.symbol LEFT JOIN trade.fills f ON f.order_id=o.id WHERE p.broker='DUMMY' GROUP BY p.broker,p.account_id,p.symbol,p.quantity HAVING p.quantity<>coalesce(sum(f.quantity),0)"
        ).fetchall()
        conn.execute(
            "UPDATE trade.positions SET reconciliation_status='MATCHED' WHERE broker='DUMMY'"
        )
        for position in discrepancies:
            conn.execute(
                "UPDATE trade.positions SET reconciliation_status='DISCREPANCY' WHERE broker=%s AND account_id=%s AND symbol=%s",
                (position["broker"], position["account_id"], position["symbol"]),
            )
        audit(
            conn,
            actor,
            "RECONCILIATION",
            outcome="DISCREPANCY" if discrepancies else "OK",
            details={"discrepancies": len(discrepancies)},
        )
    return {"discrepancies": discrepancies}
