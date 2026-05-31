import logging
import uuid
from datetime import datetime, timedelta

from opc_client.client import OPCClient
from session.cache import BaselineSnapshot, CacheBackend, make_cache

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages per-session baselines. Reads are served from cache within the grace period."""

    def __init__(
        self,
        opc_client: OPCClient,
        grace_minutes: int = 10,
        cache_backend: str = "memory",
    ) -> None:
        self._client = opc_client
        self._grace_minutes = grace_minutes
        self._cache: CacheBackend = make_cache(cache_backend)

    # ── Public API ──────────────────────────────────────────────────────────

    async def init_session(self, project_id: str, session_id: str | None = None) -> str:
        """Create a new session (or force-refresh an existing one) and fetch baseline."""
        sid = session_id or str(uuid.uuid4())
        await self._fetch_baseline(sid, project_id)
        logger.info("Session %s initialised for project %s", sid, project_id)
        return sid

    async def route_read(
        self,
        session_id: str,
        entity: str,
        project_id: str,
        filters: dict | None = None,
    ) -> list[dict]:
        """Return entity list from cache, refreshing first if the grace period has expired."""
        snapshot = self._cache.get(session_id)

        if snapshot is None or not snapshot.is_valid():
            snapshot = await self._fetch_baseline(session_id, project_id)

        items: list[dict] = getattr(snapshot, entity)
        return _apply_filters(items, filters or {})

    async def apply_write(
        self,
        session_id: str,
        entity: str,
        record_id: str,
        updates: dict,
        id_field: str = "id",
    ) -> None:
        """Optimistically update the in-memory snapshot after a write and reset the clock."""
        snapshot = self._cache.get(session_id)
        if snapshot is None:
            return

        items: list[dict] = getattr(snapshot, entity)
        for item in items:
            if item.get(id_field) == record_id:
                item.update(updates)
                break

        snapshot.is_dirty = True
        snapshot.grace_until = datetime.utcnow() + timedelta(minutes=self._grace_minutes)
        self._cache.set(snapshot)

    async def invalidate(self, session_id: str) -> None:
        self._cache.delete(session_id)

    def get_snapshot(self, session_id: str) -> BaselineSnapshot | None:
        return self._cache.get(session_id)

    # ── Internal ────────────────────────────────────────────────────────────

    async def _fetch_baseline(self, session_id: str, project_id: str) -> BaselineSnapshot:
        logger.info("Fetching baseline for session %s / project %s", session_id, project_id)
        now = datetime.utcnow()
        activities, wbs, relationships, calendars = (
            await self._client.fetch_activities(project_id),
            await self._client.fetch_wbs(project_id),
            await self._client.fetch_relationships(project_id),
            await self._client.fetch_calendars(project_id),
        )
        snapshot = BaselineSnapshot(
            session_id=session_id,
            project_id=project_id,
            snapshot_time=now,
            grace_until=now + timedelta(minutes=self._grace_minutes),
            activities=activities,
            wbs_nodes=wbs,
            relationships=relationships,
            calendars=calendars,
        )
        self._cache.set(snapshot)
        return snapshot


def _apply_filters(items: list[dict], filters: dict) -> list[dict]:
    result = items
    for key, value in filters.items():
        if value is not None:
            result = [item for item in result if item.get(key) == value]
    return result
