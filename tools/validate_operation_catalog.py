"""Validate the v2 deployment catalog against the live FastAPI application.

The validator deliberately derives its expectations from mounted routes,
OpenAPI, and the installed transport middleware instead of reusing the catalog
builder.  This makes it a repository-native drift gate rather than a snapshot.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Final, cast

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from glio_proteogen.adapters.limits import MAX_REQUEST_BYTES, RequestSizeLimitMiddleware
from glio_proteogen.deployment import DeploymentSettings, create_deployment_app
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.gbm_functional_proteotype.demo import (
    DEMO_ID as FUNCTIONAL_PROTEOTYPE_DEMO_ID,
)
from glio_proteogen.research.gbm_master_kinases import DEMO_ID as MASTER_KINASE_DEMO_ID
from glio_proteogen.research.gbm_proteomic_axes import DEMO_ID as GBM_DEMO_ID
from glio_proteogen.research.gbm_rna_purity.demo import DEMO_ID as GBM_RNA_PURITY_DEMO_ID
from glio_proteogen.research.kncc_gbm_factor_graph.contracts import (
    DEMO_ID as FACTOR_GRAPH_DEMO_ID,
)
from glio_proteogen.research.longitudinal_gbm.demo import DEMO_ID as LONGITUDINAL_DEMO_ID
from glio_proteogen.research.longitudinal_gbm_complex_transition.demo import (
    DEMO_ID as LONGITUDINAL_COMPLEX_TRANSITION_DEMO_ID,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.demo import (
    DEMO_ID as LONGITUDINAL_KINASE_TRANSITION_DEMO_ID,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.demo import (
    DEMO_ID as LONGITUDINAL_NEFTEL_TRANSITION_DEMO_ID,
)
from glio_proteogen.research.longitudinal_gbm_phospho.demo import (
    DEMO_ID as LONGITUDINAL_PHOSPHO_DEMO_ID,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.demo import (
    DEMO_ID as LONGITUDINAL_REACTOME_TRANSITION_DEMO_ID,
)
from glio_proteogen.research.m14_microenvironment_protein_programs_facade import (
    DEMO_ID as M14_MICROENVIRONMENT_DEMO_ID,
)
from glio_proteogen.research.neftel_protein_programs import DEMO_ID as NEFTEL_DEMO_ID
from glio_proteogen.research.proteogenomic_state import DEMO_ID

if TYPE_CHECKING:
    from fastapi import FastAPI

_HTTP_METHODS: Final = frozenset(
    {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD", "TRACE"}
)
_MODULE_ID_PATTERN: Final = re.compile(r"M\d{2}-\d{2}", re.IGNORECASE)
_S3_FIRST_MODULE: Final = 21
_CATALOG_VERSION: Final = 2
_CATALOG_PATH: Final = "/v2/deployment/catalog"
_VALIDATED_EXAMPLES: Final = {
    "/v1/research/proteogenomic-state/analyze": DEMO_ID,
    "/v1/research/gbm-functional-proteotype/analyze": FUNCTIONAL_PROTEOTYPE_DEMO_ID,
    "/v1/research/gbm-proteomic-axes/analyze": GBM_DEMO_ID,
    "/v1/research/neftel-protein-programs/analyze": NEFTEL_DEMO_ID,
    "/v1/research/gbm-master-kinases/analyze": MASTER_KINASE_DEMO_ID,
    "/v1/research/gbm-rna-purity/analyze": GBM_RNA_PURITY_DEMO_ID,
    "/v1/research/longitudinal-gbm/analyze": LONGITUDINAL_DEMO_ID,
    "/v1/research/longitudinal-gbm-phospho/analyze": LONGITUDINAL_PHOSPHO_DEMO_ID,
    "/v1/research/longitudinal-gbm-kinase-transition/analyze": (
        LONGITUDINAL_KINASE_TRANSITION_DEMO_ID
    ),
    "/v1/research/longitudinal-gbm-neftel-transition/analyze": (
        LONGITUDINAL_NEFTEL_TRANSITION_DEMO_ID
    ),
    "/v1/research/longitudinal-gbm-reactome-transition/analyze": (
        LONGITUDINAL_REACTOME_TRANSITION_DEMO_ID
    ),
    "/v1/research/longitudinal-gbm-complex-transition/analyze": (
        LONGITUDINAL_COMPLEX_TRANSITION_DEMO_ID
    ),
    "/v1/research/gbm-factor-graph/analyze": FACTOR_GRAPH_DEMO_ID,
    "/v2/research/modules/m09/complex-transition-concordance/analyze": (
        LONGITUDINAL_COMPLEX_TRANSITION_DEMO_ID
    ),
    "/v2/research/modules/m10/functional-proteotype/analyze": (FUNCTIONAL_PROTEOTYPE_DEMO_ID),
    "/v2/research/modules/m11/protein-native-subtype/analyze": GBM_DEMO_ID,
    "/v2/research/modules/m14/microenvironment-protein-programs/analyze": (
        M14_MICROENVIRONMENT_DEMO_ID
    ),
    "/v2/research/modules/m15/longitudinal-recurrence-proteotype/analyze": (LONGITUDINAL_DEMO_ID),
}
_VALIDATED_EXAMPLE_FLOWS: Final = (
    (
        "/v1/research/proteogenomic-state/demo",
        "/v1/research/proteogenomic-state/analyze",
        "sample_id",
        DEMO_ID,
    ),
    (
        "/v1/research/gbm-functional-proteotype/demo",
        "/v1/research/gbm-functional-proteotype/analyze",
        "sample_id",
        FUNCTIONAL_PROTEOTYPE_DEMO_ID,
    ),
    (
        "/v1/research/gbm-proteomic-axes/demo",
        "/v1/research/gbm-proteomic-axes/analyze",
        "sample_id",
        GBM_DEMO_ID,
    ),
    (
        "/v1/research/neftel-protein-programs/demo",
        "/v1/research/neftel-protein-programs/analyze",
        "sample_id",
        NEFTEL_DEMO_ID,
    ),
    (
        "/v1/research/gbm-master-kinases/demo",
        "/v1/research/gbm-master-kinases/analyze",
        "sample_id",
        MASTER_KINASE_DEMO_ID,
    ),
    (
        "/v1/research/gbm-rna-purity/demo",
        "/v1/research/gbm-rna-purity/analyze",
        "sample_id",
        GBM_RNA_PURITY_DEMO_ID,
    ),
    (
        "/v1/research/longitudinal-gbm/demo",
        "/v1/research/longitudinal-gbm/analyze",
        "series_id",
        LONGITUDINAL_DEMO_ID,
    ),
    (
        "/v1/research/longitudinal-gbm-phospho/demo",
        "/v1/research/longitudinal-gbm-phospho/analyze",
        "series_id",
        LONGITUDINAL_PHOSPHO_DEMO_ID,
    ),
    (
        "/v1/research/longitudinal-gbm-kinase-transition/demo",
        "/v1/research/longitudinal-gbm-kinase-transition/analyze",
        "series_id",
        LONGITUDINAL_KINASE_TRANSITION_DEMO_ID,
    ),
    (
        "/v1/research/longitudinal-gbm-neftel-transition/demo",
        "/v1/research/longitudinal-gbm-neftel-transition/analyze",
        "series_id",
        LONGITUDINAL_NEFTEL_TRANSITION_DEMO_ID,
    ),
    (
        "/v1/research/longitudinal-gbm-reactome-transition/demo",
        "/v1/research/longitudinal-gbm-reactome-transition/analyze",
        "series_id",
        LONGITUDINAL_REACTOME_TRANSITION_DEMO_ID,
    ),
    (
        "/v1/research/longitudinal-gbm-complex-transition/demo",
        "/v1/research/longitudinal-gbm-complex-transition/analyze",
        "series_id",
        LONGITUDINAL_COMPLEX_TRANSITION_DEMO_ID,
    ),
    (
        "/v1/research/gbm-factor-graph/demo",
        "/v1/research/gbm-factor-graph/analyze",
        "analysis_id",
        FACTOR_GRAPH_DEMO_ID,
    ),
    (
        "/v2/research/modules/m09/complex-transition-concordance/demo",
        "/v2/research/modules/m09/complex-transition-concordance/analyze",
        "series_id",
        LONGITUDINAL_COMPLEX_TRANSITION_DEMO_ID,
    ),
    (
        "/v2/research/modules/m10/functional-proteotype/demo",
        "/v2/research/modules/m10/functional-proteotype/analyze",
        "sample_id",
        FUNCTIONAL_PROTEOTYPE_DEMO_ID,
    ),
    (
        "/v2/research/modules/m11/protein-native-subtype/demo",
        "/v2/research/modules/m11/protein-native-subtype/analyze",
        "sample_id",
        GBM_DEMO_ID,
    ),
    (
        "/v2/research/modules/m14/microenvironment-protein-programs/demo",
        "/v2/research/modules/m14/microenvironment-protein-programs/analyze",
        "sample_id",
        M14_MICROENVIRONMENT_DEMO_ID,
    ),
    (
        "/v2/research/modules/m15/longitudinal-recurrence-proteotype/demo",
        "/v2/research/modules/m15/longitudinal-recurrence-proteotype/analyze",
        "series_id",
        LONGITUDINAL_DEMO_ID,
    ),
)
_VALIDATED: Final = "validated"
_ABSTAINED: Final = "abstained"
_NO_BODY_REASON: Final = "operation_has_no_request_body"
_PRIOR_RESULT_REASON: Final = "requires_prior_operation_result"
_NO_FIXTURE_REASON: Final = "no_repository_validated_fixture"
_HTTP_OK: Final = 200
_RESEARCH_ROUTE_PREFIXES: Final = ("/v1/research/", "/v2/research/")


@dataclass(frozen=True, slots=True, order=True)
class OperationCatalogIssue:
    """One deterministic catalog validation finding."""

    operation: str
    message: str

    def render(self) -> str:
        """Render a stable, actionable validation message."""

        return f"{self.operation}: {self.message}"


class OperationCatalogValidationError(RuntimeError):
    """Raised when the catalog diverges from the mounted application."""

    def __init__(self, issues: Sequence[OperationCatalogIssue]) -> None:
        self.issues = tuple(sorted(issues))
        super().__init__("\n".join(issue.render() for issue in self.issues))


def _mounted_operations(app: FastAPI) -> tuple[tuple[str, str, APIRoute], ...]:
    routes: list[APIRoute] = []
    pending: list[object] = list(reversed(app.routes))
    while pending:
        route = pending.pop()
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            pending.extend(reversed(original_router.routes))
        elif isinstance(route, APIRoute):
            routes.append(route)

    operations = [
        (method, route.path, route)
        for route in routes
        for method in sorted(route.methods or set())
        if method in _HTTP_METHODS
    ]
    return tuple(sorted(operations, key=lambda item: (item[0], item[1])))


def _transport_configuration(
    app: FastAPI,
) -> tuple[int, int | None, Mapping[str, tuple[int, int | None]]]:
    for middleware in app.user_middleware:
        if cast("object", middleware.cls) is not RequestSizeLimitMiddleware:
            continue
        return (
            cast("int", middleware.kwargs.get("max_bytes", MAX_REQUEST_BYTES)),
            cast("int | None", middleware.kwargs.get("result_max_bytes")),
            cast(
                "Mapping[str, tuple[int, int | None]]",
                middleware.kwargs.get("route_limits", {}),
            ),
        )
    return MAX_REQUEST_BYTES, None, {}


def _effective_limits(app: FastAPI, path: str) -> tuple[int, int | None, bool, bool]:
    request_default, result_default, route_limits = _transport_configuration(app)
    matches = (
        (prefix, limits)
        for prefix, limits in route_limits.items()
        if path == prefix or path.startswith(f"{prefix}/")
    )
    selected = max(matches, key=lambda item: len(item[0]), default=None)
    if selected is None:
        return request_default, result_default, False, False
    request_limit, result_limit = selected[1]
    return request_limit, result_limit, True, path == selected[0]


def _safety_class(path: str) -> str:
    if path.startswith(_RESEARCH_ROUTE_PREFIXES):
        return "research-use-only"
    match = _MODULE_ID_PATTERN.search(path)
    if match is None:
        return "operational"
    return "S3" if int(match.group(0)[1:3]) >= _S3_FIRST_MODULE else "S2"


def _mutability_class(path: str, method: str) -> str:
    if method == "GET":
        return "read-only"
    lowered = path.lower()
    if lowered.endswith("/verify") or "replay" in lowered:
        return "verification"
    if path.startswith(_RESEARCH_ROUTE_PREFIXES):
        return "stateless-compute"
    return "bounded-execution"


def _example_metadata(
    path: str,
    *,
    request_body_present: bool,
    mutability_class: str,
) -> dict[str, str | None]:
    example_id = _VALIDATED_EXAMPLES.get(path)
    if example_id is not None:
        return {
            "validated_example_status": _VALIDATED,
            "validated_example_id": example_id,
            "validated_example_abstention_reason": None,
        }
    if not request_body_present:
        reason = _NO_BODY_REASON
    elif mutability_class == "verification":
        reason = _PRIOR_RESULT_REASON
    else:
        reason = _NO_FIXTURE_REASON
    return {
        "validated_example_status": _ABSTAINED,
        "validated_example_id": None,
        "validated_example_abstention_reason": reason,
    }


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[object]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _response_media_types(operation: Mapping[str, object]) -> list[str]:
    responses = _mapping(operation.get("responses"))
    media_types: set[str] = set()
    for response in responses.values():
        content = _mapping(_mapping(response).get("content"))
        media_types.update(str(media_type) for media_type in content)
    return sorted(media_types)


def _parameter_locations(
    path_document: Mapping[str, object], operation: Mapping[str, object]
) -> list[str]:
    parameters = (
        *_sequence(path_document.get("parameters")),
        *_sequence(operation.get("parameters")),
    )
    return sorted(
        {
            location
            for parameter in parameters
            if isinstance(parameter, Mapping) and isinstance((location := parameter.get("in")), str)
        }
    )


def _expected_operation(
    app: FastAPI,
    route: APIRoute,
    method: str,
    path: str,
    openapi: Mapping[str, object],
) -> tuple[dict[str, object], bool]:
    paths = _mapping(openapi.get("paths"))
    path_document = _mapping(paths.get(path))
    operation = _mapping(path_document.get(method.lower()))
    request_body = _mapping(operation.get("requestBody"))
    request_content = _mapping(request_body.get("content"))
    effective_request, effective_result, route_limits_declared, exact_route_limit = (
        _effective_limits(app, path)
    )
    request_limit = None
    if request_body:
        request_limit = (
            effective_result
            if path.lower().endswith("/verify")
            and effective_result is not None
            and not exact_route_limit
            else effective_request
        )
    mutability = _mutability_class(path, method)
    expected: dict[str, object] = {
        "operation_id": operation.get("operationId", route.name),
        "method": method,
        "path": path,
        "summary": operation.get("summary", route.summary),
        "tags": sorted(str(tag) for tag in route.tags),
        "request_media_types": sorted(str(media_type) for media_type in request_content),
        "response_media_types": _response_media_types(operation),
        "parameter_locations": _parameter_locations(path_document, operation),
        "request_max_bytes": request_limit,
        "result_max_bytes": effective_result if route_limits_declared else None,
        "safety_class": _safety_class(path),
        "mutability_class": mutability,
    }
    expected.update(
        _example_metadata(
            path,
            request_body_present=bool(request_body),
            mutability_class=mutability,
        )
    )
    return expected, bool(operation)


def _catalog_operations(
    catalog: Mapping[str, object], issues: list[OperationCatalogIssue]
) -> tuple[list[Mapping[str, object]], dict[tuple[str, str], Mapping[str, object]]]:
    raw_operations = catalog.get("operations")
    if not isinstance(raw_operations, list):
        issues.append(OperationCatalogIssue("catalog", "operations must be a list"))
        return [], {}
    operations: list[Mapping[str, object]] = []
    indexed: dict[tuple[str, str], Mapping[str, object]] = {}
    for index, value in enumerate(raw_operations):
        if not isinstance(value, Mapping):
            issues.append(OperationCatalogIssue(f"operations[{index}]", "must be an object"))
            continue
        operations.append(value)
        method = value.get("method")
        path = value.get("path")
        if not isinstance(method, str) or not isinstance(path, str):
            issues.append(
                OperationCatalogIssue(
                    f"operations[{index}]", "method and path must both be strings"
                )
            )
            continue
        key = (method, path)
        if key in indexed:
            issues.append(OperationCatalogIssue(f"{method} {path}", "duplicate catalog operation"))
        indexed[key] = value
    return operations, indexed


def _mounted_index(
    app: FastAPI,
) -> tuple[
    tuple[tuple[str, str, APIRoute], ...],
    dict[tuple[str, str], APIRoute],
    int,
]:
    mounted = _mounted_operations(app)
    mounted_index: dict[tuple[str, str], APIRoute] = {}
    for method, path, route in mounted:
        key = (method, path)
        # FastAPI dispatches the first matching route.  Repeated registrations
        # therefore describe one externally addressable operation, not two
        # catalog keys.  Count the shadows explicitly while validating against
        # the effective first registration used by the runtime.
        mounted_index.setdefault(key, route)
    return mounted, mounted_index, len(mounted) - len(mounted_index)


def _validate_coverage(
    catalog: Mapping[str, object],
    operations: Sequence[Mapping[str, object]],
    indexed: Mapping[tuple[str, str], Mapping[str, object]],
    mounted_index: Mapping[tuple[str, str], APIRoute],
    issues: list[OperationCatalogIssue],
) -> None:
    mounted_keys = set(mounted_index)
    catalog_keys = set(indexed)
    for method, path in sorted(mounted_keys - catalog_keys):
        issues.append(OperationCatalogIssue(f"{method} {path}", "missing from catalog"))
    for method, path in sorted(catalog_keys - mounted_keys):
        issues.append(OperationCatalogIssue(f"{method} {path}", "not mounted by FastAPI"))

    if catalog.get("operation_count") != len(operations):
        issues.append(OperationCatalogIssue("catalog", "operation_count does not match operations"))
    expected_order = sorted(catalog_keys)
    actual_order = [
        (str(operation.get("method")), str(operation.get("path"))) for operation in operations
    ]
    if actual_order != expected_order:
        issues.append(
            OperationCatalogIssue("catalog", "operations are not deterministically sorted")
        )


def _validate_metadata(
    app: FastAPI,
    indexed: Mapping[tuple[str, str], Mapping[str, object]],
    mounted_index: Mapping[tuple[str, str], APIRoute],
    issues: list[OperationCatalogIssue],
) -> None:
    mounted_keys = set(mounted_index)
    catalog_keys = set(indexed)

    openapi = _mapping(app.openapi())
    for key in sorted(mounted_keys & catalog_keys):
        method, path = key
        expected, documented = _expected_operation(app, mounted_index[key], method, path, openapi)
        label = f"{method} {path}"
        if not documented:
            issues.append(OperationCatalogIssue(label, "mounted operation is absent from OpenAPI"))
        actual = indexed[key]
        for field, expected_value in expected.items():
            if actual.get(field) != expected_value:
                issues.append(
                    OperationCatalogIssue(
                        label,
                        f"{field} is {actual.get(field)!r}; expected {expected_value!r}",
                    )
                )
        if expected["request_max_bytes"] is not None and not expected["request_media_types"]:
            issues.append(OperationCatalogIssue(label, "request body has no declared media type"))
        if not expected["response_media_types"]:
            issues.append(OperationCatalogIssue(label, "has no declared response media type"))


def _validation_report(
    operations: Sequence[Mapping[str, object]],
    mounted_registration_count: int,
    shadowed_registration_count: int,
    catalog_digest: str,
) -> dict[str, object]:
    method_counts = Counter(str(operation["method"]) for operation in operations)
    safety_counts = Counter(str(operation["safety_class"]) for operation in operations)
    request_media_counts = Counter(
        media_type
        for operation in operations
        for media_type in cast("Sequence[str]", operation["request_media_types"])
    )
    response_media_counts = Counter(
        media_type
        for operation in operations
        for media_type in cast("Sequence[str]", operation["response_media_types"])
    )
    example_status_counts = Counter(
        str(operation["validated_example_status"]) for operation in operations
    )
    abstention_reason_counts = Counter(
        str(reason)
        for operation in operations
        if (reason := operation["validated_example_abstention_reason"]) is not None
    )
    return {
        "valid": True,
        "catalog_digest": catalog_digest,
        "mounted_operation_count": mounted_registration_count - shadowed_registration_count,
        "mounted_route_registration_count": mounted_registration_count,
        "shadowed_route_registration_count": shadowed_registration_count,
        "catalog_operation_count": len(operations),
        "method_counts": dict(sorted(method_counts.items())),
        "safety_class_counts": dict(sorted(safety_counts.items())),
        "request_media_type_counts": dict(sorted(request_media_counts.items())),
        "response_media_type_counts": dict(sorted(response_media_counts.items())),
        "request_limit_declared_count": sum(
            operation["request_max_bytes"] is not None for operation in operations
        ),
        "result_limit_declared_count": sum(
            operation["result_max_bytes"] is not None for operation in operations
        ),
        "validated_example_status_counts": dict(sorted(example_status_counts.items())),
        "validated_example_abstention_reason_counts": dict(
            sorted(abstention_reason_counts.items())
        ),
    }


def validate_operation_catalog(app: FastAPI, catalog: Mapping[str, object]) -> dict[str, object]:
    """Validate catalog coverage and metadata, returning deterministic audit counts."""

    issues: list[OperationCatalogIssue] = []
    if catalog.get("catalog_version") != _CATALOG_VERSION:
        issues.append(OperationCatalogIssue("catalog", "catalog_version must be 2"))

    operations, indexed = _catalog_operations(catalog, issues)
    mounted, mounted_index, shadowed_count = _mounted_index(app)
    _validate_coverage(catalog, operations, indexed, mounted_index, issues)
    _validate_metadata(app, indexed, mounted_index, issues)
    expected_digest = sha256_digest({"operations": operations})
    if catalog.get("catalog_digest") != expected_digest:
        issues.append(OperationCatalogIssue("catalog", "catalog_digest does not match operations"))
    if issues:
        raise OperationCatalogValidationError(issues)
    return _validation_report(operations, len(mounted), shadowed_count, expected_digest)


def _load_json_response(
    response_status: int, response_body: object, label: str
) -> Mapping[str, object]:
    if response_status != _HTTP_OK:
        raise OperationCatalogValidationError(
            (OperationCatalogIssue(label, f"returned HTTP {response_status}"),)
        )
    if not isinstance(response_body, Mapping):
        raise OperationCatalogValidationError(
            (OperationCatalogIssue(label, "response must be a JSON object"),)
        )
    return response_body


def run_repository_validation(database_path: Path) -> dict[str, object]:
    """Build the production app and validate catalog determinism plus its demo fixture."""

    app = create_deployment_app(
        DeploymentSettings(database_path=database_path, environment="catalog-validation")
    )
    with TestClient(app) as client:
        first = client.get(_CATALOG_PATH)
        second = client.get(_CATALOG_PATH)
        catalog = _load_json_response(first.status_code, first.json(), _CATALOG_PATH)
        repeated = _load_json_response(second.status_code, second.json(), _CATALOG_PATH)
        if repeated != catalog:
            raise OperationCatalogValidationError(
                (OperationCatalogIssue(_CATALOG_PATH, "successive responses differ"),)
            )
        report = validate_operation_catalog(app, catalog)

        for demo_path, analyze_path, identity_field, example_id in _VALIDATED_EXAMPLE_FLOWS:
            demo_response = client.get(demo_path)
            demo = _load_json_response(
                demo_response.status_code,
                demo_response.json(),
                demo_path,
            )
            if demo.get(identity_field) != example_id:
                raise OperationCatalogValidationError(
                    (
                        OperationCatalogIssue(
                            demo_path,
                            f"{identity_field} does not match validated example",
                        ),
                    )
                )
            analyze_response = client.post(analyze_path, json=demo)
            _load_json_response(
                analyze_response.status_code,
                analyze_response.json(),
                analyze_path,
            )

    report["deterministic_replay_count"] = 2
    report["executed_validated_example_id"] = DEMO_ID
    report["executed_validated_example_ids"] = [
        example_id
        for _demo_path, _analyze_path, _identity_field, example_id in _VALIDATED_EXAMPLE_FLOWS
    ]
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.database is not None:
            report = run_repository_validation(args.database)
        else:
            with TemporaryDirectory(prefix="glio-catalog-") as directory:
                report = run_repository_validation(Path(directory) / "events.sqlite3")
    except OperationCatalogValidationError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
