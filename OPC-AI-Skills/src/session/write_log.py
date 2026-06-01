import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class WriteOperation:
    op_id: str
    session_id: str
    timestamp: datetime
    tool: str           # e.g. "update_activity"
    entity_type: str    # "activities", "wbs_nodes", "relationships", "calendars"
    entity_id: str
    before: dict        # entity state before the write (from baseline snapshot)
    payload: dict       # update payload / create body sent to OPC
    opc_confirmed: bool = False
    undone: bool = False


class WriteLog:
    """Append-only per-session log of all write operations."""

    def __init__(self) -> None:
        self._log: list[WriteOperation] = []

    def record(
        self,
        session_id: str,
        tool: str,
        entity_type: str,
        entity_id: str,
        before: dict,
        payload: dict,
    ) -> WriteOperation:
        op = WriteOperation(
            op_id=str(uuid.uuid4()),
            session_id=session_id,
            timestamp=datetime.utcnow(),
            tool=tool,
            entity_type=entity_type,
            entity_id=entity_id,
            before=before,
            payload=payload,
        )
        self._log.append(op)
        return op

    def confirm(self, op_id: str) -> None:
        op = self._get(op_id)
        if op:
            op.opc_confirmed = True

    def mark_undone(self, op_id: str) -> None:
        op = self._get(op_id)
        if op:
            op.undone = True

    def get_all(self, session_id: str) -> list[WriteOperation]:
        return [op for op in self._log if op.session_id == session_id and not op.undone]

    def get_last(self, session_id: str) -> WriteOperation | None:
        ops = self.get_all(session_id)
        return ops[-1] if ops else None

    def get_by_id(self, op_id: str) -> WriteOperation | None:
        return self._get(op_id)

    def _get(self, op_id: str) -> WriteOperation | None:
        return next((op for op in self._log if op.op_id == op_id), None)
