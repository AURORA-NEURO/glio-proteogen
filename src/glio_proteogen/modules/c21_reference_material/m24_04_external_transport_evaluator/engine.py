"""Deterministic external transport evaluation for provisional M24-04."""

from __future__ import annotations

from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_04 import (
    M2404_CONTRACT_VERSION,
    M2404_EVIDENCE_CLAIM,
    M2404_MODULE_ID,
    BiomarkerPanelExternalTransportResult,
    EvaluateBiomarkerPanelExternalTransportRequest,
    EvaluationStatus,
    SupportDomainUpdate,
    TransportabilityReport,
    TransportFinding,
    TransportFindingCode,
    TransportStatus,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import Limitation, SupportStatus
from glio_proteogen.kernel.strict_json import strict_json_loads

from .._m24_runtime_common import (
    AuthorizationError,
    evidence,
    preflight,
    provenance,
    support,
    uncertainty,
)

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateBiomarkerPanelExternalTransportRequest)
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_transport",
        statement=(
            "Transport metrics, validation records, thresholds and evidence are caller-declared; "
            "the evaluator does not inspect raw cohort data or authenticate issuers."
        ),
    ),
    Limitation(
        code="support_domain_only",
        statement=(
            "The result reports support-domain material only and emits no biomarker, protein, "
            "proteoform, isoform, glioma, treatment or mechanism claim."
        ),
    ),
    Limitation(
        code="provisional_abi",
        statement="M24-04 remains 0.1.0-provisional pending Bioinformatics owner confirmation.",
    ),
)


class M2404ReplayError(ValueError):
    """Raised when an M24-04 result fails semantic replay."""


def _result_id(request_digest: str) -> str:
    return "m2404.result." + request_digest.removeprefix("sha256:")


def _findings(
    request: EvaluateBiomarkerPanelExternalTransportRequest,
) -> tuple[TransportFinding, ...]:
    findings: list[TransportFinding] = []
    by_dimension = {item.dimension: item for item in request.evaluations}
    validation_dims = {item.dimension for item in request.validations}
    for dimension in request.configuration.required_dimensions:
        if dimension not in validation_dims:
            findings.append(
                TransportFinding(
                    finding_id=f"m2404.validation.{dimension.value}",
                    code=TransportFindingCode.DIMENSION_UNVALIDATED,
                    message=f"{dimension.value} has no independent validation record.",
                    evidence=evidence(request.source_artifacts, M2404_EVIDENCE_CLAIM),
                )
            )
        evaluation = by_dimension.get(dimension)
        if evaluation is None:
            findings.append(
                TransportFinding(
                    finding_id=f"m2404.evaluation.{dimension.value}",
                    code=TransportFindingCode.EVALUATION_INCOMPLETE,
                    message=f"{dimension.value} has no transport evaluation.",
                    evidence=evidence(request.source_artifacts, M2404_EVIDENCE_CLAIM),
                )
            )
        elif evaluation.status is not TransportStatus.SUPPORTED:
            code = (
                TransportFindingCode.CALIBRATION_FLOOR_FAILED
                if evaluation.status is TransportStatus.DOMAIN_NARROWED
                else TransportFindingCode.EVALUATION_INCOMPLETE
            )
            findings.append(
                TransportFinding(
                    finding_id=f"m2404.status.{dimension.value}",
                    code=code,
                    message=(
                        f"{dimension.value} is {evaluation.status.value}; support domain "
                        "must be narrowed or reviewed."
                    ),
                    evidence=evidence(request.source_artifacts, M2404_EVIDENCE_CLAIM),
                )
            )
        elif evaluation.metric_value < request.configuration.minimum_calibration_floor:
            findings.append(
                TransportFinding(
                    finding_id=f"m2404.floor.{dimension.value}",
                    code=TransportFindingCode.CALIBRATION_FLOOR_FAILED,
                    message=(
                        f"{dimension.value} metric {evaluation.metric_value:.6g} is below "
                        "the configured minimum calibration floor "
                        f"{request.configuration.minimum_calibration_floor:.6g}."
                    ),
                    evidence=evidence(request.source_artifacts, M2404_EVIDENCE_CLAIM),
                )
            )
    return tuple(findings)


class M2404ExternalTransportEvaluator:
    """Evaluate caller-declared transport metrics without extrapolation."""

    __slots__ = ()

    def evaluate(self, request: object) -> BiomarkerPanelExternalTransportResult:
        if isinstance(request, bytes | bytearray | str):
            decoded = strict_json_loads(request)
            validated = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            preflight(request, M2404_MODULE_ID)
            validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight(validated, M2404_MODULE_ID)
        canonical = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(validated), strict=True)
        request_digest = canonical_request_digest(canonical)
        findings = _findings(canonical)
        supported = not findings
        report = None
        if supported:
            retained = canonical.configuration.required_dimensions
            update = SupportDomainUpdate(
                update_id=f"m2404.support.{request_digest.removeprefix('sha256:')}",
                version=canonical.configuration.version,
                status=TransportStatus.SUPPORTED,
                retained_dimensions=retained,
                narrowed_dimensions=(),
                rationale=(
                    "Every configured transport dimension has independent validation and "
                    "meets the configured minimum calibration floor."
                ),
                evidence=evidence(canonical.source_artifacts, M2404_EVIDENCE_CLAIM),
            )
            report = TransportabilityReport(
                report_id=f"m2404.report.{request_digest.removeprefix('sha256:')}",
                version=canonical.configuration.version,
                validations=canonical.validations,
                evaluations=canonical.evaluations,
                support_domain=update,
                configuration=canonical.configuration,
                evidence=evidence(canonical.source_artifacts, M2404_EVIDENCE_CLAIM),
            )
        payload: dict[str, Any] = {
            "output_type": "biomarker_panel_external_transport",
            "result_id": _result_id(request_digest),
            "result_version": M2404_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": "sha256:" + "0" * 64,
            "request": canonical,
            "status": EvaluationStatus.EVALUATED if supported else EvaluationStatus.ABSTAINED,
            "report": report,
            "findings": findings,
            "abstention_reason": (
                None
                if supported
                else "M24-04 abstained pending transport validation and support-domain review."
            ),
            "parent_target": "biomarker panel",
            "emits_parent": False,
            "support_decision": support(
                SupportStatus.SUPPORTED if supported else SupportStatus.REVIEW_REQUIRED,
                "transport_evaluation_complete" if supported else "transport_review_required",
                (
                    "All required external transport dimensions are supported."
                    if supported
                    else "One or more transport dimensions cannot support the requested domain."
                ),
            ),
            "uncertainty": uncertainty(M2404_MODULE_ID),
            "provenance": provenance(
                canonical.context,
                (
                    canonical.mass_spectrometry_proteome,
                    canonical.genome_transcriptome,
                    canonical.ptm_annotations,
                    canonical.benchmark_package,
                    *canonical.source_artifacts,
                ),
                request_digest,
                M2404_MODULE_ID,
                M2404_CONTRACT_VERSION,
                canonical_request_digest(canonical.configuration),
            ),
            "evidence": evidence(
                (
                    canonical.mass_spectrometry_proteome,
                    canonical.genome_transcriptome,
                    canonical.ptm_annotations,
                    canonical.benchmark_package,
                    *canonical.source_artifacts,
                ),
                M2404_EVIDENCE_CLAIM,
            ),
            "limitations": _LIMITATIONS,
            "human_review_required": True,
        }
        provisional = BiomarkerPanelExternalTransportResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return BiomarkerPanelExternalTransportResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )

    def verify_replay(
        self, result: BiomarkerPanelExternalTransportResult
    ) -> BiomarkerPanelExternalTransportResult:
        if result.request_digest != canonical_request_digest(result.request):
            raise M2404ReplayError("M24-04 request digest mismatch")  # noqa: TRY003
        if result.result_id != _result_id(result.request_digest):
            raise M2404ReplayError("M24-04 result identifier mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M2404ReplayError("M24-04 result payload digest mismatch")  # noqa: TRY003
        try:
            replayed = BiomarkerPanelExternalTransportResult.model_validate_json(
                canonical_json_bytes(result), strict=True
            )
            expected = self.evaluate(replayed.request)
        except Exception as error:
            raise M2404ReplayError from error
        if canonical_json_bytes(expected) != canonical_json_bytes(replayed):
            raise M2404ReplayError("M24-04 semantic replay mismatch")  # noqa: TRY003
        return replayed


def evaluate_biomarker_panel_external_transport(
    request: object,
) -> BiomarkerPanelExternalTransportResult:
    return M2404ExternalTransportEvaluator().evaluate(request)


def preflight_m2404_authorization(candidate: object) -> None:
    preflight(candidate, M2404_MODULE_ID)


__all__ = [
    "AuthorizationError",
    "M2404ExternalTransportEvaluator",
    "M2404ReplayError",
    "evaluate_biomarker_panel_external_transport",
    "preflight_m2404_authorization",
]
