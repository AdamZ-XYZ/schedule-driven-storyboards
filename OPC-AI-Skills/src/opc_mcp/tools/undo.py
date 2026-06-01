from opc_mcp.errors import UndoNotPossible
from opc_mcp.middleware import safe_tool
from opc_mcp.server import mcp, opc_client, session_mgr
from opc_client.endpoints import OPCEndpoints

_IRREVERSIBLE = {"create_relationship", "schedule_run"}


@mcp.tool()
@safe_tool
async def list_operations(session_id: str) -> list[dict]:
    """Show all write operations made in this session, in order. Use op_id to undo a specific one."""
    ops = session_mgr.get_write_log().get_all(session_id)
    return [
        {
            "op_id": op.op_id,
            "timestamp": op.timestamp.isoformat(),
            "tool": op.tool,
            "entity_type": op.entity_type,
            "entity_id": op.entity_id,
            "opc_confirmed": op.opc_confirmed,
            "reversible": op.tool not in _IRREVERSIBLE,
        }
        for op in ops
    ]


@mcp.tool()
@safe_tool
async def undo_last(session_id: str) -> dict:
    """Reverse the most recent write operation in this session.

    Not all operations are reversible (e.g. schedule_run).
    The before state is restored by PATCHing or re-creating the entity.
    """
    op = session_mgr.get_write_log().get_last(session_id)
    if op is None:
        return {"status": "nothing_to_undo"}
    return await _reverse_operation(session_id, op.op_id)


@mcp.tool()
@safe_tool
async def undo_operation(session_id: str, op_id: str) -> dict:
    """Reverse a specific write operation by op_id (from list_operations).

    Undoing an older operation may leave the schedule in an inconsistent state
    if later operations depended on it. Prefer undo_last for sequential reversal.
    """
    return await _reverse_operation(session_id, op_id)


@mcp.tool()
@safe_tool
async def undo_all(session_id: str) -> dict:
    """Reverse all write operations in this session in reverse order.

    Irreversible operations (schedule_run) are skipped with a warning.
    """
    log = session_mgr.get_write_log()
    ops = list(reversed(log.get_all(session_id)))
    results = []
    for op in ops:
        result = await _reverse_operation(session_id, op.op_id, raise_on_irreversible=False)
        results.append(result)
    return {"undone": len([r for r in results if r.get("status") == "undone"]), "details": results}


# ── Internal ──────────────────────────────────────────────────────────────────

async def _reverse_operation(session_id: str, op_id: str, raise_on_irreversible: bool = True) -> dict:
    log = session_mgr.get_write_log()
    op = log.get_by_id(op_id)

    if op is None:
        return {"status": "not_found", "op_id": op_id}

    if op.undone:
        return {"status": "already_undone", "op_id": op_id}

    if op.tool in _IRREVERSIBLE:
        msg = f"Operation '{op.tool}' cannot be reversed."
        if raise_on_irreversible:
            raise UndoNotPossible(msg)
        return {"status": "skipped_irreversible", "op_id": op_id, "tool": op.tool}

    pid = session_mgr.get_project(session_id)

    if op.tool == "delete_activity":
        # Recreate by PATCHing isn't possible after delete — we POST the before state
        await opc_client.post(
            OPCEndpoints.ACTIVITIES.format(project_id=pid),
            body=op.before,
        )
        snapshot = session_mgr.get_snapshot(session_id)
        if snapshot is not None:
            snapshot.activities.append(op.before)

    elif op.tool == "update_activity":
        await opc_client.patch(
            OPCEndpoints.ACTIVITY.format(project_id=pid, activity_id=op.entity_id),
            body=op.before,
        )
        await session_mgr.apply_write(session_id, "activities", op.entity_id, op.before, id_field="activityId")

    elif op.tool == "create_activity":
        entity_id = op.entity_id if op.entity_id != "new" else None
        if entity_id:
            await opc_client.delete(OPCEndpoints.ACTIVITY.format(project_id=pid, activity_id=entity_id))
            snapshot = session_mgr.get_snapshot(session_id)
            if snapshot is not None:
                snapshot.activities = [a for a in snapshot.activities if a.get("activityId") != entity_id]

    elif op.tool == "update_wbs_node":
        await opc_client.patch(
            OPCEndpoints.WBS_NODE.format(project_id=pid, wbs_id=op.entity_id),
            body=op.before,
        )
        await session_mgr.apply_write(session_id, "wbs_nodes", op.entity_id, op.before, id_field="wbsId")

    elif op.tool == "delete_relationship":
        await opc_client.post(OPCEndpoints.RELS.format(project_id=pid), body=op.before)
        snapshot = session_mgr.get_snapshot(session_id)
        if snapshot is not None:
            snapshot.relationships.append(op.before)

    elif op.tool == "update_relationship":
        await opc_client.patch(
            OPCEndpoints.REL.format(project_id=pid, rel_id=op.entity_id),
            body=op.before,
        )
        await session_mgr.apply_write(session_id, "relationships", op.entity_id, op.before, id_field="relationshipId")

    elif op.tool == "update_calendar":
        await opc_client.patch(
            OPCEndpoints.CALENDAR.format(project_id=pid, calendar_id=op.entity_id),
            body=op.before,
        )
        await session_mgr.apply_write(session_id, "calendars", op.entity_id, op.before, id_field="calendarId")

    else:
        return {"status": "unsupported_undo", "op_id": op_id, "tool": op.tool}

    log.mark_undone(op_id)
    return {"status": "undone", "op_id": op_id, "tool": op.tool, "entity_id": op.entity_id}
