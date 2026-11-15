# Hackathon_Cognee_Superlinked

Keenable discovers and reads cryptocurrency news; Superlinked SIE produces cited
briefings; Band connects the worker as `suvasis/superlinked-bot`.

## First live validation

[Read the briefing](data/live/report.md), [source catalog](data/live/sources.md),
or [connection status](data/connection-status.json). The live API validation
produced eight findings from 64 dated sources for November 12–14, 2026, including
24 YouTube metadata results and four Bloomberg results. Transcripts were not
verified in this session. Thirteen offline tests pass. Live requests used direct
HTTP because the Python worker could not connect from this sandbox.

## Run

Requires Python 3.12 and outbound HTTPS/WebSocket access.

```sh
cd superlinked-bot
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
# On a new machine only: copy .env.example to .env and supply credentials.
# This workspace already has a private .env; do not overwrite it.
.venv/bin/python app.py doctor
.venv/bin/python app.py run
.venv/bin/python app.py band
```

`doctor` checks authentication, model availability, and Band room membership.
`run` writes a fresh briefing to `data/runs/<UTC timestamp>/report.md`, with
machine-readable evidence and execution status alongside it. `data/latest.txt`
points to the most recent successful run. To focus the briefing:

```sh
.venv/bin/python app.py run --question 'What changed for Bitcoin ETFs and stablecoins?'
```

`band` stays connected while the process runs. Add the existing bot to a room
in [Band](https://app.band.ai) and mention `@suvasis/superlinked-bot` with a
question. Band's SDK handles message delivery, claims, reconnection, and replies.
The worker serializes research requests and reuses evidence younger than 15
minutes, displaying its actual collection window. Stop with Ctrl-C.
On this Mac, `start-band.command` also starts the worker in a regular terminal.

## Local background hosting on macOS

The background-service configuration is prepared, but activation from the Codex
session failed with `launchctl bootstrap` error 5. No background worker is
currently running. From a regular Mac Terminal, run:

```sh
cd /Users/macmachine/tools/drone_project_idea/Blogs/hackathon/superlinked-bot
./service.sh start
./service.sh status
./service.sh logs
```

Once started, the terminal can close. `launchd` runs the worker in your current
login session and restarts it after failures, with a 60-second throttle. Logs
are in `data/service/`; credentials remain in `.env`, never in the service plist.
Confirm the logs show the Band connection before relying on it.

Use `./service.sh stop` to shut it down or `./service.sh restart` to restart it.
Start it again after logout/reboot; no login-item installation is performed.
The Mac must remain awake and connected to the internet. This worker opens no
inbound web port and creates no recurring news job or Superlinked console agent.

## Research behavior

- `sources.json` configures eight publishers/platforms, including YouTube,
  Bloomberg, Reuters, CoinDesk, Cointelegraph, Decrypt, The Block, and CNBC.
- Each run searches two topic groups per source, selecting at most 100 unique
  articles from the preceding 48 hours. Dates are checked in UTC, inclusive of
  both boundaries; undated, future, stale, and obvious landing pages are excluded.
- Source coverage is bounded: search indexes cannot promise every news item.
  The report lists search hits, accepted items, selected items, and search errors.
- Public English YouTube captions are attempted. Missing/blocked transcripts
  remain **video metadata only**; descriptions are never called transcripts.
- Bloomberg and other restricted pages use labeled search excerpts when full
  page access is unavailable. The worker does not bypass subscription access.
- Fetches are capped at 6,000 characters per source. One synthesis call uses at
  most 60,000 characters of source text, divided evenly across the selected
  items (metadata adds overhead). Full fetched excerpts remain in the evidence
  file. Structured output and source IDs are validated;
  invalid citations fail the run. Citation validation does not independently
  fact-check every model claim.
- API credentials stay in environment variables and are never included in model
  context. Source text cannot invoke tools or change the agent's configuration.

## Configuration and verification

### Cognee Cloud memory

The configured destination is:

- Tenant: `08778ee6-4489-4c05-9e04-f423294d0dec`
- Base URL: `https://tenant-08778ee6-4489-4c05-9e04-f423294d0dec.aws.cognee.ai`
- Existing dataset: **`forgeclaw-mesh`**

The cloud API key is still missing. Set `COGNEE_API_KEY` privately in `.env`, then run:

```sh
./start-memory.command
```

This command now uses Cloud only; it does not start Docker. It verifies API-key
and tenant authentication, dataset access, and recall without adding documents,
then restarts the Band worker. The supplied user ID is informational; the API key
establishes the authenticated user. Requests send `X-Api-Key` and `X-Tenant-Id`.
The request field names follow this tenant's live OpenAPI schema, including
`searchType`, `topK`, and `runInBackground`.

The bot reads historical context from `forgeclaw-mesh` and appends generated,
source-linked news briefings there. This explicitly configured dataset is shared
across this bot's rooms; it does not create per-room datasets. Existing documents
are not deleted or replaced. Current news citations must still come from fresh
dated evidence, never solely from historical memory.

Writes use the durable `data/memory/outbox/` queue. One report is indexed at a
time; failures stay queued for retry. Queue records are bound to the destination
tenant, so old local test records will not be uploaded to the cloud. Retrieval
failures are disclosed without preventing fresh news answers. Room questions may
be sent as search queries, but only generated public-news reports are queued as
memory documents. Credentials are never included in those reports.

HTTP 307/308 redirects are replayed only on the same origin, preserving POST
bodies without forwarding credentials to another host. The mistakenly provisioned
local Cognee container has been stopped; its Docker volume is preserved.
`compose.memory.yaml` remains only as an unused local fallback configuration.

[Cloud API schema](https://tenant-08778ee6-4489-4c05-9e04-f423294d0dec.aws.cognee.ai/openapi.json)

### Credentials and tests

`.env.example` lists all variables. The supplied credentials are stored only in
the ignored, owner-readable `.env`. `data/` is also ignored and contains fetched
evidence and local validation requests; do not publish it wholesale.
The default model is `zai-org/GLM-5.3-Flash:relay`, with a 24,576-token output
budget so reasoning does not consume the entire allowance before the answer.
SIE calls are sequential; rate limits and cold starts receive at most two retries.
Changing the model may require lowering `SIE_MAX_OUTPUT_TOKENS` to its supported
limit. Inference consumes the account's credits; no credits are purchased by this
application.

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Tests cover time boundaries, deduplication, URL/source validation, paywalls,
unknown citations, fatal authentication errors, the SIE request contract, and
actual SDK construction/cleanup. No provider credentials are needed for tests.

## API references and deployment limits

- [Superlinked inference API](https://superlinked.com/docs/reference/api):
  authenticated model discovery and `/v1/chat/completions`.
- [Keenable search](https://docs.keenable.ai/api-reference/search) and
  [fetch](https://docs.keenable.ai/api-reference/fetch): publication filters and
  page excerpts, using its official Python SDK.
- [Band custom adapters](https://docs.band.ai/advanced/creating-adapters):
  `SimpleAdapter`, `Agent.create`, and SDK-managed room delivery.
- [Keenable Hive Mind](https://artifacts.keenable.ai/hivemind/) is a hackathon
  onboarding/credits page, not a separate messaging API.

The supplied Superlinked console agents/jobs/models pages redirect to browser
sign-in. An inference key authenticates inference calls; no undocumented
console-management endpoints are assumed. Console registration or cloud job
deployment still requires access to that authenticated management surface.

In this Codex session, direct authenticated HTTP checks succeeded for all three
providers, but Python outbound connections failed with DNS/connection errors.
Consequently, the continuous Band worker has not been verified online here.
Run `doctor` and `band` from a network-enabled terminal before relying on it.

## Continuous news checks

The Band worker checks the rolling 48-hour window on startup and every five
minutes (`NEWS_CHECK_INTERVAL_SECONDS=300`). New source URLs trigger a briefing
and a durable Cognee upload. With no new URLs, it logs `No new crypto news
compared with recorded memory` and skips inference and duplicate memory documents.
Failed uploads retry in the background; search failures are incomplete checks.

The durable ledger tracks this worker's news queued for Cognee, not every
unrelated document in the shared dataset. Edits at an existing URL do not count
as new articles. Memory indexing, checks, and Band replies run serially; slow
operations skip elapsed ticks. See `data/service/schedule.json` and
`./service.sh logs`. The Mac must remain awake and logged in. Briefings are
available through Band replies; automatic room broadcasts are not configured.

Requests such as `Show me the latest crypto briefing with sources` return the
latest completed report directly, bypassing research and memory indexing locks.
The reply labels it as saved and retains its collection window and citations;
retrieving it does not create another Cognee document. If no completed report
exists, the bot says so immediately. Specific analysis and explicit refresh
requests still use the serialized research path.

## Ordered keyword scoring

Edit `news_priorities.json` with comma-separated keywords, highest priority first,
or run `.venv/bin/python app.py keywords --keywords 'bitcoin, ETF, hack'`.
The empty default leaves priorities unset; changes are picked up without restart.
Ask the Band bot `score news` or run `.venv/bin/python app.py score` for the top
10 articles from the latest completed evidence. Each five-minute discovery also
writes `data/news_scores.json`, even when there are no new URLs.

For N unique keywords, weights are N, N−1, …, 1. Score = 100 × matched weights /
all weights. Matching is case-insensitive, respects word boundaries, supports
phrases, and counts each keyword once across title and available content.
For `bitcoin, ETF, hack`, Bitcoin alone scores 50; hack alone scores 16.67.
This is additive relevance: several lower-priority terms can outweigh one higher
term. It does not infer synonyms, validate claims, or score price direction.

A future model workflow could extract cited entities/events into structured JSON,
then have a decision model label relevant stories `alert`, `watch`, or `ignore`
with evidence and uncertainty. Keep the deterministic relevance score separate
from that judgment. Keyword scoring and the decision stage below are enabled. A separate extraction
stage and automatic score-based alerts are not enabled.

`KEYWORDS=bitcoin,ethereum,PAX,coinbase,hack` in `.env` takes precedence over
`news_priorities.json`. The scorer reads it on each request/check, so edits do
not require restart. An explicitly empty KEYWORDS disables scoring. If KEYWORDS
is present, edit that value rather than using the JSON-based `keywords` command.

Decision-model candidate verified in the authenticated SIE catalog:
`fastino/GLiNER2.5-Decide`. It accepts classification labels and could classify
news as alert/watch/ignore. It is integrated as described below. Keyword relevance scores remain deterministic;
model accuracy on crypto news has not been independently evaluated.
Model reference: https://huggingface.co/fastino/GLiNER2.5-Decide

## Decision model

The running worker calls `fastino/GLiNER2.5-Decide` at Superlinked's
`POST /v1/systemone` using the existing SIE key. Every check classifies up to
10 keyword-matching articles by relevance as `alert`, `watch`, or `ignore`.
This also happens on no-new-news checks, allowing changed keywords to take effect.
Each call sees the title (180 characters) and a search excerpt (650 characters),
plus priority instructions. This is bounded evidence, not full-article analysis.

Results and all three probabilities are in `data/news_decisions.json`; exact
inputs, keyword order, policy and model determine the durable cache key. Repeated
inputs use the cache, avoiding duplicate inference. Changed inputs are classified
again. Provider failures are marked unavailable/pending and retry next check;
they never become invented labels or stop ordinary news collection. Probabilities
below 0.65 for every option flag the decision for review; this threshold is a
heuristic, not validated calibration.

Ask Band `show decisions` or `show alerts` for saved classifications without
waiting for model calls. `score news` still shows deterministic keyword scores.
Decisions are saved locally; they do not send automatic room alerts, execute
trades, or add duplicate Cognee documents. The scheduled briefing still goes to
Cognee as before. All provider inference shares the existing concurrency lock.

Configure `SIE_DECISION_MODEL` (default `fastino/GLiNER2.5-Decide`) and
`NEWS_DECISION_LIMIT` (default 10, maximum 20) in `.env`; restart for these two
settings. `KEYWORDS` remains hot-reloaded.
API reference: https://superlinked.com/docs/migrate/typesafe

## 20-stock research swarm

Twenty logical stock agents run inside this local worker: ten US and ten India,
with three concurrent data collectors and serialized decision-model calls. These
are not twenty separately registered Band accounts. `stock_watchlist.json` is a
research watchlist, not the user's holdings or a recommended portfolio. Its
company exposure claims include primary source links. India names have indirect
business channels; RBI digital-rupee participation is not private-crypto exposure.

Each agent collects dated company-news search excerpts from the preceding 14
calendar days and Yahoo Finance provider-adjusted daily closes. Prices use the
last available close on/before the window start and the latest completed day;
the current exchange calendar day is excluded, even after close. Prices remain
in USD or INR without currency conversion. Missing data is N/A, never estimated.
Collection is cached for 15 minutes; the swarm checks every five minutes and
reuses model decisions for identical evidence/policy/model. Crypto evidence comes
from the existing bot's last 48-hour source window and is filtered by date again.

Up to two linked stories per stock are assessed as positive, negative, neutral,
or insufficient by GLiNER2.5-Decide using short excerpts. Direct exposures can
receive sector hypotheses; indirect exposures require a company mention in a
crypto story. Model outcomes are not proof of causation or calibrated forecasts.

Impact score = 100 × weighted mean(Ppositive − Pnegative), with per-story weight
0.25 + 0.75 × keyword_relevance/100. Indirect exposures get an additional 0.25
multiplier (maximum ±25), a conservative heuristic rather than estimated beta.
Insufficient outcomes are excluded; no usable outcomes means N/A, not neutral.
Observed share returns never enter the model or score. Tables rank absolute
impact for investigation, not investment merit. Company news is included as
possible competing explanations, not asserted causes.

Band command: `show stocks` (also `stock scores`). CLI: `app.py stocks`.
Full output: `data/stocks/report.md` and `data/stocks/latest.json`; each stock has
its own `stock-<symbol>.json` with sources, probabilities, and input excerpts.
The JSON includes daily prices for inspection. Results are local and do not
execute trades, send automatic room messages, or create Cognee duplicates.
Set `STOCK_CHECK_INTERVAL_SECONDS` (minimum/default 300) and restart to change
frequency. To analyze actual holdings, replace watchlist entries with your
10 US and 10 Indian holdings; portfolio P&L needs quantities or weights separately.

Quality gates exclude rolling topic/quote pages, token purchase pages, demo sites,
and automated comparison titles. Directional model outcomes with maximum class
probability below 0.65 require review and are excluded from the aggregate score.
This is a conservative heuristic; it does not establish calibrated confidence.

Stock tables also show a 0–100 relevance score (highest ordered-keyword match
among eligible linked stories). Zero means no matched terms, not no financial
risk. Stock news searches include separate general-company and crypto queries.
Linkage is checked against the same bounded excerpt sent to the model. Indirect
links require crypto in the headline to reduce boilerplate false matches.
Positive classifications that conflict with explicit adverse headline language
are flagged for review and excluded from the directional impact score.

## Cognee stock graph

Stock assessments now sync to the configured Cognee dataset (`forgeclaw-mesh`).
A snapshot identifies all 20 stocks and explicitly links each stock to a dated
assessment, relevance score, potential impact score, observed return, and sources.
Unknown scores stay unavailable. These are historical, unvalidated research
assessments; they are not permanent company facts or personal holdings.

Only meaningful score, price, keyword, or source changes queue another snapshot;
clock ticks alone do not. Upload/indexing uses the existing durable memory outbox.
`data/stocks/cognee_snapshot.md` shows the exact stock snapshot queued for upload;
`cognee_sync.json` records its identifier and outbox record. Graph extraction is
performed by Cognee, so node names/layout are generated rather than a custom
colored stock-score dashboard. In Cognee, choose Graph and `forgeclaw-mesh`, then
look for a company/ticker or the `stock-scores-...` snapshot identifier. Search can
retrieve the exact scores and assessment timestamp from the source document.

Each snapshot also uploads a compact, single-record table of all 20 stock scores.
This avoids relying on retrieval to gather twenty separate graph nodes/chunks.
Historical snapshot tables preserve original values; they never borrow current
scores. For complete numeric output, ask Cognee for the `Complete score table`
of the desired snapshot and select only `forgeclaw-mesh`. Cognee's own UI search
can still return partial context; the local/Band `show stocks` command reads the
complete structured report directly. Graph selection and Search may reference
different snapshots, so compare the identifiers and timestamps.

### Holdings-only monitoring and charts

Stock monitoring now requires private `data/portfolio.json` with `mode: user_portfolio`.
Each entry must have `membership: holding` (or an explicitly confirmed
`user_confirmed_watchlist`), plus its symbol, market, name and evidence fields.
The former generic 20-stock catalogs are retired and are never used as fallback.
Missing symbols remain unavailable; no substitute stock is selected. Stored
Cognee assessments from older research runs remain historical records.

Open `data/stocks/charts/index.html` for the searchable portfolio chart report.
Every supported holding has separate adjusted-close and daily share-volume panels
covering the last two weeks, with source links and dates. Missing volume stays
missing, rather than becoming zero. Refresh charts independently with
`.venv/bin/python portfolio_charts.py`; completed stock monitoring cycles also
refresh them automatically. `STOCK_SWARM_ENABLED=true` enables portfolio monitoring.
Portfolio quantities and source records are private and must remain under `data/`.

## Project presentation

Six slides presenting a unified brain for personal assistants: Muse and Dot, shared Cognee memory, external research agents, and a portfolio demonstration.

- [Editable PowerPoint](docs/presentation/Cognee_Superlinked_6_Slides.pptx)
- [PDF slides](docs/presentation/Cognee_Superlinked_6_Slides.pdf)
- [Slide preview](docs/presentation/preview.png)

The deck includes speaker notes and identifies the pending Dot–Cognee write/retrieval test.
