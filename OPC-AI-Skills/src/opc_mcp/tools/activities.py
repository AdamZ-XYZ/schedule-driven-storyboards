from pydantic import ValidationError as PydanticValidationError

from opc_mcp.errors import ValidationError
from opc_mcp.middleware import safe_tool
from opc_mcp.schemas import ActivityCreate, ActivityUpdate
from opc_mcp.server import mcp, opc_client, session_mgr
from opc_client.endpoints import OPCEndpoints


@mcp.tool()
@safe_tool
async def init_session(project_id: str | None = None, session_id: str | None = None) -> dict:
    """Start a new editing session and snapshot the project baseline.

    ALWAYS call this first. Returns the session_id required by all other tools.
    Calling with an existing session_id forces a fresh baseline fetch.
    """
    from config.settings import settings
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
@safe_tool
async def list_activities(
    session_id: str,
    wbs_id: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """List activities for the project. Served from the session baseline cache within the grace period."""
    return await session_mgr.route_read(
        session_id=session_id,
        entity="activities",
        filters={"wbsId": wbs_id, "status": status},
    )


@mcp.tool()
@safe_tool
async def get_activity(session_id: str, activity_id: str) -> dict:
    """Get a single activity by ID from the session baseline cache."""
    return session_mgr.assert_entity_exists(session_id, "activities", activity_id, "activityId")


@mcp.tool()
@safe_tool
async def create_activity(session_id: str, activity: dict, dry_run: bool = False) -> dict:
    """Create a new activity.

    Set dry_run=True first to preview what will be created without touching OPC.
    Required fields: name, wbsId. Optional: startDate, finishDate, duration, status, calendarId.
    """
    try:
        validated = ActivityCreate.model_validate(activity)
    except PydanticValidationError as e:
        raise ValidationError(str(e)) from e

    pid = session_mgr.get_project(session_id)
    payload = validated.model_dump(exclude_none=True, mode="json")

    if dry_run:
        return {"dry_run": True, "would_create": payload, "project_id": pid}

    op = session_mgr.record_write(session_id, "create_activity", "activities", "new", {}, payload)
    result = await opc_client.post(OPCEndpoints.ACTIVITIES.format(project_id=pid), body=payload)
    session_mgr.confirm_write(op.op_id)

    snapshot = session_mgr.get_snapshot(session_id)
    if snapshot is not None:
        snapshot.activities.append(result)
    return result


@mcp.tool()
@safe_tool
async def update_activity(
    session_id: str,
    activity_id: str,
    updates: dict,
    dry_run: bool = False,
) -> dict:
    """Update fields on an activity (e.g. startDate, duration, name, status).

    IMPORTANT: Only use activity IDs returned by list_activities or get_activity.
    Set dry_run=True first to preview the change without touching OPC.
    Allowed fields: name, startDate, finishDate, duration, status, calendarId, wbsId.
    """
    try:
        validated = ActivityUpdate.model_validate(updates)
    except PydanticValidationError as e:
        raise ValidationError(str(e)) from e

    before = session_mgr.assert_entity_exists(session_id, "activities", activity_id, "activityId")
    pid = session_mgr.get_project(session_id)
    payload = validated.model_dump(exclude_none=True, mode="json")

    if dry_run:
        return {"dry_run": True, "activity_id": activity_id, "before": before, "would_apply": payload}

    op = session_mgr.record_write(session_id, "update_activity", "activities", activity_id, dict(before), payload)
    result = await opc_client.patch(
        OPCEndpoints.ACTIVITY.format(project_id=pid, activity_id=activity_id),
        body=payload,
    )
    session_mgr.confirm_write(op.op_id)
    await session_mgr.apply_write(session_id, "activities", activity_id, payload, id_field="activityId")
    return result


@mcp.tool()
@safe_tool
async def delete_activity(session_id: str, activity_id: str, dry_run: bool = False) -> dict:
    """Delete an activity. This is irreversible via undo_last only if the activity data is preserved.

    CONFIRM with the user before calling without dry_run=True.
    IMPORTANT: Only use activity IDs returned by list_activities or get_activity.
    """
    before = session_mgr.assert_entity_exists(session_id, "activities", activity_id, "activityId")
    pid = session_mgr.get_project(session_id)

    if dry_run:
        return {"dry_run": True, "would_delete": before}

    op = session_mgr.record_write(session_id, "delete_activity", "activities", activity_id, dict(before), {})
    await opc_client.delete(OPCEndpoints.ACTIVITY.format(project_id=pid, activity_id=activity_id))
    session_mgr.confirm_write(op.op_id)

    snapshot = session_mgr.get_snapshot(session_id)
    if snapshot is not None:
        snapshot.activities = [a for a in snapshot.activities if a.get("activityId") != activity_id]
    return {"deleted": activity_id, "op_id": op.op_id}
