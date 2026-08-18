"""Deterministic, caller-declared M25-02 synthetic-truth generation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_02 import (
    M2502_CONTRACT_VERSION,
    M2502_EVIDENCE_CLAIM,
    M2502_MODULE_ID,
    FixtureKind,
    GenerateProteotypeSyntheticTruthRequest,
    GenerationManifest,
    GenerationStatus,
    ProteotypeSyntheticTruthResult,
    SyntheticTruthCase,
    SyntheticTruthCorpus,
    TruthRepresentation,
    canonical_request_digest,
    normalized_request,
    result_identifier,
    result_payload_digest,
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

_REQUEST_ADAPTER: Final = TypeAdapter(GenerateProteotypeSyntheticTruthRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "M25-02 generation requires accepted configuration, resolved identity, granted consent, "
    "accepted provenance/quality/support/intended-use controls"
)
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_synthetic_truth",
        statement=(
            "Fixture labels, analytic recoverability, seeds and source authority are caller-"
            "declared; issuer authority and scientific truth are not authenticated."
        ),
    ),
    Limitation(
        code="proteotype_parent_boundary",
        statement=(
            "The generator creates benchmark material for batch and missing-protein sensitivity "
            "but does not emit a proteotype or biological conclusion."
        ),
    ),
    Limitation(
        code="exclusive_scope",
        statement=(
            "Kinase ownership, generic all-omics fusion, treatment recommendation, identity "
            "inference and unsupported-to-negative conversion are outside this module."
        ),
    ),
)


class M2502AuthorizationError(ValueError):
    """Raised when caller-declared controls do not authorize execution."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2502ReplayError(ValueError):
    """Raised when an immutable M25-02 result fails replay closure."""


class M2502SyntheticTruthGenerator:
    """Generate, validate, and replay one deterministic synthetic-truth corpus."""

    __slots__ = ()

    def generate(self, request: object) -> ProteotypeSyntheticTruthResult:
        preflight_m2502_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(normalized_request(validated)), strict=True
        )
        request_digest = canonical_request_digest(canonical)
        corpus = _corpus(canonical, request_digest)
        payload: dict[str, Any] = {
            "output_type": "proteotype_synthetic_truth",
            "result_id": result_identifier(request_digest),
            "result_version": M2502_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": "sha256:" + ("0" * 64),
            "request": canonical,
            "status": GenerationStatus.GENERATED,
            "corpus": corpus,
            "manifest": corpus.manifest,
            "findings": (),
            "abstention_reason": None,
            "parent_target": "proteotype",
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="deterministic_fixture_generation",
                rationale="All declared controls and reproducibility fields are closed.",
            ),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(canonical, request_digest),
            "evidence": _evidence(canonical),
            "limitations": _LIMITATIONS,
            "human_review_required": False,
        }
        provisional = ProteotypeSyntheticTruthResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return ProteotypeSyntheticTruthResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )

    def verify_replay(
        self,
        result: ProteotypeSyntheticTruthResult,
    ) -> ProteotypeSyntheticTruthResult:
        """Rebuild and compare the complete synthetic corpus during replay."""

        if result.request_digest != canonical_request_digest(result.request):
            raise M2502ReplayError("M25-02 result request digest mismatch")  # noqa: TRY003
        if result.result_id != result_identifier(canonical_request_digest(result.request)):
            raise M2502ReplayError("M25-02 result identifier mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M2502ReplayError("M25-02 result payload digest mismatch")  # noqa: TRY003
        try:
            replayed = ProteotypeSyntheticTruthResult.model_validate_json(
                canonical_json_bytes(result), strict=True
            )
            expected = self.generate(replayed.request)
        except Exception as error:
            raise M2502ReplayError("M25-02 deterministic replay could not execute") from error
        if canonical_json_bytes(expected) != canonical_json_bytes(replayed):
            raise M2502ReplayError("M25-02 deterministic replay output mismatch")  # noqa: TRY003
        return replayed


def generate_proteotype_synthetic_truth(
    request: object,
) -> ProteotypeSyntheticTruthResult:
    """Public stateless M25-02 generation entry point."""

    return M2502SyntheticTruthGenerator().generate(request)


def preflight_m2502_authorization(candidate: object) -> None:
    """Reject denied controls before traversing caller-declared material."""

    try:
        context = (
            candidate.context
            if isinstance(candidate, GenerateProteotypeSyntheticTruthRequest)
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
            _state_value(_member(_member(references, role), "state")) == state
            for role, state in expected.items()
        )
    except Exception:  # noqa: BLE001 - fail closed at hostile mapping boundary.
        raise M2502AuthorizationError from None
    if not authorized:
        raise M2502AuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    return getattr(candidate, "value", candidate)


def _corpus(
    request: GenerateProteotypeSyntheticTruthRequest,
    request_digest: str,
) -> SyntheticTruthCorpus:
    kinds = request.configuration.requested_fixture_kinds
    cases = tuple(
        SyntheticTruthCase(
            case_id=f"m2502.case.{index:04d}",
            fixture_kind=kind,
            representation=(
                TruthRepresentation.ANALYTIC
                if kind in {FixtureKind.NORMAL, FixtureKind.EDGE, FixtureKind.MISSING}
                else TruthRepresentation.SEMI_SYNTHETIC
            ),
            seed=request.configuration.seed + index,
            expected_features=("protein_abundance", "rna_abundance", "copy_number"),
            truth_values=(
                f"protein={request.configuration.seed + index}",
                f"rna={request.configuration.seed + index + 1}",
                f"copy_number={request.configuration.seed + index + 2}",
            ),
            perturbations=(kind.value,),
            evidence=_evidence(request),
        )
        for index, kind in enumerate(
            kinds[i % len(kinds)] for i in range(request.requested_case_count)
        )
    )
    case_ids = tuple(case.case_id for case in cases)
    configuration = request.configuration
    manifest_payload: dict[str, Any] = {
        "manifest_id": "m2502.manifest." + request_digest.removeprefix("sha256:"),
        "version": configuration.version,
        "configuration": configuration,
        "case_ids": case_ids,
        "reproducibility_digest": "sha256:" + ("0" * 64),
        "fixture_summary": tuple(sorted({case.fixture_kind.value for case in cases})),
        "evidence": _evidence(request),
    }
    manifest_payload["reproducibility_digest"] = sha256_digest(
        {"cases": cases, "configuration": configuration}
    )
    manifest = GenerationManifest(**cast("Any", manifest_payload))
    return SyntheticTruthCorpus(
        corpus_id="m2502.corpus." + request_digest.removeprefix("sha256:"),
        version=configuration.version,
        cases=cases,
        manifest=manifest,
        source_artifacts=request.source_artifacts,
        evidence=_evidence(request),
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=f"M25-02 does not infer {dimension} uncertainty from caller material.",
        )

    return UncertaintyProfile(
        measurement=unavailable("measurement"),
        sampling=unavailable("sampling"),
        parameter=unavailable("parameter"),
        model_form=unavailable("model form"),
        identification=unavailable("identification"),
        support=unavailable("support"),
        transport=unavailable("transport"),
        sensitivity_notes=("Synthetic fixture uncertainty is not biological uncertainty.",),
    )


def _evidence(
    request: GenerateProteotypeSyntheticTruthRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M2502_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _provenance(
    request: GenerateProteotypeSyntheticTruthRequest,
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
        activity_id="m2502.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2502_MODULE_ID,
        module_version=M2502_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(artifact.digest for artifact in request.source_artifacts),
        configuration_digest=canonical_request_digest(request.configuration),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M2502AuthorizationError",
    "M2502ReplayError",
    "M2502SyntheticTruthGenerator",
    "generate_proteotype_synthetic_truth",
    "preflight_m2502_authorization",
]
