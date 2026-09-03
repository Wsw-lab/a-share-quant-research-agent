from __future__ import annotations

import csv
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import inspect
import io
import json
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

import a_share_quant_agent.study_v2_coverage as coverage
from a_share_quant_agent.study_v2_coverage import (
    StudyV2CoverageError,
    audit_study_inputs,
)


class StudyV2CoverageAuditTest(unittest.TestCase):
    def test_authoritative_report_is_external_atomic_private_and_no_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repository = root / "independent-repository"
            linked = root / "linked-worktree"
            repository.mkdir()
            subprocess.run(
                ["git", "init", "-q", str(repository)],
                check=True,
                capture_output=True,
            )
            (repository / "tracked.txt").write_text("fixture\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(repository), "add", "tracked.txt"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repository),
                    "-c",
                    "user.name=Coverage Fixture",
                    "-c",
                    "user.email=coverage-fixture@example.test",
                    "commit",
                    "-q",
                    "-m",
                    "fixture",
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repository),
                    "worktree",
                    "add",
                    "--detach",
                    str(linked),
                    "HEAD",
                ],
                check=True,
                capture_output=True,
            )
            report = {"gates": {"ready_to_lock_stage2_plan": False}}

            for worktree in (repository, linked):
                target = worktree / "ignored" / "coverage.json"
                with self.subTest(worktree=worktree), self.assertRaisesRegex(
                    StudyV2CoverageError,
                    "must be outside every Git worktree",
                ):
                    coverage.write_coverage_report(report, target)
                self.assertFalse(target.exists())

            cli_target = repository / "ignored" / "cli-coverage.json"
            with mock.patch.object(coverage, "audit_study_inputs") as audit, self.assertRaisesRegex(
                StudyV2CoverageError,
                "must be outside every Git worktree",
            ):
                coverage.main(
                    [
                        "--quotes", "unused-quotes.csv",
                        "--stock-master", "unused-master.csv",
                        "--fundamentals", "unused-fundamentals.csv",
                        "--official-calendar", "unused-calendar.csv",
                        "--output", str(cli_target),
                    ]
                )
            audit.assert_not_called()
            self.assertFalse(cli_target.exists())

            external = root / "private-evidence" / "coverage.json"
            coverage.write_coverage_report(report, external)
            self.assertEqual(
                stat.S_IMODE(external.stat().st_mode),
                0o600,
            )
            self.assertEqual(
                external.read_bytes(),
                coverage._canonical_json_bytes(report) + b"\n",
            )

            sentinel = b"do not overwrite\n"
            existing = root / "private-evidence" / "existing.json"
            existing.write_bytes(sentinel)
            with self.assertRaisesRegex(StudyV2CoverageError, "already exists"):
                coverage.write_coverage_report(report, existing)
            self.assertEqual(existing.read_bytes(), sentinel)

    def test_official_calendar_is_a_required_raw_input_contract(self) -> None:
        self.assertIn(
            "official_calendar_path",
            inspect.signature(audit_study_inputs).parameters,
        )
        self.assertIn(
            "official_calendar_csv",
            inspect.signature(coverage.recompute_coverage_report).parameters,
        )
        self.assertIn(
            "official_calendar_csv",
            inspect.signature(coverage.validate_coverage_report).parameters,
        )

    def test_cli_binds_official_calendar_into_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            output = root / "coverage.json"
            try:
                with redirect_stdout(io.StringIO()):
                    status = coverage.main(
                        [
                            "--quotes", str(quotes),
                            "--stock-master", str(master),
                            "--fundamentals", str(fundamentals),
                            "--official-calendar", str(calendar),
                            "--output", str(output),
                        ]
                    )
            except SystemExit as exc:
                self.fail(f"CLI rejected the official-calendar contract: {exc}")

            self.assertEqual(status, 1)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertEqual(report["official_calendar"]["sha256"], _sha256(calendar))
            self.assertFalse(report["gates"]["ready_to_lock_stage2_plan"])

    def test_cli_returns_zero_only_for_ready_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "coverage.json"
            paths = {
                "quotes": root / "quotes.csv",
                "stock_master": root / "stock_master.csv",
                "fundamentals": root / "fundamentals.csv",
                "official_calendar": root / "official_calendar.csv",
            }
            for path in paths.values():
                path.write_text("placeholder\n", encoding="utf-8")
            ready_report = {"gates": {"ready_to_lock_stage2_plan": True}}
            with mock.patch.object(
                coverage, "audit_study_inputs", return_value=ready_report
            ), mock.patch.object(coverage, "write_coverage_report"):
                with redirect_stdout(io.StringIO()):
                    status = coverage.main(
                        [
                            "--quotes", str(paths["quotes"]),
                            "--stock-master", str(paths["stock_master"]),
                            "--fundamentals", str(paths["fundamentals"]),
                            "--official-calendar", str(paths["official_calendar"]),
                            "--output", str(output),
                        ]
                    )
            self.assertEqual(status, 0)

    def test_coverage_audit_rejects_symlink_inputs_before_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            linked_quotes = root / "linked_quotes.csv"
            try:
                linked_quotes.symlink_to(quotes)
            except OSError as exc:  # pragma: no cover - platform restriction
                self.skipTest(f"symlinks unavailable: {exc}")

            with self.assertRaisesRegex(
                StudyV2CoverageError, "quotes is not a regular file"
            ):
                audit_study_inputs(
                    quotes_path=linked_quotes,
                    stock_master_path=master,
                    fundamentals_path=fundamentals,
                    official_calendar_path=calendar,
                )

    def test_attestation_cannot_override_missing_fixed_sample_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertEqual(report["schema_version"], "study_v2_data_coverage_audit_v1")
            self.assertEqual(report["quotes"]["market_start"], "2015-01-05")
            self.assertEqual(report["quotes"]["market_end"], "2025-01-06")
            self.assertEqual(report["fundamentals"]["publish_date_non_null_rate"], 1.0)
            self.assertFalse(report["gates"]["minimum_history_years_met"])
            self.assertFalse(report["gates"]["target_quote_interval_available"])
            self.assertFalse(report["gates"]["target_fundamental_interval_available"])
            self.assertFalse(report["gates"]["minimum_monthly_observations_met"])
            self.assertFalse(report["gates"]["minimum_symbols_per_month_met"])
            self.assertFalse(
                report["gates"][
                    "fundamental_complete_quote_contract_support_met"
                ]
            )
            self.assertTrue(report["gates"]["publication_date_coverage_met"])
            self.assertTrue(report["gates"]["execution_columns_present"])
            self.assertFalse(report["gates"]["execution_semantics_verified"])
            self.assertFalse(report["gates"]["tradability_fields_verified"])
            self.assertFalse(report["gates"]["data_rights_verified"])
            self.assertFalse(report["gates"]["ready_to_lock_stage2_plan"])
            self.assertIn(
                "EXECUTION_SEMANTICS_NOT_VERIFIED",
                report["gates"]["blocking_reason_codes"],
            )
            self.assertIn(
                "INSUFFICIENT_COMPLETE_QUOTE_FUNDAMENTAL_JOINT_SUPPORT",
                report["gates"]["blocking_reason_codes"],
            )
            self.assertFalse(report["gates"]["complete_revision_vintage_available"])
            self.assertFalse(report["gates"]["revision_history_claim_allowed"])
            self.assertNotIn(str(root), str(report))

            attested = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
                review_attestation=_review_attestation(
                    quotes, master, fundamentals, calendar
                ),
            )
            self.assertTrue(attested["gates"]["execution_semantics_verified"])
            self.assertTrue(attested["gates"]["tradability_fields_verified"])
            self.assertTrue(attested["gates"]["data_rights_verified"])
            self.assertTrue(
                attested["review_attestation"][
                    "exact_endpoint_resolution_semantics_verified"
                ]
            )
            self.assertTrue(
                attested["review_attestation"][
                    "endpoint_reason_ledger_rights_verified"
                ]
            )
            self.assertEqual(
                attested["review_attestation"]["coverage_probe_receipt_path"],
                "coverage_probe_receipt.v2.json",
            )
            self.assertEqual(
                attested["review_attestation"]["coverage_probe_receipt_sha256"],
                "8" * 64,
            )
            self.assertFalse(attested["gates"]["ready_to_lock_stage2_plan"])

    def test_review_attestation_binds_recomputed_input_identity_and_calendar_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            valid = _review_attestation(quotes, master, fundamentals, calendar)

            cases = (
                ("missing identity", lambda item: item.__setitem__("input_identity", None), "input identity"),
                (
                    "quote row count",
                    lambda item: item["input_identity"]["quotes"].__setitem__("row_count", 999),
                    "row count",
                ),
                (
                    "quote date range",
                    lambda item: item["input_identity"]["quotes"].__setitem__("minimum_date", "1900-01-01"),
                    "date range",
                ),
                (
                    "fundamental date range",
                    lambda item: item["input_identity"]["fundamentals"].__setitem__("maximum_publish_date", "2099-01-01"),
                    "date range",
                ),
                (
                    "calendar source name",
                    lambda item: item["input_identity"]["official_calendar"].__setitem__("source_name", ""),
                    "provenance",
                ),
                (
                    "calendar source reference",
                    lambda item: item["input_identity"]["official_calendar"].__setitem__("source_reference", "todo"),
                    "provenance",
                ),
                (
                    "calendar generated timestamp",
                    lambda item: item["input_identity"]["official_calendar"].__setitem__("source_generated_at", None),
                    "provenance",
                ),
                (
                    "calendar timezone",
                    lambda item: item["input_identity"]["official_calendar"].__setitem__("timezone", "UTC"),
                    "provenance",
                ),
            )
            for label, mutate, pattern in cases:
                with self.subTest(label=label):
                    changed = deepcopy(valid)
                    mutate(changed)
                    with self.assertRaisesRegex(StudyV2CoverageError, pattern):
                        audit_study_inputs(
                            quotes_path=quotes,
                            stock_master_path=master,
                            fundamentals_path=fundamentals,
                            official_calendar_path=calendar,
                            review_attestation=changed,
                        )

    def test_review_attestation_accepts_only_lowercase_human_evidence_signature(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            valid = _review_attestation(quotes, master, fundamentals, calendar)
            for signature_type in ("detached_digital_signature", "external_registry_attestation"):
                changed = deepcopy(valid)
                changed["signature"]["type"] = signature_type
                with self.subTest(signature_type=signature_type), self.assertRaisesRegex(
                    StudyV2CoverageError, "signature is invalid"
                ):
                    audit_study_inputs(
                        quotes_path=quotes,
                        stock_master_path=master,
                        fundamentals_path=fundamentals,
                        official_calendar_path=calendar,
                        review_attestation=changed,
                    )
            changed = deepcopy(valid)
            changed["signature"]["evidence_sha256"] = "A" * 64
            with self.assertRaisesRegex(StudyV2CoverageError, "signature is invalid"):
                audit_study_inputs(
                    quotes_path=quotes,
                    stock_master_path=master,
                    fundamentals_path=fundamentals,
                    official_calendar_path=calendar,
                    review_attestation=changed,
                )

    def test_review_attestation_requires_membership_and_publication_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            valid = _review_attestation(quotes, master, fundamentals, calendar)
            cases = (
                (
                    "suspension valuation flag",
                    lambda item: item.__setitem__(
                        "suspension_valuation_semantics_verified", False
                    ),
                    "suspension_valuation_semantics_verified must be true",
                ),
                (
                    "suspension valuation evidence",
                    lambda item: item["evidence_sha256"].__setitem__(
                        "suspension_valuation_semantics", None
                    ),
                    "suspension_valuation_semantics evidence hash is invalid",
                ),
                (
                    "price adjustment semantics flag",
                    lambda item: item.__setitem__(
                        "price_adjustment_semantics_verified", False
                    ),
                    "price_adjustment_semantics_verified must be true",
                ),
                (
                    "provider raw close definition evidence",
                    lambda item: item["evidence_sha256"].__setitem__(
                        "provider_close_raw_definition", None
                    ),
                    "provider_close_raw_definition evidence hash is invalid",
                ),
                (
                    "close observation mapping assertion",
                    lambda item: item["review_assertions"].__setitem__(
                        "close_observation_type_matches_suspension_state_on_every_quote_row",
                        False,
                    ),
                    "assertions have not all passed",
                ),
                (
                    "candidate endpoint assertion",
                    lambda item: item["review_assertions"].__setitem__(
                        "all_signal_session_candidates_have_exact_t_t1_t20_t21_endpoints_before_design_freeze",
                        False,
                    ),
                    "assertions have not all passed",
                ),
                (
                    "membership flag",
                    lambda item: item.__setitem__(
                        "historical_membership_completeness_verified", False
                    ),
                    "historical_membership_completeness_verified must be true",
                ),
                (
                    "terminal survivor flag",
                    lambda item: item.__setitem__(
                        "terminal_survivor_comparator_verified", False
                    ),
                    "terminal_survivor_comparator_verified must be true",
                ),
                (
                    "identifier semantics flag",
                    lambda item: item.__setitem__(
                        "security_identifier_semantics_verified", False
                    ),
                    "security_identifier_semantics_verified must be true",
                ),
                (
                    "code change mapping evidence",
                    lambda item: item["evidence_sha256"].__setitem__(
                        "code_change_mapping", None
                    ),
                    "code_change_mapping evidence hash is invalid",
                ),
                (
                    "publication evidence",
                    lambda item: item["evidence_sha256"].__setitem__(
                        "fundamental_publication_semantics", None
                    ),
                    "fundamental_publication_semantics evidence hash is invalid",
                ),
                (
                    "membership assertion",
                    lambda item: item["review_assertions"].__setitem__(
                        "stock_master_covers_every_strict_sh_sz_a_share_active_at_any_time_from_2009_01_through_2023_01_and_is_not_latest_only",
                        False,
                    ),
                    "assertions have not all passed",
                ),
            )
            for label, mutate, pattern in cases:
                with self.subTest(label=label):
                    changed = deepcopy(valid)
                    mutate(changed)
                    with self.assertRaisesRegex(StudyV2CoverageError, pattern):
                        audit_study_inputs(
                            quotes_path=quotes,
                            stock_master_path=master,
                            fundamentals_path=fundamentals,
                            official_calendar_path=calendar,
                            review_attestation=changed,
                        )

    def test_recompute_from_raw_csv_records_fixed_contract_and_normalized_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )

            self.assertTrue(
                hasattr(coverage, "recompute_coverage_report"),
                "coverage module must expose the pure raw-CSV recomputation API",
            )
            report = coverage.recompute_coverage_report(
                quotes_csv=quotes.read_bytes(),
                stock_master_csv=master.read_bytes(),
                fundamentals_csv=fundamentals.read_bytes(),
                official_calendar_csv=calendar.read_bytes(),
                input_names={
                    "quotes": "quotes.csv",
                    "stock_master": "stock_master.csv",
                    "fundamentals": "fundamentals.csv",
                    "official_calendar": "official_calendar.csv",
                },
            )

            self.assertEqual(
                report["parameters"],
                {
                    "analysis_end": "2022-12-31",
                    "analysis_start": "2010-01-01",
                    "minimum_history_years": 13.0,
                    "minimum_monthly_observations": 156,
                    "minimum_publish_date_rate": 0.95,
                    "minimum_sessions_per_month": 15,
                    "minimum_symbols_per_month": 1000,
                    "maximum_fundamental_staleness_months": 18,
                    "required_fundamental_end": "2022-12-31",
                    "required_fundamental_start": "2009-01-01",
                    "required_official_calendar_first_month": "2009-01",
                    "required_official_calendar_last_month": "2023-01",
                    "required_quote_end": "2023-01-31",
                    "required_quote_start": "2009-01-01",
                    "terminal_survivor_cutoff": "2023-01-31",
                    "security_identifier_contract_id": (
                        "provider_stable_exchange_qualified_security_identifier_with_"
                        "reviewed_code_change_mapping_v1"
                    ),
                },
            )
            self.assertEqual(report["parameters"], report["thresholds"])
            self.assertEqual(report["inputs"]["hash_algorithm"], "sha256")
            self.assertEqual(report["inputs"]["hash_basis"], "raw_csv_bytes")
            self.assertEqual(
                report["inputs"]["normalization"],
                {
                    "blank_values": "strip_surrounding_whitespace_then_empty_is_null",
                    "column_names": "case_sensitive_exact_header_names",
                    "csv_dialect": "excel",
                    "date_values": (
                        "exact_YYYY-MM-DD_valid_calendar_date_and_pandas_"
                        "nanosecond_safe_1677-09-22_through_2262-04-11"
                    ),
                    "encoding": "utf-8-sig",
                    "logical_key_symbols": (
                        "strip_surrounding_whitespace_then_uppercase"
                    ),
                    "numeric_values": (
                        "exact_ASCII_decimal_with_optional_sign_fraction_and_base10_exponent"
                    ),
                },
            )
            self.assertEqual(
                report["inputs"]["files"]["quotes"]["sha256"],
                _sha256(quotes),
            )
            self.assertEqual(
                report["inputs"]["files"]["stock_master"]["file_name"],
                "stock_master.csv",
            )
            self.assertEqual(
                report["inputs"]["files"]["official_calendar"]["sha256"],
                _sha256(calendar),
            )
            self.assertEqual(report["gates"]["expected_analysis_month_count"], 156)

    def test_public_report_uses_fixed_logical_names_and_never_operator_basenames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            private_names = {
                "quotes": "person-alice_account-731_wind-quotes.csv",
                "stock_master": "person-bob_account-842_csmar-master.csv",
                "fundamentals": "client-carol_provider-resset-fundamentals.csv",
                "official_calendar": "operator-dan_provider-choice-calendar.csv",
            }
            renamed_paths = {}
            for role, path in zip(
                ("quotes", "stock_master", "fundamentals", "official_calendar"),
                (quotes, master, fundamentals, calendar),
            ):
                renamed_paths[role] = path.rename(root / private_names[role])

            attestation = _review_attestation(
                renamed_paths["quotes"],
                renamed_paths["stock_master"],
                renamed_paths["fundamentals"],
                renamed_paths["official_calendar"],
            )
            report = audit_study_inputs(
                quotes_path=renamed_paths["quotes"],
                stock_master_path=renamed_paths["stock_master"],
                fundamentals_path=renamed_paths["fundamentals"],
                official_calendar_path=renamed_paths["official_calendar"],
                review_attestation=attestation,
            )
            expected_names = {
                "quotes": "quotes.csv",
                "stock_master": "stock_master.csv",
                "fundamentals": "fundamentals.csv",
                "official_calendar": "official_calendar.csv",
            }
            self.assertEqual(
                {
                    role: report["inputs"]["files"][role]["file_name"]
                    for role in expected_names
                },
                expected_names,
            )
            self.assertEqual(
                {role: report[role]["file_name"] for role in expected_names},
                expected_names,
            )
            serialized = json.dumps(report, sort_keys=True)
            for private_name in private_names.values():
                self.assertNotIn(private_name, serialized)

            raw_inputs = {
                role: path.read_bytes() for role, path in renamed_paths.items()
            }
            recomputed = coverage.recompute_coverage_report(
                quotes_csv=raw_inputs["quotes"],
                stock_master_csv=raw_inputs["stock_master"],
                fundamentals_csv=raw_inputs["fundamentals"],
                official_calendar_csv=raw_inputs["official_calendar"],
                input_names=private_names,
                review_attestation=attestation,
            )
            self.assertEqual(recomputed, report)
            validated = coverage.validate_coverage_report(
                report,
                quotes_csv=raw_inputs["quotes"],
                stock_master_csv=raw_inputs["stock_master"],
                fundamentals_csv=raw_inputs["fundamentals"],
                official_calendar_csv=raw_inputs["official_calendar"],
                input_names={
                    role: f"different-person-provider-{role}.csv"
                    for role in expected_names
                },
                review_attestation=attestation,
            )
            self.assertEqual(validated, report)

    def test_audit_rejects_threshold_override_outside_fixed_design(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )

            with self.assertRaisesRegex(StudyV2CoverageError, "fixed design contract"):
                audit_study_inputs(
                    quotes_path=quotes,
                    stock_master_path=master,
                    fundamentals_path=fundamentals,
                    official_calendar_path=calendar,
                    minimum_symbols_per_month=999,
                )

    def test_strict_validator_rejects_threshold_tampering_despite_all_true_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )
            tampered = deepcopy(report)
            tampered["thresholds"]["minimum_symbols_per_month"] = 1
            _force_all_gates_true(tampered)

            with self.assertRaisesRegex(StudyV2CoverageError, "recomputed raw CSV"):
                coverage.validate_coverage_report(
                    tampered,
                    quotes_csv=quotes.read_bytes(),
                    stock_master_csv=master.read_bytes(),
                    fundamentals_csv=fundamentals.read_bytes(),
                    official_calendar_csv=calendar.read_bytes(),
                    input_names=_input_names(quotes, master, fundamentals, calendar),
                )

    def test_strict_validator_rejects_date_tampering_despite_all_true_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )
            tampered = deepcopy(report)
            tampered["parameters"]["analysis_start"] = "2011-01-01"
            tampered["thresholds"]["analysis_start"] = "2011-01-01"
            _force_all_gates_true(tampered)

            with self.assertRaisesRegex(StudyV2CoverageError, "recomputed raw CSV"):
                coverage.validate_coverage_report(
                    tampered,
                    quotes_csv=quotes.read_bytes(),
                    stock_master_csv=master.read_bytes(),
                    fundamentals_csv=fundamentals.read_bytes(),
                    official_calendar_csv=calendar.read_bytes(),
                    input_names=_input_names(quotes, master, fundamentals, calendar),
                )

    def test_strict_validator_rejects_handwritten_all_true_skeleton(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            skeleton = {
                "schema_version": "study_v2_data_coverage_audit_v1",
                "parameters": {
                    "analysis_start": "2010-01-01",
                    "analysis_end": "2022-12-31",
                    "required_quote_start": "2009-01-01",
                    "required_quote_end": "2023-01-31",
                    "minimum_history_years": 13.0,
                    "minimum_monthly_observations": 156,
                    "minimum_symbols_per_month": 1000,
                    "minimum_sessions_per_month": 15,
                    "minimum_publish_date_rate": 0.95,
                    "maximum_fundamental_staleness_months": 18,
                    "required_fundamental_start": "2009-01-01",
                    "required_fundamental_end": "2022-12-31",
                    "required_official_calendar_first_month": "2009-01",
                    "required_official_calendar_last_month": "2023-01",
                },
                "quotes": {"sha256": _sha256(quotes)},
                "stock_master": {"sha256": _sha256(master)},
                "fundamentals": {"sha256": _sha256(fundamentals)},
                "official_calendar": {"sha256": _sha256(calendar)},
                "gates": {
                    "minimum_history_years_met": True,
                    "target_quote_interval_available": True,
                    "target_fundamental_interval_available": True,
                    "minimum_monthly_observations_met": True,
                    "minimum_symbols_per_month_met": True,
                    "publication_date_coverage_met": True,
                    "point_in_time_membership_available": True,
                    "execution_columns_present": True,
                    "execution_semantics_verified": True,
                    "tradability_fields_verified": True,
                    "data_rights_verified": True,
                    "ready_to_lock_stage2_plan": True,
                    "blocking_reason_codes": [],
                },
            }

            with self.assertRaisesRegex(StudyV2CoverageError, "recomputed raw CSV"):
                coverage.validate_coverage_report(
                    skeleton,
                    quotes_csv=quotes.read_bytes(),
                    stock_master_csv=master.read_bytes(),
                    fundamentals_csv=fundamentals.read_bytes(),
                    official_calendar_csv=calendar.read_bytes(),
                    input_names=_input_names(quotes, master, fundamentals, calendar),
                )

    def test_strict_validator_accepts_exact_recomputation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            validated = coverage.validate_coverage_report(
                report,
                quotes_csv=quotes.read_bytes(),
                stock_master_csv=master.read_bytes(),
                fundamentals_csv=fundamentals.read_bytes(),
                official_calendar_csv=calendar.read_bytes(),
                input_names=_input_names(quotes, master, fundamentals, calendar),
            )

            self.assertEqual(validated, report)

    def test_sparse_quote_dates_fail_monthly_official_session_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            for index in range(20):
                _append_quote(quotes, "2020-01-02", f"{200001 + index:06d}.SZ")

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            calendar_january = _month_row(report["official_calendar"], "2020-01")
            quotes_january = _month_row(report["quotes"], "2020-01")
            self.assertEqual(calendar_january["session_count"], 15)
            self.assertEqual(quotes_january["session_count"], 1)
            self.assertEqual(quotes_january.get("official_session_count"), 1)
            self.assertEqual(report["gates"]["full_month_count"], 0)
            self.assertFalse(report["gates"]["minimum_sessions_per_month_met"])
            self.assertIn(
                {"month": "2020-01", "official_quote_session_count": 1},
                report["gates"].get("insufficient_official_quote_session_months", []),
            )
            self.assertIn(
                "INSUFFICIENT_MONTHLY_SESSION_COVERAGE",
                report["gates"]["blocking_reason_codes"],
            )
            self.assertTrue(
                report["gates"]["target_official_calendar_interval_available"]
            )

    def test_per_symbol_contract_rejects_dense_rebalance_sparse_panel(self) -> None:
        sessions = _contract_calendar(date(2010, 1, 1))
        symbols = {f"{index:06d}.SZ" for index in range(1, 1001)}
        anchor = "000001.SZ"
        dated_symbols = {session: {anchor} for session in sessions}
        dated_symbols[date(2010, 1, 1)] = set(symbols)

        result = coverage._quote_contract_monthly_coverage(
            dated_quote_symbols=dated_symbols,
            official_sessions=sessions,
            expected_months=("2010-01",),
            eligible_master_symbols=symbols,
            minimum_symbols=1000,
        )

        january = result["monthly_coverage"][0]
        self.assertEqual(january["rebalance_symbol_count"], 1000)
        self.assertEqual(january["momentum_60d_symbol_count"], 1)
        self.assertEqual(january["low_volatility_20d_symbol_count"], 1)
        self.assertEqual(january["amount_20d_symbol_count"], 1)
        self.assertEqual(january["exact_endpoint_symbol_count"], 1)
        self.assertEqual(january["complete_quote_contract_symbol_count"], 1)
        self.assertFalse(result["complete_quote_contract_coverage_met"])
        self.assertEqual(
            result["insufficient_complete_quote_contract_months"],
            [{"month": "2010-01", "complete_quote_contract_symbol_count": 1}],
        )

    def test_exact_endpoint_threshold_cannot_hide_missing_candidate_endpoint(
        self,
    ) -> None:
        sessions = _contract_calendar(date(2010, 1, 1))
        symbols = {"000001.SZ", "000002.SZ"}
        dated_symbols = {session: set(symbols) for session in sessions}
        dated_symbols[sessions[-1]] = {"000001.SZ"}

        result = coverage._quote_contract_monthly_coverage(
            dated_quote_symbols=dated_symbols,
            official_sessions=sessions,
            expected_months=("2010-01",),
            eligible_master_symbols=symbols,
            minimum_symbols=1,
        )

        january = result["monthly_coverage"][0]
        self.assertEqual(january["signal_session_candidate_symbol_count"], 2)
        self.assertEqual(january["exact_endpoint_symbol_count"], 1)
        self.assertEqual(january["missing_exact_endpoint_candidate_count"], 1)
        self.assertTrue(result["exact_endpoint_coverage_met"])
        self.assertFalse(
            result["all_signal_session_candidates_have_exact_endpoints"]
        )

    def test_signal_session_close_observation_types_can_pass_non_degeneracy(
        self,
    ) -> None:
        signal_session = date(2010, 1, 4)
        raw_quotes = (
            "date,symbol,close_observation_type\n"
            "2010-01-04,000001.SZ,traded_close\n"
            "2010-01-04,000002.SZ,suspension_valuation\n"
            "2010-01-05,000003.SZ,traded_close\n"
        ).encode("utf-8")

        result = coverage._signal_session_close_observation_coverage(
            raw_quotes,
            signal_session_candidates={
                signal_session: {"000001.SZ", "000002.SZ"}
            },
            source_name="quotes.csv",
        )

        self.assertEqual(
            result["signal_session_close_observation_type_counts"],
            {"suspension_valuation": 1, "traded_close": 1},
        )
        self.assertEqual(
            result["signal_session_close_observation_invalid_row_count"], 0
        )
        self.assertTrue(
            result["signal_session_close_observation_types_non_degenerate"]
        )

    def test_fundamental_support_must_intersect_complete_quote_contract(self) -> None:
        signal_date = date(2010, 1, 4)
        quote_complete = "000001.SZ"
        fundamental_only = "000002.SZ"
        raw_fundamentals = (
            "symbol,roeDiluted,publishDate,reportPeriodEnd\n"
            f"{fundamental_only},0.10,2009-10-30,2009-09-30\n"
        ).encode("utf-8")

        result = coverage._fundamental_monthly_coverage(
            raw_csv=raw_fundamentals,
            expected_months=("2010-01",),
            official_sessions={signal_date},
            monthly_quote_symbols={
                "2010-01": {quote_complete, fundamental_only}
            },
            eligible_master_symbols={quote_complete, fundamental_only},
            eligible_universe_symbols={quote_complete, fundamental_only},
            complete_quote_contract_symbols_by_month={
                "2010-01": {quote_complete}
            },
            required_start=date(2009, 1, 1),
            required_end=date(2010, 12, 31),
            maximum_staleness_months=18,
        )

        january = result["monthly_coverage"][0]
        self.assertEqual(january["nonstale_fundamental_symbol_count"], 1)
        self.assertEqual(january["complete_quote_contract_symbol_count"], 1)
        self.assertEqual(
            january["nonstale_complete_contract_fundamental_symbol_count"], 0
        )

    def test_quote_symbol_index_uses_compact_bitmap_set_views(self) -> None:
        symbols = tuple(f"{index:06d}.SZ" for index in range(1, 257))
        sessions = tuple(
            date(2010, 1, 1) + timedelta(days=offset) for offset in range(15)
        )
        rows = ["date,symbol"]
        for session_index, session in enumerate(sessions):
            session_symbols = symbols if session_index % 2 == 0 else symbols[::2]
            rows.extend(
                f"{session.isoformat()},{symbol}" for symbol in session_symbols
            )
        payload = ("\n".join(rows) + "\n").encode("utf-8")

        indexed_symbols, dated_symbols = coverage._quote_symbol_index(payload)

        self.assertEqual(indexed_symbols, set(symbols))
        self.assertEqual(len(dated_symbols), len(sessions))
        full_view = dated_symbols.get(sessions[0], set())
        half_view = dated_symbols.get(sessions[1], set())
        self.assertNotIsInstance(full_view, set)
        self.assertEqual(set(full_view), set(symbols))
        self.assertEqual(set(half_view), set(symbols[::2]))
        subset = {symbols[0], symbols[1], symbols[-1]}
        self.assertEqual(full_view & subset, subset)
        self.assertEqual(subset & half_view, {symbols[0]})
        intersection_update = set(subset)
        intersection_update.intersection_update(half_view)
        self.assertEqual(intersection_update, {symbols[0]})
        self.assertEqual(dated_symbols.get(date(1999, 1, 1), set()), set())
        self.assertTrue(
            all(
                isinstance(mask, int)
                for mask in dated_symbols._date_masks.values()
            )
        )

    def test_per_symbol_contract_scopes_universe_to_signal_day_lifecycle(self) -> None:
        sessions = _contract_calendar(date(2010, 1, 1))
        symbols = {
            "000001.SZ",
            "000002.SZ",
            "000003.SZ",
            "600001.SH",
        }
        dated_symbols = {session: set(symbols) for session in sessions}
        lifecycles = {
            "000001.SZ": (date(2000, 1, 1), None),
            "000002.SZ": (date(2010, 1, 2), None),
            "000003.SZ": (date(2000, 1, 1), date(2009, 12, 31)),
            "600001.SH": (date(2000, 1, 1), date(2010, 1, 1)),
        }

        result = coverage._quote_contract_monthly_coverage(
            dated_quote_symbols=dated_symbols,
            official_sessions=sessions,
            expected_months=("2010-01",),
            eligible_master_symbols=symbols,
            minimum_symbols=2,
            master_lifecycles=lifecycles,
        )

        january = result["monthly_coverage"][0]
        self.assertEqual(january["active_strict_a_share_symbol_count"], 2)
        self.assertEqual(january["rebalance_symbol_count"], 2)
        self.assertEqual(january["complete_quote_contract_symbol_count"], 2)
        self.assertTrue(result["complete_quote_contract_coverage_met"])

    def test_per_symbol_contract_detects_missing_first_warmup_session(self) -> None:
        sessions = _contract_calendar(date(2010, 1, 1))
        symbols = {"000001.SZ", "000002.SZ"}
        dated_symbols = {session: set(symbols) for session in sessions}
        dated_symbols[sessions[0]] = {"000001.SZ"}

        result = coverage._quote_contract_monthly_coverage(
            dated_quote_symbols=dated_symbols,
            official_sessions=sessions,
            expected_months=("2010-01",),
            eligible_master_symbols=symbols,
            minimum_symbols=2,
        )

        january = result["monthly_coverage"][0]
        self.assertEqual(january["momentum_start_date"], "2009-11-02")
        self.assertEqual(january["momentum_60d_symbol_count"], 1)
        self.assertEqual(january["low_volatility_20d_symbol_count"], 2)
        self.assertEqual(january["amount_20d_symbol_count"], 2)
        self.assertEqual(january["exact_endpoint_symbol_count"], 2)
        self.assertFalse(result["momentum_60d_history_coverage_met"])
        self.assertTrue(result["exact_endpoint_coverage_met"])
        self.assertFalse(result["complete_quote_contract_coverage_met"])

    def test_per_symbol_contract_requires_contiguous_momentum_history(self) -> None:
        sessions = _contract_calendar(date(2010, 1, 1))
        symbols = {"000001.SZ", "000002.SZ"}
        dated_symbols = {session: set(symbols) for session in sessions}
        dated_symbols[sessions[30]] = {"000001.SZ"}

        result = coverage._quote_contract_monthly_coverage(
            dated_quote_symbols=dated_symbols,
            official_sessions=sessions,
            expected_months=("2010-01",),
            eligible_master_symbols=symbols,
            minimum_symbols=2,
        )

        january = result["monthly_coverage"][0]
        self.assertEqual(january["momentum_60d_symbol_count"], 1)
        self.assertEqual(january["low_volatility_20d_symbol_count"], 2)
        self.assertEqual(january["exact_endpoint_symbol_count"], 2)
        self.assertFalse(result["momentum_60d_history_coverage_met"])
        self.assertFalse(result["complete_quote_contract_coverage_met"])

    def test_per_symbol_contract_detects_missing_january_lag_exit(self) -> None:
        sessions = _contract_calendar(
            date(2022, 12, 1), lag_exit=date(2023, 1, 3)
        )
        symbols = {"000001.SZ", "000002.SZ"}
        dated_symbols = {session: set(symbols) for session in sessions}
        dated_symbols[sessions[-1]] = {"000001.SZ"}

        result = coverage._quote_contract_monthly_coverage(
            dated_quote_symbols=dated_symbols,
            official_sessions=sessions,
            expected_months=("2022-12",),
            eligible_master_symbols=symbols,
            minimum_symbols=2,
        )

        december = result["monthly_coverage"][0]
        self.assertEqual(december["lag_exit_date"], "2023-01-03")
        self.assertEqual(december["momentum_60d_symbol_count"], 2)
        self.assertEqual(december["low_volatility_20d_symbol_count"], 2)
        self.assertEqual(december["amount_20d_symbol_count"], 2)
        self.assertEqual(december["exact_endpoint_symbol_count"], 1)
        self.assertTrue(result["momentum_60d_history_coverage_met"])
        self.assertFalse(result["exact_endpoint_coverage_met"])
        self.assertFalse(result["complete_quote_contract_coverage_met"])

    def test_report_fails_closed_on_per_symbol_quote_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertEqual(
                len(report["quotes"]["per_symbol_quote_contract_monthly_coverage"]),
                156,
            )
            self.assertFalse(
                report["gates"]["required_session_geometry_coverage_met"]
            )
            self.assertFalse(
                report["gates"]["momentum_60d_history_coverage_met"]
            )
            self.assertFalse(
                report["gates"]["low_volatility_20d_history_coverage_met"]
            )
            self.assertFalse(report["gates"]["amount_20d_history_coverage_met"])
            self.assertFalse(report["gates"]["exact_endpoint_coverage_met"])
            self.assertFalse(
                report["gates"]["complete_quote_contract_coverage_met"]
            )
            self.assertFalse(report["gates"]["minimum_symbols_per_month_met"])
            self.assertIn(
                "INSUFFICIENT_COMPLETE_PER_SYMBOL_QUOTE_COVERAGE",
                report["gates"]["blocking_reason_codes"],
            )
            self.assertIn(
                "REQUIRED_QUOTE_SESSION_GEOMETRY_UNAVAILABLE",
                report["gates"]["blocking_reason_codes"],
            )

    def test_membership_records_malformed_scoped_dates_as_blocking(self) -> None:
        fixtures = (
            (
                "000001.SZ",
                {"listDate": "not-a-date"},
                "MISSING_OR_INVALID_SCOPED_LIST_DATE",
            ),
            (
                "600000.SH",
                {"delistDate": "not-a-date"},
                "INVALID_SCOPED_DELIST_DATE",
            ),
        )
        for symbol, updates, expected_reason in fixtures:
            with self.subTest(expected_reason=expected_reason):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    quotes, master, fundamentals, calendar = _write_panel(
                        root, missing_publish_date=False
                    )
                    _rewrite_master_row(master, symbol, **updates)

                    report = audit_study_inputs(
                        quotes_path=quotes,
                        stock_master_path=master,
                        fundamentals_path=fundamentals,
                        official_calendar_path=calendar,
                    )

                    self.assertFalse(
                        report["gates"]["point_in_time_membership_available"]
                    )
                    self.assertIn(
                        expected_reason,
                        report["stock_master"][
                            "membership_blocking_reason_codes"
                        ],
                    )

    def test_membership_requires_valid_list_date_for_every_scoped_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            for index in range(20):
                _append_master_row(
                    master,
                    symbol=f"{100001 + index:06d}.SZ",
                    list_date="2000-01-01",
                    delist_date="",
                    list_status="listed",
                    stock_type="A股",
                )
            _rewrite_master_row(master, "000001.SZ", listDate="")

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertGreater(report["stock_master"]["non_null_list_date_rate"], 0.95)
            self.assertFalse(report["gates"]["point_in_time_membership_available"])
            self.assertEqual(
                report["stock_master"].get("missing_or_invalid_scoped_list_date_count"),
                1,
            )
            self.assertIn(
                "MISSING_OR_INVALID_SCOPED_LIST_DATE",
                report["stock_master"].get("membership_blocking_reason_codes", []),
            )

    def test_membership_requires_delist_date_and_valid_lifecycle_order(self) -> None:
        fixtures = (
            (
                {"delistDate": ""},
                "DELISTED_ROW_MISSING_DELIST_DATE",
            ),
            (
                {"listDate": "2024-01-01", "delistDate": "2023-12-29"},
                "DELIST_DATE_BEFORE_LIST_DATE",
            ),
        )
        for updates, expected_reason in fixtures:
            with self.subTest(expected_reason=expected_reason):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    quotes, master, fundamentals, calendar = _write_panel(
                        root, missing_publish_date=False
                    )
                    _rewrite_master_row(master, "600000.SH", **updates)

                    report = audit_study_inputs(
                        quotes_path=quotes,
                        stock_master_path=master,
                        fundamentals_path=fundamentals,
                        official_calendar_path=calendar,
                    )

                    self.assertFalse(
                        report["gates"]["point_in_time_membership_available"]
                    )
                    self.assertIn(
                        expected_reason,
                        report["stock_master"].get(
                            "membership_blocking_reason_codes", []
                        ),
                    )

    def test_membership_allows_delist_date_equal_to_list_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            _rewrite_master_row(
                master,
                "600000.SH",
                listDate="2023-12-29",
                delistDate="2023-12-29",
            )

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertTrue(report["gates"]["point_in_time_membership_available"])
            self.assertEqual(
                report["stock_master"].get("membership_blocking_reason_codes"),
                [],
            )

    def test_membership_rejects_status_date_inconsistency(self) -> None:
        fixtures = (
            (
                {"delistDate": "2020-01-01", "listStatus": "listed"},
                "ACTIVE_ROW_HAS_DELIST_DATE",
            ),
            (
                {"delistDate": "", "listStatus": "unknown"},
                "UNRECOGNIZED_LIST_STATUS",
            ),
        )
        for updates, expected_reason in fixtures:
            with self.subTest(expected_reason=expected_reason):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    quotes, master, fundamentals, calendar = _write_panel(
                        root, missing_publish_date=False
                    )
                    _rewrite_master_row(master, "000001.SZ", **updates)

                    report = audit_study_inputs(
                        quotes_path=quotes,
                        stock_master_path=master,
                        fundamentals_path=fundamentals,
                        official_calendar_path=calendar,
                    )

                    self.assertFalse(
                        report["gates"]["point_in_time_membership_available"]
                    )
                    self.assertIn(
                        expected_reason,
                        report["stock_master"].get(
                            "membership_blocking_reason_codes", []
                        ),
                    )

    def test_membership_lifecycle_validation_is_limited_to_scoped_a_shares(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            _append_master_row(
                master,
                symbol="900001.SH",
                list_date="",
                delist_date="",
                list_status="",
                stock_type="指数",
            )

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertTrue(report["gates"]["point_in_time_membership_available"])
            self.assertEqual(report["stock_master"].get("scoped_row_count"), 2)
            self.assertEqual(
                report["stock_master"].get("membership_blocking_reason_codes"),
                [],
            )

    def test_quote_interval_uses_bound_calendar_sessions_not_month_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            _append_quote(quotes, "2009-01-05", "000001.SZ")

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertEqual(report["quotes"]["market_start"], "2009-01-05")
            self.assertEqual(
                report["gates"]["required_quote_session_start"], "2009-01-05"
            )
            self.assertEqual(
                report["gates"]["required_quote_session_end"], "2023-01-31"
            )
            self.assertTrue(report["gates"]["target_quote_interval_available"])

    def test_quote_date_outside_official_calendar_blocks_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            _remove_calendar_date(calendar, "2025-01-06")

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertIn("quote_dates_are_official_sessions", report["gates"])
            self.assertFalse(report["gates"]["quote_dates_are_official_sessions"])
            self.assertEqual(report["gates"]["non_calendar_quote_date_count"], 1)
            self.assertIn(
                "QUOTE_DATES_OUTSIDE_OFFICIAL_CALENDAR",
                report["gates"]["blocking_reason_codes"],
            )

    def test_quote_numeric_integrity_is_aggregate_only_and_blocks_readiness(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            baseline = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )
            self.assertTrue(baseline["quotes"]["numeric_integrity_verified"])
            self.assertTrue(baseline["gates"]["quote_numeric_integrity_met"])
            self.assertEqual(baseline["quotes"]["close_invalid_rate"], 0.0)
            self.assertEqual(baseline["quotes"]["amount_invalid_rate"], 0.0)

            _rewrite_quote_numeric_values(
                quotes,
                (
                    {"close": "", "amount": ""},
                    {"close": "not-a-close", "amount": "Infinity"},
                    {"close": "0", "amount": "-12345.67"},
                ),
            )
            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertEqual(report["quotes"]["close_blank_row_count"], 1)
            self.assertEqual(
                report["quotes"][
                    "close_non_numeric_or_non_finite_row_count"
                ],
                1,
            )
            self.assertEqual(report["quotes"]["close_non_positive_row_count"], 1)
            self.assertEqual(report["quotes"]["close_invalid_row_count"], 3)
            self.assertEqual(report["quotes"]["close_invalid_rate"], 0.5)
            self.assertEqual(report["quotes"]["amount_blank_row_count"], 1)
            self.assertEqual(
                report["quotes"][
                    "amount_non_numeric_or_non_finite_row_count"
                ],
                1,
            )
            self.assertEqual(report["quotes"]["amount_negative_row_count"], 1)
            self.assertEqual(report["quotes"]["amount_invalid_row_count"], 3)
            self.assertEqual(report["quotes"]["amount_invalid_rate"], 0.5)
            self.assertFalse(report["quotes"]["numeric_integrity_verified"])
            self.assertFalse(report["gates"]["quote_numeric_integrity_met"])
            self.assertFalse(report["gates"]["ready_to_lock_stage2_plan"])
            for reason in (
                "QUOTE_CLOSE_BLANK",
                "QUOTE_CLOSE_NON_NUMERIC_OR_NON_FINITE",
                "QUOTE_CLOSE_NON_POSITIVE",
                "QUOTE_AMOUNT_BLANK",
                "QUOTE_AMOUNT_NON_NUMERIC_OR_NON_FINITE",
                "QUOTE_AMOUNT_NEGATIVE",
            ):
                self.assertIn(reason, report["gates"]["blocking_reason_codes"])
            serialized = json.dumps(report)
            self.assertNotIn("not-a-close", serialized)
            self.assertNotIn("Infinity", serialized)
            self.assertNotIn("-12345.67", serialized)

    def test_quote_boolean_integrity_uses_runner_tokens_and_requires_both_states(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            _rewrite_quote_boolean_values(
                quotes,
                is_st=(" TRUE ", "1", "yes", "False", "0", "NO"),
                is_suspended=("false", "0", "no", "TRUE", "1", "Yes"),
            )
            valid = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertEqual(
                valid["quotes"]["is_st_distinct_canonical_states"],
                ["false", "true"],
            )
            self.assertEqual(
                valid["quotes"]["is_suspended_distinct_canonical_states"],
                ["false", "true"],
            )
            self.assertTrue(valid["quotes"]["boolean_integrity_verified"])
            self.assertTrue(valid["gates"]["quote_boolean_integrity_met"])
            self.assertTrue(valid["gates"]["close_observation_contract_met"])
            self.assertTrue(
                valid["gates"][
                    "signal_session_close_observation_types_non_degenerate"
                ]
            )

            _rewrite_quote_boolean_values(
                quotes,
                is_st=("", "not-a-boolean", "yes", "1", "TRUE", "true"),
                is_suspended=(" no ", "no", "0", "FALSE", "No", "false"),
            )
            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertEqual(report["quotes"]["is_st_blank_row_count"], 1)
            self.assertEqual(
                report["quotes"]["is_st_invalid_boolean_row_count"], 1
            )
            self.assertEqual(
                report["quotes"]["is_st_distinct_canonical_states"], ["true"]
            )
            self.assertFalse(report["quotes"]["is_st_non_degenerate"])
            self.assertEqual(
                report["quotes"]["is_suspended_distinct_canonical_states"],
                ["false"],
            )
            self.assertFalse(report["quotes"]["is_suspended_non_degenerate"])
            self.assertFalse(report["quotes"]["boolean_integrity_verified"])
            self.assertFalse(report["gates"]["quote_boolean_integrity_met"])
            self.assertFalse(
                report["gates"]["required_field_non_null_integrity_met"]
            )
            self.assertFalse(report["gates"]["ready_to_lock_stage2_plan"])
            for reason in (
                "QUOTE_IS_ST_BLANK",
                "QUOTE_IS_ST_INVALID_BOOLEAN",
                "QUOTE_IS_ST_DEGENERATE",
                "QUOTE_IS_SUSPENDED_DEGENERATE",
            ):
                self.assertIn(reason, report["gates"]["blocking_reason_codes"])
            self.assertNotIn("not-a-boolean", json.dumps(report))

    def test_quote_amount_unit_must_be_exact_cny_before_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            valid = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )
            self.assertTrue(valid["quotes"]["canonical_amount_unit_verified"])
            self.assertTrue(valid["gates"]["canonical_amount_unit_met"])

            _rewrite_csv_rows(
                quotes, ((0, {"amount_unit": "thousand_CNY"}),)
            )
            blocked = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )
            self.assertEqual(blocked["quotes"]["amount_unit_non_cny_row_count"], 1)
            self.assertFalse(blocked["gates"]["canonical_amount_unit_met"])
            self.assertIn(
                "QUOTE_AMOUNT_UNIT_NOT_EXACT_CNY",
                blocked["gates"]["blocking_reason_codes"],
            )

    def test_adjusted_close_formula_and_tokens_fail_closed_before_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            valid = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )
            self.assertTrue(valid["quotes"]["price_adjustment_contract_verified"])
            self.assertTrue(valid["gates"]["price_adjustment_contract_met"])

            for label, update, reason in (
                (
                    "method",
                    {"price_adjustment_method": "vendor_adjusted"},
                    "QUOTE_PRICE_ADJUSTMENT_METHOD_INVALID",
                ),
                (
                    "convention",
                    {"price_adjustment_convention": "qfq"},
                    "QUOTE_PRICE_ADJUSTMENT_CONVENTION_INVALID",
                ),
                (
                    "formula",
                    {"adjustment_factor": "2"},
                    "QUOTE_PRICE_ADJUSTMENT_FORMULA_MISMATCH",
                ),
            ):
                with self.subTest(label=label):
                    changed_root = root / label
                    changed_root.mkdir()
                    changed_quotes, changed_master, changed_fundamentals, changed_calendar = (
                        _write_panel(changed_root, missing_publish_date=False)
                    )
                    _rewrite_csv_rows(changed_quotes, ((0, update),))
                    blocked = audit_study_inputs(
                        quotes_path=changed_quotes,
                        stock_master_path=changed_master,
                        fundamentals_path=changed_fundamentals,
                        official_calendar_path=changed_calendar,
                    )
                    self.assertFalse(
                        blocked["gates"]["price_adjustment_contract_met"]
                    )
                    self.assertIn(reason, blocked["gates"]["blocking_reason_codes"])

    def test_required_non_null_fields_fail_closed_with_aggregate_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            _rewrite_csv_rows(
                quotes,
                ((0, {"date": ""}), (1, {"symbol": ""})),
            )
            _rewrite_csv_rows(
                master,
                (
                    (0, {"symbol": "", "listDate": ""}),
                    (1, {"listStatus": "", "stockType": ""}),
                ),
            )
            _rewrite_csv_rows(
                fundamentals,
                (
                    (0, {"symbol": ""}),
                    (1, {"roeDiluted": ""}),
                    (2, {"reportPeriodEnd": ""}),
                ),
            )
            _rewrite_csv_rows(calendar, ((0, {"date": ""}),))

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertEqual(report["quotes"]["blank_value_counts"]["date"], 1)
            self.assertEqual(report["quotes"]["blank_value_counts"]["symbol"], 1)
            for field in ("symbol", "listDate", "listStatus", "stockType"):
                self.assertEqual(
                    report["stock_master"]["blank_value_counts"][field], 1
                )
            for field in ("symbol", "roeDiluted", "reportPeriodEnd"):
                self.assertEqual(
                    report["fundamentals"]["blank_value_counts"][field], 1
                )
            self.assertEqual(
                report["official_calendar"]["blank_value_counts"]["date"], 1
            )
            self.assertFalse(
                report["gates"]["required_field_non_null_integrity_met"]
            )
            self.assertFalse(report["gates"]["ready_to_lock_stage2_plan"])
            for reason in (
                "QUOTE_DATE_BLANK",
                "QUOTE_SYMBOL_BLANK",
                "STOCK_MASTER_SYMBOL_BLANK",
                "STOCK_MASTER_LIST_DATE_BLANK",
                "STOCK_MASTER_LIST_STATUS_BLANK",
                "STOCK_MASTER_STOCK_TYPE_BLANK",
                "FUNDAMENTAL_SYMBOL_BLANK",
                "FUNDAMENTAL_ROE_DILUTED_BLANK",
                "FUNDAMENTAL_REPORT_PERIOD_END_BLANK",
                "OFFICIAL_CALENDAR_DATE_BLANK",
            ):
                self.assertIn(reason, report["gates"]["blocking_reason_codes"])

    def test_publish_date_remains_thresholded_not_an_all_row_non_null_gate(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=True
            )

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertGreater(
                report["fundamentals"]["blank_value_counts"]["publishDate"], 0
            )
            self.assertTrue(
                report["gates"]["required_field_non_null_integrity_met"]
            )

    def test_malformed_csv_row_widths_block_every_input_role(self) -> None:
        roles = (
            "quotes",
            "stock_master",
            "fundamentals",
            "official_calendar",
        )
        for role in roles:
            with self.subTest(role=role), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                quotes, master, fundamentals, calendar = _write_panel(
                    root, missing_publish_date=False
                )
                paths = {
                    "quotes": quotes,
                    "stock_master": master,
                    "fundamentals": fundamentals,
                    "official_calendar": calendar,
                }
                _malform_csv_row_width(paths[role], mode="extra")

                report = audit_study_inputs(
                    quotes_path=quotes,
                    stock_master_path=master,
                    fundamentals_path=fundamentals,
                    official_calendar_path=calendar,
                )

                section = report[role]
                self.assertEqual(section["malformed_csv_row_width_count"], 1)
                self.assertEqual(section["extra_field_row_count"], 1)
                self.assertEqual(section["missing_field_row_count"], 0)
                self.assertGreater(section["malformed_csv_row_width_rate"], 0)
                self.assertFalse(section["structural_integrity_verified"])
                self.assertFalse(report["gates"]["csv_row_width_integrity_met"])
                self.assertFalse(report["gates"]["input_structural_integrity_met"])
                self.assertFalse(report["gates"]["ready_to_lock_stage2_plan"])
                reason_label = {
                    "quotes": "QUOTES",
                    "stock_master": "STOCK_MASTER",
                    "fundamentals": "FUNDAMENTALS",
                    "official_calendar": "OFFICIAL_CALENDAR",
                }[role]
                self.assertIn(
                    f"MALFORMED_{reason_label}_CSV_ROW_WIDTH",
                    report["gates"]["blocking_reason_codes"],
                )
                self.assertNotIn("unexpected-extra-field", json.dumps(report))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            _malform_csv_row_width(quotes, mode="missing")
            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )
            self.assertEqual(report["quotes"]["malformed_csv_row_width_count"], 1)
            self.assertEqual(report["quotes"]["extra_field_row_count"], 0)
            self.assertEqual(report["quotes"]["missing_field_row_count"], 1)
            self.assertIn(
                "MALFORMED_QUOTES_CSV_ROW_WIDTH",
                report["gates"]["blocking_reason_codes"],
            )

    def test_normalized_logical_duplicate_keys_block_every_input_role(self) -> None:
        cases = (
            ("quotes", ("symbol", "date")),
            ("stock_master", ("symbol",)),
            ("fundamentals", ("symbol", "reportPeriodEnd")),
            ("official_calendar", ("date",)),
        )
        for role, key_columns in cases:
            with self.subTest(role=role), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                quotes, master, fundamentals, calendar = _write_panel(
                    root, missing_publish_date=False
                )
                if role == "quotes":
                    _append_quote(
                        quotes, "2015-01-05", " 000001.sz "
                    )
                elif role == "stock_master":
                    _append_master_row(
                        master,
                        symbol=" 000001.sz ",
                        list_date="1991-04-03",
                        delist_date="",
                        list_status="listed",
                        stock_type="A股",
                    )
                elif role == "fundamentals":
                    _append_fundamental(
                        fundamentals,
                        symbol=" 000001.sz ",
                        roe="0.20",
                        publish_date="2015-05-01",
                        report_period_end="2014-12-31",
                    )
                else:
                    _append_calendar_date(calendar, "2009-01-05")

                report = audit_study_inputs(
                    quotes_path=quotes,
                    stock_master_path=master,
                    fundamentals_path=fundamentals,
                    official_calendar_path=calendar,
                )

                section = report[role]
                self.assertEqual(section["duplicate_logical_key_row_count"], 1)
                self.assertGreater(section["duplicate_logical_key_row_rate"], 0)
                self.assertEqual(section["logical_key_columns"], list(key_columns))
                self.assertFalse(section["structural_integrity_verified"])
                self.assertFalse(report["gates"]["logical_key_uniqueness_met"])
                self.assertFalse(report["gates"]["input_structural_integrity_met"])
                self.assertFalse(report["gates"]["ready_to_lock_stage2_plan"])
                reason_label = {
                    "quotes": "QUOTES",
                    "stock_master": "STOCK_MASTER",
                    "fundamentals": "FUNDAMENTALS",
                    "official_calendar": "OFFICIAL_CALENDAR",
                }[role]
                self.assertIn(
                    f"DUPLICATE_{reason_label}_LOGICAL_KEY",
                    report["gates"]["blocking_reason_codes"],
                )
                self.assertIn(
                    "enforced here",
                    report["scope"]["duplicate_key_validation"],
                )

    def test_exact_logical_key_tracker_spills_and_cleans_temporary_storage(self) -> None:
        tracker = coverage._ExactLogicalKeyTracker(max_in_memory_keys=2)
        with tracker:
            self.assertFalse(tracker.add(("ab", "c")))
            self.assertEqual(tracker.storage_backend, "memory")
            self.assertFalse(tracker.add(("a", "bc")))
            self.assertEqual(tracker.storage_backend, "sqlite_spill")
            self.assertFalse(tracker.add(("含", "Unicode")))
            self.assertTrue(tracker.add(("ab", "c")))
            self.assertIsNotNone(tracker._temporary_directory)
            spill_directory = Path(tracker._temporary_directory.name)
            self.assertTrue(spill_directory.is_dir())
        self.assertFalse(spill_directory.exists())

    def test_logical_key_spill_failure_does_not_disclose_temporary_path(self) -> None:
        private_detail = "/private/person-account/provider-keys.sqlite3"
        with mock.patch.object(
            coverage.sqlite3,
            "connect",
            side_effect=coverage.sqlite3.OperationalError(private_detail),
        ):
            tracker = coverage._ExactLogicalKeyTracker(max_in_memory_keys=1)
            with self.assertRaises(StudyV2CoverageError) as raised:
                with tracker:
                    tracker.add(("000001.SZ", "2010-01-04"))
        self.assertEqual(
            str(raised.exception), "temporary exact logical-key index failed"
        )
        self.assertNotIn(private_detail, str(raised.exception))

    def test_forced_logical_key_spill_matches_in_memory_scan_exactly(self) -> None:
        payload = (
            "date,symbol,close,close_observation_type,amount,amount_unit,is_st,is_suspended\n"
            "2010-01-04,000001.SZ,10,traded_close,100,CNY,false,false\n"
            "2010-01-05,000002.SZ,11,traded_close,110,CNY,false,false\n"
            "2010-01-06,000003.SZ,12,traded_close,120,CNY,true,false\n"
            "2010-01-04, 000001.sz ,13,suspension_valuation,130,CNY,false,true\n"
            "2010-01-04,000001.SZ,14,traded_close,140,CNY,false,false\n"
        ).encode("utf-8")
        scan_arguments = {
            "source_name": "quotes.csv",
            "required": coverage.QUOTE_REQUIRED,
            "date_columns": ("date",),
            "non_null_columns": (
                "date",
                "symbol",
                "close",
                "close_observation_type",
                "amount",
                "amount_unit",
                "is_st",
                "is_suspended",
            ),
            "logical_key_columns": ("symbol", "date"),
            "monthly_date_column": "date",
        }
        with mock.patch.object(
            coverage, "LOGICAL_KEY_IN_MEMORY_LIMIT", 1000
        ):
            memory_scan = coverage._scan_csv(payload, **scan_arguments)
        with mock.patch.object(coverage, "LOGICAL_KEY_IN_MEMORY_LIMIT", 2):
            spill_scan = coverage._scan_csv(payload, **scan_arguments)

        self.assertEqual(spill_scan, memory_scan)
        self.assertEqual(spill_scan["duplicate_logical_key_row_count"], 2)

    def test_streaming_csv_scan_rejects_invalid_utf8_without_echoing_bytes(self) -> None:
        payload = b"date,symbol\n2010-01-04,000001.SZ\n\xff"
        with self.assertRaisesRegex(StudyV2CoverageError, "not valid UTF-8"):
            coverage._scan_csv(
                payload,
                source_name="quotes.csv",
                required=("date", "symbol"),
                date_columns=("date",),
                non_null_columns=("date", "symbol"),
                logical_key_columns=("symbol", "date"),
            )

    def test_noncanonical_dates_cannot_reach_the_ready_runner_boundary(self) -> None:
        cases = (
            (
                "quotes",
                "date",
                0,
                "2015-01-05T00:00:00",
                "QUOTE_DATE_INVALID_CANONICAL_DATE",
            ),
            (
                "stock_master",
                "listDate",
                0,
                "1991-04-03T00:00:00",
                "STOCK_MASTER_LIST_DATE_INVALID_CANONICAL_DATE",
            ),
            (
                "stock_master",
                "delistDate",
                1,
                "2023-12-29junk",
                "STOCK_MASTER_DELIST_DATE_INVALID_CANONICAL_DATE",
            ),
            (
                "fundamentals",
                "publishDate",
                0,
                "2015-04-30T00:00:00",
                "FUNDAMENTAL_PUBLISH_DATE_INVALID_CANONICAL_DATE",
            ),
            (
                "fundamentals",
                "reportPeriodEnd",
                0,
                "2014-12-31junk",
                "FUNDAMENTAL_REPORT_PERIOD_END_INVALID_CANONICAL_DATE",
            ),
            (
                "official_calendar",
                "date",
                0,
                "2020-01-01junk",
                "OFFICIAL_CALENDAR_DATE_INVALID_CANONICAL_DATE",
            ),
            (
                "quotes",
                "date",
                0,
                "2263-01-05",
                "QUOTE_DATE_INVALID_CANONICAL_DATE",
            ),
            (
                "stock_master",
                "listDate",
                0,
                "1677-09-21",
                "STOCK_MASTER_LIST_DATE_INVALID_CANONICAL_DATE",
            ),
            (
                "fundamentals",
                "reportPeriodEnd",
                0,
                "0001-01-01",
                "FUNDAMENTAL_REPORT_PERIOD_END_INVALID_CANONICAL_DATE",
            ),
            (
                "official_calendar",
                "date",
                0,
                "9999-12-31",
                "OFFICIAL_CALENDAR_DATE_INVALID_CANONICAL_DATE",
            ),
        )
        for role, field, row_index, value, reason in cases:
            with self.subTest(role=role, field=field), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                quotes, master, fundamentals, calendar = _write_panel(
                    root, missing_publish_date=False
                )
                paths = {
                    "quotes": quotes,
                    "stock_master": master,
                    "fundamentals": fundamentals,
                    "official_calendar": calendar,
                }
                _rewrite_csv_rows(paths[role], ((row_index, {field: value}),))

                report = audit_study_inputs(
                    quotes_path=quotes,
                    stock_master_path=master,
                    fundamentals_path=fundamentals,
                    official_calendar_path=calendar,
                )

                self.assertEqual(
                    report[role]["invalid_date_format_counts"][field], 1
                )
                self.assertFalse(
                    report["gates"]["canonical_date_format_integrity_met"]
                )
                self.assertFalse(report["gates"]["ready_to_lock_stage2_plan"])
                self.assertIn(reason, report["gates"]["blocking_reason_codes"])
                self.assertNotIn(value, json.dumps(report))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=True
            )
            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )
            self.assertEqual(
                report["stock_master"]["invalid_date_format_counts"]["delistDate"],
                0,
            )
            self.assertEqual(
                report["fundamentals"]["invalid_date_format_counts"]["publishDate"],
                0,
            )
            self.assertTrue(
                report["gates"]["canonical_date_format_integrity_met"]
            )

    def test_canonical_symbol_gate_rejects_na_mixed_case_and_bad_suffixes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            _rewrite_csv_rows(
                quotes,
                (
                    (0, {"symbol": "NA"}),
                    (1, {"symbol": "600000.sh"}),
                    (2, {"symbol": "000001.BJ"}),
                ),
            )
            _rewrite_csv_rows(
                master,
                ((0, {"symbol": "NULL"}), (1, {"symbol": "600000.sz"})),
            )
            _rewrite_csv_rows(
                fundamentals,
                (
                    (0, {"symbol": "NA"}),
                    (1, {"symbol": "600000.sh"}),
                    (2, {"symbol": "000001.BJ"}),
                ),
            )

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertEqual(report["quotes"]["symbol_na_like_row_count"], 1)
            self.assertEqual(
                report["quotes"]["symbol_invalid_canonical_format_row_count"],
                2,
            )
            self.assertEqual(
                report["stock_master"]["symbol_na_like_row_count"], 1
            )
            self.assertEqual(
                report["stock_master"][
                    "symbol_invalid_canonical_format_row_count"
                ],
                1,
            )
            self.assertEqual(
                report["fundamentals"]["symbol_na_like_row_count"], 1
            )
            self.assertEqual(
                report["fundamentals"][
                    "symbol_invalid_canonical_format_row_count"
                ],
                2,
            )
            self.assertFalse(report["gates"]["canonical_symbol_integrity_met"])
            self.assertFalse(
                report["gates"]["required_field_non_null_integrity_met"]
            )
            self.assertFalse(report["gates"]["ready_to_lock_stage2_plan"])
            for reason in (
                "QUOTE_SYMBOL_NA_LIKE",
                "QUOTE_SYMBOL_INVALID_CANONICAL_FORMAT",
                "STOCK_MASTER_SYMBOL_NA_LIKE",
                "STOCK_MASTER_SYMBOL_INVALID_CANONICAL_FORMAT",
                "FUNDAMENTAL_SYMBOL_NA_LIKE",
                "FUNDAMENTAL_SYMBOL_INVALID_CANONICAL_FORMAT",
            ):
                self.assertIn(reason, report["gates"]["blocking_reason_codes"])
            serialized = json.dumps(report)
            for raw_value in ("NULL", "600000.sh", "600000.sz", "000001.BJ"):
                self.assertNotIn(raw_value, serialized)

    def test_stock_master_required_enums_reject_na_like_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            _rewrite_csv_rows(
                master,
                ((0, {"listStatus": "NA"}), (1, {"stockType": "NULL"})),
            )

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertEqual(
                report["stock_master"]["na_like_value_counts"]["listStatus"],
                1,
            )
            self.assertEqual(
                report["stock_master"]["na_like_value_counts"]["stockType"],
                1,
            )
            self.assertFalse(
                report["gates"]["required_field_non_null_integrity_met"]
            )
            self.assertIn(
                "STOCK_MASTER_LIST_STATUS_NA_LIKE",
                report["gates"]["blocking_reason_codes"],
            )
            self.assertIn(
                "STOCK_MASTER_STOCK_TYPE_NA_LIKE",
                report["gates"]["blocking_reason_codes"],
            )

    def test_canonical_numeric_grammar_rejects_python_underscores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            _rewrite_csv_rows(quotes, ((0, {"close": "1_000"}),))
            _rewrite_csv_rows(fundamentals, ((0, {"roeDiluted": "1_000"}),))

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertEqual(
                report["quotes"][
                    "close_invalid_canonical_numeric_format_row_count"
                ],
                1,
            )
            self.assertEqual(
                report["fundamentals"][
                    "invalid_roe_diluted_numeric_format_row_count"
                ],
                1,
            )
            self.assertFalse(report["gates"]["quote_numeric_integrity_met"])
            self.assertFalse(
                report["gates"]["fundamental_roe_numeric_integrity_met"]
            )
            self.assertFalse(report["gates"]["ready_to_lock_stage2_plan"])
            self.assertIn(
                "QUOTE_CLOSE_INVALID_CANONICAL_NUMERIC_FORMAT",
                report["gates"]["blocking_reason_codes"],
            )
            self.assertIn(
                "FUNDAMENTAL_ROE_DILUTED_INVALID_CANONICAL_NUMERIC_FORMAT",
                report["gates"]["blocking_reason_codes"],
            )
            self.assertNotIn("1_000", json.dumps(report))

    def test_official_calendar_requires_strictly_increasing_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            _reverse_calendar_rows(calendar)

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertIn("strictly_increasing", report["official_calendar"])
            self.assertFalse(report["official_calendar"]["strictly_increasing"])
            self.assertFalse(report["gates"]["official_calendar_integrity_verified"])
            self.assertIn(
                "INVALID_OFFICIAL_CALENDAR",
                report["gates"]["blocking_reason_codes"],
            )

    def test_official_calendar_rejects_additional_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            _add_calendar_source_column(calendar)

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertIn("additional_columns", report["official_calendar"])
            self.assertEqual(report["official_calendar"]["additional_columns"], ["source"])
            self.assertFalse(report["gates"]["official_calendar_integrity_verified"])

    def test_monthly_symbol_gate_uses_strict_a_share_master_quote_intersection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            _append_quote(quotes, "2020-01-06", "900001.SH")
            _append_quote(quotes, "2020-01-06", "430001.BJ")
            _append_quote(quotes, "2020-01-06", "600001.sh")
            _append_quote(quotes, "2020-01-06", "000003.SZ")
            _append_quote(quotes, "2020-01-06", "000004.SZ")
            _append_master(master, "900001.SH", "指数")
            _append_master(master, "430001.BJ", "A股")
            _append_master(master, "600001.sh", "A股")
            _append_master(master, "000004.SZ", "A股")

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            january = _month_row(report["quotes"], "2020-01")
            self.assertIn("eligible_symbol_count", january)
            self.assertEqual(january["symbol_count"], 7)
            self.assertEqual(january["eligible_symbol_count"], 2)
            self.assertEqual(report["gates"]["eligible_a_share_symbol_count"], 3)
            self.assertFalse(report["gates"]["minimum_symbols_per_month_met"])

    def test_monthly_coverage_uses_active_lifecycle_with_inclusive_delist_date(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            lifecycle_rows = (
                ("000010.SZ", "2020-01-03", "", "listed"),
                ("600010.SH", "2000-01-01", "2020-01-01", "delisted"),
                ("600011.SH", "2000-01-01", "2020-01-02", "delisted"),
            )
            for symbol, list_date, delist_date, list_status in lifecycle_rows:
                _append_master_row(
                    master,
                    symbol=symbol,
                    list_date=list_date,
                    delist_date=delist_date,
                    list_status=list_status,
                    stock_type="A股",
                )
                _append_quote(quotes, "2020-01-02", symbol)
                _append_fundamental(
                    fundamentals,
                    symbol=symbol,
                    roe="0.20",
                    publish_date="2019-10-31",
                    report_period_end="2019-09-30",
                )
            for symbol in ("000010.SZ", "600010.SH"):
                _append_fundamental(
                    fundamentals,
                    symbol=symbol,
                    roe="0.21",
                    publish_date="2018-12-30",
                    report_period_end="2018-12-31",
                )

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            quote_january = _month_row(report["quotes"], "2020-01")
            fundamental_january = _month_row(report["fundamentals"], "2020-01")
            self.assertEqual(
                quote_january["active_strict_a_share_symbol_count"], 3
            )
            self.assertEqual(quote_january["eligible_symbol_count"], 3)
            self.assertEqual(
                fundamental_january["eligible_quote_symbol_count"], 3
            )
            self.assertEqual(
                fundamental_january["available_fundamental_symbol_count"], 3
            )
            self.assertEqual(
                fundamental_january["nonstale_fundamental_symbol_count"], 1
            )
            self.assertEqual(
                report["fundamentals"]["invalid_publication_order_row_count"], 0
            )

    def test_publication_before_report_period_end_blocks_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            _append_fundamental(
                fundamentals,
                symbol="000001.SZ",
                roe="0.20",
                publish_date="2019-12-30",
                report_period_end="2019-12-31",
            )

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertEqual(
                report["fundamentals"]["invalid_publication_order_row_count"], 1
            )
            self.assertFalse(
                report["gates"]["fundamental_publication_order_integrity_met"]
            )
            self.assertFalse(report["gates"]["ready_to_lock_stage2_plan"])
            self.assertIn(
                "FUNDAMENTAL_PUBLICATION_BEFORE_REPORT_PERIOD_END",
                report["gates"]["blocking_reason_codes"],
            )

    def test_global_publication_order_gate_catches_unscoped_and_outside_rows(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            _append_fundamental(
                fundamentals,
                symbol="300999.SZ",
                roe="0.18",
                publish_date="2019-01-01",
                report_period_end="2019-12-31",
            )
            _append_fundamental(
                fundamentals,
                symbol="000001.SZ",
                roe="0.19",
                publish_date="2023-01-01",
                report_period_end="2023-12-31",
            )

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertEqual(
                report["fundamentals"][
                    "eligible_scope_publication_before_report_period_end_row_count"
                ],
                0,
            )
            self.assertEqual(
                report["fundamentals"][
                    "global_publication_before_report_period_end_row_count"
                ],
                2,
            )
            self.assertTrue(
                report["gates"]["fundamental_publication_order_integrity_met"]
            )
            self.assertFalse(
                report["gates"][
                    "global_fundamental_publication_order_integrity_met"
                ]
            )
            self.assertFalse(report["gates"]["ready_to_lock_stage2_plan"])
            self.assertIn(
                "GLOBAL_FUNDAMENTAL_PUBLICATION_BEFORE_REPORT_PERIOD_END",
                report["gates"]["blocking_reason_codes"],
            )
            self.assertNotIn("300999.SZ", json.dumps(report))

    def test_fundamental_monthly_gate_filters_eligibility_and_staleness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            _append_fundamental(
                fundamentals,
                symbol="000001.SZ",
                roe="0.11",
                publish_date="2019-10-31",
                report_period_end="2019-09-30",
            )
            _append_fundamental(
                fundamentals,
                symbol="000099.SZ",
                roe="0.12",
                publish_date="2019-10-31",
                report_period_end="2019-09-30",
            )

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertIn("monthly_coverage", report["fundamentals"])
            january = _month_row(report["fundamentals"], "2020-01")
            self.assertEqual(january["eligible_quote_symbol_count"], 2)
            self.assertEqual(january["available_fundamental_symbol_count"], 2)
            self.assertEqual(january["nonstale_fundamental_symbol_count"], 1)
            self.assertEqual(january["stale_fundamental_symbol_count"], 1)
            self.assertFalse(report["gates"]["fundamental_target_month_continuity_met"])
            self.assertFalse(report["gates"]["fundamental_staleness_coverage_met"])
            self.assertFalse(report["gates"]["target_fundamental_interval_available"])

    def test_fundamental_coverage_counts_only_finite_numeric_roe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            _rewrite_fundamental_roe(fundamentals, "600000.SH", "NaN")
            _append_fundamental(
                fundamentals,
                symbol="000001.SZ",
                roe="0.11",
                publish_date="2019-10-31",
                report_period_end="2019-09-30",
            )
            _append_fundamental(
                fundamentals,
                symbol="600000.SH",
                roe="not-a-number",
                publish_date="2019-10-31",
                report_period_end="2019-09-30",
            )

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertEqual(
                report["fundamentals"]["roe_diluted_finite_numeric_rate"],
                0.5,
            )
            self.assertEqual(
                report["fundamentals"][
                    "invalid_roe_diluted_numeric_row_count"
                ],
                4,
            )
            serialized = json.dumps(report)
            self.assertNotIn("not-a-number", serialized)
            self.assertNotIn('"NaN"', serialized)
            january = _month_row(report["fundamentals"], "2020-01")
            self.assertEqual(january["available_fundamental_symbol_count"], 1)
            self.assertEqual(january["nonstale_fundamental_symbol_count"], 1)
            self.assertFalse(
                report["gates"]["fundamental_roe_numeric_integrity_met"]
            )
            self.assertFalse(
                report["gates"]["target_fundamental_interval_available"]
            )
            self.assertFalse(report["gates"]["ready_to_lock_stage2_plan"])
            self.assertIn(
                "FUNDAMENTAL_ROE_DILUTED_NON_NUMERIC_OR_NON_FINITE",
                report["gates"]["blocking_reason_codes"],
            )

    def test_same_day_publication_is_unavailable_to_the_signal_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            for symbol in ("000001.SZ", "600000.SH"):
                _append_fundamental(
                    fundamentals,
                    symbol=symbol,
                    roe="0.20",
                    publish_date="2020-01-02",
                    report_period_end="2019-12-31",
                )

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            january = _month_row(report["fundamentals"], "2020-01")
            self.assertEqual(january["rebalance_date"], "2020-01-02")
            self.assertEqual(january["nonstale_fundamental_symbol_count"], 0)
            self.assertIn(
                "publishDate strictly before that session",
                report["gates"]["fundamental_interval_basis"],
            )

    def test_staleness_cutoff_uses_exact_calendar_date_offset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            for symbol in ("000001.SZ", "600000.SH"):
                _append_fundamental(
                    fundamentals,
                    symbol=symbol,
                    roe="0.20",
                    publish_date="2018-08-01",
                    report_period_end="2018-07-01",
                )

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            january = _month_row(report["fundamentals"], "2020-01")
            self.assertEqual(january["rebalance_date"], "2020-01-02")
            self.assertEqual(january["available_fundamental_symbol_count"], 2)
            self.assertEqual(january["nonstale_fundamental_symbol_count"], 0)
            self.assertEqual(january["stale_fundamental_symbol_count"], 2)

    def test_ic_core_quote_contract_does_not_require_open_or_volume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            _drop_quote_columns(quotes, {"open", "volume"})

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertTrue(report["quotes"]["required_columns_present"])
            self.assertEqual(report["quotes"]["missing_required_columns"], [])
            self.assertTrue(report["gates"]["execution_columns_present"])

    def test_vintage_columns_cannot_enable_revision_claim_without_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, master, fundamentals, calendar = _write_panel(
                root, missing_publish_date=False
            )
            _add_unvalidated_vintage_columns(fundamentals)

            report = audit_study_inputs(
                quotes_path=quotes,
                stock_master_path=master,
                fundamentals_path=fundamentals,
                official_calendar_path=calendar,
            )

            self.assertIn("revision_vintage_fields_observed", report["fundamentals"])
            self.assertTrue(report["fundamentals"]["revision_vintage_fields_observed"])
            self.assertFalse(
                report["fundamentals"]["complete_revision_vintage_fields_present"]
            )
            self.assertFalse(report["gates"]["complete_revision_vintage_available"])
            self.assertFalse(report["gates"]["revision_history_claim_allowed"])


def _write_panel(
    root: Path, *, missing_publish_date: bool
) -> tuple[Path, Path, Path, Path]:
    quotes = root / "quotes.csv"
    with quotes.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "date", "symbol", "open", "close_raw", "adjustment_factor",
                "close", "price_adjustment_method", "price_adjustment_convention",
                "close_observation_type", "volume", "amount", "amount_unit",
                "is_st", "is_suspended"
            ),
        )
        writer.writeheader()
        for day in ("2015-01-05", "2020-01-02", "2025-01-06"):
            for index, symbol in enumerate(("000001.SZ", "600000.SH")):
                writer.writerow(
                    {
                        "date": day,
                        "symbol": symbol,
                        "open": 10 + index,
                        "close_raw": 10.2 + index,
                        "adjustment_factor": 1,
                        "close": 10.2 + index,
                        "price_adjustment_method": (
                            "close_equals_close_raw_times_adjustment_factor"
                        ),
                        "price_adjustment_convention": (
                            "provider_cumulative_backward_adjusted_hfq_no_rebasing"
                        ),
                        "volume": 1_000_000,
                        "amount": 10_000_000,
                        "amount_unit": "CNY",
                        "is_st": "True" if day == "2020-01-02" and index == 1 else "False",
                        "is_suspended": (
                            "True" if day == "2020-01-02" and index == 1 else "False"
                        ),
                        "close_observation_type": (
                            "suspension_valuation"
                            if day == "2020-01-02" and index == 1
                            else "traded_close"
                        ),
                    }
                )

    master = root / "stock_master.csv"
    with master.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("symbol", "listDate", "delistDate", "listStatus", "stockType"),
        )
        writer.writeheader()
        writer.writerow(
            {"symbol": "000001.SZ", "listDate": "1991-04-03", "delistDate": "", "listStatus": "listed", "stockType": "A股"}
        )
        writer.writerow(
            {"symbol": "600000.SH", "listDate": "1999-11-10", "delistDate": "2023-12-29", "listStatus": "delisted", "stockType": "A股"}
        )

    fundamentals = root / "fundamentals.csv"
    with fundamentals.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("symbol", "roeDiluted", "publishDate", "reportPeriodEnd"),
        )
        writer.writeheader()
        for index, year in enumerate((2014, 2019, 2024)):
            for symbol in ("000001.SZ", "600000.SH"):
                writer.writerow(
                    {
                        "symbol": symbol,
                        "roeDiluted": 0.08 + index * 0.01,
                        "publishDate": "" if missing_publish_date and index == 0 else f"{year + 1}-04-30",
                        "reportPeriodEnd": f"{year}-12-31",
                    }
                )
    calendar = root / "official_calendar.csv"
    with calendar.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("date",))
        writer.writeheader()
        for day in (
            "2009-01-05",
            "2015-01-05",
            "2020-01-02",
            "2020-01-03",
            "2020-01-06",
            "2020-01-07",
            "2020-01-08",
            "2020-01-09",
            "2020-01-10",
            "2020-01-13",
            "2020-01-14",
            "2020-01-15",
            "2020-01-16",
            "2020-01-17",
            "2020-01-20",
            "2020-01-21",
            "2020-01-22",
            "2023-01-31",
            "2025-01-06",
        ):
            writer.writerow({"date": day})
    return quotes, master, fundamentals, calendar


def _contract_calendar(
    rebalance: date, *, lag_exit: date | None = None
) -> tuple[date, ...]:
    history = tuple(
        rebalance - timedelta(days=offset) for offset in range(60, 0, -1)
    )
    forward = tuple(rebalance + timedelta(days=offset) for offset in range(1, 21))
    final_session = lag_exit or rebalance + timedelta(days=21)
    return (*history, rebalance, *forward, final_session)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _review_attestation(
    quotes: Path, master: Path, fundamentals: Path, calendar: Path
) -> dict[str, object]:
    report = coverage.recompute_coverage_report(
        quotes_csv=quotes.read_bytes(),
        stock_master_csv=master.read_bytes(),
        fundamentals_csv=fundamentals.read_bytes(),
        official_calendar_csv=calendar.read_bytes(),
    )
    files = report["inputs"]["files"]
    return {
        "schema_version": "stage2_data_review_attestation_v1",
        "study_id": "a-share-factor-timing-bias-decomposition-v2",
        "status": "reviewed_pass",
        "review_scope_cutoff_at": "2026-09-01T08:55:00+08:00",
        "coverage_probe_spec_path": "coverage_probe_spec.v2.json",
        "coverage_probe_spec_sha256": "6" * 64,
        "coverage_probe_receipt_path": "coverage_probe_receipt.v2.json",
        "coverage_probe_receipt_sha256": "8" * 64,
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
        "reviewed_at": "2026-09-01T09:00:00+08:00",
        "reviewer": "fixture-reviewer",
        "reviewer_role": "fixture methods reviewer",
        "reviewer_authority_basis": "Fixture data-contract custodian.",
        "input_file_sha256": {
            role: files[role]["sha256"]
            for role in ("quotes", "stock_master", "fundamentals", "official_calendar")
        },
        "input_identity": {
            "quotes": {
                "byte_size": files["quotes"]["size_bytes"],
                "row_count": report["quotes"]["row_count"],
                "minimum_date": report["quotes"]["market_start"],
                "maximum_date": report["quotes"]["market_end"],
            },
            "stock_master": {
                "byte_size": files["stock_master"]["size_bytes"],
                "row_count": report["stock_master"]["row_count"],
                "symbol_count": report["stock_master"]["symbol_count"],
            },
            "fundamentals": {
                "byte_size": files["fundamentals"]["size_bytes"],
                "row_count": report["fundamentals"]["row_count"],
                "minimum_publish_date": report["fundamentals"]["publication_start"],
                "maximum_publish_date": report["fundamentals"]["publication_end"],
            },
            "official_calendar": {
                "byte_size": files["official_calendar"]["size_bytes"],
                "row_count": report["official_calendar"]["row_count"],
                "minimum_date": report["official_calendar"]["calendar_start"],
                "maximum_date": report["official_calendar"]["calendar_end"],
                "source_name": "Shanghai and Shenzhen Stock Exchange official calendar",
                "source_reference": "https://example.test/official-calendar",
                "source_generated_at": "2026-08-31T07:00:00+08:00",
                "timezone": "Asia/Shanghai",
            },
        },
        "evidence_sha256": {
            "execution_semantics": "1" * 64,
            "tradability_fields": "2" * 64,
            "exact_endpoint_resolution": "6" * 64,
            "suspension_valuation_semantics": "b" * 64,
            "provider_close_raw_definition": "c" * 64,
            "provider_adjustment_factor_convention": "d" * 64,
            "price_adjustment_normalization": "e" * 64,
            "amount_unit_normalization": "c" * 64,
            "endpoint_reason_ledger_rights": "7" * 64,
            "historical_membership_completeness": "9" * 64,
            "terminal_survivor_comparator": "8" * 64,
            "security_identifier_semantics": "7" * 64,
            "code_change_mapping": "6" * 64,
            "fundamental_publication_semantics": "a" * 64,
            "data_rights": "3" * 64,
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


def _input_names(
    quotes: Path, master: Path, fundamentals: Path, calendar: Path
) -> dict[str, str]:
    return {
        "quotes": quotes.name,
        "stock_master": master.name,
        "fundamentals": fundamentals.name,
        "official_calendar": calendar.name,
    }


def _month_row(section: object, month: str) -> dict[str, object]:
    assert isinstance(section, dict)
    rows = section["monthly_coverage"]
    assert isinstance(rows, list)
    return next(row for row in rows if row["month"] == month)


def _remove_calendar_date(path: Path, removed: str) -> None:
    with path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("date",))
        writer.writeheader()
        writer.writerows(row for row in rows if row["date"] != removed)


def _reverse_calendar_rows(path: Path) -> None:
    with path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("date",))
        writer.writeheader()
        writer.writerows(reversed(rows))


def _add_calendar_source_column(path: Path) -> None:
    with path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("date", "source"))
        writer.writeheader()
        writer.writerows({"date": row["date"], "source": "fixture"} for row in rows)


def _append_quote(path: Path, day: str, symbol: str) -> None:
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "date", "symbol", "open", "close_raw", "adjustment_factor",
                "close", "price_adjustment_method", "price_adjustment_convention",
                "close_observation_type", "volume", "amount", "amount_unit",
                "is_st", "is_suspended",
            ),
        )
        writer.writerow(
            {
                "date": day,
                "symbol": symbol,
                "open": 10,
                "close_raw": 10.1,
                "adjustment_factor": 1,
                "close": 10.1,
                "price_adjustment_method": (
                    "close_equals_close_raw_times_adjustment_factor"
                ),
                "price_adjustment_convention": (
                    "provider_cumulative_backward_adjusted_hfq_no_rebasing"
                ),
                "close_observation_type": "traded_close",
                "volume": 1_000_000,
                "amount": 10_000_000,
                "amount_unit": "CNY",
                "is_st": "False",
                "is_suspended": "False",
            }
        )


def _drop_quote_columns(path: Path, removed: set[str]) -> None:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = [name for name in (reader.fieldnames or []) if name not in removed]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(
            {name: row[name] for name in fieldnames}
            for row in rows
        )


def _rewrite_quote_numeric_values(
    path: Path, updates: tuple[dict[str, str], ...]
) -> None:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or ())
    for row, update in zip(rows, updates):
        row.update(update)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _rewrite_quote_boolean_values(
    path: Path,
    *,
    is_st: tuple[str, ...],
    is_suspended: tuple[str, ...],
) -> None:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or ())
    if len(is_st) != len(rows) or len(is_suspended) != len(rows):
        raise AssertionError("boolean fixture values must cover every quote row")
    for row, st_value, suspended_value in zip(rows, is_st, is_suspended):
        row["is_st"] = st_value
        row["is_suspended"] = suspended_value
        normalized = suspended_value.strip().lower()
        row["close_observation_type"] = (
            "suspension_valuation"
            if normalized in {"true", "1", "yes"}
            else "traded_close"
        )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _rewrite_csv_rows(
    path: Path, updates: tuple[tuple[int, dict[str, str]], ...]
) -> None:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or ())
    for index, update in updates:
        rows[index].update(update)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _malform_csv_row_width(path: Path, *, mode: str) -> None:
    with path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    if mode == "extra":
        rows[1].append("unexpected-extra-field")
    elif mode == "missing":
        rows[1].pop()
    else:
        raise AssertionError(f"unsupported malformed-row mode: {mode}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


def _append_calendar_date(path: Path, value: str) -> None:
    with path.open("a", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=("date",)).writerow({"date": value})


def _append_master(path: Path, symbol: str, stock_type: str) -> None:
    _append_master_row(
        path,
        symbol=symbol,
        list_date="2000-01-01",
        delist_date="",
        list_status="listed",
        stock_type=stock_type,
    )


def _append_master_row(
    path: Path,
    *,
    symbol: str,
    list_date: str,
    delist_date: str,
    list_status: str,
    stock_type: str,
) -> None:
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("symbol", "listDate", "delistDate", "listStatus", "stockType"),
        )
        writer.writerow(
            {
                "symbol": symbol,
                "listDate": list_date,
                "delistDate": delist_date,
                "listStatus": list_status,
                "stockType": stock_type,
            }
        )


def _rewrite_master_row(path: Path, symbol: str, **updates: str) -> None:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or ())
    for row in rows:
        if row["symbol"] == symbol:
            row.update(updates)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _append_fundamental(
    path: Path,
    *,
    symbol: str,
    roe: str,
    publish_date: str,
    report_period_end: str,
) -> None:
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("symbol", "roeDiluted", "publishDate", "reportPeriodEnd"),
        )
        writer.writerow(
            {
                "symbol": symbol,
                "roeDiluted": roe,
                "publishDate": publish_date,
                "reportPeriodEnd": report_period_end,
            }
        )


def _rewrite_fundamental_roe(path: Path, symbol: str, value: str) -> None:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or ())
    for row in rows:
        if row["symbol"] == symbol:
            row["roeDiluted"] = value
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _add_unvalidated_vintage_columns(path: Path) -> None:
    with path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    versioned_rows = []
    for row in rows:
        versioned_rows.append(
            {
                **row,
                "as_of_date": row["publishDate"] or "2020-01-01",
                "version_id": "v1",
            }
        )
    versioned_rows.append({**versioned_rows[0], "version_id": "v2"})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "symbol", "roeDiluted", "publishDate", "reportPeriodEnd", "as_of_date",
                "version_id",
            ),
        )
        writer.writeheader()
        writer.writerows(versioned_rows)


def _force_all_gates_true(report: dict[str, object]) -> None:
    gates = report["gates"]
    assert isinstance(gates, dict)
    for key, value in tuple(gates.items()):
        if isinstance(value, bool):
            gates[key] = True
    gates["blocking_reason_codes"] = []


if __name__ == "__main__":
    unittest.main()
