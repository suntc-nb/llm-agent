import logging
from datetime import datetime

# from typing import Any, Protocol, cast
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from llm_app.core.exceptions import AppError, NotFoundError
from llm_app.server.exception_handlers import (
    app_error_handler,
    http_exception_handler,
    sqlalchemy_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from llm_app.server.middleware import RequestContextMiddleware


class Payload(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=8)


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # 下面是测试专用的"故障路由"
    @app.get('/app-error')
    def app_error() -> None:
        raise NotFoundError(
            '会话不存在',
            details={'session_id': 'abc'},
            headers={'X-Test': '1'},
        )

    @app.post('/validation')
    def validation(payload: Payload) -> dict[str, bool]:
        return {'ok': True}

    @app.get('/http-401')
    def http_401() -> None:
        raise HTTPException(401, detail='未认证', headers={'WWW-Authenticate': 'Bearer'})

    @app.get('/http-500')
    def http_500() -> None:
        raise HTTPException(500, detail='内部秘密，不能给客户端看')

    @app.get('/db-error')
    def db_error() -> None:
        raise SQLAlchemyError('password=supersecret')

    @app.get('/boom')
    def boom() -> None:
        raise RuntimeError('password=supersecret')

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    # 关键：不让 TestClient 把服务端异常直接抛出来，我们要看 500 响应体
    return TestClient(app, raise_server_exceptions=False)


def test_app_error_contract(client: TestClient) -> None:
    resp = client.get('/app-error', headers={'X-Request-ID': 'rid-test-110'})
    body = resp.json()

    # TODO: 断言 status=404 / code=NOT_FOUND / message / details
    # TODO: 断言 body['request_id'] 和响应头一致
    # TODO: 断言自定义响应头 X-Test 被保留
    # TODO: datetime.fromisoformat(body['timestamp']) 不抛异常

    assert resp.status_code == 404
    assert body['code'] == 'NOT_FOUND'
    assert body['message'] == '会话不存在'
    assert body['details'] == {'session_id': 'abc'}

    assert body['request_id'] == 'rid-test-110'

    assert resp.headers['X-TEST'] == '1'


def test_app_error_logs_warning_without_stack(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger='llm_app.server.exception_handlers'):
        client.get('/app-error')

    # TODO: 取出 exception_handlers 的日志记录
    # TODO: 断言 levelno == logging.WARNING
    # TODO: 断言 exc_info is None
    # TODO: 断言 record.error_code == 'NOT_FOUND'
    record: logging.LogRecord | None = next(
        (r for r in caplog.records if r.name == 'llm_app.server.exception_handlers'), None
    )
    # print(record.__dict__)
    assert record is not None
    assert record.levelno == logging.WARNING
    assert record.exc_info is None
    assert record.error_code == 'NOT_FOUND'  # pyright: ignore[reportAttributeAccessIssue]


def test_http_exception_preserves_headers(client: TestClient) -> None:
    resp = client.get('/http-401')
    body = resp.json()
    # print(body)
    assert resp.status_code == 401
    assert body['code'] == 'HTTP_401'
    assert resp.headers['WWW-Authenticate'] == 'Bearer'


def test_http_500_hides_internal_detail(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    # TODO: 500 / code == 'HTTP_500' / message == '服务器内部错误'
    # TODO: 断言 '内部秘密' 不在 resp.text 里
    resp = client.get('/http-500')
    body = resp.json()
    caplog.set_level(logging.WARNING, logger='llm_app.server.exception_handlers')
    records = [r for r in caplog.records if r.name == 'llm_app.server.exception_handlers']

    # print(resp.text)
    assert resp.status_code == 500
    assert body['code'] == 'HTTP_500'
    assert body['message'] == '服务器内部错误'
    assert '内部秘密' not in resp.text

    assert records, '未捕获到 http_exception_handler 的日志'
    assert getattr(records[0], 'internal_details', None) == '内部秘密，不能给客户端看'


def test_validation_error_sanitizes_input(client: TestClient) -> None:
    resp = client.post('/validation', json={'username': '', 'password': 'secret'})
    body = resp.json()
    # print(body)
    # TODO: 422 / code == 'VALIDATION_ERROR'
    # TODO: 每条 details 的键集合严格等于 {'loc', 'msg', 'type'}
    # TODO: 断言 'secret' 不在 resp.text 里

    assert resp.status_code == 422
    assert body['code'] == 'VALIDATION_ERROR'

    details = body['details']
    assert set(details[0].keys()) == {'loc', 'msg', 'type'}
    for item in details:
        assert set(item.keys()) == {'loc', 'msg', 'type'}

    # assert all(set(item.keys()) == {'loc', 'msg', 'type'} for item in details)

    assert 'secret' not in resp.text


def test_sqlalchemy_error_hides_internal_message(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger='llm_app.server.exception_handlers'):
        resp = client.get('/db-error')
        body = resp.json()
        records = [r for r in caplog.records if r.name == 'llm_app.server.exception_handlers']

    # TODO: 500 / code == 'DATABASE_ERROR'
    # TODO: 'supersecret' 不在 resp.text 里
    # TODO: 日志 levelno == ERROR 且 exc_info is not None

    assert resp.status_code == 500
    assert body['code'] == 'DATABASE_ERROR'
    assert 'supersecret' not in resp.text
    assert getattr(records[0], 'levelno', None) == logging.ERROR
    assert getattr(records[0], 'exc_info', None) is not None


def test_unhandled_exception_hides_internal_message(client: TestClient) -> None:
    resp = client.get('/boom', headers={'X-Request-ID': 'rid-boom'})
    body = resp.json()

    # TODO: 500 / code == 'INTERNAL_ERROR'
    # TODO: 'supersecret' 不在 resp.text 里
    # TODO: body['request_id'] == 'rid-boom'
    # TODO: resp.headers['x-request-id'] == 'rid-boom'
    assert resp.status_code == 500
    assert body['code'] == 'INTERNAL_ERROR'
    assert 'supersecret' not in resp.text
    assert body['request_id'] == 'rid-boom'
    assert resp.headers['x-request-id'] == 'rid-boom'
