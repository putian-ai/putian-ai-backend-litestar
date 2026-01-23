# Electron 前端模块化多页应用 + 日程视图（Todo AI 桌面端）

这份 ExecPlan 是一份动态文档。随着工作的进行，`Progress`、`Surprises & Discoveries`、`Decision Log` 和 `Outcomes & Retrospective` 章节必须保持更新。

本计划遵循仓库根目录的 `.agents/PLANS.md` 要求进行维护。

## Purpose / Big Picture (目的/大图景)

这次工作将把渲染层升级为“模块化多页应用”，具备 Todo 管理、日程视图与 AI 助手三条核心体验路径。用户能够在独立页面中完成“登录 -> 任务管理 -> 日程查看 -> AI 规划”，并在设置页查看账号与用量信息。完成后，打开 Electron 应用即可看到清晰的导航与多页结构，主流程可被端到端验证。

## Progress (进度)

- [x] (2026-01-20 00:00Z) 选择“方案 2：模块化多页应用 + 日程视图”。
- [x] (2026-01-20 04:30Z) 设计信息架构与导航（页面划分、路由/导航方式）。
- [x] (2026-01-20 04:30Z) 搭建应用壳与页面容器（布局、顶部/侧边导航、页头）。
- [x] (2026-01-20 04:30Z) 实现认证模块 MVP（登录/注册/退出 + 验证提示）。
- [x] (2026-01-20 04:30Z) 实现 Todo 模块（列表/创建/编辑/删除 + 标签管理 + 基础筛选）。
- [x] (2026-01-20 04:30Z) 实现日程模块（按日期视图展示 Todo，支持时间范围切换）。
- [x] (2026-01-20 04:30Z) 实现 AI 助手模块 MVP（非流式对话 + 会话列表 + 用量信息）。
- [x] (2026-01-20 04:30Z) 统一空态/错误态/加载态，完成视觉打磨与验证记录。

## Surprises & Discoveries (惊喜与发现)

- ESLint 会对 OpenAPI 自动生成文件报 `no-explicit-any` 与 `ban-ts-comment`，需在 lint 配置中排除或降级规则。
- Electron 渲染层使用 `credentials: include` 时，后端 CORS 若保持 `*` 会被浏览器拒绝，需要开发环境显式允许 `http://127.0.0.1:5173/5174`。

## Decision Log (决策日志)

- 决策：采用“多页模块化”信息架构，但先以轻量导航实现，不强制引入路由依赖。
  理由：保留多页体验的清晰度，同时控制依赖复杂度，符合 KISS/YAGNI。
  日期/作者：2026-01-20 / Codex
- 决策：日程视图基于已有 Todo 列表接口做前端分组与筛选。
  理由：后端无专用日程接口，前端聚合可快速落地 MVP。
  日期/作者：2026-01-20 / Codex
- 决策：AI 助手 MVP 先走 `/api/todos/agent-create`，流式接口作为后续增强。
  理由：降低实现复杂度，先验证业务链路。
  日期/作者：2026-01-20 / Codex
- 决策：优化阶段引入 `/api/todos/agent-create/stream`，使用生成客户端的 SSE 通道。
  理由：提升对话反馈速度，保持依赖最小化。
  日期/作者：2026-01-20 / Codex

## Outcomes & Retrospective (结果与回顾)

- 已完成多页信息架构、主布局与核心模块 UI，形成可运行的 Todo/日程/AI/设置 MVP。
- 已补齐 AI 流式响应（SSE）以提升交互实时性。

## Context and Orientation (背景与导向)

渲染层位于 `electron-frontend/packages/renderer/`，入口为 `electron-frontend/packages/renderer/src/main.tsx`。OpenAPI 客户端已生成在 `electron-frontend/packages/renderer/src/api/generated/`，调用封装在 `electron-frontend/packages/renderer/src/api/generated/sdk.gen.ts`。

关键 API：

- 认证与账户：`/api/access/login`、`/api/access/signup`、`/api/access/logout`、`/api/me`、`/api/access/resend-verification`
- Todo 与标签：`/api/todos`、`/api/todos/tags`、`/api/todos/create_tag`、`/api/todos/delete_tag/{tag_id}`
- AI 助手：`/api/todos/agent-create`、`/api/todos/agent-sessions`、`/api/todos/agent-sessions/new`、`/api/todos/agent-sessions/{session_id}/history`、`/api/todos/usage-stats`
- 会话管理：`/api/agent-sessions` 与 `/api/agent-sessions/{session_id}/messages` 系列

Todo 关键字段：`item`、`description`、`start_time`、`end_time`、`importance`、`tags`。日程视图需要基于 `start_time/end_time` 按天分组。

## Plan of Work (工作计划)

先定义应用信息架构和导航模型，把页面划分为“概览/仪表盘”“Todo”“日程”“AI 助手”“设置”。随后构建应用壳与页面容器，通过轻量状态管理实现页面切换。再按模块分别实现认证、Todo、日程与 AI 页面，每个模块都遵循单一职责：页面负责布局与交互、服务层负责 API 调用与转换。最后补齐空态/错误态/加载态，并完成最小验证脚本或手动验证记录。

## Concrete Steps (具体步骤)

1) 在 `electron-frontend/packages/renderer/src/` 建立页面与组件结构（例如 `pages/`、`features/`、`components/`、`layouts/`、`state/`），并替换 `App.tsx` 为应用壳与导航框架。
2) 定义“导航状态模型”（当前页、二级标签、用户会话状态）与轻量状态容器，避免引入大型依赖。
3) 认证模块：实现登录/注册/退出页，登录后进入主布局；未登录时只能访问认证页。
4) Todo 模块：列表页（含筛选、排序、分页/加载更多）+ 表单抽屉或详情页；标签管理独立面板。
5) 日程模块：按天或周视图展示 Todo（由 `start_time/end_time` 分组），提供日期切换与时间段筛选。
6) AI 助手模块：对话页（发送消息、查看会话列表、查看用量卡片），数据源来自 `agent-create` 与 session/history。
7) 完成空态/错误态/加载态与基础视觉，保证主流程连贯。

## Validation and Acceptance (验证与验收)

- 在 `electron-frontend/` 目录运行：
  - `npm run dev --workspace @app/renderer`
- 验收结果：
  - 登录成功后进入主界面，可在导航中切换到 Todo、日程、AI、设置页面。
  - Todo 新建、更新、删除能在列表中回显。
  - 日程页能按日期展示 Todo，并能切换日期范围。
  - AI 助手能返回响应并显示对话历史。
  - 用量信息在 AI 或设置页可见。

## Idempotence and Recovery (幂等性与恢复)

- UI 结构与组件可重复调整；任何页面重构都保持模块内替换，避免一次性大改。
- OpenAPI 生成代码不可修改，自定义逻辑放在手写封装层，重新生成不会覆盖。

## Artifacts and Notes (工件与笔记)

- 页面结构建议：侧边导航（概览/Todo/日程/AI/设置）+ 内容区（列表/日程/对话）+ 顶部状态栏（当前用户/快捷动作）。

## Interfaces and Dependencies (接口与依赖)

- 依赖优先使用现有：React + HeroUI + Tailwind v4。
- API 调用使用 `electron-frontend/packages/renderer/src/api/generated/sdk.gen.ts`。
- 若引入路由/状态库，需记录原因与替代方案评估。

更新记录：补充 AI 流式响应的决策与成果说明，并记录开发环境 CORS 修正。
