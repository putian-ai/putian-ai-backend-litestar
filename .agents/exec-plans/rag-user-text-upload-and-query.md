# 为 Litestar 后端集成用户隔离的 LightRAG 纯文本知识库

这份 ExecPlan 是动态文档。随着工作推进，`Progress`、`Surprises & Discoveries`、`Decision Log` 和 `Outcomes & Retrospective` 必须保持更新。

本计划遵循仓库规则文件：`.agents/PLANS.md`。任何后续修改都必须继续满足该文件中的自包含、可验证、结果导向要求。

## Purpose / Big Picture (目的/大图景)

用户现在可以把 `text/plain` 文本上传到后端，系统会异步构建个人知识库索引，并通过 `/api/rag/query` 返回“答案 + 引用片段”。这让用户从“只能与待办代理交互”升级为“可以把私人文本当知识库检索问答”，并且每个用户的数据完全隔离。

可观察结果：

1. 上传接口成功返回 `queued` 和 `document_id`。
2. 文档列表可看到状态变化（`queued/indexing/ready/failed/deleted`）。
3. 查询接口返回 `answer` 与 `sources`，可选 `document_id` 严格过滤。
4. 删除文档后触发重建，不再出现在可用文档中。

## Progress (进度)

- [x] (2026-03-02 04:10Z) 新增 `rag` 领域骨架与接口定义：`controllers/services/schemas/deps/urls/queue/lightrag_client`。
- [x] (2026-03-02 04:13Z) 新增数据库模型 `rag_document` 并在 `user` 关系中挂载。
- [x] (2026-03-02 04:14Z) 新增 Alembic 迁移 `3d2a7f9e8b1c`，创建 `rag_document` 表与索引。
- [x] (2026-03-02 04:16Z) 扩展 `AISettings`（DeepSeek + SiliconFlow + RAG 队列/存储配置）。
- [x] (2026-03-02 04:18Z) 在应用核心注册 `RagController` 与 RAG worker 生命周期。
- [x] (2026-03-02 04:20Z) 增加单元测试 `tests/unit/test_rag_service.py`、`tests/unit/test_rag_controller.py`。
- [x] (2026-03-02 04:22Z) 增加集成测试 `tests/integration/test_rag.py`。
- [x] (2026-03-02 04:24Z) 修复 Litestar 启动时依赖签名解析的前向类型问题，`create_app()` 可成功创建应用。
- [x] (2026-03-02 04:33Z) 执行数据库迁移：`uv run app database upgrade`，升级到 `3d2a7f9e8b1c`。
- [x] (2026-03-05) 修复集成测试数据库解析逻辑，避免默认读取 `.env` 的开发库地址。
- [x] (2026-03-05) 跑通 `tests/integration/test_health.py` 与 `tests/integration/test_rag.py`。

## Surprises & Discoveries (惊喜与发现)

- 观察：`uv run app database upgrade` 默认进入交互确认，非 TTY 模式会中止。
  证据：
    Starting database upgrade process
    Are you sure you want migrate the database to the `head` revision? [y/n]:
    Aborted.

- 观察：Litestar 在应用启动时会解析依赖函数签名；仅 `TYPE_CHECKING` 下的前向类型可能触发 `NameError`。
  证据：
    NameError: name 'RagQueueService' is not defined

- 观察：初版集成测试适配为了绕过 `pytest-databases` 的 Docker 卡顿，错误地回退到 `.env` 的 `DATABASE_URL`，而测试 fixture 会直接 `drop_all/create_all`。
  证据：
    `tests/integration/conftest.py` 的 `_seed_db` 包含 `await conn.run_sync(metadata.drop_all)` 与 `await conn.run_sync(metadata.create_all)`。

- 观察：修正后，集成测试必须只读取显式的 `INTEGRATION_DATABASE_URL` 或 `TEST_DATABASE_URL`，否则回退到测试容器，不允许再默认吃开发库地址。
  证据：
    `tests/integration/conftest.py` 的 `_resolve_integration_database_url()` 仅检查环境变量和 `.env.testing` 的测试专用键。

## Decision Log (决策日志)

- 决策：RAG API 独立于现有 Todo Agent 对话入口。
  理由：降低首版耦合，先稳定“上传-索引-查询”闭环，再决定是否作为 Tool 接入 Agent。
  日期/作者：2026-03-02 / Codex

- 决策：索引采用异步队列（ARQ + Redis），Redis 不可用时请求失败，不降级同步。
  理由：避免请求路径被大文档索引阻塞，保持行为明确可预期。
  日期/作者：2026-03-02 / Codex

- 决策：删除文档后执行用户级重建（全量有效文档重建）。
  理由：保证索引一致性与严格过滤语义，避免增量删除带来的碎片与遗漏。
  日期/作者：2026-03-02 / Codex

- 决策：`document_id` 查询采用严格过滤（仅该文档 workspace）。
  理由：满足“严格不回退到其它文档”的产品要求。
  日期/作者：2026-03-02 / Codex

- 决策：查询复用现有月度配额体系 `RateLimitService + UserUsageQuotaService`。
  理由：减少新计费模型复杂度，保持一致的配额体验。
  日期/作者：2026-03-02 / Codex

- 决策：集成测试不再默认读取 `.env` 的 `DATABASE_URL`。
  理由：integration fixture 具备破坏性重建逻辑，必须只使用显式的测试库地址或测试容器。
  日期/作者：2026-03-05 / Codex

## Outcomes & Retrospective (结果与回顾)

已完成端到端核心能力：模型、迁移、配置、控制器、服务、队列、LightRAG 包装器、应用注册、单元测试、集成测试与静态检查。应用可启动，数据库已升级到 RAG 迁移版本，`tests/integration/test_health.py` 与 `tests/integration/test_rag.py` 已通过。后续如要继续演进，应优先把 RAG 接成 Agent Tool，并确保测试环境与开发数据库隔离策略持续生效。

## Context and Orientation (背景与导向)

本仓库是 Litestar 后端，主代码在 `src/app`。本次新增的核心文件：

- `src/app/domain/rag/controllers.py`：对外 HTTP 接口（上传/列表/删除/查询）。
- `src/app/domain/rag/services.py`：上传校验、持久化、索引重建、查询与引用片段提取。
- `src/app/domain/rag/queue.py`：ARQ 队列封装与 worker 生命周期。
- `src/app/domain/rag/lightrag_client.py`：LightRAG 适配层，管理用户/文档 workspace。
- `src/app/db/models/rag_document.py`：文档元数据表模型。
- `src/app/db/migrations/versions/2026-03-02_add_rag_document_3d2a7f9e8b1c.py`：数据库结构升级。
- `src/app/server/core.py`：挂载 `RagController` 与 `start_rag_worker/stop_rag_worker`。
- `src/app/config/base.py`：新增 RAG 与 provider 配置项。
- `tests/integration/conftest.py`：integration 测试数据库解析与重建逻辑。

术语定义：

- workspace：LightRAG 在磁盘上的索引工作目录（这里是每用户一个 `all`，每文档一个独立目录）。
- strict filter：传入 `document_id` 时只能使用该文档上下文，不允许回退其他文档。
- source citation：查询响应中的引用片段，包含文档标识、分片编号、片段文本。

## Plan of Work (工作计划)

先扩展配置与依赖，保证 provider、队列、存储路径可配置；再新增 `rag_document` 模型和迁移，确立数据边界。随后实现 `rag` 领域：控制器仅负责协议与异常映射，服务层负责业务规则，队列负责异步索引调度，`lightrag_client` 封装第三方库调用，避免控制器/服务直接耦合外部 API。最后把控制器和 worker 注册到应用核心，并补齐单元测试与集成测试。测试基建部分需要额外保证数据库隔离，不能复用开发库地址。

## Concrete Steps (具体步骤)

工作目录：`/home/harry/code/putian-ai-todo-back-end-litestar`

1. 安装并锁定依赖。
   命令：
     uv sync
   预期：`uv.lock` 包含 `lightrag-hku` 与 `openai>=2,<3`。

2. 执行数据库迁移。
   命令：
     uv run app database upgrade
   关键输出：
     Running upgrade 7b9c1d2e3f4a -> 3d2a7f9e8b1c, add rag document

3. 静态检查与类型检查。
   命令：
     uv run ruff check src/app/domain/rag
     uv run pyright src/app/domain/rag
   预期：无 error。

4. 运行新增单元测试与关键回归。
   命令：
     uv run pytest tests/unit/test_rag_service.py tests/unit/test_rag_controller.py --quiet
     uv run pytest tests/unit/test_todo_agents_controller.py --quiet
   预期：全部通过。

5. 运行集成测试。
   命令：
     uv run pytest tests/integration/test_health.py tests/integration/test_rag.py -q
   预期：通过；如果需要外部数据库，必须显式设置 `INTEGRATION_DATABASE_URL` 或 `TEST_DATABASE_URL`，不能依赖 `.env` 的开发库地址。

## Validation and Acceptance (验证与验收)

验收以行为为准：

1. 上传 `text/plain` 小文件到 `/api/rag/documents/upload`，HTTP 202 且返回 `status=queued`。
2. 请求 `/api/rag/documents` 可看到文档记录，状态字段存在且合法。
3. 删除 `/api/rag/documents/{id}` 后再次列表，该文档不应返回（已软删）。
4. 调用 `/api/rag/query` 返回 `answer` 与 `sources` 字段；传 `document_id` 时 `used_document_ids` 仅包含该文档或为空。
5. 应用启动成功（`create_app()` 不抛异常）。
6. 集成测试运行时不会默认指向 `.env` 中的开发库地址。

## Idempotence and Recovery (幂等性与恢复)

- 迁移命令可重复执行；已迁移版本会保持不变。
- 上传/删除为业务操作，允许重复请求但会产生新文档或“文档不存在”结果，属于预期行为。
- 若 RAG 队列不可用，请求会返回 503/失败状态，不会偷偷降级同步索引。
- 若索引失败，文档状态进入 `failed` 并保留错误信息；修复配置后可通过“删除+重建”或重新上传恢复。
- 若要跑 integration tests，优先使用专用测试库；不要把开发库地址写入 `INTEGRATION_DATABASE_URL` 或 `TEST_DATABASE_URL`。

## Artifacts and Notes (工件与笔记)

关键执行证据：

  uv run app database upgrade
  ...
  Running upgrade 7b9c1d2e3f4a -> 3d2a7f9e8b1c, add rag document

  uv run pytest tests/unit/test_rag_service.py tests/unit/test_rag_controller.py --quiet
  .... [100%]
  4 passed in 2.21s

  uv run pytest tests/integration/test_health.py tests/integration/test_rag.py -q
  ..... [100%]
  5 passed in 4.70s

  uv run python - <<'PY'
  from app.asgi import create_app
  create_app()
  print("app-created")
  PY
  app-created

## Interfaces and Dependencies (接口与依赖)

新增公共接口：

- `POST /api/rag/documents/upload`
- `GET /api/rag/documents`
- `DELETE /api/rag/documents/{document_id}`
- `POST /api/rag/query`

新增核心类型：

- `RagDocument`（ORM）
- `RagDocumentStatus`、`RagQueryRequest`、`RagQueryResponse`（Pydantic）
- `RagQueueService`（异步索引队列）
- `LightRagClient`（第三方库适配）

关键依赖与用途：

- `lightrag-hku`：执行 `ainsert/aquery` 的 RAG 引擎。
- `openai>=2,<3`：配合 LightRAG 的 OpenAI 兼容接口调用。
- `arq` + `redis`：索引异步任务队列与 worker。

Plan Update Note：2026-03-02 / Codex 创建初版，记录 RAG 纯文本上传、索引与查询的实现计划。
Plan Update Note：2026-03-05 / Codex 补充 integration 测试隔离修复与已通过的测试结果，并强调不得默认读取开发库地址。
