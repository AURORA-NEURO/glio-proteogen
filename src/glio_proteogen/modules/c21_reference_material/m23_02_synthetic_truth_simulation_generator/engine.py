"""Deterministic, caller-declared M23-02 synthetic truth generation runtime."""

# ruff: noqa: TRY003

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m23_02 import (
    M2302_CONTRACT_VERSION,
    M2302_EVIDENCE_CLAIM,
    M2302_MODULE_ID,
    FixtureKind,
    GenerateVariantPeptideSyntheticTruthRequest,
    GenerationManifest,
    GenerationStatus,
    SyntheticTruthCase,
    SyntheticTruthCorpus,
    TruthRepresentation,
    VariantPeptideSyntheticTruthResult,
    canonical_request_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final = TypeAdapter(GenerateVariantPeptideSyntheticTruthRequest)
_RESULT_ADAPTER: Final = TypeAdapter(VariantPeptideSyntheticTruthResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_EXPECTED_CONTROLS: Final = {
    "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
    "identity_lineage": IdentityLineageState.RESOLVED.value,
    "provenance": UpstreamDecisionState.ACCEPTED.value,
    "consent": ConsentState.GRANTED.value,
    "quality": UpstreamDecisionState.ACCEPTED.value,
    "support": UpstreamDecisionState.ACCEPTED.value,
    "intended_use": UpstreamDecisionState.ACCEPTED.value,
}
_LIMITATIONS: Final = (
    Limitation(
        code="m2302_caller_declared_upstream",
        statement=(
            "M23-01 is retained as an opaque caller-declared artifact; issuer authority and "
            "source content are not authenticated or traversed."
        ),
    ),
    Limitation(
        code="m2302_analytic_scope",
        statement=(
            "Synthetic values are reproducibility fixtures, not biological measurements or "
            "clinical evidence."
        ),
    ),
    Limitation(
        code="m2302_provisional_abi",
        statement="The M23-02 ABI remains provisional pending Platform engineering confirmation.",
    ),
)


class M2302AuthorizationError(ValueError):
    """Caller-declared controls do not authorize synthetic truth generation."""


class M2302EvaluationError(ValueError):
    """A synthetic truth request failed safe validation."""


class M2302ReplayError(ValueError):
    """A synthetic truth result failed canonical replay verification."""


def _member(candidate: object, name: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(name)
    return getattr(candidate, name, None)


def _state(candidate: object) -> str | None:
    value = _member(candidate, "state")
    state = getattr(value, "value", value)
    return state if isinstance(state, str) else None


def preflight_m2302_authorization(candidate: object) -> None:
    """Reject denied or malformed controls before synthetic fixture generation."""

    try:
        references = _member(_member(candidate, "context"), "references")
        authorized = all(
            _state(_member(references, role)) == expected
            for role, expected in _EXPECTED_CONTROLS.items()
        )
    except Exception as error:
        raise M2302AuthorizationError("M23-02 controls are malformed") from error
    if not authorized:
        raise M2302AuthorizationError("M23-02 requires all seven accepted controls")


def _evidence(
    request: GenerateVariantPeptideSyntheticTruthRequest,
) -> tuple[EvidenceReference, ...]:
    artifacts = (
        request.upstream_result,
        *request.source_artifacts,
        *(item.reference for item in request.configuration.evidence),
    )
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M2302_EVIDENCE_CLAIM)
        for artifact in unique.values()
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M23-02 emits locked synthetic truth, not a scientific estimate.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=("Values are sensitive to the locked generator seed and fixture kind.",),
    )


def _provenance(
    request: GenerateVariantPeptideSyntheticTruthRequest,
    request_digest: str,
) -> ProvenanceRecord:
    refs = request.context.references
    controls = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.CONSENT, refs.consent),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    )
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=decision.decision_id,
            state=_state(decision) or "unknown",
            policy_version=decision.policy_version,
            evidence_digest=decision.evidence.digest,
            subject_digest=getattr(decision, "binding_digest", None),
        )
        for role, decision in controls
    )
    return ProvenanceRecord(
        activity_id=f"m2302.activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M2302_MODULE_ID,
        module_version=M2302_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            dict.fromkeys(
                (
                    request_digest,
                    request.upstream_result.digest,
                    *(artifact.digest for artifact in request.source_artifacts),
                )
            )
        ),
        configuration_digest=request.configuration.evidence[0].reference.digest
        if request.configuration.evidence
        else request.source_artifacts[0].digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


def _case(kind: FixtureKind, index: int, seed: int) -> SyntheticTruthCase:
    value = seed + index
    return SyntheticTruthCase(
        case_id=f"case.m2302.generated.{index}",
        fixture_kind=kind,
        representation=(
            TruthRepresentation.ANALYTIC
            if kind in {FixtureKind.NORMAL, FixtureKind.EDGE}
            else TruthRepresentation.SEMI_SYNTHETIC
        ),
        seed=value,
        expected_features=("variant_peptide.abundance", "variant_peptide.support"),
        truth_values=(f"{value}.0", f"{value * 2}.0"),
        perturbations=(kind.value,),
    )


def _corpus(request: GenerateVariantPeptideSyntheticTruthRequest) -> SyntheticTruthCorpus:
    kinds = tuple(FixtureKind)
    cases = tuple(
        _case(kinds[index % len(kinds)], index, request.configuration.seed)
        for index in range(request.requested_case_count)
    )
    manifest = GenerationManifest(
        manifest_id="manifest.m2302.generated",
        version=request.configuration.version,
        configuration=request.configuration,
        case_ids=tuple(item.case_id for item in cases),
        reproducibility_digest=sha256_digest(
            {
                "configuration": request.configuration.model_dump(mode="json"),
                "cases": [item.model_dump(mode="json") for item in cases],
            }
        ),
        fixture_summary=tuple(
            f"{kind.value}:{sum(item.fixture_kind is kind for item in cases)}" for kind in kinds
        ),
        evidence=_evidence(request),
    )
    return SyntheticTruthCorpus(
        corpus_id="corpus.m2302.generated",
        version=request.configuration.version,
        cases=cases,
        manifest=manifest,
        source_artifacts=request.source_artifacts,
        evidence=_evidence(request),
    )


class M2302Engine:
    """Stateless deterministic synthetic truth generator."""

    def validate_request(self, candidate: object) -> GenerateVariantPeptideSyntheticTruthRequest:
        preflight_m2302_authorization(candidate)
        try:
            return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
        except Exception as error:
            raise M2302EvaluationError("M23-02 request is invalid") from error

    def generate(self, candidate: object) -> VariantPeptideSyntheticTruthResult:
        request = self.validate_request(candidate)
        request_digest = canonical_request_digest(request)
        corpus = _corpus(request)
        payload: dict[str, Any] = {
            "output_type": "variant_peptide_synthetic_truth",
            "result_id": result_identifier(request),
            "result_version": M2302_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": GenerationStatus.GENERATED,
            "corpus": corpus,
            "manifest": corpus.manifest,
            "findings": (),
            "abstention_reason": None,
            "parent_target": "variant peptide",
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m2302_generation_supported",
                rationale="All five locked fixture kinds are generated deterministically.",
            ),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request, request_digest),
            "evidence": _evidence(request),
            "limitations": _LIMITATIONS,
            "human_review_required": False,
        }
        provisional = VariantPeptideSyntheticTruthResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        try:
            return _RESULT_ADAPTER.validate_python(payload, strict=True)
        except Exception as error:
            raise M2302EvaluationError("M23-02 result construction failed safely") from error

    def replay(self, result: object) -> VariantPeptideSyntheticTruthResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M2302ReplayError("M23-02 result is invalid") from error
        if validated.result_digest != result_payload_digest(validated):
            raise M2302ReplayError("M23-02 result payload digest mismatch")
        expected = self.generate(validated.request)
        if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
            raise M2302ReplayError("M23-02 deterministic replay mismatch")
        return validated


def generate_variant_peptide_synthetic_truth(
    candidate: object,
) -> VariantPeptideSyntheticTruthResult:
    """Public stateless M23-02 generation entry point."""

    return M2302Engine().generate(candidate)


__all__ = [
    "M2302AuthorizationError",
    "M2302Engine",
    "M2302EvaluationError",
    "M2302ReplayError",
    "generate_variant_peptide_synthetic_truth",
    "preflight_m2302_authorization",
]
