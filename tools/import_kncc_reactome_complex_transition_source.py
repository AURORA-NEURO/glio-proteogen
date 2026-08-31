# ruff: noqa: E501, PLR0913, PLR2004, T201, TRY003
"""Build the source-locked KNCC/Reactome complex-transition pilot catalog.

The prespecified repository-authored pilot panel was informed by public glioma
biology and the PDC000514 source paper.  This importer validates the exact
protein/HGNC axes and Reactome V97 complex/pathway files, then projects that
panel without reading abundance arrays during import.  That procedural
separation is not demonstrated outcome independence.  The catalog does not
infer complex assembly, activity, essentiality, stoichiometry, or causality.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
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
    EXPECTED_HGNC_COMPLETE_SET_DIGEST as PARENT_HGNC_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm.catalog import (
    EXPECTED_SOURCE_FILE_LOCK_DIGEST as PARENT_SOURCE_FILE_LOCK_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm.catalog import (
    EXPECTED_SOURCE_MANIFEST_DIGEST as PARENT_SOURCE_MANIFEST_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm.catalog import longitudinal_gbm_catalog
from tools import import_kncc_longitudinal_gbm as base

PROFILE_ID: Final = "kncc-reactome-complex-transition/1.0.0"
SCHEMA_VERSION: Final = "glio-proteogen.kncc-reactome-complex-transition-source/1.0.0"
SELECTION_RULE_ID: Final = "gbm-complex-pilot-reactome-v97/1.0.0"
REACTOME_RELEASE: Final = 97
REACTOME_SPECIES: Final = "Homo sapiens"
EXPECTED_PATIENT_COUNT: Final = 104
EXPECTED_GENE_COUNT: Final = 11_312
EXPECTED_COMPLEX_ROWS: Final = 16_169
EXPECTED_COMPLEX_PATHWAY_ROWS: Final = 28_727
EXPECTED_HUMAN_PATHWAYS: Final = 2_883
EXPECTED_HGNC_ROWS: Final = 45_045
MIN_SOURCE_PROTEIN_GENES: Final = 3
MAX_SOURCE_PROTEIN_GENES: Final = 24
MIN_PARENT_FEATURES: Final = 3
MIN_ELIGIBLE_FEATURES: Final = 3
MIN_PARENT_MAPPING_FRACTION: Final = 0.50


@dataclass(frozen=True, slots=True)
class SourceFileLock:
    """One exact local source file consumed by this importer."""

    relative_path: str
    bytes: int
    sha256: str


REACTOME_FILES: Final = (
    SourceFileLock(
        "ComplexParticipantsPubMedIdentifiers_human.txt",
        3_690_987,
        "ad536e76c39772964a4e225a848acfce6c1e0f3232393d903bc59358a1c8987c",
    ),
    SourceFileLock(
        "Complex_2_Pathway_human.txt",
        1_168_246,
        "99af18181f9e79f54a136235339142421d1a4ccaa7535f92abad63c0dfde95c3",
    ),
    SourceFileLock(
        "ReactomePathways.txt",
        1_592_393,
        "f6d7a2bf89b5bcfe0250a0bc7f51bff94641447911712b8ff129f5b55e52df3a",
    ),
)
HGNC_FILE: Final = SourceFileLock(
    base.HGNC_SOURCE_FILENAME,
    base.HGNC_SOURCE_BYTES,
    base.HGNC_SOURCE_SHA256,
)


@dataclass(frozen=True, slots=True)
class ComplexSpec:
    """One repository-authored pilot complex and its exact Reactome anchor."""

    domain_id: str
    reactome_id: str
    expected_name: str
    anchor_pathway_id: str
    expected_anchor_name: str
    expected_top_level_id: str
    selection_tier: str
    rationale: str


PANEL_SPECS: Final = (
    ComplexSpec(
        "egfr_erbb_signaling",
        "R-HSA-179791",
        "EGF-like ligands:p-6Y-EGFR:GRB2:p-5Y-GAB1:PI3K [plasma membrane]",
        "R-HSA-180292",
        "GAB1 signalosome",
        "R-HSA-162582",
        "domain_anchor",
        "physiological ligand-associated EGFR/GAB1/PI3K annotation; mutant EGFR branches excluded",
    ),
    ComplexSpec(
        "pdgf_signaling",
        "R-HSA-381954",
        "PDGF:Phospho-PDGFR receptor dimer:Nck [plasma membrane]",
        "R-HSA-186763",
        "Downstream signal transduction",
        "R-HSA-162582",
        "domain_anchor",
        "physiological PDGF-receptor/adaptor annotation; disease-mutant PDGFR branches excluded",
    ),
    ComplexSpec(
        "pi3k_akt",
        "R-HSA-114540",
        "RAC1:GTP,RAC2:GTP,RHOG:GTP:PI3K alpha [plasma membrane]",
        "R-HSA-1257604",
        "PIP3 activates AKT signaling",
        "R-HSA-162582",
        "domain_anchor",
        "class-I PI3K-alpha annotation with small-GTPase context",
    ),
    ComplexSpec(
        "pi3k_akt",
        "R-HSA-437110",
        "PI3K beta [cytosol]",
        "R-HSA-1257604",
        "PIP3 activates AKT signaling",
        "R-HSA-162582",
        "supporting_mechanism",
        "PI3K-beta protein membership complements the alpha-family anchor",
    ),
    ComplexSpec(
        "mtor_energy_sensing",
        "R-HSA-377400",
        "mTORC1 [cytosol]",
        "R-HSA-165159",
        "MTOR signalling",
        "R-HSA-162582",
        "domain_anchor",
        "canonical Reactome mTORC1 membership projected without an activity claim",
    ),
    ComplexSpec(
        "mtor_energy_sensing",
        "R-HSA-198626",
        "mTORC2 [cytosol]",
        "R-HSA-1257604",
        "PIP3 activates AKT signaling",
        "R-HSA-162582",
        "supporting_mechanism",
        "mTORC2 membership captures a distinct PI3K/AKT-associated complex family",
    ),
    ComplexSpec(
        "mtor_energy_sensing",
        "R-HSA-380967",
        "LKB1:STRAD:MO25 [cytosol]",
        "R-HSA-380972",
        "Energy dependent regulation of mTOR by LKB1-AMPK",
        "R-HSA-162582",
        "supporting_mechanism",
        "energy-sensing LKB1/STRAD/MO25 membership is upstream context, not inferred flux",
    ),
    ComplexSpec(
        "raf_mapk",
        "R-HSA-5672728",
        "dephosphorylated inactive RAFS:YWHAB dimer [cytosol]",
        "R-HSA-5673000",
        "RAF activation",
        "R-HSA-162582",
        "domain_anchor",
        "physiological RAF-family membership; abundance does not assert the named phosphostate",
    ),
    ComplexSpec(
        "raf_mapk",
        "R-HSA-5674131",
        "WDR83:LAMTOR2:LAMTOR3:activated RAF:p-2S MAP2K:p-T,Y MAPK complex [endosome membrane]",
        "R-HSA-5674135",
        "MAP2K and MAPK activation",
        "R-HSA-162582",
        "supporting_mechanism",
        "endosomal RAF/MAP2K/MAPK membership; abundance cannot establish modification state",
    ),
    ComplexSpec(
        "wnt_pcp",
        "R-HSA-4551543",
        "N4GlycoAsn-PalmS WNT5A:ROR2:VANGL2 [plasma membrane]",
        "R-HSA-4086400",
        "PCP/CE pathway",
        "R-HSA-162582",
        "domain_anchor",
        "WNT5A/ROR2/VANGL2 PCP membership reflects a source-paper-informed GBM-evolution program",
    ),
    ComplexSpec(
        "wnt_pcp",
        "R-HSA-3858469",
        "pp-DVL:RAC:GTP [plasma membrane]",
        "R-HSA-4086400",
        "PCP/CE pathway",
        "R-HSA-162582",
        "supporting_mechanism",
        "DVL/RAC PCP branch membership, with no phosphostate or GTP-loading inference",
    ),
    ComplexSpec(
        "wnt_pcp",
        "R-HSA-3858472",
        "ppDVL:DAAM1 [cytosol]",
        "R-HSA-4086400",
        "PCP/CE pathway",
        "R-HSA-162582",
        "supporting_mechanism",
        "DVL/DAAM1 PCP membership retained separately from RAC and profilin branches",
    ),
    ComplexSpec(
        "wnt_pcp",
        "R-HSA-3965386",
        "ppDVL:DAAM1:PFN1 [cytosol]",
        "R-HSA-4086400",
        "PCP/CE pathway",
        "R-HSA-162582",
        "supporting_mechanism",
        "profilin-containing DVL/DAAM1 membership exposes nested-family sensitivity",
    ),
    ComplexSpec(
        "cell_cycle",
        "R-HSA-141410",
        "MCC:APC/C complex [cytosol]",
        "R-HSA-141430",
        "Inactivation of APC/C via direct inhibition of the APC/C complex",
        "R-HSA-1640170",
        "domain_anchor",
        "mitotic-checkpoint/APC-C membership; no proliferation rate is inferred",
    ),
    ComplexSpec(
        "cell_cycle",
        "R-HSA-1363265",
        "PP2A [nucleoplasm]",
        "R-HSA-69231",
        "Cyclin D associated events in G1",
        "R-HSA-1640170",
        "supporting_mechanism",
        "cell-cycle-associated PP2A family membership without substrate or activity claims",
    ),
    ComplexSpec(
        "cell_cycle",
        "R-HSA-2484812",
        "p-Ac-Cohesin:PDS5:WAPAL [cytosol]",
        "R-HSA-2500257",
        "Resolution of Sister Chromatid Cohesion",
        "R-HSA-1640170",
        "supporting_mechanism",
        "cohesin/PDS5/WAPAL membership complements checkpoint-complex evidence",
    ),
    ComplexSpec(
        "cell_cycle",
        "R-HSA-2520845",
        "CDK1 Phosphorylated Condensin I [cytosol]",
        "R-HSA-2514853",
        "Condensation of Prometaphase Chromosomes",
        "R-HSA-1640170",
        "supporting_mechanism",
        "condensin-I membership; protein abundance does not establish CDK1 phosphorylation",
    ),
    ComplexSpec(
        "dna_repair",
        "R-HSA-5358511",
        "MLH1:PMS2:MSH2:MSH6:ATP:PCNA:DNA containing 1-2 base mismatch [nucleoplasm]",
        "R-HSA-5358565",
        "Mismatch repair (MMR) directed by MSH2:MSH6 (MutSalpha)",
        "R-HSA-73894",
        "domain_anchor",
        "mismatch-repair protein membership; DNA/ATP participants are not protein evidence",
    ),
    ComplexSpec(
        "dna_repair",
        "R-HSA-3785763",
        "DNA DSBs:MRN [nucleoplasm]",
        "R-HSA-5693548",
        "Sensing of DNA Double Strand Breaks",
        "R-HSA-73894",
        "supporting_mechanism",
        "MRN protein membership represents a distinct double-strand-break branch",
    ),
    ComplexSpec(
        "dna_repair",
        "R-HSA-75907",
        "PRKDC:XRCC5:XRCC6:DNA DSB ends [nucleoplasm]",
        "R-HSA-5693571",
        "Nonhomologous End-Joining (NHEJ)",
        "R-HSA-73894",
        "supporting_mechanism",
        "DNA-PK/Ku protein membership represents the NHEJ branch",
    ),
    ComplexSpec(
        "hypoxia_vhl",
        "R-HSA-1234141",
        "VHL:EloB,C:CUL2:RBX1 [nucleoplasm]",
        "R-HSA-1234176",
        "Oxygen-dependent proline hydroxylation of Hypoxia-inducible Factor Alpha",
        "R-HSA-8953897",
        "domain_anchor",
        "VHL/Elo/CUL2/RBX1 membership; no oxygenation or ubiquitination state is inferred",
    ),
    ComplexSpec(
        "hypoxia_vhl",
        "R-HSA-1234101",
        "hydroxyPro-HIF-alpha:VHL:EloB,C:CUL2:RBX1 [nucleoplasm]",
        "R-HSA-1234176",
        "Oxygen-dependent proline hydroxylation of Hypoxia-inducible Factor Alpha",
        "R-HSA-8953897",
        "supporting_mechanism",
        "HIF-containing nested membership enables explicit family-overlap sensitivity",
    ),
    ComplexSpec(
        "ecm_adhesion",
        "R-HSA-1604373",
        "MMP14:TIMP2:MMP2 intermediate form [plasma membrane]",
        "R-HSA-1592389",
        "Activation of Matrix Metalloproteinases",
        "R-HSA-1474244",
        "domain_anchor",
        "MMP14/TIMP2/MMP2 membership represents a bounded ECM-remodelling branch",
    ),
    ComplexSpec(
        "ecm_adhesion",
        "R-HSA-2327790",
        "Integrin alpha5beta1:Fibronectin matrix [plasma membrane]",
        "R-HSA-1566977",
        "Fibronectin matrix formation",
        "R-HSA-1474244",
        "supporting_mechanism",
        "integrin/fibronectin membership complements metalloproteinase evidence",
    ),
    ComplexSpec(
        "ecm_adhesion",
        "R-HSA-215995",
        "Integrin alpha7beta1:Laminin-211, 221, 411, 512, 521 [plasma membrane]",
        "R-HSA-3000157",
        "Laminin interactions",
        "R-HSA-1474244",
        "supporting_mechanism",
        "integrin/laminin membership provides a second ECM-ligand family",
    ),
    ComplexSpec(
        "innate_inflammation",
        "R-HSA-202513",
        "CHUK:p-S177,S181-IKBKB:IKBKG [cytosol]",
        "R-HSA-168638",
        "NOD1/2 Signaling Pathway",
        "R-HSA-168256",
        "domain_anchor",
        "IKK-complex protein membership; abundance does not establish kinase activation",
    ),
    ComplexSpec(
        "innate_inflammation",
        "R-HSA-1834956",
        "STING:TBK1:IRF3 [cytoplasmic vesicle membrane]",
        "R-HSA-3270619",
        "IRF3-mediated induction of type I IFN",
        "R-HSA-168256",
        "supporting_mechanism",
        "STING/TBK1/IRF3 membership is retained as an innate-signalling branch",
    ),
    ComplexSpec(
        "innate_inflammation",
        "R-HSA-9709857",
        "MAVS:TOMM70:HSP90:TBK1:IRF3 [mitochondrial outer membrane]",
        "R-HSA-168928",
        "DDX58/IFIH1-mediated induction of interferon-alpha/beta",
        "R-HSA-168256",
        "supporting_mechanism",
        "MAVS/TOMM70/TBK1/IRF3 membership exposes overlap with the STING branch",
    ),
)


@dataclass(frozen=True, slots=True)
class ComplexRow:
    identifier: str
    name: str
    participants: tuple[str, ...]
    participating_complexes: tuple[str, ...]
    pubmed_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class PathwayLink:
    pathway_id: str
    top_level_pathway_id: str


@dataclass(frozen=True, slots=True)
class HgncProtein:
    symbol: str
    hgnc_id: str


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


def _verify_lock(root: Path, lock: SourceFileLock) -> Path:
    path = root / lock.relative_path
    if not path.is_file() or path.stat().st_size != lock.bytes or _file_digest(path) != lock.sha256:
        raise ValueError(f"source lock mismatch: {lock.relative_path}")
    return path


def verify_reactome_sources(source_dir: Path) -> dict[str, Path]:
    """Fail closed unless every consumed Reactome V97 file matches its lock."""

    return {lock.relative_path: _verify_lock(source_dir, lock) for lock in REACTOME_FILES}


def verify_hgnc_source(path: Path) -> Path:
    """Verify the exact HGNC complete-set bytes shared with the parent model."""

    if path.name != HGNC_FILE.relative_path:
        raise ValueError("HGNC source filename mismatch")
    verified = _verify_lock(path.parent, HGNC_FILE)
    if f"sha256:{HGNC_FILE.sha256}" != PARENT_HGNC_DIGEST:
        raise ValueError("HGNC lock differs from the parent protein catalog")
    return verified


def _read_tsv(path: Path, expected_header: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != expected_header:
            raise ValueError(f"source header mismatch: {path.name}")
        rows = [dict(row) for row in reader]
    if any(
        set(row) != set(expected_header) or any(value is None for value in row.values())
        for row in rows
    ):
        raise ValueError(f"malformed source row: {path.name}")
    return rows


def _split_source_ids(value: str, *, field: str) -> tuple[str, ...]:
    if value == "-":
        return ()
    values = tuple(value.split("|"))
    if not values or any(not item for item in values) or len(values) != len(set(values)):
        raise ValueError(f"duplicate or empty {field}")
    return values


def _parse_complexes(path: Path) -> dict[str, ComplexRow]:
    rows = _read_tsv(
        path,
        ("identifier", "name", "participants", "participatingComplex", "pubMedIdentifiers"),
    )
    if len(rows) != EXPECTED_COMPLEX_ROWS:
        raise ValueError("unexpected Reactome human-complex row count")
    result: dict[str, ComplexRow] = {}
    for row in rows:
        identifier = row["identifier"]
        if identifier in result or re.fullmatch(r"R-[A-Z]{3}-\d+", identifier) is None:
            raise ValueError("duplicate or malformed Reactome complex identifier")
        participants = _split_source_ids(row["participants"], field="complex participant")
        containers = _split_source_ids(row["participatingComplex"], field="container complex")
        publications = _split_source_ids(row["pubMedIdentifiers"], field="PubMed identifier")
        if any(not value.isdecimal() or int(value) < 1 for value in publications):
            raise ValueError("malformed Reactome PubMed identifier")
        result[identifier] = ComplexRow(
            identifier=identifier,
            name=row["name"],
            participants=participants,
            participating_complexes=containers,
            pubmed_ids=tuple(int(value) for value in publications),
        )
    return result


def _parse_pathway_links(path: Path) -> dict[str, tuple[PathwayLink, ...]]:
    rows = _read_tsv(path, ("complex", "pathway", "top_level_pathway"))
    if len(rows) != EXPECTED_COMPLEX_PATHWAY_ROWS:
        raise ValueError("unexpected Reactome complex-to-pathway row count")
    seen: set[tuple[str, str, str]] = set()
    grouped: dict[str, list[PathwayLink]] = {}
    for row in rows:
        key = (row["complex"], row["pathway"], row["top_level_pathway"])
        if key in seen or any(re.fullmatch(r"R-[A-Z]{3}-\d+", value) is None for value in key):
            raise ValueError("duplicate or malformed Reactome complex-to-pathway row")
        seen.add(key)
        grouped.setdefault(key[0], []).append(PathwayLink(key[1], key[2]))
    return {
        identifier: tuple(
            sorted(values, key=lambda item: (item.pathway_id, item.top_level_pathway_id))
        )
        for identifier, values in grouped.items()
    }


def _parse_pathway_metadata(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        fields = line.split("\t")
        if len(fields) != 3:
            raise ValueError(f"malformed Reactome pathway metadata row {line_number}")
        stable_id, name, species = fields
        if species != REACTOME_SPECIES:
            continue
        if stable_id in result:
            raise ValueError("duplicate human Reactome pathway identifier")
        result[stable_id] = name
    if len(result) != EXPECTED_HUMAN_PATHWAYS:
        raise ValueError("unexpected human Reactome pathway inventory")
    return result


def _parse_hgnc(path: Path) -> tuple[dict[str, tuple[HgncProtein, ...]], dict[str, int]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = tuple(reader.fieldnames or ())
        required = {"hgnc_id", "symbol", "status", "uniprot_ids"}
        if not required.issubset(fieldnames):
            raise ValueError("HGNC complete-set header is incompatible")
        rows = list(reader)
    if len(rows) != EXPECTED_HGNC_ROWS:
        raise ValueError("unexpected HGNC complete-set row count")
    accessions: dict[str, list[HgncProtein]] = {}
    approved = 0
    approved_with_accession = 0
    for row in rows:
        if row["status"] != "Approved":
            continue
        approved += 1
        item = HgncProtein(row["symbol"], row["hgnc_id"])
        values = tuple(value for value in row["uniprot_ids"].split("|") if value)
        if values:
            approved_with_accession += 1
        for accession in values:
            accessions.setdefault(accession, []).append(item)
    return (
        {key: tuple(values) for key, values in accessions.items()},
        {
            "rows": len(rows),
            "approved_rows": approved,
            "approved_rows_with_uniprot": approved_with_accession,
            "unique_uniprot_accessions": len(accessions),
            "ambiguous_uniprot_accessions": sum(len(values) > 1 for values in accessions.values()),
        },
    )


def _cohort_axis_guard(cohort: base.Cohort) -> None:
    parent = longitudinal_gbm_catalog()
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
        or tuple(cohort.genes) != tuple(feature.gene_symbol for feature in parent.features)
        or any(cohort.oracles.get(key) != value for key, value in expected_oracles.items())
    ):
        raise ValueError("PDC000514 patient/gene axis does not match the locked parent catalog")


def _source_lock_projection(hgnc_inventory: dict[str, int]) -> dict[str, object]:
    return {
        "pdc000514": {
            "study_id": "PDC000514",
            "study_version_uuid": base.PDC_STUDY_VERSION_UUID,
            "parent_model_id": "kncc-paired-protein-transition/1.0.0",
            "parent_artifact_byte_digest": PARENT_ARTIFACT_BYTE_DIGEST,
            "parent_artifact_content_digest": PARENT_CONTENT_DIGEST,
            "parent_feature_space_digest": PARENT_FEATURE_SPACE_DIGEST,
            "parent_source_file_lock_digest": PARENT_SOURCE_FILE_LOCK_DIGEST,
            "versioned_source_manifest_digest": PARENT_SOURCE_MANIFEST_DIGEST,
        },
        "hgnc": {
            "filename": HGNC_FILE.relative_path,
            "bytes": HGNC_FILE.bytes,
            "sha256": f"sha256:{HGNC_FILE.sha256}",
            "license": "CC0-1.0",
            "url": "https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt",
            "inventory": hgnc_inventory,
        },
        "reactome": {
            "declared_release": REACTOME_RELEASE,
            "release_attestation": (
                "release number is supplied by the local cache label; exact bytes are authoritative"
            ),
            "annotation_license": "CC0-1.0",
            "files": [
                {
                    "relative_path": item.relative_path,
                    "bytes": item.bytes,
                    "sha256": f"sha256:{item.sha256}",
                }
                for item in REACTOME_FILES
            ],
        },
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


def _compartment(name: str) -> str:
    match = re.search(r" \[([^\]]+)\]$", name)
    if match is None:
        raise ValueError("selected Reactome complex lacks one terminal compartment")
    return match.group(1)


def _base_accession(accession: str) -> str:
    match = re.fullmatch(r"(?P<base>[A-Z0-9]+)(?:-\d+)?", accession)
    if match is None:
        raise ValueError(f"unsupported UniProt accession syntax: {accession}")
    return match.group("base")


def _pathway_documents(
    links: tuple[PathwayLink, ...],
    metadata: dict[str, str],
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for link in links:
        pathway_name = metadata.get(link.pathway_id)
        top_name = metadata.get(link.top_level_pathway_id)
        if pathway_name is None or top_name is None:
            raise ValueError("Reactome pathway link has unresolved human metadata")
        result.append(
            {
                "pathway_id": link.pathway_id,
                "pathway_name": pathway_name,
                "top_level_pathway_id": link.top_level_pathway_id,
                "top_level_pathway_name": top_name,
            }
        )
    return result


def _build_complex_document(
    *,
    spec: ComplexSpec,
    panel_index: int,
    row: ComplexRow,
    links: tuple[PathwayLink, ...],
    metadata: dict[str, str],
    hgnc_by_accession: dict[str, tuple[HgncProtein, ...]],
) -> dict[str, object]:
    if row.name != spec.expected_name:
        raise ValueError(f"Reactome complex name mismatch: {spec.reactome_id}")
    pathway_documents = _pathway_documents(links, metadata)
    anchor = next(
        (
            item
            for item in pathway_documents
            if item["pathway_id"] == spec.anchor_pathway_id
            and item["top_level_pathway_id"] == spec.expected_top_level_id
        ),
        None,
    )
    if anchor is None or anchor["pathway_name"] != spec.expected_anchor_name:
        raise ValueError(f"Reactome complex anchor mismatch: {spec.reactome_id}")

    uniprot_accessions = tuple(
        participant.removeprefix("UniProt:")
        for participant in row.participants
        if participant.startswith("UniProt:")
    )
    if len(uniprot_accessions) != len(set(uniprot_accessions)):
        raise ValueError(f"duplicate selected-complex UniProt accession: {spec.reactome_id}")
    by_hgnc: dict[str, dict[str, object]] = {}
    for accession in uniprot_accessions:
        candidates = hgnc_by_accession.get(_base_accession(accession), ())
        if len(candidates) != 1:
            raise ValueError(f"selected-complex UniProt mapping is not unique: {accession}")
        mapped = candidates[0]
        binding = by_hgnc.setdefault(
            mapped.hgnc_id,
            {
                "gene_symbol": mapped.symbol,
                "hgnc_id": mapped.hgnc_id,
                "source_accessions": [],
            },
        )
        cast("list[str]", binding["source_accessions"]).append(accession)

    parent = longitudinal_gbm_catalog()
    parent_features = parent.features_by_symbol
    bindings: list[dict[str, object]] = []
    for binding in by_hgnc.values():
        symbol = cast("str", binding["gene_symbol"])
        parent_feature = parent_features.get(symbol)
        if parent_feature is not None and parent_feature.hgnc_id != binding["hgnc_id"]:
            raise ValueError("HGNC/parent feature authority disagreement")
        bindings.append(
            {
                **binding,
                "parent_feature_index": None if parent_feature is None else parent_feature.index,
                "parent_feature_eligible": False
                if parent_feature is None
                else parent_feature.eligible,
            }
        )
    bindings.sort(
        key=lambda item: (
            EXPECTED_GENE_COUNT
            if item["parent_feature_index"] is None
            else cast("int", item["parent_feature_index"]),
            cast("str", item["gene_symbol"]),
        )
    )
    member_indices = tuple(
        cast("int", binding["parent_feature_index"])
        for binding in bindings
        if binding["parent_feature_index"] is not None
    )
    eligible_indices = tuple(
        cast("int", binding["parent_feature_index"])
        for binding in bindings
        if binding["parent_feature_index"] is not None
        and binding["parent_feature_eligible"] is True
    )
    source_gene_count = len(bindings)
    parent_mapping_fraction = len(member_indices) / source_gene_count
    if (
        not MIN_SOURCE_PROTEIN_GENES <= source_gene_count <= MAX_SOURCE_PROTEIN_GENES
        or len(member_indices) < MIN_PARENT_FEATURES
        or len(eligible_indices) < MIN_ELIGIBLE_FEATURES
        or parent_mapping_fraction < MIN_PARENT_MAPPING_FRACTION
    ):
        raise ValueError(f"selected complex fails the frozen assay gate: {spec.reactome_id}")
    return {
        "panel_index": panel_index,
        "domain_id": spec.domain_id,
        "ablation_family_id": spec.domain_id,
        "selection_tier": spec.selection_tier,
        "reactome_id": spec.reactome_id,
        "name": spec.expected_name,
        "compartment": _compartment(spec.expected_name),
        "rationale": spec.rationale,
        "source_participant_ids": list(row.participants),
        "source_participant_count": len(row.participants),
        "source_participant_digest": _digest(list(row.participants)),
        "source_uniprot_accessions": list(uniprot_accessions),
        "source_uniprot_accession_digest": _digest(list(uniprot_accessions)),
        "nonprotein_participant_ids": [
            participant
            for participant in row.participants
            if not participant.startswith("UniProt:")
        ],
        "participating_complex_ids": list(row.participating_complexes),
        "pubmed_ids": list(row.pubmed_ids),
        "direct_pathway_bindings": pathway_documents,
        "anchor_pathway": anchor,
        "mapped_hgnc_gene_count": source_gene_count,
        "parent_feature_count": len(member_indices),
        "eligible_feature_count": len(eligible_indices),
        "parent_feature_mapping_fraction": round(parent_mapping_fraction, 10),
        "member_bindings": bindings,
        "member_feature_indices": list(member_indices),
        "eligible_feature_indices": list(eligible_indices),
    }


def _decorate_overlap(
    complexes: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    membership_degree = Counter(
        index for item in complexes for index in cast("list[int]", item["member_feature_indices"])
    )
    selected_ids = {cast("str", item["reactome_id"]) for item in complexes}
    children: dict[str, list[str]] = {identifier: [] for identifier in selected_ids}
    for item in complexes:
        identifier = cast("str", item["reactome_id"])
        for container in cast("list[str]", item["participating_complex_ids"]):
            if container in selected_ids:
                children[container].append(identifier)

    by_family: dict[str, list[dict[str, object]]] = {}
    for item in complexes:
        by_family.setdefault(cast("str", item["ablation_family_id"]), []).append(item)
    for item in complexes:
        indices = cast("list[int]", item["member_feature_indices"])
        item["member_panel_degrees"] = [membership_degree[index] for index in indices]
        item["member_inverse_panel_degree_weights"] = [
            round(1.0 / membership_degree[index], 10) for index in indices
        ]
        identifier = cast("str", item["reactome_id"])
        item["selected_parent_complex_ids"] = sorted(
            selected_ids.intersection(cast("list[str]", item["participating_complex_ids"]))
        )
        item["selected_child_complex_ids"] = sorted(children[identifier])
        eligible = set(cast("list[int]", item["eligible_feature_indices"]))
        overlaps: list[tuple[float, str]] = []
        for other in by_family[cast("str", item["ablation_family_id"])]:
            other_id = cast("str", other["reactome_id"])
            if other_id == identifier:
                continue
            other_eligible = set(cast("list[int]", other["eligible_feature_indices"]))
            union = eligible | other_eligible
            jaccard = 0.0 if not union else len(eligible & other_eligible) / len(union)
            overlaps.append((jaccard, other_id))
        if overlaps:
            maximum, closest = max(overlaps, key=lambda value: (value[0], value[1]))
            item["same_family_max_eligible_jaccard"] = round(maximum, 10)
            item["same_family_closest_complex_id"] = closest
        else:
            item["same_family_max_eligible_jaccard"] = 0.0
            item["same_family_closest_complex_id"] = None

    all_ids = [cast("str", item["reactome_id"]) for item in complexes]
    families: list[dict[str, object]] = []
    for family_index, (family_id, members) in enumerate(by_family.items()):
        member_ids = [cast("str", item["reactome_id"]) for item in members]
        retained = [identifier for identifier in all_ids if identifier not in set(member_ids)]
        families.append(
            {
                "family_index": family_index,
                "family_id": family_id,
                "domain_id": family_id,
                "complex_ids": member_ids,
                "leave_family_out_retained_complex_ids": retained,
                "ablation_interpretation": (
                    "source-panel family removal; not a biological knockout or causal intervention"
                ),
            }
        )
    return complexes, families


def build_artifact(
    cohort: base.Cohort, reactome_source_dir: Path, hgnc_source: Path
) -> dict[str, object]:
    """Build the pilot binding without reading either cohort abundance array."""

    _cohort_axis_guard(cohort)
    source_paths = verify_reactome_sources(reactome_source_dir)
    verified_hgnc = verify_hgnc_source(hgnc_source)
    complex_rows = _parse_complexes(source_paths["ComplexParticipantsPubMedIdentifiers_human.txt"])
    pathway_links = _parse_pathway_links(source_paths["Complex_2_Pathway_human.txt"])
    pathway_metadata = _parse_pathway_metadata(source_paths["ReactomePathways.txt"])
    hgnc_by_accession, hgnc_inventory = _parse_hgnc(verified_hgnc)

    ids = [spec.reactome_id for spec in PANEL_SPECS]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate selected Reactome complex identifier")
    domains = tuple(dict.fromkeys(spec.domain_id for spec in PANEL_SPECS))
    if any(
        sum(
            spec.domain_id == domain and spec.selection_tier == "domain_anchor"
            for spec in PANEL_SPECS
        )
        != 1
        for domain in domains
    ):
        raise ValueError("each pilot domain must have exactly one source-declared anchor")

    parent = longitudinal_gbm_catalog()
    complexes = [
        _build_complex_document(
            spec=spec,
            panel_index=index,
            row=complex_rows.get(spec.reactome_id)
            or (_ for _ in ()).throw(ValueError(f"missing Reactome complex: {spec.reactome_id}")),
            links=pathway_links.get(spec.reactome_id, ()),
            metadata=pathway_metadata,
            hgnc_by_accession=hgnc_by_accession,
        )
        for index, spec in enumerate(PANEL_SPECS)
    ]
    complexes, families = _decorate_overlap(complexes)
    domain_inventory = [
        {
            "domain_index": index,
            "domain_id": domain,
            "complex_count": sum(item["domain_id"] == domain for item in complexes),
            "coverage_role": "repository-authored pilot coverage; not exhaustive complexome coverage",
        }
        for index, domain in enumerate(domains)
    ]
    source_bindings = _source_lock_projection(hgnc_inventory)
    selection = {
        "rule_id": SELECTION_RULE_ID,
        "panel_status": "pilot",
        "rule": (
            "prespecified repository-authored pilot panel informed by public glioma biology "
            "and the PDC000514 source paper; selected without reading abundance arrays during "
            "import; not demonstrated outcome-independent; every selected complex must have "
            "an exact direct Complex_2_Pathway association to its declared anchor and pass "
            "the frozen PDC/HGNC assay-support gate"
        ),
        "domain_basis": (
            "public glioma biology represented by the prior repository GBM pathway panel "
            "and the WNT/PCP transition program reported in the PDC000514 source paper"
        ),
        "outcome_independence_status": "not demonstrated outcome-independent",
        "association_closure_policy": (
            "exact direct Complex_2_Pathway rows only; top-level assignments are copied from "
            "that source table and no inferred transitive pathway membership is added"
        ),
        "physiology_policy": (
            "prefer physiological complexes; exclude mutation-, fusion-, inhibitor-, and "
            "treatment-specific complexes unless a future version declares compatible evidence"
        ),
        "selection_tiers": ["domain_anchor", "supporting_mechanism"],
        "assay_gate": {
            "uniprot_policy": (
                "retain exact source accessions; strip only a terminal numeric isoform suffix "
                "for exact unique HGNC UniProt lookup"
            ),
            "minimum_source_protein_genes": MIN_SOURCE_PROTEIN_GENES,
            "maximum_source_protein_genes": MAX_SOURCE_PROTEIN_GENES,
            "minimum_parent_features": MIN_PARENT_FEATURES,
            "minimum_eligible_parent_features": MIN_ELIGIBLE_FEATURES,
            "minimum_parent_mapping_fraction": MIN_PARENT_MAPPING_FRACTION,
        },
        "domain_inventory": domain_inventory,
    }
    membership_projection = [
        {
            "reactome_id": item["reactome_id"],
            "source_participant_digest": item["source_participant_digest"],
            "source_uniprot_accession_digest": item["source_uniprot_accession_digest"],
            "member_feature_indices": item["member_feature_indices"],
            "eligible_feature_indices": item["eligible_feature_indices"],
            "member_panel_degrees": item["member_panel_degrees"],
            "member_inverse_panel_degree_weights": item["member_inverse_panel_degree_weights"],
        }
        for item in complexes
    ]
    pathway_projection = [
        {
            "reactome_id": item["reactome_id"],
            "anchor_pathway": item["anchor_pathway"],
            "direct_pathway_bindings": item["direct_pathway_bindings"],
        }
        for item in complexes
    ]
    overlap_projection = {
        "families": families,
        "nesting": [
            {
                "reactome_id": item["reactome_id"],
                "selected_parent_complex_ids": item["selected_parent_complex_ids"],
                "selected_child_complex_ids": item["selected_child_complex_ids"],
                "same_family_max_eligible_jaccard": item["same_family_max_eligible_jaccard"],
                "same_family_closest_complex_id": item["same_family_closest_complex_id"],
            }
            for item in complexes
        ],
    }
    document: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "profile_id": PROFILE_ID,
        "artifact_role": (
            "source-locked complex membership and assay binding only; no fitted complex transition model"
        ),
        "patient_axis": _patient_axis_projection(),
        "gene_axis": {
            "count": EXPECTED_GENE_COUNT,
            "ordering_basis": "exact ordered feature array in the locked parent protein model",
            "order_digest": _digest([feature.gene_symbol for feature in parent.features]),
            "symbols_not_duplicated": True,
        },
        "selection": selection,
        "complexes": complexes,
        "ablation_families": families,
        "source_bindings": source_bindings,
        "projection_digests": {
            "source_binding_digest": _digest(source_bindings),
            "selection_digest": _digest(selection),
            "complex_order_digest": _digest(ids),
            "complex_membership_digest": _digest(membership_projection),
            "pathway_binding_digest": _digest(pathway_projection),
            "overlap_control_digest": _digest(overlap_projection),
        },
        "provenance": {
            "pdc_article": (
                "Kim et al., Integrated proteogenomic characterization of glioblastoma "
                "evolution, Cancer Cell 42(3):358-377.e8 (2024)"
            ),
            "pdc_article_doi": "10.1016/j.ccell.2023.12.015",
            "pdc_article_pmid": "38215747",
            "pdc_license": "CC-BY-4.0",
            "reactome_resource": "Reactome human complex and complex-to-pathway annotation",
            "reactome_release": REACTOME_RELEASE,
            "reactome_annotation_license": "CC0-1.0",
            "hgnc_resource": "HGNC complete set",
            "hgnc_license": "CC0-1.0",
            "transformation_notice": (
                "GLIO-PROTEOGEN retains exact selected complex identities, participant IDs, "
                "direct pathway annotations, publication IDs, and de-identified parent-feature "
                "indices. No patient measurements, identifiers, identifier hashes, fitted "
                "effects, or individual predictions are bundled."
            ),
        },
        "limitations": [
            "Research use only; this pilot artifact is not clinically validated or prescriptive.",
            "The prespecified repository-authored pilot panel was informed by public glioma biology and the PDC000514 source paper, selected without reading abundance arrays during import, and is not demonstrated outcome-independent.",
            "Reactome complex membership does not establish in-sample assembly, abundance, activity, flux, or causality.",
            "Reactome membership does not identify essential subunits or quantitative stoichiometry.",
            "Names may encode phosphorylation, nucleotide, ligand, or localization states that protein abundance cannot establish.",
            "The eleven represented domains are repository-authored pilot coverage, not an exhaustive GBM complexome.",
            "Overlapping and nested complexes are retained transparently; inverse membership degree and leave-family-out definitions support sensitivity analysis.",
            "Only exact unique HGNC UniProt mappings and the locked PDC000514 feature intersection are admitted.",
            "Patient ordering is reproducible from locked policy, but identifiers and identifier-derived hashes are not redistributed.",
        ],
    }
    return {**document, "artifact_digest": _digest(document)}


def _identifier_hashes(identifiers: Iterable[str]) -> set[bytes]:
    values: set[bytes] = set()
    for identifier in identifiers:
        encoded = identifier.encode()
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
    """Write canonical JSON after rejecting direct patient identifiers and hashes."""

    payload = _canonical_bytes(artifact)
    identifiers = tuple(patient_groups) + tuple(
        identifier
        for patient in patient_groups
        for identifier in (f"{patient}_T1", f"{patient}_T2")
    )
    if any(identifier.encode() in payload for identifier in identifiers):
        raise ValueError("patient identifier leaked into complex source artifact")
    lowered = payload.lower()
    if any(token in lowered for token in _identifier_hashes(identifiers)):
        raise ValueError("patient identifier hash leaked into complex source artifact")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)


def _default_output() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "glio_proteogen"
        / "research"
        / "longitudinal_gbm_complex_transition"
        / "data"
        / "kncc_reactome_complex_transition_source.v1.json"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdc-source-dir", type=Path, required=True)
    parser.add_argument("--hgnc-source", type=Path, required=True)
    parser.add_argument("--reactome-source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=_default_output())
    args = parser.parse_args()
    cohort = base.load_cohort(args.pdc_source_dir, args.hgnc_source)
    artifact = build_artifact(cohort, args.reactome_source_dir, args.hgnc_source)
    write_artifact(artifact, args.output, patient_groups=cohort.patient_groups)
    print(
        json.dumps(
            {
                "artifact_digest": artifact["artifact_digest"],
                "bytes": args.output.stat().st_size,
                "complexes": len(cast("list[object]", artifact["complexes"])),
                "domains": len(
                    cast(
                        "list[object]",
                        cast("dict[str, object]", artifact["selection"])["domain_inventory"],
                    )
                ),
                "output": str(args.output),
                "sha256": "sha256:" + hashlib.sha256(args.output.read_bytes()).hexdigest(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
