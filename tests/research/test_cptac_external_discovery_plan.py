"""Synthetic exact hierarchy, source-channel, and cohort-separation oracles."""

from __future__ import annotations

import copy
import hashlib
import json
import pickle
from dataclasses import asdict, replace
from uuid import UUID

import pytest

from glio_proteogen.research.cptac_gbm_external_admission import cohort_plan as engine
from glio_proteogen.research.cptac_gbm_external_admission.plan import (
    AdmissionPlanError,
    ExternalAdmissionPlan,
)

_PAYLOAD = b"synthetic locked native assay"


def _uuid(number):
    return str(UUID(int=number))


def _sample(index, case_id, *, workflow, normal=False):
    aliquot_id = _uuid(60_000 + index * 10 + (2 if normal else workflow == "AscatNGS"))
    aliquot_label = f"fixture-{workflow}-aliquot-{index}-{normal}"
    sample = {
        "sample_id": _uuid(50_000 + index * 10 + int(normal)),
        "submitter_id": f"fixture-{'normal' if normal else 'sample'}-{index:03}",
        "sample_type": "Blood Derived Normal" if normal else "Primary Tumor",
        "tissue_type": "Normal" if normal else "Tumor",
        "portions": [
            {
                "portion_id": _uuid(1_000_000 + index * 10 + int(normal)),
                "analytes": [
                    {
                        "analyte_id": _uuid(2_000_000 + index * 10 + int(normal)),
                        "aliquots": [{"aliquot_id": aliquot_id, "submitter_id": aliquot_label}],
                    }
                ],
            }
        ],
    }
    entity = {
        "case_id": case_id,
        "entity_id": aliquot_id,
        "entity_type": "aliquot",
        "entity_submitter_id": aliquot_label,
    }
    return sample, entity


def _fixture(count=2, offset=0):
    candidates, files, downloaded = [], [], []
    for i in range(count):
        index = i + offset
        case_id = _uuid(40_000 + index)
        pdc = {
            "case_id": _uuid(10_000 + index),
            "case_submitter_id": f"fixture-case-{index:03}",
            "case_status": "Qualified",
            "sample_id": _uuid(20_000 + index),
            "sample_submitter_id": f"fixture-sample-{index:03}",
            "sample_status": "Qualified",
            "sample_type": "Primary Tumor",
            "pool": "No",
            "aliquot_id": _uuid(30_000 + index),
            "aliquot_submitter_id": f"exact-unrelated-protein-label-{index:03}",
            "aliquot_status": "Qualified",
        }
        row = {
            "pdc": pdc,
            "gdc_sample_uuid": _uuid(50_000 + index * 10),
            "metadata_candidate_not_admitted": True,
        }
        for key, workflow in (("rna_file", "STAR - Counts"), ("cnv_file", "AscatNGS")):
            sample, entity = _sample(index, case_id, workflow=workflow)
            normal, normal_entity = _sample(index, case_id, workflow=workflow, normal=True)
            file_id = _uuid(100_000 + index * 2 + int(workflow == "AscatNGS"))
            file = {
                "file_id": file_id,
                "id": file_id,
                "file_name": "uninformative.txt",
                "file_size": len(_PAYLOAD),
                "md5sum": hashlib.md5(_PAYLOAD, usedforsecurity=False).hexdigest(),
                "access": "open",
                "state": "released",
                "data_format": "TSV",
                "data_type": "Gene Expression Quantification"
                if key == "rna_file"
                else "Gene Level Copy Number",
                "analysis": {"workflow_type": workflow},
                "associated_entities": [entity] + ([normal_entity] if key == "cnv_file" else []),
                "cases": [
                    {
                        "case_id": case_id,
                        "submitter_id": pdc["case_submitter_id"],
                        "samples": [sample, normal],
                    }
                ],
            }
            row[key] = file
            files.append(copy.deepcopy(file))
            downloaded.append(
                {
                    "file_id": file_id,
                    "bytes": len(_PAYLOAD),
                    "md5": file["md5sum"],
                    "sha256": hashlib.sha256(_PAYLOAD).hexdigest(),
                    "relative_path": file_id + ".bin",
                    "workflow": workflow,
                    "official_size_and_md5_verified": True,
                    "source_kind": "gdc",
                    "cached_verified": False,
                }
            )
        candidates.append(row)
    choices = {
        "schema": "discovery-paired-source-metadata/1.0.0",
        "source_candidates_sha256": "c" * 64,
        "source_integrity_manifest_sha256": "d" * 64,
        "metadata_only": True,
        "measurement_admitted": False,
        "candidate_count": count,
        "file_count": 2 * count,
        "candidates": candidates,
        "GDC_paired_official_file_choices": files,
    }
    labels = [row["pdc"]["aliquot_submitter_id"] for row in candidates] + [
        f"fixture-unused-map-label-{i}" for i in range(110 - count)
    ]
    map_rows = [
        {
            "plex_index": i,
            "source_row": [
                f"fixture-regex-{i}",
                f"fixture-plex-{i}",
                "POOL",
                *labels[i * 10 : (i + 1) * 10],
                "TMT11",
                engine._RATIOS,
            ],
        }
        for i in range(11)
    ]
    matched = [
        {
            "candidate": copy.deepcopy(row),
            "exact_once_in_nonreference_sample_map": True,
            "sample_map_occurrences": [
                {"plex_index": i // 10, "channel": engine._CHANNELS[1:][i % 10]}
            ],
            "metadata_candidate_not_admitted": True,
        }
        for i, row in enumerate(candidates)
    ]
    mapped = {
        "schema": "discovery-exact-tmt-channel-map-bindings/1.0.0",
        "source_candidate_bindings_sha256": "a" * 64,
        "source_map_sha256": engine.MAP_SHA256,
        "source_map_md5": engine.MAP_MD5,
        "qualified_metadata_candidates_before_map": count,
        "candidate_bindings": matched,
        "withheld": [],
        "parsed_map_rows": map_rows,
        "reference_assignments_excluded": [
            {"plex_index": i, "channel": "126C", "label": "POOL"} for i in range(11)
        ],
        "measurement_admitted": False,
    }
    manifest = {
        "schema": "frozen-discovery-GDC-downloads/1.0.0",
        "source_plan_sha256": "a" * 64,
        "source_channel_bindings_sha256": "b" * 64,
        "selected_specimens": count,
        "requested_files": 2 * count,
        "official_size_and_md5_verified_files": 2 * count,
        "verified_bytes": len(_PAYLOAD) * 2 * count,
        "files": downloaded,
        "failures": [],
        "model_fits": False,
        "redistribution_status": "local_only_terms_unverified",
    }
    return choices, mapped, manifest


def _decode(choices, mapped, manifest, count=2):
    return engine._decode_discovery_plan(
        choices,
        mapped,
        manifest,
        choices_sha256="a" * 64,
        map_bindings_sha256="b" * 64,
        files_manifest_sha256="e" * 64,
        candidate_count=count,
    )


def _sync(choices, mapped):
    choices["GDC_paired_official_file_choices"] = [
        copy.deepcopy(row[key]) for row in choices["candidates"] for key in ("rna_file", "cnv_file")
    ]
    for bound, original in zip(mapped["candidate_bindings"], choices["candidates"], strict=True):
        bound["candidate"] = copy.deepcopy(original)


def _trace(file, index=0):
    return engine._associated_primary_sample(
        file,
        case_label=f"fixture-case-{index:03}",
        sample_label=f"fixture-sample-{index:03}",
        sample_uuid=_uuid(50_000 + index * 10),
    )


def _write_public(tmp_path, count=72):
    choices, mapped, manifest = _fixture(count)

    def save(name, value):
        payload = json.dumps(value, allow_nan=False).encode()
        path = tmp_path / name
        path.write_bytes(payload)
        return path, hashlib.sha256(payload).hexdigest()

    cp, cs = save("choices.private.json", choices)
    mapped["source_candidate_bindings_sha256"] = cs
    mp, ms = save("map.private.json", mapped)
    manifest["source_plan_sha256"] = cs
    manifest["source_channel_bindings_sha256"] = ms
    fp, fs = save("files.private.json", manifest)
    for file in manifest["files"]:
        (tmp_path / file["relative_path"]).write_bytes(_PAYLOAD)
    return {
        "choices_path": cp,
        "choices_sha256": cs,
        "map_bindings_path": mp,
        "map_bindings_sha256": ms,
        "files_manifest_path": fp,
        "files_manifest_sha256": fs,
    }


def test_exact_metadata_and_paired_normal_provenance_do_not_conflate_omics_aliquots():
    choices, mapped, manifest = _fixture()
    result = _decode(choices, mapped, manifest)
    assert len(result.candidates) == 2 and len(result.files) == 4
    assert (
        result.candidates[0].protein_aliquot_uuid
        != choices["candidates"][0]["rna_file"]["associated_entities"][0]["entity_id"]
    )
    assert result.protein_aliquots == (
        "exact-unrelated-protein-label-000",
        "exact-unrelated-protein-label-001",
    )
    assert result.receipt.profile_id == engine.PROFILE_ID
    assert not result.receipt.issuer_authentication
    assert not result.receipt.eligibility_admitted
    assert not result.receipt.measurement_bytes_reverified
    assert "fixture-case" not in json.dumps(asdict(result.receipt))
    with pytest.raises(TypeError):
        result.files["untracked"] = next(iter(result.files.values()))
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(result)


def test_case_broad_unassociated_tumor_does_not_create_false_aliquot_ambiguity():
    file = _fixture()[0]["candidates"][0]["rna_file"]
    unrelated, _ = _sample(100, file["cases"][0]["case_id"], workflow="STAR - Counts")
    file["cases"][0]["samples"].append(unrelated)
    assert _trace(file) == _uuid(40_000)


@pytest.mark.parametrize("ambiguity", ["second_sample", "second_portion"])
def test_official_associated_aliquot_requires_unique_full_ancestry(ambiguity):
    file = _fixture()[0]["candidates"][0]["rna_file"]
    samples = file["cases"][0]["samples"]
    if ambiguity == "second_sample":
        duplicate = copy.deepcopy(samples[0])
        duplicate["sample_id"] = _uuid(999_000)
        duplicate["submitter_id"] = "another-exact-sample"
        samples.append(duplicate)
    else:
        duplicate = copy.deepcopy(samples[0]["portions"][0])
        duplicate["portion_id"] = _uuid(999_000)
        samples[0]["portions"].append(duplicate)
    with pytest.raises(AdmissionPlanError):
        _trace(file)


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_aliquot",
        "wrong_case",
        "wrong_submitter",
        "not_aliquot",
        "duplicate_entity",
        "no_entity",
        "no_ancestry",
    ],
)
def test_associated_entities_need_exact_official_lineage_and_roles(mutation):
    file = _fixture()[0]["candidates"][0]["rna_file"]
    entity = file["associated_entities"][0]
    if mutation == "unknown_aliquot":
        entity["entity_id"] = _uuid(999_000)
    elif mutation == "wrong_case":
        entity["case_id"] = _uuid(999_000)
    elif mutation == "wrong_submitter":
        entity["entity_submitter_id"] = "prefix-is-not-an-exact-match"
    elif mutation == "not_aliquot":
        entity["entity_type"] = "sample"
    elif mutation == "duplicate_entity":
        file["associated_entities"].append(copy.deepcopy(entity))
    elif mutation == "no_entity":
        file["associated_entities"] = []
    else:
        file["cases"][0]["samples"][0]["portions"] = []
    with pytest.raises(AdmissionPlanError):
        _trace(file)


@pytest.mark.parametrize(
    "mutation",
    [
        "two_tumors",
        "unknown_normal",
        "normal_tissue_disagrees",
        "different_case",
        "normal_added_to_rna",
        "no_tumor",
        "tumor_tissue_disagrees",
    ],
)
def test_paired_analysis_accepts_only_one_exact_tumor_and_explicit_same_case_normal(mutation):
    file = _fixture()[0]["candidates"][0]["cnv_file"]
    tumor, normal = file["cases"][0]["samples"]
    if mutation == "two_tumors":
        normal["sample_type"] = "Primary Tumor"
        normal["tissue_type"] = "Tumor"
    elif mutation == "unknown_normal":
        normal["sample_type"] = "Not Reported"
    elif mutation == "normal_tissue_disagrees":
        normal["tissue_type"] = "Tumor"
    elif mutation == "different_case":
        second = {
            "case_id": _uuid(999_000),
            "submitter_id": file["cases"][0]["submitter_id"],
            "samples": [normal],
        }
        file["cases"][0]["samples"].pop()
        file["cases"].append(second)
        file["associated_entities"][1]["case_id"] = second["case_id"]
    elif mutation == "normal_added_to_rna":
        file["analysis"]["workflow_type"] = "STAR - Counts"
    elif mutation == "no_tumor":
        tumor["sample_type"] = "Solid Tissue Normal"
        tumor["tissue_type"] = "Normal"
    else:
        tumor["tissue_type"] = "Normal"
    with pytest.raises(AdmissionPlanError):
        _trace(file)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("case_status", "Disqualified"),
        ("sample_status", "Disqualified"),
        ("aliquot_status", "Disqualified"),
        ("pool", "Yes"),
        ("sample_type", "Solid Tissue Normal"),
        ("case_submitter_id", "other-case"),
        ("sample_submitter_id", "sample-prefix-is-not-exact"),
    ],
)
def test_qualified_nonpool_primary_tumor_and_exact_case_sample_assertions_are_required(
    field, value
):
    choices, mapped, manifest = _fixture()
    choices["candidates"][0]["pdc"][field] = value
    _sync(choices, mapped)
    with pytest.raises(AdmissionPlanError):
        _decode(choices, mapped, manifest)


@pytest.mark.parametrize("field", ["case_id", "sample_id", "aliquot_id", "aliquot_submitter_id"])
def test_pdc_source_uuid_and_aliquot_namespace_collisions_fail_closed(field):
    choices, mapped, manifest = _fixture()
    rows = choices["candidates"]
    rows[1]["pdc"][field] = rows[0]["pdc"][field]
    _sync(choices, mapped)
    with pytest.raises(AdmissionPlanError):
        _decode(choices, mapped, manifest)


def test_shared_gdc_case_uuid_cannot_hide_behind_different_submitter_labels():
    choices, mapped, manifest = _fixture()
    case_id = choices["candidates"][0]["rna_file"]["cases"][0]["case_id"]
    for key in ("rna_file", "cnv_file"):
        f = choices["candidates"][1][key]
        f["cases"][0]["case_id"] = case_id
        for entity in f["associated_entities"]:
            entity["case_id"] = case_id
    _sync(choices, mapped)
    with pytest.raises(AdmissionPlanError):
        _decode(choices, mapped, manifest)


def test_rna_and_cnv_must_have_the_same_official_case_uuid_not_only_its_label():
    choices, mapped, manifest = _fixture()
    file = choices["candidates"][0]["cnv_file"]
    file["cases"][0]["case_id"] = _uuid(999_000)
    for entity in file["associated_entities"]:
        entity["case_id"] = _uuid(999_000)
    _sync(choices, mapped)
    with pytest.raises(AdmissionPlanError):
        _decode(choices, mapped, manifest)


@pytest.mark.parametrize("mutation", ["missing_workflow", "nonlist_cases", "too_many_samples"])
def test_malformed_or_unbounded_nested_metadata_is_rejected(mutation):
    choices, mapped, manifest = _fixture()
    file = choices["candidates"][0]["rna_file"]
    if mutation == "missing_workflow":
        file["analysis"] = {}
    elif mutation == "nonlist_cases":
        file["cases"] = None
    else:
        file["cases"][0]["samples"] = [{}] * 2_001
    _sync(choices, mapped)
    with pytest.raises(AdmissionPlanError):
        _decode(choices, mapped, manifest)


@pytest.mark.parametrize("inventory", ["choices", "manifest"])
def test_duplicate_official_file_ids_cannot_replace_another_required_assay(inventory):
    choices, mapped, manifest = _fixture()
    records = (
        choices["GDC_paired_official_file_choices"] if inventory == "choices" else manifest["files"]
    )
    records[1] = copy.deepcopy(records[0])
    with pytest.raises(AdmissionPlanError):
        _decode(choices, mapped, manifest)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("access", "controlled"),
        ("state", "submitted"),
        ("data_format", "CSV"),
        ("data_type", "Copy Number Segment"),
        ("file_size", True),
        ("file_size", 0),
        ("md5sum", "A" * 32),
        ("id", _uuid(999_000)),
    ],
)
def test_file_metadata_requires_expected_open_native_assay_and_canonical_locks(field, value):
    choices, mapped, manifest = _fixture()
    choices["candidates"][0]["rna_file"][field] = value
    _sync(choices, mapped)
    with pytest.raises(AdmissionPlanError):
        _decode(choices, mapped, manifest)


def test_rich_candidate_file_record_must_match_the_frozen_official_choices_copy():
    choices, mapped, manifest = _fixture()
    choices["candidates"][0]["rna_file"]["file_name"] = "another-name.txt"
    with pytest.raises(AdmissionPlanError):
        _decode(choices, mapped, manifest)


@pytest.mark.parametrize(
    "mutation",
    [
        "source_digest",
        "map_digest",
        "map_md5",
        "source_count",
        "admitted",
        "withheld",
        "duplicate_bound",
        "wrong_candidate",
        "wrong_channel",
        "multiple_occurrences",
        "false_once",
        "false_metadata",
        "duplicate_map_label",
        "reference_channel",
        "reference_label",
        "duplicate_plex",
        "ragged_row",
        "wrong_ratio",
        "duplicate_analytical",
    ],
)
def test_exact_channel_map_and_immutable_source_binding_are_revalidated(mutation):  # noqa: C901, PLR0912 - explicit source-corruption fixture matrix.
    choices, mapped, manifest = _fixture()
    if mutation == "source_digest":
        mapped["source_candidate_bindings_sha256"] = "c" * 64
    elif mutation == "map_digest":
        mapped["source_map_sha256"] = "c" * 64
    elif mutation == "map_md5":
        mapped["source_map_md5"] = "c" * 32
    elif mutation == "source_count":
        mapped["qualified_metadata_candidates_before_map"] = 3
    elif mutation == "admitted":
        mapped["measurement_admitted"] = True
    elif mutation == "withheld":
        mapped["withheld"] = [{}]
    elif mutation == "duplicate_bound":
        mapped["candidate_bindings"][1] = copy.deepcopy(mapped["candidate_bindings"][0])
    elif mutation == "wrong_candidate":
        mapped["candidate_bindings"][0]["candidate"]["pdc"]["case_status"] = "Disqualified"
    elif mutation == "wrong_channel":
        mapped["candidate_bindings"][0]["sample_map_occurrences"][0]["channel"] = "126C"
    elif mutation == "multiple_occurrences":
        mapped["candidate_bindings"][0]["sample_map_occurrences"] *= 2
    elif mutation == "false_once":
        mapped["candidate_bindings"][0]["exact_once_in_nonreference_sample_map"] = False
    elif mutation == "false_metadata":
        mapped["candidate_bindings"][0]["metadata_candidate_not_admitted"] = False
    elif mutation == "duplicate_map_label":
        mapped["parsed_map_rows"][0]["source_row"][4] = mapped["parsed_map_rows"][0]["source_row"][
            3
        ]
    elif mutation == "reference_channel":
        mapped["reference_assignments_excluded"][0]["channel"] = "127N"
    elif mutation == "reference_label":
        mapped["reference_assignments_excluded"][0]["label"] = "individual-not-pool"
    elif mutation == "duplicate_plex":
        mapped["parsed_map_rows"][1]["plex_index"] = 0
    elif mutation == "ragged_row":
        mapped["parsed_map_rows"][0]["source_row"].pop()
    elif mutation == "wrong_ratio":
        mapped["parsed_map_rows"][0]["source_row"][-1] = "127N/131C"
    else:
        mapped["parsed_map_rows"][1]["source_row"][1] = mapped["parsed_map_rows"][0]["source_row"][
            1
        ]
    with pytest.raises(AdmissionPlanError):
        _decode(choices, mapped, manifest)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema", "other"),
        ("source_plan_sha256", "c" * 64),
        ("source_channel_bindings_sha256", "c" * 64),
        ("selected_specimens", True),
        ("requested_files", 3),
        ("official_size_and_md5_verified_files", 3),
        ("verified_bytes", 1),
        ("failures", [{}]),
        ("model_fits", True),
        ("redistribution_status", "public"),
    ],
)
def test_manifest_requires_both_frozen_inputs_complete_inventory_and_no_model_claim(field, value):
    choices, mapped, manifest = _fixture()
    manifest[field] = value
    with pytest.raises(AdmissionPlanError):
        _decode(choices, mapped, manifest)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("relative_path", "../other.bin"),
        ("relative_path", "C:\\other.bin"),
        ("bytes", len(_PAYLOAD) + 1),
        ("md5", "0" * 32),
        ("sha256", "A" * 64),
        ("workflow", "AscatNGS"),
        ("official_size_and_md5_verified", 1),
        ("source_kind", "protein"),
        ("cached_verified", "yes"),
    ],
)
def test_file_manifest_cannot_change_safe_path_or_official_assay_lock(field, value):
    choices, mapped, manifest = _fixture()
    manifest["files"][0][field] = value
    with pytest.raises(AdmissionPlanError):
        _decode(choices, mapped, manifest)


def test_public_fixed72_loader_binds_all_three_digests_and_orders_candidates(tmp_path):
    arguments = _write_public(tmp_path)
    result = engine.load_discovery_plan(**arguments)
    assert len(result.candidates) == 72 and len(result.files) == 144
    assert result.receipt.choices_sha256 == arguments["choices_sha256"]
    assert result.receipt.files_manifest_sha256 == arguments["files_manifest_sha256"]
    assert arguments["map_bindings_sha256"] in " ".join(result.receipt.limitations)
    assert [x.case_submitter_id for x in result.candidates] == sorted(
        x.case_submitter_id for x in result.candidates
    )


def test_public_loader_has_no_small_cohort_configuration_bypass(tmp_path):
    with pytest.raises(AdmissionPlanError):
        engine.load_discovery_plan(**_write_public(tmp_path, count=2))


@pytest.mark.parametrize("path_key", ["choices_path", "map_bindings_path", "files_manifest_path"])
def test_each_input_json_is_checksum_checked_before_use(tmp_path, path_key):
    arguments = _write_public(tmp_path)
    arguments[path_key].write_bytes(arguments[path_key].read_bytes() + b" ")
    with pytest.raises(AdmissionPlanError, match="checksum"):
        engine.load_discovery_plan(**arguments)


@pytest.mark.parametrize("mutation", ["missing", "size", "symlink"])
def test_public_local_file_binding_is_regular_nonlink_exact_size_without_echoing_ids(
    tmp_path, mutation
):
    arguments = _write_public(tmp_path)
    files = json.loads(arguments["files_manifest_path"].read_bytes())["files"]
    path = tmp_path / files[0]["relative_path"]
    if mutation == "missing":
        path.unlink()
    elif mutation == "size":
        path.write_bytes(b"x")
    else:
        target = tmp_path / "target.bin"
        target.write_bytes(_PAYLOAD)
        path.unlink()
        path.symlink_to(target)
    with pytest.raises(AdmissionPlanError) as caught:
        engine.load_discovery_plan(**arguments)
    assert path.name not in str(caught.value) and str(tmp_path) not in str(caught.value)


def test_distinct_plan_receipt_is_aggregate_and_explicit_about_identity_scope():
    train = _decode(*_fixture())
    test = _decode(*_fixture(offset=100))
    receipt = engine.assert_distinct_cohort_plans(train, test)
    assert receipt.training_candidates == receipt.test_candidates == 2
    assert not receipt.donor_independence_admitted
    assert len(receipt.checked_identifier_namespaces) == 6
    assert all(value == 0 for name, value in asdict(receipt).items() if name.endswith("overlaps"))
    assert "fixture-case" not in json.dumps(asdict(receipt))


@pytest.mark.parametrize(
    "field",
    [
        "case_submitter_id",
        "sample_submitter_id",
        "gdc_sample_uuid",
        "protein_aliquot_submitter_id",
        "protein_aliquot_uuid",
        "rna_file_id",
        "cnv_file_id",
    ],
)
def test_any_known_identity_overlap_rejects_separation_without_leaking_identifiers(field):
    train = _decode(*_fixture())
    test = _decode(*_fixture(offset=100))
    shared = getattr(train.candidates[0], "rna_file_id" if field == "cnv_file_id" else field)
    changed = replace(test.candidates[0], **{field: shared})
    test = ExternalAdmissionPlan((changed, test.candidates[1]), test.files, test.receipt)
    with pytest.raises(AdmissionPlanError, match="share exact") as caught:
        engine.assert_distinct_cohort_plans(train, test)
    assert shared not in str(caught.value)


def test_separation_rejects_nonplan_objects():
    with pytest.raises(AdmissionPlanError, match="plan contracts"):
        engine.assert_distinct_cohort_plans(object(), object())


def test_separation_also_checks_all_exposed_file_mapping_keys():
    train = _decode(*_fixture())
    test = _decode(*_fixture(offset=100))
    files = dict(test.files)
    files.update(train.files)
    changed = ExternalAdmissionPlan(test.candidates, files, test.receipt)
    with pytest.raises(AdmissionPlanError, match="share exact"):
        engine.assert_distinct_cohort_plans(train, changed)
