import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from news_agent import Article
from news_decisions import NewsDecisions, parse_answer, saved_decisions


def answer():
    return {'answers': {'priority': {'choice': 'watch', 'probabilities': {'alert': .1, 'watch': .8, 'ignore': .1}}}}


class DecisionTests(unittest.IsolatedAsyncioTestCase):
    async def test_cache_keyword_changes_and_wire_contract(self):
        calls = []
        def handle(request):
            calls.append(json.loads(request.content))
            self.assertEqual(request.url.path, '/v1/systemone')
            return httpx.Response(200, json=answer())
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'SIE_API_KEY': 'test'}):
            root = Path(directory)
            (root / '.env').write_text('KEYWORDS=bitcoin,hack\n')
            a = Article('1', 'Bitcoin update', 'https://example.com/a', 'example', '2026-11-14T00:00:00Z', 'Bitcoin and hack reporting')
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
                stage = NewsDecisions(root, http, 'https://api.superlinked.com')
                first = await stage.check([a])
                second = await stage.check([a])
                self.assertEqual(first['model_calls'], 1)
                self.assertEqual(second['model_calls'], 0)
                self.assertEqual(calls[0]['questions']['priority']['type'], 'choice')
                self.assertIn('WATCH', saved_decisions(root))
                (root / '.env').write_text('KEYWORDS=hack,bitcoin\n')
                self.assertIn('Keywords changed', saved_decisions(root))
                await stage.check([a])
                self.assertEqual(len(calls), 2)
                a.content += ' New details'
                await stage.check([a])
                self.assertEqual(len(calls), 3)

    async def test_failure_backoff_and_no_fake_labels(self):
        calls = []
        def handle(request):
            calls.append(request)
            return httpx.Response(503, json={'secret': 'never persist me'})
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'SIE_API_KEY': 'test'}):
            root = Path(directory)
            (root / '.env').write_text('KEYWORDS=bitcoin\n')
            articles = [Article(str(i), 'Bitcoin', f'https://example.com/{i}', 'example', '2026-11-14T00:00:00Z', '') for i in range(2)]
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
                result = await NewsDecisions(root, http, 'https://api.superlinked.com').check(articles)
                self.assertEqual(len(calls), 1)
                self.assertEqual(result['articles'][0]['decision']['status'], 'unavailable')
                self.assertEqual(result['articles'][1]['decision']['status'], 'pending')
                self.assertNotIn('never persist', (root / 'data/news_decisions.json').read_text())

    def test_invalid_probabilities_rejected(self):
        for probs in [{'alert': float('nan'), 'watch': .8, 'ignore': .2}, {'alert': .9, 'watch': .9, 'ignore': .9}]:
            body = answer()
            body['answers']['priority']['probabilities'] = probs
            with self.assertRaises(ValueError):
                parse_answer(body)
