"""Book on-chain pool payouts as mining income."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from ledger.connectors.chain import ChainWatcher
from ledger.prices import PriceService
from spine import db


@dataclass
class ImportResult:
    wallet: str
    new: int
    skipped: int
    btc: Decimal
    usd: Decimal


def import_payouts(
    con, wallet: str, address: str, source: str, watcher: ChainWatcher, prices: PriceService
) -> ImportResult:
    new = skipped = 0
    btc = usd = Decimal(0)
    for p in watcher.payouts(address):
        fmv = (p.qty_btc * prices.usd_at(p.ts)).quantize(Decimal("0.01"), ROUND_HALF_UP)
        added = db.insert_income(
            con,
            id=p.id,
            ts=p.ts,
            wallet=wallet,
            source=source,
            qty=p.qty_btc,
            fmv_usd=fmv,
            coinbase=p.coinbase,
        )
        if added:
            new += 1
            btc += p.qty_btc
            usd += fmv
        else:
            skipped += 1
    return ImportResult(wallet, new, skipped, btc, usd)
