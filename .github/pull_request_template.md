Closes #

## What changed

## Checklist

- [ ] `uv run pytest -q` passes
- [ ] `uv run ruff check . && uv run ruff format --check .` passes
- [ ] New behavior has tests (no network)
- [ ] No private data (addresses, balances, pool accounts, keys, tax docs)
- [ ] Money and BTC math uses `Decimal`
- [ ] Tax logic cites its source; rates live in config or rules files
