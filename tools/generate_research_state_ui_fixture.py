"""Regenerate the UI's backend-authored GLIO-ECGI replay fixture."""

from __future__ import annotations

import json
from pathlib import Path

from glio_proteogen.research.proteogenomic_state import (
    ReplayVerificationRequest,
    algorithm_profile,
    analyze_proteogenomic_state,
    synthetic_demo_request,
    verify_proteogenomic_replay,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_OUTPUT = _REPOSITORY_ROOT / "ui" / "tests" / "fixtures" / "proteogenomic-state.json"
_VERIFICATION_ERROR = "generated research-state fixture did not verify"


def main() -> None:
    """Write one internally verified profile/request/result/replay document."""

    request = synthetic_demo_request()
    result = analyze_proteogenomic_state(request)
    verification = verify_proteogenomic_replay(
        ReplayVerificationRequest(request=request, result=result)
    )
    if not verification.verified:
        raise RuntimeError(_VERIFICATION_ERROR)
    payload = {
        "profile": algorithm_profile().model_dump(mode="json"),
        "request": request.model_dump(mode="json"),
        "result": result.model_dump(mode="json"),
        "verification": verification.model_dump(mode="json"),
    }
    _OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
