---
title: Furina Code 初循环建立记录
status: ACTIVE
authority: REALITY
version: 1.1
prepared_at: 2026-07-17
last_verified: 2026-07-17
authority_scope: narrow_initial_loop_establishment_claim
implementation_authority: true
evidence_revision: LOCAL_WORKING_TREE_AFTER_INITIAL_LOOP_V2
---

# Furina Code 初循环建立记录

## 1. 建立结论

**IL-L3 初循环已建立，但只在以下严格范围内成立：**

```text
隔离 Git 项目 × 低风险 notes/*.txt 单文件创建 × 两轮真实受控写入 × 第二轮受限经验试用
```

它不是广义 Furina Code 已完成，也不是产品入口已经开放。

## 2. 已验证闭环

两轮任务均实际执行：

```text
观察 → 计划(含 experience_match_ref) → 授权 → 执行前重新观察现实 → 写入 → 对账 → 验证 → 裁决(action_plan_ref) → 终态
```

V1.1 修订：
- `BoundActionPlan.experience_match_ref` 为正式字段，创建时写入 canonical payload 和 integrity 计算；
- `CompletionVerdict.action_plan_ref` 为正式字段，记录本次实际执行的 action plan；
- `record_trial_use()` 验证完整因果链：experience → match → plan → completion；
- E5 执行器在 `execute_single_file_create()` 前重新创建 act-time snapshot。

第二轮另行走完整闭环，只可接收第一轮的 `candidate_guidance_only`。成功后经验最高为 `conditional`，失败会降级；不得自证或升级为 `reusable`。

## 3. 关键反例与约束

- 无票据或越界/高风险动作不得执行；
- 快照漂移、重复幂等键和不符合范围的变更不得伪装成功；
- 写前中断只可重新运行瞬时 Gate；
- 结果未知时先观察：确认目标已存在才跳过重复写入，否则暂停；绝不自动重试；
- 恢复裁决必须进入恢复后 `TaskRun` 的因果引用与当前引用；
- 现实变化会使验证/完成裁决失效；用户中途纠正创建新任务修订，旧方向仍可追溯；
- 完成裁决未绑定携带 `experience_match_ref` 的实际计划时，不能生成 TrialUseRecord。

## 4. 证据窗口与可信边界

- Windows 本地工作区全量：`python -m pytest -q`，**437 passed**；
- 初循环相关集合：E5 / E6 / E7 / `initial_loop`，**23 passed**；
- 已执行两轮真实写入和第二轮经验试用烟测；
- 本轮尚未记录新的 main 提交 SHA 或 GitHub Actions 运行，不能写成 main/CI 证据。

## 5. 不覆盖的能力

不覆盖任意文件操作、多文件任务、更新/删除/重命名、跨仓库、外部系统、高风险动作、通用恢复、长期经验、产品入口或成熟托付。扩展任何一项，都必须重新建立对应 Gate、对账、失败反例和范围化证据。
