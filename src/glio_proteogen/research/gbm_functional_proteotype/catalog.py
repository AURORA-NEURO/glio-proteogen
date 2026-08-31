"""Digest-locked access to Migliozzi Table 2d/2e aggregate evidence."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from itertools import pairwise
from typing import Final, cast

from .canonical import sha256_digest

CATALOG_RESOURCE: Final = "data/gbm_functional_proteotype_catalog.v1.json"
EXPECTED_SCHEMA_VERSION: Final = "gbm-functional-proteotype-catalog/1.0.0"
EXPECTED_ARTIFACT_DIGEST: Final = (
    "sha256:67dd0d660fcd88a4aa309dd398e3d5b9fec8c018bea1cad88158463edf6d8d6d"
)
EXPECTED_CONTENT_DIGEST: Final = (
    "sha256:1d4099b6d04bf3ea85ea268e551464b5aba220a081b6dffd69282bbb28cafb8b"
)
EXPECTED_SIGNATURE_CATALOG_DIGEST: Final = (
    "sha256:e9f9f6c0a19c6c44902ad6c85880ab1c702648e3f1bd0cc7002b7350dfa6585d"
)
EXPECTED_PATHWAY_CATALOG_DIGEST: Final = (
    "sha256:f2674bb03ac9306b7a06b524e0b2dbbd0bfa20264b797863975fb62763c3f3b4"
)
EXPECTED_SOURCE_WORKBOOK_DIGEST: Final = (
    "sha256:865a2db1ec99dcf047d6ff56b313a21607b840e5239bb9184739f6f6f217fb88"
)
EXPECTED_SOURCE_SIZE_BYTES: Final = 7_635_280
EXPECTED_AXIS_ORDER: Final = ("GPM", "MTC", "NEU", "PPR")
EXPECTED_SIGNATURE_COUNTS: Final = dict.fromkeys(EXPECTED_AXIS_ORDER, 150)
EXPECTED_PATHWAY_COUNTS: Final = {"GPM": 243, "MTC": 107, "NEU": 272, "PPR": 204}
EXPECTED_AXIS_SIGNATURE_DIGESTS: Final = {
    "GPM": "sha256:705b8adf92f48d59d99ba4c5def49dc74d7b9c5df57f9c7daecaa58d95a3e02e",
    "MTC": "sha256:d89fb68636e765170aa948e0a2045a3c57f7576b9b15621d79d0a2d4def7b92b",
    "NEU": "sha256:244b38ed1f5aa3ef6d5e9cd1b89b6cc9b77dd946ff3fbff9983c54d67913b8e7",
    "PPR": "sha256:0dc46e67b9c10da860c6cc93585298acca754eb0c2285bfc677e60e004bbce5c",
}
EXPECTED_AXIS_PATHWAY_DIGESTS: Final = {
    "GPM": "sha256:281a7cb5c62fa2580e3e6133677f982ef483f6beea2fa1510bfcac55b61309e9",
    "MTC": "sha256:dda70e67de34e15c4d8770272b59a1537787e27d883a2e2a37a8e77ec1c8b897",
    "NEU": "sha256:7ac20c06dde8b741aa88dbb38ea870d07745e3785d2781f1a564f0994e2ff5a9",
    "PPR": "sha256:f3581864529af625dcb8fda74c862e1da225f243dc0222a89668770bfb310e6f",
}


@dataclass(frozen=True, slots=True)
class CatalogProtein:
    axis: str
    gene_symbol: str
    source_protein_label: str
    source_mww_score: float
    source_rank: int
    source_loading: float


@dataclass(frozen=True, slots=True)
class CatalogPathway:
    axis: str
    pathway: str
    logit_nes: float
    p_value: float
    q_value: float
    source_rank: int


@dataclass(frozen=True, slots=True)
class FunctionalProteotypeCatalog:
    axes: dict[str, tuple[CatalogProtein, ...]]
    source_cohort_pathway_context: dict[str, tuple[CatalogPathway, ...]]
    by_gene_symbol: dict[str, CatalogProtein]
    source: dict[str, object]
    content_digest: str
    artifact_digest: str
    signature_catalog_digest: str
    pathway_catalog_digest: str
    axis_signature_digests: dict[str, str]
    axis_pathway_digests: dict[str, str]


def _resource_bytes() -> bytes:
    return files(__package__).joinpath(CATALOG_RESOURCE).read_bytes()


def _plain_document(raw_bytes: bytes) -> dict[str, object]:
    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        document: dict[str, object] = {}
        for key, value in pairs:
            if key in document:
                raise RuntimeError("functional-proteotype catalog contains a duplicate key")
            document[key] = value
        return document

    try:
        value = json.loads(
            raw_bytes,
            object_pairs_hook=unique_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON token {token}")
            ),
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError("functional-proteotype catalog is not strict JSON") from error
    if type(value) is not dict:
        raise RuntimeError("functional-proteotype catalog root must be an object")
    return cast("dict[str, object]", value)


def _finite(value: object, *, field: str) -> float:
    if type(value) not in {int, float}:
        raise RuntimeError(f"catalog {field} must be numeric")
    number = float(cast("int | float", value))
    if not math.isfinite(number):
        raise RuntimeError(f"catalog {field} must be finite")
    return number


def _text(value: object, *, field: str) -> str:
    if type(value) is not str or not value:
        raise RuntimeError(f"catalog {field} must be non-empty text")
    return value


def _protein_axes(
    document: dict[str, object],
) -> tuple[dict[str, tuple[CatalogProtein, ...]], dict[str, CatalogProtein]]:
    raw_axes = cast("dict[str, object]", document["axes"])
    if tuple(raw_axes) != EXPECTED_AXIS_ORDER:
        raise RuntimeError("functional-proteotype axis order changed")
    axes: dict[str, tuple[CatalogProtein, ...]] = {}
    by_gene: dict[str, CatalogProtein] = {}
    for axis in EXPECTED_AXIS_ORDER:
        raw_rows = cast("list[dict[str, object]]", raw_axes[axis])
        if len(raw_rows) != EXPECTED_SIGNATURE_COUNTS[axis]:
            raise RuntimeError(f"unexpected {axis} signature size")
        scores = tuple(
            _finite(row.get("source_mww_score"), field="source_mww_score") for row in raw_rows
        )
        if any(score <= 0.0 for score in scores) or any(
            left < right for left, right in pairwise(scores)
        ):
            raise RuntimeError(f"{axis} source MWW scores are invalid or out of order")
        median_score = statistics.median(scores)
        proteins: list[CatalogProtein] = []
        for expected_rank, (row, score) in enumerate(zip(raw_rows, scores, strict=True), start=1):
            gene_symbol = _text(row.get("gene_symbol"), field="gene_symbol")
            source_label = _text(row.get("source_protein_label"), field="source_protein_label")
            if row.get("source_rank") != expected_rank:
                raise RuntimeError(f"{axis} source ranks are not contiguous")
            if gene_symbol in by_gene:
                raise RuntimeError("source signature gene symbols are not disjoint")
            protein = CatalogProtein(
                axis=axis,
                gene_symbol=gene_symbol,
                source_protein_label=source_label,
                source_mww_score=score,
                source_rank=expected_rank,
                source_loading=score / median_score,
            )
            proteins.append(protein)
            by_gene[gene_symbol] = protein
        axes[axis] = tuple(proteins)
    if len(by_gene) != 600:
        raise RuntimeError("functional-proteotype source must contain 600 disjoint genes")
    return axes, by_gene


def _pathway_context(document: dict[str, object]) -> dict[str, tuple[CatalogPathway, ...]]:
    raw_context = cast("dict[str, object]", document["source_cohort_pathway_context"])
    if tuple(raw_context) != EXPECTED_AXIS_ORDER:
        raise RuntimeError("functional-proteotype pathway axis order changed")
    context: dict[str, tuple[CatalogPathway, ...]] = {}
    for axis in EXPECTED_AXIS_ORDER:
        raw_rows = cast("list[dict[str, object]]", raw_context[axis])
        if len(raw_rows) != EXPECTED_PATHWAY_COUNTS[axis]:
            raise RuntimeError(f"unexpected {axis} pathway-context size")
        pathways: list[CatalogPathway] = []
        seen: set[str] = set()
        for expected_rank, row in enumerate(raw_rows, start=1):
            pathway = _text(row.get("pathway"), field="pathway")
            logit_nes = _finite(row.get("logit_nes"), field="logit_nes")
            p_value = _finite(row.get("p_value"), field="p_value")
            q_value = _finite(row.get("q_value"), field="q_value")
            if row.get("source_rank") != expected_rank:
                raise RuntimeError(f"{axis} pathway ranks are not contiguous")
            if pathway in seen:
                raise RuntimeError(f"{axis} pathway context contains duplicates")
            if not 0.0 <= p_value <= q_value <= 0.05:
                raise RuntimeError(f"{axis} pathway probabilities are invalid")
            seen.add(pathway)
            pathways.append(
                CatalogPathway(
                    axis=axis,
                    pathway=pathway,
                    logit_nes=logit_nes,
                    p_value=p_value,
                    q_value=q_value,
                    source_rank=expected_rank,
                )
            )
        context[axis] = tuple(pathways)
    return context


@lru_cache(maxsize=1)
def functional_proteotype_catalog() -> FunctionalProteotypeCatalog:
    """Load and exhaustively revalidate the immutable aggregate source catalog."""

    raw_bytes = _resource_bytes()
    artifact_digest = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
    if artifact_digest != EXPECTED_ARTIFACT_DIGEST:
        raise RuntimeError("functional-proteotype catalog artifact digest mismatch")
    document = _plain_document(raw_bytes)
    if document.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        raise RuntimeError("unsupported functional-proteotype catalog schema")
    declared_content_digest = _text(document.get("content_digest"), field="content_digest")
    digest_payload = dict(document)
    digest_payload.pop("content_digest")
    content_digest = sha256_digest(digest_payload)
    if (
        declared_content_digest != EXPECTED_CONTENT_DIGEST
        or content_digest != EXPECTED_CONTENT_DIGEST
    ):
        raise RuntimeError("functional-proteotype catalog content digest mismatch")
    raw_axes = cast("dict[str, object]", document["axes"])
    raw_pathways = cast("dict[str, object]", document["source_cohort_pathway_context"])
    signature_digest = sha256_digest(raw_axes)
    pathway_digest = sha256_digest(raw_pathways)
    if signature_digest != EXPECTED_SIGNATURE_CATALOG_DIGEST:
        raise RuntimeError("functional-proteotype signature digest mismatch")
    if pathway_digest != EXPECTED_PATHWAY_CATALOG_DIGEST:
        raise RuntimeError("functional-proteotype pathway digest mismatch")
    axis_signature_digests = {axis: sha256_digest(raw_axes[axis]) for axis in EXPECTED_AXIS_ORDER}
    axis_pathway_digests = {axis: sha256_digest(raw_pathways[axis]) for axis in EXPECTED_AXIS_ORDER}
    if axis_signature_digests != EXPECTED_AXIS_SIGNATURE_DIGESTS:
        raise RuntimeError("functional-proteotype per-axis signature digests changed")
    if axis_pathway_digests != EXPECTED_AXIS_PATHWAY_DIGESTS:
        raise RuntimeError("functional-proteotype per-axis pathway digests changed")

    source = cast("dict[str, object]", document["source"])
    if (
        source.get("source_sha256") != EXPECTED_SOURCE_WORKBOOK_DIGEST
        or source.get("source_size_bytes") != EXPECTED_SOURCE_SIZE_BYTES
        or source.get("article_doi") != "10.1038/s43018-022-00510-x"
        or source.get("pmcid") != "PMC9970878"
        or source.get("license") != "CC-BY-4.0"
        or source.get("license_url") != "https://creativecommons.org/licenses/by/4.0/"
    ):
        raise RuntimeError("functional-proteotype source provenance changed")
    axes, by_gene = _protein_axes(document)
    pathway_context = _pathway_context(document)
    return FunctionalProteotypeCatalog(
        axes=axes,
        source_cohort_pathway_context=pathway_context,
        by_gene_symbol=by_gene,
        source=source,
        content_digest=content_digest,
        artifact_digest=artifact_digest,
        signature_catalog_digest=signature_digest,
        pathway_catalog_digest=pathway_digest,
        axis_signature_digests=axis_signature_digests,
        axis_pathway_digests=axis_pathway_digests,
    )


def is_source_gene_symbol(gene_symbol: str) -> bool:
    """Return whether an exact source Table 2d gene identifier is modeled."""

    return gene_symbol in functional_proteotype_catalog().by_gene_symbol


__all__ = [
    "CATALOG_RESOURCE",
    "EXPECTED_ARTIFACT_DIGEST",
    "EXPECTED_AXIS_ORDER",
    "EXPECTED_CONTENT_DIGEST",
    "EXPECTED_PATHWAY_CATALOG_DIGEST",
    "EXPECTED_SIGNATURE_CATALOG_DIGEST",
    "EXPECTED_SOURCE_WORKBOOK_DIGEST",
    "CatalogPathway",
    "CatalogProtein",
    "FunctionalProteotypeCatalog",
    "functional_proteotype_catalog",
    "is_source_gene_symbol",
]
