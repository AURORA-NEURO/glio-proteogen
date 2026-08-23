from __future__ import annotations

import inspect
import re
from typing import TYPE_CHECKING, Any, get_args, get_origin

from fastapi.routing import APIRoute
from pydantic import TypeAdapter

if TYPE_CHECKING:
    from collections.abc import Iterable

    from fastapi import FastAPI

_HTTP_METHODS = frozenset({"POST", "PUT", "PATCH"})
_REQUEST_BODY_FALLBACK: dict[str, Any] = {
    "type": "object",
    "additionalProperties": True,
    "title": "JSON request",
}


def _routes(routes: Iterable[Any]) -> Iterable[APIRoute]:
    for route in routes:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            yield from _routes(original_router.routes)
        elif isinstance(route, APIRoute):
            yield route


def _schema_from_adapter(adapter: object) -> dict[str, Any] | None:
    if not isinstance(adapter, TypeAdapter):
        return None
    try:
        schema = adapter.json_schema()
    except (TypeError, ValueError):
        return None
    return schema if isinstance(schema, dict) else None


def _schema_from_annotation(endpoint: object) -> dict[str, Any] | None:
    if not callable(endpoint):
        return None
    try:
        annotations = inspect.get_annotations(endpoint, eval_str=True)
    except (NameError, TypeError, ValueError):
        return None
    for name, annotation in annotations.items():
        if name == "return" or name in {"request", "self"}:
            continue
        candidate_annotation = annotation
        if get_origin(annotation) is not None:
            args = get_args(annotation)
            if args:
                candidate_annotation = args[0]
        try:
            schema = TypeAdapter(candidate_annotation).json_schema()
        except (TypeError, ValueError):
            continue
        if isinstance(schema, dict):
            return schema
    return None


def _schema_from_globals(route: APIRoute) -> dict[str, Any] | None:
    endpoint = route.endpoint
    globals_map = getattr(endpoint, "__globals__", {})
    verify_route = "verify" in route.path.lower() or "replay" in route.path.lower()
    preferred_names = ("_RESULT_ADAPTER", "RESULT_ADAPTER") if verify_route else (
        "_REQUEST_ADAPTER",
        "REQUEST_ADAPTER",
    )
    for name in preferred_names:
        schema = _schema_from_adapter(globals_map.get(name))
        if schema is not None:
            return schema

    module_key_match = re.search(r"M(\d{2})[-_](\d{2})", route.path, re.IGNORECASE)
    module_key = "m" + "".join(module_key_match.groups()) if module_key_match else ""
    candidates: list[tuple[int, dict[str, Any]]] = []
    for name, value in globals_map.items():
        schema = _schema_from_adapter(value)
        if schema is None:
            continue
        normalized_name = re.sub(r"[^a-z0-9]", "", name.lower())
        if module_key and module_key not in normalized_name:
            continue
        score = 1
        if verify_route and "result" in normalized_name:
            score += 4
        if not verify_route and "request" in normalized_name:
            score += 4
        candidates.append((score, schema))
    if candidates:
        return max(candidates, key=lambda item: item[0])[1]
    return None


def _request_schema(route: APIRoute) -> dict[str, Any]:
    return (
        _schema_from_annotation(route.endpoint)
        or _schema_from_globals(route)
        or dict(_REQUEST_BODY_FALLBACK)
    )


def _enrich(schema: dict[str, Any], app: FastAPI) -> None:
    for route in _routes(app.routes):
        methods = {method.upper() for method in (route.methods or set())}
        if not methods.intersection(_HTTP_METHODS) or route.body_field is not None:
            continue
        for method in methods.intersection(_HTTP_METHODS):
            operation = schema.get("paths", {}).get(route.path, {}).get(method.lower())
            if not isinstance(operation, dict) or "requestBody" in operation:
                continue
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": _request_schema(route),
                    }
                },
            }


def install_request_body_openapi(app: FastAPI) -> None:
    original_openapi = app.openapi

    def openapi_with_request_bodies() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = original_openapi()
            _enrich(schema, app)
            app.openapi_schema = schema
        return app.openapi_schema

    app.__dict__["openapi"] = openapi_with_request_bodies


__all__ = ["install_request_body_openapi"]
