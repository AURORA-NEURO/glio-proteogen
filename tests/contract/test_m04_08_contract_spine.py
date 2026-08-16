"""ABI-independent contract checks for the M04-08 release-package spine."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from typing import cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m04_08 import (
    M0408_MAX_ARTIFACT_BYTES,
    ProteoformReleaseArtifact,
    ProteoformReleaseArtifactRole,
    ProteoformReleasePolicy,
    ProteoformReproductionEvidence,
    ProteoformSignatureAlgorithm,
    ProteoformSignatureVerification,
    ProteoformSignatureVerificationReason,
    contract_json_schemas,
    opaque_release_identifier,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import ArtifactReference
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging import (
    M0408Plugin,
    M0408Service,
    build_proteoform_release,
    build_proteoform_release_manifest,
    verify_proteoform_release,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging.engine import (
    ProteoformReleaseAuthorizationError,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging.plugin import (
    _InvalidSubmissionError,
)

_REPRODUCTION_EVIDENCE_COUNT = 9


def _digest(label: str) -> str:
    return sha256_digest({"m0408_test": label})


def _opaque(namespace: str, label: str) -> str:
    return f"{namespace}.{_digest(label).removeprefix('sha256:')}"


def _evidence(label: str, *, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=_opaque("evidence", label),
        version="1.0.0",
        digest=digest or _digest(f"evidence:{label}"),
        media_type="application/json",
    )


def test_m0408_owned_schema_inventory_is_exact_and_importable() -> None:
    schemas = contract_json_schemas()

    assert tuple(schemas) == (
        "request",
        "output",
        "policy",
        "artifact",
        "manifest",
        "verification",
        "signature",
        "stage-provenance",
        "reproduction-evidence",
    )
    for name, schema in schemas.items():
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        schema_id = schema["$id"]
        assert isinstance(schema_id, str)
        assert schema_id.endswith(f":{name}")
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["m0407BindingRequiredForExecution"] is True
        assert metadata["proteinRnaDiscordanceInference"] is False
        assert metadata["kinaseActivityInference"] is False
        assert metadata["treatmentRecommendation"] is False


def test_m0408_known_artifact_role_has_fixed_path_media_and_identifier() -> None:
    suffix = _digest("m0406-request").removeprefix("sha256:")
    artifact = ProteoformReleaseArtifact(
        path="stages/m04-06-harmonization.json",
        role=ProteoformReleaseArtifactRole.M04_06_HARMONIZATION,
        reference=ArtifactReference(
            artifact_id=f"result.m0406.{suffix}",
            version="1.0.0",
            digest=_digest("m0406-result-bytes"),
            media_type="application/vnd.glio-proteogen.m04-06+json",
        ),
        declared_size=M0408_MAX_ARTIFACT_BYTES,
    )

    assert artifact.role is ProteoformReleaseArtifactRole.M04_06_HARMONIZATION
    payload = artifact.model_dump(mode="json")
    payload["path"] = "stages/alias.json"
    with pytest.raises(ValidationError, match="fixed canonical path"):
        ProteoformReleaseArtifact.model_validate_json(canonical_json_bytes(payload), strict=True)


def test_m0408_m0407_artifact_validation_uses_the_exact_bound_abi() -> None:
    with pytest.raises(ValidationError, match="contradicts its fixed role"):
        ProteoformReleaseArtifact(
            path="stages/m04-07-upstream-result.json",
            role=ProteoformReleaseArtifactRole.M04_07_UPSTREAM_RESULT,
            reference=ArtifactReference(
                artifact_id=_opaque("unbound", "m0407"),
                version="1.0.0",
                digest=_digest("m0407-result-bytes"),
                media_type="application/octet-stream",
            ),
            declared_size=1,
        )


def test_m0408_reproduction_evidence_requires_nine_distinct_receipts() -> None:
    labels = (
        "environment_lock",
        "build_recipe",
        "locked_tests",
        "benchmark",
        "traceability",
        "risk_control_verification",
        "data_model_reference_manifest",
        "reviewer_signoff",
        "rollback",
    )
    values = {label: _evidence(label) for label in labels}

    evidence = ProteoformReproductionEvidence(**values)
    assert len(type(evidence).model_fields) == _REPRODUCTION_EVIDENCE_COUNT

    values["rollback"] = values["reviewer_signoff"]
    with pytest.raises(ValidationError, match="digests must be unique"):
        ProteoformReproductionEvidence(**values)


def test_m0408_policy_and_signature_verification_are_closed() -> None:
    verifier_id = _opaque("verifier", "primary")
    policy = ProteoformReleasePolicy(
        policy_id=_opaque("policy", "release"),
        version="1.0.0",
        allowed_signature_algorithms=(
            ProteoformSignatureAlgorithm.RSA_PSS_SHA256,
            ProteoformSignatureAlgorithm.ED25519,
        ),
        allowed_verifier_ids=(verifier_id,),
        evidence=_evidence("policy"),
        reviewed_by=_opaque("reviewer", "release"),
        reviewed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    verification = ProteoformSignatureVerification(
        verifier_id=verifier_id,
        algorithm=ProteoformSignatureAlgorithm.ED25519,
        key_id=_opaque("key", "release"),
        statement_digest=_digest("statement"),
        verified=True,
        reason_code=ProteoformSignatureVerificationReason.VERIFIED,
    )

    assert policy.allowed_signature_algorithms == (
        ProteoformSignatureAlgorithm.ED25519,
        ProteoformSignatureAlgorithm.RSA_PSS_SHA256,
    )
    assert verification.verified is True
    assert opaque_release_identifier("release", {"version": 1}).startswith("release.")


class _UntouchedMapping(Mapping[str, object]):
    touched = False

    def __getitem__(self, key: str) -> object:
        type(self).touched = True
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        type(self).touched = True
        return iter(())

    def __len__(self) -> int:
        type(self).touched = True
        return 0


@pytest.mark.parametrize(
    "operation",
    [
        lambda hostile: build_proteoform_release(object(), hostile, hostile),
        lambda hostile: build_proteoform_release_manifest(object(), hostile, hostile),
        lambda hostile: verify_proteoform_release(object(), cast("bytes", hostile)),
    ],
)
def test_m0408_runtime_fails_before_touching_inputs_after_authorization_denial(
    operation: Callable[[Mapping[str, object]], object],
) -> None:
    _UntouchedMapping.touched = False
    hostile = _UntouchedMapping()

    with pytest.raises((ProteoformReleaseAuthorizationError, ValidationError)):
        operation(hostile)
    assert _UntouchedMapping.touched is False


def test_m0408_plugin_publishes_dossier_metadata_and_rejects_invalid_submission() -> None:
    plugin = M0408Plugin(M0408Service())

    descriptor = plugin.descriptor()
    assert descriptor.module_id == "GLIO-PROTEOGEN-M04-08"
    assert descriptor.owner == "Bioinformatics"
    assert descriptor.safety_class == "S2"
    assert descriptor.gate == "G1"
    with pytest.raises(_InvalidSubmissionError):
        plugin.validate(object())
