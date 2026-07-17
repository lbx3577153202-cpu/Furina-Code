---
title: PDR-003 MiMo 无界面自动调用路线暂停
status: PAUSED
authority: PROJECT_DECISION
version: 1.0
prepared_at: 2026-07-16
last_verified: 2026-07-12
authority_scope: mimo_headless_route_status_and_recovery_conditions
implementation_authority: false

---

# PDR-003：MiMo 无界面自动调用路线暂停

## 状态

`PAUSED`

## 路线

```text
Python CLI
→ mimo run
→ 固定结构化输出
→ candidate 文件
→ collect / validate / finalize
```

## 实际价值

该路线可用于：

- 定时或无人值守分析；
- 批量固定任务；
- 机器可验证的结构化输出；
- 不打开 UI 的后台运行。

## 暂停原因

当前用户直接在 MiMo Code 中调用 MiMo AI 更简单、更灵活，并且本地持续生命系统尚未形成完整持续运行能力。继续开发只会增加 Adapter、schema 和旁路复杂度，无法完成当前所需的“后端入口 × 本地生命系统”。

## 归档证据

```text
source_head: aa31f8e16f00f7cfd743b35919ac308bf550de89
archive_branch: archive/mimo-headless-e4
archive_tag: archive-mimo-headless-e4-v0.1
historical_prs: #11, #12
cleanup_pr: #13
main_cleanup_commit: 2a221ccd129507f0d32bccdacb3a8246a2c90b63
```

## 恢复条件

必须同时满足：

1. 出现明确的无人值守、定时或批量任务；
2. 本地持续生命系统可真实持续运行；
3. 自动调用相比直接使用后端产生可度量收益；
4. 凭证、隔离、失败、恢复和成本边界已设计；
5. 形成新的 ACCEPTED PDR 和有界任务卡。

## 恢复方式

从归档 tag 定点提取需要的 Adapter/接线并重新审查；禁止整分支直接合并，也禁止把历史测试结果当当前适配证明。
