"""Versioned JSON Schema 2020-12 exports for M01-01 public contracts."""

from __future__ import annotations

from typing import Any, Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_01.v1 import (
    M0101_RESERVED_LIMITATION_CODES,
    ConformanceProfile,
    EvaluateMetadataRequest,
    M0101Output,
    M0101Request,
    MetadataDocument,
    ProtocolSchema,
    ProtocolSchemaReceipt,
    RegisterProtocolRequest,
)

CONTRACT_VERSION: Final = "1.0.0"
JSON_SCHEMA_DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-01:1.0.0"

type ContractName = Literal[
    "request",
    "output",
    "register-request",
    "evaluate-request",
    "protocol-schema",
    "metadata-document",
    "protocol-receipt",
    "conformance-profile",
]

_ADAPTERS: Final[dict[ContractName, TypeAdapter[object]]] = {
    "request": TypeAdapter(M0101Request),
    "output": TypeAdapter(M0101Output),
    "register-request": TypeAdapter(RegisterProtocolRequest),
    "evaluate-request": TypeAdapter(EvaluateMetadataRequest),
    "protocol-schema": TypeAdapter(ProtocolSchema),
    "metadata-document": TypeAdapter(MetadataDocument),
    "protocol-receipt": TypeAdapter(ProtocolSchemaReceipt),
    "conformance-profile": TypeAdapter(ConformanceProfile),
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return the structural schema plus explicit executable-invariant metadata."""

    generated = _ADAPTERS[name].json_schema(mode="validation")
    exported = {
        "$schema": JSON_SCHEMA_DIALECT,
        "$id": f"{SCHEMA_ID_PREFIX}:{name}",
        **generated,
    }
    _enrich_expressible_invariants(exported)
    exported["x-glio-validation-profile"] = {
        "id": f"{SCHEMA_ID_PREFIX}:runtime-conformance",
        "scope": "structural schema plus expressible relational invariants",
        "strictJson": True,
        "silentCoercion": False,
        "authoritativeRuntime": (
            "Pydantic-v2 strict contracts followed by M01-01 semantic conformance validation"
        ),
        "extensionKeywords": ["x-glio-uniqueBy", "x-glio-relationalInvariants"],
    }
    return cast("dict[str, object]", exported)


def _definition(schema: dict[str, Any], name: str) -> dict[str, Any] | None:
    if schema.get("title") == name:
        return schema
    definitions = schema.get("$defs", {})
    candidate = definitions.get(name)
    return candidate if isinstance(candidate, dict) else None


def _array_property(
    definition: dict[str, Any],
    name: str,
) -> dict[str, Any] | None:
    candidate = definition.get("properties", {}).get(name)
    return candidate if isinstance(candidate, dict) else None


def _enrich_expressible_invariants(schema: dict[str, Any]) -> None:
    _mark_unique_arrays(schema)
    _mark_unique_keys(schema)
    _add_field_conditionals(schema)
    _add_predicate_conditionals(schema)
    _add_unit_dimension_conditionals(schema)
    _add_output_limitation_conditionals(schema)
    _mark_runtime_relations(schema)


def _mark_unique_arrays(schema: dict[str, Any]) -> None:
    targets = {
        "ProtocolSchema": ("assay_versions", "specimen_versions"),
        "FieldSpecification": ("allowed_units", "allowed_missingness"),
        "ProvenanceRecord": ("input_digests",),
    }
    for definition_name, property_names in targets.items():
        definition = _definition(schema, definition_name)
        if definition is None:
            continue
        for property_name in property_names:
            array = _array_property(definition, property_name)
            if array is not None:
                array["uniqueItems"] = True


def _mark_unique_keys(schema: dict[str, Any]) -> None:
    targets = {
        ("ProtocolSchema", "fields"): "/path",
        ("ProtocolSchema", "vocabularies"): "/vocabulary_id",
        ("ProtocolSchema", "units"): "/code",
        ("ProtocolSchema", "compatibility_rules"): "/rule_id",
        ("ProtocolSchema", "limitations"): "/code",
        ("VocabularyDefinition", "terms"): "/code",
        ("MetadataDocument", "entries"): "/path",
        ("ProtocolSchemaReceipt", "limitations"): "/code",
        ("ConformanceProfile", "limitations"): "/code",
        ("ProvenanceRecord", "control_decisions"): "/role",
    }
    for (definition_name, property_name), pointer in targets.items():
        definition = _definition(schema, definition_name)
        if definition is None:
            continue
        array = _array_property(definition, property_name)
        if array is not None:
            array["x-glio-uniqueBy"] = pointer


def _add_field_conditionals(schema: dict[str, Any]) -> None:
    field = _definition(schema, "FieldSpecification")
    if field is None:
        return
    field.setdefault("allOf", []).extend(
        (
            {
                "if": {
                    "properties": {"identity_key": {"const": True}},
                    "required": ["identity_key"],
                },
                "then": {
                    "properties": {
                        "required": {"const": True},
                        "value_kind": {"const": "identifier"},
                        "cardinality": {
                            "properties": {
                                "minimum": {"const": 1},
                                "maximum": {"const": 1},
                            },
                            "required": ["minimum", "maximum"],
                        },
                        "allowed_missingness": {"maxItems": 0},
                    },
                    "required": ["required", "value_kind", "cardinality"],
                },
            },
            {
                "if": {
                    "properties": {"allowed_units": {"minItems": 1}},
                    "required": ["allowed_units"],
                },
                "then": {
                    "properties": {
                        "unit_dimension": {"type": "string"},
                        "reference_unit": {"type": "string"},
                        "value_kind": {"enum": ["integer", "number"]},
                    },
                    "required": ["unit_dimension", "reference_unit"],
                },
            },
            {
                "if": {
                    "properties": {"unit_dimension": {"type": "string"}},
                    "required": ["unit_dimension"],
                },
                "then": {
                    "properties": {
                        "allowed_units": {"minItems": 1},
                        "reference_unit": {"type": "string"},
                    },
                    "required": ["allowed_units", "reference_unit"],
                },
            },
            {
                "if": {
                    "properties": {"value_kind": {"const": "term"}},
                    "required": ["value_kind"],
                },
                "then": {
                    "properties": {"vocabulary_id": {"type": "string"}},
                    "required": ["vocabulary_id"],
                },
            },
            {
                "if": {
                    "required": ["numeric_bounds"],
                    "properties": {"numeric_bounds": {"type": "object"}},
                },
                "then": {"properties": {"value_kind": {"enum": ["integer", "number"]}}},
            },
            {
                "if": {
                    "required": ["pattern"],
                    "properties": {"pattern": {"type": "string"}},
                },
                "then": {
                    "properties": {
                        "value_kind": {"enum": ["text", "identifier", "timestamp"]}
                    }
                },
            },
        )
    )


def _add_predicate_conditionals(schema: dict[str, Any]) -> None:
    predicate = _definition(schema, "CompatibilityPredicate")
    if predicate is None:
        return
    predicate.setdefault("allOf", []).extend(
        (
            {
                "if": {
                    "properties": {"operator": {"enum": ["present", "absent"]}},
                    "required": ["operator"],
                },
                "then": {"properties": {"values": {"maxItems": 0}, "unit": {"type": "null"}}},
            },
            {
                "if": {
                    "properties": {"operator": {"enum": ["equals", "in"]}},
                    "required": ["operator"],
                },
                "then": {"properties": {"values": {"minItems": 1}}},
            },
            {
                "if": {
                    "properties": {"operator": {"const": "equals"}},
                    "required": ["operator"],
                },
                "then": {"properties": {"values": {"minItems": 1, "maxItems": 1}}},
            },
        )
    )


def _add_unit_dimension_conditionals(schema: dict[str, Any]) -> None:
    unit = _definition(schema, "UnitDefinition")
    if unit is None:
        return
    dimensions = {
        "mass": ["g", "mg", "ug", "ng", "pg"],
        "volume": ["L", "mL", "uL"],
        "time": ["s", "min", "h", "d"],
        "temperature": ["K", "Cel"],
        "amount": ["mol", "mmol", "umol", "nmol", "pmol"],
        "mass_concentration": ["g/L", "mg/mL", "ug/uL", "mg/L", "ug/mL", "ng/uL", "ng/mL"],
        "amount_concentration": ["pmol/uL", "nmol/L"],
        "frequency": ["Hz", "/min"],
        "electric_potential": ["V", "mV", "kV"],
        "electric_current": ["A", "mA", "uA"],
        "pressure": ["Pa", "kPa"],
        "plane_angle": ["rad", "deg"],
        "acceleration": ["[g]"],
        "dimensionless": ["1", "%"],
        "count": ["{count}"],
    }
    unit.setdefault("allOf", []).extend(
        {
            "if": {"properties": {"code": {"enum": codes}}, "required": ["code"]},
            "then": {"properties": {"dimension": {"const": dimension}}},
        }
        for dimension, codes in dimensions.items()
    )


def _add_output_limitation_conditionals(schema: dict[str, Any]) -> None:
    for definition_name in ("ProtocolSchemaReceipt", "ConformanceProfile"):
        definition = _definition(schema, definition_name)
        if definition is None:
            continue
        definition.setdefault("allOf", []).extend(
            {
                "properties": {
                    "limitations": {
                        "contains": {
                            "type": "object",
                            "properties": {"code": {"const": code}},
                            "required": ["code"],
                        },
                        "minContains": 1,
                        "maxContains": 1,
                    }
                },
                "required": ["limitations"],
            }
            for code in sorted(M0101_RESERVED_LIMITATION_CODES)
        )


def _mark_runtime_relations(schema: dict[str, Any]) -> None:
    relations = {
        "ProtocolSchema": [
            "closed field/vocabulary/unit/rule references",
            "predicate value kind, unit, and controlled-term compatibility",
            "reference unit membership in allowed units",
            "module-reserved limitation codes",
        ],
        "ProtocolSchemaReceipt": [
            "protocol identifier/version/digest equals canonical embedded schema",
            "limited support and mandatory module limitations",
        ],
        "ConformanceProfile": [
            "decision, support, and human-review flag derive from typed issues",
            "mandatory module limitations",
        ],
        "MetadataDocument": ["entry paths are unique"],
        "ProvenanceRecord": ["all seven upstream control roles occur exactly once"],
    }
    for definition_name, invariants in relations.items():
        definition = _definition(schema, definition_name)
        if definition is not None:
            definition["x-glio-relationalInvariants"] = invariants


__all__ = [
    "CONTRACT_VERSION",
    "JSON_SCHEMA_DIALECT",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
]
