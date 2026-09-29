"""Thin pool clients used to label payouts and pull hashrate.

Response shapes are not formally documented by either pool, so these return raw JSON.
Pin down the fields you rely on with a fixture test the first time you call them.
"""

from __future__ import annotations

from typing import Protocol

import httpx


class PoolConnector(Protocol):
    name: str

    def stats(self, address: str) -> dict: ...


class OceanPool:
    """OCEAN (TIDES). Public, no key. Paths from Tether's MiningOS OCEAN worker."""

    name = "ocean"
    base = "https://api.ocean.xyz/v1"

    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=20)

    def _get(self, path: str) -> dict:
        r = self.client.get(f"{self.base}/{path}")
        r.raise_for_status()
        return r.json()

    def stats(self, address: str) -> dict:
        return self._get(f"user_hashrate/{address}")

    def workers(self, address: str) -> dict:
        return self._get(f"user_hashrate_full/{address}")

    def earnings(self, address: str, since_epoch: int) -> dict:
        return self._get(f"earnpay/{address}/{since_epoch}")

    def monthly_report(self, address: str, month: str) -> dict:
        """month like '2026-09'."""
        return self._get(f"monthly_earnings_report/{address}/{month}")


class BasedMiningPool:
    """BasedMining. Free JSON endpoints behind the site (no official docs yet).

    Paid x402 endpoints (worker-status etc., $0.01 each in USDC on Base) are listed at
    https://basedmining.xyz/.well-known/x402 and are not called here.
    """

    name = "basedmining"
    base = "https://basedmining.xyz/api"

    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=20)

    def _get(self, path: str, **params) -> dict:
        r = self.client.get(f"{self.base}/{path}", params=params or None)
        r.raise_for_status()
        return r.json()

    def pool_stats(self) -> dict:
        return self._get("pool-stats")

    def bitcoin_status(self) -> dict:
        return self._get("bitcoin/status")

    def participations(self) -> dict:
        """Keyed by BTC address (or EVM wallet for NFT holders): blocks_participated,
        total_diff, share_count, best_share, tier_name, nft_count. Checked 2026-09-28."""
        return self._get("pool/participations")

    def stats(self, address: str) -> dict:
        pool = self.pool_stats().get("pool", {})
        return {"pool": pool, "yours": self.participations().get(address)}


class BtcPowLabPool:
    """BTC PoW Lab public per-address mining summary. No key required.

    The endpoint reports observed Stratum work and connection state. It does not
    imply that a block, reward, or payout is guaranteed.
    """

    name = "btcpowlab"
    base = "https://btcpowlab-pool.com/public/v1"

    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=20)

    def _get(self, path: str) -> dict:
        r = self.client.get(f"{self.base}/{path}")
        r.raise_for_status()
        return r.json()

    def stats(self, address: str) -> dict:
        return self._get(f"miner/{address}/summary")

    def connection(self, address: str) -> dict:
        return self._get(f"miner/{address}/connection")


POOLS: dict[str, type] = {
    "ocean": OceanPool,
    "basedmining": BasedMiningPool,
    "btcpowlab": BtcPowLabPool,
}
