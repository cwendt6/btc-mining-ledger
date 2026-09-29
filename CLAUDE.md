# btc-mining-ledger

Read ../CLAUDE.md first for workspace rules.

## Commands

- Setup: `uv venv && uv pip install -e ".[dev,app]"`
- Test: `uv run pytest -q`
- Lint: `uv run ruff check . && uv run ruff format --check .`
- Demo (synthetic data): `uv run ledger demo`
- Dashboard: `uv run streamlit run app/streamlit_app.py`
- Real config lives at `../data/ledger.toml` (LEDGER_CONFIG env var overrides). Never read real config in tests.

## Design

- Events are the source of truth (income_events, purchases, transfers, disposals, expenses, fixed_assets in `src/spine/schema.sql`). Lots are never stored; `spine.db.replay()` rebuilds them in time order.
- `spine` is shared by other repos (tax-planner, onchain-desk). Keep it free of ledger-specific code and CLI imports. Breaking changes to spine need a version bump and a note in STATUS.md.
- Lots are per wallet (Rev. Proc. 2024-28). Method (fifo, hifo, spec_id) is set per wallet. Transfers carry basis and acquisition date; fee basis is added to the received lots (documented choice, revisit if law changes).
- Holding period: long term only if disposed after the one-year anniversary (`holding_term`).
- Chain watcher is the income source of truth: confirmed outputs to payout addresses, dedupe key `txid:vout`, priced via mempool `historical-price`. Pool APIs only label and cross-check.
- Pool API shapes are undocumented. Any field you rely on gets a fixture test in `tests/fixtures/`.
- Tests never hit the network. Use fixtures and fakes (see tests/test_ledger.py).
