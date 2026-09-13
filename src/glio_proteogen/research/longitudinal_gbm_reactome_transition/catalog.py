"""Fail-closed catalog for the Reactome V97/PDC000514 source binding.

The artifact contains pathway identities and zero-based indices into the already
verified KNCC protein feature axis.  It intentionally contains no patient values,
identifiers, fitted effects, or pathway-activity estimates.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from types import MappingProxyType
from typing import Final, Mapping, Never, cast

from glio_proteogen.research.longitudinal_gbm.catalog import (
    EXPECTED_ARTIFACT_BYTE_DIGEST as PARENT_ARTIFACT_BYTE_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm.catalog import (
    EXPECTED_CONTENT_DIGEST as PARENT_CONTENT_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm.catalog import (
    EXPECTED_FEATURE_SPACE_DIGEST as PARENT_FEATURE_SPACE_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm.catalog import (
    EXPECTED_SOURCE_FILE_LOCK_DIGEST as PARENT_SOURCE_FILE_LOCK_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm.catalog import (
    EXPECTED_SOURCE_MANIFEST_DIGEST as PARENT_SOURCE_MANIFEST_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm.catalog import longitudinal_gbm_catalog

from .errors import ReactomeTransitionSourceIntegrityError

ARTIFACT_RESOURCE: Final = "data/kncc_reactome_transition_source.v1.json"
PROFILE_ID: Final = "kncc-reactome-conditional-transition/1.0.0"
SCHEMA_VERSION: Final = "glio-proteogen.kncc-reactome-transition-source/1.0.0"
SELECTION_RULE_ID: Final = "gbm-mechanism-slots-reactome-v97/1.0.0"
EXPECTED_ARTIFACT_BYTES: Final = 34_279
EXPECTED_ARTIFACT_SHA256: Final = (
    "sha256:8446a9d923e047f0d4df9d190daca18f20faa932c471710efb733b8e2b1e631c"
)
EXPECTED_CONTENT_DIGEST: Final = (
    "sha256:0d0ad7b572aabed7049f302a44380166135cb2fed1527fe845a19457a8cbcdc6"
)
EXPECTED_SOURCE_BINDING_DIGEST: Final = (
    "sha256:84732b0bb2c89e82285c7b10fd567c3612eb89ae3a36846df0d7b88b6be59584"
)
EXPECTED_SELECTION_CANDIDATE_DIGEST: Final = (
    "sha256:c7ae590f4a1a13bea24de8bb8e6c2bed0369f4d54ca0081bbef373071d766a7c"
)
EXPECTED_PATHWAY_ORDER_DIGEST: Final = (
    "sha256:c8a1acae9b080feecb68d530b81f79ba673fcc6a7799baddb424349dcb1d95a0"
)
EXPECTED_PATHWAY_MEMBERSHIP_DIGEST: Final = (
    "sha256:7a801d5787c16e40e6824965ef5c7a78d819e09c4a11da0700a5e319c64f37c1"
)
EXPECTED_GENE_ORDER_DIGEST: Final = (
    "sha256:db1c48250032a6ea68211dcfa388acc8fea5b874c13a75198b3eec15f0234c65"
)
EXPECTED_PATIENT_ORDER_RULE_DIGEST: Final = (
    "sha256:e9339a2020313ccd2c1ea7bf300ed8229ec9112d3e6f358aa1968762b761b4cf"
)
EXPECTED_PATIENT_COUNT: Final = 104
EXPECTED_GENE_COUNT: Final = 11_312
EXPECTED_REACTOME_RELEASE: Final = 97
EXPECTED_PATHWAY_COUNT: Final = 10
EXPECTED_EXCLUDED_CANDIDATE_COUNT: Final = 12

EXPECTED_PATHWAYS: Final = (
    ("receptor_egfr", "R-HSA-177929", "Signaling by EGFR"),
    ("receptor_pdgf", "R-HSA-186797", "Signaling by PDGF"),
    ("second_messenger_pi3k_akt", "R-HSA-198203", "PI3K/AKT activation"),
    ("mtor_signaling", "R-HSA-165159", "MTOR signalling"),
    ("mapk_cascades", "R-HSA-5683057", "MAPK family signaling cascades"),
    ("cell_cycle", "R-HSA-1640170", "Cell Cycle"),
    ("dna_repair", "R-HSA-73894", "DNA Repair"),
    ("hypoxia_response", "R-HSA-1234174", "Cellular response to hypoxia"),
    ("extracellular_matrix", "R-HSA-1474244", "Extracellular matrix organization"),
    ("innate_immune_system", "R-HSA-168249", "Innate Immune System"),
)

EXPECTED_REACTOME_FILES: Final = (
    (
        "ReactomePathways.gmt.zip",
        298_479,
        "sha256:8c1dbc8578431da5d2d5118262718c60b553a9be3398e93658daa069e4a9afd4",
    ),
    (
        "gmt/ReactomePathways.gmt",
        1_032_186,
        "sha256:89983d5c1f0af11c52edfeee7323eb425580ac6281d387a528562ab1787ce56b",
    ),
    (
        "ReactomePathways.txt",
        1_592_393,
        "sha256:f6d7a2bf89b5bcfe0250a0bc7f51bff94641447911712b8ff129f5b55e52df3a",
    ),
    (
        "ReactomePathwaysRelation.txt",
        634_259,
        "sha256:fd49a624d80c14eb37ae57a02e141d574d5ede3f60022bb99edbd909448a3f1e",
    ),
)


@dataclass(frozen=True, slots=True)
class ReactomeSourceFile:
    """One byte-locked Reactome input used for the projection."""

    relative_path: str
    bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ExcludedReactomeCandidate:
    """One transparent, pre-outcome non-selection from the nearby domain scope."""

    domain_id: str
    reactome_id: str
    name: str
    reason: str


@dataclass(frozen=True, slots=True)
class ReactomePathwayBinding:
    """One exact Reactome event projected onto the KNCC HGNC feature axis."""

    panel_index: int
    domain_id: str
    reactome_id: str
    name: str
    species: str
    rationale: str
    parent_ids: tuple[str, ...]
    source_member_count: int
    source_member_digest: str
    mapped_feature_count: int
    mapping_fraction: float
    eligible_feature_count: int
    member_feature_indices: tuple[int, ...]
    eligible_feature_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ReactomeTransitionSourceCatalog:
    """Immutable, verified input catalog for the future conditional model."""

    profile_id: str
    patient_count: int
    patient_ordering_policy: str
    patient_order_rule_digest: str
    genes: tuple[str, ...]
    gene_index_by_symbol: Mapping[str, int]
    gene_order_digest: str
    pathways: tuple[ReactomePathwayBinding, ...]
    pathway_by_id: Mapping[str, ReactomePathwayBinding]
    pathway_by_domain: Mapping[str, ReactomePathwayBinding]
    excluded_candidates: tuple[ExcludedReactomeCandidate, ...]
    reactome_release: int
    reactome_files: tuple[ReactomeSourceFile, ...]
    artifact_byte_digest: str
    content_digest: str
    source_binding_digest: str
    selection_candidate_digest: str
    pathway_order_digest: str
    pathway_membership_digest: str
    provenance: Mapping[str, str | int]
    limitations: tuple[str, ...]


def _resource_bytes() -> bytes:
    return files(__package__).joinpath(ARTIFACT_RESOURCE).read_bytes()


def _fail(message: str) -> Never:
    raise ReactomeTransitionSourceIntegrityError(message)


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _object(value: object, name: str) -> dict[str, object]:
    if type(value) is not dict:
        _fail(f"artifact field {name!r} must be an object")
    return cast("dict[str, object]", value)


def _list(value: object, name: str) -> list[object]:
    if type(value) is not list:
        _fail(f"artifact field {name!r} must be an array")
    return cast("list[object]", value)


def _integer(value: object, name: str) -> int:
    if type(value) is not int:
        _fail(f"artifact field {name!r} must be an integer")
    return value


def _finite(value: object, name: str) -> float:
    if type(value) not in {int, float}:
        _fail(f"artifact field {name!r} must be numeric")
    parsed = float(cast("int | float", value))
    if not math.isfinite(parsed):
        _fail(f"artifact field {name!r} must be finite")
    return parsed


def _validate_top_level(
    document: dict[str, object],
) -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    list[object],
]:
    if document.get("schema_version") != SCHEMA_VERSION:
        _fail("Reactome transition source schema mismatch")
    if document.get("profile_id") != PROFILE_ID:
        _fail("Reactome transition profile identifier mismatch")
    expected_role = "source admission and feature binding only; no fitted pathway model"
    if document.get("artifact_role") != expected_role:
        _fail("Reactome transition artifact role mismatch")
    patient_axis = _object(document.get("patient_axis"), "patient_axis")
    gene_axis = _object(document.get("gene_axis"), "gene_axis")
    selection = _object(document.get("selection"), "selection")
    bindings = _object(document.get("source_bindings"), "source_bindings")
    pathways = _list(document.get("pathways"), "pathways")
    return patient_axis, gene_axis, selection, bindings, pathways


def _validate_projection_digests(
    document: dict[str, object],
    selection: dict[str, object],
    bindings: dict[str, object],
    pathways: list[object],
) -> None:
    projection = _object(document.get("projection_digests"), "projection_digests")
    pathway_documents = [_object(value, "pathway") for value in pathways]
    computed = {
        "source_binding_digest": _digest(bindings),
        "selection_candidate_digest": _digest(selection),
        "pathway_order_digest": _digest(
            [item.get("reactome_id") for item in pathway_documents]
        ),
        "pathway_membership_digest": _digest(
            [
                {
                    "reactome_id": item.get("reactome_id"),
                    "source_member_digest": item.get("source_member_digest"),
                    "member_feature_indices": item.get("member_feature_indices"),
                    "eligible_feature_indices": item.get("eligible_feature_indices"),
                }
                for item in pathway_documents
            ]
        ),
    }
    locked = {
        "source_binding_digest": EXPECTED_SOURCE_BINDING_DIGEST,
        "selection_candidate_digest": EXPECTED_SELECTION_CANDIDATE_DIGEST,
        "pathway_order_digest": EXPECTED_PATHWAY_ORDER_DIGEST,
        "pathway_membership_digest": EXPECTED_PATHWAY_MEMBERSHIP_DIGEST,
    }
    if any(projection.get(key) != value for key, value in computed.items()):
        _fail("Reactome transition self-declared projection digest mismatch")
    if computed != locked:
        _fail("Reactome transition locked projection digest mismatch")


def _validate_parent_binding(bindings: dict[str, object]) -> tuple[ReactomeSourceFile, ...]:
    pdc = _object(bindings.get("pdc000514"), "source_bindings.pdc000514")
    expected_pdc = {
        "study_id": "PDC000514",
        "study_version_uuid": "524d5116-b6de-4e36-892a-e35dba7d0170",
        "parent_model_id": "kncc-paired-protein-transition/1.0.0",
        "parent_artifact_byte_digest": PARENT_ARTIFACT_BYTE_DIGEST,
        "parent_artifact_content_digest": PARENT_CONTENT_DIGEST,
        "parent_feature_space_digest": PARENT_FEATURE_SPACE_DIGEST,
        "parent_source_file_lock_digest": PARENT_SOURCE_FILE_LOCK_DIGEST,
        "versioned_source_manifest_digest": PARENT_SOURCE_MANIFEST_DIGEST,
    }
    if pdc != expected_pdc:
        _fail("Reactome transition parent PDC000514 binding mismatch")
    reactome = _object(bindings.get("reactome"), "source_bindings.reactome")
    if (
        reactome.get("declared_release") != EXPECTED_REACTOME_RELEASE
        or reactome.get("release_attestation")
        != "release number is supplied by the local cache label; exact bytes are authoritative"
    ):
        _fail("Reactome release binding mismatch")
    source_files: list[ReactomeSourceFile] = []
    file_rows = _list(reactome.get("files"), "source_bindings.reactome.files")
    observed: list[tuple[str, int, str]] = []
    for value in file_rows:
        item = _object(value, "Reactome file")
        row = (
            str(item.get("relative_path")),
            _integer(item.get("bytes"), "Reactome bytes"),
            str(item.get("sha256")),
        )
        observed.append(row)
        source_files.append(ReactomeSourceFile(*row))
    if tuple(observed) != EXPECTED_REACTOME_FILES:
        _fail("Reactome source-file lock mismatch")
    return tuple(source_files)


def _validate_selection(selection: dict[str, object]) -> tuple[ExcludedReactomeCandidate, ...]:
    if (
        selection.get("rule_id") != SELECTION_RULE_ID
        or "no patient transition value" not in str(selection.get("rule"))
    ):
        _fail("Reactome pre-outcome selection rule mismatch")
    gate = _object(selection.get("assay_gate"), "selection.assay_gate")
    if gate != {
        "identity_policy": "exact approved HGNC symbol intersection only",
        "minimum_source_genes": 5,
        "maximum_source_genes": 1_500,
        "minimum_mapped_genes": 5,
        "minimum_mapping_fraction": 0.65,
    }:
        _fail("Reactome assay-identity gate mismatch")
    candidate_values = _list(
        selection.get("excluded_candidates"),
        "selection.excluded_candidates",
    )
    candidates: list[ExcludedReactomeCandidate] = []
    for value in candidate_values:
        item = _object(value, "excluded candidate")
        candidates.append(
            ExcludedReactomeCandidate(
                domain_id=str(item.get("domain_id")),
                reactome_id=str(item.get("reactome_id")),
                name=str(item.get("name")),
                reason=str(item.get("reason")),
            )
        )
    if (
        len(candidates) != EXPECTED_EXCLUDED_CANDIDATE_COUNT
        or len({item.reactome_id for item in candidates}) != len(candidates)
        or not any("EMT" in item.name for item in candidates)
        or not any(item.name == "Apoptosis" for item in candidates)
    ):
        _fail("Reactome excluded-candidate inventory mismatch")
    return tuple(candidates)


def _validate_axes(
    patient_axis: dict[str, object],
    gene_axis: dict[str, object],
) -> tuple[tuple[str, ...], Mapping[str, int]]:
    if patient_axis != {
        "count": EXPECTED_PATIENT_COUNT,
        "identifier_or_identifier_hash_bundled": False,
        "identifiers_bundled": False,
        "ordering_policy": (
            "lexicographic KNCC patient-group order after complete T1/T2 selection and "
            "official versioned sample-type exclusions"
        ),
        "ordering_rule_digest": EXPECTED_PATIENT_ORDER_RULE_DIGEST,
    }:
        _fail("Reactome transition patient-axis policy mismatch")
    if (
        gene_axis.get("count") != EXPECTED_GENE_COUNT
        or gene_axis.get("order_digest") != EXPECTED_GENE_ORDER_DIGEST
        or gene_axis.get("symbols_not_duplicated") is not True
        or gene_axis.get("ordering_basis")
        != "exact ordered feature array in the locked parent protein model"
    ):
        _fail("Reactome transition gene-axis binding mismatch")
    parent = longitudinal_gbm_catalog()
    genes = tuple(feature.gene_symbol for feature in parent.features)
    if len(genes) != EXPECTED_GENE_COUNT or _digest(list(genes)) != EXPECTED_GENE_ORDER_DIGEST:
        _fail("Reactome transition parent feature order mismatch")
    return genes, MappingProxyType({symbol: index for index, symbol in enumerate(genes)})


def _parse_pathways(
    pathways: list[object],
    *,
    parent_eligible_indices: frozenset[int],
) -> tuple[ReactomePathwayBinding, ...]:
    if len(pathways) != EXPECTED_PATHWAY_COUNT:
        _fail("Reactome transition pathway count mismatch")
    result: list[ReactomePathwayBinding] = []
    for index, (value, expected) in enumerate(zip(pathways, EXPECTED_PATHWAYS, strict=True)):
        item = _object(value, f"pathways[{index}]")
        domain_id, reactome_id, name = expected
        indices = tuple(
            _integer(entry, "member feature index")
            for entry in _list(item.get("member_feature_indices"), "member indices")
        )
        eligible_indices = tuple(
            _integer(entry, "eligible feature index")
            for entry in _list(item.get("eligible_feature_indices"), "eligible indices")
        )
        source_count = _integer(item.get("source_member_count"), "source member count")
        mapped_count = _integer(item.get("mapped_feature_count"), "mapped feature count")
        eligible_count = _integer(item.get("eligible_feature_count"), "eligible feature count")
        mapping_fraction = _finite(item.get("mapping_fraction"), "mapping fraction")
        if (
            item.get("panel_index") != index
            or (item.get("domain_id"), item.get("reactome_id"), item.get("name")) != expected
            or item.get("species") != "Homo sapiens"
            or not str(item.get("source_member_digest")).startswith("sha256:")
            or len(str(item.get("source_member_digest"))) != 71
            or indices != tuple(sorted(set(indices)))
            or eligible_indices != tuple(sorted(set(eligible_indices)))
            or any(not 0 <= feature_index < EXPECTED_GENE_COUNT for feature_index in indices)
            or not set(eligible_indices).issubset(indices)
            or frozenset(indices).intersection(parent_eligible_indices)
            != frozenset(eligible_indices)
            or mapped_count != len(indices)
            or eligible_count != len(eligible_indices)
            or not 5 <= source_count <= 1_500
            or mapped_count < 5
            or not math.isclose(mapping_fraction, mapped_count / source_count, abs_tol=5e-11)
            or mapping_fraction < 0.65
        ):
            _fail(f"Reactome transition pathway invariant mismatch: {reactome_id}")
        parent_ids = tuple(
            str(entry) for entry in _list(item.get("parent_ids"), "parent identifiers")
        )
        if parent_ids != tuple(sorted(set(parent_ids))):
            _fail("Reactome parent identifiers must be sorted and unique")
        result.append(
            ReactomePathwayBinding(
                panel_index=index,
                domain_id=domain_id,
                reactome_id=reactome_id,
                name=name,
                species="Homo sapiens",
                rationale=str(item.get("rationale")),
                parent_ids=parent_ids,
                source_member_count=source_count,
                source_member_digest=str(item.get("source_member_digest")),
                mapped_feature_count=mapped_count,
                mapping_fraction=mapping_fraction,
                eligible_feature_count=eligible_count,
                member_feature_indices=indices,
                eligible_feature_indices=eligible_indices,
            )
        )
    return tuple(result)


@lru_cache(maxsize=1)
def reactome_transition_source_catalog() -> ReactomeTransitionSourceCatalog:
    """Load and independently verify the compact Reactome/PDC000514 binding."""

    raw_bytes = _resource_bytes()
    if len(raw_bytes) != EXPECTED_ARTIFACT_BYTES:
        _fail("Reactome transition artifact byte length mismatch")
    artifact_byte_digest = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
    if artifact_byte_digest != EXPECTED_ARTIFACT_SHA256:
        _fail("Reactome transition artifact byte digest mismatch")
    try:
        document = cast("dict[str, object]", json.loads(raw_bytes))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReactomeTransitionSourceIntegrityError(
            "Reactome transition artifact is not valid JSON"
        ) from error
    if type(document) is not dict or _canonical_bytes(document) != raw_bytes:
        _fail("Reactome transition artifact must be canonical JSON")
    content = dict(document)
    declared_content_digest = content.pop("artifact_digest", None)
    content_digest = _digest(content)
    if content_digest != EXPECTED_CONTENT_DIGEST or declared_content_digest != content_digest:
        _fail("Reactome transition canonical content digest mismatch")

    patient_axis, gene_axis, selection, bindings, pathway_values = _validate_top_level(document)
    _validate_projection_digests(document, selection, bindings, pathway_values)
    reactome_files = _validate_parent_binding(bindings)
    excluded_candidates = _validate_selection(selection)
    genes, gene_index = _validate_axes(patient_axis, gene_axis)
    parent = longitudinal_gbm_catalog()
    eligible_indices = frozenset(feature.index for feature in parent.features if feature.eligible)
    pathways = _parse_pathways(
        pathway_values,
        parent_eligible_indices=eligible_indices,
    )
    pathway_by_id = MappingProxyType({item.reactome_id: item for item in pathways})
    pathway_by_domain = MappingProxyType({item.domain_id: item for item in pathways})
    if len(pathway_by_id) != len(pathways) or len(pathway_by_domain) != len(pathways):
        _fail("Reactome pathway identifiers or domains are duplicated")

    provenance_document = _object(document.get("provenance"), "provenance")
    provenance: dict[str, str | int] = {}
    for key, value in provenance_document.items():
        if type(value) not in {str, int}:
            _fail("Reactome provenance values must be scalar")
        provenance[key] = cast("str | int", value)
    limitations = tuple(
        str(value) for value in _list(document.get("limitations"), "limitations")
    )
    if len(limitations) < 6 or not all(limitations):
        _fail("Reactome transition limitation inventory mismatch")
    projection = _object(document["projection_digests"], "projection_digests")
    return ReactomeTransitionSourceCatalog(
        profile_id=PROFILE_ID,
        patient_count=EXPECTED_PATIENT_COUNT,
        patient_ordering_policy=str(patient_axis["ordering_policy"]),
        patient_order_rule_digest=EXPECTED_PATIENT_ORDER_RULE_DIGEST,
        genes=genes,
        gene_index_by_symbol=gene_index,
        gene_order_digest=EXPECTED_GENE_ORDER_DIGEST,
        pathways=pathways,
        pathway_by_id=pathway_by_id,
        pathway_by_domain=pathway_by_domain,
        excluded_candidates=excluded_candidates,
        reactome_release=EXPECTED_REACTOME_RELEASE,
        reactome_files=reactome_files,
        artifact_byte_digest=artifact_byte_digest,
        content_digest=content_digest,
        source_binding_digest=str(projection["source_binding_digest"]),
        selection_candidate_digest=str(projection["selection_candidate_digest"]),
        pathway_order_digest=str(projection["pathway_order_digest"]),
        pathway_membership_digest=str(projection["pathway_membership_digest"]),
        provenance=MappingProxyType(provenance),
        limitations=limitations,
    )
