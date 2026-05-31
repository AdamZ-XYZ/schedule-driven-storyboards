from opc_mcp.server import mcp, session_mgr, opc_client
from opc_client.endpoints import OPCEndpoints
from config.settings import settings


@mcp.tool()
async def init_session(project_id: str | None = None, session_id: str | None = None) -> dict:
    """Start a new editing session and snapshot the project baseline.

    Call this at the start of a conversation. Returns the session_id to pass to all other tools.
    If called with an existing session_id, forces a fresh baseline fetch.
    """
    pid = project_id or settings.opc_project_id
    sid = await session_mgr.init_session(project_id=pid, session_id=session_id)
    snapshot = session_mgr.get_snapshot(sid)
    return {
        "session_id": sid,
        "project_id": pid,
        "snapshot_time": snapshot.snapshot_time.isoformat(),
        "grace_until": snapshot.grace_until.isoformat(),
        "activity_count": len(snapshot.activities),
        "wbs_count": len(snapshot.wbs_nodes),
    }


@mcp.tool()
async def list_activities(
    session_id: str,
    project_id: str | None = None,
    wbs_id: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """List activities for the project. Served from the session baseline cache within the grace period."""
    return await session_mgr.route_read(
        session_id=session_id,
        entity="activities",
        project_id=project_id or settings.opc_project_id,
        filters={"wbsId": wbs_id, "status": status},
    )


@mcp.tool()
async def get_activity(session_id: str, activity_id: str, project_id: str | None = None) -> dict | None:
    """Get a single activity by ID from the session baseline cache."""
    items = await session_mgr.route_read(
        session_id=session_id,
        entity="activities",
        project_id=project_id or settings.opc_project_id,
    )
    return next((a for a in items if a.get("activityId") == activity_id), None)


@mcp.tool()
async def create_activity(session_id: str, activity: dict, project_id: str | None = None) -> dict:
    """Create a new activity in OPC. The session cache is updated after creation."""
    pid = project_id or settings.opc_project_id
    result = await opc_client.post(
        OPCEndpoints.ACTIVITIES.format(project_id=pid),
        body=activity,
    )
    # Add new record to local cache
    snapshot = session_mgr.get_snapshot(session_id)
    if snapshot is not None:
        snapshot.activities.append(result)
    return result


@mcp.tool()
async def update_activity(
    session_id: str,
    activity_id: str,
    updates: dict,
    project_id: str | None = None,
) -> dict:
    """Update fields on an existing activity (e.g. startDate, duration, name)."""
    pid = project_id or settings.opc_project_id
    result = await opc_client.patch(
        OPCEndpoints.ACTIVITY.format(project_id=pid, activity_id=activity_id),
        body=updates,
    )
    await session_mgr.apply_write(session_id, "activities", activity_id, updates, id_field="activityId")
    return result


@mcp.tool()
async def delete_activity(session_id: str, activity_id: str, project_id: str | None = None) -> dict:
    """Delete an activity from OPC and remove it from the session cache."""
    pid = project_id or settings.opc_project_id
    await opc_client.delete(
        OPCEndpoints.ACTIVITY.format(project_id=pid, activity_id=activity_id)
    )
    snapshot = session_mgr.get_snapshot(session_id)
    if snapshot is not None:
        snapshot.activities = [a for a in snapshot.activities if a.get("activityId") != activity_id]
    return {"deleted": activity_id}
