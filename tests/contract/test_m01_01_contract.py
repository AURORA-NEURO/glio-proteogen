"""Locked structural and serialization behavior for the M01-01 contract."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m01_01.schema import (
    CONTRACT_VERSION,
    JSON_SCHEMA_DIALECT,
    SCHEMA_ID_PREFIX,
    ContractName,
    contract_json_schema,
)
from glio_proteogen.contracts.m01_01.v1 import M0101Request, ProtocolSchema
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from tests.m01_01_support import load_json, load_protocol_schema, load_request

pytestmark = pytest.mark.contract

SNAPSHOT_PATH = (
    Path(__file__).parents[1] / "snapshots" / "m01_01" / "schema_digests.json"
)
PUBLIC_SCHEMA_NAMES: tuple[ContractName, ...] = (
    "request",
    "output",
    "register-request",
    "evaluate-request",
    "protocol-schema",
    "metadata-document",
    "protocol-receipt",
    "conformance-profile",
)


def test_public_json_schema_snapshots_are_locked() -> None:
    expected = load_json(SNAPSHOT_PATH)
    documents = {name: contract_json_schema(name) for name in PUBLIC_SCHEMA_NAMES}
    actual = {
        "contract_version": CONTRACT_VERSION,
        "dialect": JSON_SCHEMA_DIALECT,
        "schemas": {
            name: {
                "$id": document["$id"],
                "digest": sha256_digest(document),
            }
            for name, document in documents.items()
        },
    }

    assert actual == expected


@pytest.mark.parametrize("name", PUBLIC_SCHEMA_NAMES)
def test_public_schema_is_self_identifying_draft_2020_12(name: ContractName) -> None:
    document = contract_json_schema(name)

    assert document["$schema"] == JSON_SCHEMA_DIALECT
    assert document["$id"] == f"{SCHEMA_ID_PREFIX}:{name}"
    Draft202012Validator.check_schema(document)


def test_public_schema_extensions_name_every_semantically_unique_object_key() -> None:
    protocol = cast("dict[str, Any]", contract_json_schema("protocol-schema"))
    document = cast("dict[str, Any]", contract_json_schema("metadata-document"))
    output = cast("dict[str, Any]", contract_json_schema("output"))

    protocol_definition = protocol["$defs"]
    assert protocol["properties"]["fields"]["x-glio-uniqueBy"] == "/path"
    assert protocol["properties"]["vocabularies"]["x-glio-uniqueBy"] == (
        "/vocabulary_id"
    )
    assert protocol["properties"]["units"]["x-glio-uniqueBy"] == "/code"
    assert protocol["properties"]["compatibility_rules"]["x-glio-uniqueBy"] == (
        "/rule_id"
    )
    assert protocol["properties"]["limitations"]["x-glio-uniqueBy"] == "/code"
    assert protocol_definition["VocabularyDefinition"]["properties"]["terms"][
        "x-glio-uniqueBy"
    ] == "/code"
    assert document["properties"]["entries"]["x-glio-uniqueBy"] == "/path"
    for output_name in ("ProtocolSchemaReceipt", "ConformanceProfile"):
        assert output["$defs"][output_name]["properties"]["limitations"][
            "x-glio-uniqueBy"
        ] == "/code"
    assert output["$defs"]["ProvenanceRecord"]["properties"]["control_decisions"][
        "x-glio-uniqueBy"
    ] == "/role"


@pytest.mark.parametrize("name", PUBLIC_SCHEMA_NAMES)
def test_public_schema_declares_authoritative_strict_runtime_profile(
    name: ContractName,
) -> None:
    profile = cast(
        "dict[str, Any]",
        contract_json_schema(name)["x-glio-validation-profile"],
    )

    assert profile == {
        "id": f"{SCHEMA_ID_PREFIX}:runtime-conformance",
        "scope": "structural schema plus expressible relational invariants",
        "strictJson": True,
        "silentCoercion": False,
        "authoritativeRuntime": (
            "Pydantic-v2 strict contracts followed by M01-01 semantic conformance "
            "validation"
        ),
        "extensionKeywords": ["x-glio-uniqueBy", "x-glio-relationalInvariants"],
    }


def test_canonical_json_ignores_mapping_insertion_order() -> None:
    request = load_request("register_minimal.valid.json")
    payload = request.model_dump(mode="json")
    reverse_order = {key: deepcopy(payload[key]) for key in reversed(payload)}

    assert canonical_json_bytes(payload) == canonical_json_bytes(reverse_order)
    assert sha256_digest(payload) == sha256_digest(reverse_order)


def test_contract_models_are_deeply_immutable() -> None:
    schema = load_protocol_schema()

    with pytest.raises(ValidationError, match="frozen"):
        schema.title = "mutated"  # type: ignore[misc]
    with pytest.raises(TypeError):
        schema.fields[0] = schema.fields[-1]  # type: ignore[index]


@pytest.mark.parametrize(
    ("field", "coerced"),
    [("required", "true"), ("required", 1), ("identity_key", "false")],
)
def test_field_specification_never_coerces_boolean_values(field: str, coerced: object) -> None:
    payload = load_protocol_schema().fields[0].model_dump(mode="python")
    payload[field] = coerced

    with pytest.raises(ValidationError):
        TypeAdapter(type(load_protocol_schema().fields[0])).validate_python(payload)


def test_absent_optional_values_serialize_differently_from_explicit_null() -> None:
    schema = load_protocol_schema()
    without_none = schema.model_dump(mode="json", exclude_none=True)
    with_none = schema.model_dump(mode="json", exclude_none=False)

    assert canonical_json_bytes(without_none) != canonical_json_bytes(with_none)


def test_request_discriminator_is_closed() -> None:
    with pytest.raises(ValidationError, match="union_tag_invalid"):
        TypeAdapter(M0101Request).validate_python({"operation": "recommend"})


@pytest.mark.parametrize("field", ["assay_versions", "specimen_versions"])
def test_supported_version_lists_reject_duplicates(field: str) -> None:
    payload = load_protocol_schema().model_dump(mode="json")
    payload[field] = ["1.0.0", "1.0.0"]

    with pytest.raises(ValidationError, match="versions must be unique"):
        TypeAdapter(ProtocolSchema).validate_json(json.dumps(payload))
