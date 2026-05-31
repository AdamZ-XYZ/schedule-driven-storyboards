from opc_mcp.server import mcp, session_mgr, opc_client
from opc_client.endpoints import OPCEndpoints
from config.settings import settings


@mcp.tool()
async def list_calendars(session_id: str, project_id: str | None = None) -> list[dict]:
    """List all calendars for the project. Served from session baseline cache."""
    return await session_mgr.route_read(
        session_id=session_id,
        entity="calendars",
        project_id=project_id or settings.opc_project_id,
    )


@mcp.tool()
async def update_calendar(
    session_id: str,
    calendar_id: str,
    updates: dict,
    project_id: str | None = None,
) -> dict:
    """Update a calendar (e.g. working hours, exceptions)."""
    pid = project_id or settings.opc_project_id
    result = await opc_client.patch(
        OPCEndpoints.CALENDAR.format(project_id=pid, calendar_id=calendar_id),
        body=updates,
    )
    await session_mgr.apply_write(session_id, "calendars", calendar_id, updates, id_field="calendarId")
    return result


@mcp.tool()
async def schedule_run(session_id: str, project_id: str | None = None) -> dict:
    """Trigger OPC schedule calculation for the project."""
    pid = project_id or settings.opc_project_id
    result = await opc_client.post(
        OPCEndpoints.SCHEDULE.format(project_id=pid),
        body={},
    )
    # After a schedule run the dates may change, so invalidate the cache
    await session_mgr.invalidate(session_id)
    return result or {"status": "schedule_run_triggered", "project_id": pid}
