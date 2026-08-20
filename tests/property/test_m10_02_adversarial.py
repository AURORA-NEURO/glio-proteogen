"""Adversarial closure for M10-02 ownership, replay, and safe failure."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m10_02 import (
    FeatureLineage,
    RepresentationFeature,
    RepresentationFeatureValueKind,
    RepresentationInputFeature,
    RepresentationMissingness,
    TransformationStep,
    result_payload_digest,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_02_representation_feature_constructor import (  # noqa: E501
    construct_protein_rna_representation,
    verify_result_replay,
)
from tests.modules.test_m10_02_representation_constructor import _request


def test_strict_input_rejects_numeric_string_coercion() -> None:
    with pytest.raises(ValueError, match="valid number"):
        RepresentationInputFeature(
            feature_id="protein.alpha",
            value_kind=RepresentationFeatureValueKind.SCALAR,
            state=RepresentationMissingness.OBSERVED,
            unit="log2_ratio",
            scalar_value="1.5",  # type: ignore[arg-type]
        )


def test_configuration_rejects_duplicate_transformation_outputs() -> None:
    base = _request()
    with pytest.raises(ValueError, match="output feature identifiers must be unique"):
        base.configuration.model_copy(
            update={
                "transformations": (
                    TransformationStep(
                        transformation_id="transform.one",
                        operation="identity",
                        input_feature_ids=("protein.alpha",),
                        output_feature_ids=("representation.alpha", "representation.alpha"),
                        fit_scope="none",
                    ),
                )
            }
        )


def test_tampered_result_digest_is_not_replayable() -> None:
    result = construct_protein_rna_representation(_request())
    tampered = result.model_copy(update={"result_digest": "sha256:" + ("f" * 64)})
    assert verify_result_replay(tampered) is False


def test_self_rehashed_semantic_mutation_is_not_replayable() -> None:
    result = construct_protein_rna_representation(_request())
    mutated = result.model_copy(update={"abstention_reason": "caller-rehashed semantic mutation"})
    forged = mutated.model_copy(update={"result_digest": result_payload_digest(mutated)})
    assert verify_result_replay(forged) is False


def test_observed_feature_cannot_carry_multiple_value_shapes() -> None:
    source = _request().source_artifacts[0]
    with pytest.raises(ValueError, match="exactly one"):
        RepresentationFeature(
            feature_id="representation.alpha",
            value_kind=RepresentationFeatureValueKind.SCALAR,
            state=RepresentationMissingness.OBSERVED,
            unit="log2_ratio",
            scalar_value=1.0,
            category="wrong-shape",
            lineage=FeatureLineage(
                feature_id="representation.alpha",
                source_artifacts=(source,),
            ),
        )
