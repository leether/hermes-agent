"""Shipped git MCP entries must name immutable code and bounded local bootstrap."""
from pathlib import Path
import re
import shlex

from packaging.requirements import Requirement
import pytest
import yaml

ROOT = Path(__file__).parents[2]
MANIFESTS = sorted((ROOT / "optional-mcps").glob("*/manifest.yaml"))


@pytest.mark.parametrize("manifest", MANIFESTS, ids=lambda p: p.parent.name)
def test_bundled_git_install_is_immutable_and_project_local(manifest):
    data = yaml.safe_load(manifest.read_text())
    install = data.get("install")
    if not install:
        assert data["transport"]["type"] == "http"
        assert data["transport"]["url"].startswith("https://")
        return
    assert re.fullmatch(r"[0-9a-f]{40}", install["ref"])
    commands = [shlex.split(command) for command in install["bootstrap"]]
    assert commands[0][:2] == ["uv", "venv"]
    assert "--python" in commands[0] and commands[0][-1] == ".venv"
    assert commands[1][:5] == ["uv", "pip", "install", "--python", ".venv/bin/python"]
    for dependency in commands[1][5:]:
        requirement = Requirement(dependency)
        assert requirement.url is None
        assert any(item.operator in {"<", "<=", "==", "~="} for item in requirement.specifier)
    assert data["transport"]["command"] == "${INSTALL_DIR}/.venv/bin/python"
    assert data["transport"]["args"] == ["${INSTALL_DIR}/server.py"]
