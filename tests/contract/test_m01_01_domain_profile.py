"""Locked evidence for the real M01-01 GLIO preanalytic domain profile."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from importlib.resources import files
from typing import Any

import pytest
from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_01.canonical import (
    identity_binding_digest,
    protocol_digest,
)
from glio_proteogen.contracts.m01_01.v1 import (
    ConformanceDecision,
    MetadataDocument,
    ProtocolSchema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.validator import (
    validate_metadata,
    validate_protocol_schema,
)

_PROFILE_PACKAGE = "glio_proteogen.profiles.m01_01.v1"
_MINIMUM_CORPUS_CASES = 10
_SCHEMA_ADAPTER = TypeAdapter(ProtocolSchema)
_DOCUMENT_ADAPTER = TypeAdapter(MetadataDocument)


def _asset_bytes(name: str) -> bytes:
    return files(_PROFILE_PACKAGE).joinpath(name).read_bytes()


def _asset_json(name: str) -> Any:
    return strict_json_loads(_asset_bytes(name))


def _profile_schema() -> ProtocolSchema:
    return _SCHEMA_ADAPTER.validate_json(_asset_bytes("protocol-schema.json"))


def _case_document(corpus: dict[str, Any], case: dict[str, Any]) -> MetadataDocument:
    document = deepcopy(corpus["base_document"])
    entries = {entry["path"]: entry for entry in document["entries"]}
    for path in case["remove_paths"]:
        entries.pop(path)
    for entry in case["replace_entries"]:
        entries[entry["path"]] = entry
    for entry in case["add_entries"]:
        assert entry["path"] not in entries
        entries[entry["path"]] = entry
    document["entries"] = list(entries.values())
    return _DOCUMENT_ADAPTER.validate_json(canonical_json_bytes(document))


_CORPUS = _asset_json("conformance-corpus.json")


@pytest.mark.contract
def test_domain_protocol_is_shape_and_semantically_valid() -> None:
    schema = _profile_schema()

    report = validate_protocol_schema(schema)

    assert schema.schema_id == "glio_preanalytic_proteomics"
    assert schema.version == "1.0.0"
    assert report.decision is ConformanceDecision.CONFORMANT
    assert report.issues == ()
    assert not report.human_review_required


@pytest.mark.contract
def test_catalog_accounts_for_every_field_and_every_optional_obligation() -> None:
    schema = _profile_schema()
    catalog = _asset_json("catalog.json")
    grouped_paths = [
        path for group in catalog["field_groups"] for path in group["paths"]
    ]
    conditional = {entry["path"]: entry for entry in catalog["conditional_fields"]}
    fields = {field.path: field for field in schema.fields}
    rules = {rule.rule_id for rule in schema.compatibility_rules}

    assert len(grouped_paths) == len(set(grouped_paths))
    assert set(grouped_paths) == set(fields)
    assert set(conditional) == {path for path, field in fields.items() if not field.required}
    assert all(
        set(entry["enforced_by"]).issubset(rules) and entry["obligation"]
        for entry in conditional.values()
    )


@pytest.mark.contract
def test_profile_has_mandatory_owned_domain_surfaces() -> None:
    schema = _profile_schema()
    fields = {field.path: field for field in schema.fields}
    required_paths = {
        "/identity/analytical_sample_id",
        "/identity/source_specimen_id",
        "/identity/lineage_node_id",
        "/context/treatment_history/reference_id",
        "/context/genomic_context/reference_id",
        "/context/transcriptome_context/reference_id",
        "/context/ptm_annotations/reference_id",
        "/specimen/preservation",
        "/specimen/warm_ischemia_time",
        "/specimen/cold_ischemia_time",
        "/preparation/protocol_reference_id",
        "/preparation/cleavage_agent",
        "/acquisition/method",
        "/acquisition/instrument_model",
        "/acquisition/raw_data_digest",
        "/quality/report_reference_id",
        "/quality/pathology_review_status",
    }

    assert all(fields[path].required for path in required_paths)
    assert fields["/identity/analytical_sample_id"].identity_key
    assert not any(
        fields[path].identity_key
        for path in fields
        if path != "/identity/analytical_sample_id"
    )


@pytest.mark.contract
def test_profile_units_are_pinned_and_reference_complete() -> None:
    schema = _profile_schema()
    catalog = _asset_json("catalog.json")
    units = {unit.code: unit for unit in schema.units}
    unitful_fields = [field for field in schema.fields if field.allowed_units]

    assert catalog["unit_catalog"]["system"] == "UCUM"
    assert catalog["unit_catalog"]["system_version"] == "2.2"
    assert set(catalog["unit_catalog"]["codes"]) == set(units)
    assert all(unit.system == "UCUM" and unit.system_version == "2.2" for unit in units.values())
    assert all(field.reference_unit in field.allowed_units for field in unitful_fields)
    assert all(set(field.allowed_units).issubset(units) for field in unitful_fields)


@pytest.mark.contract
def test_external_controlled_subsets_are_exact_and_versioned() -> None:
    schema = _profile_schema()
    vocabularies = {
        vocabulary.vocabulary_id: vocabulary for vocabulary in schema.vocabularies
    }
    term_codes = {
        vocabulary_id: {term.code for term in vocabulary.terms}
        for vocabulary_id, vocabulary in vocabularies.items()
    }

    assert vocabularies["psi_ms.cleavage_agent"].version == "4.1.258"
    assert term_codes["psi_ms.cleavage_agent"] == {"MS:1001251", "MS:1001309"}
    assert term_codes["psi_ms.instrument_model"] == {
        "MS:1002523",
        "MS:1002732",
        "MS:1003005",
    }
    assert term_codes["pride.acquisition_method"] == {
        "PRIDE:0000450",
        "PRIDE:0000627",
    }
    assert term_codes["glio.organism"] == {"NCBITaxon:9606"}
    assert term_codes["glio.organism_part"] == {"UBERON:0000955"}


@pytest.mark.contract
def test_standards_manifest_is_pinned_offline_and_traceable() -> None:
    catalog = _asset_json("catalog.json")
    manifest = _asset_json("standards-manifest.json")
    sources = {source["source_id"]: source for source in manifest["sources"]}
    referenced_sources = {
        source_id
        for group in catalog["field_groups"]
        for source_id in group["source_ids"]
    }
    required_sources = {
        "governing_dossier",
        "sdrf_proteomics_1_1_0",
        "psi_ms_cv_4_1_258",
        "pride_ontology_2026_06_19",
        "ucum_2_2",
        "mzml_1_1_1",
        "miape_2007",
        "brisq_2011",
        "nci_best_practices_2026",
        "nci_gdc_biospecimen",
    }

    assert manifest["runtime_reference_inventory"] == []
    assert required_sources == set(sources)
    assert referenced_sources.issubset(sources)
    assert all(source["runtime_dependency"] is False for source in sources.values())
    assert all(source["used_for"] for source in sources.values())
    assert sources["governing_dossier"]["content_digest"].startswith("sha256:")
    assert sources["ucum_2_2"]["source_pin"].startswith("git:")


@pytest.mark.contract
def test_artifact_manifest_locks_exact_packaged_bytes_and_protocol_identity() -> None:
    manifest = _asset_json("artifact-manifest.json")
    schema = _profile_schema()
    manifested_files = {artifact["file"] for artifact in manifest["artifacts"]}
    packaged_files = {
        asset.name
        for asset in files(_PROFILE_PACKAGE).iterdir()
        if asset.name.endswith(".json") and asset.name != "artifact-manifest.json"
    }

    assert manifest["canonical_protocol_digest"] == protocol_digest(schema)
    assert manifested_files == packaged_files
    for artifact in manifest["artifacts"]:
        payload = _asset_bytes(artifact["file"])
        assert len(payload) == artifact["bytes"]
        assert f"sha256:{sha256(payload).hexdigest()}" == artifact["digest"]


@pytest.mark.contract
def test_profile_exposes_non_removable_scientific_and_safety_ceilings() -> None:
    schema = _profile_schema()
    limitation_codes = {limitation.code for limitation in schema.limitations}

    assert {
        "research_use_only",
        "declared_metadata_only",
        "no_kinase_state",
        "no_treatment_recommendation",
        "no_generic_omics_fusion",
        "brain_tissue_scope",
        "bottom_up_ms_scope",
        "opaque_identity_only",
        "no_missing_to_negative",
    }.issubset(limitation_codes)


@pytest.mark.contract
def test_profile_paths_do_not_invite_direct_personal_identifiers() -> None:
    schema = _profile_schema()
    prohibited_tokens = {"patient", "name", "mrn", "birth", "address", "email", "phone"}

    assert all(
        prohibited_tokens.isdisjoint(field.path.lower().replace("/", "_").split("_"))
        for field in schema.fields
    )
    assert all(
        value.startswith("syn-") or "synthetic" in value
        for value in _synthetic_identifiers(_CORPUS["base_document"])
    )


def _synthetic_identifiers(document: dict[str, Any]) -> list[str]:
    identifier_fragments = (
        "/identity/",
        "/context/",
        "/preparation/protocol_reference_id",
        "/acquisition/assay_id",
        "/acquisition/raw_data_reference_id",
        "/quality/report_reference_id",
    )
    values: list[str] = []
    for entry in document["entries"]:
        if not any(fragment in entry["path"] for fragment in identifier_fragments):
            continue
        value = entry["values"][0].get("value")
        if isinstance(value, str) and not value.startswith("sha256:"):
            values.append(value.lower())
    return values


@pytest.mark.contract
def test_conformance_corpus_is_unique_bounded_and_mixed() -> None:
    schema = _profile_schema()
    cases = _CORPUS["cases"]
    case_ids = [case["case_id"] for case in cases]
    known_paths = {field.path for field in schema.fields}

    assert len(case_ids) == len(set(case_ids))
    assert len(cases) >= _MINIMUM_CORPUS_CASES
    assert {case["expected_decision"] for case in cases} == {
        "conformant",
        "nonconformant",
        "quarantined",
        "review_required",
    }
    for case in cases:
        mutation_paths = [
            *(entry["path"] for entry in case["replace_entries"]),
            *case["remove_paths"],
            *(entry["path"] for entry in case["add_entries"]),
        ]
        assert len(mutation_paths) == len(set(mutation_paths))
        assert set(mutation_paths).issubset(known_paths)


@pytest.mark.contract
@pytest.mark.parametrize(
    "case",
    _CORPUS["cases"],
    ids=[case["case_id"] for case in _CORPUS["cases"]],
)
def test_locked_domain_conformance_case(case: dict[str, Any]) -> None:
    schema = _profile_schema()
    document = _case_document(_CORPUS, case)
    expected_binding_digest = case.get(
        "expected_identity_binding_digest",
        identity_binding_digest(schema, document),
    )

    report = validate_metadata(
        schema,
        document,
        consent_state=ConsentState.GRANTED,
        expected_identity_binding_digest=expected_binding_digest,
    )

    assert report.decision.value == case["expected_decision"]
    assert report.human_review_required is case["expected_human_review"]
    assert {issue.code for issue in report.issues} == set(case["expected_issue_codes"])
