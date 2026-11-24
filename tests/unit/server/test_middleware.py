import logging
import re
from typing import Protocol, cast

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from llm_app.server.middleware import RequestContextMiddleware

HEX32 = re.compile(r'^[0-9a-f]{32}$')


class AccessLogRecord(Protocol):
    request_id: str
    method: str
    path: str
    status_code: int
    latency: float

    def getMessage(self) -> str: ...


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get('/ping')
    def ping(request: Request) -> dict[str, str]:
        return {'request_id': request.state.request_id}

    @app.get('/headers')
    def headers() -> JSONResponse:
        return JSONResponse({'ok': 'true'}, headers={'X-Request_ID': 'from-route'})

    return app


def test_valid_request_id_is_passed_through(app: FastAPI) -> None:
    with TestClient(app) as client:
        resp = client.get('/ping', headers={'X-Request-ID': 'test-abc-123'})

    assert resp.status_code == 200
    assert resp.json() == {'request_id': 'test-abc-123'}
    assert resp.headers['x-request-id'] == 'test-abc-123'
    assert resp.headers.get_list('x-request-id') == ['test-abc-123']


def test_missing_request_id_generates_hex32(app: FastAPI) -> None:
    with TestClient(app) as client:
        resp = client.get('/ping')

    request_id = resp.headers['x-request-id']
    assert HEX32.fullmatch(request_id) is not None
    assert len(request_id) == 32


""" @pytest.mark.parametrize(
    ('bad_id', 'desc'),
    [
        ('bad id example', '包含空格'),
        ('a' * 65, '长度65，超出上限'),
        ('a' * 7, '长度7，超出下限'),
    ],
) """


@pytest.mark.parametrize(
    'bad_id',
    [
        pytest.param('bad id', id='包含空格'),
        pytest.param('a' * 65, id='长度超过64上限'),
        pytest.param('a' * 7, id='长度未达到8最下限'),
    ],
)
def test_invalid_request_id_is_replace(app: FastAPI, bad_id: str) -> None:
    with TestClient(app) as client:
        resp = client.get('/ping', headers={'x-request-id': bad_id})

    assert resp.status_code == 200
    assert resp.headers['x-request-id'] != bad_id
    assert len(resp.headers['x-request-id']) == 32


def test_access_log_fields_and_no_query_string(
    app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    with (
        caplog.at_level(logging.INFO, logger='llm_app.server.middleware'),
        TestClient(app) as client,
    ):
        client.get('/ping?token=super-secret', headers={'x-request-id': 'rid-test-123'})
    records = [r for r in caplog.records if r.name == 'llm_app.server.middleware']

    assert len(records) == 1
    record = cast(AccessLogRecord, records[0])

    assert record.request_id == 'rid-test-123'
    assert record.method == 'GET'
    assert record.path == '/ping'
    assert record.status_code == 200
    assert record.latency is not None
    assert 'super-secret' not in record.getMessage()


def test_middleware_overwrites_existing_request_id_header(app: FastAPI) -> None:
    client = TestClient(app)

    resp = client.get('/headers', headers={'x-request-id': 'rid-test-123'})
    request_id_list = resp.headers.get_list('x-request-id')

    assert request_id_list == ['rid-test-123']
    assert len(request_id_list) == 1


async def test_non_http_scope_is_passed_through() -> None:
    called: list[str] = []

    async def fake_app(scope, receive, send) -> None:
        called.append(scope['type'])

    async def receive() -> dict:
        return {'type': 'lifespan.startup'}

    async def send(message: dict) -> None:
        return None

    middleware = RequestContextMiddleware(fake_app)
    await middleware({'type': 'lifespan'}, receive, send)

    assert called == ['lifespan']
