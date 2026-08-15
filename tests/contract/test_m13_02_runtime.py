"""Contract/runtime/interface tests for the M13-02 deep build."""

from __future__ import annotations

from datetime import UTC, datetime
from json import dumps

import pytest

from glio_proteogen.contracts.m13_02 import (
    ApplicableMechanism,
    ContextDimension,
    ContextObservation,
    ContextObservationStatus,
    MechanismApplicability,
    MechanismCandidate,
    StratifierConfiguration,
    StratifierPolicy,
    StratifyProteotypeContextRequest,
    canonical_request_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ControlRole,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c11_protein_native_subtype.m13_02_context_subtype_stratifier import (
    M1302AuthorizationError,
    M1302Plugin,
    M1302Service,
    compute_proteotype_context,
    preflight_context_authorization,
    verify_context_result,
)

_TIME = datetime(2026, 1, 1, tzinfo=UTC)
_CONTROL_COUNT = 7


def _artifact(name: str, letter: str = "a") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest="sha256:" + letter * 64,
        media_type="application/json",
    )


def _context(*, denied: bool = False) -> ExecutionContext:
    evidence = _artifact("control-evidence", "b")
    accepted = UpstreamDecisionState.REJECTED if denied else UpstreamDecisionState.ACCEPTED

    def upstream(name: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=name,
            state=accepted,
            policy_version="1.0.0",
            evidence=evidence,
        )

    identity_state = (
        IdentityLineageState.RESOLVED if not denied else IdentityLineageState.UNRESOLVED
    )
    return ExecutionContext(
        request_id="request-m1302",
        actor_id="actor-m1302",
        occurred_at=_TIME,
        references=ContextReferences(
            approved_configuration=upstream("configuration-decision"),
            identity_lineage=IdentityLineageReference(
                decision_id="identity-decision",
                state=identity_state,
                policy_version="1.0.0",
                binding_digest="sha256:" + "c" * 64,
                evidence=evidence,
            ),
            provenance=upstream("provenance-decision"),
            consent=ConsentReference(
                decision_id="consent-decision",
                state=ConsentState.GRANTED if not denied else ConsentState.WITHHELD,
                policy_version="1.0.0",
                evidence=evidence,
            ),
            quality=upstream("quality-decision"),
            support=upstream("support-decision"),
            intended_use=upstream("intended-use-decision"),
        ),
    )


def _request(
    *, statuses: tuple[ContextObservationStatus, ...] | None = None
) -> StratifyProteotypeContextRequest:
    source = _artifact("context-observations", "d")
    evidence = EvidenceReference(
        reference=source,
        role="evidence",
        claim="Caller-declared context observation",
    )
    values = (
        (ContextDimension.SUBTYPE, "IDH-mutant astrocytoma"),
        (ContextDimension.PLATFORM, "LC-MS"),
    )
    statuses = statuses or (ContextObservationStatus.SUPPORTED,) * len(values)
    observations = tuple(
        ContextObservation(
            observation_id=f"observation-{index}",
            dimension=dimension,
            value=value,
            normalized_value=(
                value.lower() if status is not ContextObservationStatus.UNRESOLVED else None
            ),
            status=status,
            source_artifact=source,
            evidence=(evidence,),
        )
        for index, ((dimension, value), status) in enumerate(zip(values, statuses, strict=True), 1)
    )
    configuration = StratifierConfiguration(
        configuration_id="config-m1302",
        version="1.0.0",
        method="caller-declared-context-rule",
        model_reference=_artifact("m1302-config", "e"),
        evidence=(evidence,),
    )
    candidate = MechanismCandidate(
        mechanism_id="mechanism.context.subtype",
        label="Subtype-context mechanism route",
        required_dimensions=(ContextDimension.SUBTYPE,),
        rationale="Requires supported subtype context only; no kinase state is inferred.",
        evidence=(evidence,),
    )
    return StratifyProteotypeContextRequest(
        request_id="request-m1302",
        context=_context(),
        variant_peptide_result=_artifact("variant-peptide-result", "f"),
        policy=StratifierPolicy(
            required_dimensions=(ContextDimension.SUBTYPE, ContextDimension.PLATFORM),
            configuration=configuration,
        ),
        observations=observations,
        mechanism_candidates=(candidate,),
        source_artifacts=(source,),
    )


def test_supported_context_emits_profile_mechanism_and_sealed_provenance() -> None:
    result = compute_proteotype_context(_request())
    assert result.status.value == "stratified"
    assert result.context_profile is not None
    assert result.applicable_mechanisms[0].applicability is MechanismApplicability.APPLICABLE
    assert result.parent_target == "proteotype"
    assert result.provenance.module_id == "GLIO-PROTEOGEN-M13-02"
    assert len(result.provenance.control_decisions) == _CONTROL_COUNT
    assert {item.role for item in result.provenance.control_decisions} == set(ControlRole)
    assert verify_context_result(result)


@pytest.mark.parametrize(
    "statuses",
    [
        (ContextObservationStatus.UNRESOLVED, ContextObservationStatus.SUPPORTED),
        (ContextObservationStatus.CONFLICTED, ContextObservationStatus.SUPPORTED),
    ],
)
def test_unresolved_or_conflicted_context_abstains_without_negative_mechanism(
    statuses: tuple[ContextObservationStatus, ...],
) -> None:
    result = compute_proteotype_context(_request(statuses=statuses))
    assert result.status.value == "abstained"
    assert result.context_profile is None
    assert result.applicable_mechanisms == ()
    assert result.support_decision.status.value in {"unsupported", "review_required"}
    assert result.abstention_reason is not None
    assert verify_context_result(result)


def test_missing_required_dimension_abstains() -> None:
    request = _request()
    missing = request.model_copy(update={"observations": request.observations[:1]})
    # Rebuild to exercise the exact source-reference and strict request path.
    result = compute_proteotype_context(missing)
    assert result.status.value == "abstained"
    assert "platform" in (result.abstention_reason or "")


def test_controls_are_checked_before_request_content() -> None:
    denied = _request().model_copy(update={"context": _context(denied=True)})
    with pytest.raises(M1302AuthorizationError):
        preflight_context_authorization(denied)
    with pytest.raises(M1302AuthorizationError):
        compute_proteotype_context(denied)


def test_plugin_strict_json_boundary_and_execution_token() -> None:
    request = _request()
    plugin = M1302Plugin(M1302Service())
    payload = dumps(request.model_dump(mode="json"), separators=(",", ":"))
    token = plugin.validate(payload)
    result = plugin.run(token)
    assert result.request_digest == canonical_request_digest(request)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]
    duplicate = payload[:-1] + ',"request_id":"tampered"}'
    with pytest.raises(StrictJsonError):  # strict JSON duplicate-key boundary
        plugin.validate(duplicate)


def test_result_tamper_fails_replay_verification() -> None:
    result = compute_proteotype_context(_request())
    tampered = result.model_copy(update={"findings": ()})
    assert not verify_context_result(tampered)


def test_supported_mechanism_requires_evidence_at_contract_boundary() -> None:
    with pytest.raises(ValueError, match="requires evidence"):
        ApplicableMechanism(
            mechanism_id="mechanism.no-evidence",
            label="No evidence",
            applicability=MechanismApplicability.APPLICABLE,
            rationale="Invalid supported route.",
        )
