"""Cloud connection check; local deployments also run an isolated write test."""
import asyncio
import json
import sys

from cognee_memory import CogneeMemory
from news_agent import ROOT, load_environment, safe_error


async def main():
    load_environment()
    memory = CogneeMemory(ROOT)
    try:
        if not memory.enabled:
            print("Set COGNEE_API_KEY in .env." if memory.cloud else "Set COGNEE_URL first.")
            return 1
        if memory.cloud:
            print("Checking Cognee Cloud authentication and configured dataset (read-only).", flush=True)
            response = await memory._request("GET", "/api/v1/datasets/", timeout=30)
            response.raise_for_status()
            records = response.json()
            if isinstance(records, dict):
                records = records.get("data", records.get("datasets", []))
            if not any(r.get("name") == memory.dataset_name for r in records):
                print("Configured dataset is not accessible:", memory.dataset_name)
                return 1
            await memory.recall("__connection_check__", "cryptocurrency news and source provenance")
            print("Cloud authentication, dataset access and recall passed:", memory.dataset_name)
            print("No documents were added or changed by this check.")
            return 0
        print("Checking Cognee ingestion, indexing and recall; inference may take several minutes.", flush=True)
        marker = "crypto_memory_connection_check_v1"
        key = memory.enqueue("__connection_check__", marker + ": The news bot preserves source links and publication dates.")
        await memory.flush_once(record_id=key)
        receipt = json.loads((memory.root / "outbox" / (key + ".json")).read_text())
        if receipt["status"] != "stored":
            print("Cognee indexing failed; retained in outbox:", receipt.get("last_error", "pending"))
            return 1
        result = await memory.recall("__connection_check__", marker)
        if marker not in result:
            print("Cognee accepted indexing, but the test memory was not retrieved.")
            return 1
        print("Cognee write → index → recall passed.")
        return 0
    finally:
        await memory.close()


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as error:
        print("Cognee check failed:", safe_error(error))
        sys.exit(1)
