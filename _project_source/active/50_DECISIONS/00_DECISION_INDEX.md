---
title: 项目重大决定索引
status: ACTIVE
authority: PROJECT_DECISION
version: 1.1
prepared_at: 2026-07-16
last_verified: 2026-07-16
authority_scope: project_level_decision_index
implementation_authority: true

---

# 项目重大决定索引

项目级决定使用 `PDR`（Project Decision Record），避免与仓库中的工程 ADR 编号冲突。

| PDR | 状态 | 决定 | 影响 |
|---|---|---|---|
| `PDR-001` | ACCEPTED | 后端是现实入口和能力载体，本地生命系统提供持续权威 | 固定依赖方向，防止再次造 headless 主入口 |
| `PDR-002` | ACCEPTED | 当前工程重点是本地持续生命系统，而不是再造智能后端 | 约束资源投入和下一切片 |
| `PDR-003` | PAUSED | MiMo headless CLI 自动调用路线退出主线并归档 | 保留未来无人值守路线，不污染当前产品 |
| `PDR-004` | ACCEPTED | 活跃来源与冷档案物理隔离 | 防止旧定义和原始对话覆盖当前事实 |
| `PDR-005` | ACCEPTED | 后端入口不是 provider 集成；本地生命系统不是外部控制器 | 消除“Furina Code 调用 MiMo”与双产品拼接的错误解释 |

## PDR 适用范围

PDR 只记录会改变物种、依赖方向、主线、权威边界或重大路线的决定。普通实现技术选择继续使用仓库 `docs/adr/`。
