"""Review source-attributed clinical context before existing purity eligibility gates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Never

from glio_proteogen.research.cptac_gbm_rna_purity_resolution.review import (
    evaluate_review,
    load_inputs,
    prepare_review,
    profile,
    verify_review,
)


class _Parser(argparse.ArgumentParser):
    def error(self, _message: str) -> Never:
        sys.stdout.write(
            json.dumps(
                {
                    "complete": False,
                    "error_category": "UsageError",
                    "message": "Clinical review arguments were not accepted.",
                }
            )
            + "\n"
        )
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("profile")
    for name in ("prepare", "review"):
        command = commands.add_parser(name)
        command.add_argument("--inputs", type=Path, required=True)
        command.add_argument("--inputs-sha256", required=True)
        if name == "review":
            command.add_argument("--expected-protocol-digest", required=True)
            command.add_argument("--output-dir", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "profile":
            result = profile()
        elif args.command == "verify":
            result = verify_review(args.directory)
        else:
            inputs = load_inputs(args.inputs, sha256=args.inputs_sha256)
            if args.command == "prepare":
                result = prepare_review(inputs)
            else:
                result = evaluate_review(
                    inputs,
                    output_dir=args.output_dir,
                    expected_protocol_digest=args.expected_protocol_digest,
                )
    except Exception as error:  # noqa: BLE001 -- never echo clinical values, paths or identifiers
        result = {
            "complete": False,
            "error_category": type(error).__name__,
            "message": "Clinical source review stopped; retain incomplete evidence.",
            "model_execution_status": "not_reported",
        }
        sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
        return 1
    sys.stdout.write(json.dumps(result, sort_keys=True, allow_nan=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
