from __future__ import annotations

import json
from pathlib import Path
import sys

from a_share_quant_agent.audit import audit_backtest
from a_share_quant_agent.backtest import run_backtest
from a_share_quant_agent.nl_parser import parse_strategy_idea
from a_share_quant_agent.report import render_markdown_report, write_report
from a_share_quant_agent.sample_data import make_sample_panel
from a_share_quant_agent.spec import spec_to_dict


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IDEA = (
    "每月买入 ROE 排名前 30%、PE 排名后 40%、近 60 日涨幅排名前 30%、"
    "且过去 20 日成交额大于 1 亿的非 ST 股票，等权持有 20 只。"
)


def main() -> None:
    idea = " ".join(sys.argv[1:]).strip() or DEFAULT_IDEA
    parse_result = parse_strategy_idea(idea)
    spec = parse_result.spec

    generated_spec_path = ROOT / "reports" / "generated_strategy_spec.json"
    report_path = ROOT / "reports" / "idea_report.md"

    generated_spec_path.write_text(
        json.dumps(spec_to_dict(spec), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    data = make_sample_panel()
    result = run_backtest(data, spec)
    audit = audit_backtest(data, result)
    markdown = _prepend_parse_notes(
        render_markdown_report(result, audit),
        idea,
        parse_result.assumptions,
        parse_result.warnings,
    )
    write_report(report_path, markdown)

    print(f"Idea: {idea}")
    print(f"Generated spec: {generated_spec_path}")
    print(f"Report: {report_path}")
    print(f"Verdict: {audit['verdict']}")
    print(f"Annualized return: {result.metrics['annualized_return']:.2%}")
    print(f"Max drawdown: {result.metrics['max_drawdown']:.2%}")
    print(f"Trades: {result.metrics['trade_count']:.0f}")


def _prepend_parse_notes(markdown: str, idea: str, assumptions: tuple[str, ...], warnings: tuple[str, ...]) -> str:
    lines = [
        "# Natural Language Parse",
        "",
        f"Original idea: {idea}",
        "",
        "## Parser Notes",
        "",
    ]
    if assumptions:
        lines.append("Assumptions:")
        lines.extend(f"- {item}" for item in assumptions)
    else:
        lines.append("Assumptions: none")
    lines.append("")
    if warnings:
        lines.append("Warnings:")
        lines.extend(f"- {item}" for item in warnings)
    else:
        lines.append("Warnings: none")
    lines.extend(["", "---", "", markdown])
    return "\n".join(lines)


if __name__ == "__main__":
    main()

