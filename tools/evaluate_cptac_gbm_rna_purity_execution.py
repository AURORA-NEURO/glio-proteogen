"""Local source-qualified native RNA execution of the existing GBMPurity model."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Never

from glio_proteogen.research.cptac_gbm_rna_purity_execution.execution import (
    evaluate_execution,
    frozen_protocol,
    profile,
    verify_execution,
)
from glio_proteogen.research.cptac_gbm_rna_purity_execution.inputs import load_inputs


class _Parser(argparse.ArgumentParser):
    def error(self, _message: str) -> Never:
        sys.stdout.write(
            json.dumps(
                {
                    "complete": False,
                    "error_category": "UsageError",
                    "message": "RNA input qualification arguments were not accepted.",
                    "model_execution_status": "not_reported",
                },
                sort_keys=True,
            )
            + "\n"
        )
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("profile", help="Describe the exact method without input reads.")
    prepare = commands.add_parser("prepare", help="Freeze metadata/context before RNA reads.")
    execute = commands.add_parser(
        "execute", help="Project nonheld RNA and estimate only fully qualified cases."
    )
    for command in (prepare, execute):
        command.add_argument("--inputs", type=Path, required=True)
        command.add_argument(
            "--inputs-sha256", required=True, help="Exact raw SHA-256 of private input config."
        )
    execute.add_argument("--expected-protocol-digest", required=True)
    execute.add_argument("--output-dir", type=Path, required=True)
    verify = commands.add_parser("verify", help="Check saved aggregate integrity and conservation.")
    verify.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "profile":
            result = profile()
        elif args.command == "verify":
            result = verify_execution(args.directory)
        else:
            inputs = load_inputs(args.inputs, sha256=args.inputs_sha256)
            if args.command == "prepare":
                result = frozen_protocol(inputs)
            else:
                result = evaluate_execution(
                    inputs,
                    output_dir=args.output_dir,
                    expected_protocol_digest=args.expected_protocol_digest,
                )
    except Exception as error:  # noqa: BLE001 -- sanitize paths, row values and case identifiers
        sys.stdout.write(
            json.dumps(
                {
                    "complete": False,
                    "error_category": type(error).__name__,
                    "message": (
                        "RNA input qualification stopped; retain incomplete evidence for review."
                    ),
                    "model_execution_status": "not_reported",
                },
                sort_keys=True,
            )
            + "\n"
        )
        return 1
    sys.stdout.write(json.dumps(result, sort_keys=True, allow_nan=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
