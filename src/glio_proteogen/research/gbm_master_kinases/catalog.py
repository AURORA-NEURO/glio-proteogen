"""Digest-locked access to SPHINKS/MK Supplementary Tables 5a/d/e."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from types import MappingProxyType
from typing import Final, Mapping, cast

from .canonical import sha256_digest
from .errors import CatalogIntegrityError

CATALOG_RESOURCE: Final = "data/sphinks_master_kinase_catalog.v1.json"
SOURCE_SHA256: Final = "sha256:865a2db1ec99dcf047d6ff56b313a21607b840e5239bb9184739f6f6f217fb88"
EXPECTED_CATALOG_ARTIFACT_DIGEST: Final = (
    "sha256:a9e89cc55133386223dff130cc0162fb3ff18152af8a8ca875e9cbd662143e60"
)
EXPECTED_CATALOG_CONTENT_DIGEST: Final = (
    "sha256:beb705a4d5ca31aa6f5f6ee24e9689fc3d7bc41e04cd54ee0cf095d8ae2f9572"
)
EXPECTED_BACKGROUND_TUPLE_DIGEST: Final = (
    "sha256:1b2c46dde1965729f913f0bbed61d2ce2e98f029125304f6d417bdb679f406ba"
)
EXPECTED_BACKGROUND_LABEL_DIGEST: Final = (
    "sha256:4cf8731253177a1e794145dc0d9810165a6c9546d3a0febaf751e09bb233b437"
)
EXPECTED_MASTER_KINASE_DIGEST: Final = (
    "sha256:cf723900c41a0d0c42347658bc9fe618556487f86eff88b3567b1566e0fd5f4c"
)
EXPECTED_SIGNATURE_EDGE_DIGEST: Final = (
    "sha256:2cba909989a33438e5d81c551015300b5de7553fa7275b1d5dffde6bf134b345"
)
EXPECTED_ALIAS_DIGEST: Final = (
    "sha256:760275fab6f6a9aea3f0866fbfffafc9efadcb8ce683ece6e1935409ed97beeb"
)
EXPECTED_BACKGROUND_TUPLE_COUNT: Final = 34_098
EXPECTED_BACKGROUND_LABEL_COUNT: Final = 30_175
EXPECTED_EDGE_COUNTS: Final = {"GPM": 1_256, "MTC": 34, "NEU": 467, "PPR": 1_803}
EXPECTED_UNIQUE_TARGET_COUNTS: Final = {"GPM": 557, "MTC": 33, "NEU": 232, "PPR": 1_006}
EXPECTED_KINASE_COUNTS: Final = {"GPM": 9, "MTC": 1, "NEU": 7, "PPR": 7}
EXPECTED_REPEATED_KINASE_SITE_EXTRA_ROWS: Final = 225


@dataclass(frozen=True, slots=True)
class BackgroundTuple:
    source_site_label: str
    refseq_id: str
    peptide: str
    source_protein_labels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceReference:
    kinase_activity_mww_score: float
    log2fc_activity_subtype_vs_others: float
    p_value: float
    modality_mww_scores: Mapping[str, Mapping[str, float]]


@dataclass(frozen=True, slots=True)
class SignatureEdge:
    source_row_id: str
    source_row_number: int
    subtype: str
    source_kinase_label: str
    hgnc_symbol: str
    source_site_label: str
    source_target_protein_label: str
    svm_probability: float
    rho_spearman: float
    known_phosphosite_plus_substrate: bool


@dataclass(frozen=True, slots=True)
class MasterKinase:
    source_row_id: str
    source_row_number: int
    subtype: str
    source_kinase_label: str
    hgnc_symbol: str
    source_reference: SourceReference


@dataclass(frozen=True, slots=True)
class MasterKinaseCatalog:
    background_tuples: tuple[BackgroundTuple, ...]
    background_labels: frozenset[str]
    masters: tuple[MasterKinase, ...]
    edges: tuple[SignatureEdge, ...]
    edges_by_kinase: Mapping[str, tuple[SignatureEdge, ...]]
    aliases: Mapping[str, str]
    artifact_digest: str
    content_digest: str
    background_tuple_digest: str
    background_label_digest: str
    master_kinase_digest: str
    signature_edge_digest: str
    alias_digest: str
    source_sha256: str
    source_url: str
    article_doi: str
    article_title: str
    article_authors: str
    source_license: str
    source_license_url: str
    transformation_notice: str


def _resource_bytes() -> bytes:
    return files(__package__).joinpath(CATALOG_RESOURCE).read_bytes()


def _fail(message: str) -> None:
    raise CatalogIntegrityError(message)


@lru_cache(maxsize=1)
def master_kinase_catalog() -> MasterKinaseCatalog:  # noqa: PLR0915
    raw_bytes = _resource_bytes()
    artifact_digest = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
    if artifact_digest != EXPECTED_CATALOG_ARTIFACT_DIGEST:
        _fail("SPHINKS master-kinase catalog artifact digest mismatch")
    try:
        document = cast("dict[str, object]", json.loads(raw_bytes))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CatalogIntegrityError("SPHINKS master-kinase catalog is not valid JSON") from error
    content_digest = sha256_digest(document)
    if content_digest != EXPECTED_CATALOG_CONTENT_DIGEST:
        _fail("SPHINKS master-kinase catalog canonical content digest mismatch")
    if document.get("schema_version") != "sphinks-gbm-master-kinase-catalog/1.0.0":
        _fail("unsupported SPHINKS master-kinase catalog schema")
    source = cast("dict[str, object]", document["source"])
    if (
        source.get("source_sha256") != SOURCE_SHA256
        or source.get("license") != "CC-BY-4.0"
        or source.get("license_url") != "https://creativecommons.org/licenses/by/4.0/"
        or source.get("copyright") != "© The Author(s) 2023"
        or source.get("article_authors") != "Migliozzi et al."
    ):
        _fail("SPHINKS source provenance lock mismatch")
    background = cast("dict[str, object]", document["background"])
    labels = cast("list[str]", background["labels"])
    tuple_documents = cast("list[dict[str, object]]", background["tuples"])
    if (
        background.get("tuple_count") != EXPECTED_BACKGROUND_TUPLE_COUNT
        or len(tuple_documents) != EXPECTED_BACKGROUND_TUPLE_COUNT
        or background.get("label_count") != EXPECTED_BACKGROUND_LABEL_COUNT
        or len(labels) != EXPECTED_BACKGROUND_LABEL_COUNT
        or labels != sorted(set(labels))
    ):
        _fail("SPHINKS Table 5a background inventory mismatch")
    tuple_projection = [
        [item["source_site_label"], item["refseq_id"], item["peptide"]] for item in tuple_documents
    ]
    if len({tuple(item) for item in tuple_projection}) != EXPECTED_BACKGROUND_TUPLE_COUNT:
        _fail("SPHINKS Table 5a background contains duplicate source tuples")
    tuple_digest = sha256_digest(tuple_projection)
    label_digest = sha256_digest(labels)
    if (
        tuple_digest != EXPECTED_BACKGROUND_TUPLE_DIGEST
        or background.get("tuple_digest") != EXPECTED_BACKGROUND_TUPLE_DIGEST
        or label_digest != EXPECTED_BACKGROUND_LABEL_DIGEST
        or background.get("label_digest") != EXPECTED_BACKGROUND_LABEL_DIGEST
    ):
        _fail("SPHINKS Table 5a background semantic digest mismatch")
    background_tuples = tuple(
        BackgroundTuple(
            source_site_label=cast("str", item["source_site_label"]),
            refseq_id=cast("str", item["refseq_id"]),
            peptide=cast("str", item["peptide"]),
            source_protein_labels=tuple(cast("list[str]", item["source_protein_labels"])),
        )
        for item in tuple_documents
    )
    normalization = cast("dict[str, object]", document["kinase_label_normalization"])
    alias_documents = cast("list[dict[str, str]]", normalization["aliases"])
    alias_digest = sha256_digest(alias_documents)
    aliases = MappingProxyType(
        {item["source_kinase_label"]: item["hgnc_symbol"] for item in alias_documents}
    )
    if (
        alias_digest != EXPECTED_ALIAS_DIGEST
        or normalization.get("mapping_digest") != EXPECTED_ALIAS_DIGEST
        or len(aliases) != 24
        or len(set(aliases.values())) != 24
    ):
        _fail("SPHINKS kinase-label normalization lock mismatch")
    master_documents = cast("list[dict[str, object]]", document["master_kinases"])
    edge_documents = cast("list[dict[str, object]]", document["signature_edges"])
    source_digests = cast("dict[str, object]", document["source_digests"])
    if (
        sha256_digest(master_documents) != EXPECTED_MASTER_KINASE_DIGEST
        or source_digests.get("master_kinase_digest") != EXPECTED_MASTER_KINASE_DIGEST
        or sha256_digest(edge_documents) != EXPECTED_SIGNATURE_EDGE_DIGEST
        or source_digests.get("signature_edge_digest") != EXPECTED_SIGNATURE_EDGE_DIGEST
    ):
        _fail("SPHINKS Table 5d/e semantic digest mismatch")
    masters = tuple(
        MasterKinase(
            source_row_id=cast("str", item["source_row_id"]),
            source_row_number=cast("int", item["source_row_number"]),
            subtype=cast("str", item["subtype"]),
            source_kinase_label=cast("str", item["source_kinase_label"]),
            hgnc_symbol=cast("str", item["hgnc_symbol"]),
            source_reference=SourceReference(
                kinase_activity_mww_score=cast("float", item["kinase_activity_mww_score"]),
                log2fc_activity_subtype_vs_others=cast(
                    "float", item["log2fc_activity_subtype_vs_others"]
                ),
                p_value=cast("float", item["p_value"]),
                modality_mww_scores=MappingProxyType(
                    {
                        modality: MappingProxyType(dict(values))
                        for modality, values in cast(
                            "dict[str, dict[str, float]]",
                            item["modality_mww_scores"],
                        ).items()
                    }
                ),
            ),
        )
        for item in master_documents
    )
    if (
        len(masters) != 24
        or len({item.hgnc_symbol for item in masters}) != 24
        or Counter(item.subtype for item in masters) != Counter(EXPECTED_KINASE_COUNTS)
    ):
        _fail("SPHINKS Table 5e master-kinase inventory mismatch")
    edges = tuple(
        SignatureEdge(
            source_row_id=cast("str", item["source_row_id"]),
            source_row_number=cast("int", item["source_row_number"]),
            subtype=cast("str", item["subtype"]),
            source_kinase_label=cast("str", item["source_kinase_label"]),
            hgnc_symbol=cast("str", item["hgnc_symbol"]),
            source_site_label=cast("str", item["source_site_label"]),
            source_target_protein_label=cast("str", item["source_target_protein_label"]),
            svm_probability=cast("float", item["svm_probability"]),
            rho_spearman=cast("float", item["rho_spearman"]),
            known_phosphosite_plus_substrate=cast("bool", item["known_phosphosite_plus_substrate"]),
        )
        for item in edge_documents
    )
    if len({item.source_row_id for item in edges}) != len(edges):
        _fail("SPHINKS Table 5d source row identities are not unique")
    edge_counts = Counter(item.subtype for item in edges)
    unique_counts = {
        subtype: len({item.source_site_label for item in edges if item.subtype == subtype})
        for subtype in EXPECTED_EDGE_COUNTS
    }
    if dict(edge_counts) != EXPECTED_EDGE_COUNTS or unique_counts != EXPECTED_UNIQUE_TARGET_COUNTS:
        _fail("SPHINKS Table 5d subtype edge inventory mismatch")
    if any(item.source_site_label not in labels for item in edges):
        _fail("SPHINKS Table 5d target is absent from pinned Table 5a background")
    pair_counts = Counter((item.hgnc_symbol, item.source_site_label) for item in edges)
    if sum(count - 1 for count in pair_counts.values()) != EXPECTED_REPEATED_KINASE_SITE_EXTRA_ROWS:
        _fail("SPHINKS repeated kinase-site source-row inventory mismatch")
    edges_by_kinase = MappingProxyType(
        {
            master.hgnc_symbol: tuple(
                item for item in edges if item.hgnc_symbol == master.hgnc_symbol
            )
            for master in masters
        }
    )
    if any(not values for values in edges_by_kinase.values()):
        _fail("SPHINKS master kinase has no Table 5d signature rows")
    return MasterKinaseCatalog(
        background_tuples=background_tuples,
        background_labels=frozenset(labels),
        masters=masters,
        edges=edges,
        edges_by_kinase=edges_by_kinase,
        aliases=aliases,
        artifact_digest=artifact_digest,
        content_digest=content_digest,
        background_tuple_digest=tuple_digest,
        background_label_digest=label_digest,
        master_kinase_digest=EXPECTED_MASTER_KINASE_DIGEST,
        signature_edge_digest=EXPECTED_SIGNATURE_EDGE_DIGEST,
        alias_digest=alias_digest,
        source_sha256=cast("str", source["source_sha256"]),
        source_url=cast("str", source["source_url"]),
        article_doi=cast("str", source["article_doi"]),
        article_title=cast("str", source["article_title"]),
        article_authors=cast("str", source["article_authors"]),
        source_license=cast("str", source["license"]),
        source_license_url=cast("str", source["license_url"]),
        transformation_notice=cast("str", source["transformation_notice"]),
    )


def is_pinned_phosphosite(phosphosite_id: str) -> bool:
    """Return whether an exact source label belongs to pinned Table 5a."""

    return phosphosite_id in master_kinase_catalog().background_labels


@lru_cache(maxsize=1)
def independent_kinase_memberships_by_site() -> Mapping[str, int]:
    """Return immutable counts of independent kinase hypotheses using each source site.

    Repeated Table 5d source rows for the same kinase/site pair deliberately count once.
    This inventory supports deterministic request budgeting without treating source-row
    alternatives as independent measurements.
    """

    pairs = {(edge.hgnc_symbol, edge.source_site_label) for edge in master_kinase_catalog().edges}
    return MappingProxyType(dict(Counter(site for _kinase, site in pairs)))


__all__ = [
    "CATALOG_RESOURCE",
    "EXPECTED_ALIAS_DIGEST",
    "EXPECTED_BACKGROUND_LABEL_COUNT",
    "EXPECTED_BACKGROUND_LABEL_DIGEST",
    "EXPECTED_BACKGROUND_TUPLE_COUNT",
    "EXPECTED_BACKGROUND_TUPLE_DIGEST",
    "EXPECTED_CATALOG_ARTIFACT_DIGEST",
    "EXPECTED_CATALOG_CONTENT_DIGEST",
    "EXPECTED_EDGE_COUNTS",
    "EXPECTED_KINASE_COUNTS",
    "EXPECTED_MASTER_KINASE_DIGEST",
    "EXPECTED_REPEATED_KINASE_SITE_EXTRA_ROWS",
    "EXPECTED_SIGNATURE_EDGE_DIGEST",
    "EXPECTED_UNIQUE_TARGET_COUNTS",
    "SOURCE_SHA256",
    "BackgroundTuple",
    "MasterKinase",
    "MasterKinaseCatalog",
    "SignatureEdge",
    "SourceReference",
    "independent_kinase_memberships_by_site",
    "is_pinned_phosphosite",
    "master_kinase_catalog",
]
