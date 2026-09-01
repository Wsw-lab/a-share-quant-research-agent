"""Pre-specified estimands for the Stage-2 A-share bias decomposition.

The functions in this module operate on monthly, all-cell observations from
``confirmatory_study``.  They deliberately compare variants within the same
month and use the complete registered factorial; no result-selection helper is
provided.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any

import numpy as np

from .confirmatory_study import (
    STAGE2_COMPONENTS,
    Stage2VariantSpec,
    validate_stage2_variant_plan,
)


class Stage2EstimandError(RuntimeError):
    """Raised when registered Stage-2 estimands cannot be computed safely."""


def build_registered_estimands(
    observations: Sequence[Mapping[str, Any]],
    *,
    plan: Mapping[str, Any],
    nw_lag: int = 3,
    minimum_claim_months: int = 60,
) -> dict[str, Any]:
    """Build the complete registered IC estimand bundle without ranking cells."""

    variants = validate_stage2_variant_plan(plan)
    factors = tuple(plan.get("factors") or ())
    if factors != ("roe", "momentum_60d", "low_vol_20d", "composite"):
        raise Stage2EstimandError("registered estimands require the maintained factor order")
    final_report = _unique_semantic_variant(
        variants,
        universe_mode="final_survivor",
        availability="report_period_end",
        components=frozenset(),
    )
    pit_report = _unique_semantic_variant(
        variants,
        universe_mode="point_in_time",
        availability="report_period_end",
        components=frozenset(),
    )
    pit_publication = _unique_semantic_variant(
        variants,
        universe_mode="point_in_time",
        availability="publication_date",
        components=frozenset(),
    )
    pit_full = _unique_semantic_variant(
        variants,
        universe_mode="point_in_time",
        availability="publication_date",
        components=frozenset(STAGE2_COMPONENTS),
    )

    primary_family = []
    for estimand_id, factor in (
        ("P1_roe_publication_signed_decrement", "roe"),
    ):
        primary_family.append({
            "estimand_id": estimand_id,
            "directional_expectation": "less_than_or_equal_to_zero",
            **paired_variant_difference(
                observations,
                minuend_variant=pit_publication.variant_id,
                subtrahend_variant=pit_report.variant_id,
                factor=factor,
                outcome="ic",
                nw_lag=nw_lag,
                minimum_claim_months=minimum_claim_months,
            ),
        })
    for row in primary_family:
        adjusted = row["two_sided_p_value"]
        row["primary_adjusted_p_value"] = adjusted
        row["primary_multiplicity_method"] = "none_single_primary"
        row["reject_primary_at_alpha_0_05"] = bool(
            row["claim_eligible"] and adjusted is not None and adjusted <= 0.05
        )

    secondary_publication = {
        "estimand_id": "S_composite_publication_signed_decrement",
        "interpretation": (
            "downstream composite response to the ROE timing correction; not independent primary evidence"
        ),
        **paired_variant_difference(
            observations,
            minuend_variant=pit_publication.variant_id,
            subtrahend_variant=pit_report.variant_id,
            factor="composite",
            outcome="ic",
            nw_lag=nw_lag,
            minimum_claim_months=minimum_claim_months,
        ),
    }

    timing_negative_controls = []
    for factor in ("momentum_60d", "low_vol_20d"):
        control = {
            "estimand_id": f"C_publication_isolation_{factor}",
            "role": "deterministic_timing_isolation_check_not_in_inferential_family",
            **paired_variant_difference(
                observations,
                minuend_variant=pit_publication.variant_id,
                subtrahend_variant=pit_report.variant_id,
                factor=factor,
                outcome="ic",
                nw_lag=nw_lag,
                minimum_claim_months=minimum_claim_months,
            ),
        }
        control["absolute_tolerance"] = 1e-12
        control["isolation_check_passed"] = bool(
            control["unmatched_observation_count"] == 0
            and control["maximum_absolute_difference"] <= 1e-12
        )
        timing_negative_controls.append(control)

    secondary_paired = []
    for factor in factors:
        secondary_paired.extend([
            {
                "estimand_id": f"S_membership_{factor}_ic",
                **paired_variant_difference(
                    observations,
                    minuend_variant=pit_report.variant_id,
                    subtrahend_variant=final_report.variant_id,
                    factor=factor,
                    outcome="ic",
                    nw_lag=nw_lag,
                    minimum_claim_months=minimum_claim_months,
                ),
            },
            {
                "estimand_id": f"S_full_implementation_{factor}_ic",
                **paired_variant_difference(
                    observations,
                    minuend_variant=pit_full.variant_id,
                    subtrahend_variant=pit_publication.variant_id,
                    factor=factor,
                    outcome="ic",
                    nw_lag=nw_lag,
                    minimum_claim_months=minimum_claim_months,
                ),
            },
        ])
    shapley_ic = [
        exact_monthly_shapley(
            observations,
            plan=plan,
            factor=factor,
            outcome="ic",
            nw_lag=nw_lag,
        )
        for factor in factors
    ]

    secondary_members: list[dict[str, Any]] = [secondary_publication, *secondary_paired]
    for result in shapley_ic:
        for component in result["components"]:
            component["estimand_id"] = (
                f"S_shapley_{result['factor']}_{component['component']}_ic"
            )
            component["claim_eligible"] = (
                component["monthly_observation_count"] >= minimum_claim_months
                and component["two_sided_p_value"] is not None
            )
            secondary_members.append(component)
    adjusted_secondary = benjamini_hochberg_adjust(
        [row["two_sided_p_value"] for row in secondary_members]
    )
    for row, adjusted in zip(secondary_members, adjusted_secondary):
        row["bh_adjusted_p_value"] = adjusted
        row["reject_at_fdr_0_10"] = bool(
            row["claim_eligible"] and adjusted is not None and adjusted <= 0.10
        )

    bundle = {
        "schema_version": "stage2_registered_estimands_v1",
        "primary_family": primary_family,
        "secondary_publication_ic": secondary_publication,
        "timing_negative_controls": timing_negative_controls,
        "secondary_paired_ic": secondary_paired,
        "shapley_ic": shapley_ic,
        "multiplicity_control": {
            "primary": "No multiplicity adjustment: one primary ROE estimand",
            "secondary": (
                "Benjamini-Hochberg FDR 0.10 across the downstream composite publication "
                "contrast, eight paired IC contrasts, and sixteen component-factor Shapley IC estimates"
            ),
            "secondary_member_count": len(secondary_members),
        },
        "selection_control": {
            "best_cell_selected": False,
            "all_primary_estimands_reported": True,
            "all_registered_secondary_ic_estimands_reported": True,
        },
    }
    verify_registered_estimands(bundle, factors=factors)
    return bundle


def verify_registered_estimands(
    bundle: Mapping[str, Any],
    *,
    factors: Sequence[str],
) -> None:
    """Fail closed when a Stage-2 estimand bundle is partial or internally inconsistent."""

    if bundle.get("schema_version") != "stage2_registered_estimands_v1":
        raise Stage2EstimandError("unsupported Stage-2 estimand schema")
    primary = bundle.get("primary_family")
    if not isinstance(primary, list) or [row.get("estimand_id") for row in primary] != [
        "P1_roe_publication_signed_decrement",
    ]:
        raise Stage2EstimandError("Stage-2 primary estimand family is incomplete")
    if any("primary_adjusted_p_value" not in row for row in primary):
        raise Stage2EstimandError("Stage-2 primary multiplicity adjustment is missing")
    secondary_publication = bundle.get("secondary_publication_ic") or {}
    if secondary_publication.get("estimand_id") != "S_composite_publication_signed_decrement":
        raise Stage2EstimandError("Stage-2 composite publication estimand is missing")
    negative_controls = bundle.get("timing_negative_controls")
    if not isinstance(negative_controls, list) or [
        row.get("estimand_id") for row in negative_controls
    ] != [
        "C_publication_isolation_momentum_60d",
        "C_publication_isolation_low_vol_20d",
    ]:
        raise Stage2EstimandError("Stage-2 timing negative controls are incomplete")
    if any(row.get("isolation_check_passed") is not True for row in negative_controls):
        raise Stage2EstimandError("Stage-2 publication-timing isolation check failed")
    secondary = bundle.get("secondary_paired_ic")
    if not isinstance(secondary, list) or len(secondary) != 2 * len(factors):
        raise Stage2EstimandError("Stage-2 paired secondary IC family is incomplete")
    shapley = bundle.get("shapley_ic")
    if not isinstance(shapley, list) or {row.get("factor") for row in shapley} != set(factors):
        raise Stage2EstimandError("Stage-2 Shapley IC family is incomplete")
    for row in shapley:
        if row.get("component_order") != list(STAGE2_COMPONENTS):
            raise Stage2EstimandError("Stage-2 Shapley component order differs from the plan")
        if row.get("maximum_absolute_efficiency_residual", math.inf) > 1e-10:
            raise Stage2EstimandError("Stage-2 Shapley efficiency identity failed")
        components = row.get("components")
        if not isinstance(components, list) or {
            component.get("component") for component in components
        } != set(STAGE2_COMPONENTS):
            raise Stage2EstimandError("Stage-2 Shapley components are incomplete")
        if any("bh_adjusted_p_value" not in component for component in components):
            raise Stage2EstimandError("Stage-2 secondary multiplicity adjustment is missing")
    control = bundle.get("selection_control") or {}
    multiplicity = bundle.get("multiplicity_control") or {}
    if multiplicity.get("secondary_member_count") != 25:
        raise Stage2EstimandError("Stage-2 secondary multiplicity family is incomplete")
    if (
        control.get("best_cell_selected") is not False
        or control.get("all_primary_estimands_reported") is not True
        or control.get("all_registered_secondary_ic_estimands_reported") is not True
    ):
        raise Stage2EstimandError("Stage-2 estimand selection controls failed")


def paired_variant_difference(
    observations: Sequence[Mapping[str, Any]],
    *,
    minuend_variant: str,
    subtrahend_variant: str,
    factor: str,
    outcome: str = "ic",
    nw_lag: int = 3,
    minimum_claim_months: int = 60,
) -> dict[str, Any]:
    """Estimate a within-month difference with Newey-West HAC inference."""

    if not minuend_variant or not subtrahend_variant:
        raise Stage2EstimandError("both variant identifiers are required")
    if minuend_variant == subtrahend_variant:
        raise Stage2EstimandError("paired variants must differ")
    if not factor or not outcome:
        raise Stage2EstimandError("factor and outcome are required")
    if nw_lag < 0:
        raise Stage2EstimandError("Newey-West lag cannot be negative")
    if minimum_claim_months <= 0:
        raise Stage2EstimandError("minimum claim months must be positive")

    selected: dict[tuple[str, str], float | None] = {}
    for index, row in enumerate(observations):
        if row.get("factor") != factor or row.get("variant") not in {
            minuend_variant,
            subtrahend_variant,
        }:
            continue
        date = row.get("date")
        variant = row.get("variant")
        if not isinstance(date, str) or not date:
            raise Stage2EstimandError(f"observation {index} has an invalid date")
        key = (date, str(variant))
        if key in selected:
            raise Stage2EstimandError(
                f"duplicate monthly observation for {date}, {variant}, {factor}"
            )
        selected[key] = _finite_float_or_none(row.get(outcome))

    minuend_dates = {
        date for (date, variant), value in selected.items()
        if variant == minuend_variant and value is not None
    }
    subtrahend_dates = {
        date for (date, variant), value in selected.items()
        if variant == subtrahend_variant and value is not None
    }
    paired_dates = sorted(minuend_dates & subtrahend_dates)
    if not paired_dates:
        raise Stage2EstimandError(
            f"no matched monthly observations for {minuend_variant} and {subtrahend_variant}"
        )
    differences = np.asarray([
        float(selected[(date, minuend_variant)])
        - float(selected[(date, subtrahend_variant)])
        for date in paired_dates
    ])
    inference = _newey_west_mean_inference(differences, lag=nw_lag)
    return {
        "minuend_variant": minuend_variant,
        "subtrahend_variant": subtrahend_variant,
        "factor": factor,
        "outcome": outcome,
        "paired_observation_count": len(paired_dates),
        "unmatched_observation_count": len(minuend_dates ^ subtrahend_dates),
        "mean_difference": float(differences.mean()),
        "maximum_absolute_difference": float(np.max(np.abs(differences))),
        "newey_west_lag": nw_lag,
        **inference,
        "minimum_claim_months": minimum_claim_months,
        "claim_eligible": (
            len(paired_dates) >= minimum_claim_months
            and inference["two_sided_p_value"] is not None
        ),
    }


def exact_monthly_shapley(
    observations: Sequence[Mapping[str, Any]],
    *,
    plan: Mapping[str, Any],
    factor: str,
    outcome: str = "ic",
    nw_lag: int = 3,
) -> dict[str, Any]:
    """Compute exact Shapley values from every complete monthly 2^4 cell set."""

    if nw_lag < 0:
        raise Stage2EstimandError("Newey-West lag cannot be negative")
    variants = validate_stage2_variant_plan(plan)
    factorial = _factorial_variants(variants)
    relevant_ids = {variant.variant_id for variant in factorial.values()}
    by_date: dict[str, dict[str, float | None]] = {}
    for index, row in enumerate(observations):
        if row.get("factor") != factor or row.get("variant") not in relevant_ids:
            continue
        date = row.get("date")
        variant = row.get("variant")
        if not isinstance(date, str) or not date:
            raise Stage2EstimandError(f"observation {index} has an invalid date")
        month = by_date.setdefault(date, {})
        if variant in month:
            raise Stage2EstimandError(
                f"duplicate monthly observation for {date}, {variant}, {factor}"
            )
        month[str(variant)] = _finite_float_or_none(row.get(outcome))

    if not by_date:
        raise Stage2EstimandError(f"no factorial observations for factor {factor}")
    component_values: dict[str, list[float]] = {
        component: [] for component in STAGE2_COMPONENTS
    }
    monthly_rows: list[dict[str, Any]] = []
    efficiency_residuals: list[float] = []
    expected_ids = {variant.variant_id for variant in factorial.values()}
    incomplete = 0
    for date in sorted(by_date):
        month = by_date[date]
        if set(month) != expected_ids or any(value is None for value in month.values()):
            incomplete += 1
            continue
        value_function = {
            components: float(month[variant.variant_id])
            for components, variant in factorial.items()
        }
        contributions = _shapley_for_value_function(value_function)
        residual = (
            sum(contributions.values())
            - (value_function[frozenset(STAGE2_COMPONENTS)] - value_function[frozenset()])
        )
        efficiency_residuals.append(residual)
        monthly_rows.append({
            "date": date,
            "contributions": {
                component: contributions[component] for component in STAGE2_COMPONENTS
            },
            "full_minus_empty": (
                value_function[frozenset(STAGE2_COMPONENTS)]
                - value_function[frozenset()]
            ),
            "efficiency_residual": residual,
        })
        for component in STAGE2_COMPONENTS:
            component_values[component].append(contributions[component])

    if not monthly_rows:
        raise Stage2EstimandError(
            f"no month has all 16 finite factorial cells for {factor} and {outcome}"
        )
    summaries = []
    for component in STAGE2_COMPONENTS:
        values = np.asarray(component_values[component], dtype=float)
        summaries.append({
            "component": component,
            "monthly_observation_count": len(values),
            "mean_contribution": float(values.mean()),
            "newey_west_lag": nw_lag,
            **_newey_west_mean_inference(values, lag=nw_lag),
        })
    return {
        "schema_version": "stage2_exact_shapley_v1",
        "factor": factor,
        "outcome": outcome,
        "component_order": list(STAGE2_COMPONENTS),
        "complete_month_count": len(monthly_rows),
        "incomplete_month_count": incomplete,
        "components": summaries,
        "maximum_absolute_efficiency_residual": float(
            max(abs(value) for value in efficiency_residuals)
        ),
        "monthly_contributions": monthly_rows,
    }


def holm_adjust(p_values: Sequence[float | None]) -> list[float | None]:
    """Return Holm family-wise adjusted p-values in original order."""

    return _adjust_p_values(p_values, method="holm")


def benjamini_hochberg_adjust(
    p_values: Sequence[float | None],
) -> list[float | None]:
    """Return Benjamini-Hochberg FDR adjusted p-values in original order."""

    return _adjust_p_values(p_values, method="benjamini-hochberg")


def _factorial_variants(
    variants: Sequence[Stage2VariantSpec],
) -> dict[frozenset[str], Stage2VariantSpec]:
    factorial = {
        variant.components: variant
        for variant in variants
        if variant.universe_mode == "point_in_time"
        and variant.fundamental_availability == "publication_date"
    }
    if len(factorial) != 1 << len(STAGE2_COMPONENTS):
        raise Stage2EstimandError("Stage-2 implementation factorial is incomplete")
    return factorial


def _unique_semantic_variant(
    variants: Sequence[Stage2VariantSpec],
    *,
    universe_mode: str,
    availability: str,
    components: frozenset[str],
) -> Stage2VariantSpec:
    matches = [
        variant for variant in variants
        if variant.universe_mode == universe_mode
        and variant.fundamental_availability == availability
        and variant.components == components
    ]
    if len(matches) != 1:
        raise Stage2EstimandError("registered semantic variant is absent or ambiguous")
    return matches[0]


def _shapley_for_value_function(
    values: Mapping[frozenset[str], float],
) -> dict[str, float]:
    component_count = len(STAGE2_COMPONENTS)
    expected_subsets = {
        frozenset(
            component
            for index, component in enumerate(STAGE2_COMPONENTS)
            if mask & (1 << index)
        )
        for mask in range(1 << component_count)
    }
    if set(values) != expected_subsets:
        raise Stage2EstimandError("Shapley value function must contain the complete factorial")
    denominator = math.factorial(component_count)
    contributions: dict[str, float] = {}
    for component in STAGE2_COMPONENTS:
        contribution = 0.0
        for subset in expected_subsets:
            if component in subset:
                continue
            weight = (
                math.factorial(len(subset))
                * math.factorial(component_count - len(subset) - 1)
                / denominator
            )
            contribution += weight * (
                values[subset | {component}] - values[subset]
            )
        contributions[component] = float(contribution)
    return contributions


def _newey_west_mean_inference(values: np.ndarray, *, lag: int) -> dict[str, float | None]:
    if len(values) < 3:
        return {
            "newey_west_standard_error": None,
            "newey_west_t_stat": None,
            "two_sided_p_value": None,
            "ci95_lower": None,
            "ci95_upper": None,
        }
    centered = values - values.mean()
    count = len(values)
    long_run_variance = float(np.dot(centered, centered) / count)
    effective_lag = min(lag, count - 1)
    for offset in range(1, effective_lag + 1):
        covariance = float(np.dot(centered[offset:], centered[:-offset]) / count)
        long_run_variance += 2.0 * (1.0 - offset / (effective_lag + 1.0)) * covariance
    long_run_variance = max(long_run_variance, 0.0)
    standard_error = math.sqrt(long_run_variance / count)
    if standard_error <= 0.0:
        return {
            "newey_west_standard_error": 0.0,
            "newey_west_t_stat": None,
            "two_sided_p_value": None,
            "ci95_lower": None,
            "ci95_upper": None,
        }
    mean = float(values.mean())
    t_stat = mean / standard_error
    p_value = math.erfc(abs(t_stat) / math.sqrt(2.0))
    critical = 1.959963984540054
    return {
        "newey_west_standard_error": float(standard_error),
        "newey_west_t_stat": float(t_stat),
        "two_sided_p_value": float(p_value),
        "ci95_lower": float(mean - critical * standard_error),
        "ci95_upper": float(mean + critical * standard_error),
    }


def _adjust_p_values(
    p_values: Sequence[float | None],
    *,
    method: str,
) -> list[float | None]:
    values = list(p_values)
    finite: list[tuple[int, float]] = []
    for index, value in enumerate(values):
        if value is None:
            continue
        numeric = float(value)
        if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
            raise Stage2EstimandError("p-values must be finite and between zero and one")
        finite.append((index, numeric))
    adjusted: list[float | None] = [None] * len(values)
    if not finite:
        return adjusted
    ordered = sorted(finite, key=lambda item: (item[1], item[0]))
    # Missing registered tests remain in the pre-specified family.  Treating
    # them as absent would shrink m after outcomes are known and make both
    # procedures anti-conservative.  They remain unreported/non-rejections,
    # while finite p-values use the full planned family size.
    count = len(values)
    if method == "holm":
        running = 0.0
        for rank, (index, value) in enumerate(ordered):
            running = max(running, (count - rank) * value)
            adjusted[index] = min(1.0, running)
    elif method == "benjamini-hochberg":
        running = 1.0
        for reverse_index in range(len(ordered) - 1, -1, -1):
            index, value = ordered[reverse_index]
            rank = reverse_index + 1
            running = min(running, value * count / rank)
            adjusted[index] = min(1.0, running)
    else:
        raise Stage2EstimandError(f"unsupported p-value adjustment: {method}")
    return adjusted


def _finite_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise Stage2EstimandError(f"outcome is not numeric: {value!r}") from exc
    return numeric if math.isfinite(numeric) else None
