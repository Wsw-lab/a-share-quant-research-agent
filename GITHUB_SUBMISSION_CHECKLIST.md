# GitHub Submission Checklist

Use this before publishing the project.

## Keep In The Repository

- `README.md`
- `PROJECT_PORTFOLIO.md`
- `DATA_AVAILABILITY.md`
- `requirements-data.txt`
- `src/a_share_quant_agent/`
- `examples/`
- `configs/`
- `data_assets/README.md`
- `data_assets/templates/`
- `data_assets/manifests/production_import/*.md`
- `reports/portfolio_readiness/latest_portfolio_readiness.md`
- `reports/completion_readiness/latest_readiness.md`
- `reports/strategy_factory/latest_board.md`

## Do Not Commit

- `.venv-akshare/`
- `.venv312_restore/`
- `data_assets/cache/`
- `data_assets/backups/`
- `data_assets/market/*.csv`
- `data_assets/fundamentals/*.csv`
- `data_assets/stock_master/*.csv`
- `reports/**/artifacts/`
- `reports/**/runs/`
- Large CSV/PKL/Parquet/Feather files.

## Final Commands

```bash
PYTHONPATH=src python3 examples/risk_overlay_smoke_test.py
PYTHONPATH=src python3 examples/check_completion_readiness.py --reports-root reports
PYTHONPATH=src python3 examples/check_portfolio_readiness.py --reports-root reports --asset-root data_assets
```

Expected portfolio result:

```text
Status: portfolio_ready_not_live_ready
Showcase ready: True
```
