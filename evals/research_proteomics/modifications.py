"""Locked evaluator for the research-only variable-modification surface."""

from __future__ import annotations

import base64
import json
import struct
from hashlib import sha256
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from glio_proteogen.research import (
    FastaEntry,
    ResearchRunRequest,
    SearchParameters,
    build_search_space_receipt,
    expand_peptide,
    parse_modified_peptide,
    run_research_protein_inference,
    search_spectrum_candidates,
    verify_search_space_receipt,
)
from glio_proteogen.research.search import _fragments, _precursor_mz


def _array(values: tuple[float, ...], accession: str) -> str:
    encoded = base64.b64encode(struct.pack(f"<{len(values)}d", *values)).decode("ascii")
    return (
        "<binaryDataArray>"
        f'<cvParam accession="{accession}"/><cvParam accession="MS:1000521"/>'
        f"<binary>{encoded}</binary></binaryDataArray>"
    )


def _modified_mzml(peptide: str) -> bytes:
    rules = ("UNIMOD:35",)
    fragments = _fragments(peptide, allowed_modifications=rules)
    precursor = _precursor_mz(peptide, 2, allowed_modifications=rules)
    mz = fragments[0] + fragments[1]
    return (
        '<mzML><run><spectrumList><spectrum id="scan=modification">'
        '<cvParam accession="MS:1000511" value="2"/>'
        "<precursorList><precursor><selectedIonList><selectedIon>"
        f'<cvParam accession="MS:1000744" value="{precursor}"/>'
        '<cvParam accession="MS:1000041" value="2"/>'
        "</selectedIon></selectedIonList></precursor></precursorList>"
        "<binaryDataArrayList>"
        + _array(mz, "MS:1000514")
        + _array(tuple(10.0 for _ in mz), "MS:1000515")
        + "</binaryDataArrayList></spectrum></spectrumList></run></mzML>"
    ).encode()


def _declared_ptm_matches() -> dict[str, object]:
    peptide = "M[UNIMOD:35]STPEPTIDER"
    request = ResearchRunRequest(
        sample_id="mod-eval:declared",
        mzml_source=_modified_mzml(peptide),
        fasta_source=b">P1\nMSTPEPTIDER\n",
        min_matched_ions=2,
        min_peptide_length=7,
        max_peptide_length=20,
        variable_modifications=("UNIMOD:35",),
        max_variable_modifications=1,
    )
    result = run_research_protein_inference(request)
    configuration = dict(result.configuration)
    passed = (
        len(result.psms) == 1
        and result.psms[0].peptide == peptide
        and configuration.get("variable_modifications") == ["UNIMOD:35"]
        and result.search_space_receipt is not None
        and result.search_space_receipt.modified_target_peptides > 1
    )
    return {"scenario_id": "declared_ptm_matches", "passed": passed}


def _undeclared_abstains() -> dict[str, object]:
    peptide = "M[UNIMOD:35]STY"
    observed = _fragments(peptide, allowed_modifications=("UNIMOD:35",))
    precursor = _precursor_mz(peptide, 2, allowed_modifications=("UNIMOD:35",))
    candidates = search_spectrum_candidates(
        "scan=undeclared",
        precursor,
        {peptide: ("P1",)},
        observed[0] + observed[1],
        (1.0,) * len(observed[0] + observed[1]),
        parameters=SearchParameters(
            precursor_charge=2,
            min_matched_ions=2,
            require_precursor_mz=True,
        ),
    )
    return {"scenario_id": "undeclared_ptm_abstains", "passed": candidates == ()}


def _receipt_binds_rules() -> dict[str, object]:
    entries = (FastaEntry("P1", "MSTPEPTIDER"), FastaEntry("DECOY_P1", "MSTPEPTIDER"))
    receipt = build_search_space_receipt(
        b">P1\nMSTPEPTIDER\n>DECOY_P1\nMSTPEPTIDER\n",
        entries,
        min_peptide_length=7,
        max_peptide_length=20,
        modification_rules=("UNIMOD:35",),
        max_variable_modifications=1,
    )
    return {
        "scenario_id": "search_space_receipt_binds_rules",
        "passed": (
            verify_search_space_receipt(receipt) == receipt
            and receipt.modification_rules == ("UNIMOD:35",)
            and receipt.modified_target_peptides > receipt.target_peptides
            and receipt.modified_target_decoy_overlap_peptides > 0
            and receipt.modified_peptide_count
            == (
                receipt.modified_target_peptides
                + receipt.modified_decoy_peptides
                - receipt.modified_target_decoy_overlap_peptides
            )
        ),
    }


def _malformed_forms_abstain() -> dict[str, object]:
    invalid = ("A[UNIMOD:35]STY", "M[+15.994915]STY", "M[UNIMOD:35][UNIMOD:35]STY")
    passed = True
    for peptide in invalid:
        try:
            parse_modified_peptide(peptide, allowed_modifications=("UNIMOD:35",))
        except ValueError:
            continue
        passed = False
    try:
        expand_peptide(
            "MSTY" * 10,
            allowed_modifications=("UNIMOD:21", "UNIMOD:35"),
            max_variable_modifications=3,
            max_variants=2,
        )
    except ValueError:
        pass
    else:
        passed = False
    return {"scenario_id": "malformed_modification_abstains", "passed": passed}


def run_modification_evaluator() -> dict[str, object]:
    """Run deterministic PTM scenarios and bind their inventory digest."""

    runners: tuple[Callable[[], dict[str, object]], ...] = (
        _declared_ptm_matches,
        _undeclared_abstains,
        _receipt_binds_rules,
        _malformed_forms_abstain,
    )
    outcomes = tuple(runner() for runner in runners)
    inventory = sha256(
        json.dumps(outcomes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "evaluator_version": "research-modifications-1",
        "declared": len(outcomes),
        "executed": len(outcomes),
        "passed": all(bool(item["passed"]) for item in outcomes),
        "inventory_sha256": inventory,
        "outcomes": list(outcomes),
    }
