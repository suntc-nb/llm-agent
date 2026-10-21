"""开发服务器启动入口。

用法::

    uv run python scripts/dev_server.py

仅监听 ``src/`` 目录以实现热重载,避免 uvicorn 扫描 ``.venv`` 中的
数万个 Python 文件。可通过 ``DEV_HOST`` / ``DEV_PORT`` 环境变量覆盖
监听地址与端口。
"""

import os
from pathlib import Path

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / 'src'


def main() -> None:
    """启动带热重载的 Uvicorn 开发服务器。"""
    uvicorn.run(
        'llm_app.server.app:app',
        host=os.getenv('DEV_HOST', '0.0.0.0'),
        port=int(os.getenv('DEV_PORT', '8000')),
        reload=True,
        reload_dirs=[str(SRC_DIR)],
    )


if __name__ == '__main__':
    main()
