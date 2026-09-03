"""Build and verify a filesystem-derived project inventory.

The historical 28 by 8 grid remains useful as a planning convention, but it is
not evidence that a cell is complete. This verifier therefore reports the
artifacts actually present in the checkout and binds every category to a digest
of its repository-relative paths.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from collections.abc import Iterable

PLANNING_MODULES: Final = 28
PLANNING_CELLS_PER_MODULE: Final = 8
PLANNING_MATRIX_TOTAL: Final = PLANNING_MODULES * PLANNING_CELLS_PER_MODULE

PROVISIONAL_SOURCE_IDS: Final = (
    "M23_06",
    "M24_01",
    "M27_01",
    "M28_01",
    "M28_02",
    "M28_03",
    "M28_05",
    "M28_06",
    "M28_07",
    "M28_08",
)

_REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
_CONTRACT_ID: Final = re.compile(r"m\d{2}_\d{2}")
_MISSING_CATEGORIES_ERROR: Final = "inventory categories are missing: {missing}"
_NO_CONTRACTS_ERROR: Final = "no contract packages were discovered"
_PROVISIONAL_PRESENT_ERROR: Final = (
    "known provisional contracts unexpectedly have source packages: {present}"
)


class ProjectStatusError(RuntimeError):
    """Raised when a project inventory cannot be trusted."""


def _relative_paths(paths: Iterable[Path], *, root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in paths)


def _path_inventory(paths: Iterable[Path], *, root: Path) -> dict[str, object]:
    ordered_paths = sorted(paths, key=lambda path: path.relative_to(root).as_posix())
    relative_paths = _relative_paths(ordered_paths, root=root)
    path_payload = "\n".join(relative_paths).encode()
    content_hasher = hashlib.sha256()
    total_bytes = 0
    content_paths = {
        candidate
        for path in ordered_paths
        for candidate in ([path] if path.is_file() else path.rglob("*"))
        if candidate.is_file()
    }
    for path in sorted(content_paths, key=lambda candidate: candidate.relative_to(root).as_posix()):
        relative_path = path.relative_to(root).as_posix()
        content = path.read_bytes()
        total_bytes += len(content)
        content_hasher.update(relative_path.encode())
        content_hasher.update(b"\0")
        content_hasher.update(hashlib.sha256(content).digest())
    return {
        "count": len(relative_paths),
        "bytes": total_bytes,
        "path_digest": f"sha256:{hashlib.sha256(path_payload).hexdigest()}",
        "content_digest": f"sha256:{content_hasher.hexdigest()}",
    }


def _module_artifacts(modules_root: Path, filename: str) -> list[Path]:
    return [path for path in modules_root.rglob(filename) if path.is_file()]


def _suite_counts(test_files: Iterable[Path], *, tests_root: Path) -> dict[str, int]:
    suites = Counter(path.relative_to(tests_root).parts[0] for path in test_files)
    return dict(sorted(suites.items()))


def _inventory_digest(inventory: dict[str, object]) -> str:
    payload = json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def build_report(repository_root: Path | None = None) -> dict[str, object]:
    """Return a deterministic inventory of source, verification, and evidence files."""

    root = (repository_root or _REPOSITORY_ROOT).resolve()
    source_root = root / "src" / "glio_proteogen"
    contracts_root = source_root / "contracts"
    modules_root = source_root / "modules"
    adapters_root = source_root / "adapters"
    tests_root = root / "tests"
    evals_root = root / "evals"
    benchmarks_root = root / "benchmarks"
    research_evidence_root = root / "docs" / "research"
    evidence_roots = (
        root / "evidence",
        root / "release-evidence",
        root / "docs" / "evidence",
        root / "docs" / "release-evidence",
        research_evidence_root,
    )

    contract_packages = sorted(
        path
        for path in contracts_root.iterdir()
        if path.is_dir() and _CONTRACT_ID.fullmatch(path.name)
    )
    engines = _module_artifacts(source_root, "engine.py")
    services = _module_artifacts(modules_root, "service.py")
    plugins = _module_artifacts(modules_root, "plugin.py")
    module_apis = _module_artifacts(modules_root, "api.py")
    module_clis = _module_artifacts(modules_root, "cli.py")
    central_adapters = [path for path in adapters_root.glob("*.py") if path.is_file()]
    test_files = [path for path in tests_root.rglob("test_*.py") if path.is_file()]
    eval_directories = sorted(
        path
        for path in evals_root.iterdir()
        if path.is_dir() and _CONTRACT_ID.fullmatch(path.name)
    )
    eval_runners = [path / "run.py" for path in eval_directories if (path / "run.py").is_file()]
    alternate_evaluators = [
        candidate
        for path in eval_directories
        if not (path / "run.py").is_file()
        for candidate in (path / "evaluator.py", path / "evaluate.py")
        if candidate.is_file()
    ]
    evaluation_entrypoints = [*eval_runners, *alternate_evaluators]
    eval_benchmarks = [path for path in evals_root.glob("m*/benchmark.py") if path.is_file()]
    repository_benchmarks = [
        path
        for path in benchmarks_root.rglob("*.py")
        if path.is_file() and path.name != "__init__.py"
    ]
    all_benchmarks = [*eval_benchmarks, *repository_benchmarks]
    evidence_files = [
        path
        for evidence_root in evidence_roots
        for path in evidence_root.rglob("*")
        if path.is_file()
    ]
    structured_evidence = [path for path in evidence_files if path.suffix.lower() == ".json"]
    narrative_evidence = [path for path in evidence_files if path.suffix.lower() == ".md"]
    research_narrative_evidence = [
        path for path in research_evidence_root.rglob("*.md") if path.is_file()
    ]

    inventory: dict[str, object] = {
        "contracts": {
            **_path_inventory(contract_packages, root=root),
            "ids": [path.name.upper() for path in contract_packages],
        },
        "engines": {
            **_path_inventory(engines, root=root),
            "services": _path_inventory(services, root=root),
            "plugins": _path_inventory(plugins, root=root),
        },
        "adapters": {
            "central": _path_inventory(central_adapters, root=root),
            "module_api": _path_inventory(module_apis, root=root),
            "module_cli": _path_inventory(module_clis, root=root),
        },
        "tests": {
            **_path_inventory(test_files, root=root),
            "suite_counts": _suite_counts(test_files, tests_root=tests_root),
        },
        "evals": {
            "runners": _path_inventory(eval_runners, root=root),
            "alternate_evaluators": _path_inventory(alternate_evaluators, root=root),
            "entrypoints": _path_inventory(evaluation_entrypoints, root=root),
            "benchmarks": _path_inventory(all_benchmarks, root=root),
            "evaluation_benchmarks": _path_inventory(eval_benchmarks, root=root),
            "repository_benchmarks": _path_inventory(repository_benchmarks, root=root),
        },
        "evidence": {
            "all": _path_inventory(evidence_files, root=root),
            "structured_json": _path_inventory(structured_evidence, root=root),
            "narrative_markdown": _path_inventory(narrative_evidence, root=root),
            "research_narrative_markdown": _path_inventory(research_narrative_evidence, root=root),
        },
    }
    contracts = cast("dict[str, object]", inventory["contracts"])
    discovered_contract_ids = set(cast("list[str]", contracts["ids"]))
    provisional_ids = set(PROVISIONAL_SOURCE_IDS)
    return {
        "planning_assumption": {
            "modules": PLANNING_MODULES,
            "cells_per_module": PLANNING_CELLS_PER_MODULE,
            "matrix_total": PLANNING_MATRIX_TOTAL,
            "is_completion_claim": False,
        },
        "known_provisional_source_ids": list(PROVISIONAL_SOURCE_IDS),
        "provisional_contracts_present": sorted(discovered_contract_ids & provisional_ids),
        "inventory": inventory,
        "inventory_digest": _inventory_digest(inventory),
    }


def verify(repository_root: Path | None = None) -> dict[str, object]:
    """Verify that the checkout has coherent, non-empty inventory categories."""

    report = build_report(repository_root)
    inventory = cast("dict[str, object]", report["inventory"])
    required = ("contracts", "engines", "adapters", "tests", "evals", "evidence")
    missing = [category for category in required if category not in inventory]
    if missing:
        raise ProjectStatusError(_MISSING_CATEGORIES_ERROR.format(missing=missing))

    contracts = cast("dict[str, object]", inventory["contracts"])
    if not contracts["count"]:
        raise ProjectStatusError(_NO_CONTRACTS_ERROR)
    if report["provisional_contracts_present"]:
        raise ProjectStatusError(
            _PROVISIONAL_PRESENT_ERROR.format(present=report["provisional_contracts_present"])
        )
    return report


def main() -> int:
    sys.stdout.write(json.dumps(verify(), indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
