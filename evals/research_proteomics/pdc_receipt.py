"""Evaluator for content-type binding in explicit research PDC receipts."""

from __future__ import annotations

import io
import json
from dataclasses import replace
from hashlib import md5, sha256

from glio_proteogen.research import (
    PdcFile,
    PdcSourceReceipt,
    PdcStudySnapshot,
    SourceReference,
    verify_pdc_source_content,
)
from glio_proteogen.research.public_proteomics import PDCError, PDCMetadataClient


def _metadata_record(pdc_study_id: str) -> dict[str, object]:
    return {
        "study_id": "cfe9f4a2-1797-11ea-9bfa-0a42f3c845fe",
        "pdc_study_id": pdc_study_id,
        "study_submitter_id": "fixture study",
        "project_id": "267d6671-0e78-11e9-a064-0a9c39d33490",
        "study_name": "fixture study",
        "study_description": "public fixture metadata",
        "program_name": "fixture program",
        "project_name": "fixture project",
        "disease_type": "caller-declared metadata",
        "primary_site": "caller-declared metadata",
        "analytical_fraction": "Proteome",
        "experiment_type": "TMT11",
        "cases_count": 2,
        "aliquots_count": 2,
    }


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
    content_verified = (
        verify_pdc_source_content(receipt, payload) is receipt
        and verify_pdc_source_content(receipt, io.BytesIO(payload)) is receipt
    )
    content_tamper_rejected = False
    try:
        verify_pdc_source_content(receipt, payload + b"tampered")
    except RuntimeError:
        content_tamper_rejected = True
    valid_metadata = PDCMetadataClient._parse_response(
        {"data": {"study": [_metadata_record("PDC000204")]}}, "PDC000204"
    )
    metadata_tamper_rejected = False
    try:
        PDCMetadataClient._parse_response(
            {"data": {"study": [_metadata_record("PDC000205")]}}, "PDC000204"
        )
    except PDCError:
        metadata_tamper_rejected = True
    outcomes = (
        {"scenario_id": "observed_media_bound", "passed": media_bound},
        {"scenario_id": "media_tamper_rejected", "passed": tamper_rejected},
        {"scenario_id": "source_content_verified", "passed": content_verified},
        {"scenario_id": "source_content_tamper_rejected", "passed": content_tamper_rejected},
        {
            "scenario_id": "metadata_catalog_id_bound",
            "passed": valid_metadata.pdc_study_id == "PDC000204" and metadata_tamper_rejected,
        },
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
