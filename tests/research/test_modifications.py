"""Adversarial coverage for the bounded research modification catalogue."""

from __future__ import annotations

import base64
import struct
from dataclasses import replace

import pytest
from evals.research_proteomics.modifications import run_modification_evaluator

from glio_proteogen.research import modifications as modifications_module
from glio_proteogen.research.fasta import FastaEntry
from glio_proteogen.research.modifications import (
    expand_peptide,
    expand_peptide_map,
    normalize_modification_rules,
    parse_modified_peptide,
    supported_modifications,
)
from glio_proteogen.research.pipeline import (
    ResearchRunRequest,
    replay_research_protein_inference,
    run_research_protein_inference,
)
from glio_proteogen.research.search import (
    SearchParameters,
    _fragments,
    _precursor_mz,
    search_spectrum_candidates,
)
from glio_proteogen.research.search_space import (
    _digest,
    build_search_space_receipt,
    verify_search_space_receipt,
)


def _array(values: tuple[float, ...], accession: str) -> str:
    encoded = base64.b64encode(struct.pack(f"<{len(values)}d", *values)).decode("ascii")
    return (
        "<binaryDataArray>"
        f'<cvParam accession="{accession}"/><cvParam accession="MS:1000521"/>'
        f"<binary>{encoded}</binary></binaryDataArray>"
    )


def _mzml(*, precursor: float, mz: tuple[float, ...]) -> bytes:
    return (
        '<mzML><run><spectrumList><spectrum id="scan=ptm">'
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


def test_catalogue_is_small_sorted_and_mass_finite() -> None:
    specs = supported_modifications()
    assert tuple(item.identifier for item in specs) == ("UNIMOD:21", "UNIMOD:35", "UNIMOD:4")
    assert all(item.delta_mass > 0 for item in specs)
    assert all(item.residues for item in specs)


def test_modification_validation_rejects_empty_type_and_unclosed_annotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert normalize_modification_rules(None) == ()
    with pytest.raises(TypeError, match="tuple or list"):
        normalize_modification_rules(1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-empty"):
        parse_modified_peptide("")
    with pytest.raises(ValueError, match="not closed"):
        parse_modified_peptide("M[UNIMOD:35", allowed_modifications=("UNIMOD:35",))
    monkeypatch.setitem(modifications_module._RESIDUE_MASS, "M", float("nan"))
    with pytest.raises(ValueError, match="finite"):
        parse_modified_peptide("M")


@pytest.mark.parametrize("value", ["UNIMOD:999", "+15.994915", "UNIMOD:35", "unimod:35"])
def test_modification_rules_require_supported_unique_identifiers(value: str) -> None:
    if value.lower() == "unimod:35":
        assert normalize_modification_rules([value]) == ("UNIMOD:35",)
        with pytest.raises(ValueError, match="unique"):
            normalize_modification_rules([value, "UNIMOD:35"])
    elif value == "UNIMOD:35":
        with pytest.raises(ValueError, match="unique"):
            normalize_modification_rules([value, value])
    else:
        with pytest.raises(ValueError):
            normalize_modification_rules([value])


def test_parser_binds_mass_delta_and_site() -> None:
    parsed = parse_modified_peptide("M[UNIMOD:35]STY", allowed_modifications=("UNIMOD:35",))
    assert parsed.sequence == "M[UNIMOD:35]STY"
    assert parsed.modifications[0].position == 0
    assert parsed.residue_masses[0] == pytest.approx(147.0354)


@pytest.mark.parametrize(
    ("peptide", "allowed", "message"),
    [
        ("M[UNIMOD:35]STY", (), "not declared"),
        ("A[UNIMOD:35]STY", ("UNIMOD:35",), "incompatible"),
        ("[UNIMOD:35]MSTY", ("UNIMOD:35",), "unsupported residue"),
        ("M[+15.994915]STY", ("UNIMOD:35",), "outside"),
        ("M[UNIMOD:35][UNIMOD:35]STY", ("UNIMOD:35",), "multiple"),
    ],
)
def test_parser_fails_closed_for_ambiguous_or_undeclared_sites(
    peptide: str, allowed: tuple[str, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        parse_modified_peptide(peptide, allowed_modifications=allowed)


def test_expansion_is_deterministic_and_bounded() -> None:
    expanded = expand_peptide(
        "MST",
        allowed_modifications=("UNIMOD:21", "UNIMOD:35"),
        max_variable_modifications=1,
    )
    assert expanded[0] == "MST"
    assert expanded == expand_peptide(
        "MST",
        allowed_modifications=("UNIMOD:35", "UNIMOD:21"),
        max_variable_modifications=1,
    )
    assert "M[UNIMOD:35]ST" in expanded
    assert "MS[UNIMOD:21]T" in expanded
    with pytest.raises(ValueError, match="exceeds"):
        expand_peptide(
            "MSTY" * 10,
            allowed_modifications=("UNIMOD:21", "UNIMOD:35"),
            max_variable_modifications=3,
            max_variants=2,
        )
    with pytest.raises(ValueError, match="between"):
        expand_peptide("MST", max_variable_modifications=4)
    with pytest.raises(ValueError, match="max_variants"):
        expand_peptide("MST", max_variants=0)
    already_modified = "M[UNIMOD:35]ST"
    assert expand_peptide(
        already_modified,
        allowed_modifications=("UNIMOD:35",),
        max_variable_modifications=1,
    ) == (already_modified,)
    with pytest.raises(ValueError, match="residue limit"):
        parse_modified_peptide("M" * 201)


def test_expansion_preserves_accession_ambiguity() -> None:
    peptide_map: dict[str, tuple[str, ...]] = {"MST": ("P1", "P2")}
    expanded = expand_peptide_map(
        peptide_map, allowed_modifications=("UNIMOD:21",), max_variable_modifications=1
    )
    assert all(value == ("P1", "P2") for value in expanded.values())


def test_modified_masses_drive_precursor_and_fragment_matching() -> None:
    peptide = "M[UNIMOD:35]PEPTIDER"
    fragments = _fragments(peptide, allowed_modifications=("UNIMOD:35",))
    precursor = _precursor_mz(peptide, 2, allowed_modifications=("UNIMOD:35",))
    parameters = SearchParameters(
        fragment_tolerance_da=0.001,
        min_matched_ions=2,
        precursor_charge=2,
        require_precursor_mz=True,
        allowed_modifications=("UNIMOD:35",),
        max_variable_modifications=1,
    )
    candidates = search_spectrum_candidates(
        "scan-ptm",
        precursor,
        {peptide: ("P1",)},
        fragments[0] + fragments[1],
        (1.0,) * len(fragments[0] + fragments[1]),
        parameters=parameters,
    )
    assert len(candidates) == 1
    assert candidates[0].peptide == peptide
    assert candidates[0].precursor_error_ppm == pytest.approx(0.0)
    no_declaration = replace(parameters, allowed_modifications=(), max_variable_modifications=0)
    assert (
        search_spectrum_candidates(
            "scan-ptm",
            precursor,
            {peptide: ("P1",)},
            fragments[0] + fragments[1],
            (1.0,) * len(fragments[0] + fragments[1]),
            parameters=no_declaration,
        )
        == ()
    )


def test_pipeline_expands_declared_modifications_and_replay_binds_controls() -> None:
    peptide = "M[UNIMOD:35]STPEPTIDER"
    fragments = _fragments(peptide, allowed_modifications=("UNIMOD:35",))
    request = ResearchRunRequest(
        sample_id="ptm-research",
        mzml_source=_mzml(
            precursor=_precursor_mz(peptide, 2, allowed_modifications=("UNIMOD:35",)),
            mz=fragments[0] + fragments[1],
        ),
        fasta_source=b">P1\nMSTPEPTIDER\n",
        min_matched_ions=2,
        min_peptide_length=7,
        max_peptide_length=20,
        variable_modifications=("UNIMOD:35",),
        max_variable_modifications=1,
    )
    result = run_research_protein_inference(request)
    assert result.psms and result.psms[0].peptide == peptide
    configuration = dict(result.configuration)
    assert configuration["variable_modifications"] == ["UNIMOD:35"]
    assert result.search_space_receipt is not None
    assert result.search_space_receipt.modified_target_peptides > 1
    assert replay_research_protein_inference(request, result).result_digest == result.result_digest
    forged = replace(result, configuration=(*result.configuration, ("forged", True)))
    with pytest.raises(ValueError, match="digest"):
        replay_research_protein_inference(request, forged)


def test_search_space_receipt_binds_modification_rules_and_variant_counts() -> None:
    entries = (FastaEntry("P1", "MSTPEPTIDER"), FastaEntry("DECOY_P1", "MSTPEPTIDER"))
    receipt = build_search_space_receipt(
        b">P1\nMSTPEPTIDER\n>DECOY_P1\nMSTPEPTIDER\n",
        entries,
        min_peptide_length=7,
        max_peptide_length=20,
        modification_rules=("UNIMOD:35",),
        max_variable_modifications=1,
    )
    assert receipt.modification_rules == ("UNIMOD:35",)
    assert receipt.modified_target_peptides > receipt.target_peptides
    assert receipt.modified_decoy_peptides > receipt.decoy_peptides
    assert receipt.modified_target_decoy_overlap_peptides > receipt.target_decoy_overlap_peptides
    assert receipt.modified_peptide_count == (
        receipt.modified_target_peptides
        + receipt.modified_decoy_peptides
        - receipt.modified_target_decoy_overlap_peptides
    )
    assert verify_search_space_receipt(receipt) == receipt


def test_search_space_receipt_binds_modified_collision_and_unique_count() -> None:
    entries = (FastaEntry("P1", "MSTPEPTIDER"), FastaEntry("DECOY_P1", "MSTPEPTIDER"))
    receipt = build_search_space_receipt(
        b">P1\nMSTPEPTIDER\n>DECOY_P1\nMSTPEPTIDER\n",
        entries,
        min_peptide_length=7,
        max_peptide_length=20,
        modification_rules=("UNIMOD:35",),
        max_variable_modifications=1,
    )
    assert receipt.modified_target_decoy_overlap_peptides == receipt.modified_target_peptides
    assert receipt.modified_peptide_count == receipt.modified_target_peptides
    assert verify_search_space_receipt(receipt) == receipt


def test_search_space_modification_controls_and_receipt_invariants() -> None:
    entries = (FastaEntry("P1", "MSTPEPTIDER"),)
    with pytest.raises(ValueError, match="positive site limit"):
        build_search_space_receipt(
            b">P1\nMSTPEPTIDER\n",
            entries,
            modification_rules=("UNIMOD:35",),
        )
    with pytest.raises(ValueError, match="at least one FASTA"):
        build_search_space_receipt(b"fixture", (), modification_rules=())
    receipt = build_search_space_receipt(b">P1\nMSTPEPTIDER\n", entries)
    forged_pair_count = replace(receipt, paired_proteins=1)
    forged_pair_count = replace(
        forged_pair_count,
        search_space_digest=_digest(
            {
                key: value
                for key, value in forged_pair_count.as_dict().items()
                if key != "search_space_digest"
            }
        ),
    )
    with pytest.raises(ValueError, match="pair count"):
        verify_search_space_receipt(forged_pair_count)
    forged_compatibility = replace(receipt, cleavage_compatible_pairs=1)
    forged_compatibility = replace(
        forged_compatibility,
        search_space_digest=_digest(
            {
                key: value
                for key, value in forged_compatibility.as_dict().items()
                if key != "search_space_digest"
            }
        ),
    )
    with pytest.raises(ValueError, match="compatibility count"):
        verify_search_space_receipt(forged_compatibility)


def test_locked_modification_evaluator_is_green_and_inventory_bound() -> None:
    report = run_modification_evaluator()
    assert report["passed"] is True
    assert report["declared"] == report["executed"] == 4
    inventory_sha256 = report["inventory_sha256"]
    assert isinstance(inventory_sha256, str)
    assert len(inventory_sha256) == 64
