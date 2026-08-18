"""Exercise concrete M04-08 validator, service, and plugin closure branches."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import pytest
from evals.m04_08.run import _fixture

if TYPE_CHECKING:
    from collections.abc import Callable

from glio_proteogen.contracts.m04_08 import (
    BuildProteoformReleaseRequest,
    ProteoformReleaseDisposition,
    ProteoformReproducibilityManifest,
    ProteoformSignatureAlgorithm,
)
from glio_proteogen.contracts.m04_08 import v1 as contract_v1
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging import (
    M0408Plugin,
    M0408Service,
    ProteoformReleaseSubmission,
    build_proteoform_release,
    build_proteoform_release_manifest,
)


def _rejects(validator: Callable[[Any], object], value: Any) -> None:
    with pytest.raises(ValueError, match=r".*"):
        validator(value)


def _request_with_artifact(
    request: BuildProteoformReleaseRequest,
    index: int,
    **updates: object,
) -> BuildProteoformReleaseRequest:
    artifacts = list(request.artifacts)
    artifacts[index] = artifacts[index].model_copy(update=updates)
    return request.model_copy(update={"artifacts": tuple(artifacts)})


def _request_with_context(
    request: BuildProteoformReleaseRequest,
    **reference_updates: object,
) -> BuildProteoformReleaseRequest:
    references = request.context.references.model_copy(update=reference_updates)
    return request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )


def test_request_validator_rejects_each_authorization_and_size_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _fixture().request
    identity = request.context.references.identity_lineage
    identity_without_binding = identity.model_copy(update={"binding_digest": None})
    references_without_binding = request.context.references.model_copy(
        update={"identity_lineage": identity_without_binding}
    )
    duplicate_roles = _request_with_artifact(request, 1, role=request.artifacts[0].role)
    duplicate_paths = _request_with_artifact(request, 1, path=request.artifacts[0].path)
    oversized = _request_with_artifact(
        request, 0, declared_size=request.policy.max_artifact_bytes + 1
    )
    total_oversized = request.model_copy(
        update={"policy": request.policy.model_copy(update={"max_total_bytes": 1})}
    )
    disallowed_algorithm = request.model_copy(
        update={
            "signature": request.signature.model_copy(
                update={"algorithm": ProteoformSignatureAlgorithm.RSA_PSS_SHA256}
            )
        }
    )
    issued_late = request.model_copy(
        update={
            "signature": request.signature.model_copy(
                update={"issued_at": datetime(2027, 1, 1, tzinfo=UTC)}
            )
        }
    )
    policy_reviewed_late = request.model_copy(
        update={
            "policy": request.policy.model_copy(
                update={"reviewed_at": datetime(2027, 1, 1, tzinfo=UTC)}
            )
        }
    )
    wrong_policy_digest = _request_with_context(
        request,
        approved_configuration=request.context.references.approved_configuration.model_copy(
            update={
                "evidence": request.context.references.approved_configuration.evidence.model_copy(
                    update={"digest": "sha256:" + "0" * 64}
                )
            }
        ),
    )
    aliased_intended_use = _request_with_context(
        request,
        intended_use=request.context.references.intended_use.model_copy(
            update={
                "evidence": identity.evidence.model_copy(update={"digest": identity.binding_digest})
            }
        ),
    )
    duplicate_software = request.model_copy(
        update={
            "software_versions": (
                request.software_versions[0],
                request.software_versions[0].model_copy(),
            )
        }
    )
    duplicate_reference = request.model_copy(
        update={
            "reference_versions": (
                request.reference_versions[0],
                request.reference_versions[0].model_copy(),
            )
        }
    )
    validator = cast(
        "Callable[[Any], object]",
        BuildProteoformReleaseRequest.request_is_authorized_closed_and_bounded,
    )
    candidates = (
        (
            "identity",
            request.model_copy(
                update={
                    "context": request.context.model_copy(
                        update={"references": references_without_binding}
                    )
                }
            ),
        ),
        ("roles", duplicate_roles),
        ("paths", duplicate_paths),
        ("artifact-size", oversized),
        ("total-size", total_oversized),
        ("algorithm", disallowed_algorithm),
        ("issued-at", issued_late),
        ("reviewed-at", policy_reviewed_late),
        ("policy-digest", wrong_policy_digest),
        ("intended-use", aliased_intended_use),
        ("software", duplicate_software),
        ("reference", duplicate_reference),
    )
    for label, candidate in candidates:
        try:
            validator(candidate)
        except ValueError:
            continue
        raise AssertionError(label)

    monkeypatch.setattr(contract_v1, "M0408_MAX_CANONICAL_REQUEST_BYTES", 1)
    _rejects(validator, request)


def test_manifest_validator_rejects_lineage_identity_and_disposition_branches() -> None:
    fixture = _fixture()
    manifest = build_proteoform_release_manifest(fixture.request, fixture.artifacts, fixture.stages)
    validator = cast(
        "Callable[[Any], object]", ProteoformReproducibilityManifest.manifest_is_owned_and_closed
    )

    artifacts = list(manifest.artifacts)
    artifacts[1] = artifacts[1].model_copy(update={"role": artifacts[0].role})
    reversed_stages = tuple(reversed(manifest.stages))
    late_stage = manifest.stages[0].model_copy(
        update={"generated_at": datetime(2027, 1, 1, tzinfo=UTC)}
    )
    changed_stage = manifest.stages[0].model_copy(update={"byte_digest": "sha256:" + "0" * 64})
    changed_request = manifest.stages[0].model_copy(update={"request_digest": "sha256:" + "0" * 64})
    changed_upstream = manifest.stages[0].model_copy(
        update={"bound_upstream_result_digests": ("sha256:" + "0" * 64,)}
    )
    base_candidates = (
        manifest.model_copy(update={"artifacts": tuple(artifacts)}),
        manifest.model_copy(update={"stages": reversed_stages}),
        manifest.model_copy(update={"stages": (late_stage, *manifest.stages[1:])}),
        manifest.model_copy(update={"reproduction_evidence_digest": "sha256:" + "0" * 64}),
        manifest.model_copy(update={"stages": (changed_stage, *manifest.stages[1:])}),
        manifest.model_copy(update={"stages": (changed_request, *manifest.stages[1:])}),
        manifest.model_copy(update={"stages": (changed_upstream, *manifest.stages[1:])}),
        manifest.model_copy(update={"identity_resolution_digest": "sha256:" + "0" * 64}),
        manifest.model_copy(update={"terminal_routing_result_digest": "sha256:" + "0" * 64}),
        manifest.model_copy(update={"terminal_routing_disposition": "rejected"}),
    )
    for candidate in base_candidates:
        _rejects(validator, candidate)

    accepted_missing = manifest.model_copy(update={"m0406_transformation_manifest_digest": None})
    _rejects(validator, accepted_missing)
    nonaccepted_claim = manifest.model_copy(
        update={
            "m0406_harmonization_disposition": "abstained",
            "m0406_transformation_manifest_digest": "sha256:" + "0" * 64,
        }
    )
    _rejects(validator, nonaccepted_claim)


def test_result_validator_rejects_signature_release_and_digest_branches() -> None:
    fixture = _fixture()
    verifier_id = fixture.request.policy.allowed_verifier_ids[0]

    class _Verifier:
        def __init__(self, verifier_id: str) -> None:
            self.verifier_id = verifier_id

        def verify(self, **_kwargs: object) -> bool:
            return True

    built = build_proteoform_release(
        fixture.request,
        fixture.artifacts,
        fixture.stages,
        _Verifier(verifier_id),
    )
    result = built.result
    validator = cast("Callable[[Any], object]", type(result).owned_result_regions_are_closed)
    zero = "sha256:" + "0" * 64
    candidates = (
        result.model_copy(update={"context_digest": zero}),
        result.model_copy(update={"policy_digest": zero}),
        result.model_copy(update={"manifest_digest": zero}),
        result.model_copy(
            update={
                "signature": result.signature.model_copy(update={"claimed_statement_digest": zero})
            }
        ),
        result.model_copy(
            update={
                "signature_verification": result.signature_verification.model_copy(
                    update={"statement_digest": zero}
                )
            }
        ),
        result.model_copy(update={"disposition": ProteoformReleaseDisposition.QUARANTINED}),
        result.model_copy(update={"package_descriptor": None}),
        result.model_copy(update={"quarantine_reasons": (object(),)}),
        result.model_copy(update={"human_review_required": True}),
        result.model_copy(update={"result_digest": zero}),
    )
    for candidate in candidates:
        _rejects(validator, candidate)


def test_service_and_plugin_cover_typed_json_and_facade_paths() -> None:
    fixture = _fixture()
    service = M0408Service()
    assert service.validate_request(fixture.request) == fixture.request
    manifest = service.manifest(fixture.request, fixture.artifacts, fixture.stages)
    assert manifest.release_id == fixture.request.release_id

    plugin = M0408Plugin(service)
    submission = ProteoformReleaseSubmission(
        request=fixture.request,
        artifacts_by_path=fixture.artifacts,
        stage_results_by_module=fixture.stages,
    )
    token = plugin.validate(submission)
    assert token.request == fixture.request
    built = plugin.run(token)
    assert built.result.release_result_id.startswith("result.m0408.")

    json_submission = ProteoformReleaseSubmission(
        request=fixture.request.model_dump_json(),
        artifacts_by_path=fixture.artifacts,
        stage_results_by_module=fixture.stages,
    )
    json_token = plugin.validate(json_submission)
    assert json_token.request == fixture.request
