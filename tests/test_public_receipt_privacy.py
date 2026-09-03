from __future__ import annotations

import json
import unittest
from urllib.parse import quote

from a_share_quant_agent.confirmatory_study import (
    ConfirmatoryStudyError,
    _validate_stage2_public_receipt_privacy,
)
from a_share_quant_agent.coverage_probe import (
    CoverageProbeError,
    _validate_public_receipt_privacy,
)
from a_share_quant_agent.public_receipt_privacy import (
    public_string_privacy_reason,
)


class SharedPublicReceiptPrivacyTest(unittest.TestCase):
    @staticmethod
    def _validators():
        return (
            (
                ConfirmatoryStudyError,
                lambda value: _validate_stage2_public_receipt_privacy(
                    value,
                    label="test artifact",
                ),
            ),
            (
                CoverageProbeError,
                lambda value: _validate_public_receipt_privacy(
                    value,
                    label="test artifact",
                ),
            ),
        )

    def test_whole_string_encoding_and_alternate_local_ip_literals_fail_closed(self) -> None:
        unsafe_values = (
            "https:%2F%2Flocalhost/x",
            "https%3A%2F%2Flocalhost%2Fx",
            "file%3A%2F%2F%2Ftmp/x",
            "https://127.1/x",
            "https://2130706433/x",
            "https://0177.0.0.1/x",
            "https://0x7f000001/x",
            "https://internal/private",
            "https://corp/private",
            "https://printer/private",
            "mailto:private.user@corp.example",
            "data:text/plain,TOPSECRET",
            "javascript:alert(document.cookie)",
            "urn:secret:customer-123",
            "authorization: Bearer highly-sensitive-value",
            "api_key=highly-sensitive-value",
            "authorization%3A%20Bearer%20highly-sensitive-value",
            "api%255fkey%3Dhighly-sensitive-value",
            "https%252525253A%252525252F%252525252Flocalhost%252525252Fx",
        )
        validators = (
            (
                ConfirmatoryStudyError,
                lambda value: _validate_stage2_public_receipt_privacy(
                    {"statement": value},
                    label="test artifact",
                ),
            ),
            (
                CoverageProbeError,
                lambda value: _validate_public_receipt_privacy(
                    {"statement": value},
                    label="test artifact",
                ),
            ),
        )
        for value in unsafe_values:
            with self.subTest(value=value, validator="shared"):
                self.assertIsNotNone(public_string_privacy_reason(value))
            for error_type, validator in validators:
                with self.subTest(value=value, validator=error_type.__name__):
                    with self.assertRaises(error_type):
                        validator(value)

    def test_excessive_percent_encoding_fails_closed(self) -> None:
        value = "https://localhost/private"
        for _ in range(10):
            value = quote(value, safe="")
        self.assertEqual(
            public_string_privacy_reason(value),
            "excessively nested percent encoding",
        )
        with self.assertRaises(ConfirmatoryStudyError):
            _validate_stage2_public_receipt_privacy(
                {"statement": value}, label="test artifact"
            )
        with self.assertRaises(CoverageProbeError):
            _validate_public_receipt_privacy(
                {"statement": value}, label="test artifact"
            )

    def test_credential_key_error_redacts_untrusted_key_text(self) -> None:
        sentinel = "SENSITIVE" + "123"
        untrusted_key = "api" + "_key_" + sentinel
        validators = (
            (
                ConfirmatoryStudyError,
                lambda: _validate_stage2_public_receipt_privacy(
                    {untrusted_key: "hidden"},
                    label="test artifact",
                ),
            ),
            (
                CoverageProbeError,
                lambda: _validate_public_receipt_privacy(
                    {untrusted_key: "hidden"},
                    label="test artifact",
                ),
            ),
        )
        for error_type, validator in validators:
            with self.subTest(validator=error_type.__name__):
                with self.assertRaises(error_type) as raised:
                    validator()
                message = str(raised.exception)
                self.assertIn("credential-like key", message)
                self.assertIn("<redacted-key>", message)
                self.assertNotIn(sentinel, message)
                self.assertNotIn(untrusted_key, message)

    def test_path_and_url_keys_fail_closed_without_key_disclosure(self) -> None:
        unsafe_keys = (
            "/" + "Users/alice/private/evidence.json",
            r"\\server\private\evidence.json",
            "C" + r":\private\evidence.json",
            "https://localhost/private/evidence",
            "https%3A%2F%2Flocalhost%2Fprivate%2Fevidence",
        )
        validators = (
            (
                ConfirmatoryStudyError,
                lambda value: _validate_stage2_public_receipt_privacy(
                    {"signature": {value: True}},
                    label="test artifact",
                ),
            ),
            (
                CoverageProbeError,
                lambda value: _validate_public_receipt_privacy(
                    {"signature": {value: True}},
                    label="test artifact",
                ),
            ),
        )
        for untrusted_key in unsafe_keys:
            with self.subTest(key=untrusted_key, validator="shared"):
                self.assertIsNotNone(public_string_privacy_reason(untrusted_key))
            for error_type, validator in validators:
                with self.subTest(
                    key=untrusted_key, validator=error_type.__name__
                ):
                    with self.assertRaises(error_type) as raised:
                        validator(untrusted_key)
                    message = str(raised.exception)
                    self.assertIn("<redacted-key>", message)
                    self.assertNotIn(untrusted_key, message)

    def test_public_doi_and_route_prose_remain_allowed(self) -> None:
        for value in (
            "https://doi.org/10.1016/j.pacfin.2025.103012",
            "documented endpoint /api/qt/stock/kline/get",
        ):
            with self.subTest(value=value):
                self.assertIsNone(public_string_privacy_reason(value))

    def test_embedded_absolute_posix_paths_with_spaces_and_custom_roots_fail_closed(self) -> None:
        unsafe_values = (
            "review copy at /data room/vendor agreement.pdf",
            "retain (/research files/private/raw.csv) for the reviewer",
            "Markdown [private file](/custom root/reviewer copy.json)",
        )
        for value in unsafe_values:
            with self.subTest(value=value):
                self.assertEqual(
                    public_string_privacy_reason(value),
                    "absolute local path",
                )
                for error_type, validator in self._validators():
                    with self.subTest(validator=error_type.__name__):
                        with self.assertRaises(error_type) as raised:
                            validator({"statement": value})
                        self.assertNotIn(value, str(raised.exception))

    def test_arbitrary_opaque_uri_schemes_fail_but_sha256_ids_remain_valid(self) -> None:
        for value in (
            "ssh:user@research-host",
            "custom-scheme:private-material",
            "magnet:?xt=urn:btih:private-material",
            "ipfs:private-cid",
            "geo:37.786971,-122.399677",
            "https://example.com/public?next=custom%3Aprivate-material",
        ):
            with self.subTest(value=value):
                self.assertEqual(public_string_privacy_reason(value), "non-HTTPS URL")
                for error_type, validator in self._validators():
                    with self.subTest(validator=error_type.__name__):
                        with self.assertRaises(error_type):
                            validator({"statement": value})

        digest_id = "sha256:" + "a" * 64
        self.assertIsNone(public_string_privacy_reason(digest_id))
        self.assertIsNone(
            public_string_privacy_reason(
                "https://example.com/public-record/id:123"
            )
        )
        for _, validator in self._validators():
            validator({"receipt_id": digest_id})

    def test_inline_auth_material_and_serialized_json_are_scanned(self) -> None:
        unsafe_values = (
            "Bearer opaque-private-token-12345",
            "Basic dXNlcjpwYXNzd29yZA==",
            "-----BEGIN" + " PRIVATE KEY----- private material",
            "s" + "k" + "-" + "A" * 24,
            "A" + "K" + "I" + "A" + "1" * 16,
            "g" + "hp_" + "A" * 24,
            "git" + "hub_pat_" + "A" * 24,
            json.dumps({"outer": {"api_key": "private-value"}}),
            json.dumps({"outer": [{"reference": "https://printer/private"}]}),
        )
        for value in unsafe_values:
            with self.subTest(value=value):
                self.assertIsNotNone(public_string_privacy_reason(value))
                for error_type, validator in self._validators():
                    with self.subTest(validator=error_type.__name__):
                        with self.assertRaises(error_type) as raised:
                            validator({"statement": value})
                        self.assertNotIn("private-value", str(raised.exception))

        for benign in (
            "Bearer authentication is not used by this receipt.",
            "Basic authentication is not used by this receipt.",
            json.dumps(
                {
                    "signature": {"type": "human_verified_evidence"},
                    "receipt_id": "sha256:" + "b" * 64,
                    "verification_uri": "https://example.com/public-record",
                }
            ),
        ):
            with self.subTest(benign=benign):
                self.assertIsNone(public_string_privacy_reason(benign))

    def test_nested_key_errors_redact_offending_and_ancestor_keys(self) -> None:
        ancestor_sentinel = "ancestor-sensitive-4872"
        offending_sentinel = "api_key_sensitive_9153"
        value = {
            ancestor_sentinel: {
                "level_two": {
                    offending_sentinel: "hidden-value-sensitive-6641",
                }
            }
        }
        for error_type, validator in self._validators():
            with self.subTest(validator=error_type.__name__):
                with self.assertRaises(error_type) as raised:
                    validator(value)
                message = str(raised.exception)
                self.assertIn("<redacted-path>.<redacted-key>", message)
                self.assertNotIn(ancestor_sentinel, message)
                self.assertNotIn(offending_sentinel, message)
                self.assertNotIn("hidden-value-sensitive-6641", message)

    def test_deep_embedded_json_fails_closed_instead_of_skipping_descendants(self) -> None:
        value: object = {"leaf": "public"}
        for index in range(12):
            value = {f"level_{index}": value}
        serialized = json.dumps(value)
        self.assertEqual(
            public_string_privacy_reason(serialized),
            "excessively nested embedded JSON",
        )
        for error_type, validator in self._validators():
            with self.subTest(validator=error_type.__name__):
                with self.assertRaises(error_type):
                    validator({"statement": serialized})

    def test_url_only_signature_parameters_are_treated_as_credentials(self) -> None:
        for value in (
            "https://example.com/x?signature=hidden",
            "https://example.com/x?Signature=hidden",
            "https://example.com/x#authorization_code=hidden",
            "https://example.com/x;auth=hidden",
        ):
            with self.subTest(value=value):
                self.assertIsNotNone(public_string_privacy_reason(value))
        # A structural signature field can carry a public, non-secret digest;
        # only URL-parameter context uses the stricter vocabulary.
        _validate_stage2_public_receipt_privacy(
            {"signature": {"type": "human_verified_evidence"}},
            label="test artifact",
        )


if __name__ == "__main__":
    unittest.main()
