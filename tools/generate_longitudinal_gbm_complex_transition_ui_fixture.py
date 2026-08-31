"""Regenerate the UI's exact complex-transition backend lifecycle fixture."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from glio_proteogen.research.longitudinal_gbm_complex_transition.contracts import (
    ComplexTransitionReplayVerificationRequest,
)
from glio_proteogen.research.longitudinal_gbm_complex_transition.demo import (
    synthetic_demo_request,
)
from glio_proteogen.research.longitudinal_gbm_complex_transition.profile import (
    algorithm_profile,
)
from glio_proteogen.research.longitudinal_gbm_complex_transition.service import (
    analyze_longitudinal_gbm_complex_transition,
    verify_longitudinal_gbm_complex_transition_replay,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_OUTPUT = (
    _REPOSITORY_ROOT
    / "ui"
    / "tests"
    / "fixtures"
    / "longitudinal-gbm-complex-transition.json"
)
_BINDING_ERROR = "generated complex-transition lifecycle did not bind"


class FixtureIntegrityError(RuntimeError):
    """Raised when freshly computed backend surfaces do not bind and replay."""


def _render_fixture() -> bytes:
    profile = algorithm_profile()
    request = synthetic_demo_request()
    result = analyze_longitudinal_gbm_complex_transition(request)
    verification = verify_longitudinal_gbm_complex_transition_replay(
        ComplexTransitionReplayVerificationRequest(request=request, result=result)
    )
    if not (
        verification.verified
        and result.request_digest == request.request_digest
        and result.profile_digest == profile.profile_digest
        and verification.recomputed_request_digest == result.request_digest
        and verification.recomputed_result_digest == result.result_digest
        and verification.authoritative_profile_digest == profile.profile_digest
    ):
        raise FixtureIntegrityError(_BINDING_ERROR)
    payload = {
        "profile": profile.model_dump(mode="json"),
        "request": request.model_dump(mode="json"),
        "result": result.model_dump(mode="json"),
        "verification": verification.model_dump(mode="json"),
    }
    return (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare the checked-in fixture with a fresh backend lifecycle",
    )
    arguments = parser.parse_args()
    expected = _render_fixture()
    if arguments.check:
        try:
            actual = _OUTPUT.read_bytes()
        except FileNotFoundError:
            sys.stderr.write(f"fixture does not exist: {_OUTPUT}\n")
            return 1
        if actual != expected:
            sys.stderr.write(
                "complex-transition UI fixture is stale; regenerate it with "
                "`uv run python tools/generate_longitudinal_gbm_complex_transition_ui_fixture.py`\n"
            )
            return 1
        sys.stdout.write(f"complex-transition UI fixture is current: {_OUTPUT}\n")
        return 0
    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT.write_bytes(expected)
    sys.stdout.write(f"wrote complex-transition UI fixture: {_OUTPUT}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
