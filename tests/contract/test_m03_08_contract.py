"""Strict relational contracts for M03-08 release packaging."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from glio_proteogen.contracts.m03_08 import (
    M0308_ARCHIVE_MEMBER_COUNT,
    M0308_CALLER_ARTIFACT_COUNT,
    M0308_CONTRACT_VERSION,
    M0308_MANIFEST_PATH,
    M0308_MAX_ARTIFACT_BYTES,
    M0308_MAX_CANONICAL_REQUEST_BYTES,
    M0308_MAX_EVIDENCE,
    M0308_MAX_PACKAGE_BYTES,
    M0308_MAX_QUARANTINE_REASONS,
    M0308_MAX_REFERENCE_VERSIONS,
    M0308_MAX_SIGNATURE_ALGORITHMS,
    M0308_MAX_SIGNATURE_VALUE_CHARS,
    M0308_MAX_SOFTWARE_VERSIONS,
    M0308_MAX_STAGE_UPSTREAM_DIGESTS,
    M0308_MAX_TOTAL_ARTIFACT_BYTES,
    M0308_MAX_VERIFIER_IDS,
    M0308_MODULE_ID,
    M0308_OPERATION,
    M0308_PARENT,
    M0308_STAGE_COUNT,
    BuildProteinInferenceReleaseRequest,
    ExternalProteinInferenceSignature,
    ProteinInferencePackageVerificationReason,
    ProteinInferenceParentComplexActivityReceipt,
    ProteinInferenceReferenceVersion,
    ProteinInferenceReleaseArtifact,
    ProteinInferenceReleaseArtifactRole,
    ProteinInferenceReleaseContractName,
    ProteinInferenceReleaseMember,
    ProteinInferenceReleasePolicy,
    ProteinInferenceReleaseQuarantine,
    ProteinInferenceReleaseQuarantineCode,
    ProteinInferenceReleaseVerification,
    ProteinInferenceReproducibilityManifest,
    ProteinInferenceReproductionEvidence,
    ProteinInferenceSignatureAlgorithm,
    ProteinInferenceSignatureVerification,
    ProteinInferenceSignatureVerificationReason,
    ProteinInferenceSoftwareVersion,
    ProteinInferenceStageModuleId,
    ProteinInferenceStageProvenance,
    contract_json_schema,
    contract_json_schemas,
    manifest_digest,
    normalized_manifest,
    normalized_request,
    opaque_release_identifier,
    policy_digest,
    release_evidence_index,
    reproduction_evidence_digest,
    result_payload_digest,
    signing_statement_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    Sha256Digest,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)

pytestmark = pytest.mark.contract

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
ZERO_DIGEST = "sha256:" + ("0" * 64)
FORGED_DIGEST = "sha256:" + ("f" * 64)
EXPECTED_BASE_EVIDENCE_COUNT = 28

ROLE_PATHS = {
    ProteinInferenceReleaseArtifactRole.PARENT_COMPLEX_ACTIVITY_HANDOFF: (
        "parent/complex-activity-handoff.json"
    ),
    ProteinInferenceReleaseArtifactRole.M03_01_PROTOCOL_CONFORMANCE: (
        "stages/m03-01-protocol-conformance.json"
    ),
    ProteinInferenceReleaseArtifactRole.M03_02_IDENTITY_LINEAGE: (
        "stages/m03-02-identity-lineage.json"
    ),
    ProteinInferenceReleaseArtifactRole.M03_03_RAW_INGESTION: ("stages/m03-03-raw-ingestion.json"),
    ProteinInferenceReleaseArtifactRole.M03_04_QUALITY: "stages/m03-04-quality.json",
    ProteinInferenceReleaseArtifactRole.M03_05_ARTIFACT_DETECTION: (
        "stages/m03-05-artifact-detection.json"
    ),
    ProteinInferenceReleaseArtifactRole.M03_06_HARMONIZATION: ("stages/m03-06-harmonization.json"),
    ProteinInferenceReleaseArtifactRole.M03_07_SUPPORT_ROUTE: ("stages/m03-07-support-route.json"),
}
ROLE_MEDIA_TYPES = {
    ProteinInferenceReleaseArtifactRole.PARENT_COMPLEX_ACTIVITY_HANDOFF: (
        "application/vnd.glio-proteogen.complex-activity-handoff+json"
    ),
    **{
        role: f"application/vnd.glio-proteogen.m03-0{index}+json"
        for index, role in enumerate(tuple(ProteinInferenceReleaseArtifactRole)[1:], 1)
    },
}
STAGE_MODULES = tuple(ProteinInferenceStageModuleId)
STAGE_DISPOSITIONS = (
    "conformant",
    "reconciled",
    "validated",
    "qualified",
    "cleared",
    "accepted",
    "supported",
)
STAGE_DEPENDENCIES = ((), (0,), (0, 1), (0, 1, 2), (3,), (3, 4), (3, 5))


def digest(label: str) -> Sha256Digest:
    return sha256_digest({"m0308": label})


def opaque(namespace: str, label: str) -> str:
    return f"{namespace}.{digest(label).removeprefix('sha256:')}"


def evidence(label: str, *, value_digest: Sha256Digest | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=opaque("evidence", label),
        version="1.0.0",
        digest=value_digest or digest(f"evidence:{label}"),
        media_type="application/json",
    )


def build_policy(
    *,
    verifier_count: int = 2,
    max_total_bytes: int = M0308_MAX_TOTAL_ARTIFACT_BYTES,
    max_artifact_bytes: int = M0308_MAX_ARTIFACT_BYTES,
) -> ProteinInferenceReleasePolicy:
    return ProteinInferenceReleasePolicy(
        policy_id=opaque("policy", "release-policy"),
        version="1.0.0",
        max_total_bytes=max_total_bytes,
        max_artifact_bytes=max_artifact_bytes,
        allowed_signature_algorithms=(
            ProteinInferenceSignatureAlgorithm.ED25519,
            ProteinInferenceSignatureAlgorithm.ECDSA_P256_SHA256,
        ),
        allowed_verifier_ids=tuple(
            opaque("verifier", f"verifier:{index}") for index in range(verifier_count)
        ),
        evidence=evidence("release-policy"),
        reviewed_by=opaque("reviewer", "release-reviewer"),
        reviewed_at=NOW - timedelta(days=1),
    )


def build_context(policy: ProteinInferenceReleasePolicy) -> ExecutionContext:
    def upstream(role: str, *, value_digest: Sha256Digest | None = None) -> ArtifactReference:
        return evidence(f"control:{role}", value_digest=value_digest)

    return ExecutionContext(
        request_id=opaque("request", "release-request"),
        actor_id=opaque("actor", "release-packager"),
        occurred_at=NOW,
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id=opaque("decision", "configuration"),
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=upstream("configuration", value_digest=policy_digest(policy)),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id=opaque("decision", "identity"),
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=digest("identity-resolution"),
                evidence=upstream("identity"),
            ),
            provenance=UpstreamDecisionReference(
                decision_id=opaque("decision", "provenance"),
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=upstream("provenance"),
            ),
            consent=ConsentReference(
                decision_id=opaque("decision", "consent"),
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=upstream("consent"),
            ),
            quality=UpstreamDecisionReference(
                decision_id=opaque("decision", "quality"),
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=upstream("quality"),
            ),
            support=UpstreamDecisionReference(
                decision_id=opaque("decision", "support"),
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=upstream("support"),
            ),
            intended_use=UpstreamDecisionReference(
                decision_id=opaque("decision", "intended-use"),
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=upstream("intended_use"),
            ),
        ),
    )


def build_artifacts(
    *, declared_sizes: tuple[int, ...] | None = None
) -> tuple[ProteinInferenceReleaseArtifact, ...]:
    sizes = declared_sizes or ((128,) * M0308_CALLER_ARTIFACT_COUNT)
    stage_request_digests = tuple(digest(f"stage-request:{index}") for index in range(7))
    artifacts: list[ProteinInferenceReleaseArtifact] = []
    for index, role in enumerate(ProteinInferenceReleaseArtifactRole):
        if index == 0:
            artifact_id = opaque("parent", "complex-activity-handoff")
        else:
            suffix = stage_request_digests[index - 1].removeprefix("sha256:")
            artifact_id = (
                f"route.{suffix}" if index == M0308_STAGE_COUNT else f"result.m030{index}.{suffix}"
            )
        artifacts.append(
            ProteinInferenceReleaseArtifact(
                path=ROLE_PATHS[role],
                role=role,
                reference=ArtifactReference(
                    artifact_id=artifact_id,
                    version="1.0.0",
                    digest=digest(f"artifact-bytes:{index}"),
                    media_type=ROLE_MEDIA_TYPES[role],
                ),
                declared_size=sizes[index],
            )
        )
    return tuple(sorted(artifacts, key=canonical_json_bytes))


def build_software(count: int = 2) -> tuple[ProteinInferenceSoftwareVersion, ...]:
    return tuple(
        sorted(
            (
                ProteinInferenceSoftwareVersion(
                    software_id=opaque("software", f"software:{index}"),
                    version=f"1.0.{index}",
                    build_digest=digest(f"software-build:{index}"),
                    evidence=evidence(f"software:{index}"),
                )
                for index in range(count)
            ),
            key=canonical_json_bytes,
        )
    )


def build_references(count: int = 2) -> tuple[ProteinInferenceReferenceVersion, ...]:
    return tuple(
        sorted(
            (
                ProteinInferenceReferenceVersion(
                    reference_id=opaque("reference", f"reference:{index}"),
                    build_id=opaque("build", f"reference-build:{index}"),
                    version=f"release-{index}",
                    digest=digest(f"reference-digest:{index}"),
                    evidence=evidence(f"reference:{index}"),
                )
                for index in range(count)
            ),
            key=canonical_json_bytes,
        )
    )


def build_reproduction_evidence() -> ProteinInferenceReproductionEvidence:
    return ProteinInferenceReproductionEvidence(
        environment_lock=evidence("reproduction:environment-lock"),
        build_recipe=evidence("reproduction:build-recipe"),
        locked_tests=evidence("reproduction:locked-tests"),
        benchmark=evidence("reproduction:benchmark"),
        traceability=evidence("reproduction:traceability"),
        reviewer_signoff=evidence("reproduction:reviewer-signoff"),
        rollback=evidence("reproduction:rollback"),
    )


def build_stages(
    artifacts: tuple[ProteinInferenceReleaseArtifact, ...],
    *,
    updates: dict[int, dict[str, object]] | None = None,
) -> tuple[ProteinInferenceStageProvenance, ...]:
    by_role = {item.role: item for item in artifacts}
    stage_artifacts = tuple(
        by_role[role] for role in tuple(ProteinInferenceReleaseArtifactRole)[1:]
    )
    result_digests = tuple(digest(f"stage-result:{index}") for index in range(7))
    values = []
    for index, module in enumerate(STAGE_MODULES):
        payload: dict[str, object] = {
            "module_id": module,
            "module_version": M0308_CONTRACT_VERSION,
            "result_digest": result_digests[index],
            "request_digest": digest(f"stage-request:{index}"),
            "byte_digest": stage_artifacts[index].reference.digest,
            "disposition": STAGE_DISPOSITIONS[index],
            "generated_at": NOW - timedelta(minutes=8 - index),
            "configuration_digest": digest(f"stage-configuration:{index}"),
            "identity_resolution_digest": digest("identity-resolution"),
            "bound_upstream_result_digests": tuple(
                result_digests[item] for item in STAGE_DEPENDENCIES[index]
            ),
            "human_review_required": False,
        }
        if updates and index in updates:
            payload.update(updates[index])
        values.append(ProteinInferenceStageProvenance.model_validate(payload, strict=True))
    return tuple(values)


def build_manifest(  # noqa: PLR0913 - explicit independently variable manifest axes.
    policy: ProteinInferenceReleasePolicy,
    context: ExecutionContext,
    *,
    artifacts: tuple[ProteinInferenceReleaseArtifact, ...] | None = None,
    software: tuple[ProteinInferenceSoftwareVersion, ...] | None = None,
    references: tuple[ProteinInferenceReferenceVersion, ...] | None = None,
    stage_updates: dict[int, dict[str, object]] | None = None,
) -> ProteinInferenceReproducibilityManifest:
    caller_artifacts = artifacts or build_artifacts()
    reproduction = build_reproduction_evidence()
    stages = build_stages(caller_artifacts, updates=stage_updates)
    return ProteinInferenceReproducibilityManifest(
        release_id=opaque("release", "canonical-release"),
        release_version="1.0.0",
        artifacts=caller_artifacts,
        stages=stages,
        software_versions=software or build_software(),
        reference_versions=references or build_references(),
        reproduction_evidence=reproduction,
        reproduction_evidence_digest=reproduction_evidence_digest(reproduction),
        m0306_transformation_manifest_digest=digest("m0306-transformation-manifest"),
        m0306_analysis_digest=digest("m0306-analysis"),
        m0304_quality_disposition=stages[3].disposition,
        m0305_artifact_disposition=stages[4].disposition,
        m0306_harmonization_disposition=stages[5].disposition,
        m0307_support_disposition=stages[6].disposition,
        identity_resolution_digest=context.references.identity_lineage.binding_digest,
        intended_use_evidence_digest=context.references.intended_use.evidence.digest,
        support_route_result_digest=stages[6].result_digest,
        policy_digest=policy_digest(policy),
    )


def statement_digest(
    manifest: ProteinInferenceReproducibilityManifest,
    policy: ProteinInferenceReleasePolicy,
) -> Sha256Digest:
    return signing_statement_digest(
        active_manifest_digest=manifest_digest(manifest),
        active_policy_digest=policy_digest(policy),
        release_id=manifest.release_id,
        release_version=manifest.release_version,
        identity_resolution_digest=manifest.identity_resolution_digest,
        intended_use_evidence_digest=manifest.intended_use_evidence_digest,
        support_route_result_digest=manifest.support_route_result_digest,
    )


def build_signature(
    claimed_statement_digest: Sha256Digest,
) -> ExternalProteinInferenceSignature:
    return ExternalProteinInferenceSignature(
        signer_id=opaque("signer", "external-signer"),
        key_id=opaque("key", "external-key"),
        algorithm=ProteinInferenceSignatureAlgorithm.ED25519,
        claimed_statement_digest=claimed_statement_digest,
        signature_value="c3ludGhldGljLXNpZ25hdHVyZQ==",
        issued_at=NOW - timedelta(minutes=1),
        evidence=evidence("external-signature"),
    )


def build_request(
    manifest: ProteinInferenceReproducibilityManifest,
    policy: ProteinInferenceReleasePolicy,
    context: ExecutionContext,
    signature: ExternalProteinInferenceSignature,
) -> BuildProteinInferenceReleaseRequest:
    return BuildProteinInferenceReleaseRequest(
        context=context,
        release_id=manifest.release_id,
        release_version=manifest.release_version,
        artifacts=manifest.artifacts,
        software_versions=manifest.software_versions,
        reference_versions=manifest.reference_versions,
        reproduction_evidence=manifest.reproduction_evidence,
        policy=policy,
        signature=signature,
    )


@dataclass(frozen=True, slots=True)
class ContractFixture:
    policy: ProteinInferenceReleasePolicy
    context: ExecutionContext
    manifest: ProteinInferenceReproducibilityManifest
    signature: ExternalProteinInferenceSignature
    request: BuildProteinInferenceReleaseRequest


def build_contract_fixture(
    *,
    software_count: int = 2,
    reference_count: int = 2,
    verifier_count: int = 2,
) -> ContractFixture:
    policy = build_policy(verifier_count=verifier_count)
    context = build_context(policy)
    manifest = build_manifest(
        policy,
        context,
        software=build_software(software_count),
        references=build_references(reference_count),
    )
    signature = build_signature(statement_digest(manifest, policy))
    request = build_request(manifest, policy, context, signature)
    return ContractFixture(policy, context, manifest, signature, request)


def build_signature_verification(
    fixture: ContractFixture,
    reason: ProteinInferenceSignatureVerificationReason = (
        ProteinInferenceSignatureVerificationReason.VERIFIED
    ),
) -> ProteinInferenceSignatureVerification:
    verifier_id = (
        fixture.policy.allowed_verifier_ids[0]
        if reason
        in {
            ProteinInferenceSignatureVerificationReason.VERIFIED,
            ProteinInferenceSignatureVerificationReason.VERIFIER_REJECTED,
        }
        else None
    )
    return ProteinInferenceSignatureVerification(
        verifier_id=verifier_id,
        algorithm=fixture.signature.algorithm,
        key_id=fixture.signature.key_id,
        statement_digest=statement_digest(fixture.manifest, fixture.policy),
        verified=reason is ProteinInferenceSignatureVerificationReason.VERIFIED,
        reason_code=reason,
    )


@pytest.mark.parametrize(
    "name",
    ["request", "output", "policy", "artifact", "manifest", "verification", "signature"],
)
def test_all_seven_schemas_are_standalone_strict_and_bounded(
    name: ProteinInferenceReleaseContractName,
) -> None:
    schema = contract_json_schema(name)
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == (f"urn:aurora-neuro:glio-proteogen:{M0308_MODULE_ID}:1.0.0:{name}")
    assert schema["additionalProperties"] is False
    metadata = cast("dict[str, object]", schema["x-glio-contract"])
    assert metadata["strict"] is True
    assert metadata["maxPackageBytes"] == M0308_MAX_PACKAGE_BYTES
    assert metadata["signsRelease"] is False
    assert metadata["authenticatesSigner"] is False
    assert metadata["establishesReleaseAuthority"] is False
    if name == "request":
        assert metadata["maxRequestBytes"] == M0308_MAX_CANONICAL_REQUEST_BYTES


def test_public_abi_constants_enums_and_schema_inventory_are_exact() -> None:
    assert (M0308_MODULE_ID, M0308_OPERATION, M0308_CONTRACT_VERSION, M0308_PARENT) == (
        "GLIO-PROTEOGEN-M03-08",
        "package_protein_inference_release",
        "1.0.0",
        "complex_activity",
    )
    assert (
        M0308_CALLER_ARTIFACT_COUNT,
        M0308_STAGE_COUNT,
        M0308_ARCHIVE_MEMBER_COUNT,
        M0308_MAX_ARTIFACT_BYTES,
        M0308_MAX_TOTAL_ARTIFACT_BYTES,
        M0308_MAX_PACKAGE_BYTES,
        M0308_MAX_SOFTWARE_VERSIONS,
        M0308_MAX_REFERENCE_VERSIONS,
        M0308_MAX_SIGNATURE_ALGORITHMS,
        M0308_MAX_VERIFIER_IDS,
        M0308_MAX_SIGNATURE_VALUE_CHARS,
        M0308_MAX_STAGE_UPSTREAM_DIGESTS,
        M0308_MAX_QUARANTINE_REASONS,
        M0308_MAX_EVIDENCE,
    ) == (8, 7, 10, 32 << 20, 64 << 20, 72 << 20, 64, 64, 16, 16, 16_384, 3, 8, 152)
    assert tuple(contract_json_schemas()) == (
        "request",
        "output",
        "policy",
        "artifact",
        "manifest",
        "verification",
        "signature",
    )
    assert len(ProteinInferenceReleaseArtifactRole) == M0308_CALLER_ARTIFACT_COUNT
    assert len(ProteinInferenceStageModuleId) == M0308_STAGE_COUNT
    assert {item.value for item in ProteinInferenceSignatureAlgorithm} == {
        "ed25519",
        "ecdsa_p256_sha256",
        "rsa_pss_sha256",
    }


def test_canonical_request_and_manifest_construct_with_exact_evidence_closure() -> None:
    fixture = build_contract_fixture()
    assert len(fixture.request.artifacts) == M0308_CALLER_ARTIFACT_COUNT
    assert len(fixture.manifest.stages) == M0308_STAGE_COUNT
    assert len(release_evidence_index(fixture.request)) == EXPECTED_BASE_EVIDENCE_COUNT
    assert len(canonical_json_bytes(normalized_request(fixture.request))) < (
        M0308_MAX_CANONICAL_REQUEST_BYTES
    )
    assert manifest_digest(fixture.manifest) == manifest_digest(
        normalized_manifest(fixture.manifest)
    )


def test_parent_receipt_is_non_inferential_and_binds_route() -> None:
    fixture = build_contract_fixture()
    receipt = ProteinInferenceParentComplexActivityReceipt(
        identity_resolution_digest=fixture.manifest.identity_resolution_digest,
        intended_use_evidence_digest=fixture.manifest.intended_use_evidence_digest,
        support_route_result_digest=fixture.manifest.support_route_result_digest,
    )
    assert receipt.parent_target == "complex_activity"
    assert receipt.emits_complex_activity is False


def test_opaque_identifier_helper_and_owned_identifier_validation() -> None:
    value = {"release": 1}
    assert opaque_release_identifier("release", value) == (
        f"release.{sha256_digest(value).removeprefix('sha256:')}"
    )
    payload = build_policy().model_dump(mode="python")
    payload["reviewed_by"] = "MPEPTIDEK"
    with pytest.raises(ValidationError, match="opaque reviewer"):
        ProteinInferenceReleasePolicy.model_validate(payload, strict=True)


def test_signature_verification_state_reason_and_verifier_are_closed() -> None:
    fixture = build_contract_fixture()
    payload = build_signature_verification(fixture).model_dump(mode="python")
    payload["verified"] = False
    with pytest.raises(ValidationError, match="verified state contradicts"):
        ProteinInferenceSignatureVerification.model_validate(payload, strict=True)
    payload = build_signature_verification(fixture).model_dump(mode="python")
    payload["verifier_id"] = None
    with pytest.raises(ValidationError, match="verifier identifier"):
        ProteinInferenceSignatureVerification.model_validate(payload, strict=True)


def test_content_failure_short_circuits_authenticity_and_receipts() -> None:
    fixture = build_contract_fixture()
    verified_signature = build_signature_verification(fixture)
    complete = {
        "content_verified": False,
        "authenticity_verified": True,
        "verified": False,
        "package_digest": digest("package"),
        "manifest_digest": manifest_digest(fixture.manifest),
        "member_count": M0308_ARCHIVE_MEMBER_COUNT,
        "signature_verification": verified_signature,
        "reason_code": ProteinInferencePackageVerificationReason.CONTENT_MISMATCH,
    }
    with pytest.raises(ValidationError, match="short-circuit authenticity"):
        ProteinInferenceReleaseVerification.model_validate(complete, strict=True)

    not_attempted = build_signature_verification(
        fixture, ProteinInferenceSignatureVerificationReason.NOT_ATTEMPTED
    )
    failure = ProteinInferenceReleaseVerification(
        content_verified=False,
        authenticity_verified=False,
        verified=False,
        member_count=0,
        signature_verification=not_attempted,
        reason_code=ProteinInferencePackageVerificationReason.CONTENT_MISMATCH,
    )
    assert failure.package_digest is failure.manifest_digest is None


def test_content_success_authenticity_failure_retains_complete_content_receipts() -> None:
    fixture = build_contract_fixture()
    signature = build_signature_verification(
        fixture, ProteinInferenceSignatureVerificationReason.VERIFIER_UNAVAILABLE
    )
    verification = ProteinInferenceReleaseVerification(
        content_verified=True,
        authenticity_verified=False,
        verified=False,
        package_digest=digest("package"),
        manifest_digest=manifest_digest(fixture.manifest),
        member_count=M0308_ARCHIVE_MEMBER_COUNT,
        signature_verification=signature,
        reason_code=ProteinInferencePackageVerificationReason.VERIFIER_UNAVAILABLE,
    )
    assert verification.package_digest is not None
    payload = verification.model_dump(mode="python")
    payload["member_count"] = 0
    with pytest.raises(ValidationError, match="complete content receipts"):
        ProteinInferenceReleaseVerification.model_validate(payload, strict=True)


def test_unknown_fields_and_scalar_coercions_are_rejected_strictly() -> None:
    fixture = build_contract_fixture()
    payload = fixture.request.model_dump(mode="python")
    payload["future_field"] = True
    with pytest.raises(ValidationError, match="Extra inputs"):
        BuildProteinInferenceReleaseRequest.model_validate(payload, strict=True)
    artifact = fixture.request.artifacts[0].model_dump(mode="python")
    artifact["declared_size"] = "128"
    with pytest.raises(ValidationError, match="valid integer"):
        ProteinInferenceReleaseArtifact.model_validate(artifact, strict=True)


def test_zero_result_digest_cannot_be_a_valid_sentinel() -> None:
    assert (
        result_payload_digest(
            {
                "result_digest": ZERO_DIGEST,
                "policy": build_policy().model_dump(mode="python"),
                "manifest": build_contract_fixture().manifest.model_dump(mode="python"),
                "quarantine_reasons": [],
                "package_descriptor": None,
                "provenance": {"input_digests": [], "control_decisions": []},
                "evidence": [],
                "limitations": [],
            }
        )
        != ZERO_DIGEST
    )


def test_schema_emits_exact_collection_caps() -> None:
    output = cast("dict[str, Any]", contract_json_schema("output")["properties"])
    request = cast("dict[str, Any]", contract_json_schema("request")["properties"])
    policy = cast("dict[str, Any]", contract_json_schema("policy")["properties"])
    assert output["evidence"]["maxItems"] == M0308_MAX_EVIDENCE
    assert output["quarantine_reasons"]["maxItems"] == M0308_MAX_QUARANTINE_REASONS
    assert (
        request["artifacts"]["minItems"]
        == request["artifacts"]["maxItems"]
        == M0308_CALLER_ARTIFACT_COUNT
    )
    assert request["software_versions"]["maxItems"] == M0308_MAX_SOFTWARE_VERSIONS
    assert request["reference_versions"]["maxItems"] == M0308_MAX_REFERENCE_VERSIONS
    assert policy["allowed_signature_algorithms"]["maxItems"] == (M0308_MAX_SIGNATURE_ALGORITHMS)
    assert policy["allowed_verifier_ids"]["maxItems"] == M0308_MAX_VERIFIER_IDS


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("reserved_path", "reserved M03-08 namespace"),
        ("wrong_path", "fixed canonical path"),
        ("wrong_identifier", "reference contradicts"),
        ("wrong_media_type", "reference contradicts"),
        ("unsafe_path", "canonical safe relative POSIX"),
        ("long_prefix", "not representable in USTAR"),
    ],
)
def test_artifact_role_path_reference_and_ustar_matrix(
    mutation: str,
    message: str,
) -> None:
    values = build_artifacts()[0].model_dump(mode="python")
    if mutation == "reserved_path":
        values["path"] = "META-INF/glio-proteogen-m03-08/caller.json"
    elif mutation == "wrong_path":
        values["path"] = "stages/m03-01-protocol-conformance.json"
    elif mutation == "wrong_identifier":
        values["reference"]["artifact_id"] = "result.m0301." + ("f" * 64)
    elif mutation == "wrong_media_type":
        values["reference"]["media_type"] = "application/json"
    elif mutation == "unsafe_path":
        values["path"] = "../parent.json"
    else:
        values["path"] = f"{'p' * 156}/{'n' * 98}"
    with pytest.raises(ValidationError, match=message):
        ProteinInferenceReleaseArtifact.model_validate(values, strict=True)


def test_reproduction_evidence_and_policy_allowlists_reject_duplicates() -> None:
    reproduction = build_reproduction_evidence().model_dump(mode="python")
    reproduction["rollback"]["digest"] = reproduction["benchmark"]["digest"]
    with pytest.raises(ValidationError, match="digests must be unique"):
        ProteinInferenceReproductionEvidence.model_validate(reproduction, strict=True)

    policy = build_policy().model_dump(mode="python")
    policy["allowed_verifier_ids"] = (
        policy["allowed_verifier_ids"][0],
        policy["allowed_verifier_ids"][0],
    )
    with pytest.raises(ValidationError, match="allowlists must be unique"):
        ProteinInferenceReleasePolicy.model_validate(policy, strict=True)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("roles", "each caller artifact role exactly once"),
        ("artifact_cap", "active per-artifact limit"),
        ("total_cap", "active total limit"),
        ("algorithm", "algorithm is not allowed"),
        ("future_signature", "cannot be issued after"),
        ("late_review", "reviewed before"),
        ("configuration", "does not bind the release policy"),
        ("intended_alias", "cannot alias"),
        ("evidence_conflict", "conflicting metadata"),
    ],
)
def test_request_authorization_policy_and_binding_matrix(
    mutation: str,
    message: str,
) -> None:
    values = build_contract_fixture().request.model_dump(mode="python")
    if mutation == "roles":
        values["artifacts"] = (*values["artifacts"][:-1], values["artifacts"][0])
    elif mutation == "artifact_cap":
        values["policy"]["max_artifact_bytes"] = 127
        values["context"]["references"]["approved_configuration"]["evidence"]["digest"] = (
            policy_digest(values["policy"])
        )
    elif mutation == "total_cap":
        values["policy"]["max_total_bytes"] = 1023
        values["context"]["references"]["approved_configuration"]["evidence"]["digest"] = (
            policy_digest(values["policy"])
        )
    elif mutation == "algorithm":
        values["policy"]["allowed_signature_algorithms"] = (
            ProteinInferenceSignatureAlgorithm.RSA_PSS_SHA256,
        )
        values["context"]["references"]["approved_configuration"]["evidence"]["digest"] = (
            policy_digest(values["policy"])
        )
    elif mutation == "future_signature":
        values["signature"]["issued_at"] = NOW + timedelta(microseconds=1)
    elif mutation == "late_review":
        values["policy"]["reviewed_at"] = values["signature"]["issued_at"] + timedelta(
            microseconds=1
        )
        values["context"]["references"]["approved_configuration"]["evidence"]["digest"] = (
            policy_digest(values["policy"])
        )
    elif mutation == "configuration":
        values["context"]["references"]["approved_configuration"]["evidence"]["digest"] = (
            FORGED_DIGEST
        )
    elif mutation == "intended_alias":
        values["context"]["references"]["intended_use"]["evidence"]["digest"] = values["context"][
            "references"
        ]["identity_lineage"]["binding_digest"]
    else:
        software_evidence = values["software_versions"][0]["evidence"]
        values["reference_versions"][0]["evidence"]["artifact_id"] = software_evidence[
            "artifact_id"
        ]
        values["reference_versions"][0]["evidence"]["version"] = software_evidence["version"]
    with pytest.raises(ValidationError, match=message):
        BuildProteinInferenceReleaseRequest.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("role", "state", "message"),
    [
        ("consent", ConsentState.REVOKED, "consent does not authorize"),
        ("identity_lineage", IdentityLineageState.UNRESOLVED, "identity lineage"),
        ("quality", UpstreamDecisionState.REJECTED, "upstream controls"),
    ],
)
def test_request_requires_all_seven_authorizing_controls(
    role: str,
    state: object,
    message: str,
) -> None:
    values = build_contract_fixture().request.model_dump(mode="python")
    values["context"]["references"][role]["state"] = state
    with pytest.raises(ValidationError, match=message):
        BuildProteinInferenceReleaseRequest.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("version", "module version"),
        ("disposition", "disposition contradicts"),
        ("duplicate_upstream", "upstream result digests must be unique"),
    ],
)
def test_stage_vocabulary_and_upstream_digest_shape(
    mutation: str,
    message: str,
) -> None:
    values = build_contract_fixture().manifest.stages[3].model_dump(mode="python")
    if mutation == "version":
        values["module_version"] = "1.0.1"
    elif mutation == "disposition":
        values["disposition"] = "cleared"
    else:
        values["bound_upstream_result_digests"] = (
            values["bound_upstream_result_digests"][0],
            values["bound_upstream_result_digests"][0],
        )
    with pytest.raises(ValidationError, match=message):
        ProteinInferenceStageProvenance.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("roles", "every caller artifact role"),
        ("total_bytes", "public byte ceiling"),
        ("metadata_ids", "identifiers must be unique"),
        ("stage_order", "ordered M03-01 through M03-07"),
        ("chronology", "nondecreasing completion times"),
        ("reproduction_digest", "reproduction evidence digest"),
        ("stage_digest", "stage digests must be unique"),
        ("byte_digest", "stage byte digests"),
        ("artifact_identity", "artifact identity"),
        ("dependency", "exact direct upstream"),
        ("identity", "complete stage lineage"),
        ("support_digest", "support route digest"),
        ("quality_disposition", "quality disposition"),
        ("artifact_disposition", "artifact disposition"),
        ("harmonization_disposition", "harmonization disposition"),
        ("harmonization_digests", "M03-06 manifest digests"),
        ("support_disposition", "support disposition"),
    ],
)
def test_manifest_chain_forgery_matrix(  # noqa: C901, PLR0912
    mutation: str,
    message: str,
) -> None:
    values = build_contract_fixture().manifest.model_dump(mode="python")
    if mutation == "roles":
        values["artifacts"] = (*values["artifacts"][:-1], values["artifacts"][0])
    elif mutation == "total_bytes":
        for item in values["artifacts"]:
            item["declared_size"] = (
                M0308_MAX_TOTAL_ARTIFACT_BYTES // M0308_CALLER_ARTIFACT_COUNT
            ) + 1
    elif mutation == "metadata_ids":
        values["software_versions"] = (
            *values["software_versions"][:-1],
            values["software_versions"][0],
        )
    elif mutation == "stage_order":
        values["stages"] = tuple(reversed(values["stages"]))
    elif mutation == "chronology":
        values["stages"][1]["generated_at"] = values["stages"][0]["generated_at"] - timedelta(
            microseconds=1
        )
    elif mutation == "reproduction_digest":
        values["reproduction_evidence_digest"] = FORGED_DIGEST
    elif mutation == "stage_digest":
        values["stages"][1]["result_digest"] = values["stages"][0]["result_digest"]
    elif mutation == "byte_digest":
        values["stages"][0]["byte_digest"] = FORGED_DIGEST
    elif mutation == "artifact_identity":
        values["stages"][0]["request_digest"] = FORGED_DIGEST
    elif mutation == "dependency":
        values["stages"][3]["bound_upstream_result_digests"] = (
            FORGED_DIGEST,
            *values["stages"][3]["bound_upstream_result_digests"][:2],
        )
    elif mutation == "identity":
        values["stages"][0]["identity_resolution_digest"] = FORGED_DIGEST
    elif mutation == "support_digest":
        values["support_route_result_digest"] = FORGED_DIGEST
    elif mutation == "quality_disposition":
        values["m0304_quality_disposition"] = "quarantined"
    elif mutation == "artifact_disposition":
        values["m0305_artifact_disposition"] = "quarantined"
    elif mutation == "harmonization_disposition":
        values["m0306_harmonization_disposition"] = "quarantined"
    elif mutation == "harmonization_digests":
        values["m0306_analysis_digest"] = None
    else:
        values["m0307_support_disposition"] = "abstained"
    with pytest.raises(ValidationError, match=message):
        ProteinInferenceReproducibilityManifest.model_validate(values, strict=True)


@pytest.mark.parametrize("shape", ["safe-failure", "post-analysis"])
def test_nonaccepted_m0306_manifest_permits_both_paired_digest_shapes(
    shape: str,
) -> None:
    post_analysis = shape == "post-analysis"
    values = build_contract_fixture().manifest.model_dump(mode="python")
    values["stages"][5]["disposition"] = "quarantined"
    values["stages"][5]["human_review_required"] = True
    values["m0306_harmonization_disposition"] = "quarantined"
    if not post_analysis:
        values["m0306_transformation_manifest_digest"] = None
        values["m0306_analysis_digest"] = None
    manifest = ProteinInferenceReproducibilityManifest.model_validate(values, strict=True)
    assert (manifest.m0306_transformation_manifest_digest is not None) is post_analysis
    assert (manifest.m0306_analysis_digest is not None) is post_analysis


@pytest.mark.parametrize("missing", ["transformation", "analysis"])
def test_m0306_manifest_digests_must_always_be_paired(missing: str) -> None:
    values = build_contract_fixture().manifest.model_dump(mode="python")
    values[
        "m0306_transformation_manifest_digest"
        if missing == "transformation"
        else "m0306_analysis_digest"
    ] = None
    with pytest.raises(ValidationError, match="M03-06 manifest digests"):
        ProteinInferenceReproducibilityManifest.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("values", "message"),
    [
        (
            {
                "code": ProteinInferenceReleaseQuarantineCode.UPSTREAM_NOT_RELEASABLE,
                "stage_module_id": None,
                "reason_code": "stage_disposition_quarantined",
                "remediation_code": "review_upstream_stage",
            },
            "only upstream quarantine reasons",
        ),
        (
            {
                "code": ProteinInferenceReleaseQuarantineCode.UPSTREAM_NOT_RELEASABLE,
                "stage_module_id": ProteinInferenceStageModuleId.M03_04,
                "reason_code": "unknown",
                "remediation_code": "review_upstream_stage",
            },
            "upstream quarantine reason vocabulary",
        ),
        (
            {
                "code": ProteinInferenceReleaseQuarantineCode.SIGNATURE_UNVERIFIED,
                "stage_module_id": None,
                "reason_code": "unknown",
                "remediation_code": "provide_verified_signature",
            },
            "signature quarantine reason vocabulary",
        ),
    ],
)
def test_quarantine_vocabulary_is_closed(values: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        ProteinInferenceReleaseQuarantine.model_validate(values, strict=True)


@pytest.mark.parametrize("shape", ["generated_has_role", "caller_has_no_role", "wrong_role"])
def test_package_member_generated_and_caller_role_shapes(shape: str) -> None:
    artifact = build_artifacts()[0]
    values: dict[str, object] = {
        "path": artifact.path,
        "byte_size": artifact.declared_size,
        "digest": artifact.reference.digest,
        "role": artifact.role,
    }
    message = "distinct role shapes"
    if shape == "generated_has_role":
        values["path"] = M0308_MANIFEST_PATH
    elif shape == "caller_has_no_role":
        values["role"] = None
    else:
        values["role"] = ProteinInferenceReleaseArtifactRole.M03_01_PROTOCOL_CONFORMANCE
        message = "fixed canonical path"
    with pytest.raises(ValidationError, match=message):
        ProteinInferenceReleaseMember.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("authenticity", "authenticity contradicts"),
        ("components", "component checks"),
        ("reason", "reason code"),
        ("content_reason", "exact content reason"),
        ("auth_reason", "exact signature reason"),
        ("reason_disagreement", "reasons disagree"),
    ],
)
def test_package_verification_relational_failure_matrix(
    mutation: str,
    message: str,
) -> None:
    fixture = build_contract_fixture()
    signature = build_signature_verification(fixture)
    values: dict[str, object] = {
        "content_verified": True,
        "authenticity_verified": True,
        "verified": True,
        "package_digest": digest("package"),
        "manifest_digest": manifest_digest(fixture.manifest),
        "member_count": M0308_ARCHIVE_MEMBER_COUNT,
        "signature_verification": signature.model_dump(mode="python"),
        "reason_code": ProteinInferencePackageVerificationReason.VERIFIED,
    }
    if mutation == "authenticity":
        values["authenticity_verified"] = False
    elif mutation == "components":
        values["verified"] = False
    elif mutation == "reason":
        values["reason_code"] = ProteinInferencePackageVerificationReason.CONTENT_MISMATCH
    elif mutation == "content_reason":
        values.update(
            content_verified=False,
            authenticity_verified=False,
            verified=False,
            package_digest=None,
            manifest_digest=None,
            member_count=0,
            reason_code=ProteinInferencePackageVerificationReason.VERIFIER_UNAVAILABLE,
            signature_verification=build_signature_verification(
                fixture, ProteinInferenceSignatureVerificationReason.NOT_ATTEMPTED
            ).model_dump(mode="python"),
        )
    elif mutation == "auth_reason":
        values.update(
            authenticity_verified=False,
            verified=False,
            reason_code=ProteinInferencePackageVerificationReason.CONTENT_MISMATCH,
            signature_verification=build_signature_verification(
                fixture, ProteinInferenceSignatureVerificationReason.VERIFIER_UNAVAILABLE
            ).model_dump(mode="python"),
        )
    else:
        values.update(
            authenticity_verified=False,
            verified=False,
            reason_code=ProteinInferencePackageVerificationReason.VERIFIER_REJECTED,
            signature_verification=build_signature_verification(
                fixture, ProteinInferenceSignatureVerificationReason.VERIFIER_UNAVAILABLE
            ).model_dump(mode="python"),
        )
    with pytest.raises(ValidationError, match=message):
        ProteinInferenceReleaseVerification.model_validate(values, strict=True)
