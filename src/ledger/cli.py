"""`ledger` command line. Run `ledger demo` to see it work on synthetic data."""

from __future__ import annotations

import csv
import os
import tomllib
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb
import typer
from rich.console import Console
from rich.table import Table

from ledger.connectors.chain import ChainWatcher
from ledger.connectors.pools import POOLS
from ledger.importer import import_payouts
from ledger.prices import PriceService
from ledger.simulator import TaxRates, compare_methods, simulate_sale
from spine import Method, db

app = typer.Typer(help="Mining income, cost basis and sell-tax simulator.", no_args_is_help=True)
console = Console()
REPO = Path(__file__).resolve().parents[2]


def load_config(path: str | None) -> dict:
    path = path or os.environ.get("LEDGER_CONFIG") or "~/Documents/dev/data/ledger.toml"
    p = Path(path).expanduser()
    if not p.exists():
        raise typer.BadParameter(f"No config at {p}. Copy config.example.toml there first.")
    return tomllib.loads(p.read_text())


def open_db(cfg: dict):
    con = db.connect(cfg["db_path"])
    for w in cfg.get("wallets", []):
        db.upsert_wallet(con, w["name"], w["kind"], w.get("address"), w.get("method", "fifo"))
    return con


def _money(x: Decimal) -> str:
    return f"-${-x:,.2f}" if x < 0 else f"${x:,.2f}"


@app.command()
def init(config: str = typer.Option(None, help="Path to ledger.toml")):
    """Create the database and register wallets from config."""
    cfg = load_config(config)
    open_db(cfg)
    console.print(f"Ready: {Path(cfg['db_path']).expanduser()}")


@app.command("import")
def import_cmd(config: str = typer.Option(None)):
    """Book new on-chain payouts for every wallet with an address."""
    cfg = load_config(config)
    con = open_db(cfg)
    base = cfg.get("mempool_url", "https://mempool.space")
    watcher, prices = ChainWatcher(base), PriceService(con, base)
    for w in cfg.get("wallets", []):
        if not w.get("address") or "..." in w["address"]:
            continue
        r = import_payouts(con, w["name"], w["address"], w.get("source", "manual"), watcher, prices)
        console.print(
            f"{r.wallet}: {r.new} new payouts ({r.btc} BTC, {_money(r.usd)}), "
            f"{r.skipped} already booked"
        )


def _print_lots(engine, wallet=None):
    t = Table("Lot", "Wallet", "Acquired", "BTC", "Basis", "Unit basis")
    for lot in sorted(engine.open_lots(wallet), key=lambda x: x.acquired_on):
        t.add_row(
            lot.id[:14],
            lot.wallet,
            str(lot.acquired_on),
            f"{lot.remaining:.8f}",
            _money(lot.remaining_basis),
            _money(lot.unit_basis),
        )
    console.print(t)


@app.command()
def lots(wallet: str = typer.Option(None), config: str = typer.Option(None)):
    """Show open lots."""
    engine, _ = db.replay(open_db(load_config(config)))
    _print_lots(engine, wallet)


def _print_sale(label, r):
    console.print(f"\n[bold]{label}[/bold]: sell {r.qty} BTC at {_money(r.price_usd)}")
    t = Table("Lot", "Acquired", "BTC", "Basis", "Proceeds", "Gain", "Term")
    for x in r.reliefs:
        t.add_row(
            x.lot_id[:14],
            str(x.acquired_on),
            f"{x.qty:.8f}",
            _money(x.basis_usd),
            _money(x.proceeds_usd),
            _money(x.gain_usd),
            x.term.value,
        )
    console.print(t)
    console.print(f"Short-term gain {_money(r.short_gain)} | Long-term gain {_money(r.long_gain)}")
    console.print(
        f"Est. federal {_money(r.federal_tax)} + state {_money(r.state_tax)} "
        f"= [bold]{_money(r.total_tax)}[/bold] | after-tax cash "
        f"{_money(r.after_tax_cash)}"
    )


@app.command("sell-sim")
def sell_sim(
    wallet: str = typer.Option(...),
    qty: str = typer.Option(..., help="BTC to sell, e.g. 0.01"),
    price: str = typer.Option(None, help="USD per BTC; defaults to the current price"),
    method: Method = typer.Option(None, help="Override the wallet's method"),
    compare: bool = typer.Option(False, help="Show FIFO vs HIFO side by side"),
    config: str = typer.Option(None),
):
    """What if I sell X BTC today?"""
    cfg = load_config(config)
    con = open_db(cfg)
    engine, _ = db.replay(con)
    rates = TaxRates.from_dict(cfg.get("tax", {}))
    px = (
        Decimal(price)
        if price
        else PriceService(con, cfg.get("mempool_url", "https://mempool.space")).usd_at(
            datetime.now().replace(minute=0, second=0)
        )
    )
    if compare:
        for m, r in compare_methods(engine, wallet, Decimal(qty), px, date.today(), rates).items():
            _print_sale(m.upper(), r)
        return
    wm = {w["name"]: w.get("method", "fifo") for w in cfg.get("wallets", [])}
    m = method or Method(wm.get(wallet, "fifo"))
    _print_sale(
        m.value.upper(),
        simulate_sale(engine, wallet, Decimal(qty), px, date.today(), rates, method=m),
    )


@app.command()
def pool(name: str, address: str):
    """Raw stats from a pool API (ocean | basedmining)."""
    console.print_json(data=POOLS[name]().stats(address))


@app.command()
def demo():
    """Load synthetic payouts into a throwaway database and run a sell simulation."""
    con = duckdb.connect(":memory:")
    db.init(con)
    db.upsert_wallet(con, "demo-payouts", "self_custody", method="fifo")
    with open(REPO / "sample_data" / "payouts.csv") as f:
        for row in csv.DictReader(f):
            qty, px = Decimal(row["qty_btc"]), Decimal(row["btc_usd"])
            db.insert_income(
                con,
                id=row["id"],
                ts=datetime.fromisoformat(row["ts"]),
                wallet="demo-payouts",
                source=row["source"],
                qty=qty,
                fmv_usd=(qty * px).quantize(Decimal("0.01")),
            )
    engine, _ = db.replay(con)
    console.print(
        f"Demo wallet: {engine.balance('demo-payouts')} BTC, "
        f"basis {_money(engine.basis('demo-payouts'))}"
    )
    _print_lots(engine)
    for m, r in compare_methods(
        engine, "demo-payouts", Decimal("0.0005"), Decimal("110000"), date(2026, 9, 28)
    ).items():
        _print_sale(m.upper(), r)


if __name__ == "__main__":
    app()
