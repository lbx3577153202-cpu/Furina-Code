---
title: PDR-005 后端入口不是 Provider 集成
status: ACCEPTED
authority: PROJECT_DECISION
version: 1.0
prepared_at: 2026-07-16
last_verified: 2026-07-16
authority_scope: backend_entry_identity_and_non_detachment_rule
implementation_authority: true
---

# PDR-005：后端入口不是 Provider 集成

## 状态

`ACCEPTED`

## 背景

尽管 PDR-001 已定义后端是现实入口与载体，当前工程遗留的 `BackendPort`、`FileBackend`、Adapter 和历史 MiMo headless 路线，仍可能诱导协作者把 Furina Code 误解为“本地 Furina 程序调用 MiMo/provider”，或把本地持续生命系统与后端入口看作两个独立产品再做连接。

这种理解会重启已经归档的套壳路线，也会改变 Furina Code 的物种关系。

## 决定

1. 后端是 Furina Code 进入项目现实、与用户交互、认知与行动的入口和载体；例如用户在项目目录运行 `mimo`，进入的是 Furina Code 的现实入口，不是先启动独立后端再等待 Furina Code 接入。
2. 本地持续生命系统是同一 Furina Code 的内在连续结构；它使该入口中的任务、现实、权威、证据、完成、恢复和经验跨会话持续存在，不是站在后端之外的产品控制器。
3. 任何 `BackendPort`、Adapter、文件交换或协议结构，只能是支撑本地生命状态在现实入口中连续表达的局部工程材料；它们不得定义产品入口或反转依赖方向。
4. 禁止以“Furina Code 调用 MiMo”“先起本地控制器再启动后端”“把后端作为普通 provider 接入”为当前主线描述、设计或实施。

## 对当前代码的解释

- `FileBackend` 和 E4 CLI 仅是受限只读闭环的工程切片；它们不构成 Furina Code 的产品入口，也不定义未来 MiMo Code 的运行关系。
- 已归档的 `Python CLI → mimo run` 路线是被拒绝的反例，不是待补全的接入骨架。
- 后续工作要解决的是：本地持续生命如何在用户实际启动和使用的后端入口中被加载、延续、约束和表达；不是让独立本地程序去调用后端。

## 后果

每个涉及后端的新任务必须先说明：

1. 用户实际通过哪个后端入口进入 Furina Code；
2. 本地持续生命在该入口中怎样保持同一主体与任务连续；
3. 为什么该设计没有制造后端外的第二产品入口或反向调用套壳；
4. 哪些工程材料只是局部传输/披露/候选边界，不能获得生命权威。

## 重新审议条件

只有用户明确要求新增一个独立的无人值守或服务型入口，并且它能保持同一主体、现实、授权、恢复与证据边界时，才可以设计第二入口模式。该模式也不得把当前 MiMo Code 入口降格为普通 provider。
