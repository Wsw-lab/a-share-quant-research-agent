from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
HANDOFF = ROOT / "studies/pit_factor_bias_decomposition_v2/external_registration_handoff.template.json"


class ExternalRegistrationHandoffTest(unittest.TestCase):
    def test_handoff_is_an_unsubmitted_provider_neutral_template(self) -> None:
        data = json.loads(HANDOFF.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "prepared_no_submission_made")
        submission = data["submission"]
        verification = data["verification"]
        for key in ("provider", "submitted_at", "artifact_path", "artifact_sha256"):
            self.assertIsNone(submission[key])
        for key in (
            "identifier",
            "verification_uri",
            "provider_record_evidence_path",
            "provider_record_evidence_sha256",
            "verified_at",
            "verifier",
            "verification_method",
        ):
            self.assertIsNone(verification[key])
        self.assertGreaterEqual(len(submission["provider_options"]), 3)

    def test_handoff_requires_verification_before_authorization(self) -> None:
        data = json.loads(HANDOFF.read_text(encoding="utf-8"))
        contract = data["handoff_contract"]
        self.assertTrue(contract["execution_authorization_after_verification"])
        self.assertIn("registration_receipt.template.json", contract["next_artifact"])
        self.assertTrue(any("probe" in item for item in contract["required_preconditions"]))
        self.assertTrue(any("rights" in item for item in contract["required_preconditions"]))
        self.assertTrue(any("factor outcomes" in item for item in contract["forbidden_actions"]))

