# OpenAPI TS 客户端生成接入到 Electron 前端

这份 ExecPlan 是一份动态文档。随着工作的进行，`Progress`、`Surprises & Discoveries`、`Decision Log` 和 `Outcomes & Retrospective` 章节必须保持更新。

本 ExecPlan 必须遵循仓库内 `.agents/PLANS.md` 的要求。

## Purpose / Big Picture (目的/大图景)

这次变更将把后端暴露的 OpenAPI 规范转成可在 Electron 前端直接调用的 TypeScript API 客户端。完成后，前端开发者可以在 `electron-frontend/packages/renderer` 中直接导入生成的 API 方法并获得类型提示，而无需手写请求。可见效果是运行生成脚本后会出现新的 `generated` 目录，并且 TypeScript 能识别生成的类型。

## Progress (进度)

- [x] (2026-01-12 23:10Z) 确认 OpenAPI 规范可访问并记录实际 URL。
- [x] (2026-01-12 23:11Z) 配置并安装 `@hey-api/openapi-ts` 与 `@hey-api/client-fetch` 依赖。
- [x] (2026-01-12 23:16Z) 创建 `openapi-ts` 配置与运行时配置文件。
- [x] (2026-01-12 23:18Z) 运行生成脚本并提交生成产物。
- [x] (2026-01-12 23:20Z) 验证生成结果可被前端编译识别。

## Surprises & Discoveries (惊喜与发现)

- 观察：`openapi-ts` CLI 不支持 `--config` 参数，会自动加载根目录的 `openapi-ts.config.ts`。
  证据：执行 `openapi-ts --config "openapi-ts.config.ts"` 报错 `unknown option '--config'`。
- 观察：`runtimeConfigPath` 会被直接写入生成文件的 import 语句，需写成相对生成目录的路径。
  证据：初次生成的 `client.gen.ts` 使用了非相对路径的 import。
- 观察：`@hey-api/client-fetch` 已被并入 `@hey-api/openapi-ts`，无需额外安装运行时依赖。
  证据：移除依赖后生成与构建均正常。

## Decision Log (决策日志)

- 决策：使用 `@hey-api/client-fetch` 作为客户端实现，并将生成输出放在 `electron-frontend/packages/renderer/src/api/generated`。
  理由：Renderer 运行在浏览器环境，原生 `fetch` 可用且依赖最少；输出路径与手写代码隔离，避免生成清理误删自定义代码。
  日期/作者：2026-01-12 / Codex
- 决策：`runtimeConfigPath` 使用 `../client-config.ts` 作为相对生成目录的导入路径。
  理由：生成的 `client.gen.ts` 会直接使用该字符串作为 import 源，需确保相对路径可解析。
  日期/作者：2026-01-12 / Codex
- 决策：移除 `@hey-api/client-fetch` 依赖，保留 `@hey-api/openapi-ts` 作为生成器。
  理由：当前版本已内置 fetch 客户端，减少依赖并避免 deprecated 警告。
  日期/作者：2026-01-12 / Codex

## Outcomes & Retrospective (结果与回顾)

已完成 OpenAPI TS 接入与生成流程，生成产物可被 `@app/renderer` 构建识别。当前仍未添加任何调用示例或 UI 层使用，这与 YAGNI 一致；后续若需要可在实际功能开发时补充。

## Context and Orientation (背景与导向)

本仓库包含后端与 Electron 前端。前端位于 `electron-frontend/`，并采用 npm workspaces。`electron-frontend/packages/renderer` 是 React 渲染进程包，使用 Vite 构建。我们需要把后端提供的 OpenAPI 规范（一个描述 HTTP API 的 JSON 文件）转换成 TypeScript 客户端代码。

关键路径如下：

1. `electron-frontend/package.json`：前端 workspace 根配置与脚本定义位置。
2. `electron-frontend/packages/renderer/package.json`：渲染进程依赖配置位置。
3. `electron-frontend/openapi-ts.config.ts`：OpenAPI TS 生成配置文件（将被新建）。
4. `electron-frontend/packages/renderer/src/api/client-config.ts`：客户端运行时配置（将被新建）。
5. `electron-frontend/packages/renderer/src/api/generated/`：生成代码输出目录（将被新建并提交）。

术语说明：

- OpenAPI：用 JSON/ YAML 描述 HTTP API 的标准格式，包含端点、参数与返回类型。
- 客户端生成器：读取 OpenAPI 规范并生成可直接调用的 TypeScript API 代码的工具。
- Renderer：Electron 中渲染进程（浏览器环境），在本仓库对应 `packages/renderer`。

## Plan of Work (工作计划)

首先确认后端 OpenAPI JSON 可访问，避免生成阶段失败。然后在 `electron-frontend/` 根目录引入 `@hey-api/openapi-ts` 作为生成器，并在 `packages/renderer` 中引入 `@hey-api/client-fetch` 作为运行时依赖。随后创建 `openapi-ts` 配置文件，指定输入 URL、输出目录与运行时配置文件路径，并明确使用渲染进程的 `tsconfig.app.json`。接着创建运行时配置文件，用 Vite 环境变量设置 `baseUrl`，默认指向 `http://127.0.0.1:8089`。最后运行生成脚本并检查生成产物，确保 TypeScript 可以解析生成类型并提交到版本库。

## Concrete Steps (具体步骤)

1. 验证 OpenAPI 规范可访问（在 `electron-frontend/` 之外也可执行）：  
   工作目录：仓库根目录  
   命令：  
     curl "http://127.0.0.1:8089/schema/openapi.json"
   预期：输出为 JSON，且包含 `"openapi"` 字段。

2. 在 `electron-frontend/` 根目录安装生成器依赖，并将其固定为精确版本：  
   工作目录：`electron-frontend/`  
   命令：  
     npm install -D -E @hey-api/openapi-ts

3. 在 `electron-frontend/packages/renderer` 安装运行时依赖：  
   工作目录：`electron-frontend/`  
   命令：  
     npm install -E -w "@app/renderer" @hey-api/client-fetch

4. 新建 `electron-frontend/openapi-ts.config.ts`，配置输入 URL、输出目录、tsconfig 与 `client-fetch` 插件，并将 `runtimeConfigPath` 设置为 `../client-config.ts`（相对生成目录）。

5. 新建 `electron-frontend/packages/renderer/src/api/client-config.ts`，实现 `createClientConfig`，设置 `baseUrl`。使用 `import.meta.env.VITE_API_BASE_URL`，若未提供则回退到 `http://127.0.0.1:8089`。

6. 在 `electron-frontend/package.json` 添加脚本（例如 `openapi`），直接调用 `openapi-ts`（CLI 自动读取 `openapi-ts.config.ts`）。

7. 运行生成脚本并提交生成产物：  
   工作目录：`electron-frontend/`  
   命令：  
     npm run openapi

8. 校验生成产物存在，确认有 `client.gen.ts`、`types.gen.ts` 等文件出现在 `electron-frontend/packages/renderer/src/api/generated/`。

## Validation and Acceptance (验证与验收)

验收标准：

1. `npm run openapi` 执行成功，生成目录存在且包含生成的 `.gen.ts` 文件。
2. 在 `electron-frontend/packages/renderer` 运行 `npm run build` 不应因生成文件或类型而失败。
3. 任意 TypeScript 文件可以从生成目录导入类型（例如 `types.gen`）并通过类型检查。

## Idempotence and Recovery (幂等性与恢复)

`npm run openapi` 可重复执行，输出目录将被重新生成；自定义运行时配置文件在输出目录外，不会被覆盖。若生成失败，请先确认后端 OpenAPI URL 可访问，再重试生成命令。若依赖安装失败，可删除 `electron-frontend/package-lock.json` 后重新执行 `npm install`，但需要重新确认所有依赖版本。

## Artifacts and Notes (工件与笔记)

生成前后可以记录输出示例（缩进表示）：
  > client.gen.ts
  > types.gen.ts

## Interfaces and Dependencies (接口与依赖)

依赖：

- `@hey-api/openapi-ts`：OpenAPI 客户端生成器（dev dependency，安装在 `electron-frontend/` 根目录）。
- `@hey-api/client-fetch`：运行时 fetch 客户端（dependency，安装在 `electron-frontend/packages/renderer`）。

接口：

- `createClientConfig`（在 `packages/renderer/src/api/client-config.ts`）：返回包含 `baseUrl` 的运行时配置对象，供生成客户端读取。

---

变更记录：初版计划创建，覆盖依赖安装、配置文件与生成流程。
变更记录：补充 CLI 无 `--config` 参数与 `runtimeConfigPath` 的相对路径要求，并更新进度状态。
变更记录：移除 `@hey-api/client-fetch` 依赖与新增 `.env.example`，并记录发现。
