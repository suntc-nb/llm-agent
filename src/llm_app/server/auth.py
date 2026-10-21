import os
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from dotenv import find_dotenv, load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from pydantic import BaseModel, Field

_ = load_dotenv(find_dotenv())


class JwtConfigInfo(BaseModel):
    secert_key: str = Field(description='加密密钥')
    algorithm: str = Field(description='加密算法')
    token_expire_time: int = Field(description='令牌有效时间,单位:分钟')


class UserInfo(BaseModel):
    user_id: str = Field(description='用户id')


JWT_SECRET_KEY = os.getenv('SECRET_KEY', '')
JWT_ALGORITHM = os.getenv('ALGORITHM', '')
JWT_TOKEN_EXPIRE_TIME = os.getenv('TOKEN_EXPIRE_TIME', '')

jwt_config_info = JwtConfigInfo(
    secert_key=JWT_SECRET_KEY,
    algorithm=JWT_ALGORITHM,
    token_expire_time=int(JWT_TOKEN_EXPIRE_TIME),
)

# print(jwt_config_info.model_dump())

pwd_context = PasswordHash.recommended()


def encode_pwd(password: str) -> str:
    """密码hash加密

    Args:
        password (str): 用户的明文密码

    Returns:
        str: 加密后的密文
    """
    return pwd_context.hash(password)


def verify_pwd(plain_pwd: str, hashed_pwd: str) -> bool:
    """验证用户密码

    Args:
        plain_pwd (str): 明文密码
        hashed_pwd (str): 密文密码

    Returns:
        bool: 登录结果,ture or false
    """
    return pwd_context.verify(plain_pwd, hashed_pwd)


def create_access_token(userinfo: dict, expire_delta: timedelta | None = None) -> str:
    encode_content = userinfo.copy()
    expire_time = datetime.now(UTC) + (
        expire_delta or timedelta(minutes=jwt_config_info.token_expire_time)
    )
    encode_content.update({'exp': expire_time})
    return jwt.encode(
        payload=encode_content, key=jwt_config_info.secert_key, algorithm=jwt_config_info.algorithm
    )


security = HTTPBearer()


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> dict:
    try:
        payload = jwt.decode(
            credentials.credentials,
            jwt_config_info.secert_key,
            algorithms=[jwt_config_info.algorithm],
        )
        user_id: str = payload.get('sub')  # pyright: ignore[reportAssignmentType]
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='无效的 token',
                headers={'WWW-Authenticate': 'Bearer'},
            )
        return {'user_id': user_id}
    except jwt.ExpiredSignatureError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Token已过期,请重新登录',
            headers={'WWW-Authenticate': 'Bearer'},
        ) from err
    except jwt.InvalidTokenError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='无效的 Token',
            headers={'WWW-Authenticate': 'Bearer'},
        ) from err
