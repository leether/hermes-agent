"""The real matrix controller output reaches the native test consumers."""
import json

import pytest

from tests.ci import _gha_expr as gha
from tests.ci import test_update_ci_routing as routing


@pytest.mark.parametrize("repository,slices", [
    ("leether/hermes-agent", {"1/2", "2/2"}),
    ("NousResearch/hermes-agent", {None}),
])
def test_real_matrix_output_reaches_the_jobs(repository, slices):
    workflow = ".github/workflows/tests-os.yml"
    inputs = routing._inputs_for(workflow, {})
    run = routing._run_workflow(workflow, inputs=inputs, repository=repository)
    node = run["os-tests"]
    matrix = gha.render(node["body"]["strategy"]["matrix"], node["ctx"])
    assert matrix == json.loads(run["os-matrix"]["outputs"]["matrix"])
    windows = [row for row in matrix["include"]
               if row["marker"] == "windows" and "arm64" not in row["name"]]
    assert {row.get("slice") for row in windows} == slices
    assert len(windows) == len(slices)
    assert any("arm64" in row["name"] for row in matrix["include"])
    assert any(row["marker"] == "macos" for row in matrix["include"])
