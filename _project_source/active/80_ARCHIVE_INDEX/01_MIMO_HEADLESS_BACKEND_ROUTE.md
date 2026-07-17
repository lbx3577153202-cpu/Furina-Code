---
title: MiMo 无界面自动调用路线归档
status: ARCHIVED
authority: ARCHIVE
version: 1.0
prepared_at: 2026-07-16
last_verified: 2026-07-12
authority_scope: mimo_headless_backend_route_history
implementation_authority: false

---

# MiMo 无界面自动调用路线归档

## 路线定义

由一个 Python 命令入口启动本机 MiMo CLI，要求 MiMo 输出固定 JSON，再由 Furina Code 的实验流程保存、校验和 finalize。

```text
python -m furina_code inspect prepare --backend mimo-cli
→ mimo run ... --format json
→ candidate.json
→ strict validation / finalize
```

## 它如何认证

实验代码本身不管理 API Key。它以 `credential_mode=inherit` 启动 MiMo CLI，由 MiMo CLI 复用其自身登录状态、环境变量或本地凭证。该认证路径没有在当前 main 中形成产品级真实验证。

## 实际完成

- `MiMoCodeCLIAdapter`；
- probe / prepare / invoke / collect / strict_validate；
- fresh temporary CWD；
- `shell=False`；
- stdout/stderr 限制；
- timeout 和进程树终止；
- Windows `.cmd` 启动兼容；
- Shadow E4 固定 JSON 候选路径；
- mock 和 CI 测试。

## 为什么退出当前主线

用户当前可直接通过 MiMo Code 使用 MiMo AI，效果更灵活。实验路线只增加固定自动化和机器校验，不会让 MiMo Code 成为承载本地持续生命系统的 Furina Code 入口，且在当前没有无人值守需求时收益低。

## 保存位置

```text
archive branch: archive/mimo-headless-e4
archive tag: archive-mimo-headless-e4-v0.1
archive head: aa31f8e16f00f7cfd743b35919ac308bf550de89
PR #12: closed without merge
PR #13: cleanup merged
main cleanup commit: 2a221ccd129507f0d32bccdacb3a8246a2c90b63
```

## 当前禁止

- 不把它称为 MiMo Code 接入完成；
- 不在当前 main 恢复 Adapter；
- 不继续修 `.cmd`、schema 或 provider 行为；
- 不用其测试证明产品入口；
- 不因“以后可能有用”继续扩建。

## 恢复条件

见 `50_DECISIONS/PDR-003_MIMO_HEADLESS_ROUTE_PAUSED.md`。
