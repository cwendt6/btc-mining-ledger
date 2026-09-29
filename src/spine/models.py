"""Core records shared by every repo that uses the spine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum


class Method(StrEnum):
    """Lot relief method. Set per wallet per tax year (Rev. Proc. 2024-28)."""

    FIFO = "fifo"
    HIFO = "hifo"
    SPEC_ID = "spec_id"


class Origin(StrEnum):
    MINED = "mined"
    BOUGHT = "bought"
    REWARD = "reward"
    TRANSFER = "transfer"


class Term(StrEnum):
    SHORT = "short"
    LONG = "long"


@dataclass
class Lot:
    id: str
    wallet: str
    asset: str
    acquired_on: date
    qty: Decimal
    basis_usd: Decimal  # total basis for the original qty
    origin: Origin = Origin.BOUGHT
    remaining: Decimal = field(default=Decimal("-1"))

    def __post_init__(self) -> None:
        if self.remaining == Decimal("-1"):
            self.remaining = self.qty

    @property
    def unit_basis(self) -> Decimal:
        return self.basis_usd / self.qty if self.qty else Decimal(0)

    @property
    def remaining_basis(self) -> Decimal:
        return self.unit_basis * self.remaining


@dataclass(frozen=True)
class LotRelief:
    """One lot's share of a disposal. This is one line on Form 8949."""

    lot_id: str
    acquired_on: date
    disposed_on: date
    qty: Decimal
    basis_usd: Decimal
    proceeds_usd: Decimal
    term: Term

    @property
    def gain_usd(self) -> Decimal:
        return self.proceeds_usd - self.basis_usd
