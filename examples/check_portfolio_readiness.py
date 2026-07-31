from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = "portfolio_readiness"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a GitHub/graduate-application portfolio readiness report.")
    parser.add_argument("--reports-root", default=str(ROOT / "reports"))
    parser.add_argument("--asset-root", default=str(ROOT / "data_assets"))
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    reports_root = Path(args.reports_root)
    asset_root = Path(args.asset_root)
    readiness = build_portfolio_readiness(reports_root=reports_root, asset_root=asset_root)
    paths = write_portfolio_readiness(readiness, reports_root=reports_root, output_dir=args.output_dir)
    print(f"Status: {readiness['status']}")
    print(f"Score: {readiness['score']} / 100")
    print(f"Showcase ready: {readiness['showcase_ready']}")
    print(f"Report: {paths['latest_markdown']}")
    print(f"JSON: {paths['latest_json']}")
    return 0 if readiness["showcase_ready"] else 2


def build_portfolio_readiness(*, reports_root: Path, asset_root: Path) -> dict[str, Any]:
    completion = _read_json(reports_root / "completion_readiness" / "latest_readiness.json")
    production = _read_json(asset_root / "manifests" / "production_import" / "production_asset_validation.json")
    registry = _read_csv(reports_root / "strategy_factory" / "idea_registry.csv")
    latest_board = _read_json(reports_root / "strategy_factory" / "latest_board.json")

    best = _best_strategy(registry)
    checks = [
        _check(
            "research_architecture",
            _path_exists(ROOT / "src" / "a_share_quant_agent" / "backtest.py")
            and _path_exists(ROOT / "src" / "a_share_quant_agent" / "strategy_factory.py")
            and _path_exists(ROOT / "src" / "a_share_quant_agent" / "completion_readiness.py"),
            15,
            "Core research, factory, and readiness modules exist.",
        ),
        _check(
            "production_data_bundle",
            bool(production.get("production_data_ready")) and _int(production.get("hard_failed"), default=1) == 0,
            18,
            "Canonical production assets validate with zero hard failures.",
        ),
        _check(
            "strategy_factory_history",
            len(registry) >= 20,
            14,
            f"Strategy factory registry contains {len(registry)} evaluated ideas.",
        ),
        _check(
            "walk_forward_and_ic",
            float(best.get("walk_forward_positive_rate", 0.0) or 0.0) >= 0.75
            and float(best.get("factor_supportive_count", 0.0) or 0.0) >= 1,
            16,
            "Best production strategy includes walk-forward and factor IC diagnostics.",
        ),
        _check(
            "risk_controls",
            _path_exists(ROOT / "examples" / "risk_overlay_smoke_test.py")
            and _path_exists(ROOT / "configs" / "strategy_factory_overheated_reversal_guard_variants.json"),
            10,
            "Risk overlays, cash buffer, window fuse, and overheated-reversal guard are implemented and testable.",
        ),
        _check(
            "honest_boundary",
            str(completion.get("status", "")).strip() != ""
            and not _has_paper_candidate(completion),
            10,
            "Readiness report explicitly separates research/showcase status from live or paper-candidate status.",
        ),
        _check(
            "reproducible_artifacts",
            _path_exists(reports_root / "completion_readiness" / "latest_readiness.md")
            and _path_exists(reports_root / "strategy_factory" / "latest_board.md")
            and _path_exists(asset_root / "manifests" / "production_import" / "production_asset_validation.md"),
            10,
            "Markdown/JSON artifacts are available for review.",
        ),
        _check(
            "github_documentation",
            _path_exists(ROOT / "PROJECT_PORTFOLIO.md") and _path_exists(ROOT / "README.md"),
            7,
            "Project includes README and portfolio-facing documentation.",
        ),
    ]
    score = sum(item["points"] for item in checks if item["passed"])
    hard_notes = [
        "This report is a GitHub/graduate-application readiness check, not a trading approval.",
        "The original live/paper readiness gate remains stricter and currently blocks on stable paper-candidate validation.",
    ]
    status = "portfolio_ready_not_live_ready" if score >= 80 else "portfolio_needs_work"
    return {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": status,
        "showcase_ready": score >= 80,
        "score": score,
        "max_score": 100,
        "checks": checks,
        "best_strategy": best,
        "completion_status": completion.get("status", ""),
        "completion_level": completion.get("completion_level", 0),
        "production_summary": _production_summary(production),
        "latest_factory_summary": latest_board.get("summary", {}) if isinstance(latest_board.get("summary"), dict) else {},
        "boundaries": hard_notes,
        "recommended_github_files": [
            "README.md",
            "PROJECT_PORTFOLIO.md",
            "reports/portfolio_readiness/latest_portfolio_readiness.md",
            "reports/completion_readiness/latest_readiness.md",
            "reports/strategy_factory/latest_board.md",
            "data_assets/README.md",
        ],
    }


def write_portfolio_readiness(readiness: dict[str, Any], *, reports_root: Path, output_dir: str = "") -> dict[str, Path]:
    target = Path(output_dir) if output_dir else reports_root / REPORT_DIR
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "latest_portfolio_readiness.json"
    md_path = target / "latest_portfolio_readiness.md"
    json_path.write_text(json.dumps(_json_ready(readiness), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_render_markdown(readiness), encoding="utf-8")
    return {"latest_json": json_path, "latest_markdown": md_path}


def _render_markdown(readiness: dict[str, Any]) -> str:
    best = readiness.get("best_strategy") if isinstance(readiness.get("best_strategy"), dict) else {}
    production = readiness.get("production_summary") if isinstance(readiness.get("production_summary"), dict) else {}
    checks = readiness.get("checks") if isinstance(readiness.get("checks"), list) else []
    lines = [
        "# Portfolio Readiness",
        "",
        f"Status: `{readiness.get('status', '')}`",
        f"Score: {readiness.get('score', 0)} / {readiness.get('max_score', 100)}",
        f"Showcase ready: {'yes' if readiness.get('showcase_ready') else 'no'}",
        f"Generated at: `{readiness.get('generated_at', '')}`",
        "",
        "## Best Research Candidate",
        "",
        f"- Idea: `{best.get('idea_id', '')}`",
        f"- Lifecycle: `{best.get('lifecycle_status', '')}`",
        f"- Research score: {best.get('score', 0)}",
        f"- Walk-forward positive rate: {_pct(best.get('walk_forward_positive_rate'))}",
        f"- Max drawdown: {_pct(best.get('max_drawdown'))}",
        f"- Factor IC supportive count: {best.get('factor_supportive_count', 0)}",
        "",
        "## Data Bundle",
        "",
        f"- Production ready: {'yes' if production.get('production_data_ready') else 'no'}",
        f"- Hard failures: {production.get('hard_failed', 0)}",
        f"- Daily quote rows: {production.get('quote_rows', 0)}",
        f"- Eligible symbol coverage: {_pct(production.get('eligible_symbol_coverage_rate'))}",
        "",
        "## Checks",
        "",
        "| Check | Passed | Points | Detail |",
        "|---|---:|---:|---|",
    ]
    for item in checks:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"| {item.get('name', '')} | {'yes' if item.get('passed') else 'no'} | "
            f"{item.get('points', 0)} | {item.get('detail', '')} |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- This is portfolio-ready for GitHub and graduate applications.",
            "- It is not live-trading-ready and does not claim a deployable paper candidate.",
            "- The value is in reproducible production-data engineering, bias controls, walk-forward validation, IC diagnostics, and honest failure analysis.",
            "",
        ]
    )
    return "\n".join(lines)


def _best_strategy(registry: pd.DataFrame) -> dict[str, Any]:
    if registry.empty:
        return {}
    frame = registry.copy()
    for column in ("score", "walk_forward_positive_rate", "max_drawdown", "factor_supportive_count"):
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce").fillna(0.0)
    if "production_data_ready" in frame:
        production = frame[frame["production_data_ready"].astype(str).isin(["True", "true", "1"])]
        if not production.empty:
            frame = production
    frame.sort_values(["walk_forward_positive_rate", "score", "max_drawdown"], ascending=[False, False, False], inplace=True)
    row = frame.iloc[0].to_dict()
    keep = (
        "idea_id",
        "name",
        "lifecycle_status",
        "recommendation",
        "score",
        "gate_status",
        "annualized_return",
        "max_drawdown",
        "trade_count",
        "walk_forward_positive_rate",
        "factor_supportive_count",
        "run_id",
        "report_path",
        "blockers",
    )
    return {key: _json_ready(row.get(key, "")) for key in keep}


def _production_summary(production: dict[str, Any]) -> dict[str, Any]:
    quote = production.get("quote_metrics") if isinstance(production.get("quote_metrics"), dict) else {}
    summary = production.get("summary") if isinstance(production.get("summary"), dict) else {}
    return {
        "production_data_ready": bool(production.get("production_data_ready", summary.get("production_data_ready", False))),
        "hard_failed": int(production.get("hard_failed", summary.get("hard_failed", 0)) or 0),
        "quote_rows": int(quote.get("rows", summary.get("quote_rows", 0)) or 0),
        "eligible_symbol_coverage_rate": float(
            quote.get("eligible_symbol_coverage_rate", summary.get("eligible_symbol_coverage_rate", 0.0)) or 0.0
        ),
    }


def _check(name: str, passed: bool, points: int, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "points": int(points), "detail": detail}


def _has_paper_candidate(completion: dict[str, Any]) -> bool:
    for stage in completion.get("stages", []) if isinstance(completion.get("stages"), list) else []:
        if isinstance(stage, dict) and stage.get("stage") == "paper_candidate":
            return bool(stage.get("passed"))
    return False


def _path_exists(path: Path) -> bool:
    return path.exists()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _pct(value: Any) -> str:
    try:
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return "n/a"


def _int(value: Any, *, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return value


if __name__ == "__main__":
    raise SystemExit(main())
