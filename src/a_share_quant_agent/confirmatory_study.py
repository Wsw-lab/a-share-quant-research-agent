"""Locked, all-results-reported confirmatory factor study.

The maintained synthetic experiment proves execution contracts.  This module
serves a different purpose: it lets a researcher run one pre-registered,
out-of-sample factor study on locally licensed market data without committing
the raw data.  The receipt never promotes statistics to a trading claim.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd


SCHEMA_VERSION = "confirmatory_factor_study_v1"
RECEIPT_SCHEMA_VERSION = "confirmatory_study_receipt_v1"
EXPECTED_VARIANTS = (
    "M0_naive",
    "M1_pit_universe",
    "M2_pit_publication",
    "M3_audited_lag",
)
EXPECTED_FACTORS = ("roe", "momentum_60d", "low_vol_20d", "composite")


class ConfirmatoryStudyError(RuntimeError):
    """Raised when a plan, input, result set, or receipt cannot be trusted."""


def run_confirmatory_study(
    *,
    plan_path: str | Path,
    quotes_path: str | Path,
    stock_master_path: str | Path,
    fundamentals_path: str | Path,
    data_declaration_path: str | Path,
    code_revision: str,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Run every registered variant/factor and atomically publish one receipt."""

    plan_path = _regular_file(plan_path, "plan")
    quotes_path = _regular_file(quotes_path, "quotes")
    stock_master_path = _regular_file(stock_master_path, "stock_master")
    fundamentals_path = _regular_file(fundamentals_path, "fundamentals")
    declaration_path = _regular_file(data_declaration_path, "data_declaration")
    output = Path(output_dir).expanduser().resolve(strict=False)
    if output.exists():
        raise ConfirmatoryStudyError(f"output directory already exists: {output}")

    plan_bytes = plan_path.read_bytes()
    plan = _read_json_object(plan_bytes, "plan")
    _validate_plan(plan)
    declaration = _read_json_object(declaration_path.read_bytes(), "data declaration")
    _validate_declaration(declaration)
    if not isinstance(code_revision, str) or not _is_git_sha(code_revision):
        raise ConfirmatoryStudyError("code_revision must be a 40-character Git commit SHA")

    quotes = _load_quotes(quotes_path)
    stock_master = _load_stock_master(stock_master_path)
    fundamentals = _load_fundamentals(fundamentals_path)
    prepared = _prepare_quotes(quotes, int(plan["forward_horizon_sessions"]))
    rebalance_dates = _monthly_rebalance_dates(
        prepared,
        str(plan["test_period"][0]),
        str(plan["test_period"][1]),
    )
    observations = _run_registered_cells(
        prepared=prepared,
        stock_master=stock_master,
        fundamentals=fundamentals,
        rebalance_dates=rebalance_dates,
        plan=plan,
    )
    results = _aggregate_results(observations, plan)
    expected_result_count = len(plan["variants"]) * len(plan["factors"])
    if len(results) != expected_result_count:
        raise ConfirmatoryStudyError(
            f"registered result set is incomplete: expected {expected_result_count}, got {len(results)}"
        )

    data_files = {
        "quotes": _file_evidence(quotes_path),
        "stock_master": _file_evidence(stock_master_path),
        "fundamentals": _file_evidence(fundamentals_path),
        "data_declaration": _file_evidence(declaration_path),
    }
    status = _evidence_status(
        declaration=declaration,
        symbol_count=int(prepared["symbol"].nunique()),
        test_rebalance_count=len(rebalance_dates),
        plan=plan,
    )
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "study_id": str(plan["study_id"]),
        "code": {"agent_git_sha": code_revision.lower()},
        "plan": {
            "schema_version": str(plan["schema_version"]),
            "status": str(plan["status"]),
            "locked_at": str(plan["locked_at"]),
            "sha256": _sha256(plan_bytes),
            "registered_variants": list(plan["variants"]),
            "registered_factors": list(plan["factors"]),
            "minimum_symbols": int(plan["minimum_symbols"]),
            "minimum_oos_rebalances": int(plan["minimum_oos_rebalances"]),
        },
        "data": {
            "classification": declaration["source_classification"],
            "source_name": declaration["source_name"],
            "redistributable": bool(declaration["redistributable"]),
            "price_semantics": declaration["price_semantics"],
            "rights_review": declaration["rights_review"],
            "files": data_files,
        },
        "sample": {
            "train_start": str(plan["train_period"][0]),
            "train_end": str(plan["train_period"][1]),
            "test_start": str(plan["test_period"][0]),
            "test_end": str(plan["test_period"][1]),
            "market_start": prepared["date"].min().date().isoformat(),
            "market_end": prepared["date"].max().date().isoformat(),
            "symbol_count": int(prepared["symbol"].nunique()),
            "row_count": int(len(prepared)),
            "test_rebalance_count": len(rebalance_dates),
            "forward_horizon_sessions": int(plan["forward_horizon_sessions"]),
        },
        "method": {
            "outcome": "cross-sectional rank IC and top-quintile minus universe forward return",
            "inference": "Newey-West t-statistic over monthly observations",
            "M0_naive": "final-survivor universe; report-period availability; same-close horizon",
            "M1_pit_universe": "point-in-time listing universe; report-period availability; same-close horizon",
            "M2_pit_publication": "point-in-time universe; publication-date fundamentals; same-close horizon",
            "M3_audited_lag": "PIT universe and fundamentals; ST/suspension/liquidity filters; one-session lag",
        },
        "results": results,
        "selection_control": {
            "all_registered_results_reported": True,
            "best_result_selected": False,
            "expected_result_count": expected_result_count,
            "reported_result_count": len(results),
        },
        "status": status,
    }
    receipt["receipt_integrity"] = {
        "algorithm": "sha256",
        "scope": "canonical_receipt_without_receipt_integrity",
        "sha256": _sha256(_canonical_bytes(receipt)),
    }
    payload = _canonical_bytes(receipt)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".confirmatory-study-", dir=output.parent))
    try:
        (staging / "receipt.json").write_bytes(payload)
        staging.replace(output)
    except Exception:
        if staging.exists():
            for item in staging.iterdir():
                item.unlink()
            staging.rmdir()
        raise
    verify_study_receipt(output / "receipt.json")
    return receipt


def verify_study_receipt(path: str | Path) -> dict[str, Any]:
    receipt_path = _regular_file(path, "receipt")
    payload = receipt_path.read_bytes()
    receipt = _read_json_object(payload, "receipt")
    if payload != _canonical_bytes(receipt):
        raise ConfirmatoryStudyError("receipt is not canonical JSON")
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        raise ConfirmatoryStudyError("unsupported confirmatory receipt schema")
    code = receipt.get("code") or {}
    if not _is_git_sha(code.get("agent_git_sha")):
        raise ConfirmatoryStudyError("receipt is not bound to an Agent Git commit")
    integrity = receipt.get("receipt_integrity")
    if not isinstance(integrity, dict):
        raise ConfirmatoryStudyError("receipt integrity is missing")
    unsigned = dict(receipt)
    unsigned.pop("receipt_integrity", None)
    if integrity.get("sha256") != _sha256(_canonical_bytes(unsigned)):
        raise ConfirmatoryStudyError("receipt integrity mismatch")
    plan = receipt.get("plan") or {}
    if (
        plan.get("schema_version") != SCHEMA_VERSION
        or plan.get("status") != "locked"
        or tuple(plan.get("registered_variants") or ()) != EXPECTED_VARIANTS
        or tuple(plan.get("registered_factors") or ()) != EXPECTED_FACTORS
    ):
        raise ConfirmatoryStudyError("receipt differs from the maintained registered plan")
    control = receipt.get("selection_control") or {}
    results = receipt.get("results")
    if not isinstance(results, list):
        raise ConfirmatoryStudyError("receipt results must be a list")
    expected = control.get("expected_result_count")
    if (
        control.get("all_registered_results_reported") is not True
        or control.get("best_result_selected") is not False
        or expected != len(results)
        or control.get("reported_result_count") != len(results)
    ):
        raise ConfirmatoryStudyError("receipt does not report the complete registered result set")
    registered = {
        (variant, factor)
        for variant in receipt["plan"]["registered_variants"]
        for factor in receipt["plan"]["registered_factors"]
    }
    reported = {(row.get("variant"), row.get("factor")) for row in results}
    if reported != registered:
        raise ConfirmatoryStudyError("receipt result cells differ from the registered plan")
    status = receipt.get("status") or {}
    if any(
        status.get(key) is not False
        for key in ("performance_claim", "generalization_claim", "usable_for_trading_decisions")
    ):
        raise ConfirmatoryStudyError("receipt claim flags must remain false")
    if status.get("code") == "REAL_MARKET_OOS_STATISTICS":
        data = receipt.get("data") or {}
        sample = receipt.get("sample") or {}
        if (
            data.get("classification") != "real_market_data"
            or int(sample.get("symbol_count", 0)) < int(plan.get("minimum_symbols", 0))
            or int(sample.get("test_rebalance_count", 0))
            < int(plan.get("minimum_oos_rebalances", 0))
        ):
            raise ConfirmatoryStudyError("real-market status is inconsistent with receipt evidence")
    elif status.get("code") != "INSUFFICIENT_EVIDENCE":
        raise ConfirmatoryStudyError("unsupported receipt evidence status")
    return receipt


def build_public_evidence_status(receipt_paths: Iterable[str | Path]) -> dict[str, Any]:
    receipts = [verify_study_receipt(path) for path in receipt_paths]
    if not receipts:
        raise ConfirmatoryStudyError("at least one verified receipt is required")
    codes = [receipt["status"]["code"] for receipt in receipts]
    status = (
        "REAL_MARKET_OOS_STATISTICS"
        if "REAL_MARKET_OOS_STATISTICS" in codes
        else "INSUFFICIENT_EVIDENCE"
    )
    return {
        "schema_version": "public_evidence_status_v1",
        "status": status,
        "source_of_truth": "verified_confirmatory_receipts",
        "verified_receipt_count": len(receipts),
        "study_ids": sorted({receipt["study_id"] for receipt in receipts}),
        "performance_claim": False,
        "generalization_claim": False,
        "usable_for_trading_decisions": False,
    }


def write_public_evidence_status(
    receipt_paths: Iterable[str | Path], output_path: str | Path
) -> dict[str, Any]:
    """Atomically derive the public status file from verified receipts only."""

    status = build_public_evidence_status(receipt_paths)
    destination = Path(output_path).expanduser().resolve(strict=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=f".{destination.name}.",
        dir=destination.parent,
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(_canonical_bytes(status))
        handle.flush()
    try:
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return status


def _validate_plan(plan: Mapping[str, Any]) -> None:
    if plan.get("schema_version") != SCHEMA_VERSION:
        raise ConfirmatoryStudyError("unsupported plan schema")
    if plan.get("status") != "locked":
        raise ConfirmatoryStudyError("plan must be locked before data analysis")
    if tuple(plan.get("variants") or ()) != EXPECTED_VARIANTS:
        raise ConfirmatoryStudyError("registered variants must match the maintained ablation sequence")
    if tuple(plan.get("factors") or ()) != EXPECTED_FACTORS:
        raise ConfirmatoryStudyError("registered factors must match the maintained factor set")
    required = (
        "study_id", "locked_at", "train_period", "test_period",
        "forward_horizon_sessions", "minimum_amount", "minimum_symbols",
        "minimum_oos_rebalances", "composite_weights",
    )
    missing = [key for key in required if key not in plan]
    if missing:
        raise ConfirmatoryStudyError(f"plan missing required fields: {missing}")
    train = plan["train_period"]
    test = plan["test_period"]
    if not (isinstance(train, list) and len(train) == 2 and isinstance(test, list) and len(test) == 2):
        raise ConfirmatoryStudyError("train_period and test_period must be two-item lists")
    train_start, train_end, test_start, test_end = map(pd.Timestamp, (*train, *test))
    if not (train_start <= train_end < test_start <= test_end):
        raise ConfirmatoryStudyError("train and test periods must be ordered and non-overlapping")
    weights = plan["composite_weights"]
    if set(weights) != {"roe", "momentum_60d", "low_vol_20d"}:
        raise ConfirmatoryStudyError("composite weights must cover the three registered base factors")
    if not math.isclose(sum(float(value) for value in weights.values()), 1.0, abs_tol=1e-12):
        raise ConfirmatoryStudyError("composite weights must sum to one")


def _validate_declaration(declaration: Mapping[str, Any]) -> None:
    required = {
        "source_classification", "source_name", "redistributable",
        "price_semantics", "rights_review",
    }
    missing = sorted(required - set(declaration))
    if missing:
        raise ConfirmatoryStudyError(f"data declaration missing fields: {missing}")
    if declaration["source_classification"] not in {"synthetic_fixture", "real_market_data"}:
        raise ConfirmatoryStudyError("unsupported source_classification")


def _load_quotes(path: Path) -> pd.DataFrame:
    columns = ["date", "symbol", "close", "amount", "is_st", "is_suspended"]
    frame = pd.read_csv(path, usecols=columns, low_memory=False)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    frame["symbol"] = frame["symbol"].astype(str)
    for name in ("close", "amount"):
        frame[name] = pd.to_numeric(frame[name], errors="coerce")
    for name in ("is_st", "is_suspended"):
        frame[name] = frame[name].map(_as_bool)
    frame = frame.dropna(subset=["date", "symbol", "close", "amount"])
    if frame.duplicated(["date", "symbol"]).any():
        raise ConfirmatoryStudyError("quotes contain duplicate (date, symbol) keys")
    if (frame["close"] <= 0).any() or (frame["amount"] < 0).any():
        raise ConfirmatoryStudyError("quotes contain invalid close or amount values")
    return frame.sort_values(["symbol", "date"]).reset_index(drop=True)


def _load_stock_master(path: Path) -> pd.DataFrame:
    columns = ["symbol", "listDate", "delistDate", "listStatus", "stockType"]
    frame = pd.read_csv(path, usecols=columns, dtype=str)
    frame["listDate"] = pd.to_datetime(frame["listDate"], errors="coerce")
    frame["delistDate"] = pd.to_datetime(frame["delistDate"], errors="coerce")
    if frame["symbol"].duplicated().any():
        raise ConfirmatoryStudyError("stock master contains duplicate symbols")
    return frame


def _load_fundamentals(path: Path) -> pd.DataFrame:
    columns = ["symbol", "roe", "publishDate", "reportPeriodEnd"]
    frame = pd.read_csv(path, usecols=columns, low_memory=False)
    frame["roe"] = pd.to_numeric(frame["roe"], errors="coerce")
    frame["publishDate"] = pd.to_datetime(frame["publishDate"], errors="coerce")
    frame["reportPeriodEnd"] = pd.to_datetime(frame["reportPeriodEnd"], errors="coerce")
    frame = frame.dropna(subset=columns).sort_values(["symbol", "publishDate", "reportPeriodEnd"])
    if frame.empty:
        raise ConfirmatoryStudyError("fundamentals contain no usable ROE observations")
    return frame


def _prepare_quotes(quotes: pd.DataFrame, horizon: int) -> pd.DataFrame:
    if horizon <= 0:
        raise ConfirmatoryStudyError("forward_horizon_sessions must be positive")
    prepared = quotes.copy()
    grouped_close = prepared.groupby("symbol", sort=False)["close"]
    prepared["return_1d"] = grouped_close.pct_change(fill_method=None)
    prepared["momentum_60d"] = grouped_close.pct_change(60, fill_method=None)
    prepared["low_vol_20d"] = -(
        prepared.groupby("symbol", sort=False)["return_1d"]
        .rolling(20, min_periods=20)
        .std()
        .reset_index(level=0, drop=True)
    )
    prepared["future_return_same"] = grouped_close.shift(-horizon) / prepared["close"] - 1.0
    prepared["future_return_lagged"] = (
        grouped_close.shift(-(horizon + 1)) / grouped_close.shift(-1) - 1.0
    )
    prepared["amount_20d"] = (
        prepared.groupby("symbol", sort=False)["amount"]
        .rolling(20, min_periods=20)
        .mean()
        .reset_index(level=0, drop=True)
    )
    return prepared


def _monthly_rebalance_dates(frame: pd.DataFrame, start: str, end: str) -> list[pd.Timestamp]:
    dates = pd.Series(frame.loc[frame["date"].between(start, end), "date"].unique()).sort_values()
    if dates.empty:
        raise ConfirmatoryStudyError("test period has no market sessions")
    table = pd.DataFrame({"date": dates})
    return list(table.groupby(table["date"].dt.to_period("M"))["date"].min())


def _run_registered_cells(
    *,
    prepared: pd.DataFrame,
    stock_master: pd.DataFrame,
    fundamentals: pd.DataFrame,
    rebalance_dates: Sequence[pd.Timestamp],
    plan: Mapping[str, Any],
) -> list[dict[str, Any]]:
    quote_by_date = {day: rows.copy() for day, rows in prepared.groupby("date", sort=False)}
    observations: list[dict[str, Any]] = []
    for day in rebalance_dates:
        base = quote_by_date[day].copy()
        for variant in plan["variants"]:
            cross_section = _variant_cross_section(
                base,
                day=day,
                variant=variant,
                stock_master=stock_master,
                fundamentals=fundamentals,
                minimum_amount=float(plan["minimum_amount"]),
            )
            ranks = {
                factor: cross_section[factor].rank(pct=True, method="average")
                for factor in ("roe", "momentum_60d", "low_vol_20d")
            }
            cross_section["composite"] = sum(
                ranks[factor] * float(weight)
                for factor, weight in plan["composite_weights"].items()
            )
            outcome = "future_return_lagged" if variant == "M3_audited_lag" else "future_return_same"
            for factor in plan["factors"]:
                sample = cross_section[[factor, outcome]].replace([np.inf, -np.inf], np.nan).dropna()
                if len(sample) < 5:
                    observations.append({
                        "date": day.date().isoformat(), "variant": variant, "factor": factor,
                        "ic": None, "top_minus_universe": None, "cross_section_size": len(sample),
                    })
                    continue
                score = sample[factor].rank(pct=True, method="average")
                ic = score.corr(sample[outcome].rank(pct=True, method="average"), method="pearson")
                top = sample.loc[score >= 0.8, outcome]
                spread = top.mean() - sample[outcome].mean()
                observations.append({
                    "date": day.date().isoformat(), "variant": variant, "factor": factor,
                    "ic": _finite_or_none(ic),
                    "top_minus_universe": _finite_or_none(spread),
                    "cross_section_size": int(len(sample)),
                })
    return observations


def _variant_cross_section(
    base: pd.DataFrame,
    *,
    day: pd.Timestamp,
    variant: str,
    stock_master: pd.DataFrame,
    fundamentals: pd.DataFrame,
    minimum_amount: float,
) -> pd.DataFrame:
    if variant == "M0_naive":
        eligible = stock_master.loc[
            stock_master["listStatus"].str.lower().ne("delisted")
            & stock_master["delistDate"].isna(),
            "symbol",
        ]
    else:
        eligible = stock_master.loc[
            stock_master["listDate"].le(day)
            & (stock_master["delistDate"].isna() | stock_master["delistDate"].ge(day)),
            "symbol",
        ]
    selected = base.loc[base["symbol"].isin(set(eligible))].copy()
    if variant == "M3_audited_lag":
        selected = selected.loc[
            ~selected["is_st"]
            & ~selected["is_suspended"]
            & selected["amount_20d"].ge(minimum_amount)
        ]
    availability = "publishDate" if variant in {"M2_pit_publication", "M3_audited_lag"} else "reportPeriodEnd"
    available = fundamentals.loc[fundamentals[availability].le(day)].copy()
    latest = (
        available.sort_values(["symbol", availability, "reportPeriodEnd"])
        .drop_duplicates("symbol", keep="last")[["symbol", "roe"]]
    )
    return selected.merge(latest, on="symbol", how="left", validate="one_to_one")


def _aggregate_results(observations: Sequence[Mapping[str, Any]], plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    frame = pd.DataFrame(observations)
    results: list[dict[str, Any]] = []
    for variant in plan["variants"]:
        for factor in plan["factors"]:
            cell = frame.loc[(frame["variant"] == variant) & (frame["factor"] == factor)]
            ic = pd.to_numeric(cell["ic"], errors="coerce").dropna().to_numpy(dtype=float)
            spread = pd.to_numeric(cell["top_minus_universe"], errors="coerce").dropna().to_numpy(dtype=float)
            results.append({
                "variant": variant,
                "factor": factor,
                "observation_count": int(len(ic)),
                "mean_ic": _rounded_or_none(np.mean(ic) if len(ic) else None),
                "newey_west_t_stat": _rounded_or_none(_newey_west_t_stat(ic, lag=3)),
                "mean_top_minus_universe_return": _rounded_or_none(np.mean(spread) if len(spread) else None),
                "mean_cross_section_size": _rounded_or_none(cell["cross_section_size"].mean()),
            })
    return results


def _newey_west_t_stat(values: np.ndarray, lag: int) -> float | None:
    if len(values) < 3:
        return None
    centered = values - values.mean()
    n = len(values)
    long_run = float(np.dot(centered, centered) / n)
    for offset in range(1, min(lag, n - 1) + 1):
        covariance = float(np.dot(centered[offset:], centered[:-offset]) / n)
        long_run += 2.0 * (1.0 - offset / (lag + 1.0)) * covariance
    if long_run <= 0:
        return None
    standard_error = math.sqrt(long_run / n)
    return float(values.mean() / standard_error) if standard_error else None


def _evidence_status(
    *,
    declaration: Mapping[str, Any],
    symbol_count: int,
    test_rebalance_count: int,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    reasons = []
    if declaration["source_classification"] != "real_market_data":
        reasons.append("SYNTHETIC_DATA")
    if symbol_count < int(plan["minimum_symbols"]):
        reasons.append("INSUFFICIENT_SYMBOL_COVERAGE")
    if test_rebalance_count < int(plan["minimum_oos_rebalances"]):
        reasons.append("INSUFFICIENT_OOS_REBALANCES")
    code = "INSUFFICIENT_EVIDENCE" if reasons else "REAL_MARKET_OOS_STATISTICS"
    caveats = [
        "The receipt reports a locked factor study, not a selected best strategy.",
        "The statistics are not evidence of implementable alpha or live-trading readiness.",
        "Raw data availability and redistribution are governed by the data declaration.",
    ]
    return {
        "code": code,
        "reason_codes": reasons,
        "performance_claim": False,
        "generalization_claim": False,
        "usable_for_trading_decisions": False,
        "caveats": caveats,
    }


def _file_evidence(path: Path) -> dict[str, Any]:
    return {"sha256": _sha256_file(path), "size_bytes": path.stat().st_size}


def _regular_file(path: str | Path, label: str) -> Path:
    resolved = Path(path).expanduser().resolve(strict=False)
    if not resolved.is_file() or resolved.is_symlink():
        raise ConfirmatoryStudyError(f"{label} is not a regular file: {resolved}")
    return resolved


def _read_json_object(payload: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfirmatoryStudyError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ConfirmatoryStudyError(f"{label} must be a JSON object")
    return value


def _as_bool(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ConfirmatoryStudyError(f"invalid boolean value in quotes: {value!r}")


def _finite_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _rounded_or_none(value: Any) -> float | None:
    number = _finite_or_none(value)
    return None if number is None else round(number, 10)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_git_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(
        character in "0123456789abcdefABCDEF" for character in value
    )


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--plan", required=True)
    run.add_argument("--quotes", required=True)
    run.add_argument("--stock-master", required=True)
    run.add_argument("--fundamentals", required=True)
    run.add_argument("--data-declaration", required=True)
    run.add_argument("--code-revision", required=True)
    run.add_argument("--output-dir", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--receipt", required=True)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--receipt", action="append", required=True)
    status_parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "run":
        receipt = run_confirmatory_study(
            plan_path=args.plan,
            quotes_path=args.quotes,
            stock_master_path=args.stock_master,
            fundamentals_path=args.fundamentals,
            data_declaration_path=args.data_declaration,
            code_revision=args.code_revision,
            output_dir=args.output_dir,
        )
        print(f"{receipt['status']['code']}: {args.output_dir}")
    elif args.command == "verify":
        receipt = verify_study_receipt(args.receipt)
        print(f"verified {receipt['study_id']}: {receipt['status']['code']}")
    else:
        status = write_public_evidence_status(args.receipt, args.output)
        print(f"{status['status']}: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
