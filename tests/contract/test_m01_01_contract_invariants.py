"""Adversarial coverage for every relational M01-01 contract invariant."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m01_01.v1 import (
    M0101_SCOPE_LIMITATION_CODE,
    M0101_UNVERIFIED_CONTROLS_LIMITATION_CODE,
    Cardinality,
    CompatibilityPredicate,
    CompatibilityRule,
    FieldSpecification,
    M0101Output,
    M0101Request,
    MetadataDocument,
    MetadataEntry,
    NumericBounds,
    ObservedValue,
    PredicateOperator,
    ProtocolSchema,
    UnitDefinition,
    VocabularyDefinition,
)
from glio_proteogen.kernel.models import ArtifactReference
from tests.m01_01_support import load_protocol_schema

pytestmark = pytest.mark.contract

SMALL_COLLECTION_LIMIT = 64
MEDIUM_COLLECTION_LIMIT = 256
PREDICATE_VALUE_LIMIT = 1_000
LARGE_COLLECTION_LIMIT = 10_000
SCALAR_TEXT_LIMIT = 65_536
SEMANTIC_VERSION_LIMIT = 128
DECLARED_LIMITATION_LIMIT = 998
_CONTROL_DECISION_COUNT = 7


def _rejects(adapter: TypeAdapter[object], payload: object, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        adapter.validate_json(json.dumps(payload))


def test_vocabulary_term_codes_are_unique() -> None:
    vocabulary = load_protocol_schema().vocabularies[0].model_dump(mode="json")
    vocabulary["terms"].append(deepcopy(vocabulary["terms"][0]))

    _rejects(TypeAdapter(VocabularyDefinition), vocabulary, "term codes must be unique")


def test_cardinality_bounds_are_ordered() -> None:
    _rejects(
        TypeAdapter(Cardinality),
        {"minimum": 2, "maximum": 1},
        "minimum cardinality cannot exceed maximum",
    )


def test_numeric_bounds_are_ordered() -> None:
    _rejects(
        TypeAdapter(NumericBounds),
        {"minimum": 2.0, "maximum": 1.0},
        "minimum value cannot exceed maximum",
    )


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"allowed_units": ["ug"], "unit_dimension": None}, "require a declared dimension"),
        ({"allowed_units": [], "unit_dimension": "mass"}, "requires at least one allowed unit"),
        ({"reference_unit": None}, "require an explicit reference unit"),
        ({"reference_unit": "mg"}, "must belong to the allowed unit set"),
        (
            {"vocabulary_id": "vocabulary.synthetic_mode"},
            "controlled vocabulary is only valid",
        ),
        ({"pattern": "^x$", "value_kind": "number"}, "only valid for text-like fields"),
        (
            {
                "numeric_bounds": {"minimum": 0.0},
                "value_kind": "text",
                "allowed_units": [],
                "unit_dimension": None,
                "reference_unit": None,
            },
            "only valid for numeric fields",
        ),
        ({"required": True, "cardinality": {"minimum": 0, "maximum": 1}}, "minimum"),
    ],
)
def test_field_constraints_are_relationally_closed(
    update: dict[str, object],
    message: str,
) -> None:
    payload = load_protocol_schema().fields[2].model_dump(mode="json")
    payload.update(update)

    _rejects(TypeAdapter(FieldSpecification), payload, message)


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"code": "banana"}, "Input should be"),
        ({"code": "mcg"}, "Input should be"),
        ({"code": "µg"}, "Input should be"),
        ({"system": "ucum"}, "Input should be 'UCUM'"),
        ({"system_version": "2.1"}, "Input should be '2.2'"),
        ({"dimension": "time"}, "does not match pinned UCUM semantics"),
    ],
)
def test_unit_definition_is_pinned_to_valid_ucum_2_2_semantics(
    update: dict[str, str],
    message: str,
) -> None:
    payload = load_protocol_schema().units[0].model_dump(mode="json")
    payload.update(update)

    _rejects(TypeAdapter(UnitDefinition), payload, message)


def test_unit_definition_requires_an_explicit_system_version() -> None:
    payload = load_protocol_schema().units[0].model_dump(mode="json")
    del payload["system_version"]

    _rejects(TypeAdapter(UnitDefinition), payload, "Field required")


@pytest.mark.parametrize(
    ("path", "unit", "message"),
    [
        ("/sample/input_mass", None, "require an explicit UCUM unit"),
        ("/sample/input_mass", "mg", "not allowed for its field"),
        ("/assay/mode", "ug", "unitless or presence predicates cannot carry"),
    ],
)
def test_protocol_rejects_ambiguous_or_inapplicable_predicate_units(
    path: str,
    unit: str | None,
    message: str,
) -> None:
    payload = load_protocol_schema().model_dump(mode="json")
    predicate: dict[str, object] = {
        "path": path,
        "operator": "equals",
        "values": [1.0],
    }
    if path == "/assay/mode":
        predicate["values"] = ["enriched"]
    if unit is not None:
        predicate["unit"] = unit
    payload["compatibility_rules"][0]["when_all"] = [predicate]

    _rejects(TypeAdapter(ProtocolSchema), payload, message)


@pytest.mark.parametrize(
    ("operator", "values", "message"),
    [
        (PredicateOperator.EQUALS, [], "require values"),
        (PredicateOperator.IN, [], "require values"),
        (PredicateOperator.PRESENT, ["x"], "cannot carry values"),
        (PredicateOperator.ABSENT, ["x"], "cannot carry values"),
        (PredicateOperator.EQUALS, ["x", "y"], "exactly one value"),
    ],
)
def test_predicate_arity_matches_operator(
    operator: PredicateOperator,
    values: list[str],
    message: str,
) -> None:
    _rejects(
        TypeAdapter(CompatibilityPredicate),
        {"path": "/sample/key", "operator": operator.value, "values": values},
        message,
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("field", "field paths must be unique"),
        ("vocabulary", "vocabulary IDs must be unique"),
        ("unit", "unit codes must be unique"),
        ("rule", "compatibility rule IDs must be unique"),
        ("limitation", "limitation codes must be unique"),
        ("unknown_vocabulary", "references unknown vocabulary"),
        ("unknown_unit", "references unknown unit"),
        ("unknown_rule_path", "references unknown field"),
    ],
)
def test_protocol_graph_rejects_duplicate_or_dangling_references(
    mutation: str,
    message: str,
) -> None:
    payload = load_protocol_schema().model_dump(mode="json")
    if mutation == "field":
        payload["fields"].append(deepcopy(payload["fields"][0]))
    elif mutation == "vocabulary":
        payload["vocabularies"].append(deepcopy(payload["vocabularies"][0]))
    elif mutation == "unit":
        payload["units"].append(deepcopy(payload["units"][0]))
    elif mutation == "rule":
        payload["compatibility_rules"].append(deepcopy(payload["compatibility_rules"][0]))
    elif mutation == "limitation":
        payload["limitations"].append(deepcopy(payload["limitations"][0]))
    elif mutation == "unknown_vocabulary":
        payload["fields"][1]["vocabulary_id"] = "vocabulary.unknown"
    elif mutation == "unknown_unit":
        payload["fields"][2]["allowed_units"] = ["mg"]
        payload["fields"][2]["reference_unit"] = "mg"
    else:
        payload["compatibility_rules"][0]["require_all"][0]["path"] = "/unknown"

    _rejects(TypeAdapter(ProtocolSchema), payload, message)


@pytest.mark.parametrize(
    "reserved_code",
    [M0101_SCOPE_LIMITATION_CODE, M0101_UNVERIFIED_CONTROLS_LIMITATION_CODE],
)
def test_client_cannot_claim_a_module_reserved_limitation(reserved_code: str) -> None:
    payload = load_protocol_schema().model_dump(mode="json")
    payload["limitations"][0]["code"] = reserved_code

    _rejects(TypeAdapter(ProtocolSchema), payload, "module limitation codes are reserved")


def test_scalar_text_has_a_hard_pre_validation_cap() -> None:
    payload = {"state": "observed", "value": "x" * (SCALAR_TEXT_LIMIT + 1)}

    _rejects(TypeAdapter(ObservedValue), payload, f"at most {SCALAR_TEXT_LIMIT}")


def test_semantic_versions_accept_the_exact_cap_and_reject_first_excess_character() -> None:
    prefix = "1.0.0-"
    artifact = {
        "artifact_id": "artifact.synthetic",
        "version": prefix + ("a" * (SEMANTIC_VERSION_LIMIT - len(prefix))),
        "digest": f"sha256:{'a' * 64}",
        "media_type": "application/json",
    }

    assert len(artifact["version"]) == SEMANTIC_VERSION_LIMIT
    TypeAdapter(ArtifactReference).validate_json(json.dumps(artifact), strict=True)
    artifact["version"] += "a"
    _rejects(
        TypeAdapter(ArtifactReference),
        artifact,
        f"at most {SEMANTIC_VERSION_LIMIT}",
    )


def test_every_exported_semantic_version_string_declares_the_shared_schema_cap() -> None:
    schema = TypeAdapter(M0101Request).json_schema(mode="validation")

    def semantic_version_nodes(node: object) -> list[dict[str, object]]:
        if isinstance(node, list):
            return [
                match
                for value in node
                for match in semantic_version_nodes(value)
            ]
        if not isinstance(node, dict):
            return []
        matches = (
            [node]
            if node.get("type") == "string"
            and "[0-9A-Za-z-]+" in str(node.get("pattern", ""))
            else []
        )
        return [
            *matches,
            *(
                match
                for value in node.values()
                for match in semantic_version_nodes(value)
            ),
        ]

    versions = semantic_version_nodes(schema)

    assert versions
    assert {node.get("maxLength") for node in versions} == {SEMANTIC_VERSION_LIMIT}


def test_nested_collections_reject_the_first_item_over_their_caps() -> None:
    numeric_field = load_protocol_schema().fields[2].model_dump(mode="json")
    numeric_field["allowed_units"] = ["ug"] * (MEDIUM_COLLECTION_LIMIT + 1)
    _rejects(TypeAdapter(FieldSpecification), numeric_field, "at most 256")

    predicate = {
        "path": "/synthetic/value",
        "operator": "in",
        "values": list(range(PREDICATE_VALUE_LIMIT + 1)),
    }
    _rejects(TypeAdapter(CompatibilityPredicate), predicate, "at most 1000")

    rule = load_protocol_schema().compatibility_rules[0].model_dump(mode="json")
    rule["when_all"] = [rule["when_all"][0]] * (SMALL_COLLECTION_LIMIT + 1)
    _rejects(TypeAdapter(CompatibilityRule), rule, "at most 64")


def _uncapped_array_paths(node: object, path: str = "$") -> list[str]:
    if isinstance(node, list):
        return [
            child_path
            for index, value in enumerate(node)
            for child_path in _uncapped_array_paths(value, f"{path}/{index}")
        ]
    if not isinstance(node, dict):
        return []
    missing = [path] if node.get("type") == "array" and "maxItems" not in node else []
    return [
        *missing,
        *(
            child_path
            for key, value in node.items()
            for child_path in _uncapped_array_paths(value, f"{path}/{key}")
        ),
    ]


def test_public_collection_caps_are_locked_in_json_schema() -> None:
    protocol = TypeAdapter(ProtocolSchema).json_schema(mode="validation")
    document = TypeAdapter(MetadataDocument).json_schema(mode="validation")
    entry = TypeAdapter(MetadataEntry).json_schema(mode="validation")
    predicate = TypeAdapter(CompatibilityPredicate).json_schema(mode="validation")
    rule = TypeAdapter(CompatibilityRule).json_schema(mode="validation")
    output = TypeAdapter(M0101Output).json_schema(mode="validation")

    assert protocol["properties"]["fields"]["maxItems"] == LARGE_COLLECTION_LIMIT
    assert (
        protocol["properties"]["limitations"]["maxItems"]
        == DECLARED_LIMITATION_LIMIT
    )
    assert (
        protocol["properties"]["compatibility_rules"]["maxItems"]
        == LARGE_COLLECTION_LIMIT
    )
    assert document["properties"]["entries"]["maxItems"] == LARGE_COLLECTION_LIMIT
    assert entry["properties"]["values"]["maxItems"] == LARGE_COLLECTION_LIMIT
    assert predicate["properties"]["values"]["maxItems"] == PREDICATE_VALUE_LIMIT
    assert rule["properties"]["when_all"]["maxItems"] == SMALL_COLLECTION_LIMIT
    assert rule["properties"]["require_all"]["maxItems"] == SMALL_COLLECTION_LIMIT
    assert (
        output["$defs"]["ConformanceIssue"]["properties"]["evidence"]["maxItems"]
        == SMALL_COLLECTION_LIMIT
    )
    for output_name in ("ConformanceProfile", "ProtocolSchemaReceipt"):
        properties = output["$defs"][output_name]["properties"]
        assert properties["evidence"]["maxItems"] == MEDIUM_COLLECTION_LIMIT
        assert properties["limitations"]["maxItems"] == PREDICATE_VALUE_LIMIT
    assert (
        output["$defs"]["UncertaintyProfile"]["properties"]["sensitivity_notes"][
            "maxItems"
        ]
        == MEDIUM_COLLECTION_LIMIT
    )
    assert (
        output["$defs"]["ProvenanceRecord"]["properties"]["input_digests"][
            "maxItems"
        ]
        == LARGE_COLLECTION_LIMIT
    )
    control_decisions = output["$defs"]["ProvenanceRecord"]["properties"][
        "control_decisions"
    ]
    assert control_decisions["minItems"] == _CONTROL_DECISION_COUNT
    assert control_decisions["maxItems"] == _CONTROL_DECISION_COUNT


@pytest.mark.parametrize("contract", [M0101Request, M0101Output])
def test_every_public_contract_array_has_an_explicit_ceiling(contract: object) -> None:
    schema = TypeAdapter(contract).json_schema(mode="validation")

    assert _uncapped_array_paths(schema) == []
