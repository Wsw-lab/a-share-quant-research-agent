from __future__ import annotations

from pathlib import Path

from .backtest import BacktestResult


def render_markdown_report(result: BacktestResult, audit: dict[str, object], notes: tuple[str, ...] | None = None) -> str:
    metrics = result.metrics
    red_flags = audit.get("red_flags", [])
    warnings = audit.get("warnings", [])
    yearly = audit.get("yearly_returns")
    factor_coverage = audit.get("factor_coverage")
    stress = audit.get("slippage_stress", {})

    lines = [
        f"# Strategy Audit Report: {result.spec.name}",
        "",
        f"Verdict: **{audit['verdict']}**",
        "",
        "## Strategy",
        "",
        result.spec.description,
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Start equity | {metrics.get('start_equity', 0):,.2f} |",
        f"| End equity | {metrics.get('end_equity', 0):,.2f} |",
        f"| Total return | {metrics.get('total_return', 0):.2%} |",
        f"| Annualized return | {metrics.get('annualized_return', 0):.2%} |",
        f"| Max drawdown | {metrics.get('max_drawdown', 0):.2%} |",
        f"| Annualized volatility | {metrics.get('annualized_volatility', 0):.2%} |",
        f"| Sharpe | {metrics.get('sharpe', 0):.2f} |",
        f"| Cash yield accrued | {metrics.get('total_cash_yield', 0):,.2f} |",
        f"| Cash yield contribution | {metrics.get('cash_yield_return_contribution', 0):.2%} |",
        f"| Trades | {metrics.get('trade_count', 0):.0f} |",
        f"| Turnover | {metrics.get('turnover', 0):.2f}x |",
        "",
        "## Audit",
        "",
    ]

    if red_flags:
        lines.append("Red flags:")
        for item in red_flags:
            lines.append(f"- {item}")
    else:
        lines.append("Red flags: none")

    lines.append("")
    if warnings:
        lines.append("Warnings:")
        for item in warnings:
            lines.append(f"- {item}")
    else:
        lines.append("Warnings: none")

    lines.extend(
        [
            "",
            "## Slippage Stress",
            "",
            "| Stress case | Value |",
            "|---|---:|",
            f"| Slippage bps | {stress.get('slippage_bps', 0):.2f} |",
            f"| Annualized return | {stress.get('annualized_return', 0):.2%} |",
            f"| Max drawdown | {stress.get('max_drawdown', 0):.2%} |",
            "",
            "## Yearly Returns",
            "",
            "| Year | Return |",
            "|---|---:|",
        ]
    )
    if yearly is not None and not yearly.empty:
        for _, row in yearly.iterrows():
            lines.append(f"| {int(row['year'])} | {row['return']:.2%} |")

    lines.extend(
        [
            "",
            "## Factor Coverage",
            "",
            "| Factor | Coverage | Non-null Rows | Total Rows |",
            "|---|---:|---:|---:|",
        ]
    )
    if factor_coverage is not None and not factor_coverage.empty:
        for _, row in factor_coverage.iterrows():
            lines.append(
                f"| {row['factor']} | {row['coverage']:.2%} | {int(row['non_null'])} | {int(row['total'])} |"
            )

    lines.extend(
        [
            "",
            "## Latest Holdings",
            "",
            "| Symbol | Shares | Weight |",
            "|---|---:|---:|",
        ]
    )
    if not result.holdings.empty:
        latest_date = result.holdings["date"].max()
        latest = result.holdings[result.holdings["date"] == latest_date].sort_values("weight", ascending=False)
        for _, row in latest.head(20).iterrows():
            lines.append(f"| {row['symbol']} | {int(row['shares'])} | {row['weight']:.2%} |")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This is research software, not investment advice.",
            "- Live trading adapters are intentionally excluded from MVP v0.",
            "",
        ]
    )
    if notes is None:
        notes = ("This MVP report uses deterministic sample data, not real market data.",)
    insertion_index = lines.index("- This is research software, not investment advice.")
    for note in reversed(notes):
        lines.insert(insertion_index, f"- {note}")
    return "\n".join(lines)


def write_report(path: str | Path, markdown: str) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    return output_path

