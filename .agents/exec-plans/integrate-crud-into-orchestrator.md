# Integrate CRUD Tools Into TodoOrchestratorAgent

这份 ExecPlan 是一份动态文档。随着工作的进行，`Progress`、`Surprises & Discoveries`、`Decision Log` 和 `Outcomes & Retrospective` 章节必须保持更新。

本文档遵循仓库根目录的 `.agents/PLANS.md` 约束，并以其格式与要求为准。

## Purpose / Big Picture (目的/大图景)

用户将继续通过主代理 `TodoOrchestratorAgent` 获得完整待办能力，但不再依赖 `TodoCrudAssistant` 子代理。变更后，主代理直接调用 CRUD 工具完成写操作，减少代理跳转，提高一致性。可通过 API 使用 `agent_name=TodoOrchestratorAgent` 发起创建/更新/删除请求来验证新行为。

## Progress (进度)

- [x] (2026-02-02 00:00Z) 阅读 `docs/AGENT_TOOLS_ARCHITECTURE_GUIDE.md`，确认当前子代理与工具分工。
- [x] (2026-02-02 04:51Z) 更新 `src/app/domain/todo_agents/tools/agent_factory.py`，移除 CRUD 子代理并让主代理直接挂载 CRUD 工具。
- [x] (2026-02-02 04:51Z) 更新 `src/app/domain/todo_agents/tools/system_instructions.py`，移除 CRUD 子代理相关约束并改写主代理指令。
- [x] (2026-02-02 04:51Z) 更新 `src/app/domain/todo_agents/tools/__init__.py` 与导出列表，移除 CRUD 子代理导出。
- [x] (2026-02-02 04:51Z) 更新 `docs/AGENT_TOOLS_ARCHITECTURE_GUIDE.md`，反映主代理直接写入的能力与新的角色分工。
- [x] (2026-02-02 05:02Z) 在 `src/app/domain/todo_agents/tools/agent_factory.py` 添加 `get_todo_crud_agent` 兼容性 shim，避免遗留导入导致启动失败。
- [x] (2026-02-02 05:48Z) 进行最小验证（启动/请求或测试），确认 `TodoOrchestratorAgent` 可执行 CRUD。（已完成：导入/构建轻量验证 + 启动服务并通过 `/api/todos/agent-create` 成功创建待办）
- [x] (2026-02-02 05:53Z) 通过设置 `DOCKER_HOST` 重跑测试，确认集成测试通过（50 passed）。

## Surprises & Discoveries (惊喜与发现)

- 观察：运行 `uv run pytest tests -n 2 --quiet` 时，`pytest_databases` 在获取 Docker 上下文时抛出 `TypeError: list indices must be integers or slices, not str`，导致集成测试集体失败。
  证据：错误栈显示在 `.venv/lib/python3.13/site-packages/pytest_databases/_service.py:48`，`get_docker_host()` 解析 Docker 上下文失败。
- 观察：启动服务并请求时，Memory context 生成出现 `DeepseekException` 的 `response_format` 警告，但请求最终仍成功返回 201。
  证据：服务日志出现 `Memory context generation failed` 与 `invalid_request_error` 的提示。
- 观察：设置 `DOCKER_HOST=unix:///var/run/docker.sock` 后，测试全部通过。
  证据：`uv run pytest tests -n 2 --quiet` 输出 `50 passed`。

## Decision Log (决策日志)

- 决策：移除 `TodoCrudAssistant` 子代理构建与注册，由 `TodoOrchestratorAgent` 直接使用 CRUD 工具。
  理由：需求明确为“不需要 CRUD sub agent”，遵循 YAGNI，减少多代理切换。
  日期/作者：2026-02-02 / Codex
- 决策：保留 `get_todo_crud_agent` 名称作为兼容性 shim，返回 `get_orchestrator_agent`。
  理由：启动时报错显示存在遗留导入，提供最小兼容以避免 ImportError，同时不恢复 CRUD 子代理。
  日期/作者：2026-02-02 / Codex

## Outcomes & Retrospective (结果与回顾)

已移除 `TodoCrudAssistant` 子代理并让 `TodoOrchestratorAgent` 直接挂载 CRUD 工具，相关系统指令与文档已同步更新。验证阶段已完成导入/构建轻量验证、HTTP 请求创建待办成功，以及设置 `DOCKER_HOST` 后的完整集成测试通过。

## Context and Orientation (背景与导向)

本项目为 Litestar 后端，AI Agents 位于 `src/app/domain/todo_agents/`。`src/app/domain/todo_agents/tools/agent_factory.py` 负责构建各代理与工具集合。当前 `TodoOrchestratorAgent` 通过 “agent-as-tools” 模式把子代理（CRUD、Schedule、Support）暴露为工具。所谓“子代理”，是指被包装为工具供主代理调用的 Agent 实例。`src/app/domain/todo_agents/tools/system_instructions.py` 定义各代理的系统指令（prompt 规则）。`docs/AGENT_TOOLS_ARCHITECTURE_GUIDE.md` 描述产品视角的能力与角色分工。此次变更要移除 `TodoCrudAssistant` 子代理，但保留 Schedule 与 Support 子代理。

## Plan of Work (工作计划)

先修改 `src/app/domain/todo_agents/tools/agent_factory.py`：删除 `get_todo_crud_agent` 与其在 `__all__`、`builders` 中的注册，并在 `get_orchestrator_agent` 中去掉 CRUD 子代理工具，改为直接追加 CRUD FunctionTools（来自 `get_crud_tool_definitions`，避免重复添加 `get_user_datetime`）。随后在 `src/app/domain/todo_agents/tools/system_instructions.py` 删除 `TODO_CRUD_INSTRUCTIONS` 常量及其导出，并重写 `ORCHESTRATOR_SYSTEM_INSTRUCTIONS` 与 `TODO_SCHEDULE_INSTRUCTIONS` 中关于 “必须使用 CRUD 子代理” 的约束，改为 “主代理可直接调用 CRUD 工具完成写入，Schedule 仅提供规划建议”。再更新 `src/app/domain/todo_agents/tools/__init__.py`，移除 CRUD 子代理的导出与 re-export。最后更新 `docs/AGENT_TOOLS_ARCHITECTURE_GUIDE.md` 中的角色分工与典型流程描述，确保文档与实现一致。

## Concrete Steps (具体步骤)

在仓库根目录执行以下命令（使用双引号包裹路径）：

1) 查看并编辑 `agent_factory.py`，移除 CRUD 子代理并在主代理中追加 CRUD 工具。

    rg -n "TodoCrudAssistant|get_todo_crud_agent" "./src/app/domain/todo_agents/tools/agent_factory.py"

2) 编辑 `system_instructions.py`，移除 CRUD 指令常量与子代理相关文本。

    rg -n "CRUD|TodoCrudAssistant" "./src/app/domain/todo_agents/tools/system_instructions.py"

3) 更新 `tools/__init__.py` 导出列表。

    rg -n "get_todo_crud_agent|TodoCrudAssistant" "./src/app/domain/todo_agents/tools/__init__.py"

4) 更新文档 `docs/AGENT_TOOLS_ARCHITECTURE_GUIDE.md` 的角色分工、关键约束与典型流程。

    rg -n "TodoCrudAssistant|CRUD" "./docs/AGENT_TOOLS_ARCHITECTURE_GUIDE.md"

## Validation and Acceptance (验证与验收)

行为验收优先于内部结构。完成后执行以下任一验证即可：

- 方式 A（推荐）：启动服务并发起一次创建待办请求，指定 `agent_name=TodoOrchestratorAgent`，确认成功创建且响应不包含 UUID。

    工作目录：仓库根目录
    命令：
      make dev

    另起终端调用 API（示例路径，不要泄露敏感数据）：
      curl -X POST "http://127.0.0.1:8089/api/todos/agent-create" -H "Content-Type: application/json" -d '{"messages":[{"role":"user","content":"明天上午 9:00 创建一个 30 分钟的会议"}],"agent_name":"TodoOrchestratorAgent"}'

    预期：返回成功消息，Todo 被创建，且响应不包含 todo/user UUID。

- 方式 B（可选）：运行测试（若项目具备相关测试覆盖）。

    uv run pytest tests -n 2 --quiet

## Idempotence and Recovery (幂等性与恢复)

本次变更为代码与文档编辑，可重复执行且不会产生副作用。若某一步执行后出现异常，可回到相同文件进行调整。若需要恢复，使用版本控制回退相关文件的修改。

## Artifacts and Notes (工件与笔记)

在执行完成后，记录关键 diff 片段或验证输出片段，保持简短，例如：

    - agent_factory.py 移除 TodoCrudAssistant 构建与注册，主代理追加 CRUD tools
    - system_instructions.py 删除 CRUD 子代理约束文本
    - docs/AGENT_TOOLS_ARCHITECTURE_GUIDE.md 更新角色分工与流程描述

## Interfaces and Dependencies (接口与依赖)

- `agents.Agent` 与 `agents.FunctionTool`：主代理构建与工具定义均依赖此接口。
- `src/app/domain/todo_agents/tools/tool_definitions.py`：提供 CRUD 工具集合（`get_crud_tool_definitions`）。
- `src/app/domain/todo_agents/tools/agent_factory.py`：本次变更的核心入口，负责组装主代理工具。

---
注：本计划于 2026-02-02 创建，用于将 CRUD 功能从子代理合并到主代理并同步更新文档，原因是需求明确不再需要 CRUD 子代理。
注：2026-02-02 追加测试失败记录与进度说明，用于标记验证受阻原因。
注：2026-02-02 追加导入/构建、HTTP 请求与重跑测试记录，说明验证已完成。
