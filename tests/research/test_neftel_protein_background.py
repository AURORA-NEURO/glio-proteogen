"""Pinned protein-background and catalog-integrity guards for Neftel inference."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

import pytest
from pydantic import ValidationError

from glio_proteogen.research.neftel_protein_programs import (
    ProteinEvidenceState,
    ProteinProgramObservation,
    ProteinProgramRequest,
)
from glio_proteogen.research.neftel_protein_programs import catalog as catalog_module
from glio_proteogen.research.neftel_protein_programs.canonical import sha256_digest

SOURCE_DIGEST = sha256_digest("neftel-protein-background-test")


def _request(symbol: str, state: ProteinEvidenceState) -> ProteinProgramRequest:
    active = state in {
        ProteinEvidenceState.OBSERVED,
        ProteinEvidenceState.LEFT_CENSORED,
    }
    observation = ProteinProgramObservation(
        observation_id="obs.background.identity",
        gene_symbol=symbol,
        state=state,
        standardized_effect=0.5 if active else None,
        standard_error=0.3 if active else None,
        quality_weight=1.0 if active else 0.0,
        provenance_digest=SOURCE_DIGEST,
    )
    return ProteinProgramRequest(
        sample_id="sample.background.identity",
        observations=(observation,),
        bootstrap_replicates=16,
        permutation_replicates=64,
        effect_scale="standardized_log2_abundance_contrast",
        effect_reference_id="reference.control",
    )


@pytest.mark.parametrize(
    "state",
    [ProteinEvidenceState.OBSERVED, ProteinEvidenceState.LEFT_CENSORED],
)
@pytest.mark.parametrize("symbol", ["NOTAREALPROTEIN1", "SOX2-OT"])
def test_active_rank_background_requires_pinned_hgnc_uniprot_identity(
    state: ProteinEvidenceState,
    symbol: str,
) -> None:
    with pytest.raises(ValidationError, match="pinned HGNC-UniProt protein background"):
        _request(symbol, state)


def test_pinned_approved_symbol_and_profile_alias_are_accepted() -> None:
    assert _request("CST3", ProteinEvidenceState.OBSERVED).observations[0].gene_symbol == "CST3"
    assert _request("WARS", ProteinEvidenceState.OBSERVED).observations[0].gene_symbol == "WARS"


def test_unverified_inactive_identifier_is_retained_but_never_rankable() -> None:
    request = _request("NOTAREALPROTEIN1", ProteinEvidenceState.UNSUPPORTED)
    assert request.observations[0].state is ProteinEvidenceState.UNSUPPORTED


@pytest.mark.parametrize(
    "mutation",
    ["alias", "eligibility", "hgnc_id", "uniprot_id", "background"],
)
def test_catalog_byte_lock_rejects_identity_tampering(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    document = copy.deepcopy(json.loads(catalog_module._resource_bytes()))
    if mutation == "alias":
        document["normalization"]["aliases"][0]["normalized_symbol"] = "FORGED"
    elif mutation == "eligibility":
        document["programs"][0]["markers"][0]["protein_eligible"] = False
    elif mutation == "hgnc_id":
        document["programs"][0]["markers"][0]["hgnc_id"] = "HGNC:0"
    elif mutation == "uniprot_id":
        document["programs"][0]["markers"][0]["uniprot_ids"] = ["P00000"]
    else:
        document["normalization"]["protein_background_symbols"][0] = "FORGED"
    encoded = json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
    with monkeypatch.context() as context:
        context.setattr(catalog_module, "_resource_bytes", lambda: encoded)
        catalog_module.marker_catalog.cache_clear()
        with pytest.raises(RuntimeError, match="artifact digest mismatch"):
            catalog_module.marker_catalog()
    catalog_module.marker_catalog.cache_clear()


def test_canonical_content_lock_is_independent_of_byte_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = copy.deepcopy(json.loads(catalog_module._resource_bytes()))
    document["normalization"]["aliases"][0]["normalized_symbol"] = "FORGED"
    encoded = json.dumps(document, indent=3, sort_keys=True).encode()
    changed_artifact_digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
    with monkeypatch.context() as context:
        context.setattr(catalog_module, "_resource_bytes", lambda: encoded)
        context.setattr(
            catalog_module,
            "EXPECTED_CATALOG_ARTIFACT_DIGEST",
            changed_artifact_digest,
        )
        catalog_module.marker_catalog.cache_clear()
        with pytest.raises(RuntimeError, match="canonical content digest mismatch"):
            catalog_module.marker_catalog()
    catalog_module.marker_catalog.cache_clear()


def test_coordinated_marker_and_background_tampering_hits_background_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = copy.deepcopy(json.loads(catalog_module._resource_bytes()))
    marker = document["programs"][0]["markers"][0]
    marker["protein_eligible"] = False
    marker["uniprot_ids"] = []
    symbol = marker["normalized_symbol"]
    document["normalization"]["protein_background_symbols"].remove(symbol)
    document["normalization"]["protein_background_count"] -= 1
    encoded = json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
    with monkeypatch.context() as context:
        context.setattr(catalog_module, "_resource_bytes", lambda: encoded)
        context.setattr(
            catalog_module,
            "EXPECTED_CATALOG_ARTIFACT_DIGEST",
            "sha256:" + hashlib.sha256(encoded).hexdigest(),
        )
        context.setattr(
            catalog_module,
            "EXPECTED_CATALOG_CONTENT_DIGEST",
            sha256_digest(document),
        )
        catalog_module.marker_catalog.cache_clear()
        with pytest.raises(RuntimeError, match="protein-background inventory mismatch"):
            catalog_module.marker_catalog()
    catalog_module.marker_catalog.cache_clear()


def _assert_inner_catalog_rejection(
    monkeypatch: pytest.MonkeyPatch,
    document: dict[str, Any],
    message: str,
    *,
    background_count: int | None = None,
    background_digest: str | None = None,
) -> None:
    """Rebind outer byte/content locks so each independent semantic lock is exercised."""

    encoded = json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
    with monkeypatch.context() as context:
        context.setattr(catalog_module, "_resource_bytes", lambda: encoded)
        context.setattr(
            catalog_module,
            "EXPECTED_CATALOG_ARTIFACT_DIGEST",
            "sha256:" + hashlib.sha256(encoded).hexdigest(),
        )
        context.setattr(
            catalog_module,
            "EXPECTED_CATALOG_CONTENT_DIGEST",
            sha256_digest(document),
        )
        if background_count is not None:
            context.setattr(
                catalog_module,
                "EXPECTED_PROTEIN_BACKGROUND_COUNT",
                background_count,
            )
        if background_digest is not None:
            context.setattr(
                catalog_module,
                "EXPECTED_PROTEIN_BACKGROUND_DIGEST",
                background_digest,
            )
        catalog_module.marker_catalog.cache_clear()
        with pytest.raises(RuntimeError, match=message):
            catalog_module.marker_catalog()
    catalog_module.marker_catalog.cache_clear()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("schema", "unsupported Neftel marker catalog schema"),
        ("source", "source provenance digest mismatch"),
        ("hgnc", "normalization provenance digest mismatch"),
        ("program_order", "marker program order mismatch"),
        ("marker_count", "marker count mismatch"),
        ("marker_rank", "marker ranks are not contiguous"),
        ("background_inventory", "protein-background inventory mismatch"),
        ("background_digest", "protein-background digest mismatch"),
        ("unsupported_inventory", "unsupported-locus inventory mismatch"),
        ("source_program", "exact Neftel source-program digest mismatch"),
    ],
)
def test_catalog_semantic_locks_fail_independently(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    message: str,
) -> None:
    document = copy.deepcopy(json.loads(catalog_module._resource_bytes()))
    if mutation == "schema":
        document["schema_version"] = "forged"
    elif mutation == "source":
        document["source"]["source_sha256"] = "sha256:" + "0" * 64
    elif mutation == "hgnc":
        document["normalization"]["authority_sha256"] = "sha256:" + "0" * 64
    elif mutation == "program_order":
        document["programs"][0], document["programs"][1] = (
            document["programs"][1],
            document["programs"][0],
        )
    elif mutation == "marker_count":
        document["programs"][0]["markers"].pop()
    elif mutation == "marker_rank":
        document["programs"][0]["markers"][0]["rank"] = 2
    elif mutation == "background_inventory":
        document["normalization"]["protein_background_count"] -= 1
    elif mutation == "background_digest":
        document["normalization"]["protein_background_digest"] = "sha256:" + "0" * 64
    elif mutation == "unsupported_inventory":
        document["normalization"]["unsupported_non_protein_loci"].pop()
    else:
        document["programs"][0]["markers"][0]["raw_symbol"] = "FORGED-SOURCE-SYMBOL"
    _assert_inner_catalog_rejection(monkeypatch, document, message)


def test_catalog_rejects_eligible_marker_missing_from_background(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = copy.deepcopy(json.loads(catalog_module._resource_bytes()))
    symbol = document["programs"][0]["markers"][0]["normalized_symbol"]
    background = document["normalization"]["protein_background_symbols"]
    background.remove(symbol)
    digest = sha256_digest(background)
    document["normalization"]["protein_background_count"] = len(background)
    document["normalization"]["protein_background_digest"] = digest
    _assert_inner_catalog_rejection(
        monkeypatch,
        document,
        "protein markers are absent",
        background_count=len(background),
        background_digest=digest,
    )


def test_catalog_rejects_non_protein_locus_in_background(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = copy.deepcopy(json.loads(catalog_module._resource_bytes()))
    background = document["normalization"]["protein_background_symbols"]
    background.append(document["normalization"]["unsupported_non_protein_loci"][0])
    background.sort()
    digest = sha256_digest(background)
    document["normalization"]["protein_background_count"] = len(background)
    document["normalization"]["protein_background_digest"] = digest
    _assert_inner_catalog_rejection(
        monkeypatch,
        document,
        "non-protein loci entered",
        background_count=len(background),
        background_digest=digest,
    )
