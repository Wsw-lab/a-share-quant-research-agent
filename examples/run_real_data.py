from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

from a_share_quant_agent.artifacts import write_backtest_artifacts
from a_share_quant_agent.audit import audit_backtest
from a_share_quant_agent.attribution import (
    render_attribution_markdown,
    run_attribution_analysis,
    write_attribution_artifacts,
)
from a_share_quant_agent.backtest import run_backtest
from a_share_quant_agent.benchmark import (
    compare_to_benchmark,
    render_benchmark_markdown,
    write_benchmark_artifacts,
)
from a_share_quant_agent.data_sources import (
    DataLoadResult,
    DataSourceError,
    apply_point_in_time_liquidity_universe,
    apply_point_in_time_stock_master_filter,
    data_trust_summary,
    enforce_production_data,
    dataframe_hash,
    enrich_panel_with_stock_master,
    enrich_panel_with_universe_classification,
    load_akshare_panel,
    load_csv_panel,
    load_investoday_benchmark_quotes,
    load_investoday_panel,
    load_investoday_realtime_universe,
    load_investoday_stock_master,
    load_sample_panel,
    load_stock_master_csv,
    load_tushare_panel,
    render_data_trust_markdown,
    symbols_from_stock_master,
    validate_stock_master_asset,
    validate_strategy_data,
    write_data_trust_artifacts,
)
from a_share_quant_agent.exposure import (
    analyze_industry_exposure,
    render_industry_exposure_markdown,
    write_industry_exposure_artifacts,
)
from a_share_quant_agent.factor_diagnostics import (
    render_factor_ic_markdown,
    run_factor_ic_diagnostics,
    write_factor_ic_artifacts,
)
from a_share_quant_agent.nl_parser import parse_strategy_idea
from a_share_quant_agent.paper import build_paper_rebalance, render_paper_rebalance_markdown, write_paper_rebalance
from a_share_quant_agent.report import render_markdown_report, write_report
from a_share_quant_agent.run_registry import (
    archive_cli_run,
    make_run_id,
    register_run,
    render_decision_gate_markdown,
)
from a_share_quant_agent.sensitivity import (
    render_sensitivity_markdown,
    run_parameter_sensitivity,
    write_sensitivity_artifact,
)
from a_share_quant_agent.spec import CostSpec, PortfolioSpec, RebalanceSpec, StrategySpec, UniverseSpec, spec_to_dict
from a_share_quant_agent.walk_forward import (
    render_walk_forward_markdown,
    run_walk_forward_validation,
    write_walk_forward_artifact,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IDEA = "每月买入近60日涨幅强、低波动、成交额大于5000万的非ST股票，等权持有5只"
DEFAULT_SYMBOLS = "600000.SH,000001.SZ,600519.SH,000858.SZ,600036.SH,601318.SH,000333.SZ,300750.SZ,600030.SH,601012.SH"


def main() -> None:
    args = _parse_args()
    idea = args.idea.strip() or DEFAULT_IDEA
    parse_result = parse_strategy_idea(idea)
    spec = _apply_strategy_overrides(parse_result.spec, args)

    try:
        loaded = _load_data(args)
        validate_strategy_data(loaded.data, spec)
        if args.require_production_data:
            enforce_production_data(loaded, min_stock_master_rows=args.historical_stock_master_min_rows)
        result = run_backtest(loaded.data, spec)
        audit = audit_backtest(loaded.data, result)
        sensitivity = None if args.skip_sensitivity else run_parameter_sensitivity(loaded.data, spec)
        walk_forward = (
            None
            if args.skip_walk_forward
            else run_walk_forward_validation(
                loaded.data,
                spec,
                train_months=args.walk_forward_train_months,
                test_months=args.walk_forward_test_months,
                step_months=args.walk_forward_step_months,
                min_train_days=args.walk_forward_min_train_days,
                min_test_days=args.walk_forward_min_test_days,
            )
        )
        industry_exposure = None if args.skip_industry_exposure else analyze_industry_exposure(result.holdings, loaded.data)
        factor_ic = (
            None
            if args.skip_factor_ic
            else run_factor_ic_diagnostics(
                loaded.data,
                spec,
                horizons=_parse_int_tuple(args.factor_ic_horizons),
                min_observations=args.factor_ic_min_observations,
                use_rebalance_dates=not args.factor_ic_all_dates,
            )
        )
        attribution = None if args.skip_attribution else run_attribution_analysis(result, loaded.data, loaded=loaded)
        benchmark = None
        if args.benchmark_code and args.source == "investoday":
            benchmark_loaded = load_investoday_benchmark_quotes(
                index_code=args.benchmark_code,
                start=args.start,
                end=args.end,
                page_size=args.page_size,
                cache_dir=None if args.no_cache else "cache/investoday_api",
                refresh_cache=args.refresh_cache,
            )
            benchmark = compare_to_benchmark(result.equity_curve, benchmark_loaded.data)
    except DataSourceError as exc:
        print(f"Data source error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    artifact_dir = ROOT / "reports" / "real_data_artifacts"
    spec_path = ROOT / "reports" / "real_data_strategy_spec.json"
    report_path = ROOT / "reports" / "real_data_report.md"
    spec_path.write_text(json.dumps(spec_to_dict(spec), ensure_ascii=False, indent=2), encoding="utf-8")
    _remove_stale_optional_artifacts(artifact_dir)
    artifact_paths = write_backtest_artifacts(
        artifact_dir,
        result,
        audit,
        metadata=_metadata_payload(args, idea, loaded, parse_result.assumptions, parse_result.warnings),
    )
    if sensitivity is not None:
        artifact_paths["sensitivity"] = write_sensitivity_artifact(artifact_dir, sensitivity)
    if walk_forward is not None:
        artifact_paths["walk_forward"] = write_walk_forward_artifact(artifact_dir, walk_forward)
    if industry_exposure is not None:
        artifact_paths.update(write_industry_exposure_artifacts(artifact_dir, industry_exposure))
    if factor_ic is not None:
        artifact_paths.update(write_factor_ic_artifacts(artifact_dir, factor_ic))
    if attribution is not None:
        artifact_paths.update(write_attribution_artifacts(artifact_dir, attribution))
    if benchmark is not None:
        artifact_paths.update(write_benchmark_artifacts(artifact_dir, benchmark))
    trust = data_trust_summary(loaded, min_stock_master_rows=args.historical_stock_master_min_rows)
    artifact_paths.update(write_data_trust_artifacts(artifact_dir, trust))
    if loaded.universe is not None and not loaded.universe.empty:
        artifact_paths["universe"] = _write_universe_artifact(artifact_dir, loaded.universe)
    if loaded.stock_master is not None and not loaded.stock_master.empty:
        artifact_paths["stock_master"] = _write_stock_master_artifact(artifact_dir, loaded.stock_master)
    paper_plan = build_paper_rebalance(loaded.data, result)
    paper_paths = write_paper_rebalance(artifact_dir, paper_plan)

    report_sections = [render_markdown_report(result, audit, notes=_report_notes(loaded))]
    if benchmark is not None:
        report_sections.append(render_benchmark_markdown(benchmark))
    if walk_forward is not None:
        report_sections.append(render_walk_forward_markdown(walk_forward))
    if sensitivity is not None:
        report_sections.append(render_sensitivity_markdown(sensitivity))
    if industry_exposure is not None:
        report_sections.append(render_industry_exposure_markdown(industry_exposure))
    if factor_ic is not None:
        report_sections.append(render_factor_ic_markdown(factor_ic))
    if attribution is not None:
        report_sections.append(render_attribution_markdown(attribution))
    report_sections.append(render_data_trust_markdown(trust))
    report_sections.extend(
        [
            render_paper_rebalance_markdown(paper_plan),
            _render_artifact_index({**artifact_paths, **paper_paths}),
        ]
    )
    markdown = _prepend_run_notes(
        "\n".join(report_sections),
        idea,
        loaded,
        parse_result.assumptions,
        parse_result.warnings,
    )
    write_report(report_path, markdown)
    run_id = make_run_id("cli")
    run_paths = archive_cli_run(ROOT / "reports", run_id, report_path, spec_path, artifact_dir)
    archived_artifact_paths = _archived_artifact_paths({**artifact_paths, **paper_paths}, run_paths["artifact_dir"])
    archived_sections = report_sections[:-1] + [_render_artifact_index(archived_artifact_paths)]
    archived_markdown = _prepend_run_notes(
        "\n".join(archived_sections),
        idea,
        loaded,
        parse_result.assumptions,
        parse_result.warnings,
    )
    write_report(run_paths["report_path"], archived_markdown)
    registry_entry = register_run(
        ROOT / "reports",
        run_id=run_id,
        channel="cli",
        idea=idea,
        loaded=loaded,
        result=result,
        audit=audit,
        report_path=run_paths["report_path"],
        spec_path=run_paths["spec_path"],
        artifact_paths=archived_artifact_paths,
        assumptions=parse_result.assumptions,
        warnings=parse_result.warnings,
        benchmark=benchmark,
        walk_forward=walk_forward,
        sensitivity=sensitivity,
        industry_exposure=industry_exposure,
        factor_ic=factor_ic,
        attribution=attribution,
    )
    decision_markdown = render_decision_gate_markdown(registry_entry)
    _append_report_section(report_path, decision_markdown)
    _append_report_section(run_paths["report_path"], decision_markdown)

    print(f"Source: {loaded.metadata.source}")
    print(f"Idea: {idea}")
    print(f"Run ID: {run_id}")
    print(f"Symbols: {len(loaded.metadata.symbols)}")
    print(f"Rows: {len(loaded.data)}")
    if loaded.metadata.data_hash:
        print(f"Data snapshot sha256: {loaded.metadata.data_hash}")
    if loaded.stock_master is not None and not loaded.stock_master.empty:
        print(f"Stock master rows: {len(loaded.stock_master)}")
    print(f"Generated spec: {spec_path}")
    print(f"Report: {report_path}")
    print(f"Archived report: {run_paths['report_path']}")
    print(f"Artifacts: {artifact_dir}")
    gate = registry_entry["decision_gate"]
    print(f"Decision gate: {gate['status']} ({gate['failed']} failed)")
    score = registry_entry.get("research_score", {})
    if isinstance(score, dict):
        print(f"Research score: {score.get('score', 0)} ({score.get('band', 'n/a')})")
    quality = registry_entry.get("data_quality", {})
    if isinstance(quality, dict):
        print(
            "Data quality: "
            f"{quality.get('status', 'n/a')} "
            f"latest={quality.get('latest_date', 'n/a')} "
            f"freshness_days={quality.get('freshness_days', 'n/a')}"
        )
    print(
        "Data trust: "
        f"{trust.get('trust_level', 'n/a')} "
        f"production_ready={trust.get('production_data_ready', False)} "
        f"universe={trust.get('universe_source', 'n/a')}"
    )
    print(f"Registry: {ROOT / 'reports' / 'run_registry.csv'}")
    print(f"Verdict: {audit['verdict']}")
    print(f"Annualized return: {result.metrics['annualized_return']:.2%}")
    print(f"Max drawdown: {result.metrics['max_drawdown']:.2%}")
    print(f"Trades: {result.metrics['trade_count']:.0f}")
    if sensitivity is not None:
        print(f"Sensitivity scenarios: {len(sensitivity)}")
    if walk_forward is not None:
        print(f"Walk-forward windows: {len(walk_forward)}")
    if industry_exposure is not None:
        metrics = industry_exposure["metrics"]
        if metrics.get("status") == "ok":
            print(
                "Latest top industry: "
                f"{metrics.get('latest_top_industry')} ({float(metrics.get('latest_top_weight', 0.0)):.2%})"
            )
    if factor_ic is not None:
        metrics = factor_ic["metrics"]
        if metrics.get("status") == "ok":
            print(
                "Best factor IC: "
                f"{metrics.get('best_factor')} {metrics.get('best_horizon_days', 0):.0f}d "
                f"({float(metrics.get('best_mean_ic', 0.0)):.3f})"
            )
    if attribution is not None:
        bias = attribution["bias_diagnostics"]
        style = attribution["style_metrics"]
        print(f"Bias diagnostics: {bias.get('status', 'n/a')} score={float(bias.get('score', 0.0)):.1f}")
        print(
            "Dominant style: "
            f"{style.get('dominant_style', 'n/a')} "
            f"({float(style.get('dominant_abs_exposure', 0.0)):.2f} z)"
        )
    if benchmark is not None:
        metrics = benchmark["metrics"]
        print(f"Benchmark: {metrics.get('benchmark_name')} ({metrics.get('benchmark_code')})")
        print(f"Excess annualized return: {metrics.get('excess_annualized_return', 0):.2%}")
        print(f"Information ratio: {metrics.get('information_ratio', 0):.2f}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a strategy idea on sample, CSV, Investoday, AKShare, or Tushare data."
    )
    parser.add_argument("--source", choices=("sample", "csv", "investoday", "akshare", "tushare"), default="sample")
    parser.add_argument("--idea", default=DEFAULT_IDEA)
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    parser.add_argument(
        "--universe",
        choices=("custom", "investoday_top_amount", "investoday_pit_top_amount", "historical_stock_master_pit_top_amount"),
        default="custom",
        help="Use custom symbols, current realtime top amount, PIT liquidity membership, or an external historical stock master.",
    )
    parser.add_argument("--universe-size", type=int, default=100, help="Number of symbols for automatic universe.")
    parser.add_argument("--candidate-size", type=int, default=300, help="Candidate symbols for PIT liquidity universe.")
    parser.add_argument("--universe-lookback-days", type=int, default=20, help="PIT liquidity lookback window.")
    parser.add_argument("--universe-min-history-days", type=int, default=20, help="Minimum prior observations for PIT membership.")
    parser.add_argument("--universe-sort", default="dealMoney", help="Investoday realtime-ext sort field.")
    parser.add_argument("--historical-stock-master-path", help="CSV with full historical A-share stock master fields.")
    parser.add_argument(
        "--historical-stock-master-min-rows",
        type=int,
        default=3000,
        help="Minimum rows for treating an external stock master as full-market coverage.",
    )
    parser.add_argument(
        "--require-production-data",
        action="store_true",
        help="Fail fast unless the loaded dataset passes the production historical data gate.",
    )
    parser.add_argument("--include-bj", action="store_true", help="Include Beijing Stock Exchange symbols.")
    parser.add_argument("--benchmark-code", default="000300", help="Investoday index code for benchmark comparison.")
    parser.add_argument("--start", default="20210101")
    parser.add_argument("--end", default="20251231")
    parser.add_argument("--csv-path")
    parser.add_argument("--adjust", default="qfq", help="AKShare adjustment: qfq, hfq, or empty string.")
    parser.add_argument("--tushare-token")
    parser.add_argument("--sample-symbols", type=int, default=80)
    parser.add_argument("--page-size", type=int, default=500, help="Page size for paginated data APIs.")
    parser.add_argument("--api-batch-size", type=int, default=20, help="Stock batch size for heavy Investoday APIs.")
    parser.add_argument("--refresh-cache", action="store_true", help="Refresh cached Investoday API responses.")
    parser.add_argument("--no-cache", action="store_true", help="Disable Investoday API response cache.")
    parser.add_argument(
        "--no-limit-flags",
        action="store_true",
        help="Disable Investoday stock/limit-up-down enrichment.",
    )
    parser.add_argument(
        "--no-financials",
        action="store_true",
        help="Disable Investoday point-in-time profitability factor enrichment.",
    )
    parser.add_argument(
        "--no-stock-master",
        action="store_true",
        help="Disable Investoday stock/basic-info listing metadata and point-in-time listing filter.",
    )
    parser.add_argument("--skip-sensitivity", action="store_true", help="Skip parameter sensitivity scenarios.")
    parser.add_argument("--skip-walk-forward", action="store_true", help="Skip walk-forward validation windows.")
    parser.add_argument("--walk-forward-train-months", type=int, default=6, help="Train window length in months.")
    parser.add_argument("--walk-forward-test-months", type=int, default=3, help="Validation window length in months.")
    parser.add_argument("--walk-forward-step-months", type=int, default=3, help="Walk-forward step size in months.")
    parser.add_argument("--walk-forward-min-train-days", type=int, default=80, help="Minimum train trading days per window.")
    parser.add_argument("--walk-forward-min-test-days", type=int, default=20, help="Minimum test trading days per window.")
    parser.add_argument("--skip-industry-exposure", action="store_true", help="Skip industry exposure artifacts.")
    parser.add_argument("--skip-factor-ic", action="store_true", help="Skip factor IC diagnostics.")
    parser.add_argument("--skip-attribution", action="store_true", help="Skip contribution attribution and bias diagnostics.")
    parser.add_argument("--factor-ic-horizons", default="5,20,60", help="Forward-return horizons for IC, comma-separated.")
    parser.add_argument("--factor-ic-min-observations", type=int, default=20, help="Minimum cross-section size per IC.")
    parser.add_argument("--factor-ic-all-dates", action="store_true", help="Compute IC on all dates instead of rebalance dates.")
    parser.add_argument("--override-max-positions", type=int, help="Override parsed max positions.")
    parser.add_argument("--override-slippage-bps", type=float, help="Override slippage in basis points.")
    parser.add_argument("--override-min-amount", type=float, help="Override minimum daily amount filter.")
    parser.add_argument("--override-frequency", choices=("monthly", "weekly"), help="Override rebalance frequency.")
    return parser.parse_args()


def _load_data(args: argparse.Namespace) -> DataLoadResult:
    symbols = tuple(item.strip() for item in args.symbols.split(",") if item.strip())
    if args.source == "sample":
        return load_sample_panel(args.start, args.end, symbols=args.sample_symbols)
    if args.source == "csv":
        if not args.csv_path:
            raise DataSourceError("--csv-path is required when --source csv")
        return load_csv_panel(args.csv_path)
    if args.source == "akshare":
        return load_akshare_panel(symbols=symbols, start=args.start, end=args.end, adjust=args.adjust)
    if args.source == "investoday":
        cache_dir = None if args.no_cache else "cache/investoday_api"
        universe = None
        historical_stock_master = None
        historical_master_status = ""
        if args.universe == "historical_stock_master_pit_top_amount":
            if not args.historical_stock_master_path:
                raise DataSourceError("--historical-stock-master-path is required for historical_stock_master_pit_top_amount")
            historical_stock_master = load_stock_master_csv(args.historical_stock_master_path)
            validation = validate_stock_master_asset(
                historical_stock_master.master,
                start=args.start,
                end=args.end,
                min_rows=args.historical_stock_master_min_rows,
                include_bj=args.include_bj,
            )
            all_symbols = symbols_from_stock_master(
                historical_stock_master.master,
                start=args.start,
                end=args.end,
                include_bj=args.include_bj,
            )
            if not all_symbols:
                raise DataSourceError("Historical stock master produced no eligible symbols for the requested date range.")
            truncated = args.candidate_size > 0 and len(all_symbols) > args.candidate_size
            symbols = all_symbols[: args.candidate_size] if truncated else all_symbols
            historical_master_status = (
                "full_historical_stock_master"
                if validation.get("status") == "production_ready" and not truncated
                else "historical_stock_master_candidate_pool"
            )
            if truncated:
                historical_master_status += "+historical_stock_master_truncated"
        if args.universe in {"investoday_top_amount", "investoday_pit_top_amount"}:
            realtime_limit = args.universe_size
            if args.universe == "investoday_pit_top_amount":
                realtime_limit = max(args.candidate_size, args.universe_size)
            universe = load_investoday_realtime_universe(
                limit=realtime_limit,
                sort_column=args.universe_sort,
                order="desc",
                include_bj=args.include_bj,
                exclude_st=True,
                cache_dir=cache_dir,
                refresh_cache=args.refresh_cache,
            )
            symbols = universe.symbols
        loaded = load_investoday_panel(
            symbols=symbols,
            start=args.start,
            end=args.end,
            page_size=args.page_size,
            api_batch_size=args.api_batch_size,
            include_limit_flags=not args.no_limit_flags,
            include_financials=not args.no_financials,
            cache_dir=cache_dir,
            refresh_cache=args.refresh_cache,
        )
        if historical_stock_master is not None:
            stock_master_data = enrich_panel_with_stock_master(loaded.data, historical_stock_master.master)
            stock_master_filter = apply_point_in_time_stock_master_filter(stock_master_data)
            loaded = DataLoadResult(
                data=stock_master_filter.data,
                metadata=replace(
                    loaded.metadata,
                    source=f"{loaded.metadata.source}+{historical_stock_master.source}+{historical_master_status}+{stock_master_filter.source}",
                    symbols=symbols,
                    notes=loaded.metadata.notes
                    + historical_stock_master.notes
                    + (
                        f"Historical stock master rows: {len(historical_stock_master.master)}.",
                        f"Historical stock master minimum rows: {args.historical_stock_master_min_rows}.",
                        f"Historical stock master validation: {validation.get('status', 'n/a')}.",
                        f"Historical stock master validation hard failed: {validation.get('hard_failed', 0)}.",
                        f"Historical candidate symbols loaded: {len(symbols)} of {len(all_symbols)} eligible.",
                        f"Historical stock master snapshot sha256: {historical_stock_master.data_hash}",
                    )
                    + stock_master_filter.notes
                    + (f"Point-in-time stock master data sha256: {stock_master_filter.data_hash}",),
                    data_hash=stock_master_filter.data_hash,
                ),
                stock_master=historical_stock_master.master,
            )
            pit = apply_point_in_time_liquidity_universe(
                loaded.data,
                top_n=args.universe_size,
                lookback_days=args.universe_lookback_days,
                min_history_days=args.universe_min_history_days,
            )
            return DataLoadResult(
                data=pit.data,
                metadata=replace(
                    loaded.metadata,
                    source=f"{loaded.metadata.source}+{pit.source}",
                    notes=loaded.metadata.notes
                    + pit.notes
                    + (f"Point-in-time universe data sha256: {pit.data_hash}",),
                    data_hash=pit.data_hash,
                ),
                universe=pit.universe,
                stock_master=loaded.stock_master,
            )
        if not args.no_stock_master:
            stock_master = load_investoday_stock_master(
                symbols=symbols,
                api_batch_size=max(args.api_batch_size, 100),
                page_size=args.page_size,
                cache_dir=cache_dir,
                refresh_cache=args.refresh_cache,
            )
            stock_master_data = enrich_panel_with_stock_master(loaded.data, stock_master.master)
            stock_master_filter = apply_point_in_time_stock_master_filter(stock_master_data)
            loaded = DataLoadResult(
                data=stock_master_filter.data,
                metadata=replace(
                    loaded.metadata,
                    source=f"{loaded.metadata.source}+{stock_master.source}+{stock_master_filter.source}",
                    notes=loaded.metadata.notes
                    + stock_master.notes
                    + (f"Stock master snapshot sha256: {stock_master.data_hash}",)
                    + stock_master_filter.notes
                    + (f"Point-in-time stock master data sha256: {stock_master_filter.data_hash}",),
                    data_hash=stock_master_filter.data_hash,
                ),
                stock_master=stock_master.master,
            )
        if universe is None:
            return loaded
        enriched_data = enrich_panel_with_universe_classification(loaded.data, universe.universe)
        loaded = DataLoadResult(
            data=enriched_data,
            metadata=replace(
                loaded.metadata,
                notes=loaded.metadata.notes
                + ("Current universe classification fields are merged into the panel for exposure diagnostics.",),
                data_hash=dataframe_hash(enriched_data),
            ),
            stock_master=loaded.stock_master,
        )
        if args.universe == "investoday_pit_top_amount":
            pit = apply_point_in_time_liquidity_universe(
                loaded.data,
                top_n=args.universe_size,
                lookback_days=args.universe_lookback_days,
                min_history_days=args.universe_min_history_days,
            )
            metadata = replace(
                loaded.metadata,
                source=f"{loaded.metadata.source}+{universe.source}+{pit.source}",
                symbols=universe.symbols,
                notes=loaded.metadata.notes
                + universe.notes
                + (f"Candidate universe snapshot sha256: {universe.data_hash}",)
                + pit.notes
                + (f"Point-in-time universe data sha256: {pit.data_hash}",),
                data_hash=pit.data_hash,
            )
            return DataLoadResult(
                data=pit.data,
                metadata=metadata,
                universe=pit.universe,
                stock_master=loaded.stock_master,
            )
        metadata = replace(
            loaded.metadata,
            source=f"{loaded.metadata.source}+{universe.source}",
            symbols=universe.symbols,
            notes=loaded.metadata.notes
            + universe.notes
            + (f"Universe snapshot sha256: {universe.data_hash}",),
        )
        return DataLoadResult(
            data=loaded.data,
            metadata=metadata,
            universe=universe.universe,
            stock_master=loaded.stock_master,
        )
    if args.source == "tushare":
        return load_tushare_panel(
            symbols=symbols,
            start=args.start,
            end=args.end,
            token=args.tushare_token,
            include_basic=True,
        )
    raise DataSourceError(f"Unsupported source: {args.source}")


def _apply_strategy_overrides(spec: StrategySpec, args: argparse.Namespace) -> StrategySpec:
    portfolio = spec.portfolio
    costs = spec.costs
    universe = spec.universe
    rebalance = spec.rebalance
    description_parts = [spec.description]

    if args.override_max_positions is not None:
        portfolio = PortfolioSpec(
            initial_cash=portfolio.initial_cash,
            max_positions=args.override_max_positions,
            weighting=portfolio.weighting,
        )
        description_parts.append(f"max_positions={args.override_max_positions}")

    if args.override_slippage_bps is not None:
        costs = CostSpec(
            commission_rate=costs.commission_rate,
            stamp_tax_rate=costs.stamp_tax_rate,
            slippage_bps=args.override_slippage_bps,
        )
        description_parts.append(f"slippage_bps={args.override_slippage_bps:g}")

    if args.override_min_amount is not None:
        universe = UniverseSpec(
            exclude_st=universe.exclude_st,
            exclude_suspended=universe.exclude_suspended,
            min_amount=args.override_min_amount,
        )
        description_parts.append(f"min_amount={args.override_min_amount:g}")

    if args.override_frequency is not None:
        rebalance = RebalanceSpec(frequency=args.override_frequency)
        description_parts.append(f"frequency={args.override_frequency}")

    return replace(
        spec,
        description=" | ".join(part for part in description_parts if part),
        universe=universe,
        rebalance=rebalance,
        portfolio=portfolio,
        costs=costs,
    )


def _prepend_run_notes(
    markdown: str,
    idea: str,
    loaded: DataLoadResult,
    assumptions: tuple[str, ...],
    warnings: tuple[str, ...],
) -> str:
    lines = [
        "# Real Data Run",
        "",
        f"Source: {loaded.metadata.source}",
        f"Range: {loaded.metadata.start_date} to {loaded.metadata.end_date}",
        f"Symbol count: {len(loaded.metadata.symbols)}",
        f"Symbols: {', '.join(loaded.metadata.symbols[:20])}",
        f"Data snapshot sha256: {loaded.metadata.data_hash or 'n/a'}",
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


def _report_notes(loaded: DataLoadResult) -> tuple[str, ...]:
    if not loaded.metadata.data_hash:
        return loaded.metadata.notes
    return loaded.metadata.notes + (f"Data snapshot sha256: {loaded.metadata.data_hash}",)


def _metadata_payload(
    args: argparse.Namespace,
    idea: str,
    loaded: DataLoadResult,
    assumptions: tuple[str, ...],
    warnings: tuple[str, ...],
) -> dict[str, object]:
    return {
        "source": loaded.metadata.source,
        "symbols": loaded.metadata.symbols,
        "start_date": loaded.metadata.start_date,
        "end_date": loaded.metadata.end_date,
        "data_hash": loaded.metadata.data_hash,
        "idea": idea,
        "parser_assumptions": assumptions,
        "parser_warnings": warnings,
        "args": vars(args),
        "notes": loaded.metadata.notes,
    }


def _parse_int_tuple(value: str) -> tuple[int, ...]:
    parsed: list[int] = []
    for item in str(value).split(","):
        item = item.strip()
        if not item:
            continue
        parsed.append(int(item))
    return tuple(parsed)


def _render_artifact_index(paths: dict[str, Path]) -> str:
    lines = [
        "## Artifacts",
        "",
        "| Name | Path |",
        "|---|---|",
    ]
    for name, path in sorted(paths.items()):
        lines.append(f"| {name} | {path} |")
    lines.append("")
    return "\n".join(lines)


def _write_universe_artifact(output_dir: Path, universe: object) -> Path:
    path = output_dir / "universe.csv"
    universe.to_csv(path, index=False)
    return path


def _write_stock_master_artifact(output_dir: Path, stock_master: object) -> Path:
    path = output_dir / "stock_master.csv"
    stock_master.to_csv(path, index=False)
    return path


def _archived_artifact_paths(paths: dict[str, Path], archive_dir: Path) -> dict[str, Path]:
    return {name: archive_dir / Path(path).name for name, path in paths.items()}


def _append_report_section(path: Path, section: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n\n")
        handle.write(section)


def _remove_stale_optional_artifacts(output_dir: Path) -> None:
    for filename in (
        "sensitivity.csv",
        "universe.csv",
        "benchmark_comparison.csv",
        "benchmark_metrics.json",
        "stock_master.csv",
        "walk_forward.csv",
        "factor_ic.csv",
        "factor_ic_summary.csv",
        "factor_ic_metrics.json",
        "industry_exposure_daily.csv",
        "industry_exposure_latest.csv",
        "industry_exposure_metrics.json",
        "style_exposure.csv",
        "style_metrics.json",
        "stock_contribution.csv",
        "industry_contribution.csv",
        "contribution_metrics.json",
        "bias_diagnostics.json",
        "attribution_summary.json",
    ):
        path = output_dir / filename
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()

