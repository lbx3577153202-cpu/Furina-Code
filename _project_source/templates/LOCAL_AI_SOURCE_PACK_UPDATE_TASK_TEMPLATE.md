---
title: 本地 AI 项目来源包更新任务模板
status: ACTIVE
authority: MAINTENANCE
version: 1.1
prepared_at: 2026-07-16
last_verified: 2026-07-16
authority_scope: local_ai_source_pack_update_execution_template
implementation_authority: true
---

# 本地 AI：Furina Code 项目来源包更新任务模板

> ChatGPT 根据本轮变化填写尖括号内容后，交给本地 AI 执行。模板本身不等于一次具体授权。

```text
任务：更新 Furina Code Active Source Pack

update_reason:
  <本轮为什么需要更新>

trigger_level:
  IMMEDIATE | BATCHED

repository:
  E:\Furina-Code

expected_main_head:
  <当前预期 main HEAD；本地 AI 必须自行核验，不能盲信>

authority_domains_affected:
  - REALITY
  - DESIGN
  - DECISION
  - ARCHIVE
  <按实际保留>

must_review:
  - _project_source/active/00_START_HERE.md
  - _project_source/active/20_CURRENT_REALITY/
  - _project_source/active/50_DECISIONS/00_DECISION_INDEX.md
  - _project_source/active/80_ARCHIVE_INDEX/00_ARCHIVED_ROUTES_INDEX.md
  - _project_source/active/90_MAINTENANCE/
  - _project_source/active/99_INTEGRITY_MANIFEST.md
  - _project_source/active/PACKAGE_QUALITY_AUDIT.md

must_update:
  <明确列出必须修改的文件；没有则写 NONE>

must_not_modify:
  - 所有 *_FROZEN.md 原稿，除非任务明确提供新冻结版本
  - 任何 Cold Archive 原件
  - 项目身份和根关系，除非用户已明确接受变更

required_reality_checks:
  - git fetch origin
  - main 与 origin/main 对齐
  - 当前 HEAD
  - 目标 PR/commit
  - CI 状态
  - 测试结果
  - working tree
  - 相关 archive branch/tag

content_rules:
  - 不能用测试通过冒充产品能力
  - 不能把 TARGET 写成 CURRENT
  - 不能根据摘要伪造冻结原稿
  - 无法核验时写 UNKNOWN 或 SOURCE_GAP
  - 能力成熟度不得高于证据
  - 旧路线退出主线时必须保留 PDR 与 Archive Index

validation_required:
  - frontmatter_parse: PASS
  - required_files: PASS
  - cross_file_consistency: PASS
  - frozen_hashes: PASS
  - duplicate_hashes: NONE
  - broken_relative_links: NONE
  - sensitive_paths_or_secrets: NONE
  - manifest_match: PASS
  - zip_integrity: PASS
  - final_zip_hash_recorded: PASS

build_outputs:
  - _project_source/build/FURINA_CODE_ACTIVE_SOURCE_PACK_CURRENT.zip
  - _project_source/build/SOURCE_PACK_RELEASE_REPORT.md
  - _project_source/build/SHA256SUMS.txt
  - _project_source/local_archive/FURINA_CODE_ACTIVE_SOURCE_PACK_<DATE>_<HEAD7>.zip

git_process:
  - 创建 source/update-<date>-<reason> 分支
  - 只提交公开安全的 active/templates/scripts
  - 创建 PR
  - 不自动合并，除非任务另有明确授权

完成后只回传：

SOURCE_PACK_UPDATE_RESULT
status: READY_FOR_REVIEW | FAILED
reason:
repository:
base_main_head:
verified_main_head:
source_branch:
source_commit:
pr:
updated_files:
unchanged_but_reviewed_files:
frozen_files_changed: no | yes
capability_ledger_changes:
decision_changes:
archive_changes:
validation:
  frontmatter:
  required_files:
  consistency:
  frozen_hashes:
  duplicates:
  links:
  sensitive_content:
  manifest:
  zip_integrity:
current_zip:
current_zip_sha256:
versioned_archive:
working_tree:
blockers:
```
