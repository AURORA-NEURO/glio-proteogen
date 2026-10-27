"""Synthetic clinical-source tests; no real case records, assays or inference."""

from __future__ import annotations

import builtins
import copy
import hashlib
import io
import json
import pickle
import zipfile
from pathlib import Path
from types import SimpleNamespace
from xml.etree.ElementTree import Element, SubElement, tostring

import pytest

from glio_proteogen.research.cptac_gbm_external_admission.contracts import SourceLock
from glio_proteogen.research.cptac_gbm_rna_purity_admission.context import ContextState
from glio_proteogen.research.cptac_gbm_rna_purity_execution import (
    clinical,
    inference,
    native_counts,
)
from glio_proteogen.research.cptac_gbm_rna_purity_execution.contracts import ExecutionError
from glio_proteogen.research.cptac_gbm_rna_purity_resolution import source as s
from glio_proteogen.research.gbm_rna_purity import service
from tests.research import test_cptac_rna_purity_execution_clinical as inherited


def _column(index):
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _workbook(sheets, *, additional=()):
    """Use valid multi-letter coordinates for the author's 42-field table."""
    output = io.BytesIO()
    workbook = Element("workbook", xmlns=inherited.XMLNS)
    sheet_list = SubElement(workbook, "sheets")
    relationships = Element("Relationships", xmlns=inherited.RELNS)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, (name, rows) in enumerate(sheets.items(), 1):
            SubElement(
                sheet_list,
                "sheet",
                {"name": name, "sheetId": str(index), f"{{{inherited.DOCREL}}}id": f"r{index}"},
            )
            SubElement(
                relationships,
                "Relationship",
                {"Id": f"r{index}", "Target": f"worksheets/sheet{index}.xml"},
            )
            worksheet = Element("worksheet", xmlns=inherited.XMLNS)
            data = SubElement(worksheet, "sheetData")
            for row_number, values in enumerate(rows, 1):
                row = SubElement(data, "row", r=str(row_number))
                for column_number, value in enumerate(values, 1):
                    cell = SubElement(
                        row, "c", r=f"{_column(column_number)}{row_number}", t="inlineStr"
                    )
                    SubElement(SubElement(cell, "is"), "t").text = value
            archive.writestr(f"xl/worksheets/sheet{index}.xml", tostring(worksheet))
        archive.writestr("xl/workbook.xml", tostring(workbook))
        archive.writestr("xl/_rels/workbook.xml.rels", tostring(relationships))
        for name, value in additional:
            archive.writestr(name, value)
    return output.getvalue()


def _sheets(rows):
    return {
        "README": [["Sheet", "clinical_data", "Clinical characteristics and survival information"]],
        "clinical_data": [list(s.HEADERS), *[[row[field] for field in s.HEADERS] for row in rows]],
        "longitudinal_genetic_alt": [["synthetic unused clinical annotations"]],
    }


def _lock(monkeypatch, payload, **changes):
    values = {
        "bytes": len(payload),
        "md5": hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        "sha256": hashlib.sha256(payload).hexdigest(),
        **changes,
    }
    monkeypatch.setattr(s, "SOURCE_LOCK", SourceLock(**values))
    return payload


def _payload(monkeypatch, rows, *, mutate_sheets=None, additional=()):
    sheets = _sheets(rows)
    if mutate_sheets is not None:
        mutate_sheets(sheets)
    return _lock(monkeypatch, _workbook(sheets, additional=additional))


@pytest.fixture
def baseline(monkeypatch):
    data = inherited._data()
    snapshots = inherited._payloads(data)
    sources = inherited._sources(monkeypatch, snapshots)
    admission = clinical.admit_clinical_context(data.targets, sources)
    assert sum(case.source_hold for case in admission.cases) == 1
    assert (
        sum(
            not case.source_hold and case.state is ContextState.OUT_OF_SCOPE
            for case in admission.cases
        )
        == 6
    )
    assert (
        sum(not case.source_hold and case.state is ContextState.UNKNOWN for case in admission.cases)
        == 65
    )
    rows = []
    for index in range(264):
        target = data.targets[index] if index < 72 else None
        key = target.case_key if target else f"synthetic-extra-case-{index}"
        row = dict.fromkeys(s.HEADERS, "NA")
        row.update(
            preferred_sample_name=key,
            case_id=key,
            parent_sample_ids=target.sample_key if target else f"synthetic-extra-sample-{index}",
            sample_type="CPTAC Pro. Primary Tumor",
            tumor_occurrence_sequence="Primary",
            excluded_in_downstream_analysis="False",
            exclusion_reason="NA",
            cohort="Discovery",
            path_diagnosis="Glioblastoma",
            who_tumor_grade="IV",
            idh1_r132h_mut_status="Negative"
            if index < 39
            else "Not Performed"
            if index < 61
            else "NA",
            age="50",
            sex="Female",
            mgmt_methyl_status="Methylated",
            vital_status="Living",
            path_diag_to_last_contact_days="0",
            path_diag_to_death_days="NA",
            treatment="Reported chemotherapy",
            cancer_history="No",
        )
        rows.append(row)
    rows[70]["parent_sample_ids"] = "synthetic-unselected-same-case-parent"
    return SimpleNamespace(data=data, admission=admission, rows=rows)


def test_unknown65_review_retains_ihc_missingness_and_preserves_baseline(monkeypatch, baseline):
    before = baseline.admission.receipt.model_dump(mode="json")
    payload = _payload(monkeypatch, baseline.rows)
    review = s.review_source(baseline.admission, payload)
    stats = json.loads(review.aggregate_bytes)
    assert len(review.facts) == 65
    assert stats["idh1_r132h"] == {
        "negative": 33,
        "not_performed": 22,
        "unknown": 10,
        "positive": 0,
    }
    assert stats["specimen"] == {"exact_specimen": 64, "specimen_mismatch": 1, "unresolved": 0}
    assert stats["historical_pathology_cases"] == stats["reviewed_cases"] == 65
    assert stats["source_qualified_cases"] == 0
    assert stats["explicit_idh_wildtype_cases"] == 0
    assert stats["explicit_idh2_scope_cases"] == 0
    assert stats["explicit_integrated_diagnosis_cases"] == 0
    assert all(value == 65 for value in stats["field_availability"].values())
    assert baseline.admission.receipt.model_dump(mode="json") == before
    assert s.review_source(baseline.admission, payload).aggregate_bytes == review.aggregate_bytes
    assert "synthetic-" not in review.aggregate_bytes.decode()
    assert all(
        target.case_key.encode() not in review.aggregate_bytes for target in baseline.data.targets
    )


def test_source_history_never_becomes_new_diagnosis(monkeypatch, baseline):
    baseline.rows[6]["cancer_history"] = "IDH-wildtype glioblastoma in historical narrative"
    baseline.rows[6]["idh1_r132h_mut_status"] = "Positive"
    review = s.review_source(baseline.admission, _payload(monkeypatch, baseline.rows))
    fact = review.facts[0]
    assert fact.source_value("cancer_history") == baseline.rows[6]["cancer_history"]
    assert fact.selected_specimen_value("path_diagnosis") == "Glioblastoma"
    stats = json.loads(review.aggregate_bytes)
    assert stats["idh1_r132h"]["positive"] == 1
    assert stats["source_qualified_cases"] == stats["explicit_idh_wildtype_cases"] == 0
    assert stats["explicit_integrated_diagnosis_cases"] == 0


def test_prior_exclusions_and_held_case_are_not_reviewed_as_new_targets(monkeypatch, baseline):
    for index in (*range(6), 71):
        baseline.rows[index].update(
            path_diagnosis="Astrocytoma, IDH-mutant",
            idh1_r132h_mut_status="unreviewed non-target annotation",
            cohort="Confirmatory",
        )
    review = s.review_source(baseline.admission, _payload(monkeypatch, baseline.rows))
    assert len(review.facts) == 65
    assert all(fact.source_value("cohort") == "Discovery" for fact in review.facts)
    assert json.loads(review.aggregate_bytes)["source_qualified_cases"] == 0
    assert baseline.admission.cases[71].source_hold
    assert all(case.state is ContextState.OUT_OF_SCOPE for case in baseline.admission.cases[:6])


def test_blank_idh_result_and_numeric_false_exclusion_keep_original_values(monkeypatch, baseline):
    baseline.rows[6].update(idh1_r132h_mut_status="", excluded_in_downstream_analysis="0")
    review = s.review_source(baseline.admission, _payload(monkeypatch, baseline.rows))
    assert review.facts[0].selected_specimen_value("idh1_r132h_mut_status") == ""
    assert review.facts[0].source_value("excluded_in_downstream_analysis") == "0"
    assert json.loads(review.aggregate_bytes)["idh1_r132h"]["unknown"] == 11


def test_same_case_parent_mismatch_preserves_case_fact_but_blocks_specimen(monkeypatch, baseline):
    review = s.review_source(baseline.admission, _payload(monkeypatch, baseline.rows))
    fact = review.facts[-1]
    assert fact.exact_selected_specimen is False
    assert fact.source_value("path_diagnosis") == "Glioblastoma"
    assert fact.source_value("parent_sample_ids") == "synthetic-unselected-same-case-parent"
    with pytest.raises(s.SourceReviewError, match="does not name the selected specimen"):
        fact.selected_specimen_value("path_diagnosis")
    assert review.facts[0].exact_selected_specimen is True
    assert review.facts[0].selected_specimen_value("idh1_r132h_mut_status") == "Negative"
    assert fact.evidence_digest != review.facts[0].evidence_digest


@pytest.mark.parametrize("token", ["", "NA", "N/A", "Unknown", "Not Performed"])
def test_original_missing_tokens_are_kept_as_source_values(monkeypatch, baseline, token):
    baseline.rows[6]["cancer_history"] = token
    review = s.review_source(baseline.admission, _payload(monkeypatch, baseline.rows))
    assert review.facts[0].source_value("cancer_history") == token
    with pytest.raises(s.SourceReviewError, match="unrecognized clinical source field"):
        review.facts[0].source_value("diagnosis_inferred_from_history")


@pytest.mark.parametrize("parents", ["", "one,one", "one,two", " synthetic-parent", "one, two"])
def test_invalid_or_multiple_parent_axis_fails(monkeypatch, baseline, parents):
    baseline.rows[6]["parent_sample_ids"] = parents
    with pytest.raises(ExecutionError):
        s.review_source(baseline.admission, _payload(monkeypatch, baseline.rows))


@pytest.mark.parametrize("other_case", [0, 7, 71])
def test_parent_from_any_other_selected_case_is_rejected(monkeypatch, baseline, other_case):
    baseline.rows[6]["parent_sample_ids"] = baseline.data.targets[other_case].sample_key
    with pytest.raises(s.SourceReviewError, match="different selected case"):
        s.review_source(baseline.admission, _payload(monkeypatch, baseline.rows))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("case_id", "synthetic-absent-case"),
        ("preferred_sample_name", "synthetic-absent-case"),
        ("sample_type", "Recurrent Tumor"),
        ("cohort", "Confirmatory"),
        ("path_diagnosis", "Astrocytoma, IDH-mutant"),
        ("who_tumor_grade", "III"),
        ("excluded_in_downstream_analysis", "True"),
        ("idh1_r132h_mut_status", "Wildtype"),
    ],
)
def test_exact_target_row_and_reviewed_semantics_required(monkeypatch, baseline, field, value):
    baseline.rows[6][field] = value
    with pytest.raises(s.SourceReviewError):
        s.review_source(baseline.admission, _payload(monkeypatch, baseline.rows))


def test_duplicate_preferred_axis_cannot_hide_ambiguous_case_rows(monkeypatch, baseline):
    baseline.rows[-1] = dict(baseline.rows[6])
    with pytest.raises(s.SourceReviewError, match="schema or preferred sample axis"):
        s.review_source(baseline.admission, _payload(monkeypatch, baseline.rows))


def test_extra_case_row_does_not_replace_the_exact_preferred_row(monkeypatch, baseline):
    baseline.rows[-1]["case_id"] = baseline.data.targets[6].case_key
    baseline.rows[-1]["path_diagnosis"] = "Unrelated historical annotation"
    review = s.review_source(baseline.admission, _payload(monkeypatch, baseline.rows))
    assert (
        review.facts[0].source_value("preferred_sample_name") == baseline.data.targets[6].case_key
    )
    assert review.facts[0].source_value("path_diagnosis") == "Glioblastoma"


@pytest.mark.parametrize("count", [263, 265])
def test_complete_source_axis_required(monkeypatch, baseline, count):
    rows = baseline.rows[:count]
    if count > len(rows):
        extra = dict(rows[-1], preferred_sample_name="synthetic-extra-unique")
        rows = [*rows, extra]
    with pytest.raises(s.SourceReviewError, match="schema or preferred sample axis"):
        s.review_source(baseline.admission, _payload(monkeypatch, rows))


@pytest.mark.parametrize("kind", ["sheet_order", "description", "missing_header", "extra_header"])
def test_exact_workbook_description_and_field_axis(monkeypatch, baseline, kind):
    def mutate(sheets):
        if kind == "sheet_order":
            sheets["README"] = sheets.pop("README")
        elif kind == "description":
            sheets["README"][0][2] = "Different source table"
        elif kind == "missing_header":
            sheets["clinical_data"][0][10] = "idh_result_from_unreviewed_source"
        else:
            for row in sheets["clinical_data"]:
                row.append("unreviewed_column")

    with pytest.raises(ExecutionError):
        s.review_source(
            baseline.admission, _payload(monkeypatch, baseline.rows, mutate_sheets=mutate)
        )


@pytest.mark.parametrize("kind", ["bytes", "sha256", "md5", "bytearray", "truncated"])
def test_strict_reviewed_snapshot_lock(monkeypatch, baseline, kind):
    payload = _workbook(_sheets(baseline.rows))
    changes = {kind: "0" * (64 if kind == "sha256" else 32)} if kind in ("md5", "sha256") else {}
    if kind == "bytes":
        changes = {"bytes": len(payload) + 1}
    _lock(monkeypatch, payload, **changes)
    if kind == "bytearray":
        payload = bytearray(payload)
    elif kind == "truncated":
        payload = payload[:-1]
    with pytest.raises(s.SourceReviewError, match="reviewed snapshot"):
        s.review_source(baseline.admission, payload)


@pytest.mark.parametrize(
    "kind", ["traversal", "active_content", "external_relation", "formula", "dtd"]
)
def test_unsafe_workbook_is_rejected_by_inherited_parser(monkeypatch, baseline, kind):
    payload = _workbook(_sheets(baseline.rows))
    stream = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(payload)) as original,
        zipfile.ZipFile(stream, "w") as rewritten,
    ):
        for member in original.infolist():
            data = original.read(member.filename)
            if kind == "external_relation" and member.filename.endswith(".rels"):
                data = data.replace(b'Target="', b'TargetMode="External" Target="', 1)
            elif kind == "formula" and member.filename == "xl/worksheets/sheet2.xml":
                data = data.replace(b"<is>", b"<f>1+1</f><is>", 1)
            elif kind == "dtd" and member.filename == "xl/worksheets/sheet2.xml":
                data = b'<!DOCTYPE worksheet [<!ENTITY injected "unsafe">]>' + data
            rewritten.writestr(member.filename, data)
        if kind == "traversal":
            rewritten.writestr("../unsafe.xml", b"unsafe")
        elif kind == "active_content":
            rewritten.writestr("xl/vbaProject.bin", b"unsafe")
    with pytest.raises(ExecutionError) as error:
        s.review_source(baseline.admission, _lock(monkeypatch, stream.getvalue()))
    assert "synthetic-private" not in str(error.value)


@pytest.mark.parametrize("operation", [repr, str, pickle.dumps, json.dumps, copy.copy])
def test_private_evidence_immutable_and_not_implicitly_serialized(monkeypatch, baseline, operation):
    review = s.review_source(baseline.admission, _payload(monkeypatch, baseline.rows))
    for value in (review, review.facts[0]):
        if operation in (repr, str):
            assert "synthetic-private" not in operation(value)
        else:
            with pytest.raises(TypeError):
                operation(value)
        with pytest.raises(AttributeError):
            value.extra = "mutable"
        with pytest.raises(AttributeError):
            del value.extra
        with pytest.raises(TypeError):
            value.__getstate__()


def test_aggregate_stats_are_copied_before_they_are_exposed():
    stats = {"nested": {"count": 1}}
    review = s.SourceReview((), stats)
    stats["nested"]["count"] = 9
    public = json.loads(review.aggregate_bytes)
    assert public == {"nested": {"count": 1}}
    public["nested"]["count"] = 10
    assert json.loads(review.aggregate_bytes) == {"nested": {"count": 1}}


def test_fact_snapshots_its_source_dictionary(baseline):
    row = dict(baseline.rows[6])
    fact = s.ClinicalContextFact(baseline.admission.cases[6], row, 8)
    before = fact.evidence_digest
    row["age"] = "modified after review"
    assert fact.source_value("age") == "50"
    assert fact.evidence_digest == before


@pytest.mark.parametrize(
    ("value", "available"),
    [
        ("NA", False),
        ("-1", False),
        ("nan", False),
        ("inf", False),
        ("not a number", False),
        ("0", True),
        ("12.5", True),
    ],
)
def test_reported_numeric_availability_never_infers_missingness(
    monkeypatch, baseline, value, available
):
    row = baseline.rows[6]
    row["age"] = row["path_diag_to_last_contact_days"] = value
    review = s.review_source(baseline.admission, _payload(monkeypatch, baseline.rows))
    counts = json.loads(review.aggregate_bytes)["field_availability"]
    assert counts["reported_age"] == counts["survival_days"] == 64 + int(available)
    assert review.facts[0].source_value("age") == value


def test_missing_categorical_fields_reduce_availability_without_changing_scope(
    monkeypatch, baseline
):
    baseline.rows[6].update(
        sex="Unknown", mgmt_methyl_status="Not Performed", treatment="", vital_status="NA"
    )
    review = s.review_source(baseline.admission, _payload(monkeypatch, baseline.rows))
    stats = json.loads(review.aggregate_bytes)
    for field in ("sex", "mgmt_status", "treatment_history", "vital_status"):
        assert stats["field_availability"][field] == 64
    assert stats["source_qualified_cases"] == 0


@pytest.mark.parametrize(
    "kind",
    [
        "not_admission",
        "short_axis",
        "wrong_case_type",
        "receipt_seal",
        "case_digest",
        "target_axis",
        "partition",
    ],
)
def test_baseline_receipt_axis_and_partition_are_revalidated(monkeypatch, baseline, kind):
    admission = baseline.admission
    if kind == "not_admission":
        admission = SimpleNamespace(cases=admission.cases, receipt=admission.receipt)
    elif kind == "short_axis":
        object.__setattr__(admission, "_cases", admission.cases[:-1])
    elif kind == "wrong_case_type":
        object.__setattr__(admission, "_cases", (*admission.cases[:-1], SimpleNamespace()))
    elif kind == "receipt_seal":
        object.__setattr__(
            admission,
            "_receipt",
            admission.receipt.model_copy(
                update={
                    "receipt_digest": "sha256:" + "0" * 64,
                }
            ),
        )
    elif kind == "case_digest":
        object.__setattr__(admission.cases[6], "_digest", "sha256:" + "0" * 64)
    elif kind == "target_axis":
        object.__setattr__(admission.cases[6], "_target", admission.cases[7].target)
    else:
        object.__setattr__(admission.cases[71], "_hold", ())
    with pytest.raises(ExecutionError):
        s.review_source(admission, _payload(monkeypatch, baseline.rows))


def test_stale_case_states_cannot_reassign_which_cases_are_unknown(monkeypatch, baseline):
    first, second = baseline.admission.cases[0], baseline.admission.cases[6]
    first_states, second_states = first.component_states, second.component_states
    object.__setattr__(first, "_states", second_states)
    object.__setattr__(second, "_states", first_states)
    assert sum(case.state is ContextState.OUT_OF_SCOPE for case in baseline.admission.cases) == 6
    with pytest.raises(ExecutionError):
        s.review_source(baseline.admission, _payload(monkeypatch, baseline.rows))


def test_review_uses_only_supplied_clinical_bytes_without_opening_payloads(monkeypatch, baseline):
    payload = _payload(monkeypatch, baseline.rows)

    def forbidden(*_args, **_kwargs):
        pytest.fail("clinical source review attempted a filesystem or model operation")

    with monkeypatch.context() as guarded:
        guarded.setattr(builtins, "open", forbidden)
        guarded.setattr(Path, "open", forbidden)
        guarded.setattr(Path, "read_bytes", forbidden)
        guarded.setattr(native_counts, "project_native_star_counts", forbidden)
        guarded.setattr(inference, "qualify_execution", forbidden)
        guarded.setattr(inference, "run_qualified_projection", forbidden)
        guarded.setattr(service, "analyze_gbm_rna_purity", forbidden)
        review = s.review_source(baseline.admission, payload)
    assert len(review.facts) == 65
