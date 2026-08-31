"""Digest-locked HGNC identities for the exact 5,000-feature GBmap source.

The Zenodo GBmap H5AD stores gene symbols in ``var/_index`` rather than stable
identifiers.  This module maps those exact source symbols to stable HGNC IDs
without rewriting the source vocabulary.  Exact current HGNC symbols win;
otherwise only an unambiguous previous/alias-symbol match is usable.

The bundled crosswalk is public, contains no expression values or donor data,
and is not a fitted model.  Ambiguous and unresolved rows remain explicit and
must never be interpreted as zero or negative evidence.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from importlib.resources import files
from typing import Any, Final, Literal, Self, cast

from pydantic import Field, field_validator, model_validator

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import FrozenModel, Sha256Digest

from .canonical import feature_order_digest
from .errors import GbmapInputError, GbmapSourceAdmissionError

FEATURE_IDENTITY_SCHEMA: Final = "gbmap-hgnc-feature-crosswalk/1.0.0"
FEATURE_IDENTITY_CROSSWALK_ID: Final = "gbmap-hgnc-feature-crosswalk/2026-08-28"
FEATURE_IDENTITY_RESOURCE: Final = "data/gbmap_hgnc_feature_crosswalk.v2.json"
GBMAP_SOURCE_SHA256: Final = (
    "sha256:cb48db2e31299b41d2fe2b6004fadbabe49957bf7d6d72396139db12366ecd8a"
)
GBMAP_FEATURE_ORDER_DIGEST: Final = (
    "sha256:d2dc362629740745fa216ac5d955f98f6eaaeb49941cf1abdbc3f0439660c577"
)
HGNC_SOURCE_ID: Final = "hgnc-complete-set-2026-08-28"
HGNC_SOURCE_SHA256: Final = (
    "sha256:854162118530e929f06249f3349465dd5fe0515fcccf0347f463e833609c1270"
)
HGNC_SOURCE_BYTES: Final = 16_948_224
HGNC_ROW_COUNT: Final = 45_045
PRODUCTION_FEATURE_COUNT: Final = 5_000

EXPECTED_FEATURE_IDENTITY_ARTIFACT_DIGEST: Final = (
    "sha256:0eeb117902a412527463466258558f4f7baf6229bb457e2e9f64f1082e63e798"
)
EXPECTED_FEATURE_IDENTITY_CONTENT_DIGEST: Final = (
    "sha256:c9749bc80c9542e37dfacf384be3c2080b2c0edf32e291f65997e867a6b8a02a"
)

_HGNC_ID = re.compile(r"^HGNC:[1-9][0-9]*$")
_ENSEMBL_GENE_ID = re.compile(r"^ENSG[0-9]{11}$")
_REQUIRED_HGNC_COLUMNS: Final = frozenset(
    {"hgnc_id", "symbol", "status", "alias_symbol", "prev_symbol", "ensembl_gene_id"}
)


class FeatureIdentityMatch(StrEnum):
    """Explicit disposition for one source feature symbol."""

    EXACT_APPROVED_SYMBOL = "exact_approved_symbol"
    UNIQUE_PREVIOUS_OR_ALIAS_SYMBOL = "unique_previous_or_alias_symbol"
    AMBIGUOUS_PREVIOUS_OR_ALIAS_SYMBOL = "ambiguous_previous_or_alias_symbol"
    UNRESOLVED = "unresolved"


class FeatureIdentityEntry(FrozenModel):
    """Public stable identity for one source symbol, in exact H5AD order."""

    input_symbol: str = Field(min_length=1, max_length=256)
    hgnc_id: str | None = Field(default=None, pattern=r"^HGNC:[1-9][0-9]*$")
    ensembl_gene_id: str | None = Field(default=None, pattern=r"^ENSG[0-9]{11}$")
    match_status: FeatureIdentityMatch

    @field_validator("input_symbol")
    @classmethod
    def symbol_is_canonical(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("input_symbol cannot contain surrounding whitespace")
        return value

    @model_validator(mode="after")
    def disposition_is_consistent(self) -> Self:
        mapped = self.match_status in {
            FeatureIdentityMatch.EXACT_APPROVED_SYMBOL,
            FeatureIdentityMatch.UNIQUE_PREVIOUS_OR_ALIAS_SYMBOL,
        }
        if mapped != (self.hgnc_id is not None):
            raise ValueError("mapped identity state and HGNC ID disagree")
        if self.ensembl_gene_id is not None and self.hgnc_id is None:
            raise ValueError("an Ensembl ID requires a stable HGNC identity")
        return self


class FeatureIdentityCounts(FrozenModel):
    """Closed reconciliation of every crosswalk disposition."""

    source_feature_count: int = Field(gt=0, le=10_000)
    exact_approved_symbol_count: int = Field(ge=0, le=10_000)
    unique_previous_or_alias_symbol_count: int = Field(ge=0, le=10_000)
    ambiguous_previous_or_alias_symbol_count: int = Field(ge=0, le=10_000)
    unresolved_count: int = Field(ge=0, le=10_000)
    stable_hgnc_mapping_count: int = Field(ge=0, le=10_000)
    unique_model_eligible_hgnc_count: int = Field(ge=0, le=10_000)
    duplicate_stable_identity_entry_count: int = Field(ge=0, le=10_000)

    @model_validator(mode="after")
    def counts_reconcile(self) -> Self:
        if (
            self.exact_approved_symbol_count
            + self.unique_previous_or_alias_symbol_count
            + self.ambiguous_previous_or_alias_symbol_count
            + self.unresolved_count
            != self.source_feature_count
        ):
            raise ValueError("feature-identity disposition counts do not reconcile")
        if self.stable_hgnc_mapping_count != (
            self.exact_approved_symbol_count + self.unique_previous_or_alias_symbol_count
        ):
            raise ValueError("stable HGNC mapping count does not reconcile")
        if (
            self.unique_model_eligible_hgnc_count + self.duplicate_stable_identity_entry_count
            != self.stable_hgnc_mapping_count
        ):
            raise ValueError("model-eligible HGNC identity counts do not reconcile")
        return self


class FeatureIdentitySource(FrozenModel):
    """Immutable source identities used to construct the public crosswalk."""

    gbmap_source_sha256: Sha256Digest
    gbmap_feature_order_digest: Sha256Digest
    hgnc_source_id: str = Field(min_length=1, max_length=128)
    hgnc_source_sha256: Sha256Digest
    hgnc_source_bytes: int = Field(gt=0)
    hgnc_row_count: int = Field(gt=0)
    hgnc_license: Literal["CC0-1.0"] = "CC0-1.0"
    hgnc_attribution: Literal["HGNC (RRID:SCR_002827)"] = "HGNC (RRID:SCR_002827)"


class FeatureIdentityPolicy(FrozenModel):
    """Machine-checkable limits on how feature identities may be used."""

    primary_stable_identifier: Literal["hgnc_id"] = "hgnc_id"
    exact_approved_symbol_preferred: Literal[True] = True
    unique_previous_or_alias_permitted: Literal[True] = True
    ambiguous_alias_mapping_permitted: Literal[False] = False
    unresolved_feature_in_model_permitted: Literal[False] = False
    silent_symbol_rewrite_permitted: Literal[False] = False
    donor_data_retained: Literal[False] = False
    expression_data_retained: Literal[False] = False
    fitted_model_parameters_retained: Literal[False] = False
    runtime_mount_permitted: Literal[False] = False


class GbmapFeatureIdentityCrosswalk(FrozenModel):
    """Complete digest-bound feature crosswalk; not a model artifact."""

    schema_version: Literal["gbmap-hgnc-feature-crosswalk/1.0.0"] = (
        "gbmap-hgnc-feature-crosswalk/1.0.0"
    )
    crosswalk_id: str = Field(min_length=1, max_length=128)
    source: FeatureIdentitySource
    policy: FeatureIdentityPolicy
    counts: FeatureIdentityCounts
    entries: tuple[FeatureIdentityEntry, ...] = Field(min_length=1, max_length=10_000)
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def crosswalk_is_consistent(self) -> Self:
        symbols = tuple(entry.input_symbol for entry in self.entries)
        if len(symbols) != len(set(symbols)):
            raise ValueError("feature-identity input symbols must be unique")
        if len(symbols) != self.counts.source_feature_count:
            raise ValueError("feature-identity entries and counts disagree")
        observed = _counts(self.entries)
        if observed != self.counts:
            raise ValueError("feature-identity entries do not match declared counts")
        observed_order = feature_order_digest(symbols, (None,) * len(symbols))
        if observed_order != self.source.gbmap_feature_order_digest:
            raise ValueError("feature-identity source order digest does not match entries")
        if self.content_digest != feature_identity_content_digest(self):
            raise ValueError("feature-identity content digest mismatch")
        return self

    @property
    def usable_feature_indices(self) -> tuple[int, ...]:
        """Return one unambiguous source index per stable HGNC identity.

        When both a current approved symbol and its historical synonym occur in
        the source, the exact current symbol wins. Multiple historical rows for
        one HGNC identity are all excluded rather than resolved arbitrarily.
        """

        return _usable_indices(self.entries)


@dataclass(frozen=True, slots=True)
class HgncIdentityRecord:
    """Transient approved HGNC row used only while building the crosswalk."""

    hgnc_id: str
    approved_symbol: str
    ensembl_gene_id: str | None
    previous_symbols: frozenset[str]
    alias_symbols: frozenset[str]

    def __post_init__(self) -> None:
        if _HGNC_ID.fullmatch(self.hgnc_id) is None:
            raise GbmapSourceAdmissionError("HGNC snapshot contains an invalid HGNC ID")
        _canonical_symbol(self.approved_symbol)
        if self.ensembl_gene_id is not None and (
            _ENSEMBL_GENE_ID.fullmatch(self.ensembl_gene_id) is None
        ):
            raise GbmapSourceAdmissionError("HGNC snapshot contains an invalid Ensembl gene ID")
        for symbol in self.previous_symbols | self.alias_symbols:
            _canonical_symbol(symbol)


def _canonical_symbol(value: object) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > 256:
        raise GbmapSourceAdmissionError("feature identity contains a noncanonical symbol")
    return value


def _split_symbols(value: str) -> frozenset[str]:
    if not value:
        return frozenset()
    values = frozenset(value.split("|"))
    if any(not item or item != item.strip() for item in values):
        raise GbmapSourceAdmissionError("HGNC synonym vocabulary is not canonical")
    return values


def parse_hgnc_complete_set(raw_bytes: bytes) -> tuple[HgncIdentityRecord, ...]:
    """Parse a complete HGNC TSV without retaining names or unrelated metadata."""

    if type(raw_bytes) is not bytes or not raw_bytes:
        raise GbmapSourceAdmissionError("HGNC snapshot must be nonempty exact bytes")
    try:
        text = raw_bytes.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text, newline=""), delimiter="\t", strict=True)
        if reader.fieldnames is None or not _REQUIRED_HGNC_COLUMNS.issubset(reader.fieldnames):
            raise GbmapSourceAdmissionError(  # noqa: TRY301
                "HGNC snapshot is missing required columns"
            )
        records: list[HgncIdentityRecord] = []
        for row in reader:
            if row.get("status") != "Approved":
                raise GbmapSourceAdmissionError(  # noqa: TRY301
                    "HGNC snapshot contains a non-approved row"
                )
            records.append(
                HgncIdentityRecord(
                    hgnc_id=cast("str", row["hgnc_id"]),
                    approved_symbol=cast("str", row["symbol"]),
                    ensembl_gene_id=cast("str", row["ensembl_gene_id"]) or None,
                    previous_symbols=_split_symbols(cast("str", row["prev_symbol"])),
                    alias_symbols=_split_symbols(cast("str", row["alias_symbol"])),
                )
            )
    except GbmapSourceAdmissionError:
        raise
    except (csv.Error, KeyError, TypeError, UnicodeDecodeError, ValueError) as exc:
        raise GbmapSourceAdmissionError("HGNC snapshot is not a valid complete-set TSV") from exc
    approved = tuple(record.approved_symbol for record in records)
    ids = tuple(record.hgnc_id for record in records)
    if len(approved) != len(set(approved)) or len(ids) != len(set(ids)):
        raise GbmapSourceAdmissionError("HGNC approved symbols and IDs must be unique")
    return tuple(records)


def _usable_indices(entries: Sequence[FeatureIdentityEntry]) -> tuple[int, ...]:
    grouped: defaultdict[str, list[int]] = defaultdict(list)
    for index, entry in enumerate(entries):
        if entry.hgnc_id is not None:
            grouped[entry.hgnc_id].append(index)
    usable: list[int] = []
    for indices in grouped.values():
        if len(indices) == 1:
            usable.extend(indices)
            continue
        exact = [
            index
            for index in indices
            if entries[index].match_status is FeatureIdentityMatch.EXACT_APPROVED_SYMBOL
        ]
        if len(exact) == 1:
            usable.extend(exact)
    return tuple(sorted(usable))


def _counts(entries: Sequence[FeatureIdentityEntry]) -> FeatureIdentityCounts:
    exact = sum(
        entry.match_status is FeatureIdentityMatch.EXACT_APPROVED_SYMBOL for entry in entries
    )
    historical = sum(
        entry.match_status is FeatureIdentityMatch.UNIQUE_PREVIOUS_OR_ALIAS_SYMBOL
        for entry in entries
    )
    ambiguous = sum(
        entry.match_status is FeatureIdentityMatch.AMBIGUOUS_PREVIOUS_OR_ALIAS_SYMBOL
        for entry in entries
    )
    unresolved = sum(entry.match_status is FeatureIdentityMatch.UNRESOLVED for entry in entries)
    stable_ids = tuple(entry.hgnc_id for entry in entries if entry.hgnc_id is not None)
    model_eligible_count = len(_usable_indices(entries))
    return FeatureIdentityCounts(
        source_feature_count=len(entries),
        exact_approved_symbol_count=exact,
        unique_previous_or_alias_symbol_count=historical,
        ambiguous_previous_or_alias_symbol_count=ambiguous,
        unresolved_count=unresolved,
        stable_hgnc_mapping_count=exact + historical,
        unique_model_eligible_hgnc_count=model_eligible_count,
        duplicate_stable_identity_entry_count=len(stable_ids) - model_eligible_count,
    )


def feature_identity_content_digest(
    value: GbmapFeatureIdentityCrosswalk | Mapping[str, object],
) -> Sha256Digest:
    """Digest every semantic field except the self-referential content digest."""

    if isinstance(value, GbmapFeatureIdentityCrosswalk):
        document = value.model_dump(mode="json")
    else:
        document = dict(value)
    document.pop("content_digest", None)
    return sha256_digest(document)


def build_feature_identity_crosswalk(
    feature_symbols: Sequence[str],
    hgnc_records: Sequence[HgncIdentityRecord],
    *,
    gbmap_source_sha256: str,
    hgnc_source_sha256: str,
    hgnc_source_bytes: int,
    hgnc_source_id: str,
) -> GbmapFeatureIdentityCrosswalk:
    """Resolve exact source symbols under the fail-closed HGNC policy."""

    symbols = tuple(_canonical_symbol(value) for value in feature_symbols)
    if not symbols or len(symbols) != len(set(symbols)):
        raise GbmapSourceAdmissionError("GBmap feature symbols must be nonempty and unique")
    records = tuple(hgnc_records)
    if not records or any(type(item) is not HgncIdentityRecord for item in records):
        raise GbmapSourceAdmissionError("HGNC records must be exact parsed identity rows")

    approved: dict[str, HgncIdentityRecord] = {}
    approved_ids: set[str] = set()
    historical: defaultdict[str, set[HgncIdentityRecord]] = defaultdict(set)
    for record in records:
        if record.approved_symbol in approved or record.hgnc_id in approved_ids:
            raise GbmapSourceAdmissionError("HGNC records contain duplicate identities")
        approved[record.approved_symbol] = record
        approved_ids.add(record.hgnc_id)
        for alias in record.previous_symbols | record.alias_symbols:
            historical[alias].add(record)

    entries: list[FeatureIdentityEntry] = []
    for symbol in symbols:
        current = approved.get(symbol)
        if current is not None:
            entries.append(
                FeatureIdentityEntry(
                    input_symbol=symbol,
                    hgnc_id=current.hgnc_id,
                    ensembl_gene_id=current.ensembl_gene_id,
                    match_status=FeatureIdentityMatch.EXACT_APPROVED_SYMBOL,
                )
            )
            continue
        candidates = historical.get(symbol, set())
        if len(candidates) == 1:
            resolved = next(iter(candidates))
            entries.append(
                FeatureIdentityEntry(
                    input_symbol=symbol,
                    hgnc_id=resolved.hgnc_id,
                    ensembl_gene_id=resolved.ensembl_gene_id,
                    match_status=FeatureIdentityMatch.UNIQUE_PREVIOUS_OR_ALIAS_SYMBOL,
                )
            )
        elif candidates:
            entries.append(
                FeatureIdentityEntry(
                    input_symbol=symbol,
                    hgnc_id=None,
                    ensembl_gene_id=None,
                    match_status=FeatureIdentityMatch.AMBIGUOUS_PREVIOUS_OR_ALIAS_SYMBOL,
                )
            )
        else:
            entries.append(
                FeatureIdentityEntry(
                    input_symbol=symbol,
                    hgnc_id=None,
                    ensembl_gene_id=None,
                    match_status=FeatureIdentityMatch.UNRESOLVED,
                )
            )

    entry_tuple = tuple(entries)
    source = FeatureIdentitySource(
        gbmap_source_sha256=gbmap_source_sha256,
        gbmap_feature_order_digest=feature_order_digest(symbols, (None,) * len(symbols)),
        hgnc_source_id=hgnc_source_id,
        hgnc_source_sha256=hgnc_source_sha256,
        hgnc_source_bytes=hgnc_source_bytes,
        hgnc_row_count=len(records),
    )
    policy = FeatureIdentityPolicy()
    payload: dict[str, Any] = {
        "schema_version": FEATURE_IDENTITY_SCHEMA,
        "crosswalk_id": FEATURE_IDENTITY_CROSSWALK_ID,
        "source": source.model_dump(mode="json"),
        "policy": policy.model_dump(mode="json"),
        "counts": _counts(entry_tuple).model_dump(mode="json"),
        "entries": [entry.model_dump(mode="json") for entry in entry_tuple],
    }
    return GbmapFeatureIdentityCrosswalk(
        schema_version=FEATURE_IDENTITY_SCHEMA,
        crosswalk_id=FEATURE_IDENTITY_CROSSWALK_ID,
        source=source,
        policy=policy,
        counts=_counts(entry_tuple),
        entries=entry_tuple,
        content_digest=feature_identity_content_digest(payload),
    )


def _strict_json(raw_bytes: bytes) -> dict[str, object]:
    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw_bytes,
            object_pairs_hook=unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite JSON")),
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise GbmapSourceAdmissionError("feature-identity artifact is not strict JSON") from exc
    if type(value) is not dict or canonical_json_bytes(value) != raw_bytes:
        raise GbmapSourceAdmissionError("feature-identity artifact is not canonical JSON")
    return cast("dict[str, object]", value)


def load_feature_identity_crosswalk_bytes(
    raw_bytes: bytes,
    *,
    expected_artifact_digest: str,
    require_production_bindings: bool = True,
) -> GbmapFeatureIdentityCrosswalk:
    """Load canonical bytes and fail closed on any semantic or byte drift."""

    if type(raw_bytes) is not bytes or not raw_bytes:
        raise GbmapSourceAdmissionError("feature-identity artifact must be nonempty bytes")
    artifact_digest = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
    if artifact_digest != expected_artifact_digest:
        raise GbmapSourceAdmissionError("feature-identity artifact digest mismatch")
    document = _strict_json(raw_bytes)
    try:
        crosswalk = GbmapFeatureIdentityCrosswalk.model_validate(document, strict=False)
    except ValueError as exc:
        raise GbmapSourceAdmissionError("feature-identity artifact contract is invalid") from exc
    if canonical_json_bytes(crosswalk.model_dump(mode="json")) != raw_bytes:
        raise GbmapSourceAdmissionError("feature-identity artifact contains coerced values")
    if require_production_bindings:
        expected = (
            FEATURE_IDENTITY_CROSSWALK_ID,
            GBMAP_SOURCE_SHA256,
            GBMAP_FEATURE_ORDER_DIGEST,
            HGNC_SOURCE_ID,
            HGNC_SOURCE_SHA256,
            HGNC_SOURCE_BYTES,
            HGNC_ROW_COUNT,
            PRODUCTION_FEATURE_COUNT,
            EXPECTED_FEATURE_IDENTITY_CONTENT_DIGEST,
        )
        observed = (
            crosswalk.crosswalk_id,
            crosswalk.source.gbmap_source_sha256,
            crosswalk.source.gbmap_feature_order_digest,
            crosswalk.source.hgnc_source_id,
            crosswalk.source.hgnc_source_sha256,
            crosswalk.source.hgnc_source_bytes,
            crosswalk.source.hgnc_row_count,
            crosswalk.counts.source_feature_count,
            crosswalk.content_digest,
        )
        if observed != expected:
            raise GbmapSourceAdmissionError("feature-identity production binding mismatch")
    return crosswalk


@lru_cache(maxsize=1)
def production_feature_identity_crosswalk() -> GbmapFeatureIdentityCrosswalk:
    """Load the immutable public crosswalk bundled with this research package."""

    raw_bytes = files(__package__).joinpath(FEATURE_IDENTITY_RESOURCE).read_bytes()
    return load_feature_identity_crosswalk_bytes(
        raw_bytes,
        expected_artifact_digest=EXPECTED_FEATURE_IDENTITY_ARTIFACT_DIGEST,
    )


def require_stable_feature_indices(
    feature_ids: Sequence[str],
    crosswalk: GbmapFeatureIdentityCrosswalk | None = None,
) -> tuple[int, ...]:
    """Validate exact feature order and return only stable, model-eligible rows."""

    identity = production_feature_identity_crosswalk() if crosswalk is None else crosswalk
    observed = tuple(feature_ids)
    expected = tuple(entry.input_symbol for entry in identity.entries)
    if observed != expected:
        raise GbmapInputError("GBmap features do not match the locked HGNC crosswalk order")
    indices = identity.usable_feature_indices
    if not indices:
        raise GbmapInputError("GBmap HGNC crosswalk has no model-eligible features")
    return indices


__all__ = [
    "EXPECTED_FEATURE_IDENTITY_ARTIFACT_DIGEST",
    "EXPECTED_FEATURE_IDENTITY_CONTENT_DIGEST",
    "FEATURE_IDENTITY_CROSSWALK_ID",
    "FEATURE_IDENTITY_RESOURCE",
    "FEATURE_IDENTITY_SCHEMA",
    "GBMAP_FEATURE_ORDER_DIGEST",
    "GBMAP_SOURCE_SHA256",
    "HGNC_ROW_COUNT",
    "HGNC_SOURCE_BYTES",
    "HGNC_SOURCE_ID",
    "HGNC_SOURCE_SHA256",
    "PRODUCTION_FEATURE_COUNT",
    "FeatureIdentityCounts",
    "FeatureIdentityEntry",
    "FeatureIdentityMatch",
    "FeatureIdentityPolicy",
    "FeatureIdentitySource",
    "GbmapFeatureIdentityCrosswalk",
    "HgncIdentityRecord",
    "build_feature_identity_crosswalk",
    "feature_identity_content_digest",
    "load_feature_identity_crosswalk_bytes",
    "parse_hgnc_complete_set",
    "production_feature_identity_crosswalk",
    "require_stable_feature_indices",
]
