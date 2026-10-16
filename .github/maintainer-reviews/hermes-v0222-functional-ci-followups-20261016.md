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
