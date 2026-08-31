from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from glio_proteogen.research.longitudinal_gbm.catalog import longitudinal_gbm_catalog
from glio_proteogen.research.longitudinal_gbm_complex_transition import source_catalog
from glio_proteogen.research.longitudinal_gbm_complex_transition.errors import (
    ComplexTransitionSourceIntegrityError,
)
from tools import import_kncc_longitudinal_gbm as base
from tools import import_kncc_reactome_complex_transition_source as importer

ARTIFACT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "glio_proteogen"
    / "research"
    / "longitudinal_gbm_complex_transition"
    / "data"
    / "kncc_reactome_complex_transition_source.v1.json"
)
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
PDC_SOURCE_DIR = WORKSPACE_ROOT / ".tmp-longitudinal-gbm-source"
HGNC_SOURCE = WORKSPACE_ROOT / ".tmp-neftel-source" / "hgnc_complete_set.txt"
REACTOME_SOURCE_DIR = WORKSPACE_ROOT / ".tmp-reactome-v97"


def _document() -> dict[str, object]:
    return cast("dict[str, object]", json.loads(ARTIFACT.read_bytes()))


def _fake_cohort() -> base.Cohort:
    parent = longitudinal_gbm_catalog()
    oracles: dict[str, object] = {
        "strict_t1_t2_pairs": 104,
        "excluded_specimen_labels": 6,
        "excluded_patient_groups": 5,
        "official_versioned_biospecimen_records": 216,
        "official_versioned_file_manifest_records": 2_503,
        "hgnc_admitted_unique_approved_symbols": 11_312,
        "hgnc_mapping_digest": source_catalog.PARENT_FEATURE_SPACE_DIGEST,
    }
    # Deliberately omit abundance arrays: the import procedure must not read them.
    value = SimpleNamespace(
        genes=tuple(feature.gene_symbol for feature in parent.features),
        patient_groups=tuple(f"KNCC_GBM{index:04d}" for index in range(104)),
        oracles=oracles,
    )
    return cast("base.Cohort", value)


def _walk_keys(value: object) -> list[str]:
    if isinstance(value, dict):
        return [str(key) for key in value] + [
            nested for child in value.values() for nested in _walk_keys(child)
        ]
    if isinstance(value, list):
        return [nested for child in value for nested in _walk_keys(child)]
    return []


def test_catalog_exposes_exact_pilot_panel_and_runtime_interface() -> None:
    loaded = source_catalog.complex_transition_source_catalog()
    assert loaded.profile_id == "kncc-reactome-complex-transition/1.0.0"
    assert loaded.patient_count == 104
    assert len(loaded.genes) == len(loaded.gene_index_by_symbol) == 11_312
    assert len(loaded.complexes) == 28
    assert len(loaded.ablation_families) == len(loaded.complexes_by_domain) == 11
    assert (
        tuple((item.domain_id, item.reactome_id, item.name) for item in loaded.complexes)
        == source_catalog.EXPECTED_COMPLEXES
    )
    assert tuple(item.complex_index for item in loaded.complexes) == tuple(range(28))
    assert loaded.complexes[0].panel_index == loaded.complexes[0].complex_index == 0
    assert (
        loaded.complexes[0].member_inverse_panel_degree_weights
        == loaded.complexes[0].inverse_degree_weights
    )
    assert loaded.gene_index_by_symbol["EGFR"] == 2_893
    assert loaded.complex_by_id["R-HSA-377400"].name == "mTORC1 [cytosol]"
    assert len(loaded.complexes_by_domain["wnt_pcp"]) == 4
    with pytest.raises(TypeError):
        loaded.gene_index_by_symbol["FAKE"] = 0  # type: ignore[index]
    with pytest.raises(TypeError):
        loaded.complex_by_id["FAKE"] = loaded.complexes[0]  # type: ignore[index]


def test_exact_members_pathways_nesting_and_interpretation_ceiling() -> None:
    loaded = source_catalog.complex_transition_source_catalog()
    egfr = loaded.complex_by_id["R-HSA-179791"]
    assert egfr.selection_tier == "domain_anchor"
    assert egfr.anchor_pathway.pathway_id == "R-HSA-180292"
    assert egfr.anchor_pathway.pathway_name == "GAB1 signalosome"
    assert egfr.eligible_feature_indices == (2_893, 3_592, 3_953, 7_072, 7_077)
    assert tuple(
        member.gene_symbol for member in egfr.member_bindings if member.parent_feature_eligible
    ) == (
        "EGFR",
        "GAB1",
        "GRB2",
        "PIK3CA",
        "PIK3R1",
    )
    assert "P62993-1" in egfr.source_uniprot_accessions

    nested_wnt = loaded.complex_by_id["R-HSA-3965386"]
    assert nested_wnt.selected_parent_complex_ids == ("R-HSA-3858472",)
    assert loaded.complex_by_id["R-HSA-3858472"].selected_child_complex_ids == ("R-HSA-3965386",)
    assert nested_wnt.same_family_max_eligible_jaccard == 0.8
    nested_hif = loaded.complex_by_id["R-HSA-1234101"]
    assert nested_hif.same_family_max_eligible_jaccard == 1.0
    assert nested_hif.selected_parent_complex_ids == ("R-HSA-1234141",)

    limitations = " ".join(loaded.limitations)
    assert "not establish in-sample assembly" in limitations
    assert "does not identify essential subunits" in limitations
    assert "not an exhaustive GBM complexome" in limitations
    keys = {key.casefold() for key in _walk_keys(_document())}
    assert keys.isdisjoint(
        {
            "activity",
            "assembly",
            "essential_subunit",
            "stoichiometry",
            "causal_effect",
            "patient_value",
        }
    )


def test_inverse_membership_degree_and_leave_family_out_are_exact() -> None:
    loaded = source_catalog.complex_transition_source_catalog()
    degree: dict[int, int] = {}
    for complex_ in loaded.complexes:
        for index in complex_.member_feature_indices:
            degree[index] = degree.get(index, 0) + 1
    for complex_ in loaded.complexes:
        assert complex_.member_panel_degrees == tuple(
            degree[index] for index in complex_.member_feature_indices
        )
        assert complex_.inverse_degree_weights == tuple(
            round(1.0 / degree[index], 10) for index in complex_.member_feature_indices
        )

    all_ids = tuple(item.reactome_id for item in loaded.complexes)
    for family in loaded.ablation_families:
        assert family.family_id in loaded.complexes_by_domain
        assert family.complex_ids == tuple(
            item.reactome_id for item in loaded.complexes_by_domain[family.family_id]
        )
        assert family.leave_family_out_retained_complex_ids == tuple(
            identifier for identifier in all_ids if identifier not in set(family.complex_ids)
        )
        assert "not a biological knockout" in family.ablation_interpretation


def test_artifact_is_canonical_hard_locked_deidentified_and_source_bound() -> None:
    payload = ARTIFACT.read_bytes()
    document = _document()
    assert len(payload) == source_catalog.EXPECTED_ARTIFACT_BYTES < 128 * 1024
    assert (
        "sha256:" + hashlib.sha256(payload).hexdigest() == source_catalog.EXPECTED_ARTIFACT_SHA256
    )
    assert importer._canonical_bytes(document) == payload
    content = dict(document)
    assert content.pop("artifact_digest") == source_catalog.EXPECTED_CONTENT_DIGEST
    assert importer._digest(content) == source_catalog.EXPECTED_CONTENT_DIGEST
    assert b"KNCC_GBM" not in payload
    assert b'"patient_groups"' not in payload
    for number in range(10_000):
        identifier = f"KNCC_GBM{number:04d}".encode()
        assert identifier not in payload
        assert hashlib.sha256(identifier).hexdigest().encode() not in payload

    loaded = source_catalog.complex_transition_source_catalog()
    assert loaded.artifact_byte_digest == source_catalog.EXPECTED_ARTIFACT_SHA256
    assert loaded.content_digest == source_catalog.EXPECTED_CONTENT_DIGEST
    assert loaded.source_binding_digest == source_catalog.EXPECTED_SOURCE_BINDING_DIGEST
    assert loaded.selection_digest == source_catalog.EXPECTED_SELECTION_DIGEST
    assert loaded.complex_order_digest == source_catalog.EXPECTED_COMPLEX_ORDER_DIGEST
    assert loaded.complex_membership_digest == source_catalog.EXPECTED_COMPLEX_MEMBERSHIP_DIGEST
    assert loaded.pathway_binding_digest == source_catalog.EXPECTED_PATHWAY_BINDING_DIGEST
    assert loaded.overlap_control_digest == source_catalog.EXPECTED_OVERLAP_CONTROL_DIGEST
    assert loaded.provenance["pdc_license"] == "CC-BY-4.0"
    assert loaded.provenance["reactome_annotation_license"] == "CC0-1.0"
    assert loaded.provenance["hgnc_license"] == "CC0-1.0"


@pytest.mark.skipif(
    not (PDC_SOURCE_DIR.is_dir() and HGNC_SOURCE.is_file() and REACTOME_SOURCE_DIR.is_dir()),
    reason="exact local source cache is unavailable",
)
def test_importer_rebuild_is_deterministic_without_reading_abundance_arrays() -> None:
    cohort = _fake_cohort()
    rebuilt = importer.build_artifact(cohort, REACTOME_SOURCE_DIR, HGNC_SOURCE)
    assert importer._canonical_bytes(rebuilt) == ARTIFACT.read_bytes()
    assert rebuilt["artifact_digest"] == source_catalog.EXPECTED_CONTENT_DIGEST
    selection = cast("dict[str, object]", rebuilt["selection"])
    assert selection["panel_status"] == "pilot"
    rule = cast("str", selection["rule"])
    assert "prespecified repository-authored pilot panel" in rule
    assert "selected without reading abundance arrays during import" in rule
    assert selection["outcome_independence_status"] == "not demonstrated outcome-independent"
    assert "exact direct Complex_2_Pathway rows only" in cast(
        "str", selection["association_closure_policy"]
    )


def test_importer_and_loader_fail_closed_on_source_or_artifact_corruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="source lock mismatch"):
        importer.verify_reactome_sources(tmp_path)
    with pytest.raises(ValueError, match="HGNC source filename"):
        importer.verify_hgnc_source(tmp_path / "renamed.tsv")
    with pytest.raises(ValueError, match="duplicate or empty"):
        importer._split_source_ids("P1|P1", field="test")
    with pytest.raises(ValueError, match="UniProt accession"):
        importer._base_accession("not-an-accession")

    payload = ARTIFACT.read_bytes()
    tampered = payload.replace(b"R-HSA-179791", b"R-HSA-179792", 1)
    assert len(tampered) == len(payload)
    source_catalog.complex_transition_source_catalog.cache_clear()
    monkeypatch.setattr(source_catalog, "_resource_bytes", lambda: tampered)
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="byte lock"):
        source_catalog.complex_transition_source_catalog()
    source_catalog.complex_transition_source_catalog.cache_clear()


def test_semantic_validators_reject_forged_members_overlap_and_family_definitions() -> None:
    document = _document()
    raw_complexes = cast("list[object]", deepcopy(document["complexes"]))
    first = cast("dict[str, object]", raw_complexes[0])
    first["selection_tier"] = "outcome_selected"
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="selection tier"):
        source_catalog._parse_complexes(raw_complexes)

    raw_complexes = cast("list[object]", deepcopy(document["complexes"]))
    first = cast("dict[str, object]", raw_complexes[0])
    cast("list[int]", first["member_feature_indices"]).append(11_311)
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="assay-support"):
        source_catalog._parse_complexes(raw_complexes)

    parsed = source_catalog._parse_complexes(cast("list[object]", deepcopy(document["complexes"])))
    forged = list(parsed)
    forged[0] = replace(forged[0], member_panel_degrees=(99,))
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="overlap-control"):
        source_catalog._validate_overlap(tuple(forged))

    families = cast("list[object]", deepcopy(document["ablation_families"]))
    cast("dict[str, object]", families[0])["complex_ids"] = []
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="leave-family-out"):
        source_catalog._parse_families(families, parsed)


def test_write_artifact_rejects_patient_identifier_and_identifier_hash(tmp_path: Path) -> None:
    destination = tmp_path / "artifact.json"
    artifact = _document()
    patient_groups = ("KNCC_GBM0001",)
    forged = deepcopy(artifact)
    cast("dict[str, object]", forged["provenance"])["leak"] = patient_groups[0]
    with pytest.raises(ValueError, match="patient identifier leaked"):
        importer.write_artifact(forged, destination, patient_groups=patient_groups)

    forged = deepcopy(artifact)
    token = hashlib.sha256(patient_groups[0].encode()).hexdigest()
    cast("dict[str, object]", forged["provenance"])["leak"] = token
    with pytest.raises(ValueError, match="identifier hash"):
        importer.write_artifact(forged, destination, patient_groups=patient_groups)
    assert not destination.exists()


def test_panel_uses_only_physiological_pilot_ids_and_exact_direct_anchors() -> None:
    loaded = source_catalog.complex_transition_source_catalog()
    forbidden_tokens = ("mutant", "fusion", "inhibitor", "gefitinib", "erlotinib")
    for complex_ in loaded.complexes:
        lowered = complex_.name.casefold()
        assert not any(token in lowered for token in forbidden_tokens)
        assert complex_.anchor_pathway in complex_.direct_pathway_bindings
        assert re.fullmatch(r"R-HSA-\d+", complex_.reactome_id)
        assert len(complex_.eligible_feature_indices) >= 3
        assert 0.5 <= complex_.parent_feature_mapping_fraction <= 1.0
    assert {item.domain_id for item in loaded.complexes} == {
        "egfr_erbb_signaling",
        "pdgf_signaling",
        "pi3k_akt",
        "mtor_energy_sensing",
        "raf_mapk",
        "wnt_pcp",
        "cell_cycle",
        "dna_repair",
        "hypoxia_vhl",
        "ecm_adhesion",
        "innate_inflammation",
    }
