from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_FLOOR
from zoneinfo import ZoneInfo

from shared.errors import DomainError

IST = ZoneInfo("Asia/Kolkata")


def order_intent(strategy, quote):
    if not quote:
        raise DomainError("Market price is missing", "RISK_REJECTION", 409)
    price = Decimal(str(quote["price"]))
    reference = max(price, strategy.get("limit_price") or price)
    quantity = int((strategy["budget"] / reference).to_integral_value(rounding=ROUND_FLOOR))
    if quantity < 1:
        raise DomainError("Budget cannot buy one unit", "RISK_REJECTION", 409)
    return {
        "broker": strategy["broker"],
        "account_id": strategy["account_id"],
        "symbol": strategy["symbol"],
        "side": "BUY",
        "quantity": quantity,
        "order_type": "LIMIT" if strategy.get("limit_price") else "MARKET",
        "limit_price": strategy.get("limit_price"),
    }


def scheduled_slot(strategy, now=None, grace_minutes=5):
    now = (now or datetime.now(timezone.utc)).astimezone(IST)
    if not strategy["enabled"] or not strategy["schedule_time"] or now.weekday() >= 5:
        return None
    hour, minute = map(int, strategy["schedule_time"].split(":"))
    due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if timedelta(0) <= now - due <= timedelta(minutes=grace_minutes):
        return f"schedule:{strategy['id']}:{due.isoformat()}"
    return None


def next_run(strategy, now=None):
    if not strategy["enabled"] or not strategy["schedule_time"]:
        return None
    now = (now or datetime.now(timezone.utc)).astimezone(IST)
    hour, minute = map(int, strategy["schedule_time"].split(":"))
    due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if due <= now:
        due += timedelta(days=1)
    while due.weekday() >= 5:
        due += timedelta(days=1)
    return due.astimezone(timezone.utc)
