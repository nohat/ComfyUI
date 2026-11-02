"""Tests for the COMFYSTUDIO_API_TOKEN bearer-token middleware"""

from unittest.mock import MagicMock

import pytest
from aiohttp import WSMsgType, web
from aiohttp.test_utils import TestClient, TestServer

import server

TOKEN = "s3cret-token-for-tests"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


async def pong(request):
    return web.Response(text="pong")


async def ws_echo(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    await ws.send_str("hello")
    await ws.close()
    return ws


def make_prompt_server():
    prompt_server = server.PromptServer(None, MagicMock(enabled=False))
    prompt_server.app.router.add_get("/ping", pong)
    prompt_server.app.router.add_post("/ping", pong)
    prompt_server.app.router.add_get("/ws-test", ws_echo)
    return prompt_server


@pytest.fixture
def token_env(monkeypatch):
    monkeypatch.setenv("COMFYSTUDIO_API_TOKEN", TOKEN)


@pytest.mark.asyncio
async def test_token_middleware_is_first(token_env):
    prompt_server = make_prompt_server()
    assert prompt_server.app.middlewares[0].__name__ == "bearer_token_middleware"


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Bearer wrong"},
    {"Authorization": "Bearer "},
    {"Authorization": "Bearer"},
    {"Authorization": TOKEN},
    {"Authorization": f"Basic {TOKEN}"},
    {"Authorization": f"Bearer {TOKEN}x"},
    {"Authorization": f"Bearer {TOKEN[:-1]}"},
    {"Authorization": "Bearer éé"},
])
async def test_rejects_missing_or_wrong_token(token_env, headers):
    async with TestClient(TestServer(make_prompt_server().app)) as client:
        for method in (client.get, client.post):
            resp = await method("/ping", headers=headers)
            assert resp.status == 401
            body = await resp.read()
            assert body == b""
            assert TOKEN.encode() not in body


@pytest.mark.asyncio
async def test_accepts_right_token(token_env):
    async with TestClient(TestServer(make_prompt_server().app)) as client:
        resp = await client.get("/ping", headers=AUTH)
        assert resp.status == 200
        assert await resp.text() == "pong"
        resp = await client.post("/ping", headers=AUTH)
        assert resp.status == 200


@pytest.mark.asyncio
async def test_scheme_is_case_insensitive(token_env):
    async with TestClient(TestServer(make_prompt_server().app)) as client:
        resp = await client.get("/ping", headers={"Authorization": f"bearer {TOKEN}"})
        assert resp.status == 200


@pytest.mark.asyncio
async def test_query_parameter_is_not_accepted(token_env):
    async with TestClient(TestServer(make_prompt_server().app)) as client:
        for name in ("token", "api_token", "access_token", "authorization"):
            resp = await client.get("/ping", params={name: TOKEN})
            assert resp.status == 401


@pytest.mark.asyncio
async def test_unknown_paths_are_not_exempt(token_env):
    async with TestClient(TestServer(make_prompt_server().app)) as client:
        for path in ("/", "/system_stats", "/ws", "/does-not-exist", "/api/system_stats"):
            resp = await client.get(path)
            assert resp.status == 401
        resp = await client.options("/ping")
        assert resp.status == 401


@pytest.mark.asyncio
async def test_websocket_upgrade_without_header_is_rejected(token_env):
    async with TestClient(TestServer(make_prompt_server().app)) as client:
        resp = await client.get("/ws-test", headers={
            "Connection": "Upgrade", "Upgrade": "websocket",
            "Sec-WebSocket-Version": "13", "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
        })
        assert resp.status == 401
        with pytest.raises(Exception):
            await client.ws_connect("/ws-test")
        with pytest.raises(Exception):
            await client.ws_connect("/ws-test", params={"token": TOKEN})


@pytest.mark.asyncio
async def test_websocket_upgrade_with_header_is_accepted(token_env):
    async with TestClient(TestServer(make_prompt_server().app)) as client:
        ws = await client.ws_connect("/ws-test", headers=AUTH)
        msg = await ws.receive()
        assert msg.type == WSMsgType.TEXT
        assert msg.data == "hello"
        await ws.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, ""])
async def test_unset_or_empty_env_leaves_server_unchanged(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("COMFYSTUDIO_API_TOKEN", raising=False)
    else:
        monkeypatch.setenv("COMFYSTUDIO_API_TOKEN", value)
    prompt_server = make_prompt_server()
    assert all(m.__name__ != "bearer_token_middleware" for m in prompt_server.app.middlewares)
    async with TestClient(TestServer(prompt_server.app)) as client:
        resp = await client.get("/ping")
        assert resp.status == 200
        ws = await client.ws_connect("/ws-test")
        assert (await ws.receive()).data == "hello"
        await ws.close()


@pytest.mark.asyncio
async def test_existing_origin_check_still_applies_with_valid_token(token_env):
    async with TestClient(TestServer(make_prompt_server().app)) as client:
        resp = await client.get("/ping", headers={**AUTH, "Sec-Fetch-Site": "cross-site"})
        assert resp.status == 403
        resp = await client.get("/ping", headers={
            **AUTH, "Host": "127.0.0.1:8188", "Origin": "http://evil.example"})
        assert resp.status == 403


@pytest.mark.asyncio
async def test_token_is_not_logged(token_env, caplog):
    caplog.set_level("DEBUG")
    async with TestClient(TestServer(make_prompt_server().app)) as client:
        await client.get("/ping")
        await client.get("/ping", headers={"Authorization": "Bearer wrong"})
        await client.get("/ping", headers=AUTH)
    assert TOKEN not in caplog.text
