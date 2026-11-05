from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]


class DBSettings(BaseSettings):
    """数据库连接配置，环境变量统一使用 SQLITE_ 前缀。"""

    database_url: str = ''
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / '.env',
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

    log_level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] = 'INFO'
    log_format: Literal['text', 'json'] = 'text'
    log_file: str = ''
    log_max_bytes: int = 10 * 1024 * 1024
    log_backup_count: int = 5
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / '.env',
        extra='ignore',
        env_file_encoding='utf-8',
    )


class LLMSettings(BaseSettings):
    api_key: SecretStr
    zai_url: str
    model_name: str
    model_config = SettingsConfigDict(
        env_prefix='BIGMODEL_',
        env_file=ROOT_DIR / '.env',
        env_file_encoding='utf-8',
        extra='ignore',
    )


@lru_cache(maxsize=1)
def get_settings() -> LLMSettings:
    return LLMSettings()  # type: ignore
