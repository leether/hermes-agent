# Host-owned memory with transient API sessions

An API host that supplies bounded context and owns its consent-aware store can opt
into `platforms.api_server.extra.transient_sessions: true`. Set
`transient_allowed_tools` to a nonempty subset of `web_search` and `web_extract`.
The default remains ordinary native sessions. This capability is generic; it has
no business profile or group identities in core.

`GET /health` and `/v1/health` advertise `session_storage: transient-v1`. This mode
accepts only non-streaming `/v1/chat/completions`, health and model-list requests.
Session-ID/key resumption, idempotency-cache reuse, other endpoints and profile
prefix routes are rejected. Authentication still applies. Each call supplies
its full bounded context; no durable native transcript or memory provider is used.
Tool schemas and post-refresh execution validation enforce the web-only list.

Conversation, compaction and tool results remain transient. Trajectories, request
debug dumps, native memory, oversized-tool spill files and web extraction caches
are disabled in the request context. Logging omits content before queueing; stdout
status is suppressed. Local `MEDIA:` paths are not read into API responses.
Responses omit reasoning and include `hermes_read_urls` from successful
`web_extract` completion callbacks in the current request, before presentation wrapping or compaction. These are retrieval
receipts, not a guarantee that a cited source supports a claim.

The host still owns upstream payload/log retention, provider data handling,
search-query privacy, authorization, deduplication and final delivery. Deploy
with a dedicated empty home, no sibling-profile mounts, read-only runtime and
restricted credentials. This mode is not a general sandbox for arbitrary plugins.
Native memory-enabled profiles continue to use their existing stores.

## Request-local extraction evidence

Transient health responses also advertise `extraction_evidence: extracted-pages-v1`.
Chat completion responses include `hermes_evidence` with this schema and `pages`.
Each page comes exclusively from a successful real `web_extract` completion;
model text and search snippets cannot create receipts. Fields are `url`, `content`,
`sha256` (over returned UTF-8 content), `retrieved_at` (UTC), and `truncated`.
Only HTTPS URLs without credentials are admitted. Each request starts empty;
later successful reads replace the same URL. Bounds are 12 pages, 200,000
characters per page and 600,000 total; consumers must fail closed on unavailable
passages. No additional disk persistence is introduced. Ordinary API mode does
not expose the envelope. This transport proves extraction, not factual accuracy,
source authority, version currency or semantic entailment; those remain caller
responsibilities. The opt-in caller must avoid logging evidence bodies.
