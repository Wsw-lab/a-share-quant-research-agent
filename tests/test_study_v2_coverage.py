from __future__ import annotations

import csv
from contextlib import redirect_stdout
from copy import deepcopy
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
                review_attestation={
                    "schema_version": "stage2_data_review_attestation_v1",
                    "study_id": "a-share-factor-timing-bias-decomposition-v2",
                    "status": "reviewed_pass",
                    "review_scope_cutoff_at": "2026-09-01T08:55:00+08:00",
                    "execution_semantics_verified": True,
                    "tradability_fields_verified": True,
                    "data_rights_verified": True,
                    "official_calendar_verified": True,
                    "reviewed_at": "2026-09-01T09:00:00+08:00",
                    "reviewer": "fixture-reviewer",
                    "reviewer_role": "fixture methods reviewer",
                    "reviewer_authority_basis": "Fixture data-contract custodian.",
                    "input_file_sha256": {
                        "quotes": _sha256(quotes),
                        "stock_master": _sha256(master),
                        "fundamentals": _sha256(fundamentals),
                        "official_calendar": _sha256(calendar),
                    },
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
                            "Identity and evidence authenticity require independent "
                            "human verification."
                        ),
                    },
                },
            )
            self.assertTrue(attested["gates"]["execution_semantics_verified"])
            self.assertTrue(attested["gates"]["tradability_fields_verified"])
            self.assertTrue(attested["gates"]["data_rights_verified"])
            self.assertFalse(attested["gates"]["ready_to_lock_stage2_plan"])

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

    def test_official_sessions_drive_month_counts_not_sparse_quote_dates(self) -> None:
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

            calendar_january = _month_row(report["official_calendar"], "2020-01")
            quotes_january = _month_row(report["quotes"], "2020-01")
            self.assertEqual(calendar_january["session_count"], 15)
            self.assertEqual(quotes_january["session_count"], 1)
            self.assertEqual(report["gates"]["full_month_count"], 1)
            self.assertTrue(
                report["gates"]["target_official_calendar_interval_available"]
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("symbol", "listDate", "delistDate", "listStatus", "stockType"),
        )
        writer.writerow(
            {
                "symbol": symbol,
                "listDate": "2000-01-01",
                "delistDate": "",
                "listStatus": "listed",
                "stockType": stock_type,
            }
        )


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
