# 实现 Memory Agent 与双层记忆存储

这份 ExecPlan 是一份动态文档。随着工作的进行，`Progress`、`Surprises & Discoveries`、`Decision Log` 和 `Outcomes & Retrospective` 章节必须保持更新。

本 ExecPlan 必须按照 ".agents/PLANS.md" 进行维护与修订。

## Purpose / Big Picture (目的/大图景)

本变更让系统具备跨会话的“记忆”，用户可以被长期记住偏好与习惯（用户记忆），同时系统也能沉淀全局规则（全局记忆）。实现后，用户在一次对话中表达的偏好会影响后续安排，例如“我更喜欢早上安排运动”，在之后的自动排期中会被优先遵循。可观察的效果包括：同一用户多次对话后，回应内容开始引用之前的偏好；数据库中存在可追踪的 Memory Bullet 记录。

## Progress (进度)

- [x] (2025-12-22 14:45Z) 创建 ExecPlan 初版并确认范围。
- [x] (2025-12-22 15:20Z) 完成 Memory 数据模型与迁移。
- [x] (2025-12-22 15:20Z) 完成 MemoryService 与依赖注入。
- [x] (2025-12-22 15:20Z) 完成 Memory Agent（上下文生成与更新）与服务编排。
- [x] (2025-12-22 15:20Z) 将 Memory Pipeline 接入 TodoAgentService（含流式与非流式）。
- [x] (2025-12-22 15:20Z) 新增测试与验证步骤，更新相关文档说明。

## Surprises & Discoveries (惊喜与发现)

- 观察：SQLAlchemy Declarative 禁止使用属性名 `metadata`，导致 Memory 模型初始化失败。
  证据：单元测试收集阶段报错 `InvalidRequestError: Attribute name 'metadata' is reserved`，已改为 `metadata_json` 并映射列名 `metadata`。
- 观察：Postgres 不接受 `boolean = integer` 的 CHECK 约束表达式。
  证据：迁移执行时报错 `UndefinedFunctionError: operator does not exist: boolean = integer`，已改为 `IS TRUE/FALSE` 表达式。
- 观察：开发环境启动时报 `MemoryService` 未解析，需补充签名命名空间注册。
  证据：启动日志中出现 `NameError: name 'MemoryService' is not defined`，已在 `src/app/server/core.py` 注册。
- 观察：示例脚本含转义字符导致语法错误。
  证据：`examples/dev_e2e_httpx.py` 报 `SyntaxError`，已修正 f-string 语法。

## Decision Log (决策日志)

- 决策：Memory 数据结构采用 ACE 的 Bullet 结构作为最小存储单元。
  理由：与 `ace-docs/ACE-REQUIREMENTS.md` 的策略条目对齐，便于映射 helpful/harmful 统计与增量更新。
  日期/作者：2025-12-22 / Codex

- 决策：Memory Agent 使用结构化输出（Pydantic output_type）生成上下文与更新计划，而不是直接暴露更新工具给业务 Agent。
  理由：避免业务 Agent 绕过策略，便于测试替身（stub）并控制更新逻辑。
  日期/作者：2025-12-22 / Codex

- 决策：Memory 注入通过“克隆 Agent 并追加 instructions”完成；若克隆不可用则退化为输入列表追加 system message。
  理由：避免把 Memory 上下文写入对话历史，保持 session 干净且可控。
  日期/作者：2025-12-22 / Codex

- 决策：模型属性改为 `metadata_json` 并映射到列名 `metadata`。
  理由：SQLAlchemy Declarative 保留字冲突，需保持数据库字段名同时避免运行时异常。
  日期/作者：2025-12-22 / Codex

- 决策：CHECK 约束使用 `IS TRUE/FALSE` 布尔表达式。
  理由：确保 Postgres 兼容性，避免 `boolean = integer` 类型错误。
  日期/作者：2025-12-22 / Codex

- 决策：在 Litestar 的签名命名空间中显式注册 `MemoryService`。
  理由：依赖注入解析 forward reference 需要类型可见，避免启动时报错。
  日期/作者：2025-12-22 / Codex

## Outcomes & Retrospective (结果与回顾)

尚未开始。完成主要里程碑后记录成果、遗留问题与经验总结。

## Context and Orientation (背景与导向)

本仓库的核心结构如下：数据库模型在 "src/app/db/models"；迁移脚本在 "src/app/db/migrations/versions"；业务服务在 "src/app/domain"；Todo Agent 的实现集中于 "src/app/domain/todo_agents"；Agent 工具与指令在 "src/app/domain/todo_agents/tools"；API 入口在 "src/app/domain/todo_agents/controllers/todo_agents.py"；依赖注入在 "src/app/domain/todo_agents/deps.py" 与 "src/app/server/core.py"。

术语定义（面向新手）：
- Agent：由大语言模型（LLM）驱动、带指令和工具的对话执行者。在本仓库中主要通过 `agents.Agent` 创建。
- Tool：Agent 可调用的函数或工具定义，用于执行数据库操作或系统动作。当前在 "src/app/domain/todo_agents/tools" 中定义。
- Session：对话历史的持久化载体。这里使用 Agents SDK 的 `SQLiteSession`（见 "src/app/domain/todo_agents/services.py"）。
- SSE：Server-Sent Events，一种服务端推送机制，用于流式对话输出（见 `agent_create_todo_stream`）。
- Migration：数据库结构变更脚本，使用 Alembic/Advanced Alchemy 体系生成与执行（见 "src/app/db/migrations/versions"）。
- Memory Bullet：与 ACE Playbook 条目对应的记忆单元，含内容、分类与有效性统计。
- 全局记忆（global）：对所有用户通用的记忆，`is_global = true` 且 `user_id` 为空。
- 用户记忆（user）：仅对单一用户生效的记忆，`is_global = false` 且 `user_id` 指向用户。
- 结构化输出：Agent 通过 `output_type` 输出符合 Pydantic 模型结构的数据，便于后续处理。

ACE 关键概念（内嵌说明）：
- Generator（生成者）：产出最终答复的业务 Agent（如 TodoAgent）。
- Reflector（反思者）：对生成结果做分析，判断哪些信息值得沉淀。
- Curator（策划者）：将反思结果转成可落库的增量更新（ADD/UPDATE/TAG/REMOVE）。

## Plan of Work (工作计划)

先构建 Memory 数据模型与服务层，确保有稳定的读写与约束基础，再引入 Memory Agent 的上下文生成与更新流程，最后接入 TodoAgentService 的前后置管线并补齐测试。全程通过小步可验证的增量推进：每完成一层就运行对应测试或脚本验证，确保变更可演示且可回滚。

## Milestones (里程碑)

### Milestone 1：数据模型与服务层落地

目标是新增 Memory 表、迁移脚本与 MemoryService。完成后应能在数据库中创建并查询 Memory Bullet（含 global 与 user）。里程碑验证通过：运行迁移后可以插入一条 user memory 并读取，且约束生效。

### Milestone 2：Memory Agent 与 Pipeline 接入

目标是新增 Memory Agent（上下文生成 + 更新计划），并将其作为 TodoAgentService 的前后置流程。完成后应能在非流式与流式对话中调用 Memory Pipeline，生成可用于注入的上下文并在对话后更新 Memory。

### Milestone 3：测试与演示

目标是通过单元测试与集成测试验证 Memory 逻辑，补充文档说明并提供可演示的效果（例如用户偏好影响后续排期）。完成后应能通过测试或手动运行看到记忆生效。

## Concrete Steps (具体步骤)

在工作目录 "/home/harry/code/putian-ai-todo-back-end-litestar" 中执行或编辑以下内容。所有命令中的路径均以双引号标注。

第一步是定位现有模式与可复用结构，避免重复设计。建议先查看相似模型与服务：
    rg -n "class AgentSession" "src/app/db/models/agent_session.py"
    rg -n "class Todo" "src/app/db/models/todo.py"
    rg -n "SQLAlchemyAsyncRepositoryService" "src/app/domain/todo/services.py"
    rg -n "TodoAgentService" "src/app/domain/todo_agents/services.py"

然后新增 Memory 模型文件 "src/app/db/models/memory.py"，实现 `Memory` 类（继承 `UUIDAuditBase`），包含：
- `is_global` (Boolean, nullable=False, default=False)
- `user_id` (ForeignKey("user_account.id"), nullable=True)
- `content` (Text, nullable=False)
- `section` (String, nullable=False)
- `helpful_count` / `harmful_count` (Integer, nullable=False, default=0)
- `metadata` (JSON, nullable=False, default=dict)
- 索引与检查约束（`is_global` 与 `user_id` 的互斥规则）

同步更新 "src/app/db/models/__init__.py" 导出 `Memory`，必要时在 "src/app/db/models/user.py" 增加 `memories` 关系（允许 `user_id` 为空，避免 innerjoin）。

生成迁移脚本（若 CLI 支持）：
    uv run app database --help
    uv run app database revision --autogenerate -m "add memory bullets"

如 CLI 不支持 `revision`，则在 "src/app/db/migrations/versions" 手动创建迁移文件，参考最近的迁移命名与结构，确保包含 `memory` 表创建与检查约束。随后执行：
    uv run app database upgrade

新增 MemoryService：创建 "src/app/domain/memory/services.py"，使用 `SQLAlchemyAsyncRepositoryService`，提供 `list_global_memory()`、`list_user_memory(user_id)`、`list_effective_memory(user_id)` 与 `apply_memory_deltas(deltas, user_id)`（支持 ADD/UPDATE/TAG/REMOVE 与 scope=global/user/both）。在 "src/app/domain/memory/deps.py" 添加 `provide_memory_service` 依赖注入。

新增 Memory Agent 数据结构与指令：
- 在 "src/app/domain/memory/schemas.py" 定义 `MemoryDeltaAction`、`MemoryScope`、`MemoryDelta`、`MemoryContextResult`、`MemoryUpdateResult`（使用 `PydanticBaseModel`）。
- 在 "src/app/domain/memory/system_instructions.py" 写入两套指令：一套用于“生成 Memory 上下文”，一套用于“生成更新计划”。指令中要求区分 global / user / both，并输出结构化字段。

新增 Memory Agent 工厂与服务：
- 在 "src/app/domain/memory/agent_factory.py" 提供 `get_memory_context_agent()` 与 `get_memory_update_agent()`，统一使用同一 LLM 配置（参照 "src/app/domain/todo_agents/tools/agent_factory.py" 的 `_get_model()`）。
- 在 "src/app/domain/memory/agent_service.py" 实现 `MemoryAgentService`，对外暴露 `build_memory_context(...)` 与 `update_memory_after_response(...)`。服务内部读取 MemoryService，调用 Memory Agent 产出结构化结果，并将更新计划应用到数据库。

接入 TodoAgentService：
- 修改 "src/app/domain/todo_agents/services.py" 构造函数，新增 `memory_agent_service`（或 `memory_service` + `memory_agent` 组合）。
- 在 `chat_with_agent` 中，在 `Runner.run` 之前调用 `build_memory_context`；将结果以追加 instructions 或 system message 的方式注入到 agent；在 `Runner.run` 之后调用 `update_memory_after_response`。
- 在 `stream_chat_with_agent` 中，启动流式前完成 Memory 注入；流式结束后使用 `final_message` 调用 `update_memory_after_response`；若 `final_message` 为空或异常事件发生则跳过更新。

更新依赖注入：
- 在 "src/app/domain/todo_agents/deps.py" 为 `provide_todo_agent_service` 增加 `memory_agent_service` 入参，并使用新的工厂函数构造。
- 若需要在控制器签名中显式使用 MemoryService 类型，则在 "src/app/server/core.py" 的 `signature_namespace` 中新增 `MemoryService`。

配置开关（灰度/回滚）：
- 在 "src/app/config/base.py" 的 `AISettings` 中新增 `MEMORY_ENABLED` 与 `MEMORY_MAX_BULLETS`（用于控制注入长度）。
- 在 MemoryAgentService 中读取该配置，若关闭则直接跳过注入与更新。

补充测试：
- 新增 "tests/unit/test_memory_service.py" 覆盖 `apply_memory_deltas` 与 global/user 逻辑。
- 新增 "tests/unit/test_memory_agent_service.py" 使用 stubbed Memory Agent 输出，验证上下文与更新应用逻辑。
- 新增 "tests/unit/test_todo_agent_memory_pipeline.py" 对 `TodoAgentService` 注入过程做顺序验证（可用 monkeypatch 替换 `Runner.run`，断言 MemoryAgentService 被调用）。

更新文档（可选但推荐）：
- 在 "docs/AGENT_TOOLS_ARCHITECTURE_GUIDE.md" 增加 Memory Agent 的角色与流程概述，确保产品/研发对齐。

## Validation and Acceptance (验证与验收)

测试命令（可逐步执行）：
    uv run pytest "tests/unit/test_memory_service.py" --quiet
    uv run pytest "tests/unit/test_memory_agent_service.py" --quiet
    uv run pytest "tests/unit/test_todo_agent_memory_pipeline.py" --quiet

预期结果：每个命令输出包含 “X passed”，且无失败。

手动演示（需要已配置 LLM 与数据库）：
- 启动服务后发起两次对话。第一次告诉偏好（例如“以后安排运动优先早上”），第二次请求排期（例如“帮我安排运动”）。
- 预期第二次回复体现“早上优先”的偏好。
- 同时可在数据库中查询 `memory` 表，看到新增的 user memory bullet。

## Idempotence and Recovery (幂等性与恢复)

迁移脚本可重复执行（`upgrade` 幂等）；若迁移失败，先确认数据库版本表状态，再重新执行。若需要回滚，优先关闭 `MEMORY_ENABLED` 以停用流程，再执行数据库降级（若 CLI 支持）：
    uv run app database downgrade -1

如果降级命令不可用，需手动移除迁移并删除 `memory` 表（谨慎执行），并确保代码中禁用 Memory Pipeline 以避免访问不存在的表。

## Artifacts and Notes (工件与笔记)

Memory Context 示例（用于注入到 Agent 的 instructions）：
    MEMORY CONTEXT:
      - [user] 偏好：早上安排运动
      - [global] 规则：避免安排在 12:00-13:00

Memory Update 结构示例（来自 Memory Agent 的结构化输出）：
    deltas:
      - action: ADD
        scope: user
        section: preferences
        content: "偏好早上安排运动"
        metadata: {source: "summary", tags: ["schedule"], scope_reason: "user stated preference"}
      - action: TAG
        scope: global
        target_id: "<existing-uuid>"
        helpful_delta: 1

## Interfaces and Dependencies (接口与依赖)

新增或变更的关键接口包括：
- "src/app/db/models/memory.py"：`class Memory(UUIDAuditBase)`，字段见数据模型定义。
- "src/app/domain/memory/services.py"：`class MemoryService`，提供 `list_global_memory`, `list_user_memory`, `list_effective_memory`, `apply_memory_deltas`。
- "src/app/domain/memory/schemas.py"：`MemoryDeltaAction`, `MemoryScope`, `MemoryDelta`, `MemoryContextResult`, `MemoryUpdateResult`。
- "src/app/domain/memory/agent_factory.py"：`get_memory_context_agent()`, `get_memory_update_agent()`。
- "src/app/domain/memory/agent_service.py"：`class MemoryAgentService`，方法 `build_memory_context(...)` 与 `update_memory_after_response(...)`。
- "src/app/domain/todo_agents/services.py"：`TodoAgentService` 新增 memory pipeline 依赖与调用顺序。
- "src/app/domain/todo_agents/deps.py"：`provide_todo_agent_service` 增加 Memory 依赖注入。
- 配置项：`AISettings.MEMORY_ENABLED`, `AISettings.MEMORY_MAX_BULLETS`。

Plan Update Note：2025-12-22 14:45Z 创建初版，基于 Memory 需求与 ACE 结构要求整理。
Plan Update Note：2025-12-22 15:20Z 标记完成核心实现与测试项，记录当前进度。
Plan Update Note：2025-12-22 15:30Z 记录 metadata 保留字修正与测试通过情况。
Plan Update Note：2025-12-26 15:30Z 记录迁移 CHECK 约束的 Postgres 兼容性修正。
Plan Update Note：2025-12-22 16:10Z 记录启动依赖修正与 E2E 脚本语法修复。
