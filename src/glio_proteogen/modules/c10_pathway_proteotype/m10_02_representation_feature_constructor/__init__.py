"""M10-02 deterministic representation and feature-constructor runtime."""

from .engine import (
    M1002RepresentationEngine,
    RepresentationAuthorizationError,
    construct_protein_rna_representation,
    verify_result_replay,
)
from .interfaces import app as cli_app
from .interfaces import create_m1002_app, export_schema
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
    "cli_app",
    "construct_protein_rna_representation",
    "create_m1002_app",
    "export_schema",
    "verify_result_replay",
]
