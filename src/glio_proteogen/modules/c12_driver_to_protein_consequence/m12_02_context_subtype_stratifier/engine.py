"""Deterministic, replay-bound M12-02 context and subtype stratifier."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, NoReturn, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m12_02 import (
    M1202_CONTRACT_VERSION,
    M1202_EVIDENCE_CLAIM,
    M1202_PARENT,
    ApplicableMechanism,
    BiomarkerPanelContextStratificationResult,
    ContextDimension,
    ContextFinding,
    ContextFindingCode,
    ContextObservation,
    ContextObservationStatus,
    ContextProfile,
    MechanismApplicability,
    StratifierStatus,
    StratifyBiomarkerPanelContextRequest,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m12_02.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import EvidenceReference as KernelEvidenceReference
from glio_proteogen.kernel.models import Limitation, SupportDecision, SupportStatus

_REQUEST_ADAPTER: Final = TypeAdapter(StratifyBiomarkerPanelContextRequest)
_RESULT_ADAPTER: Final = TypeAdapter(BiomarkerPanelContextStratificationResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_MAX_EVIDENCE: Final = 64
_EXPECTED_DIMENSIONS: Final = frozenset(ContextDimension)
_SUPPORTED_MECHANISMS: Final = {
    "immune": ("immune-context", "Immune microenvironment context"),
    "hypoxia": ("hypoxia-context", "Hypoxic biological context"),
    "proliferative": ("proliferative-context", "Proliferative biological context"),
    "mesenchymal": ("mesenchymal-subtype", "Mesenchymal subtype context"),
    "proneural": ("proneural-subtype", "Proneural subtype context"),
    "classical": ("classical-subtype", "Classical subtype context"),
}


class M1202ContextAuthorizationError(PermissionError):
    """Caller controls do not authorize context stratification."""

    def __init__(self) -> None:
        super().__init__(
            "M12-02 requires accepted controls, resolved identity, and granted consent"
        )


class M1202ReplayVerificationError(ValueError):
    """A context result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M12-02 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_context_authorization(candidate: object) -> None:
    """Check seven controls before traversing opaque context or source artifacts."""

    try:
        context = _member(candidate, "context")
        refs = _member(context, "references")
        expected = {
            "approved_configuration": "accepted",
            "identity_lineage": "resolved",
            "provenance": "accepted",
            "consent": "granted",
            "quality": "accepted",
            "support": "accepted",
            "intended_use": "accepted",
        }
        states = {role: _state(_member(_member(refs, role), "state")) for role in expected}
    except Exception:  # noqa: BLE001 - hostile caller objects fail closed.
        raise M1202ContextAuthorizationError from None
    if states != expected:
        raise M1202ContextAuthorizationError


def _evidence(
    request: StratifyBiomarkerPanelContextRequest,
) -> tuple[KernelEvidenceReference, ...]:
    refs = request.context.references
    artifacts = (
        *request.source_artifacts,
        request.driver_consequence_result,
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
        *(item.source_artifact for item in request.observations),
        *(item.reference for observation in request.observations for item in observation.evidence),
    )
    # Observation evidence is already immutable caller-declared material. Keep
    # the source index bounded while retaining first-seen order.
    seen: set[str] = set()
    output: list[KernelEvidenceReference] = []
    for artifact in artifacts:
        if artifact.artifact_id in seen:
            continue
        seen.add(artifact.artifact_id)
        output.append(
            KernelEvidenceReference(reference=artifact, role="evidence", claim=M1202_EVIDENCE_CLAIM)
        )
        if len(output) == _MAX_EVIDENCE:
            break
    return tuple(output)


def _observation_evidence(
    observation: ContextObservation,
) -> tuple[KernelEvidenceReference, ...]:
    return tuple(
        KernelEvidenceReference(
            reference=item.reference,
            role="evidence",
            claim=M1202_EVIDENCE_CLAIM,
        )
        for item in observation.evidence
    )


def _slug(value: str) -> str:
    normalized = "".join(character.lower() if character.isalnum() else "-" for character in value)
    return "-".join(part for part in normalized.split("-") if part)[:96] or "unknown"


def _mechanisms(
    observations: tuple[ContextObservation, ...],
) -> tuple[ApplicableMechanism, ...]:
    output: list[ApplicableMechanism] = []
    seen: set[str] = set()
    for observation in observations:
        if observation.status is not ContextObservationStatus.SUPPORTED:
            continue
        value = (observation.normalized_value or observation.value).lower()
        for keyword, (suffix, label) in _SUPPORTED_MECHANISMS.items():
            if keyword not in value or suffix in seen:
                continue
            seen.add(suffix)
            output.append(
                ApplicableMechanism(
                    mechanism_id=f"mechanism.{suffix}",
                    label=label,
                    applicability=MechanismApplicability.APPLICABLE,
                    rationale=(
                        "The caller-declared supported context contains a recognized context "
                        "term; no kinase-state or treatment interpretation is performed."
                    ),
                    evidence=_observation_evidence(observation),
                )
            )
    if not output:
        output.append(
            ApplicableMechanism(
                mechanism_id="mechanism.context.unknown",
                label="Context-dependent mechanism",
                applicability=MechanismApplicability.UNKNOWN,
                rationale=(
                    "No recognized mechanism label is safely inferable from the declared context."
                ),
            )
        )
    return tuple(output)


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="opaque_inputs",
            statement=(
                "Upstream and source artifacts remain immutable references and are never traversed."
            ),
        ),
        Limitation(
            code="conflict_preservation",
            statement="Conflicting context observations remain visible and block stratification.",
        ),
        Limitation(
            code="prohibited_outputs",
            statement=(
                "No kinase activity, generic all-omics fusion, direct treatment recommendation, "
                "identity inference, consent inference, or parent-output emission is performed."
            ),
        ),
    ]
    if not supported:
        values.append(
            Limitation(
                code="safe_abstention",
                statement=(
                    "No context profile or applicable mechanism is published until required "
                    "dimensions are supported."
                ),
            )
        )
    return tuple(values)


def _findings(
    request: StratifyBiomarkerPanelContextRequest,
) -> tuple[ContextFinding, ...]:
    by_dimension: dict[ContextDimension, list[ContextObservation]] = {}
    for observation in request.observations:
        by_dimension.setdefault(observation.dimension, []).append(observation)
    output: list[ContextFinding] = []
    missing = _EXPECTED_DIMENSIONS.difference(by_dimension)
    output.extend(
        ContextFinding(
            finding_id=f"finding.missing.{dimension.value}",
            code=ContextFindingCode.CONTEXT_CONFLICT,
            message=f"Required context dimension {dimension.value} is missing or unresolved.",
        )
        for dimension in sorted(missing, key=lambda item: item.value)
    )
    if set(request.policy.required_dimensions) != _EXPECTED_DIMENSIONS:
        output.append(
            ContextFinding(
                finding_id="finding.policy.incomplete",
                code=ContextFindingCode.UNSUPPORTED_PROXY_BLOCKED,
                message="Policy does not declare all eight dossier context dimensions.",
            )
        )
    for dimension, observations in by_dimension.items():
        values = {(item.normalized_value or item.value).lower() for item in observations}
        if len(values) > 1:
            output.append(
                ContextFinding(
                    finding_id=f"finding.conflict.{dimension.value}",
                    code=ContextFindingCode.CONTEXT_CONFLICT,
                    message=(
                        f"Conflicting observations remain for {dimension.value}; "
                        "stratification is withheld."
                    ),
                    evidence=tuple(
                        evidence
                        for item in observations
                        for evidence in _observation_evidence(item)
                    ),
                )
            )
        if any(item.status is not ContextObservationStatus.SUPPORTED for item in observations):
            output.append(
                ContextFinding(
                    finding_id=f"finding.unsupported.{dimension.value}",
                    code=ContextFindingCode.UNSUPPORTED_PROXY_BLOCKED,
                    message=f"Context dimension {dimension.value} is not fully supported.",
                    evidence=tuple(
                        evidence
                        for item in observations
                        for evidence in _observation_evidence(item)
                    ),
                )
            )
    if not output:
        output.append(
            ContextFinding(
                finding_id="finding.provisional_abi",
                code=ContextFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                message="Public M12-02 ABI remains provisional pending owner confirmation.",
            )
        )
    return tuple(output)


def _supported(request: StratifyBiomarkerPanelContextRequest) -> bool:
    by_dimension: dict[ContextDimension, list[ContextObservation]] = {}
    for observation in request.observations:
        by_dimension.setdefault(observation.dimension, []).append(observation)
    if set(request.policy.required_dimensions) != _EXPECTED_DIMENSIONS:
        return False
    if set(by_dimension) != _EXPECTED_DIMENSIONS:
        return False
    return all(
        len(observations) == 1 and observations[0].status is ContextObservationStatus.SUPPORTED
        for observations in by_dimension.values()
    )


class M1202ContextEngine:
    """Build one typed context profile without hidden biological inference."""

    __slots__ = ()

    def stratify(
        self,
        request: object,
    ) -> BiomarkerPanelContextStratificationResult:
        preflight_context_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return self._result(validated)

    def _result(
        self,
        request: StratifyBiomarkerPanelContextRequest,
    ) -> BiomarkerPanelContextStratificationResult:
        request_hash = canonical_request_digest(request)
        supported = _supported(request)
        findings = _findings(request)
        evidence = _evidence(request)
        profile = (
            ContextProfile(
                profile_id=f"profile.{request_hash.removeprefix('sha256:')}",
                version=request.policy.configuration.version,
                observations=request.observations,
                unresolved_dimensions=(),
                evidence=evidence,
            )
            if supported
            else None
        )
        mechanisms = _mechanisms(request.observations) if supported else ()
        payload: dict[str, object] = {
            "output_type": "biomarker_panel_context_stratification",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1202_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": StratifierStatus.STRATIFIED if supported else StratifierStatus.ABSTAINED,
            "context_profile": profile,
            "applicable_mechanisms": mechanisms,
            "findings": findings,
            "abstention_reason": None
            if supported
            else "Required context dimensions or support boundaries are not safely evaluable.",
            "parent_target": M1202_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if supported else SupportStatus.REVIEW_REQUIRED,
                reason_code="m1202_context_supported" if supported else "m1202_context_abstained",
                rationale=(
                    "All eight context dimensions are uniquely supported under the locked policy."
                    if supported
                    else (
                        "Context stratification is withheld until all required dimensions "
                        "are supported."
                    )
                ),
            ),
            "uncertainty": expected_uncertainty(supported=supported),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=supported),
            "human_review_required": not supported,
        }
        constructed = BiomarkerPanelContextStratificationResult.model_construct(
            **cast("dict[str, Any]", payload)
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> BiomarkerPanelContextStratificationResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
            if validated.result_digest != result_payload_digest(validated):
                _raise_replay()
            elif replay:
                expected = self.stratify(validated.request)
                if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                    _raise_replay()
        except M1202ReplayVerificationError:
            raise
        except Exception as error:
            raise M1202ReplayVerificationError from error
        else:
            return validated


def _raise_replay() -> NoReturn:
    raise M1202ReplayVerificationError


def stratify_biomarker_panel_context(
    request: object,
) -> BiomarkerPanelContextStratificationResult:
    """Public provisional M12-02 operation."""

    return M1202ContextEngine().stratify(request)


__all__ = [
    "M1202ContextAuthorizationError",
    "M1202ContextEngine",
    "M1202ReplayVerificationError",
    "preflight_context_authorization",
    "stratify_biomarker_panel_context",
]
