"""Versioned synthetic graph used for examples, replay checks, and benchmarks."""

from __future__ import annotations

from .canonical import graph_topology_digest, sha256_digest
from .contracts import (
    EdgeKind,
    EvidenceModality,
    EvidenceObservation,
    EvidenceState,
    ExternalKinaseEstimate,
    ExternalKinaseProfile,
    GraphEdge,
    GraphNode,
    NodeKind,
    ProteogenomicStateRequest,
    PublicTopologySource,
    TopologyProvenance,
)

DEMO_ID = "synthetic-glioma-demo-v1"
_REACTOME_RELEASE = "97"
_REACTOME_LICENSE_URI = "https://creativecommons.org/publicdomain/zero/1.0/"

_PROTEINS = (
    "EGFR",
    "PTEN",
    "AKT1",
    "MAPK1",
    "CDK1",
    "MTOR",
    "RB1",
    "TP53",
    "GFAP",
    "OLIG2",
    "PDGFRA",
    "NF1",
    "PIK3CA",
    "STAT3",
    "CDK2",
    "ERBB3",
)
_PROTEOFORMS = (
    "EGFR.vIII",
    "PTEN.canonical",
    "AKT1.canonical",
    "MAPK1.canonical",
    "CDK1.canonical",
    "MTOR.canonical",
    "RB1.canonical",
    "TP53.canonical",
    "PDGFRA.canonical",
    "NF1.canonical",
    "STAT3.canonical",
    "ERBB3.canonical",
)
_PHOSPHOSITES = (
    "EGFR.Y1068",
    "EGFR.Y1173",
    "ERBB3.Y1289",
    "STAT3.Y705",
    "GAB1.Y627",
    "SHC1.Y317",
    "AKT1.S473",
    "AKT1.T308",
    "MTOR.S2448",
    "GSK3B.S9",
    "FOXO3.S253",
    "TSC2.T1462",
    "MAPK1.T185",
    "MAPK1.Y187",
    "ELK1.S383",
    "RPS6KA1.S380",
    "JUN.S63",
    "MYC.S62",
    "CDK1.Y15",
    "RB1.S807",
    "LMNA.S22",
    "NPM1.T199",
    "HIST1H1E.S18",
    "CDC25C.S216",
)
_COMPLEXES = ("PI3K", "mTORC1", "CDK1-cyclinB", "RB-E2F", "EGFR-ERBB3")
_PATHWAYS = ("RTK-signaling", "PI3K-AKT-mTOR", "cell-cycle")
_KINASES = ("EGFR-kinase", "AKT1-kinase", "MAPK1-kinase", "CDK1-kinase")


def _node_id(kind: NodeKind, name: str) -> str:
    normalized = name.replace("-", ".").replace(" ", ".")
    return f"{kind.value}.{normalized}"


def _nodes() -> tuple[GraphNode, ...]:
    groups = (
        (NodeKind.PROTEIN, _PROTEINS),
        (NodeKind.PROTEOFORM, _PROTEOFORMS),
        (NodeKind.PHOSPHOSITE, _PHOSPHOSITES),
        (NodeKind.COMPLEX, _COMPLEXES),
        (NodeKind.PATHWAY, _PATHWAYS),
        (NodeKind.KINASE, _KINASES),
    )
    return tuple(
        GraphNode(node_id=_node_id(kind, name), kind=kind, display_name=name)
        for kind, names in groups
        for name in names
    )


def _edge(
    sequence: int,
    *,
    source_kind: NodeKind,
    source: str,
    target_kind: NodeKind,
    target: str,
    kind: EdgeKind,
    sign: int = 1,
    weight: float = 1.0,
    essential: bool = False,
) -> GraphEdge:
    return GraphEdge(
        edge_id=f"edge.{sequence:03d}",
        source_id=_node_id(source_kind, source),
        target_id=_node_id(target_kind, target),
        kind=kind,
        sign=sign,  # type: ignore[arg-type]
        weight=weight,
        essential=essential,
    )


def _edges() -> tuple[GraphEdge, ...]:
    rows: list[tuple[NodeKind, str, NodeKind, str, EdgeKind, int, float, bool]] = []
    for proteoform in _PROTEOFORMS:
        protein = proteoform.split(".", maxsplit=1)[0]
        rows.append(
            (
                NodeKind.PROTEOFORM,
                proteoform,
                NodeKind.PROTEIN,
                protein,
                EdgeKind.PROTEOFORM_OF,
                1,
                1.2,
                False,
            )
        )
    site_parents = (
        "EGFR.vIII",
        "EGFR.vIII",
        "ERBB3.canonical",
        "STAT3.canonical",
        "EGFR.vIII",
        "EGFR.vIII",
        "AKT1.canonical",
        "AKT1.canonical",
        "MTOR.canonical",
        "AKT1.canonical",
        "AKT1.canonical",
        "AKT1.canonical",
        "MAPK1.canonical",
        "MAPK1.canonical",
        "MAPK1.canonical",
        "MAPK1.canonical",
        "MAPK1.canonical",
        "MAPK1.canonical",
        "CDK1.canonical",
        "RB1.canonical",
        "CDK1.canonical",
        "CDK1.canonical",
        "CDK1.canonical",
        "CDK1.canonical",
    )
    for site, parent in zip(_PHOSPHOSITES, site_parents, strict=True):
        rows.append(
            (
                NodeKind.PHOSPHOSITE,
                site,
                NodeKind.PROTEOFORM,
                parent,
                EdgeKind.SITE_OF,
                1,
                0.35,
                False,
            )
        )
    for kinase_index, kinase in enumerate(_KINASES):
        for site_index in range(kinase_index * 6, kinase_index * 6 + 6):
            sign = -1 if site_index in {18, 23} else 1
            rows.append(
                (
                    NodeKind.KINASE,
                    kinase,
                    NodeKind.PHOSPHOSITE,
                    _PHOSPHOSITES[site_index],
                    EdgeKind.KINASE_SUBSTRATE,
                    sign,
                    1.0,
                    False,
                )
            )
    membership = (
        ("PIK3CA", "PI3K", True),
        ("PTEN", "PI3K", False),
        ("MTOR", "mTORC1", True),
        ("CDK1", "CDK1-cyclinB", True),
        ("RB1", "RB-E2F", True),
        ("EGFR", "EGFR-ERBB3", True),
        ("ERBB3", "EGFR-ERBB3", True),
    )
    for protein, complex_name, essential in membership:
        rows.append(
            (
                NodeKind.PROTEIN,
                protein,
                NodeKind.COMPLEX,
                complex_name,
                EdgeKind.MEMBER_OF,
                1,
                1.0,
                essential,
            )
        )
    pathway_members = (
        (NodeKind.PROTEIN, "EGFR", "RTK-signaling", 1),
        (NodeKind.PROTEIN, "PDGFRA", "RTK-signaling", 1),
        (NodeKind.COMPLEX, "EGFR-ERBB3", "RTK-signaling", 1),
        (NodeKind.COMPLEX, "PI3K", "PI3K-AKT-mTOR", 1),
        (NodeKind.PROTEIN, "PTEN", "PI3K-AKT-mTOR", -1),
        (NodeKind.PROTEIN, "AKT1", "PI3K-AKT-mTOR", 1),
        (NodeKind.COMPLEX, "mTORC1", "PI3K-AKT-mTOR", 1),
        (NodeKind.COMPLEX, "CDK1-cyclinB", "cell-cycle", 1),
        (NodeKind.COMPLEX, "RB-E2F", "cell-cycle", -1),
        (NodeKind.PROTEIN, "TP53", "cell-cycle", -1),
    )
    for source_kind, source, pathway, sign in pathway_members:
        rows.append(
            (
                source_kind,
                source,
                NodeKind.PATHWAY,
                pathway,
                EdgeKind.PARTICIPATES_IN,
                sign,
                0.8,
                False,
            )
        )
    regulations = (
        ("EGFR", "PIK3CA", 1),
        ("PTEN", "AKT1", -1),
        ("AKT1", "MTOR", 1),
        ("NF1", "MAPK1", -1),
        ("MAPK1", "MYC", 1),
        ("CDK1", "RB1", -1),
    )
    # MYC only exists as a phosphosite-bearing signal, so target its measured site.
    for source, target, sign in regulations:
        target_kind = NodeKind.PROTEIN
        target_name = target
        if target == "MYC":
            target_kind = NodeKind.PHOSPHOSITE
            target_name = "MYC.S62"
        rows.append(
            (
                NodeKind.PROTEIN,
                source,
                target_kind,
                target_name,
                EdgeKind.REGULATES,
                sign,
                0.65,
                False,
            )
        )
    return tuple(
        _edge(
            index,
            source_kind=source_kind,
            source=source,
            target_kind=target_kind,
            target=target,
            kind=kind,
            sign=sign,
            weight=weight,
            essential=essential,
        )
        for index, (
            source_kind,
            source,
            target_kind,
            target,
            kind,
            sign,
            weight,
            essential,
        ) in enumerate(rows, start=1)
    )


def _observation(
    index: int,
    *,
    node_id: str,
    modality: EvidenceModality,
    state: EvidenceState,
    effect: float | None,
    error: float | None,
    quality: float,
) -> EvidenceObservation:
    return EvidenceObservation(
        observation_id=f"obs.{index:03d}",
        node_id=node_id,
        modality=modality,
        state=state,
        standardized_effect=effect,
        standard_error=error,
        quality_weight=quality,
        provenance_digest=sha256_digest(
            {"demo": DEMO_ID, "modality": modality.value, "observation": index}
        ),
    )


def _observations() -> tuple[EvidenceObservation, ...]:
    observations: list[EvidenceObservation] = []
    protein_effects = (
        1.4,
        -1.1,
        0.8,
        0.6,
        0.5,
        0.9,
        -0.7,
        -0.4,
        0.2,
        0.7,
        0.9,
        -0.8,
        1.0,
        0.8,
        0.3,
        0.9,
    )
    for protein, effect in zip(_PROTEINS, protein_effects, strict=True):
        observations.append(
            _observation(
                len(observations) + 1,
                node_id=_node_id(NodeKind.PROTEIN, protein),
                modality=EvidenceModality.PROTEOMICS,
                state=EvidenceState.OBSERVED,
                effect=effect,
                error=0.25,
                quality=0.92,
            )
        )
    site_effects = (
        2.2,
        2.0,
        1.8,
        1.7,
        1.6,
        1.5,
        1.3,
        1.2,
        1.1,
        0.9,
        0.8,
        0.7,
        0.6,
        0.5,
        0.4,
        0.3,
        0.2,
        0.1,
        -0.2,
        -0.4,
        -0.6,
        -0.8,
        -1.0,
        -1.2,
    )
    for site, effect in zip(_PHOSPHOSITES, site_effects, strict=True):
        state = EvidenceState.OBSERVED
        current_effect: float | None = effect
        current_error: float | None = 0.22
        quality = 0.95
        if site == "HIST1H1E.S18":
            state = EvidenceState.LEFT_CENSORED
            current_effect = -0.85
            current_error = 0.35
            quality = 0.7
        elif site == "CDC25C.S216":
            state = EvidenceState.MISSING
            current_effect = None
            current_error = None
            quality = 0.0
        observations.append(
            _observation(
                len(observations) + 1,
                node_id=_node_id(NodeKind.PHOSPHOSITE, site),
                modality=EvidenceModality.PHOSPHOPROTEOMICS,
                state=state,
                effect=current_effect,
                error=current_error,
                quality=quality,
            )
        )
    return tuple(observations)


def demo_graph_digest() -> str:
    """Digest only the synthetic topology, independent of sample and observations."""

    return graph_topology_digest({"edges": list(_edges()), "nodes": list(_nodes())})


def demo_topology_provenance() -> TopologyProvenance:
    """Return content-addressed public context for the synthetic demo topology."""

    source_rows = (
        (
            "reactome.R-HSA-177929.release97",
            "R-HSA-177929",
            "Signaling by EGFR",
            "pathway.RTK.signaling",
            715_097,
            "8bfd16fd5aa56ac37ff1d3e8e1bc8a14f27d5ca9cf4204bcfc2231e004823260",
        ),
        (
            "reactome.R-HSA-1257604.release97",
            "R-HSA-1257604",
            "PIP3 activates AKT signaling",
            "pathway.PI3K.AKT.mTOR",
            1_085_445,
            "8274c7abb68f83738c46b7156f81f2546a51720f57ef5997c1353de92aeb4c1a",
        ),
        (
            "reactome.R-HSA-69278.release97",
            "R-HSA-69278",
            "Cell Cycle, Mitotic",
            "pathway.cell.cycle",
            3_546_893,
            "5c14a87dc086a50327c09191e001d7d1cb86231eaf34646cc8f4c3555df62ad4",
        ),
    )
    sources = tuple(
        PublicTopologySource(
            source_id=source_id,
            resource_name="Reactome",
            resource_release=_REACTOME_RELEASE,
            record_id=record_id,
            record_title=record_title,
            source_uri=(f"https://reactome.org/ContentService/exporter/event/{record_id}.sbml"),
            source_format="SBML Level 3 Version 1",
            source_digest=f"sha256:{digest}",
            source_size_bytes=size_bytes,
            license_id="CC0-1.0",
            license_uri=_REACTOME_LICENSE_URI,
            retrieved_on="2026-08-27",
            scope_node_ids=(scope_node_id,),
        )
        for source_id, record_id, record_title, scope_node_id, size_bytes, digest in source_rows
    )
    return TopologyProvenance(
        topology_digest=demo_graph_digest(),
        derivation="synthetic_abstraction",
        sources=sources,
        curation_note=(
            "Reactome records provide biological context for the three pathway nodes only. "
            "The node selection, edges, signs, weights, essential flags, and observations are "
            "repository-native synthetic demo choices, not a Reactome export or patient data."
        ),
    )


def demo_topology_provenance_digest() -> str:
    """Bind the exact public citations and their graph-scoping declaration."""

    return sha256_digest(demo_topology_provenance().model_dump(mode="json"))


def synthetic_demo_request() -> ProteogenomicStateRequest:
    """Return a 64-node glioma-like example containing synthetic measurements only."""

    external = ExternalKinaseProfile(
        profile_id="kinophos.synthetic.v1",
        source_digest=sha256_digest({"demo": DEMO_ID, "external": "synthetic"}),
        estimates=(
            ExternalKinaseEstimate(
                kinase_id=_node_id(NodeKind.KINASE, "EGFR-kinase"),
                activity=1.2,
                lower_bound=0.7,
                upper_bound=1.7,
            ),
            ExternalKinaseEstimate(
                kinase_id=_node_id(NodeKind.KINASE, "AKT1-kinase"),
                activity=0.7,
                lower_bound=0.2,
                upper_bound=1.2,
            ),
            ExternalKinaseEstimate(
                kinase_id=_node_id(NodeKind.KINASE, "CDK1-kinase"),
                activity=0.3,
                lower_bound=-0.2,
                upper_bound=0.8,
            ),
        ),
    )
    return ProteogenomicStateRequest(
        sample_id=DEMO_ID,
        nodes=_nodes(),
        edges=_edges(),
        observations=_observations(),
        bootstrap_replicates=64,
        permutation_replicates=256,
        external_kinase_profile=external,
        topology_provenance=demo_topology_provenance(),
    )


__all__ = [
    "DEMO_ID",
    "demo_graph_digest",
    "demo_topology_provenance",
    "demo_topology_provenance_digest",
    "synthetic_demo_request",
]
