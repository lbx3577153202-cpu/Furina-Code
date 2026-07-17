---
title: 项目来源谱系图
status: ACTIVE
authority: PROVENANCE
version: 1.0
prepared_at: 2026-07-16
last_verified: 2026-07-16
authority_scope: source_dependency_and_transformation_map
implementation_authority: false

---

# 项目来源谱系图

## 1. 物种与成熟来源链

```text
早期 FurinaOS / Local Autopilot 经验
→ 造物台与开发方式讨论
→ 物种边界 V0.3.1（原件当前缺失）
→ 理论基因 V1（原件当前缺失）
→ 初循环/成熟成立定义与判据
→ 两份总设计 V0.2
```

## 2. 初循环工程链

```text
初循环版总设计 V0.2
+
成熟版发育边界
→ P2 五系统/十九器官
→ P3 五组织
→ P4 权威、对象、状态、协议、Gate 冻结
→ 实现路线
→ E0/E1 工程交接
→ E2 技术基线
→ E3 本地生命脊柱
→ E4 只读真实闭环
→ MC1 BackendPort / FileBackend
```

## 3. 当前纠偏链

```text
“接入 MiMo Code”需求
→ 错误解释为 headless mimo CLI provider
→ PR #11 / #12
→ 用户指出入口关系和收益错误
→ PDR-001 / PDR-003
→ PR #13 清理
→ 当前 main 2a221ccd...
```

## 4. 资料来源分层

| 来源 | 在本包中的位置 | 当前权威 |
|---|---|---|
| 冻结总设计与正式依据 | Active Source Pack | 对各自 scope 有权威 |
| P2/P3/P4/Route exact 原件 | GitHub `docs/architecture/initial-loop/` | 工程契约逐字权威 |
| 当前代码/测试/CI | GitHub main / Actions | 工程现实权威 |
| 旧整合包和资源包 | Cold Archive | 历史和追溯 |
| ChatGPT 完整导出 | Cold Archive | 原始对话证据，无直接当前权威 |
| 本次整理稿 | Active Source Pack | 按 frontmatter scope |

## 5. 缺失来源的处理

理论基因 V1 和 V0.3.1 原件未找到时，所有下游文件仍可作为其自身已经冻结的来源使用，但不能反向声称已经恢复上游完整原文。
