"""Minimal dashboard. Run: streamlit run app/streamlit_app.py  (needs .[app] extras)."""

import os
import tomllib
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st

from spine import db

cfg_path = Path(os.environ.get("LEDGER_CONFIG", "~/Documents/dev/data/ledger.toml")).expanduser()
cfg = tomllib.loads(cfg_path.read_text())
con = db.connect(cfg["db_path"])
engine, realized = db.replay(con)

st.title("Mining ledger")
price = st.number_input("BTC price (USD)", value=100_000, step=1_000)

lots = engine.open_lots()
btc = sum((lot.remaining for lot in lots), Decimal(0))
basis = engine.basis()
c1, c2, c3 = st.columns(3)
c1.metric("BTC held", f"{btc:.8f}")
c2.metric("Cost basis", f"${basis:,.2f}")
c3.metric("Unrealized gain", f"${btc * Decimal(price) - basis:,.2f}")

income = con.execute(
    "SELECT date_trunc('month', ts) AS month, sum(qty) AS btc, sum(fmv_usd) AS income_usd "
    "FROM income_events GROUP BY 1 ORDER BY 1"
).df()
st.subheader("Mining income by month")
st.bar_chart(income, x="month", y="income_usd")

st.subheader("Open lots")
st.dataframe(
    pd.DataFrame(
        [
            {
                "lot": lot.id,
                "wallet": lot.wallet,
                "acquired": lot.acquired_on,
                "btc": float(lot.remaining),
                "basis_usd": float(lot.remaining_basis),
            }
            for lot in lots
        ]
    )
)
