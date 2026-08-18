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
    CohortQcPolicy,
    CohortSourceManifest,
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
    aggregate_cohort_evidence,
    bind_pdc_mzml_source,
    replay_research_cohort,
    run_research_cohort,
)
from glio_proteogen.research.pipeline import run_research_protein_inference

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from evals.research_proteomics.run import (
        Scenario,
        build_scenario_request,
        scenarios,
    )
else:
    from .run import Scenario, build_scenario_request, scenarios

if TYPE_CHECKING:
    from collections.abc import Callable

_EXPECTED_INTENSITY = 20.0
_EXPECTED_SAMPLE_COUNT = 2
_EXPECTED_CONTRAST_COUNT = 2
_EXPECTED_MEDIAN_RATIO = 0.1


def _projection(result: ResearchCohortResult) -> dict[str, object]:
    """Return the complete stable cohort output used by release evidence."""

    projection = result.as_dict()
    receipt = aggregate_cohort_evidence(result)
    bundle = projection.get("evidence_bundle")
    if not isinstance(bundle, dict) or bundle.get("digest") != receipt.digest:
        raise ValueError("cohort evidence receipt did not verify")  # noqa: TRY003
    return projection


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
    if fixture.get("fixture_version") != "research-cohort-3":
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
    base_request = replace(build_scenario_request(target), sample_id="normalization-template")
    base = run_research_protein_inference(base_request)
    sample_requests = {
        sample_id: replace(
            build_scenario_request(target),
            sample_id=sample_id,
            mzml_source=b"<!--"
            + sample_id.encode()
            + b"-->"
            + cast("bytes", base_request.mzml_source),
        )
        for sample_id in values
    }
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
            mzml_sha256=sha256(cast("bytes", sample_requests[sample_id].mzml_source)).hexdigest(),
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
                request=sample_requests[sample_id],
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
                source_manifest=CohortSourceManifest.from_requests(
                    tuple(sample.request for sample in samples),
                    replicate_kinds={sample.sample_id: "biological" for sample in samples},
                ),
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
        "qc_abstention",
        "explicit_missingness",
        "label_normalization",
        "duplicate_biological_source",
        "technical_duplicate_visibility",
        "unknown_independence_abstention",
        "incompatible_search_space",
        "pdc_provenance_replay",
        "pdc_manifest_receipt_identity",
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
    qc_result = run_research_cohort(
        ResearchCohortRequest(
            (
                _sample("target_supported", "qc-present", "r1"),
                _sample("no_match", "qc-absent", "r2"),
            ),
            qc_policy=CohortQcPolicy(max_missingness_rate=0.0),
        )
    )
    outcomes.append(
        {
            "id": "qc_abstention",
            "passed": qc_result.raw_matrix == ((("P1",), (None, 20.0)),)
            and qc_result.normalized_matrix == ((("P1",), (None, None)),)
            and qc_result.label_qc[0].status == "abstained_missingness"
            and qc_result.label_group_evidence[0].status == "abstained_missingness",
            "result_digest": qc_result.result_digest,
            "missing_cells": 1,
            "projection": _projection(qc_result),
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
            and all(item.status == "descriptive" for item in normalized.label_group_evidence)
            and len(normalized.label_contrasts) == _EXPECTED_CONTRAST_COUNT
            and all(item.status == "descriptive" for item in normalized.label_contrasts)
            and all(
                item.median_ratio == _EXPECTED_MEDIAN_RATIO for item in normalized.label_contrasts
            ),
            "result_digest": normalized.result_digest,
            "missing_cells": 0,
            "projection": _projection(normalized),
        }
    )

    duplicate_samples = (
        _sample("target_supported", "duplicate-a", "r1"),
        _sample("target_supported", "duplicate-b", "r2"),
    )
    duplicate_error = False
    try:
        run_research_cohort(
            ResearchCohortRequest(
                duplicate_samples,
                source_manifest=CohortSourceManifest.from_requests(
                    tuple(sample.request for sample in duplicate_samples),
                    replicate_kinds={
                        sample.sample_id: "biological" for sample in duplicate_samples
                    },
                ),
            )
        )
    except ValueError as error:
        duplicate_error = "biological replicates" in str(error)
    outcomes.append(
        {
            "id": "duplicate_biological_source",
            "passed": duplicate_error,
            "result_digest": None,
            "missing_cells": None,
            "projection": None,
        }
    )

    technical = run_research_cohort(
        ResearchCohortRequest(
            duplicate_samples,
            normalization_policy="within_label_median_v1",
            source_manifest=CohortSourceManifest.from_requests(
                tuple(sample.request for sample in duplicate_samples),
                replicate_kinds={sample.sample_id: "technical" for sample in duplicate_samples},
            ),
        )
    )
    outcomes.append(
        {
            "id": "technical_duplicate_visibility",
            "passed": technical.label_qc[0].technical_replicates == _EXPECTED_SAMPLE_COUNT
            and technical.label_qc[0].independent_replicates == 0
            and technical.label_qc[0].status == "abstained_insufficient_replicates"
            and all(value is None for _, values in technical.normalized_matrix for value in values),
            "result_digest": technical.result_digest,
            "missing_cells": 0,
            "projection": _projection(technical),
        }
    )

    unknown = run_research_cohort(
        ResearchCohortRequest(
            duplicate_samples,
            normalization_policy="within_label_median_v1",
        )
    )
    outcomes.append(
        {
            "id": "unknown_independence_abstention",
            "passed": unknown.label_qc[0].status == "abstained_unknown_independence"
            and all(value is None for _, values in unknown.normalized_matrix for value in values),
            "result_digest": unknown.result_digest,
            "missing_cells": 0,
            "projection": _projection(unknown),
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

    pdc_samples = (_pdc_sample(target, "pdc-a", "r1"), _pdc_sample(target, "pdc-b", "r2"))
    pdc_request = ResearchCohortRequest(
        pdc_samples,
        provenance_policy="external_same_study",
    )
    pdc_result = run_research_cohort(pdc_request)
    replay = replay_research_cohort(
        pdc_request,
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
    manifest = CohortSourceManifest.from_requests(
        tuple(sample.request for sample in pdc_samples),
        replicate_kinds={sample.sample_id: "technical" for sample in pdc_samples},
    )
    forged = replace(manifest.for_sample("pdc-a"), catalog_response_sha256="f" * 64)
    forged_manifest = CohortSourceManifest((forged, manifest.for_sample("pdc-b")))
    forged_error = False
    try:
        run_research_cohort(
            ResearchCohortRequest(
                pdc_samples,
                provenance_policy="external_same_study",
                source_manifest=forged_manifest,
            )
        )
    except ValueError as error:
        forged_error = "catalog response" in str(error)
    outcomes.append(
        {
            "id": "pdc_manifest_receipt_identity",
            "passed": forged_error,
            "result_digest": None,
            "missing_cells": None,
            "projection": None,
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
