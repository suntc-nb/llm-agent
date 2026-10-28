from collections import deque
from functools import lru_cache
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from transformers import PreTrainedTokenizerBase

# TOKENIZER_NAME = 'BAAI/bge-m3'
# tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_NAME)

__all__ = ['DEFAULT_TOKENIZER_MODEL', 'TokenSlidingChatMemory', 'warm_up_tokenizer']

DEFAULT_TOKENIZER_MODEL = 'BAAI/bge-m3'


@lru_cache(maxsize=4)
def _load_tokenizer(model_name: str) -> 'PreTrainedTokenizerBase':
    """加载并缓存 tokenizer。

    ``transformers`` 顶层导入会连带加载 ``torch``，耗时可达十余秒。
    若放在模块顶层，uvicorn 每次热重载重启进程都会重复付出该开销，
    因此延迟到首次实际需要分词时才导入，并按模型名缓存复用实例。

    Args:
        model_name: HuggingFace 模型名或本地路径。

    Returns:
        PreTrainedTokenizerBase: 已加载的 tokenizer 实例。
    """
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(model_name)


def warm_up_tokenizer(model_name: str = DEFAULT_TOKENIZER_MODEL) -> None:
    """预热 tokenizer，把导入与加载开销前移到服务启动阶段。

    Args:
        model_name: HuggingFace 模型名或本地路径。

    Returns:
        None
    """
    _load_tokenizer(model_name)


class MessageItem(BaseModel):
    role: Literal['system', 'user', 'assistant', 'tool', 'function'] = Field(
        description='消息角色类型'
    )
    content: str = Field(description='消息内容')
    token_count: int = Field(description='当前信息的token数量')


class TokenSlidingChatMemory:
    def __init__(
        self,
        max_total_tokens: int,
        model_name: str = DEFAULT_TOKENIZER_MODEL,
        system_prompt: str | None = None,
    ):
        self.max_total_tokens = max_total_tokens
        self.model_name = model_name
        self.enc = _load_tokenizer(model_name)

        # 系统提示词，永久保留，不参与滑动淘汰
        self.system_msg: MessageItem | None = None
        if system_prompt is not None:
            sys_token = len(
                self.enc.encode(
                    system_prompt,
                    add_special_tokens=True,
                )
            )
            self.system_msg = MessageItem(
                role='system', content=system_prompt, token_count=sys_token
            )

        # deque 存放 user / assistant 对话历史，滑动窗口主体
        self.history: deque[MessageItem] = deque()

    def _count_text_token(self, text: str) -> int:
        """计算一段文本的token数量"""
        return len(
            self.enc.encode(
                text,
                add_special_tokens=True,
            )
        )

    @property
    def current_total_tokens(self) -> int:
        """当前全部上下文总token（系统词+历史消息）"""
        total = self.system_msg.token_count if self.system_msg else 0
        for item in self.history:
            total += item.token_count
        return total

    def add_message(self, role: str, content: str):
        """新增对话消息，自动触发滑动裁剪，淘汰最旧消息"""
        if role == 'system':
            raise ValueError('系统提示词请在初始化时设置，不支持add_message添加system')

        msg_token = self._count_text_token(content)
        new_item = MessageItem(role=role, content=content, token_count=msg_token) # type: ignore
        self.history.append(new_item)

        # 滑动窗口裁剪：总token超标，持续弹出最左侧（最早）消息
        while self.current_total_tokens > self.max_total_tokens and len(self.history) > 0:
            removed = self.history.popleft()
            print(f'[窗口裁剪] 丢弃历史消息 | role:{removed.role}, token:{removed.token_count}')

    def get_messages(self) -> list[dict[str, str]]:
        """输出可直接传给OpenAI ChatCompletion的messages列表"""
        out = []
        if self.system_msg:
            out.append(self.system_msg.model_dump(include={'role', 'content'}))
        for item in self.history:
            out.append(item.model_dump(include={'role', 'content'}))
        return out

    def clear_history(self):
        """清空对话历史，保留系统提示词"""
        self.history.clear()
