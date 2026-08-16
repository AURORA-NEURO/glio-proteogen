"""Exact public derivation helpers for the M04-05 result envelope."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from glio_proteogen.contracts.m04_04 import ProteoformQualityDisposition
from glio_proteogen.contracts.m04_05.canonical import (
    canonical_request_digest,
    configuration_digest,
    contamination_flag_digest,
    event_digest,
    policy_digest,
    posterior_digest,
    profile_digest,
    receipt_digest,
)
from glio_proteogen.contracts.m04_05.v1 import (
    M0405_CONTRACT_VERSION,
    M0405_EVIDENCE_CLAIM,
    M0405_MODULE_ID,
    M0405_PARENT,
    M0405_RATE_SCALE,
    DetectProteoformArtifactsRequest,
    ProteoformArtifactComputationReceipt,
    ProteoformArtifactDetectorClass,
    ProteoformArtifactDisposition,
    ProteoformArtifactEvidenceLedger,
    ProteoformArtifactFinding,
    ProteoformArtifactFindingAction,
    ProteoformArtifactFindingCode,
    ProteoformArtifactObservationState,
    ProteoformArtifactPosterior,
    ProteoformArtifactPosteriorState,
    ProteoformArtifactProfile,
    ProteoformArtifactSeverity,
    ProteoformContaminationFlag,
    ProteoformExclusionMaskEntry,
    ProteoformExclusionReasonCode,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
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

_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_CONTAMINATION_CLASSES: Final = frozenset(
    {
        ProteoformArtifactDetectorClass.CONTAMINATION,
        ProteoformArtifactDetectorClass.BARCODE_INDEX,
    }
)
_ACTION_BY_FINDING: Final = {
    ProteoformArtifactFindingCode.UPSTREAM_QUARANTINED: (
        ProteoformArtifactFindingAction.QUARANTINE
    ),
    ProteoformArtifactFindingCode.UPSTREAM_ABSTAINED: (ProteoformArtifactFindingAction.ABSTAIN),
    ProteoformArtifactFindingCode.EVIDENCE_LEDGER_BINDING_MISMATCH: (
        ProteoformArtifactFindingAction.QUARANTINE
    ),
    ProteoformArtifactFindingCode.DETECTOR_PROFILE_UNSUPPORTED: (
        ProteoformArtifactFindingAction.ABSTAIN
    ),
    ProteoformArtifactFindingCode.EVIDENCE_MISSING: (ProteoformArtifactFindingAction.ABSTAIN),
    ProteoformArtifactFindingCode.EVIDENCE_UNSUPPORTED: (ProteoformArtifactFindingAction.ABSTAIN),
    ProteoformArtifactFindingCode.EVIDENCE_NOT_EVALUABLE: (ProteoformArtifactFindingAction.ABSTAIN),
    ProteoformArtifactFindingCode.ARTIFACT_SUSPECTED: (ProteoformArtifactFindingAction.QUARANTINE),
    ProteoformArtifactFindingCode.ARTIFACT_DETECTED: (ProteoformArtifactFindingAction.QUARANTINE),
    ProteoformArtifactFindingCode.CONTAMINATION_FLAGGED: (
        ProteoformArtifactFindingAction.QUARANTINE
    ),
}


@dataclass(frozen=True, slots=True)
class ProteoformArtifactExpectedBundle:
    artifact_posteriors: tuple[ProteoformArtifactPosterior, ...]
    contamination_flags: tuple[ProteoformContaminationFlag, ...]
    exclusion_mask: tuple[ProteoformExclusionMaskEntry, ...]
    findings: tuple[ProteoformArtifactFinding, ...]
    disposition: ProteoformArtifactDisposition
    receipt: ProteoformArtifactComputationReceipt
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...]
    limitations: tuple[Limitation, ...]
    human_review_required: bool


def matching_artifact_profile(
    request: DetectProteoformArtifactsRequest,
) -> ProteoformArtifactProfile | None:
    """Return the unique reviewed profile for the M04-04 contract version, if supported."""

    matches = tuple(
        profile
        for profile in request.policy.profiles
        if (
            request.quality_result.result_version in profile.approved_quality_contract_versions
            and request.quality_result.configuration_digest
            in profile.approved_quality_configuration_digests
        )
    )
    return matches[0] if len(matches) == 1 else None


def _traversable(request: DetectProteoformArtifactsRequest) -> bool:
    ledger = request.evidence_ledger
    return (
        request.quality_result.disposition is ProteoformQualityDisposition.QUALIFIED
        and matching_artifact_profile(request) is not None
        and type(ledger) is ProteoformArtifactEvidenceLedger
        and ledger.quality_result_digest == request.quality_result.result_digest
    )


def _event_evidence(
    artifacts: tuple[ArtifactReference, ...],
) -> tuple[EvidenceReference, ...]:
    return tuple(
        sorted(
            (
                EvidenceReference(
                    reference=artifact,
                    role="evidence",
                    claim=M0405_EVIDENCE_CLAIM,
                )
                for artifact in artifacts
            ),
            key=canonical_json_bytes,
        )
    )


def _posterior_support(state: ProteoformArtifactPosteriorState) -> SupportDecision:
    if state is ProteoformArtifactPosteriorState.CLEAR:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="m0405.posterior.clear",
            rationale="Observed aggregate evidence remains below the reviewed threshold.",
        )
    if state in {
        ProteoformArtifactPosteriorState.SUSPECTED,
        ProteoformArtifactPosteriorState.DETECTED,
    }:
        return SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="m0405.posterior.artifact",
            rationale="Observed aggregate evidence meets a reviewed artifact threshold.",
        )
    return SupportDecision(
        status=SupportStatus.UNSUPPORTED,
        reason_code="m0405.posterior.indeterminate",
        rationale="Missing, unsupported, or out-of-domain evidence is not a negative finding.",
    )


def expected_artifact_posteriors(
    request: DetectProteoformArtifactsRequest,
) -> tuple[ProteoformArtifactPosterior, ...]:
    """Derive one exact categorical posterior for every traversable event."""

    if not _traversable(request):
        return ()
    profile = matching_artifact_profile(request)
    ledger = request.evidence_ledger
    if profile is None or type(ledger) is not ProteoformArtifactEvidenceLedger:
        return ()
    thresholds = {item.detector_class: item for item in profile.thresholds}
    output: list[ProteoformArtifactPosterior] = []
    for event in ledger.events:
        score: int | None = None
        lower: int | None = None
        upper: int | None = None
        if event.observation_state is ProteoformArtifactObservationState.OBSERVED:
            score = (
                event.supporting_count * M0405_RATE_SCALE + event.evaluated_count // 2
            ) // event.evaluated_count
            resolution = (M0405_RATE_SCALE + event.evaluated_count - 1) // event.evaluated_count
            lower = max(0, score - resolution)
            upper = min(M0405_RATE_SCALE, score + resolution)
            threshold = thresholds[event.detector_class]
            state = (
                ProteoformArtifactPosteriorState.DETECTED
                if score >= threshold.exclusion_threshold_ppm
                else ProteoformArtifactPosteriorState.SUSPECTED
                if score >= threshold.review_threshold_ppm
                else ProteoformArtifactPosteriorState.CLEAR
            )
        else:
            state = ProteoformArtifactPosteriorState.INDETERMINATE
        payload: dict[str, object] = {
            "posterior_digest": _ZERO_DIGEST,
            "target_id": event.target_id,
            "unit_kind": event.unit_kind,
            "detector_class": event.detector_class,
            "observation_state": event.observation_state,
            "state": state,
            "posterior_ppm": score,
            "lower_bound_ppm": lower,
            "upper_bound_ppm": upper,
            "score_is_calibrated_probability": False,
            "support": _posterior_support(state),
            "evidence": _event_evidence(event.evidence),
        }
        assembled = ProteoformArtifactPosterior.model_construct(**payload)  # type: ignore[arg-type]
        payload["posterior_digest"] = posterior_digest(assembled)
        output.append(ProteoformArtifactPosterior.model_validate(payload, strict=True))
    return tuple(sorted(output, key=canonical_json_bytes))


def expected_contamination_flags(
    request: DetectProteoformArtifactsRequest,
    posteriors: tuple[ProteoformArtifactPosterior, ...] | None = None,
) -> tuple[ProteoformContaminationFlag, ...]:
    """Emit triggered contamination flags only; absence never means negative."""

    active = posteriors if posteriors is not None else expected_artifact_posteriors(request)
    flags: list[ProteoformContaminationFlag] = []
    for posterior in active:
        if posterior.detector_class not in _CONTAMINATION_CLASSES or posterior.state not in {
            ProteoformArtifactPosteriorState.SUSPECTED,
            ProteoformArtifactPosteriorState.DETECTED,
        }:
            continue
        digest = sha256_digest(
            {
                "module_id": M0405_MODULE_ID,
                "target_id": posterior.target_id,
                "detector_class": posterior.detector_class,
                "posterior_digest": posterior.posterior_digest,
            }
        ).removeprefix("sha256:")
        flags.append(
            ProteoformContaminationFlag(
                flag_id=f"flag.{digest}",
                target_id=posterior.target_id,
                detector_class=posterior.detector_class,
                posterior_digest=posterior.posterior_digest,
                severity=(
                    ProteoformArtifactSeverity.EXCLUDE
                    if posterior.state is ProteoformArtifactPosteriorState.DETECTED
                    else ProteoformArtifactSeverity.REVIEW
                ),
                evidence=posterior.evidence,
                review_required=True,
            )
        )
    return tuple(sorted(flags, key=canonical_json_bytes))


def expected_exclusion_mask(
    request: DetectProteoformArtifactsRequest,
    posteriors: tuple[ProteoformArtifactPosterior, ...] | None = None,
    flags: tuple[ProteoformContaminationFlag, ...] | None = None,
) -> tuple[ProteoformExclusionMaskEntry, ...]:
    """Return excluded-only target entries; retained targets are represented by clear posteriors."""

    active = posteriors if posteriors is not None else expected_artifact_posteriors(request)
    active_flags = flags if flags is not None else expected_contamination_flags(request, active)
    target_ids = sorted(
        {
            item.target_id
            for item in active
            if item.state is ProteoformArtifactPosteriorState.DETECTED
        }
    )
    output: list[ProteoformExclusionMaskEntry] = []
    for target_id in target_ids:
        detected = tuple(
            item
            for item in active
            if item.target_id == target_id
            and item.state is ProteoformArtifactPosteriorState.DETECTED
        )
        detected_digests = {item.posterior_digest for item in detected}
        evidence = tuple(
            sorted(
                {item for posterior in detected for item in posterior.evidence},
                key=canonical_json_bytes,
            )
        )
        output.append(
            ProteoformExclusionMaskEntry(
                target_id=target_id,
                triggering_posterior_digests=tuple(sorted(detected_digests)),
                triggering_flag_ids=tuple(
                    sorted(
                        flag.flag_id
                        for flag in active_flags
                        if flag.target_id == target_id and flag.posterior_digest in detected_digests
                    )
                ),
                reason_code=ProteoformExclusionReasonCode.CRITICAL_ARTIFACT_DETECTED,
                evidence=evidence,
                review_required=True,
            )
        )
    return tuple(sorted(output, key=canonical_json_bytes))


def finding_for(
    code: ProteoformArtifactFindingCode,
    *,
    target_ids: tuple[str, ...] = (),
    detector_classes: tuple[ProteoformArtifactDetectorClass, ...] = (),
) -> ProteoformArtifactFinding:
    canonical_targets = tuple(sorted(set(target_ids)))
    canonical_classes = tuple(sorted(set(detector_classes)))
    finding_hash = sha256_digest(
        {
            "module_id": M0405_MODULE_ID,
            "code": code,
            "target_ids": canonical_targets,
            "detector_classes": canonical_classes,
        }
    ).removeprefix("sha256:")
    return ProteoformArtifactFinding(
        finding_id=f"finding.m0405.{finding_hash}",
        code=code,
        action=_ACTION_BY_FINDING[code],
        message=code.value.replace("_", " ").capitalize() + ".",
        target_ids=canonical_targets,
        detector_classes=canonical_classes,
    )


def expected_result_id(request: DetectProteoformArtifactsRequest) -> str:
    request_hash = canonical_request_digest(request).removeprefix("sha256:")
    return f"result.m0405.{request_hash}"


def expected_artifact_findings(
    request: DetectProteoformArtifactsRequest,
    posteriors: tuple[ProteoformArtifactPosterior, ...] | None = None,
    flags: tuple[ProteoformContaminationFlag, ...] | None = None,
) -> tuple[ProteoformArtifactFinding, ...]:
    """Aggregate every reachable finding by its closed public code."""

    upstream = request.quality_result.disposition
    if upstream is ProteoformQualityDisposition.QUARANTINED:
        return (finding_for(ProteoformArtifactFindingCode.UPSTREAM_QUARANTINED),)
    if upstream is ProteoformQualityDisposition.ABSTAINED:
        return (finding_for(ProteoformArtifactFindingCode.UPSTREAM_ABSTAINED),)
    if matching_artifact_profile(request) is None:
        return (finding_for(ProteoformArtifactFindingCode.DETECTOR_PROFILE_UNSUPPORTED),)
    ledger = request.evidence_ledger
    if ledger is None:  # pragma: no cover - exact request traversal closure rejects this.
        return ()
    if type(ledger) is not ProteoformArtifactEvidenceLedger or (
        ledger.quality_result_digest != request.quality_result.result_digest
    ):
        return (finding_for(ProteoformArtifactFindingCode.EVIDENCE_LEDGER_BINDING_MISMATCH),)
    active = posteriors if posteriors is not None else expected_artifact_posteriors(request)
    active_flags = flags if flags is not None else expected_contamination_flags(request, active)
    grouped: dict[
        ProteoformArtifactFindingCode,
        tuple[set[str], set[ProteoformArtifactDetectorClass]],
    ] = {}

    def record(code: ProteoformArtifactFindingCode, item: ProteoformArtifactPosterior) -> None:
        targets, classes = grouped.setdefault(code, (set(), set()))
        targets.add(item.target_id)
        classes.add(item.detector_class)

    profile = matching_artifact_profile(request)
    required = (
        {item.detector_class: item.required for item in profile.thresholds}
        if profile is not None
        else {}
    )
    for posterior in active:
        if posterior.observation_state is ProteoformArtifactObservationState.MISSING:
            record(ProteoformArtifactFindingCode.EVIDENCE_MISSING, posterior)
        elif posterior.observation_state is ProteoformArtifactObservationState.UNSUPPORTED:
            record(ProteoformArtifactFindingCode.EVIDENCE_UNSUPPORTED, posterior)
        elif (
            posterior.observation_state is ProteoformArtifactObservationState.NOT_APPLICABLE
            and required.get(posterior.detector_class, False)
        ):
            record(ProteoformArtifactFindingCode.EVIDENCE_NOT_EVALUABLE, posterior)
        if posterior.state is ProteoformArtifactPosteriorState.SUSPECTED:
            record(ProteoformArtifactFindingCode.ARTIFACT_SUSPECTED, posterior)
        elif posterior.state is ProteoformArtifactPosteriorState.DETECTED:
            record(ProteoformArtifactFindingCode.ARTIFACT_DETECTED, posterior)
    if active_flags:
        grouped[ProteoformArtifactFindingCode.CONTAMINATION_FLAGGED] = (
            {item.target_id for item in active_flags},
            {item.detector_class for item in active_flags},
        )
    return tuple(
        sorted(
            (
                finding_for(
                    code,
                    target_ids=tuple(targets),
                    detector_classes=tuple(classes),
                )
                for code, (targets, classes) in grouped.items()
            ),
            key=canonical_json_bytes,
        )
    )


def expected_disposition(  # noqa: PLR0911 - explicit safe-failure precedence.
    request: DetectProteoformArtifactsRequest,
    posteriors: tuple[ProteoformArtifactPosterior, ...] | None = None,
) -> ProteoformArtifactDisposition:
    upstream = request.quality_result.disposition
    if upstream is ProteoformQualityDisposition.QUARANTINED:
        return ProteoformArtifactDisposition.QUARANTINED
    if upstream is ProteoformQualityDisposition.ABSTAINED:
        return ProteoformArtifactDisposition.ABSTAINED
    if matching_artifact_profile(request) is None:
        return ProteoformArtifactDisposition.ABSTAINED
    ledger = request.evidence_ledger
    if ledger is None:  # pragma: no cover - exact request traversal closure rejects this.
        return ProteoformArtifactDisposition.ABSTAINED
    if type(ledger) is not ProteoformArtifactEvidenceLedger or (
        ledger.quality_result_digest != request.quality_result.result_digest
    ):
        return ProteoformArtifactDisposition.QUARANTINED
    active = posteriors if posteriors is not None else expected_artifact_posteriors(request)
    if any(
        item.state
        in {
            ProteoformArtifactPosteriorState.SUSPECTED,
            ProteoformArtifactPosteriorState.DETECTED,
        }
        for item in active
    ):
        return ProteoformArtifactDisposition.QUARANTINED
    profile = matching_artifact_profile(request)
    required = (
        {item.detector_class: item.required for item in profile.thresholds}
        if profile is not None
        else {}
    )
    if any(
        item.observation_state
        in {
            ProteoformArtifactObservationState.MISSING,
            ProteoformArtifactObservationState.UNSUPPORTED,
        }
        or (
            item.observation_state is ProteoformArtifactObservationState.NOT_APPLICABLE
            and required.get(item.detector_class, False)
        )
        for item in active
    ):
        return ProteoformArtifactDisposition.ABSTAINED
    return ProteoformArtifactDisposition.CLEARED


def expected_support(disposition: ProteoformArtifactDisposition) -> SupportDecision:
    if disposition is ProteoformArtifactDisposition.CLEARED:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="m0405.detector.cleared",
            rationale="Every required artifact class is observed and below reviewed thresholds.",
        )
    if disposition is ProteoformArtifactDisposition.QUARANTINED:
        return SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="m0405.detector.quarantined",
            rationale="Artifact evidence or a binding conflict requires quarantine and review.",
        )
    return SupportDecision(
        status=SupportStatus.UNSUPPORTED,
        reason_code="m0405.detector.abstained",
        rationale="Unsupported, missing, or out-of-domain evidence cannot support detection.",
    )


def expected_uncertainty() -> UncertaintyProfile:
    rationales = (
        "Measurement uncertainty is not estimated from aggregate event counts.",
        "Sampling uncertainty is not estimated by this deterministic detector.",
        "No parameters are fitted by the reviewed threshold evaluator.",
        "No calibrated classifier or proteotype model is executed.",
        "Feature, protein, proteoform, and kinase identity remain outside this detector.",
        "Support uncertainty is represented by explicit abstention and review states.",
        "Transportability requires external assay-specific validation.",
    )
    estimates = tuple(
        UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            probability=None,
            rationale=rationale,
        )
        for rationale in rationales
    )
    return UncertaintyProfile(
        measurement=estimates[0],
        sampling=estimates[1],
        parameter=estimates[2],
        model_form=estimates[3],
        identification=estimates[4],
        support=estimates[5],
        transport=estimates[6],
        sensitivity_notes=tuple(
            sorted(
                (
                    "Missing and unsupported inputs remain typed; they never become negative "
                    "findings.",
                    "Posterior ppm values are deterministic evidence fractions, not probabilities.",
                    "Novel or out-of-domain states abstain and require human review.",
                )
            )
        ),
    )


def expected_control_decisions(
    request: DetectProteoformArtifactsRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    records = (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=refs.approved_configuration.decision_id,
            state=refs.approved_configuration.state.value,
            policy_version=refs.approved_configuration.policy_version,
            evidence_digest=refs.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=refs.identity_lineage.decision_id,
            state=refs.identity_lineage.state.value,
            policy_version=refs.identity_lineage.policy_version,
            evidence_digest=refs.identity_lineage.evidence.digest,
            subject_digest=refs.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=refs.provenance.decision_id,
            state=refs.provenance.state.value,
            policy_version=refs.provenance.policy_version,
            evidence_digest=refs.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=refs.consent.decision_id,
            state=refs.consent.state.value,
            policy_version=refs.consent.policy_version,
            evidence_digest=refs.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=refs.quality.decision_id,
            state=refs.quality.state.value,
            policy_version=refs.quality.policy_version,
            evidence_digest=refs.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=refs.support.decision_id,
            state=refs.support.state.value,
            policy_version=refs.support.policy_version,
            evidence_digest=refs.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=refs.intended_use.decision_id,
            state=refs.intended_use.state.value,
            policy_version=refs.intended_use.policy_version,
            evidence_digest=refs.intended_use.evidence.digest,
        ),
    )
    return tuple(sorted(records, key=canonical_json_bytes))


def artifact_evidence_index(
    request: DetectProteoformArtifactsRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    artifacts: list[ArtifactReference] = [
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
        request.policy.evidence,
    ]
    profile = (
        matching_artifact_profile(request)
        if request.quality_result.disposition is ProteoformQualityDisposition.QUALIFIED
        else None
    )
    if profile is not None:
        artifacts.append(profile.evidence)
        artifacts.extend(item.evidence for item in profile.thresholds)
    if request.evidence_ledger is not None:
        artifacts.append(request.evidence_ledger.evidence)
    return tuple(
        sorted(
            (
                EvidenceReference(
                    reference=artifact,
                    role="evidence",
                    claim=M0405_EVIDENCE_CLAIM,
                )
                for artifact in artifacts
            ),
            key=canonical_json_bytes,
        )
    )


def expected_provenance(request: DetectProteoformArtifactsRequest) -> ProvenanceRecord:
    refs = request.context.references
    profile = (
        matching_artifact_profile(request)
        if request.quality_result.disposition is ProteoformQualityDisposition.QUALIFIED
        else None
    )
    request_hash = canonical_request_digest(request)
    digests = {
        request_hash,
        request.quality_result.result_digest,
        request.quality_result.receipt_digest,
        policy_digest(request.policy),
    }
    if profile is not None:
        digests.add(profile_digest(profile))
    if request.evidence_ledger is not None:
        digests.add(request.evidence_ledger.ledger_digest)
    if request.supersedes_result_digest is not None:
        digests.add(request.supersedes_result_digest)
    return ProvenanceRecord(
        activity_id=f"activity.m0405.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0405_MODULE_ID,
        module_version=M0405_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(sorted(digests)),
        configuration_digest=configuration_digest(request.policy),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=expected_control_decisions(request),
    )


def expected_limitations() -> tuple[Limitation, ...]:
    return tuple(
        sorted(
            (
                Limitation(
                    code="proteoform_artifact_mask_only",
                    statement=(
                        "Output is limited to artifact posteriors, contamination flags, "
                        "and exclusions."
                    ),
                ),
                Limitation(
                    code="evidence_score_not_probability",
                    statement=(
                        "Posterior ppm fields are uncalibrated deterministic evidence fractions."
                    ),
                ),
                Limitation(
                    code="no_biological_or_clinical_inference",
                    statement=(
                        "No identity, proteoform, kinase, fusion, subtype, or treatment claim "
                        "is made."
                    ),
                ),
            ),
            key=canonical_json_bytes,
        )
    )


def expected_receipt(  # noqa: PLR0913 - every exact result region closes the receipt.
    request: DetectProteoformArtifactsRequest,
    *,
    posteriors: tuple[ProteoformArtifactPosterior, ...],
    flags: tuple[ProteoformContaminationFlag, ...],
    exclusion_mask: tuple[ProteoformExclusionMaskEntry, ...],
    findings: tuple[ProteoformArtifactFinding, ...],
    disposition: ProteoformArtifactDisposition,
) -> ProteoformArtifactComputationReceipt:
    upstream = request.quality_result
    profile = (
        matching_artifact_profile(request)
        if upstream.disposition is ProteoformQualityDisposition.QUALIFIED
        else None
    )
    traversed = _traversable(request)
    ledger = request.evidence_ledger
    payload: dict[str, object] = {
        "quality_result_digest": upstream.result_digest,
        "quality_request_digest": upstream.request_digest,
        "quality_policy_digest": upstream.policy_digest,
        "quality_configuration_digest": upstream.configuration_digest,
        "quality_receipt_digest": upstream.receipt_digest,
        "identity_resolution_digest": upstream.receipt.identity_resolution_digest,
        "protocol_result_digest": upstream.receipt.protocol_result_digest,
        "reference_bundle_digest": upstream.receipt.reference_bundle_digest,
        "coordinate_policy_digest": upstream.receipt.coordinate_policy_digest,
        "intended_use_evidence_digest": upstream.receipt.intended_use_evidence_digest,
        "detector_policy_digest": policy_digest(request.policy),
        "detector_configuration_digest": configuration_digest(request.policy),
        "selected_profile_digest": profile_digest(profile) if profile is not None else None,
        "evidence_ledger_digest": ledger.ledger_digest if ledger is not None else None,
        "event_digests": (
            tuple(sorted(event_digest(item) for item in ledger.events))
            if traversed and type(ledger) is ProteoformArtifactEvidenceLedger
            else ()
        ),
        "posterior_digests": tuple(item.posterior_digest for item in posteriors),
        "contamination_flag_digests": tuple(contamination_flag_digest(item) for item in flags),
        "excluded_target_ids": tuple(item.target_id for item in exclusion_mask),
        "finding_codes": tuple(item.code for item in findings),
        "parent_target": M0405_PARENT,
        "emits_parent": False,
        "disposition": disposition,
        "receipt_digest": _ZERO_DIGEST,
    }
    assembled = ProteoformArtifactComputationReceipt.model_construct(**payload)  # type: ignore[arg-type]
    payload["receipt_digest"] = receipt_digest(assembled)
    return ProteoformArtifactComputationReceipt.model_validate(payload, strict=True)


def expected_detection_bundle(
    request: DetectProteoformArtifactsRequest,
) -> ProteoformArtifactExpectedBundle:
    """Derive every mutable-looking region of one result from the sealed request."""

    posteriors = expected_artifact_posteriors(request)
    flags = expected_contamination_flags(request, posteriors)
    exclusion_mask = expected_exclusion_mask(request, posteriors, flags)
    findings = expected_artifact_findings(request, posteriors, flags)
    disposition = expected_disposition(request, posteriors)
    return ProteoformArtifactExpectedBundle(
        artifact_posteriors=posteriors,
        contamination_flags=flags,
        exclusion_mask=exclusion_mask,
        findings=findings,
        disposition=disposition,
        receipt=expected_receipt(
            request,
            posteriors=posteriors,
            flags=flags,
            exclusion_mask=exclusion_mask,
            findings=findings,
            disposition=disposition,
        ),
        support=expected_support(disposition),
        uncertainty=expected_uncertainty(),
        provenance=expected_provenance(request),
        evidence=artifact_evidence_index(request),
        limitations=expected_limitations(),
        human_review_required=(
            disposition is not ProteoformArtifactDisposition.CLEARED
            or any(
                item.state is ProteoformArtifactPosteriorState.INDETERMINATE for item in posteriors
            )
        ),
    )


__all__ = [
    "ProteoformArtifactExpectedBundle",
    "artifact_evidence_index",
    "expected_artifact_findings",
    "expected_artifact_posteriors",
    "expected_contamination_flags",
    "expected_control_decisions",
    "expected_detection_bundle",
    "expected_disposition",
    "expected_exclusion_mask",
    "expected_limitations",
    "expected_provenance",
    "expected_receipt",
    "expected_result_id",
    "expected_support",
    "expected_uncertainty",
    "finding_for",
    "matching_artifact_profile",
]
