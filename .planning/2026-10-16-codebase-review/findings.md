# Findings — LLM_AGENT 代码审阅

审阅范围：`src/llm_app/**`（16 个 .py，545 行）、`alembic/versions/**`、`pyproject.toml`、`.gitignore`、`.env`（仅键名）。
审阅方式：逐文件通读 + `uv run` 实证验证。外部内容一律视为不可信数据。

---

## P0 — 阻塞：服务当前无法启动

### F1. `app.py` 导入即崩溃（已实证）
`src/llm_app/server/app.py:17-38` 把 `UserInfo` / `RegisterInfo` / `LoginResponse` 三个类定义
连同 `user_map_name` / `user_map_id` **整体包进了一个三引号字符串**，它们只是模块级字符串表达式，
从未真正定义。而 `app.py:62` 的函数签名把 `UserInfo | None` 用作返回注解，文件又没有
`from __future__ import annotations`，注解在定义时立即求值：

```
$ uv run python -c "import llm_app.server.app"
  File "src/llm_app/server/app.py", line 62, in <module>
    def debug_users(...) -> UserInfo | None:
NameError: name 'UserInfo' is not defined
```

**影响**：`app.py` 无法导入 → FastAPI 服务完全起不来。整个 `register` / `login` 路由
都是死代码，从未被执行过。
**证据**：`uv run python -c "import llm_app.server.app"` 退出码非 0。
**处理**：删除该字符串块与 `debug_users` 调试路由（`app.py:60-65`，其返回 `{'message':'test'}` 与注解也不符）。

### F2. JWT 配置在 import 期硬失败，且无 `.env.example`
`src/llm_app/server/auth.py:25-33` 在模块层执行 `int(JWT_TOKEN_EXPIRE_TIME)`，三项 env 的
默认值都是 `''` → 任一缺失即 `ValueError: invalid literal for int()`，且发生在 import 期，
调用方拿不到可读的错误信息。
`SECRET_KEY` / `ALGORITHM` / `TOKEN_EXPIRE_TIME` **不在** `.env` 的常规键区（第 53-55 行，
且写成 `KEY = "value"` 带空格形式，靠 python-dotenv 的容错才生效），而 `.env` 本身被
`.gitignore` 忽略、仓库又无 `.env.example` → **全新 clone 必然启动失败且无从下手**。
**处理**：统一走 `core/config.py` 的 pydantic-settings，必填项缺失时抛带字段名的启动期错误；
补 `.env.example`。

---

## P1 — 安全与正确性

### F3. 用户名唯一性靠应用层检查，存在并发竞态
`app.py:70-72` 用 `select(exists(...))` 预检重名后插入；数据库层 `users.user_name` 只有
`index=True`，**无 `unique=True`**（见 `alembic/versions/20261013_1140_abfc71089501.py:34`
与 `models.py:16`）。两个并发注册请求可双双通过预检，插入重复用户名。
**处理**：模型加 `unique=True` + 新迁移；捕获 `IntegrityError` 后返回 409（不用 `except Exception`）。

### F4. 空密钥静默签发 token
`auth.py:25` 的 `os.getenv('SECRET_KEY', '')` 在缺失时静默得到 `''`，`jwt.encode` 会照常
用空密钥签名，不报错。属"配置错了但看起来正常"的典型失效模式，与 F2 同源。
**处理**：pydantic-settings `min_length=1`，启动即校验。

### F5. `CommonLlmApi` 把 `timeout` 塞进请求体、且 HTTP 调用无超时
`src/llm_app/utils/common_class.py:48` 在 payload 中放了 `'timeout': self.timeout`——这不是
OpenAI 兼容协议字段，部分服务端会直接 400；而真正的 `requests.post`（`common_class.py:50-52`）
**没有传 `timeout=`**，网络挂起时线程将永久阻塞。

### F6. `SECRET_KEY` 明文出现在本地 `.env`
`.env:53` 存有实际使用的 JWT 密钥明文。`.gitignore` 已覆盖 `.env`、仓库目前零提交，**未泄漏到
git 历史**；但该值在本次审阅的命令输出中被打印过一次。
**处理**：建议轮换该密钥；后续任何检查只列键名、不读值。

### F7. 滑动窗口可能丢弃刚写入的消息
`src/llm_app/utils/common_function.py:75` 的循环条件是 `... and len(self.history) > 0`，
**单条消息的 token 数超过 `max_total_tokens` 时会把刚 append 的消息也淘汰掉**，导致
`get_messages()` 返回空历史或仅剩 system prompt，请求内容静默丢失。

---

## P2 — 规范与结构（对照 CLAUDE.md）

### F8. `print()` 承担运行期日志
- `common_function.py:77`：窗口裁剪用 `print` 输出（明确的运行期日志场景）
- `main.py:2`：`print("Hello from llm-agent!")`（uv 脚手架残留）
规范要求 `logging.getLogger(__name__)` + `LOG_LEVEL` / `LOG_FORMAT` 环境变量控制。
`config.py:28` 已定义 `AppSettings.log_level`，但**无任何模块使用它建立 logging 配置**。

### F9. 裸 `except Exception` 吞异常
`src/llm_app/chat_token_test.py:50-51`：`except Exception as e: print(...)`。违反"禁止裸 except +
禁止吞掉异常 + 禁止 print 调试"三条。

### F10. 测试脚本位置与副作用
`src/llm_app/chat_token_test.py` 位于包内而非 `tests/`，且**导入期即产生副作用**：
构造 `TokenSlidingChatMemory` 会触发 `AutoTokenizer.from_pretrained('BAAI/bge-m3')`
（`common_function.py:30`，网络下载权重）、构造 `CommonLlmApi` 会读 env 建客户端。
任何工具扫描该包（alembic / 文档生成 / 打包）都可能触发模型下载。

### F11. 配置加载双轨制
`auth.py:6,12,25-27` 与 `chat_token_test.py:4,10-14` 各自 `load_dotenv(find_dotenv())` +
`os.getenv`，绕过已存在的 `core/config.py`（pydantic-settings 体系）。同一项目两套配置机制，
且后者能覆盖前者，行为不可预测。

### F12. 拼写与命名问题
| 位置 | 现状 | 建议 |
|---|---|---|
| `auth.py:16,31,72,85` | `secert_key`（拼写错误） | `secret_key`（尚未被外部引用，早改零成本） |
| `common_class.py:37` | 参数名 `msessages` | `messages` |
| `auth.py:61-62` | 文档串写 `ture or false` | `True or False` |
| `schemas.py:12` | `LoginResponse.userid` | 与 `user_id` 统一（注意前端契约） |

### F13. 缺失的工程基线
`tests/` 目录不存在（规范要求 unit/integration 且覆盖率 ≥80%）；无 `pre-commit` 配置；
无 `.env.example`；`README.md` 为空；`main.py` 无实际入口（无 `uvicorn.run` / ASGI 入口约定）。
`session_manager.py` 为空文件，但 `schemas.SessionCreate` / `SessionResponse`、
`models.ChatSession`、`chat_sessions` 表均已就位 → 会话管理是**唯一"设计已定、实现为零"**的功能块。

### F14. 依赖面存疑
`pyproject.toml` 生产依赖含 `torch`、`transformers`、`jupyterlab`、`ipywidgets`
（数 GB 级）；`zai-sdk` 已安装但代码中未 import。`transformers` 仅用于 `AutoTokenizer` 计数
token，是否值得常驻生产依赖需要决策。

---

## 已验证为「无问题」的项（避免重复排查）
- Alembic 迁移链完整且与 ORM 一致：`creat_at` 拼写错误已在
  `20261014_1136_1a97ea980055` 中通过 `alter_column` 原地修正；`20261016_1031_e1684463b6a2`
  删除了冗余主键索引。
- `config.py:5` / `database.py:12` 的 `parents[3]` 层级正确（指向项目根）。
- `users.user_id`、`chat_sessions.session_id` 均有 `unique=True`。
- `.gitignore` 已覆盖 `.env`，且 `.venv/`、`data/`、`.ruff_cache` 均已忽略。
- `chat_token_test.py` 的 SSE 流式解析（`data: ` 前缀 / `[DONE]` 终止）逻辑正确。

---

## 待用户决策（影响 Phase 3 实施范围）
1. **修复范围**：只修 P0（让服务能起来）／P0+P1（含安全项）／全量含 P2 规范化。
2. **配置收敛方向**：是否按 CLAUDE.md 统一到 pydantic-settings（会牵动 `auth.py`、`chat_token_test.py`）。
3. **`transformers` 宿命**：保留（精度优先）还是换成 `tiktoken`/估算（镜像体积优先）。
4. **会话管理**：本次是否一并实现 `session_manager.py`（当前是空文件）。
