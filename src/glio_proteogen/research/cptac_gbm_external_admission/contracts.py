"""Immutable, identifier-only contracts for exact external source admission."""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Mapping

MAX_SOURCE_BYTES: Final = 192 * 1_024 * 1_024
PANEL: Final = (
    "CDK4",
    "CDKN2A",
    "CDKN2B",
    "EGFR",
    "IDH1",
    "MDM2",
    "MDM4",
    "NF1",
    "PDGFRA",
    "PIK3CA",
    "PIK3R1",
    "PLCG1",
    "PTEN",
    "PTPN11",
    "RB1",
    "TP53",
)


class SourceVerificationError(ValueError):
    """A local source did not satisfy its bounded, exact byte lock."""


class IdentityResolutionError(ValueError):
    """An exact approved identifier reference was not admissible."""


@dataclass(frozen=True, slots=True)
class SourceLock:
    """Content lock; MD5 is an integrity cross-check, not an authenticity claim."""

    bytes: int
    md5: str
    sha256: str

    def __post_init__(self) -> None:
        if type(self.bytes) is not int or not 1 <= self.bytes <= MAX_SOURCE_BYTES:
            raise SourceVerificationError("source lock byte count is invalid")
        if (
            not isinstance(self.md5, str)
            or re.fullmatch(r"[0-9a-f]{32}", self.md5) is None
            or not isinstance(self.sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None
        ):
            raise SourceVerificationError("source lock checksums are invalid")


@dataclass(frozen=True, slots=True)
class GeneIdentity:
    """One exact approved HGNC identity; absent cross-reference IDs remain absent."""

    hgnc_id: str
    symbol: str
    entrez_id: str | None
    ensembl_gene_id: str | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.hgnc_id, str)
            or re.fullmatch(r"HGNC:[1-9][0-9]*", self.hgnc_id) is None
        ):
            raise IdentityResolutionError("approved gene identity is invalid")
        if (
            not isinstance(self.symbol, str)
            or not self.symbol
            or len(self.symbol) > 128
            or self.symbol.strip() != self.symbol
            or any(character.isspace() or ord(character) < 32 for character in self.symbol)
        ):
            raise IdentityResolutionError("approved gene identity is invalid")
        if self.entrez_id is not None and (
            not isinstance(self.entrez_id, str)
            or re.fullmatch(r"[1-9][0-9]*", self.entrez_id) is None
        ):
            raise IdentityResolutionError("approved gene identity is invalid")
        if self.ensembl_gene_id is not None and (
            not isinstance(self.ensembl_gene_id, str)
            or re.fullmatch(r"ENSG[0-9]{11}(?:_PAR_Y)?", self.ensembl_gene_id) is None
        ):
            raise IdentityResolutionError("approved gene identity is invalid")


@dataclass(frozen=True, slots=True)
class HgncReference:
    """Defensively copied, read-only exact identity indexes without alias guessing."""

    by_hgnc: Mapping[str, GeneIdentity]
    by_ensembl: Mapping[str, tuple[GeneIdentity, ...]]
    by_symbol: Mapping[str, GeneIdentity]

    def __post_init__(self) -> None:
        by_hgnc = dict(self.by_hgnc)
        by_ensembl = {key: tuple(values) for key, values in self.by_ensembl.items()}
        by_symbol = dict(self.by_symbol)
        if any(
            not isinstance(value, GeneIdentity) or key != value.hgnc_id
            for key, value in by_hgnc.items()
        ) or any(
            not isinstance(value, GeneIdentity)
            or key != value.symbol
            or by_hgnc.get(value.hgnc_id) != value
            for key, value in by_symbol.items()
        ):
            raise IdentityResolutionError("approved gene indexes are inconsistent")
        if len(by_symbol) != len(by_hgnc) or any(
            not values
            or len(set(values)) != len(values)
            or any(
                not isinstance(value, GeneIdentity)
                or key != value.ensembl_gene_id
                or by_hgnc.get(value.hgnc_id) != value
                for value in values
            )
            for key, values in by_ensembl.items()
        ):
            raise IdentityResolutionError("approved gene indexes are inconsistent")
        if any(
            identity.ensembl_gene_id is not None
            and identity not in by_ensembl.get(identity.ensembl_gene_id, ())
            for identity in by_hgnc.values()
        ):
            raise IdentityResolutionError("approved gene indexes are inconsistent")
        object.__setattr__(self, "by_hgnc", MappingProxyType(by_hgnc))
        object.__setattr__(self, "by_ensembl", MappingProxyType(by_ensembl))
        object.__setattr__(self, "by_symbol", MappingProxyType(by_symbol))


__all__ = [
    "MAX_SOURCE_BYTES",
    "PANEL",
    "GeneIdentity",
    "HgncReference",
    "IdentityResolutionError",
    "SourceLock",
    "SourceVerificationError",
]
