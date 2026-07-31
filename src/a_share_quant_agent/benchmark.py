from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def compare_to_benchmark(equity_curve: pd.DataFrame, benchmark_quotes: pd.DataFrame) -> dict[str, object]:
    comparison = _aligned_comparison(equity_curve, benchmark_quotes)
    metrics = _comparison_metrics(comparison)
    return {"comparison": comparison, "metrics": metrics}


def render_benchmark_markdown(benchmark: dict[str, object]) -> str:
    metrics = benchmark["metrics"]
    lines = [
        "## Benchmark Comparison",
        "",
        f"Benchmark: {metrics.get('benchmark_name', 'n/a')} ({metrics.get('benchmark_code', 'n/a')})",
        "",
        "| Metric | Strategy | Benchmark | Difference |",
        "|---|---:|---:|---:|",
        _metric_row("Total return", metrics, "strategy_total_return", "benchmark_total_return", pct=True),
        _metric_row("Annualized return", metrics, "strategy_annualized_return", "benchmark_annualized_return", pct=True),
        _metric_row("Max drawdown", metrics, "strategy_max_drawdown", "benchmark_max_drawdown", pct=True),
        _metric_row("Annualized volatility", metrics, "strategy_annualized_volatility", "benchmark_annualized_volatility", pct=True),
        _metric_row("Sharpe", metrics, "strategy_sharpe", "benchmark_sharpe", pct=False),
        "",
        "| Active Metric | Value |",
        "|---|---:|",
        f"| Excess annualized return | {metrics.get('excess_annualized_return', 0):.2%} |",
        f"| Tracking error | {metrics.get('tracking_error', 0):.2%} |",
        f"| Information ratio | {metrics.get('information_ratio', 0):.2f} |",
        f"| Daily return correlation | {metrics.get('daily_return_correlation', 0):.2f} |",
        f"| Aligned trading days | {metrics.get('aligned_days', 0):.0f} |",
        "",
    ]
    if metrics.get("excess_annualized_return", 0) < 0:
        lines.extend(["Benchmark notes:", "- Strategy underperformed the benchmark over the aligned test window.", ""])
    return "\n".join(lines)


def write_benchmark_artifacts(output_dir: str | Path, benchmark: dict[str, object]) -> dict[str, Path]:
    artifact_dir = Path(output_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    comparison_path = artifact_dir / "benchmark_comparison.csv"
    metrics_path = artifact_dir / "benchmark_metrics.json"
    comparison = benchmark["comparison"]
    if isinstance(comparison, pd.DataFrame):
        output = comparison.copy()
        for column in output.columns:
            if pd.api.types.is_datetime64_any_dtype(output[column]):
                output[column] = output[column].dt.strftime("%Y-%m-%d")
        output.to_csv(comparison_path, index=False)
    metrics_path.write_text(json.dumps(_json_ready(benchmark["metrics"]), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return {"benchmark_comparison": comparison_path, "benchmark_metrics": metrics_path}


def _aligned_comparison(equity_curve: pd.DataFrame, benchmark_quotes: pd.DataFrame) -> pd.DataFrame:
    if equity_curve.empty or benchmark_quotes.empty:
        return pd.DataFrame()
    strategy = equity_curve[["date", "equity"]].copy()
    strategy["date"] = pd.to_datetime(strategy["date"])
    strategy.sort_values("date", inplace=True)
    strategy["strategy_daily_return"] = strategy["equity"].pct_change().fillna(0.0)

    benchmark = benchmark_quotes[["date", "indexCode", "indexName", "closePrice"]].copy()
    benchmark["date"] = pd.to_datetime(benchmark["date"])
    benchmark.sort_values("date", inplace=True)
    benchmark = benchmark.drop_duplicates("date", keep="last")
    benchmark["benchmark_daily_return"] = benchmark["closePrice"].pct_change().fillna(0.0)

    merged = strategy.merge(benchmark, on="date", how="inner")
    if merged.empty:
        return merged
    start_equity = float(merged["equity"].iloc[0])
    start_benchmark = float(merged["closePrice"].iloc[0])
    merged["benchmark_equity"] = start_equity * merged["closePrice"] / start_benchmark
    merged["active_daily_return"] = merged["strategy_daily_return"] - merged["benchmark_daily_return"]
    return merged


def _comparison_metrics(comparison: pd.DataFrame) -> dict[str, float | str]:
    if comparison.empty:
        return {
            "benchmark_code": "n/a",
            "benchmark_name": "n/a",
            "aligned_days": 0.0,
        }
    strategy_metrics = _series_metrics(comparison["date"], comparison["equity"], comparison["strategy_daily_return"])
    benchmark_metrics = _series_metrics(
        comparison["date"],
        comparison["benchmark_equity"],
        comparison["benchmark_daily_return"],
    )
    active_returns = comparison["active_daily_return"].fillna(0.0)
    tracking_error = float(active_returns.std() * (252**0.5))
    information_ratio = float(active_returns.mean() * 252 / tracking_error) if tracking_error > 0 else 0.0
    correlation = float(comparison["strategy_daily_return"].corr(comparison["benchmark_daily_return"]))
    if pd.isna(correlation):
        correlation = 0.0
    return {
        "benchmark_code": str(comparison["indexCode"].iloc[0]),
        "benchmark_name": str(comparison["indexName"].iloc[0]),
        "aligned_days": float(len(comparison)),
        "strategy_total_return": strategy_metrics["total_return"],
        "strategy_annualized_return": strategy_metrics["annualized_return"],
        "strategy_max_drawdown": strategy_metrics["max_drawdown"],
        "strategy_annualized_volatility": strategy_metrics["annualized_volatility"],
        "strategy_sharpe": strategy_metrics["sharpe"],
        "benchmark_total_return": benchmark_metrics["total_return"],
        "benchmark_annualized_return": benchmark_metrics["annualized_return"],
        "benchmark_max_drawdown": benchmark_metrics["max_drawdown"],
        "benchmark_annualized_volatility": benchmark_metrics["annualized_volatility"],
        "benchmark_sharpe": benchmark_metrics["sharpe"],
        "excess_total_return": strategy_metrics["total_return"] - benchmark_metrics["total_return"],
        "excess_annualized_return": strategy_metrics["annualized_return"] - benchmark_metrics["annualized_return"],
        "tracking_error": tracking_error,
        "information_ratio": information_ratio,
        "daily_return_correlation": correlation,
    }


def _series_metrics(dates: pd.Series, equity: pd.Series, daily_returns: pd.Series) -> dict[str, float]:
    start = float(equity.iloc[0])
    end = float(equity.iloc[-1])
    total_return = end / start - 1 if start else 0.0
    years = max((pd.Timestamp(dates.iloc[-1]) - pd.Timestamp(dates.iloc[0])).days / 365.25, 1 / 365.25)
    annualized_return = (1 + total_return) ** (1 / years) - 1
    drawdown = equity / equity.cummax() - 1
    volatility = float(daily_returns.std() * (252**0.5))
    return {
        "total_return": float(total_return),
        "annualized_return": float(annualized_return),
        "max_drawdown": float(drawdown.min()),
        "annualized_volatility": volatility,
        "sharpe": float(annualized_return / volatility) if volatility > 0 else 0.0,
    }


def _metric_row(
    label: str,
    metrics: dict[str, object],
    strategy_key: str,
    benchmark_key: str,
    pct: bool,
) -> str:
    strategy = float(metrics.get(strategy_key, 0.0))
    benchmark = float(metrics.get(benchmark_key, 0.0))
    difference = strategy - benchmark
    if pct:
        return f"| {label} | {strategy:.2%} | {benchmark:.2%} | {difference:.2%} |"
    return f"| {label} | {strategy:.2f} | {benchmark:.2f} | {difference:.2f} |"


def _json_ready(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value
