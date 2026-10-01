"""Broker capability boundary. Unverified live execution is explicitly unavailable."""

import json
from dataclasses import dataclass
from pathlib import Path

import httpx

from shared.config import settings
from shared.errors import DomainError


@dataclass(frozen=True)
class FillResult:
    status: str
    filled_quantity: int
    broker_order_id: str
    reason: str | None = None


class DummyBroker:
    capabilities = {
        "quotes": True,
        "place": True,
        "cancel": True,
        "modify": False,
        "positions": True,
        "reconcile": True,
    }

    def place(self, order, scenario):
        broker_id = "paper-" + order["id"]
        if scenario == "OUTAGE":
            raise DomainError("Dummy broker unavailable", "BROKER_UNAVAILABLE", 503)
        if scenario == "AMBIGUOUS":
            return FillResult("AMBIGUOUS", 0, broker_id, "Submission outcome unknown; do not retry")
        if scenario == "REJECT":
            return FillResult("REJECTED", 0, broker_id, "Configured broker rejection")
        if order["order_type"] == "LIMIT" and order["limit_price"] < order["price"]:
            return FillResult("OPEN", 0, broker_id)
        quantity = order["quantity"]
        if scenario == "PARTIAL" and quantity > 1:
            return FillResult("PARTIAL", max(1, quantity // 2), broker_id)
        return FillResult("FILLED", quantity, broker_id)


class LiveBroker:
    capabilities = {
        "quotes": False,
        "place": False,
        "cancel": False,
        "modify": False,
        "positions": False,
        "reconcile": False,
        "profile": True,
    }

    def __init__(self, name):
        self.name = name

    def place(self, order, scenario=None):
        raise DomainError(
            f"{self.name} order adapter has not passed account contract validation",
            "CONFIGURATION",
            409,
        )

    def credentials(self):
        if not settings.broker_credentials_file:
            return {}
        try:
            return json.loads(Path(settings.broker_credentials_file).read_text()).get(self.name, {})
        except (OSError, ValueError):
            raise DomainError("Broker credential file is invalid", "CONFIGURATION", 503) from None

    def check_connection(self):
        credentials = self.credentials()
        token = credentials.get("access_token")
        if not token:
            return {"status": "UNCONFIGURED", "reason": "Access token is missing"}
        if self.name == "DHAN":
            url, headers = "https://api.dhan.co/v2/profile", {"access-token": token}
        elif self.name == "ZERODHA" and credentials.get("api_key"):
            url = "https://api.kite.trade/user/profile"
            headers = {
                "Authorization": f"token {credentials['api_key']}:{token}",
                "X-Kite-Version": "3",
            }
        elif self.name == "FYERS" and credentials.get("app_id"):
            url = "https://api-t1.fyers.in/api/v3/profile"
            headers = {"Authorization": f"{credentials['app_id']}:{token}"}
        else:
            return {
                "status": "DISABLED",
                "reason": "Account-specific OAuth adapter validation pending",
            }
        try:
            result = httpx.get(url, headers=headers, timeout=10)
            if result.status_code != 200:
                return {"status": "DEGRADED", "reason": "Broker session unavailable or expired"}
            data = result.json()
            if data.get("s") == "error" or data.get("status") == "error" or data.get("errorType"):
                return {"status": "DEGRADED", "reason": "Broker rejected profile request"}
            return {
                "status": "CONNECTED_READ_ONLY",
                "reason": "Profile verified; order routing disabled",
            }
        except (httpx.HTTPError, ValueError):
            return {"status": "DEGRADED", "reason": "Broker profile check unavailable"}


def adapter(name):
    return DummyBroker() if name == "DUMMY" else LiveBroker(name)
