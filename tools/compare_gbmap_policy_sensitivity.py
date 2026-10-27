"""Compare explicit GBmap policies on matched private held support.

The strict sensitivity plan is read before one selected-fold recovery. The
original point benchmark and matched-support reconstruction each solve points
on that same context; source lineages are recovered only once. Stdout contains
only a bounded aggregate receipt. It selects no policy and certifies neither
calibration nor privacy merely from aggregate formatting. Parent reconciliation
matches aggregate results; that comparison cannot authenticate saved per-case
assignments. Matched support is measured in the repeated casewise pass.
"""

# ruff: noqa: TRY003 -- stable sanitized errors at the private boundary

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Never

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.research.gbmap_mixture_benchmark import score_replayed_fold
from glio_proteogen.research.gbmap_policy_sensitivity import (
    MatchedPolicySensitivityReceipt,
    PolicySensitivityError,
    score_matched_policy_sensitivity,
)
from glio_proteogen.research.proteogenomic_state.cancellation import InferenceCancelledError
from tools import fit_gbmap_development_candidate as fit_driver
from tools.benchmark_gbmap_selected_fold import _load_plan
from tools.replay_gbmap_selected_fold import recover_selected_fold_context

MAX_OUTPUT_BYTES = 8 * 1024 * 1024


def canonical_receipt_bytes(receipt: MatchedPolicySensitivityReceipt) -> bytes:
    if type(receipt) is not MatchedPolicySensitivityReceipt:
        raise PolicySensitivityError("an exact closed policy-sensitivity receipt is required")
    checked = MatchedPolicySensitivityReceipt.model_validate(receipt.model_dump(mode="python"))
    payload = canonical_json_bytes(checked.model_dump(mode="json")) + b"\n"
    if len(payload) > MAX_OUTPUT_BYTES:
        raise PolicySensitivityError("the policy-sensitivity receipt exceeds its output bound")
    return payload


def _run_policy_sensitivity(  # noqa: PLR0913 -- one private recovery/scoring scope
    source: Path,
    reviewed_sha256: str,
    preflight_path: Path,
    run_directory: Path,
    plan_path: Path,
    *,
    fold_id: str,
    development_only_acknowledged: bool,
    sha256_independently_reviewed: bool,
) -> MatchedPolicySensitivityReceipt:
    fit_driver._require_acknowledgements(
        development_only_acknowledged=development_only_acknowledged,
        sha256_independently_reviewed=sha256_independently_reviewed,
    )
    plan = _load_plan(plan_path)
    context = recover_selected_fold_context(
        source,
        reviewed_sha256,
        preflight_path,
        run_directory,
        fold_id=fold_id,
        development_only_acknowledged=development_only_acknowledged,
        sha256_independently_reviewed=sha256_independently_reviewed,
    )
    parent = score_replayed_fold(context, plan.policies, omissions=plan.omissions)
    receipt = score_matched_policy_sensitivity(context, plan, parent_benchmark=parent)
    canonical_receipt_bytes(receipt)
    return receipt


def run_policy_sensitivity(  # noqa: PLR0913 -- exact offline producer interface
    source: Path,
    reviewed_sha256: str,
    preflight_path: Path,
    run_directory: Path,
    plan_path: Path,
    *,
    fold_id: str,
    development_only_acknowledged: bool,
    sha256_independently_reviewed: bool,
) -> MatchedPolicySensitivityReceipt:
    """Read an explicit plan and compare points after recovering the fold once."""
    receipt: MatchedPolicySensitivityReceipt | None = None
    failed = False
    try:
        receipt = _run_policy_sensitivity(
            source,
            reviewed_sha256,
            preflight_path,
            run_directory,
            plan_path,
            fold_id=fold_id,
            development_only_acknowledged=development_only_acknowledged,
            sha256_independently_reviewed=sha256_independently_reviewed,
        )
    except InferenceCancelledError:
        raise
    except Exception:  # noqa: BLE001 -- discard private internal exception context
        failed = True
    if failed or receipt is None:
        raise PolicySensitivityError("GBmap policy sensitivity failed closed") from None
    return receipt


class _Parser(argparse.ArgumentParser):
    def error(self, _message: str) -> Never:
        sys.stderr.write("error: policy-sensitivity arguments were not accepted\n")
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="compare-gbmap-policy-sensitivity", description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--reviewed-sha256", required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--fold-id", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--acknowledge-development-only", required=True, action="store_true")
    parser.add_argument(
        "--acknowledge-sha256-independently-reviewed", required=True, action="store_true"
    )
    args = parser.parse_args(argv)
    try:
        receipt = run_policy_sensitivity(
            args.source,
            args.reviewed_sha256,
            args.preflight,
            args.run_directory,
            args.plan,
            fold_id=args.fold_id,
            development_only_acknowledged=args.acknowledge_development_only,
            sha256_independently_reviewed=args.acknowledge_sha256_independently_reviewed,
        )
        sys.stdout.buffer.write(canonical_receipt_bytes(receipt))
    except InferenceCancelledError:
        raise
    except Exception:  # noqa: BLE001 -- sanitized private CLI boundary
        sys.stderr.write("error: GBmap policy sensitivity failed closed\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
