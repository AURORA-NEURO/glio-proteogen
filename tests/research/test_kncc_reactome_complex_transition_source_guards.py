"""Adversarial branch tests for the frozen Reactome complex source catalog."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from glio_proteogen.research.longitudinal_gbm_complex_transition import source_catalog
from glio_proteogen.research.longitudinal_gbm_complex_transition.errors import (
    ComplexTransitionSourceIntegrityError,
)

ARTIFACT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "glio_proteogen"
    / "research"
    / "longitudinal_gbm_complex_transition"
    / "data"
    / "kncc_reactome_complex_transition_source.v1.json"
)


def _document() -> dict[str, object]:
    return cast("dict[str, object]", json.loads(ARTIFACT.read_bytes()))


def _complex_rows() -> list[object]:
    return cast("list[object]", deepcopy(_document()["complexes"]))


def _member_rows() -> list[object]:
    first = cast("dict[str, object]", _complex_rows()[0])
    return cast("list[object]", first["member_bindings"])


def _source_bindings() -> dict[str, object]:
    return cast("dict[str, object]", deepcopy(_document()["source_bindings"]))


def _selection() -> dict[str, object]:
    return cast("dict[str, object]", deepcopy(_document()["selection"]))


def _seal(document: dict[str, object]) -> tuple[bytes, str]:
    content = dict(document)
    content.pop("artifact_digest", None)
    digest = source_catalog._digest(content)
    document["artifact_digest"] = digest
    return source_catalog._canonical_bytes(document), digest


def _install_payload(
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    *,
    content_digest: str | None = None,
) -> None:
    source_catalog.complex_transition_source_catalog.cache_clear()
    monkeypatch.setattr(source_catalog, "_resource_bytes", lambda: payload)
    monkeypatch.setattr(source_catalog, "EXPECTED_ARTIFACT_BYTES", len(payload))
    monkeypatch.setattr(
        source_catalog,
        "EXPECTED_ARTIFACT_SHA256",
        "sha256:" + hashlib.sha256(payload).hexdigest(),
    )
    if content_digest is not None:
        monkeypatch.setattr(source_catalog, "EXPECTED_CONTENT_DIGEST", content_digest)


@pytest.fixture(autouse=True)
def _clear_source_catalog_cache() -> None:
    source_catalog.complex_transition_source_catalog.cache_clear()
    yield
    source_catalog.complex_transition_source_catalog.cache_clear()


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        (lambda: source_catalog._object(None, "x"), "must be an object"),
        (lambda: source_catalog._list(None, "x"), "must be an array"),
        (lambda: source_catalog._string(None, "x"), "non-empty string"),
        (lambda: source_catalog._integer(1.0, "x"), "must be an integer"),
        (lambda: source_catalog._finite("1", "x"), "must be numeric"),
        (lambda: source_catalog._finite(float("nan"), "x"), "must be finite"),
        (lambda: source_catalog._string_array(["x", "x"], "x"), "duplicates"),
    ],
)
def test_primitive_parsers_fail_closed(operation: object, message: str) -> None:
    callable_operation = cast("object", operation)
    with pytest.raises(ComplexTransitionSourceIntegrityError, match=message):
        cast("object", callable_operation)()  # type: ignore[operator]


def test_pathway_parser_rejects_shape_and_identifier_forgery() -> None:
    pathway = {
        "pathway_id": "R-HSA-1",
        "pathway_name": "pathway",
        "top_level_pathway_id": "R-HSA-2",
        "top_level_pathway_name": "top",
    }
    malformed_shape = dict(pathway)
    malformed_shape["extra"] = "forged"
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="shape mismatch"):
        source_catalog._parse_pathway(malformed_shape, "pathway")

    malformed_identifier = dict(pathway)
    malformed_identifier["pathway_id"] = "REACTOME:1"
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="identifier is malformed"):
        source_catalog._parse_pathway(malformed_identifier, "pathway")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("parent_feature_index", "0", "integer or null"),
        ("parent_feature_eligible", 1, "eligibility must be boolean"),
        ("source_accessions", [], "no UniProt accession"),
    ],
)
def test_member_parser_rejects_invalid_scalar_fields(
    field: str, value: object, message: str
) -> None:
    members = _member_rows()
    cast("dict[str, object]", members[0])[field] = value
    with pytest.raises(ComplexTransitionSourceIntegrityError, match=message):
        source_catalog._parse_members(members)


def test_member_parser_rejects_parent_axis_and_duplicate_projections() -> None:
    absent_eligible = _member_rows()
    first = cast("dict[str, object]", absent_eligible[0])
    first["parent_feature_index"] = None
    first["parent_feature_eligible"] = True
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="cannot be eligible"):
        source_catalog._parse_members(absent_eligible)

    out_of_range = _member_rows()
    cast("dict[str, object]", out_of_range[0])["parent_feature_index"] = 1_000_000
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="out of range"):
        source_catalog._parse_members(out_of_range)

    disagreement = _member_rows()
    cast("dict[str, object]", disagreement[0])["hgnc_id"] = "HGNC:0"
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="parent feature axis"):
        source_catalog._parse_members(disagreement)

    duplicate = _member_rows()
    first = cast("dict[str, object]", duplicate[0])
    second = cast("dict[str, object]", duplicate[1])
    second["gene_symbol"] = first["gene_symbol"]
    second["hgnc_id"] = first["hgnc_id"]
    second["parent_feature_index"] = None
    second["parent_feature_eligible"] = False
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="projection is duplicated"):
        source_catalog._parse_members(duplicate)


def test_complex_parser_rejects_count_identity_family_and_compartment() -> None:
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="panel count"):
        source_catalog._parse_complexes(_complex_rows()[:-1])

    identity = _complex_rows()
    cast("dict[str, object]", identity[0])["panel_index"] = 99
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="panel identity"):
        source_catalog._parse_complexes(identity)

    family = _complex_rows()
    cast("dict[str, object]", family[0])["ablation_family_id"] = "forged"
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="family/domain"):
        source_catalog._parse_complexes(family)

    compartment = _complex_rows()
    cast("dict[str, object]", compartment[0])["compartment"] = "nucleus"
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="compartment/name"):
        source_catalog._parse_complexes(compartment)


def test_complex_parser_rejects_participant_and_pathway_forgery() -> None:
    participant = _complex_rows()
    cast("dict[str, object]", participant[0])["source_participant_count"] = -1
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="participant projection"):
        source_catalog._parse_complexes(participant)

    pathways = _complex_rows()
    cast("dict[str, object]", pathways[0])["direct_pathway_bindings"] = []
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="pathway binding"):
        source_catalog._parse_complexes(pathways)

    anchor = _complex_rows()
    anchor_row = cast("dict[str, object]", anchor[0])
    anchor_pathway = cast("dict[str, object]", deepcopy(anchor_row["anchor_pathway"]))
    anchor_pathway["pathway_name"] = "forged pathway name"
    anchor_row["anchor_pathway"] = anchor_pathway
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="anchor is not"):
        source_catalog._parse_complexes(anchor)


def test_complex_parser_rejects_membership_assay_and_publication_forgery() -> None:
    membership = _complex_rows()
    membership_row = cast("dict[str, object]", membership[0])
    members = cast("list[object]", membership_row["member_bindings"])
    first_member = cast("dict[str, object]", members[0])
    accessions = cast("list[str]", first_member["source_accessions"])
    first_member["source_accessions"] = [*accessions, "P00000"]
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="binding is incomplete"):
        source_catalog._parse_complexes(membership)

    assay = _complex_rows()
    cast("list[int]", cast("dict[str, object]", assay[0])["member_feature_indices"]).append(11_311)
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="assay-support"):
        source_catalog._parse_complexes(assay)

    publication = _complex_rows()
    cast("dict[str, object]", publication[0])["pubmed_ids"] = [-1]
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="PubMed inventory"):
        source_catalog._parse_complexes(publication)

    closest_family = _complex_rows()
    cast("dict[str, object]", closest_family[0])["same_family_closest_complex_id"] = 7
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="closest-family identifier"):
        source_catalog._parse_complexes(closest_family)


def test_family_axis_and_source_binding_guards() -> None:
    document = _document()
    complexes = source_catalog._parse_complexes(_complex_rows())
    families = cast("list[object]", deepcopy(document["ablation_families"]))
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="family count"):
        source_catalog._parse_families(families[:-1], complexes)

    patient_axis = deepcopy(document)
    cast("dict[str, object]", patient_axis["patient_axis"])["count"] = -1
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="patient-axis"):
        source_catalog._validate_axes(patient_axis)

    gene_axis = deepcopy(document)
    cast("dict[str, object]", gene_axis["gene_axis"])["count"] = -1
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="gene-axis"):
        source_catalog._validate_axes(gene_axis)

    pdc = _source_bindings()
    cast("dict[str, object]", pdc["pdc000514"])["study_id"] = "PDC000000"
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="PDC000514"):
        source_catalog._validate_source_bindings(pdc)

    hgnc = _source_bindings()
    cast("dict[str, object]", hgnc["hgnc"])["filename"] = "forged.tsv"
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="HGNC binding"):
        source_catalog._validate_source_bindings(hgnc)

    reactome = _source_bindings()
    cast("dict[str, object]", reactome["reactome"])["declared_release"] = 96
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="Reactome V97"):
        source_catalog._validate_source_bindings(reactome)


def test_selection_and_projection_digest_guards() -> None:
    complexes = source_catalog._parse_complexes(_complex_rows())

    policy = _selection()
    policy["rule_id"] = "forged-rule"
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="selection policy"):
        source_catalog._validate_selection(policy, complexes)

    count = _selection()
    cast("list[object]", count["domain_inventory"]).pop()
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="inventory count"):
        source_catalog._validate_selection(count, complexes)

    declaration = _selection()
    first_domain = cast(
        "dict[str, object]", cast("list[object]", declaration["domain_inventory"])[0]
    )
    first_domain["complex_count"] = -1
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="domain declaration"):
        source_catalog._validate_selection(declaration, complexes)

    no_anchor = list(complexes)
    no_anchor[0] = replace(no_anchor[0], selection_tier="supporting_mechanism")
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="lacks one exact anchor"):
        source_catalog._validate_selection(_selection(), tuple(no_anchor))

    forged_projection = _document()
    cast("dict[str, object]", forged_projection["projection_digests"])["complex_order_digest"] = (
        "sha256:" + "0" * 64
    )
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="projection digest"):
        source_catalog._validate_projection_digests(forged_projection)


def test_loader_rejects_invalid_noncanonical_and_content_forgery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid = b"{"
    _install_payload(monkeypatch, invalid)
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="not valid JSON"):
        source_catalog.complex_transition_source_catalog()

    noncanonical = b'{"x":1}\n\n'
    _install_payload(monkeypatch, noncanonical)
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="not canonical JSON"):
        source_catalog.complex_transition_source_catalog()

    content = _document()
    content["artifact_digest"] = "sha256:" + "0" * 64
    payload = source_catalog._canonical_bytes(content)
    _install_payload(monkeypatch, payload)
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="content digest"):
        source_catalog.complex_transition_source_catalog()


def test_loader_rejects_identity_provenance_and_interpretation_forgery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = _document()
    identity["profile_id"] = "forged-profile"
    payload, content_digest = _seal(identity)
    _install_payload(monkeypatch, payload, content_digest=content_digest)
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="top-level identity"):
        source_catalog.complex_transition_source_catalog()

    provenance = _document()
    cast("dict[str, object]", provenance["provenance"])["forged"] = ["not", "scalar"]
    payload, content_digest = _seal(provenance)
    _install_payload(monkeypatch, payload, content_digest=content_digest)
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="scalar values"):
        source_catalog.complex_transition_source_catalog()

    limitations = _document()
    limitations["limitations"] = ["research-use-only"]
    payload, content_digest = _seal(limitations)
    _install_payload(monkeypatch, payload, content_digest=content_digest)
    with pytest.raises(ComplexTransitionSourceIntegrityError, match="ceiling is incomplete"):
        source_catalog.complex_transition_source_catalog()
