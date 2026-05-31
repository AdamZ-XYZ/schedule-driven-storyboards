from mcp.server.fastmcp import FastMCP

from opc_mcp.server import mcp, session_mgr


@mcp.resource("baseline://session/{session_id}/meta")
async def baseline_meta(session_id: str) -> dict:
    """Project baseline metadata: snapshot time, grace period expiry, entity counts."""
    snapshot = session_mgr.get_snapshot(session_id)
    if snapshot is None:
        return {"error": "No baseline for this session. Call init_session first."}
    return {
        "session_id": snapshot.session_id,
        "project_id": snapshot.project_id,
        "snapshot_time": snapshot.snapshot_time.isoformat(),
        "grace_until": snapshot.grace_until.isoformat(),
        "is_dirty": snapshot.is_dirty,
        "activity_count": len(snapshot.activities),
        "wbs_count": len(snapshot.wbs_nodes),
        "relationship_count": len(snapshot.relationships),
        "calendar_count": len(snapshot.calendars),
    }


@mcp.resource("baseline://session/{session_id}/activities")
async def baseline_activities(session_id: str) -> list[dict]:
    """Full activity list as captured at baseline snapshot time."""
    snapshot = session_mgr.get_snapshot(session_id)
    if snapshot is None:
        return []
    return snapshot.activities


@mcp.resource("baseline://session/{session_id}/wbs")
async def baseline_wbs(session_id: str) -> list[dict]:
    """Full WBS node list as captured at baseline snapshot time."""
    snapshot = session_mgr.get_snapshot(session_id)
    if snapshot is None:
        return []
    return snapshot.wbs_nodes


@mcp.resource("baseline://session/{session_id}/relationships")
async def baseline_relationships(session_id: str) -> list[dict]:
    """Full relationship list as captured at baseline snapshot time."""
    snapshot = session_mgr.get_snapshot(session_id)
    if snapshot is None:
        return []
    return snapshot.relationships
