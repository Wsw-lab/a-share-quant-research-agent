from __future__ import annotations

import builtins
import csv
from datetime import date, timedelta
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tracemalloc
import unittest
from unittest.mock import patch

import pandas as pd

import a_share_quant_agent.confirmatory_study as confirmatory_module
from a_share_quant_agent.confirmatory_study import (
    ConfirmatoryStudyError,
    STAGE2_AUTHORIZATION_ENDPOINT_BOUNDARY,
    STAGE2_COMPONENTS,
    STAGE2_ENDPOINT_RESOLUTION_CONTRACT,
    STAGE2_FUNDAMENTAL_CONTRACT,
    STAGE2_IC_OUTCOME_CLOCK,
    STAGE2_PRIVATE_DECLARATION_FIELDS,
    STAGE2_PRICE_ADJUSTMENT_CONTRACT,
    STAGE2_PRICE_ADJUSTMENT_CONVENTION,
    STAGE2_PRICE_ADJUSTMENT_METHOD,
    STAGE2_PUBLIC_DECLARATION_FIELDS,
    STAGE2_SCHEMA_VERSION,
    STAGE2_REPORTING_RULE,
    STAGE2_REGISTERED_DESIGN_ASSERTIONS,
    STAGE2_REGISTERED_SCOPE_SUMMARY,
    STAGE2_RANK_GROUP_CONTRACT,
    STAGE2_RESOLVED_ENDPOINT_CODE,
    STAGE2_SECURITY_IDENTIFIER_CONTRACT,
    STAGE2_SECURITY_IDENTIFIER_CONTRACT_TOKEN,
    STAGE2_TERMINAL_SURVIVOR_CUTOFF,
    STAGE2_UNIVERSE_CONTRACT,
    STAGE2_VARIANT_MASK_ORDER,
    _aggregate_results,
    _expected_stage2_public_embedding_consent,
    _load_quotes,
    _load_stage2_quotes,
    _load_stage2_fundamentals,
    _stage2_evidence_status,
    _stage2_rank_groups,
    _validate_prior_specification_inventory,
    _validate_stage2_public_receipt_privacy,
    _validate_stage2_coverage_probe_spec,
    _validate_stage2_coverage_probe_receipt,
    _validate_stage2_plan,
    _verify_repository_commit,
    _prepare_quotes,
    build_public_evidence_status,
    run_confirmatory_study,
    run_stage2_confirmatory_study,
    _run_stage2_registered_cells,
    stage2_registered_content_sha256,
    validate_stage2_variant_plan,
    verify_stage2_study_receipt,
    verify_study_receipt,
    write_public_evidence_status,
)
from a_share_quant_agent.stage2_estimands import (
    Stage2EstimandError,
    build_registered_estimands,
    verify_registered_estimands,
)
from a_share_quant_agent.data_access import (
    STAGE2_REQUIRED_FIELDS,
    stage2_public_source_projection_sha256,
)


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

    def test_legacy_real_market_run_is_rejected_before_outcome_load_or_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _write_fixture(root, source_classification="real_market_data")
            output = root / "out"

            with patch.object(confirmatory_module, "_load_quotes") as load_quotes:
                with self.assertRaisesRegex(
                    ConfirmatoryStudyError,
                    "legacy run accepts synthetic_fixture only",
                ):
                    run_confirmatory_study(**paths, output_dir=output)

            load_quotes.assert_not_called()
            self.assertFalse(output.exists())

    def test_legacy_cli_help_declares_the_synthetic_only_boundary(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "a_share_quant_agent.confirmatory_study",
                "run",
                "--help",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("synthetic_fixture", completed.stdout)
        self.assertIn("run-stage2", completed.stdout)
        self.assertIn("Real-market execution is rejected", completed.stdout)

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
            paths = _write_fixture(root, source_classification="synthetic_fixture")
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
            synthetic_paths = _write_fixture(root / "synthetic", source_classification="synthetic_fixture")
            run_confirmatory_study(**synthetic_paths, output_dir=root / "synthetic-out")
            historical_pilot_receipt = (
                Path(__file__).resolve().parents[1]
                / "evidence"
                / "pit_factor_replication_v1"
                / "receipt.json"
            )

            status = build_public_evidence_status([
                root / "synthetic-out" / "receipt.json",
                historical_pilot_receipt,
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
                    historical_pilot_receipt,
                ],
                status_path,
            )
            self.assertEqual(written, status)
            self.assertEqual(
                status_path.read_bytes(),
                (json.dumps(status, sort_keys=True, separators=(",", ":")) + "\n").encode(),
            )

    def test_rehashed_nonallowlisted_v1_receipt_cannot_promote_public_status(self) -> None:
        historical_pilot_receipt = (
            Path(__file__).resolve().parents[1]
            / "evidence"
            / "pit_factor_replication_v1"
            / "receipt.json"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            forged = json.loads(
                historical_pilot_receipt.read_text(encoding="utf-8")
            )
            # v1 integrity is self-asserted.  This harmless content mutation and
            # matching integrity rewrite demonstrate that structural v1
            # verification alone is not provenance.
            forged["data"]["source_name"] = "self-consistent-forged-v1"
            _rewrite_receipt_integrity(forged)
            forged_path = root / "forged-v1.json"
            forged_path.write_text(
                json.dumps(
                    forged,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )

            verified = verify_study_receipt(forged_path)
            self.assertEqual(
                verified["status"]["code"], "REAL_MARKET_OOS_STATISTICS"
            )
            public_status = build_public_evidence_status([forged_path])
            self.assertEqual(public_status["status"], "INSUFFICIENT_EVIDENCE")
            self.assertEqual(public_status["verified_receipt_count"], 1)

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
            ("minimum_amount_unit", lambda plan: plan.__setitem__(
                "minimum_amount_unit", "thousand_CNY"
            )),
            ("minimum_oos_rebalances", lambda plan: plan.__setitem__(
                "minimum_oos_rebalances", 3
            )),
            ("composite_weights", lambda plan: plan["composite_weights"].__setitem__(
                "roe", 0.4
            )),
            ("fundamental_contract", lambda plan: plan["fundamental_contract"].__setitem__(
                "maximum_staleness_months", 36
            )),
            ("quote_price_adjustment_contract", lambda plan: plan[
                "quote_price_adjustment_contract"
            ].__setitem__("price_adjustment_convention", "qfq")),
            ("security_identifier_contract", lambda plan: plan[
                "security_identifier_contract"
            ].__setitem__("contract_id", "extraction_current_symbol")),
            ("universe_contract", lambda plan: plan[
                "universe_contract"
            ].__setitem__("terminal_survivor_cutoff", "2099-12-31")),
            ("rank_group_contract", lambda plan: plan[
                "rank_group_contract"
            ].__setitem__("top_quintile_rule", "percentile_rank_greater_than_or_equal_to_0.8")),
            ("ic_outcome_clock", lambda plan: plan["ic_outcome_clock"].__setitem__(
                "missing_symbol_session_rule", "shift_to_next_row"
            )),
            ("planned_excluded_modules", lambda plan: plan[
                "planned_excluded_modules"
            ].__setitem__("status", "implemented")),
            ("deviation_reporting_module", lambda plan: plan[
                "deviation_reporting_module"
            ].__setitem__("status", "implemented")),
            ("claim_boundaries", lambda plan: plan[
                "claim_boundaries"
            ].__setitem__("revision_or_vintage_claim", True)),
            ("endpoint_resolution", lambda plan: plan[
                "endpoint_resolution"
            ].__setitem__("unresolved_rule", "silently_drop_security")),
            ("publication_exposure_diagnostics", lambda plan: plan[
                "publication_exposure_diagnostics"
            ].__setitem__("uses_forward_returns", True)),
            ("runtime_contract", lambda plan: plan[
                "runtime_contract"
            ].__setitem__("pandas_version", "0.0.0")),
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

    def test_stage2_plan_rejects_integer_aliases_for_fixed_booleans(self) -> None:
        fixed_boolean_paths = (
            ("claim_boundaries", "portfolio_or_trading_claim"),
            ("fundamental_contract", "same_day_publication_usable"),
            ("rank_group_contract", "percentile_rank"),
            ("missingness", "composite_complete_case"),
        )
        for object_name, field_name in fixed_boolean_paths:
            for integer_alias in (0, 1):
                with self.subTest(
                    object_name=object_name,
                    field_name=field_name,
                    integer_alias=integer_alias,
                ):
                    plan = _stage2_plan()
                    plan[object_name][field_name] = integer_alias
                    plan["external_registration"]["registered_content_sha256"] = (
                        stage2_registered_content_sha256(plan)
                    )
                    with self.assertRaisesRegex(
                        ConfirmatoryStudyError,
                        f"Stage-2 {object_name} differs",
                    ):
                        _validate_stage2_plan(plan)

    def test_stage2_plan_rejects_external_registration_extra_fields(self) -> None:
        plan = _stage2_plan()
        plan["external_registration"]["unregistered_payload"] = {
            "raw_rows": [1, 2, 3]
        }
        with self.assertRaisesRegex(
            ConfirmatoryStudyError,
            "external registration is missing or invalid",
        ):
            _validate_stage2_plan(plan)

    def test_stage2_public_embedding_consent_rejects_integer_boolean_aliases(self) -> None:
        for field_path in (
            ("approved",),
            ("privacy_assertions", "sensitive_material_excluded"),
            ("privacy_assertions", "local_filesystem_locations_excluded"),
            (
                "privacy_assertions",
                "identities_and_verification_uris_approved_for_publication",
            ),
        ):
            for integer_alias in (0, 1):
                with self.subTest(
                    field_path=field_path,
                    integer_alias=integer_alias,
                ):
                    plan = _stage2_plan()
                    consent = plan["public_receipt_embedding"]
                    target = consent
                    for key in field_path[:-1]:
                        target = target[key]
                    target[field_path[-1]] = integer_alias
                    plan["external_registration"]["registered_content_sha256"] = (
                        stage2_registered_content_sha256(plan)
                    )
                    with self.assertRaisesRegex(
                        ConfirmatoryStudyError,
                        "execution_plan public receipt embedding consent",
                    ):
                        _validate_stage2_plan(plan)

    def test_stage2_plan_accepts_canonical_protocol_contract(self) -> None:
        self.assertEqual(len(_validate_stage2_plan(_stage2_plan())), 18)

    def test_stage2_real_data_runtime_and_repository_gates_fail_closed(self) -> None:
        contract = dict(confirmatory_module.STAGE2_RUNTIME_CONTRACT)
        with patch.object(
            confirmatory_module.platform,
            "python_version",
            return_value="0.0.0",
        ):
            with self.assertRaisesRegex(
                ConfirmatoryStudyError, "runtime dependency versions"
            ):
                confirmatory_module._verify_stage2_runtime_contract(contract)

        commit = "a" * 40
        responses = [
            subprocess.CompletedProcess([], 0, stdout="/fixture/repo\n"),
            subprocess.CompletedProcess([], 0, stdout=b""),
            subprocess.CompletedProcess([], 0, stdout=commit + "\n"),
            subprocess.CompletedProcess([], 0, stdout="?? sitecustomize" + ".py\n"),
        ]
        with patch.object(
            confirmatory_module.subprocess,
            "run",
            side_effect=responses,
        ) as mocked_run:
            with self.assertRaisesRegex(
                ConfirmatoryStudyError, "clean registered repository"
            ):
                _verify_repository_commit(commit, require_clean=True)
        status_command = mocked_run.call_args_list[-1].args[0]
        self.assertNotIn("--", status_command)
        self.assertNotIn("src/a_share_quant_agent", status_command)

    def test_stage2_estimand_implementation_loads_before_any_execution_gate(self) -> None:
        import_events: list[str] = []
        original_import = builtins.__import__

        def tracking_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name.endswith("stage2_estimands"):
                import_events.append(name)
            return original_import(name, globals, locals, fromlist, level)

        repository = Path(__file__).resolve().parents[1]
        placeholder_paths = {
            key: repository / "does-not-need-to-exist"
            for key in (
                "plan_path", "quotes_path", "stock_master_path",
                "fundamentals_path", "official_calendar_path",
                "data_declaration_path", "data_rights_attestation_path",
                "coverage_report_path", "coverage_probe_spec_path",
                "coverage_probe_receipt_path", "review_attestation_path",
                "design_manifest_path", "registration_receipt_path",
                "execution_authorization_path", "protocol_source_path",
                "statistical_analysis_plan_path",
                "prior_specification_inventory_path", "prior_exposure_log_path",
                "prior_exposure_attestation_path",
            )
        }
        with patch.object(builtins, "__import__", side_effect=tracking_import):
            with self.assertRaises(ConfirmatoryStudyError):
                run_stage2_confirmatory_study(
                    **placeholder_paths,
                    authorization_consumption_dir=repository / ".unsafe-consumption",
                    code_revision="0" * 40,
                    output_dir=repository / ".unsafe-output",
                )
        self.assertTrue(
            import_events,
            "the registered estimand module must be fixed before path and repository gates",
        )

    def test_stage2_real_data_rechecks_registered_repository_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _bind_stage2_gate_artifacts(
                _write_fixture(root, source_classification="real_market_data"),
                _stage2_plan(),
            )
            with patch.object(
                confirmatory_module,
                "_verify_repository_commit",
            ) as repository_check, patch.object(
                confirmatory_module,
                "_verify_stage2_runtime_contract",
            ), patch.object(
                confirmatory_module,
                "_validate_stage2_data_bindings",
            ):
                run_stage2_confirmatory_study(
                    **paths,
                    output_dir=root / "out",
                )
        self.assertEqual(repository_check.call_count, 2)
        for call in repository_check.call_args_list:
            self.assertTrue(call.kwargs["require_clean"])

    def test_stage2_repository_gate_rejects_untracked_files_hidden_by_git_excludes(self) -> None:
        cases = (
            ("worktree gitignore", "sitecustomize.pyc", "*.py[cod]\n"),
            ("git info exclude", "info-hidden.bin", "info-hidden.bin\n"),
            ("global excludes file", "global-hidden.bin", "global-hidden.bin\n"),
        )
        for label, hidden_name, ignore_pattern in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                repository = base / "repository"
                subprocess.run(
                    ["git", "init", "--quiet", str(repository)],
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    ["git", "-C", str(repository), "config", "user.name", "Fixture Author"],
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    [
                        "git", "-C", str(repository), "config", "user.email",
                        "fixture@example.test",
                    ],
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    ["git", "-C", str(repository), "config", "commit.gpgSign", "false"],
                    check=True,
                    capture_output=True,
                )
                (repository / ".gitignore").write_text(
                    ignore_pattern if label == "worktree gitignore" else "*.py[cod]\n",
                    encoding="utf-8",
                )
                (repository / "tracked.txt").write_text("fixture\n", encoding="utf-8")
                subprocess.run(
                    ["git", "-C", str(repository), "add", ".gitignore", "tracked.txt"],
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    ["git", "-C", str(repository), "commit", "--quiet", "-m", "fixture"],
                    check=True,
                    capture_output=True,
                )
                if label == "git info exclude":
                    (repository / ".git" / "info" / "exclude").write_text(
                        ignore_pattern,
                        encoding="utf-8",
                    )
                elif label == "global excludes file":
                    global_excludes = base / "global-excludes"
                    global_excludes.write_text(ignore_pattern, encoding="utf-8")
                    subprocess.run(
                        [
                            "git", "-C", str(repository), "config", "core.excludesFile",
                            str(global_excludes),
                        ],
                        check=True,
                        capture_output=True,
                    )
                commit = subprocess.run(
                    ["git", "-C", str(repository), "rev-parse", "HEAD"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()

                with patch.object(
                    confirmatory_module,
                    "_verify_git_commit_object",
                    return_value=repository,
                ):
                    # Repository-internal Git metadata must not count as study files.
                    _verify_repository_commit(commit, require_clean=True)
                    (repository / hidden_name).write_bytes(b"hidden fixture\n")
                    with self.assertRaisesRegex(
                        ConfirmatoryStudyError, "clean registered repository"
                    ):
                        _verify_repository_commit(commit, require_clean=True)

    def test_stage2_evidence_validators_accept_only_explicit_human_verification(self) -> None:
        attestation = {
            "type": "human_verified_evidence",
            "evidence_sha256": "1" * 64,
            "signer_identity": "independent fixture reviewer",
            "verification_uri": "https://example.test/attestation",
            "trust_boundary": (
                "Identity and evidence authenticity require independent human verification."
            ),
        }
        confirmatory_module._validate_attestation_signature(
            attestation, "fixture attestation"
        )
        for proof_type in (None, "detached_digital_signature", "external_registry_attestation"):
            with self.subTest(attestation_type=proof_type):
                changed = dict(attestation, type=proof_type)
                with self.assertRaisesRegex(
                    ConfirmatoryStudyError, "only explicit human-verified evidence"
                ):
                    confirmatory_module._validate_attestation_signature(
                        changed, "fixture attestation"
                    )

        registration = {
            "type": "human_verified_registry_record",
            "evidence_sha256": "2" * 64,
            "verifier": "independent fixture reviewer",
            "trust_boundary": (
                "The registry record has no offline-verifiable signature; authenticity "
                "requires independent human verification."
            ),
        }
        confirmatory_module._validate_registration_proof(registration)
        for proof_type in (None, "detached_digital_signature", "registry_inclusion_proof"):
            with self.subTest(registration_type=proof_type):
                changed = dict(registration, type=proof_type)
                with self.assertRaisesRegex(
                    ConfirmatoryStudyError, "only an explicit human-verified registry"
                ):
                    confirmatory_module._validate_registration_proof(changed)

    def test_stage2_publication_variant_filters_availability_before_selecting_latest_report_period(self) -> None:
        day = pd.Timestamp("2025-06-02")
        symbols = [f"{index:06d}.SZ" for index in range(1, 7)]
        base = pd.DataFrame({
            "date": [day] * len(symbols),
            "symbol": symbols,
            "is_st": [False] * len(symbols),
            "is_suspended": [False] * len(symbols),
            "amount_20d": [10_000_000.0] * len(symbols),
            "momentum_60d": list(range(1, 7)),
            "low_vol_20d": list(range(6, 0, -1)),
            "future_return_same": [value / 100 for value in range(1, 7)],
            "future_return_lagged": [value / 100 for value in range(1, 7)],
        })
        stock_master = pd.DataFrame({
            "symbol": symbols,
            "listDate": [pd.Timestamp("2010-01-01")] * len(symbols),
            "delistDate": [pd.NaT] * len(symbols),
            "listStatus": ["listed"] * len(symbols),
            "stockType": ["A股"] * len(symbols),
        })
        fundamentals = []
        for index, symbol in enumerate(symbols, start=1):
            fundamentals.extend([
                {
                    # This older accounting period has the later recorded publishDate.
                    # It must not override the newer already-published accounting period.
                    "symbol": symbol,
                    "roe": float(7 - index),
                    "publishDate": pd.Timestamp("2025-05-30"),
                    "reportPeriodEnd": pd.Timestamp("2023-12-31"),
                },
                {
                    "symbol": symbol,
                    "roe": float(index),
                    "publishDate": pd.Timestamp("2025-04-30"),
                    "reportPeriodEnd": pd.Timestamp("2024-12-31"),
                },
                {
                    # Date-only same-day publication remains unavailable at day t.
                    "symbol": symbol,
                    "roe": float(7 - index),
                    "publishDate": day,
                    "reportPeriodEnd": pd.Timestamp("2025-03-31"),
                },
            ])

        observations = _run_stage2_registered_cells(
            prepared=_stage2_prepared_with_close_types(base),
            stock_master=stock_master,
            fundamentals=pd.DataFrame(fundamentals),
            rebalance_dates=[day],
            plan=_stage2_plan(),
        )

        publication_roe = next(
            row for row in observations
            if row["variant"] == "I0000_pit_publication" and row["factor"] == "roe"
        )
        self.assertAlmostEqual(publication_roe["ic"], 1.0)

    def test_stage2_candidate_is_active_master_intersect_signal_day_quotes(self) -> None:
        day = pd.Timestamp("2025-06-02")
        symbols = [f"{index:06d}.SZ" for index in range(1, 7)]
        quoted_symbols = symbols[:-1]
        base = pd.DataFrame({
            "date": [day] * len(quoted_symbols),
            "symbol": quoted_symbols,
            "is_st": [False] * len(quoted_symbols),
            "is_suspended": [False] * len(quoted_symbols),
            "amount_20d": [10_000_000.0] * len(quoted_symbols),
            "momentum_60d": list(range(1, len(quoted_symbols) + 1)),
            "low_vol_20d": list(range(len(quoted_symbols), 0, -1)),
            "future_return_same": [0.01, 0.02, 0.03, 0.04, 0.05],
            "future_return_lagged": [0.01, 0.02, 0.03, 0.04, 0.05],
        })
        stock_master = pd.DataFrame({
            "symbol": symbols,
            "listDate": [pd.Timestamp("2010-01-01")] * len(symbols),
            "delistDate": [pd.NaT] * len(symbols),
            "listStatus": ["listed"] * len(symbols),
            "stockType": ["A股"] * len(symbols),
        })
        fundamentals = pd.DataFrame({
            "symbol": symbols,
            "roe": [value / 100 for value in range(1, len(symbols) + 1)],
            "publishDate": [pd.Timestamp("2024-04-30")] * len(symbols),
            "reportPeriodEnd": [pd.Timestamp("2023-12-31")] * len(symbols),
        })

        observations = _run_stage2_registered_cells(
            prepared=_stage2_prepared_with_close_types(base),
            stock_master=stock_master,
            fundamentals=fundamentals,
            rebalance_dates=[day],
            plan=_stage2_plan(),
        )

        self.assertTrue(observations)
        for observation in observations:
            audit = observation["sample_audit"]
            self.assertEqual(audit["candidate_count"], len(quoted_symbols))
            self.assertNotIn(
                symbols[-1],
                {row["symbol"] for row in audit["endpoint_records"]},
            )

    def test_stage2_final_survivor_universe_still_begins_at_listing_date(self) -> None:
        day = pd.Timestamp("2025-06-02")
        symbols = [f"{index:06d}.SZ" for index in range(1, 7)]
        quoted_symbols = symbols[:-1]
        base = pd.DataFrame({
            "date": [day] * len(quoted_symbols),
            "symbol": quoted_symbols,
            "is_st": [False] * len(quoted_symbols),
            "is_suspended": [False] * len(quoted_symbols),
            "amount_20d": [10_000_000.0] * len(quoted_symbols),
            "momentum_60d": list(range(1, len(quoted_symbols) + 1)),
            "low_vol_20d": list(range(len(quoted_symbols), 0, -1)),
            "future_return_same": [0.01, 0.02, 0.03, 0.04, 0.05],
            "future_return_lagged": [0.01, 0.02, 0.03, 0.04, 0.05],
        })
        stock_master = pd.DataFrame({
            "symbol": symbols,
            "listDate": [pd.Timestamp("2010-01-01")] * len(quoted_symbols)
            + [pd.Timestamp("2026-01-01")],
            "delistDate": [pd.NaT] * len(symbols),
            "listStatus": ["listed"] * len(symbols),
            "stockType": ["A股"] * len(symbols),
        })
        fundamentals = pd.DataFrame({
            "symbol": symbols,
            "roe": [value / 100 for value in range(1, len(symbols) + 1)],
            "publishDate": [pd.Timestamp("2024-04-30")] * len(symbols),
            "reportPeriodEnd": [pd.Timestamp("2023-12-31")] * len(symbols),
        })

        try:
            observations = _run_stage2_registered_cells(
                prepared=_stage2_prepared_with_close_types(base),
                stock_master=stock_master,
                fundamentals=fundamentals,
                rebalance_dates=[day],
                plan=_stage2_plan(),
            )
        except ConfirmatoryStudyError as exc:
            self.fail(f"future-listed survivor entered the historical universe: {exc}")

        final_survivor_roe = next(
            row for row in observations
            if row["variant"] == "A0_final_report_end" and row["factor"] == "roe"
        )
        self.assertEqual(
            final_survivor_roe["sample_audit"]["candidate_count"],
            len(quoted_symbols),
        )

    def test_stage2_terminal_survivor_uses_fixed_outcome_cutoff_not_current_status(self) -> None:
        day = pd.Timestamp("2020-01-02")
        symbols = [f"{index:06d}.SZ" for index in range(1, 9)]
        base = pd.DataFrame({
            "date": [day] * len(symbols),
            "symbol": symbols,
            "is_st": [False] * len(symbols),
            "is_suspended": [False] * len(symbols),
            "amount_20d": [10_000_000.0] * len(symbols),
            "momentum_60d": list(range(1, 9)),
            "low_vol_20d": list(range(8, 0, -1)),
            "future_return_same": [value / 100 for value in range(1, 9)],
            "future_return_lagged": [value / 100 for value in range(1, 9)],
        })
        stock_master = pd.DataFrame({
            "symbol": symbols,
            "listDate": [pd.Timestamp("2010-01-01")] * len(symbols),
            "delistDate": [
                pd.Timestamp("2022-01-01"),
                pd.Timestamp(STAGE2_TERMINAL_SURVIVOR_CUTOFF),
                pd.Timestamp("2023-02-01"),
                *([pd.NaT] * 5),
            ],
            "listStatus": ["delisted", "delisted", "delisted", *(["listed"] * 5)],
            "stockType": ["A股"] * len(symbols),
        })
        fundamentals = pd.DataFrame({
            "symbol": symbols,
            "roe": [value / 100 for value in range(1, 9)],
            "publishDate": [pd.Timestamp("2019-04-30")] * len(symbols),
            "reportPeriodEnd": [pd.Timestamp("2018-12-31")] * len(symbols),
        })

        observations = _run_stage2_registered_cells(
            prepared=_stage2_prepared_with_close_types(base),
            stock_master=stock_master,
            fundamentals=fundamentals,
            rebalance_dates=[day],
            plan=_stage2_plan(),
        )
        by_variant = {
            row["variant"]: row
            for row in observations
            if row["factor"] == "roe"
        }
        self.assertEqual(
            by_variant["A0_final_report_end"]["sample_audit"]["candidate_count"],
            6,
        )
        self.assertEqual(
            by_variant["A1_pit_report_end"]["sample_audit"]["candidate_count"],
            8,
        )

    def test_stage2_quintile_boundaries_are_deterministic_and_keep_ties_together(self) -> None:
        distinct = pd.Series(range(1, 1001), dtype=float)
        _, bottom, top = _stage2_rank_groups(distinct)
        self.assertEqual(int(bottom.sum()), 200)
        self.assertEqual(int(top.sum()), 200)

        tied = distinct.copy()
        tied.iloc[194:206] = 200.5
        tied.iloc[794:806] = 800.5
        ranks, tied_bottom, tied_top = _stage2_rank_groups(tied)
        self.assertEqual(int(tied_bottom.sum()), 194)
        self.assertEqual(int(tied_top.sum()), 206)
        self.assertEqual(ranks.iloc[194:206].nunique(), 1)
        self.assertFalse(tied_bottom.iloc[194:206].any())
        self.assertTrue(tied_top.iloc[794:806].all())

    def test_stage2_monthly_timing_diagnostics_close_three_part_common_support_identity(self) -> None:
        day = pd.Timestamp("2025-06-02")
        symbols = [f"{index:06d}.SZ" for index in range(1, 8)]
        base = pd.DataFrame({
            "date": [day] * len(symbols),
            "symbol": symbols,
            "is_st": [False] * len(symbols),
            "is_suspended": [False] * len(symbols),
            "amount_20d": [10_000_000.0] * len(symbols),
            "momentum_60d": list(range(1, 8)),
            "low_vol_20d": list(range(7, 0, -1)),
            "future_return_same": [value / 100 for value in range(1, 8)],
            "future_return_lagged": [value / 100 for value in range(1, 8)],
        })
        stock_master = pd.DataFrame({
            "symbol": symbols,
            "listDate": [pd.Timestamp("2010-01-01")] * len(symbols),
            "delistDate": [pd.NaT] * len(symbols),
            "listStatus": ["listed"] * len(symbols),
            "stockType": ["A股"] * len(symbols),
        })
        fundamentals = []
        for index, symbol in enumerate(symbols, start=1):
            # The report-side selector sees a newer but not-yet-published record.
            fundamentals.append({
                "symbol": symbol,
                "roe": float(8 - index),
                "publishDate": pd.Timestamp("2025-06-30"),
                "reportPeriodEnd": pd.Timestamp("2024-12-31"),
            })
            if index < len(symbols):
                fundamentals.append({
                    "symbol": symbol,
                    "roe": float(index),
                    "publishDate": pd.Timestamp("2024-04-30"),
                    "reportPeriodEnd": pd.Timestamp("2023-12-31"),
                })

        observations = _run_stage2_registered_cells(
            prepared=_stage2_prepared_with_close_types(base),
            stock_master=stock_master,
            fundamentals=pd.DataFrame(fundamentals),
            rebalance_dates=[day],
            plan=_stage2_plan(),
        )
        report_roe = next(
            row for row in observations
            if row["variant"] == "A1_pit_report_end" and row["factor"] == "roe"
        )
        publication_roe = next(
            row for row in observations
            if row["variant"] == "I0000_pit_publication" and row["factor"] == "roe"
        )
        diagnostic = publication_roe["timing_decomposition"]

        self.assertEqual(diagnostic["u_r_count"], 7)
        self.assertEqual(diagnostic["u_p_count"], 6)
        self.assertEqual(diagnostic["intersection_count"], 6)
        exposure = publication_roe["publication_exposure"]
        self.assertEqual(exposure["changed_report_period_count"], 6)
        self.assertEqual(exposure["premature_report_record_count"], 7)
        components = (
            diagnostic["report_support_restriction"]
            + diagnostic["common_support_record_replacement"]
            + diagnostic["publication_support_extension"]
        )
        self.assertAlmostEqual(diagnostic["total_timing_difference"], components)
        self.assertAlmostEqual(
            diagnostic["total_timing_difference"],
            publication_roe["ic"] - report_roe["ic"],
        )
        self.assertAlmostEqual(diagnostic["efficiency_residual"], 0.0, places=12)

    def test_publication_exposure_diagnostics_are_outcome_free_and_complete(self) -> None:
        day = pd.Timestamp("2025-06-02")
        symbols = [f"{index:06d}.SZ" for index in range(1, 4)]
        base = pd.DataFrame({
            "date": [day] * len(symbols),
            "symbol": symbols,
            "is_st": [False] * len(symbols),
            "is_suspended": [False] * len(symbols),
            "amount_20d": [10_000_000.0] * len(symbols),
            "momentum_60d": [1.0, 2.0, 3.0],
            "low_vol_20d": [3.0, 2.0, 1.0],
            # Every outcome is deliberately unresolved.  The diagnostic must still exist.
            "future_return_same": [float("nan")] * len(symbols),
            "future_return_lagged": [float("nan")] * len(symbols),
        })
        stock_master = pd.DataFrame({
            "symbol": symbols,
            "listDate": [pd.Timestamp("2010-01-01")] * len(symbols),
            "delistDate": [pd.NaT] * len(symbols),
            "listStatus": ["listed"] * len(symbols),
            "stockType": ["A股"] * len(symbols),
        })
        fundamentals: list[dict[str, object]] = []
        for index, symbol in enumerate(symbols, start=1):
            fundamentals.append({
                "symbol": symbol,
                "roe": float(4 - index),
                "publishDate": pd.Timestamp("2025-06-30"),
                "reportPeriodEnd": pd.Timestamp("2024-12-31"),
            })
            if index < 3:
                fundamentals.append({
                    "symbol": symbol,
                    "roe": float(index),
                    "publishDate": pd.Timestamp("2024-04-30"),
                    "reportPeriodEnd": pd.Timestamp("2023-12-31"),
                })

        observations = _run_stage2_registered_cells(
            prepared=_stage2_prepared_with_close_types(base),
            stock_master=stock_master,
            fundamentals=pd.DataFrame(fundamentals),
            rebalance_dates=[day],
            plan=_stage2_plan(),
        )
        publication_roe = next(
            row for row in observations
            if row["variant"] == "I0000_pit_publication" and row["factor"] == "roe"
        )
        self.assertNotIn("timing_decomposition", publication_roe)
        self.assertEqual(publication_roe["sample_audit"]["candidate_count"], 3)
        self.assertEqual(publication_roe["sample_audit"]["signal_missing_count"], 1)
        diagnostic = publication_roe["publication_exposure"]
        self.assertEqual(diagnostic["report_signal_count"], 3)
        self.assertEqual(diagnostic["publication_signal_count"], 2)
        self.assertEqual(diagnostic["common_signal_count"], 2)
        self.assertEqual(diagnostic["report_only_count"], 1)
        self.assertEqual(diagnostic["publication_only_count"], 0)
        self.assertEqual(diagnostic["premature_report_record_count"], 3)
        self.assertEqual(diagnostic["premature_report_record_share"], 1.0)
        self.assertEqual(diagnostic["changed_report_period_count"], 2)
        self.assertEqual(diagnostic["changed_report_period_share"], 1.0)
        self.assertEqual(
            diagnostic["reporting_delay_calendar_days"],
            {
                "count": 3,
                "mean": 181.0,
                "median": 181.0,
                "p25": 181.0,
                "p75": 181.0,
                "maximum": 181.0,
            },
        )

    def test_nonfinite_quote_is_input_integrity_failure_not_endpoint_reason(self) -> None:
        sessions = list(pd.bdate_range("2025-01-02", periods=22))
        quotes = pd.DataFrame({
            "date": sessions,
            "symbol": ["000001.SZ"] * len(sessions),
            "close": [10.0] * 21 + [float("inf")],
            "amount": [10_000_000.0] * len(sessions),
            "is_st": [False] * len(sessions),
            "is_suspended": [False] * len(sessions),
        })
        with self.assertRaisesRegex(ConfirmatoryStudyError, "non-finite quote"):
            _prepare_quotes(quotes, 20, exchange_sessions=sessions)

    def test_quote_loader_rejects_missing_or_unparseable_numeric_values(self) -> None:
        for invalid_close in ("", "not-a-number"):
            with self.subTest(invalid_close=invalid_close), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "quotes.csv"
                path.write_text(
                    "date,symbol,close,amount,is_st,is_suspended\n"
                    "2025-01-02,000001.SZ,10.0,10000000,false,false\n"
                    f"2025-01-03,000001.SZ,{invalid_close},10000000,false,false\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(
                    ConfirmatoryStudyError,
                    "missing or non-numeric quote values",
                ):
                    _load_quotes(path)

    def test_stage2_quote_loader_enforces_exact_close_observation_mapping(self) -> None:
        valid = (
            "date,symbol,close_raw,adjustment_factor,close,price_adjustment_method,price_adjustment_convention,close_observation_type,amount,amount_unit,is_st,is_suspended\n"
            f"2025-01-02,000001.SZ,5.0,2,10.0,{STAGE2_PRICE_ADJUSTMENT_METHOD},{STAGE2_PRICE_ADJUSTMENT_CONVENTION},traded_close,10000000,CNY,false,false\n"
            f"2025-01-02,000002.SZ,9.5,1,9.5,{STAGE2_PRICE_ADJUSTMENT_METHOD},{STAGE2_PRICE_ADJUSTMENT_CONVENTION},suspension_valuation,0,CNY,false,true\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quotes.csv"
            path.write_text(valid, encoding="utf-8")
            loaded = _load_stage2_quotes(path)
            self.assertEqual(
                set(loaded["close_observation_type"]),
                {"traded_close", "suspension_valuation"},
            )

            path.write_text(
                valid.replace(
                    "close_observation_type,", "", 1
                ).replace(
                    ",traded_close,", ",", 1
                ).replace(
                    ",suspension_valuation,", ",", 1
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ConfirmatoryStudyError, "locked close-observation contract"
            ):
                _load_stage2_quotes(path)

            for old, new, message in (
                (
                    STAGE2_PRICE_ADJUSTMENT_METHOD,
                    "provider_adjusted_close",
                    "price_adjustment_method",
                ),
                (
                    STAGE2_PRICE_ADJUSTMENT_CONVENTION,
                    "qfq",
                    "price_adjustment_convention",
                ),
                (",5.0,2,10.0,", ",5.0,2,9.0,", "does not equal close_raw"),
            ):
                path.write_text(valid.replace(old, new, 1), encoding="utf-8")
                with self.assertRaisesRegex(ConfirmatoryStudyError, message):
                    _load_stage2_quotes(path)

            path.write_text(
                valid.replace(
                    ",suspension_valuation,0,CNY,false,true",
                    ",traded_close,0,CNY,false,true",
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ConfirmatoryStudyError, "does not match is_suspended"
            ):
                _load_stage2_quotes(path)

            path.write_text(
                valid.replace(",10000000,CNY,", ",10000000,thousand_CNY,", 1),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ConfirmatoryStudyError, "amount_unit must be exact CNY"
            ):
                _load_stage2_quotes(path)

    def test_stage2_registered_cell_runner_cannot_bypass_close_observation_contract(self) -> None:
        day = pd.Timestamp("2020-01-02")
        missing_contract = pd.DataFrame({
            "date": [day],
            "symbol": ["000001.SZ"],
            "is_suspended": [False],
        })
        with self.assertRaisesRegex(
            ConfirmatoryStudyError, "missing the close-observation contract"
        ):
            _run_stage2_registered_cells(
                prepared=missing_contract,
                stock_master=pd.DataFrame(),
                fundamentals=pd.DataFrame(),
                rebalance_dates=[day],
                plan=_stage2_plan(),
            )

        mismatched_contract = missing_contract.assign(
            close_observation_type="suspension_valuation"
        )
        with self.assertRaisesRegex(
            ConfirmatoryStudyError, "does not match is_suspended"
        ):
            _run_stage2_registered_cells(
                prepared=mismatched_contract,
                stock_master=pd.DataFrame(),
                fundamentals=pd.DataFrame(),
                rebalance_dates=[day],
                plan=_stage2_plan(),
            )

        missing_price_contract = missing_contract.assign(
            close_observation_type="traded_close"
        )
        with self.assertRaisesRegex(
            ConfirmatoryStudyError, "missing the price-adjustment contract"
        ):
            _run_stage2_registered_cells(
                prepared=missing_price_contract,
                stock_master=pd.DataFrame(),
                fundamentals=pd.DataFrame(),
                rebalance_dates=[day],
                plan=_stage2_plan(),
            )

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

        observations = _run_stage2_registered_cells(
            prepared=_stage2_prepared_with_close_types(base),
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
        self.assertEqual(roe["A0_final_report_end"]["cross_section_size"], 8)
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

    def test_stage2_unresolved_exact_forward_endpoints_make_cells_non_estimable_and_auditable(self) -> None:
        sessions = list(pd.bdate_range("2025-01-02", periods=22))
        day = sessions[0]
        symbols = [f"{index:06d}.SZ" for index in range(1, 8)]
        missing_same_exit = symbols[0]
        missing_lag_entry = symbols[1]
        rows = []
        for session_index, session in enumerate(sessions):
            for symbol_index, symbol in enumerate(symbols, start=1):
                if symbol == missing_same_exit and session_index == 20:
                    continue
                if symbol == missing_lag_entry and session_index == 1:
                    continue
                rows.append({
                    "date": session,
                    "symbol": symbol,
                    "close": 10.0 + symbol_index + session_index / 10,
                    "amount": 10_000_000.0,
                    "is_st": False,
                    "is_suspended": False,
                })
        prepared = _prepare_quotes(
            pd.DataFrame(rows),
            horizon=20,
            exchange_sessions=sessions,
        )
        signal_rows = prepared["date"].eq(day)
        prepared.loc[signal_rows, "momentum_60d"] = range(1, 8)
        prepared.loc[signal_rows, "low_vol_20d"] = range(7, 0, -1)
        prepared.loc[signal_rows, "amount_20d"] = 10_000_000.0
        stock_master = pd.DataFrame({
            "symbol": symbols,
            "listDate": [pd.Timestamp("2010-01-01")] * len(symbols),
            "delistDate": [pd.NaT] * len(symbols),
            "listStatus": ["listed"] * len(symbols),
            "stockType": ["A股"] * len(symbols),
        })
        fundamentals = pd.DataFrame({
            "symbol": symbols,
            "roe": [value / 100 for value in range(1, 8)],
            "publishDate": [pd.Timestamp("2024-04-30")] * len(symbols),
            "reportPeriodEnd": [pd.Timestamp("2023-12-31")] * len(symbols),
        })
        plan = _stage2_plan()

        observations = _run_stage2_registered_cells(
            prepared=_stage2_prepared_with_close_types(prepared),
            stock_master=stock_master,
            fundamentals=fundamentals,
            rebalance_dates=[day],
            plan=plan,
        )
        same_clock = next(
            row for row in observations
            if row["variant"] == "I0000_pit_publication" and row["factor"] == "roe"
        )
        lag_clock = next(
            row for row in observations
            if row["variant"] == "I0001_lag" and row["factor"] == "roe"
        )

        self.assertIsNone(same_clock["ic"])
        self.assertIsNone(same_clock["top_minus_universe"])
        self.assertEqual(same_clock["sample_audit"]["signal_eligible_count"], 7)
        self.assertEqual(same_clock["sample_audit"]["estimable_count"], 6)
        self.assertEqual(same_clock["sample_audit"]["unresolved_endpoint_count"], 1)
        self.assertEqual(
            same_clock["sample_audit"]["unresolved_endpoints"],
            [{
                "symbol": missing_same_exit,
                "reason_code": "MISSING_EXACT_FORWARD_EXIT",
            }],
        )
        self.assertIsNone(lag_clock["ic"])
        self.assertIsNone(lag_clock["top_minus_universe"])
        self.assertEqual(lag_clock["sample_audit"]["unresolved_endpoint_count"], 1)
        self.assertEqual(
            lag_clock["sample_audit"]["unresolved_endpoints"],
            [{
                "symbol": missing_lag_entry,
                "reason_code": "MISSING_EXACT_LAG_ENTRY",
            }],
        )
        self.assertIn("endpoint_records", same_clock["sample_audit"])
        self.assertEqual(
            {row["symbol"] for row in same_clock["sample_audit"]["endpoint_records"]},
            set(symbols),
        )
        self.assertEqual(
            [
                row["resolution_code"]
                for row in same_clock["sample_audit"]["endpoint_records"]
            ].count(STAGE2_RESOLVED_ENDPOINT_CODE),
            6,
        )
        self.assertEqual(
            [
                row["resolution_code"]
                for row in same_clock["sample_audit"]["endpoint_records"]
            ].count("MISSING_EXACT_FORWARD_EXIT"),
            1,
        )
        self.assertEqual(
            [
                row["resolution_code"]
                for row in lag_clock["sample_audit"]["endpoint_records"]
            ].count("MISSING_EXACT_LAG_ENTRY"),
            1,
        )
        status = _stage2_evidence_status(
            declaration={"source_classification": "real_market_data"},
            observations=observations,
            plan=plan,
        )
        self.assertIn("UNRESOLVED_FORWARD_ENDPOINTS", status["reason_codes"])

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

        rows = _run_stage2_registered_cells(
            prepared=_stage2_prepared_with_close_types(base),
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

    def test_stage2_execution_writes_complete_private_endpoint_ledger_and_sanitizes_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _bind_stage2_gate_artifacts(
                _write_fixture(root, source_classification="synthetic_fixture"),
                _stage2_plan(),
            )
            output = root / "out"

            with patch(
                "a_share_quant_agent.confirmatory_study._validate_stage2_data_bindings"
            ):
                receipt = run_stage2_confirmatory_study(**paths, output_dir=output)

            ledger_path = output / "endpoint_reason_ledger.private.json"
            self.assertTrue(ledger_path.is_file())
            ledger_bytes = ledger_path.read_bytes()
            ledger = json.loads(ledger_bytes)
            self.assertEqual(
                ledger_bytes,
                (
                    json.dumps(
                        ledger,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode("utf-8"),
            )
            self.assertEqual(ledger["schema_version"], "stage2_endpoint_reason_ledger_v1")

            metadata = receipt["endpoint_reason_ledger"]
            self.assertEqual(
                set(metadata),
                {
                    "filename",
                    "sha256",
                    "record_count",
                    "aggregate_resolution_code_counts",
                    "exact_denominator_coverage",
                },
            )
            self.assertEqual(
                metadata["filename"], "endpoint_reason_ledger.private.json"
            )
            self.assertEqual(metadata["sha256"], hashlib.sha256(ledger_bytes).hexdigest())
            self.assertEqual(metadata["record_count"], len(ledger["records"]))

            expected_record_count = sum(
                row["sample_audit"]["signal_eligible_count"]
                for row in receipt["monthly_observations"]
            )
            self.assertEqual(metadata["record_count"], expected_record_count)
            self.assertEqual(
                metadata["exact_denominator_coverage"],
                {
                    "assertion": (
                        "one_record_per_signal_eligible_security_date_variant_factor"
                    ),
                    "expected_record_count": expected_record_count,
                    "satisfied": True,
                },
            )

            counts: dict[str, int] = {}
            ledger_cell_counts: dict[tuple[str, str, str], int] = {}
            record_keys: set[tuple[str, str, str, str]] = set()
            for row in ledger["records"]:
                self.assertEqual(
                    set(row), {"date", "variant", "factor", "symbol", "resolution_code"}
                )
                counts[row["resolution_code"]] = counts.get(row["resolution_code"], 0) + 1
                cell = (row["date"], row["variant"], row["factor"])
                ledger_cell_counts[cell] = ledger_cell_counts.get(cell, 0) + 1
                record_keys.add((*cell, row["symbol"]))
            self.assertEqual(len(record_keys), len(ledger["records"]))
            self.assertEqual(metadata["aggregate_resolution_code_counts"], counts)
            self.assertEqual(
                ledger_cell_counts,
                {
                    (row["date"], row["variant"], row["factor"]): row[
                        "sample_audit"
                    ]["signal_eligible_count"]
                    for row in receipt["monthly_observations"]
                },
            )
            for row in receipt["monthly_observations"]:
                self.assertNotIn("unresolved_endpoints", row["sample_audit"])
                self.assertNotIn("endpoint_records", row["sample_audit"])
            self.assertNotIn(
                '"symbol"',
                json.dumps(receipt["monthly_observations"], sort_keys=True),
            )

    def test_stage2_endpoint_ledger_streams_large_input_with_bounded_python_heap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            observations: list[dict[str, object]] = []
            writer = confirmatory_module._Stage2EndpointLedgerWriter(directory=root)
            tracemalloc.start()
            try:
                for cell_index in range(256):
                    observation: dict[str, object] = {
                        "date": "2020-01-02",
                        "variant": f"V{cell_index:04d}",
                        "factor": "roe",
                        "cross_section_size": 1024,
                        "sample_audit": {
                            "candidate_count": 1024,
                            "signal_eligible_count": 1024,
                            "signal_missing_count": 0,
                            "estimable_count": 1024,
                            "unresolved_endpoint_count": 0,
                            "unresolved_endpoints": [],
                            "endpoint_records": [
                                {
                                    "symbol": f"{symbol_index:06d}.SZ",
                                    "resolution_code": (
                                        STAGE2_RESOLVED_ENDPOINT_CODE
                                    ),
                                }
                                for symbol_index in range(1024)
                            ],
                        },
                    }
                    writer.add_observation(observation)
                    audit = observation["sample_audit"]
                    self.assertNotIn("endpoint_records", audit)
                    self.assertNotIn("unresolved_endpoints", audit)
                    observations.append(observation)

                metadata = writer.finalize()
                ledger_path = root / "endpoint_reason_ledger.private.json"
                writer.copy_to(ledger_path)
                confirmatory_module._validate_stage2_endpoint_reason_ledger(
                    endpoint_ledger_path=ledger_path,
                    metadata=metadata,
                    observations=observations,
                )
                _, peak_bytes = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
                writer.close()

            self.assertEqual(metadata["record_count"], 256 * 1024)
            self.assertLess(peak_bytes, 24 * 1024 * 1024)

    def test_public_endpoint_metadata_rejects_unregistered_reason_code_without_private_ledger(self) -> None:
        observations = [{
            "date": "2020-01-02",
            "variant": "I0000_pit_publication",
            "factor": "roe",
            "cross_section_size": 0,
            "sample_audit": {
                "candidate_count": 1,
                "signal_eligible_count": 1,
                "signal_missing_count": 0,
                "estimable_count": 0,
                "unresolved_endpoint_count": 1,
            },
        }]
        metadata = {
            "filename": "endpoint_reason_ledger.private.json",
            "sha256": "0" * 64,
            "record_count": 1,
            "aggregate_resolution_code_counts": {
                "UNREGISTERED_ENDPOINT_REASON": 1,
            },
            "exact_denominator_coverage": {
                "assertion": (
                    "one_record_per_signal_eligible_security_date_variant_factor"
                ),
                "expected_record_count": 1,
                "satisfied": True,
            },
        }

        with self.assertRaisesRegex(
            ConfirmatoryStudyError, "unsupported endpoint resolution code"
        ):
            confirmatory_module._validate_stage2_endpoint_reason_ledger(
                endpoint_ledger_path=None,
                metadata=metadata,
                observations=observations,
            )

    def test_stage2_verifies_staged_artifacts_before_atomic_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _bind_stage2_gate_artifacts(
                _write_fixture(root, source_classification="synthetic_fixture"),
                _stage2_plan(),
            )
            output = root / "out"

            with patch(
                "a_share_quant_agent.confirmatory_study._validate_stage2_data_bindings"
            ), patch(
                "a_share_quant_agent.confirmatory_study.verify_stage2_study_receipt",
                side_effect=ConfirmatoryStudyError("forced staged verification failure"),
            ):
                with self.assertRaisesRegex(
                    ConfirmatoryStudyError, "forced staged verification failure"
                ):
                    run_stage2_confirmatory_study(**paths, output_dir=output)

            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".confirmatory-stage2-*")), [])

    def test_stage2_verifier_rejects_invalid_private_endpoint_ledger_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _bind_stage2_gate_artifacts(
                _write_fixture(root, source_classification="synthetic_fixture"),
                _stage2_plan(),
            )
            output = root / "out"
            with patch(
                "a_share_quant_agent.confirmatory_study._validate_stage2_data_bindings"
            ):
                run_stage2_confirmatory_study(**paths, output_dir=output)

            receipt_path = output / "receipt.json"
            ledger_path = output / "endpoint_reason_ledger.private.json"
            original_receipt_bytes = receipt_path.read_bytes()
            original_ledger_bytes = ledger_path.read_bytes()
            original_receipt = json.loads(original_receipt_bytes)
            original_ledger = json.loads(original_ledger_bytes)

            verify_stage2_study_receipt(
                receipt_path, endpoint_ledger_path=ledger_path
            )

            def write_receipt(receipt: dict[str, object]) -> None:
                _rewrite_receipt_integrity(receipt)
                receipt_path.write_text(
                    json.dumps(
                        receipt,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n",
                    encoding="utf-8",
                )

            with self.subTest("canonical bytes"):
                pretty_ledger = (
                    json.dumps(original_ledger, ensure_ascii=False, indent=2) + "\n"
                ).encode("utf-8")
                ledger_path.write_bytes(pretty_ledger)
                changed_receipt = json.loads(original_receipt_bytes)
                changed_receipt["endpoint_reason_ledger"]["sha256"] = hashlib.sha256(
                    pretty_ledger
                ).hexdigest()
                write_receipt(changed_receipt)
                with self.assertRaisesRegex(
                    ConfirmatoryStudyError, "endpoint ledger is not canonical JSON"
                ):
                    verify_stage2_study_receipt(
                        receipt_path, endpoint_ledger_path=ledger_path
                    )

            receipt_path.write_bytes(original_receipt_bytes)
            ledger_path.write_bytes(original_ledger_bytes)
            with self.subTest("aggregate resolution counts"):
                changed_ledger = json.loads(original_ledger_bytes)
                changed_ledger["records"][0][
                    "resolution_code"
                ] = "MISSING_EXACT_FORWARD_EXIT"
                changed_ledger_bytes = (
                    json.dumps(
                        changed_ledger,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode("utf-8")
                ledger_path.write_bytes(changed_ledger_bytes)
                changed_receipt = json.loads(original_receipt_bytes)
                metadata = changed_receipt["endpoint_reason_ledger"]
                metadata["sha256"] = hashlib.sha256(changed_ledger_bytes).hexdigest()
                counts = metadata["aggregate_resolution_code_counts"]
                counts[STAGE2_RESOLVED_ENDPOINT_CODE] -= 1
                counts["MISSING_EXACT_FORWARD_EXIT"] = 1
                write_receipt(changed_receipt)
                with self.assertRaisesRegex(
                    ConfirmatoryStudyError,
                    "aggregate resolution counts differ from monthly audits",
                ):
                    verify_stage2_study_receipt(
                        receipt_path, endpoint_ledger_path=ledger_path
                    )

            receipt_path.write_bytes(original_receipt_bytes)
            ledger_path.write_bytes(original_ledger_bytes)
            with self.subTest("exact denominator coverage"):
                changed_ledger = json.loads(original_ledger_bytes)
                changed_ledger["records"].pop()
                changed_ledger_bytes = (
                    json.dumps(
                        changed_ledger,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode("utf-8")
                ledger_path.write_bytes(changed_ledger_bytes)
                changed_receipt = json.loads(original_receipt_bytes)
                metadata = changed_receipt["endpoint_reason_ledger"]
                metadata["sha256"] = hashlib.sha256(changed_ledger_bytes).hexdigest()
                metadata["record_count"] -= 1
                metadata["aggregate_resolution_code_counts"][
                    STAGE2_RESOLVED_ENDPOINT_CODE
                ] -= 1
                metadata["exact_denominator_coverage"][
                    "expected_record_count"
                ] -= 1
                write_receipt(changed_receipt)
                with self.assertRaisesRegex(
                    ConfirmatoryStudyError, "exact denominator coverage"
                ):
                    verify_stage2_study_receipt(
                        receipt_path, endpoint_ledger_path=ledger_path
                    )

            receipt_path.write_bytes(original_receipt_bytes)
            ledger_path.write_bytes(original_ledger_bytes)
            with self.subTest("explicit audit requires supplied ledger"):
                ledger_path.unlink()
                with self.assertRaisesRegex(
                    ConfirmatoryStudyError, "private endpoint ledger is missing"
                ):
                    verify_stage2_study_receipt(
                        receipt_path, endpoint_ledger_path=ledger_path
                    )

    def test_stage2_verifier_rejects_cross_section_size_audit_mismatch_in_both_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _bind_stage2_gate_artifacts(
                _write_fixture(root, source_classification="synthetic_fixture"),
                _stage2_plan(),
            )
            output = root / "out"
            with patch(
                "a_share_quant_agent.confirmatory_study._validate_stage2_data_bindings"
            ), patch(
                "a_share_quant_agent.confirmatory_study._verify_coverage_probe_spec_commit_binding"
            ):
                run_stage2_confirmatory_study(**paths, output_dir=output)

                receipt_path = output / "receipt.json"
                receipt = json.loads(receipt_path.read_bytes())
                receipt["monthly_observations"][0]["cross_section_size"] += 1
                _rewrite_receipt_integrity(receipt)
                receipt_path.write_text(
                    json.dumps(
                        receipt,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n",
                    encoding="utf-8",
                )

                for label, endpoint_ledger_path in (
                    ("public receipt only", None),
                    (
                        "controlled private-ledger audit",
                        output / "endpoint_reason_ledger.private.json",
                    ),
                ):
                    with self.subTest(label=label), self.assertRaisesRegex(
                        ConfirmatoryStudyError,
                        "cross-section size differs from sample audit estimable count",
                    ):
                        verify_stage2_study_receipt(
                            receipt_path,
                            endpoint_ledger_path=endpoint_ledger_path,
                        )

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
            for file_label, file_evidence in receipt["data"]["files"].items():
                self.assertEqual(
                    set(file_evidence),
                    {"sha256"},
                    file_label,
                )
            probe_file = receipt["data"]["files"]["coverage_probe_receipt"]
            probe_package = receipt["data"]["coverage_probe_receipt"]
            self.assertEqual(
                probe_file["sha256"],
                receipt["plan"]["content"]["coverage_probe_receipt_sha256"],
            )
            self.assertEqual(
                probe_package["source_file_sha256"], probe_file["sha256"]
            )
            self.assertEqual(probe_package["content"]["status"], "PASSED")
            self.assertEqual(
                receipt["registration_evidence"]["design_manifest"]["artifacts"]
                ["coverage_probe_receipt_sha256"],
                probe_file["sha256"],
            )
            self.assertEqual(
                receipt["registration_evidence"]["registration_receipt"]
                ["coverage_probe_receipt_sha256"],
                probe_file["sha256"],
            )
            self.assertEqual(
                receipt["registration_evidence"]["execution_authorization"]
                ["bound_artifacts"]["coverage_probe_receipt_sha256"],
                probe_file["sha256"],
            )
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
                28,
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
            self.assertFalse(receipt["status"]["vintage_value_claim"])
            self.assertFalse(
                receipt["status"]["historical_investor_observed_value_claim"]
            )
            self.assertFalse(receipt["status"]["announcement_reaction_claim"])
            self.assertFalse(receipt["status"]["return_timing_claim"])
            self.assertFalse(receipt["status"]["portfolio_or_trading_claim"])
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
            self.assertIs(receipt["data"]["redistributable"], False)
            verify_stage2_study_receipt(root / "out" / "receipt.json")
            for integer_alias in (0, 1):
                with self.subTest(
                    receipt_redistributable_integer_alias=integer_alias
                ):
                    changed = json.loads(
                        (root / "out" / "receipt.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    changed["data"]["redistributable"] = integer_alias
                    _rewrite_receipt_integrity(changed)
                    changed_path = (
                        root / f"redistributable-integer-{integer_alias}.json"
                    )
                    changed_path.write_text(
                        json.dumps(
                            changed,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(
                        ConfirmatoryStudyError,
                        "data summary differs from the canonical declaration",
                    ):
                        verify_stage2_study_receipt(changed_path)
            public_status = build_public_evidence_status(
                [root / "out" / "receipt.json"]
            )
            self.assertEqual(public_status["status"], "INSUFFICIENT_EVIDENCE")
            self.assertEqual(public_status["verified_receipt_count"], 1)

            standalone_public_receipt = root / "published-stage2-receipt.json"
            standalone_public_receipt.write_bytes(
                (root / "out" / "receipt.json").read_bytes()
            )
            verified_public = verify_stage2_study_receipt(
                standalone_public_receipt
            )
            self.assertEqual(verified_public["study_id"], receipt["study_id"])
            standalone_status = build_public_evidence_status(
                [standalone_public_receipt]
            )
            self.assertEqual(
                standalone_status,
                {
                    "schema_version": "public_evidence_status_v1",
                    "status": "INSUFFICIENT_EVIDENCE",
                    "source_of_truth": "verified_confirmatory_receipts",
                    "verified_receipt_count": 1,
                    "study_ids": [receipt["study_id"]],
                    "performance_claim": False,
                    "generalization_claim": False,
                    "usable_for_trading_decisions": False,
                },
            )
            self.assertFalse(receipt["estimands"]["global_claim_gate"]["passed"])
            changed = json.loads(
                (root / "out" / "receipt.json").read_text(encoding="utf-8")
            )
            changed["estimands"]["primary_family"][0]["claim_eligible"] = True
            _rewrite_receipt_integrity(changed)
            tampered_global_gate = root / "tampered-global-claim-gate.json"
            tampered_global_gate.write_text(
                json.dumps(changed, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ConfirmatoryStudyError, "estimands failed verification"
            ):
                verify_stage2_study_receipt(tampered_global_gate)

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

    def test_stage2_verifier_rejects_rehashed_file_evidence_metadata(self) -> None:
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

            original = json.loads(
                (root / "out" / "receipt.json").read_text(encoding="utf-8")
            )
            mutations = (
                ("raw size", "quotes", "size_bytes", 123),
                ("private declaration size", "data_declaration", "size_bytes", 456),
                ("private report name", "coverage_report", "name", "coverage.json"),
                (
                    "private attestation path",
                    "prior_exposure_attestation",
                    "path",
                    "private/prior-exposure.json",
                ),
            )
            for label, artifact, key, value in mutations:
                with self.subTest(label=label):
                    changed = json.loads(json.dumps(original))
                    changed["data"]["files"][artifact][key] = value
                    _rewrite_receipt_integrity(changed)
                    changed_path = root / f"file-evidence-{key}.json"
                    changed_path.write_text(
                        json.dumps(
                            changed,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n",
                        encoding="utf-8",
                    )

                    with self.assertRaisesRegex(
                        ConfirmatoryStudyError,
                        "file evidence must contain exactly one registered SHA-256",
                    ):
                        verify_stage2_study_receipt(changed_path)

    def test_stage2_verifier_rejects_rehashed_raw_and_outcome_payload_fields(self) -> None:
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

            original = json.loads(
                (root / "out" / "receipt.json").read_text(encoding="utf-8")
            )
            cases = (
                (
                    "raw payload at receipt root",
                    lambda receipt: receipt.__setitem__(
                        "raw_input_rows",
                        [{"symbol": "000001.SZ", "close": 10.0}],
                    ),
                    "receipt has fields outside the fixed public schema",
                ),
                (
                    "outcome payload in monthly observation",
                    lambda receipt: receipt["monthly_observations"][0].__setitem__(
                        "outcome_payload",
                        [0.01, -0.02],
                    ),
                    "monthly observation is invalid",
                ),
            )
            for label, mutate, pattern in cases:
                with self.subTest(label=label):
                    changed = json.loads(json.dumps(original))
                    mutate(changed)
                    _rewrite_receipt_integrity(changed)
                    changed_path = root / f"extra-{label.replace(' ', '-')}.json"
                    changed_path.write_text(
                        json.dumps(
                            changed,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(ConfirmatoryStudyError, pattern):
                        verify_stage2_study_receipt(changed_path)

    def test_stage2_public_registration_artifacts_reject_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _bind_stage2_gate_artifacts(
                _write_fixture(root, source_classification="synthetic_fixture"),
                _stage2_plan(),
            )
            artifacts = {
                "design_manifest": json.loads(
                    paths["design_manifest_path"].read_text(encoding="utf-8")
                ),
                "registration_receipt": json.loads(
                    paths["registration_receipt_path"].read_text(encoding="utf-8")
                ),
                "execution_authorization": json.loads(
                    paths["execution_authorization_path"].read_text(encoding="utf-8")
                ),
            }
            confirmatory_module._validate_stage2_registered_scope_contracts(
                manifest=artifacts["design_manifest"],
                registration_receipt=artifacts["registration_receipt"],
                authorization=artifacts["execution_authorization"],
            )

            cases = (
                ("design_manifest", None),
                ("registration_receipt", None),
                ("execution_authorization", None),
                ("design_manifest", "registered_design_assertions"),
                ("registration_receipt", "registered_scope_summary"),
                ("registration_receipt", "proof"),
                ("execution_authorization", "release_scope"),
                ("execution_authorization", "signature"),
            )
            for artifact_name, nested_name in cases:
                with self.subTest(
                    artifact=artifact_name,
                    nested=nested_name,
                ):
                    changed = json.loads(json.dumps(artifacts))
                    target = changed[artifact_name]
                    if nested_name is not None:
                        target = target[nested_name]
                    target["unregistered_payload"] = [1, 2, 3]
                    with self.assertRaisesRegex(
                        ConfirmatoryStudyError,
                        "fields outside|fixed design",
                    ):
                        confirmatory_module._validate_stage2_registered_scope_contracts(
                            manifest=changed["design_manifest"],
                            registration_receipt=changed["registration_receipt"],
                            authorization=changed["execution_authorization"],
                        )

    def test_stage2_public_receipt_templates_match_exact_consent_contract(self) -> None:
        study = (
            Path(__file__).resolve().parents[1]
            / "studies"
            / "pit_factor_bias_decomposition_v2"
        )
        templates = {
            "execution_plan": (
                "execution_plan.template.json",
                "full_artifact",
                None,
            ),
            "data_declaration": (
                "data_declaration.template.json",
                "fixed_public_projection",
                STAGE2_PUBLIC_DECLARATION_FIELDS,
            ),
            "design_manifest": (
                "design_manifest.template.json",
                "full_artifact",
                None,
            ),
            "registration_receipt": (
                "registration_receipt.template.json",
                "full_artifact",
                None,
            ),
            "execution_authorization": (
                "execution_authorization.template.json",
                "full_artifact",
                None,
            ),
        }
        for artifact_type, (filename, scope, public_fields) in templates.items():
            with self.subTest(artifact_type=artifact_type):
                template = json.loads((study / filename).read_text(encoding="utf-8"))
                consent = _expected_stage2_public_embedding_consent(
                    artifact_type,
                    scope=scope,
                    public_fields=public_fields,
                )
                consent["approved"] = False
                consent["privacy_assertions"] = {
                    key: False for key in consent["privacy_assertions"]
                }
                self.assertEqual(template["public_receipt_embedding"], consent)

        declaration_template = json.loads(
            (study / "data_declaration.template.json").read_text(encoding="utf-8")
        )
        self.assertEqual(set(declaration_template), STAGE2_PRIVATE_DECLARATION_FIELDS)
        self.assertEqual(
            declaration_template["fundamental_contract"],
            STAGE2_FUNDAMENTAL_CONTRACT,
        )
        self.assertEqual(
            {
                key: declaration_template["security_identifier_contract"][key]
                for key in STAGE2_SECURITY_IDENTIFIER_CONTRACT
            },
            STAGE2_SECURITY_IDENTIFIER_CONTRACT,
        )
        manifest_template = json.loads(
            (study / "design_manifest.template.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            set(manifest_template["public_receipt_projection_sha256"]),
            {"data_declaration", "official_calendar_session_dates"},
        )
        self.assertEqual(
            manifest_template["registered_design_assertions"],
            STAGE2_REGISTERED_DESIGN_ASSERTIONS,
        )
        authorization_template = json.loads(
            (study / "execution_authorization.template.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            authorization_template["release_scope"]["endpoint_boundary"],
            STAGE2_AUTHORIZATION_ENDPOINT_BOUNDARY,
        )
        self.assertEqual(
            authorization_template["release_scope"][
                "quote_price_adjustment_contract"
            ],
            STAGE2_PRICE_ADJUSTMENT_CONTRACT,
        )
        self.assertEqual(
            authorization_template["release_scope"]["universe_contract"],
            STAGE2_UNIVERSE_CONTRACT,
        )
        self.assertEqual(
            authorization_template["release_scope"]["rank_group_contract"],
            STAGE2_RANK_GROUP_CONTRACT,
        )
        self.assertEqual(
            authorization_template["release_scope"][
                "security_identifier_contract"
            ],
            STAGE2_SECURITY_IDENTIFIER_CONTRACT,
        )
        registration_template = json.loads(
            (study / "registration_receipt.template.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            registration_template["registered_scope_summary"],
            STAGE2_REGISTERED_SCOPE_SUMMARY,
        )
        confirmatory_module._validate_stage2_registration_artifact_schemas(
            manifest=manifest_template,
            registration_receipt=registration_template,
            authorization=authorization_template,
        )
        inventory = json.loads(
            (study / "prior_specification_inventory.json").read_text(
                encoding="utf-8"
            )
        )
        related_paths = {
            path
            for entry in inventory["entries"]
            for path in entry.get("related_paths", [])
        }
        self.assertIn(
            "studies/pit_factor_bias_decomposition_v2/"
            "data_declaration.template.json",
            related_paths,
        )
        canonical_entries = (
            json.dumps(
                inventory["entries"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        self.assertEqual(
            inventory["entries_sha256"],
            hashlib.sha256(canonical_entries).hexdigest(),
        )

    def test_stage2_requires_public_embedding_consent_for_each_artifact(self) -> None:
        cases = (
            ("execution_plan", "full_artifact", None),
            (
                "data_declaration",
                "fixed_public_projection",
                STAGE2_PUBLIC_DECLARATION_FIELDS,
            ),
            ("design_manifest", "full_artifact", None),
            ("registration_receipt", "full_artifact", None),
            ("execution_authorization", "full_artifact", None),
        )
        for artifact_type, scope, public_fields in cases:
            with self.subTest(artifact_type=artifact_type), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                rejected = _expected_stage2_public_embedding_consent(
                    artifact_type,
                    scope=scope,
                    public_fields=public_fields,
                )
                rejected["approved"] = False
                paths = _bind_stage2_gate_artifacts(
                    _write_fixture(root, source_classification="synthetic_fixture"),
                    _stage2_plan(),
                    public_consent_overrides={artifact_type: rejected},
                )
                consumption_dir = root / "consumed"
                paths["authorization_consumption_dir"] = consumption_dir
                with self.assertRaisesRegex(
                    ConfirmatoryStudyError,
                    f"{artifact_type} public receipt embedding consent",
                ):
                    run_stage2_confirmatory_study(
                        **paths,
                        output_dir=root / "out",
                    )
                self.assertFalse(consumption_dir.exists())
                self.assertFalse((root / "out").exists())

    def test_stage2_prepublication_privacy_lint_fails_closed_without_value_leakage(self) -> None:
        cases = (
            (
                "unreviewed declaration field",
                "declaration",
                "fixed reviewed schema",
                "private-contract-reference-7821",
            ),
            (
                "absolute declaration path",
                "path",
                "absolute local path",
                "/" + "Users/alice/private/licence.txt",
            ),
            (
                "credential-like plan key",
                "credential",
                "credential-like key",
                "never-publish-this-token-value",
            ),
            (
                "internal registration URL",
                "internal_url",
                "non-public URL address",
                "https://127.0.0.1/private-registration",
            ),
        )
        for label, mutation, pattern, sensitive_value in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                paths = _write_fixture(root, source_classification="synthetic_fixture")
                plan = _stage2_plan()
                if mutation in {"declaration", "path"}:
                    declaration = json.loads(
                        paths["data_declaration_path"].read_text(encoding="utf-8")
                    )
                    if mutation == "declaration":
                        declaration["contract_reference"] = sensitive_value
                    else:
                        declaration["price_semantics"] = sensitive_value
                    paths["data_declaration_path"].write_text(
                        json.dumps(declaration, indent=2) + "\n",
                        encoding="utf-8",
                    )
                elif mutation == "credential":
                    plan["external_registration"]["api_token"] = sensitive_value
                else:
                    plan["external_registration"]["verification_uri"] = sensitive_value
                paths = _bind_stage2_gate_artifacts(paths, plan)
                consumption_dir = root / "consumed"
                paths["authorization_consumption_dir"] = consumption_dir
                with self.assertRaisesRegex(ConfirmatoryStudyError, pattern) as raised:
                    run_stage2_confirmatory_study(
                        **paths,
                        output_dir=root / "out",
                    )
                self.assertNotIn(sensitive_value, str(raised.exception))
                self.assertFalse(consumption_dir.exists())
                self.assertFalse((root / "out").exists())

    def test_stage2_declaration_never_claims_raw_redistribution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _bind_stage2_gate_artifacts(
                _write_fixture(root, source_classification="synthetic_fixture"),
                _stage2_plan(),
            )
            declaration = json.loads(
                paths["data_declaration_path"].read_text(encoding="utf-8")
            )
            for invalid_value in (True, 0, 1):
                with self.subTest(redistributable=invalid_value):
                    changed = json.loads(json.dumps(declaration))
                    changed["redistributable"] = invalid_value
                    with self.assertRaisesRegex(
                        ConfirmatoryStudyError, "public/private semantic fields"
                    ):
                        confirmatory_module._validate_stage2_declaration(changed)

    def test_stage2_public_privacy_lint_covers_path_and_url_forms(self) -> None:
        _validate_stage2_public_receipt_privacy(
            {
                "request": {
                    "route_evidence": {
                        "endpoint_path": "/api/qt/stock/kline/get"
                    }
                }
            },
            label="coverage probe public receipt",
        )
        cases = (
            ("C" + r":\private\review.txt", "absolute local path"),
            ("~/private/review.txt", "absolute local path"),
            ("file:///private/review.txt", "absolute local path"),
            (
                "Reviewed at " + "/" + "Users/reviewer/private.txt",
                "absolute local path",
            ),
            (
                "Stored under " + "/" + "home/reviewer/private.txt",
                "absolute local path",
            ),
            ("Stored under /var/private/review.txt", "absolute local path"),
            ("Reviewed at /workspace/alice/private.txt", "absolute local path"),
            ("Reviewed at /foo/bar", "absolute local path"),
            ("Reviewed path:/foo/bar", "absolute local path"),
            (
                "Copied from D" + r":\private\review.txt",
                "absolute local path",
            ),
            (
                "FILE://" + "/" + "Users/reviewer/private.txt",
                "absolute local path",
            ),
            (
                "file:" + "/" + "Users/reviewer/private.txt",
                "absolute local path",
            ),
            ("http://example.test/review", "non-HTTPS URL"),
            (
                "Reviewed at http://localhost:8080/review",
                "non-HTTPS URL",
            ),
            ("https://user:password@example.test/review", "URL user information"),
            (
                "Reviewer URL: https://user:password@example.test/review",
                "URL user information",
            ),
            (
                "https://example.test/review?access_token=hidden",
                "credential-like URL query key",
            ),
            (
                "Reviewer URL: https://example.test/review?X-API-Key=hidden",
                "credential-like URL query key",
            ),
            (
                "https://example.test/review?%2561pi_key=hidden",
                "credential-like URL query key",
            ),
            (
                "https://example.test/review?redirect="
                "https%3A%2F%2Fuser%3Apassword%40example.test%2Fprivate",
                "URL user information",
            ),
            (
                "https://example.test/review?clientSecret=hidden",
                "credential-like URL query key",
            ),
            (
                "https://example.test/review?X-Amz-Signature=hidden",
                "credential-like URL query key",
            ),
            (
                "https://example.test/callback#access_token=hidden",
                "credential-like URL fragment key",
            ),
            (
                "https://example.test/callback#api%255fkey=hidden",
                "credential-like URL fragment key",
            ),
            (
                "https://example.test/callback/access_token=hidden",
                "credential-like URL path parameter key",
            ),
            (
                "https://example.test/callback;XApiKey=hidden",
                "credential-like URL path parameter key",
            ),
            (
                "https://example.test/callback;"
                "X%252dAmz%252dSignature=hidden",
                "credential-like URL path parameter key",
            ),
            ("https://registry.internal/review", "local or internal URL host"),
            ("https://%6cocalhost/review", "local or internal URL host"),
            ("https://10.0.0.1/review", "non-public URL address"),
            ("https://%31%32%37.0.0.1/review", "non-public URL address"),
        )
        for sensitive_value, pattern in cases:
            with self.subTest(pattern=pattern):
                with self.assertRaisesRegex(
                    ConfirmatoryStudyError, pattern
                ) as raised:
                    _validate_stage2_public_receipt_privacy(
                        {"review_reference": sensitive_value},
                        label="fixture public material",
                    )
                self.assertNotIn(sensitive_value, str(raised.exception))

        for credential_key in (
            "accessToken",
            "refreshToken",
            "clientSecret",
            "privateKey",
            "authorization",
            "bearerToken",
            "X-Amz-Signature",
            "X-API-Key",
            "x_api_key",
            "XApiKey",
            "AWSAccessKeyId",
            "proxy-authorization",
            "%2561pi_key",
            "api%255fkey",
            "X%252dAmz%252dSignature",
            "sig",
        ):
            sensitive_value = f"hidden-{credential_key}-value"
            with self.subTest(credential_key=credential_key):
                with self.assertRaisesRegex(
                    ConfirmatoryStudyError, "credential-like key"
                ) as raised:
                    _validate_stage2_public_receipt_privacy(
                        {
                            "registered_artifact": {
                                "nested_metadata": {
                                    credential_key: sensitive_value,
                                }
                            }
                        },
                        label="fixture public material",
                    )
                self.assertNotIn(sensitive_value, str(raised.exception))

        benign_material = (
            "See https://doi.org/10.1016/j.jfineco.2022.08.003.",
            "The documented API route is /api/qt/stock/kline/get.",
            "The versioned API route is /v1/research/items.",
            "The public endpoint is https://example.test/oauth/token.",
            "Ratios 1/2 and date 2026/09/02 are public metadata.",
            "A generic key identifies each table row.",
        )
        for value in benign_material:
            with self.subTest(benign=value):
                _validate_stage2_public_receipt_privacy(
                    {"review_reference": value},
                    label="fixture public material",
                )
        _validate_stage2_public_receipt_privacy(
            {"key": "public-row-id"},
            label="fixture public material",
        )

    def test_stage2_runner_embeds_only_registered_data_declaration_projection(self) -> None:
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
            self.assertEqual(
                package["projection_schema_version"],
                "stage2_public_data_declaration_projection_v3",
            )
            expected = json.loads(
                paths["data_declaration_path"].read_text(encoding="utf-8")
            )
            expected_projection = {
                field: expected[field]
                for field in STAGE2_PUBLIC_DECLARATION_FIELDS
            }
            self.assertEqual(package["content"], expected_projection)
            self.assertNotIn("source_text", package)
            self.assertNotIn("source_name", receipt["data"])
            self.assertNotIn("rights_review", receipt["data"])
            self.assertEqual(
                package["content"]["dataset_source_mappings"],
                expected["dataset_source_mappings"],
            )
            for source in expected["dataset_source_mappings"]["datasets"].values():
                self.assertIn(source["source_name"], json.dumps(receipt))
            self.assertNotIn(expected["rights_review"], json.dumps(receipt))
            self.assertEqual(
                package["source_file_sha256"],
                _sha256(paths["data_declaration_path"]),
            )
            canonical = (
                json.dumps(
                    expected_projection,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
            self.assertEqual(
                package["projection_sha256"], hashlib.sha256(canonical).hexdigest()
            )
            self.assertEqual(
                receipt["registration_evidence"]["design_manifest"]
                ["public_receipt_projection_sha256"]["data_declaration"],
                package["projection_sha256"],
            )

    def test_stage2_rights_packet_must_authorize_the_exact_declared_source_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _bind_stage2_gate_artifacts(
                _write_fixture(root, source_classification="synthetic_fixture"),
                _stage2_plan(),
            )
            rights_path = paths["data_rights_attestation_path"]
            rights = json.loads(rights_path.read_text(encoding="utf-8"))
            review = json.loads(
                paths["review_attestation_path"].read_text(encoding="utf-8")
            )
            declaration = json.loads(
                paths["data_declaration_path"].read_text(encoding="utf-8")
            )
            declaration["dataset_source_mappings"]["datasets"]["quotes"][
                "source_name"
            ] = "unlicensed substituted source"

            with self.assertRaisesRegex(
                ConfirmatoryStudyError,
                "DATA_DECLARATION_PROJECTION_MISMATCH",
            ):
                confirmatory_module._validate_stage2_rights_attestation(
                    rights_attestation=rights,
                    rights_attestation_bytes=rights_path.read_bytes(),
                    review_attestation=review,
                    data_declaration=declaration,
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
            self.assertNotIn("source_text", evidence)
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
            self.assertEqual(
                receipt["registration_evidence"]["design_manifest"]
                ["public_receipt_projection_sha256"]
                ["official_calendar_session_dates"],
                evidence["canonical_session_dates_sha256"],
            )

    def test_stage2_verifier_rejects_rehashed_public_privacy_tampering(self) -> None:
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
            original = json.loads(
                (root / "out" / "receipt.json").read_text(encoding="utf-8")
            )
            cases = (
                (
                    "credential key",
                    lambda receipt, value: receipt["method"].__setitem__(
                        "api_token", value
                    ),
                    "credential-like key",
                    "receipt-secret-value-1902",
                ),
                (
                    "reintroduced declaration source",
                    lambda receipt, value: receipt["data"]["declaration"].__setitem__(
                        "source_text", value
                    ),
                    "unreviewed fields",
                    "private declaration body 1903",
                ),
            )
            for label, mutate, pattern, sensitive_value in cases:
                with self.subTest(label=label):
                    changed = json.loads(json.dumps(original))
                    mutate(changed, sensitive_value)
                    _rewrite_receipt_integrity(changed)
                    changed_path = root / f"tampered-{label.replace(' ', '-')}.json"
                    changed_path.write_text(
                        json.dumps(
                            changed,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(
                        ConfirmatoryStudyError, pattern
                    ) as raised:
                        verify_stage2_study_receipt(changed_path)
                    self.assertNotIn(sensitive_value, str(raised.exception))

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

            with self.assertRaisesRegex(
                ConfirmatoryStudyError,
                "projection is not bound to the registered design manifest",
            ):
                verify_stage2_study_receipt(forged_path)

    def test_stage2_verifier_rejects_rehashed_calendar_projection_without_manifest_change(self) -> None:
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

            with self.assertRaisesRegex(
                ConfirmatoryStudyError,
                "session projection is not bound to the registered design manifest",
            ):
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

        observations = _run_stage2_registered_cells(
            prepared=_stage2_prepared_with_close_types(base),
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

            with self.assertRaisesRegex(
                ConfirmatoryStudyError,
                "coverage_report_sha256 differs from the locked research artifact",
            ):
                run_stage2_confirmatory_study(**paths, output_dir=root / "out")

    def test_stage2_coverage_probe_receipt_is_strictly_validated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _bind_stage2_gate_artifacts(
                _write_fixture(root, source_classification="synthetic_fixture"),
                _stage2_plan(),
            )
            spec_path = paths["coverage_probe_spec_path"]
            receipt_path = paths["coverage_probe_receipt_path"]
            original = json.loads(receipt_path.read_text(encoding="utf-8"))

            validated = _validate_stage2_coverage_probe_receipt(
                spec_path=spec_path,
                receipt_path=receipt_path,
                expected_study_id="a-share-factor-timing-bias-decomposition-v2",
            )
            self.assertEqual(validated["status"], "PASSED")

            inventory_path = paths["prior_specification_inventory_path"]
            original_inventory_bytes = inventory_path.read_bytes()
            inventory_path.write_bytes(original_inventory_bytes + b" ")
            with self.assertRaisesRegex(
                ConfirmatoryStudyError, "exact prior specification inventory bytes"
            ):
                _validate_stage2_coverage_probe_receipt(
                    spec_path=spec_path,
                    receipt_path=receipt_path,
                    expected_study_id="a-share-factor-timing-bias-decomposition-v2",
                )
            inventory_path.write_bytes(original_inventory_bytes)
            with self.assertRaisesRegex(
                ConfirmatoryStudyError, "after the data review scope cutoff"
            ):
                _validate_stage2_coverage_probe_receipt(
                    spec_path=spec_path,
                    receipt_path=receipt_path,
                    expected_study_id=(
                        "a-share-factor-timing-bias-decomposition-v2"
                    ),
                    review_scope_cutoff_at="2026-08-31T13:20:00+00:00",
                )

            def rewrite(receipt: dict[str, object], *, refresh_id: bool = True) -> None:
                if refresh_id:
                    receipt.pop("receipt_id", None)
                    canonical_without_id = (
                        json.dumps(
                            receipt,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode("utf-8")
                    receipt["receipt_id"] = "sha256:" + hashlib.sha256(
                        canonical_without_id
                    ).hexdigest()
                receipt_path.write_text(
                    json.dumps(
                        receipt,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n",
                    encoding="utf-8",
                )

            def refresh_timestamp_subject(receipt: dict[str, object]) -> None:
                receipt["external_timestamp_proof"]["subject_sha256"] = hashlib.sha256(
                    (
                        json.dumps(
                            receipt["timestamp_package"],
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode("utf-8")
                ).hexdigest()

            def replace_agent_commit(receipt: dict[str, object], value: str) -> None:
                receipt["repository_state"]["agent_commit"] = value
                receipt["timestamp_package"]["agent_commit"] = value
                refresh_timestamp_subject(receipt)

            def replace_inventory_hash(receipt: dict[str, object], value: str) -> None:
                receipt["timestamp_package"][
                    "prior_specification_inventory_sha256"
                ] = value
                refresh_timestamp_subject(receipt)

            cases = (
                (
                    "canonical receipt id",
                    lambda item: item.__setitem__("receipt_id", "sha256:" + "0" * 64),
                    False,
                    "receipt identifier",
                ),
                (
                    "spec hash",
                    lambda item: item.__setitem__("spec_sha256", "0" * 64),
                    True,
                    "specification hash",
                ),
                (
                    "uppercase artifact hash",
                    lambda item: item["artifacts"][0].__setitem__(
                        "sha256", "A" * 64
                    ),
                    True,
                    "private-artifact evidence is invalid",
                ),
                (
                    "study id",
                    lambda item: item.__setitem__("study_id", "wrong-study"),
                    True,
                    "study identifier",
                ),
                (
                    "probe id",
                    lambda item: item.__setitem__("probe_id", "wrong-probe"),
                    True,
                    "probe identifier",
                ),
                (
                    "request scope",
                    lambda item: item["request"].__setitem__(
                        "dates", ["2018-06-29"]
                    ),
                    True,
                    "request scope",
                ),
                (
                    "provider",
                    lambda item: item["request"].__setitem__(
                        "provider_interface", "changed.provider"
                    ),
                    True,
                    "request scope",
                ),
                (
                    "price mode",
                    lambda item: item["request"].__setitem__(
                        "price_mode", "adjusted"
                    ),
                    True,
                    "request scope",
                ),
                (
                    "passed status",
                    lambda item: item.__setitem__("status", "BLOCKED"),
                    True,
                    "must have PASSED",
                ),
                (
                    "complete coverage",
                    lambda item: item["coverage"].__setitem__(
                        "observed_symbol_date_cells", 23
                    ),
                    True,
                    "complete fixed-scope coverage",
                ),
                (
                    "all gates",
                    lambda item: item["gates"].__setitem__(
                        next(iter(item["gates"])), False
                    ),
                    True,
                    "gates have not all passed",
                ),
                (
                    "rights",
                    lambda item: item["rights"].__setitem__(
                        "aggregate_receipt_publication_allowed", False
                    ),
                    True,
                    "rights",
                ),
                (
                    "rights review hash",
                    lambda item: item.__setitem__(
                        "rights_review_sha256", "0" * 63
                    ),
                    True,
                    "rights-review hash",
                ),
                (
                    "missing rights review hash",
                    lambda item: item.pop("rights_review_sha256"),
                    True,
                    "fields differ",
                ),
                (
                    "artifact hash publication consent",
                    lambda item: item["publication_consent"].__setitem__(
                        "artifact_hash_publication_allowed", False
                    ),
                    True,
                    "metadata or identity consent",
                ),
                (
                    "route fallback",
                    lambda item: item["request"]["route_evidence"].__setitem__(
                        "fallback_attempted", True
                    ),
                    True,
                    "exact-date no-fallback",
                ),
                (
                    "claim boundaries",
                    lambda item: item["claim_boundaries"].__setitem__(
                        "factor_outcome_claim_allowed", True
                    ),
                    True,
                    "claim boundaries",
                ),
                (
                    "timestamp subject",
                    lambda item: item["external_timestamp_proof"].__setitem__(
                        "subject_sha256", "0" * 64
                    ),
                    True,
                    "timestamp proof",
                ),
                (
                    "timestamp package inventory binding",
                    lambda item: replace_inventory_hash(item, "0" * 64),
                    True,
                    "does not bind the exact prior specification inventory bytes",
                ),
                (
                    "unsupported timestamp proof label",
                    lambda item: item["external_timestamp_proof"].__setitem__(
                        "type", "detached_digital_signature"
                    ),
                    True,
                    "timestamp proof",
                ),
                (
                    "nonexistent agent commit",
                    lambda item: replace_agent_commit(item, "0" * 40),
                    True,
                    "Git commit object",
                ),
                (
                    "uppercase agent commit",
                    lambda item: replace_agent_commit(item, "A" * 40),
                    True,
                    "repository state is invalid",
                ),
                (
                    "timestamp chronology",
                    lambda item: item["external_timestamp_proof"].__setitem__(
                        "timestamped_at_utc", "2026-08-31T14:00:00+00:00"
                    ),
                    True,
                    "before probe execution",
                ),
                (
                    "timestamp verification after execution",
                    lambda item: item["external_timestamp_proof"].__setitem__(
                        "verified_at_utc", "2026-08-31T13:31:00+00:00"
                    ),
                    True,
                    "timestamp verification chronology",
                ),
            )
            for label, mutate, refresh_id, pattern in cases:
                with self.subTest(label=label):
                    changed = json.loads(json.dumps(original))
                    mutate(changed)
                    rewrite(changed, refresh_id=refresh_id)
                    with self.assertRaisesRegex(ConfirmatoryStudyError, pattern):
                        _validate_stage2_coverage_probe_receipt(
                            spec_path=spec_path,
                            receipt_path=receipt_path,
                            expected_study_id=(
                                "a-share-factor-timing-bias-decomposition-v2"
                            ),
                        )

    def test_stage2_run_requires_the_bound_coverage_probe_receipt_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _bind_stage2_gate_artifacts(
                _write_fixture(root, source_classification="synthetic_fixture"),
                _stage2_plan(),
            )
            paths["coverage_probe_receipt_path"] = root / "missing-probe-receipt.json"
            with self.assertRaisesRegex(
                ConfirmatoryStudyError, "coverage probe receipt"
            ):
                run_stage2_confirmatory_study(**paths, output_dir=root / "out")

    def test_stage2_run_recomputes_coverage_instead_of_trusting_gate_booleans(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _write_fixture(root, source_classification="synthetic_fixture")
            paths = _bind_stage2_gate_artifacts(paths, _stage2_plan())
            from a_share_quant_agent.study_v2_coverage import StudyV2CoverageError

            consumption_dir = root / "consumed"
            paths["authorization_consumption_dir"] = consumption_dir
            with patch(
                "a_share_quant_agent.study_v2_coverage.validate_coverage_report",
                side_effect=StudyV2CoverageError("raw audit mismatch"),
            ), self.assertRaisesRegex(
                ConfirmatoryStudyError, "recomputed raw-input coverage"
            ):
                run_stage2_confirmatory_study(
                    **paths,
                    output_dir=root / "out",
                )
            self.assertEqual(len(list(consumption_dir.iterdir())), 1)

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

    def test_stage2_fundamental_adapter_rejects_raw_duplicate_before_dropping_malformed_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "duplicate-with-malformed-roe.csv"
            path.write_text(
                "symbol,roeDiluted,publishDate,reportPeriodEnd\n"
                "000001.SZ,0.1,2020-04-30,2019-12-31\n"
                "000001.SZ,not-a-number,2020-05-01,2019-12-31\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ConfirmatoryStudyError,
                "duplicate symbol-report periods",
            ):
                _load_stage2_fundamentals(path)

    def test_stage2_fundamental_adapter_rejects_missing_or_invalid_raw_keys(self) -> None:
        invalid_rows = (
            ",0.2,2020-04-30,2019-12-31",
            "000002.SZ,0.2,2020-04-30,not-a-date",
        )
        for invalid_row in invalid_rows:
            with self.subTest(invalid_row=invalid_row), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "invalid-key.csv"
                path.write_text(
                    "symbol,roeDiluted,publishDate,reportPeriodEnd\n"
                    "000001.SZ,0.1,2020-04-30,2019-12-31\n"
                    f"{invalid_row}\n",
                    encoding="utf-8",
                )

                with self.assertRaisesRegex(
                    ConfirmatoryStudyError,
                    "missing or invalid fundamental keys",
                ):
                    _load_stage2_fundamentals(path)

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
        temporary_repository = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_repository.cleanup)
        audited_base, current_head = _two_commit_fixture_repository(
            Path(temporary_repository.name)
        )
        repository_patch = patch(
            "a_share_quant_agent.confirmatory_study._git_repository_root",
            return_value=Path(temporary_repository.name),
        )
        repository_patch.start()
        self.addCleanup(repository_patch.stop)
        entries = [{
            "inventory_id": "fixture-prior-specification",
            "artifact_type": "locked_confirmatory_study_plan",
            "primary_path": "fixture/prior-plan.json",
            "related_paths": [],
            "present_in_repository": True,
            "repository_state": "tracked_at_head",
            "introduced_in_commit": audited_base,
            "commit_semantics": (
                "Fixture commit introducing the prior locked study specification."
            ),
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
            "chronology_contract": {
                "required_order": (
                    "Repository inspection precedes the inventory cutoff and generation."
                ),
                "timestamp_rule": (
                    "Every inventory chronology timestamp is finite and timezone aware."
                ),
                "snapshot_commit_rule": (
                    "The audited repository snapshot is an ancestor of the bound code commit."
                ),
                "cutoff_rule": (
                    "Every in-scope artifact known by the cutoff is included in the inventory."
                ),
                "entries_hash_rule": (
                    "The entries hash binds the canonical JSON representation of every entry."
                ),
                "manifest_gate": (
                    "Only a complete outcome-blind inventory may enter the design manifest."
                ),
            },
            "repository_snapshot": {
                "head_commit": audited_base,
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
            expected_code_commit=current_head,
        )

        def rehash_entries(value: dict[str, object]) -> None:
            value["entry_count"] = len(value["entries"])
            value["entries_sha256"] = hashlib.sha256(
                (
                    json.dumps(
                        value["entries"],
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode()
            ).hexdigest()

        for location, key, expected_pattern in (
            ("root", "outcome_values", "top-level schema"),
            ("root", "mean_ic", "top-level schema"),
            ("chronology_contract", "outcome_values", "chronology contract schema"),
            ("repository_snapshot", "mean_ic", "repository snapshot"),
        ):
            with self.subTest(outcome_bearing_location=location, key=key):
                changed = json.loads(json.dumps(inventory))
                target = changed if location == "root" else changed[location]
                target[key] = [0.123]
                with self.assertRaisesRegex(ConfirmatoryStudyError, expected_pattern):
                    _validate_prior_specification_inventory(
                        changed,
                        study_id=inventory["study_id"],
                        expected_code_commit=current_head,
                    )

        for key in ("mean_ic", "outcome_values"):
            with self.subTest(outcome_bearing_entry_key=key):
                changed = json.loads(json.dumps(inventory))
                changed["entries"][0][key] = [0.123]
                rehash_entries(changed)
                with self.assertRaisesRegex(ConfirmatoryStudyError, "entry .* schema"):
                    _validate_prior_specification_inventory(
                        changed,
                        study_id=inventory["study_id"],
                        expected_code_commit=current_head,
                    )

        malformed_entries = (
            "not-an-entry-object",
            {key: value for key, value in entries[0].items() if key != "artifact_type"},
            {key: value for key, value in entries[0].items() if key != "related_paths"},
            {
                key: value
                for key, value in entries[0].items()
                if key != "specification_ids"
            },
        )
        for malformed_entry in malformed_entries:
            with self.subTest(malformed_entry=malformed_entry):
                changed = json.loads(json.dumps(inventory))
                changed["entries"] = [malformed_entry]
                rehash_entries(changed)
                with self.assertRaisesRegex(ConfirmatoryStudyError, "entry .* schema"):
                    _validate_prior_specification_inventory(
                        changed,
                        study_id=inventory["study_id"],
                        expected_code_commit=current_head,
                    )

        for array_key, malformed_value in (
            ("specification_ids", True),
            ("specification_ids", 1),
            ("related_paths", False),
            ("related_paths", 1),
        ):
            with self.subTest(array_key=array_key, malformed_value=malformed_value):
                changed = json.loads(json.dumps(inventory))
                changed["entries"][0][array_key] = [malformed_value]
                rehash_entries(changed)
                with self.assertRaisesRegex(ConfirmatoryStudyError, array_key):
                    _validate_prior_specification_inventory(
                        changed,
                        study_id=inventory["study_id"],
                        expected_code_commit=current_head,
                    )

        for key, integer_alias in (
            ("outcome_blind_inventory", 1),
            ("contains_outcome_values", 0),
        ):
            with self.subTest(key=key, integer_alias=integer_alias):
                changed = json.loads(json.dumps(inventory))
                changed[key] = integer_alias
                with self.assertRaisesRegex(ConfirmatoryStudyError, "contains outcomes"):
                    _validate_prior_specification_inventory(
                        changed,
                        study_id=inventory["study_id"],
                        expected_code_commit=current_head,
                    )

        for integer_alias in (0, 1):
            with self.subTest(present_in_repository=integer_alias):
                changed = json.loads(json.dumps(inventory))
                changed["entries"][0]["present_in_repository"] = integer_alias
                changed["entries_sha256"] = hashlib.sha256(
                    (
                        json.dumps(
                            changed["entries"],
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode()
                ).hexdigest()
                with self.assertRaisesRegex(
                    ConfirmatoryStudyError, "entry .* is incomplete"
                ):
                    _validate_prior_specification_inventory(
                        changed,
                        study_id=inventory["study_id"],
                        expected_code_commit=current_head,
                    )

        changed = json.loads(json.dumps(inventory))
        changed["entry_count"] = True
        with self.assertRaisesRegex(
            ConfirmatoryStudyError, "entry count is inconsistent"
        ):
            _validate_prior_specification_inventory(
                changed,
                study_id=inventory["study_id"],
                expected_code_commit=current_head,
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
                        expected_code_commit=current_head,
                    )

        changed = json.loads(json.dumps(inventory))
        changed["generated_at"] = "2026-08-31T22:00:00+08:00"
        with self.assertRaisesRegex(ConfirmatoryStudyError, "chronology"):
            _validate_prior_specification_inventory(
                changed,
                study_id=inventory["study_id"],
                expected_code_commit=current_head,
            )

        # The snapshot identifies a pre-inventory base commit. Requiring an
        # ancestor permits later exact-hash bindings without embedding the
        # containing commit's own id in the inventory bytes.
        changed = json.loads(json.dumps(inventory))
        changed["repository_snapshot"]["head_commit"] = current_head
        with self.assertRaisesRegex(ConfirmatoryStudyError, "ancestor"):
            _validate_prior_specification_inventory(
                changed,
                study_id=inventory["study_id"],
                expected_code_commit=audited_base,
            )

    def test_stage2_coverage_probe_spec_freezes_superseded_v1_and_design_boundary(self) -> None:
        spec_path = (
            Path(__file__).resolve().parents[1]
            / "studies"
            / "pit_factor_bias_decomposition_v2"
            / "coverage_probe_spec.v2.json"
        )
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        _validate_stage2_coverage_probe_spec(
            spec, expected_study_id="a-share-factor-timing-bias-decomposition-v2"
        )
        cases = (
            (
                "superseded v1 path",
                lambda item: item["supersedes"].__setitem__(
                    "path", "coverage_probe_spec.other.json"
                ),
                "fixed v1 supersession",
            ),
            (
                "superseded v1 hash",
                lambda item: item["supersedes"].__setitem__("sha256", "A" * 64),
                "fixed v1 supersession",
            ),
            (
                "close-observation field scope",
                lambda item: item.__setitem__(
                    "field_scope_boundary", "legacy adjusted-close-only boundary"
                ),
                "field-scope boundary",
            ),
            (
                "close-observation endpoint contract",
                lambda item: item["stage2_design_boundary"].__setitem__(
                    "endpoint_adapter", "exact_official_session_adjusted_close_only"
                ),
                "design boundary",
            ),
            (
                "variant boundary",
                lambda item: item["stage2_design_boundary"].__setitem__(
                    "variants", 17
                ),
                "design boundary",
            ),
            (
                "cell boundary",
                lambda item: item["stage2_design_boundary"].__setitem__(
                    "factor_variant_cells", 71
                ),
                "design boundary",
            ),
            (
                "primary boundary",
                lambda item: item["stage2_design_boundary"].__setitem__(
                    "primary_estimands", 2
                ),
                "design boundary",
            ),
            (
                "secondary boundary",
                lambda item: item["stage2_design_boundary"].__setitem__(
                    "secondary_estimands", 27
                ),
                "design boundary",
            ),
            (
                "inferential boundary",
                lambda item: item["stage2_design_boundary"].__setitem__(
                    "total_inferential_estimands", 28
                ),
                "design boundary",
            ),
            (
                "required commit contents",
                lambda item: item["execution_boundary"].__setitem__(
                    "required_commit_contents",
                    ["coverage_probe_spec.v2.json"],
                ),
                "required commit contents",
            ),
        )
        for label, mutate, pattern in cases:
            with self.subTest(label=label):
                changed = json.loads(json.dumps(spec))
                mutate(changed)
                with self.assertRaisesRegex(ConfirmatoryStudyError, pattern):
                    _validate_stage2_coverage_probe_spec(
                        changed,
                        expected_study_id="a-share-factor-timing-bias-decomposition-v2",
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

    def test_stage2_global_stop_rule_suppresses_all_estimand_claim_flags(self) -> None:
        plan = _stage2_plan()
        observations: list[dict[str, object]] = []
        months = list(pd.period_range("2010-01", "2022-12", freq="M"))
        bad_cell = (
            months[-1].start_time.date().isoformat(),
            "I1111_full_implementation",
            "momentum_60d",
        )
        for month_index, period in enumerate(months):
            day = period.start_time.date().isoformat()
            wiggle = ((month_index % 7) - 3) * 0.0002
            report_support = -0.002
            record_replacement = -0.020 + wiggle
            publication_support = 0.001
            total_timing = (
                report_support + record_replacement + publication_support
            )
            for variant in plan["variants"]:
                components = set(variant["components"])
                for factor_index, factor in enumerate(plan["factors"], start=1):
                    base = 0.03 + factor_index * 0.01 + month_index * 0.00001
                    if variant["id"] == "A0_final_report_end":
                        value = base - 0.004 + wiggle / 5
                    elif variant["id"] == "A1_pit_report_end":
                        value = base
                    else:
                        value = base
                        if factor == "roe":
                            value += total_timing
                        elif factor == "composite":
                            value -= 0.010 + wiggle / 2
                        value += sum(
                            (index + 1) * 0.0005
                            for index, component in enumerate(STAGE2_COMPONENTS)
                            if component in components
                        ) * (1.0 + wiggle)
                    is_bad = (day, variant["id"], factor) == bad_cell
                    row: dict[str, object] = {
                        "date": day,
                        "variant": variant["id"],
                        "factor": factor,
                        "ic": None if is_bad else value,
                        "top_minus_universe": None if is_bad else value / 10,
                        "cross_section_size": 999 if is_bad else 1000,
                        "sample_audit": {
                            "candidate_count": 1000,
                            "signal_missing_count": 0,
                            "signal_eligible_count": 1000,
                            "estimable_count": 999 if is_bad else 1000,
                            "unresolved_endpoint_count": 1 if is_bad else 0,
                        },
                    }
                    if (
                        variant["id"] == "I0000_pit_publication"
                        and factor == "roe"
                    ):
                        row["publication_exposure"] = {
                            "schema_version": "stage2_publication_exposure_month_v1",
                            "uses_forward_returns": False,
                            "date": day,
                            "report_signal_count": 1000,
                            "publication_signal_count": 950,
                            "common_signal_count": 900,
                            "report_only_count": 100,
                            "publication_only_count": 50,
                            "premature_report_record_count": 500,
                            "premature_report_record_share": 0.5,
                            "changed_report_period_count": 450,
                            "changed_report_period_share": 0.5,
                            "missing_recorded_publish_date_count": 0,
                            "reporting_delay_calendar_days": {
                                "count": 1000,
                                "mean": 90.0,
                                "median": 90.0,
                                "p25": 60.0,
                                "p75": 120.0,
                                "maximum": 180.0,
                            },
                        }
                        row["timing_decomposition"] = {
                            "report_support_restriction": report_support,
                            "common_support_record_replacement": record_replacement,
                            "publication_support_extension": publication_support,
                            "total_timing_difference": total_timing,
                            "efficiency_residual": 0.0,
                            "u_r_count": 1000,
                            "u_p_count": 950,
                            "intersection_count": 900,
                        }
                    observations.append(row)

        status = _stage2_evidence_status(
            declaration={"source_classification": "real_market_data"},
            observations=observations,
            plan=plan,
        )
        self.assertEqual(status["code"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(status["complete_registered_rebalance_count"], 155)
        self.assertIn("UNRESOLVED_FORWARD_ENDPOINTS", status["reason_codes"])

        default_stopped = build_registered_estimands(
            observations,
            plan=plan,
            nw_lag=3,
            minimum_claim_months=120,
        )
        self.assertFalse(default_stopped["global_claim_gate"]["passed"])
        self.assertFalse(default_stopped["primary_family"][0]["claim_eligible"])
        self.assertFalse(
            default_stopped["primary_family"][0]
            ["reject_primary_at_alpha_0_05"]
        )

        locally_eligible = build_registered_estimands(
            observations,
            plan=plan,
            nw_lag=3,
            minimum_claim_months=120,
            global_claim_eligible=True,
        )
        self.assertTrue(locally_eligible["primary_family"][0]["claim_eligible"])
        self.assertTrue(
            locally_eligible["primary_family"][0]
            ["reject_primary_at_alpha_0_05"]
        )

        globally_stopped = build_registered_estimands(
            observations,
            plan=plan,
            nw_lag=3,
            minimum_claim_months=120,
            global_claim_eligible=False,
        )
        self.assertFalse(globally_stopped["global_claim_gate"]["passed"])
        flag_values: list[bool] = []

        def collect_flags(value: object) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == "claim_eligible" or key.startswith("reject_"):
                        flag_values.append(child)
                    collect_flags(child)
            elif isinstance(value, list):
                for child in value:
                    collect_flags(child)

        collect_flags(globally_stopped)
        self.assertTrue(flag_values)
        self.assertTrue(all(value is False for value in flag_values))
        verify_registered_estimands(
            globally_stopped,
            factors=plan["factors"],
            expected_global_claim_eligible=False,
        )

        tampered = json.loads(json.dumps(globally_stopped))
        tampered["primary_family"][0]["claim_eligible"] = True
        with self.assertRaisesRegex(Stage2EstimandError, "global claim gate"):
            verify_registered_estimands(
                tampered,
                factors=plan["factors"],
                expected_global_claim_eligible=False,
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


def _two_commit_fixture_repository(root: Path) -> tuple[str, str]:
    """Create an isolated ancestry fixture without assuming the checkout has HEAD^."""

    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    marker = root / "inventory-state.txt"
    commits: list[str] = []
    for index, value in enumerate(("audited base\n", "bound descendant\n"), start=1):
        marker.write_text(value, encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", marker.name], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "user.name=Inventory Fixture",
                "-c",
                "user.email=inventory-fixture@example.invalid",
                "commit",
                "--quiet",
                "-m",
                f"inventory fixture {index}",
            ],
            check=True,
        )
        commits.append(
            subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
            ).strip()
        )
    return commits[0], commits[1]


def _make_fixture_probe_commit(spec_path: Path, inventory_path: Path) -> str:
    """Create a sparse, unreferenced commit containing the fixture probe blobs."""

    repository = Path(__file__).resolve().parents[1]

    def hash_blob(path: Path) -> str:
        return subprocess.check_output(
            ["git", "-C", str(repository), "hash-object", "-w", str(path)],
            text=True,
        ).strip()

    def make_tree(lines: list[str]) -> str:
        return subprocess.check_output(
            ["git", "-C", str(repository), "mktree"],
            input=("\n".join(lines) + "\n").encode("utf-8"),
        ).decode("ascii").strip()

    spec_blob = hash_blob(spec_path)
    inventory_blob = hash_blob(inventory_path)
    leaf_tree = make_tree([
        f"100644 blob {spec_blob}\tcoverage_probe_spec.v2.json",
        f"100644 blob {inventory_blob}\tprior_specification_inventory.json",
    ])
    study_tree = make_tree([
        f"040000 tree {leaf_tree}\tpit_factor_bias_decomposition_v2",
    ])
    root_tree = make_tree([f"040000 tree {study_tree}\tstudies"])
    environment = os.environ.copy()
    environment.update({
        "GIT_AUTHOR_NAME": "fixture probe",
        "GIT_AUTHOR_EMAIL": "fixture@example.test",
        "GIT_COMMITTER_NAME": "fixture probe",
        "GIT_COMMITTER_EMAIL": "fixture@example.test",
        "GIT_AUTHOR_DATE": "2026-09-01T00:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-09-01T00:00:00+00:00",
    })
    return subprocess.check_output(
        [
            "git", "-C", str(repository), "commit-tree", root_tree,
            "-p", _current_git_sha(), "-m", "fixture probe",
        ],
        env=environment,
        text=True,
    ).strip()


def _stage2_prepared_with_close_types(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy()
    prepared["close_observation_type"] = prepared["is_suspended"].map(
        lambda suspended: (
            "suspension_valuation" if bool(suspended) else "traded_close"
        )
    )
    if "close" not in prepared:
        prepared["close"] = 1.0
    prepared["close_raw"] = prepared["close"]
    prepared["adjustment_factor"] = 1.0
    prepared["price_adjustment_method"] = STAGE2_PRICE_ADJUSTMENT_METHOD
    prepared["price_adjustment_convention"] = STAGE2_PRICE_ADJUSTMENT_CONVENTION
    return prepared


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
        "public_receipt_embedding": _expected_stage2_public_embedding_consent(
            "execution_plan",
            scope="full_artifact",
        ),
        "runtime_contract": {
            "python_version": "3.12.12",
            "numpy_version": "2.0.2",
            "pandas_version": "2.3.3",
            "dependency_match_rule": "exact",
            "whole_repository_clean_required": True,
        },
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
        "coverage_probe_spec_path": "coverage_probe_spec.v2.json",
        "coverage_probe_spec_sha256": "6" * 64,
        "coverage_probe_receipt_path": "coverage_probe_receipt.v2.json",
        "coverage_probe_receipt_sha256": "5" * 64,
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
        "minimum_amount_unit": "CNY",
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
            "mapping_cardinality": "one_to_one",
            "unit": "decimal",
            "publication_date_field": "publishDate",
            "publication_date_semantics": (
                "actual_recorded_disclosure_date_not_scheduled_or_update_date"
            ),
            "maximum_staleness_months": 18,
            "same_day_publication_usable": False,
            "duplicate_symbol_report_period_rule": "fail_closed",
        },
        "security_identifier_contract": json.loads(
            json.dumps(STAGE2_SECURITY_IDENTIFIER_CONTRACT)
        ),
        "universe_contract": json.loads(json.dumps(STAGE2_UNIVERSE_CONTRACT)),
        "rank_group_contract": json.loads(
            json.dumps(STAGE2_RANK_GROUP_CONTRACT)
        ),
        "quote_price_adjustment_contract": json.loads(
            json.dumps(STAGE2_PRICE_ADJUSTMENT_CONTRACT)
        ),
        "ic_outcome_clock": json.loads(json.dumps(STAGE2_IC_OUTCOME_CLOCK)),
        "endpoint_resolution": json.loads(
            json.dumps(STAGE2_ENDPOINT_RESOLUTION_CONTRACT)
        ),
        "inference": {
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
        },
        "roe_timing_common_support_decomposition": {
            "supports": {
                "R_t": (
                    "A1 finite report-period ROE support after non-outcome eligibility "
                    "rules and successful endpoint resolution"
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
                "Recompute both signal and outcome ranks inside the support named by each "
                "IC term."
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
        },
        "publication_exposure_diagnostics": {
            "uses_forward_returns": False,
            "inference": "descriptive_only_outside_bh_family",
            "outputs": [
                "R_t_P_t_C_t_report_only_and_publication_only_counts_by_month",
                "share_of_report_side_selected_records_not_yet_recorded_as_published_at_signal_date",
                "share_of_common_support_records_with_different_selected_report_periods",
                "report_period_end_to_recorded_publish_date_calendar_day_distribution",
            ],
        },
        "missingness": {
            "signal_imputation": "none",
            "composite_complete_case": True,
            "all_registered_monthly_cells_required_for_evidence_status": True,
            "aggregate_signal_missingness_counts_required": True,
            "aggregate_common_support_counts_required": True,
            "endpoint_reason_code_for_every_signal_eligible_record_required": True,
            "outcome_availability_must_not_shrink_signal_eligible_denominator": True,
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
        "reporting_rule": STAGE2_REPORTING_RULE,
        "claim_boundaries": {
            "authorized_accounting_timing_claim": (
                "recorded-publication-date specification effect in a single-version "
                "provider snapshot"
            ),
            "revision_or_vintage_claim": False,
            "historical_investor_observed_value_claim": False,
            "announcement_reaction_or_return_timing_claim": False,
            "portfolio_or_trading_claim": False,
        },
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
    *,
    public_consent_overrides: dict[str, dict[str, object]] | None = None,
) -> dict[str, Path]:
    root = paths["plan_path"].parent
    consent_overrides = public_consent_overrides or {}
    plan["public_receipt_embedding"] = consent_overrides.get(
        "execution_plan",
        plan["public_receipt_embedding"],
    )
    symbols = [f"{index:06d}.SZ" for index in range(1, 9)]
    sessions: list[date] = []
    current = date(2009, 1, 1)
    while current <= date(2023, 1, 31):
        if current.weekday() < 5:
            sessions.append(current)
        current += timedelta(days=1)
    signal_sessions: set[date] = set()
    for session in sessions:
        if date(2010, 1, 1) <= session <= date(2022, 12, 31):
            month_key = (session.year, session.month)
            if not any(
                (known.year, known.month) == month_key
                for known in signal_sessions
            ):
                signal_sessions.add(session)

    official_calendar_path = root / "official_calendar.csv"
    with official_calendar_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("date",))
        writer.writeheader()
        for session in sessions:
            writer.writerow({"date": session.isoformat()})

    quotes_path = root / "stage2_quotes.csv"
    with quotes_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "date", "symbol", "close_raw", "adjustment_factor", "close",
            "price_adjustment_method", "price_adjustment_convention", "amount",
            "is_st", "is_suspended", "close_observation_type", "amount_unit",
        ))
        writer.writeheader()
        for day_index, session in enumerate(sessions):
            for symbol_index, symbol in enumerate(symbols):
                suspension_valuation = (
                    session in signal_sessions and symbol_index == len(symbols) - 1
                )
                writer.writerow({
                    "date": session.isoformat(),
                    "symbol": symbol,
                    "close_raw": f"{10 + symbol_index + day_index * (0.002 + symbol_index * 0.0002):.6f}",
                    "adjustment_factor": "1",
                    "close": f"{10 + symbol_index + day_index * (0.002 + symbol_index * 0.0002):.6f}",
                    "price_adjustment_method": STAGE2_PRICE_ADJUSTMENT_METHOD,
                    "price_adjustment_convention": STAGE2_PRICE_ADJUSTMENT_CONVENTION,
                    "amount": 10_000_000 + symbol_index * 1_000_000,
                    "amount_unit": "CNY",
                    "is_st": str(
                        session in signal_sessions
                        and symbol_index == len(symbols) - 2
                    ),
                    "is_suspended": str(suspension_valuation),
                    "close_observation_type": (
                        "suspension_valuation"
                        if suspension_valuation
                        else "traded_close"
                    ),
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
        "quote_price_adjustment_contract": {
            **STAGE2_PRICE_ADJUSTMENT_CONTRACT,
            "provider_close_raw_definition_sha256": "1" * 64,
            "provider_adjustment_factor_definition_sha256": "2" * 64,
            "normalization_or_adapter_evidence_sha256": "3" * 64,
        },
        "quote_amount_contract": {
            "canonical_amount_unit": "CNY",
            "normalization_stage": (
                "provider_native_amount_normalized_before_raw_input_hash_binding"
            ),
            "provider_raw_amount_unit": "CNY",
            "normalization_method": "identity conversion from provider CNY",
            "normalization_provenance_sha256": "0" * 64,
        },
        "security_identifier_contract": {
            **STAGE2_SECURITY_IDENTIFIER_CONTRACT,
            "provider_identifier_definition_sha256": "4" * 64,
            "code_change_mapping_evidence_sha256": "5" * 64,
        },
    })
    declaration.pop("source_name", None)
    declaration["dataset_source_mappings"] = {
        "schema_version": "stage2_public_dataset_source_mappings_v1",
        "datasets": {
            role: {
                "dataset_role": role,
                "source_name": f"licensed fixture source for {role}",
                "field_mapping": {
                    field: f"fixture_{role}_{field}"
                    for field in STAGE2_REQUIRED_FIELDS[role]
                },
            }
            for role in (
                "quotes",
                "stock_master",
                "fundamentals",
                "official_calendar",
            )
        },
    }
    declaration.setdefault(
        "public_receipt_embedding",
        consent_overrides.get(
            "data_declaration",
            _expected_stage2_public_embedding_consent(
                "data_declaration",
                scope="fixed_public_projection",
                public_fields=STAGE2_PUBLIC_DECLARATION_FIELDS,
            ),
        ),
    )
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
    coverage_probe_spec_path = root / "coverage_probe_spec.v2.json"
    coverage_probe_receipt_path = root / "coverage_probe_receipt.v2.json"
    prior_specification_inventory_path = root / "prior_specification_inventory.json"
    protocol_source_path.write_text("fixture protocol source\n", encoding="utf-8")
    statistical_analysis_plan_path.write_text("fixture statistical analysis plan\n", encoding="utf-8")
    maintained_probe_spec_path = (
        Path(__file__).resolve().parents[1]
        / "studies"
        / "pit_factor_bias_decomposition_v2"
        / "coverage_probe_spec.v2.json"
    )
    coverage_probe_spec_path.write_bytes(maintained_probe_spec_path.read_bytes())
    coverage_probe_spec = json.loads(
        coverage_probe_spec_path.read_text(encoding="utf-8")
    )
    coverage_probe_spec_sha256 = _sha256(coverage_probe_spec_path)
    probe_symbols = [
        row["symbol"]
        for row in coverage_probe_spec["selection_protocol"]["symbols"]
    ]
    probe_gate_ids = [
        row["id"]
        for group in ("pre_execution_gates", "post_collection_quality_gates")
        for row in coverage_probe_spec[group]
    ]
    claim_boundary_keys = list(
        coverage_probe_spec["public_receipt_schema"]["properties"]
        ["claim_boundaries"]["required"]
    )
    publication_consent_keys = list(
        coverage_probe_spec["public_receipt_schema"]["properties"]
        ["publication_consent"]["required"]
    )
    timestamp_package = {
        "schema_version": "stage2_coverage_probe_timestamp_package_v1",
        "study_id": plan["study_id"],
        "probe_id": coverage_probe_spec["probe_id"],
        "spec_path": "studies/pit_factor_bias_decomposition_v2/coverage_probe_spec.v2.json",
        "spec_sha256": coverage_probe_spec_sha256,
        "prior_specification_inventory_path": "studies/pit_factor_bias_decomposition_v2/prior_specification_inventory.json",
        "prior_specification_inventory_sha256": "a" * 64,
        "agent_commit": paths["code_revision"],
    }
    coverage_probe_receipt = {
        "schema_version": "stage2_coverage_probe_receipt_v2",
        "study_id": plan["study_id"],
        "probe_id": coverage_probe_spec["probe_id"],
        "receipt_id": "sha256:" + "0" * 64,
        "spec_sha256": coverage_probe_spec_sha256,
        "timestamp_package": timestamp_package,
        "status": "PASSED",
        "executed_at_utc": "2026-08-31T13:30:00+00:00",
        "external_timestamp_proof": {
            "type": "human_verified_external_timestamp",
            "provider": "fixture timestamp registry",
            "identifier": "fixture-probe-spec-timestamp-v2",
            "timestamped_at_utc": "2026-08-31T13:00:00+00:00",
            "verification_uri": "https://example.test/fixture-probe-timestamp",
            "evidence_sha256": "9" * 64,
            "subject_type": "coverage_probe_package_manifest_sha256",
            "subject_sha256": hashlib.sha256(
                (
                    json.dumps(
                        timestamp_package,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode("utf-8")
            ).hexdigest(),
            "verifier": "fixture independent reviewer",
            "verified_at_utc": "2026-08-31T13:05:00+00:00",
            "trust_boundary": (
                "The timestamp record has no offline-verifiable signature; authenticity "
                "requires independent human verification."
            ),
        },
        "rights_review_sha256": "7" * 64,
        "repository_state": {
            "agent_commit": paths["code_revision"],
            "qdata_commit": coverage_probe_spec["request_protocol"]["locked_runtime"]
            ["qdata_repository_commit"],
            "agent_clean": True,
            "qdata_clean": True,
            "python_version": coverage_probe_spec["request_protocol"]
            ["locked_runtime"]["python_version"],
            "akshare_version": coverage_probe_spec["request_protocol"]
            ["locked_runtime"]["akshare_version"],
        },
        "request": {
            "provider_adapter": coverage_probe_spec["request_protocol"]
            ["provider_adapter"],
            "provider_interface": coverage_probe_spec["request_protocol"]
            ["provider_interface"],
            "upstream_provider_identity": "eastmoney.com",
            "route_evidence": {
                "request_count": 24,
                "requested_https_host": "push2his.eastmoney.com",
                "final_https_host": "push2his.eastmoney.com",
                "endpoint_path": "/api/qt/stock/kline/get",
                "redirect_count": 0,
                "all_requests_exact_single_date": True,
                "fallback_attempted": False,
                "lookback_applied": False,
            },
            "dates": coverage_probe_spec["request_protocol"]["dates"],
            "symbols": probe_symbols,
            "price_mode": coverage_probe_spec["request_protocol"]["price_mode"],
            "adjust_argument": coverage_probe_spec["request_protocol"]
            ["akshare_adjust_argument"],
        },
        "artifacts": [
            {
                "kind": "normalized_private",
                "relative_path": "normalized-bars.csv",
                "sha256": "8" * 64,
                "size_bytes": 1024,
                "row_count": 24,
                "symbol_count": 12,
                "minimum_date": "2016-06-30",
                "maximum_date": "2018-06-29",
                "schema_sha256": "f4ef631a1654c78bca5130c72b9b9226dd3d646c5e001304f315b25a2a2d9f09",
            },
            {
                "kind": "request_log_private",
                "relative_path": "request-log.private.json",
                "sha256": "6" * 64,
                "size_bytes": 2048,
                "row_count": 24,
                "symbol_count": 12,
                "minimum_date": "2016-06-30",
                "maximum_date": "2018-06-29",
                "schema_sha256": "254c5a543c4aef4b3e796f954ec58826f6a20489fd80c14648d2dd4f4480255d",
            },
        ],
        "coverage": {
            "expected_symbol_date_cells": 24,
            "observed_symbol_date_cells": 24,
            "missing_symbol_date_cell_count": 0,
            "duplicate_symbol_date_cells": 0,
            "extra_symbol_date_cells": 0,
        },
        "field_quality": {
            "all_required_raw_bar_fields_valid": True,
            "scope_and_cell_identity_valid": True,
        },
        "failures": {
            "empty_response": 0,
            "validation_error": 0,
            "provider_error": 0,
            "network_error": 0,
        },
        "gates": {gate_id: True for gate_id in probe_gate_ids},
        "rights": {
            "review_status": "verified",
            "raw_redistribution_allowed": False,
            "aggregate_receipt_publication_allowed": True,
        },
        "publication_consent": {
            key: ("verified" if key == "review_status" else True)
            for key in publication_consent_keys
        },
        "claim_boundaries": {key: False for key in claim_boundary_keys},
    }
    coverage_probe_receipt_without_id = dict(coverage_probe_receipt)
    coverage_probe_receipt_without_id.pop("receipt_id")
    coverage_probe_receipt["receipt_id"] = "sha256:" + hashlib.sha256(
        (
            json.dumps(
                coverage_probe_receipt_without_id,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    ).hexdigest()
    coverage_probe_receipt_path.write_text(
        json.dumps(
            coverage_probe_receipt,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    entries = [{
        "inventory_id": "fixture-prior-specification",
        "artifact_type": "locked_confirmatory_study_plan",
        "primary_path": "fixture/prior-plan.json",
        "related_paths": [],
        "present_in_repository": True,
        "repository_state": "tracked_at_head",
        "introduced_in_commit": paths["code_revision"],
        "commit_semantics": (
            "Fixture commit introducing the prior locked study specification."
        ),
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
        "inventory_cutoff_at": "2026-08-31T20:50:00+08:00",
        "generated_at": "2026-08-31T20:55:00+08:00",
        "prepared_by": "fixture preparer",
        "preparer_role": "fixture methods reviewer",
        "outcome_blind_inventory": True,
        "contains_outcome_values": False,
        "purpose": "Enumerate every prior fixture specification without reporting outcome values.",
        "repository_snapshot": {
            "head_commit": paths["code_revision"],
            "inspected_at": "2026-08-31T20:45:00+08:00",
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
    # The production validator binds both probe blobs to the Git commit named
    # in the receipt.  This fixture inventory is intentionally different from
    # the maintained (still-incomplete) repository inventory, so create an
    # unreferenced synthetic commit containing the exact fixture bytes.  It
    # writes only Git objects; HEAD, the index, and the worktree are unchanged.
    fixture_probe_commit = _make_fixture_probe_commit(
        coverage_probe_spec_path, prior_specification_inventory_path
    )
    coverage_probe_receipt = json.loads(
        coverage_probe_receipt_path.read_text(encoding="utf-8")
    )
    coverage_probe_receipt["repository_state"]["agent_commit"] = fixture_probe_commit
    coverage_probe_receipt["timestamp_package"].update(
        {
            "prior_specification_inventory_sha256": _sha256(
                prior_specification_inventory_path
            ),
            "agent_commit": fixture_probe_commit,
        }
    )
    coverage_probe_receipt["external_timestamp_proof"]["subject_sha256"] = (
        hashlib.sha256(
            (
                json.dumps(
                    coverage_probe_receipt["timestamp_package"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
        ).hexdigest()
    )
    coverage_probe_receipt.pop("receipt_id", None)
    canonical_without_id = (
        json.dumps(
            coverage_probe_receipt,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    coverage_probe_receipt["receipt_id"] = "sha256:" + hashlib.sha256(
        canonical_without_id
    ).hexdigest()
    coverage_probe_receipt_path.write_text(
        json.dumps(
            coverage_probe_receipt,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    plan["protocol_source_sha256"] = _sha256(protocol_source_path)
    plan["statistical_analysis_plan_sha256"] = _sha256(statistical_analysis_plan_path)
    plan["coverage_probe_spec_sha256"] = coverage_probe_spec_sha256
    plan["coverage_probe_receipt_sha256"] = _sha256(coverage_probe_receipt_path)
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
    rights_datasets = {
        role: {
            "source_reference": "contract:fixture-stage2",
            "license_or_contract_scope": (
                "private research, permitted aggregate publication, and "
                "controlled reviewer rerun"
            ),
            "terms_evidence_sha256": "b" * 64,
            "local_storage_permitted": True,
            "local_analysis_permitted": True,
            "aggregate_publication_permitted": True,
            "raw_redistribution_permitted": False,
            "hash_publication_permitted": True,
            "controlled_reviewer_rerun_permitted": True,
            "source_identity_publication_permitted": True,
            "field_mapping_citation_permitted": True,
            "authorized_public_projection": json.loads(json.dumps(
                declaration["dataset_source_mappings"]["datasets"][role]
            )),
            "authorized_public_projection_sha256": (
                stage2_public_source_projection_sha256(
                    declaration["dataset_source_mappings"]["datasets"][role]
                )
            ),
            "restrictions": [],
            "conditional_permission_reviews": [],
            **(
                {"calendar_dates_publication_permitted": True}
                if role == "official_calendar"
                else {}
            ),
        }
        for role in (
            "quotes",
            "stock_master",
            "fundamentals",
            "official_calendar",
        )
    }
    rights_attestation = {
        "schema_version": "stage2_data_rights_attestation_v2",
        "study_id": plan["study_id"],
        "status": "attested",
        "attested_at": "2026-08-31T21:50:00+08:00",
        "attestor": "fixture-rights-reviewer",
        "attestor_role": "authorized fixture data custodian",
        "contract_reference": "contract:fixture-stage2",
        "contract_effective_at": "2026-01-01T00:00:00+08:00",
        "contract_expiry_at": None,
        "contract_has_no_expiry_confirmed": True,
        "post_expiry_research_publication_and_controlled_review_rights_survive": False,
        "post_expiry_survival_evidence_sha256": None,
        "contract_evidence_sha256": "c" * 64,
        "datasets": rights_datasets,
        "private_endpoint_reason_ledger": {
            "retention_permitted": True,
            "hash_binding_permitted": True,
            "row_redistribution_permitted": False,
            "terms_evidence_sha256": "d" * 64,
        },
        "public_outputs": {
            "aggregate_coverage_permitted": True,
            "aggregate_missingness_permitted": True,
            "aggregate_reason_counts_permitted": True,
            "cryptographic_hashes_permitted": True,
            "exact_official_calendar_dates_permitted": True,
            "raw_rows_permitted": False,
        },
        "evidence_index": [
            {
                "kind": "contract_terms",
                "reference": "contract:fixture-stage2",
                "sha256": "e" * 64,
            }
        ],
        "signature": {
            "type": "human_verified_evidence",
            "evidence_sha256": "f" * 64,
            "signer_identity": "fixture-rights-reviewer",
            "verification_uri": "https://example.test/fixture-rights-review",
            "trust_boundary": (
                "A human reviewer must verify the contract and the exact permitted outputs."
            ),
        },
    }
    rights_attestation_path = root / "data_rights_attestation.json"
    rights_attestation_path.write_text(
        json.dumps(rights_attestation, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    paths["data_rights_attestation_path"] = rights_attestation_path
    attestation = {
        "schema_version": "stage2_data_review_attestation_v1",
        "study_id": plan["study_id"],
        "status": "reviewed_pass",
        "review_scope_cutoff_at": "2026-08-31T21:55:00+08:00",
        "coverage_probe_spec_path": plan["coverage_probe_spec_path"],
        "coverage_probe_spec_sha256": plan["coverage_probe_spec_sha256"],
        "coverage_probe_receipt_path": plan["coverage_probe_receipt_path"],
        "coverage_probe_receipt_sha256": plan["coverage_probe_receipt_sha256"],
        "execution_semantics_verified": True,
        "tradability_fields_verified": True,
        "exact_endpoint_resolution_semantics_verified": True,
        "suspension_valuation_semantics_verified": True,
        "price_adjustment_semantics_verified": True,
        "amount_unit_normalization_semantics_verified": True,
        "endpoint_reason_ledger_rights_verified": True,
        "historical_membership_completeness_verified": True,
        "terminal_survivor_comparator_verified": True,
        "security_identifier_semantics_verified": True,
        "fundamental_publication_semantics_verified": True,
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
            "exact_endpoint_resolution": "6" * 64,
            "suspension_valuation_semantics": "b" * 64,
            "provider_close_raw_definition": "c" * 64,
            "provider_adjustment_factor_convention": "d" * 64,
            "price_adjustment_normalization": "e" * 64,
            "amount_unit_normalization": "0" * 64,
            "endpoint_reason_ledger_rights": "7" * 64,
            "historical_membership_completeness": "9" * 64,
            "terminal_survivor_comparator": "8" * 64,
            "security_identifier_semantics": "7" * 64,
            "code_change_mapping": "6" * 64,
            "fundamental_publication_semantics": "a" * 64,
            "data_rights": _sha256(rights_attestation_path),
            "official_calendar": "4" * 64,
        },
        "review_assertions": {
            "adjusted_close_return_semantics_and_corporate_action_handling_are_documented": True,
            "unadjusted_open_and_nonfill_semantics_are_not_claimed_by_the_ic_core": True,
            "amount_units_and_cutoff_timing_are_documented": True,
            "provider_raw_amount_unit_and_normalization_to_exact_cny_before_input_binding_are_documented": True,
            "st_and_suspension_fields_are_non_degenerate_and_historically_effective": True,
            "signal_eligible_denominator_is_fixed_before_outcome_lookup": True,
            "current_ic_core_resolves_only_exact_provider_recorded_close_observations_on_required_official_sessions": True,
            "close_observation_type_matches_suspension_state_on_every_quote_row": True,
            "suspension_valuation_is_provider_recorded_or_published_for_the_exact_official_session_and_never_researcher_forward_filled": True,
            "price_adjustment_method_and_convention_tokens_match_the_fixed_contract_on_every_quote_row": True,
            "close_equals_close_raw_times_adjustment_factor_within_the_fixed_tolerance_on_every_quote_row": True,
            "provider_close_raw_adjustment_factor_and_no_rebasing_definitions_are_hash_evidenced": True,
            "all_signal_session_candidates_have_exact_t_t1_t20_t21_endpoints_before_design_freeze": True,
            "unresolved_endpoints_cannot_be_dropped_shifted_carried_forward_or_assigned_default_recovery": True,
            "delisting_terminal_wealth_adapter_is_not_claimed_by_the_current_ic_core": True,
            "private_endpoint_reason_ledger_hash_and_public_aggregate_counts_are_permitted": True,
            "stock_master_covers_every_strict_sh_sz_a_share_active_at_any_time_from_2009_01_through_2023_01_and_is_not_latest_only": True,
            "terminal_survivor_comparator_uses_delist_date_null_or_strictly_after_2023_01_31_independent_of_acquisition_date": True,
            "provider_stable_security_identifier_semantics_are_identical_across_quotes_stock_master_and_fundamentals": True,
            "historical_security_code_changes_and_reassignments_have_a_documented_reviewed_mapping_before_input_hash_binding": True,
            "roe_diluted_mapping_is_one_to_one_decimal_and_publish_date_is_actual_recorded_disclosure_date_not_scheduled_or_update_date": True,
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
        "coverage_probe_spec_path": plan["coverage_probe_spec_path"],
        "coverage_probe_receipt_path": plan["coverage_probe_receipt_path"],
        "coverage_probe_spec_sha256": plan["coverage_probe_spec_sha256"],
        "coverage_probe_receipt_sha256": plan["coverage_probe_receipt_sha256"],
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
            "no_factor_return_ic_rank_or_variant_outcome_was_computed_released_or_human_inspected_through_attested_at": True,
            "registered_publication_exposure_diagnostic_values_not_inspected_through_attested_at": True,
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
            "coverage_probe_spec_sha256",
            "coverage_probe_receipt_sha256",
            "coverage_report_sha256", "review_attestation_sha256",
            "protocol_source_sha256", "statistical_analysis_plan_sha256",
            "prior_specification_inventory_sha256",
            "prior_exposure_attestation_sha256",
        )
    }
    expected_artifacts["prior_exposure_log_sha256"] = _sha256(
        prior_exposure_log_path
    )
    declaration_projection = {
        field: json.loads(json.dumps(declaration[field]))
        for field in STAGE2_PUBLIC_DECLARATION_FIELDS
    }
    public_projection_hashes = {
        "data_declaration": hashlib.sha256(
            (
                json.dumps(
                    declaration_projection,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
        ).hexdigest(),
        "official_calendar_session_dates": hashlib.sha256(
            (
                json.dumps(
                    [session.isoformat() for session in sessions],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
        ).hexdigest(),
    }
    design_manifest = {
        "schema_version": "stage2_design_manifest_v1",
        "study_id": plan["study_id"],
        "status": "frozen_outcome_blind",
        "design_frozen_at": plan["design_frozen_at"],
        "plan_core_sha256": plan["external_registration"]["registered_content_sha256"],
        "artifacts": expected_artifacts,
        "input_file_sha256": input_hashes,
        "public_receipt_projection_sha256": public_projection_hashes,
        "code_commit": plan["code_commit"],
        "public_receipt_embedding": consent_overrides.get(
            "design_manifest",
            _expected_stage2_public_embedding_consent(
                "design_manifest",
                scope="full_artifact",
            ),
        ),
        "registered_design_assertions": json.loads(
            json.dumps(STAGE2_REGISTERED_DESIGN_ASSERTIONS)
        ),
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
        "coverage_probe_receipt_sha256": plan[
            "coverage_probe_receipt_sha256"
        ],
        "registered_scope_summary": json.loads(
            json.dumps(STAGE2_REGISTERED_SCOPE_SUMMARY)
        ),
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
        "public_receipt_embedding": consent_overrides.get(
            "registration_receipt",
            _expected_stage2_public_embedding_consent(
                "registration_receipt",
                scope="full_artifact",
            ),
        ),
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
        "authorizer_authority_basis": (
            "Authorized fixture data custodian under the reviewed contract."
        ),
        "design_manifest_sha256": plan["external_registration"][
            "design_manifest_sha256"
        ],
        "registration_receipt_sha256": plan["external_registration"][
            "registration_receipt_sha256"
        ],
        "plan_core_sha256": plan["external_registration"][
            "registered_content_sha256"
        ],
        "bound_artifacts": {
            **expected_artifacts,
            "data_rights_attestation_sha256": _sha256(rights_attestation_path),
            "code_commit": plan["code_commit"],
        },
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
            "data_rights_active_at_authorization_and_post_expiry_publication_review_survival_confirmed": True,
            "no_factor_return_ic_rank_or_variant_outcome_was_computed_released_or_human_inspected_before_authorization": True,
            "all_bound_hashes_recomputed_and_equal": True,
        },
        "release_scope": {
            "authorized_runner_scope": "ic_core_only",
            "authorized_analysis_period": plan["test_period"],
            "authorized_code_commit": plan["code_commit"],
            "outcome_data_release_permitted_after_authorized_at": True,
            "quote_price_adjustment_contract": STAGE2_PRICE_ADJUSTMENT_CONTRACT,
            "security_identifier_contract": STAGE2_SECURITY_IDENTIFIER_CONTRACT,
            "universe_contract": STAGE2_UNIVERSE_CONTRACT,
            "rank_group_contract": STAGE2_RANK_GROUP_CONTRACT,
            "authorized_core_outputs": [
                "18_variant_72_cell_ic_lattice",
                "one_primary_and_28_secondary_inferential_estimands",
                "three_part_ordered_roe_common_support_decomposition",
                "aggregate_signal_missingness_and_common_support_counts",
                "no_return_publication_exposure_diagnostics",
                "per_security_endpoint_reason_ledger_hash_and_aggregate_receipt_counts",
            ],
            "endpoint_boundary": STAGE2_AUTHORIZATION_ENDPOINT_BOUNDARY,
            "claim_boundary": (
                "The strongest authorized accounting-timing claim is a "
                "recorded-publication-date specification effect in a single-version provider "
                "snapshot. Revision, vintage-value, historical-investor-observed-value, "
                "announcement-reaction, and return-timing claims remain unauthorized."
            ),
            "planned_excluded_modules_remain_unauthorized": [
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
        "public_receipt_embedding": consent_overrides.get(
            "execution_authorization",
            _expected_stage2_public_embedding_consent(
                "execution_authorization",
                scope="full_artifact",
            ),
        ),
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
        "coverage_probe_spec_path": coverage_probe_spec_path,
        "coverage_probe_receipt_path": coverage_probe_receipt_path,
        "review_attestation_path": attestation_path,
        "design_manifest_path": design_manifest_path,
        "registration_receipt_path": registration_receipt_path,
        "execution_authorization_path": execution_authorization_path,
        "authorization_consumption_dir": root / "private-consumption-store",
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
        data["declaration"]["projection_sha256"] = hashlib.sha256(
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
    receipt["status"] = _stage2_evidence_status(
        declaration={"source_classification": "real_market_data"},
        observations=receipt["monthly_observations"],
        plan=plan,
    )
    receipt["status"]["revision_history_claim"] = False
    receipt["estimands"] = build_registered_estimands(
        receipt["monthly_observations"],
        plan=plan,
        nw_lag=int(plan["newey_west_lag"]),
        minimum_claim_months=int(plan["minimum_significance_months"]),
        global_claim_eligible=(
            receipt["status"]["code"]
            == "REAL_MARKET_REGISTERED_HISTORICAL_IC_CORE_STATISTICS"
        ),
    )
    receipt["sample"]["symbol_count"] = 1000
    receipt["sample"]["complete_registered_rebalance_count"] = receipt["status"][
        "complete_registered_rebalance_count"
    ]
    _rewrite_receipt_integrity(receipt)


if __name__ == "__main__":
    unittest.main()
