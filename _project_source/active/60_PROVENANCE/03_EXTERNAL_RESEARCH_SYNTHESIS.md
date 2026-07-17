---
title: 外部架构研究综合
status: ACTIVE
authority: PROVENANCE
version: 1.0
prepared_at: 2026-07-16
last_verified: 2026-07-16
authority_scope: external_architecture_principles_and_species_compatibility
implementation_authority: false

---

# 外部架构研究综合

外部资源不是 Furina Code 的器官清单，而是用于提取原则、发现冲突和压力测试内部设计的“其他物种样本”。

## 1. 生命与认知理论

| 范式 | 可提取原则 | 不能照搬 |
|---|---|---|
| Active Inference | 内部状态维持、行动与预测误差形成闭环 | 不能把单一优化目标替代用户方向和关系责任 |
| Enactive cognition | 意义通过主体与环境互动生成 | 不能以抽象“具身”掩盖真实项目证据 |
| Interoceptive AI | 系统需要感知自身资源、风险和不确定状态 | 内部信号不能自证现实或正确性 |
| Embodied lifelong learning | 行动和长期经验共同塑造行为 | 相似度或奖励不能自动获得授权 |
| Generative agents | 记忆、反思和计划可维持社会连续性 | 文本记忆不等于持续主体或责任 |
| Constitutional AI | 原则可以约束模型输出 | 模型宪法不能替代用户主权和本地强制 Gate |

## 2. 工程范式

| 范式 | 可提取原则 | Furina Code 替换逻辑 |
|---|---|---|
| Temporal Event History | 追加历史、确定性恢复、活动与决定分离 | 项目现实必须重新观察；副作用不能盲目 replay |
| LangGraph persistence/interrupt | checkpoint、稳定运行标识、暂停恢复 | graph/thread 不是持续自我，节点恢复不能直接重写项目 |
| W3C SCXML | 状态、事件和转换语义明确 | 不采用语法即权威，任务意义仍来自用户和正式对象 |
| MCP | Host 管理连接、权限和工具边界 | 协议不是授权/完成权威，工具会话不是正式任务 |
| Git porcelain/diff | 机器可读项目事实 | Git 只覆盖版本化现实，不覆盖环境、用户方向和运行结果 |
| NIST ABAC | 授权绑定主体、对象、动作和环境 | 用户授权不是企业属性之一，不能被策略降格 |
| OPA | 判断与执行分离 | 策略引擎不拥有事实、用户授权来源或完成裁决 |
| SLSA / in-toto | 来源、材料、步骤和产物谱系 | 来源真实不等于功能正确或满足用户目标 |
| OpenTelemetry | 跨组件关联和因果追踪 | telemetry 不是正式状态或充分证据 |
| Reflexion / ExpeL | 成功失败经验、评价与反思分离、可检查经验 | 自我评价无成功保证，经验不能成为权限或通用规则 |
| SQLite WAL / JSON Schema | 本地事务、版本化结构、严格验证 | 数据有效不等于语义真实；数据库不能决定权威 |

## 3. 物种兼容审判

任何外部资源进入设计前回答：

1. 它默认服务的“主体”是谁；
2. 它把目标、状态、现实、权限和完成放在哪里；
3. 它是否会让框架运行状态取代持续自我；
4. 它是否默认动作可重试或输出可自证；
5. 它是否允许用户审查、撤权、导出和删除；
6. 它提取出的原则应进入哪个生命维度；
7. 与 Furina Code 冲突的根逻辑由什么替换。

## 4. 当前研究结论

市场和文献中没有发现一套可以直接移植的完整 Furina Code 基因。最合理路线仍是：从 Furina Code 的特定身份和生命状态出发，提取外部原则，桥接到七个生命维度，并在冲突处设计替代逻辑。
