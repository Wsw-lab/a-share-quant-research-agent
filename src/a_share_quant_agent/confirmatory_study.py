"""Locked, all-results-reported historical factor study.

The maintained synthetic experiment proves execution contracts. This module
serves a different purpose: after registration and authorization gates pass, it
runs one hash-bound factor study on locally licensed market data without
committing the raw data. The receipt never promotes statistics to a trading
claim.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import subprocess
import tempfile
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

import numpy as np
import pandas as pd


SCHEMA_VERSION = "confirmatory_factor_study_v1"
RECEIPT_SCHEMA_VERSION = "confirmatory_study_receipt_v1"
STAGE2_SCHEMA_VERSION = "confirmatory_factor_study_v2"
STAGE2_RECEIPT_SCHEMA_VERSION = "confirmatory_study_receipt_v2"
STAGE2_ENDPOINT_LEDGER_SCHEMA_VERSION = "stage2_endpoint_reason_ledger_v1"
STAGE2_ENDPOINT_LEDGER_FILENAME = "endpoint_reason_ledger.private.json"
STAGE2_RESOLVED_ENDPOINT_CODE = "EXACT_OFFICIAL_SESSION_ADJUSTED_CLOSE"
STAGE2_COMPONENTS = (
    "exclude_st",
    "exclude_suspended",
    "minimum_amount_20d",
    "one_session_lag",
)
EXPECTED_VARIANTS = (
    "M0_naive",
    "M1_pit_universe",
    "M2_pit_publication",
    "M3_audited_lag",
)
EXPECTED_FACTORS = ("roe", "momentum_60d", "low_vol_20d", "composite")
STAGE2_STUDY_ID = "a-share-factor-timing-bias-decomposition-v2"
STAGE2_TRAIN_PERIOD = ("2009-01-01", "2009-12-31")
STAGE2_TEST_PERIOD = ("2010-01-01", "2022-12-31")
STAGE2_FORWARD_HORIZON_SESSIONS = 20
STAGE2_MINIMUM_AMOUNT = 5_000_000.0
STAGE2_MINIMUM_SYMBOLS = 1000
STAGE2_MINIMUM_REBALANCES = 156
STAGE2_MINIMUM_SIGNIFICANCE_MONTHS = 120
STAGE2_NEWEY_WEST_LAG = 3
STAGE2_RUNTIME_CONTRACT = {
    "python_version": "3.12.12",
    "numpy_version": "2.0.2",
    "pandas_version": "2.3.3",
    "dependency_match_rule": "exact",
    "whole_repository_clean_required": True,
}
STAGE2_COMPOSITE_WEIGHTS = {
    "roe": 0.5,
    "momentum_60d": 0.3,
    "low_vol_20d": 0.2,
}
STAGE2_VARIANT_IDS_BY_MASK = {
    0: "I0000_pit_publication",
    1: "I1000_st",
    2: "I0100_suspension",
    3: "I1100_st_suspension",
    4: "I0010_liquidity",
    5: "I1010_st_liquidity",
    6: "I0110_suspension_liquidity",
    7: "I1110_st_suspension_liquidity",
    8: "I0001_lag",
    9: "I1001_st_lag",
    10: "I0101_suspension_lag",
    11: "I1101_st_suspension_lag",
    12: "I0011_liquidity_lag",
    13: "I1011_st_liquidity_lag",
    14: "I0111_suspension_liquidity_lag",
    15: "I1111_full_implementation",
}
# Freeze the draft protocol's human-readable order: baseline, singleton,
# pairwise, three-component, then full implementation cells.
STAGE2_VARIANT_MASK_ORDER = (
    0, 1, 2, 4, 8, 3, 5, 9, 6, 10, 12, 7, 11, 13, 14, 15,
)
STAGE2_FUNDAMENTAL_CONTRACT = {
    "roe_source_field": "roeDiluted",
    "normalized_field": "roe",
    "unit": "decimal",
    "maximum_staleness_months": 18,
    "same_day_publication_usable": False,
    "duplicate_symbol_report_period_rule": "fail_closed",
}
STAGE2_IC_OUTCOME_CLOCK = {
    "no_lag": "adjusted close t to adjusted close t+20 on official exchange sessions",
    "one_session_lag": "adjusted close t+1 to adjusted close t+21 on official exchange sessions",
    "missing_symbol_session_rule": (
        "cell_non_estimable_do_not_shift_carry_forward_or_assign_default_recovery"
    ),
}
STAGE2_UNRESOLVED_ENDPOINT_CODES = (
    "MISSING_EXACT_FORWARD_EXIT",
    "MISSING_EXACT_LAG_ENTRY",
    "MISSING_EXACT_LAG_EXIT",
)
STAGE2_ENDPOINT_RESOLUTION_CONTRACT = {
    "signal_eligible_denominator_fixed_before_outcome_lookup": True,
    "current_supported_method": (
        "exact_adjusted_close_quote_on_each_required_official_session_only"
    ),
    "required_sessions": {
        "no_lag": ["t", "t+20"],
        "one_session_lag": ["t+1", "t+21"],
    },
    "maximum_unresolved_required_endpoints_per_cell": 0,
    "unresolved_rule": "cell_non_estimable_and_global_insufficient_evidence",
    "forbidden_fallbacks": [
        "next_observed_quote",
        "post_endpoint_reopening_quote",
        "unattested_last_price_carry_forward",
        "zero_or_other_default_recovery",
    ],
    "unimplemented_adapters": [
        "calendarized_suspension_valuation",
        "delisting_or_terminal_wealth",
    ],
    "unresolved_reason_codes": list(STAGE2_UNRESOLVED_ENDPOINT_CODES),
    "receipt_contract": (
        "Record aggregate endpoint reason-code counts, bind the complete private "
        "per-security endpoint-reason ledger by SHA-256, and assert exact coverage "
        "of every signal-eligible security-month-factor-variant record."
    ),
}
STAGE2_INFERENCE_CONTRACT = {
    "primary_estimand": "P1_roe_publication_signed_decrement",
    "primary_directional_prediction": "mean_less_than_zero",
    "reported_null_hypothesis": "two_sided_mean_equals_zero",
    "primary_multiplicity": "none_single_primary",
    "confidence_level": 0.95,
    "secondary_family_member_count": 28,
    "secondary_fdr": 0.1,
    "timing_isolation_absolute_tolerance": 1e-12,
    "timing_decomposition": {
        "efficiency_absolute_tolerance": 1e-12,
    },
    "missing_family_member_rule": "retain_in_denominator_and_treat_as_non_rejection",
}
STAGE2_MISSINGNESS_CONTRACT = {
    "signal_imputation": "none",
    "composite_complete_case": True,
    "all_registered_monthly_cells_required_for_evidence_status": True,
    "aggregate_signal_missingness_counts_required": True,
    "aggregate_common_support_counts_required": True,
    "endpoint_reason_code_for_every_signal_eligible_record_required": True,
    "outcome_availability_must_not_shrink_signal_eligible_denominator": True,
}
STAGE2_PORTFOLIO_CONTRACT = {
    "status": "planned_unimplemented_excluded_from_this_runner",
    "required_before_claims": "separate externally registered and tested execution plan",
}
STAGE2_PLANNED_EXCLUDED_MODULES = (
    "full_per_security_signal_missingness_and_non_endpoint_exclusion_audit",
    "eligible_universe_loss_attribution_beyond_registered_support_counts",
    "percentage_attenuation_output",
    "raw_ratio_regressions",
    "robustness_analyses",
    "structured_deviation_log_and_receipt_reporting",
    "formal_interaction_tests",
    "stationary_bootstrap_intervals",
    "next_open_portfolios",
    "transaction_costs",
    "turnover",
    "nonfills",
    "announcement_event_or_return_timing_study",
)
STAGE2_REGISTRATION_SEMANTICS = {
    "plan_core_rule": (
        "Before registration set status to locked, materialize every fixed field and "
        "variant, set design_frozen_at, and hash the plan after excluding only "
        "external_registration and locked_at."
    ),
    "manifest_rule": (
        "stage2_design_manifest_v1 binds that plan-core hash and the exact research "
        "and input artifacts."
    ),
    "envelope_rule": (
        "After receipt verification and execution authorization, populate "
        "external_registration and set locked_at equal to authorized_at. The final "
        "envelope is not part of the previously frozen plan-core hash."
    ),
    "non_circularity_rule": (
        "The manifest has no self-hash or later-artifact hash; the receipt points "
        "backward to the manifest; the authorization points backward to the manifest, "
        "receipt, and plan core; the final plan envelope records their hashes only "
        "after authorization."
    ),
}
STAGE2_OFFICIAL_CALENDAR_CONTRACT = {
    "schema_version": "stage2_official_calendar_csv_v1",
    "schema_path": "official_calendar/calendar.schema.json",
    "format": (
        "UTF-8 CSV with one date column and one common SSE/SZSE official open session "
        "per row"
    ),
    "timezone": "Asia/Shanghai",
    "required_first_month": "2009-01",
    "required_last_month": "2023-01",
    "session_rule": (
        "every_row_is_a_common_session_on_which_both_sse_and_szse_are_officially_open"
    ),
    "input_hash_rule": (
        "official_calendar_sha256 is SHA-256 of the exact input bytes; no "
        "normalization after design freeze"
    ),
}
STAGE2_PLANNED_EXCLUDED_CONTRACT = {
    "status": "planned_unimplemented_excluded_from_this_runner",
    "items": list(STAGE2_PLANNED_EXCLUDED_MODULES),
    "shapley_boundary": (
        "Exact four-component Shapley allocation preserves interactions but does not "
        "implement formal interaction tests."
    ),
}
STAGE2_DEVIATION_REPORTING_CONTRACT = {
    "status": "planned_unimplemented_excluded_from_this_runner",
    "current_boundary": (
        "The protocol requires manual disclosure, but the current runner and receipt "
        "do not create, bind, or verify a structured deviation log."
    ),
}
STAGE2_VARIANTS_SOURCE = (
    "Before design-manifest registration, copy the exact 18 variants from "
    "plan.draft.json, freeze their order in the plan core, and do not add, delete, "
    "or rename cells after design_frozen_at."
)
STAGE2_ROE_TIMING_COMMON_SUPPORT_DECOMPOSITION = {
    "supports": {
        "R_t": (
            "A1 finite report-period ROE support after non-outcome eligibility rules "
            "and successful endpoint resolution"
        ),
        "P_t": (
            "I0000 finite recorded-publication-date ROE support after non-outcome "
            "eligibility rules and successful endpoint resolution"
        ),
        "C_t": "intersection of R_t and P_t; supports may be non-nested",
    },
    "components": [
        {
            "id": "S_roe_report_side_support_restriction",
            "definition": "IC_R(C_t)-IC_R(R_t)",
            "test": "two_sided_secondary_bh28",
        },
        {
            "id": "S_roe_within_common_support_record_replacement",
            "definition": "IC_P(C_t)-IC_R(C_t)",
            "test": "two_sided_secondary_bh28",
        },
        {
            "id": "S_roe_publication_side_support_extension",
            "definition": "IC_P(P_t)-IC_P(C_t)",
            "test": "two_sided_secondary_bh28",
        },
    ],
    "rank_rule": (
        "Recompute both signal and outcome ranks inside the support named by each IC term."
    ),
    "monthly_identity": (
        "IC_P(P_t)-IC_R(R_t)=report_side_support_restriction+"
        "within_common_support_record_replacement+publication_side_support_extension"
    ),
    "efficiency_tolerance_source": (
        "inference.timing_decomposition.efficiency_absolute_tolerance"
    ),
    "efficiency_failure_rule": (
        "absolute identity residual above the registered efficiency tolerance "
        "invalidates the run"
    ),
    "interpretation_boundary": (
        "ordered arithmetic decomposition only; no causal, revision, or vintage "
        "interpretation"
    ),
}
STAGE2_PUBLICATION_EXPOSURE_DIAGNOSTICS = {
    "uses_forward_returns": False,
    "inference": "descriptive_only_outside_bh_family",
    "outputs": [
        "R_t_P_t_C_t_report_only_and_publication_only_counts_by_month",
        "share_of_report_side_selected_records_not_yet_recorded_as_published_at_signal_date",
        "share_of_common_support_records_with_different_selected_report_periods",
        "report_period_end_to_recorded_publish_date_calendar_day_distribution",
    ],
}
STAGE2_CLAIM_BOUNDARIES = {
    "authorized_accounting_timing_claim": (
        "recorded-publication-date specification effect in a single-version provider snapshot"
    ),
    "revision_or_vintage_claim": False,
    "historical_investor_observed_value_claim": False,
    "announcement_reaction_or_return_timing_claim": False,
    "portfolio_or_trading_claim": False,
}
STAGE2_COVERAGE_PROBE_SPEC_PATH = "coverage_probe_spec.v2.json"
STAGE2_COVERAGE_PROBE_RECEIPT_PATH = "coverage_probe_receipt.v2.json"
STAGE2_COVERAGE_PROBE_PRIOR_INVENTORY_PATH = "prior_specification_inventory.json"
STAGE2_COVERAGE_PROBE_SPEC_SCHEMA_VERSION = "stage2_coverage_probe_spec_v2"
STAGE2_COVERAGE_PROBE_RECEIPT_SCHEMA_VERSION = "stage2_coverage_probe_receipt_v2"
STAGE2_COVERAGE_PROBE_ID = "stage2-akshare-raw-coverage-2016-2018-v2"
STAGE2_COVERAGE_PROBE_DATES = ["2016-06-30", "2018-06-29"]
STAGE2_COVERAGE_PROBE_SYMBOLS = [
    "600601.SH",
    "600602.SH",
    "000002.SZ",
    "000001.SZ",
    "600831.SH",
    "603077.SH",
    "000908.SZ",
    "002380.SZ",
    "600093.SH",
    "600146.SH",
    "002504.SZ",
    "300367.SZ",
]
STAGE2_COVERAGE_PROBE_PROVIDER_ADAPTER = (
    "qdata.sources.providers.akshare_provider.AkShareProvider"
)
STAGE2_COVERAGE_PROBE_PROVIDER_INTERFACE = "akshare.stock_zh_a_hist"
STAGE2_COVERAGE_PROBE_PRICE_MODE = "raw_unadjusted"
STAGE2_COVERAGE_PROBE_ADJUST_ARGUMENT = ""
STAGE2_COVERAGE_PROBE_QDATA_COMMIT = "19b2dd1df8cfbe875809179a4772e4656dce01bd"
STAGE2_COVERAGE_PROBE_PYTHON_VERSION = "3.12.12"
STAGE2_COVERAGE_PROBE_AKSHARE_VERSION = "1.18.81"
STAGE2_COVERAGE_PROBE_REPOSITORY_PATH = (
    "studies/pit_factor_bias_decomposition_v2/coverage_probe_spec.v2.json"
)
STAGE2_COVERAGE_PROBE_INVENTORY_REPOSITORY_PATH = (
    "studies/pit_factor_bias_decomposition_v2/prior_specification_inventory.json"
)
STAGE2_COVERAGE_PROBE_AGENT_COMMIT_RULE = (
    "The public receipt must name an existing Git commit whose "
    "studies/pit_factor_bias_decomposition_v2/coverage_probe_spec.v2.json blob "
    "exactly equals these timestamped bytes."
)
STAGE2_COVERAGE_PROBE_V1_SUPERSEDES = {
    "path": "coverage_probe_spec.v1.json",
    "sha256": "35e63a90dacd412868345e051031af52801ea91c22e6bd181baa482364d102e8",
    "immutability_rule": (
        "The v1 bytes remain unchanged. This v2 prospectively adds endpoint and "
        "claim boundaries while preserving the locked symbols, dates, provider, "
        "price mode, and quality thresholds."
    ),
}
STAGE2_COVERAGE_PROBE_DESIGN_BOUNDARY = {
    "variants": 18,
    "factor_variant_cells": 72,
    "primary_estimands": 1,
    "secondary_estimands": 28,
    "total_inferential_estimands": 29,
    "roe_common_support_components": 3,
    "timing_decomposition_tolerance_source": (
        "execution_plan.inference.timing_decomposition.efficiency_absolute_tolerance"
    ),
    "endpoint_adapter": "exact_official_session_adjusted_close_only",
    "single_version_claim": "recorded_publication_date_specification_effect_only",
}
STAGE2_COVERAGE_PROBE_REQUIRED_COMMIT_CONTENTS = [
    "studies/pit_factor_bias_decomposition_v2/coverage_probe_spec.v2.json",
    "studies/pit_factor_bias_decomposition_v2/prior_specification_inventory.json",
]
STAGE2_COVERAGE_PROBE_TIMESTAMP_TRUST_BOUNDARY = (
    "The timestamp record has no offline-verifiable signature; authenticity requires "
    "independent human verification."
)
STAGE2_REGISTERED_DESIGN_ASSERTIONS = {
    "variant_count": 18,
    "factor_variant_cell_count": 72,
    "primary_estimand_count": 1,
    "secondary_estimand_count": 28,
    "total_inferential_estimand_count": 29,
    "roe_common_support_component_count": 3,
    "timing_decomposition_tolerance_source": (
        "execution_plan.inference.timing_decomposition.efficiency_absolute_tolerance"
    ),
    "endpoint_resolution_method": "exact_official_session_adjusted_close_only",
    "result_receipt_binds_complete_endpoint_reason_ledger": True,
    "single_version_claim_boundary": (
        "recorded_publication_date_specification_effect_only"
    ),
}
STAGE2_REGISTERED_SCOPE_SUMMARY = {
    "variants": 18,
    "factor_variant_cells": 72,
    "primary_estimands": 1,
    "secondary_estimands": 28,
    "total_inferential_estimands": 29,
    "roe_common_support_components": 3,
    "timing_decomposition_tolerance_source": (
        "design_manifest.registered_design_assertions."
        "timing_decomposition_tolerance_source"
    ),
    "claim_boundary": "single_version_recorded_publication_date_specification_effect_only",
}
STAGE2_AUTHORIZED_CORE_OUTPUTS = [
    "18_variant_72_cell_ic_lattice",
    "one_primary_and_28_secondary_inferential_estimands",
    "three_part_ordered_roe_common_support_decomposition",
    "aggregate_signal_missingness_and_common_support_counts",
    "no_return_publication_exposure_diagnostics",
    "per_security_endpoint_reason_ledger_hash_and_aggregate_receipt_counts",
]
STAGE2_AUTHORIZATION_ENDPOINT_BOUNDARY = (
    "The current core supports exact adjusted-close quotes on required official "
    "sessions only. Any unresolved endpoint makes the cell non-estimable and the "
    "study INSUFFICIENT_EVIDENCE; suspension-valuation and delisting-terminal-wealth "
    "adapters are not authorized."
)
STAGE2_AUTHORIZATION_CLAIM_BOUNDARY = (
    "The strongest authorized accounting-timing claim is a recorded-publication-date "
    "specification effect in a single-version provider snapshot. Revision, vintage-value, "
    "historical-investor-observed-value, announcement-reaction, and return-timing claims "
    "remain unauthorized."
)
STAGE2_REPORTING_RULE = (
    "Report every registered IC cell and exactly 29 inferential estimands (one primary "
    "plus 28 secondary family members), including the three ordered ROE common-support "
    "components, with their efficiency identity at absolute tolerance 1e-12 and two "
    "deterministic timing-isolation checks reported separately. Also report aggregate "
    "signal-missingness/common-support counts and no-return publication-exposure "
    "diagnostics. Cell-level means, Newey-West t-statistics, and top-minus-universe "
    "spreads are descriptive only and cannot support cell-specific discovery claims; "
    "do not select or headline a best result. The result receipt binds the complete "
    "per-security endpoint-reason ledger and verifies signal-eligible-denominator coverage."
)
STAGE2_DEVIATION_RULE = (
    "Record every deviation without replacing the primary analysis; "
    "outcome-aware deviations are exploratory only."
)


class ConfirmatoryStudyError(RuntimeError):
    """Raised when a plan, input, result set, or receipt cannot be trusted."""


@dataclass(frozen=True)
class Stage2VariantSpec:
    """One registered cell in the Stage-2 bias-decomposition design."""

    variant_id: str
    universe_mode: str
    fundamental_availability: str
    components: frozenset[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.variant_id,
            "universe_mode": self.universe_mode,
            "fundamental_availability": self.fundamental_availability,
            "components": [
                component for component in STAGE2_COMPONENTS if component in self.components
            ],
        }


def _expected_stage2_variant_dicts() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = [
        {
            "id": "A0_final_report_end",
            "universe_mode": "final_survivor",
            "fundamental_availability": "report_period_end",
            "components": [],
        },
        {
            "id": "A1_pit_report_end",
            "universe_mode": "point_in_time",
            "fundamental_availability": "report_period_end",
            "components": [],
        },
    ]
    for mask in STAGE2_VARIANT_MASK_ORDER:
        variants.append({
            "id": STAGE2_VARIANT_IDS_BY_MASK[mask],
            "universe_mode": "point_in_time",
            "fundamental_availability": "publication_date",
            "components": [
                component
                for index, component in enumerate(STAGE2_COMPONENTS)
                if mask & (1 << index)
            ],
        })
    return variants


def stage2_registered_content_sha256(plan: Mapping[str, Any]) -> str:
    """Hash the frozen design while excluding the non-circular registration envelope."""

    content = {
        key: value
        for key, value in plan.items()
        if key not in {"external_registration", "locked_at"}
    }
    return _sha256(_canonical_bytes(content))


def validate_stage2_variant_plan(plan: Mapping[str, Any]) -> tuple[Stage2VariantSpec, ...]:
    """Validate and normalize the locked Stage-2 baseline-plus-factorial design."""

    if plan.get("schema_version") != STAGE2_SCHEMA_VERSION:
        raise ConfirmatoryStudyError("unsupported Stage-2 plan schema")
    if plan.get("status") != "locked":
        raise ConfirmatoryStudyError("Stage-2 plan must be locked before data analysis")
    raw_variants = plan.get("variants")
    if not isinstance(raw_variants, list) or not raw_variants:
        raise ConfirmatoryStudyError("Stage-2 variants must be a non-empty list")

    variants: list[Stage2VariantSpec] = []
    ids: set[str] = set()
    for index, raw in enumerate(raw_variants):
        if not isinstance(raw, Mapping):
            raise ConfirmatoryStudyError(f"Stage-2 variant at index {index} must be an object")
        variant_id = raw.get("id")
        if not isinstance(variant_id, str) or not variant_id.strip():
            raise ConfirmatoryStudyError(f"Stage-2 variant at index {index} has an invalid id")
        if variant_id in ids:
            raise ConfirmatoryStudyError(f"duplicate Stage-2 variant id: {variant_id}")
        ids.add(variant_id)
        universe_mode = raw.get("universe_mode")
        if universe_mode not in {"final_survivor", "point_in_time"}:
            raise ConfirmatoryStudyError(
                f"Stage-2 variant {variant_id} has an unsupported universe_mode"
            )
        availability = raw.get("fundamental_availability")
        if availability not in {"report_period_end", "publication_date"}:
            raise ConfirmatoryStudyError(
                f"Stage-2 variant {variant_id} has unsupported fundamental_availability"
            )
        raw_components = raw.get("components")
        if not isinstance(raw_components, list) or not all(
            isinstance(component, str) for component in raw_components
        ):
            raise ConfirmatoryStudyError(
                f"Stage-2 variant {variant_id} components must be a list of strings"
            )
        if len(raw_components) != len(set(raw_components)):
            raise ConfirmatoryStudyError(f"Stage-2 variant {variant_id} repeats a component")
        unknown = sorted(set(raw_components) - set(STAGE2_COMPONENTS))
        if unknown:
            raise ConfirmatoryStudyError(
                f"Stage-2 variant {variant_id} has unknown components: {unknown}"
            )
        variants.append(Stage2VariantSpec(
            variant_id=variant_id,
            universe_mode=str(universe_mode),
            fundamental_availability=str(availability),
            components=frozenset(raw_components),
        ))

    expected_chain = {
        ("final_survivor", "report_period_end", frozenset()),
        ("point_in_time", "report_period_end", frozenset()),
        ("point_in_time", "publication_date", frozenset()),
    }
    actual_semantics = {
        (variant.universe_mode, variant.fundamental_availability, variant.components)
        for variant in variants
    }
    if not expected_chain.issubset(actual_semantics):
        raise ConfirmatoryStudyError(
            "Stage-2 baseline chain must contain final-survivor/report-period-end, "
            "point-in-time/report-period-end, and point-in-time/publication-date cells"
        )

    semantic_keys = [
        (variant.universe_mode, variant.fundamental_availability, variant.components)
        for variant in variants
    ]
    if len(semantic_keys) != len(set(semantic_keys)):
        raise ConfirmatoryStudyError("Stage-2 variants contain duplicate semantic cells")

    expected_factorial = {
        frozenset(
            component
            for component_index, component in enumerate(STAGE2_COMPONENTS)
            if mask & (1 << component_index)
        )
        for mask in range(1 << len(STAGE2_COMPONENTS))
    }
    actual_factorial = {
        variant.components
        for variant in variants
        if variant.universe_mode == "point_in_time"
        and variant.fundamental_availability == "publication_date"
    }
    if actual_factorial != expected_factorial or len(variants) != 18:
        raise ConfirmatoryStudyError(
            "Stage-2 U2 implementation cells must form a complete 2^4 factorial"
        )
    return tuple(variants)


def run_stage2_registered_cells(
    *,
    prepared: pd.DataFrame,
    stock_master: pd.DataFrame,
    fundamentals: pd.DataFrame,
    rebalance_dates: Sequence[pd.Timestamp],
    plan: Mapping[str, Any],
    endpoint_ledger_writer: _Stage2EndpointLedgerWriter | None = None,
) -> list[dict[str, Any]]:
    """Execute every Stage-2 universe/timing/factorial cell without selection."""

    variants = _validate_stage2_plan(plan)
    quote_by_date = {day: rows.copy() for day, rows in prepared.groupby("date", sort=False)}
    observations: list[dict[str, Any]] = []
    for day in rebalance_dates:
        if day not in quote_by_date:
            raise ConfirmatoryStudyError(f"rebalance date is absent from prepared quotes: {day}")
        base = quote_by_date[day].copy()
        cross_sections: dict[str, pd.DataFrame] = {}
        for variant in variants:
            cross_section = _stage2_variant_cross_section(
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
            cross_sections[variant.variant_id] = cross_section

        rows_by_cell: dict[tuple[str, str], dict[str, Any]] = {}
        for variant in sorted(variants, key=lambda item: item.variant_id):
            cross_section = cross_sections[variant.variant_id]
            outcome = (
                "future_return_lagged"
                if "one_session_lag" in variant.components
                else "future_return_same"
            )
            for factor in sorted(plan["factors"]):
                row = _stage2_monthly_cell_observation(
                    cross_section,
                    day=day,
                    variant_id=variant.variant_id,
                    factor=factor,
                    outcome=outcome,
                )
                if endpoint_ledger_writer is not None:
                    endpoint_ledger_writer.add_observation(row)
                observations.append(row)
                rows_by_cell[(variant.variant_id, factor)] = row

        report_variant_id = "A1_pit_report_end"
        publication_variant_id = "I0000_pit_publication"
        rows_by_cell[(publication_variant_id, "roe")][
            "publication_exposure"
        ] = _stage2_publication_exposure(
            report_cross_section=cross_sections[report_variant_id],
            publication_cross_section=cross_sections[publication_variant_id],
            day=day,
        )
        timing_decomposition = _stage2_timing_decomposition(
            report_cross_section=cross_sections[report_variant_id],
            publication_cross_section=cross_sections[publication_variant_id],
            report_observation=rows_by_cell[(report_variant_id, "roe")],
            publication_observation=rows_by_cell[(publication_variant_id, "roe")],
            outcome="future_return_same",
        )
        # A registered component is emitted only when all four supporting ICs
        # are estimable.  Non-estimable months remain visible through their
        # cell values and sample audits instead of being encoded as zero.
        if timing_decomposition["total_timing_difference"] is not None:
            rows_by_cell[(publication_variant_id, "roe")][
                "timing_decomposition"
            ] = timing_decomposition
    return observations


def _stage2_monthly_cell_observation(
    cross_section: pd.DataFrame,
    *,
    day: pd.Timestamp,
    variant_id: str,
    factor: str,
    outcome: str,
) -> dict[str, Any]:
    factor_values = pd.to_numeric(cross_section[factor], errors="coerce")
    outcome_values = pd.to_numeric(cross_section[outcome], errors="coerce")
    signal_mask = factor_values.notna() & np.isfinite(factor_values)
    outcome_mask = outcome_values.notna() & np.isfinite(outcome_values)
    signal_eligible = cross_section.loc[signal_mask].copy()
    signal_eligible["_factor_value"] = factor_values.loc[signal_mask]
    signal_eligible["_outcome_value"] = outcome_values.loc[signal_mask]
    estimable = signal_eligible.loc[outcome_mask.loc[signal_mask]].copy()

    reason_column = f"{outcome}_reason"
    fallback_reason = (
        "MISSING_EXACT_LAG_ENTRY"
        if outcome == "future_return_lagged"
        else "MISSING_EXACT_FORWARD_EXIT"
    )
    endpoint_records: list[dict[str, str]] = []
    for _, row in signal_eligible.sort_values("symbol").iterrows():
        outcome_value = row["_outcome_value"]
        if pd.notna(outcome_value) and np.isfinite(outcome_value):
            resolution_code = STAGE2_RESOLVED_ENDPOINT_CODE
        else:
            raw_reason = row.get(reason_column)
            resolution_code = (
                str(raw_reason)
                if isinstance(raw_reason, str) and raw_reason.strip()
                else fallback_reason
            )
        endpoint_records.append({
            "symbol": str(row["symbol"]),
            "resolution_code": resolution_code,
        })
    unresolved_endpoints = [
        {
            "symbol": row["symbol"],
            "reason_code": row["resolution_code"],
        }
        for row in endpoint_records
        if row["resolution_code"] != STAGE2_RESOLVED_ENDPOINT_CODE
    ]

    sample_audit = {
        "candidate_count": int(len(cross_section)),
        "signal_eligible_count": int(len(signal_eligible)),
        "signal_missing_count": int(len(cross_section) - len(signal_eligible)),
        "estimable_count": int(len(estimable)),
        "unresolved_endpoint_count": int(len(unresolved_endpoints)),
        "unresolved_endpoints": unresolved_endpoints,
        "endpoint_records": endpoint_records,
    }
    if unresolved_endpoints:
        ic = None
        spread = None
    else:
        ic, spread = _stage2_rank_metrics(
            estimable,
            factor_column="_factor_value",
            outcome_column="_outcome_value",
        )
    return {
        "date": day.date().isoformat(),
        "variant": variant_id,
        "factor": factor,
        "ic": _finite_or_none(ic),
        "top_minus_universe": _finite_or_none(spread),
        "cross_section_size": int(len(estimable)),
        "sample_audit": sample_audit,
    }


class _Stage2EndpointLedgerWriter:
    """Stream one canonical private ledger without retaining its records in RAM."""

    _PREFIX = b'{"records":['
    _SUFFIX = (
        b'],"schema_version":'
        + json.dumps(STAGE2_ENDPOINT_LEDGER_SCHEMA_VERSION).encode("ascii")
        + b"}\n"
    )

    def __init__(self, *, directory: Path) -> None:
        self._handle = tempfile.TemporaryFile(mode="w+b", dir=directory)
        self._digest = hashlib.sha256()
        self._record_count = 0
        self._expected_record_count = 0
        self._aggregate_counts: dict[str, int] = {}
        self._previous_key: tuple[str, str, str, str] | None = None
        self._finalized = False
        self._closed = False
        self._write(self._PREFIX)

    def _write(self, payload: bytes) -> None:
        self._handle.write(payload)
        self._digest.update(payload)

    def add_observation(self, observation: Mapping[str, Any]) -> None:
        if self._finalized or self._closed:
            raise ConfirmatoryStudyError("Stage-2 endpoint ledger is already closed")
        audit = observation.get("sample_audit")
        if not isinstance(audit, dict):
            raise ConfirmatoryStudyError(
                "Stage-2 monthly observation is missing its endpoint audit"
            )
        endpoint_records = audit.get("endpoint_records")
        if not isinstance(endpoint_records, list):
            raise ConfirmatoryStudyError(
                "Stage-2 monthly endpoint audit is missing security-level records"
            )
        candidate_count = audit.get("candidate_count")
        signal_eligible_count = audit.get("signal_eligible_count")
        signal_missing_count = audit.get("signal_missing_count")
        estimable_count = audit.get("estimable_count")
        unresolved_count = audit.get("unresolved_endpoint_count")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in (
                candidate_count,
                signal_eligible_count,
                signal_missing_count,
                estimable_count,
                unresolved_count,
            )
        ):
            raise ConfirmatoryStudyError(
                "Stage-2 monthly endpoint audit counts are invalid"
            )
        if (
            signal_eligible_count + signal_missing_count != candidate_count
            or signal_eligible_count > candidate_count
            or len(endpoint_records) != signal_eligible_count
            or estimable_count + unresolved_count != signal_eligible_count
        ):
            raise ConfirmatoryStudyError(
                "Stage-2 endpoint records do not cover the exact signal-eligible denominator"
            )
        date_value = observation.get("date")
        variant = observation.get("variant")
        factor = observation.get("factor")
        if any(
            not isinstance(value, str) or not value
            for value in (date_value, variant, factor)
        ):
            raise ConfirmatoryStudyError(
                "Stage-2 monthly endpoint audit cell identity is invalid"
            )
        self._expected_record_count += signal_eligible_count
        seen_symbols: set[str] = set()
        resolved_count = 0
        allowed_resolution_codes = {
            STAGE2_RESOLVED_ENDPOINT_CODE,
            *STAGE2_UNRESOLVED_ENDPOINT_CODES,
        }
        for endpoint in endpoint_records:
            if not isinstance(endpoint, Mapping):
                raise ConfirmatoryStudyError(
                    "Stage-2 security-level endpoint record is invalid"
                )
            symbol = endpoint.get("symbol")
            resolution_code = endpoint.get("resolution_code")
            if (
                not isinstance(symbol, str)
                or not symbol
                or symbol in seen_symbols
                or not isinstance(resolution_code, str)
                or not resolution_code
                or resolution_code not in allowed_resolution_codes
            ):
                raise ConfirmatoryStudyError(
                    "Stage-2 security-level endpoint record is invalid"
                )
            seen_symbols.add(symbol)
            if resolution_code == STAGE2_RESOLVED_ENDPOINT_CODE:
                resolved_count += 1
            record_key = (date_value, variant, factor, symbol)
            if self._previous_key is not None and record_key <= self._previous_key:
                raise ConfirmatoryStudyError(
                    "Stage-2 endpoint records are not canonically ordered or are duplicated"
                )
            self._previous_key = record_key
            self._aggregate_counts[resolution_code] = (
                self._aggregate_counts.get(resolution_code, 0) + 1
            )
            record = {
                "date": date_value,
                "variant": variant,
                "factor": factor,
                "symbol": symbol,
                "resolution_code": resolution_code,
            }
            if self._record_count:
                self._write(b",")
            self._write(_canonical_bytes(record)[:-1])
            self._record_count += 1
        if (
            resolved_count != estimable_count
            or len(endpoint_records) - resolved_count != unresolved_count
        ):
            raise ConfirmatoryStudyError(
                "Stage-2 endpoint resolution codes differ from the monthly audit"
            )
        audit.pop("unresolved_endpoints", None)
        audit.pop("endpoint_records", None)

    def finalize(self) -> dict[str, Any]:
        if self._closed:
            raise ConfirmatoryStudyError("Stage-2 endpoint ledger is already closed")
        if not self._finalized:
            if self._record_count != self._expected_record_count:
                raise ConfirmatoryStudyError(
                    "Stage-2 endpoint ledger does not cover the exact signal-eligible denominator"
                )
            self._write(self._SUFFIX)
            self._handle.flush()
            self._finalized = True
        return {
            "filename": STAGE2_ENDPOINT_LEDGER_FILENAME,
            "sha256": self._digest.hexdigest(),
            "record_count": self._record_count,
            "aggregate_resolution_code_counts": dict(
                sorted(self._aggregate_counts.items())
            ),
            "exact_denominator_coverage": {
                "assertion": (
                    "one_record_per_signal_eligible_security_date_variant_factor"
                ),
                "expected_record_count": self._expected_record_count,
                "satisfied": self._record_count == self._expected_record_count,
            },
        }

    def copy_to(self, destination: Path) -> None:
        if not self._finalized or self._closed:
            raise ConfirmatoryStudyError("Stage-2 endpoint ledger is not finalized")
        self._handle.seek(0)
        with destination.open("xb") as target:
            for chunk in iter(lambda: self._handle.read(1024 * 1024), b""):
                target.write(chunk)
            target.flush()

    def close(self) -> None:
        if not self._closed:
            self._handle.close()
            self._closed = True


def _sanitize_stage2_monthly_observations(
    observations: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    public_observations: list[dict[str, Any]] = []
    for observation in observations:
        public_observation = dict(observation)
        audit = observation.get("sample_audit")
        if isinstance(audit, Mapping):
            public_audit = dict(audit)
            public_audit.pop("unresolved_endpoints", None)
            public_audit.pop("endpoint_records", None)
            public_observation["sample_audit"] = public_audit
        public_observations.append(public_observation)
    return public_observations


class _BoundedCanonicalJsonReader:
    """Incrementally decode one-line canonical JSON values with a hard buffer cap."""

    _CHUNK_SIZE = 64 * 1024
    _MAX_VALUE_CHARACTERS = 1024 * 1024

    def __init__(self, handle: Any) -> None:
        self._handle = handle
        self._buffer = ""
        self._position = 0
        self._eof = False
        self._decoder = json.JSONDecoder()

    def _available(self) -> int:
        return len(self._buffer) - self._position

    def _compact(self) -> None:
        if self._position >= self._CHUNK_SIZE:
            self._buffer = self._buffer[self._position:]
            self._position = 0

    def _read_more(self) -> bool:
        if self._eof:
            return False
        self._compact()
        chunk = self._handle.read(self._CHUNK_SIZE)
        if not chunk:
            self._eof = True
            return False
        self._buffer += chunk
        return True

    def _ensure(self, count: int) -> bool:
        while self._available() < count and self._read_more():
            pass
        return self._available() >= count

    def consume_exact(self, expected: str) -> None:
        if not self._ensure(len(expected)):
            raise ConfirmatoryStudyError(
                "Stage-2 private endpoint ledger is truncated or not canonical JSON"
            )
        actual = self._buffer[self._position:self._position + len(expected)]
        if actual != expected:
            raise ConfirmatoryStudyError(
                "Stage-2 private endpoint ledger is not canonical JSON"
            )
        self._position += len(expected)
        self._compact()

    def peek(self) -> str | None:
        if not self._ensure(1):
            return None
        return self._buffer[self._position]

    def decode_canonical_value(self) -> Any:
        while True:
            if not self._ensure(1):
                raise ConfirmatoryStudyError(
                    "Stage-2 private endpoint ledger is truncated or not canonical JSON"
                )
            try:
                value, end = self._decoder.raw_decode(
                    self._buffer, idx=self._position
                )
            except json.JSONDecodeError as exc:
                if (
                    self._eof
                    or self._available() >= self._MAX_VALUE_CHARACTERS
                    or not self._read_more()
                ):
                    raise ConfirmatoryStudyError(
                        "Stage-2 private endpoint ledger is not canonical JSON"
                    ) from exc
                continue
            source = self._buffer[self._position:end]
            try:
                canonical = _canonical_bytes(value)[:-1].decode("utf-8")
            except (TypeError, ValueError, UnicodeError) as exc:
                raise ConfirmatoryStudyError(
                    "Stage-2 private endpoint ledger is not canonical JSON"
                ) from exc
            if source != canonical:
                raise ConfirmatoryStudyError(
                    "Stage-2 private endpoint ledger is not canonical JSON"
                )
            self._position = end
            self._compact()
            return value

    def require_eof(self) -> None:
        if self.peek() is not None:
            raise ConfirmatoryStudyError(
                "Stage-2 private endpoint ledger is not canonical JSON"
            )


def _iter_stage2_endpoint_ledger_records(path: Path) -> Iterable[Any]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = _BoundedCanonicalJsonReader(handle)
            reader.consume_exact('{"records":[')
            first = True
            while reader.peek() != "]":
                if not first:
                    reader.consume_exact(",")
                yield reader.decode_canonical_value()
                first = False
            reader.consume_exact(
                '],"schema_version":'
                + json.dumps(STAGE2_ENDPOINT_LEDGER_SCHEMA_VERSION)
                + "}\n"
            )
            reader.require_eof()
    except (OSError, UnicodeError) as exc:
        raise ConfirmatoryStudyError(
            "Stage-2 private endpoint ledger is not valid UTF-8 JSON"
        ) from exc


def _validate_stage2_endpoint_reason_ledger(
    *,
    endpoint_ledger_path: Path | None,
    metadata: Any,
    observations: Sequence[Mapping[str, Any]],
) -> None:
    metadata_keys = {
        "filename",
        "sha256",
        "record_count",
        "aggregate_resolution_code_counts",
        "exact_denominator_coverage",
    }
    if not isinstance(metadata, Mapping) or set(metadata) != metadata_keys:
        raise ConfirmatoryStudyError(
            "Stage-2 receipt private endpoint-ledger metadata is invalid"
        )

    expected_by_cell: dict[tuple[str, str, str], tuple[int, int, int]] = {}
    expected_record_count = 0
    expected_resolved_count = 0
    expected_unresolved_count = 0
    for observation in observations:
        audit = observation.get("sample_audit")
        if not isinstance(audit, Mapping):
            raise ConfirmatoryStudyError(
                "Stage-2 receipt monthly endpoint audit is missing"
            )
        cross_section_size = observation.get("cross_section_size")
        estimable_count = audit.get("estimable_count")
        if (
            isinstance(cross_section_size, bool)
            or not isinstance(cross_section_size, int)
            or cross_section_size < 0
            or isinstance(estimable_count, bool)
            or not isinstance(estimable_count, int)
            or estimable_count < 0
        ):
            raise ConfirmatoryStudyError(
                "Stage-2 receipt monthly endpoint audit counts are invalid"
            )
        if cross_section_size != estimable_count:
            raise ConfirmatoryStudyError(
                "Stage-2 receipt monthly cross-section size differs from sample audit estimable count"
            )
        if "endpoint_records" in audit or "unresolved_endpoints" in audit:
            raise ConfirmatoryStudyError(
                "Stage-2 receipt exposes security-level endpoint records"
            )
        candidate_count = audit.get("candidate_count")
        signal_missing_count = audit.get("signal_missing_count")
        counts = (
            audit.get("signal_eligible_count"),
            audit.get("estimable_count"),
            audit.get("unresolved_endpoint_count"),
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in (*counts, candidate_count, signal_missing_count)
        ):
            raise ConfirmatoryStudyError(
                "Stage-2 receipt monthly endpoint audit counts are invalid"
            )
        signal_eligible, estimable, unresolved = counts
        if (
            estimable + unresolved != signal_eligible
            or signal_eligible + signal_missing_count != candidate_count
        ):
            raise ConfirmatoryStudyError(
                "Stage-2 receipt monthly endpoint audit denominator is inconsistent"
            )
        cell = (
            str(observation.get("date")),
            str(observation.get("variant")),
            str(observation.get("factor")),
        )
        if cell in expected_by_cell:
            raise ConfirmatoryStudyError(
                "Stage-2 receipt monthly endpoint audit contains duplicate cells"
            )
        expected_by_cell[cell] = counts
        expected_record_count += signal_eligible
        expected_resolved_count += estimable
        expected_unresolved_count += unresolved

    record_count = metadata.get("record_count")
    if (
        isinstance(record_count, bool)
        or not isinstance(record_count, int)
        or record_count < 0
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt private endpoint-ledger record count is invalid"
        )
    coverage = metadata.get("exact_denominator_coverage")
    expected_coverage = {
        "assertion": (
            "one_record_per_signal_eligible_security_date_variant_factor"
        ),
        "expected_record_count": expected_record_count,
        "satisfied": True,
    }
    if record_count != expected_record_count or coverage != expected_coverage:
        raise ConfirmatoryStudyError(
            "Stage-2 endpoint ledger fails exact denominator coverage"
        )

    aggregate_counts = metadata.get("aggregate_resolution_code_counts")
    allowed_resolution_codes = {
        STAGE2_RESOLVED_ENDPOINT_CODE,
        *STAGE2_UNRESOLVED_ENDPOINT_CODES,
    }
    if not isinstance(aggregate_counts, Mapping) or any(
        not isinstance(code, str)
        or not code
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count <= 0
        for code, count in aggregate_counts.items()
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 endpoint-ledger aggregate resolution counts are invalid"
        )
    if any(code not in allowed_resolution_codes for code in aggregate_counts):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt contains an unsupported endpoint resolution code"
        )
    if (
        sum(aggregate_counts.values()) != expected_record_count
        or aggregate_counts.get(STAGE2_RESOLVED_ENDPOINT_CODE, 0)
        != expected_resolved_count
        or sum(
            count
            for code, count in aggregate_counts.items()
            if code != STAGE2_RESOLVED_ENDPOINT_CODE
        )
        != expected_unresolved_count
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 endpoint-ledger aggregate resolution counts differ from monthly audits"
        )

    if metadata.get("filename") != STAGE2_ENDPOINT_LEDGER_FILENAME:
        raise ConfirmatoryStudyError(
            "Stage-2 receipt private endpoint-ledger filename is invalid"
        )
    if not _is_sha256(metadata.get("sha256")):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt private endpoint-ledger hash is invalid"
        )
    if endpoint_ledger_path is None:
        return
    ledger_path = Path(endpoint_ledger_path).expanduser().resolve(strict=False)
    if not ledger_path.is_file() or ledger_path.is_symlink():
        raise ConfirmatoryStudyError("Stage-2 private endpoint ledger is missing")
    if _sha256_file(ledger_path) != metadata["sha256"]:
        raise ConfirmatoryStudyError("Stage-2 private endpoint ledger hash mismatch")
    observed_counts: dict[str, int] = {}
    observed_by_cell: dict[tuple[str, str, str], list[int]] = {
        cell: [0, 0, 0] for cell in expected_by_cell
    }
    previous_key: tuple[str, str, str, str] | None = None
    observed_record_count = 0
    for record in _iter_stage2_endpoint_ledger_records(ledger_path):
        if not isinstance(record, Mapping) or set(record) != {
            "date", "variant", "factor", "symbol", "resolution_code",
        }:
            raise ConfirmatoryStudyError(
                "Stage-2 private endpoint ledger contains an invalid record"
            )
        date_value = record.get("date")
        variant = record.get("variant")
        factor = record.get("factor")
        symbol = record.get("symbol")
        resolution_code = record.get("resolution_code")
        if any(
            not isinstance(value, str) or not value
            for value in (date_value, variant, factor, symbol, resolution_code)
        ) or resolution_code not in allowed_resolution_codes:
            raise ConfirmatoryStudyError(
                "Stage-2 private endpoint ledger contains an invalid record"
            )
        cell = (date_value, variant, factor)
        record_key = (*cell, symbol)
        if (
            cell not in expected_by_cell
            or (previous_key is not None and record_key <= previous_key)
        ):
            raise ConfirmatoryStudyError(
                "Stage-2 private endpoint ledger contains a duplicate or unregistered record"
            )
        previous_key = record_key
        observed_record_count += 1
        cell_counts = observed_by_cell[cell]
        cell_counts[0] += 1
        if resolution_code == STAGE2_RESOLVED_ENDPOINT_CODE:
            cell_counts[1] += 1
        else:
            cell_counts[2] += 1
        observed_counts[resolution_code] = observed_counts.get(resolution_code, 0) + 1
    if observed_record_count != record_count:
        raise ConfirmatoryStudyError(
            "Stage-2 private endpoint ledger record count is inconsistent"
        )
    if dict(sorted(observed_counts.items())) != dict(aggregate_counts):
        raise ConfirmatoryStudyError(
            "Stage-2 private endpoint ledger counts differ from receipt aggregates"
        )
    if {
        cell: tuple(counts) for cell, counts in observed_by_cell.items()
    } != expected_by_cell:
        raise ConfirmatoryStudyError(
            "Stage-2 endpoint ledger fails exact denominator coverage"
        )


def _stage2_rank_metrics(
    sample: pd.DataFrame,
    *,
    factor_column: str,
    outcome_column: str,
) -> tuple[float | None, float | None]:
    if len(sample) < 5:
        return None, None
    score = sample[factor_column].rank(pct=True, method="average")
    outcome = sample[outcome_column]
    outcome_rank = outcome.rank(pct=True, method="average")
    ic = (
        score.corr(outcome_rank, method="pearson")
        if score.nunique(dropna=True) > 1 and outcome_rank.nunique(dropna=True) > 1
        else None
    )
    top = outcome.loc[score >= 0.8]
    spread = top.mean() - outcome.mean()
    return _finite_or_none(ic), _finite_or_none(spread)


def _stage2_timing_support(
    cross_section: pd.DataFrame,
    *,
    outcome: str,
) -> pd.DataFrame:
    factor_values = pd.to_numeric(cross_section["roe"], errors="coerce")
    outcome_values = pd.to_numeric(cross_section[outcome], errors="coerce")
    mask = (
        factor_values.notna()
        & np.isfinite(factor_values)
        & outcome_values.notna()
        & np.isfinite(outcome_values)
    )
    columns = [
        "symbol", "selected_report_period_end", "selected_publish_date",
    ]
    support = cross_section.loc[mask, columns].copy()
    support["_factor_value"] = factor_values.loc[mask]
    support["_outcome_value"] = outcome_values.loc[mask]
    return support


def _stage2_signal_support(cross_section: pd.DataFrame) -> pd.DataFrame:
    factor_values = pd.to_numeric(cross_section["roe"], errors="coerce")
    mask = factor_values.notna() & np.isfinite(factor_values)
    columns = [
        "symbol", "selected_report_period_end", "selected_publish_date",
    ]
    support = cross_section.loc[mask, columns].copy()
    support["_factor_value"] = factor_values.loc[mask]
    return support


def _stage2_calendar_day_distribution(values: pd.Series) -> dict[str, Any]:
    finite = pd.to_numeric(values, errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    ).dropna()
    if finite.empty:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "p25": None,
            "p75": None,
            "maximum": None,
        }
    array = finite.to_numpy(dtype=float)
    return {
        "count": int(len(array)),
        "mean": float(np.mean(array)),
        "median": float(np.median(array)),
        "p25": float(np.quantile(array, 0.25)),
        "p75": float(np.quantile(array, 0.75)),
        "maximum": float(np.max(array)),
    }


def _stage2_publication_exposure(
    *,
    report_cross_section: pd.DataFrame,
    publication_cross_section: pd.DataFrame,
    day: pd.Timestamp,
) -> dict[str, Any]:
    """Describe record availability using signals and dates only, never outcomes."""

    report_support = _stage2_signal_support(report_cross_section)
    publication_support = _stage2_signal_support(publication_cross_section)
    common = report_support.merge(
        publication_support,
        on="symbol",
        how="inner",
        suffixes=("_report", "_publication"),
        validate="one_to_one",
    )
    report_symbols = set(report_support["symbol"].astype(str))
    publication_symbols = set(publication_support["symbol"].astype(str))
    report_publish_dates = pd.to_datetime(
        report_support["selected_publish_date"], errors="coerce"
    )
    report_period_ends = pd.to_datetime(
        report_support["selected_report_period_end"], errors="coerce"
    )
    reporting_delay_days = (report_publish_dates - report_period_ends).dt.days
    if (reporting_delay_days.dropna() < 0).any():
        raise ConfirmatoryStudyError(
            "Stage-2 recorded publication date precedes its report period end"
        )
    premature_count = int(report_publish_dates.ge(day).sum())
    common_count = int(len(common))
    changed_count = int(
        common["selected_report_period_end_report"].ne(
            common["selected_report_period_end_publication"]
        ).sum()
    )
    report_count = int(len(report_support))
    return {
        "schema_version": "stage2_publication_exposure_month_v1",
        "uses_forward_returns": False,
        "date": day.date().isoformat(),
        "report_signal_count": report_count,
        "publication_signal_count": int(len(publication_support)),
        "common_signal_count": common_count,
        "report_only_count": int(len(report_symbols - publication_symbols)),
        "publication_only_count": int(len(publication_symbols - report_symbols)),
        "premature_report_record_count": premature_count,
        "premature_report_record_share": (
            float(premature_count / report_count) if report_count else None
        ),
        "changed_report_period_count": changed_count,
        "changed_report_period_share": (
            float(changed_count / common_count) if common_count else None
        ),
        "missing_recorded_publish_date_count": int(report_publish_dates.isna().sum()),
        "reporting_delay_calendar_days": _stage2_calendar_day_distribution(
            reporting_delay_days
        ),
    }


def _stage2_timing_decomposition(
    *,
    report_cross_section: pd.DataFrame,
    publication_cross_section: pd.DataFrame,
    report_observation: Mapping[str, Any],
    publication_observation: Mapping[str, Any],
    outcome: str,
) -> dict[str, Any]:
    report_support = _stage2_timing_support(
        report_cross_section, outcome=outcome
    )
    publication_support = _stage2_timing_support(
        publication_cross_section, outcome=outcome
    )
    common = report_support.merge(
        publication_support,
        on="symbol",
        how="inner",
        suffixes=("_report", "_publication"),
        validate="one_to_one",
    )
    result: dict[str, Any] = {
        "u_r_count": int(len(report_support)),
        "u_p_count": int(len(publication_support)),
        "intersection_count": int(len(common)),
    }
    report_audit = report_observation.get("sample_audit") or {}
    publication_audit = publication_observation.get("sample_audit") or {}
    unresolved = int(report_audit.get("unresolved_endpoint_count", 0)) + int(
        publication_audit.get("unresolved_endpoint_count", 0)
    )
    if unresolved:
        result.update({
            "report_support_restriction": None,
            "common_support_record_replacement": None,
            "publication_support_extension": None,
            "total_timing_difference": None,
            "efficiency_residual": None,
        })
        return result

    report_full_ic, _ = _stage2_rank_metrics(
        report_support,
        factor_column="_factor_value",
        outcome_column="_outcome_value",
    )
    publication_full_ic, _ = _stage2_rank_metrics(
        publication_support,
        factor_column="_factor_value",
        outcome_column="_outcome_value",
    )
    report_common_ic, _ = _stage2_rank_metrics(
        common,
        factor_column="_factor_value_report",
        outcome_column="_outcome_value_report",
    )
    publication_common_ic, _ = _stage2_rank_metrics(
        common,
        factor_column="_factor_value_publication",
        outcome_column="_outcome_value_publication",
    )
    values = (
        report_full_ic,
        publication_full_ic,
        report_common_ic,
        publication_common_ic,
    )
    if any(value is None for value in values):
        result.update({
            "report_support_restriction": None,
            "common_support_record_replacement": None,
            "publication_support_extension": None,
            "total_timing_difference": None,
            "efficiency_residual": None,
        })
        return result

    report_component = float(report_common_ic) - float(report_full_ic)
    replacement_component = float(publication_common_ic) - float(report_common_ic)
    publication_component = float(publication_full_ic) - float(publication_common_ic)
    total = float(publication_full_ic) - float(report_full_ic)
    residual = total - (
        report_component + replacement_component + publication_component
    )
    result.update({
        "report_support_restriction": report_component,
        "common_support_record_replacement": replacement_component,
        "publication_support_extension": publication_component,
        "total_timing_difference": total,
        "efficiency_residual": residual,
    })
    return result


def run_stage2_confirmatory_study(
    *,
    plan_path: str | Path,
    quotes_path: str | Path,
    stock_master_path: str | Path,
    fundamentals_path: str | Path,
    official_calendar_path: str | Path,
    data_declaration_path: str | Path,
    coverage_report_path: str | Path,
    coverage_probe_spec_path: str | Path,
    coverage_probe_receipt_path: str | Path,
    review_attestation_path: str | Path,
    design_manifest_path: str | Path,
    registration_receipt_path: str | Path,
    execution_authorization_path: str | Path,
    protocol_source_path: str | Path,
    statistical_analysis_plan_path: str | Path,
    prior_specification_inventory_path: str | Path,
    prior_exposure_log_path: str | Path,
    prior_exposure_attestation_path: str | Path,
    code_revision: str,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Run the locked Stage-2 decomposition and publish a v2 receipt atomically."""

    plan_path = _regular_file(plan_path, "plan")
    quotes_path = _regular_file(quotes_path, "quotes")
    stock_master_path = _regular_file(stock_master_path, "stock_master")
    fundamentals_path = _regular_file(fundamentals_path, "fundamentals")
    official_calendar_path = _regular_file(
        official_calendar_path, "official exchange calendar"
    )
    declaration_path = _regular_file(data_declaration_path, "data_declaration")
    coverage_path = _regular_file(coverage_report_path, "coverage report")
    coverage_probe_spec_path = _regular_file(
        coverage_probe_spec_path, "coverage probe specification"
    )
    coverage_probe_receipt_path = _regular_file(
        coverage_probe_receipt_path, "coverage probe receipt"
    )
    attestation_path = _regular_file(review_attestation_path, "review attestation")
    design_manifest_path = _regular_file(design_manifest_path, "design manifest")
    registration_receipt_path = _regular_file(
        registration_receipt_path, "external registration receipt"
    )
    execution_authorization_path = _regular_file(
        execution_authorization_path, "execution authorization"
    )
    protocol_source_path = _regular_file(protocol_source_path, "protocol source")
    statistical_analysis_plan_path = _regular_file(
        statistical_analysis_plan_path, "statistical analysis plan"
    )
    prior_specification_inventory_path = _regular_file(
        prior_specification_inventory_path, "prior specification inventory"
    )
    prior_exposure_log_path = _regular_file(
        prior_exposure_log_path, "prior exposure log"
    )
    prior_exposure_attestation_path = _regular_file(
        prior_exposure_attestation_path, "prior exposure attestation"
    )
    output = Path(output_dir).expanduser().resolve(strict=False)
    if output.exists():
        raise ConfirmatoryStudyError(f"output directory already exists: {output}")

    plan_bytes = plan_path.read_bytes()
    plan = _read_json_object(plan_bytes, "plan")
    variants = _validate_stage2_plan(plan)
    coverage_probe_receipt = _validate_stage2_coverage_probe_receipt(
        spec_path=coverage_probe_spec_path,
        receipt_path=coverage_probe_receipt_path,
        expected_study_id=str(plan["study_id"]),
        prior_specification_inventory_path=prior_specification_inventory_path,
    )
    coverage_bytes = coverage_path.read_bytes()
    coverage = _read_json_object(coverage_bytes, "coverage report")
    attestation = _read_json_object(attestation_path.read_bytes(), "review attestation")
    _validate_stage2_data_bindings(
        plan=plan,
        coverage=coverage,
        coverage_bytes=coverage_bytes,
        attestation=attestation,
        quotes_path=quotes_path,
        stock_master_path=stock_master_path,
        fundamentals_path=fundamentals_path,
        official_calendar_path=official_calendar_path,
    )
    declaration_bytes = declaration_path.read_bytes()
    declaration = _read_json_object(declaration_bytes, "data declaration")
    _validate_declaration(declaration)
    _validate_stage2_declaration(declaration)
    if not isinstance(code_revision, str) or not _is_git_sha(code_revision):
        raise ConfirmatoryStudyError("code_revision must be a 40-character Git commit SHA")
    prior_exposure_attestation = _read_json_object(
        prior_exposure_attestation_path.read_bytes(), "prior exposure attestation"
    )
    _validate_stage2_research_bindings(
        plan=plan,
        code_revision=code_revision,
        source_classification=str(declaration["source_classification"]),
        data_declaration_path=declaration_path,
        official_calendar_path=official_calendar_path,
        quotes_path=quotes_path,
        stock_master_path=stock_master_path,
        fundamentals_path=fundamentals_path,
        coverage_report_path=coverage_path,
        coverage_probe_spec_path=coverage_probe_spec_path,
        coverage_probe_receipt_path=coverage_probe_receipt_path,
        review_attestation_path=attestation_path,
        design_manifest_path=design_manifest_path,
        registration_receipt_path=registration_receipt_path,
        execution_authorization_path=execution_authorization_path,
        protocol_source_path=protocol_source_path,
        statistical_analysis_plan_path=statistical_analysis_plan_path,
        prior_specification_inventory_path=prior_specification_inventory_path,
        prior_exposure_log_path=prior_exposure_log_path,
        prior_exposure_attestation_path=prior_exposure_attestation_path,
        prior_exposure_attestation=prior_exposure_attestation,
        review_attestation=attestation,
    )

    quotes = _load_quotes(quotes_path)
    official_calendar = _load_official_calendar(official_calendar_path)
    stock_master = _load_stock_master(stock_master_path)
    fundamentals = _load_stage2_fundamentals(fundamentals_path)
    prepared = _prepare_stage2_quotes(
        quotes,
        official_calendar=official_calendar,
        horizon=int(plan["forward_horizon_sessions"]),
    )
    rebalance_dates = _monthly_rebalance_dates_from_calendar(
        official_calendar,
        str(plan["test_period"][0]),
        str(plan["test_period"][1]),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    endpoint_ledger_writer = _Stage2EndpointLedgerWriter(directory=output.parent)
    try:
        observations = run_stage2_registered_cells(
            prepared=prepared,
            stock_master=stock_master,
            fundamentals=fundamentals,
            rebalance_dates=rebalance_dates,
            plan=plan,
            endpoint_ledger_writer=endpoint_ledger_writer,
        )
        endpoint_ledger_metadata = endpoint_ledger_writer.finalize()
    except Exception:
        endpoint_ledger_writer.close()
        raise
    public_observations = _sanitize_stage2_monthly_observations(observations)
    aggregation_plan = {
        "variants": [variant.variant_id for variant in variants],
        "factors": list(plan["factors"]),
        "newey_west_lag": int(plan["newey_west_lag"]),
    }
    results = _aggregate_results(observations, aggregation_plan)
    expected_result_count = len(variants) * len(plan["factors"])
    if len(results) != expected_result_count:
        raise ConfirmatoryStudyError(
            "Stage-2 registered result set is incomplete: "
            f"expected {expected_result_count}, got {len(results)}"
        )
    status = _stage2_evidence_status(
        declaration=declaration,
        observations=observations,
        plan=plan,
    )
    status["revision_history_claim"] = False
    global_claim_eligible = (
        status["code"]
        == "REAL_MARKET_REGISTERED_HISTORICAL_IC_CORE_STATISTICS"
    )
    from .stage2_estimands import build_registered_estimands

    estimands = build_registered_estimands(
        observations,
        plan=plan,
        nw_lag=int(plan["newey_west_lag"]),
        minimum_claim_months=int(plan["minimum_significance_months"]),
        global_claim_eligible=global_claim_eligible,
    )

    data_files = {
        "plan": _file_evidence(plan_path),
        "quotes": _file_evidence(quotes_path),
        "stock_master": _file_evidence(stock_master_path),
        "fundamentals": _file_evidence(fundamentals_path),
        "official_calendar": _file_evidence(official_calendar_path),
        "data_declaration": _file_evidence(declaration_path),
        "coverage_report": _file_evidence(coverage_path),
        "coverage_probe_spec": _file_evidence(coverage_probe_spec_path),
        "coverage_probe_receipt": _file_evidence(coverage_probe_receipt_path),
        "review_attestation": _file_evidence(attestation_path),
        "design_manifest": _file_evidence(design_manifest_path),
        "registration_receipt": _file_evidence(registration_receipt_path),
        "execution_authorization": _file_evidence(execution_authorization_path),
        "protocol_source": _file_evidence(protocol_source_path),
        "statistical_analysis_plan": _file_evidence(statistical_analysis_plan_path),
        "prior_specification_inventory": _file_evidence(
            prior_specification_inventory_path
        ),
        "prior_exposure_log": _file_evidence(prior_exposure_log_path),
        "prior_exposure_attestation": _file_evidence(
            prior_exposure_attestation_path
        ),
    }
    design_manifest = _read_json_object(
        design_manifest_path.read_bytes(), "design manifest"
    )
    registration_receipt = _read_json_object(
        registration_receipt_path.read_bytes(), "external registration receipt"
    )
    execution_authorization = _read_json_object(
        execution_authorization_path.read_bytes(), "execution authorization"
    )
    coverage_probe_receipt_bytes = coverage_probe_receipt_path.read_bytes()
    coverage_probe_receipt_package = {
        "content": json.loads(json.dumps(coverage_probe_receipt)),
        "source_file_sha256": _sha256(coverage_probe_receipt_bytes),
        "canonical_sha256": _sha256(_canonical_bytes(coverage_probe_receipt)),
    }
    manifest_input_hashes = dict(design_manifest["input_file_sha256"])
    declaration_package = {
        "content": json.loads(json.dumps(declaration)),
        "source_text": declaration_bytes.decode("utf-8"),
        "source_file_sha256": _sha256(declaration_bytes),
        "canonical_sha256": _sha256(_canonical_bytes(declaration)),
        "binding": {
            "plan_data_declaration_sha256": plan["data_declaration_sha256"],
            "coverage_report_sha256": plan["coverage_report_sha256"],
            "design_manifest_sha256": plan["external_registration"][
                "design_manifest_sha256"
            ],
            "manifest_input_file_sha256": manifest_input_hashes,
        },
    }
    session_dates = [day.date().isoformat() for day in official_calendar]
    official_calendar_source_bytes = official_calendar_path.read_bytes()
    official_calendar_evidence = {
        "schema_version": STAGE2_OFFICIAL_CALENDAR_CONTRACT["schema_version"],
        "timezone": STAGE2_OFFICIAL_CALENDAR_CONTRACT["timezone"],
        "source_file_sha256": data_files["official_calendar"]["sha256"],
        "source_text": official_calendar_source_bytes.decode("utf-8"),
        "canonical_session_dates_sha256": _sha256(_canonical_bytes(session_dates)),
        "session_count": len(session_dates),
        "first_session": session_dates[0],
        "last_session": session_dates[-1],
        "session_dates": session_dates,
    }
    receipt: dict[str, Any] = {
        "schema_version": STAGE2_RECEIPT_SCHEMA_VERSION,
        "study_id": str(plan["study_id"]),
        "code": {"agent_git_sha": code_revision.lower()},
        "plan": {
            "content": json.loads(json.dumps(plan)),
            "source_file_sha256": _sha256(plan_bytes),
            "canonical_sha256": _sha256(_canonical_bytes(plan)),
        },
        "registration_evidence": {
            "design_manifest": design_manifest,
            "registration_receipt": registration_receipt,
            "execution_authorization": execution_authorization,
        },
        "data": {
            "classification": declaration["source_classification"],
            "source_name": declaration["source_name"],
            "redistributable": bool(declaration["redistributable"]),
            "price_semantics": declaration["price_semantics"],
            "rights_review": declaration["rights_review"],
            "declaration": declaration_package,
            "coverage_probe_receipt": coverage_probe_receipt_package,
            "official_calendar": official_calendar_evidence,
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
            "rebalance_dates": [day.date().isoformat() for day in rebalance_dates],
            "complete_registered_rebalance_count": int(
                status["complete_registered_rebalance_count"]
            ),
            "forward_horizon_sessions": int(plan["forward_horizon_sessions"]),
        },
        "method": {
            "outcome": (
                "cross-sectional rank IC and top-quintile minus universe forward return"
            ),
            "inference": "Newey-West t-statistic over monthly observations",
            "baseline_chain": {
                "A0_final_report_end": "final-survivor universe; report-period availability",
                "A1_pit_report_end": "point-in-time universe; report-period availability",
                "I0000_pit_publication": (
                    "point-in-time universe; publication-date fundamentals"
                ),
            },
            "implementation_components": {
                "exclude_st": "exclude securities flagged ST on the signal date",
                "exclude_suspended": "exclude securities suspended on the signal date",
                "minimum_amount_20d": "require trailing 20-session mean amount at the locked threshold",
                "one_session_lag": "measure the forward return from the next session",
            },
            "factorial_design": (
                "complete 2^4 implementation-component factorial on "
                "I0000_pit_publication"
            ),
            "runner_scope": (
                "IC core only: rank IC and top-quintile-minus-universe diagnostics; "
                "next-open portfolios, costs, turnover, and nonfills are not implemented here"
            ),
        },
        "endpoint_reason_ledger": endpoint_ledger_metadata,
        "results": results,
        "monthly_observations": public_observations,
        "estimands": estimands,
        "selection_control": {
            "all_registered_results_reported": True,
            "full_factorial_reported": True,
            "best_result_selected": False,
            "expected_result_count": expected_result_count,
            "reported_result_count": len(results),
            "expected_monthly_observation_count": len(rebalance_dates) * expected_result_count,
            "reported_monthly_observation_count": len(public_observations),
        },
        "status": status,
    }
    receipt["receipt_integrity"] = {
        "algorithm": "sha256",
        "scope": "canonical_receipt_without_receipt_integrity",
        "sha256": _sha256(_canonical_bytes(receipt)),
    }
    payload = _canonical_bytes(receipt)
    staging = Path(tempfile.mkdtemp(prefix=".confirmatory-stage2-", dir=output.parent))
    try:
        staged_endpoint_ledger = staging / STAGE2_ENDPOINT_LEDGER_FILENAME
        endpoint_ledger_writer.copy_to(staged_endpoint_ledger)
        staged_receipt = staging / "receipt.json"
        staged_receipt.write_bytes(payload)
        verify_stage2_study_receipt(
            staged_receipt,
            endpoint_ledger_path=staged_endpoint_ledger,
        )
        staging.replace(output)
    except Exception:
        if staging.exists():
            for item in staging.iterdir():
                item.unlink()
            staging.rmdir()
        raise
    finally:
        endpoint_ledger_writer.close()
    return receipt


def verify_stage2_study_receipt(
    path: str | Path,
    *,
    endpoint_ledger_path: str | Path | None = None,
) -> dict[str, Any]:
    """Verify a public v2 receipt, optionally auditing its private endpoint ledger."""

    receipt_path = _regular_file(path, "receipt")
    payload = receipt_path.read_bytes()
    receipt = _read_json_object(payload, "receipt")
    if payload != _canonical_bytes(receipt):
        raise ConfirmatoryStudyError("Stage-2 receipt is not canonical JSON")
    if receipt.get("schema_version") != STAGE2_RECEIPT_SCHEMA_VERSION:
        raise ConfirmatoryStudyError("unsupported Stage-2 receipt schema")
    code = receipt.get("code") or {}
    if not _is_git_sha(code.get("agent_git_sha")):
        raise ConfirmatoryStudyError("Stage-2 receipt is not bound to an Agent Git commit")
    integrity = receipt.get("receipt_integrity")
    if not isinstance(integrity, dict):
        raise ConfirmatoryStudyError("Stage-2 receipt integrity is missing")
    unsigned = dict(receipt)
    unsigned.pop("receipt_integrity", None)
    if integrity.get("sha256") != _sha256(_canonical_bytes(unsigned)):
        raise ConfirmatoryStudyError("Stage-2 receipt integrity mismatch")

    plan_package = receipt.get("plan") or {}
    plan = plan_package.get("content")
    if not isinstance(plan, Mapping):
        raise ConfirmatoryStudyError("Stage-2 receipt does not embed the complete locked plan")
    try:
        variants = _validate_stage2_plan(plan)
    except ConfirmatoryStudyError as exc:
        raise ConfirmatoryStudyError(
            "Stage-2 receipt differs from the exact maintained design"
        ) from exc
    if (
        not _is_sha256(plan_package.get("source_file_sha256"))
        or plan_package.get("canonical_sha256") != _sha256(_canonical_bytes(plan))
    ):
        raise ConfirmatoryStudyError("Stage-2 receipt plan hash is invalid")
    if receipt.get("study_id") != plan["study_id"]:
        raise ConfirmatoryStudyError("Stage-2 receipt study identifier differs from the plan")
    if plan["code_commit"] != code["agent_git_sha"]:
        raise ConfirmatoryStudyError("Stage-2 receipt code binding is inconsistent")
    data = receipt.get("data")
    if not isinstance(data, Mapping):
        raise ConfirmatoryStudyError("Stage-2 receipt data evidence is missing")
    files = data.get("files")
    if not isinstance(files, Mapping):
        raise ConfirmatoryStudyError("Stage-2 receipt file evidence is missing")
    bound_files = {
        "plan": "source_file_sha256",
        "data_declaration": "data_declaration_sha256",
        "official_calendar": "official_calendar_sha256",
        "coverage_report": "coverage_report_sha256",
        "coverage_probe_spec": "coverage_probe_spec_sha256",
        "coverage_probe_receipt": "coverage_probe_receipt_sha256",
        "review_attestation": "review_attestation_sha256",
        "protocol_source": "protocol_source_sha256",
        "statistical_analysis_plan": "statistical_analysis_plan_sha256",
        "prior_specification_inventory": "prior_specification_inventory_sha256",
        "prior_exposure_attestation": "prior_exposure_attestation_sha256",
    }
    if any(
        not isinstance(files.get(label), Mapping)
        or files[label].get("sha256")
        != (plan_package[plan_key] if label == "plan" else plan[plan_key])
        for label, plan_key in bound_files.items()
    ):
        raise ConfirmatoryStudyError("Stage-2 receipt research-artifact bindings are incomplete")
    prior_exposure_log_file = files.get("prior_exposure_log")
    if (
        not isinstance(prior_exposure_log_file, Mapping)
        or not _is_sha256(prior_exposure_log_file.get("sha256"))
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt prior exposure log binding is missing"
        )
    registration = plan["external_registration"]
    registration_file_bindings = {
        "design_manifest": "design_manifest_sha256",
        "registration_receipt": "registration_receipt_sha256",
        "execution_authorization": "execution_authorization_sha256",
    }
    if any(
        not isinstance(files.get(label), Mapping)
        or files[label].get("sha256") != registration[key]
        for label, key in registration_file_bindings.items()
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt registration-artifact bindings are incomplete"
        )
    registration_evidence = receipt.get("registration_evidence")
    if not isinstance(registration_evidence, Mapping):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt embedded registration evidence is missing"
        )
    for label, key in registration_file_bindings.items():
        evidence = registration_evidence.get(label)
        if not isinstance(evidence, Mapping) or _sha256(_canonical_bytes(evidence)) != registration[key]:
            raise ConfirmatoryStudyError(
                "Stage-2 receipt embedded registration evidence is inconsistent"
            )
    manifest = _validate_embedded_stage2_registration_chain(
        plan=plan,
        files=files,
        registration_evidence=registration_evidence,
    )
    _validate_stage2_receipt_coverage_probe(
        data=data,
        files=files,
        plan=plan,
    )
    input_files = manifest.get("input_file_sha256") or {}
    for label in ("quotes", "stock_master", "fundamentals", "official_calendar"):
        if (
            not isinstance(files.get(label), Mapping)
            or files[label].get("sha256") != input_files.get(label)
        ):
            raise ConfirmatoryStudyError(
                "Stage-2 receipt raw-input hashes differ from the registered manifest"
            )
    declaration = _validate_stage2_receipt_declaration(
        data=data,
        files=files,
        plan=plan,
        manifest=manifest,
        authorization=registration_evidence["execution_authorization"],
    )
    official_calendar = _validate_stage2_receipt_official_calendar(
        data=data,
        files=files,
        plan=plan,
        manifest=manifest,
    )

    results = receipt.get("results")
    if not isinstance(results, list):
        raise ConfirmatoryStudyError("Stage-2 receipt results must be a list")
    expected_result_count = len(variants) * len(EXPECTED_FACTORS)
    control = receipt.get("selection_control") or {}
    if (
        control.get("all_registered_results_reported") is not True
        or control.get("full_factorial_reported") is not True
        or control.get("best_result_selected") is not False
        or control.get("expected_result_count") != expected_result_count
        or control.get("reported_result_count") != expected_result_count
        or len(results) != expected_result_count
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt does not report the complete registered result set"
        )
    registered = {
        (variant.variant_id, factor)
        for variant in variants
        for factor in EXPECTED_FACTORS
    }
    reported = {(row.get("variant"), row.get("factor")) for row in results}
    if reported != registered or len(reported) != len(results):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt result cells differ from the registered plan"
        )

    observations = receipt.get("monthly_observations")
    if not isinstance(observations, list):
        raise ConfirmatoryStudyError("Stage-2 receipt monthly observations are missing")
    sample = receipt.get("sample") or {}
    rebalance_dates = sample.get("rebalance_dates")
    if not isinstance(rebalance_dates, list) or not all(
        isinstance(day, str) for day in rebalance_dates
    ):
        raise ConfirmatoryStudyError("Stage-2 receipt rebalance-date lattice is missing")
    parsed_dates = [pd.Timestamp(day) for day in rebalance_dates]
    if (
        rebalance_dates != sorted(rebalance_dates)
        or len(rebalance_dates) != len(set(rebalance_dates))
        or len({day.to_period("M") for day in parsed_dates}) != len(parsed_dates)
        or any(
            day < pd.Timestamp(STAGE2_TEST_PERIOD[0])
            or day > pd.Timestamp(STAGE2_TEST_PERIOD[1])
            for day in parsed_dates
        )
        or sample.get("test_rebalance_count") != len(rebalance_dates)
    ):
        raise ConfirmatoryStudyError("Stage-2 receipt rebalance-date lattice is invalid")
    _validate_stage2_receipt_calendar_sample(
        official_calendar=official_calendar,
        sample=sample,
        plan=plan,
        rebalance_dates=rebalance_dates,
    )
    expected_observation_keys = {
        (day, variant.variant_id, factor)
        for day in rebalance_dates
        for variant in variants
        for factor in EXPECTED_FACTORS
    }
    observation_keys = []
    for row in observations:
        if not isinstance(row, Mapping):
            raise ConfirmatoryStudyError("Stage-2 receipt monthly observation is invalid")
        key = (row.get("date"), row.get("variant"), row.get("factor"))
        observation_keys.append(key)
        size = row.get("cross_section_size")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ConfirmatoryStudyError(
                "Stage-2 receipt monthly cross-section size is invalid"
            )
        audit = row.get("sample_audit")
        if not isinstance(audit, Mapping):
            raise ConfirmatoryStudyError(
                "Stage-2 receipt monthly endpoint audit is missing"
            )
        estimable_count = audit.get("estimable_count")
        if (
            isinstance(estimable_count, bool)
            or not isinstance(estimable_count, int)
            or estimable_count < 0
        ):
            raise ConfirmatoryStudyError(
                "Stage-2 receipt monthly endpoint audit estimable count is invalid"
            )
        if size != estimable_count:
            raise ConfirmatoryStudyError(
                "Stage-2 receipt monthly cross-section size differs from sample audit estimable count"
            )
        for field in ("ic", "top_minus_universe"):
            value = row.get(field)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                raise ConfirmatoryStudyError(
                    f"Stage-2 receipt monthly {field} value is invalid"
                )
    expected_observations = len(expected_observation_keys)
    if (
        set(observation_keys) != expected_observation_keys
        or len(observation_keys) != expected_observations
        or control.get("expected_monthly_observation_count") != expected_observations
        or control.get("reported_monthly_observation_count") != expected_observations
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt monthly observations do not equal the exact registered Cartesian lattice"
        )
    recomputed_results = _aggregate_results(
        observations,
        {
            "variants": [variant.variant_id for variant in variants],
            "factors": list(EXPECTED_FACTORS),
            "newey_west_lag": int(plan["newey_west_lag"]),
        },
    )
    if recomputed_results != results:
        raise ConfirmatoryStudyError("Stage-2 receipt results differ from monthly observations")

    recomputed_status = _stage2_evidence_status(
        declaration=declaration,
        observations=observations,
        plan=plan,
    )
    recomputed_status["revision_history_claim"] = False
    global_claim_eligible = (
        recomputed_status["code"]
        == "REAL_MARKET_REGISTERED_HISTORICAL_IC_CORE_STATISTICS"
    )

    from .stage2_estimands import Stage2EstimandError, verify_registered_estimands

    try:
        verify_registered_estimands(
            receipt.get("estimands") or {},
            factors=EXPECTED_FACTORS,
            expected_global_claim_eligible=global_claim_eligible,
        )
    except Stage2EstimandError as exc:
        raise ConfirmatoryStudyError("Stage-2 receipt estimands failed verification") from exc
    from .stage2_estimands import build_registered_estimands

    recomputed_estimands = build_registered_estimands(
        observations,
        plan=plan,
        nw_lag=int(plan["newey_west_lag"]),
        minimum_claim_months=int(plan["minimum_significance_months"]),
        global_claim_eligible=global_claim_eligible,
    )
    if recomputed_estimands != receipt.get("estimands"):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt differs from recomputed estimands"
        )

    if receipt.get("status") != recomputed_status:
        raise ConfirmatoryStudyError(
            "Stage-2 receipt evidence status differs from the monthly observations"
        )
    if sample.get("complete_registered_rebalance_count") != recomputed_status[
        "complete_registered_rebalance_count"
    ]:
        raise ConfirmatoryStudyError(
            "Stage-2 receipt sample completeness differs from recomputed evidence"
        )
    symbol_count = sample.get("symbol_count")
    if (
        isinstance(symbol_count, bool)
        or not isinstance(symbol_count, int)
        or symbol_count < 0
        or any(row["cross_section_size"] > symbol_count for row in observations)
    ):
        raise ConfirmatoryStudyError("Stage-2 receipt symbol count is inconsistent")
    _validate_stage2_endpoint_reason_ledger(
        endpoint_ledger_path=(
            None
            if endpoint_ledger_path is None
            else Path(endpoint_ledger_path)
        ),
        metadata=receipt.get("endpoint_reason_ledger"),
        observations=observations,
    )
    return receipt


def _validate_stage2_registered_scope_contracts(
    *,
    manifest: Mapping[str, Any],
    registration_receipt: Mapping[str, Any],
    authorization: Mapping[str, Any],
) -> None:
    if manifest.get("registered_design_assertions") != STAGE2_REGISTERED_DESIGN_ASSERTIONS:
        raise ConfirmatoryStudyError(
            "Stage-2 design manifest registered assertions differ from the fixed design"
        )
    if registration_receipt.get("registered_scope_summary") != STAGE2_REGISTERED_SCOPE_SUMMARY:
        raise ConfirmatoryStudyError(
            "Stage-2 registration receipt scope summary differs from the fixed design"
        )
    release_scope = authorization.get("release_scope")
    if not isinstance(release_scope, Mapping) or (
        release_scope.get("authorized_core_outputs") != STAGE2_AUTHORIZED_CORE_OUTPUTS
        or release_scope.get("endpoint_boundary")
        != STAGE2_AUTHORIZATION_ENDPOINT_BOUNDARY
        or release_scope.get("claim_boundary") != STAGE2_AUTHORIZATION_CLAIM_BOUNDARY
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 execution authorization scope boundaries differ from the fixed design"
        )


def _validate_embedded_stage2_registration_chain(
    *,
    plan: Mapping[str, Any],
    files: Mapping[str, Any],
    registration_evidence: Mapping[str, Any],
) -> Mapping[str, Any]:
    manifest = registration_evidence.get("design_manifest")
    registration_receipt = registration_evidence.get("registration_receipt")
    authorization = registration_evidence.get("execution_authorization")
    if not all(
        isinstance(value, Mapping)
        for value in (manifest, registration_receipt, authorization)
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt embedded registration evidence is incomplete"
        )

    artifact_keys = (
        "coverage_probe_spec_sha256",
        "coverage_probe_receipt_sha256",
        "data_declaration_sha256",
        "official_calendar_sha256",
        "coverage_report_sha256",
        "review_attestation_sha256",
        "protocol_source_sha256",
        "statistical_analysis_plan_sha256",
        "prior_specification_inventory_sha256",
        "prior_exposure_attestation_sha256",
    )
    expected_artifacts = {key: plan[key] for key in artifact_keys}
    prior_exposure_log_file = files.get("prior_exposure_log")
    if (
        not isinstance(prior_exposure_log_file, Mapping)
        or not _is_sha256(prior_exposure_log_file.get("sha256"))
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt prior exposure log binding is missing"
        )
    expected_artifacts["prior_exposure_log_sha256"] = prior_exposure_log_file[
        "sha256"
    ]
    expected_input_hashes = {
        label: files[label]["sha256"]
        for label in ("quotes", "stock_master", "fundamentals", "official_calendar")
    }
    registration = plan["external_registration"]
    if (
        manifest.get("schema_version") != "stage2_design_manifest_v1"
        or manifest.get("study_id") != plan["study_id"]
        or manifest.get("status") != "frozen_outcome_blind"
        or manifest.get("design_frozen_at") != plan["design_frozen_at"]
        or manifest.get("plan_core_sha256")
        != registration["registered_content_sha256"]
        or manifest.get("artifacts") != expected_artifacts
        or manifest.get("input_file_sha256") != expected_input_hashes
        or manifest.get("code_commit") != plan["code_commit"]
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 embedded design manifest does not bind the frozen package and inputs"
        )

    if (
        registration_receipt.get("schema_version")
        != "stage2_registration_receipt_v1"
        or registration_receipt.get("study_id") != plan["study_id"]
        or registration_receipt.get("status") != "registered_external"
        or registration_receipt.get("provider") != registration["provider"]
        or registration_receipt.get("identifier") != registration["identifier"]
        or registration_receipt.get("registered_at") != registration["registered_at"]
        or registration_receipt.get("verification_uri")
        != registration["verification_uri"]
        or registration_receipt.get("registered_artifact_sha256")
        != registration["design_manifest_sha256"]
        or registration_receipt.get("coverage_probe_receipt_sha256")
        != plan["coverage_probe_receipt_sha256"]
        or registration_receipt.get("registered_artifact_type")
        != "stage2_design_manifest_v1_exact_bytes_or_sha256_digest"
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 registration receipt does not bind the design manifest"
        )

    # Hashes and reverse links prove consistency with the embedded registered
    # package, not external authenticity.  A human-verified registry record
    # remains the explicit trust boundary unless a detached proof is supplied.
    _validate_registration_proof(registration_receipt.get("proof"))
    if (
        authorization.get("schema_version")
        != "stage2_execution_authorization_v1"
        or authorization.get("study_id") != plan["study_id"]
        or authorization.get("status") != "authorized"
        or authorization.get("authorized_at") != plan["locked_at"]
        or authorization.get("design_manifest_sha256")
        != registration["design_manifest_sha256"]
        or authorization.get("registration_receipt_sha256")
        != registration["registration_receipt_sha256"]
        or authorization.get("plan_core_sha256")
        != registration["registered_content_sha256"]
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 execution authorization does not bind the registered package"
        )
    _validate_stage2_registered_scope_contracts(
        manifest=manifest,
        registration_receipt=registration_receipt,
        authorization=authorization,
    )
    expected_bound_artifacts = {
        **expected_artifacts,
        "code_commit": plan["code_commit"],
    }
    if authorization.get("bound_artifacts") != expected_bound_artifacts:
        raise ConfirmatoryStudyError(
            "Stage-2 execution authorization artifact bindings are incomplete"
        )

    chronology = authorization.get("chronology")
    chronology_keys = {
        "prior_inventory_cutoff_at",
        "prior_inventory_generated_at",
        "data_reviewed_at",
        "prior_exposure_attested_at",
        "design_frozen_at",
        "externally_registered_at",
        "registration_recorded_at",
        "registration_verified_at",
        "authorized_at",
    }
    if not isinstance(chronology, Mapping) or set(chronology) != chronology_keys:
        raise ConfirmatoryStudyError(
            "Stage-2 registration and execution authorization chronology is invalid"
        )
    expected_chronology_links = {
        "design_frozen_at": plan["design_frozen_at"],
        "externally_registered_at": registration_receipt.get("registered_at"),
        "registration_recorded_at": registration_receipt.get("recorded_at"),
        "registration_verified_at": (registration_receipt.get("proof") or {}).get(
            "verified_at"
        ),
        "authorized_at": authorization.get("authorized_at"),
    }
    if any(chronology.get(key) != value for key, value in expected_chronology_links.items()):
        raise ConfirmatoryStudyError(
            "Stage-2 registration and execution authorization chronology is invalid"
        )
    parsed_chronology = {
        key: _finite_tz_timestamp(value, key)
        for key, value in chronology.items()
    }
    if not (
        parsed_chronology["prior_inventory_cutoff_at"]
        <= parsed_chronology["prior_inventory_generated_at"]
        <= parsed_chronology["prior_exposure_attested_at"]
        <= parsed_chronology["design_frozen_at"]
        <= parsed_chronology["externally_registered_at"]
        <= parsed_chronology["registration_recorded_at"]
        <= parsed_chronology["registration_verified_at"]
        <= parsed_chronology["authorized_at"]
        and parsed_chronology["data_reviewed_at"]
        <= parsed_chronology["prior_exposure_attested_at"]
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 registration and execution authorization chronology is invalid"
        )

    assertion_keys = {
        "all_timestamps_are_timezone_aware",
        "inventory_cutoff_not_after_inventory_generation",
        "inventory_generation_not_after_prior_exposure_attestation",
        "data_review_not_after_design_freeze",
        "prior_exposure_attestation_not_after_design_freeze",
        "design_freeze_not_after_external_registration",
        "external_registration_not_after_receipt_recording",
        "receipt_recording_not_after_receipt_verification",
        "receipt_verification_not_after_authorization",
        "blind_2010_2022_outcome_data_not_released_or_inspected_before_authorization",
        "all_bound_hashes_recomputed_and_equal",
    }
    assertions = authorization.get("chronology_assertions")
    if (
        not isinstance(assertions, Mapping)
        or set(assertions) != assertion_keys
        or any(assertions[key] is not True for key in assertion_keys)
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 execution authorization assertions have not all passed"
        )
    release_scope = authorization.get("release_scope")
    if (
        not isinstance(release_scope, Mapping)
        or release_scope.get("authorized_runner_scope") != plan["runner_scope"]
        or release_scope.get("authorized_analysis_period") != list(plan["test_period"])
        or release_scope.get("authorized_code_commit") != plan["code_commit"]
        or release_scope.get("outcome_data_release_permitted_after_authorized_at")
        is not True
        or release_scope.get("planned_excluded_modules_remain_unauthorized")
        != list(STAGE2_PLANNED_EXCLUDED_MODULES)
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 execution authorization release scope is invalid"
        )
    for key in ("authorizer", "authorizer_role", "statement"):
        if not _meaningful_text(authorization.get(key)):
            raise ConfirmatoryStudyError(
                f"Stage-2 execution authorization {key} is missing or invalid"
            )
    _validate_attestation_signature(
        authorization.get("signature"), "execution authorization"
    )
    return manifest


def _validate_stage2_receipt_coverage_probe(
    *,
    data: Mapping[str, Any],
    files: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> None:
    package = data.get("coverage_probe_receipt")
    if not isinstance(package, Mapping) or set(package) != {
        "content",
        "source_file_sha256",
        "canonical_sha256",
    }:
        raise ConfirmatoryStudyError(
            "Stage-2 receipt embedded coverage probe receipt is missing"
        )
    content = package.get("content")
    file_evidence = files.get("coverage_probe_receipt")
    if not isinstance(content, Mapping) or not isinstance(file_evidence, Mapping):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt embedded coverage probe receipt is invalid"
        )
    canonical_sha256 = _sha256(_canonical_bytes(content))
    if (
        package.get("source_file_sha256") != plan["coverage_probe_receipt_sha256"]
        or package.get("canonical_sha256") != canonical_sha256
        or canonical_sha256 != plan["coverage_probe_receipt_sha256"]
        or file_evidence.get("sha256") != plan["coverage_probe_receipt_sha256"]
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt coverage probe receipt hash binding is inconsistent"
        )
    _validate_stage2_coverage_probe_receipt_content(
        content,
        expected_spec_sha256=str(plan["coverage_probe_spec_sha256"]),
        expected_study_id=str(plan["study_id"]),
    )


def _validate_stage2_receipt_declaration(
    *,
    data: Mapping[str, Any],
    files: Mapping[str, Any],
    plan: Mapping[str, Any],
    manifest: Mapping[str, Any],
    authorization: Mapping[str, Any],
) -> Mapping[str, Any]:
    package = data.get("declaration")
    if not isinstance(package, Mapping):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt canonical data declaration is missing"
        )
    declaration = package.get("content")
    if not isinstance(declaration, Mapping):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt canonical data declaration content is missing"
        )
    _validate_declaration(declaration)
    _validate_stage2_declaration(declaration)
    if package.get("canonical_sha256") != _sha256(_canonical_bytes(declaration)):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt canonical data declaration hash is invalid"
        )

    source_hash = package.get("source_file_sha256")
    manifest_artifacts = manifest.get("artifacts") or {}
    authorization_artifacts = authorization.get("bound_artifacts") or {}
    if (
        not _is_sha256(source_hash)
        or source_hash != files["data_declaration"]["sha256"]
        or source_hash != plan["data_declaration_sha256"]
        or source_hash != manifest_artifacts.get("data_declaration_sha256")
        or source_hash != authorization_artifacts.get("data_declaration_sha256")
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt data declaration is not bound to the registered source file"
        )
    source_text = package.get("source_text")
    if (
        not isinstance(source_text, str)
        or _sha256(source_text.encode("utf-8")) != source_hash
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt data declaration source text hash is invalid"
        )
    source_declaration = _read_json_object(
        source_text.encode("utf-8"), "embedded data declaration source text"
    )
    if source_declaration != declaration:
        raise ConfirmatoryStudyError(
            "Stage-2 receipt data declaration source text differs from canonical content"
        )
    expected_binding = {
        "plan_data_declaration_sha256": plan["data_declaration_sha256"],
        "coverage_report_sha256": plan["coverage_report_sha256"],
        "design_manifest_sha256": plan["external_registration"][
            "design_manifest_sha256"
        ],
        "manifest_input_file_sha256": dict(manifest["input_file_sha256"]),
    }
    if package.get("binding") != expected_binding:
        raise ConfirmatoryStudyError(
            "Stage-2 receipt data declaration artifact binding is invalid"
        )
    if (
        expected_binding["coverage_report_sha256"]
        != manifest_artifacts.get("coverage_report_sha256")
        or expected_binding["coverage_report_sha256"]
        != authorization_artifacts.get("coverage_report_sha256")
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt data declaration coverage binding is invalid"
        )

    if data.get("classification") != declaration["source_classification"]:
        raise ConfirmatoryStudyError(
            "Stage-2 receipt data declaration classification is inconsistent"
        )
    expected_summary = {
        "source_name": declaration["source_name"],
        "redistributable": bool(declaration["redistributable"]),
        "price_semantics": declaration["price_semantics"],
        "rights_review": declaration["rights_review"],
    }
    if any(data.get(key) != value for key, value in expected_summary.items()):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt data summary differs from the canonical declaration"
        )
    return declaration


def _validate_stage2_receipt_official_calendar(
    *,
    data: Mapping[str, Any],
    files: Mapping[str, Any],
    plan: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> tuple[pd.Timestamp, ...]:
    evidence = data.get("official_calendar")
    if not isinstance(evidence, Mapping):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt official-calendar session evidence is missing"
        )
    raw_dates = evidence.get("session_dates")
    if not isinstance(raw_dates, list) or not raw_dates:
        raise ConfirmatoryStudyError(
            "Stage-2 receipt official-calendar session dates are missing"
        )
    dates: list[pd.Timestamp] = []
    for value in raw_dates:
        if not isinstance(value, str):
            raise ConfirmatoryStudyError(
                "Stage-2 receipt official-calendar session date is invalid"
            )
        try:
            parsed = pd.Timestamp(value)
        except (TypeError, ValueError) as exc:
            raise ConfirmatoryStudyError(
                "Stage-2 receipt official-calendar session date is invalid"
            ) from exc
        if pd.isna(parsed) or parsed.tzinfo is not None or value != parsed.date().isoformat():
            raise ConfirmatoryStudyError(
                "Stage-2 receipt official-calendar session date is invalid"
            )
        dates.append(parsed)
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt official-calendar sessions must be unique and ordered"
        )
    if (
        evidence.get("schema_version")
        != STAGE2_OFFICIAL_CALENDAR_CONTRACT["schema_version"]
        or evidence.get("timezone") != STAGE2_OFFICIAL_CALENDAR_CONTRACT["timezone"]
        or evidence.get("session_count") != len(dates)
        or evidence.get("first_session") != raw_dates[0]
        or evidence.get("last_session") != raw_dates[-1]
        or evidence.get("canonical_session_dates_sha256")
        != _sha256(_canonical_bytes(raw_dates))
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt official-calendar canonical evidence is invalid"
        )
    source_hash = evidence.get("source_file_sha256")
    if (
        source_hash != files["official_calendar"]["sha256"]
        or source_hash != plan["official_calendar_sha256"]
        or source_hash
        != (manifest.get("input_file_sha256") or {}).get("official_calendar")
        or source_hash != (manifest.get("artifacts") or {}).get(
            "official_calendar_sha256"
        )
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt official calendar is not bound to the registered raw input"
        )
    source_text = evidence.get("source_text")
    if (
        not isinstance(source_text, str)
        or _sha256(source_text.encode("utf-8")) != source_hash
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt official-calendar raw CSV source text hash is invalid"
        )
    try:
        source_frame = pd.read_csv(
            io.StringIO(source_text), dtype=str, keep_default_na=False
        )
    except (ValueError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ConfirmatoryStudyError(
            "Stage-2 receipt official-calendar raw CSV is invalid"
        ) from exc
    if list(source_frame.columns) != ["date"]:
        raise ConfirmatoryStudyError(
            "Stage-2 receipt official-calendar raw CSV schema is invalid"
        )
    source_dates: list[str] = []
    for value in source_frame["date"]:
        try:
            parsed = pd.Timestamp(value)
        except (TypeError, ValueError) as exc:
            raise ConfirmatoryStudyError(
                "Stage-2 receipt official-calendar raw CSV date is invalid"
            ) from exc
        if pd.isna(parsed) or parsed.tzinfo is not None:
            raise ConfirmatoryStudyError(
                "Stage-2 receipt official-calendar raw CSV date is invalid"
            )
        source_dates.append(parsed.date().isoformat())
    if source_dates != raw_dates:
        raise ConfirmatoryStudyError(
            "Stage-2 receipt official-calendar raw CSV differs from session evidence"
        )
    if (
        dates[0].to_period("M") > pd.Period("2009-01", freq="M")
        or dates[-1].to_period("M") < pd.Period("2023-01", freq="M")
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt official calendar does not span the fixed endpoints"
        )
    target_months = {
        day.to_period("M") for day in dates if 2010 <= day.year <= 2022
    }
    if target_months != set(pd.period_range("2010-01", "2022-12", freq="M")):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt official calendar misses a fixed analysis month"
        )
    return tuple(dates)


def _validate_stage2_receipt_calendar_sample(
    *,
    official_calendar: Sequence[pd.Timestamp],
    sample: Mapping[str, Any],
    plan: Mapping[str, Any],
    rebalance_dates: Sequence[str],
) -> None:
    if (
        sample.get("train_start") != plan["train_period"][0]
        or sample.get("train_end") != plan["train_period"][1]
        or sample.get("test_start") != plan["test_period"][0]
        or sample.get("test_end") != plan["test_period"][1]
        or sample.get("forward_horizon_sessions")
        != plan["forward_horizon_sessions"]
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt sample interval differs from the registered plan"
        )
    expected = _monthly_rebalance_dates_from_calendar(
        official_calendar,
        str(plan["test_period"][0]),
        str(plan["test_period"][1]),
    )
    expected_dates = [day.date().isoformat() for day in expected]
    if list(rebalance_dates) != expected_dates:
        raise ConfirmatoryStudyError(
            "Stage-2 receipt rebalance dates are not each month's first official session"
        )

    calendar_index = {day.date().isoformat(): index for index, day in enumerate(official_calendar)}
    market_start = sample.get("market_start")
    market_end = sample.get("market_end")
    if market_start not in calendar_index or market_end not in calendar_index:
        raise ConfirmatoryStudyError(
            "Stage-2 receipt quote interval endpoints are not official sessions"
        )
    first_train_session = next(
        day for day in official_calendar
        if pd.Timestamp(plan["train_period"][0])
        <= day
        <= pd.Timestamp(plan["train_period"][1])
    )
    last_rebalance_index = calendar_index[expected_dates[-1]]
    required_exit_index = (
        last_rebalance_index + int(plan["forward_horizon_sessions"]) + 1
    )
    if (
        required_exit_index >= len(official_calendar)
        or calendar_index[market_start]
        > calendar_index[first_train_session.date().isoformat()]
        or calendar_index[market_end] < required_exit_index
        or calendar_index[market_start] > calendar_index[market_end]
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 receipt quote interval does not cover warm-up and outcome endpoints"
        )


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
    receipts = []
    for path in receipt_paths:
        receipt_path = _regular_file(path, "receipt")
        envelope = _read_json_object(receipt_path.read_bytes(), "receipt")
        if envelope.get("schema_version") == STAGE2_RECEIPT_SCHEMA_VERSION:
            receipts.append(verify_stage2_study_receipt(receipt_path))
        else:
            receipts.append(verify_study_receipt(receipt_path))
    if not receipts:
        raise ConfirmatoryStudyError("at least one verified receipt is required")
    codes = [receipt["status"]["code"] for receipt in receipts]
    if "REAL_MARKET_REGISTERED_HISTORICAL_IC_CORE_STATISTICS" in codes:
        status = "REAL_MARKET_REGISTERED_HISTORICAL_IC_CORE_STATISTICS"
    elif "REAL_MARKET_OOS_STATISTICS" in codes:
        status = "REAL_MARKET_OOS_STATISTICS"
    else:
        status = "INSUFFICIENT_EVIDENCE"
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


def _validate_stage2_plan(plan: Mapping[str, Any]) -> tuple[Stage2VariantSpec, ...]:
    variants = validate_stage2_variant_plan(plan)
    required = (
        "study_id", "design_frozen_at", "locked_at", "train_period", "test_period",
        "rebalance_frequency",
        "forward_horizon_sessions", "minimum_amount", "minimum_symbols",
        "minimum_oos_rebalances", "minimum_significance_months", "newey_west_lag",
        "composite_weights", "runner_scope",
        "external_registration", "coverage_report_sha256", "coverage_probe_spec_path",
        "coverage_probe_spec_sha256", "coverage_probe_receipt_path",
        "coverage_probe_receipt_sha256", "review_attestation_sha256",
        "data_declaration_sha256", "official_calendar_sha256",
        "protocol_source_sha256", "statistical_analysis_plan_sha256",
        "prior_specification_inventory_sha256", "prior_exposure_attestation_sha256",
        "code_commit", "fundamental_contract", "ic_outcome_clock", "inference",
        "endpoint_resolution", "roe_timing_common_support_decomposition",
        "publication_exposure_diagnostics", "claim_boundaries",
        "missingness", "portfolio_module", "reporting_rule", "deviation_rule",
        "deviation_reporting_module",
        "design_contract_version", "registration_semantics",
        "official_calendar_contract", "planned_excluded_modules", "variants_source",
        "runtime_contract",
    )
    missing = [key for key in required if key not in plan]
    if missing:
        raise ConfirmatoryStudyError(f"Stage-2 plan missing required fields: {missing}")
    if plan["study_id"] != STAGE2_STUDY_ID:
        raise ConfirmatoryStudyError("Stage-2 study_id differs from the fixed design")
    exact_scalars = {
        "runner_scope": "ic_core_only",
        "rebalance_frequency": "monthly",
        "forward_horizon_sessions": STAGE2_FORWARD_HORIZON_SESSIONS,
        "minimum_amount": STAGE2_MINIMUM_AMOUNT,
        "minimum_symbols": STAGE2_MINIMUM_SYMBOLS,
        "minimum_oos_rebalances": STAGE2_MINIMUM_REBALANCES,
        "minimum_significance_months": STAGE2_MINIMUM_SIGNIFICANCE_MONTHS,
        "newey_west_lag": STAGE2_NEWEY_WEST_LAG,
        "reporting_rule": STAGE2_REPORTING_RULE,
        "deviation_rule": STAGE2_DEVIATION_RULE,
        "design_contract_version": "stage2_design_contract_v1",
        "variants_source": STAGE2_VARIANTS_SOURCE,
        "coverage_probe_spec_path": STAGE2_COVERAGE_PROBE_SPEC_PATH,
        "coverage_probe_receipt_path": STAGE2_COVERAGE_PROBE_RECEIPT_PATH,
    }
    for key, expected in exact_scalars.items():
        if plan.get(key) != expected:
            raise ConfirmatoryStudyError(
                f"Stage-2 {key} differs from the fixed registered design"
            )
    if tuple(plan.get("train_period") or ()) != STAGE2_TRAIN_PERIOD:
        raise ConfirmatoryStudyError("Stage-2 warm-up period must remain 2009")
    if tuple(plan.get("test_period") or ()) != STAGE2_TEST_PERIOD:
        raise ConfirmatoryStudyError("Stage-2 analysis period must remain 2010-2022")
    if tuple(plan.get("factors") or ()) != EXPECTED_FACTORS:
        raise ConfirmatoryStudyError("Stage-2 factors must match the maintained factor set")
    if [variant.as_dict() for variant in variants] != _expected_stage2_variant_dicts():
        raise ConfirmatoryStudyError(
            "Stage-2 variants must retain the exact registered identifiers and order"
        )
    exact_objects = {
        "composite_weights": STAGE2_COMPOSITE_WEIGHTS,
        "fundamental_contract": STAGE2_FUNDAMENTAL_CONTRACT,
        "ic_outcome_clock": STAGE2_IC_OUTCOME_CLOCK,
        "endpoint_resolution": STAGE2_ENDPOINT_RESOLUTION_CONTRACT,
        "inference": STAGE2_INFERENCE_CONTRACT,
        "roe_timing_common_support_decomposition": (
            STAGE2_ROE_TIMING_COMMON_SUPPORT_DECOMPOSITION
        ),
        "publication_exposure_diagnostics": STAGE2_PUBLICATION_EXPOSURE_DIAGNOSTICS,
        "claim_boundaries": STAGE2_CLAIM_BOUNDARIES,
        "missingness": STAGE2_MISSINGNESS_CONTRACT,
        "portfolio_module": STAGE2_PORTFOLIO_CONTRACT,
        "deviation_reporting_module": STAGE2_DEVIATION_REPORTING_CONTRACT,
        "registration_semantics": STAGE2_REGISTRATION_SEMANTICS,
        "official_calendar_contract": STAGE2_OFFICIAL_CALENDAR_CONTRACT,
        "planned_excluded_modules": STAGE2_PLANNED_EXCLUDED_CONTRACT,
        "runtime_contract": STAGE2_RUNTIME_CONTRACT,
    }
    for key, expected in exact_objects.items():
        if plan.get(key) != expected:
            raise ConfirmatoryStudyError(
                f"Stage-2 {key} differs from the fixed registered design"
            )
    if plan["runner_scope"] != "ic_core_only":
        raise ConfirmatoryStudyError("Stage-2 runner_scope must be ic_core_only")
    if not _valid_external_registration(plan["external_registration"]):
        raise ConfirmatoryStudyError("Stage-2 external registration is missing or invalid")
    registration = plan["external_registration"]
    if registration["registered_content_sha256"] != stage2_registered_content_sha256(plan):
        raise ConfirmatoryStudyError(
            "Stage-2 external registration is not bound to the frozen plan content"
        )
    freeze_time = _finite_tz_timestamp(plan["design_frozen_at"], "design_frozen_at")
    registration_time = _finite_tz_timestamp(
        registration["registered_at"], "external registration timestamp"
    )
    locked_at = _finite_tz_timestamp(plan["locked_at"], "locked_at")
    if not (freeze_time <= registration_time <= locked_at):
        raise ConfirmatoryStudyError(
            "Stage-2 times must satisfy design_frozen_at <= registered_at <= locked_at"
        )
    for key in (
        "coverage_report_sha256",
        "coverage_probe_spec_sha256",
        "coverage_probe_receipt_sha256",
        "review_attestation_sha256",
        "data_declaration_sha256",
        "official_calendar_sha256",
        "protocol_source_sha256",
        "statistical_analysis_plan_sha256",
        "prior_specification_inventory_sha256",
        "prior_exposure_attestation_sha256",
    ):
        if not _is_sha256(plan[key]):
            raise ConfirmatoryStudyError(f"Stage-2 {key} is invalid")
    if not _is_git_sha(plan["code_commit"]):
        raise ConfirmatoryStudyError("Stage-2 code_commit is invalid")
    return variants


def _validate_stage2_data_bindings(
    *,
    plan: Mapping[str, Any],
    coverage: Mapping[str, Any],
    coverage_bytes: bytes,
    attestation: Mapping[str, Any],
    quotes_path: Path,
    stock_master_path: Path,
    fundamentals_path: Path,
    official_calendar_path: Path,
) -> None:
    if _sha256(coverage_bytes) != plan["coverage_report_sha256"]:
        raise ConfirmatoryStudyError("Stage-2 coverage report hash differs from the locked plan")
    from .study_v2_coverage import StudyV2CoverageError, validate_coverage_report

    try:
        validated_coverage = validate_coverage_report(
            coverage,
            quotes_csv=quotes_path.read_bytes(),
            stock_master_csv=stock_master_path.read_bytes(),
            fundamentals_csv=fundamentals_path.read_bytes(),
            official_calendar_csv=official_calendar_path.read_bytes(),
            input_names={
                "quotes": quotes_path.name,
                "stock_master": stock_master_path.name,
                "fundamentals": fundamentals_path.name,
                "official_calendar": official_calendar_path.name,
            },
            review_attestation=attestation,
        )
    except StudyV2CoverageError as exc:
        raise ConfirmatoryStudyError(
            "Stage-2 coverage report does not match recomputed raw-input coverage"
        ) from exc
    gates = validated_coverage["gates"]
    required_true = (
        "ready_to_lock_stage2_plan",
        "minimum_history_years_met",
        "minimum_monthly_observations_met",
        "minimum_sessions_per_month_met",
        "minimum_symbols_per_month_met",
        "target_quote_interval_available",
        "official_calendar_integrity_verified",
        "target_official_calendar_interval_available",
        "quote_dates_are_official_sessions",
        "target_fundamental_interval_available",
        "fundamental_target_month_continuity_met",
        "fundamental_eligible_symbol_intersection_met",
        "fundamental_staleness_coverage_met",
        "publication_date_coverage_met",
        "point_in_time_membership_available",
        "execution_semantics_verified",
        "tradability_fields_verified",
        "exact_endpoint_resolution_semantics_verified",
        "endpoint_reason_ledger_rights_verified",
        "data_rights_verified",
        "official_calendar_review_verified",
    )
    if any(gates.get(key) is not True for key in required_true):
        raise ConfirmatoryStudyError("Stage-2 coverage and review gates have not all passed")
    if gates.get("blocking_reason_codes") not in ([], ()):
        raise ConfirmatoryStudyError("Stage-2 coverage report still contains blocking reasons")
    if (
        gates.get("complete_revision_vintage_available") is not False
        or gates.get("revision_history_claim_allowed") is not False
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 revision-history claims require an unavailable validated adapter"
        )
    thresholds = validated_coverage.get("thresholds") or {}
    if (
        int(thresholds.get("minimum_monthly_observations", 0))
        < int(plan["minimum_oos_rebalances"])
        or int(thresholds.get("minimum_symbols_per_month", 0))
        < int(plan["minimum_symbols"])
        or thresholds.get("analysis_start") != str(plan["test_period"][0])
        or thresholds.get("analysis_end") != str(plan["test_period"][1])
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 coverage thresholds do not enforce the locked analysis sample"
        )


def _validate_stage2_research_bindings(
    *,
    plan: Mapping[str, Any],
    code_revision: str,
    source_classification: str,
    data_declaration_path: Path,
    official_calendar_path: Path,
    quotes_path: Path,
    stock_master_path: Path,
    fundamentals_path: Path,
    coverage_report_path: Path,
    coverage_probe_spec_path: Path,
    coverage_probe_receipt_path: Path,
    review_attestation_path: Path,
    design_manifest_path: Path,
    registration_receipt_path: Path,
    execution_authorization_path: Path,
    protocol_source_path: Path,
    statistical_analysis_plan_path: Path,
    prior_specification_inventory_path: Path,
    prior_exposure_log_path: Path,
    prior_exposure_attestation_path: Path,
    prior_exposure_attestation: Mapping[str, Any],
    review_attestation: Mapping[str, Any],
) -> None:
    if str(plan["code_commit"]).lower() != code_revision.lower():
        raise ConfirmatoryStudyError("Stage-2 code revision differs from the locked plan")
    _verify_repository_commit(
        code_revision,
        require_clean=source_classification == "real_market_data",
    )
    if source_classification == "real_market_data":
        _verify_stage2_runtime_contract(plan["runtime_contract"])
    expected_hashes = {
        "data_declaration_sha256": _sha256_file(data_declaration_path),
        "official_calendar_sha256": _sha256_file(official_calendar_path),
        "coverage_report_sha256": _sha256_file(coverage_report_path),
        "coverage_probe_spec_sha256": _sha256_file(coverage_probe_spec_path),
        "coverage_probe_receipt_sha256": _sha256_file(
            coverage_probe_receipt_path
        ),
        "review_attestation_sha256": _sha256_file(review_attestation_path),
        "protocol_source_sha256": _sha256_file(protocol_source_path),
        "statistical_analysis_plan_sha256": _sha256_file(
            statistical_analysis_plan_path
        ),
        "prior_specification_inventory_sha256": _sha256_file(
            prior_specification_inventory_path
        ),
        "prior_exposure_attestation_sha256": _sha256_file(
            prior_exposure_attestation_path
        ),
    }
    for key, digest in expected_hashes.items():
        if plan[key] != digest:
            raise ConfirmatoryStudyError(
                f"Stage-2 {key} differs from the locked research artifact"
            )

    coverage_probe_receipt = _validate_stage2_coverage_probe_receipt(
        spec_path=coverage_probe_spec_path,
        receipt_path=coverage_probe_receipt_path,
        expected_study_id=str(plan["study_id"]),
        prior_specification_inventory_path=prior_specification_inventory_path,
        review_scope_cutoff_at=review_attestation.get("review_scope_cutoff_at"),
    )
    if (
        review_attestation.get("coverage_probe_spec_path")
        != plan["coverage_probe_spec_path"]
        or review_attestation.get("coverage_probe_spec_sha256")
        != plan["coverage_probe_spec_sha256"]
        or review_attestation.get("coverage_probe_receipt_path")
        != plan["coverage_probe_receipt_path"]
        or review_attestation.get("coverage_probe_receipt_sha256")
        != plan["coverage_probe_receipt_sha256"]
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 review attestation is not bound to the coverage probe specification "
            "and receipt"
        )

    inventory = _read_json_object(
        prior_specification_inventory_path.read_bytes(),
        "prior specification inventory",
    )
    inventory_state = _validate_prior_specification_inventory(
        inventory,
        study_id=str(plan["study_id"]),
        expected_code_commit=str(plan["code_commit"]),
    )

    exposure = prior_exposure_attestation
    prior_exposure_log_sha256 = _sha256_file(prior_exposure_log_path)
    if exposure.get("schema_version") != "stage2_prior_exposure_attestation_v1":
        raise ConfirmatoryStudyError("unsupported Stage-2 prior exposure attestation")
    if exposure.get("study_id") != plan["study_id"]:
        raise ConfirmatoryStudyError(
            "Stage-2 prior exposure attestation has the wrong study identifier"
        )
    if exposure.get("analysis_period") != list(plan["test_period"]):
        raise ConfirmatoryStudyError(
            "Stage-2 prior exposure attestation has the wrong analysis period"
        )
    if (
        exposure.get("coverage_probe_spec_path")
        != plan["coverage_probe_spec_path"]
        or exposure.get("coverage_probe_receipt_path")
        != plan["coverage_probe_receipt_path"]
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 prior exposure attestation has the wrong coverage probe paths"
        )
    if exposure.get("stage2_factor_outcomes_previously_inspected") is not False:
        raise ConfirmatoryStudyError(
            "Stage-2 prior outcome exposure prevents confirmatory execution"
        )
    if exposure.get("status") != "attested_outcome_blind":
        raise ConfirmatoryStudyError(
            "Stage-2 prior exposure attestation is not finalized as outcome blind"
        )
    for key in (
        "attestor", "attestor_role", "attestor_authority_basis", "statement"
    ):
        value = exposure.get(key)
        if (
            not isinstance(value, str)
            or len(value.strip()) < 4
            or any(token in value.lower() for token in ("fill", "todo", "placeholder"))
        ):
            raise ConfirmatoryStudyError(
                f"Stage-2 prior exposure attestation {key} is missing or invalid"
            )
    attested_time = _finite_tz_timestamp(
        exposure.get("attested_at"), "prior exposure attestation timestamp"
    )
    knowledge_cutoff = _finite_tz_timestamp(
        exposure.get("knowledge_cutoff_at"), "prior exposure knowledge cutoff"
    )
    reviewed_at = _finite_tz_timestamp(
        review_attestation.get("reviewed_at"), "data review timestamp"
    )
    design_frozen_at = _finite_tz_timestamp(
        plan["design_frozen_at"], "design_frozen_at"
    )
    if not (
        inventory_state["generated_at"]
        <= knowledge_cutoff
        <= attested_time
        <= design_frozen_at
        and reviewed_at <= attested_time
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 inventory, review, attestation, and design-freeze chronology is invalid"
        )
    if (
        exposure.get("inventory_cutoff_at") != inventory_state["inventory_cutoff_at_text"]
        or exposure.get("inventory_generated_at") != inventory_state["generated_at_text"]
        or exposure.get("prior_specification_entry_count")
        != inventory_state["entry_count"]
        or exposure.get("prior_specification_entries_sha256")
        != inventory_state["entries_sha256"]
        or exposure.get("prior_exposure_log_sha256")
        != prior_exposure_log_sha256
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 prior exposure attestation is not bound to the final inventory "
            "and prior exposure log"
        )
    required_chronology_assertions = {
        "all_timestamps_are_timezone_aware",
        "inventory_cutoff_not_after_inventory_generation",
        "inventory_generation_not_after_knowledge_cutoff",
        "knowledge_cutoff_not_after_attestation",
        "data_review_completed_not_after_attestation",
        "attestation_will_precede_design_freeze",
        "blind_2010_2022_outcome_data_not_released_or_inspected_through_attested_at",
        "registered_publication_exposure_diagnostic_values_not_inspected_through_attested_at",
    }
    chronology_assertions = exposure.get("chronology_assertions")
    if (
        not isinstance(chronology_assertions, Mapping)
        or set(chronology_assertions) != required_chronology_assertions
        or any(chronology_assertions[key] is not True for key in required_chronology_assertions)
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 prior exposure chronology assertions have not all passed"
        )
    binding_keys = (
        "prior_specification_inventory_sha256",
        "coverage_probe_spec_sha256",
        "coverage_probe_receipt_sha256",
        "protocol_source_sha256",
        "statistical_analysis_plan_sha256",
        "coverage_report_sha256",
        "review_attestation_sha256",
        "data_declaration_sha256",
        "official_calendar_sha256",
        "code_commit",
    )
    if any(exposure.get(key) != plan[key] for key in binding_keys):
        raise ConfirmatoryStudyError(
            "Stage-2 prior exposure attestation is not bound to the registered artifacts"
        )
    _validate_attestation_signature(exposure.get("signature"), "prior exposure")

    input_hashes = {
        "quotes": _sha256_file(quotes_path),
        "stock_master": _sha256_file(stock_master_path),
        "fundamentals": _sha256_file(fundamentals_path),
        "official_calendar": _sha256_file(official_calendar_path),
    }
    design_manifest_bytes = design_manifest_path.read_bytes()
    if _sha256(design_manifest_bytes) != plan["external_registration"]["design_manifest_sha256"]:
        raise ConfirmatoryStudyError(
            "Stage-2 design manifest hash differs from the execution plan"
        )
    design_manifest = _read_json_object(design_manifest_bytes, "design manifest")
    if design_manifest_bytes != _canonical_bytes(design_manifest):
        raise ConfirmatoryStudyError("Stage-2 design manifest must be canonical JSON")
    expected_artifacts = {
        **expected_hashes,
        "prior_exposure_log_sha256": prior_exposure_log_sha256,
    }
    if (
        design_manifest.get("schema_version") != "stage2_design_manifest_v1"
        or design_manifest.get("study_id") != plan["study_id"]
        or design_manifest.get("status") != "frozen_outcome_blind"
        or design_manifest.get("design_frozen_at") != plan["design_frozen_at"]
        or design_manifest.get("plan_core_sha256")
        != plan["external_registration"]["registered_content_sha256"]
        or design_manifest.get("artifacts") != expected_artifacts
        or design_manifest.get("input_file_sha256") != input_hashes
        or design_manifest.get("code_commit") != plan["code_commit"]
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 design manifest does not bind the frozen package and inputs"
        )

    registration_bytes = registration_receipt_path.read_bytes()
    if _sha256(registration_bytes) != plan["external_registration"]["registration_receipt_sha256"]:
        raise ConfirmatoryStudyError(
            "Stage-2 external registration receipt hash differs from the plan"
        )
    registration_receipt = _read_json_object(
        registration_bytes, "external registration receipt"
    )
    if registration_bytes != _canonical_bytes(registration_receipt):
        raise ConfirmatoryStudyError(
            "Stage-2 external registration receipt must be canonical JSON"
        )
    registration = plan["external_registration"]
    if (
        registration_receipt.get("schema_version")
        != "stage2_registration_receipt_v1"
        or registration_receipt.get("study_id") != plan["study_id"]
        or registration_receipt.get("status") != "registered_external"
        or registration_receipt.get("provider") != registration["provider"]
        or registration_receipt.get("identifier") != registration["identifier"]
        or registration_receipt.get("registered_at") != registration["registered_at"]
        or registration_receipt.get("verification_uri")
        != registration["verification_uri"]
        or registration_receipt.get("registered_artifact_sha256")
        != registration["design_manifest_sha256"]
        or registration_receipt.get("coverage_probe_receipt_sha256")
        != plan["coverage_probe_receipt_sha256"]
        or registration_receipt.get("registered_artifact_type")
        != "stage2_design_manifest_v1_exact_bytes_or_sha256_digest"
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 registration receipt does not bind the design manifest"
        )
    _validate_registration_proof(registration_receipt.get("proof"))
    registered_at = _finite_tz_timestamp(
        registration_receipt.get("registered_at"), "external registration timestamp"
    )
    recorded_at = _finite_tz_timestamp(
        registration_receipt.get("recorded_at"), "registration receipt timestamp"
    )
    verified_at = _finite_tz_timestamp(
        (registration_receipt.get("proof") or {}).get("verified_at"),
        "registration verification timestamp",
    )

    authorization_bytes = execution_authorization_path.read_bytes()
    if _sha256(authorization_bytes) != registration["execution_authorization_sha256"]:
        raise ConfirmatoryStudyError(
            "Stage-2 execution authorization hash differs from the plan"
        )
    authorization = _read_json_object(
        authorization_bytes, "execution authorization"
    )
    if authorization_bytes != _canonical_bytes(authorization):
        raise ConfirmatoryStudyError(
            "Stage-2 execution authorization must be canonical JSON"
        )
    if (
        authorization.get("schema_version")
        != "stage2_execution_authorization_v1"
        or authorization.get("study_id") != plan["study_id"]
        or authorization.get("status") != "authorized"
        or authorization.get("authorized_at") != plan["locked_at"]
        or authorization.get("design_manifest_sha256")
        != registration["design_manifest_sha256"]
        or authorization.get("registration_receipt_sha256")
        != registration["registration_receipt_sha256"]
        or authorization.get("plan_core_sha256")
        != registration["registered_content_sha256"]
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 execution authorization does not bind the registered package"
        )
    _validate_stage2_registered_scope_contracts(
        manifest=design_manifest,
        registration_receipt=registration_receipt,
        authorization=authorization,
    )
    expected_bound_artifacts = {**expected_artifacts, "code_commit": plan["code_commit"]}
    if authorization.get("bound_artifacts") != expected_bound_artifacts:
        raise ConfirmatoryStudyError(
            "Stage-2 execution authorization artifact bindings are incomplete"
        )
    chronology = authorization.get("chronology")
    expected_chronology = {
        "prior_inventory_cutoff_at": inventory_state["inventory_cutoff_at_text"],
        "prior_inventory_generated_at": inventory_state["generated_at_text"],
        "data_reviewed_at": review_attestation.get("reviewed_at"),
        "prior_exposure_attested_at": exposure.get("attested_at"),
        "design_frozen_at": plan["design_frozen_at"],
        "externally_registered_at": registration_receipt.get("registered_at"),
        "registration_recorded_at": registration_receipt.get("recorded_at"),
        "registration_verified_at": (registration_receipt.get("proof") or {}).get(
            "verified_at"
        ),
        "authorized_at": authorization.get("authorized_at"),
    }
    authorized_at = _finite_tz_timestamp(
        authorization.get("authorized_at"), "execution authorization timestamp"
    )
    if chronology != expected_chronology or not (
        design_frozen_at <= registered_at <= recorded_at <= verified_at <= authorized_at
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 registration and execution authorization chronology is invalid"
        )
    authorization_assertion_keys = {
        "all_timestamps_are_timezone_aware",
        "inventory_cutoff_not_after_inventory_generation",
        "inventory_generation_not_after_prior_exposure_attestation",
        "data_review_not_after_design_freeze",
        "prior_exposure_attestation_not_after_design_freeze",
        "design_freeze_not_after_external_registration",
        "external_registration_not_after_receipt_recording",
        "receipt_recording_not_after_receipt_verification",
        "receipt_verification_not_after_authorization",
        "blind_2010_2022_outcome_data_not_released_or_inspected_before_authorization",
        "all_bound_hashes_recomputed_and_equal",
    }
    authorization_assertions = authorization.get("chronology_assertions")
    if (
        not isinstance(authorization_assertions, Mapping)
        or set(authorization_assertions) != authorization_assertion_keys
        or any(
            authorization_assertions[key] is not True
            for key in authorization_assertion_keys
        )
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 execution authorization assertions have not all passed"
        )
    release_scope = authorization.get("release_scope")
    if (
        not isinstance(release_scope, Mapping)
        or release_scope.get("authorized_runner_scope") != "ic_core_only"
        or release_scope.get("authorized_analysis_period") != list(plan["test_period"])
        or release_scope.get("authorized_code_commit") != plan["code_commit"]
        or release_scope.get("outcome_data_release_permitted_after_authorized_at")
        is not True
        or release_scope.get("planned_excluded_modules_remain_unauthorized")
        != list(STAGE2_PLANNED_EXCLUDED_MODULES)
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 execution authorization release scope is invalid"
        )
    for key in ("authorizer", "authorizer_role", "statement"):
        if not _meaningful_text(authorization.get(key)):
            raise ConfirmatoryStudyError(
                f"Stage-2 execution authorization {key} is missing or invalid"
            )
    _validate_attestation_signature(authorization.get("signature"), "execution authorization")


def _meaningful_text(value: Any, *, minimum_length: int = 4) -> bool:
    return bool(
        isinstance(value, str)
        and len(value.strip()) >= minimum_length
        and not any(
            token in value.lower()
            for token in ("fill", "todo", "pending", "placeholder")
        )
    )


def _validate_attestation_signature(value: Any, label: str) -> None:
    if not isinstance(value, Mapping):
        raise ConfirmatoryStudyError(f"Stage-2 {label} signature evidence is missing")
    if value.get("type") != "human_verified_evidence":
        raise ConfirmatoryStudyError(
            f"Stage-2 {label} accepts only explicit human-verified evidence; "
            "cryptographic proof validation is not implemented"
        )
    if not _is_sha256(value.get("evidence_sha256")):
        raise ConfirmatoryStudyError(f"Stage-2 {label} signature evidence hash is invalid")
    if not _meaningful_text(value.get("signer_identity")):
        raise ConfirmatoryStudyError(f"Stage-2 {label} signer identity is invalid")
    verification_uri = value.get("verification_uri")
    if not isinstance(verification_uri, str):
        raise ConfirmatoryStudyError(f"Stage-2 {label} verification URI is missing")
    parsed = urlparse(verification_uri)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ConfirmatoryStudyError(f"Stage-2 {label} verification URI is invalid")
    if value.get("trust_boundary") != (
        "Identity and evidence authenticity require independent human verification."
    ):
        raise ConfirmatoryStudyError(
            f"Stage-2 {label} must disclose the human-verification trust boundary"
        )


def _validate_registration_proof(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise ConfirmatoryStudyError("Stage-2 registration proof is missing")
    if value.get("type") != "human_verified_registry_record":
        raise ConfirmatoryStudyError(
            "Stage-2 registration accepts only an explicit human-verified registry "
            "record; cryptographic proof validation is not implemented"
        )
    if not _is_sha256(value.get("evidence_sha256")):
        raise ConfirmatoryStudyError("Stage-2 registration proof evidence hash is invalid")
    if not _meaningful_text(value.get("verifier")):
        raise ConfirmatoryStudyError("Stage-2 registration proof verifier is invalid")
    if value.get("trust_boundary") != (
        "The registry record has no offline-verifiable signature; authenticity requires independent human verification."
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 registration proof must disclose its human-verification trust boundary"
        )


def _validate_prior_specification_inventory(
    inventory: Mapping[str, Any], *, study_id: str, expected_code_commit: str
) -> dict[str, Any]:
    if (
        inventory.get("schema_version") != "prior_specification_inventory_v1"
        or inventory.get("study_id") != study_id
        or inventory.get("outcome_blind_inventory") is not True
        or inventory.get("contains_outcome_values") is not False
        or not _meaningful_text(inventory.get("inventory_id"))
        or not _meaningful_text(inventory.get("purpose"), minimum_length=20)
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 prior specification inventory is invalid or contains outcomes"
        )
    if inventory.get("status") != "manifest_eligible_outcome_blind":
        raise ConfirmatoryStudyError(
            "Stage-2 prior specification inventory is not manifest eligible"
        )
    for key in ("prepared_by", "preparer_role"):
        if not _meaningful_text(inventory.get(key)):
            raise ConfirmatoryStudyError(
                f"Stage-2 prior specification inventory {key} preparer field is invalid"
            )
    inventory_cutoff = _finite_tz_timestamp(
        inventory.get("inventory_cutoff_at"), "inventory cutoff timestamp"
    )
    generated_at = _finite_tz_timestamp(
        inventory.get("generated_at"), "inventory generation timestamp"
    )
    entries = inventory.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ConfirmatoryStudyError(
            "Stage-2 prior specification inventory must enumerate prior specifications"
        )
    if inventory.get("entry_count") != len(entries):
        raise ConfirmatoryStudyError(
            "Stage-2 prior specification inventory entry count is inconsistent"
        )
    if inventory.get("entries_sha256") != _sha256(_canonical_bytes(entries)):
        raise ConfirmatoryStudyError(
            "Stage-2 prior specification inventory entries hash is inconsistent"
        )
    identifiers: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            raise ConfirmatoryStudyError(
                f"Stage-2 prior specification inventory entry {index} is invalid"
            )
        identifier = entry.get("inventory_id")
        if not _meaningful_text(identifier) or identifier in identifiers:
            raise ConfirmatoryStudyError(
                "Stage-2 prior specification inventory identifiers are invalid or duplicated"
            )
        identifiers.add(str(identifier))
        if (
            not _meaningful_text(entry.get("artifact_type"))
            or not _meaningful_text(entry.get("primary_path"))
            or entry.get("present_in_repository") not in {True, False}
            or entry.get("repository_state")
            not in {"tracked_at_head", "working_tree_uncommitted"}
            or entry.get("outcome_exposure_known") not in {"yes", "no", "unknown"}
            or not isinstance(entry.get("specification_ids"), list)
            or not entry.get("specification_ids")
            or not _meaningful_text(
                entry.get("outcome_exposure_basis"), minimum_length=12
            )
            or not _meaningful_text(entry.get("execution_history_claim"))
        ):
            raise ConfirmatoryStudyError(
                f"Stage-2 prior specification inventory entry {identifier} is incomplete"
            )
    snapshot = inventory.get("repository_snapshot")
    if (
        not isinstance(snapshot, Mapping)
        or not _is_git_sha(snapshot.get("head_commit"))
        or str(snapshot.get("head_commit")).lower() != expected_code_commit.lower()
        or snapshot.get("working_tree_state") not in {"clean", "dirty"}
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 prior specification inventory repository snapshot is invalid"
        )
    inspected_at = _finite_tz_timestamp(
        snapshot.get("inspected_at"), "inventory repository inspection timestamp"
    )
    if snapshot.get("working_tree_state") == "dirty" and not _is_sha256(
        snapshot.get("working_tree_porcelain_sha256")
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 dirty inventory snapshot lacks a bound porcelain hash"
        )
    if not inspected_at <= inventory_cutoff <= generated_at:
        raise ConfirmatoryStudyError(
            "Stage-2 prior specification inventory chronology is invalid"
        )
    return {
        "inspected_at": inspected_at,
        "inventory_cutoff_at": inventory_cutoff,
        "generated_at": generated_at,
        "inventory_cutoff_at_text": inventory["inventory_cutoff_at"],
        "generated_at_text": inventory["generated_at"],
        "entry_count": len(entries),
        "entries_sha256": inventory["entries_sha256"],
    }


def _git_repository_root() -> Path:
    module_path = Path(__file__).resolve()
    try:
        root_text = subprocess.run(
            ["git", "-C", str(module_path.parent), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ConfirmatoryStudyError("Stage-2 repository is not a verifiable Git worktree") from exc
    return Path(root_text)


def _verify_git_commit_object(code_revision: str) -> Path:
    root = _git_repository_root()
    try:
        subprocess.run(
            ["git", "-C", str(root), "cat-file", "-e", f"{code_revision}^{{commit}}"],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ConfirmatoryStudyError(
            "Stage-2 code_commit is not a verifiable Git commit object"
        ) from exc
    return root


def _verify_repository_commit(code_revision: str, *, require_clean: bool) -> None:
    root = _verify_git_commit_object(code_revision)
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip().lower()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ConfirmatoryStudyError(
            "Stage-2 code_commit is not a verifiable Git commit object"
        ) from exc
    if head != code_revision.lower():
        raise ConfirmatoryStudyError("Stage-2 code_commit is not the checked-out Git HEAD")
    if require_clean:
        try:
            status = subprocess.run(
                [
                    "git", "-C", str(root), "status", "--porcelain",
                    "--untracked-files=all",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ConfirmatoryStudyError(
                "Stage-2 repository cleanliness could not be verified"
            ) from exc
        if status:
            raise ConfirmatoryStudyError(
                "Stage-2 real-data execution requires a clean registered repository"
            )
        # ``git status`` intentionally omits ignored untracked paths.  A real
        # data run is bound to the complete checkout, so inspect Git's full
        # standard exclusion set (worktree .gitignore, .git/info/exclude and
        # core.excludesFile) as well.  ``git ls-files`` never descends into
        # the repository's own .git directory, avoiding false positives from
        # Git metadata such as .git/info/exclude itself.
        try:
            ignored_untracked = subprocess.run(
                [
                    "git", "-C", str(root), "ls-files", "--others", "--ignored",
                    "--exclude-standard", "-z",
                ],
                check=True,
                capture_output=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ConfirmatoryStudyError(
                "Stage-2 repository cleanliness could not be verified"
            ) from exc
        if ignored_untracked:
            raise ConfirmatoryStudyError(
                "Stage-2 real-data execution requires a clean registered repository"
            )


def _verify_stage2_runtime_contract(contract: Mapping[str, Any]) -> None:
    if contract != STAGE2_RUNTIME_CONTRACT:
        raise ConfirmatoryStudyError(
            "Stage-2 runtime contract differs from the frozen exact-version contract"
        )
    actual = {
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "pandas_version": pd.__version__,
    }
    expected = {
        key: STAGE2_RUNTIME_CONTRACT[key]
        for key in ("python_version", "numpy_version", "pandas_version")
    }
    if actual != expected:
        raise ConfirmatoryStudyError(
            f"Stage-2 runtime dependency versions differ from the frozen contract: "
            f"expected={expected}, actual={actual}"
        )


def _verify_coverage_probe_spec_commit_binding(
    *, agent_commit: str, spec_bytes: bytes, prior_inventory_bytes: bytes
) -> None:
    if not _is_git_sha(agent_commit):
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe agent_commit must be a lowercase Git SHA"
        )
    root = _verify_git_commit_object(agent_commit)
    required_blobs = (
        (
            STAGE2_COVERAGE_PROBE_REPOSITORY_PATH,
            spec_bytes,
            "fixed v2 specification",
        ),
        (
            STAGE2_COVERAGE_PROBE_INVENTORY_REPOSITORY_PATH,
            prior_inventory_bytes,
            "prior specification inventory",
        ),
    )
    for repository_path, expected_bytes, label in required_blobs:
        try:
            committed = subprocess.run(
                [
                    "git", "-C", str(root), "show",
                    f"{agent_commit}:{repository_path}",
                ],
                check=True,
                capture_output=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ConfirmatoryStudyError(
                "Stage-2 coverage probe agent_commit does not contain the "
                f"{label} blob"
            ) from exc
        if committed != expected_bytes:
            raise ConfirmatoryStudyError(
                "Stage-2 coverage probe agent_commit does not bind the exact "
                f"{label} bytes"
            )


def _valid_external_registration(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    for key in ("provider", "identifier", "registered_at", "verification_uri"):
        item = value.get(key)
        if not isinstance(item, str) or not item.strip():
            return False
        if any(token in item.lower() for token in ("fill", "todo", "pending", "placeholder")):
            return False
    for key in (
        "registered_content_sha256",
        "design_manifest_sha256",
        "registration_receipt_sha256",
        "execution_authorization_sha256",
    ):
        if not _is_sha256(value.get(key)):
            return False
    parsed = urlparse(value["verification_uri"])
    if parsed.scheme != "https" or not parsed.netloc:
        return False
    try:
        _finite_tz_timestamp(value["registered_at"], "registered_at")
    except ConfirmatoryStudyError:
        return False
    return True


def _finite_tz_timestamp(value: Any, label: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ConfirmatoryStudyError(f"Stage-2 {label} is invalid") from exc
    if pd.isna(timestamp) or timestamp.tzinfo is None:
        raise ConfirmatoryStudyError(
            f"Stage-2 {label} must be finite and timezone-aware"
        )
    return timestamp


def _validate_stage2_coverage_probe_spec(
    spec: Mapping[str, Any], *, expected_study_id: str
) -> None:
    """Validate the fixed v2 outcome-blind probe rather than trusting its label."""

    request = spec.get("request_protocol")
    selection = spec.get("selection_protocol")
    runtime = request.get("locked_runtime") if isinstance(request, Mapping) else None
    symbols = selection.get("symbols") if isinstance(selection, Mapping) else None
    symbol_values = (
        [row.get("symbol") for row in symbols]
        if isinstance(symbols, list)
        and all(isinstance(row, Mapping) for row in symbols)
        else None
    )
    if (
        spec.get("schema_version") != STAGE2_COVERAGE_PROBE_SPEC_SCHEMA_VERSION
        or spec.get("study_id") != expected_study_id
        or spec.get("probe_id") != STAGE2_COVERAGE_PROBE_ID
        or spec.get("status") != "specified_not_executed"
        or not isinstance(request, Mapping)
        or not isinstance(selection, Mapping)
        or symbol_values != STAGE2_COVERAGE_PROBE_SYMBOLS
        or request.get("dates") != STAGE2_COVERAGE_PROBE_DATES
        or request.get("expected_symbol_date_cells") != 24
        or request.get("provider_adapter")
        != STAGE2_COVERAGE_PROBE_PROVIDER_ADAPTER
        or request.get("provider_interface")
        != STAGE2_COVERAGE_PROBE_PROVIDER_INTERFACE
        or request.get("price_mode") != STAGE2_COVERAGE_PROBE_PRICE_MODE
        or request.get("akshare_adjust_argument")
        != STAGE2_COVERAGE_PROBE_ADJUST_ARGUMENT
        or request.get("frequency") != "daily"
        or request.get("lookup_names") is not False
        or request.get("full_market_discovery") is not False
        or request.get("database_write") is not False
        or request.get("qdata_dry_run") is not True
        or not isinstance(runtime, Mapping)
        or runtime.get("qdata_repository_commit")
        != STAGE2_COVERAGE_PROBE_QDATA_COMMIT
        or runtime.get("agent_repository_commit_rule")
        != STAGE2_COVERAGE_PROBE_AGENT_COMMIT_RULE
        or runtime.get("python_version") != STAGE2_COVERAGE_PROBE_PYTHON_VERSION
        or runtime.get("akshare_version") != STAGE2_COVERAGE_PROBE_AKSHARE_VERSION
        or runtime.get("clean_worktrees_required") is not True
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe specification differs from the fixed v2 contract"
        )
    if spec.get("supersedes") != STAGE2_COVERAGE_PROBE_V1_SUPERSEDES:
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe specification fixed v1 supersession is invalid"
        )
    if spec.get("stage2_design_boundary") != STAGE2_COVERAGE_PROBE_DESIGN_BOUNDARY:
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe specification design boundary differs from the "
            "fixed registered 18/72/1/28/29 design boundary"
        )
    execution_boundary = spec.get("execution_boundary")
    if (
        not isinstance(execution_boundary, Mapping)
        or execution_boundary.get("external_timestamp_required_before_execution")
        is not True
        or execution_boundary.get("must_not_execute_before_repository_commit")
        is not True
        or execution_boundary.get("required_commit_contents")
        != STAGE2_COVERAGE_PROBE_REQUIRED_COMMIT_CONTENTS
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe specification lacks the external timestamp gate "
            "or exact required commit contents"
        )

    receipt_schema = spec.get("public_receipt_schema")
    required_receipt_fields = {
        "schema_version",
        "study_id",
        "probe_id",
        "receipt_id",
        "spec_sha256",
        "status",
        "executed_at_utc",
        "external_timestamp_proof",
        "repository_state",
        "request",
        "artifacts",
        "coverage",
        "field_quality",
        "failures",
        "gates",
        "rights",
        "claim_boundaries",
    }
    if (
        not isinstance(receipt_schema, Mapping)
        or receipt_schema.get("additionalProperties") is not False
        or set(receipt_schema.get("required") or ()) != required_receipt_fields
        or not isinstance(receipt_schema.get("properties"), Mapping)
        or "external_timestamp_proof" not in receipt_schema["properties"]
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe specification has an incomplete receipt schema"
        )


def _validate_stage2_coverage_probe_receipt_content(
    receipt: Mapping[str, Any],
    *,
    expected_spec_sha256: str,
    expected_study_id: str,
) -> None:
    required_fields = {
        "schema_version",
        "study_id",
        "probe_id",
        "receipt_id",
        "spec_sha256",
        "status",
        "executed_at_utc",
        "external_timestamp_proof",
        "repository_state",
        "request",
        "artifacts",
        "coverage",
        "field_quality",
        "failures",
        "gates",
        "rights",
        "claim_boundaries",
    }
    if set(receipt) != required_fields:
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe receipt fields differ from the fixed v2 schema"
        )
    if receipt.get("schema_version") != STAGE2_COVERAGE_PROBE_RECEIPT_SCHEMA_VERSION:
        raise ConfirmatoryStudyError("unsupported Stage-2 coverage probe receipt schema")
    if receipt.get("study_id") != expected_study_id:
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe receipt has the wrong study identifier"
        )
    if receipt.get("probe_id") != STAGE2_COVERAGE_PROBE_ID:
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe receipt has the wrong probe identifier"
        )
    if receipt.get("spec_sha256") != expected_spec_sha256:
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe receipt specification hash is inconsistent"
        )

    unsigned = dict(receipt)
    unsigned.pop("receipt_id", None)
    expected_receipt_id = "sha256:" + _sha256(_canonical_bytes(unsigned))
    if receipt.get("receipt_id") != expected_receipt_id:
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe receipt identifier is not canonical"
        )
    if receipt.get("status") != "PASSED":
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe receipt must have PASSED status"
        )
    executed_at = _finite_tz_timestamp(
        receipt.get("executed_at_utc"), "coverage probe execution timestamp"
    )

    repository_state = receipt.get("repository_state")
    required_repository_fields = {
        "agent_commit",
        "qdata_commit",
        "agent_clean",
        "qdata_clean",
        "python_version",
        "akshare_version",
    }
    if (
        not isinstance(repository_state, Mapping)
        or set(repository_state) != required_repository_fields
        or not _is_git_sha(repository_state.get("agent_commit"))
        or repository_state.get("qdata_commit")
        != STAGE2_COVERAGE_PROBE_QDATA_COMMIT
        or repository_state.get("agent_clean") is not True
        or repository_state.get("qdata_clean") is not True
        or repository_state.get("python_version")
        != STAGE2_COVERAGE_PROBE_PYTHON_VERSION
        or repository_state.get("akshare_version")
        != STAGE2_COVERAGE_PROBE_AKSHARE_VERSION
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe receipt repository state is invalid"
        )

    request = receipt.get("request")
    required_request_fields = {
        "provider_adapter",
        "provider_interface",
        "upstream_provider_identity",
        "dates",
        "symbols",
        "price_mode",
        "adjust_argument",
    }
    if (
        not isinstance(request, Mapping)
        or set(request) != required_request_fields
        or request.get("provider_adapter")
        != STAGE2_COVERAGE_PROBE_PROVIDER_ADAPTER
        or request.get("provider_interface")
        != STAGE2_COVERAGE_PROBE_PROVIDER_INTERFACE
        or request.get("dates") != STAGE2_COVERAGE_PROBE_DATES
        or request.get("symbols") != STAGE2_COVERAGE_PROBE_SYMBOLS
        or request.get("price_mode") != STAGE2_COVERAGE_PROBE_PRICE_MODE
        or request.get("adjust_argument") != STAGE2_COVERAGE_PROBE_ADJUST_ARGUMENT
        or not _meaningful_text(request.get("upstream_provider_identity"))
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe receipt request scope, provider, or price mode differs "
            "from the fixed v2 specification"
        )

    artifacts = receipt.get("artifacts")
    artifact_fields = {
        "kind",
        "relative_path",
        "sha256",
        "size_bytes",
        "row_count",
        "symbol_count",
        "minimum_date",
        "maximum_date",
        "schema_sha256",
    }
    if not isinstance(artifacts, list) or not artifacts:
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe receipt private-artifact evidence is missing"
        )
    for artifact in artifacts:
        relative_path = artifact.get("relative_path") if isinstance(artifact, Mapping) else None
        if (
            not isinstance(artifact, Mapping)
            or set(artifact) != artifact_fields
            or artifact.get("kind")
            not in {"raw_private", "normalized_private", "request_log_private"}
            or not isinstance(relative_path, str)
            or not relative_path
            or relative_path.startswith("/")
            or (len(relative_path) > 1 and relative_path[1] == ":")
            or ".." in Path(relative_path).parts
            or not _is_sha256(artifact.get("sha256"))
            or not _is_sha256(artifact.get("schema_sha256"))
            or any(
                isinstance(artifact.get(key), bool)
                or not isinstance(artifact.get(key), int)
                or int(artifact[key]) < 0
                for key in ("size_bytes", "row_count", "symbol_count")
            )
            or int(artifact["symbol_count"]) > len(STAGE2_COVERAGE_PROBE_SYMBOLS)
        ):
            raise ConfirmatoryStudyError(
                "Stage-2 coverage probe receipt private-artifact evidence is invalid"
            )

    coverage = receipt.get("coverage")
    if coverage != {
        "expected_symbol_date_cells": 24,
        "observed_symbol_date_cells": 24,
        "missing_symbol_date_cells": [],
        "duplicate_symbol_date_cells": 0,
        "extra_symbol_date_cells": 0,
    }:
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe receipt does not establish complete fixed-scope coverage"
        )
    field_quality = receipt.get("field_quality")
    if (
        not isinstance(field_quality, Mapping)
        or not field_quality
        or any(value is not True for value in field_quality.values())
        or receipt.get("failures") != []
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe receipt field-quality or failure evidence is invalid"
        )

    required_gate_ids = {
        "SPEC_COMMITTED",
        "SPEC_EXTERNALLY_TIMESTAMPED",
        "CODE_STATE_CLEAN_AND_BOUND",
        "OUTPUT_TARGET_NEW",
        "RIGHTS_REVIEW_RECORDED",
        "EXACT_REQUEST_SCOPE",
        "COMPLETE_CELL_COVERAGE",
        "PROBE_SPECIFIC_RAW_BAR_FIELDS",
        "BASIC_VALUE_INTEGRITY",
        "RAW_MODE_ATTESTED",
        "FAILURES_ACCOUNTED_FOR",
        "ARTIFACT_HASHES_VERIFIED",
    }
    gates = receipt.get("gates")
    if (
        not isinstance(gates, Mapping)
        or set(gates) != required_gate_ids
        or any(gates[key] is not True for key in required_gate_ids)
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe receipt gates have not all passed"
        )
    rights = receipt.get("rights")
    if (
        not isinstance(rights, Mapping)
        or set(rights)
        != {
            "review_status",
            "raw_redistribution_allowed",
            "aggregate_receipt_publication_allowed",
        }
        or rights.get("review_status") != "verified"
        or not isinstance(rights.get("raw_redistribution_allowed"), bool)
        or rights.get("aggregate_receipt_publication_allowed") is not True
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe receipt rights do not permit use of the public receipt"
        )

    claim_boundary_keys = {
        "factor_outcome_claim_allowed",
        "portfolio_claim_allowed",
        "execution_semantics_verified",
        "tradability_verified",
        "fundamental_history_verified",
        "recorded_publication_date_specification_effect_verified",
        "exact_endpoint_resolution_verified",
        "endpoint_reason_ledger_integrity_verified",
        "historical_investor_observed_value_verified",
        "revision_history_verified",
        "vintage_value_history_verified",
        "announcement_reaction_verified",
    }
    claim_boundaries = receipt.get("claim_boundaries")
    if (
        not isinstance(claim_boundaries, Mapping)
        or set(claim_boundaries) != claim_boundary_keys
        or any(claim_boundaries[key] is not False for key in claim_boundary_keys)
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe receipt claim boundaries are not all closed"
        )

    proof = receipt.get("external_timestamp_proof")
    proof_fields = {
        "type",
        "provider",
        "identifier",
        "timestamped_at_utc",
        "verification_uri",
        "evidence_sha256",
        "subject_type",
        "subject_sha256",
        "verifier",
        "verified_at_utc",
        "trust_boundary",
    }
    if (
        not isinstance(proof, Mapping)
        or set(proof) != proof_fields
        or proof.get("type") != "human_verified_external_timestamp"
        or not _meaningful_text(proof.get("provider"))
        or not _meaningful_text(proof.get("identifier"))
        or not _meaningful_text(proof.get("verifier"))
        or not _meaningful_text(proof.get("trust_boundary"))
        or not _is_sha256(proof.get("evidence_sha256"))
        or proof.get("subject_type") != "coverage_probe_spec_sha256"
        or proof.get("subject_sha256") != expected_spec_sha256
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe external timestamp proof is invalid"
        )
    verification_uri = proof.get("verification_uri")
    parsed_uri = urlparse(verification_uri) if isinstance(verification_uri, str) else None
    if parsed_uri is None or parsed_uri.scheme != "https" or not parsed_uri.netloc:
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe external timestamp proof URI is invalid"
        )
    if proof.get("trust_boundary") != STAGE2_COVERAGE_PROBE_TIMESTAMP_TRUST_BOUNDARY:
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe external timestamp proof trust boundary is invalid"
        )
    timestamped_at = _finite_tz_timestamp(
        proof.get("timestamped_at_utc"), "coverage probe external timestamp"
    )
    verified_at = _finite_tz_timestamp(
        proof.get("verified_at_utc"), "coverage probe timestamp verification"
    )
    if timestamped_at > executed_at:
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe specification was not externally timestamped before "
            "probe execution"
        )
    if verified_at < timestamped_at:
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe timestamp verification chronology is invalid"
        )


def _validate_stage2_coverage_probe_receipt(
    *,
    spec_path: str | Path,
    receipt_path: str | Path,
    expected_study_id: str,
    prior_specification_inventory_path: str | Path | None = None,
    review_scope_cutoff_at: Any = None,
) -> dict[str, Any]:
    """Validate and bind the exact v2 probe specification and public receipt."""

    resolved_spec_path = _regular_file(spec_path, "coverage probe specification")
    resolved_receipt_path = _regular_file(receipt_path, "coverage probe receipt")
    resolved_inventory_path = _regular_file(
        prior_specification_inventory_path
        if prior_specification_inventory_path is not None
        else resolved_spec_path.with_name(STAGE2_COVERAGE_PROBE_PRIOR_INVENTORY_PATH),
        "prior specification inventory",
    )
    spec_bytes = resolved_spec_path.read_bytes()
    spec = _read_json_object(spec_bytes, "coverage probe specification")
    _validate_stage2_coverage_probe_spec(spec, expected_study_id=expected_study_id)
    receipt_bytes = resolved_receipt_path.read_bytes()
    receipt = _read_json_object(receipt_bytes, "coverage probe receipt")
    if receipt_bytes != _canonical_bytes(receipt):
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe receipt must be canonical JSON"
        )
    _validate_stage2_coverage_probe_receipt_content(
        receipt,
        expected_spec_sha256=_sha256(spec_bytes),
        expected_study_id=expected_study_id,
    )
    inventory_bytes = resolved_inventory_path.read_bytes()
    inventory = _read_json_object(
        inventory_bytes, "prior specification inventory"
    )
    agent_commit = str(receipt["repository_state"]["agent_commit"])
    if (
        inventory.get("schema_version") != "prior_specification_inventory_v1"
        or inventory.get("study_id") != expected_study_id
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 coverage probe prior specification inventory schema or study "
            "identifier is invalid"
        )
    _verify_coverage_probe_spec_commit_binding(
        agent_commit=agent_commit,
        spec_bytes=spec_bytes,
        prior_inventory_bytes=inventory_bytes,
    )
    if review_scope_cutoff_at is not None:
        executed_at = _finite_tz_timestamp(
            receipt.get("executed_at_utc"), "coverage probe execution timestamp"
        )
        review_cutoff = _finite_tz_timestamp(
            review_scope_cutoff_at, "data review scope cutoff timestamp"
        )
        if executed_at > review_cutoff:
            raise ConfirmatoryStudyError(
                "Stage-2 coverage probe execution occurred after the data review scope cutoff"
            )
    return receipt


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


def _validate_stage2_declaration(declaration: Mapping[str, Any]) -> None:
    if declaration.get("fundamental_contract") != STAGE2_FUNDAMENTAL_CONTRACT:
        raise ConfirmatoryStudyError(
            "Stage-2 data declaration does not attest the locked fundamental mapping and units"
        )
    if declaration.get("official_calendar_semantics") != (
        "Shanghai and Shenzhen common official open sessions; one unique row per session"
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 data declaration does not attest official-calendar semantics"
        )
    if declaration.get("quote_date_rule") != (
        "Every quote date must be a member of the bound official calendar"
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 data declaration does not bind quote dates to the official calendar"
        )


def _load_quotes(path: Path) -> pd.DataFrame:
    columns = ["date", "symbol", "close", "amount", "is_st", "is_suspended"]
    frame = pd.read_csv(path, usecols=columns, low_memory=False)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    if frame["date"].isna().any():
        raise ConfirmatoryStudyError("quotes contain missing quote dates")
    if frame["symbol"].isna().any() or frame["symbol"].astype(str).str.strip().eq("").any():
        raise ConfirmatoryStudyError("quotes contain missing symbols")
    frame["symbol"] = frame["symbol"].astype(str)
    for name in ("close", "amount"):
        parsed = pd.to_numeric(frame[name], errors="coerce")
        if parsed.isna().any():
            raise ConfirmatoryStudyError(
                "quotes contain missing or non-numeric quote values"
            )
        frame[name] = parsed
    for name in ("is_st", "is_suspended"):
        frame[name] = frame[name].map(_as_bool)
    if frame.duplicated(["date", "symbol"]).any():
        raise ConfirmatoryStudyError("quotes contain duplicate (date, symbol) keys")
    if (
        not np.isfinite(frame["close"]).all()
        or not np.isfinite(frame["amount"]).all()
    ):
        raise ConfirmatoryStudyError("quotes contain non-finite quote values")
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


def _load_stage2_fundamentals(path: Path) -> pd.DataFrame:
    """Validate the locked provider-field adapter and timing semantics."""

    columns = ["symbol", "roeDiluted", "publishDate", "reportPeriodEnd"]
    try:
        frame = pd.read_csv(path, usecols=columns, dtype=str, low_memory=False)
    except (ValueError, pd.errors.ParserError) as exc:
        raise ConfirmatoryStudyError(
            "Stage-2 fundamentals do not match the locked roeDiluted adapter"
        ) from exc

    raw_symbols = frame["symbol"].astype("string").str.strip()
    raw_report_periods = frame["reportPeriodEnd"].astype("string").str.strip()
    if (
        raw_symbols.isna().any()
        or raw_symbols.eq("").any()
        or raw_report_periods.isna().any()
        or raw_report_periods.eq("").any()
    ):
        raise ConfirmatoryStudyError(
            "Stage-2 fundamentals contain missing or invalid fundamental keys"
        )
    raw_keys = pd.DataFrame({
        "symbol": raw_symbols,
        "reportPeriodEnd": raw_report_periods,
    })
    if raw_keys.duplicated(["symbol", "reportPeriodEnd"], keep=False).any():
        raise ConfirmatoryStudyError(
            "Stage-2 fundamentals contain duplicate symbol-report periods without an explicit vintage schema"
        )

    parsed_report_periods = pd.to_datetime(raw_report_periods, errors="coerce")
    if parsed_report_periods.isna().any():
        raise ConfirmatoryStudyError(
            "Stage-2 fundamentals contain missing or invalid fundamental keys"
        )
    frame["symbol"] = raw_symbols.astype(str)
    frame["roe"] = pd.to_numeric(frame["roeDiluted"], errors="coerce")
    frame["publishDate"] = pd.to_datetime(frame["publishDate"], errors="coerce")
    frame["reportPeriodEnd"] = parsed_report_periods
    frame = (
        frame.dropna(subset=["roe"])
        .sort_values(["symbol", "reportPeriodEnd", "publishDate"], na_position="last")
    )
    if frame.empty:
        raise ConfirmatoryStudyError("fundamentals contain no usable ROE observations")
    impossible = frame["publishDate"].notna() & frame["publishDate"].lt(
        frame["reportPeriodEnd"]
    )
    if impossible.any():
        raise ConfirmatoryStudyError(
            "Stage-2 fundamentals contain publication dates before report-period end"
        )
    if frame.duplicated(["symbol", "reportPeriodEnd"], keep=False).any():
        raise ConfirmatoryStudyError(
            "Stage-2 fundamentals contain duplicate symbol-report periods without an explicit vintage schema"
        )
    return frame


def _load_official_calendar(path: Path) -> tuple[pd.Timestamp, ...]:
    frame = pd.read_csv(path, usecols=["date"], low_memory=False)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    if frame.empty or frame["date"].isna().any() or frame["date"].duplicated().any():
        raise ConfirmatoryStudyError(
            "official exchange calendar must contain unique, finite session dates"
        )
    dates = tuple(frame["date"].sort_values())
    if dates[0].to_period("M") > pd.Period("2009-01", freq="M") or dates[-1].to_period(
        "M"
    ) < pd.Period("2023-01", freq="M"):
        raise ConfirmatoryStudyError(
            "official exchange calendar does not span the fixed Stage-2 endpoints"
        )
    target_months = {date.to_period("M") for date in dates if date.year in range(2010, 2023)}
    if target_months != set(pd.period_range("2010-01", "2022-12", freq="M")):
        raise ConfirmatoryStudyError(
            "official exchange calendar does not cover every fixed Stage-2 month"
        )
    return dates


def _prepare_stage2_quotes(
    quotes: pd.DataFrame,
    *,
    official_calendar: Sequence[pd.Timestamp],
    horizon: int,
) -> pd.DataFrame:
    return _prepare_quotes(
        quotes,
        horizon,
        exchange_sessions=official_calendar,
    )


def _prepare_quotes(
    quotes: pd.DataFrame,
    horizon: int,
    *,
    exchange_sessions: Sequence[pd.Timestamp] | None = None,
) -> pd.DataFrame:
    if horizon <= 0:
        raise ConfirmatoryStudyError("forward_horizon_sessions must be positive")
    prepared = quotes.copy().sort_values(["symbol", "date"]).reset_index(drop=True)
    if any(column not in prepared for column in ("close", "amount")) or (
        not np.isfinite(pd.to_numeric(prepared["close"], errors="coerce")).all()
        or not np.isfinite(pd.to_numeric(prepared["amount"], errors="coerce")).all()
    ):
        raise ConfirmatoryStudyError("quotes contain non-finite quote values")
    sessions = (
        sorted(prepared["date"].drop_duplicates())
        if exchange_sessions is None
        else list(exchange_sessions)
    )
    if not sessions or len(sessions) != len(set(sessions)) or sessions != sorted(sessions):
        raise ConfirmatoryStudyError("exchange sessions must be unique and ordered")
    session_index = {day: index for index, day in enumerate(sessions)}
    mapped_sessions = prepared["date"].map(session_index)
    if mapped_sessions.isna().any():
        raise ConfirmatoryStudyError(
            "quote dates are not a subset of the bound official exchange calendar"
        )
    prepared["_exchange_session_index"] = mapped_sessions.astype(int)
    grouped_session = prepared.groupby("symbol", sort=False)["_exchange_session_index"]
    grouped_close = prepared.groupby("symbol", sort=False)["close"]
    previous_close = grouped_close.shift(1)
    previous_session = grouped_session.shift(1)
    prepared["return_1d"] = (
        prepared["close"] / previous_close - 1.0
    ).where(prepared["_exchange_session_index"] - previous_session == 1)

    close_60 = grouped_close.shift(60)
    session_60 = grouped_session.shift(60)
    prepared["momentum_60d"] = (
        prepared["close"] / close_60 - 1.0
    ).where(prepared["_exchange_session_index"] - session_60 == 60)

    low_volatility = -(
        prepared.groupby("symbol", sort=False)["return_1d"]
        .rolling(20, min_periods=20)
        .std()
        .reset_index(level=0, drop=True)
    )
    session_20_returns = grouped_session.shift(20)
    prepared["low_vol_20d"] = low_volatility.where(
        prepared["_exchange_session_index"] - session_20_returns == 20
    )

    close_by_session = prepared.set_index(
        ["symbol", "_exchange_session_index"]
    )["close"]

    def exact_close_at_session_offset(offset: int) -> pd.Series:
        target = pd.MultiIndex.from_arrays(
            [
                prepared["symbol"],
                prepared["_exchange_session_index"] + offset,
            ],
            names=("symbol", "_exchange_session_index"),
        )
        return pd.Series(
            close_by_session.reindex(target).to_numpy(),
            index=prepared.index,
            dtype=float,
        )

    future_close = exact_close_at_session_offset(horizon)
    same_exit_exact = future_close.notna()
    prepared["future_return_same"] = (
        future_close / prepared["close"] - 1.0
    ).where(same_exit_exact)
    if (
        same_exit_exact
        & ~np.isfinite(prepared["future_return_same"])
    ).any():
        raise ConfirmatoryStudyError(
            "exact forward endpoints produced a non-finite return"
        )
    prepared["future_return_same_reason"] = pd.Series(
        None, index=prepared.index, dtype=object
    )
    prepared.loc[
        ~same_exit_exact, "future_return_same_reason"
    ] = "MISSING_EXACT_FORWARD_EXIT"
    lag_entry_close = exact_close_at_session_offset(1)
    lag_exit_close = exact_close_at_session_offset(horizon + 1)
    lag_entry_exact = lag_entry_close.notna()
    lag_exit_exact = lag_exit_close.notna()
    prepared["future_return_lagged"] = (
        lag_exit_close / lag_entry_close - 1.0
    ).where(
        lag_entry_exact & lag_exit_exact
    )
    if (
        lag_entry_exact
        & lag_exit_exact
        & ~np.isfinite(prepared["future_return_lagged"])
    ).any():
        raise ConfirmatoryStudyError(
            "exact lagged endpoints produced a non-finite return"
        )
    prepared["future_return_lagged_reason"] = pd.Series(
        None, index=prepared.index, dtype=object
    )
    prepared.loc[
        ~lag_entry_exact, "future_return_lagged_reason"
    ] = "MISSING_EXACT_LAG_ENTRY"
    prepared.loc[
        lag_entry_exact & ~lag_exit_exact, "future_return_lagged_reason"
    ] = "MISSING_EXACT_LAG_EXIT"
    amount_20d = (
        prepared.groupby("symbol", sort=False)["amount"]
        .rolling(20, min_periods=20)
        .mean()
        .reset_index(level=0, drop=True)
    )
    session_20_amount = grouped_session.shift(19)
    prepared["amount_20d"] = amount_20d.where(
        prepared["_exchange_session_index"] - session_20_amount == 19
    )
    return prepared.sort_values(["date", "symbol"]).reset_index(drop=True)


def _monthly_rebalance_dates_from_calendar(
    official_calendar: Sequence[pd.Timestamp], start: str, end: str
) -> list[pd.Timestamp]:
    dates = pd.Series(
        [day for day in official_calendar if pd.Timestamp(start) <= day <= pd.Timestamp(end)],
        dtype="datetime64[ns]",
    ).sort_values()
    if dates.empty:
        raise ConfirmatoryStudyError("test period has no official exchange sessions")
    table = pd.DataFrame({"date": dates})
    result = list(table.groupby(table["date"].dt.to_period("M"))["date"].min())
    if len(result) != STAGE2_MINIMUM_REBALANCES:
        raise ConfirmatoryStudyError(
            "official exchange calendar does not yield all 156 registered rebalances"
        )
    return result


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


def _stage2_variant_cross_section(
    base: pd.DataFrame,
    *,
    day: pd.Timestamp,
    variant: Stage2VariantSpec,
    stock_master: pd.DataFrame,
    fundamentals: pd.DataFrame,
    minimum_amount: float,
) -> pd.DataFrame:
    stock_type = stock_master["stockType"].astype(str).str.strip()
    a_share = stock_type.eq("A股")
    symbols = stock_master["symbol"].astype(str).str.strip()
    supported_exchange = symbols.str.fullmatch(
        r"[0-9]{6}\.(?:SH|SZ)", na=False
    )
    scoped_master = stock_master.loc[a_share & supported_exchange]
    scoped_symbols = symbols.loc[scoped_master.index]
    if variant.universe_mode == "final_survivor":
        eligible_mask = (
            scoped_master["listDate"].le(day)
            & scoped_master["listStatus"].str.lower().ne("delisted")
            & scoped_master["delistDate"].isna()
        )
    else:
        eligible_mask = (
            scoped_master["listDate"].le(day)
            & (
                scoped_master["delistDate"].isna()
                | scoped_master["delistDate"].ge(day)
            )
        )
    eligible_symbols = set(scoped_symbols.loc[eligible_mask])
    quoted = base.copy()
    quoted["symbol"] = quoted["symbol"].astype(str).str.strip()
    missing_signal_quotes = sorted(
        eligible_symbols - set(quoted["symbol"])
    )
    if missing_signal_quotes:
        raise ConfirmatoryStudyError(
            "Stage-2 master-eligible universe is missing a signal-day quote: "
            f"date={day.date().isoformat()}, variant={variant.variant_id}, "
            f"missing_count={len(missing_signal_quotes)}, "
            f"missing_symbols={missing_signal_quotes[:10]}"
        )
    selected = quoted.loc[quoted["symbol"].isin(eligible_symbols)].copy()
    if "exclude_st" in variant.components:
        selected = selected.loc[selected["is_st"].eq(False)]
    if "exclude_suspended" in variant.components:
        selected = selected.loc[selected["is_suspended"].eq(False)]
    if "minimum_amount_20d" in variant.components:
        selected = selected.loc[selected["amount_20d"].ge(minimum_amount)]

    availability = (
        "publishDate"
        if variant.fundamental_availability == "publication_date"
        else "reportPeriodEnd"
    )
    available_mask = (
        fundamentals[availability].lt(day)
        if variant.fundamental_availability == "publication_date"
        else fundamentals[availability].le(day)
    )
    available = fundamentals.loc[available_mask].copy()
    staleness_cutoff = day - pd.DateOffset(
        months=int(STAGE2_FUNDAMENTAL_CONTRACT["maximum_staleness_months"])
    )
    available = available.loc[available["reportPeriodEnd"].ge(staleness_cutoff)]
    # Availability is a gate, not the record-selection ordering.  Once the
    # information set has been restricted, choose the latest accounting
    # period; a late vendor publishDate attached to an older period must not
    # displace a newer period that was already available.
    latest = (
        available.sort_values(["symbol", "reportPeriodEnd", availability])
        .drop_duplicates("symbol", keep="last")[[
            "symbol", "roe", "reportPeriodEnd", "publishDate"
        ]]
        .rename(columns={
            "reportPeriodEnd": "selected_report_period_end",
            "publishDate": "selected_publish_date",
        })
    )
    return selected.merge(latest, on="symbol", how="left", validate="one_to_one")


def _aggregate_results(observations: Sequence[Mapping[str, Any]], plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    frame = pd.DataFrame(
        observations,
        columns=(
            "date", "variant", "factor", "ic", "top_minus_universe",
            "cross_section_size",
        ),
    )
    nw_lag = int(plan.get("newey_west_lag", 3))
    if nw_lag < 0:
        raise ConfirmatoryStudyError("Newey-West lag cannot be negative")
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
                "newey_west_t_stat": _rounded_or_none(_newey_west_t_stat(ic, lag=nw_lag)),
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


def _stage2_evidence_status(
    *,
    declaration: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    minimum_symbols = int(plan["minimum_symbols"])
    expected_cells = len(plan["variants"]) * len(plan["factors"])
    registered_cells = {
        (variant["id"], factor)
        for variant in plan["variants"]
        for factor in plan["factors"]
    }
    by_date: dict[str, list[Mapping[str, Any]]] = {}
    for row in observations:
        by_date.setdefault(str(row.get("date")), []).append(row)
    complete_dates = []
    observed_sizes = []
    for day, rows in by_date.items():
        row_cells = {(row.get("variant"), row.get("factor")) for row in rows}
        valid = [
            row for row in rows
            if isinstance(row.get("ic"), (int, float))
            and not isinstance(row.get("ic"), bool)
            and math.isfinite(float(row["ic"]))
            and isinstance(row.get("top_minus_universe"), (int, float))
            and not isinstance(row.get("top_minus_universe"), bool)
            and math.isfinite(float(row["top_minus_universe"]))
            and int(row.get("cross_section_size", 0)) >= minimum_symbols
        ]
        observed_sizes.extend(int(row.get("cross_section_size", 0)) for row in rows)
        if (
            len(rows) == expected_cells
            and row_cells == registered_cells
            and len(valid) == expected_cells
        ):
            complete_dates.append(day)

    reasons = []
    if declaration["source_classification"] != "real_market_data":
        reasons.append("SYNTHETIC_DATA")
    if any(
        int((row.get("sample_audit") or {}).get("unresolved_endpoint_count", 0)) > 0
        for row in observations
    ):
        reasons.append("UNRESOLVED_FORWARD_ENDPOINTS")
    observed_months = {
        pd.Timestamp(day).to_period("M")
        for day in by_date
    }
    expected_months = set(pd.period_range("2010-01", "2022-12", freq="M"))
    if observed_months != expected_months:
        reasons.append("MISSING_REGISTERED_REBALANCES")
    if len(complete_dates) != len(by_date) or any(
        len(rows) != expected_cells for rows in by_date.values()
    ):
        reasons.append("INCOMPLETE_REGISTERED_MONTHLY_CELLS")
    if len(complete_dates) != int(plan["minimum_oos_rebalances"]):
        reasons.append("INSUFFICIENT_COMPLETE_REGISTERED_REBALANCES")
    code = (
        "INSUFFICIENT_EVIDENCE"
        if reasons
        else "REAL_MARKET_REGISTERED_HISTORICAL_IC_CORE_STATISTICS"
    )
    return {
        "code": code,
        "reason_codes": reasons,
        "runner_scope": "ic_core_only",
        "complete_registered_rebalance_count": len(complete_dates),
        "minimum_cross_section_size_observed": min(observed_sizes, default=0),
        "performance_claim": False,
        "generalization_claim": False,
        "usable_for_trading_decisions": False,
        "revision_history_claim": False,
        "vintage_value_claim": False,
        "historical_investor_observed_value_claim": False,
        "announcement_reaction_claim": False,
        "return_timing_claim": False,
        "portfolio_or_trading_claim": False,
        "caveats": [
            "Every registered monthly factor cell must be finite and meet the minimum cross-section size.",
            "The runner reports an IC core, not next-open portfolios, costs, turnover, or nonfills.",
            "The statistics are not evidence of implementable alpha or live-trading readiness.",
        ],
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
        character in "0123456789abcdef" for character in value
    )


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
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
    run_stage2 = subparsers.add_parser("run-stage2")
    for option in (
        "plan", "quotes", "stock-master", "fundamentals", "official-calendar",
        "data-declaration", "coverage-report", "coverage-probe-spec",
        "coverage-probe-receipt",
        "review-attestation",
        "design-manifest", "registration-receipt", "execution-authorization",
        "protocol-source", "statistical-analysis-plan",
        "prior-specification-inventory", "prior-exposure-log",
        "prior-exposure-attestation",
        "code-revision", "output-dir",
    ):
        run_stage2.add_argument(f"--{option}", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--receipt", required=True)
    verify_stage2 = subparsers.add_parser("verify-stage2")
    verify_stage2.add_argument("--receipt", required=True)
    verify_stage2.add_argument(
        "--endpoint-ledger",
        help=(
            "optional private endpoint-reason ledger; when supplied, verify its hash, "
            "canonical ordering, uniqueness, cardinality, and reason counts"
        ),
    )
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
    elif args.command == "run-stage2":
        receipt = run_stage2_confirmatory_study(
            plan_path=args.plan,
            quotes_path=args.quotes,
            stock_master_path=args.stock_master,
            fundamentals_path=args.fundamentals,
            official_calendar_path=args.official_calendar,
            data_declaration_path=args.data_declaration,
            coverage_report_path=args.coverage_report,
            coverage_probe_spec_path=args.coverage_probe_spec,
            coverage_probe_receipt_path=args.coverage_probe_receipt,
            review_attestation_path=args.review_attestation,
            design_manifest_path=args.design_manifest,
            registration_receipt_path=args.registration_receipt,
            execution_authorization_path=args.execution_authorization,
            protocol_source_path=args.protocol_source,
            statistical_analysis_plan_path=args.statistical_analysis_plan,
            prior_specification_inventory_path=args.prior_specification_inventory,
            prior_exposure_log_path=args.prior_exposure_log,
            prior_exposure_attestation_path=args.prior_exposure_attestation,
            code_revision=args.code_revision,
            output_dir=args.output_dir,
        )
        print(f"{receipt['status']['code']}: {args.output_dir}")
    elif args.command == "verify":
        receipt = verify_study_receipt(args.receipt)
        print(f"verified {receipt['study_id']}: {receipt['status']['code']}")
    elif args.command == "verify-stage2":
        receipt = verify_stage2_study_receipt(
            args.receipt, endpoint_ledger_path=args.endpoint_ledger
        )
        print(f"verified {receipt['study_id']}: {receipt['status']['code']}")
    else:
        status = write_public_evidence_status(args.receipt, args.output)
        print(f"{status['status']}: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
