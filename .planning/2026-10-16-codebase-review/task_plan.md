# Task Plan: LLM_AGENT 代码审阅与修复规划

PLAN_ID: `2026-10-16-codebase-review`

## Goal
在动手改代码之前，把 `src/llm_app` 现有 545 行的问题盘清楚（阻塞项、安全项、规范项），
待用户确认修复范围后，产出一份可执行的实施计划。

## Next Step
把 `findings.md` 的 P0/P1/P2 清单与 4 个待决策项提交用户确认范围（见 ## Decisions Made 待定项）。

## Current Phase
Phase 2

## Phases

### Phase 1: 审阅现有代码库
- [x] 通读 `src/llm_app/**` 全部 16 个模块
- [x] 核对 alembic 迁移链与 ORM 模型一致性
- [x] 核对 pyproject / .gitignore / .env（仅键名）配置面
- [x] 实证复现阻塞问题（`uv run` 导入验证）
- [x] 结论落盘至 `findings.md`
- **Status:** complete

### Phase 2: 确认修复范围
- [ ] 用户确认修复范围（P0 / P0+P1 / 全量）
- [ ] 用户确认配置收敛方向与依赖取舍
- [ ] 确认是否纳入 `session_manager.py` 实现
- [ ] 据此把 Phase 3 拆成具体可执行步骤
- **Status:** in_progress

### Phase 3: 实施修复
- [ ] 待 Phase 2 确定范围后展开
- **Status:** pending

### Phase 4: 验证
- [ ] `uv run python -c "import llm_app.server.app"` 通过
- [ ] `uv run ruff format` / `uv run ruff check` / `uv run pyright` 全绿
- [ ] `uv run pytest` 通过且覆盖率达标
- [ ] 手工冒烟：register → login → 带 token 访问受保护路由
- **Status:** pending

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 审阅先行、不直接改代码 | 用户选择；P0 与配置架构强耦合，先定范围避免返工 |
| 审阅只读，不做任何代码修改 | 保持工作区干净，便于 `git diff --stat` 复核 |
| `project.txt` 不作为设计依据 | 实测为 GBK 编码的目录树转储，不含需求信息 |
| 计划文件置于 `.planning/2026-10-16-codebase-review/` | 命名计划模式，避免与根目录 legacy 文件混淆 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `.env` 键名 grep 用 `^[A-Za-z_]+=` 未匹配到 `SECRET_KEY = "..."` | 1 | `.env` 中键与 `=` 之间有空格；改用含可选空格的模式复检，确认键存在 |
| `import llm_app.server.app` 抛 `NameError` | 1 | 非环境问题，是 `app.py:17-38` 把类定义包进字符串所致（F1），已记录，不在审阅阶段修复 |
