"""Outcome-blind, fixed-scope Stage-2 coverage-probe lifecycle.

The Stage-2 protocol deliberately separates a bounded source probe from the
factor study.  This module is the small operational bridge between the two:
it performs the pre-request checks, optionally executes *only* the twelve
fixed symbols on the two fixed dates through a pinned, exact-date AkShare
transport adapter, and emits a redacted receipt. QData remains a historical
provenance input but is never imported or called by the probe. It never
computes a factor, return, rank, IC, portfolio statistic, or variant comparison.

The module is intentionally fail-closed.  A missing external timestamp,
unclean checkout, reused output directory, missing rights evidence, provider
error, duplicate/extra cell, or malformed value produces a ``BLOCKED``
receipt (or a preflight error before any request).  Private rows stay in the
operator's output directory; the public receipt contains hashes and aggregate
counts only.
"""

from __future__ import annotations

from dataclasses import is_dataclass
from datetime import datetime, timezone
import argparse
import csv
import hashlib
import importlib
from importlib import metadata as importlib_metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from a_share_quant_agent.public_receipt_privacy import (
    absolute_local_path_like as _absolute_local_path_like,
    credential_like_public_key as _credential_like_public_key,
    public_string_privacy_reason as _public_string_privacy_reason,
    unsafe_public_url_reason as _unsafe_public_url_reason,
)
from a_share_quant_agent.private_artifact_paths import (
    PrivateArtifactPathError,
    containing_git_worktree,
    publish_private_directory_atomic_exclusive,
    require_outside_any_git_worktree,
    resolve_artifact_path,
)


STUDY_ID = "a-share-factor-timing-bias-decomposition-v2"
SPEC_SCHEMA_VERSION = "stage2_coverage_probe_spec_v2"
RECEIPT_SCHEMA_VERSION = "stage2_coverage_probe_receipt_v2"
PROBE_ID = "stage2-akshare-raw-coverage-2016-2018-v2"
SPEC_REPOSITORY_PATH = (
    "studies/pit_factor_bias_decomposition_v2/coverage_probe_spec.v2.json"
)
INVENTORY_REPOSITORY_PATH = (
    "studies/pit_factor_bias_decomposition_v2/prior_specification_inventory.json"
)
V1_SPEC_REPOSITORY_PATH = (
    "studies/pit_factor_bias_decomposition_v2/coverage_probe_spec.v1.json"
)
V1_SPEC_SHA256 = "35e63a90dacd412868345e051031af52801ea91c22e6bd181baa482364d102e8"
QDATA_COMMIT = "19b2dd1df8cfbe875809179a4772e4656dce01bd"
PYTHON_VERSION = "3.12.12"
AKSHARE_VERSION = "1.18.81"
AKSHARE_HISTORY_MODULE_SHA256 = (
    "749a94a192bcd79ee76867fb8dfc7c563613cf08afb1dd72ca5a97c471bcd3d8"
)
EXACT_DATE_ADAPTER = (
    "a_share_quant_agent.coverage_probe.ExactDateAkShareProbeAdapter"
)
PROVIDER_INTERFACE = "akshare.stock_zh_a_hist"
UPSTREAM_HOST = "push2his.eastmoney.com"
UPSTREAM_PATH = "/api/qt/stock/kline/get"
UPSTREAM_IDENTITY = "eastmoney.com"
DATES = ("2016-06-30", "2018-06-29")
SYMBOLS = (
    "600601.SH",
    "600602.SH",
    "000002.SZ",
    "000001.SZ",
    "600831.SH",
    "603077.SH",
    "000908.SZ",
    "002380.SZ",
    "600093.SH",
    "600146.SH",
    "002504.SZ",
    "300367.SZ",
)
EXPECTED_CELLS = len(DATES) * len(SYMBOLS)
RAW_FIELDS = ("symbol", "trade_date", "open", "high", "low", "close", "volume", "amount")
RAW_SCHEMA_BYTES = (json.dumps(list(RAW_FIELDS), separators=(",", ":")) + "\n").encode()
RAW_SCHEMA_SHA256 = hashlib.sha256(RAW_SCHEMA_BYTES).hexdigest()
REQUEST_LOG_FIELDS = ("symbol", "date", "status")
REQUEST_LOG_SCHEMA_BYTES = (json.dumps(list(REQUEST_LOG_FIELDS), separators=(",", ":")) + "\n").encode()
REQUEST_LOG_SCHEMA_SHA256 = hashlib.sha256(REQUEST_LOG_SCHEMA_BYTES).hexdigest()
TIMESTAMP_PACKAGE_SCHEMA_VERSION = "stage2_coverage_probe_timestamp_package_v1"
TIMESTAMP_PACKAGE_FIELDS = frozenset({
    "schema_version",
    "study_id",
    "probe_id",
    "spec_path",
    "spec_sha256",
    "prior_specification_inventory_path",
    "prior_specification_inventory_sha256",
    "agent_commit",
})
TIMESTAMP_TRUST_BOUNDARY = (
    "The timestamp record has no offline-verifiable signature; authenticity requires "
    "independent human verification."
)
GATE_IDS = (
    "SPEC_COMMITTED",
    "SPEC_EXTERNALLY_TIMESTAMPED",
    "CODE_STATE_CLEAN_AND_BOUND",
    "OUTPUT_TARGET_NEW",
    "RIGHTS_REVIEW_RECORDED",
    "EXACT_REQUEST_SCOPE",
    "COMPLETE_CELL_COVERAGE",
    "PROBE_SPECIFIC_RAW_BAR_FIELDS",
    "BASIC_VALUE_INTEGRITY",
    "ROUTE_AND_UPSTREAM_VERIFIED",
    "RAW_MODE_ATTESTED",
    "FAILURES_ACCOUNTED_FOR",
    "ARTIFACT_HASHES_VERIFIED",
)
RECEIPT_FIELDS = frozenset({
    "schema_version",
    "study_id",
    "probe_id",
    "receipt_id",
    "spec_sha256",
    "timestamp_package",
    "status",
    "executed_at_utc",
    "external_timestamp_proof",
    "rights_review_sha256",
    "repository_state",
    "request",
    "artifacts",
    "coverage",
    "field_quality",
    "failures",
    "gates",
    "rights",
    "publication_consent",
    "claim_boundaries",
})
RIGHTS_REVIEW_SCHEMA_VERSION = "stage2_coverage_probe_rights_review_v3"
PRIVATE_MANIFEST_SCHEMA_VERSION = "stage2_coverage_probe_private_manifest_v2"
RIGHTS_REVIEW_FIELDS = frozenset({
    "schema_version",
    "status",
    "reviewed_at_utc",
    "reviewer",
    "authority_basis",
    "approved_timestamp_proof_sha256",
    "contract_effective_at",
    "contract_expiry_at",
    "contract_has_no_expiry_confirmed",
    "post_expiry_private_probe_artifact_retention_allowed",
    "post_expiry_aggregate_receipt_and_metadata_publication_allowed",
    "post_expiry_survival_evidence_sha256",
    "local_storage_allowed",
    "aggregate_receipt_publication_allowed",
    "aggregate_coverage_publication_allowed",
    "artifact_hash_publication_allowed",
    "artifact_filename_publication_allowed",
    "artifact_size_publication_allowed",
    "artifact_row_count_publication_allowed",
    "artifact_symbol_count_and_date_range_publication_allowed",
    "timestamp_provider_and_identifier_publication_allowed",
    "timestamp_evidence_hash_publication_allowed",
    "timestamp_verifier_identity_publication_allowed",
    "timestamp_verification_uri_publication_allowed",
    "request_route_metadata_publication_allowed",
    "raw_redistribution_allowed",
    "scope",
    "evidence_sha256",
    "statement",
})
ARTIFACT_FIELDS = frozenset({
    "kind",
    "relative_path",
    "sha256",
    "size_bytes",
    "row_count",
    "symbol_count",
    "minimum_date",
    "maximum_date",
    "schema_sha256",
})
ROUTE_EVIDENCE_FIELDS = frozenset({
    "request_count",
    "requested_https_host",
    "final_https_host",
    "endpoint_path",
    "redirect_count",
    "all_requests_exact_single_date",
    "fallback_attempted",
    "lookback_applied",
})
PUBLICATION_CONSENT_FIELDS = frozenset({
    "review_status",
    "aggregate_coverage_publication_allowed",
    "artifact_hash_publication_allowed",
    "artifact_filename_publication_allowed",
    "artifact_size_publication_allowed",
    "artifact_row_count_publication_allowed",
    "artifact_symbol_count_and_date_range_publication_allowed",
    "timestamp_provider_and_identifier_publication_allowed",
    "timestamp_evidence_hash_publication_allowed",
    "timestamp_verifier_identity_publication_allowed",
    "timestamp_verification_uri_publication_allowed",
    "request_route_metadata_publication_allowed",
})
class CoverageProbeError(RuntimeError):
    """Raised when the bounded probe cannot be safely prepared or verified."""


def canonical_json_bytes(value: Any) -> bytes:
    """Return the repository's canonical JSON representation (with one LF)."""

    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise CoverageProbeError("value is not canonical JSON") from exc
    return (text + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: str | Path) -> str:
    target = Path(path)
    digest = hashlib.sha256()
    try:
        with target.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise CoverageProbeError(f"cannot hash file: {target.name}") from exc
    return digest.hexdigest()


def _meaningful(value: Any, *, minimum: int = 4) -> bool:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        return False
    lowered = value.strip().lower()
    return not any(token in lowered for token in ("todo", "tbd", "pending", "placeholder"))


def _sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _git_sha(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def _validate_public_receipt_privacy(value: Any, *, label: str) -> None:
    """Reject unsafe public material without echoing a sensitive value."""

    def visit(item: Any, path: str) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                key_text = str(key)
                if _credential_like_public_key(key_text):
                    raise CoverageProbeError(
                        f"{label} privacy check rejected a credential-like key at "
                        "<redacted-path>.<redacted-key>"
                    )
                key_privacy_reason = _public_string_privacy_reason(key_text)
                if key_privacy_reason is not None:
                    raise CoverageProbeError(
                        f"{label} privacy check rejected {key_privacy_reason} "
                        "in a key at <redacted-path>.<redacted-key>"
                    )
                child_path = f"{path}.{key_text}"
                visit(child, child_path)
            return
        if isinstance(item, (list, tuple)):
            for index, child in enumerate(item):
                visit(child, f"{path}[{index}]")
            return
        if not isinstance(item, str):
            return
        fixed_network_endpoint_path = (
            path.endswith(".request.route_evidence.endpoint_path")
            and item == UPSTREAM_PATH
        )
        privacy_reason = (
            None if fixed_network_endpoint_path else _public_string_privacy_reason(item)
        )
        if privacy_reason is not None:
            raise CoverageProbeError(
                f"{label} privacy check rejected {privacy_reason} at "
                "<redacted-path>"
            )

    visit(value, "$")


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise CoverageProbeError(f"{label} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CoverageProbeError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CoverageProbeError(f"{label} must include a UTC offset")
    return parsed


def _regular_file(value: str | Path, label: str) -> Path:
    entry = Path(value).expanduser()
    if entry.is_symlink():
        raise CoverageProbeError(f"{label} is not a regular file")
    path = entry.resolve(strict=False)
    if not path.is_file() or path.is_symlink():
        raise CoverageProbeError(f"{label} is not a regular file")
    return path


def _load_json(path: str | Path, label: str) -> tuple[dict[str, Any], bytes]:
    target = _regular_file(path, label)
    try:
        raw = target.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoverageProbeError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise CoverageProbeError(f"{label} root must be an object")
    return value, raw


def validate_external_timestamp_proof(
    proof: Mapping[str, Any],
    *,
    package_manifest_sha256: str,
    before: datetime | None = None,
    require_verified_before: bool = True,
) -> dict[str, Any]:
    """Validate the human-verification timestamp record used by the probe.

    This is intentionally an explicit trust boundary: the code checks shape,
    hash identity, URL and chronology, while a human must inspect the
    provider-controlled record represented by ``evidence_sha256``.
    """

    _validate_public_receipt_privacy(
        proof, label="external timestamp proof"
    )

    fields = {
        "type",
        "provider",
        "identifier",
        "timestamped_at_utc",
        "verification_uri",
        "evidence_sha256",
        "subject_type",
        "subject_sha256",
        "verifier",
        "verified_at_utc",
        "trust_boundary",
    }
    if not isinstance(proof, Mapping) or set(proof) != fields:
        raise CoverageProbeError("external timestamp proof fields are incomplete")
    if proof.get("type") != "human_verified_external_timestamp":
        raise CoverageProbeError("unsupported external timestamp proof type")
    for key in ("provider", "identifier", "verifier"):
        if not _meaningful(proof.get(key)):
            raise CoverageProbeError(f"external timestamp proof {key} is invalid")
    if not _sha256(proof.get("evidence_sha256")):
        raise CoverageProbeError("external timestamp proof evidence hash is invalid")
    if proof.get("subject_type") != "coverage_probe_package_manifest_sha256":
        raise CoverageProbeError("external timestamp proof subject type is invalid")
    if proof.get("subject_sha256") != package_manifest_sha256:
        raise CoverageProbeError(
            "external timestamp proof does not bind the package manifest hash"
        )
    if proof.get("trust_boundary") != TIMESTAMP_TRUST_BOUNDARY:
        raise CoverageProbeError("external timestamp proof trust boundary is invalid")
    uri = proof.get("verification_uri")
    parsed_uri = urlparse(uri) if isinstance(uri, str) else None
    if parsed_uri is None or parsed_uri.scheme != "https" or not parsed_uri.netloc:
        raise CoverageProbeError("external timestamp proof URI must be HTTPS")
    timestamped = _timestamp(proof.get("timestamped_at_utc"), "timestamped_at_utc")
    verified = _timestamp(proof.get("verified_at_utc"), "verified_at_utc")
    if verified < timestamped:
        raise CoverageProbeError("external timestamp proof chronology is invalid")
    if before is not None:
        if timestamped > before:
            raise CoverageProbeError("external timestamp is after the preflight time")
        if require_verified_before and verified > before:
            raise CoverageProbeError("timestamp verification is after the preflight time")
    return dict(proof)


def _validate_timestamp_package(
    value: Mapping[str, Any],
    *,
    raw: bytes,
    spec_sha256: str,
    inventory_sha256: str,
    agent_commit: str,
) -> dict[str, Any]:
    """Validate the exact package which receives the external timestamp.

    The package deliberately has no self-hash.  Its canonical byte hash is the
    timestamp subject and binds the two frozen control blobs to the exact
    Agent commit which contains them.
    """

    if not isinstance(value, Mapping) or set(value) != TIMESTAMP_PACKAGE_FIELDS:
        raise CoverageProbeError("coverage probe timestamp package fields are invalid")
    if raw != canonical_json_bytes(value):
        raise CoverageProbeError("coverage probe timestamp package must be canonical JSON")
    expected = {
        "schema_version": TIMESTAMP_PACKAGE_SCHEMA_VERSION,
        "study_id": STUDY_ID,
        "probe_id": PROBE_ID,
        "spec_path": SPEC_REPOSITORY_PATH,
        "spec_sha256": spec_sha256,
        "prior_specification_inventory_path": INVENTORY_REPOSITORY_PATH,
        "prior_specification_inventory_sha256": inventory_sha256,
        "agent_commit": agent_commit,
    }
    if dict(value) != expected:
        raise CoverageProbeError(
            "coverage probe timestamp package does not bind the fixed spec, inventory, "
            "and Agent commit"
        )
    return dict(value)


def _git_root(path: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CoverageProbeError("path is not inside a verifiable Git worktree") from exc
    return Path(result.stdout.strip()).resolve()


def _git_head(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CoverageProbeError("cannot read Git HEAD") from exc
    head = result.stdout.strip().lower()
    if not _git_sha(head):
        raise CoverageProbeError("Git HEAD is not a full commit SHA")
    return head


def _git_clean(root: Path) -> bool:
    try:
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        ignored = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--others", "--ignored", "--exclude-standard", "-z"],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CoverageProbeError("Git cleanliness could not be verified") from exc
    return not status.strip() and not ignored


def _git_show(root: Path, commit: str, relative_path: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "show", f"{commit}:{relative_path}"],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CoverageProbeError(f"Git commit does not contain {relative_path}") from exc


def _verify_committed_inputs(
    *,
    spec_bytes: bytes,
    inventory_bytes: bytes,
    spec_path: Path,
    inventory_path: Path,
    agent_commit: str,
) -> tuple[Path, bool]:
    if not _git_sha(agent_commit):
        raise CoverageProbeError("agent commit must be a lowercase full Git SHA")
    root = _git_root(spec_path.parent)
    try:
        if spec_path.resolve() != root / SPEC_REPOSITORY_PATH:
            raise CoverageProbeError("coverage probe specification is not at the fixed repository path")
        inventory_root = _git_root(inventory_path.parent)
        if inventory_root != root or inventory_path.resolve() != root / INVENTORY_REPOSITORY_PATH:
            raise CoverageProbeError("prior specification inventory is not at the fixed repository path")
    except CoverageProbeError:
        raise
    except Exception as exc:
        raise CoverageProbeError("coverage probe inputs are not in one repository") from exc
    try:
        subprocess.run(
            ["git", "-C", str(root), "cat-file", "-e", f"{agent_commit}^{{commit}}"],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CoverageProbeError("agent commit is not a verifiable commit object") from exc
    if _git_show(root, agent_commit, SPEC_REPOSITORY_PATH) != spec_bytes:
        raise CoverageProbeError("agent commit does not bind the exact v2 spec bytes")
    if _git_show(root, agent_commit, INVENTORY_REPOSITORY_PATH) != inventory_bytes:
        raise CoverageProbeError("agent commit does not bind the exact inventory bytes")
    # A superseded v1 file is part of the immutability claim.  Compare the
    # checked-out bytes to the committed bytes, but do not rewrite it.
    v1_path = root / V1_SPEC_REPOSITORY_PATH
    if not v1_path.is_file() or v1_path.is_symlink():
        raise CoverageProbeError("superseded v1 probe specification is missing")
    v1_bytes = v1_path.read_bytes()
    if sha256_bytes(v1_bytes) != V1_SPEC_SHA256:
        raise CoverageProbeError("superseded v1 probe specification bytes are not immutable")
    if _git_show(root, agent_commit, V1_SPEC_REPOSITORY_PATH) != v1_bytes:
        raise CoverageProbeError("superseded v1 probe specification changed in the worktree")
    head = _git_head(root)
    if head != agent_commit.lower():
        raise CoverageProbeError("agent commit is not the checked-out HEAD")
    return root, _git_clean(root)


def _verify_qdata_checkout(path: str | Path) -> tuple[Path, bool]:
    root = _git_root(Path(path).expanduser().resolve(strict=False))
    head = _git_head(root)
    if head != QDATA_COMMIT:
        raise CoverageProbeError("QData checkout commit differs from the fixed probe commit")
    return root, _git_clean(root)


def _entry_exists(path: Path) -> bool:
    """Return true for files, directories, and dangling symlink entries."""

    return path.exists() or path.is_symlink()


def _runtime_snapshot() -> dict[str, Any]:
    """Read exact dependency versions without importing the network adapter."""

    try:
        akshare_version: str | None = importlib_metadata.version("akshare")
    except importlib_metadata.PackageNotFoundError:
        akshare_version = None
    actual = {
        "python_version": platform.python_version(),
        "akshare_version": akshare_version,
    }
    expected = {
        "python_version": PYTHON_VERSION,
        "akshare_version": AKSHARE_VERSION,
    }
    return {
        "expected": expected,
        "actual": actual,
        "matches": actual == expected,
    }


def _validate_spec_shape(spec: Mapping[str, Any]) -> None:
    """Validate the fixed fields without inspecting any outcome data."""

    # Importing the maintained validator keeps this operational command bound
    # to the same constants as ``run-stage2``.  It does not load market rows.
    try:
        from .confirmatory_study import _validate_stage2_coverage_probe_spec

        _validate_stage2_coverage_probe_spec(spec, expected_study_id=STUDY_ID)
    except Exception as exc:
        if isinstance(exc, CoverageProbeError):
            raise
        raise CoverageProbeError("coverage probe specification differs from the fixed contract") from exc


def _validate_inventory_shape(
    inventory: Mapping[str, Any], *, expected_code_commit: str
) -> dict[str, Any]:
    """Apply the same final-inventory gate used by the Stage-2 runner.

    A probe timestamp must not legitimize a draft inventory that the later
    design manifest would reject.  Import lazily to avoid a module-level
    dependency and keep this command outcome-blind; the maintained validator
    reads only control metadata and Git ancestry.
    """

    try:
        from .confirmatory_study import _validate_prior_specification_inventory

        return _validate_prior_specification_inventory(
            inventory,
            study_id=STUDY_ID,
            expected_code_commit=expected_code_commit,
        )
    except Exception as exc:
        if isinstance(exc, CoverageProbeError):
            raise
        raise CoverageProbeError(
            "prior specification inventory is not finalized, complete, or compatible "
            "with the bound Agent commit"
        ) from exc


def _validate_rights_review(
    value: Mapping[str, Any],
    *,
    timestamp_proof_sha256: str,
    active_at: datetime,
    phase: str,
) -> dict[str, Any]:
    """Validate the exact proof-bound and time-active probe rights record.

    The review is not a timeless boolean. It approves one exact raw timestamp
    proof and must be in force at every operational checkpoint. Callers use
    this function at preflight, immediately before the first provider request,
    and immediately before receipt publication.
    """

    if not isinstance(value, Mapping) or set(value) != RIGHTS_REVIEW_FIELDS:
        raise CoverageProbeError("probe rights review record is incomplete")
    if value.get("schema_version") != RIGHTS_REVIEW_SCHEMA_VERSION:
        raise CoverageProbeError("unsupported probe rights review schema")
    if value.get("status") != "verified":
        raise CoverageProbeError("probe rights review is not verified")
    if active_at.tzinfo is None or active_at.utcoffset() is None:
        raise CoverageProbeError("probe rights checkpoint must be timezone-aware")
    if not _meaningful(phase):
        raise CoverageProbeError("probe rights checkpoint phase is invalid")
    if not _meaningful(value.get("reviewer")) or not _meaningful(value.get("authority_basis"), minimum=12):
        raise CoverageProbeError("probe rights reviewer fields are incomplete")
    reviewed_at = _timestamp(value.get("reviewed_at_utc"), "rights review timestamp")
    effective_at = _timestamp(
        value.get("contract_effective_at"), "rights contract effective timestamp"
    )
    if reviewed_at > active_at:
        raise CoverageProbeError(f"rights review was recorded after {phase}")
    if effective_at > reviewed_at or effective_at > active_at:
        raise CoverageProbeError(f"probe rights contract was not effective at {phase}")
    no_expiry = value.get("contract_has_no_expiry_confirmed")
    expiry_raw = value.get("contract_expiry_at")
    if expiry_raw is None:
        if no_expiry is not True:
            raise CoverageProbeError(
                "null probe rights expiry requires explicit no-expiry confirmation"
            )
        if (
            value.get("post_expiry_private_probe_artifact_retention_allowed")
            is not False
            or value.get(
                "post_expiry_aggregate_receipt_and_metadata_publication_allowed"
            )
            is not False
            or value.get("post_expiry_survival_evidence_sha256") is not None
        ):
            raise CoverageProbeError(
                "no-expiry probe rights must not assert a post-expiry survival clause"
            )
    else:
        if no_expiry is not False:
            raise CoverageProbeError(
                "finite probe rights expiry requires no-expiry confirmation to be false"
            )
        expiry_at = _timestamp(expiry_raw, "rights contract expiry timestamp")
        if expiry_at < reviewed_at or expiry_at < active_at:
            raise CoverageProbeError(f"probe rights contract expired before {phase}")
        if (
            value.get("post_expiry_private_probe_artifact_retention_allowed")
            is not True
            or value.get(
                "post_expiry_aggregate_receipt_and_metadata_publication_allowed"
            )
            is not True
            or not _sha256(value.get("post_expiry_survival_evidence_sha256"))
        ):
            raise CoverageProbeError(
                "finite probe rights require hash-evidenced post-expiry private "
                "retention and continued aggregate receipt publication rights"
            )
    approved_proof_sha = value.get("approved_timestamp_proof_sha256")
    if (
        not _sha256(timestamp_proof_sha256)
        or not _sha256(approved_proof_sha)
        or approved_proof_sha != timestamp_proof_sha256
    ):
        raise CoverageProbeError(
            "probe rights review does not approve the exact timestamp proof bytes"
        )
    if value.get("local_storage_allowed") is not True:
        raise CoverageProbeError("rights review does not permit private local storage")
    if value.get("aggregate_receipt_publication_allowed") is not True:
        raise CoverageProbeError("rights review does not permit aggregate receipt publication")
    consent_fields = PUBLICATION_CONSENT_FIELDS - {"review_status"}
    if any(value.get(field) is not True for field in consent_fields):
        raise CoverageProbeError(
            "rights review lacks a required public receipt metadata or identity consent"
        )
    # Raw rows are never redistributed by this module, even if a vendor would
    # permit it.  Keeping this false avoids accidentally widening the public
    # receipt boundary.
    if value.get("raw_redistribution_allowed") is not False:
        raise CoverageProbeError("probe rights review must keep raw redistribution disabled")
    scope = value.get("scope")
    if not isinstance(scope, list) or "fixed_symbol_probe" not in scope:
        raise CoverageProbeError("rights review scope does not cover the fixed probe")
    if not _sha256(value.get("evidence_sha256")):
        raise CoverageProbeError("rights review evidence hash is invalid")
    if not _meaningful(value.get("statement"), minimum=40):
        raise CoverageProbeError("rights review statement is invalid")
    return dict(value)


def preflight_probe(
    *,
    spec_path: str | Path,
    prior_inventory_path: str | Path,
    timestamp_package_path: str | Path,
    timestamp_proof_path: str | Path,
    rights_review_path: str | Path,
    output_dir: str | Path,
    agent_commit: str | None = None,
    qdata_checkout: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Check every pre-request gate without contacting a provider.

    The returned object is safe to write publicly: it contains no local paths
    or raw data.  ``status`` is ``READY`` only when all gates pass.  Any
    malformed artifact raises ``CoverageProbeError`` so callers cannot mistake
    an incomplete report for authorization.
    """

    spec_file = _regular_file(spec_path, "coverage probe specification")
    inventory_file = _regular_file(prior_inventory_path, "prior specification inventory")
    package_file = _regular_file(timestamp_package_path, "coverage probe timestamp package")
    timestamp_file = _regular_file(timestamp_proof_path, "external timestamp proof")
    rights_file = _regular_file(rights_review_path, "rights review")
    output_entry = Path(output_dir).expanduser()
    output_entry_exists = _entry_exists(output_entry)
    try:
        output = resolve_artifact_path(
            output_entry, label="probe private output directory"
        )
        output_outside_worktrees = containing_git_worktree(output) is None
    except PrivateArtifactPathError as exc:
        raise CoverageProbeError(str(exc)) from exc
    spec, spec_bytes = _load_json(spec_file, "coverage probe specification")
    inventory, inventory_bytes = _load_json(inventory_file, "prior specification inventory")
    package, package_bytes = _load_json(package_file, "coverage probe timestamp package")
    proof, proof_bytes = _load_json(timestamp_file, "external timestamp proof")
    rights, rights_bytes = _load_json(rights_file, "rights review")
    _validate_spec_shape(spec)
    spec_sha = sha256_bytes(spec_bytes)
    inventory_sha = sha256_bytes(inventory_bytes)
    check_time = now or datetime.now(timezone.utc)
    if check_time.tzinfo is None or check_time.utcoffset() is None:
        raise CoverageProbeError("preflight time must be timezone-aware")
    if agent_commit is None:
        agent_commit = _git_head(_git_root(spec_file.parent))
    inventory_state = _validate_inventory_shape(
        inventory, expected_code_commit=str(agent_commit)
    )
    root, agent_clean = _verify_committed_inputs(
        spec_bytes=spec_bytes,
        inventory_bytes=inventory_bytes,
        spec_path=spec_file,
        inventory_path=inventory_file,
        agent_commit=agent_commit,
    )
    timestamp_package = _validate_timestamp_package(
        package,
        raw=package_bytes,
        spec_sha256=spec_sha,
        inventory_sha256=inventory_sha,
        agent_commit=str(agent_commit).lower(),
    )
    timestamp_proof = validate_external_timestamp_proof(
        proof,
        package_manifest_sha256=sha256_bytes(package_bytes),
        before=check_time,
        require_verified_before=True,
    )
    if inventory_state["generated_at"] > _timestamp(
        timestamp_proof["timestamped_at_utc"], "timestamped_at_utc"
    ):
        raise CoverageProbeError(
            "prior specification inventory was finalized after the package timestamp"
        )
    _validate_rights_review(
        rights,
        timestamp_proof_sha256=sha256_bytes(proof_bytes),
        active_at=check_time,
        phase="probe preflight",
    )
    qdata_clean = None
    qdata_head = None
    if qdata_checkout is not None:
        qdata_root, qdata_clean = _verify_qdata_checkout(qdata_checkout)
        qdata_head = _git_head(qdata_root)
    runtime = _runtime_snapshot()

    gates = {
        "SPEC_COMMITTED": True,
        "SPEC_EXTERNALLY_TIMESTAMPED": True,
        "CODE_STATE_CLEAN_AND_BOUND": bool(
            agent_clean and qdata_clean is True and runtime["matches"] is True
        ),
        "OUTPUT_TARGET_NEW": not output_entry_exists and output_outside_worktrees,
        "RIGHTS_REVIEW_RECORDED": True,
    }
    if qdata_checkout is None:
        gates["CODE_STATE_CLEAN_AND_BOUND"] = False
    reasons = [gate for gate, passed in gates.items() if not passed]
    return {
        "schema_version": "stage2_coverage_probe_preflight_v1",
        "status": "READY" if not reasons else "BLOCKED",
        "study_id": STUDY_ID,
        "probe_id": PROBE_ID,
        "checked_at_utc": check_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "spec_sha256": spec_sha,
        "inventory_sha256": inventory_sha,
        "timestamp_package_sha256": sha256_bytes(package_bytes),
        # Bind the exact evidence files, not merely their parsed JSON values.
        # A formatting-only substitution is still a changed evidence artifact
        # and must be caught by the preflight/run TOCTOU check.
        "timestamp_proof_sha256": sha256_bytes(proof_bytes),
        "rights_review_sha256": sha256_bytes(rights_bytes),
        "agent_commit": str(agent_commit).lower(),
        "qdata_commit": qdata_head,
        "agent_clean": bool(agent_clean),
        "qdata_clean": bool(qdata_clean),
        "runtime_contract": runtime,
        "gates": gates,
        "blocking_reason_codes": reasons,
        "request_scope": {
            "dates": list(DATES),
            "symbols": list(SYMBOLS),
            "expected_symbol_date_cells": EXPECTED_CELLS,
            "provider_adapter": EXACT_DATE_ADAPTER,
            "provider_interface": PROVIDER_INTERFACE,
            "qdata_execution_role": "provenance_only_no_import_no_call",
            "price_mode": "raw_unadjusted",
            "adjust_argument": "",
        },
        "scope_boundary": (
            "No factor, return, IC, rank, portfolio, or variant outcome is read by this preflight."
        ),
    }


def _safe_relative(path: str) -> bool:
    if (
        not isinstance(path, str)
        or not path
        or path.startswith("/")
        or "\\" in path
        or "\x00" in path
    ):
        return False
    if len(path) > 1 and path[1] == ":":
        return False
    return ".." not in Path(path).parts and Path(path) != Path(".")


def _finite_number(value: Any) -> bool:
    # ``bool`` is an ``int`` subclass in Python.  Treating True/False as
    # prices or volumes would let a malformed provider payload pass the
    # numeric integrity gate (True becomes 1.0), so reject it explicitly.
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _bar_value(bar: Any, name: str) -> Any:
    if isinstance(bar, Mapping):
        return bar.get(name)
    if is_dataclass(bar):
        return getattr(bar, name, None)
    return getattr(bar, name, None)


def _normalise_bar(bar: Any, *, expected_symbol: str, expected_date: str) -> dict[str, Any]:
    values = {name: _bar_value(bar, name) for name in RAW_FIELDS}
    # Accept a provider mapping's ``date`` alias, but never truncate a
    # timestamp or otherwise coerce a different date into the fixed scope.
    if values["trade_date"] in (None, ""):
        values["trade_date"] = _bar_value(bar, "date")
    values["symbol"] = str(values["symbol"] or "").strip()
    values["trade_date"] = str(values["trade_date"] or "").strip()
    if (
        values["symbol"] != expected_symbol
        or values["trade_date"] != expected_date
        or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", values["trade_date"])
        is None
    ):
        raise CoverageProbeError("provider response contains an out-of-scope bar")
    for name in RAW_FIELDS[2:]:
        if not _finite_number(values[name]):
            raise CoverageProbeError(f"probe bar field {name} is not finite")
        values[name] = float(values[name])
    if not (
        values["open"] > 0
        and values["high"] > 0
        and values["low"] > 0
        and values["close"] > 0
        and values["low"] <= values["open"] <= values["high"]
        and values["low"] <= values["close"] <= values["high"]
        and values["volume"] >= 0
        and values["amount"] >= 0
    ):
        raise CoverageProbeError("probe bar basic OHLCV/amount integrity failed")
    return values


class ExactDateAkShareProbeAdapter:
    """Single-endpoint adapter which cannot invoke QData fallback/lookback code.

    The pinned QData checkout remains in the package provenance because the
    superseded probe named it, but this adapter never imports or calls QData.
    It invokes one pinned AkShare function and wraps that function's transport
    call so the exact date bounds and actual final HTTPS host are observed and
    verified at runtime.
    """

    def __init__(self) -> None:
        try:
            module = importlib.import_module("akshare.stock_feature.stock_hist_em")
        except Exception as exc:
            raise CoverageProbeError("pinned AkShare history module is unavailable") from exc
        module_file = getattr(module, "__file__", None)
        if not isinstance(module_file, str):
            raise CoverageProbeError("pinned AkShare history module has no source file")
        source = Path(module_file).resolve(strict=False)
        if not source.is_file() or sha256_file(source) != AKSHARE_HISTORY_MODULE_SHA256:
            raise CoverageProbeError("AkShare history module bytes differ from the fixed probe")
        function = getattr(module, "stock_zh_a_hist", None)
        if not callable(function) or getattr(function, "__module__", None) != module.__name__:
            raise CoverageProbeError("AkShare history function identity is invalid")
        requests_module = getattr(module, "requests", None)
        if requests_module is None or not callable(getattr(requests_module, "get", None)):
            raise CoverageProbeError("AkShare history transport is unavailable")
        self._module = module
        self._function = function
        self._requests = requests_module

    @staticmethod
    def _expected_secid(symbol: str) -> str:
        market = "1" if symbol.endswith(".SH") else "0"
        return f"{market}.{symbol[:6]}"

    def _fetch_exact_history(self, *, symbol: str, trade_date: str) -> tuple[Any, dict[str, Any]]:
        compact = trade_date.replace("-", "")
        original_get = self._requests.get
        observations: list[dict[str, Any]] = []

        def audited_get(url: Any, *args: Any, **kwargs: Any) -> Any:
            if args or set(kwargs) != {"params", "timeout"}:
                raise CoverageProbeError("AkShare exact-date transport arguments changed")
            parsed = urlparse(url) if isinstance(url, str) else None
            params = kwargs.get("params")
            if (
                len(observations) != 0
                or parsed is None
                or parsed.scheme != "https"
                or parsed.hostname != UPSTREAM_HOST
                or parsed.path != UPSTREAM_PATH
                or not isinstance(params, Mapping)
                or set(params)
                != {"fields1", "fields2", "ut", "klt", "fqt", "secid", "beg", "end"}
                or str(params.get("beg")) != compact
                or str(params.get("end")) != compact
                or str(params.get("secid")) != self._expected_secid(symbol)
                or str(params.get("klt")) != "101"
                or str(params.get("fqt")) != "0"
            ):
                raise CoverageProbeError(
                    "AkShare request is not the fixed exact-date raw daily route"
                )
            try:
                response = original_get(
                    url,
                    params=dict(params),
                    timeout=kwargs.get("timeout"),
                    allow_redirects=False,
                )
            except TypeError as exc:
                raise CoverageProbeError(
                    "AkShare transport cannot enforce the no-redirect contract"
                ) from exc
            final_url = getattr(response, "url", None)
            final = urlparse(final_url) if isinstance(final_url, str) else None
            history = getattr(response, "history", None)
            status_code = getattr(response, "status_code", None)
            if (
                final is None
                or final.scheme != "https"
                or final.hostname != UPSTREAM_HOST
                or final.path != UPSTREAM_PATH
                or history not in (None, [])
                or status_code != 200
            ):
                raise CoverageProbeError(
                    "AkShare response route is redirected or has an unexpected upstream"
                )
            observations.append(
                {
                    "requested_https_host": parsed.hostname,
                    "final_https_host": final.hostname,
                    "endpoint_path": final.path,
                    "redirect_count": 0,
                    "exact_single_date": True,
                    "fallback_attempted": False,
                    "lookback_applied": False,
                }
            )
            return response

        self._module.requests.get = audited_get
        try:
            frame = self._function(
                symbol=symbol[:6],
                period="daily",
                start_date=compact,
                end_date=compact,
                adjust="",
            )
        finally:
            self._module.requests.get = original_get
        if len(observations) != 1:
            raise CoverageProbeError(
                "AkShare exact-date function did not use exactly one verified request"
            )
        return frame, observations[0]

    def fetch_daily_market(
        self, *, trade_date: str, symbols: list[str]
    ) -> dict[str, Any]:
        if (
            trade_date not in DATES
            or not isinstance(symbols, list)
            or len(symbols) != 1
            or symbols[0] not in SYMBOLS
        ):
            raise CoverageProbeError("exact-date adapter request is outside the fixed scope")
        symbol = symbols[0]
        frame, route = self._fetch_exact_history(
            symbol=symbol, trade_date=trade_date
        )
        rows: list[dict[str, Any]] = []
        if frame is not None and not getattr(frame, "empty", True):
            columns = set(getattr(frame, "columns", ()))
            required = {"日期", "开盘", "最高", "最低", "收盘", "成交量", "成交额"}
            if not required.issubset(columns):
                raise CoverageProbeError("AkShare exact-date response schema is invalid")
            for _, item in frame.iterrows():
                rows.append(
                    {
                        "symbol": symbol,
                        "trade_date": str(item["日期"]).strip(),
                        "open": item["开盘"],
                        "high": item["最高"],
                        "low": item["最低"],
                        "close": item["收盘"],
                        "volume": item["成交量"],
                        "amount": item["成交额"],
                    }
                )
        return {
            "provider": UPSTREAM_IDENTITY,
            "daily_bars": rows,
            "route_evidence": route,
        }


def _provider_factory(_qdata_checkout: Path) -> ExactDateAkShareProbeAdapter:
    """Load the dedicated adapter; QData is intentionally not imported."""

    return ExactDateAkShareProbeAdapter()


def _extract_bars(bundle: Any) -> list[Any]:
    if isinstance(bundle, Mapping):
        bars = bundle.get("daily_bars")
    else:
        bars = getattr(bundle, "daily_bars", None)
    if bars is None:
        return []
    try:
        return list(bars)
    except TypeError:
        return []


def _error_class(exc: BaseException) -> str:
    name = type(exc).__name__.lower()
    if "network" in name or "timeout" in name or "connection" in name:
        return "network_error"
    if "validation" in name:
        return "validation_error"
    if "provider" in name:
        return "provider_error"
    return "provider_error"


def _redacted_failure(symbol: str, trade_date: str, category: str) -> dict[str, str]:
    return {"symbol": symbol, "date": trade_date, "category": category}


def _artifact_metadata(path: Path, *, kind: str, row_count: int, symbol_count: int, minimum_date: str | None, maximum_date: str | None) -> dict[str, Any]:
    return {
        "kind": kind,
        "relative_path": path.name,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "row_count": int(row_count),
        "symbol_count": int(symbol_count),
        "minimum_date": minimum_date,
        "maximum_date": maximum_date,
        "schema_sha256": (
            RAW_SCHEMA_SHA256
            if kind != "request_log_private"
            else REQUEST_LOG_SCHEMA_SHA256
        ),
    }


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(RAW_FIELDS), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    try:
        path.chmod(0o600)
    except OSError as exc:
        raise CoverageProbeError("private normalized-bar file permissions could not be restricted") from exc


def _build_receipt_id(receipt_without_id: Mapping[str, Any]) -> str:
    return "sha256:" + sha256_bytes(canonical_json_bytes(dict(receipt_without_id)))


def _all_false_claim_boundaries() -> dict[str, bool]:
    return {
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
    }


def run_probe(
    *,
    spec_path: str | Path,
    prior_inventory_path: str | Path,
    timestamp_package_path: str | Path,
    timestamp_proof_path: str | Path,
    rights_review_path: str | Path,
    qdata_checkout: str | Path,
    output_dir: str | Path,
    agent_commit: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Execute the exact 24-cell source probe and publish a redacted receipt.

    The implementation always uses the Agent's pinned exact-date AkShare
    adapter.  The QData checkout is provenance-only and is never imported.
    """

    preflight = preflight_probe(
        spec_path=spec_path,
        prior_inventory_path=prior_inventory_path,
        timestamp_package_path=timestamp_package_path,
        timestamp_proof_path=timestamp_proof_path,
        rights_review_path=rights_review_path,
        output_dir=output_dir,
        agent_commit=agent_commit,
        qdata_checkout=qdata_checkout,
        now=now,
    )
    if preflight["status"] != "READY":
        raise CoverageProbeError(
            "probe preflight is blocked: " + ",".join(preflight["blocking_reason_codes"])
        )

    output_entry = Path(output_dir).expanduser()
    if _entry_exists(output_entry):
        raise CoverageProbeError("probe output target already exists")
    try:
        output = require_outside_any_git_worktree(
            output_entry, label="probe private output directory"
        )
    except PrivateArtifactPathError as exc:
        raise CoverageProbeError(str(exc)) from exc
    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    # Re-check immediately before the first provider request to close the
    # time-of-check/time-of-use window.  ``mkdir`` with exist_ok=False is the
    # atomic reservation of the staging directory; the final target remains
    # absent until a complete receipt is ready.
    if _entry_exists(output):
        raise CoverageProbeError("probe output target already exists")
    try:
        output = require_outside_any_git_worktree(
            output, label="probe private output directory"
        )
    except PrivateArtifactPathError as exc:
        raise CoverageProbeError(str(exc)) from exc
    qdata_root, qdata_clean = _verify_qdata_checkout(qdata_checkout)
    agent_root = _git_root(Path(spec_path).expanduser().resolve(strict=False).parent)
    if not qdata_clean or not _git_clean(agent_root):
        raise CoverageProbeError("a bound Git worktree changed after probe preflight")
    # Re-read every external control file after the final cleanliness check.
    # A caller must not be able to swap a timestamp, rights record, or
    # inventory between preflight and the first request (TOCTOU closure).
    spec_now = _regular_file(spec_path, "coverage probe specification")
    inventory_now = _regular_file(prior_inventory_path, "prior specification inventory")
    package_now, package_now_bytes = _load_json(
        timestamp_package_path, "coverage probe timestamp package"
    )
    proof_now, proof_now_bytes = _load_json(timestamp_proof_path, "external timestamp proof")
    rights_now, rights_now_bytes = _load_json(rights_review_path, "rights review")
    if (
        sha256_file(spec_now) != preflight["spec_sha256"]
        or sha256_file(inventory_now) != preflight["inventory_sha256"]
        or sha256_bytes(package_now_bytes)
        != preflight["timestamp_package_sha256"]
        or sha256_bytes(proof_now_bytes)
        != preflight["timestamp_proof_sha256"]
        or sha256_bytes(rights_now_bytes)
        != preflight["rights_review_sha256"]
    ):
        raise CoverageProbeError("a bound probe control file changed after preflight")
    request_time = datetime.now(timezone.utc)
    _validate_timestamp_package(
        package_now,
        raw=package_now_bytes,
        spec_sha256=preflight["spec_sha256"],
        inventory_sha256=preflight["inventory_sha256"],
        agent_commit=preflight["agent_commit"],
    )
    validate_external_timestamp_proof(
        proof_now,
        package_manifest_sha256=preflight["timestamp_package_sha256"],
        before=request_time,
        require_verified_before=True,
    )
    _validate_rights_review(
        rights_now,
        timestamp_proof_sha256=sha256_bytes(proof_now_bytes),
        active_at=request_time,
        phase="first provider request",
    )
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=parent))
    # Never let a caller back-date the public receipt through the optional
    # deterministic ``now`` argument used by pure preflight tests.
    execution_time = request_time
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    request_log: list[dict[str, Any]] = []
    route_observations: list[dict[str, Any]] = []
    scope_violation = False
    provider = None
    try:
        provider = _provider_factory(qdata_root)
        if type(provider) is not ExactDateAkShareProbeAdapter:
            raise CoverageProbeError("provider object differs from the fixed adapter contract")
        for trade_date in DATES:
            for symbol in SYMBOLS:
                request_log.append({"symbol": symbol, "date": trade_date, "status": "started"})
                try:
                    bundle = provider.fetch_daily_market(trade_date=trade_date, symbols=[symbol])
                    route = _bar_value(bundle, "route_evidence")
                    if (
                        str(_bar_value(bundle, "provider") or "").strip()
                        != UPSTREAM_IDENTITY
                        or not isinstance(route, Mapping)
                        or set(route)
                        != {
                            "requested_https_host",
                            "final_https_host",
                            "endpoint_path",
                            "redirect_count",
                            "exact_single_date",
                            "fallback_attempted",
                            "lookback_applied",
                        }
                        or route.get("requested_https_host") != UPSTREAM_HOST
                        or route.get("final_https_host") != UPSTREAM_HOST
                        or route.get("endpoint_path") != UPSTREAM_PATH
                        or route.get("redirect_count") != 0
                        or route.get("exact_single_date") is not True
                        or route.get("fallback_attempted") is not False
                        or route.get("lookback_applied") is not False
                    ):
                        raise CoverageProbeError(
                            "provider response route or upstream identity is not verified"
                        )
                    route_observations.append(dict(route))
                    bars = _extract_bars(bundle)
                    identities = {
                        (
                            str(_bar_value(bar, "symbol") or "").strip(),
                            str(
                                _bar_value(bar, "trade_date")
                                or _bar_value(bar, "date")
                                or ""
                            ).strip(),
                        )
                        for bar in bars
                    }
                    expected_cell = (symbol, trade_date)
                    if any(identity != expected_cell for identity in identities):
                        scope_violation = True
                        raise CoverageProbeError(
                            "provider response contains an extra symbol-date cell"
                        )
                    exact = [bar for bar in bars if str(_bar_value(bar, "symbol") or "").strip() == symbol and str(_bar_value(bar, "trade_date") or _bar_value(bar, "date") or "").strip() == trade_date]
                    if len(exact) != 1:
                        if len(exact) > 1:
                            scope_violation = True
                        category = "empty_response" if not exact else "validation_error"
                        failures.append(_redacted_failure(symbol, trade_date, category))
                        request_log[-1] = {"symbol": symbol, "date": trade_date, "status": category}
                        continue
                    row = _normalise_bar(exact[0], expected_symbol=symbol, expected_date=trade_date)
                    rows.append(row)
                    request_log[-1] = {"symbol": symbol, "date": trade_date, "status": "success"}
                except CoverageProbeError:
                    failures.append(_redacted_failure(symbol, trade_date, "validation_error"))
                    request_log[-1] = {"symbol": symbol, "date": trade_date, "status": "validation_error"}
                except Exception as exc:  # provider text is intentionally discarded
                    category = _error_class(exc)
                    failures.append(_redacted_failure(symbol, trade_date, category))
                    request_log[-1] = {"symbol": symbol, "date": trade_date, "status": category}

        # Deterministic order and duplicate detection are checked before any
        # public metadata is emitted.
        rows.sort(key=lambda row: (row["trade_date"], row["symbol"]))
        cells = [(row["symbol"], row["trade_date"]) for row in rows]
        expected_cells = {(symbol, trade_date) for trade_date in DATES for symbol in SYMBOLS}
        observed_set = set(cells)
        duplicate_count = len(cells) - len(observed_set)
        missing = sorted(expected_cells - observed_set)
        extra = sorted(observed_set - expected_cells)
        complete = not failures and not missing and not extra and duplicate_count == 0 and len(cells) == EXPECTED_CELLS
        values_valid = complete  # every row passed _normalise_bar
        scope_valid = (
            not scope_violation
            and not extra
            and all(cell in expected_cells for cell in observed_set)
        )
        failures_accounted = len(request_log) == EXPECTED_CELLS and all(
            item.get("status") in {"success", "empty_response", "validation_error", "provider_error", "network_error"}
            for item in request_log
        )
        route_valid = len(route_observations) == EXPECTED_CELLS and all(
            route.get("requested_https_host") == UPSTREAM_HOST
            and route.get("final_https_host") == UPSTREAM_HOST
            and route.get("endpoint_path") == UPSTREAM_PATH
            and route.get("redirect_count") == 0
            and route.get("exact_single_date") is True
            and route.get("fallback_attempted") is False
            and route.get("lookback_applied") is False
            for route in route_observations
        )
        route_evidence = {
            "request_count": len(route_observations),
            "requested_https_host": UPSTREAM_HOST if route_observations else None,
            "final_https_host": UPSTREAM_HOST if route_observations else None,
            "endpoint_path": UPSTREAM_PATH if route_observations else None,
            "redirect_count": sum(
                int(route["redirect_count"]) for route in route_observations
            ),
            "all_requests_exact_single_date": route_valid,
            "fallback_attempted": any(
                route["fallback_attempted"] for route in route_observations
            ),
            "lookback_applied": any(
                route["lookback_applied"] for route in route_observations
            ),
        }
        gates = {gate: True for gate in GATE_IDS}
        gates.update(
            {
                "EXACT_REQUEST_SCOPE": scope_valid,
                "COMPLETE_CELL_COVERAGE": complete,
                "PROBE_SPECIFIC_RAW_BAR_FIELDS": values_valid,
                "BASIC_VALUE_INTEGRITY": values_valid,
                "ROUTE_AND_UPSTREAM_VERIFIED": route_valid,
                "RAW_MODE_ATTESTED": route_valid,
                "FAILURES_ACCOUNTED_FOR": failures_accounted,
                "ARTIFACT_HASHES_VERIFIED": False,
            }
        )
        # The five preflight gates are copied from the preflight result.  They
        # are not recomputed from a mutable receipt field.
        gates.update(preflight["gates"])
        status = "PASSED" if all(gates.values()) else "BLOCKED"
        normalized_path = staging / "normalized_bars.private.csv"
        request_log_path = staging / "request_log.private.json"
        _write_csv(normalized_path, rows)
        request_log_path.write_bytes(canonical_json_bytes(request_log))
        try:
            request_log_path.chmod(0o600)
        except OSError as exc:
            raise CoverageProbeError("private request-log permissions could not be restricted") from exc
        min_date = min((row["trade_date"] for row in rows), default=None)
        max_date = max((row["trade_date"] for row in rows), default=None)
        artifacts = [
            _artifact_metadata(
                normalized_path,
                kind="normalized_private",
                row_count=len(rows),
                symbol_count=len({row["symbol"] for row in rows}),
                minimum_date=min_date,
                maximum_date=max_date,
            ),
            _artifact_metadata(
                request_log_path,
                kind="request_log_private",
                row_count=len(request_log),
                symbol_count=len(SYMBOLS),
                minimum_date=DATES[0],
                maximum_date=DATES[-1],
            ),
        ]
        # Verify the just-written private files before constructing the receipt.
        gates["ARTIFACT_HASHES_VERIFIED"] = all(
            _verify_artifact_metadata(staging, artifact) for artifact in artifacts
        )
        status = "PASSED" if all(gates.values()) else "BLOCKED"
        # Re-read and revalidate the exact rights chain immediately before
        # publishing the receipt. This catches both a mid-run proof/review
        # substitution and a finite contract that expired during collection.
        publication_time = datetime.now(timezone.utc)
        proof_publish, proof_publish_bytes = _load_json(
            timestamp_proof_path, "external timestamp proof"
        )
        rights_publish, rights_publish_bytes = _load_json(
            rights_review_path, "rights review"
        )
        if (
            sha256_bytes(proof_publish_bytes) != preflight["timestamp_proof_sha256"]
            or sha256_bytes(rights_publish_bytes) != preflight["rights_review_sha256"]
        ):
            raise CoverageProbeError(
                "a bound probe rights-chain file changed before receipt publication"
            )
        validate_external_timestamp_proof(
            proof_publish,
            package_manifest_sha256=preflight["timestamp_package_sha256"],
            before=publication_time,
            require_verified_before=True,
        )
        _validate_rights_review(
            rights_publish,
            timestamp_proof_sha256=sha256_bytes(proof_publish_bytes),
            active_at=publication_time,
            phase="receipt publication",
        )
        proof, rights = proof_publish, rights_publish
        receipt: dict[str, Any] = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "study_id": STUDY_ID,
            "probe_id": PROBE_ID,
            "receipt_id": None,
            "spec_sha256": preflight["spec_sha256"],
            "timestamp_package": package_now,
            "status": status,
            "executed_at_utc": execution_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "external_timestamp_proof": proof,
            "rights_review_sha256": preflight["rights_review_sha256"],
            "repository_state": {
                "agent_commit": preflight["agent_commit"],
                "qdata_commit": preflight["qdata_commit"],
                "agent_clean": preflight["agent_clean"],
                "qdata_clean": preflight["qdata_clean"],
                "python_version": preflight["runtime_contract"]["actual"]["python_version"],
                "akshare_version": preflight["runtime_contract"]["actual"]["akshare_version"],
            },
            "request": {
                "provider_adapter": EXACT_DATE_ADAPTER,
                "provider_interface": PROVIDER_INTERFACE,
                "upstream_provider_identity": (
                    UPSTREAM_IDENTITY if route_observations else "not_verified"
                ),
                "route_evidence": route_evidence,
                "dates": list(DATES),
                "symbols": list(SYMBOLS),
                "price_mode": "raw_unadjusted",
                "adjust_argument": "",
            },
            "artifacts": artifacts,
            "coverage": {
                "expected_symbol_date_cells": EXPECTED_CELLS,
                "observed_symbol_date_cells": len(observed_set),
                "missing_symbol_date_cell_count": len(missing),
                "duplicate_symbol_date_cells": duplicate_count,
                "extra_symbol_date_cells": len(extra),
            },
            "field_quality": {
                "all_required_raw_bar_fields_valid": bool(values_valid),
                "scope_and_cell_identity_valid": bool(scope_valid),
            },
            "failures": {
                category: sum(
                    failure["category"] == category for failure in failures
                )
                for category in (
                    "empty_response",
                    "validation_error",
                    "provider_error",
                    "network_error",
                )
            },
            "gates": gates,
            "rights": {
                "review_status": rights.get("status"),
                "raw_redistribution_allowed": False,
                "aggregate_receipt_publication_allowed": rights.get("aggregate_receipt_publication_allowed") is True,
            },
            "publication_consent": {
                "review_status": rights.get("status"),
                **{
                    field: rights.get(field) is True
                    for field in PUBLICATION_CONSENT_FIELDS - {"review_status"}
                },
            },
            "claim_boundaries": _all_false_claim_boundaries(),
        }
        _validate_public_receipt_privacy(
            receipt, label="coverage probe public receipt"
        )
        unsigned = dict(receipt)
        unsigned.pop("receipt_id")
        receipt["receipt_id"] = _build_receipt_id(unsigned)
        # Manifest is deliberately written last among private files.  It does
        # not contain its own hash, avoiding a cycle.
        manifest = {
            "schema_version": PRIVATE_MANIFEST_SCHEMA_VERSION,
            "spec_sha256": preflight["spec_sha256"],
            "timestamp_package_sha256": preflight["timestamp_package_sha256"],
            "rights_review_sha256": preflight["rights_review_sha256"],
            "agent_commit": preflight["agent_commit"],
            "qdata_commit": preflight["qdata_commit"],
            "request_scope": receipt["request"],
            "artifacts": artifacts,
            "gates": gates,
            "receipt_sha256": sha256_bytes(canonical_json_bytes(receipt)),
            "raw_rows_private": True,
        }
        manifest_path = staging / "private_manifest.json"
        receipt_path = staging / "receipt.json"
        # The receipt is complete before the manifest is materialised.  The
        # manifest is the final private control file by protocol, so an
        # interrupted run can never leave a seemingly complete manifest that
        # predates a later receipt mutation.
        receipt_path.write_bytes(canonical_json_bytes(receipt))
        manifest_path.write_bytes(canonical_json_bytes(manifest))
        try:
            manifest_path.chmod(0o600)
            receipt_path.chmod(0o600)
        except OSError as exc:
            raise CoverageProbeError("private probe control-file permissions could not be restricted") from exc
        if _entry_exists(output):
            raise CoverageProbeError("probe output target appeared during execution")
        try:
            require_outside_any_git_worktree(
                output, label="probe private output directory"
            )
        except PrivateArtifactPathError as exc:
            raise CoverageProbeError(str(exc)) from exc
        try:
            publish_private_directory_atomic_exclusive(
                staging,
                output,
                label="probe private output directory",
            )
        except PrivateArtifactPathError as exc:
            raise CoverageProbeError(str(exc)) from exc
        return receipt
    except Exception:
        # Keep no partial output.  The caller receives a fail-closed error and
        # can rerun only after selecting a fresh output target.
        try:
            _remove_tree(staging)
        except OSError:
            pass
        raise


def _verify_artifact_metadata(root: Path, artifact: Mapping[str, Any]) -> bool:
    relative = artifact.get("relative_path")
    if not _safe_relative(relative):
        return False
    target = (root / relative).resolve(strict=False)
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return False
    if not target.is_file() or target.is_symlink():
        return False
    return (
        _sha256(artifact.get("sha256"))
        and sha256_file(target) == artifact.get("sha256")
        and target.stat().st_size == artifact.get("size_bytes")
    )


def _artifact_target(root: Path, artifact: Mapping[str, Any]) -> Path:
    """Resolve an artifact path while rejecting symlinked parent components."""

    relative = artifact.get("relative_path")
    if not _safe_relative(relative):
        raise CoverageProbeError("private probe artifact path is unsafe")
    parts = Path(relative).parts
    if parts[-1] in {"receipt.json", "private_manifest.json"}:
        raise CoverageProbeError("private probe artifact shadows a control file")
    cursor = root
    for part in parts[:-1]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise CoverageProbeError("private probe artifact has a symlinked parent")
    entry = root.joinpath(*parts)
    if entry.is_symlink():
        raise CoverageProbeError("private probe artifact is a symlink")
    target = (root / relative).resolve(strict=False)
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise CoverageProbeError("private probe artifact escapes its root") from exc
    return target


def _date_range(values: Sequence[str]) -> tuple[str | None, str | None]:
    if not values:
        return None, None
    ordered = sorted(values)
    return ordered[0], ordered[-1]


def _verify_private_artifact_content(
    root: Path,
    artifact: Mapping[str, Any],
) -> dict[str, Any]:
    """Inspect private files only when an operator explicitly supplies a root.

    The public receipt intentionally contains no rows.  This helper therefore
    runs at the private-audit boundary and returns aggregate identities rather
    than exposing any row payload to callers.
    """

    target = _artifact_target(root, artifact)
    kind = artifact.get("kind")
    result: dict[str, Any] = {
        "kind": kind,
        "cells": set(),
        "failure_cells": set(),
        "request_statuses": {},
    }
    if kind == "request_log_private":
        try:
            raw = target.read_bytes()
            value = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CoverageProbeError("private request log is not valid UTF-8 JSON") from exc
        if raw != canonical_json_bytes(value) or not isinstance(value, list):
            raise CoverageProbeError("private request log must be canonical JSON")
        if len(value) != EXPECTED_CELLS:
            raise CoverageProbeError("private request log does not cover the fixed request scope")
        seen: set[tuple[str, str]] = set()
        allowed = {"started", "success", "empty_response", "validation_error", "provider_error", "network_error"}
        for item in value:
            if not isinstance(item, Mapping) or set(item) != {"symbol", "date", "status"}:
                raise CoverageProbeError("private request log entry is invalid")
            symbol, date, status = item.get("symbol"), item.get("date"), item.get("status")
            cell = (symbol, date)
            if symbol not in SYMBOLS or date not in DATES or cell in seen or status not in allowed:
                raise CoverageProbeError("private request log entry is outside the fixed scope")
            seen.add(cell)
            result["request_statuses"][cell] = status
            if status != "success":
                result["failure_cells"].add(cell)
        if seen != {(symbol, date) for date in DATES for symbol in SYMBOLS}:
            raise CoverageProbeError("private request log cells are incomplete")
        if artifact.get("row_count") != EXPECTED_CELLS or artifact.get("symbol_count") != len(SYMBOLS):
            raise CoverageProbeError("private request log dimensions are inconsistent")
        # The request log's dates describe attempted requests, not observed
        # bars.  Its range is therefore always the fixed two-date interval.
        if (artifact.get("minimum_date"), artifact.get("maximum_date")) != (DATES[0], DATES[-1]):
            raise CoverageProbeError("private request log date range is inconsistent")
        return result

    if kind in {"normalized_private", "raw_private"}:
        # Raw vendor payloads are intentionally opaque: only their hash and
        # dimensions are checked.  The normalized CSV emitted by this module
        # has a stable schema and can be checked without revealing rows.
        if kind == "raw_private":
            return result
        try:
            with target.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames != list(RAW_FIELDS):
                    raise CoverageProbeError("private normalized-bar CSV schema is invalid")
                seen: set[tuple[str, str]] = set()
                dates: list[str] = []
                symbols: set[str] = set()
                for row in reader:
                    if row is None or None in row:
                        raise CoverageProbeError("private normalized-bar CSV row is malformed")
                    symbol = str(row.get("symbol") or "")
                    date = str(row.get("trade_date") or "").strip()
                    normalized = _normalise_bar(
                        row,
                        expected_symbol=symbol,
                        expected_date=date,
                    )
                    cell = (normalized["symbol"], normalized["trade_date"])
                    if cell in seen or cell not in {
                        (candidate_symbol, candidate_date)
                        for candidate_date in DATES
                        for candidate_symbol in SYMBOLS
                    }:
                        raise CoverageProbeError("private normalized-bar CSV cell is duplicate or out of scope")
                    seen.add(cell)
                    symbols.add(normalized["symbol"])
                    dates.append(normalized["trade_date"])
        except OSError as exc:
            raise CoverageProbeError("private normalized-bar CSV cannot be read") from exc
        minimum_date, maximum_date = _date_range(dates)
        if (
            artifact.get("row_count") != len(seen)
            or artifact.get("symbol_count") != len(symbols)
            or artifact.get("minimum_date") != minimum_date
            or artifact.get("maximum_date") != maximum_date
        ):
            raise CoverageProbeError("private normalized-bar metadata is inconsistent")
        result["cells"] = seen
        return result
    raise CoverageProbeError("unsupported private probe artifact kind")


def _remove_tree(path: Path) -> None:
    # Avoid shutil.rmtree on an arbitrary user path: ``path`` is always the
    # mkdtemp staging directory created by ``run_probe``.
    import shutil

    if path.name.startswith(".") and path.is_dir():
        shutil.rmtree(path)


def verify_probe_artifacts(
    receipt_path: str | Path,
    *,
    artifact_root: str | Path | None = None,
    spec_path: str | Path | None = None,
    prior_inventory_path: str | Path | None = None,
) -> dict[str, Any]:
    """Verify a public probe receipt and, optionally, its private artifacts.

    A ``PASSED`` receipt is delegated to the maintained Stage-2 validator so
    both commands share the exact fixed contract.  ``BLOCKED`` receipts are
    accepted here for auditability but can never satisfy ``run-stage2``.
    """

    receipt_file = _regular_file(receipt_path, "coverage probe receipt")
    receipt, raw = _load_json(receipt_file, "coverage probe receipt")
    if raw != canonical_json_bytes(receipt):
        raise CoverageProbeError("coverage probe receipt must be canonical JSON")
    _validate_public_receipt_privacy(
        receipt, label="coverage probe public receipt"
    )
    if set(receipt) != RECEIPT_FIELDS:
        raise CoverageProbeError("coverage probe receipt fields differ from the fixed schema")
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        raise CoverageProbeError("unsupported coverage probe receipt schema")
    if receipt.get("study_id") != STUDY_ID or receipt.get("probe_id") != PROBE_ID:
        raise CoverageProbeError("coverage probe receipt study or probe identifier is invalid")
    unsigned = dict(receipt)
    receipt_id = unsigned.pop("receipt_id", None)
    if receipt_id != _build_receipt_id(unsigned):
        raise CoverageProbeError("coverage probe receipt identifier is not canonical")
    spec_sha = receipt.get("spec_sha256")
    if not _sha256(spec_sha):
        raise CoverageProbeError("coverage probe receipt spec hash is invalid")
    if receipt.get("status") not in {"PASSED", "BLOCKED", "ERROR"}:
        raise CoverageProbeError("coverage probe receipt status is invalid")
    executed_at = _timestamp(
        receipt.get("executed_at_utc"), "coverage probe execution timestamp"
    )
    timestamp_package = receipt.get("timestamp_package")
    if (
        not isinstance(timestamp_package, Mapping)
        or set(timestamp_package) != TIMESTAMP_PACKAGE_FIELDS
        or timestamp_package.get("schema_version")
        != TIMESTAMP_PACKAGE_SCHEMA_VERSION
        or timestamp_package.get("study_id") != STUDY_ID
        or timestamp_package.get("probe_id") != PROBE_ID
        or timestamp_package.get("spec_path") != SPEC_REPOSITORY_PATH
        or timestamp_package.get("spec_sha256") != spec_sha
        or timestamp_package.get("prior_specification_inventory_path")
        != INVENTORY_REPOSITORY_PATH
        or not _sha256(
            timestamp_package.get("prior_specification_inventory_sha256")
        )
        or not _git_sha(timestamp_package.get("agent_commit"))
    ):
        raise CoverageProbeError("coverage probe timestamp package is invalid")
    timestamp_package_sha = sha256_bytes(canonical_json_bytes(timestamp_package))
    proof = receipt.get("external_timestamp_proof")
    validate_external_timestamp_proof(
        proof,
        package_manifest_sha256=timestamp_package_sha,
        before=executed_at,
        require_verified_before=True,
    )
    rights_review_sha256 = receipt.get("rights_review_sha256")
    if not _sha256(rights_review_sha256):
        raise CoverageProbeError("coverage probe receipt rights-review hash is invalid")
    request = receipt.get("request")
    if (
        not isinstance(request, Mapping)
        or set(request)
        != {
            "provider_adapter",
            "provider_interface",
            "upstream_provider_identity",
            "route_evidence",
            "dates",
            "symbols",
            "price_mode",
            "adjust_argument",
        }
        or request.get("provider_adapter")
        != EXACT_DATE_ADAPTER
        or request.get("provider_interface") != PROVIDER_INTERFACE
        or request.get("dates") != list(DATES)
        or request.get("symbols") != list(SYMBOLS)
        or request.get("price_mode") != "raw_unadjusted"
        or request.get("adjust_argument") != ""
        or not _meaningful(request.get("upstream_provider_identity"))
    ):
        raise CoverageProbeError("coverage probe receipt request scope is invalid")
    route = request.get("route_evidence")
    if (
        not isinstance(route, Mapping)
        or set(route) != ROUTE_EVIDENCE_FIELDS
        or isinstance(route.get("request_count"), bool)
        or not isinstance(route.get("request_count"), int)
        or not 0 <= route["request_count"] <= EXPECTED_CELLS
        or route.get("requested_https_host") not in {None, UPSTREAM_HOST}
        or route.get("final_https_host") not in {None, UPSTREAM_HOST}
        or route.get("endpoint_path") not in {None, UPSTREAM_PATH}
        or isinstance(route.get("redirect_count"), bool)
        or not isinstance(route.get("redirect_count"), int)
        or route["redirect_count"] < 0
        or any(
            not isinstance(route.get(key), bool)
            for key in (
                "all_requests_exact_single_date",
                "fallback_attempted",
                "lookback_applied",
            )
        )
    ):
        raise CoverageProbeError("coverage probe route evidence is invalid")
    if receipt.get("status") == "PASSED" and route != {
        "request_count": EXPECTED_CELLS,
        "requested_https_host": UPSTREAM_HOST,
        "final_https_host": UPSTREAM_HOST,
        "endpoint_path": UPSTREAM_PATH,
        "redirect_count": 0,
        "all_requests_exact_single_date": True,
        "fallback_attempted": False,
        "lookback_applied": False,
    }:
        raise CoverageProbeError("passed coverage probe route is not exact and fail-closed")
    repository_state = receipt.get("repository_state")
    if (
        not isinstance(repository_state, Mapping)
        or set(repository_state)
        != {
            "agent_commit",
            "qdata_commit",
            "agent_clean",
            "qdata_clean",
            "python_version",
            "akshare_version",
        }
        or not _git_sha(repository_state.get("agent_commit"))
        or repository_state.get("qdata_commit") != QDATA_COMMIT
        or not isinstance(repository_state.get("agent_clean"), bool)
        or not isinstance(repository_state.get("qdata_clean"), bool)
        or not _meaningful(repository_state.get("python_version"))
        or not _meaningful(repository_state.get("akshare_version"))
    ):
        raise CoverageProbeError("coverage probe receipt repository state is invalid")
    if timestamp_package.get("agent_commit") != repository_state.get("agent_commit"):
        raise CoverageProbeError(
            "coverage probe timestamp package does not bind the receipt Agent commit"
        )
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise CoverageProbeError("coverage probe receipt artifacts are missing")
    paths: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            raise CoverageProbeError("coverage probe artifact metadata is invalid")
        if set(artifact) != ARTIFACT_FIELDS:
            raise CoverageProbeError("coverage probe artifact metadata fields are invalid")
        relative = artifact.get("relative_path")
        kind = artifact.get("kind")
        if (
            not _safe_relative(relative)
            or relative in paths
            or relative in {"receipt.json", "private_manifest.json"}
        ):
            raise CoverageProbeError("coverage probe artifact paths must be unique and relative")
        if kind not in {"raw_private", "normalized_private", "request_log_private"}:
            raise CoverageProbeError("coverage probe artifact kind is unsupported")
        paths.add(relative)
        for key in ("sha256", "schema_sha256"):
            if not _sha256(artifact.get(key)):
                raise CoverageProbeError("coverage probe artifact hash is invalid")
        expected_schema = (
            REQUEST_LOG_SCHEMA_SHA256
            if kind == "request_log_private"
            else RAW_SCHEMA_SHA256
        )
        if artifact.get("schema_sha256") != expected_schema:
            raise CoverageProbeError("coverage probe artifact schema hash is invalid")
        for key in ("size_bytes", "row_count", "symbol_count"):
            value = artifact.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise CoverageProbeError("coverage probe artifact dimensions are invalid")
        if artifact.get("symbol_count", 0) > len(SYMBOLS):
            raise CoverageProbeError("coverage probe artifact symbol count exceeds fixed scope")
        for key in ("minimum_date", "maximum_date"):
            value = artifact.get(key)
            if value is not None:
                if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
                    raise CoverageProbeError(f"artifact {key} must be an ISO date")
                _timestamp(value + "T00:00:00+00:00", f"artifact {key}")
        if artifact.get("minimum_date") and artifact.get("maximum_date") and artifact["minimum_date"] > artifact["maximum_date"]:
            raise CoverageProbeError("coverage probe artifact date range is reversed")
    rights = receipt.get("rights")
    if not isinstance(rights, Mapping) or rights.get("raw_redistribution_allowed") is not False:
        raise CoverageProbeError("public probe receipt must keep raw redistribution disabled")
    coverage = receipt.get("coverage")
    if (
        not isinstance(coverage, Mapping)
        or set(coverage)
        != {
            "expected_symbol_date_cells",
            "observed_symbol_date_cells",
            "missing_symbol_date_cell_count",
            "duplicate_symbol_date_cells",
            "extra_symbol_date_cells",
        }
        or coverage.get("expected_symbol_date_cells") != EXPECTED_CELLS
        or not isinstance(coverage.get("observed_symbol_date_cells"), int)
        or isinstance(coverage.get("observed_symbol_date_cells"), bool)
        or not 0 <= coverage["observed_symbol_date_cells"] <= EXPECTED_CELLS
        or not isinstance(coverage.get("missing_symbol_date_cell_count"), int)
        or isinstance(coverage.get("missing_symbol_date_cell_count"), bool)
        or not 0 <= coverage["missing_symbol_date_cell_count"] <= EXPECTED_CELLS
        or not isinstance(coverage.get("duplicate_symbol_date_cells"), int)
        or isinstance(coverage.get("duplicate_symbol_date_cells"), bool)
        or coverage["duplicate_symbol_date_cells"] < 0
        or not isinstance(coverage.get("extra_symbol_date_cells"), int)
        or isinstance(coverage.get("extra_symbol_date_cells"), bool)
        or coverage["extra_symbol_date_cells"] < 0
    ):
        raise CoverageProbeError("coverage probe receipt coverage accounting is invalid")
    if (
        coverage["observed_symbol_date_cells"]
        + coverage["missing_symbol_date_cell_count"]
        != EXPECTED_CELLS
    ):
        raise CoverageProbeError("coverage probe observed/missing cell accounting is inconsistent")
    if coverage["extra_symbol_date_cells"] and receipt.get("status") == "PASSED":
        raise CoverageProbeError("passed coverage probe receipt reports extra cells")
    field_quality = receipt.get("field_quality")
    if not isinstance(field_quality, Mapping):
        raise CoverageProbeError("coverage probe receipt field-quality evidence is invalid")
    if not field_quality or any(not isinstance(key, str) for key in field_quality):
        raise CoverageProbeError("coverage probe receipt field-quality evidence is invalid")
    if set(field_quality) != {
        "all_required_raw_bar_fields_valid",
        "scope_and_cell_identity_valid",
    }:
        raise CoverageProbeError("coverage probe receipt field-quality evidence is incomplete")
    if any(not isinstance(value, bool) for value in field_quality.values()):
        raise CoverageProbeError("coverage probe receipt field-quality evidence is invalid")
    failures = receipt.get("failures")
    failure_categories = {
        "empty_response",
        "validation_error",
        "provider_error",
        "network_error",
    }
    if (
        not isinstance(failures, Mapping)
        or set(failures) != failure_categories
        or any(
            isinstance(failures.get(category), bool)
            or not isinstance(failures.get(category), int)
            or failures[category] < 0
            for category in failure_categories
        )
    ):
        raise CoverageProbeError("coverage probe receipt failure evidence is invalid")
    if sum(failures.values()) != coverage["missing_symbol_date_cell_count"]:
        raise CoverageProbeError(
            "coverage probe aggregate failures must account for every missing cell"
        )
    gates = receipt.get("gates")
    if not isinstance(gates, Mapping) or set(gates) != set(GATE_IDS) or any(
        not isinstance(gates[key], bool) for key in GATE_IDS
    ):
        raise CoverageProbeError("coverage probe receipt gate evidence is invalid")
    claim_boundaries = receipt.get("claim_boundaries")
    if (
        not isinstance(claim_boundaries, Mapping)
        or claim_boundaries != _all_false_claim_boundaries()
    ):
        raise CoverageProbeError("coverage probe receipt claim boundaries are invalid")
    if (
        not isinstance(rights, Mapping)
        or set(rights)
        != {
            "review_status",
            "raw_redistribution_allowed",
            "aggregate_receipt_publication_allowed",
        }
        or rights.get("review_status") not in {"verified", "pending", "blocked"}
        or not isinstance(rights.get("raw_redistribution_allowed"), bool)
        or not isinstance(rights.get("aggregate_receipt_publication_allowed"), bool)
    ):
        raise CoverageProbeError("coverage probe receipt rights evidence is invalid")
    publication_consent = receipt.get("publication_consent")
    if (
        not isinstance(publication_consent, Mapping)
        or set(publication_consent) != PUBLICATION_CONSENT_FIELDS
        or publication_consent.get("review_status")
        not in {"verified", "pending", "blocked"}
        or any(
            not isinstance(publication_consent.get(field), bool)
            for field in PUBLICATION_CONSENT_FIELDS - {"review_status"}
        )
    ):
        raise CoverageProbeError(
            "coverage probe publication consent boundary is invalid"
        )
    if receipt.get("status") == "PASSED" and (
        not all(gates.values())
        or any(failures.values())
        or rights.get("review_status") != "verified"
        or rights.get("aggregate_receipt_publication_allowed") is not True
        or publication_consent.get("review_status") != "verified"
        or any(
            publication_consent.get(field) is not True
            for field in PUBLICATION_CONSENT_FIELDS - {"review_status"}
        )
    ):
        raise CoverageProbeError("passed coverage probe receipt contains a failed gate")
    if receipt.get("status") == "PASSED" and coverage != {
        "expected_symbol_date_cells": EXPECTED_CELLS,
        "observed_symbol_date_cells": EXPECTED_CELLS,
        "missing_symbol_date_cell_count": 0,
        "duplicate_symbol_date_cells": 0,
        "extra_symbol_date_cells": 0,
    }:
        raise CoverageProbeError(
            "passed coverage probe receipt does not establish canonical complete coverage"
        )
    if receipt.get("status") == "PASSED" and field_quality != {
        "all_required_raw_bar_fields_valid": True,
        "scope_and_cell_identity_valid": True,
    }:
        raise CoverageProbeError(
            "passed coverage probe receipt field-quality evidence is not fully true"
        )
    if (
        receipt.get("status") in {"BLOCKED", "ERROR"}
        and all(gates.values())
        and not any(failures.values())
    ):
        raise CoverageProbeError("blocked coverage probe receipt has no blocking evidence")
    if spec_path is not None:
        spec_file = _regular_file(spec_path, "coverage probe specification")
        spec_bytes = spec_file.read_bytes()
        if sha256_bytes(spec_bytes) != spec_sha:
            raise CoverageProbeError("coverage probe receipt spec hash differs from supplied spec")
    else:
        spec_file = None
    if prior_inventory_path is not None:
        inventory_file = _regular_file(
            prior_inventory_path, "prior specification inventory"
        )
        if sha256_file(inventory_file) != timestamp_package.get(
            "prior_specification_inventory_sha256"
        ):
            raise CoverageProbeError(
                "coverage probe timestamp package inventory hash differs from supplied inventory"
            )
    if artifact_root is not None:
        root_entry = Path(artifact_root).expanduser()
        if root_entry.is_symlink():
            raise CoverageProbeError("probe artifact root is not a regular directory")
        root = root_entry.resolve(strict=False)
        if not root.is_dir() or root.is_symlink():
            raise CoverageProbeError("probe artifact root is not a regular directory")
        private_evidence: list[dict[str, Any]] = []
        seen_kinds: set[str] = set()
        for artifact in artifacts:
            if artifact["kind"] in seen_kinds:
                raise CoverageProbeError("private probe artifact kinds must be unique")
            seen_kinds.add(artifact["kind"])
            if not _verify_artifact_metadata(root, artifact):
                raise CoverageProbeError("private probe artifact hash or size mismatch")
            private_evidence.append(_verify_private_artifact_content(root, artifact))
        if not {"normalized_private", "request_log_private"}.issubset(seen_kinds):
            raise CoverageProbeError(
                "private probe audit requires normalized bars and the exact request log"
            )
        expected = paths | {"receipt.json", "private_manifest.json"}
        actual: set[str] = set()
        actual_dirs: set[str] = set()
        for item in root.rglob("*"):
            if item.is_symlink():
                raise CoverageProbeError("probe private artifact root contains a symlink")
            if item.is_file():
                actual.add(str(item.relative_to(root)))
            elif item.is_dir():
                actual_dirs.add(str(item.relative_to(root)))
        if actual != expected:
            raise CoverageProbeError("probe private artifact file set is not closed")
        expected_dirs: set[str] = set()
        for relative in expected:
            for parent_dir in Path(relative).parents:
                if str(parent_dir) != ".":
                    expected_dirs.add(str(parent_dir))
        if actual_dirs != expected_dirs:
            raise CoverageProbeError("probe private artifact directory set is not closed")
        receipt_on_disk = root / "receipt.json"
        if receipt_on_disk.read_bytes() != raw:
            raise CoverageProbeError("private receipt bytes differ from verified receipt")
        manifest_file = root / "private_manifest.json"
        manifest, manifest_raw = _load_json(manifest_file, "private probe manifest")
        if manifest_raw != canonical_json_bytes(manifest):
            raise CoverageProbeError("private probe manifest must be canonical JSON")
        if (
            set(manifest)
            != {
                "schema_version",
                "spec_sha256",
                "timestamp_package_sha256",
                "rights_review_sha256",
                "agent_commit",
                "qdata_commit",
                "request_scope",
                "artifacts",
                "gates",
                "receipt_sha256",
                "raw_rows_private",
            }
            or
            manifest.get("schema_version") != PRIVATE_MANIFEST_SCHEMA_VERSION
            or manifest.get("spec_sha256") != spec_sha
            or manifest.get("timestamp_package_sha256")
            != sha256_bytes(canonical_json_bytes(receipt["timestamp_package"]))
            or manifest.get("rights_review_sha256") != rights_review_sha256
            or manifest.get("agent_commit") != repository_state.get("agent_commit")
            or manifest.get("qdata_commit") != repository_state.get("qdata_commit")
            or manifest.get("request_scope") != request
            or manifest.get("artifacts") != artifacts
            or not isinstance(manifest.get("gates"), Mapping)
            or manifest.get("gates") != dict(gates)
            or manifest.get("receipt_sha256") != sha256_bytes(raw)
            or manifest.get("raw_rows_private") is not True
        ):
            raise CoverageProbeError("private probe manifest does not bind the receipt")
        normalized_cells: set[tuple[str, str]] = set()
        request_statuses: dict[tuple[str, str], str] = {}
        private_failures: set[tuple[str, str]] = set()
        for evidence in private_evidence:
            normalized_cells.update(evidence["cells"])
            request_statuses.update(evidence["request_statuses"])
            private_failures.update(evidence["failure_cells"])
        if normalized_cells:
            expected_observed = coverage["observed_symbol_date_cells"]
            if len(normalized_cells) != expected_observed:
                raise CoverageProbeError("private normalized bars disagree with receipt coverage")
        if request_statuses:
            log_failure_cells = {
                cell for cell, status in request_statuses.items() if status != "success"
            }
            if private_failures != log_failure_cells:
                raise CoverageProbeError("private request-log failure identities are inconsistent")
            log_success_cells = {
                cell for cell, status in request_statuses.items() if status == "success"
            }
            if log_success_cells != normalized_cells:
                raise CoverageProbeError("private request log successes disagree with normalized bars")
            private_category_counts = {
                category: sum(
                    status == category for status in request_statuses.values()
                )
                for category in failures
            }
            if (
                private_category_counts != dict(failures)
                or len(log_failure_cells)
                != coverage["missing_symbol_date_cell_count"]
                or len(log_success_cells)
                != coverage["observed_symbol_date_cells"]
            ):
                raise CoverageProbeError(
                    "private exact-cell request log disagrees with public aggregate receipt"
                )
    # For a passed receipt, invoke the authoritative Stage-2 validator.  This
    # additionally checks commit binding and all fixed claim/gate fields.
    if receipt.get("status") == "PASSED":
        try:
            from .confirmatory_study import _validate_stage2_coverage_probe_receipt

            if spec_file is None:
                # A published receipt is commonly copied beside the two
                # probe-control files (rather than into a repository root).
                # Try the repository-relative location first for a checkout,
                # then the colocated spec for a self-contained package.
                candidate = receipt_file.parent / SPEC_REPOSITORY_PATH
                spec_path = candidate if candidate.is_file() else receipt_file.parent / "coverage_probe_spec.v2.json"
            else:
                spec_path = spec_file
            if prior_inventory_path is not None:
                inventory_path = prior_inventory_path
            else:
                # When --spec is supplied, the inventory is its sibling in
                # the maintained study directory.  The old receipt-parent
                # construction (`receipt/ studies/...`) made the documented
                # `verify --receipt ... --spec ...` command fail for a receipt
                # stored in a private output directory.
                candidate = Path(spec_path).parent / INVENTORY_REPOSITORY_PATH
                inventory_path = (
                    candidate
                    if candidate.is_file()
                    else Path(spec_path).parent / "prior_specification_inventory.json"
                )
            _validate_stage2_coverage_probe_receipt(
                spec_path=spec_path,
                receipt_path=receipt_file,
                expected_study_id=STUDY_ID,
                prior_specification_inventory_path=inventory_path,
            )
        except Exception as exc:
            raise CoverageProbeError("passed probe receipt failed the Stage-2 validator") from exc
    return receipt


def _preflight_report_path(value: str | Path) -> Path:
    entry = Path(value).expanduser()
    if _entry_exists(entry):
        raise CoverageProbeError("preflight report target already exists")
    path = entry.resolve(strict=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_blocked_preflight_report(path: str | Path, reason: str) -> Path:
    """Persist a redacted BLOCKED report when a preflight input is malformed.

    A malformed template must never be interpreted as permission to run.  The
    CLI still emits an auditable, machine-readable stop record so operators can
    fix the missing external evidence without guessing whether a request was
    made.
    """

    target = _preflight_report_path(path)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    report = {
        "schema_version": "stage2_coverage_probe_preflight_v1",
        "status": "BLOCKED",
        "study_id": STUDY_ID,
        "probe_id": PROBE_ID,
        "checked_at_utc": now,
        "spec_sha256": None,
        "inventory_sha256": None,
        "timestamp_package_sha256": None,
        "timestamp_proof_sha256": None,
        "rights_review_sha256": None,
        "agent_commit": None,
        "qdata_commit": None,
        "agent_clean": False,
        "qdata_clean": False,
        "runtime_contract": {
            "expected": {"python_version": PYTHON_VERSION, "akshare_version": AKSHARE_VERSION},
            "actual": _runtime_snapshot()["actual"],
            "matches": False,
        },
        "gates": {gate: False for gate in GATE_IDS[:5]},
        "blocking_reason_codes": ["PREFLIGHT_VALIDATION_ERROR"],
        "error": reason[:500],
        "scope_boundary": (
            "No provider request was made; no factor, return, IC, rank, portfolio, "
            "or variant outcome was read."
        ),
    }
    target.write_bytes(canonical_json_bytes(report))
    return target


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m a_share_quant_agent.coverage_probe",
        description=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    pre = sub.add_parser("preflight", help="check fixed probe gates without network requests")
    for option in (
        "spec",
        "prior-inventory",
        "timestamp-package",
        "timestamp-proof",
        "rights-review",
        "output-dir",
    ):
        pre.add_argument(f"--{option}", required=True)
    pre.add_argument("--qdata-checkout", required=True)
    pre.add_argument("--agent-commit")
    pre.add_argument("--report", required=True)
    run = sub.add_parser("run", help="execute the exact 24-cell probe")
    for option in (
        "spec",
        "prior-inventory",
        "timestamp-package",
        "timestamp-proof",
        "rights-review",
        "output-dir",
    ):
        run.add_argument(f"--{option}", required=True)
    run.add_argument("--qdata-checkout", required=True)
    run.add_argument("--agent-commit")
    verify = sub.add_parser("verify", help="verify a public receipt and optional private files")
    verify.add_argument("--receipt", required=True)
    verify.add_argument("--artifact-root")
    verify.add_argument("--spec")
    verify.add_argument("--prior-inventory")
    args = parser.parse_args(argv)
    try:
        if args.command == "preflight":
            report = preflight_probe(
                spec_path=args.spec,
                prior_inventory_path=args.prior_inventory,
                timestamp_package_path=args.timestamp_package,
                timestamp_proof_path=args.timestamp_proof,
                rights_review_path=args.rights_review,
                output_dir=args.output_dir,
                agent_commit=args.agent_commit,
                qdata_checkout=args.qdata_checkout,
            )
            target = _preflight_report_path(args.report)
            target.write_bytes(canonical_json_bytes(report))
            print(f"{report['status']}: {target}")
            return 0 if report["status"] == "READY" else 2
        if args.command == "run":
            receipt = run_probe(
                spec_path=args.spec,
                prior_inventory_path=args.prior_inventory,
                timestamp_package_path=args.timestamp_package,
                timestamp_proof_path=args.timestamp_proof,
                rights_review_path=args.rights_review,
                qdata_checkout=args.qdata_checkout,
                output_dir=args.output_dir,
                agent_commit=args.agent_commit,
            )
            print(f"{receipt['status']}: {args.output_dir}")
            return 0 if receipt["status"] == "PASSED" else 2
        receipt = verify_probe_artifacts(
            args.receipt,
            artifact_root=args.artifact_root,
            spec_path=args.spec,
            prior_inventory_path=args.prior_inventory,
        )
        print(f"verified {receipt['status']}: {args.receipt}")
        return 0 if receipt["status"] == "PASSED" else 2
    except (CoverageProbeError, OSError, ValueError) as exc:
        if args.command == "preflight" and getattr(args, "report", None):
            try:
                target = _write_blocked_preflight_report(args.report, str(exc))
                print(f"BLOCKED: {target}", file=sys.stderr)
                return 2
            except Exception:
                pass
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CoverageProbeError",
    "canonical_json_bytes",
    "preflight_probe",
    "run_probe",
    "sha256_file",
    "validate_external_timestamp_proof",
    "verify_probe_artifacts",
]
