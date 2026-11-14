import json
import os
import unittest
from dataclasses import asdict
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from news_agent import Article, Brief, Researcher, canonical_url, parse_brief, render_report, safe_error

CONFIG = {"hours": 48, "results_per_query": 3, "max_articles": 3,
          "max_chars_per_article": 1000, "concurrency": 2,
          "sources": ["youtube.com", "bloomberg.com"], "queries": ["crypto"]}
END = datetime(2026, 11, 14, 20, tzinfo=timezone.utc)


def item(url="https://bloomberg.com/news/articles/btc", date="2026-11-13T20:00:00Z"):
    return {"url": url, "title": "Bitcoin news", "published_at": date, "snippet": "Bitcoin reported news."}


class ResearchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.search = SimpleNamespace(search=AsyncMock(), fetch=AsyncMock(), aclose=AsyncMock())
        self.http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
        self.agent = Researcher(CONFIG, self.search, self.http)

    async def asyncTearDown(self):
        await self.agent.close()

    def test_strict_48_hour_window_and_dedup(self):
        rows = [item(), item(url="https://www.bloomberg.com/news/articles/btc?utm_source=x"),
                item(url="https://bloomberg.com/old", date="2026-11-12T19:59:59Z"),
                item(url="https://bloomberg.com/future", date="2026-11-14T20:00:01Z"),
                item(url="https://bloomberg.com/unknown", date=None),
                item(url="https://bloomberg.com/naive", date="2026-11-13T20:00:00"),
                item(url="https://bloomberg.com/boundary", date="2026-11-12T20:00:00Z")]
        articles, _ = self.agent.select([("bloomberg.com", rows)], END)
        self.assertEqual(len(articles), 2)

    def test_unrelated_and_wrong_hosts_excluded(self):
        rows = [item(url="https://evil.com/bloomberg.com"), item(url="file:///etc/passwd"),
                item(url="https://bloomberg.com/news"), {**item(), "title": "Golf", "snippet": "Golf tournament"}]
        articles, _ = self.agent.select([("bloomberg.com", rows)], END)
        self.assertEqual(articles, [])

    def test_publisher_hubs_and_tracking_redirects_excluded(self):
        from news_agent import is_news_url
        for source, path in [("decrypt.co", "/news/business"), ("decrypt.co", "/category/news/business"),
                             ("coindesk.com", "/click/tracking"), ("theblock.co", "/data/etfs/foo"),
                             ("theblock.co", "/etfs/ethereum/foo")]:
            self.assertFalse(is_news_url("https://" + source + path, source))
        self.assertEqual(canonical_url("https://cointelegraph.com/news/story?timestamp=1&_refresh=2"),
                         "https://cointelegraph.com/news/story")

    def test_video_urls(self):
        expected = "https://youtube.com/watch?v=abcdefghijk"
        self.assertEqual(canonical_url("https://youtu.be/abcdefghijk?si=x"), expected)
        self.assertEqual(canonical_url("https://youtube.com/shorts/abcdefghijk"), expected)
        with self.assertRaises(ValueError):
            canonical_url("https://youtube.com/@channel")

    def test_citation_validation(self):
        reply = json.dumps({"findings": [{"headline": "News", "summary": "Reported change", "source_ids": ["madeup"]}]})
        with self.assertRaises(ValueError):
            parse_brief(reply, {"real"})

    def test_synthesis_caps_source_text_without_mutating_evidence(self):
        self.agent.config = {**CONFIG, "max_synthesis_chars": 100}
        articles = [Article(str(i), "Bitcoin", "https://bloomberg.com/a", "bloomberg.com",
                            END.isoformat(), "a" * 1000) for i in range(2)]
        body = self.agent.synthesis_payload(articles, END)
        evidence = json.loads(body["messages"][1]["content"])["evidence"]
        self.assertEqual(sum(len(a["content"]) for a in evidence), 100)
        self.assertEqual(len(articles[0].content), 1000)

    async def test_paywall_does_not_become_full_text(self):
        a = Article("id", "Bitcoin", "https://bloomberg.com/a", "bloomberg.com", END.isoformat(), "search evidence")
        self.search.fetch.return_value = SimpleNamespace(content="Subscribe to continue " + "x" * 200)
        await self.agent.read_article(a)
        self.assertEqual(a.content, "search evidence")
        self.assertEqual(a.access, "restricted_search_excerpt")

    async def test_auth_failure_is_fatal(self):
        req = httpx.Request("GET", "https://api.keenable.ai")
        self.search.search.side_effect = httpx.HTTPStatusError("secret", request=req, response=httpx.Response(401, request=req))
        with self.assertRaises(httpx.HTTPStatusError):
            await self.agent.discover(END)

    async def test_live_wire_contract_and_validated_summary(self):
        async def handler(request):
            payload = json.loads(request.content)
            self.assertEqual(request.url.path, "/v1/chat/completions")
            self.assertNotIn("test-secret", json.dumps(payload))
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
                "findings": [{"headline": "Bitcoin news", "summary": "Publisher reports a change.", "source_ids": ["abc"]}]
            })}}]})
        await self.http.aclose()
        self.agent.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        a = Article("abc", "Bitcoin news", "https://bloomberg.com/a", "bloomberg.com", END.isoformat(), "evidence")
        with patch.dict(os.environ, {"SIE_API_KEY": "test-secret"}):
            summary = await self.agent.summarize([a], END, "news")
        self.assertEqual(summary.findings[0].source_ids, ["abc"])
        report = render_report(summary, [a], {}, END)
        self.assertIn("https://bloomberg.com/a", report)

    def test_errors_redact_secrets(self):
        self.assertEqual(safe_error(ValueError("secret API key")), "ValueError")

    async def test_real_sdk_lifecycle_without_network(self):
        from band_bot import CryptoAdapter
        with patch.dict(os.environ, {"KEENABLE_API_KEY": "test-key"}):
            researcher = Researcher(CONFIG)
            CryptoAdapter(researcher)
            await researcher.close()

    async def test_cold_start_retry(self):
        calls = []
        async def handler(request):
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(503, headers={"Retry-After": "0"}, json={})
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"findings":[]}'}}]})
        await self.http.aclose()
        self.agent.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch.dict(os.environ, {"SIE_API_KEY": "test-secret"}):
            await self.agent.complete({}, set())
        self.assertEqual(len(calls), 2)

    async def test_pipeline_writes_evidence_and_report(self):
        import tempfile
        from pathlib import Path
        articles, coverage = self.agent.select([("bloomberg.com", [item()])], END)
        self.agent.discover = AsyncMock(return_value=(articles, coverage))
        self.agent.read_article = AsyncMock()
        self.agent.summarize = AsyncMock(return_value=parse_brief(json.dumps({"findings": [{
            "headline": "Bitcoin", "summary": "Publisher reports news.", "source_ids": [articles[0].id]
        }]}), {articles[0].id}))
        with tempfile.TemporaryDirectory() as tmp, patch("news_agent.ROOT", Path(tmp)):
            run = await self.agent.run()
            self.assertEqual(json.loads((run / "status.json").read_text())["status"], "complete")
            self.assertTrue((run / "evidence.json").exists())
            self.assertIn(articles[0].url, (run / "report.md").read_text())
            self.assertEqual((Path(tmp) / "data/latest.txt").read_text(), str(run))


if __name__ == "__main__":
    unittest.main()
