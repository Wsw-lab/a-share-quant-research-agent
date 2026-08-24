from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

import pandas as pd

from .spec import RiskOverlaySpec, StrategySpec


@dataclass
class BacktestResult:
    spec: StrategySpec
    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    holdings: pd.DataFrame
    metrics: dict[str, float]
    orders: pd.DataFrame = field(default_factory=pd.DataFrame)


@dataclass
class _WindowFuseState:
    active: bool = False
    active_days: int = 0
    reentry_remaining: int = 0
    reentry_days_elapsed: int = 0
    cooldown_remaining: int = 0
    trough_drawdown: float = 0.0
    reentry_started_window_drawdown: float = 0.0
    reentry_started_rolling_return: float = 0.0
    consecutive_loss_days: int = 0
    recovery_confirmation_days: int = 0
    volatility_calm_days: int = 0
    rolling_returns: list[float] = field(default_factory=list)
    rolling_navs: list[float] = field(default_factory=list)
    latest_drawdown: float = 0.0
    latest_window_drawdown: float = 0.0
    latest_rolling_return: float = 0.0
    latest_reentry_target_weight: float = 0.0
    latest_downtrend_fuse_trend: float = 1.0
    latest_downtrend_fuse_recovery: float = 0.0
    force_rebalance: bool = False


@dataclass(frozen=True)
class _PendingRebalance:
    signal_date: pd.Timestamp
    targets: tuple[str, ...]
    risk_target_weight: float


@dataclass(frozen=True)
class _PendingStop:
    signal_date: pd.Timestamp
    symbol: str
    position_return: float


def run_backtest(data: pd.DataFrame, spec: StrategySpec) -> BacktestResult:
    if spec.execution.model == "close_signal_next_open":
        return _run_close_signal_next_open(_prepare_data(data, required_price_field="open"), spec)
    if spec.execution.model == "same_close_legacy":
        return _run_same_close_legacy(_prepare_data(data), spec)
    raise ValueError(f"Unsupported execution model: {spec.execution.model}")


def _run_close_signal_next_open(data: pd.DataFrame, spec: StrategySpec) -> BacktestResult:
    """Create orders after a completed close and fill them at the next open."""

    dates = list(data.index.get_level_values("date").unique())
    rebalance_dates = set(_get_rebalance_dates(dates, spec.rebalance.frequency))

    cash = spec.portfolio.initial_cash
    positions: dict[str, int] = {}
    buy_dates: dict[str, pd.Timestamp] = {}
    entry_prices: dict[str, float] = {}
    stopped_until: dict[str, pd.Timestamp] = {}
    trade_rows: list[dict[str, Any]] = []
    order_rows: list[dict[str, Any]] = []
    holding_rows: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []
    peak_nav = spec.portfolio.initial_cash
    previous_nav: float | None = None
    cumulative_cash_yield = 0.0
    fuse_state = _WindowFuseState()
    pending_rebalance: _PendingRebalance | None = None
    pending_stops: dict[str, _PendingStop] = {}

    for date in dates:
        today = data.xs(date, level="date")
        cash_yield_accrued = 0.0
        if previous_nav is not None:
            cash_yield_accrued = _cash_yield_for_day(cash, spec)
            cash += cash_yield_accrued
            cumulative_cash_yield += cash_yield_accrued

        pending_stops, cash, positions = _execute_pending_stops(
            date=date,
            today=today,
            pending_stops=pending_stops,
            cash=cash,
            positions=positions,
            buy_dates=buy_dates,
            entry_prices=entry_prices,
            stopped_until=stopped_until,
            spec=spec,
            trade_rows=trade_rows,
            order_rows=order_rows,
        )
        if pending_rebalance is not None:
            open_nav = _portfolio_value(cash, positions, today, price_field="open")
            cash, positions = _rebalance(
                date=date,
                today=today,
                cash=cash,
                positions=positions,
                buy_dates=buy_dates,
                entry_prices=entry_prices,
                targets=list(pending_rebalance.targets),
                nav=open_nav,
                risk_target_weight=pending_rebalance.risk_target_weight,
                spec=spec,
                trade_rows=trade_rows,
                order_rows=order_rows,
                price_field="open",
                signal_date=pending_rebalance.signal_date,
                execution_model="close_signal_next_open",
            )
            pending_rebalance = None

        nav = _portfolio_value(cash, positions, today)
        peak_nav = max(peak_nav, nav)
        daily_return = 0.0 if previous_nav is None or previous_nav <= 0 else nav / previous_nav - 1.0
        _update_window_fuse_state(
            today,
            spec.risk.risk_overlay,
            fuse_state,
            nav=nav,
            peak_nav=peak_nav,
            daily_return=daily_return,
        )
        risk_target_weight = _risk_target_weight(today, spec, nav=nav, peak_nav=peak_nav, fuse_state=fuse_state)
        alpha_health_filter_weight = _alpha_health_filter_target_weight(today, spec.risk.risk_overlay)

        for stop in _position_stop_signals(
            date=date,
            today=today,
            positions=positions,
            entry_prices=entry_prices,
            spec=spec,
        ):
            pending_stops.setdefault(stop.symbol, stop)

        is_scheduled_rebalance = date in rebalance_dates
        pre_rebalance_gross = max(nav - cash, 0.0) / nav if nav else 0.0
        if (
            is_scheduled_rebalance
            or _should_window_fuse_rebalance(
                spec.risk.risk_overlay,
                fuse_state,
                pre_rebalance_gross,
                risk_target_weight,
                positions,
            )
            or _should_overheated_guard_rebalance(
                today,
                spec.risk.risk_overlay,
                pre_rebalance_gross,
                risk_target_weight,
                positions,
            )
        ):
            selected = (
                _select_symbols(today, spec, stopped_until=stopped_until, date=date)
                if is_scheduled_rebalance
                else list(positions)
            )
            pending_rebalance = _PendingRebalance(
                signal_date=date,
                targets=tuple(symbol for symbol in selected if symbol not in pending_stops),
                risk_target_weight=risk_target_weight,
            )

        invested_value = max(nav - cash, 0.0)
        equity_rows.append(
            {
                "date": date,
                "equity": nav,
                "cash": cash,
                "cash_yield_accrued": cash_yield_accrued,
                "cumulative_cash_yield": cumulative_cash_yield,
                "gross_exposure": invested_value / nav if nav else 0.0,
                "risk_target_weight": risk_target_weight,
                "alpha_health_filter_weight": alpha_health_filter_weight,
                "alpha_health_score": _alpha_health_signal(today, spec.risk.risk_overlay),
                "market_breadth_score": _market_breadth_signal(today, spec.risk.risk_overlay),
                "overheated_reversal_guard_active": float(
                    _overheated_reversal_guard_active(today, spec.risk.risk_overlay)
                ),
                "window_fuse_active": float(fuse_state.active),
                "window_reentry_active": float(fuse_state.reentry_remaining > 0),
                "window_reentry_target_weight": fuse_state.latest_reentry_target_weight,
                "window_fuse_cooldown_remaining": float(fuse_state.cooldown_remaining),
                "window_fuse_drawdown": fuse_state.latest_drawdown,
                "window_fuse_rolling_return": fuse_state.latest_rolling_return,
                "window_fuse_consecutive_loss_days": float(fuse_state.consecutive_loss_days),
            }
        )
        for symbol, shares in positions.items():
            if shares <= 0 or symbol not in today.index:
                continue
            price = float(today.loc[symbol, "close"])
            holding_rows.append(
                {
                    "date": date,
                    "symbol": symbol,
                    "shares": shares,
                    "price": price,
                    "market_value": shares * price,
                    "weight": shares * price / nav if nav else 0.0,
                    "risk_target_weight": risk_target_weight,
                    "window_fuse_active": float(fuse_state.active),
                    "window_reentry_active": float(fuse_state.reentry_remaining > 0),
                    "window_reentry_target_weight": fuse_state.latest_reentry_target_weight,
                }
            )
        previous_nav = nav

    unfilled_final_signal_count = float(pending_rebalance is not None) + float(len(pending_stops))
    if pending_rebalance is not None:
        targets = pending_rebalance.targets or ("",)
        for symbol in targets:
            _append_order(
                order_rows,
                date=pd.NaT,
                signal_date=pending_rebalance.signal_date,
                symbol=symbol,
                side="rebalance",
                requested_shares=0,
                status="unfilled_no_next_session",
                price_field="open",
                execution_model="close_signal_next_open",
            )
    for stop in pending_stops.values():
        _append_order(
            order_rows,
            date=pd.NaT,
            signal_date=stop.signal_date,
            symbol=stop.symbol,
            side="sell",
            requested_shares=positions.get(stop.symbol, 0),
            status="unfilled_no_next_session",
            price_field="open",
            execution_model="close_signal_next_open",
            note=f"position_stop_loss:{stop.position_return:.4f}",
        )

    equity_curve = pd.DataFrame(equity_rows)
    trades = pd.DataFrame(trade_rows)
    holdings = pd.DataFrame(holding_rows)
    orders = _orders_frame(order_rows)
    metrics = _calculate_metrics(equity_curve, trades, spec.portfolio.initial_cash)
    metrics["unfilled_final_signal_count"] = unfilled_final_signal_count
    return BacktestResult(
        spec=spec,
        equity_curve=equity_curve,
        trades=trades,
        holdings=holdings,
        metrics=metrics,
        orders=orders,
    )


def _run_same_close_legacy(data: pd.DataFrame, spec: StrategySpec) -> BacktestResult:
    dates = list(data.index.get_level_values("date").unique())
    rebalance_dates = set(_get_rebalance_dates(dates, spec.rebalance.frequency))

    cash = spec.portfolio.initial_cash
    positions: dict[str, int] = {}
    buy_dates: dict[str, pd.Timestamp] = {}
    entry_prices: dict[str, float] = {}
    stopped_until: dict[str, pd.Timestamp] = {}
    trade_rows: list[dict[str, Any]] = []
    holding_rows: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []
    peak_nav = spec.portfolio.initial_cash
    previous_nav: float | None = None
    cumulative_cash_yield = 0.0
    fuse_state = _WindowFuseState()

    for date in dates:
        today = data.xs(date, level="date")
        cash_yield_accrued = 0.0
        if previous_nav is not None:
            cash_yield_accrued = _cash_yield_for_day(cash, spec)
            cash += cash_yield_accrued
            cumulative_cash_yield += cash_yield_accrued
        cash, positions = _apply_position_stops(
            date=date,
            today=today,
            cash=cash,
            positions=positions,
            buy_dates=buy_dates,
            entry_prices=entry_prices,
            stopped_until=stopped_until,
            spec=spec,
            trade_rows=trade_rows,
        )
        nav = _portfolio_value(cash, positions, today)
        peak_nav = max(peak_nav, nav)
        daily_return = 0.0 if previous_nav is None or previous_nav <= 0 else nav / previous_nav - 1.0
        _update_window_fuse_state(today, spec.risk.risk_overlay, fuse_state, nav=nav, peak_nav=peak_nav, daily_return=daily_return)
        risk_target_weight = _risk_target_weight(today, spec, nav=nav, peak_nav=peak_nav, fuse_state=fuse_state)
        alpha_health_filter_weight = _alpha_health_filter_target_weight(today, spec.risk.risk_overlay)

        is_scheduled_rebalance = date in rebalance_dates
        pre_rebalance_gross = max(nav - cash, 0.0) / nav if nav else 0.0
        if (
            is_scheduled_rebalance
            or _should_window_fuse_rebalance(spec.risk.risk_overlay, fuse_state, pre_rebalance_gross, risk_target_weight, positions)
            or _should_overheated_guard_rebalance(today, spec.risk.risk_overlay, pre_rebalance_gross, risk_target_weight, positions)
        ):
            selected = _select_symbols(today, spec, stopped_until=stopped_until, date=date) if is_scheduled_rebalance else list(positions)
            cash, positions = _rebalance(
                date=date,
                today=today,
                cash=cash,
                positions=positions,
                buy_dates=buy_dates,
                entry_prices=entry_prices,
                targets=selected,
                nav=nav,
                risk_target_weight=risk_target_weight,
                spec=spec,
                trade_rows=trade_rows,
            )

        nav = _portfolio_value(cash, positions, today)
        peak_nav = max(peak_nav, nav)
        invested_value = max(nav - cash, 0.0)
        equity_rows.append(
            {
                "date": date,
                "equity": nav,
                "cash": cash,
                "cash_yield_accrued": cash_yield_accrued,
                "cumulative_cash_yield": cumulative_cash_yield,
                "gross_exposure": invested_value / nav if nav else 0.0,
                "risk_target_weight": risk_target_weight,
                "alpha_health_filter_weight": alpha_health_filter_weight,
                "alpha_health_score": _alpha_health_signal(today, spec.risk.risk_overlay),
                "market_breadth_score": _market_breadth_signal(today, spec.risk.risk_overlay),
                "overheated_reversal_guard_active": float(_overheated_reversal_guard_active(today, spec.risk.risk_overlay)),
                "window_fuse_active": float(fuse_state.active),
                "window_reentry_active": float(fuse_state.reentry_remaining > 0),
                "window_reentry_target_weight": fuse_state.latest_reentry_target_weight,
                "window_fuse_cooldown_remaining": float(fuse_state.cooldown_remaining),
                "window_fuse_drawdown": fuse_state.latest_drawdown,
                "window_fuse_rolling_return": fuse_state.latest_rolling_return,
                "window_fuse_consecutive_loss_days": float(fuse_state.consecutive_loss_days),
            }
        )
        for symbol, shares in positions.items():
            if shares <= 0 or symbol not in today.index:
                continue
            price = float(today.loc[symbol, "close"])
            holding_rows.append(
                {
                    "date": date,
                    "symbol": symbol,
                    "shares": shares,
                    "price": price,
                    "market_value": shares * price,
                    "weight": shares * price / nav if nav else 0.0,
                    "risk_target_weight": risk_target_weight,
                    "window_fuse_active": float(fuse_state.active),
                    "window_reentry_active": float(fuse_state.reentry_remaining > 0),
                    "window_reentry_target_weight": fuse_state.latest_reentry_target_weight,
                }
            )
        previous_nav = nav

    equity_curve = pd.DataFrame(equity_rows)
    trades = pd.DataFrame(trade_rows)
    holdings = pd.DataFrame(holding_rows)
    metrics = _calculate_metrics(equity_curve, trades, spec.portfolio.initial_cash)
    metrics["unfilled_final_signal_count"] = 0.0
    return BacktestResult(spec=spec, equity_curve=equity_curve, trades=trades, holdings=holdings, metrics=metrics)


def _prepare_data(data: pd.DataFrame, *, required_price_field: str = "close") -> pd.DataFrame:
    required = {
        "date",
        "symbol",
        "close",
        "amount",
        "is_st",
        "is_suspended",
        "limit_up",
        "limit_down",
    }
    required.add(required_price_field)
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"Missing required data columns: {sorted(missing)}")

    if isinstance(data.index, pd.MultiIndex) and list(data.index.names) == ["date", "symbol"]:
        return data

    prepared = data.copy()
    prepared["date"] = pd.to_datetime(prepared["date"])
    prepared.sort_values(["date", "symbol"], inplace=True)
    return prepared.set_index(["date", "symbol"], drop=False)


def _get_rebalance_dates(dates: list[pd.Timestamp], frequency: str) -> list[pd.Timestamp]:
    date_index = pd.DatetimeIndex(dates)
    if frequency == "monthly":
        grouped = pd.Series(date_index, index=date_index).groupby(date_index.to_period("M"))
        return [group.iloc[0] for _, group in grouped]
    if frequency == "weekly":
        grouped = pd.Series(date_index, index=date_index).groupby(date_index.to_period("W"))
        return [group.iloc[0] for _, group in grouped]
    raise ValueError(f"Unsupported rebalance frequency: {frequency}")


def _select_symbols(
    today: pd.DataFrame,
    spec: StrategySpec,
    *,
    stopped_until: dict[str, pd.Timestamp] | None = None,
    date: pd.Timestamp | None = None,
) -> list[str]:
    candidates = today.copy()
    if "is_universe_member" in candidates:
        candidates = candidates[candidates["is_universe_member"].fillna(False).astype(bool)]
    if bool(getattr(spec.universe, "use_index_membership", False)):
        member_column = _index_member_column(candidates, str(getattr(spec.universe, "index_code", "") or ""))
        candidates = candidates[candidates[member_column].fillna(False).astype(bool)]
    if "is_stock_master_member" in candidates:
        candidates = candidates[candidates["is_stock_master_member"].fillna(False).astype(bool)]
    if spec.universe.exclude_st:
        candidates = candidates[~candidates["is_st"]]
    if spec.universe.exclude_suspended:
        candidates = candidates[~candidates["is_suspended"]]
    if spec.universe.min_amount > 0:
        candidates = candidates[candidates["amount"] >= spec.universe.min_amount]
    if stopped_until and date is not None and not candidates.empty:
        blocked = {symbol for symbol, until in stopped_until.items() if pd.Timestamp(until) >= date}
        if blocked:
            candidates = candidates[~candidates.index.astype(str).isin(blocked)]

    scores = pd.Series(0.0, index=candidates.index)
    for factor in spec.factors:
        if factor.field not in candidates:
            raise ValueError(f"Factor field not found in data: {factor.field}")
        values = candidates[factor.field].replace([float("inf"), float("-inf")], pd.NA).dropna()
        if values.empty:
            continue
        if factor.direction == "desc":
            ranks = values.rank(pct=True)
        elif factor.direction == "asc":
            ranks = values.rank(pct=True, ascending=False)
        else:
            raise ValueError(f"Unsupported factor direction: {factor.direction}")
        scores.loc[ranks.index] += ranks * factor.weight

    ranked = scores.dropna().sort_values(ascending=False)
    ranked = _apply_selection_bucket_cap(ranked, candidates, spec)
    ranked = _apply_selection_group_cap(ranked, candidates, spec)
    selected = ranked.head(spec.portfolio.max_positions)
    return list(selected.index)


def _index_member_column(candidates: pd.DataFrame, index_code: str) -> str:
    normalized_code = index_code.strip().upper()
    if normalized_code:
        specific = f"is_index_member_{_index_code_suffix(normalized_code)}"
        if specific in candidates:
            return specific
    if "is_index_member" in candidates:
        return "is_index_member"
    requested = normalized_code or "default"
    raise ValueError(f"Universe requested index membership for {requested}, but no PIT index membership field was found.")


def _index_code_suffix(index_code: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in index_code).strip("_")


def _apply_selection_bucket_cap(scores: pd.Series, candidates: pd.DataFrame, spec: StrategySpec) -> pd.Series:
    field = str(getattr(spec.portfolio, "selection_bucket_field", "") or "")
    max_share = float(getattr(spec.portfolio, "max_selection_bucket_share", 1.0) or 1.0)
    if not field or field not in candidates or max_share >= 1.0 or scores.empty:
        return scores
    max_positions = max(1, int(spec.portfolio.max_positions))
    bucket_limit = max(1, int(math.floor(max_positions * max_share)))
    buckets = _selection_buckets(candidates.loc[scores.index, field], int(getattr(spec.portfolio, "selection_bucket_count", 5) or 5))
    selected: list[str] = []
    deferred: list[str] = []
    bucket_counts: dict[object, int] = {}
    for symbol in scores.index:
        bucket = buckets.get(symbol)
        count = bucket_counts.get(bucket, 0)
        if count < bucket_limit:
            selected.append(symbol)
            bucket_counts[bucket] = count + 1
        else:
            deferred.append(symbol)
        if len(selected) >= max_positions:
            break
    if len(selected) < max_positions:
        for symbol in deferred:
            if symbol not in selected:
                selected.append(symbol)
            if len(selected) >= max_positions:
                break
    return scores.loc[selected]


def _apply_selection_group_cap(scores: pd.Series, candidates: pd.DataFrame, spec: StrategySpec) -> pd.Series:
    field = str(getattr(spec.portfolio, "selection_group_field", "") or "")
    max_share = float(getattr(spec.portfolio, "max_selection_group_share", 1.0) or 1.0)
    if not field or field not in candidates or max_share >= 1.0 or scores.empty:
        return scores
    max_positions = max(1, int(spec.portfolio.max_positions))
    group_limit = max(1, int(math.floor(max_positions * max_share)))
    groups = candidates.loc[scores.index, field].fillna("Unknown").replace("", "Unknown").astype(str)
    selected: list[str] = []
    deferred: list[str] = []
    group_counts: dict[str, int] = {}
    for symbol in scores.index:
        group = str(groups.get(symbol, "Unknown") or "Unknown")
        count = group_counts.get(group, 0)
        if count < group_limit:
            selected.append(symbol)
            group_counts[group] = count + 1
        else:
            deferred.append(symbol)
        if len(selected) >= max_positions:
            break
    if len(selected) < max_positions:
        for symbol in deferred:
            if symbol not in selected:
                selected.append(symbol)
            if len(selected) >= max_positions:
                break
    return scores.loc[selected]


def _selection_buckets(values: pd.Series, bucket_count: int) -> pd.Series:
    if values.empty:
        return pd.Series(index=values.index, dtype=object)
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.notna().sum() >= max(2, bucket_count):
        ranks = numeric.rank(method="first", pct=True)
        buckets = (ranks * max(1, bucket_count)).apply(math.ceil).clip(lower=1, upper=max(1, bucket_count))
        return buckets.astype("Int64")
    return values.fillna("missing").astype(str)


def _rebalance(
    date: pd.Timestamp,
    today: pd.DataFrame,
    cash: float,
    positions: dict[str, int],
    buy_dates: dict[str, pd.Timestamp],
    entry_prices: dict[str, float],
    targets: list[str],
    nav: float,
    risk_target_weight: float,
    spec: StrategySpec,
    trade_rows: list[dict[str, Any]],
    order_rows: list[dict[str, Any]] | None = None,
    *,
    price_field: str = "close",
    signal_date: pd.Timestamp | None = None,
    execution_model: str = "same_close_legacy",
) -> tuple[float, dict[str, int]]:
    target_set = set(targets)
    target_gross_weight = _clamp(risk_target_weight, 0.0, 1.0)
    max_position_value = nav * target_gross_weight * min(
        1.0 / max(1, spec.portfolio.max_positions),
        spec.risk.max_single_position_weight,
    )

    # First reduce or exit positions that are not wanted anymore.
    for symbol in list(positions):
        shares = positions[symbol]
        if shares <= 0 or symbol not in today.index:
            continue
        current_value = shares * float(today.loc[symbol, price_field])
        target_value = max_position_value if symbol in target_set else 0.0
        if current_value <= target_value:
            continue
        sell_value = current_value - target_value
        sell_shares = min(shares, _round_lot(int(sell_value / float(today.loc[symbol, price_field]))))
        cash, positions[symbol] = _sell(
            date=date,
            symbol=symbol,
            shares=sell_shares,
            cash=cash,
            held_shares=shares,
            buy_dates=buy_dates,
            today=today,
            spec=spec,
            trade_rows=trade_rows,
            order_rows=order_rows,
            price_field=price_field,
            signal_date=signal_date,
            execution_model=execution_model,
        )
        if positions.get(symbol, 0) <= 0:
            positions.pop(symbol, None)
            entry_prices.pop(symbol, None)

    # Then buy up to target weights with remaining cash.
    for symbol in targets:
        if symbol not in today.index:
            continue
        price = float(today.loc[symbol, price_field])
        current_shares = positions.get(symbol, 0)
        current_value = current_shares * price
        buy_value = max_position_value - current_value
        if buy_value <= price * 100:
            continue
        buy_price = _buy_price(price, spec)
        shares = _round_lot(int(buy_value / buy_price))
        if shares <= 0:
            continue
        max_affordable = _round_lot(int(cash / buy_price))
        shares = min(shares, max_affordable)
        if shares <= 0:
            continue
        buy_price = _buy_price(price, spec)
        cash, new_shares = _buy(
            date,
            symbol,
            shares,
            cash,
            current_shares,
            today,
            spec,
            trade_rows,
            order_rows=order_rows,
            price_field=price_field,
            signal_date=signal_date,
            execution_model=execution_model,
        )
        if new_shares > current_shares:
            prior_value = current_shares * float(entry_prices.get(symbol, buy_price))
            added_shares = new_shares - current_shares
            entry_prices[symbol] = (prior_value + added_shares * buy_price) / max(1, new_shares)
        positions[symbol] = new_shares
        buy_dates[symbol] = date

    return cash, positions


def _position_stop_signals(
    *,
    date: pd.Timestamp,
    today: pd.DataFrame,
    positions: dict[str, int],
    entry_prices: dict[str, float],
    spec: StrategySpec,
) -> list[_PendingStop]:
    stop_limit = float(getattr(spec.risk, "position_stop_loss_limit", 0.0) or 0.0)
    if stop_limit >= 0.0 or not positions:
        return []
    signals: list[_PendingStop] = []
    for symbol, shares in positions.items():
        if shares <= 0 or symbol not in today.index:
            continue
        entry_price = float(entry_prices.get(symbol, 0.0) or 0.0)
        close = float(today.loc[symbol, "close"])
        if entry_price <= 0.0 or not math.isfinite(close) or close <= 0.0:
            continue
        position_return = close / entry_price - 1.0
        if position_return <= stop_limit:
            signals.append(_PendingStop(signal_date=date, symbol=symbol, position_return=position_return))
    return signals


def _execute_pending_stops(
    *,
    date: pd.Timestamp,
    today: pd.DataFrame,
    pending_stops: dict[str, _PendingStop],
    cash: float,
    positions: dict[str, int],
    buy_dates: dict[str, pd.Timestamp],
    entry_prices: dict[str, float],
    stopped_until: dict[str, pd.Timestamp],
    spec: StrategySpec,
    trade_rows: list[dict[str, Any]],
    order_rows: list[dict[str, Any]],
) -> tuple[dict[str, _PendingStop], float, dict[str, int]]:
    remaining_stops: dict[str, _PendingStop] = {}
    cooldown_days = max(0, int(getattr(spec.risk, "position_stop_cooldown_days", 0) or 0))
    for symbol, stop in pending_stops.items():
        shares = positions.get(symbol, 0)
        if shares <= 0:
            continue
        if symbol not in today.index:
            remaining_stops[symbol] = stop
            continue
        cash, remaining = _sell(
            date=date,
            symbol=symbol,
            shares=shares,
            cash=cash,
            held_shares=shares,
            buy_dates=buy_dates,
            today=today,
            spec=spec,
            trade_rows=trade_rows,
            note=f"position_stop_loss:{stop.position_return:.4f}",
            order_rows=order_rows,
            price_field="open",
            signal_date=stop.signal_date,
            execution_model="close_signal_next_open",
        )
        if remaining <= 0:
            positions.pop(symbol, None)
            entry_prices.pop(symbol, None)
            if cooldown_days > 0:
                stopped_until[symbol] = date + pd.Timedelta(days=cooldown_days)
        else:
            positions[symbol] = remaining
            remaining_stops[symbol] = stop
    return remaining_stops, cash, positions


def _apply_position_stops(
    *,
    date: pd.Timestamp,
    today: pd.DataFrame,
    cash: float,
    positions: dict[str, int],
    buy_dates: dict[str, pd.Timestamp],
    entry_prices: dict[str, float],
    stopped_until: dict[str, pd.Timestamp],
    spec: StrategySpec,
    trade_rows: list[dict[str, Any]],
) -> tuple[float, dict[str, int]]:
    stop_limit = float(getattr(spec.risk, "position_stop_loss_limit", 0.0) or 0.0)
    if stop_limit >= 0.0 or not positions:
        return cash, positions
    cooldown_days = max(0, int(getattr(spec.risk, "position_stop_cooldown_days", 0) or 0))
    for symbol in list(positions):
        shares = positions.get(symbol, 0)
        if shares <= 0 or symbol not in today.index or buy_dates.get(symbol) == date:
            continue
        entry_price = float(entry_prices.get(symbol, 0.0) or 0.0)
        if entry_price <= 0.0:
            continue
        price = float(today.loc[symbol, "close"])
        if not math.isfinite(price) or price <= 0.0:
            continue
        position_return = price / entry_price - 1.0
        if position_return > stop_limit:
            continue
        cash, remaining = _sell(
            date=date,
            symbol=symbol,
            shares=shares,
            cash=cash,
            held_shares=shares,
            buy_dates=buy_dates,
            today=today,
            spec=spec,
            trade_rows=trade_rows,
            note=f"position_stop_loss:{position_return:.4f}",
        )
        if remaining <= 0:
            positions.pop(symbol, None)
            entry_prices.pop(symbol, None)
            if cooldown_days > 0:
                stopped_until[symbol] = date + pd.Timedelta(days=cooldown_days)
        else:
            positions[symbol] = remaining
    return cash, positions


def _buy(
    date: pd.Timestamp,
    symbol: str,
    shares: int,
    cash: float,
    held_shares: int,
    today: pd.DataFrame,
    spec: StrategySpec,
    trade_rows: list[dict[str, Any]],
    *,
    order_rows: list[dict[str, Any]] | None = None,
    price_field: str = "close",
    signal_date: pd.Timestamp | None = None,
    execution_model: str = "same_close_legacy",
) -> tuple[float, int]:
    row = today.loc[symbol]
    effective_signal_date = signal_date if signal_date is not None else date
    if bool(row["is_suspended"]):
        _append_order(
            order_rows,
            date=date,
            signal_date=effective_signal_date,
            symbol=symbol,
            side="buy",
            requested_shares=shares,
            status="blocked_suspended",
            price_field=price_field,
            execution_model=execution_model,
        )
        return cash, held_shares
    if _is_limit_up(row, price_field=price_field):
        _append_order(
            order_rows,
            date=date,
            signal_date=effective_signal_date,
            symbol=symbol,
            side="buy",
            requested_shares=shares,
            status="blocked_limit_up",
            price_field=price_field,
            execution_model=execution_model,
        )
        return cash, held_shares
    price = _buy_price(float(row[price_field]), spec)
    gross = shares * price
    commission = gross * spec.costs.commission_rate
    total = gross + commission
    if total > cash:
        _append_order(
            order_rows,
            date=date,
            signal_date=effective_signal_date,
            symbol=symbol,
            side="buy",
            requested_shares=shares,
            status="blocked_insufficient_cash",
            price_field=price_field,
            execution_model=execution_model,
        )
        return cash, held_shares
    trade_rows.append(
        {
            "date": date,
            "signal_date": effective_signal_date,
            "symbol": symbol,
            "side": "buy",
            "shares": shares,
            "price": price,
            "gross": gross,
            "commission": commission,
            "stamp_tax": 0.0,
            "cash_delta": -total,
            "execution_model": execution_model,
            "fill_price_field": price_field,
            "note": "",
        }
    )
    _append_order(
        order_rows,
        date=date,
        signal_date=effective_signal_date,
        symbol=symbol,
        side="buy",
        requested_shares=shares,
        status="filled",
        price_field=price_field,
        execution_model=execution_model,
    )
    return cash - total, held_shares + shares


def _sell(
    date: pd.Timestamp,
    symbol: str,
    shares: int,
    cash: float,
    held_shares: int,
    buy_dates: dict[str, pd.Timestamp],
    today: pd.DataFrame,
    spec: StrategySpec,
    trade_rows: list[dict[str, Any]],
    note: str = "",
    *,
    order_rows: list[dict[str, Any]] | None = None,
    price_field: str = "close",
    signal_date: pd.Timestamp | None = None,
    execution_model: str = "same_close_legacy",
) -> tuple[float, int]:
    if shares <= 0:
        return cash, held_shares
    row = today.loc[symbol]
    effective_signal_date = signal_date if signal_date is not None else date
    if buy_dates.get(symbol) == date:
        _append_order(
            order_rows,
            date=date,
            signal_date=effective_signal_date,
            symbol=symbol,
            side="sell",
            requested_shares=shares,
            status="blocked_t_plus_one",
            price_field=price_field,
            execution_model=execution_model,
            note=note,
        )
        return cash, held_shares
    if bool(row["is_suspended"]):
        _append_order(
            order_rows,
            date=date,
            signal_date=effective_signal_date,
            symbol=symbol,
            side="sell",
            requested_shares=shares,
            status="blocked_suspended",
            price_field=price_field,
            execution_model=execution_model,
            note=note,
        )
        return cash, held_shares
    if _is_limit_down(row, price_field=price_field):
        _append_order(
            order_rows,
            date=date,
            signal_date=effective_signal_date,
            symbol=symbol,
            side="sell",
            requested_shares=shares,
            status="blocked_limit_down",
            price_field=price_field,
            execution_model=execution_model,
            note=note,
        )
        return cash, held_shares
    shares = min(shares, held_shares)
    price = _sell_price(float(row[price_field]), spec)
    gross = shares * price
    commission = gross * spec.costs.commission_rate
    stamp_tax = gross * spec.costs.stamp_tax_rate
    proceeds = gross - commission - stamp_tax
    trade_rows.append(
        {
            "date": date,
            "signal_date": effective_signal_date,
            "symbol": symbol,
            "side": "sell",
            "shares": shares,
            "price": price,
            "gross": gross,
            "commission": commission,
            "stamp_tax": stamp_tax,
            "cash_delta": proceeds,
            "execution_model": execution_model,
            "fill_price_field": price_field,
            "note": note,
        }
    )
    _append_order(
        order_rows,
        date=date,
        signal_date=effective_signal_date,
        symbol=symbol,
        side="sell",
        requested_shares=shares,
        status="filled",
        price_field=price_field,
        execution_model=execution_model,
        note=note,
    )
    return cash + proceeds, held_shares - shares


def _portfolio_value(
    cash: float,
    positions: dict[str, int],
    today: pd.DataFrame,
    *,
    price_field: str = "close",
) -> float:
    value = cash
    for symbol, shares in positions.items():
        if symbol in today.index:
            value += shares * float(today.loc[symbol, price_field])
    return value


def _risk_target_weight(
    today: pd.DataFrame,
    spec: StrategySpec,
    *,
    nav: float,
    peak_nav: float,
    fuse_state: _WindowFuseState | None = None,
) -> float:
    overlay = spec.risk.risk_overlay
    if not overlay.enabled:
        return 1.0

    bad_signals = 0
    trend_signal: float | None = None
    if overlay.use_trend:
        trend_signal = _numeric_signal(today, overlay.trend_field)
        if trend_signal <= 0.0:
            bad_signals += 1
    if overlay.use_momentum and _numeric_signal(today, overlay.momentum_field) <= overlay.momentum_threshold:
        bad_signals += 1
    if overlay.use_volatility:
        volatility = _numeric_signal(today, overlay.volatility_field, neutral=0.0)
        threshold = _numeric_signal(today, overlay.volatility_threshold_field, neutral=float("inf"))
        if volatility > threshold:
            bad_signals += 1

    target = float(overlay.risk_on_weight)
    if bad_signals >= max(1, int(overlay.crisis_trigger_count)):
        target = min(target, float(overlay.crisis_weight))
    elif bad_signals >= max(1, int(overlay.risk_off_trigger_count)):
        target = min(target, float(overlay.risk_off_weight))

    drawdown = 0.0 if peak_nav <= 0 else nav / peak_nav - 1.0
    market_recovery = _market_recovery_signal(today, overlay, trend_signal=trend_signal)
    staged_recovery_weight = _staged_recovery_target_weight(
        today,
        overlay,
        trend_signal=trend_signal,
        drawdown=drawdown,
    )
    if market_recovery and bad_signals < max(1, int(overlay.crisis_trigger_count)) and target < float(overlay.risk_on_weight):
        target = max(target, float(overlay.recovery_weight))
    if staged_recovery_weight is not None and bad_signals < max(1, int(overlay.crisis_trigger_count)):
        target = max(target, staged_recovery_weight)
    if _high_vol_uptrend_guard_active(today, overlay):
        target = min(target, float(overlay.high_vol_uptrend_weight))
    if _uptrend_tail_guard_active(today, overlay):
        target = min(target, float(overlay.uptrend_tail_weight))
    if _overheated_reversal_guard_active(today, overlay):
        target = min(target, float(overlay.overheated_guard_weight))

    if overlay.portfolio_drawdown_limit < 0 and peak_nav > 0:
        if drawdown <= overlay.portfolio_drawdown_limit:
            drawdown_weight = float(overlay.drawdown_weight)
            if market_recovery and overlay.recovery_allows_drawdown_lift:
                drawdown_weight = max(drawdown_weight, float(overlay.drawdown_recovery_weight))
            if staged_recovery_weight is not None and overlay.staged_recovery_allows_drawdown_lift:
                drawdown_weight = max(drawdown_weight, staged_recovery_weight)
            target = min(target, drawdown_weight)
    if overlay.use_window_fuse and fuse_state is not None:
        if fuse_state.active:
            target = min(target, float(overlay.fuse_weight))
        elif fuse_state.reentry_remaining > 0:
            target = min(target, _window_fuse_reentry_target_weight(overlay, fuse_state))
    target = min(target, _alpha_health_filter_target_weight(today, overlay))
    return _clamp(target, 0.0, 1.0)


def _alpha_health_filter_target_weight(today: pd.DataFrame, overlay: RiskOverlaySpec) -> float:
    if not overlay.enabled:
        return 1.0
    target = 1.0
    if overlay.use_alpha_health_filter:
        health = _numeric_signal(today, overlay.alpha_health_field, neutral=1.0)
        target = min(
            target,
            _threshold_filter_weight(
                health,
                minimum=float(overlay.alpha_health_min),
                warning=float(overlay.alpha_health_warning),
                off_weight=float(overlay.alpha_health_off_weight),
                weak_weight=float(overlay.alpha_health_weak_weight),
            ),
        )
    if overlay.use_market_breadth_filter:
        breadth = _numeric_signal(today, overlay.market_breadth_field, neutral=1.0)
        target = min(
            target,
            _threshold_filter_weight(
                breadth,
                minimum=float(overlay.market_breadth_min),
                warning=float(overlay.market_breadth_warning),
                off_weight=float(overlay.market_breadth_off_weight),
                weak_weight=float(overlay.market_breadth_weak_weight),
            ),
        )
    return _clamp(target, 0.0, 1.0)


def _threshold_filter_weight(
    value: float,
    *,
    minimum: float,
    warning: float,
    off_weight: float,
    weak_weight: float,
) -> float:
    if value < minimum:
        return _clamp(off_weight, 0.0, 1.0)
    if value < warning:
        return _clamp(weak_weight, 0.0, 1.0)
    return 1.0


def _alpha_health_signal(today: pd.DataFrame, overlay: RiskOverlaySpec) -> float:
    if overlay.enabled and overlay.use_alpha_health_filter:
        return _numeric_signal(today, overlay.alpha_health_field, neutral=1.0)
    return 1.0


def _market_breadth_signal(today: pd.DataFrame, overlay: RiskOverlaySpec) -> float:
    if overlay.enabled and overlay.use_market_breadth_filter:
        return _numeric_signal(today, overlay.market_breadth_field, neutral=1.0)
    return 1.0


def _update_window_fuse_state(
    today: pd.DataFrame,
    overlay: RiskOverlaySpec,
    state: _WindowFuseState,
    *,
    nav: float,
    peak_nav: float,
    daily_return: float,
) -> None:
    state.force_rebalance = False
    if not overlay.enabled or not overlay.use_window_fuse:
        state.active = False
        state.active_days = 0
        state.reentry_remaining = 0
        state.reentry_days_elapsed = 0
        state.cooldown_remaining = 0
        state.recovery_confirmation_days = 0
        state.volatility_calm_days = 0
        state.latest_drawdown = 0.0 if peak_nav <= 0 else nav / peak_nav - 1.0
        state.latest_window_drawdown = 0.0
        state.latest_rolling_return = 0.0
        state.latest_reentry_target_weight = 0.0
        state.latest_downtrend_fuse_trend = 1.0
        state.latest_downtrend_fuse_recovery = 0.0
        return

    clean_return = daily_return if math.isfinite(daily_return) else 0.0
    state.rolling_returns.append(clean_return)
    state.rolling_navs.append(nav)
    rolling_days = max(1, int(overlay.fuse_rolling_days))
    if len(state.rolling_returns) > rolling_days:
        state.rolling_returns = state.rolling_returns[-rolling_days:]
    if len(state.rolling_navs) > rolling_days:
        state.rolling_navs = state.rolling_navs[-rolling_days:]
    state.consecutive_loss_days = state.consecutive_loss_days + 1 if clean_return < 0.0 else 0
    drawdown = 0.0 if peak_nav <= 0 else nav / peak_nav - 1.0
    rolling_peak = max(state.rolling_navs) if state.rolling_navs else nav
    window_drawdown = 0.0 if rolling_peak <= 0 else nav / rolling_peak - 1.0
    rolling_return = _compound_returns(state.rolling_returns)
    state.latest_drawdown = drawdown
    state.latest_window_drawdown = window_drawdown
    state.latest_rolling_return = rolling_return
    if overlay.use_downtrend_loss_cluster_fuse:
        state.latest_downtrend_fuse_trend = _numeric_signal(today, overlay.downtrend_fuse_trend_field, neutral=1.0)
        state.latest_downtrend_fuse_recovery = _numeric_signal(today, overlay.downtrend_fuse_recovery_field, neutral=0.0)
    else:
        state.latest_downtrend_fuse_trend = 1.0
        state.latest_downtrend_fuse_recovery = 0.0
    _update_window_fuse_confirmation_state(today, overlay, state)

    triggered = _window_fuse_triggered(overlay, state)
    if state.active:
        state.active_days += 1
        state.cooldown_remaining = max(0, state.cooldown_remaining - 1)
        state.trough_drawdown = min(state.trough_drawdown, window_drawdown)
        if _window_fuse_can_reenter(today, overlay, state):
            _start_window_reentry(state, overlay)
        return

    if state.reentry_remaining > 0:
        state.reentry_days_elapsed += 1
        state.reentry_remaining = max(0, state.reentry_remaining - 1)
        state.latest_reentry_target_weight = _window_fuse_reentry_target_weight(overlay, state)
        if _window_fuse_reentry_failed(overlay, state):
            _start_window_fuse(state, overlay, window_drawdown=window_drawdown)
        elif state.reentry_remaining <= 0:
            state.reentry_days_elapsed = 0
            state.latest_reentry_target_weight = 0.0
        return

    if triggered:
        _start_window_fuse(state, overlay, window_drawdown=window_drawdown)


def _window_fuse_triggered(overlay: RiskOverlaySpec, state: _WindowFuseState) -> bool:
    if _downtrend_loss_cluster_fuse_triggered(overlay, state):
        return True
    if state.latest_window_drawdown <= float(overlay.fuse_drawdown_limit):
        return True
    rolling_days = max(1, int(overlay.fuse_rolling_days))
    if len(state.rolling_returns) >= rolling_days and state.latest_rolling_return <= float(overlay.fuse_rolling_return_limit):
        return True
    loss_days = max(1, int(overlay.fuse_consecutive_loss_days))
    return state.consecutive_loss_days >= loss_days


def _high_vol_uptrend_guard_active(today: pd.DataFrame, overlay: RiskOverlaySpec) -> bool:
    if not overlay.use_high_vol_uptrend_guard:
        return False
    trend = _numeric_signal(today, overlay.high_vol_uptrend_trend_field, neutral=0.0)
    if trend <= 0.0:
        return False
    volatility = _numeric_signal(today, overlay.high_vol_uptrend_volatility_field, neutral=0.0)
    threshold = _numeric_signal(today, overlay.high_vol_uptrend_threshold_field, neutral=float("inf"))
    if volatility <= threshold:
        return False
    if overlay.high_vol_uptrend_requires_positive_momentum:
        momentum = _numeric_signal(today, overlay.high_vol_uptrend_momentum_field, neutral=float("-inf"))
        return momentum > float(overlay.high_vol_uptrend_momentum_floor)
    return True


def _uptrend_tail_guard_active(today: pd.DataFrame, overlay: RiskOverlaySpec) -> bool:
    if not overlay.use_uptrend_tail_guard:
        return False
    trend = _numeric_signal(today, overlay.uptrend_tail_trend_field, neutral=0.0)
    if trend <= 0.0:
        return False
    momentum = _numeric_signal(today, overlay.uptrend_tail_momentum_field, neutral=0.0)
    return momentum <= float(overlay.uptrend_tail_momentum_floor)


def _overheated_reversal_guard_active(today: pd.DataFrame, overlay: RiskOverlaySpec) -> bool:
    if not overlay.use_overheated_reversal_guard:
        return False
    alpha_health = _numeric_signal(today, overlay.overheated_alpha_health_field, neutral=0.0)
    breadth = _numeric_signal(today, overlay.overheated_breadth_field, neutral=0.0)
    momentum = _numeric_signal(today, overlay.overheated_momentum_field, neutral=1.0)
    return (
        alpha_health >= float(overlay.overheated_alpha_health_min)
        and breadth >= float(overlay.overheated_breadth_min)
        and momentum <= float(overlay.overheated_momentum_max)
    )


def _downtrend_loss_cluster_fuse_triggered(overlay: RiskOverlaySpec, state: _WindowFuseState) -> bool:
    if not overlay.use_downtrend_loss_cluster_fuse:
        return False
    trend_bad = state.latest_downtrend_fuse_trend <= 0.0
    recovery_candidate = state.latest_downtrend_fuse_recovery > 0.0
    if not (trend_bad or (overlay.downtrend_fuse_include_recovery and recovery_candidate)):
        return False
    if state.latest_window_drawdown <= float(overlay.downtrend_fuse_drawdown_limit):
        return True
    rolling_days = max(1, int(overlay.fuse_rolling_days))
    if len(state.rolling_returns) >= rolling_days and state.latest_rolling_return <= float(overlay.downtrend_fuse_rolling_return_limit):
        return True
    loss_days = max(1, int(overlay.downtrend_fuse_consecutive_loss_days))
    return state.consecutive_loss_days >= loss_days


def _window_fuse_can_reenter(today: pd.DataFrame, overlay: RiskOverlaySpec, state: _WindowFuseState) -> bool:
    max_active_days = max(0, int(overlay.fuse_max_active_days))
    max_active_expired = max_active_days > 0 and state.active_days >= max_active_days
    if state.cooldown_remaining > 0 and not max_active_expired:
        return False
    confirmation_days = max(1, int(overlay.fuse_reentry_confirmation_days))
    if (
        overlay.fuse_reentry_requires_market_recovery
        and state.recovery_confirmation_days < confirmation_days
        and not max_active_expired
    ):
        return False
    if (
        overlay.fuse_reentry_requires_volatility_calm
        and state.volatility_calm_days < confirmation_days
        and not max_active_expired
    ):
        return False
    if (
        overlay.fuse_reentry_requires_drawdown_repair
        and state.latest_window_drawdown < state.trough_drawdown + float(overlay.fuse_reentry_drawdown_repair)
        and not max_active_expired
    ):
        return False
    if state.latest_rolling_return < float(overlay.fuse_reentry_rolling_return_floor) and not max_active_expired:
        return False
    return True


def _start_window_fuse(state: _WindowFuseState, overlay: RiskOverlaySpec, *, window_drawdown: float) -> None:
    state.active = True
    state.active_days = 1
    state.reentry_remaining = 0
    state.reentry_days_elapsed = 0
    state.cooldown_remaining = max(0, int(overlay.fuse_cooldown_days))
    state.trough_drawdown = window_drawdown
    state.reentry_started_window_drawdown = 0.0
    state.reentry_started_rolling_return = 0.0
    state.latest_reentry_target_weight = 0.0
    state.force_rebalance = True


def _start_window_reentry(state: _WindowFuseState, overlay: RiskOverlaySpec) -> None:
    state.active = False
    state.active_days = 0
    state.reentry_remaining = max(0, int(overlay.fuse_reentry_days))
    state.reentry_days_elapsed = 0
    state.reentry_started_window_drawdown = state.latest_window_drawdown
    state.reentry_started_rolling_return = state.latest_rolling_return
    state.latest_reentry_target_weight = _window_fuse_reentry_target_weight(overlay, state) if state.reentry_remaining > 0 else 0.0
    state.force_rebalance = True


def _window_fuse_reentry_target_weight(overlay: RiskOverlaySpec, state: _WindowFuseState) -> float:
    cap = _clamp(float(overlay.fuse_reentry_weight), 0.0, 1.0)
    initial = float(overlay.fuse_reentry_initial_weight)
    if initial <= 0.0:
        return cap
    step_weight = max(0.0, float(overlay.fuse_reentry_step_weight))
    if step_weight <= 0.0:
        return _clamp(min(initial, cap), 0.0, 1.0)
    step_days = max(1, int(overlay.fuse_reentry_step_days))
    completed_steps = max(0, int(state.reentry_days_elapsed) // step_days)
    return _clamp(min(cap, initial + completed_steps * step_weight), 0.0, 1.0)


def _window_fuse_reentry_failed(overlay: RiskOverlaySpec, state: _WindowFuseState) -> bool:
    if state.reentry_remaining <= 0:
        return False
    if state.latest_rolling_return <= float(overlay.fuse_reentry_refuse_rolling_return_limit):
        return True
    drawdown_buffer = abs(float(overlay.fuse_reentry_refuse_drawdown_buffer))
    return state.latest_window_drawdown <= state.reentry_started_window_drawdown - drawdown_buffer


def _update_window_fuse_confirmation_state(
    today: pd.DataFrame,
    overlay: RiskOverlaySpec,
    state: _WindowFuseState,
) -> None:
    if overlay.fuse_reentry_requires_market_recovery:
        recovery = _numeric_signal(today, overlay.fuse_reentry_field, neutral=float("-inf"))
        if recovery > float(overlay.fuse_reentry_threshold):
            state.recovery_confirmation_days += 1
        else:
            state.recovery_confirmation_days = 0
    else:
        state.recovery_confirmation_days += 1

    if overlay.fuse_reentry_requires_volatility_calm:
        volatility = _numeric_signal(today, overlay.fuse_reentry_volatility_field, neutral=float("inf"))
        threshold = _numeric_signal(today, overlay.fuse_reentry_volatility_threshold_field, neutral=0.0)
        if volatility <= threshold:
            state.volatility_calm_days += 1
        else:
            state.volatility_calm_days = 0
    else:
        state.volatility_calm_days += 1


def _should_window_fuse_rebalance(
    overlay: RiskOverlaySpec,
    state: _WindowFuseState,
    gross_exposure: float,
    risk_target_weight: float,
    positions: dict[str, int],
) -> bool:
    if not overlay.enabled or not overlay.use_window_fuse or not positions:
        return False
    buffer = max(0.0, float(overlay.fuse_rebalance_buffer))
    if state.force_rebalance:
        return True
    if state.active and gross_exposure > risk_target_weight + buffer:
        return True
    if state.reentry_remaining > 0 and abs(gross_exposure - risk_target_weight) > buffer:
        return True
    return False


def _should_overheated_guard_rebalance(
    today: pd.DataFrame,
    overlay: RiskOverlaySpec,
    gross_exposure: float,
    risk_target_weight: float,
    positions: dict[str, int],
) -> bool:
    if not overlay.enabled or not overlay.use_overheated_reversal_guard or not positions:
        return False
    if not _overheated_reversal_guard_active(today, overlay):
        return False
    buffer = max(0.0, float(overlay.fuse_rebalance_buffer))
    return gross_exposure > risk_target_weight + buffer


def _compound_returns(values: list[float]) -> float:
    if not values:
        return 0.0
    total = 1.0
    for value in values:
        clean = value if math.isfinite(value) else 0.0
        total *= 1.0 + clean
    return float(total - 1.0)


def _market_recovery_signal(today: pd.DataFrame, overlay: RiskOverlaySpec, *, trend_signal: float | None) -> bool:
    if not overlay.use_recovery:
        return False
    if overlay.recovery_requires_trend_bad:
        if overlay.use_trend:
            if trend_signal is None or trend_signal > 0.0:
                return False
        else:
            return False
    recovery = _numeric_signal(today, overlay.recovery_field, neutral=float("-inf"))
    return recovery > overlay.recovery_threshold


def _staged_recovery_target_weight(
    today: pd.DataFrame,
    overlay: RiskOverlaySpec,
    *,
    trend_signal: float | None,
    drawdown: float,
) -> float | None:
    if not overlay.use_staged_recovery:
        return None
    if overlay.staged_recovery_requires_trend_bad:
        if overlay.use_trend:
            if trend_signal is None or trend_signal > 0.0:
                return None
        else:
            return None
    if overlay.staged_recovery_requires_portfolio_drawdown and drawdown > float(overlay.staged_recovery_drawdown_trigger):
        return None
    floor = float(overlay.staged_recovery_drawdown_floor)
    if floor < 0.0 and drawdown <= floor:
        return None

    signal = _numeric_signal(today, overlay.staged_recovery_field, neutral=float("-inf"))
    weight: float | None = None
    if signal > float(overlay.staged_recovery_threshold_1):
        weight = float(overlay.staged_recovery_weight_1)
    if signal > float(overlay.staged_recovery_threshold_2):
        weight = float(overlay.staged_recovery_weight_2)
    if signal > float(overlay.staged_recovery_threshold_3):
        weight = float(overlay.staged_recovery_weight_3)
    return None if weight is None else _clamp(weight, 0.0, 1.0)


def _numeric_signal(today: pd.DataFrame, field: str, *, neutral: float = 1.0) -> float:
    if field not in today:
        raise ValueError(f"Risk overlay field not found in data: {field}")
    values = pd.to_numeric(today[field], errors="coerce").replace([float("inf"), float("-inf")], pd.NA).dropna()
    if values.empty:
        return neutral
    return float(values.iloc[0])


def _buy_price(close: float, spec: StrategySpec) -> float:
    return close * (1 + spec.costs.slippage_bps / 10_000)


def _sell_price(close: float, spec: StrategySpec) -> float:
    return close * (1 - spec.costs.slippage_bps / 10_000)


def _cash_yield_for_day(cash: float, spec: StrategySpec) -> float:
    annualized_yield = float(getattr(spec.portfolio, "cash_yield_annualized", 0.0) or 0.0)
    if annualized_yield <= -1.0:
        raise ValueError("cash_yield_annualized must be greater than -100%.")
    if cash <= 0.0 or annualized_yield == 0.0:
        return 0.0
    daily_rate = (1.0 + annualized_yield) ** (1.0 / 252.0) - 1.0
    return cash * daily_rate


def _is_limit_up(row: pd.Series, *, price_field: str = "close") -> bool:
    explicit = bool(row["is_limit_up"]) if "is_limit_up" in row and pd.notna(row["is_limit_up"]) else False
    return explicit or _price_reaches_limit(row, price_field=price_field, limit_field="limit_up", upper=True)


def _is_limit_down(row: pd.Series, *, price_field: str = "close") -> bool:
    explicit = bool(row["is_limit_down"]) if "is_limit_down" in row and pd.notna(row["is_limit_down"]) else False
    return explicit or _price_reaches_limit(row, price_field=price_field, limit_field="limit_down", upper=False)


def _price_reaches_limit(row: pd.Series, *, price_field: str, limit_field: str, upper: bool) -> bool:
    if price_field not in row or limit_field not in row:
        return False
    price = pd.to_numeric(pd.Series([row[price_field]]), errors="coerce").iloc[0]
    limit = pd.to_numeric(pd.Series([row[limit_field]]), errors="coerce").iloc[0]
    if pd.isna(price) or pd.isna(limit):
        return False
    return bool(float(price) >= float(limit)) if upper else bool(float(price) <= float(limit))


def _append_order(
    order_rows: list[dict[str, Any]] | None,
    *,
    date: pd.Timestamp,
    signal_date: pd.Timestamp,
    symbol: str,
    side: str,
    requested_shares: int,
    status: str,
    price_field: str,
    execution_model: str,
    note: str = "",
) -> None:
    if order_rows is None:
        return
    order_rows.append(
        {
            "date": date,
            "signal_date": signal_date,
            "symbol": symbol,
            "side": side,
            "requested_shares": int(requested_shares),
            "status": status,
            "fill_price_field": price_field,
            "execution_model": execution_model,
            "note": note,
        }
    )


def _orders_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    columns = [
        "date",
        "signal_date",
        "symbol",
        "side",
        "requested_shares",
        "status",
        "fill_price_field",
        "execution_model",
        "note",
    ]
    return pd.DataFrame(rows, columns=columns)


def _round_lot(shares: int) -> int:
    return max(0, shares // 100 * 100)


def _calculate_metrics(equity_curve: pd.DataFrame, trades: pd.DataFrame, initial_cash: float) -> dict[str, float]:
    if equity_curve.empty:
        return {}
    curve = equity_curve.copy()
    curve["daily_return"] = curve["equity"].pct_change().fillna(0.0)
    start_equity = float(initial_cash)
    end_equity = float(curve["equity"].iloc[-1])
    total_return = end_equity / start_equity - 1
    years = max((curve["date"].iloc[-1] - curve["date"].iloc[0]).days / 365.25, 1 / 365.25)
    annualized_return = (1 + total_return) ** (1 / years) - 1
    rolling_peak = curve["equity"].cummax()
    drawdown = curve["equity"] / rolling_peak - 1
    max_drawdown = float(drawdown.min())
    volatility = float(curve["daily_return"].std() * (252**0.5))
    sharpe = annualized_return / volatility if volatility > 0 else 0.0
    trade_count = int(len(trades))
    sell_trades = trades[trades["side"] == "sell"] if not trades.empty else trades
    turnover = float(trades["gross"].sum() / curve["equity"].mean()) if not trades.empty else 0.0
    metrics = {
        "start_equity": start_equity,
        "end_equity": end_equity,
        "total_return": float(total_return),
        "annualized_return": float(annualized_return),
        "max_drawdown": max_drawdown,
        "annualized_volatility": volatility,
        "sharpe": float(sharpe),
        "trade_count": float(trade_count),
        "sell_count": float(len(sell_trades)),
        "turnover": turnover,
    }
    if "gross_exposure" in curve:
        metrics["average_gross_exposure"] = float(pd.to_numeric(curve["gross_exposure"], errors="coerce").fillna(0.0).mean())
        metrics["max_gross_exposure"] = float(pd.to_numeric(curve["gross_exposure"], errors="coerce").fillna(0.0).max())
    if "risk_target_weight" in curve:
        metrics["average_risk_target_weight"] = float(
            pd.to_numeric(curve["risk_target_weight"], errors="coerce").fillna(1.0).mean()
        )
        metrics["min_risk_target_weight"] = float(
            pd.to_numeric(curve["risk_target_weight"], errors="coerce").fillna(1.0).min()
        )
    if "alpha_health_filter_weight" in curve:
        health_weight = pd.to_numeric(curve["alpha_health_filter_weight"], errors="coerce").fillna(1.0)
        metrics["alpha_health_filter_day_share"] = float((health_weight < 1.0).mean())
        metrics["alpha_health_filter_off_day_share"] = float((health_weight <= 0.0).mean())
    if "cash_yield_accrued" in curve:
        total_cash_yield = float(pd.to_numeric(curve["cash_yield_accrued"], errors="coerce").fillna(0.0).sum())
        metrics["total_cash_yield"] = total_cash_yield
        metrics["cash_yield_return_contribution"] = total_cash_yield / initial_cash if initial_cash else 0.0
    if "window_fuse_active" in curve:
        metrics["window_fuse_days"] = float(pd.to_numeric(curve["window_fuse_active"], errors="coerce").fillna(0.0).sum())
        metrics["window_fuse_day_share"] = float(
            pd.to_numeric(curve["window_fuse_active"], errors="coerce").fillna(0.0).mean()
        )
    if "window_reentry_active" in curve:
        metrics["window_reentry_days"] = float(pd.to_numeric(curve["window_reentry_active"], errors="coerce").fillna(0.0).sum())
        metrics["window_reentry_day_share"] = float(
            pd.to_numeric(curve["window_reentry_active"], errors="coerce").fillna(0.0).mean()
        )
    return metrics


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))
