# 开发模式 Header 鉴权与 E2E 脚本

这份 ExecPlan 是一份动态文档。随着工作的进行，`Progress`、`Surprises & Discoveries`、`Decision Log` 和 `Outcomes & Retrospective` 章节必须保持更新。本文档必须遵循 `.agents/PLANS.md` 的要求并持续维护。

## Purpose / Big Picture (目的/大图景)

开发模式下，开发者在不登录的前提下访问需要认证的 API，但必须显式指定用户身份。方案使用 `X-Dev-User-Id` 请求头传递用户 UUID，在 `APP_ENV=development` 且请求无 JWT 时，由中间件将该用户解析为 `current_user`。同时维护一个可执行的 E2E 脚本验证 Todo CRUD 主流程。

## Progress (进度)

- [x] (2025-12-26 14:36Z) 完成首次方案梳理与 ExecPlan 编写。
- [x] (2025-12-26 14:40Z) 完成开发模式认证中间件初版实现（旧版：固定用户注入）。
- [x] (2025-12-26 14:43Z) 增加开发模式 E2E 脚本并完成接入。
- [x] (2025-12-26 15:40Z) 修复 E2E 更新接口调用并完成本地验证。
- [x] (2026-02-21 00:00Z) 切换为 `X-Dev-User-Id` 方案，移除固定用户自动创建逻辑。
- [x] (2026-02-21 00:00Z) 更新 E2E 脚本为强制 `DEV_E2E_USER_ID`。
- [x] (2026-02-21 00:00Z) 补充集成测试覆盖 dev header 认证路径。

## Surprises & Discoveries (惊喜与发现)

- 观察：JWT 中间件在缺失 token 时会直接拒绝请求，必须在认证中间件层面提供开发模式分支，不能仅靠依赖注入解决。
  证据：`OAuth2PasswordBearerAuth` 使用 `JWTCookieAuthenticationMiddleware`，`authenticate_request` 在没有 header/cookie 时抛出未授权异常。
- 观察：固定用户自动注入会导致“默认登录态”，不满足“dev 模式需显式 user_id”目标。
  证据：旧实现在 `APP_ENV=development` 且无 token 时直接创建/复用 `dev@local.test` 并放行请求。

## Decision Log (决策日志)

- 决策：开发模式免鉴权改为 header 显式指定用户：`X-Dev-User-Id`。
  理由：避免隐式登录态，用户身份可控、可追踪，且不影响生产认证路径。
  日期/作者：2026-02-21 / Codex
- 决策：`X-Dev-User-Id` 缺失、格式错误、用户不存在或用户不可用（非 active/verified）统一返回 401。
  理由：行为一致、失败即显式，不回退固定用户，避免掩盖配置问题。
  日期/作者：2026-02-21 / Codex

## Outcomes & Retrospective (结果与回顾)

已完成：开发模式认证从“自动注入固定用户”切换到“header 指定用户”；E2E 脚本与文档已同步更新；新增集成测试覆盖关键分支。当前行为满足“dev 模式免授权但需 user_id”目标。

## Context and Orientation (背景与导向)

本项目使用 Litestar JWT 认证。`src/app/domain/accounts/guards.py` 中的 `auth = OAuth2PasswordBearerAuth` 会注册认证中间件，路由通过 `current_user` 依赖使用认证用户。Todo API 位于 `src/app/domain/todo/controllers/todos.py`，所有核心操作都依赖 `current_user` 进行用户隔离。开发模式由 `make dev` 设置 `APP_ENV=development`。

## Plan of Work (工作计划)

在 `src/app/domain/accounts/guards.py` 保留原 JWT 流程优先级：有 token 则继续走 JWT；无 token 且 `APP_ENV=development` 时读取 `X-Dev-User-Id`。中间件将 header 解析为 UUID 并查询用户，要求用户存在且 `is_active/is_verified` 均为真；否则返回 401。`examples/dev_e2e_httpx.py` 调整为必填 `DEV_E2E_USER_ID` 并自动附加 `X-Dev-User-Id`，确保脚本可复现实验路径。补充集成测试验证 development/production 行为边界。

## Concrete Steps (具体步骤)

在仓库根目录执行以下命令与验证：

1. 启动服务（开发模式）：
   - `make dev`
2. 运行 E2E 脚本（指定开发用户）：
   - `DEV_E2E_USER_ID=<existing_user_uuid> uv run python examples/dev_e2e_httpx.py`
3. 运行集成测试（可选）：
   - `uv run pytest tests/integration/test_dev_auth.py -q`

预期输出示例（缩进仅示意）：
    ✔ health ok (200)
    ✔ create todo ok (201)
    ✔ list todos ok (200)
    ✔ update todo ok (200)
    ✔ delete todo ok (200)

## Validation and Acceptance (验证与验收)

验收标准应可观察且可重复：

- `APP_ENV=development` + 无 JWT + 无 `X-Dev-User-Id`：请求返回 401。
- `APP_ENV=development` + 无 JWT + 合法 `X-Dev-User-Id`：`GET /todos` 返回 200。
- 非 development 环境下：仅提供 `X-Dev-User-Id` 不可绕过 JWT，仍返回 401。
- E2E 脚本在提供 `DEV_E2E_USER_ID` 后可完整通过 CRUD。

## Idempotence and Recovery (幂等性与恢复)

该方案不再自动创建开发用户，数据库不会因认证绕过逻辑新增用户记录。E2E 脚本在成功路径会删除创建的 Todo，可重复执行。如脚本中途失败，可手动调用 `DELETE /todos/{id}` 清理残留。

## Artifacts and Notes (工件与笔记)

关键 header 约定：

    X-Dev-User-Id: <uuid>

关键错误行为：

    401 Unauthorized
    detail: Missing or invalid X-Dev-User-Id header for development authentication.

## Interfaces and Dependencies (接口与依赖)

需要调整的接口与依赖如下：

- `src/app/domain/accounts/guards.py`：
  - 新增 `DEV_USER_ID_HEADER = "X-Dev-User-Id"`。
  - 开发模式分支由 `_get_dev_user_from_header` 解析用户，不再 `_get_or_create_dev_user`。
- `examples/dev_e2e_httpx.py`：
  - 新增 `DEV_E2E_USER_ID` 必填校验。
  - 请求默认携带 `X-Dev-User-Id` header。
- `tests/integration/test_dev_auth.py`：
  - 新增 development/production 下 dev header 鉴权路径回归用例。

文档最后更新：2026-02-21，切换到 header 指定用户方案并完成配套更新。

