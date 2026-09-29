"""DuckDB access for the spine. Real data lives outside the repo (see config.example.toml)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from importlib import resources
from pathlib import Path

import duckdb

from spine.lots import LotEngine
from spine.models import LotRelief, Method, Origin


def connect(path: str | Path) -> duckdb.DuckDBPyConnection:
    Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(Path(path).expanduser()))
    init(con)
    return con


def init(con: duckdb.DuckDBPyConnection) -> None:
    sql = resources.files("spine").joinpath("schema.sql").read_text()
    con.execute(sql)


def upsert_wallet(con, name: str, kind: str, address: str | None = None, method: str = "fifo"):
    con.execute(
        "INSERT OR REPLACE INTO wallets (name, kind, address, method) VALUES (?, ?, ?, ?)",
        [name, kind, address, method],
    )


def insert_income(con, *, id, ts, wallet, source, qty, fmv_usd, coinbase=False, kind="mining"):
    """Insert a payout. Returns False if it was already booked (dedupe on id)."""
    exists = con.execute("SELECT 1 FROM income_events WHERE id = ?", [id]).fetchone()
    if exists:
        return False
    con.execute(
        "INSERT INTO income_events (id, ts, wallet, source, qty, fmv_usd, kind, coinbase) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [id, ts, wallet, source, qty, fmv_usd, kind, coinbase],
    )
    return True


def _d(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def _day(ts) -> date:
    return ts.date() if isinstance(ts, datetime) else ts


def replay(con, as_of: datetime | None = None) -> tuple[LotEngine, list[LotRelief]]:
    """Rebuild every lot from events in time order. Returns the engine and all realized reliefs."""
    methods = dict(con.execute("SELECT name, method FROM wallets").fetchall())
    cutoff = as_of or datetime.max
    events = con.execute(
        """
        SELECT ts, 0 AS ord, 'income' AS kind, id, wallet, NULL, qty, fmv_usd, NULL, NULL
          FROM income_events WHERE kind <> 'reward_noncash'
        UNION ALL
        SELECT ts, 0, 'buy', id, wallet, NULL, qty, cost_usd, NULL, NULL FROM purchases
        UNION ALL
        SELECT ts, 1, 'transfer', id, from_wallet, to_wallet, qty, NULL, fee_qty, NULL
          FROM transfers
        UNION ALL
        SELECT ts, 2, 'dispose', id, wallet, NULL, qty, proceeds_usd, fees_usd, lot_ids
          FROM disposals
        ORDER BY 1, 2, 4
        """
    ).fetchall()

    engine = LotEngine()
    realized: list[LotRelief] = []
    for ts, _, kind, eid, wallet, to_wallet, qty, usd, extra, lot_ids in events:
        if ts > cutoff:
            break
        qty = _d(qty)
        if kind in ("income", "buy"):
            origin = Origin.MINED if kind == "income" else Origin.BOUGHT
            engine.add_lot(wallet, _day(ts), qty, _d(usd), origin=origin, lot_id=eid)
        elif kind == "transfer":
            engine.transfer(wallet, to_wallet, qty, fee_qty=_d(extra or 0))
        else:
            method = Method(methods.get(wallet, "fifo"))
            ids = lot_ids.split(",") if lot_ids else None
            realized += engine.dispose(
                wallet, qty, _day(ts), _d(usd), _d(extra or 0), method=method, lot_ids=ids
            )
    return engine, realized
