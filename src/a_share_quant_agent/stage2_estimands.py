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
    global_claim_eligible: bool = False,
) -> dict[str, Any]:
    """Build the complete registered IC estimand bundle without ranking cells."""

    if not isinstance(global_claim_eligible, bool):
        raise Stage2EstimandError("global claim eligibility must be boolean")

    variants = validate_stage2_variant_plan(plan)
    factors = tuple(plan.get("factors") or ())
    if factors != ("roe", "momentum_60d", "low_vol_20d", "composite"):
        raise Stage2EstimandError("registered estimands require the maintained factor order")
    inference_contract = plan.get("inference") or {}
    isolation_tolerance = _finite_float_or_none(
        inference_contract.get("timing_isolation_absolute_tolerance")
    )
    if isolation_tolerance is None or isolation_tolerance <= 0:
        raise Stage2EstimandError(
            "timing-isolation absolute tolerance must be a finite positive number"
        )
    decomposition_contract = inference_contract.get("timing_decomposition")
    if not isinstance(decomposition_contract, Mapping):
        raise Stage2EstimandError(
            "timing-decomposition inference contract is missing"
        )
    decomposition_tolerance = _finite_float_or_none(
        decomposition_contract.get("efficiency_absolute_tolerance")
    )
    if decomposition_tolerance is None or decomposition_tolerance <= 0:
        raise Stage2EstimandError(
            "timing-decomposition absolute tolerance must be a finite positive number"
        )
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
            "directional_expectation": "mean_less_than_zero",
            "reported_null_hypothesis": "two_sided_mean_equals_zero",
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

    publication_exposure_diagnostics = _summarize_publication_exposure(
        observations,
        expected_variant=pit_publication.variant_id,
    )

    (
        secondary_timing_decomposition,
        timing_decomposition_diagnostics,
    ) = _summarize_timing_decomposition(
        observations,
        nw_lag=nw_lag,
        minimum_claim_months=minimum_claim_months,
        absolute_tolerance=decomposition_tolerance,
        minuend_variant=pit_publication.variant_id,
        subtrahend_variant=pit_report.variant_id,
    )

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
        control["absolute_tolerance"] = isolation_tolerance
        control["isolation_check_passed"] = (
            None
            if control["paired_observation_count"] == 0
            else bool(
                control["unmatched_observation_count"] == 0
                and control["maximum_absolute_difference"] <= isolation_tolerance
            )
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

    secondary_members: list[dict[str, Any]] = [
        secondary_publication,
        *secondary_paired,
        *secondary_timing_decomposition,
    ]
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
        "schema_version": "stage2_registered_estimands_v2",
        "primary_family": primary_family,
        "secondary_publication_ic": secondary_publication,
        "secondary_timing_decomposition_ic": secondary_timing_decomposition,
        "timing_decomposition_diagnostics": timing_decomposition_diagnostics,
        "publication_exposure_diagnostics": publication_exposure_diagnostics,
        "timing_negative_controls": timing_negative_controls,
        "secondary_paired_ic": secondary_paired,
        "shapley_ic": shapley_ic,
        "multiplicity_control": {
            "primary": "No multiplicity adjustment: one primary ROE estimand",
            "secondary": (
                "Benjamini-Hochberg FDR 0.10 across the downstream composite publication "
                "contrast, eight paired IC contrasts, three ordered ROE timing-decomposition "
                "components, and sixteen component-factor Shapley IC estimates"
            ),
            "secondary_member_count": len(secondary_members),
        },
        "selection_control": {
            "best_cell_selected": False,
            "all_primary_estimands_reported": True,
            "all_registered_secondary_ic_estimands_reported": True,
        },
        "global_claim_gate": {
            "passed": global_claim_eligible,
            "rule": "all_registered_evidence_gates_must_pass_before_any_estimand_claim",
            "failure_action": "set_every_claim_eligible_and_reject_flag_false",
        },
    }
    if not global_claim_eligible:
        _suppress_claim_and_rejection_flags(bundle)
    verify_registered_estimands(
        bundle,
        factors=factors,
        expected_global_claim_eligible=global_claim_eligible,
    )
    return bundle


def verify_registered_estimands(
    bundle: Mapping[str, Any],
    *,
    factors: Sequence[str],
    expected_global_claim_eligible: bool | None = None,
) -> None:
    """Fail closed when a Stage-2 estimand bundle is partial or internally inconsistent."""

    if bundle.get("schema_version") != "stage2_registered_estimands_v2":
        raise Stage2EstimandError("unsupported Stage-2 estimand schema")
    if expected_global_claim_eligible is not None and not isinstance(
        expected_global_claim_eligible, bool
    ):
        raise Stage2EstimandError("expected global claim eligibility must be boolean")
    global_gate = bundle.get("global_claim_gate")
    if (
        not isinstance(global_gate, Mapping)
        or set(global_gate)
        != {"passed", "rule", "failure_action"}
        or not isinstance(global_gate.get("passed"), bool)
        or global_gate.get("rule")
        != "all_registered_evidence_gates_must_pass_before_any_estimand_claim"
        or global_gate.get("failure_action")
        != "set_every_claim_eligible_and_reject_flag_false"
        or (
            expected_global_claim_eligible is not None
            and global_gate.get("passed") is not expected_global_claim_eligible
        )
    ):
        raise Stage2EstimandError(
            "Stage-2 global claim gate is missing or inconsistent"
        )
    claim_flags = list(_iter_claim_and_rejection_flags(bundle))
    if not claim_flags or any(not isinstance(value, bool) for _, value in claim_flags):
        raise Stage2EstimandError("Stage-2 estimand claim flags are invalid")
    if global_gate["passed"] is False and any(value for _, value in claim_flags):
        raise Stage2EstimandError(
            "Stage-2 global claim gate failed but an estimand claim remains enabled"
        )
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
    timing_decomposition = bundle.get("secondary_timing_decomposition_ic")
    expected_timing_components = (
        "report_support_restriction",
        "common_support_record_replacement",
        "publication_support_extension",
    )
    if (
        not isinstance(timing_decomposition, list)
        or tuple(row.get("component") for row in timing_decomposition)
        != expected_timing_components
        or any("bh_adjusted_p_value" not in row for row in timing_decomposition)
    ):
        raise Stage2EstimandError(
            "Stage-2 ROE timing decomposition family is incomplete"
        )
    timing_diagnostics = bundle.get("timing_decomposition_diagnostics") or {}
    timing_monthly_rows = timing_diagnostics.get("monthly_diagnostics")
    timing_count = timing_diagnostics.get("monthly_observation_count")
    timing_expected_count = timing_diagnostics.get(
        "expected_monthly_observation_count"
    )
    timing_observed_count = timing_diagnostics.get(
        "observed_monthly_diagnostic_count"
    )
    timing_residual = timing_diagnostics.get("maximum_absolute_efficiency_residual")
    if (
        timing_diagnostics.get("schema_version")
        != "stage2_timing_decomposition_diagnostics_v1"
        or isinstance(timing_count, bool)
        or not isinstance(timing_count, int)
        or timing_count < 0
        or isinstance(timing_expected_count, bool)
        or not isinstance(timing_expected_count, int)
        or timing_expected_count < 0
        or isinstance(timing_observed_count, bool)
        or not isinstance(timing_observed_count, int)
        or timing_observed_count < 0
        or not isinstance(timing_monthly_rows, list)
        or timing_expected_count != timing_observed_count
        or timing_observed_count != timing_count
        or timing_count != len(timing_monthly_rows)
        or any(not isinstance(row, Mapping) for row in timing_monthly_rows)
        or [row.get("date") for row in timing_monthly_rows]
        != sorted({
            row.get("date")
            for row in timing_monthly_rows
            if isinstance(row.get("date"), str) and row.get("date")
        })
        or any(
            row.get("monthly_observation_count") != timing_count
            for row in timing_decomposition
        )
    ):
        raise Stage2EstimandError(
            "Stage-2 ROE timing decomposition diagnostics are incomplete"
        )
    if (
        (
            timing_count == 0
            and timing_residual is not None
        )
        or (
            timing_count > 0
            and (
                _finite_float_or_none(timing_residual) is None
                or float(timing_residual)
                > timing_diagnostics.get("absolute_tolerance", 0.0)
            )
        )
    ):
        raise Stage2EstimandError(
            "Stage-2 ROE timing decomposition identity failed"
        )
    exposure_diagnostics = bundle.get("publication_exposure_diagnostics") or {}
    exposure_monthly_rows = exposure_diagnostics.get("monthly_diagnostics")
    exposure_count = exposure_diagnostics.get("monthly_observation_count")
    exposure_expected_count = exposure_diagnostics.get(
        "expected_monthly_observation_count"
    )
    exposure_observed_count = exposure_diagnostics.get(
        "observed_monthly_diagnostic_count"
    )
    if (
        exposure_diagnostics.get("schema_version")
        != "stage2_publication_exposure_diagnostics_v1"
        or exposure_diagnostics.get("uses_forward_returns") is not False
        or isinstance(exposure_count, bool)
        or not isinstance(exposure_count, int)
        or exposure_count < 0
        or isinstance(exposure_expected_count, bool)
        or not isinstance(exposure_expected_count, int)
        or exposure_expected_count < 0
        or isinstance(exposure_observed_count, bool)
        or not isinstance(exposure_observed_count, int)
        or exposure_observed_count < 0
        or not isinstance(exposure_monthly_rows, list)
        or exposure_expected_count != exposure_observed_count
        or exposure_observed_count != exposure_count
        or exposure_count != len(exposure_monthly_rows)
        or any(not isinstance(row, Mapping) for row in exposure_monthly_rows)
        or [row.get("date") for row in exposure_monthly_rows]
        != sorted({
            row.get("date")
            for row in exposure_monthly_rows
            if isinstance(row.get("date"), str) and row.get("date")
        })
    ):
        raise Stage2EstimandError(
            "Stage-2 outcome-free publication exposure diagnostics are incomplete"
        )
    negative_controls = bundle.get("timing_negative_controls")
    if not isinstance(negative_controls, list) or [
        row.get("estimand_id") for row in negative_controls
    ] != [
        "C_publication_isolation_momentum_60d",
        "C_publication_isolation_low_vol_20d",
    ]:
        raise Stage2EstimandError("Stage-2 timing negative controls are incomplete")
    if any(
        row.get("isolation_check_passed") is not True
        and not (
            row.get("paired_observation_count") == 0
            and row.get("isolation_check_passed") is None
        )
        for row in negative_controls
    ):
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
        shapley_count = row.get("complete_month_count")
        shapley_residual = row.get("maximum_absolute_efficiency_residual")
        if (
            shapley_count == 0 and shapley_residual is not None
        ) or (
            isinstance(shapley_count, int)
            and shapley_count > 0
            and (
                _finite_float_or_none(shapley_residual) is None
                or float(shapley_residual) > 1e-10
            )
        ):
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
    if multiplicity.get("secondary_member_count") != 28:
        raise Stage2EstimandError("Stage-2 secondary multiplicity family is incomplete")
    if (
        control.get("best_cell_selected") is not False
        or control.get("all_primary_estimands_reported") is not True
        or control.get("all_registered_secondary_ic_estimands_reported") is not True
    ):
        raise Stage2EstimandError("Stage-2 estimand selection controls failed")


def _suppress_claim_and_rejection_flags(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "claim_eligible" or key.startswith("reject_"):
                value[key] = False
            else:
                _suppress_claim_and_rejection_flags(child)
    elif isinstance(value, list):
        for child in value:
            _suppress_claim_and_rejection_flags(child)


def _iter_claim_and_rejection_flags(value: Any):
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key == "claim_eligible" or key.startswith("reject_"):
                yield key, child
            else:
                yield from _iter_claim_and_rejection_flags(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_claim_and_rejection_flags(child)


def _summarize_publication_exposure(
    observations: Sequence[Mapping[str, Any]],
    *,
    expected_variant: str,
) -> dict[str, Any]:
    count_fields = (
        "report_signal_count",
        "publication_signal_count",
        "common_signal_count",
        "report_only_count",
        "publication_only_count",
        "premature_report_record_count",
        "changed_report_period_count",
        "missing_recorded_publish_date_count",
    )
    expected_dates: set[str] = set()
    for index, observation in enumerate(observations):
        diagnostic = observation.get("publication_exposure")
        is_expected_cell = (
            observation.get("variant") == expected_variant
            and observation.get("factor") == "roe"
        )
        if not is_expected_cell:
            if diagnostic is not None:
                raise Stage2EstimandError(
                    "publication exposure may appear only on the registered publication-date ROE cell"
                )
            continue
        date = observation.get("date")
        if not isinstance(date, str) or not date:
            raise Stage2EstimandError(
                f"publication exposure observation {index} has an invalid date"
            )
        if date in expected_dates:
            raise Stage2EstimandError(
                f"duplicate registered publication-date ROE observation for {date}"
            )
        expected_dates.add(date)

    if not expected_dates:
        raise Stage2EstimandError(
            "Stage-2 publication exposure diagnostics are missing"
        )

    by_date: dict[str, dict[str, Any]] = {}
    for index, observation in enumerate(observations):
        diagnostic = observation.get("publication_exposure")
        if diagnostic is None:
            continue
        if (
            observation.get("variant") != expected_variant
            or observation.get("factor") != "roe"
        ):
            raise Stage2EstimandError(
                "publication exposure may appear only on the registered publication-date ROE cell"
            )
        date = observation.get("date")
        if not isinstance(date, str) or not date or date in by_date:
            raise Stage2EstimandError(
                f"publication exposure observation {index} has an invalid or duplicate date"
            )
        if not isinstance(diagnostic, Mapping):
            raise Stage2EstimandError(
                f"publication exposure for {date} must be an object"
            )
        if diagnostic.get("uses_forward_returns") is not False:
            raise Stage2EstimandError(
                "publication exposure diagnostics must not use forward returns"
            )
        if (
            diagnostic.get("schema_version")
            != "stage2_publication_exposure_month_v1"
            or diagnostic.get("date") != date
        ):
            raise Stage2EstimandError(
                f"publication exposure schema or date is invalid for {date}"
            )
        normalized: dict[str, Any] = {
            "schema_version": diagnostic["schema_version"],
            "uses_forward_returns": False,
            "date": date,
        }
        for field in count_fields:
            value = diagnostic.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise Stage2EstimandError(
                    f"publication exposure {field} is invalid for {date}"
                )
            normalized[field] = value
        report_count = normalized["report_signal_count"]
        publication_count = normalized["publication_signal_count"]
        common_count = normalized["common_signal_count"]
        if (
            common_count + normalized["report_only_count"] != report_count
            or common_count + normalized["publication_only_count"]
            != publication_count
            or normalized["premature_report_record_count"] > report_count
            or normalized["changed_report_period_count"] > common_count
            or normalized["missing_recorded_publish_date_count"] > report_count
        ):
            raise Stage2EstimandError(
                f"publication exposure support counts are inconsistent for {date}"
            )
        share_pairs = (
            (
                "premature_report_record_share",
                normalized["premature_report_record_count"],
                report_count,
            ),
            (
                "changed_report_period_share",
                normalized["changed_report_period_count"],
                common_count,
            ),
        )
        for field, numerator, denominator in share_pairs:
            value = _finite_float_or_none(diagnostic.get(field))
            expected = numerator / denominator if denominator else None
            if (
                (expected is None and diagnostic.get(field) is not None)
                or (expected is not None and (value is None or abs(value - expected) > 1e-12))
            ):
                raise Stage2EstimandError(
                    f"publication exposure {field} is inconsistent for {date}"
                )
            normalized[field] = value

        distribution = diagnostic.get("reporting_delay_calendar_days")
        if not isinstance(distribution, Mapping) or set(distribution) != {
            "count", "mean", "median", "p25", "p75", "maximum",
        }:
            raise Stage2EstimandError(
                f"publication exposure reporting-delay distribution is invalid for {date}"
            )
        distribution_count = distribution.get("count")
        if (
            isinstance(distribution_count, bool)
            or not isinstance(distribution_count, int)
            or distribution_count < 0
            or distribution_count
            != report_count - normalized["missing_recorded_publish_date_count"]
        ):
            raise Stage2EstimandError(
                f"publication exposure reporting-delay count is inconsistent for {date}"
            )
        normalized_distribution: dict[str, Any] = {"count": distribution_count}
        summary_fields = ("mean", "median", "p25", "p75", "maximum")
        if distribution_count == 0:
            if any(distribution.get(field) is not None for field in summary_fields):
                raise Stage2EstimandError(
                    f"empty publication reporting-delay distribution is non-null for {date}"
                )
            normalized_distribution.update({field: None for field in summary_fields})
        else:
            for field in summary_fields:
                value = _finite_float_or_none(distribution.get(field))
                if value is None or value < 0:
                    raise Stage2EstimandError(
                        f"publication exposure reporting-delay {field} is invalid for {date}"
                    )
                normalized_distribution[field] = value
            if not (
                normalized_distribution["p25"]
                <= normalized_distribution["median"]
                <= normalized_distribution["p75"]
                <= normalized_distribution["maximum"]
                and normalized_distribution["mean"]
                <= normalized_distribution["maximum"]
            ):
                raise Stage2EstimandError(
                    f"publication exposure reporting-delay summaries are unordered for {date}"
                )
        normalized["reporting_delay_calendar_days"] = normalized_distribution
        by_date[date] = normalized

    observed_dates = set(by_date)
    if observed_dates != expected_dates:
        raise Stage2EstimandError(
            "publication exposure diagnostic date coverage is incomplete: "
            f"expected {len(expected_dates)}, observed {len(observed_dates)}, "
            f"missing {sorted(expected_dates - observed_dates)}, "
            f"extra {sorted(observed_dates - expected_dates)}"
        )
    monthly_rows = [by_date[date] for date in sorted(by_date)]
    total_report = sum(row["report_signal_count"] for row in monthly_rows)
    total_common = sum(row["common_signal_count"] for row in monthly_rows)
    total_premature = sum(
        row["premature_report_record_count"] for row in monthly_rows
    )
    total_changed = sum(row["changed_report_period_count"] for row in monthly_rows)
    delay_count = sum(
        row["reporting_delay_calendar_days"]["count"] for row in monthly_rows
    )
    weighted_delay_total = sum(
        row["reporting_delay_calendar_days"]["mean"]
        * row["reporting_delay_calendar_days"]["count"]
        for row in monthly_rows
        if row["reporting_delay_calendar_days"]["count"]
    )
    return {
        "schema_version": "stage2_publication_exposure_diagnostics_v1",
        "uses_forward_returns": False,
        "inference": "descriptive_only_outside_bh_family",
        "expected_monthly_observation_count": len(expected_dates),
        "observed_monthly_diagnostic_count": len(monthly_rows),
        "monthly_observation_count": len(monthly_rows),
        "total_report_signal_count": total_report,
        "total_publication_signal_count": sum(
            row["publication_signal_count"] for row in monthly_rows
        ),
        "total_common_signal_count": total_common,
        "total_report_only_count": sum(row["report_only_count"] for row in monthly_rows),
        "total_publication_only_count": sum(
            row["publication_only_count"] for row in monthly_rows
        ),
        "total_premature_report_record_count": total_premature,
        "weighted_premature_report_record_share": (
            float(total_premature / total_report) if total_report else None
        ),
        "total_changed_report_period_count": total_changed,
        "weighted_changed_report_period_share": (
            float(total_changed / total_common) if total_common else None
        ),
        "reporting_delay_calendar_days_weighted_mean": (
            float(weighted_delay_total / delay_count) if delay_count else None
        ),
        "monthly_diagnostics": monthly_rows,
    }


def _summarize_timing_decomposition(
    observations: Sequence[Mapping[str, Any]],
    *,
    nw_lag: int,
    minimum_claim_months: int,
    absolute_tolerance: float,
    minuend_variant: str,
    subtrahend_variant: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Summarize the exact ordered decomposition of the monthly ROE timing shift.

    The three components are arithmetic specification effects, not causal
    effects.  Ranks are recomputed by the runner on each component's declared
    support before this function receives the monthly diagnostic.
    """

    if nw_lag < 0:
        raise Stage2EstimandError("Newey-West lag cannot be negative")
    if minimum_claim_months <= 0:
        raise Stage2EstimandError("minimum claim months must be positive")
    if not math.isfinite(absolute_tolerance) or absolute_tolerance <= 0:
        raise Stage2EstimandError(
            "timing-decomposition absolute tolerance must be finite and positive"
        )

    component_order = (
        "report_support_restriction",
        "common_support_record_replacement",
        "publication_support_extension",
    )
    primary_values: dict[tuple[str, str], float | None] = {}
    for index, observation in enumerate(observations):
        if observation.get("factor") != "roe" or observation.get("variant") not in {
            minuend_variant,
            subtrahend_variant,
        }:
            continue
        date = observation.get("date")
        variant = str(observation.get("variant"))
        value = _finite_float_or_none(observation.get("ic"))
        if not isinstance(date, str) or not date:
            raise Stage2EstimandError(
                f"primary timing observation {index} has an invalid date"
            )
        key = (date, variant)
        if key in primary_values:
            raise Stage2EstimandError(
                f"duplicate primary timing observation for {date}, {variant}"
            )
        primary_values[key] = value

    minuend_dates = {
        date
        for (date, variant), value in primary_values.items()
        if variant == minuend_variant and value is not None
    }
    subtrahend_dates = {
        date
        for (date, variant), value in primary_values.items()
        if variant == subtrahend_variant and value is not None
    }
    expected_dates = minuend_dates & subtrahend_dates

    by_date: dict[str, dict[str, Any]] = {}
    for index, observation in enumerate(observations):
        diagnostic = observation.get("timing_decomposition")
        if diagnostic is None:
            continue
        if (
            observation.get("factor") != "roe"
            or observation.get("variant") != minuend_variant
        ):
            raise Stage2EstimandError(
                "timing decomposition may appear only on the registered publication-date ROE cell"
            )
        date = observation.get("date")
        if not isinstance(date, str) or not date:
            raise Stage2EstimandError(
                f"timing decomposition observation {index} has an invalid date"
            )
        if date in by_date:
            raise Stage2EstimandError(
                f"duplicate ROE timing decomposition for {date}"
            )
        if date not in expected_dates:
            raise Stage2EstimandError(
                f"timing decomposition for {date} is outside the finite primary intersection"
            )
        if not isinstance(diagnostic, Mapping):
            raise Stage2EstimandError(
                f"timing decomposition for {date} must be an object"
            )
        required_numeric = (
            *component_order,
            "total_timing_difference",
            "efficiency_residual",
            "u_r_count",
            "u_p_count",
            "intersection_count",
        )
        normalized: dict[str, Any] = {}
        for key in required_numeric:
            value = _finite_float_or_none(diagnostic.get(key))
            if value is None:
                raise Stage2EstimandError(
                    f"timing decomposition {key} is missing or non-finite for {date}"
                )
            normalized[key] = value
        if any(normalized[key] < 0 for key in (
            "u_r_count",
            "u_p_count",
            "intersection_count",
        )):
            raise Stage2EstimandError(
                f"timing decomposition counts cannot be negative for {date}"
            )
        if normalized["intersection_count"] > min(
            normalized["u_r_count"], normalized["u_p_count"]
        ):
            raise Stage2EstimandError(
                f"timing decomposition intersection exceeds full support for {date}"
            )
        component_sum = sum(normalized[key] for key in component_order)
        if abs(component_sum - normalized["total_timing_difference"]) > absolute_tolerance:
            raise Stage2EstimandError(
                f"timing decomposition components do not sum to the total for {date}"
            )
        if abs(normalized["efficiency_residual"]) > absolute_tolerance:
            raise Stage2EstimandError(
                f"timing decomposition efficiency residual exceeds tolerance for {date}"
            )
        primary_pair = (
            primary_values.get((date, minuend_variant)),
            primary_values.get((date, subtrahend_variant)),
        )
        if any(value is None for value in primary_pair):
            raise Stage2EstimandError(
                f"timing decomposition lacks a finite primary monthly contrast for {date}"
            )
        primary_difference = float(primary_pair[0]) - float(primary_pair[1])
        if abs(
            normalized["total_timing_difference"] - primary_difference
        ) > absolute_tolerance:
            raise Stage2EstimandError(
                f"timing decomposition differs from the primary monthly contrast for {date}"
            )
        by_date[date] = normalized

    observed_dates = set(by_date)
    if observed_dates != expected_dates:
        raise Stage2EstimandError(
            "timing decomposition diagnostic date coverage is incomplete: "
            f"expected {len(expected_dates)}, observed {len(observed_dates)}, "
            f"missing {sorted(expected_dates - observed_dates)}, "
            f"extra {sorted(observed_dates - expected_dates)}"
        )

    if not by_date:
        empty_inference = _newey_west_mean_inference(
            np.asarray([], dtype=float), lag=nw_lag
        )
        component_rows = [
            {
                "estimand_id": f"S_roe_timing_{component}",
                "component": component,
                "role": "ordered_noncausal_timing_decomposition_secondary",
                "monthly_observation_count": 0,
                "mean_difference": None,
                "newey_west_lag": nw_lag,
                **empty_inference,
                "minimum_claim_months": minimum_claim_months,
                "claim_eligible": False,
            }
            for component in component_order
        ]
        return component_rows, {
            "schema_version": "stage2_timing_decomposition_diagnostics_v1",
            "component_order": list(component_order),
            "expected_monthly_observation_count": len(expected_dates),
            "observed_monthly_diagnostic_count": 0,
            "monthly_observation_count": 0,
            "absolute_tolerance": absolute_tolerance,
            "maximum_absolute_efficiency_residual": None,
            "mean_report_support_count": None,
            "mean_publication_support_count": None,
            "mean_common_support_count": None,
            "mean_publication_support_share": None,
            "monthly_diagnostics": [],
        }

    component_rows: list[dict[str, Any]] = []
    for component in component_order:
        values = np.asarray(
            [by_date[date][component] for date in sorted(by_date)], dtype=float
        )
        inference = _newey_west_mean_inference(values, lag=nw_lag)
        component_rows.append({
            "estimand_id": f"S_roe_timing_{component}",
            "component": component,
            "role": "ordered_noncausal_timing_decomposition_secondary",
            "monthly_observation_count": len(values),
            "mean_difference": float(values.mean()),
            "newey_west_lag": nw_lag,
            **inference,
            "minimum_claim_months": minimum_claim_months,
            "claim_eligible": (
                len(values) >= minimum_claim_months
                and inference["two_sided_p_value"] is not None
            ),
        })

    monthly_rows = [
        {"date": date, **by_date[date]}
        for date in sorted(by_date)
    ]
    report_counts = np.asarray(
        [row["u_r_count"] for row in monthly_rows], dtype=float
    )
    publication_counts = np.asarray(
        [row["u_p_count"] for row in monthly_rows], dtype=float
    )
    diagnostics = {
        "schema_version": "stage2_timing_decomposition_diagnostics_v1",
        "component_order": list(component_order),
        "expected_monthly_observation_count": len(expected_dates),
        "observed_monthly_diagnostic_count": len(monthly_rows),
        "monthly_observation_count": len(monthly_rows),
        "absolute_tolerance": absolute_tolerance,
        "maximum_absolute_efficiency_residual": float(
            max(abs(row["efficiency_residual"]) for row in monthly_rows)
        ),
        "mean_report_support_count": float(report_counts.mean()),
        "mean_publication_support_count": float(publication_counts.mean()),
        "mean_common_support_count": float(
            np.mean([row["intersection_count"] for row in monthly_rows])
        ),
        "mean_publication_support_share": float(
            np.mean(
                np.divide(
                    publication_counts,
                    report_counts,
                    out=np.zeros_like(publication_counts),
                    where=report_counts > 0,
                )
            )
        ),
        "monthly_diagnostics": monthly_rows,
    }
    return component_rows, diagnostics


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
    registered_minuend_dates = {
        date for date, variant in selected if variant == minuend_variant
    }
    registered_subtrahend_dates = {
        date for date, variant in selected if variant == subtrahend_variant
    }
    if not paired_dates:
        return {
            "minuend_variant": minuend_variant,
            "subtrahend_variant": subtrahend_variant,
            "factor": factor,
            "outcome": outcome,
            "paired_observation_count": 0,
            "unmatched_observation_count": len(minuend_dates ^ subtrahend_dates),
            "nonestimable_matched_date_count": len(
                registered_minuend_dates & registered_subtrahend_dates
            ),
            "mean_difference": None,
            "maximum_absolute_difference": None,
            "newey_west_lag": nw_lag,
            **_newey_west_mean_inference(np.asarray([], dtype=float), lag=nw_lag),
            "minimum_claim_months": minimum_claim_months,
            "claim_eligible": False,
        }
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
        "nonestimable_matched_date_count": len(
            (registered_minuend_dates & registered_subtrahend_dates) - set(paired_dates)
        ),
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
        empty_inference = _newey_west_mean_inference(
            np.asarray([], dtype=float), lag=nw_lag
        )
        return {
            "schema_version": "stage2_exact_shapley_v1",
            "factor": factor,
            "outcome": outcome,
            "component_order": list(STAGE2_COMPONENTS),
            "complete_month_count": 0,
            "incomplete_month_count": incomplete,
            "components": [
                {
                    "component": component,
                    "monthly_observation_count": 0,
                    "mean_contribution": None,
                    "newey_west_lag": nw_lag,
                    **empty_inference,
                }
                for component in STAGE2_COMPONENTS
            ],
            "maximum_absolute_efficiency_residual": None,
            "monthly_contributions": [],
        }
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
