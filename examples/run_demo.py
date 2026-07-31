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
    report_path = ROOT / "reports" / "demo_report.md"

    spec = StrategySpec.from_json(spec_path)
    data = make_sample_panel()
    result = run_backtest(data, spec)
    audit = audit_backtest(data, result)
    markdown = render_markdown_report(result, audit)
    write_report(report_path, markdown)

    print(f"Strategy: {spec.name}")
    print(f"Verdict: {audit['verdict']}")
    print(f"Annualized return: {result.metrics['annualized_return']:.2%}")
    print(f"Max drawdown: {result.metrics['max_drawdown']:.2%}")
    print(f"Trades: {result.metrics['trade_count']:.0f}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()

