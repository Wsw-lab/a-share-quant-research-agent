---
title: "How Much Do Information Timing and Implementation Choices Shift A-Share Factor Evidence?"
subtitle: "A Pre-Specified Specification-Effect Decomposition"
document_status: "Anonymous Stage-1 manuscript draft — not registered; confirmatory outcomes not accessed"
date: "1 September 2026"
keywords: "A-shares; point-in-time information; publication timing; survivorship bias; factor replication; pre-registration"
jel: "G12; G14; C12"
---

# Abstract

Empirical factor evidence can shift when a backtest changes what securities existed, when an accounting report was recorded as published, and whether a signal could be implemented under contemporaneous market conditions. We propose a historical confirmation designed to remain outcome-blind only if its custody and prior-exposure gates pass. It measures these specification effects in Shanghai and Shenzhen A-shares rather than searching for a new anomaly. The aggregate results and known limitations of an 18-month observed pilot are publicly disclosed: moving from report-period to recorded report-publication-date alignment reduced mean return-on-equity (ROE) rank information coefficient from 0.0461 to 0.0105 and the fixed composite from 0.0332 to 0.0038. The pilot was observed before this manuscript, was not externally preregistered, and is not confirmatory evidence. The proposed study fixes a 2009 warm-up, a 2010–2022 historical panel with 156 monthly rebalances, four factors, and 18 variants. Two ordered information-set contrasts are followed by the complete factorial of four implementation controls, yielding 72 factor–variant cells. Confirmatory inference is restricted to one pilot-informed primary ROE timing contrast, a fixed 25-member secondary family with Benjamini–Hochberg adjustment, and two deterministic isolation checks. Exact monthly Shapley values conditionally allocate the implementation block without selecting a preferred ordering. Every pre-specified cell will be reported, including null and sign-reversing outcomes. Historical data access, official-calendar identity, field semantics, publication rights, external registration, and execution authorization remain hard gates. No confirmatory analysis has been run, and no performance, trading-readiness, generalization, or revision-history claim is made.

**Keywords:** A-shares; point-in-time information; publication timing; survivorship bias; factor replication; pre-registration
**JEL classifications:** G12; G14; C12

> **Manuscript status.** This is an anonymous pre-results Stage-1 manuscript. The 2023–2026 pilot has been observed; its aggregate results and known limitations are publicly disclosed. The proposed 2010–2022 historical confirmation is blocked for data feasibility, has not been externally registered or authorized, and has not been executed.

# 1. Introduction

Empirical asset-pricing results depend not only on a signal but also on the historical information set and the clock used to translate that signal into a return. A backtest can be mechanically reproducible and still be economically misleading if it admits only terminal survivors, makes a financial statement available at fiscal period end, uses a security on a day when it was suspended, or measures a return from the same close at which a signal was formed. These conventions are often changed as a bundle. When the reported result moves, the reader cannot tell whether the change came from membership, information timing, eligibility, liquidity, or implementation delay.

This problem is especially consequential in China’s A-share market. China-specific factor construction matters because listing institutions, small-stock behavior, trading suspensions, Special Treatment designations, and accounting-data availability differ from the conventions embedded in many developed-market research pipelines. Liu, Stambaugh, and Yuan (2019) show that simply transplanting standard U.S. size and value definitions does not yield the most informative Chinese factor model. More recently, Gharghori and Nguyen (2025, 2026) provide a direct pre-registered comparison of prominent factor models for China. The open question pursued here is different. We do not ask which model wins. We ask how much familiar factor evidence moves when a fixed set of information and implementation conventions is changed one at a time or within a complete factorial block.

The question is also a response to a broader credibility problem in empirical finance. Data reuse, broad specification menus, and publication incentives make the best-looking result an unreliable scientific object (White, 2000; Harvey, Liu, and Zhu, 2016). Standardized replications show that many anomalies weaken under common construction and inference choices (Hou, Xue, and Zhang, 2020), while implementation costs can change the economics of apparently attractive signals (Novy-Marx and Velikov, 2016). A public code repository does not by itself solve these problems. Code can verify that a declared procedure ran; it cannot establish that the procedure, sample, and headline statistic were selected before the outcomes were known.

We therefore frame the study as a pre-specified specification-effect decomposition. The design contains an ordered information-set chain and a complete implementation block. The first contrast replaces a final-survivor universe with historical listing membership while holding the optimistic report-period clock fixed. The second contrast retains historical membership and moves ROE eligibility from fiscal period end to the recorded report publication date in a single-version export. Starting from that recorded-publication baseline, the study crosses four binary components: exclusion of ST securities, exclusion of suspended securities, a 20-session CNY 5 million amount floor, and a one-official-session return lag. All 16 component subsets are evaluated. Exact Shapley values conditionally allocate the full implementation effect among those four components while distributing interactions; no causal interpretation or analogous order-invariance is claimed for the preceding membership and publication transitions.

The design is motivated by an observed pilot, and that prior exposure is central rather than incidental. The repository’s pilot reports four familiar signals—ROE, 60-session momentum, 20-session low volatility, and a fixed 50/30/20 composite—across four cumulative variants and 18 monthly cross-sections from January 2025 through June 2026. Recorded publication-date alignment substantially reduced the pilot ROE and composite ICs. Those results were already known when the present question and directional prediction were written. The four signals, composite weights, ST and suspension controls, CNY 5 million floor, one-session lag, and Newey–West lag three also existed in the pilot or repository before this plan. The broader repository contains other strategy variants, and durable records do not establish every prior execution or outcome exposure. The 25-member Stage-2 multiplicity family therefore does not erase earlier exploration. What this design newly adds is the complete 2^4 implementation lattice and its conditional Shapley decomposition. The aggregate pilot evidence and known limitations are consequently disclosed as an empirical precondition, not relabeled as prospective or independent out-of-sample confirmation. The intended editorial inquiry asks whether that transparent precondition can support the hybrid pre-registration pathway described by Faff (2026); this manuscript does not presume that the journal has accepted the route.

The proposed confirmatory panel is historically earlier and is intended to remain outcome-blind to the research team under the required custody and prior-exposure attestation: January 2010 through December 2022, preceded by a 2009 warm-up. Calling that panel “prospective data” would be incorrect because the calendar outcomes already exist. We instead call it an outcome-blind historical confirmatory panel, conditional on those gates. A genuinely prospective extension of at least 12 months would begin only after external registration or journal in-principle acceptance and would be reported separately. The observed pilot, historical confirmation, and prospective extension will never be silently pooled.

The paper offers three contributions. First, it estimates paired specification effects rather than adding another factor to the anomaly zoo. The sole primary estimand is the monthly ROE IC difference induced by moving from report-period eligibility to recorded report-publication-date alignment within the same historical listing universe. Second, it replaces a bundled implementation stress test with a complete 2^4 design and conditional exact monthly Shapley allocation. Third, it makes research governance part of the estimand contract: all 72 pre-specified cells, one primary, the fixed 25-member secondary family, and two deterministic checks must be reported; data and rights gates must pass before outcome release; and null, mixed, negative, and sign-reversing results remain reportable under the protocol.

The contribution is deliberately bounded. Recorded report-publication dates prevent a record from entering before the date stored in a single-version export, but they do not prove the value visible to investors at that time or reconstruct historical revisions. Rank IC and top-quintile-minus-universe contrasts are research measurements, not investable portfolios. The current executable core does not implement next-open portfolios, transaction costs, turnover, nonfills, formal interaction tests, or a complete per-security exclusion audit. The code repository is publicly visible but currently has no software license and is not described as open source. These exclusions narrow the claim, but they make the remaining question testable.

The remainder of the paper develops the related literature and mechanisms, discloses the complete pilot, defines the sample partitions and gates, fixes the hypotheses and variant architecture, specifies inference and reporting, and gives an outcome-contingent interpretation matrix that is valid before results are known.

# 2. Related literature and conceptual framework

## 2.1 A-share factors and market-specific construction

The study uses familiar characteristics so that the object being measured is the research design rather than the novelty of a signal. Profitability, momentum, and low-volatility effects have long histories in empirical asset pricing (Jegadeesh and Titman, 1993; Ang et al., 2006; Novy-Marx, 2013). Their presence in this study does not imply that the short-window definitions used by the repository reproduce the canonical academic portfolios. ROE is a vendor-supplied profitability measure, momentum is a 60-session price change, low volatility is the negative standard deviation of 20 daily adjusted returns, and the composite fixes their cross-sectional rank weights at 0.50, 0.30, and 0.20.

China-specific evidence cautions against treating imported conventions as neutral. Liu, Stambaugh, and Yuan (2019) construct factors around institutional features of the Chinese market, including the unusual behavior of very small firms and filters for short listing histories and sparse trading. They also align annual accounting inputs to public announcement dates. Li et al. (2024) replicate 469 anomaly variables in A-shares, use announcement dates or pre-set lags for accounting availability, and show that breakpoint and weighting conventions can strongly affect apparent replication. Publication-date alignment is therefore not novel by itself. Gharghori and Nguyen (2025) subsequently pre-specified a comparison between the Liu–Stambaugh–Yuan and Fama–French model families; their completed study implements that comparison and transparently reports modifications to the registered design (Gharghori and Nguyen, 2026). Our incremental contribution is not a claim of first China-specific construction, first use of announcement timing, or first preregistration. It is pre-specified paired measurement and conditional attribution of specification effects within a fixed factor set.

## 2.2 Historical information sets and implementation choices

Survivorship bias arises when failed or delisted securities are absent from the historical opportunity set. Brown et al. (1992) show that conditioning a performance study on survival can alter its inferences, and Shumway (1997) documents the related importance of omitted delisting returns. In a cross-sectional equity study, the direction of the membership effect need not be mechanically negative: it depends on which firms disappear, when they disappear, and how the signal and return are associated. For that reason, the historical-membership contrast in this paper has no directional primary hypothesis. It is measured rather than assumed.

Accounting availability creates a separate look-ahead channel. Fiscal period end describes the economic period to which a report relates, not the date on which an investor could observe it. Making ROE eligible at period end can insert a future disclosure into an earlier signal. Conservative fixed lags reduce that risk but mix actual reporting delay with an arbitrary convention. A recorded publication date permits a more direct report-publication-timing comparison, subject to two important qualifications: a date-only field may not reveal whether publication preceded the market decision cutoff, and a single-version export cannot identify the numerical value visible at that date or later corrections. The confirmatory rule therefore requires `publishDate < signal date`; same-day values are excluded. The resulting contrast measures recorded publication-timing displacement, not complete value-level point-in-time availability or revision history.

Tradability and return timing constitute a third layer. ST designations, suspensions, low turnover amount, and contemporaneous signal-to-return clocks can determine whether an apparent association corresponds to a feasible decision set. Novy-Marx and Velikov (2016) show more generally that implementation costs reshape anomaly economics. The current study stops short of a costed portfolio. It asks the narrower measurement question: how do four clearly defined implementation controls change monthly cross-sectional IC? Their complete factorial is used because an ordered ablation can make attribution depend on the sequence in which components are added.

## 2.3 Specification search, multiplicity, and pre-registration

The danger of specification search is not eliminated by reporting a conventional t-statistic. Lo and MacKinlay (1990) and White (2000) show how using the data to shape a test can produce misleading inference. Harvey, Liu, and Zhu (2016) argue that the scale of the factor literature requires higher evidentiary hurdles, and Hou, Xue, and Zhang (2020) show how standardized construction and multiple-testing concerns sharply reduce replication rates. These arguments support two design choices here: no best cell is selected within the proposed lattice, and the confirmatory family is enumerated before historical outcomes are released. This constraint governs the pre-specified design; it is not a claim that earlier exploration or all researcher degrees of freedom outside the lattice have disappeared.

The Pacific-Basin Finance Journal’s pre-registration initiative offers a journal-facing mechanism for making this separation credible. Faff (2023) describes a phased process in which the importance of a question and the strength of a method can be evaluated before results. Faff (2026) introduces a hybrid path for cases that require a transparently verified empirical precondition before downstream hypotheses can be fixed. The present study fits that possibility only conditionally: the pilot’s aggregate results and known limitations are public, but editor confirmation is required before any claim that the hybrid route has been accepted. The paired Stage-1/Stage-2 articles of Gharghori and Nguyen (2025, 2026) demonstrate that pre-results and post-results papers can remain distinct. In this manuscript, “Stage 1” refers to the journal’s pre-results review stage. The repository directory label `v2` is only an implementation version and is not a claim that journal Stage-2 review has begun.

## 2.4 Mechanisms and the pilot-informed hypothesis

The primary mechanism is straightforward. Suppose a positive ROE signal is measured using a fiscal-period convention. Some observations enter the monthly cross-section before their reports are recorded as published. Replacing that convention with recorded report-publication-date alignment in a single-version export removes those observations or substitutes an older report. If the optimistic clock inflated the association, the expected paired monthly difference `IC(publication) − IC(report end)` should be negative. This direction is not theory-only: it was chosen after observing the pilot. The honest scientific claim is therefore a pilot-informed directional prediction evaluated on a historically earlier panel that may be called outcome-blind only if the custody and final prior-exposure gates pass.

Alternative outcomes remain informative. An interval containing zero would fail to establish a nonzero mean timing effect; its width, rather than non-rejection alone, determines how precise that conclusion is. A positive difference would reject the directional expectation and show that the optimistic convention did not generate the anticipated inflation. Descriptive differences across implementation components can reveal which research conventions move the measurement, but they are not formal heterogeneity tests and cannot by themselves establish an economic trading mechanism. These result branches are fixed in Section 9 before confirmatory access.

# 3. Disclosed pilot evidence

## 3.1 Evidence role and sample

The observed pilot is the repository’s `pit-factor-replication-v1` study. It uses a licensed Investoday local research export whose market file spans 3 January 2023 through 24 July 2026, with 3,894,242 rows and 4,735 symbols. The file is licensed for local research and is not redistributed. The receipt labels 2023–2024 as the training interval and evaluates 18 first-session monthly cross-sections from January 2025 through June 2026 with a 20-session forward horizon. Four factors and four cumulative variants yield 16 cells, all of which are reported; the receipt states that no best result was selected.

The pilot’s status code contains the phrase `REAL_MARKET_OOS_STATISTICS`, but that repository label does not make the evidence prospectively confirmatory. The receipt’s plan was locked on 31 August 2026, after both the test interval and the market-file endpoint, and no external timestamp preceded outcome access. The pilot is consequently described here only as an observed, repository-bound empirical precondition. Its performance, generalization, and trading-decision flags are false.

## 3.2 Complete observed matrix

**Table 1. Complete observed pilot matrix**

| Variant | Factor | Mean IC | NW t | Top minus universe | Mean N |
|---|---|---:|---:|---:|---:|
| M0 naive | ROE | 0.0435 | 2.45 | 0.562% | 4,533 |
| M0 naive | Momentum 60d | -0.0514 | -1.68 | 0.765% | 4,516 |
| M0 naive | Low volatility 20d | 0.0529 | 1.86 | -1.038% | 4,527 |
| M0 naive | Composite | 0.0302 | 1.38 | 0.502% | 4,516 |
| M1 PIT universe | ROE | 0.0461 | 2.63 | 0.593% | 4,554 |
| M1 PIT universe | Momentum 60d | -0.0495 | -1.62 | 0.784% | 4,538 |
| M1 PIT universe | Low volatility 20d | 0.0550 | 1.94 | -0.993% | 4,549 |
| M1 PIT universe | Composite | 0.0332 | 1.53 | 0.539% | 4,538 |
| M2 PIT publication | ROE | 0.0105 | 0.61 | -0.111% | 4,554 |
| M2 PIT publication | Momentum 60d | -0.0495 | -1.62 | 0.784% | 4,538 |
| M2 PIT publication | Low volatility 20d | 0.0550 | 1.94 | -0.993% | 4,549 |
| M2 PIT publication | Composite | 0.0038 | 0.18 | -0.007% | 4,538 |
| M3 bundled implementation | ROE | -0.0108 | -0.47 | -0.393% | 4,339 |
| M3 bundled implementation | Momentum 60d | -0.0446 | -1.86 | 0.864% | 4,328 |
| M3 bundled implementation | Low volatility 20d | 0.0291 | 0.91 | -1.417% | 4,339 |
| M3 bundled implementation | Composite | -0.0194 | -0.76 | -0.340% | 4,328 |

*Notes.* Each row averages 18 monthly cross-sections. “NW t” is a Newey–West statistic produced by the code-bound pilot implementation with lag three; the pilot plan did not separately preregister that lag, and no multiplicity adjustment was applied. “Top minus universe” is the equal-weight return of the top signal quintile minus the equal-weight universe mean over the 20-session measurement window. It is not self-financing and is not a portfolio return.

The cleanest pilot transition is M1 to M2 because it changes accounting availability while leaving the point-in-time universe and price-only signals unchanged. ROE mean IC falls by 0.0356, from 0.0461 to 0.0105, and the composite falls by 0.0294, from 0.0332 to 0.0038. Expressed only as descriptive ratios, these shifts are 77.2% and 88.5% of their positive M1 comparators. Momentum and low-volatility values are identical between M1 and M2, as expected because their signals do not use publication-dated accounting data. Under M3, which bundles eligibility filters and a one-session lag, ROE and composite means become negative. No component-specific causal interpretation is possible from that cumulative transition.

The matrix also shows why a favorable cell is not an adequate research conclusion. Momentum has negative mean rank IC but positive top-quintile-minus-universe spread in every variant; low volatility shows the opposite sign combination. A full-rank association and an extreme-bin contrast weight the cross-section differently. The study therefore carries both as descriptive outputs and does not relabel a factor according to whichever statistic looks more attractive.

## 3.3 Why the confirmatory contract is stricter

The confirmatory design is continuous with the pilot’s question but is not an exact replay. First, the pilot accepts a fundamental record when `publishDate` is on or before the signal day, whereas the new date-only rule requires publication strictly before the signal date. Second, the pilot derives rebalances and horizons from observed quote dates; the confirmatory study requires a hash-bound common SSE/SZSE official session calendar. Third, the pilot reads a normalized `roe` field without an 18-month staleness rule, while the confirmatory study requires the provider’s raw `roeDiluted` definition, decimal normalization, and an 18-month limit. Fourth, the pilot variant identifier `M3_audited_lag` is a machine label, not evidence that execution semantics were independently attested: the current gap review lacks the required attestation and finds no positive suspension flags. We therefore call M3 the bundled implementation variant and do not attribute its change to suspension.

These differences are not retroactive repairs to pilot results. Table 1 remains frozen as observed. They are prospective restrictions on the separate historical confirmatory design. The pilot supplies prior evidence and design input; it contributes no pilot factor-cell or rebalance estimate to the primary or secondary confirmatory estimates.

[[FIGURE:EVIDENCE_CHRONOLOGY]]

*Figure 1. Evidence chronology and inferential separation.* The historical panel is earlier in calendar time and can be treated as outcome-blind only if the custody and final prior-exposure gates pass. Only the post-registration extension is genuinely prospective. No pooled estimate across the three evidence partitions is authorized.

# 4. Data, sample partitions, and feasibility gates

## 4.1 Target population and sample periods

The target population is ordinary A-shares listed on the Shanghai or Shenzhen exchanges. B-shares, funds, bonds, preferred shares, non-equity instruments, and Beijing Stock Exchange securities are outside the current boundary. Historical eligibility begins on or after a security’s listing date and ends after its delisting date. A final-survivor universe is retained only as a deliberately optimistic comparator. Stable permanent identifiers, or documented links across symbol changes, are required; duplicate date–symbol quote keys and duplicate effective security-master records fail closed.

The proposed historical rebalance interval is fixed at 1 January 2010 through 31 December 2022. Rolling signals may use observations from a warm-up beginning 1 January 2009, but no warm-up observation contributes to a confirmatory outcome. The rebalance date is the first common official SSE/SZSE session of each month, producing 156 target months. The final December 2022 forward horizon extends 20 official sessions into January 2023. All historical rebalance dates precede the pilot’s January 2025–June 2026 evaluation window, but the final horizon shares raw quote dates with the pilot market file; those endpoint prices are inputs, not pilot factor-cell or rebalance estimates.

The exposure boundary is not inferred from calendar labels. A legacy feasibility audit has already inspected schemas and aggregate coverage in the local bundle, including fundamental records from 2020Q1 through 2022. The study has not obtained a complete 2010–2022 historical quote outcome panel and has not assembled or viewed a factor-return or IC series for the proposed historical interval. Whether the panel qualifies as outcome-blind nevertheless remains conditional on a final signed prior-exposure attestation, complete exposure inventory, independent custody, and authorized release.

At least 12 months accumulated after external registration or journal in-principle acceptance will form a prospective extension. Its estimates will be shown separately from both the historical panel and the pilot. If the journal approves another prospective duration before observations accrue, that approved duration will control. No prospective observation will be used to alter the historical primary definition, and no pooled headline estimate is authorized.

## 4.2 Required inputs and semantics

The IC core requires four bound inputs: a daily quote panel, a historically effective security master, publication-dated fundamentals, and a common official exchange calendar. The quote panel must document vendor-adjusted close-return semantics and corporate-action handling; daily turnover amount units; and contemporaneous ST and suspension status. The security master must include delisted securities and historically valid list, delist, board, and security-type fields. Fundamentals must preserve the provider’s raw `roeDiluted` definition, its units and formula, report-period end, and first publication date. The official calendar must document source provenance, timezone, exact session dates, schema version, and file hash.

ROE is the latest eligible cumulative interim or annual `roeDiluted` observation, normalized to decimal units without analyst annualization and rejected when more than 18 months stale. Duplicate symbol–report-period rows fail closed unless a separately validated vintage schema identifies versions. When only a publication date is known, the value becomes eligible only when `publishDate < signal date`. A same-day report is therefore never used in that day’s close signal. This conservative rule does not reconstruct intraday availability and does not establish which numerical vintage an investor saw.

Data rights are part of feasibility, not a disclosure footnote. The research team must have lawful local-analysis rights and permission to publish aggregate results, field definitions, input hashes, and the exact official-calendar sessions embedded in the receipt. Licensed raw rows will not be redistributed without explicit permission. Reviewability requires either a lawful independent rerun or controlled access for an authorized reviewer; hashes identify bytes but do not prove vendor correctness.

## 4.3 Outcome-blind pre-lock gates

Before registration, only metadata, field coverage, semantics, and rights may be inspected. The coverage report may not contain factor ICs, portfolio returns, candidate rankings, or any other confirmatory outcome. The design advances only if all of the following are documented without outcome access:

1. the 2009 warm-up, all 156 target months, and the January 2023 endpoint are present;
2. every target month contains at least 15 official sessions and 1,000 quoted securities;
3. at least 95% of otherwise usable fundamental records contain a valid publication date;
4. historical listing and delisting dates are present and delisted securities remain in the master;
5. adjusted-close, corporate-action, amount, ST, suspension, and decision-cutoff semantics are reviewed and hash-bound;
6. the official common-session calendar is reviewed and hash-bound;
7. research, aggregate-disclosure, calendar-publication, and reviewer-access rights are recorded;
8. the complete offline test suite passes, and the plan enumerates every factor, variant, and estimand; and
9. the owner signs a prior-exposure attestation and binds a contemporaneous inventory of earlier specifications and known outcome access.

The outcome-blind coverage specification itself must receive an external timestamp before it is run. Failure stops the design. The sample may not be shortened, moved to a later feasible period, or made less demanding after factor outcomes are viewed. A materially different feasible study requires a new timestamped protocol and cannot inherit the primary status of this one.

After authorized execution, a separate evidence-eligibility stop requires all 72 cells in all 156 months and at least 1,000 finite signal–outcome pairs per factor–variant month. Failure yields `INSUFFICIENT_EVIDENCE`; it does not permit dropping a cell or lowering a threshold.

> **Current feasibility status: BLOCKED_FOR_STAGE2.** The licensed quote bundle begins in 2023 and supplies zero target rebalance months for 2010–2022. Fundamentals begin at 2020Q1, so 2009–2019 records and part of the required early interval are absent; the existing 2020–2022 rows have already been inspected only for legacy schema and aggregate coverage. The bound official calendar, raw `roeDiluted` mapping, adjusted-return and corporate-action semantics, non-degenerate suspension evidence, aggregate-publication rights, final prior-exposure attestation, and complete registration chain are absent. A legacy three-file current-bundle audit has run, but the externally timestamped four-input historical coverage probe and every confirmatory outcome analysis remain unrun.

# 5. Questions, hypotheses, and estimand ledger

## 5.1 Sole primary hypothesis

The sole primary hypothesis is pilot-informed:

**H1 — ROE publication-timing mean contrast.** Within the historical listing universe, the pilot-informed directional prediction is that moving ROE eligibility from fiscal report-period end to the recorded report publication date produces a negative mean monthly change in the cross-sectional association between ROE rank and subsequent return: `E[d_t] < 0`.

For month `t`, let `IC_f,v,t` be the cross-sectional rank correlation between factor `f` under variant `v` and the pre-specified 20-session return. The primary monthly contrast is

`d_t = IC_ROE,I0000,t − IC_ROE,A1,t`,

and the primary estimand is the time-series mean of `d_t` across the fixed historical panel. The reported test is the two-sided null `H0: E[d_t] = 0`, accompanied by a two-sided p-value and 95% confidence interval. This separates the pilot-informed directional prediction from the inferential test and makes a positive sign reversal visible.

The manuscript may use “timing inflation” or “timing attenuation” only when the report-period comparator IC is positive and the signed difference is negative. That language is qualitative, not a percentage estimator. If the sign condition fails, the neutral term “timing displacement” is used.

## 5.2 Confirmatory and descriptive families

**Table 2. Pre-specified estimand and reporting ledger**

| Group | Count | Definition | Inference | Authorized role |
|---|---:|---|---|---|
| Primary P1 | 1 | ROE `I0000 − A1` monthly IC | NW HAC lag 3; two-sided 95% CI and p-value | Sole primary conclusion |
| Composite timing | 1 | Composite `I0000 − A1` monthly IC | Included in BH family | Downstream ROE-dependent secondary |
| Membership effects | 4 | `A1 − A0` IC, one per factor | Included in BH family | Secondary specification effect |
| Full-implementation effects | 4 | `I1111 − I0000` IC, one per factor | Included in BH family | Secondary bundled effect |
| Component Shapley effects | 16 | Four components × four factors | Monthly Shapley, NW inference; included in BH family | Conditional secondary attribution |
| Timing-isolation checks | 2 | Momentum and low-volatility `I0000 − A1` | Exact tolerance `1e−12`; no hypothesis test | Nonzero value invalidates the run |
| Cell completeness outputs | 72 | Four factors × 18 variants | Mean IC, NW t, top-minus-universe, mean N | Descriptive only; no cell discovery |

The inferential set therefore contains exactly 26 estimands: one primary plus a fixed 25-member secondary family. The secondary p-values receive Benjamini–Hochberg adjustment at nominal false-discovery rate 0.10 (Benjamini and Hochberg, 1995). The two isolation checks are outside that count. A non-estimable secondary member remains in the family denominator and is a non-rejection. Unadjusted and adjusted values will both be reported.

Momentum and low volatility do not depend on accounting publication dates. Their `I0000 − A1` IC contrasts must therefore equal zero to absolute tolerance `1e−12`. A nonzero contrast is not a factor result; it indicates that the implementation failed to isolate the changed information field and causes the run to fail closed.

# 6. Factor definitions and variant architecture

## 6.1 Signals and outcomes

The four fixed signals are:

- **ROE:** the most recent eligible provider `roeDiluted` observation, normalized to decimal units, not more than 18 months stale;
- **Momentum 60d:** adjusted close on the signal session divided by adjusted close 60 official sessions earlier, minus one;
- **Low volatility 20d:** the negative standard deviation of daily adjusted returns over the preceding 20 official sessions; and
- **Composite:** 0.50 times the cross-sectional percentile rank of ROE, plus 0.30 times the momentum rank, plus 0.20 times the low-volatility rank.

The weights are fixed and will not be re-estimated. Missing signals are not filled with cross-sectional means: a security lacking a required factor field is excluded from that factor’s monthly cross-section, and the composite is complete-case across all three component ranks. Rank IC requires no raw-ratio winsorization. Industry neutralization, size residualization, alternative lookbacks, reconstructed ROE, and raw-ratio regressions are outside the current executable claim set.

The no-lag IC outcome is adjusted close at session `t+20` divided by adjusted close at signal session `t`, minus one. The lagged outcome is adjusted close at `t+21` divided by adjusted close at `t+1`, minus one. Endpoints are positions on the common official calendar. If a security lacks a required endpoint row, the outcome is missing; the code may not silently advance to that security’s next observed quote. These are diagnostic close-to-close outcomes, not simulated fills.

For continuity with the pilot, each cell also reports the equal-weight top signal quintile return minus the equal-weight universe mean. This statistic is neither self-financing nor cost adjusted and cannot support an implementability claim.

## 6.2 Ordered information-set chain

The information-set chain contains three variants with no implementation component:

1. `A0_final_report_end`: final-survivor universe; ROE available at report-period end;
2. `A1_pit_report_end`: historical listing universe; ROE available at report-period end; and
3. `I0000_pit_publication`: historical listing universe; ROE available strictly after publication date.

The paired difference `A1 − A0` measures the historical-membership specification effect within available fields. The paired difference `I0000 − A1` measures publication timing for accounting-dependent signals. These transitions are intentionally ordered; the paper does not claim that reversing them would yield the same attribution.

## 6.3 Complete implementation block

Starting at `I0000`, the study crosses four binary components: ST exclusion on the signal session, suspension exclusion on the signal session, a 20-session mean turnover-amount floor of CNY 5 million, and a one-official-session outcome lag. Every subset is pre-specified and intended for external registration. The 16 factorial variants share the historical listing universe and recorded publication-date accounting rule. Together with `A0` and `A1`, there are 18 variants and, with four factors, 72 aggregate cells.

[[FIGURE:DESIGN_MAP]]

*Figure 2. Pre-specified design map.* The information-set chain is ordered. The implementation block evaluates every subset, so its Shapley allocation is invariant to a preferred sequence of component entry. The shared `I0000` cell appears once in the 18-variant count.

## 6.4 Exact monthly Shapley decomposition

Following Shapley (1953), let `v_t(S)` be the monthly IC for a fixed factor under component subset `S`, with `K = 4` components. For component `i`, the monthly contribution is

`phi_i,t = sum_{S not containing i} [ |S|! (K−|S|−1)! / K! ] [ v_t(S union {i}) − v_t(S) ].`

All 16 subset values must be finite in a month before that month enters the component summary. The implementation computes Shapley contributions separately in each complete month, verifies that their sum equals `v_t(all) − v_t(empty)` up to numerical rounding, and then applies Newey–West inference to each component’s monthly contribution series. No interpolation replaces a missing subset. The allocation distributes interactions among components, but it is not a formal interaction test. The planned two-way interaction module remains unimplemented and excluded.

# 7. Estimation, inference, and reporting discipline

The unit of time-series inference is the monthly cross-section. Paired contrasts use only months for which both variants have finite pre-specified ICs; comparing two separately estimated t-statistics is prohibited. For the primary contrast and every inferential secondary, the study reports the mean monthly difference, Newey–West HAC standard error with lag three, two-sided t-statistic, two-sided p-value, and 95% confidence interval (Newey and West, 1987).

The primary receives no multiplicity adjustment because it is the only primary estimand. The fixed secondary family has 25 members and uses Benjamini–Hochberg adjusted p-values at nominal FDR 0.10. The estimands are correlated by construction, so the paper will report the complete dependence context and will not treat an adjusted threshold as a substitute for effect size, confidence intervals, or design logic. Secondary estimates remain secondary even if their adjusted statistics are stronger than the primary result.

If fewer than 120 paired months remain for an estimand, its estimate and interval are shown but no statistical-significance or generalization claim is authorized. This rule is an additional estimand-level claim gate; it does not relax the stronger evidence requirement that all 156 factor–variant months be present with at least 1,000 finite pairs per cell. Under a normal-approximation design sensitivity with 156 months, monthly paired-difference standard deviation of 0.08–0.12, and HAC variance inflation of 1.0–1.5, an absolute IC effect of roughly 0.018–0.033 is the range the design is expected to detect with 80% power. This is a planning sensitivity, not a guaranteed threshold, and no historical outcome may be used to revise it.

The 72 cell-level mean ICs, Newey–West t-statistics, top-minus-universe spreads, and mean cross-sectional counts will be displayed in full. They are descriptive completeness outputs, not 72 independent discovery tests. No cell-specific hypothesis is proposed. The paper will not headline the maximum, relabel a factor according to the more favorable of IC and quintile spread, or conceal a pre-specified cell because it is null or sign reversing.

Dedicated signal-missingness tables, per-security reason codes, eligible-universe-loss decomposition, percentage attenuation, raw-ratio regressions, stationary-bootstrap intervals, robustness factors, formal interactions, next-open portfolios, transaction costs, turnover, and nonfills are not currently implemented. Listing them as possible future work does not register them. An extension can enter confirmatory evidence only if its code, numerical settings, data gates, estimands, and multiplicity treatment are completed, tested, and externally frozen before confirmatory outcome access.

# 8. Registration, reproducibility, and stopping rules

The evidence chain is designed to separate specification from outcome release. First, the team completes and freezes the outcome-blind coverage report, rights and semantics review, official calendar, prior-specification inventory, and owner exposure attestation. Second, it materializes the flat plan core, binding the dates, factors, 18 variants, clocks, missingness rules, inference settings, and artifact hashes. Third, a design manifest binds that exact plan core, code revision, protocol, data declaration, four raw-input identities, and gate evidence. Fourth, an external provider or journal timestamps the manifest bytes or their SHA-256 digest. Fifth, a registration receipt records the provider evidence. Sixth, independent verification precedes a separate execution authorization that points backward to the frozen core, manifest, receipt, calendar, and gates. Seventh, the final execution-plan envelope records the plan-core, manifest, receipt, and authorization hashes and sets `locked_at = authorized_at` without altering the registered plan core. Only then may the blind historical outcome panel be released.

If the provider supplies no verifiable digital signature, hashes establish artifact identity and integrity but do not authenticate the provider timestamp by themselves. A named authorized human must verify and hash the retained provider page, email, or journal record. This human verification is an explicit trust boundary, not a cryptographic guarantee.

This sequence records scope and chronology; it is not a cryptographic guarantee that software can execute only once. Every execution, authorized rerun, or deviation must therefore be disclosed. The current machine-readable deviation and receipt-reporting module is planned but unimplemented. Until it exists and is frozen, deviations require a manual timestamp, rationale, affected estimand, and classification as administrative, outcome-blind data driven, or outcome aware. An outcome-aware deviation cannot replace the primary analysis and can appear only in a labeled exploratory appendix.

The public reproducibility package is intended to include the timestamped plan and manifest, tagged code, public schemas and deterministic fixtures, unit and end-to-end tests, raw-file names and hashes without local paths, calendar identity, field and rights statements where permitted, the prior-specification inventory, the signed exposure attestation, the complete aggregate result matrix, and a canonical receipt. Proprietary rows are not promised. An independent authorized rerun is preferred. The verifier checks hashes, required factor–variant–month identities, result counts, estimand identities, and exposed cross-sectional sizes; it cannot prove that every per-security omission was justified or detect every arbitrary silent drop.

The study stops without a primary conclusion if a coverage or rights gate fails; prior exposure cannot be resolved; manifest, receipt, or authorization hashes are missing or out of order; a required cell is missing; publication and report-period dates cannot be distinguished; adjusted-return or official-session semantics cannot be documented; an isolation check is nonzero; or the authorized code cannot reproduce its receipt. Negative, null, mixed, and sign-reversing economic outcomes are not stop conditions.

# 9. Outcome-contingent interpretation

The interpretation below is fixed before confirmatory access.

**Table 3. Pre-specified outcome and stopping interpretation**

| Observed condition | Authorized interpretation | Prohibited interpretation |
|---|---|---|
| Primary mean is negative and CI excludes zero | Publication-date alignment reduces ROE IC in the historical panel; “attenuation” only if comparator IC is positive | Proof of revision bias, causal mechanism, or investable alpha |
| Primary CI includes zero | A nonzero mean effect is not established; precision is assessed from the interval’s width | Proof of no effect, equivalence, or pilot generalization |
| Primary mean is positive and CI excludes zero | Directional expectation is rejected; publication timing increases measured ROE IC in this panel | Relabeling the sign, changing H1, or suppressing the result |
| Secondary estimates differ across factors or components | Descriptive differences are reported; Shapley allocates the complete implementation effect | A formal interaction or heterogeneity claim, or selecting the best factor/component as a new primary discovery |
| A timing-isolation check is nonzero | Implementation-isolation failure; run stops and is diagnosed | Treating the failed check as momentum or low-volatility evidence |
| A data, rights, registration, or cell gate fails | `BLOCKED_FOR_STAGE2` or `INSUFFICIENT_EVIDENCE`; no primary conclusion | Shortening the interval, dropping cells, or relaxing thresholds after outcomes |

Regardless of statistical significance, the paper will distinguish the observed pilot, the historical confirmatory estimates, the prospective extension, and any exploratory appendix. Pilot statistics will not be re-tested as if newly observed. The prospective extension will not be pooled with the historical panel merely to improve significance. Exact effect sizes, intervals, adjusted and unadjusted p-values, and all pre-specified cells will be retained when the conclusion is null or unfavorable.

# 10. Limitations

First, the historical confirmatory panel is not forward in calendar time and is not yet entitled to an unconditional outcome-blind label. Some 2020–2022 fundamental rows have already been inspected for schema and aggregate coverage, although no complete historical quote outcome panel or historical factor-return/IC series has been assembled or viewed. Its protection depends on a complete exposure inventory, signed attestation, credible custody, external timestamping, and authorized release. Only the post-registration extension can provide genuinely prospective evidence.

Second, the required historical dataset and publication rights are not yet secured. The current local bundle cannot answer the confirmatory question. A Stage-1 editorial review may evaluate the design, but execution must remain blocked until the quote history, early fundamentals, official calendar, field semantics, and lawful review path are documented.

Third, publication-date alignment is not vintage reconstruction. The dataset must distinguish report period from first publication, but it need not—and currently cannot—show every subsequent correction or the exact value visible at every historical as-of timestamp. The study therefore makes no revision-history claim. A future vintage project would require revision identifiers, value-at-vintage records, and a separately validated adapter.

Fourth, the executable outcome is IC based. It does not model a self-financing long–short portfolio, unadjusted executable entry prices, price-limit locks, borrow constraints, turnover, commissions, stamp duty, slippage, capacity, or nonfills. A positive IC or quintile spread is not evidence that a strategy is implementable. A portfolio module would need to be completed and frozen before outcome access or pursued under a new protocol.

Fifth, the four signals are deliberately simple. Vendor-supplied ROE and short price windows may not match canonical academic factor definitions, and the composite weights are heuristic. This is acceptable for measuring specification effects but limits structural asset-pricing interpretation. The paper does not claim that the factors are new or that the results identify a unique economic channel.

Sixth, the secondary family contains correlated contrasts and Shapley allocations. Benjamini–Hochberg adjustment is a pre-specified reporting discipline, not a license to ignore its assumptions. Effect sizes, confidence intervals, family structure, and all non-rejections will therefore accompany adjusted values. Formal dependence-robust or resampling extensions cannot be added after outcomes unless separately frozen in advance.

Finally, public code and fixtures do not yield fully independent empirical reproduction when raw rows are licensed. Hashes establish identity, not correctness. The absence of a software license also means the repository is not presently described as open source. These legal and access limitations must be resolved separately from the statistical protocol.

# 11. Conclusion

This Stage-1 manuscript turns an already observed factor pilot into a narrower and more credible measurement question: how much do historical membership, recorded report-publication-date alignment using a single-version export, and implementation conventions move A-share factor evidence? The answer will not come from choosing the strongest of many variants. It will come from a fixed paired primary contrast, a complete implementation factorial, conditional exact monthly Shapley attribution, a bounded secondary family, deterministic isolation checks, and publication of every pre-specified cell.

The design is informative under negative, null, positive, mixed, or sign-reversing outcomes. A large negative primary effect would quantify the distance between report-period and recorded-publication-date evidence. An interval containing zero would fail to establish a nonzero historical effect; its width would determine the degree of precision. A positive result would reject the stated direction. Gate failure would reveal that the question cannot yet be answered with auditable data. None of these outcomes authorizes a portfolio or data-revision claim.

At the date of this manuscript, the study remains blocked for historical data feasibility and has not been externally registered, authorized, or executed. That status is a disclosure and claim boundary: the research claim opens only after the evidence chain is complete, not because the document looks finished.

# Appendix A. Pre-specified variant inventory

The 18 variants below are fixed. `I0000` is both the final information-set state and the empty implementation subset, so it is counted once.

| ID | Historical universe | Accounting availability | Enabled implementation components |
|---|---|---|---|
| A0_final_report_end | Final survivors | Report-period end | None |
| A1_pit_report_end | Point in time | Report-period end | None |
| I0000_pit_publication | Point in time | Publication date | None |
| I1000_st | Point in time | Publication date | ST exclusion |
| I0100_suspension | Point in time | Publication date | Suspension exclusion |
| I0010_liquidity | Point in time | Publication date | CNY 5m amount floor |
| I0001_lag | Point in time | Publication date | One-session lag |
| I1100_st_suspension | Point in time | Publication date | ST; suspension |
| I1010_st_liquidity | Point in time | Publication date | ST; liquidity |
| I1001_st_lag | Point in time | Publication date | ST; lag |
| I0110_suspension_liquidity | Point in time | Publication date | Suspension; liquidity |
| I0101_suspension_lag | Point in time | Publication date | Suspension; lag |
| I0011_liquidity_lag | Point in time | Publication date | Liquidity; lag |
| I1110_st_suspension_liquidity | Point in time | Publication date | ST; suspension; liquidity |
| I1101_st_suspension_lag | Point in time | Publication date | ST; suspension; lag |
| I1011_st_liquidity_lag | Point in time | Publication date | ST; liquidity; lag |
| I0111_suspension_liquidity_lag | Point in time | Publication date | Suspension; liquidity; lag |
| I1111_full_implementation | Point in time | Publication date | ST; suspension; liquidity; lag |

# Declarations

## Pre-registration status

This manuscript has not been externally registered and has not received journal in-principle acceptance. The externally timestamped historical coverage probe has not been run; the final design manifest has not been created, the registration receipt has not been issued, the execution authorization has not been signed, and the confirmatory analysis has not been executed. The pilot was observed before the present specification and is disclosed in Section 3.

## Data and code availability

The observed pilot uses licensed data that cannot be redistributed. Its aggregate receipt and the analysis implementation are maintained in the public project repository. The proposed historical panel is not currently available to the study under a completed rights and semantics attestation. Public schemas, deterministic fixtures, plan templates, and aggregate evidence may be shared subject to the final repository license and data agreements. The repository currently has no software license and is not described as open source.

## Authorship, funding, and competing interests

This is an anonymous internal drafting version. Author names, affiliations, ORCID identifiers, CRediT contributions, funding declarations, and competing-interest statements are intentionally deferred to the private author identity package and must be completed before any external submission.

## Declaration of generative AI and AI-assisted technologies in the manuscript preparation process

**Draft declaration — human confirmation required before submission.** OpenAI Codex was used to support literature organization, research-protocol consistency checking, code and evidence inspection, manuscript drafting, document generation, and editing. No confirmatory outcome was generated or inferred by the tool. Before submission, the named human authors must verify every source, number, method, interpretation, and disclosure; edit the manuscript as needed; record the tool and version required by the journal; and take full responsibility for the content.

# References

Ang, A., Hodrick, R. J., Xing, Y., & Zhang, X. (2006). The cross-section of volatility and expected returns. *Journal of Finance, 61*(1), 259–299. https://doi.org/10.1111/j.1540-6261.2006.00836.x

Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate: A practical and powerful approach to multiple testing. *Journal of the Royal Statistical Society: Series B (Methodological), 57*(1), 289–300. https://doi.org/10.1111/j.2517-6161.1995.tb02031.x

Brown, S. J., Goetzmann, W., Ibbotson, R. G., & Ross, S. A. (1992). Survivorship bias in performance studies. *Review of Financial Studies, 5*(4), 553–580. https://doi.org/10.1093/rfs/5.4.553

Faff, R. W. (2023). PBFJ editorial: Engaging with responsible science—“Open for business”—launching the PBFJ pre-registration publication initiative. *Pacific-Basin Finance Journal, 79*, 101837. https://doi.org/10.1016/j.pacfin.2022.101837

Faff, R. W. (2026). PBFJ editorial: Responsible and open science in action—an update on the PBFJ experiment and beyond. *Pacific-Basin Finance Journal, 96*, 103045. https://doi.org/10.1016/j.pacfin.2025.103045

Gharghori, P., & Nguyen, A. (2025). Which factors in China? A pre-registered report. *Pacific-Basin Finance Journal, 91*, 102562. https://doi.org/10.1016/j.pacfin.2024.102562

Gharghori, P., & Nguyen, A. (2026). Which factors in China? A pre-registered study. *Pacific-Basin Finance Journal, 96*, 103012. https://doi.org/10.1016/j.pacfin.2025.103012

Harvey, C. R., Liu, Y., & Zhu, H. (2016). … and the cross-section of expected returns. *Review of Financial Studies, 29*(1), 5–68. https://doi.org/10.1093/rfs/hhv059

Hou, K., Xue, C., & Zhang, L. (2020). Replicating anomalies. *Review of Financial Studies, 33*(5), 2019–2133. https://doi.org/10.1093/rfs/hhy131

Jegadeesh, N., & Titman, S. (1993). Returns to buying winners and selling losers: Implications for stock market efficiency. *Journal of Finance, 48*(1), 65–91. https://doi.org/10.1111/j.1540-6261.1993.tb04702.x

Li, Z., Liu, L. X., Liu, X., & Wei, K. C. J. (2024). Replicating and digesting anomalies in the Chinese A-share market. *Management Science, 70*(8), 5066–5090. https://doi.org/10.1287/mnsc.2023.4904

Liu, J., Stambaugh, R. F., & Yuan, Y. (2019). Size and value in China. *Journal of Financial Economics, 134*(1), 48–69. https://doi.org/10.1016/j.jfineco.2019.03.008

Lo, A. W., & MacKinlay, A. C. (1990). Data-snooping biases in tests of financial asset pricing models. *Review of Financial Studies, 3*(3), 431–467. https://doi.org/10.1093/rfs/3.3.431

Newey, W. K., & West, K. D. (1987). A simple, positive semi-definite, heteroskedasticity and autocorrelation consistent covariance matrix. *Econometrica, 55*(3), 703–708. https://doi.org/10.2307/1913610

Novy-Marx, R. (2013). The other side of value: The gross profitability premium. *Journal of Financial Economics, 108*(1), 1–28. https://doi.org/10.1016/j.jfineco.2013.01.003

Novy-Marx, R., & Velikov, M. (2016). A taxonomy of anomalies and their trading costs. *Review of Financial Studies, 29*(1), 104–147. https://doi.org/10.1093/rfs/hhv063

Shapley, L. S. (1953). A value for n-person games. In H. W. Kuhn & A. W. Tucker (Eds.), *Contributions to the Theory of Games II* (pp. 307–317). Princeton University Press.

Shumway, T. (1997). The delisting bias in CRSP data. *Journal of Finance, 52*(1), 327–340. https://doi.org/10.1111/j.1540-6261.1997.tb03818.x

White, H. (2000). A reality check for data snooping. *Econometrica, 68*(5), 1097–1126. https://doi.org/10.1111/1468-0262.00152
