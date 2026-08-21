"""Deterministic, replay-bound M14-04 mechanism inference runtime.

The dossier does not freeze an implementation ABI.  This runtime therefore
accepts only an explicit, documented caller-declared method grammar.  It never
opens artifact references, infers identity or consent, or treats an unknown
method as a negative biological finding.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_04 import (
    M1404_CONTRACT_VERSION,
    M1404_EVIDENCE_CLAIM,
    M1404_PARENT,
    InferProteinSubtypeMechanismRequest,
    MechanismEstimate,
    MechanismEstimateKind,
    MechanismFinding,
    MechanismFindingCode,
    MechanismInferenceStatus,
    ProteinSubtypeMechanismInferenceResult,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m14_04.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)
from glio_proteogen.kernel.models import (
    EvidenceReference as KernelEvidenceReference,
)

_REQUEST_ADAPTER: Final = TypeAdapter(InferProteinSubtypeMechanismRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeMechanismInferenceResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_SUPPORTED_METHODS: Final = frozenset({"posterior", "state"})
_ABSTAIN_METHODS: Final = frozenset({"abstain", "unsupported", "not_calibrated"})
_SUPPORTED_STATES: Final = frozenset(
    {"active", "inactive", "present", "absent", "upregulated", "downregulated", "stable"}
)
_POSTERIOR_PARTS: Final = 6
_STATE_PARTS: Final = 4


class M1404MechanismAuthorizationError(PermissionError):
    """Caller-owned controls do not authorize mechanism inference."""

    def __init__(self) -> None:
        super().__init__(
            "M14-04 requires accepted controls, resolved identity, and granted consent"
        )


class M1404ReplayVerificationError(ValueError):
    """A mechanism result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M14-04 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_mechanism_authorization(candidate: object) -> None:
    """Check seven controls before any opaque artifact or method traversal."""

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
    except Exception:  # noqa: BLE001
        raise M1404MechanismAuthorizationError from None
    if states != expected:
        raise M1404MechanismAuthorizationError


def _prepare(candidate: object) -> object:
    preflight_mechanism_authorization(candidate)
    return candidate


def _evidence(request: InferProteinSubtypeMechanismRequest) -> tuple[KernelEvidenceReference, ...]:
    refs = request.context.references
    artifacts = (
        request.hypothesis_registry_result,
        *request.source_artifacts,
        request.configuration.model_reference,
        request.configuration.calibration_reference,
        *(item.reference for item in request.configuration.evidence),
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
    )
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        KernelEvidenceReference(reference=artifact, role="evidence", claim=M1404_EVIDENCE_CLAIM)
        for artifact in tuple(unique.values())[:64]
    )


def _counter_evidence(
    request: InferProteinSubtypeMechanismRequest,
) -> tuple[KernelEvidenceReference, ...]:
    # The references are caller-declared and are deliberately not opened.
    return tuple(
        KernelEvidenceReference(
            reference=artifact,
            role="counter_evidence",
            claim="Caller-declared counter-evidence; issuer authority is not authenticated.",
        )
        for artifact in request.source_artifacts[:64]
    )


def _decimal(value: str) -> float:
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("mechanism probability is not numeric") from error  # noqa: TRY003
    if not number.is_finite() or not 0 <= number <= 1:
        raise ValueError(  # noqa: TRY003
            "mechanism probability must be finite and within [0, 1]"
        )
    return float(number)


def _parse_method(  # noqa: PLR0911
    method: str,
    *,
    counter_evidence: tuple[KernelEvidenceReference, ...],
    evidence: tuple[KernelEvidenceReference, ...],
) -> tuple[MechanismEstimate | None, MechanismFindingCode | None, str | None]:
    """Parse only the explicit provisional method grammar.

    ``posterior:mechanism-id:label:probability:lower:upper`` and
    ``state:mechanism-id:label:state`` are the only evaluable forms.  Labels
    and IDs cannot contain colons.  ``abstain:<reason>`` is an explicit safe
    failure path.
    """

    parts = method.split(":")
    kind = parts[0].lower() if parts else ""
    if kind in _ABSTAIN_METHODS:
        return None, MechanismFindingCode.MODEL_NOT_CALIBRATED, "Caller requested safe abstention."
    if kind not in _SUPPORTED_METHODS:
        return (
            None,
            MechanismFindingCode.MODEL_NOT_CALIBRATED,
            "Method is outside the closed grammar.",
        )
    if kind == "posterior":
        if len(parts) != _POSTERIOR_PARTS:
            return (
                None,
                MechanismFindingCode.MODEL_NOT_CALIBRATED,
                "Posterior method shape is invalid.",
            )
        mechanism_id, label = parts[1], parts[2]
        try:
            probability, lower, upper = (_decimal(value) for value in parts[3:])
        except ValueError:
            return (
                None,
                MechanismFindingCode.MODEL_NOT_CALIBRATED,
                "Posterior probability is invalid.",
            )
        if not mechanism_id or not label or lower > upper or not lower <= probability <= upper:
            return None, MechanismFindingCode.MODEL_NOT_CALIBRATED, "Posterior bounds are invalid."
        return (
            MechanismEstimate(
                estimate_id=f"estimate.{mechanism_id}",
                mechanism_id=mechanism_id,
                label=label,
                kind=MechanismEstimateKind.POSTERIOR,
                posterior_probability=probability,
                lower_bound=lower,
                upper_bound=upper,
                assumptions=(
                    "The approved model and calibration references are caller-declared.",
                    "The upstream variant-peptide hypothesis result is treated as opaque evidence.",
                ),
                alternatives=(
                    "Alternative mechanisms remain possible and require independent evidence.",
                ),
                counter_evidence=counter_evidence,
                evidence=evidence,
            ),
            None,
            None,
        )
    if len(parts) != _STATE_PARTS:
        return None, MechanismFindingCode.MODEL_NOT_CALIBRATED, "State method shape is invalid."
    mechanism_id, label, state_value = parts[1], parts[2], parts[3].lower()
    if not mechanism_id or not label or state_value not in _SUPPORTED_STATES:
        return (
            None,
            MechanismFindingCode.MODEL_NOT_CALIBRATED,
            "State value is outside the closed vocabulary.",
        )
    return (
        MechanismEstimate(
            estimate_id=f"estimate.{mechanism_id}",
            mechanism_id=mechanism_id,
            label=label,
            kind=MechanismEstimateKind.STATE,
            state_value=state_value,
            assumptions=(
                "The approved model and calibration references are caller-declared.",
                "The upstream variant-peptide hypothesis result is treated as opaque evidence.",
            ),
            alternatives=(
                "Alternative mechanisms remain possible and require independent evidence.",
            ),
            counter_evidence=counter_evidence,
            evidence=evidence,
        ),
        None,
        None,
    )


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="opaque_inputs",
            statement="Artifact references are immutable and are never traversed by this runtime.",
        ),
        Limitation(
            code="counter_evidence_preserved",
            statement=(
                "Assumptions, alternatives, and counter-evidence remain attached to every estimate."
            ),
        ),
        Limitation(
            code="prohibited_outputs",
            statement=(
                "No kinase activity, generic all-omics fusion, treatment recommendation, "
                "identity inference, or consent inference is emitted."
            ),
        ),
    ]
    if not supported:
        values.append(
            Limitation(
                code="safe_abstention",
                statement="No mechanism estimate is published outside the closed method grammar.",
            )
        )
    return tuple(values)


class M1404MechanismEngine:
    """Infer a caller-declared mechanism estimate with deterministic replay."""

    __slots__ = ()

    def infer(self, request: object) -> ProteinSubtypeMechanismInferenceResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self, request: InferProteinSubtypeMechanismRequest
    ) -> ProteinSubtypeMechanismInferenceResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        counter_evidence = _counter_evidence(request)
        estimate, finding_code, finding_message = _parse_method(
            request.configuration.method,
            counter_evidence=counter_evidence,
            evidence=evidence,
        )
        safe = estimate is not None and bool(counter_evidence)
        if estimate is None:
            safe = False
            finding_code = finding_code or MechanismFindingCode.MODEL_NOT_CALIBRATED
            finding_message = finding_message or "Mechanism estimate is not evaluable."
        elif not counter_evidence:
            safe = False
            finding_code = MechanismFindingCode.COUNTER_EVIDENCE_REQUIRED
            finding_message = "At least one counter-evidence reference is required."
        estimates = (estimate,) if safe and estimate is not None else ()
        findings = (
            ()
            if safe
            else (
                MechanismFinding(
                    finding_id=f"finding.{request.request_id}",
                    code=finding_code or MechanismFindingCode.COUNTER_EVIDENCE_REQUIRED,
                    message=finding_message or "Mechanism inference abstained.",
                    evidence=evidence,
                ),
            )
        )
        payload: dict[str, object] = {
            "output_type": "protein_subtype_mechanism_inference",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1404_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": MechanismInferenceStatus.INFERRED
            if safe
            else MechanismInferenceStatus.ABSTAINED,
            "estimates": estimates,
            "findings": findings,
            "abstention_reason": None
            if safe
            else (finding_message or "Mechanism inference abstained."),
            "parent_target": M1404_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED if safe else SupportStatus.UNSUPPORTED,
                reason_code=(
                    "m1404_provisional_mechanism_review_required"
                    if safe
                    else "m1404_mechanism_abstained"
                ),
                rationale=(
                    "Explicit posterior/state method, bounds, calibration references, and "
                    "counter-evidence passed."
                    if safe
                    else "The mechanism request is outside the safely evaluable support domain."
                ),
            ),
            "uncertainty": expected_uncertainty(supported=False if safe else safe),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=safe),
            "human_review_required": True if safe else not safe,
        }
        constructed = ProteinSubtypeMechanismInferenceResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinSubtypeMechanismInferenceResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1404ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1404ReplayVerificationError
        if replay:
            expected = self.infer(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1404ReplayVerificationError
        return validated


def infer_protein_subtype_mechanism(
    request: object,
) -> ProteinSubtypeMechanismInferenceResult:
    """Public provisional M14-04 operation."""

    return M1404MechanismEngine().infer(request)


__all__ = [
    "M1404MechanismAuthorizationError",
    "M1404MechanismEngine",
    "M1404ReplayVerificationError",
    "infer_protein_subtype_mechanism",
    "preflight_mechanism_authorization",
    "result_payload_digest",
]
