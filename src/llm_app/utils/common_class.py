import logging
from collections.abc import AsyncIterator
from typing import Literal

import httpx
import requests
from pydantic import BaseModel, Field

from llm_app.core.config import LLMSettings
from llm_app.core.exceptions import ExternalServiceError

__all__ = ['CommonLlmApi', 'LLMConfig']
logger = logging.getLogger(__name__)


class LLMConfig(BaseModel):
    api_key: str
    base_url: str
    model_name: str


class MessagesChat(BaseModel):
    role: Literal['system', 'user', 'assistant', 'tool', 'function'] = Field(
        description='消息角色类型'
    )
    content: str = Field(description='消息内容')


class CommonLlmApi:
    def __init__(
        self,
        llmconfig: LLMSettings,
        temperature: float = 0.0,
        top_p: float = 0.0,
        timeout: float = 120,
        stream: bool = True,
    ) -> None:
        self.llmconfig = llmconfig
        self.temperature = temperature
        self.top_p = top_p
        self.timeout = timeout
        self.stream = stream

    def _build_headers(self) -> dict[str, str]:
        return {
            'Authorization': f'Bearer {self.llmconfig.api_key.get_secret_value()}',
            'Content-Type': 'application/json',
        }

    def _build_payload(self, messages: list[dict[str, str]], *, stream: bool = True) -> dict:
        return {
            'model': self.llmconfig.model_name,
            'messages': messages,
            'temperature': self.temperature,
            'top_p': self.top_p,
            'stream': stream,
        }

    def chat(self, messages: list[dict[str, str]]):
        headers = {
            'Authorization': f'Bearer {self.llmconfig.api_key.get_secret_value()}',
            'Content-Type': 'application/json',
        }
        payload = {
            'model': self.llmconfig.model_name,
            'messages': messages,
            'temperature': self.temperature,
            'top_p': self.top_p,
            'stream': self.stream,
            #'timeout': self.timeout,
        }
        results = requests.post(
            url=self.llmconfig.zai_url,
            headers=headers,
            json=payload,
            stream=True,
            timeout=self.timeout,
        )
        # 流式响应必须先校验状态码，否则 4xx/5xx 的错误 JSON 会被当成 SSE 流解析
        try:
            results.raise_for_status()
        except requests.HTTPError as exc:
            detail = results.text[:300]
            results.close()
            raise requests.HTTPError(f'{exc} | body: {detail}', response=results) from exc
        return results

    async def astream_chat(
        self, client: httpx.AsyncClient, messages: list[dict[str, str]]
    ) -> AsyncIterator[str]:
        headers = self._build_headers()
        payload = self._build_payload(messages=messages)
        try:
            async with client.stream(
                'POST',
                url=self.llmconfig.zai_url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            ) as resp:
                if resp.status_code >= 400:
                    err_body = await resp.aread()
                    body_text = err_body.decode('utf-8', errors='replace')
                    safe_body = body_text.replace('\n', ' ').replace('\r', ' ')[:500]

                    # 上游原始响应只进内部日志，不能放进异常 message 返回给客户端
                    """ logger.error(
                        '上游 LLM 返回 HTTP %s: %s',
                        resp.status_code,
                        body_text[:500],
                    ) """
                    raise ExternalServiceError(
                        '上游服务返回错误',
                        details={'upstream_status': resp.status_code},
                        internal_details={'upstream_body': safe_body},
                    )

                async for chunk in resp.aiter_lines():
                    yield chunk
        except httpx.TimeoutException as exc:
            raise ExternalServiceError('上游服务请求超时') from exc
        except httpx.RequestError as exc:
            # RequestError 是 TransportError/TimeoutException 的父类，
            # 这一条兜住 DNS、连接拒绝、SSL、断流等所有传输异常
            raise ExternalServiceError('上游服务连接失败') from exc
