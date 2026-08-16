"""Runtime, replay, authorization, and plugin coverage for provisional M11-02."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m11_02 import (
    M1102_HYPOTHESIS_MEDIA_TYPE,
    ContextDimension,
    ContextObservation,
    ContextProfile,
    ContextStratificationPolicy,
    ContextStratificationRule,
    ContextStratificationStatus,
    MechanismApplicability,
    MechanismApplicabilityStatus,
    StratifyVariantPeptideContextRequest,
    VariantPeptideContextStratificationResult,
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
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c11_protein_native_subtype.m11_02_context_subtype_stratifier import (
    M1102AuthorizationError,
    M1102ContextEngine,
    M1102Plugin,
    M1102ReplayVerificationError,
    M1102Service,
    ValidatedM1102Request,
    stratify_variant_peptide_context,
)

_DIGEST = "sha256:" + ("a" * 64)
_WHEN = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{name}",
        version="1.0.0",
        digest=_DIGEST,
        media_type=media_type,
    )


def _decision(
    role: str, state: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED
) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{role}",
        state=state,
        policy_version="1.0.0",
        evidence=_artifact(role),
    )


def _context(*, consent: ConsentState = ConsentState.GRANTED) -> ExecutionContext:
    return ExecutionContext(
        request_id="request.context.synthetic",
        actor_id="actor.m1102.synthetic",
        occurred_at=_WHEN,
        references=ContextReferences(
            approved_configuration=_decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_DIGEST,
                evidence=_artifact("identity"),
            ),
            provenance=_decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=consent,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=_decision("quality"),
            support=_decision("support"),
            intended_use=_decision("intended-use"),
        ),
    )


def _rule(
    name: str,
    dimension: ContextDimension,
    allowed: tuple[str, ...],
    *,
    proxies: tuple[str, ...] = (),
) -> ContextStratificationRule:
    return ContextStratificationRule(
        rule_id=f"rule.{name}",
        dimension=dimension,
        criterion=f"declared {dimension.value} is supported",
        allowed_values=allowed,
        prohibited_proxies=proxies,
        evidence=(_evidence(f"rule.{name}"),),
    )


def _evidence(name: str) -> Any:
    return EvidenceReference(reference=_artifact(name), role="evidence", claim="synthetic evidence")


def _observation(
    dimension: ContextDimension,
    value: str,
    *,
    score: float = 0.95,
) -> ContextObservation:
    return ContextObservation(
        dimension=dimension,
        value=value,
        source_artifact=_artifact(f"observation.{dimension.value}"),
        support_score=score,
        evidence=(_evidence(f"observation.{dimension.value}"),),
    )


def _request(
    *,
    disease: str = "glioma",
    disease_score: float = 0.95,
    include_subtype: bool = True,
    subtype: str = "astrocytoma",
    consent: ConsentState = ConsentState.GRANTED,
) -> StratifyVariantPeptideContextRequest:
    dimensions = [ContextDimension.DISEASE_CLASS]
    rules = [_rule("disease", ContextDimension.DISEASE_CLASS, ("glioma",), proxies=("postcode",))]
    observations = [_observation(ContextDimension.DISEASE_CLASS, disease, score=disease_score)]
    if include_subtype:
        dimensions.append(ContextDimension.SUBTYPE)
        rules.append(
            _rule("subtype", ContextDimension.SUBTYPE, ("astrocytoma", "oligodendroglioma"))
        )
        observations.append(_observation(ContextDimension.SUBTYPE, subtype))
    return StratifyVariantPeptideContextRequest(
        request_id="request.m1102.synthetic",
        context=_context(consent=consent),
        hypothesis_registry=ArtifactReference(
            artifact_id="artifact.hypotheses",
            version="0.1.0-provisional",
            digest=_DIGEST,
            media_type=M1102_HYPOTHESIS_MEDIA_TYPE,
        ),
        policy=ContextStratificationPolicy(
            policy_id="policy.m1102.synthetic",
            version="1.0.0",
            dimensions=tuple(dimensions),
            rules=tuple(rules),
            minimum_support_score=0.8,
            evidence=(_evidence("policy"),),
        ),
        observations=tuple(observations),
        source_artifacts=(_artifact("mass-spec"), _artifact("genome"), _artifact("transcriptome")),
    )


def test_supported_context_emits_profile_and_applicability() -> None:
    result = M1102ContextEngine().stratify(_request())

    assert result.status is ContextStratificationStatus.STRATIFIED
    assert result.profile is not None
    assert all(
        item.status is MechanismApplicabilityStatus.APPLICABLE
        for item in result.profile.applicable_mechanisms
    )
    assert result.support_decision.status.value == "supported"
    assert result.parent_target == "variant_peptide"
    assert result.emits_parent is False
    assert result.human_review_required is False


def test_public_operation_matches_engine() -> None:
    assert (
        stratify_variant_peptide_context(_request()).status
        is ContextStratificationStatus.STRATIFIED
    )


def test_supported_context_replays_and_has_request_derived_id() -> None:
    engine = M1102ContextEngine()
    request = _request()
    result = engine.stratify(request)

    assert result.request_digest == canonical_request_digest(request)
    assert result.result_id == f"result.{result.request_digest.removeprefix('sha256:')}"
    assert engine.verify(result).model_dump(mode="json") == result.model_dump(mode="json")


def test_low_support_abstains_without_profile_and_requires_review() -> None:
    result = M1102ContextEngine().stratify(_request(disease_score=0.2))

    assert result.status is ContextStratificationStatus.ABSTAINED
    assert result.profile is None
    assert result.support_decision.status.value == "review_required"
    assert result.human_review_required is True
    assert result.diagnostics[0].status is MechanismApplicabilityStatus.ABSTAINED


def test_missing_policy_dimension_abstains_without_negative_finding() -> None:
    result = M1102ContextEngine().stratify(_request(include_subtype=False))

    assert result.status is ContextStratificationStatus.STRATIFIED
    request = _request()
    missing = request.model_copy(
        update={
            "observations": (request.observations[0],),
        }
    )
    result = M1102ContextEngine().stratify(missing)
    assert result.status is ContextStratificationStatus.ABSTAINED
    assert result.profile is None
    assert result.diagnostics[-1].status is MechanismApplicabilityStatus.NOT_EVALUABLE


@pytest.mark.parametrize("value", ["postcode", "unsupported-disease"])
def test_prohibited_or_outside_catalogue_abstains(value: str) -> None:
    request = _request(disease=value)
    if value == "unsupported-disease":
        request = request.model_copy(
            update={
                "policy": request.policy.model_copy(
                    update={
                        "rules": (
                            _rule(
                                "disease",
                                ContextDimension.DISEASE_CLASS,
                                ("glioma",),
                                proxies=("postcode",),
                            ),
                            request.policy.rules[1],
                        )
                    }
                )
            }
        )
    result = M1102ContextEngine().stratify(request)
    assert result.status is ContextStratificationStatus.ABSTAINED
    assert result.profile is None


def test_authorization_precedes_opaque_content_and_denied_consent_fails_closed() -> None:
    with pytest.raises(M1102AuthorizationError):
        M1102ContextEngine().stratify(_request(consent=ConsentState.WITHHELD))


def test_strict_validation_rejects_wrong_hypothesis_media_type() -> None:
    request = _request().model_copy(
        update={"hypothesis_registry": _artifact("wrong", "application/json")}
    )
    with pytest.raises(ValidationError, match="M11-01"):
        M1102Service.validate_request(request)


def test_service_and_plugin_have_one_canonical_result() -> None:
    request = _request()
    service = M1102Service()
    direct = service.execute(request)
    plugin = M1102Plugin(service)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M11-02"
    token = plugin.validate(request)

    assert isinstance(token, ValidatedM1102Request)
    assert plugin.run(token).model_dump(mode="json") == direct.model_dump(mode="json")
    raw = json.dumps(request.model_dump(mode="json"), sort_keys=True)
    assert plugin.run(plugin.validate(raw)).model_dump(mode="json") == direct.model_dump(
        mode="json"
    )
    assert plugin.verify(direct).model_dump(mode="json") == direct.model_dump(mode="json")


def test_plugin_rejects_forged_or_unvalidated_execution_token() -> None:
    plugin = M1102Plugin(M1102Service())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(ValidatedM1102Request(request=_request(), _seal=object()))


def test_tampered_result_fails_replay_verification() -> None:
    engine = M1102ContextEngine()
    result = engine.stratify(_request())
    tampered = result.model_copy(update={"abstention_reason": "tampered"})

    with pytest.raises((ValidationError, M1102ReplayVerificationError)):
        engine.verify(tampered)


def test_policy_and_mechanism_duplicate_ids_are_rejected() -> None:
    rule = _rule("duplicate", ContextDimension.DISEASE_CLASS, ("glioma",))
    with pytest.raises(ValidationError, match="rule ids must be unique"):
        ContextStratificationPolicy(
            policy_id="policy.duplicate",
            version="1.0.0",
            dimensions=(ContextDimension.DISEASE_CLASS,),
            rules=(rule, rule),
            minimum_support_score=0.8,
        )


def test_policy_and_rule_boundaries_reject_duplicate_or_out_of_scope_members() -> None:
    rule = _rule("boundary", ContextDimension.DISEASE_CLASS, ("glioma",), proxies=("postcode",))
    with pytest.raises(ValidationError, match="allowed values must be unique"):
        type(rule).model_validate(rule.model_copy(update={"allowed_values": ("glioma", "glioma")}))
    with pytest.raises(ValidationError, match="prohibited proxies must be unique"):
        type(rule).model_validate(
            rule.model_copy(update={"prohibited_proxies": ("postcode", "postcode")})
        )
    with pytest.raises(ValidationError, match="dimensions must be unique"):
        ContextStratificationPolicy(
            policy_id="policy.duplicate-dimensions",
            version="1.0.0",
            dimensions=(ContextDimension.DISEASE_CLASS, ContextDimension.DISEASE_CLASS),
            rules=(rule,),
            minimum_support_score=0.8,
        )
    with pytest.raises(ValidationError, match="declared by policy"):
        ContextStratificationPolicy(
            policy_id="policy.out-of-scope",
            version="1.0.0",
            dimensions=(ContextDimension.SUBTYPE,),
            rules=(rule,),
            minimum_support_score=0.8,
        )


def test_request_and_profile_duplicate_dimensions_are_rejected() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="observations must contain each dimension once"):
        type(request).model_validate(
            request.model_copy(update={"observations": (request.observations[0],) * 2})
        )

    mechanism = MechanismApplicability(
        mechanism_id="mechanism.duplicate-dimensions",
        status=MechanismApplicabilityStatus.APPLICABLE,
        rationale="synthetic mechanism",
        context_dimensions=(ContextDimension.DISEASE_CLASS,),
    )
    with pytest.raises(ValidationError, match="mechanism applicability ids must be unique"):
        ContextProfile(
            profile_id="profile.duplicate",
            version="1.0.0",
            observations=(request.observations[0],),
            applicable_mechanisms=(mechanism, mechanism),
        )
    with pytest.raises(ValidationError, match="mechanism context dimensions must be unique"):
        type(mechanism).model_validate(
            mechanism.model_copy(
                update={
                    "context_dimensions": (
                        ContextDimension.DISEASE_CLASS,
                        ContextDimension.DISEASE_CLASS,
                    )
                }
            )
        )
    with pytest.raises(
        ValidationError, match="context observations must contain each dimension once"
    ):
        ContextProfile(
            profile_id="profile.duplicate-observations",
            version="1.0.0",
            observations=(request.observations[0], request.observations[0]),
            applicable_mechanisms=(mechanism,),
        )
    with pytest.raises(ValidationError, match="outside policy scope"):
        type(request).model_validate(
            request.model_copy(
                update={
                    "observations": (
                        _observation(ContextDimension.AGE, "adult"),
                        request.observations[1],
                    )
                }
            )
        )


def test_engine_fails_closed_for_non_mapping_and_invalid_result() -> None:
    engine = M1102ContextEngine()
    with pytest.raises(M1102AuthorizationError):
        engine.stratify(object())
    with pytest.raises(M1102ReplayVerificationError, match="strict result envelope"):
        engine.verify(object())

    class HostileMapping(dict[str, object]):
        def get(self, key: object, default: object = None) -> object:
            _ = default
            raise RuntimeError(f"unexpected access: {key}")  # noqa: TRY003

    with pytest.raises(M1102AuthorizationError):
        engine.stratify(HostileMapping())


def test_engine_can_verify_without_replay_and_detects_replay_drift() -> None:
    engine = M1102ContextEngine()
    result = engine.stratify(_request())
    assert engine.verify(result, replay=False).result_id == result.result_id

    class DivergentEngine(M1102ContextEngine):
        def stratify(self, request: object) -> VariantPeptideContextStratificationResult:
            typed = StratifyVariantPeptideContextRequest.model_validate(request, strict=True)
            return super().stratify(typed.model_copy(update={"request_id": "request.drifted"}))

    with pytest.raises(M1102ReplayVerificationError, match="different result"):
        DivergentEngine().verify(result)


def test_result_closure_rejects_identifier_evidence_status_review_and_digest_tampering() -> None:
    result = M1102ContextEngine().stratify(_request())
    abstained = M1102ContextEngine().stratify(_request(disease_score=0.2))
    cases = (
        ({"request_digest": "sha256:" + ("b" * 64)}, "does not bind the exact request"),
        ({"result_id": "result.wrong"}, "derived from request digest"),
        ({"evidence": ()}, "requires evidence"),
        ({"status": ContextStratificationStatus.STRATIFIED, "profile": None}, "supported context"),
        (
            {"status": ContextStratificationStatus.ABSTAINED, "profile": result.profile},
            "abstained result requires no profile",
        ),
        (
            {
                "status": abstained.status,
                "profile": None,
                "abstention_reason": abstained.abstention_reason,
                "support_decision": abstained.support_decision,
                "human_review_required": False,
            },
            "abstention requires human review",
        ),
        ({"result_digest": "sha256:" + ("b" * 64)}, "result digest"),
    )
    for updates, message in cases:
        with pytest.raises(ValidationError, match=message):
            type(result).model_validate(result.model_copy(update=updates))
