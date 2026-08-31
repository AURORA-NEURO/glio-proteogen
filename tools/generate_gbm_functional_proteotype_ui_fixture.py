"""Regenerate the UI's exact GBM functional-proteotype backend receipt fixture."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from glio_proteogen.research.gbm_functional_proteotype import (
    ReplayVerificationRequest,
    algorithm_profile,
    analyze_functional_proteotype,
    synthetic_demo_request,
    verify_replay,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_OUTPUT = (
    _REPOSITORY_ROOT
    / "ui"
    / "tests"
    / "fixtures"
    / "gbm-functional-proteotype.json"
)


class FixtureIntegrityError(RuntimeError):
    """Raised when freshly computed backend surfaces are internally incoherent."""


def _render_fixture() -> bytes:
    """Build and serialize one internally verified backend receipt."""

    profile = algorithm_profile()
    demo = synthetic_demo_request()
    analysis = analyze_functional_proteotype(demo)
    verification = verify_replay(
        ReplayVerificationRequest(request=demo, result=analysis)
    )
    if not (
        verification.verified
        and profile.demo_request_digest == analysis.request_digest
        and profile.profile_digest == analysis.profile_digest
    ):
        raise FixtureIntegrityError

    payload = {
        "profile": profile.model_dump(mode="json"),
        "demo": demo.model_dump(mode="json"),
        "analysis": analysis.model_dump(mode="json"),
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
    """Write the canonical fixture, or fail if the checked-in fixture is stale."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare the fixture with a fresh backend receipt without modifying it",
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
                "GBM functional-proteotype UI fixture is stale; regenerate it with "
                "`uv run python tools/generate_gbm_functional_proteotype_ui_fixture.py`\n"
            )
            return 1
        sys.stdout.write(f"GBM functional-proteotype UI fixture is current: {_OUTPUT}\n")
        return 0

    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT.write_bytes(expected)
    sys.stdout.write(f"wrote GBM functional-proteotype UI fixture: {_OUTPUT}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
