from typing import Literal

import requests
from pydantic import BaseModel, Field

from llm_app.core.config import LLMSettings

__all__ = ['CommonLlmApi', 'LLMConfig']


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
        timeout: float = 60,
        stream: bool = True,
    ) -> None:
        self.llmconfig = llmconfig
        self.temperature = temperature
        self.top_p = top_p
        self.timeout = timeout
        self.stream = stream

    def chat(self, msessages: list[dict[str, str]]):
        headers = {
            'Authorization': f'Bearer {self.llmconfig.api_key.get_secret_value()}',
            'Content-Type': 'application/json',
        }
        payload = {
            'model': self.llmconfig.model_name,
            'messages': msessages,
            'temperature': self.temperature,
            'top_p': self.top_p,
            'stream': self.stream,
            'timeout': self.timeout,
        }
        results = requests.post(
            url=self.llmconfig.zai_url, headers=headers, json=payload, stream=True
        )
        return results
