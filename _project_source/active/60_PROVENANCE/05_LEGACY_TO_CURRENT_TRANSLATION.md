---
title: 旧 FurinaOS 资料到当前 Furina Code 的翻译规则
status: ACTIVE
authority: PROVENANCE
version: 1.0
prepared_at: 2026-07-16
last_verified: 2026-07-16
authority_scope: legacy_context_translation_and_contamination_prevention
implementation_authority: false

---

# 旧 FurinaOS 资料到当前 Furina Code 的翻译规则

旧资源包仍有大量方法论和失败经验价值，但不能把旧仓库状态直接搬到新项目。

| 旧资料概念 | 可保留的原则 | 当前不能直接沿用 |
|---|---|---|
| Local Autopilot | 任务卡、边界、证据、低打扰 | 旧 Commander/Worker 运行时状态 |
| U2/U3 内部产品 | 用户流程、Gate、review、memory lifecycle | “内部测试通过 = 产品 1.0”式描述 |
| 器官注册/六板域 | 责任拆分和成熟度意识 | 旧 50 器官作为当前实现清单 |
| Evidence Chain/Bundle | 证据需要结构和关联 | 旧模块存在即证明新仓库已实现 |
| Limited Source Write | 从只读到受控写入的渐进原则 | 旧 allowlist 写能力直接成为新仓库能力 |
| 造物台 | 从现实问题产生定义和结构 | 将造物台等同完整开发方式 |
| Memory Backend | 经验需持久、可审查、可删除 | 日志/对话直接当肌肉记忆 |
| User Attention Gate | 低打扰和必要介入 | 旧 UI/Workbench 已是当前产品入口 |

## 当前翻译公式

```text
旧实现/文档
→ 提取原则与失败经验
→ 检查物种和权威兼容性
→ 重新映射到 P2/P3/P4
→ 在新仓库纵向切片中重新实现和验证
```

禁止：

```text
旧仓库有某模块
→ 新 Furina-Code 当前也有该能力
```
