"""Focused M03-05 deterministic artifact-detector lifecycle tests."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import timedelta
from typing import TYPE_CHECKING, cast

import pytest
from evals.m03_04.run import build_scenario
from pydantic import ValidationError

from glio_proteogen.contracts.m03_03 import ProteinInferenceRawRole
from glio_proteogen.contracts.m03_05 import (
    M0305_SCORE_LIMITATION_CODE,
    M0305_SIGNAL_APPLICABLE_UNIT_KINDS,
    M0305_SIGNAL_COUNT,
    DetectProteinInferenceArtifactsRequest,
    ProteinInferenceArtifactDisposition,
    ProteinInferenceArtifactEvidenceLedger,
    ProteinInferenceArtifactEvidenceUnit,
    ProteinInferenceArtifactFindingCode,
    ProteinInferenceArtifactFlagState,
    ProteinInferenceArtifactObservationState,
    ProteinInferenceArtifactPolicy,
    ProteinInferenceArtifactPosteriorState,
    ProteinInferenceArtifactProfile,
    ProteinInferenceArtifactSignal,
    ProteinInferenceArtifactSignalCode,
    ProteinInferenceArtifactThreshold,
    ProteinInferenceEvidenceUnitKind,
    artifact_evidence_ledger_digest,
    artifact_quality_receipt,
    canonical_request_digest,
    configuration_digest,
    contract_json_schema,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m03_04 import ProteinInferenceQualityResult
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import ArtifactReference, SupportStatus
from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics import (
    compute_protein_inference_quality,
)
from glio_proteogen.modules.c03_protein_inference.m03_05_artifact_detection import (
    M0305Plugin,
    M0305ProteinInferenceArtifactEngine,
    M0305Service,
    ProteinInferenceArtifactAuthorizationError,
    detect_protein_inference_artifacts,
    preflight_protein_inference_artifact_authorization,
    service,
)

_PEPTIDE_UNIT_ID = f"unit.{sha256_digest({'unit': 'peptide'}).removeprefix('sha256:')}"


def _artifact(name: str, marker: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"evidence.m0305.{name}",
        version="1.0.0",
        digest="sha256:" + (marker * 64),
        media_type="application/json",
    )


def _quality_result() -> ProteinInferenceQualityResult:
    return compute_protein_inference_quality(build_scenario().request)


def _request() -> DetectProteinInferenceArtifactsRequest:
    quality_result = _quality_result()
    receipt = artifact_quality_receipt(quality_result)
    assert receipt.applicability is not None
    thresholds = tuple(
        ProteinInferenceArtifactThreshold(
            signal_code=code,
            review_threshold_ppm=200_000,
            exclude_threshold_ppm=500_000,
            required=True,
            applicable_unit_kinds=tuple(sorted(M0305_SIGNAL_APPLICABLE_UNIT_KINDS[code])),
            evidence=_artifact(f"threshold.{index}", f"{index + 1:x}"),
        )
        for index, code in enumerate(ProteinInferenceArtifactSignalCode)
    )
    profile = ProteinInferenceArtifactProfile(
        profile_id="profile.m0305.synthetic",
        version="1.0.0",
        applicability=receipt.applicability,
        approved_assay_protocol_versions=(receipt.assay_protocol_version,),
        approved_controlled_vocabulary_versions=(receipt.controlled_vocabulary_version,),
        approved_unit_system_versions=(receipt.unit_system_version,),
        thresholds=thresholds,
        evidence=_artifact("profile", "b"),
    )
    policy = ProteinInferenceArtifactPolicy(
        policy_id="policy.m0305.synthetic",
        version="1.0.0",
        max_units=32,
        max_sources=64,
        max_claims=48,
        profiles=(profile,),
        evidence=_artifact("policy", "c"),
        reviewed_by="reviewer.m0305",
        reviewed_at=quality_result.completed_at,
    )
    peptide_source = next(
        item for item in receipt.sources if item.role is ProteinInferenceRawRole.PEPTIDE_EVIDENCE
    )
    peptide_claim_id = peptide_source.bound_claim_id
    assert peptide_claim_id is not None
    signals = tuple(
        ProteinInferenceArtifactSignal(
            signal_code=code,
            observation_state=(
                ProteinInferenceArtifactObservationState.OBSERVED
                if ProteinInferenceEvidenceUnitKind.PEPTIDE_EVIDENCE
                in M0305_SIGNAL_APPLICABLE_UNIT_KINDS[code]
                else ProteinInferenceArtifactObservationState.NOT_APPLICABLE
            ),
            supporting_count=0,
            evaluated_count=(
                10
                if ProteinInferenceEvidenceUnitKind.PEPTIDE_EVIDENCE
                in M0305_SIGNAL_APPLICABLE_UNIT_KINDS[code]
                else 0
            ),
        )
        for code in ProteinInferenceArtifactSignalCode
    )
    unit = ProteinInferenceArtifactEvidenceUnit(
        unit_id=_PEPTIDE_UNIT_ID,
        unit_kind=ProteinInferenceEvidenceUnitKind.PEPTIDE_EVIDENCE,
        source_ids=(peptide_source.source_id,),
        claim_ids=(peptide_claim_id,),
        signals=signals,
    )
    recorded_at = quality_result.completed_at + timedelta(seconds=1)
    ledger_payload = {
        "ledger_id": "ledger.m0305.synthetic",
        "version": "1.0.0",
        "quality_result_digest": receipt.quality_result_digest,
        "admission_result_digest": receipt.admission_result_digest,
        "source_manifest_digest": receipt.source_manifest_digest,
        "source_binding_digest": receipt.source_binding_digest,
        "claim_binding_digest": receipt.claim_binding_digest,
        "quality_metric_binding_digest": receipt.quality_metric_binding_digest,
        "applicability": receipt.applicability,
        "units": (unit,),
        "evidence": _artifact("ledger", "d"),
        "recorded_at": recorded_at,
    }
    ledger_payload["ledger_digest"] = artifact_evidence_ledger_digest(ledger_payload)
    ledger = ProteinInferenceArtifactEvidenceLedger.model_validate(
        ledger_payload,
        strict=True,
    )
    old_context = quality_result.request.context
    references = old_context.references
    approved = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(policy)}
            )
        }
    )
    quality = references.quality.model_copy(
        update={
            "evidence": references.quality.evidence.model_copy(
                update={"digest": quality_result.result_digest}
            )
        }
    )
    context = old_context.model_copy(
        update={
            "occurred_at": recorded_at + timedelta(seconds=1),
            "references": references.model_copy(
                update={"approved_configuration": approved, "quality": quality}
            ),
        }
    )
    return DetectProteinInferenceArtifactsRequest(
        context=context,
        quality_receipt=receipt,
        evidence_ledger=ledger,
        policy=policy,
    )


def _ledger(
    request: DetectProteinInferenceArtifactsRequest,
    *,
    units: tuple[ProteinInferenceArtifactEvidenceUnit, ...] | None = None,
    **updates: object,
) -> ProteinInferenceArtifactEvidenceLedger:
    current = request.evidence_ledger
    assert current is not None
    payload = current.model_dump(mode="python")
    if units is not None:
        payload["units"] = units
    payload.update(updates)
    payload["ledger_digest"] = artifact_evidence_ledger_digest(payload)
    return ProteinInferenceArtifactEvidenceLedger.model_validate(payload, strict=True)


def _replace_signal(
    request: DetectProteinInferenceArtifactsRequest,
    code: ProteinInferenceArtifactSignalCode,
    **updates: object,
) -> DetectProteinInferenceArtifactsRequest:
    ledger = request.evidence_ledger
    assert ledger is not None
    unit = ledger.units[0]
    signals = tuple(
        item.model_copy(update=updates) if item.signal_code is code else item
        for item in unit.signals
    )
    rebuilt = ProteinInferenceArtifactEvidenceUnit.model_validate(
        unit.model_copy(update={"signals": signals}),
        strict=True,
    )
    return request.model_copy(update={"evidence_ledger": _ledger(request, units=(rebuilt,))})


def _policy_request(
    request: DetectProteinInferenceArtifactsRequest,
    policy: ProteinInferenceArtifactPolicy,
    *,
    evidence_ledger: ProteinInferenceArtifactEvidenceLedger | None,
) -> DetectProteinInferenceArtifactsRequest:
    refs = request.context.references
    approved = refs.approved_configuration.model_copy(
        update={
            "evidence": refs.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(policy)}
            )
        }
    )
    context = request.context.model_copy(
        update={"references": refs.model_copy(update={"approved_configuration": approved})}
    )
    return DetectProteinInferenceArtifactsRequest(
        context=context,
        quality_receipt=request.quality_receipt,
        evidence_ledger=evidence_ledger,
        policy=policy,
    )


build_m0305_request = _request
request_with_signal = _replace_signal


def test_canonical_artifact_detection_is_private_exact_and_deterministic() -> None:
    request = _request()
    first = detect_protein_inference_artifacts(request)
    second = M0305ProteinInferenceArtifactEngine().detect(request)

    assert first == second
    assert first.disposition is ProteinInferenceArtifactDisposition.CLEARED
    assert len(first.signal_scores) == M0305_SIGNAL_COUNT
    assert len(first.artifact_posteriors) == 1
    assert first.artifact_posteriors[0].state is ProteinInferenceArtifactPosteriorState.CLEAR
    assert first.exclusion_mask.retain_unit_ids == (_PEPTIDE_UNIT_ID,)
    assert first.contamination_flags == ()
    assert first.support.status is SupportStatus.SUPPORTED
    assert all(not item.score_is_calibrated_probability for item in first.signal_scores)
    assert {item.code for item in first.limitations} >= {M0305_SCORE_LIMITATION_CODE}
    rendered = first.model_dump_json()
    assert "MPEPTIDEK" not in rendered
    assert "scan=1" not in rendered
    assert first.infers_protein is False
    assert first.infers_kinase_activity is False


def test_suspected_contamination_quarantines_and_reviews_without_exclusion() -> None:
    request = _replace_signal(
        _request(),
        ProteinInferenceArtifactSignalCode.CONTAMINANT_REFERENCE_SUPPORT,
        supporting_count=3,
    )
    result = detect_protein_inference_artifacts(request)

    assert result.disposition is ProteinInferenceArtifactDisposition.QUARANTINED
    assert result.contamination_flags[0].state is ProteinInferenceArtifactFlagState.SUSPECTED
    assert result.exclusion_mask.review_unit_ids == (_PEPTIDE_UNIT_ID,)
    assert result.exclusion_mask.exclude_unit_ids == ()


def test_detected_artifact_beats_required_indeterminate_and_excludes() -> None:
    request = _replace_signal(
        _request(),
        ProteinInferenceArtifactSignalCode.CONTAMINANT_REFERENCE_SUPPORT,
        supporting_count=6,
    )
    request = _replace_signal(
        request,
        ProteinInferenceArtifactSignalCode.DECOY_COMPETITION_FAILURE,
        observation_state=ProteinInferenceArtifactObservationState.MISSING,
        supporting_count=0,
        evaluated_count=0,
    )
    result = detect_protein_inference_artifacts(request)

    assert result.disposition is ProteinInferenceArtifactDisposition.QUARANTINED
    assert result.exclusion_mask.exclude_unit_ids == (_PEPTIDE_UNIT_ID,)
    assert {item.code for item in result.findings} >= {
        ProteinInferenceArtifactFindingCode.ARTIFACT_DETECTED,
        ProteinInferenceArtifactFindingCode.CONTAMINATION_FLAGGED,
    }


def test_indeterminate_contamination_abstains_without_contamination_flag() -> None:
    request = _replace_signal(
        _request(),
        ProteinInferenceArtifactSignalCode.TECHNICAL_CARRYOVER,
        observation_state=ProteinInferenceArtifactObservationState.MISSING,
        supporting_count=0,
        evaluated_count=0,
    )
    result = detect_protein_inference_artifacts(request)

    assert result.disposition is ProteinInferenceArtifactDisposition.ABSTAINED
    assert result.contamination_flags == ()
    assert result.exclusion_mask.review_unit_ids == (_PEPTIDE_UNIT_ID,)


def test_out_of_domain_signal_cannot_be_observed() -> None:
    request = _request()
    ledger = request.evidence_ledger
    assert ledger is not None
    unit = ledger.units[0]
    signals = tuple(
        item.model_copy(
            update={
                "observation_state": ProteinInferenceArtifactObservationState.OBSERVED,
                "evaluated_count": 1,
            }
        )
        if item.signal_code is ProteinInferenceArtifactSignalCode.SAMPLE_CONTEXT_DISCORDANCE
        else item
        for item in unit.signals
    )
    with pytest.raises(ValidationError, match="out-of-domain"):
        ProteinInferenceArtifactEvidenceUnit.model_validate(
            unit.model_copy(update={"signals": signals}),
            strict=True,
        )


def test_binding_mismatch_is_typed_quarantine_with_no_scores() -> None:
    request = _request()
    mismatch = _ledger(request, source_binding_digest="sha256:" + ("e" * 64))
    result = detect_protein_inference_artifacts(
        request.model_copy(update={"evidence_ledger": mismatch})
    )

    assert result.signal_scores == ()
    assert result.disposition is ProteinInferenceArtifactDisposition.QUARANTINED
    assert {item.code for item in result.findings} == {
        ProteinInferenceArtifactFindingCode.EVIDENCE_LEDGER_BINDING_MISMATCH
    }


def test_policy_shape_cap_abstains_before_evidence_traversal() -> None:
    request = _request()
    policy = request.policy.model_copy(update={"max_sources": 12})
    shaped = _policy_request(request, policy, evidence_ledger=None)
    result = detect_protein_inference_artifacts(shaped)

    assert result.signal_scores == ()
    assert result.disposition is ProteinInferenceArtifactDisposition.ABSTAINED
    assert {item.code for item in result.findings} == {
        ProteinInferenceArtifactFindingCode.UPSTREAM_SHAPE_UNSUPPORTED
    }


def test_dict_subclass_shape_cap_drops_hostile_ledger_before_validation() -> None:
    request = _request()
    policy = request.policy.model_copy(
        update={"max_sources": request.quality_receipt.source_count - 1}
    )
    refs = request.context.references
    approved = refs.approved_configuration.model_copy(
        update={
            "evidence": refs.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(policy)}
            )
        }
    )
    context = request.context.model_copy(
        update={"references": refs.model_copy(update={"approved_configuration": approved})}
    )

    class HostileDict(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise AssertionError

        def copy(self) -> dict[str, object]:
            raise AssertionError

        def __iter__(self) -> Iterator[str]:
            raise AssertionError

        def __getitem__(self, key: str) -> object:
            raise AssertionError(key)

    payload = request.model_dump(mode="python")
    payload["context"] = context.model_dump(mode="python")
    payload["policy"] = policy.model_dump(mode="python")
    payload["evidence_ledger"] = HostileDict()
    candidate = HostileDict(payload)

    result = detect_protein_inference_artifacts(candidate)

    assert result.disposition is ProteinInferenceArtifactDisposition.ABSTAINED
    assert result.signal_scores == ()
    assert result.findings[0].code is ProteinInferenceArtifactFindingCode.UPSTREAM_SHAPE_UNSUPPORTED


class _HostileLedger(Mapping[str, object]):
    def __init__(self) -> None:
        self.traversals = 0

    def __getitem__(self, key: str) -> object:
        self.traversals += 1
        raise AssertionError(key)

    def __iter__(self) -> Iterator[str]:
        self.traversals += 1
        raise AssertionError

    def __len__(self) -> int:
        self.traversals += 1
        raise AssertionError


def test_preflight_denial_does_not_traverse_evidence_ledger() -> None:
    request = _request().model_dump(mode="python")
    request["context"]["references"]["consent"]["state"] = "withheld"
    hostile = _HostileLedger()
    request["evidence_ledger"] = hostile

    with pytest.raises(ProteinInferenceArtifactAuthorizationError):
        preflight_protein_inference_artifact_authorization(request)
    assert hostile.traversals == 0


class _InterruptingContext:
    @property
    def context(self) -> object:
        raise KeyboardInterrupt


def test_preflight_suppresses_exception_but_not_base_exception() -> None:
    with pytest.raises(KeyboardInterrupt):
        preflight_protein_inference_artifact_authorization(_InterruptingContext())


def test_plugin_strict_bytes_token_and_descriptor_boundary() -> None:
    request = _request()
    service = M0305Service()
    plugin = M0305Plugin(service)
    token = plugin.validate(canonical_json_bytes(request))

    assert plugin.run(token) == service.execute(request)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M03-05"
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(request)  # type: ignore[arg-type]


def test_service_verify_enforces_result_limit_for_all_ingress_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = detect_protein_inference_artifacts(_request())
    result_size = len(canonical_json_bytes(result))
    monkeypatch.setattr(service, "M0305_MAX_CANONICAL_RESULT_BYTES", result_size - 1)
    service_instance = M0305Service()

    with pytest.raises(ValueError, match="result exceeds its canonical byte limit"):
        service_instance.verify(result)
    with pytest.raises(ValueError, match="result exceeds its canonical byte limit"):
        service_instance.verify(result.model_dump(mode="python"))


def test_profile_mismatch_is_typed_abstention() -> None:
    request = _request()
    profile = request.policy.profiles[0].model_copy(
        update={"approved_assay_protocol_versions": ("99.0.0",)}
    )
    policy = request.policy.model_copy(update={"profiles": (profile,)})
    unsupported = _policy_request(request, policy, evidence_ledger=request.evidence_ledger)
    result = detect_protein_inference_artifacts(unsupported)

    assert result.signal_scores == ()
    assert result.disposition is ProteinInferenceArtifactDisposition.ABSTAINED
    assert {item.code for item in result.findings} == {
        ProteinInferenceArtifactFindingCode.DETECTOR_PROFILE_UNSUPPORTED
    }


def test_contract_schema_and_request_digest_are_stable() -> None:
    request = _request()
    schema = contract_json_schema("request")
    metadata = cast("dict[str, object]", schema["x-glio-contract"])

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert metadata["calibratedProbability"] is False
    assert canonical_request_digest(request) == canonical_request_digest(
        request.model_dump(mode="python")
    )
