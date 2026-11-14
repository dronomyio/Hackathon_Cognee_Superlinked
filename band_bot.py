"""Band owns delivery/reconnects; this adapter owns only crypto research."""
import asyncio
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from band import Agent
from band.core import HistoryConverter, SimpleAdapter
from band.core.delivery import relay_reply

from news_agent import ROOT, UTC, Article, Researcher, render_report, safe_error, timestamp
from cognee_memory import CogneeMemory
from news_schedule import NewsSchedule
from news_scoring import latest_ranking
from news_decisions import NewsDecisions, saved_decisions
from stock_swarm import StockSwarm, saved_stocks


def is_briefing_request(content):
    # Match retrieval requests narrowly; specific analysis still uses inference.
    text = re.sub(r"@\[\[[^\]]+\]\]|@[\w/-]+", "", content).strip().lower()
    return bool(re.fullmatch(
        r"(?:please\s+)?(?:(?:show|give|send)(?:\s+me)?\s+)?(?:the\s+)?"
        r"(?:latest|current|last|saved)\s+(?:crypto\s+)?(?:news|briefing|report|summary)"
        r"(?:\s+with\s+(?:sources|citations|links))?(?:\s+please)?[.!?]*", text))


def saved_briefing():
    try:
        run = Path((ROOT / "data" / "latest.txt").read_text().strip())
        state = json.loads((run / "status.json").read_text())
        if state.get("status") != "complete" or not timestamp(state.get("window_end")):
            raise ValueError("No completed briefing")
        report = (run / "report.md").read_text()
        if not report.strip():
            raise ValueError("Empty briefing")
        return "Latest completed briefing (saved report; collection time shown below).\n\n" + report
    except (OSError, ValueError, TypeError):
        return "No completed saved briefing is available yet. Automatic news checks are running; please try again shortly."


class NoHistory(HistoryConverter[list]):
    def set_agent_name(self, name):
        pass

    def convert(self, raw):
        return []


class CryptoAdapter(SimpleAdapter[list]):
    def __init__(self, researcher, memory=None):
        super().__init__(history_converter=NoHistory(), emit=(), capabilities=())
        self.researcher = researcher
        self.memory = memory
        self.lock = asyncio.Lock()

    async def on_message(self, msg, tools, history, participants_msg, contacts_msg,
                         *, is_session_bootstrap, room_id):
        content = getattr(msg, "content", "")
        command = re.sub(r"@\[\[[^\]]+\]\]|@[\w/-]+", "", content).strip().lower().rstrip('.!?')
        if command in {"show stocks", "stock scores", "show stock scores", "show stock impact", "stock impact"}:
            await relay_reply(tools, saved_stocks(ROOT), mentions=[msg.sender_id])
            return
        if command in {"show decisions", "news decisions", "show news decisions", "show alerts"}:
            await relay_reply(tools, saved_decisions(ROOT), mentions=[msg.sender_id])
            return
        if command in {"score news", "rank news", "show news scores", "show ranked news"}:
            await relay_reply(tools, latest_ranking(ROOT), mentions=[msg.sender_id])
            return
        # Read-only requests bypass the shared inference/indexing lock entirely.
        if is_briefing_request(content):
            await relay_reply(tools, saved_briefing(), mentions=[msg.sender_id])
            return
        if content.strip().lower() == "ping":
            await relay_reply(tools, "Online: Keenable research → Superlinked summaries. Ask for a 48-hour crypto briefing.", mentions=[msg.sender_id])
            return
        # A single run at a time across rooms, avoiding a burst of paid research calls.
        async with self.lock:
            question = msg.format_for_llm()
            try:
                memory_context = ""
                memory_notice = ""
                if self.memory and self.memory.enabled:
                    try:
                        memory_context = await self.memory.recall(room_id, question)
                    except Exception:
                        memory_notice = "\n\nCognee retrieval unavailable; this answer uses fresh news evidence only."
                cached = None
                pointer = ROOT / "data" / "latest.txt"
                if pointer.exists():
                    cached = json.loads((Path(pointer.read_text().strip()) / "status.json").read_text())
                end = timestamp(cached.get("window_end")) if cached else None
                if cached and cached.get("status") == "complete" and end and datetime.now(UTC) - end < timedelta(minutes=15):
                    articles = [Article(**a) for a in cached["articles"]]
                    brief = await self.researcher.summarize(articles, end, question, memory_context)
                    reply = render_report(brief, articles, cached["coverage"], end)
                else:
                    run = await self.researcher.run(question, memory_context)
                    reply = (run / "report.md").read_text()
                if self.memory and self.memory.enabled:
                    try:
                        self.memory.enqueue(room_id, reply)
                        memory_notice += "\n\nBriefing queued for the configured Cognee memory dataset."
                    except Exception:
                        memory_notice += "\n\nMemory queue unavailable; this briefing was not saved to Cognee."
                reply += memory_notice
                # Keep a single atomic reply: no partly sent multi-message briefing.
                if len(reply) > 14000:
                    reply = reply[:13500].rsplit("\n", 1)[0] + "\n\nBriefing truncated for chat; full report saved by the worker."
            except Exception as error:
                reply = "Research could not finish: " + safe_error(error) + ". No fresh briefing is being claimed."
            await relay_reply(tools, reply, mentions=[msg.sender_id])

    async def on_cleanup(self, room_id):
        pass


async def serve():
    import os
    import logging
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logging.getLogger("band").setLevel(logging.INFO)
    logging.getLogger("crypto.schedule").setLevel(logging.INFO)
    researcher = Researcher()
    memory = CogneeMemory(ROOT)
    adapter = CryptoAdapter(researcher, memory)
    agent = Agent.create(adapter=adapter,
                         agent_id=os.environ["BAND_AGENT_ID"], api_key=os.environ["BAND_API_KEY"])
    drain = asyncio.create_task(memory.drain(adapter.lock))
    decisions = NewsDecisions(ROOT, researcher.http, researcher.base)
    schedule = asyncio.create_task(NewsSchedule(ROOT, researcher, memory, adapter.lock, decisions).run())
    stocks = asyncio.create_task(StockSwarm(ROOT, researcher, adapter.lock, memory).run())
    try:
        await agent.run()
    finally:
        drain.cancel()
        schedule.cancel()
        stocks.cancel()
        await asyncio.gather(drain, schedule, stocks, return_exceptions=True)
        await memory.close()
        await researcher.close()
