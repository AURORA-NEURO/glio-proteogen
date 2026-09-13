from __future__ import annotations

import json
import math
from dataclasses import replace
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import numpy as np
import pytest
from pydantic import ValidationError

from glio_proteogen.research.longitudinal_gbm.contracts import (
    LongitudinalTimePoint,
    ProteinEvidenceState,
    ProteinObservation,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition import engine
from glio_proteogen.research.longitudinal_gbm_reactome_transition import (
    fitted_catalog as fitted,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.catalog import (
    reactome_transition_source_catalog,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.contracts import (
    AnalysisSupport,
    ConditionalPathwayAblations,
    ConditionalTransitionClassification,
    GlobalRecurrenceClassification,
    GlobalRecurrenceConcordance,
    LongitudinalGbmReactomeTransitionRequest,
    ReactomePathwayConcordance,
    ReactomePathwayProfile,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.demo import (
    synthetic_demo_request,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.errors import (
    ReactomeConditionalInferenceError,
    ReactomeConditionalModelIntegrityError,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.profile import (
    algorithm_profile,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.solver import (
    BoundSemantics,
    ConditionalSolverDiagnostics,
    ConditionalSolveResult,
    SolverEvidence,
    solve_conditional_coordinates,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


_OVERLAP_PAIR_ASSERTION = "demo requires pairwise overlap with retained support"
_FORCED_OVERLAP_FAILURE = "forced overlap failure"
_RUNTIME_DESIGN_DIGEST_ASSERTION = "runtime-derived reference design must not be raw-digested"


@pytest.fixture(autouse=True)
def _clear_fitted_cache() -> Iterator[None]:
    fitted.reactome_conditional_fitted_catalog.cache_clear()
    yield
    fitted.reactome_conditional_fitted_catalog.cache_clear()


def _invalid_result(*, condition: float = math.inf) -> ConditionalSolveResult:
    return ConditionalSolveResult(
        coordinates=(0.0,),
        diagnostics=ConditionalSolverDiagnostics(
            converged=False,
            iterations=1,
            final_max_coordinate_change=1.0,
            initial_objective=1.0,
            final_objective=1.0,
            objective_trace=(1.0,),
            objective_monotone=False,
            active_evidence_count=1,
            exact_evidence_count=1,
            upper_bound_count=0,
            lower_bound_count=0,
            design_condition_number=condition,
        ),
    )


def _valid_result(
    coordinate_count: int,
    *,
    coordinate: float = 0.1,
) -> ConditionalSolveResult:
    return ConditionalSolveResult(
        coordinates=tuple(coordinate for _ in range(coordinate_count)),
        diagnostics=ConditionalSolverDiagnostics(
            converged=True,
            iterations=2,
            final_max_coordinate_change=0.0,
            initial_objective=1.0,
            final_objective=0.5,
            objective_trace=(1.0, 0.5),
            objective_monotone=True,
            active_evidence_count=32,
            exact_evidence_count=32,
            upper_bound_count=0,
            lower_bound_count=0,
            design_condition_number=2.0,
        ),
    )


@pytest.mark.parametrize(
    ("design", "evidence", "message"),
    [
        (np.empty((0, 1)), (SolverEvidence(0, 0.0, "exact_delta", 1.0),), "non-empty"),
        (np.asarray([[math.nan]]), (SolverEvidence(0, 0.0, "exact_delta", 1.0),), "non-finite"),
        (np.ones((1, 1)), (), "active evidence"),
        (
            np.ones((1, 1)),
            (
                SolverEvidence(0, 0.0, "exact_delta", 1.0),
                SolverEvidence(0, 0.1, "exact_delta", 1.0),
            ),
            "duplicated",
        ),
        (np.ones((1, 1)), (SolverEvidence(1, 0.0, "exact_delta", 1.0),), "out of range"),
        (np.ones((1, 1)), (SolverEvidence(0, math.inf, "exact_delta", 1.0),), "finite"),
        (np.ones((1, 1)), (SolverEvidence(0, 0.0, "exact_delta", 0.0),), "positive"),
        (
            np.ones((1, 1)),
            (SolverEvidence(0, 0.0, cast("BoundSemantics", "invalid"), 1.0),),
            "unsupported",
        ),
    ],
)
def test_solver_rejects_invalid_inputs(
    design: np.ndarray[tuple[int, ...], np.dtype[np.float64]],
    evidence: tuple[SolverEvidence, ...],
    message: str,
) -> None:
    with pytest.raises(ReactomeConditionalInferenceError, match=message):
        solve_conditional_coordinates(design, evidence)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"huber_k": 0.0},
        {"ridge_lambda": 0.0},
        {"global_ridge_multiplier": 0.0},
        {"damping": 0.0},
        {"damping": 1.1},
        {"max_iterations": 0},
        {"tolerance": 0.0},
    ],
)
def test_solver_rejects_invalid_constants(kwargs: dict[str, float | int]) -> None:
    with pytest.raises(ReactomeConditionalInferenceError, match="outside their domain"):
        solve_conditional_coordinates(
            np.ones((1, 1), dtype=np.float64),
            (SolverEvidence(0, 0.0, "exact_delta", 1.0),),
            **kwargs,  # type: ignore[arg-type]
        )


def test_solver_reports_nonconvergence_and_infinite_condition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = solve_conditional_coordinates(
        np.eye(2, dtype=np.float64),
        (
            SolverEvidence(0, 2.0, "exact_delta", 1.0),
            SolverEvidence(1, -2.0, "exact_delta", 1.0),
        ),
        max_iterations=1,
        tolerance=1e-30,
    )
    assert not result.diagnostics.converged
    assert result.diagnostics.iterations == 1
    with monkeypatch.context() as condition_patch:
        condition_patch.setattr(np.linalg, "cond", lambda *_: 5.961777047638983e16)
        collinear = solve_conditional_coordinates(
            np.ones((2, 2), dtype=np.float64),
            (
                SolverEvidence(0, 1.0, "exact_delta", 1.0),
                SolverEvidence(1, 1.0, "exact_delta", 1.0),
            ),
        )
    assert math.isinf(collinear.diagnostics.design_condition_number)


def test_solver_wraps_singular_and_nonfinite_linear_updates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    design = np.ones((1, 1), dtype=np.float64)
    evidence = (SolverEvidence(0, 1.0, "exact_delta", 1.0),)
    monkeypatch.setattr(
        np.linalg,
        "solve",
        lambda *_: (_ for _ in ()).throw(np.linalg.LinAlgError()),
    )
    with pytest.raises(ReactomeConditionalInferenceError, match="singular"):
        solve_conditional_coordinates(design, evidence)
    monkeypatch.setattr(
        np.linalg,
        "solve",
        lambda *_: np.asarray([math.inf]),
    )
    with pytest.raises(ReactomeConditionalInferenceError, match="non-finite"):
        solve_conditional_coordinates(design, evidence)


def test_solver_honors_cancellation() -> None:
    context = CancellationContext()
    context.cancel()
    with pytest.raises(InferenceCancelledError):
        solve_conditional_coordinates(
            np.ones((1, 1), dtype=np.float64),
            (SolverEvidence(0, 1.0, "exact_delta", 1.0),),
            cancellation=context,
        )


def test_fitted_catalog_rejects_byte_length_digest_and_canonical_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = fitted._resource_bytes()
    monkeypatch.setattr(fitted, "_resource_bytes", lambda: b"")
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="byte length"):
        fitted.reactome_conditional_fitted_catalog()

    fitted.reactome_conditional_fitted_catalog.cache_clear()
    corrupted = bytearray(original)
    corrupted[-2] ^= 1
    monkeypatch.setattr(fitted, "_resource_bytes", lambda: bytes(corrupted))
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="byte digest"):
        fitted.reactome_conditional_fitted_catalog()

    fitted.reactome_conditional_fitted_catalog.cache_clear()
    pretty = json.dumps(json.loads(original), indent=2).encode()
    monkeypatch.setattr(fitted, "_resource_bytes", lambda: pretty)
    monkeypatch.setattr(fitted, "EXPECTED_ARTIFACT_BYTES", len(pretty))
    monkeypatch.setattr(fitted, "EXPECTED_ARTIFACT_SHA256", fitted._raw_digest(pretty))
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="canonical JSON"):
        fitted.reactome_conditional_fitted_catalog()


def _install_locked_payload(
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    content_digest: str,
) -> None:
    monkeypatch.setattr(fitted, "_resource_bytes", lambda: payload)
    monkeypatch.setattr(fitted, "EXPECTED_ARTIFACT_BYTES", len(payload))
    monkeypatch.setattr(fitted, "EXPECTED_ARTIFACT_SHA256", fitted._raw_digest(payload))
    monkeypatch.setattr(fitted, "EXPECTED_CONTENT_DIGEST", content_digest)


def _artifact_document() -> dict[str, object]:
    return cast("dict[str, object]", json.loads(fitted._resource_bytes()))


def _install_document(
    monkeypatch: pytest.MonkeyPatch,
    document: dict[str, object],
) -> None:
    content = dict(document)
    content.pop("artifact_digest", None)
    content_digest = fitted._digest(content)
    document["artifact_digest"] = content_digest
    _install_locked_payload(
        monkeypatch,
        fitted._canonical_bytes(document),
        content_digest,
    )


def _restore_payload(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> None:
    document = cast("dict[str, object]", json.loads(payload))
    content = dict(document)
    content.pop("artifact_digest")
    _install_locked_payload(monkeypatch, payload, fitted._digest(content))


def test_fitted_catalog_rejects_invalid_json_and_non_object_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    malformed = b"{\n"
    _install_locked_payload(
        monkeypatch,
        malformed,
        fitted.EXPECTED_CONTENT_DIGEST,
    )
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="valid JSON"):
        fitted.reactome_conditional_fitted_catalog()

    fitted.reactome_conditional_fitted_catalog.cache_clear()
    array_root = b"[]\n"
    _install_locked_payload(
        monkeypatch,
        array_root,
        fitted.EXPECTED_CONTENT_DIGEST,
    )
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="root must be"):
        fitted.reactome_conditional_fitted_catalog()


def test_fitted_scalar_shape_and_number_guards() -> None:
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="must be an object"):
        fitted._object([], "bad")
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="must be an array"):
        fitted._array({}, "bad")
    boolean_value: object = True
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="must be an integer"):
        fitted._integer(boolean_value, "bad")
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="must be numeric"):
        fitted._finite("1", "bad")
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="must be finite"):
        fitted._finite(math.inf, "bad")


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("recipe", "training recipe"),
        ("counts", "count inventory"),
        ("union", "union feature axis"),
        ("privacy", "privacy declaration"),
        ("limitations", "limitation inventory"),
        ("numpy", "NumPy version"),
    ],
)
def test_fitted_catalog_rejects_locked_domain_mutations(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    message: str,
) -> None:
    document = _artifact_document()
    if case == "recipe":
        recipe = cast("dict[str, object]", document["training_recipe"])
        recipe["solver_max_iterations"] = 199
    elif case == "counts":
        counts = cast("dict[str, object]", document["counts"])
        counts["source_patient_pairs"] = 103
    elif case == "union":
        union = cast("list[object]", document["union_feature_indices"])
        union[0] = cast("int", union[1])
    elif case == "privacy":
        privacy = cast("dict[str, object]", document["privacy"])
        privacy[next(iter(privacy))] = True
    elif case == "limitations":
        document["limitations"] = ["too short"]
    else:
        provenance = cast("dict[str, object]", document["provenance"])
        provenance["numpy_version"] = "0.0.0"
    _install_document(monkeypatch, document)
    with pytest.raises(ReactomeConditionalModelIntegrityError, match=message):
        fitted.reactome_conditional_fitted_catalog()


def test_fitted_catalog_rejects_impossible_membership_degree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reactome_transition_source_catalog()
    original_any = np.any

    def forced_degree_failure(value: object) -> bool:
        array = np.asarray(value)
        if array.dtype == np.dtype(np.bool_) and array.shape == (
            fitted.EXPECTED_UNION_FEATURE_COUNT,
        ):
            return True
        return bool(original_any(np.asarray(value)))

    monkeypatch.setattr(np, "any", forced_degree_failure)
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="membership degree"):
        fitted.reactome_conditional_fitted_catalog()


def test_fitted_catalog_rejects_reference_tensor_domain_and_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_decode = fitted._decode_tensor

    def invalid_reference_scale(
        value: object,
        name: str,
        *,
        expected_dtype: str,
        expected_shape: tuple[int, ...],
    ) -> np.ndarray[tuple[int, ...], np.dtype[np.generic]]:
        result = original_decode(
            value,
            name,
            expected_dtype=expected_dtype,
            expected_shape=expected_shape,
        )
        if name == "reference scale":
            mutable = np.array(result, copy=True)
            mutable[0] = 0.0
            return mutable
        return result

    monkeypatch.setattr(fitted, "_decode_tensor", invalid_reference_scale)
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="tensor domain"):
        fitted.reactome_conditional_fitted_catalog()

    fitted.reactome_conditional_fitted_catalog.cache_clear()
    monkeypatch.setattr(fitted, "_decode_tensor", original_decode)
    document = _artifact_document()
    reference = cast("dict[str, object]", document["reference_fit"])
    tensors = cast("dict[str, object]", reference["tensors"])
    tensors["unbound_extra"] = True
    _install_document(monkeypatch, document)
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="tensor digest"):
        fitted.reactome_conditional_fitted_catalog()


def test_fitted_catalog_rejects_centering_and_design_recomputation_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_digest = fitted._digest

    def mismatched_centering(value: object) -> str:
        if type(value) is dict and set(cast("dict[str, object]", value)) == {
            "scale",
            "support",
            "eligible",
        }:
            return "sha256:" + "0" * 64
        return original_digest(value)

    monkeypatch.setattr(fitted, "_digest", mismatched_centering)
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="centering/scaling"):
        fitted.reactome_conditional_fitted_catalog()

    fitted.reactome_conditional_fitted_catalog.cache_clear()
    monkeypatch.setattr(fitted, "_digest", original_digest)
    reactome_transition_source_catalog()
    original_condition = np.linalg.cond
    monkeypatch.setattr(
        np.linalg,
        "cond",
        lambda value: float(original_condition(value)) + 1.0,
    )
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="loading condition"):
        fitted.reactome_conditional_fitted_catalog()


def test_fitted_catalog_accepts_portable_reference_loading_roundoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = fitted.reactome_conditional_fitted_catalog()
    fitted.reactome_conditional_fitted_catalog.cache_clear()
    original_derive = fitted._derive_design
    original_raw_digest = fitted._raw_digest
    original_condition = np.linalg.cond
    reference_design_bytes = baseline.reference_design.nbytes
    invocation_count = 0

    def one_ulp_reference_design(
        effect: fitted.FloatArray,
        eligible: fitted.BoolArray,
        members: tuple[tuple[int, ...], ...],
        degree: fitted.FloatArray,
        *,
        use_degree: bool = True,
    ) -> tuple[fitted.FloatArray, tuple[fitted.DesignDecomposition, ...]]:
        nonlocal invocation_count
        design, decompositions = original_derive(
            effect,
            eligible,
            members,
            degree,
            use_degree=use_degree,
        )
        if invocation_count == 0:
            design = np.array(design, copy=True)
            index = np.unravel_index(np.argmax(np.abs(design)), design.shape)
            design[index] = np.nextafter(design[index], math.inf)
        invocation_count += 1
        return design, decompositions

    def forbid_runtime_design_digest(value: bytes) -> str:
        if len(value) == reference_design_bytes:
            raise AssertionError(_RUNTIME_DESIGN_DIGEST_ASSERTION)
        return original_raw_digest(value)

    monkeypatch.setattr(fitted, "_derive_design", one_ulp_reference_design)
    monkeypatch.setattr(fitted, "_raw_digest", forbid_runtime_design_digest)
    monkeypatch.setattr(
        np.linalg,
        "cond",
        lambda value: float(original_condition(value)) + 2.0e-10,
    )
    varied = fitted.reactome_conditional_fitted_catalog()

    assert varied.reference_design_digest == fitted.EXPECTED_REFERENCE_DESIGN_DIGEST
    assert not np.array_equal(varied.reference_design, baseline.reference_design)


@pytest.mark.parametrize(
    ("target", "message"),
    [
        ("design", "loading semantic"),
        ("decomposition", "loading decomposition"),
        ("decomposition count", "loading decomposition"),
    ],
)
def test_fitted_catalog_rejects_material_reference_loading_changes(
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    message: str,
) -> None:
    original_derive = fitted._derive_design
    invocation_count = 0

    def corrupt_reference_design(
        effect: fitted.FloatArray,
        eligible: fitted.BoolArray,
        members: tuple[tuple[int, ...], ...],
        degree: fitted.FloatArray,
        *,
        use_degree: bool = True,
    ) -> tuple[fitted.FloatArray, tuple[fitted.DesignDecomposition, ...]]:
        nonlocal invocation_count
        design, decompositions = original_derive(
            effect,
            eligible,
            members,
            degree,
            use_degree=use_degree,
        )
        if invocation_count == 0:
            if target == "design":
                design = np.array(design, copy=True)
                design[0, 0] += 1.0e-6
            elif target == "decomposition":
                first = decompositions[0]
                corrupted = np.array(first[0], copy=True)
                corrupted[0] += 1.0e-6
                decompositions = ((corrupted, *first[1:]), *decompositions[1:])
            else:
                decompositions = decompositions[:-1]
        invocation_count += 1
        return design, decompositions

    monkeypatch.setattr(fitted, "_derive_design", corrupt_reference_design)
    with pytest.raises(
        ReactomeConditionalModelIntegrityError,
        match=message,
    ):
        fitted.reactome_conditional_fitted_catalog()


def test_fitted_catalog_rejects_unbound_reference_design_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _artifact_document()
    reference = cast("dict[str, object]", document["reference_fit"])
    reference["design_raw_sha256"] = "sha256:" + "0" * 64
    _install_document(monkeypatch, document)

    with pytest.raises(
        ReactomeConditionalModelIntegrityError,
        match="loading provenance digest",
    ):
        fitted.reactome_conditional_fitted_catalog()


def test_fitted_catalog_rejects_source_processing_and_bootstrap_locks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_payload = fitted._resource_bytes()
    document = _artifact_document()
    processing = cast("dict[str, object]", document["source_processing_ablation"])
    effect = cast("dict[str, object]", processing["effect"])
    effect["unbound_extra"] = True
    _install_document(monkeypatch, document)
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="source-processing"):
        fitted.reactome_conditional_fitted_catalog()

    fitted.reactome_conditional_fitted_catalog.cache_clear()
    _restore_payload(monkeypatch, original_payload)
    original_decode = fitted._decode_tensor

    def invalid_bootstrap_scale(
        value: object,
        name: str,
        *,
        expected_dtype: str,
        expected_shape: tuple[int, ...],
    ) -> np.ndarray[tuple[int, ...], np.dtype[np.generic]]:
        result = original_decode(
            value,
            name,
            expected_dtype=expected_dtype,
            expected_shape=expected_shape,
        )
        if name == "bootstrap scale":
            mutable = np.array(result, copy=True)
            mutable[0, 0] = 0.0
            return mutable
        return result

    monkeypatch.setattr(fitted, "_decode_tensor", invalid_bootstrap_scale)
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="bootstrap tensor domain"):
        fitted.reactome_conditional_fitted_catalog()


def test_fitted_catalog_rejects_bootstrap_row_and_ensemble_digests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_payload = fitted._resource_bytes()
    document = _artifact_document()
    bootstrap = cast("dict[str, object]", document["bootstrap"])
    row_digests = cast("list[object]", bootstrap["row_digests"])
    row_digests[0] = "sha256:" + "0" * 64
    _install_document(monkeypatch, document)
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="row digest"):
        fitted.reactome_conditional_fitted_catalog()

    fitted.reactome_conditional_fitted_catalog.cache_clear()
    _restore_payload(monkeypatch, original_payload)
    document = _artifact_document()
    bootstrap = cast("dict[str, object]", document["bootstrap"])
    tensors = cast("dict[str, object]", bootstrap["tensors"])
    tensors["unbound_extra"] = True
    _install_document(monkeypatch, document)
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="ensemble digest"):
        fitted.reactome_conditional_fitted_catalog()


def test_fitted_catalog_rejects_evaluation_digest_scale_and_component_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_payload = fitted._resource_bytes()
    document = _artifact_document()
    evaluation = cast("dict[str, object]", document["evaluation"])
    evaluation["evaluation_count"] = 519
    _install_document(monkeypatch, document)
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="evaluation digest"):
        fitted.reactome_conditional_fitted_catalog()

    fitted.reactome_conditional_fitted_catalog.cache_clear()
    _restore_payload(monkeypatch, original_payload)
    original_finite = fitted._finite

    def invalid_coordinate_scale(value: object, name: str) -> float:
        if name == "cross-fitted MAD scale":
            return 0.0
        return original_finite(value, name)

    monkeypatch.setattr(fitted, "_finite", invalid_coordinate_scale)
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="scale inventory"):
        fitted.reactome_conditional_fitted_catalog()

    fitted.reactome_conditional_fitted_catalog.cache_clear()
    _restore_payload(monkeypatch, original_payload)
    monkeypatch.setattr(fitted, "_finite", original_finite)
    original_array = fitted._array

    def incomplete_coordinate_scales(value: object, name: str) -> list[object]:
        result = original_array(value, name)
        if name == "cross-fitted coordinate scales":
            return result[:-1]
        return result

    monkeypatch.setattr(fitted, "_array", incomplete_coordinate_scales)
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="component inventory"):
        fitted.reactome_conditional_fitted_catalog()


def test_fitted_catalog_rejects_content_identity_source_and_digest_forgery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = fitted._resource_bytes()
    document = cast("dict[str, object]", json.loads(original))
    document["artifact_digest"] = "sha256:" + "0" * 64
    bad_content = fitted._canonical_bytes(document)
    monkeypatch.setattr(fitted, "_resource_bytes", lambda: bad_content)
    monkeypatch.setattr(fitted, "EXPECTED_ARTIFACT_BYTES", len(bad_content))
    monkeypatch.setattr(
        fitted,
        "EXPECTED_ARTIFACT_SHA256",
        fitted._raw_digest(bad_content),
    )
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="content digest"):
        fitted.reactome_conditional_fitted_catalog()

    fitted.reactome_conditional_fitted_catalog.cache_clear()
    identity = cast("dict[str, object]", json.loads(original))
    identity["schema_version"] = "forged"
    identity_content = dict(identity)
    identity_content.pop("artifact_digest")
    identity_digest = fitted._digest(identity_content)
    identity["artifact_digest"] = identity_digest
    identity_payload = fitted._canonical_bytes(identity)
    _install_locked_payload(monkeypatch, identity_payload, identity_digest)
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="identity"):
        fitted.reactome_conditional_fitted_catalog()

    fitted.reactome_conditional_fitted_catalog.cache_clear()
    source = cast("dict[str, object]", json.loads(original))
    binding = cast("dict[str, object]", source["source_catalog_binding"])
    binding["content_digest"] = "sha256:" + "1" * 64
    source_content = dict(source)
    source_content.pop("artifact_digest")
    source_digest = fitted._digest(source_content)
    source["artifact_digest"] = source_digest
    source_payload = fitted._canonical_bytes(source)
    _install_locked_payload(monkeypatch, source_payload, source_digest)
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="source-catalog"):
        fitted.reactome_conditional_fitted_catalog()

    fitted.reactome_conditional_fitted_catalog.cache_clear()
    digests = cast("dict[str, object]", json.loads(original))
    digest_map = cast("dict[str, object]", digests["digests"])
    digest_map["fold_policy_digest"] = "sha256:" + "2" * 64
    digests_content = dict(digests)
    digests_content.pop("artifact_digest")
    digests_digest = fitted._digest(digests_content)
    digests["artifact_digest"] = digests_digest
    digests_payload = fitted._canonical_bytes(digests)
    _install_locked_payload(monkeypatch, digests_payload, digests_digest)
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="locked digest"):
        fitted.reactome_conditional_fitted_catalog()


def test_fitted_tensor_and_design_guards() -> None:
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="metadata"):
        fitted._decode_tensor({}, "bad", expected_dtype="<f8", expected_shape=(1,))
    invalid_encoding = {
        "dtype": "<f8",
        "shape": [1],
        "encoding": "base64+zlib",
        "data": "!",
    }
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="encoding"):
        fitted._decode_tensor(
            invalid_encoding,
            "bad",
            expected_dtype="<f8",
            expected_shape=(1,),
        )
    document = _artifact_document()
    reference = cast("dict[str, object]", document["reference_fit"])
    tensors = cast("dict[str, object]", reference["tensors"])
    scale_tensor = cast("dict[str, object]", tensors["scale"])
    non_text = dict(scale_tensor)
    non_text["data"] = None
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="data must be text"):
        fitted._decode_tensor(
            non_text,
            "bad",
            expected_dtype="<f8",
            expected_shape=(fitted.EXPECTED_UNION_FEATURE_COUNT,),
        )
    wrong_raw_lock = dict(scale_tensor)
    wrong_raw_lock["raw_bytes"] = 0
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="byte lock"):
        fitted._decode_tensor(
            wrong_raw_lock,
            "bad",
            expected_dtype="<f8",
            expected_shape=(fitted.EXPECTED_UNION_FEATURE_COUNT,),
        )
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="global effect"):
        fitted._derive_design(
            np.zeros(2),
            np.ones(2, dtype=np.bool_),
            ((0,),),
            np.ones(2),
        )
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="conditional loading"):
        fitted._derive_design(
            np.ones(2),
            np.ones(2, dtype=np.bool_),
            ((),),
            np.ones(2),
        )


def test_bootstrap_index_and_engine_classification_boundaries() -> None:
    catalog = fitted.reactome_conditional_fitted_catalog()
    assert catalog.pathway_count == 10
    with pytest.raises(IndexError):
        catalog.bootstrap_draw(-1)
    with pytest.raises(IndexError):
        catalog.bootstrap_draw(catalog.bootstrap_replicate_count)
    assert engine._global_classification(0.26, 0.5) is (
        GlobalRecurrenceClassification.SOURCE_RECURRENCE_ALIGNED
    )
    assert engine._global_classification(-0.5, -0.26) is (
        GlobalRecurrenceClassification.SOURCE_PRIMARY_ALIGNED
    )
    assert engine._global_classification(-0.25, 0.25) is (GlobalRecurrenceClassification.STABLE)
    assert engine._global_classification(-0.3, 0.3) is (
        GlobalRecurrenceClassification.INDETERMINATE
    )
    assert engine._pathway_classification(0.26, 0.5) is (
        ConditionalTransitionClassification.CONDITIONAL_SOURCE_RECURRENCE_ALIGNED
    )
    assert engine._pathway_classification(-0.5, -0.26) is (
        ConditionalTransitionClassification.CONDITIONAL_SOURCE_PRIMARY_ALIGNED
    )
    assert engine._pathway_classification(-0.25, 0.25) is (
        ConditionalTransitionClassification.CONDITIONALLY_STABLE
    )
    assert engine._pathway_classification(-0.3, 0.3) is (
        ConditionalTransitionClassification.INDETERMINATE
    )


def _unknown_active_request() -> LongitudinalGbmReactomeTransitionRequest:
    demo = synthetic_demo_request()
    additions = []
    for index, point in enumerate(demo.time_points[:2]):
        additions.append(
            point.model_copy(
                update={
                    "observations": (
                        *point.observations[:2],
                        ProteinObservation(
                            observation_id=f"unknown.active.{index}",
                            gene_symbol="NOTAREALGENE",
                            state=ProteinEvidenceState.OBSERVED,
                            log_abundance=1.0 + index,
                            standard_error=0.1,
                            quality_weight=1.0,
                            provenance_digest="sha256:" + "a" * 64,
                        ),
                    )
                }
            )
        )
    return LongitudinalGbmReactomeTransitionRequest(
        series_id="unknown.active.reactome",
        assay_compatibility=demo.assay_compatibility,
        normalization_reference=demo.normalization_reference,
        time_points=tuple(additions),
        bootstrap_replicates=32,
    )


def test_engine_rejects_unknown_active_gene_and_honors_cancellation() -> None:
    with pytest.raises(ReactomeConditionalInferenceError, match="outside the locked"):
        engine.infer_longitudinal_gbm_reactome_transition(_unknown_active_request())
    cancellation = CancellationContext()
    cancellation.cancel()
    with pytest.raises(InferenceCancelledError):
        engine.infer_longitudinal_gbm_reactome_transition(
            synthetic_demo_request(),
            cancellation=cancellation,
        )


def test_request_total_observation_limit_branch_is_fail_closed() -> None:
    digest = synthetic_demo_request().normalization_reference.binding_digest
    observations = tuple(
        SimpleNamespace(observation_id=f"observation.{index}") for index in range(12_001)
    )
    fake_points = cast(
        "tuple[LongitudinalTimePoint, ...]",
        (
            SimpleNamespace(
                time_point_id="point.0",
                time_offset_days=0.0,
                normalization_reference_digest=digest,
                observations=observations[:6_000],
            ),
            SimpleNamespace(
                time_point_id="point.1",
                time_offset_days=1.0,
                normalization_reference_digest=digest,
                observations=observations[6_000:],
            ),
        ),
    )
    request = synthetic_demo_request().model_copy(update={"time_points": fake_points})
    with pytest.raises(ValueError, match="limited to 12000"):
        request.series_is_ordered_unique_and_reference_bound()  # type: ignore[operator]


def test_abstained_pathway_cannot_carry_reconstruction_evidence() -> None:
    catalog = fitted.reactome_conditional_fitted_catalog()
    valid = engine._abstained_pathway(
        catalog,
        catalog.pathways[0],
        engine._MassMetrics(0, 0, 0, 0.0, 0.0),
        0,
        0.0,
        ("insufficient evidence",),
    )
    document = valid.model_dump(mode="python")
    document["request_reconstruction_evaluable_fold_count"] = 1
    with pytest.raises(ValidationError, match="cannot carry request reconstruction"):
        ReactomePathwayConcordance.model_validate(document, strict=True)


def test_pathway_profile_identity_and_pi3k_confounding_are_locked() -> None:
    profile = algorithm_profile()
    first_valid = profile.pathways[0].model_dump(mode="python")
    first = dict(first_valid)
    first["domain_id"] = "forged.domain"
    with pytest.raises(ValidationError, match="identity must match"):
        ReactomePathwayProfile.model_validate(first, strict=True)
    invalid_counts = dict(first_valid)
    invalid_counts["eligible_feature_count"] = (
        cast("int", invalid_counts["mapped_feature_count"]) + 1
    )
    with pytest.raises(ValidationError, match="nested within mapped"):
        ReactomePathwayProfile.model_validate(invalid_counts, strict=True)
    pi3k = next(item for item in profile.pathways if item.reactome_id == "R-HSA-198203")
    document = pi3k.model_dump(mode="python")
    document["overlap_confounded"] = False
    with pytest.raises(ValidationError, match="must expose overlap"):
        ReactomePathwayProfile.model_validate(document, strict=True)


def test_bootstrap_and_ablation_failures_are_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = synthetic_demo_request()
    catalog = fitted.reactome_conditional_fitted_catalog()
    active = engine._active_pairs(request, 0, catalog)
    monkeypatch.setattr(
        engine,
        "solve_conditional_coordinates",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ReactomeConditionalInferenceError("forced")
        ),
    )
    bootstrap = engine._bootstrap_coordinates(
        active,
        catalog,
        "sha256:" + "b" * 64,
        0,
        1,
        cancellation=None,
    )
    assert bootstrap.successful_replicates == 0
    assert bootstrap.failed_replicates == 1
    ablation = engine._solve_ablation(
        active,
        catalog.reference_scale,
        catalog.reference_design,
        1,
        catalog.pathways[0].cross_fitted_mad_scale,
        "source_processing",
        "forced",
        0.2,
        cancellation=None,
    )
    assert ablation.support is AnalysisSupport.ABSTAINED


def test_invalid_solve_gate_rejects_nonconvergence() -> None:
    assert not engine._solve_is_valid(_invalid_result())


def test_engine_numeric_helpers_cover_degenerate_and_invalid_domains() -> None:
    with pytest.raises(ReactomeConditionalInferenceError, match="non-finite"):
        engine._quantize(math.inf)
    assert engine._sample_standard_deviation((1.0,)) == 0.0
    with pytest.raises(ReactomeConditionalInferenceError, match="different lengths"):
        engine._sample_covariance((1.0,), ())
    assert engine._sample_covariance((1.0,), (2.0,)) == 0.0
    with pytest.raises(ReactomeConditionalInferenceError, match="requires fitted values"):
        engine._quantile((), 0.5)
    assert engine._quantile((3.0,), 0.5) == 3.0
    assert engine._effective_sample_size((0.0, 0.0)) == 0.0
    assert engine._effective_sample_size(()) == 0.0


def test_engine_rejects_assay_mismatch_and_skips_source_genes_outside_panel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = synthetic_demo_request()
    catalog = fitted.reactome_conditional_fitted_catalog()
    monkeypatch.setattr(
        engine,
        "algorithm_profile",
        lambda: SimpleNamespace(required_assay_compatibility=object()),
    )
    with pytest.raises(ReactomeConditionalInferenceError, match="assay attestation"):
        engine._validate_request(request, catalog)

    source_index = next(
        index
        for index in range(len(catalog.source_catalog.genes))
        if index not in catalog.local_index_by_feature
    )
    symbol = catalog.source_catalog.genes[source_index]
    template = request.time_points[0].observations[0]
    points = tuple(
        point.model_copy(
            update={
                "observations": (
                    template.model_copy(
                        update={
                            "observation_id": f"outside.panel.{index}",
                            "gene_symbol": symbol,
                        }
                    ),
                )
            }
        )
        for index, point in enumerate(request.time_points[:2])
    )
    outside = LongitudinalGbmReactomeTransitionRequest(
        series_id="outside.panel",
        assay_compatibility=request.assay_compatibility,
        normalization_reference=request.normalization_reference,
        time_points=points,
        bootstrap_replicates=32,
    )
    assert engine._active_pairs(outside, 0, catalog) == ()


def test_bootstrap_invalid_results_are_counted_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = synthetic_demo_request()
    catalog = fitted.reactome_conditional_fitted_catalog()
    active = engine._active_pairs(request, 0, catalog)
    monkeypatch.setattr(
        engine,
        "solve_conditional_coordinates",
        lambda *_args, **_kwargs: _invalid_result(),
    )
    bootstrap = engine._bootstrap_coordinates(
        active,
        catalog,
        "sha256:" + "3" * 64,
        0,
        1,
        cancellation=None,
    )
    assert bootstrap.successful_replicates == 0
    assert bootstrap.failed_replicates == 1


def _bootstrap_rows(
    coordinate_count: int,
    count: int,
    *,
    coordinate: float = 0.1,
    failures: int = 0,
) -> engine._BootstrapCoordinates:
    rows = tuple(tuple(coordinate for _ in range(coordinate_count)) for _ in range(count))
    return engine._BootstrapCoordinates(
        measurement=rows,
        fitted_model=rows,
        combined=rows,
        selected_row_digests=tuple(f"row.{index}" for index in range(count)),
        failed_replicates=failures,
    )


def test_global_result_exposes_invalid_solve_and_bootstrap_limitations() -> None:
    metrics = engine._MassMetrics(16, 16, 0, 1.0, 8.0)
    invalid = engine._global_result(
        _invalid_result(condition=2.0),
        _bootstrap_rows(1, 64),
        metrics,
        1.0,
    )
    assert invalid.support is AnalysisSupport.ABSTAINED
    assert "primary joint robust solve" in " ".join(invalid.abstention_reasons)

    limited = engine._global_result(
        _valid_result(1),
        _bootstrap_rows(1, 32, failures=1),
        metrics,
        1.0,
    )
    assert limited.support is AnalysisSupport.LIMITED
    assert len(limited.abstention_reasons) == 2


def test_empty_ablation_and_invalid_solve_constructor_are_explicit() -> None:
    catalog = fitted.reactome_conditional_fitted_catalog()
    ablation = engine._solve_ablation(
        (),
        catalog.reference_scale,
        catalog.reference_design,
        1,
        catalog.pathways[0].cross_fitted_mad_scale,
        "source_processing",
        "empty",
        0.0,
        cancellation=None,
    )
    assert ablation.support is AnalysisSupport.ABSTAINED
    assert "no active evidence" in cast("str", ablation.reason)
    invalid = engine._invalid_solve(3)
    assert invalid.coordinates == (0.0, 0.0, 0.0)
    assert not engine._solve_is_valid(invalid)


@pytest.mark.parametrize(
    "outcome",
    ["full_error", "full_invalid", "omitted_error", "omitted_invalid"],
)
def test_request_reconstruction_failures_remain_non_evaluable(
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    request = synthetic_demo_request()
    catalog = fitted.reactome_conditional_fitted_catalog()
    active = engine._active_pairs(request, 0, catalog)

    def controlled_solver(
        design: np.ndarray[tuple[int, ...], np.dtype[np.float64]],
        *_args: object,
        **_kwargs: object,
    ) -> ConditionalSolveResult:
        full = design.shape[1] == catalog.reference_design.shape[1]
        if (outcome == "full_error" and full) or (outcome == "omitted_error" and not full):
            raise ReactomeConditionalInferenceError("forced")
        if (outcome == "full_invalid" and full) or (outcome == "omitted_invalid" and not full):
            return _invalid_result(condition=2.0)
        return _valid_result(design.shape[1])

    monkeypatch.setattr(engine, "solve_conditional_coordinates", controlled_solver)
    reconstruction = engine._request_reconstruction(
        active,
        catalog,
        cancellation=None,
    )
    assert all(evaluable == 0 for evaluable, _improved, _gain in reconstruction)


def test_request_reconstruction_skips_folds_without_inference_or_validation() -> None:
    catalog = fitted.reactome_conditional_fitted_catalog()
    assert engine._request_reconstruction((), catalog, cancellation=None) == tuple(
        (0, 0, 0.0) for _ in catalog.pathways
    )


def test_zero_contributions_and_discordance_are_not_invented() -> None:
    request = synthetic_demo_request()
    catalog = fitted.reactome_conditional_fitted_catalog()
    active = engine._active_pairs(request, 0, catalog)
    pathway = catalog.pathways[0]
    zeros = np.zeros(catalog.union_feature_count, dtype=np.float64)
    zero_pathway = replace(
        pathway,
        unadjusted_loading=zeros,
        global_adjustment_loading=zeros,
        conditional_loading=zeros,
    )
    assert engine._top_contributions(active, zero_pathway, catalog.reference_scale) == ()
    assert engine._discordance(active, pathway, catalog.reference_scale, 0.0) == 0.0
    assert engine._discordance((), zero_pathway, catalog.reference_scale, 1.0) == 0.0


def _all_numeric_ablations(
    score: float,
    *,
    reverse: bool = False,
) -> ConditionalPathwayAblations:
    without = -abs(score) if reverse else score
    return ConditionalPathwayAblations(
        global_axis=engine._numeric_ablation(
            "global_axis",
            "global_recurrence",
            score,
            without,
            "test sensitivity",
        ),
        source_processing=(
            engine._numeric_ablation(
                "source_processing",
                "ordinary",
                score,
                without,
                "test sensitivity",
            ),
        ),
        degree_normalization=engine._numeric_ablation(
            "degree_normalization",
            "degree",
            score,
            score,
            "test sensitivity",
        ),
        unique_members=engine._numeric_ablation(
            "unique_members",
            "unique",
            score,
            score,
            "test sensitivity",
        ),
        leave_pathway_out=engine._numeric_ablation(
            "leave_pathway_out",
            "leave",
            score,
            0.0,
            "test sensitivity",
        ),
    )


def _supported_global() -> GlobalRecurrenceConcordance:
    return engine._global_result(
        _valid_result(1),
        _bootstrap_rows(1, 64),
        engine._MassMetrics(16, 16, 0, 1.0, 8.0),
        1.0,
    )


def test_pathway_result_covers_invalid_and_limited_evidence_gates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = synthetic_demo_request()
    catalog = fitted.reactome_conditional_fitted_catalog()
    active = engine._active_pairs(request, 0, catalog)
    pathway = catalog.pathways[0]
    global_result = _supported_global()

    abstained = engine._pathway_result(
        active,
        catalog,
        pathway,
        _invalid_result(condition=2.0),
        _bootstrap_rows(catalog.pathway_count + 1, 64),
        global_result,
        (0, 0, 0.0),
        {},
        cancellation=None,
    )
    assert abstained.support is AnalysisSupport.ABSTAINED
    assert "primary joint robust solve" in " ".join(abstained.abstention_reasons)

    monkeypatch.setattr(
        engine,
        "_pathway_ablations",
        lambda _active, _catalog, _pathway, score, _cache, *, cancellation: _all_numeric_ablations(
            score
        ),
    )
    point = _valid_result(catalog.pathway_count + 1)
    limited = engine._pathway_result(
        active,
        catalog,
        pathway,
        point,
        _bootstrap_rows(catalog.pathway_count + 1, 32, failures=1),
        global_result,
        (4, 4, 0.02),
        {},
        cancellation=None,
    )
    assert limited.support is AnalysisSupport.LIMITED
    reasons = " ".join(limited.abstention_reasons)
    assert "requested fitted bootstrap" in reasons
    assert "fewer than 64" in reasons
    assert "all five held-gene" in reasons
    assert "structural ablations are not estimable" not in reasons

    monkeypatch.setattr(
        engine,
        "_pathway_ablations",
        lambda _active, _catalog, _pathway, score, _cache, *, cancellation: _all_numeric_ablations(
            score, reverse=True
        ),
    )
    reversed_result = engine._pathway_result(
        active,
        catalog,
        pathway,
        point,
        _bootstrap_rows(catalog.pathway_count + 1, 64),
        global_result,
        (5, 4, 0.02),
        {},
        cancellation=None,
    )
    assert "reverses" in " ".join(reversed_result.abstention_reasons)


def _overlap_pair(
    active: tuple[engine._ActivePair, ...],
    catalog: fitted.ReactomeConditionalFittedCatalog,
) -> tuple[fitted.FittedPathwayLoading, fitted.FittedPathwayLoading, tuple[int, ...]]:
    for left_index, left in enumerate(catalog.pathways):
        for right in catalog.pathways[left_index + 1 :]:
            shared = frozenset(left.member_local_indices) & frozenset(right.member_local_indices)
            removed = tuple(pair.local_position for pair in active if pair.local_position in shared)
            if not removed:
                continue
            remaining = tuple(pair for pair in active if pair.local_position not in shared)
            supported = True
            for pathway in (left, right):
                metrics = engine._mass_metrics(
                    remaining,
                    pathway.unadjusted_loading,
                    pathway.member_local_indices,
                    catalog.reference_scale,
                )
                supported = supported and (
                    metrics.active_count >= 5
                    and metrics.coverage >= 0.5
                    and metrics.effective_sample_size >= 3.0
                )
            if supported:
                return left, right, tuple(sorted(removed))
    raise AssertionError(_OVERLAP_PAIR_ASSERTION)


@pytest.mark.parametrize("outcome", ["valid", "error", "invalid"])
def test_overlap_removal_refit_is_cached_and_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    request = synthetic_demo_request()
    catalog = fitted.reactome_conditional_fitted_catalog()
    active = engine._active_pairs(request, 0, catalog)
    left, right, removed_positions = _overlap_pair(active, catalog)
    small_catalog = replace(catalog, pathways=(left, right))
    remaining_positions = frozenset(
        pair.local_position for pair in active if pair.local_position not in removed_positions
    )
    overlap_solve_calls = 0

    def controlled_solver(
        design: np.ndarray[tuple[int, ...], np.dtype[np.float64]],
        evidence: tuple[SolverEvidence, ...],
        **_kwargs: object,
    ) -> ConditionalSolveResult:
        nonlocal overlap_solve_calls
        positions = frozenset(item.feature_position for item in evidence)
        if positions == remaining_positions and design.shape == catalog.reference_design.shape:
            overlap_solve_calls += 1
            if outcome == "error":
                raise ReactomeConditionalInferenceError(_FORCED_OVERLAP_FAILURE)
            if outcome == "invalid":
                return _invalid_result(condition=2.0)
        return _valid_result(design.shape[1])

    monkeypatch.setattr(engine, "solve_conditional_coordinates", controlled_solver)
    cache: dict[tuple[int, ...], ConditionalSolveResult | None] = {}
    left_result = engine._pathway_ablations(
        active,
        small_catalog,
        left,
        0.4,
        cache,
        cancellation=None,
    )
    right_result = engine._pathway_ablations(
        active,
        small_catalog,
        right,
        0.4,
        cache,
        cancellation=None,
    )
    assert overlap_solve_calls == 1
    assert tuple(cache) == (removed_positions,)
    expected_support = AnalysisSupport.LIMITED if outcome == "valid" else AnalysisSupport.ABSTAINED
    assert left_result.overlap[0].support is expected_support
    assert right_result.overlap[0].support is expected_support


def _missing_request() -> LongitudinalGbmReactomeTransitionRequest:
    demo = synthetic_demo_request()
    template = demo.time_points[0].observations[0]
    points = tuple(
        point.model_copy(
            update={
                "observations": (
                    ProteinObservation(
                        observation_id=f"missing.{index}",
                        gene_symbol=template.gene_symbol,
                        state=ProteinEvidenceState.MISSING,
                        log_abundance=None,
                        standard_error=None,
                        quality_weight=0.0,
                        provenance_digest=template.provenance_digest,
                    ),
                )
            }
        )
        for index, point in enumerate(demo.time_points[:2])
    )
    return LongitudinalGbmReactomeTransitionRequest(
        series_id="reactome.missing.only",
        assay_compatibility=demo.assay_compatibility,
        normalization_reference=demo.normalization_reference,
        time_points=points,
        bootstrap_replicates=32,
    )


def test_transition_primary_failure_and_no_active_evidence_are_abstained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = fitted.reactome_conditional_fitted_catalog()
    request = _unknown_active_request().model_copy(
        update={"series_id": "reactome.primary.solve.failure"}
    )
    known_only = request.model_copy(
        update={
            "time_points": tuple(
                point.model_copy(update={"observations": point.observations[:2]})
                for point in request.time_points
            )
        }
    )
    monkeypatch.setattr(
        engine,
        "solve_conditional_coordinates",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ReactomeConditionalInferenceError("forced primary failure")
        ),
    )
    failed = engine._calculate_transition(
        known_only,
        0,
        catalog,
        "sha256:" + "4" * 64,
        cancellation=None,
    )
    assert failed.global_recurrence.support is AnalysisSupport.ABSTAINED

    missing = engine._calculate_transition(
        _missing_request(),
        0,
        catalog,
        "sha256:" + "5" * 64,
        cancellation=None,
    )
    assert missing.global_recurrence.shared_active_gene_count == 0
    assert missing.global_recurrence.support is AnalysisSupport.ABSTAINED


def test_demo_oracle_guard_fails_closed_on_semantic_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _missing_request()
    profile = algorithm_profile().model_copy(update={"demo_request_digest": request.request_digest})
    monkeypatch.setattr(engine, "algorithm_profile", lambda: profile)
    monkeypatch.setattr(
        engine,
        "EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST",
        "sha256:" + "0" * 64,
    )
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="semantic oracle"):
        engine.infer_longitudinal_gbm_reactome_transition(request)
