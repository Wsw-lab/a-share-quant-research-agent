from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import a_share_quant_agent.coverage_probe as coverage_probe
from a_share_quant_agent.coverage_probe import (
    AKSHARE_VERSION,
    DATES,
    EXACT_DATE_ADAPTER,
    GATE_IDS,
    PROBE_ID,
    PRIVATE_MANIFEST_SCHEMA_VERSION,
    PYTHON_VERSION,
    QDATA_COMMIT,
    RAW_SCHEMA_SHA256,
    REQUEST_LOG_SCHEMA_SHA256,
    RECEIPT_SCHEMA_VERSION,
    RIGHTS_REVIEW_SCHEMA_VERSION,
    STUDY_ID,
    SYMBOLS,
    TIMESTAMP_TRUST_BOUNDARY,
    V1_SPEC_SHA256,
    CoverageProbeError,
    ExactDateAkShareProbeAdapter,
    canonical_json_bytes,
    main,
    _normalise_bar,
    _validate_rights_review,
    _validate_inventory_shape,
    _validate_public_receipt_privacy,
    _validate_timestamp_package,
    sha256_bytes,
    validate_external_timestamp_proof,
    verify_probe_artifacts,
)
from a_share_quant_agent.public_receipt_privacy import (
    credential_like_public_key,
    public_string_privacy_reason,
)


class CoverageProbeContractTest(unittest.TestCase):
    def _verified_probe_rights(
        self,
        *,
        proof_sha256: str = "7" * 64,
        expiry: str | None = "2026-12-31T23:59:59+00:00",
    ) -> dict[str, object]:
        return {
            "schema_version": RIGHTS_REVIEW_SCHEMA_VERSION,
            "status": "verified",
            "reviewed_at_utc": "2026-08-31T13:10:00+00:00",
            "reviewer": "Fixture rights reviewer",
            "authority_basis": "Provider contract and written permission record",
            "approved_timestamp_proof_sha256": proof_sha256,
            "contract_effective_at": "2026-01-01T00:00:00+00:00",
            "contract_expiry_at": expiry,
            "contract_has_no_expiry_confirmed": expiry is None,
            "post_expiry_private_probe_artifact_retention_allowed": (
                expiry is not None
            ),
            "post_expiry_aggregate_receipt_and_metadata_publication_allowed": (
                expiry is not None
            ),
            "post_expiry_survival_evidence_sha256": (
                "6" * 64 if expiry is not None else None
            ),
            "local_storage_allowed": True,
            "aggregate_receipt_publication_allowed": True,
            "aggregate_coverage_publication_allowed": True,
            "artifact_hash_publication_allowed": True,
            "artifact_filename_publication_allowed": True,
            "artifact_size_publication_allowed": True,
            "artifact_row_count_publication_allowed": True,
            "artifact_symbol_count_and_date_range_publication_allowed": True,
            "timestamp_provider_and_identifier_publication_allowed": True,
            "timestamp_evidence_hash_publication_allowed": True,
            "timestamp_verifier_identity_publication_allowed": True,
            "timestamp_verification_uri_publication_allowed": True,
            "request_route_metadata_publication_allowed": True,
            "raw_redistribution_allowed": False,
            "scope": ["fixed_symbol_probe"],
            "evidence_sha256": "8" * 64,
            "statement": (
                "The exact proof and contract authorize the bounded private probe and "
                "the separately enumerated aggregate receipt metadata."
            ),
        }

    def test_probe_rights_review_is_exact_proof_bound_and_active(self) -> None:
        checkpoint = datetime(2026, 9, 1, tzinfo=timezone.utc)
        finite = self._verified_probe_rights()
        validated = _validate_rights_review(
            finite,
            timestamp_proof_sha256="7" * 64,
            active_at=checkpoint,
            phase="probe preflight",
        )
        self.assertEqual(
            validated["approved_timestamp_proof_sha256"], "7" * 64
        )

        no_expiry = self._verified_probe_rights(expiry=None)
        _validate_rights_review(
            no_expiry,
            timestamp_proof_sha256="7" * 64,
            active_at=checkpoint,
            phase="receipt publication",
        )

        cases = []
        missing_hash = self._verified_probe_rights()
        missing_hash.pop("approved_timestamp_proof_sha256")
        cases.append(("missing proof hash", missing_hash, "incomplete", "7" * 64))
        cases.append(
            (
                "proof substitution",
                self._verified_probe_rights(),
                "exact timestamp proof bytes",
                "9" * 64,
            )
        )
        expired = self._verified_probe_rights(expiry="2026-08-31T23:59:59+00:00")
        cases.append(("expired contract", expired, "expired", "7" * 64))
        future_effective = self._verified_probe_rights()
        future_effective["contract_effective_at"] = "2026-09-02T00:00:00+00:00"
        cases.append(("future effective", future_effective, "not effective", "7" * 64))
        ambiguous_null = self._verified_probe_rights(expiry=None)
        ambiguous_null["contract_has_no_expiry_confirmed"] = False
        cases.append(("ambiguous null", ambiguous_null, "no-expiry", "7" * 64))
        inconsistent_finite = self._verified_probe_rights()
        inconsistent_finite["contract_has_no_expiry_confirmed"] = True
        cases.append(("inconsistent finite", inconsistent_finite, "finite", "7" * 64))
        finite_missing_retention = self._verified_probe_rights()
        finite_missing_retention[
            "post_expiry_private_probe_artifact_retention_allowed"
        ] = False
        cases.append(
            (
                "finite missing private retention",
                finite_missing_retention,
                "post-expiry private retention",
                "7" * 64,
            )
        )
        finite_missing_publication = self._verified_probe_rights()
        finite_missing_publication[
            "post_expiry_aggregate_receipt_and_metadata_publication_allowed"
        ] = False
        cases.append(
            (
                "finite missing continued publication",
                finite_missing_publication,
                "continued aggregate receipt publication",
                "7" * 64,
            )
        )
        finite_missing_survival_evidence = self._verified_probe_rights()
        finite_missing_survival_evidence["post_expiry_survival_evidence_sha256"] = None
        cases.append(
            (
                "finite missing survival evidence",
                finite_missing_survival_evidence,
                "hash-evidenced post-expiry",
                "7" * 64,
            )
        )
        no_expiry_with_survival_claim = self._verified_probe_rights(expiry=None)
        no_expiry_with_survival_claim[
            "post_expiry_private_probe_artifact_retention_allowed"
        ] = True
        no_expiry_with_survival_claim[
            "post_expiry_aggregate_receipt_and_metadata_publication_allowed"
        ] = True
        no_expiry_with_survival_claim["post_expiry_survival_evidence_sha256"] = "6" * 64
        cases.append(
            (
                "no-expiry with contradictory survival clause",
                no_expiry_with_survival_claim,
                "must not assert a post-expiry",
                "7" * 64,
            )
        )
        naive = self._verified_probe_rights()
        naive["contract_expiry_at"] = "2026-12-31T23:59:59"
        cases.append(("naive expiry", naive, "UTC offset", "7" * 64))

        for label, rights, pattern, proof_sha in cases:
            with self.subTest(label=label), self.assertRaisesRegex(
                CoverageProbeError, pattern
            ):
                _validate_rights_review(
                    rights,
                    timestamp_proof_sha256=proof_sha,
                    active_at=checkpoint,
                    phase="probe preflight",
                )

    def test_run_revalidates_rights_before_request_and_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec_path = root / "spec.json"
            inventory_path = root / "inventory.json"
            package_path = root / "package.json"
            proof_path = root / "proof.json"
            rights_path = root / "rights.json"
            qdata_path = root / "qdata"
            output_path = root / "private-probe"
            qdata_path.mkdir()
            spec_path.write_bytes(b"{}\n")
            inventory_path.write_bytes(b"{}\n")
            spec_sha = sha256_bytes(spec_path.read_bytes())
            inventory_sha = sha256_bytes(inventory_path.read_bytes())
            agent_commit = "c" * 40
            package = {
                "schema_version": "stage2_coverage_probe_timestamp_package_v1",
                "study_id": STUDY_ID,
                "probe_id": PROBE_ID,
                "spec_path": (
                    "studies/pit_factor_bias_decomposition_v2/"
                    "coverage_probe_spec.v2.json"
                ),
                "spec_sha256": spec_sha,
                "prior_specification_inventory_path": (
                    "studies/pit_factor_bias_decomposition_v2/"
                    "prior_specification_inventory.json"
                ),
                "prior_specification_inventory_sha256": inventory_sha,
                "agent_commit": agent_commit,
            }
            package_path.write_bytes(canonical_json_bytes(package))
            package_sha = sha256_bytes(package_path.read_bytes())
            proof = {
                "type": "human_verified_external_timestamp",
                "provider": "Fixture registry",
                "identifier": "fixture-record-1",
                "timestamped_at_utc": "2026-01-01T00:00:00+00:00",
                "verification_uri": "https://example.invalid/fixture-record-1",
                "evidence_sha256": "a" * 64,
                "subject_type": "coverage_probe_package_manifest_sha256",
                "subject_sha256": package_sha,
                "verifier": "Independent fixture reviewer",
                "verified_at_utc": "2026-01-01T00:05:00+00:00",
                "trust_boundary": TIMESTAMP_TRUST_BOUNDARY,
            }
            proof_path.write_bytes(canonical_json_bytes(proof))
            rights = self._verified_probe_rights(
                proof_sha256=sha256_bytes(proof_path.read_bytes()),
                expiry="2099-12-31T23:59:59+00:00",
            )
            rights["contract_effective_at"] = "2025-01-01T00:00:00+00:00"
            rights_path.write_bytes(canonical_json_bytes(rights))
            preflight = {
                "status": "READY",
                "blocking_reason_codes": [],
                "spec_sha256": spec_sha,
                "inventory_sha256": inventory_sha,
                "timestamp_package_sha256": package_sha,
                "timestamp_proof_sha256": sha256_bytes(proof_path.read_bytes()),
                "rights_review_sha256": sha256_bytes(rights_path.read_bytes()),
                "agent_commit": agent_commit,
                "qdata_commit": QDATA_COMMIT,
                "agent_clean": True,
                "qdata_clean": True,
                "runtime_contract": {
                    "actual": {
                        "python_version": PYTHON_VERSION,
                        "akshare_version": AKSHARE_VERSION,
                    }
                },
                "gates": {
                    "SPEC_COMMITTED": True,
                    "SPEC_EXTERNALLY_TIMESTAMPED": True,
                    "CODE_STATE_CLEAN_AND_BOUND": True,
                    "OUTPUT_TARGET_NEW": True,
                    "RIGHTS_REVIEW_RECORDED": True,
                },
            }
            provider = object.__new__(ExactDateAkShareProbeAdapter)

            def fetch_daily_market(*, trade_date: str, symbols: list[str]):
                symbol = symbols[0]
                return {
                    "provider": "eastmoney.com",
                    "route_evidence": {
                        "requested_https_host": "push2his.eastmoney.com",
                        "final_https_host": "push2his.eastmoney.com",
                        "endpoint_path": "/api/qt/stock/kline/get",
                        "redirect_count": 0,
                        "exact_single_date": True,
                        "fallback_attempted": False,
                        "lookback_applied": False,
                    },
                    "daily_bars": [{
                        "symbol": symbol,
                        "trade_date": trade_date,
                        "open": 10.0,
                        "high": 11.0,
                        "low": 9.0,
                        "close": 10.5,
                        "volume": 1000.0,
                        "amount": 10000.0,
                    }],
                }

            original_validate = coverage_probe._validate_rights_review
            original_publish = (
                coverage_probe.publish_private_directory_atomic_exclusive
            )
            with mock.patch.object(
                coverage_probe, "preflight_probe", return_value=preflight
            ), mock.patch.object(
                coverage_probe,
                "_verify_qdata_checkout",
                return_value=(qdata_path, True),
            ), mock.patch.object(
                coverage_probe, "_git_root", return_value=root
            ), mock.patch.object(
                coverage_probe, "_git_clean", return_value=True
            ), mock.patch.object(
                coverage_probe, "_provider_factory", return_value=provider
            ), mock.patch.object(
                ExactDateAkShareProbeAdapter,
                "fetch_daily_market",
                side_effect=fetch_daily_market,
            ), mock.patch.object(
                coverage_probe,
                "_validate_rights_review",
                wraps=original_validate,
            ) as validate_rights, mock.patch.object(
                coverage_probe,
                "publish_private_directory_atomic_exclusive",
                wraps=original_publish,
            ) as publish_private:
                receipt = coverage_probe.run_probe(
                    spec_path=spec_path,
                    prior_inventory_path=inventory_path,
                    timestamp_package_path=package_path,
                    timestamp_proof_path=proof_path,
                    rights_review_path=rights_path,
                    qdata_checkout=qdata_path,
                    output_dir=output_path,
                    agent_commit=agent_commit,
                )

            self.assertEqual(
                [call.kwargs["phase"] for call in validate_rights.call_args_list],
                ["first provider request", "receipt publication"],
            )
            self.assertEqual(
                receipt["rights_review_sha256"], preflight["rights_review_sha256"]
            )
            private_manifest = json.loads(
                (output_path / "private_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                private_manifest["rights_review_sha256"],
                receipt["rights_review_sha256"],
            )
            publish_private.assert_called_once()
            self.assertEqual(
                Path(publish_private.call_args.args[1]), output_path.resolve()
            )

    def test_probe_atomic_publish_never_replaces_racing_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for entry_kind in ("file", "empty_directory", "symlink"):
                with self.subTest(entry_kind=entry_kind):
                    staging = root / f"staging-{entry_kind}"
                    destination = root / f"destination-{entry_kind}"
                    staging.mkdir()
                    (staging / "complete.json").write_text(
                        '{"complete":true}\n', encoding="utf-8"
                    )
                    if entry_kind == "file":
                        destination.write_text("race winner\n", encoding="utf-8")
                    elif entry_kind == "empty_directory":
                        destination.mkdir()
                    else:
                        symlink_target = root / f"symlink-target-{entry_kind}"
                        symlink_target.mkdir()
                        destination.symlink_to(symlink_target, target_is_directory=True)

                    with self.assertRaisesRegex(
                        coverage_probe.PrivateArtifactPathError,
                        "already exists",
                    ):
                        coverage_probe.publish_private_directory_atomic_exclusive(
                            staging,
                            destination,
                            label="probe private output directory",
                        )

                    self.assertTrue(staging.is_dir())
                    self.assertTrue((staging / "complete.json").is_file())
                    if entry_kind == "file":
                        self.assertEqual(
                            destination.read_text(encoding="utf-8"),
                            "race winner\n",
                        )
                    elif entry_kind == "empty_directory":
                        self.assertTrue(destination.is_dir())
                        self.assertEqual(list(destination.iterdir()), [])
                    else:
                        self.assertTrue(destination.is_symlink())

    def test_probe_blocks_any_git_worktree_before_provider_request(self) -> None:
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
                    "user.name=Probe Fixture",
                    "-c",
                    "user.email=probe-fixture@example.test",
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

            for worktree in (repository, linked):
                provider_factory = mock.Mock()
                with self.subTest(worktree=worktree), mock.patch.object(
                    coverage_probe,
                    "preflight_probe",
                    return_value={"status": "READY", "blocking_reason_codes": []},
                ), mock.patch.object(
                    coverage_probe,
                    "_provider_factory",
                    provider_factory,
                ), self.assertRaisesRegex(
                    CoverageProbeError,
                    "must be outside every Git worktree",
                ):
                    coverage_probe.run_probe(
                        spec_path="unused-spec.json",
                        prior_inventory_path="unused-inventory.json",
                        timestamp_package_path="unused-package.json",
                        timestamp_proof_path="unused-proof.json",
                        rights_review_path="unused-rights.json",
                        qdata_checkout="unused-qdata",
                        output_dir=worktree / "private-probe-output",
                    )
                provider_factory.assert_not_called()
                self.assertFalse((worktree / "private-probe-output").exists())

    def test_recursive_credential_key_decoding_is_bounded_and_fail_closed(self) -> None:
        for encoded_key in (
            "%2561pi_key",
            "api%255fkey",
            "X%252dAmz%252dSignature",
        ):
            with self.subTest(encoded_key=encoded_key):
                self.assertTrue(credential_like_public_key(encoded_key))
        self.assertFalse(credential_like_public_key("key"))

    def test_encoded_authority_and_labeled_paths_fail_closed(self) -> None:
        cases = (
            ("https://%6cocalhost/x", "local or internal URL host"),
            ("https://%31%32%37.0.0.1/x", "non-public URL address"),
            ("reviewed path:/foo/bar", "absolute local path"),
        )
        for value, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(public_string_privacy_reason(value), expected)
        self.assertIsNone(
            public_string_privacy_reason(
                "See https://doi.org/10.1016/j.jfineco.2022.08.003 and /api/v1/items."
            )
        )

    def _final_inventory(self, *, base_commit: str) -> dict[str, object]:
        entries = [{
            "inventory_id": "fixture-prior-specification",
            "artifact_type": "locked_confirmatory_study_plan",
            "primary_path": "fixture/prior-plan.json",
            "related_paths": [],
            "present_in_repository": True,
            "repository_state": "tracked_at_head",
            "introduced_in_commit": base_commit,
            "commit_semantics": (
                "Fixture commit introducing the prior locked study specification."
            ),
            "specification_ids": ["fixture-prior-specification"],
            "outcome_exposure_known": "unknown",
            "outcome_exposure_basis": (
                "The fixture does not establish whether prior outcomes were inspected."
            ),
            "execution_history_claim": "unknown",
        }]
        return {
            "schema_version": "prior_specification_inventory_v1",
            "inventory_id": "fixture-prior-inventory",
            "study_id": STUDY_ID,
            "status": "manifest_eligible_outcome_blind",
            "inventory_cutoff_at": "2026-08-31T12:50:00+00:00",
            "generated_at": "2026-08-31T12:55:00+00:00",
            "prepared_by": "fixture preparer",
            "preparer_role": "fixture methods reviewer",
            "outcome_blind_inventory": True,
            "contains_outcome_values": False,
            "purpose": (
                "Enumerate every prior fixture specification without reporting outcomes."
            ),
            "repository_snapshot": {
                "head_commit": base_commit,
                "inspected_at": "2026-08-31T12:45:00+00:00",
                "working_tree_state": "clean",
            },
            "entry_count": len(entries),
            "entries_sha256": sha256_bytes(canonical_json_bytes(entries)),
            "entries": entries,
        }

    def test_probe_inventory_gate_blocks_draft_and_accepts_finalized_ancestor(self) -> None:
        source_root = Path(__file__).resolve().parents[1]
        study = source_root / "studies/pit_factor_bias_decomposition_v2"
        temporary_repository = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_repository.cleanup)
        base, head = _two_commit_fixture_repository(Path(temporary_repository.name))
        repository_patch = mock.patch(
            "a_share_quant_agent.confirmatory_study._git_repository_root",
            return_value=Path(temporary_repository.name),
        )
        repository_patch.start()
        self.addCleanup(repository_patch.stop)

        maintained_draft = json.loads(
            (study / "prior_specification_inventory.json").read_text(encoding="utf-8")
        )
        with self.assertRaisesRegex(CoverageProbeError, "not finalized"):
            _validate_inventory_shape(
                maintained_draft, expected_code_commit=head
            )

        finalized = self._final_inventory(base_commit=base)
        frozen_bytes = canonical_json_bytes(finalized)
        state = _validate_inventory_shape(finalized, expected_code_commit=head)
        self.assertEqual(state["entry_count"], 1)
        self.assertEqual(canonical_json_bytes(finalized), frozen_bytes)

        # A future snapshot cannot be retroactively attached to an older
        # containing commit. The same exact inventory bytes may instead be
        # hash-bound by later descendant commits without self-reference.
        finalized["repository_snapshot"]["head_commit"] = head
        with self.assertRaisesRegex(CoverageProbeError, "compatible"):
            _validate_inventory_shape(finalized, expected_code_commit=base)

    def test_external_timestamp_requires_provider_evidence_and_hash_binding(self) -> None:
        proof = {
            "type": "human_verified_external_timestamp",
            "provider": "Example registry",
            "identifier": "record-1",
            "timestamped_at_utc": "2026-08-31T13:00:00Z",
            "verification_uri": "https://example.invalid/record-1",
            "evidence_sha256": "a" * 64,
            "subject_type": "coverage_probe_package_manifest_sha256",
            "subject_sha256": "b" * 64,
            "verifier": "Independent reviewer",
            "verified_at_utc": "2026-08-31T13:05:00Z",
            "trust_boundary": TIMESTAMP_TRUST_BOUNDARY,
        }
        self.assertEqual(
            validate_external_timestamp_proof(
                proof,
                package_manifest_sha256="b" * 64,
                before=datetime(2026, 9, 1, tzinfo=timezone.utc),
            )["identifier"],
            "record-1",
        )
        proof["subject_sha256"] = "c" * 64
        with self.assertRaises(CoverageProbeError):
            validate_external_timestamp_proof(
                proof, package_manifest_sha256="b" * 64
            )

    def test_public_timestamp_and_receipt_privacy_fail_closed(self) -> None:
        proof = {
            "type": "human_verified_external_timestamp",
            "provider": "Example registry",
            "identifier": "record-1",
            "timestamped_at_utc": "2026-08-31T13:00:00Z",
            "verification_uri": "https://example.invalid/record-1?view=public",
            "evidence_sha256": "a" * 64,
            "subject_type": "coverage_probe_package_manifest_sha256",
            "subject_sha256": "b" * 64,
            "verifier": "Independent reviewer",
            "verified_at_utc": "2026-08-31T13:05:00Z",
            "trust_boundary": TIMESTAMP_TRUST_BOUNDARY,
        }
        validate_external_timestamp_proof(
            proof,
            package_manifest_sha256="b" * 64,
            before=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
        cases = (
            (
                "verification_uri",
                "https://user:password@example.invalid/record-1",
                "URL user information",
            ),
            (
                "provider",
                "Reviewed at https://user:password@example.invalid/record-1",
                "URL user information",
            ),
            (
                "verification_uri",
                "https://example.invalid/record-1?accessToken=hidden-value",
                "credential-like URL query key",
            ),
            (
                "provider",
                "Registry URL: http://localhost:8080/record-1",
                "non-HTTPS URL",
            ),
            (
                "provider",
                "Registry URL: https://example.invalid/record-1?X-API-Key=hidden-value",
                "credential-like URL query key",
            ),
            (
                "provider",
                "Registry URL: https://example.invalid/record-1?"
                "%2561pi_key=hidden-value",
                "credential-like URL query key",
            ),
            (
                "provider",
                "Registry URL: https://example.invalid/record-1?redirect="
                "https%3A%2F%2Flocalhost%2Fprivate",
                "local or internal URL host",
            ),
            (
                "verification_uri",
                "https://example.invalid/record-1?clientSecret=hidden-value",
                "credential-like URL query key",
            ),
            (
                "verification_uri",
                "https://example.invalid/record-1?X-Amz-Signature=hidden-value",
                "credential-like URL query key",
            ),
            (
                "verification_uri",
                "https://example.invalid/callback#access_token=hidden-value",
                "credential-like URL fragment key",
            ),
            (
                "verification_uri",
                "https://example.invalid/callback#api%255fkey=hidden-value",
                "credential-like URL fragment key",
            ),
            (
                "verification_uri",
                "https://example.invalid/callback/access_token=hidden-value",
                "credential-like URL path parameter key",
            ),
            (
                "verification_uri",
                "https://example.invalid/callback;XApiKey=hidden-value",
                "credential-like URL path parameter key",
            ),
            (
                "verification_uri",
                "https://example.invalid/callback;"
                "X%252dAmz%252dSignature=hidden-value",
                "credential-like URL path parameter key",
            ),
            ("provider", "/" + "Users/reviewer/private.txt", "absolute local path"),
            (
                "provider",
                "Reviewed at " + "/" + "Users/reviewer/private.txt",
                "absolute local path",
            ),
            (
                "provider",
                "Stored under " + "/" + "home/reviewer/private.txt",
                "absolute local path",
            ),
            (
                "provider",
                "Stored under /workspace/reviewer/private.txt",
                "absolute local path",
            ),
            ("provider", "Stored under /foo/bar", "absolute local path"),
            ("provider", "Reviewed path:/foo/bar", "absolute local path"),
            (
                "provider",
                "Registry URL: https://%6cocalhost/private",
                "local or internal URL host",
            ),
            (
                "provider",
                "Registry URL: https://%31%32%37.0.0.1/private",
                "non-public URL address",
            ),
            (
                "identifier",
                "FILE://" + "/" + "Users/reviewer/private.txt",
                "absolute local path",
            ),
            (
                "verifier",
                "file:" + "/" + "Users/reviewer/private.txt",
                "absolute local path",
            ),
            (
                "trust_boundary",
                "C" + r":\private\review.txt",
                "absolute local path",
            ),
        )
        for field, sensitive_value, pattern in cases:
            with self.subTest(field=field, pattern=pattern):
                changed = json.loads(json.dumps(proof))
                changed[field] = sensitive_value
                with self.assertRaisesRegex(CoverageProbeError, pattern) as raised:
                    validate_external_timestamp_proof(
                        changed,
                        package_manifest_sha256="b" * 64,
                        before=datetime(2026, 9, 1, tzinfo=timezone.utc),
                    )
                self.assertNotIn(sensitive_value, str(raised.exception))

        _validate_public_receipt_privacy(
            {
                "request": {
                    "route_evidence": {
                        "endpoint_path": "/api/qt/stock/kline/get"
                    }
                }
            },
            label="coverage probe public receipt",
        )

        for credential_key in (
            "X-API-Key",
            "x_api_key",
            "XApiKey",
            "AWSAccessKeyId",
            "proxy-authorization",
            "%2561pi_key",
            "api%255fkey",
            "X%252dAmz%252dSignature",
        ):
            sensitive_value = f"hidden-{credential_key}-value"
            with self.subTest(credential_key=credential_key):
                with self.assertRaisesRegex(
                    CoverageProbeError, "credential-like key"
                ) as raised:
                    _validate_public_receipt_privacy(
                        {"nested": {credential_key: sensitive_value}},
                        label="coverage probe public receipt",
                    )
                self.assertNotIn(sensitive_value, str(raised.exception))

        for value in (
            "See https://doi.org/10.1016/j.jfineco.2022.08.003.",
            "The documented API route is /api/qt/stock/kline/get.",
            "The versioned API route is /v1/research/items.",
            "The public endpoint is https://example.invalid/oauth/token.",
            "Ratios 1/2 and date 2026/09/02 are public metadata.",
            "A generic key identifies each table row.",
        ):
            with self.subTest(benign=value):
                _validate_public_receipt_privacy(
                    {"review_reference": value},
                    label="coverage probe public receipt",
                )
        _validate_public_receipt_privacy(
            {"key": "public-row-id"},
            label="coverage probe public receipt",
        )

    def test_v1_hash_is_the_locked_immutable_predecessor(self) -> None:
        root = Path(__file__).resolve().parents[1]
        value = root / "studies/pit_factor_bias_decomposition_v2/coverage_probe_spec.v1.json"
        self.assertEqual(sha256_bytes(value.read_bytes()), V1_SPEC_SHA256)

    def test_timestamp_package_binds_spec_inventory_and_agent_commit(self) -> None:
        package = {
            "schema_version": "stage2_coverage_probe_timestamp_package_v1",
            "study_id": STUDY_ID,
            "probe_id": PROBE_ID,
            "spec_path": "studies/pit_factor_bias_decomposition_v2/coverage_probe_spec.v2.json",
            "spec_sha256": "a" * 64,
            "prior_specification_inventory_path": "studies/pit_factor_bias_decomposition_v2/prior_specification_inventory.json",
            "prior_specification_inventory_sha256": "b" * 64,
            "agent_commit": "c" * 40,
        }
        self.assertEqual(
            _validate_timestamp_package(
                package,
                raw=canonical_json_bytes(package),
                spec_sha256="a" * 64,
                inventory_sha256="b" * 64,
                agent_commit="c" * 40,
            )["agent_commit"],
            "c" * 40,
        )
        package["prior_specification_inventory_sha256"] = "d" * 64
        with self.assertRaisesRegex(CoverageProbeError, "does not bind"):
            _validate_timestamp_package(
                package,
                raw=canonical_json_bytes(package),
                spec_sha256="a" * 64,
                inventory_sha256="b" * 64,
                agent_commit="c" * 40,
            )

    def test_blocked_receipt_is_auditable_but_never_passes(self) -> None:
        spec_sha = "d" * 64
        timestamp_package = {
            "schema_version": "stage2_coverage_probe_timestamp_package_v1",
            "study_id": STUDY_ID,
            "probe_id": PROBE_ID,
            "spec_path": "studies/pit_factor_bias_decomposition_v2/coverage_probe_spec.v2.json",
            "spec_sha256": spec_sha,
            "prior_specification_inventory_path": "studies/pit_factor_bias_decomposition_v2/prior_specification_inventory.json",
            "prior_specification_inventory_sha256": "9" * 64,
            "agent_commit": "e" * 40,
        }
        package_sha = sha256_bytes(canonical_json_bytes(timestamp_package))
        receipt = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "study_id": STUDY_ID,
            "probe_id": PROBE_ID,
            "receipt_id": None,
            "spec_sha256": spec_sha,
            "timestamp_package": timestamp_package,
            "status": "BLOCKED",
            "executed_at_utc": "2026-08-31T13:30:00Z",
            "external_timestamp_proof": {
                "type": "human_verified_external_timestamp",
                "provider": "Example registry",
                "identifier": "record-1",
                "timestamped_at_utc": "2026-08-31T13:00:00Z",
                "verification_uri": "https://example.invalid/record-1",
                "evidence_sha256": "a" * 64,
                "subject_type": "coverage_probe_package_manifest_sha256",
                "subject_sha256": package_sha,
                "verifier": "Independent reviewer",
                "verified_at_utc": "2026-08-31T13:05:00Z",
                "trust_boundary": TIMESTAMP_TRUST_BOUNDARY,
            },
            "rights_review_sha256": "7" * 64,
            "repository_state": {
                "agent_commit": "e" * 40,
                "qdata_commit": QDATA_COMMIT,
                "agent_clean": True,
                "qdata_clean": True,
                "python_version": PYTHON_VERSION,
                "akshare_version": AKSHARE_VERSION,
            },
            "request": {
                "provider_adapter": EXACT_DATE_ADAPTER,
                "provider_interface": "akshare.stock_zh_a_hist",
                "upstream_provider_identity": "not_verified",
                "route_evidence": {
                    "request_count": 0,
                    "requested_https_host": None,
                    "final_https_host": None,
                    "endpoint_path": None,
                    "redirect_count": 0,
                    "all_requests_exact_single_date": False,
                    "fallback_attempted": False,
                    "lookback_applied": False,
                },
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
                "missing_symbol_date_cell_count": 24,
                "duplicate_symbol_date_cells": 0,
                "extra_symbol_date_cells": 0,
            },
            "field_quality": {
                "all_required_raw_bar_fields_valid": False,
                "scope_and_cell_identity_valid": False,
            },
            "failures": {
                "empty_response": 24,
                "validation_error": 0,
                "provider_error": 0,
                "network_error": 0,
            },
            "gates": {
                gate: (
                    gate
                    not in {
                        "COMPLETE_CELL_COVERAGE",
                        "PROBE_SPECIFIC_RAW_BAR_FIELDS",
                        "BASIC_VALUE_INTEGRITY",
                        "ROUTE_AND_UPSTREAM_VERIFIED",
                    }
                )
                for gate in GATE_IDS
            },
            "rights": {
                "review_status": "verified",
                "raw_redistribution_allowed": False,
                "aggregate_receipt_publication_allowed": True,
            },
            "publication_consent": {
                "review_status": "verified",
                "aggregate_coverage_publication_allowed": True,
                "artifact_hash_publication_allowed": True,
                "artifact_filename_publication_allowed": True,
                "artifact_size_publication_allowed": True,
                "artifact_row_count_publication_allowed": True,
                "artifact_symbol_count_and_date_range_publication_allowed": True,
                "timestamp_provider_and_identifier_publication_allowed": True,
                "timestamp_evidence_hash_publication_allowed": True,
                "timestamp_verifier_identity_publication_allowed": True,
                "timestamp_verification_uri_publication_allowed": True,
                "request_route_metadata_publication_allowed": True,
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
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            normalized = root / "normalized.csv"
            normalized.write_text(",".join((
                "symbol", "trade_date", "open", "high", "low", "close", "volume", "amount"
            )) + "\n", encoding="utf-8")
            request_log = root / "request_log.json"
            exact_log = [
                {"symbol": symbol, "date": date, "status": "empty_response"}
                for date in DATES
                for symbol in SYMBOLS
            ]
            request_log.write_bytes(canonical_json_bytes(exact_log))
            receipt["artifacts"] = [
                {
                    "kind": "normalized_private",
                    "relative_path": normalized.name,
                    "sha256": sha256_bytes(normalized.read_bytes()),
                    "size_bytes": normalized.stat().st_size,
                    "row_count": 0,
                    "symbol_count": 0,
                    "minimum_date": None,
                    "maximum_date": None,
                    "schema_sha256": RAW_SCHEMA_SHA256,
                },
                {
                    "kind": "request_log_private",
                    "relative_path": request_log.name,
                    "sha256": sha256_bytes(request_log.read_bytes()),
                    "size_bytes": request_log.stat().st_size,
                    "row_count": 24,
                    "symbol_count": len(SYMBOLS),
                    "minimum_date": DATES[0],
                    "maximum_date": DATES[-1],
                    "schema_sha256": REQUEST_LOG_SCHEMA_SHA256,
                },
            ]
            unsigned = dict(receipt)
            unsigned.pop("receipt_id")
            receipt["receipt_id"] = "sha256:" + sha256_bytes(
                canonical_json_bytes(unsigned)
            )
            path = root / "receipt.json"
            path.write_bytes(canonical_json_bytes(receipt))
            manifest = {
                "schema_version": PRIVATE_MANIFEST_SCHEMA_VERSION,
                "spec_sha256": spec_sha,
                "timestamp_package_sha256": package_sha,
                "rights_review_sha256": receipt["rights_review_sha256"],
                "agent_commit": "e" * 40,
                "qdata_commit": QDATA_COMMIT,
                "request_scope": receipt["request"],
                "artifacts": receipt["artifacts"],
                "gates": receipt["gates"],
                "receipt_sha256": sha256_bytes(path.read_bytes()),
                "raw_rows_private": True,
            }
            (root / "private_manifest.json").write_bytes(
                canonical_json_bytes(manifest)
            )
            audited = verify_probe_artifacts(path, artifact_root=root)

            unsafe_receipt = json.loads(json.dumps(receipt))
            sensitive_uri = (
                "https://example.invalid/record-1?accessToken=hidden-value"
            )
            unsafe_receipt["external_timestamp_proof"][
                "verification_uri"
            ] = sensitive_uri
            unsigned = dict(unsafe_receipt)
            unsigned.pop("receipt_id")
            unsafe_receipt["receipt_id"] = "sha256:" + sha256_bytes(
                canonical_json_bytes(unsigned)
            )
            unsafe_path = root / "unsafe-public-receipt.json"
            unsafe_path.write_bytes(canonical_json_bytes(unsafe_receipt))
            with self.assertRaisesRegex(
                CoverageProbeError, "credential-like URL query key"
            ) as raised:
                verify_probe_artifacts(unsafe_path)
            self.assertNotIn(sensitive_uri, str(raised.exception))
            unsafe_path.unlink()

            # Public-only verification must derive the PASSED invariants; a
            # recomputed receipt_id cannot turn inconsistent self-reported
            # gates into valid coverage, quality, or publication rights.
            passed = json.loads(json.dumps(receipt))
            passed["status"] = "PASSED"
            passed["request"]["upstream_provider_identity"] = "eastmoney.com"
            passed["request"]["route_evidence"] = {
                "request_count": 24,
                "requested_https_host": "push2his.eastmoney.com",
                "final_https_host": "push2his.eastmoney.com",
                "endpoint_path": "/api/qt/stock/kline/get",
                "redirect_count": 0,
                "all_requests_exact_single_date": True,
                "fallback_attempted": False,
                "lookback_applied": False,
            }
            passed["artifacts"][0].update(
                {
                    "row_count": 24,
                    "symbol_count": 12,
                    "minimum_date": DATES[0],
                    "maximum_date": DATES[-1],
                }
            )
            passed["coverage"] = {
                "expected_symbol_date_cells": 24,
                "observed_symbol_date_cells": 24,
                "missing_symbol_date_cell_count": 0,
                "duplicate_symbol_date_cells": 0,
                "extra_symbol_date_cells": 0,
            }
            passed["field_quality"] = {
                "all_required_raw_bar_fields_valid": True,
                "scope_and_cell_identity_valid": True,
            }
            passed["failures"] = {
                "empty_response": 0,
                "validation_error": 0,
                "provider_error": 0,
                "network_error": 0,
            }
            passed["gates"] = {gate: True for gate in GATE_IDS}
            for label, pattern, mutate in (
                (
                    "duplicate-coverage",
                    "canonical complete coverage",
                    lambda item: item["coverage"].__setitem__(
                        "duplicate_symbol_date_cells", 1
                    ),
                ),
                (
                    "false-field-quality",
                    "field-quality evidence is not fully true",
                    lambda item: item["field_quality"].__setitem__(
                        "scope_and_cell_identity_valid", False
                    ),
                ),
                (
                    "aggregate-rights-denied",
                    "contains a failed gate",
                    lambda item: item["rights"].__setitem__(
                        "aggregate_receipt_publication_allowed", False
                    ),
                ),
            ):
                tampered = json.loads(json.dumps(passed))
                mutate(tampered)
                unsigned = dict(tampered)
                unsigned.pop("receipt_id")
                tampered["receipt_id"] = "sha256:" + sha256_bytes(
                    canonical_json_bytes(unsigned)
                )
                public_only_path = root / f"{label}.json"
                public_only_path.write_bytes(canonical_json_bytes(tampered))
                with self.assertRaisesRegex(CoverageProbeError, pattern):
                    verify_probe_artifacts(public_only_path)
                public_only_path.unlink()

            # A public category reshuffle preserves the total missing count,
            # so only the private exact-cell request log can disprove it.
            receipt["failures"]["empty_response"] = 23
            receipt["failures"]["provider_error"] = 1
            unsigned = dict(receipt)
            unsigned.pop("receipt_id")
            receipt["receipt_id"] = "sha256:" + sha256_bytes(
                canonical_json_bytes(unsigned)
            )
            path.write_bytes(canonical_json_bytes(receipt))
            manifest["receipt_sha256"] = sha256_bytes(path.read_bytes())
            (root / "private_manifest.json").write_bytes(
                canonical_json_bytes(manifest)
            )
            with self.assertRaisesRegex(
                CoverageProbeError, "public aggregate receipt"
            ):
                verify_probe_artifacts(path, artifact_root=root)

            receipt["status"] = "ERROR"
            path.write_bytes(canonical_json_bytes(receipt))
            with self.assertRaises(CoverageProbeError):
                verify_probe_artifacts(path)
        self.assertEqual(audited["status"], "BLOCKED")

    def test_malformed_timestamp_is_rejected(self) -> None:
        with self.assertRaises(CoverageProbeError):
            validate_external_timestamp_proof(
                {}, package_manifest_sha256="a" * 64
            )

    def test_exact_date_adapter_observes_one_nonredirected_route(self) -> None:
        adapter = object.__new__(ExactDateAkShareProbeAdapter)
        response = SimpleNamespace(
            url="https://push2his.eastmoney.com/api/qt/stock/kline/get?beg=20160630&end=20160630",
            history=[],
            status_code=200,
        )
        calls = []

        def transport_get(url, **kwargs):
            calls.append((url, kwargs))
            return response

        requests_module = SimpleNamespace(get=transport_get)
        module = SimpleNamespace(requests=requests_module)

        def exact_function(**kwargs):
            params = {
                "fields1": "f1",
                "fields2": "f51",
                "ut": "fixed",
                "klt": "101",
                "fqt": "0",
                "secid": "1.600601",
                "beg": kwargs["start_date"],
                "end": kwargs["end_date"],
            }
            module.requests.get(
                "https://push2his.eastmoney.com/api/qt/stock/kline/get",
                params=params,
                timeout=None,
            )
            return []

        adapter._module = module
        adapter._requests = requests_module
        adapter._function = exact_function
        _, route = adapter._fetch_exact_history(
            symbol="600601.SH", trade_date="2016-06-30"
        )
        self.assertEqual(route["final_https_host"], "push2his.eastmoney.com")
        self.assertTrue(route["exact_single_date"])
        self.assertFalse(route["fallback_attempted"])
        self.assertEqual(calls[0][1]["allow_redirects"], False)
        self.assertEqual(calls[0][1]["params"]["beg"], calls[0][1]["params"]["end"])

    def test_exact_date_adapter_rejects_lookback_or_second_route(self) -> None:
        adapter = object.__new__(ExactDateAkShareProbeAdapter)
        requests_module = SimpleNamespace(
            get=lambda url, **kwargs: SimpleNamespace(
                url=url, history=[], status_code=200
            )
        )
        module = SimpleNamespace(requests=requests_module)

        def lookback_function(**kwargs):
            module.requests.get(
                "https://push2his.eastmoney.com/api/qt/stock/kline/get",
                params={
                    "fields1": "f1",
                    "fields2": "f51",
                    "ut": "fixed",
                    "klt": "101",
                    "fqt": "0",
                    "secid": "1.600601",
                    "beg": "20160601",
                    "end": kwargs["end_date"],
                },
                timeout=None,
            )
            return []

        adapter._module = module
        adapter._requests = requests_module
        adapter._function = lookback_function
        with self.assertRaisesRegex(CoverageProbeError, "exact-date"):
            adapter._fetch_exact_history(
                symbol="600601.SH", trade_date="2016-06-30"
            )

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

        bar["open"] = 1.25
        bar["trade_date"] = DATES[0] + "T00:00:00Z"
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
                    "--timestamp-package",
                    str(study / "coverage_probe_timestamp_package.template.json"),
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


def _two_commit_fixture_repository(root: Path) -> tuple[str, str]:
    """Create an isolated ancestry fixture without assuming the checkout has HEAD^."""

    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    marker = root / "inventory-state.txt"
    commits: list[str] = []
    for index, value in enumerate(("audited base\n", "bound descendant\n"), start=1):
        marker.write_text(value, encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", marker.name], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "user.name=Inventory Fixture",
                "-c",
                "user.email=inventory-fixture@example.invalid",
                "commit",
                "--quiet",
                "-m",
                f"inventory fixture {index}",
            ],
            check=True,
        )
        commits.append(
            subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
            ).strip()
        )
    return commits[0], commits[1]


if __name__ == "__main__":
    unittest.main()
