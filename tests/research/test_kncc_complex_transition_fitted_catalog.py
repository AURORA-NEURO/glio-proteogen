"""Integrity and immutability checks for the aggregate fitted model artifact."""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from glio_proteogen.research.longitudinal_gbm_complex_transition import fitted_catalog
from glio_proteogen.research.longitudinal_gbm_complex_transition.errors import (
    ComplexTransitionModelIntegrityError,
)


def test_fitted_catalog_is_locked_aggregate_only_and_read_only() -> None:
    loaded = fitted_catalog.complex_transition_fitted_catalog()

    assert loaded.artifact_bytes == fitted_catalog.EXPECTED_ARTIFACT_BYTES
    assert loaded.artifact_byte_digest == fitted_catalog.EXPECTED_ARTIFACT_SHA256
    assert loaded.content_digest == fitted_catalog.EXPECTED_CONTENT_DIGEST
    assert loaded.bootstrap_seed_namespace_digest == (
        fitted_catalog.EXPECTED_BOOTSTRAP_SEED_NAMESPACE_DIGEST
    )
    assert loaded.bootstrap_replicate_count == 128
    assert loaded.member_slot_count == 146
    assert len(loaded.complexes) == 28
    assert len(loaded.union_gene_symbols) == 120
    assert not loaded.bootstrap_member_scales.flags.writeable
    assert not loaded.bootstrap_member_loadings.flags.writeable
    assert all(not item.member_loadings.flags.writeable for item in loaded.complexes)
    with pytest.raises(ValueError, match="read-only"):
        loaded.bootstrap_member_scales[0, 0] = np.float32(1.0)


def test_bootstrap_complex_slice_is_bounded_normalized_and_read_only() -> None:
    loaded = fitted_catalog.complex_transition_fitted_catalog()
    model = loaded.complexes[7]
    scales, loadings = loaded.bootstrap_complex_parameters(17, model.complex_index)

    assert scales.shape == loadings.shape == (model.member_slot_count,)
    assert np.all(np.isfinite(scales))
    assert np.all(scales > 0.0)
    assert np.linalg.norm(loadings) == pytest.approx(1.0, abs=2e-6)
    assert not scales.flags.writeable
    assert not loadings.flags.writeable
    with pytest.raises(IndexError, match="draw index"):
        loaded.bootstrap_draw(loaded.bootstrap_replicate_count)
    with pytest.raises(IndexError, match="complex index"):
        loaded.bootstrap_complex_parameters(0, len(loaded.complexes))


def test_fitted_artifact_byte_tampering_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = fitted_catalog._resource_bytes()
    marker = b"kncc-reactome-complex-transition-factor-model"
    assert marker in payload
    tampered = payload.replace(marker, b"xncc-reactome-complex-transition-factor-model", 1)
    assert len(tampered) == len(payload)
    assert "sha256:" + hashlib.sha256(tampered).hexdigest() != (
        fitted_catalog.EXPECTED_ARTIFACT_SHA256
    )

    fitted_catalog.complex_transition_fitted_catalog.cache_clear()
    monkeypatch.setattr(fitted_catalog, "_resource_bytes", lambda: tampered)
    with pytest.raises(ComplexTransitionModelIntegrityError, match="byte lock"):
        fitted_catalog.complex_transition_fitted_catalog()
    fitted_catalog.complex_transition_fitted_catalog.cache_clear()
