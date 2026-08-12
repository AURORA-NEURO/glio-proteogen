"""M01-01 latency regression tripwires.

Budgets are deliberately generous across CI hardware. They detect algorithmic regressions,
not small machine-to-machine variance.
"""

from __future__ import annotations

from importlib.resources import files
from itertools import count
from typing import TYPE_CHECKING, cast

import pytest
from pydantic import TypeAdapter
from tests.m01_01_support import load_protocol_schema, load_request

from glio_proteogen.contracts.m01_01.canonical import (
    identity_binding_digest,
    metadata_document_digest,
)
from glio_proteogen.contracts.m01_01.v1 import (
    Cardinality,
    ConformanceDecision,
    ConformanceProfile,
    EvaluateMetadataRequest,
    FieldSpecification,
    MetadataDocument,
    MetadataEntry,
    ObservedValue,
    ProtocolSchema,
    ProtocolSchemaReceipt,
    RegisterProtocolRequest,
    ValueKind,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.kernel.strict_json import JsonValue, strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.event_store import (
    M0101EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.quality_consensus import (
    ConsensusStatus,
    LoadedQualityConsensus,
    assess_quality_consensus,
    load_packaged_quality_consensus,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.service import (
    M0101Service,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.validator import (
    validate_metadata,
    validate_protocol_schema,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_benchmark.fixture import BenchmarkFixture

REFERENCE_MEAN_BUDGET_SECONDS = 0.005
LARGE_MEAN_BUDGET_SECONDS = 0.050
DIGEST_MEAN_BUDGET_SECONDS = 0.005
SERVICE_LIFECYCLE_MEAN_BUDGET_SECONDS = 0.100
SERVICE_REPLAY_MEAN_BUDGET_SECONDS = 0.010
DOMAIN_PROFILE_MEAN_BUDGET_SECONDS = 0.010
QUALITY_CONSENSUS_MEAN_BUDGET_SECONDS = 0.010
QUALITY_CONSENSUS_BENCHMARK_ROUNDS = 64
QUALITY_CONSENSUS_BENCHMARK_ITERATIONS = 2
SERVICE_BENCHMARK_ROUNDS = 16
SERVICE_EVENT_COUNT = 2
DOMAIN_PROFILE_FIELD_COUNT = 55
QUALITY_FEATURE_COUNT = 18
QUALITY_PROFILE_COUNT = 12
DOMAIN_PROFILE_PACKAGE = "glio_proteogen.profiles.m01_01.v1"

pytestmark = pytest.mark.benchmark


def _large_case(size: int = 500) -> tuple[ProtocolSchema, MetadataDocument]:
    schema = load_protocol_schema()
    request = load_request("evaluate_conformant.valid.json")
    assert isinstance(request, EvaluateMetadataRequest)
    fields = list(schema.fields)
    entries = list(request.document.entries)
    for index in range(size):
        path = f"/synthetic/value_{index:04d}"
        fields.append(
            FieldSpecification(
                path=path,
                title=f"Synthetic value {index}",
                description="Artificial integer used only for scaling evidence.",
                value_kind=ValueKind.INTEGER,
                required=False,
                cardinality=Cardinality(minimum=0, maximum=1),
            )
        )
        entries.append(MetadataEntry(path=path, values=(ObservedValue(value=index),)))
    return (
        schema.model_copy(update={"fields": tuple(fields)}),
        request.document.model_copy(update={"entries": tuple(entries)}),
    )


def _service_requests() -> tuple[RegisterProtocolRequest, EvaluateMetadataRequest]:
    registration = load_request("register_minimal.valid.json")
    evaluation = load_request("evaluate_conformant.valid.json")
    assert isinstance(registration, RegisterProtocolRequest)
    assert isinstance(evaluation, EvaluateMetadataRequest)
    return registration, evaluation


def _domain_profile_case() -> tuple[ProtocolSchema, MetadataDocument]:
    profile = files(DOMAIN_PROFILE_PACKAGE)
    schema = TypeAdapter(ProtocolSchema).validate_json(
        profile.joinpath("protocol-schema.json").read_bytes()
    )
    corpus = cast(
        "dict[str, JsonValue]",
        strict_json_loads(profile.joinpath("conformance-corpus.json").read_bytes()),
    )
    document = TypeAdapter(MetadataDocument).validate_json(
        canonical_json_bytes(corpus["base_document"])
    )
    return schema, document


def _register_and_evaluate(
    service: M0101Service,
    registration: RegisterProtocolRequest,
    evaluation: EvaluateMetadataRequest,
) -> tuple[ProtocolSchemaReceipt, ConformanceProfile]:
    return service.register(registration), service.evaluate(evaluation)


def test_reference_validation_mean_latency(benchmark: BenchmarkFixture) -> None:
    schema = load_protocol_schema()
    request = load_request("evaluate_conformant.valid.json")
    assert isinstance(request, EvaluateMetadataRequest)

    report = benchmark(
        validate_metadata,
        schema,
        request.document,
        consent_state=ConsentState.GRANTED,
    )

    assert report.decision is ConformanceDecision.CONFORMANT
    assert benchmark.stats.stats.mean <= REFERENCE_MEAN_BUDGET_SECONDS


def test_five_hundred_field_validation_stays_linear(benchmark: BenchmarkFixture) -> None:
    schema, document = _large_case()

    report = benchmark(
        validate_metadata,
        schema,
        document,
        consent_state=ConsentState.GRANTED,
    )

    assert report.decision is ConformanceDecision.CONFORMANT
    assert benchmark.stats.stats.mean <= LARGE_MEAN_BUDGET_SECONDS


def test_document_canonical_digest_mean_latency(benchmark: BenchmarkFixture) -> None:
    request = load_request("evaluate_conformant.valid.json")
    assert isinstance(request, EvaluateMetadataRequest)

    digest = benchmark(metadata_document_digest, request.document)

    assert digest.startswith("sha256:")
    assert benchmark.stats.stats.mean <= DIGEST_MEAN_BUDGET_SECONDS


def test_domain_profile_validation_mean_latency(benchmark: BenchmarkFixture) -> None:
    schema, document = _domain_profile_case()
    expected_binding = identity_binding_digest(schema, document)

    report = benchmark(
        validate_metadata,
        schema,
        document,
        consent_state=ConsentState.GRANTED,
        expected_identity_binding_digest=expected_binding,
    )

    assert len(schema.fields) == DOMAIN_PROFILE_FIELD_COUNT
    assert report.decision is ConformanceDecision.CONFORMANT
    assert benchmark.stats.stats.mean <= DOMAIN_PROFILE_MEAN_BUDGET_SECONDS


def test_domain_quality_consensus_mean_latency(benchmark: BenchmarkFixture) -> None:
    """Measure the frozen 18-feature, 3-view, 12-profile nearest-medoid guard."""

    schema, document = _domain_profile_case()
    loaded: LoadedQualityConsensus = load_packaged_quality_consensus()

    assessment = benchmark.pedantic(
        assess_quality_consensus,
        args=(schema, document, loaded),
        rounds=QUALITY_CONSENSUS_BENCHMARK_ROUNDS,
        warmup_rounds=8,
        iterations=QUALITY_CONSENSUS_BENCHMARK_ITERATIONS,
    )

    assert assessment.status is ConsensusStatus.IN_DOMAIN
    assert assessment.evaluated_views == len(loaded.model.views)
    assert len(loaded.model.features) == QUALITY_FEATURE_COUNT
    assert len(loaded.corpus.profiles) == QUALITY_PROFILE_COUNT
    assert benchmark.stats.stats.mean <= QUALITY_CONSENSUS_MEAN_BUDGET_SECONDS


def test_adversarial_pattern_is_rejected_without_regex_evaluation(
    benchmark: BenchmarkFixture,
) -> None:
    schema = load_protocol_schema()
    adjacent_optionals = "^" + "a?" * 24 + "a" * 24 + "b$"
    field = schema.fields[0].model_copy(update={"pattern": adjacent_optionals})
    candidate = schema.model_copy(update={"fields": (field, *schema.fields[1:])})

    report = benchmark(validate_protocol_schema, candidate)

    assert report.decision is ConformanceDecision.QUARANTINED
    assert "schema.pattern_unsafe" in {issue.code for issue in report.issues}
    assert benchmark.stats.stats.mean <= REFERENCE_MEAN_BUDGET_SECONDS


def test_fresh_sqlite_registration_and_evaluation_mean_latency(
    benchmark: BenchmarkFixture,
    tmp_path: Path,
) -> None:
    """Measure one fresh two-event lifecycle; database initialization is setup cost."""

    registration, evaluation = _service_requests()
    sequence = count()

    def setup() -> tuple[
        tuple[M0101Service, RegisterProtocolRequest, EvaluateMetadataRequest],
        dict[str, object],
    ]:
        database = tmp_path / f"lifecycle-{next(sequence):03d}.sqlite3"
        service = M0101Service(M0101EventStore(database))
        return (service, registration, evaluation), {}

    def teardown(
        service: M0101Service,
        _registration: RegisterProtocolRequest,
        _evaluation: EvaluateMetadataRequest,
    ) -> None:
        service.close()

    receipt, profile = benchmark.pedantic(
        _register_and_evaluate,
        setup=setup,
        teardown=teardown,
        rounds=SERVICE_BENCHMARK_ROUNDS,
        warmup_rounds=2,
        iterations=1,
    )

    assert receipt.output_type == "protocol_schema"
    assert profile.decision is ConformanceDecision.CONFORMANT
    assert benchmark.stats.stats.mean <= SERVICE_LIFECYCLE_MEAN_BUDGET_SECONDS


def test_exact_service_replay_mean_latency(
    benchmark: BenchmarkFixture,
    tmp_path: Path,
) -> None:
    """Measure idempotent register/evaluate replay on an isolated two-event ledger."""

    registration, evaluation = _service_requests()
    service = M0101Service(M0101EventStore(tmp_path / "replay.sqlite3"))
    expected = _register_and_evaluate(service, registration, evaluation)
    try:
        actual = benchmark(
            _register_and_evaluate,
            service,
            registration,
            evaluation,
        )
        verification = service.verify_event_chain()
    finally:
        service.close()

    assert actual == expected
    assert verification.valid is True
    assert verification.event_count == SERVICE_EVENT_COUNT
    assert benchmark.stats.stats.mean <= SERVICE_REPLAY_MEAN_BUDGET_SECONDS
