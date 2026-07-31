from __future__ import annotations

import argparse
from pathlib import Path
import sys

from a_share_quant_agent.alpha_line_retirement import load_alpha_line_retirement_ledger
from a_share_quant_agent.data_sources import DataSourceError
from a_share_quant_agent.strategy_factory import (
    load_strategy_templates,
    run_strategy_factory,
    write_default_templates,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATES = ROOT / "configs" / "strategy_factory_templates.json"


def main() -> int:
    args = _parse_args()
    if args.write_default_templates:
        path = write_default_templates(args.write_default_templates)
        print(f"Wrote default templates: {path}")
        return 0
    try:
        templates = load_strategy_templates(args.templates)
        alpha_line_retirement_ledger = (
            load_alpha_line_retirement_ledger(args.alpha_line_retirement_ledger)
            if args.skip_retired_alpha_lines
            else None
        )
        result = run_strategy_factory(
            reports_root=ROOT / "reports",
            templates=templates,
            source=args.source,
            csv_path=args.csv_path,
            asset_root=args.asset_root,
            start=args.start,
            end=args.end,
            sample_symbols=args.sample_symbols,
            universe_size=args.universe_size,
            universe_lookback_days=args.universe_lookback_days,
            universe_min_history_days=args.universe_min_history_days,
            historical_stock_master_min_rows=args.historical_stock_master_min_rows,
            min_delisted_rows=args.min_delisted_rows,
            include_bj=args.include_bj,
            max_ideas=args.max_ideas,
            skip_sensitivity=args.skip_sensitivity,
            skip_walk_forward=args.skip_walk_forward,
            skip_factor_ic=args.skip_factor_ic,
            skip_attribution=args.skip_attribution,
            skip_industry_exposure=args.skip_industry_exposure,
            skip_incompatible_templates=args.skip_incompatible_templates,
            benchmark_code="" if args.no_benchmark else args.benchmark_code,
            benchmark_page_size=args.benchmark_page_size,
            benchmark_cache_dir=None if args.no_cache else "cache/investoday_api",
            refresh_benchmark_cache=args.refresh_benchmark_cache,
            alpha_line_retirement_ledger=alpha_line_retirement_ledger,
            skip_retired_alpha_lines=args.skip_retired_alpha_lines,
            frozen_panel_cache_path=args.frozen_panel_cache_path or None,
        )
    except DataSourceError as exc:
        print(f"Data source error: {exc}", file=sys.stderr)
        return 2

    board = result["board"]
    summary = board.get("summary", {})
    print(f"Factory ID: {result['factory_id']}")
    print(f"Latest board: {result['paths']['latest_board']}")
    print(f"Report: {result['paths']['latest_board_report']}")
    print(f"Ideas: {summary.get('total', 0)}")
    print(f"Errors: {summary.get('errors', 0)}")
    print(f"Skipped: {summary.get('skipped', 0)}")
    print(f"Status counts: {summary.get('status_counts', {})}")
    benchmark = result.get("benchmark", {})
    if isinstance(benchmark, dict) and benchmark.get("code"):
        print(f"Benchmark: {benchmark.get('code')} rows={benchmark.get('rows', 0)} error={benchmark.get('error', '') or 'none'}")
    for record in result["records"]:
        print(
            "{idea_id} | {status} | {recommendation} | score={score:.2f} | run={run_id}".format(
                idea_id=record.get("idea_id", ""),
                status=record.get("lifecycle_status", ""),
                recommendation=record.get("recommendation", ""),
                score=float(record.get("score", 0.0) or 0.0),
                run_id=record.get("run_id", ""),
            )
        )
    return 0 if not result["errors"] else 3


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Strategy Factory v1 over a template library.")
    parser.add_argument("--templates", default=str(DEFAULT_TEMPLATES), help="Strategy template JSON file.")
    parser.add_argument("--write-default-templates", help="Write bundled default templates to this path and exit.")
    parser.add_argument("--source", choices=("sample", "csv", "production"), default="sample")
    parser.add_argument("--csv-path")
    parser.add_argument("--asset-root", default=str(ROOT / "data_assets"))
    parser.add_argument("--start", default="20210101")
    parser.add_argument("--end", default="20251231")
    parser.add_argument("--sample-symbols", type=int, default=80)
    parser.add_argument("--universe-size", type=int, default=100)
    parser.add_argument("--universe-lookback-days", type=int, default=20)
    parser.add_argument("--universe-min-history-days", type=int, default=20)
    parser.add_argument("--historical-stock-master-min-rows", type=int, default=3000)
    parser.add_argument("--min-delisted-rows", type=int, default=50)
    parser.add_argument("--include-bj", action="store_true")
    parser.add_argument("--max-ideas", type=int, default=0, help="Limit number of templates for smoke/quick runs.")
    parser.add_argument("--skip-sensitivity", action="store_true")
    parser.add_argument("--skip-walk-forward", action="store_true")
    parser.add_argument("--skip-factor-ic", action="store_true")
    parser.add_argument("--skip-attribution", action="store_true")
    parser.add_argument("--skip-industry-exposure", action="store_true")
    parser.add_argument("--skip-incompatible-templates", action="store_true")
    parser.add_argument("--skip-retired-alpha-lines", action="store_true")
    parser.add_argument(
        "--alpha-line-retirement-ledger",
        default=str(ROOT / "reports" / "alpha_line_retirement" / "latest_alpha_line_retirement.json"),
    )
    parser.add_argument("--benchmark-code", default="", help="Investoday index code, e.g. 000300, for benchmark comparison and gates.")
    parser.add_argument("--benchmark-page-size", type=int, default=500)
    parser.add_argument("--refresh-benchmark-cache", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--no-benchmark", action="store_true")
    parser.add_argument(
        "--frozen-panel-cache-path",
        default="",
        help="Explicit production panel pickle to reuse for accelerated research reruns.",
    )
    args = parser.parse_args()
    if args.max_ideas <= 0:
        args.max_ideas = None
    return args


if __name__ == "__main__":
    raise SystemExit(main())
