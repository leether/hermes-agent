"""One reviewed upstream import; ordinary PRs keep their current-main gates.

Only leether/hermes-agent PR 5 (and its first main push) can inherit the
fixed v0.22.2 health baseline and exact upstream assets. No moving refs, path-only
exceptions, guessed authors or blanket security exclusions are accepted.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from scripts.ci import check_blob_size


class ContractError(RuntimeError):
    """A requested import cannot prove its frozen provenance."""


@dataclass(frozen=True)
class ImportPolicy:
    repository: str
    pull_request: int
    base: str
    upstream: str
    candidate: str
    blobs: Mapping[str, str]
    security_paths: tuple[str, ...]


POLICY = ImportPolicy(
    repository="leether/hermes-agent", pull_request=5,
    base="f8aa37b58570dd2d30b7d2cfe6e09bc5024e212b",
    upstream="d923a5eb487a17c0a68801bba9ef0f56c81040a8",
    candidate="f401e8a38bf8cd010b1eef8fe1ac831db219aa84",
    blobs={
        "apps/desktop/packaging/nous-dmg-2b.tiff": "cfb4e54d9ebb593852673a88b44cb523d07a4011",
        "apps/shared/src/gateway-contract.openrpc.json": "ba761e0f9199b99644f551e6216bae871b629593",
        "tests/tui_gateway/test_tui_gateway_server.py": "dd74fb8391a14d21d3c0a5444380faa0dae2aace",
        "apps/desktop/electron/main.ts": "5987d629f2dfa6a9f04b0ad319d0775e24270715",
        "native/fts5_cjk/vendor/sqlite3.h": "c2ed750305b24468fabd090699ffd700bfdf4f88",
        "tools/file_operations.py": "1a93283f8c99617803753183f8b64ba040cf4cf6",
        "hermes_cli/_launchers.py": "61ca4d8ef779675d012d9436fe1d10a6ed837cb0",
        "tests/gateway/test_gateway_inline_bootstrap_identity.py": "c51d58080488f240b470179d6aaa15278235af28",
        "tests-js/scripts/desktop-smoke.test.ts": "490dadc9345f615efe6774fa532958be6459772d",
    },
    security_paths=("tools/file_operations.py", "hermes_cli/_launchers.py",
                    "tests/gateway/test_gateway_inline_bootstrap_identity.py",
                    "tests-js/scripts/desktop-smoke.test.ts"),
)
LOCK_EXCLUDES = (":!uv.lock", ":!*.lock", ":!package-lock.json", ":!yarn.lock")


def git(repo: Path, *args: str) -> str:
    """Read local objects only: missing provenance must never trigger lazy fetch."""
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=120, check=False,
                            env={**os.environ, "GIT_NO_LAZY_FETCH": "1"})
    if result.returncode:
        raise ContractError(f"git {args[0]} failed ({result.returncode})")
    return result.stdout


def event_context(env: Mapping[str, str]) -> tuple[str, int]:
    repository = env.get("GITHUB_REPOSITORY", "")
    event_name = env.get("GITHUB_EVENT_NAME")
    if repository != POLICY.repository or event_name not in {"pull_request", "push"}:
        return repository, 0
    event = json.loads(Path(env["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8-sig"))
    if not isinstance(event, dict):
        raise ContractError("event is not an object")
    if event_name == "push":
        # The import's first main push must pass too. The next commit's base
        # is different, so this cannot become a permanent baseline exception.
        eligible = (env.get("GITHUB_REF") == "refs/heads/main" and event.get("before") == POLICY.base
                    and re.fullmatch(r"[0-9a-f]{40}", str(event.get("after"))) is not None
                    and event.get("after") == env.get("GITHUB_SHA"))
        return repository, POLICY.pull_request if eligible else 0
    number = event.get("number")
    if type(number) is not int:
        raise ContractError("pull request event has no integer number")
    return repository, number


def verify_blobs(repo: Path, head: str, policy: ImportPolicy) -> None:
    for path, expected in policy.blobs.items():
        upstream = git(repo, "rev-parse", f"{policy.upstream}:{path}").strip()
        committed = git(repo, "rev-parse", f"{head}:{path}").strip()
        working = git(repo, "hash-object", "--", path).strip()
        if upstream != expected or committed != expected or working != expected:
            raise ContractError(f"reviewed upstream content changed: {path}")


def import_policy(repo: Path, base: str, head: str, context: tuple[str, int],
                  policy: ImportPolicy = POLICY) -> ImportPolicy | None:
    resolved = git(repo, "rev-parse", "--verify", f"{base}^{{commit}}").strip()
    if context != (policy.repository, policy.pull_request) or resolved != policy.base:
        return None
    git(repo, "merge-base", "--is-ancestor", policy.upstream, head)
    git(repo, "merge-base", "--is-ancestor", policy.candidate, head)
    verify_blobs(repo, head, policy)
    print(f"Reviewed one-time import: {policy.upstream}; normal gates resume after merge.", file=sys.stderr)
    return policy


def health_base(repo: Path, base: str, policy: ImportPolicy | None) -> str:
    return policy.upstream if policy else git(repo, "rev-parse", base).strip()


def author_emails(repo: Path, base: str, head: str, policy: ImportPolicy | None) -> str:
    # Fixed upstream ancestry keeps its original authors. Every local commit
    # remains subject to the existing mapping check; no identity is invented.
    exclude = [f"^{policy.upstream}"] if policy else []
    emails = git(repo, "log", f"{base}..{head}", *exclude, "--format=%ae", "--no-merges")
    return "\n".join(sorted(set(emails.splitlines())))


def supply_diff(repo: Path, base: str, head: str, policy: ImportPolicy | None) -> str:
    # Only these whole files have exact-content review. Any edit aborts the
    # contract before exclusions apply. All other added lines reach the scanner.
    reviewed = [f":!{path}" for path in policy.security_paths] if policy else []
    return git(repo, "diff", f"{base}...{head}", "--", ".", *LOCK_EXCLUDES, *reviewed)


def blob_offenders(repo: Path, base: str, policy: ImportPolicy | None,
                   limit: int = check_blob_size.MAX_BYTES) -> list[check_blob_size.Offender]:
    offenders = check_blob_size.find_offenders(
        repo, base, None, limit, check_blob_size.read_allowlist(repo / check_blob_size.ALLOWLIST))
    # verify_blobs already proved both committed and working content. Do not
    # turn this into a permanent path allowlist: policy is absent after import.
    return [item for item in offenders if not policy or item.path not in policy.blobs
            or item.path in policy.security_paths]


def check_blobs(repo: Path, base: str, policy: ImportPolicy | None) -> int:
    offenders = blob_offenders(repo, base, policy)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as stream:
            if policy:
                stream.write(f"Reviewed fixed upstream import: `{policy.upstream}`. Exact blobs only.\n")
            stream.write(check_blob_size.summary_table(offenders, check_blob_size.MAX_BYTES))
    if offenders:
        print("\n".join(check_blob_size.render(offenders, check_blob_size.MAX_BYTES)))
        return 1
    print("Blob gate passed; no unreviewed added/modified file exceeds its cap.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("health-base", "author-emails", "supply-diff", "blob-size"))
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args(argv)
    repo = Path.cwd()
    try:
        policy = import_policy(repo, args.base, args.head, event_context(os.environ))
        if args.command == "blob-size":
            return check_blobs(repo, args.base, policy)
        if args.command == "health-base":
            print(health_base(repo, args.base, policy))
        elif args.command == "author-emails":
            print(author_emails(repo, args.base, args.head, policy))
        else:
            print(supply_diff(repo, args.base, args.head, policy), end="")
    except (ContractError, check_blob_size.GitError, OSError, ValueError, KeyError) as exc:
        print(f"upstream import contract refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
