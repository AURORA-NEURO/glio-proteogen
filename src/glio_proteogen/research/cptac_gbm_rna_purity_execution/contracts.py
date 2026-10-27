"""Closed execution policy and canonical bindings for the existing purity model."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Final, Literal

from pydantic import field_validator

from glio_proteogen.kernel.models import FrozenModel

PROFILE_ID: Final = "cptac-gbm-native-star-purity-execution/1.0.0"


class ExecutionError(ValueError):
    """A sanitized source qualification or frozen inference binding failure."""


def canonical_bytes(value: object) -> bytes:
    """Encode finite JSON with one deterministic representation."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def validate_digest(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise ExecutionError("execution digest is invalid")
    return value


class ExecutionPolicy(FrozenModel):
    """Operational research declarations, separately bound from clinical evidence."""

    schema_version: Literal["cptac-gbm-rna-purity-execution-policy/1.0.0"] = (
        "cptac-gbm-rna-purity-execution-policy/1.0.0"
    )
    model_id: Literal["gbmpurity-primary-idhwt-rna/1.0.0"] = "gbmpurity-primary-idhwt-rna/1.0.0"
    model_profile_id: Literal["gbm-rna-tumor-purity/1.0.0"] = "gbm-rna-tumor-purity/1.0.0"
    research_use_only: Literal[True]
    caller_authorizes_missing_gene_zero_fill: Literal[True]
    allow_limited_support: bool
    individual_prediction_export: Literal[False] = False
    redistribution_status: Literal["local_only_terms_unverified"] = "local_only_terms_unverified"

    @field_validator(
        "research_use_only",
        "caller_authorizes_missing_gene_zero_fill",
        "allow_limited_support",
        "individual_prediction_export",
        mode="before",
    )
    @staticmethod
    def literal_booleans_are_not_integer_aliases(value: object) -> object:
        if type(value) is not bool:
            raise ValueError("execution policy declarations must be boolean")
        return value


def checked_policy(policy: ExecutionPolicy) -> ExecutionPolicy:
    """Revalidate Python callers including bypassed or subsequently corrupted objects."""
    if type(policy) is not ExecutionPolicy:
        raise ExecutionError("an exact execution policy is required")
    try:
        return ExecutionPolicy.model_validate(policy.model_dump(mode="python"), strict=True)
    except (AttributeError, TypeError, ValueError):
        raise ExecutionError("execution policy declarations are invalid") from None


__all__ = [
    "PROFILE_ID",
    "ExecutionError",
    "ExecutionPolicy",
    "canonical_bytes",
    "checked_policy",
    "digest",
    "validate_digest",
]
