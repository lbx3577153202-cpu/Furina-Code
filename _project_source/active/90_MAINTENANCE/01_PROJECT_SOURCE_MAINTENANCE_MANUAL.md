---
title: Furina Code 项目来源持续维护说明书
status: ACTIVE
authority: MAINTENANCE
version: 1.1
prepared_at: 2026-07-16
last_verified: 2026-07-16
authority_scope: project_source_update_governance
implementation_authority: true
---

# Furina Code 项目来源持续维护说明书 V1.1

## 0. 目标

Furina Code 的项目来源不是一次生成后永久不变的静态资料，而是供用户、ChatGPT 和本地 AI 共用的**持续项目认知层**。

它必须同时保证：

1. 新对话能恢复正确的项目身份、主线和现实状态；
2. 工程变化后，旧资料不会继续冒充当前现实；
3. 冻结定义、当前设计、工程现实、成熟目标和历史档案不互相污染；
4. 更新复杂度由 ChatGPT 与本地 AI 内部吸收，用户只承担必要确认和单包替换。

## 1. 最终维护模型

```text
可维护的来源规范目录
        ↓
真实仓库核验
        ↓
定点更新
        ↓
自动校验
        ↓
重新构建 Active Source Pack
        ↓
用户替换 ChatGPT 项目中的唯一旧包
```

项目来源系统不是一个 ZIP，而是：

```text
规范目录
+
更新规则
+
构建与校验
+
版本归档
+
唯一活跃发布物
```

### 1.1 ZIP 不是编辑源

禁止把旧 ZIP 作为唯一原件，直接在压缩包内部零散替换文件。

正确方式：

```text
维护普通 Markdown 目录
→ 更新 Manifest
→ 运行质量校验
→ 重新构建 ZIP
```

### 1.2 活跃来源与冷档案分离

```text
Active Source Pack
= 当前理解和开发需要的高质量上下文

Cold Archive
= 原始聊天、旧资源包、旧候选稿、二进制原件和完整历史
```

ChatGPT 项目中长期只保留一个 Active Source Pack。Cold Archive 只在需要追溯原始证据时临时读取。

## 2. 两种更新模式

### 模式 A：ChatGPT 直接更新发布包

适用于：

- 当前 Active Source Pack 已上传；
- 改动范围明确；
- ChatGPT 能核验所需仓库事实；
- 用户希望立即得到新的可上传 ZIP。

流程：

```text
ChatGPT 读取当前包
→ 核验 GitHub / 已有证据
→ 定点修改来源文件
→ 运行完整性检查
→ 生成新 CURRENT.zip
→ 用户替换旧包
```

这种模式适合快速维护和文档治理，但不能代替本地工作树、未推送提交或私有运行状态的核验。

### 模式 B：本地规范目录维护

这是长期推荐模式。

本地仓库建议建立：

```text
Furina-Code/
└─ _project_source/
   ├─ active/
   ├─ templates/
   ├─ scripts/
   ├─ build/
   └─ local_archive/
```

本地 AI 读取真实工作树和 Git 历史，更新 `_project_source/active/`，运行脚本，再生成：

```text
FURINA_CODE_ACTIVE_SOURCE_PACK_CURRENT.zip
FURINA_CODE_ACTIVE_SOURCE_PACK_<DATE>_<HEAD7>.zip
```

ChatGPT负责审查 GitHub、更新内容和回传证据，用户只替换项目来源。

## 3. 三方职责

### 3.1 ChatGPT

负责：

- 判断是否触发来源更新；
- 指定受影响的权威领域和文件；
- 生成本地 AI 更新任务；
- 审查 PR、HEAD、CI、来源内容和 ZIP；
- 告诉用户本轮“需要替换”或“暂不需要替换”。

不得：

- 猜测当前 HEAD；
- 根据摘要伪造缺失冻结原稿；
- 把测试通过升级为产品能力；
- 未经用户确认改变项目根身份；
- 让旧来源覆盖实时仓库现实。

### 3.2 本地 AI

负责：

- 同步并核验本地 `main` 与远端；
- 读取真实代码、提交、测试、CI 和工作树；
- 定点更新来源规范目录；
- 保持冻结原稿字节不变；
- 运行结构、一致性、Hash、链接、隐私和 ZIP 校验；
- 生成 CURRENT ZIP 和版本化本地归档；
- 回传可核验证据，不只说“完成”。

### 3.3 用户

只需：

- 确认项目身份、根架构或重大方向变化；
- 替换 ChatGPT 项目中的唯一 Active Source Pack；
- 对真正存在的重大来源冲突作最终裁决。

## 4. 什么时候必须立即更新

当旧来源可能让下一次对话产生实质性错误判断时，必须更新。

一级触发包括：

1. 项目身份、根关系或不可突破原则变化；
2. 当前工程主线变化；
3. 重大路线被接受、暂停、拒绝或恢复；
4. 能力成熟度发生跨级：
   `DEFINED → IMPLEMENTED → TESTED → REAL_ENV_VERIFIED → PRODUCT_EXPOSED → USER_USABLE`；
5. 产品入口或用户可见能力变化；
6. 找回新冻结原稿或旧冻结稿被正式取代；
7. 当前来源出现事实错误、损坏 frontmatter、重复真相或错误 Hash；
8. 现有来源会把 TARGET、ARCHIVED 或历史证据误读为当前能力。

## 5. 什么时候可以批量更新

以下变化可在阶段结束时集中更新：

- 同一阶段内连续合并多个普通工程 PR；
- 测试数量变化，但能力成熟度没有变化；
- 内部实现细化，没有改变入口、主线或用户能力边界；
- 连续修复性提交；
- Evidence Index 需要补充多个提交；
- Current Reality 落后了若干重要提交。

推荐批量节点：

```text
一个工程阶段完成
或
3—5 个有实质内容的 PR 合并
或
准备进入下一轮重大设计前
```

项目没有实质变化时，不为刷新日期机械生成新包。

## 6. 什么时候不需要更新

通常无需更新：

- 拼写和排版修复；
- 不改变语义的重构；
- 单纯增加内部单元测试；
- 尚未合并的实验分支；
- Draft PR；
- 临时执行日志；
- 没有形成项目决定的失败尝试；
- 尚未被接受的探索性讨论。

## 7. 每次发布必须检查的文件

```text
00_START_HERE.md
20_CURRENT_REALITY/01_CURRENT_STATE_SNAPSHOT.md
20_CURRENT_REALITY/02_CAPABILITY_REALITY_LEDGER.md
20_CURRENT_REALITY/03_CURRENT_GAPS_AND_RISKS.md
20_CURRENT_REALITY/04_ENGINEERING_EVIDENCE_INDEX.md
50_DECISIONS/00_DECISION_INDEX.md
80_ARCHIVE_INDEX/00_ARCHIVED_ROUTES_INDEX.md
90_MAINTENANCE/*
99_INTEGRITY_MANIFEST.md
PACKAGE_QUALITY_AUDIT.md
```

“检查”不等于必须修改。确认仍然正确也应记录在本地 AI 回传中。

## 8. 事件与文件映射

| 事件 | 主要更新位置 |
|---|---|
| 新主线或架构决定 | `00_START_HERE`、`30_ACTIVE_DESIGN`、`50_DECISIONS` |
| 能力跨级 | `20_CURRENT_REALITY` |
| 路线暂停或恢复 | `50_DECISIONS`、`80_ARCHIVE_INDEX` |
| 冻结稿新增或替代 | `10_CONSTITUTION` / `11_FORMAL_BASIS`、Manifest |
| 历史解释改变 | `60_PROVENANCE` |
| 仅 HEAD/CI 变化 | Current State、Evidence Index、Manifest |
| 维护方式改变 | `90_MAINTENANCE` |

重大决定不得只静默修改总设计。退出路线不得从历史中消失，必须保留决定记录、归档索引和恢复条件。

## 9. 本地 AI 标准流程

### A. 确定范围

确认：

```text
update_reason
trigger_level
verified_repo_head
authority_domains_affected
files_expected_to_change
files_forbidden_to_change
```

范围不明确时 fail-closed，不得自行扩大到根身份。

### B. 核验现实

至少执行：

```text
git fetch origin
git switch main
git pull --ff-only origin main
git status --short
git rev-parse HEAD
git log --oneline --decorate -20
```

同时核验目标 PR、CI、测试、工作树和相关归档 branch/tag。

### C. 定点更新

规则：

- 只修改受影响文件；
- 冻结原稿不得原地修改；
- 快照写明 `last_verified`、`snapshot_head` 和证据窗口；
- 能力成熟度不得高于证据；
- TARGET 不得写成 CURRENT；
- 无法核验时标记 `UNKNOWN` 或 `SOURCE_GAP`；
- 历史 HEAD 必须明确标注为历史。

### D. 自动校验

必须覆盖：

- 必需目录和文件；
- frontmatter 可解析；
- 状态词合法；
- 入口、Current Reality、Evidence 和 Manifest 一致；
- 有效 PDR 与 Decision Index 一致；
- PAUSED / ARCHIVED 路线与 Archive Index 一致；
- 冻结文件 Hash 不变；
- 无重复内容；
- 无失效相对链接；
- 无私人绝对路径、凭证或密钥；
- ZIP 可解压；
- 解压后 Hash 与 Manifest 一致；
- 构建报告记录最终 ZIP Hash。

### E. 发布

生成：

```text
FURINA_CODE_ACTIVE_SOURCE_PACK_CURRENT.zip
FURINA_CODE_ACTIVE_SOURCE_PACK_<YYYY-MM-DD>_<HEAD7>.zip
SOURCE_PACK_RELEASE_REPORT.md
SHA256SUMS.txt
```

## 10. ChatGPT 审核

审核三层：

### 工程事实

- PR/commit 是否真实存在；
- HEAD、CI 和归档状态是否匹配；
- 是否夸大实现范围。

### 来源内容

- 主线是否与用户决定一致；
- Current Reality 是否保守；
- Capability Ledger 是否越级；
- 错误路线是否正确归档；
- 冻结原稿是否未变。

### 发布物

- ZIP 可解压；
- Manifest 正确；
- 无冷档案、重复包和敏感内容；
- `00_START_HERE` 能准确恢复项目；
- 项目来源中只需保留这一份包。

## 11. 更新决策检查

每轮重大工程工作结束后，ChatGPT内部检查：

```text
A. 项目身份是否变化？
B. 当前主线是否变化？
C. 能力成熟度是否跨级？
D. 产品入口是否变化？
E. 是否接受、暂停或恢复重大路线？
F. 是否找回或替代冻结来源？
G. 旧包是否会让新对话产生实质性错误判断？
```

判定：

```text
A—F 任一为 yes
→ 立即更新

A—F 均为 no，但 G 为 yes
→ 更新 Current Reality

全部为 no
→ 不更新
```

## 12. 低打扰原则

用户无需记忆触发条件。

以后由 ChatGPT在阶段收尾时直接给出：

```text
本轮变化已影响项目来源，建议更新 Active Source Pack。
```

或：

```text
本轮只改变内部实现，没有改变来源事实，暂不需要更新。
```

用户同意后，由 ChatGPT直接更新发布包，或生成本地 AI 任务卡。

## 13. 最终原则

```text
不是每次提交都更新
而是在项目理解可能实质变化时更新

不是直接修改 ZIP
而是维护规范目录并重新构建

不是让用户手工整理
而是 ChatGPT 判断、本地 AI 执行、用户替换

不是用来源包替代仓库
而是让来源包解释仓库现实、设计边界和决策历史
```
