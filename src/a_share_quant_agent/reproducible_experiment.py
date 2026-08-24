"""Deterministic QData-to-Agent timing experiment and receipt verifier.

This module deliberately implements one fixed synthetic timing probe.  It is
contract evidence, not a strategy search or a performance claim.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import numbers
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence

import pandas as pd

from .backtest import BacktestResult, run_backtest
from .qdata_snapshot import QDataSnapshotError, load_qdata_snapshot, verify_qdata_snapshot
from .spec import StrategySpec


RECEIPT_SCHEMA_VERSION = "a_share_research_receipt_v1"
EXPECTED_SNAPSHOT_ID = "sha256:0b7a9697ceccc81cf74e131b74e9377c106160919da990910725011ad39c342b"
EXPECTED_PANEL_SHA256 = "6485d65f8c7e9e7c1fd8a8c02a6b2a0b65e5d119ab87e6a1c2e4d4add738c8ea"
AGENT_REPOSITORY = {
    "canonical_name": "a-share-quant-research-agent",
    "canonical_remote_url": "https://github.com/Wsw-lab/a-share-quant-research-agent",
}
QDATA_REPOSITORY = {
    "canonical_name": "qdata-free-source-quant-research-db",
    "canonical_remote_url": "https://github.com/Wsw-lab/qdata-free-source-quant-research-db",
}
OUTPUT_FILENAMES = (
    "equity.jsonl",
    "metrics.json",
    "orders.jsonl",
    "receipt.json",
    "trades.jsonl",
)
SNAPSHOT_FILENAMES = (
    "daily_bar.csv",
    "fundamental_pit.csv",
    "manifest.json",
    "security_membership.csv",
    "tradability.csv",
)
QDATA_PROVENANCE_BUILDER = "byte_verified_builder_checkout"
QDATA_PROVENANCE_REFERENCE = "unverified_fixture_repository_reference"
REASON_CODES = (
    "SYNTHETIC_DATA",
    "TWO_SYMBOLS",
    "THREE_SESSIONS",
    "NO_OUT_OF_SAMPLE",
    "NO_STATISTICAL_INFERENCE",
    "NO_PERFORMANCE_CLAIM",
)
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_CONTENT_SHA_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)\.[0-9]+$")
_SESSION_DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")

_RUNTIME_STRATEGY_CONFIG: dict[str, Any] = {
    "name": "qdata-research-snapshot-timing-probe",
    "description": "Synthetic contract and next-session raw-open timing probe only.",
    "universe": {
        "exclude_st": True,
        "exclude_suspended": True,
        "min_amount": 0.0,
    },
    "rebalance": {"frequency": "weekly"},
    "portfolio": {
        "initial_cash": 1_000_000.0,
        "max_positions": 1,
        "weighting": "equal",
    },
    "costs": {
        "commission_rate": 0.0,
        "stamp_tax_rate": 0.0,
        "slippage_bps": 0.0,
    },
    "execution": {"model": "close_signal_next_open"},
    "factors": [{"field": "roe_ttm", "direction": "desc", "weight": 1.0}],
    "risk": {"max_single_position_weight": 1.0},
}

_TRADE_COLUMNS = (
    "signal_date",
    "date",
    "symbol",
    "side",
    "shares",
    "price",
    "gross",
    "commission",
    "stamp_tax",
    "cash_delta",
    "execution_model",
    "fill_price_field",
    "note",
)
_ORDER_COLUMNS = (
    "signal_date",
    "date",
    "symbol",
    "side",
    "requested_shares",
    "status",
    "fill_price_field",
    "execution_model",
    "note",
    "record_type",
    "targets",
)
_EQUITY_COLUMNS = (
    "date",
    "equity",
    "cash",
    "cash_yield_accrued",
    "cumulative_cash_yield",
    "gross_exposure",
    "risk_target_weight",
    "alpha_health_filter_weight",
    "alpha_health_score",
    "market_breadth_score",
    "overheated_reversal_guard_active",
    "window_fuse_active",
    "window_reentry_active",
    "window_reentry_target_weight",
    "window_fuse_cooldown_remaining",
    "window_fuse_drawdown",
    "window_fuse_rolling_return",
    "window_fuse_consecutive_loss_days",
)
_ARTIFACT_CONTRACT = {
    "trades.jsonl": {"format": "canonical-jsonl-v1", "columns": list(_TRADE_COLUMNS)},
    "orders.jsonl": {"format": "canonical-jsonl-v1", "columns": list(_ORDER_COLUMNS)},
    "equity.jsonl": {"format": "canonical-jsonl-v1", "columns": list(_EQUITY_COLUMNS)},
    "metrics.json": {"format": "canonical-json-v1", "columns": []},
}
_EXPECTED_ARTIFACT_ROW_COUNTS = {
    "equity.jsonl": 3,
    "metrics.json": 1,
    "orders.jsonl": 1,
    "trades.jsonl": 1,
}
_EXPECTED_ARTIFACT_SHA256 = {
    "equity.jsonl": "d38044564ca874e56efab0a81fb85b80d3f7ce09cfed8d178ec130b7c9829f96",
    "metrics.json": "ee3a5dfdfc80b27a2b48de467dc82279294195f8b8b09bc7f6fe209ad1b4dec0",
    "orders.jsonl": "8069eaa426d9510073eae25c73ec8cc16af36c8e709d9aca9c81563e8e25a872",
    "trades.jsonl": "8159805990c1e646ae99cdc30fe4b27ba520afd4270d4346cf9fbdcd49524077",
}
_EXPECTED_SOURCE_LINEAGE = [
    {"key": "snapshot", "value": "deterministic_synthetic_fixture"},
    {"key": "daily_bar.source_id", "value": "synthetic"},
    {"key": "daily_bar.batch_id", "value": "batch-fixture-001"},
    {"key": "fundamental_pit.source_id", "value": "synthetic"},
]


class ExperimentError(RuntimeError):
    """Raised when an experiment or receipt cannot be trusted."""


def run_experiment(
    snapshot_dir: str | Path,
    output_dir: str | Path,
    *,
    qdata_checkout: str | Path | None = None,
    qdata_sha: str | None = None,
    _agent_sha_for_testing: str | None = None,
    _qdata_sha_for_testing: str | None = None,
) -> dict[str, Any]:
    """Run the single fixed timing probe and atomically publish its artifacts.

    The underscored SHA arguments are deliberately absent from the CLI and are
    only for unit tests that need checkout-independent identities.
    """

    output = Path(output_dir).expanduser().resolve(strict=False)
    _validate_fresh_output(output)
    try:
        loaded = load_qdata_snapshot(snapshot_dir)
    except QDataSnapshotError as exc:
        raise ExperimentError(f"snapshot verification failed: {exc}") from exc
    try:
        manifest = verify_qdata_snapshot(snapshot_dir)
    except QDataSnapshotError as exc:
        raise ExperimentError(f"snapshot changed after verification: {exc}") from exc
    if (
        loaded.metadata.snapshot_id != manifest.get("snapshot_id")
        or loaded.metadata.schema_version != manifest.get("schema_version")
        or loaded.metadata.cutoff_ts != manifest.get("cutoff_ts")
    ):
        raise ExperimentError("snapshot changed after verification: adapter and manifest identities differ")
    if manifest.get("source") != "deterministic_synthetic_fixture":
        raise ExperimentError("the maintained timing probe accepts only the deterministic synthetic fixture")

    agent_identity = _agent_identity(_agent_sha_for_testing)
    qdata_identity = _qdata_identity(
        manifest=manifest,
        snapshot_dir=snapshot_dir,
        qdata_checkout=qdata_checkout,
        qdata_sha=qdata_sha,
        sha_for_testing=_qdata_sha_for_testing,
    )
    _require_output_untracked_if_inside_checkout(output, agent_identity.get("checkout_root"))

    spec = StrategySpec.from_dict(deepcopy(_RUNTIME_STRATEGY_CONFIG))
    result = run_backtest(loaded.data, spec)
    artifacts = _build_artifact_payloads(result)
    _validate_fixed_artifact_counts(
        {filename: artifact["row_count"] for filename, artifact in artifacts.items()}
    )
    _validate_fixed_artifact_hashes(
        {filename: _sha256(artifact["bytes"]) for filename, artifact in artifacts.items()}
    )
    _validate_result_timing(
        artifacts["trades.jsonl"]["value"],
        artifacts["orders.jsonl"]["value"],
        final_session=str(manifest["datasets"]["daily_bar"]["date_range"]["end"]),
    )
    first_fill = _first_fill_evidence(result, loaded.data)

    receipt = _build_receipt(
        manifest=manifest,
        loaded=loaded,
        artifacts=artifacts,
        agent_identity=_public_repository_identity(agent_identity),
        qdata_identity=_public_repository_identity(qdata_identity),
        first_fill=first_fill,
    )
    receipt["receipt_integrity"] = {
        "algorithm": "sha256",
        "scope": "canonical_receipt_without_receipt_integrity",
        "sha256": _sha256(_canonical_json_bytes(receipt)),
    }
    receipt_bytes = _canonical_json_bytes(receipt)

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".research-receipt-staging-", dir=output.parent))
    try:
        for filename in ("trades.jsonl", "orders.jsonl", "equity.jsonl", "metrics.json"):
            _write_new_file(staging / filename, artifacts[filename]["bytes"])
        # The receipt is deliberately the final file published in the staging set.
        _write_new_file(staging / "receipt.json", receipt_bytes)
        if output.exists():
            output.rmdir()
        staging.replace(output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return receipt


def verify_experiment(
    output_dir: str | Path,
    *,
    expected_agent_sha: str | None = None,
    expected_qdata_sha: str | None = None,
) -> dict[str, Any]:
    """Verify the exact artifact set, canonical bytes, hashes, and semantics."""

    root = Path(output_dir)
    payloads = _read_exact_output_files(root)
    receipt = _decode_canonical_json(payloads["receipt.json"], "receipt.json")
    if not isinstance(receipt, dict):
        raise ExperimentError("receipt.json root must be an object")
    _verify_receipt_integrity(receipt)
    _verify_receipt_contract(receipt, expected_agent_sha, expected_qdata_sha)

    parsed_artifacts: dict[str, Any] = {}
    for filename in ("trades.jsonl", "orders.jsonl", "equity.jsonl"):
        parsed_artifacts[filename] = _decode_canonical_jsonl(payloads[filename], filename)
    metrics = _decode_canonical_json(payloads["metrics.json"], "metrics.json")
    if not isinstance(metrics, dict):
        raise ExperimentError("metrics.json root must be an object")
    parsed_artifacts["metrics.json"] = metrics

    for filename, value in parsed_artifacts.items():
        metadata = receipt["artifacts"].get(filename)
        if not isinstance(metadata, dict):
            raise ExperimentError(f"receipt lacks artifact metadata for {filename}")
        if metadata.get("sha256") != _sha256(payloads[filename]):
            raise ExperimentError(f"artifact SHA256 mismatch for {filename}")
        row_count = 1 if filename == "metrics.json" else len(value)
        if metadata.get("row_count") != row_count:
            raise ExperimentError(f"artifact row count mismatch for {filename}")
        contract = _ARTIFACT_CONTRACT[filename]
        if metadata.get("format") != contract["format"] or metadata.get("columns") != contract["columns"]:
            raise ExperimentError(f"artifact contract mismatch for {filename}")

    _verify_record_columns(parsed_artifacts)
    _validate_result_timing(
        parsed_artifacts["trades.jsonl"],
        parsed_artifacts["orders.jsonl"],
        final_session=receipt["snapshot"]["datasets"]["daily_bar"]["date_range"]["end"],
    )
    _verify_first_fill(receipt["first_fill"], parsed_artifacts)
    _verify_metrics_payload(metrics)
    _validate_fixed_artifact_hashes(
        {filename: _sha256(payloads[filename]) for filename in _EXPECTED_ARTIFACT_SHA256}
    )
    return receipt


def _build_receipt(
    *,
    manifest: Mapping[str, Any],
    loaded: Any,
    artifacts: Mapping[str, Mapping[str, Any]],
    agent_identity: Mapping[str, Any],
    qdata_identity: Mapping[str, Any],
    first_fill: Mapping[str, Any],
) -> dict[str, Any]:
    canonical_config = _normalize_json_value(_RUNTIME_STRATEGY_CONFIG)
    artifact_metadata = {
        filename: {
            "columns": list(_ARTIFACT_CONTRACT[filename]["columns"]),
            "format": _ARTIFACT_CONTRACT[filename]["format"],
            "row_count": artifacts[filename]["row_count"],
            "sha256": _sha256(artifacts[filename]["bytes"]),
        }
        for filename in sorted(artifacts)
    }
    snapshot = {
        "artifact_notice": manifest["artifact_notice"],
        "cutoff_ts": manifest["cutoff_ts"],
        "data_version": manifest["data_version"],
        "dataset_count": len(manifest["datasets"]),
        "datasets": manifest["datasets"],
        "format": manifest["format"],
        "normalized_panel_sha256": loaded.metadata.data_hash,
        "producer_source": manifest["source"],
        "quality_status": manifest["quality_status"],
        "schema_version": manifest["schema_version"],
        "snapshot_id": manifest["snapshot_id"],
        "source_lineage": [
            {"key": key, "value": value}
            for key, value in loaded.metadata.source_lineage
        ],
        "timezone": manifest["timezone"],
    }
    receipt: dict[str, Any] = {
        "artifact_contract": _expected_canonicalization_contract(),
        "artifacts": artifact_metadata,
        "conventions": _expected_conventions(),
        "determinism": _expected_determinism(),
        "environment": {
            "pandas_version": pd.__version__,
            "platform_machine": platform.machine(),
            "platform_system": platform.system(),
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
        },
        "first_fill": dict(first_fill),
        "interpretation": {
            "classification": "fixture_arithmetic_only",
            "statement": "This receipt tests data contracts and event timing only; it is not performance evidence.",
        },
        "repositories": {"agent": dict(agent_identity), "qdata": dict(qdata_identity)},
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "snapshot": snapshot,
        "strategy": {
            "config": canonical_config,
            "sha256": _sha256(_canonical_json_bytes(canonical_config)),
        },
        "verdict": _expected_verdict(),
    }
    return _normalize_json_value(receipt)


def _build_artifact_payloads(result: BacktestResult) -> dict[str, dict[str, Any]]:
    trades = _canonicalize_frame(result.trades, _TRADE_COLUMNS, ("signal_date", "date", "symbol", "side"))
    orders = _canonicalize_frame(
        result.orders,
        _ORDER_COLUMNS,
        ("signal_date", "date", "symbol", "side", "record_type", "status"),
    )
    equity = _canonicalize_frame(result.equity_curve, _EQUITY_COLUMNS, ("date",))
    metrics = {
        "classification": "fixture_arithmetic_only",
        "not_performance_evidence": True,
        "values": _normalize_json_value(dict(sorted(result.metrics.items()))),
    }
    return {
        "trades.jsonl": {"bytes": _canonical_jsonl_bytes(trades), "row_count": len(trades), "value": trades},
        "orders.jsonl": {"bytes": _canonical_jsonl_bytes(orders), "row_count": len(orders), "value": orders},
        "equity.jsonl": {"bytes": _canonical_jsonl_bytes(equity), "row_count": len(equity), "value": equity},
        "metrics.json": {"bytes": _canonical_json_bytes(metrics), "row_count": 1, "value": metrics},
    }


def _canonicalize_frame(
    frame: pd.DataFrame,
    columns: Sequence[str],
    sort_columns: Sequence[str],
) -> list[dict[str, Any]]:
    actual = tuple(str(column) for column in frame.columns)
    if set(actual) != set(columns) or len(actual) != len(columns):
        raise ExperimentError(f"engine artifact columns changed: expected {list(columns)}, got {list(actual)}")
    records = [
        {column: _normalize_json_value(row[column]) for column in columns}
        for row in frame.loc[:, list(columns)].to_dict(orient="records")
    ]
    records.sort(key=lambda row: tuple(_sort_token(row[column]) for column in sort_columns))
    return records


def _first_fill_evidence(result: BacktestResult, panel: pd.DataFrame) -> dict[str, Any]:
    if result.trades.empty:
        raise ExperimentError("the fixed timing probe produced no fill")
    first = result.trades.sort_values(["date", "symbol", "side"], kind="mergesort").iloc[0]
    signal_session = pd.Timestamp(first["signal_date"])
    fill_session = pd.Timestamp(first["date"])
    symbol = str(first["symbol"])
    raw_open_rows = panel[
        (panel["symbol"].astype(str) == symbol)
        & (pd.to_datetime(panel["date"]) == fill_session)
    ]
    if len(raw_open_rows) != 1:
        raise ExperimentError("cannot resolve a unique raw-open reference for the first fill")
    row = raw_open_rows.iloc[0]
    lot_size = int(row["lot_size"])
    evidence = {
        "fill_price": _decimal_text(first["price"]),
        "fill_price_field": str(first["fill_price_field"]),
        "fill_session": fill_session.strftime("%Y-%m-%d"),
        "lot_multiple": int(first["shares"]) % lot_size == 0,
        "lot_size": lot_size,
        "raw_open_reference": _decimal_text(row["open_raw"]),
        "shares": int(first["shares"]),
        "signal_session": signal_session.strftime("%Y-%m-%d"),
        "symbol": symbol,
    }
    expected = {
        "symbol": "600519.SH",
        "signal_session": "2024-01-02",
        "fill_session": "2024-01-03",
        "raw_open_reference": "1710.0",
        "fill_price": "1710.0",
        "fill_price_field": "open",
        "lot_size": 100,
        "lot_multiple": True,
    }
    for field, value in expected.items():
        if evidence.get(field) != value:
            raise ExperimentError(f"fixed first-fill timing probe mismatch for {field}")
    return evidence


def _validate_result_timing(
    trades: Sequence[Mapping[str, Any]],
    orders: Sequence[Mapping[str, Any]],
    *,
    final_session: str,
) -> None:
    for trade in trades:
        if trade.get("execution_model") != "close_signal_next_open":
            raise ExperimentError("trade uses an unexpected execution model")
        if trade.get("fill_price_field") != "open":
            raise ExperimentError("trade does not use the raw-open fill field")
        if not isinstance(trade.get("signal_date"), str) or not isinstance(trade.get("date"), str):
            raise ExperimentError("trade timing fields must be canonical session dates")
        if trade["date"] <= trade["signal_date"]:
            raise ExperimentError("trade fill must occur after its signal session")
    for order in orders:
        if order.get("execution_model") != "close_signal_next_open":
            raise ExperimentError("order uses an unexpected execution model")
        if order.get("fill_price_field") != "open":
            raise ExperimentError("order does not use the raw-open fill field")
        if order.get("status") == "unfilled_no_next_session":
            if order.get("date") is not None:
                raise ExperimentError("final-session signal must not have a fabricated fill date")
            if order.get("signal_date") != final_session or order.get("record_type") != "signal_intent":
                raise ExperimentError("unfilled final-session signal metadata is inconsistent")
        elif order.get("record_type") == "signal_intent":
            raise ExperimentError("signal intent cannot be presented as a filled order")


def _verify_first_fill(evidence: Any, artifacts: Mapping[str, Any]) -> None:
    if not isinstance(evidence, dict):
        raise ExperimentError("receipt first_fill must be an object")
    trades = artifacts["trades.jsonl"]
    orders = artifacts["orders.jsonl"]
    if not trades:
        raise ExperimentError("trade artifact has no first fill")
    first = trades[0]
    expected = {
        "fill_price": first["price"],
        "fill_price_field": first["fill_price_field"],
        "fill_session": first["date"],
        "lot_multiple": True,
        "lot_size": 100,
        "raw_open_reference": "1710.0",
        "shares": first["shares"],
        "signal_session": first["signal_date"],
        "symbol": first["symbol"],
    }
    if evidence != expected:
        raise ExperimentError("receipt first-fill evidence differs from the trade artifact")
    if expected["symbol"] != "600519.SH" or expected["fill_session"] != "2024-01-03":
        raise ExperimentError("receipt does not contain the fixed first-fill timing probe")
    if expected["signal_session"] != "2024-01-02":
        raise ExperimentError("receipt does not contain the exact first-fill signal session")
    if expected["fill_price"] != "1710.0" or expected["raw_open_reference"] != "1710.0":
        raise ExperimentError("first fill is not the fixture's raw open")
    if expected["shares"] % expected["lot_size"] != 0:
        raise ExperimentError("first fill violates the fixture lot size")
    matching_orders = [
        order for order in orders
        if order.get("symbol") == expected["symbol"]
        and order.get("signal_date") == expected["signal_session"]
        and order.get("date") == expected["fill_session"]
        and order.get("status") == "filled"
    ]
    if len(matching_orders) != 1:
        raise ExperimentError("first fill lacks one matching filled order")


def _verify_receipt_contract(
    receipt: Mapping[str, Any],
    expected_agent_sha: str | None,
    expected_qdata_sha: str | None,
) -> None:
    required = {
        "artifact_contract", "artifacts", "conventions", "determinism", "environment", "first_fill",
        "interpretation", "receipt_integrity", "repositories", "schema_version", "snapshot",
        "strategy", "verdict",
    }
    if set(receipt) != required:
        raise ExperimentError("receipt top-level fields do not match the v1 contract")
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        raise ExperimentError(f"unsupported receipt schema: {receipt.get('schema_version')!r}")
    if receipt.get("artifact_contract") != _expected_canonicalization_contract():
        raise ExperimentError("receipt canonicalization contract was mutated")
    if receipt.get("conventions") != _expected_conventions():
        raise ExperimentError("receipt timing or marking conventions were mutated")
    if receipt.get("determinism") != _expected_determinism():
        raise ExperimentError("receipt determinism scope was mutated")
    if receipt.get("verdict") != _expected_verdict():
        raise ExperimentError("receipt failure card was mutated")
    if receipt.get("interpretation") != {
        "classification": "fixture_arithmetic_only",
        "statement": "This receipt tests data contracts and event timing only; it is not performance evidence.",
    }:
        raise ExperimentError("receipt interpretation was mutated")

    strategy = receipt.get("strategy")
    expected_config = _normalize_json_value(_RUNTIME_STRATEGY_CONFIG)
    if not isinstance(strategy, dict) or strategy.get("config") != expected_config:
        raise ExperimentError("receipt strategy config differs from the fixed timing probe")
    if strategy.get("sha256") != _sha256(_canonical_json_bytes(expected_config)):
        raise ExperimentError("receipt strategy config hash mismatch")

    repositories = receipt.get("repositories")
    if not isinstance(repositories, dict) or set(repositories) != {"agent", "qdata"}:
        raise ExperimentError("receipt repository identities are incomplete")
    _verify_repository_identity(repositories["agent"], AGENT_REPOSITORY, expected_agent_sha)
    qdata_identity = repositories["qdata"]
    if not isinstance(qdata_identity, dict):
        raise ExperimentError("QData repository identity is malformed")
    provenance_verification = qdata_identity.get("provenance_verification")
    if provenance_verification not in {QDATA_PROVENANCE_BUILDER, QDATA_PROVENANCE_REFERENCE}:
        raise ExperimentError("QData provenance verification status is unsupported")
    _verify_repository_identity(
        qdata_identity,
        QDATA_REPOSITORY,
        expected_qdata_sha,
        provenance_verification=provenance_verification,
    )
    dirty_observed = qdata_identity["dirty_state"]["observed"]
    if provenance_verification == QDATA_PROVENANCE_BUILDER and not dirty_observed:
        raise ExperimentError("builder-verified QData provenance requires an observed checkout")
    if provenance_verification == QDATA_PROVENANCE_REFERENCE and dirty_observed:
        raise ExperimentError("an unverified QData fixture reference must not claim an observed checkout")
    _verify_snapshot_metadata(receipt.get("snapshot"))

    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(_ARTIFACT_CONTRACT):
        raise ExperimentError("receipt artifact set does not match the v1 contract")
    _validate_fixed_artifact_counts(
        {
            filename: metadata.get("row_count") if isinstance(metadata, dict) else None
            for filename, metadata in artifacts.items()
        }
    )
    environment = receipt.get("environment")
    required_environment = {
        "pandas_version", "platform_machine", "platform_system",
        "python_implementation", "python_version",
    }
    if not isinstance(environment, dict) or set(environment) != required_environment:
        raise ExperimentError("receipt environment fields do not match the v1 contract")
    if not all(isinstance(value, str) and value for value in environment.values()):
        raise ExperimentError("receipt environment facts must be non-empty strings")


def _verify_repository_identity(
    identity: Any,
    expected: Mapping[str, str],
    expected_sha: str | None,
    *,
    provenance_verification: str | None = None,
) -> None:
    expected_fields = {"canonical_name", "canonical_remote_url", "dirty_state", "sha"}
    if provenance_verification is not None:
        expected_fields.add("provenance_verification")
    if not isinstance(identity, dict) or set(identity) != expected_fields:
        raise ExperimentError("repository identity fields do not match the v1 contract")
    if provenance_verification is not None and identity["provenance_verification"] != provenance_verification:
        raise ExperimentError("repository provenance verification status mismatch")
    if identity["canonical_name"] != expected["canonical_name"]:
        raise ExperimentError("repository canonical name mismatch")
    if identity["canonical_remote_url"] != expected["canonical_remote_url"]:
        raise ExperimentError("repository canonical remote URL mismatch")
    _validate_sha(identity["sha"], "repository SHA")
    if expected_sha is not None:
        _validate_sha(expected_sha, "expected repository SHA")
        if identity["sha"] != expected_sha:
            raise ExperimentError("repository SHA differs from the expected verification anchor")
    dirty = identity["dirty_state"]
    if not isinstance(dirty, dict) or set(dirty) != {"is_dirty", "method", "observed"}:
        raise ExperimentError("repository dirty-state disclosure is malformed")
    if not isinstance(dirty["observed"], bool):
        raise ExperimentError("repository dirty-state observation flag must be boolean")
    if dirty["is_dirty"] is not None and not isinstance(dirty["is_dirty"], bool):
        raise ExperimentError("repository dirty-state value must be boolean or null")
    if dirty["observed"] != (dirty["is_dirty"] is not None):
        raise ExperimentError("repository dirty-state disclosure is internally inconsistent")
    if not isinstance(dirty["method"], str) or not dirty["method"]:
        raise ExperimentError("repository dirty-state method must be disclosed")


def _verify_snapshot_metadata(snapshot: Any) -> None:
    required = {
        "artifact_notice", "cutoff_ts", "data_version", "dataset_count", "datasets", "format",
        "normalized_panel_sha256", "producer_source", "quality_status", "schema_version",
        "snapshot_id", "source_lineage", "timezone",
    }
    if not isinstance(snapshot, dict) or set(snapshot) != required:
        raise ExperimentError("snapshot receipt fields do not match the v1 contract")
    if snapshot["schema_version"] != "research_snapshot_v1":
        raise ExperimentError("receipt references an unsupported snapshot schema")
    if not isinstance(snapshot["snapshot_id"], str) or not snapshot["snapshot_id"].startswith("sha256:"):
        raise ExperimentError("receipt snapshot_id is malformed")
    if not _CONTENT_SHA_PATTERN.fullmatch(snapshot["snapshot_id"][7:]):
        raise ExperimentError("receipt snapshot_id digest is malformed")
    if not _CONTENT_SHA_PATTERN.fullmatch(str(snapshot["normalized_panel_sha256"])):
        raise ExperimentError("receipt normalized panel hash is malformed")
    if (
        snapshot["snapshot_id"] != EXPECTED_SNAPSHOT_ID
        or snapshot["normalized_panel_sha256"] != EXPECTED_PANEL_SHA256
        or snapshot["producer_source"] != "deterministic_synthetic_fixture"
        or snapshot["data_version"] != "fixture-v1"
        or snapshot["timezone"] != "Asia/Shanghai"
        or snapshot["format"] != "csv+canonical-json"
        or snapshot["cutoff_ts"] != "2024-05-01T08:00:00Z"
        or snapshot["quality_status"] != {"error_count": 0, "status": "passed", "warning_count": 0}
    ):
        raise ExperimentError("receipt snapshot does not identify the exact synthetic fixture")
    datasets = snapshot["datasets"]
    if not isinstance(datasets, dict) or snapshot["dataset_count"] != 4 or len(datasets) != 4:
        raise ExperimentError("receipt snapshot dataset count mismatch")
    if set(datasets) != {"daily_bar", "fundamental_pit", "security_membership", "tradability"}:
        raise ExperimentError("receipt snapshot datasets do not match research_snapshot_v1")
    for name, metadata in datasets.items():
        if not isinstance(metadata, dict):
            raise ExperimentError(f"snapshot dataset metadata is malformed for {name}")
        if not _CONTENT_SHA_PATTERN.fullmatch(str(metadata.get("sha256", ""))):
            raise ExperimentError(f"snapshot dataset SHA256 is malformed for {name}")
        if not isinstance(metadata.get("row_count"), int) or metadata["row_count"] <= 0:
            raise ExperimentError(f"snapshot dataset row count is malformed for {name}")
    expected_rows = {"daily_bar": 6, "fundamental_pit": 3, "security_membership": 2, "tradability": 6}
    expected_ranges = {
        "daily_bar": {"start": "2024-01-02", "end": "2024-01-04"},
        "fundamental_pit": {"start": "2023-09-30", "end": "2023-09-30"},
        "security_membership": {"start": "1991-04-03", "end": "2001-08-27"},
        "tradability": {"start": "2024-01-02", "end": "2024-01-04"},
    }
    if any(
        datasets[name].get("row_count") != expected_rows[name]
        or datasets[name].get("date_range") != expected_ranges[name]
        for name in expected_rows
    ):
        raise ExperimentError("receipt snapshot dimensions differ from the exact synthetic fixture")
    manifest_view = {
        "artifact_notice": snapshot["artifact_notice"],
        "cutoff_ts": snapshot["cutoff_ts"],
        "data_version": snapshot["data_version"],
        "datasets": snapshot["datasets"],
        "format": snapshot["format"],
        "quality_status": snapshot["quality_status"],
        "schema_version": snapshot["schema_version"],
        "source": snapshot["producer_source"],
        "timezone": snapshot["timezone"],
    }
    if "sha256:" + _sha256(_canonical_json_bytes(manifest_view)) != snapshot["snapshot_id"]:
        raise ExperimentError("receipt snapshot manifest fields do not match its snapshot_id")
    lineage = snapshot["source_lineage"]
    if not isinstance(lineage, list) or not lineage:
        raise ExperimentError("receipt snapshot lineage is missing")
    if any(not isinstance(item, dict) or set(item) != {"key", "value"} for item in lineage):
        raise ExperimentError("receipt snapshot lineage is malformed")
    if lineage != _EXPECTED_SOURCE_LINEAGE:
        raise ExperimentError("receipt snapshot does not contain the exact deterministic fixture lineage")


def _validate_fixed_artifact_counts(row_counts: Mapping[str, Any]) -> None:
    if row_counts != _EXPECTED_ARTIFACT_ROW_COUNTS:
        raise ExperimentError("artifact row counts differ from the fixed timing-probe row count contract")


def _validate_fixed_artifact_hashes(hashes: Mapping[str, Any]) -> None:
    if hashes != _EXPECTED_ARTIFACT_SHA256:
        raise ExperimentError("artifact differs from the fixed research artifact SHA256 contract")


def _verify_receipt_integrity(receipt: Mapping[str, Any]) -> None:
    integrity = receipt.get("receipt_integrity")
    if not isinstance(integrity, dict) or integrity.get("algorithm") != "sha256":
        raise ExperimentError("receipt integrity metadata is malformed")
    if set(integrity) != {"algorithm", "scope", "sha256"}:
        raise ExperimentError("receipt integrity fields are malformed")
    if integrity["scope"] != "canonical_receipt_without_receipt_integrity":
        raise ExperimentError("receipt integrity scope is unsupported")
    unsigned = dict(receipt)
    unsigned.pop("receipt_integrity", None)
    if integrity["sha256"] != _sha256(_canonical_json_bytes(unsigned)):
        raise ExperimentError("receipt integrity hash mismatch")


def _verify_record_columns(artifacts: Mapping[str, Any]) -> None:
    for filename, columns in (
        ("trades.jsonl", _TRADE_COLUMNS),
        ("orders.jsonl", _ORDER_COLUMNS),
        ("equity.jsonl", _EQUITY_COLUMNS),
    ):
        for index, record in enumerate(artifacts[filename]):
            if not isinstance(record, dict) or set(record) != set(columns):
                raise ExperimentError(f"{filename} row {index} fields do not match the v1 contract")
    for index, trade in enumerate(artifacts["trades.jsonl"]):
        _require_session_date(trade["signal_date"], f"trades.jsonl row {index} signal_date")
        _require_session_date(trade["date"], f"trades.jsonl row {index} date")
        _require_integer(trade["shares"], f"trades.jsonl row {index} shares")
        for field in ("price", "gross", "commission", "stamp_tax", "cash_delta"):
            _require_decimal_string(trade[field], f"trades.jsonl row {index} {field}")
    for index, order in enumerate(artifacts["orders.jsonl"]):
        _require_session_date(order["signal_date"], f"orders.jsonl row {index} signal_date")
        if order["date"] is not None:
            _require_session_date(order["date"], f"orders.jsonl row {index} date")
        if order["requested_shares"] is not None:
            _require_integer(order["requested_shares"], f"orders.jsonl row {index} requested_shares")
        if not isinstance(order["targets"], list) or any(not isinstance(item, str) for item in order["targets"]):
            raise ExperimentError(f"orders.jsonl row {index} targets must be a string list")
    for index, equity in enumerate(artifacts["equity.jsonl"]):
        _require_session_date(equity["date"], f"equity.jsonl row {index} date")
        for field in _EQUITY_COLUMNS[1:]:
            _require_decimal_string(equity[field], f"equity.jsonl row {index} {field}")
    if artifacts["trades.jsonl"] != sorted(
        artifacts["trades.jsonl"],
        key=lambda row: tuple(_sort_token(row[column]) for column in ("signal_date", "date", "symbol", "side")),
    ):
        raise ExperimentError("trades.jsonl rows are not in canonical order")
    if artifacts["orders.jsonl"] != sorted(
        artifacts["orders.jsonl"],
        key=lambda row: tuple(
            _sort_token(row[column])
            for column in ("signal_date", "date", "symbol", "side", "record_type", "status")
        ),
    ):
        raise ExperimentError("orders.jsonl rows are not in canonical order")
    if artifacts["equity.jsonl"] != sorted(
        artifacts["equity.jsonl"], key=lambda row: _sort_token(row["date"])
    ):
        raise ExperimentError("equity.jsonl rows are not in canonical order")


def _verify_metrics_payload(metrics: Mapping[str, Any]) -> None:
    if set(metrics) != {"classification", "not_performance_evidence", "values"}:
        raise ExperimentError("metrics payload fields do not match the v1 contract")
    if metrics["classification"] != "fixture_arithmetic_only" or metrics["not_performance_evidence"] is not True:
        raise ExperimentError("metrics payload is not labelled as fixture arithmetic")
    if not isinstance(metrics["values"], dict) or not metrics["values"]:
        raise ExperimentError("metrics payload values are missing")
    for key, value in metrics["values"].items():
        _require_decimal_string(value, f"metrics.json values.{key}")


def _require_decimal_string(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _DECIMAL_PATTERN.fullmatch(value):
        raise ExperimentError(f"{label} must use the canonical finite decimal string encoding")
    if _decimal_text(value) != value:
        raise ExperimentError(f"{label} is not a canonical decimal string")


def _require_integer(value: Any, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExperimentError(f"{label} must use JSON integer encoding")


def _require_session_date(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SESSION_DATE_PATTERN.fullmatch(value):
        raise ExperimentError(f"{label} must use YYYY-MM-DD session-date encoding")
    try:
        pd.Timestamp(value)
    except ValueError as exc:
        raise ExperimentError(f"{label} is not a valid session date") from exc


def _expected_conventions() -> dict[str, Any]:
    return {
        "costs": {
            "commission_rate": "0.0",
            "slippage_bps": "0.0",
            "stamp_tax_rate": "0.0",
        },
        "decision": {
            "information_cutoff": "completed_session_close_and_snapshot_signal_available_at",
            "same_session_fill_allowed": False,
        },
        "fill": {
            "cost_application": "explicit_after_raw_open_reference",
            "lot_size_source": "snapshot_tradability",
            "t_plus_one_source": "snapshot_tradability",
        },
        "fill_reference": {
            "adjusted_price_allowed": False,
            "price": "raw_open",
            "session": "next_available_market_session",
        },
        "marking": {"adjusted_price_allowed": False, "price": "raw_close"},
        "signal": {"factor": "roe_ttm", "time": "session_close_after_data_availability"},
    }


def _expected_canonicalization_contract() -> dict[str, Any]:
    return {
        "decimal_encoding": "finite base-10 string with a decimal point; no exponent",
        "integer_encoding": "JSON integer",
        "missing_value_encoding": "JSON null",
        "row_order": "contract-specific stable lexicographic keys",
        "timestamp_encoding": "session dates YYYY-MM-DD; other timestamps RFC3339 UTC",
    }


def _expected_determinism() -> dict[str, Any]:
    return {
        "byte_identity_scope": "same snapshot, repository identities, and environment facts",
        "environment_fields_allowed_to_vary": [
            "pandas_version",
            "platform_machine",
            "platform_system",
            "python_implementation",
            "python_version",
        ],
        "research_artifact_hashes": [
            "equity.jsonl",
            "metrics.json",
            "orders.jsonl",
            "strategy_config",
            "trades.jsonl",
        ],
    }


def _expected_verdict() -> dict[str, Any]:
    return {
        "generalization_evidence": False,
        "performance_evidence": False,
        "reason_codes": list(REASON_CODES),
        "status": "INSUFFICIENT_EVIDENCE",
        "usable_for_trading_decisions": False,
    }


def _agent_identity(sha_for_testing: str | None) -> dict[str, Any]:
    if sha_for_testing is not None:
        _validate_sha(sha_for_testing, "test Agent SHA")
        return {
            **AGENT_REPOSITORY,
            "checkout_root": None,
            "dirty_state": {
                "is_dirty": None,
                "method": "unit-test SHA injection; checkout not observed",
                "observed": False,
            },
            "sha": sha_for_testing,
        }
    # Provenance belongs to the code being executed, not to the caller's cwd.
    # Resolving from __file__ also keeps `python -m ...` honest when PYTHONPATH
    # points at this checkout from inside some unrelated Git repository.
    root = _find_git_root(Path(__file__).resolve().parent)
    return _git_identity(root, AGENT_REPOSITORY)


def _qdata_identity(
    *,
    manifest: Mapping[str, Any],
    snapshot_dir: str | Path,
    qdata_checkout: str | Path | None,
    qdata_sha: str | None,
    sha_for_testing: str | None,
) -> dict[str, Any]:
    supplied = sum(value is not None for value in (qdata_checkout, qdata_sha, sha_for_testing))
    if supplied != 1:
        raise ExperimentError("provide exactly one QData checkout or explicit fixture SHA")
    if sha_for_testing is not None:
        _validate_sha(sha_for_testing, "test QData SHA")
        sha = sha_for_testing
        method = "unit-test SHA injection; checkout not observed"
    elif qdata_sha is not None:
        if manifest.get("source") != "deterministic_synthetic_fixture":
            raise ExperimentError("an explicit QData SHA is allowed only for the synthetic fixture")
        _validate_sha(qdata_sha, "explicit QData SHA")
        sha = qdata_sha
        method = "explicit fixture SHA; checkout not observed"
    else:
        identity = _git_identity(Path(qdata_checkout).expanduser().resolve(), QDATA_REPOSITORY)
        _verify_qdata_builder_checkout(identity["checkout_root"], Path(snapshot_dir))
        identity["provenance_verification"] = QDATA_PROVENANCE_BUILDER
        return identity
    return {
        **QDATA_REPOSITORY,
        "checkout_root": None,
        "dirty_state": {"is_dirty": None, "method": method, "observed": False},
        "provenance_verification": QDATA_PROVENANCE_REFERENCE,
        "sha": sha,
    }


def _verify_qdata_builder_checkout(checkout_root: Path, snapshot_dir: Path) -> None:
    builder = checkout_root / "examples" / "build_research_snapshot.py"
    builder_module = checkout_root / "qdata" / "research_snapshot.py"
    for path in (builder, builder_module):
        try:
            info = path.lstat()
        except OSError as exc:
            raise ExperimentError("QData checkout lacks the database-free snapshot builder") from exc
        if not stat.S_ISREG(info.st_mode) or path.is_symlink():
            raise ExperimentError("QData checkout lacks the database-free snapshot builder")

    with tempfile.TemporaryDirectory(prefix="agent-qdata-builder-proof-") as temp_dir:
        rebuilt_snapshot = Path(temp_dir) / "snapshot"
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            result = subprocess.run(
                [sys.executable, str(builder), "build", str(rebuilt_snapshot)],
                cwd=checkout_root,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExperimentError("QData database-free snapshot builder could not be executed") from exc
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "builder failed"
            raise ExperimentError(f"QData database-free snapshot builder failed: {detail}")
        expected_payloads = _read_exact_snapshot_files(snapshot_dir)
        rebuilt_payloads = _read_exact_snapshot_files(rebuilt_snapshot)
        if rebuilt_payloads != expected_payloads:
            raise ExperimentError(
                "QData database-free snapshot builder output does not byte-match the supplied snapshot"
            )


def _read_exact_snapshot_files(root: Path) -> dict[str, bytes]:
    try:
        info = root.lstat()
        if not stat.S_ISDIR(info.st_mode) or root.is_symlink():
            raise ExperimentError("QData database-free snapshot builder output is not a regular directory")
        names = {path.name for path in root.iterdir()}
    except OSError as exc:
        raise ExperimentError("cannot read QData database-free snapshot builder output") from exc
    if names != set(SNAPSHOT_FILENAMES):
        raise ExperimentError("QData database-free snapshot builder produced an unexpected file set")
    payloads: dict[str, bytes] = {}
    for filename in SNAPSHOT_FILENAMES:
        path = root / filename
        try:
            file_info = path.lstat()
            if not stat.S_ISREG(file_info.st_mode) or path.is_symlink():
                raise ExperimentError(f"QData snapshot file is not regular: {filename}")
            payloads[filename] = path.read_bytes()
        except OSError as exc:
            raise ExperimentError(f"cannot read QData snapshot file: {filename}") from exc
    return payloads


def _git_identity(root: Path, expected: Mapping[str, str]) -> dict[str, Any]:
    actual_root = _run_git(root, "rev-parse", "--show-toplevel")
    canonical_root = Path(actual_root).resolve()
    sha = _run_git(canonical_root, "rev-parse", "--verify", "HEAD^{commit}")
    _validate_sha(sha, f"{expected['canonical_name']} HEAD")
    remote = _run_git(canonical_root, "remote", "get-url", "origin")
    if _normalize_remote_url(remote) != expected["canonical_remote_url"]:
        raise ExperimentError(f"{expected['canonical_name']} origin does not match its canonical remote")
    status_output = _run_git(canonical_root, "status", "--porcelain=v1", "--untracked-files=normal")
    return {
        **expected,
        "checkout_root": canonical_root,
        "dirty_state": {
            "is_dirty": bool(status_output),
            "method": "git status --porcelain=v1 --untracked-files=normal",
            "observed": True,
        },
        "sha": sha,
    }


def _public_repository_identity(identity: Mapping[str, Any]) -> dict[str, Any]:
    public_identity = {
        "canonical_name": identity["canonical_name"],
        "canonical_remote_url": identity["canonical_remote_url"],
        "dirty_state": identity["dirty_state"],
        "sha": identity["sha"],
    }
    if "provenance_verification" in identity:
        public_identity["provenance_verification"] = identity["provenance_verification"]
    return public_identity


def _find_git_root(start: Path) -> Path:
    try:
        return Path(_run_git(start, "rev-parse", "--show-toplevel")).resolve()
    except ExperimentError as exc:
        raise ExperimentError("run the command from an Agent Git checkout") from exc


def _run_git(root: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise ExperimentError("Git is required to resolve repository provenance") from exc
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "Git command failed"
        raise ExperimentError(message)
    return result.stdout.strip()


def _normalize_remote_url(value: str) -> str:
    remote = value.strip()
    if remote.startswith("git@github.com:"):
        remote = "https://github.com/" + remote[len("git@github.com:"):]
    if remote.startswith("ssh://git@github.com/"):
        remote = "https://github.com/" + remote[len("ssh://git@github.com/"):]
    if remote.endswith(".git"):
        remote = remote[:-4]
    return remote


def _validate_sha(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SHA_PATTERN.fullmatch(value):
        raise ExperimentError(f"{label} must be a full lowercase 40-hex Git object ID")


def _validate_fresh_output(output: Path) -> None:
    if output.is_symlink():
        raise ExperimentError("output directory must not be a symbolic link")
    if output.exists():
        if not output.is_dir():
            raise ExperimentError("output path already exists and is not a directory")
        try:
            next(output.iterdir())
        except StopIteration:
            return
        raise ExperimentError("refusing to overwrite a nonempty output directory")


def _require_output_untracked_if_inside_checkout(output: Path, checkout_root: Any) -> None:
    if not isinstance(checkout_root, Path):
        return
    try:
        output.relative_to(checkout_root)
    except ValueError:
        return
    result = subprocess.run(
        ["git", "-C", str(checkout_root), "check-ignore", "--quiet", str(output)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ExperimentError("output inside the Agent checkout must be covered by .gitignore")


def _read_exact_output_files(root: Path) -> dict[str, bytes]:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory_only = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory_only is None:
        raise ExperimentError("strict no-follow output verification is unavailable")
    close_on_exec = getattr(os, "O_CLOEXEC", 0)
    nonblocking = getattr(os, "O_NONBLOCK", 0)
    directory_fd: int | None = None
    file_descriptors: dict[str, int] = {}
    try:
        directory_fd = os.open(root, os.O_RDONLY | directory_only | nofollow | close_on_exec)
        directory_info = os.fstat(directory_fd)
        if not stat.S_ISDIR(directory_info.st_mode):
            raise ExperimentError("experiment output must be a regular directory")
        names = set(os.listdir(directory_fd))
        if names != set(OUTPUT_FILENAMES):
            raise ExperimentError(
                f"experiment output files mismatch: expected {list(OUTPUT_FILENAMES)}, got {sorted(names)}"
            )
        directory_identity = _file_identity(directory_info)
        file_identities: dict[str, tuple[int, ...]] = {}
        for filename in OUTPUT_FILENAMES:
            descriptor = os.open(
                filename,
                os.O_RDONLY | nofollow | close_on_exec | nonblocking,
                dir_fd=directory_fd,
            )
            file_descriptors[filename] = descriptor
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise ExperimentError(f"{filename} must be a regular file")
            if info.st_nlink != 1:
                raise ExperimentError(f"{filename} must not be hard-linked")
            file_identities[filename] = _file_identity(info)

        payloads = {
            filename: _read_file_descriptor(descriptor)
            for filename, descriptor in file_descriptors.items()
        }

        if _file_identity(os.fstat(directory_fd)) != directory_identity:
            raise ExperimentError("experiment output directory changed during verification")
        if set(os.listdir(directory_fd)) != set(OUTPUT_FILENAMES):
            raise ExperimentError("experiment output file set changed during verification")

        for filename, descriptor in file_descriptors.items():
            identity = file_identities[filename]
            if _file_identity(os.fstat(descriptor)) != identity:
                raise ExperimentError(f"{filename} changed during verification")
            entry_info = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
            if _file_identity(entry_info) != identity:
                raise ExperimentError(f"{filename} changed during verification")
            second_payload = _read_file_descriptor(descriptor)
            if _sha256(second_payload) != _sha256(payloads[filename]):
                raise ExperimentError(f"{filename} changed during verification")
            if _file_identity(os.fstat(descriptor)) != identity:
                raise ExperimentError(f"{filename} changed during verification")

        if _file_identity(os.fstat(directory_fd)) != directory_identity:
            raise ExperimentError("experiment output directory changed during verification")
        if set(os.listdir(directory_fd)) != set(OUTPUT_FILENAMES):
            raise ExperimentError("experiment output file set changed during verification")
        return payloads
    except ExperimentError:
        raise
    except OSError as exc:
        raise ExperimentError("experiment output changed during verification") from exc
    finally:
        for descriptor in file_descriptors.values():
            try:
                os.close(descriptor)
            except OSError:
                pass
        if directory_fd is not None:
            try:
                os.close(directory_fd)
            except OSError:
                pass


def _read_file_descriptor(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _file_identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_mode),
        int(info.st_nlink),
        int(info.st_size),
        int(info.st_mtime_ns),
        int(info.st_ctime_ns),
    )


def _write_new_file(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)


def _decode_canonical_json(payload: bytes, label: str) -> Any:
    try:
        text = payload.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda token: (_raise_nonfinite(label, token)),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExperimentError(f"{label} is not valid UTF-8 JSON") from exc
    if payload != _canonical_json_bytes(value):
        raise ExperimentError(f"{label} is not canonical JSON")
    return value


def _decode_canonical_jsonl(payload: bytes, label: str) -> list[Any]:
    if not payload or not payload.endswith(b"\n"):
        raise ExperimentError(f"{label} must end with exactly one canonical newline")
    lines = payload.splitlines(keepends=True)
    if any(line in {b"\n", b"\r\n"} for line in lines):
        raise ExperimentError(f"{label} must not contain blank rows")
    return [_decode_canonical_json(line, f"{label} row {index}") for index, line in enumerate(lines)]


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ExperimentError(f"canonical JSON contains duplicate key: {key}")
        output[key] = value
    return output


def _raise_nonfinite(label: str, token: str) -> Any:
    raise ExperimentError(f"{label} contains non-finite JSON value {token}")


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ExperimentError("value cannot be represented as canonical finite JSON") from exc


def _canonical_jsonl_bytes(records: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(_canonical_json_bytes(record) for record in records)


def _normalize_json_value(value: Any) -> Any:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        if value.tzinfo is None and value == value.normalize():
            return value.strftime("%Y-%m-%d")
        timestamp = value.tz_localize("UTC") if value.tzinfo is None else value.tz_convert("UTC")
        return timestamp.isoformat().replace("+00:00", "Z")
    if isinstance(value, bool):
        return value
    if pd.api.types.is_bool(value):
        return bool(value)
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, (numbers.Real, Decimal)):
        return _decimal_text(value)
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return {str(key): _normalize_json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize_json_value(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    raise ExperimentError(f"unsupported canonical value type: {type(value).__name__}")


def _decimal_text(value: Any) -> str:
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise ExperimentError("decimal value is malformed") from exc
    if not number.is_finite():
        raise ExperimentError("decimal value must be finite")
    if number == 0:
        return "0.0"
    text = format(number, "f")
    if "." not in text:
        text += ".0"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
        if "." not in text:
            text += ".0"
    return text


def _sort_token(value: Any) -> tuple[int, str]:
    return (1, "") if value is None else (0, json.dumps(value, ensure_ascii=False, sort_keys=True))


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m a_share_quant_agent.reproducible_experiment",
        description="Run or verify the fixed QData-to-Agent timing probe.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="run the fixed synthetic timing probe")
    run_parser.add_argument("--snapshot-dir", required=True)
    run_parser.add_argument("--output-dir", required=True)
    provenance = run_parser.add_mutually_exclusive_group(required=True)
    provenance.add_argument("--qdata-checkout")
    provenance.add_argument("--qdata-sha")

    verify_parser = subparsers.add_parser("verify", help="verify an emitted receipt and artifacts")
    verify_parser.add_argument("--output-dir", required=True)
    verify_parser.add_argument("--expected-agent-sha")
    verify_parser.add_argument("--expected-qdata-sha")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "run":
            receipt = run_experiment(
                arguments.snapshot_dir,
                arguments.output_dir,
                qdata_checkout=arguments.qdata_checkout,
                qdata_sha=arguments.qdata_sha,
            )
            print(
                f"wrote {arguments.output_dir}: {receipt['verdict']['status']} "
                f"({receipt['snapshot']['snapshot_id']})"
            )
        else:
            receipt = verify_experiment(
                arguments.output_dir,
                expected_agent_sha=arguments.expected_agent_sha,
                expected_qdata_sha=arguments.expected_qdata_sha,
            )
            print(
                f"verified {arguments.output_dir}: {receipt['verdict']['status']} "
                f"({receipt['snapshot']['snapshot_id']})"
            )
    except (ExperimentError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["ExperimentError", "RECEIPT_SCHEMA_VERSION", "run_experiment", "verify_experiment"]
