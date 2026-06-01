import logging
import uuid
from datetime import datetime, timedelta

from opc_client.client import OPCClient
from opc_mcp.errors import (
    EntityNotFoundError,
    ProjectScopeViolation,
    RateLimitExceeded,
    SessionNotInitialisedError,
)
from session.cache import BaselineSnapshot, CacheBackend, make_cache
from session.write_log import WriteLog, WriteOperation

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages per-session baselines. Reads are served from cache within the grace period."""

    def __init__(
        self,
        opc_client: OPCClient,
        grace_minutes: int = 10,
        cache_backend: str = "memory",
        allowed_project_ids: list[str] | None = None,
        max_writes_per_session: int = 50,
    ) -> None:
        self._client = opc_client
        self._grace_minutes = grace_minutes
        self._cache: CacheBackend = make_cache(cache_backend)
        self._allowed_project_ids: list[str] = allowed_project_ids or []
        self._max_writes = max_writes_per_session
        self._write_counts: dict[str, int] = {}
        self._write_log = WriteLog()

    # ── Public API ──────────────────────────────────────────────────────────

    async def init_session(self, project_id: str, session_id: str | None = None) -> str:
        """Create a new session (or force-refresh an existing one) and fetch baseline."""
        self._check_project_allowed(project_id)
        sid = session_id or str(uuid.uuid4())
        await self._fetch_baseline(sid, project_id)
        self._write_counts[sid] = 0
        logger.info("Session %s initialised for project %s", sid, project_id)
        return sid

    def get_project(self, session_id: str) -> str:
        """Return the project_id locked to this session."""
        snapshot = self._require_snapshot(session_id)
        return snapshot.project_id

    async def route_read(
        self,
        session_id: str,
        entity: str,
        filters: dict | None = None,
    ) -> list[dict]:
        """Return entity list from cache, refreshing first if the grace period has expired."""
        snapshot = self._require_snapshot(session_id)

        if not snapshot.is_valid():
            snapshot = await self._fetch_baseline(session_id, snapshot.project_id)

        items: list[dict] = getattr(snapshot, entity)
        return _apply_filters(items, filters or {})

    def assert_entity_exists(
        self,
        session_id: str,
        entity: str,
        entity_id: str,
        id_field: str,
    ) -> dict:
        """Raise EntityNotFoundError if the entity is not in the session baseline."""
        snapshot = self._require_snapshot(session_id)
        items: list[dict] = getattr(snapshot, entity)
        match = next((item for item in items if item.get(id_field) == entity_id), None)
        if match is None:
            raise EntityNotFoundError(
                f"{entity_id!r} not found in session baseline for entity '{entity}'. "
                "Use the corresponding list_ tool to retrieve valid IDs."
            )
        return match

    def record_write(
        self,
        session_id: str,
        tool: str,
        entity_type: str,
        entity_id: str,
        before: dict,
        payload: dict,
    ) -> WriteOperation:
        """Log a write before executing it. Raises RateLimitExceeded if quota is hit."""
        count = self._write_counts.get(session_id, 0)
        if count >= self._max_writes:
            raise RateLimitExceeded(
                f"Session {session_id} has reached the maximum of {self._max_writes} writes. "
                "Call init_session to start a fresh session."
            )
        op = self._write_log.record(session_id, tool, entity_type, entity_id, before, payload)
        self._write_counts[session_id] = count + 1
        return op

    def confirm_write(self, op_id: str) -> None:
        self._write_log.confirm(op_id)

    async def apply_write(
        self,
        session_id: str,
        entity: str,
        entity_id: str,
        updates: dict,
        id_field: str = "id",
    ) -> None:
        """Optimistically update the in-memory snapshot after a write and reset the clock."""
        snapshot = self._cache.get(session_id)
        if snapshot is None:
            return

        items: list[dict] = getattr(snapshot, entity)
        for item in items:
            if item.get(id_field) == entity_id:
                item.update(updates)
                break

        snapshot.is_dirty = True
        snapshot.grace_until = datetime.utcnow() + timedelta(minutes=self._grace_minutes)
        self._cache.set(snapshot)

    async def invalidate(self, session_id: str) -> None:
        self._cache.delete(session_id)

    def get_snapshot(self, session_id: str) -> BaselineSnapshot | None:
        return self._cache.get(session_id)

    def get_write_log(self) -> WriteLog:
        return self._write_log

    # ── Internal ────────────────────────────────────────────────────────────

    def _require_snapshot(self, session_id: str) -> BaselineSnapshot:
        snapshot = self._cache.get(session_id)
        if snapshot is None:
            raise SessionNotInitialisedError(
                f"No session found for session_id={session_id!r}. Call init_session first."
            )
        return snapshot

    def _check_project_allowed(self, project_id: str) -> None:
        if self._allowed_project_ids and project_id not in self._allowed_project_ids:
            raise ProjectScopeViolation(
                f"Project {project_id!r} is not in the allowed project list: "
                f"{self._allowed_project_ids}"
            )

    async def _fetch_baseline(self, session_id: str, project_id: str) -> BaselineSnapshot:
        logger.info("Fetching baseline for session %s / project %s", session_id, project_id)
        now = datetime.utcnow()
        activities = await self._client.fetch_activities(project_id)
        wbs = await self._client.fetch_wbs(project_id)
        relationships = await self._client.fetch_relationships(project_id)
        calendars = await self._client.fetch_calendars(project_id)
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
