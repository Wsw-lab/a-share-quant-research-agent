from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import shutil
from typing import Any

import pandas as pd

from .backtest import BacktestResult
from .data_sources import DataLoadResult, data_trust_summary, universe_source_from_source


REGISTRY_JSONL = "run_registry.jsonl"
REGISTRY_CSV = "run_registry.csv"


def make_run_id(channel: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    return f"{channel}_{timestamp}"


def archive_cli_run(
    reports_root: str | Path,
    run_id: str,
    report_path: str | Path,
    spec_path: str | Path,
    artifact_dir: str | Path,
) -> dict[str, Path]:
    run_dir = Path(reports_root) / "cli_runs" / run_id
    archive_artifact_dir = run_dir / "artifacts"
    run_dir.mkdir(parents=True, exist_ok=True)
    if archive_artifact_dir.exists():
        shutil.rmtree(archive_artifact_dir)
    shutil.copytree(artifact_dir, archive_artifact_dir)
    archived_report = run_dir / "report.md"
    archived_spec = run_dir / "strategy_spec.json"
    shutil.copy2(report_path, archived_report)
    shutil.copy2(spec_path, archived_spec)
    return {
        "run_dir": run_dir,
        "artifact_dir": archive_artifact_dir,
        "report_path": archived_report,
        "spec_path": archived_spec,
    }


def register_run(
    reports_root: str | Path,
    *,
    run_id: str,
    channel: str,
    idea: str,
    loaded: DataLoadResult,
    result: BacktestResult,
    audit: dict[str, object],
    report_path: str | Path,
    spec_path: str | Path,
    artifact_paths: dict[str, Path],
    assumptions: tuple[str, ...] = (),
    warnings: tuple[str, ...] = (),
    benchmark: dict[str, object] | None = None,
    walk_forward: pd.DataFrame | None = None,
    sensitivity: pd.DataFrame | None = None,
    industry_exposure: dict[str, object] | None = None,
    factor_ic: dict[str, object] | None = None,
    attribution: dict[str, object] | None = None,
) -> dict[str, object]:
    reports_path = Path(reports_root)
    reports_path.mkdir(parents=True, exist_ok=True)
    entry = build_run_entry(
        run_id=run_id,
        channel=channel,
        idea=idea,
        loaded=loaded,
        result=result,
        audit=audit,
        report_path=Path(report_path),
        spec_path=Path(spec_path),
        artifact_paths=artifact_paths,
        assumptions=assumptions,
        warnings=warnings,
        benchmark=benchmark,
        walk_forward=walk_forward,
        sensitivity=sensitivity,
        industry_exposure=industry_exposure,
        factor_ic=factor_ic,
        attribution=attribution,
    )
    _append_jsonl(reports_path / REGISTRY_JSONL, entry)
    write_registry_csv(reports_path)
    return entry


def build_run_entry(
    *,
    run_id: str,
    channel: str,
    idea: str,
    loaded: DataLoadResult,
    result: BacktestResult,
    audit: dict[str, object],
    report_path: Path,
    spec_path: Path,
    artifact_paths: dict[str, Path],
    assumptions: tuple[str, ...] = (),
    warnings: tuple[str, ...] = (),
    benchmark: dict[str, object] | None = None,
    walk_forward: pd.DataFrame | None = None,
    sensitivity: pd.DataFrame | None = None,
    industry_exposure: dict[str, object] | None = None,
    factor_ic: dict[str, object] | None = None,
    attribution: dict[str, object] | None = None,
) -> dict[str, object]:
    metrics = result.metrics
    benchmark_metrics = _dict_or_empty(benchmark, "metrics")
    exposure_metrics = _dict_or_empty(industry_exposure, "metrics")
    factor_metrics = _dict_or_empty(factor_ic, "metrics")
    attribution_summary = _dict_or_empty(attribution, "summary")
    style_metrics = _dict_or_empty(attribution, "style_metrics")
    contribution_metrics = _dict_or_empty(attribution, "contribution_metrics")
    bias_metrics = _dict_or_empty(attribution, "bias_diagnostics")
    walk_metrics = _walk_forward_metrics(walk_forward)
    gate = decision_gate(
        loaded=loaded,
        metrics=metrics,
        audit=audit,
        benchmark_metrics=benchmark_metrics,
        walk_metrics=walk_metrics,
        factor_metrics=factor_metrics,
        bias_metrics=bias_metrics,
    )
    quality = data_quality(loaded)
    trust = data_trust_summary(loaded)
    score = research_score(
        metrics=metrics,
        benchmark_metrics=benchmark_metrics,
        walk_metrics=walk_metrics,
        exposure_metrics=exposure_metrics,
        factor_metrics=factor_metrics,
        bias_metrics=bias_metrics,
        gate=gate,
        data_quality=quality,
        verdict=str(audit.get("verdict", "n/a")),
    )
    artifact_dir = _common_parent(artifact_paths)
    return _json_ready(
        {
            "run_id": run_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "channel": channel,
            "idea": idea,
            "source": loaded.metadata.source,
            "start_date": loaded.metadata.start_date,
            "end_date": loaded.metadata.end_date,
            "symbols": len(loaded.metadata.symbols),
            "rows": len(loaded.data),
            "data_hash": loaded.metadata.data_hash,
            "verdict": audit.get("verdict", "n/a"),
            "metrics": metrics,
            "benchmark": benchmark_metrics,
            "walk_forward": walk_metrics,
            "industry_exposure": exposure_metrics,
            "factor_ic": factor_metrics,
            "attribution": {
                "summary": attribution_summary,
                "style_metrics": style_metrics,
                "contribution_metrics": contribution_metrics,
                "bias_diagnostics": bias_metrics,
            },
            "sensitivity_scenarios": 0 if sensitivity is None else int(len(sensitivity)),
            "stock_master_rows": 0 if loaded.stock_master is None else int(len(loaded.stock_master)),
            "universe_rows": 0 if loaded.universe is None else int(len(loaded.universe)),
            "decision_gate": gate,
            "research_score": score,
            "data_quality": quality,
            "data_trust": trust,
            "parser_assumptions": assumptions,
            "parser_warnings": warnings,
            "report_path": str(report_path),
            "spec_path": str(spec_path),
            "artifact_dir": str(artifact_dir) if artifact_dir is not None else "",
            "artifact_paths": {name: str(path) for name, path in sorted(artifact_paths.items())},
        }
    )


def decision_gate(
    *,
    loaded: DataLoadResult,
    metrics: dict[str, float],
    audit: dict[str, object],
    benchmark_metrics: dict[str, object],
    walk_metrics: dict[str, object],
    factor_metrics: dict[str, object],
    bias_metrics: dict[str, object],
) -> dict[str, object]:
    source = loaded.metadata.source
    real_data_source = "investoday:" in source or "historical_asset:" in source
    bias_status = str(bias_metrics.get("status", "missing") or "missing")
    bias_score = _float(bias_metrics.get("score"))
    bias_hard_failed = _float(bias_metrics.get("hard_failed"))
    trust = data_trust_summary(loaded)
    checks = [
        _check("real_data", real_data_source, "Source must be real Investoday or canonical historical asset data."),
        _check("pit_universe", "pit_liquidity_universe" in source, "PIT liquidity membership must be enabled."),
        _check("stock_master", "pit_stock_master_filter" in source, "Stock master listing filter must be enabled."),
        _check(
            "production_data",
            bool(trust.get("production_data_ready")),
            f"Production data trust must be ready; current level={trust.get('trust_level', 'n/a')}.",
        ),
        _check(
            "benchmark",
            float(benchmark_metrics.get("aligned_days", 0.0) or 0.0) > 0,
            "Benchmark comparison must be available.",
        ),
        _check(
            "walk_forward",
            float(walk_metrics.get("positive_rate", 0.0) or 0.0) >= 0.75
            and int(walk_metrics.get("failed_count", 0) or 0) == 0,
            "At least 75% of walk-forward windows must be positive with no failed OOS windows.",
        ),
        _check(
            "factor_ic",
            float(factor_metrics.get("supportive_count", 0.0) or 0.0) >= 1
            and float(factor_metrics.get("adverse_count", 0.0) or 0.0) == 0,
            "At least one factor-horizon pair must be supportive and none should be adverse.",
        ),
        _check(
            "bias_diagnostics",
            bias_status in {"ok", "warn"} and bias_score >= 70.0 and bias_hard_failed == 0.0,
            f"Bias diagnostics status {bias_status}; score {bias_score:.1f}; hard_failed={bias_hard_failed:.0f}.",
        ),
        _check(
            "drawdown",
            float(metrics.get("max_drawdown", 0.0) or 0.0) >= -0.25,
            "Max drawdown must be better than -25%.",
        ),
        _check(
            "trade_sample",
            float(metrics.get("trade_count", 0.0) or 0.0) >= 100,
            "Trade count must be at least 100.",
        ),
        _check("audit", audit.get("verdict") != "abandon", "Audit verdict must not be abandon."),
    ]
    passed = sum(1 for item in checks if item["passed"])
    failed = len(checks) - passed
    status = "paper_candidate" if failed == 0 else "research_only"
    return {
        "status": status,
        "passed": passed,
        "failed": failed,
        "checks": checks,
    }


def research_score(
    *,
    metrics: dict[str, object],
    benchmark_metrics: dict[str, object],
    walk_metrics: dict[str, object],
    exposure_metrics: dict[str, object],
    factor_metrics: dict[str, object],
    bias_metrics: dict[str, object],
    gate: dict[str, object],
    data_quality: dict[str, object],
    verdict: str,
) -> dict[str, object]:
    annualized = _float(metrics.get("annualized_return"))
    drawdown = _float(metrics.get("max_drawdown"))
    information_ratio = _float(benchmark_metrics.get("information_ratio"))
    sharpe = _float(metrics.get("sharpe"))
    trade_count = _float(metrics.get("trade_count"))
    walk_windows = _float(walk_metrics.get("windows"))
    walk_positive = _float(walk_metrics.get("positive_rate"))
    walk_failed = _float(walk_metrics.get("failed_count"))
    top_industry_weight = _float(exposure_metrics.get("latest_top_weight"))
    supportive = _float(factor_metrics.get("supportive_count"))
    adverse = _float(factor_metrics.get("adverse_count"))
    best_t = _float(factor_metrics.get("best_t_stat"))
    bias_score = _float(bias_metrics.get("score"))
    bias_hard_failed = _float(bias_metrics.get("hard_failed"))
    gate_failed = _float(gate.get("failed"))
    gate_total = _float(gate.get("passed")) + gate_failed

    return_component = _clamp(annualized / 0.30, 0.0, 1.0) * 12.0
    drawdown_component = _clamp((0.30 + drawdown) / 0.25, 0.0, 1.0) * 12.0
    if information_ratio != 0:
        risk_adjusted_component = _clamp(information_ratio / 1.5, 0.0, 1.0) * 14.0
    else:
        risk_adjusted_component = _clamp(sharpe / 1.5, 0.0, 1.0) * 8.0

    walk_component = 0.0
    if walk_windows > 0:
        walk_component = _clamp(walk_positive, 0.0, 1.0) * 15.0
        walk_component -= min(walk_failed, walk_windows) / walk_windows * 6.0
        walk_component = _clamp(walk_component, 0.0, 15.0)

    factor_component = _clamp(supportive / 2.0, 0.0, 1.0) * 9.0
    factor_component += _clamp(best_t / 2.0, 0.0, 1.0) * 4.0
    factor_component -= min(adverse, 3.0) * 2.0
    factor_component = _clamp(factor_component, 0.0, 15.0)

    sample_component = _clamp(trade_count / 200.0, 0.0, 1.0) * 10.0

    concentration_component = 4.0
    if top_industry_weight > 0:
        concentration_component = _clamp((0.45 - top_industry_weight) / 0.30, 0.0, 1.0) * 8.0

    data_component = _data_quality_score(data_quality)
    gate_component = _clamp((gate_total - gate_failed) / gate_total, 0.0, 1.0) * 6.0 if gate_total > 0 else 0.0
    bias_component = _clamp(bias_score / 100.0, 0.0, 1.0) * 6.0
    if bias_hard_failed > 0:
        bias_component = min(bias_component, 2.0)

    components = {
        "return": return_component,
        "drawdown": drawdown_component,
        "risk_adjusted": risk_adjusted_component,
        "walk_forward": walk_component,
        "factor_ic": factor_component,
        "sample_size": sample_component,
        "concentration": concentration_component,
        "data_quality": data_component,
        "decision_gate": gate_component,
        "bias": bias_component,
    }
    total = min(sum(components.values()), 100.0)
    if verdict == "abandon":
        total = min(total, 45.0)
    elif gate.get("status") != "paper_candidate":
        total = min(total, 80.0)

    band = "reject"
    if total >= 75:
        band = "strong_watch"
    elif total >= 60:
        band = "watch"
    elif total >= 45:
        band = "weak_watch"

    return {
        "score": round(float(total), 2),
        "band": band,
        "components": {name: round(float(value), 2) for name, value in components.items()},
        "notes": (
            "Conservative score: rewards robustness, sample size, IC support and data quality; "
            "abandon verdicts and failed gates cap the final score."
        ),
    }


def data_quality(loaded: DataLoadResult) -> dict[str, object]:
    data = loaded.data
    source = loaded.metadata.source
    critical_columns = ("date", "symbol", "open", "high", "low", "close", "amount")
    execution_columns = ("is_st", "is_suspended", "limit_up", "limit_down")
    missing_columns = [column for column in critical_columns if column not in data.columns]
    missing_execution_columns = [column for column in execution_columns if column not in data.columns]
    latest_date = _latest_data_date(data)
    freshness_days = None
    if latest_date is not None:
        freshness_days = (datetime.now().date() - latest_date.date()).days
    null_close_rate = _null_rate(data, "close")
    null_amount_rate = _null_rate(data, "amount")
    duplicate_key_count = _duplicate_key_count(data)

    status = "ok"
    if data.empty:
        status = "empty"
    elif missing_columns:
        status = "missing_columns"
    elif source == "sample":
        status = "sample"
    elif freshness_days is not None and freshness_days > 5:
        status = "stale"
    elif null_close_rate > 0.01 or null_amount_rate > 0.05 or duplicate_key_count > 0:
        status = "warn"

    cache_hint = "none"
    if any("cache" in note.lower() for note in loaded.metadata.notes):
        cache_hint = "cache_enabled"

    return {
        "status": status,
        "latest_date": "" if latest_date is None else latest_date.strftime("%Y-%m-%d"),
        "freshness_days": freshness_days,
        "missing_columns": missing_columns,
        "missing_execution_columns": missing_execution_columns,
        "null_close_rate": null_close_rate,
        "null_amount_rate": null_amount_rate,
        "duplicate_key_count": duplicate_key_count,
        "rows": len(data),
        "symbols": len(loaded.metadata.symbols),
        "cache_hint": cache_hint,
    }


def render_decision_gate_markdown(entry: dict[str, object]) -> str:
    gate = _nested_dict(entry, "decision_gate")
    score = _score_dict(entry)
    quality = _quality_dict(entry)
    trust = _trust_dict(entry)
    attribution = _attribution_dict(entry)
    bias = _nested_dict(attribution, "bias_diagnostics")
    checks = gate.get("checks", [])
    lines = [
        "## Decision Gate",
        "",
        f"Status: `{gate.get('status', 'n/a')}`",
        f"Passed: {gate.get('passed', 0)}",
        f"Failed: {gate.get('failed', 0)}",
        "",
        "| Check | Passed | Detail |",
        "|---|---:|---|",
    ]
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, dict):
                continue
            name = _markdown_cell(str(check.get("name", "")))
            passed = "yes" if check.get("passed") else "no"
            detail = _markdown_cell(str(check.get("detail", "")))
            lines.append(f"| {name} | {passed} | {detail} |")
    components = _nested_dict(score, "components")
    lines.extend(
        [
            "",
            "## Research Score",
            "",
            f"Score: {score.get('score', 0)}",
            f"Band: `{score.get('band', 'n/a')}`",
            "",
            "| Component | Points |",
            "|---|---:|",
        ]
    )
    for name, value in components.items():
        lines.append(f"| {_markdown_cell(str(name))} | {value} |")
    lines.extend(
        [
            "",
            "## Data Quality",
            "",
            f"Status: `{quality.get('status', 'n/a')}`",
            f"Latest date: {quality.get('latest_date', 'n/a')}",
            f"Freshness days: {quality.get('freshness_days', 'n/a')}",
            f"Missing columns: {', '.join(quality.get('missing_columns', []) or []) or 'none'}",
            f"Missing execution columns: {', '.join(quality.get('missing_execution_columns', []) or []) or 'none'}",
            "",
            "## Data Trust",
            "",
            f"Status: `{trust.get('status', 'n/a')}`",
            f"Trust level: `{trust.get('trust_level', 'n/a')}`",
            f"Production data ready: {'yes' if trust.get('production_data_ready') else 'no'}",
            f"Universe source: `{trust.get('universe_source', 'n/a')}`",
            f"Stock master rows: {trust.get('stock_master_rows', 0)}",
            "",
            "## Bias Diagnostics",
            "",
            f"Status: `{bias.get('status', 'missing')}`",
            f"Score: {bias.get('score', 0.0)}",
            f"Hard failed: {bias.get('hard_failed', 0)}",
            f"Warnings: {bias.get('warnings', 0)}",
        ]
    )
    bias_checks = bias.get("checks", [])
    if isinstance(bias_checks, list) and bias_checks:
        lines.extend(["", "| Check | Severity | Passed | Detail |", "|---|---|---:|---|"])
        for check in bias_checks:
            if not isinstance(check, dict):
                continue
            lines.append(
                "| {name} | {severity} | {passed} | {detail} |".format(
                    name=_markdown_cell(str(check.get("name", ""))),
                    severity=_markdown_cell(str(check.get("severity", ""))),
                    passed="yes" if check.get("passed") else "no",
                    detail=_markdown_cell(str(check.get("detail", ""))),
                )
            )
    lines.append("")
    return "\n".join(lines)


def load_registry(reports_root: str | Path) -> list[dict[str, object]]:
    path = Path(reports_root) / REGISTRY_JSONL
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def write_registry_csv(reports_root: str | Path) -> Path:
    reports_path = Path(reports_root)
    rows = [_flatten_entry(entry) for entry in load_registry(reports_path)]
    csv_path = reports_path / REGISTRY_CSV
    if not rows:
        pd.DataFrame().to_csv(csv_path, index=False)
        return csv_path
    frame = pd.DataFrame(rows).drop_duplicates("run_id", keep="last")
    frame.sort_values("created_at", ascending=False, inplace=True)
    frame.to_csv(csv_path, index=False)
    return csv_path


def registry_dataframe(reports_root: str | Path) -> pd.DataFrame:
    rows = [_flatten_entry(entry) for entry in load_registry(reports_root)]
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows).drop_duplicates("run_id", keep="last")
    frame.sort_values("created_at", ascending=False, inplace=True)
    return frame.reset_index(drop=True)


def _walk_forward_metrics(walk_forward: pd.DataFrame | None) -> dict[str, object]:
    if walk_forward is None or walk_forward.empty:
        return {"windows": 0.0, "positive_rate": 0.0, "failed_count": 0.0, "weak_count": 0.0}
    values = pd.to_numeric(walk_forward.get("test_annualized_return"), errors="coerce").dropna()
    statuses = walk_forward.get("status", pd.Series(dtype=object)).astype(str)
    return {
        "windows": float(len(walk_forward)),
        "positive_rate": float((values > 0).mean()) if not values.empty else 0.0,
        "failed_count": float(statuses.eq("failed_oos").sum()),
        "weak_count": float(statuses.isin(["failed_oos", "weak_oos"]).sum()),
        "best_test_annualized_return": float(values.max()) if not values.empty else 0.0,
        "worst_test_annualized_return": float(values.min()) if not values.empty else 0.0,
    }


def _flatten_entry(entry: dict[str, object]) -> dict[str, object]:
    metrics = _nested_dict(entry, "metrics")
    benchmark = _nested_dict(entry, "benchmark")
    walk = _nested_dict(entry, "walk_forward")
    exposure = _nested_dict(entry, "industry_exposure")
    factor = _nested_dict(entry, "factor_ic")
    attribution = _attribution_dict(entry)
    attribution_summary = _nested_dict(attribution, "summary")
    style = _nested_dict(attribution, "style_metrics")
    contribution = _nested_dict(attribution, "contribution_metrics")
    bias = _nested_dict(attribution, "bias_diagnostics")
    gate = _nested_dict(entry, "decision_gate")
    score = _score_dict(entry)
    components = _nested_dict(score, "components")
    quality = _quality_dict(entry)
    trust = _trust_dict(entry)
    validation = _nested_dict(trust, "stock_master_validation")
    gate_status = str(gate.get("status", "n/a"))
    gate_failed = gate.get("failed", 0)
    if gate_status == "paper_candidate" and not _bool_value(trust.get("production_data_ready")):
        gate_status = "research_only"
        gate_failed = max(1, int(_float(gate_failed)))
    return {
        "run_id": entry.get("run_id", ""),
        "created_at": entry.get("created_at", ""),
        "channel": entry.get("channel", ""),
        "research_score": score.get("score", 0.0),
        "research_band": score.get("band", "n/a"),
        "score_return": components.get("return", 0.0),
        "score_drawdown": components.get("drawdown", 0.0),
        "score_risk_adjusted": components.get("risk_adjusted", 0.0),
        "score_walk_forward": components.get("walk_forward", 0.0),
        "score_factor_ic": components.get("factor_ic", 0.0),
        "score_sample_size": components.get("sample_size", 0.0),
        "score_concentration": components.get("concentration", 0.0),
        "score_data_quality": components.get("data_quality", 0.0),
        "score_decision_gate": components.get("decision_gate", 0.0),
        "score_bias": components.get("bias", 0.0),
        "data_quality_status": quality.get("status", "n/a"),
        "latest_data_date": quality.get("latest_date", entry.get("end_date", "")),
        "freshness_days": quality.get("freshness_days", 0),
        "missing_column_count": len(quality.get("missing_columns", []) or []),
        "missing_execution_column_count": len(quality.get("missing_execution_columns", []) or []),
        "null_close_rate": quality.get("null_close_rate", 0.0),
        "null_amount_rate": quality.get("null_amount_rate", 0.0),
        "duplicate_key_count": quality.get("duplicate_key_count", 0),
        "cache_hint": quality.get("cache_hint", "n/a"),
        "data_trust_status": trust.get("status", "n/a"),
        "data_trust_level": trust.get("trust_level", "n/a"),
        "production_data_ready": trust.get("production_data_ready", False),
        "data_source_kind": trust.get("data_source_kind", "n/a"),
        "stock_master_validation_status": _nested_dict(trust, "stock_master_validation").get("status", "n/a"),
        "data_trust_hard_failed": trust.get("hard_failed", 0),
        "data_trust_caveats": " | ".join(str(item) for item in (trust.get("caveats", []) or [])[:5]),
        "gate_status": gate_status,
        "gate_failed": gate_failed,
        "verdict": entry.get("verdict", ""),
        "annualized_return": metrics.get("annualized_return", 0.0),
        "max_drawdown": metrics.get("max_drawdown", 0.0),
        "sharpe": metrics.get("sharpe", 0.0),
        "trade_count": metrics.get("trade_count", 0.0),
        "excess_annualized_return": benchmark.get("excess_annualized_return", 0.0),
        "information_ratio": benchmark.get("information_ratio", 0.0),
        "benchmark_aligned_days": benchmark.get("aligned_days", 0.0),
        "walk_forward_windows": walk.get("windows", 0.0),
        "walk_forward_positive_rate": walk.get("positive_rate", 0.0),
        "walk_forward_failed_count": walk.get("failed_count", 0.0),
        "latest_top_industry": exposure.get("latest_top_industry", "n/a"),
        "latest_top_industry_weight": exposure.get("latest_top_weight", 0.0),
        "best_factor": factor.get("best_factor", "n/a"),
        "best_factor_horizon_days": factor.get("best_horizon_days", 0.0),
        "best_factor_mean_ic": factor.get("best_mean_ic", 0.0),
        "best_factor_t_stat": factor.get("best_t_stat", 0.0),
        "factor_supportive_count": factor.get("supportive_count", 0.0),
        "factor_adverse_count": factor.get("adverse_count", 0.0),
        "attribution_status": attribution_summary.get("status", "n/a"),
        "bias_status": bias.get("status", "n/a"),
        "bias_score": bias.get("score", 0.0),
        "bias_hard_failed": bias.get("hard_failed", 0.0),
        "bias_warnings": bias.get("warnings", 0.0),
        "dominant_style": style.get("dominant_style", "n/a"),
        "dominant_style_abs_exposure": style.get("dominant_abs_exposure", 0.0),
        "top_stock_contributor": contribution.get("top_stock_contributor", "n/a"),
        "top_stock_contribution": contribution.get("top_stock_contribution", 0.0),
        "top_industry_contributor": contribution.get("top_industry_contributor", "n/a"),
        "top_industry_contribution": contribution.get("top_industry_contribution", 0.0),
        "source": entry.get("source", ""),
        "universe_source": trust.get("universe_source") or _universe_source(str(entry.get("source", ""))),
        "symbols": entry.get("symbols", 0),
        "rows": entry.get("rows", 0),
        "data_hash": entry.get("data_hash", ""),
        "report_path": entry.get("report_path", ""),
        "artifact_dir": entry.get("artifact_dir", ""),
        "idea": entry.get("idea", ""),
    }


def _append_jsonl(path: Path, entry: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def _dict_or_empty(container: dict[str, object] | None, key: str) -> dict[str, object]:
    if not isinstance(container, dict):
        return {}
    value = container.get(key)
    return value if isinstance(value, dict) else {}


def _nested_dict(entry: dict[str, object], key: str) -> dict[str, object]:
    value = entry.get(key)
    return value if isinstance(value, dict) else {}


def _score_dict(entry: dict[str, object]) -> dict[str, object]:
    value = entry.get("research_score")
    if isinstance(value, dict):
        return value
    metrics = _nested_dict(entry, "metrics")
    benchmark = _nested_dict(entry, "benchmark")
    walk = _nested_dict(entry, "walk_forward")
    exposure = _nested_dict(entry, "industry_exposure")
    factor = _nested_dict(entry, "factor_ic")
    gate = _nested_dict(entry, "decision_gate")
    return research_score(
        metrics=metrics,
        benchmark_metrics=benchmark,
        walk_metrics=walk,
        exposure_metrics=exposure,
        factor_metrics=factor,
        bias_metrics=_nested_dict(_attribution_dict(entry), "bias_diagnostics"),
        gate=gate,
        data_quality=_quality_dict(entry),
        verdict=str(entry.get("verdict", "n/a")),
    )


def _quality_dict(entry: dict[str, object]) -> dict[str, object]:
    value = entry.get("data_quality")
    if isinstance(value, dict):
        return value
    latest_date = str(entry.get("end_date", "") or "")
    freshness_days = None
    parsed = pd.to_datetime(latest_date, errors="coerce")
    if not pd.isna(parsed):
        latest_date = parsed.strftime("%Y-%m-%d")
        freshness_days = (datetime.now().date() - parsed.date()).days
    source = str(entry.get("source", ""))
    status = "unknown"
    if source == "sample":
        status = "sample"
    elif "investoday:" in source:
        status = "ok"
        if freshness_days is not None and freshness_days > 5:
            status = "stale"
    return {
        "status": status,
        "latest_date": latest_date,
        "freshness_days": freshness_days,
        "missing_columns": [],
        "missing_execution_columns": [],
        "null_close_rate": 0.0,
        "null_amount_rate": 0.0,
        "duplicate_key_count": 0,
        "cache_hint": "n/a",
    }


def _trust_dict(entry: dict[str, object]) -> dict[str, object]:
    value = entry.get("data_trust")
    if isinstance(value, dict):
        return value
    source = str(entry.get("source", ""))
    universe_source = universe_source_from_source(source)
    production_ready = "full_historical_stock_master" in source and "historical_stock_master_truncated" not in source
    if production_ready:
        trust_level = "production_research"
        status = "ready"
    elif source == "sample":
        trust_level = "sample"
        status = "demo_only"
    elif "investoday:" in source:
        trust_level = "real_data_candidate_pool"
        status = "research_only"
    else:
        trust_level = "custom_or_unknown"
        status = "research_only"
    return {
        "status": status,
        "trust_level": trust_level,
        "production_data_ready": production_ready,
        "universe_source": universe_source,
        "data_source_kind": "investoday_real" if "investoday:" in source else source or "unknown",
        "stock_master_rows": entry.get("stock_master_rows", 0),
        "hard_failed": 0 if production_ready else 1,
        "caveats": [] if production_ready else ["Legacy run has no detailed data trust summary."],
        "stock_master_validation": {},
    }


def _attribution_dict(entry: dict[str, object]) -> dict[str, object]:
    value = entry.get("attribution")
    return value if isinstance(value, dict) else {}


def _universe_source(source: str) -> str:
    return universe_source_from_source(source)


def _check(name: str, passed: bool, detail: str) -> dict[str, object]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _common_parent(paths: dict[str, Path]) -> Path | None:
    if not paths:
        return None
    first = next(iter(paths.values()))
    return Path(first).parent


def _latest_data_date(data: pd.DataFrame) -> pd.Timestamp | None:
    if data.empty or "date" not in data.columns:
        return None
    dates = pd.to_datetime(data["date"], errors="coerce").dropna()
    if dates.empty:
        return None
    return pd.Timestamp(dates.max())


def _null_rate(data: pd.DataFrame, column: str) -> float:
    if data.empty or column not in data.columns:
        return 0.0
    return float(data[column].isna().mean())


def _duplicate_key_count(data: pd.DataFrame) -> int:
    if data.empty or "date" not in data.columns or "symbol" not in data.columns:
        return 0
    return int(data.duplicated(["date", "symbol"]).sum())


def _data_quality_score(quality: dict[str, object]) -> float:
    status = str(quality.get("status", "unknown"))
    if status == "ok":
        return 8.0
    if status == "warn":
        return 5.5
    if status == "stale":
        return 4.0
    if status == "sample":
        return 2.0
    if status == "unknown":
        return 3.0
    return 0.0


def _float(value: object) -> float:
    try:
        if value is None or pd.isna(value):
            return 0.0
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


def _json_ready(value: object) -> object:
    if isinstance(value, pd.DataFrame):
        records = value.copy()
        for column in records.columns:
            if pd.api.types.is_datetime64_any_dtype(records[column]):
                records[column] = records[column].dt.strftime("%Y-%m-%d")
        return records.to_dict(orient="records")
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if pd.isna(value):
        return None
    return value
