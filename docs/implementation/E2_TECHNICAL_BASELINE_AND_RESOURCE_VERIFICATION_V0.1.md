# E2 技术基线与资源核验

**任务编号:** E2
**状态:** E2 实施文档
**日期:** 2026-07-11

---

## 1. 环境现实

| 项目 | 值 |
|------|-----|
| 操作系统 | Windows 10/11 (win32) |
| 架构 | x64 |
| 本地 Python 列表 | 3.11.9, 3.13.14 |
| 正式 E2 Python | 3.13.14 |
| pip | (venv 内版本) |
| setuptools | (构建时解析) |
| pytest | 9.1.1 |
| SQLite | (Python 内置) |
| Git | 2.54.0.windows.1 |
| main 基线 HEAD | 7da2c5819bbd3e0c3899a3f2b82d0d55e0ba5da2 |
| E2 分支 | e2/technical-baseline-resource-verification |

---

## 2. 能力来源矩阵

| 资源 | 引入方式 | 状态 |
|------|---------|------|
| CPython 标准库 | dependency / platform | 批准 |
| SQLite (Python sqlite3) | standard-library adapter | 批准 |
| Git CLI | wrapped_tool | 批准 |
| pytest 9.1.1 | dev dependency | 批准 |
| setuptools | build dependency | 批准 |
| Pydantic | dependency | 延后、未批准 |
| Pydantic AI | dependency | 延后、未批准 |
| Agent/工作流框架 | dependency | 禁止进入当前切片 |

---

## 3. 批准资源引入卡

### CPython 标准库

- **来源:** Python 官方发行版
- **实际版本:** 3.13.14
- **用途:** sqlite3, subprocess, pathlib, hashlib, json, tomllib 等基础能力
- **引入方式:** 平台内置，无需安装
- **许可证:** PSF License
- **安全与依赖面:** 无第三方依赖
- **P4 权威禁令:** 不能绕过 Gate 或对象拥有器
- **异常与降级方式:** N/A
- **替代和退出方案:** N/A
- **验收证据:** test_environment_baseline.py 中的导入和 SQLite 测试

### SQLite (Python sqlite3)

- **来源:** Python 标准库
- **实际版本:** 随 Python 3.13.14
- **用途:** 本地事务性存储
- **引入方式:** 标准库适配器
- **许可证:** Public Domain
- **安全与依赖面:** 无外部依赖
- **P4 权威禁令:** SQLite 不是正式状态权威
- **异常与降级方式:** 内存数据库用于测试
- **替代和退出方案:** N/A
- **验收证据:** test_environment_baseline.py 中的内存数据库测试

### Git CLI

- **来源:** Git 官方发行版
- **实际版本:** 2.54.0.windows.1
- **用途:** 项目观察（HEAD/status/diff）
- **引入方式:** 通过 subprocess 参数列表调用，shell=False
- **许可证:** GPLv2
- **安全与依赖面:** 独立安装
- **P4 权威禁令:** Git 不是项目现实裁决器
- **异常与降级方式:** N/A
- **替代和退出方案:** N/A
- **验收证据:** test_environment_baseline.py 中的 git --version 测试

### pytest 9.1.1

- **来源:** pytest-dev/pytest (GitHub)
- **实际版本:** 9.1.1
- **用途:** 开发验证测试运行
- **引入方式:** dev dependency
- **许可证:** MIT
- **安全与依赖面:** 纯 Python，无编译扩展
- **P4 权威禁令:** pytest 不是完成裁决器
- **异常与降级方式:** N/A
- **替代和退出方案:** N/A
- **验收证据:** 本地 pytest 运行通过

### setuptools

- **来源:** pypa/setuptools (GitHub)
- **实际版本:** >=75 (构建时解析)
- **用途:** Python 包构建后端
- **引入方式:** build dependency
- **许可证:** MIT
- **安全与依赖面:** 仅构建时使用
- **P4 权威禁令:** setuptools 不是运行时组成
- **异常与降级方式:** N/A
- **替代和退出方案:** N/A
- **验收证据:** editable install 成功

---

## 4. E3 接口边界（只设计不实现）

### LedgerPort

- **责任:** 追加事件到持久账本
- **输入:** EventEnvelope
- **输出:** 追加确认 + revision
- **失败类型:** 版本冲突、写入失败
- **禁止拥有的权威:** 不拥有事件解释权

### GitObservationPort

- **责任:** 观察 Git 工作区状态
- **输入:** 工作区路径、允许命令白名单
- **输出:** Git 状态快照
- **失败类型:** Git 不可用、路径不存在
- **禁止拥有的权威:** 不拥有项目现实裁决权

### CandidateInputPort

- **责任:** 从外部 JSON 接收候选行动
- **输入:** CandidateEnvelope JSON
- **输出:** 接受/拒绝 + 记录
- **失败类型:** 格式错误、版本不匹配
- **禁止拥有的权威:** 不拥有任务或行动权

### ControlledActionPort

- **责任:** 执行已批准的受控行动
- **输入:** ActionProposal
- **输出:** ActionReceipt
- **失败类型:** 权限不足、执行失败
- **禁止拥有的权威:** 不拥有执行决定权

### VerificationRunnerPort

- **责任:** 运行预先声明的验证
- **输入:** 验证命令列表
- **输出:** 验证结果
- **失败类型:** 命令失败、超时
- **禁止拥有的权威:** 不拥有完成裁决权
