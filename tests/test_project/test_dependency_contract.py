from pathlib import Path


def test_pydantic_floor_supports_model_serialization_features() -> None:
    pyproject = Path("pyproject.toml").read_text()

    assert '"pydantic>=2.12"' in pyproject


def test_gateway_dockerfile_uses_supported_pydantic_floor() -> None:
    dockerfile = Path("docker/gateway.Dockerfile").read_text()

    assert '"pydantic>=2.12"' in dockerfile
