"""Explainable relevance ranking; keyword order determines weight, not truth."""
import json
import re
import os
from pathlib import Path
from dotenv import dotenv_values


def parse_keywords(value):
    result = []
    for item in value.split(','):
        item = ' '.join(item.casefold().split())
        if item and item not in result:
            result.append(item)
    if len(result) > 50 or any(len(item) > 100 for item in result):
        raise ValueError('Use at most 50 keywords, each at most 100 characters.')
    return result


def keywords(root):
    # Read on every check so edits are picked up by the running service.
    value = dotenv_values(root / '.env').get('KEYWORDS', os.environ.get('KEYWORDS'))
    if value is not None:
        return parse_keywords(value)
    path = root / 'news_priorities.json'
    return parse_keywords(json.loads(path.read_text()).get('keywords', '')) if path.exists() else []


def configure(root, value):
    terms = parse_keywords(value)
    path = root / 'news_priorities.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'keywords': ', '.join(terms)}, indent=2) + '\n')
    temporary.replace(path)
    return terms


def rank(articles, terms):
    total = len(terms) * (len(terms) + 1) / 2
    rows = []
    for article in articles:
        data = article if isinstance(article, dict) else vars(article)
        matches = []
        for index, term in enumerate(terms):
            pattern = r'(?<!\w)' + r'\s+'.join(re.escape(p) for p in term.split()) + r'(?!\w)'
            location = next((field for field in ('title', 'content') if re.search(pattern, data.get(field, '').casefold())), None)
            if location:
                matches.append({'keyword': term, 'weight': len(terms) - index, 'location': location})
        points = sum(m['weight'] for m in matches)
        rows.append({'id': data['id'], 'title': data['title'], 'url': data['url'],
                     'published_at': data['published_at'], 'access': data.get('access', ''),
                     'score': round(100 * points / total, 2) if total else 0,
                     'matches': matches})
    return sorted(rows, key=lambda r: (-r['score'], r['url']))


def save_ranking(root, articles):
    terms = keywords(root)
    result = {'keywords': terms, 'method': 'Ordered keyword relevance; not credibility or investment advice',
              'articles': rank(articles, terms)}
    path = root / 'data' / 'news_scores.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, indent=2))
    temporary.replace(path)
    return result


def latest_ranking(root):
    if not keywords(root):
        return 'No scoring keywords configured yet. Add your comma-separated keywords in news_priorities.json, highest priority first.'
    try:
        run = Path((root / 'data/latest.txt').read_text().strip())
        state = json.loads((run / 'status.json').read_text())
        result = save_ranking(root, state['articles'])
    except (OSError, KeyError, ValueError):
        return 'No completed news evidence is available to score yet.'
    lines = ['# Keyword relevance ranking', 'Evidence window ends: ' + state['window_end'],
             'Priority order: ' + ', '.join(result['keywords']),
             'Scores measure keyword relevance, not truth, sentiment, or trading value.']
    for row in result['articles'][:10]:
        reason = ', '.join(f"{m['keyword']} (weight {m['weight']}, {m['location']})" for m in row['matches']) or 'No keyword matches'
        lines.append(f"\n**{row['score']}/100** — [{row['title']}]({row['url']})\n{reason}")
    return '\n'.join(lines)
