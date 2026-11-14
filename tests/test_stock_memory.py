import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from cognee_memory import CogneeMemory
from stock_memory import sync_stock_memory


class StockMemoryTests(unittest.TestCase):
    def test_dated_scores_null_and_dedup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            memory = Mock(enabled=True, destination='cloud', enqueue=Mock(return_value='record'), _save=CogneeMemory._save)
            memory.root = root / 'data/memory'
            memory.dataset.return_value = 'forgeclaw-mesh'
            result = {'asof':'2026-11-14T22:00:00+00:00', 'keywords':['bitcoin'], 'stocks':[
                {'symbol':'COIN','name':'Coinbase','market':'US','impact_score':None,'relevance_score':50,
                 'prices':{'return_2w_pct':-2,'last_close':123.45,'last_date':'2026-11-13','currency':'USD'},'decisions':[]}]}
            sync_stock_memory(root,memory,result)
            table = memory.enqueue.call_args_list[0].args[1]
            self.assertIn('US | -2 | 123.45 | USD | 2026-11-13', table)
            self.assertIn('return_2w_pct', (root / 'data/stocks/portfolio_scores.csv').read_text())
            text = memory.enqueue.call_args.args[1]
            self.assertIn('impact score unavailable',text)
            self.assertIn('keyword relevance score 50',text)
            self.assertIn(result['asof'],text)
            result['asof']='2026-11-14T22:05:00+00:00'
            sync_stock_memory(root,memory,result)
            self.assertEqual(memory.enqueue.call_count,2)
            result['stocks'][0]['impact_score']=-30
            sync_stock_memory(root,memory,result)
            self.assertEqual(memory.enqueue.call_count,4)
            self.assertIn('impact score -30',memory.enqueue.call_args.args[1])

    def test_compact_table_preserves_all_twenty_historical_values(self):
        from stock_memory import render_snapshot, table_from_snapshot
        stocks = [{'symbol':f'S{i}', 'name':f'Stock {i}', 'market':'US', 'impact_score':None if i==0 else -78.1,
                   'relevance_score':0 if i==0 else 60.0, 'return_2w_pct':-1.5, 'currency':'USD',
                   'price_date':'2026-11-13','evidence_status':'test', 'price_source':'https://example.com',
                   'exposure_sources':[], 'news_sources':[]} for i in range(20)]
        report=render_snapshot({'stocks':stocks,'keywords':['bitcoin']},'stock-scores-historical','2026-11-14T00:00:00Z')
        identifier, table=table_from_snapshot(report)
        self.assertEqual(identifier,'stock-scores-historical')
        for i in range(20): self.assertIn(f'\nS{i} |',table)
        self.assertIn('S0 | 0 | Unavailable',table)
        self.assertIn('S1 | 60 | -78.1',table)
        self.assertLess(len(table),4000)
