import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from llm_app.core.context import get_request_id
from llm_app.core.exceptions import AppError

logger = logging.getLogger(__name__)


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str,
    details: dict[str, Any] | list[Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    payload: dict[str, Any] = {
        'code': code,
        'message': message,
        'request_id': request_id,
        'timestamp': datetime.now(UTC).isoformat(),
    }
    if details is not None:
        payload['details'] = details
    response_headers = dict(headers or {})
    response_headers['X-Request-ID'] = request_id  # 最后写，保证不被覆盖

    return JSONResponse(
        status_code=status_code,
        content=payload,
        headers=response_headers,
    )


def _get_request_id(request: Request) -> str:
    return getattr(request.state, 'request_id', None) or get_request_id()


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    app_exc = cast(AppError, exc)
    request_id = _get_request_id(request=request)
    logger.log(
        app_exc.log_level,
        '%s',
        str(app_exc),
        extra={
            'request_id': request_id,
            'error_code': app_exc.code,
            'http_status': app_exc.http_status,
            'details': app_exc.details,
            'internal_details': app_exc.internal_details,
        },
        exc_info=app_exc if app_exc.log_level >= logging.ERROR else None,
    )
    return _error_response(
        status_code=app_exc.http_status,
        code=app_exc.code,
        message=app_exc.message,
        request_id=request_id,
        details=app_exc.details,
        headers=app_exc.headers,
    )


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    app_exc = cast(RequestValidationError, exc)
    request_id = _get_request_id(request=request)
    safe_error = [
        {
            'loc': err.get('loc'),
            'msg': err.get('msg'),
            'type': err.get('type'),
        }
        for err in app_exc.errors()
    ]
    logger.warning(
        '请求参数校验失败!',
        extra={'request_id': request_id, 'error_code': 'VALIDATION_ERROR', 'details': safe_error},
    )
    return _error_response(
        status_code=422,
        code='VALIDATION_ERROR',
        message='请求参数验证失败!',
        request_id=request_id,
        details=safe_error,
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """把 Starlette/FastAPI 的 HTTPException 转成统一错误响应。

    Args:
        request: 当前请求，处理函数签名要求，本函数未直接使用。
        exc: 框架或业务代码抛出的 HTTPException。

    Returns:
        JSONResponse: 统一格式的错误响应，保留原始响应头。
    """
    app_exc = cast(StarletteHTTPException, exc)
    request_id = _get_request_id(request=request)
    internal_details: Any = None
    # 5xx 不向客户端泄露内部细节
    if app_exc.status_code >= 500:
        message = '服务器内部错误'
        details = None
        internal_details = app_exc.detail
    elif isinstance(app_exc.detail, str):
        message = app_exc.detail
        details = None
    else:
        message = '请求失败'
        details = app_exc.detail

    log_level = logging.WARNING if app_exc.status_code < 500 else logging.ERROR
    logger.log(
        log_level,
        'HTTPException %s: %s',
        app_exc.status_code,
        message,
        extra={
            'request_id': request_id,
            'error_code': f'HTTP_{app_exc.status_code}',
            'http_status': app_exc.status_code,
            'details': details,  # 对外字段，5xx 为 None
            'internal_details': internal_details,  # 仅内部排障，5xx 时保留原始 detail
        },
        exc_info=app_exc if log_level >= logging.ERROR else False,
    )

    return _error_response(
        status_code=app_exc.status_code,
        code=f'HTTP_{app_exc.status_code}',
        message=message,
        request_id=request_id,
        details=details,
        headers=app_exc.headers,  # 可能是 None，辅助函数里用 dict(headers or {}) 兜底
    )


async def sqlalchemy_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    db_exc = cast(SQLAlchemyError, exc)
    request_id = _get_request_id(request)
    logger.log(
        logging.ERROR,
        '数据库操作失败:%s',
        type(db_exc).__name__,
        exc_info=db_exc,
        extra={
            'request_id': request_id,
            'error_code': 'DATABASE_ERROR',  # 或 DATABASE_ERROR
            'exception_type': type(exc).__name__,
        },
    )
    return _error_response(
        status_code=500,
        code='DATABASE_ERROR',
        message='服务器内部错误',
        request_id=request_id,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = _get_request_id(request)
    logger.log(
        logging.ERROR,
        '未处理异常:%s',
        type(exc).__name__,
        exc_info=exc,
        extra={
            'request_id': request_id,
            'error_code': 'INTERNAL_ERROR',  # 或 DATABASE_ERROR
            'exception_type': type(exc).__name__,
        },
    )
    return _error_response(
        status_code=500, code='INTERNAL_ERROR', message='服务器内部错误', request_id=request_id
    )
