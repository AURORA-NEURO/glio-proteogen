"""Content-bound profile for local CPTAC GBM discordance evidence."""

from __future__ import annotations

import ast
from importlib.resources import files
from typing import Final

import numpy as np

from glio_proteogen.kernel.canonical import sha256_digest

from .canonical import profile_digest
from .contracts import (
    AlgorithmConstants,
    AlgorithmLimits,
    TranscriptProteinDiscordanceProfile,
)
from .source import EXACT_SOURCE_LOCKS

EXPECTED_NUMPY_VERSION: Final = "2.5.2"
_SEMANTIC_FILES: Final = (
    "__init__.py",
    "artifact.py",
    "canonical.py",
    "contracts.py",
    "errors.py",
    "fitter.py",
    "model.py",
    "profile.py",
    "service.py",
    "source.py",
)
_SHARED_SCIENTIFIC_PACKAGE: Final = "glio_proteogen.research.cptac_gbm_cis_dosage"
_SHARED_SCIENTIFIC_FILES: Final = (
    "contracts.py",
    "errors.py",
    "model.py",
    "ooxml.py",
    "source.py",
)
_ADAPTER_PACKAGE: Final = "glio_proteogen.adapters"
_LOCAL_CLI_ADAPTER_FILE: Final = "cptac_gbm_transcript_protein_discordance.py"
_SURFACE_BINDING_MARKER: Final = "cptac_gbm_transcript_protein_discordance"


def _canonical_ast(source: bytes) -> str:
    text = source.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return ast.dump(ast.parse(text), annotate_fields=True, include_attributes=False)


def _matching_top_level_ast(source: bytes, marker: str) -> str:
    text = source.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    parsed = ast.parse(text)
    body = [
        node
        for node in parsed.body
        if marker in ast.dump(node, annotate_fields=True, include_attributes=False)
    ]
    return ast.dump(
        ast.Module(body=body, type_ignores=[]),
        annotate_fields=True,
        include_attributes=False,
    )


def engine_semantic_digest() -> str:
    root = files(__package__)
    shared_root = files(_SHARED_SCIENTIFIC_PACKAGE)
    adapter_root = files(_ADAPTER_PACKAGE)
    return sha256_digest(
        {
            "local_engine": {
                name: _canonical_ast(root.joinpath(name).read_bytes()) for name in _SEMANTIC_FILES
            },
            "shared_scientific_dependencies": {
                f"{_SHARED_SCIENTIFIC_PACKAGE}/{name}": _canonical_ast(
                    shared_root.joinpath(name).read_bytes()
                )
                for name in _SHARED_SCIENTIFIC_FILES
            },
            "declared_surface_bindings": {
                "local_cli_adapter": _canonical_ast(
                    adapter_root.joinpath(_LOCAL_CLI_ADAPTER_FILE).read_bytes()
                ),
                "central_cli_registration": _matching_top_level_ast(
                    adapter_root.joinpath("cli.py").read_bytes(),
                    _SURFACE_BINDING_MARKER,
                ),
                "central_http_absence": _matching_top_level_ast(
                    adapter_root.joinpath("api.py").read_bytes(),
                    _SURFACE_BINDING_MARKER,
                ),
            },
        }
    )


def algorithm_profile() -> TranscriptProteinDiscordanceProfile:
    """Return the exact local-only, cohort-query algorithm profile."""

    if np.__version__ != EXPECTED_NUMPY_VERSION:
        raise RuntimeError("CPTAC GBM discordance evidence requires NumPy 2.5.2")
    semantic_digest = engine_semantic_digest()
    constants = AlgorithmConstants()
    limits = AlgorithmLimits()
    payload = {
        "algorithm_id": "cptac-gbm-transcript-protein-discordance",
        "algorithm_version": "1.0.0",
        "profile_id": "cptac-gbm-transcript-protein-discordance/1.0.0",
        "engine_semantic_digest": semantic_digest,
        "numpy_version": np.__version__,
        "constants": constants.model_dump(mode="json"),
        "limits": limits.model_dump(mode="json"),
        "exact_source_locks": [lock.model_dump(mode="json") for lock in EXACT_SOURCE_LOCKS],
        "artifact_schema": "cptac-gbm-transcript-protein-discordance-artifact/1.0.0",
        "redistribution_status": "local_only_terms_unverified",
        "public_http_mounted": False,
        "public_cli_mounted": True,
        "local_artifact_query_available": True,
        "runtime_behavior": "cohort_gene_query_never_patient_scoring",
        "claim_ceiling": "limited_observational_cohort_pattern",
        "patient_measurement_input_permitted": False,
        "local_trust_boundary": "same_user_local_artifact_integrity_only",
        "cross_user_authenticity": "signed_manifest_required_not_provided",
    }
    return TranscriptProteinDiscordanceProfile(
        profile_digest=profile_digest(payload),
        engine_semantic_digest=semantic_digest,
        constants=constants,
        limits=limits,
        exact_source_locks=EXACT_SOURCE_LOCKS,
    )


__all__ = [
    "EXACT_SOURCE_LOCKS",
    "EXPECTED_NUMPY_VERSION",
    "algorithm_profile",
    "engine_semantic_digest",
]
