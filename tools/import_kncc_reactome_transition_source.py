# ruff: noqa: PLR2004, T201, TRY003
"""Build the de-identified Reactome V97/PDC000514 transition source binding.

This importer admits topology and assay identity only.  It never reads a patient
outcome to choose or rank pathways, never serializes patient identifiers, and does
not fit or claim a pathway activity model.  The generated artifact is the compact,
source-locked input catalog for the planned
``kncc-reactome-conditional-transition/1.0.0`` research lane.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from collections.abc import Iterable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from glio_proteogen.research.longitudinal_gbm.catalog import (
    EXPECTED_ARTIFACT_BYTE_DIGEST as PARENT_ARTIFACT_BYTE_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm.catalog import (
    EXPECTED_CONTENT_DIGEST as PARENT_CONTENT_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm.catalog import (
    EXPECTED_FEATURE_SPACE_DIGEST as PARENT_FEATURE_SPACE_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm.catalog import (
    EXPECTED_SOURCE_FILE_LOCK_DIGEST as PARENT_SOURCE_FILE_LOCK_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm.catalog import (
    EXPECTED_SOURCE_MANIFEST_DIGEST as PARENT_SOURCE_MANIFEST_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm.catalog import longitudinal_gbm_catalog
from tools import import_kncc_longitudinal_gbm as base

PROFILE_ID: Final = "kncc-reactome-conditional-transition/1.0.0"
SCHEMA_VERSION: Final = "glio-proteogen.kncc-reactome-transition-source/1.0.0"
SELECTION_RULE_ID: Final = "gbm-mechanism-slots-reactome-v97/1.0.0"
REACTOME_RELEASE: Final = 97
REACTOME_SPECIES: Final = "Homo sapiens"
EXPECTED_PATIENT_COUNT: Final = 104
EXPECTED_GENE_COUNT: Final = 11_312
MIN_SOURCE_GENES: Final = 5
MAX_SOURCE_GENES: Final = 1_500
MIN_MAPPED_GENES: Final = 5
MIN_MAPPING_FRACTION: Final = 0.65


@dataclass(frozen=True, slots=True)
class SourceFileLock:
    """One exact local Reactome source file consumed by the importer."""

    relative_path: str
    bytes: int
    sha256: str


REACTOME_FILES: Final = (
    SourceFileLock(
        "ReactomePathways.gmt.zip",
        298_479,
        "8c1dbc8578431da5d2d5118262718c60b553a9be3398e93658daa069e4a9afd4",
    ),
    SourceFileLock(
        "gmt/ReactomePathways.gmt",
        1_032_186,
        "89983d5c1f0af11c52edfeee7323eb425580ac6281d387a528562ab1787ce56b",
    ),
    SourceFileLock(
        "ReactomePathways.txt",
        1_592_393,
        "f6d7a2bf89b5bcfe0250a0bc7f51bff94641447911712b8ff129f5b55e52df3a",
    ),
    SourceFileLock(
        "ReactomePathwaysRelation.txt",
        634_259,
        "fd49a624d80c14eb37ae57a02e141d574d5ede3f60022bb99edbd909448a3f1e",
    ),
)


@dataclass(frozen=True, slots=True)
class PanelSpec:
    """One pre-outcome GBM mechanism slot and its exact Reactome event."""

    domain_id: str
    reactome_id: str
    expected_name: str
    rationale: str


PANEL_SPECS: Final = (
    PanelSpec(
        "receptor_egfr",
        "R-HSA-177929",
        "Signaling by EGFR",
        "physiological EGFR parent; avoids variant-specific cancer assertions",
    ),
    PanelSpec(
        "receptor_pdgf",
        "R-HSA-186797",
        "Signaling by PDGF",
        "physiological PDGF signaling; avoids disease-mutant receptor assertions",
    ),
    PanelSpec(
        "second_messenger_pi3k_akt",
        "R-HSA-198203",
        "PI3K/AKT activation",
        "bounded physiological activation branch; avoids cancer-genotype assertions",
    ),
    PanelSpec(
        "mtor_signaling",
        "R-HSA-165159",
        "MTOR signalling",
        "physiological MTOR parent rather than one nutrient-sensitive sub-branch",
    ),
    PanelSpec(
        "mapk_cascades",
        "R-HSA-5683057",
        "MAPK family signaling cascades",
        "family-level MAPK branch rather than one terminal MAPK1/3 sub-branch",
    ),
    PanelSpec(
        "cell_cycle",
        "R-HSA-1640170",
        "Cell Cycle",
        "complete physiological cell-cycle root; no RB1 genotype is inferred",
    ),
    PanelSpec(
        "dna_repair",
        "R-HSA-73894",
        "DNA Repair",
        "complete physiological repair root rather than one regulator-specific child",
    ),
    PanelSpec(
        "hypoxia_response",
        "R-HSA-1234174",
        "Cellular response to hypoxia",
        "complete response branch rather than HIF-alpha hydroxylation alone",
    ),
    PanelSpec(
        "extracellular_matrix",
        "R-HSA-1474244",
        "Extracellular matrix organization",
        "complete organization root rather than degradation alone",
    ),
    PanelSpec(
        "innate_immune_system",
        "R-HSA-168249",
        "Innate Immune System",
        "physiological innate-immune root; no immune-cell fraction is inferred",
    ),
)


@dataclass(frozen=True, slots=True)
class ExcludedCandidate:
    """One explicit nearby candidate excluded before outcome inspection."""

    domain_id: str
    reactome_id: str
    expected_name: str
    reason: str


EXCLUDED_CANDIDATES: Final = (
    ExcludedCandidate(
        "receptor_egfr",
        "R-HSA-5637812",
        "Signaling by EGFRvIII in Cancer",
        "variant- and disease-specific; would imply an unobserved genotype",
    ),
    ExcludedCandidate(
        "receptor_pdgf",
        "R-HSA-9671555",
        "Signaling by PDGFR in disease",
        "disease-mutant branch; genotype is not established by protein abundance",
    ),
    ExcludedCandidate(
        "second_messenger_pi3k_akt",
        "R-HSA-2219528",
        "PI3K/AKT Signaling in Cancer",
        "cancer-specific umbrella; the physiological branch has a narrower claim ceiling",
    ),
    ExcludedCandidate(
        "mapk_cascades",
        "R-HSA-5684996",
        "MAPK1/MAPK3 signaling",
        "narrow sub-branch does not represent the prespecified MAPK-family slot",
    ),
    ExcludedCandidate(
        "mtor_signaling",
        "R-HSA-166208",
        "mTORC1-mediated signalling",
        "narrow complex-specific child of the prespecified MTOR slot",
    ),
    ExcludedCandidate(
        "cell_cycle",
        "R-HSA-69278",
        "Cell Cycle, Mitotic",
        "narrower child omits non-mitotic cell-cycle evidence in the frozen slot",
    ),
    ExcludedCandidate(
        "dna_repair",
        "R-HSA-6796648",
        "TP53 Regulates Transcription of DNA Repair Genes",
        "regulator-specific child; protein evidence does not establish TP53 mechanism",
    ),
    ExcludedCandidate(
        "hypoxia_response",
        "R-HSA-1234176",
        "Oxygen-dependent proline hydroxylation of Hypoxia-inducible Factor Alpha",
        "single biochemical child of the complete hypoxia-response slot",
    ),
    ExcludedCandidate(
        "extracellular_matrix",
        "R-HSA-1474228",
        "Degradation of the extracellular matrix",
        "one-direction child of the complete organization slot",
    ),
    ExcludedCandidate(
        "innate_immune_system",
        "R-HSA-168256",
        "Immune System",
        "2,494-gene root mixes adaptive and innate branches outside the frozen slot",
    ),
    ExcludedCandidate(
        "scope_boundary",
        "R-HSA-2173791",
        "TGF-beta receptor signaling in EMT (epithelial to mesenchymal transition)",
        "EMT is an epithelial program and is not relabeled as a GBM transition coordinate",
    ),
    ExcludedCandidate(
        "scope_boundary",
        "R-HSA-109581",
        "Apoptosis",
        "not added post hoc merely to improve transition-effect performance",
    ),
)


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_reactome_sources(source_dir: Path) -> dict[str, Path]:
    """Verify every consumed V97 file and the zip/decompressed GMT identity."""

    verified: dict[str, Path] = {}
    for lock in REACTOME_FILES:
        path = source_dir / Path(lock.relative_path)
        if (
            not path.is_file()
            or path.stat().st_size != lock.bytes
            or _file_digest(path) != lock.sha256
        ):
            raise ValueError(f"Reactome source lock mismatch: {lock.relative_path}")
        verified[lock.relative_path] = path
    with zipfile.ZipFile(verified["ReactomePathways.gmt.zip"]) as archive:
        if archive.namelist() != ["ReactomePathways.gmt"]:
            raise ValueError("Reactome GMT zip member inventory mismatch")
        archived = archive.read("ReactomePathways.gmt")
    if archived != verified["gmt/ReactomePathways.gmt"].read_bytes():
        raise ValueError("Reactome zipped and decompressed GMT bytes differ")
    return verified


def _parse_pathway_metadata(path: Path) -> dict[str, str]:
    human: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        fields = line.split("\t")
        if len(fields) != 3:
            raise ValueError(f"Reactome pathway metadata row {line_number} is malformed")
        reactome_id, name, species = fields
        if species != REACTOME_SPECIES:
            continue
        if reactome_id in human:
            raise ValueError("duplicate human Reactome pathway identifier")
        human[reactome_id] = name
    if len(human) != 2_883:
        raise ValueError("unexpected human Reactome pathway inventory")
    return human


def _parse_gmt(path: Path) -> dict[str, tuple[str, tuple[str, ...]]]:
    pathways: dict[str, tuple[str, tuple[str, ...]]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        fields = line.split("\t")
        if len(fields) < 3:
            raise ValueError(f"Reactome GMT row {line_number} is malformed")
        name, reactome_id, *genes = fields
        if not reactome_id.startswith("R-HSA-"):
            continue
        if reactome_id in pathways or len(genes) != len(set(genes)):
            raise ValueError("duplicate Reactome pathway or member symbol")
        pathways[reactome_id] = (name, tuple(genes))
    if len(pathways) != 2_868:
        raise ValueError("unexpected human Reactome GMT inventory")
    return pathways


def _parse_parents(path: Path, human_ids: frozenset[str]) -> dict[str, tuple[str, ...]]:
    parents: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        fields = line.split("\t")
        if len(fields) != 2:
            raise ValueError(f"Reactome relation row {line_number} is malformed")
        parent, child = fields
        if parent not in human_ids or child not in human_ids:
            continue
        edge = (parent, child)
        if edge in seen:
            raise ValueError("duplicate human Reactome hierarchy edge")
        seen.add(edge)
        parents.setdefault(child, []).append(parent)
    if len(seen) != 2_899:
        raise ValueError("unexpected human Reactome hierarchy inventory")
    return {child: tuple(sorted(values)) for child, values in parents.items()}


def _candidate_projection(
    candidate: ExcludedCandidate,
    metadata: dict[str, str],
    gmt: dict[str, tuple[str, tuple[str, ...]]],
) -> dict[str, str]:
    if metadata.get(candidate.reactome_id) != candidate.expected_name:
        raise ValueError(f"Reactome excluded-candidate metadata mismatch: {candidate.reactome_id}")
    gmt_row = gmt.get(candidate.reactome_id)
    if gmt_row is None or gmt_row[0] != candidate.expected_name:
        raise ValueError(f"Reactome excluded-candidate GMT mismatch: {candidate.reactome_id}")
    return {
        "domain_id": candidate.domain_id,
        "reactome_id": candidate.reactome_id,
        "name": candidate.expected_name,
        "reason": candidate.reason,
    }


def _source_lock_projection() -> dict[str, object]:
    return {
        "declared_release": REACTOME_RELEASE,
        "release_attestation": (
            "release number is supplied by the local cache label; exact bytes are authoritative"
        ),
        "files": [
            {
                "relative_path": item.relative_path,
                "bytes": item.bytes,
                "sha256": f"sha256:{item.sha256}",
            }
            for item in REACTOME_FILES
        ],
    }


def _patient_axis_projection() -> dict[str, object]:
    return {
        "count": EXPECTED_PATIENT_COUNT,
        "ordering_policy": (
            "lexicographic KNCC patient-group order after complete T1/T2 selection and "
            "official versioned sample-type exclusions"
        ),
        "ordering_rule_digest": _digest(
            {
                "complete_pair_rule": "times exactly equal T1,T2",
                "order": "Unicode code-point ascending patient-group label",
                "sample_type_exclusion": "locked PDC biospecimen response mismatch groups",
                "source_parser": "import_kncc_longitudinal_gbm._strict_patients/1.0.0",
            }
        ),
        "identifiers_bundled": False,
        "identifier_or_identifier_hash_bundled": False,
    }


def build_artifact(
    cohort: base.Cohort,
    reactome_source_dir: Path,
) -> dict[str, object]:
    """Build a compact binding without consulting ``cohort.primary_delta`` values."""

    paths = verify_reactome_sources(reactome_source_dir)
    parent = longitudinal_gbm_catalog()
    parent_genes = tuple(feature.gene_symbol for feature in parent.features)
    expected_oracles: dict[str, object] = {
        "strict_t1_t2_pairs": EXPECTED_PATIENT_COUNT,
        "excluded_specimen_labels": 6,
        "excluded_patient_groups": 5,
        "official_versioned_biospecimen_records": 216,
        "official_versioned_file_manifest_records": 2_503,
        "hgnc_admitted_unique_approved_symbols": EXPECTED_GENE_COUNT,
        "hgnc_mapping_digest": PARENT_FEATURE_SPACE_DIGEST,
    }
    if (
        len(cohort.patient_groups) != EXPECTED_PATIENT_COUNT
        or tuple(cohort.patient_groups) != tuple(sorted(set(cohort.patient_groups)))
        or any(re.fullmatch(r"KNCC_GBM\d{4}", value) is None for value in cohort.patient_groups)
        or len(cohort.genes) != EXPECTED_GENE_COUNT
        or tuple(cohort.genes) != parent_genes
        or any(cohort.oracles.get(key) != value for key, value in expected_oracles.items())
    ):
        raise ValueError("PDC000514 patient/gene axis does not match the locked parent catalog")
    gene_index = {symbol: index for index, symbol in enumerate(parent_genes)}
    eligible = {feature.index for feature in parent.features if feature.eligible}

    metadata = _parse_pathway_metadata(paths["ReactomePathways.txt"])
    gmt = _parse_gmt(paths["gmt/ReactomePathways.gmt"])
    parents = _parse_parents(paths["ReactomePathwaysRelation.txt"], frozenset(metadata))
    excluded = [
        _candidate_projection(candidate, metadata, gmt) for candidate in EXCLUDED_CANDIDATES
    ]

    pathways: list[dict[str, object]] = []
    for panel_index, spec in enumerate(PANEL_SPECS):
        if metadata.get(spec.reactome_id) != spec.expected_name:
            raise ValueError(f"Reactome panel metadata mismatch: {spec.reactome_id}")
        gmt_row = gmt.get(spec.reactome_id)
        if gmt_row is None or gmt_row[0] != spec.expected_name:
            raise ValueError(f"Reactome panel GMT mismatch: {spec.reactome_id}")
        source_symbols = gmt_row[1]
        indices = tuple(
            sorted(gene_index[symbol] for symbol in source_symbols if symbol in gene_index)
        )
        eligible_indices = tuple(index for index in indices if index in eligible)
        mapping_fraction = len(indices) / len(source_symbols)
        if (
            not MIN_SOURCE_GENES <= len(source_symbols) <= MAX_SOURCE_GENES
            or len(indices) < MIN_MAPPED_GENES
            or mapping_fraction < MIN_MAPPING_FRACTION
        ):
            raise ValueError(f"Reactome panel assay-support gate failed: {spec.reactome_id}")
        pathways.append(
            {
                "panel_index": panel_index,
                "domain_id": spec.domain_id,
                "reactome_id": spec.reactome_id,
                "name": spec.expected_name,
                "species": REACTOME_SPECIES,
                "rationale": spec.rationale,
                "parent_ids": list(parents.get(spec.reactome_id, ())),
                "source_member_count": len(source_symbols),
                "source_member_digest": _digest(list(source_symbols)),
                "mapped_feature_count": len(indices),
                "mapping_fraction": round(mapping_fraction, 10),
                "eligible_feature_count": len(eligible_indices),
                "member_feature_indices": list(indices),
                "eligible_feature_indices": list(eligible_indices),
            }
        )

    source_bindings: dict[str, object] = {
        "pdc000514": {
            "study_id": "PDC000514",
            "study_version_uuid": base.PDC_STUDY_VERSION_UUID,
            "parent_model_id": parent.model_id,
            "parent_artifact_byte_digest": PARENT_ARTIFACT_BYTE_DIGEST,
            "parent_artifact_content_digest": PARENT_CONTENT_DIGEST,
            "parent_feature_space_digest": PARENT_FEATURE_SPACE_DIGEST,
            "parent_source_file_lock_digest": PARENT_SOURCE_FILE_LOCK_DIGEST,
            "versioned_source_manifest_digest": PARENT_SOURCE_MANIFEST_DIGEST,
        },
        "reactome": _source_lock_projection(),
    }
    selection = {
        "rule_id": SELECTION_RULE_ID,
        "rule": (
            "ten predeclared GBM mechanism slots, each bound to one exact physiological "
            "human Reactome stable ID; no patient transition value, recurrence direction, "
            "or fitted effect participates in selection"
        ),
        "assay_gate": {
            "identity_policy": "exact approved HGNC symbol intersection only",
            "minimum_source_genes": MIN_SOURCE_GENES,
            "maximum_source_genes": MAX_SOURCE_GENES,
            "minimum_mapped_genes": MIN_MAPPED_GENES,
            "minimum_mapping_fraction": MIN_MAPPING_FRACTION,
        },
        "excluded_candidates": excluded,
    }
    gene_order = list(parent_genes)
    document: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "profile_id": PROFILE_ID,
        "artifact_role": "source admission and feature binding only; no fitted pathway model",
        "patient_axis": _patient_axis_projection(),
        "gene_axis": {
            "count": len(gene_order),
            "ordering_basis": "exact ordered feature array in the locked parent protein model",
            "order_digest": _digest(gene_order),
            "symbols_not_duplicated": True,
        },
        "selection": selection,
        "pathways": pathways,
        "source_bindings": source_bindings,
        "projection_digests": {
            "source_binding_digest": _digest(source_bindings),
            "selection_candidate_digest": _digest(selection),
            "pathway_order_digest": _digest([item["reactome_id"] for item in pathways]),
            "pathway_membership_digest": _digest(
                [
                    {
                        "reactome_id": item["reactome_id"],
                        "source_member_digest": item["source_member_digest"],
                        "member_feature_indices": item["member_feature_indices"],
                        "eligible_feature_indices": item["eligible_feature_indices"],
                    }
                    for item in pathways
                ]
            ),
        },
        "provenance": {
            "pdc_article": (
                "Kim et al., Integrated proteogenomic characterization of glioblastoma "
                "evolution, Cancer Cell 42(3):358-377.e8 (2024)"
            ),
            "pdc_article_doi": "10.1016/j.ccell.2023.12.015",
            "pdc_license": "CC-BY-4.0",
            "reactome_resource": "Reactome human pathway annotation",
            "reactome_release": REACTOME_RELEASE,
            "reactome_annotation_license": "CC0-1.0",
            "transformation_notice": (
                "GLIO-PROTEOGEN retains only exact pathway identities, hierarchy parents, "
                "and de-identified HGNC feature indices. No Reactome graph edges, patient "
                "measurements, patient identifiers, or fitted pathway effects are bundled."
            ),
        },
        "limitations": [
            "This artifact is not a pathway-activity, pathway-flux, recurrence, or clinical model.",
            "Membership is annotation, not evidence of activation or causal direction.",
            "The ten mechanism slots are an explicit analyst-authored scope fixed before outcomes.",
            "Reactome release 97 is declared by the cache label; hashes, not filenames, "
            "lock bytes.",
            "Only exact HGNC symbol overlap is admitted; unmapped Reactome members remain absent.",
            "Patient ordering is reproducible from locked sources and policy but identifiers and "
            "identifier-derived hashes are intentionally not redistributed.",
        ],
    }
    return {**document, "artifact_digest": _digest(document)}


def _identifier_hashes(identifiers: Iterable[str]) -> set[bytes]:
    values: set[bytes] = set()
    for identifier in identifiers:
        for encoded in (
            identifier.encode(),
            json.dumps(identifier, separators=(",", ":")).encode(),
            identifier.encode() + b"\n",
        ):
            values.update(
                {
                    hashlib.md5(encoded, usedforsecurity=False).hexdigest().encode(),
                    hashlib.sha1(encoded, usedforsecurity=False).hexdigest().encode(),
                    hashlib.sha256(encoded).hexdigest().encode(),
                    hashlib.sha512(encoded).hexdigest().encode(),
                }
            )
    return values


def write_artifact(
    artifact: dict[str, object],
    destination: Path,
    *,
    patient_groups: tuple[str, ...],
) -> None:
    """Write canonical JSON after rejecting patient identifiers and direct hashes."""

    payload = _canonical_bytes(artifact)
    patient_tokens = {value.encode() for value in patient_groups}
    patient_tokens.update(f"{value}_T1".encode() for value in patient_groups)
    patient_tokens.update(f"{value}_T2".encode() for value in patient_groups)
    if any(token in payload for token in patient_tokens):
        raise ValueError("patient identifier leaked into Reactome source artifact")
    identifiers = tuple(patient_groups) + tuple(
        identifier
        for value in patient_groups
        for identifier in (f"{value}_T1", f"{value}_T2")
    )
    if any(token in payload.lower() for token in _identifier_hashes(identifiers)):
        raise ValueError("patient identifier hash leaked into Reactome source artifact")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)


def _default_output() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "glio_proteogen"
        / "research"
        / "longitudinal_gbm_reactome_transition"
        / "data"
        / "kncc_reactome_transition_source.v1.json"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdc-source-dir", type=Path, required=True)
    parser.add_argument("--hgnc-source", type=Path, required=True)
    parser.add_argument("--reactome-source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=_default_output())
    args = parser.parse_args()
    cohort = base.load_cohort(args.pdc_source_dir, args.hgnc_source)
    artifact = build_artifact(cohort, args.reactome_source_dir)
    write_artifact(artifact, args.output, patient_groups=cohort.patient_groups)
    print(
        json.dumps(
            {
                "artifact_digest": artifact["artifact_digest"],
                "bytes": args.output.stat().st_size,
                "output": str(args.output),
                "pathways": len(cast("list[object]", artifact["pathways"])),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
