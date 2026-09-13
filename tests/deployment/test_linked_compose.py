"""Static acceptance checks for the linked API/workbench deployment."""

import json
import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]
SERVICE_COUNT = 3
T3_NODE_STAGE_COUNT = 2


def test_backend_build_uses_the_locked_production_graph() -> None:
    dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "python:3.12.13-slim-bookworm" in dockerfile
    assert "ghcr.io/astral-sh/uv:0.11.14" in dockerfile
    assert "COPY pyproject.toml uv.lock README.md ./" in dockerfile
    assert "COPY THIRD_PARTY_NOTICES.md ./" in dockerfile
    assert "uv sync --locked --no-dev --no-editable" in dockerfile
    assert "COPY --from=builder /build/.venv /opt/glio-proteogen" in dockerfile


def test_every_ui_node_stage_is_digest_pinned() -> None:
    dockerfile = (REPOSITORY_ROOT / "ui" / "Dockerfile").read_text(encoding="utf-8")
    node_stages: set[str] = set()

    for line in dockerfile.splitlines():
        instruction = line.strip()
        if not instruction.upper().startswith("FROM NODE:"):
            continue
        match = re.fullmatch(
            r"FROM\s+(node:\S+)\s+AS\s+([a-z][a-z0-9_-]*)",
            instruction,
            flags=re.IGNORECASE,
        )
        assert match, f"UI Node stage is malformed or unnamed: {line}"
        image, stage = match.groups()
        image_name, separator, digest = image.partition("@sha256:")
        assert separator, f"UI Node stage {stage!r} is not digest-pinned"
        assert image_name == "node:24.14.0-alpine3.23"
        assert re.fullmatch(r"[0-9a-f]{64}", digest), (
            f"UI Node stage {stage!r} has an invalid SHA-256 digest"
        )
        node_stages.add(stage)

    assert node_stages == {"dependencies", "build", "runtime"}


def test_compose_links_ui_to_healthy_backend() -> None:
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "ui:" in compose
    assert '"127.0.0.1:3000:3000"' in compose
    assert '"127.0.0.1:8000:8000"' in compose
    assert '"127.0.0.1:3773:3773"' in compose
    assert "GLIO_API_URL: http://glio-proteogen:8000" in compose
    assert "GLIO_AUTH_DATABASE_PATH: /data/glio-auth/auth.sqlite3" in compose
    assert "T3_PAIRING_BROKER_URL: http://t3-code:3774/pairing" in compose
    assert "glio-proteogen-ui-auth:/data/glio-auth" in compose
    assert "glio-proteogen-t3-state:/data/t3" in compose
    assert ".:/workspace:ro" in compose
    assert "condition: service_healthy" in compose
    assert compose.count("read_only: true") == SERVICE_COUNT
    assert compose.count("no-new-privileges:true") == SERVICE_COUNT
    assert compose.count("- ALL") == SERVICE_COUNT
    assert "/healthz" in compose
    assert "/readyz" in compose


def test_t3_runtime_is_exactly_pinned_and_brokered() -> None:
    runtime_root = REPOSITORY_ROOT / "ui" / "t3"
    dockerfile = (runtime_root / "Dockerfile").read_text(encoding="utf-8")
    server = (runtime_root / "server.mjs").read_text(encoding="utf-8")
    package = json.loads((runtime_root / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((runtime_root / "package-lock.json").read_text(encoding="utf-8"))

    assert package["dependencies"] == {"t3": "0.0.35"}
    assert lock["packages"][""]["dependencies"] == {"t3": "0.0.35"}
    assert lock["packages"]["node_modules/t3"]["version"] == "0.0.35"
    assert lock["packages"]["node_modules/t3"]["integrity"] == (
        "sha512-8EsWqFFTFL7uHQfqhZgM6YEv7TFvciXtuy8PWw8uaJnPKhsFaJJGA/"
        "s5kPp3GPGtLIPJYhaMcthSJBYBkdw3KA=="
    )
    assert dockerfile.count("node:24.15.0-bookworm-slim@sha256:") == T3_NODE_STAGE_COUNT
    assert "node:latest" not in dockerfile
    assert "USER t3" in dockerfile
    assert "--shell /bin/sh t3" in dockerfile
    assert "/usr/sbin/nologin" not in dockerfile
    assert '"auth",\n      "pairing",\n      "create"' in server
    assert '"--base-dir",\n      baseDirectory' in server
    assert "allowExistingProject" in server
    assert "ProjectAlreadyExistsError" in server
    assert 'stdio: ["ignore", "ignore", "inherit"]' in server
    assert "pairing_unavailable" in server
    assert "latest" not in server
