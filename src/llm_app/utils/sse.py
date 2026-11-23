"""SSE 编解码工具，不依赖任何 Web 框架。"""

import json
from typing import Any


def encode_event(event: str, data: dict[str, Any]) -> str:
    """把一条 SSE 事件编码成 wire format。"""
    return f'event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'


def parse_data_line(line: str) -> str | None:
    """解析一行 data 字段；非 data 行返回 None。"""
    if not line.startswith('data:'):
        return None
    return line.removeprefix('data:').removeprefix(' ')


def extract_content(data_str: str) -> str:
    """从 OpenAI 兼容的 delta JSON 中提取增量文本。

    Raises:
        json.JSONDecodeError: 当该行不是合法 JSON 时。
    """
    data = json.loads(data_str)
    delta = data.get('choices', [{}])[0].get('delta', {})
    return delta.get('content', '')
