from pathlib import Path
import yaml
import pytest


def test_render_yaml_structure_and_constraints() -> None:
    """Validate render.yaml configuration matches deployment constraints."""
    render_file = Path("render.yaml")
    assert render_file.exists(), "render.yaml must exist at the project root"

    with open(render_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    assert "services" in config, "render.yaml must define 'services'"
    services = config["services"]
    assert len(services) >= 1, "render.yaml must contain at least one service"

    web_svc = next((s for s in services if s.get("type") == "web"), None)
    assert web_svc is not None, "render.yaml must define a 'web' service"

    # Runtime and build command checks
    assert web_svc.get("runtime") == "python"
    build_cmd = web_svc.get("buildCommand", "")
    assert "download.pytorch.org/whl/cpu" in build_cmd, "Build command must specify CPU-only PyTorch index"
    assert "requirements.txt" in build_cmd, "Build command must install requirements.txt"

    # Start command checks
    start_cmd = web_svc.get("startCommand", "")
    assert "$PORT" in start_cmd or "${PORT}" in start_cmd, "Start command must bind to Render's $PORT"
    assert "--workers 1" in start_cmd, "Start command must enforce a single worker to limit memory usage"
    assert "app.main:app" in start_cmd, "Start command must point to app.main:app"

    # Health check path
    assert web_svc.get("healthCheckPath") == "/health", "Health check path must be '/health'"

    # Required environment variables
    env_vars = {item["key"]: item.get("value") for item in web_svc.get("envVars", [])}
    assert "APP_ENV" in env_vars
    assert env_vars["APP_ENV"] == "production"
    assert "APP_MODE" in env_vars
    assert env_vars["APP_MODE"] == "authenticated"
    assert "DEMO_MODE" in env_vars
    assert env_vars["DEMO_MODE"] == "false"
    assert "EMBEDDING_MODEL" in env_vars
    assert env_vars["EMBEDDING_MODEL"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert "MONGODB_URI" in env_vars
    assert "DATABASE_NAME" in env_vars


def test_runtime_dependencies_declared() -> None:
    """Ensure all required production runtime dependencies are present in requirements.txt."""
    req_file = Path("requirements.txt")
    assert req_file.exists()

    with open(req_file, "r", encoding="utf-8") as f:
        req_lines = [line.strip().lower() for line in f if line.strip() and not line.startswith("#")]

    required_packages = [
        "fastapi",
        "uvicorn",
        "pymongo",
        "dnspython",
        "pydantic",
        "pydantic-settings",
        "pillow",
        "sentence-transformers",
        "jinja2",
        "python-multipart",
        "email-validator",
    ]

    for pkg in required_packages:
        found = any(line.startswith(pkg) for line in req_lines)
        assert found, f"Required dependency '{pkg}' must be declared in requirements.txt"
