"""Focused schema and deterministic-fixture smoke for provisional M21-02."""

from typing import Any, cast

import pytest
from evals.m21_02.fixture import build_request
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from glio_proteogen.contracts.m21_02 import (
    M2102_DOSSIER_SHA256,
    M2102_DOSSIER_SLICE,
    M2102_M2101_INPUT_MEDIA_TYPE,
    M2102_OUTPUT_MEDIA_TYPE,
    M2102_PROVISIONAL_ABI,
    ComplexActivitySyntheticTruthResult,
    FixtureKind,
    GenerateComplexActivitySyntheticTruthRequest,
    GenerationConfiguration,
    GenerationManifest,
    GenerationStatus,
    SyntheticTruthCorpus,
    TruthRepresentation,
    contract_json_schemas,
)
from glio_proteogen.contracts.m21_02.canonical import canonical_request_digest
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c21_reference_material.m21_02_synthetic_truth_simulation_generator import (  # noqa: E501
    M2102Service,
)

_SCHEMA_COUNT = 7
_FIXTURE_KIND_COUNT = 5


def test_provisional_schemas_require_reproducible_truth_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "corpus",
        "case",
        "manifest",
        "configuration",
        "finding",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["analyticallyKnownFixturesRequired"] is True
        assert metadata["semiSyntheticFixturesRequired"] is True
        assert metadata["normalEdgeMissingShiftedAdversarialCoverage"] is True
        assert metadata["deterministicSeedRequired"] is True
        assert metadata["reproducibilityManifestRequired"] is True
        assert metadata["unsupportedToNegative"] is False
        assert metadata["parentTarget"] == "complex activity"
        assert metadata["upstreamInputMediaType"] == M2102_M2101_INPUT_MEDIA_TYPE
        assert metadata["dossierSha256"] == M2102_DOSSIER_SHA256
        assert metadata["dossierSlice"] == M2102_DOSSIER_SLICE
    output_metadata = cast("dict[str, object]", schemas["output"]["x-glio-contract"])
    assert output_metadata["outputMediaType"] == M2102_OUTPUT_MEDIA_TYPE
    assert M2102_PROVISIONAL_ABI is True


def test_fixture_kinds_and_generation_states_are_explicit() -> None:
    assert len(tuple(FixtureKind)) == _FIXTURE_KIND_COUNT
    assert FixtureKind.ADVERSARIAL.value == "adversarial"
    assert TruthRepresentation.ANALYTIC.value == "analytic"
    assert GenerationStatus.GENERATED.value == "generated"
    assert GenerationStatus.ABSTAINED.value == "abstained"


def test_contract_rejects_duplicate_kinds_and_uses_mapping_canonicalization() -> None:
    request = build_request()
    with pytest.raises(ValueError, match="fixture kinds"):
        request.configuration.model_validate(
            request.configuration.model_copy(
                update={"requested_fixture_kinds": (FixtureKind.NORMAL, FixtureKind.NORMAL)}
            ),
            strict=True,
        )
    assert canonical_request_digest({"request_id": "mapping"}).startswith("sha256:")


def test_contract_rejects_duplicate_manifest_and_corpus_case_ids() -> None:
    request = build_request()
    result = M2102Service().generate(request)
    assert result.manifest is not None
    assert result.corpus is not None
    with pytest.raises(ValueError, match="manifest case ids"):
        GenerationManifest.model_validate(
            result.manifest.model_copy(
                update={"case_ids": (result.manifest.case_ids[0], result.manifest.case_ids[0])}
            ),
            strict=True,
        )
    with pytest.raises(ValueError, match="corpus case ids"):
        SyntheticTruthCorpus.model_validate(
            result.corpus.model_copy(
                update={"cases": (result.corpus.cases[0], result.corpus.cases[0])}
            ),
            strict=True,
        )
    with pytest.raises(ValueError, match="enumerate"):
        SyntheticTruthCorpus.model_validate(
            result.corpus.model_copy(
                update={
                    "manifest": result.manifest.model_copy(
                        update={"case_ids": result.manifest.case_ids[:-1]}
                    )
                }
            ),
            strict=True,
        )


def test_request_and_result_closures_bind_context_manifest_and_case_count() -> None:
    request = build_request()
    result = M2102Service().generate(request)
    assert result.manifest is not None
    assert result.corpus is not None
    with pytest.raises(ValueError, match="request id"):
        GenerateComplexActivitySyntheticTruthRequest.model_validate(
            request.model_copy(
                update={"context": request.context.model_copy(update={"request_id": "other"})}
            ),
            strict=True,
        )
    empty_configuration_data = request.configuration.model_dump(mode="python")
    empty_configuration_data["requested_fixture_kinds"] = ()
    empty_configuration = GenerationConfiguration.model_construct(**empty_configuration_data)
    empty_request = request.model_copy(update={"configuration": empty_configuration})
    with pytest.raises(ValueError, match="at least one fixture"):
        cast("Any", empty_request).request_is_bound()
    with pytest.raises(ValueError, match="request digest"):
        ComplexActivitySyntheticTruthResult.model_validate(
            result.model_copy(update={"request_digest": sha256_digest("wrong-request")}),
            strict=True,
        )
    with pytest.raises(ValueError, match="manifest must equal"):
        ComplexActivitySyntheticTruthResult.model_validate(
            result.model_copy(
                update={"manifest": result.manifest.model_copy(update={"manifest_id": "other"})}
            ),
            strict=True,
        )
    alternate_configuration = request.configuration.model_copy(update={"seed": 7})
    alternate_manifest = result.manifest.model_copy(
        update={"configuration": alternate_configuration}
    )
    alternate_corpus = result.corpus.model_copy(update={"manifest": alternate_manifest})
    with pytest.raises(ValueError, match="configuration"):
        ComplexActivitySyntheticTruthResult.model_validate(
            result.model_copy(update={"manifest": alternate_manifest, "corpus": alternate_corpus}),
            strict=True,
        )
    alternate_request = request.model_copy(update={"requested_case_count": 9})
    with pytest.raises(ValueError, match="case count"):
        ComplexActivitySyntheticTruthResult.model_validate(
            result.model_copy(
                update={
                    "request": alternate_request,
                    "request_digest": canonical_request_digest(alternate_request),
                }
            ),
            strict=True,
        )
    altered_case = result.corpus.cases[0].model_copy(update={"case_id": "other.case"})
    with pytest.raises(ValueError, match="enumerate every"):
        ComplexActivitySyntheticTruthResult.model_validate(
            result.model_copy(
                update={
                    "corpus": result.corpus.model_copy(
                        update={"cases": (altered_case, *result.corpus.cases[1:])}
                    )
                }
            ),
            strict=True,
        )
    with pytest.raises(ValueError, match="result digest"):
        ComplexActivitySyntheticTruthResult.model_validate(
            result.model_copy(update={"result_digest": sha256_digest("wrong-result")}),
            strict=True,
        )
