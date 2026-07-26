import os
import re
from typing import Any, Literal

import httpx
from mcp.server.fastmcp import FastMCP

BYBIT_BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")
PORT = int(os.getenv("PORT", "8000"))

mcp = FastMCP(
    name="Bybit Read Only",
    instructions=(
        "Read-only Bybit market-data tools. "
        "Never claims to place, amend, or cancel orders."
    ),
    host="0.0.0.0",
    port=PORT,
    stateless_http=True,
    json_response=True,
)

Category = Literal["spot", "linear", "inverse", "option"]

_SYMBOL_RE = re.compile(r"^[A-Z0-9]{3,30}$")
_ALLOWED_INTERVALS = {
    "1", "3", "5", "15", "30", "60", "120", "240", "360", "720",
    "D", "W", "M",
}
_ALLOWED_OI_INTERVALS = {"5min", "15min", "30min", "1h", "4h", "1d"}


def _clean_symbol(symbol: str) -> str:
    value = symbol.replace("/", "").replace("-", "").strip().upper()
    if not _SYMBOL_RE.fullmatch(value):
        raise ValueError("Invalid symbol. Example: BTCUSDT")
    return value


def _bounded_limit(limit: int, minimum: int, maximum: int) -> int:
    if not isinstance(limit, int):
        raise ValueError("limit must be an integer")
    return max(minimum, min(limit, maximum))


async def _bybit_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    timeout = httpx.Timeout(15.0, connect=8.0)
    headers = {
        "User-Agent": "bybit-readonly-mcp/1.0",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        response = await client.get(f"{BYBIT_BASE_URL}{path}", params=params)
        response.raise_for_status()
        data = response.json()

    if data.get("retCode") != 0:
        raise RuntimeError(
            f"Bybit API error {data.get('retCode')}: {data.get('retMsg', 'Unknown error')}"
        )
    return data


@mcp.tool()
async def get_ticker(
    symbol: str = "BTCUSDT",
    category: Category = "linear",
) -> dict[str, Any]:
    """Get the current Bybit ticker for one symbol. Read-only and no API key required."""
    symbol = _clean_symbol(symbol)
    return await _bybit_get(
        "/v5/market/tickers",
        {"category": category, "symbol": symbol},
    )


@mcp.tool()
async def get_klines(
    symbol: str = "BTCUSDT",
    interval: str = "15",
    limit: int = 100,
    category: Category = "linear",
) -> dict[str, Any]:
    """Get OHLCV candles from Bybit. interval examples: 1, 5, 15, 60, D."""
    symbol = _clean_symbol(symbol)
    interval = interval.strip()
    if interval not in _ALLOWED_INTERVALS:
        raise ValueError(
            "Unsupported interval. Use 1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, or M."
        )
    limit = _bounded_limit(limit, 1, 1000)
    return await _bybit_get(
        "/v5/market/kline",
        {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        },
    )


@mcp.tool()
async def get_orderbook(
    symbol: str = "BTCUSDT",
    limit: int = 25,
    category: Category = "linear",
) -> dict[str, Any]:
    """Get a Bybit order-book snapshot. Read-only."""
    symbol = _clean_symbol(symbol)
    max_limit = 200 if category in {"linear", "inverse"} else 50
    limit = _bounded_limit(limit, 1, max_limit)
    return await _bybit_get(
        "/v5/market/orderbook",
        {"category": category, "symbol": symbol, "limit": limit},
    )


@mcp.tool()
async def get_funding_history(
    symbol: str = "BTCUSDT",
    limit: int = 20,
    category: Literal["linear", "inverse"] = "linear",
) -> dict[str, Any]:
    """Get recent funding-rate history for a perpetual contract. Read-only."""
    symbol = _clean_symbol(symbol)
    limit = _bounded_limit(limit, 1, 200)
    return await _bybit_get(
        "/v5/market/funding/history",
        {"category": category, "symbol": symbol, "limit": limit},
    )


@mcp.tool()
async def get_open_interest(
    symbol: str = "BTCUSDT",
    interval_time: str = "5min",
    limit: int = 20,
    category: Literal["linear", "inverse"] = "linear",
) -> dict[str, Any]:
    """Get open-interest history for a Bybit perpetual/futures symbol. Read-only."""
    symbol = _clean_symbol(symbol)
    interval_time = interval_time.strip()
    if interval_time not in _ALLOWED_OI_INTERVALS:
        raise ValueError("interval_time must be 5min, 15min, 30min, 1h, 4h, or 1d")
    limit = _bounded_limit(limit, 1, 200)
    return await _bybit_get(
        "/v5/market/open-interest",
        {
            "category": category,
            "symbol": symbol,
            "intervalTime": interval_time,
            "limit": limit,
        },
    )


@mcp.tool()
async def server_status() -> dict[str, Any]:
    """Check that this MCP server and Bybit public API are reachable."""
    data = await _bybit_get("/v5/market/time", {})
    return {
        "status": "ok",
        "mode": "read_only",
        "trading_tools": False,
        "bybit": data,
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
