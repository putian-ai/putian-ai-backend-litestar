# 优化任务清单深色模式可读性与交互

这份 ExecPlan 是一份动态文档。随着工作的进行，`Progress`、`Surprises & Discoveries`、`Decision Log` 和 `Outcomes & Retrospective` 章节必须保持更新。

本计划受仓库根目录下 `.agents/PLANS.md` 约束，必须按照该文件要求维护。

## Purpose / Big Picture (目的/大图景)

用户在任务清单页面的“近 7 天任务”与页面底部输入区域感到信息密度过高、对比度不足与排版混乱。本次变更将保持现有字体与配色，强化卡片内部的层级、行距与交互热区，并在卡片内提供摘要与展开内容的切换。完成后，用户能更快扫描任务摘要，展开查看细节列表，并在底部输入区域获得更清晰的输入边界与对齐体验。

## Progress (进度)

- [x] (2026-02-03 00:00) 读取任务清单页面与全局样式，确认改动范围。
- [x] (2026-02-03 02:03Z) 更新 `TodosPage` 的卡片结构、摘要/展开逻辑与标签布局。
- [x] (2026-02-03 02:03Z) 调整底部输入区的布局与控件样式，提升对齐与可读性。
- [x] (2026-02-03 02:03Z) 在 `index.css` 添加与页面使用的最小化工具类（行高、截断、列表、按钮命中区）。
- [ ] (2026-02-03 00:00) 手工验证深色模式下的阅读与交互体验。

## Surprises & Discoveries (惊喜与发现)

- 暂无。

## Decision Log (决策日志)

- 决策：保持现有字体与颜色 token 不变，仅通过布局与类名提升可读性。
  理由：用户明确要求不改字体与颜色，避免全局视觉回归。
  日期/作者：2026-02-03 / Codex
- 决策：在任务卡片内提供“摘要 + 展开”而不是跳转详情页。
  理由：用户要求卡片内展开，且任务清单需要快速浏览。
  日期/作者：2026-02-03 / Codex
- 决策：用轻量规则解析描述文本中的列表（基于换行或编号前缀）。
  理由：KISS 原则下提供最小可用的结构化展示。
  日期/作者：2026-02-03 / Codex

## Outcomes & Retrospective (结果与回顾)

- 待完成：实施后补充总结。

## Context and Orientation (背景与导向)

本仓库的 Electron 前端位于 `electron-frontend/`。任务清单页面在 `electron-frontend/packages/renderer/src/pages/TodosPage.tsx`，该页面包含“近 7 天任务”卡片列表与底部的标签管理/输入区域。全局主题与通用样式位于 `electron-frontend/packages/renderer/src/index.css`。本次变更只调整这两个文件（必要时新增最小 CSS 工具类），不引入新依赖，也不调整主题 token。

## Plan of Work (工作计划)

先在 `TodosPage.tsx` 增加描述文本的解析与展开状态，并重新组织任务卡片内部结构：标题、时间、重要程度、标签、描述、操作区分层展示，同时为描述添加行高与最多三行截断。之后优化底部输入区的网格布局与控件尺寸，确保输入框、按钮对齐，交互热区达标。最后在 `index.css` 增加必要的工具类（如 `app-clamp-3`、`app-text-list`、`app-btn-hit`），并确保这些类使用现有颜色变量。

## Concrete Steps (具体步骤)

1. 在工作目录中打开 `electron-frontend/packages/renderer/src/pages/TodosPage.tsx`，添加描述解析函数与展开状态；调整卡片布局与按钮区域；更新底部输入区布局与控件类名。
2. 打开 `electron-frontend/packages/renderer/src/index.css`，添加最小化工具类，确保仅影响使用到这些类的组件。
3. 运行前端开发服务器或预览（如需要），人工检查深色模式视觉。

示例命令（在仓库根目录执行）：
  - cd "electron-frontend/packages/renderer"
  - npm run dev

## Validation and Acceptance (验证与验收)

- 进入任务清单页面后，“近 7 天任务”卡片中的描述默认最多显示三行，存在溢出时显示“展开”，点击可在卡片内展开查看完整内容。
- 描述文本在深色模式下行距约为字号的 1.5 倍，段落不再紧贴。
- 标签与操作区分层展示，底部操作区有分隔线或视觉区隔，点击区域不小于 44px 的可用高度。
- 页面底部输入区（标签管理）控件对齐，输入框高度一致，文字清晰可读。

## Idempotence and Recovery (幂等性与恢复)

- 所有更改均为前端样式与组件结构调整，可重复执行而不影响数据。
- 若需要回退，可在 `TodosPage.tsx` 与 `index.css` 中撤销新增类名与结构调整，不会影响后端。

## Artifacts and Notes (工件与笔记)

- 预计会新增类似如下片段（示意，非完整代码）：
  - const [expandedTodos, setExpandedTodos] = useState<Record<string, boolean>>({})
  - <p className={isExpanded ? 'leading-relaxed' : 'app-clamp-3 leading-relaxed'}>...</p>
  - .app-clamp-3 { display: -webkit-box; -webkit-line-clamp: 3; ... }

## Interfaces and Dependencies (接口与依赖)

- 不新增第三方依赖。
- 使用现有的 React、HeroUI 组件与 `index.css` 中的 CSS 变量。

变更记录：2026-02-03 初始化计划，基于当前需求建立执行路线。
