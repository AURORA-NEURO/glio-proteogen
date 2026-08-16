"""FastAPI entry point for the provisional M10-02 interface."""

from .interfaces import create_m1002_app

app = create_m1002_app()

__all__ = ["app", "create_m1002_app"]
