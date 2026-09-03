"""Outcome-blind Stage-2 data-access contracts and metadata adapters.

This module deliberately stops at the *data-access boundary*.  It can inspect
CSV headers, dates, keys, non-null rates, and field informativeness, but it
never computes a factor, return, rank, IC, portfolio result, or variant
ordering.  The functions are intended for a pre-registration coverage probe
and for preparing a licensed-data review packet.  They do not grant a licence
and they do not fetch data from a provider.

The source adapters accept provider response frames supplied by the caller.
Network clients and credentials stay outside this repository's public API.
The CLI's exact hashes, sizes, counts, and date extrema are private
rights-controlled evidence. It requires a new output outside every Git
worktree; a separately reviewed redacted public export is not implemented.
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

from .public_receipt_privacy import credential_like_public_key
from .private_artifact_paths import (
    PrivateArtifactPathError,
    require_new_private_file_target,
    write_private_bytes_atomic_exclusive,
)


class DataAccessError(ValueError):
    """Raised when a source response cannot be adapted without guessing."""


STAGE2_DATASET_ROLES = ("quotes", "stock_master", "fundamentals", "official_calendar")

STAGE2_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "quotes": (
        "date",
        "symbol",
        "close_raw",
        "adjustment_factor",
        "close",
        "price_adjustment_method",
        "price_adjustment_convention",
        "close_observation_type",
        "amount",
        "amount_unit",
        "is_st",
        "is_suspended",
    ),
    "stock_master": ("symbol", "listDate", "delistDate", "listStatus", "stockType"),
    "fundamentals": ("symbol", "roeDiluted", "publishDate", "reportPeriodEnd"),
    "official_calendar": ("date",),
}

STAGE2_PRICE_ADJUSTMENT_METHOD = (
    "close_equals_close_raw_times_adjustment_factor"
)
STAGE2_PRICE_ADJUSTMENT_CONVENTION = (
    "provider_cumulative_backward_adjusted_hfq_no_rebasing"
)

STAGE2_TARGETS = {
    "quote_start_month": "2009-01",
    "quote_end_month": "2023-01",
    "calendar_start_month": "2009-01",
    "calendar_end_month": "2023-01",
    "analysis_start": "2010-01-01",
    "analysis_end": "2022-12-31",
    "minimum_symbols_per_month": 1000,
    "minimum_sessions_per_month": 15,
    "minimum_publish_date_rate": 0.95,
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
# Provider-specific aliases are normalized at the Tushare adapter boundary so
# downstream canonical CSV never depends on a provider code.  ``P``/paused is
# intentionally absent: the two-state Stage-2 lifecycle contract cannot infer
# whether a transitional record should be active or delisted.
_TUSHARE_LIST_STATUS_TO_CANONICAL = {
    "L": "ACTIVE",
    "LISTED": "ACTIVE",
    "ACTIVE": "ACTIVE",
    "A": "ACTIVE",
    "正常上市": "ACTIVE",
    "D": "DELISTED",
    "DELISTED": "DELISTED",
    "TERMINATED": "DELISTED",
    "退市": "DELISTED",
    "终止上市": "DELISTED",
}
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
_TUSHARE_UNAMBIGUOUS_A_STOCK_TYPE_VALUES = frozenset({"A", "A股"})
_CANONICAL_A_SHARE_STOCK_TYPE = "A股"
_MISSING_TEXT_TOKENS = frozenset({"", "NONE", "NAN", "NAT", "NULL", "NA", "N/A", "<NA>"})
_CLOSE_OBSERVATION_TYPES = frozenset(
    {"traded_close", "suspension_valuation"}
)


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
            "trade_calendar_by_exchange_candidate",
            "security_master",
            "historical_security_list_from_2016_candidate",
            "st_history",
            "suspension_records_target_coverage_unverified",
            "report_publication_date",
            "financial_indicator",
        ),
        access_mode="token_and_points_or_entitlement",
        status="candidate_subject_to_documented_coverage_provenance_and_written_rights_review",
        limitations=(
            "daily and adjustment-factor responses must be joined and frozen before producing adjusted close",
            "daily.close multiplied by adj_factor is the documented hfq construction; this adapter does not produce qfq",
            "stock_basic is not by itself a historical point-in-time membership table; retain historical-list evidence",
            "bak_basic is documented from 2016 and cannot establish 2009-2015 membership by itself",
            "disclosure_date.actual_date is preferred over that endpoint's pre_date and ann_date, but first-publication semantics still require confirmation",
            "ST and suspension endpoints need a complete date-by-date extraction and non-degeneracy audit; suspend_d documentation does not promise full target coverage",
            "trade_cal exchange parameters do not establish authoritative exchange provenance or data-publication rights",
            "the service agreement describes a personal, non-transferable, non-commercial, revocable licence; no aggregate publication right is inferred",
        ),
        references=(
            "https://tushare.pro/document/2?doc_id=27",
            "https://tushare.pro/document/2?doc_id=28",
            "https://tushare.pro/document/2?doc_id=146",
            "https://tushare.pro/document/2?doc_id=25",
            "https://tushare.pro/document/2?doc_id=26",
            "https://tushare.pro/document/2?doc_id=79",
            "https://tushare.pro/document/2?doc_id=162",
            "https://tushare.pro/document/2?doc_id=214",
            "https://tushare.pro/document/2?doc_id=397",
            "https://tushare.pro/document/1?doc_id=262",
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
        references=("https://pypi.org/project/baostock/",),
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
            "https://www.sse.com.cn/market/publicdata/",
            "https://www.sse.com.cn/disclosure/dealinstruc/calendar/index.shtml",
            "https://english.sse.com.cn/start/trading/schedule/",
            "https://www.szse.cn/application/laws/",
            "https://www.cninfo.com.cn/",
            "https://www.cninfo.com.cn/new/commonUrl?url=data%2Fyuyuepilu",
        ),
    ),
    ProviderCapability(
        provider_id="resset_institutional",
        datasets=("contractual_capabilities_to_be_verified",),
        access_mode="institutional_contract",
        status="candidate_primary_not_verified_capability_or_entitlement",
        limitations=(
            "public terms permit licensed querying, extraction, and research use with source attribution, but restrict unauthorized copying, dissemination, network display, and account sharing",
            "public product materials do not prove that this study holds an institutional entitlement or that the subscribed product contains every required field and target date",
            "2009-2023 coverage, field semantics, source provenance, local retention, aggregate publication, and controlled reviewer-rerun rights require written contractual confirmation",
            "no public product description is treated as evidence of revision/vintage history or first-release accounting values",
        ),
        references=(
            "https://db.resset.com/db/main/termofuseIn_en.jsp",
            "https://manual.resset.com/RESSETDB4.0.pdf",
        ),
    ),
    ProviderCapability(
        provider_id="licensed_vendor_wind_csmar_choice_or_equivalent",
        datasets=("contractual_capabilities_to_be_verified",),
        access_mode="institutional_contract",
        status="preferred_procurement_route_not_verified_capability",
        limitations=(
            "vendor names are alternatives, not a claim that any contract is currently held or that a named product includes the required fields",
            "public product pages describe broad databases or terminals but do not establish table-level field semantics, complete 2009-2023 delivery, exchange-source provenance, or this study's entitlement",
            "the actual institutional contract and field dictionary must identify historical coverage, point-in-time fields, adjusted-price construction, local retention, aggregate publication, and controlled reviewer-rerun rights",
            "a vendor's current snapshot cannot be relabelled as revision/vintage history without versioned values and as-of timestamps",
        ),
        references=(
            "https://www.wind.com.cn/portal/zh/WFT/index.html",
            "https://www.csmar.com/channels/31.html",
            "https://choice.eastmoney.com/terminal",
        ),
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
        for field in (
            "is_st",
            "is_suspended",
            "close_observation_type",
            "price_adjustment_method",
            "price_adjustment_convention",
            "amount_unit",
            "listStatus",
            "stockType",
        )
        if field in fields
    }
    invalid_boolean_value_count: dict[str, int] = {
        field: 0 for field in ("is_st", "is_suspended") if field in fields
    }
    invalid_close_observation_type_count = 0
    close_observation_suspension_mismatch_count = 0
    invalid_price_adjustment_method_count = 0
    invalid_price_adjustment_convention_count = 0
    price_adjustment_formula_mismatch_count = 0
    invalid_amount_unit_count = 0
    numeric_value_issue_counts: dict[str, int] = {}
    if role == "quotes":
        numeric_value_issue_counts = {
            "close_raw_non_numeric_count": 0,
            "close_raw_non_finite_count": 0,
            "close_raw_non_positive_count": 0,
            "adjustment_factor_non_numeric_count": 0,
            "adjustment_factor_non_finite_count": 0,
            "adjustment_factor_non_positive_count": 0,
            "close_non_numeric_count": 0,
            "close_non_finite_count": 0,
            "close_non_positive_count": 0,
            "amount_non_numeric_count": 0,
            "amount_non_finite_count": 0,
            "amount_negative_count": 0,
        }
    elif role == "fundamentals":
        numeric_value_issue_counts = {
            "roeDiluted_non_numeric_count": 0,
            "roeDiluted_non_finite_count": 0,
        }
    invalid_date_value_counts: dict[str, int] = {}
    if role == "fundamentals":
        invalid_date_value_counts = {
            "publishDate": 0,
            "reportPeriodEnd": 0,
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
                if field == "close_observation_type":
                    raw_value = str(row[field])
                    canonical_value = raw_value.strip()
                    if (
                        raw_value == canonical_value
                        and canonical_value in _CLOSE_OBSERVATION_TYPES
                    ):
                        distinct[field].add(canonical_value)
                    continue
                normalized = _distinct_normalized((row[field],))
                distinct[field].update(normalized or (str(row[field]).strip().lower(),))
                if field in invalid_boolean_value_count and normalized and normalized[0] not in {"true", "false"}:
                    invalid_boolean_value_count[field] += 1
        if role == "quotes":
            if str(row.get("price_adjustment_method") or "") != (
                STAGE2_PRICE_ADJUSTMENT_METHOD
            ):
                invalid_price_adjustment_method_count += 1
            if str(row.get("price_adjustment_convention") or "") != (
                STAGE2_PRICE_ADJUSTMENT_CONVENTION
            ):
                invalid_price_adjustment_convention_count += 1
            raw_amount_unit = str(row.get("amount_unit") or "")
            if raw_amount_unit != "CNY":
                invalid_amount_unit_count += 1
            raw_observation_type = str(
                row.get("close_observation_type") or ""
            )
            observation_type = raw_observation_type.strip()
            if observation_type and (
                raw_observation_type != observation_type
                or observation_type not in _CLOSE_OBSERVATION_TYPES
            ):
                invalid_close_observation_type_count += 1
            suspended_tokens = _distinct_normalized(
                (row.get("is_suspended"),)
            )
            if (
                observation_type in _CLOSE_OBSERVATION_TYPES
                and suspended_tokens
                and suspended_tokens[0] in {"true", "false"}
            ):
                expected_type = (
                    "suspension_valuation"
                    if suspended_tokens[0] == "true"
                    else "traded_close"
                )
                if observation_type != expected_type:
                    close_observation_suspension_mismatch_count += 1
            parsed_quote_values: dict[str, float] = {}
            for field in ("close_raw", "adjustment_factor", "close", "amount"):
                raw_numeric_value = row.get(field)
                if not _nonblank(raw_numeric_value):
                    # Required-field non-null rates handle blank values.  The
                    # counters below distinguish malformed nonblank values
                    # without retaining or exposing the values themselves.
                    continue
                try:
                    numeric_value = float(str(raw_numeric_value).strip())
                except (TypeError, ValueError):
                    numeric_value_issue_counts[f"{field}_non_numeric_count"] += 1
                    continue
                if not math.isfinite(numeric_value):
                    numeric_value_issue_counts[f"{field}_non_finite_count"] += 1
                    continue
                parsed_quote_values[field] = numeric_value
                if (
                    field in {"close_raw", "adjustment_factor", "close"}
                    and numeric_value <= 0
                ):
                    numeric_value_issue_counts[f"{field}_non_positive_count"] += 1
                elif field == "amount" and numeric_value < 0:
                    numeric_value_issue_counts["amount_negative_count"] += 1
            if {"close_raw", "adjustment_factor", "close"}.issubset(
                parsed_quote_values
            ):
                expected_close = (
                    parsed_quote_values["close_raw"]
                    * parsed_quote_values["adjustment_factor"]
                )
                if not math.isclose(
                    parsed_quote_values["close"],
                    expected_close,
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                ):
                    price_adjustment_formula_mismatch_count += 1
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
            raw_publish = row.get("publishDate")
            raw_report = row.get("reportPeriodEnd")
            publish = _parse_date(raw_publish)
            report = _parse_date(raw_report)
            row_date = report
            for field, raw_value, parsed_value in (
                ("publishDate", raw_publish, publish),
                ("reportPeriodEnd", raw_report, report),
            ):
                if _nonblank(raw_value) and parsed_value is None:
                    invalid_date_value_counts[field] += 1
                    invalid_date_count += 1
                    # For these required date fields, coverage means a usable
                    # date rather than merely a nonblank string.  Other fields'
                    # non-null rates retain their existing literal semantics.
                    non_null[field] -= 1
            raw_roe = row.get("roeDiluted")
            if _nonblank(raw_roe):
                try:
                    roe_value = float(str(raw_roe).strip())
                except (TypeError, ValueError):
                    numeric_value_issue_counts[
                        "roeDiluted_non_numeric_count"
                    ] += 1
                else:
                    if not math.isfinite(roe_value):
                        numeric_value_issue_counts[
                            "roeDiluted_non_finite_count"
                        ] += 1
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
        elif role != "fundamentals" and any(
            _nonblank(row.get(field))
            for field in ("date", "listDate", "reportPeriodEnd")
        ):
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
        "invalid_close_observation_type_count": (
            invalid_close_observation_type_count
        ),
        "close_observation_suspension_mismatch_count": (
            close_observation_suspension_mismatch_count
        ),
        "invalid_price_adjustment_method_count": (
            invalid_price_adjustment_method_count
        ),
        "invalid_price_adjustment_convention_count": (
            invalid_price_adjustment_convention_count
        ),
        "price_adjustment_formula_mismatch_count": (
            price_adjustment_formula_mismatch_count
        ),
        "invalid_amount_unit_count": invalid_amount_unit_count,
        "numeric_value_issue_counts": numeric_value_issue_counts,
        "invalid_date_value_counts": invalid_date_value_counts,
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
    # A min/max metadata scan cannot know the exchange's exact first and last
    # required sessions.  Accept observations anywhere in the boundary months;
    # the authoritative coverage audit binds quotes to the official calendar
    # and checks the exact session geometry.
    if _range_month_start_after(
        quote_range, STAGE2_TARGETS["quote_start_month"]
    ):
        issues.append("QUOTE_WARMUP_NOT_COVERED")
    if _range_month_end_before(
        quote_range, STAGE2_TARGETS["quote_end_month"]
    ):
        issues.append("QUOTE_ENDPOINT_NOT_COVERED")
    numeric_value_issue_counts = quotes.get("numeric_value_issue_counts", {})
    numeric_count_gates = (
        ("close_raw_non_numeric_count", "QUOTE_CLOSE_RAW_NON_NUMERIC"),
        ("close_raw_non_finite_count", "QUOTE_CLOSE_RAW_NON_FINITE"),
        ("close_raw_non_positive_count", "QUOTE_CLOSE_RAW_NON_POSITIVE"),
        (
            "adjustment_factor_non_numeric_count",
            "QUOTE_ADJUSTMENT_FACTOR_NON_NUMERIC",
        ),
        (
            "adjustment_factor_non_finite_count",
            "QUOTE_ADJUSTMENT_FACTOR_NON_FINITE",
        ),
        (
            "adjustment_factor_non_positive_count",
            "QUOTE_ADJUSTMENT_FACTOR_NON_POSITIVE",
        ),
        ("close_non_numeric_count", "QUOTE_CLOSE_NON_NUMERIC"),
        ("close_non_finite_count", "QUOTE_CLOSE_NON_FINITE"),
        ("close_non_positive_count", "QUOTE_CLOSE_NON_POSITIVE"),
        ("amount_non_numeric_count", "QUOTE_AMOUNT_NON_NUMERIC"),
        ("amount_non_finite_count", "QUOTE_AMOUNT_NON_FINITE"),
        ("amount_negative_count", "QUOTE_AMOUNT_NEGATIVE"),
    )
    for count_key, issue_code in numeric_count_gates:
        count = (
            _metadata_count(numeric_value_issue_counts, count_key)
            if isinstance(numeric_value_issue_counts, Mapping)
            else None
        )
        if count is None:
            issues.append(f"INVALID_QUOTE_NUMERIC_COUNT:{count_key}")
        elif count > 0:
            issues.append(issue_code)
    fundamentals_value = metadata_by_role.get("fundamentals", {})
    fundamentals = fundamentals_value if isinstance(fundamentals_value, Mapping) else {}
    fundamental_numeric_value_issue_counts = fundamentals.get(
        "numeric_value_issue_counts", {}
    )
    fundamental_numeric_count_gates = (
        ("roeDiluted_non_numeric_count", "FUNDAMENTAL_ROE_DILUTED_NON_NUMERIC"),
        ("roeDiluted_non_finite_count", "FUNDAMENTAL_ROE_DILUTED_NON_FINITE"),
    )
    for count_key, issue_code in fundamental_numeric_count_gates:
        count = (
            _metadata_count(fundamental_numeric_value_issue_counts, count_key)
            if isinstance(fundamental_numeric_value_issue_counts, Mapping)
            else None
        )
        if count is None:
            issues.append(f"INVALID_FUNDAMENTAL_NUMERIC_COUNT:{count_key}")
        elif count > 0:
            issues.append(issue_code)
    fundamental_date_value_counts = fundamentals.get(
        "invalid_date_value_counts", {}
    )
    fundamental_date_count_gates = (
        ("publishDate", "FUNDAMENTAL_PUBLISH_DATE_INVALID"),
        ("reportPeriodEnd", "FUNDAMENTAL_REPORT_PERIOD_END_INVALID"),
    )
    for field, issue_code in fundamental_date_count_gates:
        count = (
            _metadata_count(fundamental_date_value_counts, field)
            if isinstance(fundamental_date_value_counts, Mapping)
            else None
        )
        if count is None:
            issues.append(f"INVALID_FUNDAMENTAL_DATE_COUNT:{field}")
        elif count > 0:
            issues.append(issue_code)
    fundamental_publish_range = _metadata_range(fundamentals, "publishDate")
    fundamental_report_range = _metadata_range(fundamentals, "reportPeriodEnd")
    if not _range_is_valid(fundamental_publish_range):
        issues.append("FUNDAMENTAL_PUBLICATION_RANGE_INVALID")
    if not _range_is_valid(fundamental_report_range):
        issues.append("FUNDAMENTAL_REPORT_RANGE_INVALID")
    # Reports and disclosures are events, not daily observations.  Their first
    # valid dates need not coincide with the first day of the warm-up interval
    # (for example, a first reportPeriodEnd of 2009-03-31 is legitimate).
    # Eligible-symbol/month history and staleness are therefore checked only
    # by the authoritative coverage audit.  This metadata layer retains range
    # validity without requiring an event on either exact interval boundary.
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
    distinct_values = quotes.get("distinct_values", {})
    raw_observation_types = (
        distinct_values.get("close_observation_type", [])
        if isinstance(distinct_values, Mapping)
        else []
    )
    observation_types = (
        {str(value).strip() for value in raw_observation_types}
        if isinstance(raw_observation_types, (list, tuple, set))
        else set()
    )
    if observation_types != _CLOSE_OBSERVATION_TYPES:
        issues.append("DEGENERATE_FIELD:close_observation_type")
    invalid_observation_type_count = _metadata_count(
        quotes, "invalid_close_observation_type_count"
    )
    if invalid_observation_type_count is None:
        issues.append("INVALID_CLOSE_OBSERVATION_TYPE_COUNT")
    elif invalid_observation_type_count > 0:
        issues.append("INVALID_CLOSE_OBSERVATION_TYPE")
    observation_mismatch_count = _metadata_count(
        quotes, "close_observation_suspension_mismatch_count"
    )
    if observation_mismatch_count is None:
        issues.append("INVALID_CLOSE_OBSERVATION_SUSPENSION_MISMATCH_COUNT")
    elif observation_mismatch_count > 0:
        issues.append("CLOSE_OBSERVATION_SUSPENSION_MISMATCH")
    invalid_adjustment_method_count = _metadata_count(
        quotes, "invalid_price_adjustment_method_count"
    )
    if invalid_adjustment_method_count is None:
        issues.append("INVALID_PRICE_ADJUSTMENT_METHOD_COUNT")
    elif invalid_adjustment_method_count > 0:
        issues.append("QUOTE_PRICE_ADJUSTMENT_METHOD_INVALID")
    invalid_adjustment_convention_count = _metadata_count(
        quotes, "invalid_price_adjustment_convention_count"
    )
    if invalid_adjustment_convention_count is None:
        issues.append("INVALID_PRICE_ADJUSTMENT_CONVENTION_COUNT")
    elif invalid_adjustment_convention_count > 0:
        issues.append("QUOTE_PRICE_ADJUSTMENT_CONVENTION_INVALID")
    formula_mismatch_count = _metadata_count(
        quotes, "price_adjustment_formula_mismatch_count"
    )
    if formula_mismatch_count is None:
        issues.append("INVALID_PRICE_ADJUSTMENT_FORMULA_MISMATCH_COUNT")
    elif formula_mismatch_count > 0:
        issues.append("QUOTE_PRICE_ADJUSTMENT_FORMULA_MISMATCH")
    invalid_amount_unit_count = _metadata_count(
        quotes, "invalid_amount_unit_count"
    )
    if invalid_amount_unit_count is None:
        issues.append("INVALID_AMOUNT_UNIT_COUNT")
    elif invalid_amount_unit_count > 0:
        issues.append("QUOTE_AMOUNT_UNIT_NOT_EXACT_CNY")

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
        "quotes": (
            "date",
            "symbol",
            "close_raw",
            "adjustment_factor",
            "close",
            "price_adjustment_method",
            "price_adjustment_convention",
            "close_observation_type",
            "amount",
            "amount_unit",
            "is_st",
            "is_suspended",
        ),
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
                continue
            minimum_rate = (
                float(STAGE2_TARGETS["minimum_publish_date_rate"])
                if role == "fundamentals" and field == "publishDate"
                else 1.0
            )
            if numeric_rate < minimum_rate:
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
_RIGHTS_RESTRICTION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_RIGHTS_PERMISSION_FIELDS = frozenset(
    {
        "local_storage_permitted",
        "local_analysis_permitted",
        "aggregate_publication_permitted",
        "raw_redistribution_permitted",
        "hash_publication_permitted",
        "controlled_reviewer_rerun_permitted",
        "calendar_dates_publication_permitted",
        "source_identity_publication_permitted",
        "field_mapping_citation_permitted",
    }
)

STAGE2_RIGHTS_ATTESTATION_SCHEMA_VERSION = "stage2_data_rights_attestation_v2"
STAGE2_PUBLIC_DATASET_SOURCE_MAPPINGS_SCHEMA_VERSION = (
    "stage2_public_dataset_source_mappings_v1"
)
_RIGHTS_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "study_id",
        "status",
        "attested_at",
        "attestor",
        "attestor_role",
        "contract_reference",
        "contract_effective_at",
        "contract_expiry_at",
        "contract_has_no_expiry_confirmed",
        "post_expiry_research_publication_and_controlled_review_rights_survive",
        "post_expiry_survival_evidence_sha256",
        "contract_evidence_sha256",
        "datasets",
        "private_endpoint_reason_ledger",
        "public_outputs",
        "evidence_index",
        "signature",
    }
)
_RIGHTS_DATASET_FIELDS = frozenset(
    {
        "source_reference",
        "license_or_contract_scope",
        "terms_evidence_sha256",
        "local_storage_permitted",
        "local_analysis_permitted",
        "aggregate_publication_permitted",
        "raw_redistribution_permitted",
        "hash_publication_permitted",
        "controlled_reviewer_rerun_permitted",
        "source_identity_publication_permitted",
        "field_mapping_citation_permitted",
        "authorized_public_projection",
        "authorized_public_projection_sha256",
        "restrictions",
        "conditional_permission_reviews",
    }
)
_RIGHTS_RESTRICTION_FIELDS = frozenset(
    {"restriction_id", "permission", "description"}
)
_RIGHTS_CONDITIONAL_REVIEW_FIELDS = frozenset(
    {
        "restriction_id",
        "permission",
        "conditions_satisfied",
        "condition_evidence_sha256",
        "reviewed_at",
    }
)
_RIGHTS_PRIVATE_LEDGER_FIELDS = frozenset(
    {
        "retention_permitted",
        "hash_binding_permitted",
        "row_redistribution_permitted",
        "terms_evidence_sha256",
    }
)
_RIGHTS_PUBLIC_OUTPUT_FIELDS = frozenset(
    {
        "aggregate_coverage_permitted",
        "aggregate_missingness_permitted",
        "aggregate_reason_counts_permitted",
        "cryptographic_hashes_permitted",
        "exact_official_calendar_dates_permitted",
        "raw_rows_permitted",
    }
)
_RIGHTS_EVIDENCE_INDEX_FIELDS = frozenset({"kind", "reference", "sha256"})
_RIGHTS_SIGNATURE_FIELDS = frozenset(
    {
        "type",
        "evidence_sha256",
        "signer_identity",
        "verification_uri",
        "trust_boundary",
    }
)
_PUBLIC_SOURCE_PROJECTION_FIELDS = frozenset(
    {"dataset_role", "source_name", "field_mapping"}
)
_GENERIC_MAPPING_ASSERTIONS = frozenset(
    {
        "approved",
        "compliant",
        "confirmed",
        "covered",
        "licensed",
        "ok",
        "permitted",
        "true",
        "yes",
    }
)


def _canonical_json_bytes(value: Any) -> bytes:
    """Serialize a JSON value for an exact, order-independent hash binding."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def stage2_public_source_projection_sha256(projection: Mapping[str, Any]) -> str:
    """Hash one exact public source-identity and canonical-field projection."""

    return hashlib.sha256(_canonical_json_bytes(projection)).hexdigest()


def _validate_public_source_projection(
    projection: Any,
    *,
    role: str,
    prefix: str,
    issues: list[str],
) -> None:
    if not isinstance(projection, Mapping):
        issues.append(f"{prefix}:NOT_OBJECT")
        return
    if set(projection) != _PUBLIC_SOURCE_PROJECTION_FIELDS:
        issues.append(f"{prefix}:SCHEMA_FIELDS")
    if projection.get("dataset_role") != role:
        issues.append(f"{prefix}:DATASET_ROLE_MISMATCH")
    source_name = projection.get("source_name")
    if not isinstance(source_name, str) or not source_name.strip():
        issues.append(f"{prefix}:SOURCE_NAME_MISSING")
    elif source_name.strip().casefold() in _GENERIC_MAPPING_ASSERTIONS:
        issues.append(f"{prefix}:SOURCE_NAME_GENERIC")
    field_mapping = projection.get("field_mapping")
    if not isinstance(field_mapping, Mapping):
        issues.append(f"{prefix}:FIELD_MAPPING_NOT_OBJECT")
        return
    if set(field_mapping) != set(STAGE2_REQUIRED_FIELDS[role]):
        issues.append(f"{prefix}:FIELD_MAPPING_FIELDS")
    for canonical_field in STAGE2_REQUIRED_FIELDS[role]:
        provider_field = field_mapping.get(canonical_field)
        if not isinstance(provider_field, str) or not provider_field.strip():
            issues.append(f"{prefix}:FIELD_MAPPING_MISSING:{canonical_field}")
            continue
        if provider_field.strip().casefold() in _GENERIC_MAPPING_ASSERTIONS:
            issues.append(f"{prefix}:FIELD_MAPPING_GENERIC:{canonical_field}")


def validate_stage2_dataset_source_mappings(mappings: Any) -> dict[str, Any]:
    """Validate the exact four-role projection intended for public citation."""

    issues: list[str] = []
    if not isinstance(mappings, Mapping):
        return {
            "schema_version": STAGE2_PUBLIC_DATASET_SOURCE_MAPPINGS_SCHEMA_VERSION,
            "status": "invalid",
            "issues": ["SOURCE_MAPPINGS_NOT_OBJECT"],
        }
    if set(mappings) != {"schema_version", "datasets"}:
        issues.append("SOURCE_MAPPINGS_SCHEMA_FIELDS")
    if mappings.get("schema_version") != (
        STAGE2_PUBLIC_DATASET_SOURCE_MAPPINGS_SCHEMA_VERSION
    ):
        issues.append("SOURCE_MAPPINGS_SCHEMA_VERSION")
    datasets = mappings.get("datasets")
    if not isinstance(datasets, Mapping):
        issues.append("SOURCE_MAPPINGS_DATASETS_NOT_OBJECT")
        datasets = {}
    if set(datasets) != set(STAGE2_DATASET_ROLES):
        issues.append("SOURCE_MAPPINGS_DATASET_ROLES")
    for role in STAGE2_DATASET_ROLES:
        _validate_public_source_projection(
            datasets.get(role),
            role=role,
            prefix=f"SOURCE_MAPPING:{role}",
            issues=issues,
        )
    return {
        "schema_version": STAGE2_PUBLIC_DATASET_SOURCE_MAPPINGS_SCHEMA_VERSION,
        "status": "valid" if not issues else "invalid",
        "issues": sorted(dict.fromkeys(issues)),
    }


def validate_rights_attestation(
    attestation: Mapping[str, Any] | None,
    *,
    required_datasets: Iterable[str] = STAGE2_DATASET_ROLES,
    data_declaration: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a rights packet while keeping all legal decisions human-bound."""

    issues: list[str] = []
    if not isinstance(attestation, Mapping):
        return {"schema_version": STAGE2_RIGHTS_ATTESTATION_SCHEMA_VERSION, "status": "missing", "issues": ["ATTESTATION_MISSING"]}
    # A credential-bearing packet is rejected before any structural detail is
    # reported.  This keeps the validation response itself from becoming a
    # side channel for the location of a secret-like key.
    if _contains_secret_like_value(attestation):
        return {
            "schema_version": STAGE2_RIGHTS_ATTESTATION_SCHEMA_VERSION,
            "status": "invalid",
            "issues": ["SECRET_LIKE_VALUE_PRESENT"],
            "authorization_granted": False,
        }
    if set(attestation) != _RIGHTS_TOP_LEVEL_FIELDS:
        issues.append("ATTESTATION_SCHEMA_FIELDS")
    if attestation.get("schema_version") != STAGE2_RIGHTS_ATTESTATION_SCHEMA_VERSION:
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
    no_expiry_confirmed = attestation.get("contract_has_no_expiry_confirmed")
    surviving_use = attestation.get(
        "post_expiry_research_publication_and_controlled_review_rights_survive"
    )
    surviving_use_hash = attestation.get(
        "post_expiry_survival_evidence_sha256"
    )
    if not isinstance(no_expiry_confirmed, bool):
        issues.append("CONTRACT_NO_EXPIRY_CONFIRMATION_BOOLEAN_REQUIRED")
    if not isinstance(surviving_use, bool):
        issues.append("POST_EXPIRY_SURVIVING_USE_BOOLEAN_REQUIRED")
    if expiry_value in (None, ""):
        if no_expiry_confirmed is not True:
            issues.append("CONTRACT_NO_EXPIRY_NOT_CONFIRMED")
        if surviving_use is not False or surviving_use_hash not in (None, ""):
            issues.append("NO_EXPIRY_SURVIVING_USE_FIELDS_INVALID")
    else:
        if no_expiry_confirmed is not False:
            issues.append("FINITE_EXPIRY_MUST_NOT_CLAIM_NO_EXPIRY")
        if surviving_use is not True:
            issues.append("POST_EXPIRY_SURVIVING_USE_NOT_CONFIRMED")
        if _SHA256_RE.match(str(surviving_use_hash or "")) is None:
            issues.append("POST_EXPIRY_SURVIVAL_EVIDENCE_HASH_INVALID")
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
    required_roles = tuple(required_datasets)
    if set(required_roles) != set(STAGE2_DATASET_ROLES) or len(required_roles) != len(
        STAGE2_DATASET_ROLES
    ):
        issues.append("REQUIRED_DATASET_ROLES_MUST_BE_EXACT_STAGE2_SET")
        required_roles = STAGE2_DATASET_ROLES
    datasets = attestation.get("datasets")
    if not isinstance(datasets, Mapping):
        issues.append("DATASETS_NOT_OBJECT")
        datasets = {}
    if set(datasets) != set(required_roles):
        issues.append("DATASET_ROLES_NOT_EXACT")
    declaration_mappings: Any = None
    if data_declaration is not None:
        if not isinstance(data_declaration, Mapping):
            issues.append("DATA_DECLARATION_NOT_OBJECT")
        else:
            declaration_mappings = data_declaration.get("dataset_source_mappings")
            declaration_mapping_validation = validate_stage2_dataset_source_mappings(
                declaration_mappings
            )
            issues.extend(
                f"DATA_DECLARATION_{issue}"
                for issue in declaration_mapping_validation["issues"]
            )
    for role in required_roles:
        record = datasets.get(role)
        if not isinstance(record, Mapping):
            issues.append(f"DATASET_MISSING:{role}")
            continue
        expected_dataset_fields = set(_RIGHTS_DATASET_FIELDS)
        if role == "official_calendar":
            expected_dataset_fields.add("calendar_dates_publication_permitted")
        if set(record) != expected_dataset_fields:
            issues.append(f"{role}:SCHEMA_FIELDS")
        for field in (
            "source_reference",
            "license_or_contract_scope",
            "terms_evidence_sha256",
        ):
            if not str(record.get(field) or "").strip():
                issues.append(f"{role}:MISSING_{field}")
        if not _SHA256_RE.match(str(record.get("terms_evidence_sha256") or "")):
            issues.append(f"{role}:TERMS_HASH_INVALID")
        authorized_projection = record.get("authorized_public_projection")
        _validate_public_source_projection(
            authorized_projection,
            role=role,
            prefix=f"{role}:AUTHORIZED_PUBLIC_PROJECTION",
            issues=issues,
        )
        authorized_projection_sha256 = record.get(
            "authorized_public_projection_sha256"
        )
        if not _SHA256_RE.match(str(authorized_projection_sha256 or "")):
            issues.append(f"{role}:AUTHORIZED_PUBLIC_PROJECTION_HASH_INVALID")
        elif isinstance(authorized_projection, Mapping):
            try:
                computed_projection_sha256 = stage2_public_source_projection_sha256(
                    authorized_projection
                )
            except (TypeError, ValueError):
                issues.append(f"{role}:AUTHORIZED_PUBLIC_PROJECTION_NOT_JSON")
            else:
                if authorized_projection_sha256 != computed_projection_sha256:
                    issues.append(
                        f"{role}:AUTHORIZED_PUBLIC_PROJECTION_HASH_MISMATCH"
                    )
        if isinstance(declaration_mappings, Mapping):
            declaration_datasets = declaration_mappings.get("datasets")
            if isinstance(declaration_datasets, Mapping):
                declared_projection = declaration_datasets.get(role)
                try:
                    projections_match = _canonical_json_bytes(
                        authorized_projection
                    ) == _canonical_json_bytes(declared_projection)
                except (TypeError, ValueError):
                    projections_match = False
                if not projections_match:
                    issues.append(f"{role}:DATA_DECLARATION_PROJECTION_MISMATCH")
        for field in (
            "local_storage_permitted",
            "local_analysis_permitted",
            "aggregate_publication_permitted",
            "raw_redistribution_permitted",
            "hash_publication_permitted",
            "controlled_reviewer_rerun_permitted",
            "source_identity_publication_permitted",
            "field_mapping_citation_permitted",
        ):
            if not isinstance(record.get(field), bool):
                issues.append(f"{role}:BOOLEAN_REQUIRED:{field}")
        for field in (
            "local_storage_permitted",
            "local_analysis_permitted",
            "aggregate_publication_permitted",
            "hash_publication_permitted",
            "controlled_reviewer_rerun_permitted",
            "source_identity_publication_permitted",
            "field_mapping_citation_permitted",
        ):
            if record.get(field) is not True:
                issues.append(f"{role}:PERMISSION_NOT_GRANTED:{field}")
        if record.get("raw_redistribution_permitted") is not False:
            issues.append(f"{role}:RAW_REDISTRIBUTION_MUST_BE_FALSE")
        if not str(record.get("source_reference") or "").startswith(("https://", "http://", "urn:", "contract:")):
            issues.append(f"{role}:SOURCE_REFERENCE_NOT_TRACEABLE")
        if role == "official_calendar" and record.get("calendar_dates_publication_permitted") is not True:
            issues.append("official_calendar:CALENDAR_DATE_PUBLICATION_NOT_ATTESTED")
        restrictions = record.get("restrictions")
        if not isinstance(restrictions, list):
            issues.append(f"{role}:RESTRICTIONS_NOT_LIST")
            restrictions = []
        restrictions_by_id: dict[str, Mapping[str, Any]] = {}
        for index, restriction in enumerate(restrictions):
            prefix = f"{role}:RESTRICTION:{index}"
            if not isinstance(restriction, Mapping):
                issues.append(f"{prefix}:NOT_OBJECT")
                continue
            if set(restriction) != _RIGHTS_RESTRICTION_FIELDS:
                issues.append(f"{prefix}:SCHEMA_FIELDS")
            restriction_id = restriction.get("restriction_id")
            if not isinstance(restriction_id, str) or not _RIGHTS_RESTRICTION_ID_RE.match(
                restriction_id
            ):
                issues.append(f"{prefix}:ID_INVALID")
                continue
            if restriction_id in restrictions_by_id:
                issues.append(f"{prefix}:ID_DUPLICATE")
            else:
                restrictions_by_id[restriction_id] = restriction
            permission = restriction.get("permission")
            if (
                not isinstance(permission, str)
                or permission not in _RIGHTS_PERMISSION_FIELDS
                or permission not in record
            ):
                issues.append(f"{prefix}:PERMISSION_INVALID")
            elif record.get(permission) is not True:
                issues.append(f"{prefix}:PERMISSION_NOT_GRANTED")
            if not str(restriction.get("description") or "").strip():
                issues.append(f"{prefix}:DESCRIPTION_MISSING")
        conditional_reviews = record.get("conditional_permission_reviews")
        if not isinstance(conditional_reviews, list):
            issues.append(f"{role}:CONDITIONAL_REVIEWS_NOT_LIST")
            conditional_reviews = []
        reviewed_restriction_ids: set[str] = set()
        for index, conditional in enumerate(conditional_reviews):
            prefix = f"{role}:CONDITIONAL_REVIEW:{index}"
            if not isinstance(conditional, Mapping):
                issues.append(f"{prefix}:NOT_OBJECT")
                continue
            if set(conditional) != _RIGHTS_CONDITIONAL_REVIEW_FIELDS:
                issues.append(f"{prefix}:SCHEMA_FIELDS")
            restriction_id = conditional.get("restriction_id")
            restriction: Mapping[str, Any] | None = None
            if not isinstance(restriction_id, str) or not _RIGHTS_RESTRICTION_ID_RE.match(
                restriction_id
            ):
                issues.append(f"{prefix}:RESTRICTION_ID_INVALID")
            elif restriction_id not in restrictions_by_id:
                issues.append(f"{prefix}:RESTRICTION_ID_UNKNOWN")
            else:
                restriction = restrictions_by_id[restriction_id]
                if restriction_id in reviewed_restriction_ids:
                    issues.append(f"{prefix}:RESTRICTION_ID_DUPLICATE")
                reviewed_restriction_ids.add(restriction_id)
            permission = conditional.get("permission")
            if (
                not isinstance(permission, str)
                or permission not in _RIGHTS_PERMISSION_FIELDS
                or permission not in record
            ):
                issues.append(f"{prefix}:PERMISSION_INVALID")
            elif restriction is not None and permission != restriction.get("permission"):
                issues.append(f"{prefix}:PERMISSION_MISMATCH")
            if conditional.get("conditions_satisfied") is not True:
                issues.append(f"{prefix}:CONDITIONS_NOT_SATISFIED")
            if not _SHA256_RE.match(
                str(conditional.get("condition_evidence_sha256") or "")
            ):
                issues.append(f"{prefix}:EVIDENCE_HASH_INVALID")
            reviewed_text = str(conditional.get("reviewed_at") or "")
            if not _ISO_TIMESTAMP_RE.match(reviewed_text):
                issues.append(f"{prefix}:REVIEWED_AT_NOT_TIMEZONE_AWARE")
            else:
                try:
                    conditional_reviewed_at = datetime.fromisoformat(
                        reviewed_text.replace("Z", "+00:00")
                    )
                    if (
                        conditional_reviewed_at.tzinfo is None
                        or conditional_reviewed_at.utcoffset() is None
                    ):
                        issues.append(f"{prefix}:REVIEWED_AT_NOT_TIMEZONE_AWARE")
                    elif (
                        attested_at_for_order is not None
                        and conditional_reviewed_at > attested_at_for_order
                    ):
                        issues.append(f"{prefix}:REVIEW_AFTER_ATTESTATION")
                except ValueError:
                    issues.append(f"{prefix}:REVIEWED_AT_INVALID")
            if (
                isinstance(permission, str)
                and permission in record
                and record.get(permission) is not True
            ):
                issues.append(f"{prefix}:PERMISSION_NOT_GRANTED")
        for restriction_id in sorted(restrictions_by_id):
            if restriction_id not in reviewed_restriction_ids:
                issues.append(f"{role}:RESTRICTION_UNREVIEWED:{restriction_id}")

    private_ledger = attestation.get("private_endpoint_reason_ledger")
    if not isinstance(private_ledger, Mapping):
        issues.append("PRIVATE_LEDGER_NOT_OBJECT")
    else:
        if set(private_ledger) != _RIGHTS_PRIVATE_LEDGER_FIELDS:
            issues.append("PRIVATE_LEDGER_SCHEMA_FIELDS")
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
        if set(public_outputs) != _RIGHTS_PUBLIC_OUTPUT_FIELDS:
            issues.append("PUBLIC_OUTPUTS_SCHEMA_FIELDS")
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
        if set(signature) != _RIGHTS_SIGNATURE_FIELDS:
            issues.append("SIGNATURE_SCHEMA_FIELDS")
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
            if set(item) != _RIGHTS_EVIDENCE_INDEX_FIELDS:
                issues.append(f"EVIDENCE_INDEX_SCHEMA_FIELDS:{index}")
            if not str(item.get("kind") or "").strip():
                issues.append(f"EVIDENCE_INDEX_KIND_MISSING:{index}")
            reference = str(item.get("reference") or "")
            if not reference.startswith(("https://", "http://", "urn:", "contract:")):
                issues.append(f"EVIDENCE_INDEX_REFERENCE_INVALID:{index}")
            if _SHA256_RE.match(str(item.get("sha256") or "")) is None:
                issues.append(f"EVIDENCE_INDEX_HASH_INVALID:{index}")

    # Prevent accidental inclusion of credentials or raw secrets in the packet.
    # Inspect JSON keys recursively: searching serialized JSON text is brittle
    # because standard object keys are quoted before the colon.
    try:
        json.dumps(attestation, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        issues.append("ATTESTATION_NOT_JSON_SERIALIZABLE")
    return {
        "schema_version": STAGE2_RIGHTS_ATTESTATION_SCHEMA_VERSION,
        "status": "valid" if not issues else "invalid",
        "issues": sorted(dict.fromkeys(issues)),
        "authorization_granted": False,
    }


def _contains_secret_like_value(value: Any) -> bool:
    """Return true for a non-empty value under a credential-like JSON key.

    The check intentionally reports only a generic issue code; it never echoes
    the key path or candidate value into the public metadata audit.
    """

    pending = [value]
    seen_containers: set[int] = set()
    while pending:
        current = pending.pop()
        if isinstance(current, Mapping):
            identity = id(current)
            if identity in seen_containers:
                continue
            seen_containers.add(identity)
            for raw_key, item in current.items():
                if credential_like_public_key(
                    str(raw_key)
                ) and _nonempty_secret_value(item):
                    return True
                pending.append(item)
        elif isinstance(current, (list, tuple)):
            identity = id(current)
            if identity in seen_containers:
                continue
            seen_containers.add(identity)
            pending.extend(current)
    return False


def _nonempty_secret_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, (list, tuple, set, frozenset)):
        return bool(value)
    return True


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
    """Join Tushare daily and ``adj_factor`` rows into fixed ``hfq`` quotes.

    The join is exact on ``(ts_code, trade_date)``.  No forward/backward fill
    or inferred factor is allowed. The canonical ``close`` equals raw close
    multiplied by ``adj_factor``, the provider-documented back-adjusted
    (``hfq``) construction; this adapter does not produce ``qfq``. Amount is converted from thousand CNY and
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
            "price_adjustment_method": STAGE2_PRICE_ADJUSTMENT_METHOD,
            "price_adjustment_convention": STAGE2_PRICE_ADJUSTMENT_CONVENTION,
            "amount": joined["amount"] * 1000.0,
            "amount_unit": "CNY",
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
    """Create a candidate common SSE/SZSE calendar from provider rows.

    Missing exchange rows and SSE/SZSE disagreements fail closed.  The output
    contains dates only; the endpoint's exchange parameters do not prove
    authoritative exchange provenance. Source provenance and rights remain in
    the attestation and require separate verification.
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
    """Map provider-labelled ``actual_date`` values to the Stage-2 contract.

    ``pre_date`` and other scheduled dates are never substituted.  The label
    alone does not prove first-publication or legally reviewable ``actual``
    semantics; those require external source/rights confirmation.
    """

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
    provider_status = frame["list_status"].astype(str).str.strip().str.upper()
    frame["stockType"] = frame["stock_type"].astype(str).str.strip().str.upper()
    if provider_status.eq("").any() or provider_status.isin(_MISSING_TEXT_TOKENS).any():
        raise DataAccessError("Tushare stock master contains blank list_status values")
    if frame["stockType"].eq("").any() or frame["stockType"].isin(_MISSING_TEXT_TOKENS).any():
        raise DataAccessError("Tushare stock master contains blank stock_type values")
    unknown_status = ~provider_status.isin(_TUSHARE_LIST_STATUS_TO_CANONICAL)
    if unknown_status.any():
        raise DataAccessError("Tushare stock master contains unknown list_status values")
    # Only Tushare labels documented by this adapter as unambiguous A-share
    # identifiers are accepted.  Generic security labels such as EQUITY,
    # STOCK, SHARE, or 1 cannot distinguish A shares from other share classes.
    unknown_type = ~frame["stockType"].isin(
        _TUSHARE_UNAMBIGUOUS_A_STOCK_TYPE_VALUES
    )
    if unknown_type.any():
        raise DataAccessError("Tushare stock master contains unknown stock_type values")
    frame["stockType"] = _CANONICAL_A_SHARE_STOCK_TYPE
    if frame.duplicated("symbol").any():
        raise DataAccessError("Tushare stock master has duplicate symbols")
    delisted = provider_status.map(_TUSHARE_LIST_STATUS_TO_CANONICAL).eq("DELISTED")
    if (delisted & frame["delistDate"].isna()).any():
        raise DataAccessError("Tushare stock master has delisted rows without delist_date")
    active = provider_status.map(_TUSHARE_LIST_STATUS_TO_CANONICAL).eq("ACTIVE")
    if (active & frame["delistDate"].notna()).any():
        raise DataAccessError("Tushare stock master has active rows with delist_date")
    if (frame["delistDate"].notna() & (frame["delistDate"] < frame["listDate"])).any():
        raise DataAccessError("Tushare stock master has delist dates before list dates")
    frame["listStatus"] = provider_status.map(_TUSHARE_LIST_STATUS_TO_CANONICAL)
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
    "STAGE2_PRICE_ADJUSTMENT_METHOD",
    "STAGE2_PRICE_ADJUSTMENT_CONVENTION",
    "STAGE2_RIGHTS_ATTESTATION_SCHEMA_VERSION",
    "STAGE2_PUBLIC_DATASET_SOURCE_MAPPINGS_SCHEMA_VERSION",
    "PROVIDER_CAPABILITIES",
    "provider_capability_matrix",
    "assess_provider_capability",
    "summarize_csv_metadata",
    "audit_stage2_field_contract",
    "validate_rights_attestation",
    "validate_stage2_dataset_source_mappings",
    "stage2_public_source_projection_sha256",
    "normalize_tushare_daily_frame",
    "normalize_tushare_trade_calendar_frame",
    "normalize_tushare_disclosure_frame",
    "normalize_tushare_stock_master_frame",
    "normalize_tushare_st_frame",
    "normalize_tushare_suspend_frame",
]


def _cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Outcome-blind Stage-2 data-access metadata audit"
    )
    parser.add_argument("--quotes", required=True)
    parser.add_argument("--stock-master", required=True)
    parser.add_argument("--fundamentals", required=True)
    parser.add_argument("--official-calendar", required=True)
    parser.add_argument("--rights-attestation")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--fail-on-blocked",
        action="store_true",
        help="return exit code 2 when metadata/rights gates are blocked",
    )
    args = parser.parse_args(argv)
    try:
        output = require_new_private_file_target(
            args.output,
            label="data-access audit output target",
        )
    except PrivateArtifactPathError as exc:
        raise DataAccessError(str(exc)) from exc
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
    payload = (
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    try:
        write_private_bytes_atomic_exclusive(
            output,
            payload,
            label="data-access audit output target",
        )
    except PrivateArtifactPathError as exc:
        raise DataAccessError(str(exc)) from exc
    return 2 if args.fail_on_blocked and result["status"] == "blocked" else 0


if __name__ == "__main__":  # pragma: no cover - exercised through subprocess in release checks
    raise SystemExit(_cli())
