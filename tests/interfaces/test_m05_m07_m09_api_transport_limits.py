"""Pre-parse transport ceilings for remaining module-local FastAPI apps."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from glio_proteogen.modules.c05_ptm_localization.m05_08_release_packaging.api import (
    create_app as create_m0508_app,
)
from glio_proteogen.modules.c07_copy_number.m07_01_formal_state_feature_schema.api import (
    create_app as create_m0701_app,
)
from glio_proteogen.modules.c07_copy_number.m07_02_representation_feature_constructor.api import (
    create_app as create_m0702_app,
)
from glio_proteogen.modules.c09_complex_activity.m09_05_mechanism_constraint_integrator.api import (
    create_app as create_m0905_app,
)

_OVERSIZED = b"{" + b"x" * (4 * 1024 * 1024) + b"}"

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize(
    "factory",
    [create_m0508_app, create_m0701_app, create_m0702_app, create_m0905_app],
)
def test_module_apps_reject_oversized_body_before_route_parsing(
    factory: Callable[[], Any],
) -> None:
    response = TestClient(factory()).post("/v1/modules/test/validate", content=_OVERSIZED)
    assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert response.json()["detail"] == "request body exceeds the byte limit"


def test_m0702_verify_uses_result_ceiling() -> None:
    response = TestClient(create_m0702_app()).post(
        "/v1/modules/M07-02/verify",
        content=b"{" + b"x" * (8 * 1024 * 1024 - 8) + b"}",
    )
    assert response.status_code != HTTPStatus.REQUEST_ENTITY_TOO_LARGE
