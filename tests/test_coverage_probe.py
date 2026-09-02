from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from a_share_quant_agent.coverage_probe import (
    AKSHARE_VERSION,
    DATES,
    GATE_IDS,
    PROBE_ID,
    PYTHON_VERSION,
    QDATA_COMMIT,
    RAW_SCHEMA_SHA256,
    RECEIPT_SCHEMA_VERSION,
    STUDY_ID,
    SYMBOLS,
    TIMESTAMP_TRUST_BOUNDARY,
    V1_SPEC_SHA256,
    CoverageProbeError,
    canonical_json_bytes,
    main,
    _normalise_bar,
    sha256_bytes,
    validate_external_timestamp_proof,
    verify_probe_artifacts,
)


class CoverageProbeContractTest(unittest.TestCase):
    def test_external_timestamp_requires_provider_evidence_and_hash_binding(self) -> None:
        proof = {
            "type": "human_verified_external_timestamp",
            "provider": "Example registry",
            "identifier": "record-1",
            "timestamped_at_utc": "2026-08-31T13:00:00Z",
            "verification_uri": "https://example.invalid/record-1",
            "evidence_sha256": "a" * 64,
            "subject_type": "coverage_probe_spec_sha256",
            "subject_sha256": "b" * 64,
            "verifier": "Independent reviewer",
            "verified_at_utc": "2026-08-31T13:05:00Z",
            "trust_boundary": TIMESTAMP_TRUST_BOUNDARY,
        }
        self.assertEqual(
            validate_external_timestamp_proof(
                proof,
                spec_sha256="b" * 64,
                before=datetime(2026, 9, 1, tzinfo=timezone.utc),
            )["identifier"],
            "record-1",
        )
        proof["subject_sha256"] = "c" * 64
        with self.assertRaises(CoverageProbeError):
            validate_external_timestamp_proof(proof, spec_sha256="b" * 64)

    def test_v1_hash_is_the_locked_immutable_predecessor(self) -> None:
        root = Path(__file__).resolve().parents[1]
        value = root / "studies/pit_factor_bias_decomposition_v2/coverage_probe_spec.v1.json"
        self.assertEqual(sha256_bytes(value.read_bytes()), V1_SPEC_SHA256)

    def test_blocked_receipt_is_auditable_but_never_passes(self) -> None:
        spec_sha = "d" * 64
        missing = [f"{symbol}|{date}" for date in DATES for symbol in SYMBOLS]
        failure = {"symbol": SYMBOLS[0], "date": DATES[0], "category": "empty_response"}
        receipt = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "study_id": STUDY_ID,
            "probe_id": PROBE_ID,
            "receipt_id": None,
            "spec_sha256": spec_sha,
            "status": "BLOCKED",
            "executed_at_utc": "2026-08-31T13:30:00Z",
            "external_timestamp_proof": {
                "type": "human_verified_external_timestamp",
                "provider": "Example registry",
                "identifier": "record-1",
                "timestamped_at_utc": "2026-08-31T13:00:00Z",
                "verification_uri": "https://example.invalid/record-1",
                "evidence_sha256": "a" * 64,
                "subject_type": "coverage_probe_spec_sha256",
                "subject_sha256": spec_sha,
                "verifier": "Independent reviewer",
                "verified_at_utc": "2026-08-31T13:05:00Z",
                "trust_boundary": TIMESTAMP_TRUST_BOUNDARY,
            },
            "repository_state": {
                "agent_commit": "e" * 40,
                "qdata_commit": QDATA_COMMIT,
                "agent_clean": True,
                "qdata_clean": True,
                "python_version": PYTHON_VERSION,
                "akshare_version": AKSHARE_VERSION,
            },
            "request": {
                "provider_adapter": "qdata.sources.providers.akshare_provider.AkShareProvider",
                "provider_interface": "akshare.stock_zh_a_hist",
                "upstream_provider_identity": "akshare",
                "dates": list(DATES),
                "symbols": list(SYMBOLS),
                "price_mode": "raw_unadjusted",
                "adjust_argument": "",
            },
            "artifacts": [
                {
                    "kind": "normalized_private",
                    "relative_path": "normalized.csv",
                    "sha256": "f" * 64,
                    "size_bytes": 0,
                    "row_count": 0,
                    "symbol_count": 0,
                    "minimum_date": None,
                    "maximum_date": None,
                    "schema_sha256": RAW_SCHEMA_SHA256,
                }
            ],
            "coverage": {
                "expected_symbol_date_cells": 24,
                "observed_symbol_date_cells": 0,
                "missing_symbol_date_cells": missing,
                "duplicate_symbol_date_cells": 0,
                "extra_symbol_date_cells": 0,
            },
            "field_quality": {
                "all_required_raw_bar_fields_valid": False,
                "scope_and_cell_identity_valid": False,
            },
            "failures": [failure],
            "gates": {
                gate: (gate not in {"COMPLETE_CELL_COVERAGE", "PROBE_SPECIFIC_RAW_BAR_FIELDS", "BASIC_VALUE_INTEGRITY"})
                for gate in GATE_IDS
            },
            "rights": {
                "review_status": "verified",
                "raw_redistribution_allowed": False,
                "aggregate_receipt_publication_allowed": True,
            },
            "claim_boundaries": {
                "factor_outcome_claim_allowed": False,
                "portfolio_claim_allowed": False,
                "execution_semantics_verified": False,
                "tradability_verified": False,
                "fundamental_history_verified": False,
                "recorded_publication_date_specification_effect_verified": False,
                "exact_endpoint_resolution_verified": False,
                "endpoint_reason_ledger_integrity_verified": False,
                "historical_investor_observed_value_verified": False,
                "revision_history_verified": False,
                "vintage_value_history_verified": False,
                "announcement_reaction_verified": False,
            },
        }
        unsigned = dict(receipt)
        unsigned.pop("receipt_id")
        receipt["receipt_id"] = "sha256:" + sha256_bytes(canonical_json_bytes(unsigned))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "receipt.json"
            path.write_bytes(canonical_json_bytes(receipt))
            audited = verify_probe_artifacts(path)
            receipt["status"] = "ERROR"
            path.write_bytes(canonical_json_bytes(receipt))
            with self.assertRaises(CoverageProbeError):
                verify_probe_artifacts(path)
        self.assertEqual(audited["status"], "BLOCKED")

    def test_malformed_timestamp_is_rejected(self) -> None:
        with self.assertRaises(CoverageProbeError):
            validate_external_timestamp_proof({}, spec_sha256="a" * 64)

    def test_boolean_market_values_are_not_numeric_bar_values(self) -> None:
        bar = {
            "symbol": SYMBOLS[0],
            "trade_date": DATES[0],
            "open": True,
            "high": 2.0,
            "low": 1.0,
            "close": 1.5,
            "volume": 1.0,
            "amount": 1.0,
        }
        with self.assertRaises(CoverageProbeError):
            _normalise_bar(bar, expected_symbol=SYMBOLS[0], expected_date=DATES[0])

    def test_cli_records_a_blocked_preflight_for_uncompleted_templates(self) -> None:
        root = Path(__file__).resolve().parents[1]
        study = root / "studies/pit_factor_bias_decomposition_v2"
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            report = output / "preflight.json"
            code = main(
                [
                    "preflight",
                    "--spec",
                    str(study / "coverage_probe_spec.v2.json"),
                    "--prior-inventory",
                    str(study / "prior_specification_inventory.json"),
                    "--timestamp-proof",
                    str(study / "coverage_probe_timestamp_proof.template.json"),
                    "--rights-review",
                    str(study / "coverage_probe_rights_review.template.json"),
                    "--qdata-checkout",
                    str(output / "missing-qdata"),
                    "--output-dir",
                    str(output / "probe"),
                    "--report",
                    str(report),
                ]
            )
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["status"], "BLOCKED")
            self.assertFalse((output / "probe").exists())


if __name__ == "__main__":
    unittest.main()
