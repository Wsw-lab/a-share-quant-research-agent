from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from a_share_quant_agent.data_access import (
    DataAccessError,
    STAGE2_DATASET_ROLES,
    assess_provider_capability,
    audit_stage2_field_contract,
    normalize_tushare_daily_frame,
    normalize_tushare_disclosure_frame,
    normalize_tushare_stock_master_frame,
    normalize_tushare_st_frame,
    normalize_tushare_suspend_frame,
    normalize_tushare_trade_calendar_frame,
    provider_capability_matrix,
    summarize_csv_metadata,
    validate_rights_attestation,
)


ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "studies" / "pit_factor_bias_decomposition_v2"


class DataAccessContractTest(unittest.TestCase):
    def test_capability_matrix_is_conservative_and_json_safe(self) -> None:
        matrix = provider_capability_matrix()
        self.assertGreaterEqual(len(matrix), 5)
        self.assertTrue(any(row["provider_id"] == "tushare_pro" for row in matrix))
        akshare = next(row for row in matrix if row["provider_id"] == "akshare")
        self.assertEqual(akshare["status"], "probe_only")
        self.assertNotIn("report_publication_date", akshare["datasets"])
        json.dumps(matrix)

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
            "date,symbol,close,amount,is_st,is_suspended\n"
            "2010-01-04,600000.SH,10,100,true,false\n"
            "2010-01-05,600000.SH,11,120,false,true\n"
        ).encode()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quotes.csv"
            path.write_bytes(payload)
            metadata = summarize_csv_metadata(path, "quotes")
        self.assertEqual(metadata["row_count"], 2)
        self.assertEqual(metadata["symbol_count"], 1)
        self.assertEqual(metadata["distinct_values"]["is_st"], ["false", "true"])
        self.assertEqual(metadata["distinct_values"]["is_suspended"], ["false", "true"])
        self.assertEqual(metadata["date_ranges"]["date"], ["2010-01-04", "2010-01-05"])
        self.assertNotIn("close", metadata["distinct_values"])

    def test_metadata_scan_counts_duplicate_keys_without_dropping_rows(self) -> None:
        payload = (
            "date,symbol,close,amount,is_st,is_suspended\n"
            "2010-01-04,600000.SH,10,100,false,false\n"
            "2010-01-04,600000.SH,10,100,false,false\n"
        ).encode()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quotes.csv"
            path.write_bytes(payload)
            metadata = summarize_csv_metadata(path, "quotes")
        self.assertEqual(metadata["row_count"], 2)
        self.assertEqual(metadata["duplicate_key_count"], 1)

    def test_metadata_scan_normalizes_date_keys_and_rejects_malformed_rows_at_audit(self) -> None:
        payload = (
            "date,symbol,close,amount,is_st,is_suspended\n"
            "20100104,600000.SH,10,100,false,false\n"
            "2010-01-04,600000.SH,10,100,false,false\n"
            "2010-01-05,600001.SZ,10,100,false,false,EXTRA\n"
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
                        "date", "symbol", "close", "amount", "is_st", "is_suspended",
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
        }
        metadata["quotes"]["invalid_boolean_value_count"] = {
            "is_st": 1,
            "is_suspended": 0,
        }
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
        datasets = {
            role: {
                "source_name": "licensed test source",
                "source_reference": "contract:test-123",
                "license_or_contract_scope": "private research and aggregate reporting",
                "terms_evidence_sha256": "a" * 64,
                "local_storage_permitted": True,
                "local_analysis_permitted": True,
                "aggregate_publication_permitted": True,
                "raw_redistribution_permitted": False,
                "hash_publication_permitted": True,
                "controlled_reviewer_rerun_permitted": True,
                "calendar_dates_publication_permitted": True,
            }
            for role in STAGE2_DATASET_ROLES
        }
        packet = {
            "schema_version": "stage2_data_rights_attestation_v1",
            "study_id": "a-share-factor-timing-bias-decomposition-v2",
            "status": "attested",
            "attested_at": "2026-09-02T12:00:00+08:00",
            "attestor": "Test reviewer",
            "attestor_role": "authorized data custodian",
            "contract_reference": "contract:test-123",
            "contract_effective_at": "2026-01-01T00:00:00+08:00",
            "contract_expiry_at": "2027-01-01T00:00:00+08:00",
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
                "trust_boundary": "A human reviewer must verify the contract and the exact permitted outputs.",
            },
        }
        result = validate_rights_attestation(packet)
        self.assertEqual(result["status"], "valid")
        self.assertFalse(result["authorization_granted"])

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
        datasets = {
            role: {
                "source_name": "licensed test source",
                "source_reference": "contract:test-123",
                "license_or_contract_scope": "private research and aggregate reporting",
                "terms_evidence_sha256": "a" * 64,
                "local_storage_permitted": True,
                "local_analysis_permitted": True,
                "aggregate_publication_permitted": True,
                "raw_redistribution_permitted": False,
                "hash_publication_permitted": True,
                "controlled_reviewer_rerun_permitted": True,
                "calendar_dates_publication_permitted": True,
            }
            for role in STAGE2_DATASET_ROLES
        }
        packet = {
            "schema_version": "stage2_data_rights_attestation_v1",
            "study_id": "a-share-factor-timing-bias-decomposition-v2",
            "status": "attested",
            "attested_at": "2026-09-02T12:00:00Z",
            "attestor": "Test reviewer",
            "attestor_role": "authorized data custodian",
            "contract_reference": "contract:test-123",
            "contract_effective_at": "2026-09-03T00:00:00Z",
            "contract_expiry_at": "2027-01-01T00:00:00Z",
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
            "evidence_index": [{"kind": "terms", "reference": "contract:test-123", "sha256": "a" * 64}],
            "signature": {
                "type": "human_verified_evidence",
                "evidence_sha256": "d" * 64,
                "signer_identity": "Test reviewer",
                "verification_uri": "https://example.invalid/review/123",
                "trust_boundary": "A human reviewer must verify the contract and the exact permitted outputs.",
            },
        }
        result = validate_rights_attestation(packet)
        self.assertEqual(result["status"], "invalid")
        self.assertIn("CONTRACT_NOT_EFFECTIVE_AT_ATTESTATION", result["issues"])

    def test_audit_requires_all_four_roles_and_reports_historical_gaps(self) -> None:
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
        self.assertIn("FUNDAMENTAL_PUBLICATION_HISTORY_NOT_COVERED", result["issues"])
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

    def test_lifecycle_adapter_requires_explicit_delist_and_status_fields(self) -> None:
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

        a_share_label = raw.copy()
        a_share_label["stock_type"] = "A股"
        self.assertEqual(
            len(normalize_tushare_stock_master_frame(a_share_label)),
            len(raw),
        )
        with self.assertRaisesRegex(DataAccessError, "required columns"):
            normalize_tushare_stock_master_frame(raw.drop(columns=["delist_date"]))

        unknown = raw.copy()
        unknown.loc[0, "list_status"] = "NEW_STATUS"
        with self.assertRaisesRegex(DataAccessError, "unknown list_status"):
            normalize_tushare_stock_master_frame(unknown)

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
