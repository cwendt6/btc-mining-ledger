-- The spine: events are the source of truth. Lots are rebuilt by replaying them in order.

CREATE TABLE IF NOT EXISTS wallets (
    name        TEXT PRIMARY KEY,           -- e.g. 'payout-ocean', 'cold', 'coinbase'
    kind        TEXT NOT NULL,              -- pool | exchange | self_custody
    chain       TEXT NOT NULL DEFAULT 'bitcoin',
    address     TEXT,                       -- payout address for chain-watched wallets
    method      TEXT NOT NULL DEFAULT 'fifo' -- fifo | hifo | spec_id
);

CREATE TABLE IF NOT EXISTS prices (
    asset   TEXT NOT NULL,
    ts      TIMESTAMP NOT NULL,
    usd     DECIMAL(18, 2) NOT NULL,
    source  TEXT NOT NULL,
    PRIMARY KEY (asset, ts)
);

CREATE TABLE IF NOT EXISTS income_events (
    id        TEXT PRIMARY KEY,             -- txid:vout for on-chain payouts (dedupe key)
    ts        TIMESTAMP NOT NULL,
    wallet    TEXT NOT NULL,
    source    TEXT NOT NULL,                -- basedmining | ocean | f2pool | manual
    asset     TEXT NOT NULL DEFAULT 'BTC',
    qty       DECIMAL(20, 8) NOT NULL,
    fmv_usd   DECIMAL(18, 2) NOT NULL,      -- ordinary income AND the new lot's basis
    kind      TEXT NOT NULL DEFAULT 'mining',
    coinbase  BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS purchases (
    id        TEXT PRIMARY KEY,
    ts        TIMESTAMP NOT NULL,
    wallet    TEXT NOT NULL,
    asset     TEXT NOT NULL DEFAULT 'BTC',
    qty       DECIMAL(20, 8) NOT NULL,
    cost_usd  DECIMAL(18, 2) NOT NULL       -- includes fees
);

CREATE TABLE IF NOT EXISTS transfers (
    id          TEXT PRIMARY KEY,           -- txid
    ts          TIMESTAMP NOT NULL,
    from_wallet TEXT NOT NULL,
    to_wallet   TEXT NOT NULL,
    asset       TEXT NOT NULL DEFAULT 'BTC',
    qty         DECIMAL(20, 8) NOT NULL,
    fee_qty     DECIMAL(20, 8) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS disposals (
    id           TEXT PRIMARY KEY,
    ts           TIMESTAMP NOT NULL,
    wallet       TEXT NOT NULL,
    asset        TEXT NOT NULL DEFAULT 'BTC',
    qty          DECIMAL(20, 8) NOT NULL,
    proceeds_usd DECIMAL(18, 2) NOT NULL,
    fees_usd     DECIMAL(18, 2) NOT NULL DEFAULT 0,
    lot_ids      TEXT                       -- comma list, only for spec_id
);

CREATE TABLE IF NOT EXISTS expenses (
    id        TEXT PRIMARY KEY,
    dt        DATE NOT NULL,
    category  TEXT NOT NULL,                -- power | hosting | pool_fee | internet | software | other
    amount    DECIMAL(18, 2) NOT NULL,
    memo      TEXT
);

CREATE TABLE IF NOT EXISTS fixed_assets (
    id                 TEXT PRIMARY KEY,
    item               TEXT NOT NULL,       -- e.g. 'Avalon Nano 3S'
    cost_usd           DECIMAL(18, 2) NOT NULL,
    placed_in_service  DATE NOT NULL,
    method             TEXT NOT NULL DEFAULT 'bonus'  -- bonus | sec179 | macrs5
);
