● ACE框架机制与实现思路

  1. 核心设计理念

  ACE (Agentic Context Engineering) 框架基于三个协作的智能体角色，通过持续的学习循环来改进AI系统的表现：

  Generator → 环境执行 → Reflector → Curator → Playbook更新 → Generator
      ↑                                                        ↓
      ←←←←←←←←←←←←← 改进的上下文/策略 ←←←←←←←←←←←←←←←←←

  2. 三角色协作机制

  Generator (生成者)

  - 职责: 使用当前playbook生成答案
  - 输入: 问题 + 上下文 + playbook + 反思信息
  - 输出: 推理过程 + 最终答案 + 使用的策略ID列表
  - 关键特性: 引用playbook中的具体策略，实现可追踪的决策

  Reflector (反思者)

  - 职责: 分析Generator的表现，识别成功/失败因素
  - 输入: Generator轨迹 + 环境反馈 + 标准答案 + 相关策略
  - 输出: 错误分析 + 根本原因 + 关键洞见 + 策略分类标签
  - 关键特性: 将具体策略标记为helpful/harmful/neutral

  Curator (策划者)

  - 职责: 将反思转化为具体的知识更新
  - 输入: Reflector分析 + 当前playbook + 任务上下文
  - 输出: Delta操作序列 (ADD/UPDATE/TAG/REMOVE)
  - 关键特性: 智能去重、原子性操作、上下文感知

  3. Playbook知识结构

  数据模型

  Playbook {
      bullets: Dict[id, Bullet],
      sections: Dict[section_name, List[bullet_ids]]
  }

  Bullet {
      id: str,
      content: str,
      section: str,
      helpful_count: int,
      harmful_count: int,
      created_at: datetime,
      metadata: dict
  }

  Delta更新机制

  - ADD: 添加新的策略条目
  - UPDATE: 修改现有策略内容
  - TAG: 更新helpful/harmful计数
  - REMOVE: 删除有害策略

  4. 两种适应模式

  OfflineAdapter (离线学习)

  for epoch in range(epochs):
      for sample in training_data:
          Generator → 环境评估 → Reflector → Curator → 更新playbook
  - 多轮次训练数据
  - 批量更新，适合模型预训练

  OnlineAdapter (在线学习)

  while 有新样本:
      Generator → 环境评估 → Reflector → Curator → 立即更新playbook
  - 实时学习，适合生产环境
  - 即时适应新任务模式

  5. 实现架构思路

  模块化设计

  ace/
  ├── roles.py          # 三角色实现
  ├── playbook.py       # 知识存储与更新
  ├── delta.py          # 增量操作定义
  ├── adaptation.py     # 学习循环编排
  ├── llm.py           # LLM抽象接口
  └── prompts.py       # 角色提示模板

  LLM抽象层

  - 统一的LLMClient接口
  - 支持多种后端 (OpenAI, Anthropic, 本地模型等)
  - 自动重试和错误处理
  - 可观测性集成 (Opik追踪)

  结构化提示工程

  - JSON格式约束输出
  - 内置重试机制
  - 多语言支持的错误提示
  - 版本化提示模板 (v1.0 → v2.1)

  6. 关键技术创新

  可追踪的决策

  - Generator显式引用使用的策略ID
  - Reflector基于具体使用策略进行反馈
  - 形成完整的决策因果链

  渐进式知识进化

  - 基于统计的策略优胜劣汰
  - 原子性更新，支持回滚
  - 智能去重避免知识冗余



Reference #file:WIKI_TOC.md , read docs if you need in #file:docs 