"""Exact KNCC protein-axis and Neftel Table S2 program binding.

This module derives the transition feature inventory from two already verified
repository artifacts.  It contains no patient values and performs no fitting.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from types import MappingProxyType
from typing import Final, Mapping, cast

from glio_proteogen.research.longitudinal_gbm.catalog import (
    EXPECTED_ARTIFACT_BYTE_DIGEST as KNCC_ARTIFACT_BYTE_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm.catalog import (
    EXPECTED_CONTENT_DIGEST as KNCC_CONTENT_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm.catalog import (
    EXPECTED_FEATURE_COUNT as EXPECTED_GENE_COUNT,
)
from glio_proteogen.research.longitudinal_gbm.catalog import (
    EXPECTED_FEATURE_SPACE_DIGEST as KNCC_FEATURE_SPACE_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm.catalog import (
    EXPECTED_SOURCE_FILE_LOCK_DIGEST as KNCC_SOURCE_FILE_LOCK_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm.catalog import (
    EXPECTED_SOURCE_MANIFEST_DIGEST as KNCC_SOURCE_MANIFEST_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm.catalog import longitudinal_gbm_catalog
from glio_proteogen.research.neftel_protein_programs.catalog import (
    EXACT_SOURCE_PROGRAM_DIGEST,
    EXPECTED_PROGRAM_COUNTS,
    EXPECTED_PROGRAM_ORDER,
    marker_catalog,
)
from glio_proteogen.research.neftel_protein_programs.catalog import (
    EXPECTED_CATALOG_ARTIFACT_DIGEST as NEFTEL_CATALOG_ARTIFACT_DIGEST,
)
from glio_proteogen.research.neftel_protein_programs.catalog import (
    EXPECTED_CATALOG_CONTENT_DIGEST as NEFTEL_CATALOG_CONTENT_DIGEST,
)
from glio_proteogen.research.neftel_protein_programs.catalog import (
    HGNC_SHA256 as NEFTEL_HGNC_SHA256,
)
from glio_proteogen.research.neftel_protein_programs.catalog import (
    SOURCE_SHA256 as NEFTEL_TABLE_S2_SHA256,
)

from .canonical import sha256_digest
from .errors import NeftelTransitionSourceIntegrityError

PROFILE_ID: Final = "kncc-neftel-program-transition/1.0.0"
MODEL_ID: Final = "kncc-neftel-program-transition-model/1.0.0"
EXPECTED_PATIENT_COUNT: Final = 104
EXPECTED_PROGRAM_COUNT: Final = 8
EXPECTED_MAPPED_UNION_FEATURE_COUNT: Final = 289
EXPECTED_ELIGIBLE_UNION_FEATURE_COUNT: Final = 256

EXPECTED_PROGRAMS: Final = tuple(
    ("neftel_table_s2", program_id, program_id) for program_id in EXPECTED_PROGRAM_ORDER
)
EXPECTED_PROGRAM_MAPPED_COUNTS: Final = {
    "MES2": (50, 50, 42, 40),
    "MES1": (50, 50, 49, 47),
    "AC": (39, 39, 37, 36),
    "OPC": (50, 49, 47, 46),
    "NPC1": (50, 50, 43, 42),
    "NPC2": (50, 46, 41, 38),
    "G1/S": (29, 29, 26, 14),
    "G2/M": (45, 45, 37, 25),
}

PATIENT_ORDERING_POLICY: Final = (
    "PDC000514 strict paired patient groups in the frozen KNCC source-model order"
)
PATIENT_ORDER_RULE_DIGEST: Final = sha256_digest(
    {
        "policy": PATIENT_ORDERING_POLICY,
        "source_pair_count": EXPECTED_PATIENT_COUNT,
        "source_manifest_digest": KNCC_SOURCE_MANIFEST_DIGEST,
    }
)


@dataclass(frozen=True, slots=True)
class NeftelProgramBinding:
    """One exact Neftel program projected onto the frozen KNCC feature axis."""

    program_index: int
    domain_id: str
    program_id: str
    name: str
    species: str
    rationale: str
    parent_ids: tuple[str, ...]
    source_member_count: int
    protein_eligible_marker_count: int
    source_member_digest: str
    member_symbol_digest: str
    member_index_digest: str
    mapped_feature_count: int
    mapping_fraction: float
    eligible_feature_count: int
    mapped_feature_indices: tuple[int, ...]
    member_feature_indices: tuple[int, ...]
    eligible_feature_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class NeftelTransitionSourceCatalog:
    """Immutable binding of KNCC protein features to eight Neftel programs."""

    profile_id: str
    patient_count: int
    patient_ordering_policy: str
    patient_order_rule_digest: str
    genes: tuple[str, ...]
    gene_index_by_symbol: Mapping[str, int]
    gene_order_digest: str
    programs: tuple[NeftelProgramBinding, ...]
    program_by_id: Mapping[str, NeftelProgramBinding]
    artifact_byte_digest: str
    content_digest: str
    source_binding_digest: str
    neftel_source_program_digest: str
    program_order_digest: str
    program_membership_digest: str
    pdc_source_binding: Mapping[str, object]
    pdc_source_binding_digest: str
    source_catalog_binding: Mapping[str, object]
    kncc_artifact_byte_digest: str
    kncc_content_digest: str
    kncc_feature_space_digest: str
    kncc_source_file_lock_digest: str
    kncc_source_manifest_digest: str
    neftel_catalog_artifact_digest: str
    neftel_catalog_content_digest: str
    neftel_table_s2_sha256: str
    neftel_hgnc_sha256: str
    neftel_protein_background_digest: str
    neftel_article_doi: str
    neftel_source_url: str
    terms_state: str
    provenance: Mapping[str, str]
    limitations: tuple[str, ...]


def _fail(message: str) -> None:
    raise NeftelTransitionSourceIntegrityError(message)


def _artifact_digest(value: object) -> str:
    payload = (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _pdc_source_binding() -> dict[str, object]:
    resource = files("glio_proteogen.research.longitudinal_gbm").joinpath(
        "data/kncc_paired_protein_transition.v1.json"
    )
    document = cast("dict[str, object]", json.loads(resource.read_bytes()))
    source_lock = cast("dict[str, object]", document["source_lock"])
    manifest = cast("dict[str, object]", source_lock["versioned_source_manifest"])
    gene_identity = cast("dict[str, object]", document["gene_identity"])
    source_files = cast("list[dict[str, object]]", source_lock["files"])
    return {
        "pdc_study_id": source_lock["pdc_study_id"],
        "pdc_study_version_uuid": source_lock["pdc_study_version_uuid"],
        "versioned_source_manifest": {
            key: manifest[key]
            for key in (
                "filename",
                "bytes",
                "sha256",
                "schema_version",
                "graphql_api_version",
            )
        },
        "files": [
            {
                "filename": item["filename"],
                "uuid": item["uuid"],
                "bytes": item["bytes"],
                "md5": item["md5"],
                "sha256": f"sha256:{item['sha256']}",
            }
            for item in source_files
        ],
        "hgnc_authority": {
            "filename": gene_identity["authority_filename"],
            "bytes": gene_identity["authority_bytes"],
            "sha256": gene_identity["authority_sha256"],
        },
        "primary_measure": "Unshared Log",
        "source_processing_ablation_measure": "Log",
    }


@lru_cache(maxsize=1)
def neftel_transition_source_catalog() -> NeftelTransitionSourceCatalog:
    """Build and verify the exact source binding from the two pinned catalogs."""

    kncc = longitudinal_gbm_catalog()
    neftel = marker_catalog()
    genes = tuple(feature.gene_symbol for feature in kncc.features)
    gene_index = {symbol: index for index, symbol in enumerate(genes)}
    if (
        len(genes) != EXPECTED_GENE_COUNT
        or len(gene_index) != EXPECTED_GENE_COUNT
        or kncc.artifact_byte_digest != KNCC_ARTIFACT_BYTE_DIGEST
        or kncc.content_digest != KNCC_CONTENT_DIGEST
        or kncc.feature_space_digest != KNCC_FEATURE_SPACE_DIGEST
        or neftel.artifact_digest != NEFTEL_CATALOG_ARTIFACT_DIGEST
        or neftel.content_digest != NEFTEL_CATALOG_CONTENT_DIGEST
        or neftel.source_program_digest != EXACT_SOURCE_PROGRAM_DIGEST
        or tuple(neftel.programs) != EXPECTED_PROGRAM_ORDER
    ):
        _fail("KNCC or Neftel parent catalog binding mismatch")

    programs: list[NeftelProgramBinding] = []
    for program_index, program_id in enumerate(EXPECTED_PROGRAM_ORDER):
        markers = neftel.programs[program_id]
        protein_markers = tuple(marker for marker in markers if marker.protein_eligible)
        mapped = tuple(
            gene_index[marker.normalized_symbol]
            for marker in protein_markers
            if marker.normalized_symbol in gene_index
        )
        eligible = tuple(index for index in mapped if kncc.features[index].eligible)
        expected = EXPECTED_PROGRAM_MAPPED_COUNTS[program_id]
        observed = (len(markers), len(protein_markers), len(mapped), len(eligible))
        if observed != expected or len(markers) != EXPECTED_PROGRAM_COUNTS[program_id]:
            _fail(f"Neftel {program_id} KNCC mapping-count mismatch")
        if len(set(mapped)) != len(mapped) or len(set(eligible)) != len(eligible):
            _fail(f"Neftel {program_id} mapping contains duplicate features")
        source_member_digest = sha256_digest(
            [marker.normalized_symbol for marker in protein_markers]
        )
        member_symbol_digest = _artifact_digest([genes[index] for index in eligible])
        member_index_digest = _artifact_digest(list(eligible))
        programs.append(
            NeftelProgramBinding(
                program_index=program_index,
                domain_id="neftel_table_s2",
                program_id=program_id,
                name=program_id,
                species="Homo sapiens",
                rationale="Exact Neftel Table S2 program membership projected to KNCC proteins.",
                parent_ids=(),
                source_member_count=len(markers),
                protein_eligible_marker_count=len(protein_markers),
                source_member_digest=source_member_digest,
                member_symbol_digest=member_symbol_digest,
                member_index_digest=member_index_digest,
                mapped_feature_count=len(mapped),
                mapping_fraction=len(mapped) / len(protein_markers),
                eligible_feature_count=len(eligible),
                mapped_feature_indices=mapped,
                member_feature_indices=eligible,
                eligible_feature_indices=eligible,
            )
        )

    mapped_union = tuple(
        sorted({index for item in programs for index in item.mapped_feature_indices})
    )
    eligible_union = tuple(
        sorted({index for item in programs for index in item.eligible_feature_indices})
    )
    if (
        len(programs) != EXPECTED_PROGRAM_COUNT
        or len(mapped_union) != EXPECTED_MAPPED_UNION_FEATURE_COUNT
        or len(eligible_union) != EXPECTED_ELIGIBLE_UNION_FEATURE_COUNT
    ):
        _fail("Neftel KNCC union-feature inventory mismatch")

    gene_order_digest = sha256_digest(list(genes))
    program_order_digest = _artifact_digest(list(EXPECTED_PROGRAM_ORDER))
    program_membership_digest = _artifact_digest(
        [
            {
                "program_id": item.program_id,
                "mapped_symbols": [genes[index] for index in item.mapped_feature_indices],
                "mapped_feature_indices": list(item.mapped_feature_indices),
                "member_symbols": [genes[index] for index in item.member_feature_indices],
                "member_feature_indices": list(item.member_feature_indices),
            }
            for item in programs
        ]
    )
    pdc_source_binding = _pdc_source_binding()
    pdc_source_binding_digest = _artifact_digest(pdc_source_binding)
    source_binding = {
        "pdc_source_binding": pdc_source_binding,
        "pdc_source_binding_digest": pdc_source_binding_digest,
        "neftel_catalog_artifact_digest": NEFTEL_CATALOG_ARTIFACT_DIGEST,
        "neftel_catalog_content_digest": NEFTEL_CATALOG_CONTENT_DIGEST,
        "neftel_source_program_digest": EXACT_SOURCE_PROGRAM_DIGEST,
        "neftel_source_sha256": NEFTEL_TABLE_S2_SHA256,
        "neftel_hgnc_sha256": NEFTEL_HGNC_SHA256,
        "neftel_protein_background_digest": neftel.protein_background_digest,
        "program_order_digest": program_order_digest,
        "program_membership_digest": program_membership_digest,
    }
    source_binding_digest = _artifact_digest(source_binding)
    provenance = MappingProxyType(
        {
            "kncc_attribution": kncc.source_attribution,
            "kncc_source_license": kncc.source_license,
            "kncc_source_license_url": kncc.source_license_url,
            "kncc_transformation_notice": kncc.source_transformation_notice,
            "neftel_article_doi": "10.1016/j.cell.2019.06.024",
            "neftel_source_url": neftel.source_url,
            "neftel_terms_state": "not_asserted_by_this_derived_catalog",
        }
    )
    return NeftelTransitionSourceCatalog(
        profile_id=PROFILE_ID,
        patient_count=EXPECTED_PATIENT_COUNT,
        patient_ordering_policy=PATIENT_ORDERING_POLICY,
        patient_order_rule_digest=PATIENT_ORDER_RULE_DIGEST,
        genes=genes,
        gene_index_by_symbol=MappingProxyType(gene_index),
        gene_order_digest=gene_order_digest,
        programs=tuple(programs),
        program_by_id=MappingProxyType({item.program_id: item for item in programs}),
        artifact_byte_digest=NEFTEL_CATALOG_ARTIFACT_DIGEST,
        content_digest=NEFTEL_CATALOG_CONTENT_DIGEST,
        source_binding_digest=source_binding_digest,
        neftel_source_program_digest=EXACT_SOURCE_PROGRAM_DIGEST,
        program_order_digest=program_order_digest,
        program_membership_digest=program_membership_digest,
        pdc_source_binding=MappingProxyType(pdc_source_binding),
        pdc_source_binding_digest=pdc_source_binding_digest,
        source_catalog_binding=MappingProxyType(source_binding),
        kncc_artifact_byte_digest=KNCC_ARTIFACT_BYTE_DIGEST,
        kncc_content_digest=KNCC_CONTENT_DIGEST,
        kncc_feature_space_digest=KNCC_FEATURE_SPACE_DIGEST,
        kncc_source_file_lock_digest=KNCC_SOURCE_FILE_LOCK_DIGEST,
        kncc_source_manifest_digest=KNCC_SOURCE_MANIFEST_DIGEST,
        neftel_catalog_artifact_digest=NEFTEL_CATALOG_ARTIFACT_DIGEST,
        neftel_catalog_content_digest=NEFTEL_CATALOG_CONTENT_DIGEST,
        neftel_table_s2_sha256=NEFTEL_TABLE_S2_SHA256,
        neftel_hgnc_sha256=NEFTEL_HGNC_SHA256,
        neftel_protein_background_digest=neftel.protein_background_digest,
        neftel_article_doi="10.1016/j.cell.2019.06.024",
        neftel_source_url=neftel.source_url,
        terms_state="not_asserted_by_this_derived_catalog",
        provenance=provenance,
        limitations=(
            "Program identities are exact Neftel Table S2 marker sets, not cell fractions.",
            "Bulk-protein program coordinates do not identify cellular origin or subtype.",
            "The paired KNCC source cohort does not validate recurrence prediction.",
        ),
    )


__all__ = [
    "EXPECTED_ELIGIBLE_UNION_FEATURE_COUNT",
    "EXPECTED_GENE_COUNT",
    "EXPECTED_MAPPED_UNION_FEATURE_COUNT",
    "EXPECTED_PATIENT_COUNT",
    "EXPECTED_PROGRAMS",
    "EXPECTED_PROGRAM_COUNT",
    "EXPECTED_PROGRAM_MAPPED_COUNTS",
    "MODEL_ID",
    "PROFILE_ID",
    "NeftelProgramBinding",
    "NeftelTransitionSourceCatalog",
    "neftel_transition_source_catalog",
]
