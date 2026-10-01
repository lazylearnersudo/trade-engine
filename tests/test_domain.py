from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.contracts import StrategyInput

from modules.broker import DummyBroker, LiveBroker
from modules.risk import market_session, validate
from modules.strategy import order_intent, scheduled_slot
from shared.config import Settings
from shared.errors import DomainError

NOW = datetime(2026, 10, 1, 5, 0, tzinfo=timezone.utc)


def inputs():
    intent = {"broker": "DUMMY", "account_id": "paper", "symbol": "NIFTYBEES", "quantity": 10}
    controls = {
        "kill_switch": False,
        "live_armed": False,
        "risk": {
            "max_quantity": 100,
            "max_order_value": 10000,
            "max_position_value": 50000,
            "max_daily_capital": 25000,
            "max_open_orders": 5,
            "max_quote_age_seconds": 30,
            "allowed_instruments": ["NIFTYBEES"],
            "allowed_brokers": ["DUMMY"],
            "allowed_accounts": ["paper"],
            "market_hours_only": True,
        },
    }
    broker = {"enabled": True, "account_id": "paper", "cash": Decimal("100000")}
    quote = {"price": Decimal("250"), "updated_at": NOW}
    return intent, controls, broker, quote


def test_risk_approves_dummy():
    validate(*inputs(), Decimal(0), Decimal(0), 0, Settings(), NOW)


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("max_order_value", 100, "Order value"),
        ("max_quantity", 1, "Quantity"),
        ("max_daily_capital", 100, "Daily capital"),
        ("max_position_value", 100, "Position value"),
    ],
)
def test_risk_limits(field, value, match):
    intent, controls, broker, quote = inputs()
    controls["risk"][field] = value
    with pytest.raises(DomainError, match=match):
        validate(intent, controls, broker, quote, Decimal(0), Decimal(0), 0, Settings(), NOW)


@pytest.mark.parametrize("offset", [-31, 1])
def test_stale_or_future_quote(offset):
    intent, controls, broker, quote = inputs()
    quote["updated_at"] = NOW + timedelta(seconds=offset)
    with pytest.raises(DomainError, match="stale or future"):
        validate(intent, controls, broker, quote, Decimal(0), Decimal(0), 0, Settings(), NOW)


def test_local_live_forbidden():
    with pytest.raises(DomainError, match="Local live"):
        validate(*inputs(), Decimal(0), Decimal(0), 0, Settings(execution_mode="LIVE"), NOW)


def test_deployed_live_without_static_ip():
    with pytest.raises(DomainError, match="static outbound IP"):
        validate(
            *inputs(),
            Decimal(0),
            Decimal(0),
            0,
            Settings(environment="deployed", execution_mode="LIVE"),
            NOW,
        )


def test_missing_quote():
    intent, controls, broker, _ = inputs()
    with pytest.raises(DomainError, match="price is missing"):
        validate(intent, controls, broker, None, Decimal(0), Decimal(0), 0, Settings(), NOW)


def test_session_timezone():
    assert market_session(NOW)
    assert not market_session(datetime(2026, 10, 3, 5, tzinfo=timezone.utc))
    assert not market_session(datetime(2026, 10, 1, 10, tzinfo=timezone.utc))


def test_strategy_quantity():
    intent = order_intent(
        {
            "budget": Decimal("2499"),
            "broker": "DUMMY",
            "account_id": "paper",
            "symbol": "NIFTYBEES",
        },
        {"price": 250},
    )
    assert intent["quantity"] == 9


def test_scheduler_grace_and_weekend():
    item = {"id": "a", "enabled": True, "schedule_time": "10:30"}
    assert scheduled_slot(item, NOW)
    assert not scheduled_slot(item, NOW + timedelta(minutes=6))
    assert not scheduled_slot(item, NOW + timedelta(days=2))


def test_dummy_limit_and_partial():
    order = {"id": "1", "quantity": 10, "order_type": "LIMIT", "limit_price": 240, "price": 250}
    assert DummyBroker().place(order, "NORMAL").status == "OPEN"
    order["limit_price"] = 260
    assert DummyBroker().place(order, "PARTIAL").filled_quantity == 5
    assert DummyBroker().place(order, "REJECT").status == "REJECTED"
    assert DummyBroker().place(order, "AMBIGUOUS").status == "AMBIGUOUS"


def test_live_adapters_cannot_place():
    with pytest.raises(DomainError, match="contract validation"):
        LiveBroker("DHAN").place({})


@pytest.mark.parametrize("schedule", ["09:10", "09:14", "15:30"])
def test_schedule_rejects_outside_execution_window(schedule):
    with pytest.raises(ValidationError):
        StrategyInput(name="ETF", budget="2500", schedule_time=schedule)
