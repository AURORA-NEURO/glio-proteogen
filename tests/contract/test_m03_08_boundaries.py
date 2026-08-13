"""Adversarial, replay, and maximum-shape boundaries for M03-08."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import pytest
from evals.m03_08.run import (
    Scenario,
    build_maximum_scenario,
    build_scenario,
)
from pydantic import ValidationError

from glio_proteogen.contracts.m03_08 import (
    M0308_ARCHIVE_MEMBER_COUNT,
    M0308_MAX_CANONICAL_REQUEST_BYTES,
    M0308_MAX_EVIDENCE,
    M0308_MAX_REFERENCE_VERSIONS,
    M0308_MAX_SOFTWARE_VERSIONS,
    BuildProteinInferenceReleaseRequest,
    ProteinInferencePackageVerificationReason,
    ProteinInferenceReleaseDisposition,
    ProteinInferenceReleasePackageDescriptor,
    ProteinInferenceReleaseQuarantineCode,
    ProteinInferenceReleaseResult,
    ProteinInferenceSignatureVerificationReason,
    ProteinInferenceSoftwareVersion,
    canonical_request_digest,
    expected_release_quarantine_reasons,
    manifest_digest,
    normalized_request,
    normalized_result,
    opaque_release_identifier,
    policy_digest,
    result_payload_digest,
    signing_statement_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import ArtifactReference
from glio_proteogen.modules.c03_protein_inference.m03_08_release_packaging import (
    BuiltProteinInferenceRelease,
    build_protein_inference_release,
    verify_protein_inference_release,
)

pytestmark = pytest.mark.contract

ZERO_DIGEST = "sha256:" + ("0" * 64)
FORGED_DIGEST = "sha256:" + ("f" * 64)


@dataclass(frozen=True, slots=True)
class BuiltScenario:
    scenario: Scenario
    built: BuiltProteinInferenceRelease


@pytest.fixture(scope="module")
def canonical() -> BuiltScenario:
    scenario = build_scenario()
    built = build_protein_inference_release(
        scenario.request,
        scenario.artifacts,
        scenario.stages,
        scenario.verifier,
    )
    return BuiltScenario(scenario, built)


def payload(value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value.model_dump(mode="python"))  # type: ignore[attr-defined]


def test_genuine_public_chain_releases_and_verifies_content_then_authenticity(
    canonical: BuiltScenario,
) -> None:
    result = canonical.built.result
    package = canonical.built.package_bytes
    assert result.disposition is ProteinInferenceReleaseDisposition.RELEASED
    assert package is not None
    assert len(result.manifest.artifacts) + 2 == M0308_ARCHIVE_MEMBER_COUNT
    assert result.package_descriptor is not None
    assert result.package_descriptor.member_count == M0308_ARCHIVE_MEMBER_COUNT
    verification = verify_protein_inference_release(
        result,
        package,
        canonical.scenario.verifier,
    )
    assert (
        verification.content_verified,
        verification.authenticity_verified,
        verification.verified,
        verification.reason_code,
    ) == (True, True, True, ProteinInferencePackageVerificationReason.VERIFIED)


def test_typed_dict_and_json_reconstruction_are_exact(canonical: BuiltScenario) -> None:
    result = canonical.built.result
    from_dict = ProteinInferenceReleaseResult.model_validate(payload(result), strict=True)
    from_json = ProteinInferenceReleaseResult.model_validate_json(
        result.model_dump_json(), strict=True
    )
    assert from_dict == from_json == result
    assert normalized_result(from_dict) == normalized_result(from_json)


def test_request_semantic_reorder_materializes_identically(canonical: BuiltScenario) -> None:
    request = canonical.scenario.request
    values = payload(request)
    for field in ("artifacts", "software_versions", "reference_versions"):
        values[field] = tuple(reversed(values[field]))
    values["policy"]["allowed_signature_algorithms"] = tuple(
        reversed(values["policy"]["allowed_signature_algorithms"])
    )
    values["policy"]["allowed_verifier_ids"] = tuple(
        reversed(values["policy"]["allowed_verifier_ids"])
    )
    reordered = BuildProteinInferenceReleaseRequest.model_validate(values, strict=True)
    assert reordered == request
    assert normalized_request(reordered) == normalized_request(request)
    assert canonical_request_digest(reordered) == canonical_request_digest(request)


def test_full_result_semantic_reorder_materializes_identically(canonical: BuiltScenario) -> None:
    result = canonical.built.result
    values = payload(result)
    for field in ("artifacts", "software_versions", "reference_versions"):
        values["manifest"][field] = tuple(reversed(values["manifest"][field]))
    for stage in values["manifest"]["stages"]:
        stage["bound_upstream_result_digests"] = tuple(
            reversed(stage["bound_upstream_result_digests"])
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
    values["provenance"]["input_digests"] = tuple(reversed(values["provenance"]["input_digests"]))
    values["provenance"]["control_decisions"] = tuple(
        reversed(values["provenance"]["control_decisions"])
    )
    for field in ("evidence", "limitations", "quarantine_reasons"):
        values[field] = tuple(reversed(values[field]))
    values["uncertainty"]["sensitivity_notes"] = tuple(
        reversed(values["uncertainty"]["sensitivity_notes"])
    )
    reconstructed = ProteinInferenceReleaseResult.model_validate(values, strict=True)
    assert reconstructed == result
    assert normalized_result(reconstructed) == normalized_result(result)


@pytest.mark.parametrize(
    "forged_digest",
    [ZERO_DIGEST, FORGED_DIGEST],
    ids=["zero", "stale"],
)
def test_zero_and_stale_result_digest_sentinels_are_rejected(
    canonical: BuiltScenario,
    forged_digest: str,
) -> None:
    values = payload(canonical.built.result)
    values["result_digest"] = forged_digest
    with pytest.raises(ValidationError, match="result digest"):
        ProteinInferenceReleaseResult.model_validate(values, strict=True)


def test_resigned_result_id_forgery_is_rejected(canonical: BuiltScenario) -> None:
    values = payload(canonical.built.result)
    values["release_result_id"] = "result.m0308." + ("f" * 64)
    values["result_digest"] = result_payload_digest(values)
    with pytest.raises(ValidationError, match="identifier does not bind"):
        ProteinInferenceReleaseResult.model_validate(values, strict=True)


def test_nonlexical_result_id_is_rejected_before_digest_replay(
    canonical: BuiltScenario,
) -> None:
    values = payload(canonical.built.result)
    values["release_result_id"] = "release.m0308." + ("f" * 64)
    with pytest.raises(ValidationError, match="opaque M03-08 result alias"):
        ProteinInferenceReleaseResult.model_validate(values, strict=True)


def test_built_release_requires_package_presence_to_match_disposition(
    canonical: BuiltScenario,
) -> None:
    with pytest.raises(ValueError, match="package-byte presence"):
        BuiltProteinInferenceRelease(canonical.built.result, None)


def test_verification_rejects_mutable_package_bytes(canonical: BuiltScenario) -> None:
    with pytest.raises(TypeError, match="immutable bytes"):
        verify_protein_inference_release(
            canonical.built.result,
            cast("bytes", bytearray()),
            canonical.scenario.verifier,
        )


def test_request_rejects_duplicate_metadata_identity(canonical: BuiltScenario) -> None:
    values = payload(canonical.scenario.request)
    values["software_versions"] = (
        *values["software_versions"][:-1],
        values["software_versions"][0],
    )
    with pytest.raises(ValidationError, match="metadata identifiers must be unique"):
        BuildProteinInferenceReleaseRequest.model_validate(values, strict=True)


def test_package_descriptor_rejects_duplicate_member_paths(canonical: BuiltScenario) -> None:
    descriptor = canonical.built.result.package_descriptor
    assert descriptor is not None
    values = payload(descriptor)
    values["members"] = (*values["members"][:-1], values["members"][0])
    with pytest.raises(ValidationError, match="member paths must be alias-free"):
        ProteinInferenceReleasePackageDescriptor.model_validate(values, strict=True)


def test_resigned_package_byte_size_forgery_is_rejected(canonical: BuiltScenario) -> None:
    values = payload(canonical.built.result)
    values["package_descriptor"]["byte_size"] += 1
    values["result_digest"] = result_payload_digest(values)
    with pytest.raises(ValidationError, match="canonical USTAR framing"):
        ProteinInferenceReleaseResult.model_validate(values, strict=True)


def test_package_digest_is_authenticated_only_against_the_archive_bytes(
    canonical: BuiltScenario,
) -> None:
    values = payload(canonical.built.result)
    values["package_descriptor"]["digest"] = FORGED_DIGEST
    values["result_digest"] = result_payload_digest(values)
    resigned = ProteinInferenceReleaseResult.model_validate(values, strict=True)
    package = canonical.built.package_bytes
    assert package is not None
    verifier = canonical.scenario.verifier
    calls = len(verifier.calls)
    verification = verify_protein_inference_release(resigned, package, verifier)
    assert verification.reason_code is (
        ProteinInferencePackageVerificationReason.DESCRIPTOR_MISMATCH
    )
    assert verification.content_verified is verification.authenticity_verified is False
    assert len(verifier.calls) == calls


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("policy_digest", "policy digest"),
        ("manifest_digest", "manifest digest"),
        ("statement_digest", "does not bind the release statement"),
        ("descriptor_digest", "contradicts a caller artifact"),
        ("support", "support envelope"),
        ("uncertainty", "uncertainty must remain"),
        ("provenance", "exact unique input digest set"),
        ("control", "control decisions do not match"),
        ("evidence", "evidence index or claims"),
        ("limitations", "exact limitation statements"),
        ("request_digest", "request digest"),
    ],
)
def test_resigned_relational_forgery_matrix_is_rejected(  # noqa: C901
    canonical: BuiltScenario,
    mutation: str,
    message: str,
) -> None:
    values = payload(canonical.built.result)
    if mutation == "policy_digest":
        values["policy_digest"] = FORGED_DIGEST
    elif mutation == "manifest_digest":
        values["manifest_digest"] = FORGED_DIGEST
    elif mutation == "statement_digest":
        values["signature_verification"]["statement_digest"] = FORGED_DIGEST
    elif mutation == "descriptor_digest":
        member = next(item for item in values["package_descriptor"]["members"] if item["role"])
        member["digest"] = FORGED_DIGEST
    elif mutation == "support":
        values["support"]["rationale"] = "Forged release support."
    elif mutation == "uncertainty":
        values["uncertainty"]["transport"]["rationale"] = "Forged uncertainty."
    elif mutation == "provenance":
        values["provenance"]["input_digests"] = values["provenance"]["input_digests"][1:]
    elif mutation == "control":
        values["provenance"]["control_decisions"][0]["decision_id"] = "decision.forged"
    elif mutation == "evidence":
        values["evidence"] = values["evidence"][1:]
    elif mutation == "limitations":
        values["limitations"][0]["statement"] = "Forged limitation."
    else:
        values["request_digest"] = FORGED_DIGEST
    values["result_digest"] = result_payload_digest(values)
    with pytest.raises(ValidationError, match=message):
        ProteinInferenceReleaseResult.model_validate(values, strict=True)


def test_signature_rejection_quarantines_without_package_bytes() -> None:
    scenario = build_scenario()
    scenario.verifier.accept = False
    built = build_protein_inference_release(
        scenario.request,
        scenario.artifacts,
        scenario.stages,
        scenario.verifier,
    )
    assert built.package_bytes is None
    assert built.result.disposition is ProteinInferenceReleaseDisposition.QUARANTINED
    assert built.result.package_descriptor is None
    assert tuple(item.code for item in built.result.quarantine_reasons) == (
        ProteinInferenceReleaseQuarantineCode.SIGNATURE_UNVERIFIED,
    )
    assert built.result.signature_verification.reason_code is (
        ProteinInferenceSignatureVerificationReason.VERIFIER_REJECTED
    )
    assert len(scenario.verifier.calls) == 1


def test_verification_content_failure_never_calls_verifier(canonical: BuiltScenario) -> None:
    package = canonical.built.package_bytes
    assert package is not None
    verifier = canonical.scenario.verifier
    calls = len(verifier.calls)
    outcome = verify_protein_inference_release(
        canonical.built.result,
        package[:-1],
        verifier,
    )
    assert outcome.content_verified is False
    assert outcome.authenticity_verified is outcome.verified is False
    assert outcome.package_digest is outcome.manifest_digest is None
    assert outcome.member_count == 0
    assert outcome.signature_verification.reason_code is (
        ProteinInferenceSignatureVerificationReason.NOT_ATTEMPTED
    )
    assert outcome.signature_verification.verifier_id is None
    assert len(verifier.calls) == calls


def test_manifest_quarantine_precedence_names_every_unreleasable_stage(
    canonical: BuiltScenario,
) -> None:
    manifest_values = payload(canonical.built.result.manifest)
    manifest_values["stages"][3]["disposition"] = "quarantined"
    manifest_values["stages"][3]["human_review_required"] = True
    manifest_values["m0304_quality_disposition"] = "quarantined"
    manifest = type(canonical.built.result.manifest).model_validate(manifest_values, strict=True)
    verification_values = payload(canonical.built.result.signature_verification)
    verification_values.update(
        verifier_id=None,
        verified=False,
        reason_code=ProteinInferenceSignatureVerificationReason.NOT_ATTEMPTED,
    )
    verification = type(canonical.built.result.signature_verification).model_validate(
        verification_values, strict=True
    )
    reasons = expected_release_quarantine_reasons(manifest, verification)
    assert len(reasons) == 1
    assert reasons[0].code is ProteinInferenceReleaseQuarantineCode.UPSTREAM_NOT_RELEASABLE
    assert reasons[0].stage_module_id is not None
    assert reasons[0].reason_code == "human_review_required"


def test_exact_maximum_metadata_shape_executes_with_152_evidence() -> None:
    scenario = build_maximum_scenario()
    request_bytes = canonical_json_bytes(normalized_request(scenario.request))
    assert len(scenario.request.software_versions) == M0308_MAX_SOFTWARE_VERSIONS
    assert len(scenario.request.reference_versions) == M0308_MAX_REFERENCE_VERSIONS
    assert len(request_bytes) <= M0308_MAX_CANONICAL_REQUEST_BYTES
    built = build_protein_inference_release(
        scenario.request,
        scenario.artifacts,
        scenario.stages,
        scenario.verifier,
    )
    assert built.result.disposition is ProteinInferenceReleaseDisposition.RELEASED
    assert len(built.result.evidence) == M0308_MAX_EVIDENCE
    assert built.package_bytes is not None


def test_first_excess_metadata_record_is_rejected_before_packaging() -> None:
    scenario = build_maximum_scenario()
    request_values = payload(scenario.request)
    request_values["software_versions"] = (
        *request_values["software_versions"],
        ProteinInferenceSoftwareVersion(
            software_id=opaque_release_identifier("software", "first-excess"),
            version="1.0.0",
            build_digest=sha256_digest("first-excess-build"),
            evidence=ArtifactReference(
                artifact_id=opaque_release_identifier("evidence", "first-excess"),
                version="1.0.0",
                digest=sha256_digest("first-excess-evidence"),
                media_type="application/json",
            ),
        ).model_dump(mode="python"),
    )
    with pytest.raises(ValidationError, match="at most 64 items"):
        BuildProteinInferenceReleaseRequest.model_validate(request_values, strict=True)


def test_recursive_output_contains_no_biological_or_secret_canaries(
    canonical: BuiltScenario,
) -> None:
    serialized = canonical.built.result.model_dump_json()
    for canary in (
        "MPEPTIDEK",
        "raw_spectrum_peak",
        "treatment_recommendation",
        "PRIVATE_KEY",
        "signature_secret",
    ):
        assert canary not in serialized


@pytest.mark.parametrize(
    "channel",
    [
        "request_id",
        "actor_id",
        "approved_configuration",
        "identity_lineage",
        "provenance",
        "consent",
        "quality",
        "support",
        "intended_use",
    ],
)
def test_biological_canary_in_every_reflected_context_identifier_is_rejected(
    canonical: BuiltScenario,
    channel: str,
) -> None:
    values = payload(canonical.scenario.request)
    if channel in {"request_id", "actor_id"}:
        values["context"][channel] = "mpeptidek"
    else:
        values["context"]["references"][channel]["decision_id"] = "mpeptidek"
    with pytest.raises(ValidationError, match=r"opaque"):
        BuildProteinInferenceReleaseRequest.model_validate(values, strict=True)


@pytest.mark.parametrize(
    "control",
    [
        "approved_configuration",
        "identity_lineage",
        "provenance",
        "consent",
        "quality",
        "support",
        "intended_use",
    ],
)
def test_biological_canary_in_every_reflected_control_evidence_id_is_rejected(
    canonical: BuiltScenario,
    control: str,
) -> None:
    values = payload(canonical.scenario.request)
    values["context"]["references"][control]["evidence"]["artifact_id"] = "mpeptidek"
    with pytest.raises(ValidationError, match=r"opaque evidence"):
        BuildProteinInferenceReleaseRequest.model_validate(values, strict=True)


@pytest.mark.parametrize(
    "control",
    [
        "approved_configuration",
        "identity_lineage",
        "provenance",
        "consent",
        "quality",
        "support",
        "intended_use",
    ],
)
def test_reflected_control_evidence_media_type_requires_lowercase_lexical_syntax(
    canonical: BuiltScenario,
    control: str,
) -> None:
    values = payload(canonical.scenario.request)
    values["context"]["references"][control]["evidence"]["media_type"] = "Application/JSON"
    with pytest.raises(ValidationError, match=r"lowercase type/subtype"):
        BuildProteinInferenceReleaseRequest.model_validate(values, strict=True)


def test_manifest_digest_and_result_digest_are_nonzero(canonical: BuiltScenario) -> None:
    result = canonical.built.result
    assert manifest_digest(result.manifest) == result.manifest_digest != ZERO_DIGEST
    assert result_payload_digest(result) == result.result_digest != ZERO_DIGEST


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("context_digest", "context digest"),
        ("stage_order", "nondecreasing completion times"),
        ("stage_after_signature", "signature cannot precede"),
        ("signature_after_context", "cannot postdate"),
        ("policy_after_signature", "review cannot postdate"),
        ("manifest_policy", "manifest does not bind"),
        ("manifest_identity", "authorized identity"),
        ("manifest_intended_use", "intended-use evidence"),
        ("verified_unreleasable", "must not invoke"),
        ("false_statement_mismatch", "mismatch outcome is inconsistent"),
        ("not_attempted_releasable", "requires a signature verification attempt"),
        ("disposition", "disposition contradicts"),
        ("quarantine_reasons", "not exactly derived"),
        ("package_presence", "only a released result"),
    ],
)
def test_full_result_temporal_statement_and_disposition_forgery_matrix(  # noqa: C901, PLR0912
    canonical: BuiltScenario,
    mutation: str,
    message: str,
) -> None:
    from datetime import timedelta  # noqa: PLC0415 - local test-only mutation helper.

    values = payload(canonical.built.result)
    if mutation == "context_digest":
        values["context_digest"] = FORGED_DIGEST
    elif mutation == "stage_order":
        values["manifest"]["stages"][1]["generated_at"] = values["manifest"]["stages"][0][
            "generated_at"
        ] - timedelta(microseconds=1)
    elif mutation == "stage_after_signature":
        values["manifest"]["stages"][-1]["generated_at"] = values["signature"][
            "issued_at"
        ] + timedelta(microseconds=1)
    elif mutation == "signature_after_context":
        values["signature"]["issued_at"] = values["context"]["occurred_at"] + timedelta(
            microseconds=1
        )
    elif mutation == "policy_after_signature":
        values["policy"]["reviewed_at"] = values["signature"]["issued_at"] + timedelta(
            microseconds=1
        )
        values["policy_digest"] = policy_digest(values["policy"])
        values["manifest"]["policy_digest"] = values["policy_digest"]
        values["manifest_digest"] = manifest_digest(values["manifest"])
        values["signature_verification"]["statement_digest"] = signing_statement_digest(
            active_manifest_digest=values["manifest_digest"],
            active_policy_digest=values["policy_digest"],
            release_id=values["manifest"]["release_id"],
            release_version=values["manifest"]["release_version"],
            identity_resolution_digest=values["manifest"]["identity_resolution_digest"],
            intended_use_evidence_digest=values["manifest"]["intended_use_evidence_digest"],
            support_route_result_digest=values["manifest"]["support_route_result_digest"],
        )
    elif mutation == "manifest_policy":
        values["manifest"]["policy_digest"] = FORGED_DIGEST
        values["manifest_digest"] = manifest_digest(values["manifest"])
    elif mutation == "manifest_identity":
        for stage in values["manifest"]["stages"]:
            stage["identity_resolution_digest"] = FORGED_DIGEST
        values["manifest"]["identity_resolution_digest"] = FORGED_DIGEST
        values["manifest_digest"] = manifest_digest(values["manifest"])
    elif mutation == "manifest_intended_use":
        values["manifest"]["intended_use_evidence_digest"] = FORGED_DIGEST
        values["manifest_digest"] = manifest_digest(values["manifest"])
    elif mutation == "verified_unreleasable":
        values["manifest"]["stages"][3]["disposition"] = "quarantined"
        values["manifest"]["m0304_quality_disposition"] = "quarantined"
        values["manifest_digest"] = manifest_digest(values["manifest"])
        values["signature_verification"]["statement_digest"] = signing_statement_digest(
            active_manifest_digest=values["manifest_digest"],
            active_policy_digest=values["policy_digest"],
            release_id=values["manifest"]["release_id"],
            release_version=values["manifest"]["release_version"],
            identity_resolution_digest=values["manifest"]["identity_resolution_digest"],
            intended_use_evidence_digest=values["manifest"]["intended_use_evidence_digest"],
            support_route_result_digest=values["manifest"]["support_route_result_digest"],
        )
    elif mutation == "false_statement_mismatch":
        values["signature_verification"].update(
            verifier_id=None,
            verified=False,
            reason_code=ProteinInferenceSignatureVerificationReason.STATEMENT_MISMATCH,
        )
    elif mutation == "not_attempted_releasable":
        values["signature_verification"].update(
            verifier_id=None,
            verified=False,
            reason_code=ProteinInferenceSignatureVerificationReason.NOT_ATTEMPTED,
        )
    elif mutation == "disposition":
        values["disposition"] = ProteinInferenceReleaseDisposition.QUARANTINED
    elif mutation == "quarantine_reasons":
        values["quarantine_reasons"] = (
            {
                "code": ProteinInferenceReleaseQuarantineCode.SIGNATURE_UNVERIFIED,
                "stage_module_id": None,
                "reason_code": "verifier_rejected",
                "remediation_code": "provide_verified_signature",
            },
        )
    else:
        values["package_descriptor"] = None
    values["result_digest"] = result_payload_digest(values)
    with pytest.raises(ValidationError, match=message):
        ProteinInferenceReleaseResult.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("manifest_member", "manifest member"),
        ("receipt_member", "verification receipt"),
        ("provenance_envelope", "provenance envelope"),
        ("consent_provenance", "consent provenance"),
        ("sensitivity_notes", "sensitivity notes"),
    ],
)
def test_result_generated_member_and_envelope_forgery_matrix(
    canonical: BuiltScenario,
    mutation: str,
    message: str,
) -> None:
    values = payload(canonical.built.result)
    if mutation == "manifest_member":
        member = next(
            item
            for item in values["package_descriptor"]["members"]
            if item["path"].endswith("reproducibility-manifest.json")
        )
        member["digest"] = FORGED_DIGEST
    elif mutation == "receipt_member":
        member = next(
            item
            for item in values["package_descriptor"]["members"]
            if item["path"].endswith("signature-verification.json")
        )
        member["digest"] = FORGED_DIGEST
    elif mutation == "provenance_envelope":
        values["provenance"]["actor_id"] = opaque_release_identifier("actor", "forged")
    elif mutation == "consent_provenance":
        values["provenance"]["consent_decision_id"] = opaque_release_identifier(
            "decision", "forged"
        )
    else:
        values["uncertainty"]["sensitivity_notes"] = ("Forged sensitivity note.",)
    values["result_digest"] = result_payload_digest(values)
    with pytest.raises(ValidationError, match=message):
        ProteinInferenceReleaseResult.model_validate(values, strict=True)
