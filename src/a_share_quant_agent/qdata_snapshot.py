"""Strict, database-free consumer for QData ``research_snapshot_v1`` bundles."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from .data_sources import (
    DataLoadResult,
    DataSourceError,
    DataSourceMetadata,
    dataframe_hash,
    prepare_backtest_panel,
)


SCHEMA_VERSION = "research_snapshot_v1"
MANIFEST_FILENAME = "manifest.json"


class QDataSnapshotError(DataSourceError):
    """Raised when a QData snapshot cannot be trusted or adapted."""


@dataclass(frozen=True)
class _DatasetContract:
    columns: tuple[str, ...]
    primary_key: tuple[str, ...]
    date_field: str
    kinds: Mapping[str, str]
    nullable: frozenset[str] = frozenset()


_CONTRACTS: Mapping[str, _DatasetContract] = {
    "daily_bar": _DatasetContract(
        columns=(
            "symbol", "trade_date", "open_raw", "high_raw", "low_raw",
            "close_raw", "close_adjusted", "adjustment_factor", "volume",
            "amount", "bar_end_at", "available_at", "source_id", "batch_id",
            "data_version",
        ),
        primary_key=("symbol", "trade_date"),
        date_field="trade_date",
        kinds={
            "symbol": "string", "trade_date": "date", "open_raw": "number",
            "high_raw": "number", "low_raw": "number", "close_raw": "number",
            "close_adjusted": "number", "adjustment_factor": "number",
            "volume": "number", "amount": "number", "bar_end_at": "timestamp",
            "available_at": "timestamp", "source_id": "string", "batch_id": "string",
            "data_version": "string",
        },
    ),
    "tradability": _DatasetContract(
        columns=(
            "symbol", "trade_date", "is_st", "is_suspended", "limit_up",
            "limit_down", "is_limit_up", "is_limit_down", "can_buy", "can_sell",
            "lot_size", "t_plus_one", "available_at",
        ),
        primary_key=("symbol", "trade_date"),
        date_field="trade_date",
        kinds={
            "symbol": "string", "trade_date": "date", "is_st": "boolean",
            "is_suspended": "boolean", "limit_up": "number", "limit_down": "number",
            "is_limit_up": "boolean", "is_limit_down": "boolean", "can_buy": "boolean",
            "can_sell": "boolean", "lot_size": "integer", "t_plus_one": "boolean",
            "available_at": "timestamp",
        },
        nullable=frozenset({"limit_up", "limit_down"}),
    ),
    "security_membership": _DatasetContract(
        columns=(
            "symbol", "list_date", "delist_date", "valid_from", "valid_to", "board",
            "asset_type", "status", "available_at",
        ),
        primary_key=("symbol", "valid_from"),
        date_field="valid_from",
        kinds={
            "symbol": "string", "list_date": "date", "delist_date": "date",
            "valid_from": "date", "valid_to": "date", "board": "string",
            "asset_type": "string", "status": "string", "available_at": "timestamp",
        },
        nullable=frozenset({"delist_date", "valid_to"}),
    ),
    "fundamental_pit": _DatasetContract(
        columns=(
            "symbol", "report_period_end", "field_name", "field_value", "published_at",
            "first_seen_at", "available_at", "revision_id", "is_restated", "source_id",
        ),
        primary_key=("symbol", "report_period_end", "field_name", "revision_id"),
        date_field="report_period_end",
        kinds={
            "symbol": "string", "report_period_end": "date", "field_name": "string",
            "field_value": "number", "published_at": "timestamp",
            "first_seen_at": "timestamp", "available_at": "timestamp",
            "revision_id": "string", "is_restated": "boolean", "source_id": "string",
        },
    ),
}

_MANIFEST_KEYS = {
    "schema_version", "snapshot_id", "format", "cutoff_ts", "timezone", "source",
    "data_version", "quality_status", "artifact_notice", "datasets",
}
_DATASET_METADATA_KEYS = {
    "path", "sha256", "row_count", "columns", "primary_key", "date_field", "date_range",
}


def verify_qdata_snapshot(snapshot_dir: str | Path) -> dict[str, Any]:
    """Independently verify a QData snapshot without importing QData."""

    manifest, _ = _verify_snapshot(Path(snapshot_dir))
    return manifest


def load_qdata_snapshot(snapshot_dir: str | Path) -> DataLoadResult:
    """Verify and adapt a frozen QData snapshot into the backtest panel contract."""

    manifest, rows = _verify_snapshot(Path(snapshot_dir))
    data, universe, stock_master = _adapt_rows(rows)
    dataset_versions = tuple((name, str(manifest["data_version"])) for name in sorted(_CONTRACTS))
    daily_source_ids = sorted({row["source_id"] for row in rows["daily_bar"]})
    daily_batch_ids = sorted({row["batch_id"] for row in rows["daily_bar"]})
    fundamental_source_ids = sorted({row["source_id"] for row in rows["fundamental_pit"]})
    lineage = [("snapshot", str(manifest["source"]))]
    lineage.extend(("daily_bar.source_id", value) for value in daily_source_ids)
    lineage.extend(("daily_bar.batch_id", value) for value in daily_batch_ids)
    lineage.extend(("fundamental_pit.source_id", value) for value in fundamental_source_ids)
    notes = (
        "Verified QData research_snapshot_v1; all files, hashes, schemas, keys, and PIT cutoffs passed.",
        "Signal time is max(daily_bar.available_at, tradability.available_at).",
        "Execution open and close map only from raw OHLC; close_adjusted is retained separately.",
    )
    return DataLoadResult(
        data=data,
        universe=universe,
        stock_master=stock_master,
        metadata=DataSourceMetadata(
            source=f"qdata_snapshot:{manifest['source']}+pit_membership+pit_fundamentals",
            symbols=tuple(sorted(data["symbol"].unique())),
            start_date=str(data["date"].min().date()),
            end_date=str(data["date"].max().date()),
            notes=notes,
            data_hash=dataframe_hash(data),
            snapshot_id=str(manifest["snapshot_id"]),
            schema_version=str(manifest["schema_version"]),
            cutoff_ts=str(manifest["cutoff_ts"]),
            dataset_versions=dataset_versions,
            source_lineage=tuple(lineage),
        ),
    )


def _verify_snapshot(root: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, str]]]]:
    directory_fd, directory_identity = _open_regular_directory(root)
    file_fds: dict[str, int] = {}
    try:
        payloads, file_fds, file_identities = _read_snapshot_payloads(directory_fd)
        manifest_payload = payloads[MANIFEST_FILENAME]
        manifest = _read_manifest(manifest_payload)
        cutoff = _parse_timestamp(manifest["cutoff_ts"], "cutoff_ts")
        timezone_name = _required_string(manifest["timezone"], "timezone")
        try:
            snapshot_timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise QDataSnapshotError(f"unknown IANA timezone: {timezone_name}") from exc
        data_version = _required_string(manifest["data_version"], "data_version")
        _validate_manifest_values(manifest, cutoff)

        rows_by_dataset: dict[str, list[dict[str, str]]] = {}
        for name, contract in _CONTRACTS.items():
            payload = payloads[f"{name}.csv"]
            metadata = manifest["datasets"][name]
            if metadata["sha256"] != _sha256(payload):
                raise QDataSnapshotError(f"SHA256 mismatch for {name}.csv")
            rows = _read_and_canonicalize_csv(
                name,
                contract,
                payload,
                cutoff=cutoff,
                data_version=data_version,
                snapshot_timezone=snapshot_timezone,
            )
            expected_metadata = _dataset_metadata(name, contract, rows, payload)
            if metadata != expected_metadata:
                raise QDataSnapshotError(f"manifest metadata mismatch for {name}")
            rows_by_dataset[name] = rows

        _validate_cross_dataset(rows_by_dataset, snapshot_timezone=snapshot_timezone)
        without_id = dict(manifest)
        claimed_id = without_id.pop("snapshot_id")
        expected_id = "sha256:" + _sha256(_canonical_json_bytes(without_id))
        if claimed_id != expected_id:
            raise QDataSnapshotError("snapshot_id does not match manifest content")
        _recheck_snapshot_contents(
            root,
            directory_fd,
            directory_identity=directory_identity,
            file_fds=file_fds,
            file_identities=file_identities,
            initial_payloads=payloads,
        )
        return manifest, rows_by_dataset
    finally:
        for file_fd in file_fds.values():
            os.close(file_fd)
        os.close(directory_fd)


_DirectoryIdentity = tuple[int, int, int, int]
_FileIdentity = tuple[int, int, int, int, int]


def _open_regular_directory(path: Path) -> tuple[int, _DirectoryIdentity]:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise QDataSnapshotError(
            "platform lacks O_NOFOLLOW/O_DIRECTORY; secure verification is unavailable"
        )
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        directory_fd = os.open(os.fspath(path), flags)
    except (OSError, NotImplementedError) as exc:
        raise QDataSnapshotError(
            f"snapshot path is not a regular directory without symlinks: {path}"
        ) from exc
    metadata = os.fstat(directory_fd)
    if not stat.S_ISDIR(metadata.st_mode):
        os.close(directory_fd)
        raise QDataSnapshotError(f"snapshot path is not a regular directory: {path}")
    return directory_fd, _directory_identity(metadata)


def _read_snapshot_payloads(
    directory_fd: int,
) -> tuple[dict[str, bytes], dict[str, int], dict[str, _FileIdentity]]:
    expected = _expected_snapshot_filenames()
    try:
        actual = set(os.listdir(directory_fd))
    except (OSError, TypeError, NotImplementedError) as exc:
        raise QDataSnapshotError("cannot enumerate snapshot directory") from exc
    if actual != expected:
        raise QDataSnapshotError(
            f"snapshot file set mismatch; missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    payloads: dict[str, bytes] = {}
    file_fds: dict[str, int] = {}
    identities: dict[str, _FileIdentity] = {}
    try:
        for filename in sorted(expected):
            file_fd, payload, identity = _open_and_read_regular_file_at(
                directory_fd, filename
            )
            file_fds[filename] = file_fd
            payloads[filename] = payload
            identities[filename] = identity
        return payloads, file_fds, identities
    except BaseException:
        for file_fd in file_fds.values():
            os.close(file_fd)
        raise


def _open_and_read_regular_file_at(
    directory_fd: int,
    filename: str,
) -> tuple[int, bytes, _FileIdentity]:
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        file_fd = os.open(filename, flags, dir_fd=directory_fd)
    except (OSError, NotImplementedError) as exc:
        raise QDataSnapshotError(
            f"{filename} must be a regular file without symlinks"
        ) from exc
    try:
        before = os.fstat(file_fd)
        _validate_open_file_metadata(filename, before)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(file_fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        payload = b"".join(chunks)
        after = os.fstat(file_fd)
        _validate_open_file_metadata(filename, after)
        before_identity = _file_identity(before)
        after_identity = _file_identity(after)
        if before_identity != after_identity or after.st_size != len(payload):
            raise QDataSnapshotError(f"{filename} changed while it was being read")
        return file_fd, payload, after_identity
    except BaseException:
        os.close(file_fd)
        raise


def _validate_open_file_metadata(filename: str, metadata: os.stat_result) -> None:
    if not stat.S_ISREG(metadata.st_mode):
        raise QDataSnapshotError(f"{filename} must be a regular file")
    if metadata.st_nlink != 1:
        raise QDataSnapshotError(f"{filename} is exposed through a hard link")


def _file_identity(metadata: os.stat_result) -> _FileIdentity:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _directory_identity(metadata: os.stat_result) -> _DirectoryIdentity:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _recheck_snapshot_contents(
    root: Path,
    directory_fd: int,
    *,
    directory_identity: _DirectoryIdentity,
    file_fds: Mapping[str, int],
    file_identities: Mapping[str, _FileIdentity],
    initial_payloads: Mapping[str, bytes],
) -> None:
    _recheck_directory_state(
        root,
        directory_fd,
        directory_identity=directory_identity,
        expected_names=set(file_identities),
    )
    if set(file_fds) != set(file_identities) or set(initial_payloads) != set(file_identities):
        raise QDataSnapshotError("snapshot file handles changed during verification")

    for filename in sorted(file_identities):
        expected_identity = file_identities[filename]
        file_fd = file_fds[filename]
        try:
            before = os.fstat(file_fd)
            _validate_open_file_metadata(filename, before)
            final_digest, final_size = _hash_open_file(file_fd)
            after = os.fstat(file_fd)
            _validate_open_file_metadata(filename, after)
        except OSError as exc:
            raise QDataSnapshotError(f"{filename} changed during verification") from exc
        if (
            _file_identity(before) != expected_identity
            or _file_identity(after) != expected_identity
            or final_size != expected_identity[2]
            or final_digest != _sha256(initial_payloads[filename])
        ):
            raise QDataSnapshotError(f"{filename} changed during verification")
        _recheck_directory_entry(
            directory_fd,
            filename=filename,
            expected_identity=expected_identity,
        )

    _recheck_directory_state(
        root,
        directory_fd,
        directory_identity=directory_identity,
        expected_names=set(file_identities),
    )
    for filename in sorted(file_identities):
        expected_identity = file_identities[filename]
        try:
            metadata = os.fstat(file_fds[filename])
            _validate_open_file_metadata(filename, metadata)
        except OSError as exc:
            raise QDataSnapshotError(f"{filename} changed during verification") from exc
        if _file_identity(metadata) != expected_identity:
            raise QDataSnapshotError(f"{filename} changed during verification")
        _recheck_directory_entry(
            directory_fd,
            filename=filename,
            expected_identity=expected_identity,
        )


def _hash_open_file(file_fd: int) -> tuple[str, int]:
    os.lseek(file_fd, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    total_size = 0
    while True:
        chunk = os.read(file_fd, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
        total_size += len(chunk)
    return digest.hexdigest(), total_size


def _recheck_directory_state(
    root: Path,
    directory_fd: int,
    *,
    directory_identity: _DirectoryIdentity,
    expected_names: set[str],
) -> None:
    try:
        root_metadata = os.stat(root, follow_symlinks=False)
        open_metadata = os.fstat(directory_fd)
    except (OSError, NotImplementedError) as exc:
        raise QDataSnapshotError("snapshot directory changed during verification") from exc
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or not stat.S_ISDIR(open_metadata.st_mode)
        or _directory_identity(root_metadata) != directory_identity
        or _directory_identity(open_metadata) != directory_identity
    ):
        raise QDataSnapshotError("snapshot directory changed during verification")
    try:
        current_names = set(os.listdir(directory_fd))
    except (OSError, TypeError, NotImplementedError) as exc:
        raise QDataSnapshotError("snapshot directory changed during verification") from exc
    if current_names != expected_names:
        raise QDataSnapshotError("snapshot file set changed during verification")


def _recheck_directory_entry(
    directory_fd: int,
    *,
    filename: str,
    expected_identity: _FileIdentity,
) -> None:
    try:
        metadata = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
    except (OSError, NotImplementedError) as exc:
        raise QDataSnapshotError(f"{filename} changed during verification") from exc
    _validate_open_file_metadata(filename, metadata)
    if _file_identity(metadata) != expected_identity:
        raise QDataSnapshotError(f"{filename} changed during verification")


def _expected_snapshot_filenames() -> set[str]:
    return {MANIFEST_FILENAME} | {f"{name}.csv" for name in _CONTRACTS}


def _read_manifest(payload: bytes) -> dict[str, Any]:
    try:
        text = payload.decode("utf-8")
        pairs: list[tuple[str, Any]] = []

        def reject_duplicates(items: list[tuple[str, Any]]) -> dict[str, Any]:
            seen: set[str] = set()
            for key, _ in items:
                if key in seen:
                    raise QDataSnapshotError(f"manifest contains duplicate key: {key}")
                seen.add(key)
            return dict(items)

        manifest = json.loads(text, object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QDataSnapshotError("manifest is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise QDataSnapshotError("manifest root must be an object")
    if payload != _canonical_json_bytes(manifest):
        raise QDataSnapshotError("manifest is not canonical JSON")
    if set(manifest) != _MANIFEST_KEYS:
        raise QDataSnapshotError("manifest fields do not match research_snapshot_v1")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise QDataSnapshotError(f"unsupported schema_version: {manifest.get('schema_version')!r}")
    if manifest.get("format") != "csv+canonical-json":
        raise QDataSnapshotError("unsupported snapshot format")
    datasets = manifest.get("datasets")
    if not isinstance(datasets, dict) or set(datasets) != set(_CONTRACTS):
        raise QDataSnapshotError("manifest datasets do not match research_snapshot_v1")
    for name, contract in _CONTRACTS.items():
        metadata = datasets[name]
        if not isinstance(metadata, dict) or set(metadata) != _DATASET_METADATA_KEYS:
            raise QDataSnapshotError(f"manifest metadata fields mismatch for {name}")
        if metadata.get("path") != f"{name}.csv":
            raise QDataSnapshotError(f"manifest path mismatch for {name}")
        if metadata.get("columns") != list(contract.columns):
            raise QDataSnapshotError(f"manifest columns mismatch for {name}")
        if metadata.get("primary_key") != list(contract.primary_key):
            raise QDataSnapshotError(f"manifest primary key mismatch for {name}")
        if metadata.get("date_field") != contract.date_field:
            raise QDataSnapshotError(f"manifest date field mismatch for {name}")
        row_count = metadata.get("row_count")
        if isinstance(row_count, bool) or not isinstance(row_count, int) or row_count <= 0:
            raise QDataSnapshotError(f"manifest row_count must be a positive integer for {name}")
    return manifest


def _validate_manifest_values(manifest: Mapping[str, Any], cutoff: datetime) -> None:
    if manifest["cutoff_ts"] != _format_timestamp(cutoff):
        raise QDataSnapshotError("cutoff_ts is not canonical UTC")
    for field in ("timezone", "source", "data_version", "artifact_notice"):
        if manifest[field] != _required_string(manifest[field], field):
            raise QDataSnapshotError(f"{field} is not canonical")
    quality = manifest["quality_status"]
    if not isinstance(quality, dict) or set(quality) != {"status", "error_count", "warning_count"}:
        raise QDataSnapshotError("quality_status fields do not match research_snapshot_v1")
    if quality["status"] != "passed":
        raise QDataSnapshotError("snapshot quality_status must be passed with zero errors")
    for field in ("error_count", "warning_count"):
        count = quality[field]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise QDataSnapshotError(f"quality_status.{field} must be a non-negative integer")
    if quality["error_count"] != 0:
        raise QDataSnapshotError("snapshot quality_status must be passed with zero errors")


def _read_and_canonicalize_csv(
    name: str,
    contract: _DatasetContract,
    payload: bytes,
    *,
    cutoff: datetime,
    data_version: str,
    snapshot_timezone: ZoneInfo,
) -> list[dict[str, str]]:
    try:
        text = payload.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if reader.fieldnames != list(contract.columns):
            raise QDataSnapshotError(f"{name}.csv header does not match contract")
        raw_rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise QDataSnapshotError(f"{name}.csv is malformed UTF-8 CSV") from exc
    if not raw_rows:
        raise QDataSnapshotError(f"{name} must contain at least one row")
    if any(None in row for row in raw_rows):
        raise QDataSnapshotError(f"{name}.csv contains extra unnamed columns")

    rows: list[dict[str, str]] = []
    seen: set[tuple[str, ...]] = set()
    for index, raw in enumerate(raw_rows, start=1):
        if set(raw) != set(contract.columns):
            raise QDataSnapshotError(f"{name} row {index} fields do not match contract")
        row = {
            column: _canonical_value(
                raw[column], contract.kinds[column], nullable=column in contract.nullable,
                field=f"{name}[{index}].{column}",
            )
            for column in contract.columns
        }
        key = tuple(row[column] for column in contract.primary_key)
        if key in seen:
            raise QDataSnapshotError(f"duplicate {name} primary key {key}")
        seen.add(key)
        available_at = _parse_timestamp(row["available_at"], f"{name}.available_at")
        if available_at > cutoff:
            raise QDataSnapshotError(f"{name} row {index} available_at exceeds cutoff_ts")
        if name == "daily_bar" and row["data_version"] != data_version:
            raise QDataSnapshotError("daily_bar data_version does not match manifest")
        _validate_row(name, row, index, snapshot_timezone)
        rows.append(row)
    canonical_rows = sorted(rows, key=lambda row: tuple(row[field] for field in contract.primary_key))
    if payload != _csv_bytes(contract, canonical_rows):
        raise QDataSnapshotError(f"{name}.csv is not canonical")
    return canonical_rows


def _validate_row(name: str, row: Mapping[str, str], index: int, snapshot_timezone: ZoneInfo) -> None:
    if name == "daily_bar":
        prices = [Decimal(row[field]) for field in ("open_raw", "high_raw", "low_raw", "close_raw", "close_adjusted")]
        open_price, high, low, close, _ = prices
        if min(prices) <= 0 or high < max(open_price, low, close) or low > min(open_price, high, close):
            raise QDataSnapshotError(f"daily_bar row {index} has invalid OHLC prices")
        if Decimal(row["adjustment_factor"]) <= 0:
            raise QDataSnapshotError(f"daily_bar row {index} adjustment_factor must be positive")
        if Decimal(row["volume"]) < 0 or Decimal(row["amount"]) < 0:
            raise QDataSnapshotError(f"daily_bar row {index} volume and amount must be non-negative")
        bar_end = _parse_timestamp(row["bar_end_at"], "daily_bar.bar_end_at")
        available = _parse_timestamp(row["available_at"], "daily_bar.available_at")
        if bar_end.astimezone(snapshot_timezone).date() != date.fromisoformat(row["trade_date"]):
            raise QDataSnapshotError(f"daily_bar row {index} bar_end_at date differs from trade_date")
        if available < bar_end:
            raise QDataSnapshotError(f"daily_bar row {index} available_at precedes bar_end_at")
    elif name == "tradability":
        if int(row["lot_size"]) <= 0:
            raise QDataSnapshotError(f"tradability row {index} lot_size must be positive")
        if not row["limit_up"] or not row["limit_down"]:
            raise QDataSnapshotError(f"tradability row {index} lacks critical price-limit constraints")
        limit_up = Decimal(row["limit_up"])
        limit_down = Decimal(row["limit_down"])
        if limit_up <= limit_down or limit_down <= 0:
            raise QDataSnapshotError(f"tradability row {index} has invalid price limits")
        if row["is_limit_up"] == "true" and row["is_limit_down"] == "true":
            raise QDataSnapshotError(f"tradability row {index} has contradictory limit flags")
        suspended = row["is_suspended"] == "true"
        if suspended and (row["can_buy"] != "false" or row["can_sell"] != "false"):
            raise QDataSnapshotError(f"tradability row {index} suspended security cannot trade")
        if row["is_limit_up"] == "true" and row["can_buy"] != "false":
            raise QDataSnapshotError(f"tradability row {index} limit-up security cannot be buyable")
        if row["is_limit_down"] == "true" and row["can_sell"] != "false":
            raise QDataSnapshotError(f"tradability row {index} limit-down security cannot be sellable")
    elif name == "security_membership":
        list_date = date.fromisoformat(row["list_date"])
        valid_from = date.fromisoformat(row["valid_from"])
        delist = date.fromisoformat(row["delist_date"]) if row["delist_date"] else None
        valid_to = date.fromisoformat(row["valid_to"]) if row["valid_to"] else None
        if valid_from < list_date:
            raise QDataSnapshotError(f"security_membership row {index} valid_from precedes list_date")
        if delist is not None and delist < list_date:
            raise QDataSnapshotError(f"security_membership row {index} delist_date precedes list_date")
        if valid_to is not None and valid_to <= valid_from:
            raise QDataSnapshotError(f"security_membership row {index} invalid interval")
        if delist is not None and valid_to is None:
            raise QDataSnapshotError(f"security_membership row {index} delist_date requires valid_to")
        if delist is not None and valid_to is not None and valid_to > delist:
            raise QDataSnapshotError(f"security_membership row {index} valid_to exceeds delist_date")
    else:
        report_period_end = date.fromisoformat(row["report_period_end"])
        published = _parse_timestamp(row["published_at"], "fundamental_pit.published_at")
        first_seen = _parse_timestamp(row["first_seen_at"], "fundamental_pit.first_seen_at")
        available = _parse_timestamp(row["available_at"], "fundamental_pit.available_at")
        disclosure_dates = {
            "published_at": published.astimezone(snapshot_timezone).date(),
            "first_seen_at": first_seen.astimezone(snapshot_timezone).date(),
            "available_at": available.astimezone(snapshot_timezone).date(),
        }
        for field, disclosure_date in disclosure_dates.items():
            if report_period_end > disclosure_date:
                raise QDataSnapshotError(
                    f"fundamental_pit row {index} report_period_end is after local {field} date"
                )
        if available < max(published, first_seen):
            raise QDataSnapshotError("fundamental available_at precedes publication or ingestion")


def _validate_cross_dataset(
    rows: Mapping[str, Sequence[Mapping[str, str]]],
    *,
    snapshot_timezone: ZoneInfo,
) -> None:
    daily_keys = {(row["symbol"], row["trade_date"]) for row in rows["daily_bar"]}
    tradability_keys = {(row["symbol"], row["trade_date"]) for row in rows["tradability"]}
    if daily_keys != tradability_keys:
        raise QDataSnapshotError("daily_bar and tradability keys must match exactly")
    daily_by_key = {(row["symbol"], row["trade_date"]): row for row in rows["daily_bar"]}
    tradability_by_key = {(row["symbol"], row["trade_date"]): row for row in rows["tradability"]}
    for key in sorted(daily_keys):
        daily = daily_by_key[key]
        tradability = tradability_by_key[key]
        close = Decimal(daily["close_raw"])
        if tradability["is_suspended"] == "true" and (
            Decimal(daily["volume"]) != 0 or Decimal(daily["amount"]) != 0
        ):
            raise QDataSnapshotError(f"suspended key {key} must have zero volume and amount")
        limit_up = Decimal(tradability["limit_up"])
        limit_down = Decimal(tradability["limit_down"])
        if close > limit_up or close < limit_down:
            raise QDataSnapshotError(f"close_raw outside declared limits for {key}")
        if (tradability["is_limit_up"] == "true") != (close == limit_up):
            raise QDataSnapshotError(f"is_limit_up disagrees with close_raw for {key}")
        if (tradability["is_limit_down"] == "true") != (close == limit_down):
            raise QDataSnapshotError(f"is_limit_down disagrees with close_raw for {key}")

    memberships: dict[str, list[Mapping[str, str]]] = {}
    for membership in rows["security_membership"]:
        memberships.setdefault(membership["symbol"], []).append(membership)
    for symbol, intervals in memberships.items():
        ordered = sorted(intervals, key=lambda item: item["valid_from"])
        previous_end: date | None = None
        for position, membership in enumerate(ordered):
            start = date.fromisoformat(membership["valid_from"])
            end = date.fromisoformat(membership["valid_to"]) if membership["valid_to"] else None
            if position and (previous_end is None or start < previous_end):
                raise QDataSnapshotError(f"symbol {symbol} has overlapping membership intervals")
            previous_end = end

    market_trade_dates = sorted(
        {date.fromisoformat(trade_date_text) for _, trade_date_text in daily_keys}
    )
    missing_coverage: list[tuple[str, str]] = []
    for symbol, intervals in memberships.items():
        for membership in intervals:
            start = date.fromisoformat(membership["valid_from"])
            end = date.fromisoformat(membership["valid_to"]) if membership["valid_to"] else None
            for trade_day in market_trade_dates:
                if start <= trade_day and (end is None or trade_day < end):
                    key = (symbol, trade_day.isoformat())
                    if key not in daily_keys or key not in tradability_keys:
                        missing_coverage.append(key)
    if missing_coverage:
        raise QDataSnapshotError(
            "missing explicit market/tradability coverage for active membership keys: "
            f"{missing_coverage[:5]}"
        )

    for symbol, trade_date_text in sorted(daily_keys):
        trade_day = date.fromisoformat(trade_date_text)
        daily = daily_by_key[(symbol, trade_date_text)]
        tradability = tradability_by_key[(symbol, trade_date_text)]
        signal_at = max(
            _parse_timestamp(daily["available_at"], "daily_bar.available_at"),
            _parse_timestamp(tradability["available_at"], "tradability.available_at"),
        )
        if signal_at.astimezone(snapshot_timezone).date() != trade_day:
            raise QDataSnapshotError(
                f"signal availability for {(symbol, trade_date_text)} is outside local trade_date"
            )
        matching = [
            membership for membership in memberships.get(symbol, [])
            if date.fromisoformat(membership["valid_from"]) <= trade_day
            and (not membership["valid_to"] or trade_day < date.fromisoformat(membership["valid_to"]))
        ]
        if len(matching) != 1:
            raise QDataSnapshotError(f"daily_bar key {(symbol, trade_date_text)} lacks unique active membership")
        membership_available = _parse_timestamp(matching[0]["available_at"], "security_membership.available_at")
        if membership_available > signal_at:
            raise QDataSnapshotError(f"membership for {(symbol, trade_date_text)} was unavailable at signal time")
    for fundamental in rows["fundamental_pit"]:
        if fundamental["symbol"] not in memberships:
            raise QDataSnapshotError(f"fundamental symbol {fundamental['symbol']} has no membership")


def _adapt_rows(
    rows: Mapping[str, Sequence[Mapping[str, str]]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    daily = pd.DataFrame(rows["daily_bar"]).rename(
        columns={
            "trade_date": "date",
            "available_at": "daily_available_at",
            "open_raw": "open",
            "high_raw": "high",
            "low_raw": "low",
            "close_raw": "close",
        }
    )
    daily["open_raw"] = daily["open"]
    daily["high_raw"] = daily["high"]
    daily["low_raw"] = daily["low"]
    daily["close_raw"] = daily["close"]
    tradability = pd.DataFrame(rows["tradability"]).rename(
        columns={"trade_date": "date", "available_at": "tradability_available_at"}
    )
    panel = daily.merge(tradability, on=["symbol", "date"], how="inner", validate="one_to_one")
    for column in (
        "open", "high", "low", "close", "open_raw", "high_raw", "low_raw", "close_raw",
        "close_adjusted", "adjustment_factor", "volume", "amount", "limit_up", "limit_down",
    ):
        panel[column] = pd.to_numeric(panel[column], errors="raise")
    for column in (
        "is_st", "is_suspended", "is_limit_up", "is_limit_down", "can_buy", "can_sell", "t_plus_one",
    ):
        panel[column] = panel[column].map({"true": True, "false": False}).astype("boolean")
    panel["lot_size"] = pd.to_numeric(panel["lot_size"], errors="raise").astype(int)
    panel["date"] = pd.to_datetime(panel["date"], format="%Y-%m-%d", errors="raise")
    for column in ("bar_end_at", "daily_available_at", "tradability_available_at"):
        panel[column] = pd.to_datetime(panel[column], utc=True, errors="raise")
    panel["signal_available_at"] = panel[["daily_available_at", "tradability_available_at"]].max(axis=1)

    membership_rows: list[dict[str, Any]] = []
    for _, market in panel.iterrows():
        trade_day = market["date"].date()
        matches = [
            membership for membership in rows["security_membership"]
            if membership["symbol"] == market["symbol"]
            and date.fromisoformat(membership["valid_from"]) <= trade_day
            and (not membership["valid_to"] or trade_day < date.fromisoformat(membership["valid_to"]))
        ]
        membership = matches[0]
        membership_rows.append(
            {
                "symbol": market["symbol"], "date": market["date"],
                "is_stock_master_member": True, "board": membership["board"],
                "asset_type": membership["asset_type"], "membership_status": membership["status"],
                "list_date": membership["list_date"], "delist_date": membership["delist_date"],
                "membership_valid_from": membership["valid_from"],
                "membership_valid_to": membership["valid_to"],
                "membership_available_at": pd.Timestamp(membership["available_at"]),
            }
        )
    universe = pd.DataFrame(membership_rows)
    panel = panel.merge(universe, on=["symbol", "date"], how="inner", validate="one_to_one")
    panel["is_universe_member"] = True
    panel = _merge_pit_fundamentals(panel, rows["fundamental_pit"])
    expected_keys = {
        (row["symbol"], pd.Timestamp(row["trade_date"])) for row in rows["daily_bar"]
    }
    panel = prepare_backtest_panel(panel, align_missing_sessions=False)
    actual_keys = set(zip(panel["symbol"], panel["date"]))
    if len(panel) != len(expected_keys) or actual_keys != expected_keys:
        raise QDataSnapshotError("normalized panel keys differ from verified daily_bar keys")

    stock_master = pd.DataFrame(rows["security_membership"]).rename(
        columns={
            "list_date": "listDate", "delist_date": "delistDate", "status": "listStatus",
            "asset_type": "stockType", "available_at": "membership_available_at",
        }
    )
    for column in ("listDate", "delistDate", "valid_from", "valid_to"):
        stock_master[column] = pd.to_datetime(stock_master[column], format="%Y-%m-%d", errors="coerce")
    stock_master["membership_available_at"] = pd.to_datetime(
        stock_master["membership_available_at"], utc=True, errors="raise"
    )
    return panel, universe, stock_master


def _merge_pit_fundamentals(
    panel: pd.DataFrame, fundamentals: Sequence[Mapping[str, str]]
) -> pd.DataFrame:
    output = panel.copy()
    fields = sorted({row["field_name"] for row in fundamentals})
    collisions = sorted(set(fields) & set(output.columns))
    if collisions:
        raise QDataSnapshotError(
            f"fundamental field name collides with protected market columns: {collisions}"
        )
    parsed = [
        {
            **row,
            "report_period_end_value": date.fromisoformat(row["report_period_end"]),
            "available_at_value": _parse_timestamp(row["available_at"], "fundamental_pit.available_at"),
            "published_at_value": _parse_timestamp(row["published_at"], "fundamental_pit.published_at"),
            "first_seen_at_value": _parse_timestamp(row["first_seen_at"], "fundamental_pit.first_seen_at"),
        }
        for row in fundamentals
    ]
    for field in fields:
        values: list[float | None] = []
        revisions: list[str | None] = []
        available_values: list[pd.Timestamp | None] = []
        report_periods: list[pd.Timestamp | None] = []
        for _, market in output.iterrows():
            signal_at = market["signal_available_at"].to_pydatetime()
            candidates = [
                row for row in parsed
                if row["symbol"] == market["symbol"]
                and row["field_name"] == field
                and row["available_at_value"] <= signal_at
            ]
            if candidates:
                latest_period = max(row["report_period_end_value"] for row in candidates)
                period_candidates = [row for row in candidates if row["report_period_end_value"] == latest_period]
                chosen = max(
                    period_candidates,
                    key=lambda row: (
                        row["available_at_value"], row["first_seen_at_value"],
                        row["published_at_value"], row["revision_id"],
                    ),
                )
                values.append(float(Decimal(chosen["field_value"])))
                revisions.append(chosen["revision_id"])
                available_values.append(pd.Timestamp(chosen["available_at_value"]))
                report_periods.append(pd.Timestamp(chosen["report_period_end"]))
            else:
                values.append(None)
                revisions.append(None)
                available_values.append(None)
                report_periods.append(None)
        output[field] = values
        output[f"{field}_revision_id"] = revisions
        output[f"{field}_available_at"] = pd.to_datetime(available_values, utc=True)
        output[f"{field}_report_period_end"] = pd.to_datetime(report_periods)
    return output


def _dataset_metadata(
    name: str, contract: _DatasetContract, rows: Sequence[Mapping[str, str]], payload: bytes
) -> dict[str, Any]:
    dates = [row[contract.date_field] for row in rows]
    return {
        "path": f"{name}.csv", "sha256": _sha256(payload), "row_count": len(rows),
        "columns": list(contract.columns), "primary_key": list(contract.primary_key),
        "date_field": contract.date_field, "date_range": {"start": min(dates), "end": max(dates)},
    }


def _canonical_value(value: Any, kind: str, *, nullable: bool, field: str) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        if nullable:
            return ""
        raise QDataSnapshotError(f"missing required field {field}")
    if kind == "string":
        return _required_string(value, field)
    if kind == "date":
        try:
            return date.fromisoformat(str(value).strip()).isoformat()
        except (TypeError, ValueError) as exc:
            raise QDataSnapshotError(f"{field} must be an ISO date") from exc
    if kind == "timestamp":
        return _format_timestamp(_parse_timestamp(value, field))
    if kind == "boolean":
        normalized = str(value).strip().lower()
        if normalized in {"true", "1"}:
            return "true"
        if normalized in {"false", "0"}:
            return "false"
        raise QDataSnapshotError(f"{field} must be boolean")
    if kind in {"number", "integer"}:
        try:
            number = Decimal(str(value).strip())
        except (InvalidOperation, ValueError) as exc:
            raise QDataSnapshotError(f"{field} must be numeric") from exc
        if not number.is_finite():
            raise QDataSnapshotError(f"{field} must be finite")
        if kind == "integer" and number != number.to_integral_value():
            raise QDataSnapshotError(f"{field} must be an integer")
        return _render_decimal(number.to_integral_value() if kind == "integer" else number)
    raise QDataSnapshotError(f"unknown field kind for {field}")


def _parse_timestamp(value: Any, field: str) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError) as exc:
        raise QDataSnapshotError(f"{field} must be an ISO timestamp with explicit offset") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise QDataSnapshotError(f"{field} must be an ISO timestamp with explicit offset")
    return parsed.astimezone(timezone.utc)


def _render_decimal(number: Decimal) -> str:
    """Match QData's context-independent canonical finite-decimal renderer."""

    if number.is_zero():
        return "0"
    parts = number.as_tuple()
    digits = list(parts.digits)
    exponent = int(parts.exponent)
    while len(digits) > 1 and digits[-1] == 0:
        digits.pop()
        exponent += 1
    coefficient = "".join(str(digit) for digit in digits)
    decimal_point = len(coefficient) + exponent
    if exponent >= 0:
        plain_length = len(coefficient) + exponent
    elif decimal_point > 0:
        plain_length = len(coefficient) + 1
    else:
        plain_length = 2 + (-decimal_point) + len(coefficient)
    sign = "-" if parts.sign else ""
    if plain_length > 4096:
        mantissa = coefficient[0]
        if len(coefficient) > 1:
            mantissa += "." + coefficient[1:]
        scientific_exponent = exponent + len(coefficient) - 1
        return f"{sign}{mantissa}e{scientific_exponent}"
    if exponent >= 0:
        rendered = coefficient + ("0" * exponent)
    elif decimal_point > 0:
        rendered = coefficient[:decimal_point] + "." + coefficient[decimal_point:]
    else:
        rendered = "0." + ("0" * -decimal_point) + coefficient
    return sign + rendered


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QDataSnapshotError(f"{field} must be a non-empty string")
    return value.strip()


def _csv_bytes(contract: _DatasetContract, rows: Sequence[Mapping[str, str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(contract.columns), lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row[column] for column in contract.columns})
    return output.getvalue().encode("utf-8")


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "MANIFEST_FILENAME", "QDataSnapshotError", "SCHEMA_VERSION",
    "load_qdata_snapshot", "verify_qdata_snapshot",
]
