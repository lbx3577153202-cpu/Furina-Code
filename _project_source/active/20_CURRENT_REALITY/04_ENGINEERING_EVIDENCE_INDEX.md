---
title: Furina Code 当前工程证据索引
status: SNAPSHOT
authority: REALITY
version: 1.1
prepared_at: 2026-07-17
last_verified: 2026-07-17
authority_scope: engineering_evidence_index
implementation_authority: false
snapshot_head: LOCAL_WORKING_TREE_AFTER_INITIAL_LOOP_V1
---

# Furina Code 当前工程证据索引

本表用于定位工程事实，不替代提交、CI、测试输出或仓库 diff。

| 证据窗口 | 结果 | 主要内容 | 真实性边界 |
|---|---|---|---|
| 历史 E2–E4 / MC1 | 已有 | Python 基线、生命脊柱、只读真实闭环、BackendPort/FileBackend | 不等于写入、恢复或经验成长 |
| 历史 main 清理锚点 | `2a221ccd…` | MiMo 专属 Adapter 已从 main 删除 | 是初循环前锚点，不能代表本轮代码 |
| 本地 E5 | passed | 计划绑定、授权票据、动作收据、写后对账、验证和完成链 | 仅单文件创建任务族 |
| 本地 E6 | passed | 中断恢复、未知结果观察、暂停、因果绑定 | 仅单文件写入副作用 |
| 本地 E7 | passed | 候选经验、第二轮试用、升降级 | 最高 `conditional`，不代表可复用经验 |
| 本地初循环端到端 | passed | 两轮不同 `notes/*.txt` 真实写入与经验试用 | 隔离 Git 项目、低风险单文件 |
| Windows 本地全量 pytest | **405 passed** | 回归验证窗口 | 未提交 main、未形成新 CI run |

## 当前锚点

```text
evidence_revision: LOCAL_WORKING_TREE_AFTER_INITIAL_LOOP_V1
main_head_for_this_change: 未记录（不得用旧 2a221ccd… 代替）
targeted_initial_loop_tests: 17 passed
full_local_tests: 405 passed
ci_for_this_change: 未记录
```

## 使用规则

- 测试数量只属于对应代码窗口，不能单独推出产品成熟度；
- 未提交工作树不得写成 GitHub main，未运行 CI 不得写成跨平台验证；
- 当前初循环结论以 `05_INITIAL_LOOP_ESTABLISHMENT_RECORD.md` 的严格范围为准；
- 每个新任务族应增加独立的真实证据条目，而非复用本条目。
