---
title: 项目来源缺口登记
status: ACTIVE
authority: CONSTITUTION
version: 1.0
prepared_at: 2026-07-16
last_verified: 2026-07-16
authority_scope: known_missing_or_not_independently_verified_sources
implementation_authority: false

---

# 项目来源缺口登记

| 编号 | 缺口 | 当前证据 | 风险 | 处理规则 |
|---|---|---|---|---|
| SG-001 | 理论基因 V1 原始独立 Markdown 未找到 | 多份资料记录其冻结状态和历史路径 | 摘要被误当原文，物种定义被无证据重写 | 不重建；找到后原样核验 |
| SG-002 | 物种边界 V0.3.1 独立冻结文件未在本包找到 | 历史对话与资源包记录其地位 | 宪法只能依赖间接一致性 | 继续搜索旧 `_handoff` / repo；不伪造 |
| SG-003 | P2/P3/P4/Implementation Route 的 exact wording 未复制进本包 | 当前 GitHub `docs/architecture/initial-loop/` 存在原件，E0 记录源/仓库 Hash 匹配 | 离线包不能逐字审查工程链 | 本包提供路径、Hash 和详尽综合；逐字裁决以 GitHub 原件为准 |
| SG-004 | MiMo Code UI 与本地持续生命系统的正式加载协议尚未设计/实现 | 当前主线没有该产品级耦合证据 | 再次把 headless CLI 当主线接入 | 保持能力为 NOT_IMPLEMENTED；进入开发前先形成独立设计决定 |
| SG-005 | 当前完整文件树和测试明细未被本包静态复制 | GitHub main/CI 是实时事实源 | 快照快速过时 | 以 GitHub 为准；更新 Reality Snapshot |

## 缺口处理原则

- `SOURCE_GAP` 不是失败掩盖词，而是禁止猜测的正式状态；
- 只有获得原始文件、可核验提交或同等一手证据后才关闭；
- 关闭缺口必须更新本表、对应来源状态文件和 Manifest；
- 缺口未关闭不阻止使用其他已核验来源，但必须限制其推断范围。
