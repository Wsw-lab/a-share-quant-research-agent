from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .run_registry import registry_dataframe


PAPER_DIR = "paper"
ACCOUNT_STATE = "account_state.json"
ACCOUNT_LEDGER = "account_ledger.csv"
POSITIONS_CSV = "positions.csv"
EQUITY_CURVE_CSV = "equity_curve.csv"
ORDERS_CSV = "orders.csv"
LATEST_ORDERS_CSV = "latest_orders.csv"
TRADES_CSV = "trades.csv"
LATEST_CONTROL_JSON = "latest_control.json"
RISK_GATE_JSON = "risk_gate.json"
CONTROL_JSONL = "control_log.jsonl"
AUDIT_JSONL = "audit_log.jsonl"
AUDIT_CSV = "audit_log.csv"
ALERTS_JSONL = "alerts.jsonl"
ALERTS_CSV = "alerts.csv"
LATEST_ALERTS_JSON = "latest_alerts.json"


DEFAULT_PAPER_CONFIG = {
    "paper_account_id": "paper_default",
    "paper_initial_cash": 10_000_000.0,
    "paper_auto_approve": False,
    "paper_execute_simulated": False,
    "paper_single_position_limit": 0.08,
    "paper_industry_limit": 0.45,
    "paper_max_turnover": 0.85,
    "paper_max_drawdown_stop": -0.12,
    "paper_min_cash_buffer": 0.02,
    "paper_max_order_value": 1_000_000.0,
    "paper_drawdown_buy_stop": -0.08,
    "paper_blacklist_symbols": "",
    "paper_watchlist_symbols": "",
    "paper_alert_on_pending": True,
    "paper_alert_on_risk_fail": True,
}


def run_paper_control_from_summary(
    summary: dict[str, object],
    reports_root: str | Path,
    config: dict[str, object] | None = None,
) -> dict[str, object]:
    reports_path = Path(reports_root)
    cfg = {**DEFAULT_PAPER_CONFIG, **(config or {})}
    control_id = f"paper_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]}"
    run_id = str(summary.get("selected_candidate_run_id", "") or "")
    pipeline_id = str(summary.get("pipeline_id", "") or "")
    paper_root = reports_path / PAPER_DIR
    paper_root.mkdir(parents=True, exist_ok=True)

    account = _load_account_state(paper_root, cfg)
    registry = registry_dataframe(reports_path)
    run_row = _registry_row(registry, run_id)
    if not run_id or run_row is None:
        control = _blocked_control(
            control_id,
            pipeline_id,
            run_id,
            account,
            "no_selected_candidate",
            "Daily pipeline did not select a paper candidate.",
        )
        _write_control_outputs(paper_root, control, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), account)
        _record_control_events(paper_root, control, pd.DataFrame())
        return control

    artifact_dir = Path(str(run_row.get("artifact_dir", "")))
    target_holdings = _read_csv(artifact_dir / "target_holdings.csv")
    source_orders = _read_csv(artifact_dir / "paper_orders.csv")
    industry_metrics = _read_json(artifact_dir / "industry_exposure_metrics.json")
    strategy_spec = _read_json(artifact_dir / "strategy_spec.json")
    if not isinstance(strategy_spec, dict):
        strategy_spec = _read_json(Path(str(run_row.get("spec_path", ""))))
    if not isinstance(strategy_spec, dict):
        strategy_spec = {}

    current_positions = _load_positions(paper_root)
    candidate = _candidate_from_summary(summary, run_id)
    orders, scaled_targets = _build_orders(
        control_id=control_id,
        pipeline_id=pipeline_id,
        run_id=run_id,
        account=account,
        current_positions=current_positions,
        target_holdings=target_holdings,
        source_orders=source_orders,
        strategy_spec=strategy_spec,
        cfg=cfg,
    )
    risk_gate = evaluate_risk_gate(
        summary=summary,
        registry_row=run_row,
        account=account,
        target_holdings=scaled_targets,
        orders=orders,
        industry_metrics=industry_metrics if isinstance(industry_metrics, dict) else {},
        cfg=cfg,
    )
    orders = _apply_review_state(orders, risk_gate=risk_gate, cfg=cfg)
    updated_account, updated_positions, trades = _apply_simulated_execution(
        account,
        current_positions,
        orders,
        scaled_targets,
        execute=_bool(cfg.get("paper_execute_simulated"), False) and _bool(cfg.get("paper_auto_approve"), False),
    )

    status = "blocked_by_risk"
    if risk_gate["status"] == "pass":
        if not orders.empty and not trades.empty:
            status = "executed_simulated"
        elif not orders.empty:
            status = "pending_review"
        else:
            status = "no_orders"
    control = {
        "control_id": control_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "pipeline_id": pipeline_id,
        "run_id": run_id,
        "account_id": account["account_id"],
        "status": status,
        "candidate": candidate,
        "risk_gate": risk_gate,
        "orders": _order_counts(orders),
        "trades": {"count": int(len(trades))},
        "account_before": account,
        "account_after": updated_account,
        "artifact_dir": str(artifact_dir),
        "paths": {
            "paper_root": str(paper_root),
            "latest_control": str(paper_root / LATEST_CONTROL_JSON),
            "risk_gate": str(paper_root / RISK_GATE_JSON),
            "latest_orders": str(paper_root / LATEST_ORDERS_CSV),
            "positions": str(paper_root / POSITIONS_CSV),
            "equity_curve": str(paper_root / EQUITY_CURVE_CSV),
            "audit_log": str(paper_root / AUDIT_CSV),
            "alerts": str(paper_root / ALERTS_CSV),
        },
    }
    _write_control_outputs(paper_root, control, orders, updated_positions, trades, updated_account)
    _write_control_run_dir(paper_root, control_id, control, orders, scaled_targets, trades, risk_gate)
    _record_control_events(paper_root, control, orders)
    return control


def evaluate_risk_gate(
    *,
    summary: dict[str, object],
    registry_row: dict[str, object],
    account: dict[str, object],
    target_holdings: pd.DataFrame,
    orders: pd.DataFrame,
    industry_metrics: dict[str, object],
    cfg: dict[str, object],
) -> dict[str, object]:
    checks = []
    checks.append(_check("pipeline_status", str(summary.get("status", "")) == "succeeded", "Daily pipeline must succeed."))
    checks.append(_check("health_state", str(_nested(summary, "health", "state")) == "ok", "Health gate must be ok."))
    checks.append(
        _check(
            "fresh_data",
            bool(_nested(summary, "health", "freshness", "ok")),
            "Latest Investoday data must satisfy freshness policy.",
        )
    )
    checks.append(_check("candidate_gate", str(registry_row.get("gate_status", "")) == "paper_candidate", "Run must pass decision gate."))
    checks.append(
        _check(
            "production_data_ready",
            _bool(registry_row.get("production_data_ready")),
            "Run must pass the production data trust gate.",
        )
    )
    blocked_orders = int(orders.get("source_blocked", pd.Series(dtype=bool)).fillna(False).sum()) if not orders.empty else 0
    checks.append(_check("execution_blocks", blocked_orders == 0, f"Source paper order blocks: {blocked_orders}."))

    max_weight = float(target_holdings.get("target_weight", pd.Series(dtype=float)).max() or 0.0) if not target_holdings.empty else 0.0
    single_limit = _float(cfg.get("paper_single_position_limit"), 0.08)
    checks.append(_check("single_position", max_weight <= single_limit + 1e-9, f"Max target weight {max_weight:.2%}; limit {single_limit:.2%}."))

    industry_weight = _float(industry_metrics.get("latest_top_weight"), 0.0)
    industry_limit = _float(cfg.get("paper_industry_limit"), 0.45)
    checks.append(
        _check(
            "industry_concentration",
            industry_weight <= industry_limit + 1e-9,
            f"Top industry {industry_metrics.get('latest_top_industry', 'n/a')} {industry_weight:.2%}; limit {industry_limit:.2%}.",
        )
    )

    turnover = _turnover(orders, _float(account.get("equity"), 0.0))
    turnover_limit = _float(cfg.get("paper_max_turnover"), 0.85)
    checks.append(_check("turnover", turnover <= turnover_limit + 1e-9, f"Estimated turnover {turnover:.2%}; limit {turnover_limit:.2%}."))

    drawdown = _account_drawdown(account)
    drawdown_stop = _float(cfg.get("paper_max_drawdown_stop"), -0.12)
    checks.append(_check("drawdown_stop", drawdown >= drawdown_stop, f"Account drawdown {drawdown:.2%}; stop {drawdown_stop:.2%}."))

    cash_after = _float(account.get("cash"), 0.0) + float(orders.get("cash_delta", pd.Series(dtype=float)).sum() if not orders.empty else 0.0)
    cash_buffer = _float(cfg.get("paper_min_cash_buffer"), 0.02)
    equity = _float(account.get("equity"), 0.0)
    checks.append(_check("cash_buffer", cash_after >= equity * cash_buffer, f"Cash after orders {cash_after:,.2f}; buffer {cash_buffer:.2%}."))

    max_order_value = _float(cfg.get("paper_max_order_value"), 1_000_000.0)
    largest_order = float(orders.get("gross", pd.Series(dtype=float)).abs().max() or 0.0) if not orders.empty else 0.0
    checks.append(
        _check(
            "single_order_value",
            largest_order <= max_order_value + 1e-9,
            f"Largest order value {largest_order:,.2f}; limit {max_order_value:,.2f}.",
        )
    )

    has_buy_orders = bool((orders.get("side", pd.Series(dtype=object)).astype(str) == "buy").any()) if not orders.empty else False
    drawdown_buy_stop = _float(cfg.get("paper_drawdown_buy_stop"), -0.08)
    checks.append(
        _check(
            "drawdown_buy_stop",
            not (drawdown <= drawdown_buy_stop and has_buy_orders),
            f"Account drawdown {drawdown:.2%}; buy-stop threshold {drawdown_buy_stop:.2%}.",
        )
    )

    blacklist = _symbol_set(cfg.get("paper_blacklist_symbols", ""))
    order_symbols = {str(symbol) for symbol in orders.get("symbol", pd.Series(dtype=object)).dropna().astype(str)} if not orders.empty else set()
    blacklisted = sorted(order_symbols & blacklist)
    checks.append(
        _check(
            "blacklist",
            not blacklisted,
            f"Blacklisted symbols in orders: {','.join(blacklisted) if blacklisted else 'none'}.",
        )
    )

    watchlist = _symbol_set(cfg.get("paper_watchlist_symbols", ""))
    watched = sorted(order_symbols & watchlist)
    passed = sum(1 for item in checks if item["passed"])
    failed = len(checks) - passed
    return {
        "status": "pass" if failed == 0 else "fail",
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "metrics": {
            "max_target_weight": max_weight,
            "top_industry_weight": industry_weight,
            "estimated_turnover": turnover,
            "account_drawdown": drawdown,
            "cash_after_orders": cash_after,
            "largest_order_value": largest_order,
            "has_buy_orders": has_buy_orders,
            "blacklisted_symbols": blacklisted,
            "watchlist_symbols": watched,
        },
    }


def review_paper_orders(
    reports_root: str | Path,
    *,
    action: str,
    actor: str,
    reason: str = "",
    order_ids: list[str] | tuple[str, ...] | set[str] | None = None,
    control_id: str | None = None,
    execute_simulated: bool = False,
) -> dict[str, object]:
    reports_path = Path(reports_root)
    paper_root = reports_path / PAPER_DIR
    paper_root.mkdir(parents=True, exist_ok=True)
    action = str(action or "").strip().lower()
    if action not in {"approve", "reject", "execute"}:
        raise ValueError("action must be approve, reject, or execute")

    control = _load_review_control(paper_root, control_id)
    if not control:
        raise FileNotFoundError("No paper control is available for review.")
    review_control_id = str(control.get("control_id", "") or "")
    if not review_control_id:
        raise ValueError("Paper control is missing control_id.")

    run_dir = paper_root / "control_runs" / review_control_id
    orders = _read_csv(run_dir / "orders.csv")
    if orders.empty:
        orders = _read_csv(paper_root / LATEST_ORDERS_CSV)
    if orders.empty:
        result = {
            "control_id": review_control_id,
            "action": action,
            "status": "no_orders",
            "selected": 0,
            "executed": 0,
            "message": "No paper orders are available for review.",
        }
        _append_paper_audit(
            paper_root,
            event_type="paper_review_no_orders",
            actor=actor,
            action="纸面订单复核",
            control=control,
            detail=f"操作=无可复核订单 动作={action} 原因={reason or 'none'}",
            order_ids=[],
            result="no_orders",
        )
        return result

    orders = _ensure_review_columns(orders)
    selected_mask = _selected_order_mask(orders, order_ids)
    now = datetime.now().isoformat(timespec="seconds")
    actor_text = str(actor or "operator").strip() or "operator"
    reason_text = str(reason or "").strip() or "no_reason"

    selected_ids: list[str] = []
    execute_mask = pd.Series(False, index=orders.index)
    if action == "approve":
        eligible = selected_mask & orders["status"].astype(str).isin({"pending_review"})
        orders.loc[eligible, "status"] = "approved"
        orders.loc[eligible, "review_status"] = "approved"
        orders.loc[eligible, "reviewer"] = actor_text
        orders.loc[eligible, "reviewed_at"] = now
        orders.loc[eligible, "review_reason"] = reason_text
        selected_ids = orders.loc[eligible, "order_id"].astype(str).tolist()
        if execute_simulated:
            execute_mask = eligible
    elif action == "reject":
        eligible = selected_mask & orders["status"].astype(str).isin({"pending_review", "approved"})
        orders.loc[eligible, "status"] = "rejected"
        orders.loc[eligible, "review_status"] = "rejected"
        orders.loc[eligible, "reviewer"] = actor_text
        orders.loc[eligible, "reviewed_at"] = now
        orders.loc[eligible, "review_reason"] = reason_text
        orders.loc[eligible, "reason"] = reason_text
        selected_ids = orders.loc[eligible, "order_id"].astype(str).tolist()
    else:
        eligible = selected_mask & orders["status"].astype(str).isin({"approved"})
        selected_ids = orders.loc[eligible, "order_id"].astype(str).tolist()
        execute_mask = eligible

    account_before = _load_account_state(paper_root, DEFAULT_PAPER_CONFIG)
    current_positions = _load_positions(paper_root)
    target_holdings = _read_csv(run_dir / "target_holdings.csv")
    updated_account = account_before
    updated_positions = current_positions
    trades = pd.DataFrame()
    if bool(execute_mask.any()):
        execution_orders = orders.loc[execute_mask].copy()
        execution_orders["status"] = "executed_simulated"
        updated_account, updated_positions, trades = _apply_simulated_execution(
            account_before,
            current_positions,
            execution_orders,
            target_holdings,
            execute=True,
        )
        orders.loc[execute_mask, "status"] = "executed_simulated"
        orders.loc[execute_mask, "review_status"] = "approved"
        orders.loc[execute_mask, "executed_at"] = datetime.now().isoformat(timespec="seconds")

    if action == "reject":
        status = "rejected_by_reviewer" if selected_ids else "review_noop"
    elif not selected_ids:
        status = "review_noop"
    elif not trades.empty:
        status = "executed_simulated"
    elif action == "execute":
        status = "approved_pending_execution"
    else:
        status = "approved_pending_execution"

    control = {
        **control,
        "status": status,
        "review": {
            "action": action,
            "actor": actor_text,
            "reason": reason_text,
            "reviewed_at": now,
            "order_ids": selected_ids,
            "execute_simulated": bool(execute_simulated or action == "execute"),
        },
        "orders": _order_counts(orders),
        "trades": {"count": int(_float(_nested(control, "trades", "count"), 0.0) + len(trades))},
        "account_before": control.get("account_before", account_before),
        "account_after": updated_account,
    }
    _write_review_outputs(paper_root, review_control_id, control, orders, updated_positions, trades, updated_account)

    result = {
        "control_id": review_control_id,
        "action": action,
        "status": status,
        "selected": len(selected_ids),
        "executed": int(len(trades)),
        "order_ids": selected_ids,
        "latest_control": str(paper_root / LATEST_CONTROL_JSON),
    }
    _append_paper_audit(
        paper_root,
        event_type="paper_order_review",
        actor=actor_text,
        action="纸面订单复核",
        control=control,
        detail=(
            f"操作={action} 选中订单={len(selected_ids)} 模拟成交={len(trades)} "
            f"状态={status} 原因={reason_text}"
        ),
        order_ids=selected_ids,
        result=status,
    )
    if action == "reject" and selected_ids:
        _append_paper_alert(
            paper_root,
            severity="warning",
            category="paper_review",
            title="Paper orders rejected",
            detail=f"{len(selected_ids)} paper orders were rejected by {actor_text}: {reason_text}",
            control=control,
        )
    if not trades.empty:
        _append_paper_alert(
            paper_root,
            severity="info",
            category="paper_execution",
            title="Paper orders executed",
            detail=f"{len(trades)} approved paper orders were simulated by {actor_text}.",
            control=control,
        )
    return result


def _build_orders(
    *,
    control_id: str,
    pipeline_id: str,
    run_id: str,
    account: dict[str, object],
    current_positions: pd.DataFrame,
    target_holdings: pd.DataFrame,
    source_orders: pd.DataFrame,
    strategy_spec: dict[str, object],
    cfg: dict[str, object],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if target_holdings.empty:
        return pd.DataFrame(), pd.DataFrame()
    account_nav = _float(account.get("equity"), _float(cfg.get("paper_initial_cash"), 10_000_000.0))
    costs = strategy_spec.get("costs") if isinstance(strategy_spec.get("costs"), dict) else {}
    commission_rate = _float(costs.get("commission_rate"), 0.0003) if isinstance(costs, dict) else 0.0003
    stamp_tax_rate = _float(costs.get("stamp_tax_rate"), 0.0005) if isinstance(costs, dict) else 0.0005
    slippage_bps = _float(costs.get("slippage_bps"), 5.0) if isinstance(costs, dict) else 5.0

    source_blocks = _source_blocks(source_orders)
    current = _position_map(current_positions)
    target = target_holdings.copy()
    target["target_weight"] = pd.to_numeric(target["target_weight"], errors="coerce").fillna(0.0)
    target["price"] = pd.to_numeric(target["price"], errors="coerce").fillna(0.0)
    target = target[target["target_weight"] > 0].copy()
    if target.empty:
        return pd.DataFrame(), target
    as_of_date = str(target["as_of_date"].iloc[0]) if "as_of_date" in target else datetime.now().date().isoformat()
    rows = []
    target_rows = []
    symbols = sorted(set(target["symbol"].astype(str)) | set(current))
    target_by_symbol = {str(row["symbol"]): row for _, row in target.iterrows()}
    for symbol in symbols:
        row = target_by_symbol.get(symbol)
        price = float(row["price"]) if row is not None else _float(current.get(symbol, {}).get("last_price"), 0.0)
        target_weight = float(row["target_weight"]) if row is not None else 0.0
        target_shares = _round_lot(int((account_nav * target_weight) / price)) if price > 0 else 0
        current_shares = int(current.get(symbol, {}).get("shares", 0))
        delta = target_shares - current_shares
        target_rows.append(
            {
                "as_of_date": as_of_date,
                "symbol": symbol,
                "price": price,
                "current_shares": current_shares,
                "target_shares": target_shares,
                "delta_shares": delta,
                "target_weight": target_shares * price / account_nav if account_nav else 0.0,
            }
        )
        if delta == 0:
            continue
        side = "buy" if delta > 0 else "sell"
        shares = abs(int(delta))
        order_price = price * (1 + slippage_bps / 10_000.0) if side == "buy" else price * (1 - slippage_bps / 10_000.0)
        gross = shares * order_price
        commission = gross * commission_rate
        stamp_tax = gross * stamp_tax_rate if side == "sell" else 0.0
        cash_delta = -(gross + commission) if side == "buy" else gross - commission - stamp_tax
        block_note = source_blocks.get((symbol, side), "")
        rows.append(
            {
                "order_id": f"{control_id}_{len(rows) + 1:04d}",
                "control_id": control_id,
                "pipeline_id": pipeline_id,
                "run_id": run_id,
                "date": as_of_date,
                "symbol": symbol,
                "side": side,
                "shares": shares,
                "price": order_price,
                "gross": gross,
                "commission": commission,
                "stamp_tax": stamp_tax,
                "cash_delta": cash_delta,
                "target_weight": target_weight,
                "source_blocked": bool(block_note),
                "source_note": block_note,
                "review_status": "new",
                "status": "new",
                "reason": "candidate_rebalance",
            }
        )
    orders = pd.DataFrame(rows)
    scaled_targets = pd.DataFrame(target_rows)
    if not orders.empty:
        orders = _apply_cash_limit(orders, _float(account.get("cash"), 0.0))
    return orders, scaled_targets


def _apply_review_state(orders: pd.DataFrame, *, risk_gate: dict[str, object], cfg: dict[str, object]) -> pd.DataFrame:
    if orders.empty:
        return orders
    output = orders.copy()
    if risk_gate["status"] != "pass":
        output["status"] = "blocked_by_risk"
        output["review_status"] = "rejected"
        output["reason"] = "risk_gate_failed"
        return output
    blocked = output["source_blocked"].fillna(False).astype(bool) | output["status"].astype(str).str.startswith("blocked")
    output.loc[blocked, "status"] = "blocked_by_execution"
    output.loc[blocked, "review_status"] = "rejected"
    tradable = ~blocked
    if _bool(cfg.get("paper_auto_approve"), False):
        output.loc[tradable, "status"] = "approved"
        output.loc[tradable, "review_status"] = "approved"
        if _bool(cfg.get("paper_execute_simulated"), False):
            output.loc[tradable, "status"] = "executed_simulated"
    else:
        output.loc[tradable, "status"] = "pending_review"
        output.loc[tradable, "review_status"] = "pending_review"
    return output


def _apply_simulated_execution(
    account: dict[str, object],
    current_positions: pd.DataFrame,
    orders: pd.DataFrame,
    target_holdings: pd.DataFrame,
    *,
    execute: bool,
) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame]:
    if not execute or orders.empty:
        return account, current_positions, pd.DataFrame()
    positions = _position_map(current_positions)
    cash = _float(account.get("cash"), 0.0)
    trade_rows = []
    executed = orders[orders["status"] == "executed_simulated"].copy()
    for _, order in executed.iterrows():
        symbol = str(order["symbol"])
        side = str(order["side"])
        shares = int(order["shares"])
        price = float(order["price"])
        cash += float(order["cash_delta"])
        current = int(positions.get(symbol, {}).get("shares", 0))
        next_shares = current + shares if side == "buy" else current - shares
        if next_shares <= 0:
            positions.pop(symbol, None)
        else:
            positions[symbol] = {"symbol": symbol, "shares": next_shares, "last_price": price}
        trade_rows.append(
            {
                "trade_id": f"{order['order_id']}_sim",
                "order_id": order["order_id"],
                "control_id": order["control_id"],
                "run_id": order["run_id"],
                "date": order["date"],
                "symbol": symbol,
                "side": side,
                "shares": shares,
                "price": price,
                "gross": float(order["gross"]),
                "commission": float(order["commission"]),
                "stamp_tax": float(order["stamp_tax"]),
                "cash_delta": float(order["cash_delta"]),
                "status": "executed_simulated",
            }
        )
    price_map = _price_map(target_holdings)
    position_rows = []
    market_value = 0.0
    for symbol, position in sorted(positions.items()):
        price = price_map.get(symbol, _float(position.get("last_price"), 0.0))
        shares = int(position.get("shares", 0))
        value = shares * price
        market_value += value
        position_rows.append({"symbol": symbol, "shares": shares, "last_price": price, "market_value": value})
    equity = cash + market_value
    high_watermark = max(_float(account.get("high_watermark"), equity), equity)
    updated = {
        **account,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "cash": cash,
        "market_value": market_value,
        "equity": equity,
        "high_watermark": high_watermark,
        "max_drawdown": equity / high_watermark - 1 if high_watermark else 0.0,
    }
    return updated, pd.DataFrame(position_rows), pd.DataFrame(trade_rows)


def _load_account_state(paper_root: Path, cfg: dict[str, object]) -> dict[str, object]:
    path = paper_root / ACCOUNT_STATE
    if path.exists():
        value = _read_json(path)
        if isinstance(value, dict):
            return value
    initial_cash = _float(cfg.get("paper_initial_cash"), 10_000_000.0)
    now = datetime.now().isoformat(timespec="seconds")
    return {
        "account_id": str(cfg.get("paper_account_id", "paper_default") or "paper_default"),
        "created_at": now,
        "updated_at": now,
        "cash": initial_cash,
        "market_value": 0.0,
        "equity": initial_cash,
        "high_watermark": initial_cash,
        "max_drawdown": 0.0,
        "status": "active",
    }


def _write_control_outputs(
    paper_root: Path,
    control: dict[str, object],
    orders: pd.DataFrame,
    positions: pd.DataFrame,
    trades: pd.DataFrame,
    account: dict[str, object],
) -> None:
    (paper_root / ACCOUNT_STATE).write_text(json.dumps(_json_ready(account), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    (paper_root / LATEST_CONTROL_JSON).write_text(json.dumps(_json_ready(control), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    (paper_root / RISK_GATE_JSON).write_text(json.dumps(_json_ready(control.get("risk_gate", {})), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    _append_jsonl(paper_root / CONTROL_JSONL, control)
    _write_csv(positions, paper_root / POSITIONS_CSV)
    _write_csv(orders, paper_root / LATEST_ORDERS_CSV)
    _append_csv(orders, paper_root / ORDERS_CSV)
    _append_csv(trades, paper_root / TRADES_CSV)
    _append_ledger(paper_root, control, account)


def _write_control_run_dir(
    paper_root: Path,
    control_id: str,
    control: dict[str, object],
    orders: pd.DataFrame,
    target_holdings: pd.DataFrame,
    trades: pd.DataFrame,
    risk_gate: dict[str, object],
) -> None:
    run_dir = paper_root / "control_runs" / control_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "control.json").write_text(json.dumps(_json_ready(control), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    (run_dir / "risk_gate.json").write_text(json.dumps(_json_ready(risk_gate), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    _write_csv(orders, run_dir / "orders.csv")
    _write_csv(target_holdings, run_dir / "target_holdings.csv")
    _write_csv(trades, run_dir / "trades.csv")


def _write_review_outputs(
    paper_root: Path,
    control_id: str,
    control: dict[str, object],
    orders: pd.DataFrame,
    positions: pd.DataFrame,
    trades: pd.DataFrame,
    account: dict[str, object],
) -> None:
    latest_control = _read_json(paper_root / LATEST_CONTROL_JSON)
    is_latest = isinstance(latest_control, dict) and str(latest_control.get("control_id", "")) == control_id
    run_dir = paper_root / "control_runs" / control_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "control.json").write_text(json.dumps(_json_ready(control), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    _write_csv(orders, run_dir / "orders.csv")
    if not trades.empty:
        _append_csv(trades, run_dir / "trades.csv")
    if is_latest:
        (paper_root / ACCOUNT_STATE).write_text(json.dumps(_json_ready(account), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        (paper_root / LATEST_CONTROL_JSON).write_text(json.dumps(_json_ready(control), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        _write_csv(positions, paper_root / POSITIONS_CSV)
        _write_csv(orders, paper_root / LATEST_ORDERS_CSV)
        _append_jsonl(paper_root / CONTROL_JSONL, control)
        _append_csv(orders, paper_root / ORDERS_CSV)
        _append_csv(trades, paper_root / TRADES_CSV)
        _append_ledger(paper_root, control, account)


def _record_control_events(paper_root: Path, control: dict[str, object], orders: pd.DataFrame) -> None:
    risk_status = str(_nested(control, "risk_gate", "status") or "n/a")
    order_count = int(_nested(control, "orders", "count") or 0)
    trade_count = int(_nested(control, "trades", "count") or 0)
    _append_paper_audit(
        paper_root,
        event_type="paper_control_generated",
        actor="system",
        action="纸面控制生成",
        control=control,
        detail=(
            f"状态={control.get('status', '')} 风控={risk_status} "
            f"订单={order_count} 成交={trade_count}"
        ),
        order_ids=orders.get("order_id", pd.Series(dtype=object)).astype(str).tolist() if not orders.empty else [],
        result=str(control.get("status", "")),
    )
    if risk_status == "fail" and _bool(DEFAULT_PAPER_CONFIG.get("paper_alert_on_risk_fail"), True):
        failed = int(_nested(control, "risk_gate", "failed") or 0)
        _append_paper_alert(
            paper_root,
            severity="critical",
            category="risk_gate",
            title="Paper risk gate failed",
            detail=f"Paper control {control.get('control_id', '')} failed {failed} risk checks.",
            control=control,
        )
    pending = int(_nested(control, "orders", "pending_review") or 0)
    if pending and _bool(DEFAULT_PAPER_CONFIG.get("paper_alert_on_pending"), True):
        _append_paper_alert(
            paper_root,
            severity="warning",
            category="approval",
            title="Paper orders pending review",
            detail=f"{pending} paper orders are waiting for manual review.",
            control=control,
        )
    if trade_count:
        _append_paper_alert(
            paper_root,
            severity="info",
            category="paper_execution",
            title="Paper simulated execution completed",
            detail=f"{trade_count} paper orders were simulated for control {control.get('control_id', '')}.",
            control=control,
        )


def _append_paper_audit(
    paper_root: Path,
    *,
    event_type: str,
    actor: str,
    action: str,
    control: dict[str, object],
    detail: str,
    order_ids: list[str],
    result: str,
) -> None:
    row = {
        "event_id": f"audit_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]}",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "event_type": event_type,
        "actor": str(actor or "system"),
        "action": action,
        "message": f"{action} control_id={control.get('control_id', '')} {detail}",
        "control_id": control.get("control_id", ""),
        "pipeline_id": control.get("pipeline_id", ""),
        "run_id": control.get("run_id", ""),
        "status": control.get("status", ""),
        "result": result,
        "order_ids": ",".join(order_ids),
    }
    _append_jsonl(paper_root / AUDIT_JSONL, row)
    _append_csv(pd.DataFrame([row]), paper_root / AUDIT_CSV)


def _append_paper_alert(
    paper_root: Path,
    *,
    severity: str,
    category: str,
    title: str,
    detail: str,
    control: dict[str, object],
) -> None:
    row = {
        "alert_id": f"alert_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]}",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "severity": severity,
        "category": category,
        "title": title,
        "detail": detail,
        "control_id": control.get("control_id", ""),
        "pipeline_id": control.get("pipeline_id", ""),
        "run_id": control.get("run_id", ""),
        "status": "open",
    }
    _append_jsonl(paper_root / ALERTS_JSONL, row)
    _append_csv(pd.DataFrame([row]), paper_root / ALERTS_CSV)
    alerts = _read_csv(paper_root / ALERTS_CSV)
    latest = alerts.tail(50).iloc[::-1].to_dict(orient="records") if not alerts.empty else []
    (paper_root / LATEST_ALERTS_JSON).write_text(json.dumps(_json_ready(latest), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _load_review_control(paper_root: Path, control_id: str | None) -> dict[str, object]:
    latest = _read_json(paper_root / LATEST_CONTROL_JSON)
    if not control_id:
        return latest if isinstance(latest, dict) else {}
    run_control = _read_json(paper_root / "control_runs" / str(control_id) / "control.json")
    return run_control if isinstance(run_control, dict) else {}


def _ensure_review_columns(orders: pd.DataFrame) -> pd.DataFrame:
    output = orders.copy()
    for column in ("reviewer", "reviewed_at", "review_reason", "executed_at"):
        if column not in output.columns:
            output[column] = ""
    return output


def _selected_order_mask(orders: pd.DataFrame, order_ids: list[str] | tuple[str, ...] | set[str] | None) -> pd.Series:
    if not order_ids:
        return pd.Series(True, index=orders.index)
    selected = {str(item).strip() for item in order_ids if str(item).strip()}
    if "order_id" not in orders.columns:
        return pd.Series(False, index=orders.index)
    return orders["order_id"].astype(str).isin(selected)


def _order_counts(orders: pd.DataFrame) -> dict[str, int]:
    statuses = orders.get("status", pd.Series(dtype=object)).astype(str) if not orders.empty else pd.Series(dtype=object)
    return {
        "count": int(len(orders)),
        "pending_review": int((statuses == "pending_review").sum()),
        "approved": int((statuses == "approved").sum()),
        "executed_simulated": int((statuses == "executed_simulated").sum()),
        "rejected": int((statuses == "rejected").sum()),
        "blocked": int(statuses.str.startswith("blocked").sum()) if not statuses.empty else 0,
    }


def _blocked_control(
    control_id: str,
    pipeline_id: str,
    run_id: str,
    account: dict[str, object],
    status: str,
    reason: str,
) -> dict[str, object]:
    return {
        "control_id": control_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "pipeline_id": pipeline_id,
        "run_id": run_id,
        "account_id": account["account_id"],
        "status": status,
        "reason": reason,
        "risk_gate": {"status": "fail", "passed": 0, "failed": 1, "checks": [_check(status, False, reason)]},
        "orders": {"count": 0, "pending_review": 0, "approved": 0, "executed_simulated": 0, "blocked": 0},
        "trades": {"count": 0},
        "account_before": account,
        "account_after": account,
    }


def load_paper_dashboard(reports_root: str | Path) -> dict[str, object]:
    paper_root = Path(reports_root) / PAPER_DIR
    return {
        "account": _read_json(paper_root / ACCOUNT_STATE) if (paper_root / ACCOUNT_STATE).exists() else {},
        "latest_control": _read_json(paper_root / LATEST_CONTROL_JSON) if (paper_root / LATEST_CONTROL_JSON).exists() else {},
        "risk_gate": _read_json(paper_root / RISK_GATE_JSON) if (paper_root / RISK_GATE_JSON).exists() else {},
        "positions": _read_csv(paper_root / POSITIONS_CSV),
        "latest_orders": _read_csv(paper_root / LATEST_ORDERS_CSV),
        "trades": _read_csv(paper_root / TRADES_CSV),
        "equity_curve": _read_csv(paper_root / EQUITY_CURVE_CSV),
        "ledger": _read_csv(paper_root / ACCOUNT_LEDGER),
        "alerts": _read_csv(paper_root / ALERTS_CSV),
        "audit_log": _read_csv(paper_root / AUDIT_CSV),
    }


def _append_ledger(paper_root: Path, control: dict[str, object], account: dict[str, object]) -> None:
    row = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "control_id": control.get("control_id", ""),
        "pipeline_id": control.get("pipeline_id", ""),
        "run_id": control.get("run_id", ""),
        "status": control.get("status", ""),
        "cash": account.get("cash", 0.0),
        "market_value": account.get("market_value", 0.0),
        "equity": account.get("equity", 0.0),
        "high_watermark": account.get("high_watermark", 0.0),
        "max_drawdown": account.get("max_drawdown", 0.0),
        "orders": _nested(control, "orders", "count"),
        "trades": _nested(control, "trades", "count"),
    }
    _append_csv(pd.DataFrame([row]), paper_root / ACCOUNT_LEDGER)
    _append_csv(pd.DataFrame([row]), paper_root / EQUITY_CURVE_CSV)


def _registry_row(registry: pd.DataFrame, run_id: str) -> dict[str, object] | None:
    if registry.empty or "run_id" not in registry.columns:
        return None
    frame = registry[registry["run_id"].astype(str).eq(run_id)]
    if frame.empty:
        return None
    return {str(key): _json_ready(value) for key, value in frame.iloc[0].to_dict().items()}


def _candidate_from_summary(summary: dict[str, object], run_id: str) -> dict[str, object]:
    candidates = summary.get("paper_candidates")
    if isinstance(candidates, list):
        for item in candidates:
            if isinstance(item, dict) and str(item.get("run_id", "")) == run_id:
                return item
    return {"run_id": run_id}


def _source_blocks(source_orders: pd.DataFrame) -> dict[tuple[str, str], str]:
    blocks: dict[tuple[str, str], str] = {}
    if source_orders.empty:
        return blocks
    for _, row in source_orders.iterrows():
        status = str(row.get("status", ""))
        if status != "blocked":
            continue
        blocks[(str(row.get("symbol", "")), str(row.get("side", "")))] = str(row.get("note", "") or "source_blocked")
    return blocks


def _apply_cash_limit(orders: pd.DataFrame, cash: float) -> pd.DataFrame:
    output = orders.copy()
    available_cash = cash + output[(output["side"] == "sell") & (~output["source_blocked"])]["cash_delta"].sum()
    for index, row in output[output["side"] == "buy"].iterrows():
        required = abs(float(row["cash_delta"]))
        if bool(row["source_blocked"]):
            output.loc[index, "status"] = "blocked_by_execution"
            output.loc[index, "source_note"] = output.loc[index, "source_note"] or "source_blocked"
            continue
        if required > available_cash:
            output.loc[index, "status"] = "blocked_insufficient_cash"
            output.loc[index, "source_blocked"] = True
            output.loc[index, "source_note"] = "insufficient_cash"
        else:
            available_cash -= required
    return output


def _turnover(orders: pd.DataFrame, equity: float) -> float:
    if orders.empty or equity <= 0:
        return 0.0
    tradable = orders[~orders.get("source_blocked", pd.Series(False, index=orders.index)).fillna(False).astype(bool)]
    return float(tradable["gross"].abs().sum() / equity) if not tradable.empty else 0.0


def _account_drawdown(account: dict[str, object]) -> float:
    equity = _float(account.get("equity"), 0.0)
    high = _float(account.get("high_watermark"), equity)
    return equity / high - 1 if high else 0.0


def _position_map(positions: pd.DataFrame) -> dict[str, dict[str, object]]:
    if positions.empty:
        return {}
    rows = {}
    for _, row in positions.iterrows():
        rows[str(row.get("symbol", ""))] = {
            "symbol": str(row.get("symbol", "")),
            "shares": int(float(row.get("shares", 0) or 0)),
            "last_price": _float(row.get("last_price", row.get("price", 0.0)), 0.0),
        }
    return rows


def _price_map(target_holdings: pd.DataFrame) -> dict[str, float]:
    if target_holdings.empty:
        return {}
    return {str(row["symbol"]): _float(row.get("price"), 0.0) for _, row in target_holdings.iterrows()}


def _load_positions(paper_root: Path) -> pd.DataFrame:
    return _read_csv(paper_root / POSITIONS_CSV)


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _read_json(path: Path) -> object:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output = frame.copy()
    for column in output.columns:
        if pd.api.types.is_datetime64_any_dtype(output[column]):
            output[column] = output[column].dt.strftime("%Y-%m-%d")
    output.to_csv(path, index=False)


def _append_csv(frame: pd.DataFrame, path: Path) -> None:
    if frame.empty:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    output = frame.copy()
    if path.exists():
        existing = _read_csv(path)
        output = pd.concat([existing, output], ignore_index=True)
    _write_csv(output, path)


def _append_jsonl(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_json_ready(payload), ensure_ascii=False, sort_keys=True) + "\n")


def _check(name: str, passed: bool, detail: str) -> dict[str, object]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def _nested(container: dict[str, object], *keys: str) -> object:
    current: object = container
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _round_lot(shares: int) -> int:
    return max(0, shares // 100 * 100)


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _symbol_set(value: object) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    text = str(value).replace(";", ",").replace(" ", ",")
    return {item.strip() for item in text.split(",") if item.strip()}


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
