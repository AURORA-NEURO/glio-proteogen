"""Static checks for the production container contract."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]


def test_docker_image_uses_configurable_startup_and_non_root_runtime() -> None:
    dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")
    entrypoint = (REPOSITORY_ROOT / "docker-entrypoint.sh").read_text(encoding="utf-8")

    assert "COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh" in dockerfile
    assert "USER glio" in dockerfile
    assert "docker inspect --format '{{.Config.User}}' glio-proteogen-ci" in (
        REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")
    assert "HEALTHCHECK" in dockerfile
    assert "/data/glio-proteogen" in dockerfile
    assert "exec python -m glio_proteogen.asgi" in entrypoint
    assert "uvicorn" not in entrypoint


def test_compose_preserves_persistence_and_container_hardening() -> None:
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "glio-proteogen-data:/data/glio-proteogen" in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "CMD-SHELL" in compose
    assert "/readyz" in compose


def test_backend_build_context_excludes_generated_and_frontend_trees() -> None:
    exclusions = set((REPOSITORY_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines())

    assert {
        ".coverage*",
        ".tmp-*",
        "coverage*.json",
        "coverage*.xml",
        "current-candidate-receipt.json",
        "module-validation.json",
        "research-state-performance.json",
        "*.junit.xml",
        "ui",
    } <= exclusions


def test_ci_container_smoke_checks_the_persistent_database_volume() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "--volume glio-proteogen-ci-data:/data/glio-proteogen" in workflow
    assert "--volumes-from glio-proteogen-ci" in workflow
    assert "events.sqlite3').is_file()" in workflow
    assert "State.Health.Status" in workflow
    assert "= healthy" in workflow
    assert "/v1/deployment/catalog" in workflow
    assert "catalog['unmounted_route_limit_prefixes'] == []" in workflow
    assert "catalog['catalog_digest']" in workflow
    assert "/v1/modules/M26-01/schemas/request" in workflow
    assert "/v1/modules/M23-02/schemas/request" in workflow
    assert "/v1/modules/M25-08/schemas/request" in workflow
    assert "/v1/contracts/M27-02/output/schema" in workflow
    assert "docker volume rm --force glio-proteogen-ci-data" in workflow


def test_ci_enforces_the_concrete_model_coverage_gate() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "model-quality:" in workflow
    assert "coverage run --branch" in workflow
    assert "--fail-under=100" in workflow
    assert "test_deployed_model_routes.py" in workflow
    assert "m27_02|m2702" in workflow
    assert "m24_04|m2404" in workflow
    assert "m24_04_external_transport_evaluator/api.py" in workflow
    assert "contracts/m27_02/v1.py" in workflow
    assert "contracts/m24_08/*.py" in workflow
    assert "contracts/m27_03/*.py" in workflow
    assert "contracts/m25_04/*.py" in workflow
    assert "contracts/m25_06/*.py" in workflow
    assert "contracts/m27_07/*.py" in workflow
    assert "contracts/m27_08/*.py" in workflow
    assert "contracts/m27_05/*.py" in workflow
    assert "contracts/m27_06/*.py" in workflow
    assert "--fail-under=100 --include=src/glio_proteogen/contracts/m27_05/*.py" in workflow
    assert (
        "--fail-under=100 --include=src/glio_proteogen/modules/"
        "c20_biomarker_panel/m26_01_registry_configuration_service/api.py"
    ) in workflow
    assert (
        "--fail-under=100 --include=src/glio_proteogen/modules/"
        "c21_reference_material/m23_01_reference_truth_benchmark_curator/api.py"
    ) in workflow


def test_ci_enforces_deployment_branch_coverage() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "deployment-quality:" in workflow
    assert "tests/deployment/test_asgi.py" in workflow
    assert "--fail-under=100 --include=src/glio_proteogen/deployment.py" in workflow


def test_full_test_jobs_execute_the_repository_suite() -> None:
    ci_workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    release_workflow = (
        REPOSITORY_ROOT / ".github" / "workflows" / "release-evidence.yml"
    ).read_text(encoding="utf-8")

    assert "git ls-files tests \\" in ci_workflow
    assert 'uv run pytest "${selected_files[@]}" \\' in ci_workflow
    assert "diff -u expected-test-files.txt actual-test-files.txt" in ci_workflow
    assert "coverage combine --keep test-shards/test-shard-*" in ci_workflow
    assert "coverage report --fail-under=95" in ci_workflow
    assert "uv run pytest tests \\\n" in release_workflow
    assert "--junitxml=evidence/tests.junit.xml" in release_workflow
    assert "--cov-report=xml:evidence/coverage.xml" in release_workflow
