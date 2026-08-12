"""Generative and metamorphic invariants for M01-01 validation."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from glio_proteogen.contracts.m01_01.canonical import (
    canonical_protocol_bytes,
    canonical_request_digest,
    identity_binding_digest,
    metadata_document_digest,
    protocol_digest,
)
from glio_proteogen.contracts.m01_01.v1 import (
    EvaluateMetadataRequest,
    ObservedValue,
    RegisterProtocolRequest,
    UnresolvedValue,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.validator import (
    validate_metadata,
)
from tests.m01_01_support import load_protocol_schema, load_request

MINIMUM_MASS = 0.1
MAXIMUM_MASS = 10_000.0


@st.composite
def _schema_and_entry_orders(draw: st.DrawFn) -> tuple[tuple[int, ...], tuple[int, ...]]:
    schema_order = tuple(draw(st.permutations((0, 1, 2, 3))))
    entry_order = tuple(draw(st.permutations((0, 1, 2, 3))))
    return schema_order, entry_order


@settings(max_examples=64, deadline=None)
@given(orders=_schema_and_entry_orders())
def test_field_and_entry_order_never_changes_validation(
    orders: tuple[tuple[int, ...], ...],
) -> None:
    schema_order, entry_order = orders
    schema = load_protocol_schema()
    request = load_request("evaluate_conformant.valid.json")
    assert isinstance(request, EvaluateMetadataRequest)
    expected = validate_metadata(schema, request.document, consent_state=ConsentState.GRANTED)
    permuted_schema = schema.model_copy(
        update={"fields": tuple(schema.fields[index] for index in schema_order)}
    )
    permuted_document = request.document.model_copy(
        update={"entries": tuple(request.document.entries[index] for index in entry_order)}
    )

    actual = validate_metadata(
        permuted_schema,
        permuted_document,
        consent_state=ConsentState.GRANTED,
    )

    assert actual == expected


def test_semantically_unordered_protocol_collections_have_one_content_identity() -> None:
    request = load_request("register_minimal.valid.json")
    assert isinstance(request, RegisterProtocolRequest)
    schema = request.protocol_schema
    permuted_fields = tuple(
        field.model_copy(
            update={
                "allowed_units": tuple(reversed(field.allowed_units)),
                "allowed_missingness": tuple(reversed(field.allowed_missingness)),
            }
        )
        for field in reversed(schema.fields)
    )
    permuted_vocabularies = tuple(
        vocabulary.model_copy(update={"terms": tuple(reversed(vocabulary.terms))})
        for vocabulary in reversed(schema.vocabularies)
    )
    permuted_rules = tuple(
        rule.model_copy(
            update={
                "when_all": tuple(
                    predicate.model_copy(
                        update={"values": tuple(reversed(predicate.values))}
                    )
                    for predicate in reversed(rule.when_all)
                ),
                "require_all": tuple(
                    predicate.model_copy(
                        update={"values": tuple(reversed(predicate.values))}
                    )
                    for predicate in reversed(rule.require_all)
                ),
            }
        )
        for rule in reversed(schema.compatibility_rules)
    )
    permuted_schema = schema.model_copy(
        update={
            "assay_versions": tuple(reversed(schema.assay_versions)),
            "specimen_versions": tuple(reversed(schema.specimen_versions)),
            "fields": permuted_fields,
            "vocabularies": permuted_vocabularies,
            "units": tuple(reversed(schema.units)),
            "compatibility_rules": permuted_rules,
            "limitations": tuple(reversed(schema.limitations)),
        }
    )
    permuted_request = request.model_copy(update={"protocol_schema": permuted_schema})

    assert canonical_protocol_bytes(permuted_schema) == canonical_protocol_bytes(schema)
    assert protocol_digest(permuted_schema) == protocol_digest(schema)
    assert canonical_request_digest(permuted_request) == canonical_request_digest(request)


def test_semantically_unordered_document_entries_and_values_have_one_digest() -> None:
    request = load_request("evaluate_conformant.valid.json")
    assert isinstance(request, EvaluateMetadataRequest)
    document = request.document
    batch_entry = document.entries[-1].model_copy(
        update={
            "values": (
                ObservedValue(value="BATCH-AA"),
                ObservedValue(value="BATCH-BB"),
            )
        }
    )
    multi_value_document = document.model_copy(
        update={"entries": (*document.entries[:-1], batch_entry)}
    )
    permuted_entries = tuple(
        entry.model_copy(update={"values": tuple(reversed(entry.values))})
        for entry in reversed(multi_value_document.entries)
    )
    permuted_document = multi_value_document.model_copy(update={"entries": permuted_entries})
    baseline_request = request.model_copy(update={"document": multi_value_document})
    permuted_request = request.model_copy(update={"document": permuted_document})

    assert metadata_document_digest(permuted_document) == metadata_document_digest(
        multi_value_document
    )
    assert canonical_request_digest(permuted_request) == canonical_request_digest(
        baseline_request
    )


def test_identity_binding_uses_only_canonical_declared_identity_key_evidence() -> None:
    schema = load_protocol_schema()
    request = load_request("evaluate_conformant.valid.json")
    assert isinstance(request, EvaluateMetadataRequest)
    document = request.document
    expected = identity_binding_digest(schema, document)

    nonidentity_entry = document.entries[1].model_copy(
        update={"values": (ObservedValue(value="enriched"),)}
    )
    irrelevant_changes = document.model_copy(
        update={
            "document_id": "document.synthetic.changed",
            "entries": tuple(
                reversed((document.entries[0], nonidentity_entry, *document.entries[2:]))
            ),
        }
    )
    permuted_schema = schema.model_copy(update={"fields": tuple(reversed(schema.fields))})

    assert identity_binding_digest(permuted_schema, irrelevant_changes) == expected

    changed_identity = document.entries[0].model_copy(
        update={"values": (ObservedValue(value="SYN-999"),)}
    )
    identity_change = document.model_copy(
        update={"entries": (changed_identity, *document.entries[1:])}
    )

    assert identity_binding_digest(schema, identity_change) != expected


@settings(max_examples=96, deadline=None)
@given(value=st.floats(allow_nan=False, allow_infinity=False, width=32))
def test_numeric_bounds_are_inclusive_and_total_for_finite_values(value: float) -> None:
    schema = load_protocol_schema()
    request = load_request("evaluate_conformant.valid.json")
    assert isinstance(request, EvaluateMetadataRequest)
    entries = list(request.document.entries)
    mass_entry = entries[2]
    observed = mass_entry.values[0].model_copy(update={"value": value})
    entries[2] = mass_entry.model_copy(update={"values": (observed,)})
    document = request.document.model_copy(update={"entries": tuple(entries)})

    report = validate_metadata(schema, document, consent_state=ConsentState.GRANTED)
    codes = {issue.code for issue in report.issues}

    if value < MINIMUM_MASS:
        assert "value.numeric_below_minimum" in codes
    elif value > MAXIMUM_MASS:
        assert "value.numeric_above_maximum" in codes
    else:
        assert not codes


@settings(max_examples=32, deadline=None)
@given(value=st.sampled_from([True, False, "12.5", "0", "unknown"]))
def test_number_fields_never_coerce_other_scalar_kinds(value: object) -> None:
    schema = load_protocol_schema()
    request = load_request("evaluate_conformant.valid.json")
    assert isinstance(request, EvaluateMetadataRequest)
    entries = list(request.document.entries)
    mass_entry = entries[2]
    observed = mass_entry.values[0].model_copy(update={"value": value})
    entries[2] = mass_entry.model_copy(update={"values": (observed,)})
    document = request.document.model_copy(update={"entries": tuple(entries)})

    report = validate_metadata(schema, document, consent_state=ConsentState.GRANTED)

    assert "value.kind_mismatch" in {issue.code for issue in report.issues}


@settings(max_examples=32, deadline=None)
@given(state=st.sampled_from(["missing", "not_applicable", "unsupported"]))
def test_disallowed_missingness_is_never_interpreted_as_observed(state: str) -> None:
    request = load_request("evaluate_conformant.valid.json")
    assert isinstance(request, EvaluateMetadataRequest)
    schema = load_protocol_schema()
    batch_entry = request.document.entries[3]
    unresolved = UnresolvedValue(
        state=state,
        reason_code="synthetic_unresolved",
        explanation="Synthetic unresolved state for generative evidence.",
    )
    entries = (
        *request.document.entries[:3],
        batch_entry.model_copy(update={"values": (unresolved,)}),
    )
    document = request.document.model_copy(update={"entries": entries})

    report = validate_metadata(schema, document, consent_state=ConsentState.GRANTED)

    assert "value.missingness_not_allowed" in {issue.code for issue in report.issues}
    assert f"value.unresolved_{state}" in {issue.code for issue in report.issues}
    assert all("negative" not in issue.code for issue in report.issues)


@settings(max_examples=32, deadline=None)
@given(consent=st.sampled_from(tuple(ConsentState)))
def test_validation_never_mutates_inputs(consent: ConsentState) -> None:
    schema = load_protocol_schema()
    request = load_request("evaluate_conformant.valid.json")
    assert isinstance(request, EvaluateMetadataRequest)
    schema_before = schema.model_dump(mode="python")
    document_before = request.document.model_dump(mode="python")

    validate_metadata(schema, request.document, consent_state=consent)

    assert schema.model_dump(mode="python") == schema_before
    assert request.document.model_dump(mode="python") == document_before
