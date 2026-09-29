import json
from datetime import date, datetime
from decimal import Decimal as D
from pathlib import Path

import duckdb

from ledger.connectors.chain import payouts_from_txs
from ledger.importer import import_payouts
from ledger.prices import parse_historical_price
from ledger.simulator import TaxRates, simulate_sale
from spine import LotEngine, Method, db

FIX = Path(__file__).parent / "fixtures"
ADDR = "bc1qexamplepayoutaddress0000000000000000000"


def mem():
    con = duckdb.connect(":memory:")
    db.init(con)
    return con


def test_parse_price():
    assert parse_historical_price(
        {"prices": [{"time": 1757998800, "USD": 115536}], "exchangeRates": {}}
    ) == D("115536")


def test_payouts_from_txs_skips_unconfirmed_and_other_outputs():
    txs = json.loads((FIX / "address_txs.json").read_text())
    p = payouts_from_txs(txs, ADDR)
    assert [x.id for x in p] == ["tx02:0", "cb01:1"]
    assert p[1].coinbase and not p[0].coinbase
    assert p[1].qty_btc == D("0.00012345")


class FakeWatcher:
    def payouts(self, address):
        return payouts_from_txs(json.loads((FIX / "address_txs.json").read_text()), address)


class FakePrices:
    def usd_at(self, ts):
        return D("100000")


def test_import_dedupes_and_replays():
    con = mem()
    db.upsert_wallet(con, "payout", "self_custody", ADDR, "fifo")
    r1 = import_payouts(con, "payout", ADDR, "ocean", FakeWatcher(), FakePrices())
    r2 = import_payouts(con, "payout", ADDR, "ocean", FakeWatcher(), FakePrices())
    assert (r1.new, r2.new, r2.skipped) == (2, 0, 2)
    assert r1.usd == D("12.35") + D("50.00")
    engine, realized = db.replay(con)
    assert engine.balance("payout") == D("0.00062345")
    assert realized == []


def test_replay_applies_transfers_and_disposals_in_order():
    con = mem()
    db.upsert_wallet(con, "a", "self_custody")
    db.upsert_wallet(con, "b", "exchange", method="hifo")
    db.insert_income(
        con,
        id="i1",
        ts=datetime(2025, 1, 1),
        wallet="a",
        source="t",
        qty=D("0.01"),
        fmv_usd=D("900"),
    )
    db.insert_income(
        con,
        id="i2",
        ts=datetime(2025, 2, 1),
        wallet="a",
        source="t",
        qty=D("0.01"),
        fmv_usd=D("1200"),
    )
    con.execute("INSERT INTO transfers VALUES ('t1', '2025-03-01', 'a', 'b', 'BTC', 0.02, 0)")
    con.execute(
        "INSERT INTO disposals VALUES ('d1', '2026-06-01', 'b', 'BTC', 0.01, 1000, 0, NULL)"
    )
    engine, realized = db.replay(con)
    assert len(realized) == 1 and realized[0].basis_usd == D("1200")  # HIFO on wallet b
    assert engine.balance("b") == D("0.01")


def test_simulator_splits_terms_and_estimates_tax():
    e = LotEngine()
    e.add_lot("w", date(2024, 1, 1), D("0.01"), D("500"))  # long
    e.add_lot("w", date(2026, 6, 1), D("0.01"), D("1000"))  # short
    rates = TaxRates(federal_ordinary=D("0.24"), federal_ltcg=D("0.15"), state=D("0.03"))
    r = simulate_sale(e, "w", D("0.02"), D("110000"), date(2026, 9, 28), rates, method=Method.FIFO)
    assert r.long_gain == D("600.00") and r.short_gain == D("100.00")
    assert r.federal_tax == D("114.00")  # 600*.15 + 100*.24
    assert r.state_tax == D("21.00")
    assert e.balance("w") == D("0.02")  # real book untouched
