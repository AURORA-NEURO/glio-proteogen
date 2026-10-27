"""Run an explicit private sensitivity plan on one reproduced GBmap fold.

The plan is validated before source recovery. Every scientific policy value
comes from that plan; this command neither selects a policy nor calibrates a
threshold. Stdout contains a bounded aggregate receipt, never individual
predictions, reference parameters, a saved model or a production admission.
"""

# ruff: noqa: TRY003 -- stable sanitized errors at the private boundary

from __future__ import annotations

import argparse
import json
import stat
import sys
from pathlib import Path
from typing import Never

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.research.gbmap_mixture_benchmark import (
    MixtureBenchmarkError,
    MixtureBenchmarkPlan,
    MixtureBenchmarkReceipt,
    score_replayed_fold,
)
from glio_proteogen.research.proteogenomic_state.cancellation import InferenceCancelledError
from tools import fit_gbmap_development_candidate as fit_driver
from tools import run_gbmap_hierarchy_tasks as tasks
from tools.replay_gbmap_selected_fold import recover_selected_fold_context

MAX_PLAN_BYTES = 128 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise MixtureBenchmarkError("duplicate plan fields are forbidden")
        result[key] = value
    return result


def _reject_constant(_value: str) -> Never:
    raise MixtureBenchmarkError("nonfinite plan constants are forbidden")


def _read_plan_bytes(path: Path) -> bytes:
    if not isinstance(path, Path):
        raise MixtureBenchmarkError("the sensitivity plan requires a regular file path")
    lexical = fit_driver._lexical_absolute(path)
    ancestors = []
    for ancestor in reversed(lexical.parents):
        info = ancestor.lstat()
        if fit_driver._is_link_or_reparse(info) or not stat.S_ISDIR(info.st_mode):
            raise MixtureBenchmarkError("plan ancestors must be ordinary directories")
        ancestors.append((ancestor, fit_driver._ancestor_identity(info)))
    before = fit_driver._file_identity(lexical.lstat())
    payload = tasks._read_regular_bytes(
        lexical, MAX_PLAN_BYTES, "the sensitivity plan could not be read safely"
    )
    after = lexical.lstat()
    if fit_driver._is_link_or_reparse(after) or fit_driver._file_identity(after) != before:
        raise MixtureBenchmarkError("the sensitivity plan changed while it was read")
    for ancestor, expected in ancestors:
        if fit_driver._ancestor_identity(ancestor.lstat()) != expected:
            raise MixtureBenchmarkError("plan ancestors changed while the plan was read")
    return payload


def _load_plan(path: Path) -> MixtureBenchmarkPlan:
    payload = _read_plan_bytes(path)
    # Check object-key uniqueness without losing strict JSON tuple semantics in
    # the closed model. Input whitespace and outer declaration order may vary.
    json.loads(payload, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    return MixtureBenchmarkPlan.model_validate_json(payload)


def canonical_receipt_bytes(receipt: MixtureBenchmarkReceipt) -> bytes:
    if type(receipt) is not MixtureBenchmarkReceipt:
        raise MixtureBenchmarkError("an exact closed benchmark receipt is required")
    checked = MixtureBenchmarkReceipt.model_validate(receipt.model_dump(mode="python"))
    payload = canonical_json_bytes(checked.model_dump(mode="json")) + b"\n"
    if len(payload) > MAX_OUTPUT_BYTES:
        raise MixtureBenchmarkError("the benchmark receipt exceeds its output bound")
    return payload


def _run_selected_fold_benchmark(  # noqa: PLR0913 -- one private recovery/scoring scope
    source: Path,
    reviewed_sha256: str,
    preflight_path: Path,
    run_directory: Path,
    plan_path: Path,
    *,
    fold_id: str,
    development_only_acknowledged: bool,
    sha256_independently_reviewed: bool,
) -> MixtureBenchmarkReceipt:
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
    receipt = score_replayed_fold(context, plan.policies, omissions=plan.omissions)
    canonical_receipt_bytes(receipt)
    return receipt


def run_selected_fold_benchmark(  # noqa: PLR0913 -- exact offline producer interface
    source: Path,
    reviewed_sha256: str,
    preflight_path: Path,
    run_directory: Path,
    plan_path: Path,
    *,
    fold_id: str,
    development_only_acknowledged: bool,
    sha256_independently_reviewed: bool,
) -> MixtureBenchmarkReceipt:
    """Validate an explicit plan, recover once, and return aggregate point errors."""
    receipt: MixtureBenchmarkReceipt | None = None
    failed = False
    try:
        receipt = _run_selected_fold_benchmark(
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
        raise MixtureBenchmarkError("GBmap selected-fold benchmark failed closed") from None
    return receipt


class _Parser(argparse.ArgumentParser):
    def error(self, _message: str) -> Never:
        sys.stderr.write("error: selected-fold benchmark arguments were not accepted\n")
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="benchmark-gbmap-selected-fold", description=__doc__)
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
        receipt = run_selected_fold_benchmark(
            args.source,
            args.reviewed_sha256,
            args.preflight,
            args.run_directory,
            args.plan,
            fold_id=args.fold_id,
            development_only_acknowledged=args.acknowledge_development_only,
            sha256_independently_reviewed=args.acknowledge_sha256_independently_reviewed,
        )
        sys.stdout.write(canonical_receipt_bytes(receipt).decode())
    except InferenceCancelledError:
        raise
    except Exception:  # noqa: BLE001 -- sanitized private CLI boundary
        sys.stderr.write("error: GBmap selected-fold benchmark failed closed\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
