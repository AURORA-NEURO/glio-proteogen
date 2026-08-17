"""Run the locked M27-05 evaluator matrix."""

from __future__ import annotations

import json
import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from glio_proteogen.contracts.m27_05 import TelemetryStatus
from glio_proteogen.modules.c27_complex_activity.m27_05_observability_telemetry import (
    M2705Plugin,
    M2705ReplayError,
    M2705Service,
    TelemetrySubmission,
    emit_search_quant_observability_telemetry,
)

if __package__:
    from .fixture import build_request
else:
    from evals.m27_05.fixture import build_request

_EXPECTED_SAMPLE_COUNT = 9


def run() -> dict[str, object]:
    request = build_request()
    result = emit_search_quant_observability_telemetry(request)
    replay = M2705Service().replay(result)
    plugin = M2705Plugin()
    token = plugin.validate(TelemetrySubmission(request))
    plugin_result = plugin.run(token)
    rejected = False
    forged = result.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    try:
        M2705Service().replay(forged)
    except (M2705ReplayError, ValueError):
        rejected = True
    unsupported = emit_search_quant_observability_telemetry(
        build_request("m2705.request.unsupported", upstream_media_type="application/json")
    )
    checks = {
        "emitted": result.status is TelemetryStatus.EMITTED,
        "stream_samples": result.telemetry_stream is not None
        and len(result.telemetry_stream.samples) == _EXPECTED_SAMPLE_COUNT,
        "replay": replay == result,
        "plugin_parity": plugin_result == result,
        "tamper_rejected": rejected,
        "unsupported_abstained": unsupported.status is TelemetryStatus.ABSTAINED,
        "unsupported_no_stream": unsupported.telemetry_stream is None,
    }
    return {
        "module_id": "GLIO-PROTEOGEN-M27-05",
        "checks": checks,
        "passed": all(checks.values()),
    }


def main() -> int:
    report = run()
    print(json.dumps(report, sort_keys=True))  # noqa: T201
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "run"]
