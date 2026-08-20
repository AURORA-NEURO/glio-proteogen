"""Deterministic authorization-first M17-07 typed export engine."""

# Audit-oriented branches are intentionally explicit.
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m17_07 import (
    M1707_CONTRACT_VERSION,
    M1707_EVIDENCE_CLAIM,
    M1707_MODULE_ID,
    CompatibilityMode,
    DownstreamContractObject,
    ExportFinding,
    ExportFindingCode,
    ExportOwnershipBinding,
    ExportStatus,
    ExportVariantPeptideDownstreamContractRequest,
    SignedContractEnvelope,
    VariantPeptideDownstreamExportResult,
    canonical_request_digest,
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
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ExportVariantPeptideDownstreamContractRequest)
_RESULT_ADAPTER: Final = TypeAdapter(VariantPeptideDownstreamExportResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M1707AuthorizationError(PermissionError):
    """Caller controls do not authorize downstream export."""

    def __init__(self) -> None:
        super().__init__(
            "M17-07 requires accepted controls, resolved identity, and granted consent"
        )


class M1707ReplayVerificationError(ValueError):
    """An M17-07 result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M17-07 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1707_authorization(candidate: object) -> None:
    """Check all seven controls before traversing export fields."""

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
        raise M1707AuthorizationError from None
    if states != expected:
        raise M1707AuthorizationError


def _prepare(candidate: object) -> object:
    preflight_m1707_authorization(candidate)
    return candidate


def _evidence(
    request: ExportVariantPeptideDownstreamContractRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    artifacts: list[ArtifactReference] = [
        request.adjudication_result,
        *request.source_artifacts,
        *(evidence.reference for field in request.fields for evidence in field.evidence),
        *(evidence.reference for evidence in request.configuration.evidence),
        request.consent.evidence,
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
    ]
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1707_EVIDENCE_CLAIM)
        for artifact in tuple(unique.values())[:64]
    )


def _uncertainty(*, estimable: bool) -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if estimable else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if estimable else None,
        rationale=(
            "Caller-declared typed fields, support, consent, and references are evaluable."
            if estimable
            else "Consent, support, compatibility, or upstream evidence is not safely exportable."
        ),
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=(
            "Field values, ownership, compatibility, consent, and signature authority are caller-declared.",
            "Unsupported or missing evidence is never converted into a negative export field.",
        ),
    )


def _provenance(
    request: ExportVariantPeptideDownstreamContractRequest,
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
            decision_id=reference.decision_id,
            state=str(_state(reference.state)),
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=getattr(reference, "binding_digest", None),
        )
        for role, reference in controls
    )
    input_digests = tuple(
        dict.fromkeys(
            (
                request_digest,
                request.adjudication_result.digest,
                *(artifact.digest for artifact in request.source_artifacts),
                *(field.value_digest for field in request.fields),
                *(evidence.reference.digest for evidence in request.configuration.evidence),
                request.consent.evidence.digest,
            )
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1707_MODULE_ID,
        module_version=M1707_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


def _classify(
    request: ExportVariantPeptideDownstreamContractRequest,
) -> tuple[ExportStatus, tuple[ExportFindingCode, ...]]:
    findings: list[ExportFindingCode] = []
    if request.consent.state is not ConsentState.GRANTED:
        findings.append(ExportFindingCode.CONSENT_WITHHELD)
    if request.support_decision.status is not SupportStatus.SUPPORTED:
        findings.append(ExportFindingCode.SUPPORT_BOUNDARY)
    if request.configuration.compatibility is CompatibilityMode.REVIEW_REQUIRED:
        findings.append(ExportFindingCode.COMPATIBILITY_MISMATCH)
    if findings:
        return ExportStatus.ABSTAINED, tuple(findings)
    findings.append(ExportFindingCode.PROVISIONAL_ABI_PENDING_REVIEW)
    return ExportStatus.EXPORTED, tuple(findings)


def _findings(
    codes: tuple[ExportFindingCode, ...],
    evidence: tuple[EvidenceReference, ...],
) -> tuple[ExportFinding, ...]:
    messages = {
        ExportFindingCode.FIELD_UNDOCUMENTED: "A field is not documented for this export.",
        ExportFindingCode.CONSENT_WITHHELD: "Consent is not granted; no downstream contract is exported.",
        ExportFindingCode.SUPPORT_BOUNDARY: "Support is outside the export envelope.",
        ExportFindingCode.COMPATIBILITY_MISMATCH: "Compatibility requires review before export.",
        ExportFindingCode.SIGNATURE_MISSING: "A signed contract envelope is unavailable.",
        ExportFindingCode.UPSTREAM_UNSUPPORTED: "The upstream adjudication is not safely exportable.",
        ExportFindingCode.PROVISIONAL_ABI_PENDING_REVIEW: "The provisional ABI requires governed owner review.",
    }
    return tuple(
        ExportFinding(
            finding_id=f"finding.m1707.{code.value}",
            code=code,
            message=messages[code],
            evidence=evidence[:1],
        )
        for code in codes
    )


def _limitations(*, abstained: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="caller_declared_export",
            statement="Field values, documentation, compatibility, support, consent, and signatures are caller-declared.",
        ),
        Limitation(
            code="typed_downstream_only",
            statement="The service emits only a signed typed contract object and never emits the variant-peptide parent result.",
        ),
        Limitation(
            code="prohibited_outputs",
            statement="No generic all-omics fusion, kinase activity, treatment recommendation, identity inference, or consent inference is emitted.",
        ),
    ]
    if abstained:
        values.append(
            Limitation(
                code="safe_abstention",
                statement="Unsupported, withheld, or incompatible inputs produce no downstream contract.",
            )
        )
    return tuple(values)


class M1707DownstreamTypedExportEngine:
    """Export documented immutable fields without changing upstream evidence."""

    __slots__ = ()

    def infer(self, request: object) -> VariantPeptideDownstreamExportResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self,
        request: ExportVariantPeptideDownstreamContractRequest,
    ) -> VariantPeptideDownstreamExportResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        status, codes = _classify(request)
        contract = None
        if status is ExportStatus.EXPORTED:
            contract_id = f"contract.{request_hash.removeprefix('sha256:')}"
            ownership = ExportOwnershipBinding(
                owning_module=M1707_MODULE_ID,
                owner="Data engineering",
                ownership_statement="M17-07 owns only this documented downstream typed export.",
                evidence=evidence[:1],
            )
            signed_payload = sha256_digest(
                {
                    "contract_id": contract_id,
                    "version": request.configuration.version,
                    "fields": request.fields,
                    "ownership": ownership,
                    "consent": request.consent,
                    "configuration": request.configuration,
                }
            )
            signature = SignedContractEnvelope(
                signer_id=request.context.actor_id,
                algorithm="caller-declared-sha256",
                signed_payload_digest=signed_payload,
                signature_digest=sha256_digest(
                    {
                        "signer_id": request.context.actor_id,
                        "algorithm": "caller-declared-sha256",
                        "signed_payload_digest": signed_payload,
                    }
                ),
                evidence=evidence[:1],
            )
            contract = DownstreamContractObject(
                contract_id=contract_id,
                version=request.configuration.version,
                fields=request.fields,
                ownership=ownership,
                consent=request.consent,
                support_decision=request.support_decision,
                configuration=request.configuration,
                signature=signature,
                uncertainty=_uncertainty(estimable=True),
                provenance=_provenance(request, request_hash),
                evidence=evidence,
            )
        payload: dict[str, object] = {
            "output_type": "variant_peptide_downstream_contract",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1707_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "contract": contract,
            "findings": _findings(codes, evidence),
            "abstention_reason": None
            if contract is not None
            else "Export inputs are not safely compatible.",
            "parent_target": "variant peptide",
            "emits_parent": False,
            "support_decision": (
                request.support_decision
                if contract is not None
                else SupportDecision(
                    status=SupportStatus.REVIEW_REQUIRED,
                    reason_code="m1707_export_abstained",
                    rationale="Consent, support, or compatibility limitations prevent safe export.",
                )
            ),
            "uncertainty": _uncertainty(estimable=contract is not None),
            "provenance": _provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(abstained=contract is None),
            "human_review_required": contract is None,
        }
        constructed = VariantPeptideDownstreamExportResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> VariantPeptideDownstreamExportResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1707ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1707ReplayVerificationError
        if replay:
            expected = self.infer(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1707ReplayVerificationError
        return validated


def export_variant_peptide_downstream_contract(
    request: object,
) -> VariantPeptideDownstreamExportResult:
    """Public provisional M17-07 operation."""

    return M1707DownstreamTypedExportEngine().infer(request)


__all__ = [
    "M1707AuthorizationError",
    "M1707DownstreamTypedExportEngine",
    "M1707ReplayVerificationError",
    "export_variant_peptide_downstream_contract",
    "preflight_m1707_authorization",
]
