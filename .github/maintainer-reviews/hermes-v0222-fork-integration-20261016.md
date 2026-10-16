# v0.22.2 fork integration decisions

The two real parents are governed fork main f8aa37b58570dd2d30b7d2cfe6e09bc5024e212b and function-proven candidate 9223607c734fb08622b7681666912f07e59e48c6. GitHub compare identifies a688d2a1bd2941c39a7c9efd4d97fda399735266 as their upstream merge base. A real three-way merge was inspected; the proposed tree deliberately uses the proven candidate runtime, with each fork-only concern accounted for below. It never restores obsolete runtime code over a new implementation.

| Fork work | Final disposition |
| --- | --- |
| a3cdc84 / 2c4c25 ingress, commands and private cache names | Adapted candidate functions and unchanged red/green tests. Moved WeCom code uses the target module layout. |
| f0e486f query input | Native target CLI; file/stdin/BOM/encoding/exclusivity/resume and real CLI transport passed. |
| f2a50b5 / PR 1 continuation | Native target SQLite child resolution plus old-parent/latest-child and consumer proofs. |
| 883c6e4 / PR 2 budgets and leases | Candidate replay/auxiliary bounds, required profile overlay, native lease/fence/concurrent proofs. Worker-terminal work remains separate and undeployed. |
| 8e18699 install-hook review | Exact-head/content owner verifier and negative tests retained; Git/API subprocesses now have 30/60 second timeouts required by target code health. Target delegates install hooks to upstream CODEOWNERS; a separate fork workflow retains the stronger owner gate, without changing upstream scanning. All added/modified .pth paths remain blocking. |
| 8e18699 contributor identities | Target contributor directory is authoritative. Missing mappings are carried; existing differing upstream mappings are reported for review, never overwritten silently. Historical review is retained. |
| 8e18699 model catalog fixture | Both target catalog readers mocked. Stable `_match_in_catalog` explicitly forbids fuzzy model-ID rewriting because it could silently select the wrong model version. The previous auto-correction assertion is replaced by a stricter missing-ID rejection plus version suggestion, exact requested-ID and provider preservation, and no-network negative case; no runtime selection code is changed. |
| 8e18699 optional MCP bootstrap | Pinned/ref/bounded local bootstrap contract retained. Upstream removed the old n8n git bridge and ships n8n-official HTTP/OAuth; no obsolete bridge is resurrected. Declared required URL placeholders remain supported. |
| 8e18699 Telegram cache assertion | Candidate opaque-cache/content/original-name tests retain the contract. Target Telegram tests remain, and upstream removal of an old fixture is not reversed. |
| 8e18699 old Nix workflow change | Target removed nix-lockfile-fix.yml; the obsolete workflow is not resurrected. Current nix.yml remains unchanged. |

Runtime Python, PM lock, upstream tests and APIs are byte-identical to the already proven candidate except for the explicitly described catalog fixture and additional tests. No production profile/config, credentials, private original answers or LIVE bindings are included. Complete hosted CI and the separate LIVE admission remain required before rollout.
