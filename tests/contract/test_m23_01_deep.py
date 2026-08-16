"""Adversarial contract, lock, source-binding, and replay coverage for M23-01."""

import hashlib
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from glio_proteogen.contracts.m23_01 import (
    M2301_DOSSIER_SHA256,
    M2301_DOSSIER_SLICE,
    AdjudicationRecord,
    AdjudicationStatus,
    BenchmarkConfiguration,
    CurateVariantPeptideReferenceTruthRequest,
    CurationStatus,
    EndpointDefinition,
    InclusionDecision,
    ReferenceEntry,
    ReferenceKind,
    ReferenceTruthPackage,
    VariantPeptideReferenceTruthResult,
    canonical_request_digest,
    contract_json_schemas,
    package_payload_digest,
    result_identifier,
    result_payload_digest,
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

_SCHEMA_COUNT = 9


def _artifact(name: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="0.1.0",
        digest="sha256:" + hashlib.sha256(name.encode()).hexdigest(),
        media_type="application/json",
    )


def _evidence(name: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(name),
        role="evidence",
        claim="Caller-declared M23-01 benchmark evidence.",
    )


def _uncertainty() -> UncertaintyProfile:
    return UncertaintyProfile(
        **cast(
            "Any",
            {
                field: UncertaintyEstimate(
                    state=EstimateState.NOT_ESTIMABLE,
                    rationale="No calibrated estimate is asserted by this provisional module.",
                )
                for field in (
                    "measurement",
                    "sampling",
                    "parameter",
                    "model_form",
                    "identification",
                    "support",
                    "transport",
                )
            },
        )
    )


def _context(request_id: str = "request-1") -> ExecutionContext:
    artifact = _artifact("context-control")
    upstream = UpstreamDecisionReference(
        decision_id="decision-accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="test-actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=upstream,
            identity_lineage=IdentityLineageReference(
                decision_id="identity-resolved",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "b" * 64,
                evidence=artifact,
            ),
            provenance=upstream,
            consent=ConsentReference(
                decision_id="consent-granted",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifact,
            ),
            quality=upstream,
            support=upstream,
            intended_use=upstream,
        ),
    )


def _entry(identifier: str, kind: ReferenceKind) -> ReferenceEntry:
    return ReferenceEntry(
        reference_id=identifier,
        kind=kind,
        artifact=_artifact(identifier),
        expected_label="known variant peptide reference",
        inclusion_reason="registered benchmark material",
        provenance_artifact=_artifact(identifier + "-provenance"),
        challenge_set=kind is ReferenceKind.CHALLENGE_SET,
        uncertainty=_uncertainty(),
        evidence=(_evidence(identifier + "-evidence"),),
    )


def _request() -> CurateVariantPeptideReferenceTruthRequest:
    references = (
        _entry("calibrator-1", ReferenceKind.CALIBRATOR),
        _entry("challenge-1", ReferenceKind.CHALLENGE_SET),
    )
    controls = (
        _entry("positive-control-1", ReferenceKind.POSITIVE_CONTROL),
        _entry("negative-control-1", ReferenceKind.NEGATIVE_CONTROL),
    )
    ids = tuple(item.reference_id for item in (*references, *controls))
    endpoint = EndpointDefinition(
        endpoint_id="endpoint-1",
        name="Variant peptide reference endpoint",
        definition="Reference truth for variant peptide.",
        metric="calibration_error",
        acceptance_tolerance="Within preregistered tolerance.",
        evidence=(_evidence("endpoint-evidence"),),
    )
    configuration = BenchmarkConfiguration(
        configuration_id="configuration-1",
        version="0.1.0",
        evidence=(_evidence("configuration-evidence"),),
    )
    source_names = [
        "endpoint-evidence",
        "configuration-evidence",
    ]
    for entry in (*references, *controls):
        source_names.extend(
            [
                entry.reference_id,
                entry.reference_id + "-provenance",
                entry.reference_id + "-evidence",
            ]
        )
    source_names.extend(identifier + "-inclusion" for identifier in ids)
    source_names.extend(identifier + "-adjudication" for identifier in ids)
    return CurateVariantPeptideReferenceTruthRequest(
        request_id="request-1",
        context=_context(),
        endpoint=endpoint,
        references=references,
        controls=controls,
        inclusions=tuple(
            InclusionDecision(
                reference_id=identifier,
                included=True,
                rationale="meets locked benchmark inclusion policy",
                leakage_audit="audited against challenge partition",
                evidence=(_evidence(identifier + "-inclusion"),),
            )
            for identifier in ids
        ),
        adjudications=tuple(
            AdjudicationRecord(
                reference_id=identifier,
                status=AdjudicationStatus.LOCKED,
                reviewer_tokens=("reviewer-a", "reviewer-b"),
                agreement_statement="Independent reviewers agree.",
                evidence=(_evidence(identifier + "-adjudication"),),
            )
            for identifier in ids
        ),
        configuration=configuration,
        source_artifacts=tuple(_artifact(name) for name in source_names),
    )


def _package(request: CurateVariantPeptideReferenceTruthRequest) -> ReferenceTruthPackage:
    base: dict[str, Any] = {
        "package_id": "package-1",
        "version": "0.1.0",
        "endpoint": request.endpoint,
        "references": request.references,
        "controls": request.controls,
        "inclusions": request.inclusions,
        "adjudications": request.adjudications,
        "challenge_set_ids": ("challenge-1",),
        "configuration": request.configuration,
        "lock_digest": "sha256:" + "0" * 64,
        "locked": True,
        "evidence": (_evidence("package-evidence"),),
    }
    provisional = ReferenceTruthPackage.model_construct(**cast("Any", base))
    base["lock_digest"] = package_payload_digest(provisional)
    return ReferenceTruthPackage(**cast("Any", base))


def _provenance() -> ProvenanceRecord:
    digest = "sha256:" + "c" * 64
    states = {
        ControlRole.APPROVED_CONFIGURATION: "accepted",
        ControlRole.IDENTITY_LINEAGE: "resolved",
        ControlRole.PROVENANCE: "accepted",
        ControlRole.CONSENT: "granted",
        ControlRole.QUALITY: "accepted",
        ControlRole.SUPPORT: "accepted",
        ControlRole.INTENDED_USE: "accepted",
    }
    return ProvenanceRecord(
        activity_id="activity-1",
        actor_id="test-actor",
        module_id="GLIO-PROTEOGEN-M23-01",
        module_version="0.1.0-provisional",
        generated_at=datetime(2026, 8, 16, tzinfo=UTC),
        input_digests=(digest,),
        configuration_digest=digest,
        consent_decision_id="consent-granted",
        consent_state=ConsentState.GRANTED,
        consent_policy_version="1.0.0",
        consent_evidence_digest=digest,
        control_decisions=tuple(
            ControlDecisionRecord(
                role=role,
                decision_id="control-" + role.value,
                state=states[role],
                policy_version="1.0.0",
                evidence_digest=digest,
                subject_digest=digest if role is ControlRole.IDENTITY_LINEAGE else None,
            )
            for role in ControlRole
        ),
    )


def _result(
    request: CurateVariantPeptideReferenceTruthRequest,
) -> VariantPeptideReferenceTruthResult:
    base: dict[str, Any] = {
        "result_id": result_identifier(canonical_request_digest(request)),
        "request_digest": canonical_request_digest(request),
        "result_digest": "sha256:" + "0" * 64,
        "request": request,
        "status": CurationStatus.CURATED,
        "package": _package(request),
        "findings": (),
        "abstention_reason": None,
        "support_decision": SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="supported_locked_reference_truth",
            rationale="all required controls and lock evidence are present",
        ),
        "uncertainty": _uncertainty(),
        "provenance": _provenance(),
        "evidence": (_evidence("result-evidence"),),
        "limitations": (
            Limitation(
                code="caller_declared_reference_truth",
                statement="Issuer authority is not authenticated.",
            ),
        ),
        "human_review_required": True,
    }
    provisional = VariantPeptideReferenceTruthResult.model_construct(**cast("Any", base))
    base["result_digest"] = result_payload_digest(provisional)
    return VariantPeptideReferenceTruthResult(**cast("Any", base))


def test_authority_and_schema_metadata_are_locked() -> None:
    schemas = cast("dict[str, dict[str, Any]]", contract_json_schemas())
    assert M2301_DOSSIER_SHA256.startswith("sha256:")
    assert M2301_DOSSIER_SLICE.endswith(":7956-7996")
    assert len(schemas) == _SCHEMA_COUNT
    assert all(
        schema["x-glio-contract"]["parentTarget"] == "variant peptide"
        for schema in schemas.values()
    )
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())


def test_locked_package_and_result_bind_canonical_digests() -> None:
    request = _request()
    package = _package(request)
    result = _result(request)
    assert package.lock_digest == package_payload_digest(package)
    assert result.request_digest == canonical_request_digest(request)
    assert result.result_digest == result_payload_digest(result)


def test_request_rejects_context_or_source_substitution() -> None:
    request = _request()
    with pytest.raises(ValueError, match="request ID"):
        CurateVariantPeptideReferenceTruthRequest(
            **request.model_copy(update={"context": _context("different")}).model_dump(
                mode="python"
            )
        )
    source = request.source_artifacts[0].model_copy(update={"digest": "sha256:" + "f" * 64})
    with pytest.raises(ValueError, match="bind every declared"):
        CurateVariantPeptideReferenceTruthRequest(
            **request.model_copy(
                update={"source_artifacts": (source, *request.source_artifacts[1:])}
            ).model_dump(mode="python")
        )


def test_package_rejects_pending_adjudication_or_lock_tamper() -> None:
    request = _request()
    package = _package(request)
    pending = package.adjudications[0].model_copy(update={"status": AdjudicationStatus.PENDING})
    with pytest.raises(ValueError, match="locked adjudications"):
        ReferenceTruthPackage.model_validate(
            package.model_copy(
                update={"adjudications": (pending, *package.adjudications[1:])}
            ).model_dump()
        )
    with pytest.raises(ValueError, match="lock digest"):
        ReferenceTruthPackage.model_validate(
            package.model_copy(update={"lock_digest": "sha256:" + "f" * 64}).model_dump()
        )


def test_result_id_and_digest_replay_reject_tamper() -> None:
    request = _request()
    result = _result(request)
    with pytest.raises(ValueError, match="result identifier"):
        VariantPeptideReferenceTruthResult.model_validate(
            result.model_copy(update={"result_id": "result-tampered"}).model_dump()
        )
    with pytest.raises(ValueError, match="result digest"):
        VariantPeptideReferenceTruthResult.model_validate(
            result.model_copy(update={"result_digest": "sha256:" + "f" * 64}).model_dump()
        )
