"""Architecture guards for the additive, non-governed research namespace.

The research pipeline is intentionally useful without becoming an accidental
implementation of a frozen M03/M04/M05 contract. These tests make that
boundary executable: governed module code may not import the research
namespace, and the public application may expose only the explicitly bounded
proteogenomic-state research surface.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

from glio_proteogen.adapters.api import create_app

if TYPE_CHECKING:
    from collections.abc import Iterator

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src" / "glio_proteogen"
_GOVERNED_ROOTS = (
    _SRC_ROOT / "modules" / "c03_protein_inference",
    _SRC_ROOT / "modules" / "c04_proteoform_isoform",
    _SRC_ROOT / "modules" / "c05_ptm_localization",
)
_RESEARCH_PREFIX = "/v1/research/proteogenomic-state"
_FUNCTIONAL_PROTEOTYPE_RESEARCH_PREFIX = "/v1/research/gbm-functional-proteotype"
_GBM_RESEARCH_PREFIX = "/v1/research/gbm-proteomic-axes"
_NEFTEL_RESEARCH_PREFIX = "/v1/research/neftel-protein-programs"
_MASTER_KINASE_RESEARCH_PREFIX = "/v1/research/gbm-master-kinases"
_GBM_RNA_PURITY_RESEARCH_PREFIX = "/v1/research/gbm-rna-purity"
_LONGITUDINAL_RESEARCH_PREFIX = "/v1/research/longitudinal-gbm"
_PHOSPHO_RESEARCH_PREFIX = "/v1/research/longitudinal-gbm-phospho"
_KINASE_TRANSITION_RESEARCH_PREFIX = "/v1/research/longitudinal-gbm-kinase-transition"
_NEFTEL_TRANSITION_RESEARCH_PREFIX = "/v1/research/longitudinal-gbm-neftel-transition"
_REACTOME_TRANSITION_RESEARCH_PREFIX = "/v1/research/longitudinal-gbm-reactome-transition"
_COMPLEX_TRANSITION_RESEARCH_PREFIX = "/v1/research/longitudinal-gbm-complex-transition"
_FACTOR_GRAPH_RESEARCH_PREFIX = "/v1/research/gbm-factor-graph"
_M09_RESEARCH_PREFIX = "/v2/research/modules/m09/complex-transition-concordance"
_M10_RESEARCH_PREFIX = "/v2/research/modules/m10/functional-proteotype"
_M11_RESEARCH_PREFIX = "/v2/research/modules/m11/protein-native-subtype"
_M14_RESEARCH_PREFIX = "/v2/research/modules/m14/microenvironment-protein-programs"
_M15_RESEARCH_PREFIX = "/v2/research/modules/m15/longitudinal-recurrence-proteotype"
_RESEARCH_PATHS = {
    f"{prefix}/{suffix}"
    for prefix in (
        _RESEARCH_PREFIX,
        _FUNCTIONAL_PROTEOTYPE_RESEARCH_PREFIX,
        _GBM_RESEARCH_PREFIX,
        _NEFTEL_RESEARCH_PREFIX,
        _MASTER_KINASE_RESEARCH_PREFIX,
        _GBM_RNA_PURITY_RESEARCH_PREFIX,
        _LONGITUDINAL_RESEARCH_PREFIX,
        _PHOSPHO_RESEARCH_PREFIX,
        _KINASE_TRANSITION_RESEARCH_PREFIX,
        _NEFTEL_TRANSITION_RESEARCH_PREFIX,
        _REACTOME_TRANSITION_RESEARCH_PREFIX,
        _COMPLEX_TRANSITION_RESEARCH_PREFIX,
        _FACTOR_GRAPH_RESEARCH_PREFIX,
        _M09_RESEARCH_PREFIX,
        _M10_RESEARCH_PREFIX,
        _M11_RESEARCH_PREFIX,
        _M14_RESEARCH_PREFIX,
        _M15_RESEARCH_PREFIX,
    )
    for suffix in ("profile", "demo", "analyze", "verify")
}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def _application_routes(application: object) -> Iterator[object]:
    pending = list(getattr(application, "routes", ()))
    while pending:
        route = pending.pop()
        included = getattr(route, "original_router", None)
        if included is not None:
            pending.extend(getattr(included, "routes", ()))
        else:
            yield route


def test_governed_modules_cannot_import_research_namespace() -> None:
    """Prevent research computation from becoming a governed dependency."""

    paths = [file for root in _GOVERNED_ROOTS for file in root.rglob("*.py")]
    violations = {
        str(path.relative_to(_REPO_ROOT)): module
        for path in paths
        for module in _imported_modules(path)
        if module == "glio_proteogen.research" or module.startswith("glio_proteogen.research.")
    }
    assert violations == {}


def test_public_fastapi_exposes_only_the_bounded_research_surface(tmp_path: Path) -> None:
    """Keep research computation behind the dedicated typed adapter."""

    application = create_app(tmp_path / "events.sqlite3")
    research_routes: dict[str, str] = {}
    for route in _application_routes(application):
        path = getattr(route, "path", "")
        endpoint = getattr(route, "endpoint", None)
        endpoint_module = getattr(endpoint, "__module__", "")
        if "/research" in path.lower():
            research_routes[path] = endpoint_module
    assert set(research_routes) == _RESEARCH_PATHS
    assert set(research_routes.values()) == {
        "glio_proteogen.adapters.gbm_functional_proteotype",
        "glio_proteogen.adapters.gbm_master_kinases",
        "glio_proteogen.adapters.gbm_rna_purity",
        "glio_proteogen.adapters.glioma_models",
        "glio_proteogen.adapters.neftel_programs",
        "glio_proteogen.adapters.research_state",
        "glio_proteogen.adapters.longitudinal_gbm",
        "glio_proteogen.adapters.longitudinal_gbm_phospho",
        "glio_proteogen.adapters.longitudinal_gbm_kinase_transition",
        "glio_proteogen.adapters.longitudinal_gbm_neftel_transition",
        "glio_proteogen.adapters.longitudinal_gbm_reactome_transition",
        "glio_proteogen.adapters.longitudinal_gbm_complex_transition",
        "glio_proteogen.adapters.gbm_factor_graph",
        "glio_proteogen.adapters.m10_functional_proteotype_facade",
        "glio_proteogen.adapters.m11_protein_native_subtype_facade",
        "glio_proteogen.adapters.m14_microenvironment_protein_programs_facade",
    }
