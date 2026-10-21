from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class UserInfo(BaseModel):
    username: str
    password: str
    email: str = ''
    phone: str = ''


class LoginRegister(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    userid: str
    username: str
    token: str


class SessionCreate(BaseModel):
    session_name: str = '新会话'


class SessionResponse(BaseModel):
    session_id: str
    session_name: str
    user_id: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ChatMessageCreate(BaseModel):
    content: str


class ChatMessageResponse(BaseModel):
    message_id: str
    session_id: str
    role: Literal['system', 'user', 'assistant', 'tool', 'function'] = Field(
        description='消息角色类型'
    )
    content: str
    token_count: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ChatRequest(BaseModel):
    session_id: str
    content: str
