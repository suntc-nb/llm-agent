import logging
import re

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from llm_app.server.middleware import RequestContextMiddleware

HEX32 = re.compile(r'^[0-9a-f]{32}$')


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


def test_valid_requese_id_is_passed_through(app: FastAPI) -> None:
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
