---
title: 活跃来源包质量审计
status: ACTIVE
authority: MAINTENANCE
version: 1.4
prepared_at: 2026-07-17
---

# 活跃来源包质量审计

## 审计结论

本包可作为唯一活跃项目来源直接替换。V1.4 在 V1.3 基础上修复了初循环的执行前现实核验、E7 实际计划因果链、冻结稿独立防篡改和发布元数据真实性。

## V1.4 修订原因

1. **执行前现实核验**：E5 执行器在 `execute_single_file_create()` 前重新创建 act-time snapshot，确保执行面对真实项目状态而非 observe-time 快照；
2. **E7 实际计划因果链**：`BoundActionPlan.experience_match_ref` 和 `CompletionVerdict.action_plan_ref` 为正式对象字段，`record_trial_use()` 验证完整链路；
3. **冻结稿独立防篡改**：`FROZEN_EXPECTED_HASHES` 包含真实 SHA-256，不依赖可编辑的 SHA256SUMS.txt；
4. **ZIP 逐文件内容校验**：解压后逐文件 SHA-256 比对，拒绝缺失、额外或内容不一致的文件；
5. **真实发布元数据**：HEAD、origin/main、branch、status 从 Git 实时读取，不硬编码。

## 测试证据

- 初循环集合（E5/E6/E7/initial_loop）：23 passed
- 全量 pytest：437 passed
- CI：unknown（本工作分支无新 main SHA 或 CI run）
- HEAD：`6c0d77965a6748449e386bcce2a30e5b36fac97c`
- origin/main：`2a221ccd129507f0d32bccdacb3a8246a2c90b63`

## 一致性检查

- 当前入口、现实账本、缺口、证据索引和建立记录对初循环范围表述一致；
- 初循环成立仅限隔离 Git 项目、低风险 `notes/*.txt` 单文件创建、两轮受控写入与第二轮受限经验试用；
- 不存在"Furina Code 调用 MiMo"的新路线；
- 不存在将本地测试误写成产品入口、GitHub main 或跨平台 CI 的表述；
- 完整性清单覆盖本包全部 Markdown 文件并记录哈希。

## 替换边界

上传本包后，项目来源中应只保留这一份 `FURINA_CODE_ACTIVE_SOURCE_PACK_CURRENT.zip`。旧活跃包、解压副本和冷档案不应并列存在。
