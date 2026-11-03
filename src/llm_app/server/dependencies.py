from __future__ import annotations

import httpx
from fastapi import Request

__all__ = ['get_http_client']


def get_http_client(request: Request) -> httpx.AsyncClient:
    """取出 lifespan 中创建的共享 HTTP 客户端。

    Args:
        request: 当前请求对象，用于访问应用实例状态。

    Returns:
        httpx.AsyncClient: 应用级共享客户端。
    """
    return request.app.state.http_client
