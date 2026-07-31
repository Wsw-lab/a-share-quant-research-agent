from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Iterable

import pandas as pd

from .artifacts import write_backtest_artifacts
from .audit import audit_backtest
from .alpha_line_retirement import filter_retired_strategy_templates
from .attribution import render_attribution_markdown, run_attribution_analysis, write_attribution_artifacts
from .backtest import _prepare_data, run_backtest
from .benchmark import compare_to_benchmark, render_benchmark_markdown, write_benchmark_artifacts
from .data_sources import (
    DataLoadResult,
    DataSourceError,
    add_market_regime_features,
    data_trust_summary,
    load_csv_panel,
    load_investoday_benchmark_quotes,
    load_sample_panel,
    render_data_trust_markdown,
    required_risk_overlay_fields,
    validate_strategy_data,
    write_data_trust_artifacts,
)
from .exposure import analyze_industry_exposure, render_industry_exposure_markdown, write_industry_exposure_artifacts
from .factor_diagnostics import render_factor_ic_markdown, run_factor_ic_diagnostics, write_factor_ic_artifacts
from .historical_assets import load_frozen_production_panel_cache, load_production_asset_panel
from .report import render_markdown_report, write_report
from .run_registry import make_run_id, register_run, render_decision_gate_markdown
from .sensitivity import render_sensitivity_markdown, run_parameter_sensitivity, write_sensitivity_artifact
from .spec import StrategySpec, spec_to_dict
from .walk_forward import render_walk_forward_markdown, run_walk_forward_validation, write_walk_forward_artifact


FACTORY_DIR = "strategy_factory"
IDEA_REGISTRY_JSONL = "idea_registry.jsonl"
IDEA_REGISTRY_CSV = "idea_registry.csv"
LATEST_BOARD_JSON = "latest_board.json"
LATEST_BOARD_MD = "latest_board.md"


DEFAULT_TEMPLATES: tuple[dict[str, object], ...] = (
    {
        "idea_id": "quality_value_momentum",
        "name": "质量价值动量",
        "category": "quality_value",
        "hypothesis": "高 ROE、低估值、近 60 日动量强的股票可能同时获得基本面质量和趋势确认。",
        "spec": {
            "name": "质量价值动量",
            "description": "Quality, value, and medium-term momentum blend.",
            "universe": {"exclude_st": True, "exclude_suspended": True, "min_amount": 5000000},
            "rebalance": {"frequency": "monthly"},
            "portfolio": {"initial_cash": 1000000, "max_positions": 20, "weighting": "equal"},
            "costs": {"commission_rate": 0.0003, "stamp_tax_rate": 0.0005, "slippage_bps": 8},
            "factors": [
                {"field": "roe", "direction": "desc", "weight": 0.35},
                {"field": "pe", "direction": "asc", "weight": 0.25},
                {"field": "momentum_60d", "direction": "desc", "weight": 0.40},
            ],
            "risk": {"max_single_position_weight": 0.08, "benchmark": "CSI300"},
        },
    },
    {
        "idea_id": "low_vol_dividend",
        "name": "低波红利",
        "category": "defensive_income",
        "hypothesis": "低波动、高股息、低 PB 的股票在震荡期可能有更好的回撤控制。",
        "spec": {
            "name": "低波红利",
            "description": "Low volatility dividend proxy.",
            "universe": {"exclude_st": True, "exclude_suspended": True, "min_amount": 3000000},
            "rebalance": {"frequency": "monthly"},
            "portfolio": {"initial_cash": 1000000, "max_positions": 25, "weighting": "equal"},
            "costs": {"commission_rate": 0.0003, "stamp_tax_rate": 0.0005, "slippage_bps": 8},
            "factors": [
                {"field": "volatility_20d", "direction": "asc", "weight": 0.40},
                {"field": "dividend_yield", "direction": "desc", "weight": 0.35},
                {"field": "pb", "direction": "asc", "weight": 0.25},
            ],
            "risk": {"max_single_position_weight": 0.06, "benchmark": "CSI300"},
        },
    },
    {
        "idea_id": "profit_repair",
        "name": "盈利修复",
        "category": "earnings_repair",
        "hypothesis": "ROE 较高且短期动量改善的股票可能反映盈利修复预期。",
        "spec": {
            "name": "盈利修复",
            "description": "Profitability plus short-term repair momentum.",
            "universe": {"exclude_st": True, "exclude_suspended": True, "min_amount": 5000000},
            "rebalance": {"frequency": "monthly"},
            "portfolio": {"initial_cash": 1000000, "max_positions": 20, "weighting": "equal"},
            "costs": {"commission_rate": 0.0003, "stamp_tax_rate": 0.0005, "slippage_bps": 8},
            "factors": [
                {"field": "roe", "direction": "desc", "weight": 0.45},
                {"field": "momentum_20d", "direction": "desc", "weight": 0.35},
                {"field": "pe", "direction": "asc", "weight": 0.20},
            ],
            "risk": {"max_single_position_weight": 0.08, "benchmark": "CSI300"},
        },
    },
    {
        "idea_id": "event_momentum_proxy",
        "name": "事件动量代理",
        "category": "event_momentum",
        "hypothesis": "短期强动量和成交额放大的股票可能代理公告、产业催化或资金关注。",
        "spec": {
            "name": "事件动量代理",
            "description": "Short-term momentum and liquidity attention proxy.",
            "universe": {"exclude_st": True, "exclude_suspended": True, "min_amount": 8000000},
            "rebalance": {"frequency": "weekly"},
            "portfolio": {"initial_cash": 1000000, "max_positions": 15, "weighting": "equal"},
            "costs": {"commission_rate": 0.0003, "stamp_tax_rate": 0.0005, "slippage_bps": 12},
            "factors": [
                {"field": "momentum_20d", "direction": "desc", "weight": 0.50},
                {"field": "amount", "direction": "desc", "weight": 0.30},
                {"field": "volatility_20d", "direction": "asc", "weight": 0.20},
            ],
            "risk": {"max_single_position_weight": 0.08, "benchmark": "CSI300"},
        },
    },
    {
        "idea_id": "industry_rotation_proxy",
        "name": "行业轮动代理",
        "category": "rotation",
        "hypothesis": "中期趋势和流动性共振可作为行业轮动在个股层面的代理信号。",
        "spec": {
            "name": "行业轮动代理",
            "description": "Medium-term momentum and liquidity rotation proxy.",
            "universe": {"exclude_st": True, "exclude_suspended": True, "min_amount": 10000000},
            "rebalance": {"frequency": "monthly"},
            "portfolio": {"initial_cash": 1000000, "max_positions": 30, "weighting": "equal"},
            "costs": {"commission_rate": 0.0003, "stamp_tax_rate": 0.0005, "slippage_bps": 10},
            "factors": [
                {"field": "momentum_60d", "direction": "desc", "weight": 0.55},
                {"field": "amount", "direction": "desc", "weight": 0.30},
                {"field": "volatility_20d", "direction": "asc", "weight": 0.15},
            ],
            "risk": {"max_single_position_weight": 0.05, "benchmark": "CSI300"},
        },
    },
    {
        "idea_id": "liquidity_breakout",
        "name": "流动性突破",
        "category": "liquidity_momentum",
        "hypothesis": "成交额高、趋势强且波动抬升的股票可能处在资金推动阶段，但需要更严执行成本约束。",
        "spec": {
            "name": "流动性突破",
            "description": "Liquidity and trend breakout proxy with higher slippage.",
            "universe": {"exclude_st": True, "exclude_suspended": True, "min_amount": 15000000},
            "rebalance": {"frequency": "weekly"},
            "portfolio": {"initial_cash": 1000000, "max_positions": 12, "weighting": "equal"},
            "costs": {"commission_rate": 0.0003, "stamp_tax_rate": 0.0005, "slippage_bps": 15},
            "factors": [
                {"field": "amount", "direction": "desc", "weight": 0.35},
                {"field": "momentum_60d", "direction": "desc", "weight": 0.45},
                {"field": "volatility_20d", "direction": "desc", "weight": 0.20},
            ],
            "risk": {"max_single_position_weight": 0.08, "benchmark": "CSI300"},
        },
    },
    {
        "idea_id": "defensive_cashflow_proxy",
        "name": "防御现金流代理",
        "category": "defensive_quality",
        "hypothesis": "高股息、低波动、合理估值的组合可作为现金流防御型策略候选。",
        "spec": {
            "name": "防御现金流代理",
            "description": "Dividend, low volatility, and valuation defensive proxy.",
            "universe": {"exclude_st": True, "exclude_suspended": True, "min_amount": 3000000},
            "rebalance": {"frequency": "monthly"},
            "portfolio": {"initial_cash": 1000000, "max_positions": 30, "weighting": "equal"},
            "costs": {"commission_rate": 0.0003, "stamp_tax_rate": 0.0005, "slippage_bps": 8},
            "factors": [
                {"field": "dividend_yield", "direction": "desc", "weight": 0.45},
                {"field": "volatility_20d", "direction": "asc", "weight": 0.35},
                {"field": "pe", "direction": "asc", "weight": 0.20},
            ],
            "risk": {"max_single_position_weight": 0.05, "benchmark": "CSI300"},
        },
    },
)


def load_strategy_templates(path: str | Path | None = None) -> list[dict[str, object]]:
    if path is None:
        return [json.loads(json.dumps(item, ensure_ascii=False)) for item in DEFAULT_TEMPLATES]
    template_path = Path(path)
    if not template_path.exists():
        raise DataSourceError(f"Strategy template file does not exist: {template_path}")
    payload = json.loads(template_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        value = payload.get("ideas")
    else:
        value = payload
    if not isinstance(value, list) or not value:
        raise DataSourceError("Strategy template file must contain a non-empty ideas list.")
    return [item for item in value if isinstance(item, dict)]


def write_default_templates(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"ideas": list(DEFAULT_TEMPLATES)}, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target


def run_strategy_factory(
    *,
    reports_root: str | Path,
    templates: Iterable[dict[str, object]],
    source: str = "sample",
    csv_path: str | Path | None = None,
    asset_root: str | Path | None = None,
    start: str = "20210101",
    end: str = "20251231",
    sample_symbols: int = 80,
    universe_size: int = 100,
    universe_lookback_days: int = 20,
    universe_min_history_days: int = 20,
    historical_stock_master_min_rows: int = 3000,
    min_delisted_rows: int = 50,
    include_bj: bool = False,
    max_ideas: int | None = None,
    skip_sensitivity: bool = False,
    skip_walk_forward: bool = False,
    skip_factor_ic: bool = False,
    skip_attribution: bool = False,
    skip_industry_exposure: bool = False,
    skip_incompatible_templates: bool = False,
    benchmark_code: str | None = None,
    benchmark_page_size: int = 500,
    benchmark_cache_dir: str | Path | None = "cache/investoday_api",
    refresh_benchmark_cache: bool = False,
    alpha_line_retirement_ledger: dict[str, object] | None = None,
    skip_retired_alpha_lines: bool = False,
    frozen_panel_cache_path: str | Path | None = None,
) -> dict[str, object]:
    reports = Path(reports_root)
    factory_id = make_run_id("factory_batch")
    factory_dir = reports / FACTORY_DIR / "runs" / factory_id
    factory_dir.mkdir(parents=True, exist_ok=True)
    template_list = list(templates)
    if max_ideas is not None and max_ideas > 0:
        template_list = template_list[:max_ideas]
    retired_skipped: list[dict[str, object]] = []
    if skip_retired_alpha_lines and alpha_line_retirement_ledger:
        template_list, retired_skipped = filter_retired_strategy_templates(template_list, alpha_line_retirement_ledger)
    if not template_list:
        board = build_strategy_factory_board(
            factory_id=factory_id,
            records=[],
            errors=[],
            skipped=retired_skipped,
            source=f"{source}+alpha_line_retirement_screen",
            start=start,
            end=end,
        )
        paths = write_strategy_factory_board(reports, board)
        return {
            "factory_id": factory_id,
            "records": [],
            "errors": [],
            "skipped": retired_skipped,
            "board": board,
            "paths": paths,
            "benchmark": {"code": str(benchmark_code or "").strip(), "rows": 0, "error": ""},
        }
    requested_data_fields = _templates_requested_data_fields(template_list)
    fundamental_fields = _templates_required_fundamental_fields(template_list)
    loaded = _load_factory_data(
        source=source,
        csv_path=csv_path,
        asset_root=asset_root,
        start=start,
        end=end,
        sample_symbols=sample_symbols,
        universe_size=universe_size,
        universe_lookback_days=universe_lookback_days,
        universe_min_history_days=universe_min_history_days,
        historical_stock_master_min_rows=historical_stock_master_min_rows,
        min_delisted_rows=min_delisted_rows,
        include_bj=include_bj,
        frozen_panel_cache_path=frozen_panel_cache_path,
        fundamental_fields=fundamental_fields,
        required_data_fields=requested_data_fields,
    )
    benchmark_data = None
    benchmark_error = ""
    benchmark_code_text = str(benchmark_code or "").strip()
    if benchmark_code_text:
        try:
            benchmark_loaded = load_investoday_benchmark_quotes(
                index_code=benchmark_code_text,
                start=start,
                end=end,
                page_size=benchmark_page_size,
                cache_dir=benchmark_cache_dir,
                refresh_cache=refresh_benchmark_cache,
            )
            benchmark_data = benchmark_loaded.data
        except Exception as exc:
            benchmark_error = str(exc)
    overlay_fields = _templates_required_risk_overlay_fields(template_list)
    if benchmark_data is not None and overlay_fields:
        loaded = _with_market_regime_features(
            loaded,
            benchmark_data,
            benchmark_code=benchmark_code_text,
            fields=overlay_fields,
        )
    started_at = time.monotonic()
    last_at = started_at
    loaded = _trim_loaded_data_for_templates(loaded, template_list)
    loaded = replace(loaded, data=_prepare_data(loaded.data))
    last_at = _factory_progress("shared_data_prepared", started_at=started_at, last_at=last_at)

    records: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = list(retired_skipped)
    for index, template in enumerate(template_list, start=1):
        if skip_incompatible_templates:
            missing_fields = _template_missing_factor_fields(template, loaded.data)
            if missing_fields:
                skipped.append(
                    {
                        "idea_id": str(template.get("idea_id", "unknown")),
                        "name": str(template.get("name", "")),
                        "reason": "missing_factor_fields",
                        "missing_fields": missing_fields,
                    }
                )
                continue
        idea_id = _safe_id(str(template.get("idea_id") or template.get("name") or "idea"))
        _factory_progress(
            f"idea_start {index}/{len(template_list)} {idea_id}",
            started_at=started_at,
            last_at=last_at,
        )
        try:
            record = _run_factory_idea(
                reports,
                factory_id=factory_id,
                factory_dir=factory_dir,
                template=template,
                loaded=loaded,
                skip_sensitivity=skip_sensitivity,
                skip_walk_forward=skip_walk_forward,
                skip_factor_ic=skip_factor_ic,
                skip_attribution=skip_attribution,
                skip_industry_exposure=skip_industry_exposure,
                benchmark_data=benchmark_data,
                benchmark_error=benchmark_error,
            )
            records.append(record)
            last_at = _factory_progress(
                f"idea_done {index}/{len(template_list)} {idea_id}",
                started_at=started_at,
                last_at=last_at,
            )
        except Exception as exc:
            errors.append(
                {
                    "idea_id": str(template.get("idea_id", "unknown")),
                    "name": str(template.get("name", "")),
                    "error": str(exc),
                }
            )
            last_at = _factory_progress(
                f"idea_error {index}/{len(template_list)} {idea_id}: {type(exc).__name__}",
                started_at=started_at,
                last_at=last_at,
            )

    board = build_strategy_factory_board(
        factory_id=factory_id,
        records=records,
        errors=errors,
        skipped=skipped,
        source=loaded.metadata.source,
        start=start,
        end=end,
    )
    paths = write_strategy_factory_board(reports, board)
    append_strategy_idea_registry(reports, records)
    return {
        "factory_id": factory_id,
        "records": records,
        "errors": errors,
        "skipped": skipped,
        "board": board,
        "paths": paths,
        "benchmark": {
            "code": benchmark_code_text,
            "rows": 0 if benchmark_data is None else int(len(benchmark_data)),
            "error": benchmark_error,
        },
    }


def append_strategy_idea_registry(reports_root: str | Path, records: Iterable[dict[str, object]]) -> dict[str, Path]:
    factory_root = Path(reports_root) / FACTORY_DIR
    factory_root.mkdir(parents=True, exist_ok=True)
    jsonl_path = factory_root / IDEA_REGISTRY_JSONL
    with jsonl_path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(_json_ready(record), ensure_ascii=False, sort_keys=True) + "\n")
    csv_path = write_strategy_idea_registry_csv(reports_root)
    return {"idea_registry": jsonl_path, "idea_registry_csv": csv_path}


def write_strategy_idea_registry_csv(reports_root: str | Path) -> Path:
    rows = load_strategy_idea_registry(reports_root)
    path = Path(reports_root) / FACTORY_DIR / IDEA_REGISTRY_CSV
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        pd.DataFrame().to_csv(path, index=False)
        return path
    frame = pd.DataFrame(_flatten_idea_record(row) for row in rows)
    frame = frame.drop_duplicates("idea_id", keep="last").sort_values(["priority", "score"], ascending=[True, False])
    frame.to_csv(path, index=False)
    return path


def load_strategy_idea_registry(reports_root: str | Path) -> list[dict[str, object]]:
    path = Path(reports_root) / FACTORY_DIR / IDEA_REGISTRY_JSONL
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def load_strategy_factory_board(reports_root: str | Path) -> dict[str, object]:
    path = Path(reports_root) / FACTORY_DIR / LATEST_BOARD_JSON
    if not path.exists():
        return {"records": [], "errors": [], "summary": {"total": 0}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"records": [], "errors": [], "summary": {"total": 0}}
    return value if isinstance(value, dict) else {"records": [], "errors": [], "summary": {"total": 0}}


def build_strategy_factory_board(
    *,
    factory_id: str,
    records: list[dict[str, object]],
    errors: list[dict[str, object]],
    skipped: list[dict[str, object]] | None = None,
    source: str,
    start: str,
    end: str,
) -> dict[str, object]:
    skipped = skipped or []
    status_counts: dict[str, int] = {}
    for record in records:
        status = str(record.get("lifecycle_status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1
    sorted_records = sorted(records, key=lambda row: (-float(row.get("score", 0.0) or 0.0), str(row.get("idea_id", ""))))
    return {
        "factory_id": factory_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "start_date": start,
        "end_date": end,
        "summary": {
            "total": len(records),
            "errors": len(errors),
            "skipped": len(skipped),
            "status_counts": status_counts,
            "paper_candidates": status_counts.get("paper_candidate", 0),
            "watch": status_counts.get("watch", 0),
            "testing": status_counts.get("testing", 0),
            "rejected": status_counts.get("rejected", 0),
        },
        "records": sorted_records,
        "errors": errors,
        "skipped": skipped,
        "notes": [
            "Strategy factory promotion is conservative and cannot bypass production data, bias, walk-forward, factor IC, drawdown, and sample-size gates.",
            "Non-production data runs stay in testing even when returns look attractive.",
            "Skipped templates are incompatible with the loaded data surface and should be retried after the required factors are onboarded.",
        ],
    }


def write_strategy_factory_board(reports_root: str | Path, board: dict[str, object]) -> dict[str, Path]:
    root = Path(reports_root) / FACTORY_DIR
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / LATEST_BOARD_JSON
    markdown_path = root / LATEST_BOARD_MD
    json_path.write_text(json.dumps(_json_ready(board), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_strategy_factory_board_markdown(board), encoding="utf-8")
    return {"latest_board": json_path, "latest_board_report": markdown_path}


def render_strategy_factory_board_markdown(board: dict[str, object]) -> str:
    summary = board.get("summary") if isinstance(board.get("summary"), dict) else {}
    lines = [
        "## Strategy Factory Board",
        "",
        f"Factory: `{board.get('factory_id', 'n/a')}`",
        f"Generated at: `{board.get('generated_at', 'n/a')}`",
        f"Source: `{board.get('source', 'n/a')}`",
        f"Range: `{board.get('start_date', '')}` to `{board.get('end_date', '')}`",
        f"Total ideas: {summary.get('total', 0)}",
        f"Errors: {summary.get('errors', 0)}",
        f"Skipped: {summary.get('skipped', 0)}",
        "",
        "| Idea | Status | Recommendation | Score | Gate | Data Trust | Walk | IC | Drawdown | Trades | Run |",
        "|---|---|---|---:|---|---|---:|---:|---:|---:|---|",
    ]
    records = board.get("records", [])
    if isinstance(records, list):
        for record in records:
            if not isinstance(record, dict):
                continue
            lines.append(
                "| {name} | {status} | {recommendation} | {score:.2f} | {gate} | {trust} | {walk:.0%} | {ic:.0f} | {drawdown:.2%} | {trades:.0f} | `{run}` |".format(
                    name=_md(str(record.get("name", ""))),
                    status=_md(str(record.get("lifecycle_status", ""))),
                    recommendation=_md(str(record.get("recommendation", ""))),
                    score=float(record.get("score", 0.0) or 0.0),
                    gate=_md(str(record.get("gate_status", ""))),
                    trust=_md(str(record.get("data_trust_level", ""))),
                    walk=float(record.get("walk_forward_positive_rate", 0.0) or 0.0),
                    ic=float(record.get("factor_supportive_count", 0.0) or 0.0),
                    drawdown=float(record.get("max_drawdown", 0.0) or 0.0),
                    trades=float(record.get("trade_count", 0.0) or 0.0),
                    run=_md(str(record.get("run_id", ""))),
                )
            )
    errors = board.get("errors", [])
    if isinstance(errors, list) and errors:
        lines.extend(["", "### Errors", ""])
        for error in errors:
            if isinstance(error, dict):
                lines.append(f"- `{error.get('idea_id', 'unknown')}`: {error.get('error', '')}")
    skipped = board.get("skipped", [])
    if isinstance(skipped, list) and skipped:
        lines.extend(["", "### Skipped", ""])
        for item in skipped:
            if isinstance(item, dict):
                reason = str(item.get("reason", ""))
                if reason == "retired_alpha_line":
                    alpha_lines = ", ".join(str(field) for field in item.get("alpha_lines", []) or [])
                    requirements = "; ".join(str(field) for field in item.get("rewrite_required", []) or [])
                    lines.append(f"- `{item.get('idea_id', 'unknown')}`: retired alpha line `{alpha_lines}`; rewrite required: {requirements}")
                else:
                    missing = ", ".join(str(field) for field in item.get("missing_fields", []) or [])
                    lines.append(f"- `{item.get('idea_id', 'unknown')}`: missing or empty factor fields: {missing}")
    lines.append("")
    return "\n".join(lines)


def _template_missing_factor_fields(template: dict[str, object], data: pd.DataFrame) -> list[str]:
    spec_payload = template.get("spec")
    if not isinstance(spec_payload, dict):
        return []
    factors = spec_payload.get("factors")
    if not isinstance(factors, list):
        return []
    available = set(data.columns)
    missing = []
    for factor in factors:
        if not isinstance(factor, dict):
            continue
        field = str(factor.get("field", ""))
        if not field:
            continue
        if field not in available or _factor_field_has_no_values(data[field]):
            missing.append(field)
    try:
        spec = StrategySpec.from_dict(spec_payload)
    except Exception:
        spec = None
    if spec is not None:
        for field in required_risk_overlay_fields(spec):
            if field not in available or _factor_field_has_no_values(data[field]):
                missing.append(field)
    return sorted(set(missing))


def _factor_field_has_no_values(series: pd.Series) -> bool:
    values = pd.to_numeric(series, errors="coerce")
    return bool(values.dropna().empty)


def _with_market_regime_features(
    loaded: DataLoadResult,
    benchmark_data: pd.DataFrame,
    *,
    benchmark_code: str,
    fields: Iterable[str],
) -> DataLoadResult:
    data = add_market_regime_features(loaded.data, benchmark_data, fields=fields)
    field_text = ", ".join(str(field) for field in fields)
    data_hash = _market_regime_data_hash(loaded, benchmark_data, benchmark_code=benchmark_code, fields=fields)
    notes = loaded.metadata.notes + (
        f"Merged lagged market regime features from benchmark {benchmark_code or 'n/a'}.",
        f"Market regime fields: {field_text}.",
        "Risk overlay benchmark features use prior index information only; same-day close is shifted by one trading day.",
        f"Market regime feature data sha256: {data_hash}",
    )
    return DataLoadResult(
        data=data,
        metadata=replace(
            loaded.metadata,
            source=f"{loaded.metadata.source}+benchmark_market_regime_features",
            notes=notes,
            data_hash=data_hash,
        ),
        universe=loaded.universe,
        stock_master=loaded.stock_master,
    )


def _market_regime_data_hash(
    loaded: DataLoadResult,
    benchmark_data: pd.DataFrame,
    *,
    benchmark_code: str,
    fields: Iterable[str],
) -> str:
    payload = {
        "base_data_hash": loaded.metadata.data_hash,
        "benchmark_code": benchmark_code,
        "benchmark_rows": int(len(benchmark_data)),
        "benchmark_start": "" if benchmark_data.empty else str(pd.to_datetime(benchmark_data["date"]).min().date()),
        "benchmark_end": "" if benchmark_data.empty else str(pd.to_datetime(benchmark_data["date"]).max().date()),
        "fields": list(fields),
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _trim_loaded_data_for_templates(loaded: DataLoadResult, templates: Iterable[dict[str, object]]) -> DataLoadResult:
    data = loaded.data
    if data.empty:
        return loaded
    required = _templates_required_data_fields(templates)
    columns = [column for column in data.columns if column in required or _keep_diagnostic_column(str(column))]
    columns = list(dict.fromkeys(columns))
    if not columns:
        return loaded
    trimmed = data.loc[:, columns].copy()
    dropped = len(data.columns) - len(trimmed.columns)
    if dropped <= 0:
        return loaded
    metadata = replace(
        loaded.metadata,
        notes=loaded.metadata.notes
        + (
            f"Strategy factory trimmed production panel columns from {len(data.columns)} to {len(trimmed.columns)} for this template batch.",
            f"Trimmed production panel retained fields: {', '.join(str(column) for column in trimmed.columns[:80])}.",
        ),
    )
    return DataLoadResult(data=trimmed, metadata=metadata, universe=loaded.universe, stock_master=loaded.stock_master)


def _templates_required_data_fields(templates: Iterable[dict[str, object]]) -> set[str]:
    fields = {
        "date",
        "symbol",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "is_st",
        "is_suspended",
        "limit_up",
        "limit_down",
        "is_universe_member",
        "is_stock_master_member",
        "stockName",
        "industryLV1Name",
        "industryName",
        "boardName",
        "stockType",
        "listStatus",
        "listDate",
        "delistDate",
        "daily_return",
        "momentum_20d",
        "momentum_60d",
        "momentum_120d",
        "momentum_252d",
        "volatility_20d",
        "volatility_60d",
        "volatility_downside_60d",
        "drawdown_120d",
        "drawdown_252d",
        "close_to_ma_60d",
        "trend_persistence_120d",
        "market_breadth_20d_lag1",
        "market_breadth_60d_lag1",
        "market_breadth_120d_lag1",
        "market_above_ma60_share_lag1",
        "market_drawdown_ok_share_lag1",
        "market_price_trend_stability_score_median_lag1",
        "market_downside_volatility_score_median_lag1",
        "market_liquidity_exposure_guard_score_median_lag1",
        "market_single_name_risk_guard_score_median_lag1",
        "market_alpha_quality_stability_score_median_lag1",
        "market_alpha_health_score_lag1",
        "momentum_120d_positive_score",
        "momentum_252d_positive_score",
        "long_trend_quality_score",
        "downside_volatility_score",
        "reversal_risk_guard_score",
        "price_trend_stability_score",
        "capitalFlowDate",
        "inflowSmall",
        "inflowMedium",
        "inflowLarge",
        "inflowXlarge",
        "outflowSmall",
        "outflowMedium",
        "outflowLarge",
        "outflowXlarge",
        "netInflowSmall",
        "netInflowMedium",
        "netInflowLarge",
        "netInflowXlarge",
        "netInflowRatioSmall",
        "netInflowRatioMedium",
        "netInflowRatioLarge",
        "netInflowRatioXlarge",
        "mainNetInflow",
        "mainNetInflowRatio",
        "controlRatio",
        "askVolumeTotal",
        "bidVolumeTotal",
        "bidAskVolumeDiff",
        "main_net_inflow_to_amount",
        "large_net_inflow_to_amount",
        "xlarge_net_inflow_to_amount",
        "main_flow_strength_score",
        "large_flow_strength_score",
        "xlarge_flow_strength_score",
        "main_flow_positive_score",
        "flow_persistence_20d_raw",
        "flow_persistence_20d_score",
        "flow_reversal_guard_score",
        "capital_flow_quality_score",
        "marginTradeDate",
        "marginBalance",
        "marginBuyAmount",
        "marginRepayAmount",
        "shortBalanceVolume",
        "shortSellVolume",
        "shortBalanceAmount",
        "marginShortBalance",
        "margin_net_buy_amount",
        "margin_buy_to_amount",
        "margin_repay_to_amount",
        "margin_net_buy_to_amount",
        "margin_balance_to_amount",
        "short_balance_to_amount",
        "margin_net_buy_strength_score",
        "margin_balance_crowding_guard_score",
        "margin_short_pressure_guard_score",
        "margin_leverage_flow_score",
        "margin_deleveraging_guard_score",
        "margin_trade_quality_score",
        "dragon_tiger_count_90d",
        "dragon_tiger_amount_90d",
        "dragon_tiger_days_since_last",
        "dragon_tiger_max_deviation_90d",
        "dragon_tiger_attention_score",
        "dragon_tiger_amount_score",
        "dragon_tiger_recency_score",
        "dragon_tiger_cooldown_score",
        "dragon_tiger_event_score",
        "announcement_count_30d",
        "announcement_count_90d",
        "announcement_count_180d",
        "announcement_count_365d",
        "announcement_buyback_count_180d",
        "announcement_dividend_count_365d",
        "announcement_financing_count_365d",
        "announcement_reorg_count_365d",
        "announcement_risk_alert_count_365d",
        "announcement_report_count_365d",
        "announcement_days_since_last",
        "announcement_activity_score",
        "announcement_recency_score",
        "announcement_noise_guard_score",
        "announcement_buyback_activity_score",
        "announcement_shareholder_return_score",
        "announcement_risk_alert_guard_score",
        "announcement_financing_cooldown_score",
        "announcement_reorg_cooldown_score",
        "announcement_stability_guard_score",
        "announcement_event_score",
        "turnover",
        "universe_liquidity",
        "universe_rank",
    }
    for template in templates:
        spec_payload = template.get("spec") if isinstance(template, dict) else None
        if not isinstance(spec_payload, dict):
            continue
        for factor in spec_payload.get("factors", []) or []:
            if isinstance(factor, dict) and factor.get("field"):
                fields.add(str(factor["field"]))
        portfolio = spec_payload.get("portfolio") if isinstance(spec_payload.get("portfolio"), dict) else {}
        for key in ("selection_bucket_field", "selection_group_field"):
            value = portfolio.get(key)
            if value:
                fields.add(str(value))
        universe = spec_payload.get("universe") if isinstance(spec_payload.get("universe"), dict) else {}
        index_code = str(universe.get("index_code", "") or "").strip()
        if index_code:
            suffix = "".join(character if character.isalnum() else "_" for character in index_code.upper()).strip("_")
            fields.add(f"is_index_member_{suffix}")
            fields.add(f"index_weight_{suffix}")
        try:
            spec = StrategySpec.from_dict(spec_payload)
        except Exception:
            spec = None
        if spec is not None:
            for field in required_risk_overlay_fields(spec):
                fields.add(str(field))
    return fields


def _templates_requested_data_fields(templates: Iterable[dict[str, object]]) -> set[str]:
    fields: set[str] = set()
    for template in templates:
        spec_payload = template.get("spec") if isinstance(template, dict) else None
        if not isinstance(spec_payload, dict):
            continue
        for factor in spec_payload.get("factors", []) or []:
            if isinstance(factor, dict) and factor.get("field"):
                fields.add(str(factor["field"]))
        portfolio = spec_payload.get("portfolio") if isinstance(spec_payload.get("portfolio"), dict) else {}
        for key in ("selection_bucket_field", "selection_group_field"):
            value = portfolio.get(key)
            if value:
                fields.add(str(value))
        universe = spec_payload.get("universe") if isinstance(spec_payload.get("universe"), dict) else {}
        index_code = str(universe.get("index_code", "") or "").strip()
        if index_code:
            suffix = "".join(character if character.isalnum() else "_" for character in index_code.upper()).strip("_")
            fields.add(f"is_index_member_{suffix}")
            fields.add(f"index_weight_{suffix}")
        try:
            spec = StrategySpec.from_dict(spec_payload)
        except Exception:
            spec = None
        if spec is not None:
            for field in required_risk_overlay_fields(spec):
                fields.add(str(field))
    return fields


def _templates_required_fundamental_fields(templates: Iterable[dict[str, object]]) -> set[str] | None:
    required = _templates_required_data_fields(templates)
    dependencies = {
        "pe_sane": {"pe"},
        "pe_valid_score": {"pe"},
        "pb_sane": {"pb"},
        "pb_valid_score": {"pb"},
        "roe_sane": {"roe"},
        "roe_positive_score": {"roe"},
        "roe_delta_252d": {"roe"},
        "roe_repair_score": {"roe"},
        "dividend_yield_capped": {"dividend_yield"},
        "dividend_yield_sane": {"dividend_yield"},
        "dividend_yield_valid_score": {"dividend_yield"},
        "valuation_sanity_score": {"pe", "pb", "dividend_yield"},
        "gross_margin_sane": {"gross_margin"},
        "gross_margin_score": {"gross_margin"},
        "net_margin_sane": {"net_margin"},
        "net_margin_score": {"net_margin"},
        "roic_sane": {"roic"},
        "roic_score": {"roic"},
        "rev_growth_1y_sane": {"rev_growth_1y"},
        "rev_growth_score": {"rev_growth_1y"},
        "np_growth_1y_sane": {"np_growth_1y"},
        "np_growth_score": {"np_growth_1y"},
        "cfo_growth_1y_sane": {"cfo_growth_1y"},
        "cfo_growth_score": {"cfo_growth_1y"},
        "ocf_to_net_profit_sane": {"ocf_to_net_profit_ratio"},
        "ocf_to_net_profit_score": {"ocf_to_net_profit_ratio"},
        "cfo_to_revenue_sane": {"cfo_to_revenue"},
        "cfo_to_revenue_score": {"cfo_to_revenue"},
        "fcf_to_equity_ps_positive_score": {"fcf_to_equity_ps"},
        "cash_debt_ratio_sane": {"cash_debt_ratio"},
        "cash_debt_ratio_score": {"cash_debt_ratio"},
        "debt_asset_ratio_sane": {"debt_asset_ratio"},
        "low_debt_score": {"debt_asset_ratio"},
        "f_score_sane": {"f_score"},
        "f_score_quality_score": {"f_score"},
        "profitability_quality_score": {"gross_margin", "net_margin", "roic"},
        "growth_quality_score": {"rev_growth_1y", "np_growth_1y", "cfo_growth_1y"},
        "cashflow_quality_score": {"ocf_to_net_profit_ratio", "cfo_to_revenue", "fcf_to_equity_ps"},
        "balance_sheet_quality_score": {"cash_debt_ratio", "debt_asset_ratio", "f_score"},
        "alpha_quality_stability_score": {
            "roe",
            "pe",
            "pb",
            "dividend_yield",
            "gross_margin",
            "net_margin",
            "roic",
            "rev_growth_1y",
            "np_growth_1y",
            "cfo_growth_1y",
            "ocf_to_net_profit_ratio",
            "cfo_to_revenue",
            "fcf_to_equity_ps",
            "cash_debt_ratio",
            "debt_asset_ratio",
            "f_score",
        },
    }
    base_fields = {
        "pe",
        "pb",
        "roe",
        "dividend_yield",
        "gross_margin",
        "net_margin",
        "roic",
        "rev_growth_1y",
        "np_growth_1y",
        "cfo_growth_1y",
        "ocf_to_net_profit_ratio",
        "cfo_to_revenue",
        "fcf_to_equity_ps",
        "cash_debt_ratio",
        "debt_asset_ratio",
        "f_score",
    }
    requested = {field for field in required if field in base_fields}
    for field in required:
        requested.update(dependencies.get(field, set()))
    return requested or None


def _keep_diagnostic_column(column: str) -> bool:
    return (
        column.startswith("benchmark_")
        or column.startswith("is_index_member")
        or column.startswith("index_weight")
        or column.startswith("index_name")
        or column in {"indexCode", "indexName"}
    )


def _templates_required_risk_overlay_fields(templates: Iterable[dict[str, object]]) -> list[str]:
    fields: list[str] = []
    for template in templates:
        spec_payload = template.get("spec") if isinstance(template, dict) else None
        if not isinstance(spec_payload, dict):
            continue
        try:
            spec = StrategySpec.from_dict(spec_payload)
        except Exception:
            continue
        fields.extend(required_risk_overlay_fields(spec))
    return sorted(dict.fromkeys(fields))


def _run_factory_idea(
    reports_root: Path,
    *,
    factory_id: str,
    factory_dir: Path,
    template: dict[str, object],
    loaded: DataLoadResult,
    skip_sensitivity: bool,
    skip_walk_forward: bool,
    skip_factor_ic: bool,
    skip_attribution: bool,
    skip_industry_exposure: bool,
    benchmark_data: pd.DataFrame | None,
    benchmark_error: str = "",
) -> dict[str, object]:
    started_at = time.monotonic()
    last_at = started_at
    idea_id = _safe_id(str(template.get("idea_id") or template.get("name") or "idea"))
    run_id = make_run_id("factory")
    idea_dir = factory_dir / idea_id
    artifact_dir = idea_dir / "artifacts"
    idea_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    spec_payload = template.get("spec")
    if not isinstance(spec_payload, dict):
        raise DataSourceError(f"Template {idea_id} does not contain a spec object.")
    spec = StrategySpec.from_dict(spec_payload)
    validate_strategy_data(loaded.data, spec)
    prepared_data = _prepare_data(loaded.data)
    last_at = _factory_progress(f"{idea_id} data_prepared", started_at=started_at, last_at=last_at)
    result = run_backtest(prepared_data, spec)
    last_at = _factory_progress(f"{idea_id} backtest_done", started_at=started_at, last_at=last_at)
    audit = audit_backtest(prepared_data, result)
    last_at = _factory_progress(f"{idea_id} audit_done", started_at=started_at, last_at=last_at)
    sensitivity = None if skip_sensitivity else run_parameter_sensitivity(prepared_data, spec)
    last_at = _factory_progress(f"{idea_id} sensitivity_done", started_at=started_at, last_at=last_at)
    walk_forward = None if skip_walk_forward else run_walk_forward_validation(prepared_data, spec)
    last_at = _factory_progress(f"{idea_id} walk_forward_done", started_at=started_at, last_at=last_at)
    factor_ic = None if skip_factor_ic else run_factor_ic_diagnostics(loaded.data, spec)
    last_at = _factory_progress(f"{idea_id} factor_ic_done", started_at=started_at, last_at=last_at)
    industry_exposure = None if skip_industry_exposure else analyze_industry_exposure(result.holdings, loaded.data)
    last_at = _factory_progress(f"{idea_id} industry_exposure_done", started_at=started_at, last_at=last_at)
    attribution = None if skip_attribution else run_attribution_analysis(result, loaded.data, loaded=loaded)
    last_at = _factory_progress(f"{idea_id} attribution_done", started_at=started_at, last_at=last_at)
    benchmark = compare_to_benchmark(result.equity_curve, benchmark_data) if benchmark_data is not None else None
    trust = data_trust_summary(loaded)

    spec_path = idea_dir / "strategy_spec.json"
    spec_path.write_text(json.dumps(spec_to_dict(spec), ensure_ascii=False, indent=2), encoding="utf-8")
    artifact_paths = write_backtest_artifacts(
        artifact_dir,
        result,
        audit,
        metadata={
            "factory_id": factory_id,
            "idea_id": idea_id,
            "idea_name": template.get("name", spec.name),
            "category": template.get("category", ""),
            "hypothesis": template.get("hypothesis", ""),
            "source": loaded.metadata.source,
            "start_date": loaded.metadata.start_date,
            "end_date": loaded.metadata.end_date,
            "data_hash": loaded.metadata.data_hash,
            "notes": loaded.metadata.notes,
        },
    )
    artifact_paths.update(write_data_trust_artifacts(artifact_dir, trust))
    if sensitivity is not None:
        artifact_paths["sensitivity"] = write_sensitivity_artifact(artifact_dir, sensitivity)
    if walk_forward is not None:
        artifact_paths["walk_forward"] = write_walk_forward_artifact(artifact_dir, walk_forward)
    if factor_ic is not None:
        artifact_paths.update(write_factor_ic_artifacts(artifact_dir, factor_ic))
    if industry_exposure is not None:
        artifact_paths.update(write_industry_exposure_artifacts(artifact_dir, industry_exposure))
    if attribution is not None:
        artifact_paths.update(write_attribution_artifacts(artifact_dir, attribution))
    if benchmark is not None:
        artifact_paths.update(write_benchmark_artifacts(artifact_dir, benchmark))

    report_sections = [
        render_markdown_report(result, audit, notes=loaded.metadata.notes),
        render_data_trust_markdown(trust),
    ]
    if benchmark is not None:
        report_sections.append(render_benchmark_markdown(benchmark))
    elif benchmark_error:
        report_sections.append(f"## Benchmark Comparison\n\nBenchmark unavailable: {benchmark_error}\n")
    if walk_forward is not None:
        report_sections.append(render_walk_forward_markdown(walk_forward))
    if sensitivity is not None:
        report_sections.append(render_sensitivity_markdown(sensitivity))
    if factor_ic is not None:
        report_sections.append(render_factor_ic_markdown(factor_ic))
    if industry_exposure is not None:
        report_sections.append(render_industry_exposure_markdown(industry_exposure))
    if attribution is not None:
        report_sections.append(render_attribution_markdown(attribution))
    report_path = write_report(idea_dir / "report.md", _prepend_factory_report(template, loaded, "\n".join(report_sections)))

    registry_entry = register_run(
        reports_root,
        run_id=run_id,
        channel="factory",
        idea=str(template.get("hypothesis") or template.get("name") or spec.description),
        loaded=loaded,
        result=result,
        audit=audit,
        report_path=report_path,
        spec_path=spec_path,
        artifact_paths=artifact_paths,
        walk_forward=walk_forward,
        sensitivity=sensitivity,
        industry_exposure=industry_exposure,
        factor_ic=factor_ic,
        attribution=attribution,
        benchmark=benchmark,
    )
    decision_markdown = render_decision_gate_markdown(registry_entry)
    _append_report_section(report_path, decision_markdown)
    _factory_progress(f"{idea_id} artifacts_done", started_at=started_at, last_at=last_at)
    return build_idea_record(template, registry_entry, report_path=report_path, spec_path=spec_path)


def _factory_progress(label: str, *, started_at: float, last_at: float) -> float:
    now = time.monotonic()
    if os.environ.get("A_SHARE_FACTORY_PROGRESS") == "1":
        print(f"[factory] {label} +{now - last_at:.1f}s total={now - started_at:.1f}s", flush=True)
    return now


def build_idea_record(template: dict[str, object], registry_entry: dict[str, object], *, report_path: Path, spec_path: Path) -> dict[str, object]:
    score = registry_entry.get("research_score") if isinstance(registry_entry.get("research_score"), dict) else {}
    gate = registry_entry.get("decision_gate") if isinstance(registry_entry.get("decision_gate"), dict) else {}
    trust = registry_entry.get("data_trust") if isinstance(registry_entry.get("data_trust"), dict) else {}
    metrics = registry_entry.get("metrics") if isinstance(registry_entry.get("metrics"), dict) else {}
    benchmark = registry_entry.get("benchmark") if isinstance(registry_entry.get("benchmark"), dict) else {}
    walk = registry_entry.get("walk_forward") if isinstance(registry_entry.get("walk_forward"), dict) else {}
    factor = registry_entry.get("factor_ic") if isinstance(registry_entry.get("factor_ic"), dict) else {}
    benchmark = registry_entry.get("benchmark") if isinstance(registry_entry.get("benchmark"), dict) else {}
    promotion = promote_strategy_idea(registry_entry)
    return {
        "idea_id": _safe_id(str(template.get("idea_id") or template.get("name") or registry_entry.get("run_id", ""))),
        "name": str(template.get("name", "")),
        "category": str(template.get("category", "")),
        "hypothesis": str(template.get("hypothesis", "")),
        "lifecycle_status": promotion["status"],
        "recommendation": promotion["recommendation"],
        "priority": promotion["priority"],
        "blockers": promotion["blockers"],
        "next_action": promotion["next_action"],
        "run_id": registry_entry.get("run_id", ""),
        "created_at": registry_entry.get("created_at", ""),
        "score": float(score.get("score", 0.0) or 0.0),
        "research_band": score.get("band", "n/a"),
        "gate_status": gate.get("status", "n/a"),
        "gate_failed": gate.get("failed", 0),
        "data_trust_level": trust.get("trust_level", "n/a"),
        "production_data_ready": bool(trust.get("production_data_ready", False)),
        "data_source_kind": trust.get("data_source_kind", "n/a"),
        "annualized_return": metrics.get("annualized_return", 0.0),
        "max_drawdown": metrics.get("max_drawdown", 0.0),
        "sharpe": metrics.get("sharpe", 0.0),
        "benchmark_aligned_days": benchmark.get("aligned_days", 0.0),
        "excess_annualized_return": benchmark.get("excess_annualized_return", 0.0),
        "information_ratio": benchmark.get("information_ratio", 0.0),
        "trade_count": metrics.get("trade_count", 0.0),
        "walk_forward_positive_rate": walk.get("positive_rate", 0.0),
        "walk_forward_failed_count": walk.get("failed_count", 0.0),
        "factor_supportive_count": factor.get("supportive_count", 0.0),
        "factor_adverse_count": factor.get("adverse_count", 0.0),
        "report_path": str(report_path),
        "spec_path": str(spec_path),
    }


def promote_strategy_idea(registry_entry: dict[str, object]) -> dict[str, object]:
    score = registry_entry.get("research_score") if isinstance(registry_entry.get("research_score"), dict) else {}
    gate = registry_entry.get("decision_gate") if isinstance(registry_entry.get("decision_gate"), dict) else {}
    trust = registry_entry.get("data_trust") if isinstance(registry_entry.get("data_trust"), dict) else {}
    metrics = registry_entry.get("metrics") if isinstance(registry_entry.get("metrics"), dict) else {}
    walk = registry_entry.get("walk_forward") if isinstance(registry_entry.get("walk_forward"), dict) else {}
    factor = registry_entry.get("factor_ic") if isinstance(registry_entry.get("factor_ic"), dict) else {}
    audit_verdict = str(registry_entry.get("verdict", "n/a"))
    blockers = _promotion_blockers(registry_entry)
    score_value = float(score.get("score", 0.0) or 0.0)
    production_ready = bool(trust.get("production_data_ready", False))
    gate_status = str(gate.get("status", "n/a"))
    trade_count = float(metrics.get("trade_count", 0.0) or 0.0)
    max_drawdown = float(metrics.get("max_drawdown", 0.0) or 0.0)
    walk_positive = float(walk.get("positive_rate", 0.0) or 0.0)
    factor_adverse = float(factor.get("adverse_count", 0.0) or 0.0)

    if gate_status == "paper_candidate" and production_ready:
        return {
            "status": "paper_candidate",
            "recommendation": "promote_to_paper_review",
            "priority": 1,
            "blockers": blockers,
            "next_action": "Send to Paper Control only after manual review.",
        }
    if not production_ready:
        return {
            "status": "testing",
            "recommendation": "rerun_on_production_data",
            "priority": 2,
            "blockers": ["production_data_not_ready", *blockers[:5]],
            "next_action": "Rerun with production canonical assets before judging alpha.",
        }
    if audit_verdict == "abandon" or score_value < 45 or max_drawdown < -0.35:
        return {
            "status": "rejected",
            "recommendation": "reject",
            "priority": 5,
            "blockers": blockers,
            "next_action": "Archive the hypothesis or rewrite its economic logic.",
        }
    if score_value >= 75 and trade_count >= 100 and walk_positive >= 0.75 and factor_adverse == 0:
        return {
            "status": "watch",
            "recommendation": "watchlist",
            "priority": 3,
            "blockers": blockers,
            "next_action": "Stress with broader regimes, variants, and costs.",
        }
    return {
        "status": "testing",
        "recommendation": "refine",
        "priority": 4,
        "blockers": blockers,
        "next_action": "Adjust hypothesis or parameters, then rerun walk-forward and sensitivity.",
    }


def _promotion_blockers(registry_entry: dict[str, object]) -> list[str]:
    blockers: list[str] = []
    gate = registry_entry.get("decision_gate") if isinstance(registry_entry.get("decision_gate"), dict) else {}
    for check in gate.get("checks", []) or []:
        if isinstance(check, dict) and not check.get("passed", False):
            blockers.append(str(check.get("name", "gate_failed")))
    trust = registry_entry.get("data_trust") if isinstance(registry_entry.get("data_trust"), dict) else {}
    if not trust.get("production_data_ready", False):
        blockers.append(str(trust.get("trust_level", "data_not_production_ready")))
    audit_flags = registry_entry.get("audit", {})
    if isinstance(audit_flags, dict):
        blockers.extend(str(item) for item in audit_flags.get("red_flags", [])[:3])
    return list(dict.fromkeys(blockers))[:12]


def _load_factory_data(
    *,
    source: str,
    csv_path: str | Path | None,
    asset_root: str | Path | None,
    start: str,
    end: str,
    sample_symbols: int,
    universe_size: int,
    universe_lookback_days: int,
    universe_min_history_days: int,
    historical_stock_master_min_rows: int,
    min_delisted_rows: int,
    include_bj: bool,
    frozen_panel_cache_path: str | Path | None = None,
    fundamental_fields: Iterable[str] | None = None,
    required_data_fields: Iterable[str] | None = None,
) -> DataLoadResult:
    if frozen_panel_cache_path:
        return load_frozen_production_panel_cache(
            frozen_panel_cache_path,
            require_production_data=source == "production",
            min_stock_master_rows=historical_stock_master_min_rows,
        )
    if source == "sample":
        return load_sample_panel(start, end, symbols=sample_symbols)
    if source == "csv":
        if not csv_path:
            raise DataSourceError("--csv-path is required when source=csv")
        return load_csv_panel(csv_path)
    if source == "production":
        root = Path(asset_root or "data_assets")
        return load_production_asset_panel(
            root,
            start=start,
            end=end,
            universe_size=universe_size,
            universe_lookback_days=universe_lookback_days,
            universe_min_history_days=universe_min_history_days,
            min_stock_master_rows=historical_stock_master_min_rows,
            min_delisted_rows=min_delisted_rows,
            include_bj=include_bj,
            fundamental_fields=fundamental_fields,
            required_data_fields=required_data_fields,
        )
    raise DataSourceError("Strategy factory supports source=sample, source=csv, or source=production.")


def _prepend_factory_report(template: dict[str, object], loaded: DataLoadResult, body: str) -> str:
    lines = [
        f"# Strategy Factory: {template.get('name', '')}",
        "",
        f"Idea ID: `{template.get('idea_id', '')}`",
        f"Category: `{template.get('category', '')}`",
        f"Hypothesis: {template.get('hypothesis', '')}",
        f"Source: `{loaded.metadata.source}`",
        f"Range: `{loaded.metadata.start_date}` to `{loaded.metadata.end_date}`",
        f"Symbols: {len(loaded.metadata.symbols)}",
        f"Data hash: `{loaded.metadata.data_hash or 'n/a'}`",
        "",
        body,
    ]
    return "\n".join(lines)


def _append_report_section(path: Path, markdown: str) -> None:
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write("\n\n")
        handle.write(markdown)


def _flatten_idea_record(record: dict[str, object]) -> dict[str, object]:
    return {
        "idea_id": record.get("idea_id", ""),
        "name": record.get("name", ""),
        "category": record.get("category", ""),
        "lifecycle_status": record.get("lifecycle_status", ""),
        "recommendation": record.get("recommendation", ""),
        "priority": record.get("priority", 99),
        "score": record.get("score", 0.0),
        "research_band": record.get("research_band", "n/a"),
        "gate_status": record.get("gate_status", "n/a"),
        "gate_failed": record.get("gate_failed", 0),
        "data_trust_level": record.get("data_trust_level", "n/a"),
        "production_data_ready": record.get("production_data_ready", False),
        "annualized_return": record.get("annualized_return", 0.0),
        "max_drawdown": record.get("max_drawdown", 0.0),
        "trade_count": record.get("trade_count", 0.0),
        "walk_forward_positive_rate": record.get("walk_forward_positive_rate", 0.0),
        "factor_supportive_count": record.get("factor_supportive_count", 0.0),
        "benchmark_aligned_days": record.get("benchmark_aligned_days", 0.0),
        "excess_annualized_return": record.get("excess_annualized_return", 0.0),
        "information_ratio": record.get("information_ratio", 0.0),
        "run_id": record.get("run_id", ""),
        "created_at": record.get("created_at", ""),
        "report_path": record.get("report_path", ""),
        "next_action": record.get("next_action", ""),
        "blockers": " | ".join(str(item) for item in record.get("blockers", [])[:8])
        if isinstance(record.get("blockers"), list)
        else "",
    }


def _safe_id(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "_" for char in value.strip())
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned or "idea"


def _json_ready(value: object) -> object:
    if isinstance(value, pd.DataFrame):
        return value.to_dict(orient="records")
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
