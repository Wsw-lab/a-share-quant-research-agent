from __future__ import annotations

import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from a_share_quant_agent.confirmatory_study import (
    ConfirmatoryStudyError,
    STAGE2_AUTHORIZATION_CONSUMPTION_SUFFIX,
    _canonical_bytes,
    consume_stage2_execution_authorization,
    run_stage2_confirmatory_study,
    verify_stage2_execution_authorization_consumption,
)


class AuthorizationConsumptionTest(unittest.TestCase):
    """Pure lifecycle tests; they never load quotes or execute Stage-2 cells."""

    @staticmethod
    def _write_authorization(root: Path) -> tuple[Path, dict[str, object]]:
        study_id = "a-share-factor-timing-bias-decomposition-v2"
        code_commit = "a" * 40
        plan_core_sha256 = "b" * 64
        plan: dict[str, object] = {
            "study_id": study_id,
            "locked_at": "2026-08-31T00:00:00+00:00",
            "runner_scope": "ic_core_only",
            "test_period": ["2010-01-01", "2022-12-31"],
            "code_commit": code_commit,
            "external_registration": {
                "registered_content_sha256": plan_core_sha256,
            },
        }
        authorization: dict[str, object] = {
            "schema_version": "stage2_execution_authorization_v1",
            "study_id": study_id,
            "status": "authorized",
            "authorized_at": plan["locked_at"],
            "plan_core_sha256": plan_core_sha256,
            "release_scope": {
                "authorized_runner_scope": "ic_core_only",
                "authorized_analysis_period": ["2010-01-01", "2022-12-31"],
                "authorized_code_commit": code_commit,
            },
        }
        path = root / "execution_authorization.json"
        path.write_bytes(_canonical_bytes(authorization))
        return path, plan

    def test_exclusive_sidecar_is_created_and_second_claim_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authorization_path, plan = self._write_authorization(root)
            consumption_dir = root / "private-consumption-store"
            metadata = consume_stage2_execution_authorization(
                authorization_path,
                plan=plan,
                code_revision=str(plan["code_commit"]),
                consumption_dir=consumption_dir,
                consumed_at="2026-09-01T00:01:00+00:00",
            )

            sidecar_path = consumption_dir / metadata["filename"]
            self.assertTrue(sidecar_path.is_file())
            self.assertEqual(
                sidecar_path.stat().st_mode & 0o777,
                0o600,
            )
            self.assertEqual(
                sidecar_path.name,
                f"{metadata['record']['authorization_sha256']}{STAGE2_AUTHORIZATION_CONSUMPTION_SUFFIX}",
            )
            # The sidecar carries only hashes/scope/timestamps; no licensed
            # input path, row, or outcome value is released at this boundary.
            self.assertNotIn("quotes_path", metadata["record"])
            self.assertNotIn("fundamentals_path", metadata["record"])

            verified = verify_stage2_execution_authorization_consumption(
                authorization_path,
                sidecar_path,
                plan=plan,
                expected_metadata=metadata,
            )
            self.assertEqual(verified, metadata)

            with self.assertRaisesRegex(
                ConfirmatoryStudyError,
                "already been consumed",
            ):
                consume_stage2_execution_authorization(
                    authorization_path,
                    plan=plan,
                    code_revision=str(plan["code_commit"]),
                    consumption_dir=consumption_dir,
                    consumed_at="2026-09-01T00:02:00+00:00",
                )

    def test_private_sidecar_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authorization_path, plan = self._write_authorization(root)
            consumption_dir = root / "private-consumption-store"
            metadata = consume_stage2_execution_authorization(
                authorization_path,
                plan=plan,
                code_revision=str(plan["code_commit"]),
                consumption_dir=consumption_dir,
                consumed_at="2026-09-01T00:01:00+00:00",
            )
            sidecar_path = consumption_dir / metadata["filename"]
            tampered = json.loads(sidecar_path.read_text(encoding="utf-8"))
            tampered["status"] = "authorized"
            sidecar_path.write_bytes(_canonical_bytes(tampered))

            with self.assertRaisesRegex(
                ConfirmatoryStudyError,
                "authorization consumption record is invalid",
            ):
                verify_stage2_execution_authorization_consumption(
                    authorization_path,
                    sidecar_path,
                    plan=plan,
                )

    def test_write_failure_leaves_claim_marker_and_blocks_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authorization_path, plan = self._write_authorization(root)
            consumption_dir = root / "private-consumption-store"
            with patch(
                "a_share_quant_agent.confirmatory_study.os.fsync",
                side_effect=OSError("simulated durable-write failure"),
            ):
                with self.assertRaisesRegex(
                    ConfirmatoryStudyError,
                    "sidecar could not be created",
                ):
                    consume_stage2_execution_authorization(
                        authorization_path,
                        plan=plan,
                        code_revision=str(plan["code_commit"]),
                        consumption_dir=consumption_dir,
                        consumed_at="2026-09-01T00:01:00+00:00",
                    )

            markers = list(consumption_dir.glob("*.consumed.json"))
            self.assertEqual(len(markers), 1)
            with self.assertRaisesRegex(ConfirmatoryStudyError, "already been consumed"):
                consume_stage2_execution_authorization(
                    authorization_path,
                    plan=plan,
                    code_revision=str(plan["code_commit"]),
                    consumption_dir=consumption_dir,
                    consumed_at="2026-09-01T00:02:00+00:00",
                )

    def test_runner_consumes_authorization_at_outcome_release_boundary(self) -> None:
        source = inspect.getsource(run_stage2_confirmatory_study)
        binding_check = source.index("_validate_stage2_research_bindings(")
        consumption = source.index("consume_stage2_execution_authorization(")
        outcome_loaders = (
            source.index("quotes = _load_quotes("),
            source.index("official_calendar = _load_official_calendar("),
            source.index("stock_master = _load_stock_master("),
            source.index("fundamentals = _load_stage2_fundamentals("),
        )

        self.assertLess(binding_check, consumption)
        self.assertTrue(all(consumption < index for index in outcome_loaders))

    def test_authorization_and_sidecar_symlinks_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authorization_path, plan = self._write_authorization(root)
            authorization_link = root / "authorization-link.json"
            authorization_link.symlink_to(authorization_path)
            with self.assertRaisesRegex(ConfirmatoryStudyError, "not a regular file"):
                consume_stage2_execution_authorization(
                    authorization_link,
                    plan=plan,
                    code_revision=str(plan["code_commit"]),
                    consumed_at="2026-09-01T00:01:00+00:00",
                )


if __name__ == "__main__":
    unittest.main()
