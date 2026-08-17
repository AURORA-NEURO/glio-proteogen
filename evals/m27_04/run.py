"""Run the locked M27-04 gateway safety and determinism evaluator."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from fastapi.testclient import TestClient

if __package__:
    from evals.m27_04.fixture import build_request
else:
    from fixture import build_request  # type: ignore[no-redef]

from glio_proteogen.contracts.m27_04 import (
    AuthorizationDecision,
    GatewayStatus,
    JobStatus,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c20_biomarker_panel.m27_04_api_sdk_cli_gateway.api import create_app
from glio_proteogen.modules.c20_biomarker_panel.m27_04_api_sdk_cli_gateway.engine import (
    M2704AuthorizationError,
    M2704GatewayEngine,
    M2704ReplayError,
)
from glio_proteogen.modules.c20_biomarker_panel.m27_04_api_sdk_cli_gateway.plugin import (
    GatewaySubmission,
    M2704Plugin,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M27-04"
SCENARIO_ID: Final = "m2704.gateway.safety.v1"
EXPECTED_CHECK_COUNT: Final = 10
EXPECTED_SCHEMA_COUNT: Final = 12
HTTP_OK: Final = 200
HTTP_UNPROCESSABLE_CONTENT: Final = 422


@dataclass(frozen=True, slots=True)
class EvalCheck:
    """One executable evaluator assertion."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    """Serializable locked evaluator output."""

    module_id: str
    scenario_id: str
    fixture_digest: str
    checks: tuple[EvalCheck, ...]
    passed: bool


class InvalidEvaluatorMatrixError(RuntimeError):
    """The executable matrix changed without updating its locked count."""


def _check(name: str, condition: bool, detail: str) -> EvalCheck:  # noqa: FBT001
    return EvalCheck(name=name, passed=condition, detail=detail)


def run_evaluator() -> EvaluationReport:
    """Exercise supported, abstained, replay, interface, and tamper paths."""

    request = build_request()
    fixture_digest = sha256_digest(request.model_dump(mode="json"))
    engine = M2704GatewayEngine()
    baseline = engine.publish(request)
    denied = request.model_copy(
        update={
            "authorizations": (
                request.authorizations[0].model_copy(
                    update={"decision": AuthorizationDecision.DENY}
                ),
            )
        }
    )
    queued = request.model_copy(
        update={"jobs": (request.jobs[0].model_copy(update={"status": JobStatus.QUEUED}),)}
    )
    rejected_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={
                    "support": request.context.references.support.model_copy(
                        update={"state": "rejected"}
                    )
                }
            )
        }
    )
    plugin = M2704Plugin()
    checks = [
        _check(
            "supported_publication",
            baseline.status is GatewayStatus.PUBLISHED and baseline.access_surface is not None,
            f"status={baseline.status.value}",
        ),
        _check(
            "deterministic_digest",
            engine.publish(request) == baseline,
            "repeated publication is byte-equivalent",
        ),
        _check(
            "supported_replay",
            engine.replay(baseline) == baseline,
            "canonical result replay verified",
        ),
        _check(
            "authorization_abstention",
            engine.publish(denied).status is GatewayStatus.ABSTAINED,
            "denied operation has no access surface",
        ),
        _check(
            "unresolved_job_abstention",
            engine.publish(queued).status is GatewayStatus.ABSTAINED,
            "queued asynchronous job abstains safely",
        ),
        _check(
            "control_preflight_fail_closed",
            _preflight_rejects(engine, request.model_copy(update={"context": rejected_context})),
            "rejected support control cannot publish",
        ),
        _check(
            "sealed_plugin_parity",
            plugin.run(plugin.validate(GatewaySubmission(request.model_dump_json()))) == baseline,
            "plugin accepts only validated token and preserves service result",
        ),
        _check(
            "tamper_replay_rejected",
            _tamper_rejected(baseline),
            "forged result identity cannot pass canonical replay",
        ),
        _check(
            "strict_schema_metadata",
            len(contract_json_schemas()) == EXPECTED_SCHEMA_COUNT
            and all(
                schema["x-glio-contract"]["explicitAbstentionRequired"]
                for schema in contract_json_schemas().values()
            ),
            "all contract schemas carry explicit abstention metadata",
        ),
        _check(
            "api_publish_and_invalid_json",
            _api_paths(request.model_dump(mode="json")),
            "API publication succeeds and malformed JSON is rejected without details",
        ),
    ]
    # Keep the evaluator itself strict about its locked matrix shape.
    if len(checks) != EXPECTED_CHECK_COUNT:
        raise InvalidEvaluatorMatrixError(  # noqa: TRY003
            f"expected {EXPECTED_CHECK_COUNT} checks, got {len(checks)}"
        )
    return EvaluationReport(
        module_id=MODULE_ID,
        scenario_id=SCENARIO_ID,
        fixture_digest=fixture_digest,
        checks=tuple(checks),
        passed=all(item.passed for item in checks),
    )


def _preflight_rejects(engine: M2704GatewayEngine, request: object) -> bool:
    try:
        engine.publish(request)  # type: ignore[arg-type]
    except M2704AuthorizationError:
        return True
    return False


def _tamper_rejected(result: object) -> bool:
    try:
        forged = result.model_copy(update={"result_id": "gateway.m2704.forged"})  # type: ignore[attr-defined]
        M2704GatewayEngine().replay(forged)
    except (M2704ReplayError, ValueError, TypeError):
        return True
    return False


def _api_paths(payload: dict[str, object]) -> bool:
    with TestClient(create_app()) as client:
        published = client.post("/v1/modules/M27-04/publish", json=payload)
        malformed = client.post("/v1/modules/M27-04/publish", content=b"not-json")
    return published.status_code == HTTP_OK and malformed.status_code == HTTP_UNPROCESSABLE_CONTENT


def main(argv: list[str] | None = None) -> int:
    """Print the evaluator report and return a CI-friendly status."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    report = run_evaluator()
    rendered = json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0 if report.passed else 1


__all__ = ["EvalCheck", "EvaluationReport", "main", "run_evaluator"]


if __name__ == "__main__":
    raise SystemExit(main())
