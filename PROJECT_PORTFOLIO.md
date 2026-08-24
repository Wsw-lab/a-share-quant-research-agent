# Project Portfolio Boundary

## 项目定位

这是一个 A 股研究/审计原型，而不是已部署的交易产品。公开价值集中在一条可检查的研究链：QData `research_snapshot_v1` 冻结输入与独立验证、Agent 的收盘信号/下一会话原始开盘执行、显式摩擦、确定性产物和失败判定。

## 当前能证明什么

- `implemented`：研究 spec、回测、审计、QData 严格适配器和 receipt 生成器存在并可导入。
- `unit-tested`：时间可得性、下一会话成交、交易约束、快照拒绝条件和 receipt 语义由离线测试覆盖。
- `local-integration-tested`：严格合成 fixture 可运行两次并产生相同字节，receipt 可独立验证；同级 QData checkout 模式还会重建并逐字节比较 fixture。
- `open`：真实市场有效性、样本外泛化、统计推断、完整数据权利/覆盖、数据库生产拓扑、券商与实盘交易。

严格实验固定为合成的 2 个标的和 3 个交易会话，结论必须是 `INSUFFICIENT_EVIDENCE`。它证明的是时序与审计合同，不是策略收益，也不能用于交易决策。

## 可审阅的工程判断

- 信号使用 t 日收盘后可得信息，成交最早发生在 t+1；
- 成交参考使用未复权开盘价，复权序列不能冒充真实成交价；
- 不可交易、涨跌停、上市状态和手数约束以显式失败或未成交记录处理；
- 输入 snapshot、两个仓库身份、策略配置、输出哈希和 verdict 绑定到同一 receipt；
- 验证器不只复核哈希，也复核固定语义与文件对象一致性。

## 不作为申请证据的内容

历史生成报告、生产导入清单和旧示例依赖的输入未随仓库提供，也不是修正后引擎的证据。当前公开树不发布无法从本 checkout 重建的历史策略指标。详见[历史证据说明](docs/legacy-evidence.md)。

## 复现入口

唯一绿色路径在 [README](README.md)；公共合同可用 `python3 -m unittest -v tests.test_public_surface_contract` 检查。上游数据合同来自 [QData](https://github.com/Wsw-lab/qdata-free-source-quant-research-db)，但 QData 的局部 PostgreSQL/ClickHouse 集成证据不等于 Agent 已运行数据库生产链，`cross-store transactions` 仍是开放工作。

本项目没有券商接入、实盘交易、投资建议或托管服务证据。真实来源的数据权利、许可、覆盖率和稳定性需要逐源重新验证。
