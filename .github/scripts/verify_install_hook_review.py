"""Verify an explicit repository-owner review of exact install-hook bytes.

This can discharge only install-hook findings. The workflow keeps all other
critical patterns blocking. A label or a PR-authored allowlist is insufficient.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess

MARKER = "<!-- hermes-install-hook-review:v1 -->"
HOOKS = frozenset({"setup.py", "setup.cfg", "sitecustomize.py", "usercustomize.py", "__init__.pth"})


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate review field")
        result[key] = value
    return result


def reviewed_by_owner(comments, repository, head_sha, files):
    """Require owner identity, exact head and the complete path/hash mapping."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        return False
    if not re.fullmatch(r"[0-9a-f]{40}", head_sha) or not files:
        return False
    if not set(files).issubset(HOOKS) or not all(
        isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v) for v in files.values()
    ):
        return False
    owner = repository.split("/", 1)[0].casefold()
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        user = comment.get("user") or {}
        if not isinstance(user, dict) or (
            str(user.get("login", "")).casefold() != owner
            or user.get("type") != "User"
            or comment.get("author_association") != "OWNER"
        ):
            continue
        body = comment.get("body")
        if not isinstance(body, str) or not body.startswith(MARKER + "\n"):
            continue
        try:
            review = json.loads(body[len(MARKER):], object_pairs_hook=_unique_keys)
        except (ValueError, TypeError):
            continue
        if not isinstance(review, dict):
            continue
        if (
            review.get("head_sha") == head_sha
            and review.get("files") == files
            and review.get("disposition") == "reviewed-install-hook-only"
            and isinstance(review.get("reason"), str)
            and 20 <= len(review["reason"].strip()) <= 4000
        ):
            return True
    return False


def hook_hashes(head_sha, paths):
    if not re.fullmatch(r"[0-9a-f]{40}", head_sha):
        raise ValueError("invalid head SHA")
    if not paths or len(paths) != len(set(paths)) or not set(paths).issubset(HOOKS):
        raise ValueError("invalid install-hook paths")
    return {
        path: hashlib.sha256(subprocess.check_output(["git", "show", f"{head_sha}:{path}"], timeout=30)).hexdigest()
        for path in paths
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--head", required=True)
    parser.add_argument("--hooks-file", required=True)
    args = parser.parse_args()
    if args.pr <= 0 or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
        raise ValueError("invalid repository/PR")
    with open(args.hooks_file, encoding="utf-8") as stream:
        paths = stream.read().splitlines()
    files = hook_hashes(args.head, paths)
    raw = subprocess.check_output([
        "gh", "api", "--paginate", "--slurp",
        f"repos/{args.repository}/issues/{args.pr}/comments",
    ], text=True, timeout=60)
    pages = json.loads(raw)
    if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
        raise ValueError("unexpected comments response")
    comments = [comment for page in pages for comment in page]
    if not reviewed_by_owner(comments, args.repository, args.head, files):
        raise SystemExit("No exact-head, exact-content repository-owner install-hook review found.")
    print("Repository-owner install-hook review matches exact head and content.")


if __name__ == "__main__":
    main()
