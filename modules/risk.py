from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from shared.errors import DomainError

IST = ZoneInfo("Asia/Kolkata")


def market_session(now):
    india = now.astimezone(IST)
    return india.weekday() < 5 and (9, 15) <= (india.hour, india.minute) < (15, 30)


def validate(
    intent, controls, broker, quote, position_value, daily_value, open_count, config, now=None
):
    now = now or datetime.now(timezone.utc)
    risk = controls["risk"]
    checks = [
        (not controls["kill_switch"], "Kill switch blocks new submissions"),
        (config.execution_mode != "DISABLED", "Execution is disabled"),
        (broker["enabled"], "Broker is disabled"),
        (intent["broker"] in risk["allowed_brokers"], "Broker is outside the allowed universe"),
        (
            intent["account_id"] == broker["account_id"]
            and intent["account_id"] in risk["allowed_accounts"],
            "Account mapping is not approved",
        ),
        (
            intent["symbol"] in risk["allowed_instruments"],
            "Instrument is outside the allowed universe",
        ),
        (quote is not None, "Market price is missing"),
        (0 < intent["quantity"] <= risk["max_quantity"], "Quantity exceeds risk limit"),
        (open_count < risk["max_open_orders"], "Open order limit reached"),
    ]
    if quote:
        price = Decimal(str(quote["price"]))
        value = price * intent["quantity"]
        if intent.get("limit_price") is not None:
            value = max(price, Decimal(str(intent["limit_price"]))) * intent["quantity"]
        checks.extend(
            [
                (price > 0, "Market price is invalid"),
                (
                    0
                    <= (now - quote["updated_at"]).total_seconds()
                    <= risk["max_quote_age_seconds"],
                    "Market price is stale or future dated",
                ),
                (value <= Decimal(str(risk["max_order_value"])), "Order value exceeds risk limit"),
                (
                    value + position_value <= Decimal(str(risk["max_position_value"])),
                    "Position value exceeds risk limit",
                ),
                (
                    value + daily_value <= Decimal(str(risk["max_daily_capital"])),
                    "Daily capital limit reached",
                ),
                (value <= broker["cash"], "Insufficient available cash"),
            ]
        )
    if config.execution_mode == "LIVE":
        checks.extend(
            [
                (config.environment == "deployed", "Local live execution is forbidden"),
                (
                    bool(config.approved_outbound_ip)
                    and config.approved_outbound_ip == config.verified_outbound_ip,
                    "Approved static outbound IP is not verified",
                ),
                (
                    config.deployment_ack == "I_ACKNOWLEDGE_REAL_MONEY_EXECUTION",
                    "Deployment acknowledgement is missing",
                ),
                (controls["live_armed"], "Live execution is disarmed"),
                (intent["broker"] != "DUMMY", "Dummy broker cannot route live execution"),
            ]
        )
    else:
        checks.append((intent["broker"] == "DUMMY", "Live brokers require guarded LIVE execution"))
    if risk["market_hours_only"] and intent["broker"] != "DUMMY":
        checks.append((market_session(now), "Outside Indian market session"))
    for approved, reason in checks:
        if not approved:
            raise DomainError(reason, "RISK_REJECTION", 409)
