import argparse
import asyncio
import json
import os
import sys

import httpx
from keenable import AsyncKeenable

from news_agent import ROOT, Researcher, load_environment, safe_error


async def doctor():
    result = {}
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        for name, url, headers in [
            ("superlinked", os.environ.get("SIE_BASE_URL", "https://api.superlinked.com") + "/v1/models",
             {"Authorization": "Bearer " + os.environ["SIE_API_KEY"]}),
            ("band", os.environ.get("BAND_REST_URL", "https://app.band.ai") + "/api/v1/agent/chats",
             {"X-API-Key": os.environ["BAND_API_KEY"]}),
        ]:
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                result[name] = {"connected": True, "count": len(data["data"])}
                if name == "superlinked":
                    model = os.environ.get("SIE_MODEL", "zai-org/GLM-5.3-Flash:relay")
                    result[name]["configured_model_available"] = model in {m["id"] for m in data["data"]}
                else:
                    profile = await client.get(
                        os.environ.get("BAND_REST_URL", "https://app.band.ai") + "/api/v1/agent/me",
                        headers=headers,
                    )
                    profile.raise_for_status()
                    identity = profile.json()["data"]
                    result[name]["handle"] = identity["handle"]
                    result[name]["connected"] = identity["id"] == os.environ["BAND_AGENT_ID"]
            except Exception as error:
                result[name] = {"connected": False, "error": safe_error(error)}
    try:
        async with AsyncKeenable(timeout=30, max_retries=0) as client:
            search = await client.search("cryptocurrency news", published_after="2d", max_results=3)
            result["keenable"] = {"connected": True, "count": len(search.results)}
    except Exception as error:
        result["keenable"] = {"connected": False, "error": safe_error(error)}
    print(json.dumps(result, indent=2))
    return 0 if all(v["connected"] and v.get("configured_model_available", True) for v in result.values()) else 1


async def main():
    parser = argparse.ArgumentParser(description="Crypto news research agent")
    parser.add_argument("command", choices=["doctor", "run", "band", "score", "keywords", "stocks"])
    parser.add_argument("--keywords", help="Comma-separated keywords, highest priority first")
    parser.add_argument("--question", default="Summarize the most important crypto news from the last 48 hours.")
    args = parser.parse_args()
    load_environment()
    if args.command == "stocks":
        from stock_swarm import saved_stocks
        print(saved_stocks(ROOT))
        return 0
    if args.command in {"score", "keywords"}:
        from news_scoring import configure, latest_ranking
        if args.command == "keywords":
            if args.keywords is None:
                parser.error("keywords requires --keywords")
            terms = configure(ROOT, args.keywords)
            print("Priority order: " + ", ".join(terms))
        print(latest_ranking(ROOT))
        return 0
    required = ["SIE_API_KEY", "KEENABLE_API_KEY"]
    if args.command in {"doctor", "band"}:
        required += ["BAND_API_KEY", "BAND_AGENT_ID"]
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        print("Missing configuration: " + ", ".join(missing), file=sys.stderr)
        return 1
    if args.command == "doctor":
        return await doctor()
    if args.command == "band":
        from band_bot import serve
        await serve()
        return 0
    researcher = Researcher()
    try:
        run = await researcher.run(args.question)
        print("Report: " + str(run / "report.md"))
    finally:
        await researcher.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        pass
    except Exception as error:
        print("Failed: " + safe_error(error), file=sys.stderr)
        sys.exit(1)
