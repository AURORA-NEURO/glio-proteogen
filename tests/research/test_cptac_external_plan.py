"""Synthetic metadata receipts exercise the exact replay and privacy boundary."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import pickle
from dataclasses import FrozenInstanceError, asdict
from uuid import UUID

import pytest

from glio_proteogen.research.cptac_gbm_external_admission import plan
from glio_proteogen.research.cptac_gbm_external_admission.contracts import SourceVerificationError
from glio_proteogen.research.cptac_gbm_external_admission.protein import (
    PROTEIN_LOCK,
    SAMPLE_MAP_LOCK,
)
from glio_proteogen.research.cptac_gbm_external_admission.source import read_verified_source

_PAYLOAD = b"synthetic measurement bytes"


def _uuid(number):
    return str(UUID(int=number))


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def _bytes(value):
    return json.dumps(value, allow_nan=False, separators=(",", ":")).encode()


def _fixture(count=2):
    channels = sorted(plan._CHANNELS)
    candidates = []
    choices = []
    downloaded = []
    for index in range(count):
        rna_id, cnv_id = _uuid(1000 + index * 2), _uuid(1001 + index * 2)
        candidates.append(
            {
                "case_submitter_id": f"fixture-case-{index:03}",
                "sample_submitter_id": f"fixture-sample-{index:03}",
                "GDC_sample_uuid": _uuid(2000 + index),
                "PDC_protein_aliquot_submitter_id": f"unrelated-exact-label-{index:03}",
                "PDC_protein_aliquot_uuid": _uuid(3000 + index),
                "RNA_file_id": rna_id,
                "gene_CNV_file_id": cnv_id,
                "exact_once_in_sample_map": True,
                "metadata_candidate_not_admitted": True,
                "sample_map_occurrences": [
                    {
                        "channel": channels[index % len(channels)],
                        "plex_index": index // len(channels),
                    }
                ],
            }
        )
        for file_id, assay, workflow in (
            (rna_id, "RNA", "STAR - Counts"),
            (cnv_id, "gene_CNV", "AscatNGS"),
        ):
            md5 = hashlib.md5(_PAYLOAD, usedforsecurity=False).hexdigest()
            choices.append(
                {
                    "file_id": file_id,
                    "file_name": "uninformative-name.txt",
                    "file_size": len(_PAYLOAD),
                    "md5sum": md5,
                    "workflow": workflow,
                    "assay": assay,
                    "access": "open",
                }
            )
            downloaded.append(
                {
                    "file_id": file_id,
                    "relative_path": file_id + ".bin",
                    "bytes": len(_PAYLOAD),
                    "md5": md5,
                    "sha256": _digest(_PAYLOAD),
                    "workflow": workflow,
                    "official_size_and_md5_verified": True,
                }
            )
    pdc = []
    for index, (length, md5) in enumerate(
        (
            (PROTEIN_LOCK.bytes, PROTEIN_LOCK.md5),
            (SAMPLE_MAP_LOCK.bytes, SAMPLE_MAP_LOCK.md5),
            (1, "a" * 32),
        )
    ):
        pdc.append(
            {
                "file_id": _uuid(4000 + index),
                "file_name": "no-filename-inference.txt",
                "file_size": str(length),
                "md5sum": md5,
                "data_category": "Protein Assembly",
                "file_type": "Text",
                "pdc_study_id": "PDC000446",
                "study_id": _uuid(5000),
            }
        )
    choice = {
        "GDC_candidate_file_choices": choices,
        "PDC_candidate_source_files": pdc,
        "candidate_count": count,
        "measurement_downloaded": False,
        "sample_map_matched_candidate_rows": candidates,
        "status": plan._CHOICE_STATUS,
        "withheld_count_absent_from_map": 1,
    }
    manifest = {
        "failures": [],
        "files": downloaded,
        "model_fits": False,
        "official_size_and_md5_verified_files": 2 * count,
        "redistribution_status": "local_only_terms_unverified",
        "requested_files": 2 * count,
        "schema": "frozen-confirmatory-GDC-downloads/1.0.0",
        "selected_specimens": count,
        "source_plan_sha256": "a" * 64,
        "verified_bytes": len(_PAYLOAD) * 2 * count,
    }
    return choice, manifest


def _decode(choice, manifest, count=2):
    return plan._decode_plan(
        choice,
        manifest,
        choices_sha256="a" * 64,
        files_manifest_sha256="b" * 64,
        candidate_count=count,
    )


def _write_public(tmp_path, count=56):
    choice, manifest = _fixture(count)
    choices_path = tmp_path / "choices.private.json"
    choices_payload = _bytes(choice)
    choices_path.write_bytes(choices_payload)
    manifest["source_plan_sha256"] = _digest(choices_payload)
    manifest_path = tmp_path / "files.private.json"
    manifest_payload = _bytes(manifest)
    manifest_path.write_bytes(manifest_payload)
    for row in manifest["files"]:
        (tmp_path / row["relative_path"]).write_bytes(_PAYLOAD)
    return {
        "choices_path": choices_path,
        "choices_sha256": _digest(choices_payload),
        "files_manifest_path": manifest_path,
        "files_manifest_sha256": _digest(manifest_payload),
    }


def test_exact_sorted_bindings_preserve_roles_without_label_or_filename_inference():
    choice, manifest = _fixture()
    choice["sample_map_matched_candidate_rows"].reverse()
    choice["GDC_candidate_file_choices"].reverse()
    manifest["files"].reverse()
    result = _decode(choice, manifest)
    assert tuple(row.case_submitter_id for row in result.candidates) == (
        "fixture-case-000",
        "fixture-case-001",
    )
    assert result.protein_aliquots == ("unrelated-exact-label-000", "unrelated-exact-label-001")
    for candidate in result.candidates:
        assert result.files[candidate.rna_file_id].workflow == "STAR - Counts"
        assert result.files[candidate.cnv_file_id].workflow == "AscatNGS"
        assert candidate.metadata_candidate_not_admitted is True
    assert result.receipt.manifest_verified_bytes == 4 * len(_PAYLOAD)


def test_private_bindings_are_read_only_repr_hidden_and_nonpickleable():
    choice, manifest = _fixture()
    result = _decode(choice, manifest)
    candidate = result.candidates[0]
    binding = result.files[candidate.rna_file_id]
    for value in (result, candidate, binding):
        with pytest.raises(TypeError, match="cannot be serialized"):
            pickle.dumps(value)
        with pytest.raises(TypeError, match="cannot be serialized"):
            value.__getstate__()
    assert candidate.case_submitter_id not in repr(result)
    assert candidate.protein_aliquot_submitter_id not in repr(candidate)
    assert candidate.rna_file_id not in repr(binding)
    with pytest.raises(TypeError):
        result.files["extra"] = binding
    with pytest.raises(FrozenInstanceError):
        candidate.rna_file_id = "changed"
    with pytest.raises(FrozenInstanceError):
        result.receipt.eligibility_admitted = True
    copied = dict(result.files)
    rebuilt = plan.ExternalAdmissionPlan(result.candidates, copied, result.receipt)
    copied.clear()
    assert len(rebuilt.files) == 4


def test_aggregate_receipt_does_not_authenticate_issuers_reprove_joins_or_admit_eligibility():
    choice, manifest = _fixture()
    result = _decode(choice, manifest)
    receipt = asdict(result.receipt)
    assert receipt["choices_sha256"] == "a" * 64
    assert receipt["files_manifest_sha256"] == "b" * 64
    assert receipt["issuer_authentication"] is False
    assert receipt["eligibility_admitted"] is False
    assert receipt["measurement_bytes_reverified"] is False
    assert receipt["metadata_candidate_not_admitted"] is True
    rendered = json.dumps(receipt)
    for candidate in result.candidates:
        for private in (
            candidate.case_submitter_id,
            candidate.sample_submitter_id,
            candidate.gdc_sample_uuid,
            candidate.protein_aliquot_submitter_id,
            candidate.protein_aliquot_uuid,
            candidate.rna_file_id,
            candidate.cnv_file_id,
        ):
            assert private not in rendered
    assert "not GDC/PDC issuer authenticity" in rendered
    assert "does not re-prove official ancestry" in rendered


@pytest.mark.parametrize(
    "field",
    [
        "case_submitter_id",
        "sample_submitter_id",
        "GDC_sample_uuid",
        "PDC_protein_aliquot_submitter_id",
        "PDC_protein_aliquot_uuid",
        "RNA_file_id",
        "gene_CNV_file_id",
    ],
)
def test_each_candidate_and_referenced_file_identity_must_be_unique(field):
    choice, manifest = _fixture()
    rows = choice["sample_map_matched_candidate_rows"]
    rows[1][field] = rows[0][field]
    with pytest.raises(plan.AdmissionPlanError):
        _decode(choice, manifest)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("exact_once_in_sample_map", False),
        ("exact_once_in_sample_map", 1),
        ("metadata_candidate_not_admitted", False),
        ("metadata_candidate_not_admitted", 1),
        ("GDC_sample_uuid", "NOT-AN-EXACT-UUID"),
        ("GDC_sample_uuid", _uuid(2000).upper().replace("0000", "ABCD", 1)),
        ("RNA_file_id", _uuid(999999)),
        ("RNA_file_id", _uuid(1001)),
        ("case_submitter_id", ""),
        ("sample_submitter_id", " padded "),
        ("PDC_protein_aliquot_submitter_id", "unsafe\nvalue"),
    ],
)
def test_candidate_assertions_and_exact_file_roles_fail_closed(field, value):
    choice, manifest = _fixture()
    choice["sample_map_matched_candidate_rows"][0][field] = value
    with pytest.raises(plan.AdmissionPlanError):
        _decode(choice, manifest)


@pytest.mark.parametrize(
    "mutation", ["reference", "multiple", "shared", "bad_plex", "bool_plex", "unknown_channel"]
)
def test_single_nonreference_sample_map_occurrence_is_required(mutation):
    choice, manifest = _fixture()
    rows = choice["sample_map_matched_candidate_rows"]
    occurrence = rows[0]["sample_map_occurrences"][0]
    if mutation == "reference":
        occurrence["channel"] = "126C"
    elif mutation == "multiple":
        rows[0]["sample_map_occurrences"].append(copy.deepcopy(occurrence))
    elif mutation == "shared":
        rows[1]["sample_map_occurrences"] = copy.deepcopy(rows[0]["sample_map_occurrences"])
    elif mutation == "bad_plex":
        occurrence["plex_index"] = 15
    elif mutation == "bool_plex":
        occurrence["plex_index"] = True
    else:
        occurrence["channel"] = "unmapped"
    with pytest.raises(plan.AdmissionPlanError):
        _decode(choice, manifest)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "admitted"),
        ("measurement_downloaded", True),
        ("candidate_count", True),
        ("candidate_count", 3),
        ("withheld_count_absent_from_map", -1),
    ],
)
def test_choices_remain_metadata_only_with_exact_counts(field, value):
    choice, manifest = _fixture()
    choice[field] = value
    with pytest.raises(plan.AdmissionPlanError):
        _decode(choice, manifest)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema", "different"),
        ("source_plan_sha256", "c" * 64),
        ("model_fits", True),
        ("redistribution_status", "public"),
        ("failures", [{}]),
        ("selected_specimens", 1),
        ("requested_files", 5),
        ("official_size_and_md5_verified_files", 3),
        ("verified_bytes", 1),
        ("requested_files", True),
    ],
)
def test_download_manifest_must_bind_exact_choices_and_complete_unmodified_inventory(field, value):
    choice, manifest = _fixture()
    manifest[field] = value
    with pytest.raises(plan.AdmissionPlanError):
        _decode(choice, manifest)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("access", "controlled"),
        ("assay", "RNA-ish"),
        ("workflow", "OTHER"),
        ("file_size", 0),
        ("file_size", True),
        ("md5sum", "A" * 32),
        ("file_name", "unsafe\x00name"),
    ],
)
def test_file_choices_require_open_expected_assay_workflow_and_canonical_lock(field, value):
    choice, manifest = _fixture()
    choice["GDC_candidate_file_choices"][0][field] = value
    with pytest.raises(plan.AdmissionPlanError):
        _decode(choice, manifest)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("official_size_and_md5_verified", False),
        ("official_size_and_md5_verified", 1),
        ("workflow", "AscatNGS"),
        ("bytes", len(_PAYLOAD) + 1),
        ("bytes", float(len(_PAYLOAD))),
        ("md5", "0" * 32),
        ("sha256", "A" * 64),
        ("file_id", _uuid(99999)),
    ],
)
def test_manifest_file_must_match_metadata_size_md5_workflow_and_unique_id(field, value):
    choice, manifest = _fixture()
    manifest["files"][0][field] = value
    with pytest.raises(plan.AdmissionPlanError):
        _decode(choice, manifest)


@pytest.mark.parametrize(
    "relative",
    [
        "../x.bin",
        "..\\x.bin",
        "/x.bin",
        "C:\\x.bin",
        "https://source/x.bin",
        "x.bin",
        _uuid(1000) + ".bin.bak",
        _uuid(1000) + "/.bin",
    ],
)
def test_relative_paths_are_exact_uuid_bin_basenames_without_traversal_or_roots(relative):
    choice, manifest = _fixture()
    manifest["files"][0]["relative_path"] = relative
    with pytest.raises(plan.AdmissionPlanError):
        _decode(choice, manifest)


@pytest.mark.parametrize(
    "inventory",
    [
        "choice_duplicate",
        "download_duplicate",
        "extra_choice",
        "extra_download",
        "missing_candidate",
        "extra_key",
    ],
)
def test_inventory_duplicates_extras_missing_rows_and_unrecognized_metadata_fail(inventory):
    choice, manifest = _fixture()
    if inventory == "choice_duplicate":
        choice["GDC_candidate_file_choices"][1] = copy.deepcopy(
            choice["GDC_candidate_file_choices"][0]
        )
    elif inventory == "download_duplicate":
        manifest["files"][1] = copy.deepcopy(manifest["files"][0])
    elif inventory == "extra_choice":
        choice["GDC_candidate_file_choices"].append(
            copy.deepcopy(choice["GDC_candidate_file_choices"][0])
        )
    elif inventory == "extra_download":
        manifest["files"].append(copy.deepcopy(manifest["files"][0]))
    elif inventory == "missing_candidate":
        choice["sample_map_matched_candidate_rows"].pop()
    else:
        choice["unfrozen_field"] = True
    with pytest.raises(plan.AdmissionPlanError):
        _decode(choice, manifest)


@pytest.mark.parametrize(
    "mutation",
    ["duplicate", "category", "file_type", "study", "study_uuid", "size", "md5", "known_lock"],
)
def test_pdc_source_inventory_preserves_fixed_protein_sample_map_locks(mutation):
    choice, manifest = _fixture()
    rows = choice["PDC_candidate_source_files"]
    if mutation == "duplicate":
        rows[1]["file_id"] = rows[0]["file_id"]
    elif mutation == "category":
        rows[0]["data_category"] = "OTHER"
    elif mutation == "file_type":
        rows[0]["file_type"] = "OTHER"
    elif mutation == "study":
        rows[0]["pdc_study_id"] = "OTHER"
    elif mutation == "study_uuid":
        rows[0]["study_id"] = _uuid(5001)
    elif mutation == "size":
        rows[0]["file_size"] = "01"
    elif mutation == "md5":
        rows[0]["md5sum"] = "g" * 32
    else:
        rows[0]["md5sum"] = "0" * 32
    with pytest.raises(plan.AdmissionPlanError):
        _decode(choice, manifest)


@pytest.mark.parametrize("value", ["a" * 63, "A" * 64, "sha256:" + "a" * 64, None])
def test_caller_digest_validation_precedes_reading_paths(tmp_path, value):
    with pytest.raises(plan.AdmissionPlanError, match="raw lowercase SHA-256"):
        plan.load_admission_plan(
            choices_path=tmp_path / "absent",
            choices_sha256=value,
            files_manifest_path=tmp_path / "absent-too",
            files_manifest_sha256="b" * 64,
        )


@pytest.mark.parametrize(
    "payload",
    [
        b'{"x":1,"x":2}',
        b'{"nested":{"x":1,"x":2}}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":-Infinity}',
        b'{"x":1e9999}',
        b'{"x":1.5}',
        b'{"x":"escaped\\ncontrol"}',
        b'{"escaped\\tkey":1}',
        b'{"x":"\\u0085"}',
        b'{"x":"\\u202e"}',
        b"\xff",
        b"\xef\xbb\xbf{}",
        b'{"unterminated',
        b"[" * 40 + b"]" * 40,
    ],
)
def test_json_rejects_duplicate_keys_nonfinite_numbers_controls_bad_utf8_or_nesting(
    tmp_path, payload
):
    path = tmp_path / "private-source-name.json"
    path.write_bytes(payload)
    with pytest.raises(plan.AdmissionPlanError) as caught:
        plan._read_json(path, _digest(payload))
    assert path.name not in str(caught.value)
    assert "escaped" not in str(caught.value)
    assert "unterminated" not in str(caught.value)


def test_json_checksum_is_checked_before_malformed_content_is_decoded(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b"\xff")
    with pytest.raises(plan.AdmissionPlanError, match="checksum"):
        plan._read_json(path, "0" * 64)


def test_json_exact_maximum_is_accepted_and_oversize_rejected_before_open(tmp_path, monkeypatch):
    path = tmp_path / "boundary.json"
    payload = b"{}" + b" " * (plan.MAX_PLAN_BYTES - 2)
    path.write_bytes(payload)
    assert plan._read_json(path, _digest(payload)) == {}
    path.write_bytes(payload + b" ")

    def forbidden_open(*_args, **_kwargs):
        pytest.fail("oversize JSON must be rejected before opening")

    monkeypatch.setattr(plan.os, "open", forbidden_open)
    with pytest.raises(plan.AdmissionPlanError, match="bounded JSON size"):
        plan._read_json(path, "0" * 64)


def test_json_read_path_replacement_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / "original.json"
    swapped = tmp_path / "replacement.json"
    path.write_bytes(b"{}")
    swapped.write_bytes(b"{}")
    original_open = plan.os.open
    monkeypatch.setattr(plan.os, "open", lambda _path, flags: original_open(swapped, flags))
    with pytest.raises(plan.AdmissionPlanError, match="binding changed"):
        plan._read_json(path, _digest(b"{}"))


def test_single_json_read_detects_in_read_metadata_change_and_closes_descriptor(
    tmp_path, monkeypatch
):
    path = tmp_path / "fixture.json"
    payload = b'{"fixture":1}'
    path.write_bytes(payload)
    before = path.stat()
    original_fdopen = plan.os.fdopen
    observations = []

    class ChangedRead:
        def __init__(self, stream):
            self.stream = stream
            self.requests = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.stream.close()

        def fileno(self):
            return self.stream.fileno()

        def read(self, count):
            self.requests.append(count)
            result = self.stream.read(count)
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000))
            return result

    def opened(descriptor, mode):
        observer = ChangedRead(original_fdopen(descriptor, mode))
        observations.append(observer)
        return observer

    monkeypatch.setattr(plan.os, "fdopen", opened)
    with pytest.raises(plan.AdmissionPlanError, match="binding changed"):
        plan._read_json(path, _digest(payload))
    assert len(observations) == 1
    assert observations[0].requests == [plan.MAX_PLAN_BYTES + 1]
    assert observations[0].stream.closed


def test_fixed_public_plan_success_validates_all_files_but_does_not_claim_measurement_rehash(
    tmp_path,
):
    arguments = _write_public(tmp_path)
    result = plan.load_admission_plan(**arguments)
    assert len(result.candidates) == 56
    assert len(result.files) == 112
    assert result.receipt.paired_file_count == 112
    assert result.receipt.measurement_bytes_reverified is False
    binding = next(iter(result.files.values()))
    file_path = tmp_path / binding.relative_path
    file_path.write_bytes(b"x" * len(_PAYLOAD))
    assert plan.load_admission_plan(**arguments).receipt.candidate_count == 56
    with pytest.raises(SourceVerificationError, match="checksums"):
        read_verified_source(file_path, binding.lock, max_bytes=10_000_000)


def test_public_loader_rejects_small_fixture_no_caller_configurable_cohort_bypass(tmp_path):
    with pytest.raises(plan.AdmissionPlanError):
        plan.load_admission_plan(**_write_public(tmp_path, count=2))


@pytest.mark.parametrize("mutation", ["missing", "wrong_size", "symlink"])
def test_public_loader_rejects_unavailable_wrong_size_or_linked_local_assay(tmp_path, mutation):
    arguments = _write_public(tmp_path)
    manifest = json.loads(arguments["files_manifest_path"].read_bytes())
    path = tmp_path / manifest["files"][0]["relative_path"]
    if mutation == "missing":
        path.unlink()
    elif mutation == "wrong_size":
        path.write_bytes(_PAYLOAD + b"!")
    else:
        target = tmp_path / "target.bin"
        target.write_bytes(_PAYLOAD)
        path.unlink()
        path.symlink_to(target)
    with pytest.raises(plan.AdmissionPlanError) as caught:
        plan.load_admission_plan(**arguments)
    assert path.name not in str(caught.value)
    assert str(tmp_path) not in str(caught.value)


def test_json_source_link_is_rejected_before_payload_read(tmp_path):
    path = tmp_path / "source.json"
    path.write_bytes(b"{}")
    linked = tmp_path / "linked.json"
    linked.symlink_to(path)
    with pytest.raises(plan.AdmissionPlanError, match="regular non-link"):
        plan._read_json(linked, _digest(b"{}"))


def test_read_errors_are_sanitized_and_original_paths_suppressed(tmp_path):
    path = tmp_path / "private-name-not-to-echo"
    with pytest.raises(plan.AdmissionPlanError) as caught:
        plan._read_json(path, "a" * 64)
    assert path.name not in str(caught.value)
    assert caught.value.__suppress_context__
