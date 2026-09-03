"""Shared fail-closed privacy checks for public JSON receipt strings.

The receipt builders deliberately keep this scanner independent of field
semantics: a URL or machine-local path is unsafe even when it is embedded in
otherwise benign prose.  Callers remain responsible for their one narrowly
scoped, hash-bound network endpoint-path exemption.
"""

from __future__ import annotations

import base64
import binascii
import ipaddress
import json
import re
from collections.abc import Iterator, Mapping
from urllib.parse import parse_qsl, unquote, urlparse


_CREDENTIAL_KEY_PARTS = frozenset(
    {
        "cookie",
        "credential",
        "credentials",
        "passwd",
        "password",
        "secret",
        "token",
    }
)
_CREDENTIAL_KEYS = frozenset(
    {
        "access_key",
        "accesskey",
        "access_token",
        "accesstoken",
        "api_key",
        "apikey",
        "authorization",
        "authorization_header",
        "aws_access_key_id",
        "awsaccesskeyid",
        "client_secret",
        "clientsecret",
        "private_key",
        "privatekey",
        "proxy_authorization",
        "refresh_token",
        "refreshtoken",
        "set_cookie",
        "sig",
        "x_amz_signature",
        "x_api_key",
        "x_goog_signature",
        "xapikey",
    }
)
_SENSITIVE_KEY_SEQUENCES = (
    ("api", "key"),
    ("access", "key"),
    ("secret", "key"),
    ("private", "key"),
    ("signing", "key"),
    ("proxy", "authorization"),
)
_SENSITIVE_COMPACT_KEYS = (
    "apikey",
    "accesskey",
    "accesstoken",
    "clientsecret",
    "privatekey",
    "refreshtoken",
    "awsaccesskeyid",
    "proxyauthorization",
)
_URL_ONLY_CREDENTIAL_KEYS = frozenset(
    {"auth", "authorization_code", "signature"}
)

# URI tokens stop only at characters that cannot occur unescaped in a URI.
# Balanced closing punctuation is trimmed separately so Markdown/prose such as
# ``(https://example.invalid/record)`` yields the URL without its delimiter.
#
# Do not enumerate only familiar schemes here.  RFC 3986 permits applications
# to mint new schemes, so an opaque ``custom:...`` URI must not bypass the
# HTTPS-only public-receipt policy merely because its scheme is unfamiliar.
# The lookahead avoids treating ordinary ``Label: prose`` text as a URI.
_URI_START_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9+.-])"
    r"[A-Za-z][A-Za-z0-9+.-]*:(?=[^\s<>\"'])"
)
_URI_TERMINATORS = frozenset(" \t\r\n<>\"'")
_FILE_URI_RE = re.compile(r"(?i)(?<![A-Za-z0-9+.-])file:/+")
_WINDOWS_DRIVE_RE = re.compile(r"(?<![A-Za-z0-9+.-])[A-Za-z]:[\\/]")
_WINDOWS_UNC_RE = re.compile(r"(?<![\\A-Za-z0-9])\\\\[^\\\s]+[\\/]")
_HOME_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])~[\\/]")
_OBVIOUS_POSIX_ROOT_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_.-])/"
    r"(?:Users|home|private|var|tmp|etc|opt|root|srv|mnt|Volumes|usr|bin|sbin|"
    r"lib|Library|System|Applications|dev|proc|sys|run|boot|media)"
    r"(?=[/\\]|\b)"
)
_GENERIC_POSIX_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_.:/-])/"
    # POSIX components may contain spaces. Requiring a second slash keeps
    # ordinary prose such as ``and/or`` out of scope while still finding
    # disclosures embedded in sentences or Markdown. The match need not
    # consume the complete path; two absolute components are sufficient.
    r"(?P<first>[A-Za-z0-9_~.-]{2,}(?:[ ]+[A-Za-z0-9_~.-]+)*)/"
    r"(?P<second>[A-Za-z0-9_~.-]+(?:[ ]+[A-Za-z0-9_~.-]+)*)"
)
_LABELED_ABSOLUTE_PATH_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_.-])"
    r"[A-Za-z][A-Za-z0-9_.-]{0,31}\s*:\s*/(?!/)"
    r"[A-Za-z0-9_~.-]{2,}/[A-Za-z0-9_~.-]+"
)
_NETWORK_ROUTE_ROOTS = frozenset(
    {"api", "callback", "callbacks", "graphql", "oauth", "openapi", "rest", "rpc", "webhook"}
)
_QUERYLIKE_PAIR_RE = re.compile(r"(?:^|[?&;])([^?&;=#/]+)=([^&;]*)")
_PATH_PARAMETER_KEY_RE = re.compile(r"(?:^|[/;])([^/;=:?#]+)[=:]")
_INLINE_CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])"
    r"(?P<key>[A-Za-z][A-Za-z0-9_.%\-]{1,95})"
    r"\s*[:=]\s*(?P<value>[^\s,;]+)"
)
_QUOTED_CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])"
    r"(?P<quote>[\"'])(?P<key>[A-Za-z][A-Za-z0-9_.%\-]{1,95})(?P=quote)"
    r"\s*[:=]\s*(?P<value>[^\s,;]+)"
)
_HTTP_AUTH_MATERIAL_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])"
    r"(?P<scheme>bearer|basic)\s+"
    r"(?P<material>[A-Za-z0-9._~+/=\-]{8,})"
)
_PEM_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN(?: [A-Z0-9]+)* PRIVATE KEY-----",
    re.IGNORECASE,
)
_KNOWN_CREDENTIAL_MATERIAL_RE = re.compile(
    "(?:"
    + "s"
    + "k"
    + r"-[A-Za-z0-9_-]{20,}|"
    + "A"
    + "K"
    + "I"
    + "A"
    + r"[0-9A-Z]{16}|"
    + "g"
    + r"h[pousr]_[A-Za-z0-9]{20,}|"
    + "git"
    + r"hub_pat_[A-Za-z0-9_]{20,}"
    + ")"
)
_SAFE_CONTENT_IDENTIFIER_RE = re.compile(r"sha256:[0-9a-f]{64}", re.IGNORECASE)
_AUTH_DESCRIPTION_WORDS = frozenset(
    {
        "authentication",
        "authorization",
        "credential",
        "credentials",
        "scheme",
        "token",
    }
)
_MAX_NESTED_URI_DEPTH = 3
_MAX_PERCENT_DECODE_ROUNDS = 8
_MAX_EMBEDDED_JSON_DEPTH = 8


def _normalise_key(value: str) -> str:
    # Split both ``clientSecret`` and acronym-leading ``AWSAccessKeyId``.
    acronym_split = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", value)
    camel_split = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", acronym_split)
    return re.sub(r"[^a-z0-9]+", "_", camel_split.lower()).strip("_")


def credential_like_public_key(value: str) -> bool:
    """Return whether a structural key is likely to carry authentication data."""

    for candidate in _bounded_decodings(value):
        normalized = _normalise_key(candidate)
        if normalized in _CREDENTIAL_KEYS:
            return True
        parts = tuple(part for part in normalized.split("_") if part)
        if any(part in _CREDENTIAL_KEY_PARTS for part in parts):
            return True
        if any(
            parts[index : index + len(sequence)] == sequence
            for sequence in _SENSITIVE_KEY_SEQUENCES
            for index in range(len(parts) - len(sequence) + 1)
        ):
            return True
        compact = "".join(parts)
        if any(marker in compact for marker in _SENSITIVE_COMPACT_KEYS):
            return True
    return False


def _credential_like_url_parameter_key(value: str) -> bool:
    """Apply the stricter credential vocabulary appropriate to URL parameters."""

    return credential_like_public_key(value) or any(
        _normalise_key(candidate) in _URL_ONLY_CREDENTIAL_KEYS
        for candidate in _bounded_decodings(value)
    )


def _trim_uri_punctuation(token: str) -> str:
    token = token.rstrip(".,!?。，；：！？、")
    for opener, closer in (
        ("(", ")"),
        ("[", "]"),
        ("{", "}"),
        ("（", "）"),
        ("【", "】"),
        ("《", "》"),
        ("「", "」"),
        ("『", "』"),
    ):
        while token.endswith(closer) and token.count(closer) > token.count(opener):
            token = token[:-1]
    return token


def iter_embedded_uri_tokens(value: str) -> Iterator[tuple[str, int, int]]:
    """Yield URI-looking tokens and spans from any position in ``value``."""

    position = 0
    while (match := _URI_START_RE.search(value, position)) is not None:
        end = match.end()
        while end < len(value) and value[end] not in _URI_TERMINATORS:
            end += 1
        raw = value[match.start() : end]
        token = _trim_uri_punctuation(raw)
        if token:
            yield token, match.start(), match.start() + len(token)
        # The regular expression matches only the scheme prefix, whereas the
        # manual scan above consumes the complete URI.  Resume after that
        # complete token so a colon in an HTTPS path is not reinterpreted as a
        # second top-level opaque URI.
        position = max(end, match.end())


def _local_path_in_text(value: str, *, generic_leading_path: bool) -> bool:
    text = value.strip()
    if not text:
        return False
    if generic_leading_path and text.startswith(("/", "\\\\")):
        return True
    if bool(
        _FILE_URI_RE.search(value)
        or _WINDOWS_DRIVE_RE.search(value)
        or _WINDOWS_UNC_RE.search(value)
        or _HOME_PATH_RE.search(value)
        or _OBVIOUS_POSIX_ROOT_RE.search(value)
    ):
        return True
    if _LABELED_ABSOLUTE_PATH_RE.search(value):
        return True
    for match in _GENERIC_POSIX_PATH_RE.finditer(value):
        first = match.group("first").lower()
        second = match.group("second").lower()
        # Route-shaped tokens are common in otherwise public API prose.  The
        # validator still grants its sole field-level exemption only to the
        # exact frozen endpoint path; this syntactic distinction merely keeps
        # embedded API examples from being misclassified as machine paths.
        if first in _NETWORK_ROUTE_ROOTS or re.fullmatch(r"v[0-9]+", first):
            continue
        # Do not turn slash-separated dates or ratios into filesystem alerts.
        if first.isdigit() and second.isdigit():
            continue
        return True
    return False


def absolute_local_path_like(value: str) -> bool:
    """Detect standalone or embedded obvious machine-local path tokens."""

    spans = list(iter_embedded_uri_tokens(value))
    for token, _, _ in spans:
        if token.lower().startswith("file:"):
            return True
    # Remote URL paths are not local filesystem disclosures.  Blank complete
    # URI spans before checking the surrounding prose for machine paths.
    residual = list(value)
    for _, start, end in spans:
        residual[start:end] = " " * (end - start)
    return _local_path_in_text("".join(residual), generic_leading_path=True)


def _credential_key_in_querylike(value: str) -> bool:
    decoded = unquote(value)
    return any(
        _credential_like_url_parameter_key(match.group(1))
        for match in _QUERYLIKE_PAIR_RE.finditer(decoded)
    )


def _credential_key_in_path_parameters(path: str, params: str) -> bool:
    # Require an assignment delimiter.  This rejects
    # ``/callback/access_token=...`` and ``;api_key:...`` without treating a
    # benign route such as ``/oauth/token`` as leaked credential material.
    joined = "/".join(part for part in (unquote(path), unquote(params)) if part)
    return any(
        _credential_like_url_parameter_key(match.group(1))
        for match in _PATH_PARAMETER_KEY_RE.finditer(joined)
    )


def _bounded_decodings(value: str) -> Iterator[str]:
    current = value
    seen: set[str] = set()
    for _ in range(_MAX_PERCENT_DECODE_ROUNDS + 1):
        if current in seen:
            return
        seen.add(current)
        yield current
        decoded = unquote(current)
        if decoded == current:
            return
        current = decoded


def _percent_decoding_exceeds_limit(value: str) -> bool:
    """Fail closed when percent encoding remains nested beyond the scan budget."""

    current = value
    seen: set[str] = set()
    for _ in range(_MAX_PERCENT_DECODE_ROUNDS + 1):
        if current in seen:
            return False
        seen.add(current)
        decoded = unquote(current)
        if decoded == current:
            return False
        current = decoded
    return True


def _inline_authorization_material_like(value: str) -> bool:
    """Detect authorization-header material embedded in otherwise plain prose."""

    for match in _HTTP_AUTH_MATERIAL_RE.finditer(value):
        scheme = match.group("scheme").lower()
        material = match.group("material")
        # Permit descriptions such as ``Bearer authentication`` while still
        # treating actual-looking opaque material as private.
        if material.lower() in _AUTH_DESCRIPTION_WORDS:
            continue
        if scheme == "bearer":
            return True
        try:
            padded = material + "=" * (-len(material) % 4)
            decoded = base64.b64decode(padded, validate=True)
        except (binascii.Error, ValueError):
            # ``Basic`` followed by a long opaque token is sensitive even if
            # the supplied value is malformed according to RFC 7617.
            return True
        if decoded:
            return True
    return False


def _embedded_json_privacy_reason(
    value: str,
    *,
    uri_depth: int,
    embedded_json_depth: int,
) -> str | None:
    """Inspect JSON serialized inside a string, including every nested key."""

    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return None
    try:
        document = json.loads(stripped)
    except RecursionError:
        return "excessively nested embedded JSON"
    except json.JSONDecodeError:
        return None
    if not isinstance(document, (Mapping, list)):
        return None
    if embedded_json_depth >= _MAX_EMBEDDED_JSON_DEPTH:
        return "excessively nested embedded JSON"

    stack: list[tuple[object, int]] = [(document, 0)]
    while stack:
        item, node_depth = stack.pop()
        if node_depth > _MAX_EMBEDDED_JSON_DEPTH:
            return "excessively nested embedded JSON"
        if isinstance(item, Mapping):
            for key, child in item.items():
                key_text = str(key)
                if credential_like_public_key(key_text):
                    return "credential-like key in embedded JSON"
                key_reason = _public_string_privacy_reason(
                    key_text,
                    depth=uri_depth,
                    embedded_json_depth=embedded_json_depth + 1,
                )
                if key_reason is not None:
                    return f"unsafe key in embedded JSON: {key_reason}"
                stack.append((child, node_depth + 1))
            continue
        if isinstance(item, list):
            stack.extend((child, node_depth + 1) for child in item)
            continue
        if isinstance(item, str):
            reason = _public_string_privacy_reason(
                item,
                depth=uri_depth,
                embedded_json_depth=embedded_json_depth + 1,
            )
            if reason is not None:
                return reason
    return None


def _nonstandard_ipv4_literal_like(hostname: str) -> bool:
    """Reject alternate IPv4 spellings that URL stacks may canonicalize locally."""

    lowered = hostname.lower()
    if re.fullmatch(r"0x[0-9a-f]+", lowered) or lowered.isdigit():
        return True
    parts = lowered.split(".")
    numeric_parts = all(
        re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)", part) is not None
        for part in parts
    )
    if not numeric_parts:
        return False
    if len(parts) != 4:
        return True
    return any(
        part.startswith("0x") or (len(part) > 1 and part.startswith("0"))
        for part in parts
    )


def _https_authority_reason(netloc: str) -> str | None:
    """Validate original and bounded-decoded HTTPS authority representations."""

    if not netloc:
        return "URL without a host"
    for authority in _bounded_decodings(netloc):
        try:
            candidate = urlparse("//" + authority)
        except ValueError:
            return "malformed URL"
        # Percent-decoding must not smuggle path/query/fragment delimiters out
        # of the authority component.
        if candidate.path or candidate.params or candidate.query or candidate.fragment:
            return "malformed URL"
        if candidate.username is not None or candidate.password is not None:
            return "URL user information"
        try:
            hostname = candidate.hostname or ""
            candidate.port
        except ValueError:
            return "malformed URL"
        if not hostname:
            return "URL without a host"
        for decoded_hostname in _bounded_decodings(hostname):
            normalized = decoded_hostname.rstrip(".").lower()
            if not normalized:
                return "URL without a host"
            if "@" in normalized:
                return "URL user information"
            if any(delimiter in normalized for delimiter in "/?#"):
                return "malformed URL"
            if normalized == "localhost" or normalized.endswith(
                (
                    ".localhost",
                    ".local",
                    ".internal",
                    ".intranet",
                    ".lan",
                    ".home",
                    ".corp",
                    ".private",
                )
            ):
                return "local or internal URL host"
            if _nonstandard_ipv4_literal_like(normalized):
                return "non-public URL address"
            try:
                address = ipaddress.ip_address(normalized)
            except ValueError:
                address = None
            if address is not None and not address.is_global:
                return "non-public URL address"
            if address is None and "." not in normalized:
                # A bare label can resolve only through host-specific search,
                # multicast, or private DNS and is not a stable public origin.
                return "local or internal URL host"
    return None


def _unsafe_public_url_reason(value: str, *, depth: int) -> str | None:

    text = value.strip()
    try:
        parsed = urlparse(text)
    except ValueError:
        return "malformed URL" if ":/" in text else None
    scheme = parsed.scheme.lower()
    if not scheme:
        return None
    if scheme == "sha256":
        if _SAFE_CONTENT_IDENTIFIER_RE.fullmatch(text):
            return None
        return "malformed content identifier"
    if scheme == "file" or (
        scheme == "path" and text[len(parsed.scheme) + 1 :].startswith(("/", "\\"))
    ) or (
        len(parsed.scheme) == 1
        and text[len(parsed.scheme) + 1 :].startswith(("/", "\\"))
    ):
        return "absolute local path"
    if scheme != "https":
        return "non-HTTPS URL"
    authority_reason = _https_authority_reason(parsed.netloc)
    if authority_reason is not None:
        return authority_reason

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if any(_credential_like_url_parameter_key(key) for key, _ in query_pairs) or (
        _credential_key_in_querylike(parsed.query)
    ):
        return "credential-like URL query key"
    if _credential_key_in_querylike(parsed.fragment):
        return "credential-like URL fragment key"
    if _credential_key_in_path_parameters(parsed.path, parsed.params):
        return "credential-like URL path parameter key"

    # A local path placed in a query/fragment value is still a filesystem
    # disclosure even though the enclosing URL has a public HTTPS host.
    component_values = [component for _, component in query_pairs]
    component_values.extend(
        match.group(2)
        for match in _QUERYLIKE_PAIR_RE.finditer(unquote(parsed.fragment))
    )
    for component in component_values:
        for decoded in _bounded_decodings(component):
            if _local_path_in_text(decoded, generic_leading_path=True):
                return "absolute local path in URL component"
            if depth < _MAX_NESTED_URI_DEPTH:
                nested_reason = _public_string_privacy_reason(
                    decoded,
                    depth=depth + 1,
                    embedded_json_depth=0,
                )
                if nested_reason is not None:
                    return nested_reason
    return None


def unsafe_public_url_reason(value: str) -> str | None:
    """Return a stable reason for one unsafe URI token, without echoing it."""

    return _unsafe_public_url_reason(value, depth=0)


def _public_string_privacy_reason(
    value: str,
    *,
    depth: int,
    embedded_json_depth: int = 0,
) -> str | None:
    # Decode the whole string as well as individual URI components.  Otherwise
    # a prose field could conceal the URI introducer itself (for example an
    # encoded ``https://`` or ``file:///`` token) from the token scanner.
    if _percent_decoding_exceeds_limit(value):
        return "excessively nested percent encoding"
    for representation in _bounded_decodings(value):
        spans = list(iter_embedded_uri_tokens(representation))
        for token, _, _ in spans:
            reason = _unsafe_public_url_reason(token, depth=depth)
            if reason is not None:
                return reason
        if any(
            _credential_like_url_parameter_key(match.group("key"))
            for match in _INLINE_CREDENTIAL_ASSIGNMENT_RE.finditer(representation)
        ):
            return "credential-like plaintext assignment"
        if any(
            credential_like_public_key(match.group("key"))
            for match in _QUOTED_CREDENTIAL_ASSIGNMENT_RE.finditer(representation)
        ):
            return "credential-like plaintext assignment"
        if _inline_authorization_material_like(representation):
            return "inline authorization material"
        if _PEM_PRIVATE_KEY_RE.search(representation):
            return "inline private-key material"
        if _KNOWN_CREDENTIAL_MATERIAL_RE.search(representation):
            return "known credential material"
        if absolute_local_path_like(representation):
            return "absolute local path"
        embedded_reason = _embedded_json_privacy_reason(
            representation,
            uri_depth=depth,
            embedded_json_depth=embedded_json_depth,
        )
        if embedded_reason is not None:
            return embedded_reason
    return None


def public_string_privacy_reason(value: str) -> str | None:
    """Scan every URI and remaining prose segment in one public string."""

    return _public_string_privacy_reason(value, depth=0, embedded_json_depth=0)
