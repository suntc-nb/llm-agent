# Task Plan: LLM_AGENT 学习项目 — 打通聊天闭环

PLAN_ID: `2026-10-16-codebase-review`

## Goal
以自学为目的，把「注册 → 登录 → 建会话 → 流式对话 → 刷新回显」这条链路跑通。
只修阻塞这条链路的问题；不引入测试、pre-commit、配置重构等生产化设施。

## Next Step
等待用户确认是否按 Batch 1 → Batch 2 的顺序开始实施；确认后从 L1 开始。

## Current Phase
Phase 3

## Phases

### Phase 1: 审阅现有代码库
- [x] 通读 `src/llm_app/**`
- [x] 结论落盘至 `findings.md`
- **Status:** complete

### Phase 2: 确认修复范围
- [x] 2026-10-16 版范围确认（由用户自行推进，与本计划不同）
- **Status:** complete

### Phase 2.5: 状态复核（2026-10-28）
- [x] 复核 12 天内的代码演进
- [x] F1（启动崩溃）、F3（用户唯一索引）已关闭
- [x] 新发现 N1~N5 写入 `findings.md`
- **Status:** complete

### Phase 3: 确认本轮范围
- [x] 用户明确：自学项目，不需要生产化设施
- [x] 范围收敛为「打通聊天闭环」
- [ ] 用户确认是否开始实施
- **Status:** in_progress

### Phase 4: 实施（学习版最小集）
- [x] D1（临时插入）：`/docs` 白屏修复 —— Swagger UI 资源改为本地加载
- [ ] Batch 1：让对话能发出去（L1、L2）
- [ ] Batch 2：会话可回显（L3、L4，L5 可选）
- [ ] Batch 3：顺手清理（L6，可选）
- **Status:** in_progress

### Phase 5: 手工验证
- [ ] 浏览器完整走一遍：注册 → 登录 → 新建会话 → 发消息 → 看到流式回复
- [ ] 刷新页面后历史消息仍在
- [ ] `uv run ruff check .` 通过
- **Status:** pending

## Implementation Plan（学习版）

### D1 [已完成 2026-10-28] `/docs` 白屏修复
- **原因**：`/docs` 的 HTML 正常（200），但 FastAPI 默认引用
  `cdn.jsdelivr.net` 的 `swagger-ui-bundle.js` / `swagger-ui.css`；
  本机访问 jsdelivr 失败（curl 返回 000），页面因此空白。
- **做法**：
  - 下载 `swagger-ui-dist@5.17.14` 的两个资源到 `src/llm_app/static/swagger/`
  - `app.py` 设 `docs_url=None`，新增 `/docs` 路由，用 `get_swagger_ui_html`
    指向 `/static/swagger/...`
- **验收**：`/docs` HTML 引用本地路径；两个资源均 200；`/openapi.json` 仍 200

### Batch 1 — 让对话能发出去

#### L1 [必修] 修正 SSE Content-Type
- **文件**：`src/llm_app/server/app.py:345`
- **问题**：`media_type='text/envent-stream'` 拼写错误，浏览器不识别
- **做法**：改为 `'text/event-stream'`
- **验收**：发送消息时响应头为 `Content-Type: text/event-stream; charset=utf-8`

#### L2 [必修] 前端实现 `sendMessage()`
- **文件**：`src/llm_app/static/js/chat.js:159-162`
- **现状**：只 `console.log('测试消息', input)`，没有发请求
- **做法**：
  - 取输入框内容，清空输入框
  - 在 `#chat-messages` 里追加用户气泡和空的 assistant 气泡
  - `fetch('/api/chat/stream', { method:'POST', headers:{...token...}, body: JSON.stringify({ sessionId, content }) })`
  - 用 `response.body.getReader()` + `TextDecoder('utf-8')`（`stream: true`）读取
  - 按 `\n\n` 切分事件，解析 `data: {"content": "..."}`，增量写进 assistant 气泡
  - 收到 `data: {"done": true}` 结束
- **验收**：在浏览器里输入文字并发送，回复逐字出现
- **依赖**：L1
- **注意**：`TextDecoder` 必须带 `stream: true`，否则中文可能被 chunk 切断

### Batch 2 — 会话可回显

#### L3 [必修] 新增历史消息接口
- **文件**：`src/llm_app/server/app.py`
- **做法**：新增 `GET /api/sessions/{session_id}/messages`
  - 校验该会话属于当前用户，否则 404
  - 按 `created_at` 升序返回 `list[schemas.ChatMessageResponse]`
- **验收**：新会话返回 `[]`；聊过天后返回 user/assistant 消息

#### L4 [必修] 切换会话时加载历史
- **文件**：`src/llm_app/static/js/chat.js`
- **做法**：`selectSession()` 里调用 L3 的接口，把消息渲染成气泡；页面初始化时也加载当前会话
- **验收**：刷新页面后，历史对话仍显示；切换不同会话显示各自内容
- **依赖**：L3

#### L5 [可选] 根路径直接打开页面
- **文件**：`src/llm_app/server/app.py`
- **做法**：`@app.get('/')` 返回 `FileResponse(static_dir / 'index.html')`
- **验收**：访问 `http://localhost:8000/` 直接看到登录页

### Batch 3 — 顺手清理（可选）

#### L6 [建议] 删除调试路由与内存 token 表
- **文件**：`app.py`
- **做法**：删除 `/api/test`、`/api/debug/users`、`LoginInfo`、`user_map_id`
  以及 `login()` 里写入 `user_map_id` 的几行
- **理由**：`/api/test` 未登录就能拿到所有 token，虽在本地学习也没有保留价值；
  同时能让 `login()` 更干净、更容易读懂
- **验收**：`/api/test` 返回 404，登录功能不受影响

### 验证方式（手工即可）
| 步骤 | 期望 |
|------|------|
| 浏览器打开首页 → 注册 → 登录 | 进入聊天页 |
| 新建会话 → 输入消息 → 发送 | 回复逐字出现 |
| 刷新页面 | 会话列表与历史消息仍在 |
| 切换会话 | 显示各自历史 |
| `uv run ruff check .` | `All checks passed!` |

## 暂不做（学习阶段不需要）
- `tests/` 与覆盖率、CI
- pre-commit、密钥扫描
- `.env.example`
- 配置体系重构（`auth.py` 收敛到 pydantic-settings）
- JSON 日志、logging 规范化
- `transformers` 替换 / 依赖瘦身
- 全项目命名与文档串大修

以上条目已记录在 `findings.md`，以后想补再单独开计划。

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 只做「聊天闭环」相关修复 | 用户明确这是自学项目，不需要生产化设施 |
| 审阅先行、不直接改代码 | 先看清现状再动手 |
| 计划文件置于 `.planning/2026-10-16-codebase-review/` | 命名计划模式，避免与根目录 legacy 文件混淆 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `.env` 键名 grep 未匹配 `SECRET_KEY = "..."` | 1 | 键与 `=` 之间有空格；改用含可选空格的模式复检 |
| `import llm_app.server.app` 抛 `NameError` | 1 | 已由后续代码修复，2026-10-28 复核实测通过 |
