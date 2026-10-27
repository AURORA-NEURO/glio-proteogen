"""Synthetic source joins and production trust-boundary rejection oracles.

The private fixture factory deliberately bypasses published-source admission.
It exercises exact joins and returns a fixture-marked capability, never evidence
that synthetic metadata came from TCGA, GDC or the publication. Public source
tests retain the real global workbook pin and never open clinical corpora,
RNA assays, model weights, network connections or an inference path.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import pickle
import stat
import zipfile
from dataclasses import asdict, replace
from types import SimpleNamespace
from typing import TYPE_CHECKING
from xml.etree.ElementTree import Element, SubElement, tostring

import pytest
from defusedxml.ElementTree import fromstring

from glio_proteogen.research.cptac_gbm_external_admission.contracts import SourceLock
from glio_proteogen.research.tcga_gbm_historical_replication import contracts as c
from glio_proteogen.research.tcga_gbm_historical_replication import source as s

if TYPE_CHECKING:
    from pathlib import Path

_CASE = "TCGA-ZZ-0001"
_CASE_UUID = "aaaaaaaa-1111-4111-8111-111111111111"
_SAMPLE = _CASE + "-01A"
_SAMPLE_UUID = "bbbbbbbb-2222-4222-8222-222222222222"
_PORTION = _SAMPLE + "-01"
_PORTION_UUID = "cccccccc-3333-4333-8333-333333333333"
_ANALYTE = _PORTION + "R"
_ANALYTE_UUID = "dddddddd-4444-4444-8444-444444444444"
_ALIQUOT = _ANALYTE + "-0000-00"
_ALIQUOT_UUID = "eeeeeeee-5555-4555-8555-555555555555"
_FILE = "ffffffff-6666-4666-8666-666666666666"
_OTHER_UUID = "77777777-7777-4777-8777-777777777777"
_SHEET = "S1A. TCGA discovery dataset"
_SHARED = "http://tcga.nci/bcr/xml/shared/2.7"
_CLINICAL = "http://tcga.nci/bcr/xml/clinical/gbm/2.7"
_BIO = "http://tcga.nci/bcr/xml/biospecimen/2.7"
_XLS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_DOCREL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_ROLES = ("author_workbook", "clinical_xml", "biospecimen_xml", "gdc_metadata", "file_association")
_AUTHOR_HEADERS = {
    "A": "Case",
    "C": "Study",
    "G": "RNAseq",
    "M": "Histology",
    "N": "Grade",
    "V": "IDH status",
    "X": "IDH/codel subtype",
}
_AUTHOR_VALUES = {
    "A": _CASE,
    "C": "Glioblastoma multiforme",
    "G": "Yes",
    "M": "glioblastoma",
    "N": "G4",
    "V": "WT",
    "X": "IDHwt",
}


def _lock(payload: bytes) -> SourceLock:
    return SourceLock(
        bytes=len(payload),
        md5=hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def _json(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _workbook(*, values=None, headers=None, rows=None, sheet_name=_SHEET, additional=()):
    """Bounded authored XLSX using explicit named cells, not publication data."""
    output = io.BytesIO()
    workbook = Element("workbook", xmlns=_XLS)
    sheets = SubElement(workbook, "sheets")
    SubElement(sheets, "sheet", {"name": sheet_name, "sheetId": "1", f"{{{_DOCREL}}}id": "r1"})
    relationships = Element("Relationships", xmlns=_REL)
    SubElement(relationships, "Relationship", {"Id": "r1", "Target": "worksheets/sheet1.xml"})
    worksheet = Element("worksheet", xmlns=_XLS)
    data = SubElement(worksheet, "sheetData")
    content = [({}, 1), (_AUTHOR_HEADERS if headers is None else headers, 2)]
    content.extend(
        (row, index)
        for index, row in enumerate(
            [_AUTHOR_VALUES if values is None else values] if rows is None else rows, start=3
        )
    )
    for cells, index in content:
        row = SubElement(data, "row", r=str(index))
        for column, value in cells.items():
            cell = SubElement(row, "c", r=f"{column}{index}", t="inlineStr")
            SubElement(SubElement(cell, "is"), "t").text = value
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", tostring(workbook))
        archive.writestr("xl/_rels/workbook.xml.rels", tostring(relationships))
        archive.writestr("xl/worksheets/sheet1.xml", tostring(worksheet))
        for name, payload in additional:
            archive.writestr(name, payload)
    return output.getvalue()


def _xml_field(parent, namespace, field, value):
    SubElement(parent, f"{{{namespace}}}{field}").text = value


def _clinical():
    root = Element(f"{{{_CLINICAL}}}tcga_bcr")
    patient = SubElement(root, f"{{{_CLINICAL}}}patient")
    for field, value in (
        ("bcr_patient_barcode", _CASE),
        ("bcr_patient_uuid", _CASE_UUID),
        ("histological_type", "Untreated primary (de novo) GBM"),
        ("history_of_neoadjuvant_treatment", "No"),
    ):
        _xml_field(patient, _SHARED, field, value)
    _xml_field(patient, _CLINICAL, "prior_glioma", "NO")
    return tostring(root)


def _biospecimen():
    root = Element(f"{{{_BIO}}}tcga_bcr")
    patient = SubElement(root, f"{{{_BIO}}}patient")
    _xml_field(patient, _SHARED, "bcr_patient_barcode", _CASE)
    _xml_field(patient, _SHARED, "bcr_patient_uuid", _CASE_UUID)
    parent = SubElement(patient, f"{{{_BIO}}}samples")
    for singular, plural, barcode, uuid in (
        ("sample", "portions", _SAMPLE, _SAMPLE_UUID),
        ("portion", "analytes", _PORTION, _PORTION_UUID),
        ("analyte", "aliquots", _ANALYTE, _ANALYTE_UUID),
        ("aliquot", None, _ALIQUOT, _ALIQUOT_UUID),
    ):
        node = SubElement(parent, f"{{{_BIO}}}{singular}")
        _xml_field(node, _BIO, f"bcr_{singular}_barcode", barcode)
        _xml_field(node, _BIO, f"bcr_{singular}_uuid", uuid)
        if singular == "sample":
            for field, value in (
                ("sample_type", "Primary Tumor"),
                ("tissue_type", "Tumor"),
                ("tumor_descriptor", "Primary"),
                ("days_to_collection", ""),
            ):
                _xml_field(node, _BIO, field, value)
            _xml_field(node, _SHARED, "days_to_sample_procurement", "")
        if singular == "analyte":
            _xml_field(node, _BIO, "analyte_type", "RNA")
        if plural is not None:
            parent = SubElement(node, f"{{{_BIO}}}{plural}")
    return tostring(root)


def _gdc(rna_payload):
    aliquot = {"aliquot_id": _ALIQUOT_UUID, "submitter_id": _ALIQUOT}
    analyte = {
        "analyte_id": _ANALYTE_UUID,
        "submitter_id": _ANALYTE,
        "analyte_type": "RNA",
        "aliquots": [aliquot],
    }
    portion = {"portion_id": _PORTION_UUID, "submitter_id": _PORTION, "analytes": [analyte]}
    sample = {
        "sample_id": _SAMPLE_UUID,
        "submitter_id": _SAMPLE,
        "sample_type": "Primary Tumor",
        "tissue_type": "Tumor",
        "tumor_descriptor": "Primary",
        "portions": [portion],
    }
    case = {
        "case_id": _CASE_UUID,
        "submitter_id": _CASE,
        "project": {"project_id": "TCGA-GBM"},
        "samples": [sample],
    }
    lock = _lock(rna_payload)
    file = {
        "file_id": _FILE,
        "id": _FILE,
        "file_size": lock.bytes,
        "md5sum": lock.md5,
        "access": "open",
        "state": "released",
        "data_format": "TSV",
        "data_type": "Gene Expression Quantification",
        "experimental_strategy": "RNA-Seq",
        "analysis": {"workflow_type": "STAR - Counts"},
        "cases": [case],
    }
    return {"data": {"hits": [file]}}


def _association():
    return {
        "data": {
            "file_id": _FILE,
            "associated_entities": [
                {
                    "entity_id": _ALIQUOT_UUID,
                    "entity_submitter_id": _ALIQUOT,
                    "entity_type": "aliquot",
                    "case_id": _CASE_UUID,
                }
            ],
        },
        "warnings": {},
    }


def _payloads(rna_payload=b"synthetic RNA payload; not source data"):
    return {
        "author_workbook": _workbook(),
        "clinical_xml": _clinical(),
        "biospecimen_xml": _biospecimen(),
        "gdc_metadata": _json(_gdc(rna_payload)),
        "file_association": _json(_association()),
    }


def _fixture(rna_payload=b"synthetic RNA payload; not source data"):
    """Unauthenticated join fixture for source and projection test modules only."""
    payloads = _payloads(rna_payload)
    qualification = s._fixture_qualification(
        payloads, target_file_id=_FILE, rna_lock=_lock(rna_payload)
    )
    return SimpleNamespace(
        payloads=payloads,
        qualification=qualification,
        rna_payload=rna_payload,
        rna_lock=_lock(rna_payload),
        target_file_id=_FILE,
    )


def _change_json(payloads, role, change):
    document = json.loads(payloads[role])
    change(document)
    return {**payloads, role: _json(document)}


def _file(document):
    return document["data"]["hits"][0]


def _case(document):
    return _file(document)["cases"][0]


def _sample(document):
    return _case(document)["samples"][0]


def _portion(document):
    return _sample(document)["portions"][0]


def _analyte(document):
    return _portion(document)["analytes"][0]


def _aliquot(document):
    return _analyte(document)["aliquots"][0]


def _change_xml(payloads, role, namespace, field, value):
    root = fromstring(payloads[role])
    nodes = root.findall(f".//{{{namespace}}}{field}")
    assert len(nodes) == 1
    nodes[0].text = value
    return {**payloads, role: tostring(root)}


def _join(payloads):
    """The private parser/join seam makes no production-source authenticity claim."""
    return s._join_sources(payloads, target_file_id=_FILE)


def test_synthetic_five_role_join_has_exact_original_rna_ancestry_and_direct_file_edge():
    result = _join(_payloads())
    assert result.case_id == _CASE_UUID
    assert result.case_barcode == _CASE
    assert result.file_id == _FILE
    assert result.lineage == (
        (_SAMPLE_UUID, _SAMPLE),
        (_PORTION_UUID, _PORTION),
        (_ANALYTE_UUID, _ANALYTE),
        (_ALIQUOT_UUID, _ALIQUOT),
    )
    fixture = _fixture()
    assert type(fixture.qualification) is c.HistoricalPopulationQualification
    # A private synthetic capability is deliberately not an authorized source
    # for the real RNA verifier, despite internally consistent row joins.
    with pytest.raises(ValueError):
        s.verify_rna_payload(fixture.rna_payload, qualification=fixture.qualification)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("A", "TCGA-ZZ-0002"),
        ("C", "Lower Grade Glioma"),
        ("G", "No"),
        ("M", "astrocytoma"),
        ("N", "G3"),
        ("V", "Mutant"),
        ("V", "Unknown"),
        ("V", "No mutation detected"),
        ("V", ""),
        ("X", "IDHmut-non-codel"),
    ],
)
def test_positive_historical_author_population_requires_each_explicit_source_field(column, value):
    payloads = _payloads()
    payloads["author_workbook"] = _workbook(values={**_AUTHOR_VALUES, column: value})
    with pytest.raises(ValueError):
        _join(payloads)


@pytest.mark.parametrize("kind", ["duplicate_case", "wrong_header", "wrong_sheet"])
def test_author_case_join_cannot_use_duplicate_rows_or_a_stale_table_schema(kind):
    payloads = _payloads()
    options = {
        "duplicate_case": {"rows": [_AUTHOR_VALUES, dict(_AUTHOR_VALUES)]},
        "wrong_header": {"headers": {**_AUTHOR_HEADERS, "V": "IDH1 only"}},
        "wrong_sheet": {"sheet_name": "unreviewed replacement table"},
    }[kind]
    payloads["author_workbook"] = _workbook(**options)
    with pytest.raises(ValueError):
        _join(payloads)


def test_author_case_is_found_by_exact_key_instead_of_saved_row_position():
    payloads = _payloads()
    payloads["author_workbook"] = _workbook(
        rows=[{**_AUTHOR_VALUES, "A": "TCGA-ZZ-0002"}, _AUTHOR_VALUES]
    )
    assert _join(payloads) is not None


@pytest.mark.parametrize(
    ("namespace", "field", "value"),
    [
        (_SHARED, "bcr_patient_barcode", "TCGA-ZZ-0002"),
        (_SHARED, "bcr_patient_uuid", _OTHER_UUID),
        (_SHARED, "histological_type", "Glioblastoma, NOS"),
        (_CLINICAL, "prior_glioma", "YES"),
        (_CLINICAL, "prior_glioma", "Unknown"),
    ],
)
def test_original_clinical_case_and_disease_origin_are_not_replaced_by_primary_sample_role(
    namespace, field, value
):
    payloads = _change_xml(_payloads(), "clinical_xml", namespace, field, value)
    with pytest.raises(ValueError):
        _join(payloads)


@pytest.mark.parametrize("entity", ["sample", "portion", "analyte", "aliquot"])
@pytest.mark.parametrize("coordinate", ["uuid", "barcode"])
def test_each_original_biospecimen_ancestry_uuid_and_barcode_is_required(entity, coordinate):
    payloads = _change_xml(
        _payloads(),
        "biospecimen_xml",
        _BIO,
        f"bcr_{entity}_{coordinate}",
        _OTHER_UUID if coordinate == "uuid" else "synthetic-other-barcode",
    )
    with pytest.raises(ValueError):
        _join(payloads)


@pytest.mark.parametrize(
    ("namespace", "field", "value"),
    [
        (_SHARED, "bcr_patient_uuid", _OTHER_UUID),
        (_SHARED, "bcr_patient_barcode", "TCGA-ZZ-0002"),
        (_BIO, "sample_type", "Blood Derived Normal"),
        (_BIO, "tissue_type", "Normal"),
        (_BIO, "tumor_descriptor", "Recurrent"),
        (_BIO, "analyte_type", "DNA"),
    ],
)
def test_biospecimen_case_and_selected_roles_are_not_inferred_from_barcode_prefixes(
    namespace, field, value
):
    with pytest.raises(ValueError):
        _join(_change_xml(_payloads(), "biospecimen_xml", namespace, field, value))


@pytest.mark.parametrize("entity", ["case", "sample", "portion", "analyte", "aliquot"])
@pytest.mark.parametrize("coordinate", ["uuid", "barcode"])
def test_current_file_nested_ancestry_must_match_every_original_entity(entity, coordinate):
    getter = {
        "case": _case,
        "sample": _sample,
        "portion": _portion,
        "analyte": _analyte,
        "aliquot": _aliquot,
    }[entity]
    key = f"{entity}_id" if coordinate == "uuid" else "submitter_id"
    payloads = _change_json(
        _payloads(),
        "gdc_metadata",
        lambda document: getter(document).__setitem__(
            key, _OTHER_UUID if coordinate == "uuid" else "synthetic-other-barcode"
        ),
    )
    with pytest.raises(ValueError):
        _join(payloads)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("file_id", _OTHER_UUID),
        ("id", _OTHER_UUID),
        ("file_size", True),
        ("file_size", 0),
        ("md5sum", "not-a-checksum"),
        ("access", "controlled"),
        ("state", "withdrawn"),
        ("data_format", "FPKM"),
        ("data_type", "Gene Level Copy Number"),
        ("experimental_strategy", "WXS"),
    ],
)
def test_selected_rna_file_metadata_has_a_strict_exact_file_and_assay_domain(key, value):
    with pytest.raises(ValueError):
        _join(
            _change_json(
                _payloads(), "gdc_metadata", lambda doc: _file(doc).__setitem__(key, value)
            )
        )


@pytest.mark.parametrize("role", ["project", "workflow", "sample_type", "analyte_type"])
def test_current_gdc_population_and_assay_roles_are_source_fields_not_caller_assertions(role):
    def edit(document):
        if role == "project":
            _case(document)["project"]["project_id"] = "TCGA-LGG"
        elif role == "workflow":
            _file(document)["analysis"]["workflow_type"] = "HTSeq - FPKM"
        elif role == "sample_type":
            _sample(document)["sample_type"] = "Blood Derived Normal"
        else:
            _analyte(document)["analyte_type"] = "DNA"

    with pytest.raises(ValueError):
        _join(_change_json(_payloads(), "gdc_metadata", edit))


@pytest.mark.parametrize(
    "kind",
    [
        "absent",
        "duplicate",
        "wrong_aliquot",
        "wrong_barcode",
        "wrong_case",
        "wrong_type",
        "wrong_file",
    ],
)
def test_case_wide_matching_aliquot_cannot_substitute_for_the_direct_selected_file_edge(kind):
    def edit(document):
        row = document["data"]
        entity = row["associated_entities"][0]
        if kind == "absent":
            row["associated_entities"] = []
        elif kind == "duplicate":
            row["associated_entities"].append(dict(entity))
        elif kind == "wrong_file":
            row["file_id"] = _OTHER_UUID
        else:
            key, value = {
                "wrong_aliquot": ("entity_id", _OTHER_UUID),
                "wrong_barcode": ("entity_submitter_id", _ALIQUOT + "-different"),
                "wrong_case": ("case_id", _OTHER_UUID),
                "wrong_type": ("entity_type", "sample"),
            }[kind]
            entity[key] = value

    payloads = _change_json(_payloads(), "file_association", edit)
    with pytest.raises(ValueError):
        _join(payloads)


def test_duplicate_selected_file_metadata_is_not_resolved_by_first_row_order():
    payloads = _change_json(
        _payloads(),
        "gdc_metadata",
        lambda doc: doc["data"]["hits"].append(copy.deepcopy(_file(doc))),
    )
    with pytest.raises(ValueError):
        _join(payloads)


@pytest.mark.parametrize("role", ["clinical_xml", "biospecimen_xml"])
def test_xml_entities_are_never_expanded_for_source_qualification(role):
    payloads = _payloads()
    payloads[role] = (
        b'<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///synthetic-private">]><x>&secret;</x>'
    )
    with pytest.raises(ValueError):
        _join(payloads)


@pytest.mark.parametrize("role", ["gdc_metadata", "file_association"])
@pytest.mark.parametrize(
    "payload", [b'{"data":{},"data":{}}', b'{"data":NaN}', b'{"data":Infinity}', b"\xff"]
)
def test_metadata_json_rejects_duplicate_keys_nonfinite_constants_and_invalid_utf8(role, payload):
    with pytest.raises(ValueError):
        _join({**_payloads(), role: payload})


def test_unused_unsafe_workbook_member_cannot_hide_behind_a_valid_sheet():
    payloads = _payloads()
    payloads["author_workbook"] = _workbook(additional=(("../synthetic-private", b"unused"),))
    with pytest.raises(ValueError):
        _join(payloads)


def test_fixture_qualification_is_private_immutable_and_not_an_original_cptac_context():
    qualification = _fixture().qualification
    assert not hasattr(qualification, "__dict__")
    assert _CASE not in repr(qualification) and _FILE not in repr(qualification)
    for operation in (
        lambda: pickle.dumps(qualification),
        lambda: copy.deepcopy(qualification),
        lambda: json.dumps(qualification),
        lambda: asdict(qualification),
    ):
        with pytest.raises((TypeError, ValueError)):
            operation()
    with pytest.raises((AttributeError, TypeError)):
        qualification.selected_file_id = _OTHER_UUID
    with pytest.raises((TypeError, ValueError)):
        c.HistoricalPopulationQualification()


def test_public_admission_does_not_accept_feasibility_flags_or_a_receipt_as_authority(tmp_path):
    payloads = _payloads()
    paths = _write_paths(tmp_path, payloads)
    untrusted = {
        "source_supported": True,
        "reviewed": True,
        "eligible": True,
        "receipt_digest": "sha256:" + "0" * 64,
    }
    with pytest.raises(ValueError):
        s.admit_historical_population(paths, authority=untrusted, target_file_id=_FILE)


def _write_paths(tmp_path: Path, payloads):
    paths = {}
    for role in _ROLES:
        path = tmp_path / (role + ".source")
        path.write_bytes(payloads[role])
        paths[role] = path
    return c.HistoricalSourcePaths(**paths)


def _authority(
    payloads, rna_payload=b"synthetic RNA payload; not source data", *, author_lock=None
):
    """Synthetic operator configuration; it is not proof of a real-source review."""
    origins = {
        "author_workbook": "https://api.gdc.cancer.gov/data/a0886693-4c6e-40de-9cb1-8bfcb4bb30a7",
        "clinical_xml": "https://api.gdc.cancer.gov/data/88888888-8888-4888-8888-888888888888",
        "biospecimen_xml": "https://api.gdc.cancer.gov/data/99999999-9999-4999-8999-999999999999",
        "gdc_metadata": "https://api.gdc.cancer.gov/files",
        "file_association": "https://api.gdc.cancer.gov/files/" + _FILE,
    }
    resources = tuple(
        c.HistoricalResourceAuthority(
            role=role,
            origin=origins[role],
            version="synthetic-reviewed-source-v1",
            lock=(c.OFFICIAL_AUTHOR_LOCK if author_lock is None else author_lock)
            if role == "author_workbook"
            else _lock(payloads[role]),
        )
        for role in _ROLES
    )
    return c.ReviewedHistoricalSourceAuthority(
        resources=resources,
        review_id="synthetic-operator-review",
        reviewed_rna=c.ReviewedRnaAuthority(file_id=_FILE, lock=_lock(rna_payload)),
    )


def test_public_fixed_workbook_pin_rejects_a_synthetic_book_before_any_semantic_join(
    tmp_path, monkeypatch
):
    payloads = _payloads()
    paths = _write_paths(tmp_path, payloads)
    authority = _authority(payloads)
    joined = []

    def forbidden(*_args, **_kwargs):
        joined.append(True)
        pytest.fail("an arbitrary workbook must not reach the source qualification join")

    monkeypatch.setattr(s, "_join_sources", forbidden)
    with pytest.raises(ValueError):
        s.admit_historical_population(paths, authority=authority, target_file_id=_FILE)
    assert joined == []


def test_rehashed_fake_workbook_cannot_become_published_authority_by_declaring_a_review(tmp_path):
    payloads = _payloads()
    paths = _write_paths(tmp_path, payloads)
    with pytest.raises(ValueError):
        s.admit_historical_population(
            paths,
            authority=_authority(payloads, author_lock=_lock(payloads["author_workbook"])),
            target_file_id=_FILE,
        )


@pytest.mark.parametrize("resources", [(), [], (None,) * 5])
def test_operator_authority_requires_the_complete_strict_role_inventory(resources):
    with pytest.raises(ValueError):
        c.ReviewedHistoricalSourceAuthority(resources=resources, review_id="synthetic-review")


@pytest.mark.parametrize("change", ["duplicate", "missing", "permuted"])
def test_operator_role_locks_cannot_be_dropped_duplicated_or_reordered(change):
    original = _authority(_payloads())
    resources = original.resources
    if change == "duplicate":
        resources = (*resources[:-1], resources[0])
    elif change == "missing":
        resources = resources[:-1]
    else:
        resources = tuple(reversed(resources))
    with pytest.raises(ValueError):
        c.ReviewedHistoricalSourceAuthority(resources=resources, review_id="synthetic-review")


@pytest.mark.parametrize(
    "origin",
    [
        "http://api.gdc.cancer.gov/files",
        "https://api.gdc.cancer.gov.evil/files",
        "https://user:secret@api.gdc.cancer.gov/files",
        "file:///synthetic-private",
    ],
)
def test_source_origins_cannot_claim_a_different_issuer_or_embed_credentials(origin):
    with pytest.raises(ValueError):
        c.HistoricalResourceAuthority(
            role="gdc_metadata", origin=origin, version="synthetic-v1", lock=_lock(b"{}")
        )


@pytest.mark.parametrize("target", ["", "not-a-uuid", True, 1, None])
def test_selected_file_target_requires_an_explicit_uuid_not_a_truthy_review_flag(target):
    with pytest.raises(ValueError):
        s._join_sources(_payloads(), target_file_id=target)


@pytest.mark.parametrize("kind", ["missing", "extra", "text_payload"])
def test_raw_join_role_set_and_bytes_domain_are_closed(kind):
    payloads = _payloads()
    if kind == "missing":
        payloads.pop("file_association")
    elif kind == "extra":
        payloads["reviewed_flags"] = b'{"qualified":true}'
    else:
        payloads["clinical_xml"] = payloads["clinical_xml"].decode()
    with pytest.raises(ValueError):
        _join(payloads)


@pytest.mark.parametrize("role", ["clinical_xml", "biospecimen_xml"])
def test_malformed_xml_is_a_sanitized_source_failure_without_retained_parser_context(role):
    with pytest.raises(c.HistoricalSourceError) as caught:
        _join({**_payloads(), role: b"<synthetic-private-unclosed>"})
    assert caught.value.__context__ is caught.value.__cause__ is None
    assert "synthetic-private" not in str(caught.value)


@pytest.mark.parametrize("role", ["gdc_metadata", "file_association"])
def test_deeply_nested_bounded_json_cannot_escape_as_a_recursion_failure(role):
    payload = b'{"data":' + b"[" * 1500 + b"null" + b"]" * 1500 + b"}"
    assert len(payload) < c.MAX_METADATA_BYTES
    with pytest.raises(c.HistoricalSourceError) as caught:
        _join({**_payloads(), role: payload})
    assert caught.value.__context__ is caught.value.__cause__ is None


@pytest.mark.parametrize("role", ["gdc_metadata", "file_association"])
def test_provider_error_envelope_cannot_be_combined_with_otherwise_matching_source_data(role):
    payloads = _change_json(
        _payloads(),
        role,
        lambda doc: doc.__setitem__("errors", [{"message": "synthetic provider failure"}]),
    )
    with pytest.raises(c.HistoricalSourceError):
        _join(payloads)


@pytest.mark.parametrize("role", ["gdc_metadata", "file_association"])
@pytest.mark.parametrize("warning", [{"provider": ["synthetic warning"]}, [], None])
def test_provider_warnings_or_malformed_warning_envelopes_cannot_grant_qualification(role, warning):
    payloads = _change_json(_payloads(), role, lambda doc: doc.__setitem__("warnings", warning))
    with pytest.raises(c.HistoricalSourceError):
        _join(payloads)


@pytest.mark.parametrize("role", ["gdc_metadata", "file_association"])
@pytest.mark.parametrize("present", [False, True])
def test_absent_or_explicitly_empty_provider_warnings_preserve_matching_evidence(role, present):
    def change(document):
        document.pop("warnings", None)
        if present:
            document["warnings"] = {}

    evidence = _join(_change_json(_payloads(), role, change))
    assert evidence.file_id == _FILE
    assert evidence.lineage[-1] == (_ALIQUOT_UUID, _ALIQUOT)


def test_source_role_content_aliasing_is_rejected_by_the_trusted_authority_inventory():
    authority = _authority(_payloads())
    resources = list(authority.resources)
    resources[2] = replace(resources[2], lock=resources[1].lock)
    with pytest.raises(c.HistoricalSourceError):
        c.ReviewedHistoricalSourceAuthority(
            resources=tuple(resources), review_id="synthetic-review"
        )


@pytest.mark.parametrize("kind", ["same_path", "hardlink", "directory"])
def test_invalid_or_aliased_local_roles_stop_before_any_source_payload_read(
    tmp_path, monkeypatch, kind
):
    payloads = _payloads()
    paths = _write_paths(tmp_path, payloads)
    if kind == "same_path":
        paths = replace(paths, clinical_xml=paths.author_workbook)
    elif kind == "hardlink":
        alias = tmp_path / "synthetic-hardlink"
        alias.hardlink_to(paths.author_workbook)
        paths = replace(paths, clinical_xml=alias)
    else:
        paths = replace(paths, author_workbook=tmp_path)

    def forbidden(*_args, **_kwargs):
        pytest.fail("invalid local roles must not reach a payload reader")

    monkeypatch.setattr(s, "read_verified_source", forbidden)
    with pytest.raises(c.HistoricalSourceError) as caught:
        s.admit_historical_population(paths, authority=_authority(payloads), target_file_id=_FILE)
    assert caught.value.__context__ is caught.value.__cause__ is None


@pytest.mark.parametrize("kind", ["leaf_link", "ancestor_link", "leaf_reparse"])
def test_nonordinary_leaf_or_ancestor_stops_before_payload_reads_without_symlink_privileges(
    tmp_path, monkeypatch, kind
):
    payloads = _payloads()
    paths = _write_paths(tmp_path, payloads)
    target = tmp_path if kind == "ancestor_link" else paths.author_workbook
    ordinary = type(target).lstat

    def inspect(path, *_args, **_kwargs):
        if path == target:
            return SimpleNamespace(
                st_mode=stat.S_IFREG if kind == "leaf_reparse" else stat.S_IFLNK,
                st_file_attributes=0x400 if kind == "leaf_reparse" else 0,
            )
        return ordinary(path)

    def forbidden(*_args, **_kwargs):
        pytest.fail("nonordinary local sources must not reach a payload reader")

    monkeypatch.setattr(type(target), "lstat", inspect)
    monkeypatch.setattr(s, "read_verified_source", forbidden)
    with pytest.raises(c.HistoricalSourceError):
        s.admit_historical_population(paths, authority=_authority(payloads), target_file_id=_FILE)


def test_hash_free_source_receipt_is_closed_and_cannot_redeem_a_fixture_capability():
    qualification = _fixture().qualification
    receipt = qualification.receipt
    document = receipt.model_dump(mode="json")
    assert type(receipt) is c.HistoricalPopulationReceipt
    assert c.HistoricalPopulationReceipt.model_validate_json(receipt.model_dump_json()) == receipt
    assert document["source_evidence_kind"] == "synthetic_fixture"
    assert document["specimen_collection_timepoint"] == "unknown"
    assert document["specimen_treatment_exposure"] == "unknown"
    assert not any("digest" in key or "sha256" in key for key in document)
    assert not set(document) & {"case_id", "file_id", "lineage", "counts", "source_path"}
    serialized = receipt.model_dump_json()
    assert _CASE not in serialized and _FILE not in serialized
    for field in (
        "formal_integrated_diagnosis_established",
        "who2021_reclassification_performed",
        "original_cptac_gate_changed",
        "inference_executed",
    ):
        assert document[field] is False
        for value in (True, 0, 1):
            with pytest.raises(ValueError):
                c.HistoricalPopulationReceipt.model_validate({**document, field: value})
    for fake_authority in (receipt, document, True):
        with pytest.raises(c.HistoricalSourceError):
            s.verify_rna_payload(b"synthetic", qualification=fake_authority)


def test_uuid_letter_case_is_canonicalized_without_casefolding_submitter_barcodes():
    payloads = _payloads()
    for role in ("clinical_xml", "biospecimen_xml"):
        root = fromstring(payloads[role])
        for element in root.iter():
            if element.tag.endswith("_uuid"):
                element.text = element.text.upper()
        payloads[role] = tostring(root)
    evidence = s._join_sources(payloads, target_file_id=_FILE.upper())
    assert evidence.case_id == _CASE_UUID
    assert evidence.file_id == _FILE
    assert evidence.lineage == (
        (_SAMPLE_UUID, _SAMPLE),
        (_PORTION_UUID, _PORTION),
        (_ANALYTE_UUID, _ANALYTE),
        (_ALIQUOT_UUID, _ALIQUOT),
    )
    changed = _change_xml(
        payloads, "biospecimen_xml", _BIO, "bcr_aliquot_barcode", _ALIQUOT.lower()
    )
    with pytest.raises(c.HistoricalSourceError):
        _join(changed)


def test_metadata_role_lock_bound_is_enforced_without_allocating_an_oversized_payload():
    oversized = SourceLock(c.MAX_METADATA_BYTES + 1, "0" * 32, "0" * 64)
    with pytest.raises(c.HistoricalSourceError):
        c.HistoricalResourceAuthority(
            role="gdc_metadata",
            origin="https://api.gdc.cancer.gov/files",
            version="synthetic-v1",
            lock=oversized,
        )


@pytest.mark.parametrize("role", ["gdc_metadata", "file_association"])
def test_metadata_json_byte_limit_precedes_parsing(role):
    with pytest.raises(c.HistoricalSourceError):
        _join({**_payloads(), role: b" " * (c.MAX_METADATA_BYTES + 1)})


def test_blank_original_xml_material_observations_remain_unknown_despite_positive_gdc_roles():
    payloads = _payloads()
    for field in ("tissue_type", "tumor_descriptor"):
        payloads = _change_xml(payloads, "biospecimen_xml", _BIO, field, "")
    qualification = s._fixture_qualification(
        payloads, target_file_id=_FILE, rna_lock=_lock(b"synthetic RNA payload; not source data")
    )
    receipt = qualification.receipt
    assert receipt.original_xml_tissue_type == "unknown"
    assert receipt.original_xml_tumor_descriptor == "unknown"
    assert receipt.specimen_material_basis == (
        "file_specific_gdc_tumor_and_original_xml_primary_tumor_role"
    )
    assert receipt.formal_integrated_diagnosis_established is False
    assert receipt.specimen_collection_timepoint == receipt.specimen_treatment_exposure == "unknown"


def test_blank_original_observation_cannot_cancel_nonblank_source_role_opposition():
    payloads = _change_xml(_payloads(), "biospecimen_xml", _BIO, "tissue_type", "")
    payloads = _change_xml(payloads, "biospecimen_xml", _BIO, "tumor_descriptor", "Recurrent")
    with pytest.raises(c.HistoricalSourceError):
        _join(payloads)


@pytest.mark.parametrize("entity", ["sample", "portion", "analyte", "aliquot"])
@pytest.mark.parametrize("duplicate", ["uuid", "barcode"])
def test_original_biospecimen_identity_collisions_cannot_hide_as_unselected_aliases(
    entity, duplicate
):
    payloads = _payloads()
    root = fromstring(payloads["biospecimen_xml"])
    group = root.find(f".//{{{_BIO}}}{entity}s")
    assert group is not None and len(group) == 1
    extra = copy.deepcopy(group[0])
    changed = extra.find(f"{{{_BIO}}}bcr_{entity}_{'barcode' if duplicate == 'uuid' else 'uuid'}")
    assert changed is not None
    changed.text = "synthetic-other-barcode" if duplicate == "uuid" else _OTHER_UUID
    group.append(extra)
    with pytest.raises(c.HistoricalSourceError):
        _join({**payloads, "biospecimen_xml": tostring(root)})


def _controlled_source_orchestration(tmp_path, monkeypatch, *, reviewed_rna=True):
    """Mock only byte authentication; this does not admit a published source.

    The real fixed publication authority, path snapshots, source parsers,
    qualification factory and RNA re-admission all remain active. The fake
    workbook intentionally does not match the fixed publication byte lock.
    """
    rna_payload = b"controlled synthetic RNA bytes; not a published assay"
    payloads = _payloads(rna_payload)
    paths = _write_paths(tmp_path, payloads)
    authority = _authority(payloads, rna_payload)
    if not reviewed_rna:
        authority = replace(authority, reviewed_rna=None)
    state = SimpleNamespace(
        payloads=payloads,
        paths=paths,
        authority=authority,
        rna_payload=rna_payload,
        reads=[],
        before_return=None,
    )
    resources = {resource.lock.sha256: resource for resource in authority.resources}

    def mocked_byte_authentication(path, lock, *, max_bytes):
        resource = resources[lock.sha256]
        assert lock == resource.lock
        assert max_bytes == c.MAX_METADATA_BYTES
        state.reads.append((resource.role, path))
        if state.before_return is not None:
            state.before_return(resource.role)
        return state.payloads[resource.role]

    monkeypatch.setattr(s, "read_verified_source", mocked_byte_authentication)
    return state


def _admit_controlled_orchestration(state):
    return s.admit_historical_population(
        state.paths, authority=state.authority, target_file_id=_FILE
    )


@pytest.mark.parametrize("reviewed_rna", [False, True])
def test_controlled_source_orchestration_replays_all_raw_roles_before_rna_redemption(
    tmp_path, monkeypatch, reviewed_rna
):
    state = _controlled_source_orchestration(tmp_path, monkeypatch, reviewed_rna=reviewed_rna)
    qualification = _admit_controlled_orchestration(state)
    assert [role for role, _ in state.reads] == list(_ROLES)
    assert qualification.receipt.source_evidence_kind == "reviewed_official_capture"
    assert qualification.receipt.formal_integrated_diagnosis_established is False
    # That receipt label follows the mocked source boundary, not real publisher authentication.
    if reviewed_rna:
        assert s.verify_rna_payload(state.rna_payload, qualification=qualification) == _lock(
            state.rna_payload
        )
        assert [role for role, _ in state.reads] == list(_ROLES) * 2
    else:
        with pytest.raises(c.HistoricalSourceError):
            s.verify_rna_payload(state.rna_payload, qualification=qualification)
        assert [role for role, _ in state.reads] == list(_ROLES)


def _change_synthetic_source_snapshot(path, change):
    if change == "inode":
        replacement = path.with_suffix(".replacement")
        replacement.write_bytes(path.read_bytes())
        replacement.replace(path)
    elif change == "size":
        path.write_bytes(path.read_bytes() + b" ")
    else:
        metadata = path.stat()
        os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000_000))


@pytest.mark.parametrize("change", ["inode", "size", "mtime"])
def test_controlled_source_orchestration_rejects_a_source_changed_during_verified_reads(
    tmp_path, monkeypatch, change
):
    state = _controlled_source_orchestration(tmp_path, monkeypatch)

    def mutate_after_last_role(role):
        if role == _ROLES[-1]:
            _change_synthetic_source_snapshot(state.paths.clinical_xml, change)

    state.before_return = mutate_after_last_role
    with pytest.raises(c.HistoricalSourceError) as caught:
        _admit_controlled_orchestration(state)
    assert [role for role, _ in state.reads] == list(_ROLES)
    assert caught.value.__context__ is caught.value.__cause__ is None


@pytest.mark.parametrize("change", ["inode", "size", "mtime"])
def test_controlled_source_orchestration_rejects_stale_source_snapshots_on_live_rna_replay(
    tmp_path, monkeypatch, change
):
    state = _controlled_source_orchestration(tmp_path, monkeypatch)
    qualification = _admit_controlled_orchestration(state)
    _change_synthetic_source_snapshot(state.paths.clinical_xml, change)
    with pytest.raises(c.HistoricalSourceError):
        s.verify_rna_payload(state.rna_payload, qualification=qualification)
    assert [role for role, _ in state.reads] == list(_ROLES) * 2


def test_controlled_source_orchestration_reparses_changed_role_semantics_on_rna_replay(
    tmp_path, monkeypatch
):
    state = _controlled_source_orchestration(tmp_path, monkeypatch)
    qualification = _admit_controlled_orchestration(state)
    state.payloads = _change_xml(state.payloads, "clinical_xml", _CLINICAL, "prior_glioma", "YES")
    # The real verifier would also reject the old role lock; this seam isolates raw re-admission.
    with pytest.raises(c.HistoricalSourceError):
        s.verify_rna_payload(state.rna_payload, qualification=qualification)
    assert [role for role, _ in state.reads] == list(_ROLES) * 2


@pytest.mark.parametrize("altered", ["binding", "receipt", "authority", "paths", "evidence"])
def test_controlled_source_orchestration_rejects_changed_private_qualification_binding(
    tmp_path, monkeypatch, altered
):
    state = _controlled_source_orchestration(tmp_path, monkeypatch)
    qualification = _admit_controlled_orchestration(state)
    if altered == "binding":
        object.__setattr__(qualification, "_binding", "sha256:" + "0" * 64)
    elif altered == "receipt":
        document = qualification.receipt.model_dump(mode="python")
        document["original_xml_tissue_type"] = "unknown"
        object.__setattr__(qualification, "_receipt", c.HistoricalPopulationReceipt(**document))
    elif altered == "authority":
        object.__setattr__(
            qualification,
            "_authority",
            replace(state.authority, review_id="changed-synthetic-review"),
        )
    elif altered == "paths":
        alias = tmp_path / "copied-clinical.source"
        alias.write_bytes(state.paths.clinical_xml.read_bytes())
        object.__setattr__(qualification, "_paths", replace(state.paths, clinical_xml=alias))
    else:
        evidence = qualification._evidence
        values = evidence._values
        object.__setattr__(evidence, "_values", (values[0], "changed-case-barcode", *values[2:]))
    with pytest.raises(c.HistoricalSourceError):
        s.verify_rna_payload(state.rna_payload, qualification=qualification)
    assert [role for role, _ in state.reads] == list(_ROLES) * 2


@pytest.mark.parametrize("altered", ["file_id", "bytes", "md5"])
def test_controlled_source_orchestration_rejects_reviewed_rna_authority_not_matching_metadata(
    tmp_path, monkeypatch, altered
):
    state = _controlled_source_orchestration(tmp_path, monkeypatch)
    reviewed = state.authority.reviewed_rna
    assert reviewed is not None
    lock = reviewed.lock
    if altered == "file_id":
        reviewed = replace(reviewed, file_id=_OTHER_UUID)
    elif altered == "bytes":
        reviewed = replace(reviewed, lock=SourceLock(lock.bytes + 1, lock.md5, lock.sha256))
    else:
        reviewed = replace(reviewed, lock=SourceLock(lock.bytes, "0" * 32, lock.sha256))
    state.authority = replace(state.authority, reviewed_rna=reviewed)
    with pytest.raises(c.HistoricalSourceError):
        _admit_controlled_orchestration(state)


def test_controlled_source_orchestration_does_not_replace_reviewed_rna_sha_with_a_new_hash(
    tmp_path, monkeypatch
):
    state = _controlled_source_orchestration(tmp_path, monkeypatch)
    lock = _lock(state.rna_payload)
    state.authority = replace(
        state.authority,
        reviewed_rna=c.ReviewedRnaAuthority(_FILE, SourceLock(lock.bytes, lock.md5, "0" * 64)),
    )
    qualification = _admit_controlled_orchestration(state)
    with pytest.raises(c.HistoricalSourceError):
        s.verify_rna_payload(state.rna_payload, qualification=qualification)
    assert [role for role, _ in state.reads] == list(_ROLES) * 2


@pytest.mark.parametrize("altered", ["length", "same_length_content", "mutable_buffer"])
def test_controlled_source_orchestration_requires_exact_reviewed_rna_payload_bytes(
    tmp_path, monkeypatch, altered
):
    state = _controlled_source_orchestration(tmp_path, monkeypatch)
    qualification = _admit_controlled_orchestration(state)
    payload = state.rna_payload
    if altered == "length":
        payload += b"!"
    elif altered == "same_length_content":
        payload = bytes([payload[0] ^ 1]) + payload[1:]
    else:
        payload = bytearray(payload)
    with pytest.raises(c.HistoricalSourceError) as caught:
        s.verify_rna_payload(payload, qualification=qualification)
    assert [role for role, _ in state.reads] == list(_ROLES) * 2
    assert caught.value.__context__ is caught.value.__cause__ is None


@pytest.mark.parametrize("phase", ["admission", "rna_replay"])
def test_controlled_source_orchestration_sanitizes_operational_reader_failure(
    tmp_path, monkeypatch, phase
):
    state = _controlled_source_orchestration(tmp_path, monkeypatch)
    qualification = _admit_controlled_orchestration(state) if phase == "rna_replay" else None

    def fail_at_read(_role):
        raise OSError("SYNTHETIC_PRIVATE_SOURCE_SENTINEL")

    def invoke_failed_reader():
        if phase == "admission":
            _admit_controlled_orchestration(state)
        else:
            s.verify_rna_payload(state.rna_payload, qualification=qualification)

    state.before_return = fail_at_read
    with pytest.raises(c.HistoricalSourceError) as caught:
        invoke_failed_reader()
    assert "SYNTHETIC_PRIVATE_SOURCE_SENTINEL" not in str(caught.value)
    assert caught.value.__context__ is caught.value.__cause__ is None


@pytest.mark.parametrize("review_id", ["", True])
def test_operator_review_identifier_cannot_be_empty_or_a_semantic_approval_flag(review_id):
    authority = _authority(_payloads())
    with pytest.raises(c.HistoricalSourceError):
        replace(authority, review_id=review_id)


def test_clinical_xml_authority_cannot_substitute_a_files_metadata_acquisition_origin():
    clinical = _authority(_payloads()).resources[1]
    assert clinical.role == "clinical_xml"
    with pytest.raises(c.HistoricalSourceError):
        replace(clinical, origin="https://api.gdc.cancer.gov/files")


def test_reviewed_rna_authority_requires_an_exact_source_lock_not_matching_duck_attributes():
    lock = _lock(b"synthetic RNA authority bytes")
    duck_lock = SimpleNamespace(bytes=lock.bytes, md5=lock.md5, sha256=lock.sha256)
    with pytest.raises(c.HistoricalSourceError):
        c.ReviewedRnaAuthority(file_id=_FILE, lock=duck_lock)
