from __future__ import annotations

import copy
import unittest

from a_share_quant_agent.confirmatory_study import (
    STAGE2_COMPONENTS,
    STAGE2_SCHEMA_VERSION,
)
from a_share_quant_agent.stage2_estimands import (
    Stage2EstimandError,
    benjamini_hochberg_adjust,
    build_registered_estimands,
    exact_monthly_shapley,
    holm_adjust,
    paired_variant_difference,
    verify_registered_estimands,
)


class Stage2EstimandsTest(unittest.TestCase):
    def test_paired_variant_difference_uses_only_matched_months(self) -> None:
        observations = []
        baseline = [0.01, 0.04, 0.02, 0.06, 0.03, 0.08]
        differences = [-0.02, -0.01, -0.03, -0.02, -0.04, -0.01]
        for month, (base, difference) in enumerate(zip(baseline, differences), start=1):
            day = f"2025-{month:02d}-03"
            observations.extend([
                {"date": day, "variant": "A1", "factor": "roe", "ic": base},
                {
                    "date": day,
                    "variant": "I0000",
                    "factor": "roe",
                    "ic": base + difference,
                },
            ])
        observations.append(
            {"date": "2025-07-03", "variant": "A1", "factor": "roe", "ic": 9.0}
        )

        result = paired_variant_difference(
            observations,
            minuend_variant="I0000",
            subtrahend_variant="A1",
            factor="roe",
            outcome="ic",
            nw_lag=3,
            minimum_claim_months=60,
        )

        self.assertEqual(result["paired_observation_count"], 6)
        self.assertEqual(result["unmatched_observation_count"], 1)
        self.assertAlmostEqual(result["mean_difference"], sum(differences) / 6)
        self.assertAlmostEqual(result["maximum_absolute_difference"], 0.04)
        self.assertIsNotNone(result["newey_west_standard_error"])
        self.assertIsNotNone(result["two_sided_p_value"])
        self.assertFalse(result["claim_eligible"])

    def test_exact_shapley_recovers_main_effects_and_splits_interaction(self) -> None:
        plan = _stage2_plan()
        factorial = [
            variant
            for variant in plan["variants"]
            if variant["universe_mode"] == "point_in_time"
            and variant["fundamental_availability"] == "publication_date"
        ]
        observations = []
        for date_index, day in enumerate(("2025-01-03", "2025-02-03"), start=1):
            for variant in factorial:
                enabled = set(variant["components"])
                value = float(date_index)
                value += 1.0 if "exclude_st" in enabled else 0.0
                value += 2.0 if "exclude_suspended" in enabled else 0.0
                value += 3.0 if "minimum_amount_20d" in enabled else 0.0
                value += 4.0 if "one_session_lag" in enabled else 0.0
                if {"exclude_st", "exclude_suspended"}.issubset(enabled):
                    value += 5.0
                observations.append({
                    "date": day,
                    "variant": variant["id"],
                    "factor": "roe",
                    "ic": value,
                })

        result = exact_monthly_shapley(
            observations,
            plan=plan,
            factor="roe",
            outcome="ic",
            nw_lag=1,
        )

        self.assertEqual(result["complete_month_count"], 2)
        expected = {
            "exclude_st": 3.5,
            "exclude_suspended": 4.5,
            "minimum_amount_20d": 3.0,
            "one_session_lag": 4.0,
        }
        for row in result["components"]:
            self.assertAlmostEqual(row["mean_contribution"], expected[row["component"]])
        self.assertAlmostEqual(result["maximum_absolute_efficiency_residual"], 0.0)

    def test_registered_multiplicity_adjustments_are_monotone_and_bounded(self) -> None:
        self.assertEqual(holm_adjust([0.01, 0.04]), [0.02, 0.04])
        adjusted = benjamini_hochberg_adjust([0.01, 0.04, 0.03, 0.2])
        self.assertEqual(adjusted, [0.04, 0.05333333333333334, 0.05333333333333334, 0.2])
        self.assertTrue(all(0.0 <= value <= 1.0 for value in adjusted))
        self.assertEqual(holm_adjust([0.03, None]), [0.06, None])
        self.assertEqual(benjamini_hochberg_adjust([0.03, None]), [0.06, None])

    def test_registered_bundle_v2_adds_three_timing_decomposition_components_to_bh_family(self) -> None:
        plan = _stage2_plan()
        observations = []
        for month in range(1, 7):
            day = f"2025-{month:02d}-03"
            report_ic = 0.05 + month / 1000
            report_support = -0.004 - month / 10000
            record_replacement = -0.020 - month / 5000
            publication_support = 0.002 + month / 20000
            total_timing = (
                report_support + record_replacement + publication_support
            )
            for variant in plan["variants"]:
                enabled = set(variant["components"])
                for factor_index, factor in enumerate(plan["factors"], start=1):
                    base = report_ic + factor_index / 100
                    if variant["id"] == "A0":
                        value = base - 0.01
                    elif variant["id"] == "A1":
                        value = base
                    else:
                        value = base
                        if factor == "roe":
                            value += total_timing
                        elif factor == "composite":
                            value -= 0.01
                        value += 0.001 * len(enabled)
                    row = {
                        "date": day,
                        "variant": variant["id"],
                        "factor": factor,
                        "ic": value,
                    }
                    if variant["id"] == "I0000" and factor == "roe":
                        row["publication_exposure"] = _publication_exposure(day)
                        row["timing_decomposition"] = {
                            "report_support_restriction": report_support,
                            "common_support_record_replacement": record_replacement,
                            "publication_support_extension": publication_support,
                            "total_timing_difference": total_timing,
                            "efficiency_residual": 0.0,
                            "u_r_count": 1200,
                            "u_p_count": 1100,
                            "intersection_count": 1050,
                        }
                    observations.append(row)

        bundle = build_registered_estimands(
            observations,
            plan=plan,
            nw_lag=1,
            minimum_claim_months=3,
        )

        self.assertEqual(bundle["schema_version"], "stage2_registered_estimands_v2")
        decomposition = bundle["secondary_timing_decomposition_ic"]
        self.assertEqual(
            {row["component"] for row in decomposition},
            {
                "report_support_restriction",
                "common_support_record_replacement",
                "publication_support_extension",
            },
        )
        self.assertTrue(
            all("bh_adjusted_p_value" in row for row in decomposition)
        )
        self.assertEqual(
            bundle["multiplicity_control"]["secondary_member_count"], 28
        )
        exposure = bundle["publication_exposure_diagnostics"]
        self.assertFalse(exposure["uses_forward_returns"])
        self.assertEqual(exposure["monthly_observation_count"], 6)
        self.assertEqual(exposure["total_report_signal_count"], 7200)
        self.assertAlmostEqual(exposure["weighted_premature_report_record_share"], 0.75)

    def test_registered_bundle_rejects_timing_total_that_differs_from_primary_monthly_contrast(self) -> None:
        plan = _stage2_plan()
        observations = []
        for variant in plan["variants"]:
            for factor in plan["factors"]:
                row = {
                    "date": "2025-01-03",
                    "variant": variant["id"],
                    "factor": factor,
                    "ic": 0.01,
                }
                if variant["id"] == "A1" and factor == "roe":
                    row["ic"] = 0.04
                if variant["id"] == "I0000" and factor == "roe":
                    row["ic"] = 0.02
                    row["publication_exposure"] = _publication_exposure("2025-01-03")
                    row["timing_decomposition"] = {
                        "report_support_restriction": -0.005,
                        "common_support_record_replacement": -0.010,
                        "publication_support_extension": 0.005,
                        "total_timing_difference": -0.010,
                        "efficiency_residual": 0.0,
                        "u_r_count": 1200,
                        "u_p_count": 1100,
                        "intersection_count": 1050,
                    }
                observations.append(row)

        with self.assertRaisesRegex(
            Stage2EstimandError,
            "primary monthly contrast",
        ):
            build_registered_estimands(
                observations,
                plan=plan,
                nw_lag=0,
                minimum_claim_months=1,
            )

    def test_registered_bundle_rejects_publication_exposure_that_uses_returns(self) -> None:
        plan = _stage2_plan()
        observations = []
        for variant in plan["variants"]:
            for factor in plan["factors"]:
                row = {
                    "date": "2025-01-03",
                    "variant": variant["id"],
                    "factor": factor,
                    "ic": 0.01,
                }
                if variant["id"] == "I0000" and factor == "roe":
                    row["publication_exposure"] = _publication_exposure("2025-01-03")
                    row["publication_exposure"]["uses_forward_returns"] = True
                    row["timing_decomposition"] = {
                        "report_support_restriction": 0.0,
                        "common_support_record_replacement": 0.0,
                        "publication_support_extension": 0.0,
                        "total_timing_difference": 0.0,
                        "efficiency_residual": 0.0,
                        "u_r_count": 1200,
                        "u_p_count": 1100,
                        "intersection_count": 1050,
                    }
                observations.append(row)

        with self.assertRaisesRegex(Stage2EstimandError, "must not use forward returns"):
            build_registered_estimands(
                observations,
                plan=plan,
                nw_lag=0,
                minimum_claim_months=1,
            )

    def test_publication_exposure_requires_every_i0000_roe_month(self) -> None:
        plan = _stage2_plan()
        observations = _complete_registered_observations(
            plan,
            ("2025-01-03", "2025-02-03"),
        )
        target = next(
            row
            for row in observations
            if row["date"] == "2025-02-03"
            and row["variant"] == "I0000"
            and row["factor"] == "roe"
        )
        target.pop("publication_exposure")

        with self.assertRaisesRegex(
            Stage2EstimandError,
            "publication exposure diagnostic date coverage",
        ):
            build_registered_estimands(
                observations,
                plan=plan,
                nw_lag=0,
                minimum_claim_months=1,
            )

    def test_publication_exposure_rejects_wrong_cell_and_duplicate_month(self) -> None:
        plan = _stage2_plan()
        for destination_variant, destination_factor in (
            ("I0001", "roe"),
            ("I0000", "momentum_60d"),
        ):
            with self.subTest(
                variant=destination_variant,
                factor=destination_factor,
            ):
                observations = _complete_registered_observations(
                    plan,
                    ("2025-01-03",),
                )
                source = next(
                    row
                    for row in observations
                    if row["variant"] == "I0000" and row["factor"] == "roe"
                )
                diagnostic = source.pop("publication_exposure")
                destination = next(
                    row
                    for row in observations
                    if row["variant"] == destination_variant
                    and row["factor"] == destination_factor
                )
                destination["publication_exposure"] = diagnostic

                with self.assertRaisesRegex(
                    Stage2EstimandError,
                    "registered publication-date ROE cell",
                ):
                    build_registered_estimands(
                        observations,
                        plan=plan,
                        nw_lag=0,
                        minimum_claim_months=1,
                    )

        observations = _complete_registered_observations(
            plan,
            ("2025-01-03",),
        )
        duplicate = copy.deepcopy(next(
            row
            for row in observations
            if row["variant"] == "I0000" and row["factor"] == "roe"
        ))
        observations.append(duplicate)
        with self.assertRaisesRegex(Stage2EstimandError, "duplicate"):
            build_registered_estimands(
                observations,
                plan=plan,
                nw_lag=0,
                minimum_claim_months=1,
            )

    def test_timing_decomposition_requires_every_finite_primary_intersection_month(self) -> None:
        plan = _stage2_plan()
        observations = _complete_registered_observations(
            plan,
            ("2025-01-03", "2025-02-03"),
        )
        target = next(
            row
            for row in observations
            if row["date"] == "2025-02-03"
            and row["variant"] == "I0000"
            and row["factor"] == "roe"
        )
        target.pop("timing_decomposition")

        with self.assertRaisesRegex(
            Stage2EstimandError,
            "timing decomposition diagnostic date coverage",
        ):
            build_registered_estimands(
                observations,
                plan=plan,
                nw_lag=0,
                minimum_claim_months=1,
            )

    def test_timing_decomposition_must_be_attached_to_i0000_roe(self) -> None:
        plan = _stage2_plan()
        for destination_variant, destination_factor in (
            ("A1", "roe"),
            ("I0000", "momentum_60d"),
        ):
            with self.subTest(
                variant=destination_variant,
                factor=destination_factor,
            ):
                observations = _complete_registered_observations(
                    plan,
                    ("2025-01-03",),
                )
                publication_row = next(
                    row
                    for row in observations
                    if row["variant"] == "I0000" and row["factor"] == "roe"
                )
                diagnostic = publication_row.pop("timing_decomposition")
                destination = next(
                    row
                    for row in observations
                    if row["variant"] == destination_variant
                    and row["factor"] == destination_factor
                )
                destination["timing_decomposition"] = diagnostic

                with self.assertRaisesRegex(
                    Stage2EstimandError,
                    "registered publication-date ROE cell",
                ):
                    build_registered_estimands(
                        observations,
                        plan=plan,
                        nw_lag=0,
                        minimum_claim_months=1,
                    )

    def test_timing_decomposition_allows_only_nonestimable_months_to_be_absent(self) -> None:
        plan = _stage2_plan()
        observations = _complete_registered_observations(
            plan,
            ("2025-01-03", "2025-02-03"),
        )
        for row in observations:
            if (
                row["date"] == "2025-02-03"
                and row["factor"] == "roe"
                and row["variant"] in {"A1", "I0000"}
            ):
                row["ic"] = None
            if (
                row["date"] == "2025-02-03"
                and row["variant"] == "I0000"
                and row["factor"] == "roe"
            ):
                row.pop("timing_decomposition")

        bundle = build_registered_estimands(
            observations,
            plan=plan,
            nw_lag=0,
            minimum_claim_months=1,
        )

        exposure = bundle["publication_exposure_diagnostics"]
        self.assertEqual(exposure.get("expected_monthly_observation_count"), 2)
        self.assertEqual(exposure.get("observed_monthly_diagnostic_count"), 2)
        timing = bundle["timing_decomposition_diagnostics"]
        self.assertEqual(timing.get("expected_monthly_observation_count"), 1)
        self.assertEqual(timing.get("observed_monthly_diagnostic_count"), 1)
        self.assertEqual(
            [row["date"] for row in timing["monthly_diagnostics"]],
            ["2025-01-03"],
        )

    def test_timing_decomposition_rejects_nonestimable_extra_and_duplicate_months(self) -> None:
        plan = _stage2_plan()
        observations = _complete_registered_observations(
            plan,
            ("2025-01-03", "2025-02-03"),
        )
        for row in observations:
            if (
                row["date"] == "2025-02-03"
                and row["variant"] == "I0000"
                and row["factor"] == "roe"
            ):
                row["ic"] = None
        with self.assertRaisesRegex(
            Stage2EstimandError,
            "finite primary intersection",
        ):
            build_registered_estimands(
                observations,
                plan=plan,
                nw_lag=0,
                minimum_claim_months=1,
            )

        observations = _complete_registered_observations(
            plan,
            ("2025-01-03",),
        )
        duplicate = copy.deepcopy(next(
            row
            for row in observations
            if row["variant"] == "I0000" and row["factor"] == "roe"
        ))
        observations.append(duplicate)
        with self.assertRaisesRegex(Stage2EstimandError, "duplicate"):
            build_registered_estimands(
                observations,
                plan=plan,
                nw_lag=0,
                minimum_claim_months=1,
            )

    def test_verifier_rejects_tampered_diagnostic_coverage_counts(self) -> None:
        plan = _stage2_plan()
        bundle = build_registered_estimands(
            _complete_registered_observations(plan, ("2025-01-03",)),
            plan=plan,
            nw_lag=0,
            minimum_claim_months=1,
        )
        for diagnostic_name in (
            "publication_exposure_diagnostics",
            "timing_decomposition_diagnostics",
        ):
            for count_field in (
                "expected_monthly_observation_count",
                "observed_monthly_diagnostic_count",
            ):
                with self.subTest(
                    diagnostic=diagnostic_name,
                    count_field=count_field,
                ):
                    tampered = copy.deepcopy(bundle)
                    tampered[diagnostic_name][count_field] = 2
                    with self.assertRaisesRegex(Stage2EstimandError, "incomplete"):
                        verify_registered_estimands(
                            tampered,
                            factors=plan["factors"],
                        )

    def test_nonestimable_registered_cells_remain_reported_as_non_rejections(self) -> None:
        plan = _stage2_plan()
        observations = []
        for variant in plan["variants"]:
            for factor in plan["factors"]:
                row = {
                    "date": "2025-01-03",
                    "variant": variant["id"],
                    "factor": factor,
                    "ic": None,
                }
                if variant["id"] == "I0000" and factor == "roe":
                    row["publication_exposure"] = _publication_exposure("2025-01-03")
                observations.append(row)

        bundle = build_registered_estimands(
            observations,
            plan=plan,
            nw_lag=0,
            minimum_claim_months=1,
        )

        self.assertEqual(bundle["primary_family"][0]["paired_observation_count"], 0)
        self.assertFalse(bundle["primary_family"][0]["claim_eligible"])
        self.assertEqual(
            bundle["timing_decomposition_diagnostics"]["monthly_observation_count"],
            0,
        )
        self.assertEqual(bundle["multiplicity_control"]["secondary_member_count"], 28)
        self.assertTrue(
            all(
                row["bh_adjusted_p_value"] is None
                and row["reject_at_fdr_0_10"] is False
                for row in bundle["secondary_timing_decomposition_ic"]
            )
        )


def _publication_exposure(day: str) -> dict[str, object]:
    return {
        "schema_version": "stage2_publication_exposure_month_v1",
        "uses_forward_returns": False,
        "date": day,
        "report_signal_count": 1200,
        "publication_signal_count": 1100,
        "common_signal_count": 1050,
        "report_only_count": 150,
        "publication_only_count": 50,
        "premature_report_record_count": 900,
        "premature_report_record_share": 0.75,
        "changed_report_period_count": 840,
        "changed_report_period_share": 0.8,
        "missing_recorded_publish_date_count": 0,
        "reporting_delay_calendar_days": {
            "count": 1200,
            "mean": 91.0,
            "median": 90.0,
            "p25": 60.0,
            "p75": 120.0,
            "maximum": 180.0,
        },
    }


def _complete_registered_observations(
    plan: dict[str, object],
    days: tuple[str, ...],
) -> list[dict[str, object]]:
    observations: list[dict[str, object]] = []
    for day in days:
        for variant in plan["variants"]:
            for factor in plan["factors"]:
                row: dict[str, object] = {
                    "date": day,
                    "variant": variant["id"],
                    "factor": factor,
                    "ic": 0.01,
                }
                if variant["id"] == "A1" and factor == "roe":
                    row["ic"] = 0.04
                if variant["id"] == "I0000" and factor == "roe":
                    row["ic"] = 0.02
                    row["publication_exposure"] = _publication_exposure(day)
                    row["timing_decomposition"] = {
                        "report_support_restriction": -0.005,
                        "common_support_record_replacement": -0.010,
                        "publication_support_extension": -0.005,
                        "total_timing_difference": -0.020,
                        "efficiency_residual": 0.0,
                        "u_r_count": 1200,
                        "u_p_count": 1100,
                        "intersection_count": 1050,
                    }
                observations.append(row)
    return observations


def _stage2_plan() -> dict[str, object]:
    variants: list[dict[str, object]] = [
        {
            "id": "A0",
            "universe_mode": "final_survivor",
            "fundamental_availability": "report_period_end",
            "components": [],
        },
        {
            "id": "A1",
            "universe_mode": "point_in_time",
            "fundamental_availability": "report_period_end",
            "components": [],
        },
    ]
    for mask in range(16):
        variants.append({
            "id": f"I{mask:04b}",
            "universe_mode": "point_in_time",
            "fundamental_availability": "publication_date",
            "components": [
                component
                for index, component in enumerate(STAGE2_COMPONENTS)
                if mask & (1 << index)
            ],
        })
    return {
        "schema_version": STAGE2_SCHEMA_VERSION,
        "status": "locked",
        "factors": ["roe", "momentum_60d", "low_vol_20d", "composite"],
        "inference": {
            "timing_isolation_absolute_tolerance": 1e-12,
            "timing_decomposition": {"efficiency_absolute_tolerance": 1e-12},
        },
        "variants": variants,
    }


if __name__ == "__main__":
    unittest.main()
