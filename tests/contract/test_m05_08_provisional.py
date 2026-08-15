"""Minimal local smoke for the provisional M05-08 packaging seam."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m05_08 import (
    BuildPtmLocalizationReleaseRequest,
    PtmLocalizationReleaseArtifact,
    PtmLocalizationReleaseArtifactRole,
    PtmLocalizationReleaseManifest,
    PtmLocalizationReleasePolicy,
    PtmLocalizationReleaseSignature,
    manifest_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
    SupportStatus,
)
from glio_proteogen.modules.c05_ptm_localization.m05_08_release_packaging import (
    M0508Plugin,
    M0508Service,
)


def _reference(label: str) -> ArtifactReference:
    char = format(sum(map(ord, label)) % 16, "x")
    return ArtifactReference(
        artifact_id=f"evidence.m0508.{label}",
        version="1.0.0",
        digest=f"sha256:{char * 64}",
        media_type="application/json",
    )


def _accepted(role: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m0508.{role}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_reference(role),
    )


def _request() -> BuildPtmLocalizationReleaseRequest:
    context = ExecutionContext(
        request_id="request.m0508.smoke",
        actor_id="actor.m0508.smoke",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_accepted("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m0508.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=f"sha256:{'1' * 64}",
                evidence=_reference("identity"),
            ),
            provenance=_accepted("provenance"),
            consent=ConsentReference(
                decision_id="decision.m0508.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_reference("consent"),
            ),
            quality=_accepted("quality"),
            support=_accepted("support"),
            intended_use=_accepted("intended_use"),
        ),
    )
    stage_digest = f"sha256:{'2' * 64}"
    manifest = PtmLocalizationReleaseManifest(
        manifest_id="manifest.m0508.smoke",
        release_id="release.m0508.smoke",
        release_version="1.0.0",
        stage_result_digests=(stage_digest,),
        software_versions=("1.0.0",),
        reference_versions=("1.0.0",),
        quality_decision_ids=("decision.m0508.quality",),
        support_status=SupportStatus.SUPPORTED,
        reproducibility_evidence=(_reference("reproduction"),),
    )
    return BuildPtmLocalizationReleaseRequest(
        context=context,
        artifacts=(
            PtmLocalizationReleaseArtifact(
                path="parent/variant-peptide.json",
                role=PtmLocalizationReleaseArtifactRole.PARENT_VARIANT_PEPTIDE_HANDOFF,
                reference=_reference("parent"),
                declared_size=1,
            ),
        ),
        manifest=manifest,
        policy=PtmLocalizationReleasePolicy(
            policy_id="policy.m0508.smoke",
            policy_version="1.0.0",
            allowed_signature_algorithms=("ed25519",),
            allowed_verifier_ids=("verifier.m0508.smoke",),
            evidence=_reference("policy"),
        ),
        signature=PtmLocalizationReleaseSignature(
            algorithm="ed25519",
            key_id="key.m0508.smoke",
            signature_value="provisional-signature",
            claimed_manifest_digest=manifest_digest(manifest),
            evidence=_reference("signature"),
        ),
        upstream_result_digests=(stage_digest,),
    )


def test_provisional_runtime_manifest_and_plugin_smoke() -> None:
    request = _request()
    service = M0508Service()
    typed = service.validate_request(request.model_dump(mode="python"))

    assert typed == request
    assert service.manifest(request) == request.manifest
    assert M0508Plugin.descriptor["status"] == "provisional"
    assert M0508Plugin().validate_request(request) == request

    with pytest.raises(NotImplementedError, match="provisional"):
        service.execute(request)
