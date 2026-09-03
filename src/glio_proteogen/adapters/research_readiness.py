"""Adapter-owned readiness checks for mounted fitted research profiles.

The central API must not import research implementations across the governance
firewall.  This registry therefore preflights profiles only through their
public adapter boundaries.  Facade profiles embed and validate their exact
delegated v1 profile, so one check can cover both mounted route surfaces
without resolving the same fitted profile twice.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from fastapi import Response

from glio_proteogen.adapters import (
    gbm_factor_graph,
    gbm_functional_proteotype,
    gbm_master_kinases,
    gbm_rna_purity,
    glioma_models,
    longitudinal_gbm,
    longitudinal_gbm_complex_transition,
    longitudinal_gbm_kinase_transition,
    longitudinal_gbm_neftel_transition,
    longitudinal_gbm_phospho,
    longitudinal_gbm_reactome_transition,
    m10_functional_proteotype_facade,
    m11_protein_native_subtype_facade,
    m14_microenvironment_protein_programs_facade,
    neftel_programs,
    research_state,
)

type ReadinessCallable = Callable[[], object]
type ProfileEndpoint = Callable[[Response], object]

RESEARCH_READINESS_REGISTRY_LANE_ID: Final = "research-readiness-registry"


@dataclass(frozen=True, slots=True)
class ResearchReadinessCheck:
    """One unique fitted-profile check and every route surface it covers."""

    lane_id: str
    profile_routes: tuple[str, ...]
    check: ReadinessCallable


class ResearchReadinessError(RuntimeError):
    """Sanitized failure containing only the stable public lane identifier."""

    lane_id: str

    def __init__(self, lane_id: str) -> None:
        self.lane_id = lane_id
        super().__init__(f"research lane is not ready: {lane_id}")


def _profile_check(endpoint: ProfileEndpoint) -> ReadinessCallable:
    def check() -> object:
        return endpoint(Response())

    return check


def _profile_route(route_prefix: str) -> str:
    return f"{route_prefix}/profile"


RESEARCH_READINESS_CHECKS: Final[tuple[ResearchReadinessCheck, ...]] = (
    ResearchReadinessCheck(
        lane_id="proteogenomic-state",
        profile_routes=(_profile_route(research_state.RESEARCH_STATE_ROUTE_PREFIX),),
        check=research_state.ensure_research_state_ready,
    ),
    ResearchReadinessCheck(
        lane_id="gbm-functional-proteotype",
        profile_routes=(
            _profile_route(gbm_functional_proteotype.GBM_FUNCTIONAL_PROTEOTYPE_ROUTE_PREFIX),
            _profile_route(m10_functional_proteotype_facade.M10_FUNCTIONAL_PROTEOTYPE_ROUTE_PREFIX),
        ),
        check=_profile_check(m10_functional_proteotype_facade.profile),
    ),
    ResearchReadinessCheck(
        lane_id="gbm-proteomic-axes",
        profile_routes=(
            _profile_route(glioma_models.GBM_AXES_ROUTE_PREFIX),
            _profile_route(
                m11_protein_native_subtype_facade.M11_PROTEIN_NATIVE_SUBTYPE_ROUTE_PREFIX
            ),
        ),
        check=_profile_check(m11_protein_native_subtype_facade.profile),
    ),
    ResearchReadinessCheck(
        lane_id="neftel-protein-programs",
        profile_routes=(
            _profile_route(neftel_programs.NEFTEL_PROGRAMS_ROUTE_PREFIX),
            _profile_route(
                m14_microenvironment_protein_programs_facade.M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_ROUTE_PREFIX
            ),
        ),
        check=_profile_check(m14_microenvironment_protein_programs_facade.profile),
    ),
    ResearchReadinessCheck(
        lane_id="gbm-master-kinases",
        profile_routes=(_profile_route(gbm_master_kinases.GBM_MASTER_KINASES_ROUTE_PREFIX),),
        check=_profile_check(gbm_master_kinases.profile),
    ),
    ResearchReadinessCheck(
        lane_id="gbm-rna-purity",
        profile_routes=(_profile_route(gbm_rna_purity.GBM_RNA_PURITY_ROUTE_PREFIX),),
        check=_profile_check(gbm_rna_purity.profile),
    ),
    ResearchReadinessCheck(
        lane_id="longitudinal-gbm",
        profile_routes=(
            _profile_route(longitudinal_gbm.LONGITUDINAL_GBM_ROUTE_PREFIX),
            _profile_route(longitudinal_gbm.M15_LONGITUDINAL_RECURRENCE_ROUTE_PREFIX),
        ),
        check=_profile_check(longitudinal_gbm.m15_profile),
    ),
    ResearchReadinessCheck(
        lane_id="longitudinal-gbm-phospho",
        profile_routes=(
            _profile_route(longitudinal_gbm_phospho.LONGITUDINAL_GBM_PHOSPHO_ROUTE_PREFIX),
        ),
        check=_profile_check(longitudinal_gbm_phospho.profile),
    ),
    ResearchReadinessCheck(
        lane_id="longitudinal-gbm-kinase-transition",
        profile_routes=(
            _profile_route(
                longitudinal_gbm_kinase_transition.LONGITUDINAL_GBM_KINASE_TRANSITION_ROUTE_PREFIX
            ),
        ),
        check=_profile_check(longitudinal_gbm_kinase_transition.profile),
    ),
    ResearchReadinessCheck(
        lane_id="longitudinal-gbm-neftel-transition",
        profile_routes=(
            _profile_route(
                longitudinal_gbm_neftel_transition.LONGITUDINAL_GBM_NEFTEL_TRANSITION_ROUTE_PREFIX
            ),
        ),
        check=_profile_check(longitudinal_gbm_neftel_transition.profile),
    ),
    ResearchReadinessCheck(
        lane_id="longitudinal-gbm-reactome-transition",
        profile_routes=(
            _profile_route(
                longitudinal_gbm_reactome_transition.LONGITUDINAL_GBM_REACTOME_TRANSITION_ROUTE_PREFIX
            ),
        ),
        check=_profile_check(longitudinal_gbm_reactome_transition.profile),
    ),
    ResearchReadinessCheck(
        lane_id="longitudinal-gbm-complex-transition",
        profile_routes=(
            _profile_route(
                longitudinal_gbm_complex_transition.LONGITUDINAL_GBM_COMPLEX_TRANSITION_ROUTE_PREFIX
            ),
            _profile_route(longitudinal_gbm_complex_transition.M09_COMPLEX_TRANSITION_ROUTE_PREFIX),
        ),
        check=_profile_check(longitudinal_gbm_complex_transition.m09_profile),
    ),
    ResearchReadinessCheck(
        lane_id="gbm-factor-graph",
        profile_routes=(_profile_route(gbm_factor_graph.GBM_FACTOR_GRAPH_ROUTE_PREFIX),),
        check=_profile_check(gbm_factor_graph.profile),
    ),
)

RESEARCH_PROFILE_ROUTES: Final[tuple[str, ...]] = tuple(
    route
    for readiness_check in RESEARCH_READINESS_CHECKS
    for route in readiness_check.profile_routes
)


def ensure_research_profiles_ready() -> None:
    """Run every unique profile preflight, then fail closed on the first bad lane."""

    failed_lane_id: str | None = None
    for readiness_check in RESEARCH_READINESS_CHECKS:
        try:
            readiness_check.check()
        except Exception:  # noqa: BLE001 - adapter failures must not escape this boundary.
            if failed_lane_id is None:
                failed_lane_id = readiness_check.lane_id
    if failed_lane_id is not None:
        raise ResearchReadinessError(failed_lane_id) from None


__all__ = [
    "RESEARCH_PROFILE_ROUTES",
    "RESEARCH_READINESS_CHECKS",
    "RESEARCH_READINESS_REGISTRY_LANE_ID",
    "ResearchReadinessCheck",
    "ResearchReadinessError",
    "ensure_research_profiles_ready",
]
