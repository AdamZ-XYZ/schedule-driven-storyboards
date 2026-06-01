import asyncio
import functools
import logging
import time
from typing import Any, Callable

from opc_mcp.errors import (
    EntityNotFoundError,
    OPCAPIError,
    OPCError,
    ProjectScopeViolation,
    RateLimitExceeded,
    SessionNotInitialisedError,
    TransientError,
    ValidationError,
)

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("opc.audit")


def safe_tool(fn: Callable) -> Callable:
    """Wrap an MCP tool so it always returns a structured dict, never a raw exception.

    Transient errors are retried up to 3 times with exponential backoff.
    All tool invocations are written to the audit log.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.monotonic()
        tool_name = fn.__name__

        audit_logger.info(
            "CALL tool=%s args=%s kwargs=%s",
            tool_name,
            _safe_repr(args),
            _safe_repr(kwargs),
        )

        result = await _execute_with_retry(fn, args, kwargs)

        elapsed_ms = int((time.monotonic() - start) * 1000)
        if isinstance(result, dict) and "error" in result:
            audit_logger.warning("FAIL tool=%s error=%s elapsed_ms=%d", tool_name, result, elapsed_ms)
        else:
            audit_logger.info("OK   tool=%s elapsed_ms=%d", tool_name, elapsed_ms)

        return result

    return wrapper


async def _execute_with_retry(fn: Callable, args: tuple, kwargs: dict, max_retries: int = 3) -> Any:
    for attempt in range(max_retries + 1):
        try:
            return await fn(*args, **kwargs)
        except TransientError as e:
            if attempt < max_retries:
                wait = 2 ** attempt
                logger.warning("Transient error on %s, retry %d/%d in %ds: %s", fn.__name__, attempt + 1, max_retries, wait, e)
                await asyncio.sleep(wait)
            else:
                return {"error": "transient", "message": f"OPC API unavailable after {max_retries} retries: {e}"}
        except SessionNotInitialisedError as e:
            return {"error": "session_not_found", "message": str(e), "hint": "Call init_session first."}
        except EntityNotFoundError as e:
            return {"error": "not_found", "message": str(e), "hint": "Use a list_ tool to find valid IDs."}
        except ProjectScopeViolation as e:
            return {"error": "scope_violation", "message": str(e)}
        except RateLimitExceeded as e:
            return {"error": "rate_limit", "message": str(e)}
        except ValidationError as e:
            return {"error": "validation", "message": str(e), "hint": "Check field names and value types."}
        except OPCAPIError as e:
            if e.status_code >= 500:
                if attempt < max_retries:
                    wait = 2 ** attempt
                    await asyncio.sleep(wait)
                    continue
                return {"error": "api_error", "status_code": e.status_code, "message": e.detail}
            return {"error": "api_error", "status_code": e.status_code, "message": e.detail}
        except OPCError as e:
            return {"error": "opc_error", "message": str(e)}
        except Exception as e:
            logger.exception("Unexpected error in tool %s", fn.__name__)
            return {"error": "internal", "message": f"Unexpected error: {type(e).__name__}: {e}"}

    return {"error": "internal", "message": "Retry loop exhausted unexpectedly"}


_REDACT_KEYS = frozenset({"session_id", "token", "secret", "password", "client_secret", "access_token"})


def _safe_repr(obj: Any) -> str:
    try:
        if isinstance(obj, dict):
            safe = {k: "***" if k in _REDACT_KEYS else v for k, v in obj.items()}
            s = repr(safe)
        elif isinstance(obj, (list, tuple)):
            s = repr(type(obj)(  # type: ignore[call-arg]
                _safe_repr(item) if isinstance(item, dict) else item for item in obj
            ))
        else:
            s = repr(obj)
        return s[:200] if len(s) > 200 else s
    except Exception:
        return "<unrepresentable>"
