from __future__ import annotations

from dataclasses import replace

import pandas as pd

from .backtest import BacktestResult, run_backtest
from .spec import StrategySpec


def audit_backtest(data: pd.DataFrame, result: BacktestResult) -> dict[str, object]:
    metrics = result.metrics
    red_flags: list[str] = []
    warnings: list[str] = []

    if metrics.get("trade_count", 0) < 30:
        red_flags.append("交易次数少于 30，样本不足。")
    if metrics.get("max_drawdown", 0) < -0.30:
        red_flags.append("最大回撤超过 30%。")
    if metrics.get("annualized_return", 0) <= 0:
        red_flags.append("年化收益为负或接近无效。")
    if metrics.get("turnover", 0) > 24:
        warnings.append("换手率偏高，实盘滑点和冲击成本可能显著放大。")

    years_tested = _years_tested(result.equity_curve)
    if years_tested < 0.75:
        red_flags.append("回测周期短于 9 个月，无法评估跨阶段稳定性。")
    elif years_tested < 3:
        warnings.append("回测周期短于 3 年，样本周期偏短。")

    factor_coverage = _factor_coverage(data, result.spec)
    for _, row in factor_coverage.iterrows():
        if row["coverage"] < 0.70:
            red_flags.append(f"因子 {row['factor']} 有效覆盖率低于 70%。")
        elif row["coverage"] < 0.90:
            warnings.append(f"因子 {row['factor']} 有效覆盖率低于 90%。")

    yearly = _yearly_returns(result.equity_curve)
    if not yearly.empty:
        positive_years = int((yearly["return"] > 0).sum())
        if positive_years < max(1, len(yearly) // 2):
            red_flags.append("正收益年份不足一半，策略可能强依赖特定行情。")

    stress = _slippage_stress(data, result.spec)
    base_return = metrics.get("annualized_return", 0.0)
    stressed_return = stress["annualized_return"]
    if base_return > 0 and stressed_return < base_return * 0.5:
        red_flags.append("滑点提升后年化收益低于基准回测的一半。")
    if stressed_return <= 0:
        red_flags.append("高滑点压力测试后收益失效。")

    verdict = "deploy_simulation"
    if red_flags:
        verdict = "abandon" if len(red_flags) >= 2 else "refine"
    elif warnings:
        verdict = "refine"

    return {
        "verdict": verdict,
        "red_flags": red_flags,
        "warnings": warnings,
        "yearly_returns": yearly,
        "slippage_stress": stress,
        "factor_coverage": factor_coverage,
        "years_tested": years_tested,
    }


def _yearly_returns(equity_curve: pd.DataFrame) -> pd.DataFrame:
    if equity_curve.empty:
        return pd.DataFrame(columns=["year", "return"])
    curve = equity_curve.copy()
    curve["year"] = pd.to_datetime(curve["date"]).dt.year
    rows = []
    for year, group in curve.groupby("year"):
        start = float(group["equity"].iloc[0])
        end = float(group["equity"].iloc[-1])
        rows.append({"year": int(year), "return": end / start - 1})
    return pd.DataFrame(rows)


def _slippage_stress(data: pd.DataFrame, spec: StrategySpec) -> dict[str, float]:
    stressed_costs = replace(spec.costs, slippage_bps=spec.costs.slippage_bps * 3)
    stressed_spec = replace(spec, costs=stressed_costs)
    stressed = run_backtest(data, stressed_spec)
    return {
        "slippage_bps": stressed_costs.slippage_bps,
        "annualized_return": stressed.metrics.get("annualized_return", 0.0),
        "max_drawdown": stressed.metrics.get("max_drawdown", 0.0),
        "trade_count": stressed.metrics.get("trade_count", 0.0),
    }


def _years_tested(equity_curve: pd.DataFrame) -> float:
    if equity_curve.empty:
        return 0.0
    start = pd.Timestamp(equity_curve["date"].iloc[0])
    end = pd.Timestamp(equity_curve["date"].iloc[-1])
    return max((end - start).days / 365.25, 0.0)


def _factor_coverage(data: pd.DataFrame, spec: StrategySpec) -> pd.DataFrame:
    rows = []
    total_rows = max(len(data), 1)
    for factor in spec.factors:
        if factor.field not in data:
            rows.append({"factor": factor.field, "non_null": 0, "total": total_rows, "coverage": 0.0})
            continue
        non_null = int(data[factor.field].notna().sum())
        rows.append(
            {
                "factor": factor.field,
                "non_null": non_null,
                "total": total_rows,
                "coverage": non_null / total_rows,
            }
        )
    return pd.DataFrame(rows)

