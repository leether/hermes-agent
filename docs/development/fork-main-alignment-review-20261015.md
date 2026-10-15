# Fork main alignment: bounded CI and catalog review

The alignment retains the published `42bdffd8` maintenance history. No runtime deployment, in-flight lifecycle branch or newer upgrade candidate is included. All 24 source/test blobs touched by the five maintenance patches remain unchanged.

## Behavioral checks

The Telegram ZIP test used an original-filename suffix assertion after the cache contract deliberately switched to short ASCII UUID paths. It now checks the actual cached bytes, safe extension/MIME, and original Telegram filename retained in the event. The cache implementation is unchanged.

The OpenCode test mocked the selection catalog but not the subsequent validation catalog, allowing an external model listing to change the expected identifier. Both readers now use synthetic responses. The original exact-name/provider assertions remain, with separate coverage for legitimate version correction and no socket connection. Production model selection/validation code is unchanged.

Twenty-two release author mappings were verified against their original GitHub commit's author/login; no contributor identity or history is rewritten. The upstream GitHub App-backed Nix auto-commit job is limited to the upstream repository. Fork Nix verification remains enabled and read-only.

## Install-hook review

Reviewed `setup.py`, SHA256 `2d2f6d04d44467713f51a63567d2f2c2f7e18cc37d2af7e045b790f3a7f7ffac`: it imports stdlib collections/pathlib and setuptools, groups existing files from the two declared skill trees, then supplies `data_files` to setup(). It contains no shell command, decoded execution, credential reads or network call. Its packaging behavior is retained.

Install-hook findings still block by default. The scanner now permits only an explicit repository-owner comment bound to the exact PR head SHA and complete Git-blob SHA256 mapping. It cannot discharge any other critical finding, and a label, bot, non-owner, stale head or changed bytes is insufficient. The owner review uses this strict body format:

```text
<!-- hermes-install-hook-review:v1 -->
{"head_sha":"<40 hex PR head>","files":{"setup.py":"<64 hex Git blob SHA256>"},"disposition":"reviewed-install-hook-only","reason":"Specific review of the exact hook behavior and its retained packaging purpose."}
```

The owner must review and publish the actual head/content record after the final commit. Every later head requires a new record. GitHub comments are read through the API, never executed. Bot comments and candidate-authored hash allowlists alone provide no approval.

## Bundled MCP review

The catalog contains two entries. Neither is installed or enabled by this alignment.

- **Linear**: the remote Streamable HTTP URL `https://mcp.linear.app/mcp` and OAuth setup match [Linear's official documentation](https://linear.app/docs/mcp). No local command/bootstrap or requested static secret is introduced. The existing endpoint exposes read/write capabilities; installation and OAuth are explicit user actions, not a read-only entitlement.
- **n8n**: [source commit 7a9ae00795593aa1fdb4e61ecd640e8bfd0c3841](https://github.com/CyberSamuraiX/hermes-n8n-mcp/tree/7a9ae00795593aa1fdb4e61ecd640e8bfd0c3841) was read without execution. The manifest's floating `main` is replaced by that immutable commit. Launch is the cloned venv Python plus `server.py` over stdio; there is no shell wrapper or public listener. Bootstrap uses a project-local uv venv and the same three upstream dependencies with explicit upper bounds. Transitive packages are resolved at a future explicit install, not claimed as an offline lock.
- n8n's required `N8N_BASE_URL` and secret `N8N_API_KEY` correspond to source HTTP client configuration; the API key is sent only as `X-N8N-API-KEY` to the configured n8n instance. The server supports optional dotenv files; no dotenv file or credential is bundled here.
- Its default tool selection remains the eight existing inspection/export tools. Activate/deactivate and Docker-log tools remain excluded. The source's health tool may inspect Docker container status, and optional Docker-log access defaults on upstream; these are documented capabilities, not a sandbox or absolute read-only guarantee. No tool was called in this review.
- The installer only clones/bootstraps on explicit install and writes profile-local configuration. Existing installer tests exercise those contracts with synthetic repos and mocks. Bootstrap commands remain trusted catalog code; no general shell-execution sandbox is claimed.

Only after this command/args/env/source review should the existing `mcp-catalog-reviewed` label be applied to the exact alignment PR. The MCP label gate itself is unchanged.
