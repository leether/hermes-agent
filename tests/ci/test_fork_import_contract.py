"""A reviewed upstream import cannot hide new local risks or future regressions."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess

import pytest

from scripts.ci.fork_import_contract import (
    POLICY, ContractError, ImportPolicy, author_emails, blob_offenders,
    event_context, health_base, import_policy, main, supply_diff,
)


def git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo, text=True, encoding="utf-8", timeout=30).strip()


def commit(repo, message, email):
    git(repo, "add", ".")
    git(repo, "commit", "-qm", message, "--author", f"Test Author <{email}>")
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def imported(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "config", "commit.gpgsign", "false")
    git(repo, "config", "core.hooksPath", str(tmp_path / "empty-hooks"))
    (repo / "README").write_text("base\n", encoding="utf-8")
    base = commit(repo, "old fork", "old@example.invalid")
    (repo / "asset.bin").write_bytes(b"\0" + b"A" * (513 * 1024))
    (repo / "bootstrap.py").write_text("print('trusted fixture')\n", encoding="utf-8")
    upstream = commit(repo, "upstream", "upstream@example.invalid")
    (repo / "local.py").write_text("value = 1\n", encoding="utf-8")
    candidate = commit(repo, "local patch", "local@example.invalid")
    blobs = {name: git(repo, "rev-parse", f"{upstream}:{name}")
             for name in ("asset.bin", "bootstrap.py")}
    policy = ImportPolicy(POLICY.repository, POLICY.pull_request, base,
                          upstream, candidate, blobs, ("bootstrap.py",))
    return repo, policy


def resolved(imported):
    repo, policy = imported
    return import_policy(repo, policy.base, "HEAD", (policy.repository, policy.pull_request), policy)


def test_exact_import_keeps_local_authors_and_only_fixed_blob_exemptions(imported):
    repo, policy = imported
    active = resolved(imported)
    assert health_base(repo, policy.base, active) == policy.upstream
    assert author_emails(repo, policy.base, "HEAD", active) == "local@example.invalid"
    assert blob_offenders(repo, policy.base, active) == []
    assert "bootstrap.py" not in supply_diff(repo, policy.base, "HEAD", active)


@pytest.mark.parametrize("path", ["asset.bin", "bootstrap.py"])
def test_drift_even_below_size_cap_refuses_before_exemptions(imported, path):
    repo, _ = imported
    (repo / path).write_text("changed\n", encoding="utf-8")
    with pytest.raises(ContractError, match="content changed"):
        resolved(imported)


def test_committed_drift_cannot_be_hidden_by_restoring_only_worktree(imported):
    repo, _policy = imported
    original = (repo / "bootstrap.py").read_bytes()
    (repo / "bootstrap.py").write_text("changed\n", encoding="utf-8")
    commit(repo, "unreviewed change", "local@example.invalid")
    (repo / "bootstrap.py").write_bytes(original)
    with pytest.raises(ContractError, match="content changed"):
        resolved(imported)


@pytest.mark.parametrize("field", ["upstream", "candidate"])
def test_missing_fixed_objects_fail_closed(imported, field):
    repo, policy = imported
    wrong = replace(policy, **{field: "f" * 40})
    with pytest.raises(ContractError):
        import_policy(repo, policy.base, "HEAD", (policy.repository, policy.pull_request), wrong)


def test_unreviewed_expected_blob_is_not_accepted(imported):
    repo, policy = imported
    wrong = replace(policy, blobs={**policy.blobs, "asset.bin": "f" * 40})
    with pytest.raises(ContractError, match="content changed"):
        import_policy(repo, policy.base, "HEAD", (policy.repository, policy.pull_request), wrong)


@pytest.mark.parametrize("context", [("another/fork", 5), (POLICY.repository, 6)])
def test_other_prs_keep_original_blob_and_base_gates(imported, context):
    repo, policy = imported
    active = import_policy(repo, policy.base, "HEAD", context, policy)
    assert active is None
    assert health_base(repo, policy.base, active) == policy.base
    assert [item.path for item in blob_offenders(repo, policy.base, active)] == ["asset.bin"]


def test_next_main_baseline_cannot_reuse_the_old_import(imported):
    repo, policy = imported
    active = import_policy(repo, policy.candidate, "HEAD", (policy.repository, 5), policy)
    assert active is None
    assert health_base(repo, policy.candidate, active) == policy.candidate


def test_new_untracked_large_binary_still_blocks(imported):
    repo, policy = imported
    (repo / "new.bin").write_bytes(b"\0" + b"B" * (513 * 1024))
    assert [item.path for item in blob_offenders(repo, policy.base, resolved(imported))] == ["new.bin"]


def test_new_local_encoded_execution_reaches_original_scanner(imported):
    repo, policy = imported
    risk = "exec("
    risk += "base64.b64decode('unreviewed'))\n"
    (repo / "new_payload.py").write_text(risk, encoding="utf-8")
    commit(repo, "unreviewed risk fixture", "unknown@example.invalid")
    active = resolved(imported)
    assert risk.strip() in supply_diff(repo, policy.base, "HEAD", active)
    assert "unknown@example.invalid" in author_emails(repo, policy.base, "HEAD", active)


def test_context_admits_only_the_first_exact_main_push(tmp_path):
    event = tmp_path / "event.json"
    sha = "a" * 40
    event.write_text(json.dumps({"before": POLICY.base, "after": sha}), encoding="utf-8")
    env = {"GITHUB_REPOSITORY": POLICY.repository, "GITHUB_EVENT_NAME": "push",
           "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": sha, "GITHUB_EVENT_PATH": str(event)}
    assert event_context(env) == (POLICY.repository, 5)
    assert event_context({**env, "GITHUB_REF": "refs/heads/other"}) == (POLICY.repository, 0)
    event.write_text(json.dumps({"before": sha, "after": sha}), encoding="utf-8")
    assert event_context(env) == (POLICY.repository, 0)


@pytest.mark.parametrize("event", [[], {"number": "5"}, {"number": None}])
def test_malformed_pr_events_refuse_instead_of_enabling_import(tmp_path, monkeypatch, event):
    path = tmp_path / "event.json"
    path.write_text(json.dumps(event), encoding="utf-8")
    monkeypatch.setenv("GITHUB_REPOSITORY", POLICY.repository)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(path))
    assert main(["health-base", "--base", "HEAD"]) == 2


def test_security_review_does_not_grant_a_large_blob_exception(imported):
    repo, policy = imported
    (repo / "bootstrap.py").write_bytes(b"#" * (513 * 1024))
    revision = commit(repo, "large security fixture", "upstream@example.invalid")
    changed = replace(policy, upstream=revision, candidate=revision,
                      blobs={**policy.blobs, "bootstrap.py": git(repo, "rev-parse", f"{revision}:bootstrap.py")})
    active = import_policy(repo, policy.base, "HEAD", (policy.repository, policy.pull_request), changed)
    assert [item.path for item in blob_offenders(repo, policy.base, active)] == ["bootstrap.py"]


@pytest.mark.parametrize("field", ["upstream", "candidate"])
def test_existing_object_without_required_ancestry_refuses(imported, field):
    repo, policy = imported
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    foreign = git(repo, "commit-tree", tree, "-m", "unrelated fixture root")
    changed = replace(policy, **{field: foreign})
    with pytest.raises(ContractError):
        import_policy(repo, policy.base, "HEAD", (policy.repository, policy.pull_request), changed)
