---
title: ChatGPT 项目来源替换指南
status: ACTIVE
authority: MAINTENANCE
version: 1.1
prepared_at: 2026-07-16
last_verified: 2026-07-16
authority_scope: chatgpt_project_source_replacement
implementation_authority: false
---

# ChatGPT 项目来源替换指南

## 1. 长期只保留一个活跃包

项目来源中长期只保留：

```text
FURINA_CODE_ACTIVE_SOURCE_PACK_CURRENT.zip
```

不要同时保留：

- 上一版 Active Source Pack；
- 带 `(1)` 的重复副本；
-完整整合包；
- Cold Archive；
- 解压后的同一套 Markdown 与 ZIP；
- 原始聊天导出、旧资源包和二进制原件。

## 2. 替换步骤

1. 在本地保存旧包，项目界面不是唯一备份；
2. 上传新的 `FURINA_CODE_ACTIVE_SOURCE_PACK_CURRENT.zip`；
3. 确认新包已经出现在项目来源；
4. 删除旧 Active Source Pack；
5. 确认来源列表中只有一个 Furina Code 活跃包；
6. 进行三项烟雾测试。

## 3. 烟雾测试

向 ChatGPT询问：

```text
1. Furina Code 当前初循环根关系是什么？
2. 当前 main 核验到哪个 HEAD，哪些能力仍未成立？
3. MiMo headless 路线当前是什么状态，什么条件下才能恢复？
```

应分别命中：

- `00_START_HERE.md`；
- `20_CURRENT_REALITY/`；
- `50_DECISIONS/` 和 `80_ARCHIVE_INDEX/`。

## 4. 更新时机

只有 ChatGPT明确判断“本轮变化已影响项目来源”时，才需要替换。

普通重构、未合并实验和不改变能力边界的内部测试，不需要频繁替换。

## 5. 代码事实边界

项目来源包不替代 GitHub。涉及当前 HEAD、文件、PR、CI、测试和真实能力时，ChatGPT仍应重新核验仓库。

## 6. 替换失败时

若新包无法读取、结构异常或烟雾测试失败：

1. 保留当前项目来源；
2. 不同时上传多个候选修复包；
3. 回到本地版本化归档或上一个已验证 ZIP；
4. 修复后重新生成一个唯一 CURRENT 包。
