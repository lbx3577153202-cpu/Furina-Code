---
title: 项目来源权威与冲突裁决规则
status: ACTIVE
authority: CONSTITUTION
version: 1.1
prepared_at: 2026-07-16
last_verified: 2026-07-16
authority_scope: source_authority_conflict_resolution_and_maintenance
implementation_authority: true

---

# 项目来源权威与冲突裁决规则

## 1. 为什么不能使用单一总优先级

项目中的“身份定义”“工程现实”“当前设计”“成熟目标”和“历史来源”回答的是不同问题。将它们排成一条简单的高低顺序，会产生两类错误：

- 用抽象理论否认仓库中已经发生的工程事实；
- 用当前代码偶然形态反向改写 Furina Code 的物种身份和用户关系。

因此，本项目采用 **领域权威 + 适用范围 + 新鲜度 + 证据** 的联合裁决。

## 2. 领域权威矩阵

| 领域 | 第一权威 | 第二权威 | 不得作为裁决来源 |
|---|---|---|---|
| 用户方向、风险偏好、是否继续 | 用户当前明确指令 | 有来源的用户纠正记录 | 模型推断、旧任务卡 |
| 项目身份、关系、根原则 | Project Constitution、冻结正式依据 | 最新 ACCEPTED 物种级 PDR | 当前实现便利、外部框架默认假设 |
| 实时代码、HEAD、分支、测试 | 本地仓库、GitHub `main`、CI | 带证据的工程快照 | 旧资源包、聊天记忆、候选稿 |
| 当前实现边界 | Capability Reality Ledger + 仓库证据 | PR/提交/运行证据 | 总设计中的未来描述、测试数量本身 |
| 当前工程设计 | Active Design + ACCEPTED PDR | 冻结 P4 工程契约 | Target Design、Archived Routes |
| 成熟目标 | Target Design + 成熟冻结正式依据 | 理论基因原始冻结稿（找回后） | 当前代码目录结构 |
| 历史与来源 | Provenance 整理稿 | Cold Archive 原始材料 | 将历史观点直接当现行规范 |
| 已退出路线 | Archive Index + Git archive ref | 原 PR/branch/tag | 自动恢复或默认合并 |

## 3. 冲突处理算法

发现两个来源不一致时，按以下顺序处理：

1. **确定问题领域。** 是身份、工程现实、当前设计、成熟目标、历史还是归档？
2. **检查来源状态。** `FROZEN / ACTIVE / SNAPSHOT / TARGET / ACCEPTED / PAUSED / SUPERSEDED / ARCHIVED / SOURCE_GAP`。
3. **检查 authority_scope。** 文件是否真的对该问题有裁决权？
4. **检查时间和证据。** 快照是否过期，是否有 HEAD、CI、提交或原始来源支持？
5. **执行 fail-closed。** 无法判断时标记 `UNKNOWN` 或 `SOURCE_GAP`，不得补写一个看似合理的事实。
6. **留下版本化决定。** 物种级、依赖方向、主线或不可逆决策必须形成 PDR；不得静默改历史。
7. **更新下游来源。** 决定生效后，更新入口、现实账本、决策索引和完整性清单。

涉及后端时，额外执行一条物种检查：任何描述、设计或任务若将 Furina Code 表述为“本地控制器调用后端 / provider”，或将后端表述为可从产品入口剥离的内部子程序，必须判为与 PDR-001、PDR-005 冲突；除非用户明确决定新增独立无人值守入口，且满足对应恢复条件。

## 4. 状态词汇

| 状态 | 含义 | 能否指导当前实现 |
|---|---|---|
| `FROZEN` | 已冻结根定义或正式判据，修改需版本化修订 | 在 authority_scope 内可以 |
| `ACTIVE` | 当前有效说明或设计 | 可以，但不能超出现实和上位边界 |
| `SNAPSHOT` | 有核验时间的现实快照 | 只在对应时间窗口内 |
| `TARGET` | 成熟目标或长期方向 | 不能直接证明或要求当前能力 |
| `ACCEPTED` | 已采纳的项目决定 | 在决定范围内可以 |
| `PAUSED` | 暂停，等待明确恢复条件 | 不可以 |
| `SUPERSEDED` | 已被新版本取代 | 不可以，只用于追溯 |
| `ARCHIVED` | 已退出当前主线 | 不可以 |
| `SOURCE_GAP` | 已知应存在但缺乏原始可核验来源 | 不可以推测补全 |

## 5. “实现权威”不等于“真相权威”

`implementation_authority: true` 表示该文件可约束实现范围，并不表示文件描述的能力已经存在。能力存在必须由当前代码、测试、真实环境和用户入口证据共同判断。

## 6. 文件维护规则

- 冻结原稿保持字节不变；元数据放在索引和 Manifest，不在原稿顶部插入新 frontmatter。
- 活跃文件使用稳定文件名，版本写在文件头；避免“最终版、最终最终版”。
- 快照必须记录 `verified_at`、仓库 HEAD 和证据来源。
- 重大决策使用 `PDR-*`，避免与仓库工程 ADR 编号冲突。
- 旧材料移入 Cold Archive 后，从活跃索引中删除其裁决权。
- 每次主线架构纠偏至少同步更新：`00_START_HERE`、Current Reality、Decision Index、Archive Index、Manifest。

## 7. 禁止的来源行为

- 根据摘要重建缺失的冻结原文；
- 将候选稿改名为正式冻结稿；
- 用模型口头总结覆盖原文件；
- 用 CI green 证明产品能力；
- 用当前某个 Adapter 形态把后端重写成 Furina Code 调用的 provider，或把本地生命系统重写成后端之外的产品控制器；
- 将 Cold Archive 全量长期上传，造成旧定义检索污染；
- 删除错误路线的历史证据，使未来无法解释为什么拒绝它。
