from __future__ import annotations

import os
import json
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from a_share_quant_agent import reproducible_experiment as experiment


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "qdata_research_snapshot_v1"
QDATA_SHA = "1" * 40


class ReproducibleExperimentCliTest(unittest.TestCase):
    def test_public_command_runs_exact_fixture_and_verifies_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run"
            second_output = Path(temp_dir) / "run-again"
            result = _command(
                "run",
                "--snapshot-dir",
                str(FIXTURE),
                "--output-dir",
                str(output),
                "--qdata-sha",
                QDATA_SHA,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {"receipt.json", "trades.jsonl", "orders.jsonl", "equity.jsonl", "metrics.json"},
            )
            repeated = _command(
                "run",
                "--snapshot-dir",
                str(FIXTURE),
                "--output-dir",
                str(second_output),
                "--qdata-sha",
                QDATA_SHA,
            )
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertEqual(
                {path.name: path.read_bytes() for path in output.iterdir()},
                {path.name: path.read_bytes() for path in second_output.iterdir()},
            )

            receipt_bytes = (output / "receipt.json").read_bytes()
            self.assertTrue(receipt_bytes.endswith(b"\n"))
            receipt = json.loads(receipt_bytes)
            self.assertEqual(receipt["schema_version"], "a_share_research_receipt_v1")
            self.assertEqual(receipt["snapshot"]["schema_version"], "research_snapshot_v1")
            self.assertEqual(receipt["snapshot"]["dataset_count"], 4)
            self.assertEqual(receipt["snapshot"]["normalized_panel_sha256"].__len__(), 64)
            self.assertEqual(
                {name: metadata["row_count"] for name, metadata in receipt["snapshot"]["datasets"].items()},
                {"daily_bar": 6, "fundamental_pit": 3, "security_membership": 2, "tradability": 6},
            )
            self.assertEqual(receipt["repositories"]["qdata"]["sha"], QDATA_SHA)
            self.assertEqual(
                receipt["repositories"]["qdata"]["provenance_verification"],
                "unverified_fixture_repository_reference",
            )
            self.assertEqual(receipt["strategy"]["config"]["factors"][0]["field"], "roe_ttm")
            self.assertEqual(receipt["strategy"]["config"]["rebalance"]["frequency"], "weekly")
            self.assertEqual(receipt["strategy"]["config"]["portfolio"]["max_positions"], 1)
            self.assertEqual(receipt["strategy"]["config"]["costs"]["slippage_bps"], "0.0")
            self.assertEqual(receipt["conventions"]["fill_reference"]["price"], "raw_open")
            self.assertFalse(receipt["conventions"]["fill_reference"]["adjusted_price_allowed"])
            self.assertEqual(
                receipt["first_fill"],
                {
                    "fill_price": "1710.0",
                    "fill_price_field": "open",
                    "fill_session": "2024-01-03",
                    "lot_multiple": True,
                    "lot_size": 100,
                    "raw_open_reference": "1710.0",
                    "shares": 500,
                    "signal_session": "2024-01-02",
                    "symbol": "600519.SH",
                },
            )
            self.assertEqual(receipt["verdict"]["status"], "INSUFFICIENT_EVIDENCE")
            self.assertEqual(
                receipt["verdict"]["reason_codes"],
                [
                    "SYNTHETIC_DATA",
                    "TWO_SYMBOLS",
                    "THREE_SESSIONS",
                    "NO_OUT_OF_SAMPLE",
                    "NO_STATISTICAL_INFERENCE",
                    "NO_PERFORMANCE_CLAIM",
                ],
            )
            self.assertFalse(receipt["verdict"]["performance_evidence"])
            self.assertFalse(receipt["verdict"]["generalization_evidence"])
            self.assertFalse(receipt["verdict"]["usable_for_trading_decisions"])
            self.assertEqual(
                receipt["determinism"]["environment_fields_allowed_to_vary"],
                [
                    "pandas_version",
                    "platform_machine",
                    "platform_system",
                    "python_implementation",
                    "python_version",
                ],
            )
            self.assertEqual(
                receipt["determinism"]["research_artifact_hashes"],
                ["equity.jsonl", "metrics.json", "orders.jsonl", "strategy_config", "trades.jsonl"],
            )
            self.assertEqual(
                json.loads((output / "metrics.json").read_bytes())["classification"],
                "fixture_arithmetic_only",
            )
            self.assertEqual(
                {name: metadata["row_count"] for name, metadata in receipt["artifacts"].items()},
                {"equity.jsonl": 3, "metrics.json": 1, "orders.jsonl": 1, "trades.jsonl": 1},
            )
            for name, metadata in receipt["artifacts"].items():
                self.assertEqual(
                    metadata["sha256"],
                    hashlib.sha256((output / name).read_bytes()).hexdigest(),
                )
            config_bytes = _canonical_bytes(receipt["strategy"]["config"])
            self.assertEqual(receipt["strategy"]["sha256"], hashlib.sha256(config_bytes).hexdigest())
            verified = _command("verify", "--output-dir", str(output))
            self.assertEqual(verified.returncode, 0, verified.stderr)

    def test_public_command_resolves_qdata_checkout_provenance(self) -> None:
        qdata_checkout = ROOT.parent / "qdata"
        if not qdata_checkout.is_dir():
            self.skipTest("neighboring QData checkout is not available")
        expected_sha = subprocess.run(
            ["git", "-C", str(qdata_checkout), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run"
            result = _command(
                "run",
                "--snapshot-dir",
                str(FIXTURE),
                "--output-dir",
                str(output),
                "--qdata-checkout",
                str(qdata_checkout),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads((output / "receipt.json").read_bytes())
            self.assertEqual(receipt["repositories"]["qdata"]["sha"], expected_sha)
            self.assertTrue(receipt["repositories"]["qdata"]["dirty_state"]["observed"])
            self.assertIsInstance(receipt["repositories"]["qdata"]["dirty_state"]["is_dirty"], bool)
            self.assertEqual(
                receipt["repositories"]["qdata"]["provenance_verification"],
                "byte_verified_builder_checkout",
            )

    def test_agent_identity_is_resolved_from_executing_module_not_foreign_git_cwd(self) -> None:
        expected_sha = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        with tempfile.TemporaryDirectory() as temp_dir:
            foreign_checkout = Path(temp_dir) / "foreign"
            foreign_checkout.mkdir()
            subprocess.run(["git", "init", "--quiet", str(foreign_checkout)], check=True)
            output = Path(temp_dir) / "output"
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(ROOT / "src")
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "a_share_quant_agent.reproducible_experiment",
                    "run",
                    "--snapshot-dir",
                    str(FIXTURE),
                    "--output-dir",
                    str(output),
                    "--qdata-sha",
                    QDATA_SHA,
                ],
                cwd=foreign_checkout,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads((output / "receipt.json").read_bytes())
            self.assertEqual(receipt["repositories"]["agent"]["sha"], expected_sha)

    def test_old_qdata_checkout_without_database_free_builder_is_rejected(self) -> None:
        qdata_checkout = ROOT.parent / "qdata"
        if not (qdata_checkout / ".git").exists():
            self.skipTest("neighboring QData Git checkout is not available")
        old_sha = "0479c8e30b775a0a862649c8e3ed41b785136077"
        probe = subprocess.run(
            ["git", "-C", str(qdata_checkout), "cat-file", "-e", f"{old_sha}^{{commit}}"],
            capture_output=True,
            check=False,
        )
        if probe.returncode != 0:
            self.skipTest("QData baseline commit is not available locally")
        with tempfile.TemporaryDirectory() as temp_dir:
            old_checkout = Path(temp_dir) / "qdata-old"
            subprocess.run(
                ["git", "clone", "--quiet", "--no-checkout", str(qdata_checkout), str(old_checkout)],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(old_checkout), "checkout", "--quiet", old_sha],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(old_checkout),
                    "remote",
                    "set-url",
                    "origin",
                    "https://github.com/Wsw-lab/qdata-free-source-quant-research-db.git",
                ],
                check=True,
            )

            with self.assertRaisesRegex(experiment.ExperimentError, "database-free snapshot builder"):
                experiment.run_experiment(
                    FIXTURE,
                    Path(temp_dir) / "output",
                    qdata_checkout=old_checkout,
                    _agent_sha_for_testing="2" * 40,
                )


class ReproducibleExperimentBoundaryTest(unittest.TestCase):
    def test_artifact_mutated_during_semantic_verification_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "output"
            _run_test_experiment(output)
            equity_path = output / "equity.jsonl"
            original_verify_metrics = experiment._verify_metrics_payload
            mutated = False

            def mutate_after_payloads_were_read(metrics):
                nonlocal mutated
                if not mutated:
                    payload = equity_path.read_bytes()
                    changed = payload.replace(b'"cash":"1000000.0"', b'"cash":"1000001.0"', 1)
                    self.assertEqual(len(changed), len(payload))
                    equity_path.write_bytes(changed)
                    mutated = True
                return original_verify_metrics(metrics)

            with patch.object(
                experiment,
                "_verify_metrics_payload",
                side_effect=mutate_after_payloads_were_read,
            ):
                with self.assertRaisesRegex(experiment.ExperimentError, "changed during verification"):
                    experiment.verify_experiment(output)

    def test_output_path_replaced_during_semantic_verification_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "output"
            moved_output = Path(temp_dir) / "original-output-moved"
            replacement = Path(temp_dir) / "replacement"
            _run_test_experiment(output)
            shutil.copytree(output, replacement)
            original_verify_metrics = experiment._verify_metrics_payload
            replaced = False

            def replace_output_path_before_final_check(metrics):
                nonlocal replaced
                if not replaced:
                    output.rename(moved_output)
                    replacement.rename(output)
                    replaced = True
                return original_verify_metrics(metrics)

            with patch.object(
                experiment,
                "_verify_metrics_payload",
                side_effect=replace_output_path_before_final_check,
            ):
                with self.assertRaisesRegex(experiment.ExperimentError, "changed during verification"):
                    experiment.verify_experiment(output)

    def test_resealed_research_values_cannot_change_fixed_artifact_payloads(self) -> None:
        mutations = {
            "trade_gross": ("trades.jsonl", lambda value: value[0].__setitem__("gross", "855001.0")),
            "trade_commission": ("trades.jsonl", lambda value: value[0].__setitem__("commission", "999.0")),
            "trade_stamp_tax": ("trades.jsonl", lambda value: value[0].__setitem__("stamp_tax", "999.0")),
            "trade_cash": ("trades.jsonl", lambda value: value[0].__setitem__("cash_delta", "-1.0")),
            "order": ("orders.jsonl", lambda value: value[0].__setitem__("note", "fabricated")),
            "equity": ("equity.jsonl", lambda value: value[0].__setitem__("cash", "999999.0")),
            "metrics": (
                "metrics.json",
                lambda value: value["values"].__setitem__("annualized_return", "999.0"),
            ),
        }
        for name, (filename, mutate) in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp_dir:
                output = Path(temp_dir) / "output"
                _run_test_experiment(output)
                artifact_path = output / filename
                if filename.endswith(".jsonl"):
                    value = [
                        json.loads(line)
                        for line in artifact_path.read_text(encoding="utf-8").splitlines()
                    ]
                    mutate(value)
                    payload = b"".join(_canonical_bytes(row) for row in value)
                    row_count = len(value)
                else:
                    value = json.loads(artifact_path.read_bytes())
                    mutate(value)
                    payload = _canonical_bytes(value)
                    row_count = 1
                artifact_path.write_bytes(payload)
                _update_artifact_and_reseal(output, filename, payload, row_count)

                with self.assertRaisesRegex(experiment.ExperimentError, "fixed research artifact SHA256"):
                    experiment.verify_experiment(output)

    def test_same_length_rewrite_with_restored_mtime_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "output"
            _run_test_experiment(output)
            equity_path = output / "equity.jsonl"
            trades_path = output / "trades.jsonl"
            original_equity_info = equity_path.stat()
            trades_inode = trades_path.stat().st_ino
            original_path_read = Path.read_bytes
            original_os_read = os.read
            mutated = False

            def mutate_equity_once() -> None:
                nonlocal mutated
                if mutated:
                    return
                payload = original_path_read(equity_path)
                changed = payload.replace(b'"cash":"1000000.0"', b'"cash":"1000001.0"', 1)
                self.assertEqual(len(changed), len(payload))
                with equity_path.open("r+b") as handle:
                    handle.write(changed)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.utime(
                    equity_path,
                    ns=(original_equity_info.st_atime_ns, original_equity_info.st_mtime_ns),
                    follow_symlinks=False,
                )
                mutated = True

            def path_read_with_mutation(path):
                payload = original_path_read(path)
                if path.name == "trades.jsonl":
                    mutate_equity_once()
                return payload

            def os_read_with_mutation(descriptor, size):
                if os.fstat(descriptor).st_ino == trades_inode:
                    mutate_equity_once()
                return original_os_read(descriptor, size)

            with patch.object(Path, "read_bytes", path_read_with_mutation), patch.object(
                os, "read", os_read_with_mutation
            ):
                with self.assertRaisesRegex(experiment.ExperimentError, "changed during verification"):
                    experiment.verify_experiment(output)

    def test_snapshot_byte_mutation_is_rejected_before_output_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = Path(temp_dir) / "snapshot"
            output = Path(temp_dir) / "output"
            shutil.copytree(FIXTURE, snapshot)
            daily_bar = snapshot / "daily_bar.csv"
            daily_bar.write_bytes(daily_bar.read_bytes().replace(b"1710", b"1711", 1))

            with self.assertRaisesRegex(experiment.ExperimentError, "snapshot verification failed"):
                experiment.run_experiment(
                    snapshot,
                    output,
                    _agent_sha_for_testing="2" * 40,
                    _qdata_sha_for_testing=QDATA_SHA,
                )
            self.assertFalse(output.exists())

    def test_snapshot_changed_after_adapter_load_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = Path(temp_dir) / "snapshot"
            output = Path(temp_dir) / "output"
            shutil.copytree(FIXTURE, snapshot)
            original_load = experiment.load_qdata_snapshot

            def load_then_replace_manifest(path):
                loaded = original_load(path)
                manifest_path = Path(path) / "manifest.json"
                manifest = json.loads(manifest_path.read_bytes())
                manifest["artifact_notice"] += " Mutated after adapter verification."
                manifest_path.write_text(
                    json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
                    encoding="utf-8",
                )
                return loaded

            with patch.object(experiment, "load_qdata_snapshot", side_effect=load_then_replace_manifest):
                with self.assertRaisesRegex(experiment.ExperimentError, "changed after verification"):
                    experiment.run_experiment(
                        snapshot,
                        output,
                        _agent_sha_for_testing="2" * 40,
                        _qdata_sha_for_testing=QDATA_SHA,
                    )

    def test_verifier_rejects_json_float_in_decimal_string_column_even_when_resealed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "output"
            _run_test_experiment(output)
            equity_path = output / "equity.jsonl"
            rows = [json.loads(line) for line in equity_path.read_text(encoding="utf-8").splitlines()]
            rows[0]["cash"] = 1_000_000.0
            payload = b"".join(_canonical_bytes(row) for row in rows)
            equity_path.write_bytes(payload)
            _update_artifact_and_reseal(output, "equity.jsonl", payload, len(rows))

            with self.assertRaisesRegex(experiment.ExperimentError, "decimal string"):
                experiment.verify_experiment(output)

    def test_maintained_in_repository_output_root_is_git_ignored(self) -> None:
        output_root = ROOT / ".research-artifacts"
        output = output_root / "unit-test-run"
        shutil.rmtree(output_root, ignore_errors=True)
        try:
            experiment.run_experiment(
                FIXTURE,
                output,
                qdata_sha=QDATA_SHA,
            )
            self.assertTrue(output.is_dir())
            ignored = subprocess.run(
                ["git", "check-ignore", "--quiet", str(output)],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(ignored.returncode, 0)
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_timing_and_strategy_receipt_mutations_are_rejected_even_when_resealed(self) -> None:
        mutations = {
            "timing": lambda receipt: receipt["conventions"]["fill_reference"].__setitem__("price", "adjusted_open"),
            "strategy": lambda receipt: receipt["strategy"]["config"]["factors"][0].__setitem__("direction", "asc"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp_dir:
                output = Path(temp_dir) / "output"
                _run_test_experiment(output)
                receipt_path = output / "receipt.json"
                receipt = json.loads(receipt_path.read_bytes())
                mutate(receipt)
                if name == "strategy":
                    receipt["strategy"]["sha256"] = hashlib.sha256(
                        _canonical_bytes(receipt["strategy"]["config"])
                    ).hexdigest()
                _reseal_receipt(receipt_path, receipt)

                with self.assertRaises(experiment.ExperimentError):
                    experiment.verify_experiment(output)

    def test_resealed_snapshot_cannot_be_relabelled_as_market_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "output"
            _run_test_experiment(output)
            receipt_path = output / "receipt.json"
            receipt = json.loads(receipt_path.read_bytes())
            receipt["snapshot"]["producer_source"] = "real_market_data"
            receipt["snapshot"]["artifact_notice"] = "Verified market evidence."
            _reseal_receipt(receipt_path, receipt)

            with self.assertRaisesRegex(experiment.ExperimentError, "exact synthetic fixture"):
                experiment.verify_experiment(output)

    def test_resealed_first_fill_cannot_move_before_exact_signal_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "output"
            _run_test_experiment(output)
            trades_path = output / "trades.jsonl"
            orders_path = output / "orders.jsonl"
            trades = [json.loads(line) for line in trades_path.read_text(encoding="utf-8").splitlines()]
            orders = [json.loads(line) for line in orders_path.read_text(encoding="utf-8").splitlines()]
            trades[0]["signal_date"] = "2024-01-01"
            orders[0]["signal_date"] = "2024-01-01"
            trades_payload = b"".join(_canonical_bytes(row) for row in trades)
            orders_payload = b"".join(_canonical_bytes(row) for row in orders)
            trades_path.write_bytes(trades_payload)
            orders_path.write_bytes(orders_payload)
            receipt_path = output / "receipt.json"
            receipt = json.loads(receipt_path.read_bytes())
            receipt["first_fill"]["signal_session"] = "2024-01-01"
            receipt["artifacts"]["trades.jsonl"]["sha256"] = hashlib.sha256(trades_payload).hexdigest()
            receipt["artifacts"]["orders.jsonl"]["sha256"] = hashlib.sha256(orders_payload).hexdigest()
            _reseal_receipt(receipt_path, receipt)

            with self.assertRaisesRegex(experiment.ExperimentError, "exact first-fill signal session"):
                experiment.verify_experiment(output)

    def test_resealed_source_lineage_must_match_exact_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "output"
            _run_test_experiment(output)
            receipt_path = output / "receipt.json"
            receipt = json.loads(receipt_path.read_bytes())
            receipt["snapshot"]["source_lineage"][2]["value"] = "fabricated-batch"
            _reseal_receipt(receipt_path, receipt)

            with self.assertRaisesRegex(experiment.ExperimentError, "exact deterministic fixture lineage"):
                experiment.verify_experiment(output)

    def test_resealed_extra_trade_and_order_cannot_expand_fixed_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "output"
            _run_test_experiment(output)
            trades_path = output / "trades.jsonl"
            orders_path = output / "orders.jsonl"
            trades = [json.loads(line) for line in trades_path.read_text(encoding="utf-8").splitlines()]
            orders = [json.loads(line) for line in orders_path.read_text(encoding="utf-8").splitlines()]
            extra_trade = dict(trades[0])
            extra_trade.update(
                {
                    "cash_delta": "-1000.0",
                    "gross": "1000.0",
                    "price": "10.0",
                    "shares": 100,
                    "symbol": "600520.SH",
                }
            )
            extra_order = dict(orders[0])
            extra_order.update({"requested_shares": 100, "symbol": "600520.SH"})
            trades.append(extra_trade)
            orders.append(extra_order)
            trades.sort(key=lambda row: (row["signal_date"], row["date"], row["symbol"], row["side"]))
            orders.sort(
                key=lambda row: (
                    row["signal_date"], row["date"], row["symbol"], row["side"],
                    row["record_type"], row["status"],
                )
            )
            trades_payload = b"".join(_canonical_bytes(row) for row in trades)
            orders_payload = b"".join(_canonical_bytes(row) for row in orders)
            trades_path.write_bytes(trades_payload)
            orders_path.write_bytes(orders_payload)
            receipt_path = output / "receipt.json"
            receipt = json.loads(receipt_path.read_bytes())
            for name, payload, rows in (
                ("trades.jsonl", trades_payload, trades),
                ("orders.jsonl", orders_payload, orders),
            ):
                receipt["artifacts"][name]["sha256"] = hashlib.sha256(payload).hexdigest()
                receipt["artifacts"][name]["row_count"] = len(rows)
            _reseal_receipt(receipt_path, receipt)

            with self.assertRaisesRegex(experiment.ExperimentError, "fixed timing-probe row count"):
                experiment.verify_experiment(output)

    def test_resealed_canonicalization_contract_mutation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "output"
            _run_test_experiment(output)
            receipt_path = output / "receipt.json"
            receipt = json.loads(receipt_path.read_bytes())
            receipt["artifact_contract"]["decimal_encoding"] = "arbitrary JSON number"
            _reseal_receipt(receipt_path, receipt)

            with self.assertRaisesRegex(experiment.ExperimentError, "canonicalization contract"):
                experiment.verify_experiment(output)

    def test_trade_artifact_one_byte_mutation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "output"
            _run_test_experiment(output)
            trades = output / "trades.jsonl"
            payload = trades.read_bytes()
            mutated = payload.replace(b"600519.SH", b"600518.SH", 1)
            self.assertEqual(len(payload), len(mutated))
            trades.write_bytes(mutated)

            with self.assertRaisesRegex(experiment.ExperimentError, "SHA256 mismatch"):
                experiment.verify_experiment(output)

    def test_artifact_changed_after_its_read_is_rejected_before_verifier_returns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "output"
            _run_test_experiment(output)
            equity_path = output / "equity.jsonl"
            trades_inode = (output / "trades.jsonl").stat().st_ino
            original_equity = equity_path.read_bytes()
            original_os_read = os.read
            mutated = False

            def read_then_mutate_earlier_artifact(descriptor, size):
                nonlocal mutated
                if os.fstat(descriptor).st_ino == trades_inode and not mutated:
                    equity_path.write_bytes(
                        original_equity.replace(b"1000000.0", b"1000001.0", 1)
                    )
                    mutated = True
                return original_os_read(descriptor, size)

            with patch.object(os, "read", read_then_mutate_earlier_artifact):
                with self.assertRaisesRegex(experiment.ExperimentError, "changed during verification"):
                    experiment.verify_experiment(output)

    def test_repository_sha_mutation_is_rejected_by_expected_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "output"
            _run_test_experiment(output)
            receipt_path = output / "receipt.json"
            receipt = json.loads(receipt_path.read_bytes())
            receipt["repositories"]["agent"]["sha"] = "3" * 40
            _reseal_receipt(receipt_path, receipt)

            with self.assertRaisesRegex(experiment.ExperimentError, "verification anchor"):
                experiment.verify_experiment(output, expected_agent_sha="2" * 40)

    def test_extra_and_missing_output_files_are_rejected(self) -> None:
        for mutation in ("extra", "missing"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp_dir:
                output = Path(temp_dir) / "output"
                _run_test_experiment(output)
                if mutation == "extra":
                    (output / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
                else:
                    (output / "orders.jsonl").unlink()

                with self.assertRaisesRegex(experiment.ExperimentError, "output files mismatch"):
                    experiment.verify_experiment(output)

    def test_unknown_schema_and_noncanonical_receipt_are_rejected(self) -> None:
        for mutation in ("schema", "pretty"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp_dir:
                output = Path(temp_dir) / "output"
                _run_test_experiment(output)
                receipt_path = output / "receipt.json"
                receipt = json.loads(receipt_path.read_bytes())
                if mutation == "schema":
                    receipt["schema_version"] = "a_share_research_receipt_v2"
                    _reseal_receipt(receipt_path, receipt)
                    pattern = "unsupported receipt schema"
                else:
                    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
                    pattern = "not canonical JSON"

                with self.assertRaisesRegex(experiment.ExperimentError, pattern):
                    experiment.verify_experiment(output)

    def test_nan_artifact_is_rejected_before_hash_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "output"
            _run_test_experiment(output)
            metrics_path = output / "metrics.json"
            metrics_path.write_text(
                '{"classification":"fixture_arithmetic_only","not_performance_evidence":true,"values":{"bad":NaN}}\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(experiment.ExperimentError, "non-finite JSON value"):
                experiment.verify_experiment(output)

    def test_fabricated_final_session_fill_is_rejected_even_when_resealed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "output"
            _run_test_experiment(output)
            orders_path = output / "orders.jsonl"
            orders = [json.loads(line) for line in orders_path.read_text(encoding="utf-8").splitlines()]
            orders[0] = {
                "date": "2024-01-04",
                "execution_model": "close_signal_next_open",
                "fill_price_field": "open",
                "note": "",
                "record_type": "signal_intent",
                "requested_shares": None,
                "side": "rebalance_intent",
                "signal_date": "2024-01-04",
                "status": "unfilled_no_next_session",
                "symbol": "",
                "targets": ["600519.SH"],
            }
            orders.sort(
                key=lambda row: tuple(
                    (1, "") if row[field] is None else (0, json.dumps(row[field], sort_keys=True))
                    for field in ("signal_date", "date", "symbol", "side", "record_type", "status")
                )
            )
            payload = b"".join(_canonical_bytes(row) for row in orders)
            orders_path.write_bytes(payload)
            _update_artifact_and_reseal(output, "orders.jsonl", payload, len(orders))

            with self.assertRaisesRegex(experiment.ExperimentError, "must not have a fabricated fill date"):
                experiment.verify_experiment(output)

    def test_real_engine_final_session_signal_remains_an_unfilled_intent(self) -> None:
        data = experiment.load_qdata_snapshot(FIXTURE).data.copy()
        date_map = {
            "2024-01-02": "2024-01-02",
            "2024-01-03": "2024-01-08",
            "2024-01-04": "2024-01-15",
        }
        data["date"] = pd.to_datetime(data["date"].dt.strftime("%Y-%m-%d").map(date_map))
        final = data["date"] == pd.Timestamp("2024-01-15")
        data.loc[final & (data["symbol"] == "000001.SZ"), "roe_ttm"] = 9.0
        data.loc[final & (data["symbol"] == "600519.SH"), "roe_ttm"] = -9.0
        spec = experiment.StrategySpec.from_dict(
            json.loads(json.dumps(experiment._RUNTIME_STRATEGY_CONFIG))
        )

        result = experiment.run_backtest(data, spec)
        artifacts = experiment._build_artifact_payloads(result)
        orders = artifacts["orders.jsonl"]["value"]
        unfilled = [order for order in orders if order["status"] == "unfilled_no_next_session"]

        self.assertEqual(len(unfilled), 1)
        self.assertIsNone(unfilled[0]["date"])
        self.assertEqual(unfilled[0]["signal_date"], "2024-01-15")
        self.assertEqual(unfilled[0]["record_type"], "signal_intent")
        experiment._validate_result_timing(
            artifacts["trades.jsonl"]["value"],
            orders,
            final_session="2024-01-15",
        )

    def test_nonempty_output_directory_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "output"
            _run_test_experiment(output)
            original = {path.name: path.read_bytes() for path in output.iterdir()}

            with self.assertRaisesRegex(experiment.ExperimentError, "refusing to overwrite"):
                _run_test_experiment(output)
            self.assertEqual(original, {path.name: path.read_bytes() for path in output.iterdir()})

    def test_invalid_explicit_qdata_sha_is_rejected_by_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = _command(
                "run",
                "--snapshot-dir",
                str(FIXTURE),
                "--output-dir",
                str(Path(temp_dir) / "output"),
                "--qdata-sha",
                "short",
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("full lowercase 40-hex", result.stderr)

    def test_receipt_contains_no_checkout_or_temporary_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "output"
            _run_test_experiment(output)
            payload = (output / "receipt.json").read_text(encoding="utf-8")

            self.assertNotIn(str(ROOT), payload)
            self.assertNotIn(temp_dir, payload)


def _command(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "a_share_quant_agent.reproducible_experiment", *arguments],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def _run_test_experiment(output: Path) -> None:
    experiment.run_experiment(
        FIXTURE,
        output,
        _agent_sha_for_testing="2" * 40,
        _qdata_sha_for_testing=QDATA_SHA,
    )


def _canonical_bytes(value) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _update_artifact_and_reseal(output: Path, filename: str, payload: bytes, row_count: int) -> None:
    receipt_path = output / "receipt.json"
    receipt = json.loads(receipt_path.read_bytes())
    receipt["artifacts"][filename]["sha256"] = hashlib.sha256(payload).hexdigest()
    receipt["artifacts"][filename]["row_count"] = row_count
    _reseal_receipt(receipt_path, receipt)


def _reseal_receipt(path: Path, receipt: dict) -> None:
    unsigned = dict(receipt)
    unsigned.pop("receipt_integrity", None)
    receipt["receipt_integrity"]["sha256"] = hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()
    path.write_bytes(_canonical_bytes(receipt))


if __name__ == "__main__":
    unittest.main()
