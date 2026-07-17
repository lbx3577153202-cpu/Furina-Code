---
title: Furina Code 项目来源入口
status: ACTIVE
authority: CONSTITUTION
version: 1.3
prepared_at: 2026-07-17
last_verified: 2026-07-17
authority_scope: source_navigation_and_current_project_orientation
implementation_authority: false
---

# Furina Code 项目来源入口

本目录是 Furina Code 的唯一活跃项目来源包。它回答项目身份、当前工程现实、当前设计依据、冻结与候选的边界，以及冲突裁决规则；它不保存全部历史材料。

## 1. 当前项目根定义

> **Furina Code 是用户项目世界中的持续开发生命体。后端是它进入现实、与用户交互、认知和行动的入口与载体；本地持续生命系统是使这一入口中的每次会话持续成为同一个 Furina Code 的内在生命底座。**

```text
后端入口 / 载体 × 本地持续生命系统 = Furina Code 初循环
```

后端不是由独立本地控制器调用的 provider；本地持续生命系统也不是另一个产品入口或外部控制器。

## 2. 当前真实状态摘要

2026-07-17 的本地工程证据窗口：

```text
repository: lbx3577153202-cpu/Furina-Code
verified_revision: LOCAL_WORKING_TREE_AFTER_INITIAL_LOOP_V1
verification_environment: Windows 本地项目工作区
pytest: 405 passed
initial-loop suite: 17 passed
```

**第一版初循环已经成立，但仅限以下范围：**隔离 Git 项目内、低风险 `notes/*.txt` 单文件创建任务族的两轮受控写入与第二轮经验试用。

```text
观察 → 计划 → 授权 → 写入 → 对账 → 验证 → 裁决 → 终态 → 第二轮经验试用
```

其中未知写入结果绝不自动重试；第二轮经验只作候选指导，成功后最高为 `conditional`，不会直接成为可复用授权。正式证据与边界见 `20_CURRENT_REALITY/05_INITIAL_LOOP_ESTABLISHMENT_RECORD.md`。

仍不能声称：广义 Furina Code 已完成、MiMo Code 已加载本地生命系统、产品级入口已开放、任意项目写入安全可用、通用恢复/长期经验已完成，或用户可长期托付成熟开发责任。

本轮未记录新的 main 提交 SHA 或 GitHub Actions 运行；不得将本地验证误写成 main/CI 已验证。

## 3. 阅读顺序

快速恢复上下文：

1. 本文件；
2. `01_SOURCE_AUTHORITY_AND_CONFLICT_RULES.md`；
3. `10_CONSTITUTION/01_PROJECT_CONSTITUTION.md`；
4. `20_CURRENT_REALITY/01_CURRENT_STATE_SNAPSHOT.md`；
5. `20_CURRENT_REALITY/02_CAPABILITY_REALITY_LEDGER.md`；
6. `20_CURRENT_REALITY/05_INITIAL_LOOP_ESTABLISHMENT_RECORD.md`；
7. `50_DECISIONS/00_DECISION_INDEX.md`。

工程设计或审查还应阅读 `11_FORMAL_BASIS/`、`30_ACTIVE_DESIGN/` 和 `20_CURRENT_REALITY/04_ENGINEERING_EVIDENCE_INDEX.md`。历史追溯只读 `60_PROVENANCE/` 与 `80_ARCHIVE_INDEX/`；完整原始对话和旧包属于 Cold Archive，不应长期加载。

## 4. 领域裁决规则

| 问题 | 裁决来源 |
|---|---|
| 用户当前要什么 | 用户当前明确指令 |
| Furina Code 是什么、不能变成什么 | `10_CONSTITUTION/` 与冻结正式依据 |
| 当前代码、HEAD、测试、真实能力 | 本地仓库、GitHub `main`、GitHub Actions |
| 当前按什么设计和实现 | `30_ACTIVE_DESIGN/` + 最新 ACCEPTED PDR，不得超出现实账本 |
| 受限初循环是否成立 | `20_CURRENT_REALITY/05_*` + 可复核仓库/测试证据 |
| 成熟目标 | `40_TARGET_DESIGN/`，无当前实现证明权 |

## 5. 五条最高风险误读

1. 冻结文档不等于实现已成立。
2. 测试通过不等于产品入口已开放或用户可用。
3. 本轮 `notes/*.txt` 初循环成立不等于任意开发任务成立。
4. 后端不是 Furina Code 要调用的 provider；它本来就是现实入口与载体。
5. 归档路线不能因代码仍可恢复而自动重新进入主线。

## 6. 本包与实时工程的关系

本包是上下文和裁决入口，不是实时数据库。带 HEAD、测试数或能力状态的文件都是日期快照；若与可核验仓库现实冲突，必须更新快照，不能让旧来源覆盖现实。ChatGPT 项目来源中长期只保留一个 `FURINA_CODE_ACTIVE_SOURCE_PACK_CURRENT.zip`。
