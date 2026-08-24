from __future__ import annotations

import unittest

import pandas as pd

from a_share_quant_agent.backtest import _buy, _prepare_data, _sell, run_backtest
from a_share_quant_agent.data_sources import DataSourceError, prepare_backtest_panel
from a_share_quant_agent.spec import StrategySpec


class ExecutionFailClosedTest(unittest.TestCase):
    def test_alignment_keeps_valuation_price_but_marks_missing_raw_open(self) -> None:
        raw = _raw_panel(
            [
                ("2024-01-02", "000001.SZ", 10.0, 10.0),
                ("2024-01-03", "000001.SZ", 11.0, 11.0),
                ("2024-01-02", "600000.SH", 20.0, 20.0),
            ]
        )

        aligned = prepare_backtest_panel(raw)
        missing_session = aligned[
            (aligned["date"] == pd.Timestamp("2024-01-03"))
            & (aligned["symbol"] == "600000.SH")
        ].iloc[0]

        self.assertIn("_has_raw_open", aligned.columns)
        self.assertFalse(bool(missing_session["_has_raw_open"]))
        self.assertTrue(bool(missing_session["is_suspended"]))
        self.assertEqual(float(missing_session["open"]), 20.0)
        self.assertEqual(float(missing_session["close"]), 20.0)

    def test_missing_raw_open_is_blocked_instead_of_filled_or_crashing(self) -> None:
        data = _single_symbol_panel(
            [
                ("2024-01-02", 10.0, 10.0),
                ("2024-01-03", float("nan"), 11.0),
            ]
        )
        data["_has_raw_open"] = [True, False]

        result = run_backtest(data, _spec())

        self.assertTrue(result.trades.empty)
        blocked = result.orders[result.orders["status"] == "blocked_missing_open"]
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked.iloc[0]["date"], pd.Timestamp("2024-01-03"))

    def test_public_panel_preparation_rejects_missing_critical_constraints(self) -> None:
        raw = pd.DataFrame(
            {
                "date": [pd.Timestamp("2024-01-02")],
                "symbol": ["000001.SZ"],
                "open": [10.0],
                "high": [10.5],
                "low": [9.5],
                "close": [10.0],
                "amount": [1_000_000.0],
            }
        )

        with self.assertRaises(DataSourceError):
            prepare_backtest_panel(raw)

    def test_public_panel_preparation_rejects_nan_constraint_on_tradable_row(self) -> None:
        raw = _single_symbol_panel([("2024-01-02", 10.0, 10.0)])
        raw.loc[0, "limit_down"] = float("nan")

        with self.assertRaises(DataSourceError):
            prepare_backtest_panel(raw)

    def test_nan_limit_constraint_blocks_next_open(self) -> None:
        data = _single_symbol_panel(
            [
                ("2024-01-02", 10.0, 10.0),
                ("2024-01-03", 10.0, 10.0),
            ]
        )
        data.loc[data["date"] == pd.Timestamp("2024-01-03"), "limit_up"] = float("nan")

        result = run_backtest(data, _spec())

        self.assertTrue(result.trades.empty)
        blocked = result.orders[result.orders["status"] == "blocked_missing_constraint"]
        self.assertEqual(len(blocked), 1)

    def test_nan_st_constraint_blocks_next_open(self) -> None:
        data = _single_symbol_panel(
            [
                ("2024-01-02", 10.0, 10.0),
                ("2024-01-03", 10.0, 10.0),
            ]
        )
        data["is_st"] = data["is_st"].astype("boolean")
        data.loc[data["date"] == pd.Timestamp("2024-01-03"), "is_st"] = pd.NA

        result = run_backtest(data, _spec())

        self.assertTrue(result.trades.empty)
        self.assertEqual(list(result.orders["status"]), ["blocked_missing_constraint"])

    def test_reverse_ordered_multiindex_is_normalized_before_execution(self) -> None:
        data = _single_symbol_panel(
            [
                ("2024-01-02", 10.0, 10.0),
                ("2024-01-03", 11.0, 11.0),
                ("2024-01-04", 12.0, 12.0),
            ]
        )
        reversed_multiindex = data.set_index(["date", "symbol"], drop=False).iloc[::-1]

        result = run_backtest(reversed_multiindex, _spec())

        self.assertEqual(list(result.equity_curve["date"]), sorted(result.equity_curve["date"]))
        self.assertFalse(result.trades.empty)
        self.assertTrue((result.trades["signal_date"] < result.trades["date"]).all())

    def test_duplicate_multiindex_keys_are_rejected(self) -> None:
        row = _single_symbol_panel([("2024-01-02", 10.0, 10.0)])
        duplicated = pd.concat([row, row], ignore_index=True).set_index(["date", "symbol"], drop=False)

        with self.assertRaisesRegex(ValueError, "duplicate"):
            _prepare_data(duplicated, required_price_field="open")

    def test_pending_stop_does_not_duplicate_rebalance_sell_and_retries(self) -> None:
        data = _single_symbol_panel(
            [
                ("2024-01-05", 10.0, 10.0),
                ("2024-01-08", 10.0, 5.0),
                ("2024-01-09", 4.0, 4.0),
                ("2024-01-10", 4.0, 4.0),
                ("2024-01-11", 4.5, 4.5),
            ]
        )
        data.loc[data["date"] == pd.Timestamp("2024-01-09"), "is_suspended"] = True
        data.loc[data["date"] == pd.Timestamp("2024-01-10"), "limit_down"] = 4.0

        result = run_backtest(data, _spec(position_stop_loss_limit=-0.20))

        jan_9_sells = result.orders[
            (result.orders["date"] == pd.Timestamp("2024-01-09"))
            & (result.orders["side"] == "sell")
        ]
        self.assertEqual(len(jan_9_sells), 1)
        self.assertEqual(jan_9_sells.iloc[0]["status"], "blocked_suspended")
        jan_10_sells = result.orders[
            (result.orders["date"] == pd.Timestamp("2024-01-10"))
            & (result.orders["side"] == "sell")
        ]
        self.assertEqual(list(jan_10_sells["status"]), ["blocked_limit_down"])
        sell = result.trades[result.trades["side"] == "sell"].iloc[0]
        self.assertEqual(sell["date"], pd.Timestamp("2024-01-11"))
        self.assertEqual(sell["signal_date"], pd.Timestamp("2024-01-08"))
        self.assertLess(sell["signal_date"], sell["date"])

    def test_final_multi_target_rebalance_is_one_signal_intent_not_fake_orders(self) -> None:
        data = _two_symbol_panel(["2024-01-02"])

        result = run_backtest(data, _spec(max_positions=2))

        intents = result.orders[result.orders["status"] == "unfilled_no_next_session"]
        self.assertEqual(result.metrics["unfilled_final_signal_count"], 1.0)
        self.assertEqual(len(intents), 1)
        self.assertEqual(intents.iloc[0]["record_type"], "signal_intent")
        self.assertEqual(intents.iloc[0]["side"], "rebalance_intent")
        self.assertTrue(pd.isna(intents.iloc[0]["requested_shares"]))
        self.assertEqual(tuple(intents.iloc[0]["targets"]), ("000001.SZ", "600000.SH"))

    def test_final_no_change_rebalance_is_not_reported_as_unfilled_order(self) -> None:
        data = _single_symbol_panel(
            [
                ("2024-01-01", 10.0, 10.0),
                ("2024-01-02", 10.0, 10.0),
                ("2024-01-08", 10.0, 10.0),
            ]
        )

        result = run_backtest(data, _spec())

        self.assertEqual(result.metrics["unfilled_final_signal_count"], 0.0)
        self.assertFalse((result.orders["status"] == "unfilled_no_next_session").any())


class ExecutionAccountingTest(unittest.TestCase):
    def test_buy_and_sell_costs_match_hand_calculation_and_t_plus_one_blocks(self) -> None:
        spec = _spec(commission_rate=0.01, stamp_tax_rate=0.05, slippage_bps=100.0)
        trade_rows: list[dict[str, object]] = []
        order_rows: list[dict[str, object]] = []
        buy_day = _execution_today(open_price=10.0, close_price=10.0)

        cash, shares = _buy(
            pd.Timestamp("2024-01-02"),
            "000001.SZ",
            100,
            2_000.0,
            0,
            buy_day,
            spec,
            trade_rows,
            order_rows=order_rows,
            price_field="open",
            signal_date=pd.Timestamp("2024-01-01"),
            execution_model="close_signal_next_open",
        )

        self.assertAlmostEqual(cash, 979.90, places=8)
        self.assertEqual(shares, 100)
        self.assertAlmostEqual(float(trade_rows[0]["price"]), 10.10, places=8)
        self.assertAlmostEqual(float(trade_rows[0]["commission"]), 10.10, places=8)

        unchanged_cash, unchanged_shares = _sell(
            date=pd.Timestamp("2024-01-02"),
            symbol="000001.SZ",
            shares=100,
            cash=cash,
            held_shares=shares,
            buy_dates={"000001.SZ": pd.Timestamp("2024-01-02")},
            today=buy_day,
            spec=spec,
            trade_rows=trade_rows,
            order_rows=order_rows,
            price_field="open",
            signal_date=pd.Timestamp("2024-01-02"),
            execution_model="close_signal_next_open",
        )
        self.assertEqual((unchanged_cash, unchanged_shares), (cash, shares))
        self.assertEqual(order_rows[-1]["status"], "blocked_t_plus_one")

        sell_day = _execution_today(open_price=12.0, close_price=12.0)
        cash, shares = _sell(
            date=pd.Timestamp("2024-01-03"),
            symbol="000001.SZ",
            shares=100,
            cash=cash,
            held_shares=shares,
            buy_dates={"000001.SZ": pd.Timestamp("2024-01-02")},
            today=sell_day,
            spec=spec,
            trade_rows=trade_rows,
            order_rows=order_rows,
            price_field="open",
            signal_date=pd.Timestamp("2024-01-02"),
            execution_model="close_signal_next_open",
        )

        self.assertEqual(shares, 0)
        self.assertAlmostEqual(float(trade_rows[-1]["price"]), 11.88, places=8)
        self.assertAlmostEqual(float(trade_rows[-1]["gross"]), 1_188.00, places=8)
        self.assertAlmostEqual(float(trade_rows[-1]["commission"]), 11.88, places=8)
        self.assertAlmostEqual(float(trade_rows[-1]["stamp_tax"]), 59.40, places=8)
        self.assertAlmostEqual(float(trade_rows[-1]["cash_delta"]), 1_116.72, places=8)
        self.assertAlmostEqual(cash, 2_096.62, places=8)

    def test_commission_aware_cash_sizing_buys_affordable_round_lot(self) -> None:
        data = _single_symbol_panel(
            [
                ("2024-01-02", 10.0, 10.0),
                ("2024-01-03", 10.0, 10.0),
            ]
        )

        result = run_backtest(data, _spec(initial_cash=10_000.0, commission_rate=0.01))

        buy = result.trades[result.trades["side"] == "buy"].iloc[0]
        self.assertEqual(int(buy["shares"]), 900)
        self.assertAlmostEqual(float(buy["gross"]), 9_000.0, places=8)
        self.assertAlmostEqual(float(buy["commission"]), 90.0, places=8)
        self.assertAlmostEqual(float(result.equity_curve.iloc[-1]["cash"]), 910.0, places=8)

    def test_target_sizing_uses_fill_session_open_nav(self) -> None:
        data = _single_symbol_panel(
            [
                ("2024-01-02", 10.0, 10.0),
                ("2024-01-03", 20.0, 20.0),
            ]
        )

        result = run_backtest(data, _spec(max_single_position_weight=0.50))

        buy = result.trades[result.trades["side"] == "buy"].iloc[0]
        self.assertEqual(int(buy["shares"]), 2_500)
        self.assertEqual(float(buy["gross"]), 50_000.0)

    def test_existing_position_gap_uses_raw_open_nav_for_next_open_rebalance(self) -> None:
        data = _raw_panel(
            [
                ("2024-01-05", "000001.SZ", 10.0, 10.0),
                ("2024-01-05", "600000.SH", 10.0, 10.0),
                ("2024-01-08", "000001.SZ", 10.0, 10.0),
                ("2024-01-08", "600000.SH", 10.0, 10.0),
                ("2024-01-09", "000001.SZ", 20.0, 10.0),
                ("2024-01-09", "600000.SH", 10.0, 10.0),
            ]
        )
        data["score"] = [2.0, 1.0, 1.0, 2.0, 1.0, 2.0]

        result = run_backtest(data, _spec())

        self.assertEqual(list(result.trades["side"]), ["buy", "sell", "buy"])
        switched_buy = result.trades[
            (result.trades["date"] == pd.Timestamp("2024-01-09"))
            & (result.trades["symbol"] == "600000.SH")
            & (result.trades["side"] == "buy")
        ].iloc[0]
        self.assertEqual(int(switched_buy["shares"]), 20_000)
        self.assertEqual(float(switched_buy["gross"]), 200_000.0)
        final = result.equity_curve.iloc[-1]
        self.assertEqual(float(final["cash"]), 0.0)
        final_holding = result.holdings[
            (result.holdings["date"] == pd.Timestamp("2024-01-09"))
            & (result.holdings["symbol"] == "600000.SH")
        ].iloc[0]
        self.assertEqual(int(final_holding["shares"]), 20_000)

    def test_default_and_legacy_models_have_hand_checked_gap_accounting(self) -> None:
        data = _single_symbol_panel(
            [
                ("2024-01-02", 10.0, 10.0),
                ("2024-01-03", 20.0, 20.0),
            ]
        )

        default = run_backtest(data, _spec())
        legacy = run_backtest(data, _spec(execution_model="same_close_legacy"))

        self.assertEqual(float(default.metrics["end_equity"]), 100_000.0)
        self.assertEqual(float(legacy.metrics["end_equity"]), 200_000.0)
        self.assertEqual(int(default.trades.iloc[0]["shares"]), 5_000)
        self.assertEqual(int(legacy.trades.iloc[0]["shares"]), 10_000)

    def test_explicit_legacy_model_keeps_close_only_input_compatibility(self) -> None:
        data = _single_symbol_panel([("2024-01-02", 10.0, 10.0)]).drop(columns=["open"])

        result = run_backtest(data, _spec(execution_model="same_close_legacy"))

        self.assertEqual(float(result.trades.iloc[0]["price"]), 10.0)
        self.assertEqual(result.trades.iloc[0]["fill_price_field"], "close")

    def test_explicit_can_buy_false_blocks_otherwise_tradable_next_open(self) -> None:
        data = _single_symbol_panel(
            [("2024-01-02", 10.0, 10.0), ("2024-01-03", 10.0, 10.0)]
        )
        data["can_buy"] = [True, False]

        result = run_backtest(data, _spec())

        self.assertTrue(result.trades.empty)
        self.assertEqual(list(result.orders["status"]), ["blocked_cannot_buy"])

    def test_explicit_can_sell_false_blocks_otherwise_tradable_rebalance_sell(self) -> None:
        data = _raw_panel(
            [
                ("2024-01-05", "000001.SZ", 10.0, 10.0),
                ("2024-01-05", "600000.SH", 10.0, 10.0),
                ("2024-01-08", "000001.SZ", 10.0, 10.0),
                ("2024-01-08", "600000.SH", 10.0, 10.0),
                ("2024-01-09", "000001.SZ", 10.0, 10.0),
                ("2024-01-09", "600000.SH", 10.0, 10.0),
            ]
        )
        data["score"] = [2.0, 1.0, 1.0, 2.0, 1.0, 2.0]
        data["can_sell"] = True
        data.loc[
            (data["date"] == pd.Timestamp("2024-01-09"))
            & (data["symbol"] == "000001.SZ"),
            "can_sell",
        ] = False

        result = run_backtest(data, _spec())

        blocked = result.orders[
            (result.orders["date"] == pd.Timestamp("2024-01-09"))
            & (result.orders["side"] == "sell")
        ]
        self.assertEqual(list(blocked["status"]), ["blocked_cannot_sell"])
        self.assertFalse((result.trades["side"] == "sell").any())

    def test_nonstandard_lot_size_controls_public_order_and_fill_shares(self) -> None:
        data = _single_symbol_panel(
            [("2024-01-02", 10.0, 10.0), ("2024-01-03", 10.0, 10.0)]
        )
        data["lot_size"] = 300

        result = run_backtest(data, _spec())

        buy = result.trades.iloc[0]
        filled_order = result.orders[result.orders["status"] == "filled"].iloc[0]
        self.assertEqual(int(buy["shares"]), 9_900)
        self.assertEqual(int(filled_order["requested_shares"]), 9_900)
        self.assertEqual(int(buy["shares"]) % 300, 0)

    def test_t_plus_one_false_allows_private_same_day_sell_path(self) -> None:
        today = _execution_today(open_price=10.0, close_price=10.0)
        today["t_plus_one"] = False
        trade_rows: list[dict[str, object]] = []
        order_rows: list[dict[str, object]] = []

        cash, shares = _sell(
            date=pd.Timestamp("2024-01-02"),
            symbol="000001.SZ",
            shares=100,
            cash=0.0,
            held_shares=100,
            buy_dates={"000001.SZ": pd.Timestamp("2024-01-02")},
            today=today,
            spec=_spec(),
            trade_rows=trade_rows,
            order_rows=order_rows,
            price_field="open",
            signal_date=pd.Timestamp("2024-01-02"),
            execution_model="close_signal_next_open",
        )

        self.assertEqual(shares, 0)
        self.assertEqual(cash, 1_000.0)
        self.assertEqual(list(row["status"] for row in order_rows), ["filled"])

    def test_nan_in_any_present_optional_execution_column_fails_closed(self) -> None:
        for field in ("can_buy", "can_sell", "lot_size", "t_plus_one"):
            with self.subTest(field=field):
                today = _execution_today(open_price=10.0, close_price=10.0)
                today[field] = pd.NA
                trade_rows: list[dict[str, object]] = []
                order_rows: list[dict[str, object]] = []

                cash, shares = _buy(
                    pd.Timestamp("2024-01-02"),
                    "000001.SZ",
                    100,
                    2_000.0,
                    0,
                    today,
                    _spec(),
                    trade_rows,
                    order_rows=order_rows,
                    price_field="open",
                    signal_date=pd.Timestamp("2024-01-01"),
                    execution_model="close_signal_next_open",
                )

                self.assertEqual((cash, shares), (2_000.0, 0))
                self.assertEqual(list(row["status"] for row in order_rows), ["blocked_missing_constraint"])
                self.assertEqual(trade_rows, [])

    def test_below_lot_order_ledger_preserves_original_requested_shares(self) -> None:
        today = _execution_today(open_price=10.0, close_price=10.0)
        today["lot_size"] = 300
        trade_rows: list[dict[str, object]] = []
        order_rows: list[dict[str, object]] = []

        cash, shares = _buy(
            pd.Timestamp("2024-01-02"),
            "000001.SZ",
            100,
            2_000.0,
            0,
            today,
            _spec(),
            trade_rows,
            order_rows=order_rows,
            price_field="open",
            signal_date=pd.Timestamp("2024-01-01"),
            execution_model="close_signal_next_open",
        )

        self.assertEqual((cash, shares), (2_000.0, 0))
        self.assertEqual(order_rows[0]["status"], "blocked_below_lot_size")
        self.assertEqual(order_rows[0]["requested_shares"], 100)
        self.assertEqual(trade_rows, [])


def _spec(
    *,
    initial_cash: float = 100_000.0,
    max_positions: int = 1,
    max_single_position_weight: float = 1.0,
    position_stop_loss_limit: float = 0.0,
    commission_rate: float = 0.0,
    stamp_tax_rate: float = 0.0,
    slippage_bps: float = 0.0,
    execution_model: str | None = None,
) -> StrategySpec:
    payload: dict[str, object] = {
        "name": "fail-closed-execution-contract",
        "description": "Literal daily-bar execution fixtures.",
        "universe": {"exclude_st": True, "exclude_suspended": True, "min_amount": 0.0},
        "rebalance": {"frequency": "weekly"},
        "portfolio": {
            "initial_cash": initial_cash,
            "max_positions": max_positions,
            "weighting": "equal",
        },
        "costs": {
            "commission_rate": commission_rate,
            "stamp_tax_rate": stamp_tax_rate,
            "slippage_bps": slippage_bps,
        },
        "factors": [{"field": "score", "direction": "desc", "weight": 1.0}],
        "risk": {
            "max_single_position_weight": max_single_position_weight,
            "position_stop_loss_limit": position_stop_loss_limit,
        },
    }
    if execution_model is not None:
        payload["execution"] = {"model": execution_model}
    return StrategySpec.from_dict(payload)  # type: ignore[arg-type]


def _single_symbol_panel(sessions: list[tuple[str, float, float]]) -> pd.DataFrame:
    return _raw_panel(
        [(date, "000001.SZ", open_price, close_price) for date, open_price, close_price in sessions]
    )


def _two_symbol_panel(dates: list[str]) -> pd.DataFrame:
    rows: list[tuple[str, str, float, float]] = []
    for date in dates:
        rows.extend(
            [
                (date, "000001.SZ", 10.0, 10.0),
                (date, "600000.SH", 20.0, 20.0),
            ]
        )
    panel = _raw_panel(rows)
    panel.loc[panel["symbol"] == "000001.SZ", "score"] = 2.0
    return panel


def _raw_panel(rows: list[tuple[str, str, float, float]]) -> pd.DataFrame:
    records = []
    for date, symbol, open_price, close_price in rows:
        records.append(
            {
                "date": pd.Timestamp(date),
                "symbol": symbol,
                "open": open_price,
                "high": max(open_price, close_price),
                "low": min(open_price, close_price),
                "close": close_price,
                "volume": 1_000_000.0,
                "amount": 10_000_000.0,
                "score": 1.0,
                "is_st": False,
                "is_suspended": False,
                "limit_up": 99.0,
                "limit_down": 0.01,
                "is_limit_up": False,
                "is_limit_down": False,
            }
        )
    return pd.DataFrame(records)


def _execution_today(*, open_price: float, close_price: float) -> pd.DataFrame:
    row = _single_symbol_panel([("2024-01-02", open_price, close_price)]).iloc[0].to_dict()
    row["_has_raw_open"] = True
    return pd.DataFrame([row]).set_index("symbol")


if __name__ == "__main__":
    unittest.main()
