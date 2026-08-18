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


def _array(values: tuple[float, ...], accession: str) -> str:
    encoded = base64.b64encode(struct.pack(f"<{len(values)}d", *values)).decode("ascii")
    return (
        "<binaryDataArray>"
        f'<cvParam accession="{accession}"/><cvParam accession="MS:1000521"/>'
        f"<binary>{encoded}</binary></binaryDataArray>"
    )


def _mzml(*, matched: bool) -> bytes:
    mz = (132.0, 229.1, 358.1) if matched else (1.0,)
    intensity = (10.0, 20.0, 30.0) if matched else (1.0,)
    return (
        '<mzML><run><spectrumList><spectrum id="scan=1">'
        '<cvParam accession="MS:1000511" value="2"/>'
        "<binaryDataArrayList>"
        + _array(mz, "MS:1000514")
        + _array(intensity, "MS:1000515")
        + "</binaryDataArrayList></spectrum></spectrumList></run></mzML>"
    ).encode()


def scenarios() -> tuple[Scenario, ...]:
    return (
        Scenario("target_supported", b">P1\nMPEPTIDER\n", _mzml(matched=True), 1, 1),
        Scenario("decoy_rejected", b">DECOY_P1\nMPEPTIDER\n", _mzml(matched=True), 1, 0),
        Scenario("no_match", b">P1\nMPEPTIDER\n", _mzml(matched=False), 0, 0),
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
        (item["id"], item["expected_psms"], item["expected_accepted"])
        for item in fixture["scenarios"]
    )
    observed = tuple(
        (item.scenario_id, item.expected_psms, item.expected_accepted) for item in locked
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
        )
        outcomes.append(
            {
                "scenario_id": scenario.scenario_id,
                "passed": passed,
                "result_digest": result.result_digest,
                "psms": len(result.psms),
                "accepted_psms": len(result.accepted_psms),
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
