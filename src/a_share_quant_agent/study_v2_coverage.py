"""Private authoritative coverage audit for the Stage-2 factor study.

The audit reports field availability, time span, coverage rates, and file
identity without publishing local paths or row-level licensed data.  Its exact
hashes, byte sizes, and coverage metadata remain rights-controlled private
evidence.  A separately reviewed public-export command is not implemented.
This is a precondition check, not a replacement for the study runner's strict
input validation.
"""

from __future__ import annotations

import argparse
from calendar import monthrange
from collections.abc import Mapping as MappingABC, Set as SetABC
import csv
from datetime import date, datetime
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Any, Iterable, Iterator, Mapping, Sequence
from urllib.parse import urlparse

from .private_artifact_paths import (
    PrivateArtifactPathError,
    require_new_private_file_target,
    write_private_bytes_atomic_exclusive,
)


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
    "terminal_survivor_cutoff": "2023-01-31",
    "security_identifier_contract_id": (
        "provider_stable_exchange_qualified_security_identifier_with_"
        "reviewed_code_change_mapping_v1"
    ),
}
CSV_NORMALIZATION: dict[str, str] = {
    "blank_values": "strip_surrounding_whitespace_then_empty_is_null",
    "column_names": "case_sensitive_exact_header_names",
    "csv_dialect": "excel",
    "date_values": (
        "exact_YYYY-MM-DD_valid_calendar_date_and_pandas_nanosecond_safe_"
        "1677-09-22_through_2262-04-11"
    ),
    "encoding": "utf-8-sig",
    "logical_key_symbols": "strip_surrounding_whitespace_then_uppercase",
    "numeric_values": (
        "exact_ASCII_decimal_with_optional_sign_fraction_and_base10_exponent"
    ),
}
INPUT_ROLES = ("quotes", "stock_master", "fundamentals", "official_calendar")
PUBLIC_INPUT_FILE_NAMES = {
    "quotes": "quotes.csv",
    "stock_master": "stock_master.csv",
    "fundamentals": "fundamentals.csv",
    "official_calendar": "official_calendar.csv",
}
INPUT_ROLE_REASON_LABELS = {
    "quotes": "QUOTES",
    "stock_master": "STOCK_MASTER",
    "fundamentals": "FUNDAMENTALS",
    "official_calendar": "OFFICIAL_CALENDAR",
}

QUOTE_REQUIRED = {
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
}
STAGE2_CANONICAL_AMOUNT_UNIT = "CNY"
STAGE2_PRICE_ADJUSTMENT_METHOD = (
    "close_equals_close_raw_times_adjustment_factor"
)
STAGE2_PRICE_ADJUSTMENT_CONVENTION = (
    "provider_cumulative_backward_adjusted_hfq_no_rebasing"
)
STAGE2_PRICE_ADJUSTMENT_REL_TOLERANCE = 1e-12
STAGE2_PRICE_ADJUSTMENT_ABS_TOLERANCE = 1e-12
STAGE2_CLOSE_OBSERVATION_TYPES = frozenset(
    {"traded_close", "suspension_valuation"}
)
STAGE2_TERMINAL_SURVIVOR_CUTOFF = date(2023, 1, 31)
STAGE2_SECURITY_IDENTIFIER_CONTRACT_TOKEN = (
    "provider_stable_exchange_qualified_security_identifier_with_"
    "reviewed_code_change_mapping_v1"
)
MASTER_REQUIRED = {"symbol", "listDate", "delistDate", "listStatus", "stockType"}
FUNDAMENTAL_REQUIRED = {"symbol", "roeDiluted", "publishDate", "reportPeriodEnd"}
CALENDAR_REQUIRED = {"date"}
ACTIVE_LIST_STATUSES = frozenset({"ACTIVE", "LISTED", "L", "上市", "正常上市"})
DELISTED_LIST_STATUSES = frozenset(
    {"DELISTED", "TERMINATED", "D", "退市", "终止上市"}
)
VINTAGE_TIME_COLUMNS = {
    "asofdate", "as_of_date", "vintagedate", "vintage_date", "revisiondate",
    "revision_date", "as_of_or_vintage_timestamp",
}
VINTAGE_ID_COLUMNS = {
    "versionid", "version_id", "revisionid", "revision_id", "vintageid",
    "vintage_id", "version_or_revision_identifier",
}
NA_LIKE_TOKENS = frozenset(
    {
        "#n/a", "#n/a n/a", "#na", "-1.#ind", "-1.#qnan", "-nan", "1.#ind",
        "1.#qnan", "<na>", "n/a", "na", "nan", "none", "null",
    }
)
CANONICAL_DECIMAL_PATTERN = re.compile(
    r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
)
CANONICAL_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
CANONICAL_SYMBOL_PATTERN = re.compile(r"[0-9]{6}\.(?:SH|SZ)")
CANONICAL_DATE_MIN = date(1677, 9, 22)
CANONICAL_DATE_MAX = date(2262, 4, 11)
LOGICAL_KEY_IN_MEMORY_LIMIT = 100_000


class StudyV2CoverageError(RuntimeError):
    """Raised when an input cannot be audited safely."""


class _ExactLogicalKeyTracker:
    """Count exact duplicate keys with a bounded in-memory fast path.

    Once the fixed unique-key limit is reached, keys move to a temporary
    SQLite table with a BLOB primary key.  The length-prefixed encoding is
    collision-free for tuples of UTF-8 strings.  Temporary storage is always
    closed and removed by the context manager and its path is never reported.
    """

    def __init__(self, max_in_memory_keys: int = LOGICAL_KEY_IN_MEMORY_LIMIT) -> None:
        if not isinstance(max_in_memory_keys, int) or max_in_memory_keys < 1:
            raise StudyV2CoverageError("logical-key memory limit must be positive")
        self._max_in_memory_keys = max_in_memory_keys
        self._memory_keys: set[tuple[str, ...]] = set()
        self._temporary_directory: tempfile.TemporaryDirectory[str] | None = None
        self._connection: sqlite3.Connection | None = None

    @property
    def storage_backend(self) -> str:
        return "sqlite_spill" if self._connection is not None else "memory"

    def __enter__(self) -> _ExactLogicalKeyTracker:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        if self._temporary_directory is not None:
            self._temporary_directory.cleanup()
            self._temporary_directory = None
        self._memory_keys.clear()

    def add(self, key: tuple[str, ...]) -> bool:
        """Add ``key`` and return true exactly when it was already present."""

        if self._connection is None:
            if key in self._memory_keys:
                return True
            self._memory_keys.add(key)
            if len(self._memory_keys) >= self._max_in_memory_keys:
                self._spill_to_sqlite()
            return False
        encoded = _encode_logical_key(key)
        try:
            before = self._connection.total_changes
            self._connection.execute(
                "INSERT OR IGNORE INTO logical_keys(encoded_key) VALUES (?)",
                (sqlite3.Binary(encoded),),
            )
            return self._connection.total_changes == before
        except sqlite3.Error:
            raise StudyV2CoverageError(
                "temporary exact logical-key index failed"
            ) from None

    def _spill_to_sqlite(self) -> None:
        try:
            self._temporary_directory = tempfile.TemporaryDirectory(
                prefix="stage2-coverage-logical-keys-"
            )
            database_path = Path(self._temporary_directory.name) / "keys.sqlite3"
            self._connection = sqlite3.connect(database_path)
            self._connection.execute("PRAGMA journal_mode=OFF")
            self._connection.execute("PRAGMA synchronous=OFF")
            self._connection.execute(
                "CREATE TABLE logical_keys "
                "(encoded_key BLOB PRIMARY KEY) WITHOUT ROWID"
            )
            self._connection.executemany(
                "INSERT INTO logical_keys(encoded_key) VALUES (?)",
                (
                    (sqlite3.Binary(_encode_logical_key(key)),)
                    for key in self._memory_keys
                ),
            )
            self._memory_keys.clear()
        except (OSError, sqlite3.Error):
            self.close()
            raise StudyV2CoverageError(
                "temporary exact logical-key index failed"
            ) from None


def _encode_logical_key(key: tuple[str, ...]) -> bytes:
    encoded = bytearray()
    for component in key:
        payload = component.encode("utf-8")
        encoded.extend(len(payload).to_bytes(8, byteorder="big", signed=False))
        encoded.extend(payload)
    return bytes(encoded)


class _SymbolBitmapView(SetABC[str]):
    """Read-only set view over one date's compact symbol bitmap."""

    def __init__(
        self,
        *,
        mask: int,
        symbol_to_bit: Mapping[str, int],
        symbols_by_bit: Sequence[str],
    ) -> None:
        self._mask = mask
        self._symbol_to_bit = symbol_to_bit
        self._symbols_by_bit = symbols_by_bit

    def __contains__(self, value: object) -> bool:
        if not isinstance(value, str):
            return False
        bit = self._symbol_to_bit.get(value)
        return bit is not None and bool(self._mask & (1 << bit))

    def __iter__(self) -> Iterator[str]:
        remaining = self._mask
        while remaining:
            least_significant_bit = remaining & -remaining
            position = least_significant_bit.bit_length() - 1
            yield self._symbols_by_bit[position]
            remaining ^= least_significant_bit

    def __len__(self) -> int:
        return self._mask.bit_count()

    def __and__(self, other: Iterable[str]) -> set[str]:
        return {symbol for symbol in other if symbol in self}

    def __rand__(self, other: Iterable[str]) -> set[str]:
        return self.__and__(other)


class _SymbolBitmapIndex(MappingABC[date, SetABC[str]]):
    """Map dates to lazy set views backed by one integer bitmap per date."""

    def __init__(
        self,
        *,
        symbol_to_bit: Mapping[str, int],
        symbols_by_bit: Sequence[str],
        date_masks: Mapping[date, int],
    ) -> None:
        self._symbol_to_bit = dict(symbol_to_bit)
        self._symbols_by_bit = tuple(symbols_by_bit)
        self._date_masks = dict(date_masks)

    def __getitem__(self, key: date) -> SetABC[str]:
        return _SymbolBitmapView(
            mask=self._date_masks[key],
            symbol_to_bit=self._symbol_to_bit,
            symbols_by_bit=self._symbols_by_bit,
        )

    def __iter__(self) -> Iterator[date]:
        return iter(self._date_masks)

    def __len__(self) -> int:
        return len(self._date_masks)


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
    Operator-supplied basenames are never persisted: ``input_names`` remains
    accepted only for compatibility and structure validation, while the
    report always uses fixed public logical names.
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
    strict_a_share_master_lifecycles = _strict_a_share_master_lifecycles(
        raw_inputs["stock_master"]
    )
    eligible_a_share_symbols = quote_symbols & strict_a_share_master_symbols
    master["strict_a_share_symbol_count"] = len(strict_a_share_master_symbols)
    quotes["eligible_symbol_count"] = len(eligible_a_share_symbols)
    quotes["eligible_symbol_count_basis"] = (
        "first official session per target month intersected with the closed "
        "listDate-to-delistDate strict A-share lifecycle"
    )
    for row in quotes["monthly_coverage"]:
        signal_date = rebalance_date_by_month.get(row["month"])
        active_symbols = _active_strict_a_share_symbols(
            strict_a_share_master_lifecycles, signal_date
        )
        row["active_strict_a_share_symbol_count"] = len(active_symbols)
        row["eligible_symbol_count"] = len(
            monthly_rebalance_quote_symbols.get(row["month"], set()) & active_symbols
        )
    expected_input_identity = _expected_review_input_identity(
        identities=identities,
        quotes=quotes,
        master=master,
        fundamentals=fundamentals,
        official_calendar=official_calendar,
    )
    attestation = _validate_review_attestation(
        review_attestation,
        expected_file_sha256={
            role: identities[role]["sha256"] for role in INPUT_ROLES
        },
        expected_input_identity=expected_input_identity,
    )
    parameters = dict(FIXED_DESIGN_PARAMETERS)
    if (
        parameters["terminal_survivor_cutoff"]
        != parameters["required_quote_end"]
        or parameters["terminal_survivor_cutoff"]
        != STAGE2_TERMINAL_SURVIVOR_CUTOFF.isoformat()
        or parameters["security_identifier_contract_id"]
        != STAGE2_SECURITY_IDENTIFIER_CONTRACT_TOKEN
    ):
        raise StudyV2CoverageError(
            "fixed terminal-survivor or security-identifier contract drifted"
        )
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
    signal_session_candidates: dict[date, set[str]] = {}
    for month in expected_months:
        signal_session = rebalance_date_by_month.get(month)
        if signal_session is None:
            continue
        signal_session_candidates[signal_session] = (
            _active_strict_a_share_symbols(
                strict_a_share_master_lifecycles, signal_session
            )
            & dated_quote_symbols.get(signal_session, set())
        )
    quotes.update(
        _signal_session_close_observation_coverage(
            raw_inputs["quotes"],
            signal_session_candidates=signal_session_candidates,
            source_name=str(identities["quotes"]["file_name"]),
        )
    )
    complete_quote_contract_symbols_by_month: dict[str, set[str]] = {}
    quote_contract_coverage = _quote_contract_monthly_coverage(
        dated_quote_symbols=dated_quote_symbols,
        official_sessions=tuple(official_session_dates),
        expected_months=expected_months,
        eligible_master_symbols=strict_a_share_master_symbols,
        master_lifecycles=strict_a_share_master_lifecycles,
        minimum_symbols=parameters["minimum_symbols_per_month"],
        complete_symbols_by_month=complete_quote_contract_symbols_by_month,
    )
    quotes["per_symbol_quote_contract_monthly_coverage"] = (
        quote_contract_coverage["monthly_coverage"]
    )
    quotes["per_symbol_quote_contract_basis"] = (
        "active strict A-share identifiers (closed listDate-to-delistDate interval) "
        "with identifier/date presence on the exact official sessions required for "
        "the contiguous t-60 through t momentum history, 20-session volatility "
        "and amount histories, and "
        "t/t+1/t+20/t+21 endpoints; no prices, returns, signals, or ranks inspected"
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
        and official_calendar["invalid_date_format_counts"].get("date", 0) == 0
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
    quote_dates = set(dated_quote_symbols)
    non_calendar_quote_dates = quote_dates - calendar_dates
    quote_dates_are_official_sessions = not non_calendar_quote_dates
    official_quote_dates = quote_dates & calendar_dates
    official_quote_session_count_by_month: dict[str, int] = {}
    for quote_date in official_quote_dates:
        month = quote_date.strftime("%Y-%m")
        official_quote_session_count_by_month[month] = (
            official_quote_session_count_by_month.get(month, 0) + 1
        )
    for row in quotes["monthly_coverage"]:
        row["official_session_count"] = official_quote_session_count_by_month.get(
            row["month"], 0
        )
    quotes["minimum_official_sessions_per_observed_month"] = min(
        (row["official_session_count"] for row in quotes["monthly_coverage"]),
        default=0,
    )
    quotes["official_session_count_basis"] = (
        "distinct quote dates intersected with the bound official calendar"
    )
    monthly_by_id = {
        row["month"]: row for row in official_calendar["monthly_coverage"]
    }
    target_months = [monthly_by_id[month] for month in expected_months if month in monthly_by_id]
    missing_analysis_months = [month for month in expected_months if month not in monthly_by_id]
    insufficient_official_quote_session_months = [
        {
            "month": month,
            "official_quote_session_count": official_quote_session_count_by_month.get(
                month, 0
            ),
        }
        for month in expected_months
        if official_quote_session_count_by_month.get(month, 0)
        < parameters["minimum_sessions_per_month"]
    ]
    full_month_ids = {
        month
        for month in expected_months
        if official_quote_session_count_by_month.get(month, 0)
        >= parameters["minimum_sessions_per_month"]
    }
    full_months = [
        row
        for row in target_months
        if row["month"] in full_month_ids
    ]
    quote_monthly_by_id = {row["month"]: row for row in quotes["monthly_coverage"]}
    symbol_eligible_month_ids = [
        month
        for month in expected_months
        if quote_monthly_by_id.get(month, {}).get("eligible_symbol_count", 0)
        >= parameters["minimum_symbols_per_month"]
    ]
    complete_quote_contract_month_ids = {
        row["month"]
        for row in quote_contract_coverage["monthly_coverage"]
        if row["complete_quote_contract_symbol_count"]
        >= parameters["minimum_symbols_per_month"]
    }
    eligible_months = [
        row
        for row in full_months
        if row["month"] in complete_quote_contract_month_ids
    ]
    minimum_monthly_observations_met = len(target_months) == len(expected_months)
    minimum_sessions_per_month_met = len(full_month_ids) == len(expected_months)
    minimum_symbols_per_month_met = bool(
        quote_contract_coverage["complete_quote_contract_coverage_met"]
    )
    fundamental_coverage = _fundamental_monthly_coverage(
        raw_csv=raw_inputs["fundamentals"],
        expected_months=expected_months,
        official_sessions=calendar_dates,
        monthly_quote_symbols=monthly_rebalance_quote_symbols,
        eligible_master_symbols=strict_a_share_master_symbols,
        eligible_universe_symbols=eligible_a_share_symbols,
        complete_quote_contract_symbols_by_month=(
            complete_quote_contract_symbols_by_month
        ),
        master_lifecycles=strict_a_share_master_lifecycles,
        required_start=required_fundamental_start_date,
        required_end=required_fundamental_end_date,
        maximum_staleness_months=parameters[
            "maximum_fundamental_staleness_months"
        ],
    )
    complete_quote_contract_symbols_by_month.clear()
    fundamentals.update(fundamental_coverage)
    publication_coverage_met = (
        fundamentals["eligible_interval_publish_date_non_null_rate"]
        >= parameters["minimum_publish_date_rate"]
    )
    quote_numeric_integrity_met = bool(quotes["numeric_integrity_verified"])
    quote_boolean_integrity_met = bool(quotes["boolean_integrity_verified"])
    close_observation_contract_met = bool(
        quotes["close_observation_contract_verified"]
    )
    price_adjustment_contract_met = bool(
        quotes["price_adjustment_contract_verified"]
    )
    canonical_amount_unit_met = bool(quotes["canonical_amount_unit_verified"])
    signal_session_close_observation_types_non_degenerate = bool(
        quotes["signal_session_close_observation_types_non_degenerate"]
    )
    fundamental_publication_order_integrity_met = (
        fundamentals[
            "eligible_scope_publication_before_report_period_end_row_count"
        ]
        == 0
    )
    global_fundamental_publication_order_integrity_met = (
        fundamentals[
            "global_publication_before_report_period_end_row_count"
        ]
        == 0
    )
    fundamental_roe_numeric_integrity_met = (
        fundamentals["invalid_roe_diluted_numeric_row_count"] == 0
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
    fundamental_complete_quote_contract_support_met = all(
        row["nonstale_complete_contract_fundamental_symbol_count"]
        >= parameters["minimum_symbols_per_month"]
        for row in fundamentals["monthly_coverage"]
    )
    target_fundamental_interval_available = bool(
        fundamentals["required_columns_present"]
        and publication_coverage_met
        and fundamental_target_month_continuity_met
        and fundamental_eligible_symbol_intersection_met
        and fundamental_staleness_coverage_met
        and fundamental_complete_quote_contract_support_met
        and fundamental_publication_order_integrity_met
        and fundamental_roe_numeric_integrity_met
    )
    membership_available = bool(master["membership_integrity_verified"])
    execution_columns_present = quotes["required_columns_present"]
    execution_semantics_verified = bool(
        execution_columns_present and attestation["execution_semantics_verified"]
    )
    tradability_fields_verified = bool(
        execution_columns_present and attestation["tradability_fields_verified"]
    )
    exact_endpoint_resolution_semantics_verified = bool(
        execution_columns_present
        and attestation["exact_endpoint_resolution_semantics_verified"]
    )
    suspension_valuation_semantics_verified = bool(
        execution_columns_present
        and attestation["suspension_valuation_semantics_verified"]
    )
    price_adjustment_semantics_verified = bool(
        price_adjustment_contract_met
        and attestation["price_adjustment_semantics_verified"]
    )
    amount_unit_normalization_semantics_verified = bool(
        canonical_amount_unit_met
        and attestation["amount_unit_normalization_semantics_verified"]
    )
    endpoint_reason_ledger_rights_verified = bool(
        attestation["endpoint_reason_ledger_rights_verified"]
    )
    historical_membership_completeness_verified = bool(
        attestation["historical_membership_completeness_verified"]
    )
    terminal_survivor_comparator_verified = bool(
        membership_available
        and attestation["terminal_survivor_comparator_verified"]
    )
    fundamental_publication_semantics_verified = bool(
        attestation["fundamental_publication_semantics_verified"]
    )
    data_rights_verified = bool(attestation["data_rights_verified"])
    official_calendar_review_verified = bool(
        attestation["official_calendar_verified"]
    )
    no_empty_inputs = all(
        section["row_count"] > 0
        for section in (quotes, master, fundamentals, official_calendar)
    )
    sections_by_role = {
        "quotes": quotes,
        "stock_master": master,
        "fundamentals": fundamentals,
        "official_calendar": official_calendar,
    }
    csv_row_width_integrity_met = all(
        section["malformed_csv_row_width_count"] == 0
        for section in sections_by_role.values()
    )
    logical_key_uniqueness_met = all(
        section["duplicate_logical_key_row_count"] == 0
        for section in sections_by_role.values()
    )
    input_structural_integrity_met = (
        csv_row_width_integrity_met and logical_key_uniqueness_met
    )
    required_non_null_fields = {
        "quotes": (
            "date", "symbol", "close_raw", "adjustment_factor", "close",
            "price_adjustment_method", "price_adjustment_convention",
            "close_observation_type", "amount", "amount_unit", "is_st",
            "is_suspended",
        ),
        "stock_master": ("symbol", "listDate", "listStatus", "stockType"),
        "fundamentals": ("symbol", "roeDiluted", "reportPeriodEnd"),
        "official_calendar": ("date",),
    }
    required_field_non_null_integrity_met = all(
        section["missing_value_counts"].get(field, section["row_count"]) == 0
        for role, section in sections_by_role.items()
        for field in required_non_null_fields[role]
    )
    canonical_symbol_integrity_met = all(
        sections_by_role[role]["canonical_symbol_integrity_verified"]
        for role in ("quotes", "stock_master", "fundamentals")
    )
    security_identifier_contract_verified = bool(
        attestation["security_identifier_semantics_verified"]
        and canonical_symbol_integrity_met
    )
    canonical_date_format_integrity_met = all(
        invalid_count == 0
        for section in sections_by_role.values()
        for invalid_count in section["invalid_date_format_counts"].values()
    )
    ready = all(
        (
            minimum_history_met,
            target_quote_interval_available,
            calendar_integrity_verified,
            target_calendar_interval_available,
            quote_dates_are_official_sessions,
            quote_numeric_integrity_met,
            quote_boolean_integrity_met,
            close_observation_contract_met,
            price_adjustment_contract_met,
            canonical_amount_unit_met,
            signal_session_close_observation_types_non_degenerate,
            target_fundamental_interval_available,
            minimum_monthly_observations_met,
            minimum_sessions_per_month_met,
            minimum_symbols_per_month_met,
            quote_contract_coverage["required_session_geometry_coverage_met"],
            quote_contract_coverage["momentum_60d_history_coverage_met"],
            quote_contract_coverage["low_volatility_20d_history_coverage_met"],
            quote_contract_coverage["amount_20d_history_coverage_met"],
            quote_contract_coverage["exact_endpoint_coverage_met"],
            quote_contract_coverage[
                "all_signal_session_candidates_have_exact_endpoints"
            ],
            quote_contract_coverage["complete_quote_contract_coverage_met"],
            publication_coverage_met,
            fundamental_publication_order_integrity_met,
            global_fundamental_publication_order_integrity_met,
            fundamental_roe_numeric_integrity_met,
            fundamental_complete_quote_contract_support_met,
            membership_available,
            terminal_survivor_comparator_verified,
            security_identifier_contract_verified,
            execution_columns_present,
            execution_semantics_verified,
            tradability_fields_verified,
            exact_endpoint_resolution_semantics_verified,
            suspension_valuation_semantics_verified,
            price_adjustment_semantics_verified,
            amount_unit_normalization_semantics_verified,
            endpoint_reason_ledger_rights_verified,
            historical_membership_completeness_verified,
            fundamental_publication_semantics_verified,
            data_rights_verified,
            official_calendar_review_verified,
            fundamentals["required_columns_present"],
            no_empty_inputs,
            input_structural_integrity_met,
            required_field_non_null_integrity_met,
            canonical_date_format_integrity_met,
            canonical_symbol_integrity_met,
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
    if quotes["close_blank_row_count"]:
        reasons.append("QUOTE_CLOSE_BLANK")
    if quotes["close_non_numeric_or_non_finite_row_count"]:
        reasons.append("QUOTE_CLOSE_NON_NUMERIC_OR_NON_FINITE")
    if quotes["close_invalid_canonical_numeric_format_row_count"]:
        reasons.append("QUOTE_CLOSE_INVALID_CANONICAL_NUMERIC_FORMAT")
    if quotes["close_non_finite_row_count"]:
        reasons.append("QUOTE_CLOSE_NON_FINITE")
    if quotes["close_non_positive_row_count"]:
        reasons.append("QUOTE_CLOSE_NON_POSITIVE")
    if quotes["amount_blank_row_count"]:
        reasons.append("QUOTE_AMOUNT_BLANK")
    if quotes["amount_non_numeric_or_non_finite_row_count"]:
        reasons.append("QUOTE_AMOUNT_NON_NUMERIC_OR_NON_FINITE")
    if quotes["amount_invalid_canonical_numeric_format_row_count"]:
        reasons.append("QUOTE_AMOUNT_INVALID_CANONICAL_NUMERIC_FORMAT")
    if quotes["amount_non_finite_row_count"]:
        reasons.append("QUOTE_AMOUNT_NON_FINITE")
    if quotes["amount_negative_row_count"]:
        reasons.append("QUOTE_AMOUNT_NEGATIVE")
    if quotes["amount_unit_blank_row_count"]:
        reasons.append("QUOTE_AMOUNT_UNIT_BLANK")
    if quotes["amount_unit_non_cny_row_count"]:
        reasons.append("QUOTE_AMOUNT_UNIT_NOT_EXACT_CNY")
    if not canonical_amount_unit_met:
        reasons.append("QUOTE_AMOUNT_NOT_CANONICAL_CNY")
    for field, label in (
        ("is_st", "QUOTE_IS_ST"),
        ("is_suspended", "QUOTE_IS_SUSPENDED"),
    ):
        if quotes[f"{field}_blank_row_count"]:
            reasons.append(f"{label}_BLANK")
        if quotes[f"{field}_invalid_boolean_row_count"]:
            reasons.append(f"{label}_INVALID_BOOLEAN")
        if not quotes[f"{field}_non_degenerate"]:
            reasons.append(f"{label}_DEGENERATE")
    if quotes["close_observation_type_blank_row_count"]:
        reasons.append("QUOTE_CLOSE_OBSERVATION_TYPE_BLANK")
    if quotes["close_observation_type_invalid_row_count"]:
        reasons.append("QUOTE_CLOSE_OBSERVATION_TYPE_INVALID")
    if quotes["close_observation_type_suspension_mismatch_row_count"]:
        reasons.append("QUOTE_CLOSE_OBSERVATION_SUSPENSION_MISMATCH")
    if not close_observation_contract_met:
        reasons.append("CLOSE_OBSERVATION_CONTRACT_NOT_MET")
    for field, label in (
        ("close_raw", "QUOTE_CLOSE_RAW"),
        ("adjustment_factor", "QUOTE_ADJUSTMENT_FACTOR"),
    ):
        if quotes[f"{field}_blank_row_count"]:
            reasons.append(f"{label}_BLANK")
        if quotes[f"{field}_invalid_row_count"]:
            reasons.append(f"{label}_INVALID")
        if quotes[f"{field}_non_positive_row_count"]:
            reasons.append(f"{label}_NON_POSITIVE")
    if quotes["price_adjustment_method_blank_row_count"]:
        reasons.append("QUOTE_PRICE_ADJUSTMENT_METHOD_BLANK")
    if quotes["price_adjustment_method_invalid_row_count"]:
        reasons.append("QUOTE_PRICE_ADJUSTMENT_METHOD_INVALID")
    if quotes["price_adjustment_convention_blank_row_count"]:
        reasons.append("QUOTE_PRICE_ADJUSTMENT_CONVENTION_BLANK")
    if quotes["price_adjustment_convention_invalid_row_count"]:
        reasons.append("QUOTE_PRICE_ADJUSTMENT_CONVENTION_INVALID")
    if quotes["price_adjustment_formula_uncheckable_row_count"]:
        reasons.append("QUOTE_PRICE_ADJUSTMENT_FORMULA_UNCHECKABLE")
    if quotes["price_adjustment_formula_mismatch_row_count"]:
        reasons.append("QUOTE_PRICE_ADJUSTMENT_FORMULA_MISMATCH")
    if not price_adjustment_contract_met:
        reasons.append("PRICE_ADJUSTMENT_CONTRACT_NOT_MET")
    if not signal_session_close_observation_types_non_degenerate:
        reasons.append("SIGNAL_SESSION_CLOSE_OBSERVATION_TYPES_DEGENERATE")
    if not target_fundamental_interval_available:
        reasons.append("TARGET_FUNDAMENTAL_INTERVAL_UNAVAILABLE")
    if not fundamental_target_month_continuity_met:
        reasons.append("INCOMPLETE_FUNDAMENTAL_TARGET_MONTH_CONTINUITY")
    if not fundamental_eligible_symbol_intersection_met:
        reasons.append("INSUFFICIENT_FUNDAMENTAL_ELIGIBLE_SYMBOL_COVERAGE")
    if not fundamental_staleness_coverage_met:
        reasons.append("INSUFFICIENT_NONSTALE_FUNDAMENTAL_COVERAGE")
    if not fundamental_complete_quote_contract_support_met:
        reasons.append("INSUFFICIENT_COMPLETE_QUOTE_FUNDAMENTAL_JOINT_SUPPORT")
    if not fundamental_publication_order_integrity_met:
        reasons.append("FUNDAMENTAL_PUBLICATION_BEFORE_REPORT_PERIOD_END")
    if not global_fundamental_publication_order_integrity_met:
        reasons.append(
            "GLOBAL_FUNDAMENTAL_PUBLICATION_BEFORE_REPORT_PERIOD_END"
        )
    if not fundamental_roe_numeric_integrity_met:
        reasons.append("FUNDAMENTAL_ROE_DILUTED_NON_NUMERIC_OR_NON_FINITE")
    if fundamentals["invalid_roe_diluted_numeric_format_row_count"]:
        reasons.append("FUNDAMENTAL_ROE_DILUTED_INVALID_CANONICAL_NUMERIC_FORMAT")
    if fundamentals["non_finite_roe_diluted_row_count"]:
        reasons.append("FUNDAMENTAL_ROE_DILUTED_NON_FINITE")
    if not minimum_monthly_observations_met:
        reasons.append("INSUFFICIENT_MONTHLY_COVERAGE")
    if not minimum_sessions_per_month_met:
        reasons.append("INSUFFICIENT_MONTHLY_SESSION_COVERAGE")
    if not minimum_symbols_per_month_met:
        reasons.append("INSUFFICIENT_MONTHLY_SYMBOL_COVERAGE")
    if not quote_contract_coverage["required_session_geometry_coverage_met"]:
        reasons.append("REQUIRED_QUOTE_SESSION_GEOMETRY_UNAVAILABLE")
    if not quote_contract_coverage["momentum_60d_history_coverage_met"]:
        reasons.append("INSUFFICIENT_MOMENTUM_60D_HISTORY_COVERAGE")
    if not quote_contract_coverage["low_volatility_20d_history_coverage_met"]:
        reasons.append("INSUFFICIENT_LOW_VOLATILITY_20D_HISTORY_COVERAGE")
    if not quote_contract_coverage["amount_20d_history_coverage_met"]:
        reasons.append("INSUFFICIENT_AMOUNT_20D_HISTORY_COVERAGE")
    if not quote_contract_coverage["exact_endpoint_coverage_met"]:
        reasons.append("INSUFFICIENT_EXACT_ENDPOINT_QUOTE_COVERAGE")
    if not quote_contract_coverage[
        "all_signal_session_candidates_have_exact_endpoints"
    ]:
        reasons.append(
            "INCOMPLETE_EXACT_ENDPOINT_COVERAGE_FOR_SIGNAL_CANDIDATES"
        )
    if not quote_contract_coverage["complete_quote_contract_coverage_met"]:
        reasons.append("INSUFFICIENT_COMPLETE_PER_SYMBOL_QUOTE_COVERAGE")
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
    if not exact_endpoint_resolution_semantics_verified:
        reasons.append("EXACT_ENDPOINT_SEMANTICS_NOT_VERIFIED")
    if not suspension_valuation_semantics_verified:
        reasons.append("SUSPENSION_VALUATION_SEMANTICS_NOT_VERIFIED")
    if not price_adjustment_semantics_verified:
        reasons.append("PRICE_ADJUSTMENT_SEMANTICS_NOT_VERIFIED")
    if not amount_unit_normalization_semantics_verified:
        reasons.append("AMOUNT_UNIT_NORMALIZATION_SEMANTICS_NOT_VERIFIED")
    if not endpoint_reason_ledger_rights_verified:
        reasons.append("ENDPOINT_LEDGER_RIGHTS_NOT_VERIFIED")
    if not historical_membership_completeness_verified:
        reasons.append("HISTORICAL_MEMBERSHIP_COMPLETENESS_NOT_VERIFIED")
    if not terminal_survivor_comparator_verified:
        reasons.append("TERMINAL_SURVIVOR_COMPARATOR_NOT_VERIFIED")
    if not security_identifier_contract_verified:
        reasons.append("SECURITY_IDENTIFIER_CONTRACT_NOT_VERIFIED")
    if not fundamental_publication_semantics_verified:
        reasons.append("FUNDAMENTAL_PUBLICATION_SEMANTICS_NOT_VERIFIED")
    if not data_rights_verified:
        reasons.append("DATA_RIGHTS_NOT_VERIFIED")
    if not official_calendar_review_verified:
        reasons.append("OFFICIAL_CALENDAR_NOT_REVIEWED")
    if not fundamentals["required_columns_present"]:
        reasons.append("MISSING_FUNDAMENTAL_FIELDS")
    if not no_empty_inputs:
        reasons.append("EMPTY_INPUT")
    completeness_reason_fields = {
        "quotes": {"date": "QUOTE_DATE", "symbol": "QUOTE_SYMBOL"},
        "stock_master": {
            "symbol": "STOCK_MASTER_SYMBOL",
            "listDate": "STOCK_MASTER_LIST_DATE",
            "listStatus": "STOCK_MASTER_LIST_STATUS",
            "stockType": "STOCK_MASTER_STOCK_TYPE",
        },
        "fundamentals": {
            "symbol": "FUNDAMENTAL_SYMBOL",
            "roeDiluted": "FUNDAMENTAL_ROE_DILUTED",
            "reportPeriodEnd": "FUNDAMENTAL_REPORT_PERIOD_END",
        },
        "official_calendar": {"date": "OFFICIAL_CALENDAR_DATE"},
    }
    for role, fields in completeness_reason_fields.items():
        section = sections_by_role[role]
        for field, label in fields.items():
            if section["blank_value_counts"].get(field, section["row_count"]):
                reasons.append(f"{label}_BLANK")
            if section["na_like_value_counts"].get(field, 0):
                reasons.append(f"{label}_NA_LIKE")
    for role, reason_label in (
        ("quotes", "QUOTE_SYMBOL"),
        ("stock_master", "STOCK_MASTER_SYMBOL"),
        ("fundamentals", "FUNDAMENTAL_SYMBOL"),
    ):
        section = sections_by_role[role]
        if section["symbol_invalid_canonical_format_row_count"]:
            reasons.append(f"{reason_label}_INVALID_CANONICAL_FORMAT")
    canonical_date_reason_fields = {
        "quotes": {"date": "QUOTE_DATE"},
        "stock_master": {
            "listDate": "STOCK_MASTER_LIST_DATE",
            "delistDate": "STOCK_MASTER_DELIST_DATE",
        },
        "fundamentals": {
            "publishDate": "FUNDAMENTAL_PUBLISH_DATE",
            "reportPeriodEnd": "FUNDAMENTAL_REPORT_PERIOD_END",
        },
        "official_calendar": {"date": "OFFICIAL_CALENDAR_DATE"},
    }
    for role, fields in canonical_date_reason_fields.items():
        section = sections_by_role[role]
        for field, label in fields.items():
            if section["invalid_date_format_counts"].get(field, 0):
                reasons.append(f"{label}_INVALID_CANONICAL_DATE")
    for role in INPUT_ROLES:
        section = sections_by_role[role]
        reason_label = INPUT_ROLE_REASON_LABELS[role]
        if section["malformed_csv_row_width_count"]:
            reasons.append(f"MALFORMED_{reason_label}_CSV_ROW_WIDTH")
        if section["duplicate_logical_key_row_count"]:
            reasons.append(f"DUPLICATE_{reason_label}_LOGICAL_KEY")

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
            "quote_numeric_integrity_met": quote_numeric_integrity_met,
            "quote_boolean_integrity_met": quote_boolean_integrity_met,
            "close_observation_contract_met": close_observation_contract_met,
            "price_adjustment_contract_met": price_adjustment_contract_met,
            "canonical_amount_unit_met": canonical_amount_unit_met,
            "signal_session_close_observation_types_non_degenerate": (
                signal_session_close_observation_types_non_degenerate
            ),
            "target_fundamental_interval_available": target_fundamental_interval_available,
            "fundamental_interval_basis": (
                "first official session per target month; publishDate strictly before "
                "that session; the same identifiers must satisfy the complete quote "
                "contract and the closed listDate-to-delistDate interval "
                "(delistDate inclusive); "
                "reportPeriodEnd no more than 18 calendar months stale; publication "
                "dates before reportPeriodEnd block readiness"
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
            "fundamental_complete_quote_contract_support_met": (
                fundamental_complete_quote_contract_support_met
            ),
            "fundamental_publication_order_integrity_met": (
                fundamental_publication_order_integrity_met
            ),
            "global_fundamental_publication_order_integrity_met": (
                global_fundamental_publication_order_integrity_met
            ),
            "fundamental_roe_numeric_integrity_met": (
                fundamental_roe_numeric_integrity_met
            ),
            "expected_analysis_month_count": len(expected_months),
            "target_observed_month_count": len(target_months),
            "missing_analysis_months": missing_analysis_months,
            "full_month_count": len(full_months),
            "minimum_official_quote_sessions_per_target_month": min(
                (
                    official_quote_session_count_by_month.get(month, 0)
                    for month in expected_months
                ),
                default=0,
            ),
            "insufficient_official_quote_session_months": (
                insufficient_official_quote_session_months
            ),
            "monthly_session_coverage_basis": (
                "distinct quote dates that are members of the bound official calendar"
            ),
            "eligible_a_share_symbol_count": len(eligible_a_share_symbols),
            "rebalance_symbol_eligible_month_count": len(symbol_eligible_month_ids),
            "symbol_eligible_month_count": len(complete_quote_contract_month_ids),
            "eligible_month_count": len(eligible_months),
            "minimum_monthly_observations_met": minimum_monthly_observations_met,
            "minimum_sessions_per_month_met": minimum_sessions_per_month_met,
            "minimum_symbols_per_month_met": minimum_symbols_per_month_met,
            "minimum_symbols_per_month_basis": (
                "same strict A-share identifiers satisfy the complete exact-session "
                "quote contract in each target month"
            ),
            "required_session_geometry_coverage_met": quote_contract_coverage[
                "required_session_geometry_coverage_met"
            ],
            "momentum_60d_history_coverage_met": quote_contract_coverage[
                "momentum_60d_history_coverage_met"
            ],
            "low_volatility_20d_history_coverage_met": quote_contract_coverage[
                "low_volatility_20d_history_coverage_met"
            ],
            "amount_20d_history_coverage_met": quote_contract_coverage[
                "amount_20d_history_coverage_met"
            ],
            "exact_endpoint_coverage_met": quote_contract_coverage[
                "exact_endpoint_coverage_met"
            ],
            "all_signal_session_candidates_have_exact_endpoints": (
                quote_contract_coverage[
                    "all_signal_session_candidates_have_exact_endpoints"
                ]
            ),
            "complete_quote_contract_coverage_met": quote_contract_coverage[
                "complete_quote_contract_coverage_met"
            ],
            "minimum_momentum_60d_history_symbol_count": quote_contract_coverage[
                "minimum_momentum_60d_history_symbol_count"
            ],
            "minimum_low_volatility_20d_history_symbol_count": (
                quote_contract_coverage[
                    "minimum_low_volatility_20d_history_symbol_count"
                ]
            ),
            "minimum_amount_20d_history_symbol_count": quote_contract_coverage[
                "minimum_amount_20d_history_symbol_count"
            ],
            "minimum_exact_endpoint_symbol_count": quote_contract_coverage[
                "minimum_exact_endpoint_symbol_count"
            ],
            "minimum_complete_quote_contract_symbol_count": (
                quote_contract_coverage[
                    "minimum_complete_quote_contract_symbol_count"
                ]
            ),
            "insufficient_complete_quote_contract_months": (
                quote_contract_coverage[
                    "insufficient_complete_quote_contract_months"
                ]
            ),
            "publication_date_coverage_met": publication_coverage_met,
            "point_in_time_membership_available": membership_available,
            "terminal_survivor_cutoff": parameters[
                "terminal_survivor_cutoff"
            ],
            "terminal_survivor_comparator_verified": (
                terminal_survivor_comparator_verified
            ),
            "security_identifier_contract_id": parameters[
                "security_identifier_contract_id"
            ],
            "security_identifier_contract_verified": (
                security_identifier_contract_verified
            ),
            "execution_columns_present": execution_columns_present,
            "execution_semantics_verified": execution_semantics_verified,
            "tradability_fields_verified": tradability_fields_verified,
            "exact_endpoint_resolution_semantics_verified": (
                exact_endpoint_resolution_semantics_verified
            ),
            "suspension_valuation_semantics_verified": (
                suspension_valuation_semantics_verified
            ),
            "price_adjustment_semantics_verified": (
                price_adjustment_semantics_verified
            ),
            "amount_unit_normalization_semantics_verified": (
                amount_unit_normalization_semantics_verified
            ),
            "endpoint_reason_ledger_rights_verified": (
                endpoint_reason_ledger_rights_verified
            ),
            "historical_membership_completeness_verified": (
                historical_membership_completeness_verified
            ),
            "fundamental_publication_semantics_verified": (
                fundamental_publication_semantics_verified
            ),
            "data_rights_verified": data_rights_verified,
            "official_calendar_review_verified": official_calendar_review_verified,
            "csv_row_width_integrity_met": csv_row_width_integrity_met,
            "logical_key_uniqueness_met": logical_key_uniqueness_met,
            "input_structural_integrity_met": input_structural_integrity_met,
            "required_field_non_null_integrity_met": (
                required_field_non_null_integrity_met
            ),
            "canonical_date_format_integrity_met": (
                canonical_date_format_integrity_met
            ),
            "canonical_symbol_integrity_met": canonical_symbol_integrity_met,
            "complete_revision_vintage_available": vintage_available,
            "revision_history_claim_allowed": vintage_available,
            "ready_to_lock_stage2_plan": ready,
            "blocking_reason_codes": reasons,
        },
        "scope": {
            "purpose": "data-feasibility precondition for a Stage-2 registered study",
            "contract_mutability": "fixed; caller overrides are rejected",
            "duplicate_key_validation": (
                "enforced here on normalized logical keys for every input role; "
                "an exact bounded-memory index spills to private temporary SQLite "
                "storage when needed; only aggregate duplicate-row counts are "
                "reported and temporary paths are never disclosed"
            ),
            "csv_row_width_validation": (
                "enforced here for short and over-wide records; only aggregate "
                "malformed-row counts are reported"
            ),
            "canonical_date_validation": (
                "every non-blank canonical CSV date field must be an exact, valid "
                "YYYY-MM-DD value within the pandas-nanosecond-safe midnight range "
                "1677-09-22 through 2262-04-11; provider-native formats must be "
                "normalized by the private adapter before this audit"
            ),
            "canonical_symbol_validation": (
                "quotes, stock_master, and fundamentals require one canonical "
                "six-digit uppercase .SH/.SZ symbol on every row; only aggregate "
                "blank, NA-like, and invalid-format counts are reported"
            ),
            "canonical_numeric_validation": (
                "quote close/amount and fundamental roeDiluted must use ASCII decimal "
                "syntax with an optional sign, fraction, and base-10 exponent; "
                "underscores, locale separators, hexadecimal forms, NaN, and infinity "
                "are rejected before finite and economic-domain checks"
            ),
            "canonical_amount_unit_validation": (
                "every bound Stage-2 quote row must carry the exact case-sensitive "
                "amount_unit token CNY; provider-native thousand-CNY or other units "
                "must be normalized by a documented private adapter before hashing, "
                "coverage audit, registration, and execution"
            ),
            "canonical_price_adjustment_validation": (
                "every row must carry close_raw, a finite positive adjustment_factor, "
                "the exact fixed method and hfq convention tokens, and a close equal "
                "to close_raw multiplied by adjustment_factor within fixed 1e-12 "
                "relative and absolute tolerances; provider definitions and no-rebasing "
                "normalization remain hash-bound human-review evidence"
            ),
            "raw_rows_disclosed": False,
            "local_paths_disclosed": False,
            "revision_history_boundary": (
                "not allowed: a validated revision-vintage adapter is not implemented; "
                "observed vintage-like columns are diagnostic only"
            ),
            "column_presence_boundary": (
                "presence alone does not establish execution semantics or publication "
                "rights; this audit separately enforces runner-compatible ST and "
                "suspension boolean encodings, exact close-observation-type mapping, "
                "and signal-session non-degeneracy, while supplier-recorded same-session "
                "suspension-valuation semantics remain subject to the bound human "
                "review attestation"
            ),
            "symbol_eligibility_boundary": (
                "each target month constructs its strict SH/SZ A-share universe from "
                "listDate <= signal_date <= delistDate (delistDate inclusive), then "
                "requires every active master identifier with a signal-session quote "
                "to have quote rows at t, t+1, t+20, and t+21, and separately requires "
                "at least 1,000 identifiers with quote rows on every exact "
                "official session needed "
                "from t-60 through t for momentum, for the 20-session volatility "
                "and amount histories, "
                "and t/t+1/t+20/t+21 endpoints; a dense rebalance date or file-level "
                "minimum/maximum date cannot substitute for per-symbol coverage"
            ),
        },
        "review_attestation": {
            "present": review_attestation is not None,
            "schema_version": attestation["schema_version"],
            "coverage_probe_spec_path": attestation["coverage_probe_spec_path"],
            "coverage_probe_spec_sha256": attestation[
                "coverage_probe_spec_sha256"
            ],
            "coverage_probe_receipt_path": attestation[
                "coverage_probe_receipt_path"
            ],
            "coverage_probe_receipt_sha256": attestation[
                "coverage_probe_receipt_sha256"
            ],
            "exact_endpoint_resolution_semantics_verified": attestation[
                "exact_endpoint_resolution_semantics_verified"
            ],
            "suspension_valuation_semantics_verified": attestation[
                "suspension_valuation_semantics_verified"
            ],
            "price_adjustment_semantics_verified": attestation[
                "price_adjustment_semantics_verified"
            ],
            "amount_unit_normalization_semantics_verified": attestation[
                "amount_unit_normalization_semantics_verified"
            ],
            "endpoint_reason_ledger_rights_verified": attestation[
                "endpoint_reason_ledger_rights_verified"
            ],
            "terminal_survivor_comparator_verified": attestation[
                "terminal_survivor_comparator_verified"
            ],
            "security_identifier_semantics_verified": attestation[
                "security_identifier_semantics_verified"
            ],
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
    payload = _canonical_json_bytes(report) + b"\n"
    try:
        write_private_bytes_atomic_exclusive(
            output_path,
            payload,
            label="authoritative coverage report target",
        )
    except PrivateArtifactPathError as exc:
        raise StudyV2CoverageError(str(exc)) from exc


def _scan_quotes(raw_csv: bytes, identity: Mapping[str, Any]) -> dict[str, Any]:
    scan = _scan_csv(
        raw_csv,
        source_name=str(identity["file_name"]),
        required=QUOTE_REQUIRED,
        date_columns=("date",),
        non_null_columns=(
            "date", "symbol", "open", "close_raw", "adjustment_factor",
            "close", "price_adjustment_method", "price_adjustment_convention",
            "volume", "amount",
            "amount_unit", "close_observation_type", "is_st", "is_suspended",
        ),
        logical_key_columns=("symbol", "date"),
        monthly_date_column="date",
    )
    numeric_integrity = _quote_numeric_integrity(
        raw_csv, source_name=str(identity["file_name"])
    )
    boolean_integrity = _quote_boolean_integrity(
        raw_csv, source_name=str(identity["file_name"])
    )
    amount_unit_integrity = _quote_amount_unit_integrity(
        raw_csv, source_name=str(identity["file_name"])
    )
    price_adjustment_integrity = _quote_price_adjustment_integrity(
        raw_csv, source_name=str(identity["file_name"])
    )
    symbol_integrity = _canonical_symbol_integrity(
        raw_csv, source_name=str(identity["file_name"])
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
        "blank_value_counts": scan["blank_value_counts"],
        "na_like_value_counts": scan["na_like_value_counts"],
        "missing_value_counts": scan["missing_value_counts"],
        "invalid_date_format_counts": scan["invalid_date_format_counts"],
        **_structural_integrity_fields(scan),
        **numeric_integrity,
        **boolean_integrity,
        **amount_unit_integrity,
        **price_adjustment_integrity,
        **symbol_integrity,
        "observed_month_count": len(scan["monthly_coverage"]),
        "minimum_monthly_symbol_count": min(
            (row["symbol_count"] for row in scan["monthly_coverage"]), default=0
        ),
        "minimum_sessions_per_observed_month": min(
            (row["session_count"] for row in scan["monthly_coverage"]), default=0
        ),
        "monthly_coverage": scan["monthly_coverage"],
    }


def _quote_numeric_integrity(
    raw_csv: bytes, *, source_name: str
) -> dict[str, Any]:
    """Return aggregate-only integrity counts for outcome-bearing quote fields."""

    counts = {
        "close_blank_row_count": 0,
        "close_non_numeric_or_non_finite_row_count": 0,
        "close_invalid_canonical_numeric_format_row_count": 0,
        "close_non_finite_row_count": 0,
        "close_non_positive_row_count": 0,
        "amount_blank_row_count": 0,
        "amount_non_numeric_or_non_finite_row_count": 0,
        "amount_invalid_canonical_numeric_format_row_count": 0,
        "amount_non_finite_row_count": 0,
        "amount_negative_row_count": 0,
    }
    row_count = 0
    try:
        with io.TextIOWrapper(
            io.BytesIO(raw_csv), encoding="utf-8-sig", newline=""
        ) as handle:
            for row in csv.DictReader(handle):
                row_count += 1
                close_value, close_status = _canonical_numeric_value(
                    row.get("close")
                )
                if close_status == "blank":
                    counts["close_blank_row_count"] += 1
                elif close_status == "invalid_format":
                    counts["close_non_numeric_or_non_finite_row_count"] += 1
                    counts[
                        "close_invalid_canonical_numeric_format_row_count"
                    ] += 1
                elif close_status == "non_finite":
                    counts["close_non_numeric_or_non_finite_row_count"] += 1
                    counts["close_non_finite_row_count"] += 1
                elif close_value is not None and close_value <= 0:
                    counts["close_non_positive_row_count"] += 1

                amount_value, amount_status = _canonical_numeric_value(
                    row.get("amount")
                )
                if amount_status == "blank":
                    counts["amount_blank_row_count"] += 1
                elif amount_status == "invalid_format":
                    counts["amount_non_numeric_or_non_finite_row_count"] += 1
                    counts[
                        "amount_invalid_canonical_numeric_format_row_count"
                    ] += 1
                elif amount_status == "non_finite":
                    counts["amount_non_numeric_or_non_finite_row_count"] += 1
                    counts["amount_non_finite_row_count"] += 1
                elif amount_value is not None and amount_value < 0:
                    counts["amount_negative_row_count"] += 1
    except csv.Error as exc:
        raise StudyV2CoverageError(f"CSV cannot be parsed: {source_name}") from exc

    close_invalid = sum(
        counts[key]
        for key in (
            "close_blank_row_count",
            "close_non_numeric_or_non_finite_row_count",
            "close_non_positive_row_count",
        )
    )
    amount_invalid = sum(
        counts[key]
        for key in (
            "amount_blank_row_count",
            "amount_non_numeric_or_non_finite_row_count",
            "amount_negative_row_count",
        )
    )
    return {
        **counts,
        "close_invalid_row_count": close_invalid,
        "close_invalid_rate": round(close_invalid / row_count, 10)
        if row_count
        else 0.0,
        "amount_invalid_row_count": amount_invalid,
        "amount_invalid_rate": round(amount_invalid / row_count, 10)
        if row_count
        else 0.0,
        "numeric_integrity_verified": close_invalid == 0 and amount_invalid == 0,
        "numeric_integrity_basis": (
            "aggregate row counts only; values must match the exact canonical ASCII "
            "decimal grammar with optional sign, fraction, and base-10 exponent, "
            "then be finite; close must be strictly positive and amount non-negative"
        ),
    }


def _quote_boolean_integrity(
    raw_csv: bytes, *, source_name: str
) -> dict[str, Any]:
    """Audit runner-compatible flags without retaining raw field values."""

    true_tokens = {"true", "1", "yes"}
    false_tokens = {"false", "0", "no"}
    states: dict[str, set[str]] = {
        "is_st": set(),
        "is_suspended": set(),
    }
    blank_counts = {"is_st": 0, "is_suspended": 0}
    invalid_counts = {"is_st": 0, "is_suspended": 0}
    observation_types: set[str] = set()
    observation_type_blank_count = 0
    observation_type_invalid_count = 0
    observation_type_suspension_mismatch_count = 0
    try:
        with io.TextIOWrapper(
            io.BytesIO(raw_csv), encoding="utf-8-sig", newline=""
        ) as handle:
            for row in csv.DictReader(handle):
                canonical_suspension_state: str | None = None
                for field in states:
                    text = str(row.get(field) or "").strip().lower()
                    if not text:
                        blank_counts[field] += 1
                    elif text in true_tokens:
                        states[field].add("true")
                        if field == "is_suspended":
                            canonical_suspension_state = "true"
                    elif text in false_tokens:
                        states[field].add("false")
                        if field == "is_suspended":
                            canonical_suspension_state = "false"
                    else:
                        invalid_counts[field] += 1
                raw_observation_type = str(
                    row.get("close_observation_type") or ""
                )
                observation_type = raw_observation_type.strip()
                if not observation_type:
                    observation_type_blank_count += 1
                elif (
                    raw_observation_type != observation_type
                    or observation_type not in STAGE2_CLOSE_OBSERVATION_TYPES
                ):
                    observation_type_invalid_count += 1
                else:
                    observation_types.add(observation_type)
                    if canonical_suspension_state is not None:
                        expected_type = (
                            "suspension_valuation"
                            if canonical_suspension_state == "true"
                            else "traded_close"
                        )
                        if observation_type != expected_type:
                            observation_type_suspension_mismatch_count += 1
    except csv.Error as exc:
        raise StudyV2CoverageError(f"CSV cannot be parsed: {source_name}") from exc

    result: dict[str, Any] = {}
    for field in ("is_st", "is_suspended"):
        result[f"{field}_blank_row_count"] = blank_counts[field]
        result[f"{field}_invalid_boolean_row_count"] = invalid_counts[field]
        result[f"{field}_distinct_canonical_states"] = sorted(states[field])
        result[f"{field}_non_degenerate"] = states[field] == {"true", "false"}
    result["boolean_integrity_verified"] = all(
        blank_counts[field] == 0
        and invalid_counts[field] == 0
        and states[field] == {"true", "false"}
        for field in states
    )
    result["boolean_integrity_basis"] = (
        "aggregate-only runner-compatible normalization: true/1/yes -> true; "
        "false/0/no -> false; case and surrounding whitespace ignored; each "
        "required field must contain both canonical states"
    )
    result.update(
        {
            "close_observation_type_blank_row_count": (
                observation_type_blank_count
            ),
            "close_observation_type_invalid_row_count": (
                observation_type_invalid_count
            ),
            "close_observation_type_suspension_mismatch_row_count": (
                observation_type_suspension_mismatch_count
            ),
            "close_observation_type_distinct_states": sorted(
                observation_types
            ),
            "close_observation_type_non_degenerate": observation_types
            == STAGE2_CLOSE_OBSERVATION_TYPES,
            "close_observation_contract_verified": bool(
                observation_type_blank_count == 0
                and observation_type_invalid_count == 0
                and observation_type_suspension_mismatch_count == 0
            ),
            "close_observation_contract_basis": (
                "exact canonical traded_close iff is_suspended is false; exact "
                "canonical suspension_valuation iff is_suspended is true; "
                "supplier-recorded same-session valuation semantics require the "
                "separate human review attestation"
            ),
        }
    )
    return result


def _quote_amount_unit_integrity(
    raw_csv: bytes, *, source_name: str
) -> dict[str, Any]:
    """Require the bound canonical amount field to be expressed in exact CNY."""

    blank_count = 0
    non_cny_count = 0
    row_count = 0
    try:
        with io.TextIOWrapper(
            io.BytesIO(raw_csv), encoding="utf-8-sig", newline=""
        ) as handle:
            for row in csv.DictReader(handle):
                row_count += 1
                raw_unit = row.get("amount_unit")
                if raw_unit is None or raw_unit == "":
                    blank_count += 1
                elif raw_unit != STAGE2_CANONICAL_AMOUNT_UNIT:
                    non_cny_count += 1
    except csv.Error as exc:
        raise StudyV2CoverageError(f"CSV cannot be parsed: {source_name}") from exc
    return {
        "amount_unit_blank_row_count": blank_count,
        "amount_unit_non_cny_row_count": non_cny_count,
        "canonical_amount_unit_verified": bool(
            row_count > 0 and blank_count == 0 and non_cny_count == 0
        ),
        "canonical_amount_unit_basis": (
            "exact case-sensitive CNY token on every bound quote row; provider-native "
            "units must be normalized before input hashing and coverage audit"
        ),
    }


def _quote_price_adjustment_integrity(
    raw_csv: bytes, *, source_name: str
) -> dict[str, Any]:
    """Mechanically verify the fixed adjusted-close construction row by row.

    The audit retains only aggregate failure counts. Provider definitions and
    the meaning of its cumulative factor remain a separately hash-bound human
    review; exact tokens cannot prove a vendor's documentation by themselves.
    """

    counts = {
        "close_raw_blank_row_count": 0,
        "close_raw_invalid_row_count": 0,
        "close_raw_non_positive_row_count": 0,
        "adjustment_factor_blank_row_count": 0,
        "adjustment_factor_invalid_row_count": 0,
        "adjustment_factor_non_positive_row_count": 0,
        "price_adjustment_method_blank_row_count": 0,
        "price_adjustment_method_invalid_row_count": 0,
        "price_adjustment_convention_blank_row_count": 0,
        "price_adjustment_convention_invalid_row_count": 0,
        "price_adjustment_formula_uncheckable_row_count": 0,
        "price_adjustment_formula_mismatch_row_count": 0,
    }
    row_count = 0
    try:
        with io.TextIOWrapper(
            io.BytesIO(raw_csv), encoding="utf-8-sig", newline=""
        ) as handle:
            for row in csv.DictReader(handle):
                row_count += 1
                numeric: dict[str, float] = {}
                for field in ("close_raw", "adjustment_factor", "close"):
                    value, status = _canonical_numeric_value(row.get(field))
                    if field == "close":
                        if status != "valid" or value is None or value <= 0:
                            counts[
                                "price_adjustment_formula_uncheckable_row_count"
                            ] += 1
                        else:
                            numeric[field] = value
                        continue
                    if status == "blank":
                        counts[f"{field}_blank_row_count"] += 1
                    elif status != "valid" or value is None:
                        counts[f"{field}_invalid_row_count"] += 1
                    elif value <= 0:
                        counts[f"{field}_non_positive_row_count"] += 1
                    else:
                        numeric[field] = value
                for field, expected in (
                    ("price_adjustment_method", STAGE2_PRICE_ADJUSTMENT_METHOD),
                    (
                        "price_adjustment_convention",
                        STAGE2_PRICE_ADJUSTMENT_CONVENTION,
                    ),
                ):
                    raw_value = row.get(field)
                    if raw_value is None or raw_value == "":
                        counts[f"{field}_blank_row_count"] += 1
                    elif raw_value != expected:
                        counts[f"{field}_invalid_row_count"] += 1
                if len(numeric) != 3:
                    if "close" in numeric:
                        counts[
                            "price_adjustment_formula_uncheckable_row_count"
                        ] += 1
                    continue
                expected_close = numeric["close_raw"] * numeric["adjustment_factor"]
                if not math.isclose(
                    numeric["close"],
                    expected_close,
                    rel_tol=STAGE2_PRICE_ADJUSTMENT_REL_TOLERANCE,
                    abs_tol=STAGE2_PRICE_ADJUSTMENT_ABS_TOLERANCE,
                ):
                    counts["price_adjustment_formula_mismatch_row_count"] += 1
    except csv.Error as exc:
        raise StudyV2CoverageError(f"CSV cannot be parsed: {source_name}") from exc

    invalid_count = sum(counts.values())
    return {
        **counts,
        "price_adjustment_contract_verified": bool(
            row_count > 0 and invalid_count == 0
        ),
        "price_adjustment_contract": {
            "method": STAGE2_PRICE_ADJUSTMENT_METHOD,
            "convention": STAGE2_PRICE_ADJUSTMENT_CONVENTION,
            "formula": "close=close_raw*adjustment_factor",
            "relative_tolerance": STAGE2_PRICE_ADJUSTMENT_REL_TOLERANCE,
            "absolute_tolerance": STAGE2_PRICE_ADJUSTMENT_ABS_TOLERANCE,
            "normalization_base_rule": (
                "provider_cumulative_factor_as_delivered_no_rebasing"
            ),
            "return_invariance_rule": (
                "per_symbol_positive_constant_factor_rescaling_leaves_return_ratios_unchanged"
            ),
        },
        "price_adjustment_contract_basis": (
            "aggregate-only verification that every row carries the exact method and "
            "convention tokens and that close equals close_raw times a finite positive "
            "adjustment_factor within fixed 1e-12 relative and absolute tolerances"
        ),
    }


def _signal_session_close_observation_coverage(
    raw_csv: bytes,
    *,
    signal_session_candidates: Mapping[date, SetABC[str]],
    source_name: str,
) -> dict[str, Any]:
    """Count close-observation types for fixed signal-session candidates only."""

    counts = {value: 0 for value in STAGE2_CLOSE_OBSERVATION_TYPES}
    scoped_rows = 0
    invalid_rows = 0
    try:
        with io.TextIOWrapper(
            io.BytesIO(raw_csv), encoding="utf-8-sig", newline=""
        ) as handle:
            for row in csv.DictReader(handle):
                row_date, date_has_invalid_format = _optional_canonical_date(
                    row.get("date")
                )
                symbol = str(row.get("symbol") or "").strip().upper()
                candidates = (
                    signal_session_candidates.get(row_date, set())
                    if row_date is not None and not date_has_invalid_format
                    else set()
                )
                if not symbol or symbol not in candidates:
                    continue
                scoped_rows += 1
                raw_type = str(row.get("close_observation_type") or "")
                observation_type = raw_type.strip()
                if (
                    raw_type != observation_type
                    or observation_type not in STAGE2_CLOSE_OBSERVATION_TYPES
                ):
                    invalid_rows += 1
                    continue
                counts[observation_type] += 1
    except csv.Error as exc:
        raise StudyV2CoverageError(f"CSV cannot be parsed: {source_name}") from exc
    return {
        "signal_session_close_observation_row_count": scoped_rows,
        "signal_session_close_observation_type_counts": dict(sorted(counts.items())),
        "signal_session_close_observation_invalid_row_count": invalid_rows,
        "signal_session_close_observation_types_non_degenerate": bool(
            invalid_rows == 0 and all(counts[value] > 0 for value in counts)
        ),
        "signal_session_close_observation_scope": (
            "aggregate counts over active strict A-share master identifiers with a "
            "quote on the first common official session in each of the 156 fixed "
            "target months; no price, return, factor, rank, or security identifier "
            "is reported"
        ),
    }


def _canonical_symbol_integrity(
    raw_csv: bytes, *, source_name: str
) -> dict[str, Any]:
    blank_rows = 0
    na_like_rows = 0
    invalid_format_rows = 0
    try:
        with io.TextIOWrapper(
            io.BytesIO(raw_csv), encoding="utf-8-sig", newline=""
        ) as handle:
            for row in csv.DictReader(handle):
                raw_text = str(row.get("symbol") or "")
                text = raw_text.strip()
                if not text:
                    blank_rows += 1
                elif _is_na_like_token(text):
                    na_like_rows += 1
                elif raw_text != text or CANONICAL_SYMBOL_PATTERN.fullmatch(text) is None:
                    invalid_format_rows += 1
    except csv.Error as exc:
        raise StudyV2CoverageError(f"CSV cannot be parsed: {source_name}") from exc
    return {
        "symbol_blank_row_count": blank_rows,
        "symbol_na_like_row_count": na_like_rows,
        "symbol_invalid_canonical_format_row_count": invalid_format_rows,
        "canonical_symbol_integrity_verified": (
            blank_rows == 0 and na_like_rows == 0 and invalid_format_rows == 0
        ),
        "canonical_symbol_integrity_basis": (
            "every row must contain exactly six ASCII digits followed by uppercase "
            ".SH or .SZ; blank and pandas-default-NA-like tokens are invalid; "
            "aggregate counts only"
        ),
    }


def _scan_master(raw_csv: bytes, identity: Mapping[str, Any]) -> dict[str, Any]:
    scan = _scan_csv(
        raw_csv,
        source_name=str(identity["file_name"]),
        required=MASTER_REQUIRED,
        date_columns=("listDate", "delistDate"),
        non_null_columns=("symbol", "listDate", "listStatus", "stockType"),
        logical_key_columns=("symbol",),
        collect_columns=("listStatus",),
    )
    symbol_integrity = _canonical_symbol_integrity(
        raw_csv, source_name=str(identity["file_name"])
    )
    scoped_rows = 0
    scoped_symbols: set[str] = set()
    nonblank_list_dates = 0
    valid_list_dates: list[date] = []
    valid_delist_dates: list[date] = []
    missing_or_invalid_list_dates = 0
    invalid_delist_dates = 0
    delisted_missing_delist_dates = 0
    delist_before_list_dates = 0
    active_with_delist_dates = 0
    unrecognized_statuses = 0
    delisted_symbols: set[str] = set()
    terminal_survivor_symbols: set[str] = set()
    with io.TextIOWrapper(
        io.BytesIO(raw_csv), encoding="utf-8-sig", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            if not _is_strict_a_share_master_row(row):
                continue
            scoped_rows += 1
            symbol = (row.get("symbol") or "").strip()
            scoped_symbols.add(symbol)
            if (row.get("listDate") or "").strip():
                nonblank_list_dates += 1
            list_date, _ = _optional_master_date(row.get("listDate"))
            delist_date, delist_date_invalid = _optional_master_date(
                row.get("delistDate")
            )
            if list_date is None:
                missing_or_invalid_list_dates += 1
            else:
                valid_list_dates.append(list_date)
            if delist_date_invalid:
                invalid_delist_dates += 1
            if delist_date is not None:
                valid_delist_dates.append(delist_date)
            if (
                list_date is not None
                and list_date <= STAGE2_TERMINAL_SURVIVOR_CUTOFF
                and (
                    delist_date is None
                    or delist_date > STAGE2_TERMINAL_SURVIVOR_CUTOFF
                )
            ):
                terminal_survivor_symbols.add(symbol)

            status = (row.get("listStatus") or "").strip().upper()
            if status in DELISTED_LIST_STATUSES:
                delisted_symbols.add(symbol)
                if delist_date is None:
                    delisted_missing_delist_dates += 1
            elif status in ACTIVE_LIST_STATUSES:
                if (row.get("delistDate") or "").strip():
                    active_with_delist_dates += 1
            else:
                unrecognized_statuses += 1

            if (
                list_date is not None
                and delist_date is not None
                and delist_date < list_date
            ):
                delist_before_list_dates += 1

    membership_reasons: list[str] = []
    if scoped_rows == 0:
        membership_reasons.append("NO_SCOPED_A_SHARE_ROWS")
    if missing_or_invalid_list_dates:
        membership_reasons.append("MISSING_OR_INVALID_SCOPED_LIST_DATE")
    if not delisted_symbols:
        membership_reasons.append("NO_DELISTED_SCOPED_A_SHARE_ROWS")
    if delisted_missing_delist_dates:
        membership_reasons.append("DELISTED_ROW_MISSING_DELIST_DATE")
    if invalid_delist_dates:
        membership_reasons.append("INVALID_SCOPED_DELIST_DATE")
    if delist_before_list_dates:
        membership_reasons.append("DELIST_DATE_BEFORE_LIST_DATE")
    if active_with_delist_dates:
        membership_reasons.append("ACTIVE_ROW_HAS_DELIST_DATE")
    if unrecognized_statuses:
        membership_reasons.append("UNRECOGNIZED_LIST_STATUS")
    if not scan["required_columns_present"]:
        membership_reasons.append("MISSING_STOCK_MASTER_FIELDS")

    return {
        **identity,
        "row_count": scan["row_count"],
        "symbol_count": scan["symbol_count"],
        "scoped_row_count": scoped_rows,
        "scoped_symbol_count": len(scoped_symbols),
        "earliest_list_date": min(valid_list_dates).isoformat()
        if valid_list_dates
        else None,
        "latest_delist_date": max(valid_delist_dates).isoformat()
        if valid_delist_dates
        else None,
        "delisted_symbol_count": len(delisted_symbols),
        "terminal_survivor_cutoff": STAGE2_TERMINAL_SURVIVOR_CUTOFF.isoformat(),
        "terminal_survivor_symbol_count": len(terminal_survivor_symbols),
        "terminal_survivor_rule": (
            "listDate_on_or_before_signal_session_and_delistDate_is_null_or_"
            "strictly_after_2023-01-31;_listStatus_and_acquisition_date_do_not_"
            "redefine_membership"
        ),
        "non_null_list_date_rate": round(
            nonblank_list_dates / scoped_rows, 10
        )
        if scoped_rows
        else 0.0,
        "valid_list_date_rate": round(len(valid_list_dates) / scoped_rows, 10)
        if scoped_rows
        else 0.0,
        "valid_scoped_list_date_count": len(valid_list_dates),
        "missing_or_invalid_scoped_list_date_count": (
            missing_or_invalid_list_dates
        ),
        "invalid_scoped_delist_date_count": invalid_delist_dates,
        "delisted_row_missing_delist_date_count": (
            delisted_missing_delist_dates
        ),
        "delist_date_before_list_date_count": delist_before_list_dates,
        "active_row_with_delist_date_count": active_with_delist_dates,
        "unrecognized_list_status_count": unrecognized_statuses,
        "membership_integrity_verified": not membership_reasons,
        "membership_blocking_reason_codes": membership_reasons,
        "required_columns_present": scan["required_columns_present"],
        "missing_required_columns": scan["missing_required_columns"],
        "non_null_rates": scan["non_null_rates"],
        "blank_value_counts": scan["blank_value_counts"],
        "na_like_value_counts": scan["na_like_value_counts"],
        "missing_value_counts": scan["missing_value_counts"],
        "invalid_date_format_counts": scan["invalid_date_format_counts"],
        **_structural_integrity_fields(scan),
        **symbol_integrity,
    }


def _scan_fundamentals(raw_csv: bytes, identity: Mapping[str, Any]) -> dict[str, Any]:
    scan = _scan_csv(
        raw_csv,
        source_name=str(identity["file_name"]),
        required=FUNDAMENTAL_REQUIRED,
        date_columns=("publishDate", "reportPeriodEnd"),
        non_null_columns=("symbol", "roeDiluted", "publishDate", "reportPeriodEnd"),
        finite_numeric_columns=("roeDiluted",),
        logical_key_columns=("symbol", "reportPeriodEnd"),
    )
    vintage = _audit_vintage_rows(raw_csv, scan["fieldnames"])
    global_publication_order = _global_fundamental_publication_order(raw_csv)
    symbol_integrity = _canonical_symbol_integrity(
        raw_csv, source_name=str(identity["file_name"])
    )
    return {
        **identity,
        "row_count": scan["row_count"],
        "symbol_count": scan["symbol_count"],
        "report_period_start": scan["date_ranges"]["reportPeriodEnd"][0],
        "report_period_end": scan["date_ranges"]["reportPeriodEnd"][1],
        "publication_start": scan["date_ranges"]["publishDate"][0],
        "publication_end": scan["date_ranges"]["publishDate"][1],
        "publish_date_non_null_rate": scan["non_null_rates"].get("publishDate", 0.0),
        "roe_diluted_finite_numeric_rate": scan["finite_numeric_rates"].get(
            "roeDiluted", 0.0
        ),
        "invalid_roe_diluted_numeric_row_count": scan[
            "invalid_finite_numeric_counts"
        ].get("roeDiluted", 0),
        "invalid_roe_diluted_numeric_format_row_count": scan[
            "invalid_numeric_format_counts"
        ].get("roeDiluted", 0),
        "non_finite_roe_diluted_row_count": scan[
            "non_finite_numeric_counts"
        ].get("roeDiluted", 0),
        **global_publication_order,
        "required_columns_present": scan["required_columns_present"],
        "missing_required_columns": scan["missing_required_columns"],
        "non_null_rates": scan["non_null_rates"],
        "blank_value_counts": scan["blank_value_counts"],
        "na_like_value_counts": scan["na_like_value_counts"],
        "missing_value_counts": scan["missing_value_counts"],
        "invalid_date_format_counts": scan["invalid_date_format_counts"],
        **_structural_integrity_fields(scan),
        **symbol_integrity,
        "revision_vintage_fields_observed": vintage["fields_present"],
        "validated_revision_adapter_implemented": False,
        "complete_revision_vintage_fields_present": False,
        "revision_vintage_complete_row_rate": vintage["complete_row_rate"],
        "revision_versioned_symbol_period_count": vintage["versioned_symbol_period_count"],
    }


def _global_fundamental_publication_order(raw_csv: bytes) -> dict[str, Any]:
    comparable_rows = 0
    publication_before_report_rows = 0
    with io.TextIOWrapper(
        io.BytesIO(raw_csv), encoding="utf-8-sig", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            publish_date, _ = _optional_canonical_date(row.get("publishDate"))
            report_end, _ = _optional_canonical_date(row.get("reportPeriodEnd"))
            if publish_date is None or report_end is None:
                continue
            comparable_rows += 1
            if publish_date < report_end:
                publication_before_report_rows += 1
    return {
        "global_publication_order_comparable_row_count": comparable_rows,
        "global_publication_before_report_period_end_row_count": (
            publication_before_report_rows
        ),
        "global_publication_order_check_scope": (
            "all input rows with non-blank, valid publishDate and reportPeriodEnd; "
            "aggregate counts only"
        ),
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
        logical_key_columns=("date",),
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
        "blank_value_counts": scan["blank_value_counts"],
        "na_like_value_counts": scan["na_like_value_counts"],
        "missing_value_counts": scan["missing_value_counts"],
        "invalid_date_format_counts": scan["invalid_date_format_counts"],
        "duplicate_session_count": scan["duplicate_logical_key_row_count"],
        "strictly_increasing": bool(dates) and all(
            earlier < later for earlier, later in zip(dates, dates[1:])
        ),
        **_structural_integrity_fields(scan),
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
    finite_numeric_columns: Sequence[str] = (),
    logical_key_columns: Sequence[str] = (),
    collect_columns: Sequence[str] = (),
    monthly_date_column: str | None = None,
) -> dict[str, Any]:
    try:
        with io.TextIOWrapper(
            io.BytesIO(raw_csv), encoding="utf-8-sig", newline=""
        ) as handle, _ExactLogicalKeyTracker(
            LOGICAL_KEY_IN_MEMORY_LIMIT
        ) as seen_logical_keys:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or ())
            if not fieldnames:
                raise StudyV2CoverageError(f"CSV has no header: {source_name}")
            if len(fieldnames) != len(set(fieldnames)):
                raise StudyV2CoverageError(f"CSV has duplicate headers: {source_name}")
            missing = sorted(set(required) - set(fieldnames))
            dates: dict[str, list[date | None]] = {name: [None, None] for name in date_columns}
            invalid_date_formats = {name: 0 for name in date_columns}
            non_null = {name: 0 for name in non_null_columns}
            blank_values = {name: 0 for name in non_null_columns}
            na_like_values = {name: 0 for name in non_null_columns}
            finite_numeric = set(finite_numeric_columns)
            if not finite_numeric.issubset(non_null):
                raise StudyV2CoverageError(
                    "finite numeric columns must also be non-null columns: "
                    f"{source_name}"
                )
            invalid_finite_numeric = {name: 0 for name in finite_numeric}
            invalid_numeric_formats = {name: 0 for name in finite_numeric}
            non_finite_numeric = {name: 0 for name in finite_numeric}
            valid_finite_numeric = {name: 0 for name in finite_numeric}
            duplicate_logical_key_rows = 0
            extra_field_rows = 0
            missing_field_rows = 0
            malformed_width_rows = 0
            collected: dict[str, dict[str, int]] = {name: {} for name in collect_columns}
            symbols: set[str] = set()
            monthly_symbols: dict[str, set[str]] = {}
            monthly_sessions: dict[str, set[str]] = {}
            rows = 0
            for row in reader:
                rows += 1
                has_extra_fields = None in row
                has_missing_fields = any(row.get(name) is None for name in fieldnames)
                if has_extra_fields:
                    extra_field_rows += 1
                if has_missing_fields:
                    missing_field_rows += 1
                if has_extra_fields or has_missing_fields:
                    malformed_width_rows += 1
                logical_key = _normalized_logical_key(
                    row,
                    columns=logical_key_columns,
                    date_columns=date_columns,
                )
                if logical_key is not None:
                    if seen_logical_keys.add(logical_key):
                        duplicate_logical_key_rows += 1
                symbol = (row.get("symbol") or "").strip()
                if symbol:
                    symbols.add(symbol)
                for name in non_null_columns:
                    raw_value = str(row.get(name) or "")
                    value = raw_value.strip()
                    if not value:
                        blank_values[name] += 1
                        continue
                    if _is_na_like_token(value):
                        na_like_values[name] += 1
                        if name in finite_numeric:
                            invalid_finite_numeric[name] += 1
                            invalid_numeric_formats[name] += 1
                        continue
                    non_null[name] += 1
                    if name in finite_numeric:
                        _, numeric_status = _canonical_numeric_value(raw_value)
                        if numeric_status != "valid":
                            invalid_finite_numeric[name] += 1
                        else:
                            valid_finite_numeric[name] += 1
                        if numeric_status == "invalid_format":
                            invalid_numeric_formats[name] += 1
                        elif numeric_status == "non_finite":
                            non_finite_numeric[name] += 1
                for name in date_columns:
                    parsed, invalid_format = _optional_canonical_date(row.get(name))
                    if invalid_format:
                        invalid_date_formats[name] += 1
                        continue
                    if parsed is None:
                        continue
                    if dates[name][0] is None or parsed < dates[name][0]:
                        dates[name][0] = parsed
                    if dates[name][1] is None or parsed > dates[name][1]:
                        dates[name][1] = parsed
                if monthly_date_column is not None:
                    parsed_month_date, _ = _optional_canonical_date(
                        row.get(monthly_date_column)
                    )
                    if parsed_month_date is not None:
                        month = parsed_month_date.strftime("%Y-%m")
                        monthly_sessions.setdefault(month, set()).add(parsed_month_date.isoformat())
                        if symbol:
                            monthly_symbols.setdefault(month, set()).add(symbol)
                for name in collect_columns:
                    value = (row.get(name) or "").strip()
                    collected[name][value] = collected[name].get(value, 0) + 1
    except UnicodeDecodeError as exc:
        raise StudyV2CoverageError(f"CSV is not valid UTF-8: {source_name}") from exc
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
        "blank_value_counts": {
            name: blank_values[name] for name in non_null_columns
        },
        "na_like_value_counts": {
            name: na_like_values[name] for name in non_null_columns
        },
        "missing_value_counts": {
            name: blank_values[name] + na_like_values[name]
            for name in non_null_columns
        },
        "finite_numeric_rates": {
            name: round(valid_finite_numeric[name] / rows, 10)
            if rows
            else 0.0
            for name in finite_numeric
        },
        "invalid_finite_numeric_counts": invalid_finite_numeric,
        "invalid_numeric_format_counts": invalid_numeric_formats,
        "non_finite_numeric_counts": non_finite_numeric,
        "invalid_date_format_counts": invalid_date_formats,
        "malformed_csv_row_width_count": malformed_width_rows,
        "extra_field_row_count": extra_field_rows,
        "missing_field_row_count": missing_field_rows,
        "malformed_csv_row_width_rate": round(malformed_width_rows / rows, 10)
        if rows
        else 0.0,
        "duplicate_logical_key_row_count": duplicate_logical_key_rows,
        "duplicate_logical_key_row_rate": round(
            duplicate_logical_key_rows / rows, 10
        )
        if rows
        else 0.0,
        "logical_key_columns": list(logical_key_columns),
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


def _structural_integrity_fields(scan: Mapping[str, Any]) -> dict[str, Any]:
    malformed = int(scan["malformed_csv_row_width_count"])
    duplicates = int(scan["duplicate_logical_key_row_count"])
    return {
        "malformed_csv_row_width_count": malformed,
        "extra_field_row_count": int(scan["extra_field_row_count"]),
        "missing_field_row_count": int(scan["missing_field_row_count"]),
        "malformed_csv_row_width_rate": scan["malformed_csv_row_width_rate"],
        "duplicate_logical_key_row_count": duplicates,
        "duplicate_logical_key_row_rate": scan["duplicate_logical_key_row_rate"],
        "logical_key_columns": list(scan["logical_key_columns"]),
        "structural_integrity_verified": malformed == 0 and duplicates == 0,
    }


def _normalized_logical_key(
    row: Mapping[str | None, Any],
    *,
    columns: Sequence[str],
    date_columns: Sequence[str],
) -> tuple[str, ...] | None:
    if not columns:
        return None
    normalized: list[str] = []
    for name in columns:
        raw_value = row.get(name)
        text = str(raw_value or "").strip()
        if not text:
            return None
        if name in date_columns:
            parsed, invalid_format = _optional_canonical_date(raw_value)
            if invalid_format:
                return None
            if parsed is None:
                return None
            text = parsed.isoformat()
        elif name == "symbol":
            text = text.upper()
        normalized.append(text)
    return tuple(normalized)


def _date_column_values(raw_csv: bytes, column: str) -> list[date]:
    values: list[date] = []
    with io.TextIOWrapper(
        io.BytesIO(raw_csv), encoding="utf-8-sig", newline=""
    ) as handle:
        reader = csv.DictReader(handle)
        if column not in (reader.fieldnames or ()):
            return values
        for row in reader:
            parsed, _ = _optional_canonical_date(row.get(column))
            if parsed is not None:
                values.append(parsed)
    return values


def _quote_symbol_index(
    raw_csv: bytes,
) -> tuple[set[str], Mapping[date, SetABC[str]]]:
    symbol_to_bit: dict[str, int] = {}
    symbols_by_bit: list[str] = []
    date_masks: dict[date, int] = {}
    with io.TextIOWrapper(
        io.BytesIO(raw_csv), encoding="utf-8-sig", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            symbol = (row.get("symbol") or "").strip()
            trade_date, _ = _optional_canonical_date(row.get("date"))
            if trade_date is None:
                continue
            # Preserve every valid observed quote date even when a malformed
            # row has no symbol.  Structural gates still block that row, while
            # date-level aggregates retain their pre-bitmap semantics.
            date_masks.setdefault(trade_date, 0)
            if not symbol:
                continue
            bit = symbol_to_bit.get(symbol)
            if bit is None:
                bit = len(symbols_by_bit)
                symbol_to_bit[symbol] = bit
                symbols_by_bit.append(symbol)
            date_masks[trade_date] = date_masks.get(trade_date, 0) | (1 << bit)
    return set(symbol_to_bit), _SymbolBitmapIndex(
        symbol_to_bit=symbol_to_bit,
        symbols_by_bit=symbols_by_bit,
        date_masks=date_masks,
    )


def _quote_contract_monthly_coverage(
    *,
    dated_quote_symbols: Mapping[date, SetABC[str]],
    official_sessions: Sequence[date],
    expected_months: Sequence[str],
    eligible_master_symbols: set[str],
    minimum_symbols: int,
    master_lifecycles: Mapping[str, tuple[date, date | None]] | None = None,
    complete_symbols_by_month: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    """Count per-symbol quote availability for every fixed signal session.

    This check uses only identifier/date presence.  It never reads a price,
    return, signal value, cross-sectional rank, or implementation outcome.
    """

    ordered_sessions = sorted(set(official_sessions))
    session_index = {
        session: index for index, session in enumerate(ordered_sessions)
    }
    sessions_by_month: dict[str, list[date]] = {}
    for session in ordered_sessions:
        sessions_by_month.setdefault(session.strftime("%Y-%m"), []).append(session)

    def symbols_present_on(
        required_sessions: Sequence[date], universe: set[str]
    ) -> set[str]:
        present = set(universe)
        for required_session in required_sessions:
            present.intersection_update(
                dated_quote_symbols.get(required_session, set())
            )
            if not present:
                break
        return present

    rows: list[dict[str, Any]] = []
    for month in expected_months:
        month_sessions = sessions_by_month.get(month, [])
        rebalance = min(month_sessions) if month_sessions else None
        active_symbols = (
            _active_strict_a_share_symbols(master_lifecycles, rebalance)
            if master_lifecycles is not None
            else set(eligible_master_symbols)
        )
        position = session_index.get(rebalance) if rebalance is not None else None
        geometry_available = bool(
            position is not None
            and position >= 60
            and position + 21 < len(ordered_sessions)
        )
        if geometry_available:
            assert position is not None
            momentum_start = ordered_sessions[position - 60]
            volatility_start = ordered_sessions[position - 20]
            amount_start = ordered_sessions[position - 19]
            lag_entry = ordered_sessions[position + 1]
            no_lag_exit = ordered_sessions[position + 20]
            lag_exit = ordered_sessions[position + 21]
            momentum_sessions = tuple(
                ordered_sessions[position - 60 : position + 1]
            )
            volatility_sessions = tuple(
                ordered_sessions[position - 20 : position + 1]
            )
            amount_sessions = tuple(
                ordered_sessions[position - 19 : position + 1]
            )
            endpoint_sessions = (
                rebalance,
                lag_entry,
                no_lag_exit,
                lag_exit,
            )
            complete_sessions = tuple(
                sorted(
                    set(momentum_sessions)
                    | set(volatility_sessions)
                    | set(amount_sessions)
                    | set(endpoint_sessions)
                )
            )
            rebalance_symbols = symbols_present_on((rebalance,), active_symbols)
            momentum_symbols = symbols_present_on(momentum_sessions, active_symbols)
            volatility_symbols = symbols_present_on(
                volatility_sessions, active_symbols
            )
            amount_symbols = symbols_present_on(amount_sessions, active_symbols)
            endpoint_symbols = symbols_present_on(endpoint_sessions, active_symbols)
            complete_symbols = symbols_present_on(complete_sessions, active_symbols)
        else:
            momentum_start = None
            volatility_start = None
            amount_start = None
            lag_entry = None
            no_lag_exit = None
            lag_exit = None
            rebalance_symbols = set()
            momentum_symbols = set()
            volatility_symbols = set()
            amount_symbols = set()
            endpoint_symbols = set()
            complete_symbols = set()
        if complete_symbols_by_month is not None:
            # Private in-memory bridge to the fundamental support audit.  Only
            # aggregate intersection counts enter the public report.
            complete_symbols_by_month[month] = complete_symbols
        rows.append(
            {
                "month": month,
                "rebalance_date": rebalance.isoformat() if rebalance else None,
                "momentum_start_date": (
                    momentum_start.isoformat() if momentum_start else None
                ),
                "volatility_start_date": (
                    volatility_start.isoformat() if volatility_start else None
                ),
                "amount_start_date": amount_start.isoformat() if amount_start else None,
                "lag_entry_date": lag_entry.isoformat() if lag_entry else None,
                "no_lag_exit_date": (
                    no_lag_exit.isoformat() if no_lag_exit else None
                ),
                "lag_exit_date": lag_exit.isoformat() if lag_exit else None,
                "required_session_geometry_available": geometry_available,
                "active_strict_a_share_symbol_count": len(active_symbols),
                "rebalance_symbol_count": len(rebalance_symbols),
                "signal_session_candidate_symbol_count": len(rebalance_symbols),
                "momentum_60d_symbol_count": len(momentum_symbols),
                "low_volatility_20d_symbol_count": len(volatility_symbols),
                "amount_20d_symbol_count": len(amount_symbols),
                "exact_endpoint_symbol_count": len(endpoint_symbols),
                "missing_exact_endpoint_candidate_count": len(
                    rebalance_symbols - endpoint_symbols
                ),
                "all_signal_session_candidates_have_exact_endpoints": (
                    endpoint_symbols == rebalance_symbols
                ),
                "complete_quote_contract_symbol_count": len(complete_symbols),
            }
        )

    component_keys = {
        "momentum_60d_history": "momentum_60d_symbol_count",
        "low_volatility_20d_history": "low_volatility_20d_symbol_count",
        "amount_20d_history": "amount_20d_symbol_count",
        "exact_endpoint": "exact_endpoint_symbol_count",
        "complete_quote_contract": "complete_quote_contract_symbol_count",
    }
    result: dict[str, Any] = {"monthly_coverage": rows}
    for label, count_key in component_keys.items():
        insufficient = [
            {"month": row["month"], count_key: row[count_key]}
            for row in rows
            if row[count_key] < minimum_symbols
        ]
        result[f"{label}_coverage_met"] = not insufficient
        result[f"insufficient_{label}_months"] = insufficient
        result[f"minimum_{label}_symbol_count"] = min(
            (row[count_key] for row in rows), default=0
        )
    result["required_session_geometry_coverage_met"] = all(
        row["required_session_geometry_available"] for row in rows
    )
    incomplete_candidate_months = [
        {
            "month": row["month"],
            "signal_session_candidate_symbol_count": row[
                "signal_session_candidate_symbol_count"
            ],
            "exact_endpoint_symbol_count": row["exact_endpoint_symbol_count"],
            "missing_exact_endpoint_candidate_count": row[
                "missing_exact_endpoint_candidate_count"
            ],
        }
        for row in rows
        if not row["all_signal_session_candidates_have_exact_endpoints"]
    ]
    result["all_signal_session_candidates_have_exact_endpoints"] = not (
        incomplete_candidate_months
    )
    result["incomplete_signal_session_candidate_endpoint_months"] = (
        incomplete_candidate_months
    )
    return result


def _strict_a_share_master_symbols(raw_csv: bytes) -> set[str]:
    symbols: set[str] = set()
    with io.TextIOWrapper(
        io.BytesIO(raw_csv), encoding="utf-8-sig", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            if _is_strict_a_share_master_row(row):
                symbols.add((row.get("symbol") or "").strip())
    return symbols


def _strict_a_share_master_lifecycles(
    raw_csv: bytes,
) -> dict[str, tuple[date, date | None]]:
    """Return valid strict SH/SZ A-share listing intervals by identifier.

    The interval is closed on both ends: a security contributes to a target
    rebalance only when ``listDate <= signal_date <= delistDate`` (or when no
    delist date is recorded). Rows with malformed or contradictory dates are
    omitted here and remain a blocking membership-integrity finding in the
    master scan.
    """

    lifecycles: dict[str, tuple[date, date | None]] = {}
    invalid_symbols: set[str] = set()
    with io.TextIOWrapper(
        io.BytesIO(raw_csv), encoding="utf-8-sig", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            if not _is_strict_a_share_master_row(row):
                continue
            symbol = (row.get("symbol") or "").strip()
            list_date, list_date_invalid = _optional_master_date(row.get("listDate"))
            delist_date, delist_date_invalid = _optional_master_date(
                row.get("delistDate")
            )
            if (
                list_date_invalid
                or delist_date_invalid
                or list_date is None
                or (delist_date is not None and delist_date < list_date)
                or symbol in lifecycles
                or symbol in invalid_symbols
            ):
                # Fail closed for malformed or duplicate lifecycle records.
                lifecycles.pop(symbol, None)
                invalid_symbols.add(symbol)
                continue
            lifecycles[symbol] = (list_date, delist_date)
    return lifecycles


def _active_strict_a_share_symbols(
    lifecycles: Mapping[str, tuple[date, date | None]],
    signal_date: date | None,
) -> set[str]:
    """Construct the point-in-time strict A-share universe for a signal day."""

    if signal_date is None:
        return set()
    return {
        symbol
        for symbol, (list_date, delist_date) in lifecycles.items()
        if list_date <= signal_date
        and (delist_date is None or signal_date <= delist_date)
    }


def _is_strict_a_share_master_row(row: Mapping[str, Any]) -> bool:
    symbol = (row.get("symbol") or "").strip()
    stock_type = (row.get("stockType") or "").strip()
    return bool(
        stock_type == "A股"
        and re.fullmatch(r"[0-9]{6}\.(?:SH|SZ)", symbol)
    )


def _optional_master_date(value: Any) -> tuple[date | None, bool]:
    return _optional_canonical_date(value)


def _fundamental_monthly_coverage(
    *,
    raw_csv: bytes,
    expected_months: Sequence[str],
    official_sessions: set[date],
    monthly_quote_symbols: Mapping[str, SetABC[str]],
    eligible_master_symbols: set[str],
    eligible_universe_symbols: set[str],
    complete_quote_contract_symbols_by_month: Mapping[str, set[str]],
    required_start: date,
    required_end: date,
    maximum_staleness_months: int,
    master_lifecycles: Mapping[str, tuple[date, date | None]] | None = None,
) -> dict[str, Any]:
    sessions_by_month: dict[str, list[date]] = {}
    for session in official_sessions:
        sessions_by_month.setdefault(session.strftime("%Y-%m"), []).append(session)
    active_quote_symbols_by_month: dict[str, set[str]] = {}
    complete_contract_symbols_by_month: dict[str, set[str]] = {}
    for month in expected_months:
        sessions = sessions_by_month.get(month, [])
        signal_date = min(sessions) if sessions else None
        active_symbols = (
            _active_strict_a_share_symbols(master_lifecycles, signal_date)
            if master_lifecycles is not None
            else set(eligible_master_symbols)
        )
        active_quote_symbols_by_month[month] = (
            monthly_quote_symbols.get(month, set()) & active_symbols
        )
        complete_contract_symbols_by_month[month] = (
            set(complete_quote_contract_symbols_by_month.get(month, set()))
            & active_quote_symbols_by_month[month]
            & eligible_universe_symbols
        )
    scoped_signal_symbols = set().union(*active_quote_symbols_by_month.values())
    scoped_signal_symbols.intersection_update(eligible_universe_symbols)
    histories: dict[str, list[tuple[date, date, bool]]] = {}
    eligible_interval_rows = 0
    eligible_interval_publish_dates = 0
    invalid_publication_order_rows = 0
    with io.TextIOWrapper(
        io.BytesIO(raw_csv), encoding="utf-8-sig", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            symbol = (row.get("symbol") or "").strip()
            if symbol not in scoped_signal_symbols:
                continue
            report_end, _ = _optional_canonical_date(row.get("reportPeriodEnd"))
            publish_date, _ = _optional_canonical_date(row.get("publishDate"))
            roe_present = _is_finite_numeric(row.get("roeDiluted"))
            if report_end is not None and required_start <= report_end <= required_end:
                eligible_interval_rows += 1
                if publish_date is not None:
                    eligible_interval_publish_dates += 1
            if report_end is None or publish_date is None:
                continue
            if publish_date < report_end:
                if (
                    roe_present
                    and required_start <= report_end <= required_end
                ):
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
        eligible_quote_symbols = active_quote_symbols_by_month.get(month, set())
        available = 0
        nonstale = 0
        stale = 0
        available_complete_contract = 0
        nonstale_complete_contract = 0
        stale_complete_contract = 0
        complete_contract_symbols = complete_contract_symbols_by_month.get(
            month, set()
        )
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
                is_complete_contract_symbol = symbol in complete_contract_symbols
                if is_complete_contract_symbol:
                    available_complete_contract += 1
                staleness_cutoff = _subtract_calendar_months(
                    signal_date, maximum_staleness_months
                )
                if report_end >= staleness_cutoff:
                    nonstale += 1
                    if is_complete_contract_symbol:
                        nonstale_complete_contract += 1
                else:
                    stale += 1
                    if is_complete_contract_symbol:
                        stale_complete_contract += 1
        rows.append(
            {
                "month": month,
                "rebalance_date": signal_date.isoformat() if signal_date else None,
                "eligible_quote_symbol_count": len(eligible_quote_symbols),
                "complete_quote_contract_symbol_count": len(
                    complete_contract_symbols
                ),
                "active_strict_a_share_symbol_count": len(
                    _active_strict_a_share_symbols(master_lifecycles, signal_date)
                    if master_lifecycles is not None
                    else eligible_master_symbols
                ),
                "available_fundamental_symbol_count": available,
                "nonstale_fundamental_symbol_count": nonstale,
                "stale_fundamental_symbol_count": stale,
                "available_complete_contract_fundamental_symbol_count": (
                    available_complete_contract
                ),
                "nonstale_complete_contract_fundamental_symbol_count": (
                    nonstale_complete_contract
                ),
                "stale_complete_contract_fundamental_symbol_count": (
                    stale_complete_contract
                ),
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
        "eligible_scope_publication_before_report_period_end_row_count": (
            invalid_publication_order_rows
        ),
        "publication_order_check_scope": (
            "strict SH/SZ A-share symbols quoted on at least one target rebalance; "
            "roeDiluted finite numeric; reportPeriodEnd within the required fundamental "
            "interval"
        ),
        "eligible_scope_publication_order_check_scope": (
            "strict SH/SZ A-share symbols quoted on at least one target rebalance; "
            "roeDiluted finite numeric; reportPeriodEnd within the required fundamental "
            "interval; aggregate counts only"
        ),
        "maximum_staleness_months": maximum_staleness_months,
        "complete_quote_fundamental_joint_support_basis": (
            "nonstale fundamental availability intersected with the same private "
            "identifier set that satisfies the full per-symbol quote contract; "
            "only aggregate counts are reported"
        ),
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


def _optional_canonical_date(value: Any) -> tuple[date | None, bool]:
    raw_text = str(value or "")
    text = raw_text.strip()
    if not text:
        return None, False
    if raw_text != text or CANONICAL_DATE_PATTERN.fullmatch(text) is None:
        return None, True
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return None, True
    if parsed < CANONICAL_DATE_MIN or parsed > CANONICAL_DATE_MAX:
        return None, True
    return parsed, False


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise StudyV2CoverageError(f"invalid ISO date: {text!r}") from exc


def _is_finite_numeric(value: Any) -> bool:
    _, status = _canonical_numeric_value(value)
    return status == "valid"


def _canonical_numeric_value(value: Any) -> tuple[float | None, str]:
    raw_text = str(value or "")
    text = raw_text.strip()
    if not text or _is_na_like_token(text):
        return None, "blank" if not text else "invalid_format"
    if raw_text != text or CANONICAL_DECIMAL_PATTERN.fullmatch(text) is None:
        return None, "invalid_format"
    try:
        number = float(text)
    except (OverflowError, ValueError):
        return None, "invalid_format"
    if not math.isfinite(number):
        return None, "non_finite"
    return number, "valid"


def _is_na_like_token(value: Any) -> bool:
    return str(value or "").strip().casefold() in NA_LIKE_TOKENS


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


def _expected_review_input_identity(
    *,
    identities: Mapping[str, Mapping[str, Any]],
    quotes: Mapping[str, Any],
    master: Mapping[str, Any],
    fundamentals: Mapping[str, Any],
    official_calendar: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return the identity fields a human review must have checked.

    The attestation template intentionally keeps the four raw-file hashes in
    ``input_file_sha256`` and puts independently recomputed dimensions in
    ``input_identity``.  Keeping this projection in one place prevents a
    reviewer from attesting to a hash while silently changing the row/date
    ranges used by the coverage report.
    """

    return {
        "quotes": {
            "byte_size": identities["quotes"]["size_bytes"],
            "row_count": quotes["row_count"],
            "minimum_date": quotes["market_start"],
            "maximum_date": quotes["market_end"],
        },
        "stock_master": {
            "byte_size": identities["stock_master"]["size_bytes"],
            "row_count": master["row_count"],
            "symbol_count": master["symbol_count"],
        },
        "fundamentals": {
            "byte_size": identities["fundamentals"]["size_bytes"],
            "row_count": fundamentals["row_count"],
            "minimum_publish_date": fundamentals["publication_start"],
            "maximum_publish_date": fundamentals["publication_end"],
        },
        "official_calendar": {
            "byte_size": identities["official_calendar"]["size_bytes"],
            "row_count": official_calendar["row_count"],
            "minimum_date": official_calendar["calendar_start"],
            "maximum_date": official_calendar["calendar_end"],
        },
    }


def _attestation_meaningful_text(value: Any, *, minimum_length: int = 4) -> bool:
    if not isinstance(value, str) or len(value.strip()) < minimum_length:
        return False
    lowered = value.strip().lower()
    return not any(
        token in lowered
        for token in ("todo", "tbd", "pending", "placeholder", "unknown")
    )


def _validate_review_attestation(
    value: Mapping[str, Any] | None,
    *,
    expected_file_sha256: Mapping[str, str],
    expected_input_identity: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if value is None:
        return {
            "schema_version": None,
            "coverage_probe_spec_path": None,
            "coverage_probe_spec_sha256": None,
            "coverage_probe_receipt_path": None,
            "coverage_probe_receipt_sha256": None,
            "execution_semantics_verified": False,
            "tradability_fields_verified": False,
            "exact_endpoint_resolution_semantics_verified": False,
            "suspension_valuation_semantics_verified": False,
            "price_adjustment_semantics_verified": False,
            "amount_unit_normalization_semantics_verified": False,
            "endpoint_reason_ledger_rights_verified": False,
            "historical_membership_completeness_verified": False,
            "terminal_survivor_comparator_verified": False,
            "security_identifier_semantics_verified": False,
            "fundamental_publication_semantics_verified": False,
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
        "exact_endpoint_resolution_semantics_verified",
        "suspension_valuation_semantics_verified",
        "price_adjustment_semantics_verified",
        "amount_unit_normalization_semantics_verified",
        "endpoint_reason_ledger_rights_verified",
        "historical_membership_completeness_verified",
        "terminal_survivor_comparator_verified",
        "security_identifier_semantics_verified",
        "fundamental_publication_semantics_verified",
        "data_rights_verified",
        "official_calendar_verified",
    ):
        if value.get(key) is not True:
            raise StudyV2CoverageError(f"review attestation {key} must be true")
    if value.get("coverage_probe_spec_path") != "coverage_probe_spec.v2.json":
        raise StudyV2CoverageError(
            "review attestation coverage probe specification path is invalid"
        )
    if not _is_sha256(value.get("coverage_probe_spec_sha256")):
        raise StudyV2CoverageError(
            "review attestation coverage probe specification hash is invalid"
        )
    if value.get("coverage_probe_receipt_path") != "coverage_probe_receipt.v2.json":
        raise StudyV2CoverageError(
            "review attestation coverage probe receipt path is invalid"
        )
    if not _is_sha256(value.get("coverage_probe_receipt_sha256")):
        raise StudyV2CoverageError(
            "review attestation coverage probe receipt hash is invalid"
        )
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
    if (
        not isinstance(input_hashes, Mapping)
        or set(input_hashes) != set(INPUT_ROLES)
        or any(not _is_sha256(input_hashes.get(role)) for role in INPUT_ROLES)
        or dict(input_hashes) != dict(expected_file_sha256)
    ):
        raise StudyV2CoverageError(
            "review attestation is not bound to the audited input files"
        )
    input_identity = value.get("input_identity")
    if (
        not isinstance(input_identity, Mapping)
        or set(input_identity) != set(INPUT_ROLES)
    ):
        raise StudyV2CoverageError(
            "review attestation input identity is missing or has the wrong roles"
        )
    expected_identity_keys = {
        "quotes": {
            "byte_size", "row_count", "minimum_date", "maximum_date"
        },
        "stock_master": {"byte_size", "row_count", "symbol_count"},
        "fundamentals": {
            "byte_size", "row_count", "minimum_publish_date", "maximum_publish_date"
        },
        "official_calendar": {
            "byte_size", "row_count", "minimum_date", "maximum_date",
            "source_name", "source_reference", "source_generated_at", "timezone",
        },
    }
    for role in INPUT_ROLES:
        identity = input_identity.get(role)
        if not isinstance(identity, Mapping):
            raise StudyV2CoverageError(
                f"review attestation input identity for {role} is invalid"
            )
        if set(identity) != expected_identity_keys[role]:
            raise StudyV2CoverageError(
                f"review attestation input identity for {role} is incomplete"
            )
        for key, expected in expected_input_identity[role].items():
            if identity.get(key) != expected:
                descriptor = (
                    "row count"
                    if key == "row_count"
                    else "date range"
                    if key in {
                        "minimum_date",
                        "maximum_date",
                        "minimum_publish_date",
                        "maximum_publish_date",
                    }
                    else key
                )
                raise StudyV2CoverageError(
                    f"review attestation input identity {role} {descriptor} differs "
                    "from recomputed raw input"
                )
        for key in ("byte_size", "row_count"):
            item = identity.get(key)
            if (
                isinstance(item, bool)
                or not isinstance(item, int)
                or item < 0
            ):
                raise StudyV2CoverageError(
                    f"review attestation input identity {role} {key} is invalid"
                )
        if role == "stock_master":
            item = identity.get("symbol_count")
            if isinstance(item, bool) or not isinstance(item, int) or item < 0:
                raise StudyV2CoverageError(
                    "review attestation input identity stock_master symbol_count is invalid"
                )
        else:
            for key in (
                "minimum_date"
                if role in {"quotes", "official_calendar"}
                else "minimum_publish_date",
                "maximum_date"
                if role in {"quotes", "official_calendar"}
                else "maximum_publish_date",
            ):
                _required_date(identity.get(key), f"review attestation {role} {key}")
    calendar_identity = input_identity["official_calendar"]
    if calendar_identity.get("timezone") != "Asia/Shanghai":
        raise StudyV2CoverageError(
            "review attestation official calendar provenance timezone is invalid"
        )
    for key in ("source_name", "source_reference"):
        if not _attestation_meaningful_text(calendar_identity.get(key)):
            raise StudyV2CoverageError(
                "review attestation official calendar provenance is incomplete"
            )
    generated_at = _required_timezone_aware_datetime(
        calendar_identity.get("source_generated_at"),
        "review attestation official calendar provenance generated_at",
    )
    if generated_at > reviewed_time:
        raise StudyV2CoverageError(
            "review attestation official calendar provenance chronology is invalid"
        )
    evidence_hashes = value.get("evidence_sha256")
    if not isinstance(evidence_hashes, Mapping):
        raise StudyV2CoverageError("review attestation evidence hashes are required")
    for key in (
        "execution_semantics",
        "tradability_fields",
        "exact_endpoint_resolution",
        "suspension_valuation_semantics",
        "provider_close_raw_definition",
        "provider_adjustment_factor_convention",
        "price_adjustment_normalization",
        "amount_unit_normalization",
        "endpoint_reason_ledger_rights",
        "historical_membership_completeness",
        "terminal_survivor_comparator",
        "security_identifier_semantics",
        "code_change_mapping",
        "fundamental_publication_semantics",
        "data_rights",
        "official_calendar",
    ):
        if not _is_sha256(evidence_hashes.get(key)):
            raise StudyV2CoverageError(f"review attestation {key} evidence hash is invalid")
    required_assertions = {
        "adjusted_close_return_semantics_and_corporate_action_handling_are_documented",
        "unadjusted_open_and_nonfill_semantics_are_not_claimed_by_the_ic_core",
        "amount_units_and_cutoff_timing_are_documented",
        "provider_raw_amount_unit_and_normalization_to_exact_cny_before_input_binding_are_documented",
        "st_and_suspension_fields_are_non_degenerate_and_historically_effective",
        "signal_eligible_denominator_is_fixed_before_outcome_lookup",
        "current_ic_core_resolves_only_exact_provider_recorded_close_observations_on_required_official_sessions",
        "close_observation_type_matches_suspension_state_on_every_quote_row",
        "suspension_valuation_is_provider_recorded_or_published_for_the_exact_official_session_and_never_researcher_forward_filled",
        "price_adjustment_method_and_convention_tokens_match_the_fixed_contract_on_every_quote_row",
        "close_equals_close_raw_times_adjustment_factor_within_the_fixed_tolerance_on_every_quote_row",
        "provider_close_raw_adjustment_factor_and_no_rebasing_definitions_are_hash_evidenced",
        "all_signal_session_candidates_have_exact_t_t1_t20_t21_endpoints_before_design_freeze",
        "unresolved_endpoints_cannot_be_dropped_shifted_carried_forward_or_assigned_default_recovery",
        "delisting_terminal_wealth_adapter_is_not_claimed_by_the_current_ic_core",
        "private_endpoint_reason_ledger_hash_and_public_aggregate_counts_are_permitted",
        "stock_master_covers_every_strict_sh_sz_a_share_active_at_any_time_from_2009_01_through_2023_01_and_is_not_latest_only",
        "terminal_survivor_comparator_uses_delist_date_null_or_strictly_after_2023_01_31_independent_of_acquisition_date",
        "provider_stable_security_identifier_semantics_are_identical_across_quotes_stock_master_and_fundamentals",
        "historical_security_code_changes_and_reassignments_have_a_documented_reviewed_mapping_before_input_hash_binding",
        "roe_diluted_mapping_is_one_to_one_decimal_and_publish_date_is_actual_recorded_disclosure_date_not_scheduled_or_update_date",
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
        or signature.get("type") != "human_verified_evidence"
        or not _is_sha256(signature.get("evidence_sha256"))
        or not isinstance(signature.get("signer_identity"), str)
        or len(signature["signer_identity"].strip()) < 4
    ):
        raise StudyV2CoverageError("review attestation signature is invalid")
    verification_uri = str(signature.get("verification_uri") or "")
    parsed_uri = urlparse(verification_uri)
    if parsed_uri.scheme != "https" or not parsed_uri.netloc:
        raise StudyV2CoverageError("review attestation verification URI is invalid")
    if signature.get(
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
        "coverage_probe_spec_path": value["coverage_probe_spec_path"],
        "coverage_probe_spec_sha256": value["coverage_probe_spec_sha256"],
        "coverage_probe_receipt_path": value["coverage_probe_receipt_path"],
        "coverage_probe_receipt_sha256": value["coverage_probe_receipt_sha256"],
        "execution_semantics_verified": value["execution_semantics_verified"],
        "tradability_fields_verified": value["tradability_fields_verified"],
        "exact_endpoint_resolution_semantics_verified": value[
            "exact_endpoint_resolution_semantics_verified"
        ],
        "suspension_valuation_semantics_verified": value[
            "suspension_valuation_semantics_verified"
        ],
        "price_adjustment_semantics_verified": value[
            "price_adjustment_semantics_verified"
        ],
        "amount_unit_normalization_semantics_verified": value[
            "amount_unit_normalization_semantics_verified"
        ],
        "endpoint_reason_ledger_rights_verified": value[
            "endpoint_reason_ledger_rights_verified"
        ],
        "historical_membership_completeness_verified": value[
            "historical_membership_completeness_verified"
        ],
        "terminal_survivor_comparator_verified": value[
            "terminal_survivor_comparator_verified"
        ],
        "security_identifier_semantics_verified": value[
            "security_identifier_semantics_verified"
        ],
        "fundamental_publication_semantics_verified": value[
            "fundamental_publication_semantics_verified"
        ],
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
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _raw_csv_bytes(value: Any, label: str) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise StudyV2CoverageError(f"{label} raw CSV must be bytes")
    return bytes(value)


def _normalized_input_names(value: Mapping[str, str] | None) -> dict[str, str]:
    supplied: Mapping[str, str] = PUBLIC_INPUT_FILE_NAMES if value is None else value
    if not isinstance(supplied, Mapping) or set(supplied) != set(INPUT_ROLES):
        raise StudyV2CoverageError(
            "input_names must contain exactly quotes, stock_master, fundamentals, "
            "and official_calendar"
        )
    for role in INPUT_ROLES:
        raw_name = supplied[role]
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise StudyV2CoverageError(f"input_names {role} must be a non-empty string")
    return dict(PUBLIC_INPUT_FILE_NAMES)


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
        "terminal_survivor_cutoff",
        "security_identifier_contract_id",
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
    candidate = Path(value).expanduser()
    if candidate.is_symlink():
        raise StudyV2CoverageError(f"{label} is not a regular file")
    path = candidate.resolve(strict=False)
    if not path.is_file() or path.is_symlink():
        raise StudyV2CoverageError(f"{label} is not a regular file")
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
    try:
        output = require_new_private_file_target(
            args.output,
            label="authoritative coverage report target",
        )
    except PrivateArtifactPathError as exc:
        raise StudyV2CoverageError(str(exc)) from exc
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
    write_coverage_report(report, output)
    print(
        "READY" if report["gates"]["ready_to_lock_stage2_plan"] else "BLOCKED",
        output,
    )
    return 0 if report["gates"]["ready_to_lock_stage2_plan"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
