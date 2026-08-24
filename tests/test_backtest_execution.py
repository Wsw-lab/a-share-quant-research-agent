from __future__ import annotations

import unittest

import pandas as pd

from a_share_quant_agent.backtest import _is_limit_down, _is_limit_up, run_backtest
from a_share_quant_agent.spec import StrategySpec


class BacktestExecutionTest(unittest.TestCase):
    def test_default_close_signal_fills_at_next_session_open(self) -> None:
        data = _panel(
            [
                ("2024-01-02", 9.0, 10.0, False, False),
                ("2024-01-03", 20.0, 21.0, False, False),
            ]
        )

        result = run_backtest(data, _spec())

        self.assertEqual(list(result.trades["date"]), [pd.Timestamp("2024-01-03")])
        self.assertEqual(list(result.trades["signal_date"]), [pd.Timestamp("2024-01-02")])
        self.assertEqual(list(result.trades["price"]), [20.0])
        self.assertEqual(list(result.trades["fill_price_field"]), ["open"])

    def test_same_close_legacy_requires_explicit_configuration(self) -> None:
        data = _panel(
            [
                ("2024-01-02", 9.0, 10.0, False, False),
                ("2024-01-03", 20.0, 21.0, False, False),
            ]
        )

        result = run_backtest(data, _spec(execution_model="same_close_legacy"))

        self.assertEqual(list(result.trades["date"]), [pd.Timestamp("2024-01-02")])
        self.assertEqual(list(result.trades["price"]), [10.0])
        self.assertEqual(list(result.trades["fill_price_field"]), ["close"])

    def test_final_close_signal_remains_unfilled_without_a_next_session(self) -> None:
        result = run_backtest(
            _panel([("2024-01-02", 9.0, 10.0, False, False)]),
            _spec(),
        )

        self.assertTrue(result.trades.empty)
        self.assertEqual(result.metrics["unfilled_final_signal_count"], 1.0)

    def test_numeric_limit_threshold_blocks_fill_when_boolean_flag_is_false(self) -> None:
        limit_up = pd.Series(
            {"open": 11.0, "close": 11.0, "limit_up": 11.0, "limit_down": 9.0, "is_limit_up": False}
        )
        limit_down = pd.Series(
            {"open": 9.0, "close": 9.0, "limit_up": 11.0, "limit_down": 9.0, "is_limit_down": False}
        )

        self.assertTrue(_is_limit_up(limit_up))
        self.assertTrue(_is_limit_down(limit_down))

    def test_next_open_at_limit_up_is_blocked_even_with_false_boolean_flag(self) -> None:
        data = _panel(
            [
                ("2024-01-02", 9.0, 10.0, False, False),
                ("2024-01-03", 11.0, 10.5, False, False),
            ],
            limit_up_by_date={"2024-01-03": 11.0},
        )

        result = run_backtest(data, _spec())

        self.assertTrue(result.trades.empty)
        blocked = result.orders[result.orders["status"] == "blocked_limit_up"]
        self.assertEqual(len(blocked), 1)

    def test_next_open_suspension_blocks_fill(self) -> None:
        data = _panel(
            [
                ("2024-01-02", 9.0, 10.0, False, False),
                ("2024-01-03", 10.0, 10.0, True, False),
            ]
        )

        result = run_backtest(data, _spec())

        self.assertTrue(result.trades.empty)
        blocked = result.orders[result.orders["status"] == "blocked_suspended"]
        self.assertEqual(len(blocked), 1)

    def test_stop_created_after_purchase_sells_no_earlier_than_t_plus_one(self) -> None:
        data = _panel(
            [
                ("2024-01-02", 10.0, 10.0, False, False),
                ("2024-01-03", 10.0, 5.0, False, False),
                ("2024-01-04", 4.0, 4.0, False, False),
            ],
            limit_down_by_date={"2024-01-03": 1.0, "2024-01-04": 1.0},
        )

        result = run_backtest(data, _spec(position_stop_loss_limit=-0.20))

        self.assertEqual(list(result.trades["side"]), ["buy", "sell"])
        self.assertEqual(
            list(result.trades["date"]),
            [pd.Timestamp("2024-01-03"), pd.Timestamp("2024-01-04")],
        )
        self.assertEqual(
            list(result.trades["signal_date"]),
            [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")],
        )


def _spec(
    *,
    position_stop_loss_limit: float = 0.0,
    execution_model: str | None = None,
) -> StrategySpec:
    payload = {
            "name": "execution-contract",
            "description": "Hand-checked execution fixture.",
            "universe": {"exclude_st": True, "exclude_suspended": True, "min_amount": 0.0},
            "rebalance": {"frequency": "weekly"},
            "portfolio": {
                "initial_cash": 100_000.0,
                "max_positions": 1,
                "weighting": "equal",
            },
            "costs": {"commission_rate": 0.0, "stamp_tax_rate": 0.0, "slippage_bps": 0.0},
            "factors": [{"field": "score", "direction": "desc", "weight": 1.0}],
            "risk": {
                "max_single_position_weight": 1.0,
                "position_stop_loss_limit": position_stop_loss_limit,
            },
    }
    if execution_model is not None:
        payload["execution"] = {"model": execution_model}
    return StrategySpec.from_dict(payload)


def _panel(
    sessions: list[tuple[str, float, float, bool, bool]],
    *,
    limit_up_by_date: dict[str, float] | None = None,
    limit_down_by_date: dict[str, float] | None = None,
) -> pd.DataFrame:
    limit_up_by_date = limit_up_by_date or {}
    limit_down_by_date = limit_down_by_date or {}
    rows = []
    for date, open_price, close_price, is_suspended, is_st in sessions:
        rows.append(
            {
                "date": pd.Timestamp(date),
                "symbol": "000001.SZ",
                "open": open_price,
                "high": max(open_price, close_price),
                "low": min(open_price, close_price),
                "close": close_price,
                "amount": 10_000_000.0,
                "score": 1.0,
                "is_st": is_st,
                "is_suspended": is_suspended,
                "limit_up": limit_up_by_date.get(date, 99.0),
                "limit_down": limit_down_by_date.get(date, 0.01),
                "is_limit_up": False,
                "is_limit_down": False,
            }
        )
    return pd.DataFrame(rows)


if __name__ == "__main__":
    unittest.main()
