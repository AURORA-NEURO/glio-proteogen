"""Strict contract, chain-closure, and tamper tests for M02-08 releases."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import TYPE_CHECKING, Any

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from pydantic import BaseModel, ValidationError

from glio_proteogen.contracts.m02_08 import (
    M0208_ARCHIVE_MEMBER_COUNT,
    M0208_AUTHORITY_LIMITATION_CODE,
    M0208_AUTHORITY_LIMITATION_STATEMENT,
    M0208_CALLER_ARTIFACT_COUNT,
    M0208_MANIFEST_PATH,
    M0208_MAX_ARTIFACT_BYTES,
    M0208_MAX_CANONICAL_REQUEST_BYTES,
    M0208_MAX_TOTAL_ARTIFACT_BYTES,
    M0208_PACKAGE_LIMITATION_CODE,
    M0208_PACKAGE_LIMITATION_STATEMENT,
    M0208_QUARANTINED_SUPPORT_RATIONALE,
    M0208_RELEASED_SUPPORT_RATIONALE,
    M0208_SENSITIVITY_NOTES,
    M0208_SIGNATURE_RECEIPT_PATH,
    M0208_UNCERTAINTY_RATIONALES,
    BuildIdentificationQcReleaseRequest,
    ExternalIdentificationSignature,
    IdentificationPackageVerificationReason,
    IdentificationQcReleaseResult,
    IdentificationQcReproducibilityManifest,
    IdentificationReferenceVersion,
    IdentificationReleaseArtifact,
    IdentificationReleaseArtifactRole,
    IdentificationReleaseDisposition,
    IdentificationReleaseMember,
    IdentificationReleasePackageDescriptor,
    IdentificationReleasePolicy,
    IdentificationReleaseQuarantine,
    IdentificationReleaseQuarantineCode,
    IdentificationReleaseVerification,
    IdentificationReproductionEvidence,
    IdentificationSignatureVerification,
    IdentificationSignatureVerificationReason,
    IdentificationSoftwareVersion,
    IdentificationStageProvenance,
    canonical_request_digest,
    context_digest,
    contract_json_schema,
    expected_release_quarantine_reasons,
    manifest_digest,
    policy_digest,
    release_evidence_index,
    reproduction_evidence_digest,
    signing_statement_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.canonical_ustar import sha256_bytes
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

if TYPE_CHECKING:
    from collections.abc import Callable

    from glio_proteogen.contracts.m02_08.schema import ContractName
    from glio_proteogen.kernel.models import Sha256Digest

pytestmark = pytest.mark.contract

_NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
_ZERO_DIGEST = "sha256:" + ("0" * 64)
_FORGED_DIGEST = "sha256:" + ("f" * 64)
_STAGE_MODULES = tuple(f"GLIO-PROTEOGEN-M02-{index:02d}" for index in range(1, 8))
_M0206_INDEX = 5
_M0207_INDEX = 6
_USTAR_MAX_PATH_BYTES = 255
_MAX_METADATA_RECORDS = 64
_MAX_ALLOWLIST_ENTRIES = 16
_ACCEPTED_DISPOSITIONS = (
    "conformant",
    "conformant",
    "accepted",
    "accepted",
    "accepted",
    "accepted",
    "supported",
)


def _digest(label: str) -> Sha256Digest:
    return sha256_digest(label)


def _artifact_reference(
    label: str,
    *,
    digest: Sha256Digest | None = None,
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m0208.{label}",
        version="1.0.0",
        digest=digest or _digest(f"artifact:{label}"),
        media_type="application/json",
    )


def _policy(
    *,
    max_total_bytes: int = M0208_MAX_TOTAL_ARTIFACT_BYTES,
    max_artifact_bytes: int = M0208_MAX_ARTIFACT_BYTES,
    algorithms: tuple[str, ...] = ("ed25519", "ecdsa-p256"),
    verifier_ids: tuple[str, ...] = ("verifier.primary", "verifier.backup"),
) -> IdentificationReleasePolicy:
    return IdentificationReleasePolicy(
        policy_id="policy.m0208.release",
        version="1.0.0",
        max_total_bytes=max_total_bytes,
        max_artifact_bytes=max_artifact_bytes,
        allowed_signature_algorithms=algorithms,
        allowed_verifier_ids=verifier_ids,
        evidence=_artifact_reference("release-policy"),
    )


def _context(policy: IdentificationReleasePolicy) -> ExecutionContext:
    return ExecutionContext(
        request_id="request.m0208.release",
        actor_id="actor.release-service",
        occurred_at=_NOW,
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="decision.m0208.configuration",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=_artifact_reference(
                    "approved-configuration",
                    digest=policy_digest(policy),
                ),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m0208.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_digest("subject:protein-subtype-release"),
                evidence=_artifact_reference("identity-lineage"),
            ),
            provenance=UpstreamDecisionReference(
                decision_id="decision.m0208.provenance",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=_artifact_reference("provenance-control"),
            ),
            consent=ConsentReference(
                decision_id="decision.m0208.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact_reference("consent-control"),
            ),
            quality=UpstreamDecisionReference(
                decision_id="decision.m0208.quality",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=_artifact_reference("quality-control"),
            ),
            support=UpstreamDecisionReference(
                decision_id="decision.m0208.support",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=_artifact_reference("support-control"),
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="decision.m0208.intended-use",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=_artifact_reference("intended-use-control"),
            ),
        ),
    )


def _caller_artifacts(
    *,
    declared_sizes: tuple[int, ...] | None = None,
) -> tuple[IdentificationReleaseArtifact, ...]:
    sizes = declared_sizes or ((128,) * len(IdentificationReleaseArtifactRole))
    return tuple(
        IdentificationReleaseArtifact(
            path=f"inputs/{index:02d}-{role.value}.json",
            role=role,
            reference=_artifact_reference(f"caller-{role.value}"),
            declared_size=sizes[index],
        )
        for index, role in enumerate(IdentificationReleaseArtifactRole)
    )


def _software_versions(count: int = 2) -> tuple[IdentificationSoftwareVersion, ...]:
    values = tuple(
        IdentificationSoftwareVersion(
            software_id=f"software.m0208.{index:02d}",
            version=f"1.0.{index}",
            build_digest=_digest(f"software-build:{index}"),
            evidence=_artifact_reference(f"software-evidence-{index}"),
        )
        for index in range(count)
    )
    return tuple(sorted(values, key=canonical_json_bytes))


def _reference_versions(count: int = 2) -> tuple[IdentificationReferenceVersion, ...]:
    values = tuple(
        IdentificationReferenceVersion(
            reference_id=f"reference.m0208.{index:02d}",
            build_id=f"build.m0208.{index:02d}",
            version=f"release-{index}",
            digest=_digest(f"reference-build:{index}"),
            evidence=_artifact_reference(f"reference-evidence-{index}"),
        )
        for index in range(count)
    )
    return tuple(sorted(values, key=canonical_json_bytes))


def _reproduction_evidence() -> IdentificationReproductionEvidence:
    return IdentificationReproductionEvidence(
        environment_lock=_artifact_reference("reproduction-environment-lock"),
        build_recipe=_artifact_reference("reproduction-build-recipe"),
        locked_tests=_artifact_reference("reproduction-locked-tests"),
        benchmark=_artifact_reference("reproduction-benchmark"),
        traceability=_artifact_reference("reproduction-traceability"),
        reviewer_signoff=_artifact_reference("reproduction-reviewer-signoff"),
        rollback=_artifact_reference("reproduction-rollback"),
    )


def _stages(
    artifacts: tuple[IdentificationReleaseArtifact, ...],
    *,
    updates: dict[int, dict[str, object]] | None = None,
) -> tuple[IdentificationStageProvenance, ...]:
    result_digests = tuple(_digest(f"stage-result:{index}") for index in range(7))
    subject_digest = _digest("subject:protein-subtype-release")
    values: list[IdentificationStageProvenance] = []
    for index, (module_id, disposition) in enumerate(
        zip(_STAGE_MODULES, _ACCEPTED_DISPOSITIONS, strict=True)
    ):
        bound: tuple[Sha256Digest, ...] = ()
        if index == _M0206_INDEX:
            bound = tuple(sorted(result_digests[:_M0206_INDEX]))
        elif index == _M0207_INDEX:
            bound = tuple(sorted((result_digests[3], result_digests[_M0206_INDEX])))
        payload: dict[str, object] = {
            "module_id": module_id,
            "module_version": "1.0.0",
            "result_digest": result_digests[index],
            "byte_digest": artifacts[index + 1].reference.digest,
            "disposition": disposition,
            "generated_at": _NOW,
            "configuration_digest": _digest(f"stage-configuration:{index}"),
            "identity_subject_digest": subject_digest,
            "analysis_lineage_digest": (
                result_digests[_M0206_INDEX]
                if index == _M0207_INDEX
                else _digest(f"analysis-lineage:{index}")
            ),
            "bound_upstream_result_digests": bound,
            "human_review_required": False,
        }
        if updates and index in updates:
            payload.update(updates[index])
        values.append(IdentificationStageProvenance.model_validate(payload, strict=True))
    return tuple(values)


def _manifest(
    *,
    artifacts: tuple[IdentificationReleaseArtifact, ...] | None = None,
    software_versions: tuple[IdentificationSoftwareVersion, ...] | None = None,
    reference_versions: tuple[IdentificationReferenceVersion, ...] | None = None,
    stage_updates: dict[int, dict[str, object]] | None = None,
) -> IdentificationQcReproducibilityManifest:
    release_policy = _policy()
    context = _context(release_policy)
    caller_artifacts = artifacts or _caller_artifacts()
    reproduction = _reproduction_evidence()
    stages = _stages(caller_artifacts, updates=stage_updates)
    return IdentificationQcReproducibilityManifest(
        release_id="release.identification-qc.2026-08-12",
        release_version="1.0.0",
        artifacts=caller_artifacts,
        stages=stages,
        software_versions=software_versions or _software_versions(),
        reference_versions=reference_versions or _reference_versions(),
        reproduction_evidence=reproduction,
        reproduction_evidence_digest=reproduction_evidence_digest(reproduction),
        m0206_transformation_manifest_digest=_digest("m0206-transformation-manifest"),
        m0204_quality_disposition=stages[3].disposition,
        m0207_support_disposition=stages[6].disposition,
        subject_binding_digest=context.references.identity_lineage.binding_digest,
        intended_use_evidence_digest=context.references.intended_use.evidence.digest,
        policy_digest=policy_digest(release_policy),
    )


def _signature(
    statement_digest: Sha256Digest,
    *,
    algorithm: str = "ed25519",
) -> ExternalIdentificationSignature:
    return ExternalIdentificationSignature(
        signer_id="signer.external-release",
        key_id="key.external-release.01",
        algorithm=algorithm,
        claimed_statement_digest=statement_digest,
        signature_value="ZmFrZS1zeW50aGV0aWMtc2lnbmF0dXJl",
        issued_at=_NOW,
        evidence=_artifact_reference("external-signature"),
    )


def _statement_digest(
    manifest: IdentificationQcReproducibilityManifest,
    release_policy: IdentificationReleasePolicy,
) -> Sha256Digest:
    return signing_statement_digest(
        active_manifest_digest=manifest_digest(manifest),
        active_policy_digest=policy_digest(release_policy),
        release_id=manifest.release_id,
        release_version=manifest.release_version,
        subject_binding_digest=manifest.subject_binding_digest,
        intended_use_evidence_digest=manifest.intended_use_evidence_digest,
    )


def _request_from_manifest(
    manifest: IdentificationQcReproducibilityManifest,
    release_policy: IdentificationReleasePolicy,
    context: ExecutionContext,
    signature: ExternalIdentificationSignature,
) -> BuildIdentificationQcReleaseRequest:
    return BuildIdentificationQcReleaseRequest(
        context=context,
        release_id=manifest.release_id,
        release_version=manifest.release_version,
        artifacts=manifest.artifacts,
        software_versions=manifest.software_versions,
        reference_versions=manifest.reference_versions,
        reproduction_evidence=manifest.reproduction_evidence,
        policy=release_policy,
        signature=signature,
    )


def _request() -> BuildIdentificationQcReleaseRequest:
    manifest = _manifest()
    release_policy = _policy()
    return _request_from_manifest(
        manifest,
        release_policy,
        _context(release_policy),
        _signature(_statement_digest(manifest, release_policy)),
    )


def _signature_verification(
    signature: ExternalIdentificationSignature,
    expected_statement: Sha256Digest,
    reason: IdentificationSignatureVerificationReason,
) -> IdentificationSignatureVerification:
    verifier_id = (
        "verifier.primary"
        if reason
        in {
            IdentificationSignatureVerificationReason.VERIFIED,
            IdentificationSignatureVerificationReason.VERIFIER_REJECTED,
        }
        else None
    )
    return IdentificationSignatureVerification(
        verifier_id=verifier_id,
        algorithm=signature.algorithm,
        key_id=signature.key_id,
        statement_digest=expected_statement,
        verified=reason is IdentificationSignatureVerificationReason.VERIFIED,
        reason_code=reason,
    )


def _control_decisions(context: ExecutionContext) -> tuple[ControlDecisionRecord, ...]:
    refs = context.references
    return (
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


def _uncertainty() -> UncertaintyProfile:
    values = {
        dimension: UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=rationale,
        )
        for dimension, rationale in M0208_UNCERTAINTY_RATIONALES.items()
    }
    return UncertaintyProfile(
        **values,
        sensitivity_notes=M0208_SENSITIVITY_NOTES,
    )


def _package_descriptor(
    manifest: IdentificationQcReproducibilityManifest,
    active_manifest_digest: Sha256Digest,
    verification: IdentificationSignatureVerification,
) -> IdentificationReleasePackageDescriptor:
    members = [
        IdentificationReleaseMember(
            path=item.path,
            byte_size=item.declared_size,
            digest=item.reference.digest,
            role=item.role,
        )
        for item in manifest.artifacts
    ]
    manifest_bytes = canonical_json_bytes(manifest.model_dump(mode="python"))
    receipt_bytes = canonical_json_bytes(verification.model_dump(mode="python"))
    members.extend(
        (
            IdentificationReleaseMember(
                path=M0208_MANIFEST_PATH,
                byte_size=len(manifest_bytes),
                digest=active_manifest_digest,
            ),
            IdentificationReleaseMember(
                path=M0208_SIGNATURE_RECEIPT_PATH,
                byte_size=len(receipt_bytes),
                digest=sha256_bytes(receipt_bytes),
            ),
        )
    )
    return IdentificationReleasePackageDescriptor(
        byte_size=20_480,
        digest=_digest("canonical-release-package"),
        members=tuple(sorted(members, key=canonical_json_bytes)),
    )


def _provenance_input_digests(
    request: BuildIdentificationQcReleaseRequest,
    manifest: IdentificationQcReproducibilityManifest,
    active_manifest_digest: Sha256Digest,
    controls: tuple[ControlDecisionRecord, ...],
) -> tuple[Sha256Digest, ...]:
    values = {
        canonical_request_digest(request),
        context_digest(request.context),
        policy_digest(request.policy),
        active_manifest_digest,
        *(stage.result_digest for stage in manifest.stages),
        *(stage.byte_digest for stage in manifest.stages),
        *(item.reference.digest for item in request.artifacts),
        *(item.build_digest for item in request.software_versions),
        *(item.digest for item in request.reference_versions),
        *(reference.digest for reference, _ in release_evidence_index(request)),
        *(item.evidence_digest for item in controls),
    }
    return tuple(sorted(values))


@cache
def _released_result() -> IdentificationQcReleaseResult:
    return _result()


def _result(
    *,
    stage_updates: dict[int, dict[str, object]] | None = None,
    verification_reason: IdentificationSignatureVerificationReason = (
        IdentificationSignatureVerificationReason.VERIFIED
    ),
) -> IdentificationQcReleaseResult:
    release_policy = _policy()
    context = _context(release_policy)
    manifest = _manifest(stage_updates=stage_updates)
    active_manifest_digest = manifest_digest(manifest)
    expected_statement = _statement_digest(manifest, release_policy)
    claimed_statement = (
        _digest("mismatched-signature-statement")
        if verification_reason is IdentificationSignatureVerificationReason.STATEMENT_MISMATCH
        else expected_statement
    )
    signature = _signature(claimed_statement)
    request = _request_from_manifest(manifest, release_policy, context, signature)
    verification = _signature_verification(signature, expected_statement, verification_reason)
    quarantine_reasons = expected_release_quarantine_reasons(manifest, verification)
    disposition = (
        IdentificationReleaseDisposition.QUARANTINED
        if quarantine_reasons
        else IdentificationReleaseDisposition.RELEASED
    )
    controls = _control_decisions(context)
    request_digest = canonical_request_digest(request)
    provenance = ProvenanceRecord(
        activity_id=f"activity.m0208.{request_digest.removeprefix('sha256:')}",
        actor_id=context.actor_id,
        module_id="GLIO-PROTEOGEN-M02-08",
        module_version="1.0.0",
        generated_at=context.occurred_at,
        input_digests=_provenance_input_digests(
            request,
            manifest,
            active_manifest_digest,
            controls,
        ),
        configuration_digest=policy_digest(release_policy),
        consent_decision_id=context.references.consent.decision_id,
        consent_state=context.references.consent.state,
        consent_policy_version=context.references.consent.policy_version,
        consent_evidence_digest=context.references.consent.evidence.digest,
        control_decisions=controls,
    )
    evidence = tuple(
        sorted(
            (
                EvidenceReference(reference=reference, role="evidence", claim=claim)
                for reference, claim in release_evidence_index(request)
            ),
            key=canonical_json_bytes,
        )
    )
    limitations = tuple(
        sorted(
            (
                Limitation(
                    code=M0208_PACKAGE_LIMITATION_CODE,
                    statement=M0208_PACKAGE_LIMITATION_STATEMENT,
                ),
                Limitation(
                    code=M0208_AUTHORITY_LIMITATION_CODE,
                    statement=M0208_AUTHORITY_LIMITATION_STATEMENT,
                ),
            ),
            key=canonical_json_bytes,
        )
    )
    released = disposition is IdentificationReleaseDisposition.RELEASED
    return IdentificationQcReleaseResult(
        release_result_id=f"release.m0208.{request_digest.removeprefix('sha256:')}",
        request_digest=request_digest,
        context_digest=context_digest(context),
        context=context,
        policy_digest=policy_digest(release_policy),
        policy=release_policy,
        manifest_digest=active_manifest_digest,
        manifest=manifest,
        signature=signature,
        signature_verification=verification,
        disposition=disposition,
        package_descriptor=(
            _package_descriptor(manifest, active_manifest_digest, verification)
            if released
            else None
        ),
        quarantine_reasons=quarantine_reasons,
        support=SupportDecision(
            status=SupportStatus.LIMITED if released else SupportStatus.REVIEW_REQUIRED,
            reason_code=(
                "identification_release_packaged"
                if released
                else "identification_release_quarantined"
            ),
            rationale=(
                M0208_RELEASED_SUPPORT_RATIONALE
                if released
                else M0208_QUARANTINED_SUPPORT_RATIONALE
            ),
        ),
        uncertainty=_uncertainty(),
        provenance=provenance,
        evidence=evidence,
        limitations=limitations,
        human_review_required=not released,
        completed_at=context.occurred_at,
    )


def _result_payload() -> dict[str, Any]:
    return deepcopy(_released_result().model_dump(mode="python"))


def _forge_caller_member_digest(value: dict[str, Any]) -> object:
    member = next(
        item
        for item in value["package_descriptor"]["members"]
        if item["role"] is not None
    )
    return member.update(digest=_FORGED_DIGEST)


def _package_verification() -> IdentificationReleaseVerification:
    result = _released_result()
    descriptor = result.package_descriptor
    assert descriptor is not None
    return IdentificationReleaseVerification(
        content_verified=True,
        authenticity_verified=True,
        verified=True,
        package_digest=descriptor.digest,
        manifest_digest=result.manifest_digest,
        member_count=M0208_ARCHIVE_MEMBER_COUNT,
        signature_verification=result.signature_verification,
        reason_code=IdentificationPackageVerificationReason.VERIFIED,
    )


@pytest.mark.parametrize(
    "name",
    ["request", "output", "policy", "artifact", "manifest", "verification", "signature"],
)
def test_all_seven_public_schemas_are_strict_draft_2020_12(name: ContractName) -> None:
    schema = contract_json_schema(name)

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == (
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-08:1.0.0:"
        f"{name}"
    )
    assert schema["additionalProperties"] is False
    metadata = {
        "moduleId": "GLIO-PROTEOGEN-M02-08",
        "contractVersion": "1.0.0",
        "strict": True,
        "rawPayload": False,
        "biologicalInterpretation": False,
        "exactByteReproduction": True,
        "signatureAuthorityOwnedExternally": True,
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0208_MAX_CANONICAL_REQUEST_BYTES
    assert schema["x-glio-contract"] == metadata
    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize(
    ("model", "factory"),
    [
        (BuildIdentificationQcReleaseRequest, _request),
        (IdentificationQcReleaseResult, _released_result),
        (IdentificationReleasePolicy, _policy),
        (IdentificationReleaseArtifact, lambda: _caller_artifacts()[0]),
        (IdentificationQcReproducibilityManifest, _manifest),
        (IdentificationReleaseVerification, _package_verification),
        (ExternalIdentificationSignature, lambda: _released_result().signature),
    ],
)
def test_every_public_model_rejects_unknown_fields(
    model: type[BaseModel],
    factory: Callable[[], BaseModel],
) -> None:
    payload = factory().model_dump(mode="python")
    payload["unexpected"] = True

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        model.model_validate(payload, strict=True)


def test_public_models_reject_primitive_coercion() -> None:
    policy = _policy().model_dump(mode="python")
    policy["max_total_bytes"] = "1024"
    with pytest.raises(ValidationError, match="valid integer"):
        IdentificationReleasePolicy.model_validate(policy, strict=True)

    verification = _package_verification().model_dump(mode="python")
    verification["member_count"] = "10"
    with pytest.raises(ValidationError, match="valid integer"):
        IdentificationReleaseVerification.model_validate(verification, strict=True)


@pytest.mark.parametrize(
    "path",
    [
        "/absolute/result.json",
        "../traversal.json",
        "inputs/../traversal.json",
        "inputs\\windows.json",
        "C:/drive.json",
        "inputs//alias.json",
        "META-INF/glio-proteogen-m02-08/forbidden.json",
        "meta-inf/GLIO-PROTEOGEN-M02-08/forbidden.json",
        "inputs/nonascii-é.json",
        f"inputs/{'n' * 101}",
    ],
)
def test_caller_paths_fail_closed_before_archive_assembly(path: str) -> None:
    payload = _caller_artifacts()[0].model_dump(mode="python")
    payload["path"] = path

    with pytest.raises(ValidationError):
        IdentificationReleaseArtifact.model_validate(payload, strict=True)


def test_maximum_ustar_path_shape_is_accepted_but_long_prefix_is_not() -> None:
    payload = _caller_artifacts()[0].model_dump(mode="python")
    payload["path"] = f"{'p' * 154}/{'n' * 100}"
    assert len(payload["path"].encode("ascii")) == _USTAR_MAX_PATH_BYTES
    assert (
        IdentificationReleaseArtifact.model_validate(payload, strict=True).path
        == payload["path"]
    )

    payload["path"] = f"{'p' * 156}/{'n' * 98}"
    with pytest.raises(ValidationError, match="not representable in USTAR"):
        IdentificationReleaseArtifact.model_validate(payload, strict=True)


@pytest.mark.parametrize("failure", ["duplicate_role", "case_alias"])
def test_request_requires_exact_roles_and_alias_free_paths(failure: str) -> None:
    manifest = _manifest()
    release_policy = _policy()
    context = _context(release_policy)
    signature = _signature(_statement_digest(manifest, release_policy))
    payload = _request_from_manifest(
        manifest, release_policy, context, signature
    ).model_dump(mode="python")
    if failure == "duplicate_role":
        payload["artifacts"][-1]["role"] = payload["artifacts"][0]["role"]
    else:
        payload["artifacts"][-1]["path"] = payload["artifacts"][0]["path"].upper()

    with pytest.raises(ValidationError):
        BuildIdentificationQcReleaseRequest.model_validate(payload, strict=True)


def test_artifact_and_policy_static_caps_are_closed() -> None:
    artifact = _caller_artifacts()[0].model_dump(mode="python")
    artifact["declared_size"] = M0208_MAX_ARTIFACT_BYTES
    assert IdentificationReleaseArtifact.model_validate(artifact, strict=True).declared_size == (
        M0208_MAX_ARTIFACT_BYTES
    )
    artifact["declared_size"] += 1
    with pytest.raises(ValidationError, match="less than or equal"):
        IdentificationReleaseArtifact.model_validate(artifact, strict=True)

    policy = _policy().model_dump(mode="python")
    policy["max_total_bytes"] = M0208_MAX_TOTAL_ARTIFACT_BYTES + 1
    with pytest.raises(ValidationError, match="less than or equal"):
        IdentificationReleasePolicy.model_validate(policy, strict=True)


@pytest.mark.parametrize(
    ("policy_updates", "message"),
    [
        ({"max_artifact_bytes": 127}, "per-artifact limit"),
        ({"max_total_bytes": 1023}, "active total limit"),
    ],
)
def test_request_enforces_active_policy_byte_caps(
    policy_updates: dict[str, int],
    message: str,
) -> None:
    release_policy = IdentificationReleasePolicy.model_validate(
        {**_policy().model_dump(mode="python"), **policy_updates},
        strict=True,
    )
    manifest = _manifest()
    context = _context(release_policy)
    signature = _signature(_statement_digest(manifest, release_policy))

    with pytest.raises(ValidationError, match=message):
        BuildIdentificationQcReleaseRequest(
            context=context,
            release_id=manifest.release_id,
            release_version=manifest.release_version,
            artifacts=manifest.artifacts,
            software_versions=manifest.software_versions,
            reference_versions=manifest.reference_versions,
            reproduction_evidence=manifest.reproduction_evidence,
            policy=release_policy,
            signature=signature,
        )


def test_policy_allowlists_and_reproduction_evidence_are_unique() -> None:
    policy = _policy().model_dump(mode="python")
    policy["allowed_verifier_ids"] = ("verifier.primary", "verifier.primary")
    with pytest.raises(ValidationError, match="allowlists must be unique"):
        IdentificationReleasePolicy.model_validate(policy, strict=True)

    evidence = _reproduction_evidence().model_dump(mode="python")
    evidence["rollback"]["digest"] = evidence["benchmark"]["digest"]
    with pytest.raises(ValidationError, match="digests must be unique"):
        IdentificationReproductionEvidence.model_validate(evidence, strict=True)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("algorithm", "algorithm is not allowed"),
        ("future", "cannot be issued after"),
        ("configuration", "does not bind the release policy"),
    ],
)
def test_request_policy_signature_and_configuration_are_bound(
    mutation: str,
    message: str,
) -> None:
    manifest = _manifest()
    release_policy = _policy()
    context = _context(release_policy)
    signature = _signature(_statement_digest(manifest, release_policy))
    payload = _request_from_manifest(
        manifest, release_policy, context, signature
    ).model_dump(mode="python")
    if mutation == "algorithm":
        payload["signature"]["algorithm"] = "rsa-legacy"
    elif mutation == "future":
        payload["signature"]["issued_at"] = _NOW + timedelta(seconds=1)
    else:
        payload["context"]["references"]["approved_configuration"]["evidence"][
            "digest"
        ] = _FORGED_DIGEST

    with pytest.raises(ValidationError, match=message):
        BuildIdentificationQcReleaseRequest.model_validate(payload, strict=True)


@pytest.mark.parametrize(
    ("role", "state", "message"),
    [
        ("consent", ConsentState.REVOKED, "consent does not authorize"),
        ("identity_lineage", IdentityLineageState.UNRESOLVED, "identity lineage"),
        ("quality", UpstreamDecisionState.REJECTED, "upstream controls"),
    ],
)
def test_request_requires_all_authorizing_controls(
    role: str,
    state: object,
    message: str,
) -> None:
    manifest = _manifest()
    release_policy = _policy()
    payload = _request_from_manifest(
        manifest,
        release_policy,
        _context(release_policy),
        _signature(_statement_digest(manifest, release_policy)),
    ).model_dump(mode="python")
    payload["context"]["references"][role]["state"] = state

    with pytest.raises(ValidationError, match=message):
        BuildIdentificationQcReleaseRequest.model_validate(payload, strict=True)


@pytest.mark.parametrize(
    ("index", "update"),
    [
        (0, {"disposition": "accepted"}),
        (5, {"bound_upstream_result_digests": (_ZERO_DIGEST,)}),
        (6, {"analysis_lineage_digest": _ZERO_DIGEST}),
        (6, {"identity_subject_digest": _ZERO_DIGEST}),
    ],
)
def test_stage_and_manifest_chain_forgery_fails_closed(
    index: int,
    update: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        _manifest(stage_updates={index: update})


def test_manifest_requires_ordered_complete_stage_chain() -> None:
    payload = _manifest().model_dump(mode="python")
    payload["stages"] = tuple(reversed(payload["stages"]))

    with pytest.raises(ValidationError, match="ordered M02-01 through M02-07"):
        IdentificationQcReproducibilityManifest.model_validate(payload, strict=True)


def test_manifest_binds_each_stage_artifact_to_its_exact_byte_digest() -> None:
    payload = _manifest().model_dump(mode="python")
    stage_artifact = next(
        item for item in payload["artifacts"] if item["role"] == "m02_01_conformance"
    )
    stage_artifact["reference"]["digest"] = _FORGED_DIGEST

    with pytest.raises(ValidationError):
        IdentificationQcReproducibilityManifest.model_validate(payload, strict=True)


def test_manifest_rejects_duplicate_metadata_ids_and_oversized_inventory() -> None:
    payload = _manifest().model_dump(mode="python")
    payload["software_versions"] = (
        payload["software_versions"][0],
        payload["software_versions"][0],
    )
    with pytest.raises(ValidationError):
        IdentificationQcReproducibilityManifest.model_validate(payload, strict=True)

    payload = _manifest().model_dump(mode="python")
    for item in payload["artifacts"]:
        item["declared_size"] = M0208_MAX_ARTIFACT_BYTES
    with pytest.raises(ValidationError):
        IdentificationQcReproducibilityManifest.model_validate(payload, strict=True)


def test_signature_verification_state_reason_and_verifier_are_relational() -> None:
    payload = _released_result().signature_verification.model_dump(mode="python")
    payload["verified"] = False
    with pytest.raises(ValidationError, match="verified state contradicts"):
        IdentificationSignatureVerification.model_validate(payload, strict=True)

    payload = _released_result().signature_verification.model_dump(mode="python")
    payload["verifier_id"] = None
    with pytest.raises(ValidationError, match="verifier identifier"):
        IdentificationSignatureVerification.model_validate(payload, strict=True)


def test_typed_quarantine_rejects_unknown_stage_vocabulary() -> None:
    with pytest.raises(ValidationError):
        IdentificationReleaseQuarantine.model_validate(
            {
                "code": IdentificationReleaseQuarantineCode.UPSTREAM_NOT_RELEASABLE,
                "stage_module_id": "GLIO-PROTEOGEN-M99-99",
                "reason_code": "stage_disposition_quarantined",
                "remediation_code": "review_upstream_stage",
            },
            strict=True,
        )


def test_package_descriptor_requires_exact_roles_and_generated_members() -> None:
    payload = _released_result().package_descriptor
    assert payload is not None
    values = payload.model_dump(mode="python")
    caller = next(item for item in values["members"] if item["role"] is not None)
    caller["role"] = None
    with pytest.raises(ValidationError):
        IdentificationReleasePackageDescriptor.model_validate(values, strict=True)

    values = payload.model_dump(mode="python")
    generated = next(
        item for item in values["members"] if item["path"] == M0208_MANIFEST_PATH
    )
    generated["role"] = IdentificationReleaseArtifactRole.PARENT_PROTEIN_SUBTYPE
    with pytest.raises(ValidationError):
        IdentificationReleasePackageDescriptor.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("reason", "expected_code"),
    [
        (
            IdentificationSignatureVerificationReason.VERIFIER_UNAVAILABLE,
            IdentificationReleaseQuarantineCode.SIGNATURE_UNVERIFIED,
        ),
        (
            IdentificationSignatureVerificationReason.VERIFIER_REJECTED,
            IdentificationReleaseQuarantineCode.SIGNATURE_UNVERIFIED,
        ),
        (
            IdentificationSignatureVerificationReason.STATEMENT_MISMATCH,
            IdentificationReleaseQuarantineCode.SIGNATURE_UNVERIFIED,
        ),
    ],
)
def test_unverified_signature_produces_typed_quarantine_without_package(
    reason: IdentificationSignatureVerificationReason,
    expected_code: IdentificationReleaseQuarantineCode,
) -> None:
    result = _result(verification_reason=reason)

    assert result.disposition is IdentificationReleaseDisposition.QUARANTINED
    assert result.package_descriptor is None
    assert tuple(item.code for item in result.quarantine_reasons) == (expected_code,)
    assert result.human_review_required is True


def test_unreleasable_stage_skips_verifier_and_names_exact_stage() -> None:
    result = _result(
        stage_updates={3: {"disposition": "quarantined", "human_review_required": True}},
        verification_reason=IdentificationSignatureVerificationReason.NOT_ATTEMPTED,
    )

    assert result.disposition is IdentificationReleaseDisposition.QUARANTINED
    assert result.signature_verification.reason_code is (
        IdentificationSignatureVerificationReason.NOT_ATTEMPTED
    )
    assert result.quarantine_reasons[0].stage_module_id == "GLIO-PROTEOGEN-M02-04"
    assert result.quarantine_reasons[0].reason_code == "human_review_required"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update(policy_digest=_FORGED_DIGEST), "policy digest"),
        (lambda value: value.update(manifest_digest=_FORGED_DIGEST), "manifest digest"),
        (
            lambda value: value["signature_verification"].update(
                statement_digest=_FORGED_DIGEST
            ),
            "does not bind the release statement",
        ),
        (_forge_caller_member_digest, "contradicts a caller artifact"),
        (
            lambda value: value["support"].update(rationale="Forged support rationale."),
            "support envelope contradicts",
        ),
        (
            lambda value: value["uncertainty"]["transport"].update(
                rationale="Forged transport uncertainty."
            ),
            "uncertainty must remain deterministic",
        ),
        (
            lambda value: value["provenance"].update(
                input_digests=value["provenance"]["input_digests"][:-1]
            ),
            "exact unique input digest set",
        ),
        (
            lambda value: value["provenance"]["control_decisions"][0].update(
                decision_id="decision.forged"
            ),
            "control decisions do not match",
        ),
        (
            lambda value: value["evidence"][0].update(claim="Forged evidence claim."),
            "evidence index or claims",
        ),
        (
            lambda value: value["limitations"][0].update(
                statement="Forged limitation statement."
            ),
            "requires both exact limitation",
        ),
        (lambda value: value.update(request_digest=_FORGED_DIGEST), "request digest"),
        (lambda value: value.update(result_digest=_FORGED_DIGEST), "result digest"),
    ],
)
def test_result_forgery_fails_closed(
    mutate: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    values = _result_payload()
    mutate(values)

    with pytest.raises(ValidationError, match=message):
        IdentificationQcReleaseResult.model_validate(values, strict=True)


def test_package_verification_requires_consistent_content_and_authenticity() -> None:
    values = _package_verification().model_dump(mode="python")
    values["content_verified"] = False
    with pytest.raises(ValidationError, match="verified state contradicts"):
        IdentificationReleaseVerification.model_validate(values, strict=True)

    values = _package_verification().model_dump(mode="python")
    values["member_count"] = 9
    with pytest.raises(ValidationError, match="complete content receipts"):
        IdentificationReleaseVerification.model_validate(values, strict=True)


def test_request_and_manifest_canonical_digests_ignore_semantic_reordering() -> None:
    manifest = _manifest()
    release_policy = _policy()
    context = _context(release_policy)
    request = _request_from_manifest(
        manifest,
        release_policy,
        context,
        _signature(_statement_digest(manifest, release_policy)),
    )
    request_values = request.model_dump(mode="python")
    for field in ("artifacts", "software_versions", "reference_versions"):
        request_values[field] = tuple(reversed(request_values[field]))
    request_values["policy"]["allowed_signature_algorithms"] = tuple(
        reversed(request_values["policy"]["allowed_signature_algorithms"])
    )
    request_values["policy"]["allowed_verifier_ids"] = tuple(
        reversed(request_values["policy"]["allowed_verifier_ids"])
    )
    reordered_request = BuildIdentificationQcReleaseRequest.model_validate(
        request_values, strict=True
    )
    assert canonical_request_digest(reordered_request) == canonical_request_digest(request)

    manifest_values = manifest.model_dump(mode="python")
    for field in ("artifacts", "software_versions", "reference_versions"):
        manifest_values[field] = tuple(reversed(manifest_values[field]))
    manifest_values["stages"][5]["bound_upstream_result_digests"] = tuple(
        reversed(manifest_values["stages"][5]["bound_upstream_result_digests"])
    )
    reordered_manifest = IdentificationQcReproducibilityManifest.model_validate(
        manifest_values, strict=True
    )
    assert manifest_digest(reordered_manifest) == manifest_digest(manifest)


def test_result_digest_ignores_every_semantically_unordered_collection() -> None:
    result = _released_result()
    values = result.model_dump(mode="python")
    for field in ("artifacts", "software_versions", "reference_versions"):
        values["manifest"][field] = tuple(reversed(values["manifest"][field]))
    values["manifest"]["stages"][5]["bound_upstream_result_digests"] = tuple(
        reversed(values["manifest"]["stages"][5]["bound_upstream_result_digests"])
    )
    values["policy"]["allowed_signature_algorithms"] = tuple(
        reversed(values["policy"]["allowed_signature_algorithms"])
    )
    values["policy"]["allowed_verifier_ids"] = tuple(
        reversed(values["policy"]["allowed_verifier_ids"])
    )
    values["package_descriptor"]["members"] = tuple(
        reversed(values["package_descriptor"]["members"])
    )
    values["provenance"]["input_digests"] = tuple(
        reversed(values["provenance"]["input_digests"])
    )
    values["provenance"]["control_decisions"] = tuple(
        reversed(values["provenance"]["control_decisions"])
    )
    values["evidence"] = tuple(reversed(values["evidence"]))
    values["limitations"] = tuple(reversed(values["limitations"]))

    reordered = IdentificationQcReleaseResult.model_validate(values, strict=True)

    assert reordered.result_digest == result.result_digest


def test_signature_statement_is_domain_bound_to_every_release_identity() -> None:
    manifest = _manifest()
    release_policy = _policy()
    baseline = _statement_digest(manifest, release_policy)

    assert signing_statement_digest(
        active_manifest_digest=manifest_digest(manifest),
        active_policy_digest=policy_digest(release_policy),
        release_id="release.identification-qc.other",
        release_version=manifest.release_version,
        subject_binding_digest=manifest.subject_binding_digest,
        intended_use_evidence_digest=manifest.intended_use_evidence_digest,
    ) != baseline
    assert signing_statement_digest(
        active_manifest_digest=manifest_digest(manifest),
        active_policy_digest=policy_digest(release_policy),
        release_id=manifest.release_id,
        release_version=manifest.release_version,
        subject_binding_digest=_FORGED_DIGEST,
        intended_use_evidence_digest=manifest.intended_use_evidence_digest,
    ) != baseline


def test_maximum_declared_request_shape_is_valid_and_below_ingress_cap() -> None:
    algorithms = tuple(
        f"algorithm.m0208.{index:02d}" for index in range(_MAX_ALLOWLIST_ENTRIES)
    )
    verifier_ids = tuple(
        f"verifier.m0208.{index:02d}" for index in range(_MAX_ALLOWLIST_ENTRIES)
    )
    release_policy = _policy(
        algorithms=algorithms,
        verifier_ids=verifier_ids,
    )
    context = _context(release_policy)
    artifacts = _caller_artifacts(
        declared_sizes=((M0208_MAX_TOTAL_ARTIFACT_BYTES // 8,) * 8)
    )
    reproduction = _reproduction_evidence()
    signature = _signature(_digest("max-shape-statement"), algorithm=algorithms[0])
    request = BuildIdentificationQcReleaseRequest(
        context=context,
        release_id="release.identification-qc.maximum-shape",
        release_version="1.0.0",
        artifacts=artifacts,
        software_versions=_software_versions(_MAX_METADATA_RECORDS),
        reference_versions=_reference_versions(_MAX_METADATA_RECORDS),
        reproduction_evidence=reproduction,
        policy=release_policy,
        signature=signature,
    )

    assert len(request.artifacts) == M0208_CALLER_ARTIFACT_COUNT
    assert sum(item.declared_size for item in request.artifacts) == (
        M0208_MAX_TOTAL_ARTIFACT_BYTES
    )
    assert len(request.software_versions) == _MAX_METADATA_RECORDS
    assert len(request.reference_versions) == _MAX_METADATA_RECORDS
    assert len(request.policy.allowed_signature_algorithms) == _MAX_ALLOWLIST_ENTRIES
    assert len(request.policy.allowed_verifier_ids) == _MAX_ALLOWLIST_ENTRIES
    assert len(canonical_json_bytes(request)) < M0208_MAX_CANONICAL_REQUEST_BYTES
