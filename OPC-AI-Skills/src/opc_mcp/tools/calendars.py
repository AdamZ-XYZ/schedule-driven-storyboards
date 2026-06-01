from pydantic import ValidationError as PydanticValidationError

from opc_mcp.errors import ValidationError
from opc_mcp.middleware import safe_tool
from opc_mcp.schemas import CalendarUpdate
from opc_mcp.server import mcp, opc_client, session_mgr
from opc_client.endpoints import OPCEndpoints


@mcp.tool()
@safe_tool
async def list_calendars(session_id: str) -> list[dict]:
    """List all calendars for the project. Served from session baseline cache."""
    return await session_mgr.route_read(session_id=session_id, entity="calendars")


@mcp.tool()
@safe_tool
async def update_calendar(
    session_id: str,
    calendar_id: str,
    updates: dict,
    dry_run: bool = False,
) -> dict:
    """Update a calendar. Allowed fields: name.

    IMPORTANT: Only use calendar IDs returned by list_calendars.
    Set dry_run=True to preview without touching OPC.
    """
    try:
        validated = CalendarUpdate.model_validate(updates)
    except PydanticValidationError as e:
        raise ValidationError(str(e)) from e

    before = session_mgr.assert_entity_exists(session_id, "calendars", calendar_id, "calendarId")
    pid = session_mgr.get_project(session_id)
    payload = validated.model_dump(exclude_none=True, mode="json")

    if dry_run:
        return {"dry_run": True, "calendar_id": calendar_id, "before": before, "would_apply": payload}

    op = session_mgr.record_write(session_id, "update_calendar", "calendars", calendar_id, dict(before), payload)
    result = await opc_client.patch(OPCEndpoints.CALENDAR.format(project_id=pid, calendar_id=calendar_id), body=payload)
    session_mgr.confirm_write(op.op_id)
    await session_mgr.apply_write(session_id, "calendars", calendar_id, payload, id_field="calendarId")
    return result


@mcp.tool()
@safe_tool
async def schedule_run(session_id: str, dry_run: bool = False) -> dict:
    """Trigger OPC schedule calculation.

    WARNING: This cannot be undone. CONFIRM with the user before calling without dry_run=True.
    After a schedule run, dates will change and the session baseline will be invalidated.
    """
    pid = session_mgr.get_project(session_id)

    if dry_run:
        return {"dry_run": True, "would_trigger": "schedule_calculation", "project_id": pid}

    result = await opc_client.post(OPCEndpoints.SCHEDULE.format(project_id=pid), body={})
    # Invalidate cache — dates will have changed
    await session_mgr.invalidate(session_id)
    return result or {"status": "schedule_run_triggered", "project_id": pid, "note": "Baseline invalidated. Call init_session to reload."}
