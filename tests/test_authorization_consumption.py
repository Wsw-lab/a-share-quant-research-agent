from __future__ import annotations

import hashlib
import io
import inspect
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from a_share_quant_agent.confirmatory_study import (
    ConfirmatoryStudyError,
    STAGE2_AUTHORIZATION_CONSUMPTION_SUFFIX,
    _assert_stage2_private_directory_outside_worktrees,
    _bytes_evidence,
    _canonical_bytes,
    _git_repository_root,
    _load_stage2_quotes,
    _require_stage2_no_bytecode_invocation,
    consume_stage2_execution_authorization,
    main as confirmatory_main,
    run_stage2_confirmatory_study,
    _run_stage2_registered_cells,
    verify_stage2_execution_authorization_consumption,
)
from a_share_quant_agent.private_artifact_paths import (
    PrivateArtifactPathError,
    containing_git_worktree,
    publish_private_directory_atomic_exclusive,
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

    def test_stage2_cli_requires_bytecode_suppression_from_startup(self) -> None:
        with patch.object(sys, "dont_write_bytecode", False):
            with self.assertRaisesRegex(
                ConfirmatoryStudyError,
                "PYTHONDONTWRITEBYTECODE=1 and python3 -B",
            ):
                _require_stage2_no_bytecode_invocation()
        with patch.object(sys, "dont_write_bytecode", True):
            _require_stage2_no_bytecode_invocation()

        required_options = (
            "plan", "quotes", "stock-master", "fundamentals", "official-calendar",
            "data-declaration", "data-rights-attestation", "coverage-report",
            "coverage-probe-spec", "coverage-probe-receipt", "review-attestation",
            "design-manifest", "registration-receipt", "execution-authorization",
            "protocol-source", "statistical-analysis-plan",
            "prior-specification-inventory", "prior-exposure-log",
            "prior-exposure-attestation", "code-revision", "output-dir",
            "authorization-consumption-dir",
        )
        argv = ["run-stage2"]
        for option in required_options:
            argv.extend((f"--{option}", "unused"))
        with patch.object(sys, "dont_write_bytecode", False), patch(
            "a_share_quant_agent.confirmatory_study.run_stage2_confirmatory_study"
        ) as runner:
            with self.assertRaisesRegex(
                ConfirmatoryStudyError,
                "PYTHONDONTWRITEBYTECODE=1 and python3 -B",
            ):
                confirmatory_main(argv)
            runner.assert_not_called()

    def test_result_publication_never_replaces_a_racing_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = root / ".staged-result"
            destination = root / "result"
            staging.mkdir()
            (staging / "receipt.json").write_text("complete\n", encoding="utf-8")

            # The destination was absent at the caller's precheck, but a
            # competing process wins the name immediately before publication.
            self.assertFalse(destination.exists())
            destination.mkdir()
            destination_identity = destination.stat().st_ino
            with self.assertRaisesRegex(
                PrivateArtifactPathError,
                "already exists",
            ):
                publish_private_directory_atomic_exclusive(
                    staging,
                    destination,
                    label="Stage-2 output directory",
                )

            self.assertEqual(destination.stat().st_ino, destination_identity)
            self.assertEqual(list(destination.iterdir()), [])
            self.assertEqual(
                (staging / "receipt.json").read_text(encoding="utf-8"),
                "complete\n",
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

    def test_finite_rights_must_be_active_at_authorization_consumption(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authorization_path, plan = self._write_authorization(root)
            consumption_dir = root / "private-consumption-store"

            with self.assertRaisesRegex(
                ConfirmatoryStudyError,
                "data rights contract expired before authorization consumption",
            ):
                consume_stage2_execution_authorization(
                    authorization_path,
                    plan=plan,
                    code_revision=str(plan["code_commit"]),
                    consumption_dir=consumption_dir,
                    consumed_at="2026-09-01T00:01:00+00:00",
                    rights_contract_expiry_at="2026-09-01T00:00:00+00:00",
                )

            self.assertFalse(consumption_dir.exists())

            metadata = consume_stage2_execution_authorization(
                authorization_path,
                plan=plan,
                code_revision=str(plan["code_commit"]),
                consumption_dir=consumption_dir,
                consumed_at="2026-09-01T00:01:00+00:00",
                rights_contract_expiry_at="2026-09-01T00:02:00+00:00",
            )
            self.assertTrue((consumption_dir / metadata["filename"]).is_file())

    def test_stage2_loader_uses_the_captured_bytes_not_a_replaced_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "quotes.csv"
            captured = (
                b"date,symbol,close_raw,adjustment_factor,close,price_adjustment_method,price_adjustment_convention,close_observation_type,amount,amount_unit,is_st,is_suspended\n"
                b"2020-01-02,000001.SZ,10.5,1,10.5,close_equals_close_raw_times_adjustment_factor,provider_cumulative_backward_adjusted_hfq_no_rebasing,traded_close,1000000,CNY,false,false\n"
            )
            path.write_bytes(captured)
            path.write_text("replaced,path\n", encoding="utf-8")

            frame = _load_stage2_quotes(path, raw_csv=captured)

            self.assertEqual(len(frame), 1)
            self.assertEqual(frame.loc[0, "symbol"], "000001.SZ")
            self.assertEqual(_bytes_evidence(captured)["size_bytes"], len(captured))

    def test_runner_rejects_private_targets_in_current_worktree_before_claim(self) -> None:
        from tests.test_confirmatory_study import (
            _bind_stage2_gate_artifacts,
            _stage2_plan,
            _write_fixture,
        )

        repository_root = _git_repository_root().resolve()
        forbidden_output = repository_root / ".stage2-private-output-test"
        forbidden_consumption = repository_root / ".stage2-private-consumption-test"
        self.assertFalse(forbidden_output.exists())
        self.assertFalse(forbidden_consumption.exists())

        for target in ("output", "consumption"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                paths = _bind_stage2_gate_artifacts(
                    _write_fixture(root, source_classification="synthetic_fixture"),
                    _stage2_plan(),
                )
                output = root / "external-output"
                if target == "output":
                    output = forbidden_output
                else:
                    paths["authorization_consumption_dir"] = forbidden_consumption
                marker_dir = Path(paths["authorization_consumption_dir"])

                with self.assertRaisesRegex(
                    ConfirmatoryStudyError,
                    "must be outside every Git worktree",
                ):
                    run_stage2_confirmatory_study(**paths, output_dir=output)

                self.assertFalse(output.exists())
                self.assertFalse(marker_dir.exists())
                self.assertFalse(forbidden_output.exists())
                self.assertFalse(forbidden_consumption.exists())

    def test_any_independent_or_linked_worktree_is_forbidden_but_external_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
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
                    "user.name=Stage2 Fixture",
                    "-c",
                    "user.email=stage2-fixture@example.test",
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

            self.assertEqual(
                containing_git_worktree(repository / "private-output"),
                repository.resolve(),
            )
            self.assertEqual(
                containing_git_worktree(linked / "private-output"),
                linked.resolve(),
            )
            for worktree in (repository, linked):
                with self.subTest(worktree=worktree), self.assertRaisesRegex(
                    ConfirmatoryStudyError,
                    "must be outside every Git worktree",
                ):
                    _assert_stage2_private_directory_outside_worktrees(
                        worktree / "private-output",
                        label="output directory",
                    )
            _assert_stage2_private_directory_outside_worktrees(
                root / "external-private-output",
                label="output directory",
            )

    def test_runner_requires_explicit_authorization_consumption_directory(self) -> None:
        from tests.test_confirmatory_study import (
            _bind_stage2_gate_artifacts,
            _stage2_plan,
            _write_fixture,
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = _bind_stage2_gate_artifacts(
                _write_fixture(root, source_classification="synthetic_fixture"),
                _stage2_plan(),
            )
            paths.pop("authorization_consumption_dir")
            output = root / "out"

            with self.assertRaisesRegex(
                TypeError,
                "authorization_consumption_dir",
            ):
                run_stage2_confirmatory_study(**paths, output_dir=output)

            self.assertFalse(output.exists())
            self.assertFalse((root / "private-consumption-store").exists())

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
        raw_capture = source.index("raw_input_bytes = {")
        post_consumption_expiry_check = source.index(
            "_assert_stage2_rights_active(", consumption
        )
        raw_coverage_recomputation = source.index("_validate_stage2_data_bindings(")
        outcome_loaders = (
            source.index("quotes = _load_stage2_quotes("),
            source.index("official_calendar = _load_official_calendar("),
            source.index("stock_master = _load_stock_master("),
            source.index("fundamentals = _load_stage2_fundamentals("),
        )
        pre_staging_expiry_check = source.index(
            "_assert_stage2_rights_active(", source.index("payload = _canonical_bytes(")
        )
        receipt_staging = source.index("staging = Path(tempfile.mkdtemp(")
        final_receipt_expiry_check = source.rindex("_assert_stage2_rights_active(")
        receipt_publication = source.index(
            "publish_private_directory_atomic_exclusive("
        )

        self.assertLess(binding_check, consumption)
        self.assertLess(consumption, post_consumption_expiry_check)
        self.assertLess(consumption, raw_capture)
        self.assertLess(raw_capture, raw_coverage_recomputation)
        self.assertLess(post_consumption_expiry_check, raw_coverage_recomputation)
        self.assertLess(consumption, raw_coverage_recomputation)
        self.assertTrue(all(consumption < index for index in outcome_loaders))
        self.assertLess(pre_staging_expiry_check, receipt_staging)
        self.assertLess(receipt_staging, final_receipt_expiry_check)
        self.assertLess(final_receipt_expiry_check, receipt_publication)

        cell_source = inspect.getsource(_run_stage2_registered_cells)
        self.assertIn("rights_contract_expiry_at", cell_source)
        self.assertGreaterEqual(
            cell_source.count("_assert_stage2_rights_active("),
            2,
        )

    def test_raw_inputs_are_opened_once_only_after_consumption_and_mismatch_burns_claim(
        self,
    ) -> None:
        from tests.test_confirmatory_study import (
            _bind_stage2_gate_artifacts,
            _stage2_plan,
            _write_fixture,
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = _bind_stage2_gate_artifacts(
                _write_fixture(root, source_classification="synthetic_fixture"),
                _stage2_plan(),
            )
            # Change one sealed input after every control artifact was bound.
            # The registered runner must consume first, capture all four inputs
            # once, then reject these changed bytes without publishing a result.
            quotes_path = Path(paths["quotes_path"])
            quotes_path.write_bytes(quotes_path.read_bytes() + b"\n")

            consumption_dir = root / "private-consumption-store"
            paths["authorization_consumption_dir"] = consumption_dir
            output = root / "out"
            raw_paths = {
                Path(paths[f"{role}_path"]).resolve(): role
                for role in (
                    "quotes",
                    "stock_master",
                    "fundamentals",
                    "official_calendar",
                )
            }
            reads = {role: [] for role in raw_paths.values()}
            real_open = Path.open

            def audited_open(candidate: Path, *args: object, **kwargs: object):
                role = raw_paths.get(candidate.resolve())
                if role is not None:
                    reads[role].append(
                        bool(
                            list(
                                consumption_dir.glob(
                                    f"*{STAGE2_AUTHORIZATION_CONSUMPTION_SUFFIX}"
                                )
                            )
                        )
                    )
                return real_open(candidate, *args, **kwargs)

            with patch.object(Path, "open", new=audited_open):
                with self.assertRaisesRegex(
                    ConfirmatoryStudyError,
                    "captured raw-input bytes differ from the registered input hashes",
                ):
                    run_stage2_confirmatory_study(
                        **paths,
                        output_dir=output,
                    )

            self.assertEqual(
                reads,
                {
                    "quotes": [True],
                    "stock_master": [True],
                    "fundamentals": [True],
                    "official_calendar": [True],
                },
            )
            self.assertEqual(
                len(
                    list(
                        consumption_dir.glob(
                            f"*{STAGE2_AUTHORIZATION_CONSUMPTION_SUFFIX}"
                        )
                    )
                ),
                1,
            )
            self.assertFalse(output.exists())

    def test_review_and_prior_exposure_use_one_captured_snapshot_for_parse_and_hash(
        self,
    ) -> None:
        from tests.test_confirmatory_study import (
            _bind_stage2_gate_artifacts,
            _stage2_plan,
            _write_fixture,
        )

        attacks = (
            (
                "review_attestation_path",
                "reviewer",
                "unbound-but-well-formed-reviewer",
                "review_attestation_sha256 differs",
            ),
            (
                "prior_exposure_attestation_path",
                "attestor",
                "unbound-but-well-formed-owner",
                "prior_exposure_attestation_sha256 differs",
            ),
        )
        for path_key, field, replacement, expected_error in attacks:
            with self.subTest(path_key=path_key), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                paths = _bind_stage2_gate_artifacts(
                    _write_fixture(root, source_classification="synthetic_fixture"),
                    _stage2_plan(),
                )
                target = Path(paths[path_key]).resolve()
                bound_bytes = target.read_bytes()
                unbound = json.loads(bound_bytes)
                unbound[field] = replacement
                unbound_bytes = _canonical_bytes(unbound)
                open_count = 0
                real_open = Path.open

                def attacked_open(
                    candidate: Path, *args: object, **kwargs: object
                ):
                    nonlocal open_count
                    if candidate.resolve() == target:
                        open_count += 1
                        if open_count == 1:
                            # Supply an unbound object to the capture while the
                            # path itself still contains the registered bytes.
                            # A parse-then-reopen implementation would parse
                            # this object and later hash different bytes.
                            return io.BytesIO(unbound_bytes)
                    return real_open(candidate, *args, **kwargs)

                consumption_dir = root / "private-consumption-store"
                paths["authorization_consumption_dir"] = consumption_dir
                with patch.object(Path, "open", new=attacked_open):
                    with self.assertRaisesRegex(
                        ConfirmatoryStudyError,
                        expected_error,
                    ):
                        run_stage2_confirmatory_study(
                            **paths,
                            output_dir=root / "out",
                        )

                self.assertEqual(open_count, 1)
                self.assertFalse(consumption_dir.exists())
                self.assertFalse((root / "out").exists())

    def test_consumption_uses_the_same_captured_authorization_after_path_swap(
        self,
    ) -> None:
        from tests.test_confirmatory_study import (
            _bind_stage2_gate_artifacts,
            _stage2_plan,
            _write_fixture,
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = _bind_stage2_gate_artifacts(
                _write_fixture(root, source_classification="synthetic_fixture"),
                _stage2_plan(),
            )
            authorization_path = Path(paths["execution_authorization_path"]).resolve()
            bound_authorization_bytes = authorization_path.read_bytes()
            swapped = json.loads(bound_authorization_bytes)
            swapped["authorizer"] = "post-capture-unbound-authorizer"
            swapped_bytes = _canonical_bytes(swapped)

            # Force a post-consumption stop so the test reaches the claim but
            # never executes cells or publishes a receipt.
            quotes_path = Path(paths["quotes_path"])
            quotes_path.write_bytes(quotes_path.read_bytes() + b"\n")
            consumption_dir = root / "private-consumption-store"
            paths["authorization_consumption_dir"] = consumption_dir
            real_open = Path.open
            authorization_open_count = 0

            def swap_after_capture(
                candidate: Path, *args: object, **kwargs: object
            ):
                nonlocal authorization_open_count
                if candidate.resolve() == authorization_path:
                    authorization_open_count += 1
                    if authorization_open_count == 1:
                        # The capture receives the registered bytes while the
                        # backing path is replaced.  Validation and atomic
                        # consumption must both continue from the snapshot.
                        with real_open(authorization_path, "wb") as handle:
                            handle.write(swapped_bytes)
                        return io.BytesIO(bound_authorization_bytes)
                return real_open(candidate, *args, **kwargs)

            with patch.object(Path, "open", new=swap_after_capture):
                with self.assertRaisesRegex(
                    ConfirmatoryStudyError,
                    "captured raw-input bytes differ from the registered input hashes",
                ):
                    run_stage2_confirmatory_study(
                        **paths,
                        output_dir=root / "out",
                    )

            expected_marker = consumption_dir / (
                hashlib.sha256(bound_authorization_bytes).hexdigest()
                + STAGE2_AUTHORIZATION_CONSUMPTION_SUFFIX
            )
            self.assertEqual(authorization_open_count, 1)
            self.assertTrue(expected_marker.is_file())
            self.assertFalse((root / "out").exists())

    def test_raw_coverage_or_panel_failure_remains_consumed(self) -> None:
        from tests.test_confirmatory_study import (
            _bind_stage2_gate_artifacts,
            _stage2_plan,
            _write_fixture,
        )

        failure_cases = (
            (
                "raw coverage recomputation",
                "_validate_stage2_data_bindings",
                "simulated raw coverage failure",
            ),
            (
                "quote panel load",
                "_load_stage2_quotes",
                "simulated quote load failure",
            ),
        )
        for label, target_name, message in failure_cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                paths = _bind_stage2_gate_artifacts(
                    _write_fixture(root, source_classification="synthetic_fixture"),
                    _stage2_plan(),
                )
                consumption_dir = root / "private-consumption-store"
                paths["authorization_consumption_dir"] = consumption_dir
                patches = []
                if target_name == "_load_stage2_quotes":
                    patches.append(
                        patch(
                            "a_share_quant_agent.confirmatory_study._validate_stage2_data_bindings"
                        )
                    )
                patches.append(
                    patch(
                        f"a_share_quant_agent.confirmatory_study.{target_name}",
                        side_effect=ConfirmatoryStudyError(message),
                    )
                )
                entered = []
                try:
                    for patcher in patches:
                        entered.append(patcher)
                        patcher.start()
                    with self.assertRaisesRegex(ConfirmatoryStudyError, message):
                        run_stage2_confirmatory_study(
                            **paths,
                            output_dir=root / "out",
                        )
                finally:
                    for patcher in reversed(entered):
                        patcher.stop()

                markers = list(consumption_dir.glob("*.consumed.json"))
                self.assertEqual(len(markers), 1)

    def test_registration_chain_failure_does_not_consume_authorization(self) -> None:
        from tests.test_confirmatory_study import (
            _bind_stage2_gate_artifacts,
            _stage2_plan,
            _write_fixture,
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = _bind_stage2_gate_artifacts(
                _write_fixture(root, source_classification="synthetic_fixture"),
                _stage2_plan(),
            )
            registration_path = paths["registration_receipt_path"]
            registration_path.write_bytes(registration_path.read_bytes() + b" ")
            consumption_dir = root / "private-consumption-store"
            paths["authorization_consumption_dir"] = consumption_dir

            with self.assertRaisesRegex(
                ConfirmatoryStudyError,
                "registration receipt hash differs",
            ):
                run_stage2_confirmatory_study(
                    **paths,
                    output_dir=root / "out",
                )

            self.assertFalse(consumption_dir.exists())

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
