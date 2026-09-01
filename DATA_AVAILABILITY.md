# Data Availability

## 当前公开输入

仓库公开两类材料。`tests/fixtures/qdata_research_snapshot_v1/` 是 QData `research_snapshot_v1` 的确定性合成 fixture，包含 2 个标的、3 个交易会话，用于验证 schema、PIT cutoff、文件哈希、覆盖和 Agent 时序合同。[真实市场研究 receipt](evidence/pit_factor_replication_v1/receipt.json)只公开汇总统计、方案/代码身份与本地输入哈希，不公开供应商数据行。

fixture 的实验 verdict 固定为 `INSUFFICIENT_EVIDENCE`。它不证明真实行情正确、可获得、可交易、完整或有权再分发，也不提供策略表现证据。

真实市场 pilot receipt 保留历史 schema 标签 `REAL_MARKET_OOS_STATISTICS`，这里只解释为仓库内锁定测试窗统计，不解释为第三方预注册、长期真实样本外验证或此前未接触数据；`performance_claim`、`generalization_claim` 和 `usable_for_trading_decisions` 均为 false。`evidence/PUBLIC_EVIDENCE_STATUS.json` 由验证后的 pilot receipt 派生，是当前已运行证据的唯一公开状态；旧 registry/readiness 文件不作为状态来源。Stage-2 期刊研究尚未运行，当前为 `BLOCKED_FOR_STAGE2`，也没有可替代这一缺口的候选 registry 或 readiness 结果。

## 一并提供的材料

- `data_assets/templates/*.csv`：字段模板，不是数据样本或覆盖证明；
- `examples/strategy_specs/quality_value_momentum.json`：合成演示 spec；
- `tests/fixtures/QDATA_RESEARCH_SNAPSHOT_PROVENANCE.md`：fixture 来源与生成命令记录；
- `studies/pit_factor_replication_v1/plan.json`：锁定的 4×4 全结果披露方案；
- `studies/pit_factor_replication_v1/data_declaration.example.json`：本地来源、许可和价格语义声明模板；
- `studies/pit_factor_bias_decomposition_v2/`：未运行的 Stage-2 protocol、四输入 coverage gate、prior-exposure 与外部登记模板；
- `evidence/`：不含本机路径或原始行的规范化 receipt 与派生状态；
- 严格适配器和 verifier：消费前重新校验 snapshot，而不是信任文件名。

## 未提供或未确立

- 真实 A 股行情、财务、成分、行业、事件或交易约束历史库；
- 任何供应商/API 的凭据、授权、数据权利、许可或服务等级；
- 可再分发的全市场原始数据、完整 vintage/revision 历史和所有交易日的独立覆盖率证明；
- Stage-2 所需的 2009 warm-up、2010—2022 面板、官方 SSE/SZSE 日历、原始 `roeDiluted` 输入和已签署审阅/登记材料；
- PostgreSQL/ClickHouse 数据库快照或可复建的跨库生产状态。

QData 仓库记录的有界本地 selector/迁移测试只是其自身的限定证据；Agent 的离线路径不启动数据库，`cross-store transactions` 仍未验证。

公开 receipt 允许审阅者核对方案范围、代码 commit、输入身份、全部结果和主张边界；由于省略的授权数据无法从 checkout 恢复，它不是第三方独立重算。参见 [README](README.md) 与[历史证据说明](docs/legacy-evidence.md)。
