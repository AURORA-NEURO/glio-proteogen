"""Architecture-level firewall for governed C03/C04/C05 surfaces.

The research package is intentionally additive and non-governed.  The frozen
M03/M04/M05 contracts and their C03/C04/C05 implementation families must
therefore remain unable to import or expose it by accident, even as the
central adapters grow.  These checks inspect the source graph and the
assembled transports rather than relying only on individual module tests; a
copied route, a new governed import, or an unapproved nested CLI registration
is consequently visible at the boundary where it would become public.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Final, cast

import pytest
from fastapi.testclient import TestClient

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fastapi import FastAPI

pytestmark = pytest.mark.contract

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]
_SOURCE_ROOT: Final = _REPO_ROOT / "src" / "glio_proteogen"
_ADAPTER_ROOT: Final = _SOURCE_ROOT / "adapters"
_RESEARCH_NAMESPACE: Final = "glio_proteogen.research"
_RESEARCH_ADAPTER_NAMESPACE: Final = "glio_proteogen.adapters.research_state"
_FUNCTIONAL_PROTEOTYPE_ADAPTER_NAMESPACE: Final = (
    "glio_proteogen.adapters.gbm_functional_proteotype"
)
_GBM_ADAPTER_NAMESPACE: Final = "glio_proteogen.adapters.glioma_models"
_NEFTEL_ADAPTER_NAMESPACE: Final = "glio_proteogen.adapters.neftel_programs"
_MASTER_KINASE_ADAPTER_NAMESPACE: Final = "glio_proteogen.adapters.gbm_master_kinases"
_GBM_RNA_PURITY_ADAPTER_NAMESPACE: Final = "glio_proteogen.adapters.gbm_rna_purity"
_LONGITUDINAL_ADAPTER_NAMESPACE: Final = "glio_proteogen.adapters.longitudinal_gbm"
_PHOSPHO_ADAPTER_NAMESPACE: Final = "glio_proteogen.adapters.longitudinal_gbm_phospho"
_KINASE_TRANSITION_ADAPTER_NAMESPACE: Final = (
    "glio_proteogen.adapters.longitudinal_gbm_kinase_transition"
)
_NEFTEL_TRANSITION_ADAPTER_NAMESPACE: Final = (
    "glio_proteogen.adapters.longitudinal_gbm_neftel_transition"
)
_REACTOME_TRANSITION_ADAPTER_NAMESPACE: Final = (
    "glio_proteogen.adapters.longitudinal_gbm_reactome_transition"
)
_COMPLEX_TRANSITION_ADAPTER_NAMESPACE: Final = (
    "glio_proteogen.adapters.longitudinal_gbm_complex_transition"
)
_FACTOR_GRAPH_ADAPTER_NAMESPACE: Final = "glio_proteogen.adapters.gbm_factor_graph"
_M10_ADAPTER_NAMESPACE: Final = "glio_proteogen.adapters.m10_functional_proteotype_facade"
_M11_ADAPTER_NAMESPACE: Final = "glio_proteogen.adapters.m11_protein_native_subtype_facade"
_M14_ADAPTER_NAMESPACE: Final = (
    "glio_proteogen.adapters.m14_microenvironment_protein_programs_facade"
)
_CPTAC_CIS_DOSAGE_ADAPTER_NAMESPACE: Final = "glio_proteogen.adapters.cptac_gbm_cis_dosage"
_CPTAC_DISCORDANCE_ADAPTER_NAMESPACE: Final = (
    "glio_proteogen.adapters.cptac_gbm_transcript_protein_discordance"
)
_RESEARCH_IMPLEMENTATION_NAMESPACE: Final = "glio_proteogen.research.proteogenomic_state"
_FUNCTIONAL_PROTEOTYPE_IMPLEMENTATION_NAMESPACE: Final = (
    "glio_proteogen.research.gbm_functional_proteotype"
)
_GBM_IMPLEMENTATION_NAMESPACE: Final = "glio_proteogen.research.gbm_proteomic_axes"
_NEFTEL_IMPLEMENTATION_NAMESPACE: Final = "glio_proteogen.research.neftel_protein_programs"
_MASTER_KINASE_IMPLEMENTATION_NAMESPACE: Final = "glio_proteogen.research.gbm_master_kinases"
_GBM_RNA_PURITY_IMPLEMENTATION_NAMESPACE: Final = "glio_proteogen.research.gbm_rna_purity"
_LONGITUDINAL_IMPLEMENTATION_NAMESPACE: Final = "glio_proteogen.research.longitudinal_gbm"
_PHOSPHO_IMPLEMENTATION_NAMESPACE: Final = "glio_proteogen.research.longitudinal_gbm_phospho"
_KINASE_TRANSITION_IMPLEMENTATION_NAMESPACE: Final = (
    "glio_proteogen.research.longitudinal_gbm_kinase_transition"
)
_NEFTEL_TRANSITION_IMPLEMENTATION_NAMESPACE: Final = (
    "glio_proteogen.research.longitudinal_gbm_neftel_transition"
)
_REACTOME_TRANSITION_IMPLEMENTATION_NAMESPACE: Final = (
    "glio_proteogen.research.longitudinal_gbm_reactome_transition"
)
_COMPLEX_TRANSITION_IMPLEMENTATION_NAMESPACE: Final = (
    "glio_proteogen.research.longitudinal_gbm_complex_transition"
)
_FACTOR_GRAPH_IMPLEMENTATION_NAMESPACE: Final = "glio_proteogen.research.kncc_gbm_factor_graph"
_M10_IMPLEMENTATION_NAMESPACE: Final = "glio_proteogen.research.m10_functional_proteotype_facade"
_M11_IMPLEMENTATION_NAMESPACE: Final = "glio_proteogen.research.m11_protein_native_subtype_facade"
_M14_IMPLEMENTATION_NAMESPACE: Final = (
    "glio_proteogen.research.m14_microenvironment_protein_programs_facade"
)
_CPTAC_CIS_DOSAGE_IMPLEMENTATION_NAMESPACE: Final = "glio_proteogen.research.cptac_gbm_cis_dosage"
_CPTAC_DISCORDANCE_IMPLEMENTATION_NAMESPACE: Final = (
    "glio_proteogen.research.cptac_gbm_transcript_protein_discordance"
)
_APPROVED_ADAPTER_RESEARCH_IMPORTS: Final = {
    "adapters/api.py": frozenset(
        {
            _RESEARCH_ADAPTER_NAMESPACE,
            _FUNCTIONAL_PROTEOTYPE_ADAPTER_NAMESPACE,
            _GBM_ADAPTER_NAMESPACE,
            _NEFTEL_ADAPTER_NAMESPACE,
            _MASTER_KINASE_ADAPTER_NAMESPACE,
            _GBM_RNA_PURITY_ADAPTER_NAMESPACE,
            _LONGITUDINAL_ADAPTER_NAMESPACE,
            _PHOSPHO_ADAPTER_NAMESPACE,
            _KINASE_TRANSITION_ADAPTER_NAMESPACE,
            _NEFTEL_TRANSITION_ADAPTER_NAMESPACE,
            _REACTOME_TRANSITION_ADAPTER_NAMESPACE,
            _COMPLEX_TRANSITION_ADAPTER_NAMESPACE,
            _FACTOR_GRAPH_ADAPTER_NAMESPACE,
            _M10_ADAPTER_NAMESPACE,
            _M11_ADAPTER_NAMESPACE,
            _M14_ADAPTER_NAMESPACE,
        }
    ),
    "adapters/cli.py": frozenset(
        {
            _RESEARCH_ADAPTER_NAMESPACE,
            _FUNCTIONAL_PROTEOTYPE_ADAPTER_NAMESPACE,
            _GBM_ADAPTER_NAMESPACE,
            _NEFTEL_ADAPTER_NAMESPACE,
            _MASTER_KINASE_ADAPTER_NAMESPACE,
            _GBM_RNA_PURITY_ADAPTER_NAMESPACE,
            _LONGITUDINAL_ADAPTER_NAMESPACE,
            _PHOSPHO_ADAPTER_NAMESPACE,
            _KINASE_TRANSITION_ADAPTER_NAMESPACE,
            _NEFTEL_TRANSITION_ADAPTER_NAMESPACE,
            _REACTOME_TRANSITION_ADAPTER_NAMESPACE,
            _COMPLEX_TRANSITION_ADAPTER_NAMESPACE,
            _FACTOR_GRAPH_ADAPTER_NAMESPACE,
            _CPTAC_CIS_DOSAGE_ADAPTER_NAMESPACE,
            _CPTAC_DISCORDANCE_ADAPTER_NAMESPACE,
        }
    ),
    "adapters/research_readiness.py": frozenset(
        {
            _RESEARCH_ADAPTER_NAMESPACE,
            _FUNCTIONAL_PROTEOTYPE_ADAPTER_NAMESPACE,
            _GBM_ADAPTER_NAMESPACE,
            _NEFTEL_ADAPTER_NAMESPACE,
            _MASTER_KINASE_ADAPTER_NAMESPACE,
            _GBM_RNA_PURITY_ADAPTER_NAMESPACE,
            _LONGITUDINAL_ADAPTER_NAMESPACE,
            _PHOSPHO_ADAPTER_NAMESPACE,
            _KINASE_TRANSITION_ADAPTER_NAMESPACE,
            _NEFTEL_TRANSITION_ADAPTER_NAMESPACE,
            _REACTOME_TRANSITION_ADAPTER_NAMESPACE,
            _COMPLEX_TRANSITION_ADAPTER_NAMESPACE,
            _FACTOR_GRAPH_ADAPTER_NAMESPACE,
            _M10_ADAPTER_NAMESPACE,
            _M11_ADAPTER_NAMESPACE,
            _M14_ADAPTER_NAMESPACE,
        }
    ),
    "adapters/research_state.py": frozenset({_RESEARCH_IMPLEMENTATION_NAMESPACE}),
    "adapters/gbm_functional_proteotype.py": frozenset(
        {
            _FUNCTIONAL_PROTEOTYPE_IMPLEMENTATION_NAMESPACE,
            _RESEARCH_IMPLEMENTATION_NAMESPACE,
        }
    ),
    "adapters/glioma_models.py": frozenset(
        {_GBM_IMPLEMENTATION_NAMESPACE, _RESEARCH_IMPLEMENTATION_NAMESPACE}
    ),
    "adapters/neftel_programs.py": frozenset(
        {_NEFTEL_IMPLEMENTATION_NAMESPACE, _RESEARCH_IMPLEMENTATION_NAMESPACE}
    ),
    "adapters/gbm_master_kinases.py": frozenset(
        {_MASTER_KINASE_IMPLEMENTATION_NAMESPACE, _RESEARCH_IMPLEMENTATION_NAMESPACE}
    ),
    "adapters/gbm_rna_purity.py": frozenset(
        {_GBM_RNA_PURITY_IMPLEMENTATION_NAMESPACE, _RESEARCH_IMPLEMENTATION_NAMESPACE}
    ),
    "adapters/longitudinal_gbm.py": frozenset(
        {_LONGITUDINAL_IMPLEMENTATION_NAMESPACE, _RESEARCH_IMPLEMENTATION_NAMESPACE}
    ),
    "adapters/longitudinal_gbm_phospho.py": frozenset(
        {_PHOSPHO_IMPLEMENTATION_NAMESPACE, _RESEARCH_IMPLEMENTATION_NAMESPACE}
    ),
    "adapters/longitudinal_gbm_kinase_transition.py": frozenset(
        {
            _KINASE_TRANSITION_IMPLEMENTATION_NAMESPACE,
            _RESEARCH_IMPLEMENTATION_NAMESPACE,
        }
    ),
    "adapters/longitudinal_gbm_neftel_transition.py": frozenset(
        {
            _NEFTEL_TRANSITION_IMPLEMENTATION_NAMESPACE,
            _RESEARCH_IMPLEMENTATION_NAMESPACE,
        }
    ),
    "adapters/longitudinal_gbm_reactome_transition.py": frozenset(
        {
            _REACTOME_TRANSITION_IMPLEMENTATION_NAMESPACE,
            _RESEARCH_IMPLEMENTATION_NAMESPACE,
        }
    ),
    "adapters/longitudinal_gbm_complex_transition.py": frozenset(
        {
            _COMPLEX_TRANSITION_IMPLEMENTATION_NAMESPACE,
            _RESEARCH_IMPLEMENTATION_NAMESPACE,
        }
    ),
    "adapters/gbm_factor_graph.py": frozenset(
        {
            _FACTOR_GRAPH_IMPLEMENTATION_NAMESPACE,
            _RESEARCH_IMPLEMENTATION_NAMESPACE,
        }
    ),
    "adapters/m10_functional_proteotype_facade.py": frozenset(
        {_FUNCTIONAL_PROTEOTYPE_ADAPTER_NAMESPACE, _M10_IMPLEMENTATION_NAMESPACE}
    ),
    "adapters/m11_protein_native_subtype_facade.py": frozenset(
        {_M11_IMPLEMENTATION_NAMESPACE, _RESEARCH_IMPLEMENTATION_NAMESPACE}
    ),
    "adapters/m14_microenvironment_protein_programs_facade.py": frozenset(
        {_M14_IMPLEMENTATION_NAMESPACE, _RESEARCH_IMPLEMENTATION_NAMESPACE}
    ),
    "adapters/cptac_gbm_cis_dosage.py": frozenset({_CPTAC_CIS_DOSAGE_IMPLEMENTATION_NAMESPACE}),
    "adapters/cptac_gbm_transcript_protein_discordance.py": frozenset(
        {_CPTAC_DISCORDANCE_IMPLEMENTATION_NAMESPACE}
    ),
}
_GOVERNED_FAMILY_GLOBS: Final = (
    "modules/c03_*",
    "modules/c04_*",
    "modules/c05_*",
    "contracts/m03_*",
    "contracts/m04_*",
    "contracts/m05_*",
)
_FROZEN_MANIFEST_MODULES: Final = {
    *(f"M03-{index:02d}" for index in range(1, 9)),
    *(f"M04-{index:02d}" for index in range(1, 9)),
    *(f"M05-{index:02d}" for index in range(1, 5)),
}
_RESEARCH_CAPABILITY_MARKERS: Final = (
    "/research",
    "research",
    "gbm",
    "neftel",
    "spectrum",
    "mzml",
    "psm",
    "fdr",
    "q-value",
    "qvalue",
    "quantification",
    "protein-groups",
    "protein_groups",
    "peptide-spectrum",
    "target-decoy",
    "target_decoy",
    "cohort",
    "complex-transition",
)
_RESEARCH_PREFIX: Final = "/v1/research/proteogenomic-state"
_FUNCTIONAL_PROTEOTYPE_RESEARCH_PREFIX: Final = "/v1/research/gbm-functional-proteotype"
_GBM_RESEARCH_PREFIX: Final = "/v1/research/gbm-proteomic-axes"
_NEFTEL_RESEARCH_PREFIX: Final = "/v1/research/neftel-protein-programs"
_MASTER_KINASE_RESEARCH_PREFIX: Final = "/v1/research/gbm-master-kinases"
_GBM_RNA_PURITY_RESEARCH_PREFIX: Final = "/v1/research/gbm-rna-purity"
_LONGITUDINAL_RESEARCH_PREFIX: Final = "/v1/research/longitudinal-gbm"
_PHOSPHO_RESEARCH_PREFIX: Final = "/v1/research/longitudinal-gbm-phospho"
_KINASE_TRANSITION_RESEARCH_PREFIX: Final = "/v1/research/longitudinal-gbm-kinase-transition"
_NEFTEL_TRANSITION_RESEARCH_PREFIX: Final = "/v1/research/longitudinal-gbm-neftel-transition"
_REACTOME_TRANSITION_RESEARCH_PREFIX: Final = "/v1/research/longitudinal-gbm-reactome-transition"
_COMPLEX_TRANSITION_RESEARCH_PREFIX: Final = "/v1/research/longitudinal-gbm-complex-transition"
_FACTOR_GRAPH_RESEARCH_PREFIX: Final = "/v1/research/gbm-factor-graph"
_M09_RESEARCH_PREFIX: Final = "/v2/research/modules/m09/complex-transition-concordance"
_M10_RESEARCH_PREFIX: Final = "/v2/research/modules/m10/functional-proteotype"
_M11_RESEARCH_PREFIX: Final = "/v2/research/modules/m11/protein-native-subtype"
_M14_RESEARCH_PREFIX: Final = "/v2/research/modules/m14/microenvironment-protein-programs"
_M15_RESEARCH_PREFIX: Final = "/v2/research/modules/m15/longitudinal-recurrence-proteotype"
_RESEARCH_ROUTE_SUFFIXES: Final = ("/profile", "/demo", "/analyze", "/verify")
_RESEARCH_CLI_COMMANDS: Final = {
    "research-state profile",
    "research-state demo",
    "research-state analyze",
    "research-state verify",
}
_FUNCTIONAL_PROTEOTYPE_RESEARCH_CLI_COMMANDS: Final = {
    "gbm-functional-proteotype profile",
    "gbm-functional-proteotype demo",
    "gbm-functional-proteotype analyze",
    "gbm-functional-proteotype verify",
}
_GBM_RESEARCH_CLI_COMMANDS: Final = {
    "gbm-axes profile",
    "gbm-axes demo",
    "gbm-axes analyze",
    "gbm-axes verify",
}
_NEFTEL_RESEARCH_CLI_COMMANDS: Final = {
    "neftel-programs profile",
    "neftel-programs demo",
    "neftel-programs analyze",
    "neftel-programs verify",
}
_MASTER_KINASE_RESEARCH_CLI_COMMANDS: Final = {
    "gbm-master-kinases profile",
    "gbm-master-kinases demo",
    "gbm-master-kinases analyze",
    "gbm-master-kinases verify",
}
_GBM_RNA_PURITY_RESEARCH_CLI_COMMANDS: Final = {
    "gbm-rna-purity profile",
    "gbm-rna-purity demo",
    "gbm-rna-purity analyze",
    "gbm-rna-purity verify",
}
_LONGITUDINAL_RESEARCH_CLI_COMMANDS: Final = {
    "longitudinal-gbm profile",
    "longitudinal-gbm demo",
    "longitudinal-gbm analyze",
    "longitudinal-gbm verify",
}
_PHOSPHO_RESEARCH_CLI_COMMANDS: Final = {
    "longitudinal-gbm-phospho profile",
    "longitudinal-gbm-phospho demo",
    "longitudinal-gbm-phospho analyze",
    "longitudinal-gbm-phospho verify",
}
_KINASE_TRANSITION_RESEARCH_CLI_COMMANDS: Final = {
    "longitudinal-gbm-kinase-transition profile",
    "longitudinal-gbm-kinase-transition demo",
    "longitudinal-gbm-kinase-transition analyze",
    "longitudinal-gbm-kinase-transition verify",
}
_NEFTEL_TRANSITION_RESEARCH_CLI_COMMANDS: Final = {
    "longitudinal-gbm-neftel-transition profile",
    "longitudinal-gbm-neftel-transition demo",
    "longitudinal-gbm-neftel-transition analyze",
    "longitudinal-gbm-neftel-transition verify",
}
_REACTOME_TRANSITION_RESEARCH_CLI_COMMANDS: Final = {
    "longitudinal-gbm-reactome-transition profile",
    "longitudinal-gbm-reactome-transition demo",
    "longitudinal-gbm-reactome-transition analyze",
    "longitudinal-gbm-reactome-transition verify",
}
_COMPLEX_TRANSITION_RESEARCH_CLI_COMMANDS: Final = {
    "complex-transition profile",
    "complex-transition demo",
    "complex-transition analyze",
    "complex-transition verify",
}
_FACTOR_GRAPH_RESEARCH_CLI_COMMANDS: Final = {
    "gbm-factor-graph profile",
    "gbm-factor-graph demo",
    "gbm-factor-graph analyze",
    "gbm-factor-graph verify",
}
_CPTAC_CIS_DOSAGE_RESEARCH_CLI_COMMANDS: Final = {
    "cptac-gbm-cis-dosage fit-local",
    "cptac-gbm-cis-dosage profile",
    "cptac-gbm-cis-dosage analyze",
    "cptac-gbm-cis-dosage verify",
    "cptac-gbm-cis-dosage verify-source",
}
_CPTAC_DISCORDANCE_RESEARCH_CLI_COMMANDS: Final = {
    "cptac-gbm-transcript-protein-discordance fit-local",
    "cptac-gbm-transcript-protein-discordance profile",
    "cptac-gbm-transcript-protein-discordance analyze",
    "cptac-gbm-transcript-protein-discordance verify",
}
_RESEARCH_CLI_CALLBACK_MODULES: Final = {
    **dict.fromkeys(_RESEARCH_CLI_COMMANDS, "glio_proteogen.adapters.research_state"),
    **dict.fromkeys(
        _FUNCTIONAL_PROTEOTYPE_RESEARCH_CLI_COMMANDS,
        "glio_proteogen.adapters.gbm_functional_proteotype",
    ),
    **dict.fromkeys(_GBM_RESEARCH_CLI_COMMANDS, "glio_proteogen.adapters.glioma_models"),
    **dict.fromkeys(
        _NEFTEL_RESEARCH_CLI_COMMANDS,
        "glio_proteogen.adapters.neftel_programs",
    ),
    **dict.fromkeys(
        _MASTER_KINASE_RESEARCH_CLI_COMMANDS,
        "glio_proteogen.adapters.gbm_master_kinases",
    ),
    **dict.fromkeys(
        _GBM_RNA_PURITY_RESEARCH_CLI_COMMANDS,
        "glio_proteogen.adapters.gbm_rna_purity",
    ),
    **dict.fromkeys(
        _LONGITUDINAL_RESEARCH_CLI_COMMANDS,
        "glio_proteogen.adapters.longitudinal_gbm",
    ),
    **dict.fromkeys(
        _PHOSPHO_RESEARCH_CLI_COMMANDS,
        "glio_proteogen.adapters.longitudinal_gbm_phospho",
    ),
    **dict.fromkeys(
        _KINASE_TRANSITION_RESEARCH_CLI_COMMANDS,
        "glio_proteogen.adapters.longitudinal_gbm_kinase_transition",
    ),
    **dict.fromkeys(
        _NEFTEL_TRANSITION_RESEARCH_CLI_COMMANDS,
        "glio_proteogen.adapters.longitudinal_gbm_neftel_transition",
    ),
    **dict.fromkeys(
        _REACTOME_TRANSITION_RESEARCH_CLI_COMMANDS,
        "glio_proteogen.adapters.longitudinal_gbm_reactome_transition",
    ),
    **dict.fromkeys(
        _COMPLEX_TRANSITION_RESEARCH_CLI_COMMANDS,
        "glio_proteogen.adapters.longitudinal_gbm_complex_transition",
    ),
    **dict.fromkeys(
        _FACTOR_GRAPH_RESEARCH_CLI_COMMANDS,
        "glio_proteogen.adapters.gbm_factor_graph",
    ),
    **dict.fromkeys(
        _CPTAC_CIS_DOSAGE_RESEARCH_CLI_COMMANDS,
        "glio_proteogen.adapters.cptac_gbm_cis_dosage",
    ),
    **dict.fromkeys(
        _CPTAC_DISCORDANCE_RESEARCH_CLI_COMMANDS,
        "glio_proteogen.adapters.cptac_gbm_transcript_protein_discordance",
    ),
}
_RESEARCH_ROUTE_MODULES: Final = (
    (
        _FUNCTIONAL_PROTEOTYPE_RESEARCH_PREFIX,
        "glio_proteogen.adapters.gbm_functional_proteotype",
    ),
    (_GBM_RESEARCH_PREFIX, "glio_proteogen.adapters.glioma_models"),
    (_NEFTEL_RESEARCH_PREFIX, "glio_proteogen.adapters.neftel_programs"),
    (_MASTER_KINASE_RESEARCH_PREFIX, "glio_proteogen.adapters.gbm_master_kinases"),
    (_GBM_RNA_PURITY_RESEARCH_PREFIX, "glio_proteogen.adapters.gbm_rna_purity"),
    (
        _KINASE_TRANSITION_RESEARCH_PREFIX,
        "glio_proteogen.adapters.longitudinal_gbm_kinase_transition",
    ),
    (
        _NEFTEL_TRANSITION_RESEARCH_PREFIX,
        "glio_proteogen.adapters.longitudinal_gbm_neftel_transition",
    ),
    (
        _REACTOME_TRANSITION_RESEARCH_PREFIX,
        "glio_proteogen.adapters.longitudinal_gbm_reactome_transition",
    ),
    (
        _COMPLEX_TRANSITION_RESEARCH_PREFIX,
        "glio_proteogen.adapters.longitudinal_gbm_complex_transition",
    ),
    (_FACTOR_GRAPH_RESEARCH_PREFIX, "glio_proteogen.adapters.gbm_factor_graph"),
    (_PHOSPHO_RESEARCH_PREFIX, "glio_proteogen.adapters.longitudinal_gbm_phospho"),
    (
        _M09_RESEARCH_PREFIX,
        "glio_proteogen.adapters.longitudinal_gbm_complex_transition",
    ),
    (_M10_RESEARCH_PREFIX, "glio_proteogen.adapters.m10_functional_proteotype_facade"),
    (_M11_RESEARCH_PREFIX, "glio_proteogen.adapters.m11_protein_native_subtype_facade"),
    (
        _M14_RESEARCH_PREFIX,
        "glio_proteogen.adapters.m14_microenvironment_protein_programs_facade",
    ),
    (_M15_RESEARCH_PREFIX, "glio_proteogen.adapters.longitudinal_gbm"),
    (_LONGITUDINAL_RESEARCH_PREFIX, "glio_proteogen.adapters.longitudinal_gbm"),
    (_RESEARCH_PREFIX, "glio_proteogen.adapters.research_state"),
)


def _governed_python_files() -> Iterator[Path]:
    """Yield every tracked C03/C04/C05 source file, including nested helpers.

    The previous guard discovered only ``contracts/m03_01``-style folders and
    silently missed the implementation families, which live below
    ``modules/c03_*``.  Keep the inventory explicit and deterministic so a
    newly added family cannot fall outside the AST firewall unnoticed.
    """

    paths: set[Path] = set()
    for pattern in _GOVERNED_FAMILY_GLOBS:
        for family_root in _SOURCE_ROOT.glob(pattern):
            if family_root.is_dir():
                paths.update(family_root.rglob("*.py"))

    yield from sorted(paths)


def _family_roots() -> tuple[Path, ...]:
    """Return the implementation families covered by the source inventory."""

    return tuple(
        sorted(
            family_root
            for pattern in _GOVERNED_FAMILY_GLOBS[:3]
            for family_root in _SOURCE_ROOT.glob(pattern)
            if family_root.is_dir()
        )
    )


@pytest.mark.contract
def test_governed_family_inventory_is_complete() -> None:
    """The firewall must see all three governed implementation families."""

    family_roots = _family_roots()
    assert tuple(path.name[:3] for path in family_roots) == ("c03", "c04", "c05")
    assert all(tuple(path.rglob("*.py")) for path in family_roots)


def _import_targets(tree: ast.AST) -> Iterator[tuple[str, int]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from ((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            yield node.module, node.lineno


def _source_import_targets(source_path: Path) -> Iterator[tuple[str, int]]:
    """Resolve absolute and relative imports to fully qualified targets."""

    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    relative = source_path.relative_to(_SOURCE_ROOT)
    package_parts = ["glio_proteogen", *relative.parent.parts]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from ((alias.name, node.lineno) for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            parent_hops = node.level - 1
            prefix = package_parts[: len(package_parts) - parent_hops]
            module_parts = node.module.split(".") if node.module else []
            base = ".".join((*prefix, *module_parts))
        else:
            base = node.module or ""
        if base:
            yield base, node.lineno
        yield from (
            (f"{base}.{alias.name}" if base else alias.name, node.lineno)
            for alias in node.names
            if alias.name != "*"
        )


def _restricted_research_namespace(target: str) -> str | None:
    for namespace in (
        _RESEARCH_ADAPTER_NAMESPACE,
        _FUNCTIONAL_PROTEOTYPE_ADAPTER_NAMESPACE,
        _GBM_ADAPTER_NAMESPACE,
        _NEFTEL_ADAPTER_NAMESPACE,
        _MASTER_KINASE_ADAPTER_NAMESPACE,
        _GBM_RNA_PURITY_ADAPTER_NAMESPACE,
        _PHOSPHO_ADAPTER_NAMESPACE,
        _KINASE_TRANSITION_ADAPTER_NAMESPACE,
        _NEFTEL_TRANSITION_ADAPTER_NAMESPACE,
        _REACTOME_TRANSITION_ADAPTER_NAMESPACE,
        _COMPLEX_TRANSITION_ADAPTER_NAMESPACE,
        _FACTOR_GRAPH_ADAPTER_NAMESPACE,
        _M10_ADAPTER_NAMESPACE,
        _M11_ADAPTER_NAMESPACE,
        _M14_ADAPTER_NAMESPACE,
        _CPTAC_CIS_DOSAGE_ADAPTER_NAMESPACE,
        _CPTAC_DISCORDANCE_ADAPTER_NAMESPACE,
        _LONGITUDINAL_ADAPTER_NAMESPACE,
        _RESEARCH_IMPLEMENTATION_NAMESPACE,
        _FUNCTIONAL_PROTEOTYPE_IMPLEMENTATION_NAMESPACE,
        _GBM_IMPLEMENTATION_NAMESPACE,
        _NEFTEL_IMPLEMENTATION_NAMESPACE,
        _MASTER_KINASE_IMPLEMENTATION_NAMESPACE,
        _GBM_RNA_PURITY_IMPLEMENTATION_NAMESPACE,
        _PHOSPHO_IMPLEMENTATION_NAMESPACE,
        _KINASE_TRANSITION_IMPLEMENTATION_NAMESPACE,
        _NEFTEL_TRANSITION_IMPLEMENTATION_NAMESPACE,
        _REACTOME_TRANSITION_IMPLEMENTATION_NAMESPACE,
        _COMPLEX_TRANSITION_IMPLEMENTATION_NAMESPACE,
        _FACTOR_GRAPH_IMPLEMENTATION_NAMESPACE,
        _M10_IMPLEMENTATION_NAMESPACE,
        _M11_IMPLEMENTATION_NAMESPACE,
        _M14_IMPLEMENTATION_NAMESPACE,
        _CPTAC_CIS_DOSAGE_IMPLEMENTATION_NAMESPACE,
        _CPTAC_DISCORDANCE_IMPLEMENTATION_NAMESPACE,
        _LONGITUDINAL_IMPLEMENTATION_NAMESPACE,
    ):
        if target == namespace or target.startswith(f"{namespace}."):
            return namespace
    if target == _RESEARCH_NAMESPACE or target.startswith(f"{_RESEARCH_NAMESPACE}."):
        return _RESEARCH_NAMESPACE
    return None


@pytest.mark.contract
def test_non_research_source_uses_only_the_explicit_adapter_bridge() -> None:  # noqa: PLR0915
    """Every adapter is scanned and no other source can bypass its research bridge."""

    adapter_paths = tuple(sorted(_ADAPTER_ROOT.rglob("*.py")))
    assert adapter_paths, "adapter source inventory unexpectedly empty"
    research_root = _SOURCE_ROOT / "research"
    boundary_paths = tuple(
        sorted(
            path for path in _SOURCE_ROOT.rglob("*.py") if not path.is_relative_to(research_root)
        )
    )
    assert set(adapter_paths) <= set(boundary_paths)
    observed: dict[str, set[str]] = {
        _RESEARCH_ADAPTER_NAMESPACE: set(),
        _FUNCTIONAL_PROTEOTYPE_ADAPTER_NAMESPACE: set(),
        _GBM_ADAPTER_NAMESPACE: set(),
        _NEFTEL_ADAPTER_NAMESPACE: set(),
        _MASTER_KINASE_ADAPTER_NAMESPACE: set(),
        _GBM_RNA_PURITY_ADAPTER_NAMESPACE: set(),
        _LONGITUDINAL_ADAPTER_NAMESPACE: set(),
        _PHOSPHO_ADAPTER_NAMESPACE: set(),
        _KINASE_TRANSITION_ADAPTER_NAMESPACE: set(),
        _NEFTEL_TRANSITION_ADAPTER_NAMESPACE: set(),
        _REACTOME_TRANSITION_ADAPTER_NAMESPACE: set(),
        _COMPLEX_TRANSITION_ADAPTER_NAMESPACE: set(),
        _FACTOR_GRAPH_ADAPTER_NAMESPACE: set(),
        _M10_ADAPTER_NAMESPACE: set(),
        _M11_ADAPTER_NAMESPACE: set(),
        _M14_ADAPTER_NAMESPACE: set(),
        _CPTAC_CIS_DOSAGE_ADAPTER_NAMESPACE: set(),
        _CPTAC_DISCORDANCE_ADAPTER_NAMESPACE: set(),
        _RESEARCH_IMPLEMENTATION_NAMESPACE: set(),
        _FUNCTIONAL_PROTEOTYPE_IMPLEMENTATION_NAMESPACE: set(),
        _GBM_IMPLEMENTATION_NAMESPACE: set(),
        _NEFTEL_IMPLEMENTATION_NAMESPACE: set(),
        _MASTER_KINASE_IMPLEMENTATION_NAMESPACE: set(),
        _GBM_RNA_PURITY_IMPLEMENTATION_NAMESPACE: set(),
        _LONGITUDINAL_IMPLEMENTATION_NAMESPACE: set(),
        _PHOSPHO_IMPLEMENTATION_NAMESPACE: set(),
        _KINASE_TRANSITION_IMPLEMENTATION_NAMESPACE: set(),
        _NEFTEL_TRANSITION_IMPLEMENTATION_NAMESPACE: set(),
        _REACTOME_TRANSITION_IMPLEMENTATION_NAMESPACE: set(),
        _COMPLEX_TRANSITION_IMPLEMENTATION_NAMESPACE: set(),
        _FACTOR_GRAPH_IMPLEMENTATION_NAMESPACE: set(),
        _M10_IMPLEMENTATION_NAMESPACE: set(),
        _M11_IMPLEMENTATION_NAMESPACE: set(),
        _M14_IMPLEMENTATION_NAMESPACE: set(),
        _CPTAC_CIS_DOSAGE_IMPLEMENTATION_NAMESPACE: set(),
        _CPTAC_DISCORDANCE_IMPLEMENTATION_NAMESPACE: set(),
    }
    violations: list[str] = []
    for source_path in boundary_paths:
        relative = source_path.relative_to(_SOURCE_ROOT).as_posix()
        allowed = _APPROVED_ADAPTER_RESEARCH_IMPORTS.get(relative, frozenset())
        for target, line in _source_import_targets(source_path):
            restricted = _restricted_research_namespace(target)
            if restricted is None:
                continue
            if restricted in observed:
                observed[restricted].add(relative)
            if restricted not in allowed:
                violations.append(f"{relative}:{line}: {target}")

    assert not violations, "adapter bypassed research bridge: " + "; ".join(violations)
    assert observed[_RESEARCH_ADAPTER_NAMESPACE] == {
        "adapters/api.py",
        "adapters/cli.py",
        "adapters/research_readiness.py",
    }
    assert observed[_FUNCTIONAL_PROTEOTYPE_ADAPTER_NAMESPACE] == {
        "adapters/api.py",
        "adapters/cli.py",
        "adapters/m10_functional_proteotype_facade.py",
        "adapters/research_readiness.py",
    }
    assert observed[_GBM_ADAPTER_NAMESPACE] == {
        "adapters/api.py",
        "adapters/cli.py",
        "adapters/research_readiness.py",
    }
    assert observed[_NEFTEL_ADAPTER_NAMESPACE] == {
        "adapters/api.py",
        "adapters/cli.py",
        "adapters/research_readiness.py",
    }
    assert observed[_MASTER_KINASE_ADAPTER_NAMESPACE] == {
        "adapters/api.py",
        "adapters/cli.py",
        "adapters/research_readiness.py",
    }
    assert observed[_GBM_RNA_PURITY_ADAPTER_NAMESPACE] == {
        "adapters/api.py",
        "adapters/cli.py",
        "adapters/research_readiness.py",
    }
    assert observed[_LONGITUDINAL_ADAPTER_NAMESPACE] == {
        "adapters/api.py",
        "adapters/cli.py",
        "adapters/research_readiness.py",
    }
    assert observed[_PHOSPHO_ADAPTER_NAMESPACE] == {
        "adapters/api.py",
        "adapters/cli.py",
        "adapters/research_readiness.py",
    }
    assert observed[_KINASE_TRANSITION_ADAPTER_NAMESPACE] == {
        "adapters/api.py",
        "adapters/cli.py",
        "adapters/research_readiness.py",
    }
    assert observed[_NEFTEL_TRANSITION_ADAPTER_NAMESPACE] == {
        "adapters/api.py",
        "adapters/cli.py",
        "adapters/research_readiness.py",
    }
    assert observed[_REACTOME_TRANSITION_ADAPTER_NAMESPACE] == {
        "adapters/api.py",
        "adapters/cli.py",
        "adapters/research_readiness.py",
    }
    assert observed[_COMPLEX_TRANSITION_ADAPTER_NAMESPACE] == {
        "adapters/api.py",
        "adapters/cli.py",
        "adapters/research_readiness.py",
    }
    assert observed[_FACTOR_GRAPH_ADAPTER_NAMESPACE] == {
        "adapters/api.py",
        "adapters/cli.py",
        "adapters/research_readiness.py",
    }
    assert observed[_M10_ADAPTER_NAMESPACE] == {
        "adapters/api.py",
        "adapters/research_readiness.py",
    }
    assert observed[_M11_ADAPTER_NAMESPACE] == {
        "adapters/api.py",
        "adapters/research_readiness.py",
    }
    assert observed[_M14_ADAPTER_NAMESPACE] == {
        "adapters/api.py",
        "adapters/research_readiness.py",
    }
    assert observed[_CPTAC_CIS_DOSAGE_ADAPTER_NAMESPACE] == {"adapters/cli.py"}
    assert observed[_CPTAC_DISCORDANCE_ADAPTER_NAMESPACE] == {"adapters/cli.py"}
    assert observed[_RESEARCH_IMPLEMENTATION_NAMESPACE] == {
        "adapters/gbm_functional_proteotype.py",
        "adapters/gbm_master_kinases.py",
        "adapters/gbm_rna_purity.py",
        "adapters/glioma_models.py",
        "adapters/neftel_programs.py",
        "adapters/research_state.py",
        "adapters/longitudinal_gbm.py",
        "adapters/longitudinal_gbm_phospho.py",
        "adapters/longitudinal_gbm_kinase_transition.py",
        "adapters/longitudinal_gbm_neftel_transition.py",
        "adapters/longitudinal_gbm_reactome_transition.py",
        "adapters/longitudinal_gbm_complex_transition.py",
        "adapters/gbm_factor_graph.py",
        "adapters/m11_protein_native_subtype_facade.py",
        "adapters/m14_microenvironment_protein_programs_facade.py",
    }
    assert observed[_FUNCTIONAL_PROTEOTYPE_IMPLEMENTATION_NAMESPACE] == {
        "adapters/gbm_functional_proteotype.py"
    }
    assert observed[_GBM_IMPLEMENTATION_NAMESPACE] == {"adapters/glioma_models.py"}
    assert observed[_NEFTEL_IMPLEMENTATION_NAMESPACE] == {"adapters/neftel_programs.py"}
    assert observed[_MASTER_KINASE_IMPLEMENTATION_NAMESPACE] == {"adapters/gbm_master_kinases.py"}
    assert observed[_GBM_RNA_PURITY_IMPLEMENTATION_NAMESPACE] == {"adapters/gbm_rna_purity.py"}
    assert observed[_LONGITUDINAL_IMPLEMENTATION_NAMESPACE] == {"adapters/longitudinal_gbm.py"}
    assert observed[_PHOSPHO_IMPLEMENTATION_NAMESPACE] == {"adapters/longitudinal_gbm_phospho.py"}
    assert observed[_KINASE_TRANSITION_IMPLEMENTATION_NAMESPACE] == {
        "adapters/longitudinal_gbm_kinase_transition.py"
    }
    assert observed[_NEFTEL_TRANSITION_IMPLEMENTATION_NAMESPACE] == {
        "adapters/longitudinal_gbm_neftel_transition.py"
    }
    assert observed[_REACTOME_TRANSITION_IMPLEMENTATION_NAMESPACE] == {
        "adapters/longitudinal_gbm_reactome_transition.py"
    }
    assert observed[_COMPLEX_TRANSITION_IMPLEMENTATION_NAMESPACE] == {
        "adapters/longitudinal_gbm_complex_transition.py"
    }
    assert observed[_FACTOR_GRAPH_IMPLEMENTATION_NAMESPACE] == {"adapters/gbm_factor_graph.py"}
    assert observed[_M10_IMPLEMENTATION_NAMESPACE] == {
        "adapters/m10_functional_proteotype_facade.py"
    }
    assert observed[_M11_IMPLEMENTATION_NAMESPACE] == {
        "adapters/m11_protein_native_subtype_facade.py"
    }
    assert observed[_M14_IMPLEMENTATION_NAMESPACE] == {
        "adapters/m14_microenvironment_protein_programs_facade.py"
    }
    assert observed[_CPTAC_CIS_DOSAGE_IMPLEMENTATION_NAMESPACE] == {
        "adapters/cptac_gbm_cis_dosage.py"
    }
    assert observed[_CPTAC_DISCORDANCE_IMPLEMENTATION_NAMESPACE] == {
        "adapters/cptac_gbm_transcript_protein_discordance.py"
    }


@pytest.mark.parametrize("source_path", tuple(_governed_python_files()))
def test_frozen_governed_source_cannot_import_research_namespace(source_path: Path) -> None:
    """Reject direct and aliased imports that would make research governed."""

    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    violations = [
        f"{source_path.relative_to(_REPO_ROOT)}:{line}: {module}"
        for module, line in _import_targets(tree)
        if module == _RESEARCH_NAMESPACE or module.startswith(f"{_RESEARCH_NAMESPACE}.")
    ]
    assert not violations, "research namespace crossed governed boundary: " + "; ".join(violations)


def _callback_module(callback: object) -> str | None:
    return getattr(callback, "__module__", None)


def _registered_cli_callbacks() -> Iterator[tuple[str, object]]:
    """Walk all Typer nesting levels, including future nested sub-groups."""

    def walk(typer_app: object, prefix: str, seen: set[int]) -> Iterator[tuple[str, object]]:
        app_id = id(typer_app)
        if app_id in seen:
            return
        seen.add(app_id)
        for command in getattr(typer_app, "registered_commands", ()):
            callback = getattr(command, "callback", None)
            if callback is not None:
                name = getattr(command, "name", None) or "<root>"
                yield f"{prefix} {name}".strip(), callback
        for group in getattr(typer_app, "registered_groups", ()):
            child = getattr(group, "typer_instance", None)
            if child is not None:
                name = getattr(group, "name", None) or "<group>"
                yield from walk(child, f"{prefix} {name}".strip(), seen)

    yield from walk(cli_app, "", set())


def _research_route_module(path: str) -> str:
    for prefix, module in _RESEARCH_ROUTE_MODULES:
        if path.startswith(prefix):
            return module
    raise AssertionError(path)


@pytest.mark.contract
def test_central_cli_has_only_the_approved_research_commands() -> None:
    """The central CLI exposes only the approved narrow research command groups."""

    callbacks = tuple(_registered_cli_callbacks())
    assert callbacks, "central CLI callback inventory unexpectedly empty"
    discovered_research: set[str] = set()
    for name, callback in callbacks:
        module = _callback_module(callback)
        assert module is not None, (name, module)
        assert module.startswith("glio_proteogen.adapters."), (name, module)
        assert not module.startswith(_RESEARCH_NAMESPACE), (name, module)
        if any(token in name.lower() for token in _RESEARCH_CAPABILITY_MARKERS):
            discovered_research.add(name)
            assert module == _RESEARCH_CLI_CALLBACK_MODULES.get(name), (name, module)
    assert discovered_research == (
        _RESEARCH_CLI_COMMANDS
        | _FUNCTIONAL_PROTEOTYPE_RESEARCH_CLI_COMMANDS
        | _GBM_RESEARCH_CLI_COMMANDS
        | _NEFTEL_RESEARCH_CLI_COMMANDS
        | _MASTER_KINASE_RESEARCH_CLI_COMMANDS
        | _GBM_RNA_PURITY_RESEARCH_CLI_COMMANDS
        | _LONGITUDINAL_RESEARCH_CLI_COMMANDS
        | _PHOSPHO_RESEARCH_CLI_COMMANDS
        | _KINASE_TRANSITION_RESEARCH_CLI_COMMANDS
        | _NEFTEL_TRANSITION_RESEARCH_CLI_COMMANDS
        | _REACTOME_TRANSITION_RESEARCH_CLI_COMMANDS
        | _COMPLEX_TRANSITION_RESEARCH_CLI_COMMANDS
        | _FACTOR_GRAPH_RESEARCH_CLI_COMMANDS
        | _CPTAC_CIS_DOSAGE_RESEARCH_CLI_COMMANDS
        | _CPTAC_DISCORDANCE_RESEARCH_CLI_COMMANDS
    )


def _route_inventory() -> tuple[tuple[str, str, str, str], ...]:
    with (
        TemporaryDirectory(prefix="glio-governed-firewall-") as temporary,
        TestClient(create_app(Path(temporary) / "events.sqlite")) as client,
    ):
        application = cast("FastAPI", client.app)
        routes = []
        pending = list(application.routes)
        while pending:
            route = pending.pop()
            included = getattr(route, "original_router", None)
            if included is not None:
                pending.extend(getattr(included, "routes", ()))
                continue
            path = getattr(route, "path", None)
            endpoint = getattr(route, "endpoint", None)
            if not isinstance(path, str) or endpoint is None:
                continue
            methods = ",".join(sorted(getattr(route, "methods", ())))
            routes.append(
                (
                    path,
                    methods,
                    _callback_module(endpoint) or "",
                    getattr(endpoint, "__qualname__", getattr(endpoint, "__name__", "")),
                )
            )
        return tuple(routes)


@pytest.mark.contract
def test_central_api_route_inventory_has_only_bounded_research_surface() -> None:
    """No route may masquerade as an unapproved research capability."""

    routes = _route_inventory()
    assert routes, "central API route inventory unexpectedly empty"
    discovered_research: set[str] = set()
    for path, methods, module, qualname in routes:
        public_metadata = f"{path} {methods} {module} {qualname}".lower()
        if any(token in public_metadata for token in _RESEARCH_CAPABILITY_MARKERS):
            discovered_research.add(path)
            assert path in {
                f"{prefix}{suffix}"
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
                for suffix in _RESEARCH_ROUTE_SUFFIXES
            }
            assert module == _research_route_module(path), (path, module)
    assert discovered_research == {
        f"{prefix}{suffix}"
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
        for suffix in _RESEARCH_ROUTE_SUFFIXES
    }


@pytest.mark.contract
def test_central_openapi_inventory_has_only_approved_research_operations() -> None:
    """Operation metadata cannot smuggle extra research execution public."""

    with (
        TemporaryDirectory(prefix="glio-governed-firewall-openapi-") as temporary,
        TestClient(create_app(Path(temporary) / "events.sqlite")) as client,
    ):
        document = client.get("/openapi.json").json()
    paths = document.get("paths")
    assert isinstance(paths, dict)
    assert paths
    exposed: set[str] = set()
    for path, operations in paths.items():
        if not isinstance(operations, dict):
            continue
        for method, operation in operations.items():
            if not isinstance(operation, dict):
                continue
            metadata = " ".join(
                str(operation.get(field, ""))
                for field in ("operationId", "summary", "description", "tags")
            )
            haystack = f"{path} {method} {metadata}".lower()
            if any(marker in haystack for marker in _RESEARCH_CAPABILITY_MARKERS):
                exposed.add(path)
    assert exposed == {
        f"{prefix}{suffix}"
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
        for suffix in _RESEARCH_ROUTE_SUFFIXES
    }


@pytest.mark.contract
def test_central_api_import_loads_the_approved_research_adapter() -> None:
    """Transport composition deliberately loads the narrow research adapter."""

    # Run in a fresh interpreter because another test file may already have
    # imported the research package in this process.  PYTHONPATH is explicit so
    # this checks the checkout rather than an installed wheel from another ref.
    script = (
        "import sys; "
        "import glio_proteogen.adapters.api; "
        "assert 'glio_proteogen.adapters.research_state' in sys.modules; "
        "assert 'glio_proteogen.research.proteogenomic_state' in sys.modules; "
        "assert 'glio_proteogen.adapters.gbm_functional_proteotype' in sys.modules; "
        "assert 'glio_proteogen.research.gbm_functional_proteotype' in sys.modules; "
        "assert 'glio_proteogen.adapters.glioma_models' in sys.modules; "
        "assert 'glio_proteogen.research.gbm_proteomic_axes' in sys.modules; "
        "assert 'glio_proteogen.adapters.neftel_programs' in sys.modules; "
        "assert 'glio_proteogen.research.neftel_protein_programs' in sys.modules; "
        "assert 'glio_proteogen.adapters.gbm_master_kinases' in sys.modules; "
        "assert 'glio_proteogen.research.gbm_master_kinases' in sys.modules; "
        "assert 'glio_proteogen.adapters.gbm_rna_purity' in sys.modules; "
        "assert 'glio_proteogen.research.gbm_rna_purity' in sys.modules; "
        "assert 'glio_proteogen.adapters.longitudinal_gbm' in sys.modules; "
        "assert 'glio_proteogen.research.longitudinal_gbm' in sys.modules"
        "; assert 'glio_proteogen.adapters.longitudinal_gbm_phospho' in sys.modules; "
        "assert 'glio_proteogen.research.longitudinal_gbm_phospho' in sys.modules; "
        "assert 'glio_proteogen.adapters.longitudinal_gbm_kinase_transition' "
        "in sys.modules; "
        "assert 'glio_proteogen.research.longitudinal_gbm_kinase_transition' "
        "in sys.modules; "
        "assert 'glio_proteogen.adapters.longitudinal_gbm_reactome_transition' "
        "in sys.modules; "
        "assert 'glio_proteogen.research.longitudinal_gbm_reactome_transition' "
        "in sys.modules; "
        "assert 'glio_proteogen.adapters.longitudinal_gbm_complex_transition' "
        "in sys.modules; "
        "assert 'glio_proteogen.research.longitudinal_gbm_complex_transition' "
        "in sys.modules; "
        "assert 'glio_proteogen.adapters.gbm_factor_graph' in sys.modules; "
        "assert 'glio_proteogen.research.kncc_gbm_factor_graph' in sys.modules; "
        "assert 'glio_proteogen.adapters.m10_functional_proteotype_facade' "
        "in sys.modules; "
        "assert 'glio_proteogen.research.m10_functional_proteotype_facade' "
        "in sys.modules; "
        "assert 'glio_proteogen.adapters.m11_protein_native_subtype_facade' "
        "in sys.modules; "
        "assert 'glio_proteogen.research.m11_protein_native_subtype_facade' "
        "in sys.modules; "
        "assert 'glio_proteogen.adapters.m14_microenvironment_protein_programs_facade' "
        "in sys.modules; "
        "assert 'glio_proteogen.research.m14_microenvironment_protein_programs_facade' "
        "in sys.modules"
    )
    result = subprocess.run(  # noqa: S603 - executable is the current test interpreter.
        [sys.executable, "-c", script],
        cwd=_REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(_SOURCE_ROOT)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


@pytest.mark.contract
def test_frozen_manifests_keep_research_claims_outside_governed_ceiling() -> None:
    """Manifest text remains explicit about the non-inference ceiling."""

    manifests = tuple(
        path
        for path in (_REPO_ROOT / "docs" / "modules").glob("M0[345]-*.manifest.md")
        if path.stem.split(".", maxsplit=1)[0] in _FROZEN_MANIFEST_MODULES
    )
    assert len(manifests) == len(_FROZEN_MANIFEST_MODULES)
    for manifest_path in manifests:
        text = manifest_path.read_text(encoding="utf-8").lower()
        assert "claims ceiling" in text, manifest_path
        assert "no" in text, manifest_path
        if manifest_path.name.startswith("M03-"):
            assert "protein inference" in text, manifest_path
        elif manifest_path.name.startswith("M04-"):
            assert "proteoform" in text, manifest_path
        else:
            assert "ptm" in text, manifest_path
        assert "research" not in text, (
            "governed manifest must not silently adopt research namespace claims",
            manifest_path,
        )
