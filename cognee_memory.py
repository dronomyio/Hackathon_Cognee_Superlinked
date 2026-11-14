"""Cognee Cloud/local memory with explicit dataset routing and a durable outbox."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx


class CogneeMemory:
    def __init__(self, root: Path, client=None):
        self.root = root / "data" / "memory"
        self.base = os.environ.get("COGNEE_URL", "").rstrip("/")
        self.tenant = os.environ.get("COGNEE_TENANT_ID", "")
        self.cloud = bool(self.tenant)
        self.dataset_name = os.environ.get("COGNEE_DATASET", "")
        api_key = os.environ.get("COGNEE_API_KEY", "")
        self.enabled = bool(self.base) and (not self.cloud or bool(api_key))
        self.destination = hashlib.sha256((self.base + ":" + self.tenant).encode()).hexdigest()
        self.agent = os.environ.get("BAND_AGENT_ID", "superlinked-bot")
        token = os.environ.get("COGNEE_API_TOKEN", "")
        self.headers = ({"X-Api-Key": api_key, "X-Tenant-Id": self.tenant} if self.cloud
                        else {"Authorization": "Bearer " + token} if token else {})
        self.http = client or httpx.AsyncClient(
            timeout=httpx.Timeout(300, connect=5), follow_redirects=False,
            headers=self.headers,
        )

    async def _request(self, method: str, path: str, **kwargs):
        """Replay 307/308 only within this origin; never forward credentials elsewhere."""
        url = httpx.URL(self.base + path)
        origin = (url.scheme, url.host, url.port)
        for _ in range(3):
            response = await self.http.request(method, url, headers=self.headers, follow_redirects=False, **kwargs)
            if response.status_code not in {307, 308}:
                return response
            location = response.headers.get("location")
            if not location:
                response.raise_for_status()
            target = url.join(location)
            if (target.scheme, target.host, target.port) != origin:
                raise RuntimeError("Refusing cross-origin Cognee credential redirect")
            url = target
        raise RuntimeError("Too many Cognee redirects")

    def dataset(self, room_id: str) -> str:
        if self.dataset_name:
            return self.dataset_name
        identity = hashlib.sha256((self.agent + ":" + room_id).encode()).hexdigest()[:24]
        return "crypto_news_" + identity

    async def recall(self, room_id: str, question: str) -> str:
        if not self.enabled:
            return ""
        dataset = self.dataset(room_id)
        response = await self._request("GET", "/api/v1/datasets/", timeout=15)
        response.raise_for_status()
        records = response.json()
        if isinstance(records, dict):
            records = records.get("data", records.get("datasets", []))
        if not any(r.get("name") == dataset for r in records):
            return ""
        payload = {"query": question[:2000], "datasets": [dataset]}
        payload.update({"searchType": "CHUNKS", "topK": 3, "onlyContext": True} if self.cloud
                       else {"search_type": "CHUNKS", "top_k": 3})
        response = await self._request("POST", "/api/v1/search", timeout=30, json=payload)
        response.raise_for_status()
        return json.dumps(response.json(), ensure_ascii=False)[:6000]

    def enqueue(self, room_id: str, report: str) -> str:
        dataset = self.dataset(room_id)
        digest = hashlib.sha256((self.destination + "\n" + dataset + "\n" + report).encode()).hexdigest()
        folder = self.root / "outbox"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (digest + ".json")
        if not path.exists():
            payload = {"id": digest, "dataset": dataset, "report": report, "destination": self.destination,
                       "created_at": datetime.now(timezone.utc).isoformat(), "status": "pending", "attempts": 0}
            self._save(path, payload)
        return digest

    @staticmethod
    def _save(path, payload):
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        temporary.chmod(0o600)
        temporary.replace(path)

    async def flush_once(self, record_id=None):
        if not self.enabled:
            return
        def queue_order(path):
            entry = json.loads(path.read_text())
            # Serve the newest complete portfolio table before lengthy graph dossiers.
            table = entry.get('report', '').startswith('# Complete score table:')
            created = datetime.fromisoformat(entry['created_at']).timestamp() if entry.get('created_at') else 0
            return (0 if table else 1, -created if table else created)
        for path in sorted((self.root / "outbox").glob("*.json"), key=queue_order):
            payload = json.loads(path.read_text())
            if record_id and payload["id"] != record_id:
                continue
            if payload.get("destination") != self.destination:
                continue  # Never migrate old local test data into a cloud tenant.
            if self.dataset_name and payload["dataset"] != self.dataset_name:
                continue
            if payload["status"] in {"stored", "cancelled"}:
                continue
            try:
                report = "Historical news memory; not fresh evidence.\n" + payload["report"]
                response = await self._request("POST", "/api/v1/add", timeout=30,
                    files={"data": (payload["id"] + ".txt", report.encode(), "text/plain")},
                    data={"datasetName": payload["dataset"]})
                response.raise_for_status()
                process = {"datasets": [payload["dataset"]]}
                process.update({"runInBackground": False, "chunksPerBatch": 1, "dataPerBatch": 1} if self.cloud
                               else {"run_in_background": False, "chunks_per_batch": 1})
                response = await self._request("POST", "/api/v1/cognify", json=process)
                response.raise_for_status()
                result = response.json()
                # A provider can report a pipeline failure in an HTTP-200 envelope.
                def states(value):
                    if isinstance(value, dict):
                        for key, item in value.items():
                            if key.lower() in {"status", "error", "errors"} and item:
                                yield str(item).lower()
                            yield from states(item)
                    elif isinstance(value, list):
                        for item in value:
                            yield from states(item)
                if any(any(word in state for word in ("fail", "error", "pending", "started", "running"))
                       for state in states(result)):
                    raise RuntimeError("Cognee pipeline not complete")
                payload.update(status="stored", stored_at=datetime.now(timezone.utc).isoformat())
                payload.pop("last_error", None)
            except Exception as error:
                # Do not persist provider messages, headers, or credentials.
                payload.update(status="pending", last_error=type(error).__name__)
                payload["attempts"] += 1
                self._save(path, payload)
                return  # Back off rather than hammer a missing server or exhausted account.
            self._save(path, payload)
            return  # One item per pass so a backlog does not starve Band mentions.

    async def drain(self, lock: asyncio.Lock):
        while True:
            # Memory graph construction and news generation share one inference key.
            async with lock:
                await self.flush_once()
            await asyncio.sleep(60)

    async def close(self):
        await self.http.aclose()
