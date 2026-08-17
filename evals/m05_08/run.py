"""Executable M05-08 release-packaging evaluation scenarios."""

# ruff: noqa: TRY003

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from tests.modules.c05_ptm_localization.test_m05_08_release_packaging import (
    _valid_fixture,
    _Verifier,
)

from glio_proteogen.contracts.m05_08 import PtmLocalizationReleaseDisposition
from glio_proteogen.modules.c05_ptm_localization.m05_08_release_packaging import (
    M0508PtmLocalizationReleaseEngine,
)


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    contract_version: str
    authorized_without_verifier: str
    authorized_with_verifier: str
    tamper_verified: bool
    safe_failure: bool
    passed: bool


def evaluate() -> EvaluationReport:
    request, artifacts = _valid_fixture()
    quarantined = M0508PtmLocalizationReleaseEngine().build(request, artifacts)
    verifier = _Verifier()
    released = M0508PtmLocalizationReleaseEngine(verifier).build(request, artifacts)
    if released.package_bytes is None:
        raise RuntimeError("approved fixture did not build a package")
    verification = M0508PtmLocalizationReleaseEngine(verifier).verify(
        released.result,
        released.package_bytes,
    )
    return EvaluationReport(
        module_id="GLIO-PROTEOGEN-M05-08",
        contract_version="0.1.0-provisional",
        authorized_without_verifier=quarantined.result.disposition.value,
        authorized_with_verifier=released.result.disposition.value,
        tamper_verified=verification.verified,
        safe_failure=(
            quarantined.result.disposition is PtmLocalizationReleaseDisposition.QUARANTINED
            and quarantined.package_bytes is None
        ),
        passed=(
            quarantined.result.disposition is PtmLocalizationReleaseDisposition.QUARANTINED
            and released.result.disposition is PtmLocalizationReleaseDisposition.RELEASED
            and verification.verified
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = evaluate()
    rendered = json.dumps(asdict(report), indent=2, sort_keys=True)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    sys.stdout.write(rendered + "\n")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["EvaluationReport", "evaluate", "main"]
