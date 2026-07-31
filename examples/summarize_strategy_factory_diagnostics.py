from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

import pandas as pd


REPORT_DIR = "strategy_factory_diagnostics"


def main() -> int:
    args = _parse_args()
    result = summarize_factory_diagnostics(Path(args.reports_root), factory_id=args.factory_id)
    paths = write_factory_diagnostics_artifacts(Path(args.reports_root), result)
    print(f"Factory: {result.get('factory_id', 'n/a')}")
    print(f"Status: {result.get('status', 'n/a')}")
    print(f"Ideas: {result.get('summary', {}).get('total', 0)}")
    print(f"Rejected: {result.get('summary', {}).get('rejected', 0)}")
    print(f"Report: {paths['latest_report']}")
    print(f"JSON: {paths['latest_json']}")
    return 0


def summarize_factory_diagnostics(reports_root: Path, *, factory_id: str = "latest") -> dict[str, object]:
    board = _load_board(reports_root, factory_id=factory_id)
    records = [item for item in board.get("records", []) if isinstance(item, dict)]
    diagnostics = [_idea_diagnostics(record) for record in records]
    status_counts: dict[str, int] = {}
    classification_counts: dict[str, int] = {}
    for item in diagnostics:
        status = str(item.get("lifecycle_status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1
        classification = str(item.get("diagnosis_class", "unknown"))
        classification_counts[classification] = classification_counts.get(classification, 0) + 1
    summary = {
        "total": len(diagnostics),
        "errors": len(board.get("errors", []) or []),
        "skipped": len(board.get("skipped", []) or []),
        "rejected": status_counts.get("rejected", 0),
        "watch": status_counts.get("watch", 0),
        "testing": status_counts.get("testing", 0),
        "paper_candidates": status_counts.get("paper_candidate", 0),
        "status_counts": status_counts,
        "classification_counts": classification_counts,
    }
    return {
        "schema_version": 1,
        "factory_id": board.get("factory_id", "n/a"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "factory_generated_at": board.get("generated_at", "n/a"),
        "status": "diagnosed",
        "source": board.get("source", ""),
        "start_date": board.get("start_date", ""),
        "end_date": board.get("end_date", ""),
        "summary": summary,
        "ideas": diagnostics,
        "candidate_directions": _candidate_directions(diagnostics),
        "global_actions": _global_actions(diagnostics),
        "errors": board.get("errors", []),
        "skipped": board.get("skipped", []),
    }


def write_factory_diagnostics_artifacts(reports_root: Path, result: dict[str, object]) -> dict[str, Path]:
    root = reports_root / REPORT_DIR
    run_dir = root / "runs" / str(result.get("factory_id", "unknown"))
    run_dir.mkdir(parents=True, exist_ok=True)
    json_path = run_dir / "factory_diagnostics.json"
    report_path = run_dir / "factory_diagnostics.md"
    latest_json = root / "latest_factory_diagnostics.json"
    latest_report = root / "latest_factory_diagnostics.md"
    ideas_csv = run_dir / "idea_diagnostics.csv"
    pd.DataFrame(result.get("ideas", [])).to_csv(ideas_csv, index=False)
    payload = json.dumps(_json_ready(result), ensure_ascii=False, indent=2, sort_keys=True)
    json_path.write_text(payload, encoding="utf-8")
    latest_json.write_text(payload, encoding="utf-8")
    markdown = render_factory_diagnostics_markdown(result)
    report_path.write_text(markdown, encoding="utf-8")
    latest_report.write_text(markdown, encoding="utf-8")
    return {
        "run_dir": run_dir,
        "json": json_path,
        "report": report_path,
        "latest_json": latest_json,
        "latest_report": latest_report,
        "ideas_csv": ideas_csv,
    }


def render_factory_diagnostics_markdown(result: dict[str, object]) -> str:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    lines = [
        "## Strategy Factory Diagnostics",
        "",
        f"Factory: `{result.get('factory_id', 'n/a')}`",
        f"Generated at: `{result.get('generated_at', 'n/a')}`",
        f"Factory generated at: `{result.get('factory_generated_at', 'n/a')}`",
        f"Source: `{result.get('source', '')}`",
        f"Range: `{result.get('start_date', '')}` to `{result.get('end_date', '')}`",
        "",
        "### Summary",
        "",
        f"- Ideas: {summary.get('total', 0)}",
        f"- Rejected: {summary.get('rejected', 0)}",
        f"- Testing: {summary.get('testing', 0)}",
        f"- Watch: {summary.get('watch', 0)}",
        f"- Paper candidates: {summary.get('paper_candidates', 0)}",
        f"- Errors: {summary.get('errors', 0)}",
        f"- Skipped: {summary.get('skipped', 0)}",
        "",
        "### Idea Diagnosis",
        "",
        "| Idea | Status | Class | Score | Ann. | Max DD | WF+ | IC +/- | Benchmark Days | Main Failures | Next Action |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for item in result.get("ideas", []):
        if not isinstance(item, dict):
            continue
        lines.append(
            "| {idea} | {status} | {klass} | {score:.2f} | {ann:.2%} | {dd:.2%} | {wf:.0%} | {icp:.0f}/{ica:.0f} | {bdays:.0f} | {failures} | {action} |".format(
                idea=_md(str(item.get("name") or item.get("idea_id", ""))),
                status=_md(str(item.get("lifecycle_status", ""))),
                klass=_md(str(item.get("diagnosis_class", ""))),
                score=float(item.get("score", 0.0) or 0.0),
                ann=float(item.get("annualized_return", 0.0) or 0.0),
                dd=float(item.get("max_drawdown", 0.0) or 0.0),
                wf=float(item.get("walk_forward_positive_rate", 0.0) or 0.0),
                icp=float(item.get("factor_supportive_count", 0.0) or 0.0),
                ica=float(item.get("factor_adverse_count", 0.0) or 0.0),
                bdays=float(item.get("benchmark_aligned_days", 0.0) or 0.0),
                failures=_md(", ".join(str(value) for value in item.get("failed_checks", [])[:6])),
                action=_md(str(item.get("next_research_action", ""))),
            )
        )
    lines.extend(["", "### Candidate Directions", ""])
    directions = result.get("candidate_directions", [])
    if directions:
        for item in directions:
            if isinstance(item, dict):
                lines.append(f"- **{_md(str(item.get('idea_id', '')))}**: {_md(str(item.get('rationale', '')))}")
    else:
        lines.append("- No optimization candidates; rewrite the idea set.")
    lines.extend(["", "### Global Actions", ""])
    for item in result.get("global_actions", []):
        if isinstance(item, dict):
            lines.append(f"- **{_md(str(item.get('priority', '')))}** {_md(str(item.get('action', '')))}")
    lines.append("")
    return "\n".join(lines)


def _load_board(reports_root: Path, *, factory_id: str) -> dict[str, object]:
    path = reports_root / "strategy_factory" / "latest_board.json"
    if not path.exists():
        raise FileNotFoundError(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        return {}
    if factory_id != "latest" and value.get("factory_id") != factory_id:
        raise FileNotFoundError(f"No board file found for factory_id={factory_id}; latest is {value.get('factory_id')}.")
    return value


def _idea_diagnostics(record: dict[str, object]) -> dict[str, object]:
    artifact_dir = Path(str(record.get("report_path", ""))).parent / "artifacts"
    audit = _read_json(artifact_dir / "audit.json")
    factor_ic = _read_json(artifact_dir / "factor_ic_metrics.json")
    bias = _read_json(artifact_dir / "bias_diagnostics.json")
    benchmark = _read_json(artifact_dir / "benchmark_metrics.json")
    attribution = _read_json(artifact_dir / "attribution_summary.json")
    failed_checks = list(record.get("blockers", []) or [])
    diagnosis_class = _diagnosis_class(record, audit=audit, factor_ic=factor_ic, bias=bias, benchmark=benchmark)
    return {
        "idea_id": record.get("idea_id", ""),
        "name": record.get("name", ""),
        "lifecycle_status": record.get("lifecycle_status", ""),
        "recommendation": record.get("recommendation", ""),
        "diagnosis_class": diagnosis_class,
        "score": record.get("score", 0.0),
        "research_band": record.get("research_band", "n/a"),
        "annualized_return": record.get("annualized_return", 0.0),
        "max_drawdown": record.get("max_drawdown", 0.0),
        "sharpe": record.get("sharpe", 0.0),
        "trade_count": record.get("trade_count", 0.0),
        "walk_forward_positive_rate": record.get("walk_forward_positive_rate", 0.0),
        "walk_forward_failed_count": record.get("walk_forward_failed_count", 0.0),
        "factor_supportive_count": record.get("factor_supportive_count", 0.0),
        "factor_adverse_count": record.get("factor_adverse_count", 0.0),
        "benchmark_aligned_days": benchmark.get("aligned_days", record.get("benchmark_aligned_days", 0.0)) if isinstance(benchmark, dict) else record.get("benchmark_aligned_days", 0.0),
        "information_ratio": benchmark.get("information_ratio", record.get("information_ratio", 0.0)) if isinstance(benchmark, dict) else record.get("information_ratio", 0.0),
        "bias_status": bias.get("status", "missing") if isinstance(bias, dict) else "missing",
        "bias_score": bias.get("score", 0.0) if isinstance(bias, dict) else 0.0,
        "attribution_status": attribution.get("status", "missing") if isinstance(attribution, dict) else "missing",
        "audit_verdict": audit.get("verdict", "n/a") if isinstance(audit, dict) else "n/a",
        "audit_red_flags": audit.get("red_flags", []) if isinstance(audit, dict) else [],
        "failed_checks": failed_checks,
        "next_research_action": _next_research_action(record, diagnosis_class),
        "report_path": record.get("report_path", ""),
        "run_id": record.get("run_id", ""),
    }


def _diagnosis_class(record: dict[str, object], *, audit: dict[str, object], factor_ic: dict[str, object], bias: dict[str, object], benchmark: dict[str, object]) -> str:
    annualized = float(record.get("annualized_return", 0.0) or 0.0)
    drawdown = float(record.get("max_drawdown", 0.0) or 0.0)
    supportive = float(record.get("factor_supportive_count", 0.0) or 0.0)
    adverse = float(record.get("factor_adverse_count", 0.0) or 0.0)
    walk = float(record.get("walk_forward_positive_rate", 0.0) or 0.0)
    benchmark_days = float(benchmark.get("aligned_days", record.get("benchmark_aligned_days", 0.0)) or 0.0) if isinstance(benchmark, dict) else 0.0
    verdict = str(audit.get("verdict", record.get("recommendation", ""))) if isinstance(audit, dict) else ""
    if benchmark_days <= 0:
        return "diagnostic_incomplete"
    if verdict == "abandon" or (annualized < 0 and drawdown < -0.35):
        return "rewrite_or_archive"
    if drawdown < -0.25:
        return "risk_rewrite"
    if walk < 0.75:
        return "regime_unstable"
    if supportive < 1 or adverse > 0:
        return "factor_signal_weak"
    if str(bias.get("status", "missing")) not in {"ok", "warn"}:
        return "bias_incomplete"
    return "tune_candidate"


def _next_research_action(record: dict[str, object], diagnosis_class: str) -> str:
    idea_id = str(record.get("idea_id", ""))
    if diagnosis_class == "diagnostic_incomplete":
        return "rerun with benchmark and all diagnostics enabled"
    if diagnosis_class == "rewrite_or_archive":
        return "archive or rewrite economic logic before more parameter search"
    if diagnosis_class == "risk_rewrite":
        return "reduce concentration, add drawdown guard, and rerun with stricter liquidity/costs"
    if diagnosis_class == "regime_unstable":
        return "split by market regime and tune rebalance/factor windows"
    if diagnosis_class == "factor_signal_weak":
        return "replace weak factors or test orthogonal composites"
    if idea_id in {"low_vol_dividend", "defensive_cashflow_proxy"}:
        return "test capped dividend yield, lower turnover, and sector-neutral variants"
    return "tune parameters and rerun factory diagnostics"


def _candidate_directions(items: list[dict[str, object]]) -> list[dict[str, object]]:
    ranked = sorted(items, key=lambda item: (float(item.get("max_drawdown", -1.0) or -1.0), float(item.get("annualized_return", -1.0) or -1.0)), reverse=True)
    output = []
    for item in ranked:
        if len(output) >= 3:
            break
        idea_id = str(item.get("idea_id", ""))
        if str(item.get("diagnosis_class")) == "diagnostic_incomplete":
            continue
        if idea_id in {"event_momentum_proxy", "industry_rotation_proxy", "liquidity_breakout"} and float(item.get("max_drawdown", 0.0) or 0.0) < -0.6:
            continue
        output.append(
            {
                "idea_id": idea_id,
                "name": item.get("name", ""),
                "rationale": _direction_rationale(item),
            }
        )
    return output


def _direction_rationale(item: dict[str, object]) -> str:
    idea_id = str(item.get("idea_id", ""))
    if idea_id in {"low_vol_dividend", "defensive_cashflow_proxy"}:
        return "closest to a defensive income hypothesis; next test should cap dividend_yield extremes and lower turnover."
    if idea_id == "profit_repair":
        return "fundamental signal is available; next test should separate ROE level from ROE improvement and earnings dates."
    if idea_id == "quality_value_momentum":
        return "quality/value input is complete; next test should neutralize momentum crashes and valuation traps."
    return "retain only as a rewrite candidate after reducing drawdown and improving factor IC."


def _global_actions(items: list[dict[str, object]]) -> list[dict[str, object]]:
    actions = []
    if any(float(item.get("benchmark_aligned_days", 0.0) or 0.0) <= 0 for item in items):
        actions.append({"priority": "P0", "action": "Keep benchmark-code enabled in factory runs; benchmark gate otherwise cannot pass."})
    if any(float(item.get("max_drawdown", 0.0) or 0.0) < -0.25 for item in items):
        actions.append({"priority": "P1", "action": "Add drawdown-aware variants before optimizing returns; current templates are failing risk gates."})
    if any(float(item.get("factor_supportive_count", 0.0) or 0.0) < 1 for item in items):
        actions.append({"priority": "P1", "action": "Use factor_ic_summary.csv to remove factors with no supportive horizon before parameter sweeps."})
    if any(str(item.get("bias_status", "missing")) == "missing" for item in items):
        actions.append({"priority": "P2", "action": "Ensure attribution diagnostics are enabled in production factory runs."})
    actions.append({"priority": "P2", "action": "Promote only ideas that improve walk-forward positive rate, IC support, and drawdown at the same time."})
    return actions


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _json_ready(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize latest Strategy Factory diagnostics into research actions.")
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--factory-id", default="latest")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
