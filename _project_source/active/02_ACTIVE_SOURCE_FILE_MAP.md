---
title: 活跃来源文件地图
status: ACTIVE
authority: PROVENANCE
version: 1.3
prepared_at: 2026-07-17
last_verified: 2026-07-17
authority_scope: active_source_pack_file_roles
implementation_authority: false

---

# 活跃来源文件地图

| 区域 | 主要回答 | 是否直接指导实现 |
|---|---|---|
| `00_START_HERE.md` | 项目是什么、现在在哪、先读什么 | 否，导航与防误读 |
| `01_SOURCE_AUTHORITY_AND_CONFLICT_RULES.md` | 冲突时如何裁决 | 是，来源治理规则 |
| `10_CONSTITUTION/` | Furina Code 是谁、根原则、术语和来源缺口 | 在范围内是 |
| `11_FORMAL_BASIS/` | 初循环和成熟成立的正式冻结依据 | 在范围内是，但冻结不等于实现 |
| `20_CURRENT_REALITY/` | 当前代码、证据、能力、缺口与初循环建立记录 | 是，当前能力边界 |
| `30_ACTIVE_DESIGN/` | 当前初循环按什么继续建设 | 是 |
| `40_TARGET_DESIGN/` | 成熟形态目标 | 否，只有方向约束 |
| `50_DECISIONS/` | 为什么接受/拒绝重大路线；后端入口不可被降格为 provider | 是，按 PDR 状态 |
| `60_PROVENANCE/` | 项目怎样演化、来源如何连接 | 否 |
| `80_ARCHIVE_INDEX/` | 哪些路线退出及如何追溯 | 否 |
| `90_MAINTENANCE/` | 何时更新、怎样构建、怎样替换唯一活跃包 | 是，维护流程 |
| `99_INTEGRITY_MANIFEST.md` | 文件状态、哈希、来源关系 | 否，完整性和防并列真相 |
| `PACKAGE_QUALITY_AUDIT.md` | 本次整合的质量检查 | 否 |

## 活跃包之外

Cold Archive 在本地独立保存完整原始对话、旧资源包、候选稿和二进制原件。它们不属于活跃裁决上下文，默认不上传到项目来源。

冻结原稿保留其冻结时的历史工程措辞；当前是否成立由 `20_CURRENT_REALITY/` 的最新证据记录裁决，不能用冻结原文的旧状态句反向覆盖当前现实。
