import unittest
from stock_swarm import impact_score, linked_articles, parse_direction, direction_payload, render_stocks


class StockSwarmTests(unittest.TestCase):
    def stock(self, linkage='indirect'):
        return {'name':'Example Bank','aliases':['Example Bank'],'linkage':linkage,'exposure':'Payments, not Bitcoin treasury.'}

    def article(self, title):
        return {'id':title,'title':title,'content':'','url':'https://example.com/'+title}

    def test_indirect_requires_company_specific_crypto_evidence(self):
        generic = self.article('Bitcoin fell today')
        self.assertEqual(linked_articles(self.stock(), [generic], []), [])
        self.assertEqual(len(linked_articles(self.stock('direct'), [generic], [])), 1)
        noncrypto = self.article('Example Bank posts earnings')
        self.assertEqual(linked_articles(self.stock(), [], [noncrypto]), [])
        specific = self.article('Example Bank launches crypto custody')
        self.assertEqual(linked_articles(self.stock(), [], [specific])[0]['link_type'], 'company_mentioned')

    def test_unknown_is_not_zero_and_indirect_cap(self):
        self.assertIsNone(impact_score([], 'direct'))
        d={'status':'complete','label':'positive','keyword_score':100,'probabilities':{'positive':1,'negative':0,'neutral':0,'insufficient':0}}
        self.assertEqual(impact_score([d], 'direct'), 100)
        self.assertEqual(impact_score([d], 'indirect'), 25)
        d['label']='insufficient'
        self.assertIsNone(impact_score([d], 'direct'))
        d['label']='neutral';d['probabilities']={'positive':0,'negative':0,'neutral':1,'insufficient':0}
        self.assertEqual(impact_score([d], 'direct'), 0)

    def test_bad_model_output_rejected(self):
        with self.assertRaises(ValueError):
            parse_direction({'answers':{'impact':{'choice':'buy','probabilities':{}}}})

    def test_request_excludes_observed_returns(self):
        stock={**self.stock(), 'return_2w_pct':99.9}
        payload=direction_payload(stock,self.article('Bitcoin rally'), [], 'model')
        self.assertNotIn('99.9', str(payload))
        self.assertIn('not instructions',payload['questions']['impact']['instructions'])


class StockSwarmRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_twenty_agents_produce_snapshot_without_crypto_evidence(self):
        import asyncio
        import json
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        from stock_swarm import StockSwarm
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stocks = [{'symbol':f'S{i}', 'name':f'Company {i}', 'aliases':[f'Company {i}'],
                       'market':'US' if i < 10 else 'India', 'linkage':'indirect', 'membership':'holding',
                       'exposure':'No demonstrated crypto price exposure', 'exposure_sources':[]} for i in range(20)]
            (root / 'data').mkdir()
            (root / 'data/portfolio.json').write_text(json.dumps({'mode':'user_portfolio', 'stocks':stocks}))
            r = SimpleNamespace()
            swarm = StockSwarm(root, r, asyncio.Lock())
            swarm.collect = AsyncMock(return_value={'prices':{'status':'unavailable'}, 'company_news':[], 'search_errors':[]})
            result = await swarm.check()
            self.assertEqual(swarm.collect.await_count, 20)
            self.assertEqual(len(result['stocks']), 20)
            self.assertTrue(all(s['impact_score'] is None for s in result['stocks']))
            self.assertTrue((root / 'data/stocks/report.md').exists())
            self.assertEqual(len(list((root / 'data/stocks').glob('stock-*.json'))), 20)

    def test_catalog_and_comparison_pages_are_not_news(self):
        from stock_swarm import usable_news
        for url, title in [('https://coinbase.com/how-to-buy/infosys', 'Infosys token'), ('https://example.com/tag/sbi','SBI'), ('https://example.com/a','Critical Analysis: Bitcoin firm versus Wipro'), ('https://demo.decrypt.co/123/news','News')]:
            self.assertFalse(usable_news({'url':url,'title':title}))

    def test_uncertain_model_does_not_become_directional_score(self):
        d={'status':'complete','label':'positive','keyword_score':100,'review_needed':True,
           'probabilities':{'positive':.4,'negative':.2,'neutral':.2,'insufficient':.2}}
        self.assertIsNone(impact_score([d], 'direct'))

    def test_boilerplate_crypto_does_not_link_indirect_stock(self):
        stock={'name':'Example Bank','aliases':['Example Bank'],'linkage':'indirect'}
        article={'id':'a','url':'https://example.com/a','title':'Fund buys Example Bank shares','content':'Example Bank provides crypto services.'}
        self.assertEqual(linked_articles(stock, [], [article]), [])

    def test_linkage_requires_company_in_model_excerpt(self):
        stock={'name':'Example Bank','aliases':['Example Bank'],'linkage':'indirect'}
        article={'id':'a','url':'https://example.com/a','title':'Crypto industry news','content':'Other company news. '*100 + 'Example Bank'}
        self.assertEqual(linked_articles(stock, [], [article]), [])

class PortfolioScopeTests(unittest.TestCase):
    def test_generic_watchlist_cannot_be_used_as_portfolio(self):
        import asyncio
        import json
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from stock_swarm import StockSwarm
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            swarm = StockSwarm(root, SimpleNamespace(), asyncio.Lock())
            path = root / 'data/portfolio.json'
            path.write_text(json.dumps({'mode': 'research_watchlist_not_personal_holdings', 'stocks': [{'symbol': 'OUTSIDE'}]}))
            with self.assertRaises(ValueError):
                swarm.watchlist()
            path.write_text(json.dumps({'mode': 'user_portfolio', 'stocks': [{'symbol': 'OUTSIDE', 'membership': 'unconfirmed'}]}))
            with self.assertRaises(ValueError):
                swarm.watchlist()
            path.write_text(json.dumps({'mode': 'user_portfolio', 'stocks': [{'symbol': 'OWNED', 'membership': 'holding'}]}))
            self.assertEqual([s['symbol'] for s in swarm.watchlist()], ['OWNED'])
