"""The HR MCP server process.

Run: python -m packs.hr.mcp_servers.hr.server

Needs JUTANT_CALLER_SECRET and JUTANT_MCP_HR_URL; JUTANT_HR_ADAPTERS picks the dummy or real HR
systems.
"""

import os

from mcp_servers.common.server import serve
from packs.hr.mcp_servers import build_from_environment

if __name__ == "__main__":
    serve(build_from_environment("hr"), os.environ["JUTANT_MCP_HR_URL"])
