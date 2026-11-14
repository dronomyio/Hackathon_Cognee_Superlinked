"""Auditable 14-calendar-day adjusted-price observations from Yahoo Finance.

As-of exchange calendar day is excluded, even after market close, to avoid
intraday bars. Returns use the last available close on/before the start date.
Missing/stale evidence is reported explicitly, never filled with model estimates.
"""
from datetime import datetime, timedelta, timezone
import math
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx


PARAMS = {'range': '1mo', 'interval': '1d', 'includeAdjustedClose': 'true'}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def _base(symbol, asof):
    if asof.tzinfo is None or asof.utcoffset() is None:
        raise ValueError('asof must be timezone-aware')
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError('symbol is required')
    return {'symbol': symbol, 'asof': asof.astimezone(timezone.utc).isoformat(),
            'source_url': f'https://finance.yahoo.com/quote/{quote(symbol, safe="")}/history/',
            'provider': 'Yahoo Finance', 'price_basis': 'provider-adjusted daily close',
            'cutoff_policy': 'Exclude as-of exchange calendar day; no intraday bars',
            'daily': [], 'sample_count': 0, 'return_2w_pct': None, 'return_1d_pct': None,
            'stale': False}


def parse_chart(body, symbol, asof):
    """Return JSON-safe prices/returns or explicit unavailable/stale status."""
    result = _base(symbol, asof)
    try:
        chart = body['chart']
        if chart.get('error'):
            raise ValueError('Provider returned chart error')
        payload = chart['result'][0]
        meta = payload['meta']
        zone = ZoneInfo(meta['exchangeTimezoneName'])
        today = asof.astimezone(zone).date()
        start = today - timedelta(days=14)
        result.update(currency=meta['currency'], timezone=meta['exchangeTimezoneName'], window_start=start.isoformat())
        returned_symbol = meta.get('symbol')
        if returned_symbol and returned_symbol.upper() != symbol.upper():
            raise ValueError('Provider symbol mismatch')
        timestamps = payload['timestamp']
        # Never silently replace adjusted prices with raw closes.
        adjusted = payload['indicators']['adjclose'][0]['adjclose']
        if len(timestamps) != len(adjusted):
            raise ValueError('Timestamp and adjusted-price lengths differ')
        volumes = payload['indicators'].get('quote', [{}])[0].get('volume', [])
        points = {}
        skipped = 0
        for index, (stamp, price) in enumerate(zip(timestamps, adjusted)):
            if not _number(stamp) or not _number(price):
                skipped += 1
                continue
            observed = datetime.fromtimestamp(stamp, timezone.utc)
            day = observed.astimezone(zone).date()
            if observed > asof or day >= today:
                continue
            volume = volumes[index] if index < len(volumes) else None
            valid_volume = isinstance(volume, (int, float)) and not isinstance(volume, bool) and math.isfinite(volume) and volume >= 0
            points[day] = {'date': day.isoformat(), 'adjusted_close': float(price),
                           'volume': int(volume) if valid_volume else None}
        days = sorted(points)
        before = [day for day in days if day <= start]
        if not before:
            raise ValueError('No adjusted baseline close on or before window start')
        baseline_day = before[-1]
        if (start - baseline_day).days > 7:
            raise ValueError('Baseline close is more than seven days before window start')
        selected = [day for day in days if day >= baseline_day]
        if len(selected) < 2 or selected[-1] <= start:
            raise ValueError('Insufficient completed daily prices in window')
        last_day = selected[-1]
        baseline, last = points[baseline_day]['adjusted_close'], points[last_day]['adjusted_close']
        result.update(daily=[points[day] for day in selected], sample_count=len(selected),
                      baseline_date=baseline_day.isoformat(), baseline_close=baseline,
                      last_date=last_day.isoformat(), last_close=last,
                      skipped_invalid_points=skipped, stale=(today - last_day).days > 5)
        if result['stale']:
            result.update(status='stale', error='Latest completed price is more than five calendar days old')
            return result
        previous = points[selected[-2]]['adjusted_close']
        result.update(status='complete', return_2w_pct=round((last / baseline - 1) * 100, 6),
                      return_1d_pct=round((last / previous - 1) * 100, 6))
    except (KeyError, IndexError, TypeError, ValueError, OverflowError) as error:
        # Only messages raised here are retained; no arbitrary provider message.
        detail = str(error) if isinstance(error, ValueError) else type(error).__name__
        result.update(status='unavailable', error=detail)
    return result


async def fetch_prices(http, symbol, asof):
    """Fetch chart data using an existing async HTTP client; never sends API keys."""
    base = _base(symbol, asof)
    errors = []
    for host in ('query1.finance.yahoo.com', 'query2.finance.yahoo.com'):
        url = f'https://{host}/v8/finance/chart/{quote(symbol, safe="")}'
        try:
            response = await http.get(url, params=PARAMS, timeout=20,
                                      headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
            response.raise_for_status()
            parsed = parse_chart(response.json(), symbol, asof)
            parsed['data_url'] = str(response.request.url)
            return parsed
        except httpx.HTTPStatusError as error:
            errors.append(f'HTTP {error.response.status_code}')
            if error.response.status_code not in {429, 500, 502, 503, 504}:
                break
        except (httpx.HTTPError, ValueError) as error:
            errors.append(type(error).__name__)
    return {**base, 'status': 'unavailable', 'error': '; '.join(errors)}
