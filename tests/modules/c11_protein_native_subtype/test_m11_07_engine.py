"""Runtime, replay, and hostile-input coverage for M11-07."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from glio_proteogen.contracts.m11_07 import (
    M1107_M1104_RESULT_MEDIA_TYPE,
    AdjudicateVariantPeptidePlausibilityRequest,
    ControlKind,
    ControlOutcome,
    PlausibilityAdjudicationStatus,
    PlausibilityControl,
    PlausibilityGrade,
    canonical_request_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c11_protein_native_subtype import (
    m11_07_plausibility_adjudicator as m1107,
)
from glio_proteogen.modules.c11_protein_native_subtype.m11_07_plausibility_adjudicator import (
    engine as m1107_engine,
)

M1107PlausibilityEngine = m1107.M1107PlausibilityEngine
M1107Plugin = m1107.M1107Plugin
M1107Service = m1107.M1107Service
PlausibilityAuthorizationError = m1107.PlausibilityAuthorizationError
adjudicate_variant_peptide_plausibility = m1107.adjudicate_variant_peptide_plausibility
preflight_plausibility_authorization = m1107.preflight_plausibility_authorization
verify_plausibility_replay = m1107.verify_plausibility_replay


def _digest(seed: int) -> str:
    return f"sha256:{seed:064x}"


def test_plain_materialization_rejects_recursive_and_oversized_values() -> None:
    nested: object = "leaf"
    for _ in range(70):
        nested = {"nested": nested}
    with pytest.raises(TypeError, match="string-keyed"):
        m1107_engine._plain_value(nested)
    with pytest.raises(TypeError, match="string-keyed"):
        m1107_engine._plain_value(["item"] * 4_097)


def _artifact(name: str, seed: int, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=_digest(seed),
        media_type=media_type,
    )


def _context(
    *, support: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED
) -> ExecutionContext:
    config = _artifact("configuration", 1)
    identity_evidence = _artifact("identity", 2)
    provenance = _artifact("provenance", 3)
    consent_evidence = _artifact("consent", 4)
    quality = _artifact("quality", 5)
    support_evidence = _artifact("support", 6)
    intended_use = _artifact("intended-use", 7)
    policy = "1.0.0"
    return ExecutionContext(
        request_id="context-request",
        actor_id="scientist",
        occurred_at=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="config-decision",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version=policy,
                evidence=config,
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="identity-decision",
                state=IdentityLineageState.RESOLVED,
                policy_version=policy,
                binding_digest=_digest(8),
                evidence=identity_evidence,
            ),
            provenance=UpstreamDecisionReference(
                decision_id="provenance-decision",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version=policy,
                evidence=provenance,
            ),
            consent=ConsentReference(
                decision_id="consent-decision",
                state=ConsentState.GRANTED,
                policy_version=policy,
                evidence=consent_evidence,
            ),
            quality=UpstreamDecisionReference(
                decision_id="quality-decision",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version=policy,
                evidence=quality,
            ),
            support=UpstreamDecisionReference(
                decision_id="support-decision",
                state=support,
                policy_version=policy,
                evidence=support_evidence,
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="intended-use-decision",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version=policy,
                evidence=intended_use,
            ),
        ),
    )


_CONTROL_COUNT = 6


def _controls(*, outcome: ControlOutcome = ControlOutcome.PASSED) -> tuple[Any, ...]:

    kinds = (
        ControlKind.ORTHOGONAL_EVIDENCE,
        ControlKind.KNOWN_CONTROL,
        ControlKind.DIRECTION,
        ControlKind.CONSERVATION,
        ControlKind.ASSAY_PHYSICS,
        ControlKind.COMPETING_MECHANISM,
    )
    return tuple(
        PlausibilityControl(
            control_id=f"control-{index}",
            kind=kind,
            criterion=f"criterion-{kind.value}",
            expected_direction="consistent" if kind is ControlKind.DIRECTION else None,
            required_evidence=(
                EvidenceReference(
                    reference=_artifact(f"control-evidence-{index}", 20 + index),
                    role="evidence",
                    claim="caller-declared control evidence",
                ),
            ),
            declared_outcome=outcome,
            observed_direction="consistent" if kind is ControlKind.DIRECTION else None,
            is_negative_control=kind is ControlKind.KNOWN_CONTROL,
        )
        for index, kind in enumerate(kinds)
    )


def _request(
    *,
    outcome: ControlOutcome = ControlOutcome.PASSED,
    conflict: bool = False,
    support: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED,
) -> AdjudicateVariantPeptidePlausibilityRequest:
    return AdjudicateVariantPeptidePlausibilityRequest(
        request_id="request-m1107",
        context=_context(support=support),
        mechanism_inference_result=_artifact("mechanism-result", 10, M1107_M1104_RESULT_MEDIA_TYPE),
        controls=_controls(outcome=outcome),
        candidate_mechanisms=("mechanism-a", "mechanism-b"),
        conflict_declared=conflict,
        source_artifacts=(_artifact("proteome-source", 11),),
    )


def test_supported_controls_produce_high_adjudication() -> None:
    result = adjudicate_variant_peptide_plausibility(_request())
    assert result.status is PlausibilityAdjudicationStatus.ADJUDICATED
    assert result.grade is PlausibilityGrade.HIGH
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert len(result.evaluations) == _CONTROL_COUNT
    assert all(item.outcome is ControlOutcome.PASSED for item in result.evaluations)
    assert result.human_review_required is False
    assert result.provenance.module_id == "GLIO-PROTEOGEN-M11-07"


@pytest.mark.parametrize(
    "outcome",
    [ControlOutcome.FAILED, ControlOutcome.NOT_EVALUABLE, ControlOutcome.ABSTAINED],
)
def test_blocking_control_abstains_without_negative_inference(outcome: ControlOutcome) -> None:
    result = M1107PlausibilityEngine().adjudicate(_request(outcome=outcome))
    assert result.status is PlausibilityAdjudicationStatus.ABSTAINED
    assert result.grade is None
    assert result.support_decision.status is SupportStatus.UNSUPPORTED
    assert result.abstention_reason
    assert result.human_review_required


def test_conflict_is_preserved_and_requires_review() -> None:
    result = adjudicate_variant_peptide_plausibility(_request(conflict=True))
    assert result.status is PlausibilityAdjudicationStatus.ABSTAINED
    assert result.grade is None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert len(result.conflicts) == 1
    assert result.conflicts[0].competing_mechanisms == ("mechanism-a", "mechanism-b")
    assert result.human_review_required


def test_unsupported_upstream_control_abstains_before_execution() -> None:
    request = _request(support=UpstreamDecisionState.REJECTED)
    with pytest.raises(PlausibilityAuthorizationError):
        preflight_plausibility_authorization(request)
    with pytest.raises(PlausibilityAuthorizationError):
        adjudicate_variant_peptide_plausibility(request)


def test_json_plugin_is_parse_once_and_runs_only_capability() -> None:
    service = M1107Service()
    plugin = M1107Plugin(service)
    payload = _request().model_dump_json()
    token = plugin.validate(payload)
    result = plugin.run(token)
    assert result.result_digest.startswith("sha256:")
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_service_replay_and_tamper_detection() -> None:
    request = _request()
    service = M1107Service()
    result = service.execute(request)
    assert service.verify(request, result).result_digest == result.result_digest
    assert verify_plausibility_replay(request, result)
    tampered = result.model_copy(update={"result_id": "tampered"})
    with pytest.raises(ValueError, match="result"):
        service.verify(request, tampered)


def test_request_digest_is_stable_and_result_digest_is_bound() -> None:
    first = adjudicate_variant_peptide_plausibility(_request())
    second = adjudicate_variant_peptide_plausibility(_request())
    assert canonical_request_digest(first.request) == canonical_request_digest(second.request)
    assert first.result_digest == second.result_digest
    with pytest.raises(ValueError, match="result"):
        M1107PlausibilityEngine().verify(
            _request(), first.model_copy(update={"request_digest": _digest(99)})
        )


def test_missing_negative_control_is_rejected() -> None:
    controls = tuple(
        PlausibilityControl(
            control_id=f"control-{index}",
            kind=kind,
            criterion="criterion",
            required_evidence=(
                EvidenceReference(
                    reference=_artifact(f"evidence-{index}", 50 + index),
                    role="evidence",
                    claim="claim",
                ),
            ),
        )
        for index, kind in enumerate(
            (
                ControlKind.ORTHOGONAL_EVIDENCE,
                ControlKind.KNOWN_CONTROL,
                ControlKind.DIRECTION,
                ControlKind.CONSERVATION,
                ControlKind.ASSAY_PHYSICS,
                ControlKind.COMPETING_MECHANISM,
            )
        )
    )
    with pytest.raises(ValueError, match="negative control"):
        AdjudicateVariantPeptidePlausibilityRequest(
            request_id="request-m1107",
            context=_context(),
            mechanism_inference_result=_artifact(
                "mechanism-result", 10, M1107_M1104_RESULT_MEDIA_TYPE
            ),
            controls=controls,
            candidate_mechanisms=("a", "b"),
            source_artifacts=(_artifact("source", 11),),
        )
