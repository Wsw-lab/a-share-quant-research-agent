from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd

from .backtest import _prepare_data, run_backtest
from .spec import StrategySpec


def run_parameter_sensitivity(data: pd.DataFrame, spec: StrategySpec) -> pd.DataFrame:
    scenarios = _build_scenarios(spec)
    rows: list[dict[str, object]] = []
    baseline_return = None
    baseline_drawdown = None
    prepared_data = _prepare_data(data)

    for label, dimension, value, variant in scenarios:
        try:
            result = run_backtest(prepared_data, variant)
            metrics = result.metrics
            row = {
                "scenario": label,
                "dimension": dimension,
                "value": value,
                "status": "ok",
                "annualized_return": metrics.get("annualized_return", 0.0),
                "max_drawdown": metrics.get("max_drawdown", 0.0),
                "sharpe": metrics.get("sharpe", 0.0),
                "trade_count": metrics.get("trade_count", 0.0),
                "turnover": metrics.get("turnover", 0.0),
                "end_equity": metrics.get("end_equity", 0.0),
            }
            if label == "baseline":
                baseline_return = float(row["annualized_return"])
                baseline_drawdown = float(row["max_drawdown"])
        except Exception as exc:  # pragma: no cover - retained in artifact for diagnosis
            row = {
                "scenario": label,
                "dimension": dimension,
                "value": value,
                "status": "error",
                "error": str(exc),
                "annualized_return": pd.NA,
                "max_drawdown": pd.NA,
                "sharpe": pd.NA,
                "trade_count": pd.NA,
                "turnover": pd.NA,
                "end_equity": pd.NA,
            }
        rows.append(row)

    frame = pd.DataFrame(rows)
    if baseline_return is not None:
        frame["annualized_return_delta"] = pd.to_numeric(frame["annualized_return"], errors="coerce") - baseline_return
    else:
        frame["annualized_return_delta"] = pd.NA
    if baseline_drawdown is not None:
        frame["max_drawdown_delta"] = pd.to_numeric(frame["max_drawdown"], errors="coerce") - baseline_drawdown
    else:
        frame["max_drawdown_delta"] = pd.NA
    return frame


def render_sensitivity_markdown(sensitivity: pd.DataFrame) -> str:
    lines = [
        "## Parameter Sensitivity",
        "",
        "| Scenario | Dimension | Value | Ann. Return | Max Drawdown | Trades | Delta |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    if sensitivity.empty:
        lines.append("| none | - | 0 | 0.00% | 0.00% | 0 | 0.00% |")
        return "\n".join(lines) + "\n"

    for _, row in sensitivity.iterrows():
        if row.get("status") != "ok":
            lines.append(f"| {row['scenario']} | {row['dimension']} | {row['value']} | error | error | 0 | error |")
            continue
        lines.append(
            "| {scenario} | {dimension} | {value} | {annualized_return:.2%} | "
            "{max_drawdown:.2%} | {trade_count:.0f} | {annualized_return_delta:.2%} |".format(
                scenario=row["scenario"],
                dimension=row["dimension"],
                value=row["value"],
                annualized_return=float(row["annualized_return"]),
                max_drawdown=float(row["max_drawdown"]),
                trade_count=float(row["trade_count"]),
                annualized_return_delta=float(row["annualized_return_delta"]),
            )
        )

    lines.extend(["", *_sensitivity_notes(sensitivity), ""])
    return "\n".join(lines)


def write_sensitivity_artifact(output_dir: str | Path, sensitivity: pd.DataFrame) -> Path:
    artifact_dir = Path(output_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / "sensitivity.csv"
    sensitivity.to_csv(path, index=False)
    return path


def _build_scenarios(spec: StrategySpec) -> list[tuple[str, str, object, StrategySpec]]:
    scenarios: list[tuple[str, str, object, StrategySpec]] = []
    seen: set[tuple[object, ...]] = set()

    def add(label: str, dimension: str, value: object, variant: StrategySpec) -> None:
        key = (
            variant.portfolio.max_positions,
            variant.costs.slippage_bps,
            variant.universe.min_amount,
            variant.rebalance.frequency,
        )
        if key in seen:
            return
        seen.add(key)
        scenarios.append((label, dimension, value, variant))

    add("baseline", "baseline", "base", spec)

    position_values = sorted(
        {
            max(1, spec.portfolio.max_positions // 2),
            spec.portfolio.max_positions,
            min(200, max(spec.portfolio.max_positions + 1, round(spec.portfolio.max_positions * 1.5))),
        }
    )
    for max_positions in position_values:
        add(
            f"positions_{max_positions}",
            "max_positions",
            max_positions,
            replace(spec, portfolio=replace(spec.portfolio, max_positions=int(max_positions))),
        )

    for multiplier in (2, 3):
        slippage_bps = spec.costs.slippage_bps * multiplier
        add(
            f"slippage_{slippage_bps:g}bps",
            "slippage_bps",
            f"{slippage_bps:g}",
            replace(spec, costs=replace(spec.costs, slippage_bps=slippage_bps)),
        )

    amount_values = _amount_scenarios(spec.universe.min_amount)
    for amount in amount_values:
        add(
            f"min_amount_{_format_amount(amount)}",
            "min_amount",
            _format_amount(amount),
            replace(spec, universe=replace(spec.universe, min_amount=float(amount))),
        )

    alternate_frequency = "weekly" if spec.rebalance.frequency == "monthly" else "monthly"
    add(
        f"frequency_{alternate_frequency}",
        "frequency",
        alternate_frequency,
        replace(spec, rebalance=replace(spec.rebalance, frequency=alternate_frequency)),
    )
    return scenarios


def _amount_scenarios(base_amount: float) -> tuple[float, ...]:
    if base_amount > 0:
        return tuple(sorted({base_amount * 0.5, base_amount, base_amount * 1.5}))
    return (0.0, 50_000_000.0, 100_000_000.0)


def _format_amount(value: float) -> str:
    if value >= 100_000_000:
        return f"{value / 100_000_000:g}e"
    if value >= 10_000:
        return f"{value / 10_000:g}w"
    return f"{value:g}"


def _sensitivity_notes(sensitivity: pd.DataFrame) -> list[str]:
    ok = sensitivity[sensitivity["status"] == "ok"].copy()
    ok["annualized_return"] = pd.to_numeric(ok["annualized_return"], errors="coerce")
    ok = ok.dropna(subset=["annualized_return"])
    if ok.empty:
        return ["Sensitivity notes: no successful scenarios."]

    positive_share = float((ok["annualized_return"] > 0).mean())
    annualized_range = float(ok["annualized_return"].max() - ok["annualized_return"].min())
    notes = [
        f"Sensitivity notes: {positive_share:.0%} of successful scenarios have positive annualized return.",
        f"Sensitivity annualized return range: {annualized_range:.2%}.",
    ]
    if positive_share < 0.75:
        notes.append("Robustness warning: fewer than 75% of scenarios remain positive.")
    if annualized_range > 0.15:
        notes.append("Robustness warning: scenario spread is wide, so parameter dependence needs more testing.")
    return notes
