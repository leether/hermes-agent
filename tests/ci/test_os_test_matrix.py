"""Native CI capacity keeps OS coverage and scopes free-runner sharding exactly."""
import json

import pytest

from scripts.ci.os_test_matrix import FORK_REPOSITORY, build_matrix, main
from scripts.run_tests_parallel import _slice_files


def x64_rows(repository):
    return [row for row in build_matrix(repository)["include"]
            if row["marker"] == "windows" and "arm64" not in row["name"]]


def test_fork_slices_cover_the_whole_native_file_set_once(tmp_path):
    files = [tmp_path / "tests" / f"case_{index}.py" for index in range(9)]
    rows = x64_rows(FORK_REPOSITORY)
    groups = []
    for row in rows:
        index, count = map(int, row["slice"].split("/"))
        assert row["runner"] == "windows-latest"
        assert row.get("timeout", 30) == 30
        groups.append(_slice_files(files, index, count, {}, tmp_path))
    assert len(groups) == 2
    assert all(groups)
    flattened = [path for group in groups for path in group]
    assert set(flattened) == set(files)
    assert len(flattened) == len(set(flattened))


@pytest.mark.parametrize("repository", [
    "NousResearch/hermes-agent", "another/hermes-agent", "leether/hermes-agent-copy",
])
def test_other_repositories_keep_one_unsliced_x64_lane(repository):
    rows = x64_rows(repository)
    assert len(rows) == 1
    assert rows[0]["name"] == "Windows-only tests"
    assert rows[0]["runner"] == "windows-latest-32-core"
    assert not rows[0].get("slice")
    assert rows[0].get("timeout", 30) == 30


def test_mac_and_arm_keep_their_original_partition_and_budgets():
    fork = build_matrix(FORK_REPOSITORY)["include"]
    upstream = build_matrix("NousResearch/hermes-agent")["include"]
    assert [row for row in fork if row["marker"] == "macos"] == [
        row for row in upstream if row["marker"] == "macos"]
    for rows, runner in [(fork, "windows-11-arm"), (upstream, "windows-latest-32-arm-core")]:
        arm = next(row for row in rows if "arm64" in row["name"])
        assert arm["runner"] == runner
        assert arm["timeout"] == 60
        assert not arm.get("slice")
        assert len({row["name"] for row in rows}) == len(rows)


def test_cli_emits_a_single_json_matrix_for_the_workflow(capsys):
    assert main(["--repository", FORK_REPOSITORY]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    matrix = json.loads(output.out)
    assert isinstance(matrix["include"], list)
    assert all(row.get("name") and row.get("runner") and row.get("marker")
               for row in matrix["include"])


@pytest.mark.parametrize("repository", ["", "owner", "owner/repo/extra", "owner/repo\nextra"])
def test_malformed_repository_fails_closed(repository):
    with pytest.raises(ValueError, match="repository"):
        build_matrix(repository)
