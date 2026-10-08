"""Offline Playwright bridge to the real in-process MCP client, not service calls."""

import asyncio
import json
import os
import sys

from fastmcp import Client

from ledgerlight.mcp_server import CHART_URI, create_server


async def main():
    root = os.environ.get("LEDGERLIGHT_E2E_STORAGE")
    if not root:
        raise RuntimeError("Isolated test storage is required")
    os.environ["LEDGERLIGHT_DATA_DIR"] = root + "/data"
    os.environ["LEDGERLIGHT_CONFIG_DIR"] = root + "/config"
    os.environ["LEDGERLIGHT_TODAY"] = "2026-03-15"
    async with Client(create_server()) as client:
        if sys.argv[1] == "resource":
            content = await client.read_resource(CHART_URI)
            print(json.dumps({"html": content[0].text}))
        else:
            result = await client.call_tool(sys.argv[1], json.loads(sys.argv[2]))
            print(result.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())
