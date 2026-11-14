import unittest
from news_scoring import parse_keywords, rank


class ScoringTests(unittest.TestCase):
    def article(self, title, content=''):
        return dict(id=title, title=title, content=content, url='https://example.com/' + title, published_at='2026-11-14T00:00:00Z')

    def test_order_duplicates_and_repetition(self):
        terms = parse_keywords(' Bitcoin, ETF, hack, BITCOIN, ,')
        self.assertEqual(terms, ['bitcoin', 'etf', 'hack'])
        rows = rank([self.article('hack hack hack'), self.article('Bitcoin')], terms)
        self.assertEqual(rows[0]['score'], 50)
        self.assertEqual(rows[1]['score'], 16.67)
        self.assertEqual(rank([self.article('Bitcoin ETF hack')], terms)[0]['score'], 100)

    def test_boundaries_phrases_and_empty_configuration(self):
        article = self.article('Method update', 'Spot   ETF approved')
        row = rank([article], ['eth', 'spot etf'])[0]
        self.assertEqual([m['keyword'] for m in row['matches']], ['spot etf'])
        self.assertEqual(row['matches'][0]['location'], 'content')
        self.assertEqual(rank([article], [])[0]['score'], 0)

    def test_dotenv_keywords_override_json_and_reload(self):
        import tempfile
        from pathlib import Path
        from news_scoring import keywords
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'news_priorities.json').write_text('{"keywords":"hack"}')
            (root / '.env').write_text('KEYWORDS=bitcoin,coinbase\n')
            self.assertEqual(keywords(root), ['bitcoin', 'coinbase'])
            (root / '.env').write_text('KEYWORDS=ethereum,bitcoin\n')
            self.assertEqual(keywords(root), ['ethereum', 'bitcoin'])
            (root / '.env').write_text('KEYWORDS=\n')
            self.assertEqual(keywords(root), [])
