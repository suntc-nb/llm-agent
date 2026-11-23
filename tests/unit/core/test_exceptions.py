import logging

import pytest

from llm_app.core.exceptions import (
    AppError,
    NotFoundError,
    SessionNotFoundError,
    UserAlreadyExistsError,
)


def test_app_error_defaults() -> None:
    err = AppError()
    assert err.code == 'INTERNAL_ERROR'
    assert err.http_status == 500
    assert err.log_level == logging.ERROR
    assert str(err) == '服务器内部错误'
    assert err.args == ('服务器内部错误',)


def test_message_details_headers_override() -> None:
    err = NotFoundError(
        '会话不存在', details={'session_id': '123'}, headers={'WWW-Authenticate': 'Bearer'}
    )
    assert err.message == '会话不存在'
    assert err.details == {'session_id': '123'}
    assert err.headers == {'WWW-Authenticate': 'Bearer'}
    assert err.to_dict() == {
        'code': 'NOT_FOUND',
        'message': '会话不存在',
        'details': {'session_id': '123'},
    }


@pytest.mark.parametrize(
    ('exc_cls', 'code', 'status', 'level'),
    [
        pytest.param(
            SessionNotFoundError,
            'SESSION_NOT_FOUND',
            404,
            logging.WARNING,
            id='SessionNotFoundError',
        ),
        pytest.param(
            UserAlreadyExistsError,
            'USER_ALREADY_EXISTS',
            409,
            logging.WARNING,
            id='UserAlreadyExistsError',
        ),
    ],
)
def test_domain_error_contract(
    exc_cls: type[AppError], code: str, status: int, level: int
) -> None:
    err = exc_cls()
    assert err.code == code
    assert err.http_status == status
    assert err.log_level == level


def test_damain_error_message_override() -> None:
    msg = '这个会话已被覆盖'
    err = SessionNotFoundError(msg)

    assert err.message == msg
    assert str(err) == msg
    assert err.code == 'SESSION_NOT_FOUND'
    assert err.to_dict()['message'] == msg


def test_to_dict_omits_details_when_none() -> None:
    """如果details为none,序列化时无details键"""
    err = SessionNotFoundError()
    payload = err.to_dict()

    assert payload == {'code': 'SESSION_NOT_FOUND', 'message': '会话不存在'}

    assert 'details' not in payload


def test_app_error_can_be_caught_as_base() -> None:
    """所有子类都能被基类统一捕获,便于全局处理器兜底"""
    with pytest.raises(AppError, match='会话不存在') as exc_info:
        raise SessionNotFoundError('会话不存在')
    caught = exc_info.value
    assert isinstance(caught, SessionNotFoundError)
    assert caught.code == 'SESSION_NOT_FOUND'
    assert caught.http_status == 404
    assert caught.log_level == logging.WARNING
