from __future__ import annotations

import numpy as np
import pandas as pd


def make_sample_panel(
    start: str = "2018-01-01",
    end: str = "2024-12-31",
    symbols: int = 80,
    *,
    seed: int = 20260731,
) -> pd.DataFrame:
    """Build a deterministic synthetic daily panel for examples and tests.

    The values are intentionally synthetic and must not be interpreted as
    historical market observations or evidence of strategy performance.
    """

    dates = pd.bdate_range(start, end)
    if dates.empty:
        raise ValueError("sample date range must contain at least one business day")
    if symbols <= 0:
        raise ValueError("symbols must be positive")

    random = np.random.default_rng(seed)
    rows: list[pd.DataFrame] = []
    for index in range(symbols):
        symbol = _sample_symbol(index)
        observations = len(dates)
        market_cycle = 0.0007 * np.sin(np.arange(observations) / 45.0 + index / 7.0)
        innovations = random.normal(loc=0.00015 + (index % 7) * 0.000015, scale=0.012, size=observations)
        daily_returns = np.clip(innovations + market_cycle, -0.045, 0.045)
        base_price = 8.0 + (index % 25) * 1.4
        close = base_price * np.exp(np.cumsum(daily_returns))
        previous_close = np.concatenate(([base_price], close[:-1]))
        overnight = np.clip(random.normal(0.0, 0.003, observations), -0.012, 0.012)
        open_price = previous_close * (1.0 + overnight)
        intraday_range = np.abs(random.normal(0.008, 0.003, observations))
        high = np.maximum(open_price, close) * (1.0 + intraday_range)
        low = np.minimum(open_price, close) * np.maximum(0.01, 1.0 - intraday_range)
        volume = random.integers(800_000, 8_000_000, size=observations).astype(float)
        amount = volume * (open_price + close) / 2.0
        slow_cycle = np.sin(np.arange(observations) / 126.0 + index / 5.0)

        rows.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "symbol": symbol,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                    "amount": amount,
                    "roe": 0.08 + (index % 12) * 0.012 + slow_cycle * 0.006,
                    "pe": 8.0 + (index % 22) + (1.0 - slow_cycle) * 1.5,
                    "pb": 0.9 + (index % 15) * 0.18 + slow_cycle * 0.08,
                    "dividend_yield": 0.008 + (index % 10) * 0.003,
                    "is_st": False,
                    "is_suspended": False,
                    "is_limit_up": False,
                    "is_limit_down": False,
                    "limit_up": previous_close * 1.10,
                    "limit_down": previous_close * 0.90,
                }
            )
        )

    raw = pd.concat(rows, ignore_index=True)
    from .data_sources import prepare_backtest_panel

    return prepare_backtest_panel(raw)


def _sample_symbol(index: int) -> str:
    if index % 2 == 0:
        return f"{600000 + index:06d}.SH"
    return f"{index:06d}.SZ"
