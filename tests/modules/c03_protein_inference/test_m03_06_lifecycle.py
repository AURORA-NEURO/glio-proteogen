"""Focused M03-06 fixed-point harmonization runtime lifecycle tests."""

from __future__ import annotations

from collections.abc import Iterator, Mapping

import pytest
from evals.m03_06.run import build_scenario_request
from pydantic import ValidationError

from glio_proteogen.contracts.m03_05 import (
    ProteinInferenceArtifactDisposition,
    ProteinInferenceArtifactPosteriorState,
)
from glio_proteogen.contracts.m03_06 import (
    M0306_RATE_SCALE,
    HarmonizeProteinInferenceSupportRequest,
    ProteinInferenceArtifactAction,
    ProteinInferenceArtifactHarmonizationReceipt,
    ProteinInferenceHarmonizationDiagnosticStatus,
    ProteinInferenceHarmonizationDisposition,
    ProteinInferenceHarmonizationFindingCode,
    ProteinInferenceHarmonizationPolicy,
    ProteinInferenceHarmonizationProfile,
    ProteinInferenceHarmonizationResult,
    ProteinInferenceNormalizationFactor,
    ProteinInferenceSupportInvariantKind,
    ProteinInferenceSupportLedger,
    artifact_receipt_digest,
    configuration_digest,
    opaque_harmonization_identifier,
    result_payload_digest,
    support_ledger_digest,
    unit_binding_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c03_protein_inference.m03_06_harmonization import (
    M0306Plugin,
    M0306Service,
    ProteinInferenceHarmonizationAuthorizationError,
    ValidatedM0306Request,
    execute_protein_inference_harmonization,
    harmonize_protein_inference_support,
    preflight_protein_inference_harmonization_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_06_harmonization.engine import (
    prepare_harmonization_request_candidate,
)

_OPPOSITE_SIGNED_POST_RESIDUAL_PPM = 1_100_000


@pytest.fixture(scope="module")
def canonical_request() -> HarmonizeProteinInferenceSupportRequest:
    return build_scenario_request()


def _quarantined_receipt(
    request: HarmonizeProteinInferenceSupportRequest,
    unit_id: str,
) -> ProteinInferenceArtifactHarmonizationReceipt:
    units = tuple(
        item.model_copy(
            update={
                "posterior_state": ProteinInferenceArtifactPosteriorState.SUSPECTED,
                "action": ProteinInferenceArtifactAction.REVIEW,
            }
        )
        if item.unit_id == unit_id
        else item
        for item in request.artifact_receipt.units
    )
    payload = request.artifact_receipt.model_dump(mode="python", exclude={"receipt_digest"})
    payload.update(
        {
            "artifact_disposition": ProteinInferenceArtifactDisposition.QUARANTINED,
            "artifact_support_status": SupportStatus.REVIEW_REQUIRED,
            "artifact_human_review_required": True,
            "units": units,
            "unit_binding_digest": unit_binding_digest(units),
        }
    )
    payload["receipt_digest"] = artifact_receipt_digest(payload)
    return ProteinInferenceArtifactHarmonizationReceipt.model_validate(payload, strict=True)


def test_kernel_and_engine_close_all_exact_diagnostics(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    execution = execute_protein_inference_harmonization(canonical_request)
    result = harmonize_protein_inference_support(canonical_request)

    assert execution.analysis is not None
    assert execution.transformation_manifest is not None
    assert execution.analysis == result.analysis
    assert execution.transformation_manifest == result.transformation_manifest
    assert result.disposition is ProteinInferenceHarmonizationDisposition.ACCEPTED
    assert [item.before_residual_ppm for item in result.technical_effect_diagnostics] == [
        index * 1_000 for index in range(1, 9)
    ]
    assert {item.after_residual_ppm for item in result.technical_effect_diagnostics} == {0}
    assert {
        (item.before_score_ppm, item.after_score_ppm, item.status)
        for item in result.invariant_diagnostics
    } == {(200_000, 200_000, ProteinInferenceHarmonizationDiagnosticStatus.PASSED)}


def test_service_plugin_token_and_descriptor_lifecycle(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    service = M0306Service()
    plugin = M0306Plugin(service)
    token = plugin.validate(canonical_json_bytes(canonical_request))
    typed_token = plugin.validate(canonical_request)

    assert isinstance(token, ValidatedM0306Request)
    assert typed_token.request == token.request
    assert plugin.run(token) == service.execute(canonical_request)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M03-06"
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(canonical_request)  # type: ignore[arg-type]


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


class _AccessorHostileDict(dict[str, object]):
    """Carry safe built-in dict storage while every override is hostile."""

    def get(self, key: str, default: object = None) -> object:
        del key, default
        raise AssertionError

    def copy(self) -> dict[str, object]:
        raise AssertionError


def test_preflight_denial_never_traverses_support_ledger(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    candidate = canonical_request.model_dump(mode="python")
    candidate["context"]["references"]["consent"]["state"] = "withheld"
    hostile = _HostileLedger()
    candidate["support_ledger"] = hostile

    with pytest.raises(ProteinInferenceHarmonizationAuthorizationError):
        preflight_protein_inference_harmonization_authorization(candidate)
    assert hostile.traversals == 0


def test_complete_upstream_quarantine_terminates_before_hostile_ledger(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    unit_id = canonical_request.artifact_receipt.units[0].unit_id
    receipt = _quarantined_receipt(canonical_request, unit_id)
    candidate = canonical_request.model_dump(mode="python")
    candidate["artifact_receipt"] = receipt.model_dump(mode="python")
    hostile = _HostileLedger()
    candidate["support_ledger"] = hostile

    result = harmonize_protein_inference_support(candidate)

    assert hostile.traversals == 0
    assert result.analysis is None
    assert result.transformation_manifest is None
    assert result.technical_effect_diagnostics == ()
    assert result.invariant_diagnostics == ()
    assert result.disposition is ProteinInferenceHarmonizationDisposition.QUARANTINED
    assert {item.code for item in result.findings} == {
        ProteinInferenceHarmonizationFindingCode.UPSTREAM_QUARANTINED
    }


def test_complete_upstream_quarantine_sanitizes_trivial_dict_subclass(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    unit_id = canonical_request.artifact_receipt.units[0].unit_id
    receipt = _quarantined_receipt(canonical_request, unit_id)
    payload = canonical_request.model_dump(mode="python")
    payload["artifact_receipt"] = receipt.model_dump(mode="python")
    hostile = _HostileLedger()
    payload["support_ledger"] = hostile
    candidate = _AccessorHostileDict(payload)

    result = harmonize_protein_inference_support(candidate)

    assert hostile.traversals == 0
    assert result.analysis is None
    assert result.disposition is ProteinInferenceHarmonizationDisposition.QUARANTINED
    assert {item.code for item in result.findings} == {
        ProteinInferenceHarmonizationFindingCode.UPSTREAM_QUARANTINED
    }


class _InterruptingCandidate:
    @property
    def context(self) -> object:
        raise KeyboardInterrupt


def test_preflight_collapses_exception_but_never_base_exception() -> None:
    with pytest.raises(KeyboardInterrupt):
        preflight_protein_inference_harmonization_authorization(_InterruptingCandidate())


class _ExplodingReceipt:
    @property
    def evaluation_state(self) -> object:
        raise RuntimeError


def test_candidate_preparation_is_shallow_and_fail_closed(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    assert prepare_harmonization_request_candidate(canonical_request) is canonical_request
    ordinary = canonical_request.model_dump(mode="python")
    assert prepare_harmonization_request_candidate(ordinary) is ordinary
    malformed = {"artifact_receipt": _ExplodingReceipt(), "policy": {}}
    assert prepare_harmonization_request_candidate(malformed) is malformed

    hostile = _HostileLedger()
    unsupported = {
        "artifact_receipt": {"evaluation_state": "not_evaluable", "unit_count": 0},
        "policy": {"max_units": 512},
        "support_ledger": hostile,
    }
    prepared = prepare_harmonization_request_candidate(unsupported)
    assert isinstance(prepared, dict)
    assert prepared is not unsupported
    assert prepared["support_ledger"] is None
    assert hostile.traversals == 0

    oversized = {
        "artifact_receipt": {"evaluation_state": "complete", "unit_count": 2},
        "policy": {"max_units": 1},
        "support_ledger": hostile,
    }
    prepared_oversized = prepare_harmonization_request_candidate(oversized)
    assert isinstance(prepared_oversized, dict)
    assert prepared_oversized["support_ledger"] is None


def test_plugin_strictly_rejects_unknown_json_members(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    payload = canonical_request.model_dump(mode="json")
    payload["undeclared"] = True

    with pytest.raises(ValidationError):
        M0306Plugin(M0306Service()).validate(canonical_json_bytes(payload))


@pytest.mark.parametrize(
    ("field", "canary"),
    [
        ("artifact_id", "artifact.MPEPTIDEK"),
        ("media_type", "MPEPTIDEK"),
    ],
)
def test_owned_evidence_reference_rejects_biological_canaries(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
    field: str,
    canary: str,
) -> None:
    evidence = canonical_request.policy.evidence.model_copy(update={field: canary})
    payload = canonical_request.policy.model_dump(mode="python")
    payload["evidence"] = evidence

    with pytest.raises(ValidationError, match="evidence"):
        ProteinInferenceHarmonizationPolicy.model_validate(payload, strict=True)


def test_owned_reviewer_identifier_rejects_biological_canary(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    payload = canonical_request.policy.model_dump(mode="python")
    payload["reviewed_by"] = "reviewer.MPEPTIDEK"

    with pytest.raises(ValidationError, match="reviewer"):
        ProteinInferenceHarmonizationPolicy.model_validate(payload, strict=True)


def test_binding_mismatch_is_typed_quarantine_without_analysis(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    ledger = canonical_request.support_ledger
    assert ledger is not None
    payload = ledger.model_dump(mode="python", exclude={"ledger_digest"})
    payload["artifact_receipt_digest"] = "sha256:" + ("f" * 64)
    payload["ledger_digest"] = support_ledger_digest(payload)
    mismatched = ProteinInferenceSupportLedger.model_validate(payload, strict=True)
    request = canonical_request.model_copy(update={"support_ledger": mismatched})

    result = harmonize_protein_inference_support(request)

    assert result.analysis is None
    assert result.transformation_manifest is None
    assert result.disposition is ProteinInferenceHarmonizationDisposition.QUARANTINED
    assert {item.code for item in result.findings} == {
        ProteinInferenceHarmonizationFindingCode.SUPPORT_LEDGER_BINDING_MISMATCH
    }


def test_unsupported_profile_is_typed_abstention(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    original = canonical_request.policy.profiles[0]
    profile = ProteinInferenceHarmonizationProfile.model_validate(
        {
            **original.model_dump(mode="python"),
            "approved_assay_protocol_versions": ("99.0.0",),
        },
        strict=True,
    )
    policy = ProteinInferenceHarmonizationPolicy.model_validate(
        {
            **canonical_request.policy.model_dump(mode="python"),
            "profiles": (profile,),
        },
        strict=True,
    )
    references = canonical_request.context.references
    approved = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(policy)}
            )
        }
    )
    context = canonical_request.context.model_copy(
        update={"references": references.model_copy(update={"approved_configuration": approved})}
    )
    request = HarmonizeProteinInferenceSupportRequest.model_validate(
        {
            **canonical_request.model_dump(mode="python"),
            "context": context,
            "policy": policy,
        },
        strict=True,
    )

    result = harmonize_protein_inference_support(request)

    assert result.analysis is None
    assert result.disposition is ProteinInferenceHarmonizationDisposition.ABSTAINED
    assert {item.code for item in result.findings} == {
        ProteinInferenceHarmonizationFindingCode.HARMONIZATION_PROFILE_UNSUPPORTED
    }


def test_complete_review_receipt_terminates_without_normalization(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    ledger = canonical_request.support_ledger
    assert ledger is not None
    estimation_anchor = opaque_harmonization_identifier(
        "anchor",
        {"purpose": "estimation", "factor": "platform"},
    )
    held_observation = next(
        item for item in ledger.observations if item.anchor_id == estimation_anchor
    )
    held_unit_id = held_observation.unit_id
    receipt = _quarantined_receipt(canonical_request, held_unit_id)
    request = canonical_request.model_copy(
        update={"artifact_receipt": receipt, "support_ledger": None}
    )

    result = harmonize_protein_inference_support(request)

    assert result.analysis is None
    assert result.transformation_manifest is None
    assert result.technical_effect_diagnostics == ()
    assert result.invariant_diagnostics == ()
    assert result.disposition is ProteinInferenceHarmonizationDisposition.QUARANTINED
    assert {item.code for item in result.findings} == {
        ProteinInferenceHarmonizationFindingCode.UPSTREAM_QUARANTINED
    }


def test_opposite_signed_validation_effect_uses_exact_two_scale_residual_domain(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    ledger = canonical_request.support_ledger
    assert ledger is not None
    estimation_anchor = opaque_harmonization_identifier(
        "anchor",
        {"purpose": "estimation", "factor": "platform"},
    )
    validation_anchor = opaque_harmonization_identifier(
        "anchor",
        {"purpose": "validation", "factor": "platform"},
    )
    comparison_level = opaque_harmonization_identifier(
        "level",
        {"factor": "platform", "side": "comparison"},
    )
    observations = []
    for item in ledger.observations:
        if item.anchor_id not in {estimation_anchor, validation_anchor}:
            observations.append(item)
            continue
        platform_level = next(
            level.level_id
            for level in item.factor_levels
            if level.factor is ProteinInferenceNormalizationFactor.PLATFORM
        )
        comparison = platform_level == comparison_level
        if item.anchor_id == estimation_anchor:
            coordinate = M0306_RATE_SCALE if comparison else 0
        else:
            coordinate = 0 if comparison else M0306_RATE_SCALE
        observations.append(item.model_copy(update={"support_coordinate_ppm": coordinate}))
    ledger_payload = ledger.model_dump(mode="python", exclude={"ledger_digest"})
    ledger_payload["observations"] = tuple(observations)
    ledger_payload["ledger_digest"] = support_ledger_digest(ledger_payload)
    revised_ledger = ProteinInferenceSupportLedger.model_validate(ledger_payload, strict=True)
    request = canonical_request.model_copy(update={"support_ledger": revised_ledger})

    result = harmonize_protein_inference_support(request)

    platform = next(
        item
        for item in result.technical_effect_diagnostics
        if item.factor is ProteinInferenceNormalizationFactor.PLATFORM
    )
    assert platform.before_residual_ppm == M0306_RATE_SCALE
    assert platform.after_residual_ppm == _OPPOSITE_SIGNED_POST_RESIDUAL_PPM
    assert platform.status is ProteinInferenceHarmonizationDiagnosticStatus.FAILED
    assert result.disposition is ProteinInferenceHarmonizationDisposition.QUARANTINED


def test_nonzero_adjustment_reaching_boundary_is_explicitly_clipped(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    ledger = canonical_request.support_ledger
    assert ledger is not None
    direction = next(
        item
        for item in ledger.invariants
        if item.kind is ProteinInferenceSupportInvariantKind.SUPPORT_DIRECTION
    )
    unit_id = direction.right_unit_ids[0]
    comparison_level = opaque_harmonization_identifier(
        "level",
        {"factor": "platform", "side": "comparison"},
    )
    observations = tuple(
        item.model_copy(
            update={
                "support_coordinate_ppm": 1_000,
                "factor_levels": tuple(
                    level.model_copy(update={"level_id": comparison_level})
                    if level.factor is ProteinInferenceNormalizationFactor.PLATFORM
                    else level
                    for level in item.factor_levels
                ),
            }
        )
        if item.unit_id == unit_id
        else item
        for item in ledger.observations
    )
    ledger_payload = ledger.model_dump(mode="python", exclude={"ledger_digest"})
    ledger_payload["observations"] = observations
    ledger_payload["ledger_digest"] = support_ledger_digest(ledger_payload)
    revised_ledger = ProteinInferenceSupportLedger.model_validate(ledger_payload, strict=True)

    result = harmonize_protein_inference_support(
        canonical_request.model_copy(update={"support_ledger": revised_ledger})
    )

    assert result.analysis is not None
    value = next(item for item in result.analysis.values if item.unit_id == unit_id)
    assert value.harmonized_support_coordinate_ppm == 0
    assert value.was_clipped
    assert result.disposition is ProteinInferenceHarmonizationDisposition.QUARANTINED
    assert ProteinInferenceHarmonizationFindingCode.VALUE_CLIPPED in {
        item.code for item in result.findings
    }


def test_genuine_zero_with_only_zero_shifts_is_not_clipped(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    ledger = canonical_request.support_ledger
    assert ledger is not None
    direction = next(
        item
        for item in ledger.invariants
        if item.kind is ProteinInferenceSupportInvariantKind.SUPPORT_DIRECTION
    )
    unit_id = direction.left_unit_ids[0]
    observations = tuple(
        item.model_copy(update={"support_coordinate_ppm": 0}) if item.unit_id == unit_id else item
        for item in ledger.observations
    )
    ledger_payload = ledger.model_dump(mode="python", exclude={"ledger_digest"})
    ledger_payload["observations"] = observations
    ledger_payload["ledger_digest"] = support_ledger_digest(ledger_payload)
    revised_ledger = ProteinInferenceSupportLedger.model_validate(ledger_payload, strict=True)

    result = harmonize_protein_inference_support(
        canonical_request.model_copy(update={"support_ledger": revised_ledger})
    )

    assert result.analysis is not None
    value = next(item for item in result.analysis.values if item.unit_id == unit_id)
    assert value.input_support_coordinate_ppm == 0
    assert value.harmonized_support_coordinate_ppm == 0
    assert not value.was_clipped
    assert ProteinInferenceHarmonizationFindingCode.VALUE_CLIPPED not in {
        item.code for item in result.findings
    }


def test_resigned_envelope_forgery_fails_full_replay(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    result = harmonize_protein_inference_support(canonical_request)
    payload = result.model_dump(mode="python")
    payload["human_review_required"] = True
    payload["result_digest"] = result_payload_digest(payload)

    with pytest.raises(ValidationError, match="human-review flag"):
        ProteinInferenceHarmonizationResult.model_validate(payload, strict=True)
