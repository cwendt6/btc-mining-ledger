"""Chain watcher: the source of truth for pool payouts.

BasedMining and OCEAN both pay straight to your BTC address, so every confirmed output
paid to a payout address is booked as mining income at that moment's price.
Pool APIs are only used to label and cross-check these payouts.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import httpx

SATS = Decimal(100_000_000)


@dataclass(frozen=True)
class Payout:
    id: str  # txid:vout, the dedupe key
    txid: str
    vout: int
    address: str
    ts: datetime
    qty_btc: Decimal
    coinbase: bool


def payouts_from_txs(txs: list[dict], address: str) -> list[Payout]:
    """Confirmed outputs paid to `address`. Unconfirmed txs are skipped until they confirm."""
    out = []
    for tx in txs:
        status = tx.get("status", {})
        if not status.get("confirmed"):
            continue
        is_cb = any(v.get("is_coinbase") for v in tx.get("vin", []))
        ts = datetime.fromtimestamp(status["block_time"], tz=UTC).replace(tzinfo=None)
        for n, vo in enumerate(tx.get("vout", [])):
            if vo.get("scriptpubkey_address") == address:
                out.append(
                    Payout(
                        id=f"{tx['txid']}:{n}",
                        txid=tx["txid"],
                        vout=n,
                        address=address,
                        ts=ts,
                        qty_btc=Decimal(vo["value"]) / SATS,
                        coinbase=is_cb,
                    )
                )
    return out


class ChainWatcher:
    def __init__(self, base_url: str = "https://mempool.space", client: httpx.Client | None = None):
        self.base = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=20)

    def _pages(self, address: str) -> Iterator[list[dict]]:
        r = self.client.get(f"{self.base}/api/address/{address}/txs")
        r.raise_for_status()
        page = r.json()
        while page:
            yield page
            confirmed = [t for t in page if t.get("status", {}).get("confirmed")]
            if len(confirmed) < 25:  # mempool returns 25 confirmed per page
                return
            last = confirmed[-1]["txid"]
            r = self.client.get(f"{self.base}/api/address/{address}/txs/chain/{last}")
            r.raise_for_status()
            page = r.json()

    def payouts(self, address: str) -> list[Payout]:
        seen: dict[str, Payout] = {}
        for page in self._pages(address):
            for p in payouts_from_txs(page, address):
                seen[p.id] = p
        return sorted(seen.values(), key=lambda p: p.ts)
