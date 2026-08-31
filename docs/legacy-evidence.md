# 历史证据说明

旧的 readiness、strategy-factory、生产导入输出和依赖缺失模块的示例已从当前公开表面移除；它们仍可在 Git history 中追溯。

当前树保留少量 operations/readiness 源码供审计，但不通过包级 `__all__` 发布。旧 scheduler 不再假定一个仓库中不存在的默认 runner，旧 completion-readiness builder 也会显式 fail closed；被移除 runner 专用的 daily-pipeline 配置不再出现在当前树中。

这些文件记录的是较早工作区状态，包含未随仓库提供的本地数据或运行上下文。由于省略的输入无法由审阅者从 fresh checkout 重建，它们不能验证修正后的执行引擎，也不能支持市场有效性、策略表现或生产能力结论。

当前证据入口以 [README](../README.md) 为准：合成 demo 与严格 QData fixture 走唯一离线绿色路径；锁定真实市场因子研究另有绑定输入哈希、方案和代码 commit 的新 receipt。当前公开状态只从这个通过验证的 receipt 派生，不从历史 readiness 或 registry 推断。新 receipt 仍不公开授权原始数据，也不声称拥有完整 revision/vintage 历史。
