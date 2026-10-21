from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

root_dir = Path(__file__).resolve().parents[3]


class DBSettings(BaseSettings):
    """数据库连接配置，环境变量统一使用 SQLITE_ 前缀。"""

    database_url: str = ''
    model_config = SettingsConfigDict(
        env_file=root_dir / '.env',
        extra='ignore',
        env_file_encoding='utf-8',
        env_prefix='SQLITE_',  # 环境变量统一前缀，如 APP_API_KEY
    )


class AppSettings(BaseSettings):
    """应用级通用配置。

    Attributes:
        log_level: 日志级别，取值 DEBUG/INFO/WARNING/ERROR，默认 INFO。
            为 DEBUG 时开启 SQLAlchemy 的 SQL 回显（echo）。
    """

    log_level: str = 'INFO'
    model_config = SettingsConfigDict(
        env_file=root_dir / '.env',
        extra='ignore',
        env_file_encoding='utf-8',
    )


class LLMSettings(BaseSettings):
    api_key: SecretStr
    zai_url: str
    model_name: str
    model_config = SettingsConfigDict(
        env_prefix='BIGMODEL_',
        env_file=root_dir / '.env',
        env_file_encoding='utf-8',
        extra='ignore',
    )


@lru_cache(maxsize=1)
def get_settings() -> LLMSettings:
    return LLMSettings()  # type: ignore
