# Project Portfolio Boundary

## 项目定位

这是一个 A 股研究/审计原型，而不是已部署的交易产品。公开价值集中在一条可检查的研究链：QData `research_snapshot_v1` 冻结输入与独立验证、Agent 的收盘信号/下一会话原始开盘执行、显式摩擦、确定性产物和失败判定。

## 当前能证明什么

- `implemented`：研究 spec、回测、审计、QData 严格适配器和 receipt 生成器存在并可导入。
- `unit-tested`：时间可得性、下一会话成交、交易约束、快照拒绝条件和 receipt 语义由离线测试覆盖。
- `local-integration-tested`：严格合成 fixture 可运行两次并产生相同字节，receipt 可独立验证；同级 QData checkout 模式还会重建并逐字节比较 fixture。
- `receipt-verified`：锁定因子方案在本地授权 A 股数据上产生 18 个按月测试窗截面，全部 16 个登记结果随输入哈希和代码 commit 公开；这是已观察的 pilot，不是外部预注册或长期样本外泛化证据，验证也不等于原始数据可公开重算。
- `open`：可实施市场 alpha、样本外泛化、多重检验后的发现、完整数据权利/覆盖、数据库生产拓扑、券商与实盘交易。

严格实验固定为合成的 2 个标的和 3 个交易会话，结论必须是 `INSUFFICIENT_EVIDENCE`。它证明的是时序与审计合同，不是策略收益，也不能用于交易决策。

独立的真实市场 pilot 把 4 个因子和 4 个偏差控制变体视为一组完整的敏感性分析，不挑最佳结果。当前最有力的结论是 recorded-publication 对齐会明显改变短样本中的 ROE/composite 统计；这是一项方法学审计发现，不是策略晋级。其唯一状态来自[验证后的 receipt](evidence/PUBLIC_EVIDENCE_STATUS.json)，旧 registry/readiness 不参与当前结论。Stage-2 的 2010—2022 期刊研究尚未运行，缺少官方日历、完整历史输入、签署审阅与外部登记，因此保持 `BLOCKED_FOR_STAGE2`。其执行器已把唯一 primary、固定 BH-28 family、三段共同支持分解、无收益 publication-exposure diagnostics 和逐证券端点 reason ledger 固化为 fail-closed 合同，但这些实现不替代尚未获得的历史数据与外部注册。

## 可审阅的工程判断

- 信号使用 t 日收盘后可得信息，成交最早发生在 t+1；
- 成交参考使用未复权开盘价，复权序列不能冒充真实成交价；
- 不可交易、涨跌停、上市状态和手数约束以显式失败或未成交记录处理；
- 输入 snapshot、两个仓库身份、策略配置、输出哈希和 verdict 绑定到同一 receipt；
- 验证器不只复核哈希，也复核固定语义与文件对象一致性。

## 不作为申请证据的内容

历史生成报告、生产导入清单和旧示例依赖的输入未随仓库提供，也不是修正后引擎的证据。当前只发布新锁定研究的全量统计 receipt；因为原始数据受许可限制，checkout 可验证 receipt，但不能重算其数据行。详见[历史证据说明](docs/legacy-evidence.md)。

## 复现入口

唯一绿色路径在 [README](README.md)；公共合同可用 `python3 -m unittest -v tests.test_public_surface_contract` 检查。上游数据合同来自 [QData](https://github.com/Wsw-lab/qdata-free-source-quant-research-db)，但 QData 的局部 PostgreSQL/ClickHouse 集成证据不等于 Agent 已运行数据库生产链，`cross-store transactions` 仍是开放工作。

本项目没有券商接入、实盘交易、投资建议或托管服务证据。真实来源的数据权利、许可、覆盖率和稳定性需要逐源重新验证。
