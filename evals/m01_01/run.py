"""Run the M01-01 evidence gate and emit one machine-readable report."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from dataclasses import asdict, dataclass
from importlib.resources import files
from pathlib import Path
from statistics import fmean, median
from time import perf_counter_ns
from typing import NotRequired, TypedDict, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import TypeAdapter, ValidationError
from tests.m01_01_support import load_case, load_manifest, load_protocol_schema, load_request

from glio_proteogen.contracts.m01_01.canonical import (
    canonical_request_digest,
    identity_binding_digest,
    metadata_document_digest,
    protocol_digest,
)
from glio_proteogen.contracts.m01_01.schema import ContractName, contract_json_schema
from glio_proteogen.contracts.m01_01.v1 import (
    ConformanceDecision,
    EvaluateMetadataRequest,
    M0101Output,
    M0101Request,
    MetadataDocument,
    ObservedValue,
    ProtocolSchema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.kernel.strict_json import JsonValue, StrictJsonError, strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata import (
    validate_metadata,
    validate_protocol_schema,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.quality_consensus import (
    OWNED_QUALITY_CORPUS_DIGEST,
    OWNED_QUALITY_MODEL_DIGEST,
    ConsensusStatus,
    QualityConsensusArtifactError,
    assess_quality_consensus,
    load_packaged_quality_consensus,
)

MODULE_ID = "GLIO-PROTEOGEN-M01-01"
MEAN_BUDGET_NS = 5_000_000
P95_BUDGET_NS = 10_000_000
SCALAR_TEXT_LIMIT = 65_536
DOMAIN_PROFILE_PACKAGE = "glio_proteogen.profiles.m01_01.v1"
QUALITY_FEATURE_COUNT = 18
QUALITY_VIEW_COUNT = 3
QUALITY_PROFILE_COUNT = 12
PUBLIC_SCHEMA_NAMES: tuple[ContractName, ...] = (
    "request",
    "output",
    "register-request",
    "evaluate-request",
    "protocol-schema",
    "metadata-document",
    "protocol-receipt",
    "conformance-profile",
)


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class LatencySummary:
    iterations: int
    mean_ns: float
    p50_ns: float
    p95_ns: int
    maximum_ns: int
    mean_budget_ns: int = MEAN_BUDGET_NS
    p95_budget_ns: int = P95_BUDGET_NS


class FixtureCase(TypedDict):
    case_id: str
    file: str
    target: str
    expected: str
    phase: str
    invariant: str
    expected_decision: str
    expected_issue_codes: list[str]


class DomainEntry(TypedDict):
    path: str
    values: list[dict[str, JsonValue]]


class DomainDocument(TypedDict):
    document_id: str
    schema_id: str
    schema_version: str
    assay_version: str
    specimen_version: str
    entries: list[DomainEntry]


class DomainCase(TypedDict):
    case_id: str
    description: str
    replace_entries: list[DomainEntry]
    remove_paths: list[str]
    add_entries: list[DomainEntry]
    expected_identity_binding_digest: NotRequired[str]
    expected_decision: str
    expected_human_review: bool
    expected_issue_codes: list[str]


class DomainCorpus(TypedDict):
    corpus_id: str
    corpus_version: str
    description: str
    base_document: DomainDocument
    cases: list[DomainCase]


class _DomainCorpusError(ValueError):
    def __init__(self) -> None:
        super().__init__("domain corpus addition duplicates an existing path")


def _fixture_checks() -> list[EvalCheck]:
    return [_run_fixture(case) for case in load_manifest()["cases"]]


def _domain_asset_bytes(name: str) -> bytes:
    return files(DOMAIN_PROFILE_PACKAGE).joinpath(name).read_bytes()


def _domain_schema() -> ProtocolSchema:
    return TypeAdapter(ProtocolSchema).validate_json(_domain_asset_bytes("protocol-schema.json"))


def _domain_corpus() -> DomainCorpus:
    return cast(
        "DomainCorpus",
        strict_json_loads(_domain_asset_bytes("conformance-corpus.json")),
    )


def _domain_document(corpus: DomainCorpus, case: DomainCase) -> MetadataDocument:
    document = deepcopy(corpus["base_document"])
    entries = {entry["path"]: entry for entry in document["entries"]}
    for path in case["remove_paths"]:
        entries.pop(path)
    for entry in case["replace_entries"]:
        entries[entry["path"]] = entry
    for entry in case["add_entries"]:
        if entry["path"] in entries:
            raise _DomainCorpusError
        entries[entry["path"]] = entry
    document["entries"] = list(entries.values())
    return TypeAdapter(MetadataDocument).validate_json(canonical_json_bytes(document))


def _domain_profile_checks() -> list[EvalCheck]:
    schema = _domain_schema()
    corpus = _domain_corpus()
    schema_report = validate_protocol_schema(schema)
    checks = [
        EvalCheck(
            name="domain.profile_schema",
            passed=(
                schema_report.decision is ConformanceDecision.CONFORMANT
                and not schema_report.issues
            ),
            detail=(
                f"schema={schema.schema_id}@{schema.version};"
                f"fields={len(schema.fields)};rules={len(schema.compatibility_rules)}"
            ),
        )
    ]
    checks.extend(_run_domain_case(schema, corpus, case) for case in corpus["cases"])
    return checks


def _run_domain_case(
    schema: ProtocolSchema,
    corpus: DomainCorpus,
    case: DomainCase,
) -> EvalCheck:
    try:
        document = _domain_document(corpus, case)
    except (ValidationError, ValueError) as error:
        return EvalCheck(
            name=f"domain.{case['case_id']}",
            passed=False,
            detail=f"fixture_error={type(error).__name__}",
        )
    expected_binding = case.get(
        "expected_identity_binding_digest",
        identity_binding_digest(schema, document),
    )
    report = validate_metadata(
        schema,
        document,
        consent_state=ConsentState.GRANTED,
        expected_identity_binding_digest=expected_binding,
    )
    actual_codes = sorted({issue.code for issue in report.issues})
    expected_codes = sorted(case["expected_issue_codes"])
    passed = (
        report.decision.value == case["expected_decision"]
        and report.human_review_required is case["expected_human_review"]
        and actual_codes == expected_codes
    )
    detail = (
        f"decision={report.decision.value};"
        f"review={str(report.human_review_required).lower()};"
        f"issues={','.join(actual_codes) or 'none'}"
    )
    return EvalCheck(name=f"domain.{case['case_id']}", passed=passed, detail=detail)


def _replace_domain_observed(
    document: MetadataDocument,
    path: str,
    value: str | float,
) -> MetadataDocument:
    entries = []
    for entry in document.entries:
        if entry.path != path:
            entries.append(entry)
            continue
        current = entry.values[0]
        if not isinstance(current, ObservedValue):
            raise TypeError
        entries.append(
            entry.model_copy(
                update={"values": (ObservedValue(value=value, unit=current.unit),)}
            )
        )
    return document.model_copy(update={"entries": tuple(entries)})


def _quality_consensus_checks() -> list[EvalCheck]:
    schema = _domain_schema()
    corpus = _domain_corpus()
    document = TypeAdapter(MetadataDocument).validate_json(
        canonical_json_bytes(corpus["base_document"]),
        strict=True,
    )
    try:
        loaded = load_packaged_quality_consensus()
    except QualityConsensusArtifactError as error:
        return [
            EvalCheck(
                name="quality.artifacts",
                passed=False,
                detail=type(error).__name__,
            )
        ]

    artifact_check = EvalCheck(
        name="quality.artifacts",
        passed=(
            loaded.model_digest == OWNED_QUALITY_MODEL_DIGEST
            and loaded.corpus_digest == OWNED_QUALITY_CORPUS_DIGEST
            and len(loaded.model.features) == QUALITY_FEATURE_COUNT
            and len(loaded.model.views) == QUALITY_VIEW_COUNT
            and len(loaded.corpus.profiles) == QUALITY_PROFILE_COUNT
        ),
        detail=(
            f"model={loaded.model.model_id}@{loaded.model.model_version};"
            f"corpus={loaded.corpus.corpus_id}@{loaded.corpus.corpus_version};"
            f"features={len(loaded.model.features)};views={len(loaded.model.views)};"
            f"profiles={len(loaded.corpus.profiles)}"
        ),
    )
    in_domain = assess_quality_consensus(schema, document, loaded)
    support_check = EvalCheck(
        name="quality.in_domain",
        passed=(
            in_domain.status is ConsensusStatus.IN_DOMAIN
            and in_domain.reason_code == "quality.consensus_supported"
            and in_domain.evaluated_views == len(loaded.model.views)
        ),
        detail=(
            f"status={in_domain.status.value};views="
            f"{in_domain.evaluated_views}/{in_domain.total_views}"
        ),
    )
    outlier = _replace_domain_observed(
        document,
        "/specimen/warm_ischemia_time",
        1440.0,
    )
    out_of_domain = assess_quality_consensus(schema, outlier, loaded)
    ood_check = EvalCheck(
        name="quality.out_of_domain",
        passed=(
            out_of_domain.status is ConsensusStatus.OUT_OF_DOMAIN
            and out_of_domain.reason_code == "quality.novel_or_ood"
        ),
        detail=f"status={out_of_domain.status.value};reason={out_of_domain.reason_code}",
    )
    anchors = {"/specimen/preservation", "/acquisition/method"}
    sparse = document.model_copy(
        update={
            "entries": tuple(entry for entry in document.entries if entry.path in anchors)
        }
    )
    abstained = assess_quality_consensus(schema, sparse, loaded)
    abstention_check = EvalCheck(
        name="quality.abstention",
        passed=(
            abstained.status is ConsensusStatus.INDETERMINATE
            and abstained.reason_code == "quality.insufficient_view_consensus"
            and abstained.evaluated_views == 0
        ),
        detail=f"status={abstained.status.value};reason={abstained.reason_code}",
    )
    permuted = assess_quality_consensus(
        schema.model_copy(update={"fields": tuple(reversed(schema.fields))}),
        document.model_copy(update={"entries": tuple(reversed(document.entries))}),
        loaded,
    )
    order_check = EvalCheck(
        name="quality.order_invariance",
        passed=permuted == in_domain,
        detail=f"status={permuted.status.value};views={permuted.evaluated_views}",
    )
    public_values = asdict(in_domain)
    forbidden_keys = {
        "cluster_id",
        "consensus",
        "features",
        "mean_distance",
        "neighbors",
        "votes",
    }
    leaked_keys = sorted(forbidden_keys.intersection(public_values))
    rendered = repr((in_domain, out_of_domain, abstained))
    leaked_clusters = sorted(
        cluster
        for cluster in ("frozen_dda", "frozen_dia", "ffpe_dda", "ffpe_dia")
        if cluster in rendered
    )
    privacy_check = EvalCheck(
        name="quality.public_privacy",
        passed=not leaked_keys and not leaked_clusters,
        detail=(
            "coarse status envelope only"
            if not leaked_keys and not leaked_clusters
            else f"keys={','.join(leaked_keys)};clusters={','.join(leaked_clusters)}"
        ),
    )
    return [
        artifact_check,
        support_check,
        ood_check,
        abstention_check,
        order_check,
        privacy_check,
    ]


def _run_fixture(case: FixtureCase) -> EvalCheck:
    expected = case["expected"]
    try:
        validated = load_case(case)
    except (ValidationError, ValueError) as error:
        correct_boundary = (
            isinstance(error, StrictJsonError)
            if case["phase"] == "json"
            else isinstance(error, ValidationError)
        )
        passed = expected == "reject" and correct_boundary
        return EvalCheck(
            name=case["case_id"],
            passed=passed,
            detail=f"rejected:{type(error).__name__}",
        )
    if expected == "reject":
        return EvalCheck(
            name=case["case_id"], passed=False, detail="unexpectedly accepted"
        )
    if "expected_decision" not in case:
        return EvalCheck(
            name=case["case_id"],
            passed=True,
            detail=f"accepted:{type(validated).__name__}",
        )
    if not isinstance(validated, EvaluateMetadataRequest):
        return EvalCheck(
            name=case["case_id"],
            passed=False,
            detail="validation case is not an evaluate request",
        )
    report = validate_metadata(
        load_protocol_schema(),
        validated.document,
        consent_state=validated.context.references.consent.state,
    )
    actual_codes = [issue.code for issue in report.issues]
    passed = (
        report.decision.value == case["expected_decision"]
        and actual_codes == case["expected_issue_codes"]
    )
    detail = f"decision={report.decision.value};issues={','.join(actual_codes) or 'none'}"
    return EvalCheck(case["case_id"], passed, detail)


def _metamorphic_checks() -> list[EvalCheck]:
    schema = load_protocol_schema()
    request = cast(
        "EvaluateMetadataRequest",
        load_request("evaluate_conformant.valid.json"),
    )
    expected = validate_metadata(schema, request.document, consent_state=ConsentState.GRANTED)
    reversed_schema = schema.model_copy(update={"fields": tuple(reversed(schema.fields))})
    reversed_document = request.document.model_copy(
        update={"entries": tuple(reversed(request.document.entries))}
    )
    actual = validate_metadata(
        reversed_schema,
        reversed_document,
        consent_state=ConsentState.GRANTED,
    )
    immutable_before = (schema.model_dump_json(), request.document.model_dump_json())
    validate_metadata(schema, request.document, consent_state=ConsentState.UNKNOWN)
    immutable_after = (schema.model_dump_json(), request.document.model_dump_json())
    permuted_request = request.model_copy(update={"document": reversed_document})
    return [
        EvalCheck(
            "metamorphic.field_order",
            actual == expected,
            "reversed schema fields and entries preserve the report",
        ),
        EvalCheck(
            "metamorphic.upstream_immutability",
            immutable_before == immutable_after,
            "validation leaves schema and document byte-identical",
        ),
        EvalCheck(
            "metamorphic.content_identity",
            protocol_digest(reversed_schema) == protocol_digest(schema)
            and metadata_document_digest(reversed_document)
            == metadata_document_digest(request.document)
            and canonical_request_digest(permuted_request)
            == canonical_request_digest(request),
            "semantically unordered fields and entries have one digest identity",
        ),
    ]


def _uncapped_array_paths(node: object, path: str = "$") -> list[str]:
    if isinstance(node, list):
        return [
            nested
            for index, value in enumerate(node)
            for nested in _uncapped_array_paths(value, f"{path}/{index}")
        ]
    if not isinstance(node, dict):
        return []
    current = [path] if node.get("type") == "array" and "maxItems" not in node else []
    return [
        *current,
        *(
            nested
            for key, value in node.items()
            for nested in _uncapped_array_paths(value, f"{path}/{key}")
        ),
    ]


def _schema_and_resource_checks() -> list[EvalCheck]:
    checks: list[EvalCheck] = []
    for name in PUBLIC_SCHEMA_NAMES:
        document = contract_json_schema(name)
        try:
            Draft202012Validator.check_schema(document)
        except SchemaError as error:
            checks.append(
                EvalCheck(
                    name=f"schema.{name}",
                    passed=False,
                    detail=type(error).__name__,
                )
            )
        else:
            checks.append(
                EvalCheck(
                    name=f"schema.{name}",
                    passed=True,
                    detail=str(document["$id"]),
                )
            )
    uncapped = [
        *_uncapped_array_paths(TypeAdapter(M0101Request).json_schema(mode="validation")),
        *_uncapped_array_paths(TypeAdapter(M0101Output).json_schema(mode="validation")),
    ]
    checks.append(
        EvalCheck(
            "resource.collection_caps",
            not uncapped,
            "all public arrays are bounded" if not uncapped else ",".join(uncapped),
        )
    )
    try:
        TypeAdapter(ObservedValue).validate_python(
            {"state": "observed", "value": "x" * (SCALAR_TEXT_LIMIT + 1)},
            strict=True,
        )
    except ValidationError:
        scalar_passed = True
    else:
        scalar_passed = False
    checks.append(
        EvalCheck(
            "resource.scalar_cap",
            scalar_passed,
            "first byte beyond scalar ceiling is rejected",
        )
    )
    return checks


def _protocol_checks() -> list[EvalCheck]:
    schema = load_protocol_schema()
    baseline = validate_protocol_schema(schema)
    unsafe_field = schema.fields[0].model_copy(update={"pattern": "^(a+)+$"})
    unsafe = schema.model_copy(update={"fields": (unsafe_field, *schema.fields[1:])})
    unsafe_report = validate_protocol_schema(unsafe)
    dimension_field = schema.fields[2].model_copy(update={"unit_dimension": "length"})
    mismatched = schema.model_copy(
        update={"fields": (*schema.fields[:2], dimension_field, *schema.fields[3:])}
    )
    dimension_report = validate_protocol_schema(mismatched)
    adjacent_optionals = "^" + "a?" * 24 + "a" * 24 + "b$"
    adversarial_field = schema.fields[0].model_copy(update={"pattern": adjacent_optionals})
    adversarial = schema.model_copy(
        update={"fields": (adversarial_field, *schema.fields[1:])}
    )
    adversarial_report = validate_protocol_schema(adversarial)
    return [
        EvalCheck(
            "protocol.reference",
            baseline.decision is ConformanceDecision.CONFORMANT and not baseline.issues,
            baseline.decision.value,
        ),
        EvalCheck(
            "protocol.unsafe_pattern",
            unsafe_report.decision is ConformanceDecision.QUARANTINED
            and "schema.pattern_unsafe" in {issue.code for issue in unsafe_report.issues},
            unsafe_report.decision.value,
        ),
        EvalCheck(
            "protocol.unit_dimension",
            dimension_report.decision is ConformanceDecision.QUARANTINED
            and "schema.unit_dimension_mismatch"
            in {issue.code for issue in dimension_report.issues},
            dimension_report.decision.value,
        ),
        EvalCheck(
            "protocol.adjacent_optionals",
            adversarial_report.decision is ConformanceDecision.QUARANTINED
            and "schema.pattern_unsafe"
            in {issue.code for issue in adversarial_report.issues},
            adversarial_report.decision.value,
        ),
    ]


def _measure_latency(iterations: int) -> LatencySummary:
    schema = load_protocol_schema()
    request = cast(
        "EvaluateMetadataRequest",
        load_request("evaluate_conformant.valid.json"),
    )
    for _ in range(100):
        validate_metadata(schema, request.document, consent_state=ConsentState.GRANTED)
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        validate_metadata(schema, request.document, consent_state=ConsentState.GRANTED)
        samples.append(perf_counter_ns() - started)
    ordered = sorted(samples)
    p95_index = min(len(ordered) - 1, (len(ordered) * 95 + 99) // 100 - 1)
    return LatencySummary(
        iterations=iterations,
        mean_ns=fmean(samples),
        p50_ns=median(samples),
        p95_ns=ordered[p95_index],
        maximum_ns=max(samples),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=1_000)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.iterations < 1:
        _parser().error("--iterations must be positive")
    domain_checks = _domain_profile_checks()
    quality_checks = _quality_consensus_checks()
    domain_case_count = len(_domain_corpus()["cases"])
    checks = [
        *domain_checks,
        *quality_checks,
        *_fixture_checks(),
        *_protocol_checks(),
        *_metamorphic_checks(),
        *_schema_and_resource_checks(),
    ]
    latency = _measure_latency(args.iterations)
    checks.append(
        EvalCheck(
            "performance.reference_latency",
            latency.mean_ns <= latency.mean_budget_ns and latency.p95_ns <= latency.p95_budget_ns,
            f"mean={latency.mean_ns:.0f}ns;p95={latency.p95_ns}ns",
        )
    )
    passed = all(check.passed for check in checks)
    result = {
        "module_id": MODULE_ID,
        "passed": passed,
        "checks": [asdict(check) for check in checks],
        "domain_profile": {
            "schema_id": "glio_preanalytic_proteomics",
            "schema_version": "1.0.0",
            "case_count": domain_case_count,
            "passed": all(check.passed for check in domain_checks),
        },
        "quality_consensus": {
            "model_digest": OWNED_QUALITY_MODEL_DIGEST,
            "corpus_digest": OWNED_QUALITY_CORPUS_DIGEST,
            "check_count": len(quality_checks),
            "passed": all(check.passed for check in quality_checks),
        },
        "latency": asdict(latency),
    }
    serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(serialized)
    else:
        args.output.write_text(serialized, encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
