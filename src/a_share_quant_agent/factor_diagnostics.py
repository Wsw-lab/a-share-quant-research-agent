from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .spec import FactorSpec, StrategySpec


DEFAULT_HORIZONS = (5, 20, 60)


def run_factor_ic_diagnostics(
    data: pd.DataFrame,
    spec: StrategySpec,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    min_observations: int = 20,
    use_rebalance_dates: bool = True,
) -> dict[str, object]:
    if data.empty or not spec.factors:
        return _empty_result("No data or factors are available for factor IC diagnostics.")
    if min_observations < 2:
        raise ValueError("Factor IC min_observations must be at least 2.")
    cleaned_horizons = tuple(sorted({int(horizon) for horizon in horizons if int(horizon) > 0}))
    if not cleaned_horizons:
        raise ValueError("Factor IC horizons must include at least one positive integer.")

    panel = _copy_without_panel_index(data)
    panel["date"] = pd.to_datetime(panel["date"])
    panel.sort_values(["symbol", "date"], inplace=True)
    for horizon in cleaned_horizons:
        panel[f"forward_return_{horizon}d"] = panel.groupby("symbol")["close"].shift(-horizon) / panel["close"] - 1

    dates = pd.DatetimeIndex(sorted(panel["date"].dropna().unique()))
    if use_rebalance_dates:
        selected_dates = set(_rebalance_dates(dates, spec.rebalance.frequency))
    else:
        selected_dates = set(dates)
    eligible = _eligible_mask(panel, spec)

    rows: list[dict[str, object]] = []
    for date in sorted(selected_dates):
        today = panel[(panel["date"] == date) & eligible].copy()
        if today.empty:
            continue
        for factor in spec.factors:
            if factor.field not in today:
                continue
            score = _factor_score(today[factor.field], factor)
            for horizon in cleaned_horizons:
                return_column = f"forward_return_{horizon}d"
                cross_section = pd.DataFrame(
                    {
                        "score": score,
                        "forward_return": pd.to_numeric(today[return_column], errors="coerce"),
                    }
                ).dropna()
                observations = int(len(cross_section))
                if observations < min_observations:
                    continue
                ic = _spearman_ic(cross_section["score"], cross_section["forward_return"])
                if pd.isna(ic):
                    continue
                rows.append(
                    {
                        "date": pd.Timestamp(date).strftime("%Y-%m-%d"),
                        "factor": factor.field,
                        "factor_direction": factor.direction,
                        "horizon_days": horizon,
                        "observations": observations,
                        "ic": float(ic),
                        "long_short_spread": _long_short_spread(cross_section),
                    }
                )

    detail = pd.DataFrame(rows)
    summary = _summary(detail)
    metrics = _metrics(detail, summary, cleaned_horizons, min_observations, use_rebalance_dates)
    return {
        "detail": detail,
        "summary": summary,
        "metrics": metrics,
        "notes": tuple(_factor_ic_notes(summary, metrics)),
    }


def render_factor_ic_markdown(diagnostics: dict[str, object]) -> str:
    metrics = diagnostics["metrics"]
    lines = [
        "## Factor IC Diagnostics",
        "",
        "IC compares factor values at the signal date with later returns. Ascending factors are sign-flipped, so positive IC means the strategy's preferred direction worked.",
        "",
    ]
    if metrics.get("status") != "ok":
        lines.extend([f"Factor IC unavailable: {metrics.get('reason', 'unknown reason')}", ""])
        return "\n".join(lines)

    lines.extend(
        [
            "| Factor | Horizon | Periods | Mean IC | IC Positive | Mean Spread | t-stat | Status |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    summary = diagnostics["summary"]
    if isinstance(summary, pd.DataFrame) and not summary.empty:
        for _, row in summary.iterrows():
            lines.append(
                "| {factor} | {horizon:.0f}d | {periods:.0f} | {mean_ic:.3f} | {positive:.0%} | "
                "{spread:.2%} | {t_stat:.2f} | {status} |".format(
                    factor=row["factor"],
                    horizon=float(row["horizon_days"]),
                    periods=float(row["periods"]),
                    mean_ic=float(row["mean_ic"]),
                    positive=float(row["ic_positive_rate"]),
                    spread=float(row["mean_long_short_spread"]),
                    t_stat=float(row["ic_t_stat"]),
                    status=row["status"],
                )
            )
    else:
        lines.append("| none | 0d | 0 | 0.000 | 0% | 0.00% | 0.00 | insufficient_data |")

    lines.extend(["", *diagnostics["notes"], ""])
    return "\n".join(lines)


def write_factor_ic_artifacts(output_dir: str | Path, diagnostics: dict[str, object]) -> dict[str, Path]:
    artifact_dir = Path(output_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    detail_path = artifact_dir / "factor_ic.csv"
    summary_path = artifact_dir / "factor_ic_summary.csv"
    metrics_path = artifact_dir / "factor_ic_metrics.json"
    _write_csv(diagnostics.get("detail"), detail_path)
    _write_csv(diagnostics.get("summary"), summary_path)
    metrics_path.write_text(
        json.dumps(_json_ready(diagnostics["metrics"]), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "factor_ic": detail_path,
        "factor_ic_summary": summary_path,
        "factor_ic_metrics": metrics_path,
    }


def _eligible_mask(panel: pd.DataFrame, spec: StrategySpec) -> pd.Series:
    eligible = pd.Series(True, index=panel.index, dtype=bool)
    if "is_stock_master_member" in panel:
        eligible &= panel["is_stock_master_member"].fillna(False).astype(bool)
    if "is_universe_member" in panel:
        eligible &= panel["is_universe_member"].fillna(False).astype(bool)
    if spec.universe.exclude_st and "is_st" in panel:
        eligible &= ~panel["is_st"].fillna(False).astype(bool)
    if spec.universe.exclude_suspended and "is_suspended" in panel:
        eligible &= ~panel["is_suspended"].fillna(False).astype(bool)
    if spec.universe.min_amount > 0 and "amount" in panel:
        eligible &= pd.to_numeric(panel["amount"], errors="coerce").fillna(0.0) >= spec.universe.min_amount
    return eligible


def _copy_without_panel_index(data: pd.DataFrame) -> pd.DataFrame:
    if isinstance(data.index, pd.MultiIndex) and set(data.index.names) >= {"date", "symbol"}:
        return data.reset_index(drop=True)
    return data.copy()


def _rebalance_dates(dates: pd.DatetimeIndex, frequency: str) -> list[pd.Timestamp]:
    if dates.empty:
        return []
    series = pd.Series(dates, index=dates)
    if frequency == "monthly":
        return [group.iloc[0] for _, group in series.groupby(dates.to_period("M"))]
    if frequency == "weekly":
        return [group.iloc[0] for _, group in series.groupby(dates.to_period("W"))]
    return list(dates)


def _factor_score(values: pd.Series, factor: FactorSpec) -> pd.Series:
    score = pd.to_numeric(values, errors="coerce")
    if factor.direction == "asc":
        score = -score
    return score


def _long_short_spread(cross_section: pd.DataFrame) -> float:
    ranks = cross_section["score"].rank(pct=True, method="first")
    top = cross_section.loc[ranks > 0.8, "forward_return"]
    bottom = cross_section.loc[ranks <= 0.2, "forward_return"]
    if top.empty or bottom.empty:
        return 0.0
    return float(top.mean() - bottom.mean())


def _spearman_ic(score: pd.Series, forward_return: pd.Series) -> float:
    ranked_score = score.rank(method="average")
    ranked_return = forward_return.rank(method="average")
    if ranked_score.nunique(dropna=True) < 2 or ranked_return.nunique(dropna=True) < 2:
        return float("nan")
    return float(ranked_score.corr(ranked_return))


def _summary(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame(
            columns=[
                "factor",
                "horizon_days",
                "periods",
                "mean_ic",
                "median_ic",
                "ic_std",
                "ic_t_stat",
                "ic_positive_rate",
                "mean_long_short_spread",
                "avg_observations",
                "status",
            ]
        )

    rows: list[dict[str, object]] = []
    for (factor, horizon), group in detail.groupby(["factor", "horizon_days"], sort=True):
        ic_values = pd.to_numeric(group["ic"], errors="coerce").dropna()
        spread_values = pd.to_numeric(group["long_short_spread"], errors="coerce").dropna()
        periods = int(len(ic_values))
        mean_ic = float(ic_values.mean()) if periods else 0.0
        ic_std = float(ic_values.std(ddof=1)) if periods > 1 else 0.0
        t_stat = float(mean_ic / (ic_std / (periods**0.5))) if ic_std > 0 and periods > 1 else 0.0
        rows.append(
            {
                "factor": factor,
                "horizon_days": int(horizon),
                "periods": periods,
                "mean_ic": mean_ic,
                "median_ic": float(ic_values.median()) if periods else 0.0,
                "ic_std": ic_std,
                "ic_t_stat": t_stat,
                "ic_positive_rate": float((ic_values > 0).mean()) if periods else 0.0,
                "mean_long_short_spread": float(spread_values.mean()) if not spread_values.empty else 0.0,
                "avg_observations": float(group["observations"].mean()),
                "status": _summary_status(periods, mean_ic, t_stat),
            }
        )
    return pd.DataFrame(rows).sort_values(["factor", "horizon_days"]).reset_index(drop=True)


def _summary_status(periods: int, mean_ic: float, t_stat: float) -> str:
    if periods < 3:
        return "low_period_count"
    if mean_ic < -0.02:
        return "adverse"
    if abs(mean_ic) < 0.02:
        return "weak"
    if t_stat >= 1.5:
        return "supportive"
    return "positive_but_noisy"


def _metrics(
    detail: pd.DataFrame,
    summary: pd.DataFrame,
    horizons: tuple[int, ...],
    min_observations: int,
    use_rebalance_dates: bool,
) -> dict[str, object]:
    if summary.empty:
        return {
            "status": "unavailable",
            "reason": "No factor/date/horizon cross-section met the minimum observation threshold.",
            "detail_rows": 0.0,
            "summary_rows": 0.0,
            "horizons": horizons,
            "min_observations": min_observations,
            "use_rebalance_dates": use_rebalance_dates,
        }

    best = summary.sort_values(["mean_ic", "ic_t_stat"], ascending=False).iloc[0]
    adverse_count = int((summary["status"] == "adverse").sum())
    supportive_count = int((summary["status"] == "supportive").sum())
    return {
        "status": "ok",
        "detail_rows": float(len(detail)),
        "summary_rows": float(len(summary)),
        "horizons": horizons,
        "min_observations": min_observations,
        "use_rebalance_dates": use_rebalance_dates,
        "best_factor": str(best["factor"]),
        "best_horizon_days": float(best["horizon_days"]),
        "best_mean_ic": float(best["mean_ic"]),
        "best_t_stat": float(best["ic_t_stat"]),
        "supportive_count": float(supportive_count),
        "adverse_count": float(adverse_count),
    }


def _factor_ic_notes(summary: pd.DataFrame, metrics: dict[str, object]) -> list[str]:
    if metrics.get("status") != "ok":
        return [str(metrics.get("reason", "No factor IC diagnostics were generated."))]

    notes = [
        "Factor IC is computed only on the same eligible universe used by the backtest when membership columns are present.",
        "Positive IC means the factor direction encoded in StrategySpec aligned with later returns.",
        "The sample is still short for statistical confidence; use longer histories before treating IC as stable.",
        "Best IC row: {factor} at {horizon:.0f}d, mean IC {mean_ic:.3f}, t-stat {t_stat:.2f}.".format(
            factor=metrics.get("best_factor", "n/a"),
            horizon=float(metrics.get("best_horizon_days", 0.0)),
            mean_ic=float(metrics.get("best_mean_ic", 0.0)),
            t_stat=float(metrics.get("best_t_stat", 0.0)),
        ),
    ]
    adverse = summary[summary["status"] == "adverse"] if not summary.empty else pd.DataFrame()
    if not adverse.empty:
        pairs = ", ".join(f"{row.factor}/{int(row.horizon_days)}d" for row in adverse.itertuples())
        notes.append(f"Adverse IC warning: {pairs}.")
    if float(metrics.get("supportive_count", 0.0)) == 0:
        notes.append("Robustness warning: no factor-horizon pair reached the supportive threshold.")
    return notes


def _empty_result(reason: str) -> dict[str, object]:
    return {
        "detail": pd.DataFrame(columns=["date", "factor", "horizon_days", "observations", "ic", "long_short_spread"]),
        "summary": _summary(pd.DataFrame()),
        "metrics": {"status": "unavailable", "reason": reason, "detail_rows": 0.0, "summary_rows": 0.0},
        "notes": (reason,),
    }


def _write_csv(value: object, path: Path) -> None:
    if not isinstance(value, pd.DataFrame):
        pd.DataFrame().to_csv(path, index=False)
        return
    value.to_csv(path, index=False)


def _json_ready(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value
