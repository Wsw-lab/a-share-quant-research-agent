# A-share Quant Research Agent

| 能力 | 证据级别 | 当前可复验证据与边界 |
|---|---|---|
| A 股研究/审计原型 | `implemented` | 规则化因子、组合约束、A 股交易摩擦与审计代码可导入；不是投顾、券商或实盘交易系统。 |
| `research_snapshot_v1` 严格输入 | `unit-tested` | QData 快照先由独立验证器校验 schema、文件集合、哈希、cutoff、PIT 可得性和覆盖，再规范化为 Agent 面板；异常输入 fail closed。 |
| 信号与成交时序 | `unit-tested` | 固定为“t 日收盘决策 → t+1 原始开盘参考 → 显式摩擦 → 成交”；不允许复权价充当成交价。 |
| 确定性跨仓实验与 receipt | `local-integration-tested` | 本地以同级 QData checkout 做过构建器字节比对；公开路径使用固定测试 SHA，产出可重复 receipt 并由独立命令复核。 |
| 市场有效性与生产运行 | `open` | 样本外、统计推断、真实数据覆盖、数据权利、券商接入、实盘交易、容量与长期运行均未建立证据。 |

这是一个 A 股量化研究与失败审计原型。它把数据身份、信号可得时间、执行参考、交易摩擦和失败结论放进同一条可复验链，而不是展示一条无法从公开 checkout 重建的收益曲线。

## 全新 checkout 的唯一离线绿色路径

前置条件是 Python 3.10–3.12，以及环境中已有 `numpy==2.0.2`、`pandas==2.3.3`。以下命令不访问行情服务、不需要私有数据或凭据；输出只写入临时目录和被忽略的 `.research-artifacts/`。

```bash
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

## 证据等级

- `implemented`：代码存在且当前可导入，不等于行为已充分验证。
- `unit-tested`：离线确定性单元或合同测试覆盖所述行为。
- `local-integration-tested`：维护者在本地跨模块或跨 checkout 跑通过有界测试；不代表托管服务或生产运行。
- `open`：尚未建立可复验证据，不能对外作肯定结论。

仓库内 `.github/workflows/ci.yml` 定义了只读、离线研究验证 GitHub Actions 工作流，矩阵与 Python 3.10–3.12 元数据一致。这里仅声称工作流文件和命令在本地接受检查，不声称远端工作流已经运行；应以 GitHub 上真实的 run 记录为准。

## QData 关系与数据库边界

[QData](https://github.com/Wsw-lab/qdata-free-source-quant-research-db) 是上游数据仓库；Agent 只接受它的冻结 `research_snapshot_v1`，不从可变的 `latest` 查询直接开始研究。QData 当前公开说明记录了有界的 PostgreSQL 16 selector 与 ClickHouse 24.8 迁移本地集成测试；Agent 的绿色路径和 CI 不启动数据库，也没有覆盖 query plans、故障恢复或 `cross-store transactions`。这些数据库结论属于 QData 的限定证据，不应转写成 Agent 的生产能力。

真实免费/公开源的许可、归属、缓存、再分发、稳定性、限频、数据权利和覆盖率尚未由本仓库建立。模板只说明字段形状；它们不证明相应数据可获得、完整或可合法分发。

## 维护范围

当前维护且可作为命令或输入引用的公开表面只有：

- `examples/run_demo.py`；
- `examples/strategy_specs/quality_value_momentum.json`；
- `a_share_quant_agent.reproducible_experiment` 的 `run` / `verify` 命令；
- `tests/fixtures/qdata_research_snapshot_v1/` 合成快照；
- `tests/` 离线 unittest。

其他仍保留的研究模块和配置是可审阅源码，不自动构成受支持命令或有效研究证据。旧脚本、生成报告和未随仓库提供的输入见[历史证据说明](docs/legacy-evidence.md)。

## 设计记录

- [信号与成交时序 ADR](docs/adr/0001-signal-and-fill-timing.md)
- [可复现研究链计划](docs/plans/2026-08-24-reproducible-research-chain.md)
- [历史证据说明](docs/legacy-evidence.md)

## 明确未覆盖

- 没有真实 A 股样本外结果或统计显著性结论；
- 没有经授权数据集的权利、全市场覆盖或再分发证明；
- 没有券商、订单路由、实盘交易或投资建议功能；
- 没有生产部署、服务等级、容量、性能、容灾或安全认证；
- 没有可从当前 checkout 精确复建的历史策略绩效，因此主叙事不发布历史指标。

本仓库未添加许可证；代码使用权仍需仓库所有者明确决定。
