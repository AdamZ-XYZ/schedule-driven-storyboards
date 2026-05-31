import logging
import sys
from pathlib import Path

# Allow imports from src/ without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server.fastmcp import FastMCP

from opc_client.auth import OPCTokenManager
from opc_client.client import OPCClient
from session.manager import SessionManager

# Load settings lazily so the server can start without a .env for local dev
from config.settings import settings  # noqa: E402

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

# ── Shared singletons ────────────────────────────────────────────────────────

token_manager = OPCTokenManager(
    token_url=settings.opc_token_url,
    client_id=settings.opc_client_id,
    client_secret=settings.opc_client_secret,
)

opc_client = OPCClient(
    base_url=settings.opc_base_url,
    token_manager=token_manager,
)

session_mgr = SessionManager(
    opc_client=opc_client,
    grace_minutes=settings.session_grace_minutes,
    cache_backend=settings.cache_backend,
)

# ── MCP app ──────────────────────────────────────────────────────────────────

mcp = FastMCP("OPC-AI-Skills")

# Register tool/resource/prompt modules (side-effect: decorators register on `mcp`)
from opc_mcp.tools import activities, wbs, relationships, calendars  # noqa: E402, F401
from opc_mcp.resources import baseline  # noqa: E402, F401
from opc_mcp.prompts import templates  # noqa: E402, F401


def main() -> None:
    transport = settings.transport
    if transport == "sse":
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
