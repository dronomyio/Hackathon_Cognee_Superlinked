"""Five-minute discovery with a durable ledger of news queued for cloud memory."""
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta

from news_agent import UTC, safe_error
from news_scoring import save_ranking

LOG = logging.getLogger("crypto.schedule")


class NewsSchedule:
    def __init__(self, root, researcher, memory, lock, decisions=None):
        self.decisions = decisions
        self.researcher, self.memory, self.lock = researcher, memory, lock
        self.root = root
        self.interval = max(30, int(os.environ.get("NEWS_CHECK_INTERVAL_SECONDS", "300")))
        self.path = root / "data" / "service" / "schedule.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {}
        if self.state.get("destination") != memory.destination:
            self.state = {"destination": memory.destination, "known_urls": []}

    def save(self):
        self.memory._save(self.path, self.state)

    def known_urls(self):
        known = set(self.state.get("known_urls", []))
        # Recover committed memory records even if the process stopped before saving its ledger.
        for path in (self.memory.root / "outbox").glob("*.json"):
            record = json.loads(path.read_text())
            if record.get("destination") == self.memory.destination:
                known.update(record.get("source_urls", []))
        return known

    async def check(self):
        async with self.lock:
            end = datetime.now(UTC)
            self.state.update(status="checking", last_check=end.isoformat(), interval_seconds=self.interval)
            self.save()
            articles, coverage = await self.researcher.discover(end)
            save_ranking(self.root, articles)
            if self.decisions:
                try:
                    await self.decisions.check(articles)
                except Exception as error:
                    LOG.warning("Decision stage failed: %s", safe_error(error))
            errors = {name: item["search_errors"] for name, item in coverage.items() if item.get("search_errors")}
            known = self.known_urls()
            fresh = [a for a in articles if a.url not in known]
            self.state.update(source_count=len(articles), new_articles=len(fresh), coverage_errors=errors)
            if not fresh:
                self.state["status"] = "check_incomplete" if errors else "no_update"
                LOG.info("%s (%d sources checked)", "News check incomplete: source errors" if errors else "No new crypto news compared with recorded memory", len(articles))
                self.save()
                return
            if not self.memory.enabled:
                raise RuntimeError("Cognee memory is not configured")
            context = await self.memory.recall("scheduled", "Recent crypto news briefings and source URLs")
            run = await self.researcher.run(memory_context=context, discovered=(articles, coverage), checked_at=end)
            record_id = self.memory.enqueue("scheduled", (run / "report.md").read_text())
            record_path = self.memory.root / "outbox" / (record_id + ".json")
            record = json.loads(record_path.read_text())
            record["source_urls"] = [a.url for a in articles]
            self.memory._save(record_path, record)
            known.update(record["source_urls"])
            self.state.update(status="memory_queued", known_urls=sorted(known), report=str(run / "report.md"), memory_record=record_id)
            self.save()
            LOG.info("New crypto news: %d articles; briefing queued for %s", len(fresh), self.memory.dataset("scheduled"))
            await self.memory.flush_once(record_id)
            record = json.loads(record_path.read_text())
            self.state.update(status="updated" if record["status"] == "stored" else "memory_pending", memory_status=record["status"])
            self.save()
            LOG.info("Scheduled briefing memory status: %s", record["status"])

    async def run(self):
        LOG.info("Automatic crypto news checks enabled: every %d seconds", self.interval)
        while True:
            started = asyncio.get_running_loop().time()
            try:
                await self.check()
            except Exception as error:
                self.state.update(status="failed", error=safe_error(error))
                self.save()
                LOG.warning("News check failed: %s", safe_error(error))
            # Skip elapsed ticks; never overlap or burst to catch up after a slow check.
            elapsed = asyncio.get_running_loop().time() - started
            delay = self.interval - (elapsed % self.interval)
            self.state["next_check"] = (datetime.now(UTC) + timedelta(seconds=delay)).isoformat()
            self.save()
            await asyncio.sleep(delay)
