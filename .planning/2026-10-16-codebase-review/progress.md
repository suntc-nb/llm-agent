# Progress Log

## Session: 2026-10-16

### Current Status
- **Phase:** 2 - 确认修复范围（等待用户决策）
- **Started:** 2026-10-16
- **Plan ID:** 2026-10-16-codebase-review

### Actions Taken
- 恢复项目状态：无既有计划文件，`git diff --stat` 为空（仓库零提交，工作区均为未跟踪初始文件）
- `init-session.sh "Codebase Review"` 创建命名计划目录并记录 active pointer
- 通读 `src/llm_app/**` 全部 16 个模块（共 545 行）、4 个 alembic 迁移
- 核对 `pyproject.toml`、`.gitignore`、`.env`（**只读键名，不读值**）
- 实证验证关键假设（见 Test Results）
- 产出 `findings.md`：P0×2、P1×5、P2×7，另附「已验证无问题」清单

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| `uv run python -c "import llm_app.server.app"` | 导入成功 | `NameError: name 'UserInfo' is not defined` @ app.py:62 | FAIL（阻塞项 F1，非环境问题） |
| `resolve-plan-dir.sh` | 返回计划目录或空 | 空输出（无既有计划） | OK |
| `git diff --stat` | 显示已跟踪文件改动 | 空 | OK |
| `.env` 键名清单 | 列出全部变量名 | 22 个键；JWT 三项位于第 53-55 行 | OK |

### Notes
- 服务当前**无法启动**：`app.py` 导入即崩溃，`register`/`login` 路由从未被执行过，
  因此现有 DB 中可能无任何真实用户数据，修复时无需考虑数据兼容。
- `.env:53` 的密钥值在本次审阅的命令输出中出现过一次，已在 findings F6 记录并建议轮换。

### Errors
| Error | Resolution |
|-------|------------|
| 见 `task_plan.md` ## Errors Encountered | 同 |

---

## Session: 2026-10-28

### Current Status
- **Phase:** 3 - 确认本轮修复范围（等待用户决策）
- **Plan ID:** 2026-10-16-codebase-review
- **工作区:** `7d2696c 创建后端路由` + 6 个已修改文件、2 个未跟踪文件

### Actions Taken
- 恢复规划状态：解析到 `.planning/2026-10-16-codebase-review`（`.active_plan` 指向该目录）
- `git log --stat` / `git diff --stat` 复核 12 天内的演进
- 实测 `uv run python -c "import llm_app.server.app"` → `IMPORT_OK`（F1 已关闭）
- 核对最新迁移 `dfb7606ad607`：`users.user_name` 唯一索引已建立（F3 DB 层已关闭）
- 通读当前 `app.py`(352 行)、`auth.py`、`config.py`、`common_function.py`、
  `common_class.py`、`static/index.html`、`static/js/chat.js`、`scripts/dev_server.py`
- 结论写入 `findings.md`「状态复核 2026-10-28」：新增 N1~N5，原 P1/P2 逐项标注现状

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| `uv run python -c "import llm_app.server.app"` | 导入成功 | `IMPORT_OK` | OK |
| `resolve-plan-dir.sh` | 返回既有计划目录 | `.planning/2026-10-16-codebase-review` | OK |
| `git diff --stat` | 显示未提交改动 | 6 文件 +601/-18 | OK |
| 静态资源路径 | `/static/index.html` 可访问 | 挂载存在，但无 `/` 路由（N4） | WARN |
| 前端消息发送 | 调用流式接口 | `sendMessage()` 仅 `console.log`（N3） | FAIL |

### Notes
- 本轮**未修改任何业务代码**，仅更新规划文件。
- 建议的修复优先级：N1（token 泄露）→ N2（SSE 类型）→ N3/N4（前端闭环）→ N5 → 仍开放的 P1。

### 范围修正（用户反馈）
- 用户明确：这是**自学 web 项目**，不是要上生产，不需要测试/CI/pre-commit/配置重构等生产化设施。
- 已按此重写 `task_plan.md`：范围收敛为「注册 → 登录 → 建会话 → 流式对话 → 刷新回显」，
  任务缩减为 L1~L6 共 6 项，其中 L1/L2/L3/L4 必修，L5/L6 可选。
- 生产化条目（F2/F4/F8/F11/F13/F14 等）保留在 `findings.md`，列入「暂不做」。

### 临时插入任务 D1：`/docs` 白屏（已完成）
- **排查**：`/docs` 与 `/openapi.json` 均返回 200；`curl cdn.jsdelivr.net` 返回 `000`
  （连接失败），确认是 Swagger UI 外链资源加载不到，不是 FastAPI 故障。
- **实施**：
  - 下载 `swagger-ui-dist@5.17.14` 的 `swagger-ui-bundle.js`(1.4M)、
    `swagger-ui.css`(149K) 到 `src/llm_app/static/swagger/`
  - `app.py`：`FastAPI(..., docs_url=None)`；新增 `/docs` 路由，
    用 `get_swagger_ui_html` 指向本地资源
- **验证**：`/docs` 引用 `/static/swagger/...`；bundle/css/openapi 均 200；
  `uv run ruff check src/llm_app/server/app.py` → `All checks passed!`
- **改动文件**：`src/llm_app/server/app.py`、新增 `src/llm_app/static/swagger/*`

### 问题：浏览器发送后 `fullContent` 为空（已解决）
- **排查证据**：
  - 服务端原始响应为标准 SSE（`text/event-stream`），每条 `data: {"content": "..."}`
  - 用 Node 复刻浏览器解析逻辑 + 完全相同请求体（`session_id` + 中文）
    → 200、拼出完整回复，证明服务端与请求体均正常
  - 线上 `chat.js` 与磁盘一致
- **根因**：旧代码把每次 `reader.read()` 的 chunk 当作完整行集合
  （`chunk.split('\n')`）。ReadableStream 的 chunk 边界不等于 SSE 事件边界，
  一条 `data:` 事件被切开时：前半段 `JSON.parse` 失败被 catch 吞掉，
  后半段不以 `data: ` 开头被忽略 → 内容静默丢失。
- **修复**：`chat.js` 改为 `buffer` 累积 + 按空行切完整事件，残余留到下一轮；
  增加 `content-type` 校验与解析错误日志。
- **附带**：删除临时调试脚本 `.planning/debug_stream.mjs`（内含 JWT）。
