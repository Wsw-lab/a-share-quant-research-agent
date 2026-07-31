from __future__ import annotations

import argparse
from pathlib import Path

from a_share_quant_agent.completion_readiness import (
    build_completion_readiness,
    target_passed,
    write_completion_readiness,
)


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the quant-agent completion readiness report.")
    parser.add_argument("--reports-root", default=str(ROOT / "reports"))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--min-quote-rows", type=int)
    parser.add_argument("--min-candidate-runs", type=int)
    parser.add_argument("--min-candidate-days", type=int)
    parser.add_argument("--max-candidate-age-days", type=int)
    parser.add_argument("--min-paper-control-runs", type=int)
    parser.add_argument("--min-paper-calendar-days", type=int)
    parser.add_argument("--min-paper-trade-days", type=int)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return a non-zero exit code when the selected target is not passed.",
    )
    parser.add_argument(
        "--target",
        choices=["production_research", "paper_candidate", "paper_validated", "live_ready"],
        default="paper_validated",
        help="Readiness target used only with --strict.",
    )
    args = parser.parse_args()

    reports_root = Path(args.reports_root)
    readiness = build_completion_readiness(
        reports_root,
        min_quote_rows=args.min_quote_rows,
        min_candidate_runs=args.min_candidate_runs,
        min_candidate_days=args.min_candidate_days,
        max_candidate_age_days=args.max_candidate_age_days,
        min_paper_control_runs=args.min_paper_control_runs,
        min_paper_calendar_days=args.min_paper_calendar_days,
        min_paper_trade_days=args.min_paper_trade_days,
    )
    paths = write_completion_readiness(
        reports_root,
        readiness,
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )
    print(f"Readiness ID: {readiness['readiness_id']}")
    print(f"Status: {readiness['status']}")
    print(f"Completion level: {readiness['completion_level']} / 7")
    print(f"Report: {paths['latest_markdown']}")
    print(f"JSON: {paths['latest_json']}")
    if args.strict and not target_passed(readiness, args.target):
        print(f"Strict target failed: {args.target}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
