from __future__ import annotations

import re
from dataclasses import dataclass

from code_rag.models import SecretFinding


@dataclass(frozen=True)
class SecretPattern:
    name: str
    pattern: re.Pattern[str]
    confidence: str


class SecretScanner:
    REDACTION = "[REDACTED_SECRET]"

    def __init__(self) -> None:
        self.patterns = [
            SecretPattern(
                "aws_access_key_id",
                re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
                "high",
            ),
            SecretPattern(
                "private_key",
                re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
                "high",
            ),
            SecretPattern(
                "github_token",
                re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{36,255}\b"),
                "high",
            ),
            SecretPattern(
                "gitlab_token",
                re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
                "high",
            ),
            SecretPattern(
                "slack_token",
                re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
                "high",
            ),
            SecretPattern(
                "jwt",
                re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
                "medium",
            ),
            SecretPattern(
                "assigned_secret",
                re.compile(
                    r"(?i)\b(api[_-]?key|secret|token|password|passwd|pwd)\b\s*[:=]\s*['\"]?([^'\"\s]{12,})"
                ),
                "medium",
            ),
        ]

    def scan(self, text: str) -> list[SecretFinding]:
        findings: list[SecretFinding] = []
        for secret_pattern in self.patterns:
            for match in secret_pattern.pattern.finditer(text):
                start, end = self._value_span(match)
                findings.append(
                    SecretFinding(
                        secret_type=secret_pattern.name,
                        line=text.count("\n", 0, start) + 1,
                        start=start,
                        end=end,
                        confidence=secret_pattern.confidence,
                    )
                )
        return self._dedupe(findings)

    def redact(self, text: str) -> tuple[str, list[SecretFinding]]:
        findings = self.scan(text)
        if not findings:
            return text, []
        redacted = text
        for finding in sorted(findings, key=lambda item: item.start, reverse=True):
            redacted = redacted[: finding.start] + self.REDACTION + redacted[finding.end :]
        return redacted, findings

    def _value_span(self, match: re.Match[str]) -> tuple[int, int]:
        if match.lastindex and match.lastindex >= 2:
            return match.start(2), match.end(2)
        return match.start(), match.end()

    def _dedupe(self, findings: list[SecretFinding]) -> list[SecretFinding]:
        result: list[SecretFinding] = []
        confidence_rank = {"high": 0, "medium": 1, "low": 2}
        for finding in sorted(
            findings,
            key=lambda item: (item.start, confidence_rank[item.confidence], -(item.end - item.start)),
        ):
            overlaps = any(
                finding.start < existing.end and finding.end > existing.start for existing in result
            )
            if not overlaps:
                result.append(finding)
        return result
