from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Iterable

import numpy as np
import pandas as pd

from .spec import StrategySpec


class DataSourceError(RuntimeError):
    """Raised when a market data source cannot produce a valid backtest panel."""


@dataclass(frozen=True)
class DataSourceMetadata:
    source: str
    symbols: tuple[str, ...]
    start_date: str
    end_date: str
    notes: tuple[str, ...]
    data_hash: str = ""


@dataclass(frozen=True)
class DataLoadResult:
    data: pd.DataFrame
    metadata: DataSourceMetadata
    universe: pd.DataFrame | None = None
    stock_master: pd.DataFrame | None = None


@dataclass(frozen=True)
class UniverseDiscoveryResult:
    symbols: tuple[str, ...]
    universe: pd.DataFrame
    source: str
    notes: tuple[str, ...]
    data_hash: str


@dataclass(frozen=True)
class PointInTimeUniverseResult:
    data: pd.DataFrame
    universe: pd.DataFrame
    source: str
    notes: tuple[str, ...]
    data_hash: str


@dataclass(frozen=True)
class StockMasterResult:
    master: pd.DataFrame
    source: str
    notes: tuple[str, ...]
    data_hash: str


@dataclass(frozen=True)
class PointInTimeStockMasterResult:
    data: pd.DataFrame
    source: str
    notes: tuple[str, ...]
    data_hash: str


@dataclass(frozen=True)
class BenchmarkLoadResult:
    data: pd.DataFrame
    metadata: DataSourceMetadata


STANDARD_STOCK_MASTER_COLUMNS = (
    "symbol",
    "stockCode",
    "exchangeCode",
    "stockName",
    "stockType",
    "listDate",
    "delistDate",
    "listStatus",
)


def dataframe_hash(data: pd.DataFrame) -> str:
    return _dataframe_hash(data)


def load_sample_panel(start: str, end: str, symbols: int = 80) -> DataLoadResult:
    from .sample_data import make_sample_panel

    data = make_sample_panel(start=_date_with_dash(start), end=_date_with_dash(end), symbols=symbols)
    return DataLoadResult(
        data=data,
        metadata=DataSourceMetadata(
            source="sample",
            symbols=tuple(sorted(data["symbol"].unique())),
            start_date=start,
            end_date=end,
            notes=("Deterministic sample data, not real market data.",),
            data_hash=_dataframe_hash(data),
        ),
    )


def load_csv_panel(path: str | Path) -> DataLoadResult:
    csv_path = Path(path)
    if not csv_path.exists():
        raise DataSourceError(f"CSV file does not exist: {csv_path}")
    data = pd.read_csv(csv_path)
    data = prepare_backtest_panel(data)
    return DataLoadResult(
        data=data,
        metadata=DataSourceMetadata(
            source="csv",
            symbols=tuple(sorted(data["symbol"].unique())),
            start_date=str(data["date"].min().date()),
            end_date=str(data["date"].max().date()),
            notes=(f"Loaded from CSV: {csv_path}",),
            data_hash=_dataframe_hash(data),
        ),
    )


def load_stock_master_csv(path: str | Path, *, source: str = "historical_stock_master_csv") -> StockMasterResult:
    csv_path = Path(path)
    if not csv_path.exists():
        raise DataSourceError(f"Historical stock master CSV does not exist: {csv_path}")
    raw = pd.read_csv(csv_path)
    master = _normalize_external_stock_master(raw)
    if master.empty:
        raise DataSourceError(f"Historical stock master CSV had no usable rows: {csv_path}")
    notes = (
        f"Loaded historical stock master CSV: {csv_path}.",
        "CSV stock master is treated as the candidate source; listDate/delistDate/stockType are used for PIT eligibility when present.",
        "For full survivorship-bias closure, this file must include current and delisted A-share securities for the tested market.",
    )
    return StockMasterResult(
        master=master,
        source=source,
        notes=notes,
        data_hash=_dataframe_hash(master),
    )


def symbols_from_stock_master(
    stock_master: pd.DataFrame,
    *,
    start: str | None = None,
    end: str | None = None,
    include_bj: bool = False,
) -> tuple[str, ...]:
    if stock_master.empty or "symbol" not in stock_master:
        return ()
    frame = stock_master.copy()
    frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    eligible = pd.Series(True, index=frame.index, dtype=bool)
    if not include_bj:
        eligible &= ~frame["symbol"].str.endswith(".BJ")
    eligible &= ~_b_share_symbol_mask(frame["symbol"])
    if "stockType" in frame:
        stock_type = frame["stockType"].astype(str).str.upper()
        eligible &= frame["stockType"].isna() | stock_type.isin({"A股".upper(), "A", "ASHARE", "A-SHARE", "", "NAN", "NONE"})
    if "listDate" in frame and end:
        list_dates = pd.to_datetime(frame["listDate"], errors="coerce")
        eligible &= list_dates.isna() | (list_dates <= pd.Timestamp(_date_with_dash(end)))
    if "delistDate" in frame and start:
        delist_dates = pd.to_datetime(frame["delistDate"], errors="coerce")
        eligible &= delist_dates.isna() | (delist_dates >= pd.Timestamp(_date_with_dash(start)))
    symbols = sorted(frame.loc[eligible, "symbol"].dropna().astype(str).unique())
    return tuple(symbols)


def validate_stock_master_asset(
    stock_master: pd.DataFrame,
    *,
    start: str | None = None,
    end: str | None = None,
    min_rows: int = 3000,
    min_unique_symbols: int | None = None,
    min_delisted_rows: int = 50,
    min_valid_symbol_rate: float = 0.98,
    min_list_date_coverage: float = 0.95,
    include_bj: bool = False,
) -> dict[str, object]:
    """Validate whether a normalized stock master is suitable for serious historical research."""

    min_unique_symbols = min_unique_symbols or min_rows
    frame = stock_master.copy()
    rows = int(len(frame))
    required_columns = list(STANDARD_STOCK_MASTER_COLUMNS)
    missing_columns = [column for column in required_columns if column not in frame.columns]

    if "symbol" in frame:
        symbols = frame["symbol"].map(_normalize_symbol)
    else:
        symbols = pd.Series("", index=frame.index, dtype=object)
    valid_symbol = symbols.astype(str).str.match(r"^\d{6}\.(SH|SZ|BJ)$", na=False)
    valid_symbol_rate = float(valid_symbol.mean()) if rows else 0.0
    unique_symbols = int(symbols[valid_symbol].nunique()) if rows else 0
    duplicate_symbols = int(symbols[symbols.astype(str) != ""].duplicated().sum()) if rows else 0

    exchange_counts: dict[str, int] = {}
    if rows:
        suffixes = symbols.astype(str).str.split(".", n=1).str[1]
        exchange_counts = {str(key): int(value) for key, value in suffixes.value_counts(dropna=True).sort_index().items()}

    list_dates = pd.to_datetime(frame["listDate"], errors="coerce") if "listDate" in frame else pd.Series(pd.NaT, index=frame.index)
    delist_dates = (
        pd.to_datetime(frame["delistDate"], errors="coerce") if "delistDate" in frame else pd.Series(pd.NaT, index=frame.index)
    )
    list_date_coverage = float(list_dates.notna().mean()) if rows else 0.0
    delisted_rows = int(delist_dates.notna().sum()) if rows else 0
    earliest_list_date = _date_text(list_dates.min()) if rows and list_dates.notna().any() else ""
    latest_list_date = _date_text(list_dates.max()) if rows and list_dates.notna().any() else ""
    latest_delist_date = _date_text(delist_dates.max()) if rows and delist_dates.notna().any() else ""

    eligible_symbols = symbols_from_stock_master(frame, start=start, end=end, include_bj=include_bj)
    stock_type_rate = _a_share_type_rate(frame)
    b_share_like = _b_share_symbol_mask(symbols)
    non_a_type = pd.Series(False, index=frame.index, dtype=bool)
    if "stockType" in frame:
        stock_type = frame["stockType"].where(frame["stockType"].notna(), "").astype(str).str.upper()
        non_a_type = ~stock_type.isin({"", "A", "A股".upper(), "ASHARE", "A-SHARE", "NAN", "NONE"})
    non_a_rows = int((b_share_like | non_a_type).sum()) if rows else 0
    has_sh = exchange_counts.get("SH", 0) > 0
    has_sz = exchange_counts.get("SZ", 0) > 0

    checks = [
        _trust_check(
            "required_columns",
            not missing_columns,
            "hard",
            f"Required normalized columns present; missing={missing_columns or 'none'}.",
        ),
        _trust_check("row_coverage", rows >= min_rows, "hard", f"Rows {rows}; required >= {min_rows}."),
        _trust_check(
            "unique_symbol_coverage",
            unique_symbols >= min_unique_symbols,
            "hard",
            f"Unique valid symbols {unique_symbols}; required >= {min_unique_symbols}.",
        ),
        _trust_check(
            "symbol_format",
            valid_symbol_rate >= min_valid_symbol_rate,
            "hard",
            f"Valid A-share symbol rate {valid_symbol_rate:.2%}; required >= {min_valid_symbol_rate:.2%}.",
        ),
        _trust_check(
            "duplicate_symbols",
            duplicate_symbols == 0,
            "hard",
            f"Duplicate normalized symbols: {duplicate_symbols}.",
        ),
        _trust_check(
            "list_date_coverage",
            list_date_coverage >= min_list_date_coverage,
            "hard",
            f"listDate coverage {list_date_coverage:.2%}; required >= {min_list_date_coverage:.2%}.",
        ),
        _trust_check(
            "delisted_security_coverage",
            delisted_rows >= min_delisted_rows,
            "hard",
            f"Rows with delistDate {delisted_rows}; required >= {min_delisted_rows} for survivorship-bias closure.",
        ),
        _trust_check(
            "exchange_coverage",
            has_sh and has_sz,
            "hard",
            f"Exchange counts {exchange_counts}; SH and SZ must both be present.",
        ),
        _trust_check(
            "a_share_rows_only",
            non_a_rows == 0,
            "hard",
            f"Non-A-share or B-share-like rows: {non_a_rows}.",
        ),
        _trust_check(
            "a_share_type_coverage",
            stock_type_rate >= 0.95,
            "warn",
            f"A-share stockType coverage {stock_type_rate:.2%}; non-A rows should be removed or tagged.",
        ),
        _trust_check(
            "eligible_period_symbols",
            len(eligible_symbols) >= min(100, min_unique_symbols),
            "warn",
            f"Eligible symbols for requested period: {len(eligible_symbols)}.",
        ),
    ]
    hard_failed = sum(1 for check in checks if check["severity"] == "hard" and not check["passed"])
    warnings = sum(1 for check in checks if check["severity"] == "warn" and not check["passed"])
    if hard_failed == 0:
        status = "production_ready"
        coverage_level = "full_historical_stock_master"
    elif rows >= min_rows and unique_symbols >= min_unique_symbols:
        status = "needs_review"
        coverage_level = "historical_candidate"
    elif rows > 0:
        status = "candidate_pool"
        coverage_level = "partial_stock_master"
    else:
        status = "invalid"
        coverage_level = "empty"

    caveats = [
        str(check["detail"])
        for check in checks
        if check["severity"] == "hard" and not check["passed"]
    ]
    notes = [
        "Production-ready historical stock master requires current and delisted A-share securities.",
        "listDate/delistDate are point-in-time eligibility fields; current listStatus alone is not enough.",
    ]
    if include_bj:
        notes.append("Beijing Stock Exchange symbols are included in eligibility counts.")
    else:
        notes.append("Beijing Stock Exchange symbols are excluded from period eligibility counts.")

    return {
        "status": status,
        "coverage_level": coverage_level,
        "hard_failed": hard_failed,
        "warnings": warnings,
        "checks": checks,
        "metrics": {
            "rows": rows,
            "unique_symbols": unique_symbols,
            "eligible_symbols": len(eligible_symbols),
            "duplicate_symbols": duplicate_symbols,
            "missing_columns": missing_columns,
            "valid_symbol_rate": valid_symbol_rate,
            "list_date_coverage": list_date_coverage,
            "delisted_rows": delisted_rows,
            "a_share_type_rate": stock_type_rate,
            "exchange_counts": exchange_counts,
            "earliest_list_date": earliest_list_date,
            "latest_list_date": latest_list_date,
            "latest_delist_date": latest_delist_date,
            "start": start or "",
            "end": end or "",
        },
        "caveats": caveats,
        "notes": notes,
    }


def render_stock_master_validation_markdown(validation: dict[str, object]) -> str:
    metrics = validation.get("metrics") if isinstance(validation.get("metrics"), dict) else {}
    lines = [
        "## Historical Stock Master Validation",
        "",
        f"Status: `{validation.get('status', 'n/a')}`",
        f"Coverage level: `{validation.get('coverage_level', 'n/a')}`",
        f"Hard failed: {validation.get('hard_failed', 0)}",
        f"Warnings: {validation.get('warnings', 0)}",
        "",
        "### Metrics",
        "",
        f"Rows: {metrics.get('rows', 0)}",
        f"Unique symbols: {metrics.get('unique_symbols', 0)}",
        f"Eligible symbols: {metrics.get('eligible_symbols', 0)}",
        f"Duplicate symbols: {metrics.get('duplicate_symbols', 0)}",
        f"Valid symbol rate: {_format_rate(metrics.get('valid_symbol_rate', 0.0))}",
        f"listDate coverage: {_format_rate(metrics.get('list_date_coverage', 0.0))}",
        f"Delisted rows: {metrics.get('delisted_rows', 0)}",
        f"A-share type rate: {_format_rate(metrics.get('a_share_type_rate', 0.0))}",
        f"Exchange counts: {metrics.get('exchange_counts', {})}",
        f"List date range: {metrics.get('earliest_list_date', '') or 'n/a'} to {metrics.get('latest_list_date', '') or 'n/a'}",
        f"Latest delist date: {metrics.get('latest_delist_date', '') or 'n/a'}",
        "",
        "### Checks",
        "",
        "| Check | Severity | Passed | Detail |",
        "|---|---|---:|---|",
    ]
    checks = validation.get("checks", [])
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, dict):
                continue
            lines.append(
                "| {name} | {severity} | {passed} | {detail} |".format(
                    name=_markdown_cell(str(check.get("name", ""))),
                    severity=_markdown_cell(str(check.get("severity", ""))),
                    passed="yes" if check.get("passed") else "no",
                    detail=_markdown_cell(str(check.get("detail", ""))),
                )
            )
    caveats = validation.get("caveats", [])
    if isinstance(caveats, list) and caveats:
        lines.extend(["", "### Caveats", ""])
        lines.extend(f"- {str(item)}" for item in caveats[:12])
    lines.append("")
    return "\n".join(lines)


def write_stock_master_validation_artifacts(output_dir: str | Path, validation: dict[str, object]) -> dict[str, Path]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "historical_stock_master_validation.json"
    markdown_path = target / "historical_stock_master_validation.md"
    _write_json(json_path, validation)
    markdown_path.write_text(render_stock_master_validation_markdown(validation), encoding="utf-8")
    return {"stock_master_validation": json_path, "stock_master_validation_report": markdown_path}


def data_trust_summary(loaded: DataLoadResult, *, min_stock_master_rows: int = 3000) -> dict[str, object]:
    min_stock_master_rows = _metadata_min_stock_master_rows(loaded.metadata.notes, min_stock_master_rows)
    min_delisted_rows = _metadata_min_delisted_rows(loaded.metadata.notes, 50)
    source = loaded.metadata.source
    universe_source = universe_source_from_source(source)
    validation: dict[str, object] | None = None
    if loaded.stock_master is not None and not loaded.stock_master.empty:
        validation = validate_stock_master_asset(
            loaded.stock_master,
            start=loaded.metadata.start_date,
            end=loaded.metadata.end_date,
            min_rows=min_stock_master_rows,
            min_delisted_rows=min_delisted_rows,
        )

    real_source = "investoday:" in source or "historical_asset:" in source
    checks = [
        _trust_check("real_market_data", real_source, "hard", "Research-grade runs must use real or vendor historical market data."),
        _trust_check("not_sample", source != "sample", "hard", "Sample data is for demos only."),
        _trust_check(
            "pit_liquidity_universe",
            "pit_liquidity_universe" in source,
            "hard",
            "Daily universe membership must be based on prior information.",
        ),
        _trust_check(
            "pit_stock_master_filter",
            "pit_stock_master_filter" in source,
            "hard",
            "Listing eligibility must use listDate/delistDate point-in-time fields.",
        ),
        _trust_check(
            "full_historical_stock_master",
            "full_historical_stock_master" in source and "historical_stock_master_truncated" not in source,
            "hard",
            "Candidate pool must be a validated full historical stock master and must not be truncated.",
        ),
        _trust_check(
            "stock_master_validation",
            validation is not None and validation.get("status") == "production_ready",
            "hard",
            "Historical stock master asset must pass production validation.",
        ),
    ]
    hard_failed = sum(1 for check in checks if check["severity"] == "hard" and not check["passed"])
    caveats = [str(check["detail"]) for check in checks if check["severity"] == "hard" and not check["passed"]]
    if validation:
        caveats.extend(str(item) for item in validation.get("caveats", []) or [])

    production_ready = hard_failed == 0
    if production_ready:
        trust_level = "production_research"
        status = "ready"
    elif source == "sample":
        trust_level = "sample"
        status = "demo_only"
    elif universe_source == "full_historical_stock_master":
        trust_level = "historical_needs_review"
        status = "blocked"
    elif universe_source == "historical_stock_master_candidate_pool":
        trust_level = "historical_candidate"
        status = "research_only"
    elif "investoday:" in source:
        trust_level = "real_data_candidate_pool"
        status = "research_only"
    else:
        trust_level = "custom_or_unknown"
        status = "research_only"

    return {
        "status": status,
        "trust_level": trust_level,
        "production_data_ready": production_ready,
        "universe_source": universe_source,
        "data_source_kind": data_source_kind_from_source(source),
        "stock_master_rows": 0 if loaded.stock_master is None else int(len(loaded.stock_master)),
        "universe_rows": 0 if loaded.universe is None else int(len(loaded.universe)),
        "source": source,
        "start_date": loaded.metadata.start_date,
        "end_date": loaded.metadata.end_date,
        "symbols": len(loaded.metadata.symbols),
        "rows": len(loaded.data),
        "hard_failed": hard_failed,
        "checks": checks,
        "caveats": caveats,
        "stock_master_validation": validation or {},
        "notes": [
            "This status answers whether a run is suitable for serious historical research.",
            "Paper trading can still be blocked by separate performance, risk, and operations gates.",
        ],
    }


def enforce_production_data(loaded: DataLoadResult, *, min_stock_master_rows: int = 3000) -> dict[str, object]:
    summary = data_trust_summary(loaded, min_stock_master_rows=min_stock_master_rows)
    if not summary.get("production_data_ready"):
        caveats = summary.get("caveats", []) or []
        detail = "; ".join(str(item) for item in caveats[:5])
        raise DataSourceError(f"Production data gate failed: {detail or summary.get('trust_level', 'unknown')}")
    return summary


def render_data_trust_markdown(summary: dict[str, object]) -> str:
    validation = summary.get("stock_master_validation") if isinstance(summary.get("stock_master_validation"), dict) else {}
    validation_metrics = validation.get("metrics") if isinstance(validation.get("metrics"), dict) else {}
    lines = [
        "## Data Trust",
        "",
        f"Status: `{summary.get('status', 'n/a')}`",
        f"Trust level: `{summary.get('trust_level', 'n/a')}`",
        f"Production data ready: {'yes' if summary.get('production_data_ready') else 'no'}",
        f"Universe source: `{summary.get('universe_source', 'n/a')}`",
        f"Data source kind: `{summary.get('data_source_kind', 'n/a')}`",
        f"Symbols: {summary.get('symbols', 0)}",
        f"Rows: {summary.get('rows', 0)}",
        f"Stock master rows: {summary.get('stock_master_rows', 0)}",
        "",
        "| Check | Severity | Passed | Detail |",
        "|---|---|---:|---|",
    ]
    checks = summary.get("checks", [])
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, dict):
                continue
            lines.append(
                "| {name} | {severity} | {passed} | {detail} |".format(
                    name=_markdown_cell(str(check.get("name", ""))),
                    severity=_markdown_cell(str(check.get("severity", ""))),
                    passed="yes" if check.get("passed") else "no",
                    detail=_markdown_cell(str(check.get("detail", ""))),
                )
            )
    if validation:
        lines.extend(
            [
                "",
                "### Historical Stock Master Validation",
                "",
                f"Status: `{validation.get('status', 'n/a')}`",
                f"Coverage level: `{validation.get('coverage_level', 'n/a')}`",
                f"Unique symbols: {validation_metrics.get('unique_symbols', 0)}",
                f"Eligible symbols: {validation_metrics.get('eligible_symbols', 0)}",
                f"Delisted rows: {validation_metrics.get('delisted_rows', 0)}",
                f"listDate coverage: {_format_rate(validation_metrics.get('list_date_coverage', 0.0))}",
                "",
                "| Asset Check | Severity | Passed | Detail |",
                "|---|---|---:|---|",
            ]
        )
        asset_checks = validation.get("checks", [])
        if isinstance(asset_checks, list):
            for check in asset_checks:
                if not isinstance(check, dict):
                    continue
                lines.append(
                    "| {name} | {severity} | {passed} | {detail} |".format(
                        name=_markdown_cell(str(check.get("name", ""))),
                        severity=_markdown_cell(str(check.get("severity", ""))),
                        passed="yes" if check.get("passed") else "no",
                        detail=_markdown_cell(str(check.get("detail", ""))),
                    )
                )
    caveats = summary.get("caveats", [])
    if isinstance(caveats, list) and caveats:
        lines.extend(["", "### Caveats", ""])
        lines.extend(f"- {str(item)}" for item in caveats[:12])
    lines.append("")
    return "\n".join(lines)


def write_data_trust_artifacts(output_dir: str | Path, summary: dict[str, object]) -> dict[str, Path]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "data_trust.json"
    markdown_path = target / "data_trust.md"
    _write_json(json_path, summary)
    markdown_path.write_text(render_data_trust_markdown(summary), encoding="utf-8")
    return {"data_trust": json_path, "data_trust_report": markdown_path}


def universe_source_from_source(source: str) -> str:
    if "full_historical_stock_master" in source:
        return "full_historical_stock_master"
    if "historical_stock_master_candidate_pool" in source:
        return "historical_stock_master_candidate_pool"
    if "pit_liquidity_universe" in source and "stock-quote/realtime-ext" in source:
        return "realtime_candidate_pit_liquidity"
    if "stock-quote/realtime-ext" in source:
        return "realtime_candidate_pool"
    if source == "sample":
        return "sample"
    return "custom"


def data_source_kind_from_source(source: str) -> str:
    if source == "sample":
        return "sample"
    if "investoday:" in source:
        return "investoday_real"
    if "historical_asset:" in source:
        return "historical_asset"
    if source.startswith("csv"):
        return "csv"
    if source.startswith("akshare"):
        return "akshare"
    if source.startswith("tushare"):
        return "tushare"
    return "unknown"


def load_investoday_realtime_universe(
    limit: int = 100,
    sort_column: str = "dealMoney",
    order: str = "desc",
    include_bj: bool = False,
    exclude_st: bool = True,
    cache_dir: str | Path | None = "cache/investoday_api",
    refresh_cache: bool = False,
    max_pages: int | None = None,
) -> UniverseDiscoveryResult:
    if limit < 1:
        raise DataSourceError("Universe limit must be positive.")
    if order not in {"asc", "desc"}:
        raise DataSourceError("Investoday realtime universe order must be asc or desc.")

    records: list[dict[str, object]] = []
    seen: set[str] = set()
    page = 1
    page_cap = max_pages or max(20, limit // 10 + 20)
    while len(seen) < limit and page <= page_cap:
        page_records = _investoday_post(
            "stock-quote/realtime-ext",
            {"stockCodes": []},
            query_params={"sortColumn": sort_column, "order": order, "page": page},
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
        )
        if not page_records:
            break

        new_symbols = 0
        for item in page_records:
            row = dict(item)
            row["_universe_page"] = page
            row["_universe_rank"] = len(records) + 1
            records.append(row)
            symbol = _normalize_symbol_with_market(row.get("stockCode"), row.get("marketType"))
            if symbol not in seen:
                seen.add(symbol)
                new_symbols += 1
        if new_symbols == 0:
            break
        page += 1

    if not records:
        raise DataSourceError("Investoday realtime universe returned no rows.")

    universe = _normalize_investoday_realtime_universe(pd.DataFrame(records), sort_column=sort_column, order=order)
    if not include_bj:
        universe = universe[~universe["symbol"].str.endswith(".BJ")].copy()
    if exclude_st:
        universe = universe[~universe["is_st"]].copy()
    universe = universe.drop_duplicates("symbol", keep="first").head(limit).reset_index(drop=True)
    universe["universe_rank"] = range(1, len(universe) + 1)

    if universe.empty:
        raise DataSourceError("Investoday realtime universe had no eligible symbols after filters.")

    symbols = tuple(universe["symbol"].tolist())
    notes = [
        f"Investoday stock-quote/realtime-ext universe sorted by {sort_column} {order}.",
        f"Universe size requested: {limit}; returned eligible symbols: {len(symbols)}.",
        "This is a current-day liquidity universe, not a survivorship-bias-free historical universe.",
    ]
    if not include_bj:
        notes.append("Beijing Stock Exchange symbols are excluded by default.")
    if exclude_st:
        notes.append("Current ST-like stock names are excluded by default.")
    if cache_dir is not None:
        notes.append(f"Investoday API cache directory: {Path(cache_dir)}.")

    return UniverseDiscoveryResult(
        symbols=symbols,
        universe=universe,
        source="investoday:stock-quote/realtime-ext",
        notes=tuple(notes),
        data_hash=_dataframe_hash(universe),
    )


def load_investoday_panel(
    symbols: Iterable[str],
    start: str,
    end: str,
    page_size: int = 500,
    api_batch_size: int = 20,
    include_limit_flags: bool = True,
    include_financials: bool = True,
    cache_dir: str | Path | None = "cache/investoday_api",
    refresh_cache: bool = False,
) -> DataLoadResult:
    normalized_symbols = tuple(_normalize_symbol(symbol) for symbol in symbols)
    if not normalized_symbols:
        raise DataSourceError("Investoday source requires at least one symbol.")

    records = _investoday_fetch_paginated(
        "stock/adjusted-quotes",
        {
            "stockCodes": [_symbol_to_code(symbol) for symbol in normalized_symbols],
            "beginDate": _date_with_dash(start),
            "endDate": _date_with_dash(end),
        },
        page_size=page_size,
        cache_dir=cache_dir,
        refresh_cache=refresh_cache,
    )
    if not records:
        raise DataSourceError("Investoday returned no adjusted quote data for the requested symbols and range.")

    quote_frame = _normalize_investoday_adjusted_quotes(pd.DataFrame(records))
    notes = [
        "Investoday adjusted daily stock quotes.",
        "PE/PB are sourced from adjusted quote fields when available.",
        "isTrading is mapped to suspension status.",
    ]
    if cache_dir is not None:
        notes.append(f"Investoday API cache directory: {Path(cache_dir)}.")
    if len(normalized_symbols) > api_batch_size:
        notes.append(f"Heavy enrichment endpoints are fetched in batches of {api_batch_size} symbols.")
    if include_limit_flags:
        limit_records = _investoday_fetch_paginated_batched(
            "stock/limit-up-down",
            {
                "stockCodes": [_symbol_to_code(symbol) for symbol in normalized_symbols],
                "beginDate": _date_with_dash(start),
                "endDate": _date_with_dash(end),
            },
            batch_key="stockCodes",
            batch_size=api_batch_size,
            page_size=page_size,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
        )
        if limit_records:
            quote_frame = quote_frame.merge(
                _normalize_investoday_limit_flags(pd.DataFrame(limit_records)),
                on=["date", "symbol"],
                how="left",
            )
            notes.append("Limit-up/down flags are sourced from Investoday stock/limit-up-down.")
        else:
            notes.append("Investoday limit-up/down endpoint returned no rows; falling back to simplified limits.")
    else:
        notes.append("Limit-up/down uses a simplified 10% rule in MVP v0.")

    if include_financials:
        financial_records = _investoday_fetch_paginated_batched(
            "stock/financial-indicators-profitab",
            {
                "stockCodes": [_symbol_to_code(symbol) for symbol in normalized_symbols],
                "beginDate": _financial_begin_date(start),
                "endDate": _date_with_dash(end),
            },
            batch_key="stockCodes",
            batch_size=api_batch_size,
            page_size=page_size,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
        )
        if financial_records:
            financial_frame = _normalize_investoday_profitability(pd.DataFrame(financial_records), end=end)
            quote_frame = _merge_point_in_time_financials(quote_frame, financial_frame)
            notes.append("ROE is sourced from Investoday stock/financial-indicators-profitab using publishDate alignment.")
        else:
            notes.append("Investoday profitability endpoint returned no rows; ROE is unavailable.")
    else:
        notes.append("Financial factor loading is disabled; ROE is unavailable.")

    data = prepare_backtest_panel(quote_frame)
    data_hash = _dataframe_hash(data)
    return DataLoadResult(
        data=data,
        metadata=DataSourceMetadata(
            source="investoday:stock/adjusted-quotes",
            symbols=normalized_symbols,
            start_date=start,
            end_date=end,
            notes=tuple(notes),
            data_hash=data_hash,
        ),
    )


def load_investoday_stock_master(
    symbols: Iterable[str],
    api_batch_size: int = 100,
    page_size: int = 500,
    cache_dir: str | Path | None = "cache/investoday_api",
    refresh_cache: bool = False,
) -> StockMasterResult:
    normalized_symbols = tuple(_normalize_symbol(symbol) for symbol in symbols)
    if not normalized_symbols:
        raise DataSourceError("Investoday stock master requires at least one symbol.")

    records = _investoday_fetch_paginated_batched(
        "stock/basic-info",
        {"stockCodes": [_symbol_to_code(symbol) for symbol in normalized_symbols]},
        batch_key="stockCodes",
        batch_size=api_batch_size,
        page_size=page_size,
        cache_dir=cache_dir,
        refresh_cache=refresh_cache,
    )
    if not records:
        raise DataSourceError("Investoday returned no stock/basic-info rows for the requested symbols.")

    master = _normalize_investoday_stock_basic_info(pd.DataFrame(records))
    if master.empty:
        raise DataSourceError("Investoday stock/basic-info rows were empty after normalization.")

    notes = [
        "Investoday stock/basic-info stock master metadata.",
        "listDate, delistDate, stockType and listStatus are used for point-in-time listing eligibility.",
    ]
    if cache_dir is not None:
        notes.append(f"Investoday API cache directory: {Path(cache_dir)}.")
    return StockMasterResult(
        master=master,
        source="investoday:stock/basic-info",
        notes=tuple(notes),
        data_hash=_dataframe_hash(master),
    )


def apply_point_in_time_liquidity_universe(
    data: pd.DataFrame,
    top_n: int = 100,
    lookback_days: int = 20,
    min_history_days: int = 20,
) -> PointInTimeUniverseResult:
    if top_n < 1:
        raise DataSourceError("Point-in-time universe top_n must be positive.")
    if lookback_days < 1:
        raise DataSourceError("Point-in-time universe lookback_days must be positive.")

    panel = data.copy()
    panel["date"] = pd.to_datetime(panel["date"])
    panel.sort_values(["symbol", "date"], inplace=True)
    min_periods = max(1, min(min_history_days, lookback_days))
    panel["universe_liquidity"] = panel.groupby("symbol")["amount"].transform(
        lambda values: values.rolling(lookback_days, min_periods=min_periods).mean().shift(1)
    )

    eligible = panel["universe_liquidity"].notna()
    if "is_suspended" in panel:
        eligible &= ~panel["is_suspended"].fillna(False).astype(bool)
    if "is_st" in panel:
        eligible &= ~panel["is_st"].fillna(False).astype(bool)
    panel["universe_rank"] = np.nan
    panel["is_universe_member"] = False
    if eligible.any():
        ranks = panel.loc[eligible].groupby("date")["universe_liquidity"].rank(
            method="first",
            ascending=False,
        )
        panel.loc[ranks.index, "universe_rank"] = ranks
        panel.loc[ranks.index, "is_universe_member"] = ranks <= top_n

    panel.index = pd.RangeIndex(len(panel))
    universe = panel[
        [
            column
            for column in (
                "date",
                "symbol",
                "stockName",
                "marketType",
                "industryLV1Name",
                "industryName",
                "boardName",
                "stockType",
                "listStatus",
                "listDate",
                "delistDate",
                "amount",
                "universe_liquidity",
                "universe_rank",
                "is_universe_member",
                "is_stock_master_member",
                "is_st",
                "is_suspended",
            )
            if column in panel.columns
        ]
    ].copy()
    notes = (
        f"Point-in-time liquidity universe: daily top {top_n} by prior {lookback_days}-day average amount.",
        f"Universe liquidity uses shifted historical amounts with at least {min_periods} prior observations.",
        "The daily membership flag is evaluated before factor ranking on each rebalance date.",
        "Candidate symbols still come from the selected input pool; this reduces look-ahead in ranking but is not fully survivorship-bias-free unless the candidate pool is historical.",
    )
    return PointInTimeUniverseResult(
        data=panel,
        universe=universe,
        source="pit_liquidity_universe",
        notes=notes,
        data_hash=_dataframe_hash(panel),
    )


def enrich_panel_with_stock_master(data: pd.DataFrame, stock_master: pd.DataFrame | None) -> pd.DataFrame:
    if stock_master is None or stock_master.empty or "symbol" not in stock_master:
        return data.copy()

    master_columns = [
        column
        for column in (
            "stockCode",
            "exchangeCode",
            "boardCode",
            "boardName",
            "stockName",
            "stockFullName",
            "listStatus",
            "listDate",
            "delistDate",
            "stockType",
            "companyId",
            "sharesTotal",
            "sharesFloat",
            "sharesFloatA",
            "reportDate",
            "companyGrowthStage",
        )
        if column in stock_master.columns
    ]
    if not master_columns:
        return data.copy()

    lookup = stock_master[["symbol", *master_columns]].copy()
    lookup["symbol"] = lookup["symbol"].map(_normalize_symbol)
    lookup = lookup.dropna(subset=["symbol"]).drop_duplicates("symbol", keep="first")
    if lookup.empty:
        return data.copy()

    frame = data.copy()
    frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    existing_columns = set(frame.columns)
    merged = frame.merge(lookup, on="symbol", how="left", suffixes=("", "_master"))
    for column in master_columns:
        if column in existing_columns:
            master_column = f"{column}_master"
            if master_column in merged:
                merged[column] = merged[column].where(merged[column].notna(), merged[master_column])
                merged.drop(columns=[master_column], inplace=True)
    return merged


def apply_point_in_time_stock_master_filter(data: pd.DataFrame) -> PointInTimeStockMasterResult:
    panel = data.copy()
    if panel.empty:
        return PointInTimeStockMasterResult(
            data=panel,
            source="pit_stock_master_filter",
            notes=("Point-in-time stock master filter skipped because data is empty.",),
            data_hash=_dataframe_hash(panel),
        )

    panel["date"] = pd.to_datetime(panel["date"])
    listed = pd.Series(True, index=panel.index, dtype=bool)
    if "listDate" in panel:
        list_dates = pd.to_datetime(panel["listDate"], errors="coerce")
        listed &= list_dates.isna() | (panel["date"] >= list_dates.dt.normalize())
    if "delistDate" in panel:
        delist_dates = pd.to_datetime(panel["delistDate"], errors="coerce")
        listed &= delist_dates.isna() | (panel["date"] < delist_dates.dt.normalize())
    if "stockType" in panel:
        raw_stock_type = panel["stockType"]
        stock_type = raw_stock_type.astype(str).str.upper()
        listed &= raw_stock_type.isna() | stock_type.isin({"A股".upper(), "A"})

    panel["is_stock_master_member"] = listed.fillna(False).astype(bool)
    panel.sort_values(["date", "symbol"], inplace=True)
    panel.reset_index(drop=True, inplace=True)
    notes = (
        "Point-in-time stock master filter: date must be on or after listDate and before delistDate when available.",
        "stockType must be A-share when stock/basic-info provides the field.",
        "listStatus is retained for audit; historical eligibility is based on listDate/delistDate rather than current status alone.",
    )
    return PointInTimeStockMasterResult(
        data=panel,
        source="pit_stock_master_filter",
        notes=notes,
        data_hash=_dataframe_hash(panel),
    )


def enrich_panel_with_universe_classification(data: pd.DataFrame, universe: pd.DataFrame | None) -> pd.DataFrame:
    if universe is None or universe.empty or "symbol" not in universe:
        return data.copy()

    classification_columns = [
        column
        for column in ("stockName", "marketType", "industryLV1Name", "industryName")
        if column in universe.columns
    ]
    if not classification_columns:
        return data.copy()

    lookup = universe[["symbol", *classification_columns]].copy()
    lookup["symbol"] = lookup["symbol"].map(_normalize_symbol)
    lookup = lookup.dropna(subset=["symbol"]).drop_duplicates("symbol", keep="first")
    if lookup.empty:
        return data.copy()

    frame = data.copy()
    frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    existing_columns = set(frame.columns)
    merged = frame.merge(lookup, on="symbol", how="left", suffixes=("", "_universe"))
    for column in classification_columns:
        if column in existing_columns:
            universe_column = f"{column}_universe"
            if universe_column in merged:
                merged[column] = merged[column].where(merged[column].notna(), merged[universe_column])
                merged.drop(columns=[universe_column], inplace=True)
    return merged


def load_investoday_benchmark_quotes(
    index_code: str,
    start: str,
    end: str,
    page_size: int = 500,
    cache_dir: str | Path | None = "cache/investoday_api",
    refresh_cache: bool = False,
) -> BenchmarkLoadResult:
    normalized_code = index_code.strip()
    if not normalized_code:
        raise DataSourceError("Benchmark index code is required.")
    records = _investoday_fetch_paginated(
        "index/quotes",
        {
            "indexCode": normalized_code,
            "beginDate": _date_with_dash(start),
            "endDate": _date_with_dash(end),
        },
        page_size=page_size,
        cache_dir=cache_dir,
        refresh_cache=refresh_cache,
    )
    if not records:
        raise DataSourceError(f"Investoday returned no benchmark quotes for index {normalized_code}.")
    data = _normalize_investoday_index_quotes(pd.DataFrame(records))
    index_name = str(data["indexName"].dropna().iloc[0]) if "indexName" in data and data["indexName"].notna().any() else normalized_code
    notes = [f"Investoday index/quotes benchmark for {normalized_code}."]
    if cache_dir is not None:
        notes.append(f"Investoday API cache directory: {Path(cache_dir)}.")
    return BenchmarkLoadResult(
        data=data,
        metadata=DataSourceMetadata(
            source="investoday:index/quotes",
            symbols=(normalized_code,),
            start_date=start,
            end_date=end,
            notes=tuple(notes + [f"Benchmark name: {index_name}."]),
            data_hash=_dataframe_hash(data),
        ),
    )


def load_akshare_panel(
    symbols: Iterable[str],
    start: str,
    end: str,
    adjust: str = "qfq",
) -> DataLoadResult:
    try:
        import akshare as ak
    except ImportError as exc:
        raise DataSourceError("AKShare is not installed. Run: python3 -m pip install akshare") from exc
    except Exception as exc:
        raise DataSourceError(
            "AKShare could not be imported. Recent AKShare versions require Python 3.10+. "
            f"Current Python is {sys.version.split()[0]}."
        ) from exc

    frames: list[pd.DataFrame] = []
    normalized_symbols = tuple(_normalize_symbol(symbol) for symbol in symbols)
    for symbol in normalized_symbols:
        code = _symbol_to_code(symbol)
        try:
            raw = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=_date_compact(start),
                end_date=_date_compact(end),
                adjust=adjust,
            )
        except Exception as exc:
            raise DataSourceError(
                f"AKShare request failed for {symbol}. Check network/proxy access to the upstream data site."
            ) from exc
        if raw is None or raw.empty:
            raise DataSourceError(f"AKShare returned no data for {symbol}")
        frames.append(_normalize_akshare_hist(raw, symbol))

    data = prepare_backtest_panel(pd.concat(frames, ignore_index=True))
    return DataLoadResult(
        data=data,
        metadata=DataSourceMetadata(
            source=f"akshare:{adjust or 'raw'}",
            symbols=normalized_symbols,
            start_date=start,
            end_date=end,
            notes=(
                "AKShare stock_zh_a_hist OHLCV data.",
                "Fundamental fields such as ROE and PE are not included by this adapter.",
                "Limit-up/down uses a simplified 10% rule in MVP v0.",
            ),
            data_hash=_dataframe_hash(data),
        ),
    )


def load_tushare_panel(
    symbols: Iterable[str],
    start: str,
    end: str,
    token: str | None = None,
    include_basic: bool = True,
) -> DataLoadResult:
    try:
        import tushare as ts
    except ImportError as exc:
        raise DataSourceError("Tushare is not installed. Run: python3 -m pip install tushare") from exc
    except Exception as exc:
        raise DataSourceError(f"Tushare could not be imported: {exc}") from exc

    token = token or os.environ.get("TUSHARE_TOKEN")
    if not token:
        raise DataSourceError("Tushare requires a token. Set TUSHARE_TOKEN or pass --tushare-token.")

    ts.set_token(token)
    pro = ts.pro_api()
    frames: list[pd.DataFrame] = []
    normalized_symbols = tuple(_normalize_symbol(symbol) for symbol in symbols)
    for symbol in normalized_symbols:
        try:
            daily = pro.daily(ts_code=symbol, start_date=_date_compact(start), end_date=_date_compact(end))
        except Exception as exc:
            raise DataSourceError(f"Tushare daily request failed for {symbol}.") from exc
        if daily is None or daily.empty:
            raise DataSourceError(f"Tushare daily returned no data for {symbol}")
        frame = _normalize_tushare_daily(daily)
        if include_basic:
            try:
                basic = pro.daily_basic(
                    ts_code=symbol,
                    start_date=_date_compact(start),
                    end_date=_date_compact(end),
                    fields="ts_code,trade_date,pe,pb,dv_ratio",
                )
            except Exception:
                basic = None
            if basic is not None and not basic.empty:
                frame = frame.merge(_normalize_tushare_basic(basic), on=["date", "symbol"], how="left")
        frames.append(frame)

    data = prepare_backtest_panel(pd.concat(frames, ignore_index=True))
    return DataLoadResult(
        data=data,
        metadata=DataSourceMetadata(
            source="tushare",
            symbols=normalized_symbols,
            start_date=start,
            end_date=end,
            notes=(
                "Tushare daily OHLCV data.",
                "daily_basic can provide PE, PB and dividend yield when permissions allow it.",
                "ROE is intentionally not forward-filled in MVP v0 to avoid point-in-time mistakes.",
                "Limit-up/down uses a simplified 10% rule in MVP v0.",
            ),
            data_hash=_dataframe_hash(data),
        ),
    )


def prepare_backtest_panel(data: pd.DataFrame) -> pd.DataFrame:
    normalized = _normalize_common_columns(data)
    aligned = _align_symbol_dates(normalized)
    featured = add_technical_features(aligned)
    robust = add_robust_factor_features(featured)
    return robust.sort_values(["date", "symbol"]).reset_index(drop=True)


def add_technical_features(data: pd.DataFrame) -> pd.DataFrame:
    panel = data.copy()
    panel.sort_values(["symbol", "date"], inplace=True)
    panel["daily_return"] = panel.groupby("symbol")["close"].pct_change(fill_method=None)
    panel["momentum_20d"] = panel.groupby("symbol")["close"].pct_change(20, fill_method=None)
    panel["momentum_60d"] = panel.groupby("symbol")["close"].pct_change(60, fill_method=None)
    panel["momentum_120d"] = panel.groupby("symbol")["close"].pct_change(120, fill_method=None)
    panel["momentum_252d"] = panel.groupby("symbol")["close"].pct_change(252, fill_method=None)
    panel["volatility_20d"] = (
        panel.groupby("symbol")["daily_return"].rolling(20).std().reset_index(level=0, drop=True)
    )
    panel["volatility_60d"] = (
        panel.groupby("symbol")["daily_return"].rolling(60).std().reset_index(level=0, drop=True)
    )
    panel["_downside_return"] = panel["daily_return"].where(panel["daily_return"] < 0.0, 0.0).where(
        panel["daily_return"].notna()
    )
    panel["volatility_downside_60d"] = (
        panel.groupby("symbol")["_downside_return"].rolling(60, min_periods=20).std().reset_index(level=0, drop=True)
    )
    rolling_high_120d = panel.groupby("symbol")["close"].rolling(120, min_periods=20).max().reset_index(level=0, drop=True)
    panel["drawdown_120d"] = panel["close"] / rolling_high_120d - 1.0
    rolling_high_252d = panel.groupby("symbol")["close"].rolling(252, min_periods=60).max().reset_index(level=0, drop=True)
    panel["drawdown_252d"] = panel["close"] / rolling_high_252d - 1.0
    moving_average_60d = panel.groupby("symbol")["close"].rolling(60, min_periods=20).mean().reset_index(level=0, drop=True)
    panel["close_to_ma_60d"] = panel["close"] / moving_average_60d - 1.0
    panel["_positive_return"] = (panel["daily_return"] > 0.0).astype(float).where(panel["daily_return"].notna())
    panel["trend_persistence_120d"] = (
        panel.groupby("symbol")["_positive_return"].rolling(120, min_periods=40).mean().reset_index(level=0, drop=True)
    )
    panel.drop(columns=["_downside_return", "_positive_return"], inplace=True)
    return panel


def add_margin_trade_features(data: pd.DataFrame, *, copy: bool = True) -> pd.DataFrame:
    panel = data.copy() if copy else data
    if "amount" not in panel or not any(
        column in panel for column in ("marginBalance", "marginBuyAmount", "marginRepayAmount", "shortBalanceAmount", "marginShortBalance")
    ):
        return panel

    amount = pd.to_numeric(panel["amount"], errors="coerce").where(lambda value: value > 0.0)
    margin_buy = (
        pd.to_numeric(panel["marginBuyAmount"], errors="coerce")
        if "marginBuyAmount" in panel
        else pd.Series(pd.NA, index=panel.index, dtype="Float64")
    )
    margin_repay = (
        pd.to_numeric(panel["marginRepayAmount"], errors="coerce")
        if "marginRepayAmount" in panel
        else pd.Series(pd.NA, index=panel.index, dtype="Float64")
    )
    margin_balance = (
        pd.to_numeric(panel["marginBalance"], errors="coerce")
        if "marginBalance" in panel
        else pd.Series(pd.NA, index=panel.index, dtype="Float64")
    )
    short_balance = (
        pd.to_numeric(panel["shortBalanceAmount"], errors="coerce")
        if "shortBalanceAmount" in panel
        else pd.Series(pd.NA, index=panel.index, dtype="Float64")
    )
    if "marginShortBalance" in panel:
        margin_short_balance = pd.to_numeric(panel["marginShortBalance"], errors="coerce")
        short_balance = short_balance.combine_first(margin_short_balance)

    panel["margin_net_buy_amount"] = margin_buy - margin_repay
    panel["margin_buy_to_amount"] = margin_buy / amount
    panel["margin_repay_to_amount"] = margin_repay / amount
    panel["margin_net_buy_to_amount"] = panel["margin_net_buy_amount"] / amount
    panel["margin_balance_to_amount"] = margin_balance / amount
    panel["short_balance_to_amount"] = short_balance / amount

    panel["margin_net_buy_strength_score"] = _cross_section_pct_rank(panel, "margin_net_buy_to_amount")
    net_buy_ratio = pd.to_numeric(panel["margin_net_buy_to_amount"], errors="coerce")
    deleveraging_risk = (-net_buy_ratio.clip(lower=-0.20, upper=0.0) / 0.20).fillna(0.0)
    panel["margin_deleveraging_guard_score"] = (1.0 - deleveraging_risk).clip(lower=0.0, upper=1.0).where(
        net_buy_ratio.notna()
    )

    balance_rank = _cross_section_pct_rank(panel, "margin_balance_to_amount")
    panel["margin_balance_crowding_guard_score"] = (1.0 - balance_rank).clip(lower=0.0, upper=1.0).where(
        balance_rank.notna()
    )
    short_rank = _cross_section_pct_rank(panel, "short_balance_to_amount")
    panel["margin_short_pressure_guard_score"] = (1.0 - short_rank).clip(lower=0.0, upper=1.0).where(short_rank.notna())

    panel["margin_leverage_flow_score"] = panel[
        ["margin_net_buy_strength_score", "margin_deleveraging_guard_score"]
    ].mean(axis=1).clip(lower=0.0, upper=1.0)
    panel["margin_trade_quality_score"] = panel[
        [
            "margin_leverage_flow_score",
            "margin_balance_crowding_guard_score",
            "margin_short_pressure_guard_score",
        ]
    ].mean(axis=1).clip(lower=0.0, upper=1.0)
    return panel


def add_robust_factor_features(data: pd.DataFrame, *, copy: bool = True) -> pd.DataFrame:
    panel = data.copy() if copy else data
    panel.sort_values(["symbol", "date"], inplace=True)
    if "dividend_yield" in panel:
        dividend = pd.to_numeric(panel["dividend_yield"], errors="coerce")
        dividend_valid = dividend.between(0.0, 0.20, inclusive="both")
        dividend_sane = dividend.where(dividend.between(0.0, 0.12, inclusive="both"))
        panel["dividend_yield_capped"] = dividend.clip(lower=0.0, upper=0.12).where(dividend_valid)
        panel["dividend_yield_sane"] = dividend_sane
        panel["dividend_yield_valid_score"] = dividend.between(0.005, 0.12, inclusive="both").astype(float)
    if {"dividend_event_count_365d", "dividend_event_cash_365d"}.issubset(panel.columns):
        event_count = pd.to_numeric(panel["dividend_event_count_365d"], errors="coerce").fillna(0.0)
        event_cash = pd.to_numeric(panel["dividend_event_cash_365d"], errors="coerce").fillna(0.0)
        close = pd.to_numeric(panel["close"], errors="coerce") if "close" in panel else pd.Series(pd.NA, index=panel.index)
        days_since = (
            pd.to_numeric(panel["dividend_event_days_since_last"], errors="coerce")
            if "dividend_event_days_since_last" in panel
            else pd.Series(pd.NA, index=panel.index)
        )
        event_yield = event_cash / close.where(close > 0.0)
        panel["dividend_event_yield_365d"] = event_yield.where(event_yield.between(0.0, 0.20, inclusive="both"))
        panel["dividend_event_regular_score"] = event_count.clip(lower=0.0, upper=4.0) / 4.0
        panel["dividend_event_recent_score"] = (1.0 - days_since.clip(lower=0.0, upper=365.0) / 365.0).fillna(0.0)
        panel["dividend_event_cash_score"] = event_yield.clip(lower=0.0, upper=0.08) / 0.08
        panel["dividend_event_quality_score"] = panel[
            ["dividend_event_regular_score", "dividend_event_recent_score", "dividend_event_cash_score"]
        ].mean(axis=1)
    if "amount" in panel and any(
        column in panel for column in ("mainNetInflow", "netInflowLarge", "netInflowXlarge")
    ):
        amount = pd.to_numeric(panel["amount"], errors="coerce").where(lambda value: value > 0.0)
        flow_ratio_specs = {
            "mainNetInflow": "main_net_inflow_to_amount",
            "netInflowLarge": "large_net_inflow_to_amount",
            "netInflowXlarge": "xlarge_net_inflow_to_amount",
        }
        for raw_column, ratio_column in flow_ratio_specs.items():
            if raw_column not in panel:
                continue
            flow_value = pd.to_numeric(panel[raw_column], errors="coerce")
            panel[ratio_column] = flow_value * 10000.0 / amount

        if "main_net_inflow_to_amount" in panel:
            panel["main_flow_strength_score"] = _cross_section_pct_rank(panel, "main_net_inflow_to_amount")
            main_net_inflow = pd.to_numeric(panel["mainNetInflow"], errors="coerce")
            panel["main_flow_positive_score"] = (main_net_inflow > 0.0).astype(float).where(main_net_inflow.notna())
            panel["flow_persistence_20d_raw"] = (
                panel.groupby("symbol")["main_net_inflow_to_amount"]
                .rolling(20, min_periods=5)
                .mean()
                .reset_index(level=0, drop=True)
            )
            panel["flow_persistence_20d_score"] = _cross_section_pct_rank(panel, "flow_persistence_20d_raw")
        if "large_net_inflow_to_amount" in panel:
            panel["large_flow_strength_score"] = _cross_section_pct_rank(panel, "large_net_inflow_to_amount")
        if "xlarge_net_inflow_to_amount" in panel:
            panel["xlarge_flow_strength_score"] = _cross_section_pct_rank(panel, "xlarge_net_inflow_to_amount")

        main_ratio = (
            pd.to_numeric(panel["main_net_inflow_to_amount"], errors="coerce")
            if "main_net_inflow_to_amount" in panel
            else pd.Series(pd.NA, index=panel.index, dtype="Float64")
        )
        xlarge_ratio = (
            pd.to_numeric(panel["xlarge_net_inflow_to_amount"], errors="coerce")
            if "xlarge_net_inflow_to_amount" in panel
            else pd.Series(pd.NA, index=panel.index, dtype="Float64")
        )
        has_flow_guard_input = main_ratio.notna() | xlarge_ratio.notna()
        main_outflow_risk = (-main_ratio.clip(lower=-0.08, upper=0.0) / 0.08).fillna(0.0)
        xlarge_outflow_risk = (-xlarge_ratio.clip(lower=-0.05, upper=0.0) / 0.05).fillna(0.0)
        panel["flow_reversal_guard_score"] = (
            1.0 - (0.60 * main_outflow_risk + 0.40 * xlarge_outflow_risk)
        ).clip(lower=0.0, upper=1.0).where(has_flow_guard_input)

        flow_quality_columns = [
            column
            for column in (
                "main_flow_strength_score",
                "large_flow_strength_score",
                "xlarge_flow_strength_score",
                "flow_persistence_20d_score",
                "flow_reversal_guard_score",
            )
            if column in panel
        ]
        if flow_quality_columns:
            panel["capital_flow_quality_score"] = panel[flow_quality_columns].mean(axis=1).clip(lower=0.0, upper=1.0)
    panel = add_margin_trade_features(panel, copy=False)
    if any(column in panel for column in ("dragon_tiger_count_90d", "dragon_tiger_amount_90d", "dragon_tiger_days_since_last")):
        if "dragon_tiger_count_90d" in panel:
            event_count = pd.to_numeric(panel["dragon_tiger_count_90d"], errors="coerce").fillna(0.0)
            panel["dragon_tiger_attention_score"] = (event_count.clip(lower=0.0, upper=3.0) / 3.0).clip(
                lower=0.0,
                upper=1.0,
            )
        if "dragon_tiger_amount_90d" in panel:
            panel["dragon_tiger_amount_score"] = _cross_section_pct_rank(panel, "dragon_tiger_amount_90d")
        if "dragon_tiger_days_since_last" in panel:
            days_since = pd.to_numeric(panel["dragon_tiger_days_since_last"], errors="coerce")
            panel["dragon_tiger_recency_score"] = (1.0 - days_since.clip(lower=0.0, upper=90.0) / 90.0).fillna(0.0)
        attention = (
            pd.to_numeric(panel["dragon_tiger_attention_score"], errors="coerce").fillna(0.0)
            if "dragon_tiger_attention_score" in panel
            else pd.Series(0.0, index=panel.index)
        )
        recency = (
            pd.to_numeric(panel["dragon_tiger_recency_score"], errors="coerce").fillna(0.0)
            if "dragon_tiger_recency_score" in panel
            else pd.Series(0.0, index=panel.index)
        )
        deviation = (
            pd.to_numeric(panel["dragon_tiger_max_deviation_90d"], errors="coerce").abs().clip(lower=0.0, upper=15.0) / 15.0
            if "dragon_tiger_max_deviation_90d" in panel
            else pd.Series(0.0, index=panel.index)
        )
        panel["dragon_tiger_cooldown_score"] = (1.0 - (0.55 * attention * recency + 0.45 * deviation * recency)).clip(
            lower=0.0,
            upper=1.0,
        )
        dragon_tiger_columns = [
            column
            for column in (
                "dragon_tiger_attention_score",
                "dragon_tiger_amount_score",
                "dragon_tiger_recency_score",
            )
            if column in panel
        ]
        if dragon_tiger_columns:
            panel["dragon_tiger_event_score"] = panel[dragon_tiger_columns].mean(axis=1).clip(lower=0.0, upper=1.0)
    if any(column.startswith("announcement_") for column in panel.columns):
        if "announcement_count_90d" in panel:
            event_count_90d = pd.to_numeric(panel["announcement_count_90d"], errors="coerce").fillna(0.0)
            panel["announcement_activity_score"] = (event_count_90d.clip(lower=0.0, upper=8.0) / 8.0).clip(
                lower=0.0,
                upper=1.0,
            )
        if "announcement_days_since_last" in panel:
            days_since = pd.to_numeric(panel["announcement_days_since_last"], errors="coerce")
            panel["announcement_recency_score"] = (1.0 - days_since.clip(lower=0.0, upper=90.0) / 90.0).fillna(0.0)
        if "announcement_count_30d" in panel:
            short_count = pd.to_numeric(panel["announcement_count_30d"], errors="coerce").fillna(0.0)
            panel["announcement_noise_guard_score"] = (1.0 - short_count.clip(lower=0.0, upper=10.0) / 10.0).clip(
                lower=0.0,
                upper=1.0,
            )
        if "announcement_buyback_count_180d" in panel:
            buyback_count = pd.to_numeric(panel["announcement_buyback_count_180d"], errors="coerce").fillna(0.0)
            panel["announcement_buyback_activity_score"] = (buyback_count.clip(lower=0.0, upper=2.0) / 2.0).clip(
                lower=0.0,
                upper=1.0,
            )
        if "announcement_dividend_count_365d" in panel:
            dividend_count = pd.to_numeric(panel["announcement_dividend_count_365d"], errors="coerce").fillna(0.0)
            panel["announcement_shareholder_return_score"] = (dividend_count.clip(lower=0.0, upper=3.0) / 3.0).clip(
                lower=0.0,
                upper=1.0,
            )
        if "announcement_risk_alert_count_365d" in panel:
            risk_count = pd.to_numeric(panel["announcement_risk_alert_count_365d"], errors="coerce").fillna(0.0)
            panel["announcement_risk_alert_guard_score"] = (1.0 - risk_count.clip(lower=0.0, upper=3.0) / 3.0).clip(
                lower=0.0,
                upper=1.0,
            )
        if "announcement_financing_count_365d" in panel:
            financing_count = pd.to_numeric(panel["announcement_financing_count_365d"], errors="coerce").fillna(0.0)
            panel["announcement_financing_cooldown_score"] = (
                1.0 - financing_count.clip(lower=0.0, upper=4.0) / 4.0
            ).clip(lower=0.0, upper=1.0)
        if "announcement_reorg_count_365d" in panel:
            reorg_count = pd.to_numeric(panel["announcement_reorg_count_365d"], errors="coerce").fillna(0.0)
            panel["announcement_reorg_cooldown_score"] = (1.0 - reorg_count.clip(lower=0.0, upper=3.0) / 3.0).clip(
                lower=0.0,
                upper=1.0,
            )
        stability_columns = [
            column
            for column in (
                "announcement_noise_guard_score",
                "announcement_risk_alert_guard_score",
                "announcement_financing_cooldown_score",
                "announcement_reorg_cooldown_score",
            )
            if column in panel
        ]
        if stability_columns:
            panel["announcement_stability_guard_score"] = panel[stability_columns].mean(axis=1).clip(lower=0.0, upper=1.0)
        event_columns = [
            column
            for column in (
                "announcement_activity_score",
                "announcement_recency_score",
                "announcement_buyback_activity_score",
                "announcement_shareholder_return_score",
            )
            if column in panel
        ]
        if event_columns:
            panel["announcement_event_score"] = panel[event_columns].mean(axis=1).clip(lower=0.0, upper=1.0)
    if "pe" in panel:
        pe = pd.to_numeric(panel["pe"], errors="coerce")
        panel["pe_sane"] = pe.where(pe.between(0.0, 80.0, inclusive="neither"))
        panel["pe_valid_score"] = pe.between(0.0, 80.0, inclusive="neither").astype(float)
    if "pb" in panel:
        pb = pd.to_numeric(panel["pb"], errors="coerce")
        panel["pb_sane"] = pb.where(pb.between(0.1, 20.0, inclusive="both"))
        panel["pb_valid_score"] = pb.between(0.1, 20.0, inclusive="both").astype(float)
    if "roe" in panel:
        roe = pd.to_numeric(panel["roe"], errors="coerce")
        panel["roe_sane"] = roe.clip(lower=-0.30, upper=0.40).where(roe.between(-0.50, 0.60, inclusive="both"))
        panel["roe_positive_score"] = (roe > 0.0).astype(float)
        panel["roe_delta_252d"] = panel.groupby("symbol")["roe_sane"].diff(252)
        panel["roe_repair_score"] = ((panel["roe_sane"] > 0.0) & (panel["roe_delta_252d"] > 0.0)).astype(float)
    if "gross_margin" in panel:
        gross_margin = pd.to_numeric(panel["gross_margin"], errors="coerce")
        panel["gross_margin_sane"] = gross_margin.where(gross_margin.between(-0.20, 0.95, inclusive="both"))
        panel["gross_margin_score"] = gross_margin.clip(lower=0.0, upper=0.65) / 0.65
    if "net_margin" in panel:
        net_margin = pd.to_numeric(panel["net_margin"], errors="coerce")
        panel["net_margin_sane"] = net_margin.where(net_margin.between(-0.50, 0.60, inclusive="both"))
        panel["net_margin_score"] = net_margin.clip(lower=0.0, upper=0.35) / 0.35
    if "roic" in panel:
        roic = pd.to_numeric(panel["roic"], errors="coerce")
        panel["roic_sane"] = roic.where(roic.between(-0.50, 0.80, inclusive="both"))
        panel["roic_score"] = roic.clip(lower=0.0, upper=0.30) / 0.30
    if "rev_growth_1y" in panel:
        rev_growth = pd.to_numeric(panel["rev_growth_1y"], errors="coerce")
        panel["rev_growth_1y_sane"] = rev_growth.where(rev_growth.between(-0.80, 2.00, inclusive="both"))
        panel["rev_growth_score"] = ((rev_growth.clip(lower=-0.20, upper=0.60) + 0.20) / 0.80).where(rev_growth.notna())
    if "np_growth_1y" in panel:
        np_growth = pd.to_numeric(panel["np_growth_1y"], errors="coerce")
        panel["np_growth_1y_sane"] = np_growth.where(np_growth.between(-1.00, 3.00, inclusive="both"))
        panel["np_growth_score"] = ((np_growth.clip(lower=-0.30, upper=0.80) + 0.30) / 1.10).where(np_growth.notna())
    if "cfo_growth_1y" in panel:
        cfo_growth = pd.to_numeric(panel["cfo_growth_1y"], errors="coerce")
        panel["cfo_growth_1y_sane"] = cfo_growth.where(cfo_growth.between(-2.00, 5.00, inclusive="both"))
        panel["cfo_growth_score"] = ((cfo_growth.clip(lower=-0.50, upper=1.00) + 0.50) / 1.50).where(cfo_growth.notna())
    if "ocf_to_net_profit_ratio" in panel:
        ocf_profit = pd.to_numeric(panel["ocf_to_net_profit_ratio"], errors="coerce")
        panel["ocf_to_net_profit_sane"] = ocf_profit.where(ocf_profit.between(-5.00, 8.00, inclusive="both"))
        panel["ocf_to_net_profit_score"] = ocf_profit.clip(lower=0.0, upper=2.0) / 2.0
    if "cfo_to_revenue" in panel:
        cfo_revenue = pd.to_numeric(panel["cfo_to_revenue"], errors="coerce")
        panel["cfo_to_revenue_sane"] = cfo_revenue.where(cfo_revenue.between(-1.00, 1.50, inclusive="both"))
        panel["cfo_to_revenue_score"] = cfo_revenue.clip(lower=0.0, upper=0.45) / 0.45
    if "fcf_to_equity_ps" in panel:
        fcf_ps = pd.to_numeric(panel["fcf_to_equity_ps"], errors="coerce")
        panel["fcf_to_equity_ps_positive_score"] = (fcf_ps > 0.0).astype(float)
    if "cash_debt_ratio" in panel:
        cash_debt = pd.to_numeric(panel["cash_debt_ratio"], errors="coerce")
        panel["cash_debt_ratio_sane"] = cash_debt.where(cash_debt.between(0.0, 10.0, inclusive="both"))
        panel["cash_debt_ratio_score"] = cash_debt.clip(lower=0.0, upper=3.0) / 3.0
    if "debt_asset_ratio" in panel:
        debt_asset = pd.to_numeric(panel["debt_asset_ratio"], errors="coerce")
        panel["debt_asset_ratio_sane"] = debt_asset.where(debt_asset.between(0.0, 1.2, inclusive="both"))
        panel["low_debt_score"] = (1.0 - debt_asset.clip(lower=0.0, upper=0.90) / 0.90).where(debt_asset.notna())
    if "f_score" in panel:
        f_score = pd.to_numeric(panel["f_score"], errors="coerce")
        panel["f_score_sane"] = f_score.where(f_score.between(0.0, 9.0, inclusive="both"))
        panel["f_score_quality_score"] = f_score.clip(lower=0.0, upper=9.0) / 9.0
    margin_columns = [column for column in ("gross_margin_score", "net_margin_score", "roic_score") if column in panel]
    if margin_columns:
        panel["profitability_quality_score"] = panel[margin_columns].mean(axis=1)
    growth_columns = [column for column in ("rev_growth_score", "np_growth_score", "cfo_growth_score") if column in panel]
    if growth_columns:
        panel["growth_quality_score"] = panel[growth_columns].mean(axis=1)
    cashflow_columns = [
        column
        for column in ("ocf_to_net_profit_score", "cfo_to_revenue_score", "fcf_to_equity_ps_positive_score")
        if column in panel
    ]
    if cashflow_columns:
        panel["cashflow_quality_score"] = panel[cashflow_columns].mean(axis=1)
    balance_columns = [column for column in ("cash_debt_ratio_score", "low_debt_score", "f_score_quality_score") if column in panel]
    if balance_columns:
        panel["balance_sheet_quality_score"] = panel[balance_columns].mean(axis=1)
    if "momentum_20d" in panel:
        momentum_20d = pd.to_numeric(panel["momentum_20d"], errors="coerce")
        panel["momentum_20d_positive_score"] = (momentum_20d > 0.0).astype(float)
    if "momentum_60d" in panel:
        momentum_60d = pd.to_numeric(panel["momentum_60d"], errors="coerce")
        panel["momentum_60d_positive_score"] = (momentum_60d > 0.0).astype(float)
    if "momentum_120d" in panel:
        momentum_120d = pd.to_numeric(panel["momentum_120d"], errors="coerce")
        panel["momentum_120d_positive_score"] = (momentum_120d > 0.0).astype(float)
    if "momentum_252d" in panel:
        momentum_252d = pd.to_numeric(panel["momentum_252d"], errors="coerce")
        panel["momentum_252d_positive_score"] = (momentum_252d > 0.0).astype(float)
    if "amount" in panel:
        amount_rank = _cross_section_pct_rank(panel, "amount")
        panel["liquidity_mid_score"] = (1.0 - (amount_rank - 0.62).abs() / 0.62).clip(lower=0.0, upper=1.0)
        panel["liquidity_top_penalty_score"] = (1.0 - amount_rank.clip(lower=0.0, upper=1.0)).clip(lower=0.0, upper=1.0)
        panel["_amount_rank_for_risk"] = amount_rank
    if "turnover" in panel:
        turnover = pd.to_numeric(panel["turnover"], errors="coerce")
        turnover_rank = _cross_section_pct_rank(panel, "turnover")
        panel["turnover_sane_score"] = turnover.between(0.002, 0.08, inclusive="both").astype(float)
        panel["turnover_mid_score"] = (1.0 - (turnover_rank - 0.55).abs() / 0.55).clip(lower=0.0, upper=1.0)
    if {"momentum_20d", "momentum_60d", "drawdown_120d"}.issubset(panel.columns):
        momentum_20d = pd.to_numeric(panel["momentum_20d"], errors="coerce")
        momentum_60d = pd.to_numeric(panel["momentum_60d"], errors="coerce")
        drawdown = pd.to_numeric(panel["drawdown_120d"], errors="coerce")
        panel["trend_confirmation_score"] = (
            (momentum_20d > 0.0)
            & (momentum_60d > 0.0)
            & (momentum_20d < 0.35)
            & (drawdown > -0.30)
        ).astype(float)
        panel["anti_chase_score"] = (momentum_20d.between(-0.08, 0.25, inclusive="both") & (drawdown > -0.35)).astype(float)
    if {"momentum_60d", "momentum_120d", "drawdown_252d", "trend_persistence_120d", "close_to_ma_60d"}.issubset(
        panel.columns
    ):
        momentum_60d = pd.to_numeric(panel["momentum_60d"], errors="coerce")
        momentum_120d = pd.to_numeric(panel["momentum_120d"], errors="coerce")
        momentum_252d = (
            pd.to_numeric(panel["momentum_252d"], errors="coerce")
            if "momentum_252d" in panel
            else pd.Series(float("nan"), index=panel.index, dtype="float64")
        )
        drawdown_252d = pd.to_numeric(panel["drawdown_252d"], errors="coerce")
        persistence_120d = pd.to_numeric(panel["trend_persistence_120d"], errors="coerce")
        close_to_ma_60d = pd.to_numeric(panel["close_to_ma_60d"], errors="coerce")
        trend_components = pd.DataFrame(
            {
                "momentum_60d": ((momentum_60d.clip(lower=-0.10, upper=0.30) + 0.10) / 0.40),
                "momentum_120d": ((momentum_120d.clip(lower=-0.15, upper=0.45) + 0.15) / 0.60),
                "momentum_252d": ((momentum_252d.clip(lower=-0.20, upper=0.60) + 0.20) / 0.80),
                "drawdown_252d": (1.0 + drawdown_252d.clip(lower=-0.45, upper=0.0) / 0.45),
                "persistence_120d": ((persistence_120d.clip(lower=0.40, upper=0.64) - 0.40) / 0.24),
                "close_to_ma_60d": ((close_to_ma_60d.clip(lower=-0.12, upper=0.18) + 0.12) / 0.30),
            },
            index=panel.index,
        )
        panel["long_trend_quality_score"] = trend_components.mean(axis=1).clip(lower=0.0, upper=1.0)
    if "volatility_downside_60d" in panel:
        downside_volatility_rank = _cross_section_pct_rank(panel, "volatility_downside_60d")
        panel["downside_volatility_score"] = (1.0 - downside_volatility_rank.clip(lower=0.0, upper=1.0)).clip(
            lower=0.0,
            upper=1.0,
        )
    if {"momentum_20d", "momentum_120d", "drawdown_252d"}.issubset(panel.columns):
        momentum_20d = pd.to_numeric(panel["momentum_20d"], errors="coerce")
        momentum_120d = pd.to_numeric(panel["momentum_120d"], errors="coerce")
        drawdown_252d = pd.to_numeric(panel["drawdown_252d"], errors="coerce")
        chase_risk = ((momentum_20d - 0.25).clip(lower=0.0, upper=0.35) / 0.35).fillna(0.0)
        deep_drawdown_risk = (-drawdown_252d.clip(lower=-0.55, upper=0.0) / 0.55).fillna(0.0)
        long_negative_risk = (-momentum_120d.clip(lower=-0.30, upper=0.0) / 0.30).fillna(0.0)
        panel["reversal_risk_guard_score"] = (
            1.0 - (0.45 * chase_risk + 0.35 * deep_drawdown_risk + 0.20 * long_negative_risk)
        ).clip(lower=0.0, upper=1.0)
    if "volatility_60d" in panel:
        volatility_rank = _cross_section_pct_rank(panel, "volatility_60d")
        panel["low_volatility_score"] = (1.0 - volatility_rank.clip(lower=0.0, upper=1.0)).clip(lower=0.0, upper=1.0)
        panel["_volatility_rank_for_risk"] = volatility_rank
    if {"_amount_rank_for_risk", "_volatility_rank_for_risk"}.issubset(panel.columns):
        amount_risk = pd.to_numeric(panel["_amount_rank_for_risk"], errors="coerce").fillna(0.5)
        volatility_risk = pd.to_numeric(panel["_volatility_rank_for_risk"], errors="coerce").fillna(0.5)
        momentum_risk = (
            pd.to_numeric(panel["momentum_20d"], errors="coerce").clip(lower=0.0, upper=0.35) / 0.35
            if "momentum_20d" in panel
            else pd.Series(0.0, index=panel.index)
        )
        drawdown_risk = (
            (-pd.to_numeric(panel["drawdown_120d"], errors="coerce").clip(lower=-0.50, upper=0.0) / 0.50)
            if "drawdown_120d" in panel
            else pd.Series(0.0, index=panel.index)
        )
        risk = 0.35 * amount_risk + 0.35 * volatility_risk + 0.15 * momentum_risk + 0.15 * drawdown_risk
        panel["liquidity_exposure_guard_score"] = (1.0 - risk).clip(lower=0.0, upper=1.0)
        panel["single_name_risk_guard_score"] = (
            0.45 * panel["low_volatility_score"].fillna(0.5)
            + 0.35 * panel["liquidity_exposure_guard_score"].fillna(0.5)
            + 0.20 * (1.0 - drawdown_risk).clip(lower=0.0, upper=1.0)
        ).clip(lower=0.0, upper=1.0)
    scratch_columns = [column for column in ("_amount_rank_for_risk", "_volatility_rank_for_risk") if column in panel]
    if scratch_columns:
        panel.drop(columns=scratch_columns, inplace=True)
    valid_score_columns = [column for column in ("pe_valid_score", "pb_valid_score", "dividend_yield_valid_score") if column in panel]
    if valid_score_columns:
        panel["valuation_sanity_score"] = panel[valid_score_columns].mean(axis=1)
    price_stability_columns = [
        column
        for column in (
            "long_trend_quality_score",
            "downside_volatility_score",
            "reversal_risk_guard_score",
            "trend_confirmation_score",
            "anti_chase_score",
        )
        if column in panel
    ]
    if price_stability_columns:
        panel["price_trend_stability_score"] = panel[price_stability_columns].mean(axis=1)
    quality_columns = [
        column
        for column in (
            "roe_positive_score",
            "roe_repair_score",
            "valuation_sanity_score",
            "dividend_event_quality_score",
            "trend_confirmation_score",
            "turnover_sane_score",
            "liquidity_mid_score",
            "profitability_quality_score",
            "growth_quality_score",
            "cashflow_quality_score",
            "balance_sheet_quality_score",
            "margin_trade_quality_score",
            "announcement_stability_guard_score",
        )
        if column in panel
    ]
    if quality_columns:
        panel["alpha_quality_stability_score"] = panel[quality_columns].mean(axis=1)
    panel = _add_market_alpha_health_features(panel)
    return panel


def _cross_section_pct_rank(panel: pd.DataFrame, field: str) -> pd.Series:
    values = pd.to_numeric(panel[field], errors="coerce")
    return values.groupby(panel["date"]).rank(pct=True)


def _add_market_alpha_health_features(panel: pd.DataFrame) -> pd.DataFrame:
    if "date" not in panel or panel.empty:
        return panel
    dates = pd.DatetimeIndex(sorted(panel["date"].dropna().unique()))
    if dates.empty:
        return panel

    features = pd.DataFrame(index=dates)
    if "momentum_20d" in panel:
        features["market_breadth_20d"] = _daily_share(panel, "momentum_20d", threshold=0.0)
    if "momentum_60d" in panel:
        features["market_breadth_60d"] = _daily_share(panel, "momentum_60d", threshold=0.0)
    if "momentum_120d" in panel:
        features["market_breadth_120d"] = _daily_share(panel, "momentum_120d", threshold=0.0)
    if "close_to_ma_60d" in panel:
        features["market_above_ma60_share"] = _daily_share(panel, "close_to_ma_60d", threshold=0.0)
    if "drawdown_120d" in panel:
        features["market_drawdown_ok_share"] = _daily_share(panel, "drawdown_120d", threshold=-0.20)
    for field in (
        "price_trend_stability_score",
        "downside_volatility_score",
        "liquidity_exposure_guard_score",
        "single_name_risk_guard_score",
        "alpha_quality_stability_score",
    ):
        if field in panel:
            features[f"market_{field}_median"] = (
                pd.to_numeric(panel[field], errors="coerce").groupby(panel["date"]).median().reindex(dates)
            )
    health_inputs = [
        column
        for column in (
            "market_breadth_60d",
            "market_breadth_120d",
            "market_above_ma60_share",
            "market_drawdown_ok_share",
            "market_price_trend_stability_score_median",
            "market_downside_volatility_score_median",
            "market_liquidity_exposure_guard_score_median",
            "market_single_name_risk_guard_score_median",
            "market_alpha_quality_stability_score_median",
        )
        if column in features
    ]
    if health_inputs:
        features["market_alpha_health_score"] = features[health_inputs].mean(axis=1).clip(lower=0.0, upper=1.0)

    lagged = features.shift(1)
    for column in features.columns:
        panel[column] = panel["date"].map(features[column]).astype("float32")
        panel[f"{column}_lag1"] = panel["date"].map(lagged[column]).astype("float32")
    return panel


def _daily_share(panel: pd.DataFrame, field: str, *, threshold: float) -> pd.Series:
    values = pd.to_numeric(panel[field], errors="coerce")
    passed = (values > threshold).where(values.notna())
    return passed.groupby(panel["date"]).mean()


def add_market_regime_features(
    data: pd.DataFrame,
    benchmark_quotes: pd.DataFrame,
    fields: Iterable[str] | None = None,
) -> pd.DataFrame:
    if data.empty or benchmark_quotes is None or benchmark_quotes.empty:
        return data.copy()

    panel = data.copy(deep=False)
    if not pd.api.types.is_datetime64_any_dtype(panel["date"]):
        panel = panel.copy()
        panel["date"] = pd.to_datetime(panel["date"])
    benchmark = benchmark_quotes.copy()
    benchmark["date"] = pd.to_datetime(benchmark["date"], errors="coerce")
    price_column = "closePrice" if "closePrice" in benchmark else "close"
    if price_column not in benchmark:
        raise DataSourceError("Benchmark quotes require closePrice or close for market regime features.")
    benchmark[price_column] = pd.to_numeric(benchmark[price_column], errors="coerce")
    benchmark = benchmark.dropna(subset=["date", price_column]).sort_values("date").drop_duplicates("date", keep="last")
    if benchmark.empty:
        return panel

    close = benchmark[price_column]
    daily_return = close.pct_change(fill_method=None)
    ma_120 = close.rolling(120, min_periods=60).mean()
    ma_200 = close.rolling(200, min_periods=120).mean()
    vol_60 = daily_return.rolling(60, min_periods=30).std()
    close_lag = close.shift(1)
    ma_120_lag = ma_120.shift(1)
    ma_200_lag = ma_200.shift(1)
    trend_120 = (close_lag > ma_120_lag).astype(float).where(close_lag.notna() & ma_120_lag.notna())
    trend_200 = (close_lag > ma_200_lag).astype(float).where(close_lag.notna() & ma_200_lag.notna())
    features = pd.DataFrame(
        {
            "date": benchmark["date"],
            "benchmark_close_lag1": close_lag,
            "benchmark_ma_120d_lag1": ma_120_lag,
            "benchmark_ma_200d_lag1": ma_200_lag,
            "benchmark_trend_120d_lag1": trend_120,
            "benchmark_trend_200d_lag1": trend_200,
            "benchmark_momentum_20d_lag1": close.pct_change(20, fill_method=None).shift(1),
            "benchmark_momentum_60d_lag1": close.pct_change(60, fill_method=None).shift(1),
            "benchmark_momentum_120d_lag1": close.pct_change(120, fill_method=None).shift(1),
            "benchmark_volatility_60d_lag1": vol_60.shift(1),
            "benchmark_volatility_60d_q80_lag1": vol_60.rolling(252, min_periods=120).quantile(0.80).shift(1),
        }
    )
    requested = set(fields or [column for column in features.columns if column != "date"])
    feature_columns = [column for column in features.columns if column != "date" and column in requested]
    if not feature_columns:
        return panel

    unique_dates = pd.DatetimeIndex(sorted(panel["date"].dropna().unique()))
    feature_by_date = features.set_index("date").sort_index().reindex(unique_dates, method="ffill")
    for column in feature_columns:
        mapped = panel["date"].map(feature_by_date[column])
        panel[column] = pd.to_numeric(mapped, errors="coerce").astype("float32")
    return panel


def validate_strategy_data(data: pd.DataFrame, spec: StrategySpec) -> None:
    missing = sorted({factor.field for factor in spec.factors if factor.field not in data.columns})
    if missing:
        raise DataSourceError(
            "Data source lacks required factor fields: "
            + ", ".join(missing)
            + ". Use a technical-factor idea, Tushare daily_basic fields, or provide a CSV with these columns."
        )
    overlay_missing = sorted(field for field in required_risk_overlay_fields(spec) if field not in data.columns)
    if overlay_missing:
        raise DataSourceError(
            "Data source lacks required risk overlay fields: "
            + ", ".join(overlay_missing)
            + ". Run with --benchmark-code so market regime features can be merged."
        )


def required_risk_overlay_fields(spec: StrategySpec) -> list[str]:
    overlay = spec.risk.risk_overlay
    if not overlay.enabled:
        return []
    fields = []
    if overlay.use_trend:
        fields.append(overlay.trend_field)
    if overlay.use_momentum:
        fields.append(overlay.momentum_field)
    if overlay.use_volatility:
        fields.extend([overlay.volatility_field, overlay.volatility_threshold_field])
    if overlay.use_recovery:
        fields.append(overlay.recovery_field)
    if overlay.use_staged_recovery:
        fields.append(overlay.staged_recovery_field)
    if overlay.use_window_fuse and overlay.fuse_reentry_requires_market_recovery:
        fields.append(overlay.fuse_reentry_field)
    if overlay.use_window_fuse and overlay.fuse_reentry_requires_volatility_calm:
        fields.extend([overlay.fuse_reentry_volatility_field, overlay.fuse_reentry_volatility_threshold_field])
    if overlay.use_high_vol_uptrend_guard:
        fields.extend(
            [
                overlay.high_vol_uptrend_trend_field,
                overlay.high_vol_uptrend_volatility_field,
                overlay.high_vol_uptrend_threshold_field,
            ]
        )
        if overlay.high_vol_uptrend_requires_positive_momentum:
            fields.append(overlay.high_vol_uptrend_momentum_field)
    if overlay.use_uptrend_tail_guard:
        fields.extend([overlay.uptrend_tail_trend_field, overlay.uptrend_tail_momentum_field])
    if overlay.use_window_fuse and overlay.use_downtrend_loss_cluster_fuse:
        fields.extend([overlay.downtrend_fuse_trend_field, overlay.downtrend_fuse_recovery_field])
    if overlay.use_alpha_health_filter:
        fields.append(overlay.alpha_health_field)
    if overlay.use_market_breadth_filter:
        fields.append(overlay.market_breadth_field)
    if overlay.use_overheated_reversal_guard:
        fields.extend(
            [
                overlay.overheated_alpha_health_field,
                overlay.overheated_breadth_field,
                overlay.overheated_momentum_field,
            ]
        )
    return [field for field in dict.fromkeys(fields) if field]


def _normalize_common_columns(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.rename(
        columns={
            "日期": "date",
            "代码": "symbol",
            "股票代码": "symbol",
            "ts_code": "symbol",
            "trade_date": "date",
            "tradeDate": "date",
            "stockCode": "symbol",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "openPrice": "open",
            "highPrice": "high",
            "lowPrice": "low",
            "closePrice": "close",
            "成交量": "volume",
            "成交额": "amount",
            "vol": "volume",
            "dv_ratio": "dividend_yield",
            "peTtm": "pe",
        }
    ).copy()
    required = {"date", "symbol", "open", "high", "low", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise DataSourceError(f"Market data missing required columns: {sorted(missing)}")

    frame["date"] = pd.to_datetime(frame["date"].astype(str))
    frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    for column in ("open", "high", "low", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "volume" in frame:
        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce").fillna(0.0)
    else:
        frame["volume"] = 0.0
    if "amount" in frame:
        frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce").fillna(0.0)
    else:
        frame["amount"] = frame["volume"] * frame["close"]
    if "is_st" not in frame:
        frame["is_st"] = False
    if "is_suspended" not in frame:
        frame["is_suspended"] = False
    for column in ("is_limit_up", "is_limit_down"):
        if column in frame:
            frame[column] = frame[column].where(frame[column].notna(), False).infer_objects(copy=False).astype(bool)
        else:
            frame[column] = False
    if "dividend_yield" in frame:
        frame["dividend_yield"] = _normalize_yield_series(pd.to_numeric(frame["dividend_yield"], errors="coerce"))
    for column in ("pe", "pb", "roe"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["date", "symbol", "close"])


def _align_symbol_dates(data: pd.DataFrame) -> pd.DataFrame:
    all_dates = pd.DatetimeIndex(sorted(data["date"].unique()))
    frames: list[pd.DataFrame] = []
    for symbol, group in data.groupby("symbol"):
        group = group.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
        reindexed = group.reindex(all_dates)
        traded = reindexed["close"].notna()
        reindexed["symbol"] = symbol
        for column in ("close", "open", "high", "low"):
            reindexed[column] = reindexed[column].ffill()
        reindexed["open"] = reindexed["open"].fillna(reindexed["close"])
        reindexed["high"] = reindexed["high"].fillna(reindexed["close"])
        reindexed["low"] = reindexed["low"].fillna(reindexed["close"])
        reindexed["volume"] = reindexed["volume"].where(traded, 0.0).fillna(0.0)
        reindexed["amount"] = reindexed["amount"].where(traded, 0.0).fillna(0.0)
        reindexed["is_suspended"] = (~traded) | _bool_column(reindexed, "is_suspended")
        reindexed["is_st"] = _bool_column(reindexed, "is_st", ffill=True)
        for column in ("is_limit_up", "is_limit_down"):
            reindexed[column] = _bool_column(reindexed, column).where(traded, False).astype(bool)
        for column in ("pe", "pb", "roe", "dividend_yield"):
            if column in reindexed:
                reindexed[column] = reindexed[column].ffill()

        reindexed = reindexed[reindexed["close"].notna()].copy()
        previous_close = reindexed["close"].shift(1)
        reindexed["limit_up"] = reindexed.get("limit_up", previous_close * 1.10)
        reindexed["limit_down"] = reindexed.get("limit_down", previous_close * 0.90)
        reindexed["limit_up"] = reindexed["limit_up"].fillna(previous_close * 1.10)
        reindexed["limit_down"] = reindexed["limit_down"].fillna(previous_close * 0.90)
        reindexed["date"] = reindexed.index
        frames.append(reindexed.reset_index(drop=True))

    if not frames:
        raise DataSourceError("No market data available after alignment.")
    return pd.concat(frames, ignore_index=True)


def _normalize_akshare_hist(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
    frame = raw.copy()
    frame["symbol"] = symbol
    return frame


def _normalize_tushare_daily(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    frame["date"] = pd.to_datetime(frame["trade_date"].astype(str))
    frame["symbol"] = frame["ts_code"]
    frame["volume"] = pd.to_numeric(frame["vol"], errors="coerce") * 100.0
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce") * 1000.0
    return frame[["date", "symbol", "open", "high", "low", "close", "volume", "amount"]]


def _bool_column(frame: pd.DataFrame, column: str, default: bool = False, ffill: bool = False) -> pd.Series:
    if column not in frame:
        return pd.Series(default, index=frame.index, dtype=bool)
    values = frame[column].astype("boolean")
    if ffill:
        values = values.ffill()
    return values.fillna(default).astype(bool)


def _normalize_tushare_basic(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    frame["date"] = pd.to_datetime(frame["trade_date"].astype(str))
    frame["symbol"] = frame["ts_code"]
    columns = ["date", "symbol"]
    for column in ("pe", "pb", "dv_ratio"):
        if column in frame:
            columns.append(column)
    return frame[columns].rename(columns={"dv_ratio": "dividend_yield"})


def _normalize_investoday_adjusted_quotes(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    if "tradeDate" not in frame and "date" in frame:
        frame["tradeDate"] = frame["date"]
    frame["date"] = pd.to_datetime(frame["tradeDate"].astype(str))
    frame["symbol"] = frame["stockCode"].map(_normalize_symbol)
    if "isTrading" in frame:
        frame["is_suspended"] = pd.to_numeric(frame["isTrading"], errors="coerce").fillna(0).astype(int) != 1
    if "stockName" in frame:
        frame["is_st"] = frame["stockName"].astype(str).str.upper().str.contains("ST", na=False)
    keep_columns = [
        "date",
        "symbol",
        "stockName",
        "is_st",
        "openPrice",
        "highPrice",
        "lowPrice",
        "closePrice",
        "volume",
        "amount",
        "turnover",
        "marketCapFloat",
        "marketCap",
        "changePct",
        "peTtm",
        "pb",
        "vwap",
        "is_suspended",
    ]
    return frame[[column for column in keep_columns if column in frame.columns]]


def _normalize_investoday_realtime_universe(
    raw: pd.DataFrame,
    sort_column: str,
    order: str,
) -> pd.DataFrame:
    frame = raw.copy()
    market_series = frame["marketType"] if "marketType" in frame else pd.Series("", index=frame.index)
    frame["symbol"] = [
        _normalize_symbol_with_market(stock_code, market)
        for stock_code, market in zip(frame["stockCode"], market_series)
    ]
    if "stockName" in frame:
        frame["stockName"] = frame["stockName"].astype(str)
    else:
        frame["stockName"] = ""
    frame["is_st"] = frame["stockName"].str.upper().str.contains("ST", na=False)
    frame["marketType"] = market_series.astype(str).str.upper()
    numeric_columns = [
        "currentPrice",
        "changeRatio",
        "dealStockAmount",
        "dealMoney",
        "turnOverRate",
        "circulationValue",
        "totalValue",
        "changeRatio1W",
        "changeRatioB10D",
        "dealMoney1W",
        "dealStockAmount1W",
        "_universe_page",
        "_universe_rank",
    ]
    for column in numeric_columns:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if sort_column in frame:
        frame.sort_values(sort_column, ascending=order == "asc", inplace=True, na_position="last")
    elif "_universe_rank" in frame:
        frame.sort_values("_universe_rank", inplace=True)

    keep_columns = [
        "symbol",
        "stockCode",
        "stockName",
        "marketType",
        "currentPrice",
        "changeRatio",
        "dealStockAmount",
        "dealMoney",
        "turnOverRate",
        "circulationValue",
        "totalValue",
        "industryLV1Name",
        "industryName",
        "dataTime",
        "is_st",
        "_universe_page",
        "_universe_rank",
    ]
    return frame[[column for column in keep_columns if column in frame.columns]].copy()


def _normalize_investoday_stock_basic_info(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    market_series = frame["exchangeCode"] if "exchangeCode" in frame else pd.Series("", index=frame.index)
    frame["symbol"] = [
        _normalize_symbol_with_market(stock_code, market)
        for stock_code, market in zip(frame["stockCode"], market_series)
    ]
    if "exchangeCode" in frame:
        frame["exchangeCode"] = frame["exchangeCode"].astype(str).str.upper()
    for column in ("stockName", "stockFullName", "boardName", "stockType", "companyId", "listStatus"):
        if column in frame:
            frame[column] = frame[column].astype(str)
    for column in ("listDate", "delistDate", "reportDate"):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    for column in ("boardCode", "sharesTotal", "sharesFloat", "sharesFloatA", "companyGrowthStage"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    keep_columns = [
        "symbol",
        "stockCode",
        "exchangeCode",
        "boardCode",
        "boardName",
        "stockName",
        "stockFullName",
        "listStatus",
        "listDate",
        "delistDate",
        "stockType",
        "companyId",
        "sharesTotal",
        "sharesFloat",
        "sharesFloatA",
        "reportDate",
        "companyGrowthStage",
    ]
    return frame[[column for column in keep_columns if column in frame.columns]].drop_duplicates("symbol", keep="first")


def _normalize_external_stock_master(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    aliases = {
        # QData public API / CSV export fields.
        "name": "stockName",
        "asset_type": "stockType",
        "exchange": "exchangeCode",
        "list_date": "listDate",
        "delist_date": "delistDate",
        "status": "listStatus",
        # QData SQL security-master field names.
        "current_symbol": "stockCode",
        "current_name": "stockName",
        "current_status": "listStatus",
        "exchange_code": "exchangeCode",
        # Existing external aliases.
        "股票代码": "stockCode",
        "证券代码": "stockCode",
        "代码": "stockCode",
        "股票名称": "stockName",
        "证券简称": "stockName",
        "证券名称": "stockName",
        "股票全称": "stockFullName",
        "证券全称": "stockFullName",
        "交易所": "exchangeCode",
        "市场": "exchangeCode",
        "市场类型": "exchangeCode",
        "上市板块": "boardName",
        "板块": "boardName",
        "上市状态": "listStatus",
        "上市日期": "listDate",
        "退市日期": "delistDate",
        "摘牌日期": "delistDate",
        "股票类别": "stockType",
        "证券类别": "stockType",
        "总股本": "sharesTotal",
        "流通股本": "sharesFloat",
        "A股流通股本": "sharesFloatA",
        "财务报告日期": "reportDate",
        "最新报告期": "reportDate",
    }
    for source, target in aliases.items():
        if source not in frame:
            continue
        if target in frame and source != target:
            frame[target] = frame[target].where(frame[target].notna(), frame[source])
            frame.drop(columns=[source], inplace=True)
        else:
            frame.rename(columns={source: target}, inplace=True)
    if "symbol" in frame:
        frame["symbol"] = frame["symbol"].map(_normalize_symbol)
        if "stockCode" in frame:
            market_series = frame["exchangeCode"] if "exchangeCode" in frame else pd.Series("", index=frame.index)
            fallback_symbols = [
                _normalize_symbol_with_market(stock_code, market)
                for stock_code, market in zip(frame["stockCode"], market_series)
            ]
            invalid_symbol = ~frame["symbol"].astype(str).str.match(r"^\d{6}\.(SH|SZ|BJ)$", na=False)
            frame.loc[invalid_symbol, "symbol"] = pd.Series(fallback_symbols, index=frame.index).loc[invalid_symbol]
    elif "stockCode" in frame:
        market_series = frame["exchangeCode"] if "exchangeCode" in frame else pd.Series("", index=frame.index)
        frame["symbol"] = [
            _normalize_symbol_with_market(stock_code, market)
            for stock_code, market in zip(frame["stockCode"], market_series)
        ]
    else:
        raise DataSourceError("Historical stock master CSV must include symbol, stockCode, 股票代码, or 证券代码.")

    frame["stockCode"] = frame["symbol"].str.split(".", n=1).str[0]
    frame["exchangeCode"] = frame["symbol"].str.split(".", n=1).str[1]
    if "stockType" not in frame:
        frame["stockType"] = "A股"
    else:
        normalized_type = frame["stockType"].where(frame["stockType"].notna(), "").astype(str).str.strip().str.upper()
        frame.loc[normalized_type.isin({"STOCK", "EQUITY", "A_SHARE", "A-SHARE", "ASHARE"}), "stockType"] = "A股"
    if "listStatus" not in frame:
        frame["listStatus"] = ""
    for column in ("stockName", "stockFullName", "boardName", "stockType", "companyId", "listStatus"):
        if column not in frame:
            frame[column] = ""
        frame[column] = frame[column].where(frame[column].notna(), "").astype(str)
    for column in ("listDate", "delistDate", "reportDate"):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
        else:
            frame[column] = pd.NaT
    for column in ("boardCode", "sharesTotal", "sharesFloat", "sharesFloatA", "companyGrowthStage"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    keep_columns = [
        "symbol",
        "stockCode",
        "exchangeCode",
        "boardCode",
        "boardName",
        "stockName",
        "stockFullName",
        "listStatus",
        "listDate",
        "delistDate",
        "stockType",
        "companyId",
        "sharesTotal",
        "sharesFloat",
        "sharesFloatA",
        "reportDate",
        "companyGrowthStage",
    ]
    return frame[[column for column in keep_columns if column in frame.columns]].dropna(subset=["symbol"]).drop_duplicates(
        "symbol", keep="first"
    )


def _normalize_investoday_index_quotes(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    frame["date"] = pd.to_datetime(frame["date"].astype(str))
    for column in ("openPrice", "highPrice", "lowPrice", "closePrice", "previousClosePrice", "volume", "tradingAmountCny"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame.sort_values(["date", "indexCode"], inplace=True)
    return frame[
        [
            column
            for column in (
                "date",
                "indexCode",
                "indexName",
                "previousClosePrice",
                "openPrice",
                "highPrice",
                "lowPrice",
                "closePrice",
                "volume",
                "tradingAmountCny",
            )
            if column in frame.columns
        ]
    ].dropna(subset=["date", "closePrice"])


def _normalize_investoday_limit_flags(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    frame["date"] = pd.to_datetime(frame["date"].astype(str))
    frame["symbol"] = frame["stockCode"].map(_normalize_symbol)
    frame["limitFlag"] = pd.to_numeric(frame["limitFlag"], errors="coerce").fillna(0).astype(int)
    frame["is_limit_up"] = frame["limitFlag"] == 1
    frame["is_limit_down"] = frame["limitFlag"] == -1
    return (
        frame.groupby(["date", "symbol"], as_index=False)
        .agg(
            is_limit_up=("is_limit_up", "max"),
            is_limit_down=("is_limit_down", "max"),
        )
        .copy()
    )


def _normalize_investoday_profitability(raw: pd.DataFrame, end: str) -> pd.DataFrame:
    frame = raw.copy()
    frame["symbol"] = frame["stockCode"].map(_normalize_symbol)
    frame["publishDate"] = pd.to_datetime(frame["publishDate"].astype(str))
    frame["reportPeriodEnd"] = pd.to_datetime(frame["reportPeriodEnd"].astype(str), errors="coerce")
    frame["roe"] = pd.to_numeric(frame["roeDiluted"], errors="coerce")
    frame = frame[frame["publishDate"] <= pd.Timestamp(_date_with_dash(end))]
    frame = frame.dropna(subset=["symbol", "publishDate", "roe"])
    frame.sort_values(["symbol", "publishDate", "reportPeriodEnd"], inplace=True)
    return frame.drop_duplicates(["symbol", "publishDate"], keep="last")[
        ["symbol", "publishDate", "reportPeriodEnd", "roe"]
    ]


def _merge_point_in_time_financials(quotes: pd.DataFrame, financials: pd.DataFrame) -> pd.DataFrame:
    if financials.empty:
        return quotes

    merged_frames: list[pd.DataFrame] = []
    for symbol, quote_group in quotes.groupby("symbol", sort=False):
        quote_sorted = quote_group.sort_values("date")
        financial_group = financials[financials["symbol"] == symbol].sort_values("publishDate")
        if financial_group.empty:
            quote_sorted = quote_sorted.copy()
            quote_sorted["roe"] = pd.NA
            merged_frames.append(quote_sorted)
            continue
        merged = pd.merge_asof(
            quote_sorted,
            financial_group[["publishDate", "reportPeriodEnd", "roe"]],
            left_on="date",
            right_on="publishDate",
            direction="backward",
        )
        merged_frames.append(merged)

    return pd.concat(merged_frames, ignore_index=True)


def _investoday_fetch_paginated(
    endpoint: str,
    base_body: dict[str, object],
    page_size: int = 500,
    cache_dir: str | Path | None = "cache/investoday_api",
    refresh_cache: bool = False,
) -> list[dict[str, object]]:
    if page_size < 1 or page_size > 500:
        raise DataSourceError("Investoday page_size must be between 1 and 500.")

    records: list[dict[str, object]] = []
    page_num = 1
    while True:
        body = dict(base_body)
        body["pageNum"] = page_num
        body["pageSize"] = page_size
        page = _investoday_post(endpoint, body, cache_dir=cache_dir, refresh_cache=refresh_cache)
        records.extend(page)
        if len(page) < page_size:
            break
        page_num += 1
    return records


def _investoday_fetch_paginated_batched(
    endpoint: str,
    base_body: dict[str, object],
    batch_key: str,
    batch_size: int,
    page_size: int = 500,
    cache_dir: str | Path | None = "cache/investoday_api",
    refresh_cache: bool = False,
) -> list[dict[str, object]]:
    if batch_size < 1:
        raise DataSourceError("Investoday api_batch_size must be positive.")
    values = base_body.get(batch_key)
    if not isinstance(values, list) or len(values) <= batch_size:
        return _investoday_fetch_paginated(
            endpoint,
            base_body,
            page_size=page_size,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
        )

    records: list[dict[str, object]] = []
    for start in range(0, len(values), batch_size):
        body = dict(base_body)
        body[batch_key] = values[start : start + batch_size]
        records.extend(
            _investoday_fetch_paginated(
                endpoint,
                body,
                page_size=page_size,
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
            )
        )
    return records


def _investoday_post(
    endpoint: str,
    body: dict[str, object],
    query_params: dict[str, object] | None = None,
    cache_dir: str | Path | None = "cache/investoday_api",
    refresh_cache: bool = False,
) -> list[dict[str, object]]:
    query_params = query_params or {}
    if cache_dir is not None:
        cache_path = _investoday_cache_path(cache_dir, endpoint, body, query_params=query_params)
        if cache_path.exists() and not refresh_cache:
            cached = _read_json(cache_path)
            if isinstance(cached, dict) and isinstance(cached.get("payload"), list):
                return [item for item in cached["payload"] if isinstance(item, dict)]

    executable = shutil.which("investoday-api")
    if executable is None:
        raise DataSourceError("investoday-api CLI was not found in PATH.")

    command = [
        executable,
        endpoint,
        "--method",
        "POST",
    ]
    for key, value in sorted(query_params.items()):
        if value is not None:
            command.append(f"{key}={value}")
    command.extend(["--body-json", json.dumps(body, ensure_ascii=False)])
    completed = subprocess.run(command, capture_output=True, text=True, timeout=90)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}"
        raise DataSourceError(f"Investoday request failed for {endpoint}: {message}")

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        preview = completed.stdout.strip()[:300]
        raise DataSourceError(f"Investoday returned non-JSON output for {endpoint}: {preview}") from exc

    if isinstance(payload, list):
        records = [item for item in payload if isinstance(item, dict)]
        if cache_dir is not None:
            _write_json(
                cache_path,
                {
                    "endpoint": endpoint,
                    "query_params": query_params,
                    "body": body,
                    "payload": records,
                },
            )
        return records
    if isinstance(payload, dict):
        for key in ("data", "rows", "records", "list", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                records = [item for item in value if isinstance(item, dict)]
                if cache_dir is not None:
                    _write_json(
                        cache_path,
                        {
                            "endpoint": endpoint,
                            "query_params": query_params,
                            "body": body,
                            "payload": records,
                        },
                    )
                return records
    raise DataSourceError(f"Investoday returned an unsupported payload shape for {endpoint}.")


def _investoday_cache_path(
    cache_dir: str | Path,
    endpoint: str,
    body: dict[str, object],
    query_params: dict[str, object] | None = None,
) -> Path:
    payload_body = {"endpoint": endpoint, "body": body}
    if query_params:
        payload_body["query_params"] = query_params
    payload = json.dumps(payload_body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    safe_endpoint = endpoint.replace("/", "__")
    return Path(cache_dir) / safe_endpoint / f"{digest}.json"


def _read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)


def _trust_check(name: str, passed: bool, severity: str, detail: str) -> dict[str, object]:
    return {"name": name, "passed": bool(passed), "severity": severity, "detail": detail}


def _a_share_type_rate(frame: pd.DataFrame) -> float:
    if frame.empty or "stockType" not in frame:
        return 1.0
    stock_type = frame["stockType"].where(frame["stockType"].notna(), "").astype(str).str.upper()
    valid = stock_type.isin({"", "A", "A股".upper(), "ASHARE", "A-SHARE"})
    return float(valid.mean()) if len(valid) else 1.0


def _b_share_symbol_mask(symbols: pd.Series) -> pd.Series:
    normalized = symbols.where(symbols.notna(), "").astype(str).str.upper()
    return normalized.str.match(r"^(200\d{3}\.SZ|900\d{3}\.SH)$", na=False)


def _date_text(value: object) -> str:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return ""
    return pd.Timestamp(timestamp).strftime("%Y-%m-%d")


def _format_rate(value: object) -> str:
    try:
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return "n/a"


def _metadata_min_stock_master_rows(notes: tuple[str, ...], default: int) -> int:
    return _metadata_int_note(notes, "Historical stock master minimum rows:", default)


def _metadata_min_delisted_rows(notes: tuple[str, ...], default: int) -> int:
    return _metadata_int_note(notes, "Historical stock master minimum delisted rows:", default)


def _metadata_int_note(notes: tuple[str, ...], prefix: str, default: int) -> int:
    for note in notes:
        text = str(note).strip()
        if not text.startswith(prefix):
            continue
        raw = text.removeprefix(prefix).strip().rstrip(".")
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return default
    return default


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _dataframe_hash(data: pd.DataFrame) -> str:
    if len(data) * max(1, len(data.columns)) > 2_000_000:
        ordered_columns = sorted(data.columns, key=lambda column: str(column))
        summary: dict[str, object] = {
            "rows": int(len(data)),
            "columns": [str(column) for column in ordered_columns],
        }
        if "date" in data:
            dates = pd.to_datetime(data["date"], errors="coerce")
            summary["date_min"] = "" if dates.dropna().empty else str(dates.min().date())
            summary["date_max"] = "" if dates.dropna().empty else str(dates.max().date())
        if "symbol" in data:
            summary["symbol_count"] = int(data["symbol"].astype(str).nunique(dropna=True))
        sample_indexes = set(range(min(1000, len(data))))
        sample_indexes.update(range(max(0, len(data) - 1000), len(data)))
        stride = max(1, len(data) // 1000)
        sample_indexes.update(range(0, len(data), stride))
        sample = data.iloc[sorted(sample_indexes)].loc[:, ordered_columns].copy()
        sort_columns = [column for column in ("date", "symbol") if column in sample.columns]
        if sort_columns:
            sample = sample.sort_values(sort_columns).reset_index(drop=True)
        else:
            sample = sample.reset_index(drop=True)
        sample_payload = sample.to_json(date_format="iso", orient="split", default_handler=str)
        summary["sample_hash"] = hashlib.sha256(sample_payload.encode("utf-8")).hexdigest()
        payload = json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    frame = data.copy()
    frame = frame.sort_index(axis=1)
    sort_columns = [column for column in ("date", "symbol") if column in frame.columns]
    if sort_columns:
        frame = frame.sort_values(sort_columns).reset_index(drop=True)
    else:
        frame = frame.reset_index(drop=True)
    payload = frame.to_json(date_format="iso", orient="split", default_handler=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_yield_series(values: pd.Series) -> pd.Series:
    observed = values.dropna()
    if not observed.empty and observed.abs().max() > 1:
        return values / 100.0
    return values


def _normalize_symbol(symbol: object) -> str:
    code_value = _symbol_code_text(symbol)
    if not code_value:
        return ""
    value = code_value
    if "." in value:
        code, exchange = value.split(".", 1)
        code = _symbol_code_text(code)
        if not code:
            return ""
        return f"{code.zfill(6)}.{exchange}"
    return _infer_exchange(value.zfill(6))


def _normalize_symbol_with_market(symbol: object, market: object) -> str:
    code = _symbol_code_text(symbol)
    if not code:
        return ""
    code = code.zfill(6)
    market_value = str(market).strip().upper()
    if market_value in {"SH", "SSE", "XSHG", "SHANGHAI"}:
        return f"{code}.SH"
    if market_value in {"SZ", "SZSE", "XSHE", "SHENZHEN"}:
        return f"{code}.SZ"
    if market_value in {"BJ", "BSE", "XBEI", "BEIJING"}:
        return f"{code}.BJ"
    return _normalize_symbol(code)


def _symbol_code_text(value: object) -> str:
    try:
        if value is None or pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip().upper()
    if not text or text in {"NAN", "NONE", "NULL"}:
        return ""
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def _infer_exchange(code: str) -> str:
    if code.startswith(("600", "601", "603", "605", "688", "689")):
        return f"{code}.SH"
    if code.startswith(("4", "8", "9")):
        return f"{code}.BJ"
    return f"{code}.SZ"


def _symbol_to_code(symbol: str) -> str:
    return _normalize_symbol(symbol).split(".", 1)[0]


def _date_compact(value: str) -> str:
    return value.replace("-", "")


def _date_with_dash(value: str) -> str:
    compact = _date_compact(value)
    if len(compact) != 8:
        return value
    return f"{compact[:4]}-{compact[4:6]}-{compact[6:]}"


def _financial_begin_date(start: str) -> str:
    start_date = pd.Timestamp(_date_with_dash(start))
    floor = pd.Timestamp("2020-01-01")
    financial_start = max(floor, start_date - pd.DateOffset(days=800))
    return financial_start.strftime("%Y-%m-%d")


def _financial_begin_date(start: str) -> str:
    start_date = pd.Timestamp(_date_with_dash(start))
    floor = pd.Timestamp("2020-01-01")
    financial_start = max(floor, start_date - pd.DateOffset(days=800))
    return financial_start.strftime("%Y-%m-%d")
