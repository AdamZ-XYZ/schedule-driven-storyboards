from pydantic import ValidationError as PydanticValidationError

from opc_mcp.errors import ValidationError
from opc_mcp.middleware import safe_tool
from opc_mcp.schemas import WBSNodeCreate, WBSNodeUpdate
from opc_mcp.server import mcp, opc_client, session_mgr
from opc_client.endpoints import OPCEndpoints


@mcp.tool()
@safe_tool
async def list_wbs_nodes(
    session_id: str,
    parent_wbs_id: str | None = None,
) -> list[dict]:
    """List WBS nodes, optionally filtered by parent. Served from session baseline cache."""
    return await session_mgr.route_read(
        session_id=session_id,
        entity="wbs_nodes",
        filters={"parentWbsId": parent_wbs_id},
    )


@mcp.tool()
@safe_tool
async def get_wbs_node(session_id: str, wbs_id: str) -> dict:
    """Get a single WBS node by ID from the session baseline cache."""
    return session_mgr.assert_entity_exists(session_id, "wbs_nodes", wbs_id, "wbsId")


@mcp.tool()
@safe_tool
async def create_wbs_node(session_id: str, wbs_node: dict, dry_run: bool = False) -> dict:
    """Create a new WBS node. Required: name. Optional: parentWbsId, sequenceNumber.

    Set dry_run=True to preview without touching OPC.
    """
    try:
        validated = WBSNodeCreate.model_validate(wbs_node)
    except PydanticValidationError as e:
        raise ValidationError(str(e)) from e

    pid = session_mgr.get_project(session_id)
    payload = validated.model_dump(exclude_none=True, mode="json")

    if dry_run:
        return {"dry_run": True, "would_create": payload, "project_id": pid}

    op = session_mgr.record_write(session_id, "create_wbs_node", "wbs_nodes", "new", {}, payload)
    result = await opc_client.post(OPCEndpoints.WBS.format(project_id=pid), body=payload)
    session_mgr.confirm_write(op.op_id)

    snapshot = session_mgr.get_snapshot(session_id)
    if snapshot is not None:
        snapshot.wbs_nodes.append(result)
    return result


@mcp.tool()
@safe_tool
async def update_wbs_node(
    session_id: str,
    wbs_id: str,
    updates: dict,
    dry_run: bool = False,
) -> dict:
    """Update an existing WBS node. Allowed fields: name, sequenceNumber.

    IMPORTANT: Only use WBS IDs returned by list_wbs_nodes or get_wbs_node.
    Set dry_run=True to preview without touching OPC.
    """
    try:
        validated = WBSNodeUpdate.model_validate(updates)
    except PydanticValidationError as e:
        raise ValidationError(str(e)) from e

    before = session_mgr.assert_entity_exists(session_id, "wbs_nodes", wbs_id, "wbsId")
    pid = session_mgr.get_project(session_id)
    payload = validated.model_dump(exclude_none=True, mode="json")

    if dry_run:
        return {"dry_run": True, "wbs_id": wbs_id, "before": before, "would_apply": payload}

    op = session_mgr.record_write(session_id, "update_wbs_node", "wbs_nodes", wbs_id, dict(before), payload)
    result = await opc_client.patch(OPCEndpoints.WBS_NODE.format(project_id=pid, wbs_id=wbs_id), body=payload)
    session_mgr.confirm_write(op.op_id)
    await session_mgr.apply_write(session_id, "wbs_nodes", wbs_id, payload, id_field="wbsId")
    return result
