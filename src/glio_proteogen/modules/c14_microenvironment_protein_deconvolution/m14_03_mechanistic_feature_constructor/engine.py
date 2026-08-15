"""Deterministic, replay-bound M14-03 mechanistic feature construction.

The provisional ABI does not expose scientific source bytes or a model input
matrix.  This engine therefore constructs only caller-declared categorical
feature records from immutable references and a locked configuration.  It
never infers mechanism, topology, kinetics, state, identity, or treatment
effect.  Unsupported configuration families and failed negative-control
closure return explicit abstention.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_03 import (
    M1403_CONTRACT_VERSION,
    M1403_EVIDENCE_CLAIM,
    M1403_MODULE_ID,
    M1403_PARENT,
    ConstructProteinSubtypeMechanisticFeaturesRequest,
    MechanisticConstructionStatus,
    MechanisticDiagnosticStatus,
    MechanisticFeature,
    MechanisticFeatureDiagnostic,
    MechanisticFeatureKind,
    MechanisticFeatureLineage,
    MechanisticFeatureObject,
    MechanisticFindingCode,
    MechanisticRelation,
    MechanisticRelationKind,
    MechanisticValueKind,
    ProteinSubtypeMechanisticFeatureResult,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ConstructProteinSubtypeMechanisticFeaturesRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeMechanisticFeatureResult)
_EXPECTED_CONTROLS: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_SUPPORTED_MODEL_FAMILIES: Final = frozenset(
    {"caller_declared_feature_replay", "deterministic_metadata_replay"}
)
_FEATURE_KINDS: Final = tuple(MechanisticFeatureKind)
_LIMITATIONS: Final = (
    Limitation(
        code="opaque_references",
        statement=(
            "Source and upstream artifacts are immutable references; this module never reads "
            "their bytes."
        ),
    ),
    Limitation(
        code="no_mechanistic_inference",
        statement=(
            "Categorical feature records preserve caller declarations and do not infer "
            "biological mechanism."
        ),
    ),
    Limitation(
        code="provisional_abi",
        statement=(
            "The public ABI remains provisional pending Platform engineering confirmation "
            "of the dossier slice."
        ),
    ),
)


class M1403AuthorizationError(PermissionError):
    """Caller-owned controls are not authorized for feature construction."""

    def __init__(self) -> None:
        super().__init__(
            "M14-03 requires accepted controls, resolved identity, and granted consent"
        )


class M1403ReplayVerificationError(ValueError):
    """A feature result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M14-03 replay verification failed")


class _InvalidRequestError(TypeError):
    def __init__(self) -> None:
        super().__init__("M14-03 request must be a strict request model or mapping")


class _UnsupportedConfigurationError(ValueError):
    def __init__(self) -> None:
        super().__init__("unsupported M14-03 model family")


class _DuplicateNegativeControlError(ValueError):
    def __init__(self) -> None:
        super().__init__("negative control references must be unique")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1403_authorization(candidate: object) -> None:
    """Check all seven controls before traversing feature configuration."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        states = {
            role: _state(_member(_member(references, role), "state"))
            for role in _EXPECTED_CONTROLS
        }
    except Exception as error:
        raise M1403AuthorizationError from error
    if states != _EXPECTED_CONTROLS:
        raise M1403AuthorizationError


def _as_request(candidate: object) -> ConstructProteinSubtypeMechanisticFeaturesRequest:
    preflight_m1403_authorization(candidate)
    if type(candidate) is ConstructProteinSubtypeMechanisticFeaturesRequest:
        return candidate
    if isinstance(candidate, Mapping):
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
    raise _InvalidRequestError


def _evidence(
    request: ConstructProteinSubtypeMechanisticFeaturesRequest,
) -> tuple[EvidenceReference, ...]:
    references = (
        *request.source_artifacts,
        request.upstream_result,
        request.configuration.stoichiometry_reference,
        *request.configuration.negative_control_artifacts,
        request.context.references.approved_configuration.evidence,
        request.context.references.identity_lineage.evidence,
        request.context.references.provenance.evidence,
        request.context.references.consent.evidence,
        request.context.references.quality.evidence,
        request.context.references.support.evidence,
        request.context.references.intended_use.evidence,
    )
    unique: list[ArtifactReference] = []
    seen: set[tuple[str, str, str, str]] = set()
    for reference in references:
        key = (reference.artifact_id, reference.version, reference.digest, reference.media_type)
        if key not in seen:
            seen.add(key)
            unique.append(reference)
    return tuple(
        EvidenceReference(reference=reference, role="evidence", claim=M1403_EVIDENCE_CLAIM)
        for reference in unique
    )


def _controls(
    request: ConstructProteinSubtypeMechanisticFeaturesRequest,
) -> tuple[ControlDecisionRecord, ...]:
    references = request.context.references
    values = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage),
        (ControlRole.PROVENANCE, references.provenance),
        (ControlRole.CONSENT, references.consent),
        (ControlRole.QUALITY, references.quality),
        (ControlRole.SUPPORT, references.support),
        (ControlRole.INTENDED_USE, references.intended_use),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=str(_state(reference.state)),
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=getattr(reference, "binding_digest", None),
        )
        for role, reference in values
    )


def _uncertainty() -> UncertaintyProfile:
    values = {
        "measurement": "No measurement values are constructed from opaque references.",
        "sampling": "Sampling coverage is not available at this metadata-only boundary.",
        "parameter": "No fitted parameters or parameter uncertainty are evaluated.",
        "model_form": "The dossier leaves model ABI open and no scientific model executes.",
        "identification": "Identity and upstream subtype identification are not inferred.",
        "support": "Support reflects caller controls and not external evidence authenticity.",
        "transport": "Transport across cohorts, assays, or conditions is not estimable.",
    }
    estimate = {
        name: UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=reason)
        for name, reason in values.items()
    }
    return UncertaintyProfile(
        **estimate,
        sensitivity_notes=(
            "Categorical declarations are replay-stable but are not quantitative "
            "feature estimates.",
            "Owner review is required before any ABI or mechanistic claim is promoted.",
        ),
    )


def _provenance(
    request: ConstructProteinSubtypeMechanisticFeaturesRequest,
    request_hash: str,
) -> ProvenanceRecord:
    references = request.context.references
    input_digests = (
        request.upstream_result.digest,
        *(artifact.digest for artifact in request.source_artifacts),
        request.configuration.stoichiometry_reference.digest,
        *(artifact.digest for artifact in request.configuration.negative_control_artifacts),
    )
    return ProvenanceRecord(
        activity_id=f"activity.m1403.{request_hash.removeprefix('sha256:')[:32]}",
        actor_id=request.context.actor_id,
        module_id=M1403_MODULE_ID,
        module_version=M1403_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=sha256_digest(request.configuration.model_dump(mode="json")),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=_controls(request),
    )


def _feature_object(
    request: ConstructProteinSubtypeMechanisticFeaturesRequest,
    evidence: tuple[EvidenceReference, ...],
    request_hash: str,
) -> tuple[MechanisticFeatureObject, tuple[MechanisticFeatureDiagnostic, ...]]:
    if request.configuration.model_family not in _SUPPORTED_MODEL_FAMILIES:
        raise _UnsupportedConfigurationError
    negative_keys = [
        (
            artifact.artifact_id,
            artifact.version,
            artifact.digest,
            artifact.media_type,
        )
        for artifact in request.configuration.negative_control_artifacts
    ]
    if len(negative_keys) != len(set(negative_keys)):
        raise _DuplicateNegativeControlError
    lineage = tuple(request.source_artifacts)
    features = tuple(
        MechanisticFeature(
            feature_id=(
                f"feature.m1403.{request_hash.removeprefix('sha256:')[:12]}.{kind.value}"
            ),
            version="0.1.0-provisional",
            kind=kind,
            value_kind=MechanisticValueKind.CATEGORICAL,
            unit="caller_declared",
            category=f"caller_declared:{kind.value}",
            lineage=MechanisticFeatureLineage(
                feature_id=(
                    f"feature.m1403.{request_hash.removeprefix('sha256:')[:12]}.{kind.value}"
                ),
                source_artifacts=lineage,
                claim=M1403_EVIDENCE_CLAIM,
                transformation_ids=request.configuration.transformation_ids,
                evidence=evidence[:1],
            ),
            evidence=evidence[:1],
        )
        for kind in _FEATURE_KINDS
    )
    relations = tuple(
        MechanisticRelation(
            relation_id=f"relation.m1403.{request_hash.removeprefix('sha256:')[:12]}.{index}",
            source_feature_id=features[index].feature_id,
            target_feature_id=features[index + 1].feature_id,
            kind=MechanisticRelationKind.PARTICIPATES,
            evidence=evidence[:1],
        )
        for index in range(len(features) - 1)
    )
    feature_object = MechanisticFeatureObject(
        object_id=f"features.m1403.{request_hash.removeprefix('sha256:')[:32]}",
        version="0.1.0-provisional",
        features=features,
        relations=relations,
        configuration=request.configuration,
        evidence=evidence,
    )
    diagnostics = tuple(
        MechanisticFeatureDiagnostic(
            diagnostic_id=f"diagnostic.m1403.{request_hash.removeprefix('sha256:')[:12]}.{code}",
            status=MechanisticDiagnosticStatus.PASS,
            message=message,
            evidence=evidence[:1],
        )
        for code, message in (
            ("source_closure", "All feature lineage references are caller-declared and complete."),
            ("unit_invariant", "All categorical features use the explicit caller_declared unit."),
            (
                "topology_invariant",
                "Relations connect existing distinct features without self-loops.",
            ),
            (
                "stoichiometric_invariant",
                "The locked configuration binds a stoichiometry reference.",
            ),
            (
                "negative_control",
                "The locked configuration contains unique negative-control references.",
            ),
            (
                "authority_ceiling",
                "No elevated parent, clinical, or treatment authority claim is emitted.",
            ),
        )
    )
    return feature_object, diagnostics


class M1403MechanisticFeatureEngine:
    """Construct caller-declared feature metadata without scientific inference."""

    __slots__ = ()

    def construct(self, request: object) -> ProteinSubtypeMechanisticFeatureResult:
        validated = _as_request(request)
        return self._result(validated)

    def _result(
        self,
        request: ConstructProteinSubtypeMechanisticFeaturesRequest,
    ) -> ProteinSubtypeMechanisticFeatureResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        findings: tuple[MechanisticFindingCode, ...] = ()
        abstention_reason: str | None = None
        try:
            feature_object, diagnostics = _feature_object(request, evidence, request_hash)
        except ValueError as error:
            diagnostics = (
                MechanisticFeatureDiagnostic(
                    diagnostic_id=f"diagnostic.m1403.{request_hash.removeprefix('sha256:')[:12]}.abstain",
                    status=MechanisticDiagnosticStatus.NOT_EVALUABLE,
                    message=str(error),
                    evidence=evidence[:1],
                ),
            )
            feature_object = None
            status = MechanisticConstructionStatus.ABSTAINED
            findings = (MechanisticFindingCode.UPSTREAM_UNSUPPORTED,)
            abstention_reason = (
                "M14-03 cannot safely construct features for the requested configuration."
            )
            support_status = SupportStatus.REVIEW_REQUIRED
            support_reason = "m1403_feature_construction_review_required"
            human_review_required = True
        else:
            status = MechanisticConstructionStatus.CONSTRUCTED
            findings = ()
            abstention_reason = None
            support_status = SupportStatus.SUPPORTED
            support_reason = "m1403_feature_construction_supported"
            human_review_required = True
        payload: dict[str, object] = {
            "output_type": "protein_subtype_mechanistic_features",
            "result_id": f"result.m1403.{request_hash.removeprefix('sha256:')[:32]}",
            "result_version": M1403_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": "sha256:" + "0" * 64,
            "request": request,
            "status": status,
            "feature_object": feature_object,
            "diagnostics": diagnostics,
            "findings": findings,
            "abstention_reason": abstention_reason,
            "parent_target": M1403_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=support_status,
                reason_code=support_reason,
                rationale=(
                    "All closed metadata invariants passed; output remains caller-declared."
                    if status is MechanisticConstructionStatus.CONSTRUCTED
                    else (
                        "Feature construction is withheld pending review of the unsupported "
                        "configuration."
                    )
                ),
            ),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _LIMITATIONS,
            "human_review_required": human_review_required,
        }
        constructed = ProteinSubtypeMechanisticFeatureResult.model_construct(
            **payload  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinSubtypeMechanisticFeatureResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1403ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1403ReplayVerificationError
        if replay:
            expected = self.construct(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1403ReplayVerificationError
        return validated


def construct_protein_subtype_mechanistic_features(
    request: object,
) -> ProteinSubtypeMechanisticFeatureResult:
    """Public provisional M14-03 operation."""

    return M1403MechanisticFeatureEngine().construct(request)


__all__ = [
    "M1403AuthorizationError",
    "M1403MechanisticFeatureEngine",
    "M1403ReplayVerificationError",
    "construct_protein_subtype_mechanistic_features",
    "preflight_m1403_authorization",
]
