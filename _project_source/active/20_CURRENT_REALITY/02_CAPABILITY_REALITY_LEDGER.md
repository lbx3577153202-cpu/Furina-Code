---
title: Furina Code 能力现实账本
status: ACTIVE
authority: REALITY
version: 1.1
prepared_at: 2026-07-17
last_verified: 2026-07-17
authority_scope: capability_maturity_and_claim_boundaries
implementation_authority: true
---

# Furina Code 能力现实账本

## 1. 成熟度层级

```text
DEFINED / CONTRACTED / IMPLEMENTED / TESTED / REAL_ENV_VERIFIED / PRODUCT_EXPOSED / USER_USABLE / ARCHIVED
```

层级不是自动累进证明；每项声明必须携带范围、证据窗口和未覆盖边界。

## 2. 当前账本

| 能力 | 当前最高可信状态 | 证据摘要 | 不得声称 |
|---|---|---|---|
| Furina Code 物种与用户关系 | `DEFINED` / 部分 `FROZEN` | 总设计、成立依据、项目宪法 | 理论已经产品化 |
| 外置后端 × 本地持续生命系统 | `DEFINED` / `ACCEPTED` | 初循环基线与 PDR | 二者已在产品中完整耦合 |
| Python 工程基线 | `IMPLEMENTED` + `TESTED` | pyproject、历史 CI | 产品能力已完成 |
| 正式对象、Ledger、状态与连续性基础 | `IMPLEMENTED` + `TESTED` | E3 代码与测试 | 完整持续自我已成立 |
| Git/文件只读观察 | `REAL_ENV_VERIFIED`（受限） | E4 真实只读运行 | 全部外部状态已覆盖 |
| 受控写入：`notes/*.txt` 单文件创建 | `REAL_ENV_VERIFIED`（严格限定） | E5 票据、收据、对账、验证、完成裁决；本地 405 passed | 任意文件操作已安全 |
| 恢复：该任务族 | `REAL_ENV_VERIFIED`（严格限定） | E6 中断、未知结果、暂停、因果绑定 | 通用恢复或外部副作用可自动继续 |
| 经验：两轮受限试用 | `REAL_ENV_VERIFIED`（严格限定） | E7 候选、第二轮不同任务、升降级边界 | 已形成可复用肌肉记忆 |
| 初循环 IL-L3 | `ESTABLISHED`（严格限定） | 两轮真实受控写入、第二轮经验试用、405 passed；见建立记录 | 广义初循环、产品入口或成熟系统已成立 |
| MiMo headless CLI route | `ARCHIVED` | branch/tag/PR #12/#13 | 当前主线能力 |
| 产品入口 | `NOT_IMPLEMENTED` | 无产品级 Furina Code launcher/UI | 用户已在使用完整 Furina Code |
| 成熟 MAT-M3 | `NOT_ESTABLISHED` | 成熟目标文档 | 可长期托付 |

## 3. 声明规则

对外或对用户描述能力时，必须同时包含能力范围、当前层级、证据窗口、未覆盖项和失效条件。禁止把测试数量、当前切片或未来目标压缩成无边界的“已完成”。
