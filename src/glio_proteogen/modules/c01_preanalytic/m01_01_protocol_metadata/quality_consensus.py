"""Privacy-safe consensus quality assessment for the owned M01-01 profile.

The engine is deliberately narrower than a biological classifier. It compares declared,
non-identifying protocol metadata with a locked synthetic reference corpus and emits only
an aggregate support/abstention signal. Cluster labels, neighbours, feature values, and
per-view votes never cross the module boundary.
"""

from __future__ import annotations

import collections.abc
from collections import Counter
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from enum import StrEnum
from importlib.resources import files
from itertools import combinations
from math import comb
from types import MappingProxyType
from typing import TYPE_CHECKING, Annotated, Final

from pydantic import (
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    field_serializer,
    field_validator,
    model_validator,
)

from glio_proteogen.contracts.m01_01.canonical import protocol_digest
from glio_proteogen.contracts.m01_01.ucum import convert_quantity
from glio_proteogen.contracts.m01_01.v1 import (
    FieldSpecification,
    MetadataDocument,
    ObservedValue,
    ProtocolSchema,
    ValueKind,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    FrozenModel,
    Identifier,
    SemanticVersion,
    Sha256Digest,
)
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

if TYPE_CHECKING:
    from importlib.resources.abc import Traversable

_PROFILE_PACKAGE: Final = "glio_proteogen.profiles.m01_01.v1"
_MODEL_FILE: Final = "quality-model.json"
OWNED_PROFILE_SCHEMA_ID: Final[Identifier] = "glio_preanalytic_proteomics"
OWNED_PROFILE_SCHEMA_VERSION: Final[SemanticVersion] = "1.0.0"
OWNED_PROFILE_PROTOCOL_DIGEST: Final[Sha256Digest] = (
    "sha256:1d07ccd51a014702f612cc6d83cd0d67d1bab2f17fa17de61c4e6beb68572391"
)
OWNED_QUALITY_MODEL_DIGEST: Final[Sha256Digest] = (
    "sha256:c0d8b536f2d162a41fb7ff6d3de9941f7debad31aa15bc39444a993e16ab869b"
)
OWNED_QUALITY_CORPUS_DIGEST: Final[Sha256Digest] = (
    "sha256:9ae807d745cbda935222758a2ce29d0d6855cd6452dd16adf9c694fed6145940"
)
_MAX_MODEL_BYTES: Final = 256 * 1024
_MAX_CORPUS_BYTES: Final = 2 * 1024 * 1024
_MAX_PROTOCOL_BYTES: Final = 512 * 1024
_MAX_FEATURES: Final = 128
_MAX_VIEWS: Final = 32
_MAX_PROFILES: Final = 1_024
_MAX_VIEW_OPERATIONS: Final = 2_000_000
_MAX_COMPILED_VIEW_PLANS: Final = 65_536
_MINIMUM_CLUSTERS: Final = 2
_NUMERIC_SUPPORT_MARGIN: Final = Decimal("0.10")
_DECIMAL_CONTEXT: Final = Context(prec=50, rounding=ROUND_HALF_EVEN)
_FORBIDDEN_PATH_SEGMENTS: Final = frozenset(
    {"identity", "reference", "reference_id", "digest", "patient", "subject"}
)

type _FeatureValue = str | Decimal


class FeatureKind(StrEnum):
    CATEGORICAL = "categorical"
    NUMERIC = "numeric"


class ConsensusStatus(StrEnum):
    IN_DOMAIN = "in_domain"
    OUT_OF_DOMAIN = "out_of_domain"
    INDETERMINATE = "indeterminate"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class QualityFeature(FrozenModel):
    path: Annotated[str, StringConstraints(pattern=r"^(?:/(?:[^~/]|~0|~1)*)+$", max_length=512)]
    kind: FeatureKind
    minimum: float | None = None
    maximum: float | None = None

    @model_validator(mode="after")
    def bounds_match_kind(self) -> QualityFeature:
        if self.kind is FeatureKind.NUMERIC:
            if self.minimum is None or self.maximum is None or self.minimum >= self.maximum:
                raise ValueError("bounds")
        elif self.minimum is not None or self.maximum is not None:
            raise ValueError("bounds")
        return self


class QualityView(FrozenModel):
    view_id: Identifier
    paths: tuple[str, ...] = Field(min_length=1, max_length=_MAX_FEATURES)


class QualityConsensusModel(FrozenModel):
    model_id: Identifier
    model_version: SemanticVersion
    profile_schema_id: Identifier
    profile_schema_version: SemanticVersion
    canonical_protocol_digest: Sha256Digest
    reference_corpus_file: Annotated[
        str,
        StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.json$"),
    ]
    reference_corpus_digest: Sha256Digest
    minimum_consensus: float = Field(gt=0.5, le=1.0)
    maximum_mean_distance: float = Field(ge=0.0, le=1.0)
    minimum_view_coverage: float = Field(gt=0.0, le=1.0)
    features: tuple[QualityFeature, ...] = Field(min_length=1, max_length=_MAX_FEATURES)
    views: tuple[QualityView, ...] = Field(min_length=3, max_length=_MAX_VIEWS)

    @model_validator(mode="after")
    def collections_are_closed(self) -> QualityConsensusModel:
        feature_paths = [feature.path for feature in self.features]
        view_ids = [view.view_id for view in self.views]
        if len(feature_paths) != len(set(feature_paths)):
            raise ValueError("path")
        if len(view_ids) != len(set(view_ids)):
            raise ValueError("view")
        known_paths = set(feature_paths)
        for view in self.views:
            if len(view.paths) != len(set(view.paths)) or not set(view.paths).issubset(known_paths):
                raise ValueError("reference")
        return self


class ReferenceProfile(FrozenModel):
    profile_id: Identifier
    cluster_id: Identifier
    features: collections.abc.Mapping[str, str | int | float] = Field(
        min_length=1,
        max_length=_MAX_FEATURES,
    )

    @field_validator("features")
    @classmethod
    def freeze_features(
        cls,
        features: collections.abc.Mapping[str, str | int | float],
    ) -> collections.abc.Mapping[str, str | int | float]:
        return MappingProxyType(dict(features))

    @field_serializer("features")
    def serialize_features(
        self,
        features: collections.abc.Mapping[str, str | int | float],
    ) -> dict[str, str | int | float]:
        return dict(features)


class QualityReferenceCorpus(FrozenModel):
    corpus_id: Identifier
    corpus_version: SemanticVersion
    description: Annotated[str, StringConstraints(min_length=1, max_length=512)]
    profiles: tuple[ReferenceProfile, ...] = Field(min_length=2, max_length=_MAX_PROFILES)


class QualityConsensusArtifactError(ValueError):
    """A packaged model or reference artifact failed closed validation."""

    def __init__(self) -> None:
        super().__init__("M01-01 quality consensus artifacts are invalid or unavailable")


@dataclass(frozen=True, slots=True)
class LoadedQualityConsensus:
    """Fully checked, immutable model and reference corpus."""

    model: QualityConsensusModel
    corpus: QualityReferenceCorpus
    model_digest: Sha256Digest
    corpus_digest: Sha256Digest
    _runtime: _QualityConsensusRuntime | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )


@dataclass(frozen=True, slots=True)
class _RuntimeFeature:
    path: str
    kind: FeatureKind
    field: FieldSpecification
    minimum: Decimal | None
    maximum: Decimal | None
    width: Decimal | None


@dataclass(frozen=True, slots=True)
class _RuntimeSupport:
    categorical: frozenset[str] | None = None
    minimum: Decimal | None = None
    maximum: Decimal | None = None


@dataclass(frozen=True, slots=True)
class _RuntimeProfile:
    profile_id: str
    cluster_id: str
    values: collections.abc.Mapping[str, _FeatureValue]


@dataclass(frozen=True, slots=True)
class _RuntimeMedoid:
    cluster_id: str
    profile_id: str
    values: tuple[_FeatureValue, ...]


@dataclass(frozen=True, slots=True)
class _RuntimeView:
    paths: tuple[str, ...]
    required_count: int
    medoids_by_available_paths: collections.abc.Mapping[
        tuple[str, ...],
        tuple[_RuntimeMedoid, ...],
    ]


@dataclass(frozen=True, slots=True)
class _QualityConsensusRuntime:
    """Request-independent, deeply immutable execution plan for one locked asset set."""

    protocol: ProtocolSchema
    features: collections.abc.Mapping[str, _RuntimeFeature]
    feature_order: tuple[_RuntimeFeature, ...]
    anchor_paths: tuple[str, ...]
    anchor_clusters: collections.abc.Mapping[tuple[_FeatureValue, ...], str]
    support_by_cluster: collections.abc.Mapping[
        str | None,
        collections.abc.Mapping[str, _RuntimeSupport],
    ]
    views: tuple[_RuntimeView, ...]
    required_votes: int
    minimum_consensus: Decimal
    maximum_mean_distance: Decimal


@dataclass(frozen=True, slots=True)
class QualityConsensusAssessment:
    """Coarse aggregate result safe to merge into a conformance profile."""

    status: ConsensusStatus
    evaluated_views: int
    total_views: int
    model_id: Identifier | None
    model_version: SemanticVersion | None
    model_digest: Sha256Digest | None
    corpus_id: Identifier | None
    corpus_version: SemanticVersion | None
    corpus_digest: Sha256Digest | None
    reason_code: Identifier


@dataclass(frozen=True, slots=True)
class _AssessmentValues:
    evaluated_views: int = 0


_EMPTY_ASSESSMENT_VALUES: Final = _AssessmentValues()


def load_packaged_quality_consensus() -> LoadedQualityConsensus:
    """Load and validate the locked packaged model without runtime network access."""

    try:
        package = files(_PROFILE_PACKAGE)
        model_bytes = _bounded_resource_bytes(package.joinpath(_MODEL_FILE), _MAX_MODEL_BYTES)
        model_value = strict_json_loads(model_bytes, max_bytes=_MAX_MODEL_BYTES)
        model_digest = sha256_digest(model_value)
        if model_digest != OWNED_QUALITY_MODEL_DIGEST:
            raise QualityConsensusArtifactError
        model = TypeAdapter(QualityConsensusModel).validate_json(model_bytes, strict=True)
        protocol_bytes = _bounded_resource_bytes(
            package.joinpath("protocol-schema.json"),
            _MAX_PROTOCOL_BYTES,
        )
        strict_json_loads(protocol_bytes, max_bytes=_MAX_PROTOCOL_BYTES)
        protocol = TypeAdapter(ProtocolSchema).validate_json(protocol_bytes, strict=True)
        if (
            not is_owned_quality_profile(protocol)
            or model.profile_schema_id != OWNED_PROFILE_SCHEMA_ID
            or model.profile_schema_version != OWNED_PROFILE_SCHEMA_VERSION
            or model.canonical_protocol_digest != OWNED_PROFILE_PROTOCOL_DIGEST
            or model.model_id != "glio_preanalytic_quality_consensus"
            or model.model_version != "1.0.0"
            or model.profile_schema_id != protocol.schema_id
            or model.profile_schema_version != protocol.version
            or model.canonical_protocol_digest != protocol_digest(protocol)
        ):
            raise QualityConsensusArtifactError
        corpus_bytes = _bounded_resource_bytes(
            package.joinpath(model.reference_corpus_file),
            _MAX_CORPUS_BYTES,
        )
        corpus_digest = sha256_digest(strict_json_loads(corpus_bytes, max_bytes=_MAX_CORPUS_BYTES))
        if corpus_digest != model.reference_corpus_digest:
            raise QualityConsensusArtifactError
        if corpus_digest != OWNED_QUALITY_CORPUS_DIGEST:
            raise QualityConsensusArtifactError
        corpus = TypeAdapter(QualityReferenceCorpus).validate_json(corpus_bytes, strict=True)
        loaded = LoadedQualityConsensus(
            model=model,
            corpus=corpus,
            model_digest=model_digest,
            corpus_digest=corpus_digest,
        )
        _validate_loaded_quality_consensus(loaded)
        runtime = _compile_quality_consensus_runtime(loaded, protocol)
        object.__setattr__(loaded, "_runtime", runtime)
    except (
        FileNotFoundError,
        OSError,
        StrictJsonError,
        ValidationError,
        TypeError,
        ValueError,
    ) as error:
        if isinstance(error, QualityConsensusArtifactError):
            raise
        raise QualityConsensusArtifactError from error
    return loaded


def _bounded_resource_bytes(resource: Traversable, maximum: int) -> bytes:
    with resource.open("rb") as stream:
        payload = stream.read(maximum + 1)
    if len(payload) > maximum:
        raise QualityConsensusArtifactError
    return bytes(payload)


def assess_quality_consensus(
    schema: ProtocolSchema,
    document: MetadataDocument,
    loaded: LoadedQualityConsensus,
) -> QualityConsensusAssessment:
    """Assess metadata support with deterministic multi-view nearest-medoid consensus."""

    model = loaded.model
    runtime = loaded._runtime
    if not _schema_matches_quality_runtime(schema, model, runtime):
        return _assessment(ConsensusStatus.NOT_APPLICABLE, loaded, reason="quality.not_applicable")

    if runtime is not None:
        return _assess_with_runtime(document, loaded, runtime)

    values = _extract_features(schema, document, model)
    if _outside_reference_support(values, model, loaded.corpus):
        return _assessment(
            ConsensusStatus.OUT_OF_DOMAIN,
            loaded,
            reason="quality.novel_or_ood",
            values=_EMPTY_ASSESSMENT_VALUES,
        )
    anchor_cluster = _anchor_cluster(values, model, loaded.corpus)
    if anchor_cluster is None:
        return _assessment(
            ConsensusStatus.INDETERMINATE,
            loaded,
            reason="quality.anchor_indeterminate",
            values=_EMPTY_ASSESSMENT_VALUES,
        )
    with localcontext(_DECIMAL_CONTEXT):
        votes = _view_votes(values, model, loaded.corpus)

    required_votes = _minimum_coverage_count(len(model.views), model.minimum_consensus)
    if len(votes) < required_votes:
        return _assessment(
            ConsensusStatus.INDETERMINATE,
            loaded,
            reason="quality.insufficient_view_consensus",
            values=_AssessmentValues(evaluated_views=len(votes)),
        )
    counts = Counter(cluster for cluster, _distance in votes)
    winning_count = max(counts.values())
    winning_clusters = sorted(
        cluster for cluster, count in counts.items() if count == winning_count
    )
    with localcontext(_DECIMAL_CONTEXT):
        consensus = Decimal(winning_count) / Decimal(len(model.views))
        mean_distance = sum(
            (distance for _cluster, distance in votes),
            start=Decimal(0),
        ) / Decimal(len(votes))
    if (
        len(winning_clusters) != 1
        or winning_clusters[0] != anchor_cluster
        or consensus < Decimal(str(model.minimum_consensus))
        or mean_distance > Decimal(str(model.maximum_mean_distance))
    ):
        status = ConsensusStatus.OUT_OF_DOMAIN
        reason = "quality.novel_or_ood"
    else:
        status = ConsensusStatus.IN_DOMAIN
        reason = "quality.consensus_supported"
    return _assessment(
        status,
        loaded,
        reason=reason,
        values=_AssessmentValues(
            evaluated_views=len(votes),
        ),
    )


def is_owned_quality_profile(schema: ProtocolSchema) -> bool:
    """Return whether a protocol exactly identifies the packaged reference-domain profile."""

    return (
        schema.schema_id == OWNED_PROFILE_SCHEMA_ID
        and schema.version == OWNED_PROFILE_SCHEMA_VERSION
        and protocol_digest(schema) == OWNED_PROFILE_PROTOCOL_DIGEST
    )


def _schema_matches_quality_runtime(
    schema: ProtocolSchema,
    model: QualityConsensusModel,
    runtime: _QualityConsensusRuntime | None,
) -> bool:
    return (
        schema.schema_id == model.profile_schema_id
        and schema.version == model.profile_schema_version
        and (
            (runtime is not None and schema == runtime.protocol)
            or protocol_digest(schema) == model.canonical_protocol_digest
        )
    )


def _compile_quality_consensus_runtime(
    loaded: LoadedQualityConsensus,
    protocol: ProtocolSchema,
) -> _QualityConsensusRuntime:
    model = loaded.model
    fields = {field.path: field for field in protocol.fields}
    features: dict[str, _RuntimeFeature] = {}
    for feature in model.features:
        field = fields.get(feature.path)
        if field is None or field.identity_key or _path_is_sensitive(feature.path):
            raise QualityConsensusArtifactError
        minimum = (
            Decimal(str(feature.minimum)) if feature.minimum is not None else None
        )
        maximum = (
            Decimal(str(feature.maximum)) if feature.maximum is not None else None
        )
        features[feature.path] = _RuntimeFeature(
            path=feature.path,
            kind=feature.kind,
            field=field,
            minimum=minimum,
            maximum=maximum,
            width=(maximum - minimum) if minimum is not None and maximum is not None else None,
        )
    frozen_features = MappingProxyType(features)
    profiles = tuple(
        _RuntimeProfile(
            profile_id=profile.profile_id,
            cluster_id=profile.cluster_id,
            values=MappingProxyType(
                {
                    path: _validated_runtime_reference(features[path], value)
                    for path, value in profile.features.items()
                }
            ),
        )
        for profile in loaded.corpus.profiles
    )
    profiles_by_cluster = _runtime_profiles_by_cluster(profiles)
    anchor_paths = tuple(sorted(_anchor_paths(model)))
    anchor_clusters = _compile_anchor_clusters(anchor_paths, profiles)
    support_by_cluster = _compile_support_envelopes(
        features,
        profiles,
        profiles_by_cluster,
    )
    plan_count = sum(
        _runtime_view_plan_count(view, model, anchor_paths) for view in model.views
    )
    if plan_count > _MAX_COMPILED_VIEW_PLANS:
        raise QualityConsensusArtifactError
    views = tuple(
        _compile_runtime_view(view, model, features, profiles_by_cluster, anchor_paths)
        for view in sorted(model.views, key=lambda item: item.view_id)
    )
    return _QualityConsensusRuntime(
        protocol=protocol,
        features=frozen_features,
        feature_order=tuple(features[feature.path] for feature in model.features),
        anchor_paths=anchor_paths,
        anchor_clusters=MappingProxyType(anchor_clusters),
        support_by_cluster=MappingProxyType(support_by_cluster),
        views=views,
        required_votes=_minimum_coverage_count(len(model.views), model.minimum_consensus),
        minimum_consensus=Decimal(str(model.minimum_consensus)),
        maximum_mean_distance=Decimal(str(model.maximum_mean_distance)),
    )


def _runtime_view_plan_count(
    view: QualityView,
    model: QualityConsensusModel,
    anchor_paths: tuple[str, ...],
) -> int:
    anchors = frozenset(anchor_paths)
    non_anchor_count = sum(path not in anchors for path in view.paths)
    anchor_count = len(view.paths) - non_anchor_count
    required_count = _minimum_coverage_count(len(view.paths), model.minimum_view_coverage)
    minimum_non_anchor_count = max(1, required_count - anchor_count)
    return sum(
        comb(non_anchor_count, size)
        for size in range(minimum_non_anchor_count, non_anchor_count + 1)
    )


def _validated_runtime_reference(
    feature: _RuntimeFeature,
    value: str | float,
) -> _FeatureValue:
    if feature.kind is FeatureKind.CATEGORICAL:
        if type(value) is not str:
            raise QualityConsensusArtifactError
        return value
    if type(value) not in {int, float}:
        raise QualityConsensusArtifactError
    decimal_value = Decimal(str(value))
    if (
        not decimal_value.is_finite()
        or feature.minimum is None
        or feature.maximum is None
        or not feature.minimum <= decimal_value <= feature.maximum
    ):
        raise QualityConsensusArtifactError
    return decimal_value


def _runtime_profiles_by_cluster(
    profiles: tuple[_RuntimeProfile, ...],
) -> dict[str, tuple[_RuntimeProfile, ...]]:
    grouped: dict[str, list[_RuntimeProfile]] = {}
    for profile in profiles:
        grouped.setdefault(profile.cluster_id, []).append(profile)
    return {cluster: tuple(grouped[cluster]) for cluster in sorted(grouped)}


def _compile_anchor_clusters(
    anchor_paths: tuple[str, ...],
    profiles: tuple[_RuntimeProfile, ...],
) -> dict[tuple[_FeatureValue, ...], str]:
    candidates: dict[tuple[_FeatureValue, ...], set[str]] = {}
    for profile in profiles:
        key = tuple(profile.values[path] for path in anchor_paths)
        candidates.setdefault(key, set()).add(profile.cluster_id)
    return {
        key: next(iter(clusters))
        for key, clusters in candidates.items()
        if len(clusters) == 1
    }


def _compile_support_envelopes(
    features: dict[str, _RuntimeFeature],
    profiles: tuple[_RuntimeProfile, ...],
    profiles_by_cluster: dict[str, tuple[_RuntimeProfile, ...]],
) -> dict[str | None, collections.abc.Mapping[str, _RuntimeSupport]]:
    grouped: dict[str | None, tuple[_RuntimeProfile, ...]] = {None: profiles}
    grouped.update(profiles_by_cluster)
    return {
        cluster: MappingProxyType(
            {
                path: _runtime_support(feature, members)
                for path, feature in features.items()
            }
        )
        for cluster, members in grouped.items()
    }


def _runtime_support(
    feature: _RuntimeFeature,
    profiles: tuple[_RuntimeProfile, ...],
) -> _RuntimeSupport:
    references = tuple(profile.values[feature.path] for profile in profiles)
    if feature.kind is FeatureKind.CATEGORICAL:
        if any(type(reference) is not str for reference in references):
            raise QualityConsensusArtifactError
        return _RuntimeSupport(
            categorical=frozenset(
                reference for reference in references if isinstance(reference, str)
            )
        )
    if any(not isinstance(reference, Decimal) for reference in references):
        raise QualityConsensusArtifactError
    numeric = tuple(reference for reference in references if isinstance(reference, Decimal))
    if feature.width is None:
        raise QualityConsensusArtifactError
    corpus_minimum = min(numeric)
    corpus_maximum = max(numeric)
    margin = max(
        (corpus_maximum - corpus_minimum) * _NUMERIC_SUPPORT_MARGIN,
        feature.width / 100,
    )
    return _RuntimeSupport(
        minimum=corpus_minimum - margin,
        maximum=corpus_maximum + margin,
    )


def _compile_runtime_view(
    view: QualityView,
    model: QualityConsensusModel,
    features: dict[str, _RuntimeFeature],
    profiles_by_cluster: dict[str, tuple[_RuntimeProfile, ...]],
    anchor_paths: tuple[str, ...],
) -> _RuntimeView:
    ordered_paths = tuple(sorted(view.paths))
    anchors = frozenset(anchor_paths)
    non_anchor_paths = tuple(path for path in ordered_paths if path not in anchors)
    required_count = _minimum_coverage_count(len(view.paths), model.minimum_view_coverage)
    anchor_count = len(view.paths) - len(non_anchor_paths)
    medoids: dict[tuple[str, ...], tuple[_RuntimeMedoid, ...]] = {}
    minimum_non_anchor_count = max(1, required_count - anchor_count)
    for size in range(minimum_non_anchor_count, len(non_anchor_paths) + 1):
        for available_paths in combinations(non_anchor_paths, size):
            medoids[available_paths] = tuple(
                _runtime_cluster_medoid(available_paths, features, cluster, profiles)
                for cluster, profiles in profiles_by_cluster.items()
            )
    return _RuntimeView(
        paths=ordered_paths,
        required_count=required_count,
        medoids_by_available_paths=MappingProxyType(medoids),
    )


def _runtime_cluster_medoid(
    paths: tuple[str, ...],
    features: dict[str, _RuntimeFeature],
    cluster: str,
    members: tuple[_RuntimeProfile, ...],
) -> _RuntimeMedoid:
    candidates: list[tuple[Decimal, str, _RuntimeProfile]] = []
    for candidate in members:
        total = sum(
            (
                _runtime_profile_distance(paths, features, candidate.values, member.values)
                for member in members
            ),
            start=Decimal(0),
        )
        candidates.append((total, candidate.profile_id, candidate))
    candidates.sort(key=lambda item: (item[0], item[1]))
    winner = candidates[0][2]
    return _RuntimeMedoid(
        cluster_id=cluster,
        profile_id=winner.profile_id,
        values=tuple(winner.values[path] for path in paths),
    )


def _runtime_profile_distance(
    paths: tuple[str, ...],
    features: collections.abc.Mapping[str, _RuntimeFeature],
    values: collections.abc.Mapping[str, _FeatureValue],
    reference: collections.abc.Mapping[str, _FeatureValue],
) -> Decimal:
    return sum(
        (
            _runtime_feature_distance(features[path], values[path], reference[path])
            for path in paths
        ),
        start=Decimal(0),
    ) / Decimal(len(paths))


def _runtime_feature_distance(
    feature: _RuntimeFeature,
    observed: _FeatureValue,
    expected: _FeatureValue,
) -> Decimal:
    if feature.kind is FeatureKind.CATEGORICAL:
        return Decimal(0 if observed == expected else 1)
    if (
        not isinstance(observed, Decimal)
        or not isinstance(expected, Decimal)
        or feature.width is None
    ):
        raise QualityConsensusArtifactError
    return min(Decimal(1), abs(observed - expected) / feature.width)


def _assess_with_runtime(
    document: MetadataDocument,
    loaded: LoadedQualityConsensus,
    runtime: _QualityConsensusRuntime,
) -> QualityConsensusAssessment:
    values = _runtime_extract_features(document, runtime)
    anchor_cluster = _runtime_anchor_cluster(values, runtime)
    support = runtime.support_by_cluster[anchor_cluster]
    if _runtime_outside_reference_support(values, runtime, support):
        return _assessment(
            ConsensusStatus.OUT_OF_DOMAIN,
            loaded,
            reason="quality.novel_or_ood",
        )
    if anchor_cluster is None:
        return _assessment(
            ConsensusStatus.INDETERMINATE,
            loaded,
            reason="quality.anchor_indeterminate",
        )
    with localcontext(_DECIMAL_CONTEXT):
        votes = _runtime_view_votes(values, runtime)
    if len(votes) < runtime.required_votes:
        return _assessment(
            ConsensusStatus.INDETERMINATE,
            loaded,
            reason="quality.insufficient_view_consensus",
            values=_AssessmentValues(evaluated_views=len(votes)),
        )
    counts = Counter(cluster for cluster, _distance in votes)
    winning_count = max(counts.values())
    winning_clusters = sorted(
        cluster for cluster, count in counts.items() if count == winning_count
    )
    with localcontext(_DECIMAL_CONTEXT):
        consensus = Decimal(winning_count) / Decimal(len(runtime.views))
        mean_distance = sum(
            (distance for _cluster, distance in votes),
            start=Decimal(0),
        ) / Decimal(len(votes))
    if (
        len(winning_clusters) != 1
        or winning_clusters[0] != anchor_cluster
        or consensus < runtime.minimum_consensus
        or mean_distance > runtime.maximum_mean_distance
    ):
        status = ConsensusStatus.OUT_OF_DOMAIN
        reason = "quality.novel_or_ood"
    else:
        status = ConsensusStatus.IN_DOMAIN
        reason = "quality.consensus_supported"
    return _assessment(
        status,
        loaded,
        reason=reason,
        values=_AssessmentValues(evaluated_views=len(votes)),
    )


def _runtime_extract_features(  # noqa: C901 - extraction stays explicit and fail closed.
    document: MetadataDocument,
    runtime: _QualityConsensusRuntime,
) -> dict[str, _FeatureValue]:
    entries = {entry.path: entry for entry in document.entries}
    extracted: dict[str, _FeatureValue] = {}
    for feature in runtime.feature_order:
        entry = entries.get(feature.path)
        if (
            entry is None
            or len(entry.values) != 1
            or not isinstance(entry.values[0], ObservedValue)
        ):
            continue
        observed = entry.values[0]
        field = feature.field
        if feature.kind is FeatureKind.CATEGORICAL:
            if field.value_kind is ValueKind.TERM and type(observed.value) is str:
                extracted[feature.path] = observed.value
            continue
        if field.value_kind not in {ValueKind.INTEGER, ValueKind.NUMBER}:
            continue
        value = observed.value
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        if field.reference_unit is None:
            numeric = Decimal(str(value))
        elif observed.unit is None:
            continue
        else:
            try:
                numeric = convert_quantity(
                    value,
                    source=observed.unit,
                    target=field.reference_unit,
                )
            except ValueError:
                continue
        if (
            numeric.is_finite()
            and feature.minimum is not None
            and feature.maximum is not None
            and feature.minimum <= numeric <= feature.maximum
        ):
            extracted[feature.path] = numeric
    return extracted


def _runtime_anchor_cluster(
    values: dict[str, _FeatureValue],
    runtime: _QualityConsensusRuntime,
) -> str | None:
    if not runtime.anchor_paths or any(path not in values for path in runtime.anchor_paths):
        return None
    return runtime.anchor_clusters.get(tuple(values[path] for path in runtime.anchor_paths))


def _runtime_outside_reference_support(
    values: dict[str, _FeatureValue],
    runtime: _QualityConsensusRuntime,
    support: collections.abc.Mapping[str, _RuntimeSupport],
) -> bool:
    for path, observed in values.items():
        feature = runtime.features[path]
        envelope = support[path]
        if feature.kind is FeatureKind.CATEGORICAL:
            if envelope.categorical is None or observed not in envelope.categorical:
                return True
            continue
        if (
            not isinstance(observed, Decimal)
            or envelope.minimum is None
            or envelope.maximum is None
            or observed < envelope.minimum
            or observed > envelope.maximum
        ):
            return True
    return False


def _runtime_view_votes(
    values: dict[str, _FeatureValue],
    runtime: _QualityConsensusRuntime,
) -> list[tuple[str, Decimal]]:
    votes: list[tuple[str, Decimal]] = []
    anchors = frozenset(runtime.anchor_paths)
    for view in runtime.views:
        available_paths = tuple(path for path in view.paths if path in values)
        if len(available_paths) < view.required_count:
            continue
        non_anchor_paths = tuple(path for path in available_paths if path not in anchors)
        medoids = view.medoids_by_available_paths.get(non_anchor_paths)
        if medoids is None:
            continue
        distances = sorted(
            (
                _runtime_observation_distance(non_anchor_paths, values, medoid, runtime),
                medoid.cluster_id,
                medoid.profile_id,
            )
            for medoid in medoids
        )
        nearest_distance = distances[0][0]
        nearest_clusters = {
            cluster for distance, cluster, _profile in distances if distance == nearest_distance
        }
        if len(nearest_clusters) == 1:
            votes.append((next(iter(nearest_clusters)), nearest_distance))
    return votes


def _runtime_observation_distance(
    paths: tuple[str, ...],
    values: dict[str, _FeatureValue],
    medoid: _RuntimeMedoid,
    runtime: _QualityConsensusRuntime,
) -> Decimal:
    return sum(
        (
            _runtime_feature_distance(runtime.features[path], values[path], expected)
            for path, expected in zip(paths, medoid.values, strict=True)
        ),
        start=Decimal(0),
    ) / Decimal(len(paths))


def _view_votes(
    values: dict[str, _FeatureValue],
    model: QualityConsensusModel,
    corpus: QualityReferenceCorpus,
) -> list[tuple[str, Decimal]]:
    votes: list[tuple[str, Decimal]] = []
    anchors = _anchor_paths(model)
    for view in sorted(model.views, key=lambda item: item.view_id):
        required_count = _minimum_coverage_count(len(view.paths), model.minimum_view_coverage)
        available_paths = tuple(path for path in sorted(view.paths) if path in values)
        if len(available_paths) < required_count:
            continue
        non_anchor_paths = tuple(path for path in available_paths if path not in anchors)
        if not non_anchor_paths:
            continue
        vote = _view_vote(non_anchor_paths, values, model, corpus)
        if vote is not None:
            votes.append(vote)
    return votes


def unavailable_quality_assessment() -> QualityConsensusAssessment:
    """Return the mandatory quarantine-first fallback for unusable model artifacts."""

    return QualityConsensusAssessment(
        status=ConsensusStatus.UNAVAILABLE,
        evaluated_views=0,
        total_views=0,
        model_id=None,
        model_version=None,
        model_digest=None,
        corpus_id=None,
        corpus_version=None,
        corpus_digest=None,
        reason_code="quality.consensus_unavailable",
    )


def not_applicable_quality_assessment() -> QualityConsensusAssessment:
    """Return an empty assessment for protocols outside the owned reference profile."""

    return QualityConsensusAssessment(
        status=ConsensusStatus.NOT_APPLICABLE,
        evaluated_views=0,
        total_views=0,
        model_id=None,
        model_version=None,
        model_digest=None,
        corpus_id=None,
        corpus_version=None,
        corpus_digest=None,
        reason_code="quality.not_applicable",
    )


def _assessment(
    status: ConsensusStatus,
    loaded: LoadedQualityConsensus,
    *,
    reason: Identifier,
    values: _AssessmentValues = _EMPTY_ASSESSMENT_VALUES,
) -> QualityConsensusAssessment:
    return QualityConsensusAssessment(
        status=status,
        evaluated_views=values.evaluated_views,
        total_views=len(loaded.model.views),
        model_id=loaded.model.model_id,
        model_version=loaded.model.model_version,
        model_digest=loaded.model_digest,
        corpus_id=loaded.corpus.corpus_id,
        corpus_version=loaded.corpus.corpus_version,
        corpus_digest=loaded.corpus_digest,
        reason_code=reason,
    )


def _validate_loaded_quality_consensus(  # noqa: C901 - one closed artifact audit.
    loaded: LoadedQualityConsensus,
) -> None:
    model = loaded.model
    features = {feature.path: feature for feature in model.features}
    if any(_path_is_sensitive(path) for path in features):
        raise QualityConsensusArtifactError
    expected_paths = set(features)
    profile_ids = [profile.profile_id for profile in loaded.corpus.profiles]
    clusters = {profile.cluster_id for profile in loaded.corpus.profiles}
    if len(profile_ids) != len(set(profile_ids)) or len(clusters) < _MINIMUM_CLUSTERS:
        raise QualityConsensusArtifactError
    cluster_sizes = Counter(profile.cluster_id for profile in loaded.corpus.profiles)
    pair_count = sum(size * size for size in cluster_sizes.values())
    cluster_count = len(cluster_sizes)
    profile_count = len(loaded.corpus.profiles)
    path_count = sum(len(view.paths) for view in model.views)
    operations = path_count * pair_count + len(model.views) * cluster_count * profile_count
    if operations > _MAX_VIEW_OPERATIONS:
        raise QualityConsensusArtifactError
    for profile in loaded.corpus.profiles:
        if set(profile.features) != expected_paths:
            raise QualityConsensusArtifactError
        for path, value in profile.features.items():
            _validated_reference_value(features[path], value)
    for view in model.views:
        runtime_paths = tuple(
            path for path in sorted(view.paths) if path not in _anchor_paths(model)
        )
        if not runtime_paths:
            raise QualityConsensusArtifactError
        medoids: dict[str, ReferenceProfile] = {}
        for cluster, profiles in _profiles_by_cluster(loaded.corpus).items():
            medoids[cluster] = _cluster_medoid(runtime_paths, features, profiles)
        for cluster, medoid in medoids.items():
            values = {
                path: _validated_reference_value(features[path], medoid.features[path])
                for path in runtime_paths
            }
            if _view_vote(runtime_paths, values, model, loaded.corpus) != (
                cluster,
                Decimal(0),
            ):
                raise QualityConsensusArtifactError


def _path_is_sensitive(path: str) -> bool:
    segments = {segment.lower() for segment in path.split("/") if segment}
    return bool(segments & _FORBIDDEN_PATH_SEGMENTS) or any(
        segment.endswith(("_digest", "_reference")) for segment in segments
    )


def _anchor_paths(model: QualityConsensusModel) -> frozenset[str]:
    preferred = frozenset({"/specimen/preservation", "/acquisition/method"})
    declared = {feature.path for feature in model.features}
    return preferred if preferred.issubset(declared) else frozenset()


def _anchor_cluster(
    values: dict[str, _FeatureValue],
    model: QualityConsensusModel,
    corpus: QualityReferenceCorpus,
) -> str | None:
    paths = _anchor_paths(model)
    if not paths or not paths.issubset(values):
        return None
    clusters = {
        profile.cluster_id
        for profile in corpus.profiles
        if all(_feature_equals(values[path], profile.features[path]) for path in paths)
    }
    return next(iter(clusters)) if len(clusters) == 1 else None


def _feature_equals(observed: _FeatureValue, reference: str | float) -> bool:
    if isinstance(observed, Decimal):
        return type(reference) in {int, float} and observed == Decimal(str(reference))
    return observed == reference


def _outside_reference_support(
    values: dict[str, _FeatureValue],
    model: QualityConsensusModel,
    corpus: QualityReferenceCorpus,
) -> bool:
    features = {feature.path: feature for feature in model.features}
    anchor_cluster = _anchor_cluster(values, model, corpus)
    support_profiles = (
        [profile for profile in corpus.profiles if profile.cluster_id == anchor_cluster]
        if anchor_cluster is not None
        else list(corpus.profiles)
    )
    for path, observed in values.items():
        feature = features[path]
        references = [
            _validated_reference_value(feature, profile.features[path])
            for profile in support_profiles
        ]
        if feature.kind is FeatureKind.CATEGORICAL:
            if observed not in references:
                return True
            continue
        if not isinstance(observed, Decimal) or any(
            not isinstance(reference, Decimal) for reference in references
        ):
            return True
        numeric_references = [
            reference for reference in references if isinstance(reference, Decimal)
        ]
        feature_width = Decimal(str(feature.maximum)) - Decimal(str(feature.minimum))
        corpus_minimum = min(numeric_references)
        corpus_maximum = max(numeric_references)
        margin = max(
            (corpus_maximum - corpus_minimum) * _NUMERIC_SUPPORT_MARGIN,
            feature_width / 100,
        )
        if observed < corpus_minimum - margin or observed > corpus_maximum + margin:
            return True
    return False


def _validated_reference_value(feature: QualityFeature, value: str | float) -> _FeatureValue:
    if feature.kind is FeatureKind.CATEGORICAL:
        if type(value) is not str:
            raise QualityConsensusArtifactError
        return value
    if type(value) not in {int, float}:
        raise QualityConsensusArtifactError
    decimal_value = Decimal(str(value))
    minimum = Decimal(str(feature.minimum))
    maximum = Decimal(str(feature.maximum))
    if not decimal_value.is_finite() or not minimum <= decimal_value <= maximum:
        raise QualityConsensusArtifactError
    return decimal_value


def _extract_features(  # noqa: C901, PLR0912 - extraction stays explicit and fail closed.
    schema: ProtocolSchema,
    document: MetadataDocument,
    model: QualityConsensusModel,
) -> dict[str, _FeatureValue]:
    fields = {field.path: field for field in schema.fields}
    entries = {entry.path: entry for entry in document.entries}
    extracted: dict[str, _FeatureValue] = {}
    for feature in model.features:
        field = fields.get(feature.path)
        if field is None or field.identity_key or _path_is_sensitive(feature.path):
            continue
        entry = entries.get(feature.path)
        if (
            entry is None
            or len(entry.values) != 1
            or not isinstance(entry.values[0], ObservedValue)
        ):
            continue
        observed = entry.values[0]
        if feature.kind is FeatureKind.CATEGORICAL:
            if field.value_kind is not ValueKind.TERM or type(observed.value) is not str:
                continue
            extracted[feature.path] = observed.value
            continue
        if field.value_kind not in {ValueKind.INTEGER, ValueKind.NUMBER}:
            continue
        value = observed.value
        if type(value) not in {int, float}:
            continue
        numeric_value = value
        if not isinstance(numeric_value, (int, float)) or isinstance(numeric_value, bool):
            continue
        reference_unit = field.reference_unit
        if reference_unit is None:
            numeric = Decimal(str(numeric_value))
        elif observed.unit is None:
            continue
        else:
            try:
                numeric = convert_quantity(
                    numeric_value,
                    source=observed.unit,
                    target=reference_unit,
                )
            except ValueError:
                continue
        minimum = Decimal(str(feature.minimum))
        maximum = Decimal(str(feature.maximum))
        if numeric.is_finite() and minimum <= numeric <= maximum:
            extracted[feature.path] = numeric
    return extracted


def _minimum_coverage_count(size: int, coverage: float) -> int:
    required = Decimal(size) * Decimal(str(coverage))
    return int(required.to_integral_value(rounding="ROUND_CEILING"))


def _view_vote(
    paths: tuple[str, ...],
    values: dict[str, _FeatureValue],
    model: QualityConsensusModel,
    corpus: QualityReferenceCorpus,
) -> tuple[str, Decimal] | None:
    features = {feature.path: feature for feature in model.features}
    distances: list[tuple[Decimal, str, str]] = []
    for cluster, members in _profiles_by_cluster(corpus).items():
        medoid = _cluster_medoid(paths, features, members)
        distance = _profile_distance(paths, features, values, medoid)
        distances.append((distance, cluster, medoid.profile_id))
    distances.sort()
    if not distances:
        return None
    nearest_distance = distances[0][0]
    nearest_clusters = {
        cluster
        for distance, cluster, _profile in distances
        if distance == nearest_distance
    }
    if len(nearest_clusters) != 1:
        return None
    return next(iter(nearest_clusters)), nearest_distance


def _profiles_by_cluster(
    corpus: QualityReferenceCorpus,
) -> dict[str, tuple[ReferenceProfile, ...]]:
    grouped: dict[str, list[ReferenceProfile]] = {}
    for profile in corpus.profiles:
        grouped.setdefault(profile.cluster_id, []).append(profile)
    return {cluster: tuple(grouped[cluster]) for cluster in sorted(grouped)}


def _cluster_medoid(
    paths: tuple[str, ...],
    features: dict[str, QualityFeature],
    members: tuple[ReferenceProfile, ...],
) -> ReferenceProfile:
    candidates: list[tuple[Decimal, str, ReferenceProfile]] = []
    for candidate in members:
        candidate_values = {
            path: _validated_reference_value(features[path], candidate.features[path])
            for path in paths
        }
        total = sum(
            (
                _profile_distance(paths, features, candidate_values, member)
                for member in members
            ),
            start=Decimal(0),
        )
        candidates.append((total, candidate.profile_id, candidate))
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def _profile_distance(
    paths: tuple[str, ...],
    features: dict[str, QualityFeature],
    values: dict[str, _FeatureValue],
    reference: ReferenceProfile,
) -> Decimal:
    return sum(
        (
            _feature_distance(features[path], values[path], reference.features[path])
            for path in paths
        ),
        start=Decimal(0),
    ) / Decimal(len(paths))


def _feature_distance(
    feature: QualityFeature,
    observed: _FeatureValue,
    reference: str | float,
) -> Decimal:
    expected = _validated_reference_value(feature, reference)
    if feature.kind is FeatureKind.CATEGORICAL:
        return Decimal(0 if observed == expected else 1)
    if not isinstance(observed, Decimal) or not isinstance(expected, Decimal):
        raise QualityConsensusArtifactError
    width = Decimal(str(feature.maximum)) - Decimal(str(feature.minimum))
    return min(Decimal(1), abs(observed - expected) / width)


__all__ = [
    "OWNED_PROFILE_PROTOCOL_DIGEST",
    "OWNED_PROFILE_SCHEMA_ID",
    "OWNED_PROFILE_SCHEMA_VERSION",
    "OWNED_QUALITY_CORPUS_DIGEST",
    "OWNED_QUALITY_MODEL_DIGEST",
    "ConsensusStatus",
    "FeatureKind",
    "LoadedQualityConsensus",
    "QualityConsensusArtifactError",
    "QualityConsensusAssessment",
    "QualityConsensusModel",
    "QualityReferenceCorpus",
    "assess_quality_consensus",
    "is_owned_quality_profile",
    "load_packaged_quality_consensus",
    "not_applicable_quality_assessment",
    "unavailable_quality_assessment",
]
