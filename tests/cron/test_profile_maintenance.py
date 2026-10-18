"""Maintenance must preserve due occurrences and own queued cron work through completion."""
from datetime import timedelta
import json
import threading

import pytest

from cron import jobs, scheduler
from cron.scheduler_provider import InProcessCronScheduler
from hermes_profile_maintenance import pause_profile, resume_profile
from hermes_profile_writer import WriterBusyError, WriterScope, activate_runtime, maintenance_activity
from hermes_time import now

pytestmark = pytest.mark.platforms("posix")


@pytest.fixture
def guarded_home(tmp_path, monkeypatch):
    home = tmp_path / "canary"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    scope = WriterScope(home, "runtime")
    activate_runtime(scope)
    (home / "config.yaml").write_text(json.dumps({"gateway": {"platforms": {"api_server": {
        "profile_writer_guard": {"enabled": True, "profile": home.name, "runtime_id": scope.runtime_id}}}}}))
    with jobs.use_cron_store(home):
        job = jobs.create_job(prompt="synthetic local job", schedule="every 4h")
        rows = jobs.load_jobs()
        rows[0]["next_run_at"] = (now() - timedelta(minutes=1)).isoformat()
        jobs.save_jobs(rows)
        yield scope, job


def test_paused_start_and_tick_preserve_due_job_without_attempt(guarded_home):
    scope, job = guarded_home
    before = (scope.home / "cron/jobs.json").read_bytes()
    token = pause_profile(scope)
    provider = InProcessCronScheduler()
    stop = threading.Event()
    stop.set()
    provider.start(stop)
    assert scheduler.tick(verbose=False, sync=False) == 0
    with pytest.raises(WriterBusyError):
        provider.claim_fire(job["id"])
    assert (scope.home / "cron/jobs.json").read_bytes() == before
    assert not (scope.home / "cron/executions.db").exists()
    resume_profile(scope, token)
    claim = provider.claim_fire(job["id"])
    assert claim is not None
    with pytest.raises(WriterBusyError):
        with maintenance_activity(scope):
            pytest.fail("queued fire lost its barrier")
    # Explicitly abandoning a never-started claim releases only the process pin;
    # its durable attempt remains available for unknown reconciliation.
    claim.release()


def test_async_tick_keeps_barrier_until_worker_and_finalization_finish(guarded_home, monkeypatch):
    scope, _ = guarded_home
    started, finish = threading.Event(), threading.Event()
    executions = []

    def worker(job, *args):
        started.set()
        assert finish.wait(5)
        from cron.executions import finish_execution
        finish_execution(job["execution_id"], success=True)
        executions.append(job["execution_id"])
        return True

    monkeypatch.setattr(scheduler, "_process_due_job", worker)
    try:
        assert scheduler.tick(verbose=False, sync=False) == 1
        assert started.wait(2)
        token = pause_profile(scope)
        with pytest.raises(WriterBusyError):
            resume_profile(scope, token)
    finally:
        finish.set()
        scheduler._get_parallel_pool(scheduler._resolve_max_parallel_workers()).shutdown(wait=True)
    assert len(executions) == 1
    resume_profile(scope, token)
    # The same scheduled occurrence has already been advanced; it cannot fire twice.
    assert scheduler.tick(verbose=False) == 0
    assert len(executions) == 1
