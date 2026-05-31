from opc_mcp.server import mcp, session_mgr, opc_client
from opc_client.endpoints import OPCEndpoints
from config.settings import settings


@mcp.tool()
async def list_wbs_nodes(
    session_id: str,
    parent_wbs_id: str | None = None,
    project_id: str | None = None,
) -> list[dict]:
    """List WBS nodes, optionally filtered by parent. Served from session baseline cache."""
    return await session_mgr.route_read(
        session_id=session_id,
        entity="wbs_nodes",
        project_id=project_id or settings.opc_project_id,
        filters={"parentWbsId": parent_wbs_id},
    )


@mcp.tool()
async def get_wbs_node(session_id: str, wbs_id: str, project_id: str | None = None) -> dict | None:
    """Get a single WBS node by ID from the session baseline cache."""
    items = await session_mgr.route_read(
        session_id=session_id,
        entity="wbs_nodes",
        project_id=project_id or settings.opc_project_id,
    )
    return next((w for w in items if w.get("wbsId") == wbs_id), None)


@mcp.tool()
async def create_wbs_node(session_id: str, wbs_node: dict, project_id: str | None = None) -> dict:
    """Create a new WBS node in OPC."""
    pid = project_id or settings.opc_project_id
    result = await opc_client.post(
        OPCEndpoints.WBS.format(project_id=pid),
        body=wbs_node,
    )
    snapshot = session_mgr.get_snapshot(session_id)
    if snapshot is not None:
        snapshot.wbs_nodes.append(result)
    return result


@mcp.tool()
async def update_wbs_node(
    session_id: str,
    wbs_id: str,
    updates: dict,
    project_id: str | None = None,
) -> dict:
    """Update an existing WBS node."""
    pid = project_id or settings.opc_project_id
    result = await opc_client.patch(
        OPCEndpoints.WBS_NODE.format(project_id=pid, wbs_id=wbs_id),
        body=updates,
    )
    await session_mgr.apply_write(session_id, "wbs_nodes", wbs_id, updates, id_field="wbsId")
    return result
