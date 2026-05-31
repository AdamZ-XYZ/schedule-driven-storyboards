from opc_mcp.server import mcp, session_mgr, opc_client
from opc_client.endpoints import OPCEndpoints
from config.settings import settings


@mcp.tool()
async def list_relationships(
    session_id: str,
    predecessor_id: str | None = None,
    successor_id: str | None = None,
    project_id: str | None = None,
) -> list[dict]:
    """List activity relationships (logic ties). Served from session baseline cache."""
    items = await session_mgr.route_read(
        session_id=session_id,
        entity="relationships",
        project_id=project_id or settings.opc_project_id,
    )
    if predecessor_id:
        items = [r for r in items if r.get("predecessorActivityId") == predecessor_id]
    if successor_id:
        items = [r for r in items if r.get("successorActivityId") == successor_id]
    return items


@mcp.tool()
async def create_relationship(
    session_id: str,
    predecessor_activity_id: str,
    successor_activity_id: str,
    relationship_type: str = "FS",
    lag: int = 0,
    project_id: str | None = None,
) -> dict:
    """Create a new logic tie between two activities.

    relationship_type: FS (finish-to-start), SS, FF, SF
    lag: lag in days (positive) or lead (negative)
    """
    pid = project_id or settings.opc_project_id
    body = {
        "predecessorActivityId": predecessor_activity_id,
        "successorActivityId": successor_activity_id,
        "type": relationship_type,
        "lag": lag,
    }
    result = await opc_client.post(
        OPCEndpoints.RELS.format(project_id=pid),
        body=body,
    )
    snapshot = session_mgr.get_snapshot(session_id)
    if snapshot is not None:
        snapshot.relationships.append(result)
    return result


@mcp.tool()
async def update_relationship(
    session_id: str,
    relationship_id: str,
    updates: dict,
    project_id: str | None = None,
) -> dict:
    """Update an existing relationship (e.g. change type or lag)."""
    pid = project_id or settings.opc_project_id
    result = await opc_client.patch(
        OPCEndpoints.REL.format(project_id=pid, rel_id=relationship_id),
        body=updates,
    )
    await session_mgr.apply_write(session_id, "relationships", relationship_id, updates, id_field="relationshipId")
    return result


@mcp.tool()
async def delete_relationship(
    session_id: str,
    relationship_id: str,
    project_id: str | None = None,
) -> dict:
    """Delete a logic tie between two activities."""
    pid = project_id or settings.opc_project_id
    await opc_client.delete(
        OPCEndpoints.REL.format(project_id=pid, rel_id=relationship_id)
    )
    snapshot = session_mgr.get_snapshot(session_id)
    if snapshot is not None:
        snapshot.relationships = [
            r for r in snapshot.relationships if r.get("relationshipId") != relationship_id
        ]
    return {"deleted": relationship_id}
