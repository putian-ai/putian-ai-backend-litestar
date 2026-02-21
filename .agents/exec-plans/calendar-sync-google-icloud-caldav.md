# 统一日历同步中枢：Google + iCloud + 通用 CalDAV/ICS 接入后端与 Electron

这份 ExecPlan 是一份动态文档。随着工作的进行，`Progress`、`Surprises & Discoveries`、`Decision Log` 和 `Outcomes & Retrospective` 章节必须保持更新。

本 ExecPlan 必须遵循仓库内 `.agents/PLANS.md` 的要求，并在每次执行后保持自包含。

## Purpose / Big Picture (目的/大图景)

本变更让用户可以把 Google Calendar、iCloud Calendar（通过 CalDAV）和通用 CalDAV/ICS 日历接入当前系统，并在 Electron 的“日程视图”里看到统一的事件时间线。完成后，用户可以在“设置”里连接账号、触发同步、查看同步状态；在“日程”页里同时看到 Todo 与外部日历事件，并支持双向同步（本地 Todo 改动写回外部日历、外部日历改动回写到本应用）。

用户可见结果不是“增加了一堆表和服务”，而是三个可观察行为：

1. 用户可在 UI 中完成 Google 授权和 iCloud/CalDAV 凭据绑定。
2. 本地 Todo 创建/更新/删除可推送到外部日历（对只读 ICS 自动禁用 push）。
3. 外部日历变更可回拉到本应用并更新本地日程（含取消事件处理）。
4. 同步失败时用户能看到错误信息并可重试，不会悄悄失败。

## Progress (进度)

- [x] (2026-02-13 09:20Z) 完成仓库现状调研（后端领域结构、数据库模型、认证流程、测试结构、Electron 渲染层与主进程边界）。
- [x] (2026-02-13 09:28Z) 明确目标方案：后端作为统一同步中枢，Electron 仅做授权入口与状态展示。
- [x] (2026-02-13 10:46Z) 新增 `calendar_sync` 领域模型、服务、控制器与迁移（连接、镜像事件、Todo 映射）。
- [x] (2026-02-13 10:46Z) 打通 Google OAuth（授权 URL + 回调换 token）与双向同步核心流程（pull/push/both）。
- [x] (2026-02-13 10:46Z) 打通 CalDAV（iCloud/通用）与 ICS Provider 的同步入口，支持 CalDAV 双向、ICS 只读拉取。
- [x] (2026-02-13 10:46Z) 接入 Todo CRUD 自动推送钩子（创建/更新推送，删除前远端删除）。
- [x] (2026-02-13 11:05Z) 完成后端编译与应用启动校验（`create_app()` 成功），并通过相关单元测试冒烟。
- [x] (2026-02-13 03:49Z) 在 `SettingsPage` 增加“日历同步最小联调实验”面板，打通 `create/list/sync/events/google authorize` 前端调用链并展示原始响应。
- [x] (2026-02-13 04:03Z) 使用 `agent-browser` 完成 Google 授权链路最小自动化验证：已确认可创建连接并生成授权 URL，能跳转到 Google 授权域名。
- [ ] (阻塞) Google 授权实际完成被配置阻断：`client_id` 为空导致 Google 返回 `Error 400: invalid_request`。
- [ ] (进行中) Electron 完整产品化接入：设置页正式交互、日程页融合显示外部事件、主进程安全授权跳转。
- [ ] (待执行) 增补单元测试、修复当前 Docker 测试环境后完成集成测试与手动验收记录。

## Surprises & Discoveries (惊喜与发现)

- 观察：当前后端路由存在两套风格，Todo CRUD 走 `/todos`，Agent 走 `/api/todos`，新增日历路由若不统一会增加客户端复杂度。
  证据：`src/app/domain/todo/controllers/todos.py` 使用 `path = "/todos"`；`src/app/domain/todo_agents/urls.py` 定义 `TODO_AGENTS_BASE = "/api/todos"`。

- 观察：Electron 渲染层目前没有使用 preload 暴露能力，也没有主进程 `ipcMain.handle` 业务通道，直接在 renderer 中打开外部授权 URL 不稳定且受安全模块限制。
  证据：`electron-frontend/packages/preload/src/index.ts` 仅导出 `send`；`electron-frontend/packages/main/src/modules/ExternalUrls.ts` 对外链做 origin 白名单；代码中无 `ipcMain.handle`。

- 观察：项目已存在 `user_account_oauth`，但当前并未形成可复用的“多 Provider 日历同步”流程；日历同步单独建模比强行复用账号 OAuth 表更清晰。
  证据：`src/app/db/models/oauth_account.py` 有 token 字段，但 `src/app/domain/accounts/controllers/access.py` 未实现第三方日历授权回调流程。

- 观察：Electron 现有 E2E 仍是模板断言（`count is 0`、Vite logo），与当前产品 UI 不匹配，不能作为本功能验收依据。
  证据：`electron-frontend/tests/e2e.spec.ts` 的断言仍指向模板页面元素。

- 观察：Litestar 中参数名 `state` 与应用状态注入机制冲突，Google 回调接口会在应用启动时签名解析失败。
  证据：`create_app()` 时报 `issubclass() arg 1 must be a class`，将回调参数重命名为 `oauth_state` 后恢复正常。

- 观察：当前集成测试环境依赖 `pytest-databases` 自动解析 Docker 上下文，但本机返回格式与插件预期不一致，导致集成测试在 fixture 初始化阶段失败。
  证据：运行 `uv run pytest tests/integration/test_todo.py -n 2 --quiet` 报错 `TypeError: list indices must be integers or slices, not str`（位于 `pytest_databases/_service.py`）。

- 观察：Electron 的全量 `npm run lint --workspace @app/renderer` 当前会被 `src/api/generated/**` 的历史 `any` 用法阻断，无法直接作为本次最小实验验收标准。
  证据：执行 lint 报 `@typescript-eslint/no-explicit-any` 于 `packages/renderer/src/api/generated/client/client.gen.ts` 等自动生成文件；但针对本次改动文件单独 lint 通过。

- 观察：如果未先执行最新迁移，前端创建日历连接会直接抛后端缺表错误，无法进入授权阶段。
  证据：`POST /api/calendar/connections` 返回 `relation "calendar_connection" does not exist`；执行 `printf "y\n" | uv run app database upgrade` 后恢复。

- 观察：Google 授权 URL 已生成但 `client_id` 为空，Google 侧立即拦截并返回 400。
  证据：授权链接含 `client_id=` 空值；打开后落在 `https://accounts.google.com/signin/oauth/error`，页面文案为 `Missing required parameter: client_id`。

## Decision Log (决策日志)

- 决策：采用“后端统一同步中枢，Electron 仅做连接与展示”的架构。
  理由：Google webhook 和长期凭据管理要求稳定在线服务，Electron 本地进程不适合持续同步任务。
  日期/作者：2026-02-13 / Codex

- 决策：外部日历事件先以“只读镜像”形态进入系统，不自动创建 Todo。
  理由：保持 KISS 与 YAGNI，先交付“可见同步结果”，避免引入双向写回冲突、冲突解决策略和撤销语义复杂度。
  日期/作者：2026-02-13 / Codex

- 决策：该只读策略已被“用户明确要求双向同步”覆盖，当前实施改为 `Todo <-> 外部日历` 双向，ICS 保持只读。
  理由：用户在 2026-02-13 明确确认“双向同步”，需求优先级高于前序保守策略。
  日期/作者：2026-02-13 / Codex

- 决策：Google 采用 OAuth + 增量同步，CalDAV/ICS 采用轮询窗口同步。
  理由：Google 提供稳定的 `syncToken` 与通知机制；CalDAV/ICS 在不同服务商实现差异较大，窗口轮询可先保证可用性。
  日期/作者：2026-02-13 / Codex

- 决策：日历同步独立领域模块 `src/app/domain/calendar_sync`，不混入 `todo` 或 `todo_agents`。
  理由：遵循单一职责，避免 Todo 服务承担外部连接、凭据生命周期和同步状态机。
  日期/作者：2026-02-13 / Codex

- 决策：在 Electron 先交付“最小联调实验面板”，通过直连 `/api/calendar` 验证后端能力，再推进正式 UX 与主进程授权通道。
  理由：用户当前优先目标是确认后端可用性；先做最小闭环能最快产出可观测证据，并避免被 OpenAPI 生成与完整页面重构阻塞。
  日期/作者：2026-02-13 / Codex

## Outcomes & Retrospective (结果与回顾)

已完成后端第一阶段双向能力：连接管理、Provider 抽象、Google/CalDAV/ICS 适配、Todo CRUD 推送钩子、同步 API 与迁移。已完成 `ruff` 与 `compileall` 校验、应用启动校验、以及现有单测冒烟。Electron 侧已完成“最小联调实验面板”，可直接从设置页触发连接、同步与事件查询并查看原始响应。尚未完成 Electron 正式产品化体验（含日程页融合展示与主进程安全授权通道）以及受 Docker 上下文异常影响的集成测试收口。

## Context and Orientation (背景与导向)

当前系统是 Litestar 后端 + Electron 前端。后端主装配点在 `src/app/server/core.py`，控制器通过 `app_config.route_handlers` 注册。Todo CRUD 在 `src/app/domain/todo/controllers/todos.py`，AI Agent 在 `src/app/domain/todo_agents/controllers/todo_agents.py`。Electron UI 入口在 `electron-frontend/packages/renderer/src/App.tsx`，日程页面是 `electron-frontend/packages/renderer/src/pages/SchedulePage.tsx`，设置页是 `electron-frontend/packages/renderer/src/pages/SettingsPage.tsx`。

本计划会引入“外部日历事件镜像”能力。这里的术语定义如下：

- Provider（提供方）：外部日历系统类型，例如 Google、CalDAV、ICS。
- Sync Cursor（同步游标）：记录“上次同步到哪里”的令牌或时间戳，用于下次增量同步。
- Webhook（回调通知）：外部服务向我们的 URL 发送变更通知，不需要我们一直轮询。
- CalDAV：基于 WebDAV 的日历协议，iCloud 与很多企业/个人日历服务支持。
- ICS：iCalendar 文件订阅链接，通常只读，适合公共日历。
- Mirror Event（镜像事件）：把外部事件标准化后存到本地表，用于统一查询和前端渲染。

关键现状文件（执行时会直接修改或新增）：

1. `src/app/server/core.py`：新增日历控制器与依赖类型注册入口。
2. `src/app/config/base.py`：新增日历同步相关配置（OAuth、轮询间隔、webhook 密钥等）。
3. `src/app/db/models/`：新增连接与事件镜像模型，并更新 `__init__.py`。
4. `src/app/db/migrations/versions/`：新增 Alembic 迁移。
5. `electron-frontend/packages/renderer/src/pages/SchedulePage.tsx`：合并 Todo 与外部事件展示。
6. `electron-frontend/packages/renderer/src/pages/SettingsPage.tsx`：增加账号连接、同步状态与手动重试入口。
7. `electron-frontend/packages/renderer/src/api/service.ts`：封装日历新接口。

## Milestones (里程碑)

### Milestone 1：建立可查询的日历同步骨架（数据库 + API + 手动同步）

本里程碑结束时，用户可通过 API 创建连接配置、触发一次同步、查询外部事件。此阶段先不要求 Electron 接入，也不要求 Google webhook 自动触发。

实现范围：

1. 新增 `calendar_connection` 与 `calendar_event` 模型、服务、控制器和迁移。
2. 建立统一事件读取接口（按时间窗口返回，供 `SchedulePage` 使用）。
3. 建立手动同步接口（同步单个连接）。

验收标准：

1. 调用“创建连接 → 触发同步 → 查询事件”三步接口可得到非空事件列表（在 mock provider 或测试桩下可重复）。
2. 新增集成测试通过，且不会影响既有 Todo 接口行为。

### Milestone 2：接入 Google OAuth 与增量同步

本里程碑结束时，用户可完成 Google 授权并同步 Google Calendar；后端可利用游标执行增量同步并可处理 webhook 触发。

实现范围：

1. Google 授权 URL 生成与回调处理。
2. access token 刷新与 `syncToken` 增量拉取。
3. webhook 入站路由与任务触发。

验收标准：

1. 用户完成授权后，连接状态变为 `active`。
2. 首次同步后产生镜像事件，再次同步为增量执行。
3. webhook 请求命中后可触发一次同步作业（日志可见）。

### Milestone 3：接入 iCloud/通用 CalDAV 与 ICS

本里程碑结束时，用户可通过 CalDAV 凭据绑定 iCloud 或其他 CalDAV 服务，并可绑定 ICS 订阅地址实现只读同步。

实现范围：

1. CalDAV 连接创建与验证。
2. 基于时间窗口的轮询同步。
3. ICS 拉取与解析入库。

验收标准：

1. CalDAV 配置保存后，手动同步可返回事件镜像。
2. ICS 地址可拉取并产生日历事件。
3. 同步失败会写入连接错误字段，便于 UI 呈现。

### Milestone 4：Electron 接入（设置页 + 日程页 + 授权跳转）

本里程碑结束时，用户可以在 Electron 里完成连接、重试同步，并在日程视图看到外部事件。

实现范围：

1. 设置页新增“日历连接管理”卡片。
2. 日程页合并渲染外部事件（与 Todo 区分颜色/来源标签）。
3. 新增主进程/预加载的安全外链打开能力用于 OAuth。
4. 重新生成 OpenAPI TypeScript 客户端并接入调用。

验收标准：

1. 在设置页点击“连接 Google”后可拉起系统浏览器授权。
2. 同步完成后，日程页可见外部事件。
3. 连接断开后，外部事件不再显示，Todo 保持不受影响。

### Milestone 5：稳定性与文档收口

本里程碑结束时，系统具备基础可运维能力：重试、幂等、日志、错误提示、文档与最小可用测试集。

实现范围：

1. 补齐失败重试策略与去重策略。
2. 增加关键日志与错误分类。
3. 更新后端与 Electron 文档，补充环境变量说明和手动验收步骤。

验收标准：

1. 单元与集成测试通过。
2. 文档可指导新同事从零完成连接与验证。
3. 重复执行同步不会产生重复镜像记录。

## Plan of Work (工作计划)

先从后端数据结构开始，因为 UI 只能消费稳定 API。第一步在 `src/app/db/models` 新增 `CalendarConnection` 和 `CalendarEvent`，并在 `src/app/db/migrations/versions` 增加迁移。`CalendarConnection` 存 Provider 类型、用户归属、凭据（使用 `EncryptedText` 并以 `settings.app.SECRET_KEY` 作为密钥来源）、同步状态和错误信息。`CalendarEvent` 采用“本地标准化字段 + 原始 payload JSON”双轨存储，标准化字段用于查询和渲染，原始 payload 用于调试和后续扩展。

第二步创建新领域目录 `src/app/domain/calendar_sync`，拆分为 `controllers`、`services`、`providers`、`schemas`、`deps`。控制器只做参数校验和调用服务；服务负责状态机；Provider 适配器负责外部 API 细节。Google、CalDAV、ICS 各自单独实现，统一遵循同一个 Provider 协议，避免控制器写分支。

第三步接入应用装配：在 `src/app/server/core.py` 注册新控制器并扩展 `signature_namespace`。在 `src/app/config/base.py` 增加 `CalendarSettings`（Google client id/secret、redirect URL、webhook secret、轮询周期、同步窗口等），并更新 `.env.local.example` 与 `electron-frontend/.env.example`（如果 Electron 需要新的可公开变量）。

第四步再接 Electron。先在 `electron-frontend/packages/renderer/src/api/service.ts` 增加日历接口封装，然后调整 `SettingsPage.tsx` 增加连接/断开/同步状态 UI，再修改 `SchedulePage.tsx` 拉取并合并外部事件。OAuth 跳转通过 preload + main 进程安全通道实现：在 `electron-frontend/packages/main/src` 新增 IPC handler（只允许 HTTPS 且白名单 host），在 `electron-frontend/packages/preload/src/index.ts` 导出 `openExternalUrl`，renderer 调用该方法而不是直接 `window.open`。

第五步补测试与文档。后端优先补单元测试（Provider 映射、服务幂等、错误分支），再补集成测试（连接创建、同步、查询接口）。Electron 至少补一条可执行的手动验收流程；如更新 Playwright，用当前真实 UI 重写模板断言。

## Concrete Steps (具体步骤)

以下命令全部给出工作目录，执行时严格按目录运行。

1. 准备依赖与基础环境。

   工作目录：`/home/harry/code/putian-ai-todo-back-end-litestar`

   命令：
     make install
     make start-infra
     uv run app database upgrade

   预期：
     数据库与 Redis 启动成功，迁移执行完成。

2. 实现后端日历领域（模型、迁移、服务、控制器）并注册到应用。

   工作目录：`/home/harry/code/putian-ai-todo-back-end-litestar`

   命令：
     uv run app database make-migrations -m "add calendar sync models"
     uv run app database upgrade

   预期：
     新增迁移文件可创建 `calendar_connection` 与 `calendar_event` 表。

3. 完成 Google 与 CalDAV/ICS Provider 适配并打通手动同步接口。

   工作目录：`/home/harry/code/putian-ai-todo-back-end-litestar`

   命令（接口冒烟）：
     uv run pytest tests/unit -k "calendar" --quiet
     uv run pytest tests/integration -k "calendar" --quiet

   预期：
     新增日历测试通过；旧有测试不回归。

4. 重新生成 Electron OpenAPI 客户端并接入 UI。

   工作目录：`/home/harry/code/putian-ai-todo-back-end-litestar/electron-frontend`

   命令：
     npm run openapi
     npm run build

   预期：
     `packages/renderer/src/api/generated/` 更新成功，renderer 构建通过。

5. 端到端手动验收（后端 + Electron）。

   后端工作目录：`/home/harry/code/putian-ai-todo-back-end-litestar`
   Electron 工作目录：`/home/harry/code/putian-ai-todo-back-end-litestar/electron-frontend`

   命令：
     make dev
     npm start

   预期：
     登录后可在设置页连接日历，日程页出现外部事件；断开连接后外部事件消失。

## Validation and Acceptance (验证与验收)

验证必须覆盖“API 行为”“同步行为”“UI 可见行为”三个层次。

1. API 行为验收。

   使用已登录用户调用接口：
   - 创建连接：`POST /api/calendar/connections`
   - 手动同步：`POST /api/calendar/connections/{connection_id}/sync`
   - 查询事件：`GET /api/calendar/events?start=...&end=...`

   通过标准：
   - 创建返回 `connection_id` 与 `status`。
   - 同步返回本次新增/更新/删除计数。
   - 查询返回标准化事件字段，且按时间窗口过滤生效。

2. 同步行为验收。

   - Google：首次同步后有事件，第二次同步使用增量游标（日志里能看到 `incremental=true`）。
   - CalDAV/ICS：轮询窗口重复执行不产生重复镜像记录。
   - 错误处理：凭据错误时连接状态变为 `error`，并带 `last_error`。

3. UI 行为验收。

   - `SettingsPage` 可看到连接状态（`active`/`error`/`syncing`）和“立即同步”按钮。
   - `SchedulePage` 同时展示 Todo 与外部事件，并可区分来源。
   - OAuth 跳转由系统浏览器打开，不会在应用内打开不受信任页面。

4. 回归验收。

   运行：
     make test
     make lint
     cd electron-frontend && npm run build

   通过标准：
   - 后端测试与静态检查通过。
   - Electron renderer 构建通过。

## Idempotence and Recovery (幂等性与恢复)

本计划要求关键步骤可重复执行：

1. 同一连接重复触发同步时，`calendar_event` 通过唯一键 `(connection_id, remote_event_id)` 做 upsert，避免重复数据。
2. 若 Google `syncToken` 失效（例如远端返回“游标无效”），服务自动回退到全量窗口同步并重置游标。
3. 若 CalDAV/ICS 拉取失败，不删除旧镜像，只更新 `last_error` 和失败时间，避免 UI 事件瞬间消失。
4. 数据库迁移失败时，先 `uv run app database downgrade -1` 回滚上一版本，再修复迁移脚本重试。
5. 凭据失效时，用户可在设置页重新认证；重新认证后保留连接记录并更新凭据，不新建重复连接。

## Artifacts and Notes (工件与笔记)

以下内容在执行时以缩进记录在本计划中，作为“行为已生效”的证据。

接口调用示例（响应截断）：

  POST /api/calendar/connections
  {
    "provider": "google",
    "display_name": "Work Google Calendar"
  }
  ->
  {
    "id": "8f6d....",
    "provider": "google",
    "status": "pending_auth"
  }

  POST /api/calendar/connections/8f6d.../sync
  ->
  {
    "status": "success",
    "inserted": 12,
    "updated": 3,
    "deleted": 0
  }

  GET /api/calendar/events?start=2026-02-01T00:00:00Z&end=2026-03-01T00:00:00Z
  ->
  {
    "items": [
      {
        "source": "google",
        "title": "Design Review",
        "start_time": "2026-02-14T09:00:00Z",
        "end_time": "2026-02-14T10:00:00Z"
      }
    ]
  }

关键日志示例：

  Calendar sync started connection_id=... provider=google trigger=manual
  Calendar sync completed connection_id=... inserted=12 updated=3 deleted=0
  Calendar sync failed connection_id=... provider=caldav error="401 Unauthorized"

## Interfaces and Dependencies (接口与依赖)

本节列出实现完成时必须存在的主要接口和依赖，避免执行者自行猜测。

后端新增模块与接口（建议命名）：

1. `src/app/domain/calendar_sync/schemas.py`
   - `CalendarConnectionCreate`
   - `CalendarConnectionModel`
   - `CalendarEventModel`
   - `CalendarSyncResult`

2. `src/app/domain/calendar_sync/controllers/calendars.py`
   - `POST /api/calendar/connections`
   - `GET /api/calendar/connections`
   - `DELETE /api/calendar/connections/{connection_id:uuid}`
   - `POST /api/calendar/connections/{connection_id:uuid}/sync`
   - `GET /api/calendar/events`
   - `GET /api/calendar/providers/google/authorize`
   - `GET /api/calendar/providers/google/callback`（可返回简短 HTML，提示用户回到应用）
   - `POST /api/calendar/webhooks/google`（`exclude_from_auth=True`，使用签名或 token 校验）

3. `src/app/domain/calendar_sync/services.py`
   - `class CalendarConnectionService`
   - `class CalendarSyncService`
   - `async def sync_connection(connection_id: UUID, trigger: str) -> CalendarSyncResult`

4. `src/app/domain/calendar_sync/providers/base.py`
   - `class CalendarProvider(Protocol)`，统一 `authorize`/`refresh`/`fetch_events` 接口。

5. `src/app/domain/calendar_sync/providers/google.py`
   - Google OAuth 与 Calendar API 增量同步实现。

6. `src/app/domain/calendar_sync/providers/caldav.py`
   - CalDAV 连接、窗口查询与事件映射实现。

7. `src/app/domain/calendar_sync/providers/ics.py`
   - ICS URL 拉取与解析实现（只读）。

数据库模型（建议）：

1. `src/app/db/models/calendar_connection.py`
   - 关键字段：`id`, `user_id`, `provider`, `display_name`, `status`, `credential_blob`, `sync_cursor`,
     `sync_state`, `last_synced_at`, `last_error`。
   - `credential_blob` 使用 `EncryptedText(key=lambda: get_settings().app.SECRET_KEY)`。

2. `src/app/db/models/calendar_event.py`
   - 关键字段：`id`, `connection_id`, `user_id`, `remote_event_id`, `title`, `description`, `start_time`,
     `end_time`, `all_day`, `status`, `source_timezone`, `payload`, `remote_updated_at`。
   - 唯一索引：`(connection_id, remote_event_id)`。

Electron 侧改动接口：

1. `electron-frontend/packages/renderer/src/api/service.ts`
   - 新增 `listCalendarConnections`, `createCalendarConnection`, `syncCalendarConnection`,
     `deleteCalendarConnection`, `listCalendarEvents`, `getGoogleAuthorizeUrl`。

2. `electron-frontend/packages/preload/src/index.ts`
   - 新增 `openExternalUrl(url: string): Promise<void>`。

3. `electron-frontend/packages/main/src`（新增模块）
   - 注册 `ipcMain.handle('open-external-url', ...)`，并做 URL 协议和 host 白名单校验。

建议新增依赖：

1. 后端：`icalendar`（解析 ICS）。
2. 后端：`caldav`（CalDAV 客户端；若 API 为同步阻塞调用，需 `asyncio.to_thread` 包装）。
3. 保留现有 `httpx-oauth` 与 `httpx` 能力用于 Google OAuth/token 与 API 调用。

---

Plan Update Note（2026-02-13 / Codex）：创建初版 ExecPlan。基于仓库当前后端与 Electron 代码结构，确定“后端统一同步中枢 + Electron 授权展示”的实现路线，并将里程碑、验证命令、幂等与恢复策略写成可直接执行的步骤，避免执行者依赖外部上下文。
Plan Update Note（2026-02-13 / Codex）：根据用户“确认双向同步”的明确指令，将策略从只读镜像升级为双向同步，并同步更新进度、决策与阶段性结果，使计划与当前代码实现保持一致。
Plan Update Note（2026-02-13 / Codex）：根据用户“先做前端最小实验验证后端”的要求，新增 Electron 设置页最小联调实验进度记录，并补充 lint 现实约束、阶段决策与最新回顾，确保计划与当前实现状态一致。
Plan Update Note（2026-02-13 / Codex）：根据用户要求执行 `agent-browser` Google 授权自动化测试，补充“迁移缺失导致缺表”与“Google client_id 为空导致 400”的关键发现，并更新进度阻塞项，便于后续收口排障。
