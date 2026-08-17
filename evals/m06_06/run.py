"""Genuine contract-level scenarios for the provisional M06-06 handoff.

The repository base contains M06-05 contracts but no M06-05 runtime.  This
builder therefore creates a fully validated, content-digested synthetic
M06-05 result.  It deliberately does not claim upstream estimator execution.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m06_01.v1 import (
    FormalProteinStateSchema,
    FormalStateFeatureDefinition,
    FormalStateFeatureValue,
    FormalStateFeatureValueKind,
    FormalStateMissingness,
)
from glio_proteogen.contracts.m06_05 import (
    M0605_ADVANCED_ESTIMATOR_MEDIA_TYPE,
    ConstraintAblationRecord,
    ConstraintAwareEstimate,
    ConstraintEvaluation,
    ConstraintEvaluationOutcome,
    ConstraintIntegrationStatus,
    IntegrateProteinAbundanceConstraintsRequest,
    IntegrateProteinAbundanceConstraintsResult,
    MechanismConstraint,
    MechanismConstraintHardness,
    MechanismConstraintKind,
    MechanismConstraintSet,
)
from glio_proteogen.contracts.m06_05.canonical import (
    canonical_request_digest as m0605_request_digest,
)
from glio_proteogen.contracts.m06_05.canonical import (
    result_payload_digest as m0605_result_digest,
)
from glio_proteogen.contracts.m06_06 import (
    DecomposeProteinAbundanceUncertaintyRequest,
    UncertaintyDecompositionPolicy,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c06_protein_abundance.m06_06_uncertainty_decomposition import (
    M0606Service,
)

_DIGEST: Final = "sha256:" + ("a" * 64)
_WHEN: Final = datetime(2026, 1, 1, tzinfo=UTC)


def _artifact(role: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"m0606.synthetic.{role}",
        version="1.0.0",
        digest=_DIGEST,
        media_type=media_type,
    )


def _accepted(role: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{role}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(role),
    )


def _context(request_id: str) -> ExecutionContext:
    return ExecutionContext(
        request_id=request_id,
        actor_id="actor.m0606.synthetic",
        occurred_at=_WHEN,
        references=ContextReferences(
            approved_configuration=_accepted("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_DIGEST,
                evidence=_artifact("identity"),
            ),
            provenance=_accepted("provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=_accepted("quality"),
            support=_accepted("support"),
            intended_use=_accepted("intended-use"),
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="Synthetic upstream uncertainty is not used as an estimate.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=("contract-level synthetic upstream",),
    )


def _provenance(
    context: ExecutionContext,
    module_id: str,
    module_version: str,
    request_digest: str,
    result_digest: str,
) -> ProvenanceRecord:
    refs = context.references
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=context.actor_id,
        module_id=module_id,
        module_version=module_version,
        generated_at=context.occurred_at,
        input_digests=(request_digest, result_digest),
        configuration_digest=_DIGEST,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=(),  # replaced below with the explicit seven records
    )


def _upstream_provenance(context: ExecutionContext, request_digest: str) -> ProvenanceRecord:
    refs = context.references
    decisions = (
        ("approved_configuration", refs.approved_configuration),
        ("identity_lineage", refs.identity_lineage),
        ("provenance", refs.provenance),
        ("consent", refs.consent),
        ("quality", refs.quality),
        ("support", refs.support),
        ("intended_use", refs.intended_use),
    )
    records = tuple(
        ControlDecisionRecord(
            role=ControlRole(role),
            decision_id=reference.decision_id,
            state=reference.state.value,
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=getattr(reference, "binding_digest", None),
        )
        for role, reference in decisions
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=context.actor_id,
        module_id="GLIO-PROTEOGEN-M06-05",
        module_version="0.1.0-provisional",
        generated_at=context.occurred_at,
        input_digests=(request_digest,),
        configuration_digest=_DIGEST,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=records,
    )


def _m0605_request() -> IntegrateProteinAbundanceConstraintsRequest:
    context = _context("m0605.request")
    feature = FormalStateFeatureDefinition(
        feature_id="feature.abundance",
        version="1.0.0",
        value_kind=FormalStateFeatureValueKind.SCALAR,
        unit="relative_abundance",
        allowed_missingness=(FormalStateMissingness.OBSERVED,),
        domain_lower=0.0,
        domain_upper=10.0,
    )
    schema = FormalProteinStateSchema(
        schema_id="schema.m0605.synthetic",
        version="1.0.0",
        features=(feature,),
    )
    value = FormalStateFeatureValue(
        feature_id="feature.abundance",
        state=FormalStateMissingness.OBSERVED,
        unit="relative_abundance",
        scalar_value=2.5,
    )
    constraint = MechanismConstraint(
        constraint_id="constraint.nonnegative-abundance",
        version="1.0.0",
        kind=MechanismConstraintKind.BIOLOGICAL_PRIOR,
        hardness=MechanismConstraintHardness.SOFT,
        expression="feature.abundance >= 0",
        feature_ids=("feature.abundance",),
        weight=0.5,
    )
    return IntegrateProteinAbundanceConstraintsRequest(
        request_id="m0605.request",
        context=context,
        state_schema=schema,
        feature_values=(value,),
        constraint_set=MechanismConstraintSet(
            constraint_set_id="constraints.m0605.synthetic",
            version="1.0.0",
            constraints=(constraint,),
            reviewed_by="reviewer.synthetic",
        ),
        advanced_estimator_result=_artifact(
            "advanced-estimator", M0605_ADVANCED_ESTIMATOR_MEDIA_TYPE
        ),
        source_artifacts=(_artifact("upstream-source"),),
    )


def _m0605_result(*, abstained: bool) -> IntegrateProteinAbundanceConstraintsResult:
    request = _m0605_request()
    request_digest = m0605_request_digest(request)
    evidence = (
        EvidenceReference(
            reference=_artifact("upstream-evidence"),
            role="evidence",
            claim="Synthetic contract-level upstream evidence.",
        ),
    )
    evaluation = ConstraintEvaluation(
        constraint_id="constraint.nonnegative-abundance",
        outcome=ConstraintEvaluationOutcome.SATISFIED,
        residual=0.0,
        effect_size=0.5,
        message="Synthetic constraint satisfied.",
        evidence=evidence,
    )
    ablation = ConstraintAblationRecord(
        constraint_id="constraint.nonnegative-abundance",
        with_constraint_effect=1.0,
        without_constraint_effect=0.5,
        effect_delta=0.5,
        evidence=evidence,
    )
    payload: dict[str, Any] = {
        "result_id": "result.m0605.synthetic",
        "result_version": "0.1.0-provisional",
        "request_digest": request_digest,
        "result_digest": _DIGEST,
        "request": request,
        "status": (
            ConstraintIntegrationStatus.ABSTAINED
            if abstained
            else ConstraintIntegrationStatus.INTEGRATED
        ),
        "estimates": (
            ()
            if abstained
            else (
                ConstraintAwareEstimate(
                    feature_id="feature.abundance",
                    unit="relative_abundance",
                    estimate_value=2.5,
                    lower_bound=0.0,
                    upper_bound=10.0,
                    evidence=evidence,
                ),
            )
        ),
        "evaluations": (evaluation,),
        "ablations": (ablation,),
        "abstention_reason": "Synthetic upstream review required." if abstained else None,
        "support_decision": SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED if abstained else SupportStatus.SUPPORTED,
            reason_code="synthetic_upstream",
            rationale="Synthetic result used only to exercise the M06-06 contract boundary.",
        ),
        "uncertainty": _uncertainty(),
        "provenance": _upstream_provenance(request.context, request_digest),
        "evidence": evidence,
        "limitations": (
            Limitation(
                code="synthetic_upstream",
                statement="This result is contract-level synthetic data.",
            ),
        ),
    }
    constructed = IntegrateProteinAbundanceConstraintsResult.model_construct(**payload)
    payload["result_digest"] = m0605_result_digest(constructed)
    return IntegrateProteinAbundanceConstraintsResult.model_validate(payload, strict=True)


@dataclass(frozen=True, slots=True)
class Scenario:
    request: DecomposeProteinAbundanceUncertaintyRequest
    expected_reason: str


def build_scenario(*, upstream_abstained: bool = False) -> Scenario:
    upstream = _m0605_result(abstained=upstream_abstained)
    policy = UncertaintyDecompositionPolicy(
        policy_id="policy.m0606.synthetic",
        version="1.0.0",
        method="provisional-no-calibration",
        calibration_reference=_artifact("calibration"),
    )
    request = DecomposeProteinAbundanceUncertaintyRequest(
        request_id="m0606.request",
        context=_context("m0606.request"),
        constraint_result=upstream,
        policy=policy,
        source_artifacts=(_artifact("uncertainty-source"),),
    )
    return Scenario(
        request=request,
        expected_reason="The bound upstream result is abstained."
        if upstream_abstained
        else "Owner-confirmed calibration and benchmark coverage are not locked.",
    )


def run_evaluation() -> dict[str, object]:
    service = M0606Service()
    cases = {
        "integrated_upstream": build_scenario(),
        "abstained_upstream": build_scenario(upstream_abstained=True),
    }
    outputs = {name: service.execute(case.request) for name, case in cases.items()}
    return {
        "module": "GLIO-PROTEOGEN-M06-06",
        "provisional_abi": True,
        "upstream_builder": "contract-level synthetic M06-05 result; no estimator execution",
        "scenarios": {
            name: {
                "status": output.status.value,
                "sensitivity": output.sensitivity_envelope.status.value,
                "support": output.support_decision.status.value,
                "reason": output.abstention_reason,
                "result_digest": output.result_digest,
            }
            for name, output in outputs.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the M06-06 provisional evaluator.")
    parser.add_argument("--json", action="store_true", help="Emit canonical JSON.")
    args = parser.parse_args()
    payload = run_evaluation()
    sys.stdout.write(
        (json.dumps(payload, indent=2, sort_keys=True) if args.json else str(payload)) + "\n"
    )


if __name__ == "__main__":
    main()
