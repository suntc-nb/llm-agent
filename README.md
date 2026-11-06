# LLM Agent Chat

基于 FastAPI 的多会话大模型对话应用，实现用户鉴权、会话持久化、SSE 流式响应与基于 token 预算的上下文管理。

后端以分层结构组织（core / models / schemas / server / utils），前端为无框架的原生 JS，整体不依赖任何前端构建工具。

## 功能特性

- **用户鉴权**：注册 / 登录，JWT 令牌 + Argon2 密码哈希
- **多会话管理**：会话创建、列表、删除，历史消息按时间序拉取，消息级联删除
- **流式对话**：SSE 逐块推送，前端边接收边渲染
- **上下文管理**：按 token 数而非消息条数裁剪历史，超出预算时丢弃最早的对话
- **会话内存缓存**：TTLCache 承载热会话，缓存未命中时从数据库历史重建
- **结构化日志**：contextvars 贯穿 `request_id`，支持 `text` / `json` 两种输出格式
- **离线 Swagger**：UI 资源本地化，不依赖 CDN，内网环境可用

## 技术栈

| 层 | 选型 |
|---|---|
| Web 框架 | FastAPI + Uvicorn |
| ORM / 迁移 | SQLAlchemy 2.x + Alembic |
| 数据库 | SQLite |
| 配置 | pydantic-settings + `.env` |
| HTTP 客户端 | httpx（异步、流式） |
| 鉴权 | PyJWT + pwdlib(Argon2) |
| 分词 | transformers（`BAAI/bge-m3` tokenizer） |
| 前端 | 原生 HTML / CSS / JavaScript |

## 目录结构

```
src/llm_app/
├── core/          配置、数据库连接、日志、请求上下文
├── models/        SQLAlchemy ORM 模型
├── schemas/       Pydantic 请求/响应模型
├── server/        应用入口、鉴权、依赖注入
├── utils/         LLM 客户端封装、滑动窗口内存
└── static/        前端页面、样式、脚本、本地 Swagger 资源
alembic/           数据库迁移脚本
```

## 快速开始

```bash
# 1. 安装依赖（使用 uv）
uv sync

# 2. 准备环境变量
cp .env.example .env
# 按需填写 BIGMODEL_API_KEY / SECRET_KEY 等字段

# 3. 初始化数据库
uv run alembic upgrade head

# 4. 启动服务
uv run uvicorn llm_app.server.app:app --reload
```

启动后访问：

- 对话界面：`http://127.0.0.1:8000/static/index.html`
- 接口文档：`http://127.0.0.1:8000/docs`

## 环境变量

| 变量 | 说明 |
|---|---|
| `SQLITE_DATABASE_URL` | SQLite 连接串 |
| `BIGMODEL_API_KEY` | 大模型 API 密钥 |
| `BIGMODEL_ZAI_URL` | 模型服务地址（OpenAI 兼容接口） |
| `BIGMODEL_MODEL_NAME` | 模型名称 |
| `SECRET_KEY` | JWT 签名密钥 |
| `ALGORITHM` | JWT 签名算法 |
| `TOKEN_EXPIRE_TIME` | 令牌有效期（分钟） |
| `LOG_LEVEL` / `LOG_FORMAT` | 日志级别与格式（`text` / `json`） |

## 关键实现说明

**1. 共享 HTTP 客户端由 lifespan 管理**

`httpx.AsyncClient` 的连接池与异步原语绑定在创建它的事件循环上，因此不能在模块顶层创建。应用在 lifespan 中创建、在关闭时释放，并通过依赖注入提供给路由。超时按用途拆分：建连 10 秒失败即放弃，流式读取放宽到 120 秒。

**2. 流式链路关闭压缩协商**

SSE 场景下带 `Content-Encoding` 的响应会被中间层缓冲，导致增量内容迟迟不吐出。请求头显式携带 `Accept-Encoding: identity` 规避。

**3. 上下文按 token 预算裁剪**

直接按消息条数截断会让长消息挤爆模型上下文，按字符数又不准。这里用 bge-m3 的 tokenizer 精确计数，超出预算时从最早的对话开始丢弃。tokenizer 在服务启动阶段预热，避免首个请求承担加载开销。

**4. 会话内存的双重检查重建**

会话热数据放在带 TTL 的进程内缓存里；缓存未命中时加锁回源数据库重建，并在锁内二次检查，避免并发请求重复重建。

**5. 请求 ID 贯穿日志**

中间件为每个请求生成或读取 `X-Request-ID` 写入 contextvars，日志格式化器从中取值，一次请求的所有日志行可被串联检索。

## 已知限制与后续计划

- **RAG 与 Agent 尚未集成**：依赖中已引入 LangChain，检索增强与工具调用目前处于实验阶段，本项目只完成了对话与流式链路。
- **会话缓存为进程内实现**：多实例部署需替换为 Redis。
- **前端未做工程化**：原生 JS，无构建流程与组件拆分。
- **缺少自动化测试**：尚未补齐单元测试与接口测试。
