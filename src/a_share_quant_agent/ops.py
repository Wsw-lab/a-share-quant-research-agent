from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import pandas as pd

from .paper_control import load_paper_dashboard


SCHEDULER_DIR = "scheduler"
SCHEDULER_JSONL = "runs.jsonl"
SCHEDULER_CSV = "runs.csv"
NOTIFICATIONS_DIR = "notifications"
NOTIFICATIONS_JSONL = "notifications.jsonl"
NOTIFICATIONS_CSV = "notifications.csv"
OPS_SNAPSHOT_JSON = "ops_snapshot.json"

SCHEDULER_COLUMNS = (
    "scheduler_run_id",
    "created_at",
    "run_date",
    "scheduled_time",
    "status",
    "dry_run",
    "trading_day",
    "duplicate",
    "returncode",
    "summary_path",
    "report_path",
    "pipeline_id",
    "notification_count",
    "reason",
    "command",
)

NOTIFICATION_COLUMNS = (
    "notification_id",
    "created_at",
    "updated_at",
    "status",
    "severity",
    "category",
    "title",
    "detail",
    "action_required",
    "source_id",
    "dedupe_key",
    "pipeline_id",
    "control_id",
    "ack_actor",
    "ack_reason",
    "acked_at",
)


def run_scheduler_once(
    reports_root: str | Path,
    *,
    config_path: str | Path,
    run_date: str | date | None = None,
    dry_run: bool = True,
    force: bool = False,
    skip_weekends: bool = True,
    scheduled_time: str | None = None,
    command: list[str] | None = None,
    timeout_seconds: int = 7200,
) -> dict[str, object]:
    reports_path = Path(reports_root)
    reports_path.mkdir(parents=True, exist_ok=True)
    scheduler_id = _make_id("scheduler")
    target_date = _date_string(run_date)
    target_time = _time_string(scheduled_time)
    trading_day = _is_trading_day(target_date) if skip_weekends else True
    duplicate = _has_scheduler_run_for_date(reports_path, target_date)
    started_at = _now()
    cmd = command or [
        sys.executable,
        str(Path(__file__).resolve().parents[2] / "examples" / "run_daily_pipeline.py"),
        "--config",
        str(config_path),
    ]
    row: dict[str, object] = {
        "scheduler_run_id": scheduler_id,
        "created_at": started_at,
        "run_date": target_date,
        "scheduled_time": target_time,
        "status": "running",
        "dry_run": bool(dry_run),
        "trading_day": bool(trading_day),
        "duplicate": bool(duplicate),
        "returncode": "",
        "summary_path": "",
        "report_path": "",
        "pipeline_id": "",
        "notification_count": 0,
        "reason": "",
        "command": " ".join(str(item) for item in cmd),
    }

    if target_time and not _is_after_scheduled_time(target_date, target_time):
        row.update({"status": "skipped_before_scheduled_time", "reason": f"Scheduled time {target_time} has not arrived."})
    elif not trading_day:
        row.update({"status": "skipped_non_trading_day", "reason": "Run date is not a trading day under weekday calendar."})
    elif duplicate and not force:
        row.update({"status": "skipped_duplicate", "reason": "A scheduler run for this date already exists. Use force to override."})
    elif dry_run:
        row.update({"status": "dry_run", "reason": "Scheduler dry-run did not execute daily pipeline."})
        latest = latest_pipeline_summary(reports_path)
        if latest:
            row.update(
                {
                    "summary_path": str(latest.get("_summary_path", "")),
                    "report_path": str(latest.get("_report_path", "")),
                    "pipeline_id": str(latest.get("pipeline_id", "")),
                }
            )
    else:
        completed = subprocess.run(cmd, cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=timeout_seconds)
        summary_path = _summary_path_from_stdout(completed.stdout)
        summary = _read_json(Path(summary_path)) if summary_path else latest_pipeline_summary(reports_path)
        row.update(
            {
                "status": "succeeded" if completed.returncode == 0 else "failed",
                "returncode": int(completed.returncode),
                "summary_path": str(summary_path or summary.get("_summary_path", "")) if isinstance(summary, dict) else "",
                "report_path": str(summary.get("_report_path", "")) if isinstance(summary, dict) else "",
                "pipeline_id": str(summary.get("pipeline_id", "")) if isinstance(summary, dict) else "",
                "reason": _short_text(completed.stderr or completed.stdout, 400),
            }
        )

    notifications = create_scheduler_notifications(reports_path, row)
    row["notification_count"] = len(notifications)
    _append_scheduler_run(reports_path, row)
    build_ops_snapshot(reports_path)
    return row


def create_scheduler_notifications(reports_root: str | Path, scheduler_run: dict[str, object]) -> list[dict[str, object]]:
    reports_path = Path(reports_root)
    status = str(scheduler_run.get("status", ""))
    scheduler_id = str(scheduler_run.get("scheduler_run_id", ""))
    notifications = []
    if status in {"failed"}:
        notifications.append(
            create_notification(
                reports_path,
                category="scheduler",
                severity="critical",
                title="Daily scheduler failed",
                detail=str(scheduler_run.get("reason", "") or "Daily scheduler command failed."),
                source_id=scheduler_id,
                pipeline_id=str(scheduler_run.get("pipeline_id", "")),
                action_required=True,
                dedupe_key=f"scheduler_failed:{scheduler_id}",
            )
        )
    elif status in {"dry_run", "succeeded"}:
        notifications.append(
            create_notification(
                reports_path,
                category="scheduler",
                severity="info",
                title="Daily scheduler checked",
                detail=f"Scheduler status {status} for {scheduler_run.get('run_date', '')}.",
                source_id=scheduler_id,
                pipeline_id=str(scheduler_run.get("pipeline_id", "")),
                action_required=False,
                dedupe_key=f"scheduler:{scheduler_id}",
            )
        )
    elif status.startswith("skipped"):
        notifications.append(
            create_notification(
                reports_path,
                category="scheduler",
                severity="info",
                title="Daily scheduler skipped",
                detail=str(scheduler_run.get("reason", "") or status),
                source_id=scheduler_id,
                pipeline_id=str(scheduler_run.get("pipeline_id", "")),
                action_required=False,
                dedupe_key=f"scheduler_skipped:{scheduler_id}",
            )
        )

    summary = _read_json(Path(str(scheduler_run.get("summary_path", ""))))
    if isinstance(summary, dict) and summary:
        notifications.extend(create_pipeline_notifications(reports_path, summary, source_id=scheduler_id))
    return notifications


def create_pipeline_notifications(
    reports_root: str | Path,
    summary: dict[str, object],
    *,
    source_id: str = "",
) -> list[dict[str, object]]:
    reports_path = Path(reports_root)
    pipeline_id = str(summary.get("pipeline_id", ""))
    status = str(summary.get("status", ""))
    health = summary.get("health") if isinstance(summary.get("health"), dict) else {}
    paper = summary.get("paper_control") if isinstance(summary.get("paper_control"), dict) else {}
    control_id = str(paper.get("control_id", "") or "")
    rows = [
        create_notification(
            reports_path,
            category="daily_pipeline",
            severity="info" if status == "succeeded" else "critical",
            title="Daily pipeline completed" if status == "succeeded" else "Daily pipeline needs attention",
            detail=f"Pipeline {pipeline_id or 'n/a'} status={status}; allowed_to_trade={summary.get('allowed_to_trade', False)}; ready_for_review={summary.get('ready_for_review', False)}.",
            source_id=source_id or pipeline_id,
            pipeline_id=pipeline_id,
            control_id=control_id,
            action_required=status != "succeeded",
            dedupe_key=f"pipeline:{pipeline_id}:status",
        )
    ]
    if str(health.get("state", "")) not in {"", "ok"}:
        rows.append(
            create_notification(
                reports_path,
                category="health",
                severity="warning",
                title="Health gate needs attention",
                detail=f"Health state={health.get('state', 'n/a')}; freshness={_nested(health, 'freshness', 'verdict') or 'n/a'}.",
                source_id=source_id or pipeline_id,
                pipeline_id=pipeline_id,
                control_id=control_id,
                action_required=True,
                dedupe_key=f"health:{pipeline_id}",
            )
        )
    if bool(summary.get("ready_for_review", False)):
        rows.append(
            create_notification(
                reports_path,
                category="paper_review",
                severity="warning",
                title="Paper orders waiting for review",
                detail=f"Paper control {control_id or 'n/a'} has risk-passing orders waiting for manual approval.",
                source_id=source_id or control_id,
                pipeline_id=pipeline_id,
                control_id=control_id,
                action_required=True,
                dedupe_key=f"paper_review:{control_id}",
            )
        )
    risk_status = str(_nested(paper, "risk_gate", "status") or "")
    if risk_status == "fail":
        rows.append(
            create_notification(
                reports_path,
                category="paper_risk",
                severity="critical",
                title="Paper risk gate failed",
                detail=f"Paper control {control_id or 'n/a'} failed {_nested(paper, 'risk_gate', 'failed') or 0} risk checks.",
                source_id=source_id or control_id,
                pipeline_id=pipeline_id,
                control_id=control_id,
                action_required=True,
                dedupe_key=f"paper_risk:{control_id}",
            )
        )
    return rows


def create_notification(
    reports_root: str | Path,
    *,
    category: str,
    severity: str,
    title: str,
    detail: str,
    source_id: str = "",
    pipeline_id: str = "",
    control_id: str = "",
    action_required: bool = False,
    dedupe_key: str = "",
) -> dict[str, object]:
    reports_path = Path(reports_root)
    existing = _find_open_notification(reports_path, dedupe_key) if dedupe_key else None
    if existing:
        return existing
    now = _now()
    row = {
        "notification_id": _make_id("notif"),
        "created_at": now,
        "updated_at": now,
        "status": "open",
        "severity": severity,
        "category": category,
        "title": title,
        "detail": detail,
        "action_required": bool(action_required),
        "source_id": source_id,
        "dedupe_key": dedupe_key,
        "pipeline_id": pipeline_id,
        "control_id": control_id,
        "ack_actor": "",
        "ack_reason": "",
        "acked_at": "",
    }
    _append_notification(reports_path, row)
    return row


def ack_notification(
    reports_root: str | Path,
    notification_id: str,
    *,
    actor: str,
    reason: str,
) -> dict[str, object]:
    reports_path = Path(reports_root)
    notifications = notifications_dataframe(reports_path)
    if notifications.empty:
        return {"status": "no_notifications", "acked": 0, "notification_ids": []}
    actor_text = str(actor or "operator").strip() or "operator"
    reason_text = str(reason or "").strip() or "acknowledged"
    if str(notification_id).lower() == "all":
        mask = notifications["status"].astype(str).eq("open")
    else:
        mask = notifications["notification_id"].astype(str).eq(str(notification_id))
    selected = notifications[mask].copy()
    if selected.empty:
        return {"status": "not_found", "acked": 0, "notification_ids": []}
    acked_ids = []
    for _, row in selected.iterrows():
        payload = {str(key): _json_ready(value) for key, value in row.to_dict().items()}
        payload.update(
            {
                "status": "acked",
                "updated_at": _now(),
                "ack_actor": actor_text,
                "ack_reason": reason_text,
                "acked_at": _now(),
            }
        )
        acked_ids.append(str(payload.get("notification_id", "")))
        _append_jsonl(_notifications_root(reports_path) / NOTIFICATIONS_JSONL, payload)
    _write_notifications_csv(reports_path)
    build_ops_snapshot(reports_path)
    return {"status": "acked", "acked": len(acked_ids), "notification_ids": acked_ids}


def build_ops_snapshot(reports_root: str | Path) -> dict[str, object]:
    reports_path = Path(reports_root)
    scheduler = scheduler_runs_dataframe(reports_path)
    notifications = notifications_dataframe(reports_path)
    latest_summary = latest_pipeline_summary(reports_path)
    health = _read_json(reports_path / "health_status.json")
    paper = load_paper_dashboard(reports_path)
    open_notifications = _open_notifications(notifications)
    snapshot = {
        "generated_at": _now(),
        "scheduler": {
            "runs": int(len(scheduler)),
            "latest": _frame_latest(scheduler),
            "open_notifications": int(len(open_notifications)),
        },
        "notifications": {
            "total": int(len(notifications)),
            "open": int(len(open_notifications)),
            "action_required_open": int(
                len(open_notifications[open_notifications.get("action_required", pd.Series(dtype=object)).astype(str).isin({"True", "true", "1"})])
            )
            if not open_notifications.empty
            else 0,
        },
        "latest_pipeline": _summary_brief(latest_summary),
        "health": health if isinstance(health, dict) else {},
        "paper": {
            "control_id": _nested(paper.get("latest_control", {}), "control_id"),
            "status": _nested(paper.get("latest_control", {}), "status"),
            "risk_gate": _nested(paper.get("risk_gate", {}), "status"),
            "equity": _nested(paper.get("account", {}), "equity"),
            "pending_orders": _nested(paper.get("latest_control", {}), "orders", "pending_review"),
            "approved_orders": _nested(paper.get("latest_control", {}), "orders", "approved"),
        },
    }
    ops_root = reports_path / "ops"
    ops_root.mkdir(parents=True, exist_ok=True)
    (ops_root / OPS_SNAPSHOT_JSON).write_text(json.dumps(_json_ready(snapshot), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return {
        **snapshot,
        "scheduler_runs": scheduler,
        "notifications_frame": notifications,
        "paper_dashboard": paper,
    }


def latest_pipeline_summary(reports_root: str | Path) -> dict[str, object]:
    root = Path(reports_root) / "daily_pipeline"
    paths = sorted(root.glob("*/summary.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in paths:
        payload = _read_json(path)
        if isinstance(payload, dict) and payload:
            payload["_summary_path"] = str(path)
            payload["_report_path"] = str(path.with_name("summary.md"))
            return payload
    return {}


def scheduler_runs_dataframe(reports_root: str | Path) -> pd.DataFrame:
    path = _scheduler_root(Path(reports_root)) / SCHEDULER_JSONL
    if not path.exists():
        return pd.DataFrame(columns=SCHEDULER_COLUMNS)
    rows = []
    for item in _read_jsonl(path):
        if isinstance(item, dict) and item.get("scheduler_run_id"):
            rows.append(item)
    if not rows:
        return pd.DataFrame(columns=SCHEDULER_COLUMNS)
    frame = pd.DataFrame(rows)
    frame.sort_values("created_at", ascending=False, inplace=True)
    return _with_columns(frame, SCHEDULER_COLUMNS)


def notifications_dataframe(reports_root: str | Path) -> pd.DataFrame:
    path = _notifications_root(Path(reports_root)) / NOTIFICATIONS_JSONL
    if not path.exists():
        return pd.DataFrame(columns=NOTIFICATION_COLUMNS)
    latest: dict[str, dict[str, object]] = {}
    for item in _read_jsonl(path):
        if isinstance(item, dict) and item.get("notification_id"):
            latest[str(item["notification_id"])] = item
    if not latest:
        return pd.DataFrame(columns=NOTIFICATION_COLUMNS)
    frame = pd.DataFrame(latest.values())
    frame.sort_values("created_at", ascending=False, inplace=True)
    return _with_columns(frame, NOTIFICATION_COLUMNS)


def _append_scheduler_run(reports_root: Path, row: dict[str, object]) -> None:
    _append_jsonl(_scheduler_root(reports_root) / SCHEDULER_JSONL, row)
    frame = scheduler_runs_dataframe(reports_root)
    _write_csv(frame, _scheduler_root(reports_root) / SCHEDULER_CSV)


def _append_notification(reports_root: Path, row: dict[str, object]) -> None:
    _append_jsonl(_notifications_root(reports_root) / NOTIFICATIONS_JSONL, row)
    _write_notifications_csv(reports_root)


def _write_notifications_csv(reports_root: Path) -> None:
    frame = notifications_dataframe(reports_root)
    _write_csv(frame, _notifications_root(reports_root) / NOTIFICATIONS_CSV)


def _scheduler_root(reports_root: Path) -> Path:
    return reports_root / SCHEDULER_DIR


def _notifications_root(reports_root: Path) -> Path:
    return reports_root / NOTIFICATIONS_DIR


def _date_string(value: str | date | None) -> str:
    if value is None:
        return date.today().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def _time_string(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    parts = text.split(":")
    if len(parts) == 2 and all(part.isdigit() for part in parts):
        hour = int(parts[0])
        minute = int(parts[1])
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    raise ValueError("scheduled_time must use HH:MM format")


def _is_after_scheduled_time(run_date: str, scheduled_time: str) -> bool:
    try:
        scheduled = datetime.fromisoformat(f"{run_date}T{scheduled_time}:00")
    except ValueError:
        return False
    return datetime.now() >= scheduled


def _is_trading_day(value: str) -> bool:
    try:
        return datetime.fromisoformat(value).weekday() < 5
    except ValueError:
        return False


def _has_scheduler_run_for_date(reports_root: Path, run_date: str) -> bool:
    frame = scheduler_runs_dataframe(reports_root)
    if frame.empty:
        return False
    statuses = {"dry_run", "succeeded", "running"}
    matches = frame[(frame["run_date"].astype(str) == run_date) & (frame["status"].astype(str).isin(statuses))]
    return not matches.empty


def _summary_path_from_stdout(stdout: str) -> str:
    for line in stdout.splitlines():
        if line.startswith("Summary:"):
            return line.removeprefix("Summary:").strip()
    return ""


def _find_open_notification(reports_root: Path, dedupe_key: str) -> dict[str, object] | None:
    frame = notifications_dataframe(reports_root)
    if frame.empty or "dedupe_key" not in frame.columns:
        return None
    matches = frame[(frame["dedupe_key"].astype(str) == dedupe_key) & (frame["status"].astype(str) == "open")]
    if matches.empty:
        return None
    return {str(key): _json_ready(value) for key, value in matches.iloc[0].to_dict().items()}


def _open_notifications(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "status" not in frame.columns:
        return pd.DataFrame(columns=NOTIFICATION_COLUMNS)
    return frame[frame["status"].astype(str).eq("open")].copy()


def _frame_latest(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {}
    return {str(key): _json_ready(value) for key, value in frame.iloc[0].to_dict().items()}


def _summary_brief(summary: dict[str, object]) -> dict[str, object]:
    if not isinstance(summary, dict) or not summary:
        return {}
    paper = summary.get("paper_control") if isinstance(summary.get("paper_control"), dict) else {}
    return {
        "pipeline_id": summary.get("pipeline_id", ""),
        "status": summary.get("status", ""),
        "allowed_to_trade": bool(summary.get("allowed_to_trade", False)),
        "ready_for_review": bool(summary.get("ready_for_review", False)),
        "selected_candidate_run_id": summary.get("selected_candidate_run_id", ""),
        "paper_control_id": paper.get("control_id", ""),
        "paper_status": paper.get("status", ""),
        "summary_path": summary.get("_summary_path", ""),
        "report_path": summary.get("_report_path", ""),
    }


def _read_json(path: Path) -> object:
    if not path.exists() or not str(path):
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _read_jsonl(path: Path) -> list[object]:
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _append_jsonl(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_json_ready(payload), ensure_ascii=False, sort_keys=True) + "\n")


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _with_columns(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    output = frame.copy()
    for column in columns:
        if column not in output.columns:
            output[column] = ""
    return output.loc[:, list(columns)]


def _nested(container: object, *keys: str) -> object:
    current = container
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _make_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"


def _short_text(value: str, limit: int) -> str:
    text = str(value or "").strip().replace("\n", " ")
    return text[:limit]


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
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
