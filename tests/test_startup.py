"""Test the startup boundary without importing main or loading deployment config."""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, call


def startup_function():
    source = Path(__file__).resolve().parents[1] / "main.py"
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    function = next(node for node in tree.body
                    if isinstance(node, ast.AsyncFunctionDef) and node.name == "start_app")
    namespace = {"Application": object, "logger": Mock()}
    # Execute the actual production function, but none of main's imports,
    # configuration reads, process lock, database initialization or bot setup.
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
    return namespace["start_app"]


class StartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_polling_preserves_pending_updates_after_initialization(self):
        lifecycle = Mock()
        initialize, start, poll = AsyncMock(), AsyncMock(), AsyncMock()
        lifecycle.attach_mock(initialize, "initialize")
        lifecycle.attach_mock(start, "start")
        lifecycle.attach_mock(poll, "poll")
        app = SimpleNamespace(initialize=initialize, start=start,
                              updater=SimpleNamespace(start_polling=poll),
                              bot=SimpleNamespace(name="Synthetic bot"))

        await startup_function()(app)

        self.assertEqual(lifecycle.mock_calls,
                         [call.initialize(), call.start(), call.poll(drop_pending_updates=False)])
        poll.assert_awaited_once_with(drop_pending_updates=False)

    async def test_missing_updater_fails_instead_of_claiming_polling_started(self):
        app = SimpleNamespace(initialize=AsyncMock(), start=AsyncMock(), updater=None)
        with self.assertRaisesRegex(RuntimeError, "updater"):
            await startup_function()(app)


if __name__ == "__main__":
    unittest.main()
