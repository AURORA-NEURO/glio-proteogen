"""FastAPI entry point for M10-03."""

from .interfaces import create_m1003_app

app = create_m1003_app()

__all__ = ["app", "create_m1003_app"]
