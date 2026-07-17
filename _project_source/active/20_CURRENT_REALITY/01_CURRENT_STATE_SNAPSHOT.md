---
title: Furina Code 当前工程状态快照
status: SNAPSHOT
authority: REALITY
version: 1.3
prepared_at: 2026-07-17
last_verified: 2026-07-17
authority_scope: repository_and_engineering_reality_at_verified_revision
implementation_authority: false
snapshot_head: LOCAL_WORKING_TREE_AFTER_INITIAL_LOOP_V2
live_truth:
  - local_repository
  - github_main
  - github_actions
evidence_window:
  local_test_completed_at: 2026-07-17
---

# Furina Code 当前工程状态快照

> 本文件是带日期的工程快照。实时事实始终以本地仓库、GitHub `main` 和 GitHub Actions 为准。

## 1. 基线

```text
repository: lbx3577153202-cpu/Furina-Code
default_branch: main
head: 6c0d77965a6748449e386bcce2a30e5b36fac97c
origin/main: 2a221ccd129507f0d32bccdacb3a8246a2c90b63
branch: feat/initial-loop-e5-e7-source-maintenance
verified_revision: LOCAL_WORKING_TREE_AFTER_INITIAL_LOOP_V2
verification_environment: Windows 本地项目工作区（PR 工作分支）
pytest_window: 437 passed
targeted_initial_loop_window: 23 passed（E5 / E6 / E7 / initial_loop）
CI: unknown
```

本轮未提供新的 main 提交 SHA 或 CI run。既有 GitHub `main@2a221ccd…` 是初循环前的历史锚点，不能代表本轮实现。

## 2. 当前技术基线

- Python `>=3.12`，`src` layout；
- 无第三方运行时依赖；开发依赖为 pytest；
- SQLite 追加式 Ledger、正式对象、任务状态约束与 ContinuityView 已存在；
- Git/文件的只读现实观察、BackendPort 与 FileBackend 传输边界仍是已有基础；
- 未引入 Pydantic、外部 Agent 框架、网络或模型 SDK。

## 3. 已验证的工程阶段

E2、E3、E4 与 MC1 保持原有事实。

**E5–E7 已在严格限定范围内闭合：**

- E5：计划绑定、授权票据、动作收据、执行前重新观察现实（act-time snapshot）、写后现实对账、`verify → adjudicate → terminal`；
- E6：未知结果先观察，确认目标存在才跳过重复动作，否则暂停；从不自动重试；恢复裁决进入后续 `TaskRun` 的因果和当前引用；
- E7：`experience_match_ref` 和 `action_plan_ref` 为正式对象字段，`record_trial_use()` 验证完整因果链；第一轮只能形成 `candidate`；第二个不同任务只获候选指导，成功最高 `conditional`，失败降级；
- 两轮均在隔离 Git 项目中真实创建不同 `notes/*.txt` 文件，并分别重跑完整闭环。

因此，**IL-L3 初循环已在该任务族内建立**。详见 `05_INITIAL_LOOP_ESTABLISHMENT_RECORD.md`。

## 4. 路线边界

MiMo CLI/headless 自动调用路线仍是归档路线；本轮没有新增 Furina Code → MiMo 调用链。后端仍是现实入口与能力载体，本地持续生命系统是其内在持续底座。

## 5. 当前未实现或未证明

- MiMo Code UI 自动加载本地持续状态；
- 产品级持续任务入口；
- 任意文件族、多文件、删除/更新/重命名、跨仓库或外部系统的受控写入；
- 通用恢复裁决与外部副作用恢复；
- 可复用/长期经验成长；
- MAT-M3 成熟成立与长期托付。

## 6. 更新规则

提交锚点、能力等级、入口、CI/真实运行结论或主线路线发生实质变化时，必须更新本文件。旧版本留在本地版本化归档或 Git 历史，不在活跃包中并列保留。
