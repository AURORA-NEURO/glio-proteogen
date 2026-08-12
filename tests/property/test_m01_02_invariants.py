"""Generative and metamorphic invariants for M01-02 identity and lineage policy."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from dataclasses import asdict
from itertools import product
from pathlib import Path
from typing import Any, cast

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m01_02.v1 import ReconcileIdentityLineageRequest
from glio_proteogen.kernel.models import Identifier
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.policy import (
    ENTITY_KINDS,
    ORDINARY_TRANSITIONS,
    ordinary_transition_allowed,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.solver import _analyze

EXPECTED_KINDS = (
    "aliquot",
    "analyte",
    "derived_object",
    "patient",
    "run",
    "section",
    "specimen",
)
EXPECTED_OPERATIONS = (
    "acquired_from",
    "collected_from",
    "computed_from",
    "extracted_from",
    "sectioned_from",
    "subdivided_from",
)
IDENTIFIER_ADAPTER = TypeAdapter(Identifier)
ROOT = Path(__file__).parents[2]
SCENARIO_PATH = ROOT / "tests" / "fixtures" / "m01_02" / "scenarios.json"


def _scenario_corpus() -> dict[str, Any]:
    return cast("dict[str, Any]", strict_json_loads(SCENARIO_PATH.read_bytes()))


def _analysis(request: dict[str, Any]):
    return _analyze(cast("Any", request))


def _artifact(role: str) -> dict[str, str]:
    digest_character = {
        "entity": "a",
        "assertion": "b",
        "operation": "c",
        "control": "e",
    }[role]
    return {
        "artifact_id": f"artifact.synthetic.{role}",
        "version": "1.0.0",
        "digest": f"sha256:{digest_character * 64}",
        "media_type": "application/json",
    }


def _entity(entity_id: str, kind: str) -> dict[str, Any]:
    return {
        "entity_id": entity_id,
        "kind": kind,
        "identity_tokens": [],
        "composition": "unknown",
        "evidence": [_artifact("entity")],
    }


def _policy(*, maximum_depth: int = 64, maximum_component_size: int = 256) -> dict[str, Any]:
    return {
        "policy_id": "policy.synthetic.generated",
        "version": "1.0.0",
        "max_component_size": maximum_component_size,
        "maximum_depth": maximum_depth,
        "allow_mixed_subject_pooling": False,
        "require_demultiplex_authority": True,
        "allowed_operation_kinds": sorted(
            {operation for operation, _parent, _child in ORDINARY_TRANSITIONS}
        ),
    }


def _context() -> dict[str, Any]:
    control_evidence = _artifact("control")
    accepted = {
        "decision_id": "decision.synthetic.accepted",
        "state": "accepted",
        "policy_version": "1.0.0",
        "evidence": control_evidence,
    }
    return {
        "request_id": "request.synthetic.generated",
        "actor_id": "actor.synthetic.test",
        "occurred_at": "2026-08-11T00:00:00Z",
        "references": {
            "approved_configuration": {
                **accepted,
                "decision_id": "decision.synthetic.approved-configuration",
            },
            "identity_authority": {
                "decision_id": "authority.synthetic.v1",
                "state": "accepted",
                "policy_version": "1.0.0",
                "evidence": control_evidence,
            },
            "provenance": {**accepted, "decision_id": "decision.synthetic.provenance"},
            "consent": {
                **accepted,
                "decision_id": "decision.synthetic.consent",
                "state": "granted",
            },
            "quality": {**accepted, "decision_id": "decision.synthetic.quality"},
            "support": {**accepted, "decision_id": "decision.synthetic.support"},
            "intended_use": {
                **accepted,
                "decision_id": "decision.synthetic.intended-use",
            },
        },
    }


def _operation(
    operation_id: str,
    kind: str,
    source: str,
    target: str,
) -> dict[str, Any]:
    return {
        "operation_id": operation_id,
        "kind": kind,
        "source_entity_ids": [source],
        "target_entity_ids": [target],
        "authority_decision_id": "authority.synthetic.v1",
        "policy_version": "1.0.0",
        "evidence": [_artifact("operation")],
        "mixed_subject": False,
    }


def _component_for(analysis: Any, member: str) -> Any:
    matches = [component for component in analysis.components if member in component.members]
    assert len(matches) == 1
    return matches[0]


@settings(max_examples=128, deadline=None)
@given(
    operation=st.sampled_from((*EXPECTED_OPERATIONS, "derived_from", "same_as", "unknown")),
    parent=st.sampled_from(EXPECTED_KINDS),
    child=st.sampled_from(EXPECTED_KINDS),
)
def test_transition_decision_is_exact_membership(
    operation: str,
    parent: str,
    child: str,
) -> None:
    assert ordinary_transition_allowed(operation, parent, child) is (
        (operation, parent, child) in ORDINARY_TRANSITIONS
    )


def test_transition_matrix_is_total_and_contains_no_implicit_fallthrough() -> None:
    matrix = tuple(product(EXPECTED_OPERATIONS, EXPECTED_KINDS, EXPECTED_KINDS))
    allowed = {transition for transition in matrix if ordinary_transition_allowed(*transition)}

    assert set(EXPECTED_KINDS) == ENTITY_KINDS
    assert allowed == ORDINARY_TRANSITIONS
    assert len(matrix) == len(EXPECTED_OPERATIONS) * len(EXPECTED_KINDS) ** 2


@pytest.mark.parametrize(
    "value",
    [
        "",
        " ",
        " sample",
        "sample ",
        "sample\t",
        "sample\n",
        "s\u0430mple",  # Cyrillic small a, not ASCII a.
        "samp\u200ble",  # Zero-width space.
        "sample\u202eid",  # Right-to-left override.
        "sample\u2066id",  # Left-to-right isolate.
        "\u00e9",
        "e\u0301",
        "\uff33\uff21\uff2d\uff30\uff2c\uff25",  # Full-width homoglyphs.
    ],
)
def test_identifier_boundary_rejects_whitespace_confusables_and_bidi(value: str) -> None:
    with pytest.raises(ValidationError):
        IDENTIFIER_ADAPTER.validate_python(value, strict=True)


@settings(max_examples=64, deadline=None)
@given(
    base=st.from_regex(r"[A-Za-z][A-Za-z0-9._:-]{0,30}", fullmatch=True),
    affix=st.sampled_from((" ", "\t", "\n", "\r", "\u00a0", "\u200b")),
    prefix=st.booleans(),
)
def test_identifier_boundary_never_strips_or_normalizes(
    base: str,
    affix: str,
    *,
    prefix: bool,
) -> None:
    hostile = f"{affix}{base}" if prefix else f"{base}{affix}"

    with pytest.raises(ValidationError):
        IDENTIFIER_ADAPTER.validate_python(hostile, strict=True)


@settings(max_examples=64, deadline=None)
@given(value=st.from_regex(r"[A-Za-z][A-Za-z0-9._:-]{0,127}", fullmatch=True))
def test_valid_opaque_ascii_identifiers_are_byte_preserved(value: str) -> None:
    assert IDENTIFIER_ADAPTER.validate_python(value, strict=True) == value


@pytest.mark.parametrize(
    "scenario",
    _scenario_corpus()["scenarios"],
    ids=lambda scenario: scenario["case_id"],
)
def test_locked_solver_scenarios(scenario: dict[str, Any]) -> None:
    analysis = _analysis(scenario["request"])
    expected = scenario["expected"]

    assert [issue.code for issue in analysis.issues] == expected["issue_codes"]
    if "edge_count" in expected:
        assert len(analysis.lineage_edges) == expected["edge_count"]
    if "concordance" in expected:
        actual_concordance = asdict(analysis.concordance)
        assert {
            key: actual_concordance[key] for key in expected["concordance"]
        } == expected["concordance"]
    bindings = dict(analysis.subject_bindings)
    for entity_id, subjects in expected.get("bindings", {}).items():
        assert bindings[entity_id] == tuple(subjects)
    for members in expected.get("same_components", []):
        component_ids = {_component_for(analysis, member).component_id for member in members}
        assert len(component_ids) == 1
    for left, right in expected.get("distinct_components", []):
        assert _component_for(analysis, left).component_id != _component_for(
            analysis, right
        ).component_id
    for member in expected.get("quarantined_members", []):
        assert _component_for(analysis, member).quarantined is True


@pytest.mark.parametrize(
    "scenario",
    _scenario_corpus()["scenarios"],
    ids=lambda scenario: scenario["case_id"],
)
def test_locked_scenario_contract_expectations_are_exact(
    scenario: dict[str, Any],
) -> None:
    encoded = json.dumps(scenario["request"], separators=(",", ":"))
    expectation = scenario["contract_expectation"]

    if expectation["accepted"]:
        request = ReconcileIdentityLineageRequest.model_validate_json(encoded)
        assert request.operation == "reconcile"
        assert request.contract_version == "1.0.0"
        return

    with pytest.raises(ValidationError) as captured:
        ReconcileIdentityLineageRequest.model_validate_json(encoded)
    assert expectation["error_contains"] in str(captured.value)


@pytest.mark.parametrize(
    "scenario",
    _scenario_corpus()["scenarios"],
    ids=lambda scenario: scenario["case_id"],
)
def test_scenario_order_never_changes_analysis(scenario: dict[str, Any]) -> None:
    request = scenario["request"]
    reversed_request = copy.deepcopy(request)
    for field in (
        "entities",
        "assertions",
        "lineage_operations",
        "concordance_observations",
    ):
        reversed_request[field].reverse()

    assert _analysis(reversed_request) == _analysis(request)


@pytest.mark.parametrize(
    "scenario",
    _scenario_corpus()["scenarios"],
    ids=lambda scenario: scenario["case_id"],
)
def test_solver_never_mutates_request(scenario: dict[str, Any]) -> None:
    request = copy.deepcopy(scenario["request"])
    before = copy.deepcopy(request)

    _analysis(request)

    assert request == before


def _derived_chain(edge_count: int, *, maximum_depth: int = 64) -> dict[str, Any]:
    entities = [
        _entity(f"obj-{index:03d}", "derived_object")
        for index in range(edge_count + 1)
    ]
    operations = [
        _operation(
            f"op-{index:03d}",
            "computed_from",
            f"obj-{index:03d}",
            f"obj-{index + 1:03d}",
        )
        for index in range(edge_count)
    ]
    return {
        "policy": _policy(maximum_depth=maximum_depth),
        "context": _context(),
        "entities": entities,
        "assertions": [],
        "lineage_operations": operations,
        "concordance_observations": [],
    }


@pytest.mark.parametrize(
    ("edge_count", "depth_exceeded"),
    [(0, False), (1, False), (8, False), (64, False), (65, True)],
    ids=("zero", "one", "n", "maximum", "maximum_plus_one"),
)
def test_lineage_depth_zero_one_n_maximum_and_first_excess(
    edge_count: int,
    *,
    depth_exceeded: bool,
) -> None:
    analysis = _analysis(_derived_chain(edge_count))

    assert ("lineage.depth_exceeded" in {issue.code for issue in analysis.issues}) is (
        depth_exceeded
    )


def _identity_component(size: int, *, maximum_component_size: int = 4) -> dict[str, Any]:
    entities = [
        _entity(f"spc-{index:03d}", "specimen")
        for index in range(size)
    ]
    assertions = [
        {
            "assertion_id": f"assert-{index:03d}",
            "assertion_type": "same_as",
            "left_entity_id": f"spc-{index:03d}",
            "right_entity_id": f"spc-{index + 1:03d}",
            "authority_decision_id": "authority.synthetic.v1",
            "policy_version": "1.0.0",
            "evidence": [_artifact("assertion")],
        }
        for index in range(max(0, size - 1))
    ]
    return {
        "policy": _policy(maximum_component_size=maximum_component_size),
        "context": _context(),
        "entities": entities,
        "assertions": assertions,
        "lineage_operations": [],
        "concordance_observations": [],
    }


@pytest.mark.parametrize(
    ("size", "capacity_exceeded"),
    [(0, False), (1, False), (3, False), (4, False), (5, True)],
    ids=("zero", "one", "n", "maximum", "maximum_plus_one"),
)
def test_component_size_zero_one_n_maximum_and_first_excess(
    size: int,
    *,
    capacity_exceeded: bool,
) -> None:
    analysis = _analysis(_identity_component(size))

    assert ("component.capacity_exceeded" in {issue.code for issue in analysis.issues}) is (
        capacity_exceeded
    )


def test_hash_seed_does_not_change_locked_analysis() -> None:
    request = _identity_component(4)
    script = "\n".join(
        (
            "from dataclasses import asdict",
            "import json",
            "from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage "
            "import solver",
            f"request = json.loads({json.dumps(json.dumps(request))})",
            "result = asdict(solver._analyze(request))",
            "print(json.dumps(result, sort_keys=True, separators=(',', ':')))",
        )
    )
    outputs = []
    for seed in ("0", "1", "31337"):
        environment = os.environ.copy()
        environment["PYTHONHASHSEED"] = seed
        completed = subprocess.run(  # noqa: S603
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=environment,
        )
        outputs.append(completed.stdout)

    assert len(set(outputs)) == 1
