# Data Availability

This project was developed with local A-share research data assets that are not committed to GitHub.

The repository keeps schemas, validation reports, manifests, and reproducible scripts, while excluding large or licensed datasets from version control.

## Local Data Used During Development

- Historical stock master: full A-share listing and delisting metadata.
- Daily quotes: 3,894,242 validated rows through 2026-07-24.
- Fundamental factors: ROE, cash-flow quality, balance-sheet quality, growth, and related accounting factors.
- Dividend events.
- Margin-trade records: 2,399,572 rows restored from Investoday.

## Why Raw Data Is Excluded

- Some files exceed GitHub's 100 MB single-file limit.
- Some data came from vendor/API sources and should not be redistributed.
- Reproducibility is preserved through scripts, manifests, validation reports, and schema templates.

## Included Instead

- `data_assets/templates/*.csv`: minimal schema templates.
- `data_assets/manifests/production_import/*.md`: production validation reports.
- `reports/portfolio_readiness/latest_portfolio_readiness.md`: GitHub/application readiness summary.
- `reports/completion_readiness/latest_readiness.md`: strict research/paper/live readiness boundary.
- `reports/strategy_factory/latest_board.md`: latest strategy factory summary.

## Rebuild Locally

Provide your own vendor export or API access, then run:

```bash
PYTHONPATH=src python3 examples/validate_production_data_assets.py --asset-root data_assets --start 20230101 --end 20260724
PYTHONPATH=src python3 examples/check_portfolio_readiness.py --reports-root reports --asset-root data_assets
```

The project is designed so reviewers can inspect methodology without requiring redistribution of raw market data.
