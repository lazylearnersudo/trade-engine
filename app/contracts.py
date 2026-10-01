from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Contract):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class Recovery(Contract):
    email: str = Field(min_length=1, max_length=254)


class PasswordReset(Contract):
    token: str = Field(min_length=1, max_length=4096)
    password: str = Field(min_length=10, max_length=256)


class StrategyInput(Contract):
    name: str = Field(min_length=1, max_length=100)
    broker: Literal["DUMMY", "DHAN", "FYERS", "SHOONYA", "ZERODHA"] = "DUMMY"
    account_id: str = Field(default="paper", min_length=1, max_length=100)
    symbol: str = Field(default="NIFTYBEES", pattern=r"^[A-Z0-9_-]{1,40}$")
    budget: Decimal = Field(gt=0, le=1000000, decimal_places=2)
    limit_price: Decimal | None = Field(default=None, gt=0, le=1000000, decimal_places=4)
    enabled: bool = False
    schedule_time: str | None = Field(
        default=None, pattern=r"^(?:09:(?:[1-5][0-9])|1[0-4]:[0-5][0-9]|15:[0-2][0-9])$"
    )


class RunInput(Contract):
    idempotency_key: str = Field(min_length=1, max_length=150)


class RiskInput(Contract):
    max_order_value: float = Field(gt=0, le=10000000)
    max_quantity: int = Field(gt=0, le=100000)
    max_position_value: float = Field(gt=0, le=10000000)
    max_daily_capital: float = Field(gt=0, le=10000000)
    max_open_orders: int = Field(gt=0, le=100)
    max_quote_age_seconds: int = Field(gt=0, le=300)
    allowed_instruments: list[str] = Field(min_length=1, max_length=100)
    allowed_brokers: list[Literal["DUMMY", "DHAN", "FYERS", "SHOONYA", "ZERODHA"]] = Field(
        min_length=1
    )
    allowed_accounts: list[str] = Field(min_length=1, max_length=100)
    market_hours_only: bool = True


class ControlsInput(Contract):
    kill_switch: bool


class BrokerInput(Contract):
    enabled: bool
    scenario: Literal["NORMAL", "REJECT", "PARTIAL", "OUTAGE", "AMBIGUOUS"] = "NORMAL"
    cash: Decimal | None = Field(default=None, ge=0, le=10000000, decimal_places=2)


class QuoteInput(Contract):
    price: Decimal = Field(gt=0, le=1000000, decimal_places=4)


class UserInput(Login):
    password: str = Field(min_length=10, max_length=256)
    role: Literal["USER", "ADMIN", "SUPERUSER"] = "USER"


class RoleInput(Contract):
    role: Literal["USER", "ADMIN", "SUPERUSER"]
