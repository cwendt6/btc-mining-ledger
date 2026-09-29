"""Per-wallet lot engine.

Lots belong to one wallet. Transfers move basis and acquisition dates with the coins.
Disposals relieve lots by FIFO, HIFO or specific ID and return one LotRelief per lot touched.
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from datetime import date
from decimal import Decimal

from spine.models import Lot, LotRelief, Method, Origin, Term

ZERO = Decimal(0)


class InsufficientBalance(ValueError):
    pass


def holding_term(acquired_on: date, disposed_on: date) -> Term:
    """Long term only if held MORE than one year (the anniversary date is still short)."""
    try:
        anniversary = acquired_on.replace(year=acquired_on.year + 1)
    except ValueError:  # Feb 29
        anniversary = acquired_on.replace(year=acquired_on.year + 1, day=28)
    return Term.LONG if disposed_on > anniversary else Term.SHORT


class LotEngine:
    def __init__(self) -> None:
        self._lots: dict[str, list[Lot]] = defaultdict(list)
        self._ids = itertools.count(1)

    # ---- reads -------------------------------------------------------------
    def open_lots(self, wallet: str | None = None, asset: str = "BTC") -> list[Lot]:
        wallets = [wallet] if wallet else list(self._lots)
        return [
            lot
            for w in wallets
            for lot in self._lots.get(w, [])
            if lot.asset == asset and lot.remaining > ZERO
        ]

    def balance(self, wallet: str, asset: str = "BTC") -> Decimal:
        return sum((lot.remaining for lot in self.open_lots(wallet, asset)), ZERO)

    def basis(self, wallet: str | None = None, asset: str = "BTC") -> Decimal:
        return sum((lot.remaining_basis for lot in self.open_lots(wallet, asset)), ZERO)

    # ---- writes ------------------------------------------------------------
    def add_lot(
        self,
        wallet: str,
        acquired_on: date,
        qty: Decimal,
        basis_usd: Decimal,
        origin: Origin = Origin.BOUGHT,
        asset: str = "BTC",
        lot_id: str | None = None,
    ) -> Lot:
        if qty <= ZERO:
            raise ValueError("qty must be positive")
        lot = Lot(
            id=lot_id or f"L{next(self._ids):05d}",
            wallet=wallet,
            asset=asset,
            acquired_on=acquired_on,
            qty=qty,
            basis_usd=basis_usd,
            origin=origin,
        )
        self._lots[wallet].append(lot)
        return lot

    def _ordered(self, wallet: str, asset: str, method: Method, lot_ids: list[str] | None):
        lots = self.open_lots(wallet, asset)
        if method is Method.FIFO:
            return sorted(lots, key=lambda lot: (lot.acquired_on, lot.id))
        if method is Method.HIFO:
            return sorted(lots, key=lambda lot: (-lot.unit_basis, lot.acquired_on, lot.id))
        if not lot_ids:
            raise ValueError("spec_id requires lot_ids")
        by_id = {lot.id: lot for lot in lots}
        missing = [i for i in lot_ids if i not in by_id]
        if missing:
            raise ValueError(f"lots not open in {wallet}: {missing}")
        return [by_id[i] for i in lot_ids]

    def _take(self, wallet, qty, asset, method, lot_ids):
        """Yield (lot, qty_taken, basis_taken) and reduce remaining."""
        if self.balance(wallet, asset) < qty:
            raise InsufficientBalance(
                f"{wallet} holds {self.balance(wallet, asset)} {asset}, need {qty}"
            )
        left = qty
        taken = []
        for lot in self._ordered(wallet, asset, method, lot_ids):
            if left <= ZERO:
                break
            q = min(lot.remaining, left)
            taken.append((lot, q, lot.unit_basis * q))
            lot.remaining -= q
            left -= q
        if left > ZERO:
            raise InsufficientBalance(f"selected lots short by {left} {asset}")
        return taken

    def dispose(
        self,
        wallet: str,
        qty: Decimal,
        disposed_on: date,
        proceeds_usd: Decimal,
        fees_usd: Decimal = ZERO,
        method: Method = Method.FIFO,
        lot_ids: list[str] | None = None,
        asset: str = "BTC",
    ) -> list[LotRelief]:
        """Sell or swap `qty`. Net proceeds (after fees) are split pro rata across lots."""
        net = proceeds_usd - fees_usd
        reliefs = []
        for lot, q, basis in self._take(wallet, qty, asset, method, lot_ids):
            reliefs.append(
                LotRelief(
                    lot_id=lot.id,
                    acquired_on=lot.acquired_on,
                    disposed_on=disposed_on,
                    qty=q,
                    basis_usd=basis,
                    proceeds_usd=net * q / qty,
                    term=holding_term(lot.acquired_on, disposed_on),
                )
            )
        return reliefs

    def transfer(
        self,
        from_wallet: str,
        to_wallet: str,
        qty: Decimal,
        fee_qty: Decimal = ZERO,
        method: Method = Method.FIFO,
        asset: str = "BTC",
    ) -> list[Lot]:
        """Move coins between your own wallets. Not a taxable event.

        The network fee (fee_qty) leaves the sending wallet. Its basis is carried into the
        received lots (add-to-basis treatment). Some advisers treat the fee as a small
        disposal instead; revisit once final IRS guidance or H.R. 10357 settles it.
        """
        new = []
        taken = self._take(from_wallet, qty + fee_qty, asset, method, None)
        moved = ZERO
        for i, (lot, q, basis) in enumerate(taken):
            if i == len(taken) - 1:
                received = qty - moved  # last lot absorbs rounding so totals tie exactly
            else:
                received = (q * qty / (qty + fee_qty)).quantize(Decimal("0.00000001"))
            moved += received
            new.append(
                self.add_lot(
                    wallet=to_wallet,
                    acquired_on=lot.acquired_on,  # holding period follows the coins
                    qty=received,
                    basis_usd=basis,
                    origin=lot.origin,
                    asset=asset,
                )
            )
        return new
