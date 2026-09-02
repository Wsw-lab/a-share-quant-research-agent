"""Outcome-blind Stage-2 data-access contracts and metadata adapters.

This module deliberately stops at the *data-access boundary*.  It can inspect
CSV headers, dates, keys, non-null rates, and field informativeness, but it
never computes a factor, return, rank, IC, portfolio result, or variant
ordering.  The functions are intended for a pre-registration coverage probe
and for preparing a licensed-data review packet.  They do not grant a licence
and they do not fetch data from a provider.

The source adapters accept provider response frames supplied by the caller.
Network clients and credentials stay outside this repository's public API.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import io
import json
import argparse
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd


class DataAccessError(ValueError):
    """Raised when a source response cannot be adapted without guessing."""


STAGE2_DATASET_ROLES = ("quotes", "stock_master", "fundamentals", "official_calendar")

STAGE2_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "quotes": ("date", "symbol", "close", "amount", "is_st", "is_suspended"),
    "stock_master": ("symbol", "listDate", "delistDate", "listStatus", "stockType"),
    "fundamentals": ("symbol", "roeDiluted", "publishDate", "reportPeriodEnd"),
    "official_calendar": ("date",),
}

STAGE2_TARGETS = {
    "quote_start": "2009-01-01",
    "quote_end": "2023-01-31",
    "fundamental_start": "2009-01-01",
    "fundamental_end": "2022-12-31",
    "calendar_start_month": "2009-01",
    "calendar_end_month": "2023-01",
    "analysis_start": "2010-01-01",
    "analysis_end": "2022-12-31",
    "minimum_symbols_per_month": 1000,
    "minimum_sessions_per_month": 15,
}

# Provider exports use short codes (for example, Tushare's ``L``/``D``/``P``),
# while canonical intake files may use readable labels.  We keep the accepted
# vocabulary deliberately small and fail closed on a new provider code rather
# than silently treating it as listed or delisted.
_ACTIVE_LIST_STATUS_VALUES = frozenset(
    {
        "L",
        "LISTED",
        "ACTIVE",
        "A",
        "正常上市",
    }
)
_DELISTED_LIST_STATUS_VALUES = frozenset(
    {
        "D",
        "DELISTED",
        "TERMINATED",
        "退市",
        "终止上市",
    }
)
# The Stage-2 universe has only two lifecycle states.  A provider's paused or
# otherwise transitional code is not silently treated as active; it must be
# mapped and reviewed upstream before this adapter is used.
_KNOWN_LIST_STATUS_VALUES = _ACTIVE_LIST_STATUS_VALUES | _DELISTED_LIST_STATUS_VALUES
_KNOWN_A_STOCK_TYPE_VALUES = frozenset(
    {
        "A",
        "A_SHARE",
        "A-SHARE",
        "ASHARE",
        "COMMON_A",
        "COMMON STOCK",
        "EQUITY",
        "SHARE",
        "STOCK",
        "A股",
        "A 股",
        "普通股",
        "人民币普通股",
        "1",
    }
)
_MISSING_TEXT_TOKENS = frozenset({"", "NONE", "NAN", "NAT", "NULL", "NA", "N/A", "<NA>"})


@dataclass(frozen=True)
class ProviderCapability:
    """A declared capability, never proof that the capability is licensed."""

    provider_id: str
    datasets: tuple[str, ...]
    access_mode: str
    status: str
    limitations: tuple[str, ...]
    references: tuple[str, ...]


# The matrix is intentionally conservative.  ``candidate`` means that an
# endpoint appears capable of supplying a field; ``probe_only`` means it may
# be used for the bounded outcome-blind source probe but cannot be promoted to
# the Stage-2 input without a separate rights/semantic review.
PROVIDER_CAPABILITIES: tuple[ProviderCapability, ...] = (
    ProviderCapability(
        provider_id="tushare_pro",
        datasets=(
            "daily_bar_raw",
            "adjustment_factor",
            "trade_calendar_by_exchange",
            "security_master",
            "historical_security_list",
            "st_history",
            "suspension_history",
            "report_publication_date",
            "financial_indicator",
        ),
        access_mode="token_and_points_or_entitlement",
        status="candidate_subject_to_written_rights_review",
        limitations=(
            "daily and adjustment-factor responses must be joined and frozen before producing adjusted close",
            "stock_basic is not by itself a historical point-in-time membership table; retain historical-list evidence",
            "actual publication date must come from actual_date, never pre_date or a latest-only fallback",
            "ST and suspension endpoints need a complete date-by-date extraction and non-degeneracy audit",
            "the service agreement describes a personal, non-transferable, non-commercial, revocable licence; no aggregate publication right is inferred",
        ),
        references=(
            "https://tushare.pro/document/2?doc_id=27",
            "https://tushare.pro/document/2?doc_id=28",
            "https://tushare.pro/document/2?doc_id=162",
            "https://tushare.pro/document/2?doc_id=183",
            "https://tushare.pro/document/2?doc_id=214",
            "https://tushare.pro/document/1?doc_id=405",
        ),
    ),
    ProviderCapability(
        provider_id="akshare",
        datasets=("daily_bar_raw", "third_party_calendar_candidate"),
        access_mode="open_source_client_without_repository_credentials",
        status="probe_only",
        limitations=(
            "stock_zh_a_hist is a raw-bar probe endpoint and does not establish adjusted-close semantics",
            "tool_trade_date_hist_sina is a Sina calendar, not independently authoritative common SSE/SZSE evidence",
            "no locked historical publication-date, ST, suspension, or lifecycle contract is supplied by this adapter",
            "the MIT licence covers the client code, not the upstream data or redistribution rights",
        ),
        references=(
            "https://akshare.akfamily.xyz/data/stock/stock.html",
            "https://akshare.akfamily.xyz/data/tool/tool.html",
            "https://github.com/akfamily/akshare",
        ),
    ),
    ProviderCapability(
        provider_id="baostock",
        datasets=("daily_bar_candidate", "security_master_candidate", "calendar_candidate"),
        access_mode="open_source_client_service_login",
        status="probe_only",
        limitations=(
            "the public adapter does not provide a validated actual report-publication-date history",
            "isST and missing-row suspension semantics require independent historical verification",
            "adjustment and delisting endpoint semantics must be documented before IC use",
            "client-code licensing does not grant rights to publish the returned service data",
        ),
        references=(
            "https://pypi.org/project/baostock/",
            "https://github.com/akfamily/akshare",
        ),
    ),
    ProviderCapability(
        provider_id="official_exchange_and_cninfo",
        datasets=(
            "sse_calendar",
            "szse_calendar",
            "issuer_disclosure_documents",
            "issuer_listing_lifecycle",
        ),
        access_mode="official_public_pages_or_authorized_feed",
        status="candidate_for_calendar_and_disclosure_cross_check",
        limitations=(
            "public-page availability and historical bulk extraction are not guaranteed",
            "retain the exact source document, retrieval timestamp, and terms evidence",
            "official pages alone do not provide a complete adjusted-close panel or daily ST/suspension table",
            "SSE/SZSE disagreement must be resolved against retained authoritative evidence before forming a common calendar",
        ),
        references=(
            "https://www.sse.com.cn/disclosure/dealinstruc/calendar/index.shtml",
            "https://english.sse.com.cn/start/trading/schedule/",
            "https://www.szse.cn/",
            "https://www.cninfo.com.cn/",
        ),
    ),
    ProviderCapability(
        provider_id="licensed_vendor_wind_csmar_choice_or_equivalent",
        datasets=(
            "daily_bar_adjusted",
            "adjustment_factor",
            "security_master_pit",
            "st_history",
            "suspension_history",
            "trade_calendar_by_exchange",
            "report_publication_date",
            "financial_indicator_pit",
        ),
        access_mode="institutional_contract",
        status="preferred_if_contract_explicitly_allows_research_and_aggregate_reporting",
        limitations=(
            "vendor names are alternatives, not a claim that any contract is currently held",
            "the contract must identify historical coverage, point-in-time fields, adjusted-price construction, and review/publication rights",
            "a vendor's current snapshot cannot be relabelled as revision/vintage history without versioned values and as-of timestamps",
        ),
        references=(),
    ),
)


def provider_capability_matrix() -> tuple[dict[str, Any], ...]:
    """Return JSON-safe provider capability declarations."""

    return tuple(
        {
            "provider_id": item.provider_id,
            "datasets": list(item.datasets),
            "access_mode": item.access_mode,
            "status": item.status,
            "limitations": list(item.limitations),
            "references": list(item.references),
        }
        for item in PROVIDER_CAPABILITIES
    )


def assess_provider_capability(
    provider_id: str,
    required_datasets: Iterable[str],
) -> dict[str, Any]:
    """Assess declared endpoint coverage without treating it as authorization."""

    required = tuple(dict.fromkeys(str(value).strip() for value in required_datasets if str(value).strip()))
    capability = next((item for item in PROVIDER_CAPABILITIES if item.provider_id == provider_id), None)
    if capability is None:
        return {
            "provider_id": provider_id,
            "status": "unknown_provider",
            "required_datasets": list(required),
            "missing_datasets": list(required),
            "rights_review_required": True,
        }
    available = set(capability.datasets)
    missing = [dataset for dataset in required if dataset not in available]
    return {
        "provider_id": capability.provider_id,
        "status": "insufficient_declared_capability" if missing else capability.status,
        "required_datasets": list(required),
        "declared_datasets": list(capability.datasets),
        "missing_datasets": missing,
        "limitations": list(capability.limitations),
        "references": list(capability.references),
        "rights_review_required": True,
        "authorization_granted": False,
    }


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _safe_file(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise DataAccessError(f"input must be a regular non-symlink file: {candidate.name}")
    return candidate


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text[:10]
    if re.fullmatch(r"\d{8}", text):
        text = f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _nonblank(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _distinct_normalized(values: Sequence[Any]) -> list[str]:
    result: set[str] = set()
    for value in values:
        if not _nonblank(value):
            continue
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "是"}:
            text = "true"
        elif text in {"0", "false", "no", "n", "否"}:
            text = "false"
        result.add(text)
    return sorted(result)


def summarize_csv_metadata(path: str | Path, role: str) -> dict[str, Any]:
    """Summarize one Stage-2 input without exposing row values.

    This is intentionally stricter than a generic ``pandas.read_csv`` call:
    exact bytes are hashed, duplicate keys are counted, dates are parsed only
    for coverage, and only aggregate boolean distinct values are retained.
    """

    if role not in STAGE2_DATASET_ROLES:
        raise DataAccessError(f"unknown Stage-2 data role: {role}")
    file_path = _safe_file(path)
    payload = file_path.read_bytes()
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DataAccessError(f"{role} is not UTF-8 CSV") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    fields = list(reader.fieldnames or ())
    if not fields:
        raise DataAccessError(f"{role} has no CSV header")
    if len(fields) != len(set(fields)):
        raise DataAccessError(f"{role} has duplicate CSV headers")

    required = set(STAGE2_REQUIRED_FIELDS[role])
    missing = sorted(required - set(fields))
    rows = 0
    symbols: set[str] = set()
    dates: list[date] = []
    publish_dates: list[date] = []
    report_dates: list[date] = []
    non_null: dict[str, int] = {field: 0 for field in fields}
    distinct: dict[str, set[str]] = {
        field: set()
        for field in ("is_st", "is_suspended", "listStatus", "stockType")
        if field in fields
    }
    invalid_boolean_value_count: dict[str, int] = {
        field: 0 for field in ("is_st", "is_suspended") if field in fields
    }
    duplicate_key_count = 0
    seen_keys: set[tuple[str, ...]] = set()
    invalid_date_count = 0
    publication_before_report_count = 0
    delisted_count = 0
    delisted_missing_date_count = 0
    active_with_delist_count = 0
    delist_before_list_count = 0
    unknown_list_status_count = 0
    unknown_stock_type_count = 0
    invalid_delist_date_count = 0
    malformed_row_count = 0
    date_order_violation_count = 0
    previous_calendar_date: date | None = None
    exchange_values: set[str] = set()

    for row in reader:
        rows += 1
        # DictReader stores extra columns under ``None`` and short rows as
        # ``None`` values.  Both indicate a malformed record; retaining the
        # row for aggregate accounting is safer than silently dropping it.
        if None in row or any(row.get(field) is None for field in fields):
            malformed_row_count += 1
        symbol = str(row.get("symbol") or "").strip()
        if symbol:
            symbols.add(symbol)
        for field in fields:
            if _nonblank(row.get(field)):
                non_null[field] += 1
        for field in distinct:
            if _nonblank(row.get(field)):
                normalized = _distinct_normalized((row[field],))
                distinct[field].update(normalized or (str(row[field]).strip().lower(),))
                if field in invalid_boolean_value_count and normalized and normalized[0] not in {"true", "false"}:
                    invalid_boolean_value_count[field] += 1
        if role == "quotes":
            row_date = _parse_date(row.get("date"))
            key_date = row_date.isoformat() if row_date is not None else str(row.get("date") or "").strip()
            key = (symbol, key_date)
            exchange_values.add(symbol.rsplit(".", 1)[-1].upper() if "." in symbol else "")
        elif role == "stock_master":
            row_date = _parse_date(row.get("listDate"))
            key = (symbol,)
            status = str(row.get("listStatus") or "").strip().lower()
            status_upper = status.upper()
            if status_upper in _DELISTED_LIST_STATUS_VALUES:
                delisted_count += 1
            elif status_upper not in _KNOWN_LIST_STATUS_VALUES:
                unknown_list_status_count += 1
            stock_type = str(row.get("stockType") or "").strip().upper()
            if stock_type not in _KNOWN_A_STOCK_TYPE_VALUES:
                unknown_stock_type_count += 1
            delist_raw = row.get("delistDate")
            delist_text = str(delist_raw or "").strip()
            delist_is_null = delist_text.upper() in _MISSING_TEXT_TOKENS
            delist_date = None if delist_is_null else _parse_date(delist_text)
            if not delist_is_null and delist_date is None:
                invalid_delist_date_count += 1
            if status_upper in _DELISTED_LIST_STATUS_VALUES and delist_date is None:
                delisted_missing_date_count += 1
            if status_upper in _ACTIVE_LIST_STATUS_VALUES and delist_date is not None:
                active_with_delist_count += 1
            if delist_date is not None and row_date is not None and delist_date < row_date:
                delist_before_list_count += 1
            exchange_values.add(symbol.rsplit(".", 1)[-1].upper() if "." in symbol else "")
        elif role == "fundamentals":
            row_date = _parse_date(row.get("reportPeriodEnd"))
            publish = _parse_date(row.get("publishDate"))
            report = _parse_date(row.get("reportPeriodEnd"))
            if publish is not None:
                publish_dates.append(publish)
            if report is not None:
                report_dates.append(report)
            if publish is not None and report is not None and publish < report:
                publication_before_report_count += 1
            report_key = report.isoformat() if report is not None else str(row.get("reportPeriodEnd") or "").strip()
            key = (symbol, report_key)
        else:
            row_date = _parse_date(row.get("date"))
            key_date = row_date.isoformat() if row_date is not None else str(row.get("date") or "").strip()
            key = (key_date,)
        if row_date is not None:
            dates.append(row_date)
            if role == "official_calendar":
                if previous_calendar_date is not None and row_date <= previous_calendar_date:
                    date_order_violation_count += 1
                previous_calendar_date = row_date
        elif any(_nonblank(row.get(field)) for field in ("date", "listDate", "reportPeriodEnd")):
            invalid_date_count += 1
        if key in seen_keys:
            duplicate_key_count += 1
        seen_keys.add(key)

    ranges: dict[str, list[str | None]] = {}
    if role == "fundamentals":
        ranges["reportPeriodEnd"] = _date_range(report_dates)
        ranges["publishDate"] = _date_range(publish_dates)
    else:
        ranges["date" if role != "stock_master" else "listDate"] = _date_range(dates)
        if role == "stock_master":
            delist_dates: list[date] = []
            # Parse the optional delist date a second time only to retain its
            # aggregate range; semantic counts were collected in the main pass.
            for row in csv.DictReader(io.StringIO(text, newline="")):
                parsed = _parse_date(row.get("delistDate"))
                if parsed is not None:
                    delist_dates.append(parsed)
            ranges["delistDate"] = _date_range(delist_dates)

    non_null_rates = {
        field: round(count / rows, 10) if rows else 0.0
        for field, count in non_null.items()
    }
    distinct_values = {field: sorted(values) for field, values in distinct.items()}
    return {
        "schema_version": "stage2_data_access_metadata_v1",
        "role": role,
        "file_name": file_path.name,
        "sha256": _sha256_bytes(payload),
        "byte_size": len(payload),
        "row_count": rows,
        "symbol_count": len(symbols),
        "columns": fields,
        "required_columns": list(STAGE2_REQUIRED_FIELDS[role]),
        "missing_required_columns": missing,
        "date_ranges": ranges,
        "non_null_rates": non_null_rates,
        "distinct_values": distinct_values,
        "invalid_boolean_value_count": invalid_boolean_value_count,
        "duplicate_key_count": duplicate_key_count,
        "invalid_date_count": invalid_date_count,
        "publication_before_report_count": publication_before_report_count,
        "delisted_row_count": delisted_count,
        "delisted_missing_date_count": delisted_missing_date_count,
        "active_with_delist_count": active_with_delist_count,
        "delist_before_list_count": delist_before_list_count,
        "unknown_list_status_count": unknown_list_status_count,
        "unknown_stock_type_count": unknown_stock_type_count,
        "invalid_delist_date_count": invalid_delist_date_count,
        "malformed_row_count": malformed_row_count,
        "date_order_violation_count": date_order_violation_count,
        "exchange_values": sorted(value for value in exchange_values if value),
    }


def _date_range(values: Sequence[date]) -> list[str | None]:
    return [min(values).isoformat() if values else None, max(values).isoformat() if values else None]


def audit_stage2_field_contract(
    metadata_by_role: Mapping[str, Mapping[str, Any]],
    *,
    rights_attestation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate metadata-only readiness gates.

    The result is deliberately *not* a permission to run Stage 2.  It reports
    the exact reasons that remain before a human can complete the data-review
    and registration chain.
    """

    if not isinstance(metadata_by_role, Mapping):
        return {
            "schema_version": "stage2_data_access_audit_v1",
            "status": "blocked",
            "issues": ["METADATA_BY_ROLE_NOT_OBJECT"],
            "roles": {},
            "rights": validate_rights_attestation(rights_attestation),
            "outcome_blind": True,
            "authorization_granted": False,
        }
    issues: list[str] = []
    role_reports: dict[str, Any] = {}
    for role in STAGE2_DATASET_ROLES:
        metadata = metadata_by_role.get(role)
        if metadata is None:
            issues.append(f"MISSING_ROLE:{role}")
            continue
        if not isinstance(metadata, Mapping):
            issues.append(f"INVALID_ROLE_METADATA:{role}")
            continue
        role_reports[role] = dict(metadata)
        missing_columns = metadata.get("missing_required_columns")
        if not isinstance(missing_columns, (list, tuple, set)):
            issues.append(f"MISSING_FIELDS_METADATA:{role}")
        elif missing_columns:
            issues.append(f"MISSING_FIELDS:{role}")
        row_count = _metadata_count(metadata, "row_count")
        if row_count is None:
            issues.append(f"INVALID_ROW_COUNT:{role}")
        elif row_count <= 0:
            issues.append(f"EMPTY_INPUT:{role}")
        duplicate_count = _metadata_count(metadata, "duplicate_key_count")
        if duplicate_count is None:
            issues.append(f"INVALID_DUPLICATE_COUNT:{role}")
        elif duplicate_count > 0:
            issues.append(f"DUPLICATE_KEYS:{role}")
        invalid_dates = _metadata_count(metadata, "invalid_date_count")
        if invalid_dates is None:
            issues.append(f"INVALID_DATE_COUNT:{role}")
        elif invalid_dates > 0:
            issues.append(f"INVALID_DATES:{role}")
        malformed_rows = _metadata_count(metadata, "malformed_row_count")
        if malformed_rows is None:
            issues.append(f"INVALID_MALFORMED_ROW_COUNT:{role}")
        elif malformed_rows > 0:
            issues.append(f"MALFORMED_ROWS:{role}")
        if role == "official_calendar":
            order_violations = _metadata_count(metadata, "date_order_violation_count")
            if order_violations is None:
                issues.append("INVALID_CALENDAR_ORDER_COUNT")
            elif order_violations > 0:
                issues.append("CALENDAR_NOT_STRICTLY_INCREASING")

    quotes_value = metadata_by_role.get("quotes", {})
    quotes = quotes_value if isinstance(quotes_value, Mapping) else {}
    quote_range = _metadata_range(quotes, "date")
    if not _range_is_valid(quote_range):
        issues.append("QUOTE_DATE_RANGE_INVALID")
    if _range_start_after(quote_range, STAGE2_TARGETS["quote_start"]):
        issues.append("QUOTE_WARMUP_NOT_COVERED")
    if _range_end_before(quote_range, STAGE2_TARGETS["quote_end"]):
        issues.append("QUOTE_ENDPOINT_NOT_COVERED")
    fundamentals_value = metadata_by_role.get("fundamentals", {})
    fundamentals = fundamentals_value if isinstance(fundamentals_value, Mapping) else {}
    fundamental_publish_range = _metadata_range(fundamentals, "publishDate")
    fundamental_report_range = _metadata_range(fundamentals, "reportPeriodEnd")
    if not _range_is_valid(fundamental_publish_range):
        issues.append("FUNDAMENTAL_PUBLICATION_RANGE_INVALID")
    if not _range_is_valid(fundamental_report_range):
        issues.append("FUNDAMENTAL_REPORT_RANGE_INVALID")
    if _range_start_after(fundamental_publish_range, STAGE2_TARGETS["fundamental_start"]):
        issues.append("FUNDAMENTAL_PUBLICATION_HISTORY_NOT_COVERED")
    if _range_start_after(fundamental_report_range, STAGE2_TARGETS["fundamental_start"]):
        issues.append("FUNDAMENTAL_REPORT_HISTORY_NOT_COVERED")
    if _range_end_before(fundamental_report_range, STAGE2_TARGETS["fundamental_end"]):
        issues.append("FUNDAMENTAL_REPORT_INTERVAL_NOT_COVERED")
    publication_order_count = _metadata_count(fundamentals, "publication_before_report_count")
    if publication_order_count is None:
        issues.append("INVALID_PUBLICATION_ORDER_COUNT")
    elif publication_order_count > 0:
        issues.append("PUBLICATION_BEFORE_REPORT_PERIOD")
    calendar_value = metadata_by_role.get("official_calendar", {})
    calendar = calendar_value if isinstance(calendar_value, Mapping) else {}
    calendar_range = _metadata_range(calendar, "date")
    if not _range_is_valid(calendar_range):
        issues.append("CALENDAR_DATE_RANGE_INVALID")
    if _range_month_start_after(calendar_range, STAGE2_TARGETS["calendar_start_month"]):
        issues.append("CALENDAR_START_NOT_COVERED")
    if _range_month_end_before(calendar_range, STAGE2_TARGETS["calendar_end_month"]):
        issues.append("CALENDAR_END_NOT_COVERED")
    for field in ("is_st", "is_suspended"):
        distinct_values = quotes.get("distinct_values", {})
        raw_values = distinct_values.get(field, []) if isinstance(distinct_values, Mapping) else []
        values = {str(value).strip().lower() for value in raw_values} if isinstance(raw_values, (list, tuple, set)) else set()
        if not {"true", "false"}.issubset(values):
            issues.append(f"DEGENERATE_FIELD:{field}")
        bool_counts = quotes.get("invalid_boolean_value_count", {})
        invalid_bool_count = _metadata_count(bool_counts, field) if isinstance(bool_counts, Mapping) else None
        if invalid_bool_count is None:
            issues.append(f"INVALID_BOOLEAN_VALUE_COUNT:{field}")
        elif invalid_bool_count > 0:
            issues.append(f"INVALID_BOOLEAN_VALUE:{field}")

    master_value = metadata_by_role.get("stock_master", {})
    master = master_value if isinstance(master_value, Mapping) else {}
    delisted_rows = _metadata_count(master, "delisted_row_count")
    if delisted_rows is None:
        issues.append("INVALID_DELISTED_ROW_COUNT")
    elif delisted_rows <= 0:
        issues.append("NO_DELISTED_SECURITY_ROWS")
    raw_exchanges = master.get("exchange_values", [])
    exchanges = {
        str(value).upper()
        for value in raw_exchanges
    } if isinstance(raw_exchanges, (list, tuple, set)) else set()
    if not {"SH", "SZ"}.issubset(exchanges):
        issues.append("STOCK_MASTER_MISSING_SH_OR_SZ")
    if exchanges - {"SH", "SZ"}:
        issues.append("STOCK_MASTER_UNEXPECTED_EXCHANGE")
    delisted_missing_dates = _metadata_count(master, "delisted_missing_date_count")
    if delisted_missing_dates is None:
        issues.append("INVALID_DELISTED_MISSING_DATE_COUNT")
    elif delisted_missing_dates > 0:
        issues.append("DELISTED_WITHOUT_DELIST_DATE")
    active_with_delist = _metadata_count(master, "active_with_delist_count")
    if active_with_delist is None:
        issues.append("INVALID_ACTIVE_WITH_DELIST_COUNT")
    elif active_with_delist > 0:
        issues.append("ACTIVE_WITH_DELIST_DATE")
    delist_before_list = _metadata_count(master, "delist_before_list_count")
    if delist_before_list is None:
        issues.append("INVALID_DELIST_BEFORE_LIST_COUNT")
    elif delist_before_list > 0:
        issues.append("DELIST_BEFORE_LIST_DATE")
    invalid_delists = _metadata_count(master, "invalid_delist_date_count")
    if invalid_delists is None:
        issues.append("INVALID_DELIST_DATE_COUNT")
    elif invalid_delists > 0:
        issues.append("INVALID_DELIST_DATES")
    unknown_status = _metadata_count(master, "unknown_list_status_count")
    if unknown_status is None:
        issues.append("INVALID_UNKNOWN_STATUS_COUNT")
    elif unknown_status > 0:
        issues.append("UNKNOWN_LIST_STATUS")
    unknown_type = _metadata_count(master, "unknown_stock_type_count")
    if unknown_type is None:
        issues.append("INVALID_UNKNOWN_STOCK_TYPE_COUNT")
    elif unknown_type > 0:
        issues.append("UNKNOWN_STOCK_TYPE")

    # Required key fields must be populated.  ``delistDate`` is intentionally
    # nullable for active securities and is therefore excluded from this loop.
    for role, fields in {
        "quotes": ("date", "symbol", "close", "amount", "is_st", "is_suspended"),
        "stock_master": ("symbol", "listDate", "listStatus", "stockType"),
        "fundamentals": ("symbol", "roeDiluted", "publishDate", "reportPeriodEnd"),
        "official_calendar": ("date",),
    }.items():
        metadata = metadata_by_role.get(role, {})
        rates = metadata.get("non_null_rates", {})
        for field in fields:
            rate = rates.get(field) if isinstance(rates, Mapping) else None
            if rate is None:
                issues.append(f"MISSING_NON_NULL_RATE:{role}:{field}")
                continue
            try:
                numeric_rate = float(rate)
            except (TypeError, ValueError):
                issues.append(f"INVALID_NON_NULL_RATE:{role}:{field}")
                continue
            if not math.isfinite(numeric_rate) or not 0.0 <= numeric_rate <= 1.0:
                issues.append(f"INVALID_NON_NULL_RATE:{role}:{field}")
            elif numeric_rate < 1.0:
                issues.append(f"NULL_REQUIRED_FIELD:{role}:{field}")

    rights_result = validate_rights_attestation(rights_attestation)
    if rights_result["status"] != "valid":
        issues.extend(f"RIGHTS_{issue}" for issue in rights_result["issues"])
    return {
        "schema_version": "stage2_data_access_audit_v1",
        "status": "pass_metadata_only" if not issues else "blocked",
        "issues": sorted(dict.fromkeys(issues)),
        "roles": role_reports,
        "rights": rights_result,
        "outcome_blind": True,
        "authorization_granted": False,
    }


def _metadata_range(metadata: Mapping[str, Any], field: str) -> list[str | None]:
    """Read a range from either the scanner's nested or flat representation."""

    nested = metadata.get("date_ranges", {})
    value = nested.get(field) if isinstance(nested, Mapping) else None
    if value is None:
        value = metadata.get(field)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
        return [None, None]
    return [str(value[0]) if value[0] is not None else None, str(value[1]) if value[1] is not None else None]


def _range_is_valid(value: Sequence[str | None]) -> bool:
    """Return whether a metadata range contains two ordered ISO dates."""

    if len(value) != 2 or value[0] is None or value[1] is None:
        return False
    try:
        start = date.fromisoformat(str(value[0]))
        end = date.fromisoformat(str(value[1]))
    except (TypeError, ValueError):
        return False
    return start <= end


def _range_start_after(value: Sequence[str | None], boundary: str) -> bool:
    """Fail closed when a range is missing or starts after ``boundary``."""

    if not _range_is_valid(value):
        return True
    return str(value[0]) > boundary


def _range_end_before(value: Sequence[str | None], boundary: str) -> bool:
    """Fail closed when a range is missing or ends before ``boundary``."""

    if not _range_is_valid(value):
        return True
    return str(value[1]) < boundary


def _range_month_start_after(value: Sequence[str | None], boundary: str) -> bool:
    if not _range_is_valid(value):
        return True
    return str(value[0])[:7] > boundary


def _range_month_end_before(value: Sequence[str | None], boundary: str) -> bool:
    if not _range_is_valid(value):
        return True
    return str(value[1])[:7] < boundary


def _metadata_count(metadata: Mapping[str, Any], key: str) -> int | None:
    """Read an integer metadata count without allowing malformed values through."""

    value = metadata.get(key)
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed < 0 or (isinstance(value, float) and not value.is_integer()):
        return None
    return parsed


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ISO_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T.+(?:Z|[+-]\d{2}:?\d{2})$")


def validate_rights_attestation(
    attestation: Mapping[str, Any] | None,
    *,
    required_datasets: Iterable[str] = STAGE2_DATASET_ROLES,
) -> dict[str, Any]:
    """Validate a rights packet while keeping all legal decisions human-bound."""

    issues: list[str] = []
    if not isinstance(attestation, Mapping):
        return {"schema_version": "stage2_data_rights_attestation_v1", "status": "missing", "issues": ["ATTESTATION_MISSING"]}
    if attestation.get("schema_version") != "stage2_data_rights_attestation_v1":
        issues.append("SCHEMA_VERSION")
    if attestation.get("study_id") != "a-share-factor-timing-bias-decomposition-v2":
        issues.append("STUDY_ID")
    if attestation.get("status") != "attested":
        issues.append("STATUS_NOT_ATTESTED")
    for field in (
        "study_id",
        "attested_at",
        "attestor",
        "attestor_role",
        "contract_reference",
        "contract_effective_at",
        "contract_evidence_sha256",
    ):
        if not str(attestation.get(field) or "").strip():
            issues.append(f"MISSING_{field.upper()}")
    attested_text = str(attestation.get("attested_at") or "")
    if not _ISO_TIMESTAMP_RE.match(attested_text):
        issues.append("ATTESTED_AT_NOT_TIMEZONE_AWARE")
    effective_value = attestation.get("contract_effective_at")
    expiry_value = attestation.get("contract_expiry_at")
    if not _ISO_TIMESTAMP_RE.match(str(effective_value or "")):
        issues.append("CONTRACT_EFFECTIVE_AT_NOT_TIMEZONE_AWARE")
    if expiry_value not in (None, "") and not _ISO_TIMESTAMP_RE.match(str(expiry_value)):
        issues.append("CONTRACT_EXPIRY_AT_NOT_TIMEZONE_AWARE")
    if _SHA256_RE.match(str(attestation.get("contract_evidence_sha256") or "")) is None:
        issues.append("CONTRACT_EVIDENCE_HASH_INVALID")
    effective_at: datetime | None = None
    expiry_at: datetime | None = None
    attested_at_for_order: datetime | None = None
    if isinstance(effective_value, str) and _ISO_TIMESTAMP_RE.match(effective_value):
        try:
            effective_at = datetime.fromisoformat(effective_value.replace("Z", "+00:00"))
            if effective_at.tzinfo is None or effective_at.utcoffset() is None:
                issues.append("CONTRACT_EFFECTIVE_AT_NOT_TIMEZONE_AWARE")
        except ValueError:
            issues.append("CONTRACT_EFFECTIVE_AT_INVALID")
    if expiry_value not in (None, "") and isinstance(expiry_value, str) and _ISO_TIMESTAMP_RE.match(expiry_value):
        try:
            expiry_at = datetime.fromisoformat(expiry_value.replace("Z", "+00:00"))
            if expiry_at.tzinfo is None or expiry_at.utcoffset() is None:
                issues.append("CONTRACT_EXPIRY_AT_NOT_TIMEZONE_AWARE")
        except ValueError:
            issues.append("CONTRACT_EXPIRY_AT_INVALID")
    if isinstance(attestation.get("attested_at"), str) and _ISO_TIMESTAMP_RE.match(attestation["attested_at"]):
        try:
            attested_at_for_order = datetime.fromisoformat(
                attestation["attested_at"].replace("Z", "+00:00")
            )
            if attested_at_for_order.tzinfo is None or attested_at_for_order.utcoffset() is None:
                issues.append("ATTESTED_AT_NOT_TIMEZONE_AWARE")
        except ValueError:
            issues.append("ATTESTED_AT_INVALID")
    if effective_at is not None and attested_at_for_order is not None:
        if effective_at > attested_at_for_order:
            issues.append("CONTRACT_NOT_EFFECTIVE_AT_ATTESTATION")
        if expiry_at is not None and (
            expiry_at < attested_at_for_order or expiry_at < effective_at
        ):
            issues.append("CONTRACT_EXPIRED_AT_ATTESTATION")
    datasets = attestation.get("datasets")
    if not isinstance(datasets, Mapping):
        issues.append("DATASETS_NOT_OBJECT")
        datasets = {}
    for role in required_datasets:
        record = datasets.get(role)
        if not isinstance(record, Mapping):
            issues.append(f"DATASET_MISSING:{role}")
            continue
        for field in (
            "source_name",
            "source_reference",
            "license_or_contract_scope",
            "terms_evidence_sha256",
        ):
            if not str(record.get(field) or "").strip():
                issues.append(f"{role}:MISSING_{field}")
        if not _SHA256_RE.match(str(record.get("terms_evidence_sha256") or "")):
            issues.append(f"{role}:TERMS_HASH_INVALID")
        for field in (
            "local_storage_permitted",
            "local_analysis_permitted",
            "aggregate_publication_permitted",
            "raw_redistribution_permitted",
            "hash_publication_permitted",
            "controlled_reviewer_rerun_permitted",
        ):
            if not isinstance(record.get(field), bool):
                issues.append(f"{role}:BOOLEAN_REQUIRED:{field}")
        for field in (
            "local_storage_permitted",
            "local_analysis_permitted",
            "aggregate_publication_permitted",
            "hash_publication_permitted",
            "controlled_reviewer_rerun_permitted",
        ):
            if record.get(field) is not True:
                issues.append(f"{role}:PERMISSION_NOT_GRANTED:{field}")
        if record.get("raw_redistribution_permitted") is not False:
            issues.append(f"{role}:RAW_REDISTRIBUTION_MUST_BE_FALSE")
        if not str(record.get("source_reference") or "").startswith(("https://", "http://", "urn:", "contract:")):
            issues.append(f"{role}:SOURCE_REFERENCE_NOT_TRACEABLE")
        if role == "official_calendar" and record.get("calendar_dates_publication_permitted") is not True:
            issues.append("official_calendar:CALENDAR_DATE_PUBLICATION_NOT_ATTESTED")

    private_ledger = attestation.get("private_endpoint_reason_ledger")
    if not isinstance(private_ledger, Mapping):
        issues.append("PRIVATE_LEDGER_NOT_OBJECT")
    else:
        if private_ledger.get("retention_permitted") is not True:
            issues.append("PRIVATE_LEDGER_RETENTION_NOT_PERMITTED")
        if private_ledger.get("hash_binding_permitted") is not True:
            issues.append("PRIVATE_LEDGER_HASH_BINDING_NOT_PERMITTED")
        if private_ledger.get("row_redistribution_permitted") is not False:
            issues.append("PRIVATE_LEDGER_RAW_ROWS_MUST_NOT_BE_REDISTRIBUTED")
        if not _SHA256_RE.match(str(private_ledger.get("terms_evidence_sha256") or "")):
            issues.append("PRIVATE_LEDGER_TERMS_HASH_INVALID")

    public_outputs = attestation.get("public_outputs")
    if not isinstance(public_outputs, Mapping):
        issues.append("PUBLIC_OUTPUTS_NOT_OBJECT")
    else:
        for field in (
            "aggregate_coverage_permitted",
            "aggregate_missingness_permitted",
            "aggregate_reason_counts_permitted",
            "cryptographic_hashes_permitted",
            "exact_official_calendar_dates_permitted",
        ):
            if public_outputs.get(field) is not True:
                issues.append(f"PUBLIC_OUTPUT_NOT_ATTESTED:{field}")
        if public_outputs.get("raw_rows_permitted") is not False:
            issues.append("PUBLIC_OUTPUT_RAW_ROWS_MUST_BE_FALSE")

    signature = attestation.get("signature")
    if not isinstance(signature, Mapping):
        issues.append("SIGNATURE_NOT_OBJECT")
    else:
        if signature.get("type") != "human_verified_evidence":
            issues.append("SIGNATURE_TYPE_INVALID")
        if not _SHA256_RE.match(str(signature.get("evidence_sha256") or "")):
            issues.append("SIGNATURE_EVIDENCE_HASH_INVALID")
        if not str(signature.get("signer_identity") or "").strip():
            issues.append("SIGNATURE_IDENTITY_MISSING")
        verification_uri = str(signature.get("verification_uri") or "")
        if not verification_uri.startswith("https://"):
            issues.append("SIGNATURE_VERIFICATION_URI_INVALID")
        if signature.get("trust_boundary") != (
            "A human reviewer must verify the contract and the exact permitted outputs."
        ):
            issues.append("SIGNATURE_TRUST_BOUNDARY_INVALID")
    evidence_index = attestation.get("evidence_index")
    if not isinstance(evidence_index, list) or not evidence_index:
        issues.append("EVIDENCE_INDEX_MISSING")
    else:
        for index, item in enumerate(evidence_index):
            if not isinstance(item, Mapping):
                issues.append(f"EVIDENCE_INDEX_ITEM_INVALID:{index}")
                continue
            if not str(item.get("kind") or "").strip():
                issues.append(f"EVIDENCE_INDEX_KIND_MISSING:{index}")
            reference = str(item.get("reference") or "")
            if not reference.startswith(("https://", "http://", "urn:", "contract:")):
                issues.append(f"EVIDENCE_INDEX_REFERENCE_INVALID:{index}")
            if _SHA256_RE.match(str(item.get("sha256") or "")) is None:
                issues.append(f"EVIDENCE_INDEX_HASH_INVALID:{index}")

    # Prevent accidental inclusion of credentials or raw secrets in the packet.
    try:
        serialized = json.dumps(attestation, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        serialized = ""
        issues.append("ATTESTATION_NOT_JSON_SERIALIZABLE")
    if re.search(r"(?i)(api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*['\"][^'\"]+", serialized):
        issues.append("SECRET_LIKE_VALUE_PRESENT")
    return {
        "schema_version": "stage2_data_rights_attestation_v1",
        "status": "valid" if not issues else "invalid",
        "issues": sorted(dict.fromkeys(issues)),
        "authorization_granted": False,
    }


def _require_columns(frame: pd.DataFrame, columns: Iterable[str], label: str) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise DataAccessError(f"{label} must be a pandas DataFrame")
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise DataAccessError(f"{label} missing required columns: {missing}")


def _date_series(frame: pd.DataFrame, column: str, label: str) -> pd.Series:
    parsed = pd.to_datetime(frame[column].astype(str), format="%Y%m%d", errors="coerce")
    # Some callers already provide ISO dates; accept them only if the compact
    # representation failed for that row.
    fallback = pd.to_datetime(frame[column].astype(str), errors="coerce")
    parsed = parsed.where(parsed.notna(), fallback)
    if parsed.isna().any():
        raise DataAccessError(f"{label} contains invalid dates in {column}")
    return parsed.dt.normalize()


def _coerce_finite_numeric(
    frame: pd.DataFrame,
    field: str,
    label: str,
    *,
    strictly_positive: bool = False,
    nonnegative: bool = False,
) -> pd.Series:
    """Coerce a numeric field and reject NaN, infinities, and bad signs."""

    values = pd.to_numeric(frame[field], errors="coerce")
    finite = values.map(
        lambda value: (
            False
            if pd.isna(value)
            else math.isfinite(float(value))
        )
    )
    if not bool(finite.all()):
        raise DataAccessError(f"{label} has non-finite or non-numeric {field}")
    if strictly_positive and bool((values <= 0).any()):
        raise DataAccessError(f"{label} has non-positive {field}")
    if nonnegative and bool((values < 0).any()):
        raise DataAccessError(f"{label} has negative {field}")
    return values


def normalize_tushare_daily_frame(
    raw: pd.DataFrame,
    adjustment_factors: pd.DataFrame,
) -> pd.DataFrame:
    """Join Tushare daily and ``adj_factor`` rows into adjusted-close quotes.

    The join is exact on ``(ts_code, trade_date)``.  No forward/backward fill
    or inferred factor is allowed.  Amount is converted from thousand CNY and
    volume from lots to shares, matching the existing project contract.
    """

    _require_columns(raw, ("ts_code", "trade_date", "close", "amount"), "Tushare daily")
    _require_columns(adjustment_factors, ("ts_code", "trade_date", "adj_factor"), "Tushare adj_factor")
    if raw.empty:
        raise DataAccessError("Tushare daily is empty")
    if adjustment_factors.empty:
        raise DataAccessError("Tushare daily has missing or non-positive adjustment factors")
    daily = raw.copy()
    factors = adjustment_factors.copy()
    daily["trade_date"] = _date_series(daily, "trade_date", "Tushare daily")
    factors["trade_date"] = _date_series(factors, "trade_date", "Tushare adj_factor")
    daily["ts_code"] = daily["ts_code"].astype(str).str.strip().str.upper()
    factors["ts_code"] = factors["ts_code"].astype(str).str.strip().str.upper()
    if daily["ts_code"].eq("").any() or daily["ts_code"].isin(_MISSING_TEXT_TOKENS).any():
        raise DataAccessError("Tushare daily contains blank symbols")
    if factors["ts_code"].eq("").any() or factors["ts_code"].isin(_MISSING_TEXT_TOKENS).any():
        raise DataAccessError("Tushare adj_factor contains blank symbols")
    if daily.duplicated(["ts_code", "trade_date"]).any():
        raise DataAccessError("Tushare daily has duplicate symbol-date keys")
    if factors.duplicated(["ts_code", "trade_date"]).any():
        raise DataAccessError("Tushare adj_factor has duplicate symbol-date keys")
    joined = daily.merge(
        factors[["ts_code", "trade_date", "adj_factor"]],
        on=["ts_code", "trade_date"],
        how="left",
        validate="one_to_one",
    )
    # Keep a distinct diagnostic for an unmatched exact key; this is the
    # common failure when a provider returns a daily row without its corporate
    # action factor and must not be confused with a numeric-quality failure.
    raw_adj_factor = pd.to_numeric(joined["adj_factor"], errors="coerce")
    if raw_adj_factor.isna().any():
        raise DataAccessError("Tushare daily has missing or non-positive adjustment factors")
    joined["adj_factor"] = _coerce_finite_numeric(
        joined.assign(adj_factor=raw_adj_factor),
        "adj_factor",
        "Tushare daily",
        strictly_positive=True,
    )
    joined["close"] = _coerce_finite_numeric(
        joined, "close", "Tushare daily", strictly_positive=True
    )
    joined["amount"] = _coerce_finite_numeric(
        joined, "amount", "Tushare daily", nonnegative=True
    )
    if "vol" in joined:
        joined["vol"] = _coerce_finite_numeric(
            joined, "vol", "Tushare daily", nonnegative=True
        )
    for field in ("open", "high", "low", "pre_close"):
        if field in joined:
            joined[field] = _coerce_finite_numeric(
                joined, field, "Tushare daily", strictly_positive=True
            )
    result = pd.DataFrame(
        {
            "date": joined["trade_date"],
            "symbol": joined["ts_code"],
            "close_raw": joined["close"],
            "close": joined["close"] * joined["adj_factor"],
            "adjustment_factor": joined["adj_factor"],
            "amount": joined["amount"] * 1000.0,
        }
    )
    if "vol" in joined:
        result["volume"] = joined["vol"] * 100.0
    for field in ("open", "high", "low", "pre_close"):
        if field in joined:
            result[field] = joined[field]
    if not result["close"].map(lambda value: math.isfinite(float(value)) and value > 0).all():
        raise DataAccessError("Tushare daily adjusted close is non-finite or non-positive")
    return result.sort_values(["symbol", "date"]).reset_index(drop=True)


def normalize_tushare_trade_calendar_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Create a common SSE/SZSE open-session calendar from exchange rows.

    Missing exchange rows and SSE/SZSE disagreements fail closed.  The output
    contains dates only; source provenance and rights remain in the attestation.
    """

    _require_columns(raw, ("exchange", "cal_date", "is_open"), "Tushare trade_cal")
    frame = raw.copy()
    frame["exchange"] = frame["exchange"].astype(str).str.strip().str.upper().replace({"SH": "SSE", "SZ": "SZSE"})
    frame = frame[frame["exchange"].isin({"SSE", "SZSE"})].copy()
    frame["date"] = _date_series(frame, "cal_date", "Tushare trade_cal")
    frame["is_open"] = frame["is_open"].map(_to_bool)
    if frame["is_open"].isna().any():
        raise DataAccessError("Tushare trade_cal has invalid is_open values")
    duplicate = frame.duplicated(["date", "exchange"], keep=False)
    if duplicate.any():
        raise DataAccessError("Tushare trade_cal has duplicate date-exchange keys")
    pivot = frame.pivot(index="date", columns="exchange", values="is_open")
    if not {"SSE", "SZSE"}.issubset(pivot.columns):
        raise DataAccessError("Tushare trade_cal must contain both SSE and SZSE rows")
    # A missing exchange row is not evidence that that exchange was closed.
    # Form a common calendar only when both exchanges explicitly report a
    # value for every supplied date; never fill a missing row implicitly.
    if pivot[["SSE", "SZSE"]].isna().any(axis=1).any():
        raise DataAccessError(
            "Tushare trade_cal has dates missing an SSE or SZSE row; no implicit closed-day fill is allowed"
        )
    disagreement = pivot["SSE"].notna() & pivot["SZSE"].notna() & (pivot["SSE"] != pivot["SZSE"])
    if disagreement.any():
        raise DataAccessError("SSE/SZSE trade-calendar disagreement requires human resolution")
    common = pivot[(pivot["SSE"] == True) & (pivot["SZSE"] == True)].reset_index()  # noqa: E712
    return common[["date"]].sort_values("date").reset_index(drop=True)


def normalize_tushare_disclosure_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Map only *actual* report disclosure dates to the Stage-2 contract."""

    _require_columns(raw, ("ts_code", "end_date", "actual_date"), "Tushare disclosure_date")
    frame = raw.copy()
    if frame.empty:
        raise DataAccessError("Tushare disclosure_date is empty")
    frame["symbol"] = frame["ts_code"].astype(str).str.strip().str.upper()
    if frame["symbol"].eq("").any() or frame["symbol"].isin(_MISSING_TEXT_TOKENS).any():
        raise DataAccessError("Tushare disclosure_date contains blank symbols")
    frame["reportPeriodEnd"] = _date_series(frame, "end_date", "Tushare disclosure_date")
    actual = frame["actual_date"].astype(str).str.strip()
    if actual.str.upper().isin(_MISSING_TEXT_TOKENS).any():
        raise DataAccessError("Tushare disclosure_date has rows without actual_date; do not substitute scheduled dates")
    frame["publishDate"] = _date_series(frame, "actual_date", "Tushare disclosure_date")
    if (frame["publishDate"] < frame["reportPeriodEnd"]).any():
        raise DataAccessError(
            "Tushare disclosure_date contains publication dates before the report period end"
        )
    if frame.duplicated(["symbol", "reportPeriodEnd"]).any():
        raise DataAccessError("Tushare disclosure_date has duplicate symbol-report periods")
    return frame[["symbol", "reportPeriodEnd", "publishDate"]].sort_values(["symbol", "reportPeriodEnd"]).reset_index(drop=True)


def normalize_tushare_stock_master_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize a *complete* lifecycle export, without deriving status.

    Tushare's current-list endpoint is not enough for survivorship-bias
    control.  This adapter therefore requires explicit list/delist/status/type
    columns in the supplied frame; it will not manufacture a delist date or
    infer an active status from a missing value.
    """

    _require_columns(
        raw,
        ("ts_code", "list_date", "delist_date", "list_status", "stock_type"),
        "Tushare historical stock master",
    )
    frame = raw.copy()
    if frame.empty:
        raise DataAccessError("Tushare stock master is empty")
    frame["symbol"] = frame["ts_code"].astype(str).str.strip().str.upper()
    if frame["symbol"].eq("").any() or frame["symbol"].isin(_MISSING_TEXT_TOKENS).any():
        raise DataAccessError("Tushare stock master contains blank symbols")
    frame["listDate"] = _date_series(frame, "list_date", "Tushare stock master")
    raw_delist = frame["delist_date"].astype(str).str.strip()
    parsed_delist = raw_delist.map(
        lambda value: None if value.upper() in _MISSING_TEXT_TOKENS else _parse_date(value)
    )
    frame["delistDate"] = pd.to_datetime(parsed_delist, errors="coerce").dt.normalize()
    invalid_delist = (
        ~raw_delist.str.upper().isin(_MISSING_TEXT_TOKENS)
        & frame["delistDate"].isna()
    )
    if invalid_delist.any():
        raise DataAccessError("Tushare stock master contains invalid delist_date values")
    frame["listStatus"] = frame["list_status"].astype(str).str.strip().str.upper()
    frame["stockType"] = frame["stock_type"].astype(str).str.strip().str.upper()
    if frame["listStatus"].eq("").any() or frame["listStatus"].isin(_MISSING_TEXT_TOKENS).any():
        raise DataAccessError("Tushare stock master contains blank list_status values")
    if frame["stockType"].eq("").any() or frame["stockType"].isin(_MISSING_TEXT_TOKENS).any():
        raise DataAccessError("Tushare stock master contains blank stock_type values")
    unknown_status = ~frame["listStatus"].isin(_KNOWN_LIST_STATUS_VALUES)
    if unknown_status.any():
        raise DataAccessError("Tushare stock master contains unknown list_status values")
    unknown_type = ~frame["stockType"].isin(_KNOWN_A_STOCK_TYPE_VALUES)
    if unknown_type.any():
        raise DataAccessError("Tushare stock master contains unknown stock_type values")
    if frame.duplicated("symbol").any():
        raise DataAccessError("Tushare stock master has duplicate symbols")
    delisted = frame["listStatus"].isin(_DELISTED_LIST_STATUS_VALUES)
    if (delisted & frame["delistDate"].isna()).any():
        raise DataAccessError("Tushare stock master has delisted rows without delist_date")
    active = frame["listStatus"].isin(_ACTIVE_LIST_STATUS_VALUES)
    if (active & frame["delistDate"].notna()).any():
        raise DataAccessError("Tushare stock master has active rows with delist_date")
    if (frame["delistDate"].notna() & (frame["delistDate"] < frame["listDate"])).any():
        raise DataAccessError("Tushare stock master has delist dates before list dates")
    return frame[["symbol", "listDate", "delistDate", "listStatus", "stockType"]].sort_values("symbol").reset_index(drop=True)


def normalize_tushare_st_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize positive ST observations; absence remains unknown."""

    _require_columns(raw, ("ts_code", "trade_date"), "Tushare stock_st")
    frame = raw.copy()
    frame["symbol"] = frame["ts_code"].astype(str).str.strip().str.upper()
    if frame["symbol"].eq("").any() or frame["symbol"].isin(_MISSING_TEXT_TOKENS).any():
        raise DataAccessError("Tushare stock_st contains blank symbols")
    frame["date"] = _date_series(frame, "trade_date", "Tushare stock_st")
    if frame.duplicated(["symbol", "date"]).any():
        raise DataAccessError("Tushare stock_st has duplicate symbol-date keys")
    return frame[["symbol", "date"]].assign(is_st=True).sort_values(["symbol", "date"]).reset_index(drop=True)


def normalize_tushare_suspend_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize positive suspension observations; absence remains unknown."""

    _require_columns(raw, ("ts_code", "trade_date"), "Tushare suspend_d")
    frame = raw.copy()
    frame["symbol"] = frame["ts_code"].astype(str).str.strip().str.upper()
    if frame["symbol"].eq("").any() or frame["symbol"].isin(_MISSING_TEXT_TOKENS).any():
        raise DataAccessError("Tushare suspend_d contains blank symbols")
    frame["date"] = _date_series(frame, "trade_date", "Tushare suspend_d")
    if "suspend_type" in frame:
        frame["suspend_type"] = frame["suspend_type"].astype(str).str.strip().str.upper()
        frame = frame[frame["suspend_type"].isin({"S", "SUSPEND", "停牌"})].copy()
    if frame.duplicated(["symbol", "date"]).any():
        raise DataAccessError("Tushare suspend_d has duplicate symbol-date keys")
    return frame[["symbol", "date"]].assign(is_suspended=True).sort_values(["symbol", "date"]).reset_index(drop=True)


def _to_bool(value: Any) -> bool | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "是"}:
        return True
    if text in {"0", "false", "no", "n", "否"}:
        return False
    return None


__all__ = [
    "DataAccessError",
    "ProviderCapability",
    "STAGE2_DATASET_ROLES",
    "STAGE2_REQUIRED_FIELDS",
    "STAGE2_TARGETS",
    "PROVIDER_CAPABILITIES",
    "provider_capability_matrix",
    "assess_provider_capability",
    "summarize_csv_metadata",
    "audit_stage2_field_contract",
    "validate_rights_attestation",
    "normalize_tushare_daily_frame",
    "normalize_tushare_trade_calendar_frame",
    "normalize_tushare_disclosure_frame",
    "normalize_tushare_stock_master_frame",
    "normalize_tushare_st_frame",
    "normalize_tushare_suspend_frame",
]


def _cli() -> int:
    parser = argparse.ArgumentParser(
        description="Outcome-blind Stage-2 data-access metadata audit"
    )
    parser.add_argument("--quotes", required=True)
    parser.add_argument("--stock-master", required=True)
    parser.add_argument("--fundamentals", required=True)
    parser.add_argument("--official-calendar", required=True)
    parser.add_argument("--rights-attestation")
    parser.add_argument("--output")
    parser.add_argument(
        "--fail-on-blocked",
        action="store_true",
        help="return exit code 2 when metadata/rights gates are blocked",
    )
    args = parser.parse_args()
    paths = {
        "quotes": args.quotes,
        "stock_master": args.stock_master,
        "fundamentals": args.fundamentals,
        "official_calendar": args.official_calendar,
    }
    metadata = {role: summarize_csv_metadata(path, role) for role, path in paths.items()}
    rights = None
    if args.rights_attestation:
        rights = json.loads(_safe_file(args.rights_attestation).read_text(encoding="utf-8"))
    result = audit_stage2_field_contract(metadata, rights_attestation=rights)
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 2 if args.fail_on_blocked and result["status"] == "blocked" else 0


if __name__ == "__main__":  # pragma: no cover - exercised through subprocess in release checks
    raise SystemExit(_cli())
