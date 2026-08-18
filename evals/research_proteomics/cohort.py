"""Locked evaluator for multi-sample research cohort evidence."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from hashlib import md5, sha256
from pathlib import Path
from typing import TYPE_CHECKING, cast

import glio_proteogen.research.cohort as cohort_module
from glio_proteogen.research import (
    PdcFile,
    PdcStudySnapshot,
    ProteinGroup,
    ProteinGroupQuant,
    ResearchCohortRequest,
    ResearchCohortResult,
    ResearchCohortSample,
    ResearchRunRequest,
    ResearchRunResult,
    SourceReference,
    bind_pdc_mzml_source,
    replay_research_cohort,
    run_research_cohort,
)
from glio_proteogen.research.pipeline import run_research_protein_inference

from .run import Scenario, build_scenario_request, scenarios

if TYPE_CHECKING:
    from collections.abc import Callable

_EXPECTED_INTENSITY = 20.0
_EXPECTED_SAMPLE_COUNT = 2


def _projection(result: ResearchCohortResult) -> dict[str, object]:
    """Return the complete stable cohort output used by release evidence."""

    return result.as_dict()


def _fixture_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "tests"
        / "fixtures"
        / "research"
        / "cohort_scenarios.json"
    )


def _locked_ids() -> tuple[str, ...]:
    fixture = json.loads(_fixture_path().read_text(encoding="utf-8"))
    if fixture.get("fixture_version") != "research-cohort-2":
        raise ValueError
    if any(bool(value) for value in fixture.get("claims", {}).values()):
        raise ValueError
    return tuple(item["id"] for item in fixture["scenarios"])


def _sample(scenario_id: str, sample_id: str, replicate: str) -> ResearchCohortSample:
    scenario = next(item for item in scenarios() if item.scenario_id == scenario_id)
    return ResearchCohortSample(
        sample_id=sample_id,
        request=replace(build_scenario_request(scenario), sample_id=sample_id),
        cohort_label="locked-cohort",
        replicate_label=replicate,
    )


def _label_normalization_case(target: Scenario) -> ResearchCohortResult:
    """Exercise cross-run normalization with deliberately scaled synthetic outputs."""

    values = {
        "case-a": (10.0, 30.0),
        "case-b": (20.0, 60.0),
        "control-a": (100.0, 300.0),
        "control-b": (200.0, 600.0),
    }
    base = run_research_protein_inference(
        replace(build_scenario_request(target), sample_id="normalization-template")
    )
    synthetic = {
        sample_id: replace(
            base,
            sample_id=sample_id,
            protein_groups=(
                ProteinGroup(("P1",), ("PEPTIDE",), ()),
                ProteinGroup(("P2",), ("PEPTIDE2",), ()),
            ),
            protein_group_quantifications=(
                ProteinGroupQuant(
                    ("P1",), ("PEPTIDE",), (), pair[0], 0.0, pair[0], pair[0], "quantified", 1
                ),
                ProteinGroupQuant(
                    ("P2",), ("PEPTIDE2",), (), pair[1], 0.0, pair[1], pair[1], "quantified", 1
                ),
            ),
        )
        for sample_id, pair in values.items()
    }
    original = cast(
        "Callable[[ResearchRunRequest], ResearchRunResult]",
        cohort_module.__dict__["run_research_protein_inference"],
    )
    cohort_module.__dict__["run_research_protein_inference"] = lambda request: synthetic[
        request.sample_id
    ]
    try:
        samples = tuple(
            ResearchCohortSample(
                sample_id=sample_id,
                request=replace(build_scenario_request(target), sample_id=sample_id),
                cohort_label="case" if sample_id.startswith("case") else "control",
                replicate_label=replicate,
            )
            for sample_id, replicate in (
                ("control-b", "r2"),
                ("case-b", "r2"),
                ("control-a", "r1"),
                ("case-a", "r1"),
            )
        )
        return run_research_cohort(
            ResearchCohortRequest(
                samples,
                normalization_policy="within_label_median_v1",
            )
        )
    finally:
        cohort_module.__dict__["run_research_protein_inference"] = original


def _pdc_sample(scenario: Scenario, sample_id: str, replicate: str) -> ResearchCohortSample:
    request: ResearchRunRequest = replace(build_scenario_request(scenario), sample_id=sample_id)
    mzml = request.mzml_source
    if not isinstance(mzml, bytes):
        raise TypeError
    file_name = f"{sample_id}.mzML"
    location = f"https://pdc.cancer.gov/files/{file_name}"
    pdc_file = PdcFile(
        study_id="PDC000204",
        file_name=file_name,
        file_type="processed_mzML",
        data_category="Proteome",
        file_format="mzML",
        file_size=len(mzml),
        md5=md5(mzml, usedforsecurity=False).hexdigest(),
        location=location,
    )
    source_reference = SourceReference(
        source_id=f"pdc:{sample_id}",
        locator=location,
        media_type="application/mzml",
        sha256="sha256:" + sha256(mzml).hexdigest(),
        byte_length=len(mzml),
        retrieved_at="2026-08-18T00:00:00Z",
        license_or_terms="public metadata-bound research fixture",
    )
    metadata_fixture = (
        Path(__file__).resolve().parents[2]
        / "tests"
        / "fixtures"
        / "research"
        / "pdc000204_snapshot.json"
    )
    snapshot = PdcStudySnapshot(
        study_id="PDC000204",
        counts=(("Proteome", "processed_mzML", 2),),
        files=(pdc_file,),
        source_url="https://pdc.cancer.gov/pdc/study/PDC000204",
        response_sha256=sha256(metadata_fixture.read_bytes()).hexdigest(),
    )
    bound = bind_pdc_mzml_source(
        request,
        pdc_file,
        source_reference,
        pdc_snapshot=snapshot,
    )
    return ResearchCohortSample(
        sample_id=sample_id,
        request=bound,
        cohort_label="pdc-bound-cohort",
        replicate_label=replicate,
    )


def run_evaluator() -> dict[str, object]:
    """Run locked cohort cases and return machine-readable evidence."""

    expected_ids = (
        "replicate_matrix",
        "explicit_missingness",
        "label_normalization",
        "incompatible_search_space",
        "pdc_provenance_replay",
    )
    if _locked_ids() != expected_ids:
        raise ValueError
    target = next(item for item in scenarios() if item.scenario_id == "target_supported")
    outcomes: list[dict[str, object]] = []

    replicate = run_research_cohort(
        ResearchCohortRequest(
            (_sample("target_supported", "rep-a", "r1"), _sample("target_supported", "rep-b", "r2"))
        )
    )
    outcomes.append(
        {
            "id": "replicate_matrix",
            "passed": replicate.sample_ids == ("rep-a", "rep-b")
            and replicate.matrix == ((("P1",), (_EXPECTED_INTENSITY, _EXPECTED_INTENSITY)),)
            and replicate.group_qc[0].missingness_rate == 0.0,
            "result_digest": replicate.result_digest,
            "missing_cells": sum(
                value is None for _, values in replicate.matrix for value in values
            ),
            "projection": _projection(replicate),
        }
    )
    missing = run_research_cohort(
        ResearchCohortRequest(
            (_sample("target_supported", "present", "r1"), _sample("no_match", "absent", "r2"))
        )
    )
    outcomes.append(
        {
            "id": "explicit_missingness",
            "passed": missing.matrix == ((("P1",), (None, _EXPECTED_INTENSITY)),)
            and missing.group_qc[0].missing_samples == 1
            and missing.group_qc[0].median_intensity == _EXPECTED_INTENSITY,
            "result_digest": missing.result_digest,
            "missing_cells": sum(value is None for _, values in missing.matrix for value in values),
            "projection": _projection(missing),
        }
    )
    normalized = _label_normalization_case(target)
    outcomes.append(
        {
            "id": "label_normalization",
            "passed": normalized.raw_matrix[0][1] == (10.0, 20.0, 100.0, 200.0)
            and normalized.normalized_matrix[0][1] == (15.0, 15.0, 150.0, 150.0)
            and normalized.normalized_matrix[1][1] == (45.0, 45.0, 450.0, 450.0)
            and {item.cohort_label for item in normalized.label_qc} == {"case", "control"}
            and all(item.status == "descriptive" for item in normalized.label_group_evidence),
            "result_digest": normalized.result_digest,
            "missing_cells": 0,
            "projection": _projection(normalized),
        }
    )

    incompatible_error = False
    try:
        run_research_cohort(
            ResearchCohortRequest(
                (
                    _sample("target_supported", "target", "r1"),
                    _sample("decoy_rejected", "decoy", "r2"),
                )
            )
        )
    except ValueError as error:
        incompatible_error = "FASTA and search" in str(error)
    outcomes.append(
        {
            "id": "incompatible_search_space",
            "passed": incompatible_error,
            "result_digest": None,
            "missing_cells": None,
            "projection": None,
        }
    )

    pdc_result = run_research_cohort(
        ResearchCohortRequest(
            (_pdc_sample(target, "pdc-a", "r1"), _pdc_sample(target, "pdc-b", "r2")),
            provenance_policy="external_same_study",
        )
    )
    replay = replay_research_cohort(
        ResearchCohortRequest(
            (_pdc_sample(target, "pdc-a", "r1"), _pdc_sample(target, "pdc-b", "r2")),
            provenance_policy="external_same_study",
        ),
        pdc_result,
    )
    provenance = dict(pdc_result.configuration)["sample_source_provenance"]
    outcomes.append(
        {
            "id": "pdc_provenance_replay",
            "passed": replay.result_digest == pdc_result.result_digest
            and isinstance(provenance, list)
            and len(provenance) == _EXPECTED_SAMPLE_COUNT
            and all(isinstance(item, dict) and item["external_pdc_file"] for item in provenance),
            "result_digest": pdc_result.result_digest,
            "missing_cells": 0,
            "projection": _projection(pdc_result),
        }
    )
    return {
        "passed": all(bool(item["passed"]) for item in outcomes),
        "declared": len(outcomes),
        "executed": len(outcomes),
        "fixture_sha256": sha256(_fixture_path().read_bytes()).hexdigest(),
        "outcomes": outcomes,
    }


if __name__ == "__main__":
    sys.stdout.write(json.dumps(run_evaluator(), sort_keys=True) + "\n")
