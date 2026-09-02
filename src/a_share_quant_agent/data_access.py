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
from datetime import date
import hashlib
import io
import json
import argparse
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
    duplicate_key_count = 0
    seen_keys: set[tuple[str, ...]] = set()
    invalid_date_count = 0
    publication_before_report_count = 0
    delisted_count = 0
    exchange_values: set[str] = set()

    for row in reader:
        rows += 1
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
        if role == "quotes":
            row_date = _parse_date(row.get("date"))
            key = (symbol, str(row.get("date") or "").strip())
            exchange_values.add(symbol.rsplit(".", 1)[-1].upper() if "." in symbol else "")
        elif role == "stock_master":
            row_date = _parse_date(row.get("listDate"))
            key = (symbol,)
            status = str(row.get("listStatus") or "").strip().lower()
            if status in {"delisted", "terminated", "d", "退市", "终止上市"}:
                delisted_count += 1
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
            key = (symbol, str(row.get("reportPeriodEnd") or "").strip())
        else:
            row_date = _parse_date(row.get("date"))
            key = (str(row.get("date") or "").strip(),)
        if row_date is not None:
            dates.append(row_date)
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
            # A second pass is unnecessary for rows, but delist range is useful
            # metadata; parse it from the already decoded text only.
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
        "duplicate_key_count": duplicate_key_count,
        "invalid_date_count": invalid_date_count,
        "publication_before_report_count": publication_before_report_count,
        "delisted_row_count": delisted_count,
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

    issues: list[str] = []
    role_reports: dict[str, Any] = {}
    for role in STAGE2_DATASET_ROLES:
        metadata = metadata_by_role.get(role)
        if metadata is None:
            issues.append(f"MISSING_ROLE:{role}")
            continue
        role_reports[role] = dict(metadata)
        if metadata.get("missing_required_columns"):
            issues.append(f"MISSING_FIELDS:{role}")
        if int(metadata.get("row_count", 0)) <= 0:
            issues.append(f"EMPTY_INPUT:{role}")
        if int(metadata.get("duplicate_key_count", 0)) > 0:
            issues.append(f"DUPLICATE_KEYS:{role}")
        if int(metadata.get("invalid_date_count", 0)) > 0:
            issues.append(f"INVALID_DATES:{role}")

    quotes = metadata_by_role.get("quotes", {})
    quote_range = _metadata_range(quotes, "date")
    if quote_range[0] is None or quote_range[0] > STAGE2_TARGETS["quote_start"]:
        issues.append("QUOTE_WARMUP_NOT_COVERED")
    if quote_range[1] is None or quote_range[1] < STAGE2_TARGETS["quote_end"]:
        issues.append("QUOTE_ENDPOINT_NOT_COVERED")
    fundamentals = metadata_by_role.get("fundamentals", {})
    fundamental_publish_range = _metadata_range(fundamentals, "publishDate")
    fundamental_report_range = _metadata_range(fundamentals, "reportPeriodEnd")
    if fundamental_publish_range[0] is None or fundamental_publish_range[0] > STAGE2_TARGETS["fundamental_start"]:
        issues.append("FUNDAMENTAL_PUBLICATION_HISTORY_NOT_COVERED")
    if fundamental_report_range[1] is None or fundamental_report_range[1] < STAGE2_TARGETS["fundamental_end"]:
        issues.append("FUNDAMENTAL_REPORT_INTERVAL_NOT_COVERED")
    if int(fundamentals.get("publication_before_report_count", 0)) > 0:
        issues.append("PUBLICATION_BEFORE_REPORT_PERIOD")
    calendar = metadata_by_role.get("official_calendar", {})
    calendar_range = _metadata_range(calendar, "date")
    if calendar_range[0] is None or calendar_range[0][:7] > STAGE2_TARGETS["calendar_start_month"]:
        issues.append("CALENDAR_START_NOT_COVERED")
    if calendar_range[1] is None or calendar_range[1][:7] < STAGE2_TARGETS["calendar_end_month"]:
        issues.append("CALENDAR_END_NOT_COVERED")
    for field in ("is_st", "is_suspended"):
        values = quotes.get("distinct_values", {}).get(field, [])
        if len(values) < 2:
            issues.append(f"DEGENERATE_FIELD:{field}")

    master = metadata_by_role.get("stock_master", {})
    if int(master.get("delisted_row_count", 0)) <= 0:
        issues.append("NO_DELISTED_SECURITY_ROWS")
    exchanges = {str(value).upper() for value in master.get("exchange_values", [])}
    if not {"SH", "SZ"}.issubset(exchanges):
        issues.append("STOCK_MASTER_MISSING_SH_OR_SZ")

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
            rate = rates.get(field)
            if rate is not None and float(rate) < 1.0:
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
    if attestation.get("status") != "attested":
        issues.append("STATUS_NOT_ATTESTED")
    for field in ("study_id", "attested_at", "attestor", "contract_reference"):
        if not str(attestation.get(field) or "").strip():
            issues.append(f"MISSING_{field.upper()}")
    if not _ISO_TIMESTAMP_RE.match(str(attestation.get("attested_at") or "")):
        issues.append("ATTESTED_AT_NOT_TIMEZONE_AWARE")
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
        ):
            if not isinstance(record.get(field), bool):
                issues.append(f"{role}:BOOLEAN_REQUIRED:{field}")
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
        ):
            if public_outputs.get(field) is not True:
                issues.append(f"PUBLIC_OUTPUT_NOT_ATTESTED:{field}")

    # Prevent accidental inclusion of credentials or raw secrets in the packet.
    serialized = json.dumps(attestation, ensure_ascii=False, sort_keys=True)
    if re.search(r"(?i)(api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*['\"][^'\"]+", serialized):
        issues.append("SECRET_LIKE_VALUE_PRESENT")
    return {
        "schema_version": "stage2_data_rights_attestation_v1",
        "status": "valid" if not issues else "invalid",
        "issues": sorted(dict.fromkeys(issues)),
        "authorization_granted": False,
    }


def _require_columns(frame: pd.DataFrame, columns: Iterable[str], label: str) -> None:
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
    daily = raw.copy()
    factors = adjustment_factors.copy()
    daily["trade_date"] = _date_series(daily, "trade_date", "Tushare daily")
    factors["trade_date"] = _date_series(factors, "trade_date", "Tushare adj_factor")
    daily["ts_code"] = daily["ts_code"].astype(str).str.strip().str.upper()
    factors["ts_code"] = factors["ts_code"].astype(str).str.strip().str.upper()
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
    joined["adj_factor"] = pd.to_numeric(joined["adj_factor"], errors="coerce")
    if joined["adj_factor"].isna().any() or (joined["adj_factor"] <= 0).any():
        raise DataAccessError("Tushare daily has missing or non-positive adjustment factors")
    for field in ("close", "amount"):
        joined[field] = pd.to_numeric(joined[field], errors="coerce")
        if joined[field].isna().any():
            raise DataAccessError(f"Tushare daily has non-numeric {field}")
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
        result["volume"] = pd.to_numeric(joined["vol"], errors="coerce") * 100.0
    for field in ("open", "high", "low", "pre_close"):
        if field in joined:
            result[field] = pd.to_numeric(joined[field], errors="coerce")
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
    disagreement = pivot["SSE"].notna() & pivot["SZSE"].notna() & (pivot["SSE"] != pivot["SZSE"])
    if disagreement.any():
        raise DataAccessError("SSE/SZSE trade-calendar disagreement requires human resolution")
    common = pivot[(pivot["SSE"] == True) & (pivot["SZSE"] == True)].reset_index()  # noqa: E712
    return common[["date"]].sort_values("date").reset_index(drop=True)


def normalize_tushare_disclosure_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Map only *actual* report disclosure dates to the Stage-2 contract."""

    _require_columns(raw, ("ts_code", "end_date", "actual_date"), "Tushare disclosure_date")
    frame = raw.copy()
    frame["symbol"] = frame["ts_code"].astype(str).str.strip().str.upper()
    frame["reportPeriodEnd"] = _date_series(frame, "end_date", "Tushare disclosure_date")
    actual = frame["actual_date"].astype(str).str.strip()
    if actual.eq("").any() or actual.isin({"NONE", "NAN", "NAT"}).any():
        raise DataAccessError("Tushare disclosure_date has rows without actual_date; do not substitute scheduled dates")
    frame["publishDate"] = _date_series(frame, "actual_date", "Tushare disclosure_date")
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
    frame["symbol"] = frame["ts_code"].astype(str).str.strip().str.upper()
    if frame["symbol"].eq("").any() or frame["symbol"].isin({"NAN", "NONE"}).any():
        raise DataAccessError("Tushare stock master contains blank symbols")
    frame["listDate"] = _date_series(frame, "list_date", "Tushare stock master")
    raw_delist = frame["delist_date"].astype(str).str.strip()
    frame["delistDate"] = pd.to_datetime(raw_delist.where(~raw_delist.isin({"", "NONE", "NAN", "NAT"})), errors="coerce").dt.normalize()
    invalid_delist = raw_delist.ne("") & ~raw_delist.isin({"NONE", "NAN", "NAT"}) & frame["delistDate"].isna()
    if invalid_delist.any():
        raise DataAccessError("Tushare stock master contains invalid delist_date values")
    frame["listStatus"] = frame["list_status"].astype(str).str.strip().str.upper()
    frame["stockType"] = frame["stock_type"].astype(str).str.strip().str.upper()
    if frame.duplicated("symbol").any():
        raise DataAccessError("Tushare stock master has duplicate symbols")
    if (frame["delistDate"].notna() & (frame["delistDate"] < frame["listDate"])).any():
        raise DataAccessError("Tushare stock master has delist dates before list dates")
    return frame[["symbol", "listDate", "delistDate", "listStatus", "stockType"]].sort_values("symbol").reset_index(drop=True)


def normalize_tushare_st_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize positive ST observations; absence remains unknown."""

    _require_columns(raw, ("ts_code", "trade_date"), "Tushare stock_st")
    frame = raw.copy()
    frame["symbol"] = frame["ts_code"].astype(str).str.strip().str.upper()
    frame["date"] = _date_series(frame, "trade_date", "Tushare stock_st")
    if frame.duplicated(["symbol", "date"]).any():
        raise DataAccessError("Tushare stock_st has duplicate symbol-date keys")
    return frame[["symbol", "date"]].assign(is_st=True).sort_values(["symbol", "date"]).reset_index(drop=True)


def normalize_tushare_suspend_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize positive suspension observations; absence remains unknown."""

    _require_columns(raw, ("ts_code", "trade_date"), "Tushare suspend_d")
    frame = raw.copy()
    frame["symbol"] = frame["ts_code"].astype(str).str.strip().str.upper()
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
