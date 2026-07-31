from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sys
import time

import pandas as pd

from a_share_quant_agent.data_sources import (
    DataSourceError,
    _date_with_dash,
    _investoday_fetch_paginated_batched,
    _normalize_symbol,
    _symbol_to_code,
    dataframe_hash,
    load_stock_master_csv,
    symbols_from_stock_master,
)
from a_share_quant_agent.historical_assets import MARGIN_TRADE_FIELDS, discover_data_assets, write_asset_inventory
from a_share_quant_agent.vendor_assets import validate_production_asset_bundle, write_production_asset_validation_artifacts


ROOT = Path(__file__).resolve().parents[1]
EXTRACT_DIR = "investoday_margin_trades"
RUNS_DIR = "runs"
ENDPOINT = "stock/margin-trades"
OUTPUT_COLUMNS = ("date", "symbol", "stockCode", "stockName", *MARGIN_TRADE_FIELDS, "marginTradeSource")


def main() -> int:
    args = _parse_args()
    try:
        result = extract_investoday_margin_trades(
            reports_root=args.reports_root,
            asset_root=args.asset_root,
            start=args.start,
            end=args.end,
            stock_master_path=args.stock_master_path,
            symbols=args.symbols,
            symbols_file=args.symbols_file,
            max_symbols=args.max_symbols,
            page_size=args.page_size,
            api_batch_size=args.api_batch_size,
            cache_dir=None if args.no_cache else args.cache_dir,
            refresh_cache=args.refresh_cache,
            resume=not args.no_resume,
            parallel_workers=args.parallel_workers,
            execute=args.execute,
            min_stock_master_rows=args.historical_stock_master_min_rows,
            min_delisted_rows=args.min_delisted_rows,
            include_bj=args.include_bj,
            max_retries=args.max_retries,
            retry_sleep_seconds=args.retry_sleep_seconds,
            extract_id=args.extract_id,
        )
    except DataSourceError as exc:
        print(f"Data source error: {exc}", file=sys.stderr)
        return 2

    paths = result.get("paths", {}) if isinstance(result.get("paths"), dict) else {}
    coverage = result.get("coverage", {}) if isinstance(result.get("coverage"), dict) else {}
    print(f"Extract ID: {result.get('extract_id')}")
    print(f"Status: {result.get('status')}")
    print(f"Decision: {result.get('decision')}")
    print(f"Symbols requested: {result.get('symbols_requested', 0)}")
    print(f"Rows: {result.get('rows', 0)}")
    print(f"Symbols covered: {result.get('symbols_covered', 0)}")
    print(f"Margin balance coverage: {float(coverage.get('marginBalance', 0.0) or 0.0):.2%}")
    print(f"Margin buy/repay coverage: {float(coverage.get('marginBuyAmount', 0.0) or 0.0):.2%} / {float(coverage.get('marginRepayAmount', 0.0) or 0.0):.2%}")
    print(f"Duplicate keys: {result.get('duplicate_key_count', 0)}")
    print(f"Production ready: {result.get('production_ready', False)}")
    print(f"Output CSV: {paths.get('output_csv', '')}")
    print(f"Report: {paths.get('latest_report', paths.get('report', ''))}")
    blockers = result.get("blockers") if isinstance(result.get("blockers"), list) else []
    if blockers:
        print("Notes:")
        for blocker in blockers[:8]:
            print(f"- {blocker}")
    return 0 if result.get("status") in {"dry_run_ready", "executed_ready"} else 3


def extract_investoday_margin_trades(
    *,
    reports_root: str | Path,
    asset_root: str | Path,
    start: str = "20210101",
    end: str = "20260724",
    stock_master_path: str | Path | None = None,
    symbols: str = "",
    symbols_file: str | Path | None = None,
    max_symbols: int | None = None,
    page_size: int = 500,
    api_batch_size: int = 100,
    cache_dir: str | Path | None = "cache/investoday_api",
    refresh_cache: bool = False,
    resume: bool = True,
    parallel_workers: int = 1,
    execute: bool = False,
    min_stock_master_rows: int = 3000,
    min_delisted_rows: int = 50,
    include_bj: bool = False,
    max_retries: int = 1,
    retry_sleep_seconds: float = 1.0,
    extract_id: str | None = None,
) -> dict[str, object]:
    asset_root_path = Path(asset_root)
    reports = Path(reports_root)
    extract_id = extract_id or _make_extract_id()
    run_dir = reports / EXTRACT_DIR / RUNS_DIR / extract_id
    shard_dir = run_dir / "margin_trade_shards"
    staging_root = run_dir / "staging_assets"
    manifest_dir = run_dir / "manifests"
    shard_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    selected_symbols = _load_symbols(
        asset_root_path=asset_root_path,
        stock_master_path=stock_master_path,
        symbols=symbols,
        symbols_file=symbols_file,
        start=start,
        end=end,
        include_bj=include_bj,
    )
    if max_symbols is not None:
        selected_symbols = selected_symbols[: max(0, int(max_symbols))]
    if not selected_symbols:
        raise DataSourceError("No symbols were selected for Investoday margin-trade extraction.")
    if execute and (symbols.strip() or symbols_file or max_symbols is not None):
        raise DataSourceError("--execute must run on the full eligible production universe; remove symbol filters.")

    result: dict[str, object] = {
        "schema_version": 1,
        "extract_id": extract_id,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "running",
        "decision": "extract_strict_lagged_investoday_margin_trades",
        "endpoint": ENDPOINT,
        "asset_root": str(asset_root_path),
        "reports_root": str(reports),
        "run_dir": str(run_dir),
        "start_date": start,
        "end_date": end,
        "execute_requested": bool(execute),
        "symbols_requested": len(selected_symbols),
        "options": {
            "page_size": int(page_size),
            "api_batch_size": int(api_batch_size),
            "cache_dir": str(cache_dir) if cache_dir is not None else "",
            "refresh_cache": bool(refresh_cache),
            "resume": bool(resume),
            "parallel_workers": int(parallel_workers),
            "max_retries": int(max_retries),
        },
    }

    raw, errors = _fetch_margin_trade_records(
        selected_symbols,
        start=start,
        end=end,
        shard_dir=shard_dir,
        page_size=page_size,
        api_batch_size=api_batch_size,
        cache_dir=cache_dir,
        refresh_cache=refresh_cache,
        resume=resume,
        parallel_workers=parallel_workers,
        max_retries=max_retries,
        retry_sleep_seconds=retry_sleep_seconds,
    )
    if errors:
        result["errors"] = errors
        result["status"] = "blocked"
        result["decision"] = "retry_failed_investoday_margin_trade_batches"
        result["blockers"] = [f"Investoday margin-trade extraction had {len(errors)} failed batches."]
        paths = _write_extract_artifacts(reports, result)
        result["paths"] = {name: str(path) for name, path in paths.items()}
        _write_extract_artifacts(reports, result)
        return result

    trades = _normalize_margin_trade_records(raw, end=end)
    if trades.empty:
        raise DataSourceError("Investoday margin-trade endpoint returned no usable records.")

    output_path = asset_root_path / "market" / "margin_trades.csv" if execute else run_dir / "margin_trades.csv"
    if execute:
        result["backup"] = _backup_existing_margin_trade_asset(asset_root_path, extract_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    trades.to_csv(output_path, index=False)

    validation_root = asset_root_path if execute else _build_staging_validation_root(
        staging_root=staging_root,
        asset_root=asset_root_path,
        margin_path=output_path,
    )
    validation = validate_production_asset_bundle(
        validation_root,
        start=start,
        end=end,
        min_stock_master_rows=min_stock_master_rows,
        min_delisted_rows=min_delisted_rows,
        include_bj=include_bj,
    )
    validation_output_dir = asset_root_path / "manifests" / "production_import" if execute else manifest_dir
    validation_paths = write_production_asset_validation_artifacts(validation_output_dir, validation)
    inventory = discover_data_assets(asset_root_path if execute else validation_root, start=start, end=end)
    inventory_paths = write_asset_inventory(validation_output_dir, inventory)

    margin_metrics = validation.get("margin_trade_metrics") if isinstance(validation.get("margin_trade_metrics"), dict) else {}
    field_coverage = margin_metrics.get("field_coverage") if isinstance(margin_metrics.get("field_coverage"), dict) else {}
    status = "executed_ready" if execute and validation.get("production_data_ready") else "dry_run_ready"
    if not validation.get("production_data_ready"):
        status = "blocked"
    result.update(
        {
            "status": status,
            "decision": "run_margin_trade_strategy_factory" if execute else "review_dry_run_then_execute",
            "rows": int(len(trades)),
            "symbols_covered": int(trades["symbol"].nunique()),
            "raw_rows": int(len(raw)),
            "raw_columns": [str(column) for column in raw.columns],
            "data_hash": dataframe_hash(trades),
            "output_csv": str(output_path),
            "production_ready": bool(validation.get("production_data_ready", False)),
            "validation": validation,
            "inventory": inventory,
            "coverage": {
                "marginBalance": float(field_coverage.get("marginBalance", 0.0) or 0.0),
                "marginBuyAmount": float(field_coverage.get("marginBuyAmount", 0.0) or 0.0),
                "marginRepayAmount": float(field_coverage.get("marginRepayAmount", 0.0) or 0.0),
                "shortBalanceAmount": float(field_coverage.get("shortBalanceAmount", 0.0) or 0.0),
                "marginShortBalance": float(field_coverage.get("marginShortBalance", 0.0) or 0.0),
            },
            "duplicate_key_count": int(margin_metrics.get("duplicate_key_count", 0) or 0),
            "blockers": [
                "Dry-run output is not a production asset until rerun with --execute on the full eligible universe."
            ]
            if not execute
            else [],
        }
    )
    paths = _write_extract_artifacts(reports, result)
    result["paths"] = {
        "output_csv": str(output_path),
        **{name: str(path) for name, path in validation_paths.items()},
        **{name: str(path) for name, path in inventory_paths.items()},
        **{name: str(path) for name, path in paths.items()},
    }
    _write_extract_artifacts(reports, result)
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract Investoday margin trades into canonical margin_trades.csv.")
    parser.add_argument("--reports-root", default=str(ROOT / "reports"))
    parser.add_argument("--asset-root", default=str(ROOT / "data_assets"))
    parser.add_argument("--start", default="20210101")
    parser.add_argument("--end", default="20260724")
    parser.add_argument("--stock-master-path")
    parser.add_argument("--symbols", default="", help="Comma-separated symbol override, e.g. 600000.SH,000001.SZ.")
    parser.add_argument("--symbols-file", help="Optional newline-delimited symbols file.")
    parser.add_argument("--max-symbols", type=int)
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--api-batch-size", type=int, default=100)
    parser.add_argument("--cache-dir", default="cache/investoday_api")
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--parallel-workers", type=int, default=1, help="Fetch independent symbol batches concurrently.")
    parser.add_argument("--execute", action="store_true", help="Write data_assets/market/margin_trades.csv.")
    parser.add_argument("--historical-stock-master-min-rows", type=int, default=3000)
    parser.add_argument("--min-delisted-rows", type=int, default=50)
    parser.add_argument("--include-bj", action="store_true")
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--retry-sleep-seconds", type=float, default=1.0)
    parser.add_argument("--extract-id")
    return parser.parse_args()


def _fetch_margin_trade_records(
    symbols: tuple[str, ...],
    *,
    start: str,
    end: str,
    shard_dir: Path,
    page_size: int,
    api_batch_size: int,
    cache_dir: str | Path | None,
    refresh_cache: bool,
    resume: bool,
    parallel_workers: int,
    max_retries: int,
    retry_sleep_seconds: float,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    errors: list[dict[str, object]] = []
    batches = list(enumerate(_symbol_batches(symbols, api_batch_size), start=1))
    shard_paths: dict[int, Path] = {}
    workers = max(1, int(parallel_workers))
    total_batches = len(batches)
    started_at = time.perf_counter()

    if workers == 1:
        for index, batch in batches:
            batch_index, path, error = _fetch_margin_trade_batch(
                index,
                batch,
                start=start,
                end=end,
                shard_dir=shard_dir,
                page_size=page_size,
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
                resume=resume,
                max_retries=max_retries,
                retry_sleep_seconds=retry_sleep_seconds,
            )
            if error:
                errors.append(error)
            elif path is not None:
                shard_paths[batch_index] = path
            _print_batch_progress(batch_index, total_batches, path, started_at=started_at, error=error)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _fetch_margin_trade_batch,
                    index,
                    batch,
                    start=start,
                    end=end,
                    shard_dir=shard_dir,
                    page_size=page_size,
                    cache_dir=cache_dir,
                    refresh_cache=refresh_cache,
                    resume=resume,
                    max_retries=max_retries,
                    retry_sleep_seconds=retry_sleep_seconds,
                ): index
                for index, batch in batches
            }
            for future in as_completed(futures):
                batch_index, path, error = future.result()
                if error:
                    errors.append(error)
                elif path is not None:
                    shard_paths[batch_index] = path
                _print_batch_progress(batch_index, total_batches, path, started_at=started_at, error=error)

    if errors:
        return pd.DataFrame(), errors
    frames = [pd.read_csv(shard_paths[index]) for index in sorted(shard_paths)]
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), errors


def _fetch_margin_trade_batch(
    index: int,
    batch: tuple[str, ...],
    *,
    start: str,
    end: str,
    shard_dir: Path,
    page_size: int,
    cache_dir: str | Path | None,
    refresh_cache: bool,
    resume: bool,
    max_retries: int,
    retry_sleep_seconds: float,
) -> tuple[int, Path | None, dict[str, object] | None]:
    shard_path = shard_dir / f"batch_{index:04d}.csv"
    if resume and shard_path.exists() and not refresh_cache:
        return index, shard_path, None
    try:
        records = _with_retries(
            lambda batch=batch: _investoday_fetch_paginated_batched(
                ENDPOINT,
                {
                    "stockCodes": [_symbol_to_code(symbol) for symbol in batch],
                    "beginDate": _date_with_dash(start),
                    "endDate": _date_with_dash(end),
                },
                batch_key="stockCodes",
                batch_size=len(batch),
                page_size=page_size,
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
            ),
            max_retries=max_retries,
            retry_sleep_seconds=retry_sleep_seconds,
        )
    except Exception as exc:
        return index, None, {"batch": index, "symbols": ",".join(batch[:5]), "error": str(exc)}
    shard = pd.DataFrame(records)
    if shard.empty:
        shard = pd.DataFrame(columns=("stockCode", "date"))
    shard.to_csv(shard_path, index=False)
    return index, shard_path, None


def _print_batch_progress(
    batch_index: int,
    total_batches: int,
    path: Path | None,
    *,
    started_at: float,
    error: dict[str, object] | None,
) -> None:
    elapsed = time.perf_counter() - started_at
    if error:
        status = f"error={error.get('error', '')}"
    elif path is not None and path.exists():
        status = f"rows={_csv_data_rows(path)} size_mb={path.stat().st_size / 1024 / 1024:.1f}"
    else:
        status = "empty"
    print(
        f"[margin-trades] batch {batch_index}/{total_batches} {status} elapsed={elapsed:.1f}s",
        file=sys.stderr,
        flush=True,
    )


def _csv_data_rows(path: Path) -> int:
    try:
        with path.open("rb") as handle:
            lines = sum(1 for _ in handle)
    except OSError:
        return 0
    return max(0, lines - 1)


def _normalize_margin_trade_records(raw: pd.DataFrame, *, end: str) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    frame = raw.copy()
    if "stockCode" not in frame and "symbol" not in frame:
        raise DataSourceError("Investoday margin-trade payload is missing stockCode/symbol.")
    if "date" not in frame:
        raise DataSourceError("Investoday margin-trade payload is missing date.")
    if "symbol" in frame:
        frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    else:
        frame["symbol"] = frame["stockCode"].map(_normalize_symbol)
    frame["stockCode"] = frame["symbol"].str.split(".", n=1).str[0]
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    for column in MARGIN_TRADE_FIELDS:
        if column not in frame:
            frame[column] = pd.NA
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "stockName" not in frame:
        frame["stockName"] = ""
    frame["marginTradeSource"] = f"investoday:{ENDPOINT}"
    frame = frame[(frame["date"].notna()) & (frame["date"] <= pd.Timestamp(_date_with_dash(end)))]
    frame = frame.dropna(subset=["date", "symbol"])
    if frame.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    frame = frame[[column for column in OUTPUT_COLUMNS if column in frame.columns]]
    frame.sort_values(["symbol", "date"], inplace=True)
    frame = frame.drop_duplicates(["date", "symbol"], keep="last")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return frame.sort_values(["date", "symbol"]).reset_index(drop=True)


def _load_symbols(
    *,
    asset_root_path: Path,
    stock_master_path: str | Path | None,
    symbols: str,
    symbols_file: str | Path | None,
    start: str,
    end: str,
    include_bj: bool,
) -> tuple[str, ...]:
    explicit = [item.strip() for item in symbols.split(",") if item.strip()]
    if symbols_file:
        explicit.extend(item.strip() for item in Path(symbols_file).read_text(encoding="utf-8").splitlines() if item.strip())
    if explicit:
        return tuple(dict.fromkeys(_normalize_symbol(symbol) for symbol in explicit if _normalize_symbol(symbol)))
    master_path = Path(stock_master_path) if stock_master_path else asset_root_path / "stock_master" / "historical_stock_master.csv"
    master = load_stock_master_csv(master_path)
    return symbols_from_stock_master(master.master, start=start, end=end, include_bj=include_bj)


def _symbol_batches(symbols: tuple[str, ...], batch_size: int) -> list[tuple[str, ...]]:
    if batch_size < 1:
        raise DataSourceError("Investoday api_batch_size must be positive.")
    return [symbols[index : index + batch_size] for index in range(0, len(symbols), batch_size)]


def _build_staging_validation_root(*, staging_root: Path, asset_root: Path, margin_path: Path) -> Path:
    _link_or_copy(asset_root / "stock_master", staging_root / "stock_master")
    _link_or_copy(asset_root / "market" / "daily_quotes.csv", staging_root / "market" / "daily_quotes.csv")
    _link_or_copy(asset_root / "market" / "daily_fund_flows.csv", staging_root / "market" / "daily_fund_flows.csv")
    _link_or_copy(asset_root / "fundamentals", staging_root / "fundamentals")
    _link_or_copy(asset_root / "index", staging_root / "index")
    _link_or_copy(asset_root / "industry", staging_root / "industry")
    _link_or_copy(asset_root / "events", staging_root / "events")
    margin_target = staging_root / "market" / "margin_trades.csv"
    margin_target.parent.mkdir(parents=True, exist_ok=True)
    if margin_target.exists() or margin_target.is_symlink():
        margin_target.unlink()
    _link_or_copy(margin_path, margin_target)
    return staging_root


def _backup_existing_margin_trade_asset(asset_root: Path, extract_id: str) -> dict[str, object]:
    source = asset_root / "market" / "margin_trades.csv"
    if not source.exists():
        return {"status": "skipped", "reason": "No existing margin_trades.csv to back up."}
    backup_root = asset_root / "backups" / extract_id
    backup_path = backup_root / "market" / "margin_trades.csv"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, backup_path)
    return {"status": "completed", "source": str(source), "backup_path": str(backup_path)}


def _link_or_copy(source: Path, target: Path) -> None:
    if not source.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()
    try:
        os.symlink(source.resolve(), target)
    except OSError:
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)


def _write_extract_artifacts(reports_root: Path, result: dict[str, object]) -> dict[str, Path]:
    extract_dir = reports_root / EXTRACT_DIR
    run_dir = Path(str(result.get("run_dir", extract_dir / RUNS_DIR / str(result.get("extract_id", "unknown")))))
    extract_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    json_path = run_dir / "margin_trade_extract.json"
    md_path = run_dir / "margin_trade_extract.md"
    latest_json = extract_dir / "latest_margin_trades.json"
    latest_md = extract_dir / "latest_margin_trades.md"
    payload = json.dumps(_json_ready(result), ensure_ascii=False, indent=2, sort_keys=True)
    markdown = _render_extract_markdown(result)
    json_path.write_text(payload, encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    latest_json.write_text(payload, encoding="utf-8")
    latest_md.write_text(markdown, encoding="utf-8")
    return {"extract": json_path, "report": md_path, "latest_json": latest_json, "latest_report": latest_md}


def _render_extract_markdown(result: dict[str, object]) -> str:
    paths = result.get("paths") if isinstance(result.get("paths"), dict) else {}
    coverage = result.get("coverage") if isinstance(result.get("coverage"), dict) else {}
    lines = [
        "## Investoday Margin Trades",
        "",
        f"Status: `{result.get('status', 'n/a')}`",
        f"Decision: `{result.get('decision', 'n/a')}`",
        f"Extract ID: `{result.get('extract_id', '')}`",
        f"Endpoint: `{result.get('endpoint', ENDPOINT)}`",
        f"Range: `{result.get('start_date', '')}` to `{result.get('end_date', '')}`",
        f"Execute requested: {'yes' if result.get('execute_requested') else 'no'}",
        "",
        "### Summary",
        "",
        f"- Symbols requested: {result.get('symbols_requested', 0)}",
        f"- Symbols covered: {result.get('symbols_covered', 0)}",
        f"- Rows: {result.get('rows', 0)}",
        f"- Margin balance coverage: {_format_rate(coverage.get('marginBalance', 0.0))}",
        f"- Margin buy / repay coverage: {_format_rate(coverage.get('marginBuyAmount', 0.0))} / {_format_rate(coverage.get('marginRepayAmount', 0.0))}",
        f"- Short balance amount coverage: {_format_rate(coverage.get('shortBalanceAmount', 0.0))}",
        f"- Duplicate keys: {result.get('duplicate_key_count', 0)}",
        f"- Production ready: {'yes' if result.get('production_ready') else 'no'}",
        "",
        "### API Integration",
        "",
        "| Endpoint | Method | Parameters | Runtime shape |",
        "|---|---|---|---|",
        (
            f"| `{ENDPOINT}` | POST | `stockCodes`, `beginDate`, `endDate`, `pageNum`, `pageSize` | "
            "`list[dict]` with `stockCode`, `date`, `marginBalance`, `marginBuyAmount`, `marginRepayAmount`, `shortBalanceAmount` |"
        ),
        "",
        "### PIT Usage",
        "",
        "- Strategy date T uses only the latest margin-trade row strictly before T.",
        "- Same-day margin rows are excluded by the production loader to avoid after-close leakage.",
        "- Amount and balance fields are transformed into turnover-relative ratios and cross-sectional guard scores.",
        "",
        "### Paths",
        "",
        "| Name | Path |",
        "|---|---|",
    ]
    for name, path in sorted(paths.items()):
        lines.append(f"| {_md(str(name))} | `{_md(str(path))}` |")
    blockers = result.get("blockers") if isinstance(result.get("blockers"), list) else []
    if blockers:
        lines.extend(["", "### Notes", ""])
        lines.extend(f"- {item}" for item in blockers[:12])
    lines.append("")
    return "\n".join(lines)


def _with_retries(fn, *, max_retries: int, retry_sleep_seconds: float):
    attempts = max(0, int(max_retries)) + 1
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(max(0.0, retry_sleep_seconds))
    if last_exc is not None:
        raise last_exc
    raise DataSourceError("Retry wrapper failed without an exception.")


def _make_extract_id(now: datetime | None = None) -> str:
    stamp = (now or datetime.now()).astimezone().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    return f"investoday_margin_trades_{stamp}"


def _format_rate(value: object) -> str:
    try:
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return "n/a"


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _json_ready(value: object) -> object:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


if __name__ == "__main__":
    raise SystemExit(main())
