"""Adversarial closure for M04-08 request, manifest, and result validators."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

import pytest
from evals.m04_08.run import _fixture

if TYPE_CHECKING:
    from collections.abc import Callable

from glio_proteogen.contracts.m04_08 import (
    BuildProteoformReleaseRequest,
    ExternalProteoformSignature,
    ProteoformReleaseResult,
    ProteoformReproducibilityManifest,
)
from glio_proteogen.contracts.m04_08 import v1 as contract_v1
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging import (
    build_proteoform_release,
    build_proteoform_release_manifest,
)


class _AcceptingVerifier:
    @property
    def verifier_id(self) -> str:
        return _fixture().request.policy.allowed_verifier_ids[0]

    def verify(self, *, statement_digest: str, signature: ExternalProteoformSignature) -> bool:
        return statement_digest == signature.claimed_statement_digest


def _rejects(model: Callable[[Any], object], payload: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r".*"):
        model(payload)


def test_request_validator_rejects_authority_and_inventory_mutations() -> None:
    fixture = _fixture()
    baseline = fixture.request.model_dump(mode="json")

    mutations: tuple[Callable[[dict[str, Any]], None], ...] = (
        lambda value: value["context"]["references"]["identity_lineage"].update(
            {"binding_digest": None}
        ),
        lambda value: value["artifacts"][1].update({"role": value["artifacts"][0]["role"]}),
        lambda value: value["artifacts"][1].update({"path": value["artifacts"][0]["path"]}),
        lambda value: value["artifacts"][0].update({"declared_size": 1}),
        lambda value: value["policy"].update({"max_total_bytes": 1}),
        lambda value: value["signature"].update({"algorithm": "rsa_pss_sha256"}),
        lambda value: value["signature"].update({"issued_at": "2027-01-01T00:00:00Z"}),
        lambda value: value["policy"].update({"reviewed_at": "2027-01-01T00:00:00Z"}),
        lambda value: value["context"]["references"]["intended_use"].update(
            {"evidence": value["context"]["references"]["identity_lineage"]["evidence"]}
        ),
        lambda value: value["software_versions"].append(value["software_versions"][0]),
    )
    for mutate in mutations:
        payload = deepcopy(baseline)
        mutate(payload)
        _rejects(BuildProteoformReleaseRequest.model_validate, payload)


def test_manifest_validator_rejects_stage_and_digest_mutations() -> None:
    fixture = _fixture()
    manifest = build_proteoform_release_manifest(fixture.request, fixture.artifacts, fixture.stages)
    baseline = manifest.model_dump(mode="json")
    mutations: tuple[Callable[[dict[str, Any]], None], ...] = (
        lambda value: value["artifacts"][1].update({"role": value["artifacts"][0]["role"]}),
        lambda value: value["stages"].reverse(),
        lambda value: value["stages"][0].update({"generated_at": "2027-01-01T00:00:00Z"}),
        lambda value: value.update({"reproduction_evidence_digest": "sha256:" + "0" * 64}),
        lambda value: value["stages"][0].update({"byte_digest": "sha256:" + "0" * 64}),
        lambda value: value["stages"][0].update({"request_digest": "sha256:" + "0" * 64}),
        lambda value: value["stages"][0].update(
            {"bound_upstream_result_digests": ["sha256:" + "0" * 64]}
        ),
        lambda value: value.update({"identity_resolution_digest": "sha256:" + "0" * 64}),
        lambda value: value.update({"terminal_routing_result_digest": "sha256:" + "0" * 64}),
        lambda value: value.update({"terminal_routing_disposition": "rejected"}),
        lambda value: value.update({"m0406_transformation_manifest_digest": None}),
    )
    for mutate in mutations:
        payload = deepcopy(baseline)
        mutate(payload)
        _rejects(ProteoformReproducibilityManifest.model_validate, payload)


def test_result_validator_rejects_digest_and_release_state_mutations() -> None:
    fixture = _fixture()
    built = build_proteoform_release(
        fixture.request,
        fixture.artifacts,
        fixture.stages,
        _AcceptingVerifier(),
    )
    baseline = built.result.model_dump(mode="json")
    mutations: tuple[Callable[[dict[str, Any]], None], ...] = (
        lambda value: value.update({"context_digest": "sha256:" + "0" * 64}),
        lambda value: value.update({"policy_digest": "sha256:" + "0" * 64}),
        lambda value: value.update({"manifest_digest": "sha256:" + "0" * 64}),
        lambda value: value["signature"].update({"claimed_statement_digest": "sha256:" + "0" * 64}),
        lambda value: value.update({"disposition": "quarantined"}),
        lambda value: value.update({"package_descriptor": None}),
        lambda value: value.update({"human_review_required": True}),
        lambda value: value.update({"result_digest": "sha256:" + "0" * 64}),
    )
    for mutate in mutations:
        payload = deepcopy(baseline)
        mutate(payload)
        _rejects(ProteoformReleaseResult.model_validate, payload)


def test_binding_freeze_and_missing_binding_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    binding = contract_v1._M0407_BINDING
    assert binding is not None
    with pytest.raises(RuntimeError, match="immutable"):
        contract_v1._bind_m0407_contract(
            artifact_id_pattern=binding.artifact_id_pattern.pattern,
            artifact_id_prefix=binding.artifact_id_prefix,
            media_type="application/octet-stream",
            dispositions=binding.dispositions,
            releasable_dispositions=binding.releasable_dispositions,
            direct_upstream_modules=binding.direct_upstream_modules,
        )
    monkeypatch.setattr(contract_v1, "_M0407_BINDING", None)
    with pytest.raises(contract_v1.M0408DependencyUnavailableError, match="frozen"):
        contract_v1._m0407_binding()
