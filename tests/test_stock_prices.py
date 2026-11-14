import unittest
from datetime import datetime, timezone
import httpx
from stock_prices import fetch_prices, parse_chart

ASOF = datetime(2026, 11, 14, 22, tzinfo=timezone.utc)


def chart(dates, prices, zone='America/New_York', symbol='COIN'):
    from zoneinfo import ZoneInfo
    stamps = [int(datetime.fromisoformat(date + 'T09:30:00').replace(tzinfo=ZoneInfo(zone)).timestamp()) for date in dates]
    return {'chart': {'error': None, 'result': [{'meta': {'symbol': symbol, 'currency': 'USD', 'exchangeTimezoneName': zone},
        'timestamp': stamps, 'indicators': {'adjclose': [{'adjclose': prices}]}}]}}


class PriceTests(unittest.IsolatedAsyncioTestCase):
    def test_weekend_start_baseline_and_completed_cutoff(self):
        data = chart(['2026-10-30', '2026-11-02', '2026-11-12', '2026-11-13', '2026-11-14', '2026-11-16'], [100, 101, 105, 110, 500, 999])
        result = parse_chart(data, 'COIN', ASOF)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['baseline_date'], '2026-10-30')
        self.assertEqual(result['last_date'], '2026-11-13')
        self.assertEqual(result['return_2w_pct'], 10)
        self.assertAlmostEqual(result['return_1d_pct'], 4.761905)
        self.assertEqual(result['sample_count'], 4)

    def test_volume_missing_is_not_zero_and_aligns_with_prices(self):
        data = chart(['2026-10-30', '2026-11-02', '2026-11-12', '2026-11-13'], [100, 101, 105, 110])
        data['chart']['result'][0]['indicators']['quote'] = [{'volume': [500, 0, None, -2]}]
        result = parse_chart(data, 'COIN', ASOF)
        self.assertEqual([p['volume'] for p in result['daily']], [500, 0, None, None])

    def test_timezone_and_invalid_values(self):
        data = chart(['2026-10-30', '2026-11-02', '2026-11-03', '2026-11-12', '2026-11-13'], [100, None, float('nan'), 105, 110], 'Asia/Kolkata', 'INFY.NS')
        result = parse_chart(data, 'INFY.NS', datetime(2026, 11, 13, 23, tzinfo=timezone.utc))
        self.assertEqual(result['last_date'], '2026-11-13')
        self.assertEqual(result['skipped_invalid_points'], 2)
        self.assertEqual(result['timezone'], 'Asia/Kolkata')

    def test_stale_keeps_evidence_but_withholds_returns(self):
        result = parse_chart(chart(['2026-10-30', '2026-11-02', '2026-11-06'], [100, 103, 110]), 'COIN', ASOF)
        self.assertEqual(result['status'], 'stale')
        self.assertTrue(result['daily'])
        self.assertIsNone(result['return_2w_pct'])

    def test_missing_adjustment_and_length_mismatch_rejected(self):
        data = chart(['2026-10-30', '2026-11-13'], [100, 110])
        data['chart']['result'][0]['indicators'] = {'quote': [{'close': [100, 110]}]}
        self.assertEqual(parse_chart(data, 'COIN', ASOF)['status'], 'unavailable')
        data = chart(['2026-10-30', '2026-11-13'], [100])
        self.assertEqual(parse_chart(data, 'COIN', ASOF)['status'], 'unavailable')

    async def test_http_fallback_and_failure_redaction(self):
        calls = []
        def handler(request):
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(429, text='secret provider body')
            return httpx.Response(200, json=chart(['2026-10-30', '2026-11-13'], [100, 110]))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await fetch_prices(client, 'COIN', ASOF)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(calls[1].url.host, 'query2.finance.yahoo.com')
        self.assertEqual(calls[1].url.params['includeAdjustedClose'], 'true')
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(403, text='secret'))) as client:
            result = await fetch_prices(client, 'COIN', ASOF)
        self.assertEqual(result['error'], 'HTTP 403')
        self.assertNotIn('secret', str(result))
