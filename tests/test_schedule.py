import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from cognee_memory import CogneeMemory
from news_schedule import NewsSchedule


class ScheduleTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_then_unchanged_after_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            memory = CogneeMemory(root)
            memory.enabled = True
            memory.recall = AsyncMock(return_value="")
            memory.flush_once = AsyncMock()
            run = root / "run"
            run.mkdir()
            (run / "report.md").write_text("Fresh report")
            researcher = SimpleNamespace(discover=AsyncMock(return_value=([SimpleNamespace(id="1", title="Bitcoin", content="", published_at="2026-11-14T21:00:00+00:00", url="https://news/1")], {})), run=AsyncMock(return_value=run))
            try:
                schedule = NewsSchedule(root, researcher, memory, asyncio.Lock())
                await schedule.check()
                self.assertEqual(schedule.state["status"], "memory_pending")
                restarted = NewsSchedule(root, researcher, memory, asyncio.Lock())
                await restarted.check()
                self.assertEqual(restarted.state["status"], "no_update")
                self.assertEqual(researcher.run.await_count, 1)
                self.assertEqual(len(list((memory.root / "outbox").glob("*.json"))), 1)
            finally:
                await memory.close()

    async def test_search_failure_not_reported_as_no_update(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            memory = SimpleNamespace(destination="cloud", root=root / "memory", _save=CogneeMemory._save)
            researcher = SimpleNamespace(discover=AsyncMock(return_value=([], {"source": {"search_errors": ["Timeout"]}})))
            schedule = NewsSchedule(root, researcher, memory, asyncio.Lock())
            await schedule.check()
            self.assertEqual(schedule.state["status"], "check_incomplete")
