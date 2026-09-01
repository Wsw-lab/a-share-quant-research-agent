from __future__ import annotations

import csv
from datetime import date, timedelta
import json
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from a_share_quant_agent.confirmatory_study import (
    ConfirmatoryStudyError,
    STAGE2_COMPONENTS,
    STAGE2_SCHEMA_VERSION,
    STAGE2_VARIANT_MASK_ORDER,
    _aggregate_results,
    _load_stage2_fundamentals,
    _stage2_evidence_status,
    _validate_prior_specification_inventory,
    _validate_stage2_plan,
    _verify_repository_commit,
    _prepare_quotes,
    build_public_evidence_status,
    run_confirmatory_study,
    run_stage2_confirmatory_study,
    run_stage2_registered_cells,
    stage2_registered_content_sha256,
    validate_stage2_variant_plan,
    verify_stage2_study_receipt,
    verify_study_receipt,
    write_public_evidence_status,
)
from a_share_quant_agent.stage2_estimands import build_registered_estimands


class ConfirmatoryStudyTest(unittest.TestCase):
    def test_locked_plan_reports_every_registered_result_without_best_pick(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _write_fixture(root, source_classification="synthetic_fixture")

            receipt = run_confirmatory_study(**paths, output_dir=root / "out")

            expected = 4 * 4
            self.assertEqual(len(receipt["results"]), expected)
            self.assertEqual(
                {(row["variant"], row["factor"]) for row in receipt["results"]},
                {
                    (variant, factor)
                    for variant in ("M0_naive", "M1_pit_universe", "M2_pit_publication", "M3_audited_lag")
                    for factor in ("roe", "momentum_60d", "low_vol_20d", "composite")
                },
            )
            self.assertEqual(receipt["selection_control"], {
                "all_registered_results_reported": True,
                "best_result_selected": False,
                "expected_result_count": expected,
                "reported_result_count": expected,
            })
            self.assertNotIn("best_strategy", json.dumps(receipt))
            self.assertEqual(receipt["status"]["code"], "INSUFFICIENT_EVIDENCE")
            self.assertFalse(receipt["status"]["performance_claim"])
            verify_study_receipt(root / "out" / "receipt.json")

    def test_real_market_status_requires_locked_plan_and_minimum_oos_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _write_fixture(root, source_classification="real_market_data")

            receipt = run_confirmatory_study(**paths, output_dir=root / "out")

            self.assertEqual(receipt["status"]["code"], "REAL_MARKET_OOS_STATISTICS")
            self.assertGreaterEqual(receipt["sample"]["test_rebalance_count"], 3)
            self.assertTrue(receipt["data"]["files"]["quotes"]["sha256"])
            self.assertFalse(receipt["data"]["redistributable"])
            self.assertFalse(receipt["status"]["performance_claim"])
            self.assertEqual(receipt["code"]["agent_git_sha"], "1" * 40)

    def test_unlocked_or_incomplete_plan_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _write_fixture(root, source_classification="real_market_data")
            plan = json.loads(paths["plan_path"].read_text(encoding="utf-8"))
            for mutation, pattern in (
                (lambda item: item.__setitem__("status", "draft"), "plan must be locked"),
                (lambda item: item["variants"].pop(), "registered variants"),
            ):
                with self.subTest(pattern=pattern):
                    changed = json.loads(json.dumps(plan))
                    mutation(changed)
                    paths["plan_path"].write_text(json.dumps(changed), encoding="utf-8")
                    with self.assertRaisesRegex(ConfirmatoryStudyError, pattern):
                        run_confirmatory_study(**paths, output_dir=root / pattern.replace(" ", "_"))

    def test_receipt_verifier_rejects_self_consistent_scope_or_claim_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _write_fixture(root, source_classification="real_market_data")
            run_confirmatory_study(**paths, output_dir=root / "out")
            original = json.loads((root / "out" / "receipt.json").read_text(encoding="utf-8"))

            for label, mutate, pattern in (
                (
                    "registered scope",
                    lambda receipt: (
                        receipt["plan"].__setitem__("registered_variants", ["M0_naive"]),
                        receipt["plan"].__setitem__("registered_factors", ["roe"]),
                        receipt.__setitem__("results", [receipt["results"][0]]),
                        receipt["selection_control"].update(
                            expected_result_count=1, reported_result_count=1
                        ),
                    ),
                    "maintained registered plan",
                ),
                (
                    "claim expansion",
                    lambda receipt: receipt["status"].__setitem__("performance_claim", True),
                    "claim flags",
                ),
            ):
                with self.subTest(label=label):
                    changed = json.loads(json.dumps(original))
                    mutate(changed)
                    changed.pop("receipt_integrity", None)
                    unsigned = (json.dumps(changed, sort_keys=True, separators=(",", ":")) + "\n").encode()
                    changed["receipt_integrity"] = {
                        "algorithm": "sha256",
                        "scope": "canonical_receipt_without_receipt_integrity",
                        "sha256": hashlib.sha256(unsigned).hexdigest(),
                    }
                    receipt_path = root / f"{label.replace(' ', '-')}.json"
                    receipt_path.write_text(
                        json.dumps(changed, sort_keys=True, separators=(",", ":")) + "\n",
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(ConfirmatoryStudyError, pattern):
                        verify_study_receipt(receipt_path)

    def test_public_status_is_derived_from_verified_receipts_not_legacy_registries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real_paths = _write_fixture(root / "real", source_classification="real_market_data")
            synthetic_paths = _write_fixture(root / "synthetic", source_classification="synthetic_fixture")
            run_confirmatory_study(**real_paths, output_dir=root / "real-out")
            run_confirmatory_study(**synthetic_paths, output_dir=root / "synthetic-out")

            status = build_public_evidence_status([
                root / "synthetic-out" / "receipt.json",
                root / "real-out" / "receipt.json",
            ])

            self.assertEqual(status["status"], "REAL_MARKET_OOS_STATISTICS")
            self.assertEqual(status["verified_receipt_count"], 2)
            self.assertEqual(status["source_of_truth"], "verified_confirmatory_receipts")
            self.assertFalse(status["performance_claim"])
            self.assertFalse(status["generalization_claim"])
            self.assertFalse(status["usable_for_trading_decisions"])
            self.assertNotIn("registry", status)

            status_path = root / "PUBLIC_EVIDENCE_STATUS.json"
            written = write_public_evidence_status(
                [
                    root / "synthetic-out" / "receipt.json",
                    root / "real-out" / "receipt.json",
                ],
                status_path,
            )
            self.assertEqual(written, status)
            self.assertEqual(
                status_path.read_bytes(),
                (json.dumps(status, sort_keys=True, separators=(",", ":")) + "\n").encode(),
            )

    def test_stage2_plan_requires_baseline_chain_and_complete_factorial(self) -> None:
        plan = _stage2_plan()

        variants = validate_stage2_variant_plan(plan)

        self.assertEqual(len(variants), 18)
        self.assertEqual(
            {variant.variant_id: (variant.universe_mode, variant.fundamental_availability)
             for variant in variants if variant.variant_id in {
                 "A0_final_report_end", "A1_pit_report_end", "I0000_pit_publication"
             }},
            {
                "A0_final_report_end": ("final_survivor", "report_period_end"),
                "A1_pit_report_end": ("point_in_time", "report_period_end"),
                "I0000_pit_publication": ("point_in_time", "publication_date"),
            },
        )
        self.assertEqual(
            {variant.components for variant in variants if variant.universe_mode == "point_in_time"
             and variant.fundamental_availability == "publication_date"},
            {
                frozenset(component for index, component in enumerate(STAGE2_COMPONENTS) if mask & (1 << index))
                for mask in range(16)
            },
        )

        renamed = json.loads(json.dumps(plan))
        renamed["variants"][0]["id"] = "renamed_after_lock"
        renamed["external_registration"]["registered_content_sha256"] = (
            stage2_registered_content_sha256(renamed)
        )
        with self.assertRaisesRegex(ConfirmatoryStudyError, "exact registered identifiers"):
            _validate_stage2_plan(renamed)

        missing_full_cell = json.loads(json.dumps(plan))
        missing_full_cell["variants"] = [
            variant
            for variant in missing_full_cell["variants"]
            if set(variant["components"]) != set(STAGE2_COMPONENTS)
        ]
        with self.assertRaisesRegex(ConfirmatoryStudyError, "complete 2\\^4 factorial"):
            validate_stage2_variant_plan(missing_full_cell)

        changed_baseline = json.loads(json.dumps(plan))
        next(
            variant
            for variant in changed_baseline["variants"]
            if variant["id"] == "A1_pit_report_end"
        )[
            "fundamental_availability"
        ] = "publication_date"
        with self.assertRaisesRegex(ConfirmatoryStudyError, "baseline chain"):
            validate_stage2_variant_plan(changed_baseline)

    def test_stage2_plan_rejects_relaxed_or_changed_fixed_contracts(self) -> None:
        mutations = (
            ("test_period", lambda plan: plan.__setitem__(
                "test_period", ["2024-01-01", "2024-07-31"]
            )),
            ("minimum_symbols", lambda plan: plan.__setitem__("minimum_symbols", 5)),
            ("minimum_oos_rebalances", lambda plan: plan.__setitem__(
                "minimum_oos_rebalances", 3
            )),
            ("composite_weights", lambda plan: plan["composite_weights"].__setitem__(
                "roe", 0.4
            )),
            ("fundamental_contract", lambda plan: plan["fundamental_contract"].__setitem__(
                "maximum_staleness_months", 36
            )),
            ("ic_outcome_clock", lambda plan: plan["ic_outcome_clock"].__setitem__(
                "missing_symbol_session_rule", "shift_to_next_row"
            )),
            ("planned_excluded_modules", lambda plan: plan[
                "planned_excluded_modules"
            ].__setitem__("status", "implemented")),
            ("deviation_reporting_module", lambda plan: plan[
                "deviation_reporting_module"
            ].__setitem__("status", "implemented")),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                plan = _stage2_plan()
                mutate(plan)
                plan["external_registration"]["registered_content_sha256"] = (
                    stage2_registered_content_sha256(plan)
                )
                with self.assertRaises(ConfirmatoryStudyError):
                    _validate_stage2_plan(plan)

        unbound = _stage2_plan()
        unbound["protocol_source_sha256"] = "9" * 64
        with self.assertRaisesRegex(ConfirmatoryStudyError, "not bound"):
            _validate_stage2_plan(unbound)

        with self.assertRaisesRegex(ConfirmatoryStudyError, "Git commit object"):
            _verify_repository_commit("1" * 40, require_clean=False)

    def test_stage2_runner_isolates_universe_publication_filters_and_lag(self) -> None:
        day = pd.Timestamp("2025-05-02")
        symbols = [f"{index:06d}.SZ" for index in range(1, 9)]
        base = pd.DataFrame({
            "date": [day] * len(symbols),
            "symbol": symbols,
            "is_st": [False, True, False, False, False, False, False, False],
            "is_suspended": [False, False, True, False, False, False, False, False],
            "amount_20d": [
                10_000_000.0, 10_000_000.0, 10_000_000.0, 1_000_000.0,
                10_000_000.0, 10_000_000.0, 10_000_000.0, 10_000_000.0,
            ],
            "momentum_60d": range(1, 9),
            "low_vol_20d": [2, 1, 4, 3, 6, 5, 8, 7],
            "future_return_same": [value / 100 for value in range(1, 9)],
            "future_return_lagged": [value / 100 for value in range(8, 0, -1)],
        })
        stock_master = pd.DataFrame({
            "symbol": symbols,
            "listDate": [pd.Timestamp("2010-01-01")] * len(symbols),
            "delistDate": [pd.Timestamp("2025-12-31")] + [pd.NaT] * 7,
            "listStatus": ["delisted"] + ["listed"] * 7,
            "stockType": ["A股"] * len(symbols),
        })
        fundamental_rows = []
        for index, symbol in enumerate(symbols, start=1):
            fundamental_rows.extend([
                {
                    "symbol": symbol,
                    "roe": float(index),
                    "publishDate": pd.Timestamp("2024-04-30"),
                    "reportPeriodEnd": pd.Timestamp("2023-12-31"),
                },
                {
                    "symbol": symbol,
                    "roe": float(9 - index),
                    "publishDate": day,
                    "reportPeriodEnd": pd.Timestamp("2024-12-31"),
                },
            ])
        fundamentals = pd.DataFrame(fundamental_rows)

        observations = run_stage2_registered_cells(
            prepared=base,
            stock_master=stock_master,
            fundamentals=fundamentals,
            rebalance_dates=[day],
            plan=_stage2_plan(),
        )

        self.assertEqual(len(observations), 18 * 4)
        roe = {
            row["variant"]: row
            for row in observations
            if row["factor"] == "roe"
        }
        self.assertEqual(roe["A0_final_report_end"]["cross_section_size"], 7)
        self.assertEqual(roe["A1_pit_report_end"]["cross_section_size"], 8)
        self.assertEqual(roe["I0000_pit_publication"]["cross_section_size"], 8)
        self.assertAlmostEqual(roe["A1_pit_report_end"]["ic"], -1.0)
        self.assertAlmostEqual(roe["I0000_pit_publication"]["ic"], 1.0)
        self.assertEqual(roe["I1000_st"]["cross_section_size"], 7)
        self.assertEqual(roe["I0100_suspension"]["cross_section_size"], 7)
        self.assertEqual(roe["I0010_liquidity"]["cross_section_size"], 7)
        self.assertEqual(roe["I1111_full_implementation"]["cross_section_size"], 5)
        self.assertAlmostEqual(roe["I0001_lag"]["ic"], -1.0)

    def test_stage2_forward_returns_do_not_wait_through_a_missing_exchange_session(self) -> None:
        rows = []
        for day, symbols in (
            ("2025-01-02", ("A", "B")),
            ("2025-01-03", ("A",)),
            ("2025-01-06", ("A", "B")),
            ("2025-01-07", ("A", "B")),
        ):
            for symbol in symbols:
                rows.append({
                    "date": pd.Timestamp(day),
                    "symbol": symbol,
                    "close": 10.0 + len(rows),
                    "amount": 1_000_000.0,
                    "is_st": False,
                    "is_suspended": False,
                })

        prepared = _prepare_quotes(pd.DataFrame(rows), horizon=1)

        first_b = prepared.loc[
            (prepared["date"] == pd.Timestamp("2025-01-02"))
            & (prepared["symbol"] == "B")
        ].iloc[0]
        self.assertTrue(pd.isna(first_b["future_return_same"]))

    def test_stage2_scope_rejects_bj_b_shares_funds_and_unsuffixed_symbols(self) -> None:
        day = pd.Timestamp("2020-06-01")
        valid = [f"{index:06d}.SZ" for index in range(1, 6)]
        rejected = [
            "830001.BJ",
            "000006",
            "900901.SH",
            "510300.SH",
            "000007.SZ",
            "12345.SZ",
        ]
        symbols = valid + rejected
        base = pd.DataFrame({
            "date": [day] * len(symbols),
            "symbol": symbols,
            "is_st": [False] * len(symbols),
            "is_suspended": [False] * len(symbols),
            "amount_20d": [10_000_000.0] * len(symbols),
            "momentum_60d": list(range(len(symbols))),
            "low_vol_20d": list(reversed(range(len(symbols)))),
            "future_return_same": [index / 100 for index in range(len(symbols))],
            "future_return_lagged": [index / 100 for index in range(len(symbols))],
        })
        stock_master = pd.DataFrame({
            "symbol": symbols,
            "listDate": [pd.Timestamp("2010-01-01")] * len(symbols),
            "delistDate": [pd.NaT] * len(symbols),
            "listStatus": ["listed"] * len(symbols),
            "stockType": ["A股"] * 7 + ["B股", "基金", "A-share", "A股"],
        })
        fundamentals = pd.DataFrame({
            "symbol": symbols,
            "roe": [0.05 + index / 100 for index in range(len(symbols))],
            "publishDate": [pd.Timestamp("2020-04-30")] * len(symbols),
            "reportPeriodEnd": [pd.Timestamp("2019-12-31")] * len(symbols),
        })

        rows = run_stage2_registered_cells(
            prepared=base,
            stock_master=stock_master,
            fundamentals=fundamentals,
            rebalance_dates=[day],
            plan=_stage2_plan(),
        )
        baseline = next(
            row for row in rows
            if row["variant"] == "I0000_pit_publication" and row["factor"] == "roe"
        )
        self.assertEqual(baseline["cross_section_size"], len(valid))

    def test_stage2_receipt_reports_all_factorial_cells_and_keeps_claim_gates_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _write_fixture(root, source_classification="synthetic_fixture")
            plan = _stage2_plan()
            paths = _bind_stage2_gate_artifacts(paths, plan)

            with patch(
                "a_share_quant_agent.confirmatory_study._validate_stage2_data_bindings"
            ):
                receipt = run_stage2_confirmatory_study(
                    **paths, output_dir=root / "out"
                )

            self.assertEqual(receipt["schema_version"], "confirmatory_study_receipt_v2")
            self.assertEqual(len(receipt["results"]), 18 * 4)
            self.assertEqual(receipt["selection_control"], {
                "all_registered_results_reported": True,
                "full_factorial_reported": True,
                "best_result_selected": False,
                "expected_result_count": 18 * 4,
                "reported_result_count": 18 * 4,
                "expected_monthly_observation_count": (
                    receipt["sample"]["test_rebalance_count"] * 18 * 4
                ),
                "reported_monthly_observation_count": len(receipt["monthly_observations"]),
            })
            self.assertEqual(
                [row["estimand_id"] for row in receipt["estimands"]["primary_family"]],
                [
                    "P1_roe_publication_signed_decrement",
                ],
            )
            self.assertEqual(
                receipt["estimands"]["secondary_publication_ic"]["estimand_id"],
                "S_composite_publication_signed_decrement",
            )
            self.assertEqual(len(receipt["estimands"]["secondary_paired_ic"]), 8)
            self.assertEqual(len(receipt["estimands"]["shapley_ic"]), 4)
            self.assertEqual(
                receipt["estimands"]["multiplicity_control"]["secondary_member_count"],
                25,
            )
            self.assertEqual(
                [row["factor"] for row in receipt["estimands"]["timing_negative_controls"]],
                ["momentum_60d", "low_vol_20d"],
            )
            self.assertTrue(
                all(
                    row["isolation_check_passed"]
                    for row in receipt["estimands"]["timing_negative_controls"]
                )
            )
            self.assertTrue(
                all(
                    row["absolute_tolerance"] == 1e-12
                    for row in receipt["estimands"]["timing_negative_controls"]
                )
            )
            self.assertTrue(
                all(
                    row["maximum_absolute_efficiency_residual"] < 1e-12
                    for row in receipt["estimands"]["shapley_ic"]
                )
            )
            self.assertFalse(
                any(row["claim_eligible"] for row in receipt["estimands"]["primary_family"])
            )
            self.assertFalse(receipt["status"]["performance_claim"])
            self.assertFalse(receipt["status"]["generalization_claim"])
            self.assertFalse(receipt["status"]["usable_for_trading_decisions"])
            self.assertFalse(receipt["status"]["revision_history_claim"])
            self.assertEqual(
                receipt["plan"]["content"]["external_registration"]["identifier"],
                "fixture-registration-v1",
            )
            self.assertEqual(
                receipt["plan"]["content"]["coverage_report_sha256"],
                plan["coverage_report_sha256"],
            )
            self.assertEqual(receipt["plan"]["content"]["newey_west_lag"], 3)
            self.assertEqual(
                receipt["plan"]["content"]["minimum_significance_months"], 120
            )
            self.assertEqual(
                receipt["plan"]["content"]["code_commit"], _current_git_sha()
            )
            self.assertEqual(
                receipt["plan"]["content"]["prior_exposure_attestation_sha256"],
                plan["prior_exposure_attestation_sha256"],
            )
            self.assertEqual(
                receipt["data"]["files"]["prior_exposure_log"]["sha256"],
                _sha256(paths["prior_exposure_log_path"]),
            )
            verify_stage2_study_receipt(root / "out" / "receipt.json")
            public_status = build_public_evidence_status(
                [root / "out" / "receipt.json"]
            )
            self.assertEqual(public_status["status"], "INSUFFICIENT_EVIDENCE")
            self.assertEqual(public_status["verified_receipt_count"], 1)

            changed = json.loads(
                (root / "out" / "receipt.json").read_text(encoding="utf-8")
            )
            changed["data"]["files"]["prior_exposure_log"]["sha256"] = "f" * 64
            _rewrite_receipt_integrity(changed)
            tampered_prior_log = root / "tampered-prior-log-v2.json"
            tampered_prior_log.write_text(
                json.dumps(changed, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfirmatoryStudyError, "design manifest"):
                verify_stage2_study_receipt(tampered_prior_log)

            changed = json.loads((root / "out" / "receipt.json").read_text(encoding="utf-8"))
            changed["status"]["performance_claim"] = True
            changed.pop("receipt_integrity")
            unsigned = (json.dumps(changed, sort_keys=True, separators=(",", ":")) + "\n").encode()
            changed["receipt_integrity"] = {
                "algorithm": "sha256",
                "scope": "canonical_receipt_without_receipt_integrity",
                "sha256": hashlib.sha256(unsigned).hexdigest(),
            }
            tampered = root / "tampered-v2.json"
            tampered.write_text(
                json.dumps(changed, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfirmatoryStudyError, "evidence status"):
                verify_stage2_study_receipt(tampered)

            changed = json.loads((root / "out" / "receipt.json").read_text(encoding="utf-8"))
            changed["estimands"]["primary_family"][0]["mean_difference"] = 999.0
            changed.pop("receipt_integrity")
            unsigned = (json.dumps(changed, sort_keys=True, separators=(",", ":")) + "\n").encode()
            changed["receipt_integrity"] = {
                "algorithm": "sha256",
                "scope": "canonical_receipt_without_receipt_integrity",
                "sha256": hashlib.sha256(unsigned).hexdigest(),
            }
            tampered_estimand = root / "tampered-estimand-v2.json"
            tampered_estimand.write_text(
                json.dumps(changed, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfirmatoryStudyError, "recomputed estimands"):
                verify_stage2_study_receipt(tampered_estimand)

            changed = json.loads((root / "out" / "receipt.json").read_text(encoding="utf-8"))
            changed["data"]["classification"] = "real_market_data"
            changed["status"]["code"] = (
                "REAL_MARKET_REGISTERED_HISTORICAL_IC_CORE_STATISTICS"
            )
            changed["status"]["reason_codes"] = []
            changed.pop("receipt_integrity")
            unsigned = (
                json.dumps(changed, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
            changed["receipt_integrity"] = {
                "algorithm": "sha256",
                "scope": "canonical_receipt_without_receipt_integrity",
                "sha256": hashlib.sha256(unsigned).hexdigest(),
            }
            tampered_status = root / "tampered-status-v2.json"
            tampered_status.write_text(
                json.dumps(changed, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ConfirmatoryStudyError, "data declaration classification"
            ):
                verify_stage2_study_receipt(tampered_status)

            changed = json.loads((root / "out" / "receipt.json").read_text(encoding="utf-8"))
            changed["monthly_observations"].pop()
            changed["selection_control"]["reported_monthly_observation_count"] -= 1
            changed.pop("receipt_integrity")
            unsigned = (
                json.dumps(changed, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
            changed["receipt_integrity"] = {
                "algorithm": "sha256",
                "scope": "canonical_receipt_without_receipt_integrity",
                "sha256": hashlib.sha256(unsigned).hexdigest(),
            }
            tampered_lattice = root / "tampered-lattice-v2.json"
            tampered_lattice.write_text(
                json.dumps(changed, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfirmatoryStudyError, "Cartesian lattice"):
                verify_stage2_study_receipt(tampered_lattice)

    def test_stage2_runner_embeds_canonical_registered_data_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _bind_stage2_gate_artifacts(
                _write_fixture(root, source_classification="synthetic_fixture"),
                _stage2_plan(),
            )

            with patch(
                "a_share_quant_agent.confirmatory_study._validate_stage2_data_bindings"
            ):
                receipt = run_stage2_confirmatory_study(
                    **paths, output_dir=root / "out"
                )

            self.assertIn("declaration", receipt["data"])
            package = receipt["data"]["declaration"]
            expected = json.loads(
                paths["data_declaration_path"].read_text(encoding="utf-8")
            )
            self.assertEqual(package["content"], expected)
            self.assertEqual(
                package["source_text"],
                paths["data_declaration_path"].read_bytes().decode("utf-8"),
            )
            self.assertEqual(
                package["source_file_sha256"],
                _sha256(paths["data_declaration_path"]),
            )
            canonical = (
                json.dumps(expected, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            ).encode("utf-8")
            self.assertEqual(
                package["canonical_sha256"], hashlib.sha256(canonical).hexdigest()
            )

    def test_stage2_runner_embeds_bound_official_calendar_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _bind_stage2_gate_artifacts(
                _write_fixture(root, source_classification="synthetic_fixture"),
                _stage2_plan(),
            )
            with patch(
                "a_share_quant_agent.confirmatory_study._validate_stage2_data_bindings"
            ):
                receipt = run_stage2_confirmatory_study(
                    **paths, output_dir=root / "out"
                )

            self.assertIn("official_calendar", receipt["data"])
            evidence = receipt["data"]["official_calendar"]
            expected_sessions = [
                row["date"]
                for row in csv.DictReader(
                    paths["official_calendar_path"].read_text(encoding="utf-8").splitlines()
                )
            ]
            self.assertEqual(evidence["session_dates"], expected_sessions)
            self.assertEqual(
                evidence["source_text"],
                paths["official_calendar_path"].read_bytes().decode("utf-8"),
            )
            canonical = (
                json.dumps(expected_sessions, sort_keys=True, separators=(",", ":"))
                + "\n"
            ).encode("utf-8")
            self.assertEqual(
                evidence["canonical_session_dates_sha256"],
                hashlib.sha256(canonical).hexdigest(),
            )
            self.assertEqual(
                evidence["source_file_sha256"], _sha256(paths["official_calendar_path"])
            )

    def test_stage2_verifier_rejects_nonfirst_session_rebalance_date_after_rehash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _bind_stage2_gate_artifacts(
                _write_fixture(root, source_classification="synthetic_fixture"),
                _stage2_plan(),
            )
            with patch(
                "a_share_quant_agent.confirmatory_study._validate_stage2_data_bindings"
            ):
                run_stage2_confirmatory_study(**paths, output_dir=root / "out")

            changed = json.loads(
                (root / "out" / "receipt.json").read_text(encoding="utf-8")
            )
            old_day = changed["sample"]["rebalance_dates"][0]
            calendar_days = [
                row["date"]
                for row in csv.DictReader(
                    paths["official_calendar_path"].read_text(encoding="utf-8").splitlines()
                )
            ]
            new_day = next(
                day for day in calendar_days
                if day[:7] == old_day[:7] and day > old_day
            )
            changed["sample"]["rebalance_dates"][0] = new_day
            for row in changed["monthly_observations"]:
                if row["date"] == old_day:
                    row["date"] = new_day
            _rewrite_receipt_integrity(changed)
            changed_path = root / "nonfirst-session-rebalance.json"
            changed_path.write_text(
                json.dumps(changed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfirmatoryStudyError, "first official session"):
                verify_stage2_study_receipt(changed_path)

    def test_stage2_verifier_rejects_rehashed_broken_registration_backlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _bind_stage2_gate_artifacts(
                _write_fixture(root, source_classification="synthetic_fixture"),
                _stage2_plan(),
            )
            with patch(
                "a_share_quant_agent.confirmatory_study._validate_stage2_data_bindings"
            ):
                run_stage2_confirmatory_study(**paths, output_dir=root / "out")

            changed = json.loads(
                (root / "out" / "receipt.json").read_text(encoding="utf-8")
            )
            registration_receipt = changed["registration_evidence"][
                "registration_receipt"
            ]
            registration_receipt["registered_artifact_sha256"] = "f" * 64
            registration_receipt_sha256 = hashlib.sha256(
                (
                    json.dumps(
                        registration_receipt,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode("utf-8")
            ).hexdigest()
            changed["plan"]["content"]["external_registration"][
                "registration_receipt_sha256"
            ] = registration_receipt_sha256
            changed["plan"]["canonical_sha256"] = hashlib.sha256(
                (
                    json.dumps(
                        changed["plan"]["content"],
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode("utf-8")
            ).hexdigest()
            changed["data"]["files"]["registration_receipt"][
                "sha256"
            ] = registration_receipt_sha256
            _rewrite_receipt_integrity(changed)
            changed_path = root / "broken-registration-backlink.json"
            changed_path.write_text(
                json.dumps(changed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ConfirmatoryStudyError, "registration receipt does not bind"
            ):
                verify_stage2_study_receipt(changed_path)

    def test_stage2_verifier_rejects_synthetic_to_real_upgrade_after_internal_rehash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _bind_stage2_gate_artifacts(
                _write_fixture(root, source_classification="synthetic_fixture"),
                _stage2_plan(),
            )
            with patch(
                "a_share_quant_agent.confirmatory_study._validate_stage2_data_bindings"
            ):
                run_stage2_confirmatory_study(**paths, output_dir=root / "out")

            forged = json.loads(
                (root / "out" / "receipt.json").read_text(encoding="utf-8")
            )
            _forge_stage2_receipt_as_real(forged, rewrite_declaration=False)
            forged_path = root / "forged-synthetic-as-real.json"
            forged_path.write_text(
                json.dumps(forged, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ConfirmatoryStudyError, "data declaration classification"
            ):
                verify_stage2_study_receipt(forged_path)

    def test_stage2_verifier_rejects_rehashed_declaration_content_without_source_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _bind_stage2_gate_artifacts(
                _write_fixture(root, source_classification="synthetic_fixture"),
                _stage2_plan(),
            )
            with patch(
                "a_share_quant_agent.confirmatory_study._validate_stage2_data_bindings"
            ):
                run_stage2_confirmatory_study(**paths, output_dir=root / "out")

            forged = json.loads(
                (root / "out" / "receipt.json").read_text(encoding="utf-8")
            )
            _forge_stage2_receipt_as_real(forged, rewrite_declaration=True)
            forged_path = root / "forged-declaration-content.json"
            forged_path.write_text(
                json.dumps(forged, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfirmatoryStudyError, "source text"):
                verify_stage2_study_receipt(forged_path)

    def test_stage2_verifier_rejects_rehashed_calendar_list_without_source_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _bind_stage2_gate_artifacts(
                _write_fixture(root, source_classification="synthetic_fixture"),
                _stage2_plan(),
            )
            with patch(
                "a_share_quant_agent.confirmatory_study._validate_stage2_data_bindings"
            ):
                run_stage2_confirmatory_study(**paths, output_dir=root / "out")

            changed = json.loads(
                (root / "out" / "receipt.json").read_text(encoding="utf-8")
            )
            old_day = changed["sample"]["rebalance_dates"][0]
            evidence = changed["data"]["official_calendar"]
            evidence["session_dates"].remove(old_day)
            evidence["session_count"] -= 1
            evidence["canonical_session_dates_sha256"] = hashlib.sha256(
                (
                    json.dumps(
                        evidence["session_dates"],
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode("utf-8")
            ).hexdigest()
            new_day = next(
                day for day in evidence["session_dates"] if day[:7] == old_day[:7]
            )
            changed["sample"]["rebalance_dates"][0] = new_day
            for row in changed["monthly_observations"]:
                if row["date"] == old_day:
                    row["date"] = new_day
            _rewrite_receipt_integrity(changed)
            changed_path = root / "forged-calendar-list.json"
            changed_path.write_text(
                json.dumps(changed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfirmatoryStudyError, "raw CSV"):
                verify_stage2_study_receipt(changed_path)

    def test_stage2_report_period_baseline_keeps_rows_without_publication_dates(self) -> None:
        day = pd.Timestamp("2020-06-01")
        symbols = [f"{index:06d}.SZ" for index in range(1, 7)]
        base = pd.DataFrame({
            "date": [day] * 6,
            "symbol": symbols,
            "is_st": [False] * 6,
            "is_suspended": [False] * 6,
            "amount_20d": [10_000_000.0] * 6,
            "momentum_60d": list(range(6)),
            "low_vol_20d": list(range(6)),
            "future_return_same": [value / 100 for value in range(6)],
            "future_return_lagged": [value / 100 for value in range(6)],
        })
        stock_master = pd.DataFrame({
            "symbol": symbols,
            "listDate": [pd.Timestamp("2010-01-01")] * 6,
            "delistDate": [pd.NaT] * 6,
            "listStatus": ["listed"] * 6,
            "stockType": ["A股"] * 6,
        })
        fundamentals = pd.DataFrame({
            "symbol": symbols,
            "roe": [0.1 + index / 100 for index in range(6)],
            "publishDate": [pd.Timestamp("2020-04-30")] * 5 + [pd.NaT],
            "reportPeriodEnd": [pd.Timestamp("2019-12-31")] * 6,
        })

        observations = run_stage2_registered_cells(
            prepared=base,
            stock_master=stock_master,
            fundamentals=fundamentals,
            rebalance_dates=[day],
            plan=_stage2_plan(),
        )
        roe = {
            row["variant"]: row
            for row in observations
            if row["factor"] == "roe"
        }
        self.assertGreater(
            roe["A1_pit_report_end"]["cross_section_size"],
            roe["I0000_pit_publication"]["cross_section_size"],
        )

    def test_stage2_run_rejects_an_unbound_coverage_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _write_fixture(root, source_classification="synthetic_fixture")
            plan = _stage2_plan()
            paths = _bind_stage2_gate_artifacts(paths, plan)
            changed = json.loads(paths["plan_path"].read_text(encoding="utf-8"))
            changed["coverage_report_sha256"] = "f" * 64
            changed["external_registration"]["registered_content_sha256"] = (
                stage2_registered_content_sha256(changed)
            )
            paths["plan_path"].write_text(json.dumps(changed, indent=2) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ConfirmatoryStudyError, "coverage report hash"):
                run_stage2_confirmatory_study(**paths, output_dir=root / "out")

    def test_stage2_run_recomputes_coverage_instead_of_trusting_gate_booleans(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _write_fixture(root, source_classification="synthetic_fixture")
            paths = _bind_stage2_gate_artifacts(paths, _stage2_plan())
            coverage_path = paths["coverage_report_path"]
            claimed = json.loads(coverage_path.read_text(encoding="utf-8"))
            claimed["gates"] = {
                "ready_to_lock_stage2_plan": True,
                "blocking_reason_codes": [],
            }
            coverage_path.write_text(
                json.dumps(claimed, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            plan = json.loads(paths["plan_path"].read_text(encoding="utf-8"))
            plan["coverage_report_sha256"] = _sha256(coverage_path)
            plan["external_registration"]["registered_content_sha256"] = (
                stage2_registered_content_sha256(plan)
            )
            paths["plan_path"].write_text(
                json.dumps(plan, indent=2) + "\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(
                ConfirmatoryStudyError, "recomputed raw-input coverage"
            ):
                run_stage2_confirmatory_study(**paths, output_dir=root / "out")

    def test_stage2_fundamental_adapter_enforces_source_field_and_timing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wrong_field = root / "wrong-field.csv"
            wrong_field.write_text(
                "symbol,roe,publishDate,reportPeriodEnd\n"
                "000001.SZ,0.1,2020-04-30,2019-12-31\n",
                encoding="utf-8",
            )
            with self.assertRaises(ConfirmatoryStudyError):
                _load_stage2_fundamentals(wrong_field)

            impossible_timing = root / "impossible-timing.csv"
            impossible_timing.write_text(
                "symbol,roeDiluted,publishDate,reportPeriodEnd\n"
                "000001.SZ,0.1,2019-12-01,2019-12-31\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfirmatoryStudyError, "before report-period"):
                _load_stage2_fundamentals(impossible_timing)

    def test_stage2_run_rejects_prior_outcome_exposure_even_when_rehashed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _write_fixture(root, source_classification="synthetic_fixture")
            plan = _stage2_plan()
            paths = _bind_stage2_gate_artifacts(paths, plan)
            exposure_path = paths["prior_exposure_attestation_path"]
            exposure = json.loads(exposure_path.read_text(encoding="utf-8"))
            exposure["stage2_factor_outcomes_previously_inspected"] = True
            exposure_path.write_text(json.dumps(exposure, indent=2) + "\n", encoding="utf-8")
            locked = json.loads(paths["plan_path"].read_text(encoding="utf-8"))
            locked["prior_exposure_attestation_sha256"] = _sha256(exposure_path)
            locked["external_registration"]["registered_content_sha256"] = (
                stage2_registered_content_sha256(locked)
            )
            paths["plan_path"].write_text(json.dumps(locked, indent=2) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ConfirmatoryStudyError, "prior outcome exposure"):
                with patch(
                    "a_share_quant_agent.confirmatory_study._validate_stage2_data_bindings"
                ):
                    run_stage2_confirmatory_study(**paths, output_dir=root / "out")

    def test_stage2_run_rejects_tampered_prior_exposure_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _bind_stage2_gate_artifacts(
                _write_fixture(root, source_classification="synthetic_fixture"),
                _stage2_plan(),
            )
            paths["prior_exposure_log_path"].write_text(
                "fixture log altered after attestation\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(ConfirmatoryStudyError, "prior exposure log"):
                with patch(
                    "a_share_quant_agent.confirmatory_study._validate_stage2_data_bindings"
                ):
                    run_stage2_confirmatory_study(**paths, output_dir=root / "out")

    def test_stage2_inventory_must_be_final_and_chronologically_bound(self) -> None:
        entries = [{
            "inventory_id": "fixture-prior-specification",
            "artifact_type": "locked_confirmatory_study_plan",
            "primary_path": "fixture/prior-plan.json",
            "present_in_repository": True,
            "repository_state": "tracked_at_head",
            "specification_ids": ["fixture-prior-specification"],
            "outcome_exposure_known": "unknown",
            "outcome_exposure_basis": (
                "The fixture does not establish whether prior outcomes were inspected."
            ),
            "execution_history_claim": "unknown",
        }]
        inventory = {
            "schema_version": "prior_specification_inventory_v1",
            "inventory_id": "fixture-prior-inventory",
            "study_id": "a-share-factor-timing-bias-decomposition-v2",
            "status": "manifest_eligible_outcome_blind",
            "inventory_cutoff_at": "2026-08-31T22:10:00+08:00",
            "generated_at": "2026-08-31T22:15:00+08:00",
            "prepared_by": "fixture preparer",
            "preparer_role": "fixture methods reviewer",
            "outcome_blind_inventory": True,
            "contains_outcome_values": False,
            "purpose": (
                "Enumerate every prior fixture specification without reporting outcome values."
            ),
            "repository_snapshot": {
                "head_commit": _current_git_sha(),
                "inspected_at": "2026-08-31T22:05:00+08:00",
                "working_tree_state": "clean",
            },
            "entry_count": len(entries),
            "entries_sha256": hashlib.sha256(
                (json.dumps(entries, sort_keys=True, separators=(",", ":")) + "\n").encode()
            ).hexdigest(),
            "entries": entries,
        }
        _validate_prior_specification_inventory(
            inventory,
            study_id=inventory["study_id"],
            expected_code_commit=_current_git_sha(),
        )

        for key, value, pattern in (
            ("status", "draft_incomplete_not_manifest_eligible", "manifest eligible"),
            ("inventory_cutoff_at", None, "timestamp"),
            ("prepared_by", None, "preparer"),
        ):
            with self.subTest(key=key):
                changed = json.loads(json.dumps(inventory))
                changed[key] = value
                with self.assertRaisesRegex(ConfirmatoryStudyError, pattern):
                    _validate_prior_specification_inventory(
                        changed,
                        study_id=inventory["study_id"],
                        expected_code_commit=_current_git_sha(),
                    )

        changed = json.loads(json.dumps(inventory))
        changed["generated_at"] = "2026-08-31T22:00:00+08:00"
        with self.assertRaisesRegex(ConfirmatoryStudyError, "chronology"):
            _validate_prior_specification_inventory(
                changed,
                study_id=inventory["study_id"],
                expected_code_commit=_current_git_sha(),
            )

    def test_stage2_run_rejects_draft_authorization_even_when_rehashed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _write_fixture(root, source_classification="synthetic_fixture")
            paths = _bind_stage2_gate_artifacts(paths, _stage2_plan())
            authorization_path = paths["execution_authorization_path"]
            authorization = json.loads(
                authorization_path.read_text(encoding="utf-8")
            )
            authorization["status"] = "draft_template_not_authorized"
            authorization_path.write_text(
                json.dumps(authorization, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            plan = json.loads(paths["plan_path"].read_text(encoding="utf-8"))
            plan["external_registration"]["execution_authorization_sha256"] = (
                _sha256(authorization_path)
            )
            paths["plan_path"].write_text(
                json.dumps(plan, indent=2) + "\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(
                ConfirmatoryStudyError, "authorization does not bind"
            ):
                with patch(
                    "a_share_quant_agent.confirmatory_study._validate_stage2_data_bindings"
                ):
                    run_stage2_confirmatory_study(**paths, output_dir=root / "out")

    def test_stage2_evidence_gate_uses_every_registered_monthly_cell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _write_fixture(root, source_classification="synthetic_fixture")
            plan = _stage2_plan()
            paths = _bind_stage2_gate_artifacts(paths, plan)

            with patch(
                "a_share_quant_agent.confirmatory_study._validate_stage2_data_bindings"
            ):
                receipt = run_stage2_confirmatory_study(
                    **paths, output_dir=root / "out"
                )

            self.assertEqual(receipt["status"]["code"], "INSUFFICIENT_EVIDENCE")
            self.assertIn(
                "INSUFFICIENT_COMPLETE_REGISTERED_REBALANCES",
                receipt["status"]["reason_codes"],
            )

    def test_stage2_evidence_gate_requires_reported_top_minus_universe_cells(self) -> None:
        plan = _stage2_plan()
        observations = [
            {
                "date": period.start_time.date().isoformat(),
                "variant": variant["id"],
                "factor": factor,
                "ic": 0.01,
                "top_minus_universe": 0.001,
                "cross_section_size": 1000,
            }
            for period in pd.period_range("2010-01", "2022-12", freq="M")
            for variant in plan["variants"]
            for factor in plan["factors"]
        ]
        declaration = {"source_classification": "real_market_data"}

        complete = _stage2_evidence_status(
            declaration=declaration, observations=observations, plan=plan
        )
        self.assertEqual(
            complete["code"],
            "REAL_MARKET_REGISTERED_HISTORICAL_IC_CORE_STATISTICS",
        )

        observations[0]["top_minus_universe"] = None
        incomplete = _stage2_evidence_status(
            declaration=declaration, observations=observations, plan=plan
        )
        self.assertIn(
            "INCOMPLETE_REGISTERED_MONTHLY_CELLS",
            incomplete["reason_codes"],
        )


def _write_fixture(root: Path, *, source_classification: str) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    symbols = [f"{index:06d}.SZ" for index in range(1, 9)]
    sessions = []
    current = date(2023, 1, 2)
    while len(sessions) < 430:
        if current.weekday() < 5:
            sessions.append(current)
        current += timedelta(days=1)

    quotes = root / "quotes.csv"
    with quotes.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "date", "symbol", "close", "amount", "is_st", "is_suspended",
        ))
        writer.writeheader()
        for day_index, session in enumerate(sessions):
            for symbol_index, symbol in enumerate(symbols):
                writer.writerow({
                    "date": session.isoformat(),
                    "symbol": symbol,
                    "close": f"{10 + symbol_index + day_index * (0.005 + symbol_index * 0.0004):.6f}",
                    "amount": 10_000_000 + symbol_index * 1_000_000,
                    "is_st": "False",
                    "is_suspended": "False",
                })

    stock_master = root / "stock_master.csv"
    with stock_master.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "symbol", "listDate", "delistDate", "listStatus", "stockType",
        ))
        writer.writeheader()
        for index, symbol in enumerate(symbols):
            writer.writerow({
                "symbol": symbol,
                "listDate": "2010-01-01",
                "delistDate": "2024-12-31" if index == 0 else "",
                "listStatus": "delisted" if index == 0 else "listed",
                "stockType": "A股",
            })

    fundamentals = root / "fundamentals.csv"
    with fundamentals.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "symbol", "roe", "publishDate", "reportPeriodEnd",
        ))
        writer.writeheader()
        for report_end, publish_date, offset in (
            ("2022-12-31", "2023-04-30", 0.00),
            ("2023-12-31", "2024-04-30", 0.01),
            ("2024-12-31", "2025-04-30", 0.02),
        ):
            for index, symbol in enumerate(symbols):
                writer.writerow({
                    "symbol": symbol,
                    "roe": f"{0.05 + index * 0.01 + offset:.4f}",
                    "publishDate": publish_date,
                    "reportPeriodEnd": report_end,
                })

    plan = {
        "schema_version": "confirmatory_factor_study_v1",
        "study_id": "pit-factor-replication-v1",
        "status": "locked",
        "locked_at": "2026-08-31T00:00:00+08:00",
        "train_period": ["2023-01-01", "2023-12-31"],
        "test_period": ["2024-01-01", "2024-08-30"],
        "rebalance_frequency": "monthly",
        "forward_horizon_sessions": 20,
        "minimum_amount": 5_000_000,
        "minimum_symbols": 5,
        "minimum_oos_rebalances": 3,
        "minimum_significance_months": 60,
        "newey_west_lag": 3,
        "factors": ["roe", "momentum_60d", "low_vol_20d", "composite"],
        "variants": ["M0_naive", "M1_pit_universe", "M2_pit_publication", "M3_audited_lag"],
        "composite_weights": {"roe": 0.5, "momentum_60d": 0.3, "low_vol_20d": 0.2},
    }
    plan_path = root / "plan.json"
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")

    declaration = {
        "source_classification": source_classification,
        "source_name": "test vendor" if source_classification == "real_market_data" else "deterministic fixture",
        "redistributable": False,
        "price_semantics": "vendor-adjusted close; factor-return research only",
        "rights_review": "local research use only",
    }
    declaration_path = root / "data_declaration.json"
    declaration_path.write_text(json.dumps(declaration, indent=2) + "\n", encoding="utf-8")

    return {
        "plan_path": plan_path,
        "quotes_path": quotes,
        "stock_master_path": stock_master,
        "fundamentals_path": fundamentals,
        "data_declaration_path": declaration_path,
        "code_revision": "1" * 40,
    }


def _current_git_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
    ).strip()


def _stage2_plan() -> dict[str, object]:
    variants: list[dict[str, object]] = [
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
    names = {
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
    for mask in STAGE2_VARIANT_MASK_ORDER:
        components = [
            component
            for index, component in enumerate(STAGE2_COMPONENTS)
            if mask & (1 << index)
        ]
        variants.append({
            "id": names[mask],
            "universe_mode": "point_in_time",
            "fundamental_availability": "publication_date",
            "components": components,
        })
    plan: dict[str, object] = {
        "schema_version": STAGE2_SCHEMA_VERSION,
        "design_contract_version": "stage2_design_contract_v1",
        "study_id": "a-share-factor-timing-bias-decomposition-v2",
        "status": "locked",
        "design_frozen_at": "2026-08-31T22:45:00+08:00",
        "locked_at": "2026-09-01T00:00:00+08:00",
        "runner_scope": "ic_core_only",
        "registration_semantics": {
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
        },
        "external_registration": {
            "provider": "fixture registry",
            "identifier": "fixture-registration-v1",
            "registered_at": "2026-08-31T23:00:00+08:00",
            "registered_content_sha256": "0" * 64,
            "design_manifest_sha256": "8" * 64,
            "registration_receipt_sha256": "9" * 64,
            "execution_authorization_sha256": "7" * 64,
            "verification_uri": "https://example.test/fixture-registration-v1",
        },
        "coverage_report_sha256": "a" * 64,
        "review_attestation_sha256": "b" * 64,
        "data_declaration_sha256": "1" * 64,
        "official_calendar_sha256": "2" * 64,
        "official_calendar_contract": {
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
        },
        "protocol_source_sha256": "c" * 64,
        "statistical_analysis_plan_sha256": "d" * 64,
        "prior_specification_inventory_sha256": "e" * 64,
        "prior_exposure_attestation_sha256": "f" * 64,
        "code_commit": _current_git_sha(),
        "train_period": ["2009-01-01", "2009-12-31"],
        "test_period": ["2010-01-01", "2022-12-31"],
        "rebalance_frequency": "monthly",
        "forward_horizon_sessions": 20,
        "minimum_amount": 5_000_000,
        "minimum_symbols": 1000,
        "minimum_oos_rebalances": 156,
        "minimum_significance_months": 120,
        "newey_west_lag": 3,
        "factors": ["roe", "momentum_60d", "low_vol_20d", "composite"],
        "variants": variants,
        "composite_weights": {"roe": 0.5, "momentum_60d": 0.3, "low_vol_20d": 0.2},
        "fundamental_contract": {
            "roe_source_field": "roeDiluted",
            "normalized_field": "roe",
            "unit": "decimal",
            "maximum_staleness_months": 18,
            "same_day_publication_usable": False,
            "duplicate_symbol_report_period_rule": "fail_closed",
        },
        "ic_outcome_clock": {
            "no_lag": "adjusted close t to adjusted close t+20 on official exchange sessions",
            "one_session_lag": "adjusted close t+1 to adjusted close t+21 on official exchange sessions",
            "missing_symbol_session_rule": "return_missing_do_not_shift_to_next_observed_symbol_row",
        },
        "inference": {
            "primary_estimand": "P1_roe_publication_signed_decrement",
            "primary_directional_prediction": "mean_less_than_zero",
            "reported_null_hypothesis": "two_sided_mean_equals_zero",
            "primary_multiplicity": "none_single_primary",
            "confidence_level": 0.95,
            "secondary_family_member_count": 25,
            "secondary_fdr": 0.1,
            "timing_isolation_absolute_tolerance": 1e-12,
            "missing_family_member_rule": "retain_in_denominator_and_treat_as_non_rejection",
        },
        "missingness": {
            "signal_imputation": "none",
            "composite_complete_case": True,
            "all_registered_monthly_cells_required_for_evidence_status": True,
        },
        "portfolio_module": {
            "status": "planned_unimplemented_excluded_from_this_runner",
            "required_before_claims": "separate externally registered and tested execution plan",
        },
        "deviation_reporting_module": {
            "status": "planned_unimplemented_excluded_from_this_runner",
            "current_boundary": (
                "The protocol requires manual disclosure, but the current runner and "
                "receipt do not create, bind, or verify a structured deviation log."
            ),
        },
        "planned_excluded_modules": {
            "status": "planned_unimplemented_excluded_from_this_runner",
            "items": [
                "dedicated_signal_missingness_tables",
                "per_security_exclusion_reason_codes",
                "eligible_universe_loss_output",
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
            ],
            "shapley_boundary": (
                "Exact four-component Shapley allocation preserves interactions but does not "
                "implement formal interaction tests."
            ),
        },
        "variants_source": (
            "Before design-manifest registration, copy the exact 18 variants from "
            "plan.draft.json, freeze their order in the plan core, and do not add, delete, "
            "or rename cells after design_frozen_at."
        ),
        "reporting_rule": (
            "Report every registered IC cell and exactly 26 inferential estimands (one "
            "primary plus 25 secondary family members), with two deterministic "
            "timing-isolation checks reported separately; cell-level means, Newey-West "
            "t-statistics, and top-minus-universe spreads are descriptive only and cannot "
            "support cell-specific discovery claims; do not select or headline a best result."
        ),
        "deviation_rule": (
            "Record every deviation without replacing the primary analysis; "
            "outcome-aware deviations are exploratory only."
        ),
    }
    plan["external_registration"]["registered_content_sha256"] = (
        stage2_registered_content_sha256(plan)
    )
    return plan


def _bind_stage2_gate_artifacts(
    paths: dict[str, Path],
    plan: dict[str, object],
) -> dict[str, Path]:
    root = paths["plan_path"].parent
    symbols = [f"{index:06d}.SZ" for index in range(1, 9)]
    sessions: list[date] = []
    current = date(2009, 1, 1)
    while current <= date(2023, 1, 31):
        if current.weekday() < 5:
            sessions.append(current)
        current += timedelta(days=1)

    official_calendar_path = root / "official_calendar.csv"
    with official_calendar_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("date",))
        writer.writeheader()
        for session in sessions:
            writer.writerow({"date": session.isoformat()})

    quotes_path = root / "stage2_quotes.csv"
    with quotes_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "date", "symbol", "close", "amount", "is_st", "is_suspended",
        ))
        writer.writeheader()
        for day_index, session in enumerate(sessions):
            for symbol_index, symbol in enumerate(symbols):
                writer.writerow({
                    "date": session.isoformat(),
                    "symbol": symbol,
                    "close": f"{10 + symbol_index + day_index * (0.002 + symbol_index * 0.0002):.6f}",
                    "amount": 10_000_000 + symbol_index * 1_000_000,
                    "is_st": "False",
                    "is_suspended": "False",
                })

    fundamentals_path = root / "stage2_fundamentals.csv"
    with fundamentals_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "symbol", "roeDiluted", "publishDate", "reportPeriodEnd",
        ))
        writer.writeheader()
        for year in range(2008, 2023):
            for index, symbol in enumerate(symbols):
                writer.writerow({
                    "symbol": symbol,
                    "roeDiluted": f"{0.05 + index * 0.01 + (year - 2008) * 0.0005:.6f}",
                    "publishDate": f"{year + 1}-04-30",
                    "reportPeriodEnd": f"{year}-12-31",
                })

    declaration = json.loads(paths["data_declaration_path"].read_text(encoding="utf-8"))
    declaration.update({
        "fundamental_contract": plan["fundamental_contract"],
        "official_calendar_semantics": (
            "Shanghai and Shenzhen common official open sessions; one unique row per session"
        ),
        "quote_date_rule": (
            "Every quote date must be a member of the bound official calendar"
        ),
    })
    paths["data_declaration_path"].write_text(
        json.dumps(declaration, indent=2) + "\n", encoding="utf-8"
    )
    paths = {
        **paths,
        "quotes_path": quotes_path,
        "fundamentals_path": fundamentals_path,
        "official_calendar_path": official_calendar_path,
        "code_revision": _current_git_sha(),
    }

    protocol_source_path = root / "protocol_source.md"
    statistical_analysis_plan_path = root / "sap.md"
    prior_specification_inventory_path = root / "prior_inventory.json"
    protocol_source_path.write_text("fixture protocol source\n", encoding="utf-8")
    statistical_analysis_plan_path.write_text("fixture statistical analysis plan\n", encoding="utf-8")
    entries = [{
        "inventory_id": "fixture-prior-specification",
        "artifact_type": "locked_confirmatory_study_plan",
        "primary_path": "fixture/prior-plan.json",
        "present_in_repository": True,
        "repository_state": "tracked_at_head",
        "specification_ids": ["fixture-prior-specification"],
        "outcome_exposure_known": "unknown",
        "outcome_exposure_basis": "The fixture does not establish whether prior outcomes were inspected.",
        "execution_history_claim": "unknown",
    }]
    inventory = {
        "schema_version": "prior_specification_inventory_v1",
        "inventory_id": "fixture-prior-inventory",
        "study_id": plan["study_id"],
        "status": "manifest_eligible_outcome_blind",
        "inventory_cutoff_at": "2026-08-31T22:10:00+08:00",
        "generated_at": "2026-08-31T22:15:00+08:00",
        "prepared_by": "fixture preparer",
        "preparer_role": "fixture methods reviewer",
        "outcome_blind_inventory": True,
        "contains_outcome_values": False,
        "purpose": "Enumerate every prior fixture specification without reporting outcome values.",
        "repository_snapshot": {
            "head_commit": paths["code_revision"],
            "inspected_at": "2026-08-31T22:05:00+08:00",
            "working_tree_state": "clean",
        },
        "entry_count": len(entries),
        "entries_sha256": hashlib.sha256(
            (json.dumps(entries, sort_keys=True, separators=(",", ":")) + "\n").encode()
        ).hexdigest(),
        "entries": entries,
    }
    prior_specification_inventory_path.write_text(
        json.dumps(inventory, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    plan["protocol_source_sha256"] = _sha256(protocol_source_path)
    plan["statistical_analysis_plan_sha256"] = _sha256(statistical_analysis_plan_path)
    plan["prior_specification_inventory_sha256"] = _sha256(
        prior_specification_inventory_path
    )
    plan["code_commit"] = paths["code_revision"]
    plan["data_declaration_sha256"] = _sha256(paths["data_declaration_path"])
    plan["official_calendar_sha256"] = _sha256(official_calendar_path)
    input_hashes = {
        "quotes": _sha256(quotes_path),
        "stock_master": _sha256(paths["stock_master_path"]),
        "fundamentals": _sha256(fundamentals_path),
        "official_calendar": _sha256(official_calendar_path),
    }
    attestation = {
        "schema_version": "stage2_data_review_attestation_v1",
        "study_id": plan["study_id"],
        "status": "reviewed_pass",
        "review_scope_cutoff_at": "2026-08-31T21:55:00+08:00",
        "execution_semantics_verified": True,
        "tradability_fields_verified": True,
        "data_rights_verified": True,
        "official_calendar_verified": True,
        "reviewed_at": "2026-08-31T22:00:00+08:00",
        "reviewer": "fixture-reviewer",
        "reviewer_role": "fixture methods reviewer",
        "reviewer_authority_basis": "Fixture data-contract custodian.",
        "input_file_sha256": input_hashes,
        "evidence_sha256": {
            "execution_semantics": "1" * 64,
            "tradability_fields": "2" * 64,
            "data_rights": "3" * 64,
            "official_calendar": "4" * 64,
        },
        "review_assertions": {
            "adjusted_close_return_semantics_and_corporate_action_handling_are_documented": True,
            "unadjusted_open_and_nonfill_semantics_are_not_claimed_by_the_ic_core": True,
            "amount_units_and_cutoff_timing_are_documented": True,
            "st_and_suspension_fields_are_non_degenerate_and_historically_effective": True,
            "licensed_local_analysis_is_permitted": True,
            "public_aggregate_outputs_metadata_and_hashes_are_permitted": True,
            "public_official_calendar_session_dates_are_permitted": True,
            "calendar_rows_are_unique_strictly_increasing_common_sse_szse_sessions": True,
            "calendar_covers_2009_01_through_2023_01_and_all_target_endpoints": True,
            "every_quote_date_is_a_calendar_member": True,
            "no_factor_ic_return_or_variant_ranking_was_reviewed": True,
        },
        "signature": {
            "type": "human_verified_evidence",
            "evidence_sha256": "5" * 64,
            "signer_identity": "fixture-reviewer",
            "verification_uri": "https://example.test/fixture-review",
            "trust_boundary": (
                "Identity and evidence authenticity require independent human verification."
            ),
        },
    }
    attestation_path = root / "review_attestation.json"
    attestation_path.write_text(
        json.dumps(attestation, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    plan["review_attestation_sha256"] = _sha256(attestation_path)
    coverage = {
        "schema_version": "study_v2_data_coverage_audit_v1",
        "fixture_only": True,
        "input_file_sha256": input_hashes,
        "gates": {"ready_to_lock_stage2_plan": False},
    }
    coverage_path = root / "coverage.json"
    coverage_path.write_text(
        json.dumps(coverage, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    plan["coverage_report_sha256"] = _sha256(coverage_path)
    prior_exposure_log_path = root / "prior_exposure_log.md"
    prior_exposure_log_path.write_text(
        "# Fixture prior-exposure log\n\nNo Stage-2 outcome values are included.\n",
        encoding="utf-8",
    )
    prior_exposure = {
        "schema_version": "stage2_prior_exposure_attestation_v1",
        "study_id": plan["study_id"],
        "status": "attested_outcome_blind",
        "analysis_period": plan["test_period"],
        "inventory_cutoff_at": inventory["inventory_cutoff_at"],
        "inventory_generated_at": inventory["generated_at"],
        "knowledge_cutoff_at": "2026-08-31T22:20:00+08:00",
        "stage2_factor_outcomes_previously_inspected": False,
        "attested_at": "2026-08-31T22:30:00+08:00",
        "attestor": "fixture-owner",
        "attestor_role": "repository owner",
        "attestor_authority_basis": "Fixture repository owner and study custodian.",
        "prior_specification_inventory_sha256": plan[
            "prior_specification_inventory_sha256"
        ],
        "prior_specification_entry_count": inventory["entry_count"],
        "prior_specification_entries_sha256": inventory["entries_sha256"],
        "prior_exposure_log_sha256": _sha256(prior_exposure_log_path),
        "protocol_source_sha256": plan["protocol_source_sha256"],
        "statistical_analysis_plan_sha256": plan[
            "statistical_analysis_plan_sha256"
        ],
        "coverage_report_sha256": plan["coverage_report_sha256"],
        "review_attestation_sha256": plan["review_attestation_sha256"],
        "data_declaration_sha256": plan["data_declaration_sha256"],
        "official_calendar_sha256": plan["official_calendar_sha256"],
        "code_commit": plan["code_commit"],
        "chronology_assertions": {
            "all_timestamps_are_timezone_aware": True,
            "inventory_cutoff_not_after_inventory_generation": True,
            "inventory_generation_not_after_knowledge_cutoff": True,
            "knowledge_cutoff_not_after_attestation": True,
            "data_review_completed_not_after_attestation": True,
            "attestation_will_precede_design_freeze": True,
            "blind_2010_2022_outcome_data_not_released_or_inspected_through_attested_at": True,
        },
        "statement": "Fixture attestation that no Stage-2 outcomes were inspected.",
        "signature": {
            "type": "human_verified_evidence",
            "evidence_sha256": "4" * 64,
            "signer_identity": "fixture-owner",
            "verification_uri": "https://example.test/fixture-owner-attestation",
            "trust_boundary": (
                "Identity and evidence authenticity require independent human verification."
            ),
        },
    }
    prior_exposure_attestation_path = (
        paths["plan_path"].parent / "prior_exposure_attestation.json"
    )
    prior_exposure_attestation_path.write_text(
        json.dumps(prior_exposure, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    plan["prior_exposure_attestation_sha256"] = _sha256(
        prior_exposure_attestation_path
    )
    plan["external_registration"]["registered_content_sha256"] = (
        stage2_registered_content_sha256(plan)
    )
    expected_artifacts = {
        key: plan[key]
        for key in (
            "data_declaration_sha256", "official_calendar_sha256",
            "coverage_report_sha256", "review_attestation_sha256",
            "protocol_source_sha256", "statistical_analysis_plan_sha256",
            "prior_specification_inventory_sha256",
            "prior_exposure_attestation_sha256",
        )
    }
    expected_artifacts["prior_exposure_log_sha256"] = _sha256(
        prior_exposure_log_path
    )
    design_manifest = {
        "schema_version": "stage2_design_manifest_v1",
        "study_id": plan["study_id"],
        "status": "frozen_outcome_blind",
        "design_frozen_at": plan["design_frozen_at"],
        "plan_core_sha256": plan["external_registration"]["registered_content_sha256"],
        "artifacts": expected_artifacts,
        "input_file_sha256": input_hashes,
        "code_commit": plan["code_commit"],
    }
    design_manifest_path = root / "design_manifest.json"
    design_manifest_path.write_text(
        json.dumps(design_manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    plan["external_registration"]["design_manifest_sha256"] = _sha256(
        design_manifest_path
    )
    registration_receipt = {
        "schema_version": "stage2_registration_receipt_v1",
        "study_id": plan["study_id"],
        "status": "registered_external",
        "provider": plan["external_registration"]["provider"],
        "identifier": plan["external_registration"]["identifier"],
        "registered_at": plan["external_registration"]["registered_at"],
        "recorded_at": "2026-08-31T23:05:00+08:00",
        "verification_uri": plan["external_registration"]["verification_uri"],
        "registered_artifact_type": (
            "stage2_design_manifest_v1_exact_bytes_or_sha256_digest"
        ),
        "registered_artifact_sha256": plan["external_registration"][
            "design_manifest_sha256"
        ],
        "proof": {
            "type": "human_verified_registry_record",
            "evidence_sha256": "5" * 64,
            "verifier": "fixture independent reviewer",
            "verified_at": "2026-08-31T23:10:00+08:00",
            "trust_boundary": (
                "The registry record has no offline-verifiable signature; authenticity "
                "requires independent human verification."
            ),
        },
    }
    registration_receipt_path = root / "registration_receipt.json"
    registration_receipt_path.write_text(
        json.dumps(registration_receipt, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    plan["external_registration"]["registration_receipt_sha256"] = _sha256(
        registration_receipt_path
    )
    execution_authorization = {
        "schema_version": "stage2_execution_authorization_v1",
        "study_id": plan["study_id"],
        "status": "authorized",
        "authorized_at": plan["locked_at"],
        "design_manifest_sha256": plan["external_registration"][
            "design_manifest_sha256"
        ],
        "registration_receipt_sha256": plan["external_registration"][
            "registration_receipt_sha256"
        ],
        "plan_core_sha256": plan["external_registration"][
            "registered_content_sha256"
        ],
        "bound_artifacts": {**expected_artifacts, "code_commit": plan["code_commit"]},
        "chronology": {
            "prior_inventory_cutoff_at": inventory["inventory_cutoff_at"],
            "prior_inventory_generated_at": inventory["generated_at"],
            "data_reviewed_at": attestation["reviewed_at"],
            "prior_exposure_attested_at": prior_exposure["attested_at"],
            "design_frozen_at": plan["design_frozen_at"],
            "externally_registered_at": plan["external_registration"]["registered_at"],
            "registration_recorded_at": registration_receipt["recorded_at"],
            "registration_verified_at": registration_receipt["proof"]["verified_at"],
            "authorized_at": plan["locked_at"],
        },
        "chronology_assertions": {
            "all_timestamps_are_timezone_aware": True,
            "inventory_cutoff_not_after_inventory_generation": True,
            "inventory_generation_not_after_prior_exposure_attestation": True,
            "data_review_not_after_design_freeze": True,
            "prior_exposure_attestation_not_after_design_freeze": True,
            "design_freeze_not_after_external_registration": True,
            "external_registration_not_after_receipt_recording": True,
            "receipt_recording_not_after_receipt_verification": True,
            "receipt_verification_not_after_authorization": True,
            "blind_2010_2022_outcome_data_not_released_or_inspected_before_authorization": True,
            "all_bound_hashes_recomputed_and_equal": True,
        },
        "release_scope": {
            "authorized_runner_scope": "ic_core_only",
            "authorized_analysis_period": plan["test_period"],
            "authorized_code_commit": plan["code_commit"],
            "outcome_data_release_permitted_after_authorized_at": True,
            "planned_excluded_modules_remain_unauthorized": [
                "dedicated_signal_missingness_tables",
                "per_security_exclusion_reason_codes",
                "eligible_universe_loss_output",
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
            ],
        },
        "authorizer": "fixture-authorizer",
        "authorizer_role": "independent methods reviewer",
        "statement": (
            "The registered fixture package is authorized for the fixed IC-core "
            "scope and timing chain."
        ),
        "signature": {
            "type": "human_verified_evidence",
            "evidence_sha256": "6" * 64,
            "signer_identity": "fixture-authorizer",
            "verification_uri": "https://example.test/fixture-authorization",
            "trust_boundary": (
                "Identity and evidence authenticity require independent human verification."
            ),
        },
    }
    execution_authorization_path = root / "execution_authorization.json"
    execution_authorization_path.write_text(
        json.dumps(execution_authorization, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    plan["external_registration"]["execution_authorization_sha256"] = _sha256(
        execution_authorization_path
    )
    paths["plan_path"].write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return {
        **paths,
        "coverage_report_path": coverage_path,
        "review_attestation_path": attestation_path,
        "design_manifest_path": design_manifest_path,
        "registration_receipt_path": registration_receipt_path,
        "execution_authorization_path": execution_authorization_path,
        "protocol_source_path": protocol_source_path,
        "statistical_analysis_plan_path": statistical_analysis_plan_path,
        "prior_specification_inventory_path": prior_specification_inventory_path,
        "prior_exposure_log_path": prior_exposure_log_path,
        "prior_exposure_attestation_path": prior_exposure_attestation_path,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rewrite_receipt_integrity(receipt: dict[str, object]) -> None:
    receipt.pop("receipt_integrity", None)
    unsigned = (
        json.dumps(
            receipt,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    receipt["receipt_integrity"] = {
        "algorithm": "sha256",
        "scope": "canonical_receipt_without_receipt_integrity",
        "sha256": hashlib.sha256(unsigned).hexdigest(),
    }


def _forge_stage2_receipt_as_real(
    receipt: dict[str, object], *, rewrite_declaration: bool
) -> None:
    data = receipt["data"]
    data["classification"] = "real_market_data"
    if rewrite_declaration:
        declaration = data["declaration"]["content"]
        declaration["source_classification"] = "real_market_data"
        data["declaration"]["canonical_sha256"] = hashlib.sha256(
            (
                json.dumps(
                    declaration,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
        ).hexdigest()
    for row in receipt["monthly_observations"]:
        row["cross_section_size"] = 1000
    plan = receipt["plan"]["content"]
    receipt["results"] = _aggregate_results(
        receipt["monthly_observations"],
        {
            "variants": [variant["id"] for variant in plan["variants"]],
            "factors": list(plan["factors"]),
            "newey_west_lag": int(plan["newey_west_lag"]),
        },
    )
    receipt["estimands"] = build_registered_estimands(
        receipt["monthly_observations"],
        plan=plan,
        nw_lag=int(plan["newey_west_lag"]),
        minimum_claim_months=int(plan["minimum_significance_months"]),
    )
    receipt["status"] = _stage2_evidence_status(
        declaration={"source_classification": "real_market_data"},
        observations=receipt["monthly_observations"],
        plan=plan,
    )
    receipt["status"]["revision_history_claim"] = False
    receipt["sample"]["symbol_count"] = 1000
    receipt["sample"]["complete_registered_rebalance_count"] = receipt["status"][
        "complete_registered_rebalance_count"
    ]
    _rewrite_receipt_integrity(receipt)


if __name__ == "__main__":
    unittest.main()
