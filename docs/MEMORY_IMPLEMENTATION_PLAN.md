# Memory 功能实施计划书

## 1. 目标
- 引入可持久化的 Memory，用于增强多轮对话与跨场景一致性。
- 支持 **全局记忆（global）** 与 **用户记忆（per-user）** 两种粒度。
- 通过新的 Memory Agent，在主业务 Agent（如 TodoAgent）运行前后完成 **注入** 与 **总结更新**。
- 显式对齐 ACE（Agentic Context Engineering）框架，确保记忆更新可追踪、可迭代、可控。

## 2. 范围与非目标

### 范围
- 新增数据库模型 `Memory`，包含全局与用户级记忆。
- 新增 Memory Agent（或 Memory Service + Agent 组合），具备：
  - **前置加载**：在业务 Agent 执行前加载相关 Memory 并注入上下文。
  - **后置总结**：在业务 Agent 回复后总结并更新 Memory。
  - **分类更新**：区分 global / user / 双写。
- 接入 TodoAgent 与后续其他 Agent 的统一入口。
- API / 内部服务 / 工具链路调整。
- 测试与回滚策略。

### 非目标
- 不引入外部向量检索或语义检索系统。
- 不在本阶段实现跨项目/跨系统同步。
- 不进行产品界面改造（仅服务侧能力）。

## 3. 架构设计

### 3.1 Memory Agent 总览
Memory Agent 作为所有业务 Agent 的前后置“守门人”，包含两阶段：

1. **Pre-Run 注入**
   - 获取当前上下文（用户、会话、意图）。
   - 读取 Memory（global + user）。
   - 生成结构化 `memory_context` 注入到业务 Agent 的输入中。

2. **Post-Run 总结**
   - 读取业务 Agent 的最终回复与过程信息（必要时包含 tool 调用摘要）。
   - 生成 Memory 更新指令（global / user / both）。
   - 写入数据库，保留版本或更新时间。

### 3.2 调用链路（文字流程）

- 用户请求 → API Controller
- Controller 进入统一 Agent 入口（TodoAgentService 等）
- **Memory Agent Pre-Run**：加载 Memory → 生成上下文 → 传入业务 Agent
- 业务 Agent 执行（含工具调用）
- **Memory Agent Post-Run**：总结 & 更新 Memory
- 返回响应给用户

### 3.3 与现有 Agent 架构的关系
- Memory Agent 作为 **上层包装器**，对 TodoAgent 与其他 Agent 透明。
- 通过统一 service 入口实现，不影响各 agent 的业务逻辑。
- 只在入口层做依赖注入与后置总结，避免修改大量业务工具。

## 4. 数据模型与数据库迁移

### 4.1 Memory 模型（建议）
为与 ACE Playbook 的策略条目结构一致，建议以“Memory Bullet”为最小存储单元：

Bullet {
    id: UUID,
    is_global: bool,
    user_id: UUID | null,
    content: str,
    section: str,
    helpful_count: int,
    harmful_count: int,
    created_at: datetime,
    updated_at: datetime,
    metadata: dict
}

字段含义说明：
- `id`：Memory 唯一标识。
- `is_global`：是否为全局记忆。
- `user_id`：用户记忆归属；`is_global = false` 时必填。
- `content`：记忆内容（可为规则、偏好、总结）。
- `section`：记忆所属分类（如 \"preferences\"、\"scheduling\"、\"product_rules\"）。
- `helpful_count` / `harmful_count`：用于 ACE 的策略有效性统计。
- `created_at` / `updated_at`：创建与更新时间。
- `metadata`：扩展字段（来源、版本、标签等）。

边界说明：
- Memory 采用 Bullet 结构对齐 ACE 的策略条目，但不承载 Playbook 的分区管理逻辑。
- sections 的组织可以由应用层维护（如查询聚合），不要求在数据库层实现完整 Playbook 结构。

metadata 推荐字段：
- `source`：如 "summary" / "user_preference" / "system_rule"
- `version`：记忆版本号
- `tags`：自定义标签列表
- `scope_reason`：global 或 user 的归因说明

helpful/harmful 计数更新策略：
- Reflector 在 Post-Run 分析时给出条目级别的有效性判断。
- Curator 负责将判断转化为计数更新（如 helpful_count +1）。
- 仅在有明确反馈或规则触发时更新计数，避免无依据的频繁增减。

### 4.2 约束规则
- `is_global = true` 时：`user_id` 必须为空。
- `is_global = false` 时：`user_id` 必填。
- 可选唯一索引：
  - `(is_global, user_id, source)` 用于控制同类记忆覆盖策略。
- 数据库层应具备等价的检查约束，避免出现全局与用户字段冲突的数据。

### 4.3 迁移策略
- 新增表：`memory`。
- 加入必要索引与约束（检查约束或应用层校验）。
- 迁移脚本需记录清晰注释与回滚路径。

## 5. Memory Agent 设计细节

### 5.1 输入输出
- **输入**：用户请求、会话上下文、当前业务 Agent 选择。
- **输出**：
  - Pre-Run：`memory_context`（结构化文本或 JSON）
  - Post-Run：`memory_updates`（global/user/both 指令集）

### 5.2 更新策略
- 全局记忆（global）：
  - 适用于跨用户共享的规则、通用偏好或产品规则总结。
- 用户记忆（user）：
  - 适用于用户习惯、个性化偏好、长期安排模式。
- 双写（both）：
  - 同时更新 global + user 的通用与个性化两层。

### 5.3 冲突与覆盖策略
- 同一 `source` 可配置为覆盖或追加。
- 记录 `version` 或 `updated_at` 以便审计。
- 必要时保留“历史记录”并用软删除标记。

## 6. API / Service / Tool 调整

### 6.1 Service 层
- 在 `TodoAgentService`（及未来其他 Agent Service）增加 Memory Agent 前后置调用。
- 需要新增 `MemoryService`：
  - `list_global_memory()`
  - `list_user_memory(user_id)`
  - `upsert_memory(...)`

### 6.2 Agent 工具层
- 增加 Memory Agent 内部使用工具（如 `get_memory`, `update_memory`）。
- 不直接暴露给用户侧业务 Agent，防止绕过策略。

### 6.3 API 影响
- 主业务 API 不必变更字段，仅内部处理顺序调整。
- 当前阶段不新增对外端点，保持现有接口契约稳定。

## 7. ACE 框架映射

| ACE 角色 | 本项目 Memory 机制映射 | 职责说明 |
| --- | --- | --- |
| Generator | 业务 Agent（TodoAgent 等） | 根据 Memory + 当前上下文生成回应与动作 |
| Reflector | Memory Agent 的 Post-Run 分析逻辑 | 分析生成结果，识别可沉淀的记忆 |
| Curator | Memory Service + 更新策略 | 将分析结果转化为结构化 Memory 更新 |

执行链路：
- Generator 输出结果 → Reflector 分析 → Curator 产出 delta 更新 → 写入 Memory。

## 8. 测试策略

### 8.1 单元测试
- Memory 模型约束（global/user 规则）。
- Memory Service CRUD 与 upsert 覆盖。

### 8.2 集成测试
- TodoAgent 执行前后 Memory 读写链路。
- global/user/both 更新分支验证。

### 8.3 回归测试
- 现有 todo agent 流程不受影响。
- 流式与非流式对话保持一致行为。

## 9. 风险与缓解
- **风险：** Memory 注入导致 prompt 过长。
  - **缓解：** 限制注入条数或进行摘要压缩。
- **风险：** 更新策略不稳定导致记忆污染。
  - **缓解：** 引入 `source` 与版本控制，避免无序覆盖。
- **风险：** global 记忆不当影响所有用户。
  - **缓解：** 对 global 更新引入更严格条件或人工审核开关。

## 10. 回滚策略
- 可通过开关禁用 Memory Agent（前置注入与后置更新）。
- 保留 Memory 表但不读写，确保数据可恢复。
- 数据库回滚脚本移除 `memory` 表（谨慎执行）。

## 11. 里程碑拆分

1. **M1：数据模型与服务层**
   - 新增 `Memory` 模型与迁移
   - MemoryService 初始实现

2. **M2：Memory Agent 接入**
   - Pre-Run 注入流程
   - Post-Run 总结与更新流程

3. **M3：测试与稳定性**
   - 单测 + 集成测试覆盖
   - 性能评估与注入裁剪策略
   - 灰度开关与配置项落地，支持快速禁用
