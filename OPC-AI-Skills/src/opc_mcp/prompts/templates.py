from mcp.server.fastmcp import FastMCP

from opc_mcp.server import mcp


@mcp.prompt()
def reschedule_activity(activity_id: str, new_start_date: str) -> str:
    """Move an activity to a new start date and update all successors."""
    return (
        f"Move activity {activity_id} to start on {new_start_date}. "
        "After updating, check all direct successors and adjust their dates "
        "if they now conflict. Run a schedule calculation when done."
    )


@mcp.prompt()
def add_activity_with_logic(
    wbs_code: str,
    predecessor_id: str,
    relationship_type: str = "FS",
    lag_days: int = 0,
) -> str:
    """Add a new activity under a WBS node with a logic tie to a predecessor."""
    return (
        f"Create a new activity under WBS node {wbs_code}. "
        f"Link it to activity {predecessor_id} with a {relationship_type} relationship "
        f"and {lag_days} day(s) lag. Confirm the new activity ID when done."
    )


@mcp.prompt()
def bulk_duration_change(filter_wbs: str, delta_days: int) -> str:
    """Change the duration of all activities under a WBS node by a fixed number of days."""
    sign = "+" if delta_days >= 0 else ""
    return (
        f"For all activities under WBS node {filter_wbs}, "
        f"change each duration by {sign}{delta_days} days. "
        "List the activities you updated with their old and new durations."
    )


@mcp.prompt()
def generate_schedule_summary(session_id: str) -> str:
    """Produce a concise natural-language project status from the current baseline."""
    return (
        f"Using the session baseline (session_id={session_id}), "
        "summarise the project schedule status: total activities, "
        "activities not started / in progress / complete, "
        "earliest start, latest finish, and any activities with no successor (potential dangling ends)."
    )
