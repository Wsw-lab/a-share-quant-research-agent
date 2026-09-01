# A-share Quant Research Agent

| 能力 | 证据级别 | 当前可复验证据与边界 |
|---|---|---|
| A 股研究/审计原型 | `implemented` | 规则化因子、组合约束、A 股交易摩擦与审计代码可导入；不是投顾、券商或实盘交易系统。 |
| `research_snapshot_v1` 严格输入 | `unit-tested` | QData 快照先由独立验证器校验 schema、文件集合、哈希、cutoff、PIT 可得性和覆盖，再规范化为 Agent 面板；异常输入 fail closed。 |
| 信号与成交时序 | `unit-tested` | 固定为“t 日收盘决策 → t+1 原始开盘参考 → 显式摩擦 → 成交”；不允许复权价充当成交价。 |
| 确定性跨仓实验与 receipt | `local-integration-tested` | 本地以同级 QData checkout 做过构建器字节比对；公开路径使用固定测试 SHA，产出可重复 receipt 并由独立命令复核。 |
| 锁定方案的真实市场因子统计 | `receipt-verified` | 公开 receipt 含 4735 个标的、3894242 行、18 个按月样本外截面及全部 16 个登记结果，并绑定方案、输入哈希与 Agent commit；原始授权数据不再分发，第三方不能仅靠 checkout 重算。 |
| 市场有效性与生产运行 | `open` | 可实施 alpha、跨时期泛化、多重检验后的发现、完整数据权利/覆盖、券商接入、实盘交易、容量与长期运行均未建立证据。 |

这是一个 A 股量化研究与失败审计原型。它把数据身份、信号可得时间、执行参考、交易摩擦和失败结论放进同一条可复验链，而不是展示一条无法从公开 checkout 重建的收益曲线。

## 全新 checkout 的唯一离线绿色路径

前置条件是从本项目规范 GitHub origin（`https://github.com/Wsw-lab/a-share-quant-research-agent.git`，等价 SSH URL 也可）取得的全新 checkout、Python 3.10–3.12，以及环境中已有 `numpy==2.0.2`、`pandas==2.3.3`。以下命令会先核对 origin；它们不访问行情服务、不需要私有数据或凭据，输出只写入临时目录和被忽略的 `.research-artifacts/`。

```bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
AGENT_CANONICAL_ORIGIN="https://github.com/Wsw-lab/a-share-quant-research-agent"
AGENT_CANONICAL_SSH_ORIGIN="ssh://git@github.com/Wsw-lab/a-share-quant-research-agent"
AGENT_ORIGIN="$(git remote get-url origin)"
case "$AGENT_ORIGIN" in
  "$AGENT_CANONICAL_ORIGIN"|"$AGENT_CANONICAL_ORIGIN.git"|"$AGENT_CANONICAL_SSH_ORIGIN"|"$AGENT_CANONICAL_SSH_ORIGIN.git"|git@github.com:Wsw-lab/a-share-quant-research-agent.git) ;;
  *) echo "Expected the canonical A-share Agent GitHub origin; got: $AGENT_ORIGIN" >&2; exit 2 ;;
esac
AGENT_RUN_ROOT="$(mktemp -d)"
trap 'rm -rf "$AGENT_RUN_ROOT"' EXIT
export PYTHONPATH=src
AGENT_SHA="$(git rev-parse HEAD)"

python3 examples/run_demo.py
python3 -m a_share_quant_agent.reproducible_experiment run \
  --snapshot-dir tests/fixtures/qdata_research_snapshot_v1 \
  --output-dir "$AGENT_RUN_ROOT/first" \
  --qdata-sha 1111111111111111111111111111111111111111
python3 -m a_share_quant_agent.reproducible_experiment run \
  --snapshot-dir tests/fixtures/qdata_research_snapshot_v1 \
  --output-dir "$AGENT_RUN_ROOT/second" \
  --qdata-sha 1111111111111111111111111111111111111111
diff -r "$AGENT_RUN_ROOT/first" "$AGENT_RUN_ROOT/second"
python3 -m a_share_quant_agent.reproducible_experiment verify \
  --output-dir "$AGENT_RUN_ROOT/first" \
  --expected-agent-sha "$AGENT_SHA" \
  --expected-qdata-sha 1111111111111111111111111111111111111111
python3 -m unittest discover -s tests -p 'test_*.py'
test -z "$(git status --short --untracked-files=all)"
```

`--qdata-sha` 在这里是显式的 fixture 仓库引用，receipt 会把它标成 `unverified_fixture_repository_reference`，不会伪装成已验证 checkout。若提供 `--qdata-checkout`，实验会要求规范仓库身份，并在无数据库子进程中重建快照，与传入 fixture 逐字节比较。

## 严格实验说明

公开严格实验只使用合成的 2 个标的、3 个交易会话。它验证：

- `research_snapshot_v1` 的精确文件、哈希、PIT cutoff 与字段语义；
- 收盘信号只能在下一会话以未复权 `open` 作为成交参考；
- 手数、现金、订单、成交、权益和显式成本之间的确定性关系；
- receipt、研究产物和仓库身份的绑定，以及篡改后的 fail-closed 验证。

它的强制结论是 `INSUFFICIENT_EVIDENCE`，原因包括合成数据、样本过小、无样本外验证、无统计推断和无绩效主张。该 receipt 不能用于投资或交易决策。

`examples/run_demo.py` 是另一个确定性合成引擎演示，只检查公开策略 spec 能走通执行与审计路径。它产生的本地报告属于运行时输出，不是历史表现证据。

## 锁定的真实市场样本外因子研究

[分析方案](studies/pit_factor_replication_v1/plan.json)固定了 4 个因子和 4 级偏差控制，不按结果选择“最佳策略”。本地授权数据覆盖 2023-01-03 至 2026-07-24；测试期为 2025-01-01 至 2026-06-30，共 18 个按月截面。公开的[完整 receipt](evidence/pit_factor_replication_v1/receipt.json)逐项报告 16 个登记单元，并绑定输入文件哈希、方案哈希和 Agent commit `cbf5414c2613032dfa29ef2c295c760a3f4769ef`。[唯一公开状态](evidence/PUBLIC_EVIDENCE_STATUS.json)为 `REAL_MARKET_OOS_STATISTICS`，只能由通过验证的 receipt 派生，不读取旧 registry/readiness 报告。

基于这条证据链撰写的 15 页英文 working paper 可直接查看 [PDF](docs/working-paper/A_Share_Factor_Replication_Working_Paper.pdf)，或下载[可编辑 DOCX](docs/working-paper/A_Share_Factor_Replication_Working_Paper.docx)。论文完整披露 16 个登记结果，并沿用 receipt 的三项主张边界；它不是额外的绩效证据源。

下表每格依次为“平均 rank IC / Newey-West t / top-quintile minus universe 20-session return”；没有挑选或高亮最佳单元。

| 变体 | ROE | Momentum 60d | Low volatility 20d | Composite |
|---|---:|---:|---:|---:|
| M0 naive | 0.0435 / 2.452 / 0.0056 | -0.0514 / -1.683 / 0.0076 | 0.0529 / 1.857 / -0.0104 | 0.0302 / 1.380 / 0.0050 |
| M1 PIT universe | 0.0461 / 2.629 / 0.0059 | -0.0495 / -1.622 / 0.0078 | 0.0550 / 1.936 / -0.0099 | 0.0332 / 1.532 / 0.0054 |
| M2 PIT publication | 0.0105 / 0.612 / -0.0011 | -0.0495 / -1.622 / 0.0078 | 0.0550 / 1.936 / -0.0099 | 0.0038 / 0.185 / -0.0001 |
| M3 audited lag | -0.0108 / -0.475 / -0.0039 | -0.0446 / -1.860 / 0.0086 | 0.0291 / 0.907 / -0.0142 | -0.0194 / -0.758 / -0.0034 |

最清楚的审计发现不是“哪个因子最好”，而是 ROE/composite 在按财报 `publishDate` 对齐后明显衰减，并在完整过滤和一会话滞后下改变符号。这支持“时间对齐会改变研究结论”的方法学判断，不构成显著性、可实施收益或泛化主张。方案的 `locked_at` 是仓库内声明，不是第三方时间戳预注册；因此它降低选择性披露风险，但不把本次结果包装成严格的事前发现。原始数据受许可限制，receipt 能验证内容身份和完整性，不能替代数据访问。

## 证据等级

- `implemented`：代码存在且当前可导入，不等于行为已充分验证。
- `unit-tested`：离线确定性单元或合同测试覆盖所述行为。
- `local-integration-tested`：维护者在本地跨模块或跨 checkout 跑通过有界测试；不代表托管服务或生产运行。
- `receipt-verified`：公开验证器接受规范化 receipt；证明记录自洽、范围完整且未扩大主张，不证明未公开原始数据本身正确。
- `open`：尚未建立可复验证据，不能对外作肯定结论。

仓库内 `.github/workflows/ci.yml` 定义了只读、离线研究验证 GitHub Actions 工作流，矩阵与 Python 3.10–3.12 元数据一致。这里仅声称工作流文件和命令在本地接受检查，不声称远端工作流已经运行；应以 GitHub 上真实的 run 记录为准。

## QData 关系与数据库边界

[QData](https://github.com/Wsw-lab/qdata-free-source-quant-research-db) 是上游数据仓库；Agent 的执行合同实验只接受其冻结 `research_snapshot_v1`，不从可变的 `latest` 查询开始。独立的因子研究读取已声明的本地文件并把哈希写入 receipt；这些文件没有完整 revision/vintage 历史，因此本研究不声称分析过“数据修订历史”。QData 当前公开 SDK 已为价格、复权因子和因子值提供严格 `latest`/`asof`/`vintage` 选择器，并在 SQL backend 通过 PostgreSQL 解析版本，但这不倒推本地导出文件拥有修订历史。Agent 的绿色路径和 CI 不启动数据库，也没有覆盖 query plans、故障恢复或 `cross-store transactions`。

真实免费/公开源的许可、归属、缓存、再分发、稳定性、限频、数据权利和覆盖率尚未由本仓库建立。模板只说明字段形状；它们不证明相应数据可获得、完整或可合法分发。

## 维护范围

当前维护且可作为命令或输入引用的公开表面只有：

- `examples/run_demo.py`；
- `examples/strategy_specs/quality_value_momentum.json`；
- `a_share_quant_agent.reproducible_experiment` 的 `run` / `verify` 命令；
- `a_share_quant_agent.confirmatory_study` 的 `run` / `verify` / `status` 命令；
- `studies/pit_factor_replication_v1/` 的锁定方案与数据声明模板；
- `evidence/pit_factor_replication_v1/receipt.json` 与由其派生的 `evidence/PUBLIC_EVIDENCE_STATUS.json`；
- `tests/fixtures/qdata_research_snapshot_v1/` 合成快照；
- `tests/` 离线 unittest。

包级 `__all__` 只列出支撑上述证据链的可导入模块。`ops` 与 `completion_readiness` 等旧模块仍可供源码审计，但不在维护 API 中；缺少显式 legacy 命令时会 fail closed，不会指向已删除的 runner。其他仍保留的研究模块和配置也不自动构成受支持命令或有效研究证据。旧脚本、生成报告和未随仓库提供的输入见[历史证据说明](docs/legacy-evidence.md)。

## 设计记录

- [信号与成交时序 ADR](docs/adr/0001-signal-and-fill-timing.md)
- [可复现研究链计划](docs/plans/2026-08-24-reproducible-research-chain.md)
- [历史证据说明](docs/legacy-evidence.md)

## 明确未覆盖

- 没有把真实 A 股样本外统计提升为可实施 alpha、统计显著性或跨时期泛化结论；
- 没有公开原始授权数据、完整 revision/vintage 历史或再分发权；
- 没有券商、订单路由、实盘交易或投资建议功能；
- 没有生产部署、服务等级、容量、性能、容灾或安全认证；
- 没有可从当前 checkout 精确复建的历史策略绩效，因此主叙事不发布历史指标。

本仓库未添加许可证；代码使用权仍需仓库所有者明确决定。
