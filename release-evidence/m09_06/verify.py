"""Verify immutable M09-06 release evidence and dossier traceability."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOSSIER = Path(r"C:\Users\murar\AppData\Local\Temp\GLIO-PROTEOGEN_240_Module_Dossier.md")
EXPECTED_SHA = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"


def main() -> int:
    trace = json.loads((ROOT / "release-evidence/m09_06/traceability.json").read_text())
    if trace["dossierSha256"].lower() != EXPECTED_SHA:
        return 1
    if DOSSIER.exists() and hashlib.sha256(DOSSIER.read_bytes()).hexdigest() != EXPECTED_SHA:
        return 1
    for relative in (
        *trace["contractFiles"],
        *trace["runtimeFiles"],
        *trace["interfaceFiles"],
        *trace["evaluatorFiles"],
    ):
        if not (ROOT / relative).exists():
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
