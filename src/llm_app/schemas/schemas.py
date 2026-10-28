from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field

from llm_app.schemas.base import APIModel


class UserInfo(APIModel):
    username: str
    password: str
    email: str = ''
    phone: str = ''


class LoginRegister(APIModel):
    username: str
    password: str


class LoginResponse(APIModel):
    user_id: str
    username: str
    token: str


class SessionCreate(APIModel):
    session_name: str = '新会话'


class SessionResponse(APIModel):
    session_id: str
    session_name: str
    user_id: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ChatMessageCreate(APIModel):
    content: str


class ChatMessageResponse(APIModel):
    message_id: str
    session_id: str
    role: Literal['system', 'user', 'assistant', 'tool', 'function'] = Field(
        description='消息角色类型'
    )
    content: str
    token_count: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ChatRequest(APIModel):
    session_id: str
    content: str
