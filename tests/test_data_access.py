from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

import pandas as pd

import a_share_quant_agent.data_access as data_access
import a_share_quant_agent.study_v2_coverage as study_v2_coverage
from a_share_quant_agent.data_access import (
    DataAccessError,
    STAGE2_DATASET_ROLES,
    STAGE2_PRICE_ADJUSTMENT_CONVENTION,
    STAGE2_PRICE_ADJUSTMENT_METHOD,
    STAGE2_REQUIRED_FIELDS,
    assess_provider_capability,
    audit_stage2_field_contract,
    normalize_tushare_daily_frame,
    normalize_tushare_disclosure_frame,
    normalize_tushare_stock_master_frame,
    normalize_tushare_st_frame,
    normalize_tushare_suspend_frame,
    normalize_tushare_trade_calendar_frame,
    provider_capability_matrix,
    stage2_public_source_projection_sha256,
    summarize_csv_metadata,
    validate_rights_attestation,
    validate_stage2_dataset_source_mappings,
)


ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "studies" / "pit_factor_bias_decomposition_v2"


def _valid_rights_packet() -> dict[str, object]:
    datasets = {
        role: {
            "source_reference": "contract:test-123",
            "license_or_contract_scope": "private research and aggregate reporting",
            "terms_evidence_sha256": "a" * 64,
            "local_storage_permitted": True,
            "local_analysis_permitted": True,
            "aggregate_publication_permitted": True,
            "raw_redistribution_permitted": False,
            "hash_publication_permitted": True,
            "controlled_reviewer_rerun_permitted": True,
            "source_identity_publication_permitted": True,
            "field_mapping_citation_permitted": True,
            "authorized_public_projection": (
                projection := {
                    "dataset_role": role,
                    "source_name": f"licensed test source: {role}",
                    "field_mapping": {
                        field: f"provider_{role}_{field}"
                        for field in STAGE2_REQUIRED_FIELDS[role]
                    },
                }
            ),
            "authorized_public_projection_sha256": (
                stage2_public_source_projection_sha256(projection)
            ),
            "restrictions": [],
            "conditional_permission_reviews": [],
            **(
                {"calendar_dates_publication_permitted": True}
                if role == "official_calendar"
                else {}
            ),
        }
        for role in STAGE2_DATASET_ROLES
    }
    return {
        "schema_version": "stage2_data_rights_attestation_v2",
        "study_id": "a-share-factor-timing-bias-decomposition-v2",
        "status": "attested",
        "attested_at": "2026-09-02T12:00:00+08:00",
        "attestor": "Test reviewer",
        "attestor_role": "authorized data custodian",
        "contract_reference": "contract:test-123",
        "contract_effective_at": "2026-01-01T00:00:00+08:00",
        "contract_expiry_at": "2027-01-01T00:00:00+08:00",
        "contract_has_no_expiry_confirmed": False,
        "post_expiry_research_publication_and_controlled_review_rights_survive": True,
        "post_expiry_survival_evidence_sha256": "9" * 64,
        "contract_evidence_sha256": "c" * 64,
        "datasets": datasets,
        "private_endpoint_reason_ledger": {
            "retention_permitted": True,
            "hash_binding_permitted": True,
            "row_redistribution_permitted": False,
            "terms_evidence_sha256": "b" * 64,
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
                "kind": "terms",
                "reference": "contract:test-123",
                "sha256": "a" * 64,
            }
        ],
        "signature": {
            "type": "human_verified_evidence",
            "evidence_sha256": "d" * 64,
            "signer_identity": "Test reviewer",
            "verification_uri": "https://example.invalid/review/123",
            "trust_boundary": (
                "A human reviewer must verify the contract and the exact permitted "
                "outputs."
            ),
        },
    }


def _valid_data_declaration_source_mappings() -> dict[str, object]:
    rights = _valid_rights_packet()
    return {
        "dataset_source_mappings": {
            "schema_version": "stage2_public_dataset_source_mappings_v1",
            "datasets": {
                role: json.loads(
                    json.dumps(
                        rights["datasets"][role]["authorized_public_projection"]
                    )
                )
                for role in STAGE2_DATASET_ROLES
            },
        }
    }


class DataAccessContractTest(unittest.TestCase):
    def test_cli_private_output_is_required_any_git_safe_atomic_and_no_overwrite(self) -> None:
        base_arguments = [
            "--quotes", "unused-quotes.csv",
            "--stock-master", "unused-master.csv",
            "--fundamentals", "unused-fundamentals.csv",
            "--official-calendar", "unused-calendar.csv",
        ]
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            data_access._cli(base_arguments)
        self.assertEqual(stdout.getvalue(), "")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
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
                    "user.name=Data Access Fixture",
                    "-c",
                    "user.email=data-access-fixture@example.test",
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

            sensitive_name = "private-provider-contract-7821.json"
            for worktree in (repository, linked):
                target = worktree / "ignored" / sensitive_name
                with self.subTest(worktree=worktree), self.assertRaisesRegex(
                    DataAccessError,
                    "must be outside every Git worktree",
                ) as raised:
                    data_access._cli(base_arguments + ["--output", str(target)])
                self.assertNotIn(sensitive_name, str(raised.exception))
                self.assertFalse(target.exists())

            result = {
                "status": "blocked",
                "input_file_sha256": {"quotes": "a" * 64},
                "byte_size": 123,
            }
            external = root / "private-evidence" / "data-access.json"
            stdout = io.StringIO()
            with mock.patch.object(
                data_access,
                "summarize_csv_metadata",
                return_value={"fixture": True},
            ), mock.patch.object(
                data_access,
                "audit_stage2_field_contract",
                return_value=result,
            ), redirect_stdout(stdout):
                code = data_access._cli(
                    base_arguments + ["--output", str(external)]
                )
            self.assertEqual(code, 0)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(stat.S_IMODE(external.stat().st_mode), 0o600)
            self.assertEqual(json.loads(external.read_text(encoding="utf-8")), result)

            existing = root / "private-evidence" / "existing.json"
            sentinel = b"do not overwrite\n"
            existing.write_bytes(sentinel)
            with self.assertRaisesRegex(DataAccessError, "already exists"):
                data_access._cli(base_arguments + ["--output", str(existing)])
            self.assertEqual(existing.read_bytes(), sentinel)

    def test_capability_matrix_is_conservative_and_json_safe(self) -> None:
        matrix = provider_capability_matrix()
        self.assertGreaterEqual(len(matrix), 6)
        self.assertTrue(any(row["provider_id"] == "tushare_pro" for row in matrix))
        akshare = next(row for row in matrix if row["provider_id"] == "akshare")
        self.assertEqual(akshare["status"], "probe_only")
        self.assertNotIn("report_publication_date", akshare["datasets"])
        for provider_id in (
            "csmar_institutional",
            "resset_institutional",
            "wind_institutional",
            "choice_institutional",
        ):
            provider = next(row for row in matrix if row["provider_id"] == provider_id)
            self.assertEqual(
                provider["status"],
                "institutional_candidate_not_verified_capability_or_entitlement",
            )
            self.assertTrue(provider["references"])
            self.assertTrue(any("contract" in item.lower() for item in provider["limitations"]))
        json.dumps(matrix)

    def test_runtime_and_study_capability_matrix_provider_ids_stay_in_sync(self) -> None:
        study_matrix = json.loads(
            (STUDY / "source_capability_matrix.json").read_text(encoding="utf-8")
        )
        runtime_ids = [row["provider_id"] for row in provider_capability_matrix()]
        study_ids = [row["provider_id"] for row in study_matrix["providers"]]
        self.assertEqual(len(runtime_ids), len(set(runtime_ids)))
        self.assertEqual(len(study_ids), len(set(study_ids)))
        self.assertEqual(set(runtime_ids), set(study_ids))
        runtime_by_id = {
            row["provider_id"]: row for row in provider_capability_matrix()
        }
        study_by_id = {
            row["provider_id"]: row for row in study_matrix["providers"]
        }
        for provider_id in runtime_ids:
            self.assertEqual(
                set(runtime_by_id[provider_id]["references"]),
                set(study_by_id[provider_id]["references"]),
                f"reference drift for {provider_id}",
            )
        for provider_id in (
            "csmar_institutional",
            "resset_institutional",
            "wind_institutional",
            "choice_institutional",
        ):
            study_provider = study_by_id[provider_id]
            self.assertEqual(
                study_provider["role"],
                "institutional_candidate_subject_to_exact_entitlement_field_mapping_coverage_and_rights",
            )
            self.assertTrue(study_provider["references"])
            self.assertTrue(study_provider["known_constraints"])

    def test_public_provider_materials_do_not_encode_private_outreach_priority(self) -> None:
        public_paths = (
            STUDY / "data_acquisition_plan.md",
            STUDY / "provider_outreach_dispatch_checklist.md",
            STUDY / "source_capability_matrix.json",
        )
        public_text = "\n".join(
            path.read_text(encoding="utf-8") for path in public_paths
        ).lower()
        for forbidden in (
            "csmar first",
            "resset in parallel",
            "parallel_backup_outreach_candidate",
            "contingency_only_if_csmar",
            "not_selected_for_primary_stage2",
            "not_selected_this_round",
        ):
            self.assertNotIn(forbidden, public_text)
        boundary = (STUDY / "provider_information_boundary.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("## Public repository", boundary)
        self.assertIn("## Private, outside every Git worktree", boundary)
        self.assertIn("## Never public", boundary)

    def test_study_quote_target_contract_matches_runtime_and_suspension_semantics(self) -> None:
        study_matrix = json.loads(
            (STUDY / "source_capability_matrix.json").read_text(encoding="utf-8")
        )
        quote_contract = study_matrix["target_contract"]["quotes"]
        self.assertEqual(
            set(quote_contract["required_fields"]),
            set(STAGE2_REQUIRED_FIELDS["quotes"]),
        )
        semantics = " ".join(quote_contract["semantic_requirements"]).lower()
        self.assertIn("traded_close", semantics)
        self.assertIn("suspension_valuation", semantics)
        self.assertTrue(
            "forward-fill" in semantics or "carry-forward" in semantics,
            semantics,
        )

    def test_assess_provider_does_not_grant_rights(self) -> None:
        result = assess_provider_capability(
            "tushare_pro",
            ("daily_bar_raw", "report_publication_date", "unknown_dataset"),
        )
        self.assertEqual(result["missing_datasets"], ["unknown_dataset"])
        self.assertTrue(result["rights_review_required"])
        self.assertFalse(result["authorization_granted"])

    def test_metadata_scan_is_outcome_blind_and_counts_field_informativeness(self) -> None:
        payload = (
            "date,symbol,close_raw,adjustment_factor,close,price_adjustment_method,price_adjustment_convention,close_observation_type,amount,amount_unit,is_st,is_suspended\n"
            "2010-01-04,600000.SH,10,1,10,close_equals_close_raw_times_adjustment_factor,provider_cumulative_backward_adjusted_hfq_no_rebasing,traded_close,100,CNY,true,false\n"
            "2010-01-05,600000.SH,11,1,11,close_equals_close_raw_times_adjustment_factor,provider_cumulative_backward_adjusted_hfq_no_rebasing,suspension_valuation,120,CNY,false,true\n"
        ).encode()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quotes.csv"
            path.write_bytes(payload)
            metadata = summarize_csv_metadata(path, "quotes")
        self.assertEqual(metadata["row_count"], 2)
        self.assertEqual(metadata["symbol_count"], 1)
        self.assertEqual(metadata["distinct_values"]["is_st"], ["false", "true"])
        self.assertEqual(metadata["distinct_values"]["is_suspended"], ["false", "true"])
        self.assertEqual(
            metadata["distinct_values"]["close_observation_type"],
            ["suspension_valuation", "traded_close"],
        )
        self.assertEqual(metadata["invalid_close_observation_type_count"], 0)
        self.assertEqual(metadata["close_observation_suspension_mismatch_count"], 0)
        self.assertEqual(metadata["date_ranges"]["date"], ["2010-01-04", "2010-01-05"])
        self.assertEqual(
            metadata["numeric_value_issue_counts"],
            {
                "close_raw_non_numeric_count": 0,
                "close_raw_non_finite_count": 0,
                "close_raw_non_positive_count": 0,
                "adjustment_factor_non_numeric_count": 0,
                "adjustment_factor_non_finite_count": 0,
                "adjustment_factor_non_positive_count": 0,
                "close_non_numeric_count": 0,
                "close_non_finite_count": 0,
                "close_non_positive_count": 0,
                "amount_non_numeric_count": 0,
                "amount_non_finite_count": 0,
                "amount_negative_count": 0,
            },
        )
        self.assertNotIn("close", metadata["distinct_values"])

    def test_quote_amount_unit_requires_exact_cny(self) -> None:
        payload = (
            "date,symbol,close_raw,adjustment_factor,close,price_adjustment_method,price_adjustment_convention,close_observation_type,amount,amount_unit,is_st,is_suspended\n"
            "2010-01-04,600000.SH,10,1,10,close_equals_close_raw_times_adjustment_factor,provider_cumulative_backward_adjusted_hfq_no_rebasing,traded_close,100,thousand_CNY,false,false\n"
        ).encode()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quotes.csv"
            path.write_bytes(payload)
            metadata = summarize_csv_metadata(path, "quotes")
        self.assertEqual(metadata["invalid_amount_unit_count"], 1)
        audit = audit_stage2_field_contract(
            {role: metadata for role in STAGE2_DATASET_ROLES}
        )
        self.assertIn("QUOTE_AMOUNT_UNIT_NOT_EXACT_CNY", audit["issues"])

    def test_quote_close_observation_mapping_fails_closed(self) -> None:
        payload = (
            "date,symbol,close_raw,adjustment_factor,close,price_adjustment_method,price_adjustment_convention,close_observation_type,amount,amount_unit,is_st,is_suspended\n"
            "2010-01-04,600000.SH,10,1,10,close_equals_close_raw_times_adjustment_factor,provider_cumulative_backward_adjusted_hfq_no_rebasing,suspension_valuation,100,CNY,false,false\n"
            "2010-01-05,600000.SH,11,1,11,close_equals_close_raw_times_adjustment_factor,provider_cumulative_backward_adjusted_hfq_no_rebasing, researcher_fill ,120,CNY,false,true\n"
        ).encode()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quotes.csv"
            path.write_bytes(payload)
            metadata = summarize_csv_metadata(path, "quotes")

        self.assertEqual(metadata["invalid_close_observation_type_count"], 1)
        self.assertEqual(
            metadata["close_observation_suspension_mismatch_count"], 1
        )
        audit = audit_stage2_field_contract(
            {role: metadata for role in STAGE2_DATASET_ROLES}
        )
        self.assertIn("INVALID_CLOSE_OBSERVATION_TYPE", audit["issues"])
        self.assertIn("CLOSE_OBSERVATION_SUSPENSION_MISMATCH", audit["issues"])
        self.assertNotIn("researcher_fill", json.dumps(metadata))

    def test_quote_price_adjustment_contract_is_machine_checked(self) -> None:
        header = (
            "date,symbol,close_raw,adjustment_factor,close,price_adjustment_method,"
            "price_adjustment_convention,close_observation_type,amount,amount_unit,"
            "is_st,is_suspended\n"
        )
        valid_row = (
            "2010-01-04,600000.SH,10,1.2,12,"
            f"{STAGE2_PRICE_ADJUSTMENT_METHOD},"
            f"{STAGE2_PRICE_ADJUSTMENT_CONVENTION},traded_close,100,CNY,false,false\n"
        )
        cases = (
            (
                "blank raw close",
                valid_row.replace(",10,1.2,12,", ",,1.2,12,"),
                "NULL_REQUIRED_FIELD:quotes:close_raw",
            ),
            (
                "blank factor",
                valid_row.replace(",10,1.2,12,", ",10,,12,"),
                "NULL_REQUIRED_FIELD:quotes:adjustment_factor",
            ),
            (
                "blank method",
                valid_row.replace(f",{STAGE2_PRICE_ADJUSTMENT_METHOD},", ",,"),
                "NULL_REQUIRED_FIELD:quotes:price_adjustment_method",
            ),
            (
                "blank convention",
                valid_row.replace(
                    f",{STAGE2_PRICE_ADJUSTMENT_CONVENTION},", ",,"
                ),
                "NULL_REQUIRED_FIELD:quotes:price_adjustment_convention",
            ),
            (
                "wrong method",
                valid_row.replace(STAGE2_PRICE_ADJUSTMENT_METHOD, "vendor_adjusted"),
                "QUOTE_PRICE_ADJUSTMENT_METHOD_INVALID",
            ),
            (
                "wrong convention",
                valid_row.replace(STAGE2_PRICE_ADJUSTMENT_CONVENTION, "qfq"),
                "QUOTE_PRICE_ADJUSTMENT_CONVENTION_INVALID",
            ),
            (
                "formula mismatch",
                valid_row.replace(",1.2,12,", ",1.2,11,"),
                "QUOTE_PRICE_ADJUSTMENT_FORMULA_MISMATCH",
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quotes.csv"
            path.write_text(header + valid_row, encoding="utf-8")
            valid = summarize_csv_metadata(path, "quotes")
            self.assertEqual(valid["invalid_price_adjustment_method_count"], 0)
            self.assertEqual(valid["invalid_price_adjustment_convention_count"], 0)
            self.assertEqual(valid["price_adjustment_formula_mismatch_count"], 0)
            for label, row, issue in cases:
                with self.subTest(label=label):
                    path.write_text(header + row, encoding="utf-8")
                    metadata = summarize_csv_metadata(path, "quotes")
                    audit = audit_stage2_field_contract(
                        {role: metadata for role in STAGE2_DATASET_ROLES}
                    )
                    self.assertIn(issue, audit["issues"])

    def test_quote_numeric_quality_is_aggregate_only_and_fail_closed(self) -> None:
        payload = (
            "date,symbol,close_raw,adjustment_factor,close,price_adjustment_method,price_adjustment_convention,close_observation_type,amount,amount_unit,is_st,is_suspended\n"
            "2010-01-04,600000.SH,10,1,10,close_equals_close_raw_times_adjustment_factor,provider_cumulative_backward_adjusted_hfq_no_rebasing,traded_close,100,CNY,false,false\n"
            "2010-01-05,600000.SH,10,1,not-a-number,close_equals_close_raw_times_adjustment_factor,provider_cumulative_backward_adjusted_hfq_no_rebasing,traded_close,100,CNY,false,false\n"
            "2010-01-06,600000.SH,10,1,NaN,close_equals_close_raw_times_adjustment_factor,provider_cumulative_backward_adjusted_hfq_no_rebasing,traded_close,100,CNY,false,false\n"
            "2010-01-07,600000.SH,10,1,0,close_equals_close_raw_times_adjustment_factor,provider_cumulative_backward_adjusted_hfq_no_rebasing,traded_close,100,CNY,false,false\n"
            "2010-01-08,600000.SH,10,1,10,close_equals_close_raw_times_adjustment_factor,provider_cumulative_backward_adjusted_hfq_no_rebasing,traded_close,not-a-number,CNY,false,false\n"
            "2010-01-11,600000.SH,10,1,10,close_equals_close_raw_times_adjustment_factor,provider_cumulative_backward_adjusted_hfq_no_rebasing,traded_close,inf,CNY,false,false\n"
            "2010-01-12,600000.SH,10,1,10,close_equals_close_raw_times_adjustment_factor,provider_cumulative_backward_adjusted_hfq_no_rebasing,traded_close,-1,CNY,false,false\n"
        ).encode()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quotes.csv"
            path.write_bytes(payload)
            metadata = summarize_csv_metadata(path, "quotes")

        self.assertEqual(
            metadata["numeric_value_issue_counts"],
            {
                "close_raw_non_numeric_count": 0,
                "close_raw_non_finite_count": 0,
                "close_raw_non_positive_count": 0,
                "adjustment_factor_non_numeric_count": 0,
                "adjustment_factor_non_finite_count": 0,
                "adjustment_factor_non_positive_count": 0,
                "close_non_numeric_count": 1,
                "close_non_finite_count": 1,
                "close_non_positive_count": 1,
                "amount_non_numeric_count": 1,
                "amount_non_finite_count": 1,
                "amount_negative_count": 1,
            },
        )
        self.assertNotIn("not-a-number", json.dumps(metadata))
        audit = audit_stage2_field_contract(
            {role: metadata for role in STAGE2_DATASET_ROLES}
        )
        self.assertEqual(audit["status"], "blocked")
        for issue in (
            "QUOTE_CLOSE_NON_NUMERIC",
            "QUOTE_CLOSE_NON_FINITE",
            "QUOTE_CLOSE_NON_POSITIVE",
            "QUOTE_AMOUNT_NON_NUMERIC",
            "QUOTE_AMOUNT_NON_FINITE",
            "QUOTE_AMOUNT_NEGATIVE",
        ):
            self.assertIn(issue, audit["issues"])

        metadata["numeric_value_issue_counts"].pop("close_non_numeric_count")
        missing_count_audit = audit_stage2_field_contract(
            {role: metadata for role in STAGE2_DATASET_ROLES}
        )
        self.assertIn(
            "INVALID_QUOTE_NUMERIC_COUNT:close_non_numeric_count",
            missing_count_audit["issues"],
        )

    def test_fundamental_roe_numeric_quality_is_aggregate_and_fail_closed(self) -> None:
        payload = (
            "symbol,roeDiluted,publishDate,reportPeriodEnd\n"
            "600000.SH,0.10,2010-04-30,2009-12-31\n"
            "600000.SH,not-a-number,2011-04-30,2010-12-31\n"
            "600000.SH,NaN,2012-04-30,2011-12-31\n"
        ).encode()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fundamentals.csv"
            path.write_bytes(payload)
            metadata = summarize_csv_metadata(path, "fundamentals")

        self.assertEqual(
            metadata["numeric_value_issue_counts"],
            {
                "roeDiluted_non_numeric_count": 1,
                "roeDiluted_non_finite_count": 1,
            },
        )
        serialized = json.dumps(metadata)
        self.assertNotIn("not-a-number", serialized)
        self.assertNotIn('"NaN"', serialized)
        audit = audit_stage2_field_contract(
            {role: metadata for role in STAGE2_DATASET_ROLES}
        )
        self.assertIn("FUNDAMENTAL_ROE_DILUTED_NON_NUMERIC", audit["issues"])
        self.assertIn("FUNDAMENTAL_ROE_DILUTED_NON_FINITE", audit["issues"])

        metadata["numeric_value_issue_counts"].pop(
            "roeDiluted_non_numeric_count"
        )
        missing_count_audit = audit_stage2_field_contract(
            {role: metadata for role in STAGE2_DATASET_ROLES}
        )
        self.assertIn(
            "INVALID_FUNDAMENTAL_NUMERIC_COUNT:roeDiluted_non_numeric_count",
            missing_count_audit["issues"],
        )

    def test_publish_date_accepts_95_percent_but_other_fields_require_100(self) -> None:
        non_null_rates = {
            field: 1.0
            for field in {
                "date", "symbol", "close", "close_observation_type", "amount",
                "amount_unit", "is_st", "is_suspended",
                "listDate", "listStatus", "stockType", "roeDiluted", "publishDate",
                "reportPeriodEnd",
            }
        }
        common = {
            "row_count": 100,
            "missing_required_columns": [],
            "duplicate_key_count": 0,
            "invalid_date_count": 0,
            "malformed_row_count": 0,
            "date_order_violation_count": 0,
            "date_ranges": {"date": ["2009-01-01", "2023-01-31"]},
        }
        metadata = {
            role: {**common, "non_null_rates": dict(non_null_rates)}
            for role in STAGE2_DATASET_ROLES
        }
        metadata["quotes"].update(
            {
                "distinct_values": {
                    "is_st": ["false", "true"],
                    "is_suspended": ["false", "true"],
                    "close_observation_type": [
                        "suspension_valuation", "traded_close"
                    ],
                },
                "invalid_boolean_value_count": {
                    "is_st": 0,
                    "is_suspended": 0,
                },
                "invalid_close_observation_type_count": 0,
                "close_observation_suspension_mismatch_count": 0,
                "invalid_amount_unit_count": 0,
                "numeric_value_issue_counts": {
                    "close_non_numeric_count": 0,
                    "close_non_finite_count": 0,
                    "close_non_positive_count": 0,
                    "amount_non_numeric_count": 0,
                    "amount_non_finite_count": 0,
                    "amount_negative_count": 0,
                },
            }
        )
        metadata["fundamentals"].update(
            {
                "date_ranges": {
                    "publishDate": ["2009-01-01", "2022-12-31"],
                    "reportPeriodEnd": ["2009-01-01", "2022-12-31"],
                },
                "publication_before_report_count": 0,
                "invalid_date_value_counts": {
                    "publishDate": 0,
                    "reportPeriodEnd": 0,
                },
                "numeric_value_issue_counts": {
                    "roeDiluted_non_numeric_count": 0,
                    "roeDiluted_non_finite_count": 0,
                },
            }
        )
        metadata["stock_master"].update(
            {
                "delisted_row_count": 1,
                "delisted_missing_date_count": 0,
                "active_with_delist_count": 0,
                "delist_before_list_count": 0,
                "invalid_delist_date_count": 0,
                "unknown_list_status_count": 0,
                "unknown_stock_type_count": 0,
                "exchange_values": ["SH", "SZ"],
            }
        )

        metadata["fundamentals"]["non_null_rates"]["publishDate"] = 0.95
        at_threshold = audit_stage2_field_contract(metadata)
        self.assertNotIn(
            "NULL_REQUIRED_FIELD:fundamentals:publishDate",
            at_threshold["issues"],
        )

        metadata["fundamentals"]["non_null_rates"]["publishDate"] = 0.949999
        below_threshold = audit_stage2_field_contract(metadata)
        self.assertIn(
            "NULL_REQUIRED_FIELD:fundamentals:publishDate",
            below_threshold["issues"],
        )

        metadata["fundamentals"]["non_null_rates"]["publishDate"] = 0.95
        metadata["fundamentals"]["non_null_rates"]["roeDiluted"] = 0.999999
        other_required_field_missing = audit_stage2_field_contract(metadata)
        self.assertIn(
            "NULL_REQUIRED_FIELD:fundamentals:roeDiluted",
            other_required_field_missing["issues"],
        )

    def test_metadata_range_gate_accepts_sessions_within_boundary_months_and_first_report(self) -> None:
        payloads = {
            "quotes": (
                "date,symbol,close_raw,adjustment_factor,close,price_adjustment_method,price_adjustment_convention,close_observation_type,amount,amount_unit,is_st,is_suspended\n"
                "2009-01-05,600000.SH,10,1,10,close_equals_close_raw_times_adjustment_factor,provider_cumulative_backward_adjusted_hfq_no_rebasing,traded_close,100,CNY,false,false\n"
                "2023-01-30,000001.SZ,11,1,11,close_equals_close_raw_times_adjustment_factor,provider_cumulative_backward_adjusted_hfq_no_rebasing,suspension_valuation,120,CNY,true,true\n"
            ),
            "stock_master": (
                "symbol,listDate,delistDate,listStatus,stockType\n"
                "600000.SH,1999-11-10,,L,A\n"
                "000001.SZ,1991-04-03,2012-12-31,D,A\n"
            ),
            "fundamentals": (
                "symbol,roeDiluted,publishDate,reportPeriodEnd\n"
                "600000.SH,0.10,2009-04-30,2009-03-31\n"
                "000001.SZ,0.11,2022-10-31,2022-09-30\n"
            ),
            "official_calendar": "date\n2009-01-05\n2023-01-30\n",
        }
        with tempfile.TemporaryDirectory() as directory:
            metadata = {}
            for role, payload in payloads.items():
                path = Path(directory) / f"{role}.csv"
                path.write_text(payload, encoding="utf-8")
                metadata[role] = summarize_csv_metadata(path, role)

        audit = audit_stage2_field_contract(metadata)
        for issue in (
            "QUOTE_WARMUP_NOT_COVERED",
            "QUOTE_ENDPOINT_NOT_COVERED",
            "CALENDAR_START_NOT_COVERED",
            "CALENDAR_END_NOT_COVERED",
            "FUNDAMENTAL_PUBLICATION_HISTORY_NOT_COVERED",
            "FUNDAMENTAL_REPORT_HISTORY_NOT_COVERED",
            "FUNDAMENTAL_REPORT_INTERVAL_NOT_COVERED",
        ):
            self.assertNotIn(issue, audit["issues"])
        self.assertFalse(audit["authorization_granted"])

    def test_invalid_publish_dates_are_not_coverage_and_block_even_at_four_percent(self) -> None:
        rows = ["symbol,roeDiluted,publishDate,reportPeriodEnd"]
        for index in range(100):
            publish_date = "bad-publish-date" if index < 4 else "2010-04-30"
            rows.append(
                f"{index:06d}.SZ,0.10,{publish_date},2009-12-31"
            )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fundamentals.csv"
            path.write_text("\n".join(rows) + "\n", encoding="utf-8")
            metadata = summarize_csv_metadata(path, "fundamentals")

        self.assertEqual(metadata["non_null_rates"]["publishDate"], 0.96)
        self.assertEqual(
            metadata["invalid_date_value_counts"],
            {"publishDate": 4, "reportPeriodEnd": 0},
        )
        self.assertEqual(metadata["invalid_date_count"], 4)
        self.assertNotIn("bad-publish-date", json.dumps(metadata))
        audit = audit_stage2_field_contract(
            {role: metadata for role in STAGE2_DATASET_ROLES}
        )
        self.assertEqual(audit["status"], "blocked")
        self.assertIn("FUNDAMENTAL_PUBLISH_DATE_INVALID", audit["issues"])

        metadata["invalid_date_value_counts"].pop("publishDate")
        missing_count_audit = audit_stage2_field_contract(
            {role: metadata for role in STAGE2_DATASET_ROLES}
        )
        self.assertIn(
            "INVALID_FUNDAMENTAL_DATE_COUNT:publishDate",
            missing_count_audit["issues"],
        )

    def test_invalid_report_period_end_is_counted_and_blocked_separately(self) -> None:
        payload = (
            "symbol,roeDiluted,publishDate,reportPeriodEnd\n"
            "600000.SH,0.10,2010-04-30,bad-report-date\n"
            "000001.SZ,0.11,2011-04-30,2010-12-31\n"
        ).encode()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fundamentals.csv"
            path.write_bytes(payload)
            metadata = summarize_csv_metadata(path, "fundamentals")

        self.assertEqual(metadata["non_null_rates"]["reportPeriodEnd"], 0.5)
        self.assertEqual(
            metadata["invalid_date_value_counts"],
            {"publishDate": 0, "reportPeriodEnd": 1},
        )
        self.assertEqual(metadata["invalid_date_count"], 1)
        self.assertNotIn("bad-report-date", json.dumps(metadata))
        audit = audit_stage2_field_contract(
            {role: metadata for role in STAGE2_DATASET_ROLES}
        )
        self.assertIn(
            "FUNDAMENTAL_REPORT_PERIOD_END_INVALID", audit["issues"]
        )

    def test_metadata_scan_counts_duplicate_keys_without_dropping_rows(self) -> None:
        payload = (
            "date,symbol,close_raw,adjustment_factor,close,price_adjustment_method,price_adjustment_convention,close_observation_type,amount,amount_unit,is_st,is_suspended\n"
            "2010-01-04,600000.SH,10,1,10,close_equals_close_raw_times_adjustment_factor,provider_cumulative_backward_adjusted_hfq_no_rebasing,traded_close,100,CNY,false,false\n"
            "2010-01-04,600000.SH,10,1,10,close_equals_close_raw_times_adjustment_factor,provider_cumulative_backward_adjusted_hfq_no_rebasing,traded_close,100,CNY,false,false\n"
        ).encode()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quotes.csv"
            path.write_bytes(payload)
            metadata = summarize_csv_metadata(path, "quotes")
        self.assertEqual(metadata["row_count"], 2)
        self.assertEqual(metadata["duplicate_key_count"], 1)

    def test_metadata_scan_normalizes_date_keys_and_rejects_malformed_rows_at_audit(self) -> None:
        payload = (
            "date,symbol,close_raw,adjustment_factor,close,price_adjustment_method,price_adjustment_convention,close_observation_type,amount,amount_unit,is_st,is_suspended\n"
            "20100104,600000.SH,10,1,10,close_equals_close_raw_times_adjustment_factor,provider_cumulative_backward_adjusted_hfq_no_rebasing,traded_close,100,CNY,false,false\n"
            "2010-01-04,600000.SH,10,1,10,close_equals_close_raw_times_adjustment_factor,provider_cumulative_backward_adjusted_hfq_no_rebasing,traded_close,100,CNY,false,false\n"
            "2010-01-05,600001.SZ,10,1,10,close_equals_close_raw_times_adjustment_factor,provider_cumulative_backward_adjusted_hfq_no_rebasing,traded_close,100,CNY,false,false,EXTRA\n"
        ).encode()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quotes.csv"
            path.write_bytes(payload)
            metadata = summarize_csv_metadata(path, "quotes")
        self.assertEqual(metadata["duplicate_key_count"], 1)
        self.assertEqual(metadata["malformed_row_count"], 1)
        audit = audit_stage2_field_contract({role: metadata for role in STAGE2_DATASET_ROLES})
        self.assertIn("MALFORMED_ROWS:quotes", audit["issues"])

    def test_metadata_scan_records_calendar_order_violation(self) -> None:
        payload = "date\n2010-01-05\n2010-01-04\n".encode()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calendar.csv"
            path.write_bytes(payload)
            metadata = summarize_csv_metadata(path, "official_calendar")
        self.assertEqual(metadata["date_order_violation_count"], 1)

    def test_audit_rejects_forged_ranges_rates_and_unknown_boolean_states(self) -> None:
        metadata = {
            role: {
                "row_count": 1,
                "missing_required_columns": [],
                "duplicate_key_count": 0,
                "invalid_date_count": 0,
                "malformed_row_count": 0,
                "date_order_violation_count": 0,
                "date_ranges": {"date": ["2010-01-01", "2023-01-31"]},
                "distinct_values": {"is_st": ["unknown", "true"], "is_suspended": ["false", "true"]},
                "non_null_rates": {
                    field: 1.0
                    for field in {
                        "date", "symbol", "close", "amount", "amount_unit", "is_st", "is_suspended",
                        "close_observation_type",
                        "listDate", "listStatus", "stockType", "roeDiluted", "publishDate", "reportPeriodEnd",
                    }
                },
            }
            for role in STAGE2_DATASET_ROLES
        }
        metadata["fundamentals"]["date_ranges"] = {
            "publishDate": ["not-a-date", "2022-12-31"],
            "reportPeriodEnd": ["2009-01-01", "2022-12-31"],
        }
        metadata["stock_master"].update(
            {
                "delisted_row_count": 1,
                "delisted_missing_date_count": 0,
                "active_with_delist_count": 0,
                "invalid_delist_date_count": 0,
                "unknown_list_status_count": 1,
                "unknown_stock_type_count": 1,
                "exchange_values": ["BJ", "SH", "SZ"],
            }
        )
        metadata["quotes"]["distinct_values"] = {
            "is_st": ["false", "true", "unknown"],
            "is_suspended": ["false", "true"],
            "close_observation_type": [
                "suspension_valuation", "traded_close"
            ],
        }
        metadata["quotes"]["invalid_boolean_value_count"] = {
            "is_st": 1,
            "is_suspended": 0,
        }
        metadata["quotes"]["invalid_close_observation_type_count"] = 0
        metadata["quotes"]["close_observation_suspension_mismatch_count"] = 0
        metadata["quotes"]["invalid_amount_unit_count"] = 0
        result = audit_stage2_field_contract(metadata)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("FUNDAMENTAL_PUBLICATION_RANGE_INVALID", result["issues"])
        self.assertNotIn("DEGENERATE_FIELD:is_st", result["issues"])
        self.assertIn("UNKNOWN_LIST_STATUS", result["issues"])
        self.assertIn("UNKNOWN_STOCK_TYPE", result["issues"])
        self.assertIn("STOCK_MASTER_UNEXPECTED_EXCHANGE", result["issues"])
        self.assertIn("INVALID_BOOLEAN_VALUE:is_st", result["issues"])

    def test_audit_rejects_non_object_metadata_without_throwing(self) -> None:
        result = audit_stage2_field_contract(None)  # type: ignore[arg-type]
        self.assertEqual(result["status"], "blocked")
        self.assertIn("METADATA_BY_ROLE_NOT_OBJECT", result["issues"])

    def test_rights_template_is_fail_closed_until_human_attested(self) -> None:
        template = json.loads(
            (STUDY / "data_rights_attestation.template.json").read_text(encoding="utf-8")
        )
        result = validate_rights_attestation(template)
        self.assertEqual(result["status"], "invalid")
        self.assertIn("STATUS_NOT_ATTESTED", result["issues"])
        self.assertNotIn("ATTESTATION_MISSING", result["issues"])

    def test_valid_synthetic_rights_packet_still_does_not_authorize_execution(self) -> None:
        packet = _valid_rights_packet()
        result = validate_rights_attestation(packet)
        self.assertEqual(result["status"], "valid")
        self.assertFalse(result["authorization_granted"])

        packet["datasets"]["quotes"]["api_key"] = "must-not-enter-rights-packet"
        redacted_result = validate_rights_attestation(packet)
        self.assertEqual(redacted_result["status"], "invalid")
        self.assertIn("SECRET_LIKE_VALUE_PRESENT", redacted_result["issues"])
        self.assertNotIn(
            "must-not-enter-rights-packet", json.dumps(redacted_result)
        )

        del packet["datasets"]["quotes"]["api_key"]
        for credential_key in (
            "privateKey",
            "authorization",
            "bearerToken",
            "X-Amz-Signature",
            "x_amz_signature",
            "sig",
        ):
            packet["datasets"]["quotes"][credential_key] = "never-publish-this"
            credential_result = validate_rights_attestation(packet)
            self.assertEqual(credential_result["status"], "invalid")
            self.assertIn("SECRET_LIKE_VALUE_PRESENT", credential_result["issues"])
            self.assertNotIn("never-publish-this", json.dumps(credential_result))
            del packet["datasets"]["quotes"][credential_key]

    def test_rights_packet_requires_public_projection_rights_for_every_dataset(self) -> None:
        packet = _valid_rights_packet()
        self.assertEqual(validate_rights_attestation(packet)["status"], "valid")

        for role in STAGE2_DATASET_ROLES:
            for permission in (
                "source_identity_publication_permitted",
                "field_mapping_citation_permitted",
            ):
                with self.subTest(role=role, permission=permission):
                    denied = _valid_rights_packet()
                    denied["datasets"][role][permission] = False

                    result = validate_rights_attestation(denied)

                    self.assertEqual(result["status"], "invalid")
                    self.assertIn(
                        f"{role}:PERMISSION_NOT_GRANTED:{permission}",
                        result["issues"],
                    )

    def test_rights_packet_binds_exact_four_role_source_and_field_projection(self) -> None:
        packet = _valid_rights_packet()
        declaration = _valid_data_declaration_source_mappings()

        result = validate_rights_attestation(
            packet, data_declaration=declaration
        )

        self.assertEqual(result["status"], "valid", result["issues"])
        mapping_result = validate_stage2_dataset_source_mappings(
            declaration["dataset_source_mappings"]
        )
        self.assertEqual(mapping_result["status"], "valid")

    def test_rights_packet_rejects_rehashed_but_unlicensed_declaration_mapping(self) -> None:
        packet = _valid_rights_packet()
        declaration = _valid_data_declaration_source_mappings()
        declaration["dataset_source_mappings"]["datasets"]["quotes"][
            "source_name"
        ] = "different source inserted after rights review"

        result = validate_rights_attestation(
            packet, data_declaration=declaration
        )

        self.assertEqual(result["status"], "invalid")
        self.assertIn("quotes:DATA_DECLARATION_PROJECTION_MISMATCH", result["issues"])

    def test_rights_packet_rejects_swapped_role_and_partial_or_generic_mappings(self) -> None:
        for mutation, expected_issue in (
            (
                lambda projection: projection.update(dataset_role="stock_master"),
                "quotes:AUTHORIZED_PUBLIC_PROJECTION:DATASET_ROLE_MISMATCH",
            ),
            (
                lambda projection: projection["field_mapping"].pop("amount"),
                "quotes:AUTHORIZED_PUBLIC_PROJECTION:FIELD_MAPPING_FIELDS",
            ),
            (
                lambda projection: projection["field_mapping"].update(amount="approved"),
                "quotes:AUTHORIZED_PUBLIC_PROJECTION:FIELD_MAPPING_GENERIC:amount",
            ),
        ):
            with self.subTest(expected_issue=expected_issue):
                packet = _valid_rights_packet()
                projection = packet["datasets"]["quotes"][
                    "authorized_public_projection"
                ]
                mutation(projection)
                packet["datasets"]["quotes"][
                    "authorized_public_projection_sha256"
                ] = stage2_public_source_projection_sha256(projection)

                result = validate_rights_attestation(packet)

                self.assertEqual(result["status"], "invalid")
                self.assertIn(expected_issue, result["issues"])

    def test_rights_packet_rejects_projection_hash_substitution_and_schema_widening(self) -> None:
        packet = _valid_rights_packet()
        packet["datasets"]["quotes"][
            "authorized_public_projection_sha256"
        ] = "f" * 64
        packet["datasets"]["quotes"]["compliance_statement"] = "approved"

        result = validate_rights_attestation(packet)

        self.assertEqual(result["status"], "invalid")
        self.assertIn(
            "quotes:AUTHORIZED_PUBLIC_PROJECTION_HASH_MISMATCH", result["issues"]
        )
        self.assertIn("quotes:SCHEMA_FIELDS", result["issues"])

    def test_source_mapping_requires_exact_four_roles(self) -> None:
        declaration = _valid_data_declaration_source_mappings()
        del declaration["dataset_source_mappings"]["datasets"]["fundamentals"]

        result = validate_stage2_dataset_source_mappings(
            declaration["dataset_source_mappings"]
        )

        self.assertEqual(result["status"], "invalid")
        self.assertIn("SOURCE_MAPPINGS_DATASET_ROLES", result["issues"])

    def test_rights_packet_requires_expiry_and_conditional_permission_evidence(self) -> None:
        template = json.loads(
            (STUDY / "data_rights_attestation.template.json").read_text(encoding="utf-8")
        )
        template["contract_expiry_at"] = "2027-01-01T00:00:00Z"
        result = validate_rights_attestation(template)
        self.assertIn("POST_EXPIRY_SURVIVING_USE_NOT_CONFIRMED", result["issues"])
        self.assertIn("POST_EXPIRY_SURVIVAL_EVIDENCE_HASH_INVALID", result["issues"])

        template["datasets"]["quotes"]["restrictions"] = [
            {
                "restriction_id": "R-AGG-PUB-ROUNDING",
                "permission": "aggregate_publication_permitted",
                "description": "aggregate output must be rounded",
            }
        ]
        result = validate_rights_attestation(template)
        self.assertIn(
            "quotes:RESTRICTION_UNREVIEWED:R-AGG-PUB-ROUNDING", result["issues"]
        )

    def test_rights_packet_uses_shared_credential_classifier_without_leaking(self) -> None:
        for credential_key in (
            "AWSAccessKeyId",
            "X-Api-Key",
            "proxyAuthorization",
            "xApiKey",
            "Proxy-Authorization",
        ):
            with self.subTest(credential_key=credential_key):
                packet = _valid_rights_packet()
                secret_value = "must-never-appear-in-validation-output"
                packet["datasets"]["quotes"][credential_key] = secret_value

                result = validate_rights_attestation(packet)
                serialized_result = json.dumps(result, sort_keys=True)

                self.assertEqual(result["status"], "invalid")
                self.assertEqual(result["issues"], ["SECRET_LIKE_VALUE_PRESENT"])
                self.assertNotIn(credential_key, serialized_result)
                self.assertNotIn(secret_value, serialized_result)

    def test_rights_packet_requires_one_review_for_each_restriction(self) -> None:
        packet = _valid_rights_packet()
        quotes = packet["datasets"]["quotes"]
        quotes["restrictions"] = [
            {
                "restriction_id": "R-AGG-PUB-ROUNDING",
                "permission": "aggregate_publication_permitted",
                "description": "Round every published aggregate.",
            },
            {
                "restriction_id": "R-HASH-PREFIX",
                "permission": "hash_publication_permitted",
                "description": "Label each published digest as SHA-256.",
            },
        ]
        quotes["conditional_permission_reviews"] = [
            {
                "restriction_id": "R-AGG-PUB-ROUNDING",
                "permission": "aggregate_publication_permitted",
                "conditions_satisfied": True,
                "condition_evidence_sha256": "e" * 64,
                "reviewed_at": "2026-09-02T11:00:00+08:00",
            }
        ]

        result = validate_rights_attestation(packet)

        self.assertEqual(result["status"], "invalid")
        self.assertIn(
            "quotes:RESTRICTION_UNREVIEWED:R-HASH-PREFIX", result["issues"]
        )

    def test_rights_packet_rejects_duplicate_unknown_and_mismatched_reviews(self) -> None:
        packet = _valid_rights_packet()
        quotes = packet["datasets"]["quotes"]
        quotes["source_identity_publication_permitted"] = False
        quotes["restrictions"] = [
            {
                "restriction_id": "R-AGG-PUB-ROUNDING",
                "permission": "aggregate_publication_permitted",
                "description": "Round every published aggregate.",
            },
            {
                "restriction_id": "R-AGG-PUB-ROUNDING",
                "permission": "aggregate_publication_permitted",
                "description": "Duplicate identifiers are forbidden.",
            },
            {
                "restriction_id": "R-SOURCE-DISCLOSE-01",
                "permission": "source_identity_publication_permitted",
                "description": "Name the source only with written approval.",
            },
        ]
        base_review = {
            "conditions_satisfied": True,
            "condition_evidence_sha256": "e" * 64,
            "reviewed_at": "2026-09-02T11:00:00+08:00",
        }
        quotes["conditional_permission_reviews"] = [
            {
                **base_review,
                "restriction_id": "R-AGG-PUB-ROUNDING",
                "permission": "aggregate_publication_permitted",
            },
            {
                **base_review,
                "restriction_id": "R-AGG-PUB-ROUNDING",
                "permission": "aggregate_publication_permitted",
            },
            {
                **base_review,
                "restriction_id": "R-UNKNOWN",
                "permission": "aggregate_publication_permitted",
            },
            {
                **base_review,
                "restriction_id": "R-AGG-PUB-ROUNDING",
                "permission": "hash_publication_permitted",
            },
            {
                **base_review,
                "restriction_id": "R-SOURCE-DISCLOSE-01",
                "permission": "source_identity_publication_permitted",
            },
        ]

        result = validate_rights_attestation(packet)

        self.assertEqual(result["status"], "invalid")
        self.assertIn("quotes:RESTRICTION:1:ID_DUPLICATE", result["issues"])
        self.assertIn(
            "quotes:CONDITIONAL_REVIEW:1:RESTRICTION_ID_DUPLICATE",
            result["issues"],
        )
        self.assertIn(
            "quotes:CONDITIONAL_REVIEW:2:RESTRICTION_ID_UNKNOWN",
            result["issues"],
        )
        self.assertIn(
            "quotes:CONDITIONAL_REVIEW:3:PERMISSION_MISMATCH", result["issues"]
        )
        self.assertIn(
            "quotes:CONDITIONAL_REVIEW:4:PERMISSION_NOT_GRANTED", result["issues"]
        )

    def test_rights_packet_accepts_complete_one_to_one_condition_coverage(self) -> None:
        packet = _valid_rights_packet()
        quotes = packet["datasets"]["quotes"]
        quotes["restrictions"] = [
            {
                "restriction_id": "R-AGG-PUB-ROUNDING",
                "permission": "aggregate_publication_permitted",
                "description": "Round every published aggregate.",
            },
            {
                "restriction_id": "R-HASH-PREFIX",
                "permission": "hash_publication_permitted",
                "description": "Label each published digest as SHA-256.",
            },
        ]
        quotes["conditional_permission_reviews"] = [
            {
                "restriction_id": restriction["restriction_id"],
                "permission": restriction["permission"],
                "conditions_satisfied": True,
                "condition_evidence_sha256": str(index) * 64,
                "reviewed_at": "2026-09-02T11:00:00+08:00",
            }
            for index, restriction in enumerate(quotes["restrictions"], start=1)
        ]

        result = validate_rights_attestation(packet)

        self.assertEqual(result["status"], "valid", result["issues"])

    def test_rights_packet_cannot_hide_unreviewed_permissions_or_evidence(self) -> None:
        template = json.loads(
            (STUDY / "data_rights_attestation.template.json").read_text(encoding="utf-8")
        )
        # Even if a caller changes the status label, every affirmative right
        # and every evidence hash still has to be supplied by a human.
        template["status"] = "attested"
        template["attested_at"] = "2026-09-02T12:00:00Z"
        result = validate_rights_attestation(template)
        self.assertEqual(result["status"], "invalid")
        self.assertTrue(any("PERMISSION_NOT_GRANTED" in issue for issue in result["issues"]))
        self.assertIn("EVIDENCE_INDEX_MISSING", result["issues"])

    def test_rights_packet_rejects_contract_that_is_not_effective_at_attestation(self) -> None:
        packet = _valid_rights_packet()
        packet["attested_at"] = "2026-09-02T12:00:00Z"
        packet["contract_effective_at"] = "2026-09-03T00:00:00Z"
        packet["contract_expiry_at"] = "2027-01-01T00:00:00Z"
        result = validate_rights_attestation(packet)
        self.assertEqual(result["status"], "invalid")
        self.assertIn("CONTRACT_NOT_EFFECTIVE_AT_ATTESTATION", result["issues"])

    def test_audit_requires_all_four_roles_and_reports_coverage_gaps(self) -> None:
        metadata = {
            role: {
                "row_count": 1,
                "missing_required_columns": [],
                "duplicate_key_count": 0,
                "invalid_date_count": 0,
                "date_ranges": {"date": ["2023-01-03", "2023-01-03"]},
                "distinct_values": {"is_st": ["false"], "is_suspended": ["false"]},
            }
            for role in STAGE2_DATASET_ROLES
        }
        metadata["fundamentals"]["publishDate"] = ["2020-01-01", "2020-01-01"]
        result = audit_stage2_field_contract(metadata)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("QUOTE_WARMUP_NOT_COVERED", result["issues"])
        self.assertIn("FUNDAMENTAL_REPORT_RANGE_INVALID", result["issues"])
        self.assertIn("DEGENERATE_FIELD:is_suspended", result["issues"])
        self.assertFalse(result["authorization_granted"])


class TushareFrameAdapterTest(unittest.TestCase):
    def test_daily_adapter_requires_exact_adjustment_and_converts_units(self) -> None:
        daily = pd.DataFrame(
            [
                {
                    "ts_code": "600000.SH",
                    "trade_date": "20100104",
                    "close": 10.0,
                    "amount": 12.5,
                    "vol": 3.0,
                }
            ]
        )
        factors = pd.DataFrame(
            [{"ts_code": "600000.SH", "trade_date": "20100104", "adj_factor": 1.2}]
        )
        result = normalize_tushare_daily_frame(daily, factors)
        self.assertEqual(result.loc[0, "symbol"], "600000.SH")
        self.assertAlmostEqual(result.loc[0, "close"], 12.0)
        self.assertAlmostEqual(result.loc[0, "amount"], 12500.0)
        self.assertEqual(result.loc[0, "amount_unit"], "CNY")
        self.assertEqual(
            result.loc[0, "price_adjustment_method"],
            STAGE2_PRICE_ADJUSTMENT_METHOD,
        )
        self.assertEqual(
            result.loc[0, "price_adjustment_convention"],
            STAGE2_PRICE_ADJUSTMENT_CONVENTION,
        )
        self.assertAlmostEqual(result.loc[0, "volume"], 300.0)

        with self.assertRaisesRegex(DataAccessError, "adjustment factors"):
            normalize_tushare_daily_frame(daily, factors.iloc[0:0])

        bad_close = daily.copy()
        bad_close.loc[0, "close"] = float("inf")
        with self.assertRaisesRegex(DataAccessError, "non-finite"):
            normalize_tushare_daily_frame(bad_close, factors)

        bad_amount = daily.copy()
        bad_amount.loc[0, "amount"] = -1
        with self.assertRaisesRegex(DataAccessError, "negative amount"):
            normalize_tushare_daily_frame(bad_amount, factors)

    def test_calendar_adapter_intersects_both_exchanges_and_rejects_disagreement(self) -> None:
        raw = pd.DataFrame(
            [
                {"exchange": "SSE", "cal_date": "20100104", "is_open": 1},
                {"exchange": "SZSE", "cal_date": "20100104", "is_open": 1},
                {"exchange": "SSE", "cal_date": "20100105", "is_open": 1},
                {"exchange": "SZSE", "cal_date": "20100105", "is_open": 0},
            ]
        )
        with self.assertRaisesRegex(DataAccessError, "disagreement"):
            normalize_tushare_trade_calendar_frame(raw)
        common = normalize_tushare_trade_calendar_frame(raw.iloc[:2])
        self.assertEqual(common["date"].dt.strftime("%Y-%m-%d").tolist(), ["2010-01-04"])

        missing_exchange = raw.iloc[[0, 1, 2]].copy()
        with self.assertRaisesRegex(DataAccessError, "missing an SSE or SZSE"):
            normalize_tushare_trade_calendar_frame(missing_exchange)

    def test_disclosure_adapter_uses_actual_date_only(self) -> None:
        raw = pd.DataFrame(
            [
                {
                    "ts_code": "600000.SH",
                    "end_date": "20091231",
                    "actual_date": "20100301",
                    "pre_date": "20100220",
                }
            ]
        )
        result = normalize_tushare_disclosure_frame(raw)
        self.assertEqual(result.loc[0, "publishDate"].strftime("%Y-%m-%d"), "2010-03-01")
        self.assertEqual(result.loc[0, "reportPeriodEnd"].strftime("%Y-%m-%d"), "2009-12-31")
        missing_actual = raw.copy()
        missing_actual.loc[0, "actual_date"] = None
        with self.assertRaisesRegex(DataAccessError, "actual_date"):
            normalize_tushare_disclosure_frame(missing_actual)
        before_report = raw.copy()
        before_report.loc[0, "actual_date"] = "20090101"
        with self.assertRaisesRegex(DataAccessError, "before the report period"):
            normalize_tushare_disclosure_frame(before_report)

    def test_lifecycle_adapter_round_trips_to_strict_coverage(self) -> None:
        raw = pd.DataFrame(
            [
                {
                    "ts_code": "600000.SH",
                    "list_date": "19991110",
                    "delist_date": "",
                    "list_status": "L",
                    "stock_type": "A",
                },
                {
                    "ts_code": "000001.SZ",
                    "list_date": "19910403",
                    "delist_date": "20200102",
                    "list_status": "D",
                    "stock_type": "A",
                },
            ]
        )
        result = normalize_tushare_stock_master_frame(raw)
        self.assertEqual(result["symbol"].tolist(), ["000001.SZ", "600000.SH"])
        self.assertTrue(pd.isna(result.loc[1, "delistDate"]))
        self.assertEqual(result["listStatus"].tolist(), ["DELISTED", "ACTIVE"])
        self.assertEqual(result["stockType"].tolist(), ["A股", "A股"])

        canonical_csv = result.to_csv(
            index=False, date_format="%Y-%m-%d"
        ).encode("utf-8")
        self.assertEqual(
            study_v2_coverage._strict_a_share_master_symbols(canonical_csv),
            {"000001.SZ", "600000.SH"},
        )
        coverage_scan = study_v2_coverage._scan_master(
            canonical_csv,
            {
                "file_name": "stock_master.csv",
                "size_bytes": len(canonical_csv),
                "sha256": "0" * 64,
            },
        )
        self.assertEqual(coverage_scan["unrecognized_list_status_count"], 0)
        self.assertTrue(coverage_scan["membership_integrity_verified"])

        accepted_aliases = {
            "L": "ACTIVE",
            "listed": "ACTIVE",
            "ACTIVE": "ACTIVE",
            "A": "ACTIVE",
            "正常上市": "ACTIVE",
            "D": "DELISTED",
            "delisted": "DELISTED",
            "TERMINATED": "DELISTED",
            "退市": "DELISTED",
            "终止上市": "DELISTED",
        }
        for alias, canonical_status in accepted_aliases.items():
            with self.subTest(list_status_alias=alias):
                one_row = raw.iloc[[0 if canonical_status == "ACTIVE" else 1]].copy()
                one_row.loc[:, "list_status"] = alias
                normalized = normalize_tushare_stock_master_frame(one_row)
                self.assertEqual(normalized.loc[0, "listStatus"], canonical_status)

        a_share_label = raw.copy()
        a_share_label["stock_type"] = "A股"
        self.assertEqual(
            len(normalize_tushare_stock_master_frame(a_share_label)),
            len(raw),
        )
        for ambiguous_type in (
            "A_SHARE",
            "A-SHARE",
            "ASHARE",
            "COMMON_A",
            "COMMON STOCK",
            "EQUITY",
            "SHARE",
            "STOCK",
            "1",
            "普通股",
            "人民币普通股",
        ):
            with self.subTest(ambiguous_type=ambiguous_type):
                ambiguous = raw.copy()
                ambiguous["stock_type"] = ambiguous_type
                with self.assertRaisesRegex(DataAccessError, "unknown stock_type"):
                    normalize_tushare_stock_master_frame(ambiguous)
        with self.assertRaisesRegex(DataAccessError, "required columns"):
            normalize_tushare_stock_master_frame(raw.drop(columns=["delist_date"]))

        for rejected_status in ("NEW_STATUS", "P", "PAUSED"):
            with self.subTest(rejected_status=rejected_status):
                unknown = raw.copy()
                unknown.loc[0, "list_status"] = rejected_status
                with self.assertRaisesRegex(DataAccessError, "unknown list_status"):
                    normalize_tushare_stock_master_frame(unknown)

                bypassed = result.copy()
                bypassed.loc[1, "listStatus"] = rejected_status
                bypassed_csv = bypassed.to_csv(
                    index=False, date_format="%Y-%m-%d"
                ).encode("utf-8")
                bypassed_scan = study_v2_coverage._scan_master(
                    bypassed_csv,
                    {
                        "file_name": "stock_master.csv",
                        "size_bytes": len(bypassed_csv),
                        "sha256": "0" * 64,
                    },
                )
                self.assertEqual(
                    bypassed_scan["unrecognized_list_status_count"], 1
                )
                self.assertFalse(bypassed_scan["membership_integrity_verified"])

        missing_delist = raw.copy()
        missing_delist.loc[1, "delist_date"] = ""
        with self.assertRaisesRegex(DataAccessError, "without delist_date"):
            normalize_tushare_stock_master_frame(missing_delist)

        reversed_lifecycle = raw.copy()
        reversed_lifecycle.loc[1, "delist_date"] = "19900102"
        with self.assertRaisesRegex(DataAccessError, "before list dates"):
            normalize_tushare_stock_master_frame(reversed_lifecycle)

    def test_st_and_suspension_adapters_keep_absence_unknown(self) -> None:
        st = normalize_tushare_st_frame(
            pd.DataFrame([{"ts_code": "600000.SH", "trade_date": "20100104"}])
        )
        suspension = normalize_tushare_suspend_frame(
            pd.DataFrame(
                [
                    {"ts_code": "600000.SH", "trade_date": "20100105", "suspend_type": "S"},
                    {"ts_code": "600000.SH", "trade_date": "20100106", "suspend_type": "R"},
                ]
            )
        )
        self.assertEqual(st["is_st"].tolist(), [True])
        self.assertEqual(suspension["date"].dt.strftime("%Y-%m-%d").tolist(), ["2010-01-05"])
        self.assertEqual(suspension["is_suspended"].tolist(), [True])


if __name__ == "__main__":
    unittest.main()
