import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from band_bot import CryptoAdapter, is_briefing_request, saved_briefing


class CacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_latest_reply_bypasses_busy_worker_and_providers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / 'data/run'
            run.mkdir(parents=True)
            (root / 'data/latest.txt').write_text(str(run))
            (run / 'status.json').write_text(json.dumps({'status': 'complete', 'window_end': '2026-11-14T21:57:00+00:00'}))
            report = '# Saved briefing\nWindow: 2026-11-14T21:57:00+00:00\nSource: https://example.com'
            (run / 'report.md').write_text(report)
            researcher = SimpleNamespace(run=AsyncMock(), summarize=AsyncMock())
            memory = SimpleNamespace(recall=AsyncMock(), enqueue=Mock())
            adapter = CryptoAdapter(researcher, memory)
            msg = SimpleNamespace(content='@superlinked_bot Show me the latest crypto briefing with sources.', sender_id='user')
            with patch('band_bot.ROOT', root), patch('band_bot.relay_reply', new_callable=AsyncMock) as reply:
                async with adapter.lock:
                    await asyncio.wait_for(adapter.on_message(msg, object(), [], None, None, is_session_bootstrap=False, room_id='room'), timeout=0.2)
                self.assertIn(report, reply.await_args.args[1])
                self.assertEqual(reply.await_args.kwargs['mentions'], ['user'])
                researcher.run.assert_not_awaited()
                researcher.summarize.assert_not_awaited()
                memory.recall.assert_not_awaited()
                memory.enqueue.assert_not_called()

    def test_missing_or_incomplete_cache_is_honest(self):
        with tempfile.TemporaryDirectory() as tmp, patch('band_bot.ROOT', Path(tmp)):
            self.assertIn('No completed saved briefing', saved_briefing())
            run = Path(tmp) / 'data/run'
            run.mkdir(parents=True)
            (run.parent / 'latest.txt').write_text(str(run))
            (run / 'status.json').write_text('{"status":"failed"}')
            self.assertIn('No completed saved briefing', saved_briefing())

    def test_specific_questions_and_refresh_do_not_use_generic_report(self):
        for text in ['Explain latest Bitcoin ETF flows', 'Refresh the latest crypto briefing', 'latest news about Ethereum', 'Compare current crypto news with yesterday']:
            self.assertFalse(is_briefing_request(text), text)
        for text in ['latest news', '@[[agent-id]] Show me the latest crypto briefing with sources.', 'Give me the saved report']:
            self.assertTrue(is_briefing_request(text), text)
