# Furina Code 活跃来源完整性清单

**包版本：** 1.3  
**生成日期：** 2026-07-17  
**稳定发布名：** `FURINA_CODE_ACTIVE_SOURCE_PACK_CURRENT.zip`  
**工程现实快照：** `LOCAL_WORKING_TREE_AFTER_INITIAL_LOOP_V1`；Windows 本地全量 `405 passed`；本轮无新的 main SHA 或 CI run。  
**本次来源治理修订：** 初循环已建立的严格范围、证据与未覆盖边界进入活跃现实层；冻结原稿保持不变。

## 文件清单

| 路径 | 行数 | 字节 | SHA-256 |
|---|---:|---:|---|
| `00_START_HERE.md` | 85 | 4158 | `92f984a1b043f441ba515a441b725c9a69782817b126f8ef1c3d22bc3ad1e434` |
| `01_SOURCE_AUTHORITY_AND_CONFLICT_RULES.md` | 86 | 5327 | `562668dc4c59fa10ff0556dfb62c2afa9d506077754ff9692a5325c22cea184d` |
| `02_ACTIVE_SOURCE_FILE_MAP.md` | 35 | 1907 | `14fc54dae60913aaa6893af856083f53bf8340c0b8c0e71db5e39805e6afe786` |
| `10_CONSTITUTION/`（4 文件） | 368 | 15361 | 原始冻结/活跃哈希按下列冻结对账 |
| `11_FORMAL_BASIS/`（5 文件） | 6671 | 161858 | 原始冻结哈希保持匹配 |
| `20_CURRENT_REALITY/01_CURRENT_STATE_SNAPSHOT.md` | 73 | 3070 | `5a4c1a3f4f894d358daf991c535f8c82c25ed29e26da3185c1e7250b338ecc51` |
| `20_CURRENT_REALITY/02_CAPABILITY_REALITY_LEDGER.md` | 41 | 2456 | `ea1f4ed0dfc34dafc0c462bea132b062f1a186e44c158dc4cb4d54f9ee250702` |
| `20_CURRENT_REALITY/03_CURRENT_GAPS_AND_RISKS.md` | 64 | 2291 | `306c6256af16eee1bd0982133075c3f6c716f4803c018d46daaff79da1070d2c` |
| `20_CURRENT_REALITY/04_ENGINEERING_EVIDENCE_INDEX.md` | 42 | 2019 | `6715afd392ac27bf19b2a5484393372221a02381131776b3af5a29b45faf0539` |
| `20_CURRENT_REALITY/05_INITIAL_LOOP_ESTABLISHMENT_RECORD.md` | 53 | 2142 | `ac5fe00405dec88900ded8f518f0d7f2cdebf3f8ead9daf65d05c1b06d106d05` |
| `30_ACTIVE_DESIGN/`（3 文件） | 1071 | 24554 | 冻结初循环设计未修改 |
| `40_TARGET_DESIGN/`（2 文件） | 1083 | 21353 | 冻结成熟目标未修改 |
| `50_DECISIONS/`（6 文件） | 317 | 11074 | PDR 未修改 |
| `60_PROVENANCE/`（5 文件） | 297 | 16860 | 来源材料未修改 |
| `80_ARCHIVE_INDEX/`（3 文件） | 122 | 3864 | 归档索引未修改 |
| `90_MAINTENANCE/`（3 文件） | 570 | 15089 | 维护规则未修改 |
| `PACKAGE_QUALITY_AUDIT.md` | 33 | 1498 | `aadf81ffb73dbf001c0b4ed7fe83640f4a3eabad9da8927c0eff4587106d3552` |
| `SHA256SUMS.txt` | 43 | 7594 | 包内其余 43 个 Markdown 文件的逐文件校验值 |

## 冻结原稿对账

`11_FORMAL_BASIS/` 五份冻结正式原稿与 V1.2 包的对应字节 SHA-256 均为 `MATCH`。本轮没有修改冻结原稿；它们中的历史工程状态由最新 `20_CURRENT_REALITY/` 证据记录裁决。

## 维护与发布边界

- 本包是唯一应长期上传到 ChatGPT 项目来源的 Furina Code 活跃包；
- Cold Archive、旧 Active 包、完整整合包和重复副本不应同时加载；
- Manifest 证明包内内容完整性，不证明工程能力；能力范围以现实记录和可核验仓库为准；
- 本文件自身不列入 SHA 表；最终 ZIP 的 SHA-256 记录在包外同名 `.sha256` 文件。
