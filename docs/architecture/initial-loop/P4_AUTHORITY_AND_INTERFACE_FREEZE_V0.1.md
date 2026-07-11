# Furina-Code 初循环权威与接口冻结规范 V0.1

> **文档状态**：P4 正式冻结稿。后续 P5–P8 可以实现、验证和提出修订，但不得静默改变本文权威边界。  
> **冻结日期**：2026-07-11。  
> **上位输入**：《初循环工程基线与五系统器官候选总图 V0.1》与《初循环组织层蓝图 V0.1》。  
> **适用范围**：Furina Code 初循环；不自动扩展到成熟版、多用户、多项目并发或云端自治。  
> **真实性声明**：本规范冻结的是工程契约，不代表这些契约已经编码或通过真实验证。

---

## 0. 规范语言与冻结规则

本文使用：

- **必须 / MUST**：初循环实现不得违反；
- **禁止 / MUST NOT**：违反即构成权威或真实性缺陷；
- **应当 / SHOULD**：原则上遵守，偏离必须留下设计决定和证据；
- **可以 / MAY**：不影响冻结边界的实现选择。

P4 冻结以下内容：

1. 权威根及其相互关系；
2. 正式对象的唯一拥有器官和唯一写入入口；
3. 正式对象的最低字段语义；
4. 任务、动作、授权、恢复、验证/完成和经验状态机；
5. 十一项跨组织协议的请求、响应和拒绝语义；
6. 幂等、并发、版本、未知副作用和证据完整性规则；
7. `IL-G0–IL-G9` 的可执行断言。

P4 不冻结编程语言、数据库、工作流框架、哈希算法、模型供应商、Git 库或传输协议；这些属于 P6。

---

## 1. 初循环权威宪法

### 1.1 五类权威根

| 权威根 | 能决定什么 | 不能决定什么 | 本地承载方式 |
| --- | --- | --- | --- |
| `U 用户方向与授权` | 用户想要什么、接受什么范围、何时修订/撤回授权。 | 不能把尚未发生的项目状态说成事实；也不能使系统绕过不可覆盖的安全边界。 | 原始意图引用、用户修订、授权来源引用。 |
| `R 项目现实` | 文件、Git、环境、命令、测试和实际差异目前是什么。 | 不能解释用户意义、授权行动或自行宣布完成。 | I3 的快照、动作收据与现实对账。 |
| `S 安全与责任不变量` | 哪些动作必须拒绝、暂停、降权或要求人工介入。 | 不能创造用户目标，也不能伪装成用户授权。 | I4 的策略版本、判断与强制 Gate。 |
| `E 证据与验证` | 哪些成功条件已被支持、失败、未覆盖或仍不确定。 | 不能修改项目事实或补造缺失证据。 | I4 的证据谱系、验证与完成裁决。 |
| `X 经验建议` | 哪些历史路径可能适用、有哪些反例和风险。 | 没有授权、事实或完成权；不能直接触发工具。 | I5 的经验候选、匹配和生命周期记录。 |

### 1.2 权威关系

1. `U` 定义方向与可接受边界；`S` 可以收窄或拒绝行动，但不能扩大 `U`。
2. `R` 可以使计划、票据、检查点和经验失效，但不能消灭用户原意。
3. `E` 依据 `U` 的成功条件和 `R` 的事实裁决完成度；后端自述不属于独立权威根。
4. `X` 只能进入 I2 的候选上下文；每次使用仍须重新经过 `R → S → E`。
5. 用户撤权立即优先于尚未开始的新动作；已发生或结果未知的副作用必须进入对账/恢复，不能假装撤回即可抹除。

### 1.3 权限角色

| 角色 | 定义 |
| --- | --- |
| `SOURCE` | 原始权威来源，例如用户对意图和授权的表达。 |
| `OWNER` | 正式对象唯一写入器官；负责创建新修订和发布正式事件。 |
| `PROPOSER` | 可以提交请求或候选，但不能写正式结论。 |
| `EXECUTOR` | 在有效 Gate 下产生外部副作用或观察事实。 |
| `EVALUATOR` | 对材料进行验证或裁决，但不能改写材料。 |
| `READER` | 读取满足范围和披露要求的对象。 |

任何外部模型、数据库、工作流引擎、Git 工具或适配器最多是 `PROPOSER`、`EXECUTOR` 或技术承载者，永远不是用户意图、项目完成或生命连续性的 `SOURCE/OWNER`。

---

## 2. 所有正式对象的公共契约

### 2.1 `CanonicalMeta` 最低字段

每一个正式对象修订版 MUST 包含：

| 字段 | 含义 | 规则 |
| --- | --- | --- |
| `schema_version` | 对象契约版本。 | 必填；未知主版本 MUST 拒绝写入。 |
| `object_type` | 正式对象类型。 | 必填；与协议允许类型一致。 |
| `object_id` | 对象稳定 ID。 | 同一对象跨修订不变。 |
| `revision` | 从 1 开始递增的修订号。 | 禁止跳过冲突覆盖；每次正式修改 +1。 |
| `owner_organ` | P2 冻结的唯一拥有器官。 | 请求方与拥有器官不匹配 MUST 拒绝。 |
| `run_binding_id` | 所属主体—用户—项目—任务绑定。 | 除全局后端能力档案外必填。 |
| `task_id` / `task_run_id` | 所属任务与运行。 | 与任务无关的少数对象可空，但必须说明。 |
| `project_ref` | 目标项目稳定引用。 | 涉及项目事实/行动时必填。 |
| `correlation_id` | 同一纵向任务事务的关联 ID。 | 必填。 |
| `causation_ref` | 直接导致本对象产生的请求/对象/事件。 | 除根对象外必填。 |
| `created_at` / `recorded_at` | 发生与本地记录时间。 | 使用明确时区；排序以事件序列/修订为准。 |
| `classification` | 数据分类。 | `public/project_internal/sensitive/secret` 之一。 |
| `integrity_ref` | 内容完整性引用。 | 算法 P6 选择；语义在 P4 冻结。 |
| `supersedes_ref` | 被本修订替代的前一修订。 | revision > 1 时必填。 |

### 2.2 正式修订规则

1. 已发布修订 MUST 视为不可变；修改产生新修订，不原地改历史。
2. 所有写入 MUST 提供 `expected_revision`；不匹配返回版本冲突，禁止 last-write-wins。
3. 对象拥有器官是唯一可创建新修订的责任方；组织/数据库只执行拥有器官的合法写入命令。
4. 删除正式历史采用逻辑失效、废止或受控删除事件；敏感数据依法/按用户要求物理删除时，必须留下不含原文的删除证明。
5. 一个对象被新对象取代时使用 `supersedes_ref`，禁止覆盖旧结论使其像从未存在。

### 2.3 `EventEnvelope` 最低字段

所有正式变化 MUST 同时发布事件：

`event_id, event_type, sequence, aggregate_ref, aggregate_revision, producer_organ, run_binding_id, task_run_id, correlation_id, causation_ref, occurred_at, recorded_at, payload_ref, integrity_ref`

事件追加与对象修订在逻辑上 MUST 同生共死：二者若无法确认一致，则对象进入 `integrity_uncertain`，相关任务 MUST 暂停并进入恢复审查。

### 2.4 数据分类与披露

| 分类 | 默认披露范围 |
| --- | --- |
| `public` | 可进入经批准的外置后端上下文。 |
| `project_internal` | 仅在任务最小必要范围内进入后端；必须记录披露对象和目的。 |
| `sensitive` | 默认不外发；确需外发必须有明确授权和脱敏策略。 |
| `secret` | 禁止进入模型上下文、普通日志和证据正文；只允许受控引用或凭证代理。 |

---

## 3. 正式对象目录与唯一写入入口

### 3.1 O1：生命谱系对象

| 正式对象 | OWNER | 最低业务字段 | 唯一写入入口 | 终结/失效方式 |
| --- | --- | --- | --- | --- |
| `RunBinding` | I1-A | `subject_ref,user_ref,project_ref,task_ref,allowed_tool_classes,status,source_refs` | `Create/ReviseRunBinding`（内部）+ `RegisterObject` | `revoked/closed/superseded` |
| `ContinuityView` | I1-B | `last_event_sequence,task_phase,task_disposition,open_request_refs,unresolved_action_refs,source_cursor` | 仅由已接受事件重建/刷新 | 可重建；不得作为原始权威 |
| `Checkpoint` | I1-C | `task_revision,phase,disposition,event_cursor,pending_requests,pending_actions,snapshot_ref,ticket_refs,reason` | O2 触发 `CreateCheckpoint` | 新检查点取代；旧检查点保留 |
| `RecoveryVerdict` | I1-C | `checkpoint_ref,fresh_snapshot_refs,receipt_refs,ticket_review,outcome,resume_phase,required_steps,reason` | `RequestRecoveryReview` 完成后写入 | 不可变；新审查产生新裁决 |
| `EventEnvelope` | 对应对象 OWNER | 见 2.3 | `PublishEvent` | 追加式；仅受控删除敏感载荷 |

### 3.2 O2：任务运行对象

| 正式对象 | OWNER | 最低业务字段 | 唯一写入入口 | 终结/失效方式 |
| --- | --- | --- | --- | --- |
| `TaskDossier` | I2-A | `source_intent_ref,structured_goal,success_criteria,scope,exclusions,unknowns,risk_class,user_constraints,status` | `Create/ReviseTaskDossier`（内部） | `cancelled/fulfilled/superseded` |
| `TaskRun` | I2-D | `task_revision,phase,disposition,current_refs,open_requests,started_at,terminal_reason` | `ApplyRunTransition`（内部，受本文状态机约束） | disposition=`terminal` |
| `CandidateEnvelope` | I2-D | `candidate_type,backend_profile_ref,backend_session_ref,context_ref,content_ref,claimed_assumptions,requested_actions,received_at,status` | `RequestBackendCandidate` 成功后由 I2-D 接受登记 | `accepted/rejected/superseded/expired` |

### 3.3 O3：外部世界与行动对象

| 正式对象 | OWNER | 最低业务字段 | 唯一写入入口 | 终结/失效方式 |
| --- | --- | --- | --- | --- |
| `BackendProfile` | I2-B | `provider_ref,capabilities,limits,health,credential_mode,data_policy_ref,last_checked_at` | 后端能力登记/健康检查 | `unavailable/retired/superseded` |
| `ContextEnvelope` | I2-C | `task_revision,purpose,included_refs,redactions,classification_summary,disclosure_basis,backend_ref` | `RequestBackendCandidate` 前由 I2-C 固化 | 发送后不可改；可撤销后续复用 |
| `ProjectSnapshot` | I3-A | `observation_scope,git_ref,file_facts,environment_facts,blind_spots,observed_at,freshness_policy` | `ObserveProject` | 新快照取代；旧快照不可改 |
| `BoundActionPlan` | I3-B | `candidate_ref,task_revision,baseline_snapshot_ref,target_scope,operations,expected_diff,risk,rollback_or_compensation,preconditions` | `BindActionPlan`（内部） | 快照/任务/候选漂移即 `invalidated` |
| `ActionReceipt` | I3-C | `plan_ref,ticket_ref,idempotency_key,status,started_at,ended_at,tool_ref,raw_result_ref,exit_info,side_effect_assessment` | `ExecuteBoundAction` | 按动作状态机终结；历史不可改 |
| `RealityReconciliation` | I3-D | `plan_ref,receipt_ref,before_snapshot_ref,after_snapshot_ref,expected_diff,actual_diff,unexpected_changes,verdict` | `ReportActionOutcome` | 不可变；新观察可产生补充对账 |

### 3.4 O4：治理、证据与完成对象

| 正式对象 | OWNER | 最低业务字段 | 唯一写入入口 | 终结/失效方式 |
| --- | --- | --- | --- | --- |
| `AuthorizationDecision` | I4-A | `subject_ref,task_revision,plan_ref,snapshot_ref,policy_version,decision,conditions,reason,user_authority_refs` | `RequestAuthorization` | 不可变；变化产生新判断 |
| `AuthorizationTicket` | I4-B | `decision_ref,plan_ref,task_revision,snapshot_ref,scope,valid_from,expires_at,single_use,status,revocation_ref` | I4-B 依据 allow 决策签发 | 见票据状态机 |
| `EnforcementVerdict` | I4-B | `ticket_ref,plan_ref,current_snapshot_ref,decision,checked_at,reason` | `ExecuteBoundAction` 执行瞬间内部生成 | 不可变 |
| `EvidenceEnvelope` | I4-C | `claim_scope,source_refs,causal_links,integrity_status,redactions,retention_class,missing_evidence` | `ReportActionOutcome`/验证结果进入后封装 | 新证据产生新修订；不改原始材料 |
| `VerificationPlan` | I4-D | `task_revision,success_criteria_map,checks,required_evidence,independence_requirements,stop_conditions` | `CreateVerificationPlan`（内部） | 任务/现实变化可 `invalidated` |
| `VerificationVerdict` | I4-D | `plan_ref,evidence_refs,criterion_results,coverage,failed_checks,unknowns,outcome,reason` | `RequestVerification` 收齐结果后写入 | 不可变；补证产生新裁决 |
| `CompletionVerdict` | I4-E | `task_revision,verification_ref,reconciliation_refs,outcome,completed_items,incomplete_items,unverified_items,residual_risks,user_effect` | `IssueCompletionVerdict` | 不可变；新证据只能 supersede |

### 3.5 O5：经验对象

| 正式对象 | OWNER | 最低业务字段 | 唯一写入入口 | 终结/失效方式 |
| --- | --- | --- | --- | --- |
| `ExperienceCandidate` | I5-A | `source_completion_refs,success_and_failure_facts,lesson,applicability,contraindications,risk,confidence,status` | `SubmitExperienceCandidate` | 见经验状态机 |
| `ExperienceMatch` | I5-B | `task_revision,candidate_refs,match_reasons,mismatch_reasons,risk_warnings,recommendation` | `RecommendExperience` | 仅对该任务修订有效 |
| `TrialUseRecord` | I5-B | `experience_ref,task_revision,usage_mode,influence_ref,completion_ref,result` | 第二轮完成后登记 | 不可变 |
| `ExperienceLifecycleVerdict` | I5-C | `experience_ref,evidence_refs,previous_status,new_status,reason,user_revision_ref` | 多轮证据/用户决定后写入 | 不可变；驱动候选新修订 |

---

## 4. 唯一写入与访问矩阵

| 对象域 | SOURCE | OWNER | PROPOSER/EXECUTOR | EVALUATOR | 禁止跨写 |
| --- | --- | --- | --- | --- | --- |
| 用户原始意图 | 用户 | 用户；I2-A 保存引用 | 后端可提出解释候选 | I4 检查是否越界 | 系统不得改写原文。 |
| 运行绑定/连续性 | 用户/项目/任务引用 | I1-A/B/C | 各组织发布事件 | I1-C 恢复裁决 | I2 不能自称已恢复。 |
| 任务与候选 | 用户、后端候选 | I2-A/D | O3-C 传输候选 | I4 审查边界 | 后端会话不拥有任务。 |
| 项目现实/行动 | 项目环境 | I3-A/B/C/D | 工具作为 EXECUTOR | I4-D 评价证据 | I4 不改原始事实。 |
| 授权/证据/完成 | 用户授权、规则、事实 | I4-A/B/C/D/E | I2/I3 提交请求与材料 | I4 内部制衡 | I3 不能写完成。 |
| 经验 | 已裁决经历、用户修订 | I5-A/B/C | I2 请求建议 | I4 评价试用结果 | I5 不能写任务/授权。 |

所有越过 OWNER 的直接数据库写入、文件覆盖或框架状态修改，均视为 `AUTHORITY_VIOLATION`，即使数据内容“看起来正确”。

---

## 5. 冻结状态机

### 5.1 `TaskRun` 双轴状态机

任务运行由 `phase`（业务阶段）和 `disposition`（当前可推进性）共同决定。

#### Phase

`intake → observe → deliberate → authorize → act → reconcile → verify → adjudicate → terminal`

允许的回边：

| 当前 phase | 允许的下一 phase | 条件 |
| --- | --- | --- |
| `intake` | `observe` | `IL-G0/G1` 通过。 |
| `observe` | `deliberate` | 形成满足本轮需求的快照；盲区已显式记录。 |
| `deliberate` | `observe` | 候选需要补充现实。 |
| `deliberate` | `authorize` | 已形成 BoundActionPlan 或需要受控验证动作。 |
| `deliberate` | `verify` | 任务为只读且已明确记录“无项目副作用”；VerificationPlan 已形成。 |
| `authorize` | `deliberate` | 被拒绝且允许修改候选；不得静默放宽。 |
| `authorize` | `act` | 有效票据已签发。 |
| `act` | `reconcile` | 必须有 ActionReceipt，包括 `outcome_unknown`。 |
| `reconcile` | `deliberate` | 实际差异要求修订方案。 |
| `reconcile` | `verify` | 已形成现实对账且无未解决未知副作用。 |
| `verify` | `deliberate` | 验证失败但任务仍可继续修复。 |
| `verify` | `adjudicate` | 验证结论已形成，包括 fail/inconclusive。 |
| `adjudicate` | `deliberate` | 完成裁决为 partial/not_completed 且用户目标仍继续。 |
| `adjudicate` | `terminal` | 完成、取消或明确结束。 |

禁止跳过 `act → reconcile` 或 `verify → adjudicate`。只读任务可以没有 `act`，但必须从 `deliberate` 明确进入 `verify` 并留下“无副作用”理由。

#### Disposition

`active, waiting_user, external_blocked, paused, recovery_review, manual_intervention, terminal`

规则：

1. 只有 `active` 可以推进 phase；其他 disposition 只能记录诊断、接收解除条件或进入恢复。
2. `waiting_user/external_blocked/paused → active` 必须有解除事件和原 phase 保留。
3. 非正常退出、谱系不一致、动作结果未知或检查点漂移 MUST 进入 `recovery_review`。
4. `recovery_review → active/paused/manual_intervention/terminal` 只能由 `RecoveryVerdict` 驱动。
5. `manual_intervention` 不得自动返回 active；必须有用户/运维明确处理记录。

### 5.2 动作状态机

`proposed → bound → authorization_pending → authorized → executing → applied | not_applied | outcome_unknown → reconciled_expected | reconciled_divergent | compensation_pending → compensated`

旁路终态：`rejected, cancelled, expired`。

规则：

- `authorized → executing` 时票据 MUST 被单次消费并生成 EnforcementVerdict；
- `applied/not_applied/outcome_unknown` 都 MUST 进入 reconcile；
- `outcome_unknown` 禁止自动重试，先执行恢复审查和重新观察；
- `reconciled_divergent` 不能被当作成功；只能进入新方案、补偿、人工介入或完成裁决的未完成分支；
- `compensated` 表示执行过补偿，不表示恢复到完全相同现实，仍需新的 RealityReconciliation。

### 5.3 授权票据状态机

`active → consumed | revoked | expired | invalidated`

- 初循环票据 MUST 单计划、单快照、单任务修订、单次使用；
- `consumed` 在副作用开始前写入，而不是成功后；
- 任务修订、计划修订、快照漂移、策略版本失效或用户撤权使票据 `invalidated/revoked`；
- 票据失效后不得复活，只能重新判断并签发新票据；
- 撤权无法撤销已发生副作用，但 MUST 阻止尚未开始的新副作用。

### 5.4 恢复裁决枚举

`continue_no_replay, skip_confirmed_action, retry_confirmed_not_applied, compensate, pause, manual_intervention, cancel`

只有同时满足以下条件才能 `retry_confirmed_not_applied`：已有可信证据确认副作用未发生、原计划仍有效、新票据已签发、幂等/补偿策略允许。

### 5.5 验证与完成状态

`VerificationVerdict.outcome`：`pass, fail, inconclusive, not_run`。

`CompletionVerdict.outcome`：`completed, partially_completed, not_completed, manual_decision_required, cancelled`。

规则：

- `pass` 只表示 VerificationPlan 覆盖的条件通过；不自动等于 completed；
- 存在关键 `inconclusive/not_run` 时禁止 completed；
- `partially_completed` MUST 列出明确边界，不得作为“基本完成”的模糊替代；
- 同一任务修订可以有多个 CompletionVerdict，但新裁决 MUST supersede 旧裁决并说明新增证据。

### 5.6 经验状态机

`draft → candidate → trial_eligible → under_trial → reusable | conditional | degraded | frozen | retired`

- 单次经历最多进入 `candidate`；
- 至少一次独立第二轮验证才可进入 `reusable/conditional`；
- 反例可使任何非 retired 状态进入 `degraded/frozen`；
- 用户可直接要求 `frozen/retired`；
- `reusable` 仍然只允许进入候选上下文，不能跳过任何 Gate。

---

## 6. 跨组织协议公共信封

### 6.1 `ProtocolRequest`

所有请求 MUST 包含：

`protocol_name, protocol_version, request_id, idempotency_key, caller_org, caller_organ, run_binding_id, task_id, task_run_id, correlation_id, causation_ref, expected_revisions, issued_at, deadline, payload_ref, classification, authorization_context_ref`

### 6.2 `ProtocolResponse`

所有响应 MUST 包含：

`request_id, outcome, responder_org, responder_organ, observed_revisions, produced_refs, event_refs, started_at, completed_at, error, side_effect_status`

`outcome` 固定为：

`accepted, rejected, conflict, deferred, failed, outcome_unknown, manual_intervention_required`。

### 6.3 请求处理通则

1. 先验证 schema、调用者、绑定、范围、版本和数据分类，再执行业务逻辑。
2. `deadline` 到期不等于副作用未发生；涉及动作时返回 `outcome_unknown`。
3. 同一幂等键和同一规范化载荷 MUST 返回原结果；同一键不同载荷 MUST 返回 `IDEMPOTENCY_CONFLICT`。
4. 响应 MUST 指向产生的正式对象/事件，不得只返回自然语言“成功”。
5. 拒绝响应 MUST 给出机器可判定错误码和不泄露秘密的解释。

---

## 7. 十一项跨组织协议冻结

| 协议 | 前置条件 | 核心请求载荷 | 成功输出 | 幂等与副作用规则 |
| --- | --- | --- | --- | --- |
| `RegisterObject / PublishEvent` | 调用器官是对象 OWNER；expected_revision 匹配。 | 对象修订、事件、前序引用、完整性引用。 | ObjectRef、EventRef、新 revision。 | 对象修订与事件逻辑原子；重复发布返回原引用。 |
| `ObserveProject` | 有效 RunBinding、项目范围和观察目的。 | scope、requested_facts、freshness、sensitivity。 | 新 ProjectSnapshot。 | 只读；同 request 返回同快照，新观察必须新 request_id。 |
| `RequestBackendCandidate` | TaskDossier/BackendProfile/ContextEnvelope 有效；披露规则通过。 | candidate_type、context_ref、backend_ref、limits。 | CandidateEnvelope 或明确失败。 | 同键不重复调用后端；超时记录未知/失败，不把旧结果冒充新结果。 |
| `RequestAuthorization` | BoundActionPlan、TaskDossier、ProjectSnapshot 版本一致。 | plan_ref、subject、object/action/environment、user authority refs。 | AuthorizationDecision；允许时生成 Ticket。 | 无项目副作用；相同输入复用判断，不跨版本复用票据。 |
| `ExecuteBoundAction` | Task disposition=active、phase=act；票据 active；计划/快照未漂移。 | plan_ref、ticket_ref、execution limits。 | EnforcementVerdict、ActionReceipt。 | 项目副作用协议；票据单次消费；unknown 时禁止自动重试。 |
| `ReportActionOutcome` | ActionReceipt 已存在；拥有前后观察或未知说明。 | receipt_ref、before/after snapshot、expected/actual diff。 | RealityReconciliation、EvidenceEnvelope 修订。 | 只登记事实；重复报告去重；冲突报告进入完整性审查。 |
| `RequestVerification` | VerificationPlan 有效；必要行动有对应授权策略。 | verification_plan_ref、check_refs、evidence requirements。 | 检查收据、EvidenceEnvelope、VerificationVerdict。 | 验证副作用复用 ExecuteBoundAction 语义；不得建立旁路执行通道。 |
| `IssueCompletionVerdict` | Task/Verification/Reconciliation/Evidence 版本一致；无未解决关键 unknown。 | task_revision、verification_ref、evidence_set、scope。 | CompletionVerdict、TaskRun 转换建议。 | 同证据集去重；新证据必须新裁决并 supersede。 |
| `SubmitExperienceCandidate` | CompletionVerdict 已存在；允许学习和保留；已脱敏。 | completion/evidence refs、成功失败事实、限制。 | ExperienceCandidate draft/candidate。 | 不产生任务/项目副作用；相同证据集去重。 |
| `RecommendExperience` | 新 TaskDossier 有效；经验未 frozen/retired。 | task_revision、project conditions、risk constraints。 | ExperienceMatch。 | 只读建议；对任务修订绑定；任务改变后失效。 |
| `RequestRecoveryReview` | Task disposition=recovery_review；有检查点或明确缺失。 | checkpoint、event cursor、pending requests/actions、fresh observations。 | RecoveryVerdict。 | 同一 task_run 同时只允许一个活跃恢复审查；任何不一致 fail-closed。 |

### 7.1 协议调用方向冻结

- O2 可以编排请求，但不得伪造 O3/O4/O5 的响应。
- O3-C 只能返回候选；O3-P 只能返回事实、收据和对账。
- O4 是 Authorization/Verification/Completion 的唯一发布组织。
- O5 只能发布经验对象和建议。
- 所有组织向 O1 发布自身对象的正式事件；O1 不代发业务结论。

---

## 8. 错误、拒绝与重试语义

### 8.1 冻结错误码

| 错误码 | 含义 | 自动重试 |
| --- | --- | --- |
| `CONTRACT_INVALID` | schema、必填字段或类型错误。 | 禁止；修复请求。 |
| `AUTHORITY_VIOLATION` | 非 OWNER 写对象或越权调用。 | 禁止；安全事件。 |
| `BINDING_MISMATCH` | 用户/项目/任务/运行绑定不一致。 | 禁止；恢复/人工审查。 |
| `REVISION_CONFLICT` | expected_revision 与当前版本不符。 | 重新读取并重新判断，不能盲重试。 |
| `SCOPE_VIOLATION` | 超出任务、项目、工具或数据范围。 | 禁止；需要新授权/修订。 |
| `DISCLOSURE_DENIED` | 上下文披露违反分类或最小必要性。 | 禁止；缩小/脱敏后新请求。 |
| `AUTHORIZATION_DENIED` | 策略/用户边界不允许。 | 禁止原样重试。 |
| `TICKET_EXPIRED_OR_REVOKED` | 票据不再有效。 | 重新观察和判断后新票据。 |
| `REALITY_DRIFT` | 项目现实与绑定快照不一致。 | 禁止行动；重新观察/重建计划。 |
| `DEPENDENCY_UNAVAILABLE` | 后端、工具、存储暂不可用。 | 仅无副作用或已确认未开始时可有界重试。 |
| `DEADLINE_EXCEEDED` | 请求超时。 | 读请求可重试；动作进入 unknown 审查。 |
| `SIDE_EFFECT_OUTCOME_UNKNOWN` | 无法确认副作用是否发生。 | 严禁自动重试；恢复审查。 |
| `EVIDENCE_INSUFFICIENT` | 证据不足以支持验证/完成。 | 补证，不得改写结论。 |
| `INTEGRITY_UNCERTAIN` | 对象/事件/证据完整性无法确认。 | 暂停相关事务并恢复审查。 |
| `STATE_TRANSITION_INVALID` | 不允许的状态转换。 | 禁止；修正流程或进入人工审查。 |
| `IDEMPOTENCY_CONFLICT` | 同一幂等键出现不同载荷。 | 禁止；安全/一致性审查。 |
| `MANUAL_INTERVENTION_REQUIRED` | 自动系统无法安全裁决。 | 禁止自动重试。 |

### 8.2 重试分级

| 等级 | 场景 | 规则 |
| --- | --- | --- |
| `R0 不可自动重试` | 越权、范围、披露、状态、证据、人工介入。 | 必须改变请求条件或由用户/人工处理。 |
| `R1 安全读重试` | 无副作用观察、健康检查。 | 使用新 request_id；有界次数；结果形成新快照。 |
| `R2 幂等协议重放` | 正式对象登记、已知幂等后端请求。 | 使用原 idempotency_key 和相同载荷，只取回原结果。 |
| `R3 副作用受控重试` | 仅 RecoveryVerdict=`retry_confirmed_not_applied`。 | 新票据；明确确认未发生；保留原动作链。 |

---

## 9. 并发、原子性与未知副作用冻结

### 9.1 初循环并发边界

1. 同一项目同一时刻最多一个 `executing` 写动作；重叠资源范围的写动作必须串行。
2. 同一 TaskRun 同一时刻最多一个活跃 RunTransition、一个活跃 RecoveryReview。
3. 只读观察可以并发，但每个 BoundActionPlan MUST 绑定一个明确快照；后续写动作前必须检查漂移。
4. 不同任务若指向同一项目，初循环仍共享项目写锁；不得因任务 ID 不同并发写入。
5. 任何并发扩展必须在成熟阶段重新经过权威与恢复设计，不能仅靠数据库锁放开。

### 9.2 逻辑原子性

- 正式对象新修订 + 对应 EventEnvelope MUST 逻辑原子；
- AuthorizationTicket 消费 + EnforcementVerdict + ActionReceipt(`executing`) MUST 在执行前持久化；
- 外部副作用本身无法与本地存储原子提交，因此必须采用“先记录意图，再执行，再记录收据，再观察”的冻结顺序；
- 任一步骤无法确认时不得回滚历史伪装未发生，应进入 unknown/recovery。

### 9.3 时钟与顺序

时间戳用于审计和票据过期；因果顺序以 `revision + event sequence + causation_ref` 为准。禁止只按机器时钟判断哪个正式事实更新。

---

## 10. 证据、隐私与保留规则

### 10.1 证据最低质量

每项用于验证/完成的证据 MUST 可回答：

1. 它证明哪个 claim/成功条件；
2. 谁/什么在何种任务、授权和项目现实下产生；
3. 原始材料在哪里，完整性如何；
4. 是否有盲区、失败、缺失或相反证据；
5. 是否经过独立于候选生成的评价步骤。

### 10.2 保留类别

`ephemeral, task_lifetime, project_history, experience_source, user_directed_delete`

- `secret` 不得因“证据完整”而写入普通证据正文；只保存受控引用；
- 经验来源保留前必须经过脱敏和用途允许；
- 用户要求删除时，O5 经验和后端上下文中的派生引用也必须进入影响检查；
- 原始后端思考过程不是完成所必需的正式证据，除非其具体输出成为候选/行动依据。

---

## 11. IL-G0–IL-G9 可执行断言

| Gate | MUST 全部为真 | 失败动作 |
| --- | --- | --- |
| `IL-G0 运行绑定` | RunBinding active；user/project/task 匹配；工具类别在范围内；无绑定冲突。 | disposition=`paused/manual_intervention`；禁止后续正式推进。 |
| `IL-G1 意图成案` | TaskDossier 含原意引用、成功条件、范围、排除项、未知项和任务修订；推断与原文分离。 | 回到 intake/waiting_user。 |
| `IL-G2 现实充分` | ProjectSnapshot 满足 freshness/scope；Git/文件/环境盲区已记录；关键盲区已处理或接受。 | 保持 observe；禁止写行动。 |
| `IL-G3 授权有效` | AuthorizationDecision=allow；Ticket active；计划/任务/快照/范围一致；执行瞬间 EnforcementVerdict=allow。 | rejected/paused；禁止执行。 |
| `IL-G4 候选受限` | BackendProfile 可用；ContextEnvelope 披露合规；CandidateEnvelope 有来源/上下文/假设；状态仍为 candidate。 | 拒绝候选或缩小上下文重试。 |
| `IL-G5 行动可对账` | BoundActionPlan、单次票据、ActionReceipt、前后快照和 RealityReconciliation 均存在；无未解决 outcome_unknown。 | phase=reconcile 或 disposition=recovery_review。 |
| `IL-G6 证据充分` | VerificationPlan 映射全部成功条件；证据谱系完整；关键检查已运行；Verdict 非关键 inconclusive。 | 禁止 completed；补证或 not_completed。 |
| `IL-G7 完成诚实` | CompletionVerdict 引用当前任务修订、验证和对账；明确完成/未完成/未验证/风险；不存在后端自报替代。 | 退回 adjudicate；`EVIDENCE_INSUFFICIENT`。 |
| `IL-G8 中断可恢复` | Checkpoint/event cursor 可验证；所有 pending action 有收据或 unknown；已重新观察；票据已复核；RecoveryVerdict 存在。 | 保持 recovery_review/manual_intervention；禁止续跑。 |
| `IL-G9 经验可控` | 经验来自已裁决证据；状态可用；适用/不适用理由明确；只作为建议；第二轮重新通过 G2–G7。 | 忽略/降级/冻结经验；主任务无经验运行。 |

任何 Gate 的“通过” MUST 产生结构化 Gate 结果引用；布尔值 `true` 无依据时不构成通过。

---

## 12. 接口版本与兼容性

1. 初始协议版本统一从 `1.0` 开始；对象 schema 单独版本化。
2. 新增可选字段属于兼容变更；改变字段语义、必填性、状态枚举或权威 OWNER 属于不兼容变更。
3. 不兼容变更 MUST 提升主版本并提供迁移/拒绝策略；未知主版本 fail-closed。
4. 状态枚举接收方遇到未知值不得默认映射为成功/active；必须 deferred 或 manual intervention。
5. 修改 OWNER、Gate 或禁止跨写规则必须重新进入设计冻结，不得作为普通实现重构。

---

## 13. P4 冻结后的仓库契约位置

P5/P7 实现时至少应形成以下逻辑契约文件；具体格式由 P6 技术选型决定：

```text
docs/contracts/
├─ authority-constitution.md
├─ object-catalog.md
├─ task-state-machine.md
├─ action-and-ticket-state-machines.md
├─ recovery-contract.md
├─ verification-and-completion-contract.md
├─ experience-state-machine.md
├─ protocols-v1.md
├─ errors-and-retries.md
└─ il-gates.md

src/furina_code/contracts/
├─ objects/
├─ events/
├─ protocols/
├─ states/
└─ errors/
```

`src/furina_code/contracts` 只能表达本文契约和验证，不得包含绕过五组织的万能写入服务。

---

## 14. P4 冻结裁决

### 14.1 已冻结

- 五类权威根及其优先关系；
- 正式对象公共元数据、不可变修订和单一 OWNER 原则；
- 25 类核心正式对象及唯一写入入口；
- TaskRun 双轴状态机、动作、票据、恢复、验证/完成与经验状态机；
- 十一项协议的前置条件、输入、输出、幂等和副作用语义；
- 17 类错误、四级重试规则、项目写串行与逻辑原子顺序；
- 数据分类、证据质量、保留类别和接口版本规则；
- `IL-G0–IL-G9` 的执行断言与失败动作。

### 14.2 尚未实现，因此不能声称

- 任何 schema、状态机或协议尚未成为运行代码；
- 逻辑原子性、幂等、写锁、恢复和完整性尚未通过故障注入；
- 具体存储、框架、SDK、沙箱和哈希算法尚未选择；
- Gate 断言尚未在真实任务中执行；
- P4 冻结不等于初循环能力成立。

### 14.3 冻结变更规则

后续若发现本规范无法支撑真实闭环，必须：

1. 提交明确冲突场景与证据；
2. 指出受影响的权威、对象、状态、协议和 Gate；
3. 形成版本化修订而不是静默编辑历史；
4. 重新运行相关契约、恢复和越权测试。

### 14.4 P5 的唯一任务

进入 `P5 最小纵向闭环设计`：选择一项有限风险的真实开发任务，只实现支撑该任务所需的最小对象字段、状态转换和协议切片，但必须完整穿过：

`运行绑定 → 任务成案 → 项目观察 → 后端候选 → 授权 → 受控行动 → 现实对账 → 验证 → 完成裁决 → 检查点/恢复 → 第二轮经验调用入口`

P5 可以裁剪功能深度，禁止裁剪权威链、现实对账、完成证据或未知副作用处理。
