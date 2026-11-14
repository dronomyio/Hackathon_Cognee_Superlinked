import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import AsyncMock, Mock
from types import SimpleNamespace

import httpx

from cognee_memory import CogneeMemory


class MemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_cloud_headers_dataset_and_wire_fields(self):
        calls = []
        def handler(request):
            calls.append(request)
            self.assertEqual(request.headers["X-Api-Key"], "test-secret")
            self.assertEqual(request.headers["X-Tenant-Id"], "test-tenant")
            self.assertNotIn("Authorization", request.headers)
            if request.method == "GET":
                return httpx.Response(200, json=[{"name": "forgeclaw-mesh"}])
            if request.url.path == "/api/v1/search":
                return httpx.Response(200, json=["historical context"])
            return httpx.Response(200, json={"status": "completed"})
        env = {"COGNEE_URL": "https://tenant.example", "COGNEE_TENANT_ID": "test-tenant",
               "COGNEE_API_KEY": "test-secret", "COGNEE_DATASET": "forgeclaw-mesh"}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env):
            memory = CogneeMemory(Path(tmp), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
            self.assertEqual(memory.dataset("any-room"), "forgeclaw-mesh")
            await memory.recall("room", "news")
            body = json.loads(calls[-1].content)
            self.assertEqual(body["searchType"], "CHUNKS")
            self.assertTrue(body["onlyContext"])
            memory.enqueue("room", "Dated public news")
            await memory.flush_once()
            process = json.loads(calls[-1].content)
            self.assertEqual(process["datasets"], ["forgeclaw-mesh"])
            self.assertIs(process["runInBackground"], False)
            self.assertNotIn("run_in_background", process)
            await memory.close()

    async def test_307_replays_post_but_rejects_external_redirect(self):
        calls = []
        def handler(request):
            calls.append(request)
            if request.url.path == "/api/v1/search":
                return httpx.Response(307, headers={"Location": "/api/v1/search/"})
            if request.url.path == "/api/v1/bad":
                return httpx.Response(307, headers={"Location": "https://other.example/steal"})
            return httpx.Response(200, json=[])
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"COGNEE_URL": "https://tenant.example"}):
            memory = CogneeMemory(Path(tmp), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
            await memory._request("POST", "/api/v1/search", json={"query": "news"})
            self.assertEqual(calls[0].content, calls[1].content)
            self.assertEqual(calls[1].method, "POST")
            with self.assertRaises(RuntimeError):
                await memory._request("GET", "/api/v1/bad")
            self.assertEqual(len(calls), 3)
            await memory.close()

    async def test_legacy_outbox_is_not_sent_to_new_destination(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"COGNEE_URL": "http://localhost:8010"}):
            memory = CogneeMemory(Path(tmp), httpx.AsyncClient(transport=httpx.MockTransport(lambda r: calls.append(r))))
            key = memory.enqueue("room", "Old local report")
            path = memory.root / "outbox" / (key + ".json")
            record = json.loads(path.read_text())
            record.pop("destination")
            path.write_text(json.dumps(record))
            await memory.flush_once()
            self.assertEqual(calls, [])
            self.assertEqual(json.loads(path.read_text())["status"], "pending")
            await memory.close()

    async def test_band_turn_recalls_and_queues_memory(self):
        from band_bot import CryptoAdapter
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run"
            run.mkdir()
            (run / "report.md").write_text("# Current news\nFresh sources.")
            researcher = SimpleNamespace(run=AsyncMock(return_value=run))
            memory = SimpleNamespace(enabled=True, recall=AsyncMock(return_value="Historical context"), enqueue=Mock())
            msg = SimpleNamespace(content="Explain Bitcoin ETF flows", sender_id="user-1", format_for_llm=lambda: "latest news")
            adapter = CryptoAdapter(researcher, memory)
            with patch("band_bot.ROOT", root), patch("band_bot.relay_reply", new_callable=AsyncMock) as relay:
                await adapter.on_message(msg, object(), [], None, None, is_session_bootstrap=True, room_id="room-a")
                memory.recall.assert_awaited_once_with("room-a", "latest news")
                researcher.run.assert_awaited_once_with("latest news", "Historical context")
                memory.enqueue.assert_called_once_with("room-a", "# Current news\nFresh sources.")
                self.assertIn("queued", relay.await_args.args[1])

    async def test_room_isolation_dedup_and_successful_store(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"status": "completed"})
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"COGNEE_URL": "http://localhost:8010"}):
            memory = CogneeMemory(Path(tmp), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
            self.assertNotEqual(memory.dataset("room-a"), memory.dataset("room-b"))
            first = memory.enqueue("room-a", "# Public news\nSource https://example.com")
            self.assertEqual(first, memory.enqueue("room-a", "# Public news\nSource https://example.com"))
            await memory.flush_once()
            await memory.flush_once()
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0].url.path, "/api/v1/add")
            self.assertIn(memory.dataset("room-a").encode(), calls[0].content)
            body = json.loads(calls[1].content)
            self.assertFalse(body["run_in_background"])
            self.assertEqual(body["datasets"], [memory.dataset("room-a")])
            receipt = json.loads(next((Path(tmp)/"data/memory/outbox").glob("*.json")).read_text())
            self.assertEqual(receipt["status"], "stored")
            await memory.close()

    async def test_failed_pipeline_stays_pending_without_secret_logs(self):
        def handler(request):
            return httpx.Response(200, json={"status": "failed", "error": "secret key"})
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"COGNEE_URL": "http://localhost:8010"}):
            memory = CogneeMemory(Path(tmp), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
            memory.enqueue("room", "News")
            await memory.flush_once()
            text = next((Path(tmp)/"data/memory/outbox").glob("*.json")).read_text()
            self.assertEqual(json.loads(text)["status"], "pending")
            self.assertNotIn("secret key", text)
            await memory.close()

    async def test_recall_is_scoped_to_room(self):
        calls = []
        def handler(request):
            calls.append(request)
            if request.method == "GET":
                return httpx.Response(200, json=[{"name": memory.dataset("room-a")}])
            return httpx.Response(200, json=["Historical sourced memory"])
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"COGNEE_URL": "http://localhost:8010"}):
            memory = CogneeMemory(Path(tmp), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
            self.assertEqual(await memory.recall("room-b", "news"), "")
            self.assertIn("Historical", await memory.recall("room-a", "news"))
            body = json.loads(calls[-1].content)
            self.assertEqual(body["datasets"], [memory.dataset("room-a")])
            self.assertEqual(body["search_type"], "CHUNKS")
            await memory.close()
