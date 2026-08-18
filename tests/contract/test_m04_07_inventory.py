"""Static closure checks for the locked M04-07 synthetic corpus."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final, cast

from glio_proteogen.contracts.m04_07 import (
    M0407_MAX_ANALYSIS_TARGETS,
    M0407_MAX_PLATFORM_LEVEL_IDS,
    M0407_OUTPUT_MEDIA_TYPE,
    M0407_QUALITY_METRIC_COUNT,
    contract_json_schemas,
)

_CORPUS_PATH: Final = Path(__file__).parents[1] / "fixtures" / "m04_07" / "scenarios.json"
_DIMENSIONS: Final = {
    "assay",
    "specimen",
    "disease_class",
    "quality",
    "completeness",
    "platform",
    "reference",
    "intended_use",
}
_EXPECTED_GROUP_COUNT: Final = 8
_EXPECTED_CASE_COUNT: Final = 19
_EXPECTED_SCHEMA_COUNT: Final = 14
_EXPECTED_QUALITY_METRIC_COUNT: Final = 32
_FALSE_AUTHORITY_FIELDS: Final = {
    "emits_protein_rna_discordance",
    "emits_proteogenomic_state",
    "emits_proteotype",
    "emits_protein_level_subtype",
    "infers_identity",
    "infers_consent",
    "infers_protein",
    "infers_proteoform",
    "infers_isoform",
    "localizes_modification",
    "infers_kinase_activity",
    "performs_cn_to_protein_regression",
    "performs_all_omics_fusion",
    "recommends_treatment",
    "mutates_upstream",
    "executes_model",
}


def _corpus() -> dict[str, Any]:
    return cast(
        "dict[str, Any]",
        json.loads(_CORPUS_PATH.read_text(encoding="utf-8")),
    )


def test_locked_inventory_is_exact_and_unique() -> None:
    corpus = _corpus()
    groups = corpus["scenario_groups"]
    case_ids = [case_id for group in groups for case_id in group["case_ids"]]

    assert corpus["module_id"] == "GLIO-PROTEOGEN-M04-07"
    assert corpus["operation"] == "route_proteoform_support"
    assert corpus["output_media_type"] == M0407_OUTPUT_MEDIA_TYPE
    assert corpus["parent_target"] == "protein_rna_discordance"
    assert set(corpus["dimensions"]) == _DIMENSIONS
    assert len(groups) == corpus["expected_group_count"] == _EXPECTED_GROUP_COUNT
    assert (
        len(case_ids)
        == len(set(case_ids))
        == corpus["expected_total_case_count"]
        == _EXPECTED_CASE_COUNT
    )
    assert [len(group["case_ids"]) for group in groups] == corpus["expected_case_allocation"]
    assert corpus["installed_capacity"]["platform_levels"] == M0407_MAX_PLATFORM_LEVEL_IDS
    assert corpus["installed_capacity"]["analysis_targets"] == M0407_MAX_ANALYSIS_TARGETS


def test_every_declared_unsupported_scientific_case_abstains() -> None:
    corpus = _corpus()
    unsupported = {
        "each_dimension_outside_envelope",
        "missing_and_unknown_evidence",
        "unreleasable_prerequisite_receipts",
        "all_members_platform_reference",
        "cross_envelope_combination_rejected",
    }
    groups = {group["group_id"]: group for group in corpus["scenario_groups"]}

    assert all(groups[group_id]["expected_disposition"] == "abstained" for group_id in unsupported)
    assert set(groups["each_dimension_outside_envelope"]["case_ids"]) == {
        f"outside_{dimension}" for dimension in _DIMENSIONS
    }


def test_output_ceiling_prohibits_apparently_valid_scientific_results() -> None:
    ceiling = _corpus()["output_ceiling"]

    assert ceiling["support_decision"] is True
    assert ceiling["typed_reasons"] is True
    assert ceiling["reviewed_remediation"] is True
    assert ceiling.keys() >= _FALSE_AUTHORITY_FIELDS
    assert all(ceiling[field] is False for field in _FALSE_AUTHORITY_FIELDS)


def test_contract_scaffold_exports_all_schemas_with_the_m04_quality_domain() -> None:
    schemas = contract_json_schemas()
    quality = cast(
        "dict[str, Any]",
        schemas["quality-receipt"]["properties"],
    )
    output_metadata = cast("dict[str, Any]", schemas["output"]["x-glio-contract"])

    assert len(schemas) == _EXPECTED_SCHEMA_COUNT
    assert (
        quality["metrics"]["maxItems"]
        == M0407_QUALITY_METRIC_COUNT
        == _EXPECTED_QUALITY_METRIC_COUNT
    )
    assert output_metadata["proteinRnaDiscordance"] is False
    assert output_metadata["proteoformInference"] is False
    assert output_metadata["kinaseActivityInference"] is False
    assert output_metadata["allOmicsFusion"] is False
    assert output_metadata["treatmentRecommendation"] is False
