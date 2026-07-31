from __future__ import annotations

from copy import deepcopy

import pandas as pd

from a_share_quant_agent.backtest import _WindowFuseState, _risk_target_weight, _update_window_fuse_state, run_backtest
from a_share_quant_agent.data_sources import add_market_regime_features, load_sample_panel, validate_strategy_data
from a_share_quant_agent.spec import StrategySpec
from a_share_quant_agent.strategy_factory import load_strategy_templates


def main() -> None:
    loaded = load_sample_panel("20210101", "20241231", symbols=45)
    spec = StrategySpec.from_dict(load_strategy_templates("configs/strategy_factory_regime_overlay_variants.json")[0]["spec"])

    rising = _benchmark("2021-01-01", "2024-12-31", daily_step=0.0001)
    rising_panel = add_market_regime_features(
        loaded.data,
        rising,
        fields=["benchmark_trend_200d_lag1", "benchmark_momentum_60d_lag1"],
    )
    validate_strategy_data(rising_panel, spec)
    rising_result = run_backtest(rising_panel, spec)
    assert rising_result.metrics["min_risk_target_weight"] == 1.0
    assert rising_result.metrics["average_gross_exposure"] > 0.90

    falling = _benchmark("2021-01-01", "2024-12-31", daily_step=-0.0003)
    falling_panel = add_market_regime_features(
        loaded.data,
        falling,
        fields=["benchmark_trend_200d_lag1", "benchmark_momentum_60d_lag1"],
    )
    validate_strategy_data(falling_panel, spec)
    falling_result = run_backtest(falling_panel, spec)
    assert falling_result.metrics["min_risk_target_weight"] < 1.0
    assert falling_result.metrics["average_gross_exposure"] < rising_result.metrics["average_gross_exposure"]

    recovery_spec = StrategySpec.from_dict(
        load_strategy_templates("configs/strategy_factory_regime_recovery_variants.json")[0]["spec"]
    )
    recovery = _recovery_benchmark("2021-01-01", "2024-12-31")
    recovery_panel = add_market_regime_features(
        loaded.data,
        recovery,
        fields=["benchmark_trend_200d_lag1", "benchmark_momentum_60d_lag1", "benchmark_momentum_20d_lag1"],
    )
    validate_strategy_data(recovery_panel, recovery_spec)
    recovery_result = run_backtest(recovery_panel, recovery_spec)
    recovery_weights = recovery_result.equity_curve["risk_target_weight"]
    assert ((recovery_weights > 0.70) & (recovery_weights < 0.80)).any()

    fuse_payload = deepcopy(load_strategy_templates("configs/strategy_factory_regime_recovery_variants.json")[0]["spec"])
    fuse_overlay = fuse_payload["risk"]["risk_overlay"]
    fuse_overlay.update(
        {
            "use_window_fuse": True,
            "fuse_drawdown_limit": -0.01,
            "fuse_rolling_return_limit": -0.02,
            "fuse_rolling_days": 10,
            "fuse_consecutive_loss_days": 3,
            "fuse_weight": 0.12,
            "fuse_cooldown_days": 5,
            "fuse_max_active_days": 6,
            "fuse_reentry_weight": 0.55,
            "fuse_reentry_initial_weight": 0.25,
            "fuse_reentry_step_weight": 0.10,
            "fuse_reentry_step_days": 2,
            "fuse_reentry_days": 10,
            "fuse_reentry_confirmation_days": 2,
            "fuse_reentry_requires_drawdown_repair": False,
            "fuse_reentry_drawdown_repair": 0.0,
            "fuse_reentry_rolling_return_floor": -0.02,
            "fuse_reentry_requires_market_recovery": True,
            "fuse_reentry_field": "benchmark_momentum_20d_lag1",
            "fuse_reentry_threshold": 0.0,
            "fuse_reentry_refuse_drawdown_buffer": 0.08,
            "fuse_reentry_refuse_rolling_return_limit": -0.08,
        }
    )
    fuse_spec = StrategySpec.from_dict(fuse_payload)
    fuse_panel = add_market_regime_features(
        loaded.data,
        recovery,
        fields=[
            "benchmark_trend_200d_lag1",
            "benchmark_momentum_60d_lag1",
            "benchmark_momentum_20d_lag1",
        ],
    )
    validate_strategy_data(fuse_panel, fuse_spec)
    fuse_result = run_backtest(fuse_panel, fuse_spec)
    assert fuse_result.metrics["window_fuse_days"] > 0
    assert fuse_result.metrics["window_reentry_days"] > 0
    assert fuse_result.equity_curve["window_reentry_target_weight"].max() > 0.25
    assert fuse_result.metrics["min_risk_target_weight"] <= 0.12
    _assert_staged_recovery_targets(fuse_payload)
    _assert_regime_specific_failure_targets(fuse_payload)
    _assert_alpha_health_filter_targets(fuse_payload)
    print("OK risk overlay smoke")


def _benchmark(start: str, end: str, *, daily_step: float) -> pd.DataFrame:
    dates = pd.bdate_range(start, end)
    step = pd.Series(range(len(dates)), index=dates) * daily_step
    close = (4000 * (1 + step)).clip(lower=2200)
    return pd.DataFrame(
        {
            "date": dates,
            "indexCode": "000300",
            "indexName": "CSI300",
            "closePrice": close.to_numpy(),
        }
    )


def _recovery_benchmark(start: str, end: str) -> pd.DataFrame:
    dates = pd.bdate_range(start, end)
    steps = pd.Series(range(len(dates)), index=dates, dtype=float)
    drawdown = -0.0015 * steps.clip(upper=360)
    rebound = 0.004 * (steps - 360).clip(lower=0, upper=80)
    close = 4500 * (1 + drawdown + rebound).clip(lower=0.60)
    return pd.DataFrame(
        {
            "date": dates,
            "indexCode": "000300",
            "indexName": "CSI300",
            "closePrice": close.to_numpy(),
        }
    )


def _assert_staged_recovery_targets(base_payload: dict) -> None:
    payload = deepcopy(base_payload)
    overlay = payload["risk"]["risk_overlay"]
    overlay.update(
        {
            "use_recovery": False,
            "use_window_fuse": False,
            "risk_on_weight": 1.0,
            "risk_off_weight": 0.38,
            "crisis_weight": 0.18,
            "risk_off_trigger_count": 1,
            "crisis_trigger_count": 3,
            "use_trend": True,
            "trend_field": "benchmark_trend_200d_lag1",
            "use_momentum": True,
            "momentum_field": "benchmark_momentum_60d_lag1",
            "use_staged_recovery": True,
            "staged_recovery_field": "benchmark_momentum_20d_lag1",
            "staged_recovery_threshold_1": 0.0,
            "staged_recovery_threshold_2": 0.03,
            "staged_recovery_threshold_3": 0.06,
            "staged_recovery_weight_1": 0.52,
            "staged_recovery_weight_2": 0.66,
            "staged_recovery_weight_3": 0.78,
            "staged_recovery_requires_trend_bad": True,
            "staged_recovery_requires_portfolio_drawdown": True,
            "staged_recovery_drawdown_trigger": -0.02,
            "staged_recovery_drawdown_floor": -0.24,
            "staged_recovery_allows_drawdown_lift": True,
            "portfolio_drawdown_limit": -0.05,
            "drawdown_weight": 0.24,
        }
    )
    spec = StrategySpec.from_dict(payload)
    today = pd.DataFrame(
        {
            "benchmark_trend_200d_lag1": [0.0],
            "benchmark_momentum_60d_lag1": [-0.01],
            "benchmark_momentum_20d_lag1": [0.045],
        },
        index=["000001.SZ"],
    )
    assert _risk_target_weight(today, spec, nav=0.92, peak_nav=1.0) == 0.66
    today["benchmark_momentum_20d_lag1"] = 0.075
    assert _risk_target_weight(today, spec, nav=0.92, peak_nav=1.0) == 0.78
    today["benchmark_momentum_20d_lag1"] = 0.075
    assert _risk_target_weight(today, spec, nav=0.75, peak_nav=1.0) == 0.24
    today["benchmark_trend_200d_lag1"] = 1.0
    today["benchmark_momentum_60d_lag1"] = 0.01


def _assert_alpha_health_filter_targets(base_payload: dict) -> None:
    payload = deepcopy(base_payload)
    overlay = payload["risk"]["risk_overlay"]
    overlay.update(
        {
            "use_window_fuse": False,
            "use_alpha_health_filter": True,
            "alpha_health_field": "market_alpha_health_score_lag1",
            "alpha_health_min": 0.35,
            "alpha_health_warning": 0.50,
            "alpha_health_off_weight": 0.0,
            "alpha_health_weak_weight": 0.42,
            "use_market_breadth_filter": True,
            "market_breadth_field": "market_breadth_60d_lag1",
            "market_breadth_min": 0.30,
            "market_breadth_warning": 0.45,
            "market_breadth_off_weight": 0.0,
            "market_breadth_weak_weight": 0.46,
        }
    )
    spec = StrategySpec.from_dict(payload)
    today = pd.DataFrame(
        {
            "benchmark_trend_200d_lag1": [1.0],
            "benchmark_momentum_60d_lag1": [0.01],
            "benchmark_momentum_20d_lag1": [0.01],
            "market_alpha_health_score_lag1": [0.60],
            "market_breadth_60d_lag1": [0.55],
        },
        index=["000001.SZ"],
    )
    assert _risk_target_weight(today, spec, nav=1.0, peak_nav=1.0) == 1.0
    today["market_alpha_health_score_lag1"] = 0.42
    assert _risk_target_weight(today, spec, nav=1.0, peak_nav=1.0) == 0.42
    today["market_alpha_health_score_lag1"] = 0.60
    today["market_breadth_60d_lag1"] = 0.40
    assert _risk_target_weight(today, spec, nav=1.0, peak_nav=1.0) == 0.46
    today["market_alpha_health_score_lag1"] = 0.20
    assert _risk_target_weight(today, spec, nav=1.0, peak_nav=1.0) == 0.0


def _assert_regime_specific_failure_targets(base_payload: dict) -> None:
    payload = deepcopy(base_payload)
    overlay = payload["risk"]["risk_overlay"]
    overlay.update(
        {
            "enabled": True,
            "risk_on_weight": 1.0,
            "risk_off_weight": 1.0,
            "crisis_weight": 1.0,
            "use_trend": False,
            "use_momentum": False,
            "use_recovery": False,
            "use_staged_recovery": False,
            "use_window_fuse": False,
            "portfolio_drawdown_limit": 0.0,
            "use_high_vol_uptrend_guard": True,
            "high_vol_uptrend_weight": 0.55,
            "use_uptrend_tail_guard": True,
            "uptrend_tail_momentum_floor": -0.015,
            "uptrend_tail_weight": 0.60,
        }
    )
    spec = StrategySpec.from_dict(payload)
    today = pd.DataFrame(
        {
            "benchmark_trend_200d_lag1": [1.0],
            "benchmark_volatility_60d_lag1": [0.040],
            "benchmark_volatility_60d_q80_lag1": [0.030],
            "benchmark_momentum_20d_lag1": [0.020],
        },
        index=["000001.SZ"],
    )
    assert _risk_target_weight(today, spec, nav=1.0, peak_nav=1.0) == 0.55
    today["benchmark_volatility_60d_lag1"] = 0.020
    assert _risk_target_weight(today, spec, nav=1.0, peak_nav=1.0) == 1.0
    today["benchmark_momentum_20d_lag1"] = -0.020
    assert _risk_target_weight(today, spec, nav=1.0, peak_nav=1.0) == 0.60

    overheated_payload = deepcopy(base_payload)
    overheated_overlay = overheated_payload["risk"]["risk_overlay"]
    overheated_overlay.update(
        {
            "enabled": True,
            "risk_on_weight": 1.0,
            "use_trend": False,
            "use_momentum": False,
            "use_recovery": False,
            "use_window_fuse": False,
            "use_overheated_reversal_guard": True,
            "overheated_alpha_health_min": 0.52,
            "overheated_breadth_min": 0.50,
            "overheated_momentum_max": 0.0,
            "overheated_guard_weight": 0.06,
        }
    )
    overheated_spec = StrategySpec.from_dict(overheated_payload)
    overheated_today = pd.DataFrame(
        {
            "market_alpha_health_score_lag1": [0.60],
            "market_breadth_60d_lag1": [0.62],
            "benchmark_momentum_20d_lag1": [-0.01],
        },
        index=["000001.SZ"],
    )
    assert _risk_target_weight(overheated_today, overheated_spec, nav=1.0, peak_nav=1.0) == 0.06
    overheated_today["benchmark_momentum_20d_lag1"] = 0.01
    assert _risk_target_weight(overheated_today, overheated_spec, nav=1.0, peak_nav=1.0) == 1.0

    fuse_payload = deepcopy(base_payload)
    fuse_overlay = fuse_payload["risk"]["risk_overlay"]
    fuse_overlay.update(
        {
            "enabled": True,
            "use_trend": False,
            "use_momentum": False,
            "use_recovery": False,
            "use_staged_recovery": False,
            "use_window_fuse": True,
            "fuse_drawdown_limit": -0.99,
            "fuse_rolling_return_limit": -0.99,
            "fuse_consecutive_loss_days": 99,
            "fuse_rolling_days": 5,
            "fuse_weight": 0.17,
            "use_downtrend_loss_cluster_fuse": True,
            "downtrend_fuse_consecutive_loss_days": 2,
            "downtrend_fuse_drawdown_limit": -0.99,
            "downtrend_fuse_rolling_return_limit": -0.99,
            "downtrend_fuse_include_recovery": True,
            "fuse_reentry_requires_market_recovery": False,
            "fuse_reentry_requires_volatility_calm": False,
        }
    )
    fuse_spec = StrategySpec.from_dict(fuse_payload)
    state = _WindowFuseState()
    downtrend_today = pd.DataFrame(
        {
            "benchmark_trend_200d_lag1": [0.0],
            "benchmark_momentum_20d_lag1": [0.010],
        },
        index=["000001.SZ"],
    )
    _update_window_fuse_state(downtrend_today, fuse_spec.risk.risk_overlay, state, nav=0.999, peak_nav=1.0, daily_return=-0.001)
    assert not state.active
    _update_window_fuse_state(downtrend_today, fuse_spec.risk.risk_overlay, state, nav=0.998, peak_nav=1.0, daily_return=-0.001)
    assert state.active
    assert _risk_target_weight(downtrend_today, fuse_spec, nav=0.998, peak_nav=1.0, fuse_state=state) == 0.17

    uptrend_state = _WindowFuseState()
    uptrend_today = downtrend_today.copy()
    uptrend_today["benchmark_trend_200d_lag1"] = 1.0
    uptrend_today["benchmark_momentum_20d_lag1"] = -0.010
    _update_window_fuse_state(uptrend_today, fuse_spec.risk.risk_overlay, uptrend_state, nav=0.999, peak_nav=1.0, daily_return=-0.001)
    _update_window_fuse_state(uptrend_today, fuse_spec.risk.risk_overlay, uptrend_state, nav=0.998, peak_nav=1.0, daily_return=-0.001)
    assert not uptrend_state.active


if __name__ == "__main__":
    main()
