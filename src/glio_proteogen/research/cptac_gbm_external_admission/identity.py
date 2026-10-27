"""Exact approved HGNC identity admission from one pinned local reference."""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Final

from .contracts import PANEL, GeneIdentity, HgncReference, IdentityResolutionError, SourceLock
from .source import read_verified_source

# MD5 was computed locally over the independently size/SHA-256-locked snapshot.
# It is an additional integrity checksum, not a publisher authenticity assertion.
HGNC_LOCK: Final = SourceLock(
    bytes=16_948_224,
    md5="acc6344dd46eb2942627a16e0d735fb8",
    sha256="854162118530e929f06249f3349465dd5fe0515fcccf0347f463e833609c1270",
)
_ENSEMBL: Final = re.compile(r"(ENSG[0-9]{11})(?:\.[1-9][0-9]*)?(_PAR_Y)?")
_REQUIRED_COLUMNS: Final = frozenset(
    ("hgnc_id", "symbol", "status", "entrez_id", "ensembl_gene_id")
)


def normalize_ensembl_gene_id(value: str) -> str:
    """Remove only a numeric version; preserve the distinct PAR-Y suffix."""

    if not isinstance(value, str) or (match := _ENSEMBL.fullmatch(value)) is None:
        raise IdentityResolutionError("Ensembl gene identifier format is invalid")
    return match[1] + (match[2] or "")


def _decode_hgnc(payload: bytes) -> HgncReference:
    """Private decoder seam; public admission always verifies the fixed byte lock."""

    try:
        text = payload.decode("utf-8-sig", errors="strict")
        rows = csv.DictReader(io.StringIO(text, newline=""), delimiter="\t", strict=True)
        header = rows.fieldnames
        if (
            header is None
            or len(set(header)) != len(header)
            or not _REQUIRED_COLUMNS.issubset(header)
        ):
            raise IdentityResolutionError("HGNC reference format was not accepted")  # noqa: TRY301
        by_hgnc: dict[str, GeneIdentity] = {}
        by_symbol: dict[str, GeneIdentity] = {}
        ensembl_groups: dict[str, list[GeneIdentity]] = {}
        for row in rows:
            if None in row or any(value is None for value in row.values()):
                raise IdentityResolutionError("HGNC reference format was not accepted")  # noqa: TRY301
            if row["status"] != "Approved":
                continue
            ensembl = row["ensembl_gene_id"]
            identity = GeneIdentity(
                hgnc_id=row["hgnc_id"],
                symbol=row["symbol"],
                entrez_id=row["entrez_id"] or None,
                ensembl_gene_id=normalize_ensembl_gene_id(ensembl) if ensembl else None,
            )
            if identity.hgnc_id in by_hgnc or identity.symbol in by_symbol:
                raise IdentityResolutionError("approved HGNC identities are not unique")  # noqa: TRY301
            by_hgnc[identity.hgnc_id] = identity
            by_symbol[identity.symbol] = identity
            if identity.ensembl_gene_id is not None:
                ensembl_groups.setdefault(identity.ensembl_gene_id, []).append(identity)
        if not by_hgnc:
            raise IdentityResolutionError("HGNC reference has no approved identities")  # noqa: TRY301
        by_ensembl = {
            key: tuple(sorted(values, key=lambda identity: identity.hgnc_id))
            for key, values in ensembl_groups.items()
        }
        return HgncReference(by_hgnc=by_hgnc, by_symbol=by_symbol, by_ensembl=by_ensembl)
    except IdentityResolutionError:
        raise
    except (UnicodeError, csv.Error, TypeError, ValueError, KeyError):
        raise IdentityResolutionError("HGNC reference format was not accepted") from None


def read_locked_hgnc(path: str | Path) -> HgncReference:
    """Read only the frozen reference; no caller-selectable lock or decode bypass."""

    return _decode_hgnc(read_verified_source(path, HGNC_LOCK, max_bytes=HGNC_LOCK.bytes))


__all__ = [
    "HGNC_LOCK",
    "PANEL",
    "GeneIdentity",
    "HgncReference",
    "IdentityResolutionError",
    "normalize_ensembl_gene_id",
    "read_locked_hgnc",
]
