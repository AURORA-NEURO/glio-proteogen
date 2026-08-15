"""Deterministic, evidence-preserving M11-03 feature construction runtime."""

from __future__ import annotations

from typing import Any, Final, cast

from pydantic import ValidationError

from glio_proteogen.contracts.m11_03 import (
    M1103_CONTRACT_VERSION,
    M1103_EVIDENCE_CLAIM,
    M1103_MODULE_ID,
    M1103_PARENT,
    ConstructVariantPeptideMechanisticFeaturesRequest,
    MechanisticConstructionStatus,
    MechanisticDiagnosticStatus,
    MechanisticFeatureDiagnostic,
    MechanisticFeatureObject,
    MechanisticFindingCode,
    VariantPeptideMechanisticFeatureResult,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
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
from glio_proteogen.kernel.strict_json import strict_json_loads

_ZERO_DIGEST: Final = "sha256:" + "0" * 64
_AUTHORIZED_STATES: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_FAIL_MARKERS: Final = ("fail", "invalid", "missing", "unknown", "unsupported")


class M1103AuthorizationError(PermissionError):
    """Raised before any upstream or opaque evidence reference is traversed."""

    def __init__(self) -> None:
        super().__init__(
            "M11-03 requires accepted identity, consent, quality, support, and use controls"
        )


class _InvalidRequestError(TypeError):
    def __init__(self) -> None:
        super().__init__("M11-03 request must be an exact contract type or plain JSON object")


def preflight_m1103_authorization(candidate: object) -> None:
    """Check the seven caller-declared controls without reading evidence payloads."""

    states: dict[str, str] | None = None
    if type(candidate) is ConstructVariantPeptideMechanisticFeaturesRequest:
        references = candidate.context.references
        states = {
            "approved_configuration": references.approved_configuration.state.value,
            "identity_lineage": references.identity_lineage.state.value,
            "provenance": references.provenance.state.value,
            "consent": references.consent.state.value,
            "quality": references.quality.state.value,
            "support": references.support.state.value,
            "intended_use": references.intended_use.state.value,
        }
    elif type(candidate) is dict:
        raw = cast("dict[object, object]", candidate)
        context = raw.get("context")
        refs = context.get("references") if type(context) is dict else None
        if type(refs) is dict:
            ref_map = cast("dict[object, object]", refs)
            states = {}
            for role in _AUTHORIZED_STATES:
                item = ref_map.get(role)
                state = item.get("state") if type(item) is dict else None
                if type(state) is not str:
                    states = None
                    break
                states[role] = state
    if states != _AUTHORIZED_STATES:
        raise M1103AuthorizationError


def _validate_request(candidate: object) -> ConstructVariantPeptideMechanisticFeaturesRequest:
    if type(candidate) not in {ConstructVariantPeptideMechanisticFeaturesRequest, dict}:
        raise _InvalidRequestError
    preflight_m1103_authorization(candidate)
    if type(candidate) is ConstructVariantPeptideMechanisticFeaturesRequest:
        return ConstructVariantPeptideMechanisticFeaturesRequest.model_validate(
            candidate, strict=True
        )
    return ConstructVariantPeptideMechanisticFeaturesRequest.model_validate_json(
        canonical_json_bytes(candidate), strict=True
    )


def _validate_json_request(
    decoded: object,
    serialized: bytes | bytearray | str,
) -> ConstructVariantPeptideMechanisticFeaturesRequest:
    """Validate the exact duplicate-free JSON bytes after control preflight."""

    preflight_m1103_authorization(decoded)
    return ConstructVariantPeptideMechanisticFeaturesRequest.model_validate_json(
        serialized, strict=True
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=(
                f"M11-03 provisional ABI has no locked calibration for {dimension} uncertainty"
            ),
        )

    return UncertaintyProfile(
        measurement=unavailable("measurement"),
        sampling=unavailable("sampling"),
        parameter=unavailable("parameter"),
        model_form=unavailable("model-form"),
        identification=unavailable("identification"),
        support=unavailable("support"),
        transport=unavailable("transport"),
        sensitivity_notes=(
            "Perturbation and topology sensitivity are declared, but calibration is not frozen.",
            "Novel or out-of-domain mechanistic states require human review.",
        ),
    )


def _controls(
    request: ConstructVariantPeptideMechanisticFeaturesRequest,
) -> tuple[ControlDecisionRecord, ...]:
    references = request.context.references
    values = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration, None),
        (
            ControlRole.IDENTITY_LINEAGE,
            references.identity_lineage,
            references.identity_lineage.binding_digest,
        ),
        (ControlRole.PROVENANCE, references.provenance, None),
        (ControlRole.CONSENT, references.consent, None),
        (ControlRole.QUALITY, references.quality, None),
        (ControlRole.SUPPORT, references.support, None),
        (ControlRole.INTENDED_USE, references.intended_use, None),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=reference.state.value,
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=subject,
        )
        for role, reference, subject in values
    )


def _provenance(
    request: ConstructVariantPeptideMechanisticFeaturesRequest,
    request_hash: str,
    configuration_hash: str,
) -> ProvenanceRecord:
    references = request.context.references
    controls = _controls(request)
    return ProvenanceRecord(
        activity_id=f"activity.m1103.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1103_MODULE_ID,
        module_version=M1103_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            sorted(
                {
                    request_hash,
                    configuration_hash,
                    request.upstream_result.digest,
                    *(item.digest for item in request.source_artifacts),
                    *(item.evidence_digest for item in controls),
                }
            )
        ),
        configuration_digest=configuration_hash,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


def _evidence(
    request: ConstructVariantPeptideMechanisticFeaturesRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=item, role="evidence", claim=M1103_EVIDENCE_CLAIM)
        for item in (
            request.upstream_result,
            *request.source_artifacts,
            request.configuration.topology_reference,
            *request.configuration.negative_control_artifacts,
        )
    )


def _diagnostic(
    code: str, status: MechanisticDiagnosticStatus, message: str
) -> MechanisticFeatureDiagnostic:
    return MechanisticFeatureDiagnostic(
        diagnostic_id=f"diagnostic.{code}", status=status, message=message
    )


def _marker(value: str) -> bool:
    lowered = value.casefold()
    return any(marker in lowered for marker in _FAIL_MARKERS)


def _evaluate(
    request: ConstructVariantPeptideMechanisticFeaturesRequest,
) -> tuple[
    tuple[MechanisticFeatureDiagnostic, ...],
    tuple[MechanisticFindingCode, ...],
    str | None,
    SupportStatus,
]:
    findings: list[MechanisticFindingCode] = []
    diagnostics: list[MechanisticFeatureDiagnostic] = []
    upstream_bad = _marker(request.upstream_result.artifact_id)
    source_bad = any(_marker(item.artifact_id) for item in request.source_artifacts)
    diagnostics.append(
        _diagnostic(
            "upstream",
            MechanisticDiagnosticStatus.NOT_EVALUABLE
            if upstream_bad
            else MechanisticDiagnosticStatus.PASS,
            "Upstream M11-02 support is unavailable."
            if upstream_bad
            else "Upstream M11-02 reference is accepted.",
        )
    )
    if upstream_bad:
        findings.append(MechanisticFindingCode.UPSTREAM_UNSUPPORTED)
    if not request.declared_features:
        diagnostics.append(
            _diagnostic(
                "input",
                MechanisticDiagnosticStatus.NOT_EVALUABLE,
                "No caller-declared mechanistic features were supplied.",
            )
        )
        findings.append(MechanisticFindingCode.INPUT_INCOMPLETE)
    else:
        diagnostics.append(
            _diagnostic(
                "input", MechanisticDiagnosticStatus.PASS, "Feature declarations are present."
            )
        )
    source_keys = {
        (item.artifact_id, item.version, item.digest, item.media_type)
        for item in request.source_artifacts
    }
    transform_ids = set(request.configuration.transformation_ids)
    lineage_ok = all(
        {
            (item.artifact_id, item.version, item.digest, item.media_type) in source_keys
            for item in feature.lineage.source_artifacts
        }
        and set(feature.lineage.transformation_ids) <= transform_ids
        for feature in request.declared_features
    )
    unit_ok = all(
        feature.unit.casefold() not in {"", "unknown", "invalid", "na", "n/a"}
        for feature in request.declared_features
    )
    diagnostics.append(
        _diagnostic(
            "units",
            MechanisticDiagnosticStatus.PASS
            if unit_ok and lineage_ok
            else MechanisticDiagnosticStatus.FAIL,
            "Unit and lineage invariants pass."
            if unit_ok and lineage_ok
            else "Unit or lineage closure failed.",
        )
    )
    if not unit_ok or not lineage_ok:
        findings.append(MechanisticFindingCode.UNIT_INVARIANT_FAILED)
    topology_ok = not _marker(request.configuration.topology_reference.artifact_id)
    topology_ok = topology_ok and not any(
        _marker(item.artifact_id) for item in request.configuration.negative_control_artifacts
    )
    try:
        MechanisticFeatureObject(
            object_id="probe.m1103",
            version=M1103_CONTRACT_VERSION,
            features=request.declared_features or (),
            relations=request.declared_relations,
            configuration=request.configuration,
        )
    except (TypeError, ValueError, ValidationError):
        topology_ok = False
    diagnostics.append(
        _diagnostic(
            "topology",
            MechanisticDiagnosticStatus.PASS if topology_ok else MechanisticDiagnosticStatus.FAIL,
            "Topology and negative-control invariants pass."
            if topology_ok
            else "Topology or negative-control invariant failed.",
        )
    )
    if not topology_ok:
        findings.append(MechanisticFindingCode.TOPOLOGY_INVARIANT_FAILED)
        if any(
            _marker(item.artifact_id) for item in request.configuration.negative_control_artifacts
        ):
            findings.append(MechanisticFindingCode.NEGATIVE_CONTROL_FAILED)
    bad = (
        upstream_bad
        or source_bad
        or not request.declared_features
        or not unit_ok
        or not lineage_ok
        or not topology_ok
    )
    if source_bad and MechanisticFindingCode.INPUT_INCOMPLETE not in findings:
        findings.append(MechanisticFindingCode.INPUT_INCOMPLETE)
    if bad:
        reason = "; ".join(item.value for item in findings) or "mechanistic invariant failed"
        support = (
            SupportStatus.UNSUPPORTED
            if upstream_bad or source_bad
            else SupportStatus.REVIEW_REQUIRED
        )
        return tuple(diagnostics), tuple(dict.fromkeys(findings)), reason, support
    return tuple(diagnostics), (), None, SupportStatus.SUPPORTED


def _build_result(
    request: ConstructVariantPeptideMechanisticFeaturesRequest,
) -> VariantPeptideMechanisticFeatureResult:
    request_hash = canonical_request_digest(request)
    configuration_hash = sha256_digest(request.configuration)
    diagnostics, findings, reason, support_status = _evaluate(request)
    constructed = support_status is SupportStatus.SUPPORTED
    feature_object = (
        MechanisticFeatureObject(
            object_id=f"object.m1103.{request_hash.removeprefix('sha256:')}",
            version=M1103_CONTRACT_VERSION,
            features=request.declared_features,
            relations=request.declared_relations,
            configuration=request.configuration,
            evidence=_evidence(request),
        )
        if constructed
        else None
    )
    support = SupportDecision(
        status=support_status,
        reason_code="mechanistic_features_constructed"
        if constructed
        else "mechanistic_features_quarantined",
        rationale="All locked invariants pass."
        if constructed
        else "Feature construction is quarantined pending review.",
    )
    payload: dict[str, Any] = {
        "output_type": "variant_peptide_mechanistic_features",
        "result_id": f"result.m1103.{request_hash.removeprefix('sha256:')}",
        "result_version": M1103_CONTRACT_VERSION,
        "request_digest": request_hash,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "status": MechanisticConstructionStatus.CONSTRUCTED
        if constructed
        else MechanisticConstructionStatus.ABSTAINED,
        "feature_object": feature_object,
        "diagnostics": diagnostics,
        "findings": findings,
        "abstention_reason": reason,
        "parent_target": M1103_PARENT,
        "emits_parent": False,
        "support_decision": support,
        "uncertainty": _uncertainty(),
        "provenance": _provenance(request, request_hash, configuration_hash),
        "evidence": _evidence(request),
        "limitations": (
            Limitation(
                code="provisional_abi",
                statement=(
                    "Feature catalogue and estimator ABI remain provisional "
                    "pending owner confirmation."
                ),
            ),
            Limitation(
                code="no_kinase_state",
                statement=(
                    "KINOPHOS owns kinase-state inference; this module emits no kinase activity."
                ),
            ),
        ),
        "human_review_required": not constructed,
    }
    candidate = VariantPeptideMechanisticFeatureResult.model_construct(**payload)
    payload["result_digest"] = result_payload_digest(candidate)
    return VariantPeptideMechanisticFeatureResult.model_validate(payload, strict=True)


class M1103MechanisticFeatureEngine:
    """Construct one deterministic feature object or abstain safely."""

    __slots__ = ()

    def compute(self, request: object) -> VariantPeptideMechanisticFeatureResult:
        return _build_result(_validate_request(request))


def construct_variant_peptide_mechanistic_features(
    request: object,
) -> VariantPeptideMechanisticFeatureResult:
    return M1103MechanisticFeatureEngine().compute(request)


def verify_m1103_replay(
    result: VariantPeptideMechanisticFeatureResult,
    request: object,
) -> bool:
    """Verify exact request binding and sealed result digest without recomputation."""

    try:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            decoded = strict_json_loads(serialized)
            typed = _validate_json_request(decoded, serialized)
        else:
            typed = _validate_request(request)
        if result.request_digest != canonical_request_digest(typed):
            return False
        if result.request != typed:
            return False
        return result.result_digest == result_payload_digest(result)
    except (TypeError, ValueError, ValidationError):
        return False


__all__ = [
    "M1103AuthorizationError",
    "M1103MechanisticFeatureEngine",
    "construct_variant_peptide_mechanistic_features",
    "preflight_m1103_authorization",
    "verify_m1103_replay",
]
