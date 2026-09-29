"""What if I sell X BTC today? Relieves lots on a copy of the book and estimates the tax.

This is a marginal-rate estimate, not a return. The tax-planner repo will replace these
flat rates with full bracket math from `taxcore`.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from spine import LotEngine, LotRelief, Method, Term

CENT = Decimal("0.01")


@dataclass(frozen=True)
class TaxRates:
    federal_ordinary: Decimal = Decimal("0.24")  # your marginal bracket for short-term gains
    federal_ltcg: Decimal = Decimal("0.15")  # 0 / 15 / 20 depending on taxable income
    niit: Decimal = Decimal("0")  # 0.038 if MAGI is over the NIIT threshold
    state: Decimal = Decimal("0.0295")  # Indiana flat rate; VERIFY each year
    county: Decimal = Decimal("0")  # Indiana county rate for where you live; fill in

    @classmethod
    def from_dict(cls, d: dict) -> TaxRates:
        return cls(**{k: Decimal(str(v)) for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class SaleResult:
    qty: Decimal
    price_usd: Decimal
    proceeds_usd: Decimal
    reliefs: list[LotRelief] = field(default_factory=list)
    short_gain: Decimal = Decimal(0)
    long_gain: Decimal = Decimal(0)
    federal_tax: Decimal = Decimal(0)
    state_tax: Decimal = Decimal(0)

    @property
    def total_tax(self) -> Decimal:
        return self.federal_tax + self.state_tax

    @property
    def after_tax_cash(self) -> Decimal:
        return self.proceeds_usd - self.total_tax


def simulate_sale(
    engine: LotEngine,
    wallet: str,
    qty: Decimal,
    price_usd: Decimal,
    on: date,
    rates: TaxRates | None = None,
    fees_usd: Decimal = Decimal(0),
    method: Method = Method.FIFO,
    lot_ids: list[str] | None = None,
) -> SaleResult:
    rates = rates or TaxRates()
    trial = copy.deepcopy(engine)  # never touch the real book
    proceeds = qty * price_usd
    reliefs = trial.dispose(wallet, qty, on, proceeds, fees_usd, method=method, lot_ids=lot_ids)
    st = sum((r.gain_usd for r in reliefs if r.term is Term.SHORT), Decimal(0))
    lt = sum((r.gain_usd for r in reliefs if r.term is Term.LONG), Decimal(0))
    fed = st * rates.federal_ordinary + lt * rates.federal_ltcg + (st + lt) * rates.niit
    state = (st + lt) * (rates.state + rates.county)
    q = lambda x: x.quantize(CENT, ROUND_HALF_UP)  # noqa: E731
    return SaleResult(
        qty=qty,
        price_usd=price_usd,
        proceeds_usd=q(proceeds - fees_usd),
        reliefs=reliefs,
        short_gain=q(st),
        long_gain=q(lt),
        federal_tax=q(fed),
        state_tax=q(state),
    )


def compare_methods(engine, wallet, qty, price_usd, on, rates=None) -> dict[str, SaleResult]:
    """FIFO vs HIFO side by side. HIFO usually defers the most tax."""
    return {
        m.value: simulate_sale(engine, wallet, qty, price_usd, on, rates, method=m)
        for m in (Method.FIFO, Method.HIFO)
    }
