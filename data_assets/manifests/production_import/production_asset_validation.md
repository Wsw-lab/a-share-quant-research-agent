## Production Asset Validation

Status: `production_ready`
Production data ready: yes
Hard failed: 0
Warnings: 2
Range: `20230101` to `20260724`

### Stock Master

Status: `production_ready`
Coverage level: `full_historical_stock_master`
Hard failed: 0

### Daily Quotes

Rows: 3894242
Unique symbols: 4735
Eligible symbols: 4735
Covered eligible symbols: 4735
Eligible symbol coverage: 100.00%
Trading dates: 861
Median symbol date coverage: 100.00%
Duplicate keys: 0
Bad OHLC rows: 0
Bad amount/volume rows: 0
Daily quote PE/PB coverage: 0.00% / 0.00%
Daily quote dividend yield coverage: 100.00%
Date range: 2023-01-03 to 2026-07-24

### Fundamental Factors

Exists: yes
Rows: 99628
Unique symbols: 4795
ROE symbol coverage: 100.00%
Dividend yield symbol coverage: 0.00%
Date range: 2020-04-08 to 2026-07-24

### Checks

| Check | Severity | Passed | Detail |
|---|---|---:|---|
| stock_master_production_ready | hard | yes | Stock master status is production_ready. |
| daily_quotes_exists | hard | yes | Daily quote asset path: data_assets/market/daily_quotes.csv. |
| daily_quote_rows | hard | yes | Daily quote rows: 3894242. |
| eligible_symbol_coverage | hard | yes | Eligible symbol coverage 100.00%; required >= 98.00%. |
| duplicate_daily_keys | hard | yes | Duplicate (date, symbol) rows: 0. |
| median_symbol_date_coverage | hard | yes | Median symbol date coverage 100.00%; required >= 90.00%. |
| price_integrity | hard | yes | Rows with nonpositive or internally inconsistent OHLC prices: 0. |
| amount_volume_integrity | hard | yes | Rows with negative amount/volume: 0. |
| date_range_start | warn | no | Quote min date 2023-01-03 should be on or before 20230101. |
| date_range_end | warn | yes | Quote max date 2026-07-24 should be on or after 20260724. |
| fundamental_factor_schema | warn | yes | Fundamental factor asset path: data_assets/fundamentals/fundamental_factors.csv. |
| roe_factor_coverage | warn | yes | ROE effective symbol coverage 100.00%; recommended >= 50.00%. |
| dividend_yield_factor_coverage | warn | yes | Dividend yield effective symbol coverage 100.00%; recommended >= 50.00%. |
| fundamental_duplicate_keys | warn | yes | Duplicate fundamental (date, symbol) rows: 0. |
| margin_trade_schema | warn | yes | Margin trade asset path: data_assets/market/margin_trades.csv. |
| margin_trade_duplicate_keys | warn | yes | Duplicate margin trade (date, symbol) rows: 0. |
| fundamental_factor_schema | warn | yes | Fundamental factor asset path: data_assets/fundamentals/fundamental_factors.csv. |
| roe_factor_coverage | warn | yes | ROE factor symbol coverage 100.00%; recommended >= 50.00%. |
| dividend_yield_factor_coverage | warn | no | Dividend yield factor symbol coverage 0.00%; recommended >= 50.00%. |
| fundamental_duplicate_keys | warn | yes | Duplicate fundamental (date, symbol) rows: 0. |
