from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import hashlib
import json
import os
import pickle
import sys
import time
from typing import Iterable

import numpy as np
import pandas as pd

from .cache_governance import write_production_panel_cache_sidecar
from .data_sources import (
    DataLoadResult,
    DataSourceError,
    DataSourceMetadata,
    apply_point_in_time_liquidity_universe,
    apply_point_in_time_stock_master_filter,
    add_margin_trade_features,
    add_robust_factor_features,
    dataframe_hash,
    enrich_panel_with_stock_master,
    enforce_production_data,
    load_stock_master_csv,
    load_investoday_panel,
    prepare_backtest_panel,
    symbols_from_stock_master,
    validate_stock_master_asset,
    _normalize_symbol,
)


ASSET_LAYOUT = {
    "historical_stock_master": {
        "path": "stock_master/historical_stock_master.csv",
        "required_columns": ("symbol", "stockCode", "exchangeCode", "stockName", "stockType", "listDate", "delistDate", "listStatus"),
        "required": True,
        "scope": "production",
    },
    "daily_quotes": {
        "path": "market/daily_quotes.csv",
        "required_columns": ("date", "symbol", "open", "high", "low", "close", "volume", "amount"),
        "required": True,
        "scope": "production",
    },
    "fundamental_factors": {
        "path": "fundamentals/fundamental_factors.csv",
        "required_columns": ("date", "symbol", "roe", "dividend_yield"),
        "required": False,
        "scope": "production_optional",
    },
    "dividend_events": {
        "path": "fundamentals/dividend_events.csv",
        "required_columns": ("symbol", "exDate", "cashDividendPerShare", "dividendSource"),
        "required": False,
        "scope": "production_optional",
    },
    "daily_fund_flows": {
        "path": "market/daily_fund_flows.csv",
        "required_columns": ("date", "symbol", "mainNetInflow", "netInflowLarge", "netInflowXlarge"),
        "required": False,
        "scope": "production_optional",
    },
    "margin_trades": {
        "path": "market/margin_trades.csv",
        "required_columns": ("date", "symbol", "marginBalance", "marginBuyAmount", "marginRepayAmount"),
        "required": False,
        "scope": "production_optional",
    },
    "dragon_tiger_details": {
        "path": "events/dragon_tiger_details.csv",
        "required_columns": ("date", "symbol", "abnormalType"),
        "required": False,
        "scope": "production_optional",
    },
    "announcements": {
        "path": "events/announcements.csv",
        "required_columns": ("date", "symbol", "title"),
        "required": False,
        "scope": "production_optional",
    },
    "index_constituents": {
        "path": "index/index_constituents.csv",
        "required_columns": ("date", "indexCode", "symbol", "weight"),
        "required": False,
        "scope": "production_optional",
    },
    "industry_classification": {
        "path": "industry/industry_classification.csv",
        "required_columns": ("date", "symbol", "industryLV1Name", "industryName"),
        "required": False,
        "scope": "production_optional",
    },
    "investoday_candidate_stock_master": {
        "path": "investoday_candidate/stock_master.csv",
        "required_columns": ("symbol", "stockCode", "exchangeCode", "stockName", "stockType", "listDate", "delistDate", "listStatus"),
        "required": False,
        "scope": "candidate",
    },
    "investoday_candidate_daily_quotes": {
        "path": "investoday_candidate/daily_quotes.csv",
        "required_columns": ("date", "symbol", "open", "high", "low", "close", "volume", "amount"),
        "required": False,
        "scope": "candidate",
    },
    "investoday_candidate_universe": {
        "path": "investoday_candidate/realtime_universe.csv",
        "required_columns": ("symbol", "stockCode", "stockName"),
        "required": False,
        "scope": "candidate",
    },
    "investoday_candidate_industry": {
        "path": "investoday_candidate/industry_classification.csv",
        "required_columns": ("date", "symbol", "industryLV1Name", "industryName"),
        "required": False,
        "scope": "candidate",
    },
}


PRODUCTION_PANEL_CACHE_VERSION = 1


FINANCIAL_ALPHA_FIELDS = (
    "gross_margin",
    "operating_profit_margin",
    "net_margin",
    "roa",
    "roic",
    "roe_deducted",
    "rev_growth_1y",
    "revenue_growth_3y",
    "np_growth_1y",
    "np_recurring_growth_1y",
    "op_profit_growth_1y",
    "cfo_growth_1y",
    "equity_growth_1y",
    "cfo_ps",
    "fcf_to_equity_ps",
    "net_operating_cash_flow",
    "ocf_to_net_profit_ratio",
    "cfo_to_revenue",
    "cfo_to_current_liab",
    "cash_received_sales_to_revenue",
    "cash_debt_ratio",
    "debt_asset_ratio",
    "current_ratio",
    "quick_ratio",
    "f_score",
    "z_score",
    "m_score",
    "asset_turnover",
    "inventory_turnover",
    "receivable_turnover",
    "capex_to_revenue",
    "fcf",
)


CAPITAL_FLOW_FIELDS = (
    "inflowSmall",
    "inflowMedium",
    "inflowLarge",
    "inflowXlarge",
    "outflowSmall",
    "outflowMedium",
    "outflowLarge",
    "outflowXlarge",
    "netInflowSmall",
    "netInflowMedium",
    "netInflowLarge",
    "netInflowXlarge",
    "netInflowRatioSmall",
    "netInflowRatioMedium",
    "netInflowRatioLarge",
    "netInflowRatioXlarge",
    "mainNetInflow",
    "mainNetInflowRatio",
    "controlRatio",
    "askVolumeTotal",
    "bidVolumeTotal",
    "bidAskVolumeDiff",
)


MARGIN_TRADE_FIELDS = (
    "marginBalance",
    "marginBuyAmount",
    "marginRepayAmount",
    "shortBalanceVolume",
    "shortSellVolume",
    "shortBalanceAmount",
    "marginShortBalance",
)


MARGIN_TRADE_FEATURE_FIELDS = (
    "marginTradeDate",
    "marginBalance",
    "marginBuyAmount",
    "marginRepayAmount",
    "margin_net_buy_amount",
    "margin_buy_to_amount",
    "margin_repay_to_amount",
    "margin_net_buy_to_amount",
    "margin_balance_to_amount",
    "short_balance_to_amount",
    "margin_net_buy_strength_score",
    "margin_balance_crowding_guard_score",
    "margin_short_pressure_guard_score",
    "margin_leverage_flow_score",
    "margin_deleveraging_guard_score",
    "margin_trade_quality_score",
)


ANNOUNCEMENT_DATE_ALIASES = (
    "date",
    "announcementDate",
    "publishDate",
    "disclosureDate",
    "noticeDate",
    "annDate",
    "公告日期",
    "披露日期",
    "发布日期",
)


ANNOUNCEMENT_TITLE_ALIASES = (
    "title",
    "announcementTitle",
    "noticeTitle",
    "headline",
    "公告标题",
    "标题",
)


ANNOUNCEMENT_TYPE_ALIASES = (
    "announcementType",
    "announcementTypeName",
    "noticeType",
    "noticeTypeName",
    "category",
    "公告类型",
    "公告类别",
)


ANNOUNCEMENT_SOURCE_ALIASES = (
    "announcementSource",
    "source",
    "vendorSource",
)


ANNOUNCEMENT_CATEGORY_KEYWORDS = {
    "buyback": ("回购", "repurchase", "buyback"),
    "dividend": ("分红", "派息", "派发", "权益分派", "利润分配", "cash dividend", "dividend"),
    "financing": ("增发", "配股", "可转债", "公司债", "募集资金", "融资", "定向发行", "private placement", "convertible bond", "rights issue"),
    "reorg": ("重组", "并购", "收购", "资产置换", "重大资产", "merger", "acquisition", "restructuring"),
    "risk_alert": (
        "风险提示",
        "诉讼",
        "仲裁",
        "处罚",
        "违规",
        "立案",
        "问询函",
        "监管函",
        "退市",
        "债务逾期",
        "担保",
        "减持",
        "litigation",
        "penalty",
        "delisting",
        "shareholder reduction",
    ),
    "report": ("年报", "季报", "半年报", "业绩预告", "业绩快报", "annual report", "quarterly report", "earnings forecast"),
}


ANNOUNCEMENT_EVENT_FEATURE_FIELDS = (
    "announcement_count_30d",
    "announcement_count_90d",
    "announcement_count_180d",
    "announcement_count_365d",
    "announcement_buyback_count_180d",
    "announcement_dividend_count_365d",
    "announcement_financing_count_365d",
    "announcement_reorg_count_365d",
    "announcement_risk_alert_count_365d",
    "announcement_report_count_365d",
    "announcement_days_since_last",
    "announcement_activity_score",
    "announcement_recency_score",
    "announcement_noise_guard_score",
    "announcement_buyback_activity_score",
    "announcement_shareholder_return_score",
    "announcement_risk_alert_guard_score",
    "announcement_financing_cooldown_score",
    "announcement_reorg_cooldown_score",
    "announcement_stability_guard_score",
    "announcement_event_score",
)


@dataclass(frozen=True)
class ShardedLoadResult:
    loaded: DataLoadResult
    manifest: dict[str, object]
    shard_dir: Path


def discover_data_assets(
    asset_root: str | Path,
    *,
    start: str | None = None,
    end: str | None = None,
    min_stock_master_rows: int = 3000,
) -> dict[str, object]:
    root = Path(asset_root)
    assets: list[dict[str, object]] = []
    stock_master_validation: dict[str, object] = {}
    for name, spec in ASSET_LAYOUT.items():
        path = root / str(spec["path"])
        asset = _asset_summary(
            name,
            path,
            tuple(spec["required_columns"]),
            required=bool(spec.get("required", False)),
            scope=str(spec.get("scope", "")),
        )
        assets.append(asset)
        if name == "historical_stock_master" and path.exists():
            try:
                stock_master = load_stock_master_csv(path)
                stock_master_validation = validate_stock_master_asset(
                    stock_master.master,
                    start=start,
                    end=end,
                    min_rows=min_stock_master_rows,
                )
            except Exception as exc:
                stock_master_validation = {
                    "status": "invalid",
                    "coverage_level": "error",
                    "hard_failed": 1,
                    "caveats": [f"Stock master validation failed: {exc}"],
                }

    existing = sum(1 for asset in assets if asset["exists"])
    required_assets = [asset for asset in assets if asset.get("required")]
    required_ready = all(asset["exists"] and not asset["missing_columns"] for asset in required_assets)
    return {
        "root": str(root),
        "assets": assets,
        "summary": {
            "existing_assets": existing,
            "total_assets": len(assets),
            "required_assets": len(required_assets),
            "required_ready": required_ready,
            "stock_master_ready": stock_master_validation.get("status") == "production_ready",
        },
        "stock_master_validation": stock_master_validation,
    }


def render_asset_inventory_markdown(inventory: dict[str, object]) -> str:
    summary = inventory.get("summary") if isinstance(inventory.get("summary"), dict) else {}
    lines = [
        "## Data Asset Inventory",
        "",
        f"Root: `{inventory.get('root', '')}`",
        f"Existing assets: {summary.get('existing_assets', 0)} / {summary.get('total_assets', 0)}",
        f"Required ready: {'yes' if summary.get('required_ready') else 'no'}",
        f"Stock master ready: {'yes' if summary.get('stock_master_ready') else 'no'}",
        "",
        "| Asset | Scope | Required | Exists | Rows | Date Range | Missing Columns | Path |",
        "|---|---|---:|---:|---:|---|---|---|",
    ]
    assets = inventory.get("assets", [])
    if isinstance(assets, list):
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            date_range = f"{asset.get('min_date', '') or 'n/a'} to {asset.get('max_date', '') or 'n/a'}"
            missing = ", ".join(asset.get("missing_columns", []) or []) or "none"
            lines.append(
                "| {name} | {scope} | {required} | {exists} | {rows} | {date_range} | {missing} | `{path}` |".format(
                    name=_markdown_cell(str(asset.get("name", ""))),
                    scope=_markdown_cell(str(asset.get("scope", ""))),
                    required="yes" if asset.get("required") else "no",
                    exists="yes" if asset.get("exists") else "no",
                    rows=asset.get("rows", 0),
                    date_range=_markdown_cell(date_range),
                    missing=_markdown_cell(missing),
                    path=_markdown_cell(str(asset.get("path", ""))),
                )
            )
    validation = inventory.get("stock_master_validation") if isinstance(inventory.get("stock_master_validation"), dict) else {}
    if validation:
        lines.extend(
            [
                "",
                "### Stock Master Validation",
                "",
                f"Status: `{validation.get('status', 'n/a')}`",
                f"Coverage level: `{validation.get('coverage_level', 'n/a')}`",
                f"Hard failed: {validation.get('hard_failed', 0)}",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def render_data_asset_manifest_markdown(manifest: dict[str, object]) -> str:
    data_trust = manifest.get("data_trust") if isinstance(manifest.get("data_trust"), dict) else {}
    validation = manifest.get("stock_master_validation") if isinstance(manifest.get("stock_master_validation"), dict) else {}
    paths = manifest.get("paths") if isinstance(manifest.get("paths"), dict) else {}
    caveats = manifest.get("caveats") if isinstance(manifest.get("caveats"), list) else []
    lines = [
        "## Data Asset Manifest",
        "",
        f"Scope: `{manifest.get('scope', 'n/a')}`",
        f"Source: `{manifest.get('source', 'n/a')}`",
        f"Generated at: `{manifest.get('generated_at', 'n/a')}`",
        f"Range: `{manifest.get('start_date', '')}` to `{manifest.get('end_date', '')}`",
        f"Symbols: {manifest.get('symbols', 0)}",
        f"Rows: {manifest.get('rows', 0)}",
        f"Data hash: `{manifest.get('data_hash', '') or 'n/a'}`",
        f"Trust level: `{data_trust.get('trust_level', 'n/a')}`",
        f"Production data ready: {'yes' if data_trust.get('production_data_ready') else 'no'}",
        f"Stock master status: `{validation.get('status', 'n/a')}`",
        "",
        "| Asset | Path |",
        "|---|---|",
    ]
    for name, path in sorted(paths.items()):
        lines.append(f"| {_markdown_cell(str(name))} | `{_markdown_cell(str(path))}` |")
    if caveats:
        lines.extend(["", "### Caveats", ""])
        lines.extend(f"- {str(item)}" for item in caveats[:12])
    notes = manifest.get("notes") if isinstance(manifest.get("notes"), list) else []
    if notes:
        lines.extend(["", "### Notes", ""])
        lines.extend(f"- {str(item)}" for item in notes[:12])
    lines.append("")
    return "\n".join(lines)


def write_data_asset_manifest_artifacts(output_dir: str | Path, manifest: dict[str, object]) -> dict[str, Path]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "data_asset_manifest.json"
    markdown_path = target / "data_asset_manifest.md"
    json_path.write_text(json.dumps(_json_ready(manifest), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_data_asset_manifest_markdown(manifest), encoding="utf-8")
    return {"data_asset_manifest": json_path, "data_asset_manifest_report": markdown_path}


def write_asset_inventory(output_dir: str | Path, inventory: dict[str, object]) -> dict[str, Path]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "data_asset_inventory.json"
    markdown_path = target / "data_asset_inventory.md"
    json_path.write_text(json.dumps(_json_ready(inventory), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_asset_inventory_markdown(inventory), encoding="utf-8")
    return {"data_asset_inventory": json_path, "data_asset_inventory_report": markdown_path}


def load_historical_market_panel(
    path: str | Path,
    *,
    start: str,
    end: str,
    symbols: Iterable[str] | None = None,
) -> DataLoadResult:
    panel_path = Path(path)
    if not panel_path.exists():
        raise DataSourceError(f"Historical market panel does not exist: {panel_path}")
    raw = pd.read_csv(panel_path)
    if raw.empty:
        raise DataSourceError(f"Historical market panel is empty: {panel_path}")

    frame = raw.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    frame = frame.dropna(subset=["date", "symbol"])
    start_date = pd.Timestamp(_date_with_dash(start))
    end_date = pd.Timestamp(_date_with_dash(end))
    frame = frame[(frame["date"] >= start_date) & (frame["date"] <= end_date)].copy()
    if symbols is not None:
        symbol_set = {str(symbol).upper() for symbol in symbols}
        frame = frame[frame["symbol"].isin(symbol_set)].copy()
    if frame.empty:
        raise DataSourceError("Historical market panel has no rows after date/symbol filtering.")

    data = prepare_backtest_panel(frame)
    loaded_symbols = tuple(sorted(data["symbol"].unique()))
    return DataLoadResult(
        data=data,
        metadata=DataSourceMetadata(
            source="historical_asset:daily_quotes",
            symbols=loaded_symbols,
            start_date=start,
            end_date=end,
            notes=(
                f"Loaded historical market panel asset: {panel_path}.",
                "Panel is treated as an offline real historical data asset; vendor provenance must be documented outside this file.",
            ),
            data_hash=dataframe_hash(data),
        ),
    )


def load_fundamental_factor_asset(
    path: str | Path,
    *,
    end: str,
    symbols: Iterable[str] | None = None,
    fields: Iterable[str] | None = None,
) -> pd.DataFrame:
    factor_path = Path(path)
    if not factor_path.exists():
        raise DataSourceError(f"Fundamental factor asset does not exist: {factor_path}")
    raw = pd.read_csv(factor_path)
    if raw.empty:
        raise DataSourceError(f"Fundamental factor asset is empty: {factor_path}")

    frame = raw.copy()
    if "date" not in frame:
        if "publishDate" in frame:
            frame["date"] = frame["publishDate"]
        elif "reportDate" in frame:
            frame["date"] = frame["reportDate"]
        else:
            raise DataSourceError("fundamental_factors requires date, publishDate, or reportDate.")
    if "symbol" not in frame and "stockCode" not in frame:
        raise DataSourceError("fundamental_factors requires symbol or stockCode.")

    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    if "symbol" in frame:
        frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    else:
        frame["symbol"] = frame["stockCode"].map(_normalize_symbol)
    if "publishDate" not in frame:
        frame["publishDate"] = frame["date"]
    else:
        frame["publishDate"] = pd.to_datetime(frame["publishDate"], errors="coerce")
    if "reportPeriodEnd" in frame:
        frame["reportPeriodEnd"] = pd.to_datetime(frame["reportPeriodEnd"], errors="coerce")
    elif "reportDate" in frame:
        frame["reportPeriodEnd"] = pd.to_datetime(frame["reportDate"], errors="coerce")

    for column in ("pe", "pb", "roe", "dividend_yield", *FINANCIAL_ALPHA_FIELDS):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "dividend_yield" in frame:
        frame["dividend_yield"] = _normalize_yield_series(frame["dividend_yield"])

    frame = frame.dropna(subset=["date", "symbol"])
    frame = frame[frame["date"] <= pd.Timestamp(_date_with_dash(end))]
    if symbols is not None:
        symbol_set = {str(symbol).upper() for symbol in symbols}
        frame = frame[frame["symbol"].isin(symbol_set)].copy()
    if frame.empty:
        raise DataSourceError("Fundamental factor asset has no rows after date/symbol filtering.")

    requested_fields = None if fields is None else {str(field) for field in fields if str(field)}
    all_factor_fields = ["roe", "dividend_yield", "pe", "pb", *FINANCIAL_ALPHA_FIELDS]
    if requested_fields is None:
        factor_keep = all_factor_fields
    else:
        factor_keep = [field for field in all_factor_fields if field in requested_fields]

    keep = [
        "date",
        "symbol",
        *factor_keep,
        "publishDate",
        "reportPeriodEnd",
        "source",
        "factorSource",
    ]
    frame = frame[[column for column in keep if column in frame.columns]]
    return frame.sort_values(["symbol", "date"]).drop_duplicates(["symbol", "date"], keep="last").reset_index(drop=True)


def load_dividend_event_asset(
    path: str | Path,
    *,
    end: str,
    symbols: Iterable[str] | None = None,
) -> pd.DataFrame:
    event_path = Path(path)
    if not event_path.exists():
        raise DataSourceError(f"Dividend event asset does not exist: {event_path}")
    raw = pd.read_csv(event_path)
    if raw.empty:
        raise DataSourceError(f"Dividend event asset is empty: {event_path}")

    frame = raw.copy()
    if "symbol" not in frame and "stockCode" not in frame:
        raise DataSourceError("dividend_events requires symbol or stockCode.")
    if "exDate" not in frame:
        raise DataSourceError("dividend_events requires exDate.")
    if "cashDividendPerShare" not in frame:
        raise DataSourceError("dividend_events requires cashDividendPerShare.")

    if "symbol" in frame:
        frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    else:
        frame["symbol"] = frame["stockCode"].map(_normalize_symbol)
    frame["exDate"] = pd.to_datetime(frame["exDate"], errors="coerce")
    frame["cashDividendPerShare"] = pd.to_numeric(frame["cashDividendPerShare"], errors="coerce")
    for column in ("latestAnnounceDate", "planAnnounceDate", "recordDate", "cashPayDate"):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    frame = frame.dropna(subset=["symbol", "exDate", "cashDividendPerShare"])
    frame = frame[(frame["cashDividendPerShare"] > 0.0) & (frame["exDate"] <= pd.Timestamp(_date_with_dash(end)))]
    if symbols is not None:
        symbol_set = {str(symbol).upper() for symbol in symbols}
        frame = frame[frame["symbol"].isin(symbol_set)].copy()
    if frame.empty:
        raise DataSourceError("Dividend event asset has no rows after date/symbol filtering.")

    keep = [
        "symbol",
        "stockCode",
        "stockName",
        "fiscalYearEnd",
        "latestAnnounceDate",
        "planAnnounceDate",
        "exDate",
        "recordDate",
        "cashPayDate",
        "cashDividendPerShare",
        "cashDividendPerShareAfterTax",
        "currencyCode",
        "eventTypeCode",
        "baseShares",
        "dividendSource",
    ]
    return frame[[column for column in keep if column in frame.columns]].sort_values(["symbol", "exDate"]).reset_index(drop=True)


def load_capital_flow_asset(
    path: str | Path,
    *,
    end: str,
    symbols: Iterable[str] | None = None,
) -> pd.DataFrame:
    flow_path = Path(path)
    if not flow_path.exists():
        raise DataSourceError(f"Daily fund flow asset does not exist: {flow_path}")
    raw = pd.read_csv(flow_path)
    if raw.empty:
        raise DataSourceError(f"Daily fund flow asset is empty: {flow_path}")

    frame = raw.copy()
    if "date" not in frame:
        raise DataSourceError("daily_fund_flows requires date.")
    if "symbol" not in frame and "stockCode" not in frame:
        raise DataSourceError("daily_fund_flows requires symbol or stockCode.")
    if "symbol" in frame:
        frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    else:
        frame["symbol"] = frame["stockCode"].map(_normalize_symbol)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    for column in CAPITAL_FLOW_FIELDS:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["date", "symbol"])
    frame = frame[frame["date"] <= pd.Timestamp(_date_with_dash(end))]
    if symbols is not None:
        symbol_set = {str(symbol).upper() for symbol in symbols}
        frame = frame[frame["symbol"].isin(symbol_set)].copy()
    if frame.empty:
        raise DataSourceError("Daily fund flow asset has no rows after date/symbol filtering.")

    keep = [
        "date",
        "symbol",
        "stockCode",
        "stockName",
        *CAPITAL_FLOW_FIELDS,
        "capitalFlowSource",
    ]
    return frame[[column for column in keep if column in frame.columns]].sort_values(["symbol", "date"]).reset_index(drop=True)


def load_margin_trade_asset(
    path: str | Path,
    *,
    end: str,
    symbols: Iterable[str] | None = None,
) -> pd.DataFrame:
    trade_path = Path(path)
    if not trade_path.exists():
        raise DataSourceError(f"Margin trade asset does not exist: {trade_path}")
    raw = pd.read_csv(trade_path)
    if raw.empty:
        raise DataSourceError(f"Margin trade asset is empty: {trade_path}")

    frame = raw.copy()
    if "date" not in frame:
        raise DataSourceError("margin_trades requires date.")
    if "symbol" not in frame and "stockCode" not in frame:
        raise DataSourceError("margin_trades requires symbol or stockCode.")
    if "symbol" in frame:
        frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    else:
        frame["symbol"] = frame["stockCode"].map(_normalize_symbol)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    for column in MARGIN_TRADE_FIELDS:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["date", "symbol"])
    frame = frame[frame["date"] <= pd.Timestamp(_date_with_dash(end))]
    if symbols is not None:
        symbol_set = {str(symbol).upper() for symbol in symbols}
        frame = frame[frame["symbol"].isin(symbol_set)].copy()
    if frame.empty:
        raise DataSourceError("Margin trade asset has no rows after date/symbol filtering.")

    keep = [
        "date",
        "symbol",
        "stockCode",
        "stockName",
        *MARGIN_TRADE_FIELDS,
        "marginTradeSource",
    ]
    return frame[[column for column in keep if column in frame.columns]].sort_values(["symbol", "date"]).reset_index(drop=True)


def load_dragon_tiger_detail_asset(
    path: str | Path,
    *,
    end: str,
    symbols: Iterable[str] | None = None,
) -> pd.DataFrame:
    event_path = Path(path)
    if not event_path.exists():
        raise DataSourceError(f"Dragon tiger detail asset does not exist: {event_path}")
    raw = pd.read_csv(event_path)
    if raw.empty:
        raise DataSourceError(f"Dragon tiger detail asset is empty: {event_path}")

    frame = raw.copy()
    if "date" not in frame:
        raise DataSourceError("dragon_tiger_details requires date.")
    if "symbol" not in frame and "stockCode" not in frame:
        raise DataSourceError("dragon_tiger_details requires symbol or stockCode.")
    if "abnormalType" not in frame and "abnormalTypeName" not in frame:
        raise DataSourceError("dragon_tiger_details requires abnormalType or abnormalTypeName.")
    if "symbol" in frame:
        frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    else:
        frame["symbol"] = frame["stockCode"].map(_normalize_symbol)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    for column in ("deviationPct", "volume", "amount", "buyAmount", "sellAmount", "totalAmount"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["date", "symbol"])
    frame = frame[frame["date"] <= pd.Timestamp(_date_with_dash(end))]
    if symbols is not None:
        symbol_set = {str(symbol).upper() for symbol in symbols}
        frame = frame[frame["symbol"].isin(symbol_set)].copy()
    if frame.empty:
        raise DataSourceError("Dragon tiger detail asset has no rows after date/symbol filtering.")

    keep = [
        "date",
        "symbol",
        "stockCode",
        "stockName",
        "abnormalType",
        "abnormalTypeName",
        "deviationPct",
        "volume",
        "amount",
        "buyAmount",
        "sellAmount",
        "totalAmount",
        "dragonTigerSource",
    ]
    return frame[[column for column in keep if column in frame.columns]].sort_values(["symbol", "date"]).reset_index(drop=True)


def load_announcement_event_asset(
    path: str | Path,
    *,
    end: str,
    symbols: Iterable[str] | None = None,
) -> pd.DataFrame:
    event_path = Path(path)
    if not event_path.exists():
        raise DataSourceError(f"Announcement event asset does not exist: {event_path}")
    raw = pd.read_csv(event_path)
    if raw.empty:
        raise DataSourceError(f"Announcement event asset is empty: {event_path}")

    frame = raw.copy()
    date_column = _first_existing_column(frame, ANNOUNCEMENT_DATE_ALIASES)
    title_column = _first_existing_column(frame, ANNOUNCEMENT_TITLE_ALIASES)
    type_column = _first_existing_column(frame, ANNOUNCEMENT_TYPE_ALIASES)
    source_column = _first_existing_column(frame, ANNOUNCEMENT_SOURCE_ALIASES)
    if date_column is None:
        raise DataSourceError("announcements requires date, announcementDate, publishDate, or disclosureDate.")
    if "symbol" not in frame and "stockCode" not in frame:
        raise DataSourceError("announcements requires symbol or stockCode.")
    if title_column is None and type_column is None:
        raise DataSourceError("announcements requires title/announcementTitle or announcementType.")

    if date_column != "date":
        frame["date"] = frame[date_column]
    if title_column is None:
        frame["title"] = ""
    elif title_column != "title":
        frame["title"] = frame[title_column]
    if type_column is None:
        frame["announcementType"] = ""
    elif type_column != "announcementType":
        frame["announcementType"] = frame[type_column]
    if source_column is not None and source_column != "announcementSource":
        frame["announcementSource"] = frame[source_column]
    if "announcementSource" not in frame:
        frame["announcementSource"] = "canonical:events/announcements.csv"

    if "symbol" in frame:
        frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    else:
        frame["symbol"] = frame["stockCode"].map(_normalize_symbol)
    frame["stockCode"] = frame["symbol"].str.split(".", n=1).str[0]
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    for column in (
        "title",
        "announcementType",
        "announcementId",
        "url",
        "announcementSource",
        "stockName",
        "riskType",
        "announcementContentType",
        "guid",
    ):
        if column in frame:
            frame[column] = frame[column].where(frame[column].notna(), "").astype(str)

    frame = frame.dropna(subset=["date", "symbol"])
    frame = frame[frame["date"] <= pd.Timestamp(_date_with_dash(end))]
    if symbols is not None:
        symbol_set = {str(symbol).upper() for symbol in symbols}
        frame = frame[frame["symbol"].isin(symbol_set)].copy()
    if frame.empty:
        raise DataSourceError("Announcement event asset has no rows after date/symbol filtering.")

    frame = _add_announcement_category_flags(frame)
    keep = [
        "date",
        "symbol",
        "stockCode",
        "stockName",
        "title",
        "announcementType",
        "announcementId",
        "url",
        "announcementSource",
        "riskType",
        "announcementContentType",
        "guid",
        *[f"announcement_is_{category}" for category in ANNOUNCEMENT_CATEGORY_KEYWORDS],
    ]
    duplicate_keys = [column for column in ("date", "symbol", "title", "announcementType") if column in frame.columns]
    return (
        frame[[column for column in keep if column in frame.columns]]
        .sort_values(["symbol", "date"])
        .drop_duplicates(duplicate_keys, keep="last")
        .reset_index(drop=True)
    )


def _first_existing_column(frame: pd.DataFrame, aliases: Iterable[str]) -> str | None:
    for alias in aliases:
        if alias in frame.columns:
            return str(alias)
    return None


def _add_announcement_category_flags(frame: pd.DataFrame) -> pd.DataFrame:
    combined = (
        frame.get("title", pd.Series("", index=frame.index)).where(lambda value: value.notna(), "").astype(str)
        + " "
        + frame.get("announcementType", pd.Series("", index=frame.index)).where(lambda value: value.notna(), "").astype(str)
    ).str.lower()
    for category, keywords in ANNOUNCEMENT_CATEGORY_KEYWORDS.items():
        normalized = tuple(str(keyword).lower() for keyword in keywords if str(keyword))
        frame[f"announcement_is_{category}"] = [float(any(keyword in value for keyword in normalized)) for value in combined]
    return frame


def load_industry_classification_asset(
    path: str | Path,
    *,
    end: str,
    symbols: Iterable[str] | None = None,
) -> pd.DataFrame:
    industry_path = Path(path)
    if not industry_path.exists():
        raise DataSourceError(f"Industry classification asset does not exist: {industry_path}")
    raw = pd.read_csv(industry_path)
    if raw.empty:
        raise DataSourceError(f"Industry classification asset is empty: {industry_path}")

    frame = raw.copy()
    for column in ("date", "symbol", "industryLV1Name", "industryName"):
        if column not in frame:
            raise DataSourceError(f"industry_classification requires {column}.")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    for column in ("industryLV1Name", "industryName"):
        frame[column] = frame[column].where(frame[column].notna(), "").astype(str).str.strip()
    frame = frame.dropna(subset=["date", "symbol"])
    frame = frame[(frame["date"] <= pd.Timestamp(_date_with_dash(end))) & (frame["industryLV1Name"] != "")]
    if symbols is not None:
        symbol_set = {str(symbol).upper() for symbol in symbols}
        frame = frame[frame["symbol"].isin(symbol_set)].copy()
    if frame.empty:
        raise DataSourceError("Industry classification asset has no rows after date/symbol filtering.")

    keep = [
        "date",
        "symbol",
        "industryLV1Name",
        "industryName",
        "industryLV1Code",
        "industryCode",
        "industrySource",
        "industryAsOfDate",
        "isLatestOnly",
    ]
    return frame[[column for column in keep if column in frame.columns]].sort_values(["symbol", "date"]).reset_index(drop=True)


def load_index_constituent_asset(
    path: str | Path,
    *,
    end: str,
    symbols: Iterable[str] | None = None,
    index_codes: Iterable[str] | None = None,
    allow_latest_only: bool = False,
) -> pd.DataFrame:
    constituent_path = Path(path)
    if not constituent_path.exists():
        raise DataSourceError(f"Index constituent asset does not exist: {constituent_path}")
    raw = pd.read_csv(constituent_path)
    if raw.empty:
        raise DataSourceError(f"Index constituent asset is empty: {constituent_path}")

    frame = raw.copy()
    for column in ("date", "indexCode", "symbol", "weight"):
        if column not in frame:
            raise DataSourceError(f"index_constituents requires {column}.")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["indexCode"] = frame["indexCode"].where(frame["indexCode"].notna(), "").astype(str).str.strip().str.upper()
    frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    frame["weight"] = pd.to_numeric(frame["weight"], errors="coerce")
    frame = frame.dropna(subset=["date", "symbol"])
    frame = frame[(frame["indexCode"] != "") & (frame["date"] <= pd.Timestamp(_date_with_dash(end)))]
    if symbols is not None:
        symbol_set = {str(symbol).upper() for symbol in symbols}
        frame = frame[frame["symbol"].isin(symbol_set)].copy()
    if index_codes is not None:
        code_set = {str(code).strip().upper() for code in index_codes if str(code).strip()}
        if code_set:
            frame = frame[frame["indexCode"].isin(code_set)].copy()
    if frame.empty:
        raise DataSourceError("Index constituent asset has no rows after date/symbol/index filtering.")
    if not allow_latest_only and "isLatestOnly" in frame.columns:
        latest_flags = _truthy_flag_series(frame["isLatestOnly"])
        snapshot_dates = int(frame["date"].nunique(dropna=True))
        if bool(latest_flags.all()) and snapshot_dates <= 1:
            raise DataSourceError(
                "Index constituent asset is marked latest-only and has only one snapshot date; "
                "refusing to use it as a historical point-in-time constituent source."
            )

    keep = [
        "date",
        "indexCode",
        "indexName",
        "symbol",
        "weight",
        "indexSource",
        "indexAsOfDate",
        "isLatestOnly",
    ]
    return (
        frame[[column for column in keep if column in frame.columns]]
        .sort_values(["indexCode", "date", "symbol"])
        .drop_duplicates(["date", "indexCode", "symbol"], keep="last")
        .reset_index(drop=True)
    )


def _truthy_flag_series(values: pd.Series) -> pd.Series:
    if values.dtype == bool:
        return values.fillna(False).astype(bool)
    return values.fillna(False).astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def merge_point_in_time_fundamental_factors(
    data: pd.DataFrame,
    factors: pd.DataFrame,
    *,
    fields: Iterable[str] | None = None,
) -> pd.DataFrame:
    if data.empty or factors.empty:
        return data.copy()

    requested_fields = None if fields is None else {str(field) for field in fields if str(field)}
    factor_fields = [
        column
        for column in ("pe", "pb", "roe", "dividend_yield", *FINANCIAL_ALPHA_FIELDS)
        if column in factors.columns and (requested_fields is None or column in requested_fields)
    ]
    if not factor_fields:
        return data.copy()
    factor_columns = ["date", *factor_fields]
    for column in ("publishDate", "reportPeriodEnd"):
        if column in factors.columns:
            factor_columns.append(column)

    merged_frames: list[pd.DataFrame] = []
    grouped_factors = {
        str(symbol): group.sort_values("date")
        for symbol, group in factors[factor_columns + ["symbol"]].groupby("symbol", sort=False)
    }
    for symbol, quote_group in data.groupby("symbol", sort=False):
        quote_sorted = quote_group.sort_values("date").copy()
        factor_group = grouped_factors.get(str(symbol))
        if factor_group is None or factor_group.empty:
            for field in factor_fields:
                if field not in quote_sorted.columns:
                    quote_sorted[field] = pd.NA
            if "publishDate" in factors.columns and "publishDate" not in quote_sorted.columns:
                quote_sorted["publishDate"] = pd.NaT
            if "reportPeriodEnd" in factors.columns and "reportPeriodEnd" not in quote_sorted.columns:
                quote_sorted["reportPeriodEnd"] = pd.NaT
            merged_frames.append(quote_sorted)
            continue

        factor_group = factor_group.drop(columns=["symbol"]).sort_values("date")
        merged = pd.merge_asof(
            quote_sorted,
            factor_group,
            on="date",
            direction="backward",
            suffixes=("", "_fundamental"),
        )
        for field in factor_fields:
            factor_column = f"{field}_fundamental" if f"{field}_fundamental" in merged.columns else field
            if factor_column == field:
                continue
            merged[field] = merged[factor_column].combine_first(merged[field]) if field in merged else merged[factor_column]
            merged.drop(columns=[factor_column], inplace=True)
        for column in ("publishDate", "reportPeriodEnd"):
            factor_column = f"{column}_fundamental" if f"{column}_fundamental" in merged.columns else column
            if factor_column != column and factor_column in merged.columns:
                merged[column] = merged[factor_column].combine_first(merged[column]) if column in merged else merged[factor_column]
                merged.drop(columns=[factor_column], inplace=True)
        merged_frames.append(merged)

    merged = pd.concat(merged_frames, ignore_index=True)
    return merged.sort_values(["date", "symbol"]).reset_index(drop=True)


def merge_point_in_time_industry_classification(data: pd.DataFrame, industry: pd.DataFrame) -> pd.DataFrame:
    if data.empty or industry.empty:
        return data.copy()

    industry_fields = [
        column
        for column in (
            "industryLV1Name",
            "industryName",
            "industryLV1Code",
            "industryCode",
            "industrySource",
            "industryAsOfDate",
            "isLatestOnly",
        )
        if column in industry.columns
    ]
    if not industry_fields:
        return data.copy()

    industry_dates = pd.to_datetime(industry["date"], errors="coerce")
    data_min_date = pd.to_datetime(data["date"], errors="coerce").min()
    is_latest_only = (
        "isLatestOnly" in industry
        and industry["isLatestOnly"].fillna(False).astype(bool).all()
        and industry_dates.nunique(dropna=True) == 1
        and pd.notna(data_min_date)
        and industry_dates.dropna().iloc[0] <= data_min_date
    )
    if is_latest_only:
        frame = data.copy()
        lookup = (
            industry.sort_values("date")
            .drop_duplicates("symbol", keep="last")[["symbol", *industry_fields]]
            .set_index("symbol")
        )
        mapped = pd.DataFrame(
            {field: frame["symbol"].map(lookup[field]) for field in industry_fields},
            index=frame.index,
        )
        for field in industry_fields:
            if field in frame:
                mapped[field] = mapped[field].combine_first(frame[field])
        base = frame.drop(columns=[field for field in industry_fields if field in frame.columns])
        merged = pd.concat([base, mapped], axis=1)
        return merged.sort_values(["date", "symbol"]).reset_index(drop=True)

    merged_frames: list[pd.DataFrame] = []
    grouped_industry = {
        str(symbol): group[["date", *industry_fields]].sort_values("date")
        for symbol, group in industry[["symbol", "date", *industry_fields]].groupby("symbol", sort=False)
    }
    for symbol, quote_group in data.groupby("symbol", sort=False):
        quote_sorted = quote_group.sort_values("date").copy()
        industry_group = grouped_industry.get(str(symbol))
        if industry_group is None or industry_group.empty:
            for field in industry_fields:
                if field not in quote_sorted:
                    quote_sorted[field] = pd.NA
            merged_frames.append(quote_sorted)
            continue

        merged = pd.merge_asof(
            quote_sorted,
            industry_group,
            on="date",
            direction="backward",
            suffixes=("", "_industry"),
        )
        for field in industry_fields:
            industry_column = f"{field}_industry" if f"{field}_industry" in merged.columns else field
            if industry_column == field:
                continue
            merged[field] = merged[industry_column].combine_first(merged[field]) if field in merged else merged[industry_column]
            merged.drop(columns=[industry_column], inplace=True)
        merged_frames.append(merged)

    return pd.concat(merged_frames, ignore_index=True).sort_values(["date", "symbol"]).reset_index(drop=True)


def merge_point_in_time_index_constituents(
    data: pd.DataFrame,
    constituents: pd.DataFrame,
    *,
    index_codes: Iterable[str] | None = None,
) -> pd.DataFrame:
    if data.empty or constituents.empty:
        return data.copy()
    required = {"date", "indexCode", "symbol", "weight"}
    missing = required - set(constituents.columns)
    if missing:
        raise DataSourceError(f"index_constituents missing required columns for PIT merge: {sorted(missing)}")

    frame = data.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    constituents = constituents.copy()
    constituents["date"] = pd.to_datetime(constituents["date"], errors="coerce")
    constituents["indexCode"] = constituents["indexCode"].where(constituents["indexCode"].notna(), "").astype(str).str.strip().str.upper()
    constituents["symbol"] = constituents["symbol"].map(_normalize_symbol)
    constituents["weight"] = pd.to_numeric(constituents["weight"], errors="coerce")
    constituents = constituents.dropna(subset=["date", "indexCode", "symbol"])
    constituents = constituents[constituents["indexCode"] != ""].copy()
    if index_codes is not None:
        code_set = {str(code).strip().upper() for code in index_codes if str(code).strip()}
        if code_set:
            constituents = constituents[constituents["indexCode"].isin(code_set)].copy()
    if constituents.empty:
        return frame.sort_values(["date", "symbol"]).reset_index(drop=True)

    index_code_values = list(dict.fromkeys(constituents["indexCode"].astype(str).sort_values()))
    for code in index_code_values:
        member_column = f"is_index_member_{_index_code_suffix(code)}"
        weight_column = f"index_weight_{_index_code_suffix(code)}"
        name_column = f"index_name_{_index_code_suffix(code)}"
        frame[member_column] = False
        frame[weight_column] = np.nan
        if "indexName" in constituents.columns:
            frame[name_column] = pd.NA

        subset = constituents[constituents["indexCode"] == code].copy()
        snapshot_dates = subset[["date"]].drop_duplicates().sort_values("date").rename(columns={"date": "snapshot_date"})
        quote_dates = frame[["date"]].drop_duplicates().sort_values("date")
        date_map = pd.merge_asof(
            quote_dates,
            snapshot_dates,
            left_on="date",
            right_on="snapshot_date",
            direction="backward",
        )
        date_to_snapshot = dict(zip(date_map["date"], date_map["snapshot_date"]))
        lookup_columns = ["date", "symbol", "weight"]
        if "indexName" in subset.columns:
            lookup_columns.append("indexName")
        lookup = subset[lookup_columns].rename(columns={"date": "snapshot_date"})

        probe = frame[["date", "symbol"]].copy()
        probe["snapshot_date"] = probe["date"].map(date_to_snapshot)
        probe["_row"] = np.arange(len(probe))
        matched = probe.merge(lookup, on=["snapshot_date", "symbol"], how="left")
        matched.set_index("_row", inplace=True)
        is_member = matched["weight"].notna()
        row_positions = matched.index.to_numpy(dtype=int)
        frame.iloc[row_positions, frame.columns.get_loc(member_column)] = is_member.to_numpy(dtype=bool)
        frame.iloc[row_positions, frame.columns.get_loc(weight_column)] = matched["weight"].to_numpy()
        if "indexName" in matched.columns:
            frame.iloc[row_positions, frame.columns.get_loc(name_column)] = matched["indexName"].to_numpy()

    if len(index_code_values) == 1:
        suffix = _index_code_suffix(index_code_values[0])
        frame["is_index_member"] = frame[f"is_index_member_{suffix}"]
        frame["index_weight"] = frame[f"index_weight_{suffix}"]
        frame["indexCode"] = index_code_values[0]
        name_column = f"index_name_{suffix}"
        if name_column in frame:
            frame["indexName"] = frame[name_column]
    return frame.sort_values(["date", "symbol"]).reset_index(drop=True)


def merge_point_in_time_dividend_events(data: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    if data.empty or events.empty:
        return data.copy()

    merged_frames: list[pd.DataFrame] = []
    grouped_events = {
        str(symbol): group.sort_values("exDate")
        for symbol, group in events[["symbol", "exDate", "cashDividendPerShare"]].groupby("symbol", sort=False)
    }
    for symbol, quote_group in data.groupby("symbol", sort=False):
        quote_sorted = quote_group.sort_values("date").copy()
        event_group = grouped_events.get(str(symbol))
        if event_group is None or event_group.empty:
            quote_sorted["dividend_event_count_365d"] = 0.0
            quote_sorted["dividend_event_cash_365d"] = 0.0
            quote_sorted["dividend_event_days_since_last"] = np.nan
            quote_sorted["dividend_event_last_cash"] = np.nan
            merged_frames.append(quote_sorted)
            continue

        quote_dates = pd.to_datetime(quote_sorted["date"], errors="coerce")
        event_dates = pd.to_datetime(event_group["exDate"], errors="coerce").to_numpy(dtype="datetime64[ns]")
        event_cash = pd.to_numeric(event_group["cashDividendPerShare"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        cash_cumsum = np.concatenate([[0.0], np.cumsum(event_cash)])
        quote_values = quote_dates.to_numpy(dtype="datetime64[ns]")
        left_dates = quote_values - np.timedelta64(365, "D")
        right = np.searchsorted(event_dates, quote_values, side="right")
        left = np.searchsorted(event_dates, left_dates, side="left")
        trailing_cash = cash_cumsum[right] - cash_cumsum[left]
        trailing_count = right - left
        last_index = right - 1
        has_last = last_index >= 0
        last_dates = np.full(len(quote_values), np.datetime64("NaT"), dtype="datetime64[ns]")
        last_cash = np.full(len(quote_sorted), np.nan, dtype=float)
        last_dates[has_last] = event_dates[last_index[has_last]]
        last_cash[has_last] = event_cash[last_index[has_last]]
        days_since = (quote_values - last_dates) / np.timedelta64(1, "D")
        quote_sorted["dividend_event_count_365d"] = trailing_count.astype(float)
        quote_sorted["dividend_event_cash_365d"] = trailing_cash
        quote_sorted["dividend_event_days_since_last"] = pd.Series(days_since, index=quote_sorted.index).where(has_last)
        quote_sorted["dividend_event_last_cash"] = last_cash
        merged_frames.append(quote_sorted)

    merged = pd.concat(merged_frames, ignore_index=True)
    return add_robust_factor_features(merged, copy=False)


def _add_dragon_tiger_event_features(panel: pd.DataFrame) -> pd.DataFrame:
    if "dragon_tiger_count_90d" in panel:
        event_count = pd.to_numeric(panel["dragon_tiger_count_90d"], errors="coerce").fillna(0.0)
        panel["dragon_tiger_attention_score"] = (event_count.clip(lower=0.0, upper=3.0) / 3.0).clip(
            lower=0.0,
            upper=1.0,
        )
    if "dragon_tiger_amount_90d" in panel:
        amount = pd.to_numeric(panel["dragon_tiger_amount_90d"], errors="coerce")
        panel["dragon_tiger_amount_score"] = amount.groupby(panel["date"]).rank(pct=True)
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
    return panel


def merge_point_in_time_capital_flows(data: pd.DataFrame, flows: pd.DataFrame) -> pd.DataFrame:
    if data.empty or flows.empty:
        return data.copy()

    flow_fields = [column for column in CAPITAL_FLOW_FIELDS if column in flows.columns]
    if not flow_fields:
        return data.copy()

    frame = data.copy()
    frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    flow_lookup = flows[["symbol", "date", *flow_fields]].copy()
    flow_lookup["symbol"] = flow_lookup["symbol"].map(_normalize_symbol)
    flow_lookup["capitalFlowDate"] = pd.to_datetime(flow_lookup["date"], errors="coerce")
    flow_lookup = (
        flow_lookup.dropna(subset=["symbol", "capitalFlowDate"])
        .drop(columns=["date"])
        .sort_values(["capitalFlowDate", "symbol"])
        .drop_duplicates(["capitalFlowDate", "symbol"], keep="last")
    )
    frame.sort_values(["date", "symbol"], inplace=True)
    merged = pd.merge_asof(
        frame,
        flow_lookup,
        by="symbol",
        left_on="date",
        right_on="capitalFlowDate",
        direction="backward",
        allow_exact_matches=False,
        suffixes=("", "_capital_flow"),
    )
    for field in flow_fields:
        flow_column = f"{field}_capital_flow"
        if flow_column in merged.columns:
            merged[field] = merged[flow_column].combine_first(merged[field]) if field in merged else merged[flow_column]
            merged.drop(columns=[flow_column], inplace=True)

    return add_robust_factor_features(merged, copy=False)


def merge_point_in_time_margin_trades(data: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    if data.empty or trades.empty:
        return data.copy()

    trade_fields = [column for column in MARGIN_TRADE_FIELDS if column in trades.columns]
    if not trade_fields:
        return data.copy()

    frame = data.copy()
    frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    trade_lookup = trades[["symbol", "date", *trade_fields]].copy()
    trade_lookup["symbol"] = trade_lookup["symbol"].map(_normalize_symbol)
    trade_lookup["marginTradeDate"] = pd.to_datetime(trade_lookup["date"], errors="coerce")
    trade_lookup = (
        trade_lookup.dropna(subset=["symbol", "marginTradeDate"])
        .drop(columns=["date"])
        .sort_values(["marginTradeDate", "symbol"])
        .drop_duplicates(["marginTradeDate", "symbol"], keep="last")
    )
    frame.sort_values(["date", "symbol"], inplace=True)
    merged = pd.merge_asof(
        frame,
        trade_lookup,
        by="symbol",
        left_on="date",
        right_on="marginTradeDate",
        direction="backward",
        allow_exact_matches=False,
        suffixes=("", "_margin_trade"),
    )
    for field in trade_fields:
        trade_column = f"{field}_margin_trade"
        if trade_column in merged.columns:
            merged[field] = merged[trade_column].combine_first(merged[field]) if field in merged else merged[trade_column]
            merged.drop(columns=[trade_column], inplace=True)

    return add_margin_trade_features(merged, copy=False)


def merge_point_in_time_dragon_tiger_events(data: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    if data.empty or events.empty:
        return data.copy()

    frame = data.copy(deep=False)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    row_count = len(frame)
    event_count_90d = np.zeros(row_count, dtype=float)
    event_amount_90d = np.zeros(row_count, dtype=float)
    days_since_last = np.full(row_count, np.nan, dtype=float)
    max_deviation_90d = np.full(row_count, np.nan, dtype=float)

    amount_field = "amount" if "amount" in events.columns else "totalAmount" if "totalAmount" in events.columns else ""
    event_frame = events.copy()
    event_frame["date"] = pd.to_datetime(event_frame["date"], errors="coerce")
    event_frame = event_frame.dropna(subset=["date", "symbol"]).sort_values(["symbol", "date"])
    grouped_events = {
        str(symbol): group
        for symbol, group in event_frame.groupby("symbol", sort=False)
    }
    date_values = frame["date"].to_numpy(dtype="datetime64[ns]")
    for symbol, positions in frame.groupby("symbol", sort=False).indices.items():
        event_group = grouped_events.get(str(symbol))
        if event_group is None or event_group.empty:
            continue

        order = np.argsort(date_values[positions])
        sorted_positions = positions[order]
        event_dates = pd.to_datetime(event_group["date"], errors="coerce").to_numpy(dtype="datetime64[ns]")
        event_amount = (
            pd.to_numeric(event_group[amount_field], errors="coerce").fillna(0.0).to_numpy(dtype=float)
            if amount_field
            else np.zeros(len(event_group), dtype=float)
        )
        event_deviation = (
            pd.to_numeric(event_group["deviationPct"], errors="coerce").to_numpy(dtype=float)
            if "deviationPct" in event_group
            else np.full(len(event_group), np.nan, dtype=float)
        )
        amount_cumsum = np.concatenate([[0.0], np.cumsum(event_amount)])
        quote_values = date_values[sorted_positions]
        left_dates = quote_values - np.timedelta64(90, "D")
        right = np.searchsorted(event_dates, quote_values, side="left")
        left = np.searchsorted(event_dates, left_dates, side="left")
        trailing_amount = amount_cumsum[right] - amount_cumsum[left]
        trailing_count = right - left
        last_index = right - 1
        has_last = last_index >= 0
        last_dates = np.full(len(quote_values), np.datetime64("NaT"), dtype="datetime64[ns]")
        last_dates[has_last] = event_dates[last_index[has_last]]
        days_since = (quote_values - last_dates) / np.timedelta64(1, "D")
        max_deviation = _range_max_abs(event_deviation, left, right)
        event_count_90d[sorted_positions] = trailing_count.astype(float)
        event_amount_90d[sorted_positions] = trailing_amount
        days_since_last[sorted_positions] = np.where(has_last, days_since, np.nan)
        max_deviation_90d[sorted_positions] = max_deviation

    frame["dragon_tiger_count_90d"] = event_count_90d
    frame["dragon_tiger_amount_90d"] = event_amount_90d
    frame["dragon_tiger_days_since_last"] = days_since_last
    frame["dragon_tiger_max_deviation_90d"] = max_deviation_90d
    return _add_dragon_tiger_event_features(frame)


def merge_point_in_time_announcement_events(data: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    if data.empty or events.empty:
        return data.copy()

    frame = data.copy(deep=False)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    row_count = len(frame)
    count_30d = np.zeros(row_count, dtype=float)
    count_90d = np.zeros(row_count, dtype=float)
    count_180d = np.zeros(row_count, dtype=float)
    count_365d = np.zeros(row_count, dtype=float)
    buyback_count_180d = np.zeros(row_count, dtype=float)
    dividend_count_365d = np.zeros(row_count, dtype=float)
    financing_count_365d = np.zeros(row_count, dtype=float)
    reorg_count_365d = np.zeros(row_count, dtype=float)
    risk_alert_count_365d = np.zeros(row_count, dtype=float)
    report_count_365d = np.zeros(row_count, dtype=float)
    days_since_last = np.full(row_count, np.nan, dtype=float)

    event_frame = events.copy()
    event_frame["date"] = pd.to_datetime(event_frame["date"], errors="coerce")
    event_frame["symbol"] = event_frame["symbol"].map(_normalize_symbol)
    missing_flags = [
        f"announcement_is_{category}"
        for category in ANNOUNCEMENT_CATEGORY_KEYWORDS
        if f"announcement_is_{category}" not in event_frame.columns
    ]
    if missing_flags:
        event_frame = _add_announcement_category_flags(event_frame)
    event_frame = event_frame.dropna(subset=["date", "symbol"]).sort_values(["symbol", "date"])
    grouped_events = {str(symbol): group for symbol, group in event_frame.groupby("symbol", sort=False)}
    date_values = frame["date"].to_numpy(dtype="datetime64[ns]")
    for symbol, positions in frame.groupby("symbol", sort=False).indices.items():
        event_group = grouped_events.get(str(symbol))
        if event_group is None or event_group.empty:
            continue

        positions_array = np.asarray(positions, dtype=int)
        order = np.argsort(date_values[positions_array])
        sorted_positions = positions_array[order]
        event_dates = pd.to_datetime(event_group["date"], errors="coerce").to_numpy(dtype="datetime64[ns]")
        quote_values = date_values[sorted_positions]
        right = np.searchsorted(event_dates, quote_values, side="left")
        left_30d = np.searchsorted(event_dates, quote_values - np.timedelta64(30, "D"), side="left")
        left_90d = np.searchsorted(event_dates, quote_values - np.timedelta64(90, "D"), side="left")
        left_180d = np.searchsorted(event_dates, quote_values - np.timedelta64(180, "D"), side="left")
        left_365d = np.searchsorted(event_dates, quote_values - np.timedelta64(365, "D"), side="left")

        count_30d[sorted_positions] = (right - left_30d).astype(float)
        count_90d[sorted_positions] = (right - left_90d).astype(float)
        count_180d[sorted_positions] = (right - left_180d).astype(float)
        count_365d[sorted_positions] = (right - left_365d).astype(float)
        buyback_count_180d[sorted_positions] = _range_sum(
            event_group["announcement_is_buyback"].to_numpy(dtype=float),
            left_180d,
            right,
        )
        dividend_count_365d[sorted_positions] = _range_sum(
            event_group["announcement_is_dividend"].to_numpy(dtype=float),
            left_365d,
            right,
        )
        financing_count_365d[sorted_positions] = _range_sum(
            event_group["announcement_is_financing"].to_numpy(dtype=float),
            left_365d,
            right,
        )
        reorg_count_365d[sorted_positions] = _range_sum(
            event_group["announcement_is_reorg"].to_numpy(dtype=float),
            left_365d,
            right,
        )
        risk_alert_count_365d[sorted_positions] = _range_sum(
            event_group["announcement_is_risk_alert"].to_numpy(dtype=float),
            left_365d,
            right,
        )
        report_count_365d[sorted_positions] = _range_sum(
            event_group["announcement_is_report"].to_numpy(dtype=float),
            left_365d,
            right,
        )

        last_index = right - 1
        has_last = last_index >= 0
        last_dates = np.full(len(quote_values), np.datetime64("NaT"), dtype="datetime64[ns]")
        last_dates[has_last] = event_dates[last_index[has_last]]
        days_since = (quote_values - last_dates) / np.timedelta64(1, "D")
        days_since_last[sorted_positions] = np.where(has_last, days_since, np.nan)

    features = pd.DataFrame(
        {
            "announcement_count_30d": count_30d,
            "announcement_count_90d": count_90d,
            "announcement_count_180d": count_180d,
            "announcement_count_365d": count_365d,
            "announcement_buyback_count_180d": buyback_count_180d,
            "announcement_dividend_count_365d": dividend_count_365d,
            "announcement_financing_count_365d": financing_count_365d,
            "announcement_reorg_count_365d": reorg_count_365d,
            "announcement_risk_alert_count_365d": risk_alert_count_365d,
            "announcement_report_count_365d": report_count_365d,
            "announcement_days_since_last": days_since_last,
        },
        index=frame.index,
    )
    frame = pd.concat([frame, features], axis=1)
    return add_robust_factor_features(frame, copy=False)


def _range_sum(values: np.ndarray, left: np.ndarray, right: np.ndarray) -> np.ndarray:
    clean = np.nan_to_num(np.asarray(values, dtype=float), nan=0.0)
    cumsum = np.concatenate([[0.0], np.cumsum(clean)])
    return cumsum[right] - cumsum[left]


def _range_max_abs(values: np.ndarray, left: np.ndarray, right: np.ndarray) -> np.ndarray:
    result = np.full(len(left), np.nan, dtype=float)
    if len(values) == 0 or len(left) == 0:
        return result
    clean = np.abs(np.asarray(values, dtype=float))
    clean = np.where(np.isnan(clean), -np.inf, clean)
    lengths = right - left
    valid = lengths > 0
    if not bool(valid.any()):
        return result

    valid_lengths = lengths[valid].astype(int)
    query_levels = np.floor(np.log2(valid_lengths)).astype(int)
    max_level = int(query_levels.max())
    sparse: list[np.ndarray] = [clean]
    for level in range(1, max_level + 1):
        offset = 1 << (level - 1)
        previous = sparse[-1]
        sparse.append(np.maximum(previous[:-offset], previous[offset:]))

    query_left = left[valid].astype(int)
    query_right = right[valid].astype(int)
    values_out = np.empty(len(query_left), dtype=float)
    for level in np.unique(query_levels):
        mask = query_levels == level
        span = 1 << int(level)
        values_out[mask] = np.maximum(sparse[int(level)][query_left[mask]], sparse[int(level)][query_right[mask] - span])
    values_out[values_out == -np.inf] = np.nan
    result[np.flatnonzero(valid)] = values_out
    return result


def fundamental_factor_coverage(data: pd.DataFrame, fields: Iterable[str] = ("roe", "dividend_yield")) -> dict[str, object]:
    rows = int(len(data))
    metrics: dict[str, object] = {"rows": rows, "fields": {}}
    for field in fields:
        if field not in data.columns:
            metrics["fields"][field] = {"present": False, "coverage": 0.0, "non_null": 0}
            continue
        non_null = int(pd.to_numeric(data[field], errors="coerce").notna().sum())
        metrics["fields"][field] = {
            "present": True,
            "coverage": float(non_null / rows) if rows else 0.0,
            "non_null": non_null,
        }
    return metrics


def field_coverage(data: pd.DataFrame, fields: Iterable[str]) -> dict[str, object]:
    rows = int(len(data))
    metrics: dict[str, object] = {"rows": rows, "fields": {}}
    for field in fields:
        if field not in data.columns:
            metrics["fields"][field] = {"present": False, "coverage": 0.0, "non_null": 0}
            continue
        values = data[field]
        if values.dtype == object or str(values.dtype).startswith("string"):
            valid = values.notna() & (values.astype(str).str.strip() != "")
        else:
            valid = values.notna()
        non_null = int(valid.sum())
        metrics["fields"][field] = {
            "present": True,
            "coverage": float(non_null / rows) if rows else 0.0,
            "non_null": non_null,
        }
    return metrics


def index_constituent_coverage(data: pd.DataFrame, index_codes: Iterable[str] | None = None) -> dict[str, object]:
    rows = int(len(data))
    codes = [str(code).strip().upper() for code in (index_codes or []) if str(code).strip()]
    if not codes:
        codes = []
        for column in data.columns:
            if column.startswith("is_index_member_"):
                codes.append(column.removeprefix("is_index_member_"))
    metrics: dict[str, object] = {"rows": rows, "indexes": {}}
    for code in codes:
        suffix = _index_code_suffix(code)
        member_column = f"is_index_member_{suffix}"
        weight_column = f"index_weight_{suffix}"
        if member_column not in data:
            metrics["indexes"][code] = {"present": False, "member_rows": 0, "member_coverage": 0.0, "weight_non_null": 0}
            continue
        members = data[member_column].fillna(False).astype(bool)
        weights = pd.to_numeric(data[weight_column], errors="coerce") if weight_column in data else pd.Series(np.nan, index=data.index)
        metrics["indexes"][code] = {
            "present": True,
            "member_rows": int(members.sum()),
            "member_coverage": float(members.mean()) if rows else 0.0,
            "weight_non_null": int(weights[members].notna().sum()),
            "dates_with_members": int(data.loc[members, "date"].nunique()) if "date" in data else 0,
            "symbols_with_members": int(data.loc[members, "symbol"].nunique()) if "symbol" in data else 0,
        }
    return metrics


def _index_code_suffix(index_code: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in str(index_code).strip().upper()).strip("_")


def _optional_asset_requested(
    required_fields: set[str] | None,
    fields: Iterable[str],
    *,
    prefixes: Iterable[str] = (),
) -> bool:
    if required_fields is None:
        return True
    field_set = {str(field) for field in fields}
    if required_fields & field_set:
        return True
    prefix_tuple = tuple(str(prefix) for prefix in prefixes)
    return bool(prefix_tuple and any(field.startswith(prefix_tuple) for field in required_fields))


def load_production_asset_panel(
    asset_root: str | Path,
    *,
    start: str,
    end: str,
    historical_stock_master_path: str | Path | None = None,
    market_panel_path: str | Path | None = None,
    universe_size: int = 100,
    universe_lookback_days: int = 20,
    universe_min_history_days: int = 20,
    min_stock_master_rows: int = 3000,
    min_delisted_rows: int = 50,
    include_bj: bool = False,
    require_production_data: bool = True,
    fundamental_fields: Iterable[str] | None = None,
    required_data_fields: Iterable[str] | None = None,
    use_cache: bool = True,
) -> DataLoadResult:
    progress_enabled = os.environ.get("A_SHARE_FACTORY_PROGRESS") == "1"
    started_at = time.perf_counter()
    last_progress_at = started_at

    def mark_progress(label: str) -> None:
        nonlocal last_progress_at
        if not progress_enabled:
            return
        now = time.perf_counter()
        print(
            f"[production-load] {label} +{now - last_progress_at:.1f}s total={now - started_at:.1f}s",
            file=sys.stderr,
            flush=True,
        )
        last_progress_at = now

    root = Path(asset_root)
    stock_path = Path(historical_stock_master_path) if historical_stock_master_path else root / "stock_master" / "historical_stock_master.csv"
    quote_path = Path(market_panel_path) if market_panel_path else root / "market" / "daily_quotes.csv"
    factor_path = root / "fundamentals" / "fundamental_factors.csv"
    dividend_event_path = root / "fundamentals" / "dividend_events.csv"
    capital_flow_path = root / "market" / "daily_fund_flows.csv"
    margin_trade_path = root / "market" / "margin_trades.csv"
    dragon_tiger_path = root / "events" / "dragon_tiger_details.csv"
    announcement_path = root / "events" / "announcements.csv"
    index_constituent_path = root / "index" / "index_constituents.csv"
    industry_path = root / "industry" / "industry_classification.csv"
    required_field_set = None if required_data_fields is None else {str(field) for field in required_data_fields}
    load_dividend_events = dividend_event_path.exists() and _optional_asset_requested(
        required_field_set,
        (
            "dividend_event_count_365d",
            "dividend_event_cash_365d",
            "dividend_event_yield_365d",
            "dividend_event_regular_score",
            "dividend_event_recent_score",
            "dividend_event_cash_score",
            "dividend_event_quality_score",
        ),
        prefixes=("dividend_event_",),
    )
    load_capital_flows = capital_flow_path.exists() and _optional_asset_requested(
        required_field_set,
        (
            "capitalFlowDate",
            *CAPITAL_FLOW_FIELDS,
            "main_net_inflow_to_amount",
            "large_net_inflow_to_amount",
            "xlarge_net_inflow_to_amount",
            "main_flow_strength_score",
            "large_flow_strength_score",
            "xlarge_flow_strength_score",
            "main_flow_positive_score",
            "flow_persistence_20d_raw",
            "flow_persistence_20d_score",
            "flow_reversal_guard_score",
            "capital_flow_quality_score",
        ),
    )
    load_margin_trades = margin_trade_path.exists() and _optional_asset_requested(
        required_field_set,
        (*MARGIN_TRADE_FIELDS, *MARGIN_TRADE_FEATURE_FIELDS),
        prefixes=("margin_", "short_balance_"),
    )
    load_dragon_tiger_events = dragon_tiger_path.exists() and _optional_asset_requested(
        required_field_set,
        (
            "dragon_tiger_count_90d",
            "dragon_tiger_amount_90d",
            "dragon_tiger_days_since_last",
            "dragon_tiger_max_deviation_90d",
            "dragon_tiger_attention_score",
            "dragon_tiger_amount_score",
            "dragon_tiger_recency_score",
            "dragon_tiger_cooldown_score",
            "dragon_tiger_event_score",
        ),
        prefixes=("dragon_tiger_",),
    )
    load_announcement_events = announcement_path.exists() and _optional_asset_requested(
        required_field_set,
        ANNOUNCEMENT_EVENT_FEATURE_FIELDS,
        prefixes=("announcement_",),
    )
    load_index_constituents = index_constituent_path.exists() and _optional_asset_requested(
        required_field_set,
        ("is_index_member", "index_weight", "indexCode", "indexName"),
        prefixes=("is_index_member", "index_weight", "index_name"),
    )
    load_industry = industry_path.exists() and _optional_asset_requested(
        required_field_set,
        ("industryLV1Name", "industryName"),
        prefixes=("industry",),
    )

    cache_key_payload = _production_panel_cache_key_payload(
        asset_root=root,
        stock_path=stock_path,
        quote_path=quote_path,
        factor_path=factor_path,
        dividend_event_path=dividend_event_path,
        capital_flow_path=capital_flow_path,
        margin_trade_path=margin_trade_path,
        dragon_tiger_path=dragon_tiger_path,
        announcement_path=announcement_path,
        index_constituent_path=index_constituent_path,
        industry_path=industry_path,
        start=start,
        end=end,
        universe_size=universe_size,
        universe_lookback_days=universe_lookback_days,
        universe_min_history_days=universe_min_history_days,
        min_stock_master_rows=min_stock_master_rows,
        min_delisted_rows=min_delisted_rows,
        include_bj=include_bj,
        require_production_data=require_production_data,
        fundamental_fields=fundamental_fields,
        required_data_fields=required_field_set,
    )
    cache_path = _production_panel_cache_path(root, cache_key_payload)
    if use_cache and _production_panel_cache_enabled():
        cached = _load_production_panel_cache(cache_path, cache_key_payload)
        if cached is not None:
            if require_production_data:
                enforce_production_data(cached, min_stock_master_rows=min_stock_master_rows)
            mark_progress("production_panel_cache_hit")
            return cached

    stock_master = load_stock_master_csv(stock_path)
    mark_progress("stock_master_loaded")
    stock_validation = validate_stock_master_asset(
        stock_master.master,
        start=start,
        end=end,
        min_rows=min_stock_master_rows,
        min_delisted_rows=min_delisted_rows,
        include_bj=include_bj,
    )
    if stock_validation.get("status") != "production_ready":
        raise DataSourceError(
            "Historical stock master did not pass production validation: "
            f"{'; '.join(str(item) for item in stock_validation.get('caveats', [])[:5])}"
        )

    symbols = symbols_from_stock_master(stock_master.master, start=start, end=end, include_bj=include_bj)
    if not symbols:
        raise DataSourceError("Historical stock master produced no eligible symbols for the requested period.")
    mark_progress("eligible_symbols_built")

    loaded = load_historical_market_panel(quote_path, start=start, end=end, symbols=symbols)
    mark_progress("daily_quotes_loaded")
    _enforce_panel_symbol_coverage(loaded, symbols)
    enriched = enrich_panel_with_stock_master(loaded.data, stock_master.master)
    mark_progress("stock_master_enriched")
    stock_master_filter = apply_point_in_time_stock_master_filter(enriched)
    mark_progress("stock_master_pit_filtered")
    loaded = DataLoadResult(
        data=stock_master_filter.data,
        metadata=replace(
            loaded.metadata,
            source=f"{loaded.metadata.source}+{stock_master.source}+full_historical_stock_master+{stock_master_filter.source}",
            notes=loaded.metadata.notes
            + stock_master.notes
            + (
                f"Historical stock master rows: {len(stock_master.master)}.",
                f"Historical stock master minimum rows: {min_stock_master_rows}.",
                f"Historical stock master minimum delisted rows: {min_delisted_rows}.",
                f"Historical stock master snapshot sha256: {stock_master.data_hash}",
            )
            + stock_master_filter.notes
            + (f"Point-in-time stock master data sha256: {stock_master_filter.data_hash}",),
            data_hash=stock_master_filter.data_hash,
        ),
        stock_master=stock_master.master,
    )
    has_dividend_events = load_dividend_events
    if factor_path.exists():
        factors = load_fundamental_factor_asset(factor_path, end=end, symbols=symbols, fields=fundamental_fields)
        mark_progress("fundamental_factors_loaded")
        merged = merge_point_in_time_fundamental_factors(loaded.data, factors, fields=fundamental_fields)
        mark_progress("fundamental_factors_merged")
        if not has_dividend_events:
            merged = add_robust_factor_features(merged, copy=False)
            mark_progress("robust_features_after_fundamentals")
        coverage = fundamental_factor_coverage(merged)
        field_text = "all" if fundamental_fields is None else ", ".join(sorted({str(field) for field in fundamental_fields}))
        loaded = DataLoadResult(
            data=merged,
            metadata=replace(
                loaded.metadata,
                source=f"{loaded.metadata.source}+fundamental_factor_asset+pit_fundamental_factors",
                notes=loaded.metadata.notes
                + (
                    f"Loaded canonical fundamental factor asset: {factor_path}.",
                    "Fundamental factors are merged point-in-time by symbol using the latest factor date on or before each quote date.",
                    f"Fundamental factor rows: {len(factors)}.",
                    f"Fundamental factor fields requested for this load: {field_text}.",
                    f"Fundamental factor coverage: {json.dumps(coverage, ensure_ascii=False, sort_keys=True)}.",
                ),
                data_hash=_light_panel_hash(merged),
            ),
            stock_master=loaded.stock_master,
        )
    if load_dividend_events:
        dividend_events = load_dividend_event_asset(dividend_event_path, end=end, symbols=symbols)
        mark_progress("dividend_events_loaded")
        merged = merge_point_in_time_dividend_events(loaded.data, dividend_events)
        mark_progress("dividend_events_merged_and_features_added")
        coverage = fundamental_factor_coverage(
            merged,
            fields=(
                "dividend_event_count_365d",
                "dividend_event_cash_365d",
                "dividend_event_recent_score",
                "dividend_event_regular_score",
            ),
        )
        loaded = DataLoadResult(
            data=merged,
            metadata=replace(
                loaded.metadata,
                source=f"{loaded.metadata.source}+dividend_event_asset+pit_dividend_events",
                notes=loaded.metadata.notes
                + (
                    f"Loaded canonical dividend event asset: {dividend_event_path}.",
                    "Dividend event features are merged point-in-time with exDate <= quote date and a trailing 365-day window.",
                    f"Dividend event rows: {len(dividend_events)}.",
                    f"Dividend event feature coverage: {json.dumps(coverage, ensure_ascii=False, sort_keys=True)}.",
                ),
                data_hash=_light_panel_hash(merged),
            ),
            stock_master=loaded.stock_master,
        )
    if load_capital_flows:
        capital_flows = load_capital_flow_asset(capital_flow_path, end=end, symbols=symbols)
        mark_progress("capital_flows_loaded")
        merged = merge_point_in_time_capital_flows(loaded.data, capital_flows)
        mark_progress("capital_flows_merged_and_features_added")
        coverage = field_coverage(
            merged,
            fields=(
                "capitalFlowDate",
                "mainNetInflow",
                "netInflowLarge",
                "netInflowXlarge",
                "main_flow_strength_score",
                "flow_persistence_20d_score",
                "capital_flow_quality_score",
            ),
        )
        loaded = DataLoadResult(
            data=merged,
            metadata=replace(
                loaded.metadata,
                source=f"{loaded.metadata.source}+capital_flow_asset+pit_capital_flows",
                notes=loaded.metadata.notes
                + (
                    f"Loaded canonical daily fund flow asset: {capital_flow_path}.",
                    "Daily fund flows are merged strictly point-in-time using the latest flow date before each quote date; same-day flow rows are excluded to avoid after-close leakage.",
                    f"Daily fund flow rows: {len(capital_flows)}.",
                    f"Daily fund flow feature coverage: {json.dumps(coverage, ensure_ascii=False, sort_keys=True)}.",
                ),
                data_hash=_light_panel_hash(merged),
            ),
            stock_master=loaded.stock_master,
        )
    if load_margin_trades:
        margin_trades = load_margin_trade_asset(margin_trade_path, end=end, symbols=symbols)
        mark_progress("margin_trades_loaded")
        merged = merge_point_in_time_margin_trades(loaded.data, margin_trades)
        mark_progress("margin_trades_merged_and_features_added")
        coverage = field_coverage(merged, fields=MARGIN_TRADE_FEATURE_FIELDS)
        loaded = DataLoadResult(
            data=merged,
            metadata=replace(
                loaded.metadata,
                source=f"{loaded.metadata.source}+margin_trade_asset+pit_margin_trades",
                notes=loaded.metadata.notes
                + (
                    f"Loaded canonical margin trade asset: {margin_trade_path}.",
                    "Margin trade rows are merged strictly point-in-time using the latest financing/securities-lending date before each quote date; same-day margin rows are excluded to avoid after-close leakage.",
                    f"Margin trade rows: {len(margin_trades)}.",
                    f"Margin trade feature coverage: {json.dumps(coverage, ensure_ascii=False, sort_keys=True)}.",
                ),
                data_hash=_light_panel_hash(merged),
            ),
            stock_master=loaded.stock_master,
        )
    if load_dragon_tiger_events:
        dragon_tiger_events = load_dragon_tiger_detail_asset(dragon_tiger_path, end=end, symbols=symbols)
        mark_progress("dragon_tiger_events_loaded")
        merged = merge_point_in_time_dragon_tiger_events(loaded.data, dragon_tiger_events)
        mark_progress("dragon_tiger_events_merged_and_features_added")
        coverage = field_coverage(
            merged,
            fields=(
                "dragon_tiger_count_90d",
                "dragon_tiger_amount_90d",
                "dragon_tiger_days_since_last",
                "dragon_tiger_attention_score",
                "dragon_tiger_cooldown_score",
                "dragon_tiger_event_score",
            ),
        )
        loaded = DataLoadResult(
            data=merged,
            metadata=replace(
                loaded.metadata,
                source=f"{loaded.metadata.source}+dragon_tiger_asset+pit_dragon_tiger_events",
                notes=loaded.metadata.notes
                + (
                    f"Loaded canonical dragon tiger detail asset: {dragon_tiger_path}.",
                    "Dragon tiger event features are computed from events strictly before each quote date with a trailing 90-day window; same-day events are excluded.",
                    f"Dragon tiger event rows: {len(dragon_tiger_events)}.",
                    f"Dragon tiger feature coverage: {json.dumps(coverage, ensure_ascii=False, sort_keys=True)}.",
                ),
                data_hash=_light_panel_hash(merged),
            ),
            stock_master=loaded.stock_master,
        )
    if load_announcement_events:
        announcement_events = load_announcement_event_asset(announcement_path, end=end, symbols=symbols)
        mark_progress("announcement_events_loaded")
        merged = merge_point_in_time_announcement_events(loaded.data, announcement_events)
        mark_progress("announcement_events_merged_and_features_added")
        coverage = field_coverage(merged, fields=ANNOUNCEMENT_EVENT_FEATURE_FIELDS)
        loaded = DataLoadResult(
            data=merged,
            metadata=replace(
                loaded.metadata,
                source=f"{loaded.metadata.source}+announcement_event_asset+pit_announcement_events",
                notes=loaded.metadata.notes
                + (
                    f"Loaded canonical announcement event asset: {announcement_path}.",
                    "Announcement event features are computed from factual disclosures strictly before each quote date; same-day announcements are excluded.",
                    f"Announcement event rows: {len(announcement_events)}.",
                    f"Announcement event feature coverage: {json.dumps(coverage, ensure_ascii=False, sort_keys=True)}.",
                ),
                data_hash=_light_panel_hash(merged),
            ),
            stock_master=loaded.stock_master,
        )
    if load_industry:
        industry = load_industry_classification_asset(industry_path, end=end, symbols=symbols)
        mark_progress("industry_loaded")
        merged = merge_point_in_time_industry_classification(loaded.data, industry)
        mark_progress("industry_merged")
        coverage = field_coverage(merged, fields=("industryLV1Name", "industryName"))
        latest_only_rows = int(merged["isLatestOnly"].fillna(False).astype(bool).sum()) if "isLatestOnly" in merged else 0
        loaded = DataLoadResult(
            data=merged,
            metadata=replace(
                loaded.metadata,
                source=f"{loaded.metadata.source}+industry_classification_asset+pit_industry_classification",
                notes=loaded.metadata.notes
                + (
                    f"Loaded canonical industry classification asset: {industry_path}.",
                    "Industry labels are merged point-in-time by symbol using the latest classification date on or before each quote date.",
                    f"Industry classification rows: {len(industry)}.",
                    f"Industry classification feature coverage: {json.dumps(coverage, ensure_ascii=False, sort_keys=True)}.",
                    f"Latest-only industry proxy rows in merged panel: {latest_only_rows}.",
                ),
                data_hash=_light_panel_hash(merged),
            ),
            stock_master=loaded.stock_master,
        )
    if load_index_constituents:
        constituents = load_index_constituent_asset(index_constituent_path, end=end, symbols=symbols)
        mark_progress("index_constituents_loaded")
        merged = merge_point_in_time_index_constituents(loaded.data, constituents)
        mark_progress("index_constituents_merged")
        index_codes = tuple(sorted(str(code) for code in constituents["indexCode"].dropna().astype(str).unique()))
        coverage = index_constituent_coverage(merged, index_codes=index_codes)
        latest_only_rows = int(merged["isLatestOnly"].fillna(False).astype(bool).sum()) if "isLatestOnly" in merged else 0
        loaded = DataLoadResult(
            data=merged,
            metadata=replace(
                loaded.metadata,
                source=f"{loaded.metadata.source}+index_constituent_asset+pit_index_constituents",
                notes=loaded.metadata.notes
                + (
                    f"Loaded canonical index constituent asset: {index_constituent_path}.",
                    "Index constituents are merged point-in-time by index snapshot date: each snapshot applies until the next snapshot for the same index.",
                    f"Index constituent rows: {len(constituents)}.",
                    f"Index constituent codes: {', '.join(index_codes)}.",
                    f"Index constituent feature coverage: {json.dumps(coverage, ensure_ascii=False, sort_keys=True)}.",
                    f"Latest-only index proxy rows in merged panel: {latest_only_rows}.",
                ),
                data_hash=_light_panel_hash(merged),
            ),
            stock_master=loaded.stock_master,
        )
    pit = apply_point_in_time_liquidity_universe(
        loaded.data,
        top_n=universe_size,
        lookback_days=universe_lookback_days,
        min_history_days=universe_min_history_days,
    )
    mark_progress("liquidity_universe_built")
    loaded = DataLoadResult(
        data=pit.data,
        metadata=replace(
            loaded.metadata,
            source=f"{loaded.metadata.source}+{pit.source}",
            notes=loaded.metadata.notes + pit.notes + (f"Point-in-time universe data sha256: {pit.data_hash}",),
            data_hash=pit.data_hash,
        ),
        universe=pit.universe,
        stock_master=loaded.stock_master,
    )
    if require_production_data:
        enforce_production_data(loaded, min_stock_master_rows=min_stock_master_rows)
        mark_progress("production_data_enforced")
    if use_cache and _production_panel_cache_enabled():
        _write_production_panel_cache(cache_path, cache_key_payload, loaded)
        mark_progress("production_panel_cache_written")
    return loaded


def _production_panel_cache_enabled() -> bool:
    return os.environ.get("A_SHARE_PRODUCTION_PANEL_CACHE", "1") != "0"


def _production_panel_cache_key_payload(
    *,
    asset_root: Path,
    stock_path: Path,
    quote_path: Path,
    factor_path: Path,
    dividend_event_path: Path,
    capital_flow_path: Path,
    margin_trade_path: Path,
    dragon_tiger_path: Path,
    announcement_path: Path,
    index_constituent_path: Path,
    industry_path: Path,
    start: str,
    end: str,
    universe_size: int,
    universe_lookback_days: int,
    universe_min_history_days: int,
    min_stock_master_rows: int,
    min_delisted_rows: int,
    include_bj: bool,
    require_production_data: bool,
    fundamental_fields: Iterable[str] | None,
    required_data_fields: Iterable[str] | None,
) -> dict[str, object]:
    fields = None if fundamental_fields is None else tuple(sorted({str(field) for field in fundamental_fields}))
    required_fields = None if required_data_fields is None else tuple(sorted({str(field) for field in required_data_fields}))
    return {
        "cache_version": PRODUCTION_PANEL_CACHE_VERSION,
        "asset_root": str(asset_root.resolve()),
        "start": start,
        "end": end,
        "universe_size": int(universe_size),
        "universe_lookback_days": int(universe_lookback_days),
        "universe_min_history_days": int(universe_min_history_days),
        "min_stock_master_rows": int(min_stock_master_rows),
        "min_delisted_rows": int(min_delisted_rows),
        "include_bj": bool(include_bj),
        "require_production_data": bool(require_production_data),
        "fundamental_fields": fields,
        "required_data_fields": required_fields,
        "assets": {
            "stock_master": _cache_asset_fingerprint(stock_path),
            "daily_quotes": _cache_asset_fingerprint(quote_path),
            "fundamental_factors": _cache_asset_fingerprint(factor_path),
            "dividend_events": _cache_asset_fingerprint(dividend_event_path),
            "daily_fund_flows": _cache_asset_fingerprint(capital_flow_path),
            "margin_trades": _cache_asset_fingerprint(margin_trade_path),
            "dragon_tiger_details": _cache_asset_fingerprint(dragon_tiger_path),
            "announcements": _cache_asset_fingerprint(announcement_path),
            "index_constituents": _cache_asset_fingerprint(index_constituent_path),
            "industry_classification": _cache_asset_fingerprint(industry_path),
        },
    }


def _cache_asset_fingerprint(path: Path) -> dict[str, object]:
    resolved = path.resolve()
    if not path.exists():
        return {"path": str(resolved), "exists": False, "size": 0, "mtime_ns": 0}
    stat = path.stat()
    return {
        "path": str(resolved),
        "exists": True,
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def _production_panel_cache_path(asset_root: Path, payload: dict[str, object]) -> Path:
    key = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    return asset_root / "cache" / "production_panels" / f"production_panel_{key}.pkl"


def _load_production_panel_cache(path: Path, payload: dict[str, object]) -> DataLoadResult | None:
    if not path.exists():
        return None
    try:
        with path.open("rb") as handle:
            cached = pickle.load(handle)
    except Exception:
        return None
    if not isinstance(cached, dict) or cached.get("cache_key") != payload:
        return None
    loaded = cached.get("loaded")
    if not isinstance(loaded, DataLoadResult):
        return None
    return replace(
        loaded,
        metadata=replace(
            loaded.metadata,
            source=f"{loaded.metadata.source}+production_panel_cache_hit",
            notes=loaded.metadata.notes + (f"Production panel cache hit: {path}.",),
        ),
    )


def load_frozen_production_panel_cache(
    path: str | Path,
    *,
    require_production_data: bool = True,
    min_stock_master_rows: int = 3000,
) -> DataLoadResult:
    cache_path = Path(path)
    if not cache_path.exists():
        raise DataSourceError(f"Frozen production panel cache does not exist: {cache_path}")
    try:
        with cache_path.open("rb") as handle:
            cached = pickle.load(handle)
    except Exception as exc:
        raise DataSourceError(f"Frozen production panel cache could not be loaded: {cache_path}") from exc

    loaded = cached.get("loaded") if isinstance(cached, dict) else cached
    if not isinstance(loaded, DataLoadResult):
        raise DataSourceError(f"Frozen production panel cache has unsupported payload shape: {cache_path}")
    if require_production_data:
        enforce_production_data(loaded, min_stock_master_rows=min_stock_master_rows)
    return replace(
        loaded,
        metadata=replace(
            loaded.metadata,
            source=f"{loaded.metadata.source}+frozen_production_panel_cache",
            notes=loaded.metadata.notes
            + (
                f"Explicit frozen production panel cache loaded: {cache_path}.",
                "Frozen cache mode is for accelerated research reruns when canonical source assets are temporarily unavailable; refresh canonical assets before final promotion.",
            ),
        ),
    )


def _write_production_panel_cache(path: Path, payload: dict[str, object], loaded: DataLoadResult) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        with tmp_path.open("wb") as handle:
            pickle.dump({"cache_key": payload, "loaded": loaded}, handle, protocol=pickle.HIGHEST_PROTOCOL)
        tmp_path.replace(path)
        write_production_panel_cache_sidecar(path, payload, loaded)
    except Exception:
        return


def load_investoday_panel_sharded(
    symbols: Iterable[str],
    *,
    start: str,
    end: str,
    output_dir: str | Path,
    shard_size: int = 80,
    page_size: int = 500,
    api_batch_size: int = 20,
    include_limit_flags: bool = True,
    include_financials: bool = True,
    cache_dir: str | Path | None = "cache/investoday_api",
    refresh_cache: bool = False,
    resume: bool = True,
) -> ShardedLoadResult:
    symbol_tuple = tuple(str(symbol).strip().upper() for symbol in symbols if str(symbol).strip())
    if not symbol_tuple:
        raise DataSourceError("Sharded loader requires at least one symbol.")
    if shard_size < 1:
        raise DataSourceError("shard_size must be positive.")

    shard_dir = Path(output_dir)
    shard_dir.mkdir(parents=True, exist_ok=True)
    shards = build_symbol_shards(symbol_tuple, shard_size=shard_size)
    manifest: dict[str, object] = {
        "start": start,
        "end": end,
        "shard_size": shard_size,
        "total_symbols": len(symbol_tuple),
        "total_shards": len(shards),
        "shards": [],
    }
    frames: list[pd.DataFrame] = []
    for index, shard_symbols in enumerate(shards, start=1):
        shard_id = f"shard_{index:04d}"
        csv_path = shard_dir / f"{shard_id}.csv"
        entry: dict[str, object] = {
            "shard_id": shard_id,
            "symbols": list(shard_symbols),
            "symbol_count": len(shard_symbols),
            "path": str(csv_path),
            "status": "pending",
        }
        try:
            if resume and csv_path.exists() and not refresh_cache:
                shard_data = pd.read_csv(csv_path)
                entry["status"] = "reused"
            else:
                loaded = load_investoday_panel(
                    shard_symbols,
                    start=start,
                    end=end,
                    page_size=page_size,
                    api_batch_size=api_batch_size,
                    include_limit_flags=include_limit_flags,
                    include_financials=include_financials,
                    cache_dir=cache_dir,
                    refresh_cache=refresh_cache,
                )
                shard_data = loaded.data
                shard_data.to_csv(csv_path, index=False)
                entry["status"] = "fetched"
            entry["rows"] = int(len(shard_data))
            entry["data_hash"] = dataframe_hash(shard_data)
            frames.append(shard_data)
        except Exception as exc:
            entry["status"] = "failed"
            entry["error"] = str(exc)
        manifest["shards"].append(entry)
        _write_manifest(shard_dir / "shard_manifest.json", manifest)

    failed = [item for item in manifest["shards"] if isinstance(item, dict) and item.get("status") == "failed"]
    if failed:
        raise DataSourceError(f"Sharded Investoday load failed for {len(failed)} shards. See {shard_dir / 'shard_manifest.json'}")
    if not frames:
        raise DataSourceError("Sharded Investoday load produced no frames.")

    data = prepare_backtest_panel(pd.concat(frames, ignore_index=True))
    manifest["status"] = "succeeded"
    manifest["rows"] = int(len(data))
    manifest["data_hash"] = dataframe_hash(data)
    _write_manifest(shard_dir / "shard_manifest.json", manifest)
    loaded = DataLoadResult(
        data=data,
        metadata=DataSourceMetadata(
            source="investoday:stock/adjusted-quotes+sharded_loader",
            symbols=tuple(sorted(data["symbol"].unique())),
            start_date=start,
            end_date=end,
            notes=(
                f"Investoday sharded loader output: {shard_dir}.",
                f"Shard size: {shard_size}; shards: {len(shards)}.",
                "Each shard is cached as CSV and tracked in shard_manifest.json for resume/retry.",
            ),
            data_hash=str(manifest["data_hash"]),
        ),
    )
    return ShardedLoadResult(loaded=loaded, manifest=manifest, shard_dir=shard_dir)


def _light_panel_hash(data: pd.DataFrame) -> str:
    if data.empty:
        return dataframe_hash(data)
    dates = pd.to_datetime(data["date"], errors="coerce") if "date" in data else pd.Series(dtype="datetime64[ns]")
    symbols = data["symbol"].astype(str) if "symbol" in data else pd.Series(dtype=object)
    payload = {
        "rows": int(len(data)),
        "columns": [str(column) for column in data.columns],
        "min_date": dates.min().isoformat() if not dates.empty and dates.notna().any() else "",
        "max_date": dates.max().isoformat() if not dates.empty and dates.notna().any() else "",
        "symbols": int(symbols.nunique()) if not symbols.empty else 0,
        "head_keys": data[[column for column in ("date", "symbol") if column in data.columns]].head(200).to_json(
            date_format="iso", orient="split", default_handler=str
        ),
        "tail_keys": data[[column for column in ("date", "symbol") if column in data.columns]].tail(200).to_json(
            date_format="iso", orient="split", default_handler=str
        ),
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def build_symbol_shards(symbols: Iterable[str], *, shard_size: int) -> list[tuple[str, ...]]:
    symbol_tuple = tuple(symbols)
    return [tuple(symbol_tuple[start : start + shard_size]) for start in range(0, len(symbol_tuple), shard_size)]


def _enforce_panel_symbol_coverage(loaded: DataLoadResult, expected_symbols: tuple[str, ...]) -> None:
    loaded_set = set(loaded.metadata.symbols)
    expected_set = set(expected_symbols)
    missing = sorted(expected_set - loaded_set)
    if missing:
        preview = ", ".join(missing[:10])
        raise DataSourceError(
            f"Historical market panel is missing {len(missing)} eligible stock-master symbols. "
            f"Examples: {preview}."
        )


def render_shard_manifest_markdown(manifest: dict[str, object]) -> str:
    lines = [
        "## Sharded Load Manifest",
        "",
        f"Status: `{manifest.get('status', 'unknown')}`",
        f"Symbols: {manifest.get('total_symbols', 0)}",
        f"Shards: {manifest.get('total_shards', 0)}",
        f"Rows: {manifest.get('rows', 0)}",
        "",
        "| Shard | Status | Symbols | Rows | Error |",
        "|---|---|---:|---:|---|",
    ]
    shards = manifest.get("shards", [])
    if isinstance(shards, list):
        for item in shards:
            if not isinstance(item, dict):
                continue
            lines.append(
                "| {shard} | {status} | {symbols} | {rows} | {error} |".format(
                    shard=_markdown_cell(str(item.get("shard_id", ""))),
                    status=_markdown_cell(str(item.get("status", ""))),
                    symbols=item.get("symbol_count", 0),
                    rows=item.get("rows", 0),
                    error=_markdown_cell(str(item.get("error", ""))),
                )
            )
    lines.append("")
    return "\n".join(lines)


def write_shard_manifest_artifacts(output_dir: str | Path, manifest: dict[str, object]) -> dict[str, Path]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "shard_manifest.json"
    markdown_path = target / "shard_manifest.md"
    json_path.write_text(json.dumps(_json_ready(manifest), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_shard_manifest_markdown(manifest), encoding="utf-8")
    return {"shard_manifest": json_path, "shard_manifest_report": markdown_path}


def _asset_summary(
    name: str,
    path: Path,
    required_columns: tuple[str, ...],
    *,
    required: bool,
    scope: str,
) -> dict[str, object]:
    summary: dict[str, object] = {
        "name": name,
        "scope": scope,
        "required": required,
        "path": str(path),
        "exists": path.exists(),
        "rows": 0,
        "columns": [],
        "missing_columns": list(required_columns),
        "min_date": "",
        "max_date": "",
        "data_hash": "",
    }
    if not path.exists() or not path.is_file():
        return summary
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        summary["error"] = str(exc)
        return summary
    summary["rows"] = int(len(frame))
    summary["columns"] = [str(column) for column in frame.columns]
    summary["missing_columns"] = [column for column in required_columns if column not in frame.columns]
    if "date" in frame.columns and not frame.empty:
        dates = pd.to_datetime(frame["date"], errors="coerce").dropna()
        if not dates.empty:
            summary["min_date"] = dates.min().strftime("%Y-%m-%d")
            summary["max_date"] = dates.max().strftime("%Y-%m-%d")
    summary["data_hash"] = dataframe_hash(frame) if not frame.empty else ""
    return summary


def _write_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.write_text(json.dumps(_json_ready(manifest), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _json_ready(value: object) -> object:
    if isinstance(value, pd.DataFrame):
        return value.to_dict(orient="records")
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _date_with_dash(value: str) -> str:
    compact = str(value).replace("-", "")
    if len(compact) != 8:
        return str(value)
    return f"{compact[:4]}-{compact[4:6]}-{compact[6:]}"


def _normalize_yield_series(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if values.dropna().gt(1.0).mean() > 0.5:
        values = values / 100.0
    return values


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
