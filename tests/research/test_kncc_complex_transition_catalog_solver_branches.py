"""Fail-closed branch tests for the fitted complex catalog and coordinate solver."""

from __future__ import annotations

import base64
import copy
import json
import zlib
from typing import TYPE_CHECKING

import numpy as np
import pytest

from glio_proteogen.research.longitudinal_gbm_complex_transition import fitted_catalog
from glio_proteogen.research.longitudinal_gbm_complex_transition import solver as solver_module
from glio_proteogen.research.longitudinal_gbm_complex_transition.errors import (
    ComplexTransitionInferenceError,
    ComplexTransitionModelIntegrityError,
)
from glio_proteogen.research.longitudinal_gbm_complex_transition.solver import (
    MemberEvidence,
    solve_member_coordinate,
)
from glio_proteogen.research.longitudinal_gbm_complex_transition.source_catalog import (
    complex_transition_source_catalog,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


_BOOLEAN_TRUE: object = True


@pytest.fixture(autouse=True)
def _clear_fitted_catalog_cache() -> Iterator[None]:
    fitted_catalog.complex_transition_fitted_catalog.cache_clear()
    yield
    fitted_catalog.complex_transition_fitted_catalog.cache_clear()


def _document() -> dict[str, object]:
    return fitted_catalog._object(
        json.loads(fitted_catalog._resource_bytes()),
        "root",
    )


def _object(parent: dict[str, object], key: str) -> dict[str, object]:
    return fitted_catalog._object(parent[key], key)


def _array(parent: dict[str, object], key: str) -> list[object]:
    return fitted_catalog._array(parent[key], key)


def _retag_and_lock(
    monkeypatch: pytest.MonkeyPatch,
    document: dict[str, object],
) -> bytes:
    content = dict(document)
    content.pop("artifact_digest", None)
    digest = fitted_catalog._digest(content)
    document["artifact_digest"] = digest
    payload = fitted_catalog._canonical_bytes(document)
    monkeypatch.setattr(fitted_catalog, "EXPECTED_CONTENT_DIGEST", digest)
    monkeypatch.setattr(fitted_catalog, "EXPECTED_ARTIFACT_BYTES", len(payload))
    monkeypatch.setattr(
        fitted_catalog,
        "EXPECTED_ARTIFACT_SHA256",
        fitted_catalog._raw_digest(payload),
    )
    monkeypatch.setattr(fitted_catalog, "_resource_bytes", lambda: payload)
    return payload


def _lock_raw_payload(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> None:
    monkeypatch.setattr(fitted_catalog, "EXPECTED_ARTIFACT_BYTES", len(payload))
    monkeypatch.setattr(
        fitted_catalog,
        "EXPECTED_ARTIFACT_SHA256",
        fitted_catalog._raw_digest(payload),
    )
    monkeypatch.setattr(fitted_catalog, "_resource_bytes", lambda: payload)


@pytest.mark.parametrize(
    ("operation", "match"),
    [
        (lambda: fitted_catalog._object(None, "field"), "must be an object"),
        (lambda: fitted_catalog._array(None, "field"), "must be an array"),
        (lambda: fitted_catalog._string(1, "field"), "must be a string"),
        (lambda: fitted_catalog._integer(_BOOLEAN_TRUE, "field"), "must be an integer"),
        (lambda: fitted_catalog._number("1", "field"), "must be numeric"),
        (lambda: fitted_catalog._number(float("nan"), "field"), "must be finite"),
        (lambda: fitted_catalog._bool(1, "field"), "must be boolean"),
        (lambda: fitted_catalog._float_array([1.0], "field", 2), "wrong length"),
        (lambda: fitted_catalog._int_array([1], "field", 2), "wrong length"),
    ],
)
def test_scalar_and_array_decoders_reject_wrong_domains(
    operation: object,
    match: str,
) -> None:
    callable_operation = operation
    assert callable(callable_operation)
    with pytest.raises(ComplexTransitionModelIntegrityError, match=match):
        callable_operation()


def test_boolean_decoder_accepts_only_an_actual_boolean() -> None:
    assert fitted_catalog._bool(_BOOLEAN_TRUE, "field") is True


def test_duplicate_json_keys_are_rejected() -> None:
    with pytest.raises(ComplexTransitionModelIntegrityError, match="duplicate JSON key"):
        fitted_catalog._reject_duplicates([("same", 1), ("same", 2)])


def test_float_array_defensively_rejects_nonfinite_converted_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fitted_catalog, "_number", lambda value, name: float("nan"))
    with pytest.raises(ComplexTransitionModelIntegrityError, match="non-finite values"):
        fitted_catalog._float_array([1.0], "field", 1)


def _tensor(
    values: np.ndarray[tuple[int, int], np.dtype[np.float32]],
    *,
    raw_bytes: int | None = None,
) -> dict[str, object]:
    payload = np.ascontiguousarray(values, dtype="<f4").tobytes()
    return {
        "data": base64.b64encode(zlib.compress(payload)).decode("ascii"),
        "dtype": "<f4",
        "encoding": "base64+zlib",
        "raw_bytes": len(payload) if raw_bytes is None else raw_bytes,
        "raw_sha256": fitted_catalog._raw_digest(payload),
        "shape": list(values.shape),
    }


def test_tensor_decoder_rejects_metadata_decode_payload_and_nonfinite_errors() -> None:
    with pytest.raises(ComplexTransitionModelIntegrityError, match="metadata mismatch"):
        fitted_catalog._decode_tensor(
            {"dtype": "wrong", "encoding": "base64+zlib", "shape": [1, 1]},
            "tensor",
            (1, 1),
        )

    undecodable = {
        "data": "!",
        "dtype": "<f4",
        "encoding": "base64+zlib",
        "raw_bytes": 4,
        "raw_sha256": "sha256:unused",
        "shape": [1, 1],
    }
    with pytest.raises(ComplexTransitionModelIntegrityError, match="cannot be decoded"):
        fitted_catalog._decode_tensor(undecodable, "tensor", (1, 1))

    with pytest.raises(ComplexTransitionModelIntegrityError, match="payload mismatch"):
        fitted_catalog._decode_tensor(
            _tensor(np.asarray([[1.0]], dtype=np.float32), raw_bytes=8),
            "tensor",
            (1, 1),
        )

    with pytest.raises(ComplexTransitionModelIntegrityError, match="non-finite values"):
        fitted_catalog._decode_tensor(
            _tensor(np.asarray([[np.nan]], dtype=np.float32)),
            "tensor",
            (1, 1),
        )


def test_complex_parser_rejects_count_identity_reference_ablation_and_slot_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = complex_transition_source_catalog()
    document = _document()
    raw_complexes = _array(document, "complexes")

    with pytest.raises(ComplexTransitionModelIntegrityError, match="count mismatch"):
        fitted_catalog._parse_complexes([], source)

    wrong_identity = copy.deepcopy(raw_complexes)
    fitted_catalog._object(wrong_identity[0], "complex")["complex_index"] = -1
    with pytest.raises(ComplexTransitionModelIntegrityError, match="identity, membership"):
        fitted_catalog._parse_complexes(wrong_identity, source)

    wrong_reference = copy.deepcopy(raw_complexes)
    first_reference = _object(fitted_catalog._object(wrong_reference[0], "complex"), "reference")
    first_scales = _array(first_reference, "member_scales")
    first_scales[0] = 0.0
    with pytest.raises(ComplexTransitionModelIntegrityError, match="reference numerical"):
        fitted_catalog._parse_complexes(wrong_reference, source)

    wrong_ablation = copy.deepcopy(raw_complexes)
    first_ablation = _object(
        fitted_catalog._object(wrong_ablation[0], "complex"),
        "source_processing_ablation",
    )
    first_ablation["measure"] = "not-log"
    with pytest.raises(ComplexTransitionModelIntegrityError, match="ablation mismatch"):
        fitted_catalog._parse_complexes(wrong_ablation, source)

    monkeypatch.setattr(
        fitted_catalog,
        "EXPECTED_MEMBER_SLOTS",
        fitted_catalog.EXPECTED_MEMBER_SLOTS + 1,
    )
    with pytest.raises(ComplexTransitionModelIntegrityError, match="member-slot total"):
        fitted_catalog._parse_complexes(raw_complexes, source)


def test_binding_validator_rejects_a_forged_source_binding() -> None:
    source = complex_transition_source_catalog()
    document = _document()
    _object(document, "source_catalog_binding")["profile_id"] = "forged"

    with pytest.raises(ComplexTransitionModelIntegrityError, match="digest binding mismatch"):
        fitted_catalog._validate_bindings_and_digests(document, source)


def test_bootstrap_validator_rejects_domain_row_norm_and_ensemble_mismatches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = fitted_catalog.complex_transition_fitted_catalog()
    document = _document()

    wrong_domain = copy.deepcopy(document)
    _object(wrong_domain, "bootstrap")["replicates"] = 0
    with pytest.raises(ComplexTransitionModelIntegrityError, match="bootstrap domain"):
        fitted_catalog._validate_bootstrap(wrong_domain, loaded.complexes)

    wrong_seed_namespace = copy.deepcopy(document)
    _object(wrong_seed_namespace, "bootstrap")["seed_namespace_digest"] = "sha256:forged"
    with pytest.raises(ComplexTransitionModelIntegrityError, match="bootstrap domain"):
        fitted_catalog._validate_bootstrap(wrong_seed_namespace, loaded.complexes)

    wrong_row = copy.deepcopy(document)
    _array(_object(wrong_row, "bootstrap"), "row_digests")[0] = "sha256:forged"
    with pytest.raises(ComplexTransitionModelIntegrityError, match="row digest"):
        fitted_catalog._validate_bootstrap(wrong_row, loaded.complexes)

    wrong_norm = copy.deepcopy(document)
    wrong_loadings = loaded.bootstrap_member_loadings.copy()
    first = loaded.complexes[0]
    stop = first.member_slot_offset + first.member_slot_count
    wrong_loadings[0, first.member_slot_offset : stop] = np.float32(0.0)
    scales = loaded.bootstrap_member_scales
    first_payload = np.ascontiguousarray(
        np.concatenate((scales[0], wrong_loadings[0])),
        dtype="<f4",
    ).tobytes()
    _array(_object(wrong_norm, "bootstrap"), "row_digests")[0] = fitted_catalog._raw_digest(
        first_payload
    )

    def decoded_tensor(
        value: object,
        name: str,
        expected_shape: tuple[int, int],
    ) -> fitted_catalog.Float32Array:
        del value, expected_shape
        return scales if name.endswith("member_scale") else wrong_loadings

    monkeypatch.setattr(fitted_catalog, "_decode_tensor", decoded_tensor)
    with pytest.raises(ComplexTransitionModelIntegrityError, match="loading norm"):
        fitted_catalog._validate_bootstrap(wrong_norm, loaded.complexes)

    monkeypatch.undo()
    changed_ensemble = copy.deepcopy(document)
    _object(_object(changed_ensemble, "bootstrap"), "tensors")["extra"] = "bound"
    with pytest.raises(ComplexTransitionModelIntegrityError, match="ensemble digest"):
        fitted_catalog._validate_bootstrap(changed_ensemble, loaded.complexes)


def test_top_level_loader_rejects_non_json_and_content_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"not-json"
    _lock_raw_payload(monkeypatch, payload)
    with pytest.raises(ComplexTransitionModelIntegrityError, match="not strict UTF-8 JSON"):
        fitted_catalog.complex_transition_fitted_catalog()

    fitted_catalog.complex_transition_fitted_catalog.cache_clear()
    monkeypatch.undo()
    document = _document()
    document["artifact_digest"] = "sha256:forged"
    forged = fitted_catalog._canonical_bytes(document)
    _lock_raw_payload(monkeypatch, forged)
    with pytest.raises(ComplexTransitionModelIntegrityError, match="content digest"):
        fitted_catalog.complex_transition_fitted_catalog()


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("identity", "identity mismatch"),
        ("counts", "count mismatch"),
        ("union", "union feature axis"),
        ("reference", "reference or ablation digest"),
        ("provenance", "provenance, privacy, or claim boundary"),
        ("limitations", "must expose limitations"),
    ],
)
def test_top_level_loader_rejects_semantically_forged_documents(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    match: str,
) -> None:
    document = _document()
    if mutation == "identity":
        document["model_id"] = "forged"
    elif mutation == "counts":
        _object(document, "counts")["complexes"] = 0
    elif mutation == "union":
        union = _array(document, "union_feature_indices")
        union[0] = union[1]
    elif mutation == "reference":
        complexes = _array(document, "complexes")
        reference = _object(fitted_catalog._object(complexes[0], "complex"), "reference")
        centers = _array(reference, "member_centers")
        centers[0] = fitted_catalog._number(centers[0], "center") + 0.01
    elif mutation == "provenance":
        _object(document, "provenance")["study_id"] = "forged"
    else:
        document["limitations"] = []

    _retag_and_lock(monkeypatch, document)
    with pytest.raises(ComplexTransitionModelIntegrityError, match=match):
        fitted_catalog.complex_transition_fitted_catalog()


def _evidence(
    *items: tuple[int, float, str, float],
) -> tuple[MemberEvidence, ...]:
    return tuple(
        MemberEvidence(position, value, semantics, weight)  # type: ignore[arg-type]
        for position, value, semantics, weight in items
    )


def test_solver_exercises_upper_bound_and_exhausted_iteration_diagnostics() -> None:
    result = solve_member_coordinate(
        np.asarray([1.0, 1.0], dtype=np.float64),
        _evidence((0, 0.2, "exact_delta", 1.0), (1, -1.0, "upper_bound", 1.0)),
        max_iterations=1,
        tolerance=1.0e-30,
    )

    assert result.diagnostics.upper_bound_count == 1
    assert not result.diagnostics.converged
    assert result.diagnostics.iterations == 1


@pytest.mark.parametrize(
    ("evidence", "match"),
    [
        (
            _evidence((0, 0.1, "exact_delta", 1.0), (0, 0.2, "exact_delta", 1.0)),
            "positions are duplicated",
        ),
        (_evidence((1, 0.1, "exact_delta", 1.0)), "position is out of range"),
        (_evidence((0, 0.1, "invalid", 1.0)), "unsupported member evidence semantics"),
    ],
)
def test_solver_rejects_duplicate_out_of_range_and_unknown_semantics(
    evidence: tuple[MemberEvidence, ...],
    match: str,
) -> None:
    with pytest.raises(ComplexTransitionInferenceError, match=match):
        solve_member_coordinate(np.asarray([1.0], dtype=np.float64), evidence)


def test_solver_rejects_overflowed_information_and_update() -> None:
    with np.errstate(over="ignore", invalid="ignore"):
        with pytest.raises(
            ComplexTransitionInferenceError,
            match="insufficient finite information",
        ):
            solve_member_coordinate(
                np.asarray([1.0e308], dtype=np.float64),
                _evidence((0, 1.0, "exact_delta", 1.0)),
            )

        with pytest.raises(ComplexTransitionInferenceError, match="non-finite update"):
            solve_member_coordinate(
                np.asarray([1.0e-154], dtype=np.float64),
                _evidence((0, 1.0e308, "exact_delta", 1.0e308)),
                huber_k=1.0e308,
            )


def test_solver_defensive_backtracking_can_reject_every_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def hostile_objective(*args: object, **kwargs: object) -> float:
        nonlocal calls
        del args, kwargs
        calls += 1
        return 0.0 if calls == 1 else 1.0

    monkeypatch.setattr(solver_module, "_objective", hostile_objective)
    result = solve_member_coordinate(
        np.asarray([1.0], dtype=np.float64),
        _evidence((0, 0.5, "exact_delta", 1.0)),
        max_iterations=1,
    )

    assert result.coordinate == 0.0
    assert result.diagnostics.backtracking_step_count == 24
    assert result.diagnostics.objective_monotone
