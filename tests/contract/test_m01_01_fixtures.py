"""Machine-readable fixture conformance for M01-01."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from glio_proteogen.contracts.m01_01.canonical import identity_binding_digest
from glio_proteogen.contracts.m01_01.schema import (
    JSON_SCHEMA_DIALECT,
    ContractName,
    contract_json_schema,
)
from glio_proteogen.contracts.m01_01.v1 import EvaluateMetadataRequest
from tests.m01_01_support import (
    FIXTURE_DIRECTORY,
    load_case,
    load_manifest,
    load_protocol_schema,
    load_request,
)

pytestmark = pytest.mark.contract


def _cases(expected: str) -> list[dict[str, object]]:
    return [case for case in load_manifest()["cases"] if case["expected"] == expected]


_TARGET_SCHEMAS: dict[str, tuple[ContractName, str | None]] = {
    "Cardinality": ("protocol-schema", "Cardinality"),
    "ExecutionContext": ("request", "ExecutionContext"),
    "FieldSpecification": ("protocol-schema", "FieldSpecification"),
    "M0101Request": ("request", None),
    "MetadataDocument": ("metadata-document", None),
    "NumericBounds": ("protocol-schema", "NumericBounds"),
    "ObservedValue": ("metadata-document", "ObservedValue"),
    "ProtocolSchema": ("protocol-schema", None),
}


def _fixture_json_schema(target: str) -> dict[str, Any]:
    contract_name, definition_name = _TARGET_SCHEMAS[target]
    document = contract_json_schema(contract_name)
    if definition_name is None:
        return document
    return {
        "$schema": JSON_SCHEMA_DIALECT,
        "$defs": document["$defs"],
        "$ref": f"#/$defs/{definition_name}",
    }


def _standard_schema_errors(case: dict[str, object]) -> list[object]:
    raw = (FIXTURE_DIRECTORY / str(case["file"])).read_text(encoding="utf-8")
    # The standard library parse is deliberate: Draft 2020-12 cannot detect duplicate
    # keys or reject non-finite JSON spellings, so those remain strict-runtime evidence.
    payload = json.loads(raw)
    validator = Draft202012Validator(
        _fixture_json_schema(str(case["target"])),
        format_checker=FormatChecker(),
    )
    return list(validator.iter_errors(payload))


def test_manifest_is_closed_over_fixture_directory() -> None:
    manifest = load_manifest()
    cases = manifest["cases"]
    declared = {case["file"] for case in cases}
    actual = {path.name for path in FIXTURE_DIRECTORY.glob("*.json")} - {"manifest.json"}

    assert manifest["module_id"] == "GLIO-PROTEOGEN-M01-01"
    assert manifest["data_classification"] == "synthetic_non_clinical"
    assert manifest["strict_json"] is True
    assert len({case["case_id"] for case in cases}) == len(cases)
    assert declared == actual


@pytest.mark.parametrize("case", _cases("accept"), ids=lambda case: case["case_id"])
def test_valid_fixtures_satisfy_their_declared_contract(case: dict[str, object]) -> None:
    assert load_case(case) is not None


@pytest.mark.parametrize("case", _cases("reject"), ids=lambda case: case["case_id"])
def test_invalid_fixtures_fail_at_the_declared_boundary(case: dict[str, object]) -> None:
    expected_error = ValueError if case["phase"] == "json" else ValidationError
    with pytest.raises(expected_error):
        load_case(case)


@pytest.mark.parametrize("case", _cases("reject"), ids=lambda case: case["case_id"])
def test_invalid_fixture_is_rejected_by_standard_schema_or_authoritative_runtime(
    case: dict[str, object],
) -> None:
    standard_errors = _standard_schema_errors(case)
    runtime_rejected = False
    try:
        load_case(case)
    except (ValueError, ValidationError):
        runtime_rejected = True

    assert standard_errors or runtime_rejected


@pytest.mark.parametrize(
    "filename",
    [
        "identity_shape.invalid.json",
        "duplicate_allowed_units.invalid.json",
        "duplicate_missingness.invalid.json",
    ],
)
def test_expressible_field_invariants_fail_standard_draft_2020_12_schema(
    filename: str,
) -> None:
    case = next(case for case in _cases("reject") if case["file"] == filename)

    assert _standard_schema_errors(case)


def test_fixture_names_encode_expected_contract_status() -> None:
    for case in load_manifest()["cases"]:
        status = "valid" if case["expected"] == "accept" else "invalid"
        assert Path(case["file"]).name.endswith(f".{status}.json")


@pytest.mark.parametrize(
    "filename",
    [
        "evaluate_conformant.valid.json",
        "evaluate_quarantine.valid.json",
        "evaluate_reject.valid.json",
        "evaluate_unresolved.valid.json",
    ],
)
def test_evaluation_fixture_lineage_decision_is_bound_to_identity_key_evidence(
    filename: str,
) -> None:
    request = load_request(filename)
    assert isinstance(request, EvaluateMetadataRequest)

    assert request.context.references.identity_lineage.binding_digest == (
        identity_binding_digest(load_protocol_schema(), request.document)
    )
