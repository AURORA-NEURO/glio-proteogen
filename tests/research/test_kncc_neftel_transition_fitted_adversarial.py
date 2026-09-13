from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, cast

import numpy as np
import pytest

from glio_proteogen.research.longitudinal_gbm_neftel_transition import (
    fitted_catalog as fitted,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.errors import (
    NeftelConditionalModelIntegrityError,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

_RUNTIME_DESIGN_DIGEST_ASSERTION = "runtime-derived reference designs must not be raw-digested"


@pytest.fixture(autouse=True)
def _clear_fitted_cache() -> Iterator[None]:
    fitted.neftel_program_fitted_catalog.cache_clear()
    yield
    fitted.neftel_program_fitted_catalog.cache_clear()


def _artifact_document() -> dict[str, object]:
    return cast("dict[str, object]", json.loads(fitted._resource_bytes()))


def _install_locked_payload(
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    content_digest: str,
) -> None:
    monkeypatch.setattr(fitted, "_resource_bytes", lambda: payload)
    monkeypatch.setattr(fitted, "EXPECTED_ARTIFACT_BYTES", len(payload))
    monkeypatch.setattr(fitted, "EXPECTED_ARTIFACT_SHA256", fitted._raw_digest(payload))
    monkeypatch.setattr(fitted, "EXPECTED_CONTENT_DIGEST", content_digest)


def _install_document(
    monkeypatch: pytest.MonkeyPatch,
    document: dict[str, object],
) -> None:
    content = dict(document)
    content.pop("artifact_digest", None)
    content_digest = fitted._digest(content)
    document["artifact_digest"] = content_digest
    _install_locked_payload(monkeypatch, fitted._canonical_bytes(document), content_digest)


def _restore_payload(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> None:
    document = cast("dict[str, object]", json.loads(payload))
    content = dict(document)
    content.pop("artifact_digest")
    _install_locked_payload(monkeypatch, payload, fitted._digest(content))


def test_fitted_scalar_tensor_and_design_guards() -> None:
    with pytest.raises(NeftelConditionalModelIntegrityError, match="must be an object"):
        fitted._object([], "bad")
    with pytest.raises(NeftelConditionalModelIntegrityError, match="must be an array"):
        fitted._array({}, "bad")
    boolean_value: object = True
    with pytest.raises(NeftelConditionalModelIntegrityError, match="must be an integer"):
        fitted._integer(boolean_value, "bad")
    with pytest.raises(NeftelConditionalModelIntegrityError, match="must be numeric"):
        fitted._finite("1", "bad")
    with pytest.raises(NeftelConditionalModelIntegrityError, match="must be finite"):
        fitted._finite(math.inf, "bad")
    with pytest.raises(NeftelConditionalModelIntegrityError, match="metadata"):
        fitted._decode_tensor({}, "bad", expected_dtype="<f8", expected_shape=(1,))
    invalid_encoding = {
        "dtype": "<f8",
        "shape": [1],
        "encoding": "base64+zlib",
        "data": "!",
    }
    with pytest.raises(NeftelConditionalModelIntegrityError, match="encoding"):
        fitted._decode_tensor(
            invalid_encoding,
            "bad",
            expected_dtype="<f8",
            expected_shape=(1,),
        )
    reference = cast("dict[str, object]", _artifact_document()["reference_fit"])
    tensors = cast("dict[str, object]", reference["tensors"])
    scale_tensor = cast("dict[str, object]", tensors["scale"])
    non_text = dict(scale_tensor)
    non_text["data"] = None
    with pytest.raises(NeftelConditionalModelIntegrityError, match="data must be text"):
        fitted._decode_tensor(
            non_text,
            "bad",
            expected_dtype="<f8",
            expected_shape=(fitted.EXPECTED_UNION_FEATURE_COUNT,),
        )
    wrong_raw_lock = dict(scale_tensor)
    wrong_raw_lock["raw_bytes"] = 0
    with pytest.raises(NeftelConditionalModelIntegrityError, match="byte lock"):
        fitted._decode_tensor(
            wrong_raw_lock,
            "bad",
            expected_dtype="<f8",
            expected_shape=(fitted.EXPECTED_UNION_FEATURE_COUNT,),
        )
    with pytest.raises(NeftelConditionalModelIntegrityError, match="global effect"):
        fitted._derive_design(
            np.zeros(2),
            np.ones(2, dtype=np.bool_),
            ((0,),),
            np.ones(2),
        )
    with pytest.raises(NeftelConditionalModelIntegrityError, match="conditional loading"):
        fitted._derive_design(
            np.ones(2),
            np.ones(2, dtype=np.bool_),
            ((),),
            np.ones(2),
        )
    with pytest.raises(NeftelConditionalModelIntegrityError, match="global effect"):
        fitted._derive_equal_membership_design(
            np.zeros(2),
            np.ones(2, dtype=np.bool_),
            ((0,),),
            np.ones(2),
        )
    with pytest.raises(NeftelConditionalModelIntegrityError, match="equal-membership"):
        fitted._derive_equal_membership_design(
            np.ones(2),
            np.ones(2, dtype=np.bool_),
            ((),),
            np.ones(2),
        )
    with pytest.raises(NeftelConditionalModelIntegrityError, match="shape mismatch"):
        fitted._loading_cosines(np.ones((2, 1)), np.ones((3, 1)))
    with pytest.raises(NeftelConditionalModelIntegrityError, match="norm is invalid"):
        fitted._loading_cosines(np.zeros((2, 1)), np.ones((2, 1)))


def test_fitted_catalog_counts_bootstrap_bounds_and_deep_freeze() -> None:
    catalog = fitted.neftel_program_fitted_catalog()
    assert catalog.union_feature_count == fitted.EXPECTED_UNION_FEATURE_COUNT
    assert catalog.program_count == 8
    assert catalog.bootstrap_replicate_count == 128
    assert catalog.design_for_bootstrap(0).shape == (256, 9)
    with pytest.raises(IndexError):
        catalog.bootstrap_draw(-1)
    with pytest.raises(IndexError):
        catalog.bootstrap_draw(catalog.bootstrap_replicate_count)
    frozen = fitted._deep_freeze({"rows": [{"value": 1}]})
    assert frozen is not None


def test_fitted_catalog_rejects_byte_length_digest_and_canonical_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = fitted._resource_bytes()
    monkeypatch.setattr(fitted, "_resource_bytes", lambda: b"")
    with pytest.raises(NeftelConditionalModelIntegrityError, match="byte length"):
        fitted.neftel_program_fitted_catalog()

    fitted.neftel_program_fitted_catalog.cache_clear()
    corrupted = bytearray(original)
    corrupted[-2] ^= 1
    monkeypatch.setattr(fitted, "_resource_bytes", lambda: bytes(corrupted))
    with pytest.raises(NeftelConditionalModelIntegrityError, match="byte digest"):
        fitted.neftel_program_fitted_catalog()

    fitted.neftel_program_fitted_catalog.cache_clear()
    pretty = json.dumps(json.loads(original), indent=2).encode()
    monkeypatch.setattr(fitted, "_resource_bytes", lambda: pretty)
    monkeypatch.setattr(fitted, "EXPECTED_ARTIFACT_BYTES", len(pretty))
    monkeypatch.setattr(fitted, "EXPECTED_ARTIFACT_SHA256", fitted._raw_digest(pretty))
    with pytest.raises(NeftelConditionalModelIntegrityError, match="canonical JSON"):
        fitted.neftel_program_fitted_catalog()


def test_fitted_catalog_rejects_invalid_json_nonobject_and_content_forgery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = fitted._resource_bytes()
    malformed = b"{\n"
    _install_locked_payload(monkeypatch, malformed, fitted.EXPECTED_CONTENT_DIGEST)
    with pytest.raises(NeftelConditionalModelIntegrityError, match="valid JSON"):
        fitted.neftel_program_fitted_catalog()

    fitted.neftel_program_fitted_catalog.cache_clear()
    array_root = b"[]\n"
    _install_locked_payload(monkeypatch, array_root, fitted.EXPECTED_CONTENT_DIGEST)
    with pytest.raises(NeftelConditionalModelIntegrityError, match="root must be"):
        fitted.neftel_program_fitted_catalog()

    fitted.neftel_program_fitted_catalog.cache_clear()
    _restore_payload(monkeypatch, original)
    document = _artifact_document()
    document["artifact_digest"] = "sha256:" + "0" * 64
    payload = fitted._canonical_bytes(document)
    monkeypatch.setattr(fitted, "_resource_bytes", lambda: payload)
    monkeypatch.setattr(fitted, "EXPECTED_ARTIFACT_BYTES", len(payload))
    monkeypatch.setattr(fitted, "EXPECTED_ARTIFACT_SHA256", fitted._raw_digest(payload))
    with pytest.raises(NeftelConditionalModelIntegrityError, match="content digest"):
        fitted.neftel_program_fitted_catalog()


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("identity", "identity"),
        ("recipe", "training recipe"),
        ("counts", "count inventory"),
        ("union", "union feature axis"),
        ("program", "program inventory"),
        ("privacy", "privacy declaration"),
        ("limitations", "limitation inventory"),
        ("numpy", "NumPy version"),
        ("digest_inventory", "locked digest inventory"),
        ("source", "source-catalog binding"),
    ],
)
def test_fitted_catalog_rejects_locked_domain_mutations(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    message: str,
) -> None:
    document = _artifact_document()
    if case == "identity":
        document["schema_version"] = "forged"
    elif case == "recipe":
        cast("dict[str, object]", document["training_recipe"])["solver_max_iterations"] = 199
    elif case == "counts":
        cast("dict[str, object]", document["counts"])["source_patient_pairs"] = 103
    elif case == "union":
        union = cast("list[object]", document["union_feature_indices"])
        union[0] = union[1]
    elif case == "program":
        cast("list[object]", document["programs"])[0] = {}
    elif case == "privacy":
        privacy = cast("dict[str, object]", document["privacy"])
        privacy[next(iter(privacy))] = True
    elif case == "limitations":
        document["limitations"] = ["too short"]
    elif case == "numpy":
        cast("dict[str, object]", document["provenance"])["numpy_version"] = "0.0.0"
    elif case == "digest_inventory":
        cast("dict[str, object]", document["digests"]).pop("fold_policy_digest")
    else:
        cast("dict[str, object]", document["source_catalog_binding"])["forged"] = True
    _install_document(monkeypatch, document)
    with pytest.raises(NeftelConditionalModelIntegrityError, match=message):
        fitted.neftel_program_fitted_catalog()


@pytest.mark.parametrize(
    "field",
    ["global_loading_digest", "conditional_loading_digest"],
)
def test_fitted_catalog_rejects_forged_loading_digest_inventory(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    document = _artifact_document()
    cast("dict[str, object]", document["digests"])[field] = "sha256:" + "0" * 64
    _install_document(monkeypatch, document)

    with pytest.raises(
        NeftelConditionalModelIntegrityError,
        match="locked digest inventory",
    ):
        fitted.neftel_program_fitted_catalog()


def test_fitted_catalog_rejects_membership_reference_and_design_mismatches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_decode = fitted._decode_tensor

    def invalid_degree(
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
        if name == "membership degree":
            mutable = np.array(result, copy=True)
            mutable[0] = 0
            return mutable
        return result

    monkeypatch.setattr(fitted, "_decode_tensor", invalid_degree)
    with pytest.raises(NeftelConditionalModelIntegrityError, match="membership degree"):
        fitted.neftel_program_fitted_catalog()

    fitted.neftel_program_fitted_catalog.cache_clear()

    def invalid_scale(
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

    monkeypatch.setattr(fitted, "_decode_tensor", invalid_scale)
    with pytest.raises(NeftelConditionalModelIntegrityError, match="tensor domain"):
        fitted.neftel_program_fitted_catalog()

    fitted.neftel_program_fitted_catalog.cache_clear()
    monkeypatch.setattr(fitted, "_decode_tensor", original_decode)
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
    with pytest.raises(NeftelConditionalModelIntegrityError, match="centering/scaling"):
        fitted.neftel_program_fitted_catalog()

    fitted.neftel_program_fitted_catalog.cache_clear()
    monkeypatch.setattr(fitted, "_digest", original_digest)
    original_condition = np.linalg.cond
    monkeypatch.setattr(
        np.linalg,
        "cond",
        lambda value: float(original_condition(value)) + 1.0,
    )
    with pytest.raises(NeftelConditionalModelIntegrityError, match="loading condition"):
        fitted.neftel_program_fitted_catalog()


def test_fitted_catalog_accepts_portable_reference_loading_roundoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = fitted.neftel_program_fitted_catalog()
    fitted.neftel_program_fitted_catalog.cache_clear()
    original_derive = fitted._derive_design
    original_equal = fitted._derive_equal_membership_design
    original_raw_digest = fitted._raw_digest
    original_condition = np.linalg.cond
    reference_design_bytes = baseline.reference_design.nbytes
    invocation_count = 0
    equal_membership_varied = False

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

    def one_ulp_equal_membership_design(
        effect: fitted.FloatArray,
        eligible: fitted.BoolArray,
        members: tuple[tuple[int, ...], ...],
        degree: fitted.FloatArray,
    ) -> fitted.FloatArray:
        nonlocal equal_membership_varied
        design = np.array(original_equal(effect, eligible, members, degree), copy=True)
        index = np.unravel_index(np.argmax(np.abs(design)), design.shape)
        design[index] = np.nextafter(design[index], math.inf)
        equal_membership_varied = True
        return design

    def forbid_runtime_design_digest(value: bytes) -> str:
        if len(value) == reference_design_bytes:
            raise AssertionError(_RUNTIME_DESIGN_DIGEST_ASSERTION)
        return original_raw_digest(value)

    monkeypatch.setattr(fitted, "_derive_design", one_ulp_reference_design)
    monkeypatch.setattr(
        fitted,
        "_derive_equal_membership_design",
        one_ulp_equal_membership_design,
    )
    monkeypatch.setattr(fitted, "_raw_digest", forbid_runtime_design_digest)
    monkeypatch.setattr(
        np.linalg,
        "cond",
        lambda value: float(original_condition(value)) + 2.0e-10,
    )
    varied = fitted.neftel_program_fitted_catalog()

    assert varied.reference_design_digest == baseline.reference_design_digest
    assert varied.equal_membership_design_digest == baseline.equal_membership_design_digest
    assert not np.array_equal(varied.reference_design, baseline.reference_design)
    assert equal_membership_varied


@pytest.mark.parametrize(
    ("target", "message"),
    [
        ("design", "loading semantic"),
        ("equal design", "loading semantic"),
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
    original_equal = fitted._derive_equal_membership_design
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
            elif target == "decomposition count":
                decompositions = decompositions[:-1]
        invocation_count += 1
        return design, decompositions

    def corrupt_equal_membership_design(
        effect: fitted.FloatArray,
        eligible: fitted.BoolArray,
        members: tuple[tuple[int, ...], ...],
        degree: fitted.FloatArray,
    ) -> fitted.FloatArray:
        design = original_equal(effect, eligible, members, degree)
        if target != "equal design":
            return design
        corrupted = np.array(design, copy=True)
        corrupted[0, 0] += 1.0e-6
        return corrupted

    monkeypatch.setattr(fitted, "_derive_design", corrupt_reference_design)
    monkeypatch.setattr(
        fitted,
        "_derive_equal_membership_design",
        corrupt_equal_membership_design,
    )
    with pytest.raises(NeftelConditionalModelIntegrityError, match=message):
        fitted.neftel_program_fitted_catalog()


@pytest.mark.parametrize(
    "field",
    ["design_raw_sha256", "equal_membership_design_raw_sha256"],
)
def test_fitted_catalog_rejects_unbound_reference_design_provenance(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    document = _artifact_document()
    reference = cast("dict[str, object]", document["reference_fit"])
    reference[field] = "sha256:" + "0" * 64
    _install_document(monkeypatch, document)

    with pytest.raises(
        NeftelConditionalModelIntegrityError,
        match="loading provenance digest",
    ):
        fitted.neftel_program_fitted_catalog()


def test_fitted_catalog_rejects_unbound_conditional_semantic_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        fitted,
        "_quantized_loading_digest",
        lambda _array: "sha256:" + "0" * 64,
    )

    with pytest.raises(
        NeftelConditionalModelIntegrityError,
        match="loading semantic digest",
    ):
        fitted.neftel_program_fitted_catalog()


def test_fitted_catalog_rejects_processing_bootstrap_and_evaluation_mismatches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_payload = fitted._resource_bytes()
    document = _artifact_document()
    processing = cast("dict[str, object]", document["source_processing_ablation"])
    cast("dict[str, object]", processing["effect"])["unbound_extra"] = True
    _install_document(monkeypatch, document)
    with pytest.raises(NeftelConditionalModelIntegrityError, match="source-processing"):
        fitted.neftel_program_fitted_catalog()

    fitted.neftel_program_fitted_catalog.cache_clear()
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
    with pytest.raises(NeftelConditionalModelIntegrityError, match="bootstrap tensor domain"):
        fitted.neftel_program_fitted_catalog()

    fitted.neftel_program_fitted_catalog.cache_clear()
    _restore_payload(monkeypatch, original_payload)
    monkeypatch.setattr(fitted, "_decode_tensor", original_decode)
    document = _artifact_document()
    bootstrap = cast("dict[str, object]", document["bootstrap"])
    cast("list[object]", bootstrap["row_digests"])[0] = "sha256:" + "0" * 64
    _install_document(monkeypatch, document)
    with pytest.raises(NeftelConditionalModelIntegrityError, match="row digest"):
        fitted.neftel_program_fitted_catalog()

    fitted.neftel_program_fitted_catalog.cache_clear()
    _restore_payload(monkeypatch, original_payload)
    document = _artifact_document()
    cast("dict[str, object]", document["evaluation"])["evaluation_count"] = 519
    _install_document(monkeypatch, document)
    with pytest.raises(NeftelConditionalModelIntegrityError, match="evaluation"):
        fitted.neftel_program_fitted_catalog()


def test_fitted_catalog_rejects_coordinate_scale_and_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_finite = fitted._finite

    def invalid_coordinate_scale(value: object, name: str) -> float:
        if name == "cross-fitted MAD scale":
            return 0.0
        return original_finite(value, name)

    monkeypatch.setattr(fitted, "_finite", invalid_coordinate_scale)
    with pytest.raises(NeftelConditionalModelIntegrityError, match="scale inventory"):
        fitted.neftel_program_fitted_catalog()

    fitted.neftel_program_fitted_catalog.cache_clear()
    monkeypatch.setattr(fitted, "_finite", original_finite)
    original_array = fitted._array

    def incomplete_scales(value: object, name: str) -> list[object]:
        result = original_array(value, name)
        if name == "cross-fitted coordinate scales":
            return result[:-1]
        return result

    monkeypatch.setattr(fitted, "_array", incomplete_scales)
    with pytest.raises(NeftelConditionalModelIntegrityError, match="component inventory"):
        fitted.neftel_program_fitted_catalog()


def test_fitted_catalog_rejects_exact_program_tensor_ablation_and_ensemble_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_payload = fitted._resource_bytes()
    original_digest = fitted._digest

    document = _artifact_document()
    first_program = cast("dict[str, object]", cast("list[object]", document["programs"])[0])
    first_program["program_id"] = "forged"
    _install_document(monkeypatch, document)
    locked_program_digest = cast("dict[str, str]", document["digests"])["program_inventory_digest"]

    def preserve_program_inventory_digest(value: object) -> str:
        if (
            type(value) is list
            and len(cast("list[object]", value)) == 8
            and cast("dict[str, object]", cast("list[object]", value)[0]).get("program_id")
            == "forged"
        ):
            return locked_program_digest
        return original_digest(value)

    monkeypatch.setattr(fitted, "_digest", preserve_program_inventory_digest)
    with pytest.raises(NeftelConditionalModelIntegrityError, match="program inventory mismatch"):
        fitted.neftel_program_fitted_catalog()

    fitted.neftel_program_fitted_catalog.cache_clear()
    monkeypatch.setattr(fitted, "_digest", original_digest)
    _restore_payload(monkeypatch, original_payload)
    document = _artifact_document()
    reference = cast("dict[str, object]", document["reference_fit"])
    cast("dict[str, object]", reference["tensors"])["unbound_extra"] = True
    _install_document(monkeypatch, document)
    with pytest.raises(NeftelConditionalModelIntegrityError, match="reference tensor digest"):
        fitted.neftel_program_fitted_catalog()

    fitted.neftel_program_fitted_catalog.cache_clear()
    _restore_payload(monkeypatch, original_payload)
    document = _artifact_document()
    processing = cast("dict[str, object]", document["source_processing_ablation"])
    loading_cosines = cast("list[object]", processing["loading_cosines"])
    loading_cosines[0] = cast("float", loading_cosines[0]) + 0.01
    _install_document(monkeypatch, document)
    with pytest.raises(NeftelConditionalModelIntegrityError, match="loading-ablation oracle"):
        fitted.neftel_program_fitted_catalog()

    fitted.neftel_program_fitted_catalog.cache_clear()
    _restore_payload(monkeypatch, original_payload)
    document = _artifact_document()
    bootstrap = cast("dict[str, object]", document["bootstrap"])
    cast("dict[str, object]", bootstrap["tensors"])["unbound_extra"] = True
    _install_document(monkeypatch, document)
    with pytest.raises(NeftelConditionalModelIntegrityError, match="bootstrap ensemble digest"):
        fitted.neftel_program_fitted_catalog()
