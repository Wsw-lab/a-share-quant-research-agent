"""Privacy-preserving coverage audit for the Stage-2 factor study.

The audit reports field availability, time span, coverage rates, and file
identity without publishing local paths or row-level licensed data.  It is a
precondition check, not a replacement for the study runner's strict input
validation.
"""

from __future__ import annotations

import argparse
from calendar import monthrange
import csv
from datetime import date, datetime
import hashlib
import io
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse


SCHEMA_VERSION = "study_v2_data_coverage_audit_v1"

FIXED_DESIGN_PARAMETERS: dict[str, Any] = {
    "analysis_end": "2022-12-31",
    "analysis_start": "2010-01-01",
    "maximum_fundamental_staleness_months": 18,
    "minimum_history_years": 13.0,
    "minimum_monthly_observations": 156,
    "minimum_publish_date_rate": 0.95,
    "minimum_sessions_per_month": 15,
    "minimum_symbols_per_month": 1000,
    "required_fundamental_end": "2022-12-31",
    "required_fundamental_start": "2009-01-01",
    "required_official_calendar_first_month": "2009-01",
    "required_official_calendar_last_month": "2023-01",
    "required_quote_end": "2023-01-31",
    "required_quote_start": "2009-01-01",
}
CSV_NORMALIZATION: dict[str, str] = {
    "blank_values": "strip_surrounding_whitespace_then_empty_is_null",
    "column_names": "case_sensitive_exact_header_names",
    "csv_dialect": "excel",
    "date_values": "ISO-8601_calendar_date_from_first_10_characters",
    "encoding": "utf-8-sig",
}
INPUT_ROLES = ("quotes", "stock_master", "fundamentals", "official_calendar")

QUOTE_REQUIRED = {
    "date", "symbol", "close", "amount", "is_st", "is_suspended",
}
MASTER_REQUIRED = {"symbol", "listDate", "delistDate", "listStatus", "stockType"}
FUNDAMENTAL_REQUIRED = {"symbol", "roeDiluted", "publishDate", "reportPeriodEnd"}
CALENDAR_REQUIRED = {"date"}
VINTAGE_TIME_COLUMNS = {
    "asofdate", "as_of_date", "vintagedate", "vintage_date", "revisiondate",
    "revision_date", "as_of_or_vintage_timestamp",
}
VINTAGE_ID_COLUMNS = {
    "versionid", "version_id", "revisionid", "revision_id", "vintageid",
    "vintage_id", "version_or_revision_identifier",
}


class StudyV2CoverageError(RuntimeError):
    """Raised when an input cannot be audited safely."""


def audit_study_inputs(
    *,
    quotes_path: str | Path,
    stock_master_path: str | Path,
    fundamentals_path: str | Path,
    official_calendar_path: str | Path,
    minimum_history_years: float = 13.0,
    minimum_publish_date_rate: float = 0.95,
    minimum_monthly_observations: int = 156,
    minimum_symbols_per_month: int = 1000,
    minimum_sessions_per_month: int = 15,
    analysis_start: str = "2010-01-01",
    analysis_end: str = "2022-12-31",
    required_quote_start: str = "2009-01-01",
    required_quote_end: str = "2023-01-31",
    required_fundamental_start: str = "2009-01-01",
    required_fundamental_end: str = "2022-12-31",
    review_attestation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Read four regular files and return the locked, path-redacted report.

    The keyword parameters remain accepted for CLI compatibility, but every
    value must equal the fixed Stage-2 design.  They are not tuning controls.
    """

    _validate_fixed_design_arguments(
        minimum_history_years=minimum_history_years,
        minimum_publish_date_rate=minimum_publish_date_rate,
        minimum_monthly_observations=minimum_monthly_observations,
        minimum_symbols_per_month=minimum_symbols_per_month,
        minimum_sessions_per_month=minimum_sessions_per_month,
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        required_quote_start=required_quote_start,
        required_quote_end=required_quote_end,
        required_fundamental_start=required_fundamental_start,
        required_fundamental_end=required_fundamental_end,
    )
    quote_file = _regular_file(quotes_path, "quotes")
    master_file = _regular_file(stock_master_path, "stock master")
    fundamental_file = _regular_file(fundamentals_path, "fundamentals")
    calendar_file = _regular_file(official_calendar_path, "official calendar")
    return recompute_coverage_report(
        quotes_csv=quote_file.read_bytes(),
        stock_master_csv=master_file.read_bytes(),
        fundamentals_csv=fundamental_file.read_bytes(),
        official_calendar_csv=calendar_file.read_bytes(),
        input_names={
            "quotes": quote_file.name,
            "stock_master": master_file.name,
            "fundamentals": fundamental_file.name,
            "official_calendar": calendar_file.name,
        },
        review_attestation=review_attestation,
    )


def recompute_coverage_report(
    *,
    quotes_csv: bytes,
    stock_master_csv: bytes,
    fundamentals_csv: bytes,
    official_calendar_csv: bytes,
    input_names: Mapping[str, str] | None = None,
    review_attestation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Purely recompute the locked report from raw CSV bytes.

    No report field is accepted as an input.  Hashes cover the exact bytes;
    coverage statistics are derived from deterministic UTF-8 CSV parsing.
    """

    raw_inputs = {
        "quotes": _raw_csv_bytes(quotes_csv, "quotes"),
        "stock_master": _raw_csv_bytes(stock_master_csv, "stock_master"),
        "fundamentals": _raw_csv_bytes(fundamentals_csv, "fundamentals"),
        "official_calendar": _raw_csv_bytes(
            official_calendar_csv, "official_calendar"
        ),
    }
    names = _normalized_input_names(input_names)
    identities = {
        role: _raw_file_identity(raw_inputs[role], names[role])
        for role in INPUT_ROLES
    }
    quotes = _scan_quotes(raw_inputs["quotes"], identities["quotes"])
    master = _scan_master(raw_inputs["stock_master"], identities["stock_master"])
    fundamentals = _scan_fundamentals(
        raw_inputs["fundamentals"], identities["fundamentals"]
    )
    official_calendar = _scan_official_calendar(
        raw_inputs["official_calendar"], identities["official_calendar"]
    )
    quote_symbols, dated_quote_symbols = _quote_symbol_index(
        raw_inputs["quotes"]
    )
    official_session_dates = set(
        _date_column_values(raw_inputs["official_calendar"], "date")
    )
    rebalance_date_by_month: dict[str, date] = {}
    for session in official_session_dates:
        month = session.strftime("%Y-%m")
        if month not in rebalance_date_by_month or session < rebalance_date_by_month[month]:
            rebalance_date_by_month[month] = session
    monthly_rebalance_quote_symbols = {
        month: dated_quote_symbols.get(rebalance_date, set())
        for month, rebalance_date in rebalance_date_by_month.items()
    }
    strict_a_share_master_symbols = _strict_a_share_master_symbols(
        raw_inputs["stock_master"]
    )
    eligible_a_share_symbols = quote_symbols & strict_a_share_master_symbols
    master["strict_a_share_symbol_count"] = len(strict_a_share_master_symbols)
    quotes["eligible_symbol_count"] = len(eligible_a_share_symbols)
    quotes["eligible_symbol_count_basis"] = "first_official_session_of_month"
    for row in quotes["monthly_coverage"]:
        row["eligible_symbol_count"] = len(
            monthly_rebalance_quote_symbols.get(row["month"], set())
            & strict_a_share_master_symbols
        )
    attestation = _validate_review_attestation(
        review_attestation,
        expected_file_sha256={
            role: identities[role]["sha256"] for role in INPUT_ROLES
        },
    )
    parameters = dict(FIXED_DESIGN_PARAMETERS)
    analysis_start_date = _required_date(parameters["analysis_start"], "analysis_start")
    analysis_end_date = _required_date(parameters["analysis_end"], "analysis_end")
    required_quote_start_date = _required_date(
        parameters["required_quote_start"], "required_quote_start"
    )
    required_quote_end_date = _required_date(
        parameters["required_quote_end"], "required_quote_end"
    )
    required_fundamental_start_date = _required_date(
        parameters["required_fundamental_start"], "required_fundamental_start"
    )
    required_fundamental_end_date = _required_date(
        parameters["required_fundamental_end"], "required_fundamental_end"
    )
    required_calendar_first_month = _required_month(
        parameters["required_official_calendar_first_month"],
        "required_official_calendar_first_month",
    )
    required_calendar_last_month = _required_month(
        parameters["required_official_calendar_last_month"],
        "required_official_calendar_last_month",
    )
    required_quote_first_month = required_quote_start_date.strftime("%Y-%m")
    required_quote_last_month = required_quote_end_date.strftime("%Y-%m")
    required_quote_sessions = sorted(
        session
        for session in official_session_dates
        if required_quote_first_month
        <= session.strftime("%Y-%m")
        <= required_quote_last_month
    )
    required_quote_session_start = (
        required_quote_sessions[0] if required_quote_sessions else None
    )
    required_quote_session_end = (
        required_quote_sessions[-1] if required_quote_sessions else None
    )
    expected_months = _calendar_months(analysis_start_date, analysis_end_date)
    if len(expected_months) != parameters["minimum_monthly_observations"]:
        raise StudyV2CoverageError(
            "fixed design contract month count does not match the analysis interval"
        )

    market_start = _parse_date(quotes["market_start"])
    market_end = _parse_date(quotes["market_end"])
    history_years = (
        (market_end - market_start).days / 365.2425
        if market_start is not None and market_end is not None
        else 0.0
    )
    minimum_history_met = history_years >= parameters["minimum_history_years"]
    target_quote_interval_available = bool(
        market_start is not None
        and market_end is not None
        and required_quote_session_start is not None
        and required_quote_session_end is not None
        and market_start <= required_quote_session_start
        and market_end >= required_quote_session_end
    )
    calendar_start = _parse_date(official_calendar["calendar_start"])
    calendar_end = _parse_date(official_calendar["calendar_end"])
    calendar_integrity_verified = bool(
        official_calendar["required_columns_present"]
        and official_calendar["row_count"] > 0
        and official_calendar["non_null_date_rate"] == 1.0
        and official_calendar["duplicate_session_count"] == 0
        and official_calendar["strictly_increasing"]
        and not official_calendar["additional_columns"]
    )
    target_calendar_interval_available = bool(
        calendar_start is not None
        and calendar_end is not None
        and calendar_start.strftime("%Y-%m") <= required_calendar_first_month
        and calendar_end.strftime("%Y-%m") >= required_calendar_last_month
    )
    calendar_dates = official_session_dates
    quote_dates = set(_date_column_values(raw_inputs["quotes"], "date"))
    non_calendar_quote_dates = quote_dates - calendar_dates
    quote_dates_are_official_sessions = not non_calendar_quote_dates
    monthly_by_id = {
        row["month"]: row for row in official_calendar["monthly_coverage"]
    }
    target_months = [monthly_by_id[month] for month in expected_months if month in monthly_by_id]
    missing_analysis_months = [month for month in expected_months if month not in monthly_by_id]
    full_months = [
        row
        for row in target_months
        if row["session_count"] >= parameters["minimum_sessions_per_month"]
    ]
    quote_monthly_by_id = {row["month"]: row for row in quotes["monthly_coverage"]}
    symbol_eligible_month_ids = [
        month
        for month in expected_months
        if quote_monthly_by_id.get(month, {}).get("eligible_symbol_count", 0)
        >= parameters["minimum_symbols_per_month"]
    ]
    eligible_months = [
        row
        for row in full_months
        if row["month"] in symbol_eligible_month_ids
    ]
    minimum_monthly_observations_met = len(target_months) == len(expected_months)
    minimum_sessions_per_month_met = len(full_months) == len(expected_months)
    minimum_symbols_per_month_met = (
        len(symbol_eligible_month_ids) == len(expected_months)
    )
    fundamental_coverage = _fundamental_monthly_coverage(
        raw_csv=raw_inputs["fundamentals"],
        expected_months=expected_months,
        official_sessions=calendar_dates,
        monthly_quote_symbols=monthly_rebalance_quote_symbols,
        eligible_master_symbols=strict_a_share_master_symbols,
        eligible_universe_symbols=eligible_a_share_symbols,
        required_start=required_fundamental_start_date,
        required_end=required_fundamental_end_date,
        maximum_staleness_months=parameters[
            "maximum_fundamental_staleness_months"
        ],
    )
    fundamentals.update(fundamental_coverage)
    publication_coverage_met = (
        fundamentals["eligible_interval_publish_date_non_null_rate"]
        >= parameters["minimum_publish_date_rate"]
    )
    fundamental_target_month_continuity_met = (
        fundamentals["covered_target_month_count"] == len(expected_months)
    )
    fundamental_eligible_symbol_intersection_met = all(
        row["available_fundamental_symbol_count"]
        >= parameters["minimum_symbols_per_month"]
        for row in fundamentals["monthly_coverage"]
    )
    fundamental_staleness_coverage_met = all(
        row["nonstale_fundamental_symbol_count"]
        >= parameters["minimum_symbols_per_month"]
        for row in fundamentals["monthly_coverage"]
    )
    target_fundamental_interval_available = bool(
        fundamentals["required_columns_present"]
        and publication_coverage_met
        and fundamental_target_month_continuity_met
        and fundamental_eligible_symbol_intersection_met
        and fundamental_staleness_coverage_met
    )
    membership_available = (
        master["required_columns_present"]
        and master["non_null_list_date_rate"] >= 0.95
        and master["delisted_symbol_count"] > 0
    )
    execution_columns_present = quotes["required_columns_present"]
    execution_semantics_verified = bool(
        execution_columns_present and attestation["execution_semantics_verified"]
    )
    tradability_fields_verified = bool(
        execution_columns_present and attestation["tradability_fields_verified"]
    )
    data_rights_verified = bool(attestation["data_rights_verified"])
    official_calendar_review_verified = bool(
        attestation["official_calendar_verified"]
    )
    no_empty_inputs = all(
        section["row_count"] > 0
        for section in (quotes, master, fundamentals, official_calendar)
    )
    ready = all(
        (
            minimum_history_met,
            target_quote_interval_available,
            calendar_integrity_verified,
            target_calendar_interval_available,
            quote_dates_are_official_sessions,
            target_fundamental_interval_available,
            minimum_monthly_observations_met,
            minimum_sessions_per_month_met,
            minimum_symbols_per_month_met,
            publication_coverage_met,
            membership_available,
            execution_columns_present,
            execution_semantics_verified,
            tradability_fields_verified,
            data_rights_verified,
            official_calendar_review_verified,
            fundamentals["required_columns_present"],
            no_empty_inputs,
        )
    )

    vintage_available = False
    reasons = []
    if not minimum_history_met:
        reasons.append("INSUFFICIENT_HISTORY")
    if not target_quote_interval_available:
        reasons.append("TARGET_QUOTE_INTERVAL_UNAVAILABLE")
    if not calendar_integrity_verified:
        reasons.append("INVALID_OFFICIAL_CALENDAR")
    if not target_calendar_interval_available:
        reasons.append("OFFICIAL_CALENDAR_INTERVAL_UNAVAILABLE")
    if not quote_dates_are_official_sessions:
        reasons.append("QUOTE_DATES_OUTSIDE_OFFICIAL_CALENDAR")
    if not target_fundamental_interval_available:
        reasons.append("TARGET_FUNDAMENTAL_INTERVAL_UNAVAILABLE")
    if not fundamental_target_month_continuity_met:
        reasons.append("INCOMPLETE_FUNDAMENTAL_TARGET_MONTH_CONTINUITY")
    if not fundamental_eligible_symbol_intersection_met:
        reasons.append("INSUFFICIENT_FUNDAMENTAL_ELIGIBLE_SYMBOL_COVERAGE")
    if not fundamental_staleness_coverage_met:
        reasons.append("INSUFFICIENT_NONSTALE_FUNDAMENTAL_COVERAGE")
    if not minimum_monthly_observations_met:
        reasons.append("INSUFFICIENT_MONTHLY_COVERAGE")
    if not minimum_sessions_per_month_met:
        reasons.append("INSUFFICIENT_MONTHLY_SESSION_COVERAGE")
    if not minimum_symbols_per_month_met:
        reasons.append("INSUFFICIENT_MONTHLY_SYMBOL_COVERAGE")
    if not publication_coverage_met:
        reasons.append("INSUFFICIENT_PUBLICATION_DATE_COVERAGE")
    if not membership_available:
        reasons.append("INCOMPLETE_POINT_IN_TIME_MEMBERSHIP")
    if not execution_columns_present:
        reasons.append("MISSING_EXECUTION_OR_TRADABILITY_FIELDS")
    if not execution_semantics_verified:
        reasons.append("EXECUTION_SEMANTICS_NOT_VERIFIED")
    if not tradability_fields_verified:
        reasons.append("TRADABILITY_FIELDS_NOT_VERIFIED")
    if not data_rights_verified:
        reasons.append("DATA_RIGHTS_NOT_VERIFIED")
    if not official_calendar_review_verified:
        reasons.append("OFFICIAL_CALENDAR_NOT_REVIEWED")
    if not fundamentals["required_columns_present"]:
        reasons.append("MISSING_FUNDAMENTAL_FIELDS")
    if not no_empty_inputs:
        reasons.append("EMPTY_INPUT")

    input_manifest = {
        "files": identities,
        "hash_algorithm": "sha256",
        "hash_basis": "raw_csv_bytes",
        "normalization": dict(CSV_NORMALIZATION),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "parameters": dict(parameters),
        "parameters_sha256": _canonical_sha256(parameters),
        "thresholds": dict(parameters),
        "inputs": input_manifest,
        "input_manifest_sha256": _canonical_sha256(input_manifest),
        "quotes": quotes,
        "stock_master": master,
        "fundamentals": fundamentals,
        "official_calendar": official_calendar,
        "gates": {
            "observed_history_years": round(history_years, 4),
            "minimum_history_years_met": minimum_history_met,
            "required_quote_session_start": (
                required_quote_session_start.isoformat()
                if required_quote_session_start is not None
                else None
            ),
            "required_quote_session_end": (
                required_quote_session_end.isoformat()
                if required_quote_session_end is not None
                else None
            ),
            "target_quote_interval_available": target_quote_interval_available,
            "official_calendar_integrity_verified": calendar_integrity_verified,
            "target_official_calendar_interval_available": (
                target_calendar_interval_available
            ),
            "quote_dates_are_official_sessions": quote_dates_are_official_sessions,
            "non_calendar_quote_date_count": len(non_calendar_quote_dates),
            "target_fundamental_interval_available": target_fundamental_interval_available,
            "fundamental_interval_basis": (
                "first official session per target month; publishDate strictly before "
                "that session; quote/master eligible intersection; reportPeriodEnd no "
                "more than 18 calendar months stale"
            ),
            "fundamental_target_month_continuity_met": (
                fundamental_target_month_continuity_met
            ),
            "fundamental_eligible_symbol_intersection_met": (
                fundamental_eligible_symbol_intersection_met
            ),
            "fundamental_staleness_coverage_met": (
                fundamental_staleness_coverage_met
            ),
            "expected_analysis_month_count": len(expected_months),
            "target_observed_month_count": len(target_months),
            "missing_analysis_months": missing_analysis_months,
            "full_month_count": len(full_months),
            "eligible_a_share_symbol_count": len(eligible_a_share_symbols),
            "symbol_eligible_month_count": len(symbol_eligible_month_ids),
            "eligible_month_count": len(eligible_months),
            "minimum_monthly_observations_met": minimum_monthly_observations_met,
            "minimum_sessions_per_month_met": minimum_sessions_per_month_met,
            "minimum_symbols_per_month_met": minimum_symbols_per_month_met,
            "publication_date_coverage_met": publication_coverage_met,
            "point_in_time_membership_available": membership_available,
            "execution_columns_present": execution_columns_present,
            "execution_semantics_verified": execution_semantics_verified,
            "tradability_fields_verified": tradability_fields_verified,
            "data_rights_verified": data_rights_verified,
            "official_calendar_review_verified": official_calendar_review_verified,
            "complete_revision_vintage_available": vintage_available,
            "revision_history_claim_allowed": vintage_available,
            "ready_to_lock_stage2_plan": ready,
            "blocking_reason_codes": reasons,
        },
        "scope": {
            "purpose": "data-feasibility precondition for a Stage-2 registered study",
            "contract_mutability": "fixed; caller overrides are rejected",
            "duplicate_key_validation": "deferred to the strict study runner",
            "raw_rows_disclosed": False,
            "local_paths_disclosed": False,
            "revision_history_boundary": (
                "not allowed: a validated revision-vintage adapter is not implemented; "
                "observed vintage-like columns are diagnostic only"
            ),
            "column_presence_boundary": (
                "open and tradability columns do not establish execution semantics, "
                "field informativeness, or publication rights"
            ),
            "symbol_eligibility_boundary": (
                "each monthly cell uses quotes on that month's first official session, "
                "intersected with stock-master rows whose stockType is exactly A股 and "
                "whose symbol matches six digits plus .SH or .SZ"
            ),
        },
        "review_attestation": {
            "present": review_attestation is not None,
            "schema_version": attestation["schema_version"],
            "reviewed_at": attestation["reviewed_at"],
            "reviewer_recorded": attestation["reviewer_recorded"],
            "sha256": attestation["sha256"],
        },
    }


def validate_coverage_report(
    report: Mapping[str, Any],
    *,
    quotes_csv: bytes,
    stock_master_csv: bytes,
    fundamentals_csv: bytes,
    official_calendar_csv: bytes,
    input_names: Mapping[str, str] | None = None,
    review_attestation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Strictly validate a report by independently recomputing every field."""

    if not isinstance(report, Mapping):
        raise StudyV2CoverageError("coverage report must be a JSON object")
    expected = recompute_coverage_report(
        quotes_csv=quotes_csv,
        stock_master_csv=stock_master_csv,
        fundamentals_csv=fundamentals_csv,
        official_calendar_csv=official_calendar_csv,
        input_names=input_names,
        review_attestation=review_attestation,
    )
    try:
        reported_bytes = _canonical_json_bytes(dict(report))
    except (TypeError, ValueError) as exc:
        raise StudyV2CoverageError("coverage report is not canonicalizable JSON") from exc
    if reported_bytes != _canonical_json_bytes(expected):
        raise StudyV2CoverageError(
            "coverage report does not match recomputed raw CSV report"
        )
    return expected


def write_coverage_report(report: Mapping[str, Any], output_path: str | Path) -> None:
    destination = Path(output_path).expanduser().resolve(strict=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical_json_bytes(report) + b"\n"
    destination.write_bytes(payload)


def _scan_quotes(raw_csv: bytes, identity: Mapping[str, Any]) -> dict[str, Any]:
    scan = _scan_csv(
        raw_csv,
        source_name=str(identity["file_name"]),
        required=QUOTE_REQUIRED,
        date_columns=("date",),
        non_null_columns=("date", "symbol", "open", "close", "volume", "amount"),
        monthly_date_column="date",
    )
    return {
        **identity,
        "row_count": scan["row_count"],
        "symbol_count": scan["symbol_count"],
        "market_start": scan["date_ranges"]["date"][0],
        "market_end": scan["date_ranges"]["date"][1],
        "required_columns_present": scan["required_columns_present"],
        "missing_required_columns": scan["missing_required_columns"],
        "non_null_rates": scan["non_null_rates"],
        "observed_month_count": len(scan["monthly_coverage"]),
        "minimum_monthly_symbol_count": min(
            (row["symbol_count"] for row in scan["monthly_coverage"]), default=0
        ),
        "minimum_sessions_per_observed_month": min(
            (row["session_count"] for row in scan["monthly_coverage"]), default=0
        ),
        "monthly_coverage": scan["monthly_coverage"],
    }


def _scan_master(raw_csv: bytes, identity: Mapping[str, Any]) -> dict[str, Any]:
    scan = _scan_csv(
        raw_csv,
        source_name=str(identity["file_name"]),
        required=MASTER_REQUIRED,
        date_columns=("listDate", "delistDate"),
        non_null_columns=("symbol", "listDate"),
        collect_columns=("listStatus",),
    )
    delisted = sum(
        count for value, count in scan["collected_values"]["listStatus"].items()
        if value.strip().lower() == "delisted"
    )
    return {
        **identity,
        "row_count": scan["row_count"],
        "symbol_count": scan["symbol_count"],
        "earliest_list_date": scan["date_ranges"]["listDate"][0],
        "latest_delist_date": scan["date_ranges"]["delistDate"][1],
        "delisted_symbol_count": delisted,
        "non_null_list_date_rate": scan["non_null_rates"].get("listDate", 0.0),
        "required_columns_present": scan["required_columns_present"],
        "missing_required_columns": scan["missing_required_columns"],
    }


def _scan_fundamentals(raw_csv: bytes, identity: Mapping[str, Any]) -> dict[str, Any]:
    scan = _scan_csv(
        raw_csv,
        source_name=str(identity["file_name"]),
        required=FUNDAMENTAL_REQUIRED,
        date_columns=("publishDate", "reportPeriodEnd"),
        non_null_columns=("symbol", "roeDiluted", "publishDate", "reportPeriodEnd"),
    )
    vintage = _audit_vintage_rows(raw_csv, scan["fieldnames"])
    return {
        **identity,
        "row_count": scan["row_count"],
        "symbol_count": scan["symbol_count"],
        "report_period_start": scan["date_ranges"]["reportPeriodEnd"][0],
        "report_period_end": scan["date_ranges"]["reportPeriodEnd"][1],
        "publication_start": scan["date_ranges"]["publishDate"][0],
        "publication_end": scan["date_ranges"]["publishDate"][1],
        "publish_date_non_null_rate": scan["non_null_rates"].get("publishDate", 0.0),
        "required_columns_present": scan["required_columns_present"],
        "missing_required_columns": scan["missing_required_columns"],
        "revision_vintage_fields_observed": vintage["fields_present"],
        "validated_revision_adapter_implemented": False,
        "complete_revision_vintage_fields_present": False,
        "revision_vintage_complete_row_rate": vintage["complete_row_rate"],
        "revision_versioned_symbol_period_count": vintage["versioned_symbol_period_count"],
    }


def _scan_official_calendar(
    raw_csv: bytes, identity: Mapping[str, Any]
) -> dict[str, Any]:
    scan = _scan_csv(
        raw_csv,
        source_name=str(identity["file_name"]),
        required=CALENDAR_REQUIRED,
        date_columns=("date",),
        non_null_columns=("date",),
        monthly_date_column="date",
    )
    dates = _date_column_values(raw_csv, "date") if "date" in scan["fieldnames"] else []
    return {
        **identity,
        "calendar_schema_version": "stage2_official_calendar_csv_v1",
        "timezone": "Asia/Shanghai",
        "row_count": scan["row_count"],
        "session_count": len(set(dates)),
        "calendar_start": scan["date_ranges"]["date"][0],
        "calendar_end": scan["date_ranges"]["date"][1],
        "required_columns_present": scan["required_columns_present"],
        "missing_required_columns": scan["missing_required_columns"],
        "additional_columns": sorted(set(scan["fieldnames"]) - CALENDAR_REQUIRED),
        "non_null_date_rate": scan["non_null_rates"].get("date", 0.0),
        "duplicate_session_count": len(dates) - len(set(dates)),
        "strictly_increasing": bool(dates) and all(
            earlier < later for earlier, later in zip(dates, dates[1:])
        ),
        "observed_month_count": len(scan["monthly_coverage"]),
        "monthly_coverage": scan["monthly_coverage"],
    }


def _scan_csv(
    raw_csv: bytes,
    *,
    source_name: str,
    required: Iterable[str],
    date_columns: Sequence[str],
    non_null_columns: Sequence[str],
    collect_columns: Sequence[str] = (),
    monthly_date_column: str | None = None,
) -> dict[str, Any]:
    try:
        text = raw_csv.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise StudyV2CoverageError(f"CSV is not valid UTF-8: {source_name}") from exc
    try:
        with io.StringIO(text, newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or ())
            if not fieldnames:
                raise StudyV2CoverageError(f"CSV has no header: {source_name}")
            if len(fieldnames) != len(set(fieldnames)):
                raise StudyV2CoverageError(f"CSV has duplicate headers: {source_name}")
            missing = sorted(set(required) - set(fieldnames))
            dates: dict[str, list[date | None]] = {name: [None, None] for name in date_columns}
            non_null = {name: 0 for name in non_null_columns}
            collected: dict[str, dict[str, int]] = {name: {} for name in collect_columns}
            symbols: set[str] = set()
            monthly_symbols: dict[str, set[str]] = {}
            monthly_sessions: dict[str, set[str]] = {}
            rows = 0
            for row in reader:
                rows += 1
                symbol = (row.get("symbol") or "").strip()
                if symbol:
                    symbols.add(symbol)
                for name in non_null_columns:
                    if (row.get(name) or "").strip():
                        non_null[name] += 1
                for name in date_columns:
                    parsed = _parse_date(row.get(name))
                    if parsed is None:
                        continue
                    if dates[name][0] is None or parsed < dates[name][0]:
                        dates[name][0] = parsed
                    if dates[name][1] is None or parsed > dates[name][1]:
                        dates[name][1] = parsed
                if monthly_date_column is not None:
                    parsed_month_date = _parse_date(row.get(monthly_date_column))
                    if parsed_month_date is not None:
                        month = parsed_month_date.strftime("%Y-%m")
                        monthly_sessions.setdefault(month, set()).add(parsed_month_date.isoformat())
                        if symbol:
                            monthly_symbols.setdefault(month, set()).add(symbol)
                for name in collect_columns:
                    value = (row.get(name) or "").strip()
                    collected[name][value] = collected[name].get(value, 0) + 1
    except csv.Error as exc:
        raise StudyV2CoverageError(f"CSV cannot be parsed: {source_name}") from exc

    return {
        "fieldnames": fieldnames,
        "row_count": rows,
        "symbol_count": len(symbols),
        "required_columns_present": not missing,
        "missing_required_columns": missing,
        "date_ranges": {
            name: [
                dates[name][0].isoformat() if dates[name][0] else None,
                dates[name][1].isoformat() if dates[name][1] else None,
            ]
            for name in date_columns
        },
        "non_null_rates": {
            name: round(non_null[name] / rows, 10) if rows else 0.0
            for name in non_null_columns
        },
        "collected_values": collected,
        "monthly_coverage": [
            {
                "month": month,
                "session_count": len(monthly_sessions.get(month, set())),
                "symbol_count": len(monthly_symbols.get(month, set())),
            }
            for month in sorted(set(monthly_sessions) | set(monthly_symbols))
        ],
    }


def _date_column_values(raw_csv: bytes, column: str) -> list[date]:
    values: list[date] = []
    with io.TextIOWrapper(
        io.BytesIO(raw_csv), encoding="utf-8-sig", newline=""
    ) as handle:
        reader = csv.DictReader(handle)
        if column not in (reader.fieldnames or ()):
            return values
        for row in reader:
            parsed = _parse_date(row.get(column))
            if parsed is not None:
                values.append(parsed)
    return values


def _quote_symbol_index(
    raw_csv: bytes,
) -> tuple[set[str], dict[date, set[str]]]:
    symbols: set[str] = set()
    dated_symbols: dict[date, set[str]] = {}
    with io.TextIOWrapper(
        io.BytesIO(raw_csv), encoding="utf-8-sig", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            symbol = (row.get("symbol") or "").strip()
            trade_date = _parse_date(row.get("date"))
            if not symbol or trade_date is None:
                continue
            symbols.add(symbol)
            dated_symbols.setdefault(trade_date, set()).add(symbol)
    return symbols, dated_symbols


def _strict_a_share_master_symbols(raw_csv: bytes) -> set[str]:
    symbols: set[str] = set()
    with io.TextIOWrapper(
        io.BytesIO(raw_csv), encoding="utf-8-sig", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            symbol = (row.get("symbol") or "").strip()
            stock_type = (row.get("stockType") or "").strip()
            if stock_type == "A股" and re.fullmatch(r"[0-9]{6}\.(?:SH|SZ)", symbol):
                symbols.add(symbol)
    return symbols


def _fundamental_monthly_coverage(
    *,
    raw_csv: bytes,
    expected_months: Sequence[str],
    official_sessions: set[date],
    monthly_quote_symbols: Mapping[str, set[str]],
    eligible_master_symbols: set[str],
    eligible_universe_symbols: set[str],
    required_start: date,
    required_end: date,
    maximum_staleness_months: int,
) -> dict[str, Any]:
    sessions_by_month: dict[str, list[date]] = {}
    for session in official_sessions:
        sessions_by_month.setdefault(session.strftime("%Y-%m"), []).append(session)
    histories: dict[str, list[tuple[date, date, bool]]] = {}
    eligible_interval_rows = 0
    eligible_interval_publish_dates = 0
    invalid_publication_order_rows = 0
    with io.TextIOWrapper(
        io.BytesIO(raw_csv), encoding="utf-8-sig", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            symbol = (row.get("symbol") or "").strip()
            if symbol not in eligible_universe_symbols:
                continue
            report_end = _parse_date(row.get("reportPeriodEnd"))
            publish_date = _parse_date(row.get("publishDate"))
            roe_present = bool((row.get("roeDiluted") or "").strip())
            if report_end is not None and required_start <= report_end <= required_end:
                eligible_interval_rows += 1
                if publish_date is not None:
                    eligible_interval_publish_dates += 1
            if report_end is None or publish_date is None:
                continue
            if publish_date < report_end:
                invalid_publication_order_rows += 1
                continue
            histories.setdefault(symbol, []).append(
                (report_end, publish_date, roe_present)
            )
    for observations in histories.values():
        observations.sort(key=lambda item: (item[0], item[1]))

    rows: list[dict[str, Any]] = []
    for month in expected_months:
        sessions = sessions_by_month.get(month, [])
        signal_date = min(sessions) if sessions else None
        eligible_quote_symbols = (
            monthly_quote_symbols.get(month, set()) & eligible_master_symbols
        )
        available = 0
        nonstale = 0
        stale = 0
        if signal_date is not None:
            for symbol in eligible_quote_symbols:
                known = [
                    observation
                    for observation in histories.get(symbol, ())
                    if observation[0] <= signal_date
                    and observation[1] < signal_date
                    and observation[2]
                ]
                if not known:
                    continue
                report_end, _, _ = max(known, key=lambda item: (item[0], item[1]))
                available += 1
                staleness_cutoff = _subtract_calendar_months(
                    signal_date, maximum_staleness_months
                )
                if report_end >= staleness_cutoff:
                    nonstale += 1
                else:
                    stale += 1
        rows.append(
            {
                "month": month,
                "rebalance_date": signal_date.isoformat() if signal_date else None,
                "eligible_quote_symbol_count": len(eligible_quote_symbols),
                "available_fundamental_symbol_count": available,
                "nonstale_fundamental_symbol_count": nonstale,
                "stale_fundamental_symbol_count": stale,
            }
        )
    return {
        "eligible_interval_row_count": eligible_interval_rows,
        "eligible_interval_publish_date_non_null_rate": round(
            eligible_interval_publish_dates / eligible_interval_rows, 10
        )
        if eligible_interval_rows
        else 0.0,
        "invalid_publication_order_row_count": invalid_publication_order_rows,
        "maximum_staleness_months": maximum_staleness_months,
        "target_month_count": len(rows),
        "covered_target_month_count": sum(
            row["nonstale_fundamental_symbol_count"] > 0 for row in rows
        ),
        "monthly_coverage": rows,
    }


def _subtract_calendar_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 - months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise StudyV2CoverageError(f"invalid ISO date: {text!r}") from exc


def _required_date(value: Any, label: str) -> date:
    parsed = _parse_date(value)
    if parsed is None:
        raise StudyV2CoverageError(f"{label} is required")
    return parsed


def _required_month(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}", text) is None:
        raise StudyV2CoverageError(f"{label} must be YYYY-MM")
    try:
        date.fromisoformat(text + "-01")
    except ValueError as exc:
        raise StudyV2CoverageError(f"{label} must be a valid calendar month") from exc
    return text


def _validate_review_attestation(
    value: Mapping[str, Any] | None,
    *,
    expected_file_sha256: Mapping[str, str],
) -> dict[str, Any]:
    if value is None:
        return {
            "schema_version": None,
            "execution_semantics_verified": False,
            "tradability_fields_verified": False,
            "data_rights_verified": False,
            "official_calendar_verified": False,
            "reviewed_at": None,
            "reviewer_recorded": False,
            "sha256": None,
        }
    if not isinstance(value, Mapping):
        raise StudyV2CoverageError("review attestation must be a JSON object")
    if value.get("schema_version") != "stage2_data_review_attestation_v1":
        raise StudyV2CoverageError("unsupported review attestation schema")
    if (
        value.get("study_id") != "a-share-factor-timing-bias-decomposition-v2"
        or value.get("status") != "reviewed_pass"
    ):
        raise StudyV2CoverageError(
            "review attestation is not a completed Stage-2 review"
        )
    for key in (
        "execution_semantics_verified",
        "tradability_fields_verified",
        "data_rights_verified",
        "official_calendar_verified",
    ):
        if value.get(key) is not True:
            raise StudyV2CoverageError(f"review attestation {key} must be true")
    review_scope_cutoff_at = value.get("review_scope_cutoff_at")
    reviewed_at = value.get("reviewed_at")
    cutoff_time = _required_timezone_aware_datetime(
        review_scope_cutoff_at, "review attestation review_scope_cutoff_at"
    )
    reviewed_time = _required_timezone_aware_datetime(
        reviewed_at, "review attestation reviewed_at"
    )
    if cutoff_time > reviewed_time:
        raise StudyV2CoverageError("review attestation chronology is invalid")
    for key in ("reviewer", "reviewer_role", "reviewer_authority_basis"):
        if not isinstance(value.get(key), str) or len(value[key].strip()) < 4:
            raise StudyV2CoverageError(f"review attestation {key} is required")
    input_hashes = value.get("input_file_sha256")
    if not isinstance(input_hashes, Mapping) or dict(input_hashes) != dict(expected_file_sha256):
        raise StudyV2CoverageError("review attestation is not bound to the audited input files")
    evidence_hashes = value.get("evidence_sha256")
    if not isinstance(evidence_hashes, Mapping):
        raise StudyV2CoverageError("review attestation evidence hashes are required")
    for key in (
        "execution_semantics", "tradability_fields", "data_rights", "official_calendar"
    ):
        if not _is_sha256(evidence_hashes.get(key)):
            raise StudyV2CoverageError(f"review attestation {key} evidence hash is invalid")
    required_assertions = {
        "adjusted_close_return_semantics_and_corporate_action_handling_are_documented",
        "unadjusted_open_and_nonfill_semantics_are_not_claimed_by_the_ic_core",
        "amount_units_and_cutoff_timing_are_documented",
        "st_and_suspension_fields_are_non_degenerate_and_historically_effective",
        "licensed_local_analysis_is_permitted",
        "public_aggregate_outputs_metadata_and_hashes_are_permitted",
        "public_official_calendar_session_dates_are_permitted",
        "calendar_rows_are_unique_strictly_increasing_common_sse_szse_sessions",
        "calendar_covers_2009_01_through_2023_01_and_all_target_endpoints",
        "every_quote_date_is_a_calendar_member",
        "no_factor_ic_return_or_variant_ranking_was_reviewed",
    }
    assertions = value.get("review_assertions")
    if (
        not isinstance(assertions, Mapping)
        or set(assertions) != required_assertions
        or any(assertions[key] is not True for key in required_assertions)
    ):
        raise StudyV2CoverageError(
            "review attestation assertions have not all passed"
        )
    signature = value.get("signature")
    if (
        not isinstance(signature, Mapping)
        or signature.get("type") not in {
            "detached_digital_signature",
            "external_registry_attestation",
            "human_verified_evidence",
        }
        or not _is_sha256(signature.get("evidence_sha256"))
        or not isinstance(signature.get("signer_identity"), str)
        or len(signature["signer_identity"].strip()) < 4
    ):
        raise StudyV2CoverageError("review attestation signature is invalid")
    verification_uri = str(signature.get("verification_uri") or "")
    parsed_uri = urlparse(verification_uri)
    if parsed_uri.scheme != "https" or not parsed_uri.netloc:
        raise StudyV2CoverageError("review attestation verification URI is invalid")
    if signature["type"] == "human_verified_evidence" and signature.get(
        "trust_boundary"
    ) != "Identity and evidence authenticity require independent human verification.":
        raise StudyV2CoverageError(
            "review attestation must disclose the human-verification trust boundary"
        )
    canonical = json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "schema_version": "stage2_data_review_attestation_v1",
        "execution_semantics_verified": value["execution_semantics_verified"],
        "tradability_fields_verified": value["tradability_fields_verified"],
        "data_rights_verified": value["data_rights_verified"],
        "official_calendar_verified": value["official_calendar_verified"],
        "reviewed_at": reviewed_at,
        "reviewer_recorded": True,
        "sha256": hashlib.sha256(canonical).hexdigest(),
    }


def _required_timezone_aware_datetime(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise StudyV2CoverageError(f"{label} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StudyV2CoverageError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise StudyV2CoverageError(f"{label} must include a UTC offset")
    return parsed


def _audit_vintage_rows(raw_csv: bytes, fieldnames: Sequence[str]) -> dict[str, Any]:
    normalized = {name.strip().lower(): name for name in fieldnames}
    time_name = next(
        (normalized[name] for name in sorted(VINTAGE_TIME_COLUMNS) if name in normalized),
        None,
    )
    id_name = next(
        (normalized[name] for name in sorted(VINTAGE_ID_COLUMNS) if name in normalized),
        None,
    )
    if time_name is None or id_name is None:
        return {
            "fields_present": False,
            "complete_row_rate": 0.0,
            "versioned_symbol_period_count": 0,
        }
    total = 0
    complete = 0
    versions: dict[tuple[str, str], set[str]] = {}
    with io.StringIO(raw_csv.decode("utf-8-sig"), newline="") as handle:
        for row in csv.DictReader(handle):
            total += 1
            time_value = (row.get(time_name) or "").strip()
            version_value = (row.get(id_name) or "").strip()
            if not time_value or not version_value:
                continue
            _parse_date(time_value)
            complete += 1
            key = (
                (row.get("symbol") or "").strip(),
                (row.get("reportPeriodEnd") or "").strip(),
            )
            versions.setdefault(key, set()).add(version_value)
    rate = complete / total if total else 0.0
    versioned = sum(len(values) > 1 for values in versions.values())
    return {
        "fields_present": True,
        "complete_row_rate": round(rate, 10),
        "versioned_symbol_period_count": versioned,
    }


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value) is not None


def _raw_csv_bytes(value: Any, label: str) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise StudyV2CoverageError(f"{label} raw CSV must be bytes")
    return bytes(value)


def _normalized_input_names(value: Mapping[str, str] | None) -> dict[str, str]:
    supplied: Mapping[str, str] = (
        {
            "quotes": "quotes.csv",
            "stock_master": "stock_master.csv",
            "fundamentals": "fundamentals.csv",
            "official_calendar": "official_calendar.csv",
        }
        if value is None
        else value
    )
    if not isinstance(supplied, Mapping) or set(supplied) != set(INPUT_ROLES):
        raise StudyV2CoverageError(
            "input_names must contain exactly quotes, stock_master, fundamentals, "
            "and official_calendar"
        )
    normalized: dict[str, str] = {}
    for role in INPUT_ROLES:
        raw_name = supplied[role]
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise StudyV2CoverageError(f"input_names {role} must be a non-empty string")
        file_name = raw_name.strip().replace("\\", "/").rsplit("/", 1)[-1]
        if file_name in {"", ".", ".."}:
            raise StudyV2CoverageError(f"input_names {role} has no file name")
        normalized[role] = file_name
    return normalized


def _raw_file_identity(raw_csv: bytes, file_name: str) -> dict[str, Any]:
    return {
        "file_name": file_name,
        "size_bytes": len(raw_csv),
        "sha256": hashlib.sha256(raw_csv).hexdigest(),
    }


def _calendar_months(start: date, end: date) -> list[str]:
    months: list[str] = []
    year = start.year
    month = start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}-{month:02d}")
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
    return months


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _validate_fixed_design_arguments(
    *,
    minimum_history_years: Any,
    minimum_publish_date_rate: Any,
    minimum_monthly_observations: Any,
    minimum_symbols_per_month: Any,
    minimum_sessions_per_month: Any,
    analysis_start: Any,
    analysis_end: Any,
    required_quote_start: Any,
    required_quote_end: Any,
    required_fundamental_start: Any,
    required_fundamental_end: Any,
) -> None:
    integer_values = {
        "minimum_monthly_observations": minimum_monthly_observations,
        "minimum_symbols_per_month": minimum_symbols_per_month,
        "minimum_sessions_per_month": minimum_sessions_per_month,
    }
    numeric_values = {
        "minimum_history_years": minimum_history_years,
        "minimum_publish_date_rate": minimum_publish_date_rate,
    }
    date_values = {
        "analysis_start": analysis_start,
        "analysis_end": analysis_end,
        "required_quote_start": required_quote_start,
        "required_quote_end": required_quote_end,
        "required_fundamental_start": required_fundamental_start,
        "required_fundamental_end": required_fundamental_end,
    }
    normalized: dict[str, Any] = {}
    for key, candidate in integer_values.items():
        if not isinstance(candidate, int) or isinstance(candidate, bool):
            raise StudyV2CoverageError(
                f"{key} must equal the fixed design contract value"
            )
        normalized[key] = candidate
    for key, candidate in numeric_values.items():
        if not isinstance(candidate, (int, float)) or isinstance(candidate, bool):
            raise StudyV2CoverageError(
                f"{key} must equal the fixed design contract value"
            )
        normalized[key] = float(candidate)
    for key, candidate in date_values.items():
        normalized[key] = _required_date(candidate, key).isoformat()
    for key in (
        "maximum_fundamental_staleness_months",
        "required_official_calendar_first_month",
        "required_official_calendar_last_month",
    ):
        normalized[key] = FIXED_DESIGN_PARAMETERS[key]
    changed = sorted(
        key for key, expected in FIXED_DESIGN_PARAMETERS.items()
        if normalized.get(key) != expected
    )
    if changed:
        raise StudyV2CoverageError(
            "coverage audit arguments differ from the fixed design contract: "
            + ", ".join(changed)
        )


def _regular_file(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser().resolve(strict=False)
    if not path.is_file() or path.is_symlink():
        raise StudyV2CoverageError(f"{label} is not a regular file: {path}")
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quotes", required=True)
    parser.add_argument("--stock-master", required=True)
    parser.add_argument("--fundamentals", required=True)
    parser.add_argument("--official-calendar", required=True)
    parser.add_argument("--minimum-history-years", type=float, default=13.0)
    parser.add_argument("--minimum-publish-date-rate", type=float, default=0.95)
    parser.add_argument("--minimum-monthly-observations", type=int, default=156)
    parser.add_argument("--minimum-symbols-per-month", type=int, default=1000)
    parser.add_argument("--minimum-sessions-per-month", type=int, default=15)
    parser.add_argument("--analysis-start", default="2010-01-01")
    parser.add_argument("--analysis-end", default="2022-12-31")
    parser.add_argument("--required-quote-start", default="2009-01-01")
    parser.add_argument("--required-quote-end", default="2023-01-31")
    parser.add_argument("--required-fundamental-start", default="2009-01-01")
    parser.add_argument("--required-fundamental-end", default="2022-12-31")
    parser.add_argument("--review-attestation")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    attestation = None
    if args.review_attestation:
        attestation_path = _regular_file(args.review_attestation, "review attestation")
        try:
            attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StudyV2CoverageError("review attestation is not valid UTF-8 JSON") from exc
    report = audit_study_inputs(
        quotes_path=args.quotes,
        stock_master_path=args.stock_master,
        fundamentals_path=args.fundamentals,
        official_calendar_path=args.official_calendar,
        minimum_history_years=args.minimum_history_years,
        minimum_publish_date_rate=args.minimum_publish_date_rate,
        minimum_monthly_observations=args.minimum_monthly_observations,
        minimum_symbols_per_month=args.minimum_symbols_per_month,
        minimum_sessions_per_month=args.minimum_sessions_per_month,
        analysis_start=args.analysis_start,
        analysis_end=args.analysis_end,
        required_quote_start=args.required_quote_start,
        required_quote_end=args.required_quote_end,
        required_fundamental_start=args.required_fundamental_start,
        required_fundamental_end=args.required_fundamental_end,
        review_attestation=attestation,
    )
    write_coverage_report(report, args.output)
    print(
        "READY" if report["gates"]["ready_to_lock_stage2_plan"] else "BLOCKED",
        args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
