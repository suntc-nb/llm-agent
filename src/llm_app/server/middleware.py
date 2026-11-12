import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.datastructures import MutableHeaders

from llm_app.core.context import reset_request_id, set_request_id

logger = logging.getLogger(__name__)

_HEADER = b'x-request-id'
_VALID_ID = re.compile(r'^[A-Za-z0-9._-]{1,64}$')


class RequestContextMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        request_id = self._resolve_request_id(scope)
        # request_id存入scope['state']兜底冒泡异常传递
        scope.setdefault('state', {})['request_id'] = request_id
        # 替代写法添加多条信息
        # scope.setdefault('state', {}).update({'request_id': request_id})

        token = set_request_id(request_id)
        status_code = 500
        started = time.perf_counter()

        async def send_with_id(message):
            nonlocal status_code
            if message['type'] == 'http.response.start':
                status_code = message['status']
                headers = MutableHeaders(scope=message)
                headers['x-request-id'] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            latency = time.perf_counter() - started
            latency_ms = round(latency * 1000, 2)
            logger.info(
                '%s %s -> %d %.2fms',
                scope.get('method'),
                scope.get('path'),
                status_code,
                latency_ms,
                extra={
                    'request_id': request_id,
                    'method': scope.get('method'),
                    'path': scope.get('path'),
                    'status_code': status_code,
                    'latency': latency_ms,
                },
            )
            reset_request_id(token)

    @staticmethod
    def _resolve_request_id(scope) -> str:
        for k, v in scope['headers']:
            if k == _HEADER:
                rid = v.decode('latin-1')
                if _VALID_ID.fullmatch(rid):
                    return rid
        return uuid.uuid4().hex
