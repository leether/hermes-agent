# One-time corrected-stable import contract

The maintainer-approved import is fixed to official Hermes v0.22.2 commit
`d923a5eb487a17c0a68801bba9ef0f56c81040a8`, fork base
`f8aa37b58570dd2d30b7d2cfe6e09bc5024e212b`, and the function-proven ancestor
`f401e8a38bf8cd010b1eef8fe1ac831db219aa84`. Only personal fork PR #5 and
its first main push may use this contract. Both upstream and candidate must
be real ancestors. Every later main/PR uses the ordinary current-main gates.

This accepts the imported upstream health baseline, not a claim that the 7,983
old-fork comparison findings were fixed. Local changes are still ratcheted
against the fixed official source. The old-fork CI failure remains reviewable.

Five oversized upstream files and four encoded-launch files are pinned by
path AND Git blob in `scripts/ci/fork_import_contract.py`. Both committed and
working bytes must match the fixed official tree; drift refuses the contract
before any exclusion. Blob exemptions cover only the five oversized files.
Security excludes only the four unchanged, reviewed files from the original
added-line scanner. Unknown paths and local encoded execution remain blocking.
The encoded launchers execute locally generated Python through shell quoting;
this is not an allowance for downloaded or changed encoded payloads.

Upstream ancestor commits keep their original authors. Only the fixed official
ancestor set inherits upstream attribution responsibility; all local authors
still need normal mappings. No history or author identity is rewritten.

The root install-hook exact-head/content owner review remains independent and
required. Approval on an older head does not discharge the final-head gate.
No `.pth` policy, dependency bounds, runtime behavior, test assertion or profile
budget is relaxed by this import contract.

The personal public fork uses the standard Linux x64, Windows x64 and Windows
ARM64 runners documented by GitHub:
https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job
Upstream larger-runner labels remain unchanged outside this fork. Python runs
all files across 16 four-worker slices instead of 2 thirty-two-worker slices;
platform coverage and existing timeout bounds are retained. No paid runner is
provisioned. Actual hosted CI remains required; local proof is not a substitute.

The fourth security file, `tests-js/scripts/desktop-smoke.test.ts`, contains two
static mock-launcher strings with the inert base64 fixture `eA==`; its full fixed
upstream blob is pinned too. It receives no large-blob exemption.
