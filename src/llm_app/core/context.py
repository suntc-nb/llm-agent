from contextvars import ContextVar, Token

_request_id: ContextVar[str] = ContextVar('request_id', default='-')


def get_request_id() -> str:
    """获取当前请求的 ID。

    Returns:
        当前上下文中的请求 ID；不在请求上下文中时返回 '-'。
    """
    return _request_id.get()


def set_request_id(value: str) -> Token[str]:
    """设置当前请求的 ID，并返回用于恢复的令牌。

    Args:
        value: 请求 ID，通常由中间件从 X-Request-ID 请求头读取或生成。

    Returns:
        Token[str]: 传给 reset_request_id 时用于恢复此前值的令牌。
    """
    return _request_id.set(value)


def reset_request_id(token: Token[str]) -> None:
    """将请求 ID 恢复到 set_request_id 调用之前的值。

    Args:
        token: set_request_id 返回的令牌。
    """
    _request_id.reset(token)
