---
title: PDR-001 后端是载体与入口
status: ACCEPTED
authority: PROJECT_DECISION
version: 1.0
prepared_at: 2026-07-16
last_verified: 2026-07-16
authority_scope: backend_role_and_dependency_direction
implementation_authority: true

---

# PDR-001：后端是现实载体与入口

## 状态

`ACCEPTED`

## 背景

项目已确定 Furina Code 由外置后端能力和本地持续生命系统耦合形成。一次错误开发把它解释成：

```text
本地 Furina Code Python 控制器
→ 调用 mimo run
→ 接收候选
```

这在技术上形成了一个 headless 自动化路径，但它假设本地系统先成为完整入口，再把后端当内部 provider，和用户当前通过 MiMo Code 作为现实入口工作的目标不一致。

## 决定

1. 后端（如 MiMo Code）是 Furina Code 的现实交互入口、认知载体和代码行动载体；
2. 本地持续生命系统在同一闭环中提供持续自我、用户方向、任务、现实、权威、证据、完成和经验；
3. 后端仍然不是生命权威，后端会话不能直接改写正式状态或自证完成；
4. Adapter 的职责是隔离供应商/协议差异、控制披露和接收候选，不决定产品入口必须采用反向 subprocess 调用；
5. 在产品入口耦合设计形成前，不继续扩展具体 provider 的 headless 自动调用。

## 接受的结构

```text
用户
↓
MiMo Code / 其他现实后端入口
↓
后端认知与行动能力 × 本地持续生命系统
↓
真实项目责任闭环
```

## 拒绝的默认结构

```text
假设完整的本地 Furina Code 主程序
↓
subprocess / API 调用某个 coding backend
↓
把返回结果当成“后端接入完成”
```

该结构未来可作为无人值守执行模式，但不是当前产品入口主线。

## 后果

- 当前设计必须优先回答“后端运行时如何加载和服从本地生命状态”；
- BackendPort 可保留为通用隔离基础，但不能自动推动多 provider 扩展；
- 任何新的后端接入任务必须先说明用户入口、持续状态载入和真实收益；
- P2/P3 的 Adapter 术语按本决定解释。

## 重新审议条件

只有当产品明确需要无界面服务、定时任务或服务器运行，并且本地生命系统已能持续运行时，才可增加第二入口模式；不能因此否定后端作为交互载体的主线。
