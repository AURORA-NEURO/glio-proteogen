"""Replay the locked M01-03 ingestion corpus and emit machine-readable evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, NotRequired, TypedDict, cast

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_03_raw_ingestion import (
    IngestionLimits,
    parse_raw_input,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m01_03 import ValidatedRawInputDescriptor

MODULE_ID = "GLIO-PROTEOGEN-M01-03"
ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "m01_03"
SCENARIO_PATH = FIXTURE_ROOT / "scenarios.json"


class FixtureRecord(TypedDict):
    bytes: int
    sha256: str


class ExpectedResult(TypedDict):
    status: str
    format: str | None
    version: str | None
    compression: str | None
    decoded_size_bytes: int
    record_count: int
    diagnostic_codes: list[str]


class Scenario(TypedDict):
    case_id: str
    fixture: str
    filename: NotRequired[str]
    expected_sha256: NotRequired[str]
    expected: ExpectedResult


class Corpus(TypedDict):
    module_id: str
    schema_version: str
    data_classification: str
    fixtures: dict[str, FixtureRecord]
    scenarios: list[Scenario]


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _corpus() -> Corpus:
    return cast("Corpus", strict_json_loads(SCENARIO_PATH.read_bytes()))


def _fixture_checks(corpus: Corpus) -> list[EvalCheck]:
    checks: list[EvalCheck] = []
    for filename, locked in sorted(corpus["fixtures"].items()):
        path = FIXTURE_ROOT / filename
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        checks.append(
            EvalCheck(
                name=f"fixture.{filename}",
                passed=len(payload) == locked["bytes"] and digest == locked["sha256"],
                detail=f"bytes={len(payload)};sha256={digest}",
            )
        )
    return checks


def _result_matches(
    result: ValidatedRawInputDescriptor,
    expected: ExpectedResult,
    fixture: FixtureRecord,
) -> bool:
    detected = result.detected
    return (
        result.disposition.value == expected["status"]
        and (detected.format.value if detected else None) == expected["format"]
        and (detected.version if detected else None) == expected["version"]
        and (detected.compression.value if detected else None) == expected["compression"]
        and result.source_digest == f"sha256:{fixture['sha256']}"
        and result.source_size_bytes == fixture["bytes"]
        and result.decoded_size_bytes == expected["decoded_size_bytes"]
        and result.record_count == expected["record_count"]
        and [diagnostic.code for diagnostic in result.diagnostics]
        == expected["diagnostic_codes"]
        and result.checksum_verified == ("checksum_mismatch" not in expected["diagnostic_codes"])
        and result.structural_validation_passed == (expected["status"] == "accepted")
    )


def _scenario_checks(corpus: Corpus) -> tuple[list[EvalCheck], list[dict[str, object]]]:
    checks: list[EvalCheck] = []
    serialized_results: list[dict[str, object]] = []
    for scenario in corpus["scenarios"]:
        fixture = corpus["fixtures"][scenario["fixture"]]
        path = FIXTURE_ROOT / scenario["fixture"]
        payload = path.read_bytes()
        filename = scenario.get("filename", path.name)
        keywords = {
            "source_id": f"source.synthetic.{scenario['case_id']}",
            "filename": filename,
            "expected_sha256": scenario.get("expected_sha256", fixture["sha256"]),
        }
        direct = parse_raw_input(payload, **keywords)
        streamed = parse_raw_input(BytesIO(payload), **keywords)
        expected = scenario["expected"]
        exact = direct == streamed and _result_matches(direct, expected, fixture)
        codes = ",".join(diagnostic.code for diagnostic in direct.diagnostics) or "none"
        checks.append(
            EvalCheck(
                name=f"scenario.{scenario['case_id']}",
                passed=exact,
                detail=(
                    f"disposition={direct.disposition.value};"
                    f"format={direct.detected.format.value if direct.detected else 'none'};"
                    f"records={direct.record_count};diagnostics={codes};"
                    f"stream_equal={direct == streamed}"
                ),
            )
        )
        serialized_results.append(cast("dict[str, object]", direct.model_dump(mode="json")))
    return checks, serialized_results


def _resource_checks() -> list[EvalCheck]:
    plain = (FIXTURE_ROOT / "proteins.valid.fasta").read_bytes()
    compressed = (FIXTURE_ROOT / "proteins.valid.fasta.gz").read_bytes()
    raw_limited = parse_raw_input(
        plain,
        source_id="source.synthetic.raw-limit",
        limits=IngestionLimits(max_source_bytes=len(plain) - 1),
    )
    decoded_limited = parse_raw_input(
        compressed,
        source_id="source.synthetic.decoded-limit",
        limits=IngestionLimits(max_decoded_bytes=len(plain) - 1),
    )
    return [
        EvalCheck(
            "resource.raw_first_excess",
            raw_limited.disposition.value == "rejected"
            and [item.code for item in raw_limited.diagnostics]
            == ["raw_size_limit_exceeded"],
            f"bytes={len(plain)};limit={len(plain) - 1}",
        ),
        EvalCheck(
            "resource.decoded_first_excess",
            decoded_limited.disposition.value == "rejected"
            and [item.code for item in decoded_limited.diagnostics]
            == ["decompressed_size_limit_exceeded"],
            f"decoded_bytes={len(plain)};limit={len(plain) - 1}",
        ),
    ]


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


def _privacy_check(results: list[dict[str, object]]) -> EvalCheck:
    forbidden_keys = {
        "alleles",
        "attributes",
        "genotype",
        "intensities",
        "raw_bytes",
        "raw_content",
        "rows",
        "sequences",
        "spectra",
        "treatment_recommendation",
    }
    canaries = {"SYNTHETIC_SAMPLE", "synthetic_gene", "synthetic_protein_1", "PEPTIDE"}
    keys = _all_keys(results)
    rendered = canonical_json_bytes(results).decode("utf-8")
    leaked_keys = sorted(keys.intersection(forbidden_keys))
    leaked_values = sorted(value for value in canaries if value in rendered)
    passed = not leaked_keys and not leaked_values
    return EvalCheck(
        "privacy.metadata_only_results",
        passed,
        (
            "no raw scientific payload or prohibited output"
            if passed
            else (
                f"keys={','.join(leaked_keys) or 'none'};"
                f"values={','.join(leaked_values) or 'none'}"
            )
        ),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    corpus = _corpus()
    fixture_checks = _fixture_checks(corpus)
    scenario_checks, results = _scenario_checks(corpus)
    checks = [*fixture_checks, *scenario_checks, *_resource_checks(), _privacy_check(results)]
    passed = (
        corpus["module_id"] == MODULE_ID
        and corpus["data_classification"] == "synthetic_nonclinical"
        and all(check.passed for check in checks)
    )
    report = {
        "module_id": MODULE_ID,
        "passed": passed,
        "fixture_count": len(corpus["fixtures"]),
        "scenario_count": len(corpus["scenarios"]),
        "checks": [asdict(check) for check in checks],
    }
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(serialized)
    else:
        args.output.write_text(serialized, encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
