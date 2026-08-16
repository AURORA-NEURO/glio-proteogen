"""Lightweight contract and schema gates for provisional M15-01."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m15_01 import (
    M1501_OUTPUT_MEDIA_TYPE,
    BiologicalHypothesis,
    CompetingExplanation,
    EvidenceTier,
    FalsificationRule,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

_SCHEMA_COUNT = 10


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1501": label}),
        media_type="application/json",
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim=f"Evidence claim for {label}.",
    )


def test_m1501_schemas_are_strict_and_explicitly_provisional() -> None:
    schemas = contract_json_schemas()

    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["pendingOwnerConfirmation"]
        for schema in schemas.values()
    )
    metadata = schemas["output"]["x-glio-contract"]
    assert metadata["outputMediaType"] == M1501_OUTPUT_MEDIA_TYPE
    assert metadata["parentTarget"] == "complex_activity"
    assert metadata["primaryArchitecture"] == "sparse_nmf"
    assert metadata["competingExplanationsRequired"]
    assert metadata["falsificationRulesRequired"]
    assert metadata["evidenceTiersRequired"]
    assert metadata["explicitAbstentionRequired"]


def test_m1501_hypothesis_requires_competing_explanations_and_falsification() -> None:
    evidence = _evidence("hypothesis")
    hypothesis = BiologicalHypothesis(
        hypothesis_id="hypothesis.complex",
        version="1.0.0",
        statement="Complex activity is associated with the declared state.",
        mechanism_class="sparse_nmf",
        target_ids=("complex.activity",),
        competing_explanations=(
            CompetingExplanation(
                explanation_id="explanation.alternate",
                statement="An alternate complex explains the signal.",
                distinction="Compare stoichiometric support.",
                required_evidence=(evidence,),
            ),
        ),
        falsification_rules=(
            FalsificationRule(
                rule_id="rule.support",
                criterion="Required evidence supports the mechanism.",
                failure_condition="Evidence is absent or contradictory.",
                required_evidence=(evidence,),
                prohibited_interpretation="Do not infer treatment response.",
            ),
        ),
        evidence_tiers=(
            EvidenceTier(
                tier=1,
                label="locked",
                rationale="Reviewed evidence is available.",
                evidence=(evidence,),
            ),
        ),
        prohibited_interpretations=("No direct treatment recommendation.",),
    )
    assert hypothesis.competing_explanations
    assert hypothesis.falsification_rules

    with pytest.raises(ValueError, match="at least 1 item"):
        BiologicalHypothesis(
            hypothesis_id="hypothesis.invalid",
            version="1.0.0",
            statement="Incomplete hypothesis.",
            mechanism_class="sparse_nmf",
            target_ids=("complex.activity",),
            competing_explanations=(),
            falsification_rules=(),
            evidence_tiers=(),
            prohibited_interpretations=("No treatment inference.",),
        )
