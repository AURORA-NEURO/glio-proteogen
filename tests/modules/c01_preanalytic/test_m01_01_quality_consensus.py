"""Adversarial evidence for the deterministic synthetic reference-domain guard."""

from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from decimal import ROUND_DOWN, ROUND_UP, Decimal, getcontext
from importlib.resources import files
from io import BytesIO
from typing import TYPE_CHECKING, cast

import pytest
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m01_01.v1 import (
    MetadataDocument,
    ObservedValue,
    ProtocolSchema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata import (
    quality_consensus as consensus,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.quality_consensus import (
    ConsensusStatus,
    FeatureKind,
    LoadedQualityConsensus,
    QualityConsensusArtifactError,
    QualityConsensusModel,
    QualityFeature,
    QualityReferenceCorpus,
    QualityView,
    ReferenceProfile,
    assess_quality_consensus,
    load_packaged_quality_consensus,
    unavailable_quality_assessment,
)

if TYPE_CHECKING:
    from pathlib import Path

_PROFILE_PACKAGE = "glio_proteogen.profiles.m01_01.v1"
_MODEL_DIGEST = "sha256:c0d8b536f2d162a41fb7ff6d3de9941f7debad31aa15bc39444a993e16ab869b"
_CORPUS_DIGEST = "sha256:9ae807d745cbda935222758a2ce29d0d6855cd6452dd16adf9c694fed6145940"
_MINIMUM_CONSENSUS = 0.66
_MINIMUM_VIEW_COVERAGE = 0.75
_ASSET_NAMES = (
    "protocol-schema.json",
    "quality-model.json",
    "quality-reference-corpus.json",
)

pytestmark = pytest.mark.contract


def _profile_case() -> tuple[ProtocolSchema, MetadataDocument]:
    package = files(_PROFILE_PACKAGE)
    schema = TypeAdapter(ProtocolSchema).validate_json(
        package.joinpath("protocol-schema.json").read_bytes(),
        strict=True,
    )
    corpus = strict_json_loads(package.joinpath("conformance-corpus.json").read_bytes())
    assert isinstance(corpus, dict)
    document = TypeAdapter(MetadataDocument).validate_json(
        canonical_json_bytes(corpus["base_document"]),
        strict=True,
    )
    return schema, document


def _replace_observed(
    document: MetadataDocument,
    path: str,
    value: str | float,
) -> MetadataDocument:
    entries = []
    for entry in document.entries:
        if entry.path != path:
            entries.append(entry)
            continue
        current = entry.values[0]
        assert isinstance(current, ObservedValue)
        entries.append(
            entry.model_copy(
                update={
                    "values": (
                        ObservedValue(value=value, unit=current.unit),
                    )
                }
            )
        )
    return document.model_copy(update={"entries": tuple(entries)})


def _copy_assets(target: Path) -> None:
    package = files(_PROFILE_PACKAGE)
    for name in _ASSET_NAMES:
        (target / name).write_bytes(package.joinpath(name).read_bytes())


def _tamper_packaged_assets(target: Path, tamper: str) -> None:
    model_path = target / "quality-model.json"
    direct_payloads = {
        "duplicate_json_key": b'{"model_id":"a","model_id":"b"}',
        "oversized_model": b" " * (consensus._MAX_MODEL_BYTES + 1),
    }
    oversized_resources = {
        "oversized_protocol": ("protocol-schema.json", consensus._MAX_PROTOCOL_BYTES),
        "oversized_corpus": ("quality-reference-corpus.json", consensus._MAX_CORPUS_BYTES),
    }
    model_mutations: dict[str, tuple[str, object]] = {
        "schema_id": ("profile_schema_id", "profile.forged"),
        "schema_version": ("profile_schema_version", "1.0.1"),
        "schema_digest": ("canonical_protocol_digest", f"sha256:{'0' * 64}"),
        "model_id": ("model_id", "consensus.forged"),
        "model_version": ("model_version", "1.0.1"),
        "minimum_consensus": ("minimum_consensus", 0.67),
        "maximum_mean_distance": ("maximum_mean_distance", 0.31),
        "minimum_view_coverage": ("minimum_view_coverage", 0.76),
    }
    if tamper == "missing_model":
        model_path.unlink()
        return
    if tamper in direct_payloads:
        model_path.write_bytes(direct_payloads[tamper])
        return
    if tamper in oversized_resources:
        name, maximum = oversized_resources[tamper]
        (target / name).write_bytes(b" " * (maximum + 1))
        return
    if tamper == "corpus_digest":
        corpus_path = target / "quality-reference-corpus.json"
        corpus = strict_json_loads(corpus_path.read_bytes())
        assert isinstance(corpus, dict)
        corpus["description"] = "Tampered synthetic reference corpus."
        corpus_path.write_bytes(canonical_json_bytes(corpus))
        return
    model = strict_json_loads(model_path.read_bytes())
    assert isinstance(model, dict)
    field, value = model_mutations[tamper]
    model[field] = value
    model_path.write_bytes(canonical_json_bytes(model))


def test_packaged_consensus_identity_and_closed_thresholds_are_locked() -> None:
    loaded = load_packaged_quality_consensus()

    assert loaded.model.model_id == "glio_preanalytic_quality_consensus"
    assert loaded.model.model_version == "1.0.0"
    assert loaded.model.minimum_consensus == _MINIMUM_CONSENSUS
    assert loaded.model.minimum_view_coverage == _MINIMUM_VIEW_COVERAGE
    assert loaded.model_digest == _MODEL_DIGEST
    assert loaded.corpus.corpus_id == "glio_preanalytic_quality_reference"
    assert loaded.corpus.corpus_version == "1.0.0"
    assert loaded.corpus_digest == _CORPUS_DIGEST


@pytest.mark.parametrize(
    "tamper",
    [
        "schema_id",
        "schema_version",
        "schema_digest",
        "model_id",
        "model_version",
        "minimum_consensus",
        "maximum_mean_distance",
        "minimum_view_coverage",
        "corpus_digest",
        "duplicate_json_key",
        "oversized_model",
        "oversized_protocol",
        "oversized_corpus",
        "missing_model",
    ],
)
def test_packaged_loader_fails_closed_on_tamper_or_resource_violation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    _copy_assets(tmp_path)
    _tamper_packaged_assets(tmp_path, tamper)
    monkeypatch.setattr(consensus, "files", lambda _package: tmp_path)

    with pytest.raises(
        QualityConsensusArtifactError,
        match="artifacts are invalid or unavailable",
    ) as caught:
        load_packaged_quality_consensus()

    assert str(caught.value) == (
        "M01-01 quality consensus artifacts are invalid or unavailable"
    )


def test_resource_reader_never_reads_beyond_the_first_excess_byte() -> None:
    class TrackingStream(BytesIO):
        requested: list[int]

        def __init__(self, value: bytes) -> None:
            super().__init__(value)
            self.requested = []

        def read(self, size: int = -1, /) -> bytes:
            self.requested.append(size)
            return super().read(size)

    class Resource:
        def __init__(self, value: bytes) -> None:
            self.stream = TrackingStream(value)

        def open(self, _mode: str) -> TrackingStream:
            return self.stream

    exact = Resource(b"x" * 16)
    excess = Resource(b"x" * 17)

    assert consensus._bounded_resource_bytes(exact, 16) == b"x" * 16
    with pytest.raises(QualityConsensusArtifactError):
        consensus._bounded_resource_bytes(excess, 16)

    assert exact.stream.requested == [17]
    assert excess.stream.requested == [17]


def test_loader_has_independent_identity_and_corpus_pins_after_model_digest_pin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy_assets(tmp_path)
    _tamper_packaged_assets(tmp_path, "model_id")
    model_value = strict_json_loads((tmp_path / "quality-model.json").read_bytes())
    monkeypatch.setattr(consensus, "OWNED_QUALITY_MODEL_DIGEST", sha256_digest(model_value))
    monkeypatch.setattr(consensus, "files", lambda _package: tmp_path)
    with pytest.raises(QualityConsensusArtifactError):
        load_packaged_quality_consensus()

    _copy_assets(tmp_path)
    monkeypatch.setattr(consensus, "OWNED_QUALITY_MODEL_DIGEST", _MODEL_DIGEST)
    monkeypatch.setattr(consensus, "OWNED_QUALITY_CORPUS_DIGEST", f"sha256:{'0' * 64}")
    with pytest.raises(QualityConsensusArtifactError):
        load_packaged_quality_consensus()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate_feature", "path"),
        ("duplicate_view", "view"),
        ("duplicate_view_path", "reference"),
        ("dangling_view_path", "reference"),
        ("path_traversal", "String should match pattern"),
    ],
)
def test_model_contract_rejects_ambiguous_graphs_and_paths(
    mutation: str,
    message: str,
) -> None:
    payload = load_packaged_quality_consensus().model.model_dump(mode="json")
    if mutation == "duplicate_feature":
        payload["features"].append(deepcopy(payload["features"][0]))
    elif mutation == "duplicate_view":
        payload["views"].append(deepcopy(payload["views"][0]))
    elif mutation == "duplicate_view_path":
        payload["views"][0]["paths"].append(payload["views"][0]["paths"][0])
    elif mutation == "dangling_view_path":
        payload["views"][0]["paths"][0] = "/unknown/path"
    else:
        payload["reference_corpus_file"] = "../quality-reference-corpus.json"

    with pytest.raises(ValidationError, match=message):
        TypeAdapter(QualityConsensusModel).validate_json(
            json.dumps(payload),
            strict=True,
        )


@pytest.mark.parametrize(
    ("kind", "minimum", "maximum"),
    [
        (FeatureKind.NUMERIC, None, 1.0),
        (FeatureKind.NUMERIC, 1.0, 1.0),
        (FeatureKind.NUMERIC, 2.0, 1.0),
        (FeatureKind.CATEGORICAL, 0.0, 1.0),
    ],
)
def test_feature_bounds_match_the_declared_kind(
    kind: FeatureKind,
    minimum: float | None,
    maximum: float | None,
) -> None:
    with pytest.raises(ValidationError, match="bounds"):
        QualityFeature(
            path="/synthetic/value",
            kind=kind,
            minimum=minimum,
            maximum=maximum,
        )


def test_loaded_artifacts_reject_sensitive_paths_duplicate_profiles_and_one_cluster() -> None:
    loaded = load_packaged_quality_consensus()
    first_feature = loaded.model.features[0]
    sensitive = first_feature.model_copy(update={"path": "/patient/value"})
    sensitive_model = loaded.model.model_copy(
        update={"features": (sensitive, *loaded.model.features[1:])}
    )
    duplicate_profiles = loaded.corpus.model_copy(
        update={
            "profiles": (
                loaded.corpus.profiles[0],
                loaded.corpus.profiles[0],
                *loaded.corpus.profiles[2:],
            )
        }
    )
    one_cluster = loaded.corpus.model_copy(
        update={
            "profiles": tuple(
                profile.model_copy(update={"cluster_id": "only_cluster"})
                for profile in loaded.corpus.profiles
            )
        }
    )
    incomplete_profile = loaded.corpus.profiles[0].model_copy(
        update={
            "features": dict(tuple(loaded.corpus.profiles[0].features.items())[1:])
        }
    )
    incomplete_corpus = loaded.corpus.model_copy(
        update={"profiles": (incomplete_profile, *loaded.corpus.profiles[1:])}
    )
    anchors_only = frozenset({"/specimen/preservation", "/acquisition/method"})
    anchor_view = loaded.model.views[0].model_copy(
        update={
            "paths": tuple(
                path for path in loaded.model.views[0].paths if path in anchors_only
            )
        }
    )
    anchor_only_model = loaded.model.model_copy(
        update={"views": (anchor_view, *loaded.model.views[1:])}
    )

    for candidate in (
        LoadedQualityConsensus(
            model=sensitive_model,
            corpus=loaded.corpus,
            model_digest=loaded.model_digest,
            corpus_digest=loaded.corpus_digest,
        ),
        LoadedQualityConsensus(
            model=loaded.model,
            corpus=duplicate_profiles,
            model_digest=loaded.model_digest,
            corpus_digest=loaded.corpus_digest,
        ),
        LoadedQualityConsensus(
            model=loaded.model,
            corpus=one_cluster,
            model_digest=loaded.model_digest,
            corpus_digest=loaded.corpus_digest,
        ),
        LoadedQualityConsensus(
            model=loaded.model,
            corpus=incomplete_corpus,
            model_digest=loaded.model_digest,
            corpus_digest=loaded.corpus_digest,
        ),
        LoadedQualityConsensus(
            model=anchor_only_model,
            corpus=loaded.corpus,
            model_digest=loaded.model_digest,
            corpus_digest=loaded.corpus_digest,
        ),
    ):
        with pytest.raises(QualityConsensusArtifactError):
            consensus._validate_loaded_quality_consensus(candidate)


def test_reference_profiles_are_deeply_immutable_and_round_trip_as_json() -> None:
    profile = load_packaged_quality_consensus().corpus.profiles[0]
    mutable_view = cast("dict[str, str | int | float]", profile.features)
    path = next(iter(profile.features))

    with pytest.raises(TypeError):
        mutable_view[path] = "tamper"

    serialized = profile.model_dump_json()
    assert TypeAdapter(ReferenceProfile).validate_json(serialized, strict=True) == profile


def test_loaded_audit_rejects_any_view_that_cannot_self_identify_its_medoids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = load_packaged_quality_consensus()
    monkeypatch.setattr(consensus, "_view_vote", lambda *_args: None)

    with pytest.raises(QualityConsensusArtifactError):
        consensus._validate_loaded_quality_consensus(loaded)


def test_true_pairwise_medoid_cost_is_rejected_at_first_excess_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = load_packaged_quality_consensus()
    cluster_sizes = Counter(profile.cluster_id for profile in loaded.corpus.profiles)
    pair_count = sum(size * size for size in cluster_sizes.values())
    path_count = sum(len(view.paths) for view in loaded.model.views)
    exact_operations = path_count * pair_count + (
        len(loaded.model.views)
        * len(cluster_sizes)
        * len(loaded.corpus.profiles)
    )

    monkeypatch.setattr(consensus, "_MAX_VIEW_OPERATIONS", exact_operations)
    consensus._validate_loaded_quality_consensus(loaded)
    monkeypatch.setattr(consensus, "_MAX_VIEW_OPERATIONS", exact_operations - 1)
    with pytest.raises(QualityConsensusArtifactError):
        consensus._validate_loaded_quality_consensus(loaded)


def test_assessment_statuses_are_closed_and_never_expose_internal_clusters() -> None:
    schema, document = _profile_case()
    loaded = load_packaged_quality_consensus()
    in_domain = assess_quality_consensus(schema, document, loaded)
    ood_document = _replace_observed(
        document,
        "/specimen/warm_ischemia_time",
        1440.0,
    )
    out_of_domain = assess_quality_consensus(schema, ood_document, loaded)
    anchor_paths = {"/specimen/preservation", "/acquisition/method"}
    missing_anchor = document.model_copy(
        update={
            "entries": tuple(
                entry for entry in document.entries if entry.path not in anchor_paths
            )
        }
    )
    indeterminate = assess_quality_consensus(schema, missing_anchor, loaded)
    unrelated = assess_quality_consensus(
        schema.model_copy(update={"schema_id": "profile.unrelated"}),
        document,
        loaded,
    )

    assert (in_domain.status, in_domain.reason_code) == (
        ConsensusStatus.IN_DOMAIN,
        "quality.consensus_supported",
    )
    assert in_domain.evaluated_views > 0
    assert (out_of_domain.status, out_of_domain.reason_code) == (
        ConsensusStatus.OUT_OF_DOMAIN,
        "quality.novel_or_ood",
    )
    assert (indeterminate.status, indeterminate.reason_code) == (
        ConsensusStatus.INDETERMINATE,
        "quality.anchor_indeterminate",
    )
    assert (unrelated.status, unrelated.reason_code) == (
        ConsensusStatus.NOT_APPLICABLE,
        "quality.not_applicable",
    )
    rendered = repr((in_domain, out_of_domain, indeterminate, unrelated))
    for cluster in ("frozen_dda", "frozen_dia", "ffpe_dda", "ffpe_dia"):
        assert cluster not in rendered


def test_consensus_distance_can_quarantine_inside_the_reference_support_envelope() -> None:
    schema, document = _profile_case()
    loaded = load_packaged_quality_consensus()
    shifted = _replace_observed(document, "/specimen/warm_ischemia_time", 0.0)
    strict_model = loaded.model.model_copy(update={"maximum_mean_distance": 0.0})
    strict_loaded = LoadedQualityConsensus(
        model=strict_model,
        corpus=loaded.corpus,
        model_digest=loaded.model_digest,
        corpus_digest=loaded.corpus_digest,
    )
    values = consensus._extract_features(schema, shifted, strict_model)

    assert not consensus._outside_reference_support(values, strict_model, loaded.corpus)
    assessment = assess_quality_consensus(schema, shifted, strict_loaded)
    assert assessment.status is ConsensusStatus.OUT_OF_DOMAIN
    assert assessment.reason_code == "quality.novel_or_ood"


def test_insufficient_non_anchor_features_abstain_instead_of_imputing() -> None:
    schema, document = _profile_case()
    loaded = load_packaged_quality_consensus()
    anchors = {"/specimen/preservation", "/acquisition/method"}
    sparse = document.model_copy(
        update={"entries": tuple(entry for entry in document.entries if entry.path in anchors)}
    )

    assessment = assess_quality_consensus(schema, sparse, loaded)

    assert assessment.status is ConsensusStatus.INDETERMINATE
    assert assessment.reason_code == "quality.insufficient_view_consensus"
    assert assessment.evaluated_views == 0
    assert not hasattr(assessment, "consensus")
    assert not hasattr(assessment, "mean_distance")


def test_semantically_unordered_inputs_and_ambient_decimal_context_cannot_change_result() -> None:
    schema, document = _profile_case()
    loaded = load_packaged_quality_consensus()
    expected = assess_quality_consensus(schema, document, loaded)
    permuted_model = loaded.model.model_copy(
        update={
            "features": tuple(reversed(loaded.model.features)),
            "views": tuple(
                view.model_copy(update={"paths": tuple(reversed(view.paths))})
                for view in reversed(loaded.model.views)
            ),
        }
    )
    permuted_corpus = loaded.corpus.model_copy(
        update={
            "profiles": tuple(
                profile.model_copy(
                    update={"features": dict(reversed(tuple(profile.features.items())))}
                )
                for profile in reversed(loaded.corpus.profiles)
            )
        }
    )
    permuted = LoadedQualityConsensus(
        model=permuted_model,
        corpus=permuted_corpus,
        model_digest=loaded.model_digest,
        corpus_digest=loaded.corpus_digest,
    )
    context = getcontext()
    original = (context.prec, context.rounding)
    try:
        results = []
        for precision, rounding in ((3, ROUND_DOWN), (6, ROUND_UP), (50, ROUND_DOWN)):
            context.prec = precision
            context.rounding = rounding
            results.append(
                assess_quality_consensus(
                    schema.model_copy(update={"fields": tuple(reversed(schema.fields))}),
                    document.model_copy(update={"entries": tuple(reversed(document.entries))}),
                    permuted,
                )
            )
    finally:
        context.prec, context.rounding = original

    assert results == [expected, expected, expected]


def test_view_vote_uses_cluster_medoid_and_abstains_on_cross_cluster_tie() -> None:
    feature = QualityFeature(
        path="/quality/value",
        kind=FeatureKind.NUMERIC,
        minimum=0.0,
        maximum=10.0,
    )
    model = QualityConsensusModel(
        model_id="model.synthetic",
        model_version="1.0.0",
        profile_schema_id="profile.synthetic",
        profile_schema_version="1.0.0",
        canonical_protocol_digest=f"sha256:{'1' * 64}",
        reference_corpus_file="corpus.json",
        reference_corpus_digest=f"sha256:{'2' * 64}",
        minimum_consensus=0.66,
        maximum_mean_distance=1.0,
        minimum_view_coverage=1.0,
        features=(feature,),
        views=tuple(
            QualityView(view_id=f"view{index}", paths=(feature.path,))
            for index in range(3)
        ),
    )
    profiles = tuple(
        ReferenceProfile(
            profile_id=f"a{index}",
            cluster_id="cluster_a",
            features={feature.path: value},
        )
        for index, value in enumerate((0.0, 0.0, 9.0))
    ) + tuple(
        ReferenceProfile(
            profile_id=f"b{index}",
            cluster_id="cluster_b",
            features={feature.path: value},
        )
        for index, value in enumerate((6.0, 6.0, 6.0))
    )
    corpus = QualityReferenceCorpus(
        corpus_id="corpus.synthetic",
        corpus_version="1.0.0",
        description="Synthetic medoid distinction.",
        profiles=profiles,
    )

    # The nearest individual reference to 9 is cluster A, while the true medoids are
    # A=0 and B=6; the engine must therefore choose B.
    assert consensus._view_vote(
        (feature.path,),
        {feature.path: Decimal(9)},
        model,
        corpus,
    ) == ("cluster_b", Decimal("0.3"))

    tied_profiles = (
        ReferenceProfile(
            profile_id="left",
            cluster_id="left",
            features={feature.path: 0.0},
        ),
        ReferenceProfile(
            profile_id="right",
            cluster_id="right",
            features={feature.path: 10.0},
        ),
    )
    tied_corpus = corpus.model_copy(update={"profiles": tied_profiles})
    assert (
        consensus._view_vote(
            (feature.path,),
            {feature.path: Decimal(5)},
            model,
            tied_corpus,
        )
        is None
    )
    assert consensus._view_votes({feature.path: Decimal(5)}, model, tied_corpus) == []
    assert consensus._view_vote(
        (feature.path,),
        {feature.path: Decimal(5)},
        model,
        tied_corpus.model_copy(update={"profiles": ()}),
    ) is None


def test_reference_value_types_and_distance_math_fail_closed() -> None:
    loaded = load_packaged_quality_consensus()
    categorical = next(
        feature for feature in loaded.model.features if feature.kind is FeatureKind.CATEGORICAL
    )
    numeric = next(
        feature for feature in loaded.model.features if feature.kind is FeatureKind.NUMERIC
    )
    numeric_reference = loaded.corpus.profiles[0].features[numeric.path]

    assert consensus._feature_equals(Decimal(10), 10.0)
    assert not consensus._feature_equals(Decimal(10), "10")
    assert consensus._outside_reference_support(
        {categorical.path: "not-in-the-locked-corpus"},
        loaded.model,
        loaded.corpus,
    )
    assert consensus._outside_reference_support(
        {numeric.path: "wrong-runtime-type"},
        loaded.model,
        loaded.corpus,
    )
    for feature, value in (
        (categorical, 1.0),
        (numeric, "not-a-number"),
        (numeric, float("inf")),
        (numeric, cast("float", numeric.maximum) + 1.0),
    ):
        with pytest.raises(QualityConsensusArtifactError):
            consensus._validated_reference_value(feature, value)
    with pytest.raises(QualityConsensusArtifactError):
        consensus._feature_distance(numeric, "wrong-runtime-type", numeric_reference)


def test_feature_extraction_abstains_on_shape_kind_unit_and_range_ambiguity() -> None:
    schema, document = _profile_case()
    loaded = load_packaged_quality_consensus()
    categorical = next(
        feature
        for feature in loaded.model.features
        if feature.path == "/specimen/collection_method"
    )
    numeric = next(
        feature
        for feature in loaded.model.features
        if feature.path == "/specimen/warm_ischemia_time"
    )

    def one_feature_model(feature: QualityFeature) -> QualityConsensusModel:
        return loaded.model.model_copy(update={"features": (feature,)})

    def replace_field(path: str, **updates: object) -> ProtocolSchema:
        return schema.model_copy(
            update={
                "fields": tuple(
                    field.model_copy(update=updates) if field.path == path else field
                    for field in schema.fields
                )
            }
        )

    def replace_entry(path: str, observed: ObservedValue) -> MetadataDocument:
        return document.model_copy(
            update={
                "entries": tuple(
                    entry.model_copy(update={"values": (observed,)})
                    if entry.path == path
                    else entry
                    for entry in document.entries
                )
            }
        )

    without_field = schema.model_copy(
        update={
            "fields": tuple(field for field in schema.fields if field.path != categorical.path)
        }
    )
    assert consensus._extract_features(
        without_field,
        document,
        one_feature_model(categorical),
    ) == {}
    assert consensus._extract_features(
        replace_field(categorical.path, identity_key=True),
        document,
        one_feature_model(categorical),
    ) == {}
    assert consensus._extract_features(
        replace_field(categorical.path, value_kind="text"),
        document,
        one_feature_model(categorical),
    ) == {}
    assert consensus._extract_features(
        schema,
        replace_entry(categorical.path, ObservedValue(value=1.0)),
        one_feature_model(categorical),
    ) == {}
    assert consensus._extract_features(
        replace_field(numeric.path, value_kind="term"),
        document,
        one_feature_model(numeric),
    ) == {}
    assert consensus._extract_features(
        schema,
        replace_entry(numeric.path, ObservedValue(value="not-numeric")),
        one_feature_model(numeric),
    ) == {}

    original = next(entry for entry in document.entries if entry.path == numeric.path).values[0]
    assert isinstance(original, ObservedValue)
    unitless = consensus._extract_features(
        replace_field(numeric.path, reference_unit=None),
        document,
        one_feature_model(numeric),
    )
    assert isinstance(unitless[numeric.path], Decimal)
    assert consensus._extract_features(
        schema,
        replace_entry(numeric.path, ObservedValue(value=original.value)),
        one_feature_model(numeric),
    ) == {}
    assert consensus._extract_features(
        schema,
        replace_entry(numeric.path, ObservedValue(value=original.value, unit="Cel")),
        one_feature_model(numeric),
    ) == {}
    assert consensus._extract_features(
        schema,
        replace_entry(
            numeric.path,
            ObservedValue(value=cast("float", numeric.maximum) + 1.0, unit=original.unit),
        ),
        one_feature_model(numeric),
    ) == {}


def test_anchor_only_views_are_skipped_instead_of_voting_on_identity_proxy() -> None:
    schema, document = _profile_case()
    loaded = load_packaged_quality_consensus()
    values = consensus._extract_features(schema, document, loaded.model)
    anchors = tuple(sorted({"/specimen/preservation", "/acquisition/method"}))
    anchor_views = tuple(
        QualityView(view_id=f"anchor{index}", paths=anchors) for index in range(3)
    )
    anchor_model = loaded.model.model_copy(update={"views": anchor_views})

    assert consensus._view_votes(values, anchor_model, loaded.corpus) == []


def test_unavailable_assessment_contains_no_fabricated_model_identity() -> None:
    assessment = unavailable_quality_assessment()

    assert assessment.status is ConsensusStatus.UNAVAILABLE
    assert assessment.reason_code == "quality.consensus_unavailable"
    assert not hasattr(assessment, "consensus")
    assert not hasattr(assessment, "mean_distance")
    assert assessment.model_id is None
    assert assessment.model_digest is None
    assert assessment.corpus_id is None
    assert assessment.corpus_digest is None
