# AI Agents 说明（产品视角）

本文档描述本项目 AI Agents 的能力边界、角色分工、会话与流式行为，以及对外 API 概览。

## 目标与能力概览
- AI Agent = 大模型 + 工具，负责理解用户意图并调用工具完成待办管理与时间安排。
- 重点能力：待办创建/更新/删除、日程分析、冲突避免、配额查询、会话记忆。
- 时间相关操作具备时区感知，面向“今天/明天/下周”等相对时间也可正确解析。

## 代理角色与分工
系统支持多种代理配置以满足不同场景：

- **TodoAssistant（默认）**：全功能代理，覆盖 CRUD + 日程分析 + 配额查询。
- **TodoCrudAssistant**：仅负责创建/更新/删除待办（写操作）。
- **TodoScheduleAssistant**：仅负责列出待办、分析日程与给出“规划方案”，不做任何写操作。
- **TodoSupportAssistant**：负责配额与账户状态类问题。
- **TodoOrchestratorAgent**：协调多个子代理的总控代理，适合复杂多意图请求。

关键约束：
- 日程规划与写入分离：规划由 Schedule 代理完成，写入必须由 CRUD 代理执行。
- 所有返回内容不暴露用户或待办的 UUID。

## 工具体系与能力边界
工具以功能分组，代理只暴露其职责范围内的工具：

- **通用工具**
  - `get_user_datetime`：获取用户时区当前时间，是所有时间相关操作的前置步骤。

- **待办写操作（CRUD）**
  - `create_todo`：创建待办，自动冲突检测。
  - `update_todo`：更新待办，变更时间会进行冲突检测。
  - `delete_todo`：删除待办。

- **日程分析与规划**
  - `get_todo_list`：读取待办列表。
  - `analyze_schedule`：分析日程空闲时段与冲突。
  - `schedule_todo`：自动排期（仅在全功能代理中提供）。
  - `batch_update_schedule`：批量调整排期（仅在全功能代理中提供）。

- **支持类工具**
  - `get_user_quota`：读取用户当月配额与使用情况。

## 记忆系统（Memory）
- 系统引入全局记忆（global）与用户记忆（user）两类 Memory，用于跨会话沉淀偏好与规则。
- Memory Agent 在业务 Agent 执行前注入相关记忆上下文，执行后基于结果总结并更新记忆。
- 记忆的读写为内部能力，当前不暴露新的对外 API 端点。
- Memory 更新通过 Redis 队列后台执行（ARQ Worker），避免阻塞对话响应；可通过 `MEMORY_QUEUE_*` 配置控制。

## 会话与历史
- 会话采用 Agents SDK 的 `SQLiteSession` 持久化，默认存储在 `conversations.db`。
- 传入 `session_id` 可复用历史；未传入时将自动生成。
- 会话列表接口仅返回当前进程内存中“活跃会话”。
- `agent-create` 接口会返回最近 10 条历史，便于 UI 展示上下文。

## API 端点概览
基础路径：`/api/todos`

- `POST /agent-create`：非流式对话，返回最终回复与最近历史。
- `POST /agent-create/stream`：流式对话，SSE 返回增量事件。
- `GET /agent-sessions`：列出当前用户的活跃会话。
- `POST /agent-sessions/new`：创建新会话并返回 `session_id`。
- `GET /agent-sessions/{session_id}/history`：获取指定会话历史（支持 `limit`）。
- `DELETE /agent-sessions/{session_id}`：清理指定会话历史。
- `GET /usage-stats`：获取配额与使用统计。

### 请求字段（示例）
非操作级示例，仅用于字段说明。

```json
{
  "messages": [
    {"role": "user", "content": "帮我安排明天上午 30 分钟的运动"}
  ],
  "session_id": "user_<id>_todo_agent",
  "agent_name": "TodoAssistant"
}
```

字段说明：
- `messages`：对话消息列表，服务仅使用最后一条用户消息作为本次输入。
- `session_id`：可选，复用会话历史；未提供会自动生成。
- `agent_name`：可选，指定代理（如 `TodoScheduleAssistant`）。

## 流式事件协议（SSE）
流式接口将按事件类型输出结构化数据：

- `session_initialized`：返回 `session_id`。
- `message_delta`：模型文本增量片段（`content`）。
- `message`：模型完整消息（`content`）。
- `tool_call`：工具调用信息（`tool_name`、`arguments`）。
- `tool_result`：工具执行结果（`output`）。
- `agent_updated`：代理切换（`name`）。
- `completed`：流式结束，包含 `final_message`。
- `history`：流式完成后返回会话历史（列表）。
- `error`：异常信息（`message`）。
- `rate_limit_exceeded`：超额提示（当前实现中流式未做扣费，后续启用时可能出现）。

## 配额与限流
- 非流式对话在进入 Agent 处理前会检查月度配额，超额直接返回错误响应。
- `get_user_quota` 工具可用于展示用户当月已用/剩余/重置时间。
- `GET /usage-stats` 提供当前月使用统计，便于产品侧展示额度状态。

## 典型产品流程
- **日程规划**：用户提出时间安排需求 → 调用 Schedule 代理生成规划 → 由 CRUD 代理确认并创建待办。
- **快速记录**：用户输入简单待办 → 由 TodoAssistant 直接创建，并自动避免时间冲突。
- **配额查询**：用户询问使用情况 → 由 Support 代理返回额度与剩余。
