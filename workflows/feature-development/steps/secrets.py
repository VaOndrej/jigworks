"""Secret scan of the added lines of a diff.

Uses `gitleaks` when it is on PATH; otherwise this built-in scanner with a small set of
gitleaks-style rules. A finding fails the gate like a failing test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

RULES: list[tuple[str, re.Pattern[str]]] = [
    ("aws-access-key-id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY")),
    ("github-token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    (
        "generic-secret-assignment",
        re.compile(
            r"(?i)\b[\w-]*(?:api[_-]?key|secret|token|passw(?:or)?d)[\w-]*\b\s*[:=]\s*['\"][A-Za-z0-9/+_=\-]{16,}['\"]"
        ),
    ),
]


@dataclass(frozen=True)
class Finding:
    rule: str
    file: str
    line: int


def scan_diff(diff: str) -> list[Finding]:
    findings: list[Finding] = []
    file, line_no = "", 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            file = raw[6:] if raw.startswith("+++ b/") else raw[4:]
            continue
        if raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            line_no = int(m.group(1)) - 1 if m else 0
            continue
        if raw.startswith("+"):
            line_no += 1
            for rule, pattern in RULES:
                if pattern.search(raw[1:]):
                    findings.append(Finding(rule, file, line_no))
        elif not raw.startswith("-"):
            line_no += 1
    return findings
