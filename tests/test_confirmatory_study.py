from __future__ import annotations

import csv
from datetime import date, timedelta
import json
import hashlib
from pathlib import Path
import tempfile
import unittest

from a_share_quant_agent.confirmatory_study import (
    ConfirmatoryStudyError,
    build_public_evidence_status,
    run_confirmatory_study,
    verify_study_receipt,
    write_public_evidence_status,
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


if __name__ == "__main__":
    unittest.main()
