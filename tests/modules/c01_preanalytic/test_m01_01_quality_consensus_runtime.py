"""Equivalence and safety evidence for the immutable consensus execution plan."""

from __future__ import annotations

from importlib.resources import files
from typing import cast

import pytest
from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_01.v1 import (
    MetadataDocument,
    ObservedValue,
    ProtocolSchema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata import (
    quality_consensus as consensus,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.quality_consensus import (
    LoadedQualityConsensus,
    QualityConsensusArtifactError,
    assess_quality_consensus,
    load_packaged_quality_consensus,
)

_PROFILE_PACKAGE = "glio_proteogen.profiles.m01_01.v1"
_REPEATED_REQUEST_COUNT = 2

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
        observed = entry.values[0]
        assert isinstance(observed, ObservedValue)
        entries.append(
            entry.model_copy(
                update={"values": (ObservedValue(value=value, unit=observed.unit),)}
            )
        )
    return document.model_copy(update={"entries": tuple(entries)})


def test_compiled_runtime_matches_reference_algorithm_across_closed_outcomes() -> None:
    schema, document = _profile_case()
    loaded = load_packaged_quality_consensus()
    reference = LoadedQualityConsensus(
        model=loaded.model,
        corpus=loaded.corpus,
        model_digest=loaded.model_digest,
        corpus_digest=loaded.corpus_digest,
    )
    anchors = {"/specimen/preservation", "/acquisition/method"}
    variants = (
        (schema, document),
        (schema, _replace_observed(document, "/specimen/warm_ischemia_time", 1440.0)),
        (
            schema,
            document.model_copy(
                update={
                    "entries": tuple(
                        entry for entry in document.entries if entry.path not in anchors
                    )
                }
            ),
        ),
        (
            schema,
            document.model_copy(
                update={
                    "entries": tuple(
                        entry for entry in document.entries if entry.path in anchors
                    )
                }
            ),
        ),
        (
            schema.model_copy(update={"fields": tuple(reversed(schema.fields))}),
            document.model_copy(update={"entries": tuple(reversed(document.entries))}),
        ),
        (schema.model_copy(update={"schema_id": "profile.unrelated"}), document),
    )

    for candidate_schema, candidate_document in variants:
        assert assess_quality_consensus(
            candidate_schema,
            candidate_document,
            loaded,
        ) == assess_quality_consensus(candidate_schema, candidate_document, reference)


def test_runtime_is_deeply_immutable_and_does_not_cache_request_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema, document = _profile_case()
    loaded = load_packaged_quality_consensus()
    runtime = loaded._runtime
    assert runtime is not None
    path = next(iter(runtime.features))
    mutable_features = cast("dict[str, object]", runtime.features)
    first_view_plans = cast(
        "dict[tuple[str, ...], object]",
        runtime.views[0].medoids_by_available_paths,
    )
    available_paths = next(iter(first_view_plans))

    with pytest.raises(TypeError):
        mutable_features[path] = object()
    with pytest.raises(TypeError):
        first_view_plans[available_paths] = object()

    calls = 0
    extract = consensus._runtime_extract_features

    def counted_extract(
        candidate: MetadataDocument,
        candidate_runtime: consensus._QualityConsensusRuntime,
    ) -> dict[str, consensus._FeatureValue]:
        nonlocal calls
        calls += 1
        return extract(candidate, candidate_runtime)

    monkeypatch.setattr(consensus, "_runtime_extract_features", counted_extract)
    first = assess_quality_consensus(schema, document, loaded)
    second = assess_quality_consensus(schema, document, loaded)

    assert first == second
    assert calls == _REPEATED_REQUEST_COUNT
    assert loaded._runtime is runtime


def test_compiled_plan_cap_accepts_exact_count_and_rejects_first_excess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema, _document = _profile_case()
    loaded = load_packaged_quality_consensus()
    anchors = tuple(sorted(consensus._anchor_paths(loaded.model)))
    exact_plan_count = sum(
        consensus._runtime_view_plan_count(view, loaded.model, anchors)
        for view in loaded.model.views
    )

    monkeypatch.setattr(consensus, "_MAX_COMPILED_VIEW_PLANS", exact_plan_count)
    runtime = consensus._compile_quality_consensus_runtime(loaded, schema)
    assert sum(len(view.medoids_by_available_paths) for view in runtime.views) == exact_plan_count

    monkeypatch.setattr(consensus, "_MAX_COMPILED_VIEW_PLANS", exact_plan_count - 1)
    with pytest.raises(QualityConsensusArtifactError):
        consensus._compile_quality_consensus_runtime(loaded, schema)
