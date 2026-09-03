"""Perform dependency-free structural checks on GitHub Actions workflow YAML.

This intentionally small validator covers the workflow subset used in this
repository. In particular, it rejects duplicate mapping keys, which permissive
YAML loaders commonly overwrite without warning.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

_MAPPING_ENTRY: Final = re.compile(
    r"^(?P<key>[A-Za-z_][A-Za-z0-9_-]*|'[^']+'|\"[^\"]+\")\s*:(?:\s*(?P<value>.*))?$"
)
_BLOCK_SCALAR: Final = re.compile(r"^[>|][+-]?(?:\s+#.*)?$")
_REQUIRED_TOP_LEVEL_KEYS: Final = frozenset({"name", "on", "jobs"})
_MIN_QUOTED_KEY_LENGTH: Final = 2


@dataclass(frozen=True, slots=True)
class WorkflowIssue:
    """One actionable workflow validation issue."""

    path: Path
    line: int
    message: str

    def render(self) -> str:
        """Render the issue in compiler-compatible form."""

        return f"{self.path.as_posix()}:{self.line}: {self.message}"


class WorkflowValidationError(RuntimeError):
    """Raised when one or more workflows fail structural validation."""

    def __init__(self, issues: Sequence[WorkflowIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__("\n".join(issue.render() for issue in issues))


def _unquote_key(key: str) -> str:
    if len(key) >= _MIN_QUOTED_KEY_LENGTH and key[0] == key[-1] and key[0] in {'"', "'"}:
        return key[1:-1]
    return key


def validate_workflow(path: Path) -> None:  # noqa: C901, PLR0912
    """Validate indentation, mapping structure, and duplicate keys in one workflow."""

    text = path.read_text(encoding="utf-8")
    issues: list[WorkflowIssue] = []
    seen_keys: dict[int, dict[str, int]] = {}
    top_level_keys: set[str] = set()
    block_scalar_indent: int | None = None

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.lstrip(" ")
        indent = len(raw_line) - len(stripped)

        if block_scalar_indent is not None:
            if not stripped or indent > block_scalar_indent:
                continue
            block_scalar_indent = None
        if not stripped or stripped.startswith("#") or stripped == "---":
            continue
        if raw_line[:indent].find("\t") != -1 or raw_line.startswith("\t"):
            issues.append(WorkflowIssue(path, line_number, "tabs are not valid indentation"))
            continue
        if indent % 2:
            issues.append(
                WorkflowIssue(path, line_number, "structural indentation must use two-space levels")
            )

        is_sequence_item = stripped.startswith("- ")
        content = stripped[2:] if is_sequence_item else stripped
        effective_indent = indent + 2 if is_sequence_item else indent

        for level in tuple(seen_keys):
            threshold = effective_indent if is_sequence_item else effective_indent + 1
            if level >= threshold:
                del seen_keys[level]

        match = _MAPPING_ENTRY.match(content)
        if match is None:
            if not is_sequence_item:
                issues.append(WorkflowIssue(path, line_number, "expected a YAML mapping entry"))
            continue

        key = _unquote_key(match.group("key"))
        keys_at_level = seen_keys.setdefault(effective_indent, {})
        if key in keys_at_level:
            first_line = keys_at_level[key]
            issues.append(
                WorkflowIssue(
                    path,
                    line_number,
                    f"duplicate mapping key {key!r}; first declared on line {first_line}",
                )
            )
        else:
            keys_at_level[key] = line_number
        if effective_indent == 0:
            top_level_keys.add(key)

        value = (match.group("value") or "").strip()
        if _BLOCK_SCALAR.fullmatch(value):
            block_scalar_indent = effective_indent

    missing = sorted(_REQUIRED_TOP_LEVEL_KEYS - top_level_keys)
    if missing:
        issues.append(WorkflowIssue(path, 1, f"missing top-level keys: {', '.join(missing)}"))
    if issues:
        raise WorkflowValidationError(issues)


def validate_workflows(paths: Iterable[Path]) -> None:
    """Validate all supplied workflows and report every failing file together."""

    issues: list[WorkflowIssue] = []
    for path in sorted(paths):
        try:
            validate_workflow(path)
        except WorkflowValidationError as error:
            issues.extend(error.issues)
    if issues:
        raise WorkflowValidationError(issues)


def _default_workflows() -> list[Path]:
    root = Path(__file__).resolve().parents[1]
    workflow_root = root / ".github" / "workflows"
    return sorted((*workflow_root.glob("*.yml"), *workflow_root.glob("*.yaml")))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args(argv)
    paths = args.paths or _default_workflows()
    try:
        validate_workflows(paths)
    except WorkflowValidationError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    sys.stdout.write(f"validated {len(paths)} workflow file(s)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
