"""Adversarial replay and canonicalization tests for M10-08."""

from collections.abc import Iterator, Mapping
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from glio_proteogen.contracts.m10_08.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.contracts.m10_08.v1 import (
    ProteinRnaEvidencePublicationResult,
    PublisherFindingCode,
)
from glio_proteogen.modules.c10_pathway_proteotype_factors import (
    m10_08_evidence_explanation_publisher as m1008_runtime,
)
from tests.modules.c10_pathway_proteotype_factors.test_m10_08_runtime import _request


class _HostileMapping(Mapping[str, Any]):
    """Mapping whose accessors prove that canonicalization traversed it."""

    def __getitem__(self, key: str) -> Any:
        raise AssertionError

    def __iter__(self) -> Iterator[str]:
        raise AssertionError

    def __len__(self) -> int:
        raise AssertionError


class _DictSubclass(dict[str, Any]):
    """Subclass rejected so canonicalization has one trusted container path."""


def test_canonical_projection_rejects_hostile_mapping_without_access() -> None:
    hostile: Any = _HostileMapping()
    with pytest.raises(TypeError, match="exact dicts"):
        canonical_request_digest(hostile)
    with pytest.raises(TypeError, match="exact dicts"):
        result_payload_digest(hostile)


def test_canonical_projection_rejects_dict_subclass() -> None:
    with pytest.raises(TypeError, match="exact dicts"):
        canonical_request_digest(_DictSubclass(value=1))


def test_result_verifier_rejects_hostile_mapping_without_access() -> None:
    assert not m1008_runtime.verify_publication_result(_HostileMapping())


def _rehashed_result(result: ProteinRnaEvidencePublicationResult, **updates: Any) -> dict[str, Any]:
    payload = result.model_dump(mode="python")
    payload.update(updates)
    partial = ProteinRnaEvidencePublicationResult.model_construct(**payload)
    payload["result_digest"] = result_payload_digest(partial)
    return payload


def test_replay_rejects_forged_provenance_even_with_recomputed_result_digest() -> None:
    result = m1008_runtime.publish_protein_rna_evidence(_request())
    forged = result.provenance.model_copy(update={"actor_id": "forged.actor"})
    with pytest.raises(ValidationError, match="provenance does not bind"):
        ProteinRnaEvidencePublicationResult.model_validate(
            _rehashed_result(result, provenance=forged), strict=True
        )


def test_replay_rejects_forged_uncertainty_even_with_recomputed_result_digest() -> None:
    result = m1008_runtime.publish_protein_rna_evidence(_request())
    forged = result.uncertainty.model_copy(
        update={
            "sensitivity_notes": ("forged estimate",),
        }
    )
    with pytest.raises(ValidationError, match="uncertainty does not match"):
        ProteinRnaEvidencePublicationResult.model_validate(
            _rehashed_result(result, uncertainty=forged), strict=True
        )


def test_replay_rejects_nested_bundle_provenance_drift() -> None:
    result = m1008_runtime.publish_protein_rna_evidence(_request())
    assert result.bundle is not None
    forged_bundle = result.bundle.model_copy(
        update={"provenance": result.bundle.provenance.model_copy(update={"actor_id": "forged"})}
    )
    with pytest.raises(ValidationError, match="published bundle does not bind"):
        ProteinRnaEvidencePublicationResult.model_validate(
            _rehashed_result(result, bundle=forged_bundle), strict=True
        )


def test_result_verifier_replays_findings_instead_of_trusting_a_resigned_digest() -> None:
    result = m1008_runtime.publish_protein_rna_evidence(_request())
    forged = _rehashed_result(
        result,
        findings=(
            PublisherFindingCode.UPSTREAM_ABSTAINED,
            PublisherFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
        ),
    )
    assert not m1008_runtime.verify_publication_result(forged)


def test_model_canonicalization_still_accepts_trusted_pydantic_models() -> None:
    request = _request()
    assert isinstance(request, BaseModel)
    assert canonical_request_digest(request).startswith("sha256:")
