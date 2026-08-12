"""Shared fixture access for M01-01 evidence code."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_01.v1 import (
    Cardinality,
    ExecutionContext,
    FieldSpecification,
    M0101Request,
    MetadataDocument,
    NumericBounds,
    ObservedValue,
    ProtocolSchema,
    RegisterProtocolRequest,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "m01_01"
MANIFEST_PATH = FIXTURE_DIRECTORY / "manifest.json"

TARGET_ADAPTERS = {
    "Cardinality": TypeAdapter(Cardinality),
    "ExecutionContext": TypeAdapter(ExecutionContext),
    "FieldSpecification": TypeAdapter(FieldSpecification),
    "M0101Request": TypeAdapter(M0101Request),
    "MetadataDocument": TypeAdapter(MetadataDocument),
    "NumericBounds": TypeAdapter(NumericBounds),
    "ObservedValue": TypeAdapter(ObservedValue),
    "ProtocolSchema": TypeAdapter(ProtocolSchema),
}


def load_json(path: Path) -> Any:
    """Load one bounded RFC 8259 document through the production decoder."""

    return strict_json_loads(path.read_bytes())


def load_manifest() -> dict[str, Any]:
    return load_json(MANIFEST_PATH)


def load_case(case: dict[str, Any]) -> Any:
    path = FIXTURE_DIRECTORY / case["file"]
    load_json(path)
    return TARGET_ADAPTERS[case["target"]].validate_json(path.read_bytes())


def load_request(filename: str) -> M0101Request:
    path = FIXTURE_DIRECTORY / filename
    load_json(path)
    return TypeAdapter(M0101Request).validate_json(path.read_bytes())


def load_protocol_schema() -> ProtocolSchema:
    request = load_request("register_minimal.valid.json")
    assert isinstance(request, RegisterProtocolRequest)
    return request.protocol_schema
