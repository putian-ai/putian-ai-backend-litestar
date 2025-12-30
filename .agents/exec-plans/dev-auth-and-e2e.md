# 开发模式自动注入用户与 E2E 脚本

这份 ExecPlan 是一份动态文档。随着工作的进行，`Progress`、`Surprises & Discoveries`、`Decision Log` 和 `Outcomes & Retrospective` 章节必须保持更新。本文档必须遵循 `.agents/PLANS.md` 的要求并持续维护。

## Purpose / Big Picture (目的/大图景)

开发模式下，开发者可以在不登录的情况下访问需要认证的 API，并且仍然拥有一个真实的 `current_user` 对象用于数据库关联。与此同时，提供一个可执行的端到端（E2E，end-to-end：从客户端发起请求到服务端完成业务并返回响应）脚本，用最小成本验证开发环境下的核心 API 流程（创建、读取、更新、删除 Todo）。成功后，开发者只需启动服务并运行脚本，即可看到完整流程通过。

## Progress (进度)

- [x] (2025-12-26 14:36Z) 完成现状梳理、方案选择与 ExecPlan 编写。
- [x] (2025-12-26 14:40Z) 实现开发模式自动注入用户的认证中间件逻辑，并接入现有认证配置。
- [x] (2025-12-26 14:43Z) 增加开发模式 E2E 脚本并完成接入。
- [x] (2025-12-26 14:46Z) 补充开发用户 verified_at 的一致性更新。
- [x] (2025-12-26 15:40Z) 修复 E2E 更新接口调用并完成本地验证。

## Surprises & Discoveries (惊喜与发现)

- 观察：当前认证流程在缺失 JWT 时会直接拒绝请求，因此无法通过仅设置 `current_user` 依赖来绕过认证。
  证据：`OAuth2PasswordBearerAuth` 使用 `JWTCookieAuthenticationMiddleware`，其 `authenticate_request` 在没有 header/cookie 时抛出未授权异常。
- 观察：`PATCH /todos/{id}` 在开发 E2E 中返回 500。
  证据：服务端报错 `SQLAlchemyAsyncRepositoryService.update() got an unexpected keyword argument 'item'`，原因是控制器使用了错误的 update 调用方式。

## Decision Log (决策日志)

- 决策：新增一个自定义的 `JWTCookieAuthenticationMiddleware` 子类，在 `APP_ENV=development` 且请求未携带 token 时自动注入开发用户。
  理由：保持现有 JWT 流程不变，只在开发环境缺少 token 时启用兜底逻辑，改动面小，且不影响生产安全性。
  日期/作者：2025-12-26 / Codex
- 决策：Todo 更新接口使用 `update(item_id=..., data=...)` 形式调用服务层。
  理由：Advanced Alchemy 的 `update()` 不接受字段关键字参数，确保与服务层签名一致。
  日期/作者：2025-12-26 / Codex

## Outcomes & Retrospective (结果与回顾)

已完成：开发模式认证绕过与 E2E 脚本均可运行；本地验证通过完整 CRUD 流程。后续如需要可添加更多用例（如标签与筛选）。

## Context and Orientation (背景与导向)

本项目使用 Litestar 的 JWT 认证流程。`src/app/domain/accounts/guards.py` 中定义了 `auth = OAuth2PasswordBearerAuth`，该配置会注入认证中间件（middleware，中间件：位于 ASGI 请求进入路由处理前的处理组件）并在请求缺少 JWT（JSON Web Token，一种签名的身份令牌）时拒绝访问。应用路由在 `src/app/server/core.py` 中组装，依赖注入通过 `current_user` 传递用户模型。Todo API 位于 `src/app/domain/todo/controllers/todos.py`，创建、列表、更新、删除都依赖 `current_user`，因此必须在认证阶段确保用户存在。开发模式由 `make dev` 设置 `APP_ENV=development` 标识。

## Plan of Work (工作计划)

首先在 `src/app/config/base.py` 的 `AppSettings` 中新增 `ENV` 字段以读取 `APP_ENV` 环境变量。然后在 `src/app/domain/accounts/guards.py` 添加一个自定义认证中间件类（继承 `JWTCookieAuthenticationMiddleware`），当请求没有携带 token 且 `APP_ENV=development` 时，从数据库获取或创建一个固定的开发用户（邮箱 `dev@local.test`，姓名 `Development User`，`is_active=True`，`is_verified=True`）。若用户已存在但状态不符合上述要求，则更新其状态以保证开发模式可用。随后返回 `AuthenticationResult(user=dev_user, auth=None)`。在 `auth = OAuth2PasswordBearerAuth` 初始化时指定该中间件类为 `authentication_middleware_class`，从而替换默认中间件行为。最后新增一个开发模式 E2E 脚本 `examples/dev_e2e_httpx.py`，使用 `httpx` 直接访问运行中的 API，执行健康检查与 Todo CRUD 流程，确保无需登录即可完成操作。

## Concrete Steps (具体步骤)

在仓库根目录执行以下命令与验证（使用开发模式）：

1. 启动服务（开发模式）：
   - `make dev`
2. 运行 E2E 脚本：
   - `uv run python examples/dev_e2e_httpx.py`

预期输出示例（缩进仅示意）：
    ✔ health ok (200)
    ✔ create todo ok (201)
    ✔ list todos ok (200)
    ✔ update todo ok (200)
    ✔ delete todo ok (200)

## Validation and Acceptance (验证与验收)

验收标准应可观察且可重复：

- 在 `APP_ENV=development` 下启动服务，未携带 Authorization 头的 `GET /todos` 返回 200 且能读取到列表（即 `current_user` 成功注入）。
- 运行 `examples/dev_e2e_httpx.py`，脚本完整执行并以成功状态结束，且创建的 Todo 能在后续更新/删除中被正确识别。

## Idempotence and Recovery (幂等性与恢复)

开发用户的创建应是幂等的：如果用户已存在则直接复用。E2E 脚本应在结束时删除创建的 Todo，因此可以重复执行而不污染数据。如果脚本中途失败，可手动通过 `DELETE /todos/{id}` 清理残留。要关闭自动注入行为，只需将 `APP_ENV` 设置为非 `development` 值或使用 `make run` 启动生产模式。

## Artifacts and Notes (工件与笔记)

关键接口与响应示例（缩进示意）：
    POST /todos
    {
      "item": "dev e2e",
      "description": "created by dev e2e script",
      "start_time": "2025-12-26T14:00:00+00:00",
      "end_time": "2025-12-26T15:00:00+00:00",
      "importance": "none"
    }

    200/201 响应包含：
    {
      "id": "<uuid>",
      "item": "dev e2e",
      ...
    }

## Interfaces and Dependencies (接口与依赖)

需要新增或调整的接口与依赖如下：

- `src/app/config/base.py`：在 `AppSettings` 中新增 `ENV: str`，读取 `APP_ENV`。
- `src/app/domain/accounts/guards.py`：新增 `DevJWTCookieAuthenticationMiddleware` 与 `_get_or_create_dev_user`；在 `auth = OAuth2PasswordBearerAuth(...)` 中设置 `authentication_middleware_class` 为该中间件。
- `examples/dev_e2e_httpx.py`：新增开发模式 E2E 脚本；依赖 `httpx`（项目已有依赖）。
- `dev@local.test`：开发用户的固定邮箱，用于创建或复用用户记录。

文档最后更新：2025-12-26，创建 ExecPlan 并确定实现路径。

更新记录：2025-12-26 — 标记已完成开发模式认证中间件与 E2E 脚本的实现进度，并补充开发用户 verified_at 一致性更新。
