# Stage-2 data capability and rights request

**Subject:** Outcome-blind data capability and rights confirmation for an A-share academic study

This is a provider-neutral request that may be sent to a data vendor, university
library, or licensed data administrator. Sender identity, affiliation, and
commercial details may be added when the request is transmitted; they are not
research-design inputs. The first response should contain documentation and
written yes/no answers only. Please do not send sample factor values, returns,
ICs, portfolio results, rankings, or strategy recommendations.

A provider or licensor may grant a new permission or contract addendum. A
university/library licence administrator may confirm only rights already
granted by the controlling agreement, unless that agreement expressly gives
the administrator authority to amend the licence. An administrator's letter
cannot create a publication or reviewer-access right absent from the contract.

## English request

We are preparing the outcome-blind feasibility stage of the study **“Report
Dates, Publication Dates, and the A-Share ROE Signal: A Pre-Specified Historical
Confirmation”** (`a-share-factor-timing-bias-decomposition-v2`). Before any
historical outcome analysis, we need written confirmation of data coverage,
field semantics, access limits, and permitted academic uses.

Please complete the accompanying
`provider_capability_and_field_mapping.template.xlsx` (first save a renamed
private completed copy outside Git) and
`provider_rights_confirmation_form.md`, and attach the applicable field
dictionary, licence/contract terms, and entitlement description. At this stage
we request no result-bearing sample rows.

### Required data

| Dataset role | Required interval | Minimum fields and semantics |
|---|---|---|
| Daily quotes | 2009-01-01 to 2023-01-31 | Stable SH/SZ A-share identifier and session date; `close_raw`, finite positive `adjustment_factor`, `close`, exact `price_adjustment_method=close_equals_close_raw_times_adjustment_factor`, exact `price_adjustment_convention=provider_cumulative_backward_adjusted_hfq_no_rebasing`, and `close_observation_type`. The canonical adapter uses the cumulative factor as delivered without rebasing and must satisfy `close=close_raw × adjustment_factor` within `1e-12` relative/absolute tolerances before hashing. Please supply separately hashable definitions for raw close/valuation, adjustment-factor convention, and the normalization or adapter record. Daily traded amount, provider-native unit/cutoff, conversion rule and provenance are also required; the delivered canonical file must contain `amount` already normalized to CNY and exact `amount_unit=CNY` on every row. Historical ST and suspension state are required. `close_observation_type` must be `traded_close` exactly when `is_suspended=false` and `suspension_valuation` exactly when `is_suspended=true`; each `close_raw` suspension valuation must be recorded or published by the supplier for that exact official session and cannot be a researcher-generated carry-forward. In every target month, every active-master security with a signal-session quote must have exact `t`, `t+1`, `t+20`, and `t+21` rows, with at least 1,000 complete-contract identifiers retained. These close-based returns and ICs are valuation diagnostics, not executable trade-return evidence. |
| Historical stock master | Complete lifecycle records for every security active at any time from 2009-01-01 through 2023-01-31 | Provider-stable identifier, actual listing date (including dates before 2009), delisting date, lifecycle status/effective date, and security type. Current and delisted Shanghai/Shenzhen A-shares must be retained; a latest-only stock list is insufficient. Please provide the identifier definition and complete historical code-change/reassignment map. A0 terminal survival is fixed at 2023-01-31: after listing by the historical signal session, `delistDate` must be null or strictly after that cutoff, independent of extraction date or current status. |
| Fundamentals | Publication records from 2009-01-01 to 2022-12-31 | Identifier, the provider's explicitly defined **diluted ROE** mapped one-to-one to canonical `roeDiluted`, fiscal report-period end, and the **actual recorded disclosure/publication date**. Another ROE concept and any planned, expected, appointment, or latest-update date are not substitutes. |
| Official calendars | 2009-01-01 to 2023-01-31 | Separate authoritative SSE and SZSE calendar dates with explicit open/closed states. The study forms the common-session intersection only when both exchanges explicitly report open. |

Please identify the exact product, table/API, provider field, coverage start/end,
missing-value codes, units, corporate-action treatment, effective-date logic,
time zone/cutoff, per-call limits, daily quota, bulk-export route, delivery time,
fees, and contract term for every required item.

The same provider-stable security identity must govern quotes, stock master, and
fundamentals under the fixed contract token
`provider_stable_exchange_qualified_security_identifier_with_reviewed_code_change_mapping_v1`.
Exact exchange-qualified code formatting is insufficient by itself. Please
provide separately hashable evidence for the identifier definition and every
historical code change or code reassignment. This request does not ask for a
revision or vintage history of financial values.

### Required written permissions

Please state **Yes**, **No**, or **Conditional** and cite the controlling clause
for each of the following:

1. encrypted local storage and non-commercial academic analysis;
2. publication of aggregate estimates, tables, and figures;
3. publication of aggregate coverage, missingness, and endpoint-reason counts;
4. publication of cryptographic file/evidence hashes;
5. publication of exact official common-session dates;
6. controlled reviewer/editor reruns through provider-issued reviewer access or
   a contract-covered licensed environment;
7. private retention and hash binding of a per-security endpoint-reason ledger;
8. whether the manuscript or public supplement may name the provider, product,
   and source table (a Yes answer is required for every delivered dataset
   because provider-supplied strings enter the fixed public declaration
   projection; No blocks Stage 2 under the current design);
9. whether the manuscript or public supplement may cite or reproduce the field
   dictionary/mapping (a Yes answer is required for every delivered dataset
   because the fixed public Stage-2 receipt contains the exact declaration
   mapping; No blocks Stage 2 under the current design);
10. confirmation that raw licensed rows will not be made public or transferred
   to an unauthorized person; a reviewer may access them only through
   provider-issued permission or a contract-covered controlled environment;
   credentials will never be shared.

The response must identify the contract/version, effective and expiry dates,
restrictions, and an authorized person or verifiable provider record. Every
Conditional response must identify the exact condition and evidence by which
an authorized reviewer can determine that it has been satisfied. Assign each
distinct restriction a unique ID; multiple restrictions on one permission
must retain separate IDs. The private attestation maps every restriction
one-to-one to a review carrying the same restriction ID and exact permission
field, a satisfied flag, review timestamp, and evidence hash. Missing,
duplicate, unknown, or permission-mismatched mappings fail closed, and the
mapped permission must be `true`. For a finite term, execution must occur while
the contract is active and a separate clause
must preserve publication of the completed research and controlled reviewer
access after expiry. The runner rechecks expiry at exclusive authorization
consumption, before outcome preparation, at each monthly execution boundary,
and before receipt publication; expiry fails closed without a receipt.
Post-expiry publication/review survival does not authorize a new analysis run.
A generic statement that data are “available” does not establish these rights.

### Delivery boundary

No raw data should be emailed or uploaded to the public repository. After
capability and rights are accepted, the provider or licensed administrator may
deliver the contracted files through a private encrypted channel to the named
data custodian; the custodian records the closed hash manifest. The research
team will first run only fixed structural/numeric integrity and coverage checks.
Those validators may parse raw numeric fields but may not compute, retain,
release, or human-display factor returns, signal ranks, ICs, portfolios, test
statistics, or variant rankings. Registered analysis access remains sealed until
external registration and a separate custodian execution authorization.

## 中文询权函

我们正在为研究 **《报告期日期、实际披露日期与 A 股 ROE 信号：一项预先设定的历史确认》**
（研究编号 `a-share-factor-timing-bias-decomposition-v2`）进行不查看结果的
数据可行性审查。在任何历史收益或因子结果分析之前，需要贵方书面确认数据覆盖、
字段语义、访问限制和学术使用权。

烦请先在 Git 仓库外另存并重命名
`provider_capability_and_field_mapping.template.xlsx` 的完成件，并逐项填写
`provider_rights_confirmation_form.md`，将两者一并返回，同时提供适用的字段字典、
许可或合同条款、账号权限说明。第一轮仅需返回文档和书面回答，请勿发送因子值、
收益、IC、组合结果、
策略排名或其他可能影响研究设计的结果样本。

所需数据包括：2009 年行情 warm-up、2010—2022 年研究样本以及延伸至
2023 年 1 月的收益端点；历史上市和退市证券（A0 的终点存续截止日固定为 2023-01-31，而不是提取日状态）；实际财报披露日期；历史 ST、停牌、
成交额；逐行 `close_observation_type`（非停牌=`traded_close`，停牌=供应商在同一官方交易日记录或发布的 `suspension_valuation`，不得由研究代码前向填充）；分别来源于 SSE 和 SZSE 的官方开闭市日历。每月全部“历史有效证券主表 ∩ 信号日行情”候选都必须具备精确 `t/t+1/t+20/t+21` 端点，且仍至少有 1,000 个完整合约标识符。由这些收盘观察计算的是估值收益和 rank IC，不是可执行成交收益。详细字段和语义见上表及随附
工作簿。行情、主表和财务数据还必须采用同一供应商稳定标识语义，并提供历史代码变更或重分配映射；仅满足 `NNNNNN.SH/SZ` 格式不足以证明同一证券身份。

请逐项书面确认是否允许：加密本地存储和非商业学术分析、发表汇总统计/表格/图形、
发表覆盖率/缺失率/汇总原因计数、发表文件哈希、发表准确的共同交易日期、在持牌环境
中通过供应商单独授权或合同覆盖的受控方式供审稿人复跑、私有保存并哈希绑定逐证券
端点原因账本。还请分别确认供应商身份公开权和字段映射引用权：两者对每个必需数据集
都必须回答 Yes，因为供应商填写的字符串会进入固定的公开 Stage-2 数据声明投影，
任一回答 No 都会在当前设计下阻止 Stage 2。同时明确原始
授权数据行不得公开或转交未获授权人员，账号凭证在任何情况下均不得共享。供应商/
许可人可以新增授权；学校或图书馆管理员只能确认合同已
存在的权利，除非合同明确授予其修改许可的权限。请注明合同编号/版本、有效期、限制及
有权确认人员。

能力和权利通过前不传输原始数据；通过后也只采用私有加密交付。外部注册和单独的
execution authorization 完成前，因子、收益、IC、组合和变体排名保持封存。

## Response package

Return these items through an approved private or institutional channel:

- completed provider capability workbook;
- signed rights confirmation or an equivalent provider letter;
- field dictionary and product documentation;
- applicable licence/contract extract and entitlement evidence;
- proposed secure delivery method, quotation, lead time, and contract term.

Do not include account credentials or raw data in the response package.
