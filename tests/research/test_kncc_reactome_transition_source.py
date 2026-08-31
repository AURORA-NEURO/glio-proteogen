from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from glio_proteogen.research.longitudinal_gbm.catalog import longitudinal_gbm_catalog
from glio_proteogen.research.longitudinal_gbm_reactome_transition import catalog
from glio_proteogen.research.longitudinal_gbm_reactome_transition.errors import (
    ReactomeTransitionSourceIntegrityError,
)
from tools import import_kncc_longitudinal_gbm as base
from tools import import_kncc_reactome_transition_source as importer

ARTIFACT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "glio_proteogen"
    / "research"
    / "longitudinal_gbm_reactome_transition"
    / "data"
    / "kncc_reactome_transition_source.v1.json"
)
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
PDC_SOURCE_DIR = WORKSPACE_ROOT / ".tmp-longitudinal-gbm-source"
HGNC_SOURCE = WORKSPACE_ROOT / ".tmp-neftel-source" / "hgnc_complete_set.txt"
REACTOME_SOURCE_DIR = WORKSPACE_ROOT / ".tmp-reactome-v97"


def _document() -> dict[str, object]:
    return cast("dict[str, object]", json.loads(ARTIFACT.read_bytes()))


def _patch_artifact_file_locks(
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    *,
    content_digest: str | None = None,
) -> None:
    monkeypatch.setattr(catalog, "EXPECTED_ARTIFACT_BYTES", len(payload))
    monkeypatch.setattr(
        catalog,
        "EXPECTED_ARTIFACT_SHA256",
        "sha256:" + hashlib.sha256(payload).hexdigest(),
    )
    if content_digest is not None:
        monkeypatch.setattr(catalog, "EXPECTED_CONTENT_DIGEST", content_digest)
    monkeypatch.setattr(catalog, "_resource_bytes", lambda: payload)
    catalog.reactome_transition_source_catalog.cache_clear()


def _walk(value: object, path: str = "") -> list[tuple[str, object]]:
    result = [(path, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            result.extend(_walk(child, f"{path}.{key}" if path else str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.extend(_walk(child, f"{path}[{index}]"))
    return result


def test_catalog_exposes_exact_immutable_axes_and_panel() -> None:
    loaded = catalog.reactome_transition_source_catalog()
    parent = longitudinal_gbm_catalog()
    assert loaded.profile_id == "kncc-reactome-conditional-transition/1.0.0"
    assert loaded.patient_count == 104
    assert len(loaded.genes) == len(loaded.gene_index_by_symbol) == 11_312
    assert loaded.genes == tuple(feature.gene_symbol for feature in parent.features)
    assert tuple(
        (pathway.domain_id, pathway.reactome_id, pathway.name)
        for pathway in loaded.pathways
    ) == catalog.EXPECTED_PATHWAYS
    assert tuple(pathway.panel_index for pathway in loaded.pathways) == tuple(range(10))
    assert loaded.pathway_by_id["R-HSA-177929"].name == "Signaling by EGFR"
    assert loaded.pathway_by_domain["innate_immune_system"].reactome_id == "R-HSA-168249"
    with pytest.raises(TypeError):
        loaded.gene_index_by_symbol["FAKE"] = 0  # type: ignore[index]
    with pytest.raises(TypeError):
        loaded.pathway_by_id["FAKE"] = loaded.pathways[0]  # type: ignore[index]
    with pytest.raises(TypeError):
        loaded.provenance["fake"] = "value"  # type: ignore[index]


def test_pathway_membership_is_exactly_bound_to_parent_feature_axis() -> None:
    loaded = catalog.reactome_transition_source_catalog()
    parent = longitudinal_gbm_catalog()
    eligible = {feature.index for feature in parent.features if feature.eligible}
    expected_counts = {
        "R-HSA-177929": (53, 42, 40),
        "R-HSA-186797": (58, 57, 49),
        "R-HSA-198203": (9, 7, 7),
        "R-HSA-165159": (52, 50, 48),
        "R-HSA-5683057": (314, 231, 216),
        "R-HSA-1640170": (657, 540, 468),
        "R-HSA-73894": (346, 267, 238),
        "R-HSA-1234174": (62, 52, 49),
        "R-HSA-1474244": (321, 251, 221),
        "R-HSA-168249": (1_198, 871, 817),
    }
    for pathway in loaded.pathways:
        assert (
            pathway.source_member_count,
            pathway.mapped_feature_count,
            pathway.eligible_feature_count,
        ) == expected_counts[pathway.reactome_id]
        assert pathway.member_feature_indices == tuple(sorted(set(pathway.member_feature_indices)))
        assert pathway.eligible_feature_indices == tuple(
            index for index in pathway.member_feature_indices if index in eligible
        )
        symbols = tuple(loaded.genes[index] for index in pathway.member_feature_indices)
        assert len(symbols) == len(set(symbols)) == pathway.mapped_feature_count


def test_artifact_is_canonical_hard_pinned_compact_and_deidentified() -> None:
    payload = ARTIFACT.read_bytes()
    document = cast("dict[str, object]", json.loads(payload))
    assert len(payload) == catalog.EXPECTED_ARTIFACT_BYTES < 64 * 1024
    assert "sha256:" + hashlib.sha256(payload).hexdigest() == catalog.EXPECTED_ARTIFACT_SHA256
    assert importer._canonical_bytes(document) == payload
    content = dict(document)
    assert content.pop("artifact_digest") == catalog.EXPECTED_CONTENT_DIGEST
    assert importer._digest(content) == catalog.EXPECTED_CONTENT_DIGEST
    assert b"KNCC_GBM" not in payload
    assert b'"patient_groups"' not in payload

    digest_tokens = set(re.findall(rb"(?<![0-9a-f])[0-9a-f]{32,128}(?![0-9a-f])", payload.lower()))
    for number in range(10_000):
        patient = f"KNCC_GBM{number:04d}"
        for identifier in (patient, f"{patient}_T1", f"{patient}_T2"):
            assert identifier.encode() not in payload
            encoded = identifier.encode()
            candidates = {
                hashlib.md5(encoded, usedforsecurity=False).hexdigest().encode(),
                hashlib.sha1(encoded, usedforsecurity=False).hexdigest().encode(),
                hashlib.sha256(encoded).hexdigest().encode(),
                hashlib.sha512(encoded).hexdigest().encode(),
            }
            assert digest_tokens.isdisjoint(candidates)


def test_projection_digests_and_source_locks_are_independent_hard_pins() -> None:
    loaded = catalog.reactome_transition_source_catalog()
    assert loaded.content_digest == catalog.EXPECTED_CONTENT_DIGEST
    assert loaded.source_binding_digest == catalog.EXPECTED_SOURCE_BINDING_DIGEST
    assert loaded.selection_candidate_digest == catalog.EXPECTED_SELECTION_CANDIDATE_DIGEST
    assert loaded.pathway_order_digest == catalog.EXPECTED_PATHWAY_ORDER_DIGEST
    assert loaded.pathway_membership_digest == catalog.EXPECTED_PATHWAY_MEMBERSHIP_DIGEST
    assert loaded.gene_order_digest == catalog.EXPECTED_GENE_ORDER_DIGEST
    assert loaded.patient_order_rule_digest == catalog.EXPECTED_PATIENT_ORDER_RULE_DIGEST
    assert tuple(
        (item.relative_path, item.bytes, item.sha256) for item in loaded.reactome_files
    ) == catalog.EXPECTED_REACTOME_FILES


def test_panel_selection_is_pre_outcome_and_records_nonselections() -> None:
    loaded = catalog.reactome_transition_source_catalog()
    document = cast("dict[str, object]", json.loads(ARTIFACT.read_bytes()))
    selection = cast("dict[str, object]", document["selection"])
    assert selection["rule_id"] == "gbm-mechanism-slots-reactome-v97/1.0.0"
    assert "no patient transition value" in cast("str", selection["rule"])
    assert len(loaded.excluded_candidates) == 12
    by_id = {item.reactome_id: item for item in loaded.excluded_candidates}
    assert "epithelial" in by_id["R-HSA-2173791"].reason
    assert "post hoc" in by_id["R-HSA-109581"].reason
    forbidden_fit_terms = {"coefficient", "p_value", "q_value", "effect", "accuracy"}
    assert not any(
        any(term in path.casefold() for term in forbidden_fit_terms)
        for path, _ in _walk(document)
    )


def test_catalog_rejects_same_length_artifact_substitution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = ARTIFACT.read_bytes()
    tampered = payload.replace(b"R-HSA-177929", b"R-HSA-177928", 1)
    assert len(tampered) == len(payload) and tampered != payload
    catalog.reactome_transition_source_catalog.cache_clear()
    monkeypatch.setattr(catalog, "_resource_bytes", lambda: tampered)
    with pytest.raises(ReactomeTransitionSourceIntegrityError, match="byte digest"):
        catalog.reactome_transition_source_catalog()
    catalog.reactome_transition_source_catalog.cache_clear()


def test_catalog_scalar_and_top_level_guards_reject_wrong_types_and_roles() -> None:
    for operation in (
        lambda: catalog._object(None, "value"),
        lambda: catalog._list(None, "value"),
        lambda: catalog._integer(1.0, "value"),
        lambda: catalog._finite("1", "value"),
        lambda: catalog._finite(float("nan"), "value"),
    ):
        with pytest.raises(ReactomeTransitionSourceIntegrityError):
            operation()

    for key, replacement in (
        ("schema_version", "bad"),
        ("profile_id", "bad"),
        ("artifact_role", "fitted"),
        ("patient_axis", None),
        ("pathways", None),
    ):
        document = _document()
        document[key] = replacement
        with pytest.raises(ReactomeTransitionSourceIntegrityError):
            catalog._validate_top_level(document)


def test_catalog_projection_guards_reject_declared_and_self_consistent_forgery() -> None:
    document = _document()
    patient_axis, gene_axis, selection, bindings, pathways = catalog._validate_top_level(document)
    del patient_axis, gene_axis
    projection = cast("dict[str, object]", document["projection_digests"])
    projection["pathway_order_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ReactomeTransitionSourceIntegrityError, match="self-declared"):
        catalog._validate_projection_digests(document, selection, bindings, pathways)

    document = _document()
    _, _, selection, bindings, pathways = catalog._validate_top_level(document)
    pdc = cast("dict[str, object]", bindings["pdc000514"])
    pdc["study_id"] = "forged"
    projection = cast("dict[str, object]", document["projection_digests"])
    projection["source_binding_digest"] = catalog._digest(bindings)
    with pytest.raises(ReactomeTransitionSourceIntegrityError, match="locked projection"):
        catalog._validate_projection_digests(document, selection, bindings, pathways)


def test_catalog_source_binding_rejects_each_independent_lock_family() -> None:
    def reject(bindings: dict[str, object], message: str) -> None:
        with pytest.raises(ReactomeTransitionSourceIntegrityError, match=message):
            catalog._validate_parent_binding(bindings)

    bindings = cast("dict[str, object]", deepcopy(_document()["source_bindings"]))
    cast("dict[str, object]", bindings["pdc000514"])["study_id"] = "forged"
    reject(bindings, "parent PDC000514")
    bindings = cast("dict[str, object]", deepcopy(_document()["source_bindings"]))
    cast("dict[str, object]", bindings["reactome"])["declared_release"] = 98
    reject(bindings, "release binding")
    bindings = cast("dict[str, object]", deepcopy(_document()["source_bindings"]))
    cast("dict[str, object]", bindings["reactome"])["release_attestation"] = "forged"
    reject(bindings, "release binding")
    bindings = cast("dict[str, object]", deepcopy(_document()["source_bindings"]))
    files = cast(
        "list[dict[str, object]]",
        cast("dict[str, object]", bindings["reactome"])["files"],
    )
    files[0]["sha256"] = "sha256:" + "0" * 64
    reject(bindings, "source-file lock")


def test_catalog_selection_rejects_rule_gate_and_each_candidate_inventory_failure() -> None:
    def reject(selection: dict[str, object]) -> None:
        with pytest.raises(ReactomeTransitionSourceIntegrityError):
            catalog._validate_selection(selection)

    selection = cast("dict[str, object]", deepcopy(_document()["selection"]))
    selection["rule_id"] = "forged"
    reject(selection)
    selection = cast("dict[str, object]", deepcopy(_document()["selection"]))
    selection["rule"] = "outcome-selected"
    reject(selection)
    selection = cast("dict[str, object]", deepcopy(_document()["selection"]))
    cast("dict[str, object]", selection["assay_gate"])["minimum_mapped_genes"] = 1
    reject(selection)

    selection = cast("dict[str, object]", deepcopy(_document()["selection"]))
    cast("list[object]", selection["excluded_candidates"]).pop()
    reject(selection)
    selection = cast("dict[str, object]", deepcopy(_document()["selection"]))
    candidates = cast("list[dict[str, object]]", selection["excluded_candidates"])
    candidates[-1]["reactome_id"] = candidates[0]["reactome_id"]
    reject(selection)
    selection = cast("dict[str, object]", deepcopy(_document()["selection"]))
    candidates = cast("list[dict[str, object]]", selection["excluded_candidates"])
    next(item for item in candidates if "EMT" in str(item["name"]))["name"] = "removed"
    reject(selection)
    selection = cast("dict[str, object]", deepcopy(_document()["selection"]))
    candidates = cast("list[dict[str, object]]", selection["excluded_candidates"])
    next(item for item in candidates if item["name"] == "Apoptosis")["name"] = "not apoptosis"
    reject(selection)


def test_catalog_axis_guards_reject_patient_gene_and_parent_order_corruption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patient_axis = cast("dict[str, object]", deepcopy(_document()["patient_axis"]))
    gene_axis = cast("dict[str, object]", deepcopy(_document()["gene_axis"]))
    patient_axis["count"] = 103
    with pytest.raises(ReactomeTransitionSourceIntegrityError, match="patient-axis"):
        catalog._validate_axes(patient_axis, gene_axis)

    for key, value in (
        ("count", 1),
        ("order_digest", "sha256:" + "0" * 64),
        ("symbols_not_duplicated", False),
        ("ordering_basis", "forged"),
    ):
        patient_axis = cast("dict[str, object]", deepcopy(_document()["patient_axis"]))
        gene_axis = cast("dict[str, object]", deepcopy(_document()["gene_axis"]))
        gene_axis[key] = value
        with pytest.raises(ReactomeTransitionSourceIntegrityError, match="gene-axis"):
            catalog._validate_axes(patient_axis, gene_axis)

    patient_axis = cast("dict[str, object]", deepcopy(_document()["patient_axis"]))
    gene_axis = cast("dict[str, object]", deepcopy(_document()["gene_axis"]))
    monkeypatch.setattr(
        catalog,
        "longitudinal_gbm_catalog",
        lambda: SimpleNamespace(features=()),
    )
    with pytest.raises(ReactomeTransitionSourceIntegrityError, match="parent feature order"):
        catalog._validate_axes(patient_axis, gene_axis)
    fake_feature = SimpleNamespace(gene_symbol="X")
    monkeypatch.setattr(
        catalog,
        "longitudinal_gbm_catalog",
        lambda: SimpleNamespace(features=(fake_feature,) * catalog.EXPECTED_GENE_COUNT),
    )
    with pytest.raises(ReactomeTransitionSourceIntegrityError, match="parent feature order"):
        catalog._validate_axes(patient_axis, gene_axis)


def test_catalog_pathway_guards_reject_every_membership_invariant() -> None:  # noqa: PLR0915
    parent = longitudinal_gbm_catalog()
    eligible = frozenset(feature.index for feature in parent.features if feature.eligible)

    def reject(pathways: list[object]) -> None:
        with pytest.raises(ReactomeTransitionSourceIntegrityError):
            catalog._parse_pathways(pathways, parent_eligible_indices=eligible)

    pathways = cast("list[object]", deepcopy(_document()["pathways"]))
    reject(pathways[:-1])

    def fresh() -> tuple[list[object], dict[str, object]]:
        values = cast("list[object]", deepcopy(_document()["pathways"]))
        return values, cast("dict[str, object]", values[0])

    pathways, item = fresh()
    item["panel_index"] = 1
    reject(pathways)
    pathways, item = fresh()
    item["name"] = "forged"
    reject(pathways)
    pathways, item = fresh()
    item["species"] = "Mus musculus"
    reject(pathways)
    pathways, item = fresh()
    item["source_member_digest"] = "md5:" + "0" * 32
    reject(pathways)
    pathways, item = fresh()
    item["source_member_digest"] = "sha256:" + "0" * 63
    reject(pathways)
    pathways, item = fresh()
    members = cast("list[int]", item["member_feature_indices"])
    members.append(members[-1])
    reject(pathways)
    pathways, item = fresh()
    cast("list[int]", item["eligible_feature_indices"]).reverse()
    reject(pathways)
    pathways, item = fresh()
    members = cast("list[int]", item["member_feature_indices"])
    members.append(catalog.EXPECTED_GENE_COUNT)
    item["mapped_feature_count"] = len(members)
    item["mapping_fraction"] = round(len(members) / cast("int", item["source_member_count"]), 10)
    reject(pathways)
    pathways, item = fresh()
    member_set = set(cast("list[int]", item["member_feature_indices"]))
    extra = next(index for index in eligible if index not in member_set)
    eligible_members = cast("list[int]", item["eligible_feature_indices"])
    eligible_members.append(extra)
    eligible_members.sort()
    item["eligible_feature_count"] = len(eligible_members)
    reject(pathways)
    pathways, item = fresh()
    eligible_members = cast("list[int]", item["eligible_feature_indices"])
    eligible_members.pop()
    item["eligible_feature_count"] = len(eligible_members)
    reject(pathways)
    pathways, item = fresh()
    item["mapped_feature_count"] = 1
    reject(pathways)
    pathways, item = fresh()
    item["eligible_feature_count"] = 1
    reject(pathways)
    pathways, item = fresh()
    item["source_member_count"] = 4
    reject(pathways)
    pathways, item = fresh()
    members = cast("list[int]", item["member_feature_indices"])
    del members[4:]
    eligible_members = [index for index in members if index in eligible]
    item["eligible_feature_indices"] = eligible_members
    item["mapped_feature_count"] = len(members)
    item["eligible_feature_count"] = len(eligible_members)
    item["mapping_fraction"] = round(len(members) / cast("int", item["source_member_count"]), 10)
    reject(pathways)
    pathways, item = fresh()
    item["mapping_fraction"] = 0.9
    reject(pathways)
    pathways, item = fresh()
    item["source_member_count"] = 70
    item["mapping_fraction"] = round(
        cast("int", item["mapped_feature_count"]) / 70,
        10,
    )
    reject(pathways)
    pathways, item = fresh()
    parent_ids = cast("list[str]", item["parent_ids"])
    parent_ids.append(parent_ids[0])
    reject(pathways)


def test_catalog_loader_rejects_length_json_canonical_and_content_corruption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog.reactome_transition_source_catalog.cache_clear()
    monkeypatch.setattr(catalog, "_resource_bytes", lambda: b"{}")
    with pytest.raises(ReactomeTransitionSourceIntegrityError, match="byte length"):
        catalog.reactome_transition_source_catalog()

    for payload, message in (
        (b"{\n", "valid JSON"),
        (b"[]\n", "canonical JSON"),
        (b"{}", "canonical JSON"),
    ):
        _patch_artifact_file_locks(monkeypatch, payload)
        with pytest.raises(ReactomeTransitionSourceIntegrityError, match=message):
            catalog.reactome_transition_source_catalog()

    document = _document()
    document["artifact_digest"] = "sha256:" + "0" * 64
    payload = catalog._canonical_bytes(document)
    _patch_artifact_file_locks(monkeypatch, payload)
    with pytest.raises(ReactomeTransitionSourceIntegrityError, match="content digest"):
        catalog.reactome_transition_source_catalog()

    document = _document()
    cast("list[str]", document["limitations"])[0] = "forged"
    content = dict(document)
    content.pop("artifact_digest")
    new_digest = catalog._digest(content)
    payload = catalog._canonical_bytes(
        {**content, "artifact_digest": catalog.EXPECTED_CONTENT_DIGEST}
    )
    _patch_artifact_file_locks(monkeypatch, payload, content_digest=new_digest)
    with pytest.raises(ReactomeTransitionSourceIntegrityError, match="content digest"):
        catalog.reactome_transition_source_catalog()
    catalog.reactome_transition_source_catalog.cache_clear()


def test_catalog_loader_rejects_provenance_limitations_and_duplicate_maps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document()
    cast("dict[str, object]", document["provenance"])["invalid"] = []
    content = dict(document)
    content.pop("artifact_digest")
    content_digest = catalog._digest(content)
    payload = catalog._canonical_bytes({**content, "artifact_digest": content_digest})
    _patch_artifact_file_locks(monkeypatch, payload, content_digest=content_digest)
    with pytest.raises(ReactomeTransitionSourceIntegrityError, match="provenance"):
        catalog.reactome_transition_source_catalog()

    document = _document()
    document["limitations"] = []
    content = dict(document)
    content.pop("artifact_digest")
    content_digest = catalog._digest(content)
    payload = catalog._canonical_bytes({**content, "artifact_digest": content_digest})
    _patch_artifact_file_locks(monkeypatch, payload, content_digest=content_digest)
    with pytest.raises(ReactomeTransitionSourceIntegrityError, match="limitation"):
        catalog.reactome_transition_source_catalog()

    valid = catalog._parse_pathways(
        cast("list[object]", _document()["pathways"]),
        parent_eligible_indices=frozenset(
            feature.index for feature in longitudinal_gbm_catalog().features if feature.eligible
        ),
    )

    def duplicate_pathways(
        _values: list[object],
        *,
        parent_eligible_indices: frozenset[int],
    ) -> tuple[catalog.ReactomePathwayBinding, ...]:
        del parent_eligible_indices
        return (valid[0],) * catalog.EXPECTED_PATHWAY_COUNT

    payload = ARTIFACT.read_bytes()
    _patch_artifact_file_locks(
        monkeypatch,
        payload,
        content_digest=cast("str", _document()["artifact_digest"]),
    )
    monkeypatch.setattr(catalog, "_parse_pathways", duplicate_pathways)
    with pytest.raises(ReactomeTransitionSourceIntegrityError, match="duplicated"):
        catalog.reactome_transition_source_catalog()
    catalog.reactome_transition_source_catalog.cache_clear()


def test_importer_writer_rejects_literal_and_hashed_patient_material(tmp_path: Path) -> None:
    patient = "KNCC_GBM0001"
    with pytest.raises(ValueError, match="identifier leaked"):
        importer.write_artifact(
            {"value": patient},
            tmp_path / "literal.json",
            patient_groups=(patient,),
        )
    specimen = f"{patient}_T1"
    digest = hashlib.sha256(specimen.encode()).hexdigest()
    with pytest.raises(ValueError, match="identifier hash"):
        importer.write_artifact(
            {"value": digest},
            tmp_path / "hash.json",
            patient_groups=(patient,),
        )


def test_importer_writes_canonical_artifact_and_rejects_missing_sources(tmp_path: Path) -> None:
    document = _document()
    destination = tmp_path / "artifact.json"
    importer.write_artifact(document, destination, patient_groups=("KNCC_GBM9999",))
    assert destination.read_bytes() == ARTIFACT.read_bytes()
    with pytest.raises(ValueError, match="source lock mismatch"):
        importer.verify_reactome_sources(tmp_path)


@pytest.mark.skipif(
    not PDC_SOURCE_DIR.is_dir()
    or not HGNC_SOURCE.is_file()
    or not REACTOME_SOURCE_DIR.is_dir(),
    reason="exact raw PDC/HGNC/Reactome sources are not distributed with the package",
)
def test_local_sources_reproduce_artifact_without_consulting_outcome_values() -> None:
    cohort = base.load_cohort(PDC_SOURCE_DIR, HGNC_SOURCE)
    identity_only = base.Cohort(
        genes=cohort.genes,
        hgnc_ids=cohort.hgnc_ids,
        source_gene_labels=cohort.source_gene_labels,
        mapping_basis=cohort.mapping_basis,
        patient_groups=cohort.patient_groups,
        primary_delta=cast("base.FloatArray", object()),
        ordinary_delta=cast("base.FloatArray", object()),
        unshared_peptides=cohort.unshared_peptides,
        oracles=cohort.oracles,
    )
    regenerated = importer.build_artifact(identity_only, REACTOME_SOURCE_DIR)
    assert importer._canonical_bytes(regenerated) == ARTIFACT.read_bytes()
    assert tuple(cohort.patient_groups) == tuple(sorted(cohort.patient_groups))


@pytest.mark.skipif(
    not REACTOME_SOURCE_DIR.is_dir(),
    reason="exact raw Reactome sources are not distributed with the package",
)
def test_reactome_zip_and_decompressed_gmt_are_byte_identical() -> None:
    verified = importer.verify_reactome_sources(REACTOME_SOURCE_DIR)
    assert set(verified) == {item.relative_path for item in importer.REACTOME_FILES}
