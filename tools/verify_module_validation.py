"""Build content-bound validation receipts for every discovered governed module.

The project-status inventory deliberately answers only "what files exist?".  This
verifier answers the narrower and stronger engineering question "does every source
module close over an importable contract, implementation, evaluator, benchmark,
tests, and evidence?".  Static closure is the default.  Evaluators can optionally be
executed in fresh Python processes. Benchmarks can independently be executed as
bounded smoke probes; ambiguous evaluator or benchmark output fails closed.

Passing this verifier is engineering evidence.  It does not promote provisional
contracts, validate scientific or clinical utility, or establish release authority.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import inspect
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast, get_args

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType
    from xml.etree.ElementTree import Element

SCHEMA_VERSION: Final = "glio-module-validation/1.2.0"
STATIC_PROFILE_ID: Final = "module-static-closure/1.2.0"
EVALUATOR_PROFILE_ID: Final = "module-evaluator-closure/1.2.0"
BENCHMARK_PROFILE_ID: Final = "module-benchmark-closure/1.0.0"
EVALUATOR_BENCHMARK_PROFILE_ID: Final = "module-evaluator-benchmark-closure/1.0.0"
DEFAULT_EVALUATOR_TIMEOUT_SECONDS: Final = 180.0
DEFAULT_BENCHMARK_TIMEOUT_SECONDS: Final = 30.0
MAX_EVALUATOR_OUTPUT_BYTES: Final = 4 * 1024 * 1024
MAX_BENCHMARK_OUTPUT_BYTES: Final = 4 * 1024 * 1024
BENCHMARK_SMOKE_ITERATIONS: Final = 5
MAX_TEST_EVIDENCE_BYTES: Final = 64 * 1024 * 1024
SHARD_ALGORITHM: Final = "sorted-round-robin/1.0.0"
JUNIT_EVIDENCE_PROFILE_ID: Final = "pytest-junit-module-binding/1.1.0"
COVERAGE_EVIDENCE_PROFILE_ID: Final = "coveragepy-governed-source-binding/1.0.0"
_BRANCH_ARC_SIZE: Final = 2
_PERCENT_MAX: Final = 100.0

_REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
_SOURCE_ID: Final = re.compile(r"m(?P<chapter>\d{2})_(?P<cell>\d{2})\Z")
_MODULE_DIRECTORY: Final = re.compile(r"(?P<source_id>m\d{2}_\d{2})(?:_.+)?\Z")
_PATH_MODULE_ID: Final = re.compile(
    r"(?<![a-z0-9])m(?P<chapter>\d{2})[-_]?(?P<cell>\d{2})(?!\d)",
    re.IGNORECASE,
)
_SCHEMA_ID: Final = re.compile(
    r"^urn:aurora-neuro:glio-proteogen:"
    r"(?P<module_id>GLIO-PROTEOGEN-M\d{2}-\d{2}):"
    r"(?P<version>[^:]+):(?P<name>[^:]+)$"
)
_EVALUATOR_FILES: Final = ("run.py", "evaluator.py", "evaluate.py")
_EVALUATOR_CALLABLES: Final = (
    "run_evaluator",
    "run_evaluation",
    "evaluate",
    "run",
)
_BENCHMARK_CALLABLES: Final = ("run_benchmark", "run", "benchmark")
_EVIDENCE_ROOTS: Final = (
    "release-evidence",
    "evidence",
    "docs/evidence",
    "docs/release-evidence",
    "docs/modules",
)
_IGNORED_CONTENT_PARTS: Final = frozenset({"__pycache__", ".pytest_cache"})


class ModuleValidationError(RuntimeError):
    """A module-validation report contains one or more failed closure gates."""

    def __init__(self, failed_modules: int) -> None:
        super().__init__(f"module validation failed for {failed_modules} module(s)")


class _InvalidContractExportError(TypeError):
    def __init__(self) -> None:
        super().__init__("contract schema exporter returned an invalid value")


class _InvalidModuleSourceIdError(ValueError):
    def __init__(self) -> None:
        super().__init__("invalid module source identifier")


class _InvalidTimeoutError(ValueError):
    def __init__(self) -> None:
        super().__init__("evaluator timeout must be a positive finite number")


class _InvalidBenchmarkTimeoutError(ValueError):
    def __init__(self) -> None:
        super().__init__("benchmark timeout must be a positive finite number")


class ModuleScopeError(ValueError):
    """Requested module selection or shard configuration is invalid."""

    def __init__(self, code: str) -> None:
        super().__init__(f"invalid module validation scope: {code}")


class EvidenceConfigurationError(ValueError):
    """Requested test-evidence configuration is internally inconsistent."""

    def __init__(self, code: str) -> None:
        super().__init__(f"invalid module test-evidence configuration: {code}")


class _InvalidEvidenceJsonError(ValueError):
    pass


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _content_digest(paths: Iterable[Path], *, root: Path) -> str:
    """Bind sorted relative paths, lengths, and bytes without loading all files at once."""

    digest = hashlib.sha256()
    resolved_root = root.resolve()
    unique = sorted({path.resolve() for path in paths}, key=lambda path: path.as_posix())
    for path in unique:
        relative = path.relative_to(resolved_root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        size = path.stat().st_size
        digest.update(size.to_bytes(8, "big"))
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _files_below(path: Path) -> tuple[Path, ...]:
    if not path.is_dir():
        return ()
    return tuple(
        candidate
        for candidate in path.rglob("*")
        if candidate.is_file()
        and not _IGNORED_CONTENT_PARTS.intersection(candidate.relative_to(path).parts)
        and candidate.suffix != ".pyc"
    )


def _source_id_to_module_id(source_id: str) -> str:
    match = _SOURCE_ID.fullmatch(source_id)
    if match is None:
        raise _InvalidModuleSourceIdError
    return f"GLIO-PROTEOGEN-M{match['chapter']}-{match['cell']}"


def _normalize_module_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper().replace("_", "-")
    if re.fullmatch(r"M\d{2}-\d{2}", normalized):
        return f"GLIO-PROTEOGEN-{normalized}"
    if re.fullmatch(r"GLIO-PROTEOGEN-M\d{2}-\d{2}", normalized):
        return normalized
    return None


def _ids_in_path(path: Path) -> frozenset[str]:
    return frozenset(
        f"m{match['chapter']}_{match['cell']}"
        for match in _PATH_MODULE_ID.finditer(path.as_posix())
    )


def _relative(paths: Iterable[Path], *, root: Path) -> list[str]:
    resolved_root = root.resolve()
    return sorted(path.resolve().relative_to(resolved_root).as_posix() for path in set(paths))


def discover_repository(repository_root: Path | None = None) -> dict[str, object]:
    """Discover the contract/module bijection and supporting per-module artifacts."""

    root = (repository_root or _REPOSITORY_ROOT).resolve()
    source_root = root / "src" / "glio_proteogen"
    contracts_root = source_root / "contracts"
    modules_root = source_root / "modules"
    contract_directories = contracts_root.iterdir() if contracts_root.is_dir() else ()
    contract_paths = {
        path.name: path
        for path in contract_directories
        if path.is_dir() and _SOURCE_ID.fullmatch(path.name)
    }
    module_paths: dict[str, list[Path]] = defaultdict(list)
    module_directories = modules_root.rglob("*") if modules_root.is_dir() else ()
    for path in module_directories:
        if not path.is_dir():
            continue
        match = _MODULE_DIRECTORY.fullmatch(path.name)
        if match is not None:
            module_paths[match["source_id"]].append(path)

    contract_ids = set(contract_paths)
    module_ids = set(module_paths)
    duplicates = {
        source_id: _relative(paths, root=root)
        for source_id, paths in sorted(module_paths.items())
        if len(paths) != 1
    }
    closed_ids = sorted(contract_ids & module_ids - set(duplicates))

    test_paths = tuple((root / "tests").rglob("test_*.py"))
    benchmark_paths = tuple(
        path
        for path in (root / "benchmarks").rglob("*.py")
        if path.is_file() and path.name != "__init__.py"
    )
    evidence_paths = tuple(
        path
        for relative_root in _EVIDENCE_ROOTS
        for path in (root / relative_root).rglob("*")
        if path.is_file()
    )
    tests_by_id = _associate_paths(test_paths, closed_ids)
    repository_benchmarks_by_id = _associate_paths(benchmark_paths, closed_ids)
    evidence_by_id = _associate_paths(evidence_paths, closed_ids)

    modules: list[dict[str, object]] = []
    for source_id in closed_ids:
        module_path = module_paths[source_id][0]
        evaluator_paths = [
            root / "evals" / source_id / filename
            for filename in _EVALUATOR_FILES
            if (root / "evals" / source_id / filename).is_file()
        ]
        evaluation_benchmark = root / "evals" / source_id / "benchmark.py"
        benchmarks = list(repository_benchmarks_by_id[source_id])
        if evaluation_benchmark.is_file():
            benchmarks.append(evaluation_benchmark)
        modules.append(
            {
                "source_id": source_id,
                "module_id": _source_id_to_module_id(source_id),
                "contract_path": contract_paths[source_id],
                "module_path": module_path,
                "evaluator_paths": tuple(evaluator_paths),
                "benchmark_paths": tuple(sorted(set(benchmarks))),
                "test_paths": tests_by_id[source_id],
                "evidence_paths": evidence_by_id[source_id],
            }
        )
    return {
        "root": root,
        "modules": modules,
        "contract_ids": sorted(contract_ids),
        "module_ids": sorted(module_ids),
        "duplicate_module_ids": duplicates,
        "orphan_contracts": sorted(contract_ids - module_ids),
        "orphan_modules": sorted(module_ids - contract_ids),
        "missing_roots": sorted(
            relative
            for relative, path in (
                ("src/glio_proteogen/contracts", contracts_root),
                ("src/glio_proteogen/modules", modules_root),
            )
            if not path.is_dir()
        ),
    }


def _select_module_records(
    records: Sequence[Mapping[str, object]],
    *,
    module_ids: Sequence[str] | None,
    shard_index: int | None,
    shard_count: int | None,
) -> tuple[list[Mapping[str, object]], dict[str, object]]:
    all_by_id = {cast("str", record["module_id"]): record for record in records}
    all_ids = sorted(all_by_id)
    requested = _normalize_requested_module_ids(module_ids, known_ids=frozenset(all_ids))
    candidate_ids = requested if requested is not None else all_ids
    normalized_shard = _normalize_shard(
        shard_index=shard_index,
        shard_count=shard_count,
        candidate_count=len(candidate_ids),
    )
    selected_ids = (
        candidate_ids
        if normalized_shard is None
        else [
            module_id
            for position, module_id in enumerate(candidate_ids)
            if position % normalized_shard[1] == normalized_shard[0]
        ]
    )
    if not selected_ids and (module_ids is not None or normalized_shard is not None):
        raise ModuleScopeError("empty-selection")
    mode = (
        "selection+shard"
        if requested is not None and normalized_shard is not None
        else "selection"
        if requested is not None
        else "shard"
        if normalized_shard is not None
        else "all"
    )
    scope: dict[str, object] = {
        "mode": mode,
        "selection_algorithm": SHARD_ALGORITHM,
        "requested_module_ids": requested or [],
        "candidate_module_count": len(candidate_ids),
        "candidate_module_ids": candidate_ids,
        "shard_index": normalized_shard[0] if normalized_shard is not None else None,
        "shard_count": normalized_shard[1] if normalized_shard is not None else None,
        "selected_module_count": len(selected_ids),
        "selected_module_ids": selected_ids,
        "excluded_module_count": len(all_ids) - len(selected_ids),
    }
    scope["selected_scope_digest"] = _digest_bytes(_canonical_bytes(scope))
    return [all_by_id[module_id] for module_id in selected_ids], scope


def _normalize_requested_module_ids(
    module_ids: Sequence[str] | None, *, known_ids: frozenset[str]
) -> list[str] | None:
    if module_ids is None:
        return None
    if isinstance(module_ids, str) or not module_ids:
        raise ModuleScopeError("module-selection-must-be-a-non-empty-sequence")
    normalized: list[str] = []
    for value in module_ids:
        module_id = _normalize_module_id(value)
        if module_id is None:
            raise ModuleScopeError("invalid-module-id")
        normalized.append(module_id)
    if len(normalized) != len(set(normalized)):
        raise ModuleScopeError("duplicate-module-id")
    unknown = sorted(set(normalized) - known_ids)
    if unknown:
        raise ModuleScopeError(f"unknown-module-id:{','.join(unknown)}")
    return sorted(normalized)


def _normalize_shard(
    *, shard_index: int | None, shard_count: int | None, candidate_count: int
) -> tuple[int, int] | None:
    if shard_index is None and shard_count is None:
        return None
    if shard_index is None or shard_count is None:
        raise ModuleScopeError("shard-index-and-count-required-together")
    if type(shard_index) is not int or type(shard_count) is not int:
        raise ModuleScopeError("shard-values-must-be-integers")
    if shard_count <= 0:
        raise ModuleScopeError("shard-count-must-be-positive")
    if shard_index < 0 or shard_index >= shard_count:
        raise ModuleScopeError("shard-index-out-of-range")
    if shard_count > candidate_count:
        raise ModuleScopeError("shard-count-exceeds-candidate-count")
    return shard_index, shard_count


def _associate_paths(
    paths: Iterable[Path], source_ids: Sequence[str]
) -> dict[str, tuple[Path, ...]]:
    known = frozenset(source_ids)
    associated: dict[str, list[Path]] = {source_id: [] for source_id in source_ids}
    for path in paths:
        for source_id in sorted(_ids_in_path(path) & known):
            associated[source_id].append(path)
    return {
        source_id: tuple(sorted(set(module_paths)))
        for source_id, module_paths in associated.items()
    }


@contextmanager
def _repository_import_path(root: Path) -> Iterator[None]:
    source_path = str((root / "src").resolve())
    inserted = source_path not in sys.path
    prefix = "glio_proteogen"
    displaced = {
        name: module
        for name, module in sys.modules.items()
        if name == prefix or name.startswith(f"{prefix}.")
    }
    for name in displaced:
        del sys.modules[name]
    if inserted:
        sys.path.insert(0, source_path)
    importlib.invalidate_caches()
    try:
        yield
    finally:
        for name in tuple(sys.modules):
            if name == prefix or name.startswith(f"{prefix}."):
                del sys.modules[name]
        sys.modules.update(displaced)
        if inserted:
            sys.path.remove(source_path)
        importlib.invalidate_caches()


def _contract_schemas(module: object) -> dict[str, dict[str, object]]:
    plural = getattr(module, "contract_json_schemas", None)
    if callable(plural):
        candidate = plural()
        if not isinstance(candidate, Mapping) or not candidate:
            raise _InvalidContractExportError
        if any(
            not isinstance(name, str) or not isinstance(document, dict)
            for name, document in candidate.items()
        ):
            raise _InvalidContractExportError
        return {
            str(name): cast("dict[str, object]", document) for name, document in candidate.items()
        }
    alias = getattr(module, "ContractName", None)
    names = get_args(getattr(alias, "__value__", alias))
    exporter = getattr(module, "contract_json_schema", None)
    if not callable(exporter) or not names or any(not isinstance(name, str) for name in names):
        raise _InvalidContractExportError
    exported = {name: exporter(name) for name in cast("tuple[str, ...]", names)}
    if any(not isinstance(document, dict) for document in exported.values()):
        raise _InvalidContractExportError
    return cast("dict[str, dict[str, object]]", exported)


def _schema_identity_failures(
    name: str,
    document: Mapping[str, object],
    *,
    expected_module_id: str,
) -> tuple[list[str], str | None]:
    failures: list[str] = []
    if document.get("$schema") != Draft202012Validator.META_SCHEMA["$id"]:
        failures.append(f"schema_dialect:{name}")
    try:
        Draft202012Validator.check_schema(document)
    except SchemaError:
        failures.append(f"schema_invalid:{name}")
    schema_id = document.get("$id")
    match = _SCHEMA_ID.fullmatch(schema_id) if isinstance(schema_id, str) else None
    if match is None:
        failures.append(f"schema_id_invalid:{name}")
        return failures, None
    version = match["version"]
    if match["module_id"] != expected_module_id:
        failures.append(f"schema_module_id:{name}")
    if match["name"] != name:
        failures.append(f"schema_name:{name}")
    metadata = document.get("x-glio-contract")
    if isinstance(metadata, Mapping):
        if _normalize_module_id(metadata.get("moduleId")) != expected_module_id:
            failures.append(f"schema_metadata_module_id:{name}")
        declared_version = metadata.get("contractVersion")
        if declared_version is not None and declared_version != version:
            failures.append(f"schema_metadata_version:{name}")
    return failures, version


def _validate_contract(source_id: str) -> dict[str, object]:
    expected_module_id = _source_id_to_module_id(source_id)
    failures: list[str] = []
    try:
        schema_module = importlib.import_module(f"glio_proteogen.contracts.{source_id}.schema")
        first = _contract_schemas(schema_module)
        second = _contract_schemas(schema_module)
        first_bytes = _canonical_bytes(first)
        second_bytes = _canonical_bytes(second)
    except (ImportError, AttributeError, TypeError, ValueError) as error:
        return {
            "passed": False,
            "imported": False,
            "schema_count": 0,
            "schema_digest": None,
            "versions": [],
            "failures": [f"schema_import:{type(error).__name__}"],
        }
    deterministic = first_bytes == second_bytes
    if not deterministic:
        failures.append("schema_nondeterministic")
    names = set(first)
    if "request" not in names:
        failures.append("request_schema_missing")
    if "output" not in names:
        failures.append("output_schema_missing")
    versions: set[str] = set()
    for name, document in sorted(first.items()):
        schema_failures, version = _schema_identity_failures(
            name,
            document,
            expected_module_id=expected_module_id,
        )
        failures.extend(schema_failures)
        if version is not None:
            versions.add(version)
    if len(versions) != 1:
        failures.append("schema_version_incoherent")
    return {
        "passed": not failures,
        "imported": True,
        "schema_count": len(first),
        "schema_digest": _digest_bytes(first_bytes),
        "deterministic": deterministic,
        "request_present": "request" in names,
        "output_present": "output" in names,
        "versions": sorted(versions),
        "failures": sorted(set(failures)),
    }


def _import_module(name: str) -> tuple[ModuleType | None, str | None]:
    try:
        return importlib.import_module(name), None
    except Exception as error:  # noqa: BLE001 - imports are untrusted validation targets.
        return None, f"import:{name}:{type(error).__name__}"


def _inspect_plugin(plugin_module: ModuleType | None, *, package_name: str) -> dict[str, object]:
    failures: list[str] = []
    if plugin_module is None:
        return {
            "class_name": None,
            "validation_entrypoint": None,
            "run_entrypoint": None,
            "descriptor_style": "missing",
            "failures": failures,
        }
    plugin_classes = [
        value
        for name, value in vars(plugin_module).items()
        if name.endswith("Plugin")
        and inspect.isclass(value)
        and value.__module__ == f"{package_name}.plugin"
    ]
    if len(plugin_classes) != 1:
        failures.append("plugin_class_count")
        return {
            "class_name": None,
            "validation_entrypoint": None,
            "run_entrypoint": None,
            "descriptor_style": "missing",
            "failures": failures,
        }
    plugin_class = plugin_classes[0]
    has_run = callable(getattr(plugin_class, "run", None))
    if not has_run:
        failures.append("plugin_run_missing")
    validation_entrypoint = next(
        (
            name
            for name in ("validate", "validate_request", "validate_json")
            if callable(getattr(plugin_class, name, None))
        ),
        None,
    )
    if validation_entrypoint is None:
        failures.append("plugin_validation_missing")
    descriptor = inspect.getattr_static(plugin_class, "descriptor", None)
    descriptor_style = (
        "method"
        if inspect.isfunction(descriptor)
        else "attribute"
        if descriptor is not None
        else "missing"
    )
    return {
        "class_name": plugin_class.__name__,
        "validation_entrypoint": validation_entrypoint,
        "run_entrypoint": "run" if has_run else None,
        "descriptor_style": descriptor_style,
        "failures": failures,
    }


def _validate_implementation(
    module_record: Mapping[str, object], *, root: Path
) -> dict[str, object]:
    module_path = cast("Path", module_record["module_path"])
    source_root = root / "src"
    package_name = ".".join(module_path.relative_to(source_root).parts)
    failures: list[str] = []
    imported: list[str] = []
    import_names = (package_name, f"{package_name}.service", f"{package_name}.plugin")
    loaded: dict[str, ModuleType] = {}
    for name in import_names:
        module, failure = _import_module(name)
        if module is not None:
            loaded[name] = module
            imported.append(name.rsplit(".", maxsplit=1)[-1])
        elif failure is not None:
            failures.append(failure)
    plugin = _inspect_plugin(
        loaded.get(f"{package_name}.plugin"),
        package_name=package_name,
    )
    failures.extend(cast("list[str]", plugin["failures"]))
    engine_path = module_path / "engine.py"
    if engine_path.is_file():
        engine_name = f"{package_name}.engine"
        engine_module, engine_failure = _import_module(engine_name)
        if engine_module is not None:
            imported.append("engine")
        elif engine_failure is not None:
            failures.append(engine_failure)
    return {
        "passed": not failures,
        "package_name": package_name,
        "imported_components": sorted(set(imported)),
        "engine_layout": "engine.py" if engine_path.is_file() else "alternate",
        "plugin_class": plugin["class_name"],
        "validation_entrypoint": plugin["validation_entrypoint"],
        "run_entrypoint": plugin["run_entrypoint"],
        "descriptor_style": plugin["descriptor_style"],
        "failures": sorted(failures),
    }


def _required_arguments(function: ast.FunctionDef) -> int:
    positional = (*function.args.posonlyargs, *function.args.args)
    positional_count = max(0, len(positional) - len(function.args.defaults))
    keyword_only_count = sum(default is None for default in function.args.kw_defaults)
    return positional_count + keyword_only_count


def _is_main_guard_comparison(test: ast.expr) -> bool:
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or len(test.comparators) != 1:
        return False
    if not isinstance(test.ops[0], ast.Eq):
        return False
    left, right = test.left, test.comparators[0]
    return (
        isinstance(left, ast.Name)
        and left.id == "__name__"
        and isinstance(right, ast.Constant)
        and right.value == "__main__"
    ) or (
        isinstance(right, ast.Name)
        and right.id == "__name__"
        and isinstance(left, ast.Constant)
        and left.value == "__main__"
    )


def _discover_evaluator(
    source_id: str, evaluator_paths: Sequence[Path], *, root: Path
) -> dict[str, object]:
    if not evaluator_paths:
        return {
            "passed": False,
            "status": "missing",
            "entrypoint": None,
            "alternatives": [],
            "failures": ["evaluator_missing"],
        }
    ordered = sorted(
        evaluator_paths,
        key=lambda path: _EVALUATOR_FILES.index(path.name),
    )
    selected = ordered[0]
    module_name = f"evals.{source_id}.{selected.stem}"
    try:
        source = selected.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError, UnicodeDecodeError) as error:
        return {
            "passed": False,
            "status": "invalid",
            "entrypoint": module_name,
            "alternatives": _relative(ordered[1:], root=root),
            "failures": [f"evaluator_parse:{type(error).__name__}"],
        }
    has_main_guard = any(
        isinstance(node, ast.If) and _is_main_guard_comparison(node.test) for node in tree.body
    )
    callable_name: str | None = None
    required_arguments: int | None = None
    if not has_main_guard:
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        for name in _EVALUATOR_CALLABLES:
            function = functions.get(name)
            if function is not None:
                callable_name = name
                required_arguments = _required_arguments(function)
                break
    failures: list[str] = []
    if not has_main_guard and callable_name is None:
        failures.append("evaluator_entrypoint_missing")
    status = (
        "module"
        if has_main_guard
        else "callable"
        if required_arguments == 0
        else "requires_arguments"
    )
    return {
        "passed": not failures,
        "status": status,
        "entrypoint": module_name,
        "callable": callable_name,
        "required_arguments": required_arguments,
        "path": selected.relative_to(root).as_posix(),
        "alternatives": _relative(ordered[1:], root=root),
        "failures": failures,
    }


def _benchmark_invocation(function: ast.FunctionDef) -> tuple[str, int | None]:
    if function.args.vararg is not None or function.args.kwarg is not None:
        return "requires_arguments", None
    positional = (*function.args.posonlyargs, *function.args.args)
    keyword_only = tuple(function.args.kwonlyargs)
    parameters = (*positional, *keyword_only)
    iteration_parameters = [parameter for parameter in parameters if parameter.arg == "iterations"]
    required_positional = positional[: len(positional) - len(function.args.defaults)]
    required_keyword_only = [
        parameter
        for parameter, default in zip(keyword_only, function.args.kw_defaults, strict=True)
        if default is None
    ]
    required_names = {parameter.arg for parameter in (*required_positional, *required_keyword_only)}
    if required_names - {"iterations"} or len(iteration_parameters) > 1:
        return "requires_arguments", None
    if not iteration_parameters:
        return "no_arguments", None
    iteration = iteration_parameters[0]
    if iteration in function.args.posonlyargs:
        if function.args.posonlyargs.index(iteration) != 0:
            return "requires_arguments", None
        return "positional_iterations", BENCHMARK_SMOKE_ITERATIONS
    return "keyword_iterations", BENCHMARK_SMOKE_ITERATIONS


def _benchmark_module_name(path: Path, *, root: Path) -> str:
    return ".".join(path.relative_to(root).with_suffix("").parts)


def _discover_benchmark(
    source_id: str, benchmark_paths: Sequence[Path], *, root: Path
) -> dict[str, object]:
    if not benchmark_paths:
        return {
            "passed": False,
            "status": "missing",
            "entrypoint": None,
            "alternatives": [],
            "failures": ["benchmark_missing"],
        }
    evaluation_path = root / "evals" / source_id / "benchmark.py"
    ordered = sorted(
        set(benchmark_paths),
        key=lambda path: (path.resolve() != evaluation_path.resolve(), path.as_posix()),
    )
    selected = ordered[0]
    module_name = _benchmark_module_name(selected, root=root)
    try:
        tree = ast.parse(selected.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError) as error:
        return {
            "passed": False,
            "status": "invalid",
            "entrypoint": module_name,
            "path": selected.relative_to(root).as_posix(),
            "alternatives": _relative(ordered[1:], root=root),
            "failures": [f"benchmark_parse:{type(error).__name__}"],
        }
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    callable_name = next((name for name in _BENCHMARK_CALLABLES if name in functions), None)
    has_main_guard = any(
        isinstance(node, ast.If) and _is_main_guard_comparison(node.test) for node in tree.body
    )
    invocation = "module" if callable_name is None and has_main_guard else None
    smoke_iterations: int | None = None
    if callable_name is not None:
        invocation, smoke_iterations = _benchmark_invocation(functions[callable_name])
    failures: list[str] = []
    if invocation is None:
        failures.append("benchmark_entrypoint_missing")
    elif invocation == "requires_arguments":
        failures.append("benchmark_requires_arguments")
    return {
        "passed": not failures,
        "status": (
            "callable" if callable_name is not None else "module" if has_main_guard else "missing"
        ),
        "entrypoint": module_name,
        "callable": callable_name,
        "invocation": invocation,
        "smoke_iterations": smoke_iterations,
        "path": selected.relative_to(root).as_posix(),
        "alternatives": _relative(ordered[1:], root=root),
        "failures": failures,
    }


def normalize_evaluator_report(payload: object, *, expected_module_id: str) -> dict[str, object]:
    """Normalize heterogeneous historical evaluator reports without guessing success."""

    if not isinstance(payload, Mapping):
        return _normalization_failure("evaluator_report_not_object")
    if not _evaluator_module_identity_matches(payload, expected_module_id):
        return _normalization_failure("evaluator_module_id")

    votes, totals, passed_counts = _evaluator_boolean_evidence(payload)
    numeric_votes, numeric_totals, numeric_passed = _evaluator_numeric_evidence(payload)
    votes.extend(numeric_votes)
    totals.extend(numeric_totals)
    passed_counts.extend(numeric_passed)
    if not votes:
        return _normalization_failure("evaluator_result_ambiguous")
    normalized_pass = all(votes)
    failures = [] if normalized_pass else ["evaluator_report_failed"]
    return {
        "passed": normalized_pass,
        "module_id": expected_module_id,
        "scenario_total": max(totals, default=None),
        "scenario_passed": max(passed_counts, default=None),
        "report_digest": _digest_bytes(_canonical_bytes(payload)),
        "failures": failures,
    }


def _benchmark_pass_evidence(payload: Mapping[object, object]) -> list[tuple[str, bool]]:
    evidence: list[tuple[str, bool]] = []
    for key, value in payload.items():
        if not isinstance(key, str):
            continue
        token = re.sub(r"[^a-z0-9]", "", key.lower())
        explicit = token in {"passed", "budgetpassed", "withinbudget", "allbudgetspassed"}
        component = "budget" in token and ("pass" in token or "within" in token)
        if type(value) is bool and (explicit or component):
            evidence.append((key, value))
        if isinstance(value, Mapping) and "budget" in token:
            for child_key, child_value in value.items():
                if isinstance(child_key, str) and type(child_value) is bool:
                    child_token = re.sub(r"[^a-z0-9]", "", child_key.lower())
                    if "pass" in child_token or "within" in child_token:
                        evidence.append((f"{key}.{child_key}", child_value))
    return sorted(evidence)


def _benchmark_budget_evidence(
    value: object, *, path: tuple[str, ...] = ()
) -> list[tuple[str, int | float]]:
    if not isinstance(value, Mapping):
        return []
    evidence: list[tuple[str, int | float]] = []
    for key, child in value.items():
        if not isinstance(key, str):
            continue
        child_path = (*path, key)
        if isinstance(child, Mapping):
            evidence.extend(_benchmark_budget_evidence(child, path=child_path))
        elif (
            type(child) in {int, float}
            and math.isfinite(child)
            and child > 0
            and any("budget" in re.sub(r"[^a-z0-9]", "", part.lower()) for part in child_path)
        ):
            evidence.append((".".join(child_path), child))
    return sorted(evidence)


def _benchmark_normalization_failure(code: str) -> dict[str, object]:
    return {
        "passed": False,
        "module_id": None,
        "pass_evidence_count": 0,
        "pass_evidence": [],
        "budget_evidence_count": 0,
        "budget_evidence": [],
        "budget_evidence_digest": None,
        "report_digest": None,
        "failures": [code],
    }


def normalize_benchmark_report(payload: object, *, expected_module_id: str) -> dict[str, object]:
    """Require explicit module-bound budget and pass evidence from a benchmark report."""

    if not isinstance(payload, Mapping):
        return _benchmark_normalization_failure("benchmark_report_not_object")
    if not _evaluator_module_identity_matches(payload, expected_module_id):
        return _benchmark_normalization_failure("benchmark_module_id")
    pass_evidence = _benchmark_pass_evidence(payload)
    if not pass_evidence:
        return _benchmark_normalization_failure("benchmark_pass_evidence_missing")
    budget_evidence = _benchmark_budget_evidence(payload)
    if not budget_evidence:
        return _benchmark_normalization_failure("benchmark_budget_evidence_missing")
    try:
        report_digest = _digest_bytes(_canonical_bytes(payload))
        budget_digest = _digest_bytes(_canonical_bytes(budget_evidence))
    except (TypeError, ValueError):
        return _benchmark_normalization_failure("benchmark_report_not_canonical")
    passed = all(result for _, result in pass_evidence)
    return {
        "passed": passed,
        "module_id": expected_module_id,
        "pass_evidence_count": len(pass_evidence),
        "pass_evidence": [{"path": path, "passed": result} for path, result in pass_evidence],
        "budget_evidence_count": len(budget_evidence),
        "budget_evidence": [{"path": path, "value": value} for path, value in budget_evidence],
        "budget_evidence_digest": budget_digest,
        "report_digest": report_digest,
        "failures": [] if passed else ["benchmark_report_failed"],
    }


def _evaluator_module_identity_matches(
    payload: Mapping[object, object], expected_module_id: str
) -> bool:
    declared_values = [
        payload[key] for key in ("module_id", "moduleId", "module") if key in payload
    ]
    normalized = [_normalize_module_id(value) for value in declared_values]
    return bool(normalized) and all(value == expected_module_id for value in normalized)


def _collection_boolean_evidence(value: object) -> tuple[bool | None, int, int]:
    if isinstance(value, Mapping):
        items: Sequence[object] = tuple(value.values())
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes):
        items = value
    else:
        return None, 0, 0
    results: list[bool | None] = []
    for item in items:
        if type(item) is bool:
            results.append(item)
        elif isinstance(item, Mapping) and type(item.get("passed")) is bool:
            results.append(item["passed"])
        else:
            results.append(None)
    valid_results = [result for result in results if result is not None]
    if not valid_results:
        return None, 0, 0
    vote = len(valid_results) == len(results) and all(valid_results)
    return vote, len(results), sum(valid_results)


def _evaluator_boolean_evidence(
    payload: Mapping[object, object],
) -> tuple[list[bool], list[int], list[int]]:
    votes: list[bool] = []
    totals: list[int] = []
    passed_counts: list[int] = []
    for key in ("all_passed", "allPassed", "passed"):
        value = payload.get(key)
        if type(value) is bool:
            votes.append(value)
    for key in ("checks", "scenarios"):
        vote, total, passed = _collection_boolean_evidence(payload.get(key))
        if vote is not None:
            votes.append(vote)
            totals.append(total)
            passed_counts.append(passed)
    return votes, totals, passed_counts


def _evaluator_numeric_evidence(
    payload: Mapping[object, object],
) -> tuple[list[bool], list[int], list[int]]:
    totals = _integer_values(
        payload,
        (
            "total",
            "total_cases",
            "scenario_count",
            "scenarioCount",
            "executed_cases",
            "checks_declared",
            "declared_cases",
        ),
    )
    passed_counts = _integer_values(
        payload,
        ("passed", "passed_count", "passed_cases", "checks_passed"),
    )
    if not totals or not passed_counts:
        return [], [], []
    unique_totals = set(totals)
    unique_passed = set(passed_counts)
    total = max(totals)
    passed = max(passed_counts)
    vote = len(unique_totals) == 1 and len(unique_passed) == 1 and total > 0 and passed == total
    return [vote], [total], [passed]


def _integer_values(payload: Mapping[object, object], keys: Sequence[str]) -> list[int]:
    return [value for key in keys if type(value := payload.get(key)) is int and value >= 0]


def _normalization_failure(code: str) -> dict[str, object]:
    return {
        "passed": False,
        "module_id": None,
        "scenario_total": None,
        "scenario_passed": None,
        "report_digest": None,
        "failures": [code],
    }


def _execute_evaluator(
    discovery: Mapping[str, object],
    *,
    expected_module_id: str,
    root: Path,
    timeout_seconds: float,
) -> dict[str, object]:
    if discovery.get("passed") is not True:
        return _normalization_failure("evaluator_not_discoverable")
    if discovery.get("status") == "requires_arguments":
        return _normalization_failure("evaluator_requires_arguments")
    module_name = cast("str", discovery["entrypoint"])
    if discovery.get("status") == "module":
        command = [sys.executable, "-m", module_name]
    else:
        callable_name = cast("str", discovery["callable"])
        child = (
            "import dataclasses,importlib,json;"
            f"value=getattr(importlib.import_module({module_name!r}),{callable_name!r})();"
            "value=dataclasses.asdict(value) if dataclasses.is_dataclass(value) else "
            "value.model_dump(mode='json') if hasattr(value,'model_dump') else value;"
            "print(json.dumps(value,sort_keys=True,allow_nan=False))"
        )
        command = [sys.executable, "-c", child]
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("COV_CORE_") and not key.startswith("COVERAGE_")
    }
    existing_python_path = environment.get("PYTHONPATH")
    source_path = str((root / "src").resolve())
    environment["PYTHONPATH"] = (
        source_path
        if not existing_python_path
        else f"{source_path}{os.pathsep}{existing_python_path}"
    )
    environment["PYTHONHASHSEED"] = "0"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    process_failure: str | None = None
    completed: subprocess.CompletedProcess[str] | None = None
    try:
        completed = subprocess.run(  # noqa: S603 - fixed interpreter and discovered local module.
            command,
            cwd=root,
            env=environment,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="strict",
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        process_failure = "evaluator_timeout"
    except (OSError, UnicodeError):
        process_failure = "evaluator_process_error"
    if process_failure is not None or completed is None:
        return _normalization_failure(process_failure or "evaluator_process_error")
    output = completed.stdout.encode("utf-8")
    error_output = completed.stderr.encode("utf-8")
    validation_failure = (
        "evaluator_output_too_large"
        if len(output) > MAX_EVALUATOR_OUTPUT_BYTES
        or len(error_output) > MAX_EVALUATOR_OUTPUT_BYTES
        else "evaluator_exit_nonzero"
        if completed.returncode != 0
        else None
    )
    if validation_failure is not None:
        return _normalization_failure(validation_failure)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return _normalization_failure("evaluator_output_not_json")
    normalized = normalize_evaluator_report(payload, expected_module_id=expected_module_id)
    return {
        **normalized,
        "stdout_digest": _digest_bytes(output),
        "stderr_digest": _digest_bytes(error_output),
        "exit_code": completed.returncode,
    }


def _execute_benchmark(
    discovery: Mapping[str, object],
    *,
    expected_module_id: str,
    root: Path,
    timeout_seconds: float,
) -> dict[str, object]:
    if discovery.get("passed") is not True:
        return _benchmark_normalization_failure("benchmark_not_discoverable")
    module_name = cast("str", discovery["entrypoint"])
    invocation = cast("str", discovery["invocation"])
    if invocation == "module":
        command = [sys.executable, "-m", module_name]
    else:
        callable_name = cast("str", discovery["callable"])
        call = (
            f"function({BENCHMARK_SMOKE_ITERATIONS})"
            if invocation == "positional_iterations"
            else f"function(iterations={BENCHMARK_SMOKE_ITERATIONS})"
            if invocation == "keyword_iterations"
            else "function()"
        )
        child = (
            "import dataclasses,importlib,json;"
            f"function=getattr(importlib.import_module({module_name!r}),{callable_name!r});"
            f"value={call};"
            "value=dataclasses.asdict(value) if dataclasses.is_dataclass(value) else "
            "value.model_dump(mode='json') if hasattr(value,'model_dump') else value;"
            "print(json.dumps(value,sort_keys=True,allow_nan=False))"
        )
        command = [sys.executable, "-c", child]
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("COV_CORE_") and not key.startswith("COVERAGE_")
    }
    existing_python_path = environment.get("PYTHONPATH")
    source_path = str((root / "src").resolve())
    environment["PYTHONPATH"] = (
        source_path
        if not existing_python_path
        else f"{source_path}{os.pathsep}{existing_python_path}"
    )
    environment["PYTHONHASHSEED"] = "0"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    process_failure: str | None = None
    completed: subprocess.CompletedProcess[str] | None = None
    try:
        completed = subprocess.run(  # noqa: S603 - fixed interpreter and discovered local module.
            command,
            cwd=root,
            env=environment,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="strict",
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        process_failure = "benchmark_timeout"
    except (OSError, UnicodeError):
        process_failure = "benchmark_process_error"
    if process_failure is not None or completed is None:
        return _benchmark_normalization_failure(process_failure or "benchmark_process_error")
    output = completed.stdout.encode("utf-8")
    error_output = completed.stderr.encode("utf-8")
    validation_failure = (
        "benchmark_output_too_large"
        if len(output) > MAX_BENCHMARK_OUTPUT_BYTES
        or len(error_output) > MAX_BENCHMARK_OUTPUT_BYTES
        else "benchmark_exit_nonzero"
        if completed.returncode != 0
        else None
    )
    if validation_failure is not None:
        return _benchmark_normalization_failure(validation_failure)
    try:
        payload = json.loads(
            completed.stdout,
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, _InvalidEvidenceJsonError):
        return _benchmark_normalization_failure("benchmark_output_not_json")
    normalized = normalize_benchmark_report(payload, expected_module_id=expected_module_id)
    return {
        **normalized,
        "stdout_digest": _digest_bytes(output),
        "stderr_digest": _digest_bytes(error_output),
        "exit_code": completed.returncode,
        "smoke_iterations": discovery.get("smoke_iterations"),
    }


def _validate_evidence(paths: Sequence[Path], *, expected_module_id: str) -> dict[str, object]:
    invalid_json: list[str] = []
    mismatched: list[str] = []
    checked = 0
    for path in paths:
        if path.suffix.lower() != ".json":
            continue
        checked += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            invalid_json.append(path.name)
            continue
        if not isinstance(payload, Mapping):
            invalid_json.append(path.name)
            continue
        declared = {
            normalized
            for key in ("module_id", "moduleId", "module")
            if key in payload
            if (normalized := _normalize_module_id(payload[key])) is not None
        }
        if declared and declared != {expected_module_id}:
            mismatched.append(path.name)
    return {
        "passed": bool(paths) and not invalid_json and not mismatched,
        "file_count": len(paths),
        "checked_json_documents": checked,
        "invalid_json": sorted(invalid_json),
        "module_id_mismatches": sorted(mismatched),
    }


def _normalize_evidence_paths(
    paths: Sequence[Path] | Path | None, *, evidence_kind: str
) -> tuple[Path, ...]:
    if paths is None:
        return ()
    candidates = (paths,) if isinstance(paths, Path) else tuple(paths)
    if not candidates or any(not isinstance(path, Path) for path in candidates):
        raise EvidenceConfigurationError(f"{evidence_kind}-paths")
    resolved = tuple(path.resolve() for path in candidates)
    if len(resolved) != len(set(resolved)):
        raise EvidenceConfigurationError(f"duplicate-{evidence_kind}-path")
    return tuple(sorted(resolved, key=lambda path: path.as_posix()))


def _read_evidence_bytes(
    path: Path, *, media_type: str
) -> tuple[bytes | None, dict[str, object], str | None]:
    document: dict[str, object] = {
        "name": path.name,
        "media_type": media_type,
        "byte_count": None,
        "content_digest": None,
    }
    try:
        size = path.stat().st_size
        if not path.is_file():
            return None, document, "document-not-file"
        if size > MAX_TEST_EVIDENCE_BYTES:
            return None, {**document, "byte_count": size}, "document-too-large"
        content = path.read_bytes()
    except OSError:
        return None, document, "document-unreadable"
    if len(content) > MAX_TEST_EVIDENCE_BYTES:
        return None, {**document, "byte_count": len(content)}, "document-too-large"
    document["byte_count"] = len(content)
    document["content_digest"] = _digest_bytes(content)
    return content, document, None


def _xml_root(content: bytes) -> tuple[Element | None, str | None]:
    lowered = content.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        return None, "xml-doctype-or-entity"
    try:
        return ElementTree.fromstring(content), None
    except (ElementTree.ParseError, DefusedXmlException):
        return None, "xml-malformed"


def _local_tag(element: Element) -> str:
    return element.tag.rsplit("}", maxsplit=1)[-1]


def _module_ids_in_values(values: Iterable[str]) -> frozenset[str]:
    return frozenset(
        _source_id_to_module_id(f"m{match['chapter']}_{match['cell']}")
        for value in values
        for match in _PATH_MODULE_ID.finditer(value)
    )


def _junit_case_outcome(testcase: Element) -> tuple[str | None, str | None]:
    outcomes = [
        _local_tag(child)
        for child in testcase
        if _local_tag(child) in {"failure", "error", "skipped"}
    ]
    if len(outcomes) > 1:
        return None, "testcase-outcome-ambiguous"
    return (outcomes[0] if outcomes else "passed"), None


def _junit_suite_count_failures(root: Element) -> list[str]:
    failures: list[str] = []
    for suite in (element for element in root.iter() if _local_tag(element) == "testsuite"):
        testcases = [child for child in suite if _local_tag(child) == "testcase"]
        counters = {
            "tests": len(testcases),
            "failures": sum(
                any(_local_tag(child) == "failure" for child in testcase) for testcase in testcases
            ),
            "errors": sum(
                any(_local_tag(child) == "error" for child in testcase) for testcase in testcases
            ),
            "skipped": sum(
                any(_local_tag(child) == "skipped" for child in testcase) for testcase in testcases
            ),
        }
        if "tests" not in suite.attrib:
            failures.append("testsuite-tests-missing")
        for name, actual in counters.items():
            if name not in suite.attrib:
                continue
            try:
                declared = int(suite.attrib[name])
            except ValueError:
                failures.append("testsuite-count-invalid")
                continue
            if declared < 0 or declared != actual:
                failures.append("testsuite-count-mismatch")
    return sorted(set(failures))


def _parse_junit_document(
    content: bytes,
    *,
    known_module_ids: frozenset[str],
) -> tuple[list[dict[str, object]], list[str]]:
    root, parse_failure = _xml_root(content)
    if root is None:
        return [], [cast("str", parse_failure)]
    if _local_tag(root) not in {"testsuite", "testsuites"}:
        return [], ["junit-root"]
    testcases = [element for element in root.iter() if _local_tag(element) == "testcase"]
    if not testcases:
        return [], ["junit-no-testcases"]
    records: list[dict[str, object]] = []
    failures = _junit_suite_count_failures(root)
    for testcase in testcases:
        attributes = {key: testcase.attrib.get(key, "") for key in ("file", "classname", "name")}
        if not attributes["name"]:
            failures.append("testcase-name-missing")
            continue
        locator_module_ids = [
            _module_ids_in_values((attributes[key],))
            for key in ("file", "classname")
            if attributes[key]
        ]
        mentioned = frozenset().union(*locator_module_ids)
        unknown = mentioned - known_module_ids
        if unknown:
            failures.append("testcase-unknown-module-id")
        known_locator_sets = [
            module_ids & known_module_ids
            for module_ids in locator_module_ids
            if module_ids & known_module_ids
        ]
        locator_disagreement = bool(
            known_locator_sets
            and any(
                module_ids != known_locator_sets[0]
                for module_ids in known_locator_sets[1:]
            )
        )
        if locator_disagreement:
            failures.append("testcase-module-id-ambiguous")
        owners = mentioned & known_module_ids
        associated = (
            next(iter(owners))
            if not unknown and not locator_disagreement and len(owners) == 1
            else None
        )
        outcome, outcome_failure = _junit_case_outcome(testcase)
        if outcome_failure is not None:
            failures.append(outcome_failure)
        identity = dict(attributes)
        records.append(
            {
                "testcase_id": _digest_bytes(_canonical_bytes(identity)),
                "module_id": associated,
                "outcome": outcome,
            }
        )
    return records, sorted(set(failures))


def _module_junit_result(
    module_id: str,
    records: Sequence[Mapping[str, object]],
    *,
    evidence_failures: Sequence[str],
) -> dict[str, object]:
    associated = [record for record in records if record.get("module_id") == module_id]
    outcomes = Counter(cast("str", record["outcome"]) for record in associated)
    failures: list[str] = []
    if evidence_failures:
        failures.append("test-execution-evidence-invalid")
    if not associated:
        failures.append("test-execution-missing")
    if outcomes["failure"] or outcomes["error"]:
        failures.append("test-execution-failed")
    if associated and not outcomes["passed"]:
        failures.append("test-execution-no-passing-testcase")
    return {
        "requested": True,
        "passed": not failures,
        "testcase_count": len(associated),
        "passed_count": outcomes["passed"],
        "failure_count": outcomes["failure"],
        "error_count": outcomes["error"],
        "skipped_count": outcomes["skipped"],
        "testcase_digest": _digest_bytes(
            _canonical_bytes(sorted(cast("str", record["testcase_id"]) for record in associated))
        ),
        "failures": failures,
    }


def _ingest_junit_evidence(
    paths: Sequence[Path],
    *,
    known_module_ids: frozenset[str],
    selected_module_ids: Sequence[str],
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    if not paths:
        return {
            "profile_id": JUNIT_EVIDENCE_PROFILE_ID,
            "requested": False,
            "passed": None,
            "document_count": 0,
            "documents": [],
            "testcase_count": 0,
            "associated_testcase_count": 0,
            "unassociated_testcase_count": 0,
            "failures": [],
            "evidence_digest": None,
            "maximum_document_bytes": MAX_TEST_EVIDENCE_BYTES,
        }, {}
    documents: list[dict[str, object]] = []
    records: list[dict[str, object]] = []
    failures: list[str] = []
    for path in paths:
        content, document, read_failure = _read_evidence_bytes(
            path, media_type="application/junit+xml"
        )
        documents.append(document)
        if content is None:
            failures.append(cast("str", read_failure))
            continue
        parsed, parse_failures = _parse_junit_document(
            content,
            known_module_ids=known_module_ids,
        )
        records.extend(parsed)
        failures.extend(parse_failures)
    testcase_ids = [cast("str", record["testcase_id"]) for record in records]
    if len(testcase_ids) != len(set(testcase_ids)):
        failures.append("duplicate-testcase-identity")
    failures = sorted(set(failures))
    per_module = {
        module_id: _module_junit_result(
            module_id,
            records,
            evidence_failures=failures,
        )
        for module_id in selected_module_ids
    }
    evidence: dict[str, object] = {
        "profile_id": JUNIT_EVIDENCE_PROFILE_ID,
        "requested": True,
        "passed": not failures and all(result["passed"] is True for result in per_module.values()),
        "document_count": len(paths),
        "documents": sorted(
            documents,
            key=lambda document: (
                cast("str", document["name"]),
                cast("str | None", document["content_digest"]) or "",
            ),
        ),
        "testcase_count": len(records),
        "associated_testcase_count": sum(record["module_id"] is not None for record in records),
        "unassociated_testcase_count": sum(record["module_id"] is None for record in records),
        "failures": failures,
        "maximum_document_bytes": MAX_TEST_EVIDENCE_BYTES,
    }
    evidence["evidence_digest"] = _digest_bytes(_canonical_bytes(evidence))
    return evidence, per_module


def _canonical_coverage_path(value: object, *, root: Path) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("\\", "/")
    candidate = Path(normalized)
    if not candidate.is_absolute():
        candidate = (
            root / "src" / candidate
            if normalized.startswith("glio_proteogen/")
            else root / candidate
        )
    try:
        relative = candidate.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return None
    return relative if relative.startswith("src/glio_proteogen/") else None


def _integer_set(value: object, *, positive: bool) -> set[int] | None:
    if not isinstance(value, list):
        return None
    result: set[int] = set()
    for item in value:
        if type(item) is not int or (item <= 0 if positive else item < 0):
            return None
        result.add(item)
    return result


def _branch_set(value: object) -> set[tuple[int, int]] | None:
    if not isinstance(value, list):
        return None
    result: set[tuple[int, int]] = set()
    for item in value:
        if (
            not isinstance(item, list)
            or len(item) != _BRANCH_ARC_SIZE
            or any(type(number) is not int for number in item)
        ):
            return None
        result.add((cast("int", item[0]), cast("int", item[1])))
    return result


def _coverage_json_file(value: object) -> tuple[dict[str, int] | None, str | None]:
    if not isinstance(value, Mapping):
        return None, "coverage-file-not-object"
    executed_lines = _integer_set(value.get("executed_lines"), positive=True)
    missing_lines = _integer_set(value.get("missing_lines"), positive=True)
    if executed_lines is None or missing_lines is None:
        return None, "coverage-lines-invalid"
    if executed_lines & missing_lines:
        return None, "coverage-lines-overlap"
    executed_branches = _branch_set(value.get("executed_branches", []))
    missing_branches = _branch_set(value.get("missing_branches", []))
    if executed_branches is None or missing_branches is None:
        return None, "coverage-branches-invalid"
    if executed_branches & missing_branches:
        return None, "coverage-branches-overlap"
    return {
        "covered_lines": len(executed_lines),
        "total_lines": len(executed_lines | missing_lines),
        "maximum_line": max(executed_lines | missing_lines, default=0),
        "covered_branches": len(executed_branches),
        "total_branches": len(executed_branches | missing_branches),
    }, None


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _InvalidEvidenceJsonError
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> None:
    raise _InvalidEvidenceJsonError


def _parse_coverage_json(
    content: bytes,
    *,
    root: Path,
) -> tuple[dict[str, dict[str, int]], list[str]]:
    try:
        payload = json.loads(
            content,
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, _InvalidEvidenceJsonError):
        return {}, ["coverage-json-malformed"]
    if not isinstance(payload, Mapping) or not isinstance(payload.get("files"), Mapping):
        return {}, ["coverage-json-shape"]
    records: dict[str, dict[str, int]] = {}
    failures: list[str] = []
    for raw_path, value in cast("Mapping[object, object]", payload["files"]).items():
        path = _canonical_coverage_path(raw_path, root=root)
        if path is None:
            continue
        record, failure = _coverage_json_file(value)
        if failure is not None:
            failures.append(failure)
            continue
        if path in records:
            failures.append("coverage-path-duplicate")
            continue
        records[path] = cast("dict[str, int]", record)
    if not records:
        failures.append("coverage-no-governed-source")
    return records, sorted(set(failures))


_CONDITION_COVERAGE: Final = re.compile(
    r"^\s*\d+(?:\.\d+)?%\s*\((?P<covered>\d+)\s*/\s*(?P<total>\d+)\)\s*$"
)


def _coverage_xml_class(
    class_element: Element,
) -> tuple[dict[str, int] | None, str | None]:
    lines = [element for element in class_element.iter() if _local_tag(element) == "line"]
    if not lines:
        return {
            "covered_lines": 0,
            "total_lines": 0,
            "maximum_line": 0,
            "covered_branches": 0,
            "total_branches": 0,
        }, None
    covered_lines = 0
    covered_branches = 0
    total_branches = 0
    seen_lines: set[int] = set()
    for line in lines:
        try:
            number = int(line.attrib["number"])
            hits = int(line.attrib["hits"])
        except (KeyError, ValueError):
            return None, "coverage-line-invalid"
        if number <= 0 or hits < 0 or number in seen_lines:
            return None, "coverage-line-invalid"
        seen_lines.add(number)
        covered_lines += int(hits > 0)
        if line.attrib.get("branch", "false").lower() == "true":
            match = _CONDITION_COVERAGE.fullmatch(line.attrib.get("condition-coverage", ""))
            if match is None:
                return None, "coverage-condition-invalid"
            covered_branches += int(match["covered"])
            total_branches += int(match["total"])
    if covered_branches > total_branches:
        return None, "coverage-condition-invalid"
    return {
        "covered_lines": covered_lines,
        "total_lines": len(seen_lines),
        "maximum_line": max(seen_lines),
        "covered_branches": covered_branches,
        "total_branches": total_branches,
    }, None


def _parse_coverage_xml(
    content: bytes,
    *,
    root: Path,
) -> tuple[dict[str, dict[str, int]], list[str]]:
    xml_root, parse_failure = _xml_root(content)
    if xml_root is None:
        return {}, [cast("str", parse_failure)]
    if _local_tag(xml_root) != "coverage":
        return {}, ["coverage-xml-root"]
    records: dict[str, dict[str, int]] = {}
    failures: list[str] = []
    classes = [element for element in xml_root.iter() if _local_tag(element) == "class"]
    for class_element in classes:
        path = _canonical_coverage_path(class_element.attrib.get("filename"), root=root)
        if path is None:
            continue
        record, failure = _coverage_xml_class(class_element)
        if failure is not None:
            failures.append(failure)
            continue
        if path in records:
            failures.append("coverage-path-duplicate")
            continue
        records[path] = cast("dict[str, int]", record)
    if not records:
        failures.append("coverage-no-governed-source")
    return records, sorted(set(failures))


def _percentage(covered: int, total: int) -> float:
    return 100.0 if total == 0 else round(covered * 100.0 / total, 6)


def _has_coverable_statements(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return True
    body = list(tree.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return bool(body)


def _expected_coverage_paths(record: Mapping[str, object], *, root: Path) -> list[str]:
    source_paths = (
        *_files_below(cast("Path", record["contract_path"])),
        *_files_below(cast("Path", record["module_path"])),
    )
    return sorted(
        path.relative_to(root).as_posix()
        for path in set(source_paths)
        if path.suffix == ".py" and _has_coverable_statements(path)
    )


def _module_coverage_result(
    record: Mapping[str, object],
    coverage_records: Mapping[str, Mapping[str, int]],
    *,
    root: Path,
    evidence_failures: Sequence[str],
    coverage_thresholds: tuple[float | None, float | None],
) -> dict[str, object]:
    minimum_line_percent, minimum_branch_percent = coverage_thresholds
    expected = _expected_coverage_paths(record, root=root)
    missing = sorted(set(expected) - coverage_records.keys())
    reported_paths = [path for path in expected if path in coverage_records]
    reported = [coverage_records[path] for path in reported_paths]
    invalid_source_files = [
        path
        for path in reported_paths
        if coverage_records[path]["total_lines"] == 0
        or coverage_records[path]["maximum_line"]
        > len((root / path).read_text(encoding="utf-8").splitlines())
    ]
    covered_lines = sum(value["covered_lines"] for value in reported)
    total_lines = sum(value["total_lines"] for value in reported)
    covered_branches = sum(value["covered_branches"] for value in reported)
    total_branches = sum(value["total_branches"] for value in reported)
    line_percent = _percentage(covered_lines, total_lines)
    branch_percent = _percentage(covered_branches, total_branches)
    failures: list[str] = []
    if evidence_failures:
        failures.append("coverage-evidence-invalid")
    if missing:
        failures.append("coverage-source-missing")
    if invalid_source_files:
        failures.append("coverage-source-lines-invalid")
    if minimum_line_percent is not None and line_percent < minimum_line_percent:
        failures.append("line-coverage-below-threshold")
    if minimum_branch_percent is not None and branch_percent < minimum_branch_percent:
        failures.append("branch-coverage-below-threshold")
    return {
        "requested": True,
        "passed": not failures,
        "expected_source_file_count": len(expected),
        "reported_source_file_count": len(reported),
        "missing_source_files": missing,
        "invalid_source_files": invalid_source_files,
        "source_path_digest": _digest_bytes(_canonical_bytes(expected)),
        "line_coverage": {
            "covered": covered_lines,
            "total": total_lines,
            "percent": line_percent,
            "minimum_percent": minimum_line_percent,
        },
        "branch_coverage": {
            "covered": covered_branches,
            "total": total_branches,
            "percent": branch_percent,
            "minimum_percent": minimum_branch_percent,
        },
        "failures": failures,
    }


def _ingest_coverage_evidence(
    paths: Sequence[Path],
    *,
    selected_records: Sequence[Mapping[str, object]],
    root: Path,
    minimum_line_percent: float | None,
    minimum_branch_percent: float | None,
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    if not paths:
        return {
            "profile_id": COVERAGE_EVIDENCE_PROFILE_ID,
            "requested": False,
            "passed": None,
            "document_count": 0,
            "documents": [],
            "reported_source_file_count": 0,
            "failures": [],
            "evidence_digest": None,
            "maximum_document_bytes": MAX_TEST_EVIDENCE_BYTES,
        }, {}
    documents: list[dict[str, object]] = []
    coverage_records: dict[str, dict[str, int]] = {}
    failures: list[str] = []
    for path in paths:
        suffix = path.suffix.lower()
        media_type = "application/json" if suffix == ".json" else "application/xml"
        content, document, read_failure = _read_evidence_bytes(path, media_type=media_type)
        documents.append(document)
        if content is None:
            failures.append(cast("str", read_failure))
            continue
        if suffix == ".json":
            parsed, parse_failures = _parse_coverage_json(content, root=root)
        elif suffix == ".xml":
            parsed, parse_failures = _parse_coverage_xml(content, root=root)
        else:
            parsed, parse_failures = {}, ["coverage-format-unsupported"]
        failures.extend(parse_failures)
        duplicate_paths = set(coverage_records) & parsed.keys()
        if duplicate_paths:
            failures.append("coverage-path-duplicate-across-documents")
        coverage_records.update(
            (path_name, value)
            for path_name, value in parsed.items()
            if path_name not in duplicate_paths
        )
    failures = sorted(set(failures))
    per_module = {
        cast("str", record["module_id"]): _module_coverage_result(
            record,
            coverage_records,
            root=root,
            evidence_failures=failures,
            coverage_thresholds=(minimum_line_percent, minimum_branch_percent),
        )
        for record in selected_records
    }
    evidence: dict[str, object] = {
        "profile_id": COVERAGE_EVIDENCE_PROFILE_ID,
        "requested": True,
        "passed": not failures and all(result["passed"] is True for result in per_module.values()),
        "document_count": len(paths),
        "documents": sorted(
            documents,
            key=lambda document: (
                cast("str", document["name"]),
                cast("str | None", document["content_digest"]) or "",
            ),
        ),
        "reported_source_file_count": len(coverage_records),
        "minimum_line_percent": minimum_line_percent,
        "minimum_branch_percent": minimum_branch_percent,
        "failures": failures,
        "maximum_document_bytes": MAX_TEST_EVIDENCE_BYTES,
    }
    evidence["evidence_digest"] = _digest_bytes(_canonical_bytes(evidence))
    return evidence, per_module


def _validate_coverage_threshold(value: float | None, *, name: str) -> float | None:
    if value is None:
        return None
    if (
        type(value) not in {float, int}
        or not math.isfinite(value)
        or value < 0.0
        or value > _PERCENT_MAX
    ):
        raise EvidenceConfigurationError(f"{name}-threshold")
    return round(float(value), 6)


def _profile_digest(
    *,
    run_evaluators: bool,
    timeout_seconds: float,
    selected_scope_digest: str,
    test_evidence_profile: Mapping[str, object],
    benchmark_profile: Mapping[str, object],
) -> str:
    return _digest_bytes(
        _canonical_bytes(
            {
                "schema_version": SCHEMA_VERSION,
                "profile_id": benchmark_profile["profile_id"],
                "run_evaluators": run_evaluators,
                "evaluator_timeout_seconds": timeout_seconds if run_evaluators else None,
                "maximum_evaluator_output_bytes": MAX_EVALUATOR_OUTPUT_BYTES,
                "selected_scope_digest": selected_scope_digest,
                "test_evidence": test_evidence_profile,
                "benchmark_execution": benchmark_profile,
            }
        )
    )


def _profile_identity(*, run_evaluators: bool, run_benchmarks: bool) -> tuple[str, str]:
    if run_evaluators and run_benchmarks:
        return EVALUATOR_BENCHMARK_PROFILE_ID, "evaluator+benchmark"
    if run_evaluators:
        return EVALUATOR_PROFILE_ID, "evaluator"
    if run_benchmarks:
        return BENCHMARK_PROFILE_ID, "benchmark"
    return STATIC_PROFILE_ID, "static"


def _validated_state(*, run_evaluators: bool, run_benchmarks: bool) -> str:
    if run_evaluators and run_benchmarks:
        return "validated-evaluator-benchmark"
    if run_evaluators:
        return "validated-evaluator"
    if run_benchmarks:
        return "validated-benchmark"
    return "validated-static"


def build_report(  # noqa: PLR0913, PLR0915 - public configuration facade.
    repository_root: Path | None = None,
    *,
    run_evaluators: bool = False,
    evaluator_timeout_seconds: float = DEFAULT_EVALUATOR_TIMEOUT_SECONDS,
    run_benchmarks: bool = False,
    benchmark_timeout_seconds: float = DEFAULT_BENCHMARK_TIMEOUT_SECONDS,
    module_ids: Sequence[str] | None = None,
    shard_index: int | None = None,
    shard_count: int | None = None,
    junit_xml: Sequence[Path] | Path | None = None,
    coverage_reports: Sequence[Path] | Path | None = None,
    minimum_line_coverage_percent: float | None = None,
    minimum_branch_coverage_percent: float | None = None,
) -> dict[str, object]:
    """Build a deterministic static or evaluator-backed module validation report."""

    if not math.isfinite(evaluator_timeout_seconds) or evaluator_timeout_seconds <= 0:
        raise _InvalidTimeoutError
    if (
        type(benchmark_timeout_seconds) not in {float, int}
        or not math.isfinite(benchmark_timeout_seconds)
        or benchmark_timeout_seconds <= 0
    ):
        raise _InvalidBenchmarkTimeoutError
    junit_paths = _normalize_evidence_paths(junit_xml, evidence_kind="junit")
    coverage_paths = _normalize_evidence_paths(coverage_reports, evidence_kind="coverage")
    minimum_line_percent = _validate_coverage_threshold(
        minimum_line_coverage_percent,
        name="line-coverage",
    )
    minimum_branch_percent = _validate_coverage_threshold(
        minimum_branch_coverage_percent,
        name="branch-coverage",
    )
    if (
        minimum_line_percent is not None or minimum_branch_percent is not None
    ) and not coverage_paths:
        raise EvidenceConfigurationError("coverage-threshold-without-report")
    discovery = discover_repository(repository_root)
    root = cast("Path", discovery["root"])
    duplicate_ids = cast("dict[str, list[str]]", discovery["duplicate_module_ids"])
    orphan_contracts = cast("list[str]", discovery["orphan_contracts"])
    orphan_modules = cast("list[str]", discovery["orphan_modules"])
    missing_roots = cast("list[str]", discovery["missing_roots"])
    all_records = cast("list[dict[str, object]]", discovery["modules"])
    selected_records, scope = _select_module_records(
        all_records,
        module_ids=module_ids,
        shard_index=shard_index,
        shard_count=shard_count,
    )
    selected_ids = cast("list[str]", scope["selected_module_ids"])
    known_ids = frozenset(cast("str", record["module_id"]) for record in all_records)
    junit_evidence, junit_by_module = _ingest_junit_evidence(
        junit_paths,
        known_module_ids=known_ids,
        selected_module_ids=selected_ids,
    )
    coverage_evidence, coverage_by_module = _ingest_coverage_evidence(
        coverage_paths,
        selected_records=selected_records,
        root=root,
        minimum_line_percent=minimum_line_percent,
        minimum_branch_percent=minimum_branch_percent,
    )
    module_reports: list[dict[str, object]] = []
    with _repository_import_path(root):
        for record in selected_records:
            source_id = cast("str", record["source_id"])
            module_id = cast("str", record["module_id"])
            benchmark_paths = cast("tuple[Path, ...]", record["benchmark_paths"])
            contract = _validate_contract(source_id)
            implementation = _validate_implementation(record, root=root)
            evaluator = _discover_evaluator(
                source_id,
                cast("tuple[Path, ...]", record["evaluator_paths"]),
                root=root,
            )
            evaluator_execution: dict[str, object] | None = None
            if run_evaluators:
                evaluator_execution = _execute_evaluator(
                    evaluator,
                    expected_module_id=module_id,
                    root=root,
                    timeout_seconds=evaluator_timeout_seconds,
                )
            benchmark_runner = _discover_benchmark(
                source_id,
                benchmark_paths,
                root=root,
            )
            benchmark_execution: dict[str, object] | None = None
            if run_benchmarks:
                benchmark_execution = _execute_benchmark(
                    benchmark_runner,
                    expected_module_id=module_id,
                    root=root,
                    timeout_seconds=benchmark_timeout_seconds,
                )
            test_paths = cast("tuple[Path, ...]", record["test_paths"])
            evidence_paths = cast("tuple[Path, ...]", record["evidence_paths"])
            tests = {
                "passed": bool(test_paths),
                "file_count": len(test_paths),
                "path_digest": _digest_bytes(
                    "\n".join(_relative(test_paths, root=root)).encode("utf-8")
                ),
                "content_digest": _content_digest(test_paths, root=root),
                "suites": sorted(
                    {path.relative_to(root / "tests").parts[0] for path in test_paths}
                ),
                "execution": junit_by_module.get(
                    module_id,
                    {
                        "requested": False,
                        "passed": None,
                        "testcase_count": 0,
                        "failures": [],
                    },
                ),
            }
            benchmarks = {
                "passed": bool(benchmark_paths),
                "file_count": len(benchmark_paths),
                "paths": _relative(benchmark_paths, root=root),
                "content_digest": _content_digest(benchmark_paths, root=root),
                "runner": benchmark_runner,
                "execution": benchmark_execution,
            }
            evidence = {
                **_validate_evidence(evidence_paths, expected_module_id=module_id),
                "paths": _relative(evidence_paths, root=root),
                "content_digest": _content_digest(evidence_paths, root=root),
            }
            contract_path = cast("Path", record["contract_path"])
            module_path = cast("Path", record["module_path"])
            source_paths = (
                *_files_below(contract_path),
                *_files_below(module_path),
                *cast("tuple[Path, ...]", record["evaluator_paths"]),
                *benchmark_paths,
                *test_paths,
                *evidence_paths,
            )
            static_pass = all(
                section.get("passed") is True
                for section in (
                    contract,
                    implementation,
                    evaluator,
                    tests,
                    benchmarks,
                    evidence,
                )
            )
            evaluator_pass = not run_evaluators or (
                evaluator_execution is not None and evaluator_execution.get("passed") is True
            )
            benchmark_pass = not run_benchmarks or (
                benchmark_execution is not None and benchmark_execution.get("passed") is True
            )
            test_execution = cast("Mapping[str, object]", tests["execution"])
            test_execution_pass = (
                test_execution["passed"] is True if test_execution["requested"] is True else True
            )
            coverage = coverage_by_module.get(
                module_id,
                {
                    "requested": False,
                    "passed": None,
                    "failures": [],
                },
            )
            coverage_pass = coverage["passed"] is True if coverage["requested"] is True else True
            passed = (
                static_pass
                and evaluator_pass
                and benchmark_pass
                and test_execution_pass
                and coverage_pass
            )
            failures = _module_failure_codes(
                {
                    "contract": contract,
                    "implementation": implementation,
                    "evaluator": evaluator,
                    "tests": tests,
                    "benchmarks": benchmarks,
                    "evidence": evidence,
                },
                execution_sections={
                    "evaluator": evaluator_execution,
                    "benchmark_runner": benchmark_runner
                    if benchmark_execution is not None
                    else None,
                    "benchmark": benchmark_execution,
                    "test_execution": (
                        test_execution if test_execution.get("requested") is True else None
                    ),
                    "coverage": coverage if coverage.get("requested") is True else None,
                },
            )
            versions = cast("list[str]", contract.get("versions", []))
            version = versions[0] if len(versions) == 1 else None
            module_reports.append(
                {
                    "module_id": module_id,
                    "source_id": source_id,
                    "contract_version": version,
                    "maturity": (
                        "provisional"
                        if isinstance(version, str) and "provisional" in version
                        else "governed"
                    ),
                    "paths": {
                        "contract": contract_path.relative_to(root).as_posix(),
                        "module": module_path.relative_to(root).as_posix(),
                    },
                    "source_digest": _content_digest(source_paths, root=root),
                    "contract": contract,
                    "implementation": implementation,
                    "evaluator": {
                        **evaluator,
                        "execution": evaluator_execution,
                    },
                    "tests": tests,
                    "benchmarks": benchmarks,
                    "evidence": evidence,
                    "coverage": coverage,
                    "validation_basis": [
                        "static-closure",
                        *(["evaluator-execution"] if run_evaluators else []),
                        *(["benchmark-execution"] if run_benchmarks else []),
                        *(["pytest-junit"] if junit_paths else []),
                        *(["governed-source-coverage"] if coverage_paths else []),
                    ],
                    "state": (
                        _validated_state(
                            run_evaluators=run_evaluators,
                            run_benchmarks=run_benchmarks,
                        )
                        if passed
                        else "failed"
                    ),
                    "failure_codes": failures,
                }
            )

    discovery_failures = bool(
        duplicate_ids or orphan_contracts or orphan_modules or missing_roots or not module_reports
    )
    states = Counter(cast("str", module["state"]) for module in module_reports)
    external_evidence_valid = all(
        evidence["passed"] is not False for evidence in (junit_evidence, coverage_evidence)
    )
    valid = (
        not discovery_failures
        and external_evidence_valid
        and all(module["state"] != "failed" for module in module_reports)
    )
    profile_id, mode = _profile_identity(
        run_evaluators=run_evaluators,
        run_benchmarks=run_benchmarks,
    )
    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "profile_id": profile_id,
        "profile_digest": _profile_digest(
            run_evaluators=run_evaluators,
            timeout_seconds=evaluator_timeout_seconds,
            selected_scope_digest=cast("str", scope["selected_scope_digest"]),
            test_evidence_profile={
                "junit_evidence_required": bool(junit_paths),
                "junit_evidence_profile_id": (JUNIT_EVIDENCE_PROFILE_ID if junit_paths else None),
                "coverage_evidence_required": bool(coverage_paths),
                "coverage_evidence_profile_id": (
                    COVERAGE_EVIDENCE_PROFILE_ID if coverage_paths else None
                ),
                "minimum_line_coverage_percent": minimum_line_percent,
                "minimum_branch_coverage_percent": minimum_branch_percent,
            },
            benchmark_profile={
                "profile_id": profile_id,
                "benchmark_profile_id": BENCHMARK_PROFILE_ID,
                "run_benchmarks": run_benchmarks,
                "benchmark_timeout_seconds": (
                    benchmark_timeout_seconds if run_benchmarks else None
                ),
                "smoke_iterations": BENCHMARK_SMOKE_ITERATIONS if run_benchmarks else None,
                "maximum_output_bytes": MAX_BENCHMARK_OUTPUT_BYTES,
                "callable_priority": list(_BENCHMARK_CALLABLES),
                "module_identity_fields": ["module_id", "moduleId", "module"],
                "requires_explicit_pass_evidence": True,
                "requires_positive_finite_budget_evidence": True,
            },
        ),
        "mode": mode,
        "scope": scope,
        "discovery": {
            "contract_count": len(cast("list[str]", discovery["contract_ids"])),
            "module_count": len(cast("list[str]", discovery["module_ids"])),
            "closed_module_count": len(all_records),
            "module_ids": [record["module_id"] for record in all_records],
            "duplicate_module_ids": duplicate_ids,
            "orphan_contracts": orphan_contracts,
            "orphan_modules": orphan_modules,
            "missing_roots": missing_roots,
        },
        "summary": {
            "valid": valid,
            "validated_static": states["validated-static"],
            "validated_evaluator": states["validated-evaluator"],
            "validated_benchmark": states["validated-benchmark"],
            "validated_evaluator_benchmark": states["validated-evaluator-benchmark"],
            "failed": states["failed"],
            "governed": sum(module["maturity"] == "governed" for module in module_reports),
            "provisional": sum(module["maturity"] == "provisional" for module in module_reports),
        },
        "test_evidence": {
            "junit": junit_evidence,
            "coverage": coverage_evidence,
        },
        "modules": module_reports,
        "limitations": [
            "Static validation proves source closure and contract/interface integrity; "
            "it does not execute module algorithms.",
            "Evaluator validation is engineering evidence over synthetic fixtures, "
            "not scientific, clinical, or regulatory validation.",
            "Benchmark execution uses a bounded smoke iteration count when an explicit "
            "iterations parameter is safely discoverable; it is not a release-scale load test.",
            "Benchmark acceptance requires self-reported module identity, budget values, "
            "and pass booleans; the verifier does not independently reproduce timing arithmetic.",
            "Passing validation never promotes a provisional contract or expands a "
            "module's governed ownership boundary.",
            "Associated historical evidence is checked for parse and identity coherence "
            "but is not treated as external release authority.",
            "JUnit association requires exactly one unambiguous module identifier in stable "
            "pytest testcase file or classname metadata; testcase names and shared multi-module "
            "locations are non-authoritative.",
            "JUnit evidence requires at least one non-skipped passing testcase per selected "
            "module; it does not prove every statically associated test file was collected.",
            "Coverage evidence binds reported executable lines and branches to discovered "
            "contract and implementation source files; it does not prove test quality.",
            "Coverage percentages become acceptance gates only when explicit line or branch "
            "thresholds are configured.",
            "Evidence content digests bind artifact bytes but do not authenticate the test "
            "runner or artifact producer.",
        ],
    }
    report["repository_content_digest"] = _digest_bytes(
        _canonical_bytes(
            {
                "modules": [
                    {
                        "module_id": module["module_id"],
                        "source_digest": module["source_digest"],
                    }
                    for module in module_reports
                ],
                "discovery": report["discovery"],
            }
        )
    )
    report["validation_digest"] = _digest_bytes(_canonical_bytes(report))
    return report


def _module_failure_codes(
    sections: Mapping[str, Mapping[str, object]],
    *,
    execution_sections: Mapping[str, Mapping[str, object] | None],
) -> list[str]:
    failures: list[str] = []
    for prefix in ("contract", "implementation", "evaluator"):
        section = sections[prefix]
        failures.extend(
            f"{prefix}:{failure}" for failure in cast("Sequence[str]", section.get("failures", ()))
        )
    for name in ("tests", "benchmarks", "evidence"):
        section = sections[name]
        if section.get("passed") is not True:
            failures.append(f"{name}:closure")
    prefixes = {
        "evaluator": "evaluator_execution",
        "benchmark_runner": "benchmark_runner",
        "benchmark": "benchmark_execution",
        "test_execution": "test_execution",
        "coverage": "coverage",
    }
    for name, execution in execution_sections.items():
        if execution is None:
            continue
        failures.extend(
            f"{prefixes[name]}:{failure}"
            for failure in cast("Sequence[str]", execution.get("failures", ()))
        )
    return sorted(set(failures))


def verify(  # noqa: PLR0913 - mirrors the public report-builder facade.
    repository_root: Path | None = None,
    *,
    run_evaluators: bool = False,
    evaluator_timeout_seconds: float = DEFAULT_EVALUATOR_TIMEOUT_SECONDS,
    run_benchmarks: bool = False,
    benchmark_timeout_seconds: float = DEFAULT_BENCHMARK_TIMEOUT_SECONDS,
    module_ids: Sequence[str] | None = None,
    shard_index: int | None = None,
    shard_count: int | None = None,
    junit_xml: Sequence[Path] | Path | None = None,
    coverage_reports: Sequence[Path] | Path | None = None,
    minimum_line_coverage_percent: float | None = None,
    minimum_branch_coverage_percent: float | None = None,
) -> dict[str, object]:
    """Return a report or raise when any required closure gate fails."""

    report = build_report(
        repository_root,
        run_evaluators=run_evaluators,
        evaluator_timeout_seconds=evaluator_timeout_seconds,
        run_benchmarks=run_benchmarks,
        benchmark_timeout_seconds=benchmark_timeout_seconds,
        module_ids=module_ids,
        shard_index=shard_index,
        shard_count=shard_count,
        junit_xml=junit_xml,
        coverage_reports=coverage_reports,
        minimum_line_coverage_percent=minimum_line_coverage_percent,
        minimum_branch_coverage_percent=minimum_branch_coverage_percent,
    )
    summary = cast("dict[str, object]", report["summary"])
    if summary["valid"] is not True:
        raise ModuleValidationError(cast("int", summary["failed"]))
    return report


def render_markdown(report: Mapping[str, object]) -> str:
    """Render a deterministic human-readable projection of a validation report."""

    discovery = cast("Mapping[str, object]", report["discovery"])
    scope = cast("Mapping[str, object]", report["scope"])
    summary = cast("Mapping[str, object]", report["summary"])
    test_evidence = cast("Mapping[str, Mapping[str, object]]", report["test_evidence"])
    modules = cast("Sequence[Mapping[str, object]]", report["modules"])
    lines = [
        "# GLIO-PROTEOGEN module validation",
        "",
        f"- Schema: `{report['schema_version']}`",
        f"- Profile: `{report['profile_id']}`",
        f"- Mode: `{report['mode']}`",
        f"- Closed modules discovered: {discovery['closed_module_count']}",
        f"- Modules selected: {scope['selected_module_count']}",
        f"- Scope: `{scope['mode']}`",
        f"- Scope digest: `{scope['selected_scope_digest']}`",
        f"- Valid: `{str(summary['valid']).lower()}`",
        f"- Validation digest: `{report['validation_digest']}`",
        "",
        "| Module | Version | Schemas | Tests | Benchmarks | Evidence | State |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for module in modules:
        contract = cast("Mapping[str, object]", module["contract"])
        tests = cast("Mapping[str, object]", module["tests"])
        benchmarks = cast("Mapping[str, object]", module["benchmarks"])
        evidence = cast("Mapping[str, object]", module["evidence"])
        lines.append(
            "| "
            f"{module['module_id']} | {module['contract_version'] or 'unknown'} | "
            f"{contract['schema_count']} | {tests['file_count']} | "
            f"{benchmarks['file_count']} | {evidence['file_count']} | "
            f"{module['state']} |"
        )
    discovery_issues = [
        f"duplicate module directories: {discovery['duplicate_module_ids']}",
        f"orphan contracts: {discovery['orphan_contracts']}",
        f"orphan modules: {discovery['orphan_modules']}",
        f"missing roots: {discovery['missing_roots']}",
    ]
    discovery_issues = [issue for issue in discovery_issues if not issue.endswith(("{}", "[]"))]
    if discovery_issues:
        lines.extend(("", "## Discovery failures", ""))
        lines.extend(f"- {issue}" for issue in discovery_issues)
    failed = [module for module in modules if module["state"] == "failed"]
    if failed:
        lines.extend(("", "## Failures", ""))
        for module in failed:
            failure_codes = ", ".join(cast("Sequence[str]", module["failure_codes"]))
            lines.append(f"- `{module['module_id']}`: {failure_codes}")
    requested_evidence = [
        (name, evidence)
        for name, evidence in test_evidence.items()
        if evidence["requested"] is True
    ]
    if requested_evidence:
        lines.extend(("", "## Test evidence", ""))
        for name, evidence in requested_evidence:
            lines.append(
                f"- `{name}`: passed=`{str(evidence['passed']).lower()}`, "
                f"digest=`{evidence['evidence_digest']}`"
            )
    lines.extend(("", "## Limitations", ""))
    lines.extend(f"- {limitation}" for limitation in cast("Sequence[str]", report["limitations"]))
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=_REPOSITORY_ROOT)
    parser.add_argument("--run-evaluators", action="store_true")
    parser.add_argument(
        "--evaluator-timeout-seconds",
        type=float,
        default=DEFAULT_EVALUATOR_TIMEOUT_SECONDS,
    )
    parser.add_argument("--run-benchmarks", action="store_true")
    parser.add_argument(
        "--benchmark-timeout-seconds",
        type=float,
        default=DEFAULT_BENCHMARK_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--module",
        dest="module_ids",
        action="append",
        help="select one module ID; repeat for multiple modules",
    )
    parser.add_argument("--shard-index", type=int, help="zero-based shard index")
    parser.add_argument("--shard-count", type=int, help="total round-robin shard count")
    parser.add_argument(
        "--junit-xml",
        type=Path,
        action="append",
        help="pytest JUnit XML evidence; repeat for disjoint reports",
    )
    parser.add_argument(
        "--coverage-report",
        type=Path,
        action="append",
        help="coverage.py JSON or Cobertura XML evidence; repeat for disjoint reports",
    )
    parser.add_argument("--minimum-line-coverage-percent", type=float)
    parser.add_argument("--minimum-branch-coverage-percent", type=float)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    try:
        report = build_report(
            arguments.repository_root,
            run_evaluators=arguments.run_evaluators,
            evaluator_timeout_seconds=arguments.evaluator_timeout_seconds,
            run_benchmarks=arguments.run_benchmarks,
            benchmark_timeout_seconds=arguments.benchmark_timeout_seconds,
            module_ids=arguments.module_ids,
            shard_index=arguments.shard_index,
            shard_count=arguments.shard_count,
            junit_xml=arguments.junit_xml,
            coverage_reports=arguments.coverage_report,
            minimum_line_coverage_percent=arguments.minimum_line_coverage_percent,
            minimum_branch_coverage_percent=arguments.minimum_branch_coverage_percent,
        )
    except (
        EvidenceConfigurationError,
        ModuleScopeError,
        _InvalidBenchmarkTimeoutError,
        _InvalidTimeoutError,
    ) as error:
        parser.error(str(error))
    rendered = (
        render_markdown(report)
        if arguments.format == "markdown"
        else json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0 if cast("Mapping[str, object]", report["summary"])["valid"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BENCHMARK_PROFILE_ID",
    "BENCHMARK_SMOKE_ITERATIONS",
    "COVERAGE_EVIDENCE_PROFILE_ID",
    "DEFAULT_BENCHMARK_TIMEOUT_SECONDS",
    "DEFAULT_EVALUATOR_TIMEOUT_SECONDS",
    "EVALUATOR_BENCHMARK_PROFILE_ID",
    "EVALUATOR_PROFILE_ID",
    "JUNIT_EVIDENCE_PROFILE_ID",
    "MAX_BENCHMARK_OUTPUT_BYTES",
    "MAX_EVALUATOR_OUTPUT_BYTES",
    "MAX_TEST_EVIDENCE_BYTES",
    "SCHEMA_VERSION",
    "SHARD_ALGORITHM",
    "STATIC_PROFILE_ID",
    "EvidenceConfigurationError",
    "ModuleScopeError",
    "ModuleValidationError",
    "build_report",
    "discover_repository",
    "main",
    "normalize_benchmark_report",
    "normalize_evaluator_report",
    "render_markdown",
    "verify",
]
