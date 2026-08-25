from __future__ import annotations

from pathlib import Path

from a_share_quant_agent.audit import audit_backtest
from a_share_quant_agent.backtest import run_backtest
from a_share_quant_agent.report import render_markdown_report, write_report
from a_share_quant_agent.sample_data import make_sample_panel
from a_share_quant_agent.spec import StrategySpec


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    spec_path = ROOT / "examples" / "strategy_specs" / "quality_value_momentum.json"
    report_relative = Path(".research-artifacts") / "demo" / "demo_report.md"
    report_path = ROOT / report_relative

    spec = StrategySpec.from_json(spec_path)
    data = make_sample_panel()
    result = run_backtest(data, spec)
    audit = audit_backtest(data, result)
    markdown = render_markdown_report(result, audit)
    write_report(report_path, markdown)

    print(f"Strategy: {spec.name}")
    print("Evidence: synthetic engine demonstration only; no performance claim")
    print(f"Synthetic audit outcome: {audit['verdict']}")
    print(f"Report: {report_relative.as_posix()}")


if __name__ == "__main__":
    main()
