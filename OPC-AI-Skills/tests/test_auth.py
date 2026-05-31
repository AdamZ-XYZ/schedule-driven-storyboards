import pytest
import respx
import httpx
from datetime import datetime, timedelta

from opc_client.auth import OPCTokenManager


TOKEN_URL = "https://example.oraclecloud.com/oauth/token"


@pytest.fixture
def token_manager():
    return OPCTokenManager(
        token_url=TOKEN_URL,
        client_id="test-client",
        client_secret="test-secret",
    )


@respx.mock
@pytest.mark.asyncio
async def test_fetch_token(token_manager):
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "tok123", "expires_in": 3600})
    )
    token = await token_manager.get_token()
    assert token == "tok123"


@respx.mock
@pytest.mark.asyncio
async def test_cached_token_no_second_request(token_manager):
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "tok123", "expires_in": 3600})
    )
    await token_manager.get_token()
    await token_manager.get_token()
    assert route.call_count == 1  # only one HTTP call


@respx.mock
@pytest.mark.asyncio
async def test_expired_token_refreshes(token_manager):
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "tok-new", "expires_in": 3600})
    )
    # Simulate already-expired token
    token_manager._token = "tok-old"
    token_manager._expires_at = datetime.utcnow() - timedelta(seconds=10)

    token = await token_manager.get_token()
    assert token == "tok-new"
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_invalidate_clears_token(token_manager):
    token_manager._token = "tok"
    token_manager._expires_at = datetime.utcnow() + timedelta(hours=1)
    token_manager.invalidate()
    assert token_manager._token is None
    assert token_manager._expires_at is None
