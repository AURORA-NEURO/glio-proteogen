"""Build and evaluate genuine M06-01 formal-state replay scenarios."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m06_01 import (
    FormalProteinStateSchema,
    FormalStateFeatureDefinition,
    FormalStateFeatureValue,
    FormalStateFeatureValueKind,
    FormalStateMissingness,
    FormalStateValidationStatus,
    ValidateFormalProteinStateRequest,
    ValidateFormalProteinStateResult,
)
from glio_proteogen.contracts.m06_01.canonical import (
    canonical_request_digest as m0601_request_digest,
)
from glio_proteogen.contracts.m06_01.canonical import (
    result_payload_digest as m0601_result_digest,
)
from glio_proteogen.contracts.m06_03 import (
    BaselineEstimatorFamily,
    BaselinePreprocessingPolicy,
    BaselineResultStatus,
    BaselineTuningRecord,
    EstimateProteinAbundanceBaselineRequest,
    MatureBaselineConfiguration,
)
from glio_proteogen.kernel.canonical import sha256_digest
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
from glio_proteogen.modules.c06_estimation.m06_03_mature_baseline_estimator import (
    estimate_protein_abundance_baseline,
)

FIXED_TIME = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class Scenario:
    case_id: str
    request: EstimateProteinAbundanceBaselineRequest
    expected_status: BaselineResultStatus


def _digest(value: object) -> str:
    return sha256_digest(value)


def _artifact(label: str, *, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"evidence.{label}",
        version="0.1.0",
        digest=digest or _digest({"label": label}),
        media_type="application/vnd.glio-proteogen.m06-03.evidence+json",
    )


def _context(label: str) -> ExecutionContext:
    def decision(role: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.{label}.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="0.1.0",
            evidence=_artifact(f"control-{label}-{role}"),
        )

    return ExecutionContext(
        request_id=f"request.{label}",
        actor_id=f"actor.{label}",
        occurred_at=FIXED_TIME,
        references=ContextReferences(
            approved_configuration=decision("approved-configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id=f"decision.{label}.identity-lineage",
                state=IdentityLineageState.RESOLVED,
                policy_version="0.1.0",
                binding_digest=_digest({"identity": label}),
                evidence=_artifact(f"control-{label}-identity-lineage"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id=f"decision.{label}.consent",
                state=ConsentState.GRANTED,
                policy_version="0.1.0",
                evidence=_artifact(f"control-{label}-consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(reason: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=reason)

    return UncertaintyProfile(
        measurement=unavailable("No measurement model."),
        sampling=unavailable("No sampling model."),
        parameter=unavailable("No fitted parameters."),
        model_form=unavailable("Transparent baseline only."),
        identification=unavailable("Caller-declared feature identity."),
        support=unavailable("Support inherited from M06-01."),
        transport=unavailable("No transport model."),
    )


def _provenance(
    context: ExecutionContext,
    module_id: str,
    version: str,
    inputs: tuple[str, ...],
) -> ProvenanceRecord:
    refs = context.references
    entries = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration, None),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage, refs.identity_lineage.binding_digest),
        (ControlRole.PROVENANCE, refs.provenance, None),
        (ControlRole.CONSENT, refs.consent, None),
        (ControlRole.QUALITY, refs.quality, None),
        (ControlRole.SUPPORT, refs.support, None),
        (ControlRole.INTENDED_USE, refs.intended_use, None),
    )
    return ProvenanceRecord(
        activity_id=f"activity.{module_id.lower()}.{context.request_id}",
        actor_id=context.actor_id,
        module_id=module_id,
        module_version=version,
        generated_at=context.occurred_at,
        input_digests=inputs,
        configuration_digest=_digest({"module": module_id, "request": context.request_id}),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=tuple(
            ControlDecisionRecord(
                role=role,
                decision_id=reference.decision_id,
                state=reference.state.value,
                policy_version=reference.policy_version,
                evidence_digest=reference.evidence.digest,
                subject_digest=subject,
            )
            for role, reference, subject in entries
        ),
    )


def _formal_state(label: str, *, status: FormalStateValidationStatus, missing: bool) -> tuple[
    FormalProteinStateSchema,
    tuple[FormalStateFeatureValue, ...],
    ValidateFormalProteinStateResult,
]:
    definitions = (
        FormalStateFeatureDefinition(
            feature_id="feature.scalar",
            version="0.1.0",
            value_kind=FormalStateFeatureValueKind.SCALAR,
            unit="normalized-abundance",
            allowed_missingness=(FormalStateMissingness.OBSERVED, FormalStateMissingness.MISSING),
            domain_lower=0.0,
            domain_upper=10.0,
        ),
        FormalStateFeatureDefinition(
            feature_id="feature.interval",
            version="0.1.0",
            value_kind=FormalStateFeatureValueKind.INTERVAL,
            unit="normalized-abundance",
            allowed_missingness=(FormalStateMissingness.OBSERVED, FormalStateMissingness.MISSING),
        ),
        FormalStateFeatureDefinition(
            feature_id="feature.category",
            version="0.1.0",
            value_kind=FormalStateFeatureValueKind.CATEGORICAL,
            unit="category",
            allowed_missingness=(FormalStateMissingness.OBSERVED, FormalStateMissingness.MISSING),
            allowed_categories=("low", "high"),
        ),
    )
    schema = FormalProteinStateSchema(
        schema_id="schema.formal-state.m0603",
        version="0.1.0",
        features=definitions,
    )
    state = FormalStateMissingness.MISSING if missing else FormalStateMissingness.OBSERVED
    values = (
        FormalStateFeatureValue(
            feature_id="feature.scalar",
            state=state,
            unit="normalized-abundance",
            scalar_value=None if missing else 2.5,
        ),
        FormalStateFeatureValue(
            feature_id="feature.interval",
            state=FormalStateMissingness.OBSERVED,
            unit="normalized-abundance",
            interval_lower=1.0,
            interval_upper=3.0,
        ),
        FormalStateFeatureValue(
            feature_id="feature.category",
            state=FormalStateMissingness.OBSERVED,
            unit="category",
            category="high",
        ),
    )
    context = _context(label)
    upstream_request = ValidateFormalProteinStateRequest(
        request_id=context.request_id,
        context=context,
        state_schema=schema,
        values=values,
        source_artifacts=(_artifact(f"formal-state-source-{label}"),),
    )
    request_digest = m0601_request_digest(upstream_request)
    upstream_result_payload: dict[str, object] = {
        "result_id": f"result.m0601.{label}",
        "result_version": "0.1.0-provisional",
        "request_digest": request_digest,
        "result_digest": "sha256:" + ("0" * 64),
        "request": upstream_request,
        "status": status,
        "support_decision": SupportDecision(
            status=(
                SupportStatus.SUPPORTED
                if status is FormalStateValidationStatus.VALID
                else SupportStatus.REVIEW_REQUIRED
            ),
            reason_code=(
                "m0601_validated"
                if status is FormalStateValidationStatus.VALID
                else "m0601_not_evaluable"
            ),
            rationale="Synthetic formal-state result for genuine M06-03 replay.",
        ),
        "invariant_results": (),
        "parent_target": "biomarker_panel",
        "emits_parent": False,
        "uncertainty": _uncertainty(),
        "provenance": _provenance(
            context,
            "GLIO-PROTEOGEN-M06-01",
            "0.1.0",
            (request_digest,),
        ),
        "evidence": (
            EvidenceReference(
                reference=_artifact(f"formal-state-evidence-{label}"),
                role="evidence",
                claim="Formal-state validation evidence.",
            ),
        ),
        "limitations": (
            Limitation(code="formal_state_only", statement="Formal state only."),
        ),
    }
    upstream_result_payload["result_digest"] = m0601_result_digest(
        cast("Any", ValidateFormalProteinStateResult.model_construct)(
            **upstream_result_payload
        )
    )
    upstream_result = ValidateFormalProteinStateResult.model_validate(
        upstream_result_payload,
        strict=True,
    )
    return schema, values, upstream_result


def _request(
    label: str,
    *,
    status: FormalStateValidationStatus,
    missing: bool,
) -> EstimateProteinAbundanceBaselineRequest:
    schema, values, upstream_result = _formal_state(label, status=status, missing=missing)
    context = upstream_result.request.context
    configuration = MatureBaselineConfiguration(
        configuration_id=f"configuration.{label}",
        version="0.1.0",
        estimator_family=BaselineEstimatorFamily.ROBUST_STATISTICAL,
        state_schema_id=schema.schema_id,
        state_schema_version=schema.version,
        preprocessing=BaselinePreprocessingPolicy(
            policy_id=f"policy.preprocessing.{label}",
            version="0.1.0",
            operations=("unit-normalize", "robust-center"),
        ),
        tuning=BaselineTuningRecord(
            tuning_id=f"tuning.{label}",
            version="0.1.0",
            method="locked-reference-grid",
            objective="minimize locked validation loss",
            seed=7,
            metrics=("mean-absolute-error",),
        ),
        reference=_artifact(f"configuration-reference-{label}"),
    )
    return EstimateProteinAbundanceBaselineRequest(
        request_id=context.request_id,
        context=context,
        formal_state_result=upstream_result,
        state_schema=schema,
        feature_values=values,
        configuration=configuration,
        source_artifacts=(_artifact(f"baseline-source-{label}"),),
    )


@lru_cache(maxsize=8)
def build_scenario(case_id: str = "clear") -> Scenario:
    if case_id == "clear":
        return Scenario(
            case_id,
            _request(case_id, status=FormalStateValidationStatus.VALID, missing=False),
            BaselineResultStatus.ESTIMATED,
        )
    if case_id == "missing":
        return Scenario(
            case_id,
            _request(case_id, status=FormalStateValidationStatus.VALID, missing=True),
            BaselineResultStatus.ABSTAINED,
        )
    if case_id == "upstream-abstained":
        return Scenario(
            case_id,
            _request(case_id, status=FormalStateValidationStatus.ABSTAINED, missing=False),
            BaselineResultStatus.ABSTAINED,
        )
    raise ValueError(f"unsupported M06-03 scenario: {case_id}")  # noqa: TRY003


def run_evaluation() -> dict[str, object]:
    checks: list[dict[str, object]] = []
    for case_id in ("clear", "missing", "upstream-abstained"):
        result = estimate_protein_abundance_baseline(build_scenario(case_id).request)
        checks.append(
            {
                "case_id": case_id,
                "passed": result.status is build_scenario(case_id).expected_status,
                "status": result.status.value,
                "estimate_count": len(result.estimates),
            }
        )
    return {
        "module_id": "GLIO-PROTEOGEN-M06-03",
        "passed": all(bool(item["passed"]) for item in checks),
        "checks": checks,
    }


def canonical_smoke() -> dict[str, object]:
    request = build_scenario("clear").request
    result = estimate_protein_abundance_baseline(request)
    return {
        "request_digest": request.formal_state_result.request_digest,
        "result_digest": result.result_digest,
        "status": result.status.value,
        "result_bytes": len(json.dumps(result.model_dump(mode="json"), sort_keys=True).encode()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = run_evaluation()
    sys.stdout.write((json.dumps(report, sort_keys=True) if args.json else str(report)) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["Scenario", "build_scenario", "canonical_smoke", "run_evaluation"]
