# Auxiliary request ceilings

An operator with a shorter caller deadline can set `auxiliary.<task>.max_timeout`
in that profile's `config.yaml`. This positive, finite number caps the resolved
per-request timeout, including a per-call override and compression's default
300-second floor. Invalid bounds fail before a request. With no bound, the
upstream timeout and compression-floor behavior remain unchanged.

```yaml
auxiliary:
  compression:
    timeout: 120
    max_timeout: 90
compression:
  context_timeout_seconds: 90
  context_total_ceiling_seconds: 120
```

For a caller that waits 240 seconds, this example leaves time after compaction.
The auxiliary bound is a request bound, not proof that an entire turn or every
fallback finishes within it. The host context ceiling separately limits the
compression wait; a timeout does not prove its worker exited. Keep run identity,
lease/fence and unknown-outcome handling at the caller. Each profile owns its own
configuration; declaring this example does not apply it to a running service.
