"""Deterministic, caller-declared M22-02 synthetic-truth generation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_02.canonical import (
    canonical_request_digest,
    normalized_request,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.contracts.m22_02.v1 import (
    M2202_CONTRACT_VERSION,
    M2202_EVIDENCE_CLAIM,
    M2202_MODULE_ID,
    FixtureKind,
    GenerateProteinRnaDiscordanceSyntheticTruthRequest,
    GenerationManifest,
    GenerationStatus,
    ProteinRnaDiscordanceSyntheticTruthResult,
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

_REQUEST_ADAPTER: Final = TypeAdapter(GenerateProteinRnaDiscordanceSyntheticTruthRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "M22-02 generation requires accepted configuration, resolved identity, granted consent, "
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
        code="protein_rna_discordance_parent_boundary",
        statement=(
            "The generator creates benchmark material for protein-RNA discordance but does not "
            "emit a discordance estimate or biological conclusion."
        ),
    ),
    Limitation(
        code="exclusive_scope",
        statement=(
            "KINOPHOS kinase-state ownership, generic all-omics fusion, treatment recommendation, "
            "identity inference and unsupported-to-negative conversion are outside this module."
        ),
    ),
)


class M2202AuthorizationError(ValueError):
    """Raised when caller-declared controls do not authorize execution."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2202ReplayError(ValueError):
    """Raised when an immutable M22-02 result fails replay closure."""


class M2202SyntheticTruthGenerator:
    """Generate, validate, and replay one deterministic synthetic-truth corpus."""

    __slots__ = ()

    def generate(self, request: object) -> ProteinRnaDiscordanceSyntheticTruthResult:
        preflight_m2202_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(normalized_request(validated)), strict=True
        )
        request_digest = canonical_request_digest(canonical)
        corpus = _corpus(canonical, request_digest)
        payload: dict[str, Any] = {
            "output_type": "protein_rna_discordance_synthetic_truth",
            "result_id": result_identifier(canonical),
            "result_version": M2202_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": "sha256:" + ("0" * 64),
            "request": canonical,
            "status": GenerationStatus.GENERATED,
            "corpus": corpus,
            "manifest": corpus.manifest,
            "findings": (),
            "abstention_reason": None,
            "parent_target": "protein-RNA discordance",
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
        provisional = ProteinRnaDiscordanceSyntheticTruthResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return ProteinRnaDiscordanceSyntheticTruthResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )

    def verify_replay(
        self,
        result: ProteinRnaDiscordanceSyntheticTruthResult,
    ) -> ProteinRnaDiscordanceSyntheticTruthResult:
        if result.request_digest != canonical_request_digest(result.request):
            raise M2202ReplayError("M22-02 result request digest mismatch")  # noqa: TRY003
        if result.result_id != result_identifier(result.request):
            raise M2202ReplayError("M22-02 result identifier mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M2202ReplayError("M22-02 result payload digest mismatch")  # noqa: TRY003
        return ProteinRnaDiscordanceSyntheticTruthResult.model_validate_json(
            canonical_json_bytes(result), strict=True
        )


def generate_protein_rna_discordance_synthetic_truth(
    request: object,
) -> ProteinRnaDiscordanceSyntheticTruthResult:
    """Public stateless M22-02 generation entry point."""

    return M2202SyntheticTruthGenerator().generate(request)


def preflight_m2202_authorization(candidate: object) -> None:
    """Reject denied controls before traversing caller-declared material."""

    try:
        context = (
            candidate.context
            if isinstance(candidate, GenerateProteinRnaDiscordanceSyntheticTruthRequest)
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
        raise M2202AuthorizationError from None
    if not authorized:
        raise M2202AuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    return getattr(candidate, "value", candidate)


def _corpus(
    request: GenerateProteinRnaDiscordanceSyntheticTruthRequest,
    request_digest: str,
) -> SyntheticTruthCorpus:
    kinds = request.configuration.requested_fixture_kinds
    cases = tuple(
        SyntheticTruthCase(
            case_id=f"m2202.case.{index:04d}",
            fixture_kind=kind,
            representation=(
                TruthRepresentation.ANALYTIC
                if kind in {FixtureKind.NORMAL, FixtureKind.EDGE, FixtureKind.MISSING}
                else TruthRepresentation.SEMI_SYNTHETIC
            ),
            seed=request.configuration.seed + index,
            expected_features=("protein_abundance", "rna_abundance", "discordance"),
            truth_values=(
                f"protein={request.configuration.seed + index}",
                f"rna={request.configuration.seed + index + 1}",
                f"discordance={kind.value}",
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
        "manifest_id": "m2202.manifest." + request_digest.removeprefix("sha256:"),
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
        corpus_id="m2202.corpus." + request_digest.removeprefix("sha256:"),
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
            rationale=f"M22-02 does not infer {dimension} uncertainty from caller material.",
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
    request: GenerateProteinRnaDiscordanceSyntheticTruthRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M2202_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _provenance(
    request: GenerateProteinRnaDiscordanceSyntheticTruthRequest,
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
        activity_id="m2202.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2202_MODULE_ID,
        module_version=M2202_CONTRACT_VERSION,
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
    "M2202AuthorizationError",
    "M2202ReplayError",
    "M2202SyntheticTruthGenerator",
    "generate_protein_rna_discordance_synthetic_truth",
    "preflight_m2202_authorization",
]
