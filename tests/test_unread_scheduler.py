"""Run the real scheduler boundary without importing deployment configuration."""

import ast
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock


def scheduler_function(*, paused=False, schedules_error=None):
    source = Path(__file__).resolve().parents[1] / "main.py"
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    function = next(node for node in tree.body
                    if isinstance(node, ast.AsyncFunctionDef) and node.name == "scheduler_loop")
    namespace = {
        "salchicher": None, "vaca": None, "vaca_campaigns": None,
        "schedules_paused": Mock(return_value=paused),
        "get_schedules": Mock(return_value=[], side_effect=schedules_error),
        "unread_notifier": SimpleNamespace(tick=AsyncMock()),
        "datetime": datetime, "APP_TIMEZONE": timezone.utc,
        "SCHEDULER_POLL_SECONDS": 30, "logger": Mock(),
        # Cancel at the first poll wait so this executes precisely one iteration.
        "asyncio": SimpleNamespace(sleep=AsyncMock(side_effect=asyncio.CancelledError)),
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
    return namespace


class UnreadSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_broken_schedule_cannot_block_unread_check(self):
        context = scheduler_function(schedules_error=ValueError("invalid schedule"))
        with self.assertRaises(asyncio.CancelledError):
            await context["scheduler_loop"]()
        context["get_schedules"].assert_called_once_with()
        context["unread_notifier"].tick.assert_awaited_once_with()
        context["asyncio"].sleep.assert_awaited_once_with(30)

    async def test_pausing_schedules_also_pauses_unread_notifications(self):
        context = scheduler_function(paused=True)
        with self.assertRaises(asyncio.CancelledError):
            await context["scheduler_loop"]()
        context["get_schedules"].assert_not_called()
        context["unread_notifier"].tick.assert_not_awaited()
        context["asyncio"].sleep.assert_awaited_once_with(30)


if __name__ == "__main__":
    unittest.main()
