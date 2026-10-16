"""Post-commit result and receipt contracts on the real Windows hand-off."""
from __future__ import annotations

from pathlib import Path
import time

import pytest

from tests.scripts.desktop_update.windows_commit_outcome_support import _handoff


@pytest.mark.platforms('windows')
def test_verify_failure_after_a_committed_update_is_ok_with_warnings(tmp_path: Path) -> None:
    code, out, argv, result, _ = _handoff(tmp_path, verify='raise SystemExit(3)\n')
    assert code == 0, out
    assert (result['ok'], result['exit_code'], result['manual']) == (True, 0, True), result
    assert [w.split(':')[0] for w in result['warnings']] == ['verify'], result
    assert result['message'].startswith('Hermes was updated, but'), result
    assert 'previous version' not in result['message']
    # The fleet the Desktop stopped is still brought back.
    assert argv[-1] == ['gateway', 'start', '--all'], argv



@pytest.mark.platforms('windows')
def test_result_is_atomic_json_carrying_started_at_and_warnings(tmp_path: Path) -> None:
    started = int(time.time()) - 5
    code, out, _, result, home = _handoff(tmp_path, HERMES_UPDATE_STARTED_AT=str(started))
    assert code == 0, out
    assert (result['ok'], result['started_at'], result['warnings']) == (True, started, []), result
    assert not list(home.glob('.hermes-update-result.json.*.tmp'))



@pytest.mark.platforms('windows')
def test_a_result_that_cannot_be_published_leaves_no_tmp_file(tmp_path: Path) -> None:
    # Write-Result's Move/Replace fail (the result path is a directory): its <result>.<pid>.tmp
    # must not be left beside it, one per hand-off, forever.
    code, out, _, result, home = _handoff(
        tmp_path, '-NoGateway', prepare=lambda home, _install: (home / '.hermes-update-result.json').mkdir())
    assert code == 0, out
    assert result is None
    assert not list(home.glob('.hermes-update-result.json.*.tmp')), list(home.iterdir())



@pytest.mark.platforms('windows')
@pytest.mark.parametrize(('receipt', 'ok'), [('interrupted', True), ('partial', True), ('interrupted,another-run', False),
                                             ('failed', False)])
def test_nonzero_exit_after_the_commit_point_is_installed_with_a_followup(tmp_path: Path, receipt: str, ok: bool) -> None:
    # Contract C3: `hermes update` exits 130 / 1 AFTER its commit point (Ctrl-C after the code
    # moved, a parked autostash). Its own receipt (matched by the correlation id) says so: the
    # result must report the update installed with an owed follow-up, never "update failed".
    code, out, argv, result, _ = _handoff(tmp_path, HANDOFF_RECEIPT=receipt, HANDOFF_EXIT='130')
    if ok:
        assert code == 0, out
        assert (result['ok'], result['exit_code'], result['manual']) == (True, 0, True), result
        assert result['message'].startswith('Hermes was updated, but'), result
        assert [w.split(':')[0] for w in result['warnings']] == ['update'], result
        assert argv[-1] == ['gateway', 'start', '--all'], argv   # the post-commit steps still run
    else:
        assert code == 130, out
        assert (result['ok'], result['exit_code']) == (False, 130), result
