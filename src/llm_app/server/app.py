from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated

import httpx
from cachetools import TTLCache
from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from llm_app.core.config import get_settings
from llm_app.core.context import get_request_id
from llm_app.core.database import get_db
from llm_app.core.exceptions import (
    AppError,
    ExternalServiceError,
    InvalidCredentialsError,
    SessionNotFoundError,
    UserAlreadyExistsError,
)
from llm_app.core.logging import setup_logging
from llm_app.models import models
from llm_app.schemas import schemas
from llm_app.server.auth import create_access_token, encode_pwd, get_current_user, verify_pwd
from llm_app.server.dependencies import get_http_client
from llm_app.server.exception_handlers import (
    app_error_handler,
    http_exception_handler,
    sqlalchemy_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from llm_app.server.middleware import RequestContextMiddleware
from llm_app.utils.common_class import CommonLlmApi
from llm_app.utils.common_function import TokenSlidingChatMemory, warm_up_tokenizer
from llm_app.utils.sse import encode_event, extract_content, parse_data_line

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """管理应用级共享资源：共享 HTTP 客户端与 tokenizer 预热。

    AsyncClient 内部的连接池和异步原语会绑定到创建它的事件循环，
    因此必须在 lifespan 内创建/关闭，不能放在模块顶层。

    Args:
        app: FastAPI 应用实例，共享资源挂载到 app.state。

    Yields:
        None: 应用运行期间的控制权。
    """
    # 日志入口
    setup_logging()
    # 超时按用途拆开：建连要快速失败，流式读取要允许模型长时间思考。
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        # 流式场景关闭压缩协商，避免压缩缓冲吞掉增量内容
        headers={'Accept-Encoding': 'identity'},
    )
    try:
        try:
            # 同步加载会阻塞事件循环，放到线程池执行；此时尚未开始接收请求。
            await asyncio.to_thread(warm_up_tokenizer)
        except (OSError, ValueError):
            # 预热失败不应阻止服务启动，首个对话请求会重新尝试并暴露真实错误。
            logger.warning('tokenizer 预热失败', exc_info=True)

        yield
    finally:
        # 在同一个事件循环内关闭，释放连接池中的 keep-alive 连接
        await app.state.http_client.aclose()


app = FastAPI(title='LLM Chat Server', lifespan=lifespan, docs_url=None)
# 注册中间件,处理logger
app.add_middleware(RequestContextMiddleware)
# 注册异常处理handlers
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# 挂载静态页面
static_dir = Path(__file__).parent.parent / 'static'
app.mount('/static', StaticFiles(directory=str(static_dir), html=True), name='static')

# 内存缓存:session_id->TokenSlidingChatMemory
# session_memory: dict[str, TokenSlidingChatMemory] = {}
session_memory: TTLCache[str, TokenSlidingChatMemory] = TTLCache[str, TokenSlidingChatMemory](
    maxsize=100, ttl=7200
)

memory_lock = threading.Lock()


@app.get('/docs', include_in_schema=False)
def custom_swagger_ui() -> HTMLResponse:
    """使用本地静态资源渲染 Swagger UI。

    默认页面依赖 jsdelivr CDN，国内网络常无法访问导致白屏。
    这里改为加载 ``static/swagger`` 下的本地文件，完全离线可用。

    Returns:
        HTMLResponse: Swagger UI 页面。
    """
    return get_swagger_ui_html(
        openapi_url=app.openapi_url or '/openapi.json',
        title=f'{app.title} - Swagger UI',
        swagger_js_url='/static/swagger/swagger-ui-bundle.js',
        swagger_css_url='/static/swagger/swagger-ui.css',
    )


class LoginInfo(BaseModel):
    user_id: str
    user_name: str
    token: str


# 用户数据表映射,
user_map_id: dict[str, LoginInfo] = {}


# 常量定义


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


@app.get('/api/debug/users')
def debug_users(current_user: Annotated[dict, Depends(get_current_user)]):
    """测试token有效性"""
    # user = user_map_id.get(current_user['user_id'])
    return {'message': 'test is ok!'}


@app.post('/api/auth/register')
def register(userinfo: schemas.UserInfo, db: Annotated[Session, Depends(get_db)]):
    stmt = select(exists().where(models.UserInfo.user_name == userinfo.username))
    if db.scalar(stmt):
        raise UserAlreadyExistsError()
    hash_pwd = encode_pwd(userinfo.password)
    newuser = models.UserInfo(user_name=userinfo.username, user_hashed_pwd=hash_pwd)
    db.add(newuser)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if 'user_name' in str(exc.orig):
            raise UserAlreadyExistsError() from exc
        raise
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
        raise InvalidCredentialsError(headers={'WWW-Authenticate': 'Bearer'})

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
        user_id=res_user.user_id,
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
        raise SessionNotFoundError()
    # commit 后实例会过期，删除前先取出名称，避免 ObjectDeletedError
    session_name = session.session_name

    # chat_messages 外键已配置 ON DELETE CASCADE，子表消息由数据库级联删除
    db.delete(session)
    db.commit()

    session_memory.pop(session_id, None)
    return {
        'code': 0,
        'message': f'用户：{current_user["user_id"]}的会话：{session_name}已删除',
    }


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


def _save_assistant_message(
    db: Session,
    session_id: str,
    content: str,
) -> bool:
    """持久化 assistant 消息并同步内存，失败时回滚且不中断流。"""
    try:
        db.add(models.ChatMessage(session_id=session_id, role='assistant', content=content))
        db.commit()
        # memory.add_message(role='assistant', content=content)
        return True
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error(
            '保存 assistant 消息失败, session_id=%s',
            session_id,
            exc_info=exc,
            extra={
                'error_code': 'ASSISTANT_MESSAGE_SAVE_FAILED',
                'exception_type': type(exc).__name__,
                'session_id': session_id,
            },
        )
        return False


async def chat_stream_generator(
    client: httpx.AsyncClient,
    session_id: str,
    db: Session,
    memory: TokenSlidingChatMemory,
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
    # 转移到sse外执行由全局处理处理异常
    # db.add(models.ChatMessage(session_id=session_id, role='user', content=user_content))
    # db.commit()

    # memory = _load_memory(session_id, db)
    # memory.add_message(role='user', content=user_content)

    llm = CommonLlmApi(get_settings(), temperature=0.7, top_p=0.9)

    assistant_content = ''
    try:
        async for line in llm.astream_chat(client, memory.get_messages()):
            data_str = parse_data_line(line) if line else None
            if data_str is None:
                continue
            if data_str == '[DONE]':
                break
            try:
                content_chunk = extract_content(data_str)
            except json.JSONDecodeError:
                continue
            if content_chunk:
                assistant_content += content_chunk
                yield encode_event('token', {'content': content_chunk})
    except ExternalServiceError as exc:
        request_id = get_request_id()
        upstream_status = (exc.details or {}).get('upstream_status')
        upstream_body = (exc.internal_details or {}).get('upstream_body', '')
        logger.error(
            'LLM 流式对话失败, session_id=%s, upstream_status=%s, upstream_body=%s',
            session_id,
            upstream_status,
            upstream_body,
            exc_info=exc,
            extra={
                'request_id': request_id,
                'error_code': 'LLM_STREAM_FAILED',
                'exception_type': type(exc).__name__,
                'session_id': session_id,
                'upstream_status': upstream_status,
                'upstream_body': upstream_body,
            },
        )
        # 响应头已经发出，全局处理器无法再改状态码，只能用 SSE 事件通知客户端

        yield encode_event(
            'app_err',
            {
                'error': 'LLM 服务暂时不可用，请稍后重试',
                'request_id': request_id,
            },
        )
    finally:
        if assistant_content:
            save_status = await asyncio.to_thread(
                _save_assistant_message, db, session_id, assistant_content
            )
            if save_status:
                memory.add_message(role='assistant', content=assistant_content)
            else:
                logger.error(
                    'assistant 消息保存失败!,session_id%s',
                    session_id,
                    extra={
                        'request_id': get_request_id(),
                        'error_code': 'ASSISTANT_MESSAGE_SAVE_FAILED',
                        'session_id': session_id,
                    },
                )
        # response.close()

    yield encode_event('done', {})


@app.post('/api/chat/stream')
def chat_stream(
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
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
        raise SessionNotFoundError()

    # 阶段一,数据库操作走全局处理器,返回标准的JSON错误
    db.add(
        models.ChatMessage(
            session_id=chat_request.session_id, role='user', content=chat_request.content
        )
    )
    db.commit()

    memory = _load_memory(chat_request.session_id, db)
    memory.add_message(role='user', content=chat_request.content)
    # 阶段二,只做流式响应
    return StreamingResponse(
        chat_stream_generator(
            client=client,
            session_id=chat_request.session_id,
            db=db,
            memory=memory,
        ),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )


@app.get('/api/sessions/{session_id}/messages')
def list_messages(
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> list[schemas.ChatMessageResponse]:
    stmt = select(
        exists().where(
            models.ChatSession.session_id == session_id,
            models.ChatSession.user_id == current_user['user_id'],
        )
    )
    if not db.scalar(stmt):
        raise SessionNotFoundError('会话不存在或无权访问')

    stmt = (
        select(models.ChatMessage)
        .where(models.ChatMessage.session_id == session_id)
        .order_by(models.ChatMessage.created_at)
    )
    return [schemas.ChatMessageResponse.model_validate(m) for m in db.scalars(stmt).all()]
