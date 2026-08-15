"""M10-02 deterministic representation and feature-constructor runtime."""

from .engine import (
    M1002RepresentationEngine,
    RepresentationAuthorizationError,
    construct_protein_rna_representation,
    verify_result_replay,
)
from .plugin import (
    M1002Plugin,
    ValidatedM1002Request,
)
from .service import (
    M1002Service,
)

__all__ = [
    "M1002Plugin",
    "M1002RepresentationEngine",
    "M1002Service",
    "RepresentationAuthorizationError",
    "ValidatedM1002Request",
    "construct_protein_rna_representation",
    "verify_result_replay",
]
