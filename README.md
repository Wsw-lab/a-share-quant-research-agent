# A Share Quant Agent MVP

> Portfolio note: this project is currently positioned as a GitHub / graduate-application showcase for quantitative finance and financial engineering. See `PROJECT_PORTFOLIO.md` and `reports/portfolio_readiness/latest_portfolio_readiness.md` for the concise research-readiness summary. It is not a live-trading system.

这是“全自动 A 股量化研究与交易 Agent”的第一版研究内核骨架。

当前 MVP 只做：

- 自然语言策略未来要落到的 `StrategySpec` 结构。
- 日频 A 股回测 v0。
- 手续费、印花税、滑点、T+1、100 股整数、涨跌停/停牌约束。
- 基础审计报告。
- 模拟调仓，不接实盘。
- 今日投资实时扩展行情自动股票池。
- 今日投资股票主数据上市/退市点时过滤。
- 今日投资历史点时流动性 membership。
- 参数敏感性分析。
- 沪深300等指数基准比较。
- Walk-forward 样本外验证。
- 行业暴露诊断。
- 因子 IC/收益衰减诊断。
- 空仓现金替代收益建模和贡献审计。
- 研究运行注册表、历史归档和 Web 对比看板。
- 后台研究任务队列和批量参数实验。
- 保守 Research Score、数据质量/新鲜度监控和健康页。
- 今日投资缓存预热、健康门控 JSON 和轻量冒烟测试。
- 数据源/网络类失败的后台任务重试记录。
- 本地 Web 工作台。
- 今日投资实时扩展行情自动股票池。
- 参数敏感性分析。
- 本地 Web 工作台。

当前 MVP 不做：

- 实盘自动下单。
- 高频、打板、抢涨停、T0。
- 收益承诺或荐股。
- 券商账户接入。

## Run Demo

```bash
cd a_share_quant_agent_mvp
PYTHONPATH=src python3 examples/run_demo.py
```

输出报告：

```text
a_share_quant_agent_mvp/reports/demo_report.md
```

## Run Natural Language Demo

```bash
cd a_share_quant_agent_mvp
PYTHONPATH=src python3 examples/run_from_idea.py
```

也可以传入自己的策略想法：

```bash
PYTHONPATH=src python3 examples/run_from_idea.py "每月买入 ROE 高、PE 低、近60日涨幅强、成交额大于1亿的非ST股票，等权持有20只"
```

输出：

```text
a_share_quant_agent_mvp/reports/generated_strategy_spec.json
a_share_quant_agent_mvp/reports/idea_report.md
```

当前解析器是确定性规则版本，支持识别：

- 调仓：`每月`、`月度`、`每周`、`周度`
- 持仓：`持有20只`、`买入10只`、`选择15只`
- 流动性：`成交额大于1亿`、`成交额大于5000万`
- 因子：`ROE`、`PE`、`PB`、`近60日涨幅`、`近20日涨幅`、`低波动`、`股息率`
- 过滤：默认排除 ST 和停牌股票

没有明确说明时，默认 `100万` 初始资金、`按月调仓`、`等权持有20只`、使用保守交易成本。

## Run Data Source Demo

默认仍使用可复现的 sample 数据：

```bash
cd a_share_quant_agent_mvp
PYTHONPATH=src python3 examples/run_real_data.py
```

一键端到端真实数据演示：

```bash
cd a_share_quant_agent_mvp
PYTHONPATH=src python3 examples/run_end_to_end_demo.py
```

这会完成：

- 自然语言策略解析
- 今日投资真实行情、涨跌停、ROE 财务因子加载
- 今日投资 `stock/basic-info` 股票主数据加载与上市/退市点时过滤
- 本地缓存和数据快照哈希
- 日频回测
- 审计报告
- 参数敏感性分析
- Walk-forward 样本外验证
- 行业暴露诊断
- 因子 IC/收益衰减诊断
- Run Registry 归档和 decision gate 判定
- 后台 job queue 和批量参数实验
- Research Score、data quality 和 `/health` 健康检查
- `/warmup` 今日投资缓存预热和 `health_status.json` 健康门控
- 基准相对收益分析
- 最新模拟调仓订单
- Paper Control 风控门控、模拟账户、持仓/成交/流水账本
- Production Ops 调度、通知、ack 和 `/ops` 运维总览
- CSV/JSON artifacts 导出

接 AKShare 历史行情：

```bash
python3 -m pip install -r requirements-data.txt
PYTHONPATH=src python3 examples/run_real_data.py \
  --source akshare \
  --symbols 600000.SH,000001.SZ,600519.SH,000858.SZ,600036.SH \
  --start 20210101 \
  --end 20251231 \
  --idea "每月买入近60日涨幅强、低波动、成交额大于5000万的非ST股票，等权持有5只"
```

接今日投资真实行情：

```bash
PYTHONPATH=src python3 examples/run_real_data.py \
  --source investoday \
  --symbols 600000.SH,000001.SZ,600519.SH,000858.SZ,600036.SH \
  --start 20240101 \
  --end 20241231 \
  --idea "每月买入ROE高、PE低、近60日涨幅强、成交额大于5000万的非ST股票，等权持有3只"
```

使用今日投资自动股票池，按今天全市场成交额取前 100 只：

```bash
PYTHONPATH=src python3 examples/run_real_data.py \
  --source investoday \
  --universe investoday_top_amount \
  --universe-size 100 \
  --start 20240101 \
  --end 20241231 \
  --idea "本金1000万，每月买入ROE高、PE低、近60日涨幅强、成交额大于5000万的非ST股票，等权持有20只"
```

使用历史点时流动性股票池：先取较宽候选池，再按每个历史日之前的 20 日平均成交额生成每日 Top N membership。

```bash
PYTHONPATH=src python3 examples/run_real_data.py \
  --source investoday \
  --universe investoday_pit_top_amount \
  --universe-size 100 \
  --candidate-size 150 \
  --benchmark-code 000300 \
  --start 20240101 \
  --end 20241231 \
  --idea "本金1000万，每月买入ROE高、PE低、近60日涨幅强、成交额大于5000万的非ST股票，等权持有20只"
```

也可以直接运行百股脚本：

```bash
PYTHONPATH=src python3 examples/run_100_stock_real_backtest.py
```

生产资产导入前的百股真实候选池验收留档：

```text
Source: investoday:stock/adjusted-quotes+investoday:stock-quote/realtime-ext+pit_liquidity_universe
Symbols: 150
Rows: 36002
Data snapshot sha256: ab737333ba877c00475d1ead70bd1581f50a17ea4c60b05d9687693480ca874a
Verdict: refine
Annualized return: 33.30%
Max drawdown: -17.99%
Trades: 250
Sensitivity scenarios: 8
Walk-forward windows: 2
Latest top industry: 电子 (15.78%)
Best factor IC: roe 5d (0.058)
Benchmark: 沪深300 (000300)
Excess annualized return: 17.04%
Information ratio: 1.21
```

今日投资接口响应默认缓存到：

```text
a_share_quant_agent_mvp/cache/investoday_api/
```

缓存用于加速重复回测，并让同一批数据更容易复现。需要强制重新拉取时使用：

```bash
PYTHONPATH=src python3 examples/run_real_data.py --source investoday --refresh-cache
```

需要临时禁用缓存时使用：

```bash
PYTHONPATH=src python3 examples/run_real_data.py --source investoday --no-cache
```

生产面板持久化 cache 位于 `data_assets/cache/production_panels/`。治理工具默认只生成 dry-run manifest，不会删除文件：

```bash
PYTHONPATH=src python3 examples/manage_production_panel_cache.py \
  --asset-root data_assets \
  --max-total-gb 16 \
  --keep-latest 2
```

确认报告后才使用 `--execute` 执行清理：

```bash
PYTHONPATH=src python3 examples/manage_production_panel_cache.py \
  --asset-root data_assets \
  --max-total-gb 16 \
  --keep-latest 2 \
  --execute
```

报告输出到 `reports/cache_governance/latest_cache_governance.md/json`。新写入的 production panel cache 会自动生成同名 JSON sidecar，用于免加载多 GB pickle 的审计、容量规划和清理。

报告会输出 `Data snapshot sha256`，用于标记本次回测使用的数据快照。

启动本地 Web 工作台：

```bash
PYTHONPATH=src python3 examples/web_app.py --host 127.0.0.1 --port 8765
```

常用页面：

- `http://127.0.0.1:8765/`: 单次研究运行。
- `http://127.0.0.1:8765/warmup`: 今日投资真实数据缓存预热。
- `http://127.0.0.1:8765/jobs`: 后台任务队列。
- `http://127.0.0.1:8765/compare`: score-sorted 研究对比。
- `http://127.0.0.1:8765/health`: 数据新鲜度和队列健康门控。
- `http://127.0.0.1:8765/paper`: 模拟账户、paper 风控、最新订单、持仓、成交和账本。
- `http://127.0.0.1:8765/ops`: 调度、通知、ack、health 和 paper 状态总览。

Web 服务启动后可跑健康冒烟测试：

```bash
PYTHONPATH=src python3 examples/health_smoke_test.py --base-url http://127.0.0.1:8765
```

## Paper Control

当前 MVP 使用今日投资真实 A 股行情、财务、涨跌停、股票主数据和基准数据做研究与候选筛选；交易端仍是本地模拟账户，不连接券商，不提交真实订单。

单独从某次 daily pipeline 的候选运行生成待审批模拟调仓：

```bash
PYTHONPATH=src python3 examples/run_paper_control.py \
  --pipeline-summary reports/daily_pipeline/<pipeline_id>/summary.json
```

审批并模拟执行待审批订单：

```bash
PYTHONPATH=src python3 examples/review_paper_orders.py approve \
  --actor operator \
  --reason manual_review \
  --execute-simulated
```

`configs/daily_pipeline.yaml` 默认开启 `paper_control: true`，但 `paper_auto_approve: false`、`paper_execute_simulated: false`。日跑成功后会自动读取 `selected_candidate_run_id`，按模拟账户当前 NAV 重新缩放目标持仓，经过风控门控后生成待审批订单；只有人工 approve/execute 后才写入模拟成交。

主要输出：

- `reports/paper/latest_control.json`: 最新控制面摘要、候选 run、风控结果、订单/成交统计和账户前后状态。
- `reports/paper/risk_gate.json`: pipeline、health、数据新鲜度、decision gate、production data ready、个股权重、行业集中、换手、回撤和现金缓冲检查。
- `reports/paper/latest_orders.csv`: 最新一轮拟执行/已模拟执行订单。
- `reports/paper/positions.csv`: 当前模拟持仓。
- `reports/paper/trades.csv`: 累计模拟成交。
- `reports/paper/account_ledger.csv`: 模拟账户账本。
- `reports/paper/equity_curve.csv`: 模拟账户权益曲线。
- `reports/paper/alerts.csv`: paper 风控、审批、模拟成交告警。
- `reports/paper/audit_log.csv`: 候选生成、风控、审批、拒绝、模拟成交的中文业务审计日志。

生产资产导入前的日跑/paper 端到端验证留档：

```text
Pipeline: daily_20260724_132221_761
Selected candidate: none, historical run failed the production_data gate before canonical import
Bias diagnostics: warn, score 92.0, 0 hard failures
Attribution: latest batch dominant style quality
Universe source: realtime_candidate_pit_liquidity
Data trust: real_data_candidate_pool, not canonical production asset
Paper control: paper_20260724_132233_890
Risk gate: fail, no_selected_candidate
Orders/trades: 0 order, 0 simulated trade
Allowed to trade: False
Ready for review: False
Approval smoke: examples/paper_control_smoke_test.py passed
Attribution smoke: examples/attribution_smoke_test.py passed
Historical universe smoke: examples/historical_universe_smoke_test.py passed
Data trust smoke: examples/data_trust_smoke_test.py passed
Stock master validator CLI smoke: passed
Data asset inventory smoke: examples/data_asset_inventory_smoke_test.py passed
Investoday candidate asset materialization: 20 symbols, 7520 rows, historical_candidate, not canonical production asset
Vendor production asset import smoke: examples/vendor_asset_import_smoke_test.py passed
Vendor onboarding smoke: examples/vendor_data_onboarding_smoke_test.py passed
Vendor onboarding latest: data_assets/investoday_candidate scanned, mapping_ready=True; dry-run intentionally fails production gates because this candidate-pool fixture has limited coverage and is missing dividend_yield
Production import executor smoke: examples/production_import_executor_smoke_test.py passed
Production import executor latest: imported_factory_completed; dry-run and formal import are production_ready; canonical assets were backed up before write
Full universe readiness smoke: examples/full_universe_readiness_smoke_test.py passed
Full universe readiness latest: production_ready, contract_ready=True, runtime_ready=True; stock/all GET, chain/sec-basic-info and stock/adjusted-quotes probes ok
Investoday full universe extract smoke: examples/investoday_full_universe_extract_smoke_test.py passed
Investoday full universe extract latest: extracted_ready; stock master 5509 SH/SZ A-share symbols, 323 rows with delistDate/listStatus=DL, B-share hard filter passed; daily quotes 6593923 rows, 5380 eligible quote symbols, 111/111 batches completed, 0 failed
Production data readiness smoke: examples/production_data_readiness_smoke_test.py passed
Production data readiness: production_ready=True; canonical stock_master, daily_quotes, Investoday financial-alpha fundamental_factors, dividend_events-derived daily dividend_yield, latest-only industry_classification, production daily_fund_flows, production margin_trades, production dragon_tiger_details and production announcements are present and validated; optional index_constituents PIT contract/loader is complete but its canonical full-production file is still waiting on a confirmed constituent source; effective coverage ROE=99.94%, dividend_yield/PE/PB=100.00%, capital_flow_quality_score=97.87%, margin balance coverage=69.11%
Strategy factory smoke: examples/strategy_factory_smoke_test.py passed
Alpha selection smoke: examples/alpha_selection_smoke_test.py passed, including amount bucket cap and new alpha stability factors
Risk overlay smoke: examples/risk_overlay_smoke_test.py passed, including staged recovery and window fuse/re-entry paths
Fundamental factor asset smoke: examples/fundamental_factor_asset_smoke_test.py passed; separate fundamentals/fundamental_factors.csv unlocks roe/dividend_yield templates in production fixtures
Dividend event alpha smoke: examples/dividend_event_alpha_smoke_test.py passed; PIT dividend event features stay inactive before exDate and feed dividend_event_* alpha fields after exDate
Industry classification smoke: examples/industry_classification_smoke_test.py passed; PIT industry labels stay inactive before effective date and `selection_group_field=industryLV1Name` caps single-industry selected names
Index constituent PIT smoke: examples/index_constituent_pit_smoke_test.py passed; index snapshots apply point-in-time until the next snapshot, deletions do not leak forward, and strategies can require `use_index_membership/index_code`
Capital flow alpha smoke: examples/capital_flow_alpha_smoke_test.py passed; daily fund-flow rows are strictly lagged before quote date, dragon-tiger events exclude same-day leakage, and a tiny production asset bundle verifies loader source-chain integration
Announcement event alpha smoke: examples/announcement_event_alpha_smoke_test.py passed; canonical announcements use strictly prior disclosure dates, same-day announcements do not leak into quote-date features, and tiny production bundle integration is covered
Margin trade alpha smoke: examples/margin_trade_alpha_smoke_test.py passed; financing/securities-lending rows are strictly lagged before quote date, same-day margin rows do not leak, and tiny production bundle integration is covered
Production panel cache governance smoke: examples/production_panel_cache_governance_smoke_test.py passed; cache sidecars, dry-run cleanup plans, stale temp pruning, size-cap pruning and execute-only deletion are covered on temporary fixtures
PIT structure source audit smoke: examples/pit_structure_sources_smoke_test.py passed; current-only index/industry sources stay blocked for historical PIT import, while licensed effective-date fixtures unlock the install path
Alpha line retirement smoke: examples/alpha_line_retirement_smoke_test.py passed; capital-flow/dragon-tiger, announcement and margin-trades weak alpha lines can be retired from future factory runs unless templates carry explicit rewrite metadata
Completion readiness smoke: examples/completion_readiness_smoke_test.py passed, including alpha-line retirement-screen fallback to the latest production registry evidence
Investoday financial-alpha factors extract: investoday_fundamentals_20260728_134942_285 used stock/fin-der-inds and wrote 110764 PIT rows for 5377/5380 eligible symbols into data_assets/fundamentals/fundamental_factors.csv; ROE/gross margin/net margin/ROIC/revenue growth/net profit growth/CFO growth/cash conversion/debt/F-score fields are production validated, while dividend_yield remains supplied by canonical dividend-event/quote enrichment
Investoday industry classification extract: industry_classification_20260728_105325_689 wrote 5177 latest-only industry rows for 99.83% active symbol coverage into data_assets/industry/industry_classification.csv; this is a current as-of proxy, not a true historical industry-change table
Investoday capital-flow production extract: investoday_capital_flow_production_20260729 used stock/daily-fund-flows over 20210101-20260724 and wrote 6567105 strict PIT rows for 5378 symbols to data_assets/market/daily_fund_flows.csv; duplicate date/symbol keys=0, mainNetInflow coverage=100.00%, production asset validation is production_ready
Investoday dragon-tiger production extract: investoday_dragon_tiger_production_20260729 used stock/dt-details over 20210101-20260724 and wrote 181544 strict PIT event rows for 5176 symbols to data_assets/events/dragon_tiger_details.csv; duplicate date/symbol/abnormalType/amount keys=0, amount coverage=96.21%, production asset validation is production_ready
Investoday announcement production extract: investoday_announcements_production_20260730 used announcements GET over 20210101-20260730 and wrote 1365134 canonical rows for 5274 symbols to data_assets/events/announcements.csv; duplicate date/symbol/title/type keys=0, title/type coverage=98.03%, production asset validation is production_ready
Investoday margin-trades production extract: investoday_margin_trades_production_20260730 used stock/margin-trades POST over 20210101-20260724 and wrote 3973643 strict PIT rows for 3718 symbols to data_assets/market/margin_trades.csv; duplicate date/symbol keys=0, marginBalance/marginBuyAmount/marginRepayAmount coverage=69.11%, production asset validation is production_ready
Capital-flow / dragon-tiger factory: factory_batch_20260729_171552_613 ran configs/strategy_factory_capital_flow_candidate_variants.json on production data with benchmark 000300 and --skip-sensitivity; both templates executed, 0 errors, 0 skipped, both rejected. Dragon-tiger source chain is now active through dragon_tiger_asset+pit_dragon_tiger_events. Scores stayed 43.69; capital_flow_dragon_tiger_event_guard annualized=-3.02%, max drawdown=-33.55%, WF positive rate=35%, IC supportive/adverse=12/7. Diagnostics showed 26 failed WF windows across the two ideas and 6 underexposed recovery windows; comparison vs capital-flow-only was no_clear_improvement. The follow-up staged recovery factory below reran this line with full sensitivity after the wide-panel copy path was optimized.
Staged recovery / full sensitivity factory: factory_batch_20260730_101723_741 ran configs/strategy_factory_capital_flow_staged_recovery_variants.json on production data with benchmark 000300, full sensitivity enabled, production panel cache hit, and optimized attribution; 3 templates executed, 0 errors, 0 skipped, all rejected. Best record is extreme_outflow_avoidance_staged_recovery with score=45.00, annualized=-3.30%, max drawdown=-21.78%, WF positive rate=30%, IC supportive/adverse=18/2; it passed drawdown but failed walk-forward, factor IC and audit. Latest diagnostics show 41 failed WF windows out of 60, 12 underexposed recovery windows, comparison vs pre-cache staged run is no_clear_improvement, and completion readiness remains production_research_ready_no_stable_candidate at 4/7. Performance stage result: full production panel cold build wrote a 7.0G cache in about 965s; cache-hit panel load took about 23s; the same 3-idea full factory fell from about 1351s to about 337s, with per-idea attribution reduced from about 235-272s to 11-14s.
Stable candidate stage-4 factories: factory_batch_20260731_083131_619 ran configs/strategy_factory_stable_candidate_recovery_repair_variants.json on target production window 20220701-20260724 with benchmark 000300, retired alpha-line screening, and cached production fields; 3 templates executed, 0 errors, 0 skipped, all rejected. Best score was quality_low_vol_recovery_candidate at 41.60, WF positive rate=42.86%, max drawdown=-23.26%, annualized=-2.58%, IC supportive/adverse=20/0. A second simple-overlay probe factory_batch_20260731_084206_074 tested simpler recovery/no-overlay variants; 3 templates executed, 0 errors, 0 skipped, all rejected, best WF positive rate=50.00% but max drawdown worsened to -40.80%. Conclusion: stage 4 attempt completed but no stable paper candidate; failure is alpha/window stability, not just fuse stickiness.
Window-level alpha discovery stage: examples/summarize_strategy_factory_alpha_discovery.py now reads failed walk-forward windows and factor_ic artifacts, writes reports/strategy_factory_alpha_discovery/latest_alpha_discovery.* and generates configs/strategy_factory_alpha_discovery_candidate_variants.json from factors that retain positive IC inside failed windows. Smoke coverage examples/alpha_discovery_smoke_test.py passed. Production validation factory_batch_20260731_085702_363 ran the generated candidates with benchmark 000300, attribution/bias diagnostics enabled, retired alpha-line screening, and 0 errors/0 skipped; both ideas were rejected. Best alpha_discovery_core_factor_emphasis_candidate reached score=45.00, WF positive rate=50.00%, max drawdown=-24.81%, IC supportive/adverse=15/0 and gate blockers only walk_forward/audit. Failed windows improved to 17 from the prior simple-overlay 26, but no paper candidate was produced.
Alpha-health avoidance filter stage: RiskOverlaySpec now supports lagged alpha-health and market-breadth filters; add_robust_factor_features derives market_alpha_health_score_lag1, market_breadth_20d/60d/120d_lag1 and related market median health fields from PIT-safe shifted cross-sectional technical/quality data. examples/risk_overlay_smoke_test.py covers 0/weak/full target weights. Full target window 20220701-20260724 cold build for configs/strategy_factory_alpha_health_filter_variants.json exited 137 under memory pressure before a factory board was written; shorter production validation 20230101-20260724 completed as factory_batch_20260731_093208_410 with 3 ideas, 0 errors, 0 skipped. Best alpha_health_soft_gate_candidate moved from rejected to testing/refine with score=49.33, annualized=+3.26%, max drawdown=-23.11%, IC supportive/adverse=20/0 and only walk_forward as gate blocker, but WF positive rate was still 41.67% with 7 failed_oos windows. Stricter filters reduced exposure too much and created zero/negative OOS windows; a follow-up soft-refinement cold build also exited 137. No paper candidate was produced.
Cash-substitute yield stage: PortfolioSpec now supports cash_yield_annualized, run_backtest accrues the configured daily yield only on uninvested cash after the first trading day, equity_curve records cash_yield_accrued/cumulative_cash_yield, metrics/report expose total_cash_yield and cash_yield_return_contribution, and examples/cash_yield_smoke_test.py passed. A production factory rerun that dynamically added conservative 1.8% annualized idle-cash yield to the three alpha-health candidates again exited 137 before writing a board, so no promotion claim was made. Diagnostic-only overlay examples/estimate_cash_yield_overlay.py on the prior best alpha_health_soft_gate_candidate estimated +3.07% cash-yield contribution and annualized return 3.26% -> 4.05%. The follow-up single-candidate production validation completed as factory_batch_20260731_095511_157 with 0 errors/0 skipped after avoiding the multi-candidate memory peak; alpha_health_soft_gate_cash_yield_single was still rejected with score=44.54, annualized=+5.46%, max drawdown=-22.48%, cash-yield contribution=+2.97%, IC supportive/adverse=18/0, WF positive rate=41.67%, and blockers walk_forward/bias_diagnostics. Conclusion: idle-cash modeling is now correct and auditable, but this alpha line is regime-unstable and should be rewritten rather than promoted.
Fast rerun acceleration / failure-window rewrite prep: Strategy Factory now accepts `--frozen-panel-cache-path` and `run_strategy_factory(..., frozen_panel_cache_path=...)` for explicit frozen production-panel reruns. This path is opt-in only, appends `frozen_production_panel_cache` to the data source notes, and is intended for accelerated research when canonical source files are temporarily unavailable; final promotion still requires refreshed canonical production assets. examples/production_panel_cache_smoke_test.py now covers frozen cache loading after the source daily_quotes file is removed. The leftover 2.6G tmp panel from factory_batch_20260731_095511_157 was tested and is truncated, so it cannot be reused. Current canonical `data_assets/market/daily_quotes.csv` and production panel `.pkl` bodies are missing, so new production reruns require asset restoration/reimport first. To avoid losing time after restoration, configs/strategy_factory_failure_window_cash_yield_rewrite_variants.json adds 3 fast small-batch candidates focused on the failed OOS windows, using explicit cash yield, stronger defensive/liquidity/single-name IC factors, and tighter weak-regime exposure controls.
Factor quality audit: factor_quality_20260728_130750_269 completed on canonical assets, hard_failed=0, warnings=2; high dividend_yield rows and non-positive PB rows remain QA watch items
Strategy factory full diagnostics baseline: factory_batch_20260727_084756_343, --source production with benchmark 000300 and full WF/IC/attribution/industry/sensitivity diagnostics passed execution, 7 ideas, 0 errors, 0 skipped; all 7 rejected by real research gates
Defensive rewrite factory: factory_batch_20260727_093950_013, configs/strategy_factory_defensive_variants.json passed production execution with 6 ideas, 0 errors, 0 skipped; all 6 rejected. Latest comparison comparison_factory_batch_20260727_084756_343_vs_factory_batch_20260727_093950_013 is no_clear_improvement, so no variant is promoted.
Regime overlay factory: factory_batch_20260727_104036_813, configs/strategy_factory_regime_overlay_variants.json passed production execution with 6 ideas, 0 errors, 0 skipped; all 6 rejected but comparison vs defensive rewrite is risk_improved. Drawdowns improved to -18.62% to -21.55%, but walk-forward remains weak, so no variant is promoted.
Regime recovery factory: factory_batch_20260727_112448_344, configs/strategy_factory_regime_recovery_variants.json passed production execution with 6 ideas, 0 errors, 0 skipped; all 6 rejected. Regime diagnostics show 120 WF windows, 68 failed, 12 underexposed recovery windows. Comparison vs first overlay is no_clear_improvement: best WF delta +10%, but best drawdown delta -1.88%, so no variant is promoted.
Window fuse factory: factory_batch_20260727_135316_022, configs/strategy_factory_regime_fuse_variants.json passed production execution with 6 ideas, 0 errors, 0 skipped; all 6 rejected. Window failure replay shows 85 failed WF windows and 5158 replay days; comparison vs recovery is risk_improved with best drawdown delta +11.27% but best WF delta -15%, so no variant is promoted.
Re-entry repair factory: factory_batch_20260727_152127_098, configs/strategy_factory_regime_reentry_balanced_variants.json passed production execution with 6 ideas, 0 errors, 0 skipped; all 6 rejected. Re-entry is now observable in failed windows: fuse-active day share 41.23%, re-entry day share 28.00%, failed WF windows down to 79, max drawdown -17.66% to -24.23%, WF positive rate 30%-40%. Comparison vs recovery is risk_improved, comparison vs first re-entry repair is improved, but comparison vs sticky window fuse is no_clear_improvement, so no variant is promoted.
Alpha/WF repair factory: factory_batch_20260728_091319_860, configs/strategy_factory_alpha_ic_supported_variants.json passed production execution with 6 ideas, 0 errors, 0 skipped; all 6 rejected. IC adverse count improved to 0 on all 6 ideas and failed windows stayed at 79, but WF positive rate remained 30%-40%; comparison vs re-entry balanced is no_clear_improvement, so no variant is promoted.
Dividend event alpha factory: factory_batch_20260728_095842_074, configs/strategy_factory_dividend_event_alpha_variants.json passed production execution with 6 ideas, 0 errors, 0 skipped; all 6 rejected. dividend_event_asset+pit_dividend_events is now in the production source chain, IC adverse count stayed at 0 and best drawdown improved by 2.49pp versus alpha IC-supported, but WF positive rate stayed at 30%-35%; latest comparison vs alpha IC-supported is no_clear_improvement, so no variant is promoted.
Industry-neutral factory: factory_batch_20260728_111933_162, configs/strategy_factory_industry_neutral_variants.json passed production execution with 6 ideas, 0 errors, 0 skipped; all 6 rejected. industry_classification_asset+pit_industry_classification is now in the production source chain and configs include industryLV1Name group cap, but metrics are unchanged versus dividend event alpha because selected portfolios were already below the 20% per-industry cap; latest comparison is no_clear_improvement, so no variant is promoted.
Index constituent PIT stage: generic `index/index_constituents.csv` loader, production validation summary, PIT snapshot merge, `UniverseSpec.use_index_membership/index_code` filtering and smoke coverage are complete. Stage-1 source audit added `examples/audit_pit_structure_sources.py` and `src/a_share_quant_agent/pit_structure_sources.py`: Investoday search still finds no index constituent/weight or historical industry endpoint, `stock/industries` is current-only, CSIndex public endpoints/files expose current samples/top-10 weights/current industry data but not full historical effective-date history, and local Wind/Tushare SDK runtime is not installed. The loader now refuses `isLatestOnly=True` single-snapshot index files by default, so no canonical production constituent file is fabricated; use vendor import or a confirmed licensed historical source before running index-member strategy variants.
Financial-alpha failure-window factory: factory_batch_20260728_163744_760, configs/strategy_factory_financial_alpha_failure_window_variants.json passed full production diagnostics on 20210101-20260724 with 6 ideas, 0 errors, 0 skipped; all 6 rejected by research gates. Best score is 45.00, WF positive rate tops out at 45%, max drawdown ranges from -25.06% to -31.28%, failed WF windows fell to 73, and comparison vs industry-neutral is no_clear_improvement: best WF delta +10pp but best drawdown delta -6.76pp, so no variant is promoted.
Liquidity exposure repair factory: factory_batch_20260728_180253_726, configs/strategy_factory_liquidity_repair_balanced_variants.json passed full production diagnostics with 6 ideas, 0 errors, 0 skipped; all 6 rejected. This stage added position stop-loss cooldown, liquidity_exposure_guard_score, single_name_risk_guard_score, tighter amount bucket caps and balanced high-vol protection. Worst daily replay loss improved from -3.14% to -1.64%, failed windows stayed at 73, and underexposed recovery windows fell from 16 to 14, but WF positive rate stayed at 35%-45% and several window-repair variants still breached the -25% drawdown gate. Comparison vs financial-alpha is no_clear_improvement, so no variant is promoted.
Production historical research smoke: historical_20260724_141840_056, production_research=True, short_history
Web smoke: /paper, /ops, /compare, /factory, /data and registry CSV passed; /factory shows factory_batch_20260728_180253_726 and /data shows production_ready assets
```

## Daily Pipeline

生产日跑配置在：

```text
a_share_quant_agent_mvp/configs/daily_pipeline.yaml
```

先诊断今日投资数据新鲜度：

```bash
PYTHONPATH=src python3 examples/diagnose_investoday_freshness.py \
  --config configs/daily_pipeline.yaml \
  --refresh-cache
```

执行日跑流水线：

```bash
PYTHONPATH=src python3 examples/run_daily_pipeline.py \
  --config configs/daily_pipeline.yaml
```

使用外部完整历史 stock master 跑 PIT 历史股票池：

```bash
PYTHONPATH=src python3 examples/run_real_data.py \
  --source investoday \
  --universe historical_stock_master_pit_top_amount \
  --historical-stock-master-path /path/to/full_a_share_stock_master.csv \
  --historical-stock-master-min-rows 3000 \
  --require-production-data \
  --candidate-size 0 \
  --universe-size 100 \
  --start 20210101 \
  --end 20260724
```

验收外部历史 stock master CSV：

```bash
PYTHONPATH=src python3 examples/validate_historical_stock_master.py \
  --path /path/to/full_a_share_stock_master.csv \
  --start 20210101 \
  --end 20260724 \
  --output-dir reports/data_trust
```

把今日投资真实候选池落盘到 `data_assets/investoday_candidate/`：

```bash
PYTHONPATH=src python3 examples/materialize_investoday_data_assets.py \
  --asset-root data_assets \
  --start 20250101 \
  --end 20260724 \
  --universe-size 50 \
  --pit-universe-size 50
```

该命令会输出 `stock_master.csv`、`daily_quotes.csv`、`realtime_universe.csv`、`industry_classification.csv` 和 `manifests/investoday_candidate/data_asset_manifest.json/md`。这些是真实候选池数据资产，但不是无幸存者偏差的全市场历史数据库，因此会标记为 `historical_candidate`，不会通过 `production_data_ready`。

生成全市场真实数据接入 readiness、字段定义、验收标准和接口联调报告：

```bash
PYTHONPATH=src python3 examples/check_full_universe_readiness.py \
  --asset-root data_assets \
  --reports-root reports \
  --start 20210101 \
  --end 20260724 \
  --probe-investoday-cli
```

该命令会输出 `reports/full_universe_readiness/full_universe_readiness.json/md`、`data-definition.md`、`acceptance-criteria.md` 和 `api-integration.md`。当前探针结论：今日投资 `stock/all` 已升级为 GET/query 调用并可运行，`chain/sec-basic-info` 可作为退市/证券基础信息补充源，`stock/adjusted-quotes` 可作为前复权日行情接口；canonical `data_assets/stock_master/historical_stock_master.csv` 与 `data_assets/market/daily_quotes.csv` 已由全量抽取和正式导入写入，readiness 为 `production_ready`。

审计 historical PIT 指数成分/权重和历史行业变更数据源：

```bash
PYTHONPATH=src python3 examples/audit_pit_structure_sources.py \
  --asset-root data_assets \
  --reports-root reports \
  --start 20210101 \
  --end 20260724
```

该命令会输出 `reports/pit_structure_sources/latest_pit_structure_sources.md/json`。当前结论会区分“current snapshot 可用”和“historical PIT 可入生产”：今日投资 `stock/industries`、中证指数公开样本/权重/行业接口只能作为当前快照证据；没有带历史 effective date 的成分/权重和行业变更表时，系统会保持 `do_not_install_current_snapshots_as_pit`。

抽取今日投资全市场数据到 staging，并自动生成生产导入 mapping；默认优先走 `stock/all`，不会写正式 `data_assets/`：

```bash
PYTHONPATH=src python3 examples/extract_investoday_full_universe.py \
  --reports-root reports \
  --asset-root data_assets \
  --start 20210101 \
  --end 20260724 \
  --stock-master-source stock_all \
  --extract-id full_universe_extract_production_quotes \
  --continue-on-quote-error \
  --run-import-dry-run
```

全量日线抽取是长任务；固定 `--extract-id` 后，quote shards 会落在同一个 `runs/<extract_id>/quote_shards/`，中断后原命令重跑即可断点续跑。运行中可查看 `runs/<extract_id>/quote_progress.json/md` 了解批次、行数、失败批次和最近事件。

先只验收今日投资全市场 stock master，可以用 `--stock-master-only` 快速确认主表覆盖；当前 latest 已通过该检查：

```bash
PYTHONPATH=src python3 examples/extract_investoday_full_universe.py \
  --reports-root reports \
  --asset-root data_assets \
  --start 20210101 \
  --end 20260724 \
  --stock-master-source stock_all \
  --stock-master-only
```

如果要接入外部供应商导出的全市场 stock master，也可以用 CSV 作为 licensed fallback 继续抽行情和验收链路：

```bash
PYTHONPATH=src python3 examples/extract_investoday_full_universe.py \
  --reports-root reports \
  --asset-root data_assets \
  --start 20210101 \
  --end 20260724 \
  --stock-master-source csv \
  --stock-master-path /path/to/full_a_share_stock_master.csv \
  --run-import-dry-run
```

该命令会输出 `reports/full_universe_extract/latest_extract.json/md`、`runs/<extract_id>/staging_assets/`、`runs/<extract_id>/quote_shards/`、`runs/<extract_id>/quote_progress.json/md`、`vendor_mapping.generated.yaml`、`extract_manifest.json/md`、`data-definition.md` 和 `api-integration.md`。当前 latest 为 `extracted_ready`：`stock/all + chain/sec-basic-info` 已抽出 5509 个 SH/SZ A 股 symbols，其中 323 行带退市日期/`listStatus=DL`，已硬过滤 `B股`、深市 `200xxx` 和沪市 `900xxx`；全量 `stock/adjusted-quotes` 日线抽取完成，6593923 行、5380 个有行情标的、111/111 批完成、0 失败，并通过生产导入 dry-run。

按供应商 mapping 导入生产 canonical 资产：

```bash
PYTHONPATH=src python3 examples/import_vendor_data_assets.py \
  --mapping configs/vendor_mapping.template.yaml \
  --asset-root data_assets \
  --start 20210101 \
  --end 20260724 \
  --historical-stock-master-min-rows 3000 \
  --min-delisted-rows 50 \
  --chunk-size 100000
```

真实使用时先复制 `configs/vendor_mapping.template.yaml`，把 Wind/Choice/聚源/米筐/聚宽/Tushare 等供应商导出的文件路径和字段名填进去。导入器会写入 canonical production 路径：`stock_master/historical_stock_master.csv`、`market/daily_quotes.csv`、`fundamentals/fundamental_factors.csv`、`index/index_constituents.csv`、`industry/industry_classification.csv`，并输出 `manifests/production_import/data_asset_manifest.json/md`、`production_asset_validation.json/md` 和 `data-definition.md`。

也可以先让供应商接入向导扫描导出目录，自动推断 mapping，并在 staging 目录 dry-run 导入验收：

```bash
PYTHONPATH=src python3 examples/vendor_data_onboarding.py \
  --input-dir /path/to/vendor_exports \
  --output-dir reports/vendor_onboarding/latest \
  --asset-root data_assets \
  --mapping-output configs/vendor_mapping.local.yaml \
  --start 20210101 \
  --end 20260724
```

该向导会输出 `vendor_onboarding.json/md`、`vendor_file_scan.json/md`、`vendor_mapping.suggested.yaml`、`data-definition.md` 和 `acceptance-criteria.md`。当前 latest 用 `data_assets/investoday_candidate/` 跑通扫描，能生成 mapping；该目录只是候选池 fixture，只有 20 只、没有退市样本，且默认策略模板还缺 `dividend_yield` 字段，因此会有意停在生产门控外，不代表当前 canonical production 资产状态。

用生产导入执行器做安全 dry-run；只有 dry-run 通过后，加 `--execute` 才会备份并写入正式 `data_assets/`：

```bash
PYTHONPATH=src python3 examples/execute_production_import.py \
  --mapping configs/vendor_mapping.local.yaml \
  --asset-root data_assets \
  --reports-root reports \
  --start 20210101 \
  --end 20260724
```

正式导入并在通过后触发 production 策略工厂：

```bash
PYTHONPATH=src python3 examples/execute_production_import.py \
  --mapping configs/vendor_mapping.local.yaml \
  --asset-root data_assets \
  --reports-root reports \
  --start 20210101 \
  --end 20260724 \
  --execute \
  --run-strategy-factory
```

当前 latest 用 `reports/full_universe_extract/runs/full_universe_extract_20260725_a_share_master/vendor_mapping.generated.yaml` 跑了执行器，结果为 `imported_factory_completed`：dry-run 与 formal import 均为 `production_ready`，写入前已备份 canonical assets，生产策略工厂已完成。

从今日投资盈利能力端点刷新 canonical ROE 基本面资产：

```bash
PYTHONPATH=src python3 examples/extract_investoday_fundamental_factors.py \
  --asset-root data_assets \
  --reports-root reports \
  --start 20210101 \
  --end 20260724 \
  --api-batch-size 100 \
  --execute
```

当前 canonical `fundamentals/fundamental_factors.csv` 已由 `stock/financial-indicators-profitab` 正式写入：109953 行、5377/5380 eligible symbols、ROE symbol coverage 99.94%，`publishDate/reportPeriodEnd` 已保留并按 `date=publishDate` 做 PIT/as-of 合并。估值字段 `pe/pb` 来自 canonical `market/daily_quotes.csv`，股息率由下一步分红事件富集脚本写入日线。

用 Investoday `stock/dividends` 分红事件富集 canonical 日线：

```bash
PYTHONPATH=src python3 examples/enrich_production_dividend_valuation_factors.py \
  --asset-root data_assets \
  --reports-root reports \
  --start 20210101 \
  --end 20260724 \
  --api-batch-size 100 \
  --execute
```

当前 production 执行结果为 `dividend_valuation_20260726_232839_225`：`data_assets/fundamentals/dividend_events.csv` 写入 22368 条有效现金分红事件，`data_assets/market/daily_quotes.csv` 的 6593923 行已写入 PIT `dividend_yield`。计算口径为 `exDate <= trade date` 的 trailing 365-day `cashDividendPerShare / close`，因此红利模板现在有可审计的真实输入。

只验收当前 canonical production 资产：

```bash
PYTHONPATH=src python3 examples/validate_production_data_assets.py \
  --asset-root data_assets \
  --start 20210101 \
  --end 20260724
```

生成生产数据 readiness 报告；如果提供 `--mapping`，会先导入供应商数据再验收：

```bash
PYTHONPATH=src python3 examples/prepare_production_data.py \
  --asset-root data_assets \
  --reports-root reports \
  --start 20210101 \
  --end 20260724
```

当前 readiness 为 `production_ready`：canonical production 的 `stock_master/historical_stock_master.csv`、`market/daily_quotes.csv`、Investoday ROE `fundamentals/fundamental_factors.csv`、分红事件资产与公告事件资产已存在并通过验收，因此 `production_data_ready=True`。ROE、PE/PB、`dividend_yield` 与 announcement event 模板输入均已解锁；effective `dividend_yield` coverage 为 100.00%。

用 Investoday `announcements` 公告接口生成 canonical 公告事件资产；默认 dry-run，只有加 `--execute` 才写入 `data_assets/events/announcements.csv`：

```bash
PYTHONPATH=src python3 examples/extract_investoday_announcements.py \
  --asset-root data_assets \
  --reports-root reports \
  --start 20210101 \
  --end 20260730 \
  --parallel-workers 8 \
  --execute
```

运行策略工厂模板库：

```bash
PYTHONPATH=src python3 examples/run_strategy_factory.py \
  --templates configs/strategy_factory_templates.json \
  --source sample \
  --start 20210101 \
  --end 20251231
```

默认模板生产 factory 基线为 `factory_batch_20260727_084756_343`：`--source production --asset-root data_assets --benchmark-code 000300` 跑通，7 个模板全部兼容执行，0 个执行错误、0 个 skipped；7 个 idea 均因真实研究门控未达标被 rejected。benchmark 已对齐 1345 个交易日，bias diagnostics 已把 canonical `historical_asset` 识别为真实生产数据；剩余 blockers 主要是 walk-forward、max drawdown、audit abandon，以及部分 factor IC adverse。

保守重写模板生产 factory 为 `factory_batch_20260727_093950_013`：`configs/strategy_factory_defensive_variants.json` 跑通，6 个模板、0 errors、0 skipped，但 6 个 idea 仍全部 rejected。`reports/strategy_factory_comparison/latest_factory_comparison.md/json` 对比基线后结论为 `no_clear_improvement`：best score delta 0.00，best drawdown delta -10.78%，best walk-forward delta 0%；三条策略线中 defensive_cashflow 与 low_vol_dividend 为 mixed，profit_repair 为 regressed。唯一明显改善是 IC 支持数量上升，但回撤和 walk-forward 没有同时改善，因此本轮不进入 paper candidate。

市场状态风控 overlay 生产 factory 为 `factory_batch_20260727_104036_813`：`configs/strategy_factory_regime_overlay_variants.json` 跑通，6 个模板、0 errors、0 skipped，但 6 个 idea 仍全部 rejected。该阶段在 `StrategySpec.risk.risk_overlay` 中新增了可审计的仓位 overlay，使用沪深300 `000300` 的滞后一日趋势、动量和波动字段控制目标总仓位，不影响未开启 overlay 的旧策略。最新 comparison `comparison_factory_batch_20260727_093950_013_vs_factory_batch_20260727_104036_813` 为 `risk_improved`：三条策略线均把最大回撤压到 -25% gate 内，best drawdown delta +27.87%，但 best walk-forward delta -10%，所以仍不进入 paper candidate。轻量 tuning scan 写入 `reports/strategy_factory/regime_overlay_tuning_scan.csv`，结论是更轻 overlay 可保住 WF，但回撤仍在 -33% 到 -45%，不能通过 drawdown gate。

市场状态二代 recovery overlay 生产 factory 为 `factory_batch_20260727_112448_344`：`configs/strategy_factory_regime_recovery_variants.json` 跑通，6 个模板、0 errors、0 skipped，但 6 个 idea 仍全部 rejected。本阶段新增 `reports/strategy_factory_regime_diagnostics/latest_regime_diagnostics.md/json`，把 WF 测试窗口按沪深300 downtrend、uptrend、high-vol、recovery-in-downtrend 和实际 `risk_target_weight` 拆分。一代 overlay 诊断为 120 个 WF 窗口、69 个 failed、12 个 underexposed recovery windows；二代 recovery 后为 120 个 WF 窗口、68 个 failed、12 个 underexposed recovery windows。对比一代 overlay 的 latest comparison `comparison_factory_batch_20260727_104036_813_vs_factory_batch_20260727_112448_344` 为 `no_clear_improvement`：best walk-forward delta +10%，但 best drawdown delta -1.88%，drawdown-cap recovery lift 变体打穿 -25% gate。因此本阶段结论是“diagnostics 和可审计 recovery 机制完成，但不晋级”。

窗口级 fuse/re-entry 生产 factory 为 `factory_batch_20260727_135316_022`：`configs/strategy_factory_regime_fuse_variants.json` 跑通，6 个模板、0 errors、0 skipped，但 6 个 idea 仍全部 rejected。本阶段在 `RiskOverlaySpec` 中新增了滚动窗口 drawdown/rolling return/consecutive-loss fuse、cooldown、bounded re-entry 和风险专用再平衡；新增 `reports/strategy_factory_window_failures/latest_window_failures.md/json` 与日级 replay CSV，把 failed WF window 拆到每日 strategy return、drawdown、risk target、gross exposure、benchmark regime、style exposure 和 top loser contribution。对比二代 recovery 的 latest comparison `comparison_factory_batch_20260727_112448_344_vs_factory_batch_20260727_135316_022` 为 `risk_improved`：三条策略线都显著降低回撤，best drawdown delta +11.27%，但 best walk-forward delta -15%。最终 factory 最大回撤压到 -9.48% 到 -11.74%，但 WF positive rate 只有 25%-35%，window failure replay 显示 fuse 在 failed windows 内过于 sticky，fuse-active day share=100%、re-entry day share=0%。因此本阶段结论是“窗口级熔断机制和诊断闭环完成，但参数不晋级；下一轮应修 re-entry，而不是继续压仓”。

re-entry repair 生产 factory 最终采用 `factory_batch_20260727_152127_098`：本阶段在 `RiskOverlaySpec` 中新增 `fuse_max_active_days`、re-entry 初始仓位、阶梯仓位、确认天数、drawdown repair 开关、波动冷却确认和 failed-reentry 回退阈值，并在 equity/holdings/window failure replay 中输出 active days、re-entry elapsed、re-entry target 和 recovery/volatility confirmation days。第一版 `configs/strategy_factory_regime_reentry_repair_variants.json` 跑出 `factory_batch_20260727_145658_071`，证明 re-entry 已从 0% 修复到 36.19%，但回撤放大到 -22.64% 至 -30.35%，不晋级；收紧后的 `configs/strategy_factory_regime_reentry_balanced_variants.json` 跑出 `factory_batch_20260727_152127_098`，6 个模板、0 errors、0 skipped，仍全部 rejected，但 failed WF windows 从 85 降到 79，failed-window 内 fuse-active day share=41.23%、re-entry day share=28.00%、max re-entry target=40.00%、worst daily return=-3.44%，最大回撤控制在 -17.66% 至 -24.23%。`comparison_factory_batch_20260727_145658_071_vs_factory_batch_20260727_152127_098` 为 `improved`，`comparison_factory_batch_20260727_112448_344_vs_factory_batch_20260727_152127_098` 为 `risk_improved`，但 latest 主对比 `comparison_factory_batch_20260727_135316_022_vs_factory_batch_20260727_152127_098` 为 `no_clear_improvement`：相对 sticky fuse，low_vol_dividend/profit_repair 的 WF 仅提升 5%-10%，但 best drawdown delta 为 -10.21%。因此本阶段结论是“re-entry 机制修复完成，但策略仍未达到 paper candidate；下一轮应修 alpha/WF 和 2024Q4 high-vol uptrend 失效，不再只调仓位闸门”。

alpha/WF repair 生产 factory 最终采用 `factory_batch_20260728_091319_860`：本阶段在 `PortfolioSpec` 中新增 `selection_bucket_field/selection_bucket_count/max_selection_bucket_share`，在选股排序后对数值字段按横截面分位 bucket 做持仓数量 cap；在 `add_robust_factor_features` 中新增 `liquidity_mid_score`、`liquidity_top_penalty_score`、`turnover_sane_score`、`turnover_mid_score`、`trend_confirmation_score`、`anti_chase_score` 和 `alpha_quality_stability_score`，并新增 `examples/alpha_selection_smoke_test.py`。第一版 `configs/strategy_factory_alpha_wf_variants.json` 跑出 `factory_batch_20260728_084421_543`，回撤和部分年化改善，但 IC 支持数下降、failed WF windows 增至 87，说明 binary trend/anti-chase 过钝，不晋级；第二版 `configs/strategy_factory_alpha_ic_supported_variants.json` 跑出 `factory_batch_20260728_091319_860`，6 个模板、0 errors、0 skipped，仍全部 rejected，但 6 条 idea 的 adverse IC 均降为 0，failed WF windows 回到 79，failed-window 内 fuse-active day share=38.88%、re-entry day share=31.15%，最大回撤为 -18.34% 至 -22.36%。latest comparison `comparison_factory_batch_20260727_152127_098_vs_factory_batch_20260728_091319_860` 为 `no_clear_improvement`：best drawdown delta +1.17%、best WF delta 0%，low_vol_dividend WF 仅 +5%，profit_repair WF -5%。因此本阶段结论是“当前生产因子池内的 IC-supported 重组和 liquidity bucket cap 已完成，但仍不能把 WF 拉过 45%；该结论已由后续 financial-alpha 数据源阶段承接”。

dividend event alpha 生产 factory 最终采用 `factory_batch_20260728_095842_074`：本阶段把 canonical `data_assets/fundamentals/dividend_events.csv` 从单一 `dividend_yield` 富集输入扩展为可直接选股的 PIT 事件特征，在 `load_production_asset_panel` 中按 `exDate <= quote date` 和 trailing 365-day 窗口合并 `dividend_event_count_365d`、`dividend_event_cash_365d`、`dividend_event_days_since_last` 和 `dividend_event_last_cash`，再在 `add_robust_factor_features` 中派生 `dividend_event_yield_365d`、`dividend_event_recent_score`、`dividend_event_regular_score`、`dividend_event_cash_score` 和 `dividend_event_quality_score`，并新增 `examples/dividend_event_alpha_smoke_test.py` 防未来数据泄露。`configs/strategy_factory_dividend_event_alpha_variants.json` 跑通 6 个模板、0 errors、0 skipped，但 6 个 idea 仍全部 rejected；最佳 defensive_cashflow 年化从上一代 -1.30% 改到 +1.25%、最大回撤从 -20.78% 改到 -18.29%、IC supportive 从 10 增到 13 且 adverse=0，但 WF positive rate 仍只有 30%-35%。latest comparison `comparison_factory_batch_20260728_091319_860_vs_factory_batch_20260728_095842_074` 为 `no_clear_improvement`：best score delta 0.00、best drawdown delta +2.49pp、best WF delta 0%，三条策略线都是 mixed。window failure replay 显示 80 个 failed WF windows、4842 个 replay days，失败仍集中在 2022Q3、2024Q4 与 2025Q4/2026Q1 的流动性风格暴露。因此本阶段结论是“分红事件数据源已生产化并可审计，但不是足够的新 alpha；下一轮应导入行业分类、成长/现金流/利润率、公告事件、资金流或龙虎榜等非分红类 PIT 数据，再做行业/风格中性和 2024Q4 high-vol uptrend 专项保护”。

industry-neutral 生产 factory 最终采用 `factory_batch_20260728_111933_162`：本阶段新增 `examples/extract_investoday_industry_classification.py`，按 active stock master 分批调用今日投资 `stock-quote/realtime-ext`，写入 canonical `data_assets/industry/industry_classification.csv`：5177 行、31 个一级行业、active symbol coverage 99.83%。该资产保留 `industrySource=investoday:stock-quote/realtime-ext:latest_only`、`industryAsOfDate=2026-07-24` 和 `isLatestOnly=True`，因此是当前行业标签代理，不是严格历史行业变更表；`load_production_asset_panel` 已支持真 PIT 多日期行业表的 as-of 合并，并对 latest-only 单点表走快速 symbol merge。组合侧在 `PortfolioSpec` 中新增 `selection_group_field/max_selection_group_share`，选股器支持在 amount bucket cap 之外再做行业组数量 cap；新增 `examples/industry_classification_smoke_test.py` 验证行业标签不会早于 effective date 生效，并验证单行业 cap。`configs/strategy_factory_industry_neutral_variants.json` 跑通 6 个模板、0 errors、0 skipped，但 6 个 idea 仍全部 rejected；source chain 已包含 `industry_classification_asset+pit_industry_classification`，但结果与 `factory_batch_20260728_095842_074` 完全一致，因为当前组合本身已低于 20% 单行业 cap。latest comparison `comparison_factory_batch_20260728_095842_074_vs_factory_batch_20260728_111933_162` 为 `no_clear_improvement`：best score delta 0.00、best drawdown delta 0.00pp、best WF delta 0%。因此本阶段结论是“行业资产链路和行业 cap 机制完成，但当前宽 cap 没有触发；后续应补真实历史行业变更或更直接的成长、现金流、公告、资金流数据，而不是继续只包装 latest-only 行业约束”。

index constituent PIT 阶段已完成接入层，但未伪造生产成分数据：本阶段新增 `load_index_constituent_asset` 与 `merge_point_in_time_index_constituents`，支持 canonical `data_assets/index/index_constituents.csv` 的多日期指数快照按 as-of 日期合并；每个快照只在“本快照日至下一快照日前”生效，因此下一期被剔除的股票不会被错误保留。`UniverseSpec` 新增 `use_index_membership/index_code`，选股器只有在策略明确打开该开关时才按 `is_index_member_<indexCode>` 过滤；默认全市场/流动性股票池行为不变。`validate_production_asset_bundle` 会展示 optional index constituent rows、index_count、duplicate key 等摘要，但不把它作为生产行情硬门槛。新增 `examples/index_constituent_pit_smoke_test.py` 验证成分加入、剔除、权重更新和指数成员选股过滤。今日投资当前可确认接口仍只有 index quotes/basic-info，没有可用的指数成分权重端点；本阶段结论是“PIT 接入、防未来函数和供应商导入路径完成，等待 Wind/Choice/聚源/米筐/聚宽/Tushare 或已确认接口写入真实 `index_constituents.csv` 后再跑指数成员策略工厂”。

financial alpha failure-window 阶段已完成：本阶段把 `examples/extract_investoday_fundamental_factors.py` 从单一 ROE/盈利能力端点升级为今日投资 `stock/fin-der-inds` 财务衍生指标端点，正式写入 canonical `data_assets/fundamentals/fundamental_factors.csv`：110764 行、5377/5380 eligible symbols、ROE/gross_margin/net_margin/rev_growth_1y/np_growth_1y/cfo_growth_1y/cfo_to_revenue/cash_debt_ratio/debt_asset_ratio 等核心财务 alpha 字段覆盖约 99.94%，F-score 覆盖 98.62%。`load_fundamental_factor_asset`、PIT fundamentals merge、vendor import canonicalizer 和 `add_robust_factor_features` 已支持利润率、成长、现金流、资产负债表和 F-score 组合评分，并新增 `examples/financial_alpha_factor_smoke_test.py` 防未来数据泄露。`configs/strategy_factory_financial_alpha_failure_window_variants.json` 新增 6 个基于现金流质量、利润率质量、成长质量和失败窗口 re-entry 的模板；完整生产诊断 `factory_batch_20260728_163744_760` 在 20210101-20260724 跑通 6 个模板、0 errors、0 skipped，6 个全部 rejected。诊断结论是“财务 alpha 能把 WF 上限推到 45%、failed windows 降到 73，但回撤恶化到 -25.06% 至 -31.28%，comparison vs industry-neutral 为 no_clear_improvement，所以不晋级 paper candidate”。本阶段同时优化了大表 hash 和重复特征派生，避免 full production factory 卡在 659 万行面板预处理。

liquidity exposure repair 阶段已完成但不晋级：本阶段在 `RiskSpec` 中新增 `position_stop_loss_limit/position_stop_cooldown_days`，在回测中实现单名止损卖出和冷却期禁止再选；在 `add_robust_factor_features` 中新增 `liquidity_exposure_guard_score` 与 `single_name_risk_guard_score`，用当日 amount rank、volatility rank、momentum 和 drawdown 抑制“高流动性+高波动+追涨/深回撤”组合暴露；新增 `examples/liquidity_repair_smoke_test.py` 验证止损与冷却不会未来泄露。第一版 `configs/strategy_factory_liquidity_repair_variants.json` 过于保守，最大回撤改善到 -14.98% 至 -22.34%，但 failed windows 升到 81、WF 降到 30%-40%，不晋级。最终采用 balanced 版本 `factory_batch_20260728_180253_726`：`configs/strategy_factory_liquidity_repair_balanced_variants.json` 跑通 6 个模板、0 errors、0 skipped，全部 rejected；最坏日 replay 从上一代 -3.14% 降到 -1.64%，failed windows 保持 73，underexposed recovery windows 从 16 降到 14，但 WF positive rate 仍只有 35%-45%，window-repair 变体最大回撤仍到 -26.75% 至 -28.30%。因此本阶段结论是“单名止损和流动性保护有效降低尾部日损失，但不能单独把策略推到 paper candidate；继续调仓位/流动性约束的边际价值下降”。

stable paper candidate readiness 修复阶段已完成但不晋级：本阶段在 `add_technical_features` 中新增 `momentum_120d`、`momentum_252d`、`volatility_downside_60d`、`drawdown_252d`、`close_to_ma_60d` 和 `trend_persistence_120d`，并在 `add_robust_factor_features` 中派生 `long_trend_quality_score`、`downside_volatility_score`、`reversal_risk_guard_score` 与 `price_trend_stability_score`；`Strategy Factory` 裁剪白名单和 `examples/alpha_selection_smoke_test.py` 已覆盖这些字段。归因偏差诊断已接受 canonical production 中的 `limit_up/limit_down` 价格字段作为涨跌停执行信息，避免把缺少布尔 `is_limit_up/is_limit_down` 误判为 hard fail。主候选 `configs/strategy_factory_price_stability_candidate_variants.json` 跑出 `factory_batch_20260729_093902_880`，备选 `configs/strategy_factory_supportive_recovery_candidate_only.json` 跑出 `factory_batch_20260729_094906_539`，两者均 0 errors、0 skipped、全部 rejected。最佳备选 gate 结果为 `research_only`：生产数据、PIT、benchmark、factor IC、bias diagnostics、drawdown 和 trade sample 通过，IC supportive/adverse 为 19/0，但年化 -1.95%、最大回撤 -21.43%、WF positive rate 40%，失败门槛是 `walk_forward` 和 `audit`。最新 `reports/strategy_factory_diagnostics/latest_factory_diagnostics.md`、`reports/strategy_factory_regime_diagnostics/latest_regime_diagnostics.md` 与 `reports/strategy_factory_window_failures/latest_window_failures.md` 均指向该 factory；失败集中在 downtrend、recovery-in-downtrend 和 high-vol uptrend，dominant style 仍是 liquidity。因此本阶段结论是“候选修复工程与审计链闭环完成，但没有稳定 paper candidate；下一轮必须引入新的 PIT alpha/事件/资金流证据，不能继续只调风控和价格稳定分数”。

capital-flow / dragon-tiger PIT alpha 阶段已完成真实生产落地但不晋级：本阶段确认今日投资 `stock/daily-fund-flows` 可返回日频 `mainNetInflow`、`netInflowLarge`、`netInflowXlarge` 等资金流字段，并用 `stock/dt-details` 抽取真实龙虎榜事件；新增 canonical optional assets `data_assets/market/daily_fund_flows.csv` 与 `data_assets/events/dragon_tiger_details.csv`、生产提取脚本、模板 CSV、vendor import canonicalizer 和 production validation 摘要。`examples/extract_investoday_capital_flow_factors.py --execute` 已全量执行：`investoday_capital_flow_production_20260729` 写入 production `data_assets/market/daily_fund_flows.csv`，覆盖 2021-01-04 至 2026-07-24、6567105 行、5378 个 symbol、0 个重复 date/symbol key、mainNetInflow coverage=100.00%。`examples/extract_investoday_dragon_tiger_details.py --execute` 已全量执行：`investoday_dragon_tiger_production_20260729` 写入 production `data_assets/events/dragon_tiger_details.csv`，覆盖 2021-01-04 至 2026-07-24、181544 条 canonical 事件、5176 个 symbol、0 个重复 `date/symbol/abnormalType/amount` key、amount coverage=96.21%，`reports/investoday_dragon_tiger_details/latest_dragon_tiger.md` 判定 `executed_ready` / `production_ready=True`。`load_production_asset_panel` 现在会在文件存在时把资金流按“latest flow date < quote date”严格滞后合并，龙虎榜事件按“event date < quote date”的 trailing 90-day 窗口生成 `dragon_tiger_count_90d`、`dragon_tiger_amount_90d`、`dragon_tiger_days_since_last`、`dragon_tiger_attention_score`、`dragon_tiger_cooldown_score` 和 `dragon_tiger_event_score`，同日盘后数据不泄露。为支撑全量运行，本阶段优化了 capital-flow PIT 合并、PIT liquidity universe、大表 hash、龙虎榜事件窗口合并和重复 robust 特征计算；龙虎榜事件合并在完整生产面板中从卡住降到约 6-9 秒。生产 factory `factory_batch_20260729_171552_613` 使用 `configs/strategy_factory_capital_flow_candidate_variants.json`、benchmark `000300` 和 `--skip-sensitivity` 跑通 2 个模板，0 errors、0 skipped，source chain 已包含 `capital_flow_asset+pit_capital_flows+dragon_tiger_asset+pit_dragon_tiger_events`；两个 idea 仍全部 rejected，gate=`research_only`。`capital_flow_quality_recovery_guard`：score=43.69、年化 -3.10%、最大回撤 -31.92%、WF positive rate 35%、IC supportive/adverse=12/5；`capital_flow_dragon_tiger_event_guard`：score=43.69、年化 -3.02%、最大回撤 -33.55%、WF positive rate 35%、IC supportive/adverse=12/7。`reports/strategy_factory_window_failures/latest_window_failures.md` 当时显示 26 个 failed WF windows；`reports/strategy_factory_regime_diagnostics/latest_regime_diagnostics.md` 显示失败集中在 downtrend/recovery-in-downtrend，underexposed recovery windows=6；comparison `comparison_factory_batch_20260729_143935_735_vs_factory_batch_20260729_171552_613` 为 `no_clear_improvement`。结论是“资金流与龙虎榜真实生产资产、防未来函数和候选工厂均完成，但它们仍不是足够 alpha；该结论已由后续 staged recovery / full sensitivity 阶段承接，不能人工覆盖 gate”。

drawdown-gated staged recovery / full sensitivity 阶段已完成但不晋级：本阶段在 `RiskOverlaySpec` 中新增 `use_staged_recovery`、分段阈值/仓位、趋势坏场景要求、组合回撤触发/地板和 drawdown-lift 控制；`_risk_target_weight` 会在非 crisis 状态下只对“组合受损但未破坏、短期 benchmark momentum 修复、长期趋势仍差”的窗口做有界恢复仓位，不放松 -25% drawdown gate。`examples/risk_overlay_smoke_test.py` 已覆盖 staged recovery 0.66/0.78 目标仓位、深回撤地板保护和正常趋势满仓路径。为跑完整生产 sensitivity，本阶段还让 `sensitivity.run_parameter_sensitivity`、`strategy_factory` 与 `walk_forward` 复用 `_prepare_data` 后的 MultiIndex 面板，并补齐 factor IC、归因、行业暴露对 MultiIndex 的兼容处理；`A_SHARE_FACTORY_PROGRESS=1` 会输出候选级 step 进度。首轮 staged production factory `factory_batch_20260730_090944_840` 使用 `configs/strategy_factory_capital_flow_staged_recovery_variants.json`、benchmark `000300` 和完整 sensitivity 跑通 3 个模板，0 errors、0 skipped，三条全部 rejected。`capital_flow_staged_recovery_balanced`：score=39.94、年化 -3.77%、最大回撤 -27.29%、WF positive rate 30%、IC supportive/adverse=15/4；`dragon_tiger_cooldown_staged_recovery`：score=41.86、年化 -3.45%、最大回撤 -25.47%、WF positive rate 35%、IC supportive/adverse=15/5；`extreme_outflow_avoidance_staged_recovery`：score=45.00、年化 -3.30%、最大回撤 -21.78%、WF positive rate 30%、IC supportive/adverse=18/2。`reports/strategy_factory_window_failures/latest_window_failures.md` 当时显示 41 个 failed WF windows、2482 个 replay days、failed windows average risk target=25.95%、average gross exposure=12.88%、worst daily return=-1.30%；`reports/strategy_factory_regime_diagnostics/latest_regime_diagnostics.md` 显示 60 个总 WF windows、19 个 ok、41 个 failed、underexposed recovery windows=12；comparison `comparison_factory_batch_20260729_171552_613_vs_factory_batch_20260730_090944_840` 为 `no_clear_improvement`，best drawdown delta +11.77pp 但 best WF delta -5pp、best annualized delta -0.28pp。结论是“staged recovery 机制、完整 sensitivity 性能路径和诊断闭环完成，但该经济逻辑仍未产生 stable paper candidate；当前资金流/龙虎榜线应只保留为 rewrite/archive 候选，该结论已由后续 production panel cache / attribution acceleration 阶段复验”。

production panel cache / attribution acceleration 阶段已完成但不改变晋级结论：本阶段在 `load_production_asset_panel` 顶层加入持久化 production panel cache，cache key 包含起止日期、universe 参数、生产数据门槛、fundamental fields，以及 stock master、daily quotes、fundamentals、dividend events、daily fund flows、dragon tiger、industry、index constituents 等源文件的路径、大小和 mtime；任一源文件变化或参数变化都会自动失效，`A_SHARE_PRODUCTION_PANEL_CACHE=0` 可关闭缓存。新增 `examples/production_panel_cache_smoke_test.py` 验证首次写 cache、二次命中和源文件变化失效。归因侧不改变 style z-score 定义，仍按当日横截面计算，但 `_prepare_panel` 先裁剪到归因所需列和持仓日期范围，避免复制 139 列全宽生产面板；`examples/attribution_smoke_test.py` 已通过。真实生产暖机结果：首轮完整构建 `6727912` 行、139 列生产面板并写入 `data_assets/cache/production_panels/production_panel_a0d1feb99ad3b01defa984b8.pkl`，cache 大小约 7.0G，用时约 965s；第二轮同参数加载命中 `production_panel_cache_hit`，用时约 23s，data_hash 保持 `4b5bfc57961848d8469b04d696dd7e3ba4acc6f16047eac04a7ba27fa0b52071`。缓存与归因优化后，完整 3-idea staged recovery production factory `factory_batch_20260730_101723_741` 用时约 337s，上一轮同配置约 1351s；单候选 attribution 从约 235-272s 降到 11-14s。该 factory 仍是 3 rejected、0 errors、0 skipped、0 paper candidates；最佳 `extreme_outflow_avoidance_staged_recovery` 指标不变，score=45.00、年化 -3.30%、最大回撤 -21.78%、WF positive rate 30%、IC supportive/adverse=18/2。`reports/strategy_factory_diagnostics/latest_factory_diagnostics.md`、`reports/strategy_factory_regime_diagnostics/latest_regime_diagnostics.md`、`reports/strategy_factory_window_failures/latest_window_failures.md` 和 completion readiness 已刷新到 `factory_batch_20260730_101723_741`；readiness 仍为 `production_research_ready_no_stable_candidate`，completion level 4/7。

announcement event PIT alpha 阶段已完成真实生产落地但不晋级：本阶段确认今日投资 `announcements` GET 接口可按 `stockCode/beginDate/endDate/pageNum/pageSize` 返回上市公司公告；新增 canonical optional asset `data_assets/events/announcements.csv`、`load_announcement_event_asset`、`merge_point_in_time_announcement_events`、vendor import canonicalizer、production validation 摘要、production panel cache 指纹、`examples/extract_investoday_announcements.py` 和 `examples/announcement_event_alpha_smoke_test.py`。公告特征只使用事实披露日期、标题和类型做 trailing 30/90/180/365-day 计数、最近性、噪音保护、回购/分红/融资/重组/风险提示/报告类事实分组；同日公告用 `event date < quote date` 排除，避免盘后披露泄漏，不做主观利好/利空判断。全量生产抽取 `investoday_announcements_production_20260730` 已写入 `data_assets/events/announcements.csv`：1365134 条 canonical 公告、5274 个 covered symbols、0 个重复 `date/symbol/title/announcementType` key、title/type coverage=98.03%、production_ready=True。新增 `configs/strategy_factory_announcement_event_alpha_variants.json` 跑出 production factory `factory_batch_20260730_110812_958`：3 个模板执行、0 errors、0 skipped，source chain 包含 `announcement_event_asset+pit_announcement_events`，但 3 个 idea 仍全部 rejected、0 paper candidates。`announcement_information_quality_guard` score=45.00，`announcement_buyback_shareholder_return_guard` score=45.00，`announcement_event_cooldown_defensive` score=43.54；regime diagnostics 显示 60 个 WF windows、36 个 failed windows、underexposed recovery windows=0；window failure replay 为 36 个 failed windows、2190 个 replay days；comparison vs `factory_batch_20260730_101723_741` 为 `no_clear_improvement`。冷构建公告 panel 写入新 cache `production_panel_89652122334679447c6563cc.pkl`，约 9.1G；同参数二次加载已确认 `production_panel_cache_hit=True`，公告字段存在。本轮 cold build 暴露 industry latest-only merge 慢点，已将该路径改为 symbol 映射和一次性 concat，并把公告 raw feature 列改为批量拼接；相关 smoke 已通过，尚未重新做完整 cold-build 基准。

margin-trades PIT alpha 阶段已完成真实生产落地但不晋级：本阶段确认今日投资 `stock/margin-trades` POST 接口可按 `stockCodes/beginDate/endDate/pageNum/pageSize` 返回日频融资融券明细；新增 canonical optional asset `data_assets/market/margin_trades.csv`、`load_margin_trade_asset`、`merge_point_in_time_margin_trades`、vendor import canonicalizer、production validation 摘要、`examples/extract_investoday_margin_trades.py`、`examples/margin_trade_alpha_smoke_test.py` 和 `configs/strategy_factory_margin_trade_alpha_variants.json`。两融特征严格使用 `marginTradeDate < quote date`，生成 `margin_net_buy_to_amount`、融资余额/融券余额相对成交额、净买入强度、去杠杆保护、余额拥挤保护、空头压力保护和 `margin_trade_quality_score`；同日两融行排除，避免盘后数据泄漏。全量生产抽取 `investoday_margin_trades_production_20260730` 已写入 `data_assets/market/margin_trades.csv`：3973643 行、3718 个 covered symbols、0 个重复 `date/symbol` key、marginBalance/marginBuyAmount/marginRepayAmount coverage=69.11%、production_ready=True。为避免 optional 大资产在无关模板中拖垮宽面板，`load_production_asset_panel` 新增 `required_data_fields` gating，Strategy Factory 会按模板显式请求字段只加载必要 optional assets；本阶段 margin factory source chain 为 `fundamental_factor_asset+pit_fundamental_factors+margin_trade_asset+pit_margin_trades+pit_liquidity_universe`，跳过资金流、公告、龙虎榜和行业 optional 资产，冷构建写入 cache `production_panel_560e4bbd0c4155b4426b441e.pkl`，约 6.2G；同参数二次加载已确认 `production_panel_cache_hit=True`、6727912 行、122 列且两融字段存在。production factory `factory_batch_20260730_151635_225` 跑通 3 个模板、0 errors、0 skipped，但 3 个 idea 仍全部 rejected、0 paper candidates：`margin_deleveraging_defensive_guard` score=37.79、annualized=-11.90%、max drawdown=-61.09%、WF positive rate=45%、IC supportive/adverse=6/8；`margin_leverage_flow_quality_guard` score=36.74、annualized=-10.83%、max drawdown=-57.54%、WF positive rate=40%、IC supportive/adverse=12/4；`margin_net_buy_repair_guard` score=36.74、annualized=-10.71%、max drawdown=-58.58%、WF positive rate=40%、IC supportive/adverse=7/6。Diagnostics 显示 60 个 WF windows、35 个 failed windows、2128 个 replay days、underexposed recovery windows=0；comparison vs announcement factory `factory_batch_20260730_110812_958` 为 `no_clear_improvement`；completion readiness 仍为 `production_research_ready_no_stable_candidate`，completion level 4/7。

alpha-line retirement 阶段已完成：新增 `src/a_share_quant_agent/alpha_line_retirement.py`、`examples/build_alpha_line_retirement.py` 和 `examples/alpha_line_retirement_smoke_test.py`，会从 `reports/strategy_factory/idea_registry.jsonl` 读取生产 Strategy Factory 证据，对资本流/龙虎榜、公告、融资融券三条反复失败的弱 alpha line 建立归档账本。当前 ledger `alpha_retirement_20260730_163824_833` 统计 168 条 registry 记录、98 个 unique ideas，3/3 tracked lines 均为 `retired_requires_rewrite`：资本流/龙虎榜 best score 45.00、best WF 40%；公告 best score 45.00、best WF 45%；融资融券 best score 37.79、best WF 45%、best drawdown -57.54%。Strategy Factory 新增 `--skip-retired-alpha-lines`，默认不改变旧行为；开启后，除非模板声明 `alpha_lineage.status="rewrite"`、提供足够长的 `rewrite_hypothesis` 和 `material_changes`，否则会在加载多 GB production panel 前直接跳过退休线。验证运行 `factory_batch_20260730_163825_010` 对融资融券模板输出 0 records、3 skipped、0 errors，source=`production+alpha_line_retirement_screen`。`completion_readiness` 已兼容这种归档筛选板：Strategy Factory 阶段会使用 run registry 中最近的 production_research 记录作为可评估证据，避免把“主动归档弱线”误判成工程倒退。

regime-specific failure-window 阶段已完成第一版规则化落地但不晋级：本阶段在 `RiskOverlaySpec` 中新增 `use_high_vol_uptrend_guard`、`use_uptrend_tail_guard` 和 `use_downtrend_loss_cluster_fuse`，全部只读取滞后一日 benchmark regime 字段。`high_vol_uptrend_guard` 用 `benchmark_trend_200d_lag1` + `benchmark_volatility_60d_lag1 > benchmark_volatility_60d_q80_lag1` 给 2024Q4 类窗口封顶；`uptrend_tail_guard` 在上行环境短动量转弱时给 2025Q4/2026Q1 类窗口封顶；`downtrend_loss_cluster_fuse` 在长趋势坏或 recovery-in-downtrend 且组合短窗亏损聚集时提前触发已有 window fuse。新增 `configs/strategy_factory_regime_specific_failure_window_variants.json`，只使用非退休的 cashflow、dividend-event、price-stability、liquidity guard 和 balance-sheet/profitability 逻辑；为避免 latest-only 行业标签成为本阶段内存瓶颈，新模板保留 amount bucket cap，不启用行业组 cap。全量 20210101-20260724 冷构建曾因内存压力退出 137；随后用目标窗口生产验证 `20220701-20260724` 跑通 `factory_batch_20260730_170630_450`：3 个模板、0 errors、0 skipped、全部 rejected、0 paper candidates。最佳 `downtrend_cluster_fuse_reentry_guard` score=44.11、WF positive rate=35.71%、max drawdown=-14.91%、IC supportive/adverse=14/0；另外两条 score=40.99/41.12、WF positive rate=35.71%、max drawdown约 -21%。新 window failure replay 显示 2022Q3 failed windows=0、2024Q4 failed windows=3、fuse-active day share=39.48%、re-entry day share=37.49%、worst daily return 从上一轮融资融券失败窗口的 -4.89% 降到 -3.54%；但 failed windows 仍为 27/42，且 failed average risk target=37.12% 低于 OK average risk target=41.38%，说明第一版规则把尾部压住了，却仍没有修好 walk-forward。当前结论是“阶段 3 工程完成，研究不晋级；下一步不应继续加宽 broad guard，而应在第 4 阶段寻找 stable paper candidate 或做 drawdown-gated recovery exposure repair”。

stable paper candidate 第 4 阶段已完成两轮真实生产尝试但不晋级：本阶段新增 `configs/strategy_factory_stable_candidate_recovery_repair_variants.json`，只使用未退休 alpha line 和已验证的生产字段面，围绕 cashflow/profitability/dividend-event/price-stability/downside-vol/liquidity guard 做三条候选，并把第 3 阶段发现的 recovery underexposure 作为主要修复对象。目标窗口生产 factory `factory_batch_20260731_083131_619` 使用 benchmark `000300`、`--skip-retired-alpha-lines`、`--skip-sensitivity`、`--skip-attribution` 和 `--skip-industry-exposure` 跑通 3 个模板、0 errors、0 skipped，但全部 rejected。最佳 `quality_low_vol_recovery_candidate` score=41.60、annualized=-2.58%、max drawdown=-23.26%、WF positive rate=42.86%、failed_oos=8/14、IC supportive/adverse=20/0；`price_stability_recovery_candidate` 同为 WF 42.86%，`recovery_lift_balanced_candidate` 为 35.71%。随后用同一缓存字段面直接生成第二轮简单 overlay 正式 factory `factory_batch_20260731_084206_074`，验证 sticky fuse 是否是主因；3 个模板、0 errors、0 skipped，仍全部 rejected。`liquid_price_no_overlay_candidate` 把 WF 提到 50.00%，但 max drawdown 恶化到 -40.80%；`quality_low_vol_simple_recovery_candidate` 和 `price_stability_market_timing_candidate` 仍只有 42.86%/35.71%。因此本阶段结论是“没有 stable paper candidate；调低 fuse 粘性或提高 recovery lift 不能解决 2023-2024 与 2025Q4/2026Q1 的负窗口，下一阶段必须转向新的 PIT alpha 证据、窗口级 alpha 归因/特征发现或更严格的候选入池前筛选，而不是继续叠加 broad risk guard”。当前 completion readiness 应保持 `production_research_ready_no_stable_candidate`，不允许人工改成 paper candidate。

window-level alpha discovery 阶段已完成但不晋级：本阶段新增 `examples/summarize_strategy_factory_alpha_discovery.py` 和 `examples/alpha_discovery_smoke_test.py`，把每个 Strategy Factory 候选的 `walk_forward.csv` 与 `factor_ic.csv/factor_ic_summary.csv` 连接起来，按 failed/ok 测试窗口重新统计因子 IC、positive rate、long-short spread 和 failed-window robust score；输出 `reports/strategy_factory_alpha_discovery/latest_alpha_discovery.md/json/csv`，并自动生成 `configs/strategy_factory_alpha_discovery_candidate_variants.json`。第一轮 alpha discovery 基于 `factory_batch_20260731_084206_074` 判定 `downside_volatility_score`、`liquidity_exposure_guard_score`、`single_name_risk_guard_score`、`dividend_event_quality_score`、`valuation_sanity_score` 等为 failed-window core factors，剔除 `liquidity_mid_score`；随后用生成配置跑 production factory `factory_batch_20260731_085702_363`，benchmark `000300`、retired alpha-line screening、attribution/bias diagnostics 启用、0 errors、0 skipped。两个候选仍全部 rejected：`alpha_discovery_core_factor_emphasis_candidate` score=45.00、annualized=-3.08%、max drawdown=-24.81%、WF positive rate=50.00%、failed_oos=7/14、IC supportive/adverse=15/0、gate blockers=`walk_forward|audit`；`alpha_discovery_failed_window_robust_candidate` score=44.81、annualized=-3.37%、max drawdown=-28.08%、WF positive rate=42.86%、blockers=`walk_forward|drawdown|audit`。本阶段的正向贡献是把简单 overlay 批次的 failed windows 从 26 降到 17，并消除了 bias_diagnostics blocker；但年化收益仍为负、WF 仍远低于 75% 且 failed_oos 未归零，所以不能晋级。下一步如果继续做候选，应先引入新的非同质 PIT alpha 或做窗口级“避开负窗口的可交易入场过滤”，而不是继续在同一批 failed-window core factors 上调权重。

alpha-health avoidance filter 阶段已完成工程落地并取得局部改善但不晋级：本阶段在 `RiskOverlaySpec` 中新增 `use_alpha_health_filter`、`alpha_health_field/min/warning/off_weight/weak_weight`、`use_market_breadth_filter` 和 `market_breadth_*` 参数；`add_robust_factor_features` 现在从横截面动量、均线、回撤、price stability、downside volatility、liquidity exposure、single-name risk 和 alpha quality 中派生市场级健康字段，并统一写入 `market_alpha_health_score_lag1`、`market_breadth_20d_lag1`、`market_breadth_60d_lag1`、`market_breadth_120d_lag1` 等滞后一日字段，避免同日市场状态泄漏。`_risk_target_weight` 会在原有 trend/momentum/recovery/fuse 之后再套 alpha-health/breadth 仓位上限，equity curve 输出 `alpha_health_filter_weight`、`alpha_health_score` 和 `market_breadth_score` 供诊断；`required_risk_overlay_fields` 与 Strategy Factory 裁剪白名单已同步，`examples/risk_overlay_smoke_test.py` 验证 full/weak/off 三档。新增 `configs/strategy_factory_alpha_health_filter_variants.json`。完整目标窗口 `20220701-20260724` 冷构建在 production panel 合并阶段 exit 137，未写出 factory board；随后用仍覆盖主要失败窗口的 `20230101-20260724` 跑通 production factory `factory_batch_20260731_093208_410`：3 个模板、0 errors、0 skipped。最佳 `alpha_health_soft_gate_candidate` 从上一阶段 rejected 推进到 `testing/refine`，score=49.33、annualized=+3.26%、max drawdown=-23.11%、trade_count=4245、IC supportive/adverse=20/0、gate blockers 只剩 `walk_forward`；平均 risk target=57.64%、filter-active day share=46.81%、off day share=0。失败点是 WF positive rate 只有 41.67%、failed_oos=7/12，仍远低于 75% 且 failed_oos 必须为 0。严格 alpha-health/breadth gate 把 off day share 提到约 32%-35%，但产生 0% test annualized windows，而当前 walk-forward 规则把 `test_ann <= 0` 记为 failed_oos；因此过严“空仓规避”会自带失败窗口。一次软过滤 refinement 冷构建也在股息事件合并阶段 exit 137，未形成 board。结论是“入场过滤工程有效，能把年化转正、消除 audit/bias/drawdown blocker 并推到 testing/refine，但不能单独过 paper candidate；下一步必须解决 walk-forward 定义下的正收益来源问题，例如引入现金收益/基准替代资产建模、真正新的 PIT alpha，或在不修改 gate 的前提下找到能在 2023H2-2024H1 与 2025Q4/2026Q1 仍产生正收益的可交易信号”。

production panel cache governance 阶段已完成工程闭环但不改变策略晋级结论：新增 `src/a_share_quant_agent/cache_governance.py`、`examples/manage_production_panel_cache.py` 和 `examples/production_panel_cache_governance_smoke_test.py`，治理能力包括 cache manifest、同名 JSON sidecar、legacy cache 标记、stale tmp 清理计划、按总容量 cap 的 dry-run/execute 清理、保留最新 N 个 cache 文件和报告落档。`_write_production_panel_cache` 现在会在写入新 pickle 后自动生成 sidecar，避免为了审计去加载多 GB pickle；旧 pickle 不强制反序列化，报告会标记为 `legacy_unindexed`。真实 dry-run `PYTHONPATH=src python3 examples/manage_production_panel_cache.py --asset-root data_assets --max-total-gb 16 --keep-latest 2` 已写入 `reports/cache_governance/latest_cache_governance.md/json`：当前 3 个旧 cache 合计 22.31G，3 个均为 legacy，计划保留最新 2 个并选择最老的 `production_panel_a0d1feb99ad3b01defa984b8.pkl` 作为清理候选，预计回收 7.02G、降至 15.29G；本次未加 `--execute`，因此没有删除任何生产 cache 文件。

当前因子质量审计为 `factor_quality_20260728_130750_269`：`reports/factor_quality/latest_factor_quality.md/json` 显示 hard_failed=0、warnings=2。核心输入覆盖率足够：`dividend_yield` row coverage 100.00%、`pb` 99.98%、`pe` 99.95%、ROE symbol coverage 99.81%，canonical `industry_classification.csv` 已存在。需要作为下一轮策略优化前置 QA 的 watch items：`dividend_yield >= 20%` 共 4451 行、`pb <= 0` 共 52061 行。

生成弱 alpha line 归档账本，并在策略工厂里跳过已退休逻辑：

```bash
PYTHONPATH=src python3 examples/build_alpha_line_retirement.py \
  --reports-root reports

PYTHONPATH=src python3 examples/alpha_line_retirement_smoke_test.py

PYTHONPATH=src python3 examples/run_strategy_factory.py \
  --templates configs/strategy_factory_margin_trade_alpha_variants.json \
  --source production \
  --asset-root data_assets \
  --start 20210101 \
  --end 20260724 \
  --skip-retired-alpha-lines \
  --no-benchmark \
  --skip-sensitivity \
  --skip-walk-forward \
  --skip-factor-ic \
  --skip-attribution \
  --skip-industry-exposure
```

复跑第 3 阶段 regime-specific failure-window 模板；目标窗口验证避免全量冷构建 OOM，保留 walk-forward 和 factor IC 门控：

```bash
PYTHONPATH=src python3 examples/risk_overlay_smoke_test.py

PYTHONPATH=src python3 examples/run_strategy_factory.py \
  --templates configs/strategy_factory_regime_specific_failure_window_variants.json \
  --source production \
  --asset-root data_assets \
  --start 20220701 \
  --end 20260724 \
  --benchmark-code 000300 \
  --skip-sensitivity \
  --skip-attribution \
  --skip-industry-exposure

PYTHONPATH=src python3 examples/summarize_strategy_factory_diagnostics.py \
  --reports-root reports \
  --factory-id factory_batch_20260730_170630_450

PYTHONPATH=src python3 examples/summarize_strategy_factory_regime_diagnostics.py \
  --reports-root reports \
  --factory-id factory_batch_20260730_170630_450

PYTHONPATH=src python3 examples/summarize_strategy_factory_window_failures.py \
  --reports-root reports \
  --factory-id factory_batch_20260730_170630_450
```

需要基于当前 canonical production 资产复跑策略工厂时：

```bash
PYTHONPATH=src python3 examples/run_strategy_factory.py \
  --templates configs/strategy_factory_templates.json \
  --source production \
  --asset-root data_assets \
  --start 20210101 \
  --end 20260724 \
  --benchmark-code 000300 \
  --skip-incompatible-templates
```

复跑 announcement event alpha 模板；当前 `data_assets/events/announcements.csv` 已安装，若未来缺失该文件模板会干净跳过：

```bash
PYTHONPATH=src python3 examples/announcement_event_alpha_smoke_test.py

PYTHONPATH=src python3 examples/run_strategy_factory.py \
  --templates configs/strategy_factory_announcement_event_alpha_variants.json \
  --source production \
  --asset-root data_assets \
  --start 20210101 \
  --end 20260730 \
  --benchmark-code 000300 \
  --skip-incompatible-templates
```

复跑保守重写模板并生成与基线的对比：

```bash
PYTHONPATH=src python3 examples/run_strategy_factory.py \
  --templates configs/strategy_factory_defensive_variants.json \
  --source production \
  --asset-root data_assets \
  --start 20210101 \
  --end 20260724 \
  --benchmark-code 000300 \
  --skip-incompatible-templates

PYTHONPATH=src python3 examples/summarize_strategy_factory_diagnostics.py \
  --reports-root reports

PYTHONPATH=src python3 examples/compare_strategy_factory_generations.py \
  --reports-root reports \
  --baseline-factory-id factory_batch_20260727_084756_343 \
  --challenger-factory-id factory_batch_20260727_093950_013
```

复跑市场状态风控 overlay 模板，并与保守重写基线对比：

```bash
PYTHONPATH=src python3 examples/run_strategy_factory.py \
  --templates configs/strategy_factory_regime_overlay_variants.json \
  --source production \
  --asset-root data_assets \
  --start 20210101 \
  --end 20260724 \
  --benchmark-code 000300 \
  --skip-incompatible-templates

PYTHONPATH=src python3 examples/summarize_strategy_factory_diagnostics.py \
  --reports-root reports

PYTHONPATH=src python3 examples/compare_strategy_factory_generations.py \
  --reports-root reports \
  --baseline-factory-id factory_batch_20260727_093950_013 \
  --challenger-factory-id factory_batch_20260727_104036_813
```

复跑二代 recovery overlay 模板，并与一代 overlay 对比：

```bash
PYTHONPATH=src python3 examples/run_strategy_factory.py \
  --templates configs/strategy_factory_regime_recovery_variants.json \
  --source production \
  --asset-root data_assets \
  --start 20210101 \
  --end 20260724 \
  --benchmark-code 000300 \
  --skip-incompatible-templates

PYTHONPATH=src python3 examples/summarize_strategy_factory_diagnostics.py \
  --reports-root reports

PYTHONPATH=src python3 examples/summarize_strategy_factory_regime_diagnostics.py \
  --reports-root reports \
  --factory-id latest

PYTHONPATH=src python3 examples/compare_strategy_factory_generations.py \
  --reports-root reports \
  --baseline-factory-id factory_batch_20260727_104036_813 \
  --challenger-factory-id factory_batch_20260727_112448_344
```

复跑窗口级 fuse/re-entry 模板，并与二代 recovery 对比：

```bash
PYTHONPATH=src python3 examples/run_strategy_factory.py \
  --templates configs/strategy_factory_regime_fuse_variants.json \
  --source production \
  --asset-root data_assets \
  --start 20210101 \
  --end 20260724 \
  --benchmark-code 000300 \
  --skip-incompatible-templates

PYTHONPATH=src python3 examples/summarize_strategy_factory_diagnostics.py \
  --reports-root reports

PYTHONPATH=src python3 examples/summarize_strategy_factory_regime_diagnostics.py \
  --reports-root reports \
  --factory-id latest

PYTHONPATH=src python3 examples/summarize_strategy_factory_window_failures.py \
  --reports-root reports \
  --factory-id latest

PYTHONPATH=src python3 examples/compare_strategy_factory_generations.py \
  --reports-root reports \
  --baseline-factory-id factory_batch_20260727_112448_344 \
  --challenger-factory-id factory_batch_20260727_135316_022
```

复跑 re-entry balanced 模板，并与 sticky window fuse 对比：

```bash
PYTHONPATH=src python3 examples/run_strategy_factory.py \
  --templates configs/strategy_factory_regime_reentry_balanced_variants.json \
  --source production \
  --asset-root data_assets \
  --start 20210101 \
  --end 20260724 \
  --benchmark-code 000300 \
  --skip-incompatible-templates

PYTHONPATH=src python3 examples/summarize_strategy_factory_diagnostics.py \
  --reports-root reports \
  --factory-id latest

PYTHONPATH=src python3 examples/summarize_strategy_factory_regime_diagnostics.py \
  --reports-root reports \
  --factory-id latest

PYTHONPATH=src python3 examples/summarize_strategy_factory_window_failures.py \
  --reports-root reports \
  --factory-id latest

PYTHONPATH=src python3 examples/compare_strategy_factory_generations.py \
  --reports-root reports \
  --baseline-factory-id factory_batch_20260727_135316_022 \
  --challenger-factory-id factory_batch_20260727_152127_098
```

复跑 alpha IC-supported 模板，并与 re-entry balanced 对比：

```bash
PYTHONPATH=src python3 examples/alpha_selection_smoke_test.py

PYTHONPATH=src python3 examples/run_strategy_factory.py \
  --templates configs/strategy_factory_alpha_ic_supported_variants.json \
  --source production \
  --asset-root data_assets \
  --start 20210101 \
  --end 20260724 \
  --benchmark-code 000300 \
  --skip-incompatible-templates

PYTHONPATH=src python3 examples/summarize_strategy_factory_diagnostics.py \
  --reports-root reports \
  --factory-id latest

PYTHONPATH=src python3 examples/summarize_strategy_factory_regime_diagnostics.py \
  --reports-root reports \
  --factory-id latest

PYTHONPATH=src python3 examples/summarize_strategy_factory_window_failures.py \
  --reports-root reports \
  --factory-id latest

PYTHONPATH=src python3 examples/compare_strategy_factory_generations.py \
  --reports-root reports \
  --baseline-factory-id factory_batch_20260727_152127_098 \
  --challenger-factory-id factory_batch_20260728_091319_860
```

复跑 dividend event alpha 模板，并与 alpha IC-supported 对比：

```bash
PYTHONPATH=src python3 examples/dividend_event_alpha_smoke_test.py

PYTHONPATH=src python3 examples/run_strategy_factory.py \
  --templates configs/strategy_factory_dividend_event_alpha_variants.json \
  --source production \
  --asset-root data_assets \
  --start 20210101 \
  --end 20260724 \
  --benchmark-code 000300 \
  --skip-incompatible-templates

PYTHONPATH=src python3 examples/summarize_strategy_factory_diagnostics.py \
  --reports-root reports \
  --factory-id latest

PYTHONPATH=src python3 examples/summarize_strategy_factory_regime_diagnostics.py \
  --reports-root reports \
  --factory-id latest

PYTHONPATH=src python3 examples/summarize_strategy_factory_window_failures.py \
  --reports-root reports \
  --factory-id latest

PYTHONPATH=src python3 examples/compare_strategy_factory_generations.py \
  --reports-root reports \
  --baseline-factory-id factory_batch_20260728_091319_860 \
  --challenger-factory-id factory_batch_20260728_095842_074
```

复跑 industry-neutral 模板，并与 dividend event alpha 对比：

```bash
PYTHONPATH=src python3 examples/extract_investoday_industry_classification.py \
  --asset-root data_assets \
  --reports-root reports \
  --start 20210101 \
  --end 20260724 \
  --api-batch-size 10 \
  --execute

PYTHONPATH=src python3 examples/industry_classification_smoke_test.py

PYTHONPATH=src python3 examples/run_strategy_factory.py \
  --templates configs/strategy_factory_industry_neutral_variants.json \
  --source production \
  --asset-root data_assets \
  --start 20210101 \
  --end 20260724 \
  --benchmark-code 000300 \
  --skip-incompatible-templates

PYTHONPATH=src python3 examples/summarize_strategy_factory_diagnostics.py \
  --reports-root reports \
  --factory-id latest

PYTHONPATH=src python3 examples/summarize_strategy_factory_regime_diagnostics.py \
  --reports-root reports \
  --factory-id latest

PYTHONPATH=src python3 examples/summarize_strategy_factory_window_failures.py \
  --reports-root reports \
  --factory-id latest

PYTHONPATH=src python3 examples/compare_strategy_factory_generations.py \
  --reports-root reports \
  --baseline-factory-id factory_batch_20260728_095842_074 \
  --challenger-factory-id factory_batch_20260728_111933_162
```

跑生产因子质量审计：

```bash
PYTHONPATH=src python3 examples/audit_production_factor_quality.py \
  --asset-root data_assets \
  --reports-root reports \
  --start 20210101 \
  --end 20260724
```

汇总最新策略工厂失败原因和下一轮研究动作：

```bash
PYTHONPATH=src python3 examples/summarize_strategy_factory_diagnostics.py \
  --reports-root reports
```

按 `data_assets/` 离线资产运行生产级历史研究：

```bash
PYTHONPATH=src python3 examples/run_production_historical_research.py \
  --asset-root data_assets \
  --start 20210101 \
  --end 20260724 \
  --historical-stock-master-min-rows 3000 \
  --universe-size 100
```

如果没有离线 `market/daily_quotes.csv`，可以显式启用今日投资分片加载；每个 shard 会写入 CSV 和 `shard_manifest.json`，支持断点复用：

```bash
PYTHONPATH=src python3 examples/run_production_historical_research.py \
  --asset-root data_assets \
  --use-investoday-shards \
  --shard-size 80 \
  --start 20210101 \
  --end 20260724
```

对比当前候选池与历史股票池 run：

```bash
PYTHONPATH=src python3 examples/compare_universe_bias.py \
  --baseline-run-id <realtime_candidate_run_id> \
  --candidate-run-id <historical_stock_master_run_id>
```

流水线顺序：

- 诊断今日投资行情、benchmark、stock master、实时股票池。
- 若数据超过 5 天或当前窗口无数据，则 fail-fast，不生成交易候选。
- 缓存预热真实行情、涨跌停、财务、stock master、PIT 股票池和 benchmark。
- 运行主策略。
- 运行配置化 batch variants。
- 更新 run registry、health status 和 pipeline summary。
- 若选出 `paper_candidate`，进入 Paper Control 风控门控并生成待审批订单；人工审批/执行后才写入模拟成交、持仓和账户账本。

生产资产导入前的 daily pipeline 验证留档：

```text
Pipeline: daily_20260724_132221_761
Diagnosis: fresh latest_quote_date=2026-07-23 freshness_days=1
Health: ok
Main run: cli_20260724_132226_331 research_only (3 failed), score 76.63 strong_watch
Best batch: cli_20260724_132229_717 research_only (1 failed), score 80.0 strong_watch
Selected paper candidate: none
Bias diagnostics: warn, score 92.0, 0 hard failures, current candidate-pool caveat only
Universe source: realtime_candidate_pit_liquidity
Data trust: real_data_candidate_pool, not canonical production asset
Paper control: paper_20260724_132233_890 fail, no_selected_candidate
Allowed to trade: False
Ready for review: False
```

`allowed_to_trade=true` 只在本轮 Paper Control 已经通过审批并完成模拟执行时出现；`ready_for_review=true` 表示有通过风控的待审批订单。两者都不代表实盘自动下单。

## Production Ops

Production Ops v1 是本地文件型运维闭环：调度器记录、通知中心、人工 ack 和 `/ops` 状态页。它不依赖外部通知渠道，先保证每天值守时有统一入口和可追溯记录。

Scheduler dry-run：

```bash
PYTHONPATH=src python3 examples/schedule_daily_pipeline.py \
  --config configs/daily_pipeline.yaml \
  --force
```

固定时间门控，适合配合 cron/launchd 高频调用：

```bash
PYTHONPATH=src python3 examples/schedule_daily_pipeline.py \
  --config configs/daily_pipeline.yaml \
  --at 09:35 \
  --execute
```

确认通知：

```bash
PYTHONPATH=src python3 examples/ack_notification.py <notification_id> \
  --actor operator \
  --reason reviewed
```

主要输出：

- `reports/scheduler/runs.jsonl`: append-only scheduler run log。
- `reports/scheduler/runs.csv`: scheduler run 当前表。
- `reports/notifications/notifications.jsonl`: append-only notification 状态日志。
- `reports/notifications/notifications.csv`: notification 当前表，包含 `open/acked`。
- `reports/ops/ops_snapshot.json`: `/ops` 使用的最新运维快照。

最新验证：

```text
Scheduler dry-run: scheduler_20260724_101520_200140, status=dry_run, notifications=2
Fixed-time gate: scheduler_20260724_101803_478057, status=skipped_before_scheduled_time
CLI ack: notif_20260724_101520_201492 -> acked
Web scheduler POST: dry_run passed
Web ack POST: acked passed
Smoke: /ops, scheduler CSV, notifications CSV, ops snapshot passed
```

接 Tushare：

```bash
python3 -m pip install -r requirements-data.txt
export TUSHARE_TOKEN="your_token"
PYTHONPATH=src python3 examples/run_real_data.py \
  --source tushare \
  --symbols 600000.SH,000001.SZ,600519.SH,000858.SZ,600036.SH \
  --start 20210101 \
  --end 20251231
```

输出：

```text
a_share_quant_agent_mvp/reports/real_data_strategy_spec.json
a_share_quant_agent_mvp/reports/real_data_report.md
a_share_quant_agent_mvp/reports/real_data_artifacts/
a_share_quant_agent_mvp/reports/run_registry.jsonl
a_share_quant_agent_mvp/reports/run_registry.csv
a_share_quant_agent_mvp/reports/job_queue.jsonl
a_share_quant_agent_mvp/reports/job_queue.csv
a_share_quant_agent_mvp/reports/health_status.json
a_share_quant_agent_mvp/reports/cache_warmups/<warmup_id>/
a_share_quant_agent_mvp/reports/data_freshness_diagnosis/<diagnosis_id>/
a_share_quant_agent_mvp/reports/daily_pipeline/<pipeline_id>/
a_share_quant_agent_mvp/reports/cli_runs/<run_id>/
a_share_quant_agent_mvp/reports/paper/
a_share_quant_agent_mvp/reports/paper/
```

注意：

- 最新 AKShare 版本需要 Python 3.10+；macOS 自带 Python 3.9 可能导入失败。推荐用 Python 3.10/3.11/3.12 单独建 venv。
- 外部真实数据请求依赖网络、代理和上游数据站点状态；失败时脚本会输出 `Data source error`。
- 今日投资 adapter 接 `stock/adjusted-quotes` 前复权日行情，当前是 MVP 推荐真实数据源。
- 今日投资 adapter 默认启用本地 JSON 响应缓存；缓存目录已加入 `.gitignore`。
- 今日投资 adapter 默认额外接 `stock/limit-up-down`，回测买入涨停、卖出跌停时会按真实标记阻断成交；可用 `--no-limit-flags` 关闭。
- 今日投资 adapter 默认额外接 `stock/financial-indicators-profitab`，ROE 会按财报 `publishDate` 点时对齐；可用 `--no-financials` 关闭。
- 今日投资 adapter 默认额外接 `stock/basic-info`，把上市日期、退市日期、上市状态、股票类别、板块和股本等股票主数据合入面板，并生成 `is_stock_master_member` 点时过滤列；可用 `--no-stock-master` 关闭。
- 今日投资 `investoday_top_amount` 使用 `stock-quote/realtime-ext` 按当前成交额排序构建，属于当前日流动性股票池，不是无幸存者偏差的历史点时股票池。
- 今日投资 `investoday_pit_top_amount` 使用当前候选池内的历史行情生成每日 membership：按前一日可得的 20 日平均成交额排序，避免用未来成交额决定历史日期成员；但候选池仍来自当前可见市场，不等于完整无幸存者偏差数据库。
- `historical_stock_master_pit_top_amount` 支持外部完整历史 A 股 stock master CSV：用 `--historical-stock-master-path` 导入候选源，再按 `listDate/delistDate/stockType` 做 PIT 过滤和历史流动性 membership。只有 CSV 通过历史主表验收器、达到 `--historical-stock-master-min-rows`、包含退市样本、覆盖 SH/SZ 且未被 `candidate_size` 截断时，才会标记为 `full_historical_stock_master`。
- `examples/validate_historical_stock_master.py` 会校验标准字段、代码格式、重复代码、上市日期覆盖率、退市样本、交易所覆盖、A 股类型和指定区间 eligible symbols，并输出 `historical_stock_master_validation.json/md`。
- `--require-production-data` 是严肃历史研究硬门禁：未通过 production data trust 时直接失败，不会继续生成回测结果。
- `data_assets/` 是生产历史数据资产目录契约，包含 historical stock master、daily quotes、fundamental factors、index constituents、industry classification 的模板和落盘位置。
- `examples/materialize_investoday_data_assets.py` 可以把今日投资实时 Top Amount 候选池、基础资料、复权行情和行业标签落盘到 `data_assets/investoday_candidate/`，并生成 manifest、stock master validation、data trust 和 asset inventory。
- `data_assets/investoday_candidate/` 是真实候选池资产，不是生产 canonical 资产；它用于调试、演示和数据落盘验收，不会被系统冒充为完整历史 A 股数据库。
- `examples/check_full_universe_readiness.py` 会生成全市场数据包 readiness、今日投资接口联调结果、data-definition 和 acceptance-criteria；当前已确认 `stock/all` GET、`chain/sec-basic-info` 和 `stock/adjusted-quotes` 运行探针可用，且全量 quotes 与 canonical production 资产已完成正式导入，readiness 为 `production_ready`。
- `examples/extract_investoday_full_universe.py` 是今日投资全市场抽取器：优先 `stock/all` 自动拉 stock master，并用 `chain/sec-basic-info` 补充退市 A 股样本，支持 CSV/symbol seed 降级、复权日行情分批抽取、`--extract-id` 断点续跑、quote shard、quote progress、staging canonical 资产、generated mapping、stock-master-only 快速验收和生产导入 dry-run。
- `examples/vendor_data_onboarding.py` 会扫描供应商 CSV/Parquet 目录，自动识别 stock master、daily quotes、fundamental factors、index constituents、industry classification，推断字段 mapping，生成 data-definition/acceptance-criteria，并在 staging 目录 dry-run 生产验收。
- `examples/execute_production_import.py` 是生产导入执行器：先 dry-run 到 staging，只有 dry-run `production_data_ready=true` 才允许 `--execute` 写正式 `data_assets/`；正式导入前会备份 canonical 资产，并可在通过后触发 `run_strategy_factory.py --source production`。
- `examples/import_vendor_data_assets.py` 是供应商历史数据导入器，支持 CSV/Parquet 输入、字段 mapping、CSV 分块导入、可选 Parquet 副本、canonical production 资产落盘、全市场覆盖验收、fundamental factor 覆盖率摘要和 `data-definition.md` 字段口径报告。
- `examples/validate_production_data_assets.py` 可以单独验收当前 canonical production 资产，检查 stock master、eligible symbol 覆盖、日期覆盖、重复键、价格异常和成交额/成交量异常。
- `examples/run_strategy_factory.py` 会从 `configs/strategy_factory_templates.json` 读取策略模板库，批量运行回测、审计、walk-forward、Factor IC、归因、敏感性分析，并写入 `reports/strategy_factory/idea_registry.csv` 与 `latest_board.json/md`。
- 策略工厂的晋级规则不会只看收益；未通过 production data、bias、walk-forward、Factor IC、回撤、交易样本和 decision gate 的 idea 会停在 `testing`、`rejected` 或 `watch`，不会直接进入 paper candidate。
- `examples/run_production_historical_research.py` 是生产历史研究入口：会先验收 stock master，再要求离线行情覆盖所有 eligible symbols；若显式开启 `--use-investoday-shards`，会按 shard 拉取并写入 `shard_manifest.json/md`。
- 生产历史研究会输出 `data_asset_inventory.json/md`、`data_trust.json/md`、`historical_stock_master_validation.json/md`、`regime_stability.json/md`，用于复核资产、数据可信、幸存者偏差和长周期稳健性。
- 当前 stock master 过滤能显式剔除未上市/已摘牌/非 A 股日期；若没有完整历史 stock master CSV，系统会继续保留 candidate-pool caveat，不会假装无幸存者偏差。
- 默认用今日投资 `index/quotes` 拉取沪深300 `000300` 做基准，报告输出超额收益、跟踪误差、信息比率和相关性；可用 `--benchmark-code` 改指数代码，传空字符串可关闭。
- 默认输出 `walk_forward.csv`，用 6 个月训练窗口、3 个月验证窗口、3 个月步长做固定规则样本外验证；可用 `--skip-walk-forward` 关闭，或用 `--walk-forward-*` 参数调整。
- 今日投资自动股票池会把 `industryLV1Name`、`industryName` 等行业分类透传到行情面板，默认输出 `industry_exposure_daily.csv`、`industry_exposure_latest.csv`、`industry_exposure_metrics.json`；可用 `--skip-industry-exposure` 关闭。
- 默认输出 `factor_ic.csv`、`factor_ic_summary.csv`、`factor_ic_metrics.json`，在调仓日计算因子值对未来 5/20/60 个交易日收益的横截面 IC；可用 `--skip-factor-ic` 关闭，或用 `--factor-ic-horizons` 调整。
- 默认输出 `style_exposure.csv`、`stock_contribution.csv`、`industry_contribution.csv`、`bias_diagnostics.json`、`attribution_summary.json`，用于解释收益来源、风格暴露和真实数据/PIT/披露日/执行字段偏差；可用 `--skip-attribution` 关闭。
- 当前 2024 年样本中最佳 IC 为 `roe` 的 5 日前瞻收益，mean IC 约 0.058，但 t-stat 不足 1.5，属于 `positive_but_noisy`，不能作为稳定 alpha 证据。
- 每次 CLI/Web 运行都会写入 `reports/run_registry.jsonl` 和 `reports/run_registry.csv`，并记录数据哈希、报告路径、归档 artifacts、benchmark、walk-forward、行业暴露、Factor IC、归因/偏差诊断与 decision gate 状态。
- 每条 registry 会输出保守 `research_score`、`research_band` 和分项得分。评分奖励收益/回撤/IR、walk-forward、Factor IC、交易样本、行业分散、数据质量、偏差诊断和 gate 通过情况；`abandon` 和未过 gate 的结果会被封顶，避免单次漂亮收益压过稳健性证据。
- 每条 registry 会输出 `data_quality_status`、`latest_data_date`、`freshness_days`、`universe_source`、缺失字段数量、空值率和重复键数量，用于识别样本数据、陈旧真实数据、字段缺失和候选池来源。
- 每条 registry 也会输出 `data_trust_level`、`production_data_ready`、`data_source_kind`、`stock_master_validation_status`、`data_trust_hard_failed` 和 caveats；每次 CLI/Web run 的 artifacts 会包含 `data_trust.json/md`。
- Web 默认把研究运行提交到后台队列，状态写入 `reports/job_queue.jsonl` 和 `reports/job_queue.csv`；队列当前用单 worker 串行执行，避免并发压垮真实数据接口。
- 后台队列记录 `attempt`、`max_retries`、`retry_count` 和 `attempts`；明显网络、超时、连接、限流类错误会最多重试 2 次，策略逻辑错误或字段缺失不会盲目重试。
- 当前队列是本地进程内队列，服务重启不会恢复正在运行的 job；启动时会把旧的 `queued/running/retrying` job 标记为 `interrupted`。
- `/batch` 支持批量实验，默认展开持仓数、滑点、成交额阈值和调仓频率组合，每个 variant 都会生成独立 run registry 记录。
- `/warmup` 会拉取今日投资行情、可选涨跌停/财务/stock master/PIT universe/benchmark 数据并写入 `reports/cache_warmups/<warmup_id>/metadata.json`，用于先预热真实数据再跑研究。
- `/health` 会写入 `reports/health_status.json`，统一输出 health state、最新真实数据新鲜度、失败/中断 job、最新 warmup 和建议动作。当前今日投资日频数据 freshness policy 为 5 天。
- `examples/diagnose_investoday_freshness.py` 会用当前窗口和历史基线窗口定位数据新鲜度问题，区分“当前窗口无数据”“缓存可能陈旧”“接口错误”和“数据新鲜”。
- `examples/run_daily_pipeline.py` 使用 `configs/daily_pipeline.yaml` 做日跑流水线，支持 fail-fast、warmup、主 run、batch variants、重试、summary、健康门控更新和 Paper Control 风控/待审批生成。
- `regime_stability` 会按年份、策略自身波动区间和可选 benchmark 趋势区间拆解表现；少于 5 年会标记 `short_history`，不把短样本误当稳健证据。
- `decision_gate` 是研究准入门槛，不是投资建议：只有真实数据、PIT 股票池、股票主数据、production data trust、基准、walk-forward、Factor IC、偏差诊断、回撤、交易样本和审计全部过关，才会标记为 `paper_candidate`；否则保留为 `research_only`。
- Paper Control 风控门控也检查 `production_data_ready`，避免旧 registry 或人工拼接候选绕过数据可信门。
- `examples/compare_universe_bias.py` 可以对比两个 run 的 universe source、bias score、收益、回撤、IR、风格和贡献变化，用于检验 historical universe 是否改变策略结论。
- 重型今日投资 enrichment 接口默认按 20 只股票分批请求；可用 `--api-batch-size` 调整。
- 默认输出 `sensitivity.csv`，覆盖持仓数量、滑点、成交额过滤和调仓频率变体；可用 `--skip-sensitivity` 关闭。
- AKShare adapter 当前只接 `stock_zh_a_hist` 的 OHLCV 数据，适合动量、波动率、成交额这类技术因子。
- Tushare adapter 接 `daily`，并在权限允许时合并 `daily_basic` 的 PE、PB、股息率。
- 真实财务因子必须按披露日对齐，不能按报告期直接前填；当前今日投资 ROE 已按 `publishDate` 合并。
- MVP v0 的涨跌停约束先用简化 10% 规则，创业板/科创板/北交所/ST 的差异会放到后续交易规则模块。

数据源接口参考：

- 今日投资 `stock/adjusted-quotes`：本地 skill 文档 `investoday-finance-data/references/沪深京数据/股票行情/复权行情.md`
- 今日投资 `stock-quote/realtime-ext`：本地 skill 文档 `investoday-finance-data/references/沪深京数据/股票行情/实时行情.md`
- 今日投资 `stock/basic-info`：本地 skill 文档 `investoday-finance-data/references/沪深京数据/基础信息/证券资料.md`
- 今日投资 `index/quotes`：本地 skill 文档 `investoday-finance-data/references/指数/基础行情.md`
- 今日投资 `stock/financial-indicators-profitab`：本地 skill 文档 `investoday-finance-data/references/沪深京数据/财务数据/财务当期指标数据.md`
- AKShare `stock_zh_a_hist` 文档：https://akshare.akfamily.xyz/data_tips.html
- Tushare `daily` 文档：https://tushare.pro/document/2?doc_id=27
- Tushare `daily_basic` 文档：https://tushare.pro/document/2?doc_id=32

## Project Structure

```text
a_share_quant_agent_mvp/
  examples/
    run_demo.py
    run_end_to_end_demo.py
    run_from_idea.py
    run_100_stock_real_backtest.py
    run_real_data.py
    run_production_historical_research.py
    materialize_investoday_data_assets.py
    check_full_universe_readiness.py
    extract_investoday_full_universe.py
    vendor_data_onboarding.py
    execute_production_import.py
    import_vendor_data_assets.py
    prepare_production_data.py
    run_strategy_factory.py
    run_daily_pipeline.py
    schedule_daily_pipeline.py
    ack_notification.py
    review_paper_orders.py
    validate_historical_stock_master.py
    validate_production_data_assets.py
    data_asset_inventory_smoke_test.py
    investoday_asset_manifest_smoke_test.py
    full_universe_readiness_smoke_test.py
    investoday_full_universe_extract_smoke_test.py
    vendor_data_onboarding_smoke_test.py
    production_import_executor_smoke_test.py
    vendor_asset_import_smoke_test.py
    production_data_readiness_smoke_test.py
    fundamental_factor_asset_smoke_test.py
    strategy_factory_smoke_test.py
    attribution_smoke_test.py
    data_trust_smoke_test.py
    historical_universe_smoke_test.py
    production_historical_research_smoke_test.py
    compare_universe_bias.py
    ops_smoke_test.py
    paper_control_smoke_test.py
    web_app.py
    strategy_specs/
      quality_value_momentum.json
  reports/
    production_data_readiness.json
    production_data_readiness.md
    full_universe_readiness/
      full_universe_readiness.json
      full_universe_readiness.md
      data-definition.md
      acceptance-criteria.md
      api-integration.md
    full_universe_extract/
      latest_extract.json
      latest_extract.md
      runs/
    vendor_onboarding/
      latest/
        vendor_onboarding.json
        vendor_onboarding.md
        vendor_mapping.suggested.yaml
        data-definition.md
        acceptance-criteria.md
    production_import_executor/
      latest_execution.json
      latest_execution.md
      runs/
    strategy_factory/
      idea_registry.csv
      latest_board.json
      latest_board.md
      runs/
  configs/
    daily_pipeline.yaml
    vendor_mapping.template.yaml
    strategy_factory_templates.json
  data_assets/
    README.md
    stock_master/
      historical_stock_master.csv
    market/
      daily_quotes.csv
    fundamentals/
      fundamental_factors.csv
    index/
      index_constituents.csv
    industry/
      industry_classification.csv
    templates/
      historical_stock_master.csv
      daily_quotes.csv
      fundamental_factors.csv
      index_constituents.csv
      industry_classification.csv
    investoday_candidate/
      stock_master.csv
      daily_quotes.csv
      realtime_universe.csv
      industry_classification.csv
    manifests/
      investoday_candidate/
        data_asset_manifest.json
        data_trust.json
        historical_stock_master_validation.json
      production_import/
        data_asset_manifest.json
        production_asset_validation.json
        data-definition.md
  src/a_share_quant_agent/
    audit.py
    backtest.py
    data_sources.py
    vendor_assets.py
    vendor_onboarding.py
    full_universe_readiness.py
    investoday_full_universe.py
    production_import_executor.py
    production_data_readiness.py
    strategy_factory.py
    nl_parser.py
    report.py
    regime.py
    sample_data.py
    spec.py
```

## MVP Philosophy

第一版不是要证明“AI 能赚钱”，而是证明：

> 一个 A 股策略想法可以被自动转成可复现代码，并被系统用严格假设审计。

策略被判定为 `abandon` 也是价值，因为它帮助用户更早发现未来函数、过拟合、成交假设过于乐观、样本不足等问题。
