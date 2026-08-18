"""Locked evaluator and benchmark for the research-only proteomics pipeline."""

from __future__ import annotations

import base64
import json
import struct
import sys
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from glio_proteogen.research import ResearchRunRequest, run_research_protein_inference


@dataclass(frozen=True, slots=True)
class Scenario:
    scenario_id: str
    fasta: bytes
    mzml: bytes
    expected_psms: int
    expected_accepted: int
    expected_groups: tuple[tuple[str, ...], ...] = ()
    expected_shared: tuple[str, ...] = ()
    expected_target_winners: int = 0
    expected_decoy_winners: int = 0
    expected_quantified_peptides: int = 0


def _array(values: tuple[float, ...], accession: str) -> str:
    encoded = base64.b64encode(struct.pack(f"<{len(values)}d", *values)).decode("ascii")
    return (
        "<binaryDataArray>"
        f'<cvParam accession="{accession}"/><cvParam accession="MS:1000521"/>'
        f"<binary>{encoded}</binary></binaryDataArray>"
    )


def _spectrum(
    *,
    matched: bool,
    precursor_mz: float,
    spectrum_id: str,
    mz: tuple[float, ...] | None = None,
    intensity: tuple[float, ...] | None = None,
) -> str:
    mz = mz if mz is not None else ((132.0, 229.1, 358.1) if matched else (1.0,))
    intensity = intensity if intensity is not None else ((10.0, 20.0, 30.0) if matched else (1.0,))
    return (
        f'<spectrum id="{spectrum_id}">'
        '<cvParam accession="MS:1000511" value="2"/>'
        "<precursorList><precursor><selectedIonList><selectedIon>"
        f'<cvParam accession="MS:1000744" value="{precursor_mz}"/>'
        '<cvParam accession="MS:1000041" value="1"/>'
        "</selectedIon></selectedIonList></precursor></precursorList>"
        "<binaryDataArrayList>"
        + _array(mz, "MS:1000514")
        + _array(intensity, "MS:1000515")
        + "</binaryDataArrayList></spectrum>"
    )


def _mzml(*, matched: bool, precursor_mz: float = 1087.508837466) -> bytes:
    return (
        "<mzML><run><spectrumList>"
        + _spectrum(matched=matched, precursor_mz=precursor_mz, spectrum_id="scan=1")
        + "</spectrumList></run></mzML>"
    ).encode()


def _multi_mzml() -> bytes:
    return (
        "<mzML><run><spectrumList>"
        + _spectrum(matched=True, precursor_mz=1087.508837466, spectrum_id="scan=1")
        + _spectrum(matched=False, precursor_mz=1087.508837466, spectrum_id="scan=2")
        + "</spectrumList></run></mzML>"
    ).encode()


def _multi_peptide_mzml() -> bytes:
    return (
        "<mzML><run><spectrumList>"
        + _spectrum(
            matched=True,
            precursor_mz=1087.508837466,
            spectrum_id="scan=1",
            mz=(132.047761466, 229.100525466, 358.143118466),
            intensity=(10.0, 20.0, 30.0),
        )
        + _spectrum(
            matched=True,
            precursor_mz=928.462204466,
            spectrum_id="scan=2",
            mz=(98.060040466, 227.102633466, 324.155397466),
            intensity=(5.0, 15.0, 25.0),
        )
        + "</spectrumList></run></mzML>"
    ).encode()


def scenarios() -> tuple[Scenario, ...]:
    return (
        Scenario(
            "target_supported",
            b">P1\nMPEPTIDER\n",
            _mzml(matched=True),
            1,
            1,
            (("P1",),),
            (),
            1,
            0,
            1,
        ),
        Scenario(
            "decoy_rejected",
            b">DECOY_P1\nMPEPTIDER\n",
            _mzml(matched=True),
            1,
            0,
            (),
            (),
            0,
            1,
            0,
        ),
        Scenario("no_match", b">P1\nMPEPTIDER\n", _mzml(matched=False), 0, 0, (), (), 0, 0, 0),
        Scenario(
            "precursor_rejected",
            b">P1\nMPEPTIDER\n",
            _mzml(matched=True, precursor_mz=500.0),
            0,
            0,
            (),
            (),
            0,
            0,
            0,
        ),
        Scenario(
            "shared_peptide_group",
            b">P1\nMPEPTIDER\n>P2\nMPEPTIDER\n",
            _mzml(matched=True),
            1,
            1,
            (("P1", "P2"),),
            ("MPEPTIDER",),
            1,
            0,
            1,
        ),
        Scenario(
            "multi_spectrum",
            b">P1\nMPEPTIDER\n",
            _multi_mzml(),
            1,
            1,
            (("P1",),),
            (),
            1,
            0,
            1,
        ),
        Scenario(
            "multi_peptide_quantification",
            b">P1\nMPEPTIDER\n>P2\nPEPTIDEK\n",
            _multi_peptide_mzml(),
            2,
            2,
            (("P1",), ("P2",)),
            (),
            2,
            0,
            2,
        ),
    )


def _fixture_sha256(locked: tuple[Scenario, ...]) -> str:
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "tests"
        / "fixtures"
        / "research"
        / "proteomics_scenarios.json"
    )
    fixture_bytes = fixture_path.read_bytes()
    fixture = json.loads(fixture_bytes)
    declared = tuple(
        (
            item["id"],
            item["expected_psms"],
            item["expected_accepted"],
            tuple(tuple(group) for group in item.get("expected_groups", [])),
            tuple(item.get("expected_shared", [])),
            item.get("expected_target_winners", 0),
            item.get("expected_decoy_winners", 0),
            item.get("expected_quantified_peptides", 0),
        )
        for item in fixture["scenarios"]
    )
    observed = tuple(
        (
            item.scenario_id,
            item.expected_psms,
            item.expected_accepted,
            item.expected_groups,
            item.expected_shared,
            item.expected_target_winners,
            item.expected_decoy_winners,
            item.expected_quantified_peptides,
        )
        for item in locked
    )
    if declared != observed or fixture["fixture_version"] != "research-proteomics-1":
        raise ValueError
    if any(bool(value) for value in fixture["claims"].values()):
        raise ValueError
    return sha256(fixture_bytes).hexdigest()


def build_scenario_request(scenario: Scenario) -> ResearchRunRequest:
    return ResearchRunRequest(
        sample_id=f"research-eval:{scenario.scenario_id}",
        mzml_source=scenario.mzml,
        fasta_source=scenario.fasta,
        min_matched_ions=1,
        min_peptide_length=7,
        max_peptide_length=12,
    )


def run_evaluator() -> dict[str, object]:
    locked_scenarios = scenarios()
    fixture_digest = _fixture_sha256(locked_scenarios)
    outcomes: list[dict[str, object]] = []
    for scenario in locked_scenarios:
        result = run_research_protein_inference(build_scenario_request(scenario))
        passed = (
            len(result.psms) == scenario.expected_psms
            and len(result.accepted_psms) == scenario.expected_accepted
            and all(
                item.decoy is False and item.q_value is not None for item in result.accepted_psms
            )
            and tuple(tuple(group.accessions) for group in result.protein_groups)
            == scenario.expected_groups
            and tuple(
                peptide for group in result.protein_groups for peptide in group.shared_peptides
            )
            == scenario.expected_shared
            and result.fdr_summary is not None
            and result.fdr_summary.target_winners == scenario.expected_target_winners
            and result.fdr_summary.decoy_winners == scenario.expected_decoy_winners
            and result.fdr_summary.accepted_targets == scenario.expected_accepted
            and len(result.peptide_intensities) == scenario.expected_quantified_peptides
        )
        outcomes.append(
            {
                "scenario_id": scenario.scenario_id,
                "passed": passed,
                "result_digest": result.result_digest,
                "psms": len(result.psms),
                "accepted_psms": len(result.accepted_psms),
                "groups": [list(group.accessions) for group in result.protein_groups],
                "fdr_summary": result.fdr_summary.as_dict() if result.fdr_summary else None,
                "quantified_peptides": len(result.peptide_intensities),
                "search_diagnostics": dict(result.search_diagnostics),
            }
        )
    return {
        "passed": all(bool(item["passed"]) for item in outcomes),
        "declared": len(outcomes),
        "executed": len(outcomes),
        "fixture_sha256": fixture_digest,
        "outcomes": outcomes,
    }


def run_benchmark(iterations: int = 10) -> dict[str, object]:
    if iterations < 1:
        raise ValueError
    request = build_scenario_request(scenarios()[0])
    run_research_protein_inference(request)
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        result = run_research_protein_inference(request)
        samples.append(time.perf_counter_ns() - started)
    ordered = sorted(samples)
    return {
        "iterations": iterations,
        "mean_ns": sum(samples) / len(samples),
        "median_ns": ordered[len(ordered) // 2],
        "p95_ns": ordered[min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))],
        "result_digest": result.result_digest,
    }


if __name__ == "__main__":
    sys.stdout.write(json.dumps({"evaluation": run_evaluator(), "benchmark": run_benchmark()}))
    sys.stdout.write("\n")
