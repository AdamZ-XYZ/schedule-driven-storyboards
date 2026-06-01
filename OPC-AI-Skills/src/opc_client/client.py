import logging
from typing import Any

import httpx

from .auth import OPCTokenManager
from .endpoints import OPCEndpoints

# Import unified error class; keep a local alias so existing callers still work
from opc_mcp.errors import OPCAPIError, TransientError  # noqa: E402

logger = logging.getLogger(__name__)

_DEFAULT_FIELDS = {
    "activities": "activityId,name,startDate,finishDate,duration,status,wbsId,calendarId",
    "wbs": "wbsId,name,parentWbsId,sequenceNumber",
    "relationships": "relationshipId,predecessorActivityId,successorActivityId,type,lag",
    "calendars": "calendarId,name,type",
}


_TIMEOUT = httpx.Timeout(30.0)


class OPCClient:
    """Thin async wrapper around the Oracle Primavera Cloud REST API."""

    def __init__(self, base_url: str, token_manager: OPCTokenManager) -> None:
        self._base_url = base_url.rstrip("/")
        self._token_manager = token_manager

    async def _headers(self) -> dict[str, str]:
        token = await self._token_manager.get_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def get(self, path: str, params: dict | None = None) -> Any:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(
                self._base_url + path,
                headers=await self._headers(),
                params=params or {},
            )
        return self._handle(response)

    async def post(self, path: str, body: dict) -> Any:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                self._base_url + path,
                headers=await self._headers(),
                json=body,
            )
        return self._handle(response)

    async def patch(self, path: str, body: dict) -> Any:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.patch(
                self._base_url + path,
                headers=await self._headers(),
                json=body,
            )
        return self._handle(response)

    async def delete(self, path: str) -> None:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.delete(
                self._base_url + path,
                headers=await self._headers(),
            )
        self._handle(response, expect_body=False)

    # ── Convenience fetchers used by SessionManager for baseline load ──────

    async def fetch_activities(self, project_id: str) -> list[dict]:
        return await self._fetch_all(
            OPCEndpoints.ACTIVITIES.format(project_id=project_id),
            fields=_DEFAULT_FIELDS["activities"],
        )

    async def fetch_wbs(self, project_id: str) -> list[dict]:
        return await self._fetch_all(
            OPCEndpoints.WBS.format(project_id=project_id),
            fields=_DEFAULT_FIELDS["wbs"],
        )

    async def fetch_relationships(self, project_id: str) -> list[dict]:
        return await self._fetch_all(
            OPCEndpoints.RELS.format(project_id=project_id),
            fields=_DEFAULT_FIELDS["relationships"],
        )

    async def fetch_calendars(self, project_id: str) -> list[dict]:
        return await self._fetch_all(
            OPCEndpoints.CALENDARS.format(project_id=project_id),
            fields=_DEFAULT_FIELDS["calendars"],
        )

    async def _fetch_all(self, path: str, fields: str, page_size: int = 100) -> list[dict]:
        results: list[dict] = []
        offset = 0
        while True:
            data = await self.get(path, params={"fields": fields, "limit": page_size, "offset": offset})
            items = data if isinstance(data, list) else data.get("items", [])
            results.extend(items)
            if len(items) < page_size:
                break
            offset += page_size
        return results

    @staticmethod
    def _handle(response: httpx.Response, expect_body: bool = True) -> Any:
        if response.is_error:
            exc = OPCAPIError(response.status_code, response.text)
            if response.status_code >= 500:
                raise TransientError(str(exc)) from exc
            raise exc
        if not expect_body or response.status_code == 204:
            return None
        return response.json()
