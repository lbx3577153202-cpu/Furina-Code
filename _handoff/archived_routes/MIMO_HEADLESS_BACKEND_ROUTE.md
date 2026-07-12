# MiMo 无界面自动调用后端路线

- **路线名称**: MiMo 无界面自动调用后端
- **用途**: 无人值守、定时分析、批量固定任务、机器自动验证
- **当前状态**: 暂停，不属于现阶段主线
- **暂停原因**: 当前直接使用 MiMo Code 更简单、更灵活
- **完整代码归档分支**: `archive/mimo-headless-e4`
- **完整代码归档 tag**: `archive-mimo-headless-e4-v0.1`
- **历史 PR**: #11 (MiMoCodeCLIAdapter 实现), #12 (Shadow E4 接线)

## 恢复条件

1. 出现明确无人值守任务
2. 本地持续生命系统已具备真实持续运行能力
3. 自动调用相比直接 MiMo Code 操作产生明确收益

## 恢复方式

从归档 tag `archive-mimo-headless-e4-v0.1` 定点提取 MiMo Adapter 和接线，不直接整分支合并。
