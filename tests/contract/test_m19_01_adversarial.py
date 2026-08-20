"""Deep nested invariant and tamper coverage for M19-01."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m19_01 import (
    CompatibilityDecision,
    CompatibilityReport,
    CompatibilityRule,
    CompatibilityStatus,
    ProteotypeUpstreamResolutionResult,
    ResolverConfiguration,
    ResolverFindingCode,
    ValidatedUpstreamBundle,
)
from glio_proteogen.kernel.models import ConsentState, SupportDecision, SupportStatus
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m19_01_upstream_contract_resolver as m1901,
)
from tests.contract.test_m19_01_deep import (
    _candidate,
    _configuration,
    _decision,
    _evidence,
    _report,
    _request,
    _rule,
    _validated_result,
)


def _incompatible_decision() -> CompatibilityDecision:
    return CompatibilityDecision(
        candidate_id="candidate.proteome",
        status=CompatibilityStatus.INCOMPATIBLE,
        reason_code=ResolverFindingCode.INCOMPATIBLE,
        rationale="Explicitly incompatible for adversarial testing.",
        evidence=(_evidence("decision.incompatible"),),
    )


def _unknown_decision() -> CompatibilityDecision:
    return CompatibilityDecision(
        candidate_id="candidate.proteome",
        status=CompatibilityStatus.UNKNOWN,
        reason_code=ResolverFindingCode.COMPATIBILITY_UNKNOWN,
        rationale="Unknown for adversarial testing.",
        evidence=(_evidence("decision.unknown"),),
    )


def _other_decision() -> CompatibilityDecision:
    return CompatibilityDecision(
        candidate_id="candidate.other",
        status=CompatibilityStatus.COMPATIBLE,
        reason_code=ResolverFindingCode.COMPATIBLE_ACCEPTED,
        rationale="Other candidate for adversarial testing.",
        evidence=(_evidence("decision.other"),),
    )


def test_nested_evidence_and_artifact_digests_are_unique() -> None:
    with pytest.raises(ValidationError, match="rule evidence"):
        CompatibilityRule.model_validate(
            _rule().model_dump(mode="python") | {"evidence": (_evidence("same"),) * 2}
        )
    candidate = _candidate()
    with pytest.raises(ValidationError, match="artifact and provenance"):
        type(candidate).model_validate(
            candidate.model_dump(mode="python") | {"provenance_artifact": candidate.artifact}
        )
    with pytest.raises(ValidationError, match="candidate evidence"):
        type(candidate).model_validate(
            candidate.model_dump(mode="python") | {"evidence": (_evidence("same"),) * 2}
        )
    with pytest.raises(ValidationError, match="decision evidence"):
        CompatibilityDecision.model_validate(
            _decision().model_dump(mode="python") | {"evidence": (_evidence("same"),) * 2}
        )


def test_configuration_and_report_buckets_are_closed() -> None:
    with pytest.raises(ValidationError, match="accepted intended use"):
        ResolverConfiguration.model_validate(
            _configuration().model_dump(mode="python")
            | {"rules": (_rule().model_copy(update={"required_intended_use": "other"}),)}
        )
    with pytest.raises(ValidationError, match="configuration evidence"):
        ResolverConfiguration.model_validate(
            _configuration().model_dump(mode="python") | {"evidence": (_evidence("same"),) * 2}
        )
    decisions = (
        _decision(),
        _incompatible_decision().model_copy(update={"candidate_id": "candidate.incompatible"}),
        _unknown_decision().model_copy(update={"candidate_id": "candidate.unknown"}),
    )
    base = _report(decisions)
    with pytest.raises(ValidationError, match="decision candidate ids"):
        CompatibilityReport.model_validate(
            base.model_dump(mode="python") | {"decisions": (*decisions, _decision())}
        )
    with pytest.raises(ValidationError, match="mutually exclusive"):
        CompatibilityReport.model_validate(
            base.model_dump(mode="python") | {"rejected_candidate_ids": ("candidate.proteome",)}
        )
    with pytest.raises(ValidationError, match="selected candidates"):
        CompatibilityReport.model_validate(
            base.model_dump(mode="python")
            | {
                "selected_candidate_ids": ("candidate.incompatible",),
                "rejected_candidate_ids": ("candidate.proteome",),
            }
        )
    with pytest.raises(ValidationError, match="rejected candidates"):
        CompatibilityReport.model_validate(
            base.model_dump(mode="python")
            | {
                "rejected_candidate_ids": ("candidate.unknown",),
                "unresolved_candidate_ids": ("candidate.incompatible",),
            }
        )
    with pytest.raises(ValidationError, match="report evidence"):
        CompatibilityReport.model_validate(
            base.model_dump(mode="python") | {"evidence": (_evidence("same"),) * 2}
        )


def test_bundle_and_request_membership_closure_is_fail_closed() -> None:
    candidate = _candidate()
    with pytest.raises(ValidationError, match="validated candidate ids"):
        ValidatedUpstreamBundle(
            bundle_id="bundle.duplicate",
            version="1.0.0",
            candidates=(candidate, candidate),
            compatibility_report=_report(),
            evidence=(_evidence("bundle.duplicate"),),
        )
    with pytest.raises(ValidationError, match="match selected"):
        ValidatedUpstreamBundle(
            bundle_id="bundle.mismatch",
            version="1.0.0",
            candidates=(_candidate("candidate.other"),),
            compatibility_report=_report(),
            evidence=(_evidence("bundle.mismatch"),),
        )
    unsafe_candidate = candidate.model_dump(mode="python")
    unsafe_candidate["consent_state"] = ConsentState.UNKNOWN
    with pytest.raises(ValidationError, match="granted consent"):
        ValidatedUpstreamBundle(
            bundle_id="bundle.consent",
            version="1.0.0",
            candidates=(candidate.model_construct(**unsafe_candidate),),
            compatibility_report=_report(),
            evidence=(_evidence("bundle.consent"),),
        )
    with pytest.raises(ValidationError, match="bundle evidence"):
        ValidatedUpstreamBundle(
            bundle_id="bundle.evidence",
            version="1.0.0",
            candidates=(candidate,),
            compatibility_report=_report(),
            evidence=(_evidence("same"),) * 2,
        )
    request = _request()
    with pytest.raises(ValidationError, match="source artifact"):
        type(request).model_validate(
            request.model_dump(mode="python")
            | {"source_artifacts": (request.source_artifacts[0],) * 2}
        )


def test_result_status_report_and_support_closure_rejects_tampering() -> None:
    result = _validated_result()
    mismatched_report = _report((_other_decision(),))
    unknown_report = _report((_unknown_decision(),))
    with pytest.raises(ValidationError, match="classify every"):
        ProteotypeUpstreamResolutionResult.model_validate(
            result.model_dump(mode="python") | {"compatibility_report": mismatched_report}
        )
    with pytest.raises(ValidationError, match="evidence"):
        ProteotypeUpstreamResolutionResult.model_validate(
            result.model_dump(mode="python") | {"evidence": (_evidence("same"),) * 2}
        )
    with pytest.raises(ValidationError, match="supported upstream"):
        ProteotypeUpstreamResolutionResult.model_validate(
            result.model_dump(mode="python")
            | {
                "support_decision": SupportDecision(
                    status=SupportStatus.REVIEW_REQUIRED,
                    reason_code="review",
                    rationale="Forced review.",
                )
            }
        )
    with pytest.raises(ValidationError, match="at least one selected"):
        ProteotypeUpstreamResolutionResult.model_validate(
            result.model_dump(mode="python") | {"compatibility_report": unknown_report}
        )
    with pytest.raises(ValidationError, match="human review"):
        ProteotypeUpstreamResolutionResult.model_validate(
            result.model_dump(mode="python") | {"human_review_required": True}
        )
    abstained = m1901.M1901Engine().resolve(
        _request((_candidate("candidate.unknown", compatibility=CompatibilityStatus.UNKNOWN),))
    )
    with pytest.raises(ValidationError, match="no bundle"):
        ProteotypeUpstreamResolutionResult.model_validate(
            abstained.model_dump(mode="python") | {"bundle": result.bundle}
        )
    with pytest.raises(ValidationError, match="typed findings"):
        ProteotypeUpstreamResolutionResult.model_validate(
            abstained.model_dump(mode="python") | {"findings": (), "human_review_required": False}
        )


def test_provenance_covers_nested_candidate_and_rule_evidence() -> None:
    request = _request()
    result = m1901.M1901Engine().resolve(request)
    nested_digests = {
        *(candidate.artifact.digest for candidate in request.candidates),
        *(
            candidate.provenance_artifact.digest
            for candidate in request.candidates
            if candidate.provenance_artifact is not None
        ),
        *(artifact.digest for artifact in request.source_artifacts),
        *(item.reference.digest for item in request.configuration.evidence),
        *(item.reference.digest for rule in request.configuration.rules for item in rule.evidence),
        *(item.reference.digest for candidate in request.candidates for item in candidate.evidence),
    }
    assert nested_digests <= set(result.provenance.input_digests)
