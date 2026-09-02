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
import tempfile
import unittest

import a_share_quant_agent.study_v2_coverage as coverage
from a_share_quant_agent.study_v2_coverage import (
    StudyV2CoverageError,
    audit_study_inputs,
)


class StudyV2CoverageAuditTest(unittest.TestCase):
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

            self.assertEqual(status, 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["official_calendar"]["sha256"], _sha256(calendar))

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
                    "date_values": "ISO-8601_calendar_date_from_first_10_characters",
                    "encoding": "utf-8-sig",
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
                "date", "symbol", "open", "close", "volume", "amount", "is_st", "is_suspended"
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
                        "close": 10.2 + index,
                        "volume": 1_000_000,
                        "amount": 10_000_000,
                        "is_st": "False",
                        "is_suspended": "False",
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
        "endpoint_reason_ledger_rights_verified": True,
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
            "endpoint_reason_ledger_rights": "7" * 64,
            "data_rights": "3" * 64,
            "official_calendar": "4" * 64,
        },
        "review_assertions": {
            "adjusted_close_return_semantics_and_corporate_action_handling_are_documented": True,
            "unadjusted_open_and_nonfill_semantics_are_not_claimed_by_the_ic_core": True,
            "amount_units_and_cutoff_timing_are_documented": True,
            "st_and_suspension_fields_are_non_degenerate_and_historically_effective": True,
            "signal_eligible_denominator_is_fixed_before_outcome_lookup": True,
            "current_ic_core_resolves_only_exact_adjusted_close_quotes_on_required_official_sessions": True,
            "unresolved_endpoints_cannot_be_dropped_shifted_carried_forward_or_assigned_default_recovery": True,
            "suspension_valuation_and_delisting_terminal_wealth_adapters_are_not_claimed_by_the_current_ic_core": True,
            "private_endpoint_reason_ledger_hash_and_public_aggregate_counts_are_permitted": True,
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
                "date", "symbol", "open", "close", "volume", "amount", "is_st",
                "is_suspended",
            ),
        )
        writer.writerow(
            {
                "date": day,
                "symbol": symbol,
                "open": 10,
                "close": 10.1,
                "volume": 1_000_000,
                "amount": 10_000_000,
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
