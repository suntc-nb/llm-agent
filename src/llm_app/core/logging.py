import json
import logging
import logging.config
from pathlib import Path

from llm_app.core.config import ROOT_DIR, AppSettings
from llm_app.core.context import get_request_id, reset_request_id, set_request_id

logger = logging.getLogger(__name__)
_CONFIGURED_FLAG = '_llm_app_logging_configured'


_STANDARD_RECORD_KEYS = frozenset(logging.LogRecord('', 0, '', 0, '', None, None).__dict__) | {
    'message',
    'asctime',
    'request_id',
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            'timestamp': self.formatTime(record, self.datefmt),
            'level': record.levelname,
            'request_id': getattr(record, 'request_id', '-'),
            'logger': record.name,
            'message': record.getMessage(),
        }
        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)

        # 提取 extra：所有不在标准集合里的属性
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_KEYS or key.startswith('_'):
                continue
            if key in payload:  # 防止 extra 覆盖核心字段
                continue
            payload[key] = value

        return json.dumps(payload, ensure_ascii=False, default=str)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def setup_logging(settings: AppSettings | None = None) -> None:
    # ── 第 1 段：幂等保护 ───────────────────────────
    # 反复调用时直接返回，避免同一个 handler 被挂两次 → 日志重复两行
    root = logging.getLogger()
    if getattr(root, _CONFIGURED_FLAG, False):
        return
    # ── 第 2 段：描述"整条流水线"的字典 ─────────────
    settings = settings or AppSettings()
    log_path: Path | None = None
    if settings.log_file:
        log_path = Path(settings.log_file).expanduser()
        if not log_path.is_absolute():
            log_path = ROOT_DIR / log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)  # 先建目录

    # 2. 先组装 handlers，console 永远有
    handlers: dict[str, dict] = {
        'console': {
            'class': 'logging.StreamHandler',
            'level': settings.log_level,
            'formatter': settings.log_format,
            'filters': ['request_id'],
            'stream': 'ext://sys.stdout',
        },
    }

    # 3. 只有配置了路径才加 file handler
    if log_path is not None:
        handlers['file'] = {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': settings.log_level,
            'formatter': settings.log_format,
            'filters': ['request_id'],
            'filename': str(log_path),
            'maxBytes': settings.log_max_bytes,
            'backupCount': settings.log_backup_count,
            'encoding': 'utf-8',
            'delay': True,
        }

    # 4. root 的 handler 列表跟着 handlers 走
    handler_list = list(handlers)
    config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'text': {
                'format': '%(asctime)s|%(levelname)-8s|%(request_id)s|%(name)s|%(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S',
            },
            'json': {'()': 'llm_app.core.logging.JsonFormatter'},
        },
        'filters': {
            'request_id': {'()': 'llm_app.core.logging.RequestIdFilter'},
        },
        'handlers': handlers,
        'root': {
            'level': settings.log_level,
            'handlers': handler_list,
        },
        'loggers': {
            'uvicorn': {'handlers': [], 'level': settings.log_level, 'propagate': True},
            'uvicorn.error': {'handlers': [], 'level': settings.log_level, 'propagate': True},
            'uvicorn.access': {'handlers': [], 'level': settings.log_level, 'propagate': True},
            'httpx': {'handlers': [], 'level': 'WARNING', 'propagate': True},
        },
    }
    logging.config.dictConfig(config=config)
    setattr(root, _CONFIGURED_FLAG, True)
    token = set_request_id('test001')
    try:
        logger.info(
            '日志配置生效: level=%s format=%s file=%s',
            settings.log_level,
            settings.log_format,
            settings.log_file or '(console only)',
            # extra={'request_id': get_request_id()},
        )
    finally:
        reset_request_id(token)
