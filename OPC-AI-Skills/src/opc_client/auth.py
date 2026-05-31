import logging
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger(__name__)


class OPCTokenManager:
    """Fetches and caches an OAuth 2.0 client-credentials token for OPC."""

    _REFRESH_BUFFER_SECONDS = 60

    def __init__(self, token_url: str, client_id: str, client_secret: str) -> None:
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._expires_at: datetime | None = None

    async def get_token(self) -> str:
        if self._token and self._expires_at:
            if datetime.utcnow() < self._expires_at - timedelta(seconds=self._REFRESH_BUFFER_SECONDS):
                return self._token
        return await self._fetch_new_token()

    async def _fetch_new_token(self) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            response.raise_for_status()
            payload = response.json()

        self._token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 3600))
        self._expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        logger.debug("OPC token refreshed, expires at %s", self._expires_at)
        return self._token

    def invalidate(self) -> None:
        self._token = None
        self._expires_at = None
