from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from a_share_quant_agent.backtest import run_backtest
from a_share_quant_agent.qdata_snapshot import (
    QDataSnapshotError,
    load_qdata_snapshot,
    verify_qdata_snapshot,
)
from a_share_quant_agent.spec import StrategySpec


FIXTURE = Path(__file__).parent / "fixtures" / "qdata_research_snapshot_v1"
ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ID = "sha256:0b7a9697ceccc81cf74e131b74e9377c106160919da990910725011ad39c342b"


class QDataSnapshotLoadTest(unittest.TestCase):
    def test_frozen_three_day_fixture_maps_raw_prices_constraints_and_lineage(self) -> None:
        manifest = verify_qdata_snapshot(FIXTURE)
        loaded = load_qdata_snapshot(FIXTURE)
        row = _row(loaded.data, "600519.SH", "2024-01-02")

        self.assertEqual(manifest["snapshot_id"], SNAPSHOT_ID)
        self.assertEqual(len(loaded.data), 6)
        self.assertEqual(float(row["open"]), 1700.0)
        self.assertEqual(float(row["close"]), 1870.0)
        self.assertEqual(float(row["close_adjusted"]), 1870.0)
        self.assertTrue(bool(row["is_limit_up"]))
        self.assertFalse(bool(row["can_buy"]))
        self.assertTrue(bool(row["can_sell"]))
        self.assertEqual(int(row["lot_size"]), 100)
        self.assertTrue(bool(row["t_plus_one"]))
        self.assertTrue(bool(row["is_stock_master_member"]))
        self.assertEqual(row["board"], "SSE_MAIN")
        self.assertEqual(row["signal_available_at"], pd.Timestamp("2024-01-02T07:05:00Z"))
        self.assertIsNotNone(row["signal_available_at"].tzinfo)

        metadata = loaded.metadata
        self.assertEqual(metadata.snapshot_id, SNAPSHOT_ID)
        self.assertEqual(metadata.schema_version, "research_snapshot_v1")
        self.assertEqual(metadata.cutoff_ts, "2024-05-01T08:00:00Z")
        self.assertEqual(
            dict(metadata.dataset_versions),
            {
                "daily_bar": "fixture-v1",
                "fundamental_pit": "fixture-v1",
                "security_membership": "fixture-v1",
                "tradability": "fixture-v1",
            },
        )
        self.assertIn(("snapshot", "deterministic_synthetic_fixture"), metadata.source_lineage)
        self.assertIn(("daily_bar.batch_id", "batch-fixture-001"), metadata.source_lineage)

    def test_pit_fundamentals_use_latest_revision_known_at_each_signal(self) -> None:
        data = load_qdata_snapshot(FIXTURE).data

        self.assertEqual(float(_row(data, "600519.SH", "2024-01-03")["roe_ttm"]), 0.315)
        self.assertEqual(float(_row(data, "600519.SH", "2024-01-04")["roe_ttm"]), 0.318)
        self.assertEqual(
            _row(data, "600519.SH", "2024-01-03")["roe_ttm_revision_id"],
            "original",
        )
        self.assertEqual(
            _row(data, "600519.SH", "2024-01-04")["roe_ttm_revision_id"],
            "restatement-1",
        )

    def test_adapter_runs_when_qdata_import_is_blocked(self) -> None:
        with patch.dict(sys.modules, {"qdata": None, "qdata.research_snapshot": None}):
            loaded = load_qdata_snapshot(FIXTURE)

        self.assertEqual(loaded.metadata.snapshot_id, SNAPSHOT_ID)

    def test_normalized_panel_runs_directly_with_next_raw_open_execution(self) -> None:
        loaded = load_qdata_snapshot(FIXTURE)
        spec = StrategySpec.from_dict(
            {
                "name": "qdata-contract-probe",
                "description": "Frozen synthetic contract fixture.",
                "universe": {"exclude_st": True, "exclude_suspended": True, "min_amount": 0.0},
                "rebalance": {"frequency": "weekly"},
                "portfolio": {"initial_cash": 1_000_000.0, "max_positions": 1, "weighting": "equal"},
                "costs": {"commission_rate": 0.0, "stamp_tax_rate": 0.0, "slippage_bps": 0.0},
                "execution": {"model": "close_signal_next_open"},
                "factors": [{"field": "roe_ttm", "direction": "desc", "weight": 1.0}],
                "risk": {"max_single_position_weight": 1.0},
            }
        )

        result = run_backtest(loaded.data, spec)

        first_trade = result.trades.iloc[0]
        self.assertEqual(first_trade["symbol"], "600519.SH")
        self.assertEqual(first_trade["signal_date"], pd.Timestamp("2024-01-02"))
        self.assertEqual(first_trade["date"], pd.Timestamp("2024-01-03"))
        self.assertEqual(float(first_trade["price"]), 1710.0)
        self.assertEqual(first_trade["fill_price_field"], "open")

    def test_membership_outputs_are_point_in_time_and_panel_hash_is_stable(self) -> None:
        first = load_qdata_snapshot(FIXTURE)
        second = load_qdata_snapshot(FIXTURE)
        universe = first.universe.merge(
            first.data[["symbol", "date", "signal_available_at"]],
            on=["symbol", "date"],
            how="inner",
            validate="one_to_one",
        )
        jan_four = universe[
            (universe["symbol"] == "000001.SZ")
            & (universe["date"] == pd.Timestamp("2024-01-04"))
        ].iloc[0]
        master = first.stock_master[first.stock_master["symbol"] == "000001.SZ"].iloc[0]

        self.assertEqual(first.metadata.data_hash, second.metadata.data_hash)
        self.assertEqual(len(first.metadata.data_hash), 64)
        self.assertTrue((universe["membership_available_at"] <= universe["signal_available_at"]).all())
        self.assertTrue(bool(jan_four["is_stock_master_member"]))
        self.assertEqual(jan_four["membership_status"], "delisted")
        self.assertEqual(master["valid_to"], pd.Timestamp("2024-01-05"))
        self.assertEqual(master["delistDate"], pd.Timestamp("2024-01-05"))

    def test_installed_package_exposes_snapshot_adapter_outside_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            target = temporary / "site-packages"
            outside = temporary / "outside"
            outside.mkdir()
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            environment["PIP_NO_INDEX"] = "1"
            install = subprocess.run(
                [
                    sys.executable, "-m", "pip", "install", "--no-deps",
                    "--no-build-isolation", "--target", str(target), str(ROOT),
                ],
                cwd=outside,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(install.returncode, 0, install.stdout + install.stderr)
            probe_environment = dict(environment)
            probe_environment["PYTHONPATH"] = str(target)
            probe = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; "
                        "from a_share_quant_agent.qdata_snapshot import load_qdata_snapshot; "
                        f"target=Path({str(target)!r}).resolve(); "
                        "module=Path(__import__('a_share_quant_agent.qdata_snapshot', "
                        "fromlist=['load_qdata_snapshot']).__file__).resolve(); "
                        "assert target in module.parents; assert callable(load_qdata_snapshot)"
                    ),
                ],
                cwd=outside,
                env=probe_environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(probe.returncode, 0, probe.stdout + probe.stderr)


class QDataSnapshotRejectTest(unittest.TestCase):
    def test_hash_tampering_fails_closed(self) -> None:
        with _snapshot_copy() as root:
            path = root / "daily_bar.csv"
            path.write_bytes(path.read_bytes().replace(b",1700,1870,", b",1701,1870,", 1))

            with self.assertRaisesRegex(QDataSnapshotError, "SHA256"):
                load_qdata_snapshot(root)

    def test_hard_linked_snapshot_file_fails_closed(self) -> None:
        with _snapshot_copy() as root:
            daily = root / "daily_bar.csv"
            external = root.parent / "external-daily.csv"
            external.write_bytes(daily.read_bytes())
            daily.unlink()
            os.link(external, daily)

            with self.assertRaisesRegex(QDataSnapshotError, "hard link"):
                verify_qdata_snapshot(root)

    def test_unknown_schema_extra_and_missing_files_fail_closed(self) -> None:
        cases = ("schema", "extra", "missing")
        for case in cases:
            with self.subTest(case=case), _snapshot_copy() as root:
                if case == "schema":
                    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
                    manifest["schema_version"] = "research_snapshot_v2"
                    _write_canonical_manifest(root, manifest, refresh_snapshot_id=False)
                elif case == "extra":
                    (root / "unexpected.csv").write_text("unexpected\n", encoding="utf-8")
                else:
                    (root / "tradability.csv").unlink()

                with self.assertRaises(QDataSnapshotError):
                    verify_qdata_snapshot(root)

    def test_noncanonical_manifest_values_and_metadata_types_fail_closed(self) -> None:
        cases = ("source_whitespace", "boolean_error_count", "float_row_count")
        for case in cases:
            with self.subTest(case=case), _snapshot_copy() as root:
                manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
                if case == "source_whitespace":
                    manifest["source"] = " deterministic_synthetic_fixture "
                elif case == "boolean_error_count":
                    manifest["quality_status"]["error_count"] = False
                else:
                    manifest["datasets"]["security_membership"]["row_count"] = 2.0
                _write_canonical_manifest(root, manifest, refresh_snapshot_id=True)

                with self.assertRaises(QDataSnapshotError):
                    verify_qdata_snapshot(root)

    def test_verifier_accepts_qdata_canonical_scientific_decimal(self) -> None:
        with _snapshot_copy() as root:
            def large_exact_amount(rows):
                rows[0]["amount"] = "1e5000"
                return rows

            _edit_csv(root, "daily_bar", large_exact_amount)

            manifest = verify_qdata_snapshot(root)

        self.assertTrue(str(manifest["snapshot_id"]).startswith("sha256:"))

    def test_duplicate_keys_and_column_drift_fail_closed_even_when_resigned(self) -> None:
        cases = ("duplicate", "column")
        for case in cases:
            with self.subTest(case=case), _snapshot_copy() as root:
                if case == "duplicate":
                    _edit_csv(root, "tradability", lambda rows: rows + [dict(rows[0])])
                else:
                    _edit_csv(
                        root,
                        "daily_bar",
                        lambda rows: [{**row, "unknown_price": "1"} for row in rows],
                        fieldnames=None,
                    )

                with self.assertRaises(QDataSnapshotError):
                    load_qdata_snapshot(root)

    def test_naive_late_and_pre_close_availability_fail_closed_when_resigned(self) -> None:
        cases = {
            "naive": ("tradability", "available_at", "2024-01-02T09:15:00"),
            "late": ("tradability", "available_at", "2024-06-01T01:15:00Z"),
            "pre_close": ("daily_bar", "available_at", "2024-01-02T06:59:00Z"),
        }
        for case, (dataset, field, value) in cases.items():
            with self.subTest(case=case), _snapshot_copy() as root:
                def mutate(rows):
                    rows[0][field] = value
                    return rows

                _edit_csv(root, dataset, mutate)

                with self.assertRaises(QDataSnapshotError):
                    load_qdata_snapshot(root)

    def test_cross_table_key_membership_and_critical_constraints_fail_closed(self) -> None:
        cases = ("key", "coverage", "membership_late", "limit", "can_buy")
        for case in cases:
            with self.subTest(case=case), _snapshot_copy() as root:
                if case == "key":
                    _edit_csv(root, "tradability", lambda rows: rows[1:])
                elif case == "coverage":
                    def expire(rows):
                        rows[0]["valid_to"] = "2024-01-03"
                        return rows
                    _edit_csv(root, "security_membership", expire)
                elif case == "membership_late":
                    def delay(rows):
                        rows[0]["available_at"] = "2024-01-02T08:00:00Z"
                        return rows
                    _edit_csv(root, "security_membership", delay)
                elif case == "limit":
                    def remove_limit(rows):
                        rows[2]["limit_up"] = ""
                        return rows
                    _edit_csv(root, "tradability", remove_limit)
                else:
                    def contradict(rows):
                        rows[3]["can_buy"] = "true"
                        return rows
                    _edit_csv(root, "tradability", contradict)

                with self.assertRaises(QDataSnapshotError):
                    load_qdata_snapshot(root)

    def test_fundamental_field_cannot_overwrite_raw_execution_columns(self) -> None:
        with _snapshot_copy() as root:
            def collide(rows):
                for row in rows:
                    row["field_name"] = "open"
                return rows

            _edit_csv(root, "fundamental_pit", collide)

            with self.assertRaisesRegex(QDataSnapshotError, "collides"):
                load_qdata_snapshot(root)


def _row(data: pd.DataFrame, symbol: str, date: str) -> pd.Series:
    return data[(data["symbol"] == symbol) & (data["date"] == pd.Timestamp(date))].iloc[0]


class _snapshot_copy:
    def __enter__(self) -> Path:
        self._temporary = tempfile.TemporaryDirectory()
        root = Path(self._temporary.name) / "snapshot"
        shutil.copytree(FIXTURE, root)
        return root

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._temporary.cleanup()


def _edit_csv(root: Path, dataset: str, mutate, fieldnames: list[str] | None | object = ()) -> None:
    path = root / f"{dataset}.csv"
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        original_fields = list(reader.fieldnames or [])
        rows = mutate(list(reader))
    if fieldnames == ():
        output_fields = original_fields
    elif fieldnames is None:
        output_fields = list(rows[0])
    else:
        output_fields = fieldnames
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=output_fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path.write_bytes(output.getvalue().encode("utf-8"))
    _resign_dataset(root, dataset, output_fields, rows)


def _resign_dataset(root: Path, dataset: str, columns: list[str], rows: list[dict[str, str]]) -> None:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    metadata = manifest["datasets"][dataset]
    date_field = metadata["date_field"]
    dates = [row[date_field] for row in rows]
    metadata["columns"] = columns
    metadata["row_count"] = len(rows)
    metadata["date_range"] = {"start": min(dates), "end": max(dates)}
    metadata["sha256"] = hashlib.sha256((root / f"{dataset}.csv").read_bytes()).hexdigest()
    _write_canonical_manifest(root, manifest, refresh_snapshot_id=True)


def _write_canonical_manifest(root: Path, manifest: dict[str, object], *, refresh_snapshot_id: bool) -> None:
    if refresh_snapshot_id:
        without_id = dict(manifest)
        without_id.pop("snapshot_id", None)
        payload = _canonical_json(without_id)
        manifest["snapshot_id"] = "sha256:" + hashlib.sha256(payload).hexdigest()
    (root / "manifest.json").write_bytes(_canonical_json(manifest))


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


if __name__ == "__main__":
    unittest.main()
