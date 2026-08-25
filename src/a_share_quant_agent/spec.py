from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Literal


Direction = Literal["asc", "desc"]
Frequency = Literal["monthly", "weekly"]
ExecutionModel = Literal["close_signal_next_open", "same_close_legacy"]


@dataclass(frozen=True)
class FactorSpec:
    field: str
    direction: Direction
    weight: float


@dataclass(frozen=True)
class UniverseSpec:
    exclude_st: bool = True
    exclude_suspended: bool = True
    min_amount: float = 0.0
    use_index_membership: bool = False
    index_code: str = ""


@dataclass(frozen=True)
class RebalanceSpec:
    frequency: Frequency = "monthly"


@dataclass(frozen=True)
class PortfolioSpec:
    initial_cash: float = 1_000_000.0
    cash_yield_annualized: float = 0.0
    max_positions: int = 20
    weighting: Literal["equal"] = "equal"
    selection_bucket_field: str = ""
    selection_bucket_count: int = 5
    max_selection_bucket_share: float = 1.0
    selection_group_field: str = ""
    max_selection_group_share: float = 1.0


@dataclass(frozen=True)
class CostSpec:
    commission_rate: float = 0.0003
    stamp_tax_rate: float = 0.0005
    slippage_bps: float = 5.0


@dataclass(frozen=True)
class ExecutionSpec:
    """Set the information cutoff and fill convention for daily bars."""

    model: ExecutionModel = "close_signal_next_open"

    def __post_init__(self) -> None:
        supported = {"close_signal_next_open", "same_close_legacy"}
        if self.model not in supported:
            raise ValueError(f"Unsupported execution model: {self.model}. Expected one of {sorted(supported)}")


@dataclass(frozen=True)
class RiskOverlaySpec:
    enabled: bool = False
    risk_on_weight: float = 1.0
    risk_off_weight: float = 0.50
    crisis_weight: float = 0.25
    risk_off_trigger_count: int = 1
    crisis_trigger_count: int = 2
    use_trend: bool = True
    trend_field: str = "benchmark_trend_200d_lag1"
    use_momentum: bool = True
    momentum_field: str = "benchmark_momentum_60d_lag1"
    momentum_threshold: float = 0.0
    use_volatility: bool = False
    volatility_field: str = "benchmark_volatility_60d_lag1"
    volatility_threshold_field: str = "benchmark_volatility_60d_q80_lag1"
    use_recovery: bool = False
    recovery_field: str = "benchmark_momentum_20d_lag1"
    recovery_threshold: float = 0.0
    recovery_weight: float = 0.70
    recovery_requires_trend_bad: bool = True
    recovery_allows_drawdown_lift: bool = False
    drawdown_recovery_weight: float = 0.45
    use_staged_recovery: bool = False
    staged_recovery_field: str = "benchmark_momentum_20d_lag1"
    staged_recovery_threshold_1: float = 0.0
    staged_recovery_threshold_2: float = 0.03
    staged_recovery_threshold_3: float = 0.06
    staged_recovery_weight_1: float = 0.55
    staged_recovery_weight_2: float = 0.70
    staged_recovery_weight_3: float = 0.85
    staged_recovery_requires_trend_bad: bool = True
    staged_recovery_requires_portfolio_drawdown: bool = False
    staged_recovery_drawdown_trigger: float = 0.0
    staged_recovery_drawdown_floor: float = -0.24
    staged_recovery_allows_drawdown_lift: bool = True
    use_window_fuse: bool = False
    fuse_drawdown_limit: float = -0.06
    fuse_rolling_return_limit: float = -0.05
    fuse_rolling_days: int = 20
    fuse_consecutive_loss_days: int = 5
    fuse_weight: float = 0.15
    fuse_cooldown_days: int = 20
    fuse_max_active_days: int = 0
    fuse_reentry_weight: float = 0.45
    fuse_reentry_initial_weight: float = 0.0
    fuse_reentry_step_weight: float = 0.0
    fuse_reentry_step_days: int = 5
    fuse_reentry_days: int = 20
    fuse_reentry_confirmation_days: int = 1
    fuse_reentry_requires_drawdown_repair: bool = True
    fuse_reentry_drawdown_repair: float = 0.015
    fuse_reentry_rolling_return_floor: float = -0.005
    fuse_reentry_requires_market_recovery: bool = True
    fuse_reentry_field: str = "benchmark_momentum_20d_lag1"
    fuse_reentry_threshold: float = 0.0
    fuse_reentry_requires_volatility_calm: bool = False
    fuse_reentry_volatility_field: str = "benchmark_volatility_60d_lag1"
    fuse_reentry_volatility_threshold_field: str = "benchmark_volatility_60d_q80_lag1"
    fuse_reentry_refuse_drawdown_buffer: float = 0.02
    fuse_reentry_refuse_rolling_return_limit: float = -0.03
    fuse_rebalance_buffer: float = 0.03
    use_high_vol_uptrend_guard: bool = False
    high_vol_uptrend_trend_field: str = "benchmark_trend_200d_lag1"
    high_vol_uptrend_volatility_field: str = "benchmark_volatility_60d_lag1"
    high_vol_uptrend_threshold_field: str = "benchmark_volatility_60d_q80_lag1"
    high_vol_uptrend_weight: float = 0.55
    high_vol_uptrend_requires_positive_momentum: bool = False
    high_vol_uptrend_momentum_field: str = "benchmark_momentum_20d_lag1"
    high_vol_uptrend_momentum_floor: float = float("-inf")
    use_uptrend_tail_guard: bool = False
    uptrend_tail_trend_field: str = "benchmark_trend_200d_lag1"
    uptrend_tail_momentum_field: str = "benchmark_momentum_20d_lag1"
    uptrend_tail_momentum_floor: float = -0.015
    uptrend_tail_weight: float = 0.60
    use_downtrend_loss_cluster_fuse: bool = False
    downtrend_fuse_trend_field: str = "benchmark_trend_200d_lag1"
    downtrend_fuse_recovery_field: str = "benchmark_momentum_20d_lag1"
    downtrend_fuse_include_recovery: bool = True
    downtrend_fuse_drawdown_limit: float = -0.04
    downtrend_fuse_rolling_return_limit: float = -0.035
    downtrend_fuse_consecutive_loss_days: int = 3
    use_alpha_health_filter: bool = False
    alpha_health_field: str = "market_alpha_health_score_lag1"
    alpha_health_min: float = 0.38
    alpha_health_warning: float = 0.48
    alpha_health_off_weight: float = 0.0
    alpha_health_weak_weight: float = 0.45
    use_market_breadth_filter: bool = False
    market_breadth_field: str = "market_breadth_60d_lag1"
    market_breadth_min: float = 0.32
    market_breadth_warning: float = 0.42
    market_breadth_off_weight: float = 0.0
    market_breadth_weak_weight: float = 0.45
    use_overheated_reversal_guard: bool = False
    overheated_alpha_health_field: str = "market_alpha_health_score_lag1"
    overheated_alpha_health_min: float = 0.52
    overheated_breadth_field: str = "market_breadth_60d_lag1"
    overheated_breadth_min: float = 0.50
    overheated_momentum_field: str = "benchmark_momentum_20d_lag1"
    overheated_momentum_max: float = 0.0
    overheated_guard_weight: float = 0.06
    portfolio_drawdown_limit: float = 0.0
    drawdown_weight: float = 0.35


@dataclass(frozen=True)
class RiskSpec:
    max_single_position_weight: float = 0.08
    benchmark: str = "CSI300"
    position_stop_loss_limit: float = 0.0
    position_stop_cooldown_days: int = 0
    risk_overlay: RiskOverlaySpec = field(default_factory=RiskOverlaySpec)


@dataclass(frozen=True)
class StrategySpec:
    name: str
    description: str
    universe: UniverseSpec
    rebalance: RebalanceSpec
    portfolio: PortfolioSpec
    costs: CostSpec
    factors: tuple[FactorSpec, ...]
    risk: RiskSpec
    execution: ExecutionSpec = field(default_factory=ExecutionSpec)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StrategySpec":
        factors = tuple(FactorSpec(**factor) for factor in payload["factors"])
        total_weight = sum(factor.weight for factor in factors)
        if not 0.99 <= total_weight <= 1.01:
            raise ValueError(f"Factor weights must sum to 1.0, got {total_weight:.4f}")
        if payload["portfolio"]["weighting"] != "equal":
            raise ValueError("MVP only supports equal weighting")

        risk_payload = dict(payload.get("risk", {}))
        overlay_payload = risk_payload.get("risk_overlay", {})
        if isinstance(overlay_payload, dict):
            risk_payload["risk_overlay"] = RiskOverlaySpec(**overlay_payload)
        elif isinstance(overlay_payload, RiskOverlaySpec):
            risk_payload["risk_overlay"] = overlay_payload
        else:
            risk_payload["risk_overlay"] = RiskOverlaySpec()

        execution_payload = payload.get("execution", {})
        if isinstance(execution_payload, dict):
            execution = ExecutionSpec(**execution_payload)
        elif isinstance(execution_payload, ExecutionSpec):
            execution = execution_payload
        else:
            raise ValueError("execution must be a mapping or ExecutionSpec")

        return cls(
            name=payload["name"],
            description=payload.get("description", ""),
            universe=UniverseSpec(**payload.get("universe", {})),
            rebalance=RebalanceSpec(**payload.get("rebalance", {})),
            portfolio=PortfolioSpec(**payload.get("portfolio", {})),
            costs=CostSpec(**payload.get("costs", {})),
            factors=factors,
            risk=RiskSpec(**risk_payload),
            execution=execution,
        )

    @classmethod
    def from_json(cls, path: str | Path) -> "StrategySpec":
        with Path(path).open("r", encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))


def spec_to_dict(spec: StrategySpec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "description": spec.description,
        "universe": spec.universe.__dict__,
        "rebalance": spec.rebalance.__dict__,
        "portfolio": spec.portfolio.__dict__,
        "costs": spec.costs.__dict__,
        "execution": spec.execution.__dict__,
        "factors": [factor.__dict__ for factor in spec.factors],
        "risk": asdict(spec.risk),
    }
