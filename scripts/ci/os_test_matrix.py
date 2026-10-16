"""Select bounded native CI jobs without changing the selected OS test files."""
from __future__ import annotations

import argparse
import json
import re


FORK_REPOSITORY = "leether/hermes-agent"


def build_matrix(repository: str) -> dict:
    """Shard only the standard-runner fork's x64 lane; keep other lanes intact."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("invalid repository identity")
    fork = repository == FORK_REPOSITORY
    rows = [
        {"name": f"macOS-only tests ({index}/2)", "runner": "macos-latest",
         "marker": "macos", "slice": f"{index}/2"}
        for index in (1, 2)
    ]
    if fork:
        rows.extend(
            {"name": f"Windows-only tests ({index}/2)", "runner": "windows-latest",
             "marker": "windows", "slice": f"{index}/2"}
            for index in (1, 2)
        )
    else:
        rows.append({"name": "Windows-only tests", "runner": "windows-latest-32-core",
                     "marker": "windows"})
    rows.append({"name": "Windows-only tests (arm64)",
                 "runner": "windows-11-arm" if fork else "windows-latest-32-arm-core",
                 "marker": "windows", "timeout": 60})
    return {"include": rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args(argv)
    try:
        matrix = build_matrix(args.repository)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(matrix, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
