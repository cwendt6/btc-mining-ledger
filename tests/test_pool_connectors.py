import json
from pathlib import Path

import httpx

from ledger.connectors.pools import BtcPowLabPool, POOLS


ADDRESS = "bc1qexamplepayoutaddress0000000000000000000"
FIX = Path(__file__).parent / "fixtures"


def test_btcpowlab_stats_reads_public_address_summary():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/public/v1/miner/{ADDRESS}/summary"
        return httpx.Response(
            200, json=json.loads((FIX / "btcpowlab_summary.json").read_text())
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    stats = BtcPowLabPool(client).stats(ADDRESS)

    assert stats["connected"] is True
    assert stats["accepted_shares"] == 42
    assert POOLS["btcpowlab"] is BtcPowLabPool


def test_btcpowlab_connection_reads_public_connection_state():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/public/v1/miner/{ADDRESS}/connection"
        return httpx.Response(200, json={"connected": False, "active_sessions": 0})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert BtcPowLabPool(client).connection(ADDRESS) == {
        "connected": False,
        "active_sessions": 0,
    }
