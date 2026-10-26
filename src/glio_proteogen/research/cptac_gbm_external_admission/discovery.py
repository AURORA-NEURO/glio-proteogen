"""Exact local admission of the separately profiled discovery CDAP source.

The frozen caller-trusted plan owns qualification and participant attribution.
This reader verifies the fixed source bytes and exact nonreference column/map
bindings. It selects Unshared Log Ratio without filling, converting or fitting.
The existing confirmatory profile and its public wrapper remain unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, NoReturn, SupportsIndex

from glio_proteogen.kernel.canonical import sha256_digest

from . import protein as _shared
from .contracts import PANEL, GeneIdentity, HgncReference, SourceLock
from .identity import HGNC_LOCK, read_locked_hgnc
from .protein import (
    PRIMARY_MEASURE,
    FloatArray,
    ProteinAdmissionError,
    ProteinAdmissionReceipt,
)
from .source import read_verified_source

PROFILE_ID: Final = "cptac-gbm-discovery-protein-admission/1.0.0"
PROTEIN_LOCK: Final = SourceLock(
    bytes=48_440_330,
    md5="ed614fb12f72b9db9bc4667b6d349949",
    sha256="fc7c7b595211b81482db9281fb1592e58492eef87ab7db1fd64f7e4ec3bc96bd",
)
SAMPLE_MAP_LOCK: Final = SourceLock(
    bytes=3_795,
    md5="b1a598ad26a66015f339366e44799d6a",
    sha256="faea4574cd423c54b064c201391a9591160dc98ac3b6a443adaf8975914d74d1",
)
_DISCOVERY_SHAPE: Final = _shared._ProteinShape(
    candidate_count=72,
    active_aliquots=110,
    withdrawn_aliquots=0,
    pool_targets=0,
    sample_map_plexes=11,
    biological_rows=10_977,
    trailing_blank_rows=1,
    expected_panel_features=frozenset(PANEL) - {"CDKN2B", "MDM2"},
)


@dataclass(frozen=True, slots=True)
class DiscoverySourceDescriptor:
    """Fixed source-schema counts; not a clinical or donor-independence claim."""

    profile_id: str
    study_accession: str
    candidate_count: int
    analytical_plexes: int
    nonreference_ratio_aliquots: int
    reference_channel_assignments_excluded: int
    ratio_pool_targets: int
    withdrawn_ratio_aliquots: int
    trailing_blank_map_records: int
    biological_feature_rows: int
    source_aggregate_rows_excluded: int
    expected_panel_features: tuple[str, ...]
    selected_measure: str
    measurement_axis: str
    candidate_role_authority: str


SOURCE_DESCRIPTOR: Final = DiscoverySourceDescriptor(
    profile_id=PROFILE_ID,
    study_accession="PDC000204",
    candidate_count=_DISCOVERY_SHAPE.candidate_count,
    analytical_plexes=_DISCOVERY_SHAPE.sample_map_plexes,
    nonreference_ratio_aliquots=_DISCOVERY_SHAPE.active_aliquots,
    reference_channel_assignments_excluded=_DISCOVERY_SHAPE.sample_map_plexes,
    ratio_pool_targets=_DISCOVERY_SHAPE.pool_targets,
    withdrawn_ratio_aliquots=_DISCOVERY_SHAPE.withdrawn_aliquots,
    trailing_blank_map_records=_DISCOVERY_SHAPE.trailing_blank_rows,
    biological_feature_rows=_DISCOVERY_SHAPE.biological_rows,
    source_aggregate_rows_excluded=len(_shared._AGGREGATES),
    expected_panel_features=tuple(
        gene for gene in PANEL if gene in _DISCOVERY_SHAPE.expected_panel_features
    ),
    selected_measure=PRIMARY_MEASURE,
    measurement_axis="cdap_unshared_log2_specimen_reference_ratio",
    candidate_role_authority="caller-trusted frozen Qualified Primary Tumor metadata plan",
)


@dataclass(frozen=True, slots=True)
class DiscoveryProteinAdmission:
    """Transient development inputs; only the aggregate receipt is serializable."""

    candidate_digest: str
    values: FloatArray = field(repr=False)
    identities: tuple[GeneIdentity | None, ...] = field(repr=False)
    receipt: ProteinAdmissionReceipt

    @property
    def source_descriptor(self) -> DiscoverySourceDescriptor:
        return SOURCE_DESCRIPTOR

    def __getstate__(self) -> NoReturn:
        raise TypeError("transient discovery protein admission cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("transient discovery protein admission cannot be serialized")


def _decode_discovery_contents(
    protein: bytes,
    sample_map: bytes,
    hgnc: HgncReference,
    candidate_aliquots: tuple[str, ...],
    *,
    shape: _shared._ProteinShape = _DISCOVERY_SHAPE,
) -> _shared._DecodedProtein:
    """Private synthetic oracle seam; production always uses the fixed profile."""
    if len(protein) > PROTEIN_LOCK.bytes or len(sample_map) > SAMPLE_MAP_LOCK.bytes:
        raise ProteinAdmissionError("discovery source contents exceed the admitted bound")
    return _shared._decode_protein_contents(
        protein, sample_map, hgnc, candidate_aliquots, shape=shape
    )


def admit_discovery_protein(
    *,
    protein_path: Path,
    sample_map_path: Path,
    hgnc_path: Path,
    candidate_aliquots: tuple[str, ...],
) -> DiscoveryProteinAdmission:
    """Verify fixed bytes and decode the ordered72 plan-selected nonreference inputs.

    The plan must establish Qualified Primary Tumor roles and exclude normal or
    disqualified aliases. This source reader checks exact channel occurrences;
    it does not infer metadata roles from labels, filenames or measurements.
    """
    _shared._validate_candidates(candidate_aliquots, _DISCOVERY_SHAPE)
    protein = read_verified_source(protein_path, PROTEIN_LOCK, max_bytes=PROTEIN_LOCK.bytes)
    sample_map = read_verified_source(
        sample_map_path, SAMPLE_MAP_LOCK, max_bytes=SAMPLE_MAP_LOCK.bytes
    )
    hgnc = read_locked_hgnc(hgnc_path)
    decoded = _decode_discovery_contents(protein, sample_map, hgnc, candidate_aliquots)
    candidate_digest = sha256_digest(candidate_aliquots)
    unavailable = sum(identity is None for identity in decoded.identities)
    receipt = ProteinAdmissionReceipt(
        profile_id=PROFILE_ID,
        protein_sha256=PROTEIN_LOCK.sha256,
        sample_map_sha256=SAMPLE_MAP_LOCK.sha256,
        hgnc_sha256=HGNC_LOCK.sha256,
        candidate_digest=candidate_digest,
        candidate_count=len(candidate_aliquots),
        biological_feature_rows=len(decoded.identities),
        identified_feature_rows=len(decoded.identities) - unavailable,
        unavailable_identity_rows=unavailable,
        source_aggregate_rows_excluded=len(_shared._AGGREGATES),
        withdrawn_aliquots_excluded=_DISCOVERY_SHAPE.withdrawn_aliquots,
        pool_targets_excluded=_DISCOVERY_SHAPE.pool_targets,
        finite_unshared_cells=decoded.finite_unshared,
        missing_unshared_cells=decoded.missing_unshared,
        finite_zero_unshared_cells=decoded.zero_unshared,
        finite_all_peptide_cells=decoded.finite_all_peptide,
        missing_all_peptide_cells=decoded.missing_all_peptide,
        panel_coverage=decoded.panel_coverage,
        limitations=(
            "This fixed source admits72 plan-selected protein columns, not a complete multimodal training cohort or external-validation cohort.",
            "Qualified Primary Tumor roles and specimen attribution are assertions of the caller-trusted frozen plan; this reader does not authenticate their issuer or infer roles from labels.",
            "Eleven POOL reference-channel assignments and all noncandidate aliases are excluded from the selected matrix; there is no POOL ratio-measurement target.",
            "Values remain CDAP median-normalized log2 specimen/common-reference Unshared Log Ratios; no conversion or imputation is performed.",
            "All-peptide Log Ratio is a separate coverage comparator and never fills a missing unshared value; structurally absent panel features remain absent.",
            "Stable HGNC authority and NCBI identity must agree; unresolved nonpanel identities remain None and cannot supply an approved gene.",
            "The discovery and confirmatory reference pools, historical processing, molecular disease class, treatment eligibility, donor independence, axis transport and reuse terms remain separately unadmitted.",
            "No modelling, performance comparison, mechanistic discovery, clinical prediction, support-gate relaxation or independent validation follows from this receipt.",
            "Source-derived values and private candidate bindings remain local_only_terms_unverified and must not be uploaded or committed.",
        ),
    )
    return DiscoveryProteinAdmission(candidate_digest, decoded.values, decoded.identities, receipt)


__all__ = [
    "PROFILE_ID",
    "PROTEIN_LOCK",
    "SAMPLE_MAP_LOCK",
    "SOURCE_DESCRIPTOR",
    "DiscoveryProteinAdmission",
    "DiscoverySourceDescriptor",
    "admit_discovery_protein",
]
