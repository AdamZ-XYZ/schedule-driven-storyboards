import pytest
from datetime import datetime, timedelta

from session.cache import BaselineSnapshot, InMemoryCache, SQLiteCache, make_cache


def _make_snapshot(session_id="s1", grace_minutes=10) -> BaselineSnapshot:
    now = datetime.utcnow()
    return BaselineSnapshot(
        session_id=session_id,
        project_id="P1",
        snapshot_time=now,
        grace_until=now + timedelta(minutes=grace_minutes),
        activities=[{"activityId": "A1000"}],
        wbs_nodes=[{"wbsId": "W1"}],
        relationships=[],
        calendars=[],
    )


class TestInMemoryCache:
    def test_set_and_get(self):
        cache = InMemoryCache()
        snap = _make_snapshot()
        cache.set(snap)
        assert cache.get("s1") is snap

    def test_get_missing_returns_none(self):
        cache = InMemoryCache()
        assert cache.get("nonexistent") is None

    def test_delete(self):
        cache = InMemoryCache()
        cache.set(_make_snapshot())
        cache.delete("s1")
        assert cache.get("s1") is None


class TestBaselineSnapshot:
    def test_valid_within_grace(self):
        snap = _make_snapshot(grace_minutes=10)
        assert snap.is_valid()

    def test_invalid_after_grace(self):
        snap = _make_snapshot(grace_minutes=-1)
        assert not snap.is_valid()


class TestSQLiteCache:
    def test_round_trip(self, tmp_path):
        db = str(tmp_path / "test.db")
        cache = SQLiteCache(db_path=db)
        snap = _make_snapshot()
        cache.set(snap)
        loaded = cache.get("s1")
        assert loaded is not None
        assert loaded.session_id == "s1"
        assert loaded.activities == [{"activityId": "A1000"}]

    def test_delete(self, tmp_path):
        db = str(tmp_path / "test.db")
        cache = SQLiteCache(db_path=db)
        cache.set(_make_snapshot())
        cache.delete("s1")
        assert cache.get("s1") is None


def test_make_cache_memory():
    assert isinstance(make_cache("memory"), InMemoryCache)


def test_make_cache_sqlite(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert isinstance(make_cache("sqlite"), SQLiteCache)
