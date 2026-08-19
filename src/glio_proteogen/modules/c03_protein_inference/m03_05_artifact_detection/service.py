"""Stateless application boundary for M03-05 artifact detection."""

from collections.abc import Mapping
from typing import Final, cast

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m03_05 import (
    M0305_MAX_CANONICAL_RESULT_BYTES,
    DetectProteinInferenceArtifactsRequest,
    ProteinInferenceArtifactDetectionResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_05_artifact_detection.engine import (
    M0305ProteinInferenceArtifactEngine,
    preflight_protein_inference_artifact_authorization,
    prepare_artifact_request_candidate,
)

_REQUEST_ADAPTER: Final = TypeAdapter(DetectProteinInferenceArtifactsRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinInferenceArtifactDetectionResult)
_MAX_REPLAY_DEPTH: Final = 64
_MAX_REPLAY_DICT_ITEMS: Final = 512
_MAX_REPLAY_SEQUENCE_ITEMS: Final = 512
_MAX_REPLAY_NODES: Final = 250_000


class _ResultSizeError(ValueError):
    """Raised when a canonical result exceeds the public result ceiling."""

    def __init__(self) -> None:
        super().__init__("M03-05 result exceeds its canonical byte limit")


class _InvalidReplayValueError(TypeError):
    def __init__(self) -> None:
        super().__init__("M03-05 replay values require bounded built-in containers")


def _charge_replay_bytes(budget: list[int], value: str) -> None:
    budget[0] -= len(value.encode("utf-8")) + 2
    if budget[0] < 0:
        raise _InvalidReplayValueError


def _plain_replay_value(  # noqa: C901, PLR0912 - exact built-in traversal firewall.
    candidate: object,
    *,
    _depth: int = 0,
    _budget: list[int] | None = None,
    _byte_budget: list[int] | None = None,
) -> object:
    """Materialize only bounded built-in containers for result replay."""

    if _depth > _MAX_REPLAY_DEPTH:
        raise _InvalidReplayValueError
    budget = [_MAX_REPLAY_NODES] if _budget is None else _budget
    byte_budget = [M0305_MAX_CANONICAL_RESULT_BYTES] if _byte_budget is None else _byte_budget
    budget[0] -= 1
    if budget[0] < 0:
        raise _InvalidReplayValueError
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if BaseModel in candidate_mro:
        return candidate
    if dict in candidate_mro:
        mapping = cast("dict[object, object]", candidate)
        if dict.__len__(mapping) > _MAX_REPLAY_DICT_ITEMS:
            raise _InvalidReplayValueError
        result: dict[str, object] = {}
        for key in dict.keys(mapping):
            if type(key) is not str:
                raise _InvalidReplayValueError
            _charge_replay_bytes(byte_budget, key)
            result[key] = _plain_replay_value(
                dict.__getitem__(mapping, key),
                _depth=_depth + 1,
                _budget=budget,
                _byte_budget=byte_budget,
            )
        return result
    if list in candidate_mro:
        list_values = cast("list[object]", candidate)
        if list.__len__(list_values) > _MAX_REPLAY_SEQUENCE_ITEMS:
            raise _InvalidReplayValueError
        return [
            _plain_replay_value(
                item,
                _depth=_depth + 1,
                _budget=budget,
                _byte_budget=byte_budget,
            )
            for item in list.__iter__(list_values)
        ]
    if tuple in candidate_mro:
        tuple_values = cast("tuple[object, ...]", candidate)
        if tuple.__len__(tuple_values) > _MAX_REPLAY_SEQUENCE_ITEMS:
            raise _InvalidReplayValueError
        return tuple(
            _plain_replay_value(
                item,
                _depth=_depth + 1,
                _budget=budget,
                _byte_budget=byte_budget,
            )
            for item in tuple.__iter__(tuple_values)
        )
    if Mapping in candidate_mro or isinstance(candidate, Mapping):
        raise _InvalidReplayValueError
    if type(candidate) is str:
        _charge_replay_bytes(byte_budget, candidate)
    return candidate


def _bounded_result_bytes(value: object) -> bytes:
    """Canonicalize one result while enforcing every ingress shape's ceiling."""

    payload: bytes = canonical_json_bytes(_plain_replay_value(value))
    if len(payload) > M0305_MAX_CANONICAL_RESULT_BYTES:
        raise _ResultSizeError
    return payload


class M0305Service:
    """Authorize and strictly validate one metadata-only artifact request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0305ProteinInferenceArtifactEngine | None = None) -> None:
        self._engine = engine or M0305ProteinInferenceArtifactEngine()

    @staticmethod
    def validate_request(request: object) -> DetectProteinInferenceArtifactsRequest:
        preflight_protein_inference_artifact_authorization(request)
        candidate = prepare_artifact_request_candidate(request)
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)

    def execute(self, request: object) -> ProteinInferenceArtifactDetectionResult:
        return self._engine.detect(request)

    def verify(self, result: object) -> ProteinInferenceArtifactDetectionResult:
        """Replay-verify one stored M03-05 result through its closed envelope.

        The result contract recomputes the signal matrix, categorical reduction,
        contamination flags, exclusion mask, findings, support, provenance,
        evidence index, and digest from the embedded request.  This method is a
        bounded, duplicate-safe ingress for that verifier so API, CLI, and
        library callers share the same replay path.
        """

        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(result, max_bytes=M0305_MAX_CANONICAL_RESULT_BYTES)
            return _RESULT_ADAPTER.validate_json(_bounded_result_bytes(decoded), strict=True)
        if isinstance(result, Mapping):
            return _RESULT_ADAPTER.validate_json(
                _bounded_result_bytes(result),
                strict=True,
            )
        return _RESULT_ADAPTER.validate_json(
            _bounded_result_bytes(result),
            strict=True,
        )


__all__ = ["M0305Service"]
