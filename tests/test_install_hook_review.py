"""Install-hook review is an exact-content owner decision, not a blanket waiver."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

spec = importlib.util.spec_from_file_location(
    "install_hook_review", Path(__file__).parents[1] / ".github/scripts/verify_install_hook_review.py",
)
review_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review_module)
HEAD = "a" * 40
FILES = {"setup.py": "b" * 64}


def owner_review(**changes):
    review = {"head_sha": HEAD, "files": FILES, "disposition": "reviewed-install-hook-only",
              "reason": "Reviewed the exact packaging hook; only declared skill data files are collected."}
    review.update(changes)
    return {"user": {"login": "owner", "type": "User"}, "author_association": "OWNER",
            "body": review_module.MARKER + "\n" + json.dumps(review)}


def accepted(comments, files=None):
    return review_module.reviewed_by_owner(comments, "owner/repo", HEAD, FILES if files is None else files)


def test_explicit_owner_review_of_exact_bytes_is_accepted():
    assert accepted([owner_review()])


@pytest.mark.parametrize("changes", [
    {"head_sha": "c" * 40}, {"files": {"setup.py": "c" * 64}},
    {"files": {}}, {"files": dict(FILES, **{"setup.cfg": "d" * 64})},
    {"disposition": "reviewed-everything"}, {"reason": "ok"},
])
def test_stale_incomplete_or_broad_reviews_fail_closed(changes):
    assert not accepted([owner_review(**changes)])


@pytest.mark.parametrize("login,kind,association", [
    ("contributor", "User", "CONTRIBUTOR"), ("owner", "Bot", "OWNER"),
    ("owner", "User", "COLLABORATOR"), ("other-owner", "User", "OWNER"),
])
def test_labels_bots_and_non_owner_comments_cannot_authorize(login, kind, association):
    comment = owner_review()
    comment.update(user={"login": login, "type": kind}, author_association=association)
    assert not accepted([comment])


def test_malformed_duplicate_or_missing_review_is_rejected():
    assert not accepted([])
    assert not accepted([{"labels": ["reviewed"]}])
    for body in ["reviewed", review_module.MARKER + "\n{", review_module.MARKER +
                 '\n{"head_sha":"' + HEAD + '","head_sha":"' + HEAD + '"}']:
        comment = owner_review()
        comment["body"] = body
        assert not accepted([comment])


def test_content_changes_require_another_review():
    assert not accepted([owner_review()], {"setup.py": "c" * 64})


def test_hook_hash_is_from_real_git_blob_not_dirty_worktree(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    original = b"from setuptools import setup\nsetup()\n"
    (tmp_path / "setup.py").write_bytes(original)
    subprocess.run(["git", "-C", str(tmp_path), "add", "setup.py"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                    "commit", "-qm", "fixture"], check=True)
    head = subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True).strip()
    (tmp_path / "setup.py").write_text("changed working tree")
    monkeypatch.chdir(tmp_path)
    assert review_module.hook_hashes(head, ["setup.py"]) == {"setup.py": hashlib.sha256(original).hexdigest()}
    with pytest.raises(ValueError):
        review_module.hook_hashes(head, ["../setup.py"])
