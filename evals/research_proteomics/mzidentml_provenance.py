"""Locked evaluator for structural mzIdentML provenance binding."""

from __future__ import annotations

from dataclasses import replace

from glio_proteogen.research import (
    ResearchRunRequest,
    replay_research_protein_inference,
    run_research_protein_inference,
)

from .run import build_scenario_request, scenarios

_MZIDENTML = b"""\
<MzIdentML id="evaluation">
  <SequenceCollection>
    <PeptideEvidence id="PE1" peptide_ref="PEP1" dBSequence_ref="P1"/>
  </SequenceCollection>
  <AnalysisData>
    <SpectrumIdentificationList id="SIL1">
      <SpectrumIdentificationResult id="SIR1">
        <SpectrumIdentificationItem id="SII1" passThreshold="true"/>
      </SpectrumIdentificationResult>
    </SpectrumIdentificationList>
    <ProteinDetectionList id="PDL1">
      <ProteinAmbiguityGroup id="PAG1">
        <ProteinDetectionHypothesis id="PDH1"/>
      </ProteinAmbiguityGroup>
    </ProteinDetectionList>
  </AnalysisData>
</MzIdentML>
"""


def _request(mzidentml: bytes = _MZIDENTML) -> ResearchRunRequest:
    return replace(
        build_scenario_request(scenarios()[0]),
        mzidentml_source=mzidentml,
    )


def run_mzidentml_provenance_evaluator() -> dict[str, object]:
    """Check structural counts, non-import semantics, digest binding, and replay."""

    baseline = run_research_protein_inference(build_scenario_request(scenarios()[0]))
    bound = run_research_protein_inference(_request())
    structure = bound.mzidentml_structure
    checks = {
        "structure_present": structure is not None,
        "result_count": structure is not None
        and structure.spectrum_identification_result_count == 1,
        "item_count": structure is not None and structure.spectrum_identification_item_count == 1,
        "peptide_evidence_count": structure is not None and structure.peptide_evidence_count == 1,
        "protein_hypothesis_count": structure is not None
        and structure.protein_detection_hypothesis_count == 1,
        "pass_threshold_count": structure is not None and structure.pass_threshold_item_count == 1,
        "identifications_not_imported": bound.psms == baseline.psms,
        "replay_passes": (
            replay_research_protein_inference(_request(), bound).result_digest
            == bound.result_digest
        ),
    }
    changed = _MZIDENTML.replace(b'passThreshold="true"', b'passThreshold="false"')
    changed_replay_rejected = False
    try:
        replay_research_protein_inference(_request(changed), bound)
    except ValueError:
        changed_replay_rejected = True
    checks["changed_receipt_rejected"] = changed_replay_rejected
    checks["digest_changes_with_receipt"] = baseline.result_digest != bound.result_digest
    return {
        "evaluator": "mzidentml-structural-provenance-v1",
        "passed": all(checks.values()),
        "declared": len(checks),
        "executed": len(checks),
        "checks": checks,
        "baseline_result_digest": baseline.result_digest,
        "bound_result_digest": bound.result_digest,
        "mzidentml_sha256": structure.sha256 if structure is not None else None,
    }
