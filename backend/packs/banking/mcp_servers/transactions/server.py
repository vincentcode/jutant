"""The banking transactions MCP server process.

Run: python -m packs.banking.mcp_servers.transactions.server

Needs JUTANT_CALLER_SECRET and JUTANT_MCP_TRANSACTIONS_URL; JUTANT_BANKING_ADAPTERS picks the fake
or real bank systems.
"""

import os

from mcp_servers.common.server import serve
from packs.banking.mcp_servers import build_from_environment

if __name__ == "__main__":
    serve(build_from_environment("transactions"), os.environ["JUTANT_MCP_TRANSACTIONS_URL"])
