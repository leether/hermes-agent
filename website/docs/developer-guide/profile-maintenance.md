# Profile writer maintenance

A profile may opt into an external-maintenance writer barrier using its API server
configuration. The same profile-scoped configuration loader applies to API requests,
built-in cron scans, provider fire claims and detached cron workers:

```yaml
gateway:
  platforms:
    api_server:
      profile_writer_guard:
        enabled: true
        profile: canary
        runtime_id: reviewed-release
```

Configuration belongs to the owning profile. An unmanaged launch adapter cannot bypass
a routed profile's guard. Unconfigured profiles keep their ordinary behavior. Conflicting
runtime identities and unreadable configured admission fail closed.

An operator calls `hermes_profile_maintenance.pause_profile(scope)` and saves its returned
token in the private maintenance transaction. This persistent pause is independent of
`activate_runtime`: changing the reviewed runtime does not reopen admission. The short
admission lock orders pause against new entry. Existing workers retain their writer permits
until their actual completion, including queued executor work, cancelled HTTP waiters,
cron finalization and provider handoffs. Pause does not interrupt an admitted commit.

While paused, business API requests return HTTP 503 with Retry-After. `/health` and the
authenticated `/health/detailed` remain available and expose `profile_admission.state`:
`unmanaged`, `open`, `paused`, `blocked` or `invalid`. Liveness is not permission to send work.
Cron pauses before recovery, heartbeat, due scans, occurrence advancement or claim creation;
its stored due time remains available for the existing catch-up policy after resumption.

After pausing, verify old worker identity and outstanding effects separately. Acquire the
exclusive maintenance barrier before migration or publication. File locks have no TTL.
A stopped process does not prove that its external effects completed. Preserve interrupted
sessions, tool call/result pairs, attempts and delivery evidence before any reconciliation.

`resume_profile(scope, token)` requires the exact pause token, the current runtime identity,
an exclusive drained barrier and no native session/compression leases or unresolved cron
attempts (claimed, running or unknown). It never expires, deletes or retries those records.
Persistent runtime `blocked` and partial-publication markers remain independent gates.
Only an operator may reconcile an interrupted attempt and decide when to resume producers.

Downgrading to code that does not honor this protocol requires stopping and fencing every
old producer first; copying an older database over newer messages is not a rollback.
