import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from llm_app.core.config import AppSettings, DBSettings

db_settings = DBSettings()
app_settings = AppSettings()

# as_posix() 保证 Windows 下得到正斜杠路径，避免 sqlite:///D:\... 形式的 URL。
_SQLITE_DB_PATH = Path(__file__).resolve().parents[3] / db_settings.database_url
SQLITE_DATABASE_URL = f'sqlite:///{_SQLITE_DB_PATH.as_posix()}'

# 仅在 LOG_LEVEL=DEBUG 时回显 SQL，避免生产/迁移时刷屏。
_ECHO_SQL = app_settings.log_level.upper() == 'DEBUG'

engine = create_engine(
    url=SQLITE_DATABASE_URL, connect_args={'check_same_thread': False}, echo=_ECHO_SQL
)


@event.listens_for(engine, 'connect')
def _enable_sqlite_foreign_keys(
    dbapi_connection: sqlite3.Connection, _connection_record: object
) -> None:
    """为每个新连接开启 SQLite 外键约束。

    SQLite 默认关闭外键检查，不显式开启时 ForeignKey 声明不会生效。
    """
    cursor = dbapi_connection.cursor()
    cursor.execute('PRAGMA foreign_keys=ON')
    cursor.close()


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    FastAPI 依赖注入函数：为每个请求创建独立的数据库会话。

    使用 yield 实现上下文管理器模式：
    - yield 前：创建数据库会话并返回给路由函数
    - yield 后：无论请求成功或异常，finally 块都会执行，确保会话被正确关闭
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
