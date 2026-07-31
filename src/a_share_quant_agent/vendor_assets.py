from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from .data_sources import (
    DataSourceError,
    dataframe_hash,
    load_stock_master_csv,
    symbols_from_stock_master,
    validate_stock_master_asset,
)
from .historical_assets import (
    CAPITAL_FLOW_FIELDS,
    FINANCIAL_ALPHA_FIELDS,
    MARGIN_TRADE_FIELDS,
    discover_data_assets,
    write_asset_inventory,
    write_data_asset_manifest_artifacts,
)


CANONICAL_ASSETS = {
    "stock_master": {
        "path": "stock_master/historical_stock_master.csv",
        "required": ("symbol", "stockCode", "exchangeCode", "stockName", "stockType", "listDate", "delistDate", "listStatus"),
    },
    "daily_quotes": {
        "path": "market/daily_quotes.csv",
        "required": ("date", "symbol", "open", "high", "low", "close", "volume", "amount"),
    },
    "fundamental_factors": {
        "path": "fundamentals/fundamental_factors.csv",
        "required": ("date", "symbol", "roe", "dividend_yield"),
    },
    "fundamental_factors": {
        "path": "fundamentals/fundamental_factors.csv",
        "required": ("date", "symbol", "roe", "dividend_yield"),
    },
    "daily_fund_flows": {
        "path": "market/daily_fund_flows.csv",
        "required": ("date", "symbol", "mainNetInflow", "netInflowLarge", "netInflowXlarge"),
    },
    "margin_trades": {
        "path": "market/margin_trades.csv",
        "required": ("date", "symbol", "marginBalance", "marginBuyAmount", "marginRepayAmount"),
    },
    "dragon_tiger_details": {
        "path": "events/dragon_tiger_details.csv",
        "required": ("date", "symbol", "abnormalType"),
    },
    "announcements": {
        "path": "events/announcements.csv",
        "required": ("date", "symbol", "title"),
    },
    "index_constituents": {
        "path": "index/index_constituents.csv",
        "required": ("date", "indexCode", "symbol", "weight"),
    },
    "industry_classification": {
        "path": "industry/industry_classification.csv",
        "required": ("date", "symbol", "industryLV1Name", "industryName"),
    },
}


FIELD_DEFINITIONS = {
    "symbol": ("标准证券代码", "A股标准代码，格式为 600000.SH / 000001.SZ / 920001.BJ。"),
    "stockCode": ("证券代码", "六位证券代码，不含交易所后缀。"),
    "exchangeCode": ("交易所", "SH、SZ 或 BJ。"),
    "stockName": ("证券简称", "证券在对应日期或主表中的简称。"),
    "stockType": ("证券类型", "A股、A、ASHARE 等会被识别为 A 股。"),
    "listDate": ("上市日期", "点时上市资格起始日期。"),
    "delistDate": ("退市日期", "点时上市资格结束日期；空值表示尚未退市或供应商未提供。"),
    "listStatus": ("上市状态", "当前或供应商定义的上市状态；生产 PIT 过滤以 listDate/delistDate 为准。"),
    "date": ("交易日期", "日频行情或分类生效日期。"),
    "open": ("开盘价", "复权或未复权口径由供应商 mapping/provenance 声明。"),
    "high": ("最高价", "日内最高成交价。"),
    "low": ("最低价", "日内最低成交价。"),
    "close": ("收盘价", "日收盘价。"),
    "volume": ("成交量", "供应商原始单位，需在 mapping/provenance 中确认股/手口径。"),
    "amount": ("成交额", "供应商原始币种与单位，生产研究默认按人民币金额理解。"),
    "pe": ("市盈率", "市盈率，通常使用 TTM 口径；需供应商确认。"),
    "pb": ("市净率", "市净率，通常使用 LF 或最新披露净资产口径；需供应商确认。"),
    "roe": ("净资产收益率", "ROE，必须使用 publishDate/date 作为点时可见日期，不能按报告期结束日偷看未来。"),
    "dividend_yield": ("股息率", "股息率或股息率 TTM；若供应商以百分数提供，导入器会规范为小数。"),
    "publishDate": ("披露日期", "基本面指标对市场可见的日期；生产研究以该日期或 date 做 point-in-time 合并。"),
    "reportPeriodEnd": ("报告期末", "财务指标所属报告期结束日，仅用于审计和解释，不作为可见日期。"),
    "factorSource": ("因子来源", "供应商或内部计算口径标记。"),
    "indexCode": ("指数代码", "指数或组合代码。"),
    "weight": ("成分权重", "指数成分权重，单位需由供应商确认。"),
    "industryLV1Name": ("一级行业", "点时一级行业分类名称。"),
    "industryName": ("行业名称", "点时细分行业分类名称。"),
    "mainNetInflow": ("主力净流入", "日频主力净流入金额，导入后按严格前一可见日合并，单位需供应商确认。"),
    "netInflowLarge": ("大单净流入", "日频大单净流入金额，导入后按严格前一可见日合并，单位需供应商确认。"),
    "netInflowXlarge": ("超大单净流入", "日频超大单净流入金额，导入后按严格前一可见日合并，单位需供应商确认。"),
    "mainNetInflowRatio": ("主力净流入占比", "日频主力净流入比例，若供应商以百分数提供需在 mapping/provenance 中说明。"),
    "capitalFlowSource": ("资金流来源", "资金流供应商、接口和口径标记。"),
    "marginBalance": ("融资余额", "日频融资余额，导入后按严格前一可见日合并，单位需供应商确认。"),
    "marginBuyAmount": ("融资买入额", "日频融资买入额，导入后按严格前一可见日合并，单位需供应商确认。"),
    "marginRepayAmount": ("融资偿还额", "日频融资偿还额，导入后按严格前一可见日合并，单位需供应商确认。"),
    "shortBalanceVolume": ("融券余量", "日频融券余量，股/手口径需供应商确认。"),
    "shortSellVolume": ("融券卖出量", "日频融券卖出量，股/手口径需供应商确认。"),
    "shortBalanceAmount": ("融券余额金额", "日频融券余额金额，导入后按严格前一可见日合并，单位需供应商确认。"),
    "marginShortBalance": ("融资融券余额", "融资融券合计余额或供应商定义的两融余额，单位需供应商确认。"),
    "marginTradeSource": ("融资融券来源", "融资融券供应商、接口和口径标记。"),
    "abnormalType": ("龙虎榜异常类型", "龙虎榜上榜原因或供应商类型代码。"),
    "abnormalTypeName": ("龙虎榜异常类型名称", "龙虎榜上榜原因名称。"),
    "deviationPct": ("偏离幅度", "龙虎榜相关涨跌幅偏离值，百分数或小数口径需供应商确认。"),
    "dragonTigerSource": ("龙虎榜来源", "龙虎榜供应商、接口和口径标记。"),
    "title": ("公告标题", "公司公告标题；只作为事实文本分类和计数依据，不做主观利好/利空判断。"),
    "announcementType": ("公告类型", "供应商公告类别或类型名称；只用于事实分组。"),
    "announcementSource": ("公告来源", "公告供应商、接口和口径标记。"),
    "announcementId": ("公告 ID", "供应商公告唯一标识；用于追溯和去重。"),
    "riskType": ("公告风险类型", "供应商给出的风险类型代码；只作事实字段保留。"),
    "announcementContentType": ("公告内容类别", "供应商公告内容类别代码。"),
    "guid": ("公告编号", "供应商公告编号或 GUID。"),
    "url": ("公告链接", "公告原文或供应商详情页链接。"),
}


def load_vendor_mapping(path: str | Path) -> dict[str, object]:
    mapping_path = Path(path)
    if not mapping_path.exists():
        raise DataSourceError(f"Vendor mapping does not exist: {mapping_path}")
    text = mapping_path.read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = _parse_nested_yaml(text)
    if not isinstance(payload, dict):
        raise DataSourceError("Vendor mapping must be a dictionary.")
    assets = payload.get("assets")
    if not isinstance(assets, dict) or not assets:
        raise DataSourceError("Vendor mapping must contain an assets mapping.")
    return payload


def import_vendor_data_assets(
    mapping: dict[str, object],
    *,
    asset_root: str | Path,
    start: str | None = None,
    end: str | None = None,
    min_stock_master_rows: int = 3000,
    min_delisted_rows: int = 50,
    include_bj: bool = False,
    chunk_size: int | None = None,
    write_parquet_copy: bool = False,
) -> dict[str, object]:
    root = Path(asset_root)
    root.mkdir(parents=True, exist_ok=True)
    vendor = str(mapping.get("vendor", "unknown_vendor"))
    imported: dict[str, dict[str, object]] = {}
    paths: dict[str, Path] = {}
    assets = mapping.get("assets") if isinstance(mapping.get("assets"), dict) else {}

    for asset_name in (
        "stock_master",
        "daily_quotes",
        "fundamental_factors",
        "daily_fund_flows",
        "margin_trades",
        "dragon_tiger_details",
        "announcements",
        "index_constituents",
        "industry_classification",
    ):
        asset_spec = assets.get(asset_name) if isinstance(assets, dict) else None
        if not isinstance(asset_spec, dict):
            continue
        destination = root / str(CANONICAL_ASSETS[asset_name]["path"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        frame = _materialize_asset(
            asset_name,
            asset_spec,
            destination=destination,
            start=start,
            end=end,
            chunk_size=chunk_size,
        )
        profile = _asset_profile(frame)
        profile["path"] = str(destination)
        profile["data_hash"] = dataframe_hash(frame) if not frame.empty else ""
        imported[asset_name] = profile
        paths[asset_name] = destination
        if write_parquet_copy:
            parquet_path = destination.with_suffix(".parquet")
            _write_parquet_copy(frame, parquet_path)
            paths[f"{asset_name}_parquet"] = parquet_path

    validation = validate_production_asset_bundle(
        root,
        start=start,
        end=end,
        min_stock_master_rows=min_stock_master_rows,
        min_delisted_rows=min_delisted_rows,
        include_bj=include_bj,
    )
    manifest_dir = root / "manifests" / "production_import"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    validation_paths = write_production_asset_validation_artifacts(manifest_dir, validation)
    inventory_paths = write_asset_inventory(
        manifest_dir,
        discover_data_assets(root, start=start, end=end, min_stock_master_rows=min_stock_master_rows),
    )
    definition_path = write_data_definition_artifact(manifest_dir, mapping, imported)
    manifest = build_vendor_import_manifest(
        mapping,
        asset_root=root,
        imported=imported,
        paths={**paths, **validation_paths, **inventory_paths, "data_definition": definition_path},
        validation=validation,
        start=start,
        end=end,
        vendor=vendor,
    )
    manifest_paths = write_data_asset_manifest_artifacts(manifest_dir, manifest)
    return {
        "manifest": manifest,
        "validation": validation,
        "imported": imported,
        "paths": {**paths, **validation_paths, **inventory_paths, "data_definition": definition_path, **manifest_paths},
    }


def validate_production_asset_bundle(
    asset_root: str | Path,
    *,
    start: str | None = None,
    end: str | None = None,
    min_stock_master_rows: int = 3000,
    min_delisted_rows: int = 50,
    include_bj: bool = False,
    min_symbol_coverage_rate: float = 0.98,
    min_median_symbol_date_coverage: float = 0.90,
    max_duplicate_key_count: int = 0,
) -> dict[str, object]:
    root = Path(asset_root)
    stock_master_path = root / str(CANONICAL_ASSETS["stock_master"]["path"])
    quotes_path = root / str(CANONICAL_ASSETS["daily_quotes"]["path"])
    factor_path = root / str(CANONICAL_ASSETS["fundamental_factors"]["path"])
    flow_path = root / str(CANONICAL_ASSETS["daily_fund_flows"]["path"])
    margin_path = root / str(CANONICAL_ASSETS["margin_trades"]["path"])
    dragon_tiger_path = root / str(CANONICAL_ASSETS["dragon_tiger_details"]["path"])
    announcement_path = root / str(CANONICAL_ASSETS["announcements"]["path"])
    index_path = root / str(CANONICAL_ASSETS["index_constituents"]["path"])
    stock_validation: dict[str, object] = {
        "status": "invalid",
        "coverage_level": "missing",
        "hard_failed": 1,
        "caveats": [f"Missing stock master asset: {stock_master_path}."],
    }
    expected_symbols: tuple[str, ...] = ()
    if stock_master_path.exists():
        try:
            stock_master = load_stock_master_csv(stock_master_path)
            stock_validation = validate_stock_master_asset(
                stock_master.master,
                start=start,
                end=end,
                min_rows=min_stock_master_rows,
                min_delisted_rows=min_delisted_rows,
                include_bj=include_bj,
            )
            expected_symbols = symbols_from_stock_master(stock_master.master, start=start, end=end, include_bj=include_bj)
        except Exception as exc:
            stock_validation = {
                "status": "invalid",
                "coverage_level": "error",
                "hard_failed": 1,
                "caveats": [f"Stock master validation failed: {exc}"],
            }

    quote_metrics = _empty_quote_metrics(str(quotes_path))
    if quotes_path.exists():
        try:
            quote_frame = _canonicalize_daily_quotes(_read_table(quotes_path, "csv"), {}, start=start, end=end)
            quote_metrics = _quote_coverage_metrics(quote_frame, expected_symbols)
        except Exception as exc:
            quote_metrics = _empty_quote_metrics(str(quotes_path))
            quote_metrics["error"] = str(exc)

    factor_metrics = _empty_fundamental_factor_metrics(str(factor_path))
    if factor_path.exists():
        try:
            factor_frame = _canonicalize_fundamental_factors(_read_table(factor_path, "csv"), {}, start=start, end=end)
            factor_metrics = _fundamental_factor_metrics(factor_frame, expected_symbols)
            factor_metrics["path"] = str(factor_path)
        except Exception as exc:
            factor_metrics = _empty_fundamental_factor_metrics(str(factor_path))
            factor_metrics["error"] = str(exc)

    flow_metrics = _empty_daily_fund_flow_metrics(str(flow_path))
    if flow_path.exists():
        try:
            flow_frame = _canonicalize_daily_fund_flows(_read_table(flow_path, "csv"), {}, start=start, end=end)
            flow_metrics = _daily_fund_flow_metrics(flow_frame, expected_symbols)
            flow_metrics["path"] = str(flow_path)
        except Exception as exc:
            flow_metrics = _empty_daily_fund_flow_metrics(str(flow_path))
            flow_metrics["error"] = str(exc)

    margin_metrics = _empty_margin_trade_metrics(str(margin_path))
    if margin_path.exists():
        try:
            margin_frame = _canonicalize_margin_trades(_read_table(margin_path, "csv"), {}, start=start, end=end)
            margin_metrics = _margin_trade_metrics(margin_frame, expected_symbols)
            margin_metrics["path"] = str(margin_path)
        except Exception as exc:
            margin_metrics = _empty_margin_trade_metrics(str(margin_path))
            margin_metrics["error"] = str(exc)

    dragon_tiger_metrics = _empty_dragon_tiger_detail_metrics(str(dragon_tiger_path))
    if dragon_tiger_path.exists():
        try:
            dragon_tiger_frame = _canonicalize_dragon_tiger_details(_read_table(dragon_tiger_path, "csv"), {}, start=start, end=end)
            dragon_tiger_metrics = _dragon_tiger_detail_metrics(dragon_tiger_frame, expected_symbols)
            dragon_tiger_metrics["path"] = str(dragon_tiger_path)
        except Exception as exc:
            dragon_tiger_metrics = _empty_dragon_tiger_detail_metrics(str(dragon_tiger_path))
            dragon_tiger_metrics["error"] = str(exc)

    announcement_metrics = _empty_announcement_event_metrics(str(announcement_path))
    if announcement_path.exists():
        try:
            announcement_frame = _canonicalize_announcements(_read_table(announcement_path, "csv"), {}, start=start, end=end)
            announcement_metrics = _announcement_event_metrics(announcement_frame, expected_symbols)
            announcement_metrics["path"] = str(announcement_path)
        except Exception as exc:
            announcement_metrics = _empty_announcement_event_metrics(str(announcement_path))
            announcement_metrics["error"] = str(exc)

    index_metrics = _empty_index_constituent_metrics(str(index_path))
    if index_path.exists():
        try:
            index_frame = _canonicalize_index_constituents(_read_table(index_path, "csv"), {}, start=start, end=end)
            index_metrics = _index_constituent_metrics(index_frame, expected_symbols)
            index_metrics["path"] = str(index_path)
        except Exception as exc:
            index_metrics = _empty_index_constituent_metrics(str(index_path))
            index_metrics["error"] = str(exc)

    factor_metrics = _empty_fundamental_factor_metrics(str(root / str(CANONICAL_ASSETS["fundamental_factors"]["path"])))
    factor_path = root / str(CANONICAL_ASSETS["fundamental_factors"]["path"])
    if factor_path.exists():
        try:
            factor_frame = _canonicalize_fundamental_factors(_read_table(factor_path, "csv"), {}, start=start, end=end)
            factor_metrics = _fundamental_factor_metrics(factor_frame, expected_symbols)
            factor_metrics["path"] = str(factor_path)
        except Exception as exc:
            factor_metrics = _empty_fundamental_factor_metrics(str(factor_path))
            factor_metrics["error"] = str(exc)

    factor_field_coverage = (
        factor_metrics.get("field_coverage") if isinstance(factor_metrics.get("field_coverage"), dict) else {}
    )
    quote_field_coverage = quote_metrics.get("field_coverage") if isinstance(quote_metrics.get("field_coverage"), dict) else {}
    effective_field_coverage = {
        field: max(
            float(factor_field_coverage.get(field, 0.0) or 0.0),
            float(quote_field_coverage.get(field, 0.0) or 0.0),
        )
        for field in ("roe", "dividend_yield", "pe", "pb")
    }
    checks = [
        _check(
            "stock_master_production_ready",
            stock_validation.get("status") == "production_ready",
            "hard",
            f"Stock master status is {stock_validation.get('status', 'n/a')}.",
        ),
        _check(
            "daily_quotes_exists",
            quotes_path.exists() and not quote_metrics.get("error"),
            "hard",
            f"Daily quote asset path: {quotes_path}.",
        ),
        _check(
            "daily_quote_rows",
            int(quote_metrics.get("rows", 0) or 0) > 0,
            "hard",
            f"Daily quote rows: {quote_metrics.get('rows', 0)}.",
        ),
        _check(
            "eligible_symbol_coverage",
            float(quote_metrics.get("eligible_symbol_coverage_rate", 0.0) or 0.0) >= min_symbol_coverage_rate,
            "hard",
            "Eligible symbol coverage "
            f"{_format_rate(quote_metrics.get('eligible_symbol_coverage_rate', 0.0))}; required >= {_format_rate(min_symbol_coverage_rate)}.",
        ),
        _check(
            "duplicate_daily_keys",
            int(quote_metrics.get("duplicate_key_count", 0) or 0) <= max_duplicate_key_count,
            "hard",
            f"Duplicate (date, symbol) rows: {quote_metrics.get('duplicate_key_count', 0)}.",
        ),
        _check(
            "median_symbol_date_coverage",
            float(quote_metrics.get("median_symbol_date_coverage", 0.0) or 0.0) >= min_median_symbol_date_coverage,
            "hard",
            "Median symbol date coverage "
            f"{_format_rate(quote_metrics.get('median_symbol_date_coverage', 0.0))}; "
            f"required >= {_format_rate(min_median_symbol_date_coverage)}.",
        ),
        _check(
            "price_integrity",
            int(quote_metrics.get("bad_price_rows", 0) or 0) == 0,
            "hard",
            f"Rows with nonpositive or internally inconsistent OHLC prices: {quote_metrics.get('bad_price_rows', 0)}.",
        ),
        _check(
            "amount_volume_integrity",
            int(quote_metrics.get("bad_amount_volume_rows", 0) or 0) == 0,
            "hard",
            f"Rows with negative amount/volume: {quote_metrics.get('bad_amount_volume_rows', 0)}.",
        ),
        _check(
            "date_range_start",
            not start or _date_leq(quote_metrics.get("min_date", ""), start),
            "warn",
            f"Quote min date {quote_metrics.get('min_date', '') or 'n/a'} should be on or before {start or 'n/a'}.",
        ),
        _check(
            "date_range_end",
            not end or _date_geq(quote_metrics.get("max_date", ""), end),
            "warn",
            f"Quote max date {quote_metrics.get('max_date', '') or 'n/a'} should be on or after {end or 'n/a'}.",
        ),
    ]
    if factor_path.exists():
        checks.extend(
            [
                _check(
                    "fundamental_factor_schema",
                    not factor_metrics.get("error"),
                    "warn",
                    f"Fundamental factor asset path: {factor_path}.",
                ),
                _check(
                    "roe_factor_coverage",
                    float(effective_field_coverage.get("roe", 0.0) or 0.0) >= 0.50,
                    "warn",
                    "ROE effective symbol coverage "
                    f"{_format_rate(effective_field_coverage.get('roe', 0.0))}; recommended >= 50.00%.",
                ),
                _check(
                    "dividend_yield_factor_coverage",
                    float(effective_field_coverage.get("dividend_yield", 0.0) or 0.0) >= 0.50,
                    "warn",
                    "Dividend yield effective symbol coverage "
                    f"{_format_rate(effective_field_coverage.get('dividend_yield', 0.0))}; recommended >= 50.00%.",
                ),
                _check(
                    "fundamental_duplicate_keys",
                    int(factor_metrics.get("duplicate_key_count", 0) or 0) == 0,
                    "warn",
                    f"Duplicate fundamental (date, symbol) rows: {factor_metrics.get('duplicate_key_count', 0)}.",
                ),
            ]
        )
    if flow_path.exists():
        checks.extend(
            [
                _check(
                    "daily_fund_flow_schema",
                    not flow_metrics.get("error"),
                    "warn",
                    f"Daily fund flow asset path: {flow_path}.",
                ),
                _check(
                    "daily_fund_flow_duplicate_keys",
                    int(flow_metrics.get("duplicate_key_count", 0) or 0) == 0,
                    "warn",
                    f"Duplicate daily fund flow (date, symbol) rows: {flow_metrics.get('duplicate_key_count', 0)}.",
                ),
            ]
        )
    if margin_path.exists():
        checks.extend(
            [
                _check(
                    "margin_trade_schema",
                    not margin_metrics.get("error"),
                    "warn",
                    f"Margin trade asset path: {margin_path}.",
                ),
                _check(
                    "margin_trade_duplicate_keys",
                    int(margin_metrics.get("duplicate_key_count", 0) or 0) == 0,
                    "warn",
                    f"Duplicate margin trade (date, symbol) rows: {margin_metrics.get('duplicate_key_count', 0)}.",
                ),
            ]
        )
    if dragon_tiger_path.exists():
        checks.extend(
            [
                _check(
                    "dragon_tiger_detail_schema",
                    not dragon_tiger_metrics.get("error"),
                    "warn",
                    f"Dragon tiger detail asset path: {dragon_tiger_path}.",
                ),
                _check(
                    "dragon_tiger_duplicate_keys",
                    int(dragon_tiger_metrics.get("duplicate_key_count", 0) or 0) == 0,
                    "warn",
                    f"Duplicate dragon tiger detail keys: {dragon_tiger_metrics.get('duplicate_key_count', 0)}.",
                ),
            ]
        )
    if announcement_path.exists():
        checks.extend(
            [
                _check(
                    "announcement_event_schema",
                    not announcement_metrics.get("error"),
                    "warn",
                    f"Announcement event asset path: {announcement_path}.",
                ),
                _check(
                    "announcement_duplicate_keys",
                    int(announcement_metrics.get("duplicate_key_count", 0) or 0) == 0,
                    "warn",
                    f"Duplicate announcement event keys: {announcement_metrics.get('duplicate_key_count', 0)}.",
                ),
            ]
        )
    if index_path.exists():
        checks.extend(
            [
                _check(
                    "index_constituent_schema",
                    not index_metrics.get("error"),
                    "warn",
                    f"Index constituent asset path: {index_path}.",
                ),
                _check(
                    "index_constituent_duplicate_keys",
                    int(index_metrics.get("duplicate_key_count", 0) or 0) == 0,
                    "warn",
                    f"Duplicate index constituent (date, indexCode, symbol) rows: {index_metrics.get('duplicate_key_count', 0)}.",
                ),
                _check(
                    "index_constituent_not_latest_only",
                    not bool(index_metrics.get("latest_only_all", False)),
                    "warn",
                    "Index constituent asset is marked latest-only; do not use it as historical PIT membership.",
                ),
                _check(
                    "index_constituent_snapshot_depth",
                    int(index_metrics.get("snapshot_date_count", 0) or 0) > 1,
                    "warn",
                    f"Index constituent snapshot dates: {index_metrics.get('snapshot_date_count', 0)}.",
                ),
            ]
        )
    if factor_path.exists():
        checks.extend(
            [
                _check(
                    "fundamental_factor_schema",
                    not factor_metrics.get("error"),
                    "warn",
                    f"Fundamental factor asset path: {factor_path}.",
                ),
                _check(
                    "roe_factor_coverage",
                    float((factor_metrics.get("field_coverage") or {}).get("roe", 0.0) or 0.0) >= 0.50,
                    "warn",
                    "ROE factor symbol coverage "
                    f"{_format_rate((factor_metrics.get('field_coverage') or {}).get('roe', 0.0))}; recommended >= 50.00%.",
                ),
                _check(
                    "dividend_yield_factor_coverage",
                    float((factor_metrics.get("field_coverage") or {}).get("dividend_yield", 0.0) or 0.0) >= 0.50,
                    "warn",
                    "Dividend yield factor symbol coverage "
                    f"{_format_rate((factor_metrics.get('field_coverage') or {}).get('dividend_yield', 0.0))}; recommended >= 50.00%.",
                ),
                _check(
                    "fundamental_duplicate_keys",
                    int(factor_metrics.get("duplicate_key_count", 0) or 0) == 0,
                    "warn",
                    f"Duplicate fundamental (date, symbol) rows: {factor_metrics.get('duplicate_key_count', 0)}.",
                ),
            ]
        )
    hard_failed = sum(1 for item in checks if item["severity"] == "hard" and not item["passed"])
    warnings = sum(1 for item in checks if item["severity"] == "warn" and not item["passed"])
    if hard_failed == 0:
        status = "production_ready"
    elif stock_validation.get("status") == "production_ready" and int(quote_metrics.get("rows", 0) or 0) > 0:
        status = "needs_review"
    else:
        status = "blocked"
    caveats = [str(item["detail"]) for item in checks if item["severity"] == "hard" and not item["passed"]]
    caveats.extend(str(item) for item in stock_validation.get("caveats", []) or [])
    return {
        "schema_version": 1,
        "status": status,
        "production_data_ready": status == "production_ready",
        "hard_failed": hard_failed,
        "warnings": warnings,
        "start_date": start or "",
        "end_date": end or "",
        "checks": checks,
        "caveats": caveats,
        "stock_master_validation": stock_validation,
        "quote_metrics": quote_metrics,
        "fundamental_factor_metrics": factor_metrics,
        "daily_fund_flow_metrics": flow_metrics,
        "margin_trade_metrics": margin_metrics,
        "dragon_tiger_detail_metrics": dragon_tiger_metrics,
        "announcement_event_metrics": announcement_metrics,
        "index_constituent_metrics": index_metrics,
        "effective_factor_coverage": effective_field_coverage,
        "notes": [
            "This validation is for the canonical production asset paths under data_assets/.",
            "A production-ready result means the data bundle can enter serious historical research; strategy gates still run separately.",
            "fundamentals/fundamental_factors.csv is optional for production_data_ready, but required to run Strategy Factory templates that use roe or dividend_yield.",
            "market/daily_fund_flows.csv, market/margin_trades.csv, events/dragon_tiger_details.csv, and events/announcements.csv are optional behavior/event alpha assets; loader usage is strictly point-in-time.",
            "index/index_constituents.csv is optional for production_data_ready, but required for strategies that request index membership filtering.",
        ],
    }


def render_production_asset_validation_markdown(validation: dict[str, object]) -> str:
    quote = validation.get("quote_metrics") if isinstance(validation.get("quote_metrics"), dict) else {}
    stock = validation.get("stock_master_validation") if isinstance(validation.get("stock_master_validation"), dict) else {}
    factors = validation.get("fundamental_factor_metrics") if isinstance(validation.get("fundamental_factor_metrics"), dict) else {}
    flows = validation.get("daily_fund_flow_metrics") if isinstance(validation.get("daily_fund_flow_metrics"), dict) else {}
    margins = validation.get("margin_trade_metrics") if isinstance(validation.get("margin_trade_metrics"), dict) else {}
    dragon_tiger = (
        validation.get("dragon_tiger_detail_metrics") if isinstance(validation.get("dragon_tiger_detail_metrics"), dict) else {}
    )
    announcements = (
        validation.get("announcement_event_metrics") if isinstance(validation.get("announcement_event_metrics"), dict) else {}
    )
    index_metrics = validation.get("index_constituent_metrics") if isinstance(validation.get("index_constituent_metrics"), dict) else {}
    factor_coverage = factors.get("field_coverage") if isinstance(factors.get("field_coverage"), dict) else {}
    flow_coverage = flows.get("field_coverage") if isinstance(flows.get("field_coverage"), dict) else {}
    margin_coverage = margins.get("field_coverage") if isinstance(margins.get("field_coverage"), dict) else {}
    dragon_tiger_coverage = (
        dragon_tiger.get("field_coverage") if isinstance(dragon_tiger.get("field_coverage"), dict) else {}
    )
    announcement_coverage = (
        announcements.get("field_coverage") if isinstance(announcements.get("field_coverage"), dict) else {}
    )
    quote_coverage = quote.get("field_coverage") if isinstance(quote.get("field_coverage"), dict) else {}
    effective_coverage = (
        validation.get("effective_factor_coverage") if isinstance(validation.get("effective_factor_coverage"), dict) else {}
    )
    quote_coverage = quote.get("field_coverage") if isinstance(quote.get("field_coverage"), dict) else {}
    effective_coverage = (
        validation.get("effective_factor_coverage") if isinstance(validation.get("effective_factor_coverage"), dict) else {}
    )
    lines = [
        "## Production Asset Validation",
        "",
        f"Status: `{validation.get('status', 'n/a')}`",
        f"Production data ready: {'yes' if validation.get('production_data_ready') else 'no'}",
        f"Hard failed: {validation.get('hard_failed', 0)}",
        f"Warnings: {validation.get('warnings', 0)}",
        f"Range: `{validation.get('start_date', '')}` to `{validation.get('end_date', '')}`",
        "",
        "### Stock Master",
        "",
        f"Status: `{stock.get('status', 'n/a')}`",
        f"Coverage level: `{stock.get('coverage_level', 'n/a')}`",
        f"Hard failed: {stock.get('hard_failed', 0)}",
        "",
        "### Daily Quotes",
        "",
        f"Rows: {quote.get('rows', 0)}",
        f"Unique symbols: {quote.get('unique_symbols', 0)}",
        f"Eligible symbols: {quote.get('expected_symbols', 0)}",
        f"Covered eligible symbols: {quote.get('covered_eligible_symbols', 0)}",
        f"Eligible symbol coverage: {_format_rate(quote.get('eligible_symbol_coverage_rate', 0.0))}",
        f"Trading dates: {quote.get('trading_dates', 0)}",
        f"Median symbol date coverage: {_format_rate(quote.get('median_symbol_date_coverage', 0.0))}",
        f"Duplicate keys: {quote.get('duplicate_key_count', 0)}",
        f"Bad OHLC rows: {quote.get('bad_price_rows', 0)}",
        f"Bad amount/volume rows: {quote.get('bad_amount_volume_rows', 0)}",
        f"Daily quote PE/PB coverage: {_format_rate(quote_coverage.get('pe', 0.0))} / {_format_rate(quote_coverage.get('pb', 0.0))}",
        f"Daily quote dividend yield coverage: {_format_rate(quote_coverage.get('dividend_yield', 0.0))}",
        f"Date range: {quote.get('min_date', '') or 'n/a'} to {quote.get('max_date', '') or 'n/a'}",
        "",
        "### Fundamental Factors",
        "",
        f"Exists: {'yes' if (validation.get('fundamental_factor_metrics') or {}).get('exists') else 'no'}",
        f"Rows: {(validation.get('fundamental_factor_metrics') or {}).get('rows', 0)}",
        f"Unique symbols: {(validation.get('fundamental_factor_metrics') or {}).get('unique_symbols', 0)}",
        f"ROE symbol coverage: {_format_rate(((validation.get('fundamental_factor_metrics') or {}).get('field_coverage') or {}).get('roe', 0.0))}",
        f"Dividend yield symbol coverage: {_format_rate(((validation.get('fundamental_factor_metrics') or {}).get('field_coverage') or {}).get('dividend_yield', 0.0))}",
        f"Date range: {(validation.get('fundamental_factor_metrics') or {}).get('min_date', '') or 'n/a'} to {(validation.get('fundamental_factor_metrics') or {}).get('max_date', '') or 'n/a'}",
        "",
        "### Checks",
        "",
        "| Check | Severity | Passed | Detail |",
        "|---|---|---:|---|",
    ]
    for item in validation.get("checks", []) or []:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| {name} | {severity} | {passed} | {detail} |".format(
                name=_md(str(item.get("name", ""))),
                severity=_md(str(item.get("severity", ""))),
                passed="yes" if item.get("passed") else "no",
                detail=_md(str(item.get("detail", ""))),
            )
        )
    caveats = validation.get("caveats") if isinstance(validation.get("caveats"), list) else []
    if caveats:
        lines.extend(["", "### Caveats", ""])
        lines.extend(f"- {item}" for item in caveats[:12])
    lines.append("")
    return "\n".join(lines)


def write_production_asset_validation_artifacts(output_dir: str | Path, validation: dict[str, object]) -> dict[str, Path]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "production_asset_validation.json"
    markdown_path = target / "production_asset_validation.md"
    json_path.write_text(json.dumps(_json_ready(validation), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_production_asset_validation_markdown(validation), encoding="utf-8")
    return {"production_asset_validation": json_path, "production_asset_validation_report": markdown_path}


def build_vendor_import_manifest(
    mapping: dict[str, object],
    *,
    asset_root: Path,
    imported: dict[str, dict[str, object]],
    paths: dict[str, Path],
    validation: dict[str, object],
    start: str | None,
    end: str | None,
    vendor: str,
) -> dict[str, object]:
    trust_level = "production_import_ready" if validation.get("production_data_ready") else "production_import_blocked"
    return {
        "schema_version": 2,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "scope": "production_import",
        "source": vendor,
        "vendor": vendor,
        "asset_root": str(asset_root),
        "start_date": start or "",
        "end_date": end or "",
        "symbols": int((validation.get("quote_metrics") or {}).get("unique_symbols", 0) or 0),
        "rows": int((validation.get("quote_metrics") or {}).get("rows", 0) or 0),
        "data_hash": _combined_hash(imported),
        "paths": {name: str(path) for name, path in sorted(paths.items())},
        "stock_master_validation": validation.get("stock_master_validation", {}),
        "production_asset_validation": validation,
        "data_trust": {
            "trust_level": trust_level,
            "production_data_ready": bool(validation.get("production_data_ready")),
            "status": validation.get("status", "n/a"),
        },
        "caveats": validation.get("caveats", []) or [],
        "notes": [
            "Production imports write canonical assets under stock_master/, market/, fundamentals/, index/, and industry/.",
            "CSV remains the canonical runtime contract; parquet copies are optional acceleration artifacts.",
            "Vendor provenance, adjustment method, volume unit, amount unit, and industry taxonomy must be confirmed in data-definition.md.",
        ],
        "mapping": mapping,
    }


def write_data_definition_artifact(
    output_dir: str | Path,
    mapping: dict[str, object],
    imported: dict[str, dict[str, object]],
) -> Path:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    path = target / "data-definition.md"
    path.write_text(render_data_definition_markdown(mapping, imported), encoding="utf-8")
    return path


def render_data_definition_markdown(mapping: dict[str, object], imported: dict[str, dict[str, object]]) -> str:
    vendor = str(mapping.get("vendor", "unknown_vendor"))
    assets = mapping.get("assets") if isinstance(mapping.get("assets"), dict) else {}
    lines = [
        "## Data Definition",
        "",
        f"Vendor: `{vendor}`",
        f"Generated at: `{datetime.now().astimezone().isoformat(timespec='seconds')}`",
        "",
        "| Asset | Canonical Field | Vendor Field | Chinese Meaning | Source | Frequency | Definition | Example | Pending Confirmation |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for asset_name, asset_spec in assets.items():
        if not isinstance(asset_spec, dict):
            continue
        columns = asset_spec.get("columns") if isinstance(asset_spec.get("columns"), dict) else {}
        examples = imported.get(str(asset_name), {}).get("examples", {}) if isinstance(imported.get(str(asset_name)), dict) else {}
        for canonical, vendor_field in sorted(columns.items()):
            meaning, definition = FIELD_DEFINITIONS.get(str(canonical), (str(canonical), "Vendor supplied field."))
            example = ""
            if isinstance(examples, dict):
                example = str(examples.get(str(canonical), ""))
            pending = _pending_confirmation(str(canonical))
            lines.append(
                "| {asset} | {canonical} | {vendor_field} | {meaning} | {source} | {frequency} | {definition} | {example} | {pending} |".format(
                    asset=_md(str(asset_name)),
                    canonical=_md(str(canonical)),
                    vendor_field=_md(str(vendor_field)),
                    meaning=_md(meaning),
                    source=_md(vendor),
                    frequency=_field_frequency(str(asset_name)),
                    definition=_md(definition),
                    example=_md(example),
                    pending=_md(pending),
                )
            )
    lines.extend(
        [
            "",
            "### Pending Items",
            "",
            "- Confirm price adjustment method for daily quotes: raw, forward-adjusted, or backward-adjusted.",
            "- Confirm volume unit: shares or lots.",
            "- Confirm amount unit and currency.",
            "- Confirm whether delisted securities are fully included in the stock master and quote panel.",
            "- Confirm industry taxonomy, effective date semantics, and historical revision policy.",
            "",
        ]
    )
    return "\n".join(lines)


def _materialize_asset(
    asset_name: str,
    asset_spec: dict[str, object],
    *,
    destination: Path,
    start: str | None,
    end: str | None,
    chunk_size: int | None,
) -> pd.DataFrame:
    source_path = Path(str(asset_spec.get("path", "")))
    if not source_path.exists():
        raise DataSourceError(f"Vendor {asset_name} source does not exist: {source_path}")
    source_format = str(asset_spec.get("format", source_path.suffix.lstrip(".") or "csv")).lower()
    columns = asset_spec.get("columns") if isinstance(asset_spec.get("columns"), dict) else {}
    if asset_name == "daily_quotes" and source_format == "csv" and chunk_size and chunk_size > 0:
        return _materialize_daily_quotes_chunked(source_path, columns, destination=destination, start=start, end=end, chunk_size=chunk_size)
    raw = _read_table(source_path, source_format)
    frame = _canonicalize_asset(asset_name, raw, columns, start=start, end=end)
    _write_csv(frame, destination)
    return frame


def _materialize_daily_quotes_chunked(
    source_path: Path,
    columns: dict[str, object],
    *,
    destination: Path,
    start: str | None,
    end: str | None,
    chunk_size: int,
) -> pd.DataFrame:
    chunks: list[pd.DataFrame] = []
    first = True
    destination.parent.mkdir(parents=True, exist_ok=True)
    for raw_chunk in pd.read_csv(source_path, chunksize=chunk_size):
        chunk = _canonicalize_daily_quotes(raw_chunk, columns, start=start, end=end)
        chunk.to_csv(destination, mode="w" if first else "a", header=first, index=False)
        first = False
        chunks.append(chunk)
    if not chunks:
        empty = pd.DataFrame(columns=list(CANONICAL_ASSETS["daily_quotes"]["required"]))
        _write_csv(empty, destination)
        return empty
    return pd.concat(chunks, ignore_index=True)


def _canonicalize_asset(
    asset_name: str,
    raw: pd.DataFrame,
    columns: dict[str, object],
    *,
    start: str | None,
    end: str | None,
) -> pd.DataFrame:
    if asset_name == "stock_master":
        return _canonicalize_stock_master(raw, columns)
    if asset_name == "daily_quotes":
        return _canonicalize_daily_quotes(raw, columns, start=start, end=end)
    if asset_name == "fundamental_factors":
        return _canonicalize_fundamental_factors(raw, columns, start=start, end=end)
    if asset_name == "fundamental_factors":
        return _canonicalize_fundamental_factors(raw, columns, start=start, end=end)
    if asset_name == "daily_fund_flows":
        return _canonicalize_daily_fund_flows(raw, columns, start=start, end=end)
    if asset_name == "margin_trades":
        return _canonicalize_margin_trades(raw, columns, start=start, end=end)
    if asset_name == "dragon_tiger_details":
        return _canonicalize_dragon_tiger_details(raw, columns, start=start, end=end)
    if asset_name == "announcements":
        return _canonicalize_announcements(raw, columns, start=start, end=end)
    if asset_name == "index_constituents":
        return _canonicalize_index_constituents(raw, columns, start=start, end=end)
    if asset_name == "industry_classification":
        return _canonicalize_industry_classification(raw, columns, start=start, end=end)
    raise DataSourceError(f"Unsupported vendor asset: {asset_name}")


def _canonicalize_stock_master(raw: pd.DataFrame, columns: dict[str, object]) -> pd.DataFrame:
    frame = _rename_columns(raw, columns)
    if "symbol" not in frame and "stockCode" not in frame:
        raise DataSourceError("stock_master requires symbol or stockCode after mapping.")
    if "symbol" in frame:
        frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    else:
        market = frame["exchangeCode"] if "exchangeCode" in frame else pd.Series("", index=frame.index)
        frame["symbol"] = [_normalize_symbol_with_market(code, exch) for code, exch in zip(frame["stockCode"], market)]
    invalid = ~frame["symbol"].astype(str).str.match(r"^\d{6}\.(SH|SZ|BJ)$", na=False)
    if invalid.any() and "stockCode" in frame:
        market = frame["exchangeCode"] if "exchangeCode" in frame else pd.Series("", index=frame.index)
        fallback = pd.Series([_normalize_symbol_with_market(code, exch) for code, exch in zip(frame["stockCode"], market)], index=frame.index)
        frame.loc[invalid, "symbol"] = fallback.loc[invalid]
    frame["stockCode"] = frame["symbol"].str.split(".", n=1).str[0]
    frame["exchangeCode"] = frame["symbol"].str.split(".", n=1).str[1]
    defaults = {"stockName": "", "stockType": "A股", "listStatus": ""}
    for column, default in defaults.items():
        if column not in frame:
            frame[column] = default
    for column in ("listDate", "delistDate", "reportDate"):
        if column not in frame:
            frame[column] = pd.NaT
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    for column in ("stockName", "stockType", "listStatus", "stockFullName", "boardName"):
        if column in frame:
            frame[column] = frame[column].where(frame[column].notna(), "").astype(str)
    for column in ("sharesTotal", "sharesFloat", "sharesFloatA"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    keep = [
        "symbol",
        "stockCode",
        "exchangeCode",
        "stockName",
        "stockType",
        "listDate",
        "delistDate",
        "listStatus",
        "stockFullName",
        "boardName",
        "sharesTotal",
        "sharesFloat",
        "sharesFloatA",
        "reportDate",
    ]
    frame = frame[[column for column in keep if column in frame.columns]].dropna(subset=["symbol"])
    return frame.drop_duplicates("symbol", keep="first").sort_values("symbol").reset_index(drop=True)


def _canonicalize_daily_quotes(
    raw: pd.DataFrame,
    columns: dict[str, object],
    *,
    start: str | None,
    end: str | None,
) -> pd.DataFrame:
    frame = _rename_columns(raw, columns)
    if "date" not in frame:
        raise DataSourceError("daily_quotes requires date after mapping.")
    if "symbol" not in frame and "stockCode" not in frame:
        raise DataSourceError("daily_quotes requires symbol or stockCode after mapping.")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    if "symbol" in frame:
        frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    else:
        market = frame["exchangeCode"] if "exchangeCode" in frame else pd.Series("", index=frame.index)
        frame["symbol"] = [_normalize_symbol_with_market(code, exch) for code, exch in zip(frame["stockCode"], market)]
    for column in ("open", "high", "low", "close", "volume", "amount", "pe", "pb", "roe", "dividend_yield", "turnover"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "dividend_yield" in frame:
        frame["dividend_yield"] = _normalize_yield_series(frame["dividend_yield"])
    if start:
        frame = frame[frame["date"] >= pd.Timestamp(_date_with_dash(start))]
    if end:
        frame = frame[frame["date"] <= pd.Timestamp(_date_with_dash(end))]
    keep = [
        "date",
        "symbol",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "pe",
        "pb",
        "roe",
        "dividend_yield",
        "turnover",
        "is_suspended",
        "is_limit_up",
        "is_limit_down",
        "stockName",
        "industryLV1Name",
        "industryName",
    ]
    required = set(CANONICAL_ASSETS["daily_quotes"]["required"])
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise DataSourceError(f"daily_quotes missing required mapped columns: {missing}")
    frame = frame[[column for column in keep if column in frame.columns]].dropna(subset=["date", "symbol"])
    return frame.sort_values(["date", "symbol"]).reset_index(drop=True)


def _canonicalize_fundamental_factors(
    raw: pd.DataFrame,
    columns: dict[str, object],
    *,
    start: str | None,
    end: str | None,
) -> pd.DataFrame:
    frame = _rename_columns(raw, columns)
    if "date" not in frame:
        if "publishDate" in frame:
            frame["date"] = frame["publishDate"]
        elif "reportDate" in frame:
            frame["date"] = frame["reportDate"]
        else:
            raise DataSourceError("fundamental_factors requires date, publishDate, or reportDate after mapping.")
    if "symbol" not in frame and "stockCode" not in frame:
        raise DataSourceError("fundamental_factors requires symbol or stockCode after mapping.")
    if "symbol" in frame:
        frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    else:
        market = frame["exchangeCode"] if "exchangeCode" in frame else pd.Series("", index=frame.index)
        frame["symbol"] = [_normalize_symbol_with_market(code, exch) for code, exch in zip(frame["stockCode"], market)]
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
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
    if end:
        frame = frame[frame["date"] <= pd.Timestamp(_date_with_dash(end))]
    # Keep pre-start factors so production loaders can merge the latest disclosed value
    # into the first requested trading day without look-ahead.
    keep = [
        "date",
        "symbol",
        "roe",
        "dividend_yield",
        "pe",
        "pb",
        *FINANCIAL_ALPHA_FIELDS,
        "publishDate",
        "reportPeriodEnd",
        "factorSource",
        "source",
    ]
    if not any(column in frame.columns for column in ("roe", "dividend_yield", "pe", "pb")):
        raise DataSourceError("fundamental_factors requires at least one mapped factor field.")
    frame = frame[[column for column in keep if column in frame.columns]].dropna(subset=["date", "symbol"])
    return frame.sort_values(["date", "symbol"]).drop_duplicates(["date", "symbol"], keep="last").reset_index(drop=True)


def _canonicalize_daily_fund_flows(
    raw: pd.DataFrame,
    columns: dict[str, object],
    *,
    start: str | None,
    end: str | None,
) -> pd.DataFrame:
    frame = _rename_columns(raw, columns)
    if "date" not in frame:
        raise DataSourceError("daily_fund_flows requires date after mapping.")
    if "symbol" not in frame and "stockCode" not in frame:
        raise DataSourceError("daily_fund_flows requires symbol or stockCode after mapping.")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    if "symbol" in frame:
        frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    else:
        market = frame["exchangeCode"] if "exchangeCode" in frame else pd.Series("", index=frame.index)
        frame["symbol"] = [_normalize_symbol_with_market(code, exch) for code, exch in zip(frame["stockCode"], market)]
    frame["stockCode"] = frame["symbol"].str.split(".", n=1).str[0]
    for column in CAPITAL_FLOW_FIELDS:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "capitalFlowSource" not in frame:
        frame["capitalFlowSource"] = "vendor_import:daily_fund_flows"
    if start:
        frame = frame[frame["date"] >= pd.Timestamp(_date_with_dash(start))]
    if end:
        frame = frame[frame["date"] <= pd.Timestamp(_date_with_dash(end))]
    required = set(CANONICAL_ASSETS["daily_fund_flows"]["required"])
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise DataSourceError(f"daily_fund_flows missing required mapped columns: {missing}")
    keep = ["date", "symbol", "stockCode", "stockName", *CAPITAL_FLOW_FIELDS, "capitalFlowSource"]
    frame = frame[[column for column in keep if column in frame.columns]].dropna(subset=["date", "symbol"])
    return frame.sort_values(["date", "symbol"]).drop_duplicates(["date", "symbol"], keep="last").reset_index(drop=True)


def _canonicalize_margin_trades(
    raw: pd.DataFrame,
    columns: dict[str, object],
    *,
    start: str | None,
    end: str | None,
) -> pd.DataFrame:
    frame = _rename_columns(raw, columns)
    if "date" not in frame:
        raise DataSourceError("margin_trades requires date after mapping.")
    if "symbol" not in frame and "stockCode" not in frame:
        raise DataSourceError("margin_trades requires symbol or stockCode after mapping.")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    if "symbol" in frame:
        frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    else:
        market = frame["exchangeCode"] if "exchangeCode" in frame else pd.Series("", index=frame.index)
        frame["symbol"] = [_normalize_symbol_with_market(code, exch) for code, exch in zip(frame["stockCode"], market)]
    frame["stockCode"] = frame["symbol"].str.split(".", n=1).str[0]
    for column in MARGIN_TRADE_FIELDS:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "marginTradeSource" not in frame:
        frame["marginTradeSource"] = "vendor_import:margin_trades"
    if start:
        frame = frame[frame["date"] >= pd.Timestamp(_date_with_dash(start))]
    if end:
        frame = frame[frame["date"] <= pd.Timestamp(_date_with_dash(end))]
    required = set(CANONICAL_ASSETS["margin_trades"]["required"])
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise DataSourceError(f"margin_trades missing required mapped columns: {missing}")
    keep = ["date", "symbol", "stockCode", "stockName", *MARGIN_TRADE_FIELDS, "marginTradeSource"]
    frame = frame[[column for column in keep if column in frame.columns]].dropna(subset=["date", "symbol"])
    return frame.sort_values(["date", "symbol"]).drop_duplicates(["date", "symbol"], keep="last").reset_index(drop=True)


def _canonicalize_dragon_tiger_details(
    raw: pd.DataFrame,
    columns: dict[str, object],
    *,
    start: str | None,
    end: str | None,
) -> pd.DataFrame:
    frame = _rename_columns(raw, columns)
    if "date" not in frame:
        raise DataSourceError("dragon_tiger_details requires date after mapping.")
    if "symbol" not in frame and "stockCode" not in frame:
        raise DataSourceError("dragon_tiger_details requires symbol or stockCode after mapping.")
    if "abnormalType" not in frame and "abnormalTypeName" not in frame:
        raise DataSourceError("dragon_tiger_details requires abnormalType or abnormalTypeName after mapping.")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    if "symbol" in frame:
        frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    else:
        market = frame["exchangeCode"] if "exchangeCode" in frame else pd.Series("", index=frame.index)
        frame["symbol"] = [_normalize_symbol_with_market(code, exch) for code, exch in zip(frame["stockCode"], market)]
    frame["stockCode"] = frame["symbol"].str.split(".", n=1).str[0]
    if "abnormalType" not in frame:
        frame["abnormalType"] = frame["abnormalTypeName"]
    if "abnormalTypeName" not in frame:
        frame["abnormalTypeName"] = frame["abnormalType"]
    for column in ("deviationPct", "volume", "amount", "buyAmount", "sellAmount", "totalAmount"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "dragonTigerSource" not in frame:
        frame["dragonTigerSource"] = "vendor_import:dragon_tiger_details"
    if start:
        frame = frame[frame["date"] >= pd.Timestamp(_date_with_dash(start))]
    if end:
        frame = frame[frame["date"] <= pd.Timestamp(_date_with_dash(end))]
    required = set(CANONICAL_ASSETS["dragon_tiger_details"]["required"])
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise DataSourceError(f"dragon_tiger_details missing required mapped columns: {missing}")
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
    frame = frame[[column for column in keep if column in frame.columns]].dropna(subset=["date", "symbol"])
    duplicate_keys = [column for column in ("date", "symbol", "abnormalType", "amount") if column in frame.columns]
    return frame.sort_values(["date", "symbol"]).drop_duplicates(duplicate_keys, keep="last").reset_index(drop=True)


def _canonicalize_announcements(
    raw: pd.DataFrame,
    columns: dict[str, object],
    *,
    start: str | None,
    end: str | None,
) -> pd.DataFrame:
    frame = _rename_columns(raw, columns)
    if "date" not in frame:
        if "announcementDate" in frame:
            frame["date"] = frame["announcementDate"]
        elif "publishDate" in frame:
            frame["date"] = frame["publishDate"]
        elif "disclosureDate" in frame:
            frame["date"] = frame["disclosureDate"]
        else:
            raise DataSourceError("announcements requires date, announcementDate, publishDate, or disclosureDate after mapping.")
    if "symbol" not in frame and "stockCode" not in frame:
        raise DataSourceError("announcements requires symbol or stockCode after mapping.")
    if "title" not in frame and "announcementType" not in frame:
        raise DataSourceError("announcements requires title or announcementType after mapping.")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    if "symbol" in frame:
        frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    else:
        market = frame["exchangeCode"] if "exchangeCode" in frame else pd.Series("", index=frame.index)
        frame["symbol"] = [_normalize_symbol_with_market(code, exch) for code, exch in zip(frame["stockCode"], market)]
    frame["stockCode"] = frame["symbol"].str.split(".", n=1).str[0]
    if "title" not in frame:
        frame["title"] = ""
    if "announcementType" not in frame:
        frame["announcementType"] = ""
    if "announcementSource" not in frame:
        frame["announcementSource"] = "vendor_import:announcements"
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
    if start:
        frame = frame[frame["date"] >= pd.Timestamp(_date_with_dash(start))]
    if end:
        frame = frame[frame["date"] <= pd.Timestamp(_date_with_dash(end))]
    required = set(CANONICAL_ASSETS["announcements"]["required"])
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise DataSourceError(f"announcements missing required mapped columns: {missing}")
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
    ]
    frame = frame[[column for column in keep if column in frame.columns]].dropna(subset=["date", "symbol"])
    duplicate_keys = [column for column in ("date", "symbol", "title", "announcementType") if column in frame.columns]
    return frame.sort_values(["date", "symbol"]).drop_duplicates(duplicate_keys, keep="last").reset_index(drop=True)


def _canonicalize_index_constituents(
    raw: pd.DataFrame,
    columns: dict[str, object],
    *,
    start: str | None,
    end: str | None,
) -> pd.DataFrame:
    frame = _rename_columns(raw, columns)
    for column in ("date", "indexCode", "symbol", "weight"):
        if column not in frame:
            raise DataSourceError(f"index_constituents missing required mapped column: {column}")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    frame["weight"] = pd.to_numeric(frame["weight"], errors="coerce")
    if start:
        frame = frame[frame["date"] >= pd.Timestamp(_date_with_dash(start))]
    if end:
        frame = frame[frame["date"] <= pd.Timestamp(_date_with_dash(end))]
    keep = ["date", "indexCode", "symbol", "weight", "indexName", "indexSource", "indexAsOfDate", "isLatestOnly"]
    return frame[[column for column in keep if column in frame.columns]].dropna(subset=["date", "indexCode", "symbol"])


def _canonicalize_industry_classification(
    raw: pd.DataFrame,
    columns: dict[str, object],
    *,
    start: str | None,
    end: str | None,
) -> pd.DataFrame:
    frame = _rename_columns(raw, columns)
    for column in ("date", "symbol", "industryLV1Name", "industryName"):
        if column not in frame:
            raise DataSourceError(f"industry_classification missing required mapped column: {column}")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    if start:
        frame = frame[frame["date"] >= pd.Timestamp(_date_with_dash(start))]
    if end:
        frame = frame[frame["date"] <= pd.Timestamp(_date_with_dash(end))]
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
    return frame[[column for column in keep if column in frame.columns]].dropna(subset=["date", "symbol"])


def _quote_coverage_metrics(frame: pd.DataFrame, expected_symbols: Iterable[str]) -> dict[str, object]:
    expected = set(str(symbol).upper() for symbol in expected_symbols if str(symbol).strip())
    quote_symbols = set(frame["symbol"].dropna().astype(str).unique()) if "symbol" in frame else set()
    covered = sorted(expected & quote_symbols)
    missing = sorted(expected - quote_symbols)
    extra = sorted(quote_symbols - expected) if expected else []
    trading_dates = pd.to_datetime(frame["date"], errors="coerce").dropna().dt.normalize().drop_duplicates()
    total_trading_dates = int(len(trading_dates))
    if total_trading_dates and "symbol" in frame:
        counts = frame.dropna(subset=["date", "symbol"]).groupby("symbol")["date"].nunique()
        coverage = counts / total_trading_dates
        median_coverage = float(coverage.median()) if not coverage.empty else 0.0
        min_coverage = float(coverage.min()) if not coverage.empty else 0.0
    else:
        median_coverage = 0.0
        min_coverage = 0.0
    price_columns = [column for column in ("open", "high", "low", "close") if column in frame.columns]
    bad_price = pd.Series(False, index=frame.index, dtype=bool)
    for column in price_columns:
        bad_price |= pd.to_numeric(frame[column], errors="coerce").le(0) | frame[column].isna()
    if {"high", "low"}.issubset(frame.columns):
        bad_price |= pd.to_numeric(frame["high"], errors="coerce") < pd.to_numeric(frame["low"], errors="coerce")
    if {"high", "low", "close"}.issubset(frame.columns):
        close = pd.to_numeric(frame["close"], errors="coerce")
        high = pd.to_numeric(frame["high"], errors="coerce")
        low = pd.to_numeric(frame["low"], errors="coerce")
        bad_price |= (close > high * 1.000001) | (close < low * 0.999999)
    bad_amount_volume = pd.Series(False, index=frame.index, dtype=bool)
    for column in ("volume", "amount"):
        if column in frame:
            bad_amount_volume |= pd.to_numeric(frame[column], errors="coerce").lt(0)
    duplicates = int(frame.duplicated(["date", "symbol"]).sum()) if {"date", "symbol"}.issubset(frame.columns) else 0
    dates = pd.to_datetime(frame["date"], errors="coerce").dropna() if "date" in frame else pd.Series(dtype="datetime64[ns]")
    field_coverage, field_non_null = _factor_field_coverage(frame, expected, ("pe", "pb", "roe", "dividend_yield"))
    return {
        "rows": int(len(frame)),
        "unique_symbols": int(len(quote_symbols)),
        "expected_symbols": int(len(expected)),
        "covered_eligible_symbols": int(len(covered)),
        "missing_eligible_symbols": int(len(missing)),
        "extra_symbols": int(len(extra)),
        "eligible_symbol_coverage_rate": float(len(covered) / len(expected)) if expected else 0.0,
        "missing_eligible_examples": missing[:20],
        "extra_symbol_examples": extra[:20],
        "trading_dates": total_trading_dates,
        "median_symbol_date_coverage": median_coverage,
        "min_symbol_date_coverage": min_coverage,
        "duplicate_key_count": duplicates,
        "bad_price_rows": int(bad_price.sum()),
        "bad_amount_volume_rows": int(bad_amount_volume.sum()),
        "field_coverage": field_coverage,
        "field_non_null": field_non_null,
        "min_date": dates.min().strftime("%Y-%m-%d") if not dates.empty else "",
        "max_date": dates.max().strftime("%Y-%m-%d") if not dates.empty else "",
        "path": "",
    }


def _fundamental_factor_metrics(frame: pd.DataFrame, expected_symbols: Iterable[str]) -> dict[str, object]:
    expected = set(str(symbol).upper() for symbol in expected_symbols if str(symbol).strip())
    factor_symbols = set(frame["symbol"].dropna().astype(str).unique()) if "symbol" in frame else set()
    dates = pd.to_datetime(frame["date"], errors="coerce").dropna() if "date" in frame else pd.Series(dtype="datetime64[ns]")
    field_coverage: dict[str, float] = {}
    field_non_null: dict[str, int] = {}
    for field in ("roe", "dividend_yield", "pe", "pb"):
        if field not in frame:
            field_coverage[field] = 0.0
            field_non_null[field] = 0
            continue
        covered_symbols = set(frame.loc[pd.to_numeric(frame[field], errors="coerce").notna(), "symbol"].astype(str).unique())
        field_coverage[field] = float(len(expected & covered_symbols) / len(expected)) if expected else 0.0
        field_non_null[field] = int(pd.to_numeric(frame[field], errors="coerce").notna().sum())
    return {
        "exists": True,
        "rows": int(len(frame)),
        "unique_symbols": int(len(factor_symbols)),
        "expected_symbols": int(len(expected)),
        "covered_eligible_symbols": int(len(expected & factor_symbols)),
        "eligible_symbol_coverage_rate": float(len(expected & factor_symbols) / len(expected)) if expected else 0.0,
        "field_coverage": field_coverage,
        "field_non_null": field_non_null,
        "duplicate_key_count": int(frame.duplicated(["date", "symbol"]).sum()) if {"date", "symbol"}.issubset(frame.columns) else 0,
        "min_date": dates.min().strftime("%Y-%m-%d") if not dates.empty else "",
        "max_date": dates.max().strftime("%Y-%m-%d") if not dates.empty else "",
        "path": "",
    }


def _empty_fundamental_factor_metrics(path: str) -> dict[str, object]:
    return {
        "exists": False,
        "path": path,
        "rows": 0,
        "unique_symbols": 0,
        "expected_symbols": 0,
        "covered_eligible_symbols": 0,
        "eligible_symbol_coverage_rate": 0.0,
        "field_coverage": {"roe": 0.0, "dividend_yield": 0.0, "pe": 0.0, "pb": 0.0},
        "field_non_null": {"roe": 0, "dividend_yield": 0, "pe": 0, "pb": 0},
        "duplicate_key_count": 0,
        "min_date": "",
        "max_date": "",
    }


def _empty_quote_metrics(path: str) -> dict[str, object]:
    return {
        "path": path,
        "rows": 0,
        "unique_symbols": 0,
        "expected_symbols": 0,
        "covered_eligible_symbols": 0,
        "missing_eligible_symbols": 0,
        "extra_symbols": 0,
        "eligible_symbol_coverage_rate": 0.0,
        "trading_dates": 0,
        "median_symbol_date_coverage": 0.0,
        "min_symbol_date_coverage": 0.0,
        "duplicate_key_count": 0,
        "bad_price_rows": 0,
        "bad_amount_volume_rows": 0,
        "field_coverage": {"pe": 0.0, "pb": 0.0, "roe": 0.0, "dividend_yield": 0.0},
        "field_non_null": {"pe": 0, "pb": 0, "roe": 0, "dividend_yield": 0},
        "min_date": "",
        "max_date": "",
    }


def _fundamental_factor_metrics(frame: pd.DataFrame, expected_symbols: Iterable[str]) -> dict[str, object]:
    expected = set(str(symbol).upper() for symbol in expected_symbols if str(symbol).strip())
    factor_symbols = set(frame["symbol"].dropna().astype(str).unique()) if "symbol" in frame else set()
    dates = pd.to_datetime(frame["date"], errors="coerce").dropna() if "date" in frame else pd.Series(dtype="datetime64[ns]")
    field_coverage, field_non_null = _factor_field_coverage(frame, expected, ("roe", "dividend_yield", "pe", "pb", *FINANCIAL_ALPHA_FIELDS))
    return {
        "exists": True,
        "rows": int(len(frame)),
        "unique_symbols": int(len(factor_symbols)),
        "expected_symbols": int(len(expected)),
        "covered_eligible_symbols": int(len(expected & factor_symbols)),
        "eligible_symbol_coverage_rate": float(len(expected & factor_symbols) / len(expected)) if expected else 0.0,
        "field_coverage": field_coverage,
        "field_non_null": field_non_null,
        "duplicate_key_count": int(frame.duplicated(["date", "symbol"]).sum()) if {"date", "symbol"}.issubset(frame.columns) else 0,
        "min_date": dates.min().strftime("%Y-%m-%d") if not dates.empty else "",
        "max_date": dates.max().strftime("%Y-%m-%d") if not dates.empty else "",
        "path": "",
    }


def _daily_fund_flow_metrics(frame: pd.DataFrame, expected_symbols: Iterable[str]) -> dict[str, object]:
    expected = set(str(symbol).upper() for symbol in expected_symbols if str(symbol).strip())
    flow_symbols = set(frame["symbol"].dropna().astype(str).unique()) if "symbol" in frame else set()
    dates = pd.to_datetime(frame["date"], errors="coerce").dropna() if "date" in frame else pd.Series(dtype="datetime64[ns]")
    field_coverage, field_non_null = _factor_field_coverage(frame, expected, CAPITAL_FLOW_FIELDS)
    return {
        "exists": True,
        "rows": int(len(frame)),
        "unique_symbols": int(len(flow_symbols)),
        "expected_symbols": int(len(expected)),
        "covered_eligible_symbols": int(len(expected & flow_symbols)),
        "eligible_symbol_coverage_rate": float(len(expected & flow_symbols) / len(expected)) if expected else 0.0,
        "field_coverage": field_coverage,
        "field_non_null": field_non_null,
        "duplicate_key_count": int(frame.duplicated(["date", "symbol"]).sum()) if {"date", "symbol"}.issubset(frame.columns) else 0,
        "min_date": dates.min().strftime("%Y-%m-%d") if not dates.empty else "",
        "max_date": dates.max().strftime("%Y-%m-%d") if not dates.empty else "",
        "path": "",
    }


def _margin_trade_metrics(frame: pd.DataFrame, expected_symbols: Iterable[str]) -> dict[str, object]:
    expected = set(str(symbol).upper() for symbol in expected_symbols if str(symbol).strip())
    trade_symbols = set(frame["symbol"].dropna().astype(str).unique()) if "symbol" in frame else set()
    dates = pd.to_datetime(frame["date"], errors="coerce").dropna() if "date" in frame else pd.Series(dtype="datetime64[ns]")
    field_coverage, field_non_null = _factor_field_coverage(frame, expected, MARGIN_TRADE_FIELDS)
    return {
        "exists": True,
        "rows": int(len(frame)),
        "unique_symbols": int(len(trade_symbols)),
        "expected_symbols": int(len(expected)),
        "covered_eligible_symbols": int(len(expected & trade_symbols)),
        "eligible_symbol_coverage_rate": float(len(expected & trade_symbols) / len(expected)) if expected else 0.0,
        "field_coverage": field_coverage,
        "field_non_null": field_non_null,
        "duplicate_key_count": int(frame.duplicated(["date", "symbol"]).sum()) if {"date", "symbol"}.issubset(frame.columns) else 0,
        "min_date": dates.min().strftime("%Y-%m-%d") if not dates.empty else "",
        "max_date": dates.max().strftime("%Y-%m-%d") if not dates.empty else "",
        "path": "",
    }


def _dragon_tiger_detail_metrics(frame: pd.DataFrame, expected_symbols: Iterable[str]) -> dict[str, object]:
    expected = set(str(symbol).upper() for symbol in expected_symbols if str(symbol).strip())
    event_symbols = set(frame["symbol"].dropna().astype(str).unique()) if "symbol" in frame else set()
    dates = pd.to_datetime(frame["date"], errors="coerce").dropna() if "date" in frame else pd.Series(dtype="datetime64[ns]")
    fields = ("abnormalType", "abnormalTypeName", "deviationPct", "volume", "amount", "buyAmount", "sellAmount", "totalAmount")
    field_coverage: dict[str, float] = {}
    field_non_null: dict[str, int] = {}
    for field in fields:
        if field not in frame or "symbol" not in frame:
            field_coverage[field] = 0.0
            field_non_null[field] = 0
            continue
        valid = frame[field].notna()
        if frame[field].dtype == object or str(frame[field].dtype).startswith("string"):
            valid &= frame[field].astype(str).str.strip() != ""
        covered_symbols = set(frame.loc[valid, "symbol"].astype(str).unique())
        field_coverage[field] = float(len(expected & covered_symbols) / len(expected)) if expected else 0.0
        field_non_null[field] = int(valid.sum())
    duplicate_keys = [column for column in ("date", "symbol", "abnormalType", "amount") if column in frame.columns]
    return {
        "exists": True,
        "rows": int(len(frame)),
        "unique_symbols": int(len(event_symbols)),
        "expected_symbols": int(len(expected)),
        "covered_eligible_symbols": int(len(expected & event_symbols)),
        "eligible_symbol_coverage_rate": float(len(expected & event_symbols) / len(expected)) if expected else 0.0,
        "field_coverage": field_coverage,
        "field_non_null": field_non_null,
        "duplicate_key_count": int(frame.duplicated(duplicate_keys).sum()) if duplicate_keys else 0,
        "min_date": dates.min().strftime("%Y-%m-%d") if not dates.empty else "",
        "max_date": dates.max().strftime("%Y-%m-%d") if not dates.empty else "",
        "path": "",
    }


def _announcement_event_metrics(frame: pd.DataFrame, expected_symbols: Iterable[str]) -> dict[str, object]:
    expected = set(str(symbol).upper() for symbol in expected_symbols if str(symbol).strip())
    event_symbols = set(frame["symbol"].dropna().astype(str).unique()) if "symbol" in frame else set()
    dates = pd.to_datetime(frame["date"], errors="coerce").dropna() if "date" in frame else pd.Series(dtype="datetime64[ns]")
    fields = ("title", "announcementType", "announcementId", "url", "announcementSource", "riskType", "announcementContentType", "guid")
    field_coverage: dict[str, float] = {}
    field_non_null: dict[str, int] = {}
    for field in fields:
        if field not in frame or "symbol" not in frame:
            field_coverage[field] = 0.0
            field_non_null[field] = 0
            continue
        valid = frame[field].notna()
        if frame[field].dtype == object or str(frame[field].dtype).startswith("string"):
            valid &= frame[field].astype(str).str.strip() != ""
        covered_symbols = set(frame.loc[valid, "symbol"].astype(str).unique())
        field_coverage[field] = float(len(expected & covered_symbols) / len(expected)) if expected else 0.0
        field_non_null[field] = int(valid.sum())
    duplicate_keys = [column for column in ("date", "symbol", "title", "announcementType") if column in frame.columns]
    return {
        "exists": True,
        "rows": int(len(frame)),
        "unique_symbols": int(len(event_symbols)),
        "expected_symbols": int(len(expected)),
        "covered_eligible_symbols": int(len(expected & event_symbols)),
        "eligible_symbol_coverage_rate": float(len(expected & event_symbols) / len(expected)) if expected else 0.0,
        "field_coverage": field_coverage,
        "field_non_null": field_non_null,
        "duplicate_key_count": int(frame.duplicated(duplicate_keys).sum()) if duplicate_keys else 0,
        "min_date": dates.min().strftime("%Y-%m-%d") if not dates.empty else "",
        "max_date": dates.max().strftime("%Y-%m-%d") if not dates.empty else "",
        "path": "",
    }


def _index_constituent_metrics(frame: pd.DataFrame, expected_symbols: Iterable[str]) -> dict[str, object]:
    expected = set(str(symbol).upper() for symbol in expected_symbols if str(symbol).strip())
    symbols = set(frame["symbol"].dropna().astype(str).unique()) if "symbol" in frame else set()
    dates = pd.to_datetime(frame["date"], errors="coerce").dropna() if "date" in frame else pd.Series(dtype="datetime64[ns]")
    snapshot_date_count = int(dates.dt.normalize().nunique()) if not dates.empty else 0
    index_counts = (
        {str(key): int(value) for key, value in frame.groupby("indexCode")["symbol"].nunique().sort_index().items()}
        if {"indexCode", "symbol"}.issubset(frame.columns)
        else {}
    )
    weight_non_null = int(pd.to_numeric(frame["weight"], errors="coerce").notna().sum()) if "weight" in frame else 0
    latest_only_flags = _truthy_flag_series(frame["isLatestOnly"]) if "isLatestOnly" in frame else pd.Series(False, index=frame.index)
    latest_only_rows = int(latest_only_flags.sum())
    return {
        "exists": True,
        "rows": int(len(frame)),
        "index_count": int(frame["indexCode"].nunique()) if "indexCode" in frame else 0,
        "index_counts": index_counts,
        "unique_symbols": int(len(symbols)),
        "expected_symbols": int(len(expected)),
        "covered_eligible_symbols": int(len(expected & symbols)),
        "eligible_symbol_coverage_rate": float(len(expected & symbols) / len(expected)) if expected else 0.0,
        "weight_non_null": weight_non_null,
        "duplicate_key_count": int(frame.duplicated(["date", "indexCode", "symbol"]).sum())
        if {"date", "indexCode", "symbol"}.issubset(frame.columns)
        else 0,
        "snapshot_date_count": snapshot_date_count,
        "latest_only_rows": latest_only_rows,
        "latest_only_all": bool(len(frame) > 0 and latest_only_rows == len(frame)),
        "min_date": dates.min().strftime("%Y-%m-%d") if not dates.empty else "",
        "max_date": dates.max().strftime("%Y-%m-%d") if not dates.empty else "",
        "path": "",
    }


def _truthy_flag_series(values: pd.Series) -> pd.Series:
    if values.dtype == bool:
        return values.fillna(False).astype(bool)
    return values.fillna(False).astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def _factor_field_coverage(
    frame: pd.DataFrame,
    expected_symbols: set[str],
    fields: Iterable[str],
) -> tuple[dict[str, float], dict[str, int]]:
    field_coverage: dict[str, float] = {}
    field_non_null: dict[str, int] = {}
    for field in fields:
        if field not in frame or "symbol" not in frame:
            field_coverage[field] = 0.0
            field_non_null[field] = 0
            continue
        numeric = pd.to_numeric(frame[field], errors="coerce")
        covered_symbols = set(frame.loc[numeric.notna(), "symbol"].astype(str).unique())
        field_coverage[field] = float(len(expected_symbols & covered_symbols) / len(expected_symbols)) if expected_symbols else 0.0
        field_non_null[field] = int(numeric.notna().sum())
    return field_coverage, field_non_null


def _empty_fundamental_factor_metrics(path: str) -> dict[str, object]:
    return {
        "exists": False,
        "path": path,
        "rows": 0,
        "unique_symbols": 0,
        "expected_symbols": 0,
        "covered_eligible_symbols": 0,
        "eligible_symbol_coverage_rate": 0.0,
        "field_coverage": {"roe": 0.0, "dividend_yield": 0.0, "pe": 0.0, "pb": 0.0},
        "field_non_null": {"roe": 0, "dividend_yield": 0, "pe": 0, "pb": 0},
        "duplicate_key_count": 0,
        "min_date": "",
        "max_date": "",
    }


def _empty_daily_fund_flow_metrics(path: str) -> dict[str, object]:
    return {
        "exists": False,
        "path": path,
        "rows": 0,
        "unique_symbols": 0,
        "expected_symbols": 0,
        "covered_eligible_symbols": 0,
        "eligible_symbol_coverage_rate": 0.0,
        "field_coverage": {field: 0.0 for field in CAPITAL_FLOW_FIELDS},
        "field_non_null": {field: 0 for field in CAPITAL_FLOW_FIELDS},
        "duplicate_key_count": 0,
        "min_date": "",
        "max_date": "",
    }


def _empty_margin_trade_metrics(path: str) -> dict[str, object]:
    return {
        "exists": False,
        "path": path,
        "rows": 0,
        "unique_symbols": 0,
        "expected_symbols": 0,
        "covered_eligible_symbols": 0,
        "eligible_symbol_coverage_rate": 0.0,
        "field_coverage": {field: 0.0 for field in MARGIN_TRADE_FIELDS},
        "field_non_null": {field: 0 for field in MARGIN_TRADE_FIELDS},
        "duplicate_key_count": 0,
        "min_date": "",
        "max_date": "",
    }


def _empty_dragon_tiger_detail_metrics(path: str) -> dict[str, object]:
    fields = ("abnormalType", "abnormalTypeName", "deviationPct", "volume", "amount", "buyAmount", "sellAmount", "totalAmount")
    return {
        "exists": False,
        "path": path,
        "rows": 0,
        "unique_symbols": 0,
        "expected_symbols": 0,
        "covered_eligible_symbols": 0,
        "eligible_symbol_coverage_rate": 0.0,
        "field_coverage": {field: 0.0 for field in fields},
        "field_non_null": {field: 0 for field in fields},
        "duplicate_key_count": 0,
        "min_date": "",
        "max_date": "",
    }


def _empty_announcement_event_metrics(path: str) -> dict[str, object]:
    fields = ("title", "announcementType", "announcementId", "url", "announcementSource", "riskType", "announcementContentType", "guid")
    return {
        "exists": False,
        "path": path,
        "rows": 0,
        "unique_symbols": 0,
        "expected_symbols": 0,
        "covered_eligible_symbols": 0,
        "eligible_symbol_coverage_rate": 0.0,
        "field_coverage": {field: 0.0 for field in fields},
        "field_non_null": {field: 0 for field in fields},
        "duplicate_key_count": 0,
        "min_date": "",
        "max_date": "",
    }


def _empty_index_constituent_metrics(path: str) -> dict[str, object]:
    return {
        "exists": False,
        "path": path,
        "rows": 0,
        "index_count": 0,
        "index_counts": {},
        "unique_symbols": 0,
        "expected_symbols": 0,
        "covered_eligible_symbols": 0,
        "eligible_symbol_coverage_rate": 0.0,
        "weight_non_null": 0,
        "duplicate_key_count": 0,
        "snapshot_date_count": 0,
        "latest_only_rows": 0,
        "latest_only_all": False,
        "min_date": "",
        "max_date": "",
    }


def _asset_profile(frame: pd.DataFrame) -> dict[str, object]:
    examples = {}
    if not frame.empty:
        first = frame.iloc[0].to_dict()
        examples = {str(key): _json_scalar(value) for key, value in first.items()}
    dates = pd.to_datetime(frame["date"], errors="coerce").dropna() if "date" in frame else pd.Series(dtype="datetime64[ns]")
    return {
        "rows": int(len(frame)),
        "columns": [str(column) for column in frame.columns],
        "examples": examples,
        "min_date": dates.min().strftime("%Y-%m-%d") if not dates.empty else "",
        "max_date": dates.max().strftime("%Y-%m-%d") if not dates.empty else "",
    }


def _read_table(path: Path, source_format: str) -> pd.DataFrame:
    source_format = source_format.lower()
    if source_format in {"csv", "txt"}:
        return pd.read_csv(path)
    if source_format in {"parquet", "pq"}:
        try:
            return pd.read_parquet(path)
        except ImportError as exc:
            raise DataSourceError("Reading parquet requires pyarrow or fastparquet.") from exc
    raise DataSourceError(f"Unsupported vendor table format: {source_format}")


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _write_parquet_copy(frame: pd.DataFrame, path: Path) -> None:
    try:
        frame.to_parquet(path, index=False)
    except ImportError as exc:
        raise DataSourceError("Writing parquet copies requires pyarrow or fastparquet.") from exc


def _rename_columns(raw: pd.DataFrame, columns: dict[str, object]) -> pd.DataFrame:
    reverse = {str(vendor): str(canonical) for canonical, vendor in columns.items() if str(vendor)}
    frame = raw.rename(columns=reverse).copy()
    return frame


def _parse_nested_yaml(text: str) -> dict[str, object]:
    root: dict[str, object] = {}
    stack: list[tuple[int, dict[str, object]]] = [(-1, root)]
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip() or ":" not in line:
            continue
        indent = len(line) - len(line.lstrip(" "))
        key, value = line.strip().split(":", 1)
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value.strip() == "":
            child: dict[str, object] = {}
            parent[key.strip()] = child
            stack.append((indent, child))
        else:
            parent[key.strip()] = _parse_scalar(value.strip())
    return root


def _parse_scalar(value: str) -> object:
    if value in {"", "null", "None", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    try:
        if any(char in value for char in (".", "e", "E")):
            return float(value)
        return int(value)
    except ValueError:
        return value


def _normalize_symbol(symbol: object) -> str:
    text = _symbol_text(symbol)
    if not text:
        return ""
    if "." in text:
        code, exchange = text.split(".", 1)
        code = _symbol_text(code).zfill(6)
        return f"{code}.{exchange.upper()}"
    return _infer_exchange(text.zfill(6))


def _normalize_symbol_with_market(symbol: object, market: object) -> str:
    code = _symbol_text(symbol)
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
    return _infer_exchange(code)


def _symbol_text(value: object) -> str:
    try:
        if value is None or pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip().upper()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text in {"", "NAN", "NONE", "NULL"}:
        return ""
    return text


def _infer_exchange(code: str) -> str:
    if code.startswith(("600", "601", "603", "605", "688", "689")):
        return f"{code}.SH"
    if code.startswith(("4", "8", "9")):
        return f"{code}.BJ"
    return f"{code}.SZ"


def _date_with_dash(value: str) -> str:
    compact = str(value).replace("-", "")
    if len(compact) != 8:
        return str(value)
    return f"{compact[:4]}-{compact[4:6]}-{compact[6:]}"


def _date_leq(left: object, right: object) -> bool:
    left_date = pd.to_datetime(left, errors="coerce")
    right_date = pd.to_datetime(_date_with_dash(str(right)), errors="coerce")
    return bool(pd.notna(left_date) and pd.notna(right_date) and left_date <= right_date)


def _date_geq(left: object, right: object) -> bool:
    left_date = pd.to_datetime(left, errors="coerce")
    right_date = pd.to_datetime(_date_with_dash(str(right)), errors="coerce")
    return bool(pd.notna(left_date) and pd.notna(right_date) and left_date >= right_date)


def _check(name: str, passed: bool, severity: str, detail: str) -> dict[str, object]:
    return {"name": name, "passed": bool(passed), "severity": severity, "detail": detail}


def _format_rate(value: object) -> str:
    try:
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return "n/a"


def _normalize_yield_series(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if values.dropna().gt(1.0).mean() > 0.5:
        values = values / 100.0
    return values


def _field_frequency(asset_name: str) -> str:
    if asset_name == "stock_master":
        return "event/snapshot"
    if asset_name == "fundamental_factors":
        return "effective/as-of"
    if asset_name == "dragon_tiger_details":
        return "event/daily"
    return "daily"


def _pending_confirmation(field: str) -> str:
    if field in {"open", "high", "low", "close"}:
        return "Confirm adjustment method."
    if field == "volume":
        return "Confirm shares vs lots."
    if field == "amount":
        return "Confirm currency and unit."
    if field in {"listDate", "delistDate"}:
        return "Confirm event date and revision policy."
    if field in {"industryLV1Name", "industryName"}:
        return "Confirm taxonomy and effective date semantics."
    if field in {"roe", "dividend_yield", "publishDate", "reportPeriodEnd"}:
        return "Confirm factor formula, disclosure date, and revision policy."
    if field in set(CAPITAL_FLOW_FIELDS) | {"capitalFlowSource"}:
        return "Confirm fund-flow amount unit, publication timing, and revision policy."
    if field in set(MARGIN_TRADE_FIELDS) | {"marginTradeSource"}:
        return "Confirm margin-trade amount/unit, publication timing, and revision policy."
    if field in {"abnormalType", "abnormalTypeName", "deviationPct", "dragonTigerSource"}:
        return "Confirm dragon-tiger event timing, amount unit, and revision policy."
    return "Confirm vendor definition."


def _combined_hash(imported: dict[str, dict[str, object]]) -> str:
    payload = json.dumps(_json_ready(imported), ensure_ascii=False, sort_keys=True, default=str)
    import hashlib

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_ready(value: object) -> object:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return _json_scalar(value)


def _json_scalar(value: object) -> object:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
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


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
