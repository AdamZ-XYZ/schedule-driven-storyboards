class OPCError(Exception):
    """Base for all OPC AI Skills errors."""


class SessionNotInitialisedError(OPCError):
    """Tool called with an unknown or expired session_id."""


class EntityNotFoundError(OPCError):
    """Entity ID not present in the session baseline."""


class ProjectScopeViolation(OPCError):
    """Attempted to access a project outside the allowed set."""


class ValidationError(OPCError):
    """Tool input failed schema validation."""


class TransientError(OPCError):
    """Temporary OPC API failure (5xx, timeout) — safe to retry."""


class RateLimitExceeded(OPCError):
    """Session has exceeded the maximum writes per session."""


class UndoNotPossible(OPCError):
    """Operation cannot be reversed (e.g. schedule_run, already undone)."""


class OPCAPIError(OPCError):
    """Non-2xx response from the OPC REST API."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"OPC API {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail
