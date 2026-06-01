from pydantic import ValidationError as PydanticValidationError

from opc_mcp.errors import ValidationError
from opc_mcp.middleware import safe_tool
from opc_mcp.schemas import RelationshipCreate, RelationshipUpdate
from opc_mcp.server import mcp, opc_client, session_mgr
from opc_client.endpoints import OPCEndpoints


@mcp.tool()
@safe_tool
async def list_relationships(
    session_id: str,
    predecessor_id: str | None = None,
    successor_id: str | None = None,
) -> list[dict]:
    """List activity relationships (logic ties). Served from session baseline cache."""
    items = await session_mgr.route_read(session_id=session_id, entity="relationships")
    if predecessor_id:
        items = [r for r in items if r.get("predecessorActivityId") == predecessor_id]
    if successor_id:
        items = [r for r in items if r.get("successorActivityId") == successor_id]
    return items


@mcp.tool()
@safe_tool
async def create_relationship(
    session_id: str,
    predecessor_activity_id: str,
    successor_activity_id: str,
    relationship_type: str = "FS",
    lag: int = 0,
    dry_run: bool = False,
) -> dict:
    """Create a logic tie between two activities.

    relationship_type: FS (finish-to-start), SS, FF, SF.
    lag: days (positive = lag, negative = lead).
    Set dry_run=True to preview without touching OPC.
    IMPORTANT: verify both activity IDs with get_activity before calling.
    """
    try:
        validated = RelationshipCreate(
            predecessorActivityId=predecessor_activity_id,
            successorActivityId=successor_activity_id,
            type=relationship_type,
            lag=lag,
        )
    except PydanticValidationError as e:
        raise ValidationError(str(e)) from e

    # Verify both activities exist in baseline
    session_mgr.assert_entity_exists(session_id, "activities", predecessor_activity_id, "activityId")
    session_mgr.assert_entity_exists(session_id, "activities", successor_activity_id, "activityId")

    pid = session_mgr.get_project(session_id)
    payload = validated.model_dump(mode="json")

    if dry_run:
        return {"dry_run": True, "would_create": payload, "project_id": pid}

    op = session_mgr.record_write(session_id, "create_relationship", "relationships", "new", {}, payload)
    result = await opc_client.post(OPCEndpoints.RELS.format(project_id=pid), body=payload)
    session_mgr.confirm_write(op.op_id)

    snapshot = session_mgr.get_snapshot(session_id)
    if snapshot is not None:
        snapshot.relationships.append(result)
    return result


@mcp.tool()
@safe_tool
async def update_relationship(
    session_id: str,
    relationship_id: str,
    updates: dict,
    dry_run: bool = False,
) -> dict:
    """Update an existing relationship. Allowed fields: type, lag.

    IMPORTANT: Only use IDs returned by list_relationships.
    Set dry_run=True to preview without touching OPC.
    """
    try:
        validated = RelationshipUpdate.model_validate(updates)
    except PydanticValidationError as e:
        raise ValidationError(str(e)) from e

    before = session_mgr.assert_entity_exists(session_id, "relationships", relationship_id, "relationshipId")
    pid = session_mgr.get_project(session_id)
    payload = validated.model_dump(exclude_none=True, mode="json")

    if dry_run:
        return {"dry_run": True, "relationship_id": relationship_id, "before": before, "would_apply": payload}

    op = session_mgr.record_write(session_id, "update_relationship", "relationships", relationship_id, dict(before), payload)
    result = await opc_client.patch(OPCEndpoints.REL.format(project_id=pid, rel_id=relationship_id), body=payload)
    session_mgr.confirm_write(op.op_id)
    await session_mgr.apply_write(session_id, "relationships", relationship_id, payload, id_field="relationshipId")
    return result


@mcp.tool()
@safe_tool
async def delete_relationship(session_id: str, relationship_id: str, dry_run: bool = False) -> dict:
    """Delete a logic tie. CONFIRM with the user before calling without dry_run=True.

    IMPORTANT: Only use IDs returned by list_relationships.
    """
    before = session_mgr.assert_entity_exists(session_id, "relationships", relationship_id, "relationshipId")
    pid = session_mgr.get_project(session_id)

    if dry_run:
        return {"dry_run": True, "would_delete": before}

    op = session_mgr.record_write(session_id, "delete_relationship", "relationships", relationship_id, dict(before), {})
    await opc_client.delete(OPCEndpoints.REL.format(project_id=pid, rel_id=relationship_id))
    session_mgr.confirm_write(op.op_id)

    snapshot = session_mgr.get_snapshot(session_id)
    if snapshot is not None:
        snapshot.relationships = [r for r in snapshot.relationships if r.get("relationshipId") != relationship_id]
    return {"deleted": relationship_id, "op_id": op.op_id}
