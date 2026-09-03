# A-share Quant Research Agent

| 能力 | 证据级别 | 当前可复验证据与边界 |
|---|---|---|
| A 股研究/审计原型 | `implemented` | 规则化因子、组合约束、A 股交易摩擦与审计代码可导入；不是投顾、券商或实盘交易系统。 |
| `research_snapshot_v1` 严格输入 | `unit-tested` | QData 快照先由独立验证器校验 schema、文件集合、哈希、cutoff、PIT 可得性和覆盖，再规范化为 Agent 面板；异常输入 fail closed。 |
| 信号与成交时序 | `unit-tested` | 固定为“t 日收盘决策 → t+1 原始开盘参考 → 显式摩擦 → 成交”；不允许复权价充当成交价。 |
| 确定性跨仓实验与 receipt | `local-integration-tested` | 本地以同级 QData checkout 做过构建器字节比对；公开路径使用固定测试 SHA，产出可重复 receipt 并由独立命令复核。 |
| 锁定测试窗的真实市场因子统计 | `receipt-verified` | 公开 receipt 含 4735 个标的、3894242 行、18 个按月截面及全部 16 个登记结果，并绑定方案、输入哈希与 Agent commit；这是已观察的短样本 pilot，不是外部预注册或长期泛化证据，第三方也不能仅靠 checkout 重算。 |
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

## 锁定测试窗的真实市场 pilot

[分析方案](studies/pit_factor_replication_v1/plan.json)固定了 4 个因子和 4 级偏差控制，不按结果选择“最佳策略”。本地受限数据覆盖 2023-01-03 至 2026-07-24；仓库锁定测试窗为 2025-01-01 至 2026-06-30，共 18 个按月截面。公开的[完整 receipt](evidence/pit_factor_replication_v1/receipt.json)逐项报告 16 个登记单元，并绑定输入文件哈希、方案哈希和 Agent commit `cbf5414c2613032dfa29ef2c295c760a3f4769ef`。[唯一公开状态](evidence/PUBLIC_EVIDENCE_STATUS.json)仍使用历史 schema 标签 `REAL_MARKET_OOS_STATISTICS`；这里把它严格解释为“仓库内锁定测试窗统计”，不等同于第三方预注册、此前从未接触数据或长期真实样本外验证。该状态只能由通过验证的 receipt 派生，不读取旧 registry/readiness 报告。

这份 pilot receipt 是已经公开的历史证据，但其现有 `rights_review` 文本只声明本地研究用途和不公开原始行，不足以独立证明供应商明确允许公开文件哈希及全部聚合输出。该权限必须由数据许可方或获授权的机构管理员单独复核；pilot 不构成 Stage-2 数据权利的先例。当前提交不伪造或补签这一外部事实。

基于这条证据链撰写的 15 页英文 working paper 可直接查看 [PDF](docs/working-paper/A_Share_Factor_Replication_Working_Paper.pdf)，或下载[可编辑 DOCX](docs/working-paper/A_Share_Factor_Replication_Working_Paper.docx)。论文完整披露 16 个登记结果，并沿用 receipt 的三项主张边界；它不是额外的绩效证据源。

下表每格依次为“平均 rank IC / Newey-West t / top-quintile minus universe 20-session return”；没有挑选或高亮最佳单元。

| 变体 | ROE | Momentum 60d | Low volatility 20d | Composite |
|---|---:|---:|---:|---:|
| M0 naive | 0.0435 / 2.452 / 0.0056 | -0.0514 / -1.683 / 0.0076 | 0.0529 / 1.857 / -0.0104 | 0.0302 / 1.380 / 0.0050 |
| M1 PIT universe | 0.0461 / 2.629 / 0.0059 | -0.0495 / -1.622 / 0.0078 | 0.0550 / 1.936 / -0.0099 | 0.0332 / 1.532 / 0.0054 |
| M2 PIT publication | 0.0105 / 0.612 / -0.0011 | -0.0495 / -1.622 / 0.0078 | 0.0550 / 1.936 / -0.0099 | 0.0038 / 0.185 / -0.0001 |
| M3 bundled implementation | -0.0108 / -0.475 / -0.0039 | -0.0446 / -1.860 / 0.0086 | 0.0291 / 0.907 / -0.0142 | -0.0194 / -0.758 / -0.0034 |

最清楚的审计发现不是“哪个因子最好”，而是 ROE/composite 在按财报 `publishDate` 对齐后明显衰减，并在 M3 的捆绑实现约束下改变符号。当前证据不能把 M3 的变化归因于其中任何单一组件，尤其不能用缺少正例的停牌字段作独立解释。这支持“时间对齐会改变研究结论”的方法学判断，不构成显著性、可实施收益或泛化主张。方案的 `locked_at` 是仓库内声明，不是第三方时间戳预注册；因此它降低选择性披露风险，但不把本次结果包装成严格的事前发现。原始数据受许可限制，receipt 能验证内容身份和完整性，不能替代数据访问。

## Stage-2 期刊研究（尚未运行）

[Stage-2 研究包](studies/pit_factor_bias_decomposition_v2/)把论文问题收窄为“按记录的财报发布日期约束信息后，A 股 ROE—后续收益关系还剩多少”，并明确披露上面的短样本 pilot 已经被观察。拟定的 2010-2022 主历史再平衡区间与 2025-2026 pilot 评估期不重叠，但最后一个 20-session horizon 延伸到 2023 年 1 月，与 pilot 行情文件的原始日期边界重叠；这一点已单独披露，并在放数前要求 prior-exposure 声明。方案固定 final-survivor/report-end、PIT/report-end、PIT/publication 三段基线，再完整枚举 ST、停牌、20 日成交额门槛和一会话滞后的 `2^4` 组合，共 18 个变体、72 个 factor cells。ROE publication-timing mean contrast 是唯一 primary，固定 pilot-informed 的负向预测，同时采用双侧零均值检验；28 项 secondary IC family 使用 BH，其中新增三项 ROE 共同支持恒等分解，另有两项确定性的 timing-isolation checks。72 个 cell 的均值、t 统计量和 top-minus-universe spread 只作全量描述，不构成 72 次发现检验；精确 Shapley 只对四组件 implementation block 作条件归因和顺序无关主张，因此不存在“挑最好结果”的接口。当前 72-cell 方案保持不变；若供应商不能证明停牌估值是对应官方交易日由供应商记录或发布的值，Stage-2 继续阻塞，只有在外部注册和任何结果访问之前才能前瞻改成移除全部停牌组件变体的 10-variant/40-cell 新方案并重新冻结全部设计文件。

面向期刊 Stage-1 评审的[14 页匿名完整英文稿（DOCX）](docs/working-paper/A_Share_Factor_Specification_Effects_Stage1_Manuscript.docx)已经形成，并保留[可审阅 Markdown 源稿](studies/pit_factor_bias_decomposition_v2/stage1_manuscript.md)和[文档构建脚本](studies/pit_factor_bias_decomposition_v2/build_stage1_manuscript.py)。它完整呈现 observed pilot、研究问题、文献定位、数据门槛、唯一 primary、固定 secondary family、72-cell 报告合同、结果分支、局限和声明，但没有虚构任何尚未执行的 confirmatory result。当前详细执行协议以[统计分析计划](studies/pit_factor_bias_decomposition_v2/statistical_analysis_plan.md)和机器可读模板为准；较早的[13 页 Registered Report protocol（DOCX）](docs/working-paper/A_Share_Stage2_Registered_Report_Protocol.docx)仅作为已被取代的版式模板与设计历史归档，其科学内容不再具有权威性，也不得用于执行。

这不是已完成的国际期刊实证。本地数据审计尚未找到同时满足 2009 warm-up、2010—2022 主区间、独立官方交易日历、原始 `roeDiluted`、历史生命周期与交易状态以及论文披露/受控审稿权利的完整数据源，因此状态是 `BLOCKED_FOR_STAGE2`。当前还必须逐行提供 `close_observation_type`：非停牌只能是 `traded_close`，停牌只能是供应商在该官方交易日记录或发布的 `suspension_valuation`；研究代码禁止自行前向填充。每月 `active master ∩ signal-session quote` 的全部候选都必须同时具备 `t/t+1/t+20/t+21` 精确端点，端点数必须等于候选数，且仍需至少 1,000 个完整 quote-contract 标识符。由此计算的收益和 IC 是估值诊断，不是可执行成交收益。旧版 Stage-2 候选真实数据 coverage 报告已从当前公开树移除；在该候选交付获得书面权利确认前，其文件哈希、精确行数、逐月覆盖和其他供应商衍生统计只能留在私有保管区。[数据缺口说明](studies/pit_factor_bias_decomposition_v2/current_bundle_gap_assessment.md)只保留不识别数据源的阻塞结论。针对这一阻塞，仓库提供了[数据采购询权函](studies/pit_factor_bias_decomposition_v2/stage2_data_procurement_request.md)、[供应商权利确认表](studies/pit_factor_bias_decomposition_v2/provider_rights_confirmation_form.md)、[空白字段映射工作簿](studies/pit_factor_bias_decomposition_v2/provider_capability_and_field_mapping.template.xlsx)、[私有交付说明](studies/pit_factor_bias_decomposition_v2/private_data_handoff_instructions.md)、[结果盲验收检查表](studies/pit_factor_bias_decomposition_v2/provider_delivery_acceptance_protocol.md)和[可选私有交付回执模板](studies/pit_factor_bias_decomposition_v2/provider_delivery_acceptance_receipt.template.json)；私有交付清单先冻结且不得回写，可选回执只向后绑定清单及审计哈希，不是正式门禁。正式设计冻结只接受由设计清单实际绑定的可重算 coverage report 和人工 `reviewed_pass` 声明。工作簿的完成状态只代表材料齐备待人工复核，不是数据验收、注册或执行授权。Conditional 权利不能用一段自由文本概括：每条限制必须有唯一 ID、对应的权限字段，并且恰好映射到一个同 ID、同权限字段、带满足标记、时间和证据哈希的人工复核；缺失、重复、未知、权限错配或映射权限不为真都会 fail closed。由于供应商填写的字符串会进入固定的公开 Stage-2 数据声明投影，每个必需数据集的 `source_identity_publication_permitted` 和 `field_mapping_citation_permitted` 都必须为真；任一权限为假都会阻止当前设计下的 Stage-2。未复权 `open`、`volume`、价格限制和 nonfill 语义只属于 planned portfolio extension，不是当前 IC-core 的输入门槛。现有 runner 实现 complete IC matrix、配对 HAC、IC Shapley、ROE 共同支持恒等分解、无收益 publication-exposure diagnostics，以及覆盖全部 signal-eligible 记录并由哈希绑定的私有端点 reason ledger；任何缺失的精确收益端点都会使相应 cell 不可估计并触发全局 `INSUFFICIENT_EVIDENCE`。next-open portfolios、成本、nonfills、bootstrap、interactions、退市终值适配器和结构化 deviation reporting 都明确标为 planned/unimplemented。[统计分析计划](studies/pit_factor_bias_decomposition_v2/statistical_analysis_plan.md)、[prior-exposure log](studies/pit_factor_bias_decomposition_v2/prior_exposure_log.md)、机器可读 specification inventory 和 PBFJ EOI/pitch 草案已公开；只有在完整数据、审阅声明、prior-exposure 声明和外部时间戳全部到位后，才会按 plan core → design manifest → registration receipt → execution authorization → final envelope 的顺序授权规定范围内的 IC-core 执行。授权链通过后，runner 必须显式接收两个位于任何 Git worktree（包括无关仓库、linked checkout 和 QData checkout）之外的私有路径：全新的 `output_dir`（保存结果和私有端点 ledger）以及受保护的 `authorization_consumption_dir`。它会在解析任何行情或财务结果值前，以 execution-authorization 文件哈希为键独占创建一次性 consumption sidecar；把目录加入 `.gitignore` 不构成合格的私有路径，同一授权在该受保护目录中的第二次 claim 会 fail closed，失败或中断也需重新授权。创建 sidecar 后四个原始输入各读取一次，coverage 重算、panel loader 和 receipt 输入证据复用同一组捕获字节，路径替换不能换入另一份分析样本。有限期限合同还会在 consumption、结果准备、每个月度执行边界及 receipt 发布前复查，过期即停止且不生成结果 receipt。这个本地机制不替代外部注册、人工签署或供应商数据权利，也不能防止有特权的保管人删除目录。

Stage-2 公开 receipt 的 `data.files` 对原始数据、私有声明/报告/证明和公开控制工件统一只发布注册 SHA-256；验证器拒绝额外的字节数、文件名或路径，即使 receipt integrity 被重新计算。权威 coverage report 和 data-access metadata audit 都包含精确输入哈希、字节数及详细统计，属于受权利控制的私有证据。它们的 `--output` 必须是任何 Git worktree 之外的新文件；CLI 以 `0600` 原子创建、绝不覆盖，也不会把 payload 打到 stdout。单独的、经权利复核的公开导出功能尚未实现，不能因为报告不含原始数据行就把它复制进仓库。bounded probe 的私有输出目录也必须在第一次供应商请求前满足同一 any-Git 规则。

当前 prior-specification inventory 仍是带空值的 `draft_incomplete_not_manifest_eligible`，所以 bounded probe preflight 也会 fail closed。正式操作先以已存在的被审计 base commit 编制完整 inventory，再把完整 inventory 与 probe spec 提交到其后代 commit；外部时间戳绑定后代 commit 和精确文件哈希，避免把未来 commit id 写入其自身所包含文件的自引用。probe 的 v3 权利复核还必须绑定该时间戳证明文件的原始 SHA-256，并给出带时区的合同生效/到期证据；合同需在复核、preflight、首次供应商请求和 receipt 发布时都有效。有限期限合同还必须用单独证据哈希证明到期后可持续私有留存 probe 工件，并可持续公开已经发布的 aggregate receipt/metadata。空到期日只在明确确认无到期、两个 post-expiry 布尔值为 false 且 survival evidence hash 为空时接受；任何过期、矛盾字段或证明替换都会在请求前或发布前 fail closed。公开 receipt 与私有 manifest 同时绑定完全相同的权利复核哈希。probe 结果目录以系统级 exclusive atomic rename 发布；竞态出现的文件、软链或空目录均不会被覆盖。

## 证据等级

- `implemented`：代码存在且当前可导入，不等于行为已充分验证。
- `unit-tested`：离线确定性单元或合同测试覆盖所述行为。
- `local-integration-tested`：维护者在本地跨模块或跨 checkout 跑通过有界测试；不代表托管服务或生产运行。
- `receipt-verified`：公开验证器接受规范化 receipt；证明 receipt schema 内的哈希、登记 lattice/cell/estimand 身份与数量及 claim gates 自洽。只有受控审阅模式取得私有 Stage-2 端点账本后，才能核验账本哈希、唯一性、逐 cell 基数及 signal eligibility 确定后在收益查询阶段发生的逐证券静默丢弃；公开 receipt 本身不能证明未公开原始数据正确，也不能检测进入 signal-eligible denominator 之前的任意上游遗漏。
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
- `a_share_quant_agent.confirmatory_study` 的 `run` / `verify` / `run-stage2` / `verify-stage2` / `status` 命令；legacy `run` 现在只接受 `synthetic_fixture`，不能再生成新的真实市场 receipt，仓库内既有 v1 pilot receipt 仅在完整文件 SHA-256 命中固定历史 allowlist 时保留其静态状态；任何其他自洽并重算 integrity 的 v1 receipt 都只能为公共汇总贡献 `INSUFFICIENT_EVIDENCE`。任何新的真实市场执行只能由 `run-stage2` 在完整外部注册链和一次性授权通过后启动；其底层 cell executor 是私有测试接口，不是可绕过门禁的公开命令。Stage-2 命令只覆盖已实现的 IC core，并在缺少完整注册链或授权输入时 fail closed。`verify-stage2 --receipt ...` 可独立验证公开 receipt；显式传入 `--authorization-consumption ...` 可核对私有授权消费记录，显式传入 `--endpoint-ledger ...` 才审计不公开的逐证券 endpoint ledger；
- `studies/pit_factor_replication_v1/` 的锁定方案与数据声明模板；
- `evidence/pit_factor_replication_v1/receipt.json` 与由其派生的 `evidence/PUBLIC_EVIDENCE_STATUS.json`；
- `tests/fixtures/qdata_research_snapshot_v1/` 合成快照；
- `tests/` 离线 unittest。

真实 Stage-2 的受支持启动前缀是 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m a_share_quant_agent.confirmatory_study run-stage2`。`-B`/环境变量必须从解释器启动时生效，避免模块导入先生成被忽略的 `__pycache__`、随后触发整仓 clean-check；CLI 对未禁用 bytecode 的 Stage-2 调用 fail closed。结果目录先在同一父目录完整暂存，再用系统的 exclusive atomic rename 发布；并发出现的文件、软链或空目录都不会被覆盖。

包级 `__all__` 只列出支撑上述证据链的可导入模块。`ops` 与 `completion_readiness` 等旧模块仍可供源码审计，但不在维护 API 中；缺少显式 legacy 命令时会 fail closed，不会指向已删除的 runner。其他仍保留的研究模块和配置也不自动构成受支持命令或有效研究证据。旧脚本、生成报告和未随仓库提供的输入见[历史证据说明](docs/legacy-evidence.md)。

## 设计记录

- [信号与成交时序 ADR](docs/adr/0001-signal-and-fill-timing.md)
- [可复现研究链计划](docs/plans/2026-08-24-reproducible-research-chain.md)
- [历史证据说明](docs/legacy-evidence.md)

## 明确未覆盖

- 没有把真实 A 股锁定测试窗统计提升为可实施 alpha、统计显著性或跨时期泛化结论；
- 没有公开原始授权数据、完整 revision/vintage 历史或再分发权；
- 没有券商、订单路由、实盘交易或投资建议功能；
- 没有生产部署、服务等级、容量、性能、容灾或安全认证；
- 没有可从当前 checkout 精确复建的历史策略绩效，因此主叙事不发布历史指标。

本仓库原创源代码和原创文档按根目录 [MIT License](LICENSE) 授权，文件另有说明的除外。该许可不授予任何供应商数据、第三方材料、商标或未公开授权数据的权利。
