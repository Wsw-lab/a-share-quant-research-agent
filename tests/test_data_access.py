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
            "contract_reference": "contract:test-123",
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
            },
        }
        result = validate_rights_attestation(packet)
        self.assertEqual(result["status"], "valid")
        self.assertFalse(result["authorization_granted"])

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
        with self.assertRaisesRegex(DataAccessError, "required columns"):
            normalize_tushare_stock_master_frame(raw.drop(columns=["delist_date"]))

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
