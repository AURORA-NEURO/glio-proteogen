"""Replay-bound structural provenance for optional mzIdentML evidence."""

from __future__ import annotations

from dataclasses import replace

import pytest

from glio_proteogen.research import (
    ResearchRunRequest,
    replay_research_protein_inference,
    run_research_protein_inference,
)

from .test_pipeline import _mzml

_MZIDENTML = b"""\
<MzIdentML id="fixture">
  <SequenceCollection>
    <Peptide id="PEP1"/>
    <DBSequence id="P1" accession="P1"/>
    <PeptideEvidence id="PE1" peptide_ref="PEP1" dBSequence_ref="P1"/>
    <PeptideEvidence id="PE2" peptide_ref="PEP1" dBSequence_ref="P1"/>
  </SequenceCollection>
  <AnalysisData>
    <SpectrumIdentificationList id="SIL1">
      <SpectrumIdentificationResult id="SIR1" spectrumID="scan=1">
        <SpectrumIdentificationItem id="SII1" peptide_ref="PEP1" passThreshold="true"/>
        <SpectrumIdentificationItem id="SII2" peptide_ref="PEP1" passThreshold="false"/>
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


def _request(mzidentml: bytes | None = _MZIDENTML) -> ResearchRunRequest:
    return ResearchRunRequest(
        sample_id="mzidentml-provenance",
        mzml_source=_mzml(),
        fasta_source=b">P1\nMPEPTIDER\n",
        min_matched_ions=1,
        min_peptide_length=7,
        max_peptide_length=12,
        mzidentml_source=mzidentml,
    )


def test_mzidentml_structure_is_replay_bound_without_inference_import() -> None:
    with_ident = run_research_protein_inference(_request())
    without_ident = run_research_protein_inference(_request(None))

    assert with_ident.mzidentml_structure is not None
    structure = with_ident.mzidentml_structure
    assert structure.spectrum_identification_result_count == 1
    assert structure.spectrum_identification_item_count == 2
    assert structure.peptide_evidence_count == 2
    assert structure.protein_detection_hypothesis_count == 1
    assert structure.pass_threshold_item_count == 1
    assert structure.spectrum_reference_count == 1
    assert structure.spectrum_reference_match_count == 1
    assert structure.protein_reference_count == 2
    assert structure.protein_reference_match_count == 2
    assert structure.peptide_reference_count == 4
    assert structure.peptide_reference_match_count == 4
    assert dict(with_ident.configuration)["mzidentml_sha256"] == structure.sha256
    assert any(
        record.kind == "identification_evidence_structure" for record in with_ident.evidence.records
    )
    assert with_ident.psms == without_ident.psms
    assert with_ident.result_digest != without_ident.result_digest
    assert replay_research_protein_inference(_request(), with_ident).result_digest == (
        with_ident.result_digest
    )


def test_mzidentml_mutation_rejects_replay() -> None:
    result = run_research_protein_inference(_request())
    changed = _MZIDENTML.replace(b'passThreshold="true"', b'passThreshold="false"')
    with pytest.raises(ValueError, match="replay"):
        replay_research_protein_inference(replace(_request(), mzidentml_source=changed), result)


def test_mzidentml_unrelated_spectrum_reference_abstains_before_search() -> None:
    changed = _MZIDENTML.replace(b'spectrumID="scan=1"', b'spectrumID="scan=missing"')
    with pytest.raises(ValueError, match="spectrumID"):
        run_research_protein_inference(_request(changed))


def test_mzidentml_unresolved_peptide_reference_abstains_before_search() -> None:
    changed = _MZIDENTML.replace(b'peptide_ref="PEP1"', b'peptide_ref="missing"', 1)
    with pytest.raises(ValueError, match="peptide_ref"):
        run_research_protein_inference(_request(changed))
