"""Source-locked Neftel protein programs coupled through a GBM state graph.

The Neftel lane supplies measured bulk-protein program evidence.  This bridge
does not pretend those programs are cell fractions: it projects complete
location and competitive-rank MES and OPC program-family estimates into a
small, signed glioma microenvironment graph and lets ECGI propagate uncertainty through hypoxia,
angiogenesis, myeloid, endothelial, T-cell, and molecular-program relationships. Missing source
families remain missing and never become negative observations.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Final, Literal, Self

from pydantic import Field, model_validator

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import FrozenModel, Identifier, NonEmptyStr, Sha256Digest
from glio_proteogen.research.gbm_proteomic_axes import (
    GbmProteomicAxesRequest,
    GbmProteomicAxesResult,
    GbmReplayVerificationRequest,
    analyze_gbm_proteomic_axes,
    verify_gbm_proteomic_axes_replay,
)
from glio_proteogen.research.gbm_proteomic_axes import (
    synthetic_demo_request as gbm_axes_demo_request,
)
from glio_proteogen.research.neftel_protein_programs import (
    MethodEstimate,
    ProteinEvidenceState,
    ProteinProgramObservation,
    ProteinProgramRequest,
    ProteinProgramResult,
    analyze_neftel_protein_programs,
    marker_catalog,
    verify_neftel_protein_program_replay,
)
from glio_proteogen.research.neftel_protein_programs import (
    ReplayVerificationRequest as NeftelReplayVerificationRequest,
)
from glio_proteogen.research.neftel_protein_programs import (
    algorithm_profile as neftel_algorithm_profile,
)
from glio_proteogen.research.neftel_protein_programs import (
    synthetic_demo_request as neftel_demo_request,
)
from glio_proteogen.research.proteogenomic_state import (
    EdgeKind,
    EvidenceModality,
    EvidenceObservation,
    EvidenceState,
    GraphEdge,
    GraphNode,
    NodeKind,
    ProteogenomicStateRequest,
    ProteogenomicStateResult,
    PublicTopologySource,
    TopologyProvenance,
    analyze_proteogenomic_state,
    graph_topology_digest,
    verify_proteogenomic_replay,
)
from glio_proteogen.research.proteogenomic_state import (
    ReplayVerificationRequest as EcgiReplayVerificationRequest,
)
from glio_proteogen.research.proteogenomic_state import (
    algorithm_profile as ecgi_algorithm_profile,
)

ALGORITHM_ID: Final = "gbm-microenvironment-graph"
ALGORITHM_VERSION: Final = "1.0.0"
PROFILE_ID: Final = "gbm-microenvironment-graph/1.0.0"
MAX_REQUEST_BYTES: Final = 2 * 1_024 * 1_024
MAX_RESULT_BYTES: Final = 4 * 1_024 * 1_024
MAX_REPLAY_BYTES: Final = 8 * 1_024 * 1_024
_ZERO_DIGEST: Final = "sha256:" + "0" * 64
_BRIDGE_DEMO_SOURCE_DIGEST: Final = sha256_digest(
    {
        "demo_id": "synthetic-gbm-microenvironment-graph-v1",
        "source": "neftel-table-s2-protein-catalog-v1",
        "purpose": "synthetic_mesenchymal_opc_projection",
    }
)

_PROGRAM_MAP: Final = (
    ("mesenchymal_like", "mesenchymal"),
    ("oligodendrocyte_progenitor_like", "opc_like"),
)
_GRAPH_PROGRAMS: Final = (
    "mesenchymal",
    "myeloid",
    "t_cell",
    "endothelial",
    "hypoxia",
    "angiogenic",
    "opc_like",
    "kras_targets",
    "myc_targets",
    "neural",
    "proneural",
    "egfr_targets",
)
_GRAPH_EDGES: Final = (
    ("hypoxia", "angiogenic", 1),
    ("hypoxia", "mesenchymal", 1),
    ("mesenchymal", "myeloid", 1),
    ("myeloid", "t_cell", -1),
    ("opc_like", "mesenchymal", -1),
    ("angiogenic", "endothelial", 1),
)
_AXIS_MAP: Final = (
    ("SWEET_KRAS_TARGETS_UP", "kras_targets"),
    ("HALLMARK_MYC_TARGETS_V1", "myc_targets"),
    ("WINTER_HYPOXIA_UP", "hypoxia"),
    ("VERHAAK_GLIOBLASTOMA_MESENCHYMAL", "mesenchymal"),
    ("VERHAAK_GLIOBLASTOMA_NEURAL", "neural"),
    ("VERHAAK_GLIOBLASTOMA_PRONEURAL", "proneural"),
    ("EGFR_UP.V1_UP", "egfr_targets"),
)
_AUXILIARY_STANDARD_ERROR_FLOOR: Final = 0.35
_SOURCE_LOCATION_STANDARD_ERROR_FLOOR: Final = 0.05
_SOURCE_RANK_STANDARD_ERROR_FLOOR: Final = 0.10


class MicroenvironmentGraphProfile(FrozenModel):
    """Digest-bound profile for the source evidence to graph projection."""

    profile_id: Literal["gbm-microenvironment-graph/1.0.0"] = PROFILE_ID
    algorithm_id: Literal["gbm-microenvironment-graph"] = ALGORITHM_ID
    algorithm_version: Literal["1.0.0"] = ALGORITHM_VERSION
    source_engine: Literal["neftel-bulk-protein-programs/1.0.0"] = (
        "neftel-bulk-protein-programs/1.0.0"
    )
    graph_engine: Literal["glio-ecgi/1.0.0"] = "glio-ecgi/1.0.0"
    auxiliary_source_engine: Literal["gbm-proteomic-axes/1.0.0"] = (
        "gbm-proteomic-axes/1.0.0"
    )
    source_profile_digest: Sha256Digest
    graph_profile_digest: Sha256Digest
    topology_digest: Sha256Digest
    projection_policy: Literal[
        "bulk_program_location_and_rank_to_signed_microenvironment_graph_v2"
    ] = (
        "bulk_program_location_and_rank_to_signed_microenvironment_graph_v2"
    )
    auxiliary_projection_policy: Literal[
        "independent_published_gbm_axes_as_secondary_observations_v1"
    ] = "independent_published_gbm_axes_as_secondary_observations_v1"
    projected_axis_signatures: tuple[tuple[NonEmptyStr, NonEmptyStr], ...] = _AXIS_MAP
    auxiliary_standard_error_floor: float = Field(
        default=_AUXILIARY_STANDARD_ERROR_FLOOR,
        ge=_AUXILIARY_STANDARD_ERROR_FLOOR,
        le=_AUXILIARY_STANDARD_ERROR_FLOOR,
    )
    source_location_standard_error_floor: float = Field(
        default=_SOURCE_LOCATION_STANDARD_ERROR_FLOOR,
        ge=_SOURCE_LOCATION_STANDARD_ERROR_FLOOR,
        le=_SOURCE_LOCATION_STANDARD_ERROR_FLOOR,
    )
    source_rank_standard_error_floor: float = Field(
        default=_SOURCE_RANK_STANDARD_ERROR_FLOOR,
        ge=_SOURCE_RANK_STANDARD_ERROR_FLOOR,
        le=_SOURCE_RANK_STANDARD_ERROR_FLOOR,
    )
    source_location_quality_supported: float = Field(default=1.0, ge=0.0, le=1.0)
    source_location_quality_limited: float = Field(default=0.5, ge=0.0, le=1.0)
    source_rank_quality_supported: float = Field(default=0.85, ge=0.0, le=1.0)
    source_rank_quality_limited: float = Field(default=0.40, ge=0.0, le=1.0)
    supported_source_families: tuple[Literal["mesenchymal_like", "oligodendrocyte_progenitor_like"], ...] = (
        "mesenchymal_like",
        "oligodendrocyte_progenitor_like",
    )
    missing_families_are_not_negative: Literal[True] = True
    cell_fraction_claim_permitted: Literal[False] = False
    clinical_use_permitted: Literal[False] = False
    profile_digest: Sha256Digest

    @model_validator(mode="after")
    def digest_is_bound(self) -> Self:
        if self.profile_digest != _profile_digest(self):
            raise ValueError("microenvironment graph profile digest does not match constants")
        return self


class MicroenvironmentGraphRequest(FrozenModel):
    """One source request to project into the signed microenvironment graph."""

    profile_id: Literal["gbm-microenvironment-graph/1.0.0"] = PROFILE_ID
    sample_id: Identifier
    source_request: ProteinProgramRequest
    axis_request: GbmProteomicAxesRequest | None = None

    @model_validator(mode="after")
    def sample_id_matches_source(self) -> Self:
        if self.sample_id != self.source_request.sample_id:
            raise ValueError("sample_id must match the nested Neftel source request")
        if self.axis_request is not None and self.sample_id != self.axis_request.sample_id:
            raise ValueError("sample_id must match the nested GBM axes request")
        return self

    @property
    def request_digest(self) -> Sha256Digest:
        return canonical_request_digest(self)


class MicroenvironmentGraphResult(FrozenModel):
    """Replay-closed source evidence and graph inference receipt."""

    profile_id: Literal["gbm-microenvironment-graph/1.0.0"] = PROFILE_ID
    profile_digest: Sha256Digest
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    sample_id: Identifier
    source_result: ProteinProgramResult
    axis_result: GbmProteomicAxesResult | None = None
    graph_request: ProteogenomicStateRequest
    graph_result: ProteogenomicStateResult
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=12)
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True

    @model_validator(mode="after")
    def receipt_is_closed(self) -> Self:
        if self.sample_id != self.source_result.sample_id or self.sample_id != self.graph_result.sample_id:
            raise ValueError("all bridge receipts must use one sample identifier")
        if self.axis_result is not None and self.axis_result.sample_id != self.sample_id:
            raise ValueError("axis result must use the bridge sample identifier")
        if self.graph_request.request_digest != self.graph_result.request_digest:
            raise ValueError("graph request and graph result digests do not match")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("microenvironment graph result digest does not match content")
        return self


class MicroenvironmentGraphReplayRequest(FrozenModel):
    request: MicroenvironmentGraphRequest
    result: MicroenvironmentGraphResult


class MicroenvironmentGraphReplayResult(FrozenModel):
    verified: bool
    request_digest_match: bool
    source_replay_match: bool
    axis_replay_match: bool
    graph_replay_match: bool
    result_digest_match: bool
    semantic_match: bool
    recomputed_request_digest: Sha256Digest
    recomputed_result_digest: Sha256Digest
    message: NonEmptyStr


def canonical_request_digest(request: MicroenvironmentGraphRequest) -> Sha256Digest:
    return sha256_digest(
        {
            "profile_id": PROFILE_ID,
            "sample_id": request.sample_id,
            "source_request": request.source_request.model_dump(mode="json"),
            "axis_request": (
                None
                if request.axis_request is None
                else request.axis_request.model_dump(mode="json")
            ),
        }
    )


def result_payload_digest(result: MicroenvironmentGraphResult) -> Sha256Digest:
    payload = result.model_dump(mode="json")
    payload.pop("result_digest", None)
    return sha256_digest(payload)


def _profile_digest(profile: MicroenvironmentGraphProfile | dict[str, object]) -> Sha256Digest:
    payload = profile.model_dump(mode="json") if isinstance(profile, MicroenvironmentGraphProfile) else dict(profile)
    payload.pop("profile_digest", None)
    return sha256_digest(payload)


@lru_cache(maxsize=1)
def microenvironment_graph_profile() -> MicroenvironmentGraphProfile:
    source = neftel_algorithm_profile()
    graph = ecgi_algorithm_profile()
    payload = {
        "profile_id": PROFILE_ID,
        "algorithm_id": ALGORITHM_ID,
        "algorithm_version": ALGORITHM_VERSION,
        "source_engine": "neftel-bulk-protein-programs/1.0.0",
        "graph_engine": "glio-ecgi/1.0.0",
        "auxiliary_source_engine": "gbm-proteomic-axes/1.0.0",
        "source_profile_digest": source.profile_digest,
        "graph_profile_digest": graph.profile_digest,
        "topology_digest": _bridge_topology_digest(),
        "projection_policy": "bulk_program_location_and_rank_to_signed_microenvironment_graph_v2",
        "auxiliary_projection_policy": "independent_published_gbm_axes_as_secondary_observations_v1",
        "projected_axis_signatures": _AXIS_MAP,
        "auxiliary_standard_error_floor": _AUXILIARY_STANDARD_ERROR_FLOOR,
        "source_location_standard_error_floor": _SOURCE_LOCATION_STANDARD_ERROR_FLOOR,
        "source_rank_standard_error_floor": _SOURCE_RANK_STANDARD_ERROR_FLOOR,
        "source_location_quality_supported": 1.0,
        "source_location_quality_limited": 0.5,
        "source_rank_quality_supported": 0.85,
        "source_rank_quality_limited": 0.40,
        "supported_source_families": tuple(item[0] for item in _PROGRAM_MAP),
        "missing_families_are_not_negative": True,
        "cell_fraction_claim_permitted": False,
        "clinical_use_permitted": False,
    }
    profile_digest = _profile_digest(payload)
    return MicroenvironmentGraphProfile(
        profile_id=PROFILE_ID,
        algorithm_id=ALGORITHM_ID,
        algorithm_version=ALGORITHM_VERSION,
        source_engine="neftel-bulk-protein-programs/1.0.0",
        graph_engine="glio-ecgi/1.0.0",
        auxiliary_source_engine="gbm-proteomic-axes/1.0.0",
        source_profile_digest=source.profile_digest,
        graph_profile_digest=graph.profile_digest,
        topology_digest=_bridge_topology_digest(),
        projection_policy="bulk_program_location_and_rank_to_signed_microenvironment_graph_v2",
        auxiliary_projection_policy="independent_published_gbm_axes_as_secondary_observations_v1",
        projected_axis_signatures=_AXIS_MAP,
        auxiliary_standard_error_floor=_AUXILIARY_STANDARD_ERROR_FLOOR,
        source_location_standard_error_floor=_SOURCE_LOCATION_STANDARD_ERROR_FLOOR,
        source_rank_standard_error_floor=_SOURCE_RANK_STANDARD_ERROR_FLOOR,
        source_location_quality_supported=1.0,
        source_location_quality_limited=0.5,
        source_rank_quality_supported=0.85,
        source_rank_quality_limited=0.40,
        supported_source_families=("mesenchymal_like", "oligodendrocyte_progenitor_like"),
        missing_families_are_not_negative=True,
        cell_fraction_claim_permitted=False,
        clinical_use_permitted=False,
        profile_digest=profile_digest,
    )


def _node_id(program: str) -> str:
    return f"pathway.gbm_microenvironment.{program}"


def _graph_nodes() -> tuple[GraphNode, ...]:
    return tuple(
        GraphNode(node_id=_node_id(program), kind=NodeKind.PATHWAY, display_name=program)
        for program in _GRAPH_PROGRAMS
    )


def _graph_edges() -> tuple[GraphEdge, ...]:
    return tuple(
        GraphEdge(
            edge_id=f"edge.gbm_microenvironment.{index}",
            source_id=_node_id(source_program),
            target_id=_node_id(target_program),
            kind=EdgeKind.REGULATES,
            sign=sign,  # type: ignore[arg-type]
            weight=1.0,
        )
        for index, (source_program, target_program, sign) in enumerate(_GRAPH_EDGES)
    )


@lru_cache(maxsize=1)
def _bridge_topology_digest() -> Sha256Digest:
    return graph_topology_digest({"nodes": _graph_nodes(), "edges": _graph_edges()})


def _topology_provenance() -> TopologyProvenance:
    """Bind the abstraction to public Reactome context without claiming export parity."""

    scopes = tuple(_node_id(program) for program in _GRAPH_PROGRAMS)
    source_rows = (
        (
            "reactome.R-HSA-177929.release97",
            "R-HSA-177929",
            "Signaling by EGFR",
            715_097,
            "8bfd16fd5aa56ac37ff1d3e8e1bc8a14f27d5ca9cf4204bcfc2231e004823260",
        ),
        (
            "reactome.R-HSA-1257604.release97",
            "R-HSA-1257604",
            "PIP3 activates AKT signaling",
            1_085_445,
            "8274c7abb68f83738c46b7156f81f2546a51720f57ef5997c1353de92aeb4c1a",
        ),
        (
            "reactome.R-HSA-69278.release97",
            "R-HSA-69278",
            "Cell Cycle, Mitotic",
            3_546_893,
            "5c14a87dc086a50327c09191e001d7d1cb86231eaf34646cc8f4c3555df62ad4",
        ),
    )
    sources = tuple(
        PublicTopologySource(
            source_id=source_id,
            resource_name="Reactome",
            resource_release="97",
            record_id=record_id,
            record_title=record_title,
            source_uri=f"https://reactome.org/ContentService/exporter/event/{record_id}.sbml",
            source_format="SBML Level 3 Version 1",
            source_digest=f"sha256:{digest}",
            source_size_bytes=size_bytes,
            license_id="CC0-1.0",
            license_uri="https://creativecommons.org/publicdomain/zero/1.0/",
            retrieved_on="2026-08-27",
            scope_node_ids=scopes,
        )
        for source_id, record_id, record_title, size_bytes, digest in source_rows
    )
    return TopologyProvenance(
        topology_digest=_bridge_topology_digest(),
        derivation="synthetic_abstraction",
        sources=sources,
        curation_note=(
            "Reactome records provide public biological context for this repository-native "
            "GBM microenvironment abstraction; they are not a Reactome-exported graph."
        ),
    )


def _source_method_observation(
    graph_program: str,
    method: Literal["location", "rank"],
    estimate: MethodEstimate,
    source_digest: Sha256Digest,
) -> EvidenceObservation | None:
    """Project one complete Neftel method estimate without inventing support."""

    if (
        estimate.score is None
        or estimate.lower_bound is None
        or estimate.upper_bound is None
    ):
        return None
    standard_error_floor = (
        _SOURCE_LOCATION_STANDARD_ERROR_FLOOR
        if method == "location"
        else _SOURCE_RANK_STANDARD_ERROR_FLOOR
    )
    supported_quality = 1.0 if method == "location" else 0.85
    limited_quality = 0.5 if method == "location" else 0.40
    quality = supported_quality if estimate.support.value == "supported" else limited_quality
    suffix = "" if method == "location" else ".rank"
    return EvidenceObservation(
        observation_id=f"observation.gbm_microenvironment.{graph_program}{suffix}",
        node_id=_node_id(graph_program),
        modality=EvidenceModality.PROTEOMICS,
        state=EvidenceState.OBSERVED,
        standardized_effect=float(estimate.score),
        standard_error=max(
            standard_error_floor,
            abs(float(estimate.upper_bound) - float(estimate.lower_bound)) / 3.29,
        ),
        quality_weight=quality,
        provenance_digest=source_digest,
    )


def _graph_request(
    request: MicroenvironmentGraphRequest,
    source: ProteinProgramResult,
    axes: GbmProteomicAxesResult | None,
) -> ProteogenomicStateRequest:
    nodes = _graph_nodes()
    edges = _graph_edges()
    by_id = {str(item.program_id): item for item in source.program_evidence}
    family_to_graph = dict(_PROGRAM_MAP)
    observations: list[EvidenceObservation] = []
    for family, graph_program in family_to_graph.items():
        evidence = by_id.get(family)
        if evidence is None:
            observations.append(
                EvidenceObservation(
                    observation_id=f"observation.gbm_microenvironment.{graph_program}",
                    node_id=_node_id(graph_program),
                    modality=EvidenceModality.PROTEOMICS,
                    state=EvidenceState.MISSING,
                    quality_weight=0.0,
                    provenance_digest=source.result_digest,
                )
            )
            continue
        projected = (
            _source_method_observation(
                graph_program, "location", evidence.location, source.result_digest
            ),
            _source_method_observation(
                graph_program, "rank", evidence.rank_enrichment, source.result_digest
            ),
        )
        if all(item is None for item in projected):
            observations.append(
                EvidenceObservation(
                    observation_id=f"observation.gbm_microenvironment.{graph_program}",
                    node_id=_node_id(graph_program),
                    modality=EvidenceModality.PROTEOMICS,
                    state=EvidenceState.MISSING,
                    quality_weight=0.0,
                    provenance_digest=source.result_digest,
                )
            )
        else:
            observations.extend(item for item in projected if item is not None)
    if axes is not None:
        by_signature = {str(item.signature_id): item for item in axes.signatures}
        for signature_id, graph_program in _AXIS_MAP:
            estimate = by_signature.get(signature_id)
            if estimate is None or estimate.published_score is None:
                continue
            axis_lower = estimate.lower_bound
            axis_upper = estimate.upper_bound
            standard_error = (
                _AUXILIARY_STANDARD_ERROR_FLOOR
                if axis_lower is None or axis_upper is None
                else max(
                    _AUXILIARY_STANDARD_ERROR_FLOOR,
                    abs(float(axis_upper) - float(axis_lower)) / 3.29,
                )
            )
            quality = 0.9 if estimate.support.value == "supported" else 0.55
            observations.append(
                EvidenceObservation(
                    observation_id=f"observation.gbm_microenvironment.axis.{graph_program}",
                    node_id=_node_id(graph_program),
                    modality=EvidenceModality.PROTEOMICS,
                    state=EvidenceState.OBSERVED,
                    standardized_effect=float(estimate.published_score),
                    standard_error=standard_error,
                    quality_weight=quality,
                    provenance_digest=axes.result_digest,
                )
            )
    graph_request = ProteogenomicStateRequest(
        sample_id=request.sample_id,
        nodes=nodes,
        edges=edges,
        observations=tuple(observations),
        bootstrap_replicates=request.source_request.bootstrap_replicates,
        permutation_replicates=request.source_request.permutation_replicates,
    )
    return graph_request.model_copy(update={"topology_provenance": _topology_provenance()})


def analyze_microenvironment_graph(request: MicroenvironmentGraphRequest) -> MicroenvironmentGraphResult:
    """Fit source-locked Neftel evidence, then propagate it through ECGI."""

    request = MicroenvironmentGraphRequest.model_validate(request, strict=True)
    source = analyze_neftel_protein_programs(request.source_request)
    axes = (
        None
        if request.axis_request is None
        else analyze_gbm_proteomic_axes(request.axis_request)
    )
    graph_request = _graph_request(request, source, axes)
    graph_result = analyze_proteogenomic_state(graph_request)
    profile = microenvironment_graph_profile()
    draft = MicroenvironmentGraphResult.model_construct(
        profile_digest=profile.profile_digest,
        request_digest=request.request_digest,
        result_digest=_ZERO_DIGEST,
        sample_id=request.sample_id,
        source_result=source,
        axis_result=axes,
        graph_request=graph_request,
        graph_result=graph_result,
        limitations=(
            "The source engine estimates bulk protein program evidence, not cell fractions.",
            "Only mesenchymal-like and oligodendrocyte-progenitor-like families are projected; missing families remain missing.",
            "Location and competitive-rank source estimates are retained as separate observations with profile-bound floors and quality weights; they are not silently averaged before ECGI.",
            "Published GBM proteomic-axis scores are independent secondary observations for seven GBM molecular-program nodes; they never override Neftel evidence.",
            "Secondary published-axis observations use a profile-bound 0.35 standard-error floor to cover cross-engine scale and calibration uncertainty; their narrow bootstrap width is not treated as full uncertainty.",
            "The signed graph describes research associations and does not establish causality, prognosis, or treatment response.",
            "All outputs are research-use-only and non-prescriptive.",
        ),
    )
    return draft.model_copy(update={"result_digest": result_payload_digest(draft)})


def verify_microenvironment_graph_replay(
    envelope: MicroenvironmentGraphReplayRequest,
) -> MicroenvironmentGraphReplayResult:
    """Recompute source and graph passes and compare the complete receipt."""

    request = envelope.request
    provided = envelope.result
    recomputed = analyze_microenvironment_graph(request)
    source_replay = verify_neftel_protein_program_replay(
        NeftelReplayVerificationRequest(
            request=request.source_request,
            result=provided.source_result,
        )
    )
    axis_replay_match = request.axis_request is None and provided.axis_result is None
    if request.axis_request is not None and provided.axis_result is not None:
        axis_replay_match = verify_gbm_proteomic_axes_replay(
            GbmReplayVerificationRequest(
                request=request.axis_request,
                result=provided.axis_result,
            )
        ).semantic_match
    graph_replay = verify_proteogenomic_replay(
        EcgiReplayVerificationRequest(
            request=provided.graph_request,
            result=provided.graph_result,
        )
    )
    request_match = provided.request_digest == request.request_digest == recomputed.request_digest
    result_match = provided.result_digest == result_payload_digest(provided) == recomputed.result_digest
    semantic_match = provided.model_dump(mode="json") == recomputed.model_dump(mode="json")
    verified = request_match and source_replay.semantic_match and axis_replay_match and graph_replay.semantic_match and result_match and semantic_match
    return MicroenvironmentGraphReplayResult(
        verified=verified,
        request_digest_match=request_match,
        source_replay_match=source_replay.semantic_match,
        axis_replay_match=axis_replay_match,
        graph_replay_match=graph_replay.semantic_match,
        result_digest_match=result_match,
        semantic_match=semantic_match,
        recomputed_request_digest=recomputed.request_digest,
        recomputed_result_digest=recomputed.result_digest,
        message=(
            "Replay exactly matches the Neftel-to-ECGI microenvironment receipt."
            if verified
            else "Replay differs from the supplied receipt; no graph claim is accepted."
        ),
    )


@lru_cache(maxsize=1)
def synthetic_microenvironment_graph_request() -> MicroenvironmentGraphRequest:
    """Return a synthetic bridge demo with explicit MES and OPC evidence.

    The base Neftel demo is AC-like.  This bridge adds disjoint, ranked MES and
    OPC protein markers so both graph-projected families are observable while
    preserving the catalog's exact source identities and all original controls.
    """

    source = neftel_demo_request()
    existing_symbols = {item.gene_symbol for item in source.observations}
    catalog = marker_catalog()
    mes_markers = tuple(
        marker.normalized_symbol
        for program_id in ("MES1", "MES2")
        for marker in catalog.programs[program_id]
        if marker.protein_eligible and marker.normalized_symbol not in existing_symbols
    )[:12]
    opc_markers = tuple(
        marker.normalized_symbol
        for marker in catalog.programs["OPC"]
        if marker.protein_eligible and marker.normalized_symbol not in existing_symbols
    )[:12]
    bridge_observations = tuple(
        ProteinProgramObservation(
            observation_id=f"demo.bridge.mes.{index:03d}",
            gene_symbol=symbol,
            state=ProteinEvidenceState.OBSERVED,
            standardized_effect=round(0.95 - index * 0.02, 6),
            standard_error=0.25,
            quality_weight=0.92,
            provenance_digest=_BRIDGE_DEMO_SOURCE_DIGEST,
        )
        for index, symbol in enumerate(mes_markers, start=1)
    ) + tuple(
        ProteinProgramObservation(
            observation_id=f"demo.bridge.opc.{index:03d}",
            gene_symbol=symbol,
            state=ProteinEvidenceState.OBSERVED,
            standardized_effect=round(-0.70 + index * 0.015, 6),
            standard_error=0.28,
            quality_weight=0.90,
            provenance_digest=_BRIDGE_DEMO_SOURCE_DIGEST,
        )
        for index, symbol in enumerate(opc_markers, start=1)
    )
    source = source.model_copy(update={"observations": source.observations + bridge_observations})
    axes = gbm_axes_demo_request().model_copy(update={"sample_id": source.sample_id})
    return MicroenvironmentGraphRequest(
        sample_id=source.sample_id,
        source_request=source,
        axis_request=axes,
    )


__all__ = [
    "ALGORITHM_ID",
    "ALGORITHM_VERSION",
    "MAX_REPLAY_BYTES",
    "MAX_REQUEST_BYTES",
    "MAX_RESULT_BYTES",
    "PROFILE_ID",
    "MicroenvironmentGraphProfile",
    "MicroenvironmentGraphReplayRequest",
    "MicroenvironmentGraphReplayResult",
    "MicroenvironmentGraphRequest",
    "MicroenvironmentGraphResult",
    "analyze_microenvironment_graph",
    "canonical_request_digest",
    "microenvironment_graph_profile",
    "result_payload_digest",
    "synthetic_microenvironment_graph_request",
    "verify_microenvironment_graph_replay",
]
