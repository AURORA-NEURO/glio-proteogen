"""Static safety and provenance checks for M01-01 quality-model reference assets."""

from __future__ import annotations

from importlib.resources import files
from typing import Any, Final, Literal, NotRequired, TypedDict, cast

import pytest
from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_01.canonical import protocol_digest
from glio_proteogen.contracts.m01_01.v1 import ProtocolSchema, ValueKind
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.strict_json import strict_json_loads

_PROFILE_PACKAGE: Final = "glio_proteogen.profiles.m01_01.v1"
_EXPECTED_CLUSTERS: Final = {
    "frozen_dda",
    "frozen_dia",
    "ffpe_dda",
    "ffpe_dia",
}
_EXPECTED_PROFILES_PER_CLUSTER: Final = 3
_STRICT_MAJORITY: Final = 0.5
_MINIMUM_AGREEING_VIEWS: Final = 2
_EXPECTED_VIEW_COUNT: Final = 3
_EXPECTED_MINIMUM_CONSENSUS: Final = 0.66
_DISALLOWED_PATH_TOKENS: Final = {
    "identity",
    "reference",
    "digest",
    "context",
    "raw_data",
    "protocol_reference",
    "report_reference",
}


class ModelFeature(TypedDict):
    path: str
    kind: Literal["categorical", "numeric"]
    minimum: NotRequired[float]
    maximum: NotRequired[float]


class ModelView(TypedDict):
    view_id: str
    paths: list[str]


class QualityModel(TypedDict):
    model_id: str
    model_version: str
    profile_schema_id: str
    profile_schema_version: str
    canonical_protocol_digest: str
    reference_corpus_file: str
    reference_corpus_digest: str
    minimum_consensus: float
    maximum_mean_distance: float
    minimum_view_coverage: float
    features: list[ModelFeature]
    views: list[ModelView]


class ReferenceProfile(TypedDict):
    profile_id: str
    cluster_id: str
    features: dict[str, str | int | float]


class ReferenceCorpus(TypedDict):
    corpus_id: str
    corpus_version: str
    description: str
    profiles: list[ReferenceProfile]


def _asset_bytes(name: str) -> bytes:
    return files(_PROFILE_PACKAGE).joinpath(name).read_bytes()


def _asset(name: str) -> Any:
    return strict_json_loads(_asset_bytes(name))


def _model() -> QualityModel:
    return cast("QualityModel", _asset("quality-model.json"))


def _corpus() -> ReferenceCorpus:
    return cast("ReferenceCorpus", _asset("quality-reference-corpus.json"))


def _schema() -> ProtocolSchema:
    return TypeAdapter(ProtocolSchema).validate_json(_asset_bytes("protocol-schema.json"))


@pytest.mark.contract
def test_quality_model_is_bound_to_profile_and_exact_reference_corpus() -> None:
    model = _model()
    schema = _schema()
    corpus_value = _asset(model["reference_corpus_file"])

    assert model["profile_schema_id"] == schema.schema_id
    assert model["profile_schema_version"] == schema.version
    assert model["canonical_protocol_digest"] == protocol_digest(schema)
    assert model["reference_corpus_file"] == "quality-reference-corpus.json"
    assert model["reference_corpus_digest"] == sha256_digest(corpus_value)
    assert _STRICT_MAJORITY < model["minimum_consensus"] <= 1
    assert model["minimum_consensus"] == _EXPECTED_MINIMUM_CONSENSUS
    assert len(model["views"]) == _EXPECTED_VIEW_COUNT
    assert _MINIMUM_AGREEING_VIEWS / len(model["views"]) >= model["minimum_consensus"]
    assert 0 <= model["maximum_mean_distance"] <= 1
    assert 0 < model["minimum_view_coverage"] <= 1


@pytest.mark.contract
def test_quality_asset_wire_shapes_are_exact_and_closed() -> None:
    model = _model()
    corpus = _corpus()

    assert set(model) == {
        "model_id",
        "model_version",
        "profile_schema_id",
        "profile_schema_version",
        "canonical_protocol_digest",
        "reference_corpus_file",
        "reference_corpus_digest",
        "minimum_consensus",
        "maximum_mean_distance",
        "minimum_view_coverage",
        "features",
        "views",
    }
    for feature in model["features"]:
        expected = {"path", "kind"}
        if feature["kind"] == "numeric":
            expected.update({"minimum", "maximum"})
        assert set(feature) == expected
    assert all(set(view) == {"view_id", "paths"} for view in model["views"])
    assert set(corpus) == {"corpus_id", "corpus_version", "description", "profiles"}
    assert all(
        set(profile) == {"profile_id", "cluster_id", "features"}
        for profile in corpus["profiles"]
    )


@pytest.mark.contract
def test_quality_features_are_schema_backed_non_sensitive_and_type_exact() -> None:
    model = _model()
    schema_fields = {field.path: field for field in _schema().fields}
    paths = [feature["path"] for feature in model["features"]]

    assert len(paths) == len(set(paths))
    assert all(path in schema_fields for path in paths)
    for feature in model["features"]:
        path = feature["path"]
        field = schema_fields[path]
        path_segments = path.removeprefix("/").split("/")
        assert set(path_segments).isdisjoint(_DISALLOWED_PATH_TOKENS)
        assert all(
            "reference" not in segment
            and not segment.endswith("_digest")
            and not segment.startswith("raw_data")
            for segment in path_segments
        )
        assert not field.identity_key
        assert field.value_kind in {ValueKind.TERM, ValueKind.BOOLEAN, ValueKind.NUMBER}
        if feature["kind"] == "categorical":
            assert field.value_kind in {ValueKind.TERM, ValueKind.BOOLEAN}
            assert "minimum" not in feature
            assert "maximum" not in feature
        else:
            assert field.value_kind is ValueKind.NUMBER
            assert field.reference_unit is not None
            assert feature["minimum"] < feature["maximum"]
            assert field.numeric_bounds is not None
            assert feature["minimum"] == field.numeric_bounds.minimum
            assert feature["maximum"] == field.numeric_bounds.maximum


@pytest.mark.contract
def test_reference_profiles_are_complete_type_safe_and_in_range() -> None:
    model = _model()
    corpus = _corpus()
    feature_map = {feature["path"]: feature for feature in model["features"]}
    expected_paths = set(feature_map)
    schema = _schema()
    vocabularies = {
        vocabulary.vocabulary_id: {term.code for term in vocabulary.terms}
        for vocabulary in schema.vocabularies
    }
    schema_fields = {field.path: field for field in schema.fields}
    profile_ids = [profile["profile_id"] for profile in corpus["profiles"]]

    assert len(profile_ids) == len(set(profile_ids))
    for profile in corpus["profiles"]:
        assert set(profile["features"]) == expected_paths
        for path, value in profile["features"].items():
            feature = feature_map[path]
            if feature["kind"] == "categorical":
                assert type(value) is str
                field = schema_fields[path]
                assert field.value_kind is ValueKind.TERM
                assert field.vocabulary_id is not None
                assert value in vocabularies[field.vocabulary_id]
            else:
                assert type(value) in {int, float}
                assert feature["minimum"] <= value <= feature["maximum"]


@pytest.mark.contract
def test_reference_corpus_balances_every_legal_preservation_acquisition_cluster() -> None:
    corpus = _corpus()
    clusters: dict[str, list[ReferenceProfile]] = {}
    for profile in corpus["profiles"]:
        clusters.setdefault(profile["cluster_id"], []).append(profile)

    assert set(clusters) == _EXPECTED_CLUSTERS
    assert all(len(profiles) == _EXPECTED_PROFILES_PER_CLUSTER for profiles in clusters.values())
    for cluster_id, profiles in clusters.items():
        expected_preservation, expected_acquisition = cluster_id.rsplit("_", maxsplit=1)
        expected_acquisition_code = {
            "dda": "PRIDE:0000627",
            "dia": "PRIDE:0000450",
        }[expected_acquisition]
        expected_preservation_code = {
            "frozen": "frozen_tissue",
            "ffpe": "ffpe_tissue",
        }[expected_preservation]
        assert all(
            profile["features"]["/specimen/preservation"]
            == expected_preservation_code
            and profile["features"]["/acquisition/method"]
            == expected_acquisition_code
            for profile in profiles
        )


@pytest.mark.contract
def test_every_consensus_view_is_closed_and_distinguishes_all_legal_clusters() -> None:
    model = _model()
    corpus = _corpus()
    known_paths = {feature["path"] for feature in model["features"]}
    view_ids = [view["view_id"] for view in model["views"]]

    assert len(view_ids) == len(set(view_ids))
    for view in model["views"]:
        paths = view["paths"]
        assert len(paths) == len(set(paths))
        assert set(paths).issubset(known_paths)
        assert {"/specimen/preservation", "/acquisition/method"}.issubset(paths)
        signatures: dict[str, set[tuple[str | int | float, ...]]] = {}
        for profile in corpus["profiles"]:
            signatures.setdefault(profile["cluster_id"], set()).add(
                tuple(profile["features"][path] for path in paths)
            )
        for cluster_id, cluster_signatures in signatures.items():
            other_signatures = set().union(
                *(
                    values
                    for other_id, values in signatures.items()
                    if other_id != cluster_id
                )
            )
            assert cluster_signatures.isdisjoint(other_signatures)


@pytest.mark.contract
def test_view_coverage_allows_declared_optional_quality_features_to_be_absent() -> None:
    model = _model()
    fields = {field.path: field for field in _schema().fields}

    for view in model["views"]:
        mandatory_count = sum(fields[path].required for path in view["paths"])
        assert mandatory_count / len(view["paths"]) >= model["minimum_view_coverage"]


@pytest.mark.contract
def test_quality_reference_assets_contain_no_identity_or_opaque_pointer_values() -> None:
    corpus_payload = _asset_bytes("quality-reference-corpus.json").lower()
    prohibited_literals = (
        b"sha256:",
        b"syn-glio",
        b"synthetic.001",
        b"/identity/",
        b"/context/",
        b"reference_id",
        b'"/identity/',
        b"raw_data",
    )

    assert all(literal not in corpus_payload for literal in prohibited_literals)
    for profile in _corpus()["profiles"]:
        assert all(
            not (isinstance(value, str) and (value.startswith("sha256:") or "synthetic" in value))
            for value in profile["features"].values()
        )


@pytest.mark.contract
def test_quality_reference_provenance_declares_no_training_or_sensitive_records() -> None:
    manifest = _asset("standards-manifest.json")
    catalog = _asset("catalog.json")
    provenance = manifest["quality_reference_provenance"]
    reference = catalog["quality_reference_model"]

    assert provenance["model_id"] == _model()["model_id"]
    assert provenance["model_version"] == _model()["model_version"]
    assert provenance["data_class"] == "synthetic_non_clinical"
    assert provenance["patient_record_count"] == 0
    assert provenance["identity_feature_count"] == 0
    assert provenance["opaque_pointer_feature_count"] == 0
    assert provenance["reference_profile_count"] == len(_corpus()["profiles"])
    assert (
        provenance["implementation_status"]
        == "integrated_quarantine_only_reference_domain_guard"
    )
    assert "cannot promote" in provenance["decision_authority"]
    assert "no trained" in provenance["interpretation_ceiling"]
    assert reference["development_status"] == "integrated_synthetic_reference_guard_not_fitted"
    assert reference["reference_design"]["fitted_parameters"] == 0
    assert reference["integrated_guard"]["algorithm"].startswith("deterministic")
    assert "can never promote" in reference["integrated_guard"]["decision_authority"]
