import json
import logging
import logging.config

from llm_app.core.config import AppSettings

_CONFIGURED_FLAG = '_llm_app_logging_configured'


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            'timestamp': '?',  # 提示：self.formatTime(record, self.datefmt)
            'level': '?',  # 提示：record.levelname
            'logger': '?',  # 提示：record.name
            'message': '?',  # 提示：record.getMessage()（不要用 record.msg）
        }
        if record.exc_info:
            payload['exception'] = '?'  # 提示：self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(settings: AppSettings | None = None) -> None:
    # ── 第 1 段：幂等保护 ───────────────────────────
    # 反复调用时直接返回，避免同一个 handler 被挂两次 → 日志重复两行
    root = logging.getLogger()
    if getattr(root, _CONFIGURED_FLAG, False):
        return
    # ── 第 2 段：描述"整条流水线"的字典 ─────────────
    settings = settings or AppSettings()
    config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'text': {
                'format': '%(asctime)s|%(levelname)-8s|%(name)s|%(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S',
            },
            'json': {'()': 'llm_app.core.logging.JsonFormatter'},
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': settings.log_level,
                'formatter': settings.log_format,
                'stream': 'ext://sys.stdout',
            },
        },
        'root': {
            'level': settings.log_level,
            'handlers': ['console'],
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
