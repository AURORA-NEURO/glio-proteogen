"""Synthetic exact72 source qualification, source holds and private evidence guards."""

from __future__ import annotations

import copy
import csv
import gzip
import hashlib
import io
import json
import pickle
import tarfile
import zipfile
from dataclasses import asdict
from types import SimpleNamespace
from xml.etree.ElementTree import Element, SubElement, tostring

import pytest
from pydantic import ValidationError

from glio_proteogen.research.cptac_gbm_rna_purity_admission.context import ContextState
from glio_proteogen.research.cptac_gbm_rna_purity_execution import clinical as c
from glio_proteogen.research.cptac_gbm_rna_purity_execution.contracts import canonical_bytes, digest

S = ContextState
XMLNS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELNS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOCREL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _xlsx(sheets, *, shared=False, additional=()):
    output = io.BytesIO()
    workbook = Element("workbook", xmlns=XMLNS)
    sheet_list = SubElement(workbook, "sheets")
    relationships = Element("Relationships", xmlns=RELNS)
    strings = []
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, (name, rows) in enumerate(sheets.items(), 1):
            SubElement(
                sheet_list,
                "sheet",
                {"name": name, "sheetId": str(index), f"{{{DOCREL}}}id": f"r{index}"},
            )
            SubElement(
                relationships,
                "Relationship",
                {"Id": f"r{index}", "Target": f"worksheets/sheet{index}.xml"},
            )
            root = Element("worksheet", xmlns=XMLNS)
            data = SubElement(root, "sheetData")
            for ri, values in enumerate(rows, 1):
                row = SubElement(data, "row", r=str(ri))
                for ci, value in enumerate(values):
                    coordinate = chr(65 + ci) + str(ri)
                    cell = SubElement(row, "c", r=coordinate, t="s" if shared else "inlineStr")
                    if shared:
                        strings.append(value)
                        SubElement(cell, "v").text = str(len(strings) - 1)
                    else:
                        SubElement(SubElement(cell, "is"), "t").text = value
            archive.writestr(f"xl/worksheets/sheet{index}.xml", tostring(root))
        archive.writestr("xl/workbook.xml", tostring(workbook))
        archive.writestr("xl/_rels/workbook.xml.rels", tostring(relationships))
        if shared:
            root = Element("sst", xmlns=XMLNS)
            for value in strings:
                SubElement(SubElement(root, "si"), "t").text = value
            archive.writestr("xl/sharedStrings.xml", tostring(root))
        for name, payload in additional:
            archive.writestr(name, payload)
    return output.getvalue()


def _tar(members):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for name, value in members:
            member = tarfile.TarInfo(name)
            if isinstance(value, bytes):
                member.size = len(value)
                archive.addfile(member, io.BytesIO(value))
            else:
                member.type = tarfile.SYMTYPE
                member.linkname = value
                archive.addfile(member)
    return gzip.compress(output.getvalue(), mtime=0)


def _tsv(rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=tuple(rows[0]), delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


def _sheet(rows):
    return [list(rows[0]), *[[row[field] for field in rows[0]] for row in rows]]


def _gdc(rows):
    return {"data": {"hits": rows, "pagination": {"total": len(rows), "from": 0}}}


def _data():
    targets, patient, bio, mapping, core, subtypes, pdc, pdc_status, gdc, gdc_status = (
        [] for _ in range(10)
    )
    for index in range(72):
        case = f"synthetic-private-case-{index}"
        sample = f"synthetic-private-sample-{index}"
        aliquot = f"synthetic-private-aliquot-{index}"
        target = c.ClinicalTarget(
            case_key=case,
            sample_key=sample,
            gdc_sample_id=f"synthetic-gdc-sample-{index}",
            protein_aliquot_key=aliquot,
            protein_aliquot_id=f"synthetic-pdc-aliquot-{index}",
            lineage_digest=digest({"synthetic-lineage": index}),
        )
        targets.append(target)
        result = "Yes" if index < 6 else "No" if index < 40 else ""
        performed = "Yes" if result else "No" if index < 62 else "Unknown"
        method = (
            "Next Gen Sequencing"
            if index in (0, 1) or 6 <= index < 15
            else "IHC"
            if index == 2 or 15 <= index < 27
            else "Unknown"
            if result
            else ""
        )
        patient.append(
            {
                "case_id": case,
                "case_withdrawn": "Yes" if index == 71 else "No",
                "histologic_type": "Glioblastoma",
                c._IDH_PERFORMED: performed,
                c._IDH_RESULT: result,
                c._IDH_DETAIL: "synthetic alteration" if result == "Yes" else "",
                c._IDH_METHOD: method,
                "history_of_cancer": "No",
                "history_of_any_treatment": "",
            }
        )
        if index != 71:
            bio.append(
                {
                    "case_id": case,
                    "specimen_id": sample,
                    "tissue_type": "tumor",
                    "histological_type_eligible": "Yes",
                    "consistent_with_diagnostic_report": "Yes",
                }
            )
        mapping.append(
            {
                "Case ID (Participant ID)": case,
                "Parent Sample ID(s)": sample,
                "Aliquot ID": aliquot,
                "Sample type": "tumor",
            }
        )
        core.append(
            {
                "case_id": case,
                "expert_path_review": "PASS",
                "expert_path_review_details": "NA",
                "excluded_in_downstream_analysis": "FALSE",
                "exclusion_reason": "NA",
                "tumor_reoccur_after_treatment": "TRUE",
            }
        )
        subtypes.append(
            {
                "case": case,
                "sample_type": "tumor",
                "IDH1_alter_status": "Missense" if index in (0, 1, 2, 70) else "NA",
            }
        )
        ancestry = {
            "case_id": f"synthetic-pdc-case-{index}",
            "case_submitter_id": case,
            "sample_id": f"synthetic-pdc-sample-{index}",
            "sample_submitter_id": sample,
            "aliquot_id": target.protein_aliquot_id,
            "aliquot_submitter_id": aliquot,
        }
        pdc.append(
            {
                **ancestry,
                "taxon": "Homo sapiens",
                "primary_site": "Brain",
                "sample_type": "Primary Tumor",
            }
        )
        pdc_status.append(
            {
                **ancestry,
                "case_status": "Qualified",
                "sample_status": "Qualified",
                "aliquot_status": "Qualified",
            }
        )
        gdc_case_id = f"synthetic-gdc-case-{index}"
        gdc.append(
            {
                "case_id": gdc_case_id,
                "submitter_id": case,
                "diagnoses": [
                    {"primary_diagnosis": "Glioblastoma", "diagnosis_is_primary_disease": True}
                ],
                "samples": [
                    {
                        "sample_id": target.gdc_sample_id,
                        "submitter_id": sample,
                        "sample_type": "Primary Tumor",
                        "tissue_type": "Tumor",
                        "specimen_type": "Solid Tissue",
                        "preservation_method": "Snap Frozen",
                        "tumor_descriptor": "Primary",
                    }
                ],
            }
        )
        gdc_status.append({"case_id": gdc_case_id, "submitter_id": case, "state": "released"})
    return SimpleNamespace(
        targets=tuple(targets),
        patient=patient,
        bio=bio,
        mapping=mapping,
        core=core,
        subtypes=subtypes,
        pdc=pdc,
        pdc_status=pdc_status,
        gdc=gdc,
        gdc_status=gdc_status,
    )


def _payloads(data):
    return {
        "metadata_archive": _tar(
            [
                (
                    c._PATIENT_MEMBER,
                    _xlsx(
                        {
                            "Patient_Clinical_Attributes": _sheet(data.patient),
                            "Biospecimen_Attributes": _sheet(data.bio),
                        },
                        shared=True,
                    ),
                ),
                (c._MAP_MEMBER, _xlsx({"GBM TMT Plexes": _sheet(data.mapping)})),
            ]
        ),
        "subtypes_archive": _tar(
            [
                (c._CORE_MEMBER, gzip.compress(_tsv(data.core), mtime=0)),
                (c._SUBTYPE_MEMBER, _tsv(data.subtypes)),
            ]
        ),
        "pdc_biospecimens": canonical_bytes({"data": {"biospecimenPerStudy": data.pdc}}),
        "pdc_status": canonical_bytes({"data": {"biospecimenPerStudy": data.pdc_status}}),
        "gdc_clinical": canonical_bytes(_gdc(data.gdc)),
        "gdc_status": canonical_bytes(_gdc(data.gdc_status)),
    }


def _sources(monkeypatch, payloads):
    locks = tuple(
        c.ClinicalSourceLock(
            role=role,
            filename=f"synthetic-{role}",
            bytes=len(payloads[role]),
            md5=hashlib.md5(payloads[role], usedforsecurity=False).hexdigest(),
            sha256="sha256:" + hashlib.sha256(payloads[role]).hexdigest(),
        )
        for role in c._SOURCE_ROLES
    )
    monkeypatch.setattr(c, "SOURCE_LOCKS", locks)
    return c.ClinicalSources(**payloads)


@pytest.fixture
def synthetic(monkeypatch):
    data = _data()
    payloads = _payloads(data)
    return data, payloads, _sources(monkeypatch, payloads)


def test_exact72_real_semantics_without_model_execution(synthetic):
    data, _, sources = synthetic
    admitted = c.admit_clinical_context(data.targets, sources)
    receipt = admitted.receipt
    assert len(admitted.cases) == 72
    assert receipt.target_context_ready_cases == 0
    assert receipt.clinical_idh_positive_cases == 6
    assert receipt.author_idh1_alteration_cases == 4
    assert receipt.reported_idh_alteration_union_cases == 7
    assert receipt.molecular_method_negative_cases == 9
    assert receipt.ihc_only_negative_cases == 12
    assert receipt.unknown_method_negative_cases == 13
    assert receipt.no_clinical_result_cases == 32
    assert receipt.source_hold_cases == 1
    assert receipt.missing_author_biospecimen_rows == 1
    assert receipt.state_counts.out_of_scope == 6
    assert receipt.state_counts.unknown == 66
    assert not receipt.models_executed
    for case in admitted.cases:
        assert case.component_states[2] is S.UNKNOWN
        assert case.component_states[4:] == (S.UNKNOWN,) * 3
        assert case.component_states[0] is S.SOURCE_SUPPORTED
        assert case.component_states[3] is S.SOURCE_SUPPORTED
    assert admitted.cases[70].idh_alteration_reported
    assert not admitted.cases[70].clinical_idh_positive
    assert admitted.cases[70].state is S.UNKNOWN
    assert admitted.cases[71].source_hold_reasons == (
        "historical_case_withdrawal",
        "historical_withdrawal_current_release_disagreement",
    )


def test_aggregate_has_no_source_identifiers_and_preserves_determinism(synthetic):
    data, _, sources = synthetic
    first = c.admit_clinical_context(data.targets, sources)
    second = c.admit_clinical_context(data.targets, sources)
    assert first.receipt == second.receipt
    public = first.receipt.model_dump_json()
    assert "synthetic-private" not in public
    assert all(target.case_key not in public for target in data.targets)
    assert first.receipt.source_set_digest == digest(
        [lock.model_dump(mode="json") for lock in c.SOURCE_LOCKS]
    )
    assert first.cases[0].target.case_key == data.targets[0].case_key
    assert all(
        obs.source_role in c._SOURCE_ROLES and obs.source_location and obs.field
        for obs in first.cases[0].observations
    )


@pytest.mark.parametrize("operation", [repr, str, pickle.dumps, json.dumps, asdict])
def test_private_wrappers_do_not_implicitly_export(synthetic, operation):
    data, _, sources = synthetic
    admission = c.admit_clinical_context(data.targets, sources)
    for value in (
        data.targets[0],
        sources,
        admission,
        admission.cases[0],
        admission.cases[0].observations[0],
    ):
        if operation in (repr, str):
            assert "synthetic-private" not in operation(value)
        else:
            with pytest.raises(TypeError):
                operation(value)
        with pytest.raises(AttributeError):
            value.extra = "synthetic-private"
        with pytest.raises(AttributeError):
            del value.extra


@pytest.mark.parametrize(
    "changes",
    [
        {"case_key": ""},
        {"case_key": "private bad"},
        {"sample_key": "x" * 129},
        {"gdc_sample_id": 2},
        {"lineage_digest": "bad"},
    ],
)
def test_target_rejects_invalid_semantic_types(changes):
    values = _data().targets[0]._document()
    values.update(changes)
    with pytest.raises((c.ClinicalAdmissionError, ValueError)):
        c.ClinicalTarget(**values)


@pytest.mark.parametrize("kind", ["list", "short", "wrong_type", "duplicate", "corrupted"])
def test_exact_axis_is_checked_before_sources(synthetic, kind):
    data, _, sources = synthetic
    targets = data.targets
    if kind == "list":
        targets = list(targets)
    elif kind == "short":
        targets = targets[:-1]
    elif kind == "wrong_type":
        targets = (*targets[:-1], object())
    elif kind == "duplicate":
        targets = (*targets[:-1], targets[0])
    else:
        object.__setattr__(targets[0], "_values", ())
    with pytest.raises(c.ClinicalAdmissionError):
        c.admit_clinical_context(targets, sources)


@pytest.mark.parametrize("role", c._SOURCE_ROLES)
def test_source_mutation_and_role_swap_fail_before_parsing(synthetic, role):
    data, payloads, _ = synthetic
    changed = dict(payloads)
    changed[role] += b"mutation"
    with pytest.raises(c.ClinicalAdmissionError, match="integrity"):
        c.admit_clinical_context(data.targets, c.ClinicalSources(**changed))
    changed[role] = payloads[c._SOURCE_ROLES[(c._SOURCE_ROLES.index(role) + 1) % 6]]
    with pytest.raises(c.ClinicalAdmissionError, match="integrity"):
        c.admit_clinical_context(data.targets, c.ClinicalSources(**changed))


@pytest.mark.parametrize(
    "payload",
    [b"", bytearray(b"x"), "x", None, b"x" * (c._MAX_SOURCE_BYTES + 1)],
    ids=("empty", "mutable", "text", "none", "oversized"),
)
def test_source_constructor_rejects_nonbytes_or_unbounded(synthetic, payload):
    _, payloads, _ = synthetic
    with pytest.raises(c.ClinicalAdmissionError):
        c.ClinicalSources(**{**payloads, "metadata_archive": payload})


@pytest.mark.parametrize(
    "mutation",
    [
        "patient_duplicate",
        "missing_patient",
        "map_parent",
        "map_case",
        "map_type",
        "pdc_sample",
        "pdc_case",
        "pdc_aliquot",
        "pdc_uuid",
        "gdc_sample",
        "gdc_submitter",
        "diagnosis_count",
        "diagnosis_boolean",
        "historical_diagnosis",
        "clinical_diagnosis",
        "invalid_result",
        "withdrawal_value",
        "somatic_value",
        "bio_duplicate",
        "unknown_method",
        "missing_observation",
    ],
)
def test_exact_joins_and_source_semantics_fail_closed(monkeypatch, mutation):  # noqa: C901, PLR0912 -- independent adversarial source cases
    data = _data()
    if mutation == "patient_duplicate":
        data.patient.append(copy.deepcopy(data.patient[0]))
    elif mutation == "missing_patient":
        data.patient.pop(0)
    elif mutation.startswith("map_"):
        field = {
            "map_parent": "Parent Sample ID(s)",
            "map_case": "Case ID (Participant ID)",
            "map_type": "Sample type",
        }[mutation]
        data.mapping[0][field] = "synthetic-incorrect"
    elif mutation.startswith("pdc_"):
        field = {
            "pdc_sample": "sample_submitter_id",
            "pdc_case": "case_submitter_id",
            "pdc_aliquot": "aliquot_submitter_id",
            "pdc_uuid": "case_id",
        }[mutation]
        data.pdc_status[0][field] = "synthetic-incorrect"
    elif mutation == "gdc_sample":
        data.gdc[0]["samples"][0]["submitter_id"] = "synthetic-incorrect"
    elif mutation == "gdc_submitter":
        data.gdc_status[0]["submitter_id"] = "synthetic-incorrect"
    elif mutation == "diagnosis_count":
        data.gdc[0]["diagnoses"] *= 2
    elif mutation == "diagnosis_boolean":
        data.gdc[0]["diagnoses"][0]["diagnosis_is_primary_disease"] = 1
    elif mutation == "historical_diagnosis":
        data.patient[0]["histologic_type"] = "synthetic-other"
    elif mutation == "clinical_diagnosis":
        data.gdc[0]["diagnoses"][0]["primary_diagnosis"] = "synthetic-other"
    elif mutation == "invalid_result":
        data.patient[0][c._IDH_PERFORMED] = "No"
    elif mutation == "withdrawal_value":
        data.patient[0]["case_withdrawn"] = "Unknown"
    elif mutation == "somatic_value":
        data.subtypes[0]["IDH1_alter_status"] = "WT"
    elif mutation == "bio_duplicate":
        data.bio.append(copy.deepcopy(data.bio[0]))
    elif mutation == "unknown_method":
        data.patient[6][c._IDH_METHOD] = "synthetic unreviewed method"
    else:
        data.gdc[0]["samples"][0].pop("preservation_method")
    with pytest.raises(c.ClinicalAdmissionError) as caught:
        c.admit_clinical_context(data.targets, _sources(monkeypatch, _payloads(data)))
    assert "synthetic-private" not in str(caught.value)


def test_adverse_status_hold_and_nonhuman_are_retained_without_rna(monkeypatch):
    data = _data()
    data.pdc[0]["taxon"] = "Mus musculus"
    data.gdc_status[1]["state"] = "suppressed"
    data.pdc_status[2]["case_status"] = "Disqualified"
    data.gdc[3]["samples"][0]["specimen_type"] = "Blood"
    data.gdc[4]["diagnoses"][0]["diagnosis_is_primary_disease"] = False
    admission = c.admit_clinical_context(data.targets, _sources(monkeypatch, _payloads(data)))
    assert admission.cases[0].component_states[0] is S.OUT_OF_SCOPE
    assert admission.cases[1].source_hold_reasons == ("current_source_status_not_qualified",)
    assert admission.cases[2].source_hold_reasons == ("current_source_status_not_qualified",)
    assert admission.cases[3].component_states[3] is S.UNKNOWN
    assert admission.cases[4].component_states[2] is S.UNKNOWN
    assert admission.receipt.source_hold_cases == 3


@pytest.mark.parametrize(
    "payload",
    [
        b"not gzip",
        gzip.compress(b"short"),
        gzip.compress(b"x") + gzip.compress(b"y"),
        gzip.compress(b"x")[:-2],
    ],
)
def test_compressed_sources_reject_invalid_or_concatenated_data(payload):
    with pytest.raises(c.ClinicalAdmissionError):
        c._archive(payload)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/drive", "back\\slash"])
def test_tar_paths_are_not_extracted_or_followed(name):
    with pytest.raises(c.ClinicalAdmissionError):
        c._archive(_tar([(name, b"x")]))


@pytest.mark.parametrize("members", [[("same", b"x"), ("same", b"y")], [("link", "target")]])
def test_tar_duplicate_or_link_members_fail(members):
    with pytest.raises(c.ClinicalAdmissionError):
        c._archive(_tar(members))


@pytest.mark.parametrize(
    "payload",
    [
        b"not zip",
        b"",
        _xlsx({"Sheet": [["a"]]}, additional=[("../outside", b"x")]),
        _xlsx({"Sheet": [["a"]]}, additional=[("xl/vbaProject.bin", b"x")]),
        _xlsx({"Sheet": [["a"]]}, additional=[("xl/externalLinks/link.xml", b"x")]),
        _xlsx(
            {"Sheet": [["a"]]},
            additional=[
                (
                    "external.rels",
                    b'<Relationships><Relationship TargetMode="External"/></Relationships>',
                )
            ],
        ),
    ],
)
def test_workbook_container_active_content_is_rejected(payload):
    with pytest.raises(c.ClinicalAdmissionError):
        c._workbook(payload)


@pytest.mark.parametrize(
    "payload", [b"<bad", b'<!DOCTYPE root [<!ENTITY a "bad">]><root>&a;</root>']
)
def test_workbook_xml_is_safe(payload):
    with pytest.raises(c.ClinicalAdmissionError):
        c._xml(payload)


@pytest.mark.parametrize("payload", [b"a\ta\n1\t2\n", b"a\n1\t2\n", b"a\tb\n1\n", b"\xff", b"a\n"])
def test_text_table_shape_utf8_and_duplicate_headers(payload):
    with pytest.raises(c.ClinicalAdmissionError):
        c._tsv(payload, ("a",))


@pytest.mark.parametrize(
    "document",
    [
        [],
        {},
        {"data": []},
        {"data": {"hits": []}},
        {"data": {"hits": [{}], "pagination": {"total": 2, "from": 0}}},
        {"data": {"hits": [{}], "pagination": {"total": True, "from": 0}}},
        {"data": {"hits": [{}], "pagination": {"total": 1, "from": 1}}},
        {"errors": [], "data": {"hits": [{}]}},
    ],
)
def test_json_envelope_is_closed_and_complete(document):
    with pytest.raises(c.ClinicalAdmissionError):
        c._json_rows(canonical_bytes(document), "hits")


@pytest.mark.parametrize(
    "payload", [b'{"data":{},"data":{}}', b'{"data":{"hits":[NaN]}}', b"\xff", b"{"]
)
def test_json_duplicate_nonfinite_and_encoding_rejected(payload):
    with pytest.raises(c.ClinicalAdmissionError):
        c._json_rows(payload, "hits")


def test_receipt_rejects_resealed_count_and_source_substitution(synthetic):
    data, _, sources = synthetic
    receipt = c.admit_clinical_context(data.targets, sources).receipt
    for field, value in (
        ("missing_author_biospecimen_rows", 0),
        ("clinical_negative_cases", 0),
        ("reported_idh_alteration_union_cases", 1),
        ("source_set_digest", digest([])),
    ):
        document = receipt.model_dump(mode="json")
        document[field] = value
        document.pop("receipt_digest")
        document["receipt_digest"] = digest(document)
        with pytest.raises((ValidationError, c.ClinicalAdmissionError)):
            c.ClinicalAdmissionReceipt.model_validate_json(canonical_bytes(document))
    with pytest.raises((ValidationError, c.ClinicalAdmissionError)):
        c.ClinicalAdmissionReceipt.model_validate_json(
            receipt.model_dump_json().replace(receipt.receipt_digest, digest([]))
        )
