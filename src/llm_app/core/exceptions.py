import logging
from typing import Any


class AppError(Exception):
    code: str = 'INTERNAL_ERROR'
    http_status: int = 500
    log_level: int = logging.ERROR
    default_message: str = '服务器内部错误'

    def __init__(
        self, message: str | None = None, *, details: dict[str, Any] | None = None
    ) -> None:
        self.message = message or self.default_message
        self.details = details
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

