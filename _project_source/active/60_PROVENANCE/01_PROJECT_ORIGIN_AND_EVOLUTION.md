---
title: Furina Code 项目来源与演化
status: ACTIVE
authority: PROVENANCE
version: 1.1
prepared_at: 2026-07-16
last_verified: 2026-07-16
authority_scope: project_history_and_definition_evolution
implementation_authority: false

---

# Furina Code 项目来源与演化

本文件解释项目为什么走到今天，不直接裁决当前代码能力。

## 阶段 1：本地 AI 产品与 FurinaOS

最初目标是让普通用户在本地拥有能够对话、处理文件、控制系统并形成长期关系的 AI。早期 FurinaOS 包含 GUI、语音、聊天、文件和多入口 Core。

留下的长期问题是：产品能力、Agent 能力和基础层权威边界不清，功能存在不等于同一主体在承担责任。

## 阶段 2：Local Autopilot / Agent Control Plane

项目开始关注：如何让 AI 在本地仓库中有纪律地工作，而不是无边界执行。形成任务卡、Commander/Worker、Gate、成本/研究边界和证据概念。

留下的价值是治理意识；局限是大量能力仍停留在协议、preview 或内部 harness。

## 阶段 3：U2/U3 用户级与内部产品闭环

项目建立 goal、task、permission、controlled execution、evidence、review、apply preview、memory、workbench 等内部流程，并形成大量测试。

这一阶段证明了可治理流程可以被工程化，但也暴露：测试和 preview 很容易被过度描述为产品能力，真实用户入口和 AI-backed 行动仍不足。

## 阶段 4：自主开发生命体与器官框架

项目用器官、板域、Evidence Bus、Constitution 和成长机制描述一个自主开发者生命体。

它带来了“系统必须维持生命责任，而不只是调用功能”的方向，但早期器官清单容易变成静态组件拼装，尚未给出物种级生成根。

## 阶段 5：多元问题架构与造物台

项目提出：现实问题产生定义，定义形成基因，基因长出器官。造物台成为从用户问题到系统能力的生成方法。

随后发生关键修正：Furina Code 的开发方式不等于造物台，还需要判断、执行、验证、证据、安全、记忆成长和用户成效汇报。

## 阶段 6：理论基因与生命维度

设计从器官清单上升到“Furina Code 是怎样的一个人/生命体”，形成内部生命、外部世界、持续自我、行动改变、意义生成、经验生长和关系责任七个耦合维度。

外部 Active Inference、Enactive cognition、Interoceptive AI、lifelong learning、generative agents 和 constitutional AI 被视为其他物种样本，而不是可直接拼接的完整基因。

## 阶段 7：初循环与成熟版分离

项目明确：

- 初循环证明 Furina Code 第一次真实成立；
- 成熟版证明同一主体能够长期承担项目级开发责任；
- 初循环不提前承担成熟版全部复杂度；
- 成熟发育不能删除初循环历史。

形成初循环/成熟成立定义、判据、总设计和成熟九系统权威宪法。

## 阶段 8：新 Furina-Code 仓库与工程链

为摆脱旧仓库混杂，新建 `Furina-Code` 仓库。通过 P2/P3/P4 和实现路线形成：

- 五系统、十九器官；
- 五组织；
- 正式对象唯一权威；
- 状态机、协议和 IL-G0—G9；
- 纵向小闭环实现路线。

E2—E4 依次建立技术基线、本地生命脊柱和只读真实闭环。

## 阶段 9：BackendPort 与 MiMo 路线纠偏

项目建立通用 BackendPort 与 FileBackend，随后错误地把“MiMo Code 接入”开发成 Python CLI headless 调用 `mimo run`。

用户指出：后端本来就是现实入口和载体，当前本地生命系统尚无独立产品入口；这条路线是在“车里造车”，且直接使用 MiMo AI 已达到更好效果。

最终：

- headless 路线归档；
- MiMo 专属 Adapter 从 main 删除；
- 明确当前架构为“后端入口/载体 × 本地持续生命系统”，不是两个独立产品的连接，也不是本地 Furina Code 调用后端；
- 项目来源开始按权威和当前现实重构。

## 当前演化结论

项目真正的主线不是不断添加更多 Agent 功能，而是让现有后端能力在本地主权、现实、证据、恢复和成长中成为同一个 Furina Code。
