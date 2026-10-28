"""API 层 Pydantic 基类：统一 snake_case 与 camelCase 的边界映射。"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class APIModel(BaseModel):
    """所有对外 Schema 的基类。

    Python 内部保持 snake_case；与前端交互的 JSON 契约统一使用 camelCase，
    由 alias_generator 在序列化/反序列化边界自动转换。

    Attributes:
        model_config: 启用 camelCase 别名；允许后端按 Python 字段名构造；
            拒绝未知字段，字段名错配时直接返回 422 而非静默忽略。
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra='forbid',
    )
