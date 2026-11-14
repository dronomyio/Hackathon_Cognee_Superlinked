"""Versioned stock-score snapshots for Cognee graph extraction and exact recall."""
import csv
import hashlib
import json
import re


def render_score_table(data, snapshot_id, asof):
    lines = [f'# Complete score table: all {len(data["stocks"])} stocks in {snapshot_id}',
             'Assessment timestamp UTC: ' + asof,
             ('User portfolio assessment.' if data.get('mode') == 'user_portfolio' else 'Historical research watchlist, not personal holdings.') + ' Keyword relevance is 0–100; potential crypto-news impact is -100 to +100, an unvalidated hypothesis, not a predicted return.',
             'Unavailable means insufficient evidence or model uncertainty, not zero. This compact record contains the complete stock list for this exact snapshot.',
             'Stock | Keyword relevance | Potential crypto-news impact | Market | Two-week change (%) | Adjusted close | Currency | Price date',
             '--- | ---: | ---: | --- | ---: | ---: | --- | ---']
    for stock in data['stocks']:
        relevance = 'Unavailable' if stock['relevance_score'] is None else format(stock['relevance_score'], 'g')
        impact = 'Unavailable' if stock['impact_score'] is None else format(stock['impact_score'], 'g')
        values = [stock.get(k) for k in ('market', 'return_2w_pct', 'last_close', 'currency', 'price_date')]
        extra = ' | '.join('Unavailable' if v is None else str(v) for v in values)
        lines.append(f"{stock['symbol']} | {relevance} | {impact} | {extra}")
    return '\n'.join(lines)


def table_from_snapshot(report):
    """Recover exact historic values from our durable uploaded source, not latest scores."""
    snapshot_id = re.search(r'^# Superlinked stock score snapshot (\S+)', report).group(1)
    asof = re.search(r'^Assessment timestamp UTC: (.+)$', report, re.M).group(1)
    stocks = []
    for section in report.split('\n## Stock Assessment ')[1:]:
        symbol = section.split()[0]
        relevance = re.search(r'has keyword relevance score (.+?) out of 100\.', section).group(1)
        impact = re.search(r'has potential crypto-news impact score (.+?)\.\n', section).group(1)
        stocks.append({'symbol': symbol,
                       'relevance_score': None if relevance.startswith('unavailable') else float(relevance),
                       'impact_score': None if impact.startswith('unavailable') else float(impact)})
    if not stocks or len({s['symbol'] for s in stocks}) != len(stocks):
        raise ValueError('Invalid historical stock snapshot')
    return snapshot_id, render_score_table({'stocks': stocks}, snapshot_id, asof)


def snapshot_data(result):
    stocks = []
    for stock in result['stocks']:
        prices = stock.get('prices', {})
        stocks.append({key: stock.get(key) for key in
                       ('symbol', 'name', 'market', 'impact_score', 'relevance_score', 'evidence_status')}
                      | {'price_date': prices.get('last_date'), 'return_2w_pct': prices.get('return_2w_pct'),
                         'last_close': prices.get('last_close'), 'currency': prices.get('currency'), 'price_source': prices.get('source_url'),
                         'news_sources': sorted({d['url'] for d in stock.get('decisions', [])}),
                         'exposure_sources': stock.get('exposure_sources', [])})
    return {'export_version': 2, 'mode': result.get('mode', 'research_watchlist_not_personal_holdings'), 'keywords': result['keywords'], 'stocks': sorted(stocks, key=lambda s: s['symbol'])}


def render_snapshot(data, snapshot_id, asof):
    lines = ['# Superlinked stock score snapshot ' + snapshot_id,
             'Assessment timestamp UTC: ' + asof,
             'Author: suvasis/superlinked-bot. Dataset content: ' + ('user portfolio.' if data.get('mode') == 'user_portfolio' else 'historical research watchlist, not personal holdings.'),
             'Each Stock Assessment below is a separate dated assessment of a stock. It is not a permanent property of the stock. Use the newest assessment timestamp when asked for latest scores.',
             'Keyword relevance is 0 to 100. Potential impact is -100 adverse to +100 favorable; an unvalidated model hypothesis, not a predicted return or buy/sell signal.',
             'Unavailable impact means insufficient evidence or model uncertainty, never zero. Price returns are observed in local currency and are not caused by the score.',
             'Ordered keywords: ' + ', '.join(data['keywords'])]
    for stock in data['stocks']:
        symbol = stock['symbol']
        label = f'Stock Assessment {symbol} {snapshot_id}'
        impact = 'unavailable (insufficient evidence or uncertainty)' if stock['impact_score'] is None else str(stock['impact_score'])
        relevance = 'unavailable' if stock['relevance_score'] is None else str(stock['relevance_score'])
        ret = 'unavailable' if stock['return_2w_pct'] is None else str(stock['return_2w_pct']) + '%'
        lines += ['', '## ' + label,
                  f"Stock {symbol} identifies {stock['name']} in the {stock['market']} configured stock list.",
                  f'{label} assesses stock {symbol}. {label} belongs to snapshot {snapshot_id} at {asof}.',
                  f'{label} has keyword relevance score {relevance} out of 100.',
                  f'{label} has potential crypto-news impact score {impact}.',
                  f"{label} has observed two-week adjusted-close return {ret}, currency {stock['currency']}, price date {stock['price_date']}.",
                  f"{label} has evidence status {stock['evidence_status']}.",
                  'Price evidence: ' + str(stock['price_source']),
                  'Business exposure evidence: ' + ', '.join(stock['exposure_sources']),
                  'Crypto news supporting or reviewed for this assessment: ' + (', '.join(stock['news_sources']) or 'No eligible linked story.')]
    return '\n'.join(lines)


def sync_stock_memory(root, memory, result):
    if not memory or not memory.enabled:
        return None
    data = snapshot_data(result)
    folder = root / 'data/stocks'
    folder.mkdir(parents=True, exist_ok=True)
    fields = ['symbol', 'market', 'relevance_score', 'impact_score', 'return_2w_pct',
              'last_close', 'currency', 'price_date', 'evidence_status', 'price_source']
    with (folder / 'portfolio_scores.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['assessment_timestamp'] + fields)
        writer.writeheader()
        for stock in data['stocks']:
            writer.writerow({'assessment_timestamp': result['asof'], **{
                k: 'Unavailable' if stock.get(k) is None else stock[k] for k in fields}})
    digest = hashlib.sha256(json.dumps({'data': data, 'destination': memory.destination,
                                       'dataset': memory.dataset('stock-swarm')}, sort_keys=True).encode()).hexdigest()
    path = root / 'data/stocks/cognee_sync.json'
    if path.exists():
        prior = json.loads(path.read_text())
        if prior.get('digest') == digest:
            if not prior.get('table_record_id'):
                table = render_score_table(data, prior['snapshot_id'], prior['asof'])
                prior['table_record_id'] = memory.enqueue('stock-swarm', table)
                memory._save(path, prior)
            receipt_path = memory.root / 'outbox' / (prior['record_id'] + '.json')
            if receipt_path.exists():
                receipt = json.loads(receipt_path.read_text())
                prior['status'] = receipt['status']
                prior['stored_at'] = receipt.get('stored_at')
                memory._save(path, prior)
            return prior  # Clock ticks alone must not create duplicate graph snapshots.
    snapshot_id = 'stock-scores-' + digest[:16]
    report = render_snapshot(data, snapshot_id, result['asof'])
    table = render_score_table(data, snapshot_id, result['asof'])
    table_record_id = memory.enqueue('stock-swarm', table)
    record_id = memory.enqueue('stock-swarm', report)
    root.joinpath('data/stocks').mkdir(parents=True, exist_ok=True)
    (root / 'data/stocks/cognee_snapshot.md').write_text(report)
    (root / 'data/stocks/cognee_score_table.txt').write_text(table)
    state = {'digest': digest, 'snapshot_id': snapshot_id, 'asof': result['asof'],
             'record_id': record_id, 'dataset': memory.dataset('stock-swarm'),
             'status': 'queued', 'stock_count': len(data['stocks'])}
    state['table_record_id'] = table_record_id
    memory._save(path, state)
    return state
