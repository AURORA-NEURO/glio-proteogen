"""Fail-closed access to the Reactome V97 complex-transition pilot source."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from types import MappingProxyType
from typing import Final, Mapping, Never, cast

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

from .errors import ComplexTransitionSourceIntegrityError

ARTIFACT_RESOURCE: Final = "data/kncc_reactome_complex_transition_source.v1.json"
PROFILE_ID: Final = "kncc-reactome-complex-transition/1.0.0"
SCHEMA_VERSION: Final = "glio-proteogen.kncc-reactome-complex-transition-source/1.0.0"
SELECTION_RULE_ID: Final = "gbm-complex-pilot-reactome-v97/1.0.0"
EXPECTED_ARTIFACT_BYTES: Final = 96_157
EXPECTED_ARTIFACT_SHA256: Final = (
    "sha256:03fc954944af058d6f8d4ec629e16615555791642b7d91bc1d0d1455e1dbcf30"
)
EXPECTED_CONTENT_DIGEST: Final = (
    "sha256:5719f23be05e7b1603cd5ba56deb638f90300686ada786bec22a2201a7f99124"
)
EXPECTED_SOURCE_BINDING_DIGEST: Final = (
    "sha256:ca0b0625142f4640e789b334913e743bf4c24eb84984297c17795a8aa6d2819e"
)
EXPECTED_SELECTION_DIGEST: Final = (
    "sha256:6f7e7636bbebbe4cdfd4e91303ef58cdec1286c0de454f6df32a57d1740fa09b"
)
EXPECTED_COMPLEX_ORDER_DIGEST: Final = (
    "sha256:ee65348ef9688e26f9853053b2c46e469509a7c5b5ac9ea2cd09387af0a8db02"
)
EXPECTED_COMPLEX_MEMBERSHIP_DIGEST: Final = (
    "sha256:eebf2b92fdf60a7075cd625e26a74666c50df70f15e69e64e08c99b6628c3b27"
)
EXPECTED_PATHWAY_BINDING_DIGEST: Final = (
    "sha256:1f9500bf27bde7207c999186c9f4fbb362e9fa2ec2b66864fbc8dbaa20aca92a"
)
EXPECTED_OVERLAP_CONTROL_DIGEST: Final = (
    "sha256:674e3ebee67e4a6ac53b39bc5e51d9e27bccae15d81d0b84578a9554d450bc2b"
)
EXPECTED_GENE_ORDER_DIGEST: Final = (
    "sha256:db1c48250032a6ea68211dcfa388acc8fea5b874c13a75198b3eec15f0234c65"
)
EXPECTED_PATIENT_ORDER_RULE_DIGEST: Final = (
    "sha256:e9339a2020313ccd2c1ea7bf300ed8229ec9112d3e6f358aa1968762b761b4cf"
)
EXPECTED_PATIENT_COUNT: Final = 104
EXPECTED_GENE_COUNT: Final = 11_312
EXPECTED_COMPLEX_COUNT: Final = 28
EXPECTED_DOMAIN_COUNT: Final = 11
MIN_SOURCE_PROTEIN_GENES: Final = 3
MAX_SOURCE_PROTEIN_GENES: Final = 24
MIN_PARENT_FEATURES: Final = 3
MIN_ELIGIBLE_FEATURES: Final = 3
MIN_PARENT_MAPPING_FRACTION: Final = 0.50

EXPECTED_COMPLEXES: Final = (
    (
        "egfr_erbb_signaling",
        "R-HSA-179791",
        "EGF-like ligands:p-6Y-EGFR:GRB2:p-5Y-GAB1:PI3K [plasma membrane]",
    ),
    (
        "pdgf_signaling",
        "R-HSA-381954",
        "PDGF:Phospho-PDGFR receptor dimer:Nck [plasma membrane]",
    ),
    (
        "pi3k_akt",
        "R-HSA-114540",
        "RAC1:GTP,RAC2:GTP,RHOG:GTP:PI3K alpha [plasma membrane]",
    ),
    ("pi3k_akt", "R-HSA-437110", "PI3K beta [cytosol]"),
    ("mtor_energy_sensing", "R-HSA-377400", "mTORC1 [cytosol]"),
    ("mtor_energy_sensing", "R-HSA-198626", "mTORC2 [cytosol]"),
    ("mtor_energy_sensing", "R-HSA-380967", "LKB1:STRAD:MO25 [cytosol]"),
    (
        "raf_mapk",
        "R-HSA-5672728",
        "dephosphorylated inactive RAFS:YWHAB dimer [cytosol]",
    ),
    (
        "raf_mapk",
        "R-HSA-5674131",
        "WDR83:LAMTOR2:LAMTOR3:activated RAF:p-2S MAP2K:p-T,Y MAPK complex [endosome membrane]",
    ),
    (
        "wnt_pcp",
        "R-HSA-4551543",
        "N4GlycoAsn-PalmS WNT5A:ROR2:VANGL2 [plasma membrane]",
    ),
    ("wnt_pcp", "R-HSA-3858469", "pp-DVL:RAC:GTP [plasma membrane]"),
    ("wnt_pcp", "R-HSA-3858472", "ppDVL:DAAM1 [cytosol]"),
    ("wnt_pcp", "R-HSA-3965386", "ppDVL:DAAM1:PFN1 [cytosol]"),
    ("cell_cycle", "R-HSA-141410", "MCC:APC/C complex [cytosol]"),
    ("cell_cycle", "R-HSA-1363265", "PP2A [nucleoplasm]"),
    ("cell_cycle", "R-HSA-2484812", "p-Ac-Cohesin:PDS5:WAPAL [cytosol]"),
    (
        "cell_cycle",
        "R-HSA-2520845",
        "CDK1 Phosphorylated Condensin I [cytosol]",
    ),
    (
        "dna_repair",
        "R-HSA-5358511",
        "MLH1:PMS2:MSH2:MSH6:ATP:PCNA:DNA containing 1-2 base mismatch [nucleoplasm]",
    ),
    ("dna_repair", "R-HSA-3785763", "DNA DSBs:MRN [nucleoplasm]"),
    (
        "dna_repair",
        "R-HSA-75907",
        "PRKDC:XRCC5:XRCC6:DNA DSB ends [nucleoplasm]",
    ),
    ("hypoxia_vhl", "R-HSA-1234141", "VHL:EloB,C:CUL2:RBX1 [nucleoplasm]"),
    (
        "hypoxia_vhl",
        "R-HSA-1234101",
        "hydroxyPro-HIF-alpha:VHL:EloB,C:CUL2:RBX1 [nucleoplasm]",
    ),
    (
        "ecm_adhesion",
        "R-HSA-1604373",
        "MMP14:TIMP2:MMP2 intermediate form [plasma membrane]",
    ),
    (
        "ecm_adhesion",
        "R-HSA-2327790",
        "Integrin alpha5beta1:Fibronectin matrix [plasma membrane]",
    ),
    (
        "ecm_adhesion",
        "R-HSA-215995",
        "Integrin alpha7beta1:Laminin-211, 221, 411, 512, 521 [plasma membrane]",
    ),
    (
        "innate_inflammation",
        "R-HSA-202513",
        "CHUK:p-S177,S181-IKBKB:IKBKG [cytosol]",
    ),
    (
        "innate_inflammation",
        "R-HSA-1834956",
        "STING:TBK1:IRF3 [cytoplasmic vesicle membrane]",
    ),
    (
        "innate_inflammation",
        "R-HSA-9709857",
        "MAVS:TOMM70:HSP90:TBK1:IRF3 [mitochondrial outer membrane]",
    ),
)

EXPECTED_REACTOME_FILES: Final = (
    (
        "ComplexParticipantsPubMedIdentifiers_human.txt",
        3_690_987,
        "sha256:ad536e76c39772964a4e225a848acfce6c1e0f3232393d903bc59358a1c8987c",
    ),
    (
        "Complex_2_Pathway_human.txt",
        1_168_246,
        "sha256:99af18181f9e79f54a136235339142421d1a4ccaa7535f92abad63c0dfde95c3",
    ),
    (
        "ReactomePathways.txt",
        1_592_393,
        "sha256:f6d7a2bf89b5bcfe0250a0bc7f51bff94641447911712b8ff129f5b55e52df3a",
    ),
)


@dataclass(frozen=True, slots=True)
class ComplexMemberBinding:
    """One exact UniProt-to-HGNC-to-parent-feature projection."""

    gene_symbol: str
    hgnc_id: str
    source_accessions: tuple[str, ...]
    parent_feature_index: int | None
    parent_feature_eligible: bool


@dataclass(frozen=True, slots=True)
class ComplexPathwayBinding:
    """One exact row from the Reactome complex-to-pathway table."""

    pathway_id: str
    pathway_name: str
    top_level_pathway_id: str
    top_level_pathway_name: str


@dataclass(frozen=True, slots=True)
class ReactomeComplexBinding:
    """One selected complex annotation projected onto the KNCC protein axis."""

    complex_index: int
    domain_id: str
    ablation_family_id: str
    selection_tier: str
    reactome_id: str
    name: str
    compartment: str
    rationale: str
    source_participant_ids: tuple[str, ...]
    source_uniprot_accessions: tuple[str, ...]
    nonprotein_participant_ids: tuple[str, ...]
    participating_complex_ids: tuple[str, ...]
    pubmed_ids: tuple[int, ...]
    direct_pathway_bindings: tuple[ComplexPathwayBinding, ...]
    anchor_pathway: ComplexPathwayBinding
    member_bindings: tuple[ComplexMemberBinding, ...]
    member_feature_indices: tuple[int, ...]
    eligible_feature_indices: tuple[int, ...]
    member_panel_degrees: tuple[int, ...]
    inverse_degree_weights: tuple[float, ...]
    parent_feature_mapping_fraction: float
    selected_parent_complex_ids: tuple[str, ...]
    selected_child_complex_ids: tuple[str, ...]
    same_family_max_eligible_jaccard: float
    same_family_closest_complex_id: str | None

    @property
    def panel_index(self) -> int:
        """Artifact-compatible alias for the public complex index."""

        return self.complex_index

    @property
    def member_inverse_panel_degree_weights(self) -> tuple[float, ...]:
        """Artifact-compatible alias for downstream audit code."""

        return self.inverse_degree_weights


@dataclass(frozen=True, slots=True)
class ComplexAblationFamily:
    """One source-panel leave-family-out sensitivity definition."""

    family_index: int
    family_id: str
    complex_ids: tuple[str, ...]
    leave_family_out_retained_complex_ids: tuple[str, ...]
    ablation_interpretation: str


@dataclass(frozen=True, slots=True)
class ComplexTransitionSourceCatalog:
    """Immutable verified material for downstream model fitting and inference."""

    profile_id: str
    patient_count: int
    genes: tuple[str, ...]
    gene_index_by_symbol: Mapping[str, int]
    complexes: tuple[ReactomeComplexBinding, ...]
    complex_by_id: Mapping[str, ReactomeComplexBinding]
    complexes_by_domain: Mapping[str, tuple[ReactomeComplexBinding, ...]]
    ablation_families: tuple[ComplexAblationFamily, ...]
    family_by_id: Mapping[str, ComplexAblationFamily]
    artifact_byte_digest: str
    content_digest: str
    source_binding_digest: str
    selection_digest: str
    complex_order_digest: str
    complex_membership_digest: str
    pathway_binding_digest: str
    overlap_control_digest: str
    provenance: Mapping[str, str | int]
    limitations: tuple[str, ...]


def _fail(message: str) -> Never:
    raise ComplexTransitionSourceIntegrityError(message)


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


def _resource_bytes() -> bytes:
    return files(__package__).joinpath(ARTIFACT_RESOURCE).read_bytes()


def _object(value: object, name: str) -> dict[str, object]:
    if type(value) is not dict:
        _fail(f"complex source field {name!r} must be an object")
    return cast("dict[str, object]", value)


def _list(value: object, name: str) -> list[object]:
    if type(value) is not list:
        _fail(f"complex source field {name!r} must be an array")
    return cast("list[object]", value)


def _string(value: object, name: str) -> str:
    if type(value) is not str or not value:
        _fail(f"complex source field {name!r} must be a non-empty string")
    return value


def _integer(value: object, name: str) -> int:
    if type(value) is not int:
        _fail(f"complex source field {name!r} must be an integer")
    return value


def _finite(value: object, name: str) -> float:
    if type(value) not in {int, float}:
        _fail(f"complex source field {name!r} must be numeric")
    parsed = float(cast("int | float", value))
    if not math.isfinite(parsed):
        _fail(f"complex source field {name!r} must be finite")
    return parsed


def _string_array(value: object, name: str) -> tuple[str, ...]:
    values = tuple(_string(item, name) for item in _list(value, name))
    if len(values) != len(set(values)):
        _fail(f"complex source field {name!r} contains duplicates")
    return values


def _integer_array(value: object, name: str) -> tuple[int, ...]:
    return tuple(_integer(item, name) for item in _list(value, name))


def _parse_pathway(value: object, name: str) -> ComplexPathwayBinding:
    item = _object(value, name)
    expected_keys = {
        "pathway_id",
        "pathway_name",
        "top_level_pathway_id",
        "top_level_pathway_name",
    }
    if set(item) != expected_keys:
        _fail(f"complex source pathway shape mismatch: {name}")
    pathway = ComplexPathwayBinding(
        pathway_id=_string(item["pathway_id"], f"{name}.pathway_id"),
        pathway_name=_string(item["pathway_name"], f"{name}.pathway_name"),
        top_level_pathway_id=_string(item["top_level_pathway_id"], f"{name}.top_level_pathway_id"),
        top_level_pathway_name=_string(
            item["top_level_pathway_name"], f"{name}.top_level_pathway_name"
        ),
    )
    if (
        re.fullmatch(r"R-HSA-\d+", pathway.pathway_id) is None
        or re.fullmatch(r"R-HSA-\d+", pathway.top_level_pathway_id) is None
    ):
        _fail("complex source pathway identifier is malformed")
    return pathway


def _parse_members(value: object) -> tuple[ComplexMemberBinding, ...]:
    parent = longitudinal_gbm_catalog()
    result: list[ComplexMemberBinding] = []
    for offset, raw in enumerate(_list(value, "member_bindings")):
        item = _object(raw, f"member_bindings[{offset}]")
        index_value = item.get("parent_feature_index")
        if index_value is not None and type(index_value) is not int:
            _fail("complex source parent feature index must be integer or null")
        eligible = item.get("parent_feature_eligible")
        if type(eligible) is not bool:
            _fail("complex source parent feature eligibility must be boolean")
        binding = ComplexMemberBinding(
            gene_symbol=_string(item.get("gene_symbol"), "member gene_symbol"),
            hgnc_id=_string(item.get("hgnc_id"), "member hgnc_id"),
            source_accessions=_string_array(item.get("source_accessions"), "source_accessions"),
            parent_feature_index=index_value,
            parent_feature_eligible=eligible,
        )
        if not binding.source_accessions:
            _fail("complex source member has no UniProt accession")
        if binding.parent_feature_index is None:
            if binding.parent_feature_eligible:
                _fail("absent parent feature cannot be eligible")
        else:
            if not 0 <= binding.parent_feature_index < len(parent.features):
                _fail("complex source parent feature index is out of range")
            feature = parent.features[binding.parent_feature_index]
            if (
                feature.gene_symbol != binding.gene_symbol
                or feature.hgnc_id != binding.hgnc_id
                or feature.eligible != binding.parent_feature_eligible
            ):
                _fail("complex source member disagrees with the parent feature axis")
        result.append(binding)
    if len({item.gene_symbol for item in result}) != len(result) or len(
        {item.hgnc_id for item in result}
    ) != len(result):
        _fail("complex source member HGNC projection is duplicated")
    return tuple(result)


def _parse_complexes(raw_complexes: list[object]) -> tuple[ReactomeComplexBinding, ...]:
    if len(raw_complexes) != EXPECTED_COMPLEX_COUNT:
        _fail("complex source panel count mismatch")
    result: list[ReactomeComplexBinding] = []
    for panel_index, (raw, expected) in enumerate(
        zip(raw_complexes, EXPECTED_COMPLEXES, strict=True)
    ):
        item = _object(raw, f"complexes[{panel_index}]")
        identity = (
            _string(item.get("domain_id"), "domain_id"),
            _string(item.get("reactome_id"), "reactome_id"),
            _string(item.get("name"), "name"),
        )
        if identity != expected or item.get("panel_index") != panel_index:
            _fail("complex source frozen panel identity mismatch")
        if item.get("ablation_family_id") != identity[0]:
            _fail("complex source ablation family/domain mismatch")
        selection_tier = _string(item.get("selection_tier"), "selection_tier")
        if selection_tier not in {"domain_anchor", "supporting_mechanism"}:
            _fail("complex source selection tier is unsupported")
        compartment = _string(item.get("compartment"), "compartment")
        if not identity[2].endswith(f" [{compartment}]"):
            _fail("complex source compartment/name mismatch")

        participants = _string_array(item.get("source_participant_ids"), "participants")
        accessions = _string_array(item.get("source_uniprot_accessions"), "UniProt accessions")
        nonproteins = _string_array(item.get("nonprotein_participant_ids"), "nonproteins")
        if (
            item.get("source_participant_count") != len(participants)
            or item.get("source_participant_digest") != _digest(list(participants))
            or item.get("source_uniprot_accession_digest") != _digest(list(accessions))
            or tuple(
                value.removeprefix("UniProt:")
                for value in participants
                if value.startswith("UniProt:")
            )
            != accessions
            or tuple(value for value in participants if not value.startswith("UniProt:"))
            != nonproteins
        ):
            _fail("complex source participant projection mismatch")

        pathways = tuple(
            _parse_pathway(value, f"direct_pathway_bindings[{offset}]")
            for offset, value in enumerate(_list(item.get("direct_pathway_bindings"), "pathways"))
        )
        if not pathways or len(set(pathways)) != len(pathways):
            _fail("complex source direct pathway binding is empty or duplicated")
        anchor = _parse_pathway(item.get("anchor_pathway"), "anchor_pathway")
        if anchor not in pathways:
            _fail("complex source anchor is not an exact direct pathway binding")

        members = _parse_members(item.get("member_bindings"))
        if sorted(
            accession for member in members for accession in member.source_accessions
        ) != sorted(accessions):
            _fail("complex source UniProt/HGNC binding is incomplete")
        member_indices = _integer_array(item.get("member_feature_indices"), "member indices")
        eligible_indices = _integer_array(item.get("eligible_feature_indices"), "eligible indices")
        derived_members = tuple(
            member.parent_feature_index
            for member in members
            if member.parent_feature_index is not None
        )
        derived_eligible = tuple(
            member.parent_feature_index
            for member in members
            if member.parent_feature_index is not None and member.parent_feature_eligible
        )
        mapping_fraction = _finite(
            item.get("parent_feature_mapping_fraction"), "parent feature mapping fraction"
        )
        if (
            member_indices != derived_members
            or eligible_indices != derived_eligible
            or member_indices != tuple(sorted(set(member_indices)))
            or item.get("mapped_hgnc_gene_count") != len(members)
            or item.get("parent_feature_count") != len(member_indices)
            or item.get("eligible_feature_count") != len(eligible_indices)
            or not math.isclose(mapping_fraction, len(member_indices) / len(members), abs_tol=5e-11)
            or not MIN_SOURCE_PROTEIN_GENES <= len(members) <= MAX_SOURCE_PROTEIN_GENES
            or len(member_indices) < MIN_PARENT_FEATURES
            or len(eligible_indices) < MIN_ELIGIBLE_FEATURES
            or mapping_fraction < MIN_PARENT_MAPPING_FRACTION
        ):
            _fail("complex source assay-support projection mismatch")

        publications = _integer_array(item.get("pubmed_ids"), "PubMed identifiers")
        if len(publications) != len(set(publications)) or any(value < 1 for value in publications):
            _fail("complex source PubMed inventory is malformed")
        closest = item.get("same_family_closest_complex_id")
        if closest is not None and type(closest) is not str:
            _fail("complex source closest-family identifier must be string or null")
        result.append(
            ReactomeComplexBinding(
                complex_index=panel_index,
                domain_id=identity[0],
                ablation_family_id=identity[0],
                selection_tier=selection_tier,
                reactome_id=identity[1],
                name=identity[2],
                compartment=compartment,
                rationale=_string(item.get("rationale"), "rationale"),
                source_participant_ids=participants,
                source_uniprot_accessions=accessions,
                nonprotein_participant_ids=nonproteins,
                participating_complex_ids=_string_array(
                    item.get("participating_complex_ids"), "participating complexes"
                ),
                pubmed_ids=publications,
                direct_pathway_bindings=pathways,
                anchor_pathway=anchor,
                member_bindings=members,
                member_feature_indices=member_indices,
                eligible_feature_indices=eligible_indices,
                member_panel_degrees=_integer_array(
                    item.get("member_panel_degrees"), "member panel degrees"
                ),
                inverse_degree_weights=tuple(
                    _finite(value, "inverse membership degree")
                    for value in _list(
                        item.get("member_inverse_panel_degree_weights"),
                        "inverse membership degrees",
                    )
                ),
                parent_feature_mapping_fraction=mapping_fraction,
                selected_parent_complex_ids=_string_array(
                    item.get("selected_parent_complex_ids"), "selected parents"
                ),
                selected_child_complex_ids=_string_array(
                    item.get("selected_child_complex_ids"), "selected children"
                ),
                same_family_max_eligible_jaccard=_finite(
                    item.get("same_family_max_eligible_jaccard"), "family Jaccard"
                ),
                same_family_closest_complex_id=closest,
            )
        )
    return tuple(result)


def _validate_overlap(complexes: tuple[ReactomeComplexBinding, ...]) -> None:
    degree = Counter(index for item in complexes for index in item.member_feature_indices)
    selected_ids = {item.reactome_id for item in complexes}
    children: dict[str, set[str]] = {identifier: set() for identifier in selected_ids}
    for item in complexes:
        for parent in selected_ids.intersection(item.participating_complex_ids):
            children[parent].add(item.reactome_id)
    by_family: dict[str, list[ReactomeComplexBinding]] = {}
    for item in complexes:
        by_family.setdefault(item.ablation_family_id, []).append(item)
    for item in complexes:
        expected_degrees = tuple(degree[index] for index in item.member_feature_indices)
        expected_weights = tuple(round(1.0 / value, 10) for value in expected_degrees)
        expected_parents = tuple(sorted(selected_ids.intersection(item.participating_complex_ids)))
        expected_children = tuple(sorted(children[item.reactome_id]))
        overlaps: list[tuple[float, str]] = []
        current = set(item.eligible_feature_indices)
        for other in by_family[item.ablation_family_id]:
            if other.reactome_id == item.reactome_id:
                continue
            other_members = set(other.eligible_feature_indices)
            union = current | other_members
            overlaps.append(
                (0.0 if not union else len(current & other_members) / len(union), other.reactome_id)
            )
        expected_jaccard, expected_closest = (
            max(overlaps, key=lambda value: (value[0], value[1])) if overlaps else (0.0, None)
        )
        if (
            item.member_panel_degrees != expected_degrees
            or item.member_inverse_panel_degree_weights != expected_weights
            or item.selected_parent_complex_ids != expected_parents
            or item.selected_child_complex_ids != expected_children
            or not math.isclose(
                item.same_family_max_eligible_jaccard,
                round(expected_jaccard, 10),
                abs_tol=5e-11,
            )
            or item.same_family_closest_complex_id != expected_closest
        ):
            _fail("complex source overlap-control projection mismatch")


def _parse_families(
    raw: object,
    complexes: tuple[ReactomeComplexBinding, ...],
) -> tuple[ComplexAblationFamily, ...]:
    values = _list(raw, "ablation_families")
    domains = tuple(dict.fromkeys(item.domain_id for item in complexes))
    if len(values) != EXPECTED_DOMAIN_COUNT or len(domains) != EXPECTED_DOMAIN_COUNT:
        _fail("complex source ablation-family count mismatch")
    all_ids = tuple(item.reactome_id for item in complexes)
    result: list[ComplexAblationFamily] = []
    for index, (raw_family, domain) in enumerate(zip(values, domains, strict=True)):
        item = _object(raw_family, f"ablation_families[{index}]")
        complex_ids = _string_array(item.get("complex_ids"), "family complex IDs")
        retained = _string_array(
            item.get("leave_family_out_retained_complex_ids"), "family retained IDs"
        )
        expected_ids = tuple(value.reactome_id for value in complexes if value.domain_id == domain)
        expected_retained = tuple(value for value in all_ids if value not in set(expected_ids))
        if (
            item.get("family_index") != index
            or item.get("family_id") != domain
            or item.get("domain_id") != domain
            or complex_ids != expected_ids
            or retained != expected_retained
        ):
            _fail("complex source leave-family-out definition mismatch")
        result.append(
            ComplexAblationFamily(
                family_index=index,
                family_id=domain,
                complex_ids=complex_ids,
                leave_family_out_retained_complex_ids=retained,
                ablation_interpretation=_string(
                    item.get("ablation_interpretation"), "ablation interpretation"
                ),
            )
        )
    return tuple(result)


def _validate_axes(document: dict[str, object]) -> tuple[str, ...]:
    patient = _object(document.get("patient_axis"), "patient_axis")
    gene = _object(document.get("gene_axis"), "gene_axis")
    if (
        patient.get("count") != EXPECTED_PATIENT_COUNT
        or patient.get("ordering_rule_digest") != EXPECTED_PATIENT_ORDER_RULE_DIGEST
        or patient.get("identifiers_bundled") is not False
        or patient.get("identifier_or_identifier_hash_bundled") is not False
    ):
        _fail("complex source patient-axis mismatch")
    parent = longitudinal_gbm_catalog()
    genes = tuple(feature.gene_symbol for feature in parent.features)
    if (
        len(genes) != EXPECTED_GENE_COUNT
        or gene.get("count") != EXPECTED_GENE_COUNT
        or gene.get("order_digest") != EXPECTED_GENE_ORDER_DIGEST
        or gene.get("symbols_not_duplicated") is not True
        or _digest(list(genes)) != EXPECTED_GENE_ORDER_DIGEST
    ):
        _fail("complex source parent gene-axis mismatch")
    return genes


def _validate_source_bindings(bindings: dict[str, object]) -> None:
    pdc = _object(bindings.get("pdc000514"), "source_bindings.pdc000514")
    if pdc != {
        "study_id": "PDC000514",
        "study_version_uuid": "524d5116-b6de-4e36-892a-e35dba7d0170",
        "parent_model_id": "kncc-paired-protein-transition/1.0.0",
        "parent_artifact_byte_digest": PARENT_ARTIFACT_BYTE_DIGEST,
        "parent_artifact_content_digest": PARENT_CONTENT_DIGEST,
        "parent_feature_space_digest": PARENT_FEATURE_SPACE_DIGEST,
        "parent_source_file_lock_digest": PARENT_SOURCE_FILE_LOCK_DIGEST,
        "versioned_source_manifest_digest": PARENT_SOURCE_MANIFEST_DIGEST,
    }:
        _fail("complex source PDC000514 parent binding mismatch")
    hgnc = _object(bindings.get("hgnc"), "source_bindings.hgnc")
    if (
        hgnc.get("filename") != "hgnc_complete_set.txt"
        or hgnc.get("bytes") != 16_948_224
        or hgnc.get("sha256")
        != "sha256:854162118530e929f06249f3349465dd5fe0515fcccf0347f463e833609c1270"
        or hgnc.get("license") != "CC0-1.0"
    ):
        _fail("complex source HGNC binding mismatch")
    reactome = _object(bindings.get("reactome"), "source_bindings.reactome")
    observed_files = tuple(
        (
            _string(_object(value, "Reactome file").get("relative_path"), "relative path"),
            _integer(_object(value, "Reactome file").get("bytes"), "file bytes"),
            _string(_object(value, "Reactome file").get("sha256"), "file digest"),
        )
        for value in _list(reactome.get("files"), "Reactome files")
    )
    if (
        reactome.get("declared_release") != 97
        or reactome.get("annotation_license") != "CC0-1.0"
        or observed_files != EXPECTED_REACTOME_FILES
    ):
        _fail("complex source Reactome V97 binding mismatch")


def _validate_selection(
    selection: dict[str, object], complexes: tuple[ReactomeComplexBinding, ...]
) -> None:
    if (
        selection.get("rule_id") != SELECTION_RULE_ID
        or selection.get("panel_status") != "pilot"
        or "prespecified repository-authored pilot panel" not in str(selection.get("rule"))
        or "selected without reading abundance arrays during import"
        not in str(selection.get("rule"))
        or selection.get("outcome_independence_status")
        != "not demonstrated outcome-independent"
        or selection.get("selection_tiers") != ["domain_anchor", "supporting_mechanism"]
        or "exact direct Complex_2_Pathway rows only"
        not in str(selection.get("association_closure_policy"))
    ):
        _fail("complex source pilot selection policy mismatch")
    domains = _list(selection.get("domain_inventory"), "domain inventory")
    expected_domains = tuple(dict.fromkeys(item.domain_id for item in complexes))
    if len(domains) != EXPECTED_DOMAIN_COUNT:
        _fail("complex source domain inventory count mismatch")
    for index, (raw, expected_domain) in enumerate(zip(domains, expected_domains, strict=True)):
        item = _object(raw, f"domain_inventory[{index}]")
        if (
            item.get("domain_index") != index
            or item.get("domain_id") != expected_domain
            or item.get("complex_count")
            != sum(complex_.domain_id == expected_domain for complex_ in complexes)
            or "not exhaustive" not in str(item.get("coverage_role"))
        ):
            _fail("complex source pilot-domain declaration mismatch")
        if (
            sum(
                complex_.domain_id == expected_domain and complex_.selection_tier == "domain_anchor"
                for complex_ in complexes
            )
            != 1
        ):
            _fail("complex source pilot domain lacks one exact anchor")


def _validate_projection_digests(document: dict[str, object]) -> None:
    complexes = [
        _object(value, "complex") for value in _list(document.get("complexes"), "complexes")
    ]
    selection = _object(document.get("selection"), "selection")
    bindings = _object(document.get("source_bindings"), "source_bindings")
    families = _list(document.get("ablation_families"), "ablation_families")
    membership_projection = [
        {
            "reactome_id": item.get("reactome_id"),
            "source_participant_digest": item.get("source_participant_digest"),
            "source_uniprot_accession_digest": item.get("source_uniprot_accession_digest"),
            "member_feature_indices": item.get("member_feature_indices"),
            "eligible_feature_indices": item.get("eligible_feature_indices"),
            "member_panel_degrees": item.get("member_panel_degrees"),
            "member_inverse_panel_degree_weights": item.get("member_inverse_panel_degree_weights"),
        }
        for item in complexes
    ]
    pathway_projection = [
        {
            "reactome_id": item.get("reactome_id"),
            "anchor_pathway": item.get("anchor_pathway"),
            "direct_pathway_bindings": item.get("direct_pathway_bindings"),
        }
        for item in complexes
    ]
    overlap_projection = {
        "families": families,
        "nesting": [
            {
                "reactome_id": item.get("reactome_id"),
                "selected_parent_complex_ids": item.get("selected_parent_complex_ids"),
                "selected_child_complex_ids": item.get("selected_child_complex_ids"),
                "same_family_max_eligible_jaccard": item.get("same_family_max_eligible_jaccard"),
                "same_family_closest_complex_id": item.get("same_family_closest_complex_id"),
            }
            for item in complexes
        ],
    }
    computed = {
        "source_binding_digest": _digest(bindings),
        "selection_digest": _digest(selection),
        "complex_order_digest": _digest([item.get("reactome_id") for item in complexes]),
        "complex_membership_digest": _digest(membership_projection),
        "pathway_binding_digest": _digest(pathway_projection),
        "overlap_control_digest": _digest(overlap_projection),
    }
    expected = {
        "source_binding_digest": EXPECTED_SOURCE_BINDING_DIGEST,
        "selection_digest": EXPECTED_SELECTION_DIGEST,
        "complex_order_digest": EXPECTED_COMPLEX_ORDER_DIGEST,
        "complex_membership_digest": EXPECTED_COMPLEX_MEMBERSHIP_DIGEST,
        "pathway_binding_digest": EXPECTED_PATHWAY_BINDING_DIGEST,
        "overlap_control_digest": EXPECTED_OVERLAP_CONTROL_DIGEST,
    }
    declared = _object(document.get("projection_digests"), "projection_digests")
    if declared != computed or computed != expected:
        _fail("complex source projection digest mismatch")


@lru_cache(maxsize=1)
def complex_transition_source_catalog() -> ComplexTransitionSourceCatalog:
    """Load, fully verify, and freeze the bundled complex source artifact."""

    payload = _resource_bytes()
    byte_digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    if len(payload) != EXPECTED_ARTIFACT_BYTES or byte_digest != EXPECTED_ARTIFACT_SHA256:
        _fail("complex source artifact byte lock mismatch")
    try:
        parsed = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ComplexTransitionSourceIntegrityError(
            "complex source artifact is not valid JSON"
        ) from exc
    document = _object(parsed, "document")
    if _canonical_bytes(document) != payload:
        _fail("complex source artifact is not canonical JSON")
    content = dict(document)
    declared_content_digest = content.pop("artifact_digest", None)
    if (
        declared_content_digest != EXPECTED_CONTENT_DIGEST
        or _digest(content) != EXPECTED_CONTENT_DIGEST
    ):
        _fail("complex source artifact content digest mismatch")
    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("profile_id") != PROFILE_ID
        or document.get("artifact_role")
        != "source-locked complex membership and assay binding only; no fitted complex transition model"
    ):
        _fail("complex source top-level identity mismatch")

    _validate_projection_digests(document)
    genes = _validate_axes(document)
    bindings = _object(document.get("source_bindings"), "source_bindings")
    _validate_source_bindings(bindings)
    raw_complexes = _list(document.get("complexes"), "complexes")
    complexes = _parse_complexes(raw_complexes)
    _validate_overlap(complexes)
    families = _parse_families(document.get("ablation_families"), complexes)
    _validate_selection(_object(document.get("selection"), "selection"), complexes)

    by_id = {item.reactome_id: item for item in complexes}
    by_domain: dict[str, list[ReactomeComplexBinding]] = {}
    for item in complexes:
        by_domain.setdefault(item.domain_id, []).append(item)
    provenance_raw = _object(document.get("provenance"), "provenance")
    if not all(type(value) in {str, int} for value in provenance_raw.values()):
        _fail("complex source provenance must contain scalar values")
    limitations = _string_array(document.get("limitations"), "limitations")
    if (
        not any("not establish in-sample assembly" in value for value in limitations)
        or not any("essential subunits" in value for value in limitations)
        or not any("not an exhaustive GBM complexome" in value for value in limitations)
    ):
        _fail("complex source interpretation ceiling is incomplete")
    return ComplexTransitionSourceCatalog(
        profile_id=PROFILE_ID,
        patient_count=EXPECTED_PATIENT_COUNT,
        genes=genes,
        gene_index_by_symbol=MappingProxyType(
            {symbol: index for index, symbol in enumerate(genes)}
        ),
        complexes=complexes,
        complex_by_id=MappingProxyType(by_id),
        complexes_by_domain=MappingProxyType(
            {key: tuple(value) for key, value in by_domain.items()}
        ),
        ablation_families=families,
        family_by_id=MappingProxyType({item.family_id: item for item in families}),
        artifact_byte_digest=byte_digest,
        content_digest=EXPECTED_CONTENT_DIGEST,
        source_binding_digest=EXPECTED_SOURCE_BINDING_DIGEST,
        selection_digest=EXPECTED_SELECTION_DIGEST,
        complex_order_digest=EXPECTED_COMPLEX_ORDER_DIGEST,
        complex_membership_digest=EXPECTED_COMPLEX_MEMBERSHIP_DIGEST,
        pathway_binding_digest=EXPECTED_PATHWAY_BINDING_DIGEST,
        overlap_control_digest=EXPECTED_OVERLAP_CONTROL_DIGEST,
        provenance=MappingProxyType(cast("dict[str, str | int]", dict(provenance_raw))),
        limitations=limitations,
    )


__all__ = [
    "ComplexAblationFamily",
    "ComplexMemberBinding",
    "ComplexPathwayBinding",
    "ComplexTransitionSourceCatalog",
    "ReactomeComplexBinding",
    "complex_transition_source_catalog",
]
