import pytest
from session.manager import SessionManager
from session.cache import InMemoryCache


@pytest.fixture
async def session_mgr(mock_opc_client):
    mgr = SessionManager(opc_client=mock_opc_client, grace_minutes=10, cache_backend="memory")
    return mgr


@pytest.mark.asyncio
async def test_init_session_populates_cache(session_mgr, mock_opc_client):
    sid = await session_mgr.init_session(project_id="P1")
    snapshot = session_mgr.get_snapshot(sid)
    assert snapshot is not None
    assert len(snapshot.activities) == 2
    mock_opc_client.fetch_activities.assert_called_once_with("P1")


@pytest.mark.asyncio
async def test_route_read_serves_from_cache(session_mgr, mock_opc_client):
    sid = await session_mgr.init_session(project_id="P1")
    # Second read should NOT call the API again
    result = await session_mgr.route_read(sid, "activities", "P1")
    assert len(result) == 2
    mock_opc_client.fetch_activities.assert_called_once()  # still only 1 call


@pytest.mark.asyncio
async def test_route_read_filter_by_wbs(session_mgr):
    sid = await session_mgr.init_session(project_id="P1")
    result = await session_mgr.route_read(sid, "activities", "P1", filters={"wbsId": "W1"})
    assert all(a["wbsId"] == "W1" for a in result)


@pytest.mark.asyncio
async def test_apply_write_updates_cache(session_mgr):
    sid = await session_mgr.init_session(project_id="P1")
    await session_mgr.apply_write(sid, "activities", "A1000", {"name": "Updated Design"}, id_field="activityId")
    snapshot = session_mgr.get_snapshot(sid)
    activity = next(a for a in snapshot.activities if a["activityId"] == "A1000")
    assert activity["name"] == "Updated Design"
    assert snapshot.is_dirty


@pytest.mark.asyncio
async def test_expired_grace_triggers_refetch(mock_opc_client):
    from datetime import timedelta, datetime
    mgr = SessionManager(opc_client=mock_opc_client, grace_minutes=10)
    sid = await mgr.init_session(project_id="P1")

    # Force expiry
    snapshot = mgr.get_snapshot(sid)
    snapshot.grace_until = datetime.utcnow() - timedelta(seconds=1)

    await mgr.route_read(sid, "activities", "P1")
    assert mock_opc_client.fetch_activities.call_count == 2  # re-fetched after expiry
