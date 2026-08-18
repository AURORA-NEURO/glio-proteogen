"""Execute the locked M03-08 protein-inference release evidence plan."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import tarfile
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from pydantic import ValidationError

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m03_02.run import build_scenario_request as build_m0302_request
from evals.m03_03 import run as m0303_evidence
from evals.m03_03.run import ScenarioOptions as M0303ScenarioOptions
from evals.m03_03.run import build_scenario as build_m0303_scenario
from evals.m03_04 import run as m0304_evidence
from evals.m03_04.run import build_scenario as build_m0304_scenario
from evals.m03_05 import run as m0305_evidence
from evals.m03_06.run import build_scenario as build_m0306_scenario
from evals.m03_07 import run as m0307_evidence
from evals.m03_07.run import build_scenario as build_m0307_scenario
from glio_proteogen.contracts.m03_03 import ProteinInferenceRawRole
from glio_proteogen.contracts.m03_05 import (
    ProteinInferenceArtifactSignalCode,
    artifact_quality_receipt,
)
from glio_proteogen.contracts.m03_07 import (
    ProteinInferenceDeclaredSupportState,
    ProteinInferenceSupportDimension,
    ProteinInferenceSupportRouteResult,
)
from glio_proteogen.contracts.m03_08 import (
    M0308_ARCHIVE_MEMBER_COUNT,
    M0308_CONTRACT_VERSION,
    M0308_MANIFEST_PATH,
    M0308_MAX_ARTIFACT_BYTES,
    M0308_MAX_CANONICAL_REQUEST_BYTES,
    M0308_MAX_PACKAGE_BYTES,
    M0308_MAX_REFERENCE_VERSIONS,
    M0308_MAX_SIGNATURE_ALGORITHMS,
    M0308_MAX_SIGNATURE_VALUE_CHARS,
    M0308_MAX_SOFTWARE_VERSIONS,
    M0308_MAX_TOTAL_ARTIFACT_BYTES,
    M0308_MAX_VERIFIER_IDS,
    M0308_SIGNATURE_RECEIPT_PATH,
    BuildProteinInferenceReleaseRequest,
    ExternalProteinInferenceSignature,
    ProteinInferencePackageVerificationReason,
    ProteinInferenceReferenceVersion,
    ProteinInferenceReleaseArtifact,
    ProteinInferenceReleaseArtifactRole,
    ProteinInferenceReleaseDisposition,
    ProteinInferenceReleasePolicy,
    ProteinInferenceReleaseResult,
    ProteinInferenceReproductionEvidence,
    ProteinInferenceSignatureAlgorithm,
    ProteinInferenceSoftwareVersion,
    ProteinInferenceStageModuleId,
    manifest_digest,
    normalized_manifest,
    policy_digest,
    result_payload_digest,
    signing_statement_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.canonical_ustar import (
    PackageMember,
    inspect_canonical_ustar,
    sha256_bytes,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ControlRole,
    ExecutionContext,
    FrozenModel,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_02_identity_lineage import (
    reconcile_protein_inference_identity_lineage,
)
from glio_proteogen.modules.c03_protein_inference.m03_03_raw_ingestion import (
    ingest_protein_inference_raw_inputs,
)
from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics import (
    compute_protein_inference_quality,
)
from glio_proteogen.modules.c03_protein_inference.m03_05_artifact_detection import (
    detect_protein_inference_artifacts,
)
from glio_proteogen.modules.c03_protein_inference.m03_07_support_router import (
    protein_inference_support_prerequisites,
    route_protein_inference_support,
)
from glio_proteogen.modules.c03_protein_inference.m03_08_release_packaging.engine import (
    ProteinInferenceReleaseAuthorizationError,
    ProteinInferenceReleaseInputError,
    ProteinInferenceReleaseInputErrorCode,
    build_protein_inference_release,
    build_protein_inference_release_manifest,
    verify_protein_inference_release,
)
from glio_proteogen.modules.c03_protein_inference.m03_08_release_packaging.plugin import (
    M0308Plugin,
    ProteinInferenceReleaseSubmission,
)
from glio_proteogen.modules.c03_protein_inference.m03_08_release_packaging.service import (
    M0308Service,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m03_01 import ProteinInferenceProtocolConformanceResult
    from glio_proteogen.contracts.m03_02 import ProteinInferenceIdentityLineageResolution
    from glio_proteogen.contracts.m03_03 import ProteinInferenceRawAdmissionResult
    from glio_proteogen.contracts.m03_04 import ProteinInferenceQualityResult
    from glio_proteogen.contracts.m03_05 import ProteinInferenceArtifactDetectionResult
    from glio_proteogen.contracts.m03_06 import ProteinInferenceHarmonizationResult

MODULE_ID: Final = "GLIO-PROTEOGEN-M03-08"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m03_08" / "scenarios.json"
EXPECTED_GROUP_IDS: Final = (
    "canonical_release_and_semantic_reorder",
    "seven_stage_disposition_matrix",
    "cross_chain_closure",
    "integrity_and_archive_safety",
    "signature_binding_and_replay",
    "strict_canonical_reconstruction",
    "privacy_and_ownership_closure",
    "authorization_recovery_and_maximum_shape",
)
EXPECTED_GROUP_CASE_COUNTS: Final = (2, 7, 3, 8, 6, 6, 1, 5)
EXPECTED_CASE_COUNT: Final = 38
STAGE_MODULE_IDS: Final = tuple(f"GLIO-PROTEOGEN-M03-{index:02d}" for index in range(1, 8))
NONCRYPTO_ALGORITHM: Final = ProteinInferenceSignatureAlgorithm.ED25519
NONCRYPTO_SIGNATURE: Final = "NONCRYPTO_EVALUATION_TOKEN"

_ARTIFACT_PATHS: Final = {
    ProteinInferenceReleaseArtifactRole.PARENT_COMPLEX_ACTIVITY_HANDOFF: (
        "parent/complex-activity-handoff.json"
    ),
    ProteinInferenceReleaseArtifactRole.M03_01_PROTOCOL_CONFORMANCE: (
        "stages/m03-01-protocol-conformance.json"
    ),
    ProteinInferenceReleaseArtifactRole.M03_02_IDENTITY_LINEAGE: (
        "stages/m03-02-identity-lineage.json"
    ),
    ProteinInferenceReleaseArtifactRole.M03_03_RAW_INGESTION: ("stages/m03-03-raw-ingestion.json"),
    ProteinInferenceReleaseArtifactRole.M03_04_QUALITY: "stages/m03-04-quality.json",
    ProteinInferenceReleaseArtifactRole.M03_05_ARTIFACT_DETECTION: (
        "stages/m03-05-artifact-detection.json"
    ),
    ProteinInferenceReleaseArtifactRole.M03_06_HARMONIZATION: ("stages/m03-06-harmonization.json"),
    ProteinInferenceReleaseArtifactRole.M03_07_SUPPORT_ROUTE: ("stages/m03-07-support-route.json"),
}
_ARTIFACT_MEDIA_TYPES: Final = {
    ProteinInferenceReleaseArtifactRole.PARENT_COMPLEX_ACTIVITY_HANDOFF: (
        "application/vnd.glio-proteogen.complex-activity-handoff+json"
    ),
    **{
        role: f"application/vnd.glio-proteogen.m03-{index:02d}+json"
        for index, role in enumerate(
            tuple(ProteinInferenceReleaseArtifactRole)[1:],
            start=1,
        )
    },
}


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class GenuineProteinInferenceChain:
    """Seven genuine public C03 results forming one exact releasable chain."""

    protocol: ProteinInferenceProtocolConformanceResult
    identity: ProteinInferenceIdentityLineageResolution
    ingestion: ProteinInferenceRawAdmissionResult
    quality: ProteinInferenceQualityResult
    artifact_detection: ProteinInferenceArtifactDetectionResult
    harmonization: ProteinInferenceHarmonizationResult
    support_route: ProteinInferenceSupportRouteResult

    def ordered_results(self) -> tuple[FrozenModel, ...]:
        return (
            self.protocol,
            self.identity,
            self.ingestion,
            self.quality,
            self.artifact_detection,
            self.harmonization,
            self.support_route,
        )

    def by_module(self) -> dict[str, FrozenModel]:
        return dict(zip(STAGE_MODULE_IDS, self.ordered_results(), strict=True))


@dataclass(frozen=True, slots=True)
class ProteinInferenceReleaseFixture:
    request: BuildProteinInferenceReleaseRequest
    artifacts: dict[str, bytes]
    stages: dict[str, FrozenModel]


@dataclass(frozen=True, slots=True)
class Scenario:
    fixture: ProteinInferenceReleaseFixture
    verifier: DeterministicNonCryptographicVerifier

    @property
    def request(self) -> BuildProteinInferenceReleaseRequest:
        return self.fixture.request

    @property
    def artifacts(self) -> dict[str, bytes]:
        return self.fixture.artifacts

    @property
    def stages(self) -> dict[str, FrozenModel]:
        return self.fixture.stages


class _PrematureTraversalError(AssertionError):
    pass


class _ScenarioClosureError(ValueError):
    pass


class _InvalidCorpusError(TypeError):
    pass


class _VerifierFailureError(RuntimeError):
    pass


class _UnreadableMapping(Mapping[str, object]):
    """Hostile mapping proving authorization precedes caller-controlled traversal."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.traversals = 0

    def _fail(self) -> int:
        self.traversals += 1
        raise _PrematureTraversalError(self.label)

    def __getitem__(self, key: str) -> object:
        del key
        self._fail()
        raise AssertionError

    def __iter__(self) -> Iterator[str]:
        self._fail()
        return iter(())

    def __len__(self) -> int:
        self._fail()
        return 0


class DeterministicNonCryptographicVerifier:
    """Evaluation seam only; it supplies no cryptographic or authority assurance."""

    def __init__(self, *, accept: bool = True) -> None:
        self.accept = accept
        self.calls: list[tuple[str, ExternalProteinInferenceSignature]] = []

    @property
    def verifier_id(self) -> str:
        return _oid("verifier", "deterministic-noncrypto-v1")

    def verify(
        self,
        *,
        statement_digest: str,
        signature: ExternalProteinInferenceSignature,
    ) -> bool:
        self.calls.append((statement_digest, signature))
        return (
            self.accept
            and statement_digest == signature.claimed_statement_digest
            and signature.signature_value == NONCRYPTO_SIGNATURE
        )


class _UnavailableVerifier(DeterministicNonCryptographicVerifier):
    @property
    def verifier_id(self) -> str:
        raise _VerifierFailureError


def _oid(namespace: str, label: object) -> str:
    suffix = sha256_digest(
        {"module": MODULE_ID, "namespace": namespace, "label": label}
    ).removeprefix("sha256:")
    return f"{namespace}.{suffix}"


def _evidence(label: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=_oid("evidence", label),
        version="1.0.0",
        digest=digest or sha256_digest({"m0308_evidence": label}),
        media_type="application/json",
    )


def _identity_subject(result: FrozenModel) -> str:
    if not hasattr(result, "provenance"):
        raise _ScenarioClosureError
    record = next(
        item
        for item in result.provenance.control_decisions
        if item.role is ControlRole.IDENTITY_LINEAGE
    )
    if record.subject_digest is None:
        raise _ScenarioClosureError
    return str(record.subject_digest)


@lru_cache(maxsize=1)
def build_genuine_chain() -> GenuineProteinInferenceChain:
    """Compose the exact public M03-01..07 results without forging any output."""

    ingestion_scenario = build_m0303_scenario()
    quality_scenario = build_m0304_scenario()
    artifact_scenario = build_m0306_scenario()
    support_scenario = build_m0307_scenario()
    support_route = route_protein_inference_support(support_scenario.request)
    chain = GenuineProteinInferenceChain(
        protocol=ingestion_scenario.protocol_result,
        identity=ingestion_scenario.lineage_result,
        ingestion=quality_scenario.upstream_result,
        quality=support_scenario.quality_result,
        artifact_detection=artifact_scenario.artifact_result,
        harmonization=support_scenario.harmonization_result,
        support_route=support_route,
    )
    if len({_identity_subject(item) for item in chain.ordered_results()}) != 1:
        raise _ScenarioClosureError
    if (
        chain.harmonization.request.artifact_receipt.artifact_result_digest
        != chain.artifact_detection.result_digest
    ):
        raise _ScenarioClosureError
    return chain


def _policy() -> ProteinInferenceReleasePolicy:
    return ProteinInferenceReleasePolicy(
        policy_id=_oid("policy", "exact-public-release"),
        version="1.0.0",
        allowed_signature_algorithms=(NONCRYPTO_ALGORITHM,),
        allowed_verifier_ids=(_oid("verifier", "deterministic-noncrypto-v1"),),
        evidence=_evidence("release-policy"),
        reviewed_by=_oid("reviewer", "synthetic-governed-reviewer"),
        reviewed_at=datetime(2026, 8, 12, 23, 0, tzinfo=UTC),
    )


def _context(
    active_policy: ProteinInferenceReleasePolicy,
    identity_digest: str,
    intended_use_reference: UpstreamDecisionReference,
    quality_result_digest: str,
    support_route_result_digest: str,
) -> ExecutionContext:
    def accepted(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=_oid("decision", role),
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_evidence(f"control.{role}", digest),
        )

    intended_use = UpstreamDecisionReference(
        decision_id=_oid("decision", "intended-use"),
        state=intended_use_reference.state,
        policy_version=intended_use_reference.policy_version,
        evidence=_evidence(
            "control.intended-use",
            intended_use_reference.evidence.digest,
        ),
    )

    return ExecutionContext(
        request_id=_oid("request", "canonical-release"),
        actor_id=_oid("actor", "synthetic-evaluator"),
        occurred_at=datetime(2026, 8, 13, 0, 0, 8, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted("configuration", policy_digest(active_policy)),
            identity_lineage=IdentityLineageReference(
                decision_id=_oid("decision", "identity-lineage"),
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=identity_digest,
                evidence=_evidence("control.identity-lineage"),
            ),
            provenance=accepted("provenance"),
            consent=ConsentReference(
                decision_id=_oid("decision", "consent"),
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_evidence("control.consent"),
            ),
            quality=accepted("quality", quality_result_digest),
            support=accepted("support", support_route_result_digest),
            intended_use=intended_use,
        ),
    )


def _reproduction_evidence() -> ProteinInferenceReproductionEvidence:
    return ProteinInferenceReproductionEvidence(
        environment_lock=_evidence("reproduction.environment-lock"),
        build_recipe=_evidence("reproduction.build-recipe"),
        locked_tests=_evidence("reproduction.locked-tests"),
        benchmark=_evidence("reproduction.benchmark"),
        traceability=_evidence("reproduction.traceability"),
        reviewer_signoff=_evidence("reproduction.reviewer-signoff"),
        rollback=_evidence("reproduction.rollback"),
    )


def _stage_artifact_id(result: FrozenModel) -> str:
    if isinstance(result, ProteinInferenceSupportRouteResult):
        return result.route_id
    result_id = getattr(result, "result_id", None)
    if not isinstance(result_id, str):
        raise _ScenarioClosureError
    return result_id


def _artifact_bytes(
    chain: GenuineProteinInferenceChain,
    intended_use_digest: str,
) -> dict[str, bytes]:
    parent = canonical_json_bytes(
        {
            "parent_target": "complex_activity",
            "identity_resolution_digest": chain.identity.identity_resolution_digest,
            "intended_use_evidence_digest": intended_use_digest,
            "support_route_result_digest": chain.support_route.result_digest,
            "emits_complex_activity": False,
        }
    )
    values = (parent, *(canonical_json_bytes(item) for item in chain.ordered_results()))
    return {
        _ARTIFACT_PATHS[role]: value
        for role, value in zip(ProteinInferenceReleaseArtifactRole, values, strict=True)
    }


def _artifact_declarations(
    chain: GenuineProteinInferenceChain,
    payloads: Mapping[str, bytes],
) -> tuple[ProteinInferenceReleaseArtifact, ...]:
    results: tuple[FrozenModel | None, ...] = (None, *chain.ordered_results())
    declarations = []
    for role, result in zip(ProteinInferenceReleaseArtifactRole, results, strict=True):
        path = _ARTIFACT_PATHS[role]
        content = payloads[path]
        declarations.append(
            ProteinInferenceReleaseArtifact(
                path=path,
                role=role,
                reference=ArtifactReference(
                    artifact_id=(
                        _oid("parent", {"content_digest": sha256_bytes(content)})
                        if result is None
                        else _stage_artifact_id(result)
                    ),
                    version="1.0.0",
                    digest=sha256_bytes(content),
                    media_type=_ARTIFACT_MEDIA_TYPES[role],
                ),
                declared_size=len(content),
            )
        )
    return tuple(declarations)


def _software_versions(count: int) -> tuple[ProteinInferenceSoftwareVersion, ...]:
    return tuple(
        ProteinInferenceSoftwareVersion(
            software_id=_oid("software", index),
            version="1.0.0",
            build_digest=sha256_digest({"m0308_software_build": index}),
            evidence=_evidence(f"software.{index:02d}"),
        )
        for index in range(count)
    )


def _reference_versions(count: int) -> tuple[ProteinInferenceReferenceVersion, ...]:
    return tuple(
        ProteinInferenceReferenceVersion(
            reference_id=_oid("reference", index),
            build_id=_oid("build", index),
            version=f"2026_{index:02d}",
            digest=sha256_digest({"m0308_reference_build": index}),
            evidence=_evidence(f"reference.{index:02d}"),
        )
        for index in range(count)
    )


def _unsigned_fixture(
    *,
    software_count: int = 2,
    reference_count: int = 2,
    chain: GenuineProteinInferenceChain | None = None,
) -> ProteinInferenceReleaseFixture:
    active_chain = chain or build_genuine_chain()
    active_policy = _policy()
    context = _context(
        active_policy,
        _identity_subject(active_chain.identity),
        active_chain.protocol.context.references.intended_use,
        active_chain.quality.result_digest,
        active_chain.support_route.result_digest,
    )
    payloads = _artifact_bytes(
        active_chain,
        context.references.intended_use.evidence.digest,
    )
    request = BuildProteinInferenceReleaseRequest(
        context=context,
        release_id=_oid("release", "canonical-protein-inference"),
        release_version="1.0.0",
        artifacts=_artifact_declarations(active_chain, payloads),
        software_versions=_software_versions(software_count),
        reference_versions=_reference_versions(reference_count),
        reproduction_evidence=_reproduction_evidence(),
        policy=active_policy,
        signature=ExternalProteinInferenceSignature(
            signer_id=_oid("signer", "external-evaluation"),
            key_id=_oid("key", "noncrypto-evaluation"),
            algorithm=NONCRYPTO_ALGORITHM,
            claimed_statement_digest=sha256_digest({"m0308": "unsigned-placeholder"}),
            signature_value=NONCRYPTO_SIGNATURE,
            issued_at=datetime(2026, 8, 13, 0, 0, 7, tzinfo=UTC),
            evidence=_evidence("signature.external-noncrypto"),
        ),
    )
    return ProteinInferenceReleaseFixture(request, payloads, active_chain.by_module())


def _sign_fixture(fixture: ProteinInferenceReleaseFixture) -> ProteinInferenceReleaseFixture:
    manifest = build_protein_inference_release_manifest(
        fixture.request,
        fixture.artifacts,
        fixture.stages,
    )
    request = fixture.request
    statement = signing_statement_digest(
        active_manifest_digest=manifest_digest(manifest),
        active_policy_digest=policy_digest(request.policy),
        release_id=request.release_id,
        release_version=request.release_version,
        identity_resolution_digest=manifest.identity_resolution_digest,
        intended_use_evidence_digest=manifest.intended_use_evidence_digest,
        support_route_result_digest=manifest.support_route_result_digest,
    )
    signature = request.signature.model_copy(update={"claimed_statement_digest": statement})
    signed = BuildProteinInferenceReleaseRequest.model_validate(
        request.model_copy(update={"signature": signature}).model_dump(mode="python"),
        strict=True,
    )
    return ProteinInferenceReleaseFixture(signed, fixture.artifacts, fixture.stages)


def build_release_fixture(
    *,
    software_count: int = 2,
    reference_count: int = 2,
) -> ProteinInferenceReleaseFixture:
    """Return one signed strict request around genuine public M03-01..07 results."""

    return _sign_fixture(
        _unsigned_fixture(
            software_count=software_count,
            reference_count=reference_count,
        )
    )


def build_scenario() -> Scenario:
    """Public canonical M03-08 scenario used by tests and interface evidence."""

    return Scenario(build_release_fixture(), DeterministicNonCryptographicVerifier())


def build_scenario_request() -> BuildProteinInferenceReleaseRequest:
    return build_scenario().request


def build_maximum_scenario() -> Scenario:
    """Public exact 64-software/64-reference benchmark scenario."""

    return Scenario(
        build_release_fixture(
            software_count=M0308_MAX_SOFTWARE_VERSIONS,
            reference_count=M0308_MAX_REFERENCE_VERSIONS,
        ),
        DeterministicNonCryptographicVerifier(),
    )


def build_representative_release_fixture() -> tuple[
    ProteinInferenceReleaseFixture, DeterministicNonCryptographicVerifier
]:
    scenario = build_maximum_scenario()
    return scenario.fixture, scenario.verifier


def _load_corpus() -> dict[str, object]:
    value = strict_json_loads(SCENARIO_PATH.read_bytes())
    if not isinstance(value, dict):
        raise _InvalidCorpusError
    return dict(value)


def _corpus_check() -> EvalCheck:
    corpus = _load_corpus()
    raw_groups = corpus.get("scenario_groups")
    groups = raw_groups if isinstance(raw_groups, list) else []
    ids = tuple(item.get("group_id") for item in groups if isinstance(item, dict))
    counts = tuple(item.get("case_count") for item in groups if isinstance(item, dict))
    case_ids = tuple(
        case_id
        for item in groups
        if isinstance(item, dict)
        for case_id in item.get("case_ids", [])
        if isinstance(case_id, str)
    )
    passed = (
        corpus.get("module_id") == MODULE_ID
        and ids == EXPECTED_GROUP_IDS
        and counts == EXPECTED_GROUP_CASE_COUNTS
        and len(case_ids) == len(set(case_ids)) == EXPECTED_CASE_COUNT
    )
    return EvalCheck(
        "corpus.exact_eight_groups_thirty_eight_cases",
        passed,
        f"groups={len(ids)};cases={len(case_ids)};unique={len(set(case_ids))}",
    )


def _canonical_check(scenario: Scenario) -> EvalCheck:
    built = build_protein_inference_release(
        scenario.request,
        scenario.artifacts,
        scenario.stages,
        scenario.verifier,
    )
    package = built.package_bytes
    members = inspect_canonical_ustar(package) if package is not None else ()
    member_bytes = {item.path: item.content for item in members}
    expected_manifest = canonical_json_bytes(normalized_manifest(built.result.manifest))
    passed = (
        built.result.disposition is ProteinInferenceReleaseDisposition.RELEASED
        and package is not None
        and len(members) == M0308_ARCHIVE_MEMBER_COUNT
        and all(member_bytes.get(path) == content for path, content in scenario.artifacts.items())
        and member_bytes.get(M0308_MANIFEST_PATH) == expected_manifest
        and M0308_SIGNATURE_RECEIPT_PATH in member_bytes
        and len(scenario.verifier.calls) == 1
    )
    return EvalCheck(
        "scenario.canonical_release",
        passed,
        f"disposition={built.result.disposition.value};members={len(members)}",
    )


def _scenario(case_id: str, *, passed: bool, detail: str) -> EvalCheck:
    return EvalCheck(f"scenario.{case_id}", passed, detail)


def _build(scenario: Scenario) -> tuple[ProteinInferenceReleaseResult, bytes | None]:
    built = build_protein_inference_release(
        scenario.request,
        scenario.artifacts,
        scenario.stages,
        scenario.verifier,
    )
    return built.result, built.package_bytes


def _request_with(
    request: BuildProteinInferenceReleaseRequest,
    **updates: object,
) -> BuildProteinInferenceReleaseRequest:
    payload = request.model_copy(update=updates).model_dump(mode="python")
    return BuildProteinInferenceReleaseRequest.model_validate(payload, strict=True)


def _semantic_reorder_check(scenario: Scenario) -> EvalCheck:
    canonical_result, canonical_package = _build(scenario)
    request = scenario.request
    payload = request.model_dump(mode="python")
    payload["artifacts"] = tuple(reversed(cast("tuple[object, ...]", payload["artifacts"])))
    payload["software_versions"] = tuple(
        reversed(cast("tuple[object, ...]", payload["software_versions"]))
    )
    payload["reference_versions"] = tuple(
        reversed(cast("tuple[object, ...]", payload["reference_versions"]))
    )
    policy = cast("dict[str, object]", payload["policy"])
    policy["allowed_signature_algorithms"] = tuple(
        reversed(cast("tuple[object, ...]", policy["allowed_signature_algorithms"]))
    )
    policy["allowed_verifier_ids"] = tuple(
        reversed(cast("tuple[object, ...]", policy["allowed_verifier_ids"]))
    )
    reordered = BuildProteinInferenceReleaseRequest.model_validate(payload, strict=True)
    reordered_scenario = Scenario(
        ProteinInferenceReleaseFixture(
            reordered,
            dict(reversed(tuple(scenario.artifacts.items()))),
            scenario.stages,
        ),
        DeterministicNonCryptographicVerifier(),
    )
    result, package = _build(reordered_scenario)
    return _scenario(
        "semantic_reorder_replay",
        passed=(
            reordered == request and result == canonical_result and package == canonical_package
        ),
        detail=(
            f"request_equal={reordered == request};package_equal={package == canonical_package}"
        ),
    )


def _downstream_chain(  # noqa: PLR0913 - explicit seven-stage reauthoring inputs.
    *,
    protocol: ProteinInferenceProtocolConformanceResult,
    identity: ProteinInferenceIdentityLineageResolution,
    ingestion: ProteinInferenceRawAdmissionResult,
    quality: ProteinInferenceQualityResult,
    label: str,
    artifact: ProteinInferenceArtifactDetectionResult | None = None,
    harmonization: ProteinInferenceHarmonizationResult | None = None,
    support: ProteinInferenceSupportRouteResult | None = None,
) -> GenuineProteinInferenceChain:
    active_artifact = artifact
    if active_artifact is None:
        active_artifact = detect_protein_inference_artifacts(
            m0305_evidence._with_receipt(
                m0305_evidence.build_scenario().request,
                artifact_quality_receipt(quality),
                evidence_ledger=None,
            )
        )
    active_harmonization = harmonization or m0307_evidence._harmonization_from_artifact_result(
        active_artifact,
        label,
    )
    active_support = support
    if active_support is None:
        template = m0307_evidence.build_scenario().request
        active_support = route_protein_inference_support(
            m0307_evidence._request_with(
                template,
                label,
                prerequisites=protein_inference_support_prerequisites(
                    quality,
                    active_harmonization,
                ),
            )
        )
    return GenuineProteinInferenceChain(
        protocol=protocol,
        identity=identity,
        ingestion=ingestion,
        quality=quality,
        artifact_detection=active_artifact,
        harmonization=active_harmonization,
        support_route=active_support,
    )


def _chain_from_admission(
    protocol: ProteinInferenceProtocolConformanceResult,
    identity: ProteinInferenceIdentityLineageResolution,
    admission: ProteinInferenceRawAdmissionResult,
    label: str,
) -> GenuineProteinInferenceChain:
    quality = compute_protein_inference_quality(
        m0304_evidence._request_from_admission(
            m0304_evidence.build_scenario().request,
            admission,
        )
    )
    return _downstream_chain(
        protocol=protocol,
        identity=identity,
        ingestion=admission,
        quality=quality,
        label=label,
    )


@lru_cache(maxsize=1)
def _nonreleasable_chains() -> tuple[GenuineProteinInferenceChain, ...]:
    chains: list[GenuineProteinInferenceChain] = []
    for label, lineage_case in (
        ("m03_01_quarantined", "protocol_nonconformant"),
        ("m03_02_unreleasable", "identity_unresolved"),
    ):
        identity = reconcile_protein_inference_identity_lineage(build_m0302_request(lineage_case))
        admission, _ = m0303_evidence._safe_failure_result(lineage_case)
        chains.append(
            _chain_from_admission(
                identity.request.protocol_result,
                identity,
                admission,
                label,
            )
        )

    canonical_raw = build_m0303_scenario()
    foreign_vcf = canonical_raw.sources["source.variants.vcf"].replace(
        b"build.synthetic.reference:1.0.0",
        b"build.synthetic.foreign:2.0.0",
    )
    raw_failure = build_m0303_scenario(
        options=M0303ScenarioOptions(
            raw_overrides={ProteinInferenceRawRole.GENOMIC_CONTEXT: foreign_vcf}
        )
    )
    rejected_admission = ingest_protein_inference_raw_inputs(
        raw_failure.request,
        raw_failure.sources,
    )
    chains.append(
        _chain_from_admission(
            raw_failure.protocol_result,
            raw_failure.lineage_result,
            rejected_admission,
            "m03_03_unreleasable",
        )
    )

    base = build_genuine_chain()
    quality_failure = compute_protein_inference_quality(
        m0304_evidence._request_with_ledger(
            m0304_evidence.build_scenario().request,
            ledger_updates={
                "admission_result_digest": sha256_digest({"m0308": "quality-quarantine"})
            },
        )
    )
    chains.append(
        _downstream_chain(
            protocol=base.protocol,
            identity=base.identity,
            ingestion=base.ingestion,
            quality=quality_failure,
            label="m03_04_quarantined",
        )
    )

    artifact_failure = detect_protein_inference_artifacts(
        m0305_evidence._with_signal(
            m0305_evidence.build_scenario().request,
            ProteinInferenceArtifactSignalCode.NONUNIQUE_MAPPING,
            supporting_count=3,
        )
    )
    chains.append(
        _downstream_chain(
            protocol=base.protocol,
            identity=base.identity,
            ingestion=base.ingestion,
            quality=base.quality,
            artifact=artifact_failure,
            label="m03_05_quarantined",
        )
    )

    artifact_request = m0305_evidence.build_scenario_request()
    mismatched_ledger = m0305_evidence._ledger(
        artifact_request,
        quality_result_digest=sha256_digest({"m0308": "m0306-safe-failure-artifact"}),
    )
    harmonization_artifact = detect_protein_inference_artifacts(
        artifact_request.model_copy(update={"evidence_ledger": mismatched_ledger})
    )
    harmonization_failure = m0307_evidence._harmonization_from_artifact_result(
        harmonization_artifact,
        "m03_06_quarantined",
    )
    chains.append(
        _downstream_chain(
            protocol=base.protocol,
            identity=base.identity,
            ingestion=base.ingestion,
            quality=base.quality,
            artifact=harmonization_artifact,
            harmonization=harmonization_failure,
            label="m03_06_quarantined",
        )
    )

    support_template = m0307_evidence.build_scenario()
    specimen = next(
        item
        for item in support_template.request.declared_facts
        if item.dimension is ProteinInferenceSupportDimension.SPECIMEN
    )
    missing = m0307_evidence._fact_with(
        specimen,
        state=ProteinInferenceDeclaredSupportState.MISSING,
        values=(),
    )
    support_failure = route_protein_inference_support(
        m0307_evidence._request_with(
            support_template.request,
            "m0308-support-abstention",
            facts=m0307_evidence._replace_fact(
                support_template.request,
                ProteinInferenceSupportDimension.SPECIMEN,
                missing,
            ),
        )
    )
    chains.append(
        GenuineProteinInferenceChain(
            protocol=base.protocol,
            identity=base.identity,
            ingestion=base.ingestion,
            quality=base.quality,
            artifact_detection=base.artifact_detection,
            harmonization=base.harmonization,
            support_route=support_failure,
        )
    )
    return tuple(chains)


def _stage_disposition_checks(scenario: Scenario) -> list[EvalCheck]:
    del scenario
    case_ids = (
        "m03_01_quarantined",
        "m03_02_unreleasable",
        "m03_03_unreleasable",
        "m03_04_quarantined",
        "m03_05_quarantined",
        "m03_06_quarantined",
        "m03_07_abstained",
    )
    output: list[EvalCheck] = []
    for index, (case_id, chain) in enumerate(
        zip(case_ids, _nonreleasable_chains(), strict=True),
        start=1,
    ):
        fixture = _sign_fixture(_unsigned_fixture(chain=chain))
        verifier = DeterministicNonCryptographicVerifier()
        built = build_protein_inference_release(
            fixture.request,
            fixture.artifacts,
            fixture.stages,
            verifier,
        )
        expected_module = ProteinInferenceStageModuleId(f"GLIO-PROTEOGEN-M03-{index:02d}")
        reason_modules = {item.stage_module_id for item in built.result.quarantine_reasons}
        output.append(
            _scenario(
                case_id,
                passed=(
                    built.result.disposition is ProteinInferenceReleaseDisposition.QUARANTINED
                    and built.package_bytes is None
                    and not verifier.calls
                    and expected_module in reason_modules
                ),
                detail=(
                    f"public_build={built.result.disposition.value};"
                    f"reason_stages={sorted(item.value for item in reason_modules if item)};"
                    f"verifier_calls={len(verifier.calls)}"
                ),
            )
        )
    return output


def _expect_input_error(
    case_id: str,
    scenario: Scenario,
    *,
    artifacts: Mapping[str, object] | None = None,
    stages: Mapping[str, object] | None = None,
    expected: ProteinInferenceReleaseInputErrorCode,
) -> EvalCheck:
    caught: ProteinInferenceReleaseInputErrorCode | None = None
    try:
        build_protein_inference_release(
            scenario.request,
            artifacts if artifacts is not None else scenario.artifacts,
            stages if stages is not None else scenario.stages,
            DeterministicNonCryptographicVerifier(),
        )
    except ProteinInferenceReleaseInputError as error:
        caught = error.code
    return _scenario(case_id, passed=caught is expected, detail=f"error={caught}")


def _chain_checks(scenario: Scenario) -> list[EvalCheck]:
    donors = _nonreleasable_chains()
    module_cases = (
        (
            "identity_lineage_substitution",
            "GLIO-PROTEOGEN-M03-02",
            donors[1].identity,
        ),
        (
            "predecessor_digest_substitution",
            "GLIO-PROTEOGEN-M03-03",
            donors[2].ingestion,
        ),
        (
            "harmonization_support_substitution",
            "GLIO-PROTEOGEN-M03-06",
            donors[5].harmonization,
        ),
    )
    checks: list[EvalCheck] = []
    for case_id, module, donor in module_cases:
        stage_bytes = canonical_json_bytes(donor)
        role = ProteinInferenceReleaseArtifactRole(
            {
                "GLIO-PROTEOGEN-M03-02": "m03_02_identity_lineage",
                "GLIO-PROTEOGEN-M03-03": "m03_03_raw_ingestion",
                "GLIO-PROTEOGEN-M03-06": "m03_06_harmonization",
            }[module]
        )
        declarations = tuple(
            item.model_copy(
                update={
                    "reference": item.reference.model_copy(
                        update={
                            "artifact_id": _stage_artifact_id(donor),
                            "digest": sha256_bytes(stage_bytes),
                        }
                    ),
                    "declared_size": len(stage_bytes),
                }
            )
            if item.role is role
            else item
            for item in scenario.request.artifacts
        )
        request = _request_with(scenario.request, artifacts=declarations)
        artifacts = dict(scenario.artifacts)
        artifact_path = next(item.path for item in declarations if item.role is role)
        artifacts[artifact_path] = stage_bytes
        stages = dict(scenario.stages)
        stages[module] = donor
        verifier = DeterministicNonCryptographicVerifier()
        caught: ProteinInferenceReleaseInputErrorCode | None = None
        try:
            build_protein_inference_release(
                request,
                artifacts,
                stages,
                verifier,
            )
        except ProteinInferenceReleaseInputError as error:
            caught = error.code
        checks.append(
            _scenario(
                case_id,
                passed=(
                    caught is ProteinInferenceReleaseInputErrorCode.CHAIN_MISMATCH
                    and not verifier.calls
                ),
                detail=f"error={caught};verifier_calls={len(verifier.calls)}",
            )
        )
    return checks


def _integrity_input_checks(scenario: Scenario) -> list[EvalCheck]:
    first = next(iter(scenario.artifacts))
    digest_tampered = dict(scenario.artifacts)
    flipped = bytearray(digest_tampered[first])
    flipped[0] ^= 1
    digest_tampered[first] = bytes(flipped)
    size_tampered = dict(scenario.artifacts)
    size_tampered[first] += b"tamper"
    mismatched_declarations = tuple(
        item.model_copy(
            update={
                "reference": item.reference.model_copy(
                    update={"digest": sha256_digest({"m0308": "declared-mismatch"})}
                )
            }
        )
        if item.path == first
        else item
        for item in scenario.request.artifacts
    )
    declaration_scenario = Scenario(
        ProteinInferenceReleaseFixture(
            _request_with(scenario.request, artifacts=mismatched_declarations),
            scenario.artifacts,
            scenario.stages,
        ),
        DeterministicNonCryptographicVerifier(),
    )
    missing = dict(scenario.artifacts)
    missing.pop(first)
    extra = dict(scenario.artifacts)
    extra["undeclared.json"] = b"{}"
    return [
        _expect_input_error(
            "artifact_byte_digest_mismatch",
            scenario,
            artifacts=digest_tampered,
            expected=ProteinInferenceReleaseInputErrorCode.ARTIFACT_DIGEST_MISMATCH,
        ),
        _expect_input_error(
            "artifact_declared_digest_mismatch",
            declaration_scenario,
            expected=ProteinInferenceReleaseInputErrorCode.ARTIFACT_DIGEST_MISMATCH,
        ),
        _expect_input_error(
            "artifact_size_mismatch",
            scenario,
            artifacts=size_tampered,
            expected=ProteinInferenceReleaseInputErrorCode.ARTIFACT_SIZE_MISMATCH,
        ),
        _expect_input_error(
            "missing_artifact_member",
            scenario,
            artifacts=missing,
            expected=ProteinInferenceReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH,
        ),
        _expect_input_error(
            "undeclared_artifact_member",
            scenario,
            artifacts=extra,
            expected=ProteinInferenceReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH,
        ),
    ]


def _archive_bytes(members: tuple[PackageMember, ...]) -> bytes:
    target = io.BytesIO()
    with tarfile.open(fileobj=target, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for member in members:
            info = tarfile.TarInfo(member.path)
            info.size = len(member.content)
            info.mtime = 0
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(member.content))
    return target.getvalue()


def _archive_safety_checks(scenario: Scenario) -> list[EvalCheck]:
    result, package = _build(scenario)
    if package is None:
        raise _ScenarioClosureError
    members = inspect_canonical_ustar(package)
    malformed = (
        (
            "duplicate_canonical_member",
            (
                members[0],
                PackageMember(members[0].path, members[1].content),
                *members[2:],
            ),
        ),
        (
            "unsafe_member_path",
            (PackageMember("../escape.json", members[0].content), *members[1:]),
        ),
        (
            "archive_member_alias",
            (PackageMember(members[0].path.upper(), members[0].content), *members[1:]),
        ),
    )
    checks: list[EvalCheck] = []
    for case_id, items in malformed:
        hostile_package = _archive_bytes(items)
        descriptor = result.package_descriptor
        if descriptor is None:
            raise _ScenarioClosureError
        hostile_descriptor = descriptor.model_copy(
            update={
                "byte_size": len(hostile_package),
                "digest": sha256_bytes(hostile_package),
            }
        )
        candidate = result.model_copy(update={"package_descriptor": hostile_descriptor})
        payload = candidate.model_dump(mode="python")
        payload["result_digest"] = result_payload_digest(payload)
        hostile_result = ProteinInferenceReleaseResult.model_validate(payload, strict=True)
        verifier = DeterministicNonCryptographicVerifier()
        verification = verify_protein_inference_release(
            hostile_result,
            hostile_package,
            verifier,
        )
        expected = (
            {
                ProteinInferencePackageVerificationReason.PACKAGE_INVALID,
                ProteinInferencePackageVerificationReason.INVENTORY_MISMATCH,
            }
            if case_id == "duplicate_canonical_member"
            else {ProteinInferencePackageVerificationReason.INVENTORY_MISMATCH}
        )
        checks.append(
            _scenario(
                case_id,
                passed=(
                    not verification.verified
                    and verification.reason_code in expected
                    and not verifier.calls
                ),
                detail=(
                    f"reason={verification.reason_code.value};verifier_calls={len(verifier.calls)}"
                ),
            )
        )
    return checks


def _signature_checks(scenario: Scenario) -> list[EvalCheck]:
    verified = DeterministicNonCryptographicVerifier()
    released = build_protein_inference_release(
        scenario.request,
        scenario.artifacts,
        scenario.stages,
        verified,
    )
    mismatch_signature = scenario.request.signature.model_copy(
        update={"claimed_statement_digest": sha256_digest("m0308-statement-mismatch")}
    )
    mismatch = build_protein_inference_release(
        _request_with(scenario.request, signature=mismatch_signature),
        scenario.artifacts,
        scenario.stages,
        DeterministicNonCryptographicVerifier(),
    )
    unavailable = build_protein_inference_release(
        scenario.request,
        scenario.artifacts,
        scenario.stages,
        _UnavailableVerifier(),
    )
    rejected_verifier = DeterministicNonCryptographicVerifier(accept=False)
    rejected = build_protein_inference_release(
        scenario.request,
        scenario.artifacts,
        scenario.stages,
        rejected_verifier,
    )
    unsupported_payload = scenario.request.model_dump(mode="python")
    signature = cast("dict[str, object]", unsupported_payload["signature"])
    signature["algorithm"] = "sha1_rsa"
    unsupported = False
    try:
        BuildProteinInferenceReleaseRequest.model_validate(unsupported_payload, strict=True)
    except ValidationError:
        unsupported = True
    malformed_payload = scenario.request.model_dump(mode="python")
    cast("dict[str, object]", malformed_payload["signature"])["signature_value"] = ""
    malformed = _validation_rejected(malformed_payload)
    replay_ok = False
    if released.package_bytes is not None:
        receipt_members = inspect_canonical_ustar(released.package_bytes)
        receipt = next(
            item.content for item in receipt_members if item.path == M0308_SIGNATURE_RECEIPT_PATH
        )
        replay = build_protein_inference_release(
            scenario.request,
            scenario.artifacts,
            scenario.stages,
            DeterministicNonCryptographicVerifier(),
        )
        replay_receipt = next(
            item.content
            for item in inspect_canonical_ustar(cast("bytes", replay.package_bytes))
            if item.path == M0308_SIGNATURE_RECEIPT_PATH
        )
        replay_ok = receipt == replay_receipt and replay.package_bytes == released.package_bytes
    return [
        _scenario(
            "verified_statement_releases",
            passed=(
                released.result.disposition is ProteinInferenceReleaseDisposition.RELEASED
                and released.package_bytes is not None
                and len(verified.calls) == 1
                and replay_ok
            ),
            detail=f"calls={len(verified.calls)};noncircular_replay={replay_ok}",
        ),
        _scenario(
            "statement_digest_mismatch_quarantines",
            passed=(
                mismatch.result.disposition is ProteinInferenceReleaseDisposition.QUARANTINED
                and mismatch.package_bytes is None
                and not mismatch.result.signature_verification.verified
            ),
            detail=mismatch.result.signature_verification.reason_code.value,
        ),
        _scenario(
            "unsupported_signature_algorithm_rejected",
            passed=unsupported,
            detail=f"validation_rejected={unsupported}",
        ),
        _scenario(
            "verifier_unavailable_quarantines",
            passed=(
                unavailable.result.disposition is ProteinInferenceReleaseDisposition.QUARANTINED
                and unavailable.package_bytes is None
            ),
            detail=unavailable.result.signature_verification.reason_code.value,
        ),
        _scenario(
            "verifier_rejected_quarantines",
            passed=(
                rejected.result.disposition is ProteinInferenceReleaseDisposition.QUARANTINED
                and rejected.package_bytes is None
                and len(rejected_verifier.calls) == 1
            ),
            detail=rejected.result.signature_verification.reason_code.value,
        ),
        _scenario(
            "malformed_signature_value_rejected",
            passed=malformed,
            detail=f"strict_rejected={malformed}",
        ),
    ]


def _validation_rejected(payload: dict[str, object]) -> bool:
    try:
        BuildProteinInferenceReleaseRequest.model_validate(payload, strict=True)
    except ValidationError:
        return True
    return False


def _strict_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    integer = request.model_dump(mode="python")
    cast("dict[str, object]", integer["policy"])["max_artifact_bytes"] = "33554432"
    boolean = request.model_dump(mode="python")
    cast("dict[str, object]", boolean["context"])["actor_id"] = True
    unknown = request.model_dump(mode="python")
    unknown["future_field"] = "forbidden"
    enumeration = request.model_dump(mode="python")
    cast("dict[str, object]", enumeration["signature"])["algorithm"] = "md5"
    stale = request.model_dump(mode="python")
    stale_policy = cast("dict[str, object]", stale["policy"])
    stale_policy["max_total_bytes"] = cast("int", stale_policy["max_total_bytes"]) - 1
    duplicate = request.model_dump(mode="python")
    software = list(cast("tuple[object, ...]", duplicate["software_versions"]))
    software[1] = software[0]
    duplicate["software_versions"] = tuple(software)
    return [
        _scenario(
            "coerced_integer_rejected",
            passed=_validation_rejected(integer),
            detail="strict integer",
        ),
        _scenario(
            "coerced_boolean_rejected",
            passed=_validation_rejected(boolean),
            detail="strict boolean",
        ),
        _scenario(
            "unknown_field_rejected",
            passed=_validation_rejected(unknown),
            detail="extra forbid",
        ),
        _scenario(
            "invalid_enumeration_rejected",
            passed=_validation_rejected(enumeration),
            detail="closed signature algorithm",
        ),
        _scenario(
            "stale_derived_digest_rejected",
            passed=_validation_rejected(stale),
            detail="request/context identity closure",
        ),
        _scenario(
            "semantic_duplicate_rejected",
            passed=_validation_rejected(duplicate),
            detail="duplicate software identity",
        ),
    ]


_OPAQUE_OUTPUT_FIELDS: Final = {
    "activity_id": "activity.m0308",
    "release_result_id": "result.m0308",
    "release_id": "release",
    "policy_id": "policy",
    "software_id": "software",
    "reference_id": "reference",
    "build_id": "build",
    "signer_id": "signer",
    "key_id": "key",
    "verifier_id": "verifier",
    "allowed_verifier_ids": "verifier",
    "reviewed_by": "reviewer",
    "request_id": "request",
    "actor_id": "actor",
    "decision_id": "decision",
    "consent_decision_id": "decision",
    "artifact_id": "evidence",
}


def _recursive_privacy_check(scenario: Scenario) -> EvalCheck:
    result, package = _build(scenario)
    forbidden = {
        "raw_spectra",
        "peptide_rows",
        "complex_activity_score",
        "protein_subtype_score",
        "proteotype",
        "treatment_recommendation",
        "private_key",
        "signing_secret",
    }
    payload = result.model_dump(mode="json")
    rendered = json.dumps(payload, sort_keys=True).casefold()
    values: list[tuple[str, str]] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in _OPAQUE_OUTPUT_FIELDS and isinstance(child, str):
                    values.append((key, child))
                elif key in _OPAQUE_OUTPUT_FIELDS and isinstance(child, list):
                    values.extend((key, item) for item in child if isinstance(item, str))
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    opaque = all(
        re.fullmatch(rf"{re.escape(namespace)}\.[0-9a-f]{{64}}", value) is not None
        or (key == "artifact_id" and value.startswith(("result.m03", "route.", "parent.")))
        for key, value in values
        for namespace in (_OPAQUE_OUTPUT_FIELDS[key],)
        if value is not None
    )
    return _scenario(
        "recursive_output_boundary",
        passed=(
            package is not None
            and result.emits_complex_activity is False
            and result.infers_identity is False
            and result.infers_protein is False
            and result.infers_proteoform is False
            and result.infers_kinase_activity is False
            and not any(token in rendered for token in forbidden)
            and opaque
        ),
        detail=f"opaque_identifiers={len(values)};package_bytes_not_in_result=True",
    )


def _denied_candidate(request: BuildProteinInferenceReleaseRequest) -> dict[str, object]:
    payload = request.model_dump(mode="python")
    context = cast("dict[str, object]", payload["context"])
    references = cast("dict[str, object]", context["references"])
    consent = cast("dict[str, object]", references["consent"])
    consent["state"] = "withheld"
    return payload


def _authorization_and_capacity_checks(  # noqa: C901, PLR0912, PLR0915 - exact cap matrix.
    scenario: Scenario,
) -> list[EvalCheck]:
    hostile_stages = _UnreadableMapping("stages")
    chain_blocked = False
    try:
        build_protein_inference_release(
            _denied_candidate(scenario.request),
            scenario.artifacts,
            hostile_stages,
            DeterministicNonCryptographicVerifier(),
        )
    except ProteinInferenceReleaseAuthorizationError:
        chain_blocked = True

    hostile_artifacts = _UnreadableMapping("artifacts")
    artifacts_blocked = False
    try:
        build_protein_inference_release(
            _denied_candidate(scenario.request),
            hostile_artifacts,
            scenario.stages,
            DeterministicNonCryptographicVerifier(),
        )
    except ProteinInferenceReleaseAuthorizationError:
        artifacts_blocked = True

    recovered, recovered_package = _build(
        Scenario(
            scenario.fixture,
            DeterministicNonCryptographicVerifier(),
        )
    )
    maximum = build_maximum_scenario()
    maximum_result, maximum_package = _build(maximum)
    excess_axes: dict[str, bool] = {}

    excess = maximum.request.model_dump(mode="python")
    excess["software_versions"] = _software_versions(M0308_MAX_SOFTWARE_VERSIONS + 1)
    excess_axes["software_versions"] = _validation_rejected(excess)

    excess = maximum.request.model_dump(mode="python")
    excess["reference_versions"] = _reference_versions(M0308_MAX_REFERENCE_VERSIONS + 1)
    excess_axes["reference_versions"] = _validation_rejected(excess)

    excess = scenario.request.model_dump(mode="python")
    excess["artifacts"] = (*scenario.request.artifacts, scenario.request.artifacts[0])
    excess_axes["artifact_count"] = _validation_rejected(excess)

    policy_payload = scenario.request.policy.model_dump(mode="python")
    policy_payload["allowed_signature_algorithms"] = (
        ProteinInferenceSignatureAlgorithm.ED25519,
    ) * (M0308_MAX_SIGNATURE_ALGORITHMS + 1)
    try:
        ProteinInferenceReleasePolicy.model_validate(policy_payload, strict=True)
    except ValidationError:
        excess_axes["signature_algorithms"] = True
    else:
        excess_axes["signature_algorithms"] = False

    policy_payload = scenario.request.policy.model_dump(mode="python")
    policy_payload["allowed_verifier_ids"] = tuple(
        _oid("verifier", {"excess": index}) for index in range(M0308_MAX_VERIFIER_IDS + 1)
    )
    try:
        ProteinInferenceReleasePolicy.model_validate(policy_payload, strict=True)
    except ValidationError:
        excess_axes["verifier_ids"] = True
    else:
        excess_axes["verifier_ids"] = False

    signature_payload = scenario.request.signature.model_dump(mode="python")
    signature_payload["signature_value"] = "A" * (M0308_MAX_SIGNATURE_VALUE_CHARS + 1)
    try:
        ExternalProteinInferenceSignature.model_validate(signature_payload, strict=True)
    except ValidationError:
        excess_axes["signature_value_chars"] = True
    else:
        excess_axes["signature_value_chars"] = False

    artifact_payload = scenario.request.artifacts[0].model_dump(mode="python")
    artifact_payload["declared_size"] = M0308_MAX_ARTIFACT_BYTES + 1
    try:
        ProteinInferenceReleaseArtifact.model_validate(artifact_payload, strict=True)
    except ValidationError:
        excess_axes["single_artifact_bytes"] = True
    else:
        excess_axes["single_artifact_bytes"] = False

    total_payload = scenario.request.model_dump(mode="python")
    total_artifacts = cast("tuple[dict[str, object], ...]", total_payload["artifacts"])
    total_sizes = (
        M0308_MAX_ARTIFACT_BYTES,
        M0308_MAX_ARTIFACT_BYTES - 5,
        1,
        1,
        1,
        1,
        1,
        1,
    )
    total_payload["artifacts"] = tuple(
        {**artifact, "declared_size": size}
        for artifact, size in zip(total_artifacts, total_sizes, strict=True)
    )
    excess_axes["total_artifact_bytes"] = _validation_rejected(total_payload)

    for field, limit in (
        ("max_artifact_bytes", M0308_MAX_ARTIFACT_BYTES),
        ("max_total_bytes", M0308_MAX_TOTAL_ARTIFACT_BYTES),
    ):
        policy_payload = scenario.request.policy.model_dump(mode="python")
        policy_payload[field] = limit + 1
        try:
            ProteinInferenceReleasePolicy.model_validate(policy_payload, strict=True)
        except ValidationError:
            excess_axes[f"policy_{field}"] = True
        else:
            excess_axes[f"policy_{field}"] = False

    cap_verifier = DeterministicNonCryptographicVerifier()
    oversize_artifacts = _UnreadableMapping("oversize-request-artifacts")
    oversize_stages = _UnreadableMapping("oversize-request-stages")
    raw_request_rejected = False
    try:
        M0308Plugin(M0308Service(cap_verifier)).validate(
            ProteinInferenceReleaseSubmission(
                b" " * (M0308_MAX_CANONICAL_REQUEST_BYTES + 1),
                oversize_artifacts,
                oversize_stages,
            )
        )
    except Exception:  # noqa: BLE001 - any typed bounded-parser rejection is sufficient.
        raw_request_rejected = True
    excess_axes["canonical_request_bytes"] = (
        raw_request_rejected
        and not cap_verifier.calls
        and oversize_artifacts.traversals == 0
        and oversize_stages.traversals == 0
    )

    package_verifier = DeterministicNonCryptographicVerifier()
    package_verification = verify_protein_inference_release(
        recovered,
        bytes(M0308_MAX_PACKAGE_BYTES + 1),
        package_verifier,
    )
    excess_axes["package_bytes"] = (
        package_verification.reason_code
        is ProteinInferencePackageVerificationReason.DESCRIPTOR_MISMATCH
        and not package_verifier.calls
    )
    excess_rejected = all(excess_axes.values())
    return [
        _scenario(
            "consent_denied_before_hostile_chain",
            passed=chain_blocked and hostile_stages.traversals == 0,
            detail=f"blocked={chain_blocked};traversals={hostile_stages.traversals}",
        ),
        _scenario(
            "consent_denied_before_hostile_artifacts",
            passed=artifacts_blocked and hostile_artifacts.traversals == 0,
            detail=f"blocked={artifacts_blocked};traversals={hostile_artifacts.traversals}",
        ),
        _scenario(
            "typed_blocked_recovery",
            passed=(
                chain_blocked
                and recovered.disposition is ProteinInferenceReleaseDisposition.RELEASED
                and recovered_package is not None
            ),
            detail=f"blocked_then={recovered.disposition.value}",
        ),
        _scenario(
            "maximum_accepted_shape",
            passed=(
                len(maximum.request.software_versions) == M0308_MAX_SOFTWARE_VERSIONS
                and len(maximum.request.reference_versions) == M0308_MAX_REFERENCE_VERSIONS
                and maximum_result.disposition is ProteinInferenceReleaseDisposition.RELEASED
                and maximum_package is not None
            ),
            detail=(
                f"software={len(maximum.request.software_versions)};"
                f"reference={len(maximum.request.reference_versions)}"
            ),
        ),
        _scenario(
            "first_excess_rejected_before_archive",
            passed=excess_rejected,
            detail=(
                f"axes={len(excess_axes)};failed="
                f"{sorted(name for name, passed in excess_axes.items() if not passed)}"
            ),
        ),
    ]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    corpus = _load_corpus()
    groups = cast("list[dict[str, object]]", corpus["scenario_groups"])
    declared = [case_id for group in groups for case_id in cast("list[str]", group["case_ids"])]
    scenario = build_scenario()
    scenario_checks = [
        _canonical_check(scenario),
        _semantic_reorder_check(scenario),
        *_stage_disposition_checks(scenario),
        *_chain_checks(scenario),
        *_integrity_input_checks(scenario),
        *_archive_safety_checks(scenario),
        *_signature_checks(scenario),
        *_strict_checks(scenario),
        _recursive_privacy_check(scenario),
        *_authorization_and_capacity_checks(scenario),
    ]
    executed = [item.name.removeprefix("scenario.") for item in scenario_checks]
    declared_duplicates = sorted({item for item in declared if declared.count(item) > 1})
    executed_duplicates = sorted({item for item in executed if executed.count(item) > 1})
    missing = sorted(set(declared) - set(executed))
    extra = sorted(set(executed) - set(declared))
    coverage = EvalCheck(
        "coverage.exact_declared_executable_case_set",
        (
            len(declared) == len(executed) == EXPECTED_CASE_COUNT
            and not declared_duplicates
            and not executed_duplicates
            and not missing
            and not extra
        ),
        (
            f"declared={len(declared)};executed={len(executed)};"
            f"missing={missing};extra={extra};"
            f"declared_duplicates={declared_duplicates};"
            f"executed_duplicates={executed_duplicates}"
        ),
    )
    checks = [_corpus_check(), *scenario_checks, coverage]
    report = {
        "module_id": MODULE_ID,
        "contract_version": M0308_CONTRACT_VERSION,
        "status": "PASS" if all(item.passed for item in checks) else "FAIL",
        "checks": [asdict(item) for item in checks],
        "declared_case_count": len(declared),
        "executed_case_count": len(executed),
        "missing_case_ids": missing,
        "extra_case_ids": extra,
        "duplicate_declared_case_ids": declared_duplicates,
        "duplicate_executed_case_ids": executed_duplicates,
        "passed_case_count": sum(item.passed for item in scenario_checks),
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    sys.stdout.write(rendered + "\n")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
