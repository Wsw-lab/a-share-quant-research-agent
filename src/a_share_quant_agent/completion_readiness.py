"""Legacy readiness rendering retained for audit, not as a maintained workflow."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .paper_control import load_paper_dashboard
from .run_registry import registry_dataframe


COMPLETION_DIR = "completion_readiness"
LATEST_READINESS_JSON = "latest_readiness.json"
LATEST_READINESS_MD = "latest_readiness.md"

DEFAULT_THRESHOLDS = {
    "min_quote_rows": 1_000_000,
    "min_candidate_runs": 3,
    "min_candidate_days": 3,
    "max_candidate_age_days": 30,
    "min_paper_control_runs": 20,
    "min_paper_calendar_days": 30,
    "min_paper_trade_days": 5,
}

LIVE_APPROVAL_PATH = "live_readiness/approval.json"


def build_completion_readiness(
    reports_root: str | Path,
    *,
    min_quote_rows: int | None = None,
    min_candidate_runs: int | None = None,
    min_candidate_days: int | None = None,
    max_candidate_age_days: int | None = None,
    min_paper_control_runs: int | None = None,
    min_paper_calendar_days: int | None = None,
    min_paper_trade_days: int | None = None,
) -> dict[str, object]:
    raise RuntimeError(
        "Legacy completion-readiness is not a maintained public workflow; "
        "use the README offline green path and its INSUFFICIENT_EVIDENCE receipt."
    )


def write_completion_readiness(
    reports_root: str | Path,
    readiness: dict[str, object] | None = None,
    *,
    output_dir: str | Path | None = None,
    **kwargs: object,
) -> dict[str, Path]:
    reports_path = Path(reports_root)
    payload = readiness if readiness is not None else build_completion_readiness(reports_path, **kwargs)
    target = Path(output_dir) if output_dir else reports_path / COMPLETION_DIR
    target.mkdir(parents=True, exist_ok=True)
    readiness_id = str(payload.get("readiness_id", _make_id("completion")))
    json_path = target / f"{readiness_id}.json"
    md_path = target / f"{readiness_id}.md"
    latest_json = target / LATEST_READINESS_JSON
    latest_md = target / LATEST_READINESS_MD
    rendered = render_completion_readiness_markdown(payload)
    json_text = json.dumps(_json_ready(payload), ensure_ascii=False, indent=2, sort_keys=True)
    json_path.write_text(json_text, encoding="utf-8")
    latest_json.write_text(json_text, encoding="utf-8")
    md_path.write_text(rendered, encoding="utf-8")
    latest_md.write_text(rendered, encoding="utf-8")
    return {
        "json": json_path,
        "markdown": md_path,
        "latest_json": latest_json,
        "latest_markdown": latest_md,
    }


def render_completion_readiness_markdown(readiness: dict[str, object]) -> str:
    summary = readiness.get("summary") if isinstance(readiness.get("summary"), dict) else {}
    stages = readiness.get("stages") if isinstance(readiness.get("stages"), list) else []
    lines = [
        "# Quant Agent Completion Readiness",
        "",
        f"Readiness ID: `{readiness.get('readiness_id', 'n/a')}`",
        f"Generated at: `{readiness.get('generated_at', 'n/a')}`",
        f"Status: `{readiness.get('status', 'n/a')}`",
        f"Completion level: {readiness.get('completion_level', 0)} / 7",
        f"Passed stages: {summary.get('passed_stages', 0)} / {summary.get('total_stages', 0)}",
        f"Hard blockers: {summary.get('hard_blockers', 0)}",
        "",
        "| Stage | Status | Passed | Hard blockers | Key metric |",
        "|---|---|---:|---:|---|",
    ]
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        metrics = stage.get("metrics") if isinstance(stage.get("metrics"), dict) else {}
        key_metric = _key_metric(stage, metrics)
        lines.append(
            "| {name} | `{status}` | {passed} | {hard} | {metric} |".format(
                name=_markdown_cell(str(stage.get("name", stage.get("stage", "")))),
                status=_markdown_cell(str(stage.get("status", ""))),
                passed="yes" if stage.get("passed") else "no",
                hard=stage.get("hard_blockers", 0),
                metric=_markdown_cell(key_metric),
            )
        )
    lines.extend(["", "## Failed Hard Checks", ""])
    failed_rows = _failed_hard_checks(stages)
    if not failed_rows:
        lines.append("- none")
    else:
        for row in failed_rows:
            lines.append(f"- `{row['stage']}.{row['check']}`: {row['detail']}")
    actions = readiness.get("next_actions") if isinstance(readiness.get("next_actions"), list) else []
    lines.extend(["", "## Next Actions", ""])
    if not actions:
        lines.append("- No hard actions remain for the selected readiness target.")
    else:
        for action in actions:
            lines.append(f"- {action}")
    lines.extend(
        [
            "",
            "## Compliance Boundary",
            "",
            str(readiness.get("compliance_boundary", "")),
            "",
        ]
    )
    return "\n".join(lines)


def target_passed(readiness: dict[str, object], target: str) -> bool:
    stages = readiness.get("stages") if isinstance(readiness.get("stages"), list) else []
    stage_map = {str(item.get("stage", "")): bool(item.get("passed")) for item in stages if isinstance(item, dict)}
    if target == "production_research":
        return bool(stage_map.get("production_data") and stage_map.get("strategy_factory"))
    if target == "paper_candidate":
        return bool(stage_map.get("paper_candidate"))
    if target == "paper_validated":
        return bool(stage_map.get("paper_validation"))
    if target == "live_ready":
        return bool(stage_map.get("live_readiness"))
    raise ValueError("target must be production_research, paper_candidate, paper_validated, or live_ready")


def _research_mvp_stage(reports_root: Path, registry: pd.DataFrame) -> dict[str, object]:
    src = Path(__file__).resolve().parent
    required_modules = ["backtest.py", "spec.py", "qdata_snapshot.py", "audit.py", "report.py"]
    checks = [
        _check("source_modules", all((src / name).exists() for name in required_modules), "Core research modules must exist."),
        _check("registry", not registry.empty, "At least one research run must be registered."),
        _check("archived_outputs", (reports_root / "run_registry.csv").exists(), "Run registry CSV must be available for review."),
    ]
    metrics = {
        "registry_rows": int(len(registry)),
        "latest_run_id": "" if registry.empty else str(registry.iloc[0].get("run_id", "")),
    }
    return _stage(
        "research_mvp",
        "Research MVP",
        checks,
        metrics=metrics,
        next_actions=["This legacy readiness flow is not maintained; use the README offline green path."]
        if _hard_failed(checks)
        else [],
    )


def _production_data_stage(production: object, thresholds: dict[str, int]) -> dict[str, object]:
    payload = production if isinstance(production, dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    quote_rows = int(_float(summary.get("quote_rows", 0)))
    checks = [
        _check("readiness_file", bool(payload), "production_data_readiness.json must exist."),
        _check("production_ready", _bool(payload.get("production_data_ready")), "Production data readiness must be true."),
        _check("hard_failures", int(_float(summary.get("hard_failed", 1))) == 0, "Production validation must have zero hard failures."),
        _check(
            "quote_rows",
            quote_rows >= int(thresholds["min_quote_rows"]),
            f"Daily quote rows {quote_rows}; required >= {thresholds['min_quote_rows']}.",
        ),
        _check("required_assets", _bool(summary.get("required_assets_ready")), "Canonical required assets must be ready."),
    ]
    metrics = {
        "status": payload.get("status", "missing"),
        "quote_rows": quote_rows,
        "eligible_symbol_coverage_rate": _float(summary.get("eligible_symbol_coverage_rate")),
        "roe_symbol_coverage_rate": _float(summary.get("roe_symbol_coverage_rate")),
    }
    return _stage(
        "production_data",
        "Production Data",
        checks,
        metrics=metrics,
        next_actions=["Provide authorized immutable data and a separately maintained validator before reassessing."]
        if _hard_failed(checks)
        else [],
    )


def _strategy_factory_stage(board: object, registry: pd.DataFrame) -> dict[str, object]:
    payload = board if isinstance(board, dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    records = payload.get("records") if isinstance(payload.get("records"), list) else []
    errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
    skipped = payload.get("skipped") if isinstance(payload.get("skipped"), list) else []
    source = str(payload.get("source", ""))
    retired_screen = _is_alpha_line_retirement_screen(payload)
    unresolved_skips = _unresolved_strategy_factory_skips(skipped)
    production_registry = _production_research_registry_records(registry)
    registry_record_count = int(len(production_registry))
    effective_record_count = len(records) if records else (registry_record_count if retired_screen else 0)
    effective_paper_candidates = (
        int(_float(summary.get("paper_candidates", 0)))
        if records
        else _registry_gate_count(production_registry, "paper_candidate")
    )
    effective_rejected = (
        int(_float(summary.get("rejected", 0)))
        if records
        else _registry_gate_count(production_registry, "research_only")
    )
    checks = [
        _check("board_file", bool(payload), "Strategy Factory latest board must exist."),
        _check("records", effective_record_count > 0, "Strategy Factory must evaluate at least one idea."),
        _check("errors", len(errors) == 0, f"Strategy Factory errors: {len(errors)}."),
        _check(
            "production_source",
            "historical_asset:" in source or (retired_screen and registry_record_count > 0),
            "Latest factory run should use canonical historical production assets.",
        ),
        _check(
            "no_unresolved_skips",
            len(unresolved_skips) == 0,
            f"Unresolved skipped templates: {len(unresolved_skips)}.",
        ),
    ]
    metrics = {
        "factory_id": payload.get("factory_id", ""),
        "generated_at": payload.get("generated_at", ""),
        "total": effective_record_count,
        "paper_candidates": effective_paper_candidates,
        "rejected": effective_rejected,
        "latest_board_source": source,
        "latest_board_skipped": int(len(skipped)),
        "retirement_screen": retired_screen,
        "registry_production_records": registry_record_count,
        "latest_registry_run_id": _latest_registry_run_id(production_registry),
    }
    return _stage(
        "strategy_factory",
        "Strategy Factory",
        checks,
        metrics=metrics,
        next_actions=["The legacy Strategy Factory command is not maintained in this checkout."]
        if _hard_failed(checks)
        else [],
    )


def _is_alpha_line_retirement_screen(payload: dict[str, object]) -> bool:
    source = str(payload.get("source", ""))
    records = payload.get("records") if isinstance(payload.get("records"), list) else []
    skipped = payload.get("skipped") if isinstance(payload.get("skipped"), list) else []
    return (
        "alpha_line_retirement_screen" in source
        and len(records) == 0
        and bool(skipped)
        and all(isinstance(item, dict) and item.get("reason") == "retired_alpha_line" for item in skipped)
    )


def _unresolved_strategy_factory_skips(skipped: list[object]) -> list[object]:
    return [
        item
        for item in skipped
        if not (isinstance(item, dict) and item.get("reason") == "retired_alpha_line")
    ]


def _production_research_registry_records(registry: pd.DataFrame) -> pd.DataFrame:
    if registry.empty:
        return registry
    frame = registry.copy()
    for column in ("production_data_ready", "data_trust_level", "created_at"):
        if column not in frame.columns:
            frame[column] = ""
    production_mask = frame["production_data_ready"].map(_bool)
    trust_mask = frame["data_trust_level"].astype(str).isin({"production_research", "production"})
    output = frame[production_mask & trust_mask].copy()
    if not output.empty:
        output["_created_at"] = pd.to_datetime(output["created_at"], errors="coerce")
        output.sort_values("_created_at", ascending=False, inplace=True)
    return output


def _registry_gate_count(registry: pd.DataFrame, gate_status: str) -> int:
    if registry.empty or "gate_status" not in registry.columns:
        return 0
    return int(registry["gate_status"].astype(str).eq(gate_status).sum())


def _latest_registry_run_id(registry: pd.DataFrame) -> str:
    if registry.empty or "run_id" not in registry.columns:
        return ""
    return str(registry.iloc[0].get("run_id", ""))


def _paper_candidate_stage(registry: pd.DataFrame, thresholds: dict[str, int]) -> dict[str, object]:
    candidates = _paper_candidates(registry)
    candidate_dates = _unique_dates(candidates.get("created_at", pd.Series(dtype=object))) if not candidates.empty else []
    latest_age = _latest_age_days(candidates.get("created_at", pd.Series(dtype=object))) if not candidates.empty else None
    checks = [
        _check("registry", not registry.empty, "Run registry must be available."),
        _check(
            "candidate_count",
            len(candidates) >= int(thresholds["min_candidate_runs"]),
            f"Production paper candidates {len(candidates)}; required >= {thresholds['min_candidate_runs']}.",
        ),
        _check(
            "candidate_days",
            len(candidate_dates) >= int(thresholds["min_candidate_days"]),
            f"Distinct candidate dates {len(candidate_dates)}; required >= {thresholds['min_candidate_days']}.",
        ),
        _check(
            "candidate_freshness",
            latest_age is not None and latest_age <= int(thresholds["max_candidate_age_days"]),
            f"Latest candidate age {latest_age if latest_age is not None else 'n/a'} days; max {thresholds['max_candidate_age_days']}.",
        ),
    ]
    metrics = {
        "candidate_runs": int(len(candidates)),
        "candidate_days": int(len(candidate_dates)),
        "latest_candidate_age_days": latest_age,
        "latest_candidate_run_id": "" if candidates.empty else str(candidates.iloc[0].get("run_id", "")),
    }
    return _stage(
        "paper_candidate",
        "Stable Paper Candidate",
        checks,
        metrics=metrics,
        next_actions=[
            "Keep rejected ideas in research_only; do not override the decision gate manually.",
            "Use failed-window diagnostics to add genuinely new PIT alpha or event data before rerunning Strategy Factory.",
        ]
        if _hard_failed(checks)
        else [],
    )


def _paper_validation_stage(
    reports_root: Path,
    dashboard: dict[str, object],
    candidate_stage: dict[str, object],
    thresholds: dict[str, int],
) -> dict[str, object]:
    paper_root = reports_root / "paper"
    controls = _read_jsonl(paper_root / "control_log.jsonl")
    risk_pass_controls = [item for item in controls if isinstance(item, dict) and _nested(item, "risk_gate", "status") == "pass"]
    trades = dashboard.get("trades") if isinstance(dashboard.get("trades"), pd.DataFrame) else pd.DataFrame()
    ledger = dashboard.get("ledger") if isinstance(dashboard.get("ledger"), pd.DataFrame) else pd.DataFrame()
    alerts = dashboard.get("alerts") if isinstance(dashboard.get("alerts"), pd.DataFrame) else pd.DataFrame()
    latest_control = dashboard.get("latest_control") if isinstance(dashboard.get("latest_control"), dict) else {}
    risk_gate = dashboard.get("risk_gate") if isinstance(dashboard.get("risk_gate"), dict) else {}
    paper_days = _date_count(ledger.get("timestamp", pd.Series(dtype=object))) if not ledger.empty else 0
    trade_days = _date_count(trades.get("date", pd.Series(dtype=object))) if not trades.empty else 0
    critical_open = _critical_open_alerts(alerts)
    checks = [
        _check("candidate_gate", bool(candidate_stage.get("passed")), "Stable paper candidate stage must pass first."),
        _check(
            "risk_pass_controls",
            len(risk_pass_controls) >= int(thresholds["min_paper_control_runs"]),
            f"Risk-passing paper controls {len(risk_pass_controls)}; required >= {thresholds['min_paper_control_runs']}.",
        ),
        _check(
            "calendar_days",
            paper_days >= int(thresholds["min_paper_calendar_days"]),
            f"Paper observation days {paper_days}; required >= {thresholds['min_paper_calendar_days']}.",
        ),
        _check(
            "trade_days",
            trade_days >= int(thresholds["min_paper_trade_days"]),
            f"Simulated trade days {trade_days}; required >= {thresholds['min_paper_trade_days']}.",
        ),
        _check("latest_risk_gate", str(risk_gate.get("status", "")) == "pass", "Latest paper risk gate must pass."),
        _check("critical_alerts", critical_open == 0, f"Open critical paper alerts: {critical_open}."),
    ]
    metrics = {
        "latest_control_id": latest_control.get("control_id", ""),
        "latest_control_status": latest_control.get("status", ""),
        "risk_pass_controls": int(len(risk_pass_controls)),
        "paper_observation_days": int(paper_days),
        "trade_days": int(trade_days),
        "open_critical_alerts": int(critical_open),
    }
    return _stage(
        "paper_validation",
        "Long Paper Validation",
        checks,
        metrics=metrics,
        next_actions=[
            "Run the daily pipeline through a stable candidate for the required paper observation window.",
            "Clear or acknowledge critical paper-control alerts only after the underlying risk issue is fixed.",
        ]
        if _hard_failed(checks)
        else [],
    )


def _ops_stage(reports_root: Path, health: object, ops: object) -> dict[str, object]:
    health_payload = health if isinstance(health, dict) else {}
    ops_payload = ops if isinstance(ops, dict) else {}
    notifications = ops_payload.get("notifications") if isinstance(ops_payload.get("notifications"), dict) else {}
    latest_pipeline = ops_payload.get("latest_pipeline") if isinstance(ops_payload.get("latest_pipeline"), dict) else {}
    checks = [
        _check("health_file", bool(health_payload), "health_status.json must exist."),
        _check("health_state", str(health_payload.get("state", "")) == "ok", "Health state must be ok."),
        _check("freshness", _bool(_nested(health_payload, "freshness", "ok")), "Data freshness gate must pass."),
        _check("failed_jobs", int(_float(health_payload.get("failed_jobs", 1))) == 0, "Failed jobs must be zero."),
        _check("interrupted_jobs", int(_float(health_payload.get("interrupted_jobs", 1))) == 0, "Interrupted jobs must be zero."),
        _check("ops_snapshot", bool(ops_payload), "ops_snapshot.json must exist."),
        _check(
            "latest_pipeline",
            str(latest_pipeline.get("status", "")) in {"", "succeeded"},
            f"Latest pipeline status is {latest_pipeline.get('status', 'n/a')}.",
            severity="warn",
        ),
        _check(
            "open_action_notifications",
            int(_float(notifications.get("action_required_open", 0))) == 0,
            f"Open action-required notifications: {notifications.get('action_required_open', 0)}.",
            severity="warn",
        ),
    ]
    metrics = {
        "health_state": health_payload.get("state", "missing"),
        "freshness_verdict": _nested(health_payload, "freshness", "verdict") or "missing",
        "failed_jobs": int(_float(health_payload.get("failed_jobs", 0))),
        "interrupted_jobs": int(_float(health_payload.get("interrupted_jobs", 0))),
        "open_notifications": int(_float(notifications.get("open", 0))),
        "action_required_open": int(_float(notifications.get("action_required_open", 0))),
    }
    return _stage(
        "ops",
        "Operations Control",
        checks,
        metrics=metrics,
        next_actions=["The legacy operations smoke command is not maintained in this checkout."]
        if _hard_failed(checks)
        else [],
    )


def _live_readiness_stage(reports_root: Path, previous_stages: list[dict[str, object]]) -> dict[str, object]:
    approval = _read_json(reports_root / LIVE_APPROVAL_PATH)
    payload = approval if isinstance(approval, dict) else {}
    prior_passed = all(bool(stage.get("passed")) for stage in previous_stages)
    checks = [
        _check("all_prior_stages", prior_passed, "Research, data, candidate, paper, and ops stages must all pass."),
        _check("approval_file", bool(payload), f"{LIVE_APPROVAL_PATH} must exist for live readiness."),
        _check("compliance_approved", _bool(payload.get("compliance_approved")), "Compliance approval must be explicit."),
        _check("manual_order_only", _bool(payload.get("manual_order_only")), "Initial live mode must be manual-order-only."),
        _check("kill_switch", _bool(payload.get("kill_switch_tested")), "A tested kill switch is required."),
        _check("broker_adapter", bool(str(payload.get("broker_adapter", "")).strip()), "A named broker adapter must be approved."),
    ]
    metrics = {
        "approval_path": str(reports_root / LIVE_APPROVAL_PATH),
        "approved_by": payload.get("approved_by", ""),
        "broker_adapter": payload.get("broker_adapter", ""),
        "max_capital": payload.get("max_capital", ""),
    }
    return _stage(
        "live_readiness",
        "Live Readiness",
        checks,
        metrics=metrics,
        status_override="blocked_by_compliance_boundary" if _hard_failed(checks) else None,
        next_actions=[
            "Do not connect a broker adapter until long paper validation, operator identity, compliance approval, and kill-switch drills are complete.",
            f"When those controls exist, write {LIVE_APPROVAL_PATH} with explicit approval fields and rerun this check in --strict live_ready mode.",
        ]
        if _hard_failed(checks)
        else [],
    )


def _stage(
    stage: str,
    name: str,
    checks: list[dict[str, object]],
    *,
    metrics: dict[str, object],
    next_actions: list[str],
    status_override: str | None = None,
) -> dict[str, object]:
    hard_blockers = _hard_failed(checks)
    warn_blockers = _warn_failed(checks)
    passed = hard_blockers == 0
    status = "pass" if passed else "fail"
    if passed and warn_blockers:
        status = "warn"
    if status_override and not passed:
        status = status_override
    return {
        "stage": stage,
        "name": name,
        "status": status,
        "passed": bool(passed),
        "hard_blockers": hard_blockers,
        "warn_blockers": warn_blockers,
        "checks": checks,
        "metrics": metrics,
        "next_actions": next_actions,
    }


def _completion_status(stages: list[dict[str, object]]) -> str:
    stage_map = {str(stage.get("stage")): bool(stage.get("passed")) for stage in stages}
    if stage_map.get("live_readiness"):
        return "live_ready_manual_only"
    if stage_map.get("paper_validation"):
        return "paper_validated_not_live"
    if stage_map.get("paper_candidate"):
        return "paper_candidate_ready_for_validation"
    if stage_map.get("strategy_factory") and stage_map.get("production_data"):
        return "production_research_ready_no_stable_candidate"
    if stage_map.get("production_data"):
        return "production_data_ready"
    if stage_map.get("research_mvp"):
        return "research_mvp_ready"
    return "incomplete"


def _completion_level(stages: list[dict[str, object]]) -> int:
    return sum(1 for stage in stages if stage.get("passed"))


def _summary(stages: list[dict[str, object]]) -> dict[str, object]:
    return {
        "total_stages": len(stages),
        "passed_stages": _completion_level(stages),
        "hard_blockers": sum(int(stage.get("hard_blockers", 0) or 0) for stage in stages),
        "warn_blockers": sum(int(stage.get("warn_blockers", 0) or 0) for stage in stages),
        "first_failed_stage": next((stage.get("stage") for stage in stages if not stage.get("passed")), ""),
    }


def _next_actions(stages: list[dict[str, object]]) -> list[str]:
    actions: list[str] = []
    seen: set[str] = set()
    for stage in stages:
        if stage.get("passed"):
            continue
        for action in stage.get("next_actions", []) or []:
            text = str(action)
            if text and text not in seen:
                seen.add(text)
                actions.append(text)
    return actions[:10]


def _failed_hard_checks(stages: list[object]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        for check in stage.get("checks", []) or []:
            if not isinstance(check, dict):
                continue
            if check.get("passed") or str(check.get("severity", "hard")) != "hard":
                continue
            rows.append(
                {
                    "stage": str(stage.get("stage", "")),
                    "check": str(check.get("name", "")),
                    "detail": str(check.get("detail", "")),
                }
            )
    return rows


def _paper_candidates(registry: pd.DataFrame) -> pd.DataFrame:
    if registry.empty:
        return registry
    frame = registry.copy()
    for column in ("gate_status", "production_data_ready", "data_quality_status", "created_at"):
        if column not in frame.columns:
            frame[column] = ""
    mask = (
        frame["gate_status"].astype(str).eq("paper_candidate")
        & frame["production_data_ready"].map(_bool)
        & frame["data_quality_status"].astype(str).isin({"ok", "warn"})
    )
    output = frame[mask].copy()
    if not output.empty:
        output["_created_at"] = pd.to_datetime(output["created_at"], errors="coerce")
        output.sort_values("_created_at", ascending=False, inplace=True)
    return output


def _registry_frame(reports_root: Path) -> pd.DataFrame:
    csv_path = reports_root / "run_registry.csv"
    if csv_path.exists():
        try:
            return pd.read_csv(csv_path)
        except pd.errors.EmptyDataError:
            return pd.DataFrame()
    return registry_dataframe(reports_root)


def _unique_dates(values: pd.Series) -> list[str]:
    parsed = pd.to_datetime(values, errors="coerce").dropna()
    if parsed.empty:
        return []
    return sorted({item.date().isoformat() for item in parsed})


def _latest_age_days(values: pd.Series) -> int | None:
    parsed = pd.to_datetime(values, errors="coerce").dropna()
    if parsed.empty:
        return None
    latest = parsed.max()
    return int((pd.Timestamp(datetime.now()) - latest).days)


def _date_count(values: pd.Series) -> int:
    parsed = pd.to_datetime(values, errors="coerce").dropna()
    if parsed.empty:
        return 0
    return len({item.date().isoformat() for item in parsed})


def _critical_open_alerts(alerts: pd.DataFrame) -> int:
    if alerts.empty:
        return 0
    severity = alerts.get("severity", pd.Series(dtype=object)).astype(str)
    status = alerts.get("status", pd.Series(dtype=object)).astype(str)
    return int(((severity == "critical") & (status == "open")).sum())


def _key_metric(stage: dict[str, object], metrics: dict[str, object]) -> str:
    name = str(stage.get("stage", ""))
    if name == "research_mvp":
        return f"registry_rows={metrics.get('registry_rows', 0)}"
    if name == "production_data":
        return f"quote_rows={metrics.get('quote_rows', 0)}"
    if name == "strategy_factory":
        return f"factory={metrics.get('factory_id', '')}, candidates={metrics.get('paper_candidates', 0)}"
    if name == "paper_candidate":
        return f"candidate_runs={metrics.get('candidate_runs', 0)}"
    if name == "paper_validation":
        return f"paper_days={metrics.get('paper_observation_days', 0)}, trade_days={metrics.get('trade_days', 0)}"
    if name == "ops":
        return f"health={metrics.get('health_state', '')}, action_open={metrics.get('action_required_open', 0)}"
    if name == "live_readiness":
        return f"broker={metrics.get('broker_adapter', '') or 'none'}"
    return ""


def _read_json(path: Path) -> object:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _read_jsonl(path: Path) -> list[object]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _check(name: str, passed: bool, detail: str, *, severity: str = "hard") -> dict[str, object]:
    return {"name": name, "passed": bool(passed), "severity": severity, "detail": detail}


def _hard_failed(checks: list[dict[str, object]]) -> int:
    return sum(1 for check in checks if not check.get("passed") and str(check.get("severity", "hard")) == "hard")


def _warn_failed(checks: list[dict[str, object]]) -> int:
    return sum(1 for check in checks if not check.get("passed") and str(check.get("severity", "hard")) == "warn")


def _nested(container: object, *keys: str) -> object:
    current = container
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _float(value: object, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coalesce_int(value: int | None, default: int) -> int:
    return default if value is None else int(value)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _make_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]}"


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _json_ready(value: object) -> object:
    if isinstance(value, pd.DataFrame):
        return value.to_dict(orient="records")
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
