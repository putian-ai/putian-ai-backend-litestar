# Improve AI assistant page UX and timezone handoff

这份 ExecPlan 是一份动态文档。随着工作的进行，`Progress`、`Surprises & Discoveries`、`Decision Log` 和 `Outcomes & Retrospective` 章节必须保持更新。本计划遵循仓库根目录下的 `.agents/PLANS.md`。

## Purpose / Big Picture (目的/大图景)

用户进入 AI 助手页面后不会再看到会话列表与当前会话 ID，页面更聚焦于对话内容，同时保留新建会话与用量信息。对话在 AI 输出时会自动滚动到底部，但当用户手动上滑时不会被强制拉回。用户可以在页面上选择具体的 AI agent（默认 TodoOrchestratorAgent）。每次发送消息时，前端会把用户的 IANA 时区传到后端，后端将该时区写入工具上下文并作为默认时区使用，以保证调度与时间解析准确。

## Progress (进度)

- [x] (2026-01-26 03:16Z) 调整 `electron-frontend/packages/renderer/src/pages/AgentPage.tsx` 的布局，隐藏会话列表与当前会话信息，并保留新建会话与用量显示。
- [x] (2026-01-26 03:16Z) 为消息列表增加非强制自动滚动逻辑，用户上滑后不自动回滚。
- [x] (2026-01-26 03:16Z) 在 AI 助手页面添加 agent 选择器（默认 TodoOrchestratorAgent），并随请求发送。
- [x] (2026-01-26 03:16Z) 后端 `AgentTodoRequest` 增加 `timezone` 字段，控制器与服务传递该值。
- [x] (2026-01-26 03:16Z) 在工具上下文中保存时区，并在 CRUD/调度工具与 `get_user_datetime` 工具中默认使用。
- [x] (2026-01-26 03:16Z) 更新单测并执行 `uv run pytest tests/unit/test_todo_agents_controller.py -q` 与 `npm run build` 验证。

## Surprises & Discoveries (惊喜与发现)

- 观察：`@heroui/react` 的 `CardBody` 不支持 `ref`，需要改用 `data-` 选择器获取滚动容器。
  证据：`npm run build` 报错 `Property 'ref' does not exist`。
- 观察：流式接口未设置默认 session_id，导致测试期望与实际不一致。
  证据：`pytest` 报错 `session_id` 为 `None`。

## Decision Log (决策日志)

- 决策：使用工具上下文保存 `timezone` 并在工具里作为默认值，而不是修改大量 system prompt。
  理由：改动集中、行为可控，且与现有全局上下文设计一致。
  日期/作者：2026-01-26 / Codex
- 决策：前端使用轻量 `select` 组件而非引入新依赖或修改生成代码。
  理由：避免新增依赖与修改生成文件，保持最小变更。
  日期/作者：2026-01-26 / Codex
- 决策：通过 `data-agent-messages` 查询滚动容器，避免 `CardBody` ref 类型限制。
  理由：保持现有布局与样式，同时解决类型报错。
  日期/作者：2026-01-26 / Codex
- 决策：为流式接口补齐默认 `session_id` 逻辑，与非流式接口保持一致。
  理由：避免 session_id 为 None，统一行为并修复测试期望。
  日期/作者：2026-01-26 / Codex
- 决策：抽取 `timezone_utils.resolve_timezone` 复用时区解析逻辑。
  理由：减少 CRUD/调度工具重复判断，统一错误提示，提升可维护性。
  日期/作者：2026-01-26 / Codex
- 决策：消息滚动容器改为 `CardBody` 内部 `div` + `ref`，不再依赖 DOM 查询。
  理由：保证类型安全与可控滚动行为，避免 `CardBody` ref 限制。
  日期/作者：2026-01-26 / Codex

## Outcomes & Retrospective (结果与回顾)

已完成 UI 隐藏、agent 选择、自动滚动与时区透传，并在工具层抽取时区解析共用逻辑。消息滚动改为内部容器 `ref` 实现，后端单测与 Electron 前端构建均通过。后续若需要支持更多 agent，可扩展 `AGENT_OPTIONS`。

## Context and Orientation (背景与导向)

AI 助手页面位于 `electron-frontend/packages/renderer/src/pages/AgentPage.tsx`，当前包含会话列表卡片与“当前会话”展示。消息区使用 `CardBody` 作为滚动容器。前端通过 `electron-frontend/packages/renderer/src/api/service.ts` 调用 `POST /api/todos/agent-create/stream`。后端请求模型位于 `src/app/domain/todo_agents/schemas.py` 的 `AgentTodoRequest`，控制器在 `src/app/domain/todo_agents/controllers/todo_agents.py`，业务在 `src/app/domain/todo_agents/services.py`。工具上下文在 `src/app/domain/todo_agents/tools/tool_context.py`，具体时间解析逻辑分散在 `todo_crud_tools.py`、`todo_schedule_tools.py` 和 `universal_tools.py`。

## Plan of Work (工作计划)

先修改 Electron 前端的 AI 助手页面：去掉会话列表卡片与会话 ID 文案，新增 agent 选择器，并增加消息区的自动滚动逻辑（仅在用户未离开底部时生效）。然后在前端发起请求时加入 `timezone` 字段。接着修改后端的 `AgentTodoRequest` 增加 `timezone`，并把它贯穿控制器与服务层。最后扩展工具上下文保存时区，并在 CRUD/调度工具与 `get_user_datetime` 工具中使用该默认时区。完成后更新单测签名，并运行后端单测与前端构建验证。

## Concrete Steps (具体步骤)

1) 读取并编辑 Electron AI 助手页面。
   - 目标文件：`electron-frontend/packages/renderer/src/pages/AgentPage.tsx`
   - 变更要点：移除会话列表卡片与当前会话展示；加入 agent 选择器；在消息容器上添加 `ref` 和 `onScroll` 以控制自动滚动；发送请求时携带 `timezone`。

2) 更新前端 API 调用类型（仅在 `service.ts` 中做本地类型扩展，不改生成文件）。
   - 目标文件：`electron-frontend/packages/renderer/src/api/service.ts`
   - 变更要点：为 `agentCreate`/`agentCreateStream` 的 payload 类型添加 `timezone?: string`。

3) 更新后端请求 schema 与控制器。
   - 目标文件：`src/app/domain/todo_agents/schemas.py`
   - 目标文件：`src/app/domain/todo_agents/controllers/todo_agents.py`
   - 变更要点：新增 `timezone` 字段并传递到服务层。

4) 更新后端服务与工具上下文。
   - 目标文件：`src/app/domain/todo_agents/services.py`
   - 目标文件：`src/app/domain/todo_agents/tools/tool_context.py`
   - 变更要点：服务方法新增 `user_timezone` 参数；上下文保存并提供 `get_user_timezone`。

5) 在工具实现里使用默认时区。
   - 目标文件：`src/app/domain/todo_agents/tools/universal_tools.py`
   - 目标文件：`src/app/domain/todo_agents/tools/todo_crud_tools.py`
   - 目标文件：`src/app/domain/todo_agents/tools/todo_schedule_tools.py`
   - 变更要点：当 args 未提供 timezone 时，改用工具上下文的时区。

6) 更新单测并验证。
   - 目标文件：`tests/unit/test_todo_agents_controller.py`
   - 运行后端单测与前端构建命令，确认无类型与逻辑回归。

## Validation and Acceptance (验证与验收)

后端：
- 在仓库根目录运行 `uv run pytest tests/unit/test_todo_agents_controller.py -q`，期望通过。

前端（Electron）：
- 在 `electron-frontend/` 目录运行 `npm run build`，期望构建成功无类型错误。

行为验收：
- 进入 AI 助手页面，确认看不到会话列表卡片与会话 ID。
- 发送消息后，当 AI 输出时滚动自动跟随到底部；手动上滑后不被强制拉回。
- 选择不同 agent 发送，后端请求 payload 包含 `agentname` 与 `timezone`。

## Idempotence and Recovery (幂等性与恢复)

这些改动可重复应用；前端 UI 与后端 schema 的更改是增量的。若出现回归，可回退到变更前的文件版本；不会影响数据库结构或迁移。

## Artifacts and Notes (工件与笔记)

预期请求体片段示例：
  {
    "messages": [{"role": "user", "content": "帮我安排明天上午的学习"}],
    "sessionid": "user_xxx_todo_agent",
    "agentname": "TodoOrchestratorAgent",
    "timezone": "Asia/Shanghai"
  }

## Interfaces and Dependencies (接口与依赖)

- `AgentTodoRequest` 新增字段：`timezone: str | None`。
- `TodoAgentService.chat_with_agent` 与 `stream_chat_with_agent` 新增可选参数 `user_timezone`。
- `tool_context.set_agent_context` 增加 `user_timezone` 参数，并新增 `get_user_timezone`。
- `universal_tools.get_user_datetime_impl` 在未提供 timezone 时使用上下文默认值。
- `todo_crud_tools` 与 `todo_schedule_tools` 在解析时间时，优先使用参数 timezone，否则使用上下文默认时区。

---
Plan updated on 2026-01-26 to record optimization decisions and verification results.
