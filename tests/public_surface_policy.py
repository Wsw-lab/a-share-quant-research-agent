from __future__ import annotations

import re


def scan_sensitive_text(text: str, *, stale_paths: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Return stable policy labels for unsafe tracked-text content."""

    slash = "/"
    local_roots = (
        slash + "Users" + slash,
        slash + "home" + slash,
    )
    windows_drive = re.compile(r"(?<![A-Za-z0-9+.\-])[A-Za-z]:[\\/]")
    token_prefix = "s" + "k" + "-"
    aws_prefix = "A" + "K" + "I" + "A"
    private_key_header = re.compile(r"-{5}BEGIN (?:(?:RSA|OPENSSH|EC|DSA) )?PRIVATE KEY-{5}")
    github_classic_token = re.compile("g" + r"h[pousr]_[A-Za-z0-9]{20,}")
    github_fine_grained_token = re.compile("git" + r"hub_pat_[A-Za-z0-9_]{20,}")
    assignment = re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|secret|password)\b"
        r"\s*[:=]\s*[\"'][^\"']{12,}[\"']"
    )

    violations: list[str] = []
    for root in local_roots:
        if root in text:
            violations.append(f"machine-path:{root}")
    if windows_drive.search(text):
        violations.append("machine-path:windows-drive")
    if re.search(re.escape(token_prefix) + r"[A-Za-z0-9_-]{20,}", text):
        violations.append("secret:openai-token")
    if re.search(re.escape(aws_prefix) + r"[0-9A-Z]{16}", text):
        violations.append("secret:aws-access-key")
    if private_key_header.search(text):
        violations.append("secret:private-key")
    if github_classic_token.search(text):
        violations.append("secret:github-classic-token")
    if github_fine_grained_token.search(text):
        violations.append("secret:github-fine-grained-token")
    if assignment.search(text):
        violations.append("secret:assignment")
    for stale_path in stale_paths:
        if stale_path in text:
            violations.append(f"stale-generated:{stale_path}")
    return tuple(violations)
