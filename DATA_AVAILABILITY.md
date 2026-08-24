# Data Availability

## 当前公开输入

仓库只把 `tests/fixtures/qdata_research_snapshot_v1/` 作为维护中的研究输入。它是 QData `research_snapshot_v1` 的确定性合成 fixture，包含 2 个标的、3 个交易会话，用于验证 schema、PIT cutoff、文件哈希、覆盖和 Agent 时序合同。

fixture 的实验 verdict 固定为 `INSUFFICIENT_EVIDENCE`。它不证明真实行情正确、可获得、可交易、完整或有权再分发，也不提供策略表现证据。

## 一并提供的材料

- `data_assets/templates/*.csv`：字段模板，不是数据样本或覆盖证明；
- `examples/strategy_specs/quality_value_momentum.json`：合成演示 spec；
- `tests/fixtures/QDATA_RESEARCH_SNAPSHOT_PROVENANCE.md`：fixture 来源与生成命令记录；
- 严格适配器和 verifier：消费前重新校验 snapshot，而不是信任文件名。

## 未提供或未确立

- 真实 A 股行情、财务、成分、行业、事件或交易约束历史库；
- 任何供应商/API 的凭据、授权、数据权利、许可或服务等级；
- 全市场、退市样本、修订历史和所有交易日的覆盖率证明；
- PostgreSQL/ClickHouse 数据库快照或可复建的跨库生产状态。

QData 仓库记录的有界本地 selector/迁移测试只是其自身的限定证据；Agent 的离线路径不启动数据库，`cross-store transactions` 仍未验证。

历史本地输入及其生成报告被排除出当前公共表面，因为省略的数据无法让审阅者重建结论。参见 [README](README.md) 与[历史证据说明](docs/legacy-evidence.md)。
