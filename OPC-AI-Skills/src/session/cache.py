import json
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class BaselineSnapshot:
    session_id: str
    project_id: str
    snapshot_time: datetime
    grace_until: datetime
    activities: list[dict] = field(default_factory=list)
    wbs_nodes: list[dict] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)
    calendars: list[dict] = field(default_factory=list)
    is_dirty: bool = False

    def is_valid(self) -> bool:
        return datetime.utcnow() < self.grace_until


class CacheBackend(ABC):
    @abstractmethod
    def get(self, session_id: str) -> BaselineSnapshot | None: ...

    @abstractmethod
    def set(self, snapshot: BaselineSnapshot) -> None: ...

    @abstractmethod
    def delete(self, session_id: str) -> None: ...


class InMemoryCache(CacheBackend):
    def __init__(self) -> None:
        self._store: dict[str, BaselineSnapshot] = {}

    def get(self, session_id: str) -> BaselineSnapshot | None:
        return self._store.get(session_id)

    def set(self, snapshot: BaselineSnapshot) -> None:
        self._store[session_id := snapshot.session_id] = snapshot  # noqa: F841

    def delete(self, session_id: str) -> None:
        self._store.pop(session_id, None)


class SQLiteCache(CacheBackend):
    """Optional persistent cache. Useful when the server process restarts mid-session."""

    def __init__(self, db_path: str = "opc_sessions.db") -> None:
        resolved = Path(db_path).resolve()
        if resolved.is_absolute() and not str(resolved).startswith(str(Path.cwd())):
            raise ValueError(f"Cache db_path must be within the working directory, got: {db_path}")
        self._db_path = str(resolved)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    project_id TEXT,
                    snapshot_time TEXT,
                    grace_until TEXT,
                    activities TEXT,
                    wbs_nodes TEXT,
                    relationships TEXT,
                    calendars TEXT,
                    is_dirty INTEGER
                )"""
            )

    def get(self, session_id: str) -> BaselineSnapshot | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
        if row is None:
            return None
        return BaselineSnapshot(
            session_id=row[0],
            project_id=row[1],
            snapshot_time=datetime.fromisoformat(row[2]),
            grace_until=datetime.fromisoformat(row[3]),
            activities=json.loads(row[4]),
            wbs_nodes=json.loads(row[5]),
            relationships=json.loads(row[6]),
            calendars=json.loads(row[7]),
            is_dirty=bool(row[8]),
        )

    def set(self, snapshot: BaselineSnapshot) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    snapshot.session_id,
                    snapshot.project_id,
                    snapshot.snapshot_time.isoformat(),
                    snapshot.grace_until.isoformat(),
                    json.dumps(snapshot.activities),
                    json.dumps(snapshot.wbs_nodes),
                    json.dumps(snapshot.relationships),
                    json.dumps(snapshot.calendars),
                    int(snapshot.is_dirty),
                ),
            )

    def delete(self, session_id: str) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))


def make_cache(backend: str = "memory") -> CacheBackend:
    if backend == "sqlite":
        return SQLiteCache()
    return InMemoryCache()
