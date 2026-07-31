# A-Share Quant Research Agent

This repository is a graduate-application portfolio project for quantitative finance and financial engineering.

It is intentionally framed as a research and validation system, not as a live-trading product. The project demonstrates how I think about data engineering, point-in-time backtesting, factor research, walk-forward validation, risk controls, and honest model failure analysis.

## What It Shows

- Production-style A-share data pipeline with stock master, daily quotes, fundamentals, dividends, and margin-trade assets.
- Point-in-time universe controls for listing status, delisting, liquidity membership, ST status, suspension, limit moves, and benchmark regime features.
- Rule-based strategy specs that can be generated from natural language and evaluated by a strategy factory.
- Realistic Chinese A-share backtesting assumptions: T+1 constraints, lot-size trading, commission, stamp tax, slippage, cash yield, and monthly rebalancing.
- Validation stack: sensitivity tests, walk-forward analysis, factor IC diagnostics, benchmark comparison, bias diagnostics, audit reports, and run registry.
- Risk overlays: trend/momentum filters, cash-buffer exposure, window fuse, market breadth/alpha-health filters, and overheated-reversal guard.
- A separate readiness boundary that distinguishes research showcase readiness from paper/live trading readiness.

## Current Result

The project is portfolio-ready but not live-trading-ready.

The best research line is a defensive quality cash-buffer family. It uses dividend yield, ROE sanity, low volatility, valuation sanity, PIT universe filters, and cash yield. Its strongest historical candidate reached:

- Walk-forward positive rate: about 83%.
- Max drawdown: about -2% to -3%.
- Factor IC: supportive, with no adverse IC count in the best run.
- Status: research/testing, not paper candidate.

The strict production gate correctly blocks promotion because some out-of-sample windows still fail. This is kept deliberately: for a serious quant project, the failed windows are part of the evidence, not something to hide.

## Why This Is Useful For Quant/MFE Applications

This project emphasizes research discipline over a single attractive return chart:

- It avoids manually overriding decision gates.
- It records rejected strategies instead of deleting them.
- It separates in-sample attractiveness from out-of-sample robustness.
- It keeps data lineage and validation artifacts.
- It documents remaining blockers: no stable paper candidate, stale current data after 2026-07-24, and incomplete capital-flow entitlement.

That makes it closer to a research notebook plus engineering system than a toy strategy demo.

## Key Artifacts

- `reports/portfolio_readiness/latest_portfolio_readiness.md`
- `reports/completion_readiness/latest_readiness.md`
- `reports/strategy_factory/latest_board.md`
- `reports/strategy_factory/idea_registry.csv`
- `data_assets/manifests/production_import/production_asset_validation.md`
- `configs/strategy_factory_defensive_quality_cash_buffer_variants.json`
- `configs/strategy_factory_overheated_reversal_guard_variants.json`

## Reproduce Core Checks

```bash
PYTHONPATH=src python3 examples/validate_production_data_assets.py --asset-root data_assets --start 20230101 --end 20260724
PYTHONPATH=src python3 examples/risk_overlay_smoke_test.py
PYTHONPATH=src python3 examples/check_completion_readiness.py --reports-root reports
PYTHONPATH=src python3 examples/check_portfolio_readiness.py --reports-root reports --asset-root data_assets
```

Run the latest strategy-factory candidate set:

```bash
PYTHONPATH=src python3 examples/run_strategy_factory.py \
  --templates configs/strategy_factory_overheated_reversal_guard_variants.json \
  --source production \
  --asset-root data_assets \
  --start 20230101 \
  --end 20260724 \
  --universe-size 100 \
  --benchmark-code 000300
```

## Boundary

This repository is for research demonstration and application evidence only. It does not provide investment advice, does not connect to a broker, and does not claim live deployment readiness.
