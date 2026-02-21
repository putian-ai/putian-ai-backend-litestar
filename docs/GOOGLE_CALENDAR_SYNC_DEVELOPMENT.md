# Google Calendar 双向同步开发指南

本文档聚焦本项目中 Google Calendar 的接入、双向同步、最小联调验证与排障，作为后续开发与运维的单点参考。

## 1. 目标与范围

- 目标：让本应用 Todo 与用户 Google Calendar 做双向同步。
- 当前范围：后端已具备连接管理、OAuth、手动同步、Webhook 入站、Todo CRUD 自动推送钩子；Electron 已提供“最小联调实验”入口。
- 非目标：本文不展开 CalDAV/ICS 细节，相关整体规划见 `.agents/exec-plans/calendar-sync-google-icloud-caldav.md`。

## 2. 当前架构（Google 专项）

- 后端作为同步中枢：负责 OAuth、token 管理、pull/push 编排、错误状态落库。
- Electron 目前只做最小验证：在设置页可创建连接、获取授权 URL、触发同步、查询镜像事件。
- 双向同步入口：
  - pull：`POST /api/calendar/connections/{connection_id}/sync`（`mode=pull|both`）
  - push：Todo 创建/更新/删除时自动触发（默认连接，且非 `pull_only`）

关键代码位置：

- 路由与接口：`src/app/domain/calendar_sync/controllers/calendars.py`
- 同步编排：`src/app/domain/calendar_sync/services.py`
- Google Provider：`src/app/domain/calendar_sync/providers/google.py`
- 数据模型：
  - `src/app/db/models/calendar_connection.py`
  - `src/app/db/models/calendar_event.py`
  - `src/app/db/models/todo_calendar_link.py`
- Electron 最小实验页：`electron-frontend/packages/renderer/src/pages/SettingsPage.tsx`

## 3. 数据模型速览

### 3.1 `calendar_connection`

- 连接主表（用户 + provider + 状态 + 凭据 + 同步游标）
- 关键字段：
  - `provider`: `google` / `caldav` / `ics`
  - `status`: `pending_auth` / `active` / `error` / `disabled`
  - `sync_mode`: `two_way` / `pull_only` / `push_only`
  - `credential_blob`: 使用 `EncryptedText`，加密密钥来自 `SECRET_KEY`
  - `sync_cursor`: Google 增量同步 token

### 3.2 `calendar_event`

- 外部事件镜像表（便于统一查询与前端渲染）
- 唯一约束：`(connection_id, remote_event_id)`
- `payload` 为 JSON，保存原始远端事件数据

### 3.3 `todo_calendar_link`

- Todo 与远端事件映射表
- 用于避免重复创建、支持更新/删除反查远端事件

## 4. Google OAuth 与同步时序

### 4.1 OAuth 授权链路

1. 创建 Google 连接（状态会是 `pending_auth`）  
   `POST /api/calendar/connections`
2. 获取授权链接  
   `GET /api/calendar/providers/google/authorize?connection_id=...`
3. 用户在浏览器授权，Google 回调：  
   `GET /api/calendar/providers/google/callback?code=...&state=...`
4. 回调成功后，后端把 token 写入 `credential_blob`，连接状态更新为 `active`

实现细节：

- `state` 使用 HMAC 签名并带过期时间（`GOOGLE_STATE_TTL_SECONDS`）
- 首次交换 token 后保存 `access_token`、`refresh_token`、`expires_at`

### 4.2 双向同步链路

- pull（Google -> 本地）：
  - Google `fetch_events`（支持 `syncToken` 增量）
  - upsert 到 `calendar_event`
  - 维护 `todo_calendar_link`
  - 必要时创建/更新/删除本地 Todo
- push（本地 -> Google）：
  - 遍历时间窗口内 Todo（或单 Todo 钩子）
  - `upsert_event` 到 Google
  - 更新映射和镜像

## 5. API 清单（Google 相关）

- `POST /api/calendar/connections`：创建连接（Google 可不传 `credentials`）
- `PATCH /api/calendar/connections/{connection_id}`：更新连接
- `GET /api/calendar/connections`：连接列表
- `DELETE /api/calendar/connections/{connection_id}`：删除连接
- `GET /api/calendar/providers/google/authorize`：获取授权 URL
- `GET /api/calendar/providers/google/callback`：Google OAuth 回调（免鉴权）
- `POST /api/calendar/connections/{connection_id}/sync`：手动同步
- `GET /api/calendar/events`：查询镜像事件
- `POST /api/calendar/webhooks/google`：Google Webhook 入站

## 6. 环境变量

后端 `.env` / `.env.local.example`：

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`（默认 `http://127.0.0.1:8089/api/calendar/providers/google/callback`）
- `GOOGLE_OAUTH_SCOPES`（默认 `["https://www.googleapis.com/auth/calendar"]`）
- `GOOGLE_STATE_TTL_SECONDS`（默认 `900`）
- `GOOGLE_WEBHOOK_TOKEN`
- `CALENDAR_SYNC_LOOKBACK_DAYS`（默认 `90`）
- `CALENDAR_SYNC_LOOKAHEAD_DAYS`（默认 `365`）

开发环境鉴权（无 JWT）：

- Header：`X-Dev-User-Id: <user_uuid>`
- Electron 可通过 `VITE_DEV_USER_ID` 自动注入该 header

## 7. 最小验证方法（后端 + Electron）

### 7.1 后端最小脚本（推荐先跑）

1. 启动基础环境与迁移

```bash
make start-infra
uv run app database upgrade
make dev
```

2. 创建 Google 连接

```bash
curl -sS -X POST "http://127.0.0.1:8089/api/calendar/connections" \
  -H "Content-Type: application/json" \
  -H "X-Dev-User-Id: <your_user_uuid>" \
  -d '{
    "provider":"google",
    "display_name":"Google Primary",
    "calendar_id":"primary",
    "sync_mode":"two_way",
    "is_default":true
  }'
```

3. 获取授权 URL，完成授权回调后执行同步

```bash
curl -sS "http://127.0.0.1:8089/api/calendar/providers/google/authorize?connection_id=<connection_id>" \
  -H "X-Dev-User-Id: <your_user_uuid>"
```

```bash
curl -sS -X POST "http://127.0.0.1:8089/api/calendar/connections/<connection_id>/sync" \
  -H "Content-Type: application/json" \
  -H "X-Dev-User-Id: <your_user_uuid>" \
  -d '{"mode":"both"}'
```

4. 查询事件镜像

```bash
curl -sS "http://127.0.0.1:8089/api/calendar/events" \
  -H "X-Dev-User-Id: <your_user_uuid>"
```

验收标准：

- `sync` 返回 `status=success`
- `calendar_event` 有对应记录
- 在 Google 日历侧可看到本地 Todo 推送事件

### 7.2 Electron 最小实验（设置页）

1. 启动 Electron 前端（示例）

```bash
cd electron-frontend
VITE_API_BASE_URL="http://127.0.0.1:8089" \
VITE_DEV_USER_ID="<your_user_uuid>" \
npm start
```

2. 进入设置页“日历同步最小联调实验”
3. 操作顺序：
   - Provider 选 `google`，创建连接
   - 点击“获取 Google 授权链接”，在系统浏览器完成授权
   - 回到应用点击“手动同步”
   - 点击“查询事件”，检查事件预览与最近响应 JSON

## 8. 已知问题与排障

### 8.1 Google 授权报 `invalid_request`（缺 `client_id`）

- 现象：Google 页面返回 400，提示缺少 `client_id`
- 根因：`GOOGLE_CLIENT_ID` 未配置或为空
- 处理：补齐 `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` 后重启后端

### 8.2 token 刷新报 `invalid_grant`

- 常见原因：用户撤销授权、refresh token 失效、OAuth 同意屏变更
- 处理：
  - 删除旧连接并重新授权
  - 检查 Google Cloud Console 中 OAuth 客户端与 redirect URI 是否一致

### 8.3 JSON 列写入异常（`\x01`）

- 历史问题：PostgreSQL `json`/`jsonb` codec 处理混用，导致 JSON 列解析失败
- 已修复：`src/app/config/base.py` 中分离 `json_encoder` 与 `jsonb_encoder`

### 8.4 同步异常后出现事务污染

- 历史问题：同步异常后会触发 `PendingRollbackError` 链式错误
- 已修复：`src/app/domain/calendar_sync/services.py` 增加 `_safe_session_rollback()`

### 8.5 同步耗时长，前端可能先显示失败

- 现状：在数据量大或网络慢时，`sync` 可能持续较久
- 建议：
  - 短期：前端先用 `mode=pull` 做小窗口验证
  - 中期：把同步改为后台任务 + 轮询状态（避免长请求阻塞 UI）

## 9. Webhook 现状与后续

- 当前已有入站端点：`POST /api/calendar/webhooks/google`
- 当前实现会校验 `x-goog-channel-token`，并按 `resource_id + channel_id` 反查连接
- 注意：当前代码尚未实现 Google watch channel 创建/续租流程，需要后续补齐

## 10. 安全与运维建议

- 禁止在仓库提交真实 OAuth 凭据
- 生产环境必须启用 HTTPS 回调地址
- `SECRET_KEY` 变更会影响历史 `credential_blob` 解密，需设计轮换策略
- 建议对同步结果打点监控：
  - `pull/push` 计数
  - `last_error` 频率
  - 单次同步耗时
