"""Validated access to the exact Neftel et al. Table S2 marker catalog."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Final, cast

from .canonical import sha256_digest

CATALOG_RESOURCE: Final = "data/neftel_table_s2_catalog.v1.json"
SOURCE_SHA256: Final = "sha256:208e73ab3d22c494caf85c867d69dc6be38df3fc62ab1f043d7fcc5441066277"
HGNC_SHA256: Final = "sha256:854162118530e929f06249f3349465dd5fe0515fcccf0347f463e833609c1270"
EXPECTED_PROGRAM_COUNTS: Final = {
    "MES2": 50,
    "MES1": 50,
    "AC": 39,
    "OPC": 50,
    "NPC1": 50,
    "NPC2": 50,
    "G1/S": 29,
    "G2/M": 45,
}
EXPECTED_PROGRAM_ORDER: Final = tuple(EXPECTED_PROGRAM_COUNTS)
EXACT_SOURCE_PROGRAM_DIGEST: Final = (
    "sha256:f3fd4171b07c7b0ac7b001d62fffebe0f613c9c3737ce28cdcbc71b0cd3c013b"
)
EXPECTED_CATALOG_CONTENT_DIGEST: Final = (
    "sha256:5f0baa349db65f0ee740a318db6aad334b4ab9fa94b9f9d69158441054c1582f"
)
EXPECTED_CATALOG_ARTIFACT_DIGEST: Final = (
    "sha256:69254d918c3730d7840e9157f0c9d417905bc67b9b2aa5915a1090ae95524d66"
)
EXPECTED_PROTEIN_BACKGROUND_COUNT: Final = 20_288
EXPECTED_PROTEIN_BACKGROUND_DIGEST: Final = (
    "sha256:bc339006d99637bae20d7bcce327b67c31043e6618cb70659a85d7b2b8ff1669"
)


@dataclass(frozen=True, slots=True)
class CatalogMarker:
    raw_symbol: str
    normalized_symbol: str
    rank: int
    protein_eligible: bool
    hgnc_id: str | None
    uniprot_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MarkerCatalog:
    programs: dict[str, tuple[CatalogMarker, ...]]
    aliases: dict[str, str]
    protein_background_symbols: frozenset[str]
    protein_background_digest: str
    unsupported_non_protein_loci: tuple[str, ...]
    content_digest: str
    source_program_digest: str
    artifact_digest: str
    source_sha256: str
    hgnc_sha256: str
    source_url: str


def _resource_bytes() -> bytes:
    resource = files(__package__).joinpath(CATALOG_RESOURCE)
    return resource.read_bytes()


@lru_cache(maxsize=1)
def marker_catalog() -> MarkerCatalog:
    raw_bytes = _resource_bytes()
    artifact_digest = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
    if artifact_digest != EXPECTED_CATALOG_ARTIFACT_DIGEST:
        raise RuntimeError("Neftel catalog artifact digest mismatch")
    document = cast("dict[str, object]", json.loads(raw_bytes))
    content_digest = sha256_digest(document)
    if content_digest != EXPECTED_CATALOG_CONTENT_DIGEST:
        raise RuntimeError("Neftel catalog canonical content digest mismatch")
    source = cast("dict[str, object]", document["source"])
    normalization = cast("dict[str, object]", document["normalization"])
    if document["schema_version"] != "neftel-table-s2-protein-catalog/1.0.0":
        raise RuntimeError("unsupported Neftel marker catalog schema")
    if source["source_sha256"] != SOURCE_SHA256:
        raise RuntimeError("Neftel source provenance digest mismatch")
    if normalization["authority_sha256"] != HGNC_SHA256:
        raise RuntimeError("HGNC normalization provenance digest mismatch")
    programs: dict[str, tuple[CatalogMarker, ...]] = {}
    program_documents = cast("list[dict[str, object]]", document["programs"])
    if tuple(item["program_id"] for item in program_documents) != EXPECTED_PROGRAM_ORDER:
        raise RuntimeError("Neftel marker program order mismatch")
    for program_document in program_documents:
        program_id = cast("str", program_document["program_id"])
        marker_documents = cast("list[dict[str, object]]", program_document["markers"])
        markers = tuple(
            CatalogMarker(
                raw_symbol=cast("str", item["raw_symbol"]),
                normalized_symbol=cast("str", item["normalized_symbol"]),
                rank=cast("int", item["rank"]),
                protein_eligible=cast("bool", item["protein_eligible"]),
                hgnc_id=cast("str | None", item["hgnc_id"]),
                uniprot_ids=tuple(cast("list[str]", item["uniprot_ids"])),
            )
            for item in marker_documents
        )
        expected_count = EXPECTED_PROGRAM_COUNTS.get(program_id)
        if expected_count is None or len(markers) != expected_count:
            raise RuntimeError("Neftel marker count mismatch")
        if tuple(marker.rank for marker in markers) != tuple(range(1, len(markers) + 1)):
            raise RuntimeError("Neftel marker ranks are not contiguous")
        programs[program_id] = markers
    alias_documents = cast("list[dict[str, str]]", normalization["aliases"])
    aliases = {item["raw_symbol"]: item["normalized_symbol"] for item in alias_documents}
    background_symbols = cast("list[str]", normalization["protein_background_symbols"])
    if (
        normalization["protein_background_count"] != EXPECTED_PROTEIN_BACKGROUND_COUNT
        or len(background_symbols) != EXPECTED_PROTEIN_BACKGROUND_COUNT
        or background_symbols != sorted(set(background_symbols))
    ):
        raise RuntimeError("pinned HGNC-UniProt protein-background inventory mismatch")
    background_digest = sha256_digest(background_symbols)
    if (
        normalization["protein_background_digest"] != EXPECTED_PROTEIN_BACKGROUND_DIGEST
        or background_digest != EXPECTED_PROTEIN_BACKGROUND_DIGEST
    ):
        raise RuntimeError("pinned HGNC-UniProt protein-background digest mismatch")
    protein_background_symbols = frozenset(background_symbols)
    unsupported = tuple(cast("list[str]", normalization["unsupported_non_protein_loci"]))
    catalog_unsupported = {
        marker.raw_symbol
        for markers in programs.values()
        for marker in markers
        if not marker.protein_eligible
    }
    if catalog_unsupported != set(unsupported):
        raise RuntimeError("Neftel unsupported-locus inventory mismatch")
    eligible_symbols = {
        marker.normalized_symbol
        for markers in programs.values()
        for marker in markers
        if marker.protein_eligible
    }
    if not eligible_symbols <= protein_background_symbols:
        raise RuntimeError("Neftel protein markers are absent from the pinned protein background")
    if set(unsupported) & protein_background_symbols:
        raise RuntimeError("non-protein loci entered the pinned protein background")
    source_program_digest = sha256_digest(
        {
            program_id: [marker.raw_symbol for marker in markers]
            for program_id, markers in programs.items()
        }
    )
    if source_program_digest != EXACT_SOURCE_PROGRAM_DIGEST:
        raise RuntimeError("exact Neftel source-program digest mismatch")
    return MarkerCatalog(
        programs=programs,
        aliases=aliases,
        protein_background_symbols=protein_background_symbols,
        protein_background_digest=background_digest,
        unsupported_non_protein_loci=unsupported,
        content_digest=content_digest,
        source_program_digest=source_program_digest,
        artifact_digest=artifact_digest,
        source_sha256=source["source_sha256"],
        hgnc_sha256=normalization["authority_sha256"],
        source_url=cast("str", source["source_url"]),
    )


def normalize_symbol(symbol: str) -> str:
    """Resolve only the exact, profile-pinned HGNC previous-symbol mappings."""

    return marker_catalog().aliases.get(symbol, symbol)


def is_protein_background_symbol(symbol: str) -> bool:
    """Return whether an identifier resolves to the pinned HGNC-UniProt background."""

    normalized = normalize_symbol(symbol)
    return normalized in marker_catalog().protein_background_symbols


__all__ = [
    "CATALOG_RESOURCE",
    "EXACT_SOURCE_PROGRAM_DIGEST",
    "EXPECTED_CATALOG_ARTIFACT_DIGEST",
    "EXPECTED_CATALOG_CONTENT_DIGEST",
    "EXPECTED_PROGRAM_COUNTS",
    "EXPECTED_PROGRAM_ORDER",
    "EXPECTED_PROTEIN_BACKGROUND_COUNT",
    "EXPECTED_PROTEIN_BACKGROUND_DIGEST",
    "HGNC_SHA256",
    "SOURCE_SHA256",
    "CatalogMarker",
    "MarkerCatalog",
    "is_protein_background_symbol",
    "marker_catalog",
    "normalize_symbol",
]
