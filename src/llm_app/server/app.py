from __future__ import annotations

import json
import logging
import threading
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Annotated

import httpx
from cachetools import TTLCache
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from llm_app.core.config import get_settings
from llm_app.core.database import get_db
from llm_app.models import models
from llm_app.schemas import schemas
from llm_app.server.auth import create_access_token, encode_pwd, get_current_user, verify_pwd
from llm_app.utils.common_class import CommonLlmApi
from llm_app.utils.common_function import TokenSlidingChatMemory

logger = logging.getLogger(__name__)
app = FastAPI(title='LLM Chat Server')


class LoginInfo(BaseModel):
    user_id: str
    user_name: str
    token: str


# 用户数据表映射,
user_map_id: dict[str, LoginInfo] = {}


# 常量定义
AUTH_FAILED_MSG_LOGIN = '用户名或密码错误'
AUTH_FAILED_MSG_REGISTER = '用户名已存在'
SESSION_NOT_EXISTS = '会话不存在'


@app.get('/api/health')
def health_check() -> dict:
    """服务健康检查。

    Returns:
        dict: 服务状态与当前时间。
    """
    return {
        'status': 'ok',
        'message': 'server is running!',
        'now': datetime.now(),
    }


@app.get('/api/test')
def test() -> dict:
    """测试用户token保存情况

    Returns:
        dict: user_id关联的token
    """
    return user_map_id


@app.get('/api/debug/users')
def debug_users(current_user: Annotated[dict, Depends(get_current_user)]):
    """测试token有效性"""
    # user = user_map_id.get(current_user['user_id'])
    return {'message': 'test is ok!'}


@app.post('/api/auth/register')
def register(userinfo: schemas.UserInfo, db: Annotated[Session, Depends(get_db)]):
    stmt = select(exists().where(models.UserInfo.user_name == userinfo.username))
    if db.scalar(stmt):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=AUTH_FAILED_MSG_REGISTER)
    hash_pwd = encode_pwd(userinfo.password)
    newuser = models.UserInfo(user_name=userinfo.username, user_hashed_pwd=hash_pwd)
    db.add(newuser)
    db.commit()
    db.refresh(newuser)
    return {'message': '用户注册成功'}


@app.post('/api/auth/login')
def login(
    userinfo: schemas.LoginRegister, db: Annotated[Session, Depends(get_db)]
) -> schemas.LoginResponse:
    """用户登录验证
    Args:
        reg_info (RegisterInfo): 登录请求信息对象
    Raises:
        HTTPException: 错误信息
    Returns:
        LoginResponse: 登录响应（包含access_token、用户ID、用户名）
    """
    stmt = select(models.UserInfo).where(models.UserInfo.user_name == userinfo.username)
    res_user = db.scalar(stmt)
    if not res_user or not verify_pwd(userinfo.password, hashed_pwd=res_user.user_hashed_pwd):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTH_FAILED_MSG_LOGIN)

    access_token = create_access_token(userinfo={'sub': res_user.user_id})
    # user.access_token = access_token
    user_logininfo = user_map_id.get(res_user.user_id)
    if user_logininfo:
        user_logininfo.token = access_token
    else:
        user_map_id.update(
            {
                res_user.user_id: LoginInfo(
                    user_id=res_user.user_id, user_name=userinfo.username, token=access_token
                )
            }
        )
    return schemas.LoginResponse(
        userid=res_user.user_id,
        username=res_user.user_name,
        token=access_token,
    )


@app.post('/api/session')
def creat_session(
    session_data: schemas.SessionCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> schemas.SessionResponse | None:
    new_session = models.ChatSession(
        user_id=current_user['user_id'], session_name=session_data.session_name
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return schemas.SessionResponse(
        session_id=new_session.session_id,
        session_name=new_session.session_name,
        user_id=new_session.user_id,
        created_at=new_session.created_at,
    )


@app.get('/api/sessions')
def list_sessions(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> list[schemas.SessionResponse]:
    stmt = select(models.ChatSession).where(models.ChatSession.user_id == current_user['user_id'])
    sessions = db.scalars(stmt).all()

    return [schemas.SessionResponse.model_validate(s) for s in sessions]


@app.delete('/api/sessions/{session_id}')
def delete_session(
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    stmt = select(models.ChatSession).where(
        models.ChatSession.user_id == current_user['user_id'],
        models.ChatSession.session_id == session_id,
    )
    session = db.scalar(stmt)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='会话不存在')
    db.delete(session)
    db.commit()
    return {
        'code': 0,
        'message': f'用户：{current_user["user_id"]}的会话：{session.session_name}已删除',
    }


# 内存缓存:session_id->TokenSlidingChatMemory
# session_memory: dict[str, TokenSlidingChatMemory] = {}
session_memory: TTLCache[str, TokenSlidingChatMemory] = TTLCache[str, TokenSlidingChatMemory](
    maxsize=100, ttl=7200
)

memory_lock = threading.Lock()


def _load_memory(session_id: str, db: Session) -> TokenSlidingChatMemory:
    """获取会话内存；不存在时从数据库历史重建。

    Args:
        session_id: 会话 ID。
        db: 数据库会话。

    Returns:
        TokenSlidingChatMemory: 该会话的内存对象。
    """
    memory = session_memory.get(session_id)
    if memory is not None:
        return memory
    with memory_lock:
        # 双重检查：等待锁期间可能已被其他请求创建
        memory = session_memory.get(session_id)
        if memory is not None:
            return memory
        stmt = (
            select(models.ChatMessage)
            .where(models.ChatMessage.session_id == session_id)
            .order_by(models.ChatMessage.created_at)
        )
        memory = TokenSlidingChatMemory(max_total_tokens=4000)
        for msg in db.scalars(stmt).all():
            memory.add_message(role=msg.role, content=msg.content)
        session_memory[session_id] = memory
    return memory


def _parse_sse_data(line: bytes) -> str | None:
    """解析一行 SSE，返回 data 字段内容；非 data 行返回 None。"""
    text = line.decode('utf-8')
    if not text.startswith('data: '):
        return None
    return text.removeprefix('data: ')


def _extract_content(data_str: str) -> str:
    """从 OpenAI 兼容的流式响应中提取增量文本。

    Raises:
        json.JSONDecodeError: 当该行不是合法 JSON 时。
    """
    data = json.loads(data_str)
    delta = data.get('choices', [{}])[0].get('delta', {})
    return delta.get('content', '')


def _save_assistant_message(
    db: Session, session_id: str, content: str, memory: TokenSlidingChatMemory
) -> None:
    """持久化 assistant 消息并同步内存，失败时回滚且不中断流。"""
    try:
        db.add(models.ChatMessage(session_id=session_id, role='assistant', content=content))
        db.commit()
        memory.add_message(role='assistant', content=content)
    except SQLAlchemyError:
        db.rollback()
        logger.exception('保存 assistant 消息失败, session_id=%s', session_id)


async def chat_stream_generator(
    session_id: str, user_content: str, db: Session, current_user: dict
) -> AsyncGenerator[str, None]:
    """流式返回 LLM 回复，并在结束时持久化。

    Args:
        session_id: 会话 ID。
        user_content: 用户本轮输入。
        db: 数据库会话。
        current_user: 当前登录用户信息。

    Yields:
        str: SSE 格式的事件数据。
    """
    db.add(models.ChatMessage(session_id=session_id, role='user', content=user_content))
    db.commit()

    memory = _load_memory(session_id, db)
    memory.add_message(role='user', content=user_content)

    llm = CommonLlmApi(get_settings(), temperature=0.7, top_p=0.9)
    response = llm.chat(memory.get_messages())

    assistant_content = ''
    try:
        for line in response.iter_lines():
            data_str = _parse_sse_data(line) if line else None
            if data_str is None:
                continue
            if data_str == '[DONE]':
                break
            try:
                content_chunk = _extract_content(data_str)
            except json.JSONDecodeError:
                continue
            if content_chunk:
                assistant_content += content_chunk
                yield f'data: {json.dumps({"content": content_chunk})}\n\n'
    finally:
        if assistant_content:
            _save_assistant_message(db, session_id, assistant_content, memory)
        response.close()

    yield f'data: {json.dumps({"done": True})}\n\n'


@app.post('/api/chat/stream')
def chat_stream(
    chat_request: schemas.ChatRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    stmt = select(models.ChatSession).where(
        models.ChatSession.session_id == chat_request.session_id,
        models.ChatSession.user_id == current_user['user_id'],
    )
    session = db.scalar(stmt)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SESSION_NOT_EXISTS)
    return StreamingResponse(
        chat_stream_generator(
            session_id=chat_request.session_id,
            user_content=chat_request.content,
            db=db,
            current_user=current_user,
        ),
        media_type='text/envent-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )
