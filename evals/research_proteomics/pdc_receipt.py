"""Evaluator for content-type binding in explicit research PDC receipts."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import md5, sha256

from glio_proteogen.research import PdcFile, PdcSourceReceipt, PdcStudySnapshot, SourceReference


def run_pdc_receipt_evaluator() -> dict[str, object]:
    payload = b"<mzML>catalog-bound-research-fixture</mzML>"
    file = PdcFile(
        study_id="PDC000204",
        file_name="fixture.mzML",
        file_type="Processed",
        data_category="Proteome",
        file_format="mzML",
        file_size=len(payload),
        md5=md5(payload, usedforsecurity=False).hexdigest(),
        location="memory://PDC000204/fixture.mzML",
    )
    snapshot = PdcStudySnapshot(
        study_id="PDC000204",
        counts=(("Proteome", "Processed", 1),),
        files=(file,),
        source_url="https://pdc.cancer.gov/pdc/study/PDC000204",
        response_sha256="a" * 64,
    )
    reference = SourceReference(
        source_id="pdc:PDC000204:fixture",
        locator=file.location,
        media_type="application/mzml",
        sha256="sha256:" + sha256(payload).hexdigest(),
        byte_length=len(payload),
        retrieved_at="2026-08-18T00:00:00Z",
        license_or_terms="public metadata-bound research fixture",
    )
    receipt = PdcSourceReceipt(
        snapshot=snapshot,
        file=file,
        source_reference=reference,
        observed_sha256=reference.sha256,
        observed_md5=file.md5 or "",
        observed_size=len(payload),
        observed_media_type="application/mzml",
    )
    serialized = receipt.as_dict()
    media_bound = (
        serialized["observed_media_type"] == "application/mzml"
        and receipt.digest
        == sha256(
            json.dumps(serialized, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    tamper_rejected = False
    try:
        replace(receipt, observed_media_type="text/plain")
    except ValueError:
        tamper_rejected = True
    outcomes = (
        {"scenario_id": "observed_media_bound", "passed": media_bound},
        {"scenario_id": "media_tamper_rejected", "passed": tamper_rejected},
    )
    return {
        "passed": all(bool(item["passed"]) for item in outcomes),
        "declared": len(outcomes),
        "executed": len(outcomes),
        "outcomes": outcomes,
    }


if __name__ == "__main__":
    import sys

    sys.stdout.write(json.dumps(run_pdc_receipt_evaluator(), sort_keys=True))
