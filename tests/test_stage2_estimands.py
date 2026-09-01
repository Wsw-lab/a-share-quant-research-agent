from __future__ import annotations

import unittest

from a_share_quant_agent.confirmatory_study import (
    STAGE2_COMPONENTS,
    STAGE2_SCHEMA_VERSION,
)
from a_share_quant_agent.stage2_estimands import (
    benjamini_hochberg_adjust,
    exact_monthly_shapley,
    holm_adjust,
    paired_variant_difference,
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
        "variants": variants,
    }


if __name__ == "__main__":
    unittest.main()
