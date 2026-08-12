"""Replay the locked M01-08 deterministic release-packaging fixture."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal, NotRequired, TypedDict, cast

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m01_08 import (
    BuildReleasePackageRequest,
    DecisionKind,
    DecisionReceipt,
    DecisionState,
    ExternalSignatureReceipt,
    NumericalTolerance,
    NumericalToleranceMode,
    ReferenceVersionRecord,
    ReleaseArtifact,
    ReleasePackagingPolicy,
    SoftwareVersionRecord,
    TransformationRecord,
    configuration_digest,
    manifest_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_08_release_packaging import (
    ReleasePackagingAuthorizationError,
    ReleasePackagingInputError,
    build_release_package,
    preflight_release_packaging_authorization,
    sha256_bytes,
    verify_release_package,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M01-08"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m01_08" / "scenarios.json"
EXPECTED_SCENARIO_COUNT: Final = 8
EXPECTED_ARTIFACT_COUNT: Final = 3
_REQUEST_ADAPTER: Final = TypeAdapter(BuildReleasePackageRequest)

_FILES: Final = {
    "metadata/run.json": b'{"run":"synthetic"}\n',
    "results/proteins.tsv": b"protein\tvalue\nP1\t1.0\n",
    "quality/summary.json": b'{"status":"accepted"}\n',
}


class Scenario(TypedDict):
    case_id: str
    request_case: str
    outcome: Literal["result", "rejected", "validation_rejected", "authorization_rejected"]
    expected_disposition: NotRequired[str | None]
    expected_reason: NotRequired[str]


class Corpus(TypedDict):
    module_id: str
    schema_version: str
    data_classification: str
    claims_ceiling: str
    artifact_count: int
    scenarios: list[Scenario]


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _artifact(label: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.{label}",
        version="1.0.0",
        digest=digest or sha256_digest({"m0108": label}),
        media_type="application/json",
    )


def _context(configuration: str) -> ExecutionContext:
    def decision(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.synthetic.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(role, digest),
        )

    return ExecutionContext(
        request_id="request.synthetic.m0108",
        actor_id="actor.synthetic.eval",
        occurred_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration", configuration),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.synthetic.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"m0108": "identity"}),
                evidence=_artifact("identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.synthetic.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _base_request() -> tuple[BuildReleasePackageRequest, dict[str, bytes]]:
    policy = ReleasePackagingPolicy(
        policy_id="policy.synthetic.release",
        version="1.0.0",
        allowed_signature_algorithms=("ed25519",),
    )
    artifacts = tuple(
        ReleaseArtifact(
            path=path,
            role="release_artifact",
            source=_artifact(path.replace("/", "."), sha256_bytes(content)),
            byte_size=len(content),
        )
        for path, content in sorted(_FILES.items())
    )
    inputs = tuple(item.source.digest for item in artifacts)
    decisions = tuple(
        DecisionReceipt(
            kind=kind,
            decision_id=f"decision.synthetic.{kind.value}",
            state=DecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(f"decision.{kind.value}"),
        )
        for kind in DecisionKind
    )
    request = BuildReleasePackageRequest(
        context=_context(configuration_digest(policy)),
        release_id="release.synthetic.m0108",
        release_version="1.0.0",
        artifacts=artifacts,
        software_versions=(
            SoftwareVersionRecord(
                software_id="software.glio_proteogen",
                version="0.1.0",
                digest=sha256_digest({"software": "glio-proteogen", "version": "0.1.0"}),
                evidence=_artifact("software"),
            ),
        ),
        reference_versions=(
            ReferenceVersionRecord(
                reference_id="reference.synthetic",
                version="1.0.0",
                digest=sha256_digest({"reference": "synthetic"}),
                evidence=_artifact("reference"),
            ),
        ),
        transformations=(
            TransformationRecord(
                step_id="step.synthetic.export",
                ordinal=1,
                name="Synthetic export",
                version="1.0.0",
                input_digests=inputs,
                output_digests=inputs,
                evidence=_artifact("transformation"),
            ),
        ),
        decisions=decisions,
        numerical_tolerances=(
            NumericalTolerance(
                tolerance_id="tolerance.exact",
                mode=NumericalToleranceMode.EXACT,
            ),
        ),
        policy=policy,
    )
    candidate = build_release_package(request, _FILES)
    receipt = ExternalSignatureReceipt(
        key_id="key.external.synthetic",
        algorithm="ed25519",
        signer_id="signer.external.synthetic",
        policy_id="policy.external.signature",
        policy_version="1.0.0",
        package_digest=candidate.result.package.digest,
        manifest_digest=candidate.result.manifest_digest,
        evidence=_artifact("external-signature-receipt"),
    )
    return request.model_copy(update={"signature_receipt": receipt}), dict(_FILES)


def build_scenario(case: str) -> tuple[BuildReleasePackageRequest, dict[str, bytes]]:
    """Build one deterministic strict request and its exact in-memory artifact mapping."""

    request, files = _base_request()
    if case in {"canonical", "consent_denied"}:
        return request, files
    if case == "tampered_byte":
        files[request.artifacts[0].path] += b"tampered"
        return request, files
    if case == "wrong_digest":
        first = request.artifacts[0].model_copy(update={"source": _artifact("wrong")})
        return request.model_copy(update={"artifacts": (first, *request.artifacts[1:])}), files
    if case == "missing_receipt":
        return request.model_copy(update={"signature_receipt": None}), files
    if case == "mismatched_receipt":
        receipt = request.signature_receipt
        if receipt is None:
            raise RuntimeError from None
        return request.model_copy(
            update={
                "signature_receipt": receipt.model_copy(
                    update={"package_digest": sha256_digest({"wrong": True})}
                )
            }
        ), files
    raise ValueError(case)


def _reordered(request: BuildReleasePackageRequest) -> BuildReleasePackageRequest:
    return request.model_copy(
        update={
            "artifacts": tuple(reversed(request.artifacts)),
            "software_versions": tuple(reversed(request.software_versions)),
            "reference_versions": tuple(reversed(request.reference_versions)),
            "transformations": tuple(reversed(request.transformations)),
            "decisions": tuple(reversed(request.decisions)),
            "numerical_tolerances": tuple(reversed(request.numerical_tolerances)),
        }
    )


def _canonical_check(scenario: Scenario) -> tuple[EvalCheck, dict[str, object]]:
    request, files = build_scenario("canonical")
    built = build_release_package(request, files)
    replay = build_release_package(_reordered(request), dict(reversed(tuple(files.items()))))
    verification = verify_release_package(built.result, built.package_bytes)
    expected_manifest = {
        "paths": [item.path for item in sorted(request.artifacts, key=lambda item: item.path)],
        "sizes": [item.byte_size for item in sorted(request.artifacts, key=lambda item: item.path)],
        "digests": [
            item.source.digest
            for item in sorted(request.artifacts, key=lambda item: item.path)
        ],
        "software": [item.model_dump(mode="json") for item in request.software_versions],
        "references": [item.model_dump(mode="json") for item in request.reference_versions],
        "transformations": [item.model_dump(mode="json") for item in request.transformations],
        "decisions": [
            item.model_dump(mode="json")
            for item in sorted(request.decisions, key=lambda item: item.kind.value)
        ],
        "tolerances": [item.model_dump(mode="json") for item in request.numerical_tolerances],
    }
    actual_manifest = {
        "paths": [item.path for item in built.result.manifest.artifacts],
        "sizes": [item.byte_size for item in built.result.manifest.artifacts],
        "digests": [item.source.digest for item in built.result.manifest.artifacts],
        "software": [
            item.model_dump(mode="json")
            for item in built.result.manifest.software_versions
        ],
        "references": [
            item.model_dump(mode="json")
            for item in built.result.manifest.reference_versions
        ],
        "transformations": [
            item.model_dump(mode="json")
            for item in built.result.manifest.transformations
        ],
        "decisions": [item.model_dump(mode="json") for item in built.result.manifest.decisions],
        "tolerances": [
            item.model_dump(mode="json")
            for item in built.result.manifest.numerical_tolerances
        ],
    }
    passed = (
        built.package_bytes == replay.package_bytes
        and built.result == replay.result
        and built.result.disposition.value == scenario["expected_disposition"]
        and actual_manifest == expected_manifest
        and manifest_digest(built.result.manifest) == built.result.manifest_digest
        and verification.verified
    )
    return (
        EvalCheck(
            name="scenario.canonical_three_artifact_package",
            passed=passed,
            detail=f"digest={built.result.package.digest};order_equal={built == replay}",
        ),
        cast("dict[str, object]", built.result.model_dump(mode="json")),
    )


def _negative_check(scenario: Scenario) -> EvalCheck:
    case = scenario["request_case"]
    if case in {"path_traversal", "duplicate_path"}:
        request, _ = build_scenario("canonical")
        payload = request.model_dump(mode="python")
        if case == "path_traversal":
            payload["artifacts"][0]["path"] = "../escape.txt"
        else:
            payload["artifacts"][1]["path"] = payload["artifacts"][0]["path"]
        try:
            _REQUEST_ADAPTER.validate_python(payload, strict=True)
        except ValidationError:
            return EvalCheck(
                name=f"scenario.{scenario['case_id']}",
                passed=True,
                detail="strict validation rejected",
            )
        return EvalCheck(
            name=f"scenario.{scenario['case_id']}",
            passed=False,
            detail="not rejected",
        )
    request, files = build_scenario(case)
    try:
        build_release_package(request, files)
    except ReleasePackagingInputError:
        return EvalCheck(
            name=f"scenario.{scenario['case_id']}",
            passed=True,
            detail="artifact integrity rejected",
        )
    return EvalCheck(
        name=f"scenario.{scenario['case_id']}",
        passed=False,
        detail="not rejected",
    )


def _consent_check(scenario: Scenario) -> EvalCheck:
    request, _ = build_scenario("consent_denied")
    payload = request.model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    payload["artifacts"] = object()
    try:
        preflight_release_packaging_authorization(payload)
    except ReleasePackagingAuthorizationError:
        return EvalCheck(
            name=f"scenario.{scenario['case_id']}",
            passed=True,
            detail="authorization rejected before artifacts",
        )
    return EvalCheck(
        name=f"scenario.{scenario['case_id']}",
        passed=False,
        detail="not rejected",
    )


def _boundary(results: list[dict[str, object]]) -> EvalCheck:
    forbidden = {
        "kinase_activity",
        "package_bytes",
        "private_key",
        "proteotype",
        "raw_spectra",
        "treatment_recommendation",
    }
    rendered = json.dumps(results, sort_keys=True)
    leaked = sorted(key for key in forbidden if key in rendered)
    return EvalCheck(
        name="boundary.closed_typed_output",
        passed=not leaked,
        detail="closed typed output" if not leaked else f"forbidden={','.join(leaked)}",
    )


def _corpus() -> Corpus:
    return cast("Corpus", strict_json_loads(SCENARIO_PATH.read_bytes()))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    corpus = _corpus()
    checks: list[EvalCheck] = []
    results: list[dict[str, object]] = []
    for scenario in corpus["scenarios"]:
        if scenario["request_case"] == "canonical":
            check, result = _canonical_check(scenario)
            checks.append(check)
            results.append(result)
        elif scenario["outcome"] == "result":
            request, files = build_scenario(scenario["request_case"])
            built = build_release_package(request, files)
            checks.append(
                EvalCheck(
                    name=f"scenario.{scenario['case_id']}",
                    passed=(
                        built.result.disposition.value
                        == scenario["expected_disposition"]
                        and built.result.quarantine_reason == scenario["expected_reason"]
                    ),
                    detail=(
                        f"disposition={built.result.disposition.value};"
                        f"reason={built.result.quarantine_reason}"
                    ),
                )
            )
            results.append(cast("dict[str, object]", built.result.model_dump(mode="json")))
        elif scenario["outcome"] == "authorization_rejected":
            checks.append(_consent_check(scenario))
        else:
            checks.append(_negative_check(scenario))
    checks.append(_boundary(results))
    passed = (
        corpus["module_id"] == MODULE_ID
        and corpus["artifact_count"] == EXPECTED_ARTIFACT_COUNT
        and len(corpus["scenarios"]) == EXPECTED_SCENARIO_COUNT
        and all(check.passed for check in checks)
    )
    report = {
        "module_id": MODULE_ID,
        "passed": passed,
        "scenario_count": len(corpus["scenarios"]),
        "corpus_digest": sha256_digest(corpus),
        "checks": [asdict(check) for check in checks],
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
