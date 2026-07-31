from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
from typing import Any

import pandas as pd


FRESHNESS_LIMITS = {
    "investoday_daily": 5,
    "benchmark_alignment": 2,
}

HEALTH_PRIORITY = ("job_failures", "no_real_data", "stale_data", "degraded", "ok")


def freshness_policy(row: pd.Series | dict[str, object]) -> dict[str, object]:
    source = str(_value(row, "source", ""))
    status = str(_value(row, "data_quality_status", "unknown"))
    latest_data_date = str(_value(row, "latest_data_date", "") or "")
    freshness_days = _to_optional_int(_value(row, "freshness_days", None))
    benchmark_aligned_days = _to_optional_int(_value(row, "benchmark_aligned_days", None))

    if source == "sample":
        return _freshness_result(
            verdict="sample_only",
            ok=False,
            reason="Sample data is deterministic test data and cannot satisfy production freshness.",
            latest_data_date=latest_data_date,
            freshness_days=freshness_days,
        )
    if not _is_real_data_source(source):
        return _freshness_result(
            verdict="unknown_source",
            ok=False,
            reason="Freshness policy is only defined for Investoday or canonical historical asset real-data runs.",
            latest_data_date=latest_data_date,
            freshness_days=freshness_days,
        )
    if status in {"empty", "missing_columns"}:
        return _freshness_result(
            verdict="bad_data",
            ok=False,
            reason=f"Data quality status is {status}.",
            latest_data_date=latest_data_date,
            freshness_days=freshness_days,
        )
    if freshness_days is None:
        return _freshness_result(
            verdict="unknown_freshness",
            ok=False,
            reason="Latest data date is unavailable.",
            latest_data_date=latest_data_date,
            freshness_days=freshness_days,
        )
    if freshness_days > FRESHNESS_LIMITS["investoday_daily"]:
        return _freshness_result(
            verdict="stale",
            ok=False,
            reason=f"Real daily data is {freshness_days} days old; limit is {FRESHNESS_LIMITS['investoday_daily']} days.",
            latest_data_date=latest_data_date,
            freshness_days=freshness_days,
        )
    if benchmark_aligned_days is not None and benchmark_aligned_days < FRESHNESS_LIMITS["benchmark_alignment"]:
        return _freshness_result(
            verdict="benchmark_missing",
            ok=False,
            reason=(
                f"Benchmark alignment has {benchmark_aligned_days} trading days; "
                f"minimum is {FRESHNESS_LIMITS['benchmark_alignment']}."
            ),
            latest_data_date=latest_data_date,
            freshness_days=freshness_days,
        )
    return _freshness_result(
        verdict="fresh",
        ok=True,
        reason="Real daily data is within freshness policy.",
        latest_data_date=latest_data_date,
        freshness_days=freshness_days,
    )


def health_gate(registry: pd.DataFrame, jobs: pd.DataFrame | list[dict[str, object]], reports_root: str | Path) -> dict[str, object]:
    job_frame = _jobs_frame(jobs)
    real_runs = _real_runs(registry)
    latest_real = real_runs.iloc[0] if not real_runs.empty else None
    running_jobs = _status_count(job_frame, {"queued", "running", "retrying"})
    failed_jobs = _status_count(job_frame, {"failed"})
    interrupted_jobs = _status_count(job_frame, {"interrupted"})
    latest_failed_job = _latest_status_job(job_frame, {"failed", "interrupted"})
    latest_warmup = _latest_job(job_frame, "cache_warmup")
    latest_warmup_result = latest_warmup.get("result") if isinstance(latest_warmup, dict) else {}
    latest_warmup_result = latest_warmup_result if isinstance(latest_warmup_result, dict) else {}
    latest_warmup_artifact = _latest_warmup_artifact(Path(reports_root))
    if _is_newer_warmup_artifact(latest_warmup_artifact, latest_warmup):
        latest_warmup = {
            "job_id": latest_warmup_artifact.get("warmup_id", ""),
            "kind": "cache_warmup_artifact",
            "label": "Cache warmup artifact",
            "status": "succeeded",
            "created_at": latest_warmup_artifact.get("created_at", ""),
            "updated_at": latest_warmup_artifact.get("created_at", ""),
        }
        latest_warmup_result = latest_warmup_artifact

    if latest_real is None:
        freshness = _freshness_result(
            verdict="no_real_data",
            ok=False,
            reason="No Investoday or canonical historical asset real-data registry row is available.",
            latest_data_date="",
            freshness_days=None,
        )
    else:
        freshness = freshness_policy(latest_real)

    state = "ok"
    suggestions: list[str] = []
    if failed_jobs or interrupted_jobs:
        state = _worse_state(state, "job_failures")
        suggestions.append("Open /jobs, inspect the latest failed or interrupted job, then retry if it was a data-source or network failure.")
    if latest_real is None:
        state = _worse_state(state, "no_real_data")
        suggestions.append("Run an Investoday warmup or canonical production research run before trusting production health.")
    elif freshness["verdict"] == "stale":
        state = _worse_state(state, "stale_data")
        suggestions.append("Submit /warmup for the target Investoday universe and date range, then rerun the research job.")
    elif not freshness["ok"]:
        state = _worse_state(state, "degraded")
        suggestions.append(str(freshness["reason"]))
    if running_jobs:
        state = _worse_state(state, "degraded")
        suggestions.append("Background jobs are still running; refresh /jobs before making research decisions.")
    if not suggestions:
        suggestions.append("Health gate is clear. Continue with batch research or review score-sorted /compare.")

    payload = {
        "state": state,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "registry_rows": int(len(registry)),
        "real_run_count": int(len(real_runs)),
        "running_jobs": running_jobs,
        "failed_jobs": failed_jobs,
        "interrupted_jobs": interrupted_jobs,
        "latest_real_run": _row_dict(latest_real),
        "freshness": freshness,
        "latest_failed_job": latest_failed_job,
        "latest_warmup_job": latest_warmup,
        "latest_warmup_artifact": latest_warmup_artifact,
        "latest_warmup_result": latest_warmup_result,
        "suggestions": suggestions,
    }
    path = Path(reports_root) / "health_status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_ready(payload), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def _freshness_result(
    *,
    verdict: str,
    ok: bool,
    reason: str,
    latest_data_date: str,
    freshness_days: int | None,
) -> dict[str, object]:
    return {
        "verdict": verdict,
        "ok": bool(ok),
        "reason": reason,
        "latest_data_date": latest_data_date,
        "freshness_days": freshness_days,
        "policy": dict(FRESHNESS_LIMITS),
    }


def _real_runs(registry: pd.DataFrame) -> pd.DataFrame:
    if registry.empty or "source" not in registry.columns:
        return pd.DataFrame()
    source = registry["source"].astype(str)
    frame = registry[source.str.contains("investoday:", regex=False) | source.str.contains("historical_asset:", regex=False)].copy()
    if frame.empty:
        return frame
    frame["_latest_data_sort"] = pd.to_datetime(frame.get("latest_data_date"), errors="coerce")
    frame.sort_values(["_latest_data_sort", "created_at"], ascending=[False, False], inplace=True)
    frame.drop(columns=["_latest_data_sort"], inplace=True)
    return frame.reset_index(drop=True)


def _is_real_data_source(source: str) -> bool:
    return "investoday:" in source or "historical_asset:" in source


def _jobs_frame(jobs: pd.DataFrame | list[dict[str, object]]) -> pd.DataFrame:
    if isinstance(jobs, pd.DataFrame):
        return jobs.copy()
    if not jobs:
        return pd.DataFrame()
    return pd.DataFrame([_json_ready(job) for job in jobs if isinstance(job, dict)])


def _status_count(jobs: pd.DataFrame, statuses: set[str]) -> int:
    if jobs.empty or "status" not in jobs.columns:
        return 0
    return int(jobs["status"].astype(str).isin(statuses).sum())


def _latest_status_job(jobs: pd.DataFrame, statuses: set[str]) -> dict[str, object]:
    if jobs.empty or "status" not in jobs.columns:
        return {}
    frame = jobs[jobs["status"].astype(str).isin(statuses)].copy()
    if frame.empty:
        return {}
    frame.sort_values("created_at", ascending=False, inplace=True)
    return _row_dict(frame.iloc[0])


def _latest_job(jobs: pd.DataFrame, kind: str) -> dict[str, object]:
    if jobs.empty or "kind" not in jobs.columns:
        return {}
    frame = jobs[jobs["kind"].astype(str).eq(kind)].copy()
    if frame.empty:
        return {}
    frame.sort_values("created_at", ascending=False, inplace=True)
    return _row_dict(frame.iloc[0])


def _latest_warmup_artifact(reports_root: Path) -> dict[str, object]:
    root = reports_root / "cache_warmups"
    if not root.exists():
        return {}
    rows: list[dict[str, object]] = []
    for path in root.glob("*/metadata.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            payload = dict(payload)
            payload.setdefault("metadata_path", str(path))
            rows.append(payload)
    if not rows:
        return {}
    rows.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return _json_ready(rows[0]) if isinstance(_json_ready(rows[0]), dict) else {}


def _is_newer_warmup_artifact(artifact: dict[str, object], job: dict[str, object]) -> bool:
    if not artifact:
        return False
    if not job:
        return True
    return str(artifact.get("created_at", "")) >= str(job.get("created_at", ""))


def _row_dict(row: pd.Series | None) -> dict[str, object]:
    if row is None:
        return {}
    return {str(key): _json_ready(value) for key, value in row.to_dict().items()}


def _worse_state(current: str, candidate: str) -> str:
    current_rank = HEALTH_PRIORITY.index(current) if current in HEALTH_PRIORITY else len(HEALTH_PRIORITY)
    candidate_rank = HEALTH_PRIORITY.index(candidate) if candidate in HEALTH_PRIORITY else len(HEALTH_PRIORITY)
    return candidate if candidate_rank < current_rank else current


def _value(row: pd.Series | dict[str, object], key: str, default: object) -> object:
    if isinstance(row, pd.Series):
        if key not in row:
            return default
        value = row[key]
    else:
        value = row.get(key, default)
    return default if _missing(value) else value


def _missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value == ""
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _to_optional_int(value: object) -> int | None:
    if _missing(value):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _json_ready(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if _missing(value):
        return None
    return value
