from __future__ import annotations

import argparse
from pathlib import Path

from a_share_quant_agent.investoday_full_universe import extract_investoday_full_universe


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    args = _parse_args()
    result = extract_investoday_full_universe(
        reports_root=args.reports_root,
        asset_root=args.asset_root,
        start=args.start,
        end=args.end,
        stock_master_source=args.stock_master_source,
        stock_all_endpoint=args.stock_all_endpoint,
        include_chain_sec_basic_info=not args.no_chain_sec_basic_info,
        stock_master_path=args.stock_master_path,
        symbols=_parse_symbols(args.symbols),
        symbols_file=args.symbols_file,
        daily_quotes_path=args.daily_quotes_path,
        page_size=args.page_size,
        quote_batch_size=args.quote_batch_size,
        max_symbols=args.max_symbols,
        max_quote_batches=args.max_quote_batches,
        cache_dir=None if args.no_cache else args.cache_dir,
        refresh_cache=args.refresh_cache,
        resume=not args.no_resume,
        max_retries=args.max_retries,
        retry_sleep_seconds=args.retry_sleep_seconds,
        continue_on_quote_error=args.continue_on_quote_error,
        stock_master_only=args.stock_master_only,
        run_import_dry_run=args.run_import_dry_run,
        min_stock_master_rows=args.historical_stock_master_min_rows,
        min_delisted_rows=args.min_delisted_rows,
        include_bj=args.include_bj,
        extract_id=args.extract_id,
    )
    paths = result.get("paths", {}) if isinstance(result.get("paths"), dict) else {}
    stock = result.get("stock_master", {}) if isinstance(result.get("stock_master"), dict) else {}
    quotes = result.get("quotes", {}) if isinstance(result.get("quotes"), dict) else {}
    validation = result.get("validation", {}) if isinstance(result.get("validation"), dict) else {}
    print(f"Extract ID: {result.get('extract_id')}")
    print(f"Status: {result.get('status')}")
    print(f"Decision: {result.get('decision')}")
    print(f"Stock master: {stock.get('status')} rows={stock.get('rows', 0)} symbols={stock.get('symbols', 0)}")
    print(f"Quotes: {quotes.get('status')} rows={quotes.get('rows', 0)} symbols={quotes.get('symbols', 0)}")
    print(f"Production ready: {validation.get('production_data_ready', False)}")
    print(f"Report: {paths.get('extract_manifest_report', paths.get('api_integration', ''))}")
    if paths.get("generated_mapping"):
        print(f"Generated mapping: {paths.get('generated_mapping')}")
    blockers = result.get("blockers") if isinstance(result.get("blockers"), list) else []
    if blockers:
        print("Blockers:")
        for blocker in blockers[:8]:
            print(f"- {blocker}")
    return 0 if validation.get("production_data_ready") else 3


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract Investoday full-universe A-share stock master and quotes into staging assets.")
    parser.add_argument("--reports-root", default=str(ROOT / "reports"))
    parser.add_argument("--asset-root", default=str(ROOT / "data_assets"))
    parser.add_argument("--start", default="20210101")
    parser.add_argument("--end", default="20260724")
    parser.add_argument("--stock-master-source", choices=("stock_all", "csv", "symbols", "stock_basic_info"), default="stock_all")
    parser.add_argument("--stock-all-endpoint", default="stock/all")
    parser.add_argument("--no-chain-sec-basic-info", action="store_true")
    parser.add_argument("--stock-master-path")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--symbols-file")
    parser.add_argument("--daily-quotes-path")
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--quote-batch-size", type=int, default=50)
    parser.add_argument("--max-symbols", type=int)
    parser.add_argument("--max-quote-batches", type=int)
    parser.add_argument("--cache-dir", default="cache/investoday_api")
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--retry-sleep-seconds", type=float, default=1.0)
    parser.add_argument("--continue-on-quote-error", action="store_true")
    parser.add_argument("--stock-master-only", action="store_true")
    parser.add_argument("--run-import-dry-run", action="store_true")
    parser.add_argument("--historical-stock-master-min-rows", type=int, default=3000)
    parser.add_argument("--min-delisted-rows", type=int, default=50)
    parser.add_argument("--include-bj", action="store_true")
    parser.add_argument("--extract-id", help="Reuse a run directory so quote shards can resume after interruption.")
    return parser.parse_args()


def _parse_symbols(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


if __name__ == "__main__":
    raise SystemExit(main())
