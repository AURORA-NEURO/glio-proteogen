"""Negative and canonicalization tests for the provisional M05-08 ABI."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m05_08 import (
    BuildPtmLocalizationReleaseRequest,
    PtmLocalizationReleaseArtifact,
    PtmLocalizationReleaseArtifactRole,
    PtmLocalizationReleaseManifest,
    PtmLocalizationReleasePolicy,
    PtmLocalizationReleaseQualityDecision,
    PtmLocalizationReleaseSignature,
    PtmLocalizationReleaseTransformation,
    manifest_digest,
    normalized_manifest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)


def _reference(label: str, nibble: str = "a") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"evidence.m0508.harden.{label}",
        version="1.0.0",
        digest=f"sha256:{nibble * 64}",
        media_type="application/json",
    )


def _decision(label: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m0508.harden.{label}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_reference(label),
    )


def _manifest(*, artifact_digest: str = "sha256:" + "1" * 64) -> PtmLocalizationReleaseManifest:
    quality = PtmLocalizationReleaseQualityDecision(
        decision_id="decision.m0508.harden.quality",
        status="accepted",
        evidence=_reference("quality-decision", "b"),
        rationale="fixture quality decision",
    )
    return PtmLocalizationReleaseManifest(
        manifest_id="manifest.m0508.harden",
        release_id="release.m0508.harden",
        release_version="1.0.0",
        artifact_digests=(artifact_digest,),
        stage_result_digests=("sha256:" + "2" * 64,),
        software_versions=("1.0.0",),
        reference_versions=("1.0.0",),
        quality_decision_ids=(quality.decision_id,),
        quality_decisions=(quality,),
        support_status=SupportStatus.SUPPORTED,
        reproducibility_evidence=(_reference("reproduction", "c"),),
    )


def _request() -> BuildPtmLocalizationReleaseRequest:
    artifact = PtmLocalizationReleaseArtifact(
        path="parent/variant-peptide.json",
        role=PtmLocalizationReleaseArtifactRole.PARENT_VARIANT_PEPTIDE_HANDOFF,
        reference=_reference("parent", "1"),
        declared_size=1,
    )
    manifest = _manifest(artifact_digest=artifact.reference.digest)
    context = ExecutionContext(
        request_id="request.m0508.harden",
        actor_id="actor.m0508.harden",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m0508.harden.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "3" * 64,
                evidence=_reference("identity", "4"),
            ),
            provenance=_decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.m0508.harden.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_reference("consent", "5"),
            ),
            quality=_decision("quality"),
            support=_decision("support"),
            intended_use=_decision("intended-use"),
        ),
    )
    policy = PtmLocalizationReleasePolicy(
        policy_id="policy.m0508.harden",
        policy_version="1.0.0",
        allowed_signature_algorithms=("ed25519",),
        allowed_verifier_ids=("verifier.m0508.harden",),
        evidence=_reference("policy", "6"),
    )
    signature = PtmLocalizationReleaseSignature(
        algorithm="ed25519",
        key_id="key.m0508.harden",
        signature_value="fixture-signature",
        claimed_manifest_digest=manifest_digest(manifest),
        evidence=_reference("signature", "7"),
    )
    return BuildPtmLocalizationReleaseRequest(
        context=context,
        artifacts=(artifact,),
        manifest=manifest,
        policy=policy,
        signature=signature,
        upstream_result_digests=manifest.stage_result_digests,
    )


def _rebuild(model: object, **updates: object) -> object:
    payload = model.model_dump(mode="python")  # type: ignore[union-attr]
    payload.update(updates)
    return type(model).model_validate(payload, strict=True)  # type: ignore[attr-defined]


def test_manifest_digest_is_order_independent() -> None:
    manifest = _manifest()
    swapped = _rebuild(
        manifest,
        reproducibility_evidence=(
            _reference("second", "d"),
            manifest.reproducibility_evidence[0],
        ),
    )
    assert normalized_manifest(manifest)["reproducibility_evidence"] != normalized_manifest(
        swapped
    )["reproducibility_evidence"]


def test_manifest_rejects_duplicate_artifact_digests() -> None:
    with pytest.raises(ValidationError, match="manifest entries must be unique"):
        _rebuild(_manifest(), artifact_digests=("sha256:" + "1" * 64,) * 2)


def test_manifest_rejects_duplicate_stage_digests() -> None:
    with pytest.raises(ValidationError, match="manifest entries must be unique"):
        _rebuild(_manifest(), stage_result_digests=("sha256:" + "2" * 64,) * 2)


def test_manifest_rejects_quality_id_mismatch() -> None:
    with pytest.raises(ValidationError, match="quality decision ids must match"):
        _rebuild(_manifest(), quality_decision_ids=("other-quality",))


def test_manifest_rejects_missing_transformation_evidence() -> None:
    with pytest.raises(ValidationError, match="transformation digests must match"):
        _rebuild(_manifest(), transformation_digests=("sha256:" + "8" * 64,))


def test_transformation_rejects_duplicate_inputs() -> None:
    with pytest.raises(ValidationError, match="input digests must be unique"):
        PtmLocalizationReleaseTransformation(
            transformation_id="transform.m0508.duplicate",
            name="normalization",
            version="1.0.0",
            digest="sha256:" + "9" * 64,
            input_digests=("sha256:" + "a" * 64,) * 2,
            output_digests=("sha256:" + "b" * 64,),
        )


def test_transformation_rejects_identity_output() -> None:
    with pytest.raises(ValidationError, match="emit an input digest unchanged"):
        PtmLocalizationReleaseTransformation(
            transformation_id="transform.m0508.identity",
            name="identity",
            version="1.0.0",
            digest="sha256:" + "9" * 64,
            input_digests=("sha256:" + "a" * 64,),
            output_digests=("sha256:" + "a" * 64,),
        )


def test_policy_rejects_duplicate_algorithms() -> None:
    with pytest.raises(ValidationError, match="signature algorithms must be unique"):
        PtmLocalizationReleasePolicy(
            policy_id="policy.m0508.duplicate",
            policy_version="1.0.0",
            allowed_signature_algorithms=("ed25519", "ed25519"),
            allowed_verifier_ids=("verifier.m0508",),
            evidence=_reference("policy", "6"),
        )


def test_policy_rejects_duplicate_verifiers() -> None:
    with pytest.raises(ValidationError, match="verifier ids must be unique"):
        PtmLocalizationReleasePolicy(
            policy_id="policy.m0508.duplicate-verifier",
            policy_version="1.0.0",
            allowed_signature_algorithms=("ed25519",),
            allowed_verifier_ids=("verifier.m0508", "verifier.m0508"),
            evidence=_reference("policy", "6"),
        )


def test_request_rejects_artifact_manifest_mismatch() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="artifact digests must match"):
        _rebuild(request, manifest=_manifest(artifact_digest="sha256:" + "f" * 64))


def test_request_rejects_duplicate_paths() -> None:
    request = _request()
    duplicate = _rebuild(request.artifacts[0], role=PtmLocalizationReleaseArtifactRole.STAGE_RESULT)
    with pytest.raises(ValidationError, match="artifact paths must be unique"):
        _rebuild(request, artifacts=(request.artifacts[0], duplicate))


def test_request_rejects_signature_algorithm_outside_policy() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="algorithm is not allowed"):
        _rebuild(request, signature=_rebuild(request.signature, algorithm="rsa"))


def test_request_rejects_manifest_signature_digest_mismatch() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="signature manifest digest"):
        _rebuild(
            request,
            signature=_rebuild(
                request.signature,
                claimed_manifest_digest="sha256:" + "f" * 64,
            ),
        )


def test_request_rejects_upstream_manifest_mismatch() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="upstream result digests"):
        _rebuild(request, upstream_result_digests=("sha256:" + "f" * 64,))


def test_artifact_path_rejects_absolute_and_parent_paths() -> None:
    for path in ("/absolute/x", "../x", "safe/../x", "C:/x", "safe\\x"):
        with pytest.raises(ValidationError, match="relative POSIX"):
            PtmLocalizationReleaseArtifact(
                path=path,
                role=PtmLocalizationReleaseArtifactRole.STAGE_RESULT,
                reference=_reference("path", "8"),
                declared_size=1,
            )


def test_quality_rejects_blank_rationale() -> None:
    with pytest.raises(ValidationError):
        PtmLocalizationReleaseQualityDecision(
            decision_id="decision.m0508.blank",
            status="accepted",
            evidence=_reference("quality", "b"),
            rationale=" ",
        )
