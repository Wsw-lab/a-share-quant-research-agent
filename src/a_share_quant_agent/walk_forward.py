from __future__ import annotations

from pathlib import Path

import pandas as pd

from .backtest import run_backtest
from .spec import StrategySpec


def run_walk_forward_validation(
    data: pd.DataFrame,
    spec: StrategySpec,
    train_months: int = 6,
    test_months: int = 3,
    step_months: int = 3,
    min_train_days: int = 80,
    min_test_days: int = 20,
) -> pd.DataFrame:
    if data.empty or "date" not in data:
        return pd.DataFrame()
    if train_months < 1 or test_months < 1 or step_months < 1:
        raise ValueError("Walk-forward train, test, and step months must be positive.")

    if isinstance(data.index, pd.MultiIndex) and list(data.index.names) == ["date", "symbol"]:
        panel = data
    else:
        panel = data.copy()
        panel["date"] = pd.to_datetime(panel["date"])
        panel.sort_values(["date", "symbol"], inplace=True)
    all_dates = pd.DatetimeIndex(sorted(panel["date"].dropna().unique()))
    if all_dates.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    cursor = pd.Timestamp(all_dates[0]).normalize()
    last_date = pd.Timestamp(all_dates[-1]).normalize()
    max_windows = 120

    while cursor < last_date and len(rows) < max_windows:
        train_start = cursor
        train_end = cursor + pd.DateOffset(months=train_months) - pd.Timedelta(days=1)
        test_start = cursor + pd.DateOffset(months=train_months)
        test_end = test_start + pd.DateOffset(months=test_months) - pd.Timedelta(days=1)
        if test_start > last_date:
            break

        train_slice = panel[(panel["date"] >= train_start) & (panel["date"] <= train_end)].copy()
        test_slice = panel[(panel["date"] >= test_start) & (panel["date"] <= test_end)].copy()
        train_days = int(train_slice["date"].nunique())
        test_days = int(test_slice["date"].nunique())
        if train_days >= min_train_days and test_days >= min_test_days:
            row = _run_window(len(rows) + 1, train_slice, test_slice, spec)
            row["configured_train_months"] = train_months
            row["configured_test_months"] = test_months
            row["configured_step_months"] = step_months
            rows.append(row)

        cursor = cursor + pd.DateOffset(months=step_months)

    return pd.DataFrame(rows)


def render_walk_forward_markdown(walk_forward: pd.DataFrame) -> str:
    lines = [
        "## Walk-Forward Validation",
        "",
        "Same-rule train and validation windows. The MVP does not optimize parameters inside the train window; it compares whether the fixed strategy behavior survives later data.",
        "",
        "| Window | Train | Test | Train Ann. | Test Ann. | OOS Ratio | Test DD | Test Trades | Status |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    if walk_forward.empty:
        lines.extend(
            [
                "| none | - | - | 0.00% | 0.00% | n/a | 0.00% | 0 | insufficient_data |",
                "",
                "Walk-forward notes: extend the date range or reduce train/test months to generate validation windows.",
                "",
            ]
        )
        return "\n".join(lines)

    for _, row in walk_forward.iterrows():
        lines.append(
            "| {window} | {train_start} to {train_end} | {test_start} to {test_end} | "
            "{train_annualized_return} | {test_annualized_return} | {oos_ratio} | "
            "{test_max_drawdown} | {test_trade_count} | {status} |".format(
                window=row["window"],
                train_start=row["train_start"],
                train_end=row["train_end"],
                test_start=row["test_start"],
                test_end=row["test_end"],
                train_annualized_return=_format_pct(row.get("train_annualized_return")),
                test_annualized_return=_format_pct(row.get("test_annualized_return")),
                oos_ratio=_format_float(row.get("oos_ratio")),
                test_max_drawdown=_format_pct(row.get("test_max_drawdown")),
                test_trade_count=_format_count(row.get("test_trade_count")),
                status=row["status"],
            )
        )

    lines.extend(["", *_walk_forward_notes(walk_forward), ""])
    return "\n".join(lines)


def write_walk_forward_artifact(output_dir: str | Path, walk_forward: pd.DataFrame) -> Path:
    artifact_dir = Path(output_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / "walk_forward.csv"
    walk_forward.to_csv(path, index=False)
    return path


def _run_window(
    window: int,
    train_slice: pd.DataFrame,
    test_slice: pd.DataFrame,
    spec: StrategySpec,
) -> dict[str, object]:
    row: dict[str, object] = {
        "window": window,
        "train_start": _date_text(train_slice["date"].min()),
        "train_end": _date_text(train_slice["date"].max()),
        "test_start": _date_text(test_slice["date"].min()),
        "test_end": _date_text(test_slice["date"].max()),
        "train_days": int(train_slice["date"].nunique()),
        "test_days": int(test_slice["date"].nunique()),
        "train_symbols": int(train_slice["symbol"].nunique()),
        "test_symbols": int(test_slice["symbol"].nunique()),
    }
    try:
        train_result = run_backtest(train_slice, spec)
        test_result = run_backtest(test_slice, spec)
    except Exception as exc:  # pragma: no cover - retained in artifact for diagnosis
        row.update(
            {
                "status": "error",
                "error": str(exc),
                "train_annualized_return": pd.NA,
                "test_annualized_return": pd.NA,
                "oos_ratio": pd.NA,
            }
        )
        return row

    train_metrics = train_result.metrics
    test_metrics = test_result.metrics
    train_ann = float(train_metrics.get("annualized_return", 0.0))
    test_ann = float(test_metrics.get("annualized_return", 0.0))
    oos_ratio = test_ann / train_ann if train_ann > 0 else pd.NA
    row.update(
        {
            "status": _window_status(train_ann, test_ann, float(test_metrics.get("trade_count", 0.0))),
            "train_total_return": train_metrics.get("total_return", 0.0),
            "train_annualized_return": train_ann,
            "train_max_drawdown": train_metrics.get("max_drawdown", 0.0),
            "train_sharpe": train_metrics.get("sharpe", 0.0),
            "train_trade_count": train_metrics.get("trade_count", 0.0),
            "test_total_return": test_metrics.get("total_return", 0.0),
            "test_annualized_return": test_ann,
            "test_max_drawdown": test_metrics.get("max_drawdown", 0.0),
            "test_sharpe": test_metrics.get("sharpe", 0.0),
            "test_trade_count": test_metrics.get("trade_count", 0.0),
            "oos_ratio": oos_ratio,
            "return_decay": test_ann - train_ann,
        }
    )
    return row


def _window_status(train_ann: float, test_ann: float, test_trade_count: float) -> str:
    if test_ann <= 0:
        return "failed_oos"
    if train_ann > 0 and test_ann < train_ann * 0.5:
        return "weak_oos"
    if test_trade_count < 10:
        return "low_trade_sample"
    return "ok"


def _walk_forward_notes(walk_forward: pd.DataFrame) -> list[str]:
    ok = walk_forward[walk_forward["status"] != "error"].copy()
    ok["test_annualized_return"] = pd.to_numeric(ok["test_annualized_return"], errors="coerce")
    ok = ok.dropna(subset=["test_annualized_return"])
    if ok.empty:
        return ["Walk-forward notes: no successful validation windows."]

    positive_share = float((ok["test_annualized_return"] > 0).mean())
    weak_count = int(ok["status"].isin({"failed_oos", "weak_oos"}).sum())
    notes = [
        f"Walk-forward notes: {positive_share:.0%} of validation windows have positive annualized return.",
        f"Walk-forward warnings: {weak_count} of {len(ok)} windows are failed or materially weaker out-of-sample.",
    ]
    if positive_share < 0.75:
        notes.append("Robustness warning: fewer than 75% of validation windows remain positive.")
    if weak_count:
        notes.append("Robustness warning: inspect regime dependence before considering paper trading.")
    return notes


def _date_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _format_pct(value: object) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{float(value):.2%}"


def _format_float(value: object) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{float(value):.2f}"


def _format_count(value: object) -> str:
    if pd.isna(value):
        return "0"
    return f"{float(value):.0f}"
