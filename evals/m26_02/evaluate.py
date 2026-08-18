"""Executable M26-02 scenario matrix and independent replay audit."""

# Evaluator assertions are executable evidence checks, not production control flow.
# ruff: noqa: S101, T201, TRY003

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from evals.m26_02.fixture import request
from glio_proteogen.contracts.m26_02 import LineageStatus, result_payload_digest
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c26_proteomics.m26_02_data_model_lineage_service import (
    LineageAuthorizationError,
    LineageReplayError,
    M2602LineagePlugin,
    M2602LineageService,
)

Scenario = Callable[[], dict[str, Any]]


def _supported() -> dict[str, Any]:
    service = M2602LineageService()
    result = service.execute(request())
    assert result.status is LineageStatus.BUILT
    service.verify(result)
    return {"status": result.status.value, "resultDigest": result.result_digest}


def _bad_digest() -> dict[str, Any]:
    result = M2602LineageService().execute(request(bad_digest=True))
    assert result.status is LineageStatus.ABSTAINED
    return {
        "status": result.status.value,
        "findingCodes": sorted(item.code.value for item in result.findings),
    }


def _cycle() -> dict[str, Any]:
    result = M2602LineageService().execute(request(cycle=True))
    assert result.status is LineageStatus.ABSTAINED
    assert any(item.code.value == "broken_link" for item in result.findings)
    return {
        "status": result.status.value,
        "findingCodes": [item.code.value for item in result.findings],
    }


def _denied_control() -> dict[str, Any]:
    try:
        M2602LineageService().execute(request(denied_consent=True))
    except LineageAuthorizationError:
        return {"authorization": "rejected-before-traversal"}
    raise AssertionError("denied consent must fail closed")


def _plugin_parity() -> dict[str, Any]:
    service = M2602LineageService()
    plugin = M2602LineagePlugin(service)
    candidate = request()
    raw = candidate.model_dump_json()
    result = plugin.run(plugin.validate(raw))
    direct = service.execute(candidate)
    assert result.result_digest == direct.result_digest
    return {"resultDigest": result.result_digest, "parity": True}


def _tamper_replay() -> dict[str, Any]:
    service = M2602LineageService()
    result = service.execute(request())
    tampered = result.model_copy(update={"result_id": "tampered-result"})
    try:
        service.verify(tampered)
    except (ValidationError, LineageReplayError):
        return {"tamper": "rejected"}
    raise AssertionError("tampered result must not verify")


def _semantic_tamper_replay() -> dict[str, Any]:
    service = M2602LineageService()
    result = service.execute(request())
    forged = result.model_copy(
        update={"provenance": result.provenance.model_copy(update={"activity_id": "forged"})}
    )
    forged = type(forged).model_construct(
        **{**forged.__dict__, "result_digest": result_payload_digest(forged)}
    )
    try:
        service.verify(forged)
    except LineageReplayError:
        return {"tamper": "self-rehashed semantic mutation rejected"}
    raise AssertionError("self-rehashed provenance must not verify")


def _determinism() -> dict[str, Any]:
    service = M2602LineageService()
    first = service.execute(request())
    second = service.execute(request())
    assert first.result_digest == second.result_digest
    return {"resultDigest": first.result_digest, "repeatable": True}


SCENARIOS: dict[str, Scenario] = {
    "supported": _supported,
    "bad_graph_digest": _bad_digest,
    "cycle": _cycle,
    "denied_control": _denied_control,
    "plugin_parity": _plugin_parity,
    "tamper_replay": _tamper_replay,
    "semantic_tamper_replay": _semantic_tamper_replay,
    "determinism": _determinism,
}


def evaluate() -> dict[str, Any]:
    """Run all frozen scenarios and return a digestible evidence document."""

    results = {name: scenario() for name, scenario in SCENARIOS.items()}
    fixture_digest = sha256_digest(
        {
            "module": "GLIO-PROTEOGEN-M26-02",
            "contract": "0.1.0-provisional",
            "scenarioNames": tuple(SCENARIOS),
            "supportedRequest": request().model_dump(mode="json"),
        }
    )
    return {
        "moduleId": "GLIO-PROTEOGEN-M26-02",
        "scenarioCount": len(results),
        "passed": len(results),
        "fixtureDigest": fixture_digest,
        "scenarios": results,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(evaluate(), indent=2, sort_keys=True))
