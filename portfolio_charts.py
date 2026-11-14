"""Two-week price/volume artifacts, strictly scoped to the private user portfolio."""
import asyncio
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import re

import httpx
from stock_prices import fetch_prices


def render_charts(result, folder):
    os.environ.setdefault('MPLCONFIGDIR', str(folder / '.matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    folder.mkdir(parents=True, exist_ok=True)
    cards = []
    for stock in result['stocks']:
        symbol = stock['symbol']
        prices = stock.get('prices', {})
        rows = [r for r in prices.get('daily', []) if r['date'] >= prices.get('window_start', '')]
        title = escape(symbol)
        membership = escape(stock.get('membership', 'holding'))
        detail = f'{membership}; recorded quantity: {stock.get("quantity") if stock.get("quantity") is not None else "not recorded"}'
        if not rows:
            cards.append(f'<section><h2>{title}</h2><p>{detail}</p><p>Price and volume unavailable: {escape(prices.get("error", "No provider data"))}. No substitute stock used.</p></section>')
            continue
        dates = [datetime.fromisoformat(r['date']) for r in rows]
        fig, (ax, vol) = plt.subplots(2, 1, figsize=(10, 4.8), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
        ax.plot(dates, [r['adjusted_close'] for r in rows], marker='o', color='#3659cc')
        ax.set_ylabel('Adjusted close (' + prices.get('currency', '') + ')')
        ax.set_title(symbol + ' — past two weeks (' + prices.get('status', 'unknown') + ')')
        ax.grid(alpha=.2)
        volume_rows = [(d, r['volume']) for d, r in zip(dates, rows) if r.get('volume') is not None]
        if volume_rows:
            vol.bar([r[0] for r in volume_rows], [r[1] for r in volume_rows], color='#159788', width=.7)
        else:
            vol.text(.5, .5, 'Volume unavailable', transform=vol.transAxes, ha='center')
        vol.set_ylabel('Volume\n(shares)')
        vol.grid(axis='y', alpha=.2)
        fig.autofmt_xdate()
        fig.tight_layout()
        filename = re.sub(r'[^A-Za-z0-9_.-]', '_', symbol) + '.png'
        fig.savefig(folder / filename, dpi=120)
        plt.close(fig)
        missing = sum(r.get('volume') is None for r in rows)
        note = f'{missing} sessions missing volume.' if missing else 'Daily reported share volume; missing sessions are not filled.'
        cards.append(f'<section><h2>{title}</h2><p>{detail}</p><img src="{filename}" alt="{title} price and volume"><p>{note} Last price: {prices.get("last_close")} {escape(prices.get("currency", ""))}, {escape(prices.get("last_date", ""))}.</p><a href="{escape(prices.get("source_url", ""), quote=True)}">Yahoo Finance source</a></section>')
    page = '<!doctype html><meta charset="utf-8"><title>Portfolio price and volume</title><style>body{font:16px system-ui;margin:32px;background:#f5f7fa;color:#172439}section{background:white;padding:24px;margin:20px 0;border-radius:12px}img{max-width:100%}input{padding:12px;width:300px}</style><h1>Portfolio price and volume</h1><p>As of ' + escape(result['asof']) + '. Source: saved Cognee portfolio. Completed sessions only; charts use adjusted close and reported volume. Indian quantities were recorded October 12, 2026. US membership confirmed November 14, 2026; US quantities not supplied.</p><p>' + escape(result.get('us_status', '')) + '</p><input id="filter" placeholder="Filter ticker" oninput="document.querySelectorAll(\'section\').forEach(s=>s.hidden=!s.querySelector(\'h2\').textContent.toLowerCase().includes(this.value.toLowerCase()))">' + ''.join(cards)
    temp = folder / 'index.tmp'
    temp.write_text(page)
    temp.replace(folder / 'index.html')
    return folder / 'index.html'


async def refresh(root):
    config = json.loads((root / 'data/portfolio.json').read_text())
    if config.get('mode') != 'user_portfolio':
        raise ValueError('User portfolio required')
    now = datetime.now(timezone.utc)
    limit = asyncio.Semaphore(3)
    async with httpx.AsyncClient() as http:
        async def collect(stock):
            async with limit:
                prices = await fetch_prices(http, stock['symbol'], now)
                print(stock['symbol'], prices['status'], flush=True)
                return {**stock, 'prices': prices}
        stocks = await asyncio.gather(*(collect(s) for s in config['stocks']))
    result = {**config, 'asof': now.isoformat(), 'stocks': stocks}
    (root / 'data/stocks/portfolio_prices.json').write_text(json.dumps(result, indent=2))
    render_charts(result, root / 'data/stocks/charts')


if __name__ == '__main__':
    asyncio.run(refresh(Path(__file__).resolve().parent))
