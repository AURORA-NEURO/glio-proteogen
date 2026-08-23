"""Uvicorn entry point for container and process deployments."""

import sys
from pathlib import Path

import uvicorn

if __package__ in {None, ""}:
    _SOURCE_ROOT = Path(__file__).resolve().parents[1]
    if str(_SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(_SOURCE_ROOT))

from glio_proteogen.deployment import DeploymentSettings, create_deployment_app

app = create_deployment_app()


def main() -> None:
    """Serve the application using the resolved deployment environment."""

    settings = DeploymentSettings.from_environment()
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    main()


__all__ = ["app", "main"]
