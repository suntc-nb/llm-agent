import json

import pytest

from llm_app.utils.sse import encode_event, extract_content, parse_data_line


def test_encode_event_wire_format() -> None:
    event = 'token'
    data = {'content': '测试输出结果'}

    text = encode_event(event, data=data)

    assert text == 'event: token\ndata: {"content": "测试输出结果"}\n\n'
    assert text.endswith('\n\n')


def test_parse_data_line_with_and_without_space() -> None:
    line_1 = 'data: {"content":"hello"}'
    line_2 = 'data:{"content":"hello"}'
    line_3 = 'event:token'

    assert parse_data_line(line_1) == '{"content":"hello"}'
    assert parse_data_line(line_2) == '{"content":"hello"}'
    assert parse_data_line(line_3) is None


def test_extract_content() -> None:
    data_str = '{"choices":[{"delta":{"content":"h"}}]}'

    assert extract_content(data_str=data_str) == 'h'


def test_extract_content_missing_delta_returns_empty() -> None:
    data_str = '{"choices":[{}]}'
    assert extract_content(data_str) == ''
    assert extract_content('{}') == ''


def test_extract_content_invalid_json_raises() -> None:
    with pytest.raises(json.JSONDecodeError) as exc_info:
        extract_content('not json')

    assert exc_info.type is json.JSONDecodeError
    assert 'Expecting value' in str(exc_info.value)
    assert exc_info.value.pos == 0
