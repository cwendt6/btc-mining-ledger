"""BTC/USD price at a point in time, from mempool.space or your own self-hosted mempool.

Point MEMPOOL_URL at your node's mempool instance once it's running on the Mac mini;
the API is the same, and your addresses stop leaving your network.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import httpx

DEFAULT_MEMPOOL = "https://mempool.space"


class PriceService:
    def __init__(
        self, con=None, base_url: str = DEFAULT_MEMPOOL, client: httpx.Client | None = None
    ):
        self.con = con
        self.base = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=20)

    def _cached(self, ts: datetime) -> Decimal | None:
        if self.con is None:
            return None
        row = self.con.execute(
            "SELECT usd FROM prices WHERE asset = 'BTC' AND ts = ?", [ts]
        ).fetchone()
        return Decimal(str(row[0])) if row else None

    def usd_at(self, ts: datetime) -> Decimal:
        """Price nearest to `ts` (mempool returns the closest stored point, hourly or daily)."""
        ts = ts.replace(microsecond=0)
        if (hit := self._cached(ts)) is not None:
            return hit
        epoch = int(ts.replace(tzinfo=ts.tzinfo or UTC).timestamp())
        r = self.client.get(
            f"{self.base}/api/v1/historical-price", params={"currency": "USD", "timestamp": epoch}
        )
        r.raise_for_status()
        price = parse_historical_price(r.json())
        if self.con is not None:
            self.con.execute(
                "INSERT OR REPLACE INTO prices VALUES ('BTC', ?, ?, ?)", [ts, price, self.base]
            )
        return price


def parse_historical_price(payload: dict) -> Decimal:
    prices = payload.get("prices") or []
    if not prices or "USD" not in prices[0]:
        raise ValueError(f"unexpected historical-price payload: {payload!r:.200}")
    return Decimal(str(prices[0]["USD"]))
