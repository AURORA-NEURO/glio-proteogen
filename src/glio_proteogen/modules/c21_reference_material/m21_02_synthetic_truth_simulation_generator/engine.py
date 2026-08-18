"""Deterministic, metadata-only M21-02 synthetic truth generation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_02.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.contracts.m21_02.v1 import (
    M2102_CONTRACT_VERSION,
    M2102_MODULE_ID,
    ComplexActivitySyntheticTruthResult,
    FixtureKind,
    GenerateComplexActivitySyntheticTruthRequest,
    GenerationManifest,
    GenerationStatus,
    SyntheticTruthCase,
    SyntheticTruthCorpus,
    TruthRepresentation,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    IdentityLineageReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final = TypeAdapter(GenerateComplexActivitySyntheticTruthRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "M21-02 generation requires accepted configuration, resolved identity, granted consent, "
    "accepted provenance/quality/support/intended-use controls"
)
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_upstream",
        statement=(
            "The M21-01 reference result is caller-declared; issuer authority and underlying "
            "laboratory execution are not authenticated or traversed."
        ),
    ),
    Limitation(
        code="synthetic_truth_boundary",
        statement=(
            "Generated values are deterministic fixture truth for validation and benchmarking; "
            "they are not biological measurements or a complex-activity estimate."
        ),
    ),
    Limitation(
        code="exclusive_scope",
        statement=(
            "KINOPHOS kinase ownership, generic all-omics fusion, treatment recommendation, "
            "identity inference and unsupported-to-negative conversion are outside this module."
        ),
    ),
)


class M2102AuthorizationError(ValueError):
    """Raised when caller-declared controls do not authorize generation."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2102ReplayError(ValueError):
    """Raised when a result fails canonical replay verification."""


class M2102Engine:
    """Generate and replay one deterministic synthetic-truth corpus."""

    __slots__ = ()

    def generate(self, request: object) -> ComplexActivitySyntheticTruthResult:
        preflight_m2102_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(validated.model_dump(mode="json")), strict=True
        )
        request_digest = canonical_request_digest(canonical)
        cases = _cases(canonical)
        manifest = _manifest(canonical, cases)
        corpus = SyntheticTruthCorpus(
            corpus_id="m2102.corpus." + request_digest.removeprefix("sha256:"),
            version=canonical.configuration.version,
            cases=cases,
            manifest=manifest,
            source_artifacts=canonical.source_artifacts,
            evidence=_evidence(canonical),
        )
        payload: dict[str, Any] = {
            "output_type": "complex_activity_synthetic_truth",
            "result_id": "m2102.result." + request_digest.removeprefix("sha256:"),
            "result_version": M2102_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": "sha256:" + ("0" * 64),
            "request": canonical,
            "status": GenerationStatus.GENERATED,
            "corpus": corpus,
            "manifest": manifest,
            "findings": (),
            "abstention_reason": None,
            "parent_target": "complex activity",
            "emits_parent": False,
            "support_decision": _support(),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(canonical, request_digest),
            "evidence": _evidence(canonical),
            "limitations": _LIMITATIONS,
            "human_review_required": False,
        }
        provisional = ComplexActivitySyntheticTruthResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return ComplexActivitySyntheticTruthResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )

    def replay(
        self,
        result: ComplexActivitySyntheticTruthResult,
    ) -> ComplexActivitySyntheticTruthResult:
        if result.request_digest != canonical_request_digest(result.request):
            raise M2102ReplayError("M21-02 result request digest mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M2102ReplayError("M21-02 result payload digest mismatch")  # noqa: TRY003
        return ComplexActivitySyntheticTruthResult.model_validate_json(
            canonical_json_bytes(result), strict=True
        )


def generate_complex_activity_synthetic_truth(
    request: object,
) -> ComplexActivitySyntheticTruthResult:
    """Public stateless M21-02 generation entry point."""

    return M2102Engine().generate(request)


def preflight_m2102_authorization(candidate: object) -> None:
    """Reject denied controls before reading generation configuration."""

    try:
        context = (
            candidate.context
            if isinstance(candidate, GenerateComplexActivitySyntheticTruthRequest)
            else candidate.get("context")
            if isinstance(candidate, Mapping)
            else None
        )
        references = _member(context, "references")
        expected = {
            "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
            "identity_lineage": IdentityLineageState.RESOLVED.value,
            "provenance": UpstreamDecisionState.ACCEPTED.value,
            "consent": ConsentState.GRANTED.value,
            "quality": UpstreamDecisionState.ACCEPTED.value,
            "support": UpstreamDecisionState.ACCEPTED.value,
            "intended_use": UpstreamDecisionState.ACCEPTED.value,
        }
        authorized = all(
            _state_value(_member(references, role)) == state for role, state in expected.items()
        )
    except Exception:  # noqa: BLE001 - fail closed at hostile mapping boundary.
        raise M2102AuthorizationError from None
    if not authorized:
        raise M2102AuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    actual = _member(candidate, "state")
    return getattr(actual, "value", actual)


def _cases(request: GenerateComplexActivitySyntheticTruthRequest) -> tuple[SyntheticTruthCase, ...]:
    kinds = request.configuration.requested_fixture_kinds
    source_evidence = _evidence(request)
    result: list[SyntheticTruthCase] = []
    for index in range(request.requested_case_count):
        kind = kinds[index % len(kinds)]
        representation = (
            TruthRepresentation.ANALYTIC
            if kind in {FixtureKind.NORMAL, FixtureKind.EDGE, FixtureKind.MISSING}
            else TruthRepresentation.SEMI_SYNTHETIC
        )
        perturbation = "none" if kind is FixtureKind.NORMAL else f"{kind.value}_boundary"
        result.append(
            SyntheticTruthCase(
                case_id=f"m2102.case.{index:04d}",
                fixture_kind=kind,
                representation=representation,
                seed=request.configuration.seed + index,
                expected_features=("complex_activity.signal", "complex_activity.support"),
                truth_values=(
                    f"truth:{request.configuration.seed}:{index}:known",
                    f"truth:{request.configuration.seed}:{index}:bounded",
                ),
                perturbations=(perturbation,),
                evidence=source_evidence,
            )
        )
    return tuple(result)


def _manifest(
    request: GenerateComplexActivitySyntheticTruthRequest,
    cases: tuple[SyntheticTruthCase, ...],
) -> GenerationManifest:
    case_ids = tuple(item.case_id for item in cases)
    summary = tuple(
        f"{kind.value}:{sum(item.fixture_kind is kind for item in cases)}"
        for kind in request.configuration.requested_fixture_kinds
    )
    digest = sha256_digest(
        {
            "configuration": request.configuration,
            "case_ids": case_ids,
            "fixture_summary": summary,
        }
    )
    return GenerationManifest(
        manifest_id="m2102.manifest." + canonical_request_digest(request).removeprefix("sha256:"),
        version=request.configuration.version,
        configuration=request.configuration,
        case_ids=case_ids,
        reproducibility_digest=digest,
        fixture_summary=summary,
        evidence=_evidence(request),
    )


def _support() -> SupportDecision:
    return SupportDecision(
        status=SupportStatus.SUPPORTED,
        reason_code="deterministic_synthetic_truth_generated",
        rationale=(
            "The caller-declared controls are accepted and every requested fixture is generated "
            "from the locked seed without reading raw scientific content."
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=f"M21-02 does not estimate {dimension} uncertainty from synthetic fixtures.",
        )

    return UncertaintyProfile(
        measurement=unavailable("measurement"),
        sampling=unavailable("sampling"),
        parameter=unavailable("parameter"),
        model_form=unavailable("model form"),
        identification=unavailable("identification"),
        support=unavailable("support"),
        transport=unavailable("transport"),
        sensitivity_notes=(
            "Synthetic truth is analytically recoverable under the locked seed; it is not a "
            "claim about biological measurement uncertainty.",
        ),
    )


def _evidence(
    request: GenerateComplexActivitySyntheticTruthRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared M21-02 source artifact; issuer authority is not authenticated.",
        )
        for artifact in request.source_artifacts
    )


def _provenance(
    request: GenerateComplexActivitySyntheticTruthRequest,
    request_digest: str,
) -> ProvenanceRecord:
    references = request.context.references
    controls = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage),
        (ControlRole.PROVENANCE, references.provenance),
        (ControlRole.CONSENT, references.consent),
        (ControlRole.QUALITY, references.quality),
        (ControlRole.SUPPORT, references.support),
        (ControlRole.INTENDED_USE, references.intended_use),
    )
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=decision.decision_id,
            state=str(decision.state.value),
            policy_version=decision.policy_version,
            evidence_digest=decision.evidence.digest,
            subject_digest=(
                decision.binding_digest if isinstance(decision, IdentityLineageReference) else None
            ),
        )
        for role, decision in controls
    )
    return ProvenanceRecord(
        activity_id="m2102.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2102_MODULE_ID,
        module_version=M2102_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            *tuple(artifact.digest for artifact in request.source_artifacts),
            sha256_digest(request.configuration),
        ),
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M2102AuthorizationError",
    "M2102Engine",
    "M2102ReplayError",
    "generate_complex_activity_synthetic_truth",
    "preflight_m2102_authorization",
]
