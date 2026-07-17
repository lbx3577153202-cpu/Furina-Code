---
title: 项目来源维护区索引
status: ACTIVE
authority: MAINTENANCE
version: 1.1
prepared_at: 2026-07-16
last_verified: 2026-07-16
authority_scope: project_source_maintenance_navigation
implementation_authority: false
---

# 项目来源维护区索引

本目录规定 Furina Code 项目来源怎样持续更新、构建、审查和替换。

| 文件 | 作用 |
|---|---|
| `01_PROJECT_SOURCE_MAINTENANCE_MANUAL.md` | 何时更新、由谁更新、怎样更新、怎样校验 |
| `02_LOCAL_AI_SOURCE_PACK_UPDATE_TASK_TEMPLATE.md` | ChatGPT 交给本地 AI 的标准更新任务模板 |
| `03_CHATGPT_PROJECT_SOURCE_REPLACEMENT_GUIDE.md` | 用户怎样在 ChatGPT 项目中只保留一个当前活跃包 |

## 维护总原则

```text
事件触发更新，而不是每次提交机械更新
维护普通目录，而不是直接编辑 ZIP
ChatGPT 判断与审查，本地 AI 核验与构建
用户只替换项目中的唯一 Active Source Pack
```

本目录只治理项目来源，不改变 Furina Code 当前工程主线。
