"""Tests for matrix/monitor.py's _SyncHealthTracker.

Covers the homeserver-optional fix: a down homeserver should produce exactly
one warning (not matrix-nio's own per-attempt "Error validating response"
spam) and reconnecting should produce exactly one "restored" message.

Only _SyncHealthTracker itself is exercised here, not the full
monitor_matrix() coroutine (which needs a live matrix-nio client) -- same
rationale as test_monitor_cleanup.py.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from minion_assist.matrix.monitor import _SyncHealthTracker


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _FakeSyncError:
    def __init__(self, message: str) -> None:
        self.message = message


def test_first_sync_error_prints_one_warning_and_marks_down(capsys):
    tracker = _SyncHealthTracker(backoff_seconds=0)

    _run(tracker.on_sync_error(_FakeSyncError("'next_batch' is a required property")))

    assert tracker.down is True
    err = capsys.readouterr().err
    assert "homeserver unreachable" in err
    assert "next_batch" in err


def test_repeated_sync_errors_do_not_reprint_the_warning(capsys):
    tracker = _SyncHealthTracker(backoff_seconds=0)
    error = _FakeSyncError("boom")

    _run(tracker.on_sync_error(error))
    _run(tracker.on_sync_error(error))
    _run(tracker.on_sync_error(error))

    err = capsys.readouterr().err
    assert err.count("homeserver unreachable") == 1


def test_sync_error_backs_off_before_returning():
    tracker = _SyncHealthTracker(backoff_seconds=10.0)

    with patch(
        "minion_assist.matrix.monitor.asyncio.sleep", new_callable=AsyncMock
    ) as mock_sleep:
        _run(tracker.on_sync_error(_FakeSyncError("boom")))

    mock_sleep.assert_awaited_once_with(10.0)


def test_sync_success_prints_nothing_when_already_healthy(capsys):
    tracker = _SyncHealthTracker()

    _run(tracker.on_sync_success(object()))

    assert tracker.down is False
    assert capsys.readouterr().out == ""


def test_sync_success_prints_restored_message_after_being_down(capsys):
    tracker = _SyncHealthTracker()
    tracker.down = True

    _run(tracker.on_sync_success(object()))

    assert tracker.down is False
    assert "Homeserver connection restored." in capsys.readouterr().out


def test_repeated_sync_successes_do_not_reprint_restored_message(capsys):
    tracker = _SyncHealthTracker()
    tracker.down = True

    _run(tracker.on_sync_success(object()))
    _run(tracker.on_sync_success(object()))

    out = capsys.readouterr().out
    assert out.count("Homeserver connection restored.") == 1
