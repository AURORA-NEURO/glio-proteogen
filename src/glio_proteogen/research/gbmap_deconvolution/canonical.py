"""Canonical identities for the unfitted GBmap aggregate boundary."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Protocol

import numpy as np
from pydantic import BaseModel

from glio_proteogen.kernel.canonical import sha256_digest

if TYPE_CHECKING:
    from .aggregate import AggregateReference, Int32Vector, Int64Vector


class _DigestWriter(Protocol):
    def update(self, value: bytes, /) -> None: ...


def _framed(digest: _DigestWriter, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, byteorder="big", signed=False))
    digest.update(value)


def _text(digest: _DigestWriter, value: str) -> None:
    _framed(digest, value.encode("utf-8"))


def _integer(digest: _DigestWriter, value: int) -> None:
    _text(digest, str(value))


def _int64_vector(digest: _DigestWriter, value: Int64Vector) -> None:
    payload = np.ascontiguousarray(value, dtype="<i8").tobytes(order="C")
    _integer(digest, len(value))
    _framed(digest, payload)


def _int32_vector(digest: _DigestWriter, value: Int32Vector) -> None:
    payload = np.ascontiguousarray(value, dtype="<i4").tobytes(order="C")
    _integer(digest, len(value))
    _framed(digest, payload)


def feature_order_digest(
    feature_ids: Sequence[str],
    gene_symbols: Sequence[str | None],
) -> str:
    """Bind feature order and optional public symbols without array materialization."""

    return sha256_digest(
        {
            "schema": "gbmap-feature-order/0.1.0-dev",
            "features": [
                {"feature_id": feature_id, "gene_symbol": gene_symbol}
                for feature_id, gene_symbol in zip(feature_ids, gene_symbols, strict=True)
            ],
        }
    )


def aggregate_content_digest(reference: AggregateReference) -> str:
    """Stream a stable digest over the complete transient fitting aggregate."""

    digest = hashlib.sha256()
    _text(digest, "gbmap-aggregate-reference/0.1.0-dev")
    _text(digest, reference.source_file_sha256)
    _integer(digest, reference.source_bytes)
    _text(digest, reference.taxonomy_digest)
    _text(digest, reference.extraction_recipe_digest)
    _text(digest, reference.feature_order_digest)
    _integer(digest, len(reference.records))
    for record in reference.records:
        _text(digest, record.study_key)
        _text(digest, record.donor_key)
        _text(digest, record.modeled_label)
        _integer(digest, len(record.source_labels))
        for source_label in record.source_labels:
            _text(digest, source_label)
        _integer(digest, record.cell_count)
        _integer(digest, record.total_umis)
        _int64_vector(digest, record.gene_counts)
        _int32_vector(digest, record.detected_cell_counts)
    return "sha256:" + digest.hexdigest()


def profile_digest(value: BaseModel | Mapping[str, object]) -> str:
    document: dict[str, Any]
    if isinstance(value, BaseModel):
        document = value.model_dump(mode="json")
    else:
        document = deepcopy(dict(value))
    document.pop("profile_digest", None)
    return sha256_digest(document)


__all__ = ["aggregate_content_digest", "feature_order_digest", "profile_digest"]
