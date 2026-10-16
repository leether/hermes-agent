# Functional conflicts found by the full import CI

The import-contract gates passed at `89c9c094`; the full suite still found real
local-patch overlaps. This follow-up keeps the patched behavior and upstream
invariants together, without weakening any CI gate.

* Thinking estimates drop stale `reasoning_details` only on routes that do not
  replay older thinking. Generic readable thinking remains charged; opaque and
  mirrored payloads retain their original exclusions. Canonical history is not
  modified. The existing native Anthropic wire/accounting tests stay unchanged.
* The command normalizer preserves trailing ASCII argument spaces while still
  normalizing leading wrappers and fullwidth slashes. The original Slack tests
  stay unchanged.
* MCP document results expose the sanitized original display name separately
  from the short ASCII cache path. Document contents, size limits, MIME/suffix,
  traversal checks and original-name metadata remain covered.
* Owner-review tests move unchanged to the declared `tests/ci` cross-cutting
  location. No test-tree-layout allowance is added.
* Provider/catalog tests stub their actual metadata transports. A strict socket
  guard found four attempted external probes despite all assertions passing;
  those attempts remain failed evidence. The core suite is re-run with zero
  attempts. Two cohesive test groups move to topical siblings to keep the
  existing oversized-file ratchet; cases and assertions are retained.
* Native Windows tests exposed a Git-for-Windows layout gap and two observation
  races. The locator also tries UCRT and real `bin/git.exe` layouts, retaining
  its actual executable probe and broken-trampoline refusal. The installed Git
  remains the native test subject. Package layout evidence:
  https://github.com/git-for-windows/build-extra/blob/main/installer/install.iss
  https://github.com/git-for-windows/git-for-windows-automation/blob/main/.github/workflows/build-and-deploy.yml
  Process-status observation waits for the actual suspended state. A disposable
  help-probe handshake takes the marker lock before child publication; the
  suspended update child is found by parent identity, excluding known fixture
  children, since CIM may not yet expose its command line. No production
  PowerShell script, timeout ceiling or containment assertion is weakened.

Windows behavior requires the hosted native x64/ARM64 jobs; macOS local proof
does not discharge that requirement. The final-head install-hook owner gate
also remains mandatory. No deployment, production data write, or outbound send.

The first follow-up CI classified the full import successfully but the detect
job ended cancelled after 66 seconds under its one-minute job cap; all its
steps reported success and every dependent suite was skipped. That is failed
CI evidence, not a full test run. Only personal-fork PR #5 against fixed f8aa
gets a bounded five-minute checkout/classification cap. Native test deadlines,
assertions, job dependencies and aggregate gates are unchanged.

The Windows help-probe fixture excludes its verified distlib/venv launcher
ancestor chain as well as the probe and custodian. It fails if that probe is
not descended from its own disposable hand-off; no unrelated PID is adopted.

At 5f5b460, all 16 Python slices passed (5,576 files, 60,822 cases,
860 existing skips, no flaky-file retry report). The root JS bundle-metadata
check timed out at its unchanged 15-second bound while ten workspace units
were scheduled four at once on the standard four-core runner; the other nine
units passed. The same unchanged case passed the earlier 89c9 run. The
personal fork now uses the existing workspace runner's `--concurrency 2`
option to bound nested worker contention. All ten discovered units, all test
assertions, the 15-second case deadline, and the 30-minute job cap stay intact.
The workspace-runner implementation itself is unchanged. Actual new hosted CI
is required; this is not a declaration that a retry made the failure disappear.

The same 5f5b460 native Windows x64 run passed all three originally repaired
groups (real Git trampoline, suspended process setup, marker publication lock).
Its overall job still failed: three other PowerShell-heavy files hit the
existing 300-second file cap, and a CIM creation-time query was reported flaky
after a 60-second first-attempt timeout. The summary's zero failed assertions
does not discharge those killed-file failures. The personal-fork native
Windows pool is reduced from four to two workers on both architectures;
all 216 selected files, the original 300-second file cap, 60-second probe
timeout and job bounds remain unchanged. Upstream runner scheduling is
unchanged. No Windows production script or test assertion is altered by this
resource follow-up; native hosted proof is still required.

The native ARM64 result also retained a 300-second killed file and an A7
first-attempt miss: CIM did not enumerate the never-resumed update child
within 60 seconds, although the unchanged case passed on retry. The fixture
now observes its own parent's real kernel process table through psutil,
retaining the captured launcher/custodian exclusions and the same 60-second
bound. The no-instruction-before-publication, dead-child and marker assertions
are unchanged. No production process code is changed by this oracle fix.

The 39a984415 ARM64 cold-SDK job reached its cleanup hook, where removing the
test-owned native signer directory failed with EPERM; the per-test and global
teardown then reported that same directory lock. Both cleanup sites now use
Node's bounded filesystem retry option (10 retries, 100 ms linear backoff).
Only the test-owned temporary tree is affected; a persistent lock still throws
and fails the job. SDK download, signature verification, runtime, warm-cache
and signing-boundary assertions and all test timeouts are unchanged. No test
or job result is retried/ignored by this cleanup option.

The remaining 39 ARM64 failure was one aggregate file cap: the 12-case
commit-outcome file completed 11 cases successfully and was killed at the
unchanged 300-second limit during its final bounded-help test. Its nine test
definitions (12 parameterized cases) are split into receipt/outcome and
step-liveness files, sharing the exact launcher fixture in a non-collected
support module. Every test body, decorator, assertion and individual deadline
is preserved; the one-time extraction audit verifies that conservation but
does not replace native execution. Both smaller files still have the original
300-second cap. No production updater code or timeout is changed.

The 575 x64 run exposed the same aggregate cap in the separate 19-case
marker contract file: ten cases passed before the unchanged 300-second file
budget terminated the next case. The original failed job remains evidence.
The ten definitions / nineteen cases are now grouped by ownership, reader
parity, desktop lifecycle and delegate liveness, using the original helper
bodies and constants in a non-collected sibling support module. Every test
body, decorator, assertion and individual deadline is unchanged; each file
retains the 300-second cap. This restructuring needs fresh native x64 and
ARM64 execution, and does not change production updater behavior.

The completed 575 ARM64 run also capped the separate launcher-lineage file
at 300 seconds after nine parameterized cases had passed. Its five definitions / ten cases
are grouped into old-wrapper ownership, start-time environment, shared rule
parity and run-specific bridge adoption. Helper bodies/constants and every
case body, decorator, assertion and individual deadline are retained. The
shared sleeper uses pytest's plugin registration to avoid import shadowing.
All files retain the original cap; the complete new-head native run remains
required. The failed 575 run is preserved in full.

The 14e x64 native run completed all 223 files / 706 cases with zero failures
and no flaky report, but reached its unchanged 30-minute job deadline before
checkout verification/cleanup completed. A successful assertion summary does
not discharge that cancelled job. Only this exact fork's standard x64 lane
now uses the runner's existing 1/2 and 2/2 file partition in separate jobs;
each keeps two workers, a 30-minute job cap, the 300-second file cap and all
case deadlines. The actual selected file union must be disjoint and complete.
The official and other repositories keep their single x64 lane; macOS's two
slices and ARM64's one 60-minute job remain unchanged. A bounded sparse
checkout preparation job emits the matrix; it changes no security gate or
production runtime. New-head full CI and exact-head owner review remain
required.

Matrix preparation checks out the workflow revision's helper rather than
`inputs.commit`; the original native test jobs still check out that explicit
test commit. This keeps validation of an older source commit working even
when it predates the new matrix helper.

The 841 full-suite release-threading check identified that this deliberately
controller-owned matrix checkout was not registered in its existing narrow
controller-checkout contract. Only that exact preparation step is registered;
a companion contract requires the helper plus clean-checkout action sparse
checkout, five-minute budget and matrix-only output. The preparation job ends
with the original clean-checkout action, without changing its master mode. Every actual test checkout remains subject to
the original admitted-commit assertion. The failed run is retained and the
complete CI-contract directory is verified locally before publication.

A separate 841 Linux fixture failed before its lock-owner assertion: Git 2.55
removed a background-maintenance lock while the fixture repository was being
copied. Only the two tiny fixture-setup commits disable automatic maintenance
and GC through per-command options; no repository configuration is persisted. Production Git configuration, real holder processes,
lock ownership assertions and all timeouts are unchanged; no lock is ignored
or deleted to make a copy succeed. The Linux host case still requires CI.

The existing update-routing replay assumed every matrix was a static YAML
mapping. It now executes the actual safe matrix-output step, forwards its
job output through `needs`, and evaluates `fromJSON` before replaying every
selected test consumer. Repository identity is forwarded through nested calls
and the isolated step environment. All routing and negative-control assertions
remain required; malformed or missing output is not replaced by a static list.

The 9c4c JS run completed nine workspace checks and 10,873 Desktop UI cases,
but the root metadata smoke test exceeded its 15-second aggregate budget.
Along with ten CLI starts, each request validation starts Python. Admissions
are now independent cases for identity, native stamp platforms, every request
field, conflicting stamp fields, missing requests, Mac metadata, independent
witnesses and malformed CLI requests. All original assertion expressions and
negative values are preserved; every case retains the original 15-second cap.
The controlled slow-start proof fails the original aggregate case and passes
the grouped cases. Local broad Mac workspace failures are preserved rather
than reclassified as Linux CI proof. No retry, production metadata change,
new deadline or ignored CI check is introduced.
