---
title: PDR-004 活跃来源与冷档案分离
status: ACCEPTED
authority: PROJECT_DECISION
version: 1.0
prepared_at: 2026-07-16
last_verified: 2026-07-16
authority_scope: project_source_information_architecture
implementation_authority: true

---

# PDR-004：活跃来源与冷档案物理分离

## 状态

`ACCEPTED`

## 背景

旧项目资料同时包含：冻结规范、候选稿、旧仓库状态、完整对话、资源包、任务卡和二进制原件。将它们全部长期加载，会让检索把旧 HEAD、旧定义和错误路线当成当前事实。

## 决定

项目资料分为：

```text
Active Source Pack
= 当前理解、裁决和开发所需的精选来源

Cold Archive
= 原始历史、候选、旧包和二进制证据
```

Cold Archive 默认不上传到 ChatGPT 项目来源，不拥有当前裁决权。

## 进入活跃包的条件

文件必须至少满足：

- 有明确 authority_scope；
- 状态和新鲜度可判断；
- 与当前项目直接相关；
- 不与另一文件形成未解释的并列真相；
- 有来源或明确标记 SOURCE_GAP；
- 能帮助身份、现实、设计、决定或追溯中的至少一个领域。

## 后果

- 完整历史仍然保存；
- 日常上下文更小、更稳定；
- 旧材料需要通过 Provenance/Archive Index 才能进入当前讨论；
- 任何从 Cold Archive 恢复的内容都必须重新判断状态和权威范围。
