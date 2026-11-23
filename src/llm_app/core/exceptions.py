import logging
from collections.abc import Mapping
from typing import Any


class AppError(Exception):
    code: str = 'INTERNAL_ERROR'
    http_status: int = 500
    log_level: int = logging.ERROR
    default_message: str = '服务器内部错误'

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        internal_details: dict[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details = details  # 可公开给客户端
        self.internal_details = internal_details  # 只进日志,绝不返回
        self.headers = headers
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {'code': self.code, 'message': self.message}
        if self.details is not None:
            payload['details'] = self.details
        return payload

    def __str__(self) -> str:
        return self.message


class BadRequestError(AppError):
    code = 'BAD_REQUEST'
    http_status = 400
    log_level = logging.WARNING
    default_message = '请求参数不合法'


class AuthenticationError(AppError):
    code = 'UNAUTHORIZED'
    http_status = 401
    log_level = logging.WARNING
    default_message = '未认证或凭证无效'


class PermissionDeniedError(AppError):
    code = 'FORBIDDEN'
    http_status = 403
    log_level = logging.WARNING
    default_message = '没有访问权限'


class NotFoundError(AppError):
    code = 'NOT_FOUND'
    http_status = 404
    log_level = logging.WARNING
    default_message = '资源未找到'


class ConflictError(AppError):
    code = 'CONFLICT'
    http_status = 409
    log_level = logging.WARNING
    default_message = '资源冲突'


class ExternalServiceError(AppError):
    code = 'UPSTREAM_ERROR'
    http_status = 502
    log_level = logging.ERROR
    default_message = '外部服务错误'


class SessionNotFoundError(NotFoundError):
    code = 'SESSION_NOT_FOUND'
    default_message = '会话不存在'


class UserAlreadyExistsError(ConflictError):
    code = 'USER_ALREADY_EXISTS'
    default_message = '用户名已存在'


class InvalidCredentialsError(AuthenticationError):
    code = 'INVALID_CREDENTIALS'
    default_message = '用户名或密码错误'


class MissingCredentialsError(AuthenticationError):
    code = 'MISSING_CREDENTIALS'
    default_message = '缺少认证凭证'


class InvalidTokenError(AuthenticationError):
    code = 'INVALID_TOKEN'
    default_message = '无效的 Token'


class TokenExpiredError(AuthenticationError):
    code = 'TOKEN_EXPIRED'
    default_message = 'Token 已过期，请重新登录'
