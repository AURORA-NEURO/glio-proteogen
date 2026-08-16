"""Frozen M22-01 caller-declared reference-truth fixture adapter."""

from __future__ import annotations

from tests.adversarial.test_m2201_adversarial import _request

from glio_proteogen.contracts.m22_01 import (
    AdjudicationStatus,
    CurateProteinRnaDiscordanceReferenceTruthRequest,
)


def build_request() -> CurateProteinRnaDiscordanceReferenceTruthRequest:
    """Return the frozen complete package request."""

    return _request()


def pending_request() -> CurateProteinRnaDiscordanceReferenceTruthRequest:
    """Return the frozen request with one non-locked adjudication."""

    request = build_request()
    pending = request.adjudications[0].model_copy(update={"status": AdjudicationStatus.REVIEWED})
    return request.model_copy(update={"adjudications": (pending, *request.adjudications[1:])})


__all__ = ["build_request", "pending_request"]
