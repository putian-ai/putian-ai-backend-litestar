# 让 Memory 更新进入 Redis 队列并后台处理

这份 ExecPlan 是一份动态文档。随着工作的进行，`Progress`、`Surprises & Discoveries`、`Decision Log` 和 `Outcomes & Retrospective` 章节必须保持更新。

本 ExecPlan 必须按照 ".agents/PLANS.md" 进行维护与修订。

## Purpose / Big Picture (目的/大图景)

当前 Memory Agent 的更新逻辑在请求线程内同步执行，导致对话返回时间被 LLM 调用拖慢。此次变更将 Memory 更新改为“入队 → 后台执行”，使用户可以更快收到对话回复，同时 Memory 仍会在后台完成更新。用户可见的效果是：同样的对话请求，响应更快返回；随后 Memory 仍能在下一次对话中生效（最终一致）。

## Progress (进度)

- [x] (2026-01-09 02:40Z) 创建 ExecPlan 初版，确认方案为 Redis + ARQ。
- [x] (2026-01-09 02:54Z) 集成 Redis 队列配置与依赖，新增 Memory 队列服务。
- [x] (2026-01-09 02:54Z) 启动 ARQ Worker 与应用生命周期集成。
- [x] (2026-01-09 02:54Z) TodoAgentService 改为异步入队并提供失败回退。
- [x] (2026-01-09 02:54Z) 新增单元测试与文档说明，完成验收准备。

## Surprises & Discoveries (惊喜与发现)

暂无。

## Decision Log (决策日志)

- 决策：使用 ARQ 作为 Redis 队列实现，并在同一进程启动 Worker。
  理由：ARQ 与 async 架构契合、依赖轻量、支持重试与超时控制，满足“单进程 + 可靠性 + 最终一致”。
  日期/作者：2026-01-09 / Codex

- 决策：当入队失败时回退为同步执行 Memory 更新。
  理由：避免 Redis 或网络短暂异常导致 Memory 更新永久丢失，提升可靠性。
  日期/作者：2026-01-09 / Codex

## Outcomes & Retrospective (结果与回顾)

尚未开始。

## Context and Orientation (背景与导向)

本项目为 Litestar 后端。当前 Memory 更新在 `src/app/domain/todo_agents/services.py` 的 `_update_memory_after_response` 中同步调用 `MemoryAgentService.update_memory_after_response`。`MemoryAgentService` 在 `src/app/domain/memory/agent_service.py` 中通过 `Runner.run(...)` 进行 LLM 调用，因此会阻塞请求。此计划将引入 Redis 队列与 ARQ Worker，将 Memory 更新放入队列异步处理。

术语说明：
- Redis：内存键值数据库，用于做任务队列的持久化存储。
- ARQ：Async Redis Queue，一个基于 asyncio 的 Redis 任务队列库，包含 job enqueue 与 worker 执行。
- Worker：后台任务执行器，它会从 Redis 队列取出任务并执行。
- 最终一致：请求返回时不等待后台任务完成，但任务最终会被执行完成。

## Plan of Work (工作计划)

先引入 ARQ 与 Redis 连接依赖，并增加队列配置项。然后新增 Memory 队列服务与 ARQ Worker 定义，用于把 Memory 更新任务入队并在后台执行。接着在 Litestar 生命周期中启动/停止 Worker（单进程模式），并在 `TodoAgentService` 中把 Memory 更新改为入队执行，失败时回退同步调用。最后补齐测试与文档，提供可观察的验证方式。

## Concrete Steps (具体步骤)

在工作目录 "/home/harry/code/putian-ai-todo-back-end-litestar" 中执行：

1) 增加依赖与锁文件更新。
   运行：
     uv add arq redis
   预期：`pyproject.toml` 与 `uv.lock` 更新，包含 `arq` 与 `redis` 依赖。

2) 添加 Redis 队列配置项。
   编辑 `src/app/config/base.py` 的 `AISettings`：
   - `MEMORY_QUEUE_ENABLED` (bool, 默认 True)
   - `MEMORY_QUEUE_URL` (str, 默认 "redis://localhost:6379/0")
   - `MEMORY_QUEUE_NAME` (str, 默认 "memory_updates")
   - `MEMORY_QUEUE_MAX_RETRIES` (int, 默认 3)
   - `MEMORY_QUEUE_JOB_TIMEOUT` (int, 秒，默认 120)
   - `MEMORY_QUEUE_WORKER_ENABLED` (bool, 默认 True)

3) 新增 Memory 队列与 Worker。
   创建 `src/app/domain/memory/queue.py`，包含：
   - `MemoryQueueService`：负责创建 Redis 连接池（lazy 或启动时连接），并提供 `enqueue_memory_update(user_id: UUID, user_message: str, agent_response: str) -> bool`。
   - `process_memory_update(ctx, user_id: str, user_message: str, agent_response: str)`：ARQ job 函数，内部创建数据库 session、构造 `MemoryService` 与 `MemoryAgentService`，调用 `update_memory_after_response`。
   - `MemoryWorkerSettings`：ARQ worker 配置，包含 `functions`、`redis_settings`、`max_retries`、`job_timeout`。
   - 明确 session 创建方式：使用 `settings.db.get_engine()` 与 `async_sessionmaker` 创建 `AsyncSession`。

4) 集成应用生命周期启动 Worker。
   编辑 `src/app/server/core.py`：
   - 在 `on_app_init` 中追加 `app_config.on_startup` 与 `app_config.on_shutdown` 回调。
   - `on_startup`：如果 `MEMORY_QUEUE_ENABLED` 且 `MEMORY_QUEUE_WORKER_ENABLED`，启动 ARQ Worker（后台 asyncio task）并存入 `app.state`。
   - `on_shutdown`：优雅关闭 Worker 与 Redis 连接。
   备注：需要确认 Litestar `on_startup` 的回调签名（通常 `async def func(app)` 或 `async def func()`），实现前应在本地查看 Litestar 类型或文档源码。

5) TodoAgentService 改为入队更新。
   编辑 `src/app/domain/todo_agents/services.py`：
   - 构造函数新增 `memory_queue_service: MemoryQueueService | None`。
   - `_update_memory_after_response` 优先调用队列 `enqueue_memory_update(...)`，成功则返回；入队失败记录日志并回退同步 `MemoryAgentService.update_memory_after_response`。
   - `create_todo_agent_service` 与依赖注入同步更新。

6) 依赖注入与服务提供。
   - 在 `src/app/domain/memory/deps.py` 增加 `provide_memory_queue_service`，复用单例或缓存实例。
   - 在 `src/app/domain/todo_agents/deps.py` 中注入 `memory_queue_service` 到 `create_todo_agent_service`。

7) Docker 与文档更新。
   - 在 `docker-compose.yml` 增加 `redis` 服务（默认端口 6379）。
   - 在 `docs/AGENT_TOOLS_ARCHITECTURE_GUIDE.md` 或项目 README 增加 Memory Queue 配置说明与启动方式。

## Validation and Acceptance (验证与验收)

1) 单元测试：
   - 新增 `tests/unit/test_memory_queue_service.py`：验证入队函数被调用并返回成功（可用 monkeypatch 替换 Redis enqueue）。
   - 新增 `tests/unit/test_todo_agent_memory_queue.py`：验证 `_update_memory_after_response` 优先入队，入队失败时回退同步调用。

2) 手动验收：
   - 启动 Redis（docker compose）。
   - 启动应用并发起对话请求。预期对话响应快速返回，日志显示 Memory 更新任务已入队。
   - 等待后台任务执行完成，再发起下一次对话，观察 Memory 生效。

## Idempotence and Recovery (幂等性与恢复)

- 队列入队是幂等的业务层调用，若重复入队同一任务会导致重复更新；因此在任务中应保持可重复性（当前 Memory 更新逻辑允许重复执行但可能增加计数）。
- 若 Redis 不可用，系统应自动回退同步更新（保证不丢任务）。
- 如需回滚：将 `MEMORY_QUEUE_ENABLED=false`，并移除 ARQ 依赖与相关代码改动。

## Artifacts and Notes (工件与笔记)

示例日志（成功入队）：
  Memory update enqueued {"user_id": "...", "job_id": "..."}

## Interfaces and Dependencies (接口与依赖)

新增依赖：
- `arq`：ARQ Redis 队列实现
- `redis`：Redis asyncio 客户端

新增/修改接口：
- `src/app/domain/memory/queue.py`:
  - `class MemoryQueueService`
  - `async def enqueue_memory_update(user_id: UUID, user_message: str, agent_response: str) -> bool`
  - `async def process_memory_update(ctx, user_id: str, user_message: str, agent_response: str) -> None`
  - `class MemoryWorkerSettings`
- `src/app/domain/todo_agents/services.py`:
  - `TodoAgentService.__init__(..., memory_queue_service: MemoryQueueService | None = None)`
  - `_update_memory_after_response(...)` 使用队列优先
- `src/app/domain/todo_agents/deps.py`：注入 `memory_queue_service`
- `src/app/config/base.py`：新增 `AISettings` 队列配置项
- `docker-compose.yml`：增加 Redis 服务

Plan Update Note：2026-01-09 02:40Z 创建初版计划，确定使用 ARQ + Redis，并采用“入队失败回退同步更新”的策略。
Plan Update Note：2026-01-09 02:54Z 标记实现进度完成，补充队列集成、Worker 生命周期、测试与文档更新记录。
