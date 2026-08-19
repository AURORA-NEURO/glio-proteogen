"""Adversarial structural closure for M03-03 raw XML admission."""

from __future__ import annotations

from evals.m03_03.run import ScenarioOptions, build_scenario

from glio_proteogen.contracts.m03_03 import (
    ProteinInferenceDiagnosticCode,
    ProteinInferenceRawAdmissionResult,
    ProteinInferenceRawRole,
)
from glio_proteogen.modules.c03_protein_inference.m03_03_raw_ingestion import (
    ingest_protein_inference_raw_inputs,
)


def _spectra_result(payload: bytes) -> ProteinInferenceRawAdmissionResult:
    scenario = build_scenario(
        options=ScenarioOptions(
            raw_overrides={ProteinInferenceRawRole.SPECTRA: payload},
        ),
    )
    return ingest_protein_inference_raw_inputs(scenario.request, scenario.sources)


def _spectra_diagnostics(payload: bytes) -> set[ProteinInferenceDiagnosticCode]:
    result = _spectra_result(payload)
    return {
        item.code
        for item in result.diagnostics
        if item.source_ids == ("source.spectra.mzml",)
    }


def test_mzml_duplicate_ids_are_quarantined_before_admission() -> None:
    scenario = build_scenario()
    duplicate = scenario.sources["source.spectra.mzml"].replace(
        b'<spectrum id="scan=1"',
        b'<spectrum id="run-synthetic"',
    )

    assert ProteinInferenceDiagnosticCode.MALFORMED_CONTENT in _spectra_diagnostics(duplicate)


def test_mzml_dangling_reference_is_quarantined_before_admission() -> None:
    scenario = build_scenario()
    dangling = scenario.sources["source.spectra.mzml"].replace(
        b'<spectrum id="scan=1" index="0" defaultArrayLength="0"/>',
        b'<spectrum id="scan=1" index="0" defaultArrayLength="0">'
        b'<referenceableParamGroupRef ref="missing-group"/></spectrum>',
    )

    assert ProteinInferenceDiagnosticCode.DANGLING_REFERENCE in _spectra_diagnostics(dangling)
