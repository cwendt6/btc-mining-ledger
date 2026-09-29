from datetime import date
from decimal import Decimal as D

import pytest

from spine import InsufficientBalance, LotEngine, Method, Term, holding_term


@pytest.fixture
def book():
    e = LotEngine()
    e.add_lot("w", date(2025, 1, 10), D("0.010"), D("900"), lot_id="A")  # $90k
    e.add_lot("w", date(2025, 6, 1), D("0.010"), D("1100"), lot_id="B")  # $110k
    e.add_lot("w", date(2026, 3, 1), D("0.010"), D("800"), lot_id="C")  # $80k
    return e


def test_holding_term_anniversary_is_short():
    assert holding_term(date(2025, 1, 10), date(2026, 1, 10)) is Term.SHORT
    assert holding_term(date(2025, 1, 10), date(2026, 1, 11)) is Term.LONG
    assert holding_term(date(2024, 2, 29), date(2025, 3, 1)) is Term.LONG


def test_fifo_relieves_oldest_first(book):
    r = book.dispose("w", D("0.015"), date(2026, 9, 1), D("1500"), method=Method.FIFO)
    assert [x.lot_id for x in r] == ["A", "B"]
    assert r[0].qty == D("0.010") and r[1].qty == D("0.005")
    assert r[0].basis_usd == D("900") and r[1].basis_usd == D("550")
    assert r[0].term is Term.LONG and r[1].term is Term.LONG
    assert book.balance("w") == D("0.015")


def test_hifo_relieves_highest_basis_first(book):
    r = book.dispose("w", D("0.010"), date(2026, 9, 1), D("1000"), method=Method.HIFO)
    assert [x.lot_id for x in r] == ["B"]
    assert r[0].gain_usd == D("-100")


def test_spec_id(book):
    r = book.dispose(
        "w", D("0.010"), date(2026, 9, 1), D("1000"), method=Method.SPEC_ID, lot_ids=["C"]
    )
    assert r[0].lot_id == "C" and r[0].term is Term.SHORT and r[0].gain_usd == D("200")


def test_fees_reduce_proceeds_pro_rata(book):
    r = book.dispose("w", D("0.020"), date(2026, 9, 1), D("2000"), fees_usd=D("20"))
    assert sum(x.proceeds_usd for x in r) == D("1980")


def test_cannot_oversell(book):
    with pytest.raises(InsufficientBalance):
        book.dispose("w", D("0.031"), date(2026, 9, 1), D("1"))


def test_transfer_keeps_basis_and_dates(book):
    new = book.transfer("w", "cold", D("0.0199"), fee_qty=D("0.0001"))
    assert [lot.acquired_on for lot in new] == [date(2025, 1, 10), date(2025, 6, 1)]
    assert book.balance("cold") == D("0.0199")
    assert book.balance("w") == D("0.010")
    # fee's basis rides along: all $2,000 of A + B basis now sits in cold
    assert book.basis("cold") == D("2000")
    assert book.basis() == D("2800")
