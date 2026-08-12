"""Fail a build when tracked text resembles a committed credential.

This deterministic preflight complements, but does not replace, provider-side secret scanning.
It intentionally reports only the rule and location so a credential is never copied into logs.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_MAX_FILE_BYTES: Final = 8 * 1024 * 1024
_PLACEHOLDERS: Final = frozenset(
    {
        "changeme",
        "example",
        "placeholder",
        "redacted",
        "synthetic",
        "test-only",
    }
)
_RULES: Final = (
    (
        "private-key",
        re.compile(r"-----BEGIN (?:DSA |EC |OPENSSH |PGP |RSA )?PRIVATE KEY-----"),
    ),
    ("aws-access-key", re.compile(r"\b(?:A3T[A-Z0-9]|AKIA|ASIA)[A-Z0-9]{16}\b")),
    (
        "github-token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    ),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{20,}\b")),
    ("stripe-live-key", re.compile(r"\b[rs]k_live_[0-9A-Za-z]{16,}\b")),
    ("openai-key", re.compile(r"\bsk-(?:proj-|svcacct-)?[0-9A-Za-z_-]{20,}\b")),
    ("anthropic-key", re.compile(r"\bsk-ant-[0-9A-Za-z_-]{20,}\b")),
)
_ASSIGNMENT = re.compile(
    r"(?i)\b(?:api[_-]?key|client[_-]?secret|password|passwd|secret|token)\b"
    r"\s*[:=]\s*['\"]([^'\"\s]{16,})['\"]"
)


@dataclass(frozen=True, slots=True)
class Finding:
    """One location-only result safe to print in CI logs."""

    rule: str
    line: int


class GitNotFoundError(RuntimeError):
    """Raised when the repository index cannot be enumerated safely."""

    def __init__(self) -> None:
        super().__init__("git is required for the repository secret scan")


def scan_text(text: str) -> tuple[Finding, ...]:
    """Return deterministic credential-pattern findings without retaining matched values."""

    findings: list[Finding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for rule, pattern in _RULES:
            if pattern.search(line) is not None:
                findings.append(Finding(rule=rule, line=line_number))
        for match in _ASSIGNMENT.finditer(line):
            candidate = match.group(1)
            normalized = candidate.casefold().strip("*_-.")
            if (
                normalized in _PLACEHOLDERS
                or normalized.startswith(("example", "placeholder", "synthetic"))
                or set(candidate) <= {"*"}
            ):
                continue
            findings.append(Finding(rule="credential-assignment", line=line_number))
    return tuple(findings)


def _tracked_paths(repository: Path) -> tuple[Path, ...]:
    git_executable = shutil.which("git")
    if git_executable is None:
        raise GitNotFoundError
    completed = subprocess.run(  # noqa: S603 - executable is resolved from the trusted PATH.
        [git_executable, "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    return tuple(
        repository / raw.decode("utf-8")
        for raw in completed.stdout.split(b"\0")
        if raw
    )


def _read_text(path: Path) -> str | None:
    if not path.is_file() or path.stat().st_size > _MAX_FILE_BYTES:
        return None
    payload = path.read_bytes()
    if b"\0" in payload:
        return None
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        return None


def scan_repository(repository: Path) -> tuple[tuple[Path, Finding], ...]:
    """Scan every tracked UTF-8 text file in stable path order."""

    results: list[tuple[Path, Finding]] = []
    for path in sorted(_tracked_paths(repository)):
        text = _read_text(path)
        if text is None:
            continue
        results.extend((path.relative_to(repository), item) for item in scan_text(text))
    return tuple(results)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", nargs="?", type=Path, default=Path.cwd())
    arguments = parser.parse_args()
    repository = arguments.repository.resolve()
    findings = scan_repository(repository)
    for path, finding in findings:
        sys.stdout.write(
            f"{path.as_posix()}:{finding.line}: potential secret ({finding.rule})\n"
        )
    if findings:
        sys.stdout.write(f"secret scan failed with {len(findings)} location(s)\n")
        return 1
    sys.stdout.write("secret scan passed\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
