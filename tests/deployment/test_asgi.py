"""Production ASGI configuration and probe behavior."""

from __future__ import annotations

import importlib
import json
import os
import runpy
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.error import URLError
from urllib.request import Request, urlopen

import pytest
from fastapi.testclient import TestClient

from glio_proteogen import deployment as deployment_module
from glio_proteogen.adapters import api as api_module
from glio_proteogen.deployment import DeploymentSettings, create_deployment_app
from tests.m01_01_support import FIXTURE_DIRECTORY, load_json

if TYPE_CHECKING:
    from collections.abc import Iterator

HTTP_OK = 200
TEST_PORT = 8123


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@contextmanager
def _running_asgi_process(
    database: Path, port: int, *, repository_root: Path
) -> Iterator[subprocess.Popen[str]]:
    environment = os.environ.copy()
    environment.update(
        {
            "GLIO_PROTEOGEN_DATABASE_PATH": str(database),
            "GLIO_PROTEOGEN_HOST": "127.0.0.1",
            "GLIO_PROTEOGEN_PORT": str(port),
            "GLIO_PROTEOGEN_ENVIRONMENT": "test",
            "GLIO_PROTEOGEN_LOG_LEVEL": "warning",
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "glio_proteogen.asgi"],
        cwd=repository_root,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        yield process
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        if process.stderr is not None:
            process.stderr.read()


def _wait_for_http(process: subprocess.Popen[str], url: str) -> tuple[int, bytes]:
    deadline = time.monotonic() + 20
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read() if process.stderr is not None else ""
            raise AssertionError(  # noqa: TRY003
                f"ASGI process exited with {process.returncode}: {stderr}"
            )
        try:
            with urlopen(url, timeout=1) as response:  # noqa: S310 - loopback test URL.
                return response.status, response.read()
        except (URLError, TimeoutError, OSError) as error:
            last_error = error
            time.sleep(0.1)
    raise AssertionError(  # noqa: TRY003
        f"ASGI process did not serve {url}: {last_error}"
    )


def test_deployment_app_creates_storage_and_exposes_probes(tmp_path: Path) -> None:
    database = tmp_path / "nested" / "events.sqlite3"
    settings = DeploymentSettings(database_path=database, environment="test")
    app = create_deployment_app(settings)

    assert app.state.deployment["environment"] == "test"
    assert app.state.deployment["port"] == settings.port
    assert app.state.deployment["log_level"] == "info"

    with TestClient(app) as client:
        assert client.get("/livez").json() == {"status": "alive"}
        assert client.get("/healthz").json()["status"] == "alive"
        assert client.get("/readyz").status_code == HTTP_OK

    assert database.exists()


def test_deployment_catalog_reports_mounted_model_routes_and_limits(tmp_path: Path) -> None:
    app = create_deployment_app(
        DeploymentSettings(
            database_path=tmp_path / "catalog" / "events.sqlite3",
            environment="test",
        )
    )

    with TestClient(app) as client:
        response = client.get("/v1/deployment/catalog")

    assert response.status_code == HTTP_OK
    payload = response.json()
    assert payload["catalog_version"] == 1
    assert payload["catalog_digest"].startswith("sha256:")
    assert payload["environment"] == "test"
    assert payload["module_count"] == len(payload["modules"])
    assert payload["unmounted_route_limit_prefixes"] == []
    modules = {module["module_id"]: module for module in payload["modules"]}
    assert {"M23-01", "M25-08", "M26-02", "M27-02", "M28-04"} <= modules.keys()
    for module_id in ("M23-01", "M25-08", "M26-02", "M27-02", "M28-04"):
        module = modules[module_id]
        assert module["paths"]
        assert module["request_max_bytes"] > 0
        assert module["result_max_bytes"] > 0


def test_deployment_app_preserves_registered_protocol_across_restart(tmp_path: Path) -> None:
    database = tmp_path / "persistent" / "events.sqlite3"
    settings = DeploymentSettings(database_path=database, environment="test")
    registration = load_json(FIXTURE_DIRECTORY / "register_minimal.valid.json")

    with TestClient(create_deployment_app(settings)) as client:
        registered = client.post("/v1/modules/M01-01/protocols", json=registration)
        assert registered.status_code == HTTP_OK

    with TestClient(create_deployment_app(settings)) as client:
        lookup = client.get("/v1/modules/M01-01/protocols/protocol.synthetic/1.0.0")
        readiness = client.get("/readyz")

    assert lookup.status_code == HTTP_OK
    assert lookup.json() == registered.json()
    assert readiness.status_code == HTTP_OK


def test_asgi_process_serves_probes_and_protocol_route(tmp_path: Path) -> None:
    database = tmp_path / "process" / "events.sqlite3"
    port = _free_port()
    registration = load_json(FIXTURE_DIRECTORY / "register_minimal.valid.json")
    repository_root = Path(__file__).resolve().parents[2]

    with _running_asgi_process(database, port, repository_root=repository_root) as process:
        base_url = f"http://127.0.0.1:{port}"
        status, body = _wait_for_http(process, f"{base_url}/readyz")
        assert status == HTTP_OK
        assert b'"valid":true' in body

        with urlopen(  # noqa: S310 - loopback test URL.
            f"{base_url}/v1/modules/M26-01/schemas/request", timeout=5
        ) as response:
            assert response.status == HTTP_OK
            assert (
                json.loads(response.read())["x-glio-contract"]["moduleId"]
                == "GLIO-PROTEOGEN-M26-01"
            )

        request = Request(  # noqa: S310 - loopback test URL.
            f"{base_url}/v1/modules/M01-01/protocols",
            data=json.dumps(registration).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:  # noqa: S310 - loopback test URL.
            assert response.status == HTTP_OK

    assert database.exists()


def test_app_shutdown_closes_primary_store_when_identity_close_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    class PrimaryService:
        def __init__(self, _store: object) -> None:
            pass

        def close(self) -> None:
            calls.append("primary")

    class IdentityService:
        def __init__(self, _store: object) -> None:
            pass

        def close(self) -> None:
            calls.append("identity")
            raise RuntimeError("identity close failed")  # noqa: TRY003

    monkeypatch.setattr(api_module, "M0101Service", PrimaryService)
    monkeypatch.setattr(api_module, "M0102Service", IdentityService)

    with (
        pytest.raises(RuntimeError, match="identity close failed"),
        TestClient(
            create_deployment_app(
                DeploymentSettings(
                    database_path=tmp_path / "events.sqlite3",
                    environment="test",
                )
            )
        ),
    ):
        pass

    assert calls == ["identity", "primary"]


def test_deployment_settings_parse_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GLIO_PROTEOGEN_DATABASE_PATH", str(tmp_path / "events.sqlite3"))
    monkeypatch.setenv("GLIO_PROTEOGEN_PORT", str(TEST_PORT))
    monkeypatch.setenv("GLIO_PROTEOGEN_LOG_LEVEL", "WARNING")

    settings = DeploymentSettings.from_environment()

    assert settings.database_path == tmp_path / "events.sqlite3"
    assert settings.port == TEST_PORT
    assert settings.log_level == "warning"


def test_deployment_settings_reject_invalid_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GLIO_PROTEOGEN_PORT", "0")

    with pytest.raises(ValueError, match="GLIO_PROTEOGEN_PORT"):
        DeploymentSettings.from_environment()


def test_deployment_settings_reject_blank_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GLIO_PROTEOGEN_HOST", "   ")

    with pytest.raises(ValueError, match="GLIO_PROTEOGEN_HOST"):
        DeploymentSettings.from_environment()


def test_deployment_settings_reject_non_integer_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GLIO_PROTEOGEN_PORT", "eight-thousand")

    with pytest.raises(ValueError, match="must be an integer"):
        DeploymentSettings.from_environment()


def test_deployment_settings_reject_unknown_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GLIO_PROTEOGEN_LOG_LEVEL", "verbose")

    with pytest.raises(ValueError, match="must be one of"):
        DeploymentSettings.from_environment()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("host", "   ", "GLIO_PROTEOGEN_HOST"),
        ("environment", "   ", "GLIO_PROTEOGEN_ENVIRONMENT"),
        ("port", 0, "GLIO_PROTEOGEN_PORT"),
        ("port", 65_536, "GLIO_PROTEOGEN_PORT"),
        ("port", "8000", "must be an integer"),
        ("log_level", "verbose", "must be one of"),
    ],
)
def test_programmatic_deployment_settings_use_same_validation(
    field: str, value: object, message: str, tmp_path: Path
) -> None:
    values: dict[str, object] = {
        "database_path": tmp_path / "events.sqlite3",
        field: value,
    }

    with pytest.raises(ValueError, match=message):
        DeploymentSettings(**values)  # type: ignore[arg-type]


def test_programmatic_deployment_settings_require_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"pathlib\.Path"):
        DeploymentSettings(database_path=str(tmp_path / "events.sqlite3"))  # type: ignore[arg-type]


def test_deployment_rejects_unmounted_route_limits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setitem(deployment_module._MODEL_ROUTE_LIMITS, "/v1/modules/M99-99", (1, 2))
    with pytest.raises(ValueError, match="unmounted prefixes"):
        create_deployment_app(
            DeploymentSettings(database_path=tmp_path / "events.sqlite3", environment="test")
        )


def test_deployment_catalog_ignores_non_model_limit_prefix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(deployment_module, "_MODEL_ROUTE_LIMITS", {"/v1/internal": (1, 2)})
    monkeypatch.setattr(deployment_module, "_mounted_paths", lambda _app: {"/v1/internal"})
    app = create_deployment_app(
        DeploymentSettings(database_path=tmp_path / "events.sqlite3", environment="test")
    )

    with TestClient(app) as client:
        catalog = client.get("/v1/deployment/catalog").json()

    assert catalog["module_count"] == 0
    assert catalog["unmounted_route_limit_prefixes"] == []


def test_asgi_main_passes_resolved_settings_to_uvicorn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("GLIO_PROTEOGEN_DATABASE_PATH", str(tmp_path / "events.sqlite3"))
    asgi = importlib.import_module("glio_proteogen.asgi")
    settings = DeploymentSettings(
        database_path=tmp_path / "events.sqlite3",
        host="127.0.0.1",
        port=TEST_PORT,
        log_level="debug",
        environment="test",
    )
    monkeypatch.setattr(
        asgi.DeploymentSettings,
        "from_environment",
        classmethod(lambda _cls: settings),
    )
    captured: dict[str, object] = {}

    def fake_run(application: object, **kwargs: object) -> None:
        captured["application"] = application
        captured.update(kwargs)

    monkeypatch.setattr(asgi.uvicorn, "run", fake_run)

    asgi.main()

    assert captured == {
        "application": asgi.app,
        "host": "127.0.0.1",
        "port": TEST_PORT,
        "log_level": "debug",
    }


def test_asgi_file_execution_bootstraps_src_root(monkeypatch: pytest.MonkeyPatch) -> None:
    asgi = importlib.import_module("glio_proteogen.asgi")
    source = Path(asgi.__file__).resolve()
    source_root = source.parents[1]
    monkeypatch.setattr(sys, "path", [entry for entry in sys.path if entry != str(source_root)])

    namespace = runpy.run_path(str(source), run_name="asgi_probe")

    assert namespace["_SOURCE_ROOT"] == source_root
    assert namespace["app"] is not None
