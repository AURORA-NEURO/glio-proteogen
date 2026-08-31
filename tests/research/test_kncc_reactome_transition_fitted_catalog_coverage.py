from __future__ import annotations

import math
from typing import TYPE_CHECKING, cast

import numpy as np
import pytest

from glio_proteogen.research.longitudinal_gbm_reactome_transition import (
    fitted_catalog as fitted,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.errors import (
    ReactomeConditionalModelIntegrityError,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _clear_fitted_catalog_cache() -> Iterator[None]:
    fitted.reactome_conditional_fitted_catalog.cache_clear()
    yield
    fitted.reactome_conditional_fitted_catalog.cache_clear()


def test_fitted_catalog_counts_and_bootstrap_design_are_live() -> None:
    catalog = fitted.reactome_conditional_fitted_catalog()

    assert catalog.union_feature_count == fitted.EXPECTED_UNION_FEATURE_COUNT
    design = catalog.design_for_bootstrap(0)
    assert design.shape == (
        fitted.EXPECTED_UNION_FEATURE_COUNT,
        fitted.EXPECTED_DESIGN_COLUMNS,
    )
    assert not design.flags.writeable


def test_fitted_scalar_guards_reject_bool_text_and_nonfinite_values() -> None:
    boolean_value: object = True
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="must be an object"):
        fitted._object([], "object")
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="must be an array"):
        fitted._array({}, "array")
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="must be an integer"):
        fitted._integer(boolean_value, "integer")
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="must be numeric"):
        fitted._finite("1", "number")
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="must be finite"):
        fitted._finite(math.inf, "finite number")


def test_fitted_catalog_rejects_invalid_decoded_bootstrap_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_decode = fitted._decode_tensor

    def invalid_bootstrap_scale(
        value: object,
        name: str,
        *,
        expected_dtype: str,
        expected_shape: tuple[int, ...],
    ) -> np.ndarray[tuple[int, ...], np.dtype[np.generic]]:
        decoded = original_decode(
            value,
            name,
            expected_dtype=expected_dtype,
            expected_shape=expected_shape,
        )
        if name == "bootstrap scale":
            corrupted = np.array(decoded, copy=True)
            corrupted[0, 0] = 0.0
            return corrupted
        return decoded

    monkeypatch.setattr(fitted, "_decode_tensor", invalid_bootstrap_scale)
    with pytest.raises(
        ReactomeConditionalModelIntegrityError,
        match="bootstrap tensor domain",
    ):
        fitted.reactome_conditional_fitted_catalog()


def test_fitted_catalog_rejects_bootstrap_ensemble_projection_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_digest = fitted._digest

    def corrupt_bootstrap_projection(value: object) -> str:
        if type(value) is dict and set(cast("dict[str, object]", value)) == {
            "row_digests",
            "tensors",
        }:
            return "sha256:" + "0" * 64
        return original_digest(value)

    monkeypatch.setattr(fitted, "_digest", corrupt_bootstrap_projection)
    with pytest.raises(
        ReactomeConditionalModelIntegrityError,
        match="bootstrap ensemble digest",
    ):
        fitted.reactome_conditional_fitted_catalog()


def test_fitted_catalog_rejects_source_processing_projection_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_digest = fitted._digest

    def corrupt_source_processing_projection(value: object) -> str:
        if type(value) is dict:
            projection = cast("dict[str, object]", value)
            if projection.get("dtype") == "<f8" and projection.get("shape") == [
                fitted.EXPECTED_UNION_FEATURE_COUNT
            ]:
                return "sha256:" + "0" * 64
        return original_digest(value)

    monkeypatch.setattr(fitted, "_digest", corrupt_source_processing_projection)
    with pytest.raises(
        ReactomeConditionalModelIntegrityError,
        match="source-processing digest",
    ):
        fitted.reactome_conditional_fitted_catalog()


def test_fitted_catalog_rejects_bootstrap_row_digest_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = fitted.reactome_conditional_fitted_catalog()
    first_row = catalog.bootstrap_scales[0].tobytes() + catalog.bootstrap_effects[0].tobytes()
    fitted.reactome_conditional_fitted_catalog.cache_clear()
    original_raw_digest = fitted._raw_digest

    def corrupt_bootstrap_row_digest(value: bytes) -> str:
        if value == first_row:
            return "sha256:" + "0" * 64
        return original_raw_digest(value)

    monkeypatch.setattr(fitted, "_raw_digest", corrupt_bootstrap_row_digest)
    with pytest.raises(
        ReactomeConditionalModelIntegrityError,
        match="bootstrap row digest",
    ):
        fitted.reactome_conditional_fitted_catalog()


def test_fitted_catalog_rejects_evaluation_projection_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_digest = fitted._digest

    def corrupt_evaluation_projection(value: object) -> str:
        if type(value) is dict and "evaluation_count" in cast("dict[str, object]", value):
            return "sha256:" + "0" * 64
        return original_digest(value)

    monkeypatch.setattr(fitted, "_digest", corrupt_evaluation_projection)
    with pytest.raises(
        ReactomeConditionalModelIntegrityError,
        match="evaluation digest or oracle",
    ):
        fitted.reactome_conditional_fitted_catalog()


def test_fitted_catalog_rejects_nonpositive_coordinate_scale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_finite = fitted._finite

    def nonpositive_scale(value: object, name: str) -> float:
        if name == "cross-fitted MAD scale":
            return 0.0
        return original_finite(value, name)

    monkeypatch.setattr(fitted, "_finite", nonpositive_scale)
    with pytest.raises(
        ReactomeConditionalModelIntegrityError,
        match="coordinate scale inventory",
    ):
        fitted.reactome_conditional_fitted_catalog()


def test_fitted_catalog_rejects_incomplete_coordinate_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_array = fitted._array

    def omit_coordinate(value: object, name: str) -> list[object]:
        result = original_array(value, name)
        if name == "cross-fitted coordinate scales":
            return result[:-1]
        return result

    monkeypatch.setattr(fitted, "_array", omit_coordinate)
    with pytest.raises(
        ReactomeConditionalModelIntegrityError,
        match="coordinate component inventory",
    ):
        fitted.reactome_conditional_fitted_catalog()
